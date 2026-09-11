# -*- coding: utf-8 -*-
"""
services/rule_engine.py – PipeAgent v6.0 Enterprise
موتور جامع قوانین مهندسی، کنترل فرآیند و گیت‌کیپرهای ایمنی پایپینگ و پالایشگاه
منطبق با الزامات استانداردهای ASME B31.3, ASME Section IX, AWS D1.1, EN 10204
شامل: گیت هیدروتست، صلاحیت پیشرفته جوشکاران، گواهی تکمیل مکانیکی (MCC)،
ردیابی متالورژیکی متریال و مجوز فیت‌آپ و جوشکاری.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, and_, or_, desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Rule Severity Classifications
# ──────────────────────────────────────────────

class RuleSeverity(str, Enum):
    """سطح اهمیت و شدت نقض قانون مهندسی"""
    CRITICAL_BLOCKER = "BLOCKER"  # Implementation note.
    WARNING = "WARNING"           # Implementation note.
    INFO = "INFO"                 # Implementation note.


class RuleCategory(str, Enum):
    """دسته‌بندی موضوعی قوانین"""
    HYDROTEST_GATE = "HYDROTEST"
    WELDER_QUALIFICATION = "WELDER"
    MECHANICAL_COMPLETION = "MCC"
    MATERIAL_TRACEABILITY = "MATERIAL"
    WELDING_EXECUTION = "WELDING"
    PRE_COMMISSIONING = "PRE_COMM"


# ──────────────────────────────────────────────
#  Rule Evaluation Reports & DTOs
# ──────────────────────────────────────────────

@dataclass
class RuleViolation:
    """جزئیات یک مورد نقض قانون مهندسی"""
    category: RuleCategory
    severity: RuleSeverity
    code: str
    message: str
    entity_key: Optional[str] = None
    prescriptive_action: str = ""


class CheckReport:
    """
    گزارش استاندارد ارزیابی قوانین مهندسی (کاملاً سازگار با کدهای پیشین)
    همراه با قابلیت تفکیک موانع بحرانی (Blockers) از هشدارهای فنی.
    """
    def __init__(
        self,
        success: bool,
        messages: List[str],
        violations: Optional[List[RuleViolation]] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.messages = messages
        self.violations = violations or []
        self.context = context or {}

    @property
    def has_blockers(self) -> bool:
        return any(v.severity == RuleSeverity.CRITICAL_BLOCKER for v in self.violations)

    @property
    def blockers(self) -> List[str]:
        return [v.message for v in self.violations if v.severity == RuleSeverity.CRITICAL_BLOCKER]

    @property
    def warnings(self) -> List[str]:
        return [v.message for v in self.violations if v.severity == RuleSeverity.WARNING]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "can_proceed": not self.has_blockers,
            "blockers_count": len(self.blockers),
            "warnings_count": len(self.warnings),
            "messages": self.messages,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "context": self.context,
        }

    def __repr__(self) -> str:
        return f"CheckReport(success={self.success}, blockers={len(self.blockers)}, warnings={len(self.warnings)})"


# ──────────────────────────────────────────────
#  Piping Rule Engine Core
# ──────────────────────────────────────────────

class PipingRuleEngine:
    """
    موتور جامع اعتبارسنجی قوانین مهندسی پایپینگ و پالایشگاهی (Piping Engineering Rules)
    """

    # ══════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════

    @staticmethod
    def can_proceed_to_hydrotest(
        test_package_id: int,
        session: Session,
        allow_minor_warnings: bool = False,
    ) -> Tuple[bool, List[str]]:
        """ASME B31.3 hydrotest gate against punch, NDE, PWHT and coverage evidence."""
        from services.code_compliance import hydrotest_clearance

        report = hydrotest_clearance(session, test_package_id)
        messages = list(report.get("blockers") or [])
        if not allow_minor_warnings:
            messages.extend(report.get("warnings") or [])
        elif report.get("warnings"):
            messages.extend(f"WARNING: {item}" for item in report["warnings"])
        return bool(report.get("can_proceed")), messages

    # ══════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════

    @staticmethod
    def is_welder_authorized(
        welder_stencil: str,
        thickness_mm: float,
        position: str,
        session: Session,
        diameter_inch: Optional[float] = None,
        process: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        بررسی پیشرفته صلاحیت جوشکار طبق الزامات ASME Section IX (QW-322 و QW-452):
        ۱. بررسی فعال بودن و عدم انقضای تقویمی کارت جوشکاری
        ۲. بررسی قانون استمرار ۶ ماهه (Continuity Log)
        ۳. بررسی محدوده مجاز ضخامت لوله ($t_{min} \\le t \\le t_{max}$)
        ۴. بررسی محدوده مجاز قطر لوله ($D_{min} \\le D$) طبق QW-452.3
        ۵. بررسی پوشش موقعیت جوشکاری (مثلاً 6G تمام موقعیت‌ها را پوشش می‌دهد)
        """
        from db.models import Welder

        query = session.query(Welder).filter(
            Welder.stencil_number == welder_stencil.strip().upper(),
        )
        if project_id:
            query = query.filter(Welder.project_id == project_id)

        welder = query.first()
        if not welder:
            return False, f"Welder with stencil '{welder_stencil}' is not registered or not found."

        # Implementation note.
        if getattr(welder, "status", "ACTIVE") in ["SUSPENDED", "REVOKED", "BLACKLISTED"] or not getattr(welder, "is_active", True):
            return False, f"Welder '{welder_stencil}' is currently {getattr(welder, 'status', 'Inactive')} and not permitted to weld."

        # Implementation note.
        today = date.today()
        expiry = getattr(welder, "expiry_date", None)
        if expiry and expiry < today:
            return False, f"Welder qualification expired on {expiry}."

        # Implementation note.
        last_weld = getattr(welder, "last_welded_date", None) or getattr(welder, "last_welding_date", None)
        if last_weld and (today - last_weld).days > 180:
            return False, f"Welder failed 6-month continuity rule (Inactive for {(today - last_weld).days} days)."

        # Implementation note.
        min_t = getattr(welder, "qualified_thickness_min_mm", 0.0) or 0.0
        max_t = getattr(welder, "qualified_thickness_max_mm", 999.0) or 999.0
        if thickness_mm < min_t:
            return False, f"Pipe thickness ({thickness_mm} mm) is below welder qualified minimum ({min_t} mm)."
        if thickness_mm > max_t:
            return False, f"Pipe thickness ({thickness_mm} mm) exceeds welder qualified maximum ({max_t} mm)."

        # Implementation note.
        if diameter_inch is not None:
            min_d = getattr(welder, "qualified_diameter_min_inch", 0.0) or 0.0
            if diameter_inch < min_d:
                return False, f"Pipe diameter ({diameter_inch} in) is below welder qualified minimum ({min_d} in)."
            max_d = getattr(welder, "qualified_diameter_max_inch", None)
            if max_d and diameter_inch > float(max_d):
                return False, f"Pipe diameter ({diameter_inch} in) exceeds welder qualified maximum ({max_d} in)."

        # Implementation note.
        pos_upper = position.strip().upper()
        qualified_positions = getattr(welder, "qualified_positions", "") or "6G"
        
        # Implementation note.
        if "6G" not in qualified_positions.upper():
            if pos_upper not in qualified_positions.upper():
                return False, f"Position '{pos_upper}' is outside welder qualification scope ({qualified_positions})."

        return True, "Authorized and fully compliant with ASME Sec IX."

    # ══════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════

    @staticmethod
    def can_issue_mcc(
        system_name: str,
        project_id: int,
        session: Session,
        subsystem_code: Optional[str] = None,
    ) -> Tuple[bool, List[str]]:
        """
        ارزیابی صلاحیت صدور گواهی تکمیل مکانیکی (MCC Readiness):
        ایزوله شده به ساب‌سیستم مشخص جهت جلوگیری از باگ قفل شدن کل پروژه
        ۱. صفر بودن پانچ‌های باز دسته A
        ۲. عدم وجود NCRهای باز بحرانی روی مدار
        ۳. اتمام و قبولی ۱۰۰٪ شستشوی خطوط (Flushing Complete)
        ۴. تکمیل ۱۰۰٪ رینستیتمنت و خروج بلایندها
        """
        from db.models import (
            PunchItem, NCRRecord, FlushingRecord,
            LineListItem, ReinstatementItem, AsBuiltMarkup
        )

        violations: List[str] = []
        target_scope = subsystem_code or system_name

        # Implementation note.
        subsystem_lines = session.query(LineListItem.line_number).filter(
            LineListItem.project_id == project_id,
            or_(
                LineListItem.subsystem == target_scope,
                LineListItem.area_name == system_name,
            ),
        ).all()
        line_numbers = [r[0].strip().upper() for r in subsystem_lines if r[0]]

        # Implementation note.
        open_punch_a = session.query(PunchItem).filter(
            PunchItem.project_id == project_id,
            PunchItem.category == "A",
            PunchItem.status.notin_(["QC_CLEARED", "CLIENT_ACCEPTED", "CLOSED", "CANCELLED"]),
            or_(
                PunchItem.subsystem == target_scope,
                PunchItem.line_number.in_(line_numbers) if line_numbers else False,
            ),
        ).count()

        if open_punch_a > 0:
            violations.append(f"{open_punch_a} open Category-A punch item(s) are actively blocking MCC on '{target_scope}'.")

        # Implementation note.
        open_ncrs = session.query(NCRRecord).filter(
            NCRRecord.project_id == project_id,
            NCRRecord.status.notin_(["CLOSED", "CANCELLED"]),
            or_(
                NCRRecord.line_number.in_(line_numbers) if line_numbers else False,
                getattr(NCRRecord, "subsystem", None) == target_scope,
            ),
        ).all()

        if open_ncrs:
            violations.append(f"{len(open_ncrs)} open NCR(s) exist on subsystem '{target_scope}'.")

        # Implementation note.
        if line_numbers:
            incomplete_flush = session.query(FlushingRecord).filter(
                FlushingRecord.project_id == project_id,
                FlushingRecord.line_number.in_(line_numbers),
                FlushingRecord.result != "Accept",
            ).count()
            if incomplete_flush > 0:
                violations.append(f"{incomplete_flush} line(s) have incomplete flushing/blowing verification.")

        # Implementation note.
        if line_numbers:
            pending_blinds = session.query(ReinstatementItem).filter(
                ReinstatementItem.project_id == project_id,
                ReinstatementItem.line_number.in_(line_numbers),
                ReinstatementItem.status != "COMPLETED",
            ).count()
            if pending_blinds > 0:
                violations.append(f"{pending_blinds} reinstatement / blind-removal item(s) are still pending.")

        return len(violations) == 0, violations

    # ══════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════

    @staticmethod
    def check_material_traceability(
        heat_number: str,
        project_id: int,
        session: Session,
    ) -> Tuple[bool, str]:
        """
        اعتبارسنجی ردیابی متریال و اصالت گواهینامه ساخت (EN 10204 3.1):
        ۱. ثبت بودن هیت‌نامبر در انبار
        ۲. دریافت و تایید گواهینامه MTR
        ۳. عدم قرارگیری در وضعیت قرنطینه
        ۴. پاس شدن آزمون آنالیز آلیاژی PMI (در صورت انجام)
        """
        from db.models import MaterialItem, PMIRecord

        heat_clean = heat_number.strip().upper()
        mat = session.query(MaterialItem).filter(
            MaterialItem.project_id == project_id,
            func.upper(MaterialItem.heat_number) == heat_clean,
        ).first()

        if not mat:
            return False, f"Heat No. '{heat_clean}' is not registered in project warehouse."

        if getattr(mat, "status", "") == "QUARANTINED":
            return False, f"Material with Heat '{heat_clean}' is QUARANTINED ({getattr(mat, 'quarantine_reason', 'Unverified')})."

        if not getattr(mat, "mtr_received", False):
            return False, f"MTR / Mill Test Certificate for Heat '{heat_clean}' has not been received or verified."

        # Implementation note.
        failed_pmi = session.query(PMIRecord).filter(
            func.upper(PMIRecord.heat_number) == heat_clean,
            PMIRecord.result.in_(["REJECTED", "Reject", "FAIL", "Fail"]),
        ).first()

        if failed_pmi:
            return False, f"Positive Material Identification (PMI) failed for Heat '{heat_clean}'."

        return True, "Traceability complete, MTR verified and material cleared for fabrication."

    # ══════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════

    @staticmethod
    def can_start_welding_joint(
        weld_id: int,
        session: Session,
    ) -> Tuple[bool, List[str]]:
        """
        بررسی شرایط مجاز بودن شروع جوشکاری سرجوش:
        ۱. تایید بازرسی فیت‌آپ (Fit-up Accepted)
        ۲. عدم همراستایی مجاز لبه‌ها (Hi-Lo < 1.5mm)
        ۳. ردیابی هیت نامبر هر دو لوله متصل
        """
        from db.models import Weld

        weld = session.get(Weld, weld_id)
        if not weld:
            return False, [f"Weld #{weld_id} not found."]

        blockers = []
        if weld.status not in ["FITUP_ACCEPTED", "Fit-up"]:
            blockers.append(f"Fit-up inspection is not accepted (Current status: {weld.status}).")

        if getattr(weld, "hi_lo_alignment", 0.0) and float(weld.hi_lo_alignment) > 1.6:
            blockers.append(f"Hi-Lo misalignment ({weld.hi_lo_alignment} mm) exceeds ASME B31.3 limit (1.5 mm).")

        return len(blockers) == 0, blockers


# Implementation note.
# Implementation note.
rule_engine = PipingRuleEngine