# -*- coding: utf-8 -*-
"""
services/qaqc_service.py – PipeAgent
سرویس جامع کنترل و تضمین کیفیت (QA/QC Management Service)
شامل: چرخه حیات پیشرفته پانچ‌لیست‌ها (A/B/C)، فرآیند تعیین تکلیف و ممیزی NCRها،
مدیریت ماتریس ITP و درخواست‌های بازرسی (RFI) و گیت‌های هوشمند مجوز هیدروتست و تحویل مکانیکی.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, and_, or_, desc, case
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from core.exceptions import AppError
from repositories.qaqc_repository import (
    PunchRepository,
    NCRRepository,
    ITPRepository,
)
from db.models import (
    PunchItem,
    NCRRecord,
    ITPItem,
    TestPackage,
    LineListItem,
    Weld,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Engineering Definitions
# ──────────────────────────────────────────────

class PunchCategory(str, Enum):
    """دسته‌بندی استاندارد پانچ‌لیست بر مبنای اثرگذاری بر مسیر بحرانی"""
    CAT_A = "A"  # Implementation note.
    CAT_B = "B"  # Implementation note.
    CAT_C = "C"  # Implementation note.


class PunchStatus(str, Enum):
    """چرخه حیات ۴ مرحله‌ای رفع پانچ"""
    OPEN = "OPEN"                              # Implementation note.
    RECTIFIED = "RECTIFIED"                    # Implementation note.
    QC_CLEARED = "QC_CLEARED"                  # Implementation note.
    CLIENT_ACCEPTED = "CLIENT_ACCEPTED"        # Implementation note.
    REJECTED = "REJECTED"                      # Implementation note.
    CANCELLED = "CANCELLED"                    # Implementation note.


class NCRStatus(str, Enum):
    """وضعیت‌های فرآیندی گزارش عدم انطباق"""
    ISSUED = "ISSUED"                          # Implementation note.
    UNDER_REVIEW = "UNDER_REVIEW"              # Implementation note.
    DISPOSITION_PROPOSED = "DISPOSITION_PROPOSED"  # Implementation note.
    DISPOSITION_APPROVED = "DISPOSITION_APPROVED"  # Implementation note.
    RECTIFIED = "RECTIFIED"                    # Implementation note.
    CLOSED = "CLOSED"                          # Implementation note.
    CANCELLED = "CANCELLED"                    # Implementation note.


class NCRDisposition(str, Enum):
    """نوع تعیین تکلیف مهندسی عدم انطباق"""
    REWORK = "REWORK"                          # Implementation note.
    REPAIR = "REPAIR"                          # Implementation note.
    USE_AS_IS = "USE_AS_IS"                    # Implementation note.
    SCRAP = "SCRAP"                            # Implementation note.
    RETURN_TO_VENDOR = "RTV"                   # Implementation note.


class NCRSeverity(str, Enum):
    """شدت عدم انطباق"""
    CRITICAL = "CRITICAL"                      # Implementation note.
    MAJOR = "MAJOR"                            # Implementation note.
    MINOR = "MINOR"                            # Implementation note.


class ITPPointType(str, Enum):
    """انواع نقاط مداخله در برنامه بازرسی و تست (ITP)"""
    HOLD = "H"         # Implementation note.
    WITNESS = "W"      # Implementation note.
    SURVEILLANCE = "S" # Implementation note.
    REVIEW = "R"       # Implementation note.


class RFIStatus(str, Enum):
    """وضعیت درخواست بازرسی (Request For Inspection)"""
    SUBMITTED = "SUBMITTED"
    INSPECTED_PASS = "PASS"
    INSPECTED_FAIL = "FAIL"
    WAIVED = "WAIVED"                          # Implementation note.


# ──────────────────────────────────────────────
#  Custom QA/QC Exceptions
# ──────────────────────────────────────────────

class QAQCGatekeeperError(AppError):
    """خطای مسدود بودن پیش‌نیازهای کیفی هیدروتست یا تکمیل مکانیکی"""
    pass


class PunchLifecycleError(AppError):
    """خطای نقض توالی مراحل چرخه رفع پانچ"""
    pass


class NCRWorkflowError(AppError):
    """خطای عدم احراز شرایط تغییر وضعیت عدم انطباق"""
    pass


# ──────────────────────────────────────────────
#  QA/QC Service Implementation
# ──────────────────────────────────────────────

class QAQCService:
    """
    سرویس مرکزی مدیریت فرآیندهای تضمین و کنترل کیفیت (QA/QC Management Engine)
    """

    def __init__(self, session: Session):
        self.session = session
        self.punch_repo = PunchRepository(session)
        self.ncr_repo = NCRRepository(session)
        self.itp_repo = ITPRepository(session)

    # ══════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════

    def raise_punch(
        self,
        project_id: int,
        punch_number: str,
        category: Union[PunchCategory, str],
        description: str,
        raised_by: str,
        *,
        test_package_id: Optional[int] = None,
        line_number: Optional[str] = None,
        drawing_number: Optional[str] = None,
        subsystem: Optional[str] = None,
        assigned_contractor: Optional[str] = None,
        target_closure_date: Optional[date] = None,
        attachment_file_path: Optional[str] = None,
    ) -> PunchItem:
        """ثبت رسمی آیتم پانچ‌لیست با اعتبارسنجی مقادیر دسته‌بندی (A/B/C)"""
        cat_val = category.value if isinstance(category, PunchCategory) else str(category).strip().upper()
        if cat_val not in (PunchCategory.CAT_A.value, PunchCategory.CAT_B.value, PunchCategory.CAT_C.value):
            raise AppError(f"Invalid punch category '{category}'. Must be 'A', 'B', or 'C'.")

        punch = self.punch_repo.add_punch(
            project_id=project_id,
            punch_number=punch_number.strip().upper(),
            category=cat_val,
            description=description.strip(),
            raised_by=raised_by.strip(),
            test_package_id=test_package_id,
            line_number=line_number.strip().upper() if line_number else None,
            drawing_number=drawing_number.strip().upper() if drawing_number else None,
            assigned_contractor=assigned_contractor.strip() if assigned_contractor else None,
            target_closure_date=target_closure_date,
        )

        if attachment_file_path and hasattr(punch, "attachment_path"):
            punch.attachment_path = attachment_file_path
            self.session.commit()

        logger.info(f"Punch #{punch.punch_number} (Cat {cat_val}) raised by {raised_by}.")
        return punch

    def rectify_punch(
        self,
        punch_id: int,
        rectified_by_contractor: str,
        contractor_remarks: str = "",
        rectification_photo_path: Optional[str] = None,
    ) -> PunchItem:
        """اعلام رفع عیب توسط پیمانکار اجرایی و آماده‌سازی برای ممیزی بازرس QC"""
        punch = self.punch_repo.get_by_id(punch_id)
        if not punch:
            raise AppError(f"Punch item #{punch_id} not found.")

        if punch.status in (PunchStatus.QC_CLEARED.value, PunchStatus.CLIENT_ACCEPTED.value):
            raise PunchLifecycleError(f"Punch #{punch.punch_number} is already cleared.")

        punch = self.punch_repo.mark_rectified(
            punch_id=punch_id,
            rectified_by=rectified_by_contractor.strip(),
            contractor_remarks=contractor_remarks.strip(),
        )

        if rectification_photo_path and hasattr(punch, "rectification_photo_path"):
            punch.rectification_photo_path = rectification_photo_path
            self.session.commit()

        logger.info(f"Punch #{punch.punch_number} marked as RECTIFIED by {rectified_by_contractor}.")
        return punch

    def clear_punch(
        self,
        punch_id: int,
        cleared_by_qc: str,
        *,
        client_witness: Optional[str] = None,
        qc_comments: str = "",
        reject_rectification: bool = False,
        rejection_reason: str = "",
    ) -> PunchItem:
        """تأیید نهایی ترخیص پانچ توسط بازرس QC و ناظر کارفرما، یا رد اصلاحیه"""
        punch = self.punch_repo.get_by_id(punch_id)
        if not punch:
            raise AppError(f"Punch item #{punch_id} not found.")

        if reject_rectification:
            punch.status = PunchStatus.REJECTED.value
            if hasattr(punch, "rejection_comments"):
                punch.rejection_comments = rejection_reason.strip()
            self.session.commit()
            logger.warning(f"Punch #{punch.punch_number} rectification REJECTED by {cleared_by_qc}. Reason: {rejection_reason}")
            return punch

        punch = self.punch_repo.clear_item(
            punch_id=punch_id,
            cleared_by=cleared_by_qc.strip(),
            client_witness=client_witness.strip() if client_witness else None,
            qc_comments=qc_comments.strip(),
        )
        logger.info(f"Punch #{punch.punch_number} CLEARED by QC {cleared_by_qc} (Client: {client_witness}).")
        return punch

    def bulk_clear_punches(
        self,
        project_id: int,
        punch_ids: List[int],
        cleared_by_qc: str,
        allow_cat_a: bool = False,
    ) -> Dict[str, Any]:
        """ترخیص دسته‌ای پانچ‌ها (صرفاً برای دسته‌های B و C، مگر با تایید صریح Cat-A)"""
        query = self.session.query(PunchItem).filter(
            PunchItem.project_id == project_id,
            PunchItem.id.in_(punch_ids),
        )

        if not allow_cat_a:
            query = query.filter(PunchItem.category != PunchCategory.CAT_A.value)

        cleared_count = query.update(
            {
                "status": PunchStatus.QC_CLEARED.value,
                "cleared_by": cleared_by_qc.strip(),
                "cleared_date": datetime.utcnow(),
            },
            synchronize_session="fetch",
        )
        self.session.commit()

        logger.info(f"Bulk cleared {cleared_count} punches by {cleared_by_qc}.")
        return {
            "requested_count": len(punch_ids),
            "cleared_count": cleared_count,
            "cat_a_skipped": len(punch_ids) - cleared_count if not allow_cat_a else 0,
        }

    # ══════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════

    def issue_ncr(
        self,
        project_id: int,
        ncr_number: str,
        title: str,
        description: str,
        issued_by: str,
        issued_to_contractor: str,
        spec_requirement: str,
        actual_nonconformance: str,
        severity: Union[NCRSeverity, str] = NCRSeverity.MAJOR,
        discipline: str = "PIPING",
        root_cause_analysis: Optional[str] = None,
        line_number: Optional[str] = None,
        test_package_id: Optional[int] = None,
    ) -> NCRRecord:
        """صدور رسمی گزارش عدم انطباق با جلوگیری از تکرار شماره NCR در سطح پروژه"""
        ncr_num_clean = ncr_number.strip().upper()
        existing = self.session.query(NCRRecord).filter(
            NCRRecord.project_id == project_id,
            NCRRecord.ncr_number == ncr_num_clean,
        ).first()

        if existing:
            raise AppError(f"NCR '{ncr_num_clean}' is already registered in Project #{project_id}.")

        sev_val = severity.value if isinstance(severity, NCRSeverity) else str(severity).strip().upper()

        ncr = self.ncr_repo.issue_ncr(
            project_id=project_id,
            ncr_number=ncr_num_clean,
            title=title.strip(),
            description=description.strip(),
            issued_by=issued_by.strip(),
            issued_to_contractor=issued_to_contractor.strip(),
            spec_requirement=spec_requirement.strip(),
            actual_condition=actual_nonconformance.strip(),
            severity=sev_val,
            discipline=discipline.strip().upper(),
        )

        if line_number and hasattr(ncr, "line_number"):
            ncr.line_number = line_number.strip().upper()
        if test_package_id and hasattr(ncr, "test_package_id"):
            ncr.test_package_id = test_package_id
        if root_cause_analysis and hasattr(ncr, "root_cause"):
            ncr.root_cause = root_cause_analysis.strip()

        self.session.commit()
        logger.warning(f"NCR #{ncr.ncr_number} ({sev_val}) ISSUED to {issued_to_contractor} by {issued_by}.")
        return ncr

    def propose_ncr_disposition(
        self,
        ncr_id: int,
        disposition: Union[NCRDisposition, str],
        action_details: str,
        proposed_by_engineer: str,
        root_cause_analysis: str,
        target_rectification_date: Optional[date] = None,
        technical_concession_number: Optional[str] = None,
    ) -> NCRRecord:
        """ثبت راهکار مهندسی (Disposition) و تحلیل علت ریشه‌ای عیب (RCA)"""
        ncr = self.ncr_repo.get_by_id(ncr_id)
        if not ncr:
            raise AppError(f"NCR record #{ncr_id} not found.")

        disp_val = disposition.value if isinstance(disposition, NCRDisposition) else str(disposition).strip().upper()

        ncr = self.ncr_repo.propose_disposition(
            ncr_id=ncr_id,
            disposition_type=disp_val,
            proposed_action_details=action_details.strip(),
            root_cause_analysis=root_cause_analysis.strip(),
            proposed_by=proposed_by_engineer.strip(),
            target_rectification_date=target_rectification_date,
        )

        if technical_concession_number and hasattr(ncr, "concession_number"):
            ncr.concession_number = technical_concession_number.strip().upper()
            self.session.commit()

        logger.info(f"NCR #{ncr.ncr_number} disposition proposed as '{disp_val}' by {proposed_by_engineer}.")
        return ncr

    def approve_ncr_disposition(
        self,
        ncr_id: int,
        approved_by_lead_eng: str,
        client_approval_reference: Optional[str] = None,
        approval_remarks: str = "",
    ) -> NCRRecord:
        """تأیید راهکار مهندسی توسط دفتر فنی و دستگاه نظارت/کارفرما"""
        ncr = self.ncr_repo.get_by_id(ncr_id)
        if not ncr:
            raise AppError(f"NCR record #{ncr_id} not found.")

        if ncr.status != NCRStatus.DISPOSITION_PROPOSED.value:
            raise NCRWorkflowError(f"NCR #{ncr.ncr_number} is in '{ncr.status}' status. Disposition must be proposed first.")

        ncr = self.ncr_repo.approve_disposition(
            ncr_id=ncr_id,
            approved_by_engineering=approved_by_lead_eng.strip(),
            client_approval_ref=client_approval_reference.strip() if client_approval_reference else None,
            comments=approval_remarks.strip(),
        )
        logger.info(f"NCR #{ncr.ncr_number} disposition APPROVED by {approved_by_lead_eng}.")
        return ncr

    def close_ncr(
        self,
        ncr_id: int,
        closed_by_qa_mgr: str,
        verification_report_no: str,
        corrective_action_verified: bool = True,
        preventive_action_verified: bool = True,
        closure_remarks: str = "",
    ) -> NCRRecord:
        """بستن قطعی NCR پس از راستی‌آزمایی اقدامات اصلاحی و پیشگیرانه (CAPA)"""
        ncr = self.ncr_repo.get_by_id(ncr_id)
        if not ncr:
            raise AppError(f"NCR record #{ncr_id} not found.")

        if not (corrective_action_verified and preventive_action_verified):
            raise NCRWorkflowError(f"Cannot close NCR #{ncr.ncr_number}: CAPA verification criteria not met.")

        ncr = self.ncr_repo.close_record(
            ncr_id=ncr_id,
            closed_by=closed_by_qa_mgr.strip(),
            corrective_preventive_action_verified=True,
            verification_report_ref=verification_report_no.strip(),
            closure_remarks=closure_remarks.strip(),
        )
        logger.info(f"NCR #{ncr.ncr_number} officially CLOSED by QA Manager: {closed_by_qa_mgr}.")
        return ncr

    # ══════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════

    def add_itp_activity(
        self,
        project_id: int,
        itp_number: str,
        activity_code: str,
        description: str,
        reference_standard: str,
        contractor_point: Union[ITPPointType, str] = ITPPointType.HOLD,
        client_point: Union[ITPPointType, str] = ITPPointType.WITNESS,
        required_form_code: Optional[str] = None,
        sequence: int = 1,
    ) -> ITPItem:
        """ثبت بند جدید در ماتریس ITP با تعریف دقیق نقاط توقف و بازرسی طرفین"""
        c_pt = contractor_point.value if isinstance(contractor_point, ITPPointType) else str(contractor_point).strip().upper()
        cl_pt = client_point.value if isinstance(client_point, ITPPointType) else str(client_point).strip().upper()

        item = self.itp_repo.add_itp_item(
            project_id=project_id,
            itp_number=itp_number.strip().upper(),
            activity_description=description.strip(),
            reference_spec_code=reference_standard.strip(),
            contractor_point=c_pt,
            client_point=cl_pt,
            required_record_form=required_form_code.strip() if required_form_code else None,
            sequence=sequence,
        )

        if activity_code and hasattr(item, "activity_code"):
            item.activity_code = activity_code.strip().upper()
            self.session.commit()

        logger.info(f"ITP Activity [{activity_code}] registered under ITP '{itp_number}'.")
        return item

    def sign_off_rfi_inspection(
        self,
        itp_item_id: int,
        rfi_number: str,
        inspector_qc: str,
        inspector_client: Optional[str] = None,
        is_passed: bool = True,
        is_waived_by_client: bool = False,
        comments: str = "",
    ) -> ITPItem:
        """ثبت صورتجلسه بازرسی و امضای نقطه توقف (Hold/Witness Point) بر اساس شماره RFI"""
        item = self.itp_repo.record_inspection_signoff(
            itp_item_id=itp_item_id,
            rfi_number=rfi_number.strip().upper(),
            inspector_qc=inspector_qc.strip(),
            inspector_client=inspector_client.strip() if inspector_client else None,
            is_passed=is_passed,
            is_waived_by_client=is_waived_by_client,
            comments=comments.strip(),
        )

        if not item:
            raise AppError(f"ITP Item #{itp_item_id} not found.")

        logger.info(f"RFI #{rfi_number} signed off for ITP Item #{itp_item_id} (Passed: {is_passed}, Waived: {is_waived_by_client}).")
        return item

    # ══════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════

    def can_proceed_to_hydro(
        self,
        project_id: int,
        test_package_id: int,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        ارزیابی سخت‌گیرانه و چندبعدی آمادگی پکیج جهت اجرای آزمون هیدرواستاتیک:
        ۱. صفر بودن مطلق پانچ‌های باز دسته A در پکیج تست
        ۲. بررسی عدم وجود NCR باز با شدت بحرانی (Critical/Major) روی خطوط متصل به پکیج
        ۳. ترخیص ۱۰۰٪ سرجوش‌های داخل پکیج از آزمون‌های غیرمخرب (NDT Cleared)
        """
        blockers: List[str] = []

        # Implementation note.
        punch_summary = self.punch_repo.get_summary(project_id, test_package_id)
        matrix = punch_summary.get("matrix", {})
        cat_a_open = matrix.get("A", {}).get("OPEN", 0) + matrix.get("A", {}).get("RECTIFIED", 0)

        if cat_a_open > 0:
            blockers.append(f"{cat_a_open} open or unverified Category-A punch item(s) exist on this test package.")

        # Implementation note.
        tp = self.session.get(TestPackage, test_package_id)
        if not tp:
            raise AppError(f"TestPackage #{test_package_id} not found.")

        lines_raw = (getattr(tp, "line_numbers", "") or "").replace(";", ",")
        package_lines = [l.strip().upper() for l in lines_raw.split(",") if l.strip()]

        # Implementation note.
        open_ncrs_query = self.session.query(NCRRecord).filter(
            NCRRecord.project_id == project_id,
            NCRRecord.status.notin_([NCRStatus.CLOSED.value, NCRStatus.CANCELLED.value]),
        )

        if package_lines:
            open_ncrs_query = open_ncrs_query.filter(
                or_(
                    NCRRecord.line_number.in_(package_lines),
                    getattr(NCRRecord, "test_package_id", None) == test_package_id,
                )
            )

        blocking_ncrs = open_ncrs_query.all()
        if blocking_ncrs:
            for ncr in blocking_ncrs:
                blockers.append(f"Blocking NCR #{ncr.ncr_number} ({ncr.severity}) is still {ncr.status} on line '{ncr.line_number or 'Package'}'.")

        # Implementation note.
        welds_in_tp = self.session.query(Weld).filter(
            Weld.project_id == project_id,
            or_(
                Weld.test_package_id == test_package_id,
                Weld.line_number.in_(package_lines) if package_lines else False,
            ),
        ).all()

        total_welds = len(welds_in_tp)
        uncleared_welds = [
            w.weld_number for w in welds_in_tp
            if getattr(w, "ndt_status", "") != "ACCEPTED" and w.status not in ["NDT_CLEARED", "COMPLETED", "VT_ACCEPTED"]
        ]

        if uncleared_welds:
            blockers.append(f"{len(uncleared_welds)}/{total_welds} welds lack complete NDT clearance: ({', '.join(uncleared_welds[:5])}{'...' if len(uncleared_welds) > 5 else ''}).")

        can_proceed = len(blockers) == 0

        details = {
            "test_package_id": test_package_id,
            "package_number": tp.package_number,
            "is_hydro_permitted": can_proceed,
            "blocking_reasons_count": len(blockers),
            "punch_metrics": {
                "open_cat_a": cat_a_open,
                "open_cat_b": matrix.get("B", {}).get("OPEN", 0),
            },
            "ncr_metrics": {
                "active_blocking_ncrs": len(blocking_ncrs),
                "ncr_numbers": [n.ncr_number for n in blocking_ncrs],
            },
            "ndt_metrics": {
                "total_welds": total_welds,
                "uncleared_welds_count": len(uncleared_welds),
            },
        }

        return can_proceed, blockers, details

    # ══════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════

    def get_overall_qaqc_cockpit(self, project_id: int) -> Dict[str, Any]:
        """
        محاسبه داشبورد ماتریسی کیفیت پروژه با کوئری‌های تجمعی مستقیم دیتابیس
        """
        # Implementation note.
        punch_stats = self.session.query(
            func.count(PunchItem.id).label("total"),
            func.sum(case((and_(PunchItem.category == "A", PunchItem.status.notin_(["QC_CLEARED", "CLIENT_ACCEPTED", "CLOSED"])), 1), else_=0)).label("open_a"),
            func.sum(case((and_(PunchItem.category == "B", PunchItem.status.notin_(["QC_CLEARED", "CLIENT_ACCEPTED", "CLOSED"])), 1), else_=0)).label("open_b"),
            func.sum(case((and_(PunchItem.category == "C", PunchItem.status.notin_(["QC_CLEARED", "CLIENT_ACCEPTED", "CLOSED"])), 1), else_=0)).label("open_c"),
            func.sum(case((PunchItem.status.in_(["QC_CLEARED", "CLIENT_ACCEPTED", "CLOSED"]), 1), else_=0)).label("cleared"),
        ).filter(PunchItem.project_id == project_id).first()

        # Implementation note.
        ncr_stats = self.session.query(
            func.count(NCRRecord.id).label("total"),
            func.sum(case((NCRRecord.status == NCRStatus.CLOSED.value, 1), else_=0)).label("closed"),
            func.sum(case((and_(NCRRecord.status != NCRStatus.CLOSED.value, NCRRecord.severity == NCRSeverity.CRITICAL.value), 1), else_=0)).label("open_critical"),
            func.sum(case((and_(NCRRecord.status != NCRStatus.CLOSED.value, NCRRecord.severity == NCRSeverity.MAJOR.value), 1), else_=0)).label("open_major"),
            func.sum(case((and_(NCRRecord.status != NCRStatus.CLOSED.value, NCRRecord.severity == NCRSeverity.MINOR.value), 1), else_=0)).label("open_minor"),
        ).filter(NCRRecord.project_id == project_id).first()

        # Implementation note.
        ncr_aging = self.ncr_repo.get_ncr_aging_report(project_id)
        critical_aging_count = sum(1 for item in ncr_aging if item.get("is_critical_delay", False))

        total_punches = punch_stats.total or 0
        cleared_punches = punch_stats.cleared or 0
        total_ncrs = ncr_stats.total or 0
        closed_ncrs = ncr_stats.closed or 0

        punch_clearance_pct = round((cleared_punches / total_punches * 100), 2) if total_punches > 0 else 100.0
        ncr_closure_pct = round((closed_ncrs / total_ncrs * 100), 2) if total_ncrs > 0 else 100.0

        return {
            "project_id": project_id,
            "timestamp": datetime.utcnow().isoformat(),
            "punch_list": {
                "total_punches": total_punches,
                "cleared_punches": cleared_punches,
                "open_category_a_blockers": punch_stats.open_a or 0,
                "open_category_b": punch_stats.open_b or 0,
                "open_category_c": punch_stats.open_c or 0,
                "clearance_percentage": punch_clearance_pct,
            },
            "non_conformance_reports": {
                "total_ncrs": total_ncrs,
                "closed_ncrs": closed_ncrs,
                "open_critical_ncrs": ncr_stats.open_critical or 0,
                "open_major_ncrs": ncr_stats.open_major or 0,
                "open_minor_ncrs": ncr_stats.open_minor or 0,
                "closure_percentage": ncr_closure_pct,
                "ncrs_overdue_14_days": critical_aging_count,
            },
            "quality_health_status": "EXCELLENT" if (punch_stats.open_a == 0 and ncr_stats.open_critical == 0 and critical_aging_count == 0) else "ACTION_REQUIRED",
        }