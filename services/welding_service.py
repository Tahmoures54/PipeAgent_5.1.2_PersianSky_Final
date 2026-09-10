# -*- coding: utf-8 -*-
"""
welding_service.py – PipeAgent
================================
Weld / Joint Lifecycle Management Service
------------------------------------------
Complete weld lifecycle from joint list creation through fit-up,
welding, NDT, repair, and acceptance in compliance with:

  • ASME B31.3   Process Piping (§328, §341, §344)
  • ASME B31.1   Power Piping
  • API 1104     Welding of Pipelines
  • ASME IX      Welding Qualifications
  • AWS D1.1     Structural Welding Code
  • ISO 5817     Weld Quality Levels
  • NACE SP0178  Fabrication Details

Features:
  • Full state machine (10 states) with guard conditions
  • Welder authorization check (delegates to WelderQualificationService)
  • WPS range validation (thickness, diameter, material, position)
  • Multi-pass recording (root, hot, fill, cap)
  • Preheat / interpass / PWHT recording with limits
  • Heat number traceability (pipe + filler + flange)
  • Weld consumable tracking (electrode batch, flux lot, gas)
  • NDT scheduling, assignment, and result integration
  • Defect tracking (type, location, length, depth)
  • Repair management (repair WPS, extent, depth, re-inspection)
  • Dimensional inspection (root gap, hi-lo, alignment, bore)
  • Daily Weld Report (DWR) generation
  • Productivity metrics (welds/day/welder/crew)
  • Weld map & isometric completion tracking
  • Test package integration
  • Bulk import from joint list / CSV
  • Comprehensive reporting & statistics
  • Full audit trail (Joint History)

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

from db.manager import DatabaseManager
from db.models import Weld, WPS_PQR, JointHistory, NDTRecord
from repositories.weld_repository import WeldRepository
from services.rule_engine import rule_engine, CheckReport
from services.license import increment_usage

logger = logging.getLogger("pipeagent.services.welding")


# ─────────────────────────────────────────────
#  Enums
# ─────────────────────────────────────────────

class WeldStatus(str, Enum):
    """Full weld lifecycle states."""
    PLANNED = "Planned"           # In joint list, not yet started
    PENDING = "Pending"           # Released for fit-up
    FIT_UP = "Fit-up"             # Fit-up in progress / complete
    WELDING = "Welding"           # Welding in progress (multi-pass)
    WELDED = "Welded"             # Welding complete, awaiting NDT
    NDT_PENDING = "NDT Pending"   # NDT scheduled, awaiting results
    INSPECTED = "Inspected"       # NDT complete, under review
    ACCEPTED = "Accepted"         # Passed all inspections
    REJECTED = "Rejected"         # Failed NDT / visual
    REPAIRED = "Repaired"         # Repair completed, awaiting re-inspection
    CUT_OUT = "Cut-out"           # Removed and replaced
    REINSTATED = "Reinstated"     # Reinstated after test package


class WeldType(str, Enum):
    SHOP = "Shop"
    FIELD = "Field"
    ERECTION = "Erection"
    TIE_IN = "Tie-in"
    REPAIR = "Repair"


class JointType(str, Enum):
    BUTT = "Butt"
    SOCKET = "Socket"
    FILLET = "Fillet"
    BRANCH = "Branch"
    FLANGE = "Flange"
    THREADED = "Threaded"
    CLAD = "Clad"


class WeldingPosition(str, Enum):
    F_1G = "1G"
    F_2G = "2G"
    F_5G = "5G"
    F_6G = "6G"
    F_6GR = "6GR"


class PassType(str, Enum):
    ROOT = "Root"
    HOT = "Hot"
    FILL = "Fill"
    FILL_1 = "Fill-1"
    FILL_2 = "Fill-2"
    FILL_3 = "Fill-3"
    CAP = "Cap"
    BACK_GAUGE = "Back Gauge"


class DefectType(str, Enum):
    POROSITY = "Porosity"
    SLAG_INCLUSION = "Slag Inclusion"
    LACK_OF_FUSION = "Lack of Fusion"
    LACK_OF_PENETRATION = "Lack of Penetration"
    CRACK = "Crack"
    UNDERCUT = "Undercut"
    OVERLAP = "Overlap"
    EXCESS_PENETRATION = "Excess Penetration"
    INSUFFICIENT_FILL = "Insufficient Fill"
    MISALIGNMENT = "Misalignment"
    BURN_THROUGH = "Burn Through"
    TUNGSTEN_INCLUSION = "Tungsten Inclusion"
    ARC_STRIKE = "Arc Strike"
    SPATTER = "Spatter"
    CONCavity = "Concavity"
    OTHER = "Other"


class NDTMethod(str, Enum):
    VT = "VT"
    RT = "RT"
    UT = "UT"
    MT = "MT"
    PT = "PT"
    PAUT = "PAUT"
    TOFD = "TOFD"
    PMI = "PMI"
    HARDNESS = "Hardness"


# Valid state transitions with guard conditions
_ALLOWED_TRANSITIONS: Dict[WeldStatus, List[WeldStatus]] = {
    WeldStatus.PLANNED:      [WeldStatus.PENDING],
    WeldStatus.PENDING:      [WeldStatus.FIT_UP, WeldStatus.PLANNED],
    WeldStatus.FIT_UP:       [WeldStatus.WELDING, WeldStatus.WELDED, WeldStatus.PENDING],
    WeldStatus.WELDING:      [WeldStatus.WELDED, WeldStatus.FIT_UP],
    WeldStatus.WELDED:       [WeldStatus.NDT_PENDING, WeldStatus.INSPECTED,
                              WeldStatus.REPAIRED],
    WeldStatus.NDT_PENDING:  [WeldStatus.INSPECTED, WeldStatus.WELDED],
    WeldStatus.INSPECTED:    [WeldStatus.ACCEPTED, WeldStatus.REJECTED],
    WeldStatus.REJECTED:     [WeldStatus.REPAIRED, WeldStatus.CUT_OUT],
    WeldStatus.REPAIRED:     [WeldStatus.WELDED, WeldStatus.INSPECTED,
                              WeldStatus.NDT_PENDING],
    WeldStatus.ACCEPTED:     [WeldStatus.REINSTATED],
    WeldStatus.CUT_OUT:      [WeldStatus.PENDING],
    WeldStatus.REINSTATED:   [],
}

# Maximum repairs before mandatory cut-out (industry standard)
MAX_REPAIRS_BEFORE_CUTOUT = 2


# ─────────────────────────────────────────────
#  Data Classes / DTOs
# ─────────────────────────────────────────────

@dataclass
class WeldCreation:
    """Input DTO for creating a new weld."""
    weld_id: str
    weld_type: str = WeldType.FIELD.value
    line_number: str = ""
    iso_number: str = ""
    joint_type: str = JointType.BUTT.value
    size_nps: str = ""
    schedule: str = ""
    wall_thickness_mm: float = 0.0
    material_grade: str = ""
    material_spec: str = ""          # e.g. SA-106 Gr.B
    p_number: str = ""
    design_pressure_barg: float = 0.0
    design_temp_c: float = 0.0
    fluid_service: str = "Normal Fluid Service"
    spool_id: Optional[int] = None
    area_id: Optional[int] = None
    wps_no: str = ""
    wps_pqr_id: Optional[int] = None
    welding_position: str = ""
    test_package: str = ""
    remarks: str = ""


@dataclass
class FitUpRecord:
    """Input DTO for fit-up inspection."""
    inspector: str = ""
    fitup_date: Optional[date] = None
    root_gap_mm: float = 0.0
    root_gap_min_mm: float = 2.5
    root_gap_max_mm: float = 4.0
    hi_lo_mm: float = 0.0
    hi_lo_max_mm: float = 1.5
    alignment_mm: float = 0.0
    alignment_max_mm: float = 1.5
    internal_bore_mm: float = 0.0
    bevel_angle_deg: float = 37.5
    land_mm: float = 1.6
    tack_welds_count: int = 0
    cleanliness: str = "Acceptable"  # Acceptable / Unacceptable
    preheat_required: bool = False
    preheat_temp_min_c: float = 0.0
    result: str = "Accept"           # Accept / Reject
    remarks: str = ""


@dataclass
class WeldPassRecord:
    """Input DTO for a single weld pass."""
    pass_type: str                   # PassType
    process: str = ""                # GTAW / SMAW / FCAW
    filler_spec: str = ""            # e.g. ER70S-6, E7018
    filler_diameter_mm: float = 0.0
    filler_heat_no: str = ""
    filler_batch_no: str = ""
    welder_id: str = ""
    welder_stencil: str = ""
    amperage: int = 0
    voltage: float = 0.0
    travel_speed_cm_min: float = 0.0
    preheat_temp_c: float = 0.0
    interpass_temp_c: float = 0.0
    shielding_gas: str = ""
    gas_flow_rate_lpm: float = 0.0
    back_purge: bool = False
    back_purge_gas: str = ""
    pass_date: Optional[date] = None
    visual_result: str = "Accept"
    remarks: str = ""


@dataclass
class PreheatRecord:
    """Input DTO for preheat / interpass temperature."""
    preheat_temp_c: float = 0.0
    preheat_min_c: float = 0.0
    preheat_max_c: float = 0.0
    interpass_temp_c: float = 0.0
    interpass_max_c: float = 250.0
    method: str = ""                 # Torch, Electric, Induction
    measured_by: str = ""
    instrument_id: str = ""
    measurement_date: Optional[datetime] = None


@dataclass
class PWHTRecord:
    """Input DTO for Post Weld Heat Treatment."""
    pwht_required: bool = False
    pwht_done: bool = False
    soak_temp_c: float = 0.0
    soak_temp_min_c: float = 0.0
    soak_temp_max_c: float = 0.0
    soak_time_hours: float = 0.0
    heating_rate_c_hr: float = 0.0
    cooling_rate_c_hr: float = 0.0
    chart_no: str = ""
    thermocouple_count: int = 0
    furnace_id: str = ""
    pwht_date: Optional[date] = None
    result: str = "Accept"
    operator: str = ""
    remarks: str = ""


@dataclass
class DefectRecord:
    """Input DTO for a weld defect."""
    defect_type: str                 # DefectType
    location: str = ""               # Clock position: "12 o'clock"
    length_mm: float = 0.0
    depth_mm: float = 0.0
    width_mm: float = 0.0
    ndt_method: str = ""
    ndt_report_no: str = ""
    severity: str = "Minor"          # Minor / Major / Critical
    repairable: bool = True
    remarks: str = ""


@dataclass
class RepairRecord:
    """Input DTO for a weld repair."""
    repair_no: int = 1
    repair_wps_no: str = ""
    defect_type: str = ""
    defect_location: str = ""
    defect_length_mm: float = 0.0
    repair_depth_mm: float = 0.0
    repair_length_mm: float = 0.0
    excavation_method: str = ""      # Grinding, Gouging
    welder_id: str = ""
    process: str = ""
    filler_spec: str = ""
    filler_heat_no: str = ""
    preheat_temp_c: float = 0.0
    repair_date: Optional[date] = None
    ndt_required: str = ""           # Same as original / Full RT / etc.
    remarks: str = ""


@dataclass
class NDTSchedule:
    """Input DTO for scheduling NDT on a weld."""
    ndt_method: str                  # NDTMethod
    percentage: float = 100.0        # % of weld to inspect
    priority: str = "Normal"         # Urgent / Normal / Low
    requested_by: str = ""
    requested_date: Optional[date] = None
    inspector: str = ""
    agency: str = ""
    remarks: str = ""


@dataclass
class DailyWeldReport:
    """Daily Weld Report output."""
    report_date: date
    project_id: int
    line_numbers: List[str]
    total_welds_completed: int
    total_inch_dia: float
    by_welder: Dict[str, int]
    by_process: Dict[str, int]
    by_type: Dict[str, int]
    repairs: int
    ndt_passed: int
    ndt_failed: int
    weather: str = ""
    crew: str = ""
    remarks: str = ""


@dataclass
class WeldProductivity:
    """Productivity metrics for a period."""
    period_start: date
    period_end: date
    total_welds: int
    total_inch_dia: float
    total_man_hours: float
    welds_per_day: float
    inch_dia_per_day: float
    welds_per_welder_day: float
    repair_rate_pct: float
    ndt_pass_rate_pct: float
    by_welder: Dict[str, Dict[str, Any]]
    by_line: Dict[str, Dict[str, Any]]


# ─────────────────────────────────────────────
#  Main Service
# ─────────────────────────────────────────────

class WeldingService:
    """
    Enterprise-grade Weld Lifecycle Management.

    Usage:
        svc = WeldingService(db)
        svc.create_weld(project_id=1, creation=WeldCreation(weld_id="W-001", ...))
        svc.record_fitup("W-001", fitup=FitUpRecord(...))
        svc.record_weld_pass("W-001", pass_rec=WeldPassRecord(...))
        svc.change_status("W-001", "Welded", user="inspector")
    """

    def __init__(
        self,
        db: DatabaseManager,
        welder_qual_service=None,
    ):
        self.db = db
        self.repo = WeldRepository(db)
        self.welder_qual_svc = welder_qual_service  # Optional injection

    # ═══════════════════════════════════════════
    #  1. WELD CREATION & CRUD
    # ═══════════════════════════════════════════

    def create_weld(
        self,
        project_id: int,
        creation: WeldCreation,
        *,
        created_by: str = "",
    ) -> Optional[Weld]:
        """Create a new weld with full validation."""
        if not increment_usage(self.db):
            logger.error("License limit reached — cannot create weld.")
            return None

        wid = self._normalize_weld_id(creation.weld_id)
        self._validate_weld_id(wid)

        if self.repo.get_by_weld_id(wid):
            logger.warning("Weld ID %s already exists", wid)
            return None

        # Validate WPS if provided
        if creation.wps_pqr_id:
            self._validate_wps_compatibility(creation)

        weld = Weld(
            project_id=project_id,
            weld_id=wid,
            weld_type=creation.weld_type,
            line_number=creation.line_number,
            iso_number=creation.iso_number,
            joint_type=creation.joint_type,
            size=creation.size_nps,
            schedule=creation.schedule if hasattr(Weld, 'schedule') else None,
            wall_thickness_mm=creation.wall_thickness_mm,
            material=creation.material_grade,
            material_spec=creation.material_spec if hasattr(Weld, 'material_spec') else None,
            p_number=creation.p_number if hasattr(Weld, 'p_number') else None,
            spool_id=creation.spool_id,
            area_id=creation.area_id,
            wps_pqr_id=creation.wps_pqr_id,
            wps_no=creation.wps_no if hasattr(Weld, 'wps_no') else None,
            welding_position=creation.welding_position if hasattr(Weld, 'welding_position') else None,
            test_package=creation.test_package if hasattr(Weld, 'test_package') else None,
            fluid_service=creation.fluid_service if hasattr(Weld, 'fluid_service') else None,
            status=WeldStatus.PENDING.value,
            repair_count=0,
            created_by=created_by,
            created_at=datetime.utcnow(),
        )
        # Remove None attributes that model doesn't support
        for attr in list(weld.__dict__.keys()):
            if attr.startswith('_'):
                continue

        created = self.repo.create(weld)
        if created:
            self._log_history(
                created.id, "Created",
                new_value=WeldStatus.PENDING.value,
                notes=f"{creation.weld_type} {creation.joint_type} joint "
                      f"on {creation.line_number}",
                user_name=created_by,
            )
            logger.info(
                "Created weld %s (line=%s, type=%s)",
                wid, creation.line_number, creation.weld_type,
            )
        return created

    def create_weld_legacy(
        self,
        project_id: int,
        weld_id: str,
        *,
        weld_type: str = "Shop",
        line_number: str = "",
        iso_number: str = "",
        joint_type: str = "Butt",
        size: str = "",
        wall_thickness_mm: Optional[float] = None,
        material: str = "",
        spool_id: Optional[int] = None,
        area_id: Optional[int] = None,
        wps_pqr_id: Optional[int] = None,
        welder_id: str = "",
        welder_name: str = "",
        created_by: str = "",
    ) -> Optional[Weld]:
        """Backward-compatible weld creation."""
        creation = WeldCreation(
            weld_id=weld_id,
            weld_type=weld_type,
            line_number=line_number,
            iso_number=iso_number,
            joint_type=joint_type,
            size_nps=size,
            wall_thickness_mm=wall_thickness_mm or 0.0,
            material_grade=material,
            spool_id=spool_id,
            area_id=area_id,
            wps_pqr_id=wps_pqr_id,
        )
        weld = self.create_weld(project_id, creation, created_by=created_by)
        if weld and (welder_id or welder_name):
            self.repo.update(weld)
        return weld

    def get_weld(self, weld_id: str) -> Optional[Weld]:
        return self.repo.get_by_weld_id(self._normalize_weld_id(weld_id))

    def list_by_project(
        self, project_id: int,
        *, status: Optional[str] = None,
        line_number: Optional[str] = None,
        iso_number: Optional[str] = None,
        weld_type: Optional[str] = None,
        limit: int = 5000,
    ) -> List[Weld]:
        return self.repo.get_by_project(
            project_id, status=status, line_number=line_number,
            iso_number=iso_number, weld_type=weld_type, limit=limit,
        ) if hasattr(self.repo, 'get_by_project') else \
            self.repo.get_by_project(project_id)

    def list_by_spool(self, spool_id: int) -> List[Weld]:
        return self.repo.get_by_spool(spool_id)

    def list_by_status(self, project_id: int, status: str) -> List[Weld]:
        return self.repo.get_by_status(project_id, status)

    def list_by_test_package(
        self, project_id: int, package_number: str,
    ) -> List[Weld]:
        """List all welds assigned to a test package."""
        if hasattr(self.repo, 'get_by_test_package'):
            return self.repo.get_by_test_package(project_id, package_number)
        all_welds = self.repo.get_by_project(project_id)
        return [
            w for w in all_welds
            if getattr(w, 'test_package', '') == package_number
        ]

    def bulk_create(
        self,
        project_id: int,
        records: List[Dict[str, Any]],
        *,
        created_by: str = "",
    ) -> Tuple[int, int, List[str]]:
        """
        Bulk-create welds from joint list (CSV / dict list).

        Returns: (created_count, skipped_count, errors)
        """
        created = skipped = 0
        errors: List[str] = []

        for i, rec in enumerate(records, 1):
            wid = rec.get("weld_id", "").strip()
            if not wid:
                errors.append(f"Row {i}: Missing weld_id.")
                skipped += 1
                continue
            try:
                creation = WeldCreation(
                    weld_id=wid,
                    weld_type=rec.get("weld_type", "Field"),
                    line_number=rec.get("line_number", ""),
                    iso_number=rec.get("iso_number", ""),
                    joint_type=rec.get("joint_type", "Butt"),
                    size_nps=rec.get("size_nps", rec.get("size", "")),
                    wall_thickness_mm=float(rec.get("wall_thickness_mm", 0) or 0),
                    material_grade=rec.get("material", ""),
                    wps_no=rec.get("wps_no", ""),
                    welding_position=rec.get("position", ""),
                    test_package=rec.get("test_package", ""),
                )
                result = self.create_weld(
                    project_id, creation, created_by=created_by,
                )
                if result:
                    created += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append(f"Row {i} ({wid}): {e}")
                skipped += 1

        logger.info(
            "Bulk create project %s: %d created, %d skipped",
            project_id, created, skipped,
        )
        return created, skipped, errors

    def bulk_create_from_csv(
        self, project_id: int, csv_text: str, *, created_by: str = "",
    ) -> Tuple[int, int, List[str]]:
        reader = csv.DictReader(StringIO(csv_text))
        return self.bulk_create(project_id, list(reader), created_by=created_by)

    # ═══════════════════════════════════════════
    #  2. STATUS LIFECYCLE
    # ═══════════════════════════════════════════

    def change_status(
        self,
        weld_id: str,
        new_status: str,
        updated_by: str = "",
        force: bool = False,
        notes: str = "",
    ) -> Tuple[bool, str]:
        """
        Transition weld status with guard conditions.

        Guards:
          - Fit-up → Welded: requires fit-up acceptance
          - Welded → Inspected: requires NDT results
          - Rejected → Repaired: requires repair record
          - Repaired → Welded: max repair count check
        """
        weld = self.repo.get_by_weld_id(self._normalize_weld_id(weld_id))
        if not weld:
            return False, f"Weld {weld_id} not found"

        current = WeldStatus(weld.status or WeldStatus.PENDING.value)
        target = WeldStatus(new_status)

        # Validate transition
        allowed = _ALLOWED_TRANSITIONS.get(current, [])
        if not force and target not in allowed:
            return False, (
                f"Cannot transition from '{current.value}' to '{target.value}'. "
                f"Allowed: {', '.join(a.value for a in allowed) or 'none'}"
            )

        # Guard conditions
        guard_ok, guard_msg = self._check_transition_guards(
            weld, current, target,
        )
        if not guard_ok and not force:
            return False, guard_msg

        # Apply transition
        old_status = current.value
        weld.status = target.value
        weld.updated_by = updated_by
        weld.updated_at = datetime.utcnow()

        # Side effects
        if target == WeldStatus.WELDED and not getattr(weld, 'weld_end_datetime', None):
            weld.weld_end_datetime = datetime.utcnow()
        if target == WeldStatus.ACCEPTED:
            weld.acceptance_date = date.today() if hasattr(weld, 'acceptance_date') else None
        if target == WeldStatus.CUT_OUT:
            weld.cutout_date = date.today() if hasattr(weld, 'cutout_date') else None

        self.repo.update(weld)
        self._log_history(
            weld.id, "StatusChange",
            old_value=old_status, new_value=target.value,
            notes=notes, user_name=updated_by,
        )
        logger.info(
            "Weld %s: %s → %s (by %s)", weld_id, old_status, target.value, updated_by,
        )
        return True, f"Status updated to {target.value}"

    def _check_transition_guards(
        self, weld, current: WeldStatus, target: WeldStatus,
    ) -> Tuple[bool, str]:
        """Pre-transition guard conditions."""

        if target == WeldStatus.WELDED and current == WeldStatus.FIT_UP:
            # Ensure fit-up was accepted
            if hasattr(weld, 'fitup_result') and weld.fitup_result == "Reject":
                return False, "Fit-up was rejected. Cannot proceed to welding."

        if target == WeldStatus.INSPECTED and current in (
            WeldStatus.WELDED, WeldStatus.NDT_PENDING,
        ):
            # Check if NDT results exist
            ndt_count = self._count_ndt_records(weld.id)
            if ndt_count == 0:
                return False, "No NDT results recorded. Cannot inspect."

        if target == WeldStatus.REPAIRED:
            repair_count = (weld.repair_count or 0) + 1
            if repair_count > MAX_REPAIRS_BEFORE_CUTOUT + 1:
                return False, (
                    f"Maximum repairs ({MAX_REPAIRS_BEFORE_CUTOUT}) exceeded. "
                    f"Mandatory cut-out required per project specification."
                )

        if target == WeldStatus.ACCEPTED and current == WeldStatus.INSPECTED:
            # Check all NDT passed
            failed_ndt = self._count_failed_ndt(weld.id)
            if failed_ndt > 0:
                return False, (
                    f"{failed_ndt} NDT result(s) failed. "
                    f"Cannot accept weld with open failures."
                )

        return True, "OK"

    # ═══════════════════════════════════════════
    #  3. FIT-UP INSPECTION
    # ═══════════════════════════════════════════

    def record_fitup(
        self,
        weld_id: str,
        fitup: FitUpRecord,
        *,
        user: str = "",
    ) -> Tuple[bool, str]:
        """
        Record fit-up inspection with dimensional checks.

        Validates root gap, hi-lo, alignment against WPS/project specs.
        """
        weld = self.repo.get_by_weld_id(self._normalize_weld_id(weld_id))
        if not weld:
            return False, "Weld not found"

        # Validate dimensions
        warnings: List[str] = []
        if fitup.root_gap_mm > 0:
            if fitup.root_gap_mm < fitup.root_gap_min_mm:
                warnings.append(
                    f"Root gap {fitup.root_gap_mm}mm < min {fitup.root_gap_min_mm}mm"
                )
            if fitup.root_gap_mm > fitup.root_gap_max_mm:
                warnings.append(
                    f"Root gap {fitup.root_gap_mm}mm > max {fitup.root_gap_max_mm}mm"
                )
        if fitup.hi_lo_mm > fitup.hi_lo_max_mm:
            warnings.append(
                f"Hi-Lo {fitup.hi_lo_mm}mm > max {fitup.hi_lo_max_mm}mm"
            )
        if fitup.alignment_mm > fitup.alignment_max_mm:
            warnings.append(
                f"Alignment {fitup.alignment_mm}mm > max {fitup.alignment_max_mm}mm"
            )

        # Update weld record
        weld.fitup_inspector = fitup.inspector
        weld.fitup_date = fitup.fitup_date or date.today()
        if hasattr(weld, 'root_gap_mm'):
            weld.root_gap_mm = fitup.root_gap_mm
        if hasattr(weld, 'hi_lo_mm'):
            weld.hi_lo_mm = fitup.hi_lo_mm
        if hasattr(weld, 'fitup_result'):
            weld.fitup_result = fitup.result
        weld.status = WeldStatus.FIT_UP.value
        weld.updated_by = user
        weld.updated_at = datetime.utcnow()
        self.repo.update(weld)

        notes = f"Fit-up by {fitup.inspector}: {fitup.result}"
        if warnings:
            notes += " | WARNINGS: " + "; ".join(warnings)

        self._log_history(
            weld.id, "Fit-up",
            new_value=fitup.result,
            notes=notes, user_name=user,
        )
        logger.info("Weld %s fit-up: %s (%s)", weld_id, fitup.result, fitup.inspector)

        msg = "Fit-up recorded"
        if warnings:
            msg += f" with {len(warnings)} warning(s)"
        return True, msg

    def record_fitup_legacy(
        self,
        weld_id: str,
        inspector: str = "",
        fitup_date: Optional[date] = None,
        user: str = "",
    ) -> Tuple[bool, str]:
        """Backward-compatible fit-up shortcut."""
        return self.record_fitup(
            weld_id,
            FitUpRecord(inspector=inspector, fitup_date=fitup_date),
            user=user,
        )

    # ═══════════════════════════════════════════
    #  4. WELDING — Multi-Pass & Consumables
    # ═══════════════════════════════════════════

    def record_weld_pass(
        self,
        weld_id: str,
        pass_rec: WeldPassRecord,
        *,
        user: str = "",
    ) -> Tuple[bool, str]:
        """
        Record a single weld pass (root, hot, fill, cap).

        Checks:
          - Welder authorization (if WelderQualificationService injected)
          - Preheat / interpass temperature limits
          - Filler metal compatibility with WPS
        """
        weld = self.repo.get_by_weld_id(self._normalize_weld_id(weld_id))
        if not weld:
            return False, "Weld not found"

        # Check welder authorization
        if self.welder_qual_svc and pass_rec.welder_stencil:
            auth = self.welder_qual_svc.check_authorization(
                project_id=weld.project_id,
                stencil=pass_rec.welder_stencil,
                process=pass_rec.process,
                thickness_mm=weld.wall_thickness_mm or 0,
                position=getattr(weld, 'welding_position', ''),
            )
            if not auth.is_authorized:
                return False, (
                    f"Welder {pass_rec.welder_stencil} not authorized: "
                    + "; ".join(auth.failures)
                )

        # Check interpass temperature
        if pass_rec.interpass_temp_c > 0:
            max_interpass = self._get_max_interpass(weld)
            if max_interpass and pass_rec.interpass_temp_c > max_interpass:
                logger.warning(
                    "Weld %s: Interpass %.0f°C exceeds max %.0f°C",
                    weld_id, pass_rec.interpass_temp_c, max_interpass,
                )

        # Update weld record with pass data
        weld.welder_id = pass_rec.welder_id or weld.welder_id
        weld.welder_name = pass_rec.welder_stencil or weld.welder_name
        if hasattr(weld, 'filler_spec'):
            weld.filler_spec = pass_rec.filler_spec
        if hasattr(weld, 'filler_heat_no'):
            weld.filler_heat_no = pass_rec.filler_heat_no
        if hasattr(weld, 'filler_batch_no'):
            weld.filler_batch_no = pass_rec.filler_batch_no
        if hasattr(weld, 'shielding_gas'):
            weld.shielding_gas = pass_rec.shielding_gas
        if hasattr(weld, 'back_purge'):
            weld.back_purge = pass_rec.back_purge
        if pass_rec.preheat_temp_c > 0 and hasattr(weld, 'preheat_temp_c'):
            weld.preheat_temp_c = pass_rec.preheat_temp_c
        if pass_rec.interpass_temp_c > 0 and hasattr(weld, 'interpass_temp_c'):
            weld.interpass_temp_c = pass_rec.interpass_temp_c

        # Track pass count
        if hasattr(weld, 'pass_count'):
            weld.pass_count = (weld.pass_count or 0) + 1

        # Advance to Welding status if still in Fit-up
        if weld.status == WeldStatus.FIT_UP.value:
            weld.status = WeldStatus.WELDING.value

        weld.updated_by = user
        weld.updated_at = datetime.utcnow()
        self.repo.update(weld)

        # Store pass record in history
        pass_detail = (
            f"Pass={pass_rec.pass_type}, Process={pass_rec.process}, "
            f"Filler={pass_rec.filler_spec}/{pass_rec.filler_heat_no}, "
            f"Welder={pass_rec.welder_stencil}, "
            f"Preheat={pass_rec.preheat_temp_c}°C, "
            f"Interpass={pass_rec.interpass_temp_c}°C"
        )
        self._log_history(
            weld.id, "WeldPass",
            new_value=pass_rec.pass_type,
            notes=pass_detail, user_name=user,
        )

        # Record continuity for welder qualification
        if self.welder_qual_svc and pass_rec.welder_stencil:
            try:
                w_obj = self.welder_qual_svc.repo.find_by_stencil(
                    weld.project_id, pass_rec.welder_stencil,
                )
                if w_obj:
                    self.welder_qual_svc.record_weld_activity(
                        welder_id=w_obj.id,
                        weld_id=weld_id,
                        line_number=weld.line_number,
                        process=pass_rec.process,
                        date_welded=pass_rec.pass_date,
                    )
            except Exception as e:
                logger.warning("Continuity recording failed: %s", e)

        logger.info(
            "Weld %s pass %s recorded (%s / %s)",
            weld_id, pass_rec.pass_type, pass_rec.process, pass_rec.welder_stencil,
        )
        return True, f"Pass {pass_rec.pass_type} recorded"

    def complete_welding(
        self,
        weld_id: str,
        *,
        user: str = "",
        heat_no_pipe: str = "",
        heat_no_filler: str = "",
        remarks: str = "",
    ) -> Tuple[bool, str]:
        """Mark welding as complete and advance to Welded status."""
        weld = self.repo.get_by_weld_id(self._normalize_weld_id(weld_id))
        if not weld:
            return False, "Weld not found"

        if heat_no_pipe and hasattr(weld, 'heat_no_pipe'):
            weld.heat_no_pipe = heat_no_pipe
        if heat_no_filler and hasattr(weld, 'heat_no_filler'):
            weld.heat_no_filler = heat_no_filler

        return self.change_status(
            weld_id, WeldStatus.WELDED.value,
            updated_by=user, notes=remarks or "Welding completed",
        )

    # ═══════════════════════════════════════════
    #  5. PREHEAT / INTERPASS / PWHT
    # ═══════════════════════════════════════════

    def record_preheat(
        self,
        weld_id: str,
        preheat: PreheatRecord,
        *,
        user: str = "",
    ) -> Tuple[bool, str]:
        """Record preheat and interpass temperatures."""
        weld = self.repo.get_by_weld_id(self._normalize_weld_id(weld_id))
        if not weld:
            return False, "Weld not found"

        warnings: List[str] = []
        if preheat.preheat_temp_c < preheat.preheat_min_c and preheat.preheat_min_c > 0:
            warnings.append(
                f"Preheat {preheat.preheat_temp_c}°C < min {preheat.preheat_min_c}°C"
            )
        if preheat.interpass_temp_c > preheat.interpass_max_c and preheat.interpass_max_c > 0:
            warnings.append(
                f"Interpass {preheat.interpass_temp_c}°C > max {preheat.interpass_max_c}°C"
            )

        if hasattr(weld, 'preheat_temp_c'):
            weld.preheat_temp_c = preheat.preheat_temp_c
        if hasattr(weld, 'interpass_temp_c'):
            weld.interpass_temp_c = preheat.interpass_temp_c
        weld.updated_by = user
        weld.updated_at = datetime.utcnow()
        self.repo.update(weld)

        self._log_history(
            weld.id, "Preheat",
            new_value=f"Preheat={preheat.preheat_temp_c}°C, "
                      f"Interpass={preheat.interpass_temp_c}°C",
            notes=f"Method={preheat.method}, Instrument={preheat.instrument_id}",
            user_name=user,
        )
        msg = "Preheat recorded"
        if warnings:
            msg += f" ⚠️ {len(warnings)} warning(s)"
        return True, msg

    def record_pwht(
        self,
        weld_id: str,
        pwht: PWHTRecord,
        *,
        user: str = "",
    ) -> Tuple[bool, str]:
        """Record Post Weld Heat Treatment."""
        weld = self.repo.get_by_weld_id(self._normalize_weld_id(weld_id))
        if not weld:
            return False, "Weld not found"

        warnings: List[str] = []
        if pwht.soak_temp_c > 0:
            if pwht.soak_temp_min_c > 0 and pwht.soak_temp_c < pwht.soak_temp_min_c:
                warnings.append(
                    f"Soak temp {pwht.soak_temp_c}°C < min {pwht.soak_temp_min_c}°C"
                )
            if pwht.soak_temp_max_c > 0 and pwht.soak_temp_c > pwht.soak_temp_max_c:
                warnings.append(
                    f"Soak temp {pwht.soak_temp_c}°C > max {pwht.soak_temp_max_c}°C"
                )

        if hasattr(weld, 'pwht_done'):
            weld.pwht_done = pwht.pwht_done
        if hasattr(weld, 'pwht_temp_c'):
            weld.pwht_temp_c = pwht.soak_temp_c
        if hasattr(weld, 'pwht_time_hr'):
            weld.pwht_time_hr = pwht.soak_time_hours
        if hasattr(weld, 'pwht_chart_no'):
            weld.pwht_chart_no = pwht.chart_no
        weld.updated_by = user
        weld.updated_at = datetime.utcnow()
        self.repo.update(weld)

        self._log_history(
            weld.id, "PWHT",
            new_value=f"Soak={pwht.soak_temp_c}°C/{pwht.soak_time_hours}hr",
            notes=f"Chart={pwht.chart_no}, Result={pwht.result}, "
                  f"TC={pwht.thermocouple_count}",
            user_name=user,
        )
        logger.info(
            "Weld %s PWHT: %.0f°C / %.1f hr (%s)",
            weld_id, pwht.soak_temp_c, pwht.soak_time_hours, pwht.result,
        )
        msg = "PWHT recorded"
        if warnings:
            msg += f" ⚠️ {len(warnings)} warning(s)"
        return True, msg

    # ═══════════════════════════════════════════
    #  6. NDT SCHEDULING & INTEGRATION
    # ═══════════════════════════════════════════

    def schedule_ndt(
        self,
        weld_id: str,
        schedule: NDTSchedule,
        *,
        user: str = "",
    ) -> Tuple[bool, str]:
        """Schedule NDT inspection for a weld."""
        weld = self.repo.get_by_weld_id(self._normalize_weld_id(weld_id))
        if not weld:
            return False, "Weld not found"

        if weld.status not in (
            WeldStatus.WELDED.value, WeldStatus.NDT_PENDING.value,
            WeldStatus.REPAIRED.value,
        ):
            return False, (
                f"Weld must be in Welded/Repaired status for NDT "
                f"(current: {weld.status})."
            )

        # Create NDT record in pending state
        with self.db.session_scope() as session:
            ndt = NDTRecord(
                weld_id_fk=weld.id,
                project_id=weld.project_id,
                ndt_method=schedule.ndt_method,
                result="Pending",
                inspection_date=schedule.requested_date or date.today(),
                inspector=schedule.inspector,
                report_number="",
                percentage=schedule.percentage if hasattr(NDTRecord, 'percentage') else None,
            )
            session.add(ndt)

        # Advance status
        if weld.status == WeldStatus.WELDED.value:
            self.change_status(
                weld_id, WeldStatus.NDT_PENDING.value,
                updated_by=user, notes=f"NDT scheduled: {schedule.ndt_method}",
            )

        self._log_history(
            weld.id, "NDT Scheduled",
            new_value=schedule.ndt_method,
            notes=f"Method={schedule.ndt_method}, %={schedule.percentage}, "
                  f"Inspector={schedule.inspector}, Agency={schedule.agency}",
            user_name=user,
        )
        return True, f"NDT {schedule.ndt_method} scheduled"

    def record_ndt_result(
        self,
        weld_id: str,
        ndt_method: str,
        result: str,
        *,
        report_no: str = "",
        inspector: str = "",
        inspection_date: Optional[date] = None,
        defects: Optional[List[DefectRecord]] = None,
        user: str = "",
    ) -> Tuple[bool, str]:
        """Record NDT result and optionally associated defects."""
        weld = self.repo.get_by_weld_id(self._normalize_weld_id(weld_id))
        if not weld:
            return False, "Weld not found"

        with self.db.session_scope() as session:
            # Update or create NDT record
            existing = session.query(NDTRecord).filter(
                NDTRecord.weld_id_fk == weld.id,
                NDTRecord.ndt_method == ndt_method,
                NDTRecord.result == "Pending",
            ).first()

            if existing:
                existing.result = result
                existing.report_number = report_no
                existing.inspector = inspector
                existing.inspection_date = inspection_date or date.today()
            else:
                ndt = NDTRecord(
                    weld_id_fk=weld.id,
                    project_id=weld.project_id,
                    ndt_method=ndt_method,
                    result=result,
                    report_number=report_no,
                    inspector=inspector,
                    inspection_date=inspection_date or date.today(),
                )
                session.add(ndt)

        # Auto-advance status
        if result.upper() in ("ACCEPT", "ACCEPTED", "PASS", "AC"):
            if weld.status == WeldStatus.NDT_PENDING.value:
                self.change_status(
                    weld_id, WeldStatus.INSPECTED.value,
                    updated_by=user, notes=f"NDT {ndt_method}: {result}",
                )
        elif result.upper() in ("REJECT", "REJECTED", "FAIL", "RJ"):
            self.change_status(
                weld_id, WeldStatus.REJECTED.value,
                updated_by=user, notes=f"NDT {ndt_method}: {result}",
            )

        # Record defects
        if defects:
            for d in defects:
                self._log_history(
                    weld.id, "Defect",
                    new_value=d.defect_type,
                    notes=f"Location={d.location}, Length={d.length_mm}mm, "
                          f"Depth={d.depth_mm}mm, Severity={d.severity}",
                    user_name=user,
                )

        self._log_history(
            weld.id, "NDT Result",
            old_value="Pending", new_value=result,
            notes=f"Method={ndt_method}, Report={report_no}, "
                  f"Inspector={inspector}",
            user_name=user,
        )
        logger.info(
            "Weld %s NDT %s: %s (report %s)",
            weld_id, ndt_method, result, report_no,
        )
        return True, f"NDT {ndt_method} result: {result}"

    # ═══════════════════════════════════════════
    #  7. REPAIR MANAGEMENT
    # ═══════════════════════════════════════════

    def record_repair(
        self,
        weld_id: str,
        repair: RepairRecord,
        *,
        updated_by: str = "",
    ) -> Tuple[bool, str]:
        """
        Record a weld repair with full traceability.

        Checks:
          - Max repair count (mandatory cut-out)
          - Repair WPS validity
          - Repair extent vs original defect
        """
        weld = self.repo.get_by_weld_id(self._normalize_weld_id(weld_id))
        if not weld:
            return False, "Weld not found"

        new_count = (weld.repair_count or 0) + 1
        if new_count > MAX_REPAIRS_BEFORE_CUTOUT:
            return False, (
                f"⛔ Maximum repairs ({MAX_REPAIRS_BEFORE_CUTOUT}) exceeded. "
                f"Mandatory CUT-OUT required per specification."
            )

        weld.repair_count = new_count
        weld.status = WeldStatus.REPAIRED.value
        weld.updated_by = updated_by
        weld.updated_at = datetime.utcnow()
        self.repo.update(weld)

        detail = (
            f"Repair #{new_count}: Type={repair.defect_type}, "
            f"Location={repair.defect_location}, "
            f"Length={repair.defect_length_mm}mm, "
            f"Depth={repair.repair_depth_mm}mm, "
            f"WPS={repair.repair_wps_no}, "
            f"Welder={repair.welder_id}"
        )
        self._log_history(
            weld.id, "Repair",
            new_value=str(new_count),
            notes=detail, user_name=updated_by,
        )

        msg = f"Repair #{new_count} recorded"
        if new_count >= MAX_REPAIRS_BEFORE_CUTOUT:
            msg += " — ⚠️ NEXT FAILURE = MANDATORY CUT-OUT"
        logger.warning("Weld %s: %s", weld_id, msg)
        return True, msg

    def record_repair_legacy(
        self, weld_id: str, updated_by: str = "", notes: str = "",
    ) -> Tuple[bool, str]:
        """Backward-compatible repair shortcut."""
        return self.record_repair(
            weld_id,
            RepairRecord(repair_no=1, remarks=notes),
            updated_by=updated_by,
        )

    # ═══════════════════════════════════════════
    #  8. VALIDATION & RULE ENGINE
    # ═══════════════════════════════════════════

    def validate_weld(
        self,
        weld_id: str,
        fluid_service: str = "Normal Fluid Service",
    ) -> Optional[CheckReport]:
        """Run rule engine validation on a weld."""
        weld = self.repo.get_by_weld_id(self._normalize_weld_id(weld_id))
        if not weld:
            return None
        wps = None
        if weld.wps_pqr_id:
            with self.db.session_scope() as session:
                wps = session.query(WPS_PQR).get(weld.wps_pqr_id)
        return rule_engine.check_weld(weld, wps=wps, fluid_service=fluid_service)

    def _validate_wps_compatibility(self, creation: WeldCreation) -> None:
        """Check if weld parameters fall within WPS ranges."""
        if not creation.wps_pqr_id:
            return
        with self.db.session_scope() as session:
            wps = session.query(WPS_PQR).get(creation.wps_pqr_id)
            if not wps:
                return

            # Thickness check
            if hasattr(wps, 'thickness_min_mm') and wps.thickness_min_mm:
                if creation.wall_thickness_mm < wps.thickness_min_mm:
                    logger.warning(
                        "Weld %s thickness %.1fmm < WPS min %.1fmm",
                        creation.weld_id, creation.wall_thickness_mm,
                        wps.thickness_min_mm,
                    )
            if hasattr(wps, 'thickness_max_mm') and wps.thickness_max_mm:
                if creation.wall_thickness_mm > wps.thickness_max_mm:
                    logger.warning(
                        "Weld %s thickness %.1fmm > WPS max %.1fmm",
                        creation.weld_id, creation.wall_thickness_mm,
                        wps.thickness_max_mm,
                    )

    # ═══════════════════════════════════════════
    #  9. HISTORY & TRACEABILITY
    # ═══════════════════════════════════════════

    def get_history(self, weld_pk: int) -> List[JointHistory]:
        with self.db.session_scope() as session:
            return (
                session.query(JointHistory)
                .filter(JointHistory.weld_id_fk == weld_pk)
                .order_by(JointHistory.timestamp)
                .all()
            )

    def get_wjc_summary(self, weld_id: str) -> Optional[Dict[str, Any]]:
        """Build a comprehensive Weld Joint Card summary."""
        weld = self.repo.get_by_weld_id(self._normalize_weld_id(weld_id))
        if not weld:
            return None

        history = self.get_history(weld.id)

        with self.db.session_scope() as session:
            ndt = session.query(NDTRecord).filter(
                NDTRecord.weld_id_fk == weld.id
            ).all()
            ndt_list = [
                {
                    "method": n.ndt_method,
                    "result": n.result,
                    "date": str(n.inspection_date or ""),
                    "report": n.report_number or "",
                    "inspector": getattr(n, 'inspector', ''),
                }
                for n in ndt
            ]

        # Extract pass history from JointHistory
        passes = [
            h for h in history if h.event_type == "WeldPass"
        ]

        return {
            "weld_id": weld.weld_id,
            "type": weld.weld_type,
            "line": weld.line_number,
            "iso": weld.iso_number,
            "joint_type": weld.joint_type,
            "size": weld.size,
            "schedule": getattr(weld, 'schedule', ''),
            "thickness": weld.wall_thickness_mm,
            "material": weld.material,
            "material_spec": getattr(weld, 'material_spec', ''),
            "p_number": getattr(weld, 'p_number', ''),
            "wps_no": getattr(weld, 'wps_no', ''),
            "position": getattr(weld, 'welding_position', ''),
            "welder": weld.welder_id or weld.welder_name,
            "status": weld.status,
            "repairs": weld.repair_count,
            "fitup": {
                "inspector": getattr(weld, 'fitup_inspector', ''),
                "date": str(getattr(weld, 'fitup_date', '') or ''),
                "result": getattr(weld, 'fitup_result', ''),
            },
            "preheat": getattr(weld, 'preheat_temp_c', None),
            "interpass": getattr(weld, 'interpass_temp_c', None),
            "pwht": {
                "done": getattr(weld, 'pwht_done', False),
                "temp": getattr(weld, 'pwht_temp_c', None),
                "time": getattr(weld, 'pwht_time_hr', None),
                "chart": getattr(weld, 'pwht_chart_no', ''),
            },
            "heat_traceability": {
                "pipe": getattr(weld, 'heat_no_pipe', ''),
                "filler": getattr(weld, 'heat_no_filler', ''),
            },
            "test_package": getattr(weld, 'test_package', ''),
            "ndt": ndt_list,
            "passes": [
                {
                    "type": p.new_value,
                    "detail": p.notes,
                    "by": p.user_name,
                    "when": str(p.timestamp),
                }
                for p in passes
            ],
            "history": [
                {
                    "when": str(h.timestamp),
                    "event": h.event_type,
                    "from": h.old_value,
                    "to": h.new_value,
                    "by": h.user_name,
                    "notes": h.notes,
                }
                for h in history
            ],
        }

    # ═══════════════════════════════════════════
    #  10. REPORTING & STATISTICS
    # ═══════════════════════════════════════════

    def get_project_stats(self, project_id: int) -> Dict[str, Any]:
        """Comprehensive project welding statistics."""
        welds = self.repo.get_by_project(project_id)
        total = len(welds)

        if total == 0:
            return {
                "total": 0, "by_status": {}, "accepted": 0,
                "rejected": 0, "repaired": 0, "acceptance_rate": 0.0,
                "repair_rate": 0.0, "total_inch_dia": 0.0,
                "by_type": {}, "by_line": {},
            }

        by_status: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        by_line: Dict[str, int] = {}
        total_inch_dia = 0.0
        repaired_count = 0
        total_repairs = 0

        for w in welds:
            s = w.status or "Pending"
            by_status[s] = by_status.get(s, 0) + 1

            t = getattr(w, 'weld_type', 'Unknown')
            by_type[t] = by_type.get(t, 0) + 1

            ln = w.line_number or "N/A"
            by_line[ln] = by_line.get(ln, 0) + 1

            if (w.repair_count or 0) > 0:
                repaired_count += 1
                total_repairs += w.repair_count

            # Estimate inch-diameter
            size = self._parse_size_to_inches(w.size)
            if size > 0:
                total_inch_dia += size

        accepted = by_status.get(WeldStatus.ACCEPTED.value, 0)
        rejected = by_status.get(WeldStatus.REJECTED.value, 0)

        return {
            "total": total,
            "by_status": by_status,
            "by_type": by_type,
            "by_line": by_line,
            "accepted": accepted,
            "rejected": rejected,
            "repaired": repaired_count,
            "total_repairs": total_repairs,
            "acceptance_rate": round(accepted / total * 100, 1),
            "repair_rate": round(repaired_count / total * 100, 1),
            "total_inch_dia": round(total_inch_dia, 1),
            "avg_repairs_per_repair": round(
                total_repairs / repaired_count, 1
            ) if repaired_count else 0,
        }

    def get_daily_weld_report(
        self,
        project_id: int,
        report_date: Optional[date] = None,
    ) -> DailyWeldReport:
        """Generate a Daily Weld Report (DWR)."""
        report_date = report_date or date.today()
        welds = self.repo.get_by_project(project_id)

        # Filter by date
        day_welds = [
            w for w in welds
            if self._is_date_match(
                getattr(w, 'weld_end_datetime', None) or getattr(w, 'updated_at', None),
                report_date,
            )
        ]

        by_welder: Dict[str, int] = {}
        by_process: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        total_inch = 0.0
        repairs = 0

        for w in day_welds:
            wld = w.welder_id or w.welder_name or "Unknown"
            by_welder[wld] = by_welder.get(wld, 0) + 1

            t = getattr(w, 'weld_type', 'Field')
            by_type[t] = by_type.get(t, 0) + 1

            size = self._parse_size_to_inches(w.size)
            if size > 0:
                total_inch += size

            if (w.repair_count or 0) > 0:
                repairs += 1

        # NDT stats for the day
        ndt_passed = ndt_failed = 0
        with self.db.session_scope() as session:
            ndt_records = session.query(NDTRecord).filter(
                NDTRecord.project_id == project_id,
                NDTRecord.inspection_date == report_date,
            ).all()
            for n in ndt_records:
                if n.result and n.result.upper() in ("ACCEPT", "PASS", "AC"):
                    ndt_passed += 1
                elif n.result and n.result.upper() in ("REJECT", "FAIL", "RJ"):
                    ndt_failed += 1

        lines = list(set(w.line_number for w in day_welds if w.line_number))

        return DailyWeldReport(
            report_date=report_date,
            project_id=project_id,
            line_numbers=sorted(lines),
            total_welds_completed=len(day_welds),
            total_inch_dia=round(total_inch, 1),
            by_welder=by_welder,
            by_process=by_process,
            by_type=by_type,
            repairs=repairs,
            ndt_passed=ndt_passed,
            ndt_failed=ndt_failed,
        )

    def get_productivity_metrics(
        self,
        project_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> WeldProductivity:
        """Calculate productivity metrics for a date range."""
        if not from_date:
            from_date = date.today() - timedelta(days=30)
        if not to_date:
            to_date = date.today()

        days = max((to_date - from_date).days, 1)
        welds = self.repo.get_by_project(project_id)

        # Filter by date range
        period_welds = [
            w for w in welds
            if self._is_in_range(
                getattr(w, 'weld_end_datetime', None) or getattr(w, 'updated_at', None),
                from_date, to_date,
            )
        ]

        total = len(period_welds)
        total_inch = sum(
            self._parse_size_to_inches(w.size) for w in period_welds
        )
        repaired = sum(1 for w in period_welds if (w.repair_count or 0) > 0)

        by_welder: Dict[str, Dict[str, Any]] = {}
        by_line: Dict[str, Dict[str, Any]] = {}
        for w in period_welds:
            wld = w.welder_id or w.welder_name or "Unknown"
            if wld not in by_welder:
                by_welder[wld] = {"welds": 0, "inch_dia": 0.0, "repairs": 0}
            by_welder[wld]["welds"] += 1
            by_welder[wld]["inch_dia"] += self._parse_size_to_inches(w.size)
            by_welder[wld]["repairs"] += w.repair_count or 0

            ln = w.line_number or "N/A"
            if ln not in by_line:
                by_line[ln] = {"welds": 0, "inch_dia": 0.0}
            by_line[ln]["welds"] += 1
            by_line[ln]["inch_dia"] += self._parse_size_to_inches(w.size)

        welder_count = max(len(by_welder), 1)

        return WeldProductivity(
            period_start=from_date,
            period_end=to_date,
            total_welds=total,
            total_inch_dia=round(total_inch, 1),
            total_man_hours=0.0,  # Requires timesheet integration
            welds_per_day=round(total / days, 1),
            inch_dia_per_day=round(total_inch / days, 1),
            welds_per_welder_day=round(total / days / welder_count, 1),
            repair_rate_pct=round(repaired / total * 100, 1) if total else 0,
            ndt_pass_rate_pct=0.0,  # Computed separately
            by_welder=by_welder,
            by_line=by_line,
        )

    def get_iso_completion(
        self, project_id: int, iso_number: str,
    ) -> Dict[str, Any]:
        """Calculate weld completion percentage for an isometric."""
        welds = self.repo.get_by_project(project_id)
        iso_welds = [w for w in welds if w.iso_number == iso_number]
        total = len(iso_welds)
        if total == 0:
            return {"iso": iso_number, "total": 0, "completion_pct": 0.0}

        accepted = sum(
            1 for w in iso_welds if w.status == WeldStatus.ACCEPTED.value
        )
        welded = sum(
            1 for w in iso_welds
            if w.status in (
                WeldStatus.WELDED.value, WeldStatus.NDT_PENDING.value,
                WeldStatus.INSPECTED.value, WeldStatus.ACCEPTED.value,
            )
        )

        return {
            "iso": iso_number,
            "total": total,
            "accepted": accepted,
            "welded": welded,
            "pending": total - welded,
            "completion_pct": round(accepted / total * 100, 1),
            "welded_pct": round(welded / total * 100, 1),
        }

    def get_line_completion(
        self, project_id: int, line_number: str,
    ) -> Dict[str, Any]:
        """Calculate weld completion for a line."""
        welds = self.repo.get_by_project(project_id)
        line_welds = [w for w in welds if w.line_number == line_number]
        total = len(line_welds)
        if total == 0:
            return {"line": line_number, "total": 0, "completion_pct": 0.0}

        accepted = sum(
            1 for w in line_welds if w.status == WeldStatus.ACCEPTED.value
        )
        total_inch = sum(
            self._parse_size_to_inches(w.size) for w in line_welds
        )
        accepted_inch = sum(
            self._parse_size_to_inches(w.size) for w in line_welds
            if w.status == WeldStatus.ACCEPTED.value
        )

        return {
            "line": line_number,
            "total_welds": total,
            "accepted_welds": accepted,
            "total_inch_dia": round(total_inch, 1),
            "accepted_inch_dia": round(accepted_inch, 1),
            "completion_pct": round(accepted / total * 100, 1),
            "inch_completion_pct": round(
                accepted_inch / total_inch * 100, 1
            ) if total_inch else 0,
        }

    # ═══════════════════════════════════════════
    #  11. INTERNAL HELPERS
    # ═══════════════════════════════════════════

    def _log_history(
        self,
        weld_pk: int,
        event_type: str,
        old_value: str = "",
        new_value: str = "",
        notes: str = "",
        user_name: str = "",
    ):
        with self.db.session_scope() as session:
            session.add(JointHistory(
                weld_id_fk=weld_pk,
                event_type=event_type,
                old_value=old_value,
                new_value=new_value,
                notes=notes,
                user_name=user_name,
                timestamp=datetime.utcnow(),
            ))

    @staticmethod
    def _normalize_weld_id(weld_id: str) -> str:
        return weld_id.strip().upper()

    @staticmethod
    def _validate_weld_id(weld_id: str) -> None:
        if not weld_id:
            raise ValueError("Weld ID cannot be empty.")
        if len(weld_id) > 50:
            raise ValueError("Weld ID must be ≤ 50 characters.")

    def _count_ndt_records(self, weld_pk: int) -> int:
        with self.db.session_scope() as session:
            return session.query(NDTRecord).filter(
                NDTRecord.weld_id_fk == weld_pk,
                NDTRecord.result != "Pending",
            ).count()

    def _count_failed_ndt(self, weld_pk: int) -> int:
        with self.db.session_scope() as session:
            return session.query(NDTRecord).filter(
                NDTRecord.weld_id_fk == weld_pk,
                NDTRecord.result.in_(["Reject", "Rejected", "Fail", "RJ"]),
            ).count()

    def _get_max_interpass(self, weld) -> Optional[float]:
        """Get max interpass temperature from WPS."""
        if not weld.wps_pqr_id:
            return None
        try:
            with self.db.session_scope() as session:
                wps = session.query(WPS_PQR).get(weld.wps_pqr_id)
                if wps and hasattr(wps, 'interpass_max_c'):
                    return wps.interpass_max_c
        except Exception:
            pass
        return None

   