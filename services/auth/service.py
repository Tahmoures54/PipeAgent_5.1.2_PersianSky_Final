# -*- coding: utf-8 -*-
# services/auth/service.py – PipeAgent
# Authentication service: login, password change, role checks.

import logging
from typing import Optional, Tuple
from db.manager import DatabaseManager
from db.models import User
from security.hashing import hash_password, verify_password

logger = logging.getLogger(__name__)


class AuthService:
    """
    Handles user authentication logic, independent of UI.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[User], str]:
        """
        Verify username / password.
        Returns (success, user, message).
        """
        user = self.db.get_user_by_username(username)
        if not user:
            return False, None, "Invalid username or password."
        if not user.is_active:
            return False, None, "Account is deactivated."

        try:
            if verify_password(password, user.password_hash):
                # ✅ FIX: pass the User object, not user.id
                self.db.update_user_last_login(user)
                return True, user, "Login successful."
            else:
                return False, None, "Invalid username or password."
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
        if len(new_password) < 8:  # config.PASSWORD_MIN_LENGTH could be used
            return False, "New password must be at least 8 characters."
        user.password_hash = hash_password(new_password)
        # The caller is responsible for committing the session.
        return True, "Password changed successfully."

    def user_has_permission(self, user: User, required_role: str) -> bool:
        """
        Simple hierarchical role check.
        Admins can do anything; others only their own role.
        """
        if user.role == "admin":
            return True
        return user.role == required_role