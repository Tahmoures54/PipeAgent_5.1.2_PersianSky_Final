# -*- coding: utf-8 -*-
"""
security/oidc_service.py – PipeAgent
ماژول جامع احراز هویت سازمانی (OpenID Connect / OAuth2 SSO)
سازگار با Microsoft Entra ID (Azure AD), Keycloak, Okta و Auth0
دارای کش چندنخی کلیدهای عمومی (JWKS Cache)، ایمن در برابر حملات جعل الگوریتم،
پشتیبانی از چرخش کلیدها (Key Rotation) و همگام‌سازی لحظه‌ای کاربران سازمانی (JIT User Sync).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import OIDC_AUDIENCE, OIDC_ISSUER_URL
from db.models import User

try:
    from sqlalchemy import func
except ImportError:  # pragma: no cover
    func = None

logger = logging.getLogger(__name__)

# Implementation note.
try:
    from jose import jwt, jwk
    from jose.exceptions import (
        ExpiredSignatureError,
        JWTClaimsError,
        JWTError,
        JWKError,
    )
    _HAS_JOSE = True
except ImportError:
    jwt = None
    _HAS_JOSE = False


# ──────────────────────────────────────────────
#  Custom Exceptions
# ──────────────────────────────────────────────

class OIDCError(Exception):
    """خطای پایه سیستم احراز هویت سازمانی"""
    pass


class OIDCConfigError(OIDCError):
    """خطای تنظیمات و ارتباط با سرور Identity Provider"""
    pass


class OIDCTokenExpiredError(OIDCError):
    """خطای انقضای اعتبار زمانی توکن JWT"""
    pass


class OIDCInvalidSignatureError(OIDCError):
    """خطای عدم تطابق امضای دیجیتال یا کلید نامعتبر"""
    pass


class OIDCClaimsValidationError(OIDCError):
    """خطای عدم انطباق فیلدهای استاندارد Issuer, Audience یا Subject"""
    pass


class OIDCValidationError(OIDCError):
    """توکن خالی، ناقص یا از نظر ساختاری نامعتبر است."""
    pass


# ──────────────────────────────────────────────
#  Data Transfer Objects (Claims & User Mapping)
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class OIDCClaims:
    """اطلاعات استخراج‌شده و اعتبارسنجی‌شده از توکن سازمانی"""
    subject: str                               # Implementation note.
    email: Optional[str]                       # Implementation note.
    username: str                              # Implementation note.
    full_name: str                             # Implementation note.
    roles: Set[str] = field(default_factory=set) # Implementation note.
    groups: Set[str] = field(default_factory=set)# Implementation note.
    tenant_id: Optional[str] = None            # Implementation note.
    issued_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    raw_claims: Dict[str, Any] = field(default_factory=dict)

    def has_role(self, role_name: str) -> bool:
        return role_name.upper() in {r.upper() for r in self.roles}

    def has_any_role(self, role_names: Union[List[str], Set[str]]) -> bool:
        normalized = {r.upper() for r in role_names}
        return bool({r.upper() for r in self.roles} & normalized)


# ──────────────────────────────────────────────
#  OIDC Service Implementation
# ──────────────────────────────────────────────

class OIDCService:
    """
    سرویس مدیریت ارتباط با سرورهای هویت سازمانی، اعتبارسنجی امضای JWT و نگاشت دسترسی‌ها
    """

    # Implementation note.
    ALLOWED_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]
    
    # Implementation note.
    JWKS_CACHE_TTL_SECONDS = 12 * 3600
    DISCOVERY_CACHE_TTL_SECONDS = 24 * 3600

    def __init__(
        self,
        issuer_url: Optional[str] = OIDC_ISSUER_URL,
        audience: Optional[str] = OIDC_AUDIENCE,
        client_id: Optional[str] = None,
        clock_skew_leeway_seconds: int = 60,
        request_timeout: int = 15,
    ):
        self.issuer = issuer_url.rstrip("/") if issuer_url else ""
        self.audience = audience or client_id or ""
        self.leeway = clock_skew_leeway_seconds
        self.timeout = request_timeout

        # Implementation note.
        self._discovery_doc: Optional[Dict[str, Any]] = None
        self._discovery_expires_at: float = 0.0

        self._jwks_keys_by_kid: Dict[str, Dict[str, Any]] = {}
        self._jwks_expires_at: float = 0.0

        self._lock = threading.RLock()

        # Implementation note.
        self._http = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        self._http.mount("https://", HTTPAdapter(max_retries=retries))
        self._http.mount("http://", HTTPAdapter(max_retries=retries))

    def is_configured(self) -> bool:
        """بررسی فعال و پیکربندی بودن سرویس SSO/OIDC"""
        return bool(self.issuer and self.audience)

    # Implementation note.

    def get_discovery_config(self, force_refresh: bool = False) -> Dict[str, Any]:
        """دریافت و کش کردن مستندات پیکربندی استاندارد .well-known/openid-configuration"""
        if not self.issuer:
            raise OIDCConfigError("OIDC Issuer URL is not configured.")

        now = time.time()
        with self._lock:
            if not force_refresh and self._discovery_doc and now < self._discovery_expires_at:
                return self._discovery_doc

            discovery_url = f"{self.issuer}/.well-known/openid-configuration"
            try:
                logger.info(f"Fetching OIDC discovery from: {discovery_url}")
                response = self._http.get(discovery_url, timeout=self.timeout)
                response.raise_for_status()
                
                config_data = response.json()
                self._discovery_doc = config_data
                self._discovery_expires_at = now + self.DISCOVERY_CACHE_TTL_SECONDS
                return config_data

            except requests.exceptions.RequestException as exc:
                logger.error(f"Failed to fetch OIDC discovery document: {exc}")
                raise OIDCConfigError(f"Could not connect to Identity Provider: {exc}") from exc

    # Implementation note.

    def get_signing_keys(self, force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        واکشی و کش کردن کلیدهای عمومی سرور هویت (JWKS Keys) بر مبنای Key ID (kid)
        با قابلیت چرخش خودکار کلیدها (Auto Key-Rotation)
        """
        now = time.time()
        with self._lock:
            if not force_refresh and self._jwks_keys_by_kid and now < self._jwks_expires_at:
                return self._jwks_keys_by_kid

            cfg = self.get_discovery_config()
            jwks_uri = cfg.get("jwks_uri")
            if not jwks_uri:
                raise OIDCConfigError("Discovery document does not contain 'jwks_uri'.")

            try:
                logger.info(f"Refreshing JWKS public keys from: {jwks_uri}")
                response = self._http.get(jwks_uri, timeout=self.timeout)
                response.raise_for_status()
                
                jwks_data = response.json()
                raw_keys = jwks_data.get("keys", [])

                new_keys_map = {}
                for k in raw_keys:
                    kid = k.get("kid")
                    if kid:
                        new_keys_map[kid] = k

                self._jwks_keys_by_kid = new_keys_map
                self._jwks_expires_at = now + self.JWKS_CACHE_TTL_SECONDS
                logger.info(f"Cached {len(new_keys_map)} OIDC public signing keys successfully.")
                return new_keys_map

            except requests.exceptions.RequestException as exc:
                logger.error(f"Failed to fetch JWKS keys: {exc}")
                raise OIDCConfigError(f"Could not load public signing keys from IdP: {exc}") from exc

    # Implementation note.

    def verify_token(self, token: str) -> OIDCClaims:
        """
        اعتبارسنجی کامل و امن توکن ارسالی کاربر:
        ۱. بررسی ساختار و استخراج هدر بدون اعتبارسنجی
        ۲. اعتبارسنجی امضای رمزنگاری‌شده بر مبنای کلید عمومی با Kid مشخص
        ۳. بررسی انطباق صادرکننده (Issuer) و مخاطب (Audience)
        ۴. کنترل انقضای زمانی با اعمال خطای مجاز ساعت (Clock Leeway)
        ۵. استخراج و نرمال‌سازی فیلدهای کاربری و نقش‌ها
        """
        if not _HAS_JOSE or jwt is None:
            raise RuntimeError("The 'python-jose' package with cryptography is required for OIDC verification.")

        if not token or not isinstance(token, str):
            raise OIDCValidationError("Bearer token is empty or invalid.")

        clean_token = token.replace("Bearer ", "").strip()

        # Implementation note.
        try:
            unverified_header = jwt.get_unverified_header(clean_token)
        except JWTError as exc:
            raise OIDCValidationError(f"Malformed JWT header: {exc}") from exc

        alg = unverified_header.get("alg")
        kid = unverified_header.get("kid")

        # Implementation note.
        if not alg or alg.upper() not in self.ALLOWED_ALGORITHMS:
            raise OIDCInvalidSignatureError(
                f"Unsupported or forbidden signing algorithm '{alg}'. "
                f"Allowed algorithms: {self.ALLOWED_ALGORITHMS}"
            )

        # Implementation note.
        keys_map = self.get_signing_keys(force_refresh=False)
        target_key = keys_map.get(kid) if kid else None

        if not target_key and kid:
            logger.warning(f"Signing key with kid '{kid}' not in cache. Refreshing JWKS...")
            keys_map = self.get_signing_keys(force_refresh=True)
            target_key = keys_map.get(kid)

        if not target_key:
            # Implementation note.
            if len(keys_map) == 1 and not kid:
                target_key = list(keys_map.values())[0]
            else:
                raise OIDCInvalidSignatureError(f"No matching public signing key found for kid '{kid}'.")

        # Implementation note.
        cfg = self.get_discovery_config()
        valid_issuer = cfg.get("issuer", self.issuer)

        decode_options = {
            "verify_signature": True,
            "verify_aud": bool(self.audience),
            "verify_iat": True,
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iss": True,
            "leeway": self.leeway,
        }

        try:
            payload = jwt.decode(
                clean_token,
                target_key,
                algorithms=[alg],
                audience=self.audience if self.audience else None,
                issuer=valid_issuer,
                options=decode_options,
            )
        except ExpiredSignatureError as exc:
            raise OIDCTokenExpiredError("OIDC Bearer token has expired.") from exc
        except JWTClaimsError as exc:
            raise OIDCClaimsValidationError(f"Token claims validation failed: {exc}") from exc
        except JWTError as exc:
            raise OIDCInvalidSignatureError(f"Signature verification failed: {exc}") from exc

        # Implementation note.
        return self._parse_claims_dto(payload)

    def verify(self, token: str) -> Dict[str, Any]:
        """Backward-compatible dict payload used by the enterprise API."""
        claims = self.verify_token(token)
        mapped_role = self._map_oidc_role_to_pipeagent(claims.roles)
        return {
            "sub": claims.subject,
            "email": claims.email,
            "preferred_username": claims.username,
            "name": claims.full_name,
            "role": mapped_role,
            "pipeagent_role": mapped_role,
            "roles": sorted(claims.roles),
        }

    # Implementation note.

    def _parse_claims_dto(self, payload: Dict[str, Any]) -> OIDCClaims:
        """تبدیل کلیم‌های متنوع ارائه‌دهندگان مختلف (Azure AD, Keycloak, Okta) به ساختار یکپارچه"""
        sub = payload.get("sub", "")
        email = payload.get("email") or payload.get("upn") or payload.get("preferred_username")
        
        # Implementation note.
        username = (
            payload.get("preferred_username")
            or payload.get("upn")
            or payload.get("email")
            or payload.get("name")
            or sub
        )
        if "@" in str(username):
            username = str(username).split("@")[0]  # Implementation note.

        full_name = payload.get("name") or f"{payload.get('given_name', '')} {payload.get('family_name', '')}".strip() or str(username)

        # Implementation note.
        roles: Set[str] = set()
        
        # Implementation note.
        if isinstance(payload.get("roles"), list):
            roles.update(payload["roles"])
            
        # Implementation note.
        realm_access = payload.get("realm_access", {})
        if isinstance(realm_access, dict) and isinstance(realm_access.get("roles"), list):
            roles.update(realm_access["roles"])

        # Implementation note.
        groups: Set[str] = set()
        if isinstance(payload.get("groups"), list):
            groups.update(payload["groups"])

        # Implementation note.
        exp_ts = payload.get("exp")
        iat_ts = payload.get("iat")

        return OIDCClaims(
            subject=sub,
            email=email,
            username=str(username).lower(),
            full_name=full_name,
            roles=roles,
            groups=groups,
            tenant_id=payload.get("tid"),
            issued_at=datetime.fromtimestamp(iat_ts) if iat_ts else None,
            expires_at=datetime.fromtimestamp(exp_ts) if exp_ts else None,
            raw_claims=payload,
        )

    # Implementation note.

    def authenticate_and_sync_user(self, db_session, token: str) -> Tuple[User, OIDCClaims]:
        """
        اعتبارسنجی توکن و همگام‌سازی لحظه‌ای کاربر در جدول User دیتابیس داخلی:
        در صورت عدم وجود کاربر، رکورد جدید به صورت خودکار ایجاد می‌گردد (Just-In-Time Provisioning).
        """
        claims = self.verify_token(token)

        # Implementation note.
        user = None
        if claims.email:
            user = db_session.query(User).filter(func.lower(User.email) == claims.email.lower()).first()

        if not user:
            user = db_session.query(User).filter(func.lower(User.username) == claims.username.lower()).first()

        # Implementation note.
        mapped_role = self._map_oidc_role_to_pipeagent(claims.roles)

        if not user:
            # Implementation note.
            logger.info(f"Auto-provisioning new OIDC enterprise user: '{claims.username}' (Email: {claims.email})")
            user = User(
                username=claims.username,
                email=claims.email,
                full_name=claims.full_name,
                role=mapped_role,
                is_active=True,
                auth_provider="OIDC_SSO",
                created_at=datetime.utcnow(),
            )
            db_session.add(user)
        else:
            # Implementation note.
            if hasattr(user, "full_name") and claims.full_name:
                user.full_name = claims.full_name
            if hasattr(user, "auth_provider"):
                user.auth_provider = "OIDC_SSO"
            if hasattr(user, "last_login_at"):
                user.last_login_at = datetime.utcnow()

        db_session.flush()
        return user, claims

    # Implementation note.

    @staticmethod
    def _map_oidc_role_to_pipeagent(oidc_roles: Set[str]) -> str:
        """نگاشت هوشمند گروه‌ها/نقش‌های اکتیودایرکتوری به دسترسی‌های PipeAgent"""
        normalized_roles = {r.upper() for r in oidc_roles}

        if "PIPEAGENT_SUPERADMIN" in normalized_roles or "ADMIN" in normalized_roles:
            return "SUPER_ADMIN"
        if "PIPEAGENT_QC_MANAGER" in normalized_roles or "QC_LEAD" in normalized_roles:
            return "QC_MANAGER"
        if "PIPEAGENT_QC_INSPECTOR" in normalized_roles or "INSPECTOR" in normalized_roles:
            return "QC_INSPECTOR"
        if "PIPEAGENT_PROJECT_MANAGER" in normalized_roles or "PROJECT_LEAD" in normalized_roles:
            return "PROJECT_MGR"
        if "PIPEAGENT_CLIENT_REP" in normalized_roles or "CLIENT" in normalized_roles:
            return "CLIENT_REP"
        if "PIPEAGENT_STOREKEEPER" in normalized_roles or "WAREHOUSE" in normalized_roles:
            return "STOREKEEPER"

        return "VIEWER"  # Implementation note.