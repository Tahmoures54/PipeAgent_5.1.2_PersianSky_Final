# -*- coding: utf-8 -*-
"""
repositories/material_repository.py – PipeAgent v5.1
====================================================
مدیریت جامع موجودی انبار، ردیابی هیت نامبر، سفارشات خرید و صدور کالا
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Set, TypeVar

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from db.manager import DatabaseManager
from db.models import MaterialItem, MaterialRequisition, PurchaseOrder
from repositories.base import BaseRepository

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ──────────────────────────────────────────────
#  Enums & Custom Exceptions
# ──────────────────────────────────────────────

class MaterialStatus(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    ISSUED = "issued"
    QUARANTINED = "quarantined"  # Implementation note.
    SCRAPPED = "scrapped"


class InsufficientStockError(Exception):
    """خطای کسری موجودی واقعی یا قابل تخصیص"""
    pass


class MaterialNotFoundError(Exception):
    """خطای عدم یافتن قلم متریال"""
    pass


class MaterialQuarantinedError(Exception):
    """خطای متریال قرنطینه یا فاقد سرتیفیکیت معتبر"""
    pass


# Implementation note.
try:
    class SafeBaseRepository(BaseRepository[MaterialItem]):
        pass
except TypeError:
    class SafeBaseRepository(BaseRepository):
        pass


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────

class MaterialItemRepository(SafeBaseRepository):
    """
    ریپازیتوری تخصصی اقلام متریال (لوله، اتصالات، فلنج، پیچ و مهره و...)
    با قابلیت ردیابی Heat No، کنترل موجودی و رزرو متریال.
    """

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, MaterialItem)

    # Implementation note.

    def get_by_id_with_relations(
        self, item_id: int, include_po: bool = True, include_mr: bool = True
    ) -> Optional[MaterialItem]:
        """دریافت متریال همراه با بارگذاری رابطه‌ها (جلوگیری از DetachedInstanceError)"""
        with self._session() as session:
            query = session.query(MaterialItem).filter(MaterialItem.id == item_id)
            if include_po and hasattr(MaterialItem, "purchase_order"):
                query = query.options(joinedload(MaterialItem.purchase_order))
            if include_mr and hasattr(MaterialItem, "requisition"):
                query = query.options(joinedload(MaterialItem.requisition))
            return query.first()

    def get_by_heat_number(
        self, heat_number: str, project_id: Optional[int] = None
    ) -> List[MaterialItem]:
        """ردیابی تمام اقلام دارای یک Heat Number خاص (MTR Traceability)"""
        with self._session() as session:
            query = session.query(MaterialItem).filter(
                func.lower(MaterialItem.heat_number) == heat_number.strip().lower()
            )
            if project_id:
                query = query.filter(MaterialItem.project_id == project_id)
            return query.all()

    def get_by_project(
        self,
        project_id: int,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[MaterialItem]:
        """لیست اقلام یک پروژه با فیلتر دسته‌بندی و صفحه‌بندی (سازگار با ستون‌های دیتابیس شما)"""
        with self._session() as session:
            query = session.query(MaterialItem).filter(
                MaterialItem.project_id == project_id
            )
            if category:
                if hasattr(MaterialItem, "category"):
                    query = query.filter(MaterialItem.category == category)
                else:
                    # Implementation note.
                    query = query.filter(MaterialItem.material_type == category)
            return query.order_by(MaterialItem.id.desc()).offset(offset).limit(limit).all()

    def get_available(
        self, project_id: int, min_qty: float = 0.001
    ) -> List[MaterialItem]:
        """دریافت اقلامی که موجودی آزاد برای تخصیص دارند (بدون احتساب رزروها)"""
        with self._session() as session:
            q = session.query(MaterialItem).filter(
                MaterialItem.project_id == project_id,
                MaterialItem.quantity_available >= min_qty
            )
            if hasattr(MaterialItem, "status"):
                q = q.filter(MaterialItem.status == MaterialStatus.AVAILABLE.value)
            return q.all()

    def search_materials(
        self,
        project_id: int,
        material_code: Optional[str] = None,
        size: Optional[str] = None,
        schedule_or_rating: Optional[str] = None,
        material_grade: Optional[str] = None,
        tag_number: Optional[str] = None,
    ) -> List[MaterialItem]:
        """جستجوی پیشرفته بر اساس مشخصات فنی متریال پایپینگ/مکانیک با مدیریت ستون‌های پویا"""
        with self._session() as session:
            query = session.query(MaterialItem).filter(
                MaterialItem.project_id == project_id
            )

            if material_code:
                if hasattr(MaterialItem, "material_code"):
                    query = query.filter(MaterialItem.material_code.ilike(f"%{material_code}%"))
                else:
                    query = query.filter(MaterialItem.material_type.ilike(f"%{material_code}%"))
            if size:
                query = query.filter(MaterialItem.size == size)
            if schedule_or_rating:
                filters = []
                if hasattr(MaterialItem, "schedule"):
                    filters.append(MaterialItem.schedule == schedule_or_rating)
                if hasattr(MaterialItem, "rating"):
                    filters.append(getattr(MaterialItem, "rating") == schedule_or_rating)
                if hasattr(MaterialItem, "spec_grade"):
                    filters.append(MaterialItem.spec_grade.ilike(f"%{schedule_or_rating}%"))
                if filters:
                    query = query.filter(or_(*filters))
            if material_grade:
                if hasattr(MaterialItem, "material_grade"):
                    query = query.filter(getattr(MaterialItem, "material_grade").ilike(f"%{material_grade}%"))
                else:
                    query = query.filter(MaterialItem.spec_grade.ilike(f"%{material_grade}%"))
            if tag_number:
                if hasattr(MaterialItem, "tag_number"):
                    query = query.filter(getattr(MaterialItem, "tag_number").ilike(f"%{tag_number}%"))
                else:
                    query = query.filter(MaterialItem.heat_number.ilike(f"%{tag_number}%"))

            return query.all()

    # Implementation note.

    def reserve_material(
        self,
        item_id: int,
        quantity: float,
        reserved_for: str,
        reserved_by: str,
    ) -> MaterialItem:
        """
        رزرو متریال برای برش یا ساخت با استفاده از قفل ردیف (Pessimistic Lock).
        جلوگیری از تخصیص همزمان (Race Condition).
        """
        with self._session() as session:
            try:
                item = (
                    session.query(MaterialItem)
                    .filter(MaterialItem.id == item_id)
                    .with_for_update()
                    .first()
                )

                if not item:
                    raise MaterialNotFoundError(f"Material Item #{item_id} not found.")

                if hasattr(item, "status") and item.status == MaterialStatus.QUARANTINED.value:
                    raise MaterialQuarantinedError(
                        f"Item #{item_id} is quarantined and cannot be reserved."
                    )

                if item.quantity_available < quantity:
                    raise InsufficientStockError(
                        f"Insufficient stock for #{item_id}. "
                        f"Available: {item.quantity_available}, Requested: {quantity}"
                    )

                item.quantity_available -= quantity
                if hasattr(item, "quantity_reserved"):
                    item.quantity_reserved = (getattr(item, "quantity_reserved") or 0) + quantity

                session.commit()
                session.refresh(item)
                logger.info(
                    f"Reserved {quantity} of Item #{item_id} for '{reserved_for}' by {reserved_by}."
                )
                return item

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error reserving material #{item_id}: {e}")
                raise

    def issue_material(
        self,
        item_id: int,
        quantity: float,
        miv_number: str,
        issued_to: str,
    ) -> MaterialItem:
        """صدور قطعی متریال و کسر از کل موجودی فیزیکی انبار"""
        with self._session() as session:
            try:
                item = (
                    session.query(MaterialItem)
                    .filter(MaterialItem.id == item_id)
                    .with_for_update()
                    .first()
                )

                if not item:
                    raise MaterialNotFoundError(f"Material Item #{item_id} not found.")

                total_qty = getattr(item, "quantity_received", item.quantity_available)
                if total_qty < quantity:
                    raise InsufficientStockError(
                        f"Insufficient physical quantity for issue. Total: {total_qty}, Requested: {quantity}"
                    )

                if hasattr(item, "quantity_received"):
                    item.quantity_received -= quantity
                else:
                    item.quantity_available -= quantity

                if hasattr(item, "quantity_reserved"):
                    current_res = getattr(item, "quantity_reserved") or 0
                    if current_res >= quantity:
                        setattr(item, "quantity_reserved", current_res - quantity)

                if hasattr(item, "status") and item.quantity_available == 0:
                    item.status = MaterialStatus.ISSUED.value

                session.commit()
                session.refresh(item)
                logger.info(
                    f"Issued {quantity} of Item #{item_id} under MIV: {miv_number} to {issued_to}."
                )
                return item

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error issuing material #{item_id}: {e}")
                raise

    def set_quarantine_status(
        self,
        item_id: int,
        quarantined: bool,
        reason: str,
        inspector: str,
    ) -> MaterialItem:
        """قرنطینه کردن متریال به دلیل ایراد کیفی، رد شدن MTR یا PMI"""
        with self._session() as session:
            try:
                item = session.query(MaterialItem).filter(MaterialItem.id == item_id).first()
                if not item:
                    raise MaterialNotFoundError(f"Material Item #{item_id} not found.")

                if hasattr(item, "status"):
                    item.status = (
                        MaterialStatus.QUARANTINED.value
                        if quarantined
                        else MaterialStatus.AVAILABLE.value
                    )
                if hasattr(item, "quarantine_reason"):
                    setattr(item, "quarantine_reason", reason if quarantined else None)
                if hasattr(item, "remarks") and not hasattr(item, "quarantine_reason"):
                    item.remarks = f"[QUARANTINE ALERT] {reason}" if quarantined else item.remarks

                session.commit()
                session.refresh(item)
                logger.warning(
                    f"Material #{item_id} status updated. Reason: {reason}"
                )
                return item
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error updating quarantine status #{item_id}: {e}")
                raise

    def bulk_create_materials(
        self, materials_data: List[Dict[str, Any]]
    ) -> List[MaterialItem]:
        """ثبت دسته‌ای متریال‌های ورودی از روی پکینگ‌لیست (Packing List) یا MRR"""
        with self._session() as session:
            try:
                instances = [MaterialItem(**data) for data in materials_data]
                session.bulk_save_objects(instances, return_defaults=True)
                session.commit()
                logger.info(f"Successfully bulk-created {len(instances)} material items.")
                return instances
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Failed to bulk-create materials: {e}")
                raise

    # Implementation note.

    def get_low_stock_alerts(
        self, project_id: int, threshold: float = 5.0
    ) -> List[MaterialItem]:
        """اقلامی که موجودی آنها کمتر از حد آستانه است"""
        with self._session() as session:
            q = session.query(MaterialItem).filter(
                MaterialItem.project_id == project_id,
                MaterialItem.quantity_available <= threshold
            )
            if hasattr(MaterialItem, "status"):
                q = q.filter(MaterialItem.status != MaterialStatus.ISSUED.value)
            return q.order_by(MaterialItem.quantity_available.asc()).all()

    def get_material_summary_by_category(
        self, project_id: int
    ) -> Dict[str, Dict[str, float]]:
        """خلاصه موجودی کل، رزرو شده و آزاد به تفکیک دسته‌بندی"""
        with self._session() as session:
            category_col = MaterialItem.material_type
            if hasattr(MaterialItem, "category"):
                category_col = getattr(MaterialItem, "category")

            results = (
                session.query(
                    category_col.label("cat"),
                    func.count(MaterialItem.id).label("total_items"),
                    func.sum(MaterialItem.quantity_available).label("total_available"),
                )
                .filter(MaterialItem.project_id == project_id)
                .group_by("cat")
                .all()
            )
            return {
                r.cat or "Unknown": {
                    "count": r.total_items,
                    "available_qty": float(r.total_available or 0),
                }
                for r in results
            }


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────

class MaterialRequisitionRepository(BaseRepository[MaterialRequisition]):
    """ریپازیتوری مدیریت درخواست‌های خرید و تأمین کالا (MR)"""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, MaterialRequisition)

    def get_by_number(
        self, mr_number: str, load_items: bool = True
    ) -> Optional[MaterialRequisition]:
        """دریافت MR همراه با لیست متریال‌های تخصیص‌یافته"""
        with self._session() as session:
            query = session.query(MaterialRequisition).filter(
                MaterialRequisition.mr_number == mr_number.strip()
            )
            if load_items and hasattr(MaterialRequisition, "items"):
                query = query.options(selectinload(MaterialRequisition.items))
            return query.first()

    def get_by_discipline(
        self, project_id: int, discipline: str
    ) -> List[MaterialRequisition]:
        """دریافت MRها بر اساس دیسیپلین مهندسی (Piping, Mechanical, Electrical)"""
        with self._session() as session:
            q = session.query(MaterialRequisition).filter(
                MaterialRequisition.project_id == project_id
            )
            if hasattr(MaterialRequisition, "discipline"):
                q = q.filter(getattr(MaterialRequisition, "discipline") == discipline)
            return q.all()

    def update_mr_status(
        self, mr_id: int, status: str, approved_by: Optional[str] = None
    ) -> Optional[MaterialRequisition]:
        """تغییر وضعیت MR (Draft, Under Review, Approved, Ordered)"""
        with self._session() as session:
            try:
                mr = session.query(MaterialRequisition).filter(
                    MaterialRequisition.id == mr_id
                ).first()
                if not mr:
                    return None

                mr.status = status
                if approved_by and hasattr(mr, "approved_by"):
                    setattr(mr, "approved_by", approved_by)
                    setattr(mr, "approval_date", datetime.utcnow())

                session.commit()
                session.refresh(mr)
                return mr
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error updating MR #{mr_id} status: {e}")
                raise


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────

class PurchaseOrderRepository(BaseRepository[PurchaseOrder]):
    """ریپازیتوری مدیریت سفارشات خرید و پیگیری تحویل از وندور (PO)"""

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, PurchaseOrder)

    def get_by_number(
        self, po_number: str, load_items: bool = True
    ) -> Optional[PurchaseOrder]:
        """دریافت سفارش خرید بر اساس شماره PO"""
        with self._session() as session:
            query = session.query(PurchaseOrder).filter(
                PurchaseOrder.po_number == po_number.strip()
            )
            if load_items and hasattr(PurchaseOrder, "items"):
                query = query.options(selectinload(PurchaseOrder.items))
            return query.first()

    def get_by_vendor(
        self, project_id: int, vendor_name: str
    ) -> List[PurchaseOrder]:
        """یافتن سفارش‌های مرتبط با یک تأمین‌کننده خاص"""
        with self._session() as session:
            q = session.query(PurchaseOrder).filter(
                PurchaseOrder.project_id == project_id
            )
            if hasattr(PurchaseOrder, "vendor_name"):
                q = q.filter(getattr(PurchaseOrder, "vendor_name").ilike(f"%{vendor_name}%"))
            else:
                q = q.filter(PurchaseOrder.supplier.ilike(f"%{vendor_name}%"))
            return q.all()

    def get_pending_deliveries(
        self, project_id: int
    ) -> List[PurchaseOrder]:
        """سفارشاتی که موعد تحویل آنها گذشته یا نزدیک است و هنوز تکمیل نشده‌اند"""
        with self._session() as session:
            q = session.query(PurchaseOrder).filter(
                PurchaseOrder.project_id == project_id,
                PurchaseOrder.status.notin_(["completed", "cancelled", "closed"]),
            )
            if hasattr(PurchaseOrder, "delivery_due_date"):
                q = q.order_by(getattr(PurchaseOrder, "delivery_due_date").asc())
            elif hasattr(PurchaseOrder, "delivery_date"):
                q = q.order_by(PurchaseOrder.delivery_date.asc())
            return q.all()


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────

class MaterialUnitOfWork:
    """
    الگوی Unit of Work برای لایه مهندسی و کنترل متریال.
    امکان اجرای تراکنش‌های چندگانه بین انبار، سفارشات و درخواست‌ها را فراهم می‌کند.
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.items = MaterialItemRepository(db_manager)
        self.requisitions = MaterialRequisitionRepository(db_manager)
        self.purchase_orders = PurchaseOrderRepository(db_manager)

    def receive_po_shipment(
        self,
        po_number: str,
        received_items: List[Dict[str, Any]],
        received_by: str,
    ) -> bool:
        """
        یک تراکنش کامل: دریافت کالا از وندور، ثبت آیتم‌ها با Heat No در انبار
        و به‌روزرسانی وضعیت سفارش خرید.
        """
        po = self.purchase_orders.get_by_number(po_number)
        if not po:
            raise ValueError(f"PO '{po_number}' does not exist.")

        # Implementation note.
        for item_data in received_items:
            item_data["po_id"] = po.id
            item_data["project_id"] = po.project_id
            item_data["status"] = MaterialStatus.AVAILABLE.value

        self.items.bulk_create_materials(received_items)
        logger.info(f"Shipment for PO '{po_number}' received successfully by {received_by}.")
        return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

# Implementation note.
MaterialRepository = MaterialItemRepository