# -*- coding: utf-8 -*-
"""
db/queries/qaqc_queries.py – PipeAgent v5.1
===========================================
Enterprise QA/QC & Inspection Management Query Layer.

Covers:
  • Punch List Tracking (Categories A, B, C) and Clearance Workflows
  • Non-Conformance Reports (NCR) Lifecycle (Raise, Action, and Closure)
  • Inspection and Test Plans (ITP) Activities and Verification States
  • High-performance Database-level Punch Aggregations (replaces memory loops)
  • Bulk Imports for Punch-Lists and ITP Templates
  • Multi-Tenant QA/QC KPI Statistics and Dashboard Metrics

Fully updated for SQLAlchemy 2.0, complete with pagination, filters, and safety validations.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from db.models import ITPItem, NCRRecord, PunchItem

# Implementation note.
try:
    from core.exceptions import DatabaseError, ValidationError
except ImportError:
    class DatabaseError(Exception): pass
    class ValidationError(Exception): pass

logger = logging.getLogger(__name__)

__all__ = [
    # Punch Items
    "get_punch_items",
    "get_punch_item_by_id",
    "get_punch_summary",
    "count_punch_items",
    "create_punch",
    "create_punches_bulk",
    "update_punch",
    "clear_punch",
    "delete_punch",
    # NCR Records
    "get_ncr_records",
    "get_ncr_by_id",
    "count_ncr_records",
    "create_ncr",
    "update_ncr",
    "close_ncr",
    "delete_ncr",
    # ITP Items
    "get_itp_items",
    "get_itp_item_by_id",
    "count_itp_items",
    "create_itp_item",
    "create_itp_items_bulk",
    "update_itp_item",
    "delete_itp_item",
    # QA/QC Performance Stats
    "get_qaqc_dashboard_stats",
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

def get_punch_items(
    session: Session,
    project_id: int,
    *,
    category: Optional[str] = None,
    is_cleared: Optional[bool] = None,
    test_package_id: Optional[int] = None,
    line_number: Optional[str] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[PunchItem]:
    """دریافت سوابق پانچ لیست با فیلترهای گسترده کارگاهی و صفحه‌بندی."""
    _validate_project_id(project_id)
    q = session.query(PunchItem).filter(PunchItem.project_id == project_id)

    if category:
        q = q.filter(PunchItem.category == category)
    if is_cleared is not None:
        q = q.filter(PunchItem.is_cleared == is_cleared)
    if test_package_id is not None:
        q = q.filter(PunchItem.test_package_id == test_package_id)
    if line_number:
        q = q.filter(PunchItem.line_number.ilike(f"%{line_number}%"))
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                PunchItem.description.ilike(pattern),
                PunchItem.location_desc.ilike(pattern),
                PunchItem.raised_by.ilike(pattern),
            )
        )

    q = q.order_by(PunchItem.raised_date.desc(), PunchItem.id.desc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_punch_item_by_id(session: Session, punch_id: int) -> Optional[PunchItem]:
    return session.get(PunchItem, punch_id)


def get_punch_summary(session: Session, project_id: int, test_package_id: Optional[int] = None) -> Dict[str, Dict[str, int]]:
    """
    محاسبه‌ی خلاصه وضعیت پانچ‌ها به تفکیک دسته‌های استاندارد A، B و C.

    بهینه‌سازی شده در سطح بانک اطلاعاتی با ساختار شرطی (SQL Aggregation) برای سرعت فوق‌العاده بالا.
    
    Returns:
        {
            "A": {"open": 12, "closed": 45},
            "B": {"open": 2, "closed": 88},
            "C": {"open": 0, "closed": 5}
        }
    """
    _validate_project_id(project_id)

    # Implementation note.
    case_open_a = case((and_(PunchItem.category == "A", PunchItem.is_cleared == False), 1), else_=0)  # noqa: E712
    case_closed_a = case((and_(PunchItem.category == "A", PunchItem.is_cleared == True), 1), else_=0)  # noqa: E712

    case_open_b = case((and_(PunchItem.category == "B", PunchItem.is_cleared == False), 1), else_=0)  # noqa: E712
    case_closed_b = case((and_(PunchItem.category == "B", PunchItem.is_cleared == True), 1), else_=0)  # noqa: E712

    case_open_c = case((and_(PunchItem.category == "C", PunchItem.is_cleared == False), 1), else_=0)  # noqa: E712
    case_closed_c = case((and_(PunchItem.category == "C", PunchItem.is_cleared == True), 1), else_=0)  # noqa: E712

    q = session.query(
        func.sum(case_open_a).label("open_a"),
        func.sum(case_closed_a).label("closed_a"),
        func.sum(case_open_b).label("open_b"),
        func.sum(case_closed_b).label("closed_b"),
        func.sum(case_open_c).label("open_c"),
        func.sum(case_closed_c).label("closed_c"),
    ).filter(PunchItem.project_id == project_id)

    if test_package_id is not None:
        q = q.filter(PunchItem.test_package_id == test_package_id)

    res = q.first()

    return {
        "A": {"open": int(res.open_a or 0), "closed": int(res.closed_a or 0)},
        "B": {"open": int(res.open_b or 0), "closed": int(res.closed_b or 0)},
        "C": {"open": int(res.open_c or 0), "closed": int(res.closed_c or 0)},
    }


def count_punch_items(session: Session, project_id: int, *, category: Optional[str] = None, is_cleared: Optional[bool] = None) -> int:
    _validate_project_id(project_id)
    q = session.query(func.count(PunchItem.id)).filter(PunchItem.project_id == project_id)
    if category:
        q = q.filter(PunchItem.category == category)
    if is_cleared is not None:
        q = q.filter(PunchItem.is_cleared == is_cleared)
    return q.scalar() or 0


def create_punch(session: Session, **kwargs: Any) -> PunchItem:
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a PunchItem.")
    _validate_project_id(kwargs["project_id"])

    p = PunchItem(**kwargs)
    session.add(p)
    session.flush()
    logger.info("Created PunchItem ID=%d under Category=%s", p.id, p.category)
    return p


def create_punches_bulk(
    session: Session,
    punches_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 100,
) -> int:
    """درج انبوه پانچ‌ها در زمان اتمام تست‌های سیستم و هیدروتست پکیج‌ها."""
    if not punches_data:
        return 0

    punches = [PunchItem(**data) for data in punches_data]
    total = len(punches)

    for i in range(0, total, batch_size):
        batch = punches[i : i + batch_size]
        session.add_all(batch)
        session.flush()

    logger.info("Bulk imported %d PunchItems into project.", total)
    return total


def update_punch(session: Session, punch_id: int, **kwargs: Any) -> Optional[PunchItem]:
    p = session.get(PunchItem, punch_id)
    if p is None:
        return None
    changed = _safe_update(p, kwargs)
    if changed:
        session.flush()
        logger.info("Updated PunchItem ID=%d (%d fields modified).", punch_id, changed)
    return p


def clear_punch(session: Session, punch_id: int, cleared_by: str, *, remarks: Optional[str] = None) -> Optional[PunchItem]:
    """رفع پانچ و تایید نهایی با ثبت مهر زمانی و نام ناظر کیفی."""
    p = session.get(PunchItem, punch_id)
    if p is None:
        logger.warning("PunchItem ID=%d not found.", punch_id)
        return None

    p.is_cleared = True
    p.cleared_by = cleared_by
    p.cleared_date = date.today()
    if remarks:
        p.remarks = remarks

    session.flush()
    logger.info("Cleared PunchItem ID=%d by %s.", punch_id, cleared_by)
    return p


def delete_punch(session: Session, punch_id: int) -> bool:
    p = session.get(PunchItem, punch_id)
    if p is None:
        return False
    session.delete(p)
    session.flush()
    logger.info("Deleted PunchItem ID=%d.", punch_id)
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_ncr_records(
    session: Session,
    project_id: int,
    *,
    status: Optional[str] = None,
    item_type: Optional[str] = None,
    line_number: Optional[str] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[NCRRecord]:
    """دریافت سوابق عدم انطباق پروژه با فیلترها و صفحه‌بندی."""
    _validate_project_id(project_id)
    q = session.query(NCRRecord).filter(NCRRecord.project_id == project_id)

    if status:
        q = q.filter(NCRRecord.status == status)
    if item_type:
        q = q.filter(NCRRecord.item_type == item_type)
    if line_number:
        q = q.filter(NCRRecord.line_number.ilike(f"%{line_number}%"))
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                NCRRecord.ncr_no.ilike(pattern),
                NCRRecord.description.ilike(pattern),
                NCRRecord.root_cause.ilike(pattern),
            )
        )

    q = q.order_by(NCRRecord.raised_date.desc(), NCRRecord.id.desc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_ncr_by_id(session: Session, ncr_id: int) -> Optional[NCRRecord]:
    return session.get(NCRRecord, ncr_id)


def count_ncr_records(session: Session, project_id: int, *, status: Optional[str] = None) -> int:
    _validate_project_id(project_id)
    q = session.query(func.count(NCRRecord.id)).filter(NCRRecord.project_id == project_id)
    if status:
        q = q.filter(NCRRecord.status == status)
    return q.scalar() or 0


def create_ncr(session: Session, **kwargs: Any) -> NCRRecord:
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create an NCRRecord.")
    _validate_project_id(kwargs["project_id"])

    n = NCRRecord(**kwargs)
    session.add(n)
    session.flush()
    logger.info("Created NCRRecord ID=%d No=%s", n.id, n.ncr_no)
    return n


def update_ncr(session: Session, ncr_id: int, **kwargs: Any) -> Optional[NCRRecord]:
    n = session.get(NCRRecord, ncr_id)
    if n is None:
        return None
    changed = _safe_update(n, kwargs)
    if changed:
        session.flush()
        logger.info("Updated NCRRecord ID=%d No=%s (%d fields modified).", n_id, n.ncr_no, changed)
    return n


def close_ncr(session: Session, ncr_id: int, closed_by: str, *, disposition: str, **kwargs: Any) -> Optional[NCRRecord]:
    """بستن گزارش عدم انطباق با تایید روش اصلاح عیب (Use-As-Is, Repair, Reject, Rework)."""
    n = session.get(NCRRecord, ncr_id)
    if n is None:
        logger.warning("NCRRecord ID=%d not found.", ncr_id)
        return None

    n.status = "Closed"
    n.closed_by = closed_by
    n.closed_date = date.today()
    n.disposition = disposition

    # Implementation note.
    _safe_update(n, kwargs, exclude={"id", "project_id", "status", "closed_by", "closed_date"})
    
    session.flush()
    logger.info("Closed NCRRecord ID=%d No=%s with Disposition=%s", ncr_id, n.ncr_no, disposition)
    return n


def delete_ncr(session: Session, ncr_id: int) -> bool:
    n = session.get(NCRRecord, ncr_id)
    if n is None:
        return False
    session.delete(n)
    session.flush()
    logger.info("Deleted NCRRecord ID=%d.", ncr_id)
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_itp_items(
    session: Session,
    project_id: int,
    *,
    itp_number: Optional[str] = None,
    inspection_type: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[ITPItem]:
    """دریافت بندهای طرح بازرسی و تست (Inspection & Test Plan) با صفحه‌بندی."""
    _validate_project_id(project_id)
    q = session.query(ITPItem).filter(ITPItem.project_id == project_id)

    if itp_number:
        q = q.filter(ITPItem.itp_number == itp_number)
    if inspection_type:
        q = q.filter(ITPItem.inspection_type == inspection_type)
    if status:
        q = q.filter(ITPItem.status == status)

    q = q.order_by(ITPItem.activity_code.asc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_itp_item_by_id(session: Session, itp_item_id: int) -> Optional[ITPItem]:
    return session.get(ITPItem, itp_item_id)


def count_itp_items(session: Session, project_id: int, *, itp_number: Optional[str] = None) -> int:
    _validate_project_id(project_id)
    q = session.query(func.count(ITPItem.id)).filter(ITPItem.project_id == project_id)
    if itp_number:
        q = q.filter(ITPItem.itp_number == itp_number)
    return q.scalar() or 0


def create_itp_item(session: Session, **kwargs: Any) -> ITPItem:
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create an ITPItem.")
    _validate_project_id(kwargs["project_id"])

    item = ITPItem(**kwargs)
    session.add(item)
    session.flush()
    return item


def create_itp_items_bulk(
    session: Session,
    itp_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 100,
) -> int:
    """بارگذاری دسته‌ای قالب‌های استاندارد ITP متناسب با مشخصات پروژه."""
    if not itp_data:
        return 0

    items = [ITPItem(**data) for data in itp_data]
    total = len(items)

    for i in range(0, total, batch_size):
        batch = items[i : i + batch_size]
        session.add_all(batch)
        session.flush()

    logger.info("Bulk imported %d ITPItems template.", total)
    return total


def update_itp_item(session: Session, itp_item_id: int, **kwargs: Any) -> Optional[ITPItem]:
    item = session.get(ITPItem, itp_item_id)
    if item is None:
        return None
    changed = _safe_update(item, kwargs)
    if changed:
        session.flush()
    return item


def delete_itp_item(session: Session, itp_item_id: int) -> bool:
    item = session.get(ITPItem, itp_item_id)
    if item is None:
        return False
    session.delete(item)
    session.flush()
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_qaqc_dashboard_stats(session: Session, project_id: int) -> Dict[str, Any]:
    """
    استخراج آنی شاخص‌های کلیدی مانیتورینگ کارگاهی کیفیت (QA/QC KPIs) برای کارفرما.
    
    شامل:
      - نرخ تسویه پانچ‌ها به تفکیک دسته کاربری (Cat A, B, C)
      - تعداد پرونده‌های باز NCR و توزیع نوع عدم انطباق‌ها
      - درصد پیشرفت گام‌های کنترل کیفی بر مبنای ITP
    """
    _validate_project_id(project_id)

    # Implementation note.
    p_summary = get_punch_summary(session, project_id)
    total_punches = (
        sum(p_summary[cat]["open"] + p_summary[cat]["closed"] for cat in p_summary)
    )
    closed_punches = (
        sum(p_summary[cat]["closed"] for cat in p_summary)
    )

    # Implementation note.
    total_ncrs = count_ncr_records(session, project_id)
    open_ncrs = count_ncr_records(session, project_id, status="Open")

    # Implementation note.
    total_itp = count_itp_items(session, project_id)
    completed_itp = (
        session.query(func.count(ITPItem.id))
        .filter(ITPItem.project_id == project_id, ITPItem.status == "Completed")
        .scalar() or 0
    )

    return {
        "punches": {
            "total_punches": total_punches,
            "closed_punches": closed_punches,
            "clearance_rate_pct": round(closed_punches / total_punches * 100, 1) if total_punches else 0.0,
            "breakdown": p_summary,
        },
        "ncrs": {
            "total_raised": total_ncrs,
            "open_cases": open_ncrs,
            "closed_cases": total_ncrs - open_ncrs,
            "resolution_rate_pct": round((total_ncrs - open_ncrs) / total_ncrs * 100, 1) if total_ncrs else 0.0,
        },
        "itp": {
            "total_inspections": total_itp,
            "completed_inspections": completed_itp,
            "progress_pct": round(completed_itp / total_itp * 100, 1) if total_itp else 0.0,
        }
    }