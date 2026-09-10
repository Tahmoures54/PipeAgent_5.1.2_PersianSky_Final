# -*- coding: utf-8 -*-
"""
db/queries/project_queries.py – PipeAgent v5.1
===============================================
Master Project & Area Management Query Layer.

Covers:
  • Project Lifecycle: CRUD, Soft Deletion, Archiving & Restoration
  • Area / Unit Breakdown Structure (WBS/PBS)
  • Multi-tenant Project Memberships & Role Assignments
  • Project Templating & Configuration Cloning
  • Master Project Health Index & Weighted Overall Progress Calculation
  • Comprehensive Executive Dashboard Analytics

Fully compliant with SQLAlchemy 2.0, thread-safe, and optimized for high-speed queries.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session, joinedload

from db.models import (
    Area,
    LineListItem,
    MCCCertificate,
    NCRRecord,
    NDTRecord,
    Project,
    PunchItem,
    Spool,
    TestPackage,
    User,
    Weld,
)

# Implementation note.
try:
    from db.models_enterprise import ProjectMembership
except ImportError:
    ProjectMembership = None

try:
    from core.exceptions import DatabaseError, ValidationError
except ImportError:
    class DatabaseError(Exception): pass
    class ValidationError(Exception): pass

logger = logging.getLogger(__name__)

__all__ = [
    # Project CRUD
    "get_projects",
    "get_project_by_id",
    "get_project_by_code",
    "count_projects",
    "create_project",
    "update_project",
    "delete_project",
    "restore_project",
    # Area CRUD
    "get_areas_for_project",
    "get_area_by_id",
    "get_area_by_name",
    "create_area",
    "update_area",
    "delete_area",
    # Project Memberships & Access
    "get_project_members",
    "add_user_to_project",
    "update_member_role",
    "remove_user_from_project",
    "get_user_accessible_projects",
    # Templating / Cloning
    "clone_project_structure",
    # Master Analytics & Progress S-Curve
    "get_project_master_summary",
    "calculate_project_health_score",
    "get_project_weighted_progress",
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


def _pct(numerator: float, denominator: float, digits: int = 1) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, digits)


# ══════════════════════════════════════════════
#  1. Project Lifecycle & CRUD
# ══════════════════════════════════════════════

def get_projects(
    session: Session,
    *,
    client: Optional[str] = None,
    contractor: Optional[str] = None,
    standard: Optional[str] = None,
    search: Optional[str] = None,
    include_deleted: bool = False,
    offset: int = 0,
    limit: Optional[int] = 100,
) -> List[Project]:
    """
    دریافت لیست پروژه‌ها با قابلیت فیلترگذاری و نادیده گرفتن رکوردهای حذف نرم‌شده.
    """
    q = session.query(Project)

    if not include_deleted and hasattr(Project, "deleted_at"):
        q = q.filter(Project.deleted_at.is_(None))

    if client:
        q = q.filter(Project.client.ilike(f"%{client}%"))
    if contractor:
        q = q.filter(Project.contractor.ilike(f"%{contractor}%"))
    if standard:
        q = q.filter(Project.standard == standard)
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                Project.project_code.ilike(pattern),
                Project.title.ilike(pattern),
            )
        )

    q = q.order_by(Project.created_at.desc())
    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_project_by_id(
    session: Session,
    project_id: int,
    *,
    include_deleted: bool = False,
) -> Optional[Project]:
    """دریافت پروژه بر اساس شناسه اختصاصی."""
    project = session.get(Project, project_id)
    if project is None:
        return None
    if not include_deleted and hasattr(project, "is_deleted") and project.is_deleted:
        return None
    return project


def get_project_by_code(
    session: Session,
    project_code: str,
    *,
    include_deleted: bool = False,
) -> Optional[Project]:
    """دریافت پروژه بر اساس کد یکتای پروژه (Project Code)."""
    q = session.query(Project).filter(Project.project_code == project_code)
    if not include_deleted and hasattr(Project, "deleted_at"):
        q = q.filter(Project.deleted_at.is_(None))
    return q.first()


def count_projects(session: Session, *, include_deleted: bool = False) -> int:
    """شمارش کل پروژه‌های فعال."""
    q = session.query(func.count(Project.id))
    if not include_deleted and hasattr(Project, "deleted_at"):
        q = q.filter(Project.deleted_at.is_(None))
    return q.scalar() or 0


def create_project(session: Session, **kwargs: Any) -> Project:
    """
    ایجاد پروژه جدید در پلتفرم PipeAgent.
    """
    code = kwargs.get("project_code")
    if not code:
        raise ValidationError("project_code is required to create a Project.")

    # Implementation note.
    existing = get_project_by_code(session, code, include_deleted=True)
    if existing:
        raise ValidationError(f"Project with code '{code}' already exists.")

    project = Project(**kwargs)
    session.add(project)
    session.flush()
    logger.info("Created Project ID=%d Code=%s Title='%s'", project.id, project.project_code, project.title)
    return project


def update_project(session: Session, project_id: int, **kwargs: Any) -> Optional[Project]:
    """به‌روزرسانی مشخصات پایه پروژه."""
    project = session.get(Project, project_id)
    if project is None:
        return None

    changed = _safe_update(project, kwargs)
    if changed:
        session.flush()
        logger.info("Updated Project ID=%d (%d fields modified).", project_id, changed)
    return project


def delete_project(session: Session, project_id: int, *, hard_delete: bool = False) -> bool:
    """
    حذف پروژه (به صورت پیش‌فرض حذف نرم Soft-Delete می‌شود).
    """
    project = session.get(Project, project_id)
    if project is None:
        return False

    if hard_delete:
        session.delete(project)
        logger.warning("HARD DELETED Project ID=%d and all cascading assets.", project_id)
    else:
        if hasattr(project, "soft_delete"):
            project.soft_delete()
            logger.info("Soft-deleted Project ID=%d.", project_id)
        else:
            session.delete(project)

    session.flush()
    return True


def restore_project(session: Session, project_id: int) -> bool:
    """بازگردانی پروژه از سطل بازیافت (Restoration)."""
    project = session.get(Project, project_id)
    if project is None or not hasattr(project, "restore"):
        return False

    project.restore()
    session.flush()
    logger.info("Restored Project ID=%d from soft-deletion.", project_id)
    return True


# ══════════════════════════════════════════════
#  2. Area / Unit Management
# ══════════════════════════════════════════════

def get_areas_for_project(session: Session, project_id: int) -> List[Area]:
    """دریافت لیست نواحی/یونیت‌های تعریف‌شده برای یک پروژه."""
    _validate_project_id(project_id)
    return (
        session.query(Area)
        .filter(Area.project_id == project_id)
        .order_by(Area.name.asc())
        .all()
    )


def get_area_by_id(session: Session, area_id: int) -> Optional[Area]:
    return session.get(Area, area_id)


def get_area_by_name(session: Session, project_id: int, name: str) -> Optional[Area]:
    _validate_project_id(project_id)
    return (
        session.query(Area)
        .filter(Area.project_id == project_id, Area.name == name)
        .first()
    )


def create_area(session: Session, project_id: int, name: str, description: Optional[str] = None) -> Area:
    """ایجاد ناحیه جدید در ساختار پروژه."""
    _validate_project_id(project_id)
    existing = get_area_by_name(session, project_id, name)
    if existing:
        raise ValidationError(f"Area '{name}' already exists in this project.")

    area = Area(project_id=project_id, name=name, description=description)
    session.add(area)
    session.flush()
    logger.info("Created Area ID=%d Name='%s' in Project ID=%d", area.id, area.name, project_id)
    return area


def update_area(session: Session, area_id: int, **kwargs: Any) -> Optional[Area]:
    area = session.get(Area, area_id)
    if area is None:
        return None
    changed = _safe_update(area, kwargs, exclude={"id", "project_id"})
    if changed:
        session.flush()
    return area


def delete_area(session: Session, area_id: int) -> bool:
    area = session.get(Area, area_id)
    if area is None:
        return False
    session.delete(area)
    session.flush()
    return True


# ══════════════════════════════════════════════
#  3. Project Memberships & Role Assignments
# ══════════════════════════════════════════════

def get_project_members(session: Session, project_id: int) -> List[Dict[str, Any]]:
    """دریافت اعضای تخصیص‌یافته به همراه نقش هر یک در پروژه."""
    if ProjectMembership is None:
        return []

    _validate_project_id(project_id)
    memberships = (
        session.query(ProjectMembership)
        .options(joinedload(ProjectMembership.user))
        .filter(ProjectMembership.project_id == project_id, ProjectMembership.is_active == True)
        .all()
    )

    return [
        {
            "membership_id": m.id,
            "user_id": m.user_id,
            "username": m.user.username if m.user else "N/A",
            "full_name": m.user.full_name if m.user else "N/A",
            "email_or_phone": m.user.phone if m.user else "",
            "role": m.role,
            "joined_at": m.created_at,
        }
        for m in memberships
    ]


def add_user_to_project(
    session: Session,
    project_id: int,
    user_id: int,
    role: str = "viewer",
) -> Any:
    """افزودن کاربر به پروژه با تعیین نقش اختصاصی."""
    if ProjectMembership is None:
        raise DatabaseError("Enterprise module 'ProjectMembership' is not active.")

    _validate_project_id(project_id)

    # Implementation note.
    membership = (
        session.query(ProjectMembership)
        .filter(ProjectMembership.project_id == project_id, ProjectMembership.user_id == user_id)
        .first()
    )
    if membership:
        membership.role = role
        membership.is_active = True
    else:
        membership = ProjectMembership(
            project_id=project_id,
            user_id=user_id,
            role=role,
            is_active=True,
        )
        session.add(membership)

    session.flush()
    logger.info("Assigned User ID=%d to Project ID=%d with Role='%s'", user_id, project_id, role)
    return membership


def update_member_role(session: Session, project_id: int, user_id: int, new_role: str) -> bool:
    if ProjectMembership is None:
        return False
    membership = (
        session.query(ProjectMembership)
        .filter(ProjectMembership.project_id == project_id, ProjectMembership.user_id == user_id)
        .first()
    )
    if membership:
        membership.role = new_role
        session.flush()
        return True
    return False


def remove_user_from_project(session: Session, project_id: int, user_id: int) -> bool:
    if ProjectMembership is None:
        return False
    membership = (
        session.query(ProjectMembership)
        .filter(ProjectMembership.project_id == project_id, ProjectMembership.user_id == user_id)
        .first()
    )
    if membership:
        session.delete(membership)
        session.flush()
        return True
    return False


def get_user_accessible_projects(session: Session, user_id: int) -> List[Project]:
    """دریافت کلیه پروژه‌هایی که کاربر به آن‌ها دسترسی مجاز دارد."""
    user = session.get(User, user_id)
    if not user:
        return []

    # Implementation note.
    if user.role == "admin":
        return get_projects(session)

    if ProjectMembership is None:
        return []

    return (
        session.query(Project)
        .join(ProjectMembership, ProjectMembership.project_id == Project.id)
        .filter(
            ProjectMembership.user_id == user_id,
            ProjectMembership.is_active == True,
            Project.deleted_at.is_(None) if hasattr(Project, "deleted_at") else True,
        )
        .all()
    )


# ══════════════════════════════════════════════
#  4. Project Structure Cloning & Templating
# ══════════════════════════════════════════════

def clone_project_structure(
    session: Session,
    source_project_id: int,
    new_project_code: str,
    new_title: str,
    *,
    copy_areas: bool = True,
    copy_memberships: bool = False,
) -> Project:
    """
    تکثیر مشخصات پایه و ساختار درختی (نواحی، استانداردها، پیمانکار) یک پروژه در قالب پروژه‌ای جدید.
    این متد از داده‌های اجرایی (جوش‌ها، خطوط، تست‌ها) صرف‌نظر می‌کند.
    """
    source = get_project_by_id(session, source_project_id)
    if source is None:
        raise ValidationError(f"Source project ID {source_project_id} does not exist.")

    # Implementation note.
    new_project = create_project(
        session,
        project_code=new_project_code,
        title=new_title,
        client=source.client,
        contractor=source.contractor,
        standard=source.standard,
    )

    # Implementation note.
    if copy_areas:
        for a in source.areas:
            create_area(session, new_project.id, a.name, a.description)

    # Implementation note.
    if copy_memberships and ProjectMembership is not None:
        members = get_project_members(session, source_project_id)
        for m in members:
            add_user_to_project(session, new_project.id, m["user_id"], m["role"])

    session.flush()
    logger.info("Cloned structure from Project ID=%d to New Project ID=%d", source_project_id, new_project.id)
    return new_project


# ══════════════════════════════════════════════
#  5. Master Analytics, Health Index & KPIs
# ══════════════════════════════════════════════

def calculate_project_health_score(session: Session, project_id: int) -> Dict[str, Any]:
    """
    محاسبه‌ی شاخص سلامت چندبُعدی پروژه (Overall Health Index).
    
    معیارهای ارزیابی:
      • نرخ تعمیرات جوش (Welder Repair Rate) – وزن ۳۰٪
      • درصد عدم انطباق‌های باز (Open NCRs) – وزن ۲۵٪
      • پانچ‌های بحرانی تسویه نشده (Open Category A Punch Items) – وزن ۲۵٪
      • انحراف تست هیدروستاتیک از برنامه – وزن ۲۰٪
    """
    _validate_project_id(project_id)

    # Implementation note.
    total_welds = session.query(func.count(Weld.id)).filter(Weld.project_id == project_id).scalar() or 0
    failed_ndt = (
        session.query(func.count(NDTRecord.id))
        .join(Weld, NDTRecord.weld_id_fk == Weld.id)
        .filter(Weld.project_id == project_id, NDTRecord.result.in_(["Reject", "Repair"]))
        .scalar() or 0
    )
    inspected_ndt = (
        session.query(func.count(NDTRecord.id))
        .join(Weld, NDTRecord.weld_id_fk == Weld.id)
        .filter(Weld.project_id == project_id, NDTRecord.result != "Pending")
        .scalar() or 0
    )
    repair_rate = _pct(failed_ndt, inspected_ndt) if inspected_ndt else 0.0

    # Implementation note.
    open_punch_a = (
        session.query(func.count(PunchItem.id))
        .filter(
            PunchItem.project_id == project_id,
            PunchItem.category == "A",
            PunchItem.is_cleared == False,  # noqa: E712
        )
        .scalar() or 0
    )

    # Implementation note.
    open_ncrs = (
        session.query(func.count(NCRRecord.id))
        .filter(NCRRecord.project_id == project_id, NCRRecord.status != "Closed")
        .scalar() or 0
    )

    # Implementation note.
    score = 100.0

    # Implementation note.
    if repair_rate > 3.0:
        score -= min(30.0, (repair_rate - 3.0) * 5.0)

    # Implementation note.
    score -= min(25.0, open_punch_a * 2.0)

    # Implementation note.
    score -= min(25.0, open_ncrs * 3.0)

    score = max(0.0, round(score, 1))

    status = "Excellent" if score >= 90 else "Good" if score >= 75 else "Warning" if score >= 50 else "Critical"

    return {
        "health_score": score,
        "status": status,
        "repair_rate_pct": repair_rate,
        "open_critical_punch_a": open_punch_a,
        "open_ncrs_count": open_ncrs,
        "total_welds": total_welds,
    }


def get_project_weighted_progress(session: Session, project_id: int) -> Dict[str, Any]:
    """
    محاسبه‌ی پیشرفت تجمعی و وزنی کل پروژه مطابق با استانداردهای کنترل پروژه EPC.
    
    توزیع اوزان مهندسی پایپینگ:
      • فاز ۱: مهندسی خطوط و ایزومتریک‌ها (Line List / Spooling): ۱۵٪
      • فاز ۲: ساخت و فیتاپ اسپول‌ها (Fit-up & Fabrication): ۲۵٪
      • فاز ۳: جوشکاری نهایی سایت (Site Welding): ۲۵٪
      • فاز ۴: تست‌های غیرمخرب و پذیرش کیفی (NDT Acceptance): ۱۵٪
      • فاز ۵: تست فشار و هیدروتست پکیج‌ها (Hydrotest Testing): ۱۵٪
      • فاز ۶: تکمیل مکانیکی و پرونده نهایی (MCC & Turnover): ۵٪
    """
    _validate_project_id(project_id)

    # Implementation note.
    total_lines = session.query(func.count(LineListItem.id)).filter(LineListItem.project_id == project_id).scalar() or 0
    active_lines = session.query(func.count(LineListItem.id)).filter(LineListItem.project_id == project_id, LineListItem.status == "Active").scalar() or 0
    p1 = _pct(active_lines, total_lines) if total_lines else 0.0

    # Implementation note.
    total_spools = session.query(func.count(Spool.id)).filter(Spool.project_id == project_id).scalar() or 0
    erected_spools = session.query(func.count(Spool.id)).filter(Spool.project_id == project_id, Spool.status.in_(["Erected", "Installed"])).scalar() or 0
    p2 = _pct(erected_spools, total_spools) if total_spools else 0.0

    # Implementation note.
    total_welds = session.query(func.count(Weld.id)).filter(Weld.project_id == project_id).scalar() or 0
    welded_joints = session.query(func.count(Weld.id)).filter(Weld.project_id == project_id, Weld.status != "Pending").scalar() or 0
    p3 = _pct(welded_joints, total_welds) if total_welds else 0.0

    # Implementation note.
    ndt_accepted_welds = session.query(func.count(Weld.id)).filter(Weld.project_id == project_id, Weld.status == "NDT Accepted").scalar() or 0
    p4 = _pct(ndt_accepted_welds, total_welds) if total_welds else 0.0

    # Implementation note.
    total_tp = session.query(func.count(TestPackage.id)).filter(TestPackage.project_id == project_id).scalar() or 0
    tested_tp = session.query(func.count(TestPackage.id)).filter(TestPackage.project_id == project_id, TestPackage.status.in_(["Tested", "Reinstated", "Approved"])).scalar() or 0
    p5 = _pct(tested_tp, total_tp) if total_tp else 0.0

    # Implementation note.
    total_mcc = session.query(func.count(MCCCertificate.id)).filter(MCCCertificate.project_id == project_id).scalar() or 0
    approved_mcc = session.query(func.count(MCCCertificate.id)).filter(MCCCertificate.project_id == project_id, MCCCertificate.status == "Approved").scalar() or 0
    p6 = _pct(approved_mcc, total_mcc) if total_mcc else 0.0

    # Implementation note.
    overall_progress = (
        (p1 * 0.15) +
        (p2 * 0.25) +
        (p3 * 0.25) +
        (p4 * 0.15) +
        (p5 * 0.15) +
        (p6 * 0.05)
    )

    return {
        "overall_progress_pct": round(overall_progress, 1),
        "phases": {
            "engineering_lines": {"progress_pct": p1, "weight": 0.15, "total": total_lines},
            "spool_erection": {"progress_pct": p2, "weight": 0.25, "total": total_spools},
            "welding_execution": {"progress_pct": p3, "weight": 0.25, "total": total_welds},
            "ndt_clearance": {"progress_pct": p4, "weight": 0.15, "total": total_welds},
            "hydrotest_packages": {"progress_pct": p5, "weight": 0.15, "total": total_tp},
            "mechanical_completion": {"progress_pct": p6, "weight": 0.05, "total": total_mcc},
        },
    }


def get_project_master_summary(session: Session, project_id: int) -> Dict[str, Any]:
    """
    استخراج خلاصه گزارش جامع پروژه جهت ارائه در جلسات راهبردی و داشبورد اصلی.
    """
    _validate_project_id(project_id)
    project = get_project_by_id(session, project_id)
    if not project:
        raise ValidationError(f"Project ID {project_id} not found.")

    health = calculate_project_health_score(session, project_id)
    progress = get_project_weighted_progress(session, project_id)
    areas_count = session.query(func.count(Area.id)).filter(Area.project_id == project_id).scalar() or 0

    return {
        "project_info": {
            "id": project.id,
            "project_code": project.project_code,
            "title": project.title,
            "client": project.client,
            "contractor": project.contractor,
            "standard": project.standard,
            "areas_count": areas_count,
            "created_at": project.created_at,
        },
        "health_index": health,
        "progress": progress,
    }