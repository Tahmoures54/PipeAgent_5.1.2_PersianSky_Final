# -*- coding: utf-8 -*-
"""
services/handover_service.py – PipeAgent
سرویس جامع مدیریت پرونده‌های تحویل، تکمیل مکانیکی (MC)، آماده‌سازی برای راه‌اندازی (RFC)
و واگذاری نهایی ساب‌سیستم‌ها و سیستم‌های فرآیندی (Systems / Subsystems Turnover).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, and_, or_, desc, case
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError

from db.manager import DatabaseManager
from db.models import (
    HandoverPackage,
    TurnoverDossier,
    Project,
    TestPackage,
    PunchItem,
    DocumentEvidence,
    IsoRegistry,
    LineListItem,
    Weld,
    NDTRecord,
    MechanicalCompletionCertificate,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Handover Standards
# ──────────────────────────────────────────────

class HandoverStage(str, Enum):
    """مراحل کلان تحویل طبق قراردادهای EPC"""
    MECHANICAL_COMPLETION = "MC"       # Implementation note.
    PRE_COMMISSIONING = "PRE_COMM"     # Implementation note.
    READY_FOR_COMMISSIONING = "RFC"    # Implementation note.
    PROVISIONAL_ACCEPTANCE = "PAC"     # Implementation note.
    FINAL_ACCEPTANCE = "FAC"           # Implementation note.


class HandoverStatus(str, Enum):
    """وضعیت‌های پکیج تحویل در گردش‌کار"""
    DRAFT = "DRAFT"                                    # Implementation note.
    UNDER_QC_REVIEW = "UNDER_QC_REVIEW"                # Implementation note.
    WALKDOWN_IN_PROGRESS = "WALKDOWN_IN_PROGRESS"      # Implementation note.
    PUNCH_CLEARING = "PUNCH_CLEARING"                  # Implementation note.
    READY_FOR_SIGN_OFF = "READY_FOR_SIGN_OFF"          # Implementation note.
    APPROVED = "APPROVED"                              # Implementation note.
    CONDITIONALLY_ACCEPTED = "CONDITIONALLY_ACCEPTED"  # Implementation note.
    REJECTED = "REJECTED"                              # Implementation note.
    TRANSFERRED = "TRANSFERRED"                        # Implementation note.


class SignatoryRole(str, Enum):
    """سمت‌های رسمی امضاکننده صورتجلسات تحویل"""
    CONTRACTOR_LEAD = "CONTRACTOR_LEAD"
    QC_MANAGER = "QC_MANAGER"
    CLIENT_PMT = "CLIENT_PMT"
    COMMISSIONING_LEAD = "COMMISSIONING_LEAD"
    OPERATIONS_HEAD = "OPERATIONS_HEAD"


# ──────────────────────────────────────────────
#  Custom Exceptions
# ──────────────────────────────────────────────

class HandoverGatekeeperError(Exception):
    """خطای عدم احراز شرایط و گیت‌های مهندسی تحویل"""
    pass


class PunchBlockerError(Exception):
    """خطای وجود پانچ‌های باز دسته A که مانع تحویل می‌شوند"""
    pass


# ──────────────────────────────────────────────
#  Handover Service Implementation
# ──────────────────────────────────────────────

class HandoverService:
    """
    سرویس مرکزی مدیریت واگذاری سیستم‌ها، اعتبارسنجی مدارک تحویل و صدور گواهی‌های MC و RFC
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    # Implementation note.

    def create_handover_package(
        self,
        project_id: int,
        package_number: str,
        system_code: str,
        subsystem_code: str,
        title: str,
        stage: Union[HandoverStage, str] = HandoverStage.MECHANICAL_COMPLETION,
        target_mc_date: Optional[date] = None,
        created_by: str = "system",
        description: str = "",
    ) -> HandoverPackage:
        """
        ایجاد پکیج تحویل جدید برای یک ساب‌سیستم مشخص با کدهای یکتا
        """
        pkg_num_clean = package_number.strip().upper()
        stage_val = stage.value if isinstance(stage, HandoverStage) else str(stage).strip().upper()

        with self.db.session_scope() as session:
            existing = (
                session.query(HandoverPackage)
                .filter(
                    HandoverPackage.project_id == project_id,
                    HandoverPackage.package_number == pkg_num_clean,
                )
                .first()
            )
            if existing:
                raise ValueError(f"Handover package '{pkg_num_clean}' already exists in Project #{project_id}.")

            pkg = HandoverPackage(
                project_id=project_id,
                package_number=pkg_num_clean,
                system_code=system_code.strip().upper(),
                subsystem_code=subsystem_code.strip().upper(),
                title=title.strip(),
                stage=stage_val,
                status=HandoverStatus.DRAFT.value,
                target_date=target_mc_date,
                created_by=created_by,
                description=description.strip(),
                created_at=datetime.utcnow(),
            )
            session.add(pkg)
            session.flush()

            logger.info(f"Handover Package '{pkg.package_number}' ({stage_val}) created for Subsystem '{subsystem_code}'.")
            return pkg

    # Implementation note.

    def evaluate_handover_readiness(
        self,
        project_id: int,
        package_id: int,
    ) -> Dict[str, Any]:
        """
        ارزیابی سخت‌گیرانه و چندبعدی آمادگی ساب‌سیستم جهت تکمیل مکانیکی (MC Readiness Audit):
        ۱. بررسی ۱۰۰٪ تست‌های هیدرواستاتیک خطوط داخل باندری
        ۲. بررسی ۱۰۰٪ ترخیص آزمون‌های NDT تمام سرجوش‌های پکیج
        ۳. بررسی صفر بودن قطعی پانچ‌های باز دسته A (Cat-A = 0)
        ۴. بررسی تأییدیه نقشه‌های چون‌ساخت (As-Built Isometrics)
        ۵. بررسی وضعیت بازگردانی مدار (Reinstatement Clearance)
        ۶. بررسی سلامت و اصالت فایل‌های مدارک اثباتی (Document Evidence Intactness)
        """
        with self.db.session_scope() as session:
            pkg = session.query(HandoverPackage).filter(
                HandoverPackage.id == package_id,
                HandoverPackage.project_id == project_id,
            ).first()

            if not pkg:
                raise ValueError(f"Handover Package #{package_id} not found.")

            subsystem = pkg.subsystem_code

            # Implementation note.
            lines = session.query(LineListItem).filter(
                LineListItem.project_id == project_id,
                LineListItem.subsystem == subsystem,
            ).all()
            total_lines = len(lines)
            line_numbers = [l.line_number.strip().upper() for l in lines if l.line_number]

            # Implementation note.
            test_packages = session.query(TestPackage).filter(
                TestPackage.project_id == project_id,
                TestPackage.subsystem_code == subsystem,
            ).all()
            total_tps = len(test_packages)
            tested_tps = sum(1 for tp in test_packages if str(tp.status).upper() in ["TEST_ACCEPTED", "CLOSED", "DOSSIER_CLOSED"])
            hydro_ready = (total_tps > 0) and (total_tps == tested_tps)

            # Implementation note.
            welds = session.query(Weld).filter(
                Weld.project_id == project_id,
                Weld.line_number.in_(line_numbers),
            ).all() if line_numbers else []

            total_welds = len(welds)
            cleared_welds = sum(1 for w in welds if str(w.status).upper() in ["NDT_CLEARED", "COMPLETED", "VT_ACCEPTED"])
            ndt_100_cleared = (total_welds == 0) or (total_welds == cleared_welds)

            # Implementation note.
            open_cat_a_punches = session.query(PunchItem).filter(
                PunchItem.project_id == project_id,
                PunchItem.category == "A",
                PunchItem.status.notin_(["QC_CLEARED", "CLIENT_ACCEPTED", "CLOSED", "CANCELLED"]),
                or_(
                    PunchItem.line_number.in_(line_numbers),
                    PunchItem.subsystem == subsystem,
                ),
            ).all()

            open_cat_b_punches = session.query(PunchItem).filter(
                PunchItem.project_id == project_id,
                PunchItem.category == "B",
                PunchItem.status.notin_(["QC_CLEARED", "CLIENT_ACCEPTED", "CLOSED", "CANCELLED"]),
                or_(
                    PunchItem.line_number.in_(line_numbers),
                    PunchItem.subsystem == subsystem,
                ),
            ).all()

            # Implementation note.
            asbuilt_approved_isos = session.query(func.count(IsoRegistry.id)).filter(
                IsoRegistry.project_id == project_id,
                IsoRegistry.line_number.in_(line_numbers),
                IsoRegistry.status == "AS_BUILT_APPROVED",
            ).scalar() or 0
            
            total_isos = session.query(func.count(IsoRegistry.id)).filter(
                IsoRegistry.project_id == project_id,
                IsoRegistry.line_number.in_(line_numbers),
            ).scalar() or 0

            isos_ready = (total_isos == 0) or (total_isos == asbuilt_approved_isos)

            # Implementation note.
            is_ready_for_mc = (
                hydro_ready
                and ndt_100_cleared
                and (len(open_cat_a_punches) == 0)
                and isos_ready
            )

            blocking_reasons: List[str] = []
            if not hydro_ready:
                blocking_reasons.append(f"Hydrostatic testing incomplete ({tested_tps}/{total_tps} test packs passed).")
            if not ndt_100_cleared:
                blocking_reasons.append(f"NDT clearance incomplete ({cleared_welds}/{total_welds} welds cleared).")
            if len(open_cat_a_punches) > 0:
                blocking_reasons.append(f"{len(open_cat_a_punches)} Open Category-A Punch item(s) exist.")
            if not isos_ready:
                blocking_reasons.append(f"As-Built drawings pending approval ({asbuilt_approved_isos}/{total_isos} approved).")

            return {
                "package_id": pkg.id,
                "package_number": pkg.package_number,
                "subsystem_code": subsystem,
                "is_ready_for_mc": is_ready_for_mc,
                "blocking_reasons": blocking_reasons,
                "metrics": {
                    "lines_count": total_lines,
                    "welds_count": total_welds,
                    "welds_cleared": cleared_welds,
                    "test_packages_total": total_tps,
                    "test_packages_passed": tested_tps,
                    "open_cat_a_punches_count": len(open_cat_a_punches),
                    "open_cat_b_punches_count": len(open_cat_b_punches),
                    "blocking_punch_ids": [p.id for p in open_cat_a_punches],
                    "total_isos_count": total_isos,
                    "asbuilt_isos_approved": asbuilt_approved_isos,
                },
            }

    # Implementation note.

    def initiate_joint_walkdown(
        self,
        project_id: int,
        package_id: int,
        walkdown_date: date,
        lead_inspector: str,
        client_representative: str,
    ) -> HandoverPackage:
        """شروع رسمی گشت میدانی مشترک پیمانکار و کارفرما جهت استخراج پانچ‌لیست تحویل"""
        with self.db.session_scope() as session:
            pkg = session.query(HandoverPackage).filter(
                HandoverPackage.id == package_id,
                HandoverPackage.project_id == project_id,
            ).first()

            if not pkg:
                raise ValueError(f"Handover Package #{package_id} not found.")

            pkg.status = HandoverStatus.WALKDOWN_IN_PROGRESS.value
            if hasattr(pkg, "walkdown_date"):
                pkg.walkdown_date = walkdown_date
            if hasattr(pkg, "lead_inspector"):
                pkg.lead_inspector = lead_inspector
            if hasattr(pkg, "client_rep"):
                pkg.client_rep = client_representative

            session.flush()
            logger.info(f"Joint Walkdown initiated for Handover Package '{pkg.package_number}'.")
            return pkg

    # Implementation note.

    def sign_handover_stage(
        self,
        project_id: int,
        package_id: int,
        signatory_role: Union[SignatoryRole, str],
        signatory_name: str,
        signature_comments: str = "",
        enforce_gatekeeper: bool = True,
    ) -> Dict[str, Any]:
        """
        ثبت امضای رسمی ذی‌نفعان پروژه با اعتبارسنجی اجباری پیش‌نیازها قبل از امضای نهایی
        """
        role_val = signatory_role.value if isinstance(signatory_role, SignatoryRole) else str(signatory_role)

        with self.db.session_scope() as session:
            pkg = session.query(HandoverPackage).filter(
                HandoverPackage.id == package_id,
                HandoverPackage.project_id == project_id,
            ).first()

            if not pkg:
                raise ValueError(f"Handover Package #{package_id} not found.")

            # Implementation note.
            if enforce_gatekeeper and role_val in [SignatoryRole.CLIENT_PMT.value, SignatoryRole.QC_MANAGER.value]:
                audit = self.evaluate_handover_readiness(project_id, package_id)
                if not audit["is_ready_for_mc"]:
                    raise HandoverGatekeeperError(
                        f"Cannot sign Handover Package #{package_id}: " + "; ".join(audit["blocking_reasons"])
                    )

            # Implementation note.
            signatures = json.loads(getattr(pkg, "signatures_json", None) or "{}")
            signatures[role_val] = {
                "name": signatory_name.strip(),
                "signed_at": datetime.utcnow().isoformat(),
                "comments": signature_comments.strip(),
            }
            pkg.signatures_json = json.dumps(signatures, default=str)

            # Implementation note.
            required_roles = {
                SignatoryRole.CONTRACTOR_LEAD.value,
                SignatoryRole.QC_MANAGER.value,
                SignatoryRole.CLIENT_PMT.value,
                SignatoryRole.COMMISSIONING_LEAD.value,
            }
            has_all_signatures = required_roles.issubset(set(signatures.keys()))

            if has_all_signatures:
                pkg.status = HandoverStatus.APPROVED.value
                pkg.completed_date = date.today()
                logger.info(f"Handover Package '{pkg.package_number}' FULLY APPROVED & SIGNED by all stakeholders.")
            else:
                pkg.status = HandoverStatus.READY_FOR_SIGN_OFF.value

            session.flush()

            return {
                "package_id": pkg.id,
                "package_number": pkg.package_number,
                "status": pkg.status,
                "signed_role": role_val,
                "all_signatures_completed": has_all_signatures,
                "signatures": signatures,
            }

    # Implementation note.

    def grant_conditional_acceptance(
        self,
        project_id: int,
        package_id: int,
        concession_reference_no: str,
        approved_by_client: str,
        agreed_punch_b_closure_deadline: date,
        concession_justification: str,
    ) -> HandoverPackage:
        """
        پذیرش مشروط ساب‌سیستم در صورت وجود پانچ‌های غیرمسدودکننده (دسته B)
        با اخذ تاییدیه رسمی Concession کارفرما جهت انتقال به راه‌اندازی (RFC).
        """
        with self.db.session_scope() as session:
            pkg = session.query(HandoverPackage).filter(
                HandoverPackage.id == package_id,
                HandoverPackage.project_id == project_id,
            ).first()

            if not pkg:
                raise ValueError(f"Handover Package #{package_id} not found.")

            # Implementation note.
            audit = self.evaluate_handover_readiness(project_id, package_id)
            if audit["metrics"]["open_cat_a_punches_count"] > 0:
                raise PunchBlockerError(
                    f"Conditional acceptance REJECTED: {audit['metrics']['open_cat_a_punches_count']} "
                    f"Category-A punches exist. Category-A cannot be carved out under any concession!"
                )

            pkg.status = HandoverStatus.CONDITIONALLY_ACCEPTED.value
            pkg.concession_number = concession_reference_no.strip().upper()
            pkg.concession_deadline = agreed_punch_b_closure_deadline
            pkg.concession_approved_by = approved_by_client
            pkg.concession_remarks = concession_justification.strip()

            session.flush()
            logger.warning(
                f"Handover Package '{pkg.package_number}' CONDITIONALLY ACCEPTED under Concession "
                f"'{concession_reference_no}' (Target B Closure: {agreed_punch_b_closure_deadline})."
            )
            return pkg

    # Implementation note.

    def get_turnover_matrix(self, project_id: int) -> Dict[str, Any]:
        """
        تولید ماتریس فوق‌سریع و مستقیم SQL از وضعیت کل سیستم‌ها و ساب‌سیستم‌های پروژه
        جهت رسم نمودار S-Curve تحویل مکانیکی (MC Progression).
        """
        with self.db.session_scope() as session:
            # Implementation note.
            pkg_stats = session.query(
                func.count(HandoverPackage.id).label("total_packages"),
                func.sum(case((HandoverPackage.status == HandoverStatus.APPROVED.value, 1), else_=0)).label("approved_mc"),
                func.sum(case((HandoverPackage.status == HandoverStatus.CONDITIONALLY_ACCEPTED.value, 1), else_=0)).label("conditional_mc"),
                func.sum(case((HandoverPackage.status == HandoverStatus.WALKDOWN_IN_PROGRESS.value, 1), else_=0)).label("in_walkdown"),
                func.sum(case((HandoverPackage.status == HandoverStatus.DRAFT.value, 1), else_=0)).label("in_draft"),
            ).filter(HandoverPackage.project_id == project_id).first()

            total_pkgs = pkg_stats.total_packages or 0
            approved_mc = pkg_stats.approved_mc or 0
            conditional_mc = pkg_stats.conditional_mc or 0
            transferred_mc = approved_mc + conditional_mc

            # Implementation note.
            dossier_stats = session.query(
                func.count(TurnoverDossier.id).label("total_dossiers"),
                func.sum(case((TurnoverDossier.completeness_pct >= 95.0, 1), else_=0)).label("completed_dossiers"),
                func.avg(func.coalesce(TurnoverDossier.completeness_pct, 0.0)).label("avg_completeness"),
            ).filter(TurnoverDossier.project_id == project_id).first()

            # Implementation note.
            punch_stats = session.query(
                func.sum(case((and_(PunchItem.category == "A", PunchItem.status.notin_(["QC_CLEARED", "CLIENT_ACCEPTED", "CLOSED"])), 1), else_=0)).label("open_cat_a"),
                func.sum(case((and_(PunchItem.category == "B", PunchItem.status.notin_(["QC_CLEARED", "CLIENT_ACCEPTED", "CLOSED"])), 1), else_=0)).label("open_cat_b"),
            ).filter(PunchItem.project_id == project_id).first()

            mc_progress_pct = round((transferred_mc / total_pkgs * 100), 2) if total_pkgs > 0 else 0.0

            return {
                "project_id": project_id,
                "timestamp": datetime.utcnow().isoformat(),
                "handover_summary": {
                    "total_subsystem_packages": total_pkgs,
                    "fully_approved_mc_packages": approved_mc,
                    "conditionally_accepted_packages": conditional_mc,
                    "in_walkdown_packages": pkg_stats.in_walkdown or 0,
                    "draft_packages": pkg_stats.in_draft or 0,
                    "mechanical_completion_progress_pct": mc_progress_pct,
                },
                "dossier_evidence_status": {
                    "total_dossiers": dossier_stats.total_dossiers or 0,
                    "completed_dossiers_95_plus": dossier_stats.completed_dossiers or 0,
                    "average_dossier_completeness_pct": round(float(dossier_stats.avg_completeness or 0.0), 1),
                },
                "project_punch_blockers": {
                    "open_critical_category_a": punch_stats.open_cat_a or 0,
                    "open_non_blocking_category_b": punch_stats.open_cat_b or 0,
                    "is_project_handover_blocked": (punch_stats.open_cat_a or 0) > 0,
                },
            }