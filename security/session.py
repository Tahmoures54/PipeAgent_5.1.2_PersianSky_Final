# -*- coding: utf-8 -*-
"""
security/session.py – PipeAgent
مدیریت جامع، امن و چندنخی نشست‌های کاربری (Session Manager)
شامل: تولید توکن‌های تصادفی ایمن، انقضای هوشمند (Idle & Absolute Timeout)،
ماتریس کنترل دسترسی مبتنی بر نقش (RBAC) و قابلیت خاتمه نشست‌ها.
"""

from __future__ import annotations

import logging
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

from db.models import User

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Roles & Permissions (RBAC Matrix)
# ──────────────────────────────────────────────

class UserRole(str, Enum):
    """نقش‌های استاندارد سازمانی در پروژه‌های EPC و پایپینگ"""
    SUPER_ADMIN = "SUPER_ADMIN"        # Implementation note.
    PROJECT_MANAGER = "PROJECT_MGR"    # Implementation note.
    QC_MANAGER = "QC_MANAGER"          # Implementation note.
    QC_INSPECTOR = "QC_INSPECTOR"      # Implementation note.
    CLIENT_REP = "CLIENT_REP"          # Implementation note.
    SHOP_SUPERVISOR = "SHOP_SUPERVISOR"# Implementation note.
    PLANNING_ENG = "PLANNING_ENG"      # Implementation note.
    STOREKEEPER = "STOREKEEPER"        # Implementation note.
    VIEWER = "VIEWER"                  # Implementation note.


class Permission(str, Enum):
    """مجوزهای دانه‌بندی‌شده عملیاتی سامانه PipeAgent"""
    # Implementation note.
    PROJECT_CREATE = "project:create"
    PROJECT_EDIT = "project:edit"
    PROJECT_DELETE = "project:delete"

    # Implementation note.
    MATERIAL_RECEIVE = "material:receive"
    MATERIAL_ISSUE = "material:issue"
    MATERIAL_RESERVE = "material:reserve"
    MATERIAL_QUARANTINE = "material:quarantine"

    # Implementation note.
    WELD_RECORD = "weld:record"
    WELD_FITUP_APPROVE = "weld:fitup_approve"
    WELDER_QUALIFY = "welder:qualify"
    WELDER_SUSPEND = "welder:suspend"

    # Implementation note.
    NDT_ASSIGN = "ndt:assign"
    NDT_RECORD_RESULT = "ndt:record_result"
    PUNCH_CREATE = "punch:create"
    PUNCH_CLEAR_CAT_A = "punch:clear_cat_a"
    PUNCH_CLEAR_CAT_B = "punch:clear_cat_b"
    NCR_ISSUE = "ncr:issue"
    NCR_DISPOSITION = "ncr:disposition"
    NCR_CLOSE = "ncr:close"

    # Implementation note.
    HYDRO_APPROVE = "hydro:approve"
    HYDRO_SIGN_OFF = "hydro:signoff"
    REINSTATEMENT_CLEAR = "reinstatement:clear"
    PRECOMM_EVALUATE = "precomm:evaluate"


# Implementation note.
ROLE_PERMISSIONS_MAP: Dict[UserRole, Set[Permission]] = {
    UserRole.SUPER_ADMIN: set(Permission),  # Implementation note.
    UserRole.QC_MANAGER: {
        Permission.WELD_FITUP_APPROVE, Permission.WELDER_QUALIFY, Permission.WELDER_SUSPEND,
        Permission.NDT_ASSIGN, Permission.NDT_RECORD_RESULT,
        Permission.PUNCH_CREATE, Permission.PUNCH_CLEAR_CAT_A, Permission.PUNCH_CLEAR_CAT_B,
        Permission.NCR_ISSUE, Permission.NCR_DISPOSITION, Permission.NCR_CLOSE,
        Permission.HYDRO_APPROVE, Permission.HYDRO_SIGN_OFF, Permission.REINSTATEMENT_CLEAR,
        Permission.PRECOMM_EVALUATE, Permission.MATERIAL_QUARANTINE,
    },
    UserRole.QC_INSPECTOR: {
        Permission.WELD_FITUP_APPROVE, Permission.NDT_RECORD_RESULT,
        Permission.PUNCH_CREATE, Permission.PUNCH_CLEAR_CAT_B,
        Permission.NCR_ISSUE, Permission.HYDRO_SIGN_OFF,
        Permission.REINSTATEMENT_CLEAR,
    },
    UserRole.CLIENT_REP: {
        Permission.PUNCH_CREATE, Permission.PUNCH_CLEAR_CAT_A, Permission.PUNCH_CLEAR_CAT_B,
        Permission.NCR_DISPOSITION, Permission.NCR_CLOSE, Permission.HYDRO_SIGN_OFF,
    },
    UserRole.SHOP_SUPERVISOR: {
        Permission.WELD_RECORD, Permission.MATERIAL_RESERVE,
    },
    UserRole.STOREKEEPER: {
        Permission.MATERIAL_RECEIVE, Permission.MATERIAL_ISSUE, Permission.MATERIAL_RESERVE,
    },
    UserRole.VIEWER: set(),
}


# ──────────────────────────────────────────────
#  Session Data Structure
# ──────────────────────────────────────────────

@dataclass
class UserSession:
    """ساختار اطلاعاتی یک نشست فعال کاربری"""
    session_token: str
    user_id: int
    username: str
    user_role: str
    login_time: datetime = field(default_factory=datetime.utcnow)
    last_activity_time: datetime = field(default_factory=datetime.utcnow)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_active: bool = True
    custom_permissions: Set[str] = field(default_factory=set)

    def is_idle_expired(self, max_idle_minutes: int) -> bool:
        """بررسی انقضای نشست به دلیل عدم فعالیت (Idle Timeout)"""
        idle_delta = datetime.utcnow() - self.last_activity_time
        return idle_delta > timedelta(minutes=max_idle_minutes)

    def is_absolute_expired(self, max_lifetime_hours: int) -> bool:
        """بررسی انقضای مطلق نشست از زمان شروع لاگین (Absolute Timeout)"""
        lifetime_delta = datetime.utcnow() - self.login_time
        return lifetime_delta > timedelta(hours=max_lifetime_hours)

    def touch(self) -> None:
        """به‌روزرسانی زمان آخرین فعالیت نشست (Keep-Alive)"""
        self.last_activity_time = datetime.utcnow()


# ──────────────────────────────────────────────
#  Session Manager Implementation
# ──────────────────────────────────────────────

class SessionManager:
    """
    مدیریت متمرکز و ایمن نشست‌های کاربری با قابلیت پشتیبانی از چند کاربر همزمان
    و هماهنگ با الزامات امنیتی سامانه‌های تحت وب و دسکتاپ.
    """

    def __init__(
        self,
        idle_timeout_minutes: int = 30,
        absolute_timeout_hours: int = 8,
    ):
        self._idle_timeout_minutes = idle_timeout_minutes
        self._absolute_timeout_hours = absolute_timeout_hours
        self._sessions: Dict[str, UserSession] = {}
        self._lock = threading.RLock()  # Implementation note.

        # Implementation note.
        self._current_desktop_token: Optional[str] = None

    # Implementation note.

    def start_session(
        self,
        user: User,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserSession:
        """
        ایجاد و ثبت نشست جدید با تولید توکن رمزنگاری‌شده امن (CSPRNG)
        """
        with self._lock:
            # Implementation note.
            self._cleanup_expired_sessions()

            # Implementation note.
            session_token = secrets.token_urlsafe(32)

            session = UserSession(
                session_token=session_token,
                user_id=user.id,
                username=user.username,
                user_role=user.role if hasattr(user, "role") else UserRole.VIEWER.value,
                login_time=datetime.utcnow(),
                last_activity_time=datetime.utcnow(),
                ip_address=ip_address,
                user_agent=user_agent,
                is_active=True,
            )

            self._sessions[session_token] = session
            self._current_desktop_token = session_token

            logger.info(
                f"Session started for user '{user.username}' (Role: {session.user_role}, IP: {ip_address})."
            )
            return session

    def get_session(self, session_token: Optional[str] = None) -> Optional[UserSession]:
        """
        بازیابی نشست و اعتبارسنجی اعتبار زمانی آن.
        در صورت عدم ارسال توکن، از نشست جاری دسکتاپ استفاده می‌شود.
        """
        token = session_token or self._current_desktop_token
        if not token:
            return None

        with self._lock:
            session = self._sessions.get(token)
            if not session or not session.is_active:
                return None

            # Implementation note.
            if session.is_idle_expired(self._idle_timeout_minutes):
                logger.warning(f"Session for user '{session.username}' expired due to IDLE timeout.")
                self.end_session(token)
                return None

            # Implementation note.
            if session.is_absolute_expired(self._absolute_timeout_hours):
                logger.warning(f"Session for user '{session.username}' expired due to ABSOLUTE lifetime limit.")
                self.end_session(token)
                return None

            # Implementation note.
            session.touch()
            return session

    def end_session(self, session_token: Optional[str] = None) -> None:
        """خاتمه و ابطال قطعی نشست کاربری"""
        token = session_token or self._current_desktop_token
        if not token:
            return

        with self._lock:
            session = self._sessions.pop(token, None)
            if session:
                session.is_active = False
                logger.info(f"Session terminated for user '{session.username}'.")

            if self._current_desktop_token == token:
                self._current_desktop_token = None

    def end_all_sessions_for_user(self, user_id: int) -> int:
        """ابطال تمامی نشست‌های فعال یک کاربر خاص (مثلاً پس از تغییر کلمه عبور)"""
        with self._lock:
            tokens_to_revoke = [
                tok for tok, s in self._sessions.items() if s.user_id == user_id
            ]
            for tok in tokens_to_revoke:
                self.end_session(tok)
            logger.warning(f"Revoked {len(tokens_to_revoke)} active sessions for User #{user_id}.")
            return len(tokens_to_revoke)

    # Implementation note.

    def has_permission(
        self,
        permission: Union[Permission, str],
        session_token: Optional[str] = None,
    ) -> bool:
        """
        بررسی اینکه آیا کاربر صاحب نشست دارای مجوز عملیاتی مدنظر است یا خیر
        """
        session = self.get_session(session_token)
        if not session:
            return False

        perm_val = permission.value if isinstance(permission, Permission) else permission

        # Implementation note.
        try:
            role_enum = UserRole(session.user_role)
            role_perms = {p.value for p in ROLE_PERMISSIONS_MAP.get(role_enum, set())}
            if perm_val in role_perms:
                return True
        except ValueError:
            pass

        # Implementation note.
        if session.user_role == UserRole.SUPER_ADMIN.value:
            return True

        return perm_val in session.custom_permissions

    def has_role(
        self,
        required_roles: Union[UserRole, List[UserRole], str, List[str]],
        session_token: Optional[str] = None,
    ) -> bool:
        """بررسی تطابق نقش کاربر با نقش‌های مجاز"""
        session = self.get_session(session_token)
        if not session:
            return False

        if not isinstance(required_roles, list):
            required_roles = [required_roles]

        target_roles = {
            r.value if isinstance(r, UserRole) else r for r in required_roles
        }

        # Implementation note.
        if session.user_role == UserRole.SUPER_ADMIN.value:
            return True

        return session.user_role in target_roles

    # Implementation note.

    @property
    def is_authenticated(self) -> bool:
        """وضعیت لاگین بودن کاربر جاری دسکتاپ"""
        return self.get_session() is not None

    @property
    def current_user(self) -> Optional[UserSession]:
        """اطلاعات نشست کاربر جاری"""
        return self.get_session()

    @property
    def user_role(self) -> str:
        """نقش کاربر جاری"""
        s = self.get_session()
        return s.user_role if s else ""

    @property
    def username(self) -> str:
        """نام کاربری کاربر جاری"""
        s = self.get_session()
        return s.username if s else ""

    @property
    def user_id(self) -> Optional[int]:
        """شناسه دیتابیسی کاربر جاری"""
        s = self.get_session()
        return s.user_id if s else None

    # Implementation note.

    def _cleanup_expired_sessions(self) -> None:
        """پاکسازی خودکار تمام نشست‌های منقضی‌شده از حافظه RAM"""
        expired_tokens = []
        for tok, session in self._sessions.items():
            if (
                session.is_idle_expired(self._idle_timeout_minutes)
                or session.is_absolute_expired(self._absolute_timeout_hours)
                or not session.is_active
            ):
                expired_tokens.append(tok)

        for tok in expired_tokens:
            self._sessions.pop(tok, None)
            if self._current_desktop_token == tok:
                self._current_desktop_token = None


# Implementation note.
session_manager = SessionManager()