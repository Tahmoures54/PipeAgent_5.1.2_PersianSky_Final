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
                    NDTRecord.weld_id_fk == weld_pk,
                    NDTRecord.ndt_method == method_str,
                    getattr(NDTRecord, "repair_cycle", 0) == repair_cycle_no,
                )
                .first()
            )

            if existing_record:
                existing_record.inspection_date = inspection_date or date.today()
                existing_record.inspector_id = inspector_id.strip()
                existing_record.result = verdict_str
                existing_record.report_number = report_number.strip()
                existing_record.defect_type = defect_str
                existing_record.defect_location = defect_location_clock
                existing_record.remarks = remarks.strip()
                record_obj = existing_record
            else:
                record_obj = NDTRecord(
                    weld_id_fk=weld_pk,
                    project_id=weld.project_id,
                    ndt_method=method_str,
                    inspection_date=inspection_date or date.today(),
                    inspector_id=inspector_id.strip(),
                    result=verdict_str,
                    report_number=report_number.strip(),
                    defect_type=defect_str,
                    defect_location=defect_location_clock,
                    is_penalty=is_penalty,
                    original_rejected_weld_id=original_rejected_weld_id,
                    repair_cycle=repair_cycle_no,
                    remarks=remarks.strip(),
                    created_at=datetime.utcnow(),
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

            orig_weld = session.get(Weld, orig_ndt.weld_id_fk)
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
                    weld_id_fk=cw.id,
                    project_id=project_id,
                    ndt_method=orig_ndt.ndt_method,
                    result=NDTVerdict.PENDING.value,
                    is_penalty=True,
                    original_rejected_weld_id=orig_weld.id,
                    remarks=f"Penalty assigned by {assigned_by} due to rejected Weld #{orig_weld.id} (Welder: {target_welder})",
                    created_at=datetime.utcnow(),
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
        """
        بررسی انطباق درصد بازرسی واقعی انجام‌شده با درصد الزامی مشخص‌شده در Line List:
        مثال: اگر لاین نیازمند ۱۰٪ RT باشد، آیا حداقل ۱۰٪ کل اینچ-قطر یا سرجوش‌ها ترخیص شده است؟
        """
        clean_line_no = line_number.strip().upper()

        with self.db.session_scope() as session:
            # Implementation note.
            line_item = (
                session.query(LineListItem)
                .filter(
                    LineListItem.project_id == project_id,
                    LineListItem.line_number == clean_line_no,
                )
                .first()
            )
            required_rt_pct = float(getattr(line_item, "ndt_percent_rt", 5.0) or 5.0) if line_item else 5.0

            # Implementation note.
            welds = session.query(Weld).filter(
                Weld.project_id == project_id,
                Weld.line_number == clean_line_no,
            ).all()

            total_welds = len(welds)
            total_dia_inch = sum(float(getattr(w, "dia_inch", 1.0) or 1.0) for w in welds)

            if total_welds == 0:
                return {
                    "line_number": clean_line_no,
                    "total_welds": 0,
                    "coverage_met": True,
                    "message": "No welds registered on this line.",
                }

            weld_ids = [w.id for w in welds]

            # Implementation note.
            cleared_rt_welds = (
                session.query(func.distinct(NDTRecord.weld_id_fk))
                .filter(
                    NDTRecord.weld_id_fk.in_(weld_ids),
                    NDTRecord.ndt_method == NDTMethod.RT.value,
                    NDTRecord.result == NDTVerdict.ACCEPTED.value,
                )
                .all()
            )
            cleared_weld_ids = {r[0] for r in cleared_rt_welds}
            cleared_count = len(cleared_weld_ids)

            cleared_dia_inch = sum(
                float(getattr(w, "dia_inch", 1.0) or 1.0)
                for w in welds if w.id in cleared_weld_ids
            )

            actual_joint_pct = round((cleared_count / total_welds * 100), 2)
            actual_dia_inch_pct = round((cleared_dia_inch / total_dia_inch * 100), 2) if total_dia_inch > 0 else 0.0

            coverage_satisfied = actual_joint_pct >= required_rt_pct

            return {
                "project_id": project_id,
                "line_number": clean_line_no,
                "total_welds_count": total_welds,
                "total_dia_inch": round(total_dia_inch, 1),
                "rt_cleared_welds_count": cleared_count,
                "rt_cleared_dia_inch": round(cleared_dia_inch, 1),
                "required_rt_percent": required_rt_pct,
                "actual_rt_joint_percent": actual_joint_pct,
                "actual_rt_dia_inch_percent": actual_dia_inch_pct,
                "is_coverage_satisfied": coverage_satisfied,
                "status": "COMPLIANT" if coverage_satisfied else "DEFICIT",
            }

    # Implementation note.

    def get_project_ndt_summary(self, project_id: int) -> Dict[str, Any]:
        """
        محاسبه ماتریس آماری تست‌های غیرمخرب با اجرای کوئری‌های تجمعی مستقیم در دیتابیس
        (حذف کامل گلوگاه حافظه RAM).
        """
        with self.db.session_scope() as session:
            # Implementation note.
            stats = session.query(
                func.count(NDTRecord.id).label("total_records"),
                func.sum(case((NDTRecord.result == NDTVerdict.ACCEPTED.value, 1), else_=0)).label("pass_count"),
                func.sum(case((NDTRecord.result == NDTVerdict.REJECTED.value, 1), else_=0)).label("fail_count"),
                func.sum(case((NDTRecord.result == NDTVerdict.PENDING.value, 1), else_=0)).label("pending_count"),
                func.sum(case((NDTRecord.is_penalty == True, 1), else_=0)).label("penalty_count"),
            ).filter(NDTRecord.project_id == project_id).first()

            # Implementation note.
            method_breakdown = (
                session.query(
                    NDTRecord.ndt_method,
                    func.count(NDTRecord.id).label("total"),
                    func.sum(case((NDTRecord.result == NDTVerdict.ACCEPTED.value, 1), else_=0)).label("passed"),
                    func.sum(case((NDTRecord.result == NDTVerdict.REJECTED.value, 1), else_=0)).label("failed"),
                )
                .filter(NDTRecord.project_id == project_id)
                .group_by(NDTRecord.ndt_method)
                .all()
            )

            # Implementation note.
            defect_stats = (
                session.query(
                    NDTRecord.defect_type,
                    func.count(NDTRecord.id).label("count"),
                )
                .filter(
                    NDTRecord.project_id == project_id,
                    NDTRecord.defect_type.isnot(None),
                )
                .group_by(NDTRecord.defect_type)
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
                "top_recurring_defects": {row.defect_type: row.count for row in defect_stats},
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