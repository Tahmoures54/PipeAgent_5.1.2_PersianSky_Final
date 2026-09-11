# -*- coding: utf-8 -*-
"""
repositories/weld_repository.py – PipeAgent v5.1
================================================
مدیریت جامع سرجوش‌های پایپینگ و پایپ‌لاین (Welding Management System)
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError

from db.models import Weld, NDTRecord, Spool, LineListItem, Welder
Line = LineListItem  # Implementation note.

from repositories.base import BaseRepository
from db.manager import DatabaseManager

logger = logging.getLogger(__name__)

# Industry aliases (weld_number, drawing_number, dia_inch, welding_date, …)
# are declared as SQLAlchemy synonyms on db.models.Weld.


class WeldType(str, Enum):
    BUTT_WELD = "BW"
    SOCKET_WELD = "SW"
    FILLET_WELD = "FW"
    BRANCH_WELD = "BRANCH"
    MITRE_WELD = "MITRE"
    OLET_WELD = "OLET"
    SEAL_WELD = "SEAL"


class WeldCategory(str, Enum):
    SHOP_WELD = "SHOP"
    FIELD_WELD = "FIELD"
    FIELD_FIT_WELD = "FFW"
    TIE_IN_WELD = "TIE_IN"
    GOLDEN_WELD = "GOLDEN"


class WeldStatus(str, Enum):
    FITUP_PENDING = "FITUP_PENDING"
    FITUP_ACCEPTED = "FITUP_ACCEPTED"
    FITUP_REJECTED = "FITUP_REJECTED"
    WELDING_IN_PROGRESS = "IN_PROGRESS"
    WELDED_VT_PENDING = "WELDED"
    VT_ACCEPTED = "VT_ACCEPTED"
    VT_REJECTED = "VT_REJECTED"
    NDT_REQUESTED = "NDT_REQUESTED"
    NDT_CLEARED = "NDT_CLEARED"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    CUT_OUT_REQUIRED = "CUT_OUT"
    COMPLETED = "COMPLETED"


class WeldingProcess(str, Enum):
    GTAW = "GTAW"
    SMAW = "SMAW"
    GTAW_SMAW = "GTAW+SMAW"
    GMAW = "GMAW"
    FCAW = "FCAW"
    SAW = "SAW"


class WeldRepository(BaseRepository[Weld]):
    """
    ریپازیتوری پیشرفته مدیریت سرجوش‌ها، کنترل کیفی و محاسبات مهندسی
    """

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, Weld)

    def find_weld(
        self,
        project_id: int,
        weld_number: str,
        drawing_number: Optional[str] = None,
        line_number: Optional[str] = None,
        load_ndt_history: bool = False,
    ) -> Optional[Weld]:
        with self._session() as session:
            query = session.query(Weld).filter(
                Weld.project_id == project_id,
                func.upper(Weld.weld_id) == weld_number.strip().upper(),
            )
            if drawing_number:
                query = query.filter(func.upper(Weld.iso_number) == drawing_number.strip().upper())
            if line_number:
                query = query.filter(func.upper(Weld.line_number) == line_number.strip().upper())
            return query.first()

    def search_welds(
        self,
        project_id: int,
        line_number: Optional[str] = None,
        drawing_number: Optional[str] = None,
        spool_number: Optional[str] = None,
        welder_id: Optional[str] = None,
        weld_category: Optional[Union[WeldCategory, str]] = None,
        status: Optional[Union[WeldStatus, str]] = None,
        test_package_id: Optional[int] = None,
        is_golden_weld: Optional[bool] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[List[Weld], int]:
        with self._session() as session:
            query = session.query(Weld).filter(Weld.project_id == project_id)

            if line_number:
                query = query.filter(Weld.line_number.ilike(f"%{line_number.strip()}%"))
            if drawing_number:
                query = query.filter(Weld.iso_number.ilike(f"%{drawing_number.strip()}%"))
            if welder_id:
                query = query.filter(Weld.welder_id == welder_id.strip())
            if status:
                stat_val = status.value if isinstance(status, WeldStatus) else status
                query = query.filter(Weld.status == stat_val)

            total_count = query.count()
            items = (
                query.order_by(Weld.line_number.asc(), Weld.id.asc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            return items, total_count

    def get_by_welder(
        self,
        project_id: int,
        welder_id: str,
        role: str = "ALL",
    ) -> List[Weld]:
        with self._session() as session:
            query = session.query(Weld).filter(Weld.project_id == project_id)
            query = query.filter(Weld.welder_id == welder_id.strip())
            return query.order_by(desc(Weld.id)).all()

    def get_golden_welds(self, project_id: int) -> List[Weld]:
        with self._session() as session:
            return (
                session.query(Weld)
                .filter(
                    Weld.project_id == project_id,
                    Weld.weld_type == "Golden",
                )
                .all()
            )

    def record_fitup_inspection(
        self,
        weld_id: int,
        is_passed: bool,
        inspector_name: str,
        root_gap_mm: Optional[float] = None,
        hi_lo_alignment_mm: Optional[float] = None,
        pipe1_heat_no: Optional[str] = None,
        pipe2_heat_no: Optional[str] = None,
        rejection_reason: str = "",
    ) -> Optional[Weld]:
        with self._session() as session:
            try:
                weld = session.query(Weld).filter(Weld.id == weld_id).first()
                if not weld:
                    return None

                weld.status = WeldStatus.FITUP_ACCEPTED.value if is_passed else WeldStatus.FITUP_REJECTED.value
                weld.fitup_inspector = inspector_name
                weld.fitup_date = date.today()
                weld.filler_heat_no = pipe1_heat_no  # Implementation note.
                weld.remarks = f"Gap: {root_gap_mm}, Hi-Lo: {hi_lo_alignment_mm}. {rejection_reason}"

                session.commit()
                session.refresh(weld)
                return weld
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error recording fitup on weld #{weld_id}: {e}")
                raise

    def record_welding_completion(
        self,
        weld_id: int,
        wps_number: str,
        root_welder_id: str,
        cap_welder_id: str,
        welding_process: Union[WeldingProcess, str],
        welding_date: Optional[date] = None,
        electrode_heat_batch: Optional[str] = None,
    ) -> Optional[Weld]:
        proc_val = welding_process.value if isinstance(welding_process, WeldingProcess) else welding_process
        with self._session() as session:
            try:
                weld = session.query(Weld).filter(Weld.id == weld_id).first()
                if not weld:
                    return None

                weld.welder_id = root_welder_id.strip()
                weld.welder_name = f"Root: {root_welder_id} / Cap: {cap_welder_id}"
                weld.weld_start_datetime = welding_date or date.today()
                weld.weld_end_datetime = welding_date or date.today()
                weld.filler_heat_no = electrode_heat_batch
                weld.status = WeldStatus.WELDED_VT_PENDING.value

                session.commit()
                session.refresh(weld)
                return weld
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error recording welding completion for weld #{weld_id}: {e}")
                raise

    def record_visual_inspection(
        self,
        weld_id: int,
        is_passed: bool,
        inspector_name: str,
        report_number: str,
        defect_comments: str = "",
    ) -> Optional[Weld]:
        with self._session() as session:
            try:
                weld = session.query(Weld).filter(Weld.id == weld_id).first()
                if not weld:
                    return None

                weld.status = WeldStatus.VT_ACCEPTED.value if is_passed else WeldStatus.VT_REJECTED.value
                weld.fitup_inspector = inspector_name
                weld.remarks = f"[VT Report: {report_number}] {defect_comments}"

                session.commit()
                session.refresh(weld)
                return weld
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error recording visual inspection for weld #{weld_id}: {e}")
                raise

    def initiate_weld_repair(
        self,
        weld_id: int,
        repair_welder_id: str,
        defect_type: str,
        defect_location_clock: str,
        repair_wps: str,
        is_cut_out: bool = False,
    ) -> Optional[Weld]:
        with self._session() as session:
            try:
                weld = session.query(Weld).filter(Weld.id == weld_id).first()
                if not weld:
                    return None

                weld.repair_count = (getattr(weld, "repair_count", 0) or 0) + 1
                weld.status = WeldStatus.CUT_OUT_REQUIRED.value if is_cut_out else WeldStatus.REPAIR_REQUIRED.value
                weld.remarks = f"[REPAIR] Welder: {repair_welder_id}, Defect: {defect_type} ({defect_location_clock}), WPS: {repair_wps}"

                session.commit()
                session.refresh(weld)
                return weld
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error initiating repair for weld #{weld_id}: {e}")
                raise

    def bulk_create_welds(
        self, project_id: int, welds_data: List[Dict[str, Any]]
    ) -> List[Weld]:
        with self._session() as session:
            try:
                instances = []
                for data in welds_data:
                    data["project_id"] = project_id
                    data.setdefault("status", WeldStatus.FITUP_PENDING.value)
                    instances.append(Weld(**data))

                session.bulk_save_objects(instances, return_defaults=True)
                session.commit()
                return instances
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Bulk create welds failed: {e}")
                raise

    def get_welding_dia_inch_kpis(self, project_id: int) -> Dict[str, Any]:
        with self._session() as session:
            total_welds = session.query(func.count(Weld.id)).filter(Weld.project_id == project_id).scalar() or 0

            # Implementation note.
            total_dia_inch = float(session.query(func.sum(Weld.size)).filter(
                Weld.project_id == project_id
            ).scalar() or 0.0)

            completed_dia_inch = float(session.query(func.sum(Weld.size)).filter(
                Weld.project_id == project_id,
                Weld.status.in_([
                    WeldStatus.WELDED_VT_PENDING.value,
                    WeldStatus.VT_ACCEPTED.value,
                    WeldStatus.NDT_REQUESTED.value,
                    WeldStatus.NDT_CLEARED.value,
                    WeldStatus.COMPLETED.value,
                ]),
            ).scalar() or 0.0)

            repaired_welds_count = session.query(func.count(Weld.id)).filter(
                Weld.project_id == project_id,
                Weld.repair_count > 0,
            ).scalar() or 0

            return {
                "project_id": project_id,
                "counts": {
                    "total_welds": total_welds,
                    "repaired_welds": repaired_welds_count,
                    "repair_rate_pct": round((repaired_welds_count / total_welds * 100), 2) if total_welds > 0 else 0.0,
                },
                "dia_inch_metrics": {
                    "total_dia_inch": total_dia_inch,
                    "completed_dia_inch": completed_dia_inch,
                    "shop_completed_dia_inch": completed_dia_inch * 0.6,  # Implementation note.
                    "field_completed_dia_inch": completed_dia_inch * 0.4,  # Implementation note.
                    "welding_dia_inch_progress_pct": round((completed_dia_inch / total_dia_inch * 100), 2) if total_dia_inch > 0 else 0.0,
                },
            }