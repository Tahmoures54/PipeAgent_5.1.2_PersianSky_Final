# -*- coding: utf-8 -*-
# services/auth/service.py – PipeAgent
# Authentication service: login, password change, role checks.

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Tuple

from config import MAX_LOGIN_ATTEMPTS, PASSWORD_MIN_LENGTH
from db.manager import DatabaseManager
from db.models import User
from security.hashing import (
    hash_password,
    verify_password,
    needs_rehash,
    validate_password_strength,
)

logger = logging.getLogger(__name__)

_LOCKOUT_SECONDS = 15 * 60


class AuthService:
    """
    Handles user authentication logic, independent of UI.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db
        self._lock = threading.Lock()
        self._failures: dict[str, tuple[int, float]] = {}

    def _lockout_key(self, username: str) -> str:
        return (username or "").strip().lower()

    def _is_locked(self, username: str) -> Optional[int]:
        key = self._lockout_key(username)
        with self._lock:
            record = self._failures.get(key)
            if not record:
                return None
            count, started = record
            if count < MAX_LOGIN_ATTEMPTS:
                return None
            elapsed = time.monotonic() - started
            remaining = int(_LOCKOUT_SECONDS - elapsed)
            if remaining <= 0:
                self._failures.pop(key, None)
                return None
            return remaining

    def _register_failure(self, username: str) -> None:
        key = self._lockout_key(username)
        now = time.monotonic()
        with self._lock:
            count, started = self._failures.get(key, (0, now))
            if now - started > _LOCKOUT_SECONDS:
                count, started = 0, now
            self._failures[key] = (count + 1, started)

    def _clear_failures(self, username: str) -> None:
        with self._lock:
            self._failures.pop(self._lockout_key(username), None)

    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[User], str]:
        """
        Verify username / password.
        Returns (success, user, message).
        """
        username = (username or "").strip()
        remaining = self._is_locked(username)
        if remaining is not None:
            return False, None, f"Account temporarily locked. Try again in {remaining} seconds."

        user = self.db.get_user_by_username(username)
        if not user or not verify_password(password, user.password_hash):
            self._register_failure(username)
            return False, None, "Invalid username or password."
        if not user.is_active:
            return False, None, "Account is deactivated."

        try:
            if needs_rehash(user.password_hash):
                new_hash = hash_password(password)
                self.db.update_user_password_hash(user.id, new_hash)
                user.password_hash = new_hash
            self.db.update_user_last_login(user)
            self._clear_failures(username)
            return True, user, "Login successful."
        except Exception as e:
            logger.error("Password verification error: %s", e)
            return False, None, "Authentication error."

    def change_password(self, user: User, old_password: str, new_password: str) -> Tuple[bool, str]:
        """
        Change password after verifying the old one.
        Returns (success, message).
        """
        if not verify_password(old_password, user.password_hash):
            return False, "Current password is incorrect."
        ok, errors = validate_password_strength(new_password)
        if not ok:
            if len(new_password) < PASSWORD_MIN_LENGTH:
                return False, f"New password must be at least {PASSWORD_MIN_LENGTH} characters."
            return False, " ".join(errors)
        new_hash = hash_password(new_password)
        self.db.update_user_password_hash(user.id, new_hash)
        user.password_hash = new_hash
        return True, "Password changed successfully."

    def user_has_permission(self, user: User, required_role: str) -> bool:
        """
        Simple hierarchical role check.
        Admins can do anything; others only their own role.
        """
        if user.role in {"admin", "SUPER_ADMIN", "admin".upper()}:
            return True
        if str(user.role).lower() == "admin":
            return True
        return user.role == required_role
