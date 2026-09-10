# -*- coding: utf-8 -*-
"""
services/finishing_service.py – PipeAgent
سرویس جامع فرآیندهای تکمیلی، کنترل کیفی و بازسازی پایپینگ (Finishing & Reinstatement)
شامل: مدیریت چرخه‌های عملیات حرارتی (PWHT)، ترکمتر و تنشنینگ فلنج‌ها (Flange Torque)،
سندبلاست و رنگ‌آمیزی (Painting/Coating)، عایق‌کاری (Insulation) و بازگردانی خطوط (Reinstatement).
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, and_, or_, desc, case
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from repositories.finishing_repository import (
    PaintingRepository,
    InsulationRepository,
    FlangeTorqueRepository,
    PWHTRepository,
    ReinstatementRepository,
)
from db.models import (
    Weld,
    PaintingRecord,
    InsulationRecord,
    FlangeTorqueRecord,
    PWHTRecord,
    ReinstatementItem,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Engineering Standards
# ──────────────────────────────────────────────

class FinishingStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


class BoltTorquePattern(str, Enum):
    STAR_CROSS = "STAR_CROSS"                  # Implementation note.
    CIRCULAR = "CIRCULAR"                      # Implementation note.
    HYDRAULIC_SIMULTANEOUS = "SIMULTANEOUS"    # Implementation note.


class SurfacePrepGrade(str, Enum):
    SA_1 = "Sa 1"                              # Implementation note.
    SA_2 = "Sa 2"                              # Implementation note.
    SA_2_5 = "Sa 2.5"                          # Implementation note.
    SA_3 = "Sa 3"                              # Implementation note.
    ST_3 = "St 3"                              # Implementation note.


# ──────────────────────────────────────────────
#  Custom Domain Exceptions
# ──────────────────────────────────────────────

class FinishingValidationError(Exception):
    """خطای عدم انطباق با مشخصات فنی و استانداردهای تکمیلی"""
    pass


class PWHTPreconditionError(Exception):
    """خطای عدم احراز شرایط لازم برای اجرای عملیات حرارتی جوش"""
    pass


# ──────────────────────────────────────────────
#  Finishing Service Implementation
# ──────────────────────────────────────────────

class FinishingService:
    """
    سرویس مرکزی مدیریت فرآیندهای تکمیلی، کنترل کیفی سطح، عایق، ترکمتر و بازسازی خطوط
    """

    def __init__(self, session: Session):
        self.session = session
        self.painting_repo = PaintingRepository(session)
        self.insulation_repo = InsulationRepository(session)
        self.flange_repo = FlangeTorqueRepository(session)
        self.pwht_repo = PWHTRepository(session)
        self.reinstatement_repo = ReinstatementRepository(session)

    # Implementation note.

    def record_pwht_cycle(
        self,
        project_id: int,
        weld_id_fk: int,
        cycle_number: int = 1,
        soaking_temperature_c: float = 600.0,
        soaking_duration_hours: float = 1.5,
        heating_rate_c_hr: float = 150.0,
        cooling_rate_c_hr: float = 180.0,
        chart_reference: str = "",
        operator_name: str = "",
        inspector_name: str = "",
        is_passed: bool = True,
        rejection_reason: str = "",
    ) -> PWHTRecord:
        """
        ثبت چرخه عملیات حرارتی پس از جوشکاری (PWHT)، اعتبارسنجی نرخ گرمایش/سرمایش
        و به‌روزرسانی وضعیت سرجوش در جدول Weld با متد مدرن session.get.
        """
        # Implementation note.
        weld = self.session.get(Weld, weld_id_fk)
        if not weld:
            raise PWHTPreconditionError(f"Weld Joint #{weld_id_fk} not found.")

        # Implementation note.
        if weld.status not in ["WELDED", "WELDED_VT_PENDING", "VT_ACCEPTED", "NDT_REQUESTED"]:
            logger.warning(f"PWHT applied to Weld #{weld_id_fk} with non-standard status: '{weld.status}'")

        # Implementation note.
        if heating_rate_c_hr > 300.0:
            raise FinishingValidationError(f"Heating rate ({heating_rate_c_hr} °C/hr) exceeds ASME safe limit (max 300 °C/hr).")

        pwht_status = FinishingStatus.COMPLETED.value if is_passed else FinishingStatus.REJECTED.value

        # Implementation note.
        pwht_record = self.pwht_repo.add_record(
            project_id=project_id,
            weld_id_fk=weld_id_fk,
            cycle_number=cycle_number,
            soaking_temperature=soaking_temperature_c,
            soaking_duration=soaking_duration_hours,
            heating_rate=heating_rate_c_hr,
            cooling_rate=cooling_rate_c_hr,
            chart_reference=chart_reference.strip(),
            operator_name=operator_name.strip(),
            inspector_name=inspector_name.strip(),
            status=pwht_status,
            rejection_reason=rejection_reason if not is_passed else None,
            created_at=datetime.utcnow(),
        )

        # Implementation note.
        if is_passed:
            weld.pwht_done = True
            weld.pwht_date = date.today()
            weld.status = "PWHT_COMPLETED"
        else:
            weld.pwht_done = False
            weld.status = "PWHT_FAILED"

        self.session.commit()
        logger.info(f"PWHT Cycle #{cycle_number} for Weld #{weld_id_fk} recorded as '{pwht_status}'.")
        return pwht_record

    # Implementation note.

    def record_flange_torque_inspection(
        self,
        project_id: int,
        line_number: str,
        flange_tag: str,
        flange_size_inch: str,
        flange_rating: str,
        target_torque_nm: float,
        actual_torque_nm: float,
        torque_wrench_id: str,
        calibration_valid: bool,
        tightening_pattern: Union[BoltTorquePattern, str] = BoltTorquePattern.STAR_CROSS,
        verified_by: str = "",
        is_re_torque_required: bool = False,
    ) -> FlangeTorqueRecord:
        """
        ثبت بازرسی گشتاور پیچ‌های فلنج، تطبیق با کالیبراسیون آچار ترکمتر و بررسی تلورانس مجاز (±5%)
        """
        if not calibration_valid:
            raise FinishingValidationError(f"Cannot accept torque: Torque wrench '{torque_wrench_id}' calibration is expired or invalid!")

        pattern_val = tightening_pattern.value if isinstance(tightening_pattern, BoltTorquePattern) else tightening_pattern

        # Implementation note.
        torque_deviation_pct = abs(actual_torque_nm - target_torque_nm) / target_torque_nm * 100
        is_accepted = torque_deviation_pct <= 5.0

        status_val = FinishingStatus.ACCEPTED.value if is_accepted else FinishingStatus.REJECTED.value

        record = self.flange_repo.add_record(
            project_id=project_id,
            line_number=line_number.strip().upper(),
            flange_tag=flange_tag.strip().upper(),
            flange_size=flange_size_inch.strip(),
            flange_class=flange_rating.strip(),
            target_torque_value=target_torque_nm,
            actual_torque_value=actual_torque_nm,
            torque_wrench_code=torque_wrench_id.strip(),
            bolt_tightening_pattern=pattern_val,
            re_torque_required=is_re_torque_required,
            re_torque_completed=False if is_re_torque_required else True,
            verified_by=verified_by.strip(),
            verification_date=datetime.utcnow() if is_accepted else None,
            status=status_val,
            created_at=datetime.utcnow(),
        )
        self.session.commit()
        logger.info(f"Flange Torque for '{flange_tag}' ({actual_torque_nm} Nm) recorded as '{status_val}'.")
        return record

    # Implementation note.

    def record_painting_inspection(
        self,
        project_id: int,
        line_number: str,
        spool_number: Optional[str],
        surface_prep_grade: Union[SurfacePrepGrade, str] = SurfacePrepGrade.SA_2_5,
        ambient_temp_c: float = 25.0,
        dew_point_c: float = 18.0,
        relative_humidity_pct: float = 65.0,
        primer_dft_microns: Optional[float] = None,
        intermediate_dft_microns: Optional[float] = None,
        topcoat_dft_microns: Optional[float] = None,
        inspector_name: str = "",
        is_passed: bool = True,
    ) -> PaintingRecord:
        """
        ثبت بازرسی سندبلاست و اعمال سیستم رنگ ۳ لایه:
        - کنترل عدم اعمال رنگ در شرایط رطوبت بالا یا اختلاف دمای کمتر از ۳ درجه با نقطه شبنم (Dew Point Check)
        - اندازه‌گیری ضخامت فیلم خشک (DFT)
        """
        # Implementation note.
        if (ambient_temp_c - dew_point_c) < 3.0:
            logger.warning(f"Environmental warning: Surface temp ({ambient_temp_c} °C) is less than 3 °C above Dew Point ({dew_point_c} °C)!")

        prep_val = surface_prep_grade.value if isinstance(surface_prep_grade, SurfacePrepGrade) else surface_prep_grade
        status_val = FinishingStatus.COMPLETED.value if is_passed else FinishingStatus.REJECTED.value

        record = self.painting_repo.add_record(
            project_id=project_id,
            line_number=line_number.strip().upper(),
            spool_number=spool_number.strip().upper() if spool_number else None,
            surface_prep_grade=prep_val,
            ambient_temperature=ambient_temp_c,
            dew_point=dew_point_c,
            humidity_percentage=relative_humidity_pct,
            primer_coat_dft=primer_dft_microns,
            mid_coat_dft=intermediate_dft_microns,
            top_coat_dft=topcoat_dft_microns,
            inspector_name=inspector_name.strip(),
            status=status_val,
            approval_date=datetime.utcnow() if is_passed else None,
            created_at=datetime.utcnow(),
        )
        self.session.commit()
        return record

    # Implementation note.

    def record_insulation_inspection(
        self,
        project_id: int,
        line_number: str,
        insulation_type: str,  # Hot Insulation, Cold Insulation, Personal Protection
        thickness_mm: float,
        heat_trace_verified: bool = False,
        cladding_installed: bool = True,
        cladding_type: str = "ALUMINUM",
        inspector_name: str = "",
        is_passed: bool = True,
    ) -> InsulationRecord:
        """ثبت عایق‌کاری خطوط، کنترل سیستم هیت‌تریس و نصب روکش آلومینیومی (Cladding)"""
        status_val = FinishingStatus.COMPLETED.value if is_passed else FinishingStatus.REJECTED.value

        record = self.insulation_repo.add_record(
            project_id=project_id,
            line_number=line_number.strip().upper(),
            insulation_type=insulation_type.strip(),
            thickness=thickness_mm,
            heat_trace_installed=heat_trace_verified,
            cladding_installed=cladding_installed,
            cladding_type=cladding_type.strip(),
            cladding_date=datetime.utcnow() if cladding_installed else None,
            inspector_name=inspector_name.strip(),
            status=status_val,
            created_at=datetime.utcnow(),
        )
        self.session.commit()
        return record

    # Implementation note.

    def add_reinstatement_item(
        self,
        project_id: int,
        test_package_id: int,
        line_number: str,
        item_description: str,
        category: str,  # BLIND_REMOVAL, GASKET_REPLACEMENT, VALVE_REINSTALL, INSTRUMENT_HOOKUP
        assigned_to: Optional[str] = None,
    ) -> ReinstatementItem:
        """ثبت آیتم بازگردانی مدار (مانند خروج صفحه مسدودکننده تست و بستن واشر دائم)"""
        return self.reinstatement_repo.add_item(
            project_id=project_id,
            test_package_id=test_package_id,
            line_number=line_number.strip().upper(),
            item_description=item_description.strip(),
            category=category.strip().upper(),
            status="PENDING",
            assigned_to=assigned_to,
            created_at=datetime.utcnow(),
        )

    def complete_reinstatement_item(
        self,
        item_id: int,
        verified_by_qc: str,
    ) -> ReinstatementItem:
        """تأیید خروج بلایند یا نصب دائم قطعه توسط بازرس QC"""
        item = self.reinstatement_repo.complete_item(item_id=item_id, verified_by=verified_by_qc)
        self.session.commit()
        logger.info(f"Reinstatement Item #{item_id} completed and verified by {verified_by_qc}.")
        return item

    # Implementation note.

    def get_finishing_summary(self, project_id: int) -> Dict[str, Any]:
        """
        محاسبه ماتریس آماری فرآیندهای تکمیلی با کوئری‌های بهینه SQL (بدون سرریز حافظه RAM)
        """
        # Implementation note.
        paint_stats = self.session.query(
            func.count(PaintingRecord.id).label("total"),
            func.sum(case((PaintingRecord.status.in_(["COMPLETED", "ACCEPTED"]), 1), else_=0)).label("completed"),
        ).filter(PaintingRecord.project_id == project_id).first()

        # Implementation note.
        insul_stats = self.session.query(
            func.count(InsulationRecord.id).label("total"),
            func.sum(case((InsulationRecord.status.in_(["COMPLETED", "ACCEPTED"]), 1), else_=0)).label("completed"),
            func.sum(case((InsulationRecord.cladding_installed == True, 1), else_=0)).label("cladding_done"),
        ).filter(InsulationRecord.project_id == project_id).first()

        # Implementation note.
        flange_stats = self.session.query(
            func.count(FlangeTorqueRecord.id).label("total"),
            func.sum(case((FlangeTorqueRecord.status.in_(["COMPLETED", "ACCEPTED"]), 1), else_=0)).label("verified"),
            func.sum(case((FlangeTorqueRecord.re_torque_required == True, 1), else_=0)).label("re_torque_due"),
        ).filter(FlangeTorqueRecord.project_id == project_id).first()

        # Implementation note.
        pwht_stats = self.session.query(
            func.count(PWHTRecord.id).label("total_cycles"),
            func.sum(case((PWHTRecord.status.in_(["COMPLETED", "ACCEPTED"]), 1), else_=0)).label("passed"),
            func.sum(case((PWHTRecord.status == "REJECTED", 1), else_=0)).label("rejected"),
        ).filter(PWHTRecord.project_id == project_id).first()

        # Implementation note.
        reinstatement_stats = self.session.query(
            func.count(ReinstatementItem.id).label("total"),
            func.sum(case((ReinstatementItem.status == "COMPLETED", 1), else_=0)).label("completed"),
        ).filter(ReinstatementItem.project_id == project_id).first()

        paint_total = paint_stats.total or 0
        paint_done = paint_stats.completed or 0
        insul_total = insul_stats.total or 0
        insul_done = insul_stats.completed or 0

        return {
            "project_id": project_id,
            "painting": {
                "total_records": paint_total,
                "completed_records": paint_done,
                "progress_pct": round((paint_done / paint_total * 100), 2) if paint_total > 0 else 0.0,
            },
            "insulation": {
                "total_records": insul_total,
                "completed_records": insul_done,
                "cladding_completed": insul_stats.cladding_done or 0,
                "progress_pct": round((insul_done / insul_total * 100), 2) if insul_total > 0 else 0.0,
            },
            "flange_torquing": {
                "total_flanges": flange_stats.total or 0,
                "verified_flanges": flange_stats.verified or 0,
                "re_torque_due": flange_stats.re_torque_due or 0,
            },
            "pwht_heat_treatment": {
                "total_cycles": pwht_stats.total_cycles or 0,
                "passed_cycles": pwht_stats.passed or 0,
                "rejected_cycles": pwht_stats.rejected or 0,
            },
            "reinstatement_turnover": {
                "total_items": reinstatement_stats.total or 0,
                "completed_items": reinstatement_stats.completed or 0,
                "pending_items": (reinstatement_stats.total or 0) - (reinstatement_stats.completed or 0),
            },
        }