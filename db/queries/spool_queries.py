# -*- coding: utf-8 -*-
"""
db/queries/spool_queries.py – PipeAgent v5.1
===========================================
Enterprise Spool Management & Fabrication Query Layer.

Covers:
  • Spool Lifecycle: CRUD operations, status propagation, and tracking
  • Dynamic Spool Search (Area, ISO, Line list, Pipe Class, Fabrication status)
  • Bulk Imports for Spool Generation from Piping BOMs (PDMS/SP3D exports)
  • Shop Weld integrations & Dimensional clearance checks
  • Dynamic Weight Tonnage Calculations (Total, Fabricated, Installed)
  • Advanced Spool Progress Analytics and Shop Productivity Metrics

Fully compatible with SQLAlchemy 2.0, thread-safe, and highly optimized.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from db.models import Area, DimensionalCheckRecord, Spool, Weld

try:
    from core.exceptions import DatabaseError, ValidationError
except ImportError:
    class DatabaseError(Exception): pass
    class ValidationError(Exception): pass

logger = logging.getLogger(__name__)

__all__ = [
    # Spool CRUD
    "get_spools",
    "get_spool_by_id",
    "get_spool_by_number",
    "count_spools",
    "create_spool",
    "create_spools_bulk",
    "update_spool",
    "delete_spool",
    # Spool Relational Queries
    "get_spool_welds",
    "get_spool_dimensional_checks",
    # Shop Fabrication & Erection Analytics
    "get_spool_tonnage_summary",
    "get_spool_dashboard_stats",
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
#  1. Spool CRUD Operations
# ══════════════════════════════════════════════

def get_spools(
    session: Session,
    project_id: int,
    *,
    area_id: Optional[int] = None,
    line_number: Optional[str] = None,
    iso_number: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: Optional[int] = 100,
) -> List[Spool]:
    """
    دریافت لیست اسپول‌های پروژه با اعمال فیلترهای پیشرفته و صفحه‌بندی پایگاه داده.
    """
    _validate_project_id(project_id)
    q = session.query(Spool).filter(Spool.project_id == project_id)

    if area_id is not None:
        q = q.filter(Spool.area_id == area_id)
    if line_number:
        q = q.filter(Spool.line_number.ilike(f"%{line_number}%"))
    if iso_number:
        q = q.filter(Spool.iso_number.ilike(f"%{iso_number}%"))
    if status:
        q = q.filter(Spool.status == status)
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                Spool.spool_number.ilike(pattern),
                Spool.pipe_class.ilike(pattern),
            )
        )

    # Implementation note.
    q = q.options(joinedload(Spool.area))
    q = q.order_by(Spool.spool_number.asc())

    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_spool_by_id(session: Session, spool_id: int) -> Optional[Spool]:
    """دریافت اسپول بر اساس شناسه اصلی (SQLAlchemy 2.0)."""
    return session.get(Spool, spool_id)


def get_spool_by_number(session: Session, project_id: int, spool_number: str) -> Optional[Spool]:
    """دریافت اطلاعات اسپول بر اساس نام تگ یکتا در پروژه."""
    _validate_project_id(project_id)
    return (
        session.query(Spool)
        .filter(Spool.project_id == project_id, Spool.spool_number == spool_number)
        .first()
    )


def count_spools(session: Session, project_id: int, *, status: Optional[str] = None) -> int:
    """شمارش تعداد کل اسپول‌ها."""
    _validate_project_id(project_id)
    q = session.query(func.count(Spool.id)).filter(Spool.project_id == project_id)
    if status:
        q = q.filter(Spool.status == status)
    return q.scalar() or 0


def create_spool(session: Session, **kwargs: Any) -> Spool:
    """
    ثبت شناسنامه جدید برای اسپول.
    """
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a Spool.")
    _validate_project_id(kwargs["project_id"])

    spool_no = kwargs.get("spool_number")
    if not spool_no:
        raise ValidationError("spool_number is required to create a Spool.")

    # Implementation note.
    existing = get_spool_by_number(session, kwargs["project_id"], spool_no)
    if existing:
        raise ValidationError(f"Spool with tag '{spool_no}' already exists in this project.")

    spool = Spool(**kwargs)
    session.add(spool)
    session.flush()
    logger.info("Created Spool ID=%d Tag=%s Line=%s", spool.id, spool.spool_number, spool.line_number)
    return spool


def create_spools_bulk(
    session: Session,
    spools_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 150,
) -> int:
    """
    ثبت دسته‌ای اسناد اسپول‌ها (سرعت اجرای بسیار بالا در وارد کردن اطلاعات تناژ کل نقشه).
    """
    if not spools_data:
        return 0

    spools = [Spool(**data) for data in spools_data]
    total = len(spools)

    for i in range(0, total, batch_size):
        batch = spools[i : i + batch_size]
        session.add_all(batch)
        session.flush()

    logger.info("Bulk imported %d Spool records from BOM.", total)
    return total


def update_spool(session: Session, spool_id: int, **kwargs: Any) -> Optional[Spool]:
    """به‌روزرسانی مشخصات یا وضعیت اسپول در کارگاه یا سایت."""
    spool = session.get(Spool, spool_id)
    if spool is None:
        return None

    changed = _safe_update(spool, kwargs)
    if changed:
        session.flush()
        logger.info("Updated Spool ID=%d (%d fields modified).", spool_id, changed)
    return spool


def delete_spool(session: Session, spool_id: int) -> bool:
    """حذف فیزیکی مدرک اسپول به همراه سرجوش‌های پیوست‌شده (Cascade)."""
    spool = session.get(Spool, spool_id)
    if spool is None:
        return False
    session.delete(spool)
    session.flush()
    logger.info("Deleted Spool ID=%d.", spool_id)
    return True


# ══════════════════════════════════════════════
#  2. Spool Relational Queries
# ══════════════════════════════════════════════

def get_spool_welds(session: Session, spool_id: int) -> List[Weld]:
    """دریافت کلیه سرجوش‌های کارگاهی (Shop Welds) متعلق به این اسپول."""
    spool = session.get(Spool, spool_id)
    if spool is None:
        return []
    return spool.shop_welds


def get_spool_dimensional_checks(session: Session, spool_id: int) -> List[DimensionalCheckRecord]:
    """دریافت تاریخچه نتایج بازرسی‌های کنترل ابعادی این اسپول."""
    spool = session.get(Spool, spool_id)
    if spool is None:
        return []
    return spool.dimensional_checks


# ══════════════════════════════════════════════
#  3. Shop Fabrication & Dynamic Progress
# ══════════════════════════════════════════════

def get_spool_tonnage_summary(session: Session, project_id: int) -> Dict[str, float]:
    """
    محاسبه‌ی خلاصه وضعیت وزنی و تناژ کل پروژه (فونداسیون پیشرفت فیزیکی کارگاه).
    
    Returns:
        {
            "total_tonnage_tons": 450.5,  # Implementation note.
            "fabricated_tonnage_tons": 250.0,  # Implementation note.
            "installed_tonnage_tons": 120.5,  # Implementation note.
        }
    """
    _validate_project_id(project_id)

    # Implementation note.
    res = (
        session.query(
            func.sum(Spool.weight_kg).label("total"),
            func.sum(case((Spool.status.in_(["Released", "Erected", "Installed"]), Spool.weight_kg), else_=0)).label("fabricated"),
            func.sum(case((Spool.status == "Installed", Spool.weight_kg), else_=0)).label("installed"),
        )
        .filter(Spool.project_id == project_id)
        .first()
    )

    total_kg = float(res.total or 0.0)
    fab_kg = float(res.fabricated or 0.0)
    inst_kg = float(res.installed or 0.0)

    return {
        "total_tonnage_tons": round(total_kg / 1000.0, 2),
        "fabricated_tonnage_tons": round(fab_kg / 1000.0, 2),
        "installed_tonnage_tons": round(inst_kg / 1000.0, 2),
    }


def get_spool_dashboard_stats(session: Session, project_id: int) -> Dict[str, Any]:
    """
    استخراج آمارهای تخصصی ساخت و نصب اسپول‌ها جهت نمایش در چارت‌های داشبورد کارگاه.
    """
    _validate_project_id(project_id)

    total_spools = count_spools(session, project_id)
    
    # Implementation note.
    prefab = count_spools(session, project_id, status="Prefabrication")
    released = count_spools(session, project_id, status="Released")
    installed = count_spools(session, project_id, status="Installed")

    # Implementation note.
    tonnage = get_spool_tonnage_summary(session, project_id)

    return {
        "spool_count": {
            "total": total_spools,
            "in_prefabrication": prefab,
            "released_completed": released,
            "installed_site": installed,
            "fabrication_progress_pct": _pct(released + installed, total_spools),
            "erection_progress_pct": _pct(installed, total_spools),
        },
        "tonnage_progress": {
            "total_weight_tons": tonnage["total_tonnage_tons"],
            "fabricated_weight_tons": tonnage["fabricated_tonnage_tons"],
            "installed_weight_tons": tonnage["installed_tonnage_tons"],
            "weight_progress_pct": _pct(tonnage["fabricated_tonnage_tons"], tonnage["total_tonnage_tons"]),
        }
    }
