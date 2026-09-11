# -*- coding: utf-8 -*-
"""
services/ndt_service.py – PipeAgent
سرویس جامع مدیریت آزمون‌های غیرمخرب (Non-Destructive Testing - NDT)
منطبق با استانداردهای ASME B31.3، ASME Sec V و AWS D1.1
شامل: همگام‌سازی وضعیت سرجوش، تخصیص آزمون‌های جریمه (Penalty/Tracer Welds)،
ردیابی جوش‌های تعمیری (R1/R2)، محاسبه پوشش واقعی NDT و تحلیل پارتو عیوب.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc, case
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from config import NDT_METHODS
from db.manager import DatabaseManager
from db.models import NDTRecord, Weld, LineListItem
from services.license import increment_usage

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Engineering Standards
# ──────────────────────────────────────────────

class NDTMethod(str, Enum):
    """روش‌های استاندارد بازرسی غیرمخرب"""
    RT = "RT"          # Implementation note.
    UT = "UT"          # Implementation note.
    PAUT = "PAUT"      # Implementation note.
    PT = "PT"          # Implementation note.
    MT = "MT"          # Implementation note.
    VT = "VT"          # Implementation note.
    PMI = "PMI"        # Implementation note.
    HT = "HT"          # Implementation note.
    FT = "FT"          # Implementation note.


class NDTVerdict(str, Enum):
    """نتیجه ارزیابی کیفی طبق معیارهای پذیرش ASME B31.3"""
    ACCEPTED = "Pass"                  # Implementation note.
    REJECTED = "Fail"                  # Implementation note.
    PENDING = "Pending"                # Implementation note.
    RE_TEST = "Re-Test"                # Implementation note.
    NOT_REQUIRED = "NR"                # Implementation note.


class WeldDefectType(str, Enum):
    """عیوب استاندارد جوشکاری طبق ASME Sec IX / B31.3"""
    CRACK = "CRACK"                    # Implementation note.
    LACK_OF_FUSION = "LOF"             # Implementation note.
    LACK_OF_PENETRATION = "LOP"        # Implementation note.
    POROSITY = "POROSITY"              # Implementation note.
    SLAG_INCLUSION = "SLAG"            # Implementation note.
    UNDERCUT = "UNDERCUT"              # Implementation note.
    ROOT_CONCAVITY = "CONCAVITY"       # Implementation note.
    BURN_THROUGH = "BURN_THROUGH"      # Implementation note.
    TUNGSTEN_INCLUSION = "TUNGSTEN"    # Implementation note.
    EXCESS_PENETRATION = "EXCESS_PEN"  # Implementation note.


# ──────────────────────────────────────────────
#  Custom Domain Exceptions
# ──────────────────────────────────────────────

class NDTPreconditionError(Exception):
    """خطای عدم احراز شرایط لازم برای ثبت آزمون NDT"""
    pass


class PenaltyAllocationError(Exception):
    """خطای تخصیص سرجوش‌های جریمه"""
    pass


# ──────────────────────────────────────────────
#  NDT Service Implementation
# ──────────────────────────────────────────────

class NDTService:
    """
    سرویس مرکزی مدیریت تست‌های غیرمخرب، گردش‌کار کنترل کیفیت و آزمون‌های پنالتی
    """

    VALID_RESULTS = {r.value for r in NDTVerdict}

    def __init__(self, db: DatabaseManager):
        self.db = db

    # Implementation note.

    def record_ndt_result(
        self,
        weld_pk: int,
        ndt_method: Union[NDTMethod, str],
        verdict: Union[NDTVerdict, str],
        *,
        report_number: str,
        inspector_id: str,
        inspection_date: Optional[date] = None,
        defect_type: Optional[Union[WeldDefectType, str]] = None,
        defect_location_clock: Optional[str] = None,  # Implementation note.
        defect_length_mm: Optional[float] = None,
        film_density: Optional[float] = None,
        sensitivity_wire: Optional[str] = None,
        is_penalty: bool = False,
        original_rejected_weld_id: Optional[int] = None,
        repair_cycle_no: int = 0,  # Implementation note.
        remarks: str = "",
    ) -> Dict[str, Any]:
        """
        ثبت قطعی نتیجه آزمون NDT، همگام‌سازی خودکار وضعیت سرجوش در جدول Weld،
        ثبت عیوب و آماده‌سازی برای تخصیص پنالتی در صورت ریجکت شدن.
        """
        if not increment_usage(self.db):
            raise PermissionError("License limit reached. Cannot register NDT record.")

        method_str = ndt_method.value if isinstance(ndt_method, NDTMethod) else str(ndt_method).strip().upper()
        verdict_str = verdict.value if isinstance(verdict, NDTVerdict) else str(verdict).strip()
        defect_str = defect_type.value if isinstance(defect_type, WeldDefectType) else (str(defect_type).strip().upper() if defect_type else None)

        if verdict_str not in self.VALID_RESULTS:
            verdict_str = NDTVerdict.PENDING.value

        with self.db.session_scope() as session:
            # Implementation note.
            weld = session.get(Weld, weld_pk)
            if not weld:
                raise NDTPreconditionError(f"Weld joint #{weld_pk} not found in database.")

            # Implementation note.
            existing_record = (
                session.query(NDTRecord)
                .filter(
                    NDTRecord.weld_id == weld_pk,
                    NDTRecord.ndt_method == method_str,
                )
                .first()
            )

            if existing_record:
                existing_record.inspection_date = inspection_date or date.today()
                existing_record.inspector_id = inspector_id.strip()
                existing_record.result = verdict_str
                existing_record.report_number = report_number.strip()
                existing_record.indication = defect_str
                if film_density is not None:
                    existing_record.film_density = film_density
                existing_record.is_penalty = is_penalty
                if original_rejected_weld_id:
                    existing_record.penalty_source_weld_id = original_rejected_weld_id
                existing_record.remarks = remarks.strip()
                record_obj = existing_record
            else:
                record_obj = NDTRecord(
                    weld_id=weld_pk,
                    ndt_method=method_str,
                    inspection_date=inspection_date or date.today(),
                    inspector_id=inspector_id.strip(),
                    result=verdict_str,
                    report_number=report_number.strip(),
                    indication=defect_str,
                    film_density=film_density,
                    is_penalty=is_penalty,
                    penalty_source_weld_id=original_rejected_weld_id,
                    remarks=remarks.strip(),
                )
                session.add(record_obj)

            # Implementation note.
            if verdict_str == NDTVerdict.ACCEPTED.value:
                # Implementation note.
                weld.ndt_status = "ACCEPTED"
                weld.status = "NDT_CLEARED"
                logger.info(f"Weld #{weld_pk} [{method_str}] PASSED inspection (Report: {report_number}).")

            elif verdict_str == NDTVerdict.REJECTED.value:
                weld.ndt_status = "REJECTED"
                weld.status = "REPAIR_REQUIRED"
                weld.repair_count = (getattr(weld, "repair_count", 0) or 0) + 1
                weld.defect_description = f"{defect_str or 'Defect'} at {defect_location_clock or 'N/A'}"
                logger.warning(
                    f"Weld #{weld_pk} [{method_str}] REJECTED! Reason: {defect_str}. "
                    f"Weld status transitioned to REPAIR_REQUIRED (Repair Count: {weld.repair_count})."
                )

            elif verdict_str == NDTVerdict.PENDING.value:
                weld.ndt_status = "PENDING"

            session.flush()
            record_id = record_obj.id

        return self.get_record_by_id(record_id)

    # Implementation note.

    def assign_penalty_tracer_welds(
        self,
        project_id: int,
        rejected_ndt_id: int,
        assigned_by: str,
        penalty_ratio: int = 2,  # Implementation note.
    ) -> List[Dict[str, Any]]:
        """
        تخصیص هوشمند سرجوش‌های جریمه (Tracer Welds):
        یافتن ۲ سرجوش تست‌نشده دیگر که توسط همان جوشکار، با همان فرآیند و روی همان خط/لات اجرا شده‌اند.
        """
        with self.db.session_scope() as session:
            orig_ndt = session.get(NDTRecord, rejected_ndt_id)
            if not orig_ndt or orig_ndt.result != NDTVerdict.REJECTED.value:
                raise PenaltyAllocationError(f"NDT Record #{rejected_ndt_id} must exist and have 'Fail' verdict.")

            orig_weld = session.get(Weld, orig_ndt.weld_id)
            if not orig_weld:
                raise PenaltyAllocationError("Original rejected weld record not found.")

            target_welder = getattr(orig_weld, "root_welder_id", orig_weld.welder_id)
            if not target_welder:
                raise PenaltyAllocationError(f"No welder stencil assigned to Weld #{orig_weld.id}.")

            # Implementation note.
            candidate_welds = (
                session.query(Weld)
                .filter(
                    Weld.project_id == project_id,
                    or_(
                        Weld.root_welder_id == target_welder,
                        Weld.welder_id == target_welder,
                    ),
                    Weld.id != orig_weld.id,
                    Weld.status.in_(["WELDED", "WELDED_VT_PENDING", "VT_ACCEPTED"]),
                )
                .order_by(Weld.welding_date.desc() if hasattr(Weld, "welding_date") else Weld.id.desc())
                .limit(penalty_ratio)
                .all()
            )

            created_penalties = []
            for cw in candidate_welds:
                penalty_record = NDTRecord(
                    weld_id=cw.id,
                    ndt_method=orig_ndt.ndt_method,
                    result=NDTVerdict.PENDING.value,
                    is_penalty=True,
                    penalty_source_weld_id=orig_weld.id,
                    remarks=f"Penalty assigned by {assigned_by} due to rejected Weld #{orig_weld.id} (Welder: {target_welder})",
                )
                session.add(penalty_record)
                cw.status = "NDT_REQUESTED"
                session.flush()

                created_penalties.append(penalty_record.id)

            logger.warning(
                f"Assigned {len(created_penalties)} penalty tracer welds for Welder '{target_welder}' "
                f"due to failed NDT #{rejected_ndt_id}."
            )

        return [self.get_record_by_id(pid) for pid in created_penalties]

    # Implementation note.

    def evaluate_line_ndt_coverage(self, project_id: int, line_number: str) -> Dict[str, Any]:
        """B31.3 examination extent vs line-list RT/UT/PT/MT percents."""
        from services.code_compliance import line_coverage

        with self.db.session_scope() as session:
            return line_coverage(session, project_id, line_number)

    # Implementation note.

    def get_project_ndt_summary(self, project_id: int) -> Dict[str, Any]:
        """
        محاسبه ماتریس آماری تست‌های غیرمخرب با اجرای کوئری‌های تجمعی مستقیم در دیتابیس
        (حذف کامل گلوگاه حافظه RAM).
        """
        with self.db.session_scope() as session:
            stats = session.query(
                func.count(NDTRecord.id).label("total_records"),
                func.sum(case((NDTRecord.result.in_(["Pass", "Accepted"]), 1), else_=0)).label("pass_count"),
                func.sum(case((NDTRecord.result.in_(["Fail", "Rejected"]), 1), else_=0)).label("fail_count"),
                func.sum(case((NDTRecord.result == NDTVerdict.PENDING.value, 1), else_=0)).label("pending_count"),
                func.sum(case((NDTRecord.is_penalty == True, 1), else_=0)).label("penalty_count"),
            ).join(Weld, NDTRecord.weld_id == Weld.id).filter(Weld.project_id == project_id).first()

            method_breakdown = (
                session.query(
                    NDTRecord.ndt_method,
                    func.count(NDTRecord.id).label("total"),
                    func.sum(case((NDTRecord.result.in_(["Pass", "Accepted"]), 1), else_=0)).label("passed"),
                    func.sum(case((NDTRecord.result.in_(["Fail", "Rejected"]), 1), else_=0)).label("failed"),
                )
                .join(Weld, NDTRecord.weld_id == Weld.id)
                .filter(Weld.project_id == project_id)
                .group_by(NDTRecord.ndt_method)
                .all()
            )

            defect_stats = (
                session.query(
                    NDTRecord.indication,
                    func.count(NDTRecord.id).label("count"),
                )
                .join(Weld, NDTRecord.weld_id == Weld.id)
                .filter(
                    Weld.project_id == project_id,
                    NDTRecord.indication.isnot(None),
                    NDTRecord.indication != "",
                )
                .group_by(NDTRecord.indication)
                .order_by(desc("count"))
                .limit(6)
                .all()
            )

            total = stats.total_records or 0
            passed = stats.pass_count or 0
            failed = stats.fail_count or 0

            pass_rate = round((passed / (passed + failed) * 100), 2) if (passed + failed) > 0 else 100.0

            return {
                "project_id": project_id,
                "timestamp": datetime.utcnow().isoformat(),
                "overview": {
                    "total_inspections": total,
                    "passed_count": passed,
                    "failed_count": failed,
                    "pending_interpretation": stats.pending_count or 0,
                    "penalty_tracer_inspections": stats.penalty_count or 0,
                    "overall_pass_rate_pct": pass_rate,
                },
                "breakdown_by_method": {
                    row.ndt_method: {
                        "total": row.total,
                        "passed": row.passed or 0,
                        "failed": row.failed or 0,
                        "fail_rate_pct": round(((row.failed or 0) / row.total * 100), 2) if row.total > 0 else 0.0,
                    }
                    for row in method_breakdown
                },
                "top_recurring_defects": {row.indication: row.count for row in defect_stats},
            }

    # Implementation note.

    def is_weld_ndt_complete(
        self,
        weld_pk: int,
        required_methods: Optional[List[str]] = None,
    ) -> bool:
        """
        بررسی صلاحیت ترخیص سرجوش جهت گنجانده شدن در پکیج تست هیدرواستاتیک:
        - عدم وجود تست مردود (Fail) حل‌نشده
        - پاس شدن کلیه متدهای اجباری تعیین‌شده (مثلاً VT + RT)
        """
        with self.db.session_scope() as session:
            records = (
                session.query(NDTRecord)
                .filter(NDTRecord.weld_id_fk == weld_pk)
                .all()
            )

            if not records:
                return False

            # Implementation note.
            has_unresolved_fail = any(r.result == NDTVerdict.REJECTED.value for r in records)
            if has_unresolved_fail:
                # Implementation note.
                latest_records_by_method: Dict[str, NDTRecord] = {}
                for r in sorted(records, key=lambda x: getattr(x, "repair_cycle", 0)):
                    latest_records_by_method[r.ndt_method] = r
                
                if any(lr.result == NDTVerdict.REJECTED.value for lr in latest_records_by_method.values()):
                    return False

            passed_methods = {
                r.ndt_method for r in records if r.result in (NDTVerdict.ACCEPTED.value, NDTVerdict.NOT_REQUIRED.value)
            }

            if required_methods:
                return all(m.upper().strip() in passed_methods for m in required_methods)

            # Implementation note.
            return NDTMethod.VT.value in passed_methods

    # Implementation note.

    def get_record_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """بازیابی دیکشنری مستقل و ایمن رکورد NDT جهت جلوگیری از خطای DetachedInstanceError"""
        with self.db.session_scope() as session:
            rec = session.get(NDTRecord, record_id)
            if not rec:
                return None
            return {
                "id": rec.id,
                "project_id": rec.project_id,
                "weld_id_fk": rec.weld_id_fk,
                "ndt_method": rec.ndt_method,
                "inspection_date": rec.inspection_date.isoformat() if rec.inspection_date else None,
                "inspector_id": rec.inspector_id,
                "result": rec.result,
                "report_number": rec.report_number,
                "defect_type": getattr(rec, "defect_type", None),
                "defect_location": getattr(rec, "defect_location", None),
                "is_penalty": getattr(rec, "is_penalty", False),
                "repair_cycle": getattr(rec, "repair_cycle", 0),
                "remarks": rec.remarks,
            }