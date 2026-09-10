# -*- coding: utf-8 -*-
"""
services/precomm_service.py – PipeAgent
سرویس جامع و هوشمند پیش‌راه‌اندازی (Pre-Commissioning Engineering Service)
شامل: کنترل شستشوی مدارها (Flushing & Chloride Limit)، آزمون‌های فشار و نشتی (Leak Test)،
مدیریت پلمپ نهایی تجهیزات (Vessel & Valve Box-Up)، آزادسازی پین‌های ساپورت فنری،
سیستم برنامه‌ریزی و هشدار نگهداری ادواری تجهیزات (Material Preservation Scheduler).
"""

from __future__ import annotations

import logging
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import func, and_, or_, desc, case
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from repositories.precomm_repository import (
    FlushingRepository,
    LeakTestRepository,
    BoxUpRepository,
    PMIRepository,
    DimensionalRepository,
    SpringHangerRepository,
    PreservationRepository,
)
from db.models import (
    FlushingRecord,
    LeakTestRecord,
    BoxUpRecord,
    PMITestRecord,
    DimensionalCheckRecord,
    SpringHangerRecord,
    MaterialPreservationRecord,
    LineListItem,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Engineering Definitions
# ──────────────────────────────────────────────

class PreCommStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


class FlushingMedium(str, Enum):
    DEMIN_WATER = "DEMIN_WATER"                # Implementation note.
    POTABLE_WATER = "POTABLE_WATER"            # Implementation note.
    PLANT_AIR = "PLANT_AIR"                    # Implementation note.
    STEAM_BLOWING = "STEAM"                    # Implementation note.
    CHEMICAL = "CHEMICAL_CLEANING"              # Implementation note.


class SpringHangerState(str, Enum):
    LOCKED_FOR_TEST = "LOCKED"                 # Implementation note.
    UNLOCKED_COLD = "UNLOCKED_COLD"            # Implementation note.
    OPERATING_HOT = "OPERATING_HOT"            # Implementation note.


class PreservationPeriod(str, Enum):
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    SEMI_ANNUALLY = "SEMI_ANNUALLY"


# ──────────────────────────────────────────────
#  Custom Domain Exceptions
# ──────────────────────────────────────────────

class PreCommValidationError(Exception):
    """خطای عدم انطباق با الزامات استانداردهای پیش‌راه‌اندازی"""
    pass


class ChlorideLimitExceededError(Exception):
    """خطای بالا بودن میزان کلراید آب در شستشوی خطوط استنلس استیل"""
    pass


# ──────────────────────────────────────────────
#  PreCommService Implementation
# ──────────────────────────────────────────────

class PreCommService:
    """
    سرویس مدیریت مهندسی پیش‌راه‌اندازی، تمیزکاری و تضمین آمادگی واحد برای استارت‌آپ
    """

    def __init__(self, session: Session):
        self.session = session
        self.flushing = FlushingRepository(session)
        self.leak_test = LeakTestRepository(session)
        self.boxup = BoxUpRepository(session)
        self.pmi = PMIRepository(session)
        self.dimensional = DimensionalRepository(session)
        self.spring = SpringHangerRepository(session)
        self.preservation = PreservationRepository(session)

    # Implementation note.

    def record_flushing(
        self,
        project_id: int,
        line_number: str,
        flushing_medium: Union[FlushingMedium, str],
        *,
        chloride_ppm: Optional[float] = None,
        velocity_m_s: Optional[float] = None,
        duration_minutes: int = 30,
        reinstate_status: str = "PENDING",
        inspector_name: str = "",
        is_passed: bool = True,
        comments: str = "",
    ) -> FlushingRecord:
        """
        ثبت عملیات تمیزکاری و شستشوی خط (Flushing / Air Blowing) همراه با کنترل متالورژیکی:
        - اگر جنس خط Stainless Steel باشد، میزان کلراید آب شستشو نباید از 50 ppm تجاوز کند (ASME B31.3).
        """
        line_clean = line_number.strip().upper()
        medium_val = flushing_medium.value if isinstance(flushing_medium, FlushingMedium) else str(flushing_medium).strip().upper()

        # Implementation note.
        line_item = (
            self.session.query(LineListItem)
            .filter(
                LineListItem.project_id == project_id,
                LineListItem.line_number == line_clean,
            )
            .first()
        )

        if line_item and line_item.material:
            material_upper = line_item.material.upper()
            # Implementation note.
            if any(ss_type in material_upper for ss_type in ["SS", "316", "304", "ALLOY"]) and medium_val in [FlushingMedium.DEMIN_WATER.value, FlushingMedium.POTABLE_WATER.value]:
                if chloride_ppm is not None and chloride_ppm > 50.0:
                    error_msg = f"Chloride level ({chloride_ppm} ppm) exceeds maximum limit (50 ppm) for Stainless Steel Line '{line_clean}'!"
                    logger.error(error_msg)
                    raise ChlorideLimitExceededError(error_msg)

        status_val = PreCommStatus.ACCEPTED.value if is_passed else PreCommStatus.REJECTED.value

        record = self.flushing.add(
            project_id=project_id,
            line_number=line_clean,
            flushing_medium=medium_val,
            chloride_ppm=chloride_ppm,
            flow_velocity=velocity_m_s,
            duration=duration_minutes,
            reinstatement_status=reinstate_status,
            inspector_name=inspector_name.strip(),
            result="Accept" if is_passed else "Reject",
            status=status_val,
            execution_date=date.today(),
            remarks=comments.strip(),
        )
        self.session.commit()
        logger.info(f"Flushing registered for Line '{line_clean}' [{medium_val}] -> Status: {status_val}")
        return record

    # Implementation note.

    def record_leak_test(
        self,
        project_id: int,
        test_package_id: int,
        test_type: str,  # Hydrostatic, Pneumatic, Helium Leak, Sensitive Leak
        target_pressure_bar: float,
        actual_pressure_bar: float,
        pressure_drop_bar: float,
        holding_time_minutes: int,
        gauge_calib_valid: bool,
        witness_qc: str,
        witness_client: Optional[str] = None,
    ) -> LeakTestRecord:
        """
        ثبت آزمون نشتی، تطبیق افت فشار مجاز (معمولاً صفر در اتصالات فلنجی) و بررسی کالیبراسیون گیج‌ها
        """
        if not gauge_calib_valid:
            raise PreCommValidationError("Cannot approve leak test: Pressure gauge calibration certificate is invalid or expired!")

        # Implementation note.
        is_passed = (pressure_drop_bar <= 0.05) and (actual_pressure_bar >= target_pressure_bar)
        status_val = PreCommStatus.ACCEPTED.value if is_passed else PreCommStatus.REJECTED.value

        record = self.leak_test.add(
            project_id=project_id,
            test_package_id=test_package_id,
            test_type=test_type.strip().upper(),
            target_pressure=target_pressure_bar,
            actual_pressure=actual_pressure_bar,
            pressure_drop=pressure_drop_bar,
            holding_time=holding_time_minutes,
            inspector_name=witness_qc.strip(),
            client_witness=witness_client.strip() if witness_client else None,
            result="Accept" if is_passed else "Reject",
            status=status_val,
            test_date=date.today(),
        )
        self.session.commit()
        return record

    # Implementation note.

    def record_boxup(
        self,
        project_id: int,
        item_tag: str,  # Implementation note.
        item_type: str,  # VESSEL, EXCHANGER, CONTROL_VALVE, PUMP_SUCTION
        gasket_type_verified: bool,
        internals_cleaned: bool,
        bolts_tightened: bool,
        inspector_name: str,
    ) -> BoxUpRecord:
        """
        ثبت درخواست باکس‌آپ (بستن دریچه مخازن یا پلمپ ولوها) با اعتبارسنجی ۳ گانه کیفی:
        ۱. تایید گسکت دائم و نو
        ۲. عاری بودن داخل تجهیز از هرگونه ابزار، گرد و غبار یا زنگار
        ۳. گشتاور و آچارکشی اصولی پیچ‌ها (Torque Complete)
        """
        is_ready = gasket_type_verified and internals_cleaned and bolts_tightened
        status_val = "Completed" if is_ready else "Draft"

        record = self.boxup.add(
            project_id=project_id,
            item_tag=item_tag.strip().upper(),
            item_type=item_type.strip().upper(),
            gasket_verified=gasket_type_verified,
            cleanliness_verified=internals_cleaned,
            torquing_verified=bolts_tightened,
            inspector_name=inspector_name.strip(),
            status=status_val,
            created_at=datetime.utcnow(),
        )
        self.session.commit()
        return record

    def complete_boxup(self, boxup_id: int, witness: str) -> None:
        """تایید نهایی و پلمپ امضا شده باکس‌آپ با متد مدرن session.get"""
        record = self.session.get(BoxUpRecord, boxup_id)
        if not record:
            raise ValueError(f"BoxUp record #{boxup_id} not found.")

        if not (record.gasket_verified and record.cleanliness_verified and record.torquing_verified):
            raise PreCommValidationError(f"Cannot complete Box-Up #{boxup_id}: Quality checklist is incomplete!")

        record.status = "Completed"
        record.witness_signature = witness.strip()
        record.completion_date = datetime.utcnow()
        self.session.commit()
        logger.info(f"BoxUp for '{record.item_tag}' officially completed and sealed by {witness}.")

    # Implementation note.

    def record_spring_hanger_status(
        self,
        project_id: int,
        support_tag: str,
        line_number: str,
        operating_state: Union[SpringHangerState, str],
        travel_stop_removed: bool,
        cold_setting_mm: float,
        actual_reading_mm: float,
        inspector_name: str,
    ) -> SpringHangerRecord:
        """
        ثبت وضعیت ساپورت فنری:
        - ردیابی بازشدن پین‌های موقت مسافرتی (Travel Stop Pins) قبل از استارت‌آپ داغ واحد.
        - پایش میزان انحراف موقعیت فیزیکی از نقشه طراحی (Cold/Hot Settings).
        """
        state_val = operating_state.value if isinstance(operating_state, SpringHangerState) else str(operating_state).strip().upper()

        # Implementation note.
        deviation = abs(actual_reading_mm - cold_setting_mm)
        if travel_stop_removed and deviation > 5.0:  # Implementation note.
            logger.warning(f"Spring Hanger '{support_tag}' has high deviation: {deviation} mm from design cold setting!")

        record = self.spring.add(
            project_id=project_id,
            support_tag=support_tag.strip().upper(),
            line_number=line_number.strip().upper(),
            operating_state=state_val,
            travel_stop_removed=travel_stop_removed,
            design_cold_setting=cold_setting_mm,
            actual_reading=actual_reading_mm,
            inspector_name=inspector_name.strip(),
            verification_date=date.today(),
            created_at=datetime.utcnow(),
        )
        self.session.commit()
        return record

    # Implementation note.

    def record_preservation_task(
        self,
        project_id: int,
        equipment_tag: str,
        preservation_activity: str,  # Shaft Rotation, Nitrogen Blanketing, Greasing
        periodicity: Union[PreservationPeriod, str],
        inspector_name: str,
        next_due_days: int = 30,
        remarks: str = "",
    ) -> MaterialPreservationRecord:
        """ثبت اجرای فعالیت نگهداری ادواری تجهیزات و محاسبه هوشمند موعد بعدی (Due Date)"""
        p_val = periodicity.value if isinstance(periodicity, PreservationPeriod) else str(periodicity).strip().upper()
        today = date.today()
        next_due = today + timedelta(days=next_due_days)

        record = self.preservation.add(
            project_id=project_id,
            equipment_tag=equipment_tag.strip().upper(),
            activity=preservation_activity.strip(),
            periodicity=p_val,
            last_checked_date=today,
            next_due_date=next_due,
            inspector_name=inspector_name.strip(),
            remarks=remarks.strip(),
            status="Active",
            created_at=datetime.utcnow(),
        )
        self.session.commit()
        logger.info(f"Preservation recorded for '{equipment_tag}'. Next due date: {next_due}")
        return record

    def get_overdue_preservation_alerts(self, project_id: int) -> List[Dict[str, Any]]:
        """شناسایی و استخراج سریع تجهیزاتی که موعد نگهداری ادواری آن‌ها منقضی شده است"""
        today = date.today()
        overdue_items = (
            self.session.query(MaterialPreservationRecord)
            .filter(
                MaterialPreservationRecord.project_id == project_id,
                MaterialPreservationRecord.status == "Active",
                MaterialPreservationRecord.next_due_date < today,
            )
            .order_by(asc(MaterialPreservationRecord.next_due_date))
            .all()
        )

        return [
            {
                "id": item.id,
                "equipment_tag": item.equipment_tag,
                "activity": item.activity,
                "next_due_date": item.next_due_date.isoformat(),
                "days_overdue": (today - item.next_due_date).days,
                "inspector": item.inspector_name,
            }
            for item in overdue_items
        ]

    # Implementation note.

    def get_precomm_dashboard(self, project_id: int) -> Dict[str, Any]:
        """
        محاسبه شاخص‌های آماری پیش‌راه‌اندازی با توابع تجمعی مستقیم دیتابیس (بدون لود دیتا در RAM)
        """
        # Implementation note.
        flush_stats = self.session.query(
            func.count(FlushingRecord.id).label("total"),
            func.sum(case((FlushingRecord.result == "Accept", 1), else_=0)).label("passed"),
        ).filter(FlushingRecord.project_id == project_id).first()

        # Implementation note.
        leak_stats = self.session.query(
            func.count(LeakTestRecord.id).label("total"),
            func.sum(case((LeakTestRecord.result == "Accept", 1), else_=0)).label("passed"),
        ).filter(LeakTestRecord.project_id == project_id).first()

        # Implementation note.
        boxup_stats = self.session.query(
            func.count(BoxUpRecord.id).label("total"),
            func.sum(case((BoxUpRecord.status == "Completed", 1), else_=0)).label("completed"),
        ).filter(BoxUpRecord.project_id == project_id).first()

        # Implementation note.
        pmi_stats = self.session.query(
            func.count(PMITestRecord.id).label("total"),
            func.sum(case((PMITestRecord.result == "Reject", 1), else_=0)).label("rejected"),
        ).filter(PMITestRecord.project_id == project_id).first()

        # Implementation note.
        spring_stats = self.session.query(
            func.count(SpringHangerRecord.id).label("total"),
            func.sum(case((SpringHangerRecord.travel_stop_removed == True, 1), else_=0)).label("pins_removed"),
        ).filter(SpringHangerRecord.project_id == project_id).first()

        flush_total = flush_stats.total or 0
        flush_passed = flush_stats.passed or 0
        leak_total = leak_stats.total or 0
        leak_passed = leak_stats.passed or 0

        return {
            "project_id": project_id,
            "timestamp": datetime.utcnow().isoformat(),
            "flushing": {
                "total_lines_flushed": flush_total,
                "passed_lines": flush_passed,
                "progress_pct": round((flush_passed / flush_total * 100), 2) if flush_total > 0 else 0.0,
            },
            "leak_testing": {
                "total_tests_conducted": leak_total,
                "passed_tests": leak_passed,
                "progress_pct": round((leak_passed / leak_total * 100), 2) if leak_total > 0 else 0.0,
            },
            "equipment_boxup": {
                "total_boxup_requested": boxup_stats.total or 0,
                "completed_and_sealed": boxup_stats.completed or 0,
                "pending_sealing": (boxup_stats.total or 0) - (boxup_stats.completed or 0),
            },
            "pmi_chemical_testing": {
                "total_spectro_tests": pmi_stats.total or 0,
                "rejected_lots_count": pmi_stats.rejected or 0,
            },
            "spring_hangers": {
                "total_hangers_verified": spring_stats.total or 0,
                "travel_stops_unlocked": spring_stats.pins_removed or 0,
                "pending_unlock_count": (spring_stats.total or 0) - (spring_stats.pins_removed or 0),
            },
        }

    # Implementation note.

    def record_pmi(self, project_id: int, **kwargs) -> PMITestRecord:
        record = self.pmi.add(project_id=project_id, **kwargs)
        self.session.commit()
        return record

    def record_dimensional(self, project_id: int, **kwargs) -> DimensionalCheckRecord:
        record = self.dimensional.add(project_id=project_id, **kwargs)
        self.session.commit()
        return record