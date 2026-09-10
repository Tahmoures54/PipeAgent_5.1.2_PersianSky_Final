# -*- coding: utf-8 -*-
"""
db/queries/weld_queries.py – PipeAgent v5.1
===========================================
Enterprise Welding Management & Quality Tracking Query Layer.

Covers:
  • Weld Lifecycle: Registration, status tracking, and repair history.
  • Joint History (Audit Trail): Every repair, status change, and update event.
  • NDT Integration: Fast retrieval of related Non-Destructive Test records.
  • Welder Performance: Repair rate statistics per welder (WPS qualification tracking).
  • WPS / PQR Tracking: Link to welding procedure specifications.
  • Shop vs. Field Welding Analytics: Productivity and quality metrics.
  • Bulk Import Support: For importing large weld reports from fabrication shops.
  • Pagination, Filtering, Search, and Safe Deletion.

Fully SQLAlchemy 2.0 compliant, type-annotated, and integrated with the core exception layer.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, joinedload

from db.models import (
    JointHistory,
    NDTRecord,
    WPS_PQR,
    Weld,
    WeldReportDraft,
)

try:
    from core.exceptions import DatabaseError, ValidationError
except ImportError:
    class DatabaseError(Exception): pass
    class ValidationError(Exception): pass

logger = logging.getLogger(__name__)

__all__ = [
    "WeldStatus",
    # Weld CRUD
    "get_welds",
    "get_weld_by_id",
    "get_weld_by_weld_id",
    "count_welds",
    "create_weld",
    "create_welds_bulk",
    "update_weld",
    "delete_weld",
    # Joint History / Audit
    "get_joint_history_for_weld",
    "record_joint_history",
    # Welder Performance Analytics
    "get_welder_repair_statistics",
    "get_repair_trend_by_welder",
    # NDT Integration Queries
    "get_weld_ndt_summary",
    "get_uninspected_welds",
    "get_failed_welds",
    # WPS Integration Queries
    "get_weld_wps_info",
    "get_welds_by_wps",
    # Workflows / Business Logic
    "record_weld_repair",
    "close_weld_for_ndt",
    # Bulk / Advanced
    "import_shop_weld_batch",
    # Dashboard / Stats
    "get_weld_dashboard_stats",
]


class WeldStatus:
    """Standard lifecycle states for welding joints in the system."""
    PENDING = "Pending"
    FITUP_COMPLETE = "Fit-up Complete"
    WELDED = "Welded"
    NDT_PENDING = "NDT Pending"
    NDT_ACCEPTED = "NDT Accepted"
    REPAIR_REQUIRED = "Repair Required"
    REPAIRED = "Repaired"
    CANCELLED = "Cancelled"
    CUT_OUT = "Cut Out"
    ALL = (PENDING, FITUP_COMPLETE, WELDED, NDT_PENDING, NDT_ACCEPTED, REPAIR_REQUIRED, REPAIRED, CANCELLED, CUT_OUT)
    TERMINAL = (NDT_ACCEPTED, CANCELLED, CUT_OUT)


# ──────────────────────────────────────────────
#  Helpers
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


def _pct(num: float, denom: float, digits: int = 1) -> float:
    return round((num / denom) * 100, digits) if denom else 0.0


# ══════════════════════════════════════════════
#  1. Weld Lifecycle CRUD Operations
# ══════════════════════════════════════════════

def get_welds(
    session: Session,
    project_id: int,
    *,
    spool_id: Optional[int] = None,
    weld_type: Optional[str] = None,
    status: Optional[str] = None,
    welder_id: Optional[str] = None,
    line_number: Optional[str] = None,
    iso_number: Optional[str] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[Weld]:
    """
    دریافت جامع اطلاعات سرجوش‌ها با فیلترهای دقیق کارگاهی، جستجو و صفحه‌بندی.
    """
    _validate_project_id(project_id)
    q = session.query(Weld).filter(Weld.project_id == project_id)

    if spool_id is not None:
        q = q.filter(Weld.spool_id == spool_id)
    if weld_type:
        q = q.filter(Weld.weld_type == weld_type)
    if status:
        q = q.filter(Weld.status == status)
    if welder_id:
        q = q.filter(Weld.welder_id == welder_id)
    if line_number:
        q = q.filter(Weld.line_number.ilike(f"%{line_number}%"))
    if iso_number:
        q = q.filter(Weld.iso_number.ilike(f"%{iso_number}%"))
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                Weld.weld_id.ilike(pattern),
                Weld.welder_name.ilike(pattern),
                Weld.line_number.ilike(pattern),
            )
        )

    # Eager load for quick display of related WPS and Spool
    q = q.options(
        joinedload(Weld.spool),
        joinedload(Weld.wps_pqr),
    )
    q = q.order_by(Weld.line_number.asc(), Weld.spool_id.asc().nullslast(), Weld.id.asc())

    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_weld_by_id(session: Session, weld_pk: int) -> Optional[Weld]:
    """دریافت اطلاعات دقیق جوش بر اساس شناسه اصلی."""
    return session.get(Weld, weld_pk)


def get_weld_by_weld_id(
    session: Session,
    project_id: int,
    weld_id: str,
) -> Optional[Weld]:
    """دریافت جوش بر اساس شماره اختصاصی جوش (Weld ID) در پروژه."""
    _validate_project_id(project_id)
    return (
        session.query(Weld)
        .filter(Weld.project_id == project_id, Weld.weld_id == weld_id)
        .first()
    )


def count_welds(
    session: Session,
    project_id: int,
    *,
    status: Optional[str] = None,
    weld_type: Optional[str] = None,
) -> int:
    """شمارش تعداد کل جوش‌های پروژه با فیلترهای اختیاری."""
    _validate_project_id(project_id)
    q = session.query(func.count(Weld.id)).filter(Weld.project_id == project_id)
    if status:
        q = q.filter(Weld.status == status)
    if weld_type:
        q = q.filter(Weld.weld_type == weld_type)
    return q.scalar() or 0


def create_weld(session: Session, **kwargs: Any) -> Weld:
    """
    ثبت اطلاعات سرجوش جدید در سیستم.
    """
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a Weld.")
    _validate_project_id(kwargs["project_id"])

    # Implementation note.
    wid = kwargs.get("weld_id")
    if wid:
        existing = get_weld_by_weld_id(session, kwargs["project_id"], wid)
        if existing:
            raise ValidationError(f"Weld with ID '{wid}' already exists in this project.")

    weld = Weld(**kwargs)
    session.add(weld)
    session.flush()
    logger.info("Created Weld PK=%d WeldID=%s Line=%s Status=%s", weld.id, weld.weld_id, weld.line_number, weld.status)
    return weld


def create_welds_bulk(
    session: Session,
    welds_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 150,
) -> int:
    """
    ثبت دسته‌ای جوش‌ها (مناسب برای وارد کردن اطلاعات کارگاهی از فایل‌های اکسل).
    """
    if not welds_data:
        return 0

    welds = [Weld(**data) for data in welds_data]
    total = len(welds)

    for i in range(0, total, batch_size):
        session.add_all(welds[i : i + batch_size])
        session.flush()

    logger.info("Bulk imported %d Weld records for the project.", total)
    return total


def update_weld(session: Session, weld_pk: int, **kwargs: Any) -> Optional[Weld]:
    """به‌روزرسانی فیلدهای مشخصات فنی و کارگاهی جوش."""
    weld = session.get(Weld, weld_pk)
    if weld is None:
        return None

    changed = _safe_update(weld, kwargs)
    if changed:
        session.flush()
        logger.info("Updated Weld PK=%d (%d fields modified).", weld_pk, changed)
    return weld


def delete_weld(session: Session, weld_pk: int) -> bool:
    """
    حذف فیزیکی جوش از سیستم.
    توجه: با حذف جوش، تاریخچه‌های مرتبط نیز به دلیل Cascade از بین خواهند رفت.
    """
    weld = session.get(Weld, weld_pk)
    if weld is None:
        return False
    session.delete(weld)
    session.flush()
    logger.info("Deleted Weld PK=%d.", weld_pk)
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_joint_history_for_weld(session: Session, weld_pk: int) -> List[JointHistory]:
    """
    دریافت تاریخچه‌ی دقیق تمامی رویدادهای تعمیری و تغییر وضعیت سرجوش.
    """
    weld = session.get(Weld, weld_pk)
    if weld is None:
        return []

    return (
        weld.history
        if hasattr(weld, "history")
        else session.query(JointHistory).filter(JointHistory.weld_id_fk == weld_pk).order_by(JointHistory.timestamp.asc()).all()
    )


def record_joint_history(
    session: Session,
    weld_pk: int,
    event_type: str,
    *,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    user_name: Optional[str] = None,
    notes: Optional[str] = None,
) -> JointHistory:
    """
    ثبت یک رویداد در تاریخچه‌ی جوش (مانند شروع تعمیری، پایان تعمیری، تغییر WPS و ...).
    """
    weld = session.get(Weld, weld_pk)
    if weld is None:
        raise ValidationError(f"Weld PK {weld_pk} does not exist.")

    history = JointHistory(
        weld_id_fk=weld_pk,
        event_type=event_type,
        old_value=old_value,
        new_value=new_value,
        user_name=user_name or "System",
        notes=notes,
    )
    session.add(history)
    session.flush()
    return history


# ══════════════════════════════════════════════
#  3. Repair Tracking & Lifecycle Workflows
# ══════════════════════════════════════════════

def record_weld_repair(
    session: Session,
    weld_pk: int,
    repair_notes: Optional[str] = None,
    inspector_name: Optional[str] = None,
) -> Optional[Weld]:
    """
    ثبت عملیات تعمیری سرجوش و افزایش خودکار شمارنده‌ی تعمیری.
    """
    weld = session.get(Weld, weld_pk)
    if weld is None:
        return None

    # Implementation note.
    weld.repair_count = (weld.repair_count or 0) + 1
    weld.status = WeldStatus.REPAIR_REQUIRED

    # Implementation note.
    record_joint_history(
        session,
        weld_pk=wel_pk,
        event_type="Repair Initiated",
        new_value=f"Repair Count: {weld.repair_count}",
        notes=repair_notes,
        user_name=inspector_name,
    )

    session.flush()
    logger.info("Recorded Repair for Weld PK=%d. New Repair Count=%d.", weld_pk, weld.repair_count)
    return weld


def close_weld_for_ndt(
    session: Session,
    weld_pk: int,
    *,
    result: str,
    final_inspector_name: str,
    final_notes: Optional[str] = None,
) -> Optional[Weld]:
    """
    بستن پرونده‌ی بازرسی جوش با ثبت نتیجه‌ی نهایی (Accepted / Rejected / Repair).
    """
    weld = session.get(Weld, weld_pk)
    if weld is None:
        return None

    # Implementation note.
    if result == "Accept":
        weld.status = WeldStatus.NDT_ACCEPTED
    elif result == "Reject":
        weld.status = WeldStatus.REPAIR_REQUIRED
        # Implementation note.
        if weld.repair_count == 0:
            weld.repair_count = 1
    else:
        weld.status = WeldStatus.REPAIRED

    record_joint_history(
        session,
        weld_pk=wel_pk,
        event_type=f"NDT Final Result: {result}",
        new_value=weld.status,
        notes=final_notes,
        user_name=final_inspector_name,
    )

    session.flush()
    return weld


# ══════════════════════════════════════════════
#  4. Welder Performance Analytics
# ══════════════════════════════════════════════

def get_welder_repair_statistics(
    session: Session,
    project_id: int,
    *,
    welder_id: Optional[str] = None,
    weld_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """
    محاسبه‌ی شاخص نرخ تعمیری جوش و عملکرد جوشکاران پروژه.
    """
    _validate_project_id(project_id)

    q = session.query(
        Weld.welder_id,
        Weld.welder_name,
        Weld.weld_type,
        func.count(Weld.id).label("total_welds"),
        func.sum(case((Weld.repair_count > 0, 1), else_=0)).label("repaired_welds"),
    ).filter(Weld.project_id == project_id)

    if welder_id:
        q = q.filter(Weld.welder_id == welder_id)
    if weld_type:
        q = q.filter(Weld.weld_type == weld_type)
    if date_from:
        q = q.filter(Weld.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(Weld.created_at <= datetime.combine(date_to, datetime.max.time()))

    q = q.group_by(Weld.welder_id, Weld.welder_name, Weld.weld_type)

    results = []
    for row in q.all():
        total = int(row.total_welds or 0)
        repaired = int(row.repaired_welds or 0)
        rate = _pct(repaired, total)

        # Implementation note.
        risk = "Good"
        if rate > 5.0:
            risk = "Critical"
        elif rate > 3.0:
            risk = "Warning"

        results.append({
            "welder_id": row.welder_id,
            "welder_name": row.welder_name or "N/A",
            "weld_type": row.weld_type,
            "total_welds": total,
            "repaired_welds": repaired,
            "repair_rate_pct": rate,
            "performance_risk": risk,
        })

    return sorted(results, key=lambda x: x["repair_rate_pct"], reverse=True)


def get_repair_trend_by_welder(
    session: Session,
    project_id: int,
    welder_id: str,
) -> List[Dict[str, Any]]:
    """
    نمودار روند تعمیری برای یک جوشکار خاص در طول زمان.
    """
    q = session.query(
        func.extract("month", Weld.created_at).label("month"),
        func.extract("year", Weld.created_at).label("year"),
        func.count(Weld.id).label("total"),
        func.sum(case((Weld.repair_count > 0, 1), else_=0)).label("repaired"),
    ).filter(
        Weld.project_id == project_id,
        Weld.welder_id == welder_id,
    ).group_by("year", "month").order_by("year", "month")

    trend = []
    for row in q.all():
        total = int(row.total or 0)
        repaired = int(row.repaired or 0)
        trend.append({
            "period": f"{int(row.year)}-{int(row.month):02d}",
            "total_welds": total,
            "repaired_welds": repaired,
            "repair_rate_pct": _pct(repaired, total),
        })
    return trend


# ══════════════════════════════════════════════
#  5. NDT Integration Queries
# ══════════════════════════════════════════════

def get_weld_ndt_summary(
    session: Session,
    weld_pk: int,
) -> List[Dict[str, Any]]:
    """دریافت خلاصه‌ی نتایج بازرسی‌های غیرمخرب برای یک جوش."""
    weld = session.get(Weld, weld_pk)
    if weld is None:
        return []

    records = session.query(NDTRecord).filter(NDTRecord.weld_id_fk == weld_pk).order_by(NDTRecord.ndt_method, NDTRecord.inspection_date.asc()).all()

    summary = []
    for r in records:
        summary.append({
            "method": r.ndt_method,
            "date": r.inspection_date,
            "inspector": r.inspector_id,
            "report_no": r.report_number,
            "result": r.result,
            "remarks": r.remarks,
        })
    return summary


def get_uninspected_welds(
    session: Session,
    project_id: int,
    *,
    ndt_method: Optional[str] = None,
    line_number: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[Weld]:
    """
    دریافت لیست جوش‌هایی که بازرسی NDT با روش مشخص (مثلاً RT) بر روی آن‌ها انجام نشده است (Backlog بازرسی).
    """
    _validate_project_id(project_id)

    # Implementation note.
    inspected_ids_sub = session.query(NDTRecord.weld_id_fk).filter(
        NDTRecord.ndt_method == (ndt_method or "RT")
    ).subquery()

    q = session.query(Weld).filter(
        Weld.project_id == project_id,
        Weld.id.notin_(session.query(inspected_ids_sub.c.weld_id_fk)),
        Weld.status.notin_(("Cancelled", "Cut Out")),
    )
    if line_number:
        q = q.filter(Weld.line_number.ilike(f"%{line_number}%"))
    if ndt_method:
        q = q.filter(Weld.id.notin_(session.query(NDTRecord.weld_id_fk).filter(NDTRecord.ndt_method == ndt_method)))

    q = q.order_by(Weld.line_number.asc(), Weld.spool_id.asc().nullslast(), Weld.id.asc())

    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_failed_welds(
    session: Session,
    project_id: int,
    *,
    weld_type: Optional[str] = None,
    limit_repair_count: int = 0,
    offset: int = 0,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    دریافت لیست جوش‌های مردود که نیاز به تعمیری دارند (Backlog تعمیرات).
    """
    from db.queries.ndt_queries import NDTResult
    _validate_project_id(project_id)

    q = session.query(Weld).filter(
        Weld.project_id == project_id,
        Weld.status.in_(("Repair Required",)),
    )
    if weld_type:
        q = q.filter(Weld.weld_type == weld_type)
    if limit_repair_count:
        q = q.filter(Weld.repair_count >= limit_repair_count)

    q = q.order_by(Weld.repair_count.desc(), Weld.created_at.desc())

    rows = _apply_pagination(q, offset=offset, limit=limit).all()
    results = []
    for r in rows:
        results.append({
            "weld_pk": r.id,
            "weld_id": r.weld_id,
            "line_number": r.line_number,
            "spool_id": r.spool_id,
            "welder_id": r.welder_id,
            "weld_status": r.status,
            "repair_count": r.repair_count or 0,
            "weld_type": r.weld_type,
            "recommended_action": "Cut Out" if r.repair_count >= 2 else "Repair",
        })
    return results


# ══════════════════════════════════════════════
#  6. WPS Integration Queries
# ══════════════════════════════════════════════

def get_weld_wps_info(session: Session, weld_pk: int) -> Optional[WPS_PQR]:
    weld = session.get(Weld, weld_pk)
    if weld is None or not weld.wps_pqr_id:
        return None
    return session.get(WPS_PQR, weld.wps_pqr_id)


def get_welds_by_wps(
    session: Session,
    project_id: int,
    wps_pqr_id: int,
    *,
    offset: int = 0,
    limit: int = 100,
) -> List[Weld]:
    _validate_project_id(project_id)
    q = session.query(Weld).filter(
        Weld.project_id == project_id,
        Weld.wps_pqr_id == wps_pqr_id,
    ).order_by(Weld.line_number.asc(), Weld.id.asc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


# ══════════════════════════════════════════════
#  7. Bulk / Advanced Queries
# ══════════════════════════════════════════════

def import_shop_weld_batch(
    session: Session,
    batch_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 150,
) -> int:
    """
    وارد کردن انبوه سوابق جوش‌های کارگاهی از روی خروجی سیستم‌های مدیریت کارگاه.
    """
    if not batch_data:
        return 0

    records = [Weld(**item) for item in batch_data]
    total = len(records)

    for i in range(0, total, batch_size):
        session.add_all(records[i : i + batch_size])
        session.flush()

    logger.info("Bulk imported %d shop weld records.", total)
    return total


# ══════════════════════════════════════════════
#  8. Welding Performance Dashboard Stats
# ══════════════════════════════════════════════

def get_weld_dashboard_stats(session: Session, project_id: int) -> Dict[str, Any]:
    """
    آمار جامع و لحظه‌ای وضعیت جوشکاری صنعتی پروژه جهت نمایش در داشبورد مدیریت کیفیت.
    
    شامل:
      • تعداد کل سرجوش‌ها
      • آمار وضعیت‌ها (Pending, Welded, Repair Required, NDT Accepted)
      • تعداد تعمیری کل و نرخ تعمیری کلی
      • تعداد جوش‌های مردود و نیازمند برش (Cut-Out)
      • آمار جوش‌های کارگاهی (Shop) در مقابل میدانی (Field)
    """
    _validate_project_id(project_id)

    # Implementation note.
    total_welds = count_welds(session, project_id)

    # Implementation note.
    status_counts = (
        session.query(Weld.status, func.count(Weld.id))
        .filter(Weld.project_id == project_id)
        .group_by(Weld.status)
        .all()
    )
    status_map = {status or "Unknown": count for status, count in status_counts}

    # Implementation note.
    repaired = session.query(func.sum(Weld.repair_count)).filter(Weld.project_id == project_id).scalar() or 0
    repair_rate = _pct(repaired, total_welds) if total_welds else 0.0

    # Implementation note.
    failed_count = session.query(func.count(Weld.id)).filter(
        Weld.project_id == project_id,
        Weld.repair_count >= 2,
    ).scalar() or 0

    # Implementation note.
    shop_count = session.query(func.count(Weld.id)).filter(
        Weld.project_id == project_id,
        Weld.weld_type == "Shop",
    ).scalar() or 0

    field_count = session.query(func.count(Weld.id)).filter(
        Weld.project_id == project_id,
        Weld.weld_type == "Field",
    ).scalar() or 0

    # Implementation note.
    accepted_ndt = status_map.get("NDT Accepted", 0)

    return {
        "weld_summary": {
            "total_registered_joints": total_welds,
            "accepted_joints": accepted_ndt,
            "pending_welds": status_map.get("Pending", 0) + status_map.get("Welded", 0),
            "repair_required": status_map.get("Repair Required", 0) + status_map.get("Repaired", 0),
            "cut_out_recommended": failed_count,
        },
        "performance": {
            "total_repair_events": int(repaired),
            "overall_repair_rate_pct": repair_rate,
            "shop_welds": shop_count,
            "field_welds": field_count,
            "ndt_acceptance_rate_pct": _pct(accepted_ndt, total_welds),
        }
    }