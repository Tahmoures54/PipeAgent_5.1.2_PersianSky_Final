# -*- coding: utf-8 -*-
"""
db/queries/test_package_queries.py – PipeAgent v5.1
=====================================================
Enterprise Test Package (Hydrotest/Pneumatic) Query & Workflow Layer.

Covers:
  • Test Package Lifecycle: CRUD, dynamic filtering, and search
  • Pre-Test QA/QC Safety Gates (NDT clearance verification & Category A punch audits)
  • Many-to-Many Relationship management: Welds ↔ Test Packages
  • Punch Counter Auto-Synchronization (A, B, C categories)
  • Bulk Imports for Test Package Scheduling
  • Dynamic status transitions with validation
  • Comprehensive Hydrotest Progress & Quality Analytics

Fully compatible with SQLAlchemy 2.0, thread-safe, and highly optimized.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from db.models import (
    PunchItem,
    ReinstatementItem,
    TestPackage,
    TestPackageWeld,
    Weld,
)

# Implementation note.
try:
    from core.exceptions import DatabaseError, ValidationError
except ImportError:
    class DatabaseError(Exception): pass
    class ValidationError(Exception): pass

logger = logging.getLogger(__name__)


class TestPackageStatus:
    PLANNED = "Planned"
    RELEASED = "Ready for Test"  # Implementation note.
    TESTED = "Tested"            # Implementation note.
    REINSTATED = "Reinstated"    # Implementation note.
    APPROVED = "Approved"        # Implementation note.
    ALL = (PLANNED, RELEASED, TESTED, REINSTATED, APPROVED)


__all__ = [
    "TestPackageStatus",
    # Test Package CRUD
    "get_test_packages",
    "get_test_package_by_id",
    "get_test_package_by_number",
    "count_test_packages",
    "create_test_package",
    "create_test_packages_bulk",
    "update_test_package",
    "delete_test_package",
    # Many-to-Many Welds Management
    "add_weld_to_test_package",
    "remove_weld_from_test_package",
    "get_test_package_welds",
    # Advanced Workflow Gates & Counters Sync
    "can_release_for_testing",
    "sync_test_package_punch_counters",
    "advance_test_package_status",
    # Dashboard stats
    "get_test_package_dashboard_stats",
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
#  1. Test Package CRUD Operations
# ══════════════════════════════════════════════

def get_test_packages(
    session: Session,
    project_id: int,
    *,
    area_id: Optional[int] = None,
    status: Optional[str] = None,
    test_medium: Optional[str] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: Optional[int] = 100,
) -> List[TestPackage]:
    """دریافت پکیج‌های تست با فیلترهای پیشرفته و صفحه‌بندی پایگاه داده."""
    _validate_project_id(project_id)
    q = session.query(TestPackage).filter(TestPackage.project_id == project_id)

    if area_id is not None:
        q = q.filter(TestPackage.area_id == area_id)
    if status:
        q = q.filter(TestPackage.status == status)
    if test_medium:
        q = q.filter(TestPackage.test_medium == test_medium)
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                TestPackage.package_number.ilike(pattern),
                TestPackage.description.ilike(pattern),
                TestPackage.line_numbers.ilike(pattern),
            )
        )

    # Implementation note.
    q = q.options(joinedload(TestPackage.welds))
    q = q.order_by(TestPackage.package_number.asc())

    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_test_package_by_id(session: Session, tp_id: int) -> Optional[TestPackage]:
    """دریافت پرونده پکیج تست بر اساس شناسه اصلی."""
    return session.query(TestPackage).options(joinedload(TestPackage.welds)).filter(TestPackage.id == tp_id).first()


def get_test_package_by_number(session: Session, project_id: int, package_number: str) -> Optional[TestPackage]:
    """دریافت پرونده پکیج تست بر اساس شماره منحصر‌به‌فرد پکیج (Package No)."""
    _validate_project_id(project_id)
    return (
        session.query(TestPackage)
        .options(joinedload(TestPackage.welds))
        .filter(TestPackage.project_id == project_id, TestPackage.package_number == package_number)
        .first()
    )


def count_test_packages(session: Session, project_id: int, *, status: Optional[str] = None) -> int:
    """شمارش پکیج‌های تست بر اساس وضعیت‌های کاری."""
    _validate_project_id(project_id)
    q = session.query(func.count(TestPackage.id)).filter(TestPackage.project_id == project_id)
    if status:
        q = q.filter(TestPackage.status == status)
    return q.scalar() or 0


def create_test_package(session: Session, **kwargs: Any) -> TestPackage:
    """ایجاد پرونده پکیج تست جدید."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a TestPackage.")
    _validate_project_id(kwargs["project_id"])

    tp_no = kwargs.get("package_number")
    if not tp_no:
        raise ValidationError("package_number is required to create a TestPackage.")

    # Implementation note.
    existing = get_test_package_by_number(session, kwargs["project_id"], tp_no)
    if existing:
        raise ValidationError(f"Test Package with number '{tp_no}' already exists in this project.")

    tp = TestPackage(**kwargs)
    session.add(tp)
    session.flush()
    logger.info("Created TestPackage ID=%d No=%s", tp.id, tp.package_number)
    return tp


def create_test_packages_bulk(
    session: Session,
    packages_data: Sequence[Dict[str, Any]],
    *,
    batch_size: int = 100,
) -> int:
    """ثبت گروهی برنامه‌ریزی‌های پکیج‌های تست پروژه (مثلا در فاز آغازین پیش‌راه‌اندازی)."""
    if not packages_data:
        return 0

    packages = [TestPackage(**data) for data in packages_data]
    total = len(packages)

    for i in range(0, total, batch_size):
        batch = packages[i : i + batch_size]
        session.add_all(batch)
        session.flush()

    logger.info("Bulk scheduled %d TestPackages.", total)
    return total


def update_test_package(session: Session, tp_id: int, **kwargs: Any) -> Optional[TestPackage]:
    """به‌روزرسانی فیلدهای مهندسی پکیج تست."""
    tp = session.get(TestPackage, tp_id)
    if tp is None:
        return None

    changed = _safe_update(tp, kwargs)
    if changed:
        session.flush()
        logger.info("Updated TestPackage ID=%d (%d fields modified).", tp_id, changed)
    return tp


def delete_test_package(session: Session, tp_id: int) -> bool:
    """حذف پکیج تست (روابط چندبه‌چند جوش‌ها نیز اتوماتیک گسسته می‌شوند)."""
    tp = session.get(TestPackage, tp_id)
    if tp is None:
        return False
    session.delete(tp)
    session.flush()
    logger.info("Deleted TestPackage ID=%d.", tp_id)
    return True


# ══════════════════════════════════════════════
#  2. Many-to-Many Welds ↔ Test Package Management
# ══════════════════════════════════════════════

def add_weld_to_test_package(session: Session, tp_id: int, weld_id: int) -> bool:
    """پیوست کردن یک سرجوش فیزیکی به پکیج تست فشار."""
    tp = session.get(TestPackage, tp_id)
    weld = session.get(Weld, weld_id)

    if not tp or not weld:
        logger.warning("TestPackage ID=%s or Weld ID=%s not found.", tp_id, weld_id)
        return False

    # Implementation note.
    link_exists = (
        session.query(TestPackageWeld)
        .filter(TestPackageWeld.test_package_id == tp_id, TestPackageWeld.weld_id == weld_id)
        .first()
    )
    if link_exists:
        return True

    link = TestPackageWeld(test_package_id=tp_id, weld_id=weld_id)
    session.add(link)
    session.flush()
    logger.info("Associated Weld ID=%d to TestPackage ID=%d", weld_id, tp_id)
    return True


def remove_weld_from_test_package(session: Session, tp_id: int, weld_id: int) -> bool:
    """جداسازی سرجوش از پکیج تست فشار."""
    link = (
        session.query(TestPackageWeld)
        .filter(TestPackageWeld.test_package_id == tp_id, TestPackageWeld.weld_id == weld_id)
        .first()
    )
    if link is None:
        return False

    session.delete(link)
    session.flush()
    logger.info("Removed association between Weld ID=%d and TestPackage ID=%d", weld_id, tp_id)
    return True


def get_test_package_welds(session: Session, tp_id: int) -> List[Weld]:
    """دریافت لیست کلیه سرجوش‌های گروه‌بندی شده در پکیج تست."""
    tp = session.get(TestPackage, tp_id)
    if tp is None:
        return []
    return tp.welds


# ══════════════════════════════════════════════
#  3. Advanced QC Gateways & Workflows
# ══════════════════════════════════════════════

def can_release_for_testing(session: Session, tp_id: int) -> Tuple[bool, List[str]]:
    """
    بررسی هوشمند پیش‌نیازهای ایمنی و کیفی جهت صدور مجوز آغاز هیدروتست (Ready for Test).
    
    این گیت بازرسی تایید می‌کند که:
      ۱. ۱۰۰٪ سرجوش‌های این پکیج توسط QC بازرسی و تایید نهایی NDT (NDT Accepted) شده باشند.
      ۲. هیچ پانچ باز بحرانی از دسته 'Category A' ( پانچ مسدود کننده هیدروتست) روی پکیج وجود نداشته باشد.
    
    Returns:
        (True/False, لیست علل عدم پذیرش)
    """
    tp = session.get(TestPackage, tp_id)
    if tp is None:
        return False, ["Test package not found."]

    reasons = []

    # Implementation note.
    welds = get_test_package_welds(session, tp_id)
    if not welds:
        reasons.append("Test package contains zero registered welds.")
    else:
        pending_welds = [w.weld_id for w in welds if w.status != "NDT Accepted"]
        if pending_welds:
            reasons.append(f"Contains {len(pending_welds)} welds not cleared by NDT (e.g., {pending_welds[:3]}).")

    # Implementation note.
    open_punch_a = (
        session.query(func.count(PunchItem.id))
        .filter(
            PunchItem.test_package_id == tp_id,
            PunchItem.category == "A",
            PunchItem.is_cleared == False,  # noqa: E712
        )
        .scalar() or 0
    )
    if open_punch_a > 0:
        reasons.append(f"Contains {open_punch_a} open Category A punch items (Blocking Test).")

    return (len(reasons) == 0, reasons)


def sync_test_package_punch_counters(session: Session, tp_id: int) -> None:
    """
    همگام‌سازی و آپدیت خودکار فیلدهای شمارنده پانچ تجمعی پکیج تست از روی جدول مرجع پانچ‌ها.
    """
    tp = session.get(TestPackage, tp_id)
    if tp is None:
        return

    # Implementation note.
    counts = (
        session.query(PunchItem.category, func.count(PunchItem.id))
        .filter(PunchItem.test_package_id == tp_id, PunchItem.is_cleared == False)  # noqa: E712
        .group_by(PunchItem.category)
        .all()
    )

    counts_map = {cat: count for cat, count in counts}

    tp.punch_a_count = counts_map.get("A", 0)
    tp.punch_b_count = counts_map.get("B", 0)
    tp.punch_c_count = counts_map.get("C", 0)

    session.flush()
    logger.debug("Synchronized punch counters for TestPackage ID=%d (A: %d, B: %d, C: %d)",
                 tp_id, tp.punch_a_count, tp.punch_b_count, tp.punch_c_count)


def advance_test_package_status(
    session: Session,
    tp_id: int,
    new_status: str,
    *,
    operator_name: str,
    override_qc_gate: bool = False,
) -> Optional[TestPackage]:
    """
    مدیریت حرکت در زنجیره‌ی گام‌های تایید پکیج تست (Planned -> Ready -> Tested -> Reinstated -> Approved).
    
    در زمان آزادسازی به فاز تست (Ready for Test)، گیت بازرسی ایمنی به صورت اتوماتیک اجرا می‌شود.
    """
    tp = session.get(TestPackage, tp_id)
    if tp is None:
        return None

    if new_status not in TestPackageStatus.ALL:
        raise ValidationError(f"Invalid status '{new_status}'. Allowed: {TestPackageStatus.ALL}")

    # Implementation note.
    if new_status == TestPackageStatus.RELEASED and not override_qc_gate:
        passed, reasons = can_release_for_testing(session, tp_id)
        if not passed:
            raise ValidationError(
                f"Release rejected. QC Gate failed: {'; '.join(reasons)}"
            )

    tp.status = new_status

    # Implementation note.
    if new_status == TestPackageStatus.TESTED:
        tp.test_date = date.today()
        tp.tested_by = operator_name
    elif new_status == TestPackageStatus.APPROVED:
        tp.witnessed_by = operator_name

    session.flush()
    logger.info("TestPackage ID=%d advanced to status '%s' by %s.", tp_id, new_status, operator_name)
    return tp


# ══════════════════════════════════════════════
#  4. Comprehensive Hydrotest Progress Stats
# ══════════════════════════════════════════════

def get_test_package_dashboard_stats(session: Session, project_id: int) -> Dict[str, Any]:
    """
    استخراج و مانیتورینگ آمار تجمعی و دقیق پیشرفت هیدروتست پکیج‌های پروژه جهت نمایش در داشبورد کارفرما.
    """
    _validate_project_id(project_id)

    total_tp = count_test_packages(session, project_id)
    
    # Implementation note.
    planned = count_test_packages(session, project_id, status=TestPackageStatus.PLANNED)
    released = count_test_packages(session, project_id, status=TestPackageStatus.RELEASED)
    tested = count_test_packages(session, project_id, status=TestPackageStatus.TESTED)
    reinstated = count_test_packages(session, project_id, status=TestPackageStatus.REINSTATED)
    approved = count_test_packages(session, project_id, status=TestPackageStatus.APPROVED)

    # Implementation note.
    total_open_punch_a = (
        session.query(func.count(PunchItem.id))
        .filter(
            PunchItem.project_id == project_id,
            PunchItem.category == "A",
            PunchItem.is_cleared == False,  # noqa: E712
        )
        .scalar() or 0
    )

    # Implementation note.
    total_reinstated_items = (
        session.query(func.count(ReinstatementItem.id))
        .filter(ReinstatementItem.project_id == project_id)
        .scalar() or 0
    )
    completed_reinstatements = (
        session.query(func.count(ReinstatementItem.id))
        .filter(ReinstatementItem.project_id == project_id, ReinstatementItem.status == "Completed")
        .scalar() or 0
    )

    tested_or_more = tested + reinstated + approved

    return {
        "packages": {
            "total_packages": total_tp,
            "planned": planned,
            "ready_for_test": released,
            "hydro_tested": tested,
            "reinstated": reinstated,
            "approved_closed": approved,
            "hydro_progress_pct": _pct(tested_or_more, total_tp),
            "approval_progress_pct": _pct(approved, total_tp),
        },
        "blockers": {
            "open_category_a_punch_list": total_open_punch_a,
            "pending_reinstatement_items": total_reinstated_items - completed_reinstatements,
            "reinstatement_progress_pct": _pct(completed_reinstatements, total_reinstated_items),
        }
    }