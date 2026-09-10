# -*- coding: utf-8 -*-
"""
db/queries/material_queries.py – PipeAgent v5.1
===============================================
Enterprise Material Control, Traceability, and Inventory Query Layer.

Covers:
  • Material Requisitions (MR) & Purchase Orders (PO)
  • Warehouse Receipts, Heat Number Traceability, and Inventory Levels
  • Material Take-Off (MTO) Management & Shortage Alerts
  • Material Preservation (Corrosion control, Nitrogen capping, and inspection cycles)
  • Valve Integrity Testing (Hydro Shell & Seat inspections)

All queries are optimized for SQLAlchemy 2.0, support robust filtering,
pagination, and bulk-operations for spreadsheet imports.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from db.models import (
    MaterialItem,
    MaterialPreservationRecord,
    MaterialRequisition,
    MaterialTakeOff,
    PurchaseOrder,
    ValveRecord,
)

try:
    from core.exceptions import DatabaseError, ValidationError
except ImportError:
    class DatabaseError(Exception): pass
    class ValidationError(Exception): pass

logger = logging.getLogger(__name__)

__all__ = [
    # Material Requisition (MR)
    "get_material_requisitions",
    "get_mr_by_id",
    "create_material_requisition",
    "update_material_requisition",
    "delete_material_requisition",
    # Purchase Order (PO)
    "get_purchase_orders",
    "get_po_by_id",
    "create_purchase_order",
    "update_purchase_order",
    "delete_purchase_order",
    # Material Item (Inventory Receipts)
    "get_material_items",
    "get_material_item_by_id",
    "get_material_items_by_heat_number",
    "count_material_items",
    "create_material_item",
    "create_material_items_bulk",
    "update_material_item",
    "delete_material_item",
    # Material Take-Off (MTO)
    "get_material_takeoffs",
    "get_mto_by_id",
    "create_mto_entry",
    "create_mto_entries_bulk",
    "update_mto_entry",
    "delete_mto_entry",
    # Material Preservation
    "get_preservation_records",
    "get_preservation_record_by_id",
    "get_pending_preservation_inspections",
    "create_preservation_record",
    "update_preservation_record",
    "delete_preservation_record",
    # Valve Testing & Installation
    "get_valve_records",
    "get_valve_by_id",
    "get_valve_by_tag",
    "create_valve_record",
    "update_valve_record",
    "delete_valve_record",
    # Advanced Cross-Cutting Queries
    "get_material_reconciliation_report",
    "get_material_dashboard_stats",
]


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────

def _validate_project_id(project_id: int) -> None:
    if not isinstance(project_id, int) or project_id <= 0:
        raise ValidationError(f"Invalid project_id: {project_id!r}. Must be a positive integer.")


def _apply_pagination(query, *, offset: int = 0, limit: int = 100):
    if offset > 0:
        query = query.offset(offset)
    if limit is not None and limit > 0:
        query = query.limit(limit)
    return query


def _safe_update(obj: Any, data: Dict[str, Any], *, exclude: set[str] | None = None) -> int:
    exclude = exclude or {"id", "created_at", "project_id"}
    changed = 0
    for key, value in data.items():
        if key in exclude:
            continue
        if hasattr(obj, key):
            old = getattr(obj, key)
            if old != value:
                setattr(obj, key, value)
                changed += 1
    return changed


# ══════════════════════════════════════════════
#  1. Material Requisition (MR) Queries
# ══════════════════════════════════════════════

def get_material_requisitions(
    session: Session,
    project_id: int,
    *,
    status: Optional[str] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[MaterialRequisition]:
    """دریافت لیست درخواست‌های متریال با قابلیت جستجوی آزاد شماره MR."""
    _validate_project_id(project_id)
    q = session.query(MaterialRequisition).filter(MaterialRequisition.project_id == project_id)

    if status:
        q = q.filter(MaterialRequisition.status == status)
    if search:
        q = q.filter(MaterialRequisition.mr_number.ilike(f"%{search}%"))

    q = q.order_by(MaterialRequisition.required_date.asc().nullslast())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_mr_by_id(session: Session, mr_id: int) -> Optional[MaterialRequisition]:
    """دریافت درخواست متریال بر اساس شناسه."""
    return session.get(MaterialRequisition, mr_id)


def create_material_requisition(session: Session, **kwargs: Any) -> MaterialRequisition:
    """ایجاد درخواست متریال جدید."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a MaterialRequisition.")
    _validate_project_id(kwargs["project_id"])

    mr = MaterialRequisition(**kwargs)
    session.add(mr)
    session.flush()
    logger.info("Created MaterialRequisition ID=%d No=%s", mr.id, mr.mr_number)
    return mr


def update_material_requisition(session: Session, mr_id: int, **kwargs: Any) -> Optional[MaterialRequisition]:
    """به‌روزرسانی درخواست متریال."""
    mr = session.get(MaterialRequisition, mr_id)
    if mr is None:
        return None
    changed = _safe_update(mr, kwargs)
    if changed:
        session.flush()
        logger.info("Updated MaterialRequisition ID=%d (%d fields modified).", mr_id, changed)
    return mr


def delete_material_requisition(session: Session, mr_id: int) -> bool:
    """حذف درخواست متریال."""
    mr = session.get(MaterialRequisition, mr_id)
    if mr is None:
        return False
    session.delete(mr)
    session.flush()
    logger.info("Deleted MaterialRequisition ID=%d.", mr_id)
    return True


# ══════════════════════════════════════════════
#  2. Purchase Order (PO) Queries
# ══════════════════════════════════════════════

def get_purchase_orders(
    session: Session,
    project_id: int,
    *,
    mr_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[PurchaseOrder]:
    """دریافت سفارشات خرید با فیلتر وضعیت یا شماره سفارش خرید."""
    _validate_project_id(project_id)
    q = session.query(PurchaseOrder).filter(PurchaseOrder.project_id == project_id)

    if mr_id is not None:
        q = q.filter(PurchaseOrder.mr_id == mr_id)
    if status:
        q = q.filter(PurchaseOrder.status == status)
    if search:
        q = q.filter(PurchaseOrder.po_number.ilike(f"%{search}%"))

    q = q.order_by(PurchaseOrder.order_date.desc().nullslast())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_po_by_id(session: Session, po_id: int) -> Optional[PurchaseOrder]:
    """دریافت اطلاعات سفارش خرید بر اساس شناسه."""
    return session.get(PurchaseOrder, po_id)


def create_purchase_order(session: Session, **kwargs: Any) -> PurchaseOrder:
    """ثبت سفارش خرید صادرشده جدید."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a PurchaseOrder.")
    _validate_project_id(kwargs["project_id"])

    po = PurchaseOrder(**kwargs)
    session.add(po)
    session.flush()
    logger.info("Created PurchaseOrder ID=%d No=%s", po.id, po.po_number)
    return po


def update_purchase_order(session: Session, po_id: int, **kwargs: Any) -> Optional[PurchaseOrder]:
    """به‌روزرسانی سفارش خرید."""
    po = session.get(PurchaseOrder, po_id)
    if po is None:
        return None
    changed = _safe_update(po, kwargs)
    if changed:
        session.flush()
        logger.info("Updated PurchaseOrder ID=%d (%d fields modified).", po_id, changed)
    return po


def delete_purchase_order(session: Session, po_id: int) -> bool:
    """حذف فیزیکی سفارش خرید."""
    po = session.get(PurchaseOrder, po_id)
    if po is None:
        return False
    session.delete(po)
    session.flush()
    logger.info("Deleted PurchaseOrder ID=%d.", po_id)
    return True


# ══════════════════════════════════════════════
#  3. Material Item (Warehouse Inventory Receipts)
# ══════════════════════════════════════════════

def get_material_items(
    session: Session,
    project_id: int,
    *,
    po_id: Optional[int] = None,
    material_type: Optional[str] = None,
    heat_number: Optional[str] = None,
    location: Optional[str] = None,
    mtr_received: Optional[bool] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[MaterialItem]:
    """جستجو و دریافت متریال‌های ورودی به انبار همراه با فیلترهای فنی تخصصی."""
    _validate_project_id(project_id)
    q = session.query(MaterialItem).filter(MaterialItem.project_id == project_id)

    if po_id is not None:
        q = q.filter(MaterialItem.po_id == po_id)
    if material_type:
        q = q.filter(MaterialItem.material_type == material_type)
    if heat_number:
        q = q.filter(MaterialItem.heat_number == heat_number)
    if location:
        q = q.filter(MaterialItem.location.ilike(f"%{location}%"))
    if mtr_received is not None:
        q = q.filter(MaterialItem.mtr_received == mtr_received)
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                MaterialItem.spec_grade.ilike(pattern),
                MaterialItem.heat_number.ilike(pattern),
                MaterialItem.batch_number.ilike(pattern),
            )
        )

    q = q.order_by(MaterialItem.received_date.desc().nullslast())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_material_item_by_id(session: Session, item_id: int) -> Optional[MaterialItem]:
    """دریافت یک آیتم متریال انبار با شناسه."""
    return session.get(MaterialItem, item_id)


def get_material_items_by_heat_number(session: Session, project_id: int, heat_number: str) -> List[MaterialItem]:
    """ردیابی فنی سریع کالا در انبار بر اساس شماره ذوب (اصالت کالا)."""
    _validate_project_id(project_id)
    return (
        session.query(MaterialItem)
        .filter(MaterialItem.project_id == project_id, MaterialItem.heat_number == heat_number)
        .all()
    )


def count_material_items(session: Session, project_id: int, *, material_type: Optional[str] = None) -> int:
    _validate_project_id(project_id)
    q = session.query(func.count(MaterialItem.id)).filter(MaterialItem.project_id == project_id)
    if material_type:
        q = q.filter(MaterialItem.material_type == material_type)
    return q.scalar() or 0


def create_material_item(session: Session, **kwargs: Any) -> MaterialItem:
    """ثبت ورود کالا جدید به انبار (Material Receipt)."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a MaterialItem.")
    _validate_project_id(kwargs["project_id"])

    item = MaterialItem(**kwargs)
    session.add(item)
    session.flush()
    logger.info("Receipt MaterialItem ID=%d (Type=%s, Heat=%s)", item.id, item.material_type, item.heat_number)
    return item


def create_material_items_bulk(
    session: Session,
    items_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 100,
) -> int:
    """ثبت ورود انبوه اقلام به انبار (مثلاً بارگذاری فایل تحویلی بازرس از محموله جدید ورودی)."""
    if not items_data:
        return 0

    items = [MaterialItem(**data) for data in items_data]
    total = len(items)

    for i in range(0, total, batch_size):
        batch = items[i : i + batch_size]
        session.add_all(batch)
        session.flush()

    logger.info("Bulk imported %d MaterialItems.", total)
    return total


def update_material_item(session: Session, item_id: int, **kwargs: Any) -> Optional[MaterialItem]:
    """به‌روزرسانی اطلاعات متریال انبار (مانند اصلاح قفسه چیدمان یا تصحیح تعداد موجودی)."""
    item = session.get(MaterialItem, item_id)
    if item is None:
        return None
    changed = _safe_update(item, kwargs)
    if changed:
        session.flush()
        logger.info("Updated MaterialItem ID=%d (%d fields modified).", item_id, changed)
    return item


def delete_material_item(session: Session, item_id: int) -> bool:
    """حذف متریال از سیستم."""
    item = session.get(MaterialItem, item_id)
    if item is None:
        return False
    session.delete(item)
    session.flush()
    logger.info("Deleted MaterialItem ID=%d.", item_id)
    return True


# ══════════════════════════════════════════════
#  4. Material Take-Off (MTO) Queries
# ══════════════════════════════════════════════

def get_material_takeoffs(
    session: Session,
    project_id: int,
    *,
    line_number: Optional[str] = None,
    spool_number: Optional[str] = None,
    material_type: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = 0,
    limit: int = 200,
) -> List[MaterialTakeOff]:
    """دریافت اطلاعات اقلام مورد نیاز خطوط و اسپول‌ها با فیلترها و صفحه‌بندی."""
    _validate_project_id(project_id)
    q = session.query(MaterialTakeOff).filter(MaterialTakeOff.project_id == project_id)

    if line_number:
        q = q.filter(MaterialTakeOff.line_number.ilike(f"%{line_number}%"))
    if spool_number:
        q = q.filter(MaterialTakeOff.spool_number.ilike(f"%{spool_number}%"))
    if material_type:
        q = q.filter(MaterialTakeOff.material_type == material_type)
    if status:
        q = q.filter(MaterialTakeOff.status == status)

    q = q.order_by(MaterialTakeOff.line_number.asc(), MaterialTakeOff.id.asc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_mto_by_id(session: Session, mto_id: int) -> Optional[MaterialTakeOff]:
    """دریافت ردیف MTO بر اساس شناسه."""
    return session.get(MaterialTakeOff, mto_id)


def create_mto_entry(session: Session, **kwargs: Any) -> MaterialTakeOff:
    """ایجاد یک ردیف متریال مورد نیاز جدید (MTO Entry)."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a MaterialTakeOff entry.")
    _validate_project_id(kwargs["project_id"])

    entry = MaterialTakeOff(**kwargs)
    session.add(entry)
    session.flush()
    return entry


def create_mto_entries_bulk(
    session: Session,
    mto_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 100,
) -> int:
    """وارد کردن انبوه ردیف‌های متریال مورد نیاز بر اساس اطلاعات نرم‌افزار PDMS/PDS یا ایزومتریک‌ها."""
    if not mto_data:
        return 0

    entries = [MaterialTakeOff(**data) for data in mto_data]
    total = len(entries)

    for i in range(0, total, batch_size):
        batch = entries[i : i + batch_size]
        session.add_all(batch)
        session.flush()

    logger.info("Bulk imported %d MaterialTakeOff entries.", total)
    return total


def update_mto_entry(session: Session, mto_id: int, **kwargs: Any) -> Optional[MaterialTakeOff]:
    """به‌روزرسانی مقادیر مورد نیاز، حواله‌شده یا نصب‌شده MTO."""
    entry = session.get(MaterialTakeOff, mto_id)
    if entry is None:
        return None
    changed = _safe_update(entry, kwargs)
    if changed:
        session.flush()
    return entry


def delete_mto_entry(session: Session, mto_id: int) -> bool:
    """حذف ردیف MTO."""
    entry = session.get(MaterialTakeOff, mto_id)
    if entry is None:
        return False
    session.delete(entry)
    session.flush()
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_preservation_records(
    session: Session,
    project_id: int,
    *,
    material_item_id: Optional[int] = None,
    heat_number: Optional[str] = None,
    condition: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[MaterialPreservationRecord]:
    """دریافت تاریخچه‌ی حفاظت و نگهداری کارهای پیشگیرانه خوردگی در انبار."""
    _validate_project_id(project_id)
    q = session.query(MaterialPreservationRecord).filter(MaterialPreservationRecord.project_id == project_id)

    if material_item_id is not None:
        q = q.filter(MaterialPreservationRecord.material_item_id == material_item_id)
    if heat_number:
        q = q.filter(MaterialPreservationRecord.heat_number == heat_number)
    if condition:
        q = q.filter(MaterialPreservationRecord.condition == condition)

    q = q.order_by(MaterialPreservationRecord.preservation_date.desc().nullslast())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_preservation_record_by_id(session: Session, record_id: int) -> Optional[MaterialPreservationRecord]:
    """دریافت سابقه نگهداری متریال بر اساس شناسه."""
    return session.get(MaterialPreservationRecord, record_id)


def get_pending_preservation_inspections(
    session: Session,
    project_id: int,
    *,
    target_date: Optional[date] = None,
) -> List[MaterialPreservationRecord]:
    """
    دریافت اقلامی که زمان بازرس دوره‌ای نگهداری آن‌ها فرا رسیده یا گذشته است (انقضای مهلت چرخه‌ی تست).
    """
    _validate_project_id(project_id)
    target = target_date or date.today()
    return (
        session.query(MaterialPreservationRecord)
        .filter(
            MaterialPreservationRecord.project_id == project_id,
            MaterialPreservationRecord.next_inspection_date <= target,
            MaterialPreservationRecord.condition != "Deteriorated",
        )
        .order_by(MaterialPreservationRecord.next_inspection_date.asc())
        .all()
    )


def create_preservation_record(session: Session, **kwargs: Any) -> MaterialPreservationRecord:
    """ثبت سابقه اجرای چرخه‌ی تست یا تمدید مواد محافظتی انبار."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a MaterialPreservationRecord.")
    _validate_project_id(kwargs["project_id"])

    record = MaterialPreservationRecord(**kwargs)
    session.add(record)
    session.flush()
    logger.info("Saved Preservation Cycle for Item ID=%s (Condition=%s)", record.material_item_id, record.condition)
    return record


def update_preservation_record(
    session: Session,
    record_id: int,
    **kwargs: Any,
) -> Optional[MaterialPreservationRecord]:
    """به‌روزرسانی تاریخ تست یا نتایج بازرس کیفیت حفاظت کالا."""
    record = session.get(MaterialPreservationRecord, record_id)
    if record is None:
        return None
    changed = _safe_update(record, kwargs)
    if changed:
        session.flush()
    return record


def delete_preservation_record(session: Session, record_id: int) -> bool:
    """حذف سابقه نگهداری کالا."""
    record = session.get(MaterialPreservationRecord, record_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_valve_records(
    session: Session,
    project_id: int,
    *,
    line_number: Optional[str] = None,
    valve_type: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[ValveRecord]:
    """دریافت و ردیابی سوابق شیرآلات به همراه نتایج تست هیدرو تست بدنه و دیسک."""
    _validate_project_id(project_id)
    q = session.query(ValveRecord).filter(ValveRecord.project_id == project_id)

    if line_number:
        q = q.filter(ValveRecord.line_number.ilike(f"%{line_number}%"))
    if valve_type:
        q = q.filter(ValveRecord.valve_type == valve_type)
    if status:
        q = q.filter(ValveRecord.status == status)

    q = q.order_by(ValveRecord.valve_tag.asc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_valve_by_id(session: Session, valve_id: int) -> Optional[ValveRecord]:
    """دریافت اطلاعات شیرآلات بر اساس شناسه."""
    return session.get(ValveRecord, valve_id)


def get_valve_by_tag(session: Session, project_id: int, valve_tag: str) -> Optional[ValveRecord]:
    """دریافت سریع اطلاعات شیر بر اساس Tag اختصاصی آن."""
    _validate_project_id(project_id)
    return (
        session.query(ValveRecord)
        .filter(ValveRecord.project_id == project_id, ValveRecord.valve_tag == valve_tag)
        .first()
    )


def create_valve_record(session: Session, **kwargs: Any) -> ValveRecord:
    """ثبت شناسنامه شیرآلات ورودی جدید."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a ValveRecord.")
    _validate_project_id(kwargs["project_id"])

    valve = ValveRecord(**kwargs)
    session.add(valve)
    session.flush()
    logger.info("Registered Valve ID=%d Tag=%s", valve.id, valve.valve_tag)
    return valve


def update_valve_record(session: Session, valve_id: int, **kwargs: Any) -> Optional[ValveRecord]:
    """ثبت تاییدیه هیدرو تست بدنه/سیت یا زمان نصب فیزیکی شیر روی خط."""
    valve = session.get(ValveRecord, valve_id)
    if valve is None:
        return None
    changed = _safe_update(valve, kwargs)
    if changed:
        session.flush()
        logger.info("Updated Valve ID=%d Tag=%s (%d fields modified).", valve_id, valve.valve_tag, changed)
    return valve


def delete_valve_record(session: Session, valve_id: int) -> bool:
    """حذف سوابق شیرآلات."""
    valve = session.get(ValveRecord, valve_id)
    if valve is None:
        return False
    session.delete(valve)
    session.flush()
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_material_reconciliation_report(
    session: Session,
    project_id: int,
    *,
    material_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    کوئری پیشرفته محاسباتی و مهندسی جهت مغایرت‌گیری کالا (Material Reconciliation).
    
    این گزارش مشخصات دقیق کالا را به صورت خلاصه تهیه کرده و مقادیر زیر را محاسبه می‌کند:
      - میزان متریال مورد نیاز بر اساس کل نقشه‌ها (Total MTO Required)
      - میزان متریال موجود و آزاد در انبار (Total Received/Available)
      - میزان کسری یا مازاد انبار (Overage / Shortage balance)
    
    خروجی به صورت مستقیم هشدارهای بحرانی کسری متریال را قبل از شروع فاز ساخت مشخص می‌کند.
    """
    _validate_project_id(project_id)

    # Implementation note.
    mto_q = (
        session.query(
            MaterialTakeOff.material_type,
            MaterialTakeOff.spec_grade,
            MaterialTakeOff.size,
            func.sum(MaterialTakeOff.quantity_required).label("total_required"),
            func.sum(MaterialTakeOff.quantity_issued).label("total_issued"),
        )
        .filter(MaterialTakeOff.project_id == project_id)
    )
    if material_type:
        mto_q = mto_q.filter(MaterialTakeOff.material_type == material_type)
    
    mto_results = mto_q.group_by(
        MaterialTakeOff.material_type,
        MaterialTakeOff.spec_grade,
        MaterialTakeOff.size
    ).all()

    # Implementation note.
    inv_q = (
        session.query(
            MaterialItem.material_type,
            MaterialItem.spec_grade,
            MaterialItem.size,
            func.sum(MaterialItem.quantity_received).label("total_received"),
            func.sum(MaterialItem.quantity_available).label("total_available"),
        )
        .filter(MaterialItem.project_id == project_id)
    )
    if material_type:
        inv_q = inv_q.filter(MaterialItem.material_type == material_type)

    inv_results = inv_q.group_by(
        MaterialItem.material_type,
        MaterialItem.spec_grade,
        MaterialItem.size
    ).all()

    # Implementation note.
    inv_map = {}
    for r in inv_results:
        key = (r.material_type, r.spec_grade, r.size)
        inv_map[key] = {
            "received": float(r.total_received or 0),
            "available": float(r.total_available or 0),
        }

    # Implementation note.
    reconciliation_data = []
    for r in mto_results:
        key = (r.material_type, r.spec_grade, r.size)
        inv_data = inv_map.get(key, {"received": 0.0, "available": 0.0})
        
        required = float(r.total_required or 0)
        issued = float(r.total_issued or 0)
        available = inv_data["available"]
        received = inv_data["received"]

        # Implementation note.
        remaining_needed = max(0.0, required - issued)
        balance = available - remaining_needed

        reconciliation_data.append({
            "material_type": r.material_type,
            "spec_grade": r.spec_grade,
            "size": r.size,
            "total_mto_required": required,
            "total_mto_issued": issued,
            "total_warehouse_received": received,
            "warehouse_available_now": available,
            "balance": balance,
            "status": "Safe" if balance >= 0 else "Shortage",
        })

    return reconciliation_data


def get_material_dashboard_stats(session: Session, project_id: int) -> Dict[str, Any]:
    """
    استخراج آمارهای حیاتی مهندسی مواد برای مانیتورینگ آنلاین.
    
    نظیر:
      - نسبت گواهی‌های MTR دریافتی به کل متریال ورودی (تضمین کیفیت)
      - تعداد اقلام منتظر بازرسی‌های چرخه‌ای انبار (Preservation Alert)
      - نسبت تست‌های شیرآلات (Hydro Shell/Seat Passed Ratio)
    """
    _validate_project_id(project_id)

    total_received = count_material_items(session, project_id)
    
    # Implementation note.
    mtr_ok = (
        session.query(func.count(MaterialItem.id))
        .filter(MaterialItem.project_id == project_id, MaterialItem.mtr_received == True)  # noqa: E712
        .scalar() or 0
    )

    # Implementation note.
    preservation_due = len(get_pending_preservation_inspections(session, project_id))

    # Implementation note.
    total_valves = session.query(func.count(ValveRecord.id)).filter(ValveRecord.project_id == project_id).scalar() or 0
    valves_passed = (
        session.query(func.count(ValveRecord.id))
        .filter(
            ValveRecord.project_id == project_id,
            ValveRecord.hydro_shell_test == True,  # noqa: E712
            ValveRecord.hydro_seat_test == True,   # noqa: E712
        )
        .scalar() or 0
    )

    return {
        "warehouse": {
            "total_item_types_received": total_received,
            "mtr_compliance_pct": round(mtr_ok / total_received * 100, 1) if total_received else 0.0,
            "due_preservation_cycles": preservation_due,
        },
        "valve_testing": {
            "total_registered_valves": total_valves,
            "hydro_passed_valves": valves_passed,
            "hydro_test_progress_pct": round(valves_passed / total_valves * 100, 1) if total_valves else 0.0,
        }
    }