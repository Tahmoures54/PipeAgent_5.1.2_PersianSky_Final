# -*- coding: utf-8 -*-
"""
security/api_security.py – PipeAgent
ماژول جامع صدور، اعتبارسنجی، ابطال و چرخش کلیدهای دسترسی سازمانی (API Keys)
منطبق با استانداردهای امنیتی احراز هویت ماشین-به-ماشین (M2M) و RBAC.
"""

from __future__ import annotations

import fnmatch
import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, date
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy.exc import SQLAlchemyError
from db.models import ApiCredential

try:
    from config import API_TOKEN_PEPPER
except ImportError:
    API_TOKEN_PEPPER = ""

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Standard API Scopes
# ──────────────────────────────────────────────

class ApiScope(str, Enum):
    """دسترسی‌های استاندارد API سامانه PipeAgent"""
    ALL = "*"                                  # Implementation note.
    
    # Implementation note.
    PROJECTS_READ = "projects:read"
    PROJECTS_WRITE = "projects:write"

    # Implementation note.
    MATERIALS_READ = "materials:read"
    MATERIALS_WRITE = "materials:write"
    MATERIALS_ISSUE = "materials:issue"

    # Implementation note.
    WELDS_READ = "welds:read"
    WELDS_WRITE = "welds:write"
    WELDS_FITUP = "welds:fitup"

    # Implementation note.
    NDT_READ = "ndt:read"
    NDT_WRITE = "ndt:write"
    PUNCH_READ = "punch:read"
    PUNCH_WRITE = "punch:write"
    NCR_READ = "ncr:read"
    NCR_WRITE = "ncr:write"

    # Implementation note.
    HYDRO_READ = "hydro:read"
    HYDRO_EXECUTE = "hydro:execute"
    PRECOMM_READ = "precomm:read"
    PRECOMM_WRITE = "precomm:write"

    # Implementation note.
    AI_INSIGHTS_READ = "ai:insights:read"


# ──────────────────────────────────────────────
#  Data Transfer Objects (DTOs)
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class ApiKeyInfo:
    """اطلاعات کپسوله‌شده کلید جهت جلوگیری از بروز خطای DetachedInstanceError"""
    id: int
    name: str
    token_prefix: str
    scopes: Set[str]
    project_id: Optional[int]
    created_by: Optional[int]
    expires_at: Optional[datetime]
    created_at: datetime
    last_used_at: Optional[datetime]
    is_active: bool

    def has_scope(self, required_scope: str) -> bool:
        """
        بررسی انطباق دسترسی با پشتیبانی از الگوهای سلسله‌مراتبی (Wildcards):
        مثال: دسترسی 'welds:*' کلیه متدهای 'welds:read' و 'welds:write' را پوشش می‌دهد.
        """
        if "*" in self.scopes:
            return True
        if required_scope in self.scopes:
            return True

        for granted_scope in self.scopes:
            # Implementation note.
            if fnmatch.fnmatch(required_scope, granted_scope):
                return True
        return False


# ──────────────────────────────────────────────
#  ApiSecurity Implementation
# ──────────────────────────────────────────────

class ApiSecurity:
    """
    سرویس مدیریت امنیت کلیدهای API، کنترل دسترسی دانه‌بندی‌شده و پایش تراکنش‌ها
    """

    TOKEN_PREFIX_LENGTH = 12  # Implementation note.
    TOKEN_SECRET_BYTES = 32   # Implementation note.

    def __init__(self, db_manager):
        self.db = db_manager

    # Implementation note.

    def issue_key(
        self,
        name: str,
        scopes: List[Union[ApiScope, str]],
        project_id: Optional[int] = None,
        expires_days: Optional[int] = None,
        created_by: Optional[int] = None,
        ip_whitelist: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        صدور کلید جدید با فرمت امن: pa_live_{prefix}_{secret}
        نکته امنیتی: توکن خام (Raw Token) فقط یک‌بار در این خروجی نمایش داده می‌شود.
        """
        if not name or not name.strip():
            raise ValueError("API Key name is required.")

        if not scopes:
            raise ValueError("At least one scope must be granted to the API Key.")

        # Implementation note.
        raw_secret = secrets.token_urlsafe(self.TOKEN_SECRET_BYTES)
        token_prefix = f"pa_live_{secrets.token_hex(4)}"  # Implementation note.
        full_token = f"{token_prefix}_{raw_secret}"

        # Implementation note.
        token_hash = self._hash_token(full_token)

        # Implementation note.
        normalized_scopes = [
            s.value if isinstance(s, ApiScope) else str(s).strip() for s in scopes
        ]
        scopes_str = ",".join(sorted(set(normalized_scopes)))

        expires_at = (
            datetime.utcnow() + timedelta(days=expires_days)
            if expires_days and expires_days > 0
            else None
        )

        with self.db.session_scope() as session:
            try:
                credential = ApiCredential(
                    name=name.strip(),
                    api_key=f"{token_prefix}_REDACTED",
                    token_prefix=token_prefix,
                    token_hash=token_hash,
                    scopes=scopes_str,
                    project_id=project_id,
                    expires_at=expires_at,
                    created_by=created_by,
                    ip_whitelist=ip_whitelist,
                    created_at=datetime.utcnow(),
                )
                session.add(credential)
                session.flush()

                logger.info(
                    f"API Key '{name}' (Prefix: {token_prefix}) issued successfully "
                    f"for Project #{project_id} by User #{created_by}."
                )

                return {
                    "id": credential.id,
                    "name": credential.name,
                    "token": full_token,  # Implementation note.
                    "prefix": token_prefix,
                    "scopes": normalized_scopes,
                    "project_id": project_id,
                    "expires_at": expires_at.isoformat() if expires_at else None,
                    "warning": "Store this token securely. It cannot be retrieved again!",
                }

            except SQLAlchemyError as e:
                logger.error(f"Failed to issue API key '{name}': {e}")
                raise

    # Implementation note.

    def verify(
        self,
        raw_token: str,
        required_scope: Union[ApiScope, str],
        project_id: Optional[int] = None,
        client_ip: Optional[str] = None,
    ) -> Optional[ApiKeyInfo]:
        """
        اعتبارسنجی امن توکن دریافتی در هدر ریکوئست:
        ۱. تطبیق هش توکن
        ۲. بررسی عدم ابطال (Revocation) و عدم انقضا (Expiration)
        ۳. ارزیابی اسکوپ‌های سلسله‌مراتبی
        ۴. ارزیابی انحصار پروژه (Multi-Tenant Isolation)
        ۵. به‌روزرسانی زمان آخرین استفاده (Last Used Timestamp)
        """
        if not raw_token or not isinstance(raw_token, str):
            return None

        clean_token = raw_token.strip()
        scope_val = required_scope.value if isinstance(required_scope, ApiScope) else str(required_scope).strip()

        token_hash = self._hash_token(clean_token)

        with self.db.session_scope() as session:
            # Implementation note.
            cred = (
                session.query(ApiCredential)
                .filter(ApiCredential.token_hash == token_hash)
                .first()
            )

            if cred is None:
                # Legacy rows stored the raw token in api_key before hashing was enforced.
                cred = (
                    session.query(ApiCredential)
                    .filter(ApiCredential.api_key == clean_token)
                    .first()
                )
                if cred is not None and not cred.token_hash:
                    cred.token_hash = token_hash
                    cred.api_key = f"{cred.token_prefix or 'pa_live'}_REDACTED"

            if not cred:
                return None

            # Implementation note.
            if getattr(cred, "revoked_at", None) is not None:
                logger.warning(f"Rejected API Key [{cred.token_prefix}]: Key has been revoked.")
                return None

            if getattr(cred, "is_active", True) is False:
                logger.warning(f"Rejected API Key [{cred.token_prefix}]: Key is inactive.")
                return None

            # Implementation note.
            now = datetime.utcnow()
            if cred.expires_at and cred.expires_at < now:
                logger.warning(f"Rejected API Key [{cred.token_prefix}]: Key expired on {cred.expires_at}.")
                return None

            # Implementation note.
            if cred.project_id is not None and project_id is not None:
                if cred.project_id != project_id:
                    logger.warning(
                        f"Rejected API Key [{cred.token_prefix}]: Key is restricted to "
                        f"Project #{cred.project_id}, but requested Project #{project_id}."
                    )
                    return None

            # Implementation note.
            if hasattr(cred, "ip_whitelist") and cred.ip_whitelist and client_ip:
                allowed_ips = [ip.strip() for ip in cred.ip_whitelist.split(",") if ip.strip()]
                if client_ip not in allowed_ips:
                    logger.warning(f"Rejected API Key [{cred.token_prefix}]: IP '{client_ip}' not in whitelist.")
                    return None

            # Implementation note.
            scopes_set = set(x.strip() for x in (cred.scopes or "").split(",") if x.strip())

            key_info = ApiKeyInfo(
                id=cred.id,
                name=cred.name,
                token_prefix=cred.token_prefix,
                scopes=scopes_set,
                project_id=cred.project_id,
                created_by=cred.created_by,
                expires_at=cred.expires_at,
                created_at=cred.created_at if hasattr(cred, "created_at") else now,
                last_used_at=cred.last_used_at if hasattr(cred, "last_used_at") else None,
                is_active=True,
            )

            if not key_info.has_scope(scope_val):
                logger.warning(
                    f"Rejected API Key [{cred.token_prefix}]: Scope '{scope_val}' "
                    f"not granted in {scopes_set}."
                )
                return None

            # Implementation note.
            if hasattr(cred, "last_used_at"):
                cred.last_used_at = now

            return key_info

    # Implementation note.

    def revoke_key(
        self,
        key_id: int,
        revoked_by: Optional[int] = None,
        reason: str = "Manual revocation",
    ) -> bool:
        """ابطال فوری و قطعی یک کلید دسترسی"""
        with self.db.session_scope() as session:
            cred = session.query(ApiCredential).filter(ApiCredential.id == key_id).first()
            if not cred or cred.revoked_at is not None:
                return False

            cred.revoked_at = datetime.utcnow()
            if hasattr(cred, "revocation_reason"):
                cred.revocation_reason = reason
            if hasattr(cred, "revoked_by"):
                cred.revoked_by = revoked_by

            logger.warning(f"API Key #{key_id} [{cred.token_prefix}] REVOKED. Reason: {reason}")
            return True

    def rotate_key(
        self,
        old_key_id: int,
        grace_period_days: int = 7,
        created_by: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        چرخش امن کلید (Key Rotation):
        صدور کلید جدید با مشخصات و اسکوپ‌های مشابه و تنظیم انقضای موقت روی کلید قبلی
        جهت جلوگیری از قطع شدن سرویس‌های فعال.
        """
        with self.db.session_scope() as session:
            old_cred = session.query(ApiCredential).filter(ApiCredential.id == old_key_id).first()
            if not old_cred or old_cred.revoked_at is not None:
                raise ValueError(f"Cannot rotate invalid or revoked API Key #{old_key_id}.")

            scopes_list = [s.strip() for s in (old_cred.scopes or "").split(",") if s.strip()]
            new_name = f"{old_cred.name} (Rotated {date.today().isoformat()})"
            project_id = old_cred.project_id

            # Implementation note.
            grace_expiry = datetime.utcnow() + timedelta(days=grace_period_days)
            old_cred.expires_at = grace_expiry

        # Implementation note.
        new_key_data = self.issue_key(
            name=new_name,
            scopes=scopes_list,
            project_id=project_id,
            created_by=created_by,
        )
        logger.info(f"API Key #{old_key_id} rotated to New Key #{new_key_data['id']}.")
        return new_key_data

    def list_keys(
        self,
        project_id: Optional[int] = None,
        include_revoked: bool = False,
    ) -> List[Dict[str, Any]]:
        """لیست کلیدهای صادر شده بدون افشای هش یا کلمه عبور"""
        with self.db.session_scope() as session:
            query = session.query(ApiCredential)
            if project_id is not None:
                query = query.filter(ApiCredential.project_id == project_id)
            if not include_revoked:
                query = query.filter(ApiCredential.revoked_at.is_(None))

            creds = query.order_by(ApiCredential.id.desc()).all()
            results = []
            now = datetime.utcnow()

            for c in creds:
                is_expired = c.expires_at and c.expires_at < now
                is_active = (c.revoked_at is None) and not is_expired

                results.append({
                    "id": c.id,
                    "name": c.name,
                    "prefix": c.token_prefix,
                    "scopes": [s.strip() for s in (c.scopes or "").split(",") if s.strip()],
                    "project_id": c.project_id,
                    "is_active": is_active,
                    "is_revoked": c.revoked_at is not None,
                    "expires_at": c.expires_at.isoformat() if c.expires_at else None,
                    "last_used_at": c.last_used_at.isoformat() if getattr(c, "last_used_at", None) else None,
                })
            return results

    # Implementation note.

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        """تولید هش یکپارچه با الگوریتم SHA-256"""
        return hashlib.sha256((API_TOKEN_PEPPER + raw_token.strip()).encode("utf-8")).hexdigest()