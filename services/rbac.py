# -*- coding: utf-8 -*-
"""
services/rbac_service.py – PipeAgent
سامانه جامع و سلسله‌مراتبی کنترل دسترسی مبتنی بر نقش (Role-Based Access Control - RBAC)
شامل: تفکیک نقش‌های سراسری و پروژه‌ای، تطبیق الگوهای Wildcard (مانند quality:*)،
کش‌گذاری سریع دسترسی‌ها، دکوراتورهای محافظتی و مدیریت عضویت سازمانی در پروژه‌ها.
"""

from __future__ import annotations

import fnmatch
import functools
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from core.exceptions import AppError
from db.manager import DatabaseManager
from db.models import ProjectMembership, User

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Standard Permissions
# ──────────────────────────────────────────────

class SystemRole(str, Enum):
    """نقش‌های سراسری سامانه (Global System Roles)"""
    SUPER_ADMIN = "admin"                      # Implementation note.
    SYSTEM_AUDITOR = "system_auditor"          # Implementation note.
    USER = "user"                              # Implementation note.


class ProjectRole(str, Enum):
    """نقش‌های اختصاصی در سطح یک پروژه مشخص (Project-Level Roles)"""
    PROJECT_MANAGER = "project_manager"        # Implementation note.
    ENGINEER = "engineer"                      # Implementation note.
    INSPECTOR = "inspector"                    # Implementation note.
    SUPERVISOR = "supervisor"                  # Implementation note.
    PLANNER = "planner"                        # Implementation note.
    WELDER = "welder"                          # Implementation note.
    STOREKEEPER = "storekeeper"                # Implementation note.
    CLIENT_REP = "client_rep"                  # Implementation note.
    VIEWER = "viewer"                          # Implementation note.


class Permission(str, Enum):
    """شناسه‌های استاندارد مجوزهای دانه‌بندی‌شده سامانه PipeAgent"""
    ALL = "*"

    # Implementation note.
    PROJECT_READ = "project:read"
    PROJECT_WRITE = "project:write"
    PROJECT_DELETE = "project:delete"
    PROJECT_MEMBERS_MANAGE = "project:members:manage"

    # Implementation note.
    MATERIAL_READ = "material:read"
    MATERIAL_WRITE = "material:write"
    MATERIAL_ISSUE = "material:issue"
    MATERIAL_QUARANTINE = "material:quarantine"

    # Implementation note.
    EXECUTION_READ = "execution:read"
    EXECUTION_WRITE = "execution:write"
    WELD_FITUP = "weld:fitup"
    WELD_RECORD = "weld:record"

    # Implementation note.
    QUALITY_READ = "quality:read"
    QUALITY_APPROVE = "quality:approve"
    NDT_ASSIGN = "quality:ndt:assign"
    NDT_RECORD = "quality:ndt:record"
    PUNCH_CREATE = "quality:punch:create"
    PUNCH_CLEAR = "quality:punch:clear"
    NCR_MANAGE = "quality:ncr:manage"

    # Implementation note.
    HYDRO_EXECUTE = "turnover:hydro:execute"
    TURNOVER_READ = "turnover:read"
    TURNOVER_WRITE = "turnover:write"
    MCC_SIGNOFF = "turnover:mcc:signoff"

    # Implementation note.
    REPORTS_READ = "reports:read"
    REPORTS_EXPORT = "reports:export"
    FIELD_SYNC = "field:sync"


# ──────────────────────────────────────────────
#  Role-Permissions Mapping Matrix
# ──────────────────────────────────────────────

ROLE_PERMISSIONS_MAP: Dict[str, Set[str]] = {
    SystemRole.SUPER_ADMIN.value: {Permission.ALL.value},
    
    SystemRole.SYSTEM_AUDITOR.value: {
        "project:read", "execution:read", "quality:read", "turnover:read",
        "reports:read", "reports:export", "material:read"
    },

    ProjectRole.PROJECT_MANAGER.value: {
        "project:read", "project:write", "project:members:manage",
        "execution:*", "quality:*", "turnover:*", "material:*",
        "reports:*", "field:sync"
    },

    ProjectRole.ENGINEER.value: {
        "project:read", "execution:read", "execution:write",
        "material:read", "material:write", "material:issue",
        "quality:read", "turnover:read", "turnover:write", "reports:read"
    },

    ProjectRole.INSPECTOR.value: {
        "project:read", "execution:read", "weld:fitup",
        "quality:*", "material:read", "material:quarantine",
        "turnover:read", "turnover:mcc:signoff", "reports:read", "field:sync"
    },

    ProjectRole.SUPERVISOR.value: {
        "project:read", "execution:read", "execution:write",
        "weld:record", "material:read", "material:issue", "field:sync", "reports:read"
    },

    ProjectRole.PLANNER.value: {
        "project:read", "execution:read", "execution:write",
        "material:read", "turnover:read", "reports:*"
    },

    ProjectRole.STOREKEEPER.value: {
        "project:read", "material:*", "reports:read"
    },

    ProjectRole.CLIENT_REP.value: {
        "project:read", "execution:read", "quality:read", "quality:approve",
        "turnover:read", "turnover:mcc:signoff", "reports:read", "reports:export"
    },

    ProjectRole.WELDER.value: {
        "project:read", "execution:read", "field:sync"
    },

    ProjectRole.VIEWER.value: {
        "project:read", "execution:read", "quality:read", "turnover:read", "reports:read"
    },
}


# ──────────────────────────────────────────────
#  Custom Exceptions
# ──────────────────────────────────────────────

class PermissionDeniedError(AppError):
    """خطای عدم دسترسی و رد مجوز عملیاتی"""
    def __init__(self, permission: str, project_id: Optional[int] = None, user_id: Optional[int] = None):
        msg = f"Permission denied: Action '{permission}' is not allowed"
        if project_id:
            msg += f" on Project #{project_id}"
        if user_id:
            msg += f" for User #{user_id}"
        super().__init__(msg)
        self.permission = permission
        self.project_id = project_id
        self.user_id = user_id


# ──────────────────────────────────────────────
#  RBAC Service Implementation
# ──────────────────────────────────────────────

class RBACService:
    """
    سرویس جامع بررسی اختیارات، تطبیق سلسله‌مراتبی مجوزها و حاکمیت امنیتی پروژه‌ها
    """

    def __init__(self, db: DatabaseManager):
        self.db = db
        # Implementation note.
        self._membership_cache: Dict[Tuple[int, int], Optional[str]] = {}

    # Implementation note.

    def allowed(
        self,
        user: Optional[User],
        permission: Union[Permission, str],
        project_id: Optional[int] = None,
    ) -> bool:
        """
        بررسی اینکه آیا کاربر دارای مجوز درخواستی در دامنه مورد نظر است یا خیر.
        منطق ارزیابی:
        ۱. کاربر باید معتبر و فعال باشد.
        ۲. نقش Super Admin دسترسی تام دارد.
        ۳. در صورت تعیین project_id، نقش کاربر درون آن پروژه واکشی و ارزیابی می‌شود.
        ۴. الگوهای Wildcard سلسله‌مراتبی (مانند quality:*) پشتیبانی می‌شوند.
        """
        if not user or not getattr(user, "is_active", False):
            return False

        perm_str = permission.value if isinstance(permission, Permission) else str(permission).strip()

        # Implementation note.
        if getattr(user, "role", "") == SystemRole.SUPER_ADMIN.value:
            return True

        # Implementation note.
        effective_roles: Set[str] = set()

        # Implementation note.
        if getattr(user, "role", None):
            effective_roles.add(user.role)

        # Implementation note.
        if project_id is not None:
            project_role = self._get_user_project_role(user.id, project_id)
            if not project_role:
                # Implementation note.
                return False
            effective_roles.add(project_role)

        # Implementation note.
        granted_permissions: Set[str] = set()
        for r in effective_roles:
            granted_permissions.update(ROLE_PERMISSIONS_MAP.get(r, set()))

        # Implementation note.
        return self._evaluate_permission_match(granted_permissions, perm_str)

    # Implementation note.

    def has_any_permission(
        self,
        user: Optional[User],
        permissions: List[Union[Permission, str]],
        project_id: Optional[int] = None,
    ) -> bool:
        """بررسی اینکه آیا کاربر حداقل یکی از مجوزهای لیست را داراست"""
        return any(self.allowed(user, p, project_id) for p in permissions)

    def has_all_permissions(
        self,
        user: Optional[User],
        permissions: List[Union[Permission, str]],
        project_id: Optional[int] = None,
    ) -> bool:
        """بررسی اینکه آیا کاربر تمام مجوزهای لیست را داراست"""
        return all(self.allowed(user, p, project_id) for p in permissions)

    def get_effective_permissions(
        self,
        user: Optional[User],
        project_id: Optional[int] = None,
    ) -> Set[str]:
        """استخراج فهرست کامل مجوزهای معتبر کاربر در یک پروژه جهت ارسال به فرانت‌اند"""
        if not user or not getattr(user, "is_active", False):
            return set()

        if getattr(user, "role", "") == SystemRole.SUPER_ADMIN.value:
            return {Permission.ALL.value}

        effective_roles: Set[str] = {user.role} if getattr(user, "role", None) else set()
        if project_id is not None:
            p_role = self._get_user_project_role(user.id, project_id)
            if p_role:
                effective_roles.add(p_role)

        result: Set[str] = set()
        for r in effective_roles:
            result.update(ROLE_PERMISSIONS_MAP.get(r, set()))
        return result

    def get_accessible_project_ids(
        self,
        user: Optional[User],
        required_permission: Optional[Union[Permission, str]] = None,
    ) -> List[int]:
        """دریافت لیست شناسه‌های پروژه‌هایی که کاربر مجاز به دسترسی به آن‌هاست"""
        if not user or not getattr(user, "is_active", False):
            return []

        with self.db.session_scope() as session:
            # Implementation note.
            if getattr(user, "role", "") == SystemRole.SUPER_ADMIN.value:
                # Implementation note.
                from db.models import Project
                return [p.id for p in session.query(Project.id).all()]

            memberships = (
                session.query(ProjectMembership.project_id, ProjectMembership.role)
                .filter(
                    ProjectMembership.user_id == user.id,
                    ProjectMembership.is_active == True,
                )
                .all()
            )

            if not required_permission:
                return [m.project_id for m in memberships]

            perm_str = required_permission.value if isinstance(required_permission, Permission) else str(required_permission)
            accessible_pids = []

            for m in memberships:
                role_perms = ROLE_PERMISSIONS_MAP.get(m.role, set())
                if self._evaluate_permission_match(role_perms, perm_str):
                    accessible_pids.append(m.project_id)

            return accessible_pids

    # Implementation note.

    def assign_project_role(
        self,
        project_id: int,
        user_id: int,
        role: Union[ProjectRole, str],
        assigned_by_user: Optional[User] = None,
    ) -> ProjectMembership:
        """انتساب یا به‌روزرسانی نقش یک کاربر در پروژه با بررسی دسترسی کاربر انتساب‌دهنده"""
        if assigned_by_user:
            if not self.allowed(assigned_by_user, Permission.PROJECT_MEMBERS_MANAGE, project_id):
                raise PermissionDeniedError(Permission.PROJECT_MEMBERS_MANAGE.value, project_id, assigned_by_user.id)

        role_str = role.value if isinstance(role, ProjectRole) else str(role).strip().lower()
        if role_str not in ROLE_PERMISSIONS_MAP:
            raise AppError(f"Invalid project role: '{role_str}'")

        with self.db.session_scope() as session:
            membership = (
                session.query(ProjectMembership)
                .filter(
                    ProjectMembership.project_id == project_id,
                    ProjectMembership.user_id == user_id,
                )
                .first()
            )

            if not membership:
                membership = ProjectMembership(
                    project_id=project_id,
                    user_id=user_id,
                    role=role_str,
                    is_active=True,
                )
                session.add(membership)
            else:
                membership.role = role_str
                membership.is_active = True

            session.flush()

            # Implementation note.
            self._membership_cache.pop((user_id, project_id), None)
            logger.info(f"Assigned Project Role '{role_str}' to User #{user_id} on Project #{project_id}.")
            return membership

    def revoke_project_membership(
        self,
        project_id: int,
        user_id: int,
        revoked_by_user: Optional[User] = None,
    ) -> bool:
        """ابطال عضویت و سلب دسترسی کاربر از یک پروژه"""
        if revoked_by_user:
            if not self.allowed(revoked_by_user, Permission.PROJECT_MEMBERS_MANAGE, project_id):
                raise PermissionDeniedError(Permission.PROJECT_MEMBERS_MANAGE.value, project_id, revoked_by_user.id)

        with self.db.session_scope() as session:
            membership = (
                session.query(ProjectMembership)
                .filter(
                    ProjectMembership.project_id == project_id,
                    ProjectMembership.user_id == user_id,
                )
                .first()
            )
            if not membership:
                return False

            membership.is_active = False
            session.flush()

            self._membership_cache.pop((user_id, project_id), None)
            logger.warning(f"Revoked Project Membership for User #{user_id} on Project #{project_id}.")
            return True

    # Implementation note.

    def _get_user_project_role(self, user_id: int, project_id: int) -> Optional[str]:
        """واکشی نقش کاربر در پروژه با استفاده از مکانیزم کش‌گذاری سبک"""
        cache_key = (user_id, project_id)
        if cache_key in self._membership_cache:
            return self._membership_cache[cache_key]

        with self.db.session_scope() as session:
            membership = (
                session.query(ProjectMembership.role)
                .filter(
                    ProjectMembership.project_id == project_id,
                    ProjectMembership.user_id == user_id,
                    ProjectMembership.is_active == True,
                )
                .first()
            )
            role = membership.role if membership else None
            self._membership_cache[cache_key] = role
            return role

    @staticmethod
    def _evaluate_permission_match(granted_permissions: Set[str], required_permission: str) -> bool:
        """
        تطبیق هوشمند الگوهای دسترسی (Wildcard Matching):
        - مجوز '*' دسترسی به تمام دستورات را باز می‌کند.
        - مجوز 'quality:*' تمام دستورات 'quality:read'، 'quality:approve' و... را پوشش می‌دهد.
        """
        if Permission.ALL.value in granted_permissions:
            return True
        if required_permission in granted_permissions:
            return True

        for granted in granted_permissions:
            # Implementation note.
            if fnmatch.fnmatch(required_permission, granted):
                return True
        return False


# ──────────────────────────────────────────────
#  Security Decorator for Service Layer & APIs
# ──────────────────────────────────────────────

def require_permission(
    permission: Union[Permission, str],
    project_id_param_name: str = "project_id",
):
    """
    دکوراتور امنیتی جهت تزریق گارد اعتبارسنجی مجوزها روی متدهای لایه سرویس یا اندپوینت‌ها:

    @require_permission(Permission.QUALITY_APPROVE)
    def approve_weld_inspection(self, user, project_id, weld_id):
        ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Implementation note.
            user = kwargs.get("user") or (args[0] if len(args) > 0 and isinstance(args[0], User) else None)
            project_id = kwargs.get(project_id_param_name)

            rbac: RBACService = getattr(self, "rbac_service", getattr(self, "rbac", None))
            if not rbac and hasattr(self, "db"):
                rbac = RBACService(self.db)

            if rbac and not rbac.allowed(user, permission, project_id):
                raise PermissionDeniedError(
                    permission=permission.value if isinstance(permission, Permission) else str(permission),
                    project_id=project_id,
                    user_id=getattr(user, "id", None),
                )

            return func(self, *args, **kwargs)
        return wrapper
    return decorator