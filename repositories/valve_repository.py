# -*- coding: utf-8 -*-
"""
repositories/valve_repository.py – PipeAgent v5.1
=================================================
مدیریت جامع شیرآلات صنعتی (Manual, Control, Actuated & Safety Valves)
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError

from db.models import ValveRecord, TestPackage, LineListItem
Line = LineListItem  # Implementation note.

from repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Implementation note.
if not hasattr(ValveRecord, "tag_number") and hasattr(ValveRecord, "valve_tag"):
    ValveRecord.tag_number = ValveRecord.valve_tag
if not hasattr(ValveRecord, "size") and hasattr(ValveRecord, "size_nps"):
    ValveRecord.size = ValveRecord.size_nps
if not hasattr(ValveRecord, "rating") and hasattr(ValveRecord, "rating_class"):
    ValveRecord.rating = ValveRecord.rating_class


class ValveType(str, Enum):
    GATE = "GATE"
    GLOBE = "GLOBE"
    BALL = "BALL"
    CHECK = "CHECK"
    BUTTERFLY = "BUTTERFLY"
    PLUG = "PLUG"
    NEEDLE = "NEEDLE"
    CONTROL = "CONTROL"
    PSV = "PSV"
    PRV = "PRV"
    DBB = "DBB"


class ValveStatus(str, Enum):
    RECEIVED_IN_WAREHOUSE = "RECEIVED"
    IN_TEST_SHOP = "IN_TEST_SHOP"
    TEST_PASSED = "TEST_PASSED"
    TEST_FAILED = "TEST_FAILED"
    PRESERVED_TAGGED = "PRESERVED"
    ISSUED_TO_SITE = "ISSUED_TO_SITE"
    ERECTED_ON_LINE = "ERECTED"
    PUNCHED = "PUNCHED"
    COMMISSIONED = "COMMISSIONED"


class CarSealStatus(str, Enum):
    NOT_APPLICABLE = "NA"
    CSO = "CSO"
    CSC = "CSC"
    LOCKED_OPEN = "LO"
    LOCKED_CLOSED = "LC"


class LeakageAcceptanceClass(str, Enum):
    CLASS_II = "CLASS_II"
    CLASS_III = "CLASS_III"
    CLASS_IV = "CLASS_IV"
    CLASS_V = "CLASS_V"
    CLASS_VI = "CLASS_VI"
    API_598_ZERO = "API_598_ZERO"


class ValveRepository(BaseRepository[ValveRecord]):
    """
    ریپازیتوری پیشرفته مدیریت شیرآلات صنعتی، تست‌های کارگاهی و ایمنی فرآیند
    """

    def __init__(self, db_manager: Any):
        super().__init__(db_manager, ValveRecord)

    def find_by_tag(
        self,
        project_id: int,
        tag_number: str,
        load_relations: bool = False,
    ) -> Optional[ValveRecord]:
        with self._session() as session:
            query = session.query(ValveRecord).filter(
                ValveRecord.project_id == project_id,
                func.upper(ValveRecord.tag_number) == tag_number.strip().upper(),
            )
            return query.first()

    def search_valves(
        self,
        project_id: int,
        tag_keyword: Optional[str] = None,
        valve_type: Optional[Union[ValveType, str]] = None,
        size_inch: Optional[str] = None,
        pressure_class: Optional[str] = None,
        line_number: Optional[str] = None,
        status: Optional[Union[ValveStatus, str]] = None,
        car_seal: Optional[Union[CarSealStatus, str]] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[List[ValveRecord], int]:
        with self._session() as session:
            query = session.query(ValveRecord).filter(ValveRecord.project_id == project_id)

            if tag_keyword:
                query = query.filter(ValveRecord.tag_number.ilike(f"%{tag_keyword.strip()}%"))

            if valve_type:
                v_type = valve_type.value if isinstance(valve_type, ValveType) else valve_type
                query = query.filter(ValveRecord.valve_type == v_type)

            if size_inch:
                query = query.filter(ValveRecord.size == size_inch.strip())

            if pressure_class:
                query = query.filter(ValveRecord.rating == pressure_class.strip())

            if line_number:
                query = query.filter(ValveRecord.line_number.ilike(f"%{line_number.strip()}%"))

            if status:
                stat_val = status.value if isinstance(status, ValveStatus) else status
                query = query.filter(ValveRecord.status == stat_val)

            total_count = query.count()
            items = (
                query.order_by(ValveRecord.tag_number.asc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            return items, total_count

    def get_untested_valves(
        self,
        project_id: int,
        valve_type: Optional[Union[ValveType, str]] = None,
    ) -> List[ValveRecord]:
        with self._session() as session:
            query = session.query(ValveRecord).filter(
                ValveRecord.project_id == project_id,
                ValveRecord.hydro_shell_test == False,
            )
            return query.order_by(ValveRecord.id.asc()).all()

    def record_api598_testing(
        self,
        valve_id: int,
        shell_test_pressure_bar: float,
        shell_test_passed: bool,
        high_pressure_seat_bar: float,
        seat_test_passed: bool,
        low_pressure_air_seat_bar: Optional[float] = None,
        air_seat_passed: Optional[bool] = None,
        backseat_test_passed: Optional[bool] = None,
        tested_by_technician: str = "",
        witnessed_by_qc: str = "",
        test_report_number: str = "",
        actual_leak_rate: str = "0 drops/min",
        comments: str = "",
    ) -> Optional[ValveRecord]:
        with self._session() as session:
            try:
                valve = session.query(ValveRecord).filter(ValveRecord.id == valve_id).first()
                if not valve:
                    return None

                valve.hydro_shell_test = shell_test_passed
                valve.hydro_shell_pressure_bar = shell_test_pressure_bar
                valve.hydro_shell_date = date.today()
                valve.hydro_seat_test = seat_test_passed
                valve.hydro_seat_pressure_bar = high_pressure_seat_bar
                valve.hydro_seat_date = date.today()
                
                valve.test_witness = witnessed_by_qc
                valve.installed_by = tested_by_technician
                valve.status = ValveStatus.TEST_PASSED.value if (shell_test_passed and seat_test_passed) else ValveStatus.TEST_FAILED.value
                valve.remarks = comments

                session.commit()
                session.refresh(valve)
                return valve

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error recording API 598 test for valve #{valve_id}: {e}")
                raise

    def record_psv_pop_test(
        self,
        valve_id: int,
        set_pressure_bar: float,
        actual_pop_pressure_bar: float,
        reseat_pressure_bar: float,
        cold_diff_test_pressure_cdtp: float,
        test_medium: str = "NITROGEN",
        bubble_count_per_minute: int = 0,
        calibrated_by: str = "",
        witnessed_by_client: Optional[str] = None,
        certificate_number: str = "",
    ) -> Optional[ValveRecord]:
        with self._session() as session:
            try:
                valve = session.query(ValveRecord).filter(ValveRecord.id == valve_id).first()
                if not valve:
                    return None

                valve.hydro_shell_test = True
                valve.hydro_shell_pressure_bar = set_pressure_bar
                valve.hydro_seat_test = (bubble_count_per_minute == 0)
                valve.test_witness = witnessed_by_client or ""
                valve.status = ValveStatus.TEST_PASSED.value
                valve.remarks = f"[PSV] Cert: {certificate_number}, Calib: {calibrated_by}"

                session.commit()
                session.refresh(valve)
                return valve

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error recording PSV pop test for valve #{valve_id}: {e}")
                raise

    def update_car_seal_status(
        self,
        valve_id: int,
        car_seal: Union[CarSealStatus, str],
        car_seal_tag_no: str,
        installed_by: str,
    ) -> Optional[ValveRecord]:
        cs_val = car_seal.value if isinstance(car_seal, CarSealStatus) else car_seal
        with self._session() as session:
            try:
                valve = session.query(ValveRecord).filter(ValveRecord.id == valve_id).first()
                if not valve:
                    return None

                valve.remarks = f"[Car Seal Open/Close tag: {car_seal_tag_no} by {installed_by}]"
                session.commit()
                session.refresh(valve)
                return valve

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error updating car seal status for valve #{valve_id}: {e}")
                raise

    def mark_valve_erected(
        self,
        valve_id: int,
        flow_direction_verified: bool,
        stem_orientation_acceptable: bool,
        erected_by: str,
    ) -> Optional[ValveRecord]:
        with self._session() as session:
            try:
                valve = session.query(ValveRecord).filter(ValveRecord.id == valve_id).first()
                if not valve:
                    return None

                valve.status = ValveStatus.ERECTED_ON_LINE.value
                valve.installed_by = erected_by
                valve.installed_date = date.today()

                session.commit()
                session.refresh(valve)
                return valve

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error marking valve #{valve_id} as erected: {e}")
                raise

    def bulk_create_valves(
        self, project_id: int, valves_data: List[Dict[str, Any]]
    ) -> List[ValveRecord]:
        with self._session() as session:
            try:
                instances = []
                for data in valves_data:
                    data["project_id"] = project_id
                    instances.append(ValveRecord(**data))

                session.bulk_save_objects(instances, return_defaults=True)
                session.commit()
                return instances

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Failed to bulk-create valves: {e}")
                raise

    def get_workshop_testing_kpis(self, project_id: int) -> Dict[str, Any]:
        with self._session() as session:
            total_valves = session.query(func.count(ValveRecord.id)).filter(
                ValveRecord.project_id == project_id
            ).scalar() or 0

            tested_passed = session.query(func.count(ValveRecord.id)).filter(
                ValveRecord.project_id == project_id,
                ValveRecord.hydro_shell_test == True,
                ValveRecord.hydro_seat_test == True,
            ).scalar() or 0

            erected_count = session.query(func.count(ValveRecord.id)).filter(
                ValveRecord.project_id == project_id,
                ValveRecord.status == ValveStatus.ERECTED_ON_LINE.value,
            ).scalar() or 0

            return {
                "project_id": project_id,
                "counts": {
                    "total_valves": total_valves,
                    "tested_passed": tested_passed,
                    "tested_failed": 0,
                    "erected_on_site": erected_count,
                    "untested_remaining": total_valves - tested_passed,
                },
                "psv_metrics": {
                    "total_psv_count": 0,
                    "calibrated_psv_count": 0,
                    "psv_completion_pct": 0.0,
                },
                "performance": {
                    "shop_testing_progress_pct": round((tested_passed / total_valves * 100), 2) if total_valves > 0 else 0.0,
                    "first_time_pass_rate_pct": 100.0,
                },
            }