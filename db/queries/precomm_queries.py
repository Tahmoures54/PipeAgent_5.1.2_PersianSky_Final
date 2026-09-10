# -*- coding: utf-8 -*-
"""
db/queries/precomm_queries.py – PipeAgent v5.1
================================================
Enterprise Pre-commissioning & Mechanical Completion Query Layer.

Covers:
  • Piping System Flushing & Air/Steam Blowing Records
  • Sensitive Leak Testing (Bubble, Helium, Nitrogen)
  • Equipment final internal inspection & Box-Up workflow
  • Dynamic Alloy Verification (PMI Testing)
  • Isometric Dimensional Audits
  • Spring Hanger Preset & Load Verification (Cold/Hot sets)
  • Warehouse Material Preservation audits

Optimized for SQLAlchemy 2.0, fully typed, paginated, and featuring
bulk import support and high-performance aggregate stats.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from db.models import (
    BoxUpRecord,
    DimensionalCheckRecord,
    FlushingRecord,
    LeakTestRecord,
    MaterialPreservationRecord,
    PMITestRecord,
    SpringHangerRecord,
)

# Implementation note.
try:
    from core.exceptions import DatabaseError, ValidationError
except ImportError:
    class DatabaseError(Exception): pass
    class ValidationError(Exception): pass

logger = logging.getLogger(__name__)

__all__ = [
    # Flushing
    "get_flushing_records",
    "get_flushing_record_by_id",
    "count_flushing_records",
    "create_flushing",
    "create_flushing_bulk",
    "update_flushing",
    "delete_flushing",
    # Leak Test
    "get_leak_tests",
    "get_leak_test_by_id",
    "count_leak_tests",
    "create_leak_test",
    "update_leak_test",
    "delete_leak_test",
    # Box-Up
    "get_boxup_records",
    "get_boxup_record_by_id",
    "count_boxup_records",
    "create_boxup",
    "update_boxup",
    "complete_boxup",
    "delete_boxup",
    # PMI
    "get_pmi_records",
    "get_pmi_record_by_id",
    "create_pmi",
    "update_pmi",
    "delete_pmi",
    # Dimensional Check
    "get_dim_checks",
    "get_dim_check_by_id",
    "create_dim_check",
    "update_dim_check",
    "delete_dim_check",
    # Spring Hanger
    "get_spring_hangers",
    "get_spring_hanger_by_id",
    "create_spring_hanger",
    "create_spring_hangers_bulk",
    "update_spring_hanger",
    "verify_spring_settings",
    "delete_spring_hanger",
    # Material Preservation
    "get_preservation",
    "get_preservation_by_id",
    "create_preservation",
    "update_preservation",
    "delete_preservation",
    # Pre-comm Dashboard Stats
    "get_precomm_dashboard_stats",
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


def _safe_update(obj: Any, data: Dict[str, Any], *, exclude: Optional[Set[str]] = None) -> int:
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

def get_flushing_records(
    session: Session,
    project_id: int,
    *,
    line_number: Optional[str] = None,
    flush_method: Optional[str] = None,
    result: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[FlushingRecord]:
    """دریافت سوابق عملیات شستشو/بلوئینگ با فیلترهای مهندسی و صفحه‌بندی."""
    _validate_project_id(project_id)
    q = session.query(FlushingRecord).filter(FlushingRecord.project_id == project_id)

    if line_number:
        q = q.filter(FlushingRecord.line_number.ilike(f"%{line_number}%"))
    if flush_method:
        q = q.filter(FlushingRecord.flush_method == flush_method)
    if result:
        q = q.filter(FlushingRecord.result == result)

    q = q.order_by(FlushingRecord.created_at.desc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_flushing_record_by_id(session: Session, record_id: int) -> Optional[FlushingRecord]:
    return session.get(FlushingRecord, record_id)


def count_flushing_records(session: Session, project_id: int, *, result: Optional[str] = None) -> int:
    _validate_project_id(project_id)
    q = session.query(func.count(FlushingRecord.id)).filter(FlushingRecord.project_id == project_id)
    if result:
        q = q.filter(FlushingRecord.result == result)
    return q.scalar() or 0


def create_flushing(session: Session, **kwargs: Any) -> FlushingRecord:
    """ثبت سند فلاشینگ جدید برای پایپینگ."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a FlushingRecord.")
    _validate_project_id(kwargs["project_id"])

    record = FlushingRecord(**kwargs)
    session.add(record)
    session.flush()
    logger.info("Created FlushingRecord ID=%d for Line=%s", record.id, record.line_number)
    return record


def create_flushing_bulk(
    session: Session,
    records_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 100,
) -> int:
    """درج انبوه اسناد شستشوی سیستم‌ها (پکیج‌های بزرگ)."""
    if not records_data:
        return 0

    records = [FlushingRecord(**data) for data in records_data]
    total = len(records)

    for i in range(0, total, batch_size):
        batch = records[i : i + batch_size]
        session.add_all(batch)
        session.flush()

    logger.info("Bulk imported %d FlushingRecords.", total)
    return total


def update_flushing(session: Session, record_id: int, **kwargs: Any) -> Optional[FlushingRecord]:
    record = session.get(FlushingRecord, record_id)
    if record is None:
        return None

    changed = _safe_update(record, kwargs)
    if changed:
        session.flush()
        logger.info("Updated FlushingRecord ID=%d (%d fields modified).", record_id, changed)
    return record


def delete_flushing(session: Session, record_id: int) -> bool:
    record = session.get(FlushingRecord, record_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    logger.info("Deleted FlushingRecord ID=%d.", record_id)
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_leak_tests(
    session: Session,
    project_id: int,
    *,
    line_number: Optional[str] = None,
    result: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[LeakTestRecord]:
    """دریافت لیست سوابق تست نشتی حساس سیستم پیش‌راه‌اندازی."""
    _validate_project_id(project_id)
    q = session.query(LeakTestRecord).filter(LeakTestRecord.project_id == project_id)

    if line_number:
        q = q.filter(LeakTestRecord.line_number.ilike(f"%{line_number}%"))
    if result:
        q = q.filter(LeakTestRecord.result == result)

    q = q.order_by(LeakTestRecord.created_at.desc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_leak_test_by_id(session: Session, test_id: int) -> Optional[LeakTestRecord]:
    return session.get(LeakTestRecord, test_id)


def count_leak_tests(session: Session, project_id: int, *, result: Optional[str] = None) -> int:
    _validate_project_id(project_id)
    q = session.query(func.count(LeakTestRecord.id)).filter(LeakTestRecord.project_id == project_id)
    if result:
        q = q.filter(LeakTestRecord.result == result)
    return q.scalar() or 0


def create_leak_test(session: Session, **kwargs: Any) -> LeakTestRecord:
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a LeakTestRecord.")
    _validate_project_id(kwargs["project_id"])

    record = LeakTestRecord(**kwargs)
    session.add(record)
    session.flush()
    logger.info("Created LeakTestRecord ID=%d for Line=%s", record.id, record.line_number)
    return record


def update_leak_test(session: Session, test_id: int, **kwargs: Any) -> Optional[LeakTestRecord]:
    record = session.get(LeakTestRecord, test_id)
    if record is None:
        return None

    changed = _safe_update(record, kwargs)
    if changed:
        session.flush()
        logger.info("Updated LeakTestRecord ID=%d (%d fields modified).", test_id, changed)
    return record


def delete_leak_test(session: Session, test_id: int) -> bool:
    record = session.get(LeakTestRecord, test_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    logger.info("Deleted LeakTestRecord ID=%d.", test_id)
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_boxup_records(
    session: Session,
    project_id: int,
    *,
    line_number: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[BoxUpRecord]:
    """دریافت سوابق عملیات نهایی بستن آدم‌روها و فلانژهای اصلی تجهیزات."""
    _validate_project_id(project_id)
    q = session.query(BoxUpRecord).filter(BoxUpRecord.project_id == project_id)

    if line_number:
        q = q.filter(BoxUpRecord.line_number.ilike(f"%{line_number}%"))
    if status:
        q = q.filter(BoxUpRecord.status == status)

    q = q.order_by(BoxUpRecord.created_at.desc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_boxup_record_by_id(session: Session, boxup_id: int) -> Optional[BoxUpRecord]:
    return session.get(BoxUpRecord, boxup_id)


def count_boxup_records(session: Session, project_id: int, *, status: Optional[str] = None) -> int:
    _validate_project_id(project_id)
    q = session.query(func.count(BoxUpRecord.id)).filter(BoxUpRecord.project_id == project_id)
    if status:
        q = q.filter(BoxUpRecord.status == status)
    return q.scalar() or 0


def create_boxup(session: Session, **kwargs: Any) -> BoxUpRecord:
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a BoxUpRecord.")
    _validate_project_id(kwargs["project_id"])

    record = BoxUpRecord(**kwargs)
    session.add(record)
    session.flush()
    logger.info("Created BoxUpRecord ID=%d", record.id)
    return record


def update_boxup(session: Session, boxup_id: int, **kwargs: Any) -> Optional[BoxUpRecord]:
    record = session.get(BoxUpRecord, boxup_id)
    if record is None:
        return None

    changed = _safe_update(record, kwargs)
    if changed:
        session.flush()
        logger.info("Updated BoxUpRecord ID=%d (%d fields modified).", boxup_id, changed)
    return record


def complete_boxup(
    session: Session,
    boxup_id: int,
    witnessed_by: str,
    *,
    certificate_no: Optional[str] = None,
) -> Optional[BoxUpRecord]:
    """
    بستن و مهروموم تایید نهایی فلانژ یا منهول تجهیز (Box-Up).
    
    این متد چک‌لیست‌های کیفی فیزیکی را تایید کرده و وضعیت رکورد را به 'Completed' تغییر می‌دهد.
    """
    record = session.get(BoxUpRecord, boxup_id)
    if record is None:
        logger.warning("BoxUpRecord ID=%d not found.", boxup_id)
        return None

    record.internal_inspection_done = True
    record.cleanliness_verified = True
    record.foreign_material_free = True
    record.gasket_installed = True
    record.bolt_torque_verified = True
    record.manway_closed = True
    record.blind_removed = True
    record.vent_drain_closed = True
    record.witnessed_by = witnessed_by
    record.boxup_date = date.today()
    record.status = "Completed"
    
    if certificate_no:
        record.certificate_no = certificate_no

    session.flush()
    logger.info("Equipment Box-Up ID=%d successfully completed and verified by %s.", boxup_id, witnessed_by)
    return record


def delete_boxup(session: Session, boxup_id: int) -> bool:
    record = session.get(BoxUpRecord, boxup_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    logger.info("Deleted BoxUpRecord ID=%d.", boxup_id)
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_pmi_records(
    session: Session,
    project_id: int,
    *,
    result: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[PMITestRecord]:
    """دریافت سوابق تست تشخیص آلیاژ (PMI) در فازهای پیش‌راه‌اندازی خطوط ویژه."""
    _validate_project_id(project_id)
    q = session.query(PMITestRecord).filter(PMITestRecord.project_id == project_id)

    if result:
        q = q.filter(PMITestRecord.result == result)

    q = q.order_by(PMITestRecord.created_at.desc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_pmi_record_by_id(session: Session, pmi_id: int) -> Optional[PMITestRecord]:
    return session.get(PMITestRecord, pmi_id)


def create_pmi(session: Session, **kwargs: Any) -> PMITestRecord:
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a PMITestRecord.")
    _validate_project_id(kwargs["project_id"])

    record = PMITestRecord(**kwargs)
    session.add(record)
    session.flush()
    return record


def update_pmi(session: Session, pmi_id: int, **kwargs: Any) -> Optional[PMITestRecord]:
    record = session.get(PMITestRecord, pmi_id)
    if record is None:
        return None

    changed = _safe_update(record, kwargs)
    if changed:
        session.flush()
    return record


def delete_pmi(session: Session, pmi_id: int) -> bool:
    record = session.get(PMITestRecord, pmi_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_dim_checks(
    session: Session,
    project_id: int,
    *,
    spool_number: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[DimensionalCheckRecord]:
    """دریافت سوابق کنترل ابعادی قطعات ساخته شده پیش از حمل به سایت."""
    _validate_project_id(project_id)
    q = session.query(DimensionalCheckRecord).filter(DimensionalCheckRecord.project_id == project_id)

    if spool_number:
        q = q.filter(DimensionalCheckRecord.spool_number.ilike(f"%{spool_number}%"))

    q = q.order_by(DimensionalCheckRecord.created_at.desc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_dim_check_by_id(session: Session, check_id: int) -> Optional[DimensionalCheckRecord]:
    return session.get(DimensionalCheckRecord, check_id)


def create_dim_check(session: Session, **kwargs: Any) -> DimensionalCheckRecord:
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a DimensionalCheckRecord.")
    _validate_project_id(kwargs["project_id"])

    record = DimensionalCheckRecord(**kwargs)
    session.add(record)
    session.flush()
    return record


def update_dim_check(session: Session, check_id: int, **kwargs: Any) -> Optional[DimensionalCheckRecord]:
    record = session.get(DimensionalCheckRecord, check_id)
    if record is None:
        return None

    changed = _safe_update(record, kwargs)
    if changed:
        session.flush()
    return record


def delete_dim_check(session: Session, check_id: int) -> bool:
    record = session.get(DimensionalCheckRecord, check_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_spring_hangers(
    session: Session,
    project_id: int,
    *,
    line_number: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[SpringHangerRecord]:
    """دریافت وضعیت ساپورت‌های فنری سیستم لوله‌کشی ارتعاشی در شرایط سرد و گرم."""
    _validate_project_id(project_id)
    q = session.query(SpringHangerRecord).filter(SpringHangerRecord.project_id == project_id)

    if line_number:
        q = q.filter(SpringHangerRecord.line_number.ilike(f"%{line_number}%"))
    if status:
        q = q.filter(SpringHangerRecord.status == status)

    q = q.order_by(SpringHangerRecord.support_tag.asc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_spring_hanger_by_id(session: Session, hanger_id: int) -> Optional[SpringHangerRecord]:
    return session.get(SpringHangerRecord, hanger_id)


def create_spring_hanger(session: Session, **kwargs: Any) -> SpringHangerRecord:
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a SpringHangerRecord.")
    _validate_project_id(kwargs["project_id"])

    record = SpringHangerRecord(**kwargs)
    session.add(record)
    session.flush()
    logger.info("Created SpringHangerRecord ID=%d for Tag=%s", record.id, record.support_tag)
    return record


def create_spring_hangers_bulk(
    session: Session,
    hangers_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 100,
) -> int:
    """درج انبوه تگ‌های ساپورت‌های فنری کل پروژه."""
    if not hangers_data:
        return 0

    records = [SpringHangerRecord(**data) for data in hangers_data]
    total = len(records)

    for i in range(0, total, batch_size):
        batch = records[i : i + batch_size]
        session.add_all(batch)
        session.flush()

    logger.info("Bulk imported %d SpringHangers.", total)
    return total


def update_spring_hanger(session: Session, hanger_id: int, **kwargs: Any) -> Optional[SpringHangerRecord]:
    record = session.get(SpringHangerRecord, hanger_id)
    if record is None:
        return None

    changed = _safe_update(record, kwargs)
    if changed:
        session.flush()
        logger.info("Updated SpringHangerRecord ID=%d (%d fields modified).", hanger_id, changed)
    return record


def verify_spring_settings(
    session: Session,
    hanger_id: int,
    verified_by: str,
    *,
    is_hot_set: bool = False,
) -> Optional[SpringHangerRecord]:
    """
    تایید رسمی موقعیت ساپورت فنری بر اساس شاخص‌های طراحی سرد یا گرم.
    
    این متد پین مسافرتی ساپورت را آزاد کرده و وضعیت سرد یا گرم را ثبت می‌کند.
    """
    record = session.get(SpringHangerRecord, hanger_id)
    if record is None:
        return None

    if not is_hot_set:
        record.cold_set_verified = True
        record.travel_pin_removed = True
        record.status = "Cold Verified"
    else:
        record.hot_set_verified = True
        record.status = "Hot Verified"

    record.inspector = verified_by
    record.installed_date = date.today()

    session.flush()
    logger.info("Spring Hanger Hanger ID=%d marked as %s.", hanger_id, record.status)
    return record


def delete_spring_hanger(session: Session, hanger_id: int) -> bool:
    record = session.get(SpringHangerRecord, hanger_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_preservation(
    session: Session,
    project_id: int,
    *,
    condition: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[MaterialPreservationRecord]:
    """دریافت سوابق بازرسی دوره‌ای کیفیت و پوشش‌های حفاظتی متریال در انبارها."""
    _validate_project_id(project_id)
    q = session.query(MaterialPreservationRecord).filter(MaterialPreservationRecord.project_id == project_id)

    if condition:
        q = q.filter(MaterialPreservationRecord.condition == condition)

    q = q.order_by(MaterialPreservationRecord.preservation_date.desc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_preservation_by_id(session: Session, preservation_id: int) -> Optional[MaterialPreservationRecord]:
    return session.get(MaterialPreservationRecord, preservation_id)


def create_preservation(session: Session, **kwargs: Any) -> MaterialPreservationRecord:
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a MaterialPreservationRecord.")
    _validate_project_id(kwargs["project_id"])

    record = MaterialPreservationRecord(**kwargs)
    session.add(record)
    session.flush()
    return record


def update_preservation(
    session: Session,
    preservation_id: int,
    **kwargs: Any,
) -> Optional[MaterialPreservationRecord]:
    record = session.get(MaterialPreservationRecord, preservation_id)
    if record is None:
        return None

    changed = _safe_update(record, kwargs)
    if changed:
        session.flush()
    return record


def delete_preservation(session: Session, preservation_id: int) -> bool:
    record = session.get(MaterialPreservationRecord, preservation_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    return True


# ══════════════════════════════════════════════
#  8. Pre-commissioning Dashboard Stats
# ══════════════════════════════════════════════

def get_precomm_dashboard_stats(session: Session, project_id: int) -> Dict[str, Any]:
    """
    استخراج و مانیتورینگ آمار کلی کارهای فاز پیش‌راه‌اندازی برای کارفرما.
    
    شامل مقایسه کارهای انجام شده با کارهای تعریف شده در حوزه‌های فلاشینگ خطوط،
    آب‌بندی تجهیزات، تست نشتی فلانژها و تایید ساپورت‌های ارتعاشی فنری.
    """
    _validate_project_id(project_id)

    # Implementation note.
    flush_total = count_flushing_records(session, project_id)
    flush_passed = count_flushing_records(session, project_id, result="Accept")

    # Implementation note.
    leak_total = count_leak_tests(session, project_id)
    leak_passed = count_leak_tests(session, project_id, result="Accept")

    # Implementation note.
    boxup_total = count_boxup_records(session, project_id)
    boxup_completed = count_boxup_records(session, project_id, status="Completed")

    # Implementation note.
    hanger_total = (
        session.query(func.count(SpringHangerRecord.id))
        .filter(SpringHangerRecord.project_id == project_id)
        .scalar() or 0
    )
    hanger_verified = (
        session.query(func.count(SpringHangerRecord.id))
        .filter(
            SpringHangerRecord.project_id == project_id,
            SpringHangerRecord.status.in_(["Cold Verified", "Hot Verified"])
        )
        .scalar() or 0
    )

    return {
        "flushing": {
            "total_flushed_lines": flush_total,
            "accepted_lines": flush_passed,
            "progress_pct": round(flush_passed / flush_total * 100, 1) if flush_total else 0.0,
        },
        "leak_testing": {
            "total_tested_sections": leak_total,
            "accepted_sections": leak_passed,
            "progress_pct": round(leak_passed / leak_total * 100, 1) if leak_total else 0.0,
        },
        "boxup": {
            "total_equipments": boxup_total,
            "completed_equipments": boxup_completed,
            "progress_pct": round(boxup_completed / boxup_total * 100, 1) if boxup_total else 0.0,
        },
        "spring_hangers": {
            "total_hangers_installed": hanger_total,
            "verified_hangers": hanger_verified,
            "progress_pct": round(hanger_verified / hanger_total * 100, 1) if hanger_total else 0.0,
        }
    }