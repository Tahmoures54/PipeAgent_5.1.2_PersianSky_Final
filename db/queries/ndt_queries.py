# -*- coding: utf-8 -*-
"""
db/queries/ndt_queries.py – PipeAgent v5.1
===========================================
Non-Destructive Testing (NDT) & Quality Inspection Query Layer.

Standards referenced:
  • ASME B31.3   – Process Piping (Examination requirements)
  • ASME Sec. V  – Nondestructive Examination
  • API 1104     – Welding of Pipelines
  • ASME Sec. IX – Welding Qualification

Covers:
  • NDTRecord            – RT / UT / PT / MT / VT results
  • Welder Repair Rate   – Statistical performance monitoring
  • NDT Coverage         – Actual vs. Line-List required percentage
  • PMITestRecord        – Positive Material Identification (XRF/OES)
  • DimensionalCheck     – Spool dimensional tolerance verification
  • LeakTestRecord       – Sensitive leak / Bubble / Helium testing
  • TestRequest          – NDT request workflow integration

Performance: All aggregate KPIs use SQL-level GROUP BY to avoid
loading records into memory (critical for 100k+ weld projects).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, joinedload

from db.models import (
    DimensionalCheckRecord,
    LeakTestRecord,
    LineListItem,
    NDTRecord,
    PMITestRecord,
    Spool,
    TestRequest,
    Weld,
    Welder,
)

try:
    from core.exceptions import DatabaseError, ValidationError
except ImportError:
    class DatabaseError(Exception): pass
    class ValidationError(Exception): pass

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
#  Constants – NDT domain vocabulary
# ══════════════════════════════════════════════

class NDTMethod:
    """روش‌های استاندارد بازرسی غیرمخرب."""
    RT = "RT"    # Radiographic Testing
    UT = "UT"    # Ultrasonic Testing
    PT = "PT"    # Liquid Penetrant Testing
    MT = "MT"    # Magnetic Particle Testing
    VT = "VT"    # Visual Testing
    PAUT = "PAUT"  # Phased Array UT
    TOFD = "TOFD"  # Time of Flight Diffraction
    HT = "HT"    # Hardness Testing

    ALL = (RT, UT, PT, MT, VT, PAUT, TOFD, HT)
    VOLUMETRIC = (RT, UT, PAUT, TOFD)
    SURFACE = (PT, MT, VT)


class NDTResult:
    """نتایج ممکن یک بازرسی."""
    PENDING = "Pending"
    ACCEPT = "Accept"
    REJECT = "Reject"
    REPAIR = "Repair"
    RE_SHOOT = "Re-Shoot"
    CANCELLED = "Cancelled"

    ALL = (PENDING, ACCEPT, REJECT, REPAIR, RE_SHOOT, CANCELLED)
    FAILED = (REJECT, REPAIR, RE_SHOOT)
    CLOSED = (ACCEPT, REJECT, CANCELLED)


# Implementation note.
REPAIR_RATE_WARNING_THRESHOLD = 3.0
REPAIR_RATE_CRITICAL_THRESHOLD = 5.0


__all__ = [
    "NDTMethod",
    "NDTResult",
    "REPAIR_RATE_WARNING_THRESHOLD",
    "REPAIR_RATE_CRITICAL_THRESHOLD",
    # NDT Records
    "get_ndt_records",
    "get_ndt_record_by_id",
    "get_ndt_records_for_weld",
    "count_ndt_records",
    "create_ndt_record",
    "create_ndt_records_bulk",
    "update_ndt_record",
    "record_ndt_result",
    "delete_ndt_record",
    # Analytics – Repair Rate
    "get_welder_repair_rates",
    "get_welder_repair_rate",
    "get_repair_rate_by_method",
    "get_repair_trend_by_month",
    # Analytics – Coverage
    "get_ndt_coverage_by_line",
    "get_welds_pending_ndt",
    "get_rejected_welds",
    # PMI
    "get_pmi_records",
    "get_pmi_record_by_id",
    "create_pmi_record",
    "create_pmi_records_bulk",
    "update_pmi_record",
    "delete_pmi_record",
    "get_pmi_mismatches",
    # Dimensional
    "get_dimensional_checks",
    "get_dimensional_check_by_id",
    "create_dimensional_check",
    "update_dimensional_check",
    "delete_dimensional_check",
    "evaluate_dimensional_tolerance",
    # Leak Test
    "get_leak_test_records",
    "get_leak_test_by_id",
    "create_leak_test_record",
    "update_leak_test_record",
    "delete_leak_test_record",
    # Test Requests (NDT workflow)
    "get_open_ndt_requests",
    "get_overdue_ndt_requests",
    # Dashboard
    "get_ndt_dashboard_stats",
]


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def _validate_project_id(project_id: int) -> None:
    if not isinstance(project_id, int) or project_id <= 0:
        raise ValidationError(
            f"Invalid project_id: {project_id!r}. Must be a positive integer.",
        )


def _apply_pagination(query, *, offset: int = 0, limit: Optional[int] = 100):
    if offset > 0:
        query = query.offset(offset)
    if limit is not None and limit > 0:
        query = query.limit(limit)
    return query


def _safe_update(obj: Any, data: Dict[str, Any], *, exclude: Optional[Set[str]] = None) -> int:
    exclude = exclude or {"id", "created_at"}
    changed = 0
    for key, value in data.items():
        if key in exclude:
            continue
        if hasattr(obj, key):
            if getattr(obj, key) != value:
                setattr(obj, key, value)
                changed += 1
        else:
            logger.warning("Unknown field '%s' ignored for %s", key, type(obj).__name__)
    return changed


def _pct(numerator: float, denominator: float, digits: int = 2) -> float:
    """محاسبه‌ی امن درصد (جلوگیری از تقسیم بر صفر)."""
    if not denominator:
        return 0.0
    return round(numerator / denominator * 100, digits)


# ══════════════════════════════════════════════
#  1. NDT Records – CRUD
# ══════════════════════════════════════════════

def get_ndt_records(
    session: Session,
    project_id: int,
    *,
    ndt_method: Optional[str] = None,
    result: Optional[str] = None,
    inspector_id: Optional[str] = None,
    line_number: Optional[str] = None,
    welder_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    report_number: Optional[str] = None,
    offset: int = 0,
    limit: int = 200,
) -> List[NDTRecord]:
    """
    دریافت سوابق بازرسی غیرمخرب با فیلترهای ترکیبی.

    از JOIN با جدول Weld استفاده می‌شود تا فیلتر بر اساس
    project_id، line_number و welder_id ممکن باشد.
    """
    _validate_project_id(project_id)

    q = (
        session.query(NDTRecord)
        .join(Weld, NDTRecord.weld_id_fk == Weld.id)
        .filter(Weld.project_id == project_id)
    )

    if ndt_method:
        q = q.filter(NDTRecord.ndt_method == ndt_method)
    if result:
        q = q.filter(NDTRecord.result == result)
    if inspector_id:
        q = q.filter(NDTRecord.inspector_id == inspector_id)
    if report_number:
        q = q.filter(NDTRecord.report_number.ilike(f"%{report_number}%"))
    if line_number:
        q = q.filter(Weld.line_number.ilike(f"%{line_number}%"))
    if welder_id:
        q = q.filter(Weld.welder_id == welder_id)
    if date_from:
        q = q.filter(NDTRecord.inspection_date >= date_from)
    if date_to:
        q = q.filter(NDTRecord.inspection_date <= date_to)

    q = q.options(joinedload(NDTRecord.weld))
    q = q.order_by(NDTRecord.inspection_date.desc().nullslast(), NDTRecord.id.desc())

    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_ndt_record_by_id(session: Session, record_id: int) -> Optional[NDTRecord]:
    """دریافت یک رکورد NDT بر اساس شناسه."""
    return session.get(NDTRecord, record_id)


def get_ndt_records_for_weld(session: Session, weld_pk: int) -> List[NDTRecord]:
    """دریافت تمام بازرسی‌های ثبت‌شده برای یک سرجوش خاص (شامل Re-Shootها)."""
    return (
        session.query(NDTRecord)
        .filter(NDTRecord.weld_id_fk == weld_pk)
        .order_by(NDTRecord.inspection_date.asc().nullsfirst(), NDTRecord.id.asc())
        .all()
    )


def count_ndt_records(
    session: Session,
    project_id: int,
    *,
    ndt_method: Optional[str] = None,
    result: Optional[str] = None,
) -> int:
    """شمارش رکوردهای NDT بدون بارگذاری در حافظه."""
    _validate_project_id(project_id)
    q = (
        session.query(func.count(NDTRecord.id))
        .join(Weld, NDTRecord.weld_id_fk == Weld.id)
        .filter(Weld.project_id == project_id)
    )
    if ndt_method:
        q = q.filter(NDTRecord.ndt_method == ndt_method)
    if result:
        q = q.filter(NDTRecord.result == result)
    return q.scalar() or 0


def create_ndt_record(session: Session, **kwargs: Any) -> NDTRecord:
    """
    ثبت یک بازرسی غیرمخرب جدید.

    Raises:
        ValidationError: اگر weld_id_fk یا ndt_method نامعتبر باشد.
    """
    weld_pk = kwargs.get("weld_id_fk")
    if not weld_pk:
        raise ValidationError("weld_id_fk is required to create an NDTRecord.")

    weld = session.get(Weld, weld_pk)
    if weld is None:
        raise ValidationError(f"Weld with PK {weld_pk} does not exist.")

    method = kwargs.get("ndt_method")
    if method and method not in NDTMethod.ALL:
        logger.warning("Non-standard NDT method used: %s", method)

    record = NDTRecord(**kwargs)
    session.add(record)
    session.flush()
    logger.info(
        "Created NDTRecord ID=%d Method=%s Weld=%s Result=%s",
        record.id, record.ndt_method, weld.weld_id, record.result,
    )
    return record


def create_ndt_records_bulk(
    session: Session,
    records_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 200,
) -> int:
    """ثبت دسته‌ای نتایج بازرسی (مناسب برای وارد کردن گزارش پیمانکار NDT از Excel)."""
    if not records_data:
        return 0

    records = [NDTRecord(**data) for data in records_data]
    total = len(records)

    for i in range(0, total, batch_size):
        session.add_all(records[i : i + batch_size])
        session.flush()

    logger.info("Bulk imported %d NDTRecords.", total)
    return total


def update_ndt_record(session: Session, record_id: int, **kwargs: Any) -> Optional[NDTRecord]:
    """به‌روزرسانی یک رکورد NDT."""
    record = session.get(NDTRecord, record_id)
    if record is None:
        return None
    changed = _safe_update(record, kwargs)
    if changed:
        session.flush()
        logger.info("Updated NDTRecord ID=%d (%d fields).", record_id, changed)
    return record


def record_ndt_result(
    session: Session,
    record_id: int,
    result: str,
    *,
    inspector_id: Optional[str] = None,
    report_number: Optional[str] = None,
    inspection_date: Optional[date] = None,
    remarks: Optional[str] = None,
    auto_update_weld: bool = True,
) -> Optional[NDTRecord]:
    """
    ثبت نتیجه‌ی نهایی بازرسی و همگام‌سازی خودکار وضعیت سرجوش.

    منطق کسب‌وکار:
      • Accept → وضعیت جوش به "NDT Accepted" تغییر می‌کند
      • Reject/Repair → وضعیت جوش به "Repair Required" و repair_count افزایش می‌یابد
    """
    record = session.get(NDTRecord, record_id)
    if record is None:
        logger.warning("NDTRecord ID=%d not found.", record_id)
        return None

    if result not in NDTResult.ALL:
        raise ValidationError(
            f"Invalid NDT result: {result!r}. Allowed: {NDTResult.ALL}",
        )

    old_result = record.result
    record.result = result
    if inspector_id:
        record.inspector_id = inspector_id
    if report_number:
        record.report_number = report_number
    record.inspection_date = inspection_date or date.today()
    if remarks:
        record.remarks = remarks

    # Implementation note.
    if auto_update_weld and record.weld_id_fk:
        weld = session.get(Weld, record.weld_id_fk)
        if weld is not None:
            if result == NDTResult.ACCEPT:
                weld.status = "NDT Accepted"
            elif result in NDTResult.FAILED:
                weld.status = "Repair Required"
                # Implementation note.
                if old_result not in NDTResult.FAILED:
                    weld.repair_count = (weld.repair_count or 0) + 1

    session.flush()
    logger.info(
        "NDTRecord ID=%d result set to '%s' by %s.",
        record_id, result, inspector_id or "system",
    )
    return record


def delete_ndt_record(session: Session, record_id: int) -> bool:
    """حذف یک رکورد بازرسی."""
    record = session.get(NDTRecord, record_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    logger.info("Deleted NDTRecord ID=%d.", record_id)
    return True


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def get_welder_repair_rates(
    session: Session,
    project_id: int,
    *,
    ndt_method: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    min_welds: int = 1,
    order_by_worst: bool = True,
) -> List[Dict[str, Any]]:
    """
    محاسبه‌ی نرخ تعمیر (Repair Rate) برای تمام جوشکاران پروژه.

    این شاخص مهم‌ترین معیار ارزیابی عملکرد جوشکاران است و در
    قراردادهای EPC معمولاً سقف ۳٪ برای آن تعیین می‌شود. جوشکارانی
    که از این حد عبور کنند باید مجدداً آزمون صلاحیت (Re-Qualification)
    بدهند یا از پروژه کنار گذاشته شوند.

    Formula:
        Repair Rate (%) = (Rejected Joints / Total Inspected Joints) × 100

    Returns:
        لیستی از دیکشنری‌ها شامل آمار هر جوشکار به‌همراه سطح ریسک.
    """
    _validate_project_id(project_id)

    # Implementation note.
    rejected_case = case(
        (NDTRecord.result.in_(NDTResult.FAILED), 1),
        else_=0,
    )
    accepted_case = case(
        (NDTRecord.result == NDTResult.ACCEPT, 1),
        else_=0,
    )

    q = (
        session.query(
            Weld.welder_id.label("welder_id"),
            func.max(Weld.welder_name).label("welder_name"),
            func.count(NDTRecord.id).label("total_inspected"),
            func.sum(rejected_case).label("total_rejected"),
            func.sum(accepted_case).label("total_accepted"),
        )
        .join(NDTRecord, NDTRecord.weld_id_fk == Weld.id)
        .filter(
            Weld.project_id == project_id,
            Weld.welder_id.isnot(None),
            NDTRecord.result != NDTResult.PENDING,
        )
    )

    if ndt_method:
        q = q.filter(NDTRecord.ndt_method == ndt_method)
    if date_from:
        q = q.filter(NDTRecord.inspection_date >= date_from)
    if date_to:
        q = q.filter(NDTRecord.inspection_date <= date_to)

    q = q.group_by(Weld.welder_id).having(func.count(NDTRecord.id) >= min_welds)

    results: List[Dict[str, Any]] = []
    for row in q.all():
        total = int(row.total_inspected or 0)
        rejected = int(row.total_rejected or 0)
        accepted = int(row.total_accepted or 0)
        rate = _pct(rejected, total)

        if rate >= REPAIR_RATE_CRITICAL_THRESHOLD:
            risk = "Critical"
        elif rate >= REPAIR_RATE_WARNING_THRESHOLD:
            risk = "Warning"
        else:
            risk = "Acceptable"

        results.append({
            "welder_id": row.welder_id,
            "welder_name": row.welder_name or "N/A",
            "total_inspected": total,
            "total_accepted": accepted,
            "total_rejected": rejected,
            "repair_rate_pct": rate,
            "acceptance_rate_pct": _pct(accepted, total),
            "risk_level": risk,
            "requires_requalification": rate >= REPAIR_RATE_CRITICAL_THRESHOLD,
        })

    results.sort(
        key=lambda r: r["repair_rate_pct"],
        reverse=order_by_worst,
    )
    return results


def get_welder_repair_rate(
    session: Session,
    project_id: int,
    welder_id: str,
    *,
    ndt_method: Optional[str] = None,
) -> Dict[str, Any]:
    """محاسبه‌ی نرخ تعمیر برای یک جوشکار مشخص."""
    rows = get_welder_repair_rates(
        session, project_id, ndt_method=ndt_method, min_welds=0,
    )
    for row in rows:
        if row["welder_id"] == welder_id:
            return row
    return {
        "welder_id": welder_id,
        "welder_name": "N/A",
        "total_inspected": 0,
        "total_accepted": 0,
        "total_rejected": 0,
        "repair_rate_pct": 0.0,
        "acceptance_rate_pct": 0.0,
        "risk_level": "No Data",
        "requires_requalification": False,
    }


def get_repair_rate_by_method(
    session: Session,
    project_id: int,
) -> Dict[str, Dict[str, Any]]:
    """
    نرخ تعمیر تفکیک‌شده بر اساس روش بازرسی.
    برای تشخیص اینکه آیا مشکل در جوشکاری است یا در روش بازرسی خاص.
    """
    _validate_project_id(project_id)

    rejected_case = case((NDTRecord.result.in_(NDTResult.FAILED), 1), else_=0)

    rows = (
        session.query(
            NDTRecord.ndt_method,
            func.count(NDTRecord.id).label("total"),
            func.sum(rejected_case).label("rejected"),
        )
        .join(Weld, NDTRecord.weld_id_fk == Weld.id)
        .filter(
            Weld.project_id == project_id,
            NDTRecord.result != NDTResult.PENDING,
        )
        .group_by(NDTRecord.ndt_method)
        .all()
    )

    return {
        row.ndt_method: {
            "total_inspected": int(row.total or 0),
            "total_rejected": int(row.rejected or 0),
            "repair_rate_pct": _pct(int(row.rejected or 0), int(row.total or 0)),
        }
        for row in rows
    }


def get_repair_trend_by_month(
    session: Session,
    project_id: int,
    *,
    months_back: int = 12,
) -> List[Dict[str, Any]]:
    """
    روند ماهانه‌ی نرخ تعمیر (برای رسم نمودار خطی در داشبورد).
    نشان می‌دهد آیا کیفیت جوشکاری در حال بهبود است یا افت.
    """
    _validate_project_id(project_id)

    cutoff = date.today() - timedelta(days=months_back * 31)
    rejected_case = case((NDTRecord.result.in_(NDTResult.FAILED), 1), else_=0)

    # Implementation note.
    dialect = session.bind.dialect.name if session.bind else "sqlite"
    if dialect == "postgresql":
        month_expr = func.to_char(NDTRecord.inspection_date, "YYYY-MM")
    else:
        month_expr = func.strftime("%Y-%m", NDTRecord.inspection_date)

    rows = (
        session.query(
            month_expr.label("month"),
            func.count(NDTRecord.id).label("total"),
            func.sum(rejected_case).label("rejected"),
        )
        .join(Weld, NDTRecord.weld_id_fk == Weld.id)
        .filter(
            Weld.project_id == project_id,
            NDTRecord.inspection_date.isnot(None),
            NDTRecord.inspection_date >= cutoff,
            NDTRecord.result != NDTResult.PENDING,
        )
        .group_by(month_expr)
        .order_by(month_expr)
        .all()
    )

    return [
        {
            "month": row.month,
            "total_inspected": int(row.total or 0),
            "total_rejected": int(row.rejected or 0),
            "repair_rate_pct": _pct(int(row.rejected or 0), int(row.total or 0)),
        }
        for row in rows
    ]


# ══════════════════════════════════════════════
#  3. Analytics – NDT Coverage Compliance
# ══════════════════════════════════════════════

def get_ndt_coverage_by_line(
    session: Session,
    project_id: int,
    *,
    ndt_method: str = NDTMethod.RT,
    only_non_compliant: bool = False,
) -> List[Dict[str, Any]]:
    """
    مقایسه‌ی درصد پوشش واقعی NDT با درصد الزامی مندرج در Line List.

    این گزارش برای ممیزی‌های کارفرما و TPI حیاتی است؛ زیرا نشان می‌دهد
    آیا پیمانکار به تعهدات بازرسی خود (مثلاً 10% RT) عمل کرده است یا خیر.

    Args:
        ndt_method:         روش مورد بررسی (پیش‌فرض RT)
        only_non_compliant: فقط خطوطی که کسری پوشش دارند

    Returns:
        لیست خطوط با آمار پوشش و وضعیت انطباق.
    """
    _validate_project_id(project_id)

    required_field = (
        LineListItem.ndt_percent_rt
        if ndt_method == NDTMethod.RT
        else LineListItem.ndt_percent_ut
    )

    # Implementation note.
    total_welds_sub = (
        session.query(
            Weld.line_number.label("line_number"),
            func.count(Weld.id).label("total_welds"),
        )
        .filter(Weld.project_id == project_id)
        .group_by(Weld.line_number)
        .subquery()
    )

    # Implementation note.
    inspected_sub = (
        session.query(
            Weld.line_number.label("line_number"),
            func.count(func.distinct(Weld.id)).label("inspected_welds"),
        )
        .join(NDTRecord, NDTRecord.weld_id_fk == Weld.id)
        .filter(
            Weld.project_id == project_id,
            NDTRecord.ndt_method == ndt_method,
            NDTRecord.result != NDTResult.CANCELLED,
        )
        .group_by(Weld.line_number)
        .subquery()
    )

    rows = (
        session.query(
            LineListItem.line_number,
            required_field.label("required_pct"),
            func.coalesce(total_welds_sub.c.total_welds, 0).label("total_welds"),
            func.coalesce(inspected_sub.c.inspected_welds, 0).label("inspected_welds"),
        )
        .outerjoin(total_welds_sub, LineListItem.line_number == total_welds_sub.c.line_number)
        .outerjoin(inspected_sub, LineListItem.line_number == inspected_sub.c.line_number)
        .filter(LineListItem.project_id == project_id)
        .order_by(LineListItem.line_number)
        .all()
    )

    output: List[Dict[str, Any]] = []
    for row in rows:
        total = int(row.total_welds or 0)
        inspected = int(row.inspected_welds or 0)
        required_pct = float(row.required_pct or 0)
        actual_pct = _pct(inspected, total)

        # Implementation note.
        required_count = int(-(-total * required_pct // 100)) if total else 0
        shortfall = max(0, required_count - inspected)
        compliant = shortfall == 0

        if only_non_compliant and compliant:
            continue

        output.append({
            "line_number": row.line_number,
            "total_welds": total,
            "inspected_welds": inspected,
            "required_pct": required_pct,
            "actual_pct": actual_pct,
            "required_count": required_count,
            "shortfall_count": shortfall,
            "is_compliant": compliant,
            "method": ndt_method,
        })

    return output


def get_welds_pending_ndt(
    session: Session,
    project_id: int,
    *,
    ndt_method: Optional[str] = None,
    line_number: Optional[str] = None,
    offset: int = 0,
    limit: int = 200,
) -> List[Weld]:
    """
    دریافت سرجوش‌هایی که هنوز هیچ بازرسی (یا بازرسی با روش مشخص) نشده‌اند.
    خروجی این تابع مستقیماً به لیست کاری بازرسان (Inspection Backlog) تبدیل می‌شود.
    """
    _validate_project_id(project_id)

    # Implementation note.
    inspected_q = session.query(NDTRecord.weld_id_fk)
    if ndt_method:
        inspected_q = inspected_q.filter(NDTRecord.ndt_method == ndt_method)
    inspected_ids = inspected_q.subquery()

    q = session.query(Weld).filter(
        Weld.project_id == project_id,
        Weld.id.notin_(session.query(inspected_ids.c.weld_id_fk)),
        Weld.status.notin_(("Cancelled", "Cut Out")),
    )

    if line_number:
        q = q.filter(Weld.line_number.ilike(f"%{line_number}%"))

    q = q.order_by(Weld.line_number, Weld.weld_id)
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_rejected_welds(
    session: Session,
    project_id: int,
    *,
    include_repaired: bool = False,
    offset: int = 0,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    لیست سرجوش‌های مردود که نیاز به تعمیر یا برش (Cut-Out) دارند.
    شامل تعداد دفعات تعمیر برای شناسایی جوش‌های مشکل‌دار مزمن.
    """
    _validate_project_id(project_id)

    q = (
        session.query(
            Weld.id,
            Weld.weld_id,
            Weld.line_number,
            Weld.welder_id,
            Weld.welder_name,
            Weld.repair_count,
            Weld.status,
            NDTRecord.ndt_method,
            NDTRecord.result,
            NDTRecord.report_number,
            NDTRecord.inspection_date,
            NDTRecord.remarks,
        )
        .join(NDTRecord, NDTRecord.weld_id_fk == Weld.id)
        .filter(
            Weld.project_id == project_id,
            NDTRecord.result.in_(NDTResult.FAILED),
        )
    )

    if not include_repaired:
        q = q.filter(Weld.status != "NDT Accepted")

    q = q.order_by(Weld.repair_count.desc(), NDTRecord.inspection_date.desc())
    rows = _apply_pagination(q, offset=offset, limit=limit).all()

    return [
        {
            "weld_pk": r.id,
            "weld_id": r.weld_id,
            "line_number": r.line_number,
            "welder_id": r.welder_id,
            "welder_name": r.welder_name,
            "repair_count": r.repair_count or 0,
            "weld_status": r.status,
            "ndt_method": r.ndt_method,
            "ndt_result": r.result,
            "report_number": r.report_number,
            "inspection_date": r.inspection_date,
            "remarks": r.remarks,
            # Implementation note.
            "cut_out_recommended": (r.repair_count or 0) >= 2,
        }
        for r in rows
    ]


# ══════════════════════════════════════════════
#  4. PMI – Positive Material Identification
# ══════════════════════════════════════════════

def get_pmi_records(
    session: Session,
    project_id: int,
    *,
    result: Optional[str] = None,
    line_number: Optional[str] = None,
    heat_number: Optional[str] = None,
    component_type: Optional[str] = None,
    pmi_method: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[PMITestRecord]:
    """دریافت سوابق آزمون شناسایی مثبت متریال (XRF / OES)."""
    _validate_project_id(project_id)
    q = session.query(PMITestRecord).filter(PMITestRecord.project_id == project_id)

    if result:
        q = q.filter(PMITestRecord.result == result)
    if line_number:
        q = q.filter(PMITestRecord.line_number.ilike(f"%{line_number}%"))
    if heat_number:
        q = q.filter(PMITestRecord.heat_number == heat_number)
    if component_type:
        q = q.filter(PMITestRecord.component_type == component_type)
    if pmi_method:
        q = q.filter(PMITestRecord.pmi_method == pmi_method)

    q = q.order_by(PMITestRecord.test_date.desc().nullslast())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_pmi_record_by_id(session: Session, record_id: int) -> Optional[PMITestRecord]:
    """دریافت رکورد PMI بر اساس شناسه."""
    return session.get(PMITestRecord, record_id)


def create_pmi_record(session: Session, **kwargs: Any) -> PMITestRecord:
    """
    ثبت نتیجه‌ی آزمون PMI.
    اگر آلیاژ واقعی با آلیاژ مشخص‌شده مغایرت داشته باشد، نتیجه
    به‌صورت خودکار روی Reject تنظیم می‌شود.
    """
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a PMITestRecord.")
    _validate_project_id(kwargs["project_id"])

    specified = (kwargs.get("specified_material") or "").strip().upper()
    actual = (kwargs.get("actual_material") or "").strip().upper()

    # Implementation note.
    if specified and actual and "result" not in kwargs:
        kwargs["result"] = "Accept" if specified == actual else "Reject"

    record = PMITestRecord(**kwargs)
    session.add(record)
    session.flush()

    if record.result == "Reject":
        logger.warning(
            "PMI MISMATCH detected! ID=%d Heat=%s Specified=%s Actual=%s",
            record.id, record.heat_number, specified, actual,
        )
    return record


def create_pmi_records_bulk(
    session: Session,
    records_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 100,
) -> int:
    """ثبت دسته‌ای نتایج PMI از دستگاه XRF."""
    if not records_data:
        return 0
    records = [PMITestRecord(**data) for data in records_data]
    total = len(records)
    for i in range(0, total, batch_size):
        session.add_all(records[i : i + batch_size])
        session.flush()
    logger.info("Bulk imported %d PMITestRecords.", total)
    return total


def update_pmi_record(session: Session, record_id: int, **kwargs: Any) -> Optional[PMITestRecord]:
    """به‌روزرسانی رکورد PMI."""
    record = session.get(PMITestRecord, record_id)
    if record is None:
        return None
    if _safe_update(record, kwargs):
        session.flush()
    return record


def delete_pmi_record(session: Session, record_id: int) -> bool:
    """حذف رکورد PMI."""
    record = session.get(PMITestRecord, record_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    return True


def get_pmi_mismatches(session: Session, project_id: int) -> List[PMITestRecord]:
    """
    دریافت تمام موارد اختلاط آلیاژی کشف‌شده.
    این موارد باید فوراً NCR صادر شده و متریال از خط خارج شود.
    """
    _validate_project_id(project_id)
    return (
        session.query(PMITestRecord)
        .filter(
            PMITestRecord.project_id == project_id,
            PMITestRecord.result == "Reject",
        )
        .order_by(PMITestRecord.test_date.desc().nullslast())
        .all()
    )


# ══════════════════════════════════════════════
#  5. Dimensional Check
# ══════════════════════════════════════════════

def get_dimensional_checks(
    session: Session,
    project_id: int,
    *,
    spool_number: Optional[str] = None,
    spool_id: Optional[int] = None,
    result: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[DimensionalCheckRecord]:
    """دریافت سوابق بازرسی ابعادی اسپول‌ها."""
    _validate_project_id(project_id)
    q = session.query(DimensionalCheckRecord).filter(
        DimensionalCheckRecord.project_id == project_id,
    )

    if spool_number:
        q = q.filter(DimensionalCheckRecord.spool_number.ilike(f"%{spool_number}%"))
    if spool_id is not None:
        q = q.filter(DimensionalCheckRecord.spool_id == spool_id)
    if result:
        q = q.filter(DimensionalCheckRecord.result == result)

    q = q.order_by(DimensionalCheckRecord.check_date.desc().nullslast())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_dimensional_check_by_id(
    session: Session, record_id: int,
) -> Optional[DimensionalCheckRecord]:
    """دریافت رکورد بازرسی ابعادی."""
    return session.get(DimensionalCheckRecord, record_id)


def evaluate_dimensional_tolerance(
    nominal_mm: Optional[float],
    actual_mm: Optional[float],
    tolerance_mm: float = 3.0,
) -> Tuple[str, Optional[float]]:
    """
    ارزیابی انطباق ابعادی بر اساس تلرانس مجاز.

    مطابق عرف Shop Fabrication، تلرانس طول کلی اسپول معمولاً ±3mm است.

    Returns:
        (result, deviation) → ("Accept"/"Reject", انحراف بر حسب میلی‌متر)
    """
    if nominal_mm is None or actual_mm is None:
        return "Pending", None
    deviation = round(actual_mm - nominal_mm, 2)
    result = "Accept" if abs(deviation) <= tolerance_mm else "Reject"
    return result, deviation


def create_dimensional_check(session: Session, **kwargs: Any) -> DimensionalCheckRecord:
    """
    ثبت بازرسی ابعادی اسپول با ارزیابی خودکار تلرانس.
    """
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required for DimensionalCheckRecord.")
    _validate_project_id(kwargs["project_id"])

    # Implementation note.
    if "result" not in kwargs:
        result, _dev = evaluate_dimensional_tolerance(
            kwargs.get("overall_length_mm"),
            kwargs.get("actual_length_mm"),
            kwargs.get("tolerance_mm", 3.0),
        )
        kwargs["result"] = result

    record = DimensionalCheckRecord(**kwargs)
    session.add(record)
    session.flush()
    logger.info(
        "Created DimensionalCheck ID=%d Spool=%s Result=%s",
        record.id, record.spool_number, record.result,
    )
    return record


def update_dimensional_check(
    session: Session, record_id: int, **kwargs: Any,
) -> Optional[DimensionalCheckRecord]:
    """به‌روزرسانی بازرسی ابعادی."""
    record = session.get(DimensionalCheckRecord, record_id)
    if record is None:
        return None
    if _safe_update(record, kwargs):
        session.flush()
    return record


def delete_dimensional_check(session: Session, record_id: int) -> bool:
    """حذف بازرسی ابعادی."""
    record = session.get(DimensionalCheckRecord, record_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    return True


# ══════════════════════════════════════════════
#  6. Leak Test
# ══════════════════════════════════════════════

def get_leak_test_records(
    session: Session,
    project_id: int,
    *,
    line_number: Optional[str] = None,
    test_package_id: Optional[int] = None,
    result: Optional[str] = None,
    leak_test_method: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[LeakTestRecord]:
    """دریافت سوابق تست نشتی (Bubble / Helium / Halogen / Sensitive Leak)."""
    _validate_project_id(project_id)
    q = session.query(LeakTestRecord).filter(LeakTestRecord.project_id == project_id)

    if line_number:
        q = q.filter(LeakTestRecord.line_number.ilike(f"%{line_number}%"))
    if test_package_id is not None:
        q = q.filter(LeakTestRecord.test_package_id == test_package_id)
    if result:
        q = q.filter(LeakTestRecord.result == result)
    if leak_test_method:
        q = q.filter(LeakTestRecord.leak_test_method == leak_test_method)

    q = q.order_by(LeakTestRecord.test_date.desc().nullslast())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_leak_test_by_id(session: Session, record_id: int) -> Optional[LeakTestRecord]:
    """دریافت رکورد تست نشتی."""
    return session.get(LeakTestRecord, record_id)


def create_leak_test_record(session: Session, **kwargs: Any) -> LeakTestRecord:
    """
    ثبت تست نشتی.
    اگر نشتی یافت‌شده تعمیر نشده باشد، نتیجه به‌صورت خودکار Reject می‌شود.
    """
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required for LeakTestRecord.")
    _validate_project_id(kwargs["project_id"])

    found = int(kwargs.get("leaks_found") or 0)
    repaired = int(kwargs.get("leaks_repaired") or 0)
    if "result" not in kwargs:
        kwargs["result"] = "Accept" if found == repaired else "Reject"

    record = LeakTestRecord(**kwargs)
    session.add(record)
    session.flush()
    logger.info(
        "Created LeakTest ID=%d Line=%s Found=%d Repaired=%d Result=%s",
        record.id, record.line_number, found, repaired, record.result,
    )
    return record


def update_leak_test_record(
    session: Session, record_id: int, **kwargs: Any,
) -> Optional[LeakTestRecord]:
    """به‌روزرسانی تست نشتی."""
    record = session.get(LeakTestRecord, record_id)
    if record is None:
        return None
    if _safe_update(record, kwargs):
        session.flush()
    return record


def delete_leak_test_record(session: Session, record_id: int) -> bool:
    """حذف تست نشتی."""
    record = session.get(LeakTestRecord, record_id)
    if record is None:
        return False
    session.delete(record)
    session.flush()
    return True


# ══════════════════════════════════════════════
#  7. NDT Test Requests (Workflow)
# ══════════════════════════════════════════════

def get_open_ndt_requests(
    session: Session,
    project_id: int,
    *,
    method: Optional[str] = None,
    priority: Optional[str] = None,
    assigned_to: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[TestRequest]:
    """دریافت درخواست‌های بازرسی باز (Backlog بازرسان)."""
    _validate_project_id(project_id)
    q = session.query(TestRequest).filter(
        TestRequest.project_id == project_id,
        TestRequest.request_type == "NDT",
        TestRequest.status.notin_(("Completed", "Cancelled")),
    )

    if method:
        q = q.filter(TestRequest.method == method)
    if priority:
        q = q.filter(TestRequest.priority == priority)
    if assigned_to:
        q = q.filter(TestRequest.assigned_to == assigned_to)

    q = q.order_by(
        TestRequest.required_date.asc().nullslast(),
        TestRequest.request_date.asc(),
    )
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_overdue_ndt_requests(
    session: Session,
    project_id: int,
    *,
    as_of: Optional[date] = None,
) -> List[TestRequest]:
    """
    درخواست‌های بازرسی که از تاریخ الزامی خود عبور کرده‌اند.
    این موارد مستقیماً باعث توقف پیشرفت خط و تأخیر در هیدروتست می‌شوند.
    """
    _validate_project_id(project_id)
    ref_date = as_of or date.today()
    return (
        session.query(TestRequest)
        .filter(
            TestRequest.project_id == project_id,
            TestRequest.request_type == "NDT",
            TestRequest.required_date < ref_date,
            TestRequest.status.notin_(("Completed", "Cancelled")),
        )
        .order_by(TestRequest.required_date.asc())
        .all()
    )


# ══════════════════════════════════════════════
#  8. Dashboard Statistics
# ══════════════════════════════════════════════

def get_ndt_dashboard_stats(
    session: Session,
    project_id: int,
) -> Dict[str, Any]:
    """
    آمار جامع بازرسی غیرمخرب برای داشبورد مدیریت کیفیت.

    خروجی شامل:
      • آمار کلی بازرسی و نرخ پذیرش
      • تفکیک بر اساس روش (RT/UT/PT/MT)
      • بدترین جوشکاران از نظر نرخ تعمیر
      • تعداد جوش‌های در انتظار بازرسی
      • خطوط دارای کسری پوشش NDT
      • آمار PMI، بازرسی ابعادی و تست نشتی
    """
    _validate_project_id(project_id)

    # Implementation note.
    total_ndt = count_ndt_records(session, project_id)
    accepted = count_ndt_records(session, project_id, result=NDTResult.ACCEPT)
    rejected = (
        session.query(func.count(NDTRecord.id))
        .join(Weld, NDTRecord.weld_id_fk == Weld.id)
        .filter(
            Weld.project_id == project_id,
            NDTRecord.result.in_(NDTResult.FAILED),
        )
        .scalar() or 0
    )
    pending = count_ndt_records(session, project_id, result=NDTResult.PENDING)

    # Implementation note.
    by_method = get_repair_rate_by_method(session, project_id)

    # Implementation note.
    welder_rates = get_welder_repair_rates(session, project_id, min_welds=5)
    worst_welders = welder_rates[:5]
    critical_welders = [w for w in welder_rates if w["risk_level"] == "Critical"]

    # Implementation note.
    pending_welds_count = (
        session.query(func.count(Weld.id))
        .filter(
            Weld.project_id == project_id,
            Weld.id.notin_(session.query(NDTRecord.weld_id_fk)),
            Weld.status.notin_(("Cancelled", "Cut Out")),
        )
        .scalar() or 0
    )

    # Implementation note.
    non_compliant_rt = get_ndt_coverage_by_line(
        session, project_id, ndt_method=NDTMethod.RT, only_non_compliant=True,
    )

    # ── PMI ──
    pmi_total = (
        session.query(func.count(PMITestRecord.id))
        .filter(PMITestRecord.project_id == project_id)
        .scalar() or 0
    )
    pmi_rejected = (
        session.query(func.count(PMITestRecord.id))
        .filter(
            PMITestRecord.project_id == project_id,
            PMITestRecord.result == "Reject",
        )
        .scalar() or 0
    )

    # Implementation note.
    dim_total = (
        session.query(func.count(DimensionalCheckRecord.id))
        .filter(DimensionalCheckRecord.project_id == project_id)
        .scalar() or 0
    )
    dim_accepted = (
        session.query(func.count(DimensionalCheckRecord.id))
        .filter(
            DimensionalCheckRecord.project_id == project_id,
            DimensionalCheckRecord.result == "Accept",
        )
        .scalar() or 0
    )

    # Implementation note.
    leak_total = (
        session.query(func.count(LeakTestRecord.id))
        .filter(LeakTestRecord.project_id == project_id)
        .scalar() or 0
    )
    leaks_found_sum = (
        session.query(func.coalesce(func.sum(LeakTestRecord.leaks_found), 0))
        .filter(LeakTestRecord.project_id == project_id)
        .scalar() or 0
    )

    # Implementation note.
    overdue_requests = len(get_overdue_ndt_requests(session, project_id))

    overall_repair_rate = _pct(rejected, accepted + rejected)

    return {
        "summary": {
            "total_inspections": total_ndt,
            "accepted": accepted,
            "rejected": rejected,
            "pending": pending,
            "overall_repair_rate_pct": overall_repair_rate,
            "acceptance_rate_pct": _pct(accepted, accepted + rejected),
            "health_status": (
                "Critical" if overall_repair_rate >= REPAIR_RATE_CRITICAL_THRESHOLD
                else "Warning" if overall_repair_rate >= REPAIR_RATE_WARNING_THRESHOLD
                else "Good"
            ),
        },
        "by_method": by_method,
        "welder_performance": {
            "total_welders_evaluated": len(welder_rates),
            "worst_performers": worst_welders,
            "critical_count": len(critical_welders),
            "requires_requalification": [w["welder_id"] for w in critical_welders],
        },
        "backlog": {
            "welds_pending_ndt": pending_welds_count,
            "overdue_requests": overdue_requests,
        },
        "coverage": {
            "non_compliant_lines_rt": len(non_compliant_rt),
            "non_compliant_details": non_compliant_rt[:10],
        },
        "pmi": {
            "total_tests": pmi_total,
            "mismatches": pmi_rejected,
            "mismatch_rate_pct": _pct(pmi_rejected, pmi_total),
        },
        "dimensional": {
            "total_checks": dim_total,
            "accepted": dim_accepted,
            "acceptance_rate_pct": _pct(dim_accepted, dim_total),
        },
        "leak_test": {
            "total_tests": leak_total,
            "total_leaks_found": int(leaks_found_sum),
        },
    }