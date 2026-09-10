# -*- coding: utf-8 -*-
"""
services/material_tracking.py – PipeAgent
سرویس جامع مدیریت موجودی انبار، ردیابی هیت‌نامبر، گواهینامه‌های MTR و کنترل تخصیص متریال
منطبق با استانداردهای ASME B31.3 و EN 10204، دارای قفل ردیفی ضدتداخل (Pessimistic Lock)،
مدیریت برش و شاخه‌های باقیمانده (Pipe Offcuts) و تبارشناسی کامل متریال از کارخانه تا اسپول.
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

from db.manager import DatabaseManager
from db.models import (
    MaterialItem,
    PurchaseOrder,
    MaterialRequisition,
    Spool,
    Weld,
    DocumentEvidence,
)
from services.license import increment_usage

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Engineering Standards
# ──────────────────────────────────────────────

class MaterialCategory(str, Enum):
    """دسته‌بندی اقلام متریال پایپینگ و مکانیک"""
    PIPE = "PIPE"                              # Implementation note.
    FITTING = "FITTING"                        # Implementation note.
    FLANGE = "FLANGE"                          # Implementation note.
    VALVE = "VALVE"                            # Implementation note.
    GASKET = "GASKET"                          # Implementation note.
    BOLT_NUT = "BOLT_NUT"                      # Implementation note.
    CONSUMABLE = "CONSUMABLE"                  # Implementation note.
    SPECIAL_PART = "SPECIAL_PART"              # Implementation note.


class MaterialStatus(str, Enum):
    """وضعیت کیفی و چرخه حیات انبارش متریال"""
    AVAILABLE = "AVAILABLE"                    # Implementation note.
    RESERVED = "RESERVED"                      # Implementation note.
    ISSUED = "ISSUED"                          # Implementation note.
    QUARANTINED = "QUARANTINED"                # Implementation note.
    REJECTED = "REJECTED"                      # Implementation note.
    SCRAPPED = "SCRAPPED"                      # Implementation note.


class MTRStatus(str, Enum):
    """وضعیت سرتیفیکیت متریال طبق EN 10204"""
    CERT_3_1 = "EN_10204_3.1"                  # Implementation note.
    CERT_3_2 = "EN_10204_3.2"                  # Implementation note.
    MISSING = "MISSING"                        # Implementation note.
    PENDING_REVIEW = "UNDER_REVIEW"            # Implementation note.


# ──────────────────────────────────────────────
#  Custom Domain Exceptions
# ──────────────────────────────────────────────

class InsufficientStockError(Exception):
    """خطای کسری موجودی واقعی یا قابل تخصیص انبار"""
    pass


class MaterialQuarantineError(Exception):
    """خطای ممانعت از مصرف متریال فاقد MTR یا در وضعیت قرنطینه"""
    pass


# ──────────────────────────────────────────────
#  Material Tracking Service Implementation
# ──────────────────────────────────────────────

class MaterialTrackingService:
    """
    سرویس مدیریت تبارشناسی متریال، ردیابی Heat/Batch Number و کنترل موجودی پروژه‌های پایپینگ
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    # Implementation note.

    def receive_material(
        self,
        project_id: int,
        material_type: Union[MaterialCategory, str],
        *,
        material_code: str,
        spec_grade: str,
        size_nps: str,
        heat_number: str,
        batch_number: str = "",
        quantity: float,
        unit: str = "MTR",
        rating_or_schedule: str = "",
        location_bin: str = "MAIN_YARD",
        po_id: Optional[int] = None,
        mr_id: Optional[int] = None,
        mtr_received: bool = False,
        mtr_certificate_number: str = "",
        pmi_tested: bool = False,
        pmi_result: str = "NA",
        length_per_piece_mtr: Optional[float] = None,
        supplier_name: str = "",
        receiver_name: str = "storekeeper",
        remarks: str = "",
    ) -> Dict[str, Any]:
        """
        ثبت رسید متریال ورودی به انبار (Material Receiving Report):
        در صورت عدم وجود MTR یا منفی بودن تست PMI، متریال خودکار وارد وضعیت QUARANTINED می‌شود.
        """
        if not increment_usage(self.db):
            raise PermissionError("License limit reached. Cannot register material receipt.")

        if quantity <= 0:
            raise ValueError("Receipt quantity must be strictly positive.")

        mat_type_val = material_type.value if isinstance(material_type, MaterialCategory) else str(material_type).strip().upper()
        heat_clean = str(heat_number).strip().upper()

        # Implementation note.
        is_quarantined = (not mtr_received) or (pmi_result.upper() == "FAIL")
        initial_status = MaterialStatus.QUARANTINED.value if is_quarantined else MaterialStatus.AVAILABLE.value

        with self.db.session_scope() as session:
            item = MaterialItem(
                project_id=project_id,
                purchase_order_id=po_id,
                requisition_id=mr_id,
                material_code=material_code.strip().upper(),
                material_type=mat_type_val,
                material_grade=spec_grade.strip().upper(),
                spec_grade=spec_grade.strip().upper(),
                size=size_nps.strip(),
                rating=rating_or_schedule.strip(),
                schedule=rating_or_schedule.strip(),
                heat_number=heat_clean,
                batch_number=batch_number.strip().upper(),
                quantity_received=quantity,
                quantity_available=quantity,
                quantity_reserved=0.0,
                quantity_issued=0.0,
                unit=unit.strip().upper(),
                location=location_bin.strip(),
                mtr_received=mtr_received,
                mtr_number=mtr_certificate_number.strip(),
                pmi_tested=pmi_tested,
                pmi_result=pmi_result.strip().upper(),
                length_per_piece=length_per_piece_mtr,
                supplier_name=supplier_name.strip(),
                status=initial_status,
                quarantine_reason="Missing MTR certificate" if not mtr_received else ("PMI Failed" if pmi_result.upper() == "FAIL" else None),
                received_date=date.today(),
                received_by=receiver_name,
                remarks=remarks.strip(),
                created_at=datetime.utcnow(),
            )
            session.add(item)
            session.flush()

            item_id = item.id
            logger.info(
                f"Material received: ID #{item_id} [{mat_type_val}] Heat: '{heat_clean}' "
                f"Qty: {quantity} {unit} -> Status: {initial_status}"
            )

        return self.get_material_item(item_id)

    # Implementation note.

    def reserve_material_for_spool(
        self,
        item_id: int,
        spool_id: int,
        quantity_to_reserve: float,
        reserved_by: str,
    ) -> Dict[str, Any]:
        """
        رزرو متریال برای پیش‌ساخت یک اسپول خاص با اعمال قفل بدبینانه سطحی (Pessimistic Lock).
        ممانعت از رزرو همزمان یا بیش از سقف موجودی آزاد.
        """
        if quantity_to_reserve <= 0:
            raise ValueError("Reservation quantity must be positive.")

        with self.db.session_scope() as session:
            # Implementation note.
            item = (
                session.query(MaterialItem)
                .filter(MaterialItem.id == item_id)
                .with_for_update()
                .first()
            )
            if not item:
                raise ValueError(f"Material item #{item_id} not found.")

            if item.status == MaterialStatus.QUARANTINED.value:
                raise MaterialQuarantineError(
                    f"Cannot reserve item #{item_id}: Material is in QUARANTINE ({item.quarantine_reason})."
                )

            if item.status in [MaterialStatus.REJECTED.value, MaterialStatus.SCRAPPED.value]:
                raise MaterialQuarantineError(f"Cannot reserve item #{item_id}: Material status is {item.status}.")

            # Implementation note.
            available_qty = float(item.quantity_available or 0.0)
            if available_qty < quantity_to_reserve:
                raise InsufficientStockError(
                    f"Insufficient stock for Heat '{item.heat_number}'. "
                    f"Available: {available_qty} {item.unit}, Requested: {quantity_to_reserve} {item.unit}"
                )

            # Implementation note.
            item.quantity_available = available_qty - quantity_to_reserve
            item.quantity_reserved = float(item.quantity_reserved or 0.0) + quantity_to_reserve
            item.updated_at = datetime.utcnow()

            # Implementation note.
            if item.quantity_available == 0 and item.quantity_reserved > 0:
                item.status = MaterialStatus.RESERVED.value

            session.flush()
            logger.info(
                f"Reserved {quantity_to_reserve} {item.unit} of Material #{item_id} (Heat: {item.heat_number}) "
                f"for Spool #{spool_id} by {reserved_by}."
            )

        return self.get_material_item(item_id)

    # Implementation note.

    def issue_material_to_shop(
        self,
        item_id: int,
        quantity_to_issue: float,
        miv_number: str,
        issued_to_team: str,
        issued_by: str,
    ) -> Dict[str, Any]:
        """
        صدور قطعی کالا از انبار با شماره حواله (MIV) و کسر از کل موجودی فیزیکی
        """
        if quantity_to_issue <= 0:
            raise ValueError("Issue quantity must be positive.")

        with self.db.session_scope() as session:
            item = (
                session.query(MaterialItem)
                .filter(MaterialItem.id == item_id)
                .with_for_update()
                .first()
            )
            if not item:
                raise ValueError(f"Material item #{item_id} not found.")

            if item.status == MaterialStatus.QUARANTINED.value:
                raise MaterialQuarantineError(f"Cannot issue quarantined material: {item.quarantine_reason}")

            # Implementation note.
            current_reserved = float(item.quantity_reserved or 0.0)
            current_available = float(item.quantity_available or 0.0)
            total_physical = current_reserved + current_available

            if total_physical < quantity_to_issue:
                raise InsufficientStockError(
                    f"Physical stock insufficient. Total: {total_physical} {item.unit}, Requested: {quantity_to_issue} {item.unit}"
                )

            # Implementation note.
            if current_reserved >= quantity_to_issue:
                item.quantity_reserved = current_reserved - quantity_to_issue
            else:
                remaining_deduction = quantity_to_issue - current_reserved
                item.quantity_reserved = 0.0
                item.quantity_available = current_available - remaining_deduction

            item.quantity_issued = float(item.quantity_issued or 0.0) + quantity_to_issue
            item.last_miv_number = miv_number.strip().upper()
            item.issued_to = issued_to_team.strip()
            item.issued_date = date.today()
            item.updated_at = datetime.utcnow()

            # Implementation note.
            if (item.quantity_available or 0.0) == 0 and (item.quantity_reserved or 0.0) == 0:
                item.status = MaterialStatus.ISSUED.value

            session.flush()
            logger.info(
                f"Issued {quantity_to_issue} {item.unit} of Material #{item_id} (MIV: '{miv_number}') "
                f"to '{issued_to_team}' by {issued_by}."
            )

        return self.get_material_item(item_id)

    # Implementation note.

    def cut_pipe_length(
        self,
        mother_item_id: int,
        cut_length_mtr: float,
        spool_number: str,
        cut_by: str,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """
        ثبت برش شاخه لوله:
        - طول برش‌خورده به اسپول تخصیص داده می‌شود.
        - طول باقیمانده (Remnant/Offcut) به عنوان یک قلم متریال جدید با همان Heat Number،
          MTR و مشخصات متالورژیکی با پسوند '-REM' در انبار ثبت می‌شود.
        """
        with self.db.session_scope() as session:
            mother_item = (
                session.query(MaterialItem)
                .filter(MaterialItem.id == mother_item_id)
                .with_for_update()
                .first()
            )
            if not mother_item:
                raise ValueError(f"Mother pipe item #{mother_item_id} not found.")

            available_length = float(mother_item.quantity_available or 0.0)
            if available_length < cut_length_mtr:
                raise InsufficientStockError(
                    f"Mother pipe length insufficient. Available: {available_length}m, Requested cut: {cut_length_mtr}m"
                )

            # Implementation note.
            mother_item.quantity_available = available_length - cut_length_mtr
            mother_item.quantity_issued = float(mother_item.quantity_issued or 0.0) + cut_length_mtr
            mother_item.updated_at = datetime.utcnow()
            if mother_item.quantity_available == 0:
                mother_item.status = MaterialStatus.ISSUED.value

            remnant_id = None
            remnant_length = available_length - cut_length_mtr

            # Implementation note.
            if remnant_length >= 0.5:
                remnant_item = MaterialItem(
                    project_id=mother_item.project_id,
                    purchase_order_id=mother_item.purchase_order_id,
                    material_code=f"{mother_item.material_code}-REM",
                    material_type=mother_item.material_type,
                    material_grade=mother_item.material_grade,
                    spec_grade=mother_item.spec_grade,
                    size=mother_item.size,
                    schedule=mother_item.schedule,
                    rating=mother_item.rating,
                    heat_number=mother_item.heat_number,  # Implementation note.
                    batch_number=mother_item.batch_number,
                    quantity_received=remnant_length,
                    quantity_available=remnant_length,
                    quantity_reserved=0.0,
                    quantity_issued=0.0,
                    unit="MTR",
                    location=mother_item.location,
                    mtr_received=mother_item.mtr_received,
                    mtr_number=mother_item.mtr_number,
                    pmi_tested=mother_item.pmi_tested,
                    pmi_result=mother_item.pmi_result,
                    status=MaterialStatus.AVAILABLE.value,
                    received_date=date.today(),
                    remarks=f"Remnant from cut of Pipe #{mother_item.id} for Spool {spool_number}",
                    created_at=datetime.utcnow(),
                )
                session.add(remnant_item)
                session.flush()
                remnant_id = remnant_item.id

            logger.info(
                f"Pipe #{mother_item_id} cut: {cut_length_mtr}m issued to Spool '{spool_number}'. "
                f"Remnant created: #{remnant_id} ({remnant_length:.2f}m)."
            )

        mother_dto = self.get_material_item(mother_item_id)
        remnant_dto = self.get_material_item(remnant_id) if remnant_id else None
        return mother_dto, remnant_dto

    # Implementation note.

    def release_from_quarantine(
        self,
        item_id: int,
        mtr_certificate_no: str,
        inspector_name: str,
        pmi_verified: bool = True,
        approval_comments: str = "",
    ) -> Dict[str, Any]:
        """
        تأیید گواهینامه MTR و ترخیص متریال از قرنطینه به وضعیت AVAILABLE
        """
        with self.db.session_scope() as session:
            item = session.query(MaterialItem).filter(MaterialItem.id == item_id).first()
            if not item:
                raise ValueError(f"Material item #{item_id} not found.")

            item.mtr_received = True
            item.mtr_number = mtr_certificate_no.strip()
            item.pmi_tested = pmi_verified
            item.pmi_result = "PASS" if pmi_verified else "FAIL"
            item.status = MaterialStatus.AVAILABLE.value if pmi_verified else MaterialStatus.QUARANTINED.value
            item.quarantine_reason = None if pmi_verified else "PMI Verification Failed"
            item.inspected_by = inspector_name
            item.inspection_date = datetime.utcnow()
            item.updated_at = datetime.utcnow()

            session.flush()
            logger.info(f"Material #{item_id} (Heat: {item.heat_number}) RELEASED from quarantine by {inspector_name}.")

        return self.get_material_item(item_id)

    # Implementation note.

    def trace_heat_number_genealogy(self, project_id: int, heat_number: str) -> Dict[str, Any]:
        """
        گزارش کامل و انکارناپذیر شجره‌نامه یک Heat Number خاص:
        - مشخصات خرید، سازنده، MTR و پکینگ‌لیست
        - اسپول‌ها و ایزومتریک‌هایی که این متریال در آن‌ها به کار رفته است
        - سرجوش‌هایی که این ذوب در آن‌ها مصرف شده و وضعیت NDT آن‌ها
        - پکیج‌های آزمون فشار هیدرواستاتیک مرتبط
        """
        heat_clean = str(heat_number).strip().upper()

        with self.db.session_scope() as session:
            materials = (
                session.query(MaterialItem)
                .filter(
                    MaterialItem.project_id == project_id,
                    MaterialItem.heat_number == heat_clean,
                )
                .all()
            )

            if not materials:
                return {"heat_number": heat_clean, "found": False, "message": "No material records found."}

            total_received = sum(float(m.quantity_received or 0.0) for m in materials)
            total_available = sum(float(m.quantity_available or 0.0) for m in materials)
            total_issued = sum(float(m.quantity_issued or 0.0) for m in materials)
            mtr_docs = [m.mtr_number for m in materials if m.mtr_number]

            # Implementation note.
            welds = (
                session.query(Weld)
                .filter(
                    Weld.project_id == project_id,
                    or_(
                        getattr(Weld, "pipe1_heat_no", "") == heat_clean,
                        getattr(Weld, "pipe2_heat_no", "") == heat_clean,
                    ),
                )
                .all()
            )

            welds_summary = [
                {
                    "weld_id": w.id,
                    "weld_number": getattr(w, "weld_number", f"W-{w.id}"),
                    "line_number": w.line_number,
                    "status": w.status,
                    "welder_stencil": getattr(w, "root_welder_id", w.welder_id),
                }
                for w in welds
            ]

            return {
                "heat_number": heat_clean,
                "found": True,
                "material_type": materials[0].material_type,
                "spec_grade": materials[0].spec_grade,
                "size": materials[0].size,
                "mtr_certificates": list(set(mtr_docs)),
                "is_mtr_verified": all(m.mtr_received for m in materials),
                "stock_summary": {
                    "total_received": total_received,
                    "total_available": total_available,
                    "total_issued": total_issued,
                    "unit": materials[0].unit,
                },
                "welding_genealogy": {
                    "welds_count": len(welds),
                    "welds": welds_summary,
                },
            }

    # Implementation note.

    def get_stock_dashboard(self, project_id: int) -> Dict[str, Any]:
        """
        محاسبه ماتریس جامع وضعیت انبار پروژه با اجرای کوئری‌های تجمعی مستقیم در دیتابیس
        (بدون لود بیهوده رکوردها در RAM)
        """
        with self.db.session_scope() as session:
            stats = session.query(
                func.count(MaterialItem.id).label("total_items"),
                func.sum(case((MaterialItem.status == MaterialStatus.AVAILABLE.value, 1), else_=0)).label("available_items"),
                func.sum(case((MaterialItem.status == MaterialStatus.RESERVED.value, 1), else_=0)).label("reserved_items"),
                func.sum(case((MaterialItem.status == MaterialStatus.QUARANTINED.value, 1), else_=0)).label("quarantined_items"),
                func.sum(case((MaterialItem.mtr_received == False, 1), else_=0)).label("missing_mtr_count"),
                func.sum(case((MaterialItem.quantity_available <= 5.0, 1), else_=0)).label("low_stock_count"),
            ).filter(MaterialItem.project_id == project_id).first()

            # Implementation note.
            category_breakdown = (
                session.query(
                    MaterialItem.material_type,
                    func.count(MaterialItem.id).label("count"),
                    func.sum(MaterialItem.quantity_available).label("total_available_qty"),
                )
                .filter(MaterialItem.project_id == project_id)
                .group_by(MaterialItem.material_type)
                .all()
            )

            total = stats.total_items or 0
            return {
                "project_id": project_id,
                "timestamp": datetime.utcnow().isoformat(),
                "overview": {
                    "total_material_lots": total,
                    "available_lots": stats.available_items or 0,
                    "reserved_lots": stats.reserved_items or 0,
                    "quarantined_lots": stats.quarantined_items or 0,
                },
                "quality_alarms": {
                    "missing_mtr_certificates_count": stats.missing_mtr_count or 0,
                    "low_stock_items_count": stats.low_stock_count or 0,
                    "is_quarantine_active": (stats.quarantined_items or 0) > 0,
                },
                "inventory_by_category": {
                    row.material_type or "Unclassified": {
                        "lots_count": row.count,
                        "available_quantity": float(row.total_available_qty or 0.0),
                    }
                    for row in category_breakdown
                },
            }

    # Implementation note.

    def get_material_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        """بازیابی دیکشنری مستقل و ایمن رکورد متریال جهت جلوگیری از DetachedInstanceError"""
        with self.db.session_scope() as session:
            item = session.get(MaterialItem, item_id)
            if not item:
                return None
            return {
                "id": item.id,
                "project_id": item.project_id,
                "material_code": item.material_code,
                "material_type": item.material_type,
                "material_grade": getattr(item, "material_grade", item.spec_grade),
                "size": item.size,
                "rating_schedule": getattr(item, "rating", getattr(item, "schedule", "")),
                "heat_number": item.heat_number,
                "batch_number": item.batch_number,
                "quantity_received": float(item.quantity_received or 0.0),
                "quantity_available": float(item.quantity_available or 0.0),
                "quantity_reserved": float(getattr(item, "quantity_reserved", 0.0) or 0.0),
                "quantity_issued": float(getattr(item, "quantity_issued", 0.0) or 0.0),
                "unit": item.unit,
                "location": item.location,
                "mtr_received": item.mtr_received,
                "mtr_number": getattr(item, "mtr_number", ""),
                "pmi_result": getattr(item, "pmi_result", "NA"),
                "status": item.status,
                "quarantine_reason": getattr(item, "quarantine_reason", None),
                "received_date": item.received_date.isoformat() if item.received_date else None,
            }