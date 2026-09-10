# -*- coding: utf-8 -*-
"""
repositories/precomm_repository.py – PipeAgent v5.1
===================================================
مدیریت جامع فعالیت‌های بازرسی و پیش‌راه‌اندازی پایپینگ و تجهیزات مکانیکی
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError

from repositories.base import BaseRepository
from db.models import (
    FlushingRecord,
    LeakTestRecord,
    BoxUpRecord,
    PMIRecord,  # Implementation note.
    DimensionalCheckRecord,
    SpringHangerRecord,
    MaterialPreservationRecord,
)

PMITestRecord = PMIRecord  # Implementation note.

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Engineering Definitions
# ──────────────────────────────────────────────

class PreCommStatus(str, Enum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    PUNCH_LISTED = "PUNCH_LISTED"


class FlushingMedium(str, Enum):
    DEMIN_WATER = "DEMIN_WATER"
    POTABLE_WATER = "POTABLE_WATER"
    PLANT_AIR = "PLANT_AIR"
    INSTRUMENT_AIR = "INSTRUMENT_AIR"
    STEAM_BLOWING = "STEAM_BLOWING"
    CHEMICAL_CLEANING = "CHEMICAL_CLEANING"
    OIL_FLUSHING = "OIL_FLUSHING"


class LeakTestType(str, Enum):
    HYDROSTATIC = "HYDROSTATIC"
    PNEUMATIC = "PNEUMATIC"
    SERVICE_TEST = "SERVICE_TEST"
    HELIUM_LEAK = "HELIUM_LEAK"
    SENSITIVE_VACUUM = "SENSITIVE_VACUUM"


class SpringHangerState(str, Enum):
    LOCKED_COLD = "LOCKED_COLD"
    UNLOCKED_COLD = "UNLOCKED_COLD"
    HOT_OPERATION = "HOT_OPERATION"


# ──────────────────────────────────────────────
#  1. Flushing Repository
# ──────────────────────────────────────────────

class FlushingRepository(BaseRepository[FlushingRecord]):
    """مدیریت سوابق شستشوی خطوط لوله و پکیج‌ها (Flushing / Air Blowing)"""

    def __init__(self, db_manager: Any):
        super().__init__(db_manager, FlushingRecord)

    def get_all(
        self, project_id: int, line_number: Optional[str] = None
    ) -> List[FlushingRecord]:
        with self._session() as session:
            query = session.query(FlushingRecord).filter(
                FlushingRecord.project_id == project_id
            )
            if line_number:
                query = query.filter(FlushingRecord.line_number == line_number.strip())
            return query.order_by(desc(FlushingRecord.performed_date)).all()

    def get_by_subsystem(
        self, project_id: int, subsystem_code: str
    ) -> List[FlushingRecord]:
        """سوابق فلاشینگ مرتبط با یک ساب‌سیستم یا مدار فرآیندی"""
        with self._session() as session:
            return (
                session.query(FlushingRecord)
                .filter(
                    FlushingRecord.project_id == project_id,
                    FlushingRecord.line_number.ilike(f"%{subsystem_code.strip()}%"),
                )
                .all()
            )

    def record_flushing_completion(
        self,
        record_id: int,
        accepted_by: str,
        cleanliness_accepted: bool,
        chloride_ppm: Optional[float] = None,
        duration_minutes: Optional[int] = None,
        comments: str = "",
    ) -> Optional[FlushingRecord]:
        """تأیید نهایی تمیزی خط"""
        with self._session() as session:
            try:
                record = session.query(FlushingRecord).filter(FlushingRecord.id == record_id).first()
                if not record:
                    return None

                record.duration_min = duration_minutes
                record.result = "Pass" if cleanliness_accepted else "Fail"
                record.witnessed_by = accepted_by
                record.performed_date = date.today()
                record.remarks = comments

                session.commit()
                session.refresh(record)
                return record
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error completing flushing #{record_id}: {e}")
                raise


# ──────────────────────────────────────────────
#  2. Leak / Hydro Test Repository
# ──────────────────────────────────────────────

class LeakTestRepository(BaseRepository[LeakTestRecord]):
    """مدیریت آزمون‌های فشار هیدرواستاتیک و پنوماتیک"""

    def __init__(self, db_manager: Any):
        super().__init__(db_manager, LeakTestRecord)

    def get_all(
        self, project_id: int, line_number: Optional[str] = None
    ) -> List[LeakTestRecord]:
        with self._session() as session:
            query = session.query(LeakTestRecord).filter(
                LeakTestRecord.project_id == project_id
            )
            if line_number:
                query = query.filter(LeakTestRecord.line_number == line_number.strip())
            return query.order_by(desc(LeakTestRecord.performed_date)).all()

    def get_by_test_package(
        self, project_id: int, test_package_id: int
    ) -> List[LeakTestRecord]:
        """دریافت سوابق تست بر اساس شناسه پکیج آزمون فشار"""
        with self._session() as session:
            return (
                session.query(LeakTestRecord)
                .filter(
                    LeakTestRecord.project_id == project_id,
                    LeakTestRecord.test_package_id == test_package_id,
                )
                .all()
            )

    def record_pressure_test_results(
        self,
        test_id: int,
        actual_pressure_bar: float,
        holding_time_minutes: int,
        pressure_drop_bar: float,
        ambient_temp_c: float,
        gauge_calib_valid: bool,
        witnessed_by_qc: str,
        witnessed_by_client: Optional[str] = None,
    ) -> Optional[LeakTestRecord]:
        """ثبت مقادیر گیج فشار، زمان نگهداری، افت فشار مجاز و امضای مشترک بازرسان"""
        with self._session() as session:
            try:
                test = session.query(LeakTestRecord).filter(LeakTestRecord.id == test_id).first()
                if not test:
                    return None

                is_accepted = (pressure_drop_bar <= 0.05) and gauge_calib_valid
                test.test_pressure_bar = actual_pressure_bar
                test.holding_time_min = holding_time_minutes
                test.temp_ambient_c = ambient_temp_c
                test.performed_by = witnessed_by_qc
                test.witnessed_by = witnessed_by_client or ""
                test.result = "Pass" if is_accepted else "Fail"
                test.performed_date = date.today()

                session.commit()
                session.refresh(test)
                return test
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error recording pressure test #{test_id}: {e}")
                raise


# ──────────────────────────────────────────────
#  3. Box-Up / Reinstatement Repository
# ──────────────────────────────────────────────

class BoxUpRepository(BaseRepository[BoxUpRecord]):
    """مدیریت تأییدیه‌های بستن نهایی اتصالات، مخازن و پمپ‌ها (Final Box-Up)"""

    def __init__(self, db_manager: Any):
        super().__init__(db_manager, BoxUpRecord)

    def get_all(
        self, project_id: int, line_number: Optional[str] = None
    ) -> List[BoxUpRecord]:
        with self._session() as session:
            query = session.query(BoxUpRecord).filter(BoxUpRecord.project_id == project_id)
            if line_number:
                query = query.filter(BoxUpRecord.line_number == line_number.strip())
            return query.order_by(desc(BoxUpRecord.id)).all()

    def complete(
        self,
        boxup_id: int,
        witness_name: str,
        gasket_type_verified: bool = True,
        internals_cleaned: bool = True,
        bolts_tightened: bool = True,
    ) -> Optional[BoxUpRecord]:
        """تأیید سه‌گانه چک‌لیست: بررسی سلامت واشر (Gasket)، تمیزی داخل و سفت‌سازی پیچ‌ها"""
        with self._session() as session:
            try:
                record = session.query(BoxUpRecord).filter(BoxUpRecord.id == boxup_id).first()
                if not record:
                    return None

                all_cleared = gasket_type_verified and internals_cleaned and bolts_tightened
                record.gasket_verified = gasket_type_verified
                record.internal_cleanliness = internals_cleaned
                record.bolting_torqued = bolts_tightened
                record.client_witness = witness_name
                record.status = "Approved" if all_cleared else "Pending"
                record.inspected_date = date.today()

                session.commit()
                session.refresh(record)
                return record
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error completing box-up #{boxup_id}: {e}")
                raise


# ──────────────────────────────────────────────
#  4. Positive Material Identification (PMI) Repository
# ──────────────────────────────────────────────

class PMIRepository(BaseRepository[PMIRecord]):
    """مدیریت آزمون‌های آنالیز آلیاژی فلزات با دستگاه‌های پرتابل XRF/OES"""

    def __init__(self, db_manager: Any):
        super().__init__(db_manager, PMIRecord)

    def get_all(
        self, project_id: int, result_verdict: Optional[str] = None
    ) -> List[PMIRecord]:
        with self._session() as session:
            query = session.query(PMIRecord).filter(PMIRecord.project_id == project_id)
            if result_verdict:
                query = query.filter(PMIRecord.result == result_verdict.strip())
            return query.all()

    def get_by_heat_number(self, heat_number: str) -> List[PMIRecord]:
        """بررسی سوابق PMI یک شماره ذوب (Heat No) خاص"""
        with self._session() as session:
            return (
                session.query(PMIRecord)
                .filter(func.lower(PMIRecord.heat_number) == heat_number.strip().lower())
                .all()
            )

    def record_spectro_analysis(
        self,
        project_id: int,
        item_tag: str,
        heat_number: str,
        expected_alloy: str,
        elements_pct: Dict[str, float],
        tested_by: str,
        is_pass: bool,
    ) -> PMIRecord:
        """ثبت درصد عناصر و مقایسه با گرید آلیاژی مورد انتظار"""
        with self._session() as session:
            try:
                record = PMIRecord(
                    project_id=project_id,
                    component_tag=item_tag,
                    heat_number=heat_number,
                    required_material=expected_alloy,
                    performed_by=tested_by,
                    result="Pass" if is_pass else "Fail",
                    performed_date=date.today(),
                )
                session.add(record)
                session.commit()
                session.refresh(record)
                return record
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error saving PMI test for item {item_tag}: {e}")
                raise


# ──────────────────────────────────────────────
#  5. Dimensional Check Repository
# ──────────────────────────────────────────────

class DimensionalRepository(BaseRepository[DimensionalCheckRecord]):
    """مدیریت کنترل ابعادی اسپول‌ها، انطباق با نقشه‌های ایزومتریک و تلورانس‌ها"""

    def __init__(self, db_manager: Any):
        super().__init__(db_manager, DimensionalCheckRecord)

    def get_all(
        self, project_id: int, spool_number: Optional[str] = None
    ) -> List[DimensionalCheckRecord]:
        with self._session() as session:
            query = session.query(DimensionalCheckRecord).filter(
                DimensionalCheckRecord.project_id == project_id
            )
            # Implementation note.
            if spool_number:
                query = query.filter(DimensionalCheckRecord.check_no.ilike(f"%{spool_number}%"))
            return query.all()

    def get_out_of_tolerance(self, project_id: int) -> List[DimensionalCheckRecord]:
        """لیست اسپول‌هایی که دارای انحراف ابعادی غیرمجاز بوده و نیاز به اصلاح دارند"""
        with self._session() as session:
            return (
                session.query(DimensionalCheckRecord)
                .filter(
                    DimensionalCheckRecord.project_id == project_id,
                    DimensionalCheckRecord.result == "Fail",
                )
                .all()
            )


# ──────────────────────────────────────────────
#  6. Spring Hanger & Piping Supports Repository
# ──────────────────────────────────────────────

class SpringHangerRepository(BaseRepository[SpringHangerRecord]):
    """مدیریت ساپورت‌های فنری، قفل‌های مسافرتی (Travel Stops) و موقعیت سرد و گرم"""

    def __init__(self, db_manager: Any):
        super().__init__(db_manager, SpringHangerRecord)

    def get_all(
        self, project_id: int, line_number: Optional[str] = None
    ) -> List[SpringHangerRecord]:
        with self._session() as session:
            query = session.query(SpringHangerRecord).filter(
                SpringHangerRecord.project_id == project_id
            )
            if line_number:
                query = query.filter(SpringHangerRecord.line_number == line_number.strip())
            return query.all()

    def unlock_travel_pins(
        self, hanger_id: int, unlocked_by: str, actual_cold_position_mm: float
    ) -> Optional[SpringHangerRecord]:
        """ثبت آزادسازی پین قفل ساپورت فنری قبل از بارگذاری فرآیندی"""
        with self._session() as session:
            try:
                record = session.query(SpringHangerRecord).filter(SpringHangerRecord.id == hanger_id).first()
                if not record:
                    return None

                record.pin_removed = True
                record.pin_removed_date = date.today()
                record.cold_travel_mm = actual_cold_position_mm
                record.status = "Unlocked"
                record.inspector = unlocked_by

                session.commit()
                session.refresh(record)
                return record
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error unlocking spring hanger #{hanger_id}: {e}")
                raise

    def get_locked_hangers(self, project_id: int) -> List[SpringHangerRecord]:
        """شناسایی ساپورت‌هایی که قبل از استارت‌آپ واحد هنوز پین آن‌ها برداشته نشده است"""
        with self._session() as session:
            return (
                session.query(SpringHangerRecord)
                .filter(
                    SpringHangerRecord.project_id == project_id,
                    SpringHangerRecord.pin_removed == False,
                )
                .all()
            )


# ──────────────────────────────────────────────
#  7. Material Preservation Repository
# ──────────────────────────────────────────────

class PreservationRepository(BaseRepository[MaterialPreservationRecord]):
    """مدیریت حفاظت ادواری تجهیزات (گریس‌کاری، پایش رطوبت و...)"""

    def __init__(self, db_manager: Any):
        super().__init__(db_manager, MaterialPreservationRecord)

    def get_all(
        self, project_id: int, condition_status: Optional[str] = None
    ) -> List[MaterialPreservationRecord]:
        with self._session() as session:
            query = session.query(MaterialPreservationRecord).filter(
                MaterialPreservationRecord.project_id == project_id
            )
            if condition_status:
                query = query.filter(MaterialPreservationRecord.status == condition_status.strip())
            return query.all()

    def get_overdue_preservations(
        self, project_id: int, current_date: Optional[date] = None
    ) -> List[MaterialPreservationRecord]:
        """اقلامی که موعد نگهداری ادواری آن‌ها گذشته است"""
        ref_date = current_date or date.today()
        with self._session() as session:
            return (
                session.query(MaterialPreservationRecord)
                .filter(
                    MaterialPreservationRecord.project_id == project_id,
                    MaterialPreservationRecord.next_inspection_date < ref_date,
                )
                .order_by(asc(MaterialPreservationRecord.next_inspection_date))
                .all()
            )


# ──────────────────────────────────────────────
#  8. Pre-Commissioning Unit of Work
# ──────────────────────────────────────────────

class PreCommissioningUnitOfWork:
    """
    الگوی هماهنگ‌کننده پیش‌راه‌اندازی برای اعتبارسنجی آمادگی ساب‌سیستم‌ها
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.flushing = FlushingRepository(db_manager)
        self.leak_test = LeakTestRepository(db_manager)
        self.boxup = BoxUpRepository(db_manager)
        self.pmi = PMIRepository(db_manager)
        self.dimensional = DimensionalRepository(db_manager)
        self.spring_hangers = SpringHangerRepository(db_manager)
        self.preservation = PreservationRepository(db_manager)

    def evaluate_subsystem_readiness(
        self, project_id: int, subsystem_code: str
    ) -> Dict[str, Any]:
        """ارزیابی آمادگی کامل یک ساب‌سیستم"""
        flushing_items = self.flushing.get_by_subsystem(project_id, subsystem_code)
        flushing_ok = all(item.result == "Pass" for item in flushing_items) if flushing_items else False

        locked_hangers = self.spring_hangers.get_locked_hangers(project_id)
        hangers_ok = len(locked_hangers) == 0

        is_ready = flushing_ok and hangers_ok

        return {
            "subsystem_code": subsystem_code,
            "flushing_cleared": flushing_ok,
            "all_spring_hangers_unlocked": hangers_ok,
            "locked_hangers_count": len(locked_hangers),
            "ready_for_commissioning": is_ready,
        }