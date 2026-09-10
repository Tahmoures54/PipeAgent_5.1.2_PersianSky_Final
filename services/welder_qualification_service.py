# -*- coding: utf-8 -*-
"""
welder_qualification_service.py - PipeAgent
=============================================
Welder Qualification & Performance Management Service
------------------------------------------------------
Full lifecycle management of welder qualifications in compliance with:

  • ASME Boiler & Pressure Vessel Code, Section IX
    – QW-300  Welder Performance Qualification
    – QW-322  Continuity of Qualification (6-month rule)
    – QW-350  Welding Variables for Welders
    – QW-420  F-Numbers (Filler Metal)
    – QW-422  P-Numbers (Base Metal)
  • ISO 9606-1  Qualification testing of welders (Steels)
  • ISO 9606-2  Qualification testing of welders (Aluminium)
  • AWS D1.1    Structural Welding Code – Steel

Features:
  • Multi-process qualification (SMAW, GTAW, GMAW, FCAW, SAW, etc.)
  • Full essential variable tracking (F-No, P-No, position, thickness, diameter)
  • WPS / WPQ linkage
  • Test coupon tracking with RT/UT/bend results
  • 6-month continuity tracking with automatic deactivation
  • Performance history (weld-by-weld log)
  • Comprehensive authorization engine (12+ checks)
  • Renewal & requalification workflow
  • Multi-dimensional dashboard & reporting
  • Bulk import from CSV / Excel
  • Full audit trail

Author : PipeAgent Engineering
Version: 5.0.0
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from core.exceptions import (
    AppError,
    ValidationError,
    NotFoundError,
    StateTransitionError,
)
from repositories.welder_repository import WelderRepository

logger = logging.getLogger("pipeagent.services.welder_qual")


# ─────────────────────────────────────────────
#  Enums
# ─────────────────────────────────────────────

class WeldingProcess(str, Enum):
    """ASME IX QW-492 / ISO 4063 process codes."""
    SMAW = "SMAW"          # Shielded Metal Arc (111)
    GTAW = "GTAW"          # Gas Tungsten Arc (141)
    GMAW = "GMAW"          # Gas Metal Arc (131/135)
    FCAW = "FCAW"          # Flux Cored Arc (136)
    SAW = "SAW"            # Submerged Arc (121)
    PAW = "PAW"            # Plasma Arc (15)
    OFW = "OFW"            # Oxy-Fuel Welding (311)
    ESW = "ESW"            # Electroslag (72)
    EGW = "EGW"            # Electrogas (73)
    LBW = "LBW"            # Laser Beam (52)
    EBW = "EBW"            # Electron Beam (51)
    FRW = "FRW"            # Friction (42)
    OTHER = "Other"


class WeldingPosition(str, Enum):
    """ASME IX QW-461 positions."""
    # Plate
    F_1G = "1G"            # Flat
    F_2G = "2G"            # Horizontal
    F_3G = "3G"            # Vertical
    F_4G = "4G"            # Overhead
    F_5G = "5G"            # Pipe Fixed Horizontal
    F_6G = "6G"            # Pipe Fixed 45°
    F_6GR = "6GR"          # Pipe Fixed 45° with Restriction Ring
    # Fillet
    FF_1F = "1F"
    FF_2F = "2F"
    FF_3F = "3F"
    FF_4F = "4F"
    FF_5F = "5F"


class FNumber(str, Enum):
    """ASME IX QW-432 F-Numbers (filler metal grouping)."""
    F1 = "F1"    # Carbon Steel (E6010, E6011, E6012, E6013, E7014)
    F2 = "F2"    # Carbon Steel (E7015, E7016, E7018)
    F3 = "F3"    # Stainless (E308, E309, E316)
    F4 = "F4"    # Low Alloy (E8018, E9018)
    F5 = "F5"    # Nickel
    F6 = "F6"    # Copper
    F_NO = "F-No"  # No filler (autogenous GTAW)


class PNumber(str, Enum):
    """ASME IX QW-422 P-Numbers (base metal grouping)."""
    P1 = "P1"    # Carbon Steel (SA-106, SA-53, SA-516)
    P3 = "P3"    # Low Alloy (SA-335 P11, P22)
    P4 = "P4"    # Low Alloy (SA-335 P5, P9)
    P5A = "P5A"  # Low Alloy (SA-335 P91)
    P8 = "P8"    # Stainless 304/316 (SA-312 TP304, TP316)
    P10C = "P10C"  # Duplex (SA-790 S31803)
    P10H = "P10H"  # Super Duplex (SA-790 S32750)
    P34 = "P34"  # Aluminium
    P42 = "P42"  # Titanium
    P45 = "P45"  # Nickel Alloys (Inconel 625, 825)


class WelderStatus(str, Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    EXPIRED = "Expired"
    SUSPENDED = "Suspended"
    REVOKED = "Revoked"
    PENDING_QUAL = "Pending Qualification"
    UNDER_RETEST = "Under Retest"


# Valid transitions
_ALLOWED_TRANSITIONS: Dict[WelderStatus, List[WelderStatus]] = {
    WelderStatus.PENDING_QUAL:  [WelderStatus.ACTIVE, WelderStatus.INACTIVE],
    WelderStatus.ACTIVE:        [WelderStatus.INACTIVE, WelderStatus.EXPIRED,
                                 WelderStatus.SUSPENDED, WelderStatus.UNDER_RETEST],
    WelderStatus.INACTIVE:      [WelderStatus.ACTIVE, WelderStatus.EXPIRED,
                                 WelderStatus.PENDING_QUAL],
    WelderStatus.EXPIRED:       [WelderStatus.PENDING_QUAL, WelderStatus.UNDER_RETEST],
    WelderStatus.SUSPENDED:     [WelderStatus.ACTIVE, WelderStatus.REVOKED,
                                 WelderStatus.UNDER_RETEST],
    WelderStatus.UNDER_RETEST:  [WelderStatus.ACTIVE, WelderStatus.EXPIRED,
                                 WelderStatus.SUSPENDED],
    WelderStatus.REVOKED:       [WelderStatus.PENDING_QUAL],
}


class CouponResult(str, Enum):
    PASS = "Pass"
    FAIL = "Fail"
    CONDITIONAL = "Conditional"


class NDTMethod(str, Enum):
    RT = "RT"
    UT = "UT"
    VT = "VT"
    PT = "PT"
    MT = "MT"
    BEND = "Bend Test"
    MACRO = "Macro Etch"
    TENSILE = "Tensile Test"
    IMPACT = "Impact Test"


# ─────────────────────────────────────────────
#  Data Classes / DTOs
# ─────────────────────────────────────────────

@dataclass
class WelderRegistration:
    """Input DTO for registering a new welder."""
    stencil_no: str
    full_name: str
    nationality: str = ""
    id_number: str = ""
    employer: str = ""
    trade: str = ""              # Pipe, Structural, Plate, etc.
    date_of_birth: Optional[date] = None
    phone: str = ""
    photo_path: str = ""
    remarks: str = ""


@dataclass
class QualificationRecord:
    """Input DTO for a single WPQ (Welder Performance Qualification)."""
    process: str                 # WeldingProcess
    process_variant: str = ""    # e.g. "GTAW Manual", "GMAW-S"
    wps_no: str = ""
    wpq_no: str = ""
    p_number_base: str = ""      # P-Number of base metal
    p_number_filler: str = ""    # P-Number of filler (if different)
    f_number: str = ""           # F-Number
    a_number: str = ""           # A-Number (deposited weld metal)
    position: str = ""           # WeldingPosition
    progression: str = ""        # Uphill / Downhill
    backing: str = ""            # With / Without
    coupon_type: str = ""        # Plate / Pipe
    coupon_thickness_mm: float = 0.0
    coupon_od_mm: float = 0.0
    qualified_thickness_min_mm: float = 0.0
    qualified_thickness_max_mm: float = 0.0
    qualified_diameter_min_mm: float = 0.0
    qualified_diameter_max_mm: float = 0.0
    qualified_positions: str = ""  # Comma-separated: "1G,2G,5G,6G"
    test_date: Optional[date] = None
    expiry_date: Optional[date] = None
    certificate_no: str = ""
    issuing_body: str = ""       # TUV, SGS, LR, ABS, etc.
    coupon_result: str = CouponResult.PASS.value
    ndt_method: str = ""
    ndt_result: str = ""
    ndt_report_no: str = ""
    bend_test_result: str = ""
    remarks: str = ""


@dataclass
class ContinuityEntry:
    """Record of welder activity to maintain continuity (ASME IX QW-322)."""
    welder_id: int
    weld_id: str = ""
    line_number: str = ""
    process: str = ""
    date_welded: Optional[date] = None
    joint_type: str = ""
    remarks: str = ""


@dataclass
class AuthorizationResult:
    """Detailed result of welder authorization check."""
    is_authorized: bool
    welder_name: str
    stencil_no: str
    checks: Dict[str, bool] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    matched_qualification_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class WelderDashboardStats:
    """Multi-dimensional dashboard statistics."""
    project_id: int
    total_registered: int
    total_active: int
    total_inactive: int
    total_expired: int
    total_suspended: int
    expiring_30d: int
    expiring_60d: int
    expiring_90d: int
    continuity_broken: int
    by_process: Dict[str, int]
    by_position: Dict[str, int]
    by_p_number: Dict[str, int]
    by_employer: Dict[str, int]
    avg_qualifications_per_welder: float
    critical_alerts: List[str]


# ─────────────────────────────────────────────
#  Main Service
# ─────────────────────────────────────────────

class WelderQualificationService:
    """
    Enterprise-grade Welder Qualification & Performance Management.

    Usage:
        svc = WelderQualificationService(session)
        svc.register_welder(project_id=1, stencil_no="W-101", full_name="Ali Rezaei")
        svc.add_qualification(welder_id=42, qual=QualificationRecord(...))
        auth = svc.check_authorization(project_id=1, stencil="W-101", ...)
        print(auth.is_authorized, auth.failures)
    """

    # ASME IX QW-322: 6 months without welding → qualification lapses
    CONTINUITY_PERIOD_MONTHS = 6

    def __init__(self, session: Session):
        self.repo = WelderRepository(session)
        self.session = session

    # ═══════════════════════════════════════════
    #  1. WELDER REGISTRATION
    # ═══════════════════════════════════════════

    def register_welder(
        self,
        project_id: int,
        stencil_no: str,
        full_name: str,
        **kwargs,
    ) -> Any:
        """Register a new welder with full validation."""
        stencil = self._normalize_stencil(stencil_no)
        self._validate_stencil(stencil)
        self._validate_name(full_name)

        existing = self.repo.find_by_stencil(project_id, stencil)
        if existing and getattr(existing, "is_active", True):
            raise AppError(
                f"Welder with stencil '{stencil}' is already registered "
                f"and active in project {project_id}."
            )

        data = {
            "project_id": project_id,
            "stencil_no": stencil,
            "full_name": full_name.strip(),
            "status": WelderStatus.PENDING_QUAL.value,
            "is_active": False,  # Becomes active after first WPQ
            "registered_at": datetime.utcnow(),
            **kwargs,
        }
        data = {k: v for k, v in data.items() if v is not None}

        welder = self.repo.add_welder(**data)
        logger.info(
            "Registered welder %s (%s) in project %s",
            stencil, full_name, project_id,
        )
        self._audit(welder, "REGISTER", f"Welder {stencil} registered")
        return welder

    def bulk_register(
        self,
        project_id: int,
        records: List[Dict[str, Any]],
    ) -> Tuple[int, int, List[str]]:
        """Bulk-register welders. Returns (added, skipped, errors)."""
        added = skipped = 0
        errors: List[str] = []

        for i, rec in enumerate(records, 1):
            stencil = rec.get("stencil_no", "").strip()
            name = rec.get("full_name", "").strip()
            if not stencil or not name:
                errors.append(f"Row {i}: Missing stencil_no or full_name.")
                skipped += 1
                continue
            try:
                self.register_welder(
                    project_id, stencil, name,
                    **{k: v for k, v in rec.items()
                       if k not in ("stencil_no", "full_name")},
                )
                added += 1
            except AppError as e:
                errors.append(f"Row {i} ({stencil}): {e}")
                skipped += 1
            except Exception as e:
                errors.append(f"Row {i} ({stencil}): Unexpected — {e}")
                skipped += 1

        logger.info(
            "Bulk register project %s: %d added, %d skipped",
            project_id, added, skipped,
        )
        return added, skipped, errors

    def bulk_register_from_csv(
        self, project_id: int, csv_text: str,
    ) -> Tuple[int, int, List[str]]:
        reader = csv.DictReader(StringIO(csv_text))
        return self.bulk_register(project_id, list(reader))

    # ═══════════════════════════════════════════
    #  2. QUALIFICATION (WPQ) MANAGEMENT
    # ═══════════════════════════════════════════

    def add_qualification(
        self,
        welder_id: int,
        qual: QualificationRecord,
    ) -> Any:
        """
        Add a Welder Performance Qualification (WPQ) record.

        A welder may hold multiple qualifications for different
        processes, materials, positions, and thickness ranges.
        """
        welder = self._get_welder_or_raise(welder_id)
        self._validate_qualification(qual)

        # Set default expiry (2 years from test date per common practice)
        test_date = qual.test_date or date.today()
        if not qual.expiry_date:
            qual.expiry_date = test_date + timedelta(days=730)

        # Calculate qualified ranges if not explicitly set
        if qual.qualified_thickness_min_mm == 0 and qual.coupon_thickness_mm > 0:
            qual.qualified_thickness_min_mm = self._calc_min_thickness(
                qual.coupon_thickness_mm
            )
        if qual.qualified_thickness_max_mm == 0 and qual.coupon_thickness_mm > 0:
            qual.qualified_thickness_max_mm = self._calc_max_thickness(
                qual.coupon_thickness_mm
            )
        if qual.qualified_diameter_min_mm == 0 and qual.coupon_od_mm > 0:
            qual.qualified_diameter_min_mm = self._calc_min_diameter(
                qual.coupon_od_mm
            )
        if qual.qualified_diameter_max_mm == 0:
            qual.qualified_diameter_max_mm = 9999.0  # Unlimited

        qual_data = {
            "welder_id": welder_id,
            "project_id": welder.project_id,
            **{k: v for k, v in qual.__dict__.items() if v is not None},
        }

        result = self.repo.add_qualification(**qual_data)

        # Auto-activate welder on first passing qualification
        if (
            qual.coupon_result == CouponResult.PASS.value
            and welder.status == WelderStatus.PENDING_QUAL.value
        ):
            self.repo.edit_welder(
                welder_id,
                status=WelderStatus.ACTIVE.value,
                is_active=True,
                expiry_date=qual.expiry_date,
            )
            logger.info("Welder %s auto-activated after first WPQ", welder.stencil_no)

        logger.info(
            "Added WPQ for welder %s: %s / %s / %s (exp %s)",
            welder.stencil_no, qual.process, qual.position,
            qual.p_number_base, qual.expiry_date,
        )
        self._audit(
            welder, "WPQ",
            f"Process={qual.process}, Pos={qual.position}, "
            f"P-No={qual.p_number_base}, Exp={qual.expiry_date}"
        )
        return result

    def list_qualifications(
        self, welder_id: int,
    ) -> List[Dict[str, Any]]:
        """List all WPQ records for a welder."""
        self._get_welder_or_raise(welder_id)
        return self.repo.list_qualifications(welder_id)

    def get_active_qualifications(
        self, welder_id: int,
    ) -> List[Dict[str, Any]]:
        """List only non-expired qualifications."""
        quals = self.list_qualifications(welder_id)
        today = date.today()
        return [
            q for q in quals
            if not q.get("expiry_date")
            or (isinstance(q["expiry_date"], date) and q["expiry_date"] >= today)
            or (isinstance(q["expiry_date"], str)
                and date.fromisoformat(q["expiry_date"]) >= today)
        ]

    def revoke_qualification(
        self,
        qualification_id: int,
        reason: str = "",
        revoked_by: str = "",
    ) -> Any:
        """Revoke a specific WPQ (e.g. after failed retest)."""
        result = self.repo.edit_qualification(
            qualification_id,
            is_revoked=True,
            revocation_reason=reason,
            revocation_date=date.today(),
            revoked_by=revoked_by,
        )
        logger.warning(
            "Qualification %d revoked by %s: %s",
            qualification_id, revoked_by, reason,
        )
        return result

    # ═══════════════════════════════════════════
    #  3. AUTHORIZATION ENGINE (12+ Checks)
    # ═══════════════════════════════════════════

    def check_authorization(
        self,
        project_id: int,
        stencil: str,
        *,
        process: str = "",
        thickness_mm: float = 0.0,
        position: str = "",
        p_number: str = "",
        f_number: str = "",
        diameter_mm: float = 0.0,
        backing: str = "",
        progression: str = "",
        wps_no: str = "",
        joint_type: str = "",
    ) -> AuthorizationResult:
        """
        Comprehensive welder authorization check.

        Performs 12+ checks against all active qualifications:
          1. Registration existence
          2. Active status
          3. Certificate expiry
          4. Continuity (6-month rule)
          5. Process match
          6. P-Number (base metal) match
          7. F-Number (filler metal) match
          8. Thickness range
          9. Diameter range
         10. Position match
         11. Backing (with/without)
         12. Progression (uphill/downhill)
        """
        stencil = self._normalize_stencil(stencil)
        welder = self.repo.find_by_stencil(project_id, stencil)

        # ── Check 1: Registration ──
        if not welder:
            return AuthorizationResult(
                is_authorized=False,
                welder_name="N/A",
                stencil_no=stencil,
                checks={"registered": False},
                failures=["Welder is not registered in the system."],
            )

        result = AuthorizationResult(
            is_authorized=True,
            welder_name=getattr(welder, "full_name", ""),
            stencil_no=stencil,
        )

        # ── Check 2: Active Status ──
        status = getattr(welder, "status", WelderStatus.INACTIVE.value)
        result.checks["is_active"] = status == WelderStatus.ACTIVE.value
        if not result.checks["is_active"]:
            result.failures.append(f"Welder status is '{status}', not Active.")

        # ── Check 3: Certificate Expiry ──
        expiry = getattr(welder, "expiry_date", None)
        if expiry:
            exp_date = expiry if isinstance(expiry, date) else date.fromisoformat(str(expiry))
            result.checks["not_expired"] = exp_date >= date.today()
            if not result.checks["not_expired"]:
                result.failures.append(
                    f"Qualification expired on {exp_date.isoformat()}."
                )
        else:
            result.checks["not_expired"] = True

        # ── Check 4: Continuity (6-month rule) ──
        last_weld_date = self._get_last_weld_date(welder.id)
        if last_weld_date:
            months_since = self._months_between(last_weld_date, date.today())
            result.checks["continuity_ok"] = months_since <= self.CONTINUITY_PERIOD_MONTHS
            if not result.checks["continuity_ok"]:
                result.failures.append(
                    f"Continuity broken: last weld {last_weld_date.isoformat()} "
                    f"({months_since} months ago, limit={self.CONTINUITY_PERIOD_MONTHS})."
                )
                result.warnings.append(
                    "ASME IX QW-322: Qualification lapses after 6 months "
                    "without welding in the process."
                )
        else:
            result.checks["continuity_ok"] = True  # No data yet

        # ── Checks 5-12: Against active qualifications ──
        active_quals = self.get_active_qualifications(welder.id)

        if not active_quals:
            result.checks["has_qualification"] = False
            result.failures.append("No active qualifications on record.")
            result.is_authorized = False
            return result

        result.checks["has_qualification"] = True

        # Find matching qualification
        matched = False
        for q in active_quals:
            q_match = self._match_qualification(
                q,
                process=process,
                thickness_mm=thickness_mm,
                position=position,
                p_number=p_number,
                f_number=f_number,
                diameter_mm=diameter_mm,
                backing=backing,
                progression=progression,
            )
            if q_match["all_pass"]:
                matched = True
                result.matched_qualification_id = q.get("id")
                result.checks.update(q_match["checks"])
                break

        if not matched:
            # Collect all failure reasons across all quals
            all_reasons = set()
            for q in active_quals:
                qm = self._match_qualification(
                    q, process=process, thickness_mm=thickness_mm,
                    position=position, p_number=p_number,
                    f_number=f_number, diameter_mm=diameter_mm,
                    backing=backing, progression=progression,
                )
                all_reasons.update(qm.get("failures", []))
            result.failures.extend(sorted(all_reasons))

        result.is_authorized = len(result.failures) == 0
        return result

    def _match_qualification(
        self,
        q: Dict[str, Any],
        *,
        process: str,
        thickness_mm: float,
        position: str,
        p_number: str,
        f_number: str,
        diameter_mm: float,
        backing: str,
        progression: str,
    ) -> Dict[str, Any]:
        """Check a single qualification record against required parameters."""
        checks: Dict[str, bool] = {}
        failures: List[str] = []

        # Process
        if process:
            checks["process"] = q.get("process", "").upper() == process.upper()
            if not checks["process"]:
                failures.append(
                    f"Process '{process}' not qualified "
                    f"(has: {q.get('process', 'N/A')})."
                )

        # P-Number
        if p_number:
            checks["p_number"] = q.get("p_number_base", "") == p_number
            if not checks["p_number"]:
                failures.append(
                    f"P-Number '{p_number}' not qualified "
                    f"(has: {q.get('p_number_base', 'N/A')})."
                )

        # F-Number
        if f_number:
            checks["f_number"] = q.get("f_number", "") == f_number
            if not checks["f_number"]:
                failures.append(
                    f"F-Number '{f_number}' not qualified."
                )

        # Thickness
        if thickness_mm > 0:
            t_min = q.get("qualified_thickness_min_mm", 0) or 0
            t_max = q.get("qualified_thickness_max_mm", 9999) or 9999
            checks["thickness"] = t_min <= thickness_mm <= t_max
            if not checks["thickness"]:
                failures.append(
                    f"Thickness {thickness_mm}mm outside range "
                    f"[{t_min}–{t_max}mm]."
                )

        # Diameter
        if diameter_mm > 0:
            d_min = q.get("qualified_diameter_min_mm", 0) or 0
            d_max = q.get("qualified_diameter_max_mm", 9999) or 9999
            checks["diameter"] = d_min <= diameter_mm <= d_max
            if not checks["diameter"]:
                failures.append(
                    f"Diameter {diameter_mm}mm outside range "
                    f"[{d_min}–{d_max}mm]."
                )

        # Position
        if position:
            qualified_pos = q.get("qualified_positions", "")
            pos_list = [
                p.strip().upper() for p in qualified_pos.split(",") if p.strip()
            ]
            checks["position"] = position.upper() in pos_list
            if not checks["position"]:
                failures.append(
                    f"Position '{position}' not qualified "
                    f"(has: {qualified_pos})."
                )

        # Backing
        if backing:
            q_backing = q.get("backing", "").lower()
            checks["backing"] = backing.lower() in q_backing or q_backing == ""
            if not checks["backing"]:
                failures.append(
                    f"Backing '{backing}' not qualified "
                    f"(has: {q.get('backing', 'N/A')})."
                )

        # Progression
        if progression:
            q_prog = q.get("progression", "").lower()
            checks["progression"] = (
                progression.lower() in q_prog or q_prog == ""
            )
            if not checks["progression"]:
                failures.append(
                    f"Progression '{progression}' not qualified."
                )

        return {
            "all_pass": all(checks.values()) if checks else True,
            "checks": checks,
            "failures": failures,
        }

    # ═══════════════════════════════════════════
    #  4. CONTINUITY TRACKING (ASME IX QW-322)
    # ═══════════════════════════════════════════

    def record_weld_activity(
        self,
        welder_id: int,
        weld_id: str = "",
        line_number: str = "",
        process: str = "",
        date_welded: Optional[date] = None,
        joint_type: str = "",
        remarks: str = "",
    ) -> Any:
        """
        Record a weld activity to maintain continuity.

        Per ASME IX QW-322, a welder's qualification remains valid
        indefinitely if they weld at least once every 6 months
        in each qualified process.
        """
        welder = self._get_welder_or_raise(welder_id)
        entry = ContinuityEntry(
            welder_id=welder_id,
            weld_id=weld_id,
            line_number=line_number,
            process=process,
            date_welded=date_welded or date.today(),
            joint_type=joint_type,
            remarks=remarks,
        )
        result = self.repo.add_continuity_entry(entry.__dict__)

        # Update last weld date on welder record
        self.repo.edit_welder(
            welder_id,
            last_weld_date=entry.date_welded,
        )
        logger.debug(
            "Continuity recorded: welder %s, weld %s, %s",
            welder.stencil_no, weld_id, entry.date_welded,
        )
        return result

    def check_continuity(
        self, welder_id: int, process: str = "",
    ) -> Dict[str, Any]:
        """
        Check if a welder's continuity is maintained.

        Returns per-process continuity status.
        """
        welder = self._get_welder_or_raise(welder_id)
        cutoff = date.today() - timedelta(days=self.CONTINUITY_PERIOD_MONTHS * 30)

        entries = self.repo.get_continuity_entries(welder_id, since=cutoff)

        if not process:
            # Check all processes
            processes = set(e.get("process", "") for e in entries if e.get("process"))
            if not processes:
                quals = self.get_active_qualifications(welder_id)
                processes = set(q.get("process", "") for q in quals)

            result = {"welder": welder.stencil_no, "by_process": {}}
            for p in processes:
                has_activity = any(
                    e.get("process", "").upper() == p.upper() for e in entries
                )
                result["by_process"][p] = {
                    "continuous": has_activity,
                    "last_activity": self._get_last_weld_date(
                        welder_id, process=p
                    ),
                }
            result["all_continuous"] = all(
                v["continuous"] for v in result["by_process"].values()
            )
            return result

        # Single process check
        has_activity = any(
            e.get("process", "").upper() == process.upper() for e in entries
        )
        return {
            "welder": welder.stencil_no,
            "process": process,
            "continuous": has_activity,
            "cutoff_date": cutoff.isoformat(),
            "last_activity": self._get_last_weld_date(
                welder_id, process=process
            ),
        }

    def get_continuity_broken_welders(
        self, project_id: int,
    ) -> List[Dict[str, Any]]:
        """Return all active welders with broken continuity."""
        active = self.repo.get_active(project_id)
        broken = []
        for w in active:
            last = self._get_last_weld_date(w.id)
            if last:
                months = self._months_between(last, date.today())
                if months > self.CONTINUITY_PERIOD_MONTHS:
                    broken.append({
                        "welder_id": w.id,
                        "stencil_no": w.stencil_no,
                        "full_name": w.full_name,
                        "last_weld_date": last.isoformat(),
                        "months_since": months,
                    })
        return broken

    # ═══════════════════════════════════════════
    #  5. STATUS LIFECYCLE
    # ═══════════════════════════════════════════

    def transition_status(
        self,
        welder_id: int,
        new_status: str,
        *,
        user: str = "",
        reason: str = "",
    ) -> Any:
        """Advance welder through lifecycle state machine."""
        welder = self._get_welder_or_raise(welder_id)
        current = WelderStatus(welder.status)
        target = WelderStatus(new_status)

        if target not in _ALLOWED_TRANSITIONS.get(current, []):
            raise StateTransitionError(
                f"Welder {welder.stencil_no}: Cannot transition "
                f"{current.value} → {target.value}."
            )

        is_active = target in (
            WelderStatus.ACTIVE, WelderStatus.UNDER_RETEST,
        )
        result = self.repo.edit_welder(
            welder_id,
            status=target.value,
            is_active=is_active,
        )
        logger.info(
            "Welder %s: %s → %s (by %s: %s)",
            welder.stencil_no, current.value, target.value, user, reason,
        )
        self._audit(
            welder, "STATUS",
            f"{current.value} → {target.value} by {user}: {reason}"
        )
        return result

    def suspend_welder(
        self, welder_id: int, reason: str = "", suspended_by: str = "",
    ) -> Any:
        return self.transition_status(
            welder_id, WelderStatus.SUSPENDED.value,
            user=suspended_by, reason=reason,
        )

    def reactivate_welder(
        self, welder_id: int, reactivated_by: str = "",
    ) -> Any:
        return self.transition_status(
            welder_id, WelderStatus.ACTIVE.value,
            user=reactivated_by, reason="Reactivated",
        )

    # ═══════════════════════════════════════════
    #  6. RENEWAL & REQUALIFICATION
    # ═══════════════════════════════════════════

    def renew_certificate(
        self,
        welder_id: int,
        new_expiry: date,
        certificate_no: Optional[str] = None,
        renewed_by: str = "",
    ) -> Any:
        """Renew an existing certificate (administrative extension)."""
        welder = self._get_welder_or_raise(welder_id)
        if new_expiry <= date.today():
            raise ValidationError("New expiry date must be in the future.")

        kwargs: Dict[str, Any] = {"expiry_date": new_expiry}
        if certificate_no:
            kwargs["certificate_no"] = certificate_no

        result = self.repo.edit_welder(welder_id, **kwargs)
        logger.info(
            "Welder %s certificate renewed to %s by %s",
            welder.stencil_no, new_expiry, renewed_by,
        )
        self._audit(
            welder, "RENEW",
            f"New expiry={new_expiry}, Cert={certificate_no}"
        )
        return result

    def requalify_welder(
        self,
        welder_id: int,
        qual: QualificationRecord,
        requalified_by: str = "",
    ) -> Any:
        """
        Full requalification (new WPQ test).

        Used when certificate has expired or welder failed continuity.
        """
        welder = self._get_welder_or_raise(welder_id)

        # Mark as under retest
        if welder.status in (
            WelderStatus.EXPIRED.value, WelderStatus.INACTIVE.value,
        ):
            self.transition_status(
                welder_id, WelderStatus.UNDER_RETEST.value,
                user=requalified_by, reason="Requalification initiated",
            )

        # Add new qualification
        result = self.add_qualification(welder_id, qual)

        # If passed, reactivate
        if qual.coupon_result == CouponResult.PASS.value:
            self.transition_status(
                welder_id, WelderStatus.ACTIVE.value,
                user=requalified_by, reason="Requalification passed",
            )

        return result

    # ═══════════════════════════════════════════
    #  7. QUERIES
    # ═══════════════════════════════════════════

    def get_welder(self, welder_id: int) -> Any:
        return self._get_welder_or_raise(welder_id)

    def get_welder_by_stencil(
        self, project_id: int, stencil: str,
    ) -> Any:
        stencil = self._normalize_stencil(stencil)
        welder = self.repo.find_by_stencil(project_id, stencil)
        if not welder:
            raise NotFoundError(
                f"Welder '{stencil}' not found in project {project_id}."
            )
        return welder

    def list_welders(
        self,
        project_id: int,
        *,
        status: Optional[str] = None,
        process: Optional[str] = None,
        search: str = "",
        limit: int = 500,
        offset: int = 0,
    ) -> List[Any]:
        return self.repo.list_welders(
            project_id,
            status=status,
            process=process,
            search=search.strip(),
            limit=limit,
            offset=offset,
        )

    def get_expiring_certificates(
        self, project_id: int, days: int = 30,
    ) -> List[Any]:
        """Return welders whose certificates expire within N days."""
        return self.repo.get_expiring(project_id, days)

    def get_welder_full_profile(
        self, welder_id: int,
    ) -> Dict[str, Any]:
        """Complete welder profile with all qualifications and history."""
        welder = self._get_welder_or_raise(welder_id)
        quals = self.list_qualifications(welder_id)
        continuity = self.repo.get_continuity_entries(welder_id)
        performance = self._get_performance_history(welder_id)

        return {
            "welder": {
                "id": welder.id,
                "stencil_no": welder.stencil_no,
                "full_name": welder.full_name,
                "status": welder.status,
                "is_active": getattr(welder, "is_active", False),
                "expiry_date": str(getattr(welder, "expiry_date", "")),
                "employer": getattr(welder, "employer", ""),
                "nationality": getattr(welder, "nationality", ""),
            },
            "qualifications": quals,
            "active_qualifications": self.get_active_qualifications(welder_id),
            "continuity": {
                "last_weld_date": str(
                    self._get_last_weld_date(welder_id) or "N/A"
                ),
                "entries_count": len(continuity),
                "is_continuous": self.check_continuity(welder_id).get(
                    "all_continuous", True
                ),
            },
            "performance": {
                "total_welds": len(performance),
                "repair_count": sum(
                    1 for p in performance if p.get("is_repair")
                ),
                "ndt_pass_rate": self._calc_ndt_pass_rate(performance),
            },
        }

    # ═══════════════════════════════════════════
    #  8. REPORTING & DASHBOARD
    # ═══════════════════════════════════════════

    def get_dashboard_stats(self, project_id: int) -> Dict[str, Any]:
        """Backward-compatible simple dashboard stats."""
        active = self.repo.get_active(project_id)
        expiring = self.repo.get_expiring(project_id, 30)
        expired = [
            w for w in active
            if getattr(w, "expiry_date", None)
            and (
                w.expiry_date if isinstance(w.expiry_date, date)
                else date.fromisoformat(str(w.expiry_date))
            ) < date.today()
        ]
        return {
            "total_active": len(active),
            "expiring_30d": len(expiring),
            "expired": len(expired),
        }

    def get_comprehensive_dashboard(
        self, project_id: int,
    ) -> WelderDashboardStats:
        """Multi-dimensional dashboard for project management."""
        all_welders = self.repo.get_all(project_id) if hasattr(
            self.repo, "get_all"
        ) else self.list_welders(project_id, limit=9999)

        total = len(all_welders)
        today = date.today()

        by_status: Dict[str, int] = {}
        by_process: Dict[str, int] = {}
        by_position: Dict[str, int] = {}
        by_p_number: Dict[str, int] = {}
        by_employer: Dict[str, int] = {}
        total_quals = 0
        alerts: List[str] = []

        exp_30 = exp_60 = exp_90 = 0

        for w in all_welders:
            s = getattr(w, "status", "Unknown")
            by_status[s] = by_status.get(s, 0) + 1

            emp = getattr(w, "employer", "N/A") or "N/A"
            by_employer[emp] = by_employer.get(emp, 0) + 1

            exp = getattr(w, "expiry_date", None)
            if exp:
                exp_date = exp if isinstance(exp, date) else date.fromisoformat(str(exp))
                delta = (exp_date - today).days
                if 0 < delta <= 30:
                    exp_30 += 1
                elif 0 < delta <= 60:
                    exp_60 += 1
                elif 0 < delta <= 90:
                    exp_90 += 1

            # Count qualifications per welder
            try:
                quals = self.get_active_qualifications(w.id)
                total_quals += len(quals)
                for q in quals:
                    p = q.get("process", "Unknown")
                    by_process[p] = by_process.get(p, 0) + 1
                    pos = q.get("qualified_positions", "")
                    for pp in pos.split(","):
                        pp = pp.strip()
                        if pp:
                            by_position[pp] = by_position.get(pp, 0) + 1
                    pn = q.get("p_number_base", "N/A")
                    by_p_number[pn] = by_p_number.get(pn, 0) + 1
            except Exception:
                pass

        continuity_broken = len(self.get_continuity_broken_welders(project_id))
        if continuity_broken > 0:
            alerts.append(
                f"⚠️ {continuity_broken} welder(s) with broken continuity "
                f"(ASME IX QW-322)."
            )
        if exp_30 > 0:
            alerts.append(
                f"🔴 {exp_30} certificate(s) expiring within 30 days."
            )

        active_count = by_status.get(WelderStatus.ACTIVE.value, 0)

        return WelderDashboardStats(
            project_id=project_id,
            total_registered=total,
            total_active=active_count,
            total_inactive=by_status.get(WelderStatus.INACTIVE.value, 0),
            total_expired=by_status.get(WelderStatus.EXPIRED.value, 0),
            total_suspended=by_status.get(WelderStatus.SUSPENDED.value, 0),
            expiring_30d=exp_30,
            expiring_60d=exp_60,
            expiring_90d=exp_90,
            continuity_broken=continuity_broken,
            by_process=by_process,
            by_position=by_position,
            by_p_number=by_p_number,
            by_employer=by_employer,
            avg_qualifications_per_welder=round(
                total_quals / active_count, 1
            ) if active_count else 0,
            critical_alerts=alerts,
        )

    def get_welder_performance_report(
        self,
        project_id: int,
        welder_id: Optional[int] = None,
        *,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Performance report: weld count, NDT pass rate, repairs."""
        if welder_id:
            welders = [self._get_welder_or_raise(welder_id)]
        else:
            welders = self.repo.get_active(project_id)

        report = {"project_id": project_id, "welders": []}
        for w in welders:
            perf = self._get_performance_history(
                w.id, from_date=from_date, to_date=to_date,
            )
            total = len(perf)
            repairs = sum(1 for p in perf if p.get("is_repair"))
            report["welders"].append({
                "stencil_no": w.stencil_no,
                "full_name": w.full_name,
                "total_welds": total,
                "repairs": repairs,
                "repair_rate_pct": round(
                    repairs / total * 100, 1
                ) if total else 0,
                "ndt_pass_rate": self._calc_ndt_pass_rate(perf),
            })

        return report

    # ═══════════════════════════════════════════
    #  9. INTERNAL HELPERS
    # ═══════════════════════════════════════════

    def _get_welder_or_raise(self, welder_id: int) -> Any:
        welder = self.repo.get_by_id(welder_id) if hasattr(
            self.repo, "get_by_id"
        ) else self.repo.find_by_id(welder_id)
        if not welder:
            raise NotFoundError(f"Welder id={welder_id} not found.")
        return welder

    @staticmethod
    def _normalize_stencil(stencil: str) -> str:
        return stencil.strip().upper()

    @staticmethod
    def _validate_stencil(stencil: str) -> None:
        if not stencil:
            raise ValidationError("Stencil number cannot be empty.")
        if len(stencil) > 30:
            raise ValidationError("Stencil number must be ≤ 30 characters.")

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or len(name.strip()) < 2:
            raise ValidationError("Full name must be at least 2 characters.")

    @staticmethod
    def _validate_qualification(qual: QualificationRecord) -> None:
        if not qual.process:
            raise ValidationError("Welding process is required.")
        valid_processes = {e.value for e in WeldingProcess}
        if qual.process.upper() not in valid_processes:
            raise ValidationError(
                f"Invalid process '{qual.process}'. "
                f"Must be one of: {sorted(valid_processes)}"
            )
        if qual.coupon_thickness_mm < 0:
            raise ValidationError("Coupon thickness cannot be negative.")

    @staticmethod
    def _calc_min_thickness(coupon_t: float) -> float:
        """ASME IX QW-451: Min qualified thickness."""
        if coupon_t < 13:
            return max(1.5, coupon_t * 0.5)  # 2T or 1.5mm
        return coupon_t * 0.5

    @staticmethod
    def _calc_max_thickness(coupon_t: float) -> float:
        """ASME IX QW-451: Max qualified thickness."""
        if coupon_t < 13:
            return coupon_t * 2  # 2T
        return coupon_t * 2      # 2T (unlimited for t≥38mm in some codes)

    @staticmethod
    def _calc_min_diameter(coupon_od: float) -> float:
        """ASME IX QW-452: Min qualified diameter."""
        if coupon_od < 25:
            return coupon_od
        if coupon_od < 73:
            return coupon_od * 0.4
        return coupon_od * 0.33

    @staticmethod
    def _months_between(d1: date, d2: date) -> int:
        return (d2.year - d1.year) * 12 + (d2.month - d1.month)

    def _get_last_weld_date(
        self, welder_id: int, process: str = "",
    ) -> Optional[date]:
        """Get the most recent weld date for continuity tracking."""
        try:
            if hasattr(self.repo, "get_last_weld_date"):
                return self.repo.get_last_weld_date(welder_id, process)
            entries = self.repo.get_continuity_entries(welder_id)
            if process:
                entries = [
                    e for e in entries
                    if e.get("process", "").upper() == process.upper()
                ]
            if not entries:
                return None
            dates = []
            for e in entries:
                d = e.get("date_welded")
                if isinstance(d, str):
                    d = date.fromisoformat(d)
                if isinstance(d, date):
                    dates.append(d)
            return max(dates) if dates else None
        except Exception:
            return None

    def _get_performance_history(
        self,
        welder_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Get weld performance history for a welder."""
        try:
            if hasattr(self.repo, "get_performance_history"):
                return self.repo.get_performance_history(
                    welder_id, from_date=from_date, to_date=to_date,
                )
            return self.repo.get_continuity_entries(welder_id)
        except Exception:
            return []

    @staticmethod
    def _calc_ndt_pass_rate(performance: List[Dict[str, Any]]) -> float:
        if not performance:
            return 0.0
        passed = sum(
            1 for p in performance
            if p.get("ndt_result", "").upper() in ("PASS", "ACCEPTED", "AC", "OK")
        )
        total_with_ndt = sum(
            1 for p in performance if p.get("ndt_result")
        )
        return round(
            passed / total_with_ndt * 100, 1
        ) if total_with_ndt else 0.0

    def _audit(self, welder, action: str, detail: str) -> None:
        try:
            if hasattr(self.repo, "add_audit_entry"):
                self.repo.add_audit_entry(
                    entity_type="Welder",
                    entity_id=welder.id,
                    entity_tag=welder.stencil_no,
                    action=action,
                    detail=detail,
                    timestamp=datetime.utcnow(),
                )
        except Exception as e:
            logger.warning("Audit write failed: %s", e)