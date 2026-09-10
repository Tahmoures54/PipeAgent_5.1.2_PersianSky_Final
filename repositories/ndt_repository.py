# -*- coding: utf-8 -*-
"""
repositories/ndt_repository.py – PipeAgent v5.1
==============================================
مدیریت جامع تست‌های غیرمخرب (NDT)، پایش کیفیت جوش،
ردیابی پنالتی‌ها و محاسبه نرخ خرابی جوشکاران (Welder Repair Rate).
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError

# Implementation note.
from db.models import NDTRecord, Weld, Welder
WeldJoint = Weld  # Implementation note.

from repositories.base import BaseRepository
from db.manager import DatabaseManager

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Standards Definitions
# ──────────────────────────────────────────────

class NDTMethod(str, Enum):
    """انواع متدهای تست غیرمخرب بر اساس استاندارد ASME/AWS"""
    RT = "RT"        # Radiographic Testing
    UT = "UT"        # Ultrasonic Testing
    PAUT = "PAUT"    # Phased Array Ultrasonic Testing
    MPI = "MPI"      # Magnetic Particle Inspection (MT)
    PT = "PT"        # Liquid Penetrant Testing (DPI)
    VT = "VT"        # Visual Testing
    PMI = "PMI"      # Positive Material Identification
    HARDNESS = "HT"  # Hardness Testing
    FERRITE = "FT"   # Ferrite Content Measurement


class NDTVerdict(str, Enum):
    """نتیجه ارزیابی تست NDT"""
    ACCEPTED = "ACC"
    REJECTED = "REJ"
    PENDING = "PENDING"
    RE_TEST = "RE_TEST"        # Implementation note.
    NOT_ACCESSIBLE = "N/A"     # Implementation note.


class DefectType(str, Enum):
    """عیوب استاندارد جوشکاری (ASME Sec VIII / B31.3)"""
    CRACK = "CRACK"
    LACK_OF_FUSION = "LOF"
    LACK_OF_PENETRATION = "LOP"
    POROSITY = "POROSITY"
    SLAG_INCLUSION = "SLAG"
    UNDERCUT = "UNDERCUT"
    BURN_THROUGH = "BT"
    ROOT_CONCAVITY = "RC"
    TUNGSTEN_INCLUSION = "TI"
    EXCESS_PENETRATION = "EP"


# ──────────────────────────────────────────────
#  NDT Repository Implementation
# ──────────────────────────────────────────────

class NDTRepository(BaseRepository[NDTRecord]):
    """
    ریپازیتوری پیشرفته تست‌های غیرمخرب جوش (NDT)
    """

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, NDTRecord)

    # Implementation note.

    def get_by_weld(
        self,
        weld_id_fk: int,
        method: Optional[Union[NDTMethod, str]] = None,
    ) -> List[NDTRecord]:
        """سوابق تست‌های انجام‌شده روی یک سرجوش خاص (شامل تست‌های اولیه و تعمیری R1/R2)"""
        with self._session() as session:
            query = session.query(NDTRecord).filter(NDTRecord.weld_id_fk == weld_id_fk)
            if method:
                method_val = method.value if isinstance(method, NDTMethod) else method
                query = query.filter(NDTRecord.ndt_method == method_val)
            return query.order_by(desc(NDTRecord.inspection_date)).all()

    def get_by_report_number(
        self, report_number: str, project_id: Optional[int] = None
    ) -> List[NDTRecord]:
        """یافتن رکوردهای تست مرتبط با یک شماره گزارش NDT خاص"""
        with self._session() as session:
            query = session.query(NDTRecord).filter(
                NDTRecord.report_number.ilike(f"%{report_number.strip()}%")
            )
            if project_id:
                query = query.filter(NDTRecord.project_id == project_id)
            return query.all()

    def get_by_inspector(
        self,
        inspector_id: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[NDTRecord]:
        """سوابق بازرسی‌های ثبت‌شده توسط یک مفسر/بازرس خاص در بازه زمانی"""
        with self._session() as session:
            query = session.query(NDTRecord).filter(
                NDTRecord.inspector_id == inspector_id
            )
            if from_date:
                query = query.filter(NDTRecord.inspection_date >= from_date)
            if to_date:
                query = query.filter(NDTRecord.inspection_date <= to_date)
            return query.order_by(desc(NDTRecord.inspection_date)).all()

    def get_by_method(
        self,
        method: Union[NDTMethod, str],
        project_id: Optional[int] = None,
        verdict: Optional[Union[NDTVerdict, str]] = None,
    ) -> List[NDTRecord]:
        """دریافت تست‌ها بر اساس متد و وضعیت تأیید/رد"""
        method_val = method.value if isinstance(method, NDTMethod) else method
        with self._session() as session:
            query = session.query(NDTRecord).filter(NDTRecord.ndt_method == method_val)
            if project_id:
                query = query.filter(NDTRecord.project_id == project_id)
            if verdict:
                verdict_val = verdict.value if isinstance(verdict, NDTVerdict) else verdict
                query = query.filter(NDTRecord.verdict == verdict_val)
            return query.all()

    def get_rejected_records(
        self,
        project_id: int,
        method: Optional[Union[NDTMethod, str]] = None,
    ) -> List[NDTRecord]:
        """لیست تمام جوش‌های ریجکت‌شده که نیاز به صدور کارت تعمیر (Repair/Penalty) دارند"""
        with self._session() as session:
            query = session.query(NDTRecord).filter(
                NDTRecord.project_id == project_id,
                NDTRecord.verdict == NDTVerdict.REJECTED.value,
            )
            if method:
                method_val = method.value if isinstance(method, NDTMethod) else method
                query = query.filter(NDTRecord.ndt_method == method_val)
            return query.order_by(desc(NDTRecord.inspection_date)).all()

    # Implementation note.

    def record_ndt_result(
        self,
        weld_id_fk: int,
        project_id: int,
        ndt_method: Union[NDTMethod, str],
        report_number: str,
        verdict: Union[NDTVerdict, str],
        inspector_id: str,
        inspection_date: Optional[date] = None,
        film_size: Optional[str] = None,
        defect_type: Optional[Union[DefectType, str]] = None,
        defect_location: Optional[str] = None,
        is_penalty: bool = False,
        original_rejected_weld_id: Optional[int] = None,
        comments: str = "",
    ) -> NDTRecord:
        """
        ثبت قطعی نتیجه تست NDT با جزییات عیب و پیگیری پنالتی
        """
        method_val = ndt_method.value if isinstance(ndt_method, NDTMethod) else ndt_method
        verdict_val = verdict.value if isinstance(verdict, NDTVerdict) else verdict
        defect_val = defect_type.value if isinstance(defect_type, DefectType) else defect_type

        with self._session() as session:
            try:
                record = NDTRecord(
                    weld_id_fk=weld_id_fk,
                    project_id=project_id,
                    ndt_method=method_val,
                    report_number=report_number.strip(),
                    result=verdict_val,  # Implementation note.
                    inspector_id=inspector_id,
                    inspection_date=inspection_date or date.today(),
                    remarks=comments,  # Implementation note.
                )
                session.add(record)

                # Implementation note.
                weld = session.query(Weld).filter(Weld.id == weld_id_fk).first()
                if weld:
                    if verdict_val == NDTVerdict.ACCEPTED.value or verdict_val == "ACC":
                        weld.status = "NDT Accepted"
                    elif verdict_val == NDTVerdict.REJECTED.value or verdict_val == "REJ":
                        weld.status = "Repair Required"
                        weld.repair_count = (getattr(weld, "repair_count", 0) or 0) + 1

                session.commit()
                session.refresh(record)
                logger.info(
                    f"NDT Record #{record.id} ({method_val}) for Weld #{weld_id_fk} recorded as '{verdict_val}'."
                )
                return record

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error registering NDT result for Weld #{weld_id_fk}: {e}")
                raise

    def assign_penalty_welds(
        self,
        rejected_ndt_id: int,
        penalty_weld_ids: List[int],
        assigned_by: str,
    ) -> List[NDTRecord]:
        """
        تخصیص جوش‌های پنالتی (Tracer Welds) بر اساس قوانین استاندارد ASME B31.3
        """
        with self._session() as session:
            try:
                orig_record = (
                    session.query(NDTRecord)
                    .filter(NDTRecord.id == rejected_ndt_id)
                    .first()
                )
                if not orig_record or orig_record.result not in [NDTVerdict.REJECTED.value, "REJ", "Rejected"]:
                    raise ValueError("Source NDT record must exist and have REJECTED verdict.")

                created_penalties = []
                for weld_id in penalty_weld_ids:
                    penalty_record = NDTRecord(
                        weld_id_fk=weld_id,
                        ndt_method=orig_record.ndt_method,
                        result=NDTVerdict.PENDING.value,
                        remarks=f"Penalty assigned by {assigned_by} due to rejected Weld #{orig_record.weld_id_fk}",
                        inspection_date=date.today()
                    )
                    session.add(penalty_record)
                    created_penalties.append(penalty_record)

                session.commit()
                logger.info(
                    f"Assigned {len(created_penalties)} penalty welds for rejected NDT #{rejected_ndt_id}."
                )
                return created_penalties

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error assigning penalty welds: {e}")
                raise

    # Implementation note.

    def get_welder_repair_rate(
        self,
        welder_id: str,
        project_id: int,
        method: Optional[Union[NDTMethod, str]] = None,
    ) -> Dict[str, Any]:
        """
        محاسبه شاخص نرخ خرابی جوشکار (Welder Defect Rate %)
        """
        with self._session() as session:
            query = (
                session.query(NDTRecord)
                .join(Weld, NDTRecord.weld_id_fk == Weld.id)
                .filter(
                    Weld.welder_id == welder_id,
                    Weld.project_id == project_id,
                    NDTRecord.result.in_(
                        [NDTVerdict.ACCEPTED.value, "ACC", "Accept", NDTVerdict.REJECTED.value, "REJ", "Reject"]
                    ),
                )
            )

            if method:
                method_val = method.value if isinstance(method, NDTMethod) else method
                query = query.filter(NDTRecord.ndt_method == method_val)

            total_tested = query.count()
            total_rejected = query.filter(
                NDTRecord.result.in_([NDTVerdict.REJECTED.value, "REJ", "Reject"])
            ).count()

            repair_rate = (
                round((total_rejected / total_tested) * 100, 2)
                if total_tested > 0
                else 0.0
            )

            return {
                "welder_id": welder_id,
                "total_tested_welds": total_tested,
                "total_rejected_welds": total_rejected,
                "total_accepted_welds": total_tested - total_rejected,
                "repair_rate_percentage": repair_rate,
                "status": "CRITICAL" if repair_rate > 5.0 else "ACCEPTABLE",
            }

    def get_defect_distribution(
        self,
        project_id: int,
        method: Optional[Union[NDTMethod, str]] = None,
    ) -> Dict[str, int]:
        """تحلیل پارتو (Pareto) انواع عیوب جهت کنترل فرایند جوشکاری"""
        with self._session() as session:
            query = (
                session.query(
                    NDTRecord.remarks,
                    func.count(NDTRecord.id).label("defect_count"),
                )
                .filter(
                    NDTRecord.remarks.isnot(None),
                )
                .group_by(NDTRecord.remarks)
                .order_by(desc("defect_count"))
            )

            if method:
                method_val = method.value if isinstance(method, NDTMethod) else method
                query = query.filter(NDTRecord.ndt_method == method_val)

            return {r.remarks: r.defect_count for r in query.all()}

    def get_ndt_coverage_stats(
        self,
        project_id: int,
        line_number: Optional[str] = None,
    ) -> Dict[str, Any]:
        """پایش درصد پیشرفت تست‌های غیرمخرب خطوط لوله (NDT Coverage %)"""
        with self._session() as session:
            weld_query = session.query(Weld).filter(Weld.project_id == project_id)
            if line_number:
                weld_query = weld_query.filter(Weld.line_number == line_number)

            total_welds = weld_query.count()

            ndt_query = (
                session.query(func.count(func.distinct(NDTRecord.weld_id_fk)))
                .join(Weld, NDTRecord.weld_id_fk == Weld.id)
                .filter(
                    Weld.project_id == project_id,
                    NDTRecord.result.in_([NDTVerdict.ACCEPTED.value, "ACC", "Accept"]),
                )
            )

            welds_accepted_ndt = ndt_query.scalar() or 0
            coverage_pct = (
                round((welds_accepted_ndt / total_welds) * 100, 2)
                if total_welds > 0
                else 0.0
            )

            return {
                "project_id": project_id,
                "line_number": line_number or "ALL",
                "total_welds_fitted": total_welds,
                "total_welds_ndt_cleared": welds_accepted_ndt,
                "actual_ndt_coverage_pct": coverage_pct,
            }