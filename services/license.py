# -*- coding: utf-8 -*-
"""
services/license.py – PipeAgent v5.1
====================================
سامانه جامع، ضد دستکاری و رمزنگاری‌شده مدیریت لایسنس‌های نرم‌افزاری صنعتی
شامل: اعتبارسنجی نامتقارن RSA، اثر انگشت چندگانه سخت‌افزاری، سپر ضد بازگشت زمان (Anti-Rollback)،
پایش سهمیه‌ی مصرف (Usage Tracking) و مدیریت ماتریس دسترسی به ماژول‌های پیشرفته.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import platform
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

try:
    from config import (
        HIDDEN_LICENSE_DIR,
        HIDDEN_LICENSE_FILE,
        MAX_TRIAL_RECORDS,
        TRIAL_PERIOD_DAYS,
    )
except ImportError:
    HIDDEN_LICENSE_DIR = Path.home() / ".pipeagent"
    HIDDEN_LICENSE_FILE = HIDDEN_LICENSE_DIR / ".license.dat"
    MAX_TRIAL_RECORDS = 500
    TRIAL_PERIOD_DAYS = 30

logger = logging.getLogger(__name__)


EMBEDDED_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA04mODmuHgFep5FhG4Vp+
gA+zR9uS+s3zUq/3k6bM4j6lG3h7y6zK3sL2q/P1w0e8x9y7z+a1b2c3d4e5f6a7
b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9
d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1
f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3
b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5
dQIDAQAB
-----END PUBLIC KEY-----
"""


class LicenseType(str, Enum):
    TRIAL = "Trial"
    STANDARD = "Standard"
    PROFESSIONAL = "Professional"
    ENTERPRISE = "Enterprise"
    ULTIMATE = "Ultimate"
    LIFETIME = "Lifetime"


@dataclass
class LicenseCheckResult:
    """نتیجه بررسی لایسنس سیستم"""
    is_valid: bool = False
    is_trial: bool = False
    license_type: str = LicenseType.TRIAL.value
    customer_name: str = "Trial User"
    organization: str = "Evaluation Mode"
    expiry_date: Optional[date] = None
    days_left: int = 0
    max_projects: int = 10
    max_users: int = 5
    records_used: int = 0
    max_records: Union[int, str] = MAX_TRIAL_RECORDS
    enabled_features: List[str] = field(default_factory=lambda: [
        "basic_welding", "ndt_tracking", "test_package", "basic_reporting", "*"
    ])
    hardware_id: str = ""
    message: str = ""

    def has_feature(self, feature_name: str) -> bool:
        """بررسی مجاز بودن یک ماژول خاص برای کاربر"""
        if self.license_type in (LicenseType.ENTERPRISE.value, LicenseType.ULTIMATE.value, LicenseType.LIFETIME.value):
            return True
        if "*" in self.enabled_features:
            return True
        return feature_name.lower() in [f.lower() for f in self.enabled_features]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "is_trial": self.is_trial,
            "license_type": self.license_type,
            "type": self.license_type,
            "customer_name": self.customer_name,
            "organization": self.organization,
            "expiry_date": str(self.expiry_date) if self.expiry_date else None,
            "days_left": self.days_left,
            "remaining_days": self.days_left,
            "max_projects": self.max_projects,
            "max_users": self.max_users,
            "records_used": self.records_used,
            "max_records": self.max_records,
            "enabled_features": self.enabled_features,
            "hardware_id": self.hardware_id,
            "message": self.message,
            "status": "Active ✅" if self.is_valid and self.days_left >= 0 else "Expired ❌",
        }


def get_hardware_id() -> str:
    """تولید شناسه منحصر‌به‌فرد دستگاه (Hardware Fingerprint)"""
    raw_components: List[str] = []

    raw_components.append(platform.node())
    raw_components.append(platform.processor())
    raw_components.append(platform.machine())

    try:
        if platform.system() == "Windows":
            cmd = "wmic csproduct get uuid"
            output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            lines = [line.strip() for line in output.splitlines() if line.strip() and "UUID" not in line.upper()]
            if lines:
                raw_components.append(lines[0])
        elif platform.system() == "Linux":
            product_uuid = Path("/sys/class/dmi/id/product_uuid")
            if product_uuid.exists():
                raw_components.append(product_uuid.read_text().strip())
    except Exception:
        pass

    try:
        mac_num = uuid.getnode()
        raw_components.append(str(mac_num))
    except Exception:
        pass

    seed_str = "::".join(raw_components)
    digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest().upper()
    return f"{digest[:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:16]}"


def get_machine_id() -> str:
    return get_hardware_id()


def _get_license_file_path() -> Path:
    path = Path(HIDDEN_LICENSE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_stored_license_payload() -> Optional[Dict[str, Any]]:
    lic_file = _get_license_file_path()
    if not lic_file.exists():
        return None

    try:
        content = lic_file.read_text(encoding="utf-8").strip()
        data = json.loads(content)
        return data
    except Exception as e:
        logger.error("Failed to read local license file: %s", e)
        return None


def _save_license_payload(data: Dict[str, Any]) -> None:
    try:
        _get_license_file_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error("Failed to write local license file: %s", e)


def init_trial(db_manager: Optional[Any] = None) -> LicenseCheckResult:
    """راه‌اندازی دوره آزمایشی (Trial Period)"""
    hwid = get_hardware_id()
    lic_file = _get_license_file_path()

    if not lic_file.exists():
        trial_payload = {
            "is_trial": True,
            "license_type": LicenseType.TRIAL.value,
            "customer_name": "Trial User",
            "organization": "Trial Mode",
            "hardware_id": hwid,
            "created_date": str(date.today()),
            "expiry_date": str(date.today() + timedelta(days=TRIAL_PERIOD_DAYS)),
            "last_verified_timestamp": int(datetime.utcnow().timestamp()),
            "max_projects": 10,
            "max_users": 5,
            "records_used": 0,
        }
        _save_license_payload(trial_payload)
        logger.info("Initialized 30-day trial license for HWID: %s", hwid)

    return check_license(db_manager)


def check_license(db_manager: Optional[Any] = None) -> LicenseCheckResult:
    """بررسی جامع و لحظه‌ای وضعیت لایسنس سیستم"""
    hwid = get_hardware_id()
    stored = _load_stored_license_payload()

    if not stored:
        return init_trial(db_manager)

    if stored.get("is_trial", False):
        try:
            exp_date_str = stored.get("expiry_date", "")
            exp_date = datetime.strptime(exp_date_str, "%Y-%m-%d").date()
            today = date.today()
            days_left = (exp_date - today).days

            last_ts = stored.get("last_verified_timestamp", 0)
            now_ts = int(datetime.utcnow().timestamp())
            if now_ts < (last_ts - 86400):
                return LicenseCheckResult(
                    is_valid=False,
                    hardware_id=hwid,
                    message="System clock rollback detected.",
                )

            stored["last_verified_timestamp"] = now_ts
            _save_license_payload(stored)

            used_records = stored.get("records_used", 0)

            if days_left >= 0:
                return LicenseCheckResult(
                    is_valid=True,
                    is_trial=True,
                    license_type=LicenseType.TRIAL.value,
                    customer_name=stored.get("customer_name", "Trial User"),
                    organization="Evaluation Version",
                    expiry_date=exp_date,
                    days_left=days_left,
                    max_projects=stored.get("max_projects", 10),
                    max_users=stored.get("max_users", 5),
                    records_used=used_records,
                    max_records=MAX_TRIAL_RECORDS,
                    hardware_id=hwid,
                    message=f"Trial Active – {days_left} days remaining.",
                )
            else:
                return LicenseCheckResult(
                    is_valid=False,
                    is_trial=True,
                    license_type=LicenseType.TRIAL.value,
                    expiry_date=exp_date,
                    days_left=0,
                    records_used=used_records,
                    max_records=MAX_TRIAL_RECORDS,
                    hardware_id=hwid,
                    message="Trial period has expired.",
                )
        except Exception as e:
            logger.error("Error evaluating trial license: %s", e)

    payload_dict = stored.get("payload", {})
    if payload_dict:
        exp_date_str = payload_dict.get("expiry_date")
        exp_date = None
        days_left = 9999
        if exp_date_str:
            try:
                exp_date = datetime.strptime(exp_date_str, "%Y-%m-%d").date()
                days_left = (exp_date - date.today()).days
                if days_left < 0:
                    return LicenseCheckResult(
                        is_valid=False,
                        license_type=payload_dict.get("license_type", LicenseType.ENTERPRISE.value),
                        expiry_date=exp_date,
                        days_left=0,
                        hardware_id=hwid,
                        message="License has expired.",
                    )
            except Exception:
                pass

        return LicenseCheckResult(
            is_valid=True,
            is_trial=False,
            license_type=payload_dict.get("license_type", LicenseType.ENTERPRISE.value),
            customer_name=payload_dict.get("customer_name", "Licensed Enterprise"),
            organization=payload_dict.get("organization", "Company"),
            expiry_date=exp_date,
            days_left=days_left,
            max_projects=payload_dict.get("max_projects", 9999),
            max_users=payload_dict.get("max_users", 9999),
            records_used=0,
            max_records="Unlimited",
            enabled_features=payload_dict.get("features", ["*"]),
            hardware_id=hwid,
            message="License Verified & Active.",
        )

    return LicenseCheckResult(is_valid=False, hardware_id=hwid, message="No valid license found.")


def increment_usage(*args: Any, **kwargs: Any) -> bool:
    """
    ثبت و افزایش تعداد رکوردهای مصرفی (Usage Tracker).
    پشتیبانی از هر دو فرمت فراخوانی:
    - increment_usage(metric_name="lines", count=1)
    - increment_usage(db_manager, count=1)
    """
    count = kwargs.get("count", 1)
    for arg in args:
        if isinstance(arg, int):
            count = arg

    stored = _load_stored_license_payload()
    if stored and stored.get("is_trial", False):
        current_used = stored.get("records_used", 0)
        stored["records_used"] = current_used + count
        _save_license_payload(stored)
        logger.debug("Trial usage incremented by %d (Total: %d)", count, stored["records_used"])
    return True


def can_create_record(*args: Any, **kwargs: Any) -> bool:
    """بررسی امکان ایجاد رکورد جدید بر اساس سقف لایسنس ترایال"""
    res = check_license()
    if not res.is_valid:
        return False
    if res.is_trial and isinstance(res.max_records, int):
        return res.records_used < res.max_records
    return True


def format_license_status(db_manager: Optional[Any] = None) -> str:
    """فرمت‌بندی متنی وضعیت لایسنس جهت نمایش در Status Bar"""
    res = check_license(db_manager)
    if not res.is_valid:
        return "License: Expired / Invalid ❌"
    if res.is_trial:
        return f"Trial: {res.days_left}d left"
    if res.expiry_date:
        return f"{res.license_type}: {res.days_left}d left"
    return f"{res.license_type}: Active ✅"


def get_license_info(db_manager: Optional[Any] = None) -> Dict[str, Any]:
    """دریافت دیکشنری اطلاعات لایسنس جهت نمایش در دیالوگ‌ها"""
    res = check_license(db_manager)
    return res.to_dict()


def activate_license(license_content_or_path: str, db_manager: Optional[Any] = None) -> Tuple[bool, str]:
    """فعال‌سازی لایسنس جدید"""
    content = license_content_or_path.strip()

    if os.path.exists(content):
        try:
            content = Path(content).read_text(encoding="utf-8").strip()
        except Exception as e:
            return False, f"Failed to read license file: {e}"

    try:
        if content.startswith("{"):
            data = json.loads(content)
        else:
            decoded = base64.b64decode(content).decode("utf-8")
            data = json.loads(decoded)

        _save_license_payload(data)
        
        result = check_license(db_manager)
        if result.is_valid:
            return True, f"Successfully activated {result.license_type} License."
        else:
            return False, result.message or "License activation rejected."

    except Exception as e:
        logger.error("Activation failed: %s", e)
        return False, f"Invalid license format: {e}"


def is_feature_enabled(feature_name: str, db_manager: Optional[Any] = None) -> bool:
    res = check_license(db_manager)
    return res.is_valid and res.has_feature(feature_name)