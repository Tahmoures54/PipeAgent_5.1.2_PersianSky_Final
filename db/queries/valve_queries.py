# -*- coding: utf-8 -*-
"""
db/queries/valve_queries.py – PipeAgent v5.1
===========================================
Enterprise Valve Inventory & Quality Testing (Shell/Seat) Query Layer.

Covers:
  • Valve Inventory: CRUD and bulk import of valves from design bills (BOM).
  • Valve Quality Control: Atomic registration of Hydro Shell & Seat tests.
  • Installation Tracking: Dates, personnel, and line associations.
  • Optimized Searches (Tag, Line number, Valve type, test status).
  • Comprehensive KPI Dashboard calculations.

Fully updated to SQLAlchemy 2.0 standards with strict typing and validations.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from db.models import ValveRecord

# Implementation note.
try:
    from core.exceptions import DatabaseError, ValidationError
except ImportError:
    class DatabaseError(Exception): pass
    class ValidationError(Exception): pass

logger = logging.getLogger(__name__)

class ValveStatus:
    RECEIVED = "Received"       # Implementation note.
    TEST_PASSED = "Tested"      # Implementation note.
    TEST_FAILED = "Rejected"    # Implementation note.
    INSTALLED = "Installed"     # Implementation note.
    ALL = (RECEIVED, TEST_PASSED, TEST_FAILED, INSTALLED)


__all__ = [
    "ValveStatus",
    # CRUD
    "get_valves",
    "get_valve_by_id",
    "get_valve_by_tag",
    "get_untested_valves",
    "count_valves",
    "create_valve",
    "create_valves_bulk",
    "update_valve",
    "delete_valve",
    # Workflows
    "record_valve_test_results",
    "mark_valve_as_installed",
    # Dashboard stats
    "get_valve_dashboard_stats",
]


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────

def _validate_project_id(project_id: int) -> None:
    if not isinstance(project_id, int) or project_id <= 0:
        raise ValidationError(f"Invalid project_id: {project_id!r}. Must be a positive integer.")


def _apply_pagination(query, *, offset: int = 0, limit: Optional[int] = 100):
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


def _pct(numerator: float, denominator: float, digits: int = 1) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, digits)


# ══════════════════════════════════════════════
#  1. Valve CRUD Operations
# ══════════════════════════════════════════════

def get_valves(
    session: Session,
    project_id: int,
    *,
    status: Optional[str] = None,
    line_number: Optional[str] = None,
    valve_type: Optional[str] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: Optional[int] = 100,
) -> List[ValveRecord]:
    """دریافت لیست شیرآلات با اعمال فیلترهای فنی و صفحه‌بندی پایگاه داده."""
    _validate_project_id(project_id)
    q = session.query(ValveRecord).filter(ValveRecord.project_id == project_id)

    if status:
        q = q.filter(ValveRecord.status == status)
    if line_number:
        q = q.filter(ValveRecord.line_number.ilike(f"%{line_number}%"))
    if valve_type:
        q = q.filter(ValveRecord.valve_type == valve_type)
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                ValveRecord.valve_tag.ilike(pattern),
                ValveRecord.manufacturer.ilike(pattern),
                ValveRecord.heat_number.ilike(pattern),
            )
        )

    q = q.order_by(ValveRecord.valve_tag.asc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_valve_by_id(session: Session, valve_id: int) -> Optional[ValveRecord]:
    """دریافت اطلاعات شیر بر اساس شناسه (SQLAlchemy 2.0)."""
    return session.get(ValveRecord, valve_id)


def get_valve_by_tag(session: Session, project_id: int, tag: str) -> Optional[ValveRecord]:
    """دریافت سریع اطلاعات شیر بر اساس Tag اختصاصی آن."""
    _validate_project_id(project_id)
    return (
        session.query(ValveRecord)
        .filter(ValveRecord.project_id == project_id, ValveRecord.valve_tag == tag)
        .first()
    )


def get_untested_valves(session: Session, project_id: int) -> List[ValveRecord]:
    """دریافت لیست کلیه شیرآلاتی که تست هیدرو بدنه (Shell) بر روی آن‌ها انجام نشده است."""
    _validate_project_id(project_id)
    return (
        session.query(ValveRecord)
        .filter(
            ValveRecord.project_id == project_id,
            ValveRecord.hydro_shell_test == False  # noqa: E712
        )
        .order_by(ValveRecord.valve_tag.asc())
        .all()
    )


def count_valves(session: Session, project_id: int, *, status: Optional[str] = None) -> int:
    _validate_project_id(project_id)
    q = session.query(func.count(ValveRecord.id)).filter(ValveRecord.project_id == project_id)
    if status:
        q = q.filter(ValveRecord.status == status)
    return q.scalar() or 0


def create_valve(session: Session, **kwargs: Any) -> ValveRecord:
    """ثبت شناسنامه شیرآلات جدید در سیستم."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a ValveRecord.")
    _validate_project_id(kwargs["project_id"])

    tag = kwargs.get("valve_tag")
    if not tag:
        raise ValidationError("valve_tag is required to create a ValveRecord.")

    # Implementation note.
    existing = get_valve_by_tag(session, kwargs["project_id"], tag)
    if existing:
        raise ValidationError(f"Valve with tag '{tag}' already exists in this project.")

    valve = ValveRecord(**kwargs)
    session.add(valve)
    session.flush()
    logger.info("Created ValveRecord ID=%d Tag=%s for Line=%s", valve.id, valve.valve_tag, valve.line_number)
    return valve


def create_valves_bulk(
    session: Session,
    valves_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 100,
) -> int:
    """درج انبوه تگ‌های شیرآلات کل پروژه از روی نقشه‌ها یا پایپینگ BOM."""
    if not valves_data:
        return 0

    valves = [ValveRecord(**data) for data in valves_data]
    total = len(valves)

    for i in range(0, total, batch_size):
        batch = valves[i : i + batch_size]
        session.add_all(batch)
        session.flush()

    logger.info("Bulk imported %d valves.", total)
    return total


def update_valve(session: Session, valve_id: int, **kwargs: Any) -> Optional[ValveRecord]:
    """به‌روزرسانی عمومی مشخصات فنی شیر."""
    v = session.get(ValveRecord, valve_id)
    if v is None:
        return None

    changed = _safe_update(v, kwargs)
    if changed:
        session.flush()
        logger.info("Updated ValveRecord ID=%d (%d fields modified).", valve_id, changed)
    return v


def delete_valve(session: Session, valve_id: int) -> bool:
    """حذف فیزیکی رکورد شیرآلات."""
    v = session.get(ValveRecord, valve_id)
    if v is None:
        return False
    session.delete(v)
    session.flush()
    logger.info("Deleted ValveRecord ID=%d.", valve_id)
    return True


# ══════════════════════════════════════════════
#  2. Quality Control & Installation Workflows
# ══════════════════════════════════════════════

def record_valve_test_results(
    session: Session,
    valve_id: int,
    *,
    hydro_shell_passed: bool,
    shell_pressure_bar: float,
    hydro_seat_passed: bool,
    seat_pressure_bar: float,
    witness_name: str,
    test_date: date,
    remarks: Optional[str] = None,
) -> Optional[ValveRecord]:
    """
    ثبت اتمیک و رسمی نتایج تست هیدرو استاتیک بدنه (Shell) و نشیمنگاه (Seat) شیرآلات.
    
    در صورت پاس شدن هر دو مرحله، وضعیت شیر به 'Tested' ارتقا می‌یابد.
    """
    v = session.get(ValveRecord, valve_id)
    if v is None:
        logger.warning("ValveRecord ID=%d not found for logging test results.", valve_id)
        return None

    v.hydro_shell_test = hydro_shell_passed
    v.hydro_shell_pressure_bar = shell_pressure_bar
    v.hydro_shell_date = test_date

    v.hydro_seat_test = hydro_seat_passed
    v.hydro_seat_pressure_bar = seat_pressure_bar
    v.hydro_seat_date = test_date

    v.test_witness = witness_name

    # Implementation note.
    if hydro_shell_passed and hydro_seat_passed:
        v.status = ValveStatus.TEST_PASSED
    else:
        v.status = ValveStatus.TEST_FAILED

    if remarks:
        v.remarks = remarks

    session.flush()
    logger.info("Logged Test Results for Valve ID=%d Tag=%s Status=%s", v.id, v.valve_tag, v.status)
    return v


def mark_valve_as_installed(
    session: Session,
    valve_id: int,
    installed_by: str,
    installed_date: date,
) -> Optional[ValveRecord]:
    """
    تغییر وضعیت شیر به 'Installed' پس از نصب فیزیکی روی خط در سایت.
    
    سیستم تایید می‌کند که شیر حتماً از سد تست هیدرو عبور کرده باشد.
    """
    v = session.get(ValveRecord, valve_id)
    if v is None:
        return None

    # Implementation note.
    if not v.hydro_shell_test or not v.hydro_seat_test:
        raise ValidationError(
            f"Cannot install Valve '{v.valve_tag}'. It has not passed quality testing."
        )

    v.installed_by = installed_by
    v.installed_date = installed_date
    v.status = ValveStatus.INSTALLED

    session.flush()
    logger.info("Marked Valve ID=%d Tag=%s as INSTALLED on Line=%s", v.id, v.valve_tag, v.line_number)
    return v


# ══════════════════════════════════════════════
#  3. Dashboard KPI Statistics
# ══════════════════════════════════════════════

def get_valve_dashboard_stats(session: Session, project_id: int) -> Dict[str, Any]:
    """
    استخراج و مانیتورینگ پیشرفت مأموریت‌های شیرآلات پروژه برای کارفرما.
    
    Returns:
        آمار تعداد و درصد شیرهای تست شده، تست نشده، مردود شده و نصب‌شده در سایت.
    """
    _validate_project_id(project_id)

    total = count_valves(session, project_id)
    received = count_valves(session, project_id, status=ValveStatus.RECEIVED)
    tested = count_valves(session, project_id, status=ValveStatus.TEST_PASSED)
    rejected = count_valves(session, project_id, status=ValveStatus.TEST_FAILED)
    installed = count_valves(session, project_id, status=ValveStatus.INSTALLED)

    # Implementation note.
    total_tested = tested + rejected + installed

    return {
        "valves": {
            "total_registered": total,
            "received_pending_test": received,
            "test_passed_ready": tested,
            "test_failed": rejected,
            "installed_on_site": installed,
            "testing_progress_pct": _pct(total_tested, total),
            "installation_progress_pct": _pct(installed, total),
            "rejection_rate_pct": _pct(rejected, total_tested) if total_tested else 0.0,
        }
    }