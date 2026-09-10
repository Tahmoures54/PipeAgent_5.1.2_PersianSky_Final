# -*- coding: utf-8 -*-
"""
security/hashing.py – PipeAgent
ماژول پیشرفته و چندلایه‌ای رمزنگاری، اعتبارسنجی و ارتقای هش کلمات عبور
منطبق با الزامات امنیتی OWASP و NIST SP 800-63B.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Implementation note.
_HAS_ARGON2 = False
_HAS_BCRYPT = False

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash
    # Implementation note.
    # Memory: 64MB (65536 KB), Iterations (Time): 3, Parallelism: 4 threads
    argon2_hasher = PasswordHasher(
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        salt_len=16,
    )
    _HAS_ARGON2 = True
except ImportError:
    argon2_hasher = None

try:
    import bcrypt
    _HAS_BCRYPT = True
except ImportError:
    bcrypt = None


# ──────────────────────────────────────────────
#  Constants & Security Parameters
# ──────────────────────────────────────────────

# Implementation note.
PBKDF2_ITERATIONS = 600_000
PBKDF2_SALT_BYTES = 16
PBKDF2_ALGORITHM = "sha256"

# Implementation note.
MAX_PASSWORD_LENGTH = 1024
MIN_PASSWORD_LENGTH = 8


class HashingAlgorithm(str, Enum):
    """الگوریتم‌های پشتیبانی‌شده جهت ردیابی و ارتقای خودکار"""
    ARGON2ID = "argon2id"
    BCRYPT = "bcrypt"
    PBKDF2_SHA256 = "pbkdf2_sha256"
    LEGACY_SALTED_SHA256 = "legacy_sha256"


# ──────────────────────────────────────────────
#  Core Password Hashing Functions
# ──────────────────────────────────────────────

def hash_password(password: str) -> str:
    """
    تولید هش امن کلمه عبور با استفاده از قوی‌ترین الگوریتم در دسترس:
    1. Argon2id (در صورت نصب argon2-cffi)
    2. Bcrypt (در صورت نصب bcrypt)
    3. PBKDF2-HMAC-SHA256 با ۶۰۰,۰۰۰ دور (استاندارد پیش‌فرض پایتون بدون نیاز به کتابخانه خارجی)
    """
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string.")

    if len(password.encode("utf-8")) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password exceeds maximum length limit of {MAX_PASSWORD_LENGTH} bytes.")

    # Implementation note.
    if _HAS_ARGON2 and argon2_hasher:
        try:
            return argon2_hasher.hash(password)
        except Exception as e:
            logger.error(f"Argon2 hashing error: {e}. Falling back...")

    # Implementation note.
    if _HAS_BCRYPT and bcrypt:
        try:
            salt = bcrypt.gensalt(rounds=12)
            hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
            return hashed.decode("utf-8")
        except Exception as e:
            logger.error(f"Bcrypt hashing error: {e}. Falling back...")

    # Implementation note.
    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    derived_key = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(derived_key).decode("ascii")
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt_b64}${hash_b64}"


def verify_password(password: str, hashed_password: str) -> bool:
    """
    بررسی صحت کلمه عبور با مقایسه زمان‌ثابت (Constant-Time)
    پشتیبانی همزمان از:
    - Argon2id
    - Bcrypt
    - PBKDF2
    - هش‌های قدیمی پایپ‌ایجنت (Legacy Salted SHA-256)
    """
    if not password or not hashed_password or not isinstance(hashed_password, str):
        return False

    if len(password.encode("utf-8")) > MAX_PASSWORD_LENGTH:
        return False

    # Implementation note.
    if hashed_password.startswith("$argon2"):
        if not _HAS_ARGON2 or not argon2_hasher:
            logger.warning("Verifying Argon2 hash without argon2-cffi installed.")
            return False
        try:
            return argon2_hasher.verify(hashed_password, password)
        except (VerifyMismatchError, VerificationError, InvalidHash):
            return False

    # Implementation note.
    elif hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        if not _HAS_BCRYPT or not bcrypt:
            logger.warning("Verifying Bcrypt hash without bcrypt library installed.")
            return False
        try:
            return bcrypt.checkpw(
                password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except Exception:
            return False

    # Implementation note.
    elif hashed_password.startswith("pbkdf2_sha256$"):
        try:
            parts = hashed_password.split("$")
            if len(parts) != 4:
                return False
            _, iterations_str, salt_b64, stored_hash_b64 = parts
            iterations = int(iterations_str)
            salt = base64.b64decode(salt_b64.encode("ascii"))
            stored_hash = base64.b64decode(stored_hash_b64.encode("ascii"))

            computed_hash = hashlib.pbkdf2_hmac(
                PBKDF2_ALGORITHM,
                password.encode("utf-8"),
                salt,
                iterations,
            )
            # Implementation note.
            return secrets.compare_digest(computed_hash, stored_hash)
        except (ValueError, TypeError, KeyError):
            return False

    # Implementation note.
    elif "$" in hashed_password and len(hashed_password.split("$")) == 2:
        return _verify_legacy_sha256(password, hashed_password)

    return False


def needs_rehash(hashed_password: str) -> bool:
    """
    بررسی اینکه آیا هش موجود قدیمی یا ضعیف است و باید پس از لاگین کاربر به‌روزرسانی شود.
    """
    if not hashed_password or not isinstance(hashed_password, str):
        return True

    # Implementation note.
    if "$" in hashed_password and len(hashed_password.split("$")) == 2 and not hashed_password.startswith("$"):
        return True

    # Implementation note.
    if _HAS_ARGON2 and argon2_hasher:
        if not hashed_password.startswith("$argon2"):
            return True
        try:
            return argon2_hasher.check_needs_rehash(hashed_password)
        except Exception:
            return True

    # Implementation note.
    if hashed_password.startswith("pbkdf2_sha256$"):
        try:
            iterations = int(hashed_password.split("$")[1])
            return iterations < PBKDF2_ITERATIONS
        except (IndexError, ValueError):
            return True

    return False


# ──────────────────────────────────────────────
#  Legacy Support & Helpers
# ──────────────────────────────────────────────

def _verify_legacy_sha256(password: str, hashed_password: str) -> bool:
    """
    تأیید هش‌های قدیمی سیستم قبلی: {salt_hex}${sha256_hex}
    ایمن‌شده با مقایسه زمان‌ثابت secrets.compare_digest
    """
    try:
        salt, stored_hash = hashed_password.split("$", 1)
        salted = (salt + password).encode("utf-8")
        computed_hash = hashlib.sha256(salted).hexdigest()

        # Implementation note.
        return secrets.compare_digest(computed_hash, stored_hash)
    except (ValueError, TypeError):
        return False


# ──────────────────────────────────────────────
#  Password Policy & Strength Validation
# ──────────────────────────────────────────────

COMMON_WEAK_PASSWORDS = {
    "password", "12345678", "admin123", "qwertyuiop", "pipeagent",
    "p@ssword", "welcome123", "password123", "letmein123"
}

def validate_password_strength(password: str) -> Tuple[bool, List[str]]:
    """
    اعتبارسنجی الزامات امنیتی پیچیدگی کلمه عبور:
    - حداقل ۸ کاراکتر
    - ترکیبی از حروف کوچک، بزرگ و اعداد
    - عدم استفاده از پسوردهای متداول و حدس‌زدنی
    """
    errors: List[str] = []

    if not password or len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")

    if len(password.encode("utf-8")) > MAX_PASSWORD_LENGTH:
        errors.append(f"Password is too long (maximum {MAX_PASSWORD_LENGTH} bytes).")

    if password.lower() in COMMON_WEAK_PASSWORDS:
        errors.append("Password is too common and easily guessable.")

    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter (a-z).")

    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter (A-Z).")

    if not re.search(r"\d", password):
        errors.append("Password must contain at least one numerical digit (0-9).")

    return len(errors) == 0, errors