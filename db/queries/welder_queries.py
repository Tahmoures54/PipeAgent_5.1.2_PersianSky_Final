# -*- coding: utf-8 -*-
"""
db/queries/welder_queries.py – PipeAgent v5.1
==============================================
Enterprise Welder Qualifications, Performance, and WPQ Auditing Query Layer.

Referenced Standards:
  • ASME Section IX - Welding and Brazing Qualifications
  • AWS D1.1        - Structural Welding Code - Steel
  • ASME B31.3      - Process Piping (Welder Auditing)

Covers:
  • Welder Performance Qualification (WPQ) Registry
  • Dynamic Expiration Alerts & Automated Safety Deactivations
  • Workload Audits (connecting DB primary keys and physical Stencils)
  • Welder-to-WPS Compatibility Validation (ASME Sec. IX compliance check)
  • Real-time Defect-Rate / Repair Rate analytics per welder
  • Bulk Imports for Welder mobilizations
  • QC Dashboard Performance Indicators

Fully updated to SQLAlchemy 2.0, robust, secure, and typed.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from db.models import NDTRecord, Weld, Welder, WPS_PQR

# Implementation note.
try:
    from core.exceptions import DatabaseError, ValidationError
except ImportError:
    class DatabaseError(Exception): pass
    class ValidationError(Exception): pass

logger = logging.getLogger(__name__)

__all__ = [
    # CRUD
    "get_welders",
    "get_active_welders",
    "get_welder_by_id",
    "get_welder_by_stencil",
    "get_expiring_welders",
    "create_welder",
    "create_welders_bulk",
    "update_welder",
    "deactivate_welder",
    "delete_welder",
    # Audit & Compliance (WPQ)
    "get_welder_workload",
    "get_welder_detailed_kpis",
    "is_welder_qualified_for_wps",
    # Dashboard stats
    "get_welder_monitoring_stats",
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
#  1. Welder CRUD Operations
# ══════════════════════════════════════════════

def get_welders(
    session: Session,
    project_id: int,
    *,
    is_active: Optional[bool] = None,
    welding_process: Optional[str] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: Optional[int] = 100,
) -> List[Welder]:
    """دریافت لیست جامع جوشکاران با اعمال فیلترها و صفحه‌بندی پایگاه داده."""
    _validate_project_id(project_id)
    q = session.query(Welder).filter(Welder.project_id == project_id)

    if is_active is not None:
        q = q.filter(Welder.is_active == is_active)
    if welding_process:
        q = q.filter(Welder.welding_processes.ilike(f"%{welding_process}%"))
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                Welder.stencil_no.ilike(pattern),
                Welder.full_name.ilike(pattern),
                Welder.certificate_no.ilike(pattern),
            )
        )

    q = q.order_by(Welder.stencil_no.asc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_active_welders(session: Session, project_id: int) -> List[Welder]:
    """دریافت سریع جوشکاران فعال پروژه بر اساس استنسیل‌ها (Welder Stencil)."""
    _validate_project_id(project_id)
    return (
        session.query(Welder)
        .filter(Welder.project_id == project_id, Welder.is_active == True)  # noqa: E712
        .order_by(Welder.stencil_no.asc())
        .all()
    )


def get_welder_by_id(session: Session, welder_id: int) -> Optional[Welder]:
    """دریافت اطلاعات تایید صلاحیت جوشکار بر اساس شناسه اصلی (SQLAlchemy 2.0)."""
    return session.get(Welder, welder_id)


def get_welder_by_stencil(session: Session, project_id: int, stencil: str) -> Optional[Welder]:
    """دریافت پرونده جوشکار بر اساس شماره استنسیل یکتا در پروژه (مثلاً W-105)."""
    _validate_project_id(project_id)
    return (
        session.query(Welder)
        .filter(Welder.project_id == project_id, Welder.stencil_no == stencil)
        .first()
    )


def get_expiring_welders(session: Session, project_id: int, *, days: int = 30) -> List[Welder]:
    """
    شناسایی سریع جوشکارانی که گواهینامه صلاحیت آن‌ها در شرف انقضا است.
    
    این گزارش یک هشدار پیشگیرانه کیفی (Preemptive Alert) است تا از توقف عملیات جوشکاری ممانعت شود.
    """
    _validate_project_id(project_id)
    threshold = date.today() + timedelta(days=days)
    return (
        session.query(Welder)
        .filter(
            Welder.project_id == project_id,
            Welder.is_active == True,  # noqa: E712
            Welder.expiry_date <= threshold,
            Welder.expiry_date >= date.today() # Implementation note.
        )
        .order_by(Welder.expiry_date.asc())
        .all()
    )


def create_welder(session: Session, **kwargs: Any) -> Welder:
    """ثبت صلاحیت و صدور مجوز جوشکار جدید در پروژه (WPQ Record)."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a Welder record.")
    _validate_project_id(kwargs["project_id"])

    stencil = kwargs.get("stencil_no")
    if not stencil:
        raise ValidationError("stencil_no (Stencil Number) is required to register a welder.")

    # Implementation note.
    existing = get_welder_by_stencil(session, kwargs["project_id"], stencil)
    if existing:
        raise ValidationError(f"Welder with stencil No '{stencil}' already registered in this project.")

    welder = Welder(**kwargs)
    session.add(welder)
    session.flush()
    logger.info("Registered Welder ID=%d Stencil=%s Name='%s'", welder.id, welder.stencil_no, welder.full_name)
    return welder


def create_welders_bulk(
    session: Session,
    welders_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 100,
) -> int:
    """ثبت دسته‌ای و سریع اطلاعات گواهینامه‌های جوشکاران در زمان تجهیز کارگاه."""
    if not welders_data:
        return 0

    welders = [Welder(**data) for data in welders_data]
    total = len(welders)

    for i in range(0, total, batch_size):
        batch = welders[i : i + batch_size]
        session.add_all(batch)
        session.flush()

    logger.info("Bulk imported %d welders WPQ records.", total)
    return total


def update_welder(session: Session, welder_id: int, **kwargs: Any) -> Optional[Welder]:
    """به‌روزرسانی اطلاعات صلاحیت یا تمدید گواهینامه‌های تاییدیه جوشکار."""
    w = session.get(Welder, welder_id)
    if w is None:
        return None

    changed = _safe_update(w, kwargs)
    if changed:
        session.flush()
        logger.info("Updated Welder ID=%d Stencil=%s (%d fields modified).", welder_id, w.stencil_no, changed)
    return w


def deactivate_welder(session: Session, welder_id: int) -> bool:
    """تعلیق صلاحیت جوشکار (به دلیل انقضا، عملکرد ضعیف یا اتمام کاربری)."""
    w = session.get(Welder, welder_id)
    if w is None:
        return False

    w.is_active = False
    session.flush()
    logger.warning("Deactivated Welder ID=%d Stencil=%s from project.", welder_id, w.stencil_no)
    return True


def delete_welder(session: Session, welder_id: int) -> bool:
    """حذف کامل پرونده جوشکار از سیستم."""
    w = session.get(Welder, welder_id)
    if w is None:
        return False
    session.delete(w)
    session.flush()
    logger.info("Deleted Welder ID=%d.", welder_id)
    return True


# ══════════════════════════════════════════════
#  2. Performance Audit & WPQ Compliance Checks
# ══════════════════════════════════════════════

def get_welder_workload(session: Session, project_id: int, stencil_no: str) -> int:
    """
    محاسبه‌ی دقیق تعداد کل درزجوش‌های جوشکاری‌شده توسط استنسیل جوشکار.
    
    رفع باگ: تطبیق فیلدهای متنی استنسیل (به جای شناسه دیتابیس) با جدول سرجوش‌ها.
    """
    _validate_project_id(project_id)
    return (
        session.query(Weld)
        .filter(Weld.project_id == project_id, Weld.welder_id == stencil_no)
        .count()
    )


def get_welder_detailed_kpis(session: Session, project_id: int, stencil_no: str) -> Dict[str, Any]:
    """
    محاسبه‌ی شاخص‌های عملکردی و کیفی جوشکار بر اساس نتایج بازرسی‌های کارگاهی.
    
    این متد تعداد جوش‌ها، نرخ تعمیرات (Repair Rate) و وضعیت پذیرش NDT سرجوش‌ها را محاسبه می‌کند.
    """
    _validate_project_id(project_id)

    # Implementation note.
    total_welds = get_welder_workload(session, project_id, stencil_no)

    # Implementation note.
    ndt_stats = (
        session.query(
            func.count(NDTRecord.id).label("total_inspected"),
            func.sum(case((NDTRecord.result.in_(["Reject", "Repair"]), 1), else_=0)).label("total_rejected"),
            func.sum(case((NDTRecord.result == "Accept", 1), else_=0)).label("total_accepted")
        )
        .join(Weld, NDTRecord.weld_id_fk == Weld.id)
        .filter(Weld.project_id == project_id, Weld.welder_id == stencil_no)
        .first()
    )

    inspected = int(ndt_stats.total_inspected or 0)
    rejected = int(ndt_stats.total_rejected or 0)
    accepted = int(ndt_stats.total_accepted or 0)

    repair_rate = _pct(rejected, inspected)

    return {
        "stencil_no": stencil_no,
        "total_welds_welded": total_welds,
        "total_joints_inspected": inspected,
        "accepted_joints": accepted,
        "rejected_joints": rejected,
        "repair_rate_pct": repair_rate,
        "status": "Excellent" if repair_rate <= 1.5 else "Acceptable" if repair_rate <= 3.0 else "Critical"
    }


def is_welder_qualified_for_wps(session: Session, project_id: int, stencil_no: str, wps_id_str: str) -> bool:
    """
    ممیزی تطابق صلاحیت جوشکار بر اساس الزامات فرآیند جوشکاری (ASME Sec. IX compliance check).
    
    سیستم تایید می‌کند که آیا جوشکار معرفی شده، صلاحیت کار با WPS مورد نظر را بر اساس موارد زیر دارد یا خیر:
      ۱. مطابقت فرآیند جوشکاری (GTAW, SMAW, FCAW, etc.)
      ۲. انقضای زمانی گواهینامه جوشکار
    """
    _validate_project_id(project_id)

    welder = get_welder_by_stencil(session, project_id, stencil_no)
    wps = session.query(WPS_PQR).filter(WPS_PQR.project_id == project_id, WPS_PQR.wps_id == wps_id_str).first()

    if not welder or not wps:
        logger.warning("Audit failed: Welder %s or WPS %s does not exist.", stencil_no, wps_id_str)
        return False

    # Implementation note.
    if not welder.is_active or welder.expiry_date < date.today():
        logger.warning("Audit failed: Welder %s has an expired or suspended certificate.", stencil_no)
        return False

    # Implementation note.
    qualified_processes = [p.strip().upper() for p in (welder.welding_processes or "").split(",")]
    wps_process = (wps.welding_process or "").strip().upper()

    if wps_process not in qualified_processes:
        logger.warning(
            "Audit failed: Welder %s is qualified for %s but WPS %s requires %s.",
            stencil_no, qualified_processes, wps_id_str, wps_process
        )
        return False

    return True


# ══════════════════════════════════════════════
#  3. Dashboard Monitoring KPI Statistics
# ══════════════════════════════════════════════

def get_welder_monitoring_stats(session: Session, project_id: int) -> Dict[str, Any]:
    """
    استخراج و مانیتورینگ وضعیت آماری صلاحیت کل جوشکاران پروژه برای کارفرما.
    
    Returns:
        خلاصه‌ای از تعداد جوشکاران فعال، جوشکاران معلق، رکوردهای بحرانی و موارد در شرف انقضا.
    """
    _validate_project_id(project_id)

    total_welders = session.query(func.count(Welder.id)).filter(Welder.project_id == project_id).scalar() or 0
    active_welders = count_welders = (
        session.query(func.count(Welder.id))
        .filter(Welder.project_id == project_id, Welder.is_active == True)  # noqa: E712
        .scalar() or 0
    )

    # Implementation note.
    expiring_count = len(get_expiring_welders(session, project_id, days=30))

    # Implementation note.
    expired_active_count = (
        session.query(func.count(Welder.id))
        .filter(
            Welder.project_id == project_id,
            Welder.is_active == True,  # noqa: E712
            Welder.expiry_date < date.today()
        )
        .scalar() or 0
    )

    return {
        "compliance": {
            "total_registered_welders": total_welders,
            "active_qualified": active_welders,
            "suspended_or_inactive": total_welders - active_welders,
            "expiring_within_30_days": expiring_count,
            "expired_but_active_alerts": expired_active_count, # Implementation note.
            "compliance_pct": _pct(active_welders - expired_active_count, total_welders) if total_welders else 100.0,
        }
    }