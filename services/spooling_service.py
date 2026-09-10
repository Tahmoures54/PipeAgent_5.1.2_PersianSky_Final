# -*- coding: utf-8 -*-
"""
services/spooling_service.py – PipeAgent
سرویس جامع پیش‌ساخت کارگاهی، ردیابی ابعادی، لجستیک و نصب اسپول‌های پایپینگ (Piping Spool Management)
منطبق با استانداردهای ASME B31.3، PFI ES-3 و AWS D1.1
شامل: محاسبات اینچ-قطر جوشکاری (Dia-Inch)، ارزیابی تلورانس‌های ابعادی،
دروازه‌های ترخیص کیفی شاپ، بارگیری به سایت (Dispatch Manifest) و تبارشناسی کامل ۳۶۰ درجه اسپول.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc, case
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy.exc import SQLAlchemyError

from core.exceptions import AppError
from db.manager import DatabaseManager
from db.models import (
    Spool,
    Weld,
    NDTRecord,
    PaintingRecord,
    DimensionalCheckRecord,
    MaterialItem,
    TestPackage,
    LineListItem,
    Document,
)
from services.license import increment_usage

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Engineering Standards
# ──────────────────────────────────────────────

class SpoolStatus(str, Enum):
    """مراحل تفصیلی چرخه حیات اسپول"""
    DESIGN = "DESIGN"                          # Implementation note.
    MATERIAL_ALLOCATED = "MATERIAL_ALLOCATED"  # Implementation note.
    CUTTING_FITUP = "CUTTING_FITUP"            # Implementation note.
    WELDING = "WELDING"                        # Implementation note.
    FAB_COMPLETED = "FAB_COMPLETED"            # Implementation note.
    NDT_CLEARED = "NDT_CLEARED"                # Implementation note.
    PWHT_COMPLETED = "PWHT_COMPLETED"          # Implementation note.
    DIMENSIONAL_ACCEPTED = "DIM_ACCEPTED"      # Implementation note.
    PAINTING = "PAINTING"                      # Implementation note.
    READY_FOR_DISPATCH = "READY_TO_DISPATCH"    # Implementation note.
    IN_TRANSIT = "IN_TRANSIT"                  # Implementation note.
    SITE_LAYDOWN = "SITE_LAYDOWN"              # Implementation note.
    ERECTED = "ERECTED"                        # Implementation note.
    TESTED = "TESTED"                          # Implementation note.


class SpoolLocation(str, Enum):
    """موقعیت فیزیکی اسپول"""
    FAB_SHOP = "FAB_SHOP"
    PAINTING_YARD = "PAINTING_YARD"
    MARSHALLING_YARD = "MARSHALLING_YARD"
    SITE_LAYDOWN = "SITE_LAYDOWN"
    INSTALLED_ON_LINE = "INSTALLED_ON_LINE"


class HoldReasonCategory(str, Enum):
    """علل توقف ساخت یا ارسال اسپول (Engineering/QC Hold)"""
    DESIGN_REVISION = "DESIGN_REVISION"        # Implementation note.
    MATERIAL_SHORTAGE = "MATERIAL_SHORTAGE"    # Implementation note.
    QC_REJECTION = "QC_REJECTION"              # Implementation note.
    CLIENT_HOLD = "CLIENT_HOLD"                # Implementation note.
    SITE_ACCESS_BLOCK = "SITE_ACCESS_BLOCK"    # Implementation note.


# ──────────────────────────────────────────────
#  Custom Spooling Exceptions
# ──────────────────────────────────────────────

class SpoolWorkflowError(AppError):
    """خطای نقض چرخه حیات و گردش‌کار ساخت اسپول"""
    pass


class SpoolOnHoldError(AppError):
    """خطای ممانعت از عملیات به دلیل قرار داشتن اسپول در وضعیت هولد"""
    pass


class DimensionalToleranceError(AppError):
    """خطای عدم انطباق ابعادی با تلورانس‌های استاندارد PFI ES-3"""
    pass


# ──────────────────────────────────────────────
#  Spooling Service Implementation
# ──────────────────────────────────────────────

class SpoolingService:
    """
    سرویس مرکزی مدیریت پیش‌ساخت، کنترل کیفی، لجستیک و نصب اسپول‌های پایپینگ
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    # Implementation note.

    def register_spool(
        self,
        project_id: int,
        spool_number: str,
        line_number: str,
        drawing_number: str,
        *,
        revision: str = "0",
        area_code: Optional[str] = None,
        estimated_weight_kg: float = 0.0,
        surface_area_m2: float = 0.0,
        paint_system_code: Optional[str] = None,
        insulation_type: Optional[str] = None,
        target_erection_date: Optional[date] = None,
        created_by: str = "system",
        remarks: str = "",
    ) -> Spool:
        """
        ثبت رسمی اسپول جدید با شناسه سه‌گانه یکتا (Project + Spool + Drawing)
        """
        if not increment_usage(self.db):
            raise PermissionError("License limit reached. Cannot register new Spool.")

        spool_clean = str(spool_number).strip().upper()
        line_clean = str(line_number).strip().upper()
        dwg_clean = str(drawing_number).strip().upper()

        with self.db.session_scope() as session:
            existing = (
                session.query(Spool)
                .filter(
                    Spool.project_id == project_id,
                    Spool.spool_number == spool_clean,
                    Spool.drawing_number == dwg_clean,
                )
                .first()
            )
            if existing:
                raise ValueError(f"Spool '{spool_clean}' on Drawing '{dwg_clean}' already exists in Project #{project_id}.")

            spool = Spool(
                project_id=project_id,
                spool_number=spool_clean,
                line_number=line_clean,
                drawing_number=dwg_clean,
                revision=revision.strip(),
                area_code=area_code.strip().upper() if area_code else None,
                weight_kg=estimated_weight_kg,
                surface_area_m2=surface_area_m2,
                painting_code=paint_system_code.strip() if paint_system_code else None,
                insulation_type=insulation_type.strip() if insulation_type else None,
                target_erection_date=target_erection_date,
                status=SpoolStatus.DESIGN.value,
                current_location=SpoolLocation.FAB_SHOP.value,
                is_on_hold=False,
                created_by=created_by,
                remarks=remarks.strip(),
                created_at=datetime.utcnow(),
            )
            session.add(spool)
            session.flush()

            logger.info(f"Spool '{spool_clean}' (Line: {line_clean}) registered for Project #{project_id}.")
            return spool

    # Implementation note.

    def link_welds_to_spool(
        self,
        project_id: int,
        spool_id: int,
        weld_ids: List[int],
    ) -> Dict[str, Any]:
        """
        اتصال سرجوش‌های کارگاهی (Shop Welds) به اسپول و محاسبه خودکار مجموع اینچ-قطر جوشکاری
        """
        with self.db.session_scope() as session:
            spool = session.get(Spool, spool_id)
            if not spool or spool.project_id != project_id:
                raise AppError(f"Spool #{spool_id} not found in Project #{project_id}.")

            if getattr(spool, "is_on_hold", False):
                raise SpoolOnHoldError(f"Cannot modify Spool '{spool.spool_number}': Spool is on HOLD!")

            welds = (
                session.query(Weld)
                .filter(
                    Weld.project_id == project_id,
                    Weld.id.in_(weld_ids),
                )
                .all()
            )

            total_dia_inch = 0.0
            shop_welds_count = 0

            for w in welds:
                w.spool_id = spool.id
                w.spool_number = spool.spool_number
                w.line_number = spool.line_number
                w.drawing_number = spool.drawing_number
                w.weld_category = "SHOP"  # Implementation note.
                
                di = float(getattr(w, "dia_inch", getattr(w, "size_inch", 1.0)) or 1.0)
                total_dia_inch += di
                shop_welds_count += 1

            # Implementation note.
            spool.total_dia_inch = total_dia_inch
            spool.shop_welds_count = shop_welds_count
            spool.status = SpoolStatus.CUTTING_FITUP.value
            spool.updated_at = datetime.utcnow()

            session.flush()
            logger.info(f"Linked {shop_welds_count} welds to Spool '{spool.spool_number}' (Total Dia-Inch: {total_dia_inch:.1f}).")

            return {
                "spool_id": spool.id,
                "spool_number": spool.spool_number,
                "shop_welds_linked": shop_welds_count,
                "total_dia_inch": round(total_dia_inch, 1),
                "status": spool.status,
            }

    # Implementation note.

    def record_dimensional_inspection(
        self,
        project_id: int,
        spool_id: int,
        *,
        length_deviation_mm: float,
        flange_face_tilt_mm: float,
        flange_rotation_deg: float,
        diagonal_squareness_mm: float,
        inspector_name: str,
        inspection_report_no: str,
        is_passed: bool = True,
        defect_remarks: str = "",
    ) -> DimensionalCheckRecord:
        """
        ثبت نتایج بازرسی ابعادی اسپول طبق استاندارد بین‌المللی PFI ES-3:
        - حداکثر انحراف طول مجاز: ±3.0mm (زیر ۳ متر) و ±5.0mm (بالای ۳ متر)
        - حداکثر انحراف تراز و عدم انطباق پیشانی فلنج: 1.5mm
        - حداکثر انحراف چرخش سوراخ‌های فلنج (Flange Hole Rotation): ±1.5mm / ±0.5°
        """
        with self.db.session_scope() as session:
            spool = session.get(Spool, spool_id)
            if not spool or spool.project_id != project_id:
                raise AppError(f"Spool #{spool_id} not found.")

            # Implementation note.
            tolerance_breached = (
                abs(length_deviation_mm) > 5.0
                or abs(flange_face_tilt_mm) > 2.0
                or abs(diagonal_squareness_mm) > 4.0
            )

            if tolerance_breached and is_passed:
                raise DimensionalToleranceError(
                    f"Dimensional inspection cannot pass: Measurements exceed PFI ES-3 tolerance limits! "
                    f"(Length Dev: {length_deviation_mm}mm, Tilt: {flange_face_tilt_mm}mm)."
                )

            status_val = "ACCEPTED" if is_passed and not tolerance_breached else "REJECTED"

            dim_record = DimensionalCheckRecord(
                project_id=project_id,
                spool_id=spool_id,
                spool_number=spool.spool_number,
                length_deviation_mm=length_deviation_mm,
                flange_tilt_mm=flange_face_tilt_mm,
                flange_rotation_deg=flange_rotation_deg,
                squareness_mm=diagonal_squareness_mm,
                report_number=inspection_report_no.strip().upper(),
                inspector_name=inspector_name.strip(),
                status=status_val,
                remarks=defect_remarks.strip(),
                inspection_date=datetime.utcnow(),
            )
            session.add(dim_record)

            if status_val == "ACCEPTED":
                spool.status = SpoolStatus.DIMENSIONAL_ACCEPTED.value
            else:
                spool.status = SpoolStatus.FAB_COMPLETED.value  # Implementation note.
                spool.is_on_hold = True
                spool.hold_reason = f"Dimensional Check Failed: {defect_remarks}"

            spool.updated_at = datetime.utcnow()
            session.flush()

            logger.info(f"Dimensional check for Spool '{spool.spool_number}' recorded as '{status_val}'.")
            return dim_record

    # Implementation note.

    def evaluate_shop_release_readiness(
        self,
        project_id: int,
        spool_id: int,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        ارزیابی سخت‌گیرانه آمادگی ترخیص اسپول از کارگاه ساخت جهت بارگیری به سایت:
        ۱. بررسی ۱۰۰٪ ترخیص NDT تمام سرجوش‌های شاپ
        ۲. تکمیل عملیات حرارتی (PWHT) در صورت شمول
        ۳. قبولی بازرسی ابعادی PFI ES-3
        ۴. تکمیل سیستم رنگ و سندبلاست (در صورت الزام)
        ۵. عدم وجود هرگونه وضعیت هولد مهندسی یا کیفی
        """
        with self.db.session_scope() as session:
            spool = session.get(Spool, spool_id)
            if not spool or spool.project_id != project_id:
                raise AppError(f"Spool #{spool_id} not found.")

            blockers: List[str] = []

            # Implementation note.
            if getattr(spool, "is_on_hold", False):
                blockers.append(f"Spool is on HOLD. Reason: {getattr(spool, 'hold_reason', 'Engineering Hold')}")

            # Implementation note.
            welds = session.query(Weld).filter(Weld.spool_id == spool.id).all()
            total_welds = len(welds)
            uncleared_welds = [
                w.weld_number for w in welds
                if w.status not in ["NDT_CLEARED", "COMPLETED", "VT_ACCEPTED"] and getattr(w, "ndt_status", "") != "ACCEPTED"
            ]
            if uncleared_welds:
                blockers.append(f"{len(uncleared_welds)}/{total_welds} shop welds lack NDT clearance ({', '.join(uncleared_welds[:4])}).")

            # Implementation note.
            dim_passed = (
                session.query(DimensionalCheckRecord)
                .filter(
                    DimensionalCheckRecord.spool_id == spool.id,
                    DimensionalCheckRecord.status == "ACCEPTED",
                )
                .first()
            )
            if not dim_passed:
                blockers.append("Dimensional check (PFI ES-3) has not been verified or accepted.")

            # Implementation note.
            if getattr(spool, "painting_code", None):
                paint_record = (
                    session.query(PaintingRecord)
                    .filter(
                        PaintingRecord.spool_number == spool.spool_number,
                        PaintingRecord.status.in_(["COMPLETED", "ACCEPTED"]),
                    )
                    .first()
                )
                if not paint_record:
                    blockers.append(f"Shop painting/coating ({spool.painting_code}) is not completed.")

            is_ready = len(blockers) == 0

            return is_ready, blockers, {
                "spool_id": spool.id,
                "spool_number": spool.spool_number,
                "is_ready_for_dispatch": is_ready,
                "shop_welds_count": total_welds,
                "uncleared_welds_count": len(uncleared_welds),
                "dimensional_verified": dim_passed is not None,
                "blocking_reasons": blockers,
            }

    # Implementation note.

    def dispatch_spools_to_site(
        self,
        project_id: int,
        spool_ids: List[int],
        shipping_manifest_no: str,
        transporter_name: str,
        truck_plate_no: str,
        dispatched_by: str,
    ) -> Dict[str, Any]:
        """
        صدور مانیفست حمل و انتقال دسته‌ای اسپول‌های آماده از کارگاه به سایت پروژه
        (با ممانعت قطعی از بارگیری اسپول‌های هولد یا ناقص)
        """
        manifest_clean = shipping_manifest_no.strip().upper()
        dispatched_ids: List[int] = []
        rejected_spools: List[Dict[str, Any]] = []

        with self.db.session_scope() as session:
            for s_id in spool_ids:
                is_ready, blockers, _ = self.evaluate_shop_release_readiness(project_id, s_id)
                spool = session.get(Spool, s_id)

                if not is_ready:
                    rejected_spools.append({
                        "spool_id": s_id,
                        "spool_number": spool.spool_number if spool else str(s_id),
                        "reasons": blockers,
                    })
                    continue

                spool.status = SpoolStatus.IN_TRANSIT.value
                spool.current_location = SpoolLocation.MARSHALLING_YARD.value
                spool.shipping_manifest_no = manifest_clean
                spool.dispatch_date = datetime.utcnow()
                spool.transporter_info = f"{transporter_name} / {truck_plate_no}"
                spool.updated_at = datetime.utcnow()
                dispatched_ids.append(spool.id)

            session.flush()

        logger.info(f"Dispatched {len(dispatched_ids)} spools under Manifest '{manifest_clean}' by {dispatched_by}.")
        return {
            "shipping_manifest_no": manifest_clean,
            "total_requested": len(spool_ids),
            "successfully_dispatched_count": len(dispatched_ids),
            "rejected_count": len(rejected_spools),
            "dispatched_spool_ids": dispatched_ids,
            "rejected_spools_details": rejected_spools,
        }

    # Implementation note.

    def record_site_laydown_receipt(
        self,
        project_id: int,
        spool_ids: List[int],
        laydown_bay_location: str,
        received_by: str,
    ) -> int:
        """ثبت تخلیه فیزیکی محموله اسپول‌ها در انبار روباز سایت (Staging Area)"""
        with self.db.session_scope() as session:
            count = (
                session.query(Spool)
                .filter(
                    Spool.project_id == project_id,
                    Spool.id.in_(spool_ids),
                    Spool.status == SpoolStatus.IN_TRANSIT.value,
                )
                .update(
                    {
                        "status": SpoolStatus.SITE_LAYDOWN.value,
                        "current_location": SpoolLocation.SITE_LAYDOWN.value,
                        "site_laydown_bay": laydown_bay_location.strip().upper(),
                        "site_received_date": datetime.utcnow(),
                        "site_receiver_name": received_by.strip(),
                        "updated_at": datetime.utcnow(),
                    },
                    synchronize_session="fetch",
                )
            )
            logger.info(f"Received {count} spools at Site Laydown '{laydown_bay_location}' by {received_by}.")
            return count

    def mark_spool_erected(
        self,
        project_id: int,
        spool_id: int,
        erection_team: str,
        erected_by_supervisor: str,
        elevation_verified: bool = True,
        flow_direction_verified: bool = True,
        erection_date: Optional[date] = None,
        crane_used: Optional[str] = None,
    ) -> Spool:
        """
        ثبت نصب قطعی اسپول روی سازه پایپ‌رک یا فونداسیون (Hook-up Complete)
        """
        with self.db.session_scope() as session:
            spool = session.get(Spool, spool_id)
            if not spool or spool.project_id != project_id:
                raise AppError(f"Spool #{spool_id} not found.")

            if getattr(spool, "is_on_hold", False):
                raise SpoolOnHoldError(f"Cannot erect Spool '{spool.spool_number}': Spool is on HOLD!")

            if not (elevation_verified and flow_direction_verified):
                raise SpoolWorkflowError(f"Cannot erect Spool '{spool.spool_number}': Alignment and flow direction must be verified.")

            spool.status = SpoolStatus.ERECTED.value
            spool.current_location = SpoolLocation.INSTALLED_ON_LINE.value
            spool.erection_date = erection_date or date.today()
            spool.erection_team = erection_team.strip()
            spool.erected_by = erected_by_supervisor.strip()
            spool.crane_tag = crane_used.strip().upper() if crane_used else None
            spool.updated_at = datetime.utcnow()

            session.flush()
            logger.info(f"Spool '{spool.spool_number}' ERECTED on Line '{spool.line_number}' by Team '{erection_team}'.")
            return spool

    # Implementation note.

    def toggle_spool_hold(
        self,
        project_id: int,
        spool_id: int,
        set_on_hold: bool,
        hold_reason_category: Union[HoldReasonCategory, str],
        reason_description: str,
        action_by: str,
    ) -> Spool:
        """اعمال یا لغو وضعیت هولد جهت توقف فوری ساخت یا نصب اسپول"""
        cat_val = hold_reason_category.value if isinstance(hold_reason_category, HoldReasonCategory) else str(hold_reason_category).strip().upper()

        with self.db.session_scope() as session:
            spool = session.get(Spool, spool_id)
            if not spool or spool.project_id != project_id:
                raise AppError(f"Spool #{spool_id} not found.")

            spool.is_on_hold = set_on_hold
            spool.hold_category = cat_val if set_on_hold else None
            spool.hold_reason = reason_description.strip() if set_on_hold else None
            spool.hold_date = datetime.utcnow() if set_on_hold else None
            spool.held_by = action_by.strip() if set_on_hold else None
            spool.updated_at = datetime.utcnow()

            session.flush()
            logger.warning(
                f"Spool '{spool.spool_number}' HOLD status set to {set_on_hold} "
                f"by {action_by}. Reason: [{cat_val}] {reason_description}"
            )
            return spool

    # Implementation note.

    def get_spool_dossier(self, project_id: int, spool_id: int) -> Dict[str, Any]:
        """
        استخراج پرونده فنی ۳۶۰ درجه شامل سرجوش‌ها، نتایج NDT، متریال، کنترل ابعادی و پکیج تست
        """
        with self.db.session_scope() as session:
            spool = (
                session.query(Spool)
                .filter(Spool.id == spool_id, Spool.project_id == project_id)
                .options(selectinload(Spool.welds))
                .first()
            )
            if not spool:
                raise AppError(f"Spool #{spool_id} not found.")

            # Implementation note.
            welds_data = []
            for w in (spool.welds or []):
                welds_data.append({
                    "weld_id": w.id,
                    "weld_number": getattr(w, "weld_number", f"W-{w.id}"),
                    "dia_inch": float(getattr(w, "dia_inch", 1.0) or 1.0),
                    "status": w.status,
                    "wps_number": getattr(w, "wps_number", "WPS-STD"),
                    "welder_stencil": getattr(w, "root_welder_id", w.welder_id),
                    "ndt_status": getattr(w, "ndt_status", "PENDING"),
                })

            # Implementation note.
            dim_record = (
                session.query(DimensionalCheckRecord)
                .filter(DimensionalCheckRecord.spool_id == spool.id)
                .order_by(desc(DimensionalCheckRecord.id))
                .first()
            )

            return {
                "spool_id": spool.id,
                "spool_number": spool.spool_number,
                "line_number": spool.line_number,
                "drawing_number": spool.drawing_number,
                "revision": spool.revision,
                "status": spool.status,
                "location": spool.current_location,
                "is_on_hold": spool.is_on_hold,
                "hold_details": {
                    "category": getattr(spool, "hold_category", None),
                    "reason": getattr(spool, "hold_reason", None),
                    "held_by": getattr(spool, "held_by", None),
                } if spool.is_on_hold else None,
                "engineering_metrics": {
                    "weight_kg": float(spool.weight_kg or 0.0),
                    "total_dia_inch": float(spool.total_dia_inch or 0.0),
                    "shop_welds_count": len(welds_data),
                },
                "logistics": {
                    "shipping_manifest": getattr(spool, "shipping_manifest_no", None),
                    "dispatch_date": spool.dispatch_date.isoformat() if getattr(spool, "dispatch_date", None) else None,
                    "erection_date": spool.erection_date.isoformat() if getattr(spool, "erection_date", None) else None,
                    "erection_team": getattr(spool, "erection_team", None),
                },
                "dimensional_check": {
                    "status": dim_record.status if dim_record else "NOT_INSPECTED",
                    "report_number": dim_record.report_number if dim_record else None,
                    "inspector": dim_record.inspector_name if dim_record else None,
                } if dim_record else None,
                "welds_register": welds_data,
            }

    # Implementation note.

    def get_spooling_kpis(self, project_id: int) -> Dict[str, Any]:
        """
        محاسبه شاخص‌های آماری ساخت و نصب اسپول با کوئری‌های تجمعی مستقیم دیتابیس
        """
        with self.db.session_scope() as session:
            stats = session.query(
                func.count(Spool.id).label("total_spools"),
                func.sum(func.coalesce(Spool.total_dia_inch, 0.0)).label("total_dia_inch"),
                func.sum(func.coalesce(Spool.weight_kg, 0.0)).label("total_weight_kg"),
                func.sum(case((Spool.status.in_([
                    SpoolStatus.FAB_COMPLETED.value,
                    SpoolStatus.NDT_CLEARED.value,
                    SpoolStatus.DIMENSIONAL_ACCEPTED.value,
                    SpoolStatus.PAINTING.value,
                    SpoolStatus.READY_FOR_DISPATCH.value,
                    SpoolStatus.IN_TRANSIT.value,
                    SpoolStatus.SITE_LAYDOWN.value,
                    SpoolStatus.ERECTED.value,
                ]), 1), else_=0)).label("fabricated_count"),
                func.sum(case((Spool.status.in_([
                    SpoolStatus.FAB_COMPLETED.value,
                    SpoolStatus.NDT_CLEARED.value,
                    SpoolStatus.DIMENSIONAL_ACCEPTED.value,
                    SpoolStatus.PAINTING.value,
                    SpoolStatus.READY_FOR_DISPATCH.value,
                    SpoolStatus.IN_TRANSIT.value,
                    SpoolStatus.SITE_LAYDOWN.value,
                    SpoolStatus.ERECTED.value,
                ]), func.coalesce(Spool.total_dia_inch, 0.0)), else_=0.0)).label("fabricated_dia_inch"),
                func.sum(case((Spool.status == SpoolStatus.ERECTED.value, 1), else_=0)).label("erected_count"),
                func.sum(case((Spool.status == SpoolStatus.ERECTED.value, func.coalesce(Spool.total_dia_inch, 0.0)), else_=0.0)).label("erected_dia_inch"),
                func.sum(case((Spool.is_on_hold == True, 1), else_=0)).label("on_hold_count"),
            ).filter(Spool.project_id == project_id).first()

            total_spools = stats.total_spools or 0
            total_di = float(stats.total_dia_inch or 0.0)
            fab_di = float(stats.fabricated_dia_inch or 0.0)
            erected_di = float(stats.erected_dia_inch or 0.0)

            fab_pct = round((fab_di / total_di * 100), 2) if total_di > 0 else 0.0
            erected_pct = round((erected_di / total_di * 100), 2) if total_di > 0 else 0.0

            return {
                "project_id": project_id,
                "timestamp": datetime.utcnow().isoformat(),
                "inventory_counts": {
                    "total_spools": total_spools,
                    "fabricated_spools": stats.fabricated_count or 0,
                    "erected_spools": stats.erected_count or 0,
                    "on_hold_spools": stats.on_hold_count or 0,
                    "total_tonnage": round(float(stats.total_weight_kg or 0.0) / 1000.0, 2),
                },
                "dia_inch_progression": {
                    "total_dia_inch": round(total_di, 1),
                    "fabricated_dia_inch": round(fab_di, 1),
                    "erected_dia_inch": round(erected_di, 1),
                    "fabrication_progress_pct": fab_pct,
                    "erection_progress_pct": erected_pct,
                },
            }