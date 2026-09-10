# -*- coding: utf-8 -*-
"""
db/queries/finishing_queries.py – PipeAgent v5.1
=================================================
Industrial-grade query and CRUD layer for piping finishing works:
  • PWHT (Post-Weld Heat Treatment)
  • Flange Bolt Torquing & Tensioning
  • Industrial Painting & Surface Preparation
  • Thermal Insulation (Hot, Cold, Acoustic)
  • Post-Hydrotest Reinstatement Checklists

This module implements SQLAlchemy 2.0 best practices, thread-safe session
handling, batch operations, pagination, and detailed dashboard statistics.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from db.models import (
    FlangeTorqueRecord,
    InsulationRecord,
    PaintingRecord,
    PWHTRecord,
    ReinstatementItem,
)

# Implementation note.
try:
    from core.exceptions import DatabaseError, ValidationError
except ImportError:
    class DatabaseError(Exception): pass
    class ValidationError(Exception): pass

logger = logging.getLogger(__name__)

__all__ = [
    # Painting
    "get_painting_records",
    "get_painting_record_by_id",
    "count_painting_records",
    "create_painting_record",
    "update_painting_record",
    "delete_painting_record",
    # Insulation
    "get_insulation_records",
    "get_insulation_record_by_id",
    "count_insulation_records",
    "create_insulation_record",
    "update_insulation_record",
    "delete_insulation_record",
    # Flange Torque
    "get_flange_torque_records",
    "get_flange_torque_record_by_id",
    "count_flange_torque_records",
    "create_flange_torque_record",
    "create_flange_torque_records_bulk",
    "update_flange_torque_record",
    "delete_flange_torque_record",
    # PWHT
    "get_pwht_records",
    "get_pwht_record_by_id",
    "count_pwht_records",
    "create_pwht_record",
    "update_pwht_record",
    "delete_pwht_record",
    # Reinstatement
    "get_reinstatement_items",
    "get_reinstatement_item_by_id",
    "count_reinstatement_items",
    "create_reinstatement_item",
    "create_reinstatement_items_bulk",
    "update_reinstatement_item",
    "complete_reinstatement_item",
    "delete_reinstatement_item",
    # Dashboard stats
    "get_finishing_dashboard_stats",
]


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────

def _validate_project_id(project_id: int) -> None:
    """اعتبارسنجی شناسه پروژه برای جلوگیری از تداخل امنیتی داده‌ها."""
    if not isinstance(project_id, int) or project_id <= 0:
        raise ValidationError(f"Invalid project_id: {project_id!r}. Must be a positive integer.")


def _apply_pagination(query, *, offset: int = 0, limit: int = 100):
    """اعمال صفحه‌بندی استاندارد روی کوئری‌ها."""
    if offset > 0:
        query = query.offset(offset)
    if limit is not None and limit > 0:
        query = query.limit(limit)
    return query


def _safe_update(obj: Any, data: Dict[str, Any], *, exclude: Optional[Set[str]] = None) -> int:
    """به‌روزرسانی امن فیلدهای یک ردیف پایگاه داده."""
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
# Implementation note.
# ══════════════════════════════════════════════

def get_painting_records(
    session: Session,
    project_id: int,
    *,
    line_number: Optional[str] = None,
    spool_number: Optional[str] = None,
    result: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[PaintingRecord]:
    """دریافت سوابق رنگ‌آمیزی خطوط با فیلترهای فنی و صفحه‌بندی."""
    _validate_project_id(project_id)
    q = session.query(PaintingRecord).filter(PaintingRecord.project_id == project_id)

    if line_number:
        q = q.filter(PaintingRecord.line_number.ilike(f"%{line_number}%"))
    if spool_number:
        q = q.filter(PaintingRecord.spool_number.ilike(f"%{spool_number}%"))
    if result:
        q = q.filter(PaintingRecord.result == result)

    q = q.order_by(PaintingRecord.performed_date.desc().nullslast())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_painting_record_by_id(session: Session, record_id: int) -> Optional[PaintingRecord]:
    """دریافت رکورد رنگ‌آمیزی بر اساس شناسه (SQLAlchemy 2.0)."""
    return session.get(PaintingRecord, record_id)


def count_painting_records(session: Session, project_id: int, *, result: Optional[str] = None) -> int:
    """شمارش تعداد رکوردهای رنگ‌آمیزی."""
    _validate_project_id(project_id)
    q = session.query(func.count(PaintingRecord.id)).filter(PaintingRecord.project_id == project_id)
    if result:
        q = q.filter(PaintingRecord.result == result)
    return q.scalar() or 0


def create_painting_record(session: Session, **kwargs: Any) -> PaintingRecord:
    """ثبت سوابق رنگ‌آمیزی جدید."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a PaintingRecord.")
    _validate_project_id(kwargs["project_id"])

    record = PaintingRecord(**kwargs)
    session.add(record)
    session.flush()
    logger.info("Created PaintingRecord ID=%d for Line=%s", record.id, record.line_number)
    return record


def update_painting_record(session: Session, record_id: int, **kwargs: Any) -> Optional[PaintingRecord]:
    """به‌روزرسانی اطلاعات ثبت‌شده رنگ‌آمیزی."""
    record = session.get(PaintingRecord, record_id)
    if record is None:
        return None

    changed = _safe_update(record, kwargs)
    if changed:
        session.flush()
        logger.info("Updated PaintingRecord ID=%d (%d fields modified).", record_id, changed)
    return record


def delete_painting_record(session: Session, record_id: int) -> bool:
    """حذف سوابق رنگ‌آمیزی از سیستم."""
    record = session.get(PaintingRecord, record_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    logger.info("Deleted PaintingRecord ID=%d.", record_id)
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_insulation_records(
    session: Session,
    project_id: int,
    *,
    line_number: Optional[str] = None,
    insulation_type: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[InsulationRecord]:
    """دریافت سوابق عایق‌کاری خطوط با فیلترها و صفحه‌بندی."""
    _validate_project_id(project_id)
    q = session.query(InsulationRecord).filter(InsulationRecord.project_id == project_id)

    if line_number:
        q = q.filter(InsulationRecord.line_number.ilike(f"%{line_number}%"))
    if insulation_type:
        q = q.filter(InsulationRecord.insulation_type == insulation_type)
    if status:
        q = q.filter(InsulationRecord.status == status)

    q = q.order_by(InsulationRecord.performed_date.desc().nullslast())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_insulation_record_by_id(session: Session, record_id: int) -> Optional[InsulationRecord]:
    """دریافت رکورد عایق‌کاری بر اساس شناسه."""
    return session.get(InsulationRecord, record_id)


def count_insulation_records(session: Session, project_id: int, *, status: Optional[str] = None) -> int:
    """شمارش تعداد رکوردهای عایق‌کاری خطوط."""
    _validate_project_id(project_id)
    q = session.query(func.count(InsulationRecord.id)).filter(InsulationRecord.project_id == project_id)
    if status:
        q = q.filter(InsulationRecord.status == status)
    return q.scalar() or 0


def create_insulation_record(session: Session, **kwargs: Any) -> InsulationRecord:
    """ثبت اطلاعات عایق‌کاری خط جدید."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create an InsulationRecord.")
    _validate_project_id(kwargs["project_id"])

    record = InsulationRecord(**kwargs)
    session.add(record)
    session.flush()
    logger.info("Created InsulationRecord ID=%d for Line=%s", record.id, record.line_number)
    return record


def update_insulation_record(session: Session, record_id: int, **kwargs: Any) -> Optional[InsulationRecord]:
    """به‌روزرسانی اطلاعات عایق‌کاری ثبت شده."""
    record = session.get(InsulationRecord, record_id)
    if record is None:
        return None

    changed = _safe_update(record, kwargs)
    if changed:
        session.flush()
        logger.info("Updated InsulationRecord ID=%d (%d fields modified).", record_id, changed)
    return record


def delete_insulation_record(session: Session, record_id: int) -> bool:
    """حذف سوابق عایق‌کاری از سیستم."""
    record = session.get(InsulationRecord, record_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    logger.info("Deleted InsulationRecord ID=%d.", record_id)
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_flange_torque_records(
    session: Session,
    project_id: int,
    *,
    line_number: Optional[str] = None,
    flange_tag: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[FlangeTorqueRecord]:
    """دریافت سوابق گشتاور و سفت‌کردن اتصالات فلانژی."""
    _validate_project_id(project_id)
    q = session.query(FlangeTorqueRecord).filter(FlangeTorqueRecord.project_id == project_id)

    if line_number:
        q = q.filter(FlangeTorqueRecord.line_number.ilike(f"%{line_number}%"))
    if flange_tag:
        q = q.filter(FlangeTorqueRecord.flange_tag.ilike(f"%{flange_tag}%"))
    if status:
        q = q.filter(FlangeTorqueRecord.status == status)

    q = q.order_by(FlangeTorqueRecord.performed_date.desc().nullslast())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_flange_torque_record_by_id(session: Session, record_id: int) -> Optional[FlangeTorqueRecord]:
    """دریافت سوابق گشتاور فلانژ بر اساس شناسه."""
    return session.get(FlangeTorqueRecord, record_id)


def count_flange_torque_records(session: Session, project_id: int, *, status: Optional[str] = None) -> int:
    """شمارش سوابق پیچ‌کشی فلانژها."""
    _validate_project_id(project_id)
    q = session.query(func.count(FlangeTorqueRecord.id)).filter(FlangeTorqueRecord.project_id == project_id)
    if status:
        q = q.filter(FlangeTorqueRecord.status == status)
    return q.scalar() or 0


def create_flange_torque_record(session: Session, **kwargs: Any) -> FlangeTorqueRecord:
    """ثبت رکورد پیچ‌کشی فلانژ جدید."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a FlangeTorqueRecord.")
    _validate_project_id(kwargs["project_id"])

    record = FlangeTorqueRecord(**kwargs)
    session.add(record)
    session.flush()
    logger.info("Created FlangeTorqueRecord ID=%d Tag=%s", record.id, record.flange_tag)
    return record


def create_flange_torque_records_bulk(
    session: Session,
    records_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 100,
) -> int:
    """ثبت دسته‌ای سوابق گشتاور فلانژها (مناسب برای وارد کردن از فایل اکسل)."""
    if not records_data:
        return 0

    records = [FlangeTorqueRecord(**data) for data in records_data]
    total = len(records)

    for i in range(0, total, batch_size):
        batch = records[i : i + batch_size]
        session.add_all(batch)
        session.flush()

    logger.info("Bulk imported %d FlangeTorqueRecords.", total)
    return total


def update_flange_torque_record(session: Session, record_id: int, **kwargs: Any) -> Optional[FlangeTorqueRecord]:
    """به‌روزرسانی مقادیر پیچ‌کشی فلانژ."""
    record = session.get(FlangeTorqueRecord, record_id)
    if record is None:
        return None

    changed = _safe_update(record, kwargs)
    if changed:
        session.flush()
        logger.info("Updated FlangeTorqueRecord ID=%d (%d fields modified).", record_id, changed)
    return record


def delete_flange_torque_record(session: Session, record_id: int) -> bool:
    """حذف سوابق فلانژ از پایگاه داده."""
    record = session.get(FlangeTorqueRecord, record_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    logger.info("Deleted FlangeTorqueRecord ID=%d.", record_id)
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_pwht_records(
    session: Session,
    project_id: int,
    *,
    weld_id_fk: Optional[int] = None,
    result: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[PWHTRecord]:
    """دریافت سوابق عملیات حرارتی پس از جوشکاری (تنش‌زدایی حرارتی سرجوش‌ها)."""
    _validate_project_id(project_id)
    q = session.query(PWHTRecord).filter(PWHTRecord.project_id == project_id)

    if weld_id_fk is not None:
        q = q.filter(PWHTRecord.weld_id_fk == weld_id_fk)
    if result:
        q = q.filter(PWHTRecord.result == result)

    q = q.order_by(PWHTRecord.performed_date.desc().nullslast())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_pwht_record_by_id(session: Session, record_id: int) -> Optional[PWHTRecord]:
    """دریافت اطلاعات تنش‌زدایی سرجوش با شناسه."""
    return session.get(PWHTRecord, record_id)


def count_pwht_records(session: Session, project_id: int, *, result: Optional[str] = None) -> int:
    """شمارش سرجوش‌های تنش‌زدایی شده."""
    _validate_project_id(project_id)
    q = session.query(func.count(PWHTRecord.id)).filter(PWHTRecord.project_id == project_id)
    if result:
        q = q.filter(PWHTRecord.result == result)
    return q.scalar() or 0


def create_pwht_record(session: Session, **kwargs: Any) -> PWHTRecord:
    """ثبت سوابق عملیات حرارتی جدید جوش."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a PWHTRecord.")
    _validate_project_id(kwargs["project_id"])

    record = PWHTRecord(**kwargs)
    session.add(record)
    session.flush()
    logger.info("Created PWHTRecord ID=%d for WeldFK=%d", record.id, record.weld_id_fk)
    return record


def update_pwht_record(session: Session, record_id: int, **kwargs: Any) -> Optional[PWHTRecord]:
    """به‌روزرسانی نمودارها و سوابق حرارتی جوش."""
    record = session.get(PWHTRecord, record_id)
    if record is None:
        return None

    changed = _safe_update(record, kwargs)
    if changed:
        session.flush()
        logger.info("Updated PWHTRecord ID=%d (%d fields modified).", record_id, changed)
    return record


def delete_pwht_record(session: Session, record_id: int) -> bool:
    """حذف سوابق تنش‌زدایی سرجوش."""
    record = session.get(PWHTRecord, record_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    logger.info("Deleted PWHTRecord ID=%d.", record_id)
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_reinstatement_items(
    session: Session,
    project_id: int,
    *,
    test_package_id: Optional[int] = None,
    line_number: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = 0,
    limit: int = 200,
) -> List[ReinstatementItem]:
    """دریافت چک‌لیست بازگردانی اقلام موقت خطوط پس از هیدروتست (خارج کردن کورکن‌ها و قرار دادن اوریفیس‌ها)."""
    _validate_project_id(project_id)
    q = session.query(ReinstatementItem).filter(ReinstatementItem.project_id == project_id)

    if test_package_id is not None:
        q = q.filter(ReinstatementItem.test_package_id == test_package_id)
    if line_number:
        q = q.filter(ReinstatementItem.line_number.ilike(f"%{line_number}%"))
    if status:
        q = q.filter(ReinstatementItem.status == status)

    q = q.order_by(ReinstatementItem.created_at.desc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_reinstatement_item_by_id(session: Session, item_id: int) -> Optional[ReinstatementItem]:
    """دریافت یک آیتم چک‌لیست بازگردانی با شناسه."""
    return session.get(ReinstatementItem, item_id)


def count_reinstatement_items(session: Session, project_id: int, *, status: Optional[str] = None) -> int:
    """شمارش ردیف‌های بازگردانی خطوط."""
    _validate_project_id(project_id)
    q = session.query(func.count(ReinstatementItem.id)).filter(ReinstatementItem.project_id == project_id)
    if status:
        q = q.filter(ReinstatementItem.status == status)
    return q.scalar() or 0


def create_reinstatement_item(session: Session, **kwargs: Any) -> ReinstatementItem:
    """ایجاد ردیف چک‌لیست بازگردانی جدید برای خط."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a ReinstatementItem.")
    _validate_project_id(kwargs["project_id"])

    item = ReinstatementItem(**kwargs)
    session.add(item)
    session.flush()
    return item


def create_reinstatement_items_bulk(
    session: Session,
    items_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 100,
) -> int:
    """ایجاد دسته‌ای چک‌لیست بازگردانی خطوط پس از هیدروتست."""
    if not items_data:
        return 0

    items = [ReinstatementItem(**data) for data in items_data]
    total = len(items)

    for i in range(0, total, batch_size):
        batch = items[i : i + batch_size]
        session.add_all(batch)
        session.flush()

    logger.info("Bulk created %d ReinstatementItems.", total)
    return total


def update_reinstatement_item(session: Session, item_id: int, **kwargs: Any) -> Optional[ReinstatementItem]:
    """به‌روزرسانی ردیف بازگردانی خط."""
    item = session.get(ReinstatementItem, item_id)
    if item is None:
        return None

    changed = _safe_update(item, kwargs)
    if changed:
        session.flush()
        logger.info("Updated ReinstatementItem ID=%d (%d fields modified).", item_id, changed)
    return item


def complete_reinstatement_item(
    session: Session,
    item_id: int,
    verified_by: str,
    *,
    remarks: Optional[str] = None,
) -> Optional[ReinstatementItem]:
    """
    تأیید نهایی و ثبت وضعیت 'Completed' برای آیتم بازگردانی خط.
    (حذف کورکن‌های موقت، قرار دادن گسکت‌های دائمی و بستن فلانژها با تورک نهایی).
    """
    item = session.get(ReinstatementItem, item_id)
    if item is None:
        logger.warning("ReinstatementItem ID=%d not found.", item_id)
        return None

    item.temporary_item_removed = True
    item.permanent_item_installed = True
    item.torque_verified = True
    item.verified_by = verified_by
    item.verified_date = date.today()
    item.status = "Completed"
    if remarks:
        item.remarks = remarks

    session.flush()
    logger.info("Reinstatement Item ID=%d marked as Completed by %s.", item_id, verified_by)
    return item


def delete_reinstatement_item(session: Session, item_id: int) -> bool:
    """حذف فیزیکی آیتم بازگردانی."""
    item = session.get(ReinstatementItem, item_id)
    if item is None:
        return False
    session.delete(item)
    session.flush()
    logger.info("Deleted ReinstatementItem ID=%d.", item_id)
    return True


# ══════════════════════════════════════════════
#  6. Cross-Cutting: Dashboard stats
# ══════════════════════════════════════════════

def get_finishing_dashboard_stats(session: Session, project_id: int) -> Dict[str, Any]:
    """
    ارائه آمار تجمعی و پیشرفت کارهای نهایی پروژه (پیش‌نیاز تکمیل مکانیکی خطوط).
    جهت نمایش در چارت‌ها و ویجت‌های مدیریتی کارفرما.
    """
    _validate_project_id(project_id)

    # Implementation note.
    p_total = count_painting_records(session, project_id)
    p_passed = count_painting_records(session, project_id, result="Accept")

    # Implementation note.
    i_total = count_insulation_records(session, project_id)
    i_completed = count_insulation_records(session, project_id, status="Completed")

    # Implementation note.
    t_total = count_flange_torque_records(session, project_id)
    t_completed = count_flange_torque_records(session, project_id, status="Completed")

    # Implementation note.
    r_total = count_reinstatement_items(session, project_id)
    r_completed = count_reinstatement_items(session, project_id, status="Completed")

    # Implementation note.
    pwht_total = count_pwht_records(session, project_id)
    pwht_passed = count_pwht_records(session, project_id, result="Accept")

    return {
        "painting": {
            "total_records": p_total,
            "accepted_records": p_passed,
            "progress_pct": round(p_passed / p_total * 100, 1) if p_total else 0.0,
        },
        "insulation": {
            "total_records": i_total,
            "completed_records": i_completed,
            "progress_pct": round(i_completed / i_total * 100, 1) if i_total else 0.0,
        },
        "flange_torque": {
            "total_joints": t_total,
            "completed_joints": t_completed,
            "progress_pct": round(t_completed / t_total * 100, 1) if t_total else 0.0,
        },
        "reinstatement": {
            "total_items": r_total,
            "completed_items": r_completed,
            "progress_pct": round(r_completed / r_total * 100, 1) if r_total else 0.0,
        },
        "pwht": {
            "total_welds": pwht_total,
            "accepted_welds": pwht_passed,
            "progress_pct": round(pwht_passed / pwht_total * 100, 1) if pwht_total else 0.0,
        },
    }