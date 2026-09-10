# -*- coding: utf-8 -*-
"""
valve_service.py - PipeAgent
==============================
Comprehensive Valve Lifecycle Management Service
-------------------------------------------------
Covers the full valve lifecycle from procurement receipt through
shop testing, site testing, installation, preservation, and
commissioning in accordance with:

  • API 598   – Valve Inspection and Testing
  • API 6D    – Pipeline Valves
  • ASME B16.34 – Valves (Flanged, Threaded, Welding End)
  • ISO 5208  – Industrial Valves – Pressure Testing

Features:
  • Full status state-machine (8 states)
  • All API 598 test types (shell, seat, backseat, LP closure, pneumatic)
  • Functional tests (torque, cycle, ESD)
  • Bulk registration from line-list / CSV
  • Weighted readiness scoring
  • Multi-dimensional reporting (by type, size, class, system, status)
  • Certificate & MTR linkage
  • Preservation tracking
  • Full audit trail
  • Data validation & pressure checks

Author : PipeAgent Engineering
Version: 5.0.0
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
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
from repositories.valve_repository import ValveRepository

logger = logging.getLogger("pipeagent.services.valve")


# ─────────────────────────────────────────────
#  Enums
# ─────────────────────────────────────────────

class ValveType(str, Enum):
    GATE = "Gate"
    GLOBE = "Globe"
    BALL = "Ball"
    CHECK = "Check"
    BUTTERFLY = "Butterfly"
    PLUG = "Plug"
    NEEDLE = "Needle"
    DIAPHRAGM = "Diaphragm"
    CONTROL = "Control"
    SAFETY_RELIEF = "Safety/Relief"
    OTHER = "Other"


class ValveEnd(str, Enum):
    FLANGED = "Flanged"
    BUTT_WELD = "Butt Weld"
    SOCKET_WELD = "Socket Weld"
    THREADED = "Threaded"
    WAFER = "Wafer"
    LUG = "Lug"
    CLAMP = "Clamp"


class ValveStatus(str, Enum):
    """Full lifecycle state machine."""
    ORDERED = "Ordered"
    RECEIVED = "Received"
    SHOP_TESTED = "Shop Tested"
    SITE_RECEIVED = "Site Received"
    SITE_TESTED = "Site Tested"
    INSTALLED = "Installed"
    PRESERVED = "Preserved"
    COMMISSIONED = "Commissioned"
    DEFECTIVE = "Defective"
    REJECTED = "Rejected"


# Valid transitions
_ALLOWED_TRANSITIONS: Dict[ValveStatus, List[ValveStatus]] = {
    ValveStatus.ORDERED:       [ValveStatus.RECEIVED, ValveStatus.REJECTED],
    ValveStatus.RECEIVED:      [ValveStatus.SHOP_TESTED, ValveStatus.SITE_RECEIVED,
                                ValveStatus.DEFECTIVE, ValveStatus.REJECTED],
    ValveStatus.SHOP_TESTED:   [ValveStatus.SITE_RECEIVED, ValveStatus.DEFECTIVE],
    ValveStatus.SITE_RECEIVED: [ValveStatus.SITE_TESTED, ValveStatus.INSTALLED,
                                ValveStatus.DEFECTIVE],
    ValveStatus.SITE_TESTED:   [ValveStatus.INSTALLED, ValveStatus.DEFECTIVE],
    ValveStatus.INSTALLED:     [ValveStatus.PRESERVED, ValveStatus.COMMISSIONED,
                                ValveStatus.DEFECTIVE],
    ValveStatus.PRESERVED:     [ValveStatus.COMMISSIONED, ValveStatus.DEFECTIVE],
    ValveStatus.COMMISSIONED:  [],
    ValveStatus.DEFECTIVE:     [ValveStatus.RECEIVED, ValveStatus.REJECTED],
    ValveStatus.REJECTED:      [],
}


class TestType(str, Enum):
    """API 598 test types."""
    SHELL = "Shell"
    HIGH_PRESSURE_SEAT = "High Pressure Seat"
    LOW_PRESSURE_CLOSURE = "Low Pressure Closure"
    BACKSEAT = "Backseat"
    PNEUMATIC_SHELL = "Pneumatic Shell"
    PNEUMATIC_SEAT = "Pneumatic Seat"
    FUNCTIONAL_TORQUE = "Functional Torque"
    FUNCTIONAL_CYCLE = "Functional Cycle"
    ESD_TEST = "ESD Test"
    FIRE_SAFE = "Fire Safe"


class TestMedium(str, Enum):
    WATER = "Water"
    AIR = "Air"
    NITROGEN = "Nitrogen"
    GLYCOL = "Glycol"
    SERVICE_FLUID = "Service Fluid"


class TestResult(str, Enum):
    PASS = "Pass"
    FAIL = "Fail"
    CONDITIONAL = "Conditional"


# ─────────────────────────────────────────────
#  Data Classes
# ─────────────────────────────────────────────

@dataclass
class ValveRegistration:
    """Input DTO for registering a new valve."""
    valve_tag: str
    valve_type: str = ValveType.GATE.value
    size_nps: str = ""
    pressure_class: str = ""
    end_connection: str = ValveEnd.FLANGED.value
    body_material: str = ""
    trim_material: str = ""
    manufacturer: str = ""
    model_no: str = ""
    serial_no: str = ""
    heat_no: str = ""
    mtr_no: str = ""
    line_number: str = ""
    system: str = ""
    p_and_id_ref: str = ""
    design_pressure_barg: float = 0.0
    design_temp_c: float = 0.0
    weight_kg: float = 0.0
    remarks: str = ""


@dataclass
class ValveTestRecord:
    """Input DTO for recording any valve test."""
    test_type: str
    test_medium: str = TestMedium.WATER.value
    test_pressure_bar: float = 0.0
    holding_time_sec: int = 0
    allowable_leakage: str = ""        # e.g. "Zero", "API 598 Table 5"
    actual_leakage: str = ""
    result: str = TestResult.PASS.value
    witness: str = ""
    client_witness: str = ""
    gauge_id: str = ""
    certificate_no: str = ""
    test_date: Optional[date] = None
    remarks: str = ""


@dataclass
class ValveSummary:
    """Lightweight summary for dashboards."""
    valve_id: int
    valve_tag: str
    valve_type: str
    size_nps: str
    pressure_class: str
    line_number: str
    status: str
    shell_tested: bool
    seat_tested: bool
    installed: bool


@dataclass
class ValveReport:
    """Multi-dimensional report output."""
    project_id: int
    total: int
    by_status: Dict[str, int]
    by_type: Dict[str, int]
    by_size: Dict[str, int]
    by_system: Dict[str, int]
    test_coverage: Dict[str, Any]
    installed_pct: float
    overall_readiness_pct: float
    critical_gaps: List[str]


# ─────────────────────────────────────────────
#  Main Service
# ─────────────────────────────────────────────

class ValveService:
    """
    Enterprise-grade Valve Lifecycle Management.

    Usage:
        svc = ValveService(session)
        svc.register_valve(project_id=1, valve_tag="XV-1001", valve_type="Ball", ...)
        svc.record_test(valve_id=42, record=ValveTestRecord(...))
        report = svc.get_comprehensive_report(project_id=1)
    """

    def __init__(self, session: Session):
        self.repo = ValveRepository(session)
        self.session = session

    # ═══════════════════════════════════════════
    #  1. REGISTRATION
    # ═══════════════════════════════════════════

    def register_valve(
        self,
        project_id: int,
        valve_tag: str,
        **kwargs,
    ) -> Any:
        """Register a single valve with full validation."""
        tag = self._normalize_tag(valve_tag)
        self._validate_tag(tag)

        existing = self.repo.find_by_tag(project_id, tag)
        if existing:
            raise AppError(f"Valve tag '{tag}' is already registered in project {project_id}.")

        # Validate type if provided
        vtype = kwargs.get("valve_type", ValveType.GATE.value)
        self._validate_valve_type(vtype)

        # Validate pressures
        dp = kwargs.get("design_pressure_barg", 0)
        if dp < 0:
            raise ValidationError("Design pressure cannot be negative.")

        data = {
            "project_id": project_id,
            "valve_tag": tag,
            "valve_type": vtype,
            "status": ValveStatus.ORDERED.value,
            "registered_at": datetime.utcnow(),
            **kwargs,
        }
        # Clean out None values for optional fields
        data = {k: v for k, v in data.items() if v is not None}

        valve = self.repo.add_valve(**data)
        logger.info("Registered valve %s (type=%s, project=%s)", tag, vtype, project_id)
        self._audit(valve, "REGISTER", f"Valve {tag} registered")
        return valve

    def bulk_register(
        self,
        project_id: int,
        records: List[Dict[str, Any]],
    ) -> Tuple[int, int, List[str]]:
        """
        Bulk-register valves from a list of dicts (e.g. parsed CSV).

        Returns: (added_count, skipped_count, error_messages)
        """
        added = 0
        skipped = 0
        errors: List[str] = []

        for i, rec in enumerate(records, 1):
            tag = rec.get("valve_tag", "").strip()
            if not tag:
                errors.append(f"Row {i}: Missing valve_tag.")
                skipped += 1
                continue
            try:
                self.register_valve(project_id, tag, **{
                    k: v for k, v in rec.items() if k != "valve_tag"
                })
                added += 1
            except AppError as e:
                errors.append(f"Row {i} ({tag}): {e}")
                skipped += 1
            except Exception as e:
                errors.append(f"Row {i} ({tag}): Unexpected — {e}")
                skipped += 1

        logger.info(
            "Bulk register project %s: %d added, %d skipped", project_id, added, skipped
        )
        return added, skipped, errors

    def bulk_register_from_csv(
        self,
        project_id: int,
        csv_text: str,
    ) -> Tuple[int, int, List[str]]:
        """Parse CSV text and bulk-register valves."""
        reader = csv.DictReader(StringIO(csv_text))
        records = [row for row in reader]
        return self.bulk_register(project_id, records)

    # ═══════════════════════════════════════════
    #  2. TESTING — Full API 598 Support
    # ═══════════════════════════════════════════

    def record_test(
        self,
        valve_id: int,
        record: ValveTestRecord,
    ) -> Any:
        """
        Record any type of valve test (shell, seat, backseat, pneumatic, etc.).

        This is the unified test recording method replacing the old
        record_shell_test / record_seat_test methods.
        """
        valve = self._get_valve_or_raise(valve_id)
        self._validate_test_record(record)

        # Determine field mapping based on test type
        update_fields = self._map_test_to_fields(record)
        update_fields["last_test_date"] = record.test_date or date.today()
        update_fields["last_test_witness"] = record.witness

        # Auto-advance status if applicable
        new_status = self._auto_advance_status_on_test(valve, record)
        if new_status:
            update_fields["status"] = new_status.value

        result = self.repo.edit_valve(valve_id, **update_fields)
        logger.info(
            "Valve %s: %s test → %s (%.1f bar, %ds)",
            valve.valve_tag, record.test_type, record.result,
            record.test_pressure_bar, record.holding_time_sec,
        )
        self._audit(
            valve, "TEST",
            f"{record.test_type}: {record.result} @ {record.test_pressure_bar} bar"
        )
        return result

    # ── Convenience wrappers (backward compat) ──

    def record_shell_test(
        self, valve_id: int, pressure_bar: float, witness: str = "",
    ) -> Any:
        """Backward-compatible shell test shortcut."""
        return self.record_test(valve_id, ValveTestRecord(
            test_type=TestType.SHELL.value,
            test_pressure_bar=pressure_bar,
            holding_time_sec=self._default_hold_time(TestType.SHELL),
            witness=witness,
            result=TestResult.PASS.value,
        ))

    def record_seat_test(
        self, valve_id: int, pressure_bar: float, witness: str = "",
    ) -> Any:
        """Backward-compatible seat test shortcut."""
        return self.record_test(valve_id, ValveTestRecord(
            test_type=TestType.HIGH_PRESSURE_SEAT.value,
            test_pressure_bar=pressure_bar,
            holding_time_sec=self._default_hold_time(TestType.HIGH_PRESSURE_SEAT),
            witness=witness,
            result=TestResult.PASS.value,
        ))

    def record_backseat_test(
        self, valve_id: int, pressure_bar: float, witness: str = "",
    ) -> Any:
        """Record backseat test (API 598 §6.3)."""
        return self.record_test(valve_id, ValveTestRecord(
            test_type=TestType.BACKSEAT.value,
            test_pressure_bar=pressure_bar,
            holding_time_sec=self._default_hold_time(TestType.BACKSEAT),
            witness=witness,
            result=TestResult.PASS.value,
        ))

    def record_pneumatic_test(
        self, valve_id: int, pressure_bar: float, witness: str = "",
    ) -> Any:
        """Record pneumatic shell test (API 598 §6.4)."""
        return self.record_test(valve_id, ValveTestRecord(
            test_type=TestType.PNEUMATIC_SHELL.value,
            test_medium=TestMedium.AIR.value,
            test_pressure_bar=pressure_bar,
            holding_time_sec=self._default_hold_time(TestType.PNEUMATIC_SHELL),
            witness=witness,
            result=TestResult.PASS.value,
        ))

    def record_functional_test(
        self,
        valve_id: int,
        torque_nm: float = 0.0,
        cycles: int = 0,
        witness: str = "",
    ) -> Any:
        """Record functional torque + cycle test."""
        return self.record_test(valve_id, ValveTestRecord(
            test_type=TestType.FUNCTIONAL_TORQUE.value,
            test_pressure_bar=0,
            holding_time_sec=cycles,
            witness=witness,
            result=TestResult.PASS.value,
            remarks=f"Torque={torque_nm} Nm, Cycles={cycles}",
        ))

    # ═══════════════════════════════════════════
    #  3. STATUS LIFECYCLE
    # ═══════════════════════════════════════════

    def transition_status(
        self,
        valve_id: int,
        new_status: str,
        *,
        user: str = "",
        remarks: str = "",
    ) -> Any:
        """Advance valve through its lifecycle state machine."""
        valve = self._get_valve_or_raise(valve_id)
        current = ValveStatus(valve.status)
        target = ValveStatus(new_status)

        if target not in _ALLOWED_TRANSITIONS.get(current, []):
            raise StateTransitionError(
                f"Valve {valve.valve_tag}: Cannot transition "
                f"{current.value} → {target.value}."
            )

        # Pre-transition guards
        if target == ValveStatus.SHOP_TESTED:
            self._assert_shell_tested(valve)
        elif target == ValveStatus.INSTALLED:
            self._assert_tested(valve)
        elif target == ValveStatus.COMMISSIONED:
            self._assert_installed(valve)

        result = self.repo.edit_valve(valve_id, status=target.value)
        logger.info(
            "Valve %s: %s → %s (by %s)",
            valve.valve_tag, current.value, target.value, user,
        )
        self._audit(
            valve, "STATUS",
            f"{current.value} → {target.value} by {user}: {remarks}"
        )
        return result

    def mark_received(
        self, valve_id: int, received_by: str = "",
    ) -> Any:
        return self.transition_status(
            valve_id, ValveStatus.RECEIVED.value, user=received_by,
        )

    def mark_installed(
        self, valve_id: int, installed_by: str = "",
    ) -> Any:
        """Backward-compatible install shortcut."""
        valve = self._get_valve_or_raise(valve_id)
        result = self.repo.edit_valve(
            valve_id,
            installed_date=date.today(),
            installed_by=installed_by,
            status=ValveStatus.INSTALLED.value,
        )
        self._audit(valve, "INSTALL", f"Installed by {installed_by}")
        return result

    def mark_preserved(
        self,
        valve_id: int,
        preservation_type: str = "",
        next_due_date: Optional[date] = None,
        preserved_by: str = "",
    ) -> Any:
        """Record preservation action (greasing, capping, nitrogen blanket)."""
        valve = self._get_valve_or_raise(valve_id)
        result = self.repo.edit_valve(
            valve_id,
            status=ValveStatus.PRESERVED.value,
            preservation_type=preservation_type,
            preservation_date=date.today(),
            preservation_next_due=next_due_date,
            preserved_by=preserved_by,
        )
        self._audit(
            valve, "PRESERVE",
            f"Type={preservation_type}, Next={next_due_date}"
        )
        return result

    def mark_commissioned(
        self, valve_id: int, commissioned_by: str = "",
    ) -> Any:
        return self.transition_status(
            valve_id, ValveStatus.COMMISSIONED.value, user=commissioned_by,
        )

    def mark_defective(
        self, valve_id: int, reason: str = "", reported_by: str = "",
    ) -> Any:
        return self.transition_status(
            valve_id, ValveStatus.DEFECTIVE.value,
            user=reported_by, remarks=reason,
        )

    # ═══════════════════════════════════════════
    #  4. QUERIES
    # ═══════════════════════════════════════════

    def get_valve(self, valve_id: int) -> Any:
        return self._get_valve_or_raise(valve_id)

    def get_valve_by_tag(
        self, project_id: int, valve_tag: str,
    ) -> Any:
        tag = self._normalize_tag(valve_tag)
        valve = self.repo.find_by_tag(project_id, tag)
        if not valve:
            raise NotFoundError(f"Valve '{tag}' not found in project {project_id}.")
        return valve

    def list_valves(
        self,
        project_id: int,
        *,
        status: Optional[str] = None,
        valve_type: Optional[str] = None,
        line_number: Optional[str] = None,
        system: Optional[str] = None,
        size_nps: Optional[str] = None,
        search: str = "",
        limit: int = 500,
        offset: int = 0,
    ) -> List[Any]:
        """Filtered valve listing with multiple criteria."""
        return self.repo.list_valves(
            project_id,
            status=status,
            valve_type=valve_type,
            line_number=line_number,
            system=system,
            size_nps=size_nps,
            search=search.strip(),
            limit=limit,
            offset=offset,
        )

    # ═══════════════════════════════════════════
    #  5. REPORTING
    # ═══════════════════════════════════════════

    def get_test_status_report(self, project_id: int) -> Dict[str, Any]:
        """Backward-compatible simple report."""
        all_valves = self.repo.get_all(project_id)
        total = len(all_valves)
        tested = sum(1 for v in all_valves if getattr(v, "hydro_shell_test", False))
        installed = sum(1 for v in all_valves if v.status == ValveStatus.INSTALLED.value)
        return {
            "total": total,
            "tested": tested,
            "untested": total - tested,
            "installed": installed,
            "pct_tested": round(tested / total * 100, 1) if total else 0,
        }

    def get_comprehensive_report(self, project_id: int) -> ValveReport:
        """
        Multi-dimensional valve status report for project management.
        """
        all_valves = self.repo.get_all(project_id)
        total = len(all_valves)

        if total == 0:
            return ValveReport(
                project_id=project_id, total=0,
                by_status={}, by_type={}, by_size={}, by_system={},
                test_coverage={}, installed_pct=0, overall_readiness_pct=0,
                critical_gaps=["No valves registered."],
            )

        # By Status
        by_status: Dict[str, int] = {}
        for v in all_valves:
            s = getattr(v, "status", "Unknown")
            by_status[s] = by_status.get(s, 0) + 1

        # By Type
        by_type: Dict[str, int] = {}
        for v in all_valves:
            t = getattr(v, "valve_type", "Unknown")
            by_type[t] = by_type.get(t, 0) + 1

        # By Size
        by_size: Dict[str, int] = {}
        for v in all_valves:
            sz = getattr(v, "size_nps", "N/A") or "N/A"
            by_size[sz] = by_size.get(sz, 0) + 1

        # By System
        by_system: Dict[str, int] = {}
        for v in all_valves:
            sys = getattr(v, "system", "N/A") or "N/A"
            by_system[sys] = by_system.get(sys, 0) + 1

        # Test Coverage
        shell_ok = sum(1 for v in all_valves if getattr(v, "hydro_shell_test", False))
        seat_ok = sum(1 for v in all_valves if getattr(v, "hydro_seat_test", False))
        backseat_ok = sum(1 for v in all_valves if getattr(v, "backseat_test", False))
        pneumatic_ok = sum(1 for v in all_valves if getattr(v, "pneumatic_test", False))
        functional_ok = sum(1 for v in all_valves if getattr(v, "functional_test", False))

        test_coverage = {
            "shell": {"done": shell_ok, "pct": round(shell_ok / total * 100, 1)},
            "seat": {"done": seat_ok, "pct": round(seat_ok / total * 100, 1)},
            "backseat": {"done": backseat_ok, "pct": round(backseat_ok / total * 100, 1)},
            "pneumatic": {"done": pneumatic_ok, "pct": round(pneumatic_ok / total * 100, 1)},
            "functional": {"done": functional_ok, "pct": round(functional_ok / total * 100, 1)},
        }

        installed = by_status.get(ValveStatus.INSTALLED.value, 0) + \
                    by_status.get(ValveStatus.PRESERVED.value, 0) + \
                    by_status.get(ValveStatus.COMMISSIONED.value, 0)
        installed_pct = round(installed / total * 100, 1)

        # Overall Readiness (weighted)
        readiness = (
            test_coverage["shell"]["pct"] * 0.30 +
            test_coverage["seat"]["pct"] * 0.25 +
            test_coverage["backseat"]["pct"] * 0.10 +
            test_coverage["functional"]["pct"] * 0.10 +
            installed_pct * 0.25
        )

        # Critical Gaps
        gaps: List[str] = []
        untested = total - shell_ok
        if untested > 0:
            gaps.append(f"{untested} valve(s) without shell test.")
        if by_status.get(ValveStatus.DEFECTIVE.value, 0) > 0:
            gaps.append(
                f"{by_status[ValveStatus.DEFECTIVE.value]} defective valve(s) "
                f"require disposition."
            )
        overdue = self._count_overdue_preservation(all_valves)
        if overdue > 0:
            gaps.append(f"{overdue} valve(s) with overdue preservation.")

        return ValveReport(
            project_id=project_id,
            total=total,
            by_status=by_status,
            by_type=by_type,
            by_size=by_size,
            by_system=by_system,
            test_coverage=test_coverage,
            installed_pct=installed_pct,
            overall_readiness_pct=round(readiness, 1),
            critical_gaps=gaps,
        )

    def get_valve_summaries(
        self, project_id: int,
    ) -> List[ValveSummary]:
        """Lightweight summaries for dashboard cards."""
        all_valves = self.repo.get_all(project_id)
        return [
            ValveSummary(
                valve_id=v.id,
                valve_tag=v.valve_tag,
                valve_type=getattr(v, "valve_type", ""),
                size_nps=getattr(v, "size_nps", ""),
                pressure_class=getattr(v, "pressure_class", ""),
                line_number=getattr(v, "line_number", ""),
                status=v.status,
                shell_tested=bool(getattr(v, "hydro_shell_test", False)),
                seat_tested=bool(getattr(v, "hydro_seat_test", False)),
                installed=v.status in (
                    ValveStatus.INSTALLED.value,
                    ValveStatus.PRESERVED.value,
                    ValveStatus.COMMISSIONED.value,
                ),
            )
            for v in all_valves
        ]

    # ═══════════════════════════════════════════
    #  6. READINESS & INTELLIGENCE
    # ═══════════════════════════════════════════

    def check_installation_readiness(
        self, valve_id: int,
    ) -> Dict[str, Any]:
        """
        Check if a valve is ready for installation.

        Returns readiness score and list of blockers.
        """
        valve = self._get_valve_or_raise(valve_id)
        blockers: List[str] = []
        checks: Dict[str, bool] = {}

        checks["shell_tested"] = bool(getattr(valve, "hydro_shell_test", False))
        if not checks["shell_tested"]:
            blockers.append("Shell test not recorded.")

        checks["seat_tested"] = bool(getattr(valve, "hydro_seat_test", False))
        if not checks["seat_tested"]:
            blockers.append("Seat test not recorded.")

        # Check valve type needs backseat
        vtype = getattr(valve, "valve_type", "")
        if vtype in (ValveType.GATE.value, ValveType.GLOBE.value):
            checks["backseat_tested"] = bool(getattr(valve, "backseat_test", False))
            if not checks["backseat_tested"]:
                blockers.append("Backseat test required for Gate/Globe valves.")

        checks["not_defective"] = valve.status != ValveStatus.DEFECTIVE.value
        if not checks["not_defective"]:
            blockers.append("Valve is marked DEFECTIVE.")

        checks["has_mtr"] = bool(getattr(valve, "mtr_no", ""))
        if not checks["has_mtr"]:
            blockers.append("MTR (Material Test Report) not linked.")

        score = sum(checks.values()) / len(checks) * 100 if checks else 0

        return {
            "valve_tag": valve.valve_tag,
            "is_ready": len(blockers) == 0,
            "readiness_pct": round(score, 1),
            "checks": checks,
            "blockers": blockers,
        }

    def get_preservation_alerts(
        self, project_id: int, days_threshold: int = 7,
    ) -> List[Dict[str, Any]]:
        """Return valves with overdue or soon-due preservation."""
        all_valves = self.repo.get_all(project_id)
        today = date.today()
        alerts = []
        for v in all_valves:
            due = getattr(v, "preservation_next_due", None)
            if due and isinstance(due, date):
                delta = (due - today).days
                if delta <= days_threshold:
                    alerts.append({
                        "valve_tag": v.valve_tag,
                        "valve_type": getattr(v, "valve_type", ""),
                        "status": v.status,
                        "preservation_due": due.isoformat(),
                        "days_remaining": delta,
                        "urgency": "OVERDUE" if delta < 0 else "DUE SOON",
                    })
        return sorted(alerts, key=lambda a: a["days_remaining"])

    # ═══════════════════════════════════════════
    #  7. INTERNAL HELPERS
    # ═══════════════════════════════════════════

    def _get_valve_or_raise(self, valve_id: int) -> Any:
        valve = self.repo.get_by_id(valve_id)
        if not valve:
            raise NotFoundError(f"Valve id={valve_id} not found.")
        return valve

    @staticmethod
    def _normalize_tag(tag: str) -> str:
        return tag.strip().upper()

    @staticmethod
    def _validate_tag(tag: str) -> None:
        if not tag:
            raise ValidationError("Valve tag cannot be empty.")
        if len(tag) > 50:
            raise ValidationError("Valve tag must be ≤ 50 characters.")

    @staticmethod
    def _validate_valve_type(vtype: str) -> None:
        valid = {e.value for e in ValveType}
        if vtype not in valid:
            raise ValidationError(
                f"Invalid valve type '{vtype}'. Must be one of: {sorted(valid)}"
            )

    @staticmethod
    def _validate_test_record(record: ValveTestRecord) -> None:
        if not record.test_type:
            raise ValidationError("Test type is required.")
        if record.test_pressure_bar < 0:
            raise ValidationError("Test pressure cannot be negative.")
        if record.holding_time_sec < 0:
            raise ValidationError("Holding time cannot be negative.")
        valid_results = {e.value for e in TestResult}
        if record.result not in valid_results:
            raise ValidationError(
                f"Invalid result '{record.result}'. Must be: {valid_results}"
            )

    @staticmethod
    def _map_test_to_fields(record: ValveTestRecord) -> Dict[str, Any]:
        """Map a generic ValveTestRecord to DB column names."""
        tt = record.test_type
        base = {
            f"last_test_type": tt,
            f"last_test_pressure_bar": record.test_pressure_bar,
            f"last_test_result": record.result,
            f"last_test_certificate": record.certificate_no,
        }

        if tt == TestType.SHELL.value:
            base.update(
                hydro_shell_test=True,
                hydro_shell_pressure_bar=record.test_pressure_bar,
                hydro_shell_date=record.test_date or date.today(),
                test_witness=record.witness,
            )
        elif tt == TestType.HIGH_PRESSURE_SEAT.value:
            base.update(
                hydro_seat_test=True,
                hydro_seat_pressure_bar=record.test_pressure_bar,
                hydro_seat_date=record.test_date or date.today(),
            )
        elif tt == TestType.BACKSEAT.value:
            base.update(
                backseat_test=True,
                backseat_pressure_bar=record.test_pressure_bar,
                backseat_date=record.test_date or date.today(),
            )
        elif tt in (TestType.PNEUMATIC_SHELL.value, TestType.PNEUMATIC_SEAT.value):
            base.update(
                pneumatic_test=True,
                pneumatic_pressure_bar=record.test_pressure_bar,
                pneumatic_date=record.test_date or date.today(),
            )
        elif tt in (TestType.FUNCTIONAL_TORQUE.value, TestType.FUNCTIONAL_CYCLE.value):
            base.update(
                functional_test=True,
                functional_date=record.test_date or date.today(),
            )
        elif tt == TestType.ESD_TEST.value:
            base.update(
                esd_test=True,
                esd_date=record.test_date or date.today(),
            )

        return base

    @staticmethod
    def _default_hold_time(test_type: TestType) -> int:
        """Default holding times per API 598 (seconds)."""
        defaults = {
            TestType.SHELL: 60,
            TestType.HIGH_PRESSURE_SEAT: 60,
            TestType.LOW_PRESSURE_CLOSURE: 60,
            TestType.BACKSEAT: 60,
            TestType.PNEUMATIC_SHELL: 120,
            TestType.PNEUMATIC_SEAT: 60,
            TestType.FUNCTIONAL_TORQUE: 0,
            TestType.FUNCTIONAL_CYCLE: 0,
        }
        return defaults.get(test_type, 60)

    def _auto_advance_status_on_test(
        self, valve, record: ValveTestRecord,
    ) -> Optional[ValveStatus]:
        """Auto-advance status when key tests are passed."""
        if record.result != TestResult.PASS.value:
            return None

        current = ValveStatus(valve.status)
        if record.test_type == TestType.SHELL.value:
            if current in (ValveStatus.RECEIVED, ValveStatus.SITE_RECEIVED):
                return ValveStatus.SHOP_TESTED
        return None

    def _assert_shell_tested(self, valve) -> None:
        if not getattr(valve, "hydro_shell_test", False):
            raise ValidationError(
                f"Valve {valve.valve_tag}: Shell test required before "
                f"advancing to Shop Tested."
            )

    def _assert_tested(self, valve) -> None:
        if not getattr(valve, "hydro_shell_test", False):
            raise ValidationError(
                f"Valve {valve.valve_tag}: Must be tested before installation."
            )

    def _assert_installed(self, valve) -> None:
        if valve.status not in (
            ValveStatus.INSTALLED.value, ValveStatus.PRESERVED.value,
        ):
            raise ValidationError(
                f"Valve {valve.valve_tag}: Must be installed before commissioning."
            )

    @staticmethod
    def _count_overdue_preservation(valves) -> int:
        today = date.today()
        count = 0
        for v in valves:
            due = getattr(v, "preservation_next_due", None)
            if due and isinstance(due, date) and due < today:
                count += 1
        return count

    def _audit(self, valve, action: str, detail: str) -> None:
        """Write audit trail entry (delegated to repo if available)."""
        try:
            if hasattr(self.repo, "add_audit_entry"):
                self.repo.add_audit_entry(
                    entity_type="Valve",
                    entity_id=valve.id,
                    entity_tag=valve.valve_tag,
                    action=action,
                    detail=detail,
                    timestamp=datetime.utcnow(),
                )
        except Exception as e:
            logger.warning("Audit write failed: %s", e)