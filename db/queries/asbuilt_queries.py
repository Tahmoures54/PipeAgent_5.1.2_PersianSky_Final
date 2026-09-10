# -*- coding: utf-8 -*-
"""
db/queries/asbuilt_queries.py – PipeAgent v5.2
===============================================
Query / CRUD layer for As-Built & Turnover domain models.

✅ v5.2 – Full alignment with real db/models.py field names:
    • MCCCertificate        → MCCRecord
    • certificate_no        → mcc_no
    • WeldMapEntry.weld_mark → joint_number
    • is_field_weld         → weld_type == "Field"
    • WalkdownChecklist.walkdown_date → inspection_date
    • is_compliant          → derived from status == "Completed"
    • AsBuiltMarkUp.drawing_number → drawing_no
    • incorporated_in_asbuilt → status in ("Incorporated", "Closed", "Approved")

Models covered:
  • IsoRegistry        – رجیستری ایزومتریک‌ها
  • WeldMapEntry       – نقشه جوش روی ایزو
  • MCCRecord          – گواهی تکمیل مکانیکی
  • WalkdownChecklist  – چک‌لیست بازدید نهایی
  • AsBuiltMarkUp      – اصلاحات نقشه‌های چون‌ساخت
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from db.models import (
    AsBuiltMarkUp,
    IsoRegistry,
    MCCRecord,              # ✅ renamed from MCCCertificate
    WalkdownChecklist,
    WeldMapEntry,
)

try:
    from core.exceptions import DatabaseError, ValidationError
except ImportError:
    class DatabaseError(Exception): pass
    class ValidationError(Exception): pass

logger = logging.getLogger(__name__)

# Implementation note.
_FIELD_WELD_ALIASES = ("field", "fw", "site")


__all__ = [
    # ISO Registry
    "get_iso_registry",
    "get_iso_by_id",
    "get_iso_by_number",
    "count_isos",
    "create_iso",
    "update_iso",
    "delete_iso",
    # Weld Map
    "get_weld_map",
    "get_weld_map_entry_by_id",
    "count_weld_map_entries",
    "create_weld_map_entry",
    "create_weld_map_entries_bulk",
    "update_weld_map_entry",
    "delete_weld_map_entry",
    # MCC
    "get_mcc_certificates",
    "get_mcc_by_id",
    "count_mcc_certificates",
    "create_mcc",
    "update_mcc",
    "delete_mcc",
    # Walkdown
    "get_walkdowns",
    "get_walkdown_by_id",
    "count_walkdowns",
    "create_walkdown",
    "update_walkdown",
    "close_walkdown_item",
    "delete_walkdown",
    # As-Built Mark-Up
    "get_asbuilt_markups",
    "get_markup_by_id",
    "count_markups",
    "create_markup",
    "update_markup",
    "delete_markup",
    # Cross-cutting
    "get_asbuilt_dashboard_stats",
]


# ══════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════

def _validate_project_id(project_id: int) -> None:
    """اعتبارسنجی شناسه پروژه."""
    if not isinstance(project_id, int) or project_id <= 0:
        raise ValidationError(
            f"Invalid project_id: {project_id!r}. Must be a positive integer.",
        )


def _apply_pagination(query, *, offset: int = 0, limit: int = 100):
    """اعمال offset/limit روی کوئری."""
    if offset > 0:
        query = query.offset(offset)
    if limit is not None and limit > 0:
        query = query.limit(limit)
    return query


def _safe_update(obj: Any, data: Dict[str, Any], *, exclude: set[str] | None = None) -> int:
    """
    به‌روزرسانی امن فیلدهای یک شیء ORM.
    فقط فیلدهایی که واقعاً روی مدل وجود دارند اعمال می‌شوند.
    تعداد فیلدهای تغییرکرده را برمی‌گرداند.
    """
    exclude = exclude or {"id", "created_at"}
    changed = 0
    for key, value in data.items():
        if key in exclude:
            continue
        if hasattr(obj, key):
            old = getattr(obj, key)
            if old != value:
                setattr(obj, key, value)
                changed += 1
        else:
            logger.warning("Ignoring unknown field '%s' for %s", key, type(obj).__name__)
    return changed


def _field_weld_filter(query):
    """
    فیلتر جوش‌های میدانی با استفاده از weld_type (چون مدل فیلد is_field_weld ندارد).
    Aliases: field, fw, site
    """
    conditions = [WeldMapEntry.weld_type.ilike(f"%{alias}%") for alias in _FIELD_WELD_ALIASES]
    return query.filter(or_(*conditions))


def _shop_weld_filter(query):
    """
    فیلتر جوش‌های کارگاهی (نقیض جوش‌های میدانی).
    """
    conditions = [WeldMapEntry.weld_type.ilike(f"%{alias}%") for alias in _FIELD_WELD_ALIASES]
    return query.filter(~or_(*conditions))


# ══════════════════════════════════════════════
#  1. ISO Registry
# ══════════════════════════════════════════════

def get_iso_registry(
    session: Session,
    project_id: int,
    *,
    status: Optional[str] = None,
    line_number: Optional[str] = None,
    area_id: Optional[int] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = 200,
) -> List[IsoRegistry]:
    """دریافت لیست ایزومتریک‌ها با فیلتر و صفحه‌بندی."""
    _validate_project_id(project_id)
    q = session.query(IsoRegistry).filter(IsoRegistry.project_id == project_id)

    if status:
        q = q.filter(IsoRegistry.status == status)
    if line_number:
        q = q.filter(IsoRegistry.line_number == line_number)
    if area_id is not None:
        q = q.filter(IsoRegistry.area_id == area_id)
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                IsoRegistry.iso_number.ilike(pattern),
                IsoRegistry.line_number.ilike(pattern),
            )
        )

    q = q.order_by(IsoRegistry.iso_number)
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_iso_by_id(session: Session, iso_id: int) -> Optional[IsoRegistry]:
    """دریافت یک ایزومتریک بر اساس شناسه."""
    return session.get(IsoRegistry, iso_id)


def get_iso_by_number(
    session: Session,
    project_id: int,
    iso_number: str,
) -> Optional[IsoRegistry]:
    """دریافت ایزومتریک بر اساس شماره (یکتا در پروژه)."""
    _validate_project_id(project_id)
    return (
        session.query(IsoRegistry)
        .filter(
            IsoRegistry.project_id == project_id,
            IsoRegistry.iso_number == iso_number,
        )
        .first()
    )


def count_isos(
    session: Session,
    project_id: int,
    *,
    status: Optional[str] = None,
) -> int:
    """شمارش ایزومتریک‌ها بدون بارگذاری رکوردها."""
    _validate_project_id(project_id)
    q = session.query(func.count(IsoRegistry.id)).filter(
        IsoRegistry.project_id == project_id,
    )
    if status:
        q = q.filter(IsoRegistry.status == status)
    return q.scalar() or 0


def create_iso(session: Session, **kwargs: Any) -> IsoRegistry:
    """ایجاد رکورد ایزومتریک جدید."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required for IsoRegistry.")
    _validate_project_id(kwargs["project_id"])

    iso = IsoRegistry(**kwargs)
    session.add(iso)
    session.flush()
    logger.info("Created IsoRegistry id=%d iso=%s", iso.id, iso.iso_number)
    return iso


def update_iso(
    session: Session,
    iso_id: int,
    **kwargs: Any,
) -> Optional[IsoRegistry]:
    """به‌روزرسانی فیلدهای ایزومتریک. None اگر یافت نشد."""
    iso = session.get(IsoRegistry, iso_id)
    if iso is None:
        logger.warning("IsoRegistry id=%d not found for update.", iso_id)
        return None

    changed = _safe_update(iso, kwargs)
    if changed:
        session.flush()
        logger.info("Updated IsoRegistry id=%d (%d fields).", iso_id, changed)
    return iso


def delete_iso(session: Session, iso_id: int) -> bool:
    """حذف رکورد ایزومتریک. True اگر حذف شد."""
    iso = session.get(IsoRegistry, iso_id)
    if iso is None:
        return False
    session.delete(iso)
    session.flush()
    logger.info("Deleted IsoRegistry id=%d.", iso_id)
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_weld_map(
    session: Session,
    project_id: int,
    *,
    iso_number: Optional[str] = None,
    line_number: Optional[str] = None,
    is_field_weld: Optional[bool] = None,
    offset: int = 0,
    limit: int = 500,
) -> List[WeldMapEntry]:
    """
    دریافت نقشه جوش با فیلتر.

    Args:
        iso_number:    فیلتر شماره ایزو (exact)
        line_number:   فیلتر شماره خط
        is_field_weld: True  → فقط جوش‌های میدانی
                       False → فقط جوش‌های کارگاهی
                       None  → بدون فیلتر
    """
    _validate_project_id(project_id)
    q = session.query(WeldMapEntry).filter(WeldMapEntry.project_id == project_id)

    if iso_number:
        q = q.filter(WeldMapEntry.iso_number == iso_number)
    if line_number:
        q = q.filter(WeldMapEntry.line_number == line_number)

    # Implementation note.
    if is_field_weld is True:
        q = _field_weld_filter(q)
    elif is_field_weld is False:
        q = _shop_weld_filter(q)

    # Implementation note.
    q = q.order_by(WeldMapEntry.iso_number, WeldMapEntry.joint_number)
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_weld_map_entry_by_id(
    session: Session,
    entry_id: int,
) -> Optional[WeldMapEntry]:
    """دریافت یک Weld Map Entry بر اساس شناسه."""
    return session.get(WeldMapEntry, entry_id)


def count_weld_map_entries(
    session: Session,
    project_id: int,
    *,
    iso_number: Optional[str] = None,
) -> int:
    """شمارش Weld Map Entryها."""
    _validate_project_id(project_id)
    q = session.query(func.count(WeldMapEntry.id)).filter(
        WeldMapEntry.project_id == project_id,
    )
    if iso_number:
        q = q.filter(WeldMapEntry.iso_number == iso_number)
    return q.scalar() or 0


def create_weld_map_entry(session: Session, **kwargs: Any) -> WeldMapEntry:
    """ایجاد یک Weld Map Entry."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required for WeldMapEntry.")

    # Implementation note.
    if "weld_mark" in kwargs and "joint_number" not in kwargs:
        kwargs["joint_number"] = kwargs.pop("weld_mark")
    if "is_field_weld" in kwargs and "weld_type" not in kwargs:
        kwargs["weld_type"] = "Field" if kwargs.pop("is_field_weld") else "Shop"

    entry = WeldMapEntry(**kwargs)
    session.add(entry)
    session.flush()
    return entry


def create_weld_map_entries_bulk(
    session: Session,
    entries: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 100,
) -> int:
    """
    ایجاد دسته‌ای Weld Map Entry (برای وارد کردن از Excel/CSV).
    Returns: تعداد رکوردهای ایجادشده.
    """
    if not entries:
        return 0

    normalized: List[WeldMapEntry] = []
    for data in entries:
        d = dict(data)
        # Implementation note.
        if "weld_mark" in d and "joint_number" not in d:
            d["joint_number"] = d.pop("weld_mark")
        if "is_field_weld" in d and "weld_type" not in d:
            d["weld_type"] = "Field" if d.pop("is_field_weld") else "Shop"
        normalized.append(WeldMapEntry(**d))

    total = len(normalized)
    for i in range(0, total, batch_size):
        batch = normalized[i : i + batch_size]
        session.add_all(batch)
        session.flush()

    logger.info("Bulk created %d WeldMapEntry records.", total)
    return total


def update_weld_map_entry(
    session: Session,
    entry_id: int,
    **kwargs: Any,
) -> Optional[WeldMapEntry]:
    """به‌روزرسانی Weld Map Entry."""
    entry = session.get(WeldMapEntry, entry_id)
    if entry is None:
        return None

    # Implementation note.
    if "weld_mark" in kwargs and "joint_number" not in kwargs:
        kwargs["joint_number"] = kwargs.pop("weld_mark")
    if "is_field_weld" in kwargs and "weld_type" not in kwargs:
        kwargs["weld_type"] = "Field" if kwargs.pop("is_field_weld") else "Shop"

    _safe_update(entry, kwargs)
    session.flush()
    return entry


def delete_weld_map_entry(session: Session, entry_id: int) -> bool:
    """حذف Weld Map Entry."""
    entry = session.get(WeldMapEntry, entry_id)
    if entry is None:
        return False
    session.delete(entry)
    session.flush()
    return True


# ══════════════════════════════════════════════
#  3. MCC Record  (✅ renamed from MCCCertificate)
# ══════════════════════════════════════════════

def get_mcc_certificates(
    session: Session,
    project_id: int,
    *,
    status: Optional[str] = None,
    system_name: Optional[str] = None,
    area_id: Optional[int] = None,     # Implementation note.
    offset: int = 0,
    limit: int = 100,
) -> List[MCCRecord]:
    """دریافت گواهی‌های تکمیل مکانیکی با فیلتر."""
    _validate_project_id(project_id)
    q = session.query(MCCRecord).filter(MCCRecord.project_id == project_id)

    if status:
        q = q.filter(MCCRecord.status == status)
    if system_name:
        q = q.filter(MCCRecord.system_name.ilike(f"%{system_name}%"))
    # Implementation note.
    if area_id is not None:
        logger.debug("MCCRecord has no area_id; ignoring filter area_id=%s", area_id)

    # Implementation note.
    q = q.order_by(MCCRecord.created_at.desc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_mcc_by_id(session: Session, mcc_id: int) -> Optional[MCCRecord]:
    """دریافت MCC بر اساس شناسه."""
    return session.get(MCCRecord, mcc_id)


def count_mcc_certificates(
    session: Session,
    project_id: int,
    *,
    status: Optional[str] = None,
) -> int:
    """شمارش MCCها."""
    _validate_project_id(project_id)
    q = session.query(func.count(MCCRecord.id)).filter(
        MCCRecord.project_id == project_id,
    )
    if status:
        q = q.filter(MCCRecord.status == status)
    return q.scalar() or 0


def create_mcc(session: Session, **kwargs: Any) -> MCCRecord:
    """ایجاد گواهی تکمیل مکانیکی جدید."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required for MCCRecord.")

    # Implementation note.
    if "certificate_no" in kwargs and "mcc_no" not in kwargs:
        kwargs["mcc_no"] = kwargs.pop("certificate_no")
    if "subsystem_code" in kwargs and "subsystem" not in kwargs:
        kwargs["subsystem"] = kwargs.pop("subsystem_code")
    if "issued_by_contractor" in kwargs and "issued_by" not in kwargs:
        kwargs["issued_by"] = kwargs.pop("issued_by_contractor")
    if "hydro_complete" in kwargs and "hydro_test_complete" not in kwargs:
        kwargs["hydro_test_complete"] = kwargs.pop("hydro_complete")

    mcc = MCCRecord(**kwargs)
    session.add(mcc)
    session.flush()
    logger.info("Created MCCRecord id=%d mcc_no=%s", mcc.id, mcc.mcc_no)
    return mcc


def update_mcc(
    session: Session,
    mcc_id: int,
    **kwargs: Any,
) -> Optional[MCCRecord]:
    """به‌روزرسانی MCC."""
    mcc = session.get(MCCRecord, mcc_id)
    if mcc is None:
        return None

    # Implementation note.
    if "certificate_no" in kwargs and "mcc_no" not in kwargs:
        kwargs["mcc_no"] = kwargs.pop("certificate_no")

    _safe_update(mcc, kwargs)
    session.flush()
    return mcc


def delete_mcc(session: Session, mcc_id: int) -> bool:
    """حذف MCC."""
    mcc = session.get(MCCRecord, mcc_id)
    if mcc is None:
        return False
    session.delete(mcc)
    session.flush()
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_walkdowns(
    session: Session,
    project_id: int,
    *,
    status: Optional[str] = None,
    walkdown_type: Optional[str] = None,
    line_number: Optional[str] = None,
    area_id: Optional[int] = None,
    is_compliant: Optional[bool] = None,
    offset: int = 0,
    limit: int = 200,
) -> List[WalkdownChecklist]:
    """
    دریافت چک‌لیست‌های بازدید نهایی.

    Args:
        walkdown_type: Pre-Hydro, Pre-Comm, Final, Client, یا Cat A/B/C
        is_compliant:  True  → فقط آیتم‌های Completed
                       False → فقط آیتم‌های غیر Completed
                       (چون مدل فیلد is_compliant ندارد)
    """
    _validate_project_id(project_id)
    q = session.query(WalkdownChecklist).filter(
        WalkdownChecklist.project_id == project_id,
    )

    if status:
        q = q.filter(WalkdownChecklist.status == status)
    if walkdown_type:
        q = q.filter(WalkdownChecklist.walkdown_type == walkdown_type)
    if line_number:
        q = q.filter(WalkdownChecklist.line_number == line_number)
    if area_id is not None:
        q = q.filter(WalkdownChecklist.area_id == area_id)

    # Implementation note.
    if is_compliant is True:
        q = q.filter(WalkdownChecklist.status == "Completed")
    elif is_compliant is False:
        q = q.filter(WalkdownChecklist.status != "Completed")

    # ✅ walkdown_date → inspection_date
    q = q.order_by(WalkdownChecklist.inspection_date.desc().nullslast())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_walkdown_by_id(
    session: Session,
    item_id: int,
) -> Optional[WalkdownChecklist]:
    """دریافت آیتم Walkdown بر اساس شناسه."""
    return session.get(WalkdownChecklist, item_id)


def count_walkdowns(
    session: Session,
    project_id: int,
    *,
    status: Optional[str] = None,
) -> int:
    """شمارش Walkdownها."""
    _validate_project_id(project_id)
    q = session.query(func.count(WalkdownChecklist.id)).filter(
        WalkdownChecklist.project_id == project_id,
    )
    if status:
        q = q.filter(WalkdownChecklist.status == status)
    return q.scalar() or 0


def create_walkdown(session: Session, **kwargs: Any) -> WalkdownChecklist:
    """ایجاد آیتم چک‌لیست بازدید."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required for WalkdownChecklist.")

    # Implementation note.
    if "walkdown_date" in kwargs and "inspection_date" not in kwargs:
        kwargs["inspection_date"] = kwargs.pop("walkdown_date")
    if "check_category" in kwargs and "walkdown_type" not in kwargs:
        kwargs["walkdown_type"] = kwargs.pop("check_category")

    item = WalkdownChecklist(**kwargs)
    session.add(item)
    session.flush()
    return item


def update_walkdown(
    session: Session,
    item_id: int,
    **kwargs: Any,
) -> Optional[WalkdownChecklist]:
    """به‌روزرسانی آیتم Walkdown."""
    item = session.get(WalkdownChecklist, item_id)
    if item is None:
        return None

    # Implementation note.
    if "walkdown_date" in kwargs and "inspection_date" not in kwargs:
        kwargs["inspection_date"] = kwargs.pop("walkdown_date")
    if "check_category" in kwargs and "walkdown_type" not in kwargs:
        kwargs["walkdown_type"] = kwargs.pop("check_category")

    _safe_update(item, kwargs)
    session.flush()
    return item


def close_walkdown_item(
    session: Session,
    item_id: int,
    *,
    closed_by: Optional[str] = None,
) -> Optional[WalkdownChecklist]:
    """
    بستن یک آیتم Walkdown.

    ✅ اصلاح: مدل WalkdownChecklist فیلدهای closed_date یا responsible ندارد.
       از status="Completed" و remark استفاده می‌کنیم.
    """
    item = session.get(WalkdownChecklist, item_id)
    if item is None:
        logger.warning("WalkdownChecklist id=%d not found.", item_id)
        return None

    if item.status == "Completed":
        logger.info("WalkdownChecklist id=%d already completed.", item_id)
        return item

    item.status = "Completed"

    # Implementation note.
    if closed_by:
        current = item.remarks or ""
        item.remarks = f"{current} | Closed by {closed_by} on {date.today()}".strip(" |")

    session.flush()
    logger.info("Closed WalkdownChecklist id=%d by %s.", item_id, closed_by or "system")
    return item


def delete_walkdown(session: Session, item_id: int) -> bool:
    """حذف آیتم Walkdown."""
    item = session.get(WalkdownChecklist, item_id)
    if item is None:
        return False
    session.delete(item)
    session.flush()
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

# Implementation note.
_INCORPORATED_STATUSES = ("Incorporated", "Closed", "Approved")


def get_asbuilt_markups(
    session: Session,
    project_id: int,
    *,
    iso_number: Optional[str] = None,
    drawing_number: Optional[str] = None,     # Implementation note.
    status: Optional[str] = None,
    markup_type: Optional[str] = None,
    incorporated_only: bool = False,
    offset: int = 0,
    limit: int = 100,
) -> List[AsBuiltMarkUp]:
    """
    دریافت اصلاحات نقشه‌های چون‌ساخت.

    Args:
        iso_number:        جستجوی جزئی (ILIKE)
        drawing_number:    جستجوی جزئی روی drawing_no
        markup_type:       Dimension Change, Route Change, ...
        incorporated_only: فقط اصلاحات وارد‌شده در As-Built
                           (status ∈ Incorporated/Closed/Approved)
    """
    _validate_project_id(project_id)
    q = session.query(AsBuiltMarkUp).filter(
        AsBuiltMarkUp.project_id == project_id,
    )

    if iso_number:
        q = q.filter(AsBuiltMarkUp.iso_number.ilike(f"%{iso_number}%"))

    # ✅ drawing_number → drawing_no
    if drawing_number:
        q = q.filter(AsBuiltMarkUp.drawing_no.ilike(f"%{drawing_number}%"))

    if status:
        q = q.filter(AsBuiltMarkUp.status == status)
    if markup_type:
        q = q.filter(AsBuiltMarkUp.markup_type == markup_type)

    # ✅ incorporated_in_asbuilt → status in ("Incorporated","Closed","Approved")
    if incorporated_only:
        q = q.filter(AsBuiltMarkUp.status.in_(_INCORPORATED_STATUSES))

    q = q.order_by(AsBuiltMarkUp.created_at.desc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_markup_by_id(session: Session, markup_id: int) -> Optional[AsBuiltMarkUp]:
    """دریافت Mark-Up بر اساس شناسه."""
    return session.get(AsBuiltMarkUp, markup_id)


def count_markups(
    session: Session,
    project_id: int,
    *,
    status: Optional[str] = None,
) -> int:
    """شمارش Mark-Upها."""
    _validate_project_id(project_id)
    q = session.query(func.count(AsBuiltMarkUp.id)).filter(
        AsBuiltMarkUp.project_id == project_id,
    )
    if status:
        q = q.filter(AsBuiltMarkUp.status == status)
    return q.scalar() or 0


def create_markup(session: Session, **kwargs: Any) -> AsBuiltMarkUp:
    """ایجاد Mark-Up جدید."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required for AsBuiltMarkUp.")

    # Implementation note.
    if "drawing_number" in kwargs and "drawing_no" not in kwargs:
        kwargs["drawing_no"] = kwargs.pop("drawing_number")
    if "markup_description" in kwargs and "description" not in kwargs:
        kwargs["description"] = kwargs.pop("markup_description")

    markup = AsBuiltMarkUp(**kwargs)
    session.add(markup)
    session.flush()
    return markup


def update_markup(
    session: Session,
    markup_id: int,
    **kwargs: Any,
) -> Optional[AsBuiltMarkUp]:
    """به‌روزرسانی Mark-Up."""
    markup = session.get(AsBuiltMarkUp, markup_id)
    if markup is None:
        return None

    # Implementation note.
    if "drawing_number" in kwargs and "drawing_no" not in kwargs:
        kwargs["drawing_no"] = kwargs.pop("drawing_number")
    if "incorporated_in_asbuilt" in kwargs and "status" not in kwargs:
        kwargs["status"] = (
            "Incorporated" if kwargs.pop("incorporated_in_asbuilt") else "Draft"
        )

    _safe_update(markup, kwargs)
    session.flush()
    return markup


def delete_markup(session: Session, markup_id: int) -> bool:
    """حذف Mark-Up."""
    markup = session.get(AsBuiltMarkUp, markup_id)
    if markup is None:
        return False
    session.delete(markup)
    session.flush()
    return True


# ══════════════════════════════════════════════
#  6. Cross-Cutting: Dashboard Stats
# ══════════════════════════════════════════════

def get_asbuilt_dashboard_stats(
    session: Session,
    project_id: int,
) -> Dict[str, Any]:
    """
    آمار کلی داشبورد As-Built برای یک پروژه.

    Returns:
        {
            "iso_total": 120,
            "iso_asbuilt": 85,
            "weld_map_total": 1450,
            "mcc_total": 12,
            "mcc_approved": 8,
            "walkdown_open": 34,
            "walkdown_closed": 120,
            "markup_pending": 15,
            "markup_incorporated": 42,
        }
    """
    _validate_project_id(project_id)

    iso_total = count_isos(session, project_id)
    iso_asbuilt = count_isos(session, project_id, status="As-Built")

    weld_map_total = count_weld_map_entries(session, project_id)

    mcc_total = count_mcc_certificates(session, project_id)
    mcc_approved = count_mcc_certificates(session, project_id, status="Approved")

    # Implementation note.
    # Implementation note.
    walkdown_open = (
        session.query(func.count(WalkdownChecklist.id))
        .filter(
            WalkdownChecklist.project_id == project_id,
            WalkdownChecklist.status.in_(("Open", "In Progress")),
        )
        .scalar() or 0
    )
    walkdown_closed = count_walkdowns(session, project_id, status="Completed")

    # Implementation note.
    markup_pending = count_markups(session, project_id, status="Draft")

    # ✅ markup_incorporated → status in ("Incorporated","Closed","Approved")
    markup_incorporated = (
        session.query(func.count(AsBuiltMarkUp.id))
        .filter(
            AsBuiltMarkUp.project_id == project_id,
            AsBuiltMarkUp.status.in_(_INCORPORATED_STATUSES),
        )
        .scalar() or 0
    )

    return {
        "iso_total": iso_total,
        "iso_asbuilt": iso_asbuilt,
        "iso_completion_pct": round(iso_asbuilt / iso_total * 100, 1) if iso_total else 0,
        "weld_map_total": weld_map_total,
        "mcc_total": mcc_total,
        "mcc_approved": mcc_approved,
        "walkdown_open": walkdown_open,
        "walkdown_closed": walkdown_closed,
        "markup_pending": markup_pending,
        "markup_incorporated": markup_incorporated,
    }