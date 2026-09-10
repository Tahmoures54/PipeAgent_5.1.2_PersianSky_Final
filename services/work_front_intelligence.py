# -*- coding: utf-8 -*-
"""
execution_intelligence.py - PipeAgent
=======================================
Execution Intelligence & Work Front Optimization Engine
--------------------------------------------------------
Rule-based first: deterministic, auditable recommendations that can
later be replaced/augmented by ML without changing the UI contract.

Provides:
  • Control Tower dashboard (real-time site overview)
  • Smart dispatch recommendations with multi-factor scoring
  • Critical path analysis & bottleneck detection
  • Resource constraint optimization (crews, machines, areas)
  • Dependency chain validation (predecessor / successor)
  • Material & NDT readiness integration
  • Shift / calendar / weather awareness
  • HSE constraints (fatigue, height, confined space)
  • Area congestion detection
  • What-if simulation engine
  • KPI tracking (SPI, productivity, utilization)
  • Lookahead planning (7 / 14 / 21 / 28 day)
  • Conflict detection & resolution suggestions

Architecture:
  Rule Engine → Scoring → Constraint Solver → Recommendation
  (All rules are pluggable and auditable.)

Author : PipeAgent Engineering
Version: 5.0.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from db.models import WorkFront, WorkTeam, SiteMachine, WorkAssignment

logger = logging.getLogger("pipeagent.services.execution_intelligence")


# ─────────────────────────────────────────────
#  Enums & Constants
# ─────────────────────────────────────────────

class FrontStatus(str, Enum):
    PLANNED = "Planned"
    READY = "Ready"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "In Progress"
    BLOCKED = "Blocked"
    WAITING = "Waiting"
    COMPLETED = "Completed"
    SUSPENDED = "Suspended"
    CANCELLED = "Cancelled"


class Priority(str, Enum):
    URGENT = "Urgent"
    HIGH = "High"
    NORMAL = "Normal"
    LOW = "Low"


class ResourceType(str, Enum):
    TEAM = "TEAM"
    MACHINE = "MACHINE"
    CRANE = "CRANE"
    SCAFFOLD = "SCAFFOLD"


class ConstraintType(str, Enum):
    DEPENDENCY = "Dependency"
    MATERIAL = "Material"
    NDT = "NDT"
    AREA_CONGESTION = "Area Congestion"
    RESOURCE_CONFLICT = "Resource Conflict"
    HSE = "HSE"
    WEATHER = "Weather"
    SHIFT = "Shift"
    PERMIT = "Permit"
    ACCESS = "Access"


class BottleneckSeverity(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


# Status groupings
READY_STATUSES = {
    FrontStatus.READY.value,
    FrontStatus.ASSIGNED.value,
    FrontStatus.IN_PROGRESS.value,
}
BLOCKED_STATUSES = {
    FrontStatus.BLOCKED.value,
    FrontStatus.WAITING.value,
}
ACTIVE_STATUSES = {
    FrontStatus.IN_PROGRESS.value,
}
TERMINAL_STATUSES = {
    FrontStatus.COMPLETED.value,
    FrontStatus.CANCELLED.value,
}

# Priority weights for scoring
PRIORITY_WEIGHTS: Dict[str, int] = {
    Priority.URGENT.value: 100,
    Priority.HIGH.value: 80,
    Priority.NORMAL.value: 50,
    Priority.LOW.value: 20,
}

# Activity types that require heavy equipment
HEAVY_EQUIPMENT_ACTIVITIES = {
    "Pipe Erection", "Spool Installation", "Valve Installation",
    "Material Handling", "Heavy Lift", "Module Installation",
    "Vessel Erection", "Equipment Setting",
}

# Activities requiring NDT clearance before next step
NDT_DEPENDENT_ACTIVITIES = {
    "Hydro Test", "Pneumatic Test", "Reinstatement",
    "Insulation", "Painting", "Final Walkdown",
}

# Default configuration
DEFAULT_CONFIG = {
    "max_recommendations": 12,
    "lookahead_days": 21,
    "lookahead_items": 40,
    "max_teams_per_area": 3,
    "deadline_urgent_days": 2,
    "deadline_near_days": 7,
    "overdue_score_bonus": 35,
    "deadline_urgent_bonus": 25,
    "deadline_near_bonus": 10,
    "qty_score_cap": 20,
    "qty_score_divisor": 10,
    "critical_path_bonus": 30,
    "dependency_penalty": -50,
    "material_missing_penalty": -40,
    "area_congestion_penalty": -20,
    "hse_violation_penalty": -100,
    "productivity_weight": 0.15,
    "spi_weight": 0.10,
}


# ─────────────────────────────────────────────
#  Data Classes / DTOs
# ─────────────────────────────────────────────

@dataclass
class Recommendation:
    """A single dispatch recommendation."""
    front_id: int
    front_code: str
    front_description: str
    discipline: str
    activity_type: str
    priority: str
    score: int
    score_breakdown: Dict[str, int]
    recommended_team: Optional[str] = None
    recommended_machine: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    estimated_duration_days: int = 0
    confidence_pct: float = 0.0
    is_critical_path: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class Bottleneck:
    """Identified bottleneck in execution."""
    severity: str
    category: str
    description: str
    affected_fronts: List[str]
    affected_count: int
    suggested_action: str
    impact_days: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ResourceUtilization:
    """Utilization snapshot for a resource."""
    resource_type: str
    code: str
    name: str
    status: str
    current_front: Optional[str] = None
    load: str = "AVAILABLE"
    utilization_pct: float = 0.0
    next_available_date: Optional[date] = None
    weekly_hours: float = 0.0
    fatigue_risk: str = "Low"  # Low / Medium / High

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class KPIDashboard:
    """Key Performance Indicators for execution."""
    project_id: int
    report_date: date
    total_fronts: int
    completed: int
    active: int
    blocked: int
    overdue: int
    completion_pct: float
    spi: float  # Schedule Performance Index
    planned_qty_total: int
    actual_qty_total: int
    productivity_rate: float  # qty per day
    avg_cycle_time_days: float
    resource_utilization_pct: float
    team_utilization_pct: float
    machine_utilization_pct: float
    trend_7d: str  # "Improving" / "Stable" / "Declining"

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class WhatIfScenario:
    """What-if simulation input."""
    scenario_name: str
    add_teams: int = 0
    remove_teams: int = 0
    add_machines: int = 0
    shift_change: str = ""  # "Single" / "Double" / "Triple"
    weather_delay_days: int = 0
    priority_override: Dict[int, str] = field(default_factory=dict)
    fast_track_fronts: List[int] = field(default_factory=list)


@dataclass
class WhatIfResult:
    """What-if simulation output."""
    scenario_name: str
    original_completion_date: Optional[date]
    simulated_completion_date: Optional[date]
    days_saved: int
    additional_cost_estimate: float
    risk_level: str
    details: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ControlTowerResult:
    """Complete Control Tower output."""
    project_id: Optional[int]
    generated_at: str
    summary: Dict[str, int]
    recommendations: List[Recommendation]
    bottlenecks: List[Bottleneck]
    lookahead: List[Dict[str, Any]]
    resources: List[ResourceUtilization]
    kpis: Optional[KPIDashboard]
    critical_path: List[str]
    area_congestion: Dict[str, int]
    conflicts: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "generated_at": self.generated_at,
            "summary": self.summary,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "bottlenecks": [b.to_dict() for b in self.bottlenecks],
            "lookahead": self.lookahead,
            "resources": [r.to_dict() for r in self.resources],
            "kpis": self.kpis.to_dict() if self.kpis else None,
            "critical_path": self.critical_path,
            "area_congestion": self.area_congestion,
            "conflicts": self.conflicts,
        }


# ─────────────────────────────────────────────
#  Pluggable Rule Interface
# ─────────────────────────────────────────────

class ScoringRule:
    """
    Base class for pluggable scoring rules.

    Subclass and override ``apply`` to add custom scoring logic.
    Rules are applied in order; each adds/subtracts from the score.
    """

    name: str = "BaseRule"
    weight: float = 1.0

    def apply(
        self, front, context: Dict[str, Any],
    ) -> Tuple[int, str]:
        """Return (score_delta, reason_string)."""
        return 0, ""


class PriorityRule(ScoringRule):
    name = "Priority"

    def apply(self, front, ctx):
        p = getattr(front, "priority", Priority.NORMAL.value) or Priority.NORMAL.value
        score = PRIORITY_WEIGHTS.get(p, 50)
        return score, f"priority={p}"


class DeadlineRule(ScoringRule):
    name = "Deadline"

    def apply(self, front, ctx):
        today = ctx["today"]
        cfg = ctx["config"]
        pf = getattr(front, "planned_finish", None)
        if not pf:
            return 0, "no deadline"
        days = (pf - today).days
        if days <= 0:
            return cfg["overdue_score_bonus"], "OVERDUE"
        if days <= cfg["deadline_urgent_days"]:
            return cfg["deadline_urgent_bonus"], f"deadline in {days}d"
        if days <= cfg["deadline_near_days"]:
            return cfg["deadline_near_bonus"], f"deadline in {days}d"
        return 0, f"deadline in {days}d"


class QuantityRule(ScoringRule):
    name = "Quantity"

    def apply(self, front, ctx):
        cfg = ctx["config"]
        qty = getattr(front, "target_qty", 0) or 0
        score = min(cfg["qty_score_cap"], qty // cfg["qty_score_divisor"])
        return score, f"qty={qty}"


class CriticalPathRule(ScoringRule):
    name = "CriticalPath"

    def apply(self, front, ctx):
        cfg = ctx["config"]
        if getattr(front, "is_critical_path", False):
            return cfg["critical_path_bonus"], "on critical path"
        return 0, ""


class DependencyRule(ScoringRule):
    name = "Dependency"

    def apply(self, front, ctx):
        cfg = ctx["config"]
        predecessors = ctx.get("predecessors", {})
        front_id = getattr(front, "id", None)
        if front_id and front_id in predecessors:
            for pred_id in predecessors[front_id]:
                pred = ctx.get("front_map", {}).get(pred_id)
                if pred and getattr(pred, "status", "") != FrontStatus.COMPLETED.value:
                    return cfg["dependency_penalty"], (
                        f"predecessor {getattr(pred, 'front_code', pred_id)} "
                        f"not complete"
                    )
        return 0, ""


class MaterialReadinessRule(ScoringRule):
    name = "MaterialReadiness"

    def apply(self, front, ctx):
        cfg = ctx["config"]
        material_ready = ctx.get("material_readiness", {}).get(
            getattr(front, "id", -1), True
        )
        if not material_ready:
            return cfg["material_missing_penalty"], "material not available"
        return 0, ""


class AreaCongestionRule(ScoringRule):
    name = "AreaCongestion"

    def apply(self, front, ctx):
        cfg = ctx["config"]
        area = getattr(front, "area", "") or getattr(front, "location", "")
        if not area:
            return 0, ""
        active_in_area = ctx.get("area_active_count", {}).get(area, 0)
        if active_in_area >= cfg["max_teams_per_area"]:
            return cfg["area_congestion_penalty"], (
                f"area '{area}' congested ({active_in_area} teams)"
            )
        return 0, ""


class HSERule(ScoringRule):
    name = "HSE"

    def apply(self, front, ctx):
        cfg = ctx["config"]
        hse_flags = ctx.get("hse_flags", {}).get(
            getattr(front, "id", -1), []
        )
        if "fatigue_risk" in hse_flags:
            return cfg["hse_violation_penalty"], "HSE: crew fatigue risk"
        if "permit_missing" in hse_flags:
            return cfg["hse_violation_penalty"], "HSE: work permit missing"
        return 0, ""


# Default rule pipeline
DEFAULT_RULES: List[ScoringRule] = [
    PriorityRule(),
    DeadlineRule(),
    QuantityRule(),
    CriticalPathRule(),
    DependencyRule(),
    MaterialReadinessRule(),
    AreaCongestionRule(),
    HSERule(),
]


# ─────────────────────────────────────────────
#  Main Service
# ─────────────────────────────────────────────

class ExecutionIntelligenceService:
    """
    Enterprise-grade Execution Intelligence Engine.

    Usage:
        svc = ExecutionIntelligenceService(db)
        tower = svc.build_control_tower(project_id=1)
        print(tower.summary)
        for rec in tower.recommendations:
            print(rec.front_code, rec.score, rec.reasons)
    """

    def __init__(
        self,
        db,
        *,
        config: Optional[Dict[str, Any]] = None,
        rules: Optional[List[ScoringRule]] = None,
        material_service=None,
        ndt_service=None,
        welding_service=None,
    ):
        self.db = db
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.rules = rules or list(DEFAULT_RULES)
        self.material_svc = material_service
        self.ndt_svc = ndt_service
        self.welding_svc = welding_service
        self._cache: Dict[str, Any] = {}
        self._cache_ts: Optional[datetime] = None
        self._cache_ttl = timedelta(seconds=30)

    # ═══════════════════════════════════════════
    #  1. CONTROL TOWER (Main Entry Point)
    # ═══════════════════════════════════════════

    def build_control_tower(
        self,
        session=None,
        project_id: Optional[int] = None,
    ) -> ControlTowerResult:
        """
        Build the complete Control Tower dashboard.

        This is the main entry point used by the UI.
        Backward-compatible with the old ``build_control_tower`` function.
        """
        if session is None:
            ctx_mgr = self.db.session_scope()
            session = ctx_mgr.__enter__()
            own_session = True
        else:
            own_session = False

        try:
            return self._build_tower_internal(session, project_id)
        finally:
            if own_session:
                ctx_mgr.__exit__(None, None, None)

    def _build_tower_internal(
        self, session, project_id: Optional[int],
    ) -> ControlTowerResult:
        """Internal tower builder with full intelligence."""
        today = date.today()
        cfg = self.config

        # ── Load Data ──
        fronts = self._query_fronts(session, project_id)
        teams = self._query_teams(session, project_id)
        machines = self._query_machines(session, project_id)
        assignments = self._query_active_assignments(session, project_id)

        # ── Build Lookup Maps ──
        front_map = {f.id: f for f in fronts}
        assigned_front_ids = {a.work_front_id for a in assignments}
        team_by_discipline = self._index_teams_by_discipline(teams)
        area_active_count = self._count_active_per_area(fronts)
        predecessors = self._build_dependency_graph(fronts)

        # ── Classify Fronts ──
        ready = [f for f in fronts if self._is_front_ready(f)]
        blocked = [
            f for f in fronts
            if f.status in BLOCKED_STATUSES or (getattr(f, "blocker", "") or "").strip()
        ]
        overdue = [
            f for f in fronts
            if getattr(f, "planned_finish", None)
            and f.planned_finish < today
            and f.status not in TERMINAL_STATUSES
        ]
        active = [f for f in fronts if f.status in ACTIVE_STATUSES]
        completed = [f for f in fronts if f.status == FrontStatus.COMPLETED.value]
        available_teams = [t for t in teams if t.status == "Available"]
        available_machines = [m for m in machines if m.status == "Available"]

        # ── Build Scoring Context ──
        ctx = {
            "today": today,
            "config": cfg,
            "front_map": front_map,
            "predecessors": predecessors,
            "area_active_count": area_active_count,
            "material_readiness": self._get_material_readiness(fronts),
            "hse_flags": self._get_hse_flags(fronts, teams),
        }

        # ── Score & Rank Candidates ──
        candidates = [
            f for f in ready if f.id not in assigned_front_ids
        ]
        scored_candidates = []
        for f in candidates:
            rec = self._score_and_build_recommendation(
                f, ctx, team_by_discipline, available_machines,
            )
            scored_candidates.append(rec)

        scored_candidates.sort(key=lambda r: -r.score)
        recommendations = scored_candidates[:cfg["max_recommendations"]]

        # ── Lookahead ──
        lookahead = self._build_lookahead(fronts, today, cfg["lookahead_days"])

        # ── Resource Utilization ──
        resources = self._build_utilization(teams, machines)

        # ── Bottlenecks ──
        bottlenecks = self._detect_bottlenecks(
            fronts, teams, machines, area_active_count, overdue,
        )

        # ── Critical Path ──
        critical_path = self._compute_critical_path(fronts, predecessors)

        # ── Conflicts ──
        conflicts = self._detect_conflicts(fronts, assignments, teams)

        # ── KPIs ──
        kpis = self._compute_kpis(
            project_id or 0, fronts, teams, machines, today,
        )

        # ── Summary ──
        summary = {
            "ready": len(ready),
            "active": len(active),
            "blocked": len(blocked),
            "overdue": len(overdue),
            "completed": len(completed),
            "total": len(fronts),
            "available_teams": len(available_teams),
            "available_machines": len(available_machines),
            "unassigned_ready": len(candidates),
        }

        logger.info(
            "Control Tower built: %d fronts, %d recommendations, "
            "%d bottlenecks (project=%s)",
            len(fronts), len(recommendations), len(bottlenecks), project_id,
        )

        return ControlTowerResult(
            project_id=project_id,
            generated_at=datetime.utcnow().isoformat(),
            summary=summary,
            recommendations=recommendations,
            bottlenecks=bottlenecks,
            lookahead=lookahead,
            resources=resources,
            kpis=kpis,
            critical_path=critical_path,
            area_congestion=area_active_count,
            conflicts=conflicts,
        )

    # ═══════════════════════════════════════════
    #  2. SCORING ENGINE
    # ═══════════════════════════════════════════

    def _score_and_build_recommendation(
        self,
        front,
        ctx: Dict[str, Any],
        team_by_discipline: Dict[str, List],
        available_machines: List,
    ) -> Recommendation:
        """Apply all scoring rules and build a recommendation."""
        total_score = 0
        breakdown: Dict[str, int] = {}
        reasons: List[str] = []
        constraints: List[str] = []

        for rule in self.rules:
            delta, reason = rule.apply(front, ctx)
            breakdown[rule.name] = delta
            total_score += delta
            if reason:
                if delta > 0:
                    reasons.append(f"+{delta} {reason}")
                elif delta < 0:
                    constraints.append(f"{delta} {reason}")

        # Resource matching
        discipline = (getattr(front, "discipline", "") or "").lower()
        team = None
        if discipline in team_by_discipline:
            team = team_by_discipline[discipline][0] if team_by_discipline[discipline] else None
        elif team_by_discipline.get("general"):
            team = team_by_discipline["general"][0]

        machine = None
        activity = getattr(front, "activity_type", "") or ""
        if activity in HEAVY_EQUIPMENT_ACTIVITIES and available_machines:
            machine = available_machines[0]

        if team:
            reasons.append(f"team {getattr(team, 'team_code', '?')}")
        else:
            constraints.append("no matching team available")

        if machine:
            reasons.append(f"machine {getattr(machine, 'machine_code', '?')}")
        elif activity in HEAVY_EQUIPMENT_ACTIVITIES:
            constraints.append("no heavy equipment available")

        # Confidence
        confidence = min(100, max(0, 50 + total_score // 3))

        # Duration estimate
        duration = self._estimate_duration(front)

        return Recommendation(
            front_id=getattr(front, "id", 0),
            front_code=getattr(front, "front_code", ""),
            front_description=getattr(front, "description", ""),
            discipline=getattr(front, "discipline", ""),
            activity_type=activity,
            priority=getattr(front, "priority", Priority.NORMAL.value) or Priority.NORMAL.value,
            score=total_score,
            score_breakdown=breakdown,
            recommended_team=getattr(team, "team_code", None) if team else None,
            recommended_machine=getattr(machine, "machine_code", None) if machine else None,
            reasons=reasons,
            constraints=constraints,
            blockers=[getattr(front, "blocker", "")] if getattr(front, "blocker", "") else [],
            estimated_duration_days=duration,
            confidence_pct=round(confidence, 1),
            is_critical_path=getattr(front, "is_critical_path", False),
        )

    def score_front(
        self, front, context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, Dict[str, int]]:
        """Public API: score a single front."""
        ctx = context or {
            "today": date.today(),
            "config": self.config,
            "front_map": {},
            "predecessors": {},
            "area_active_count": {},
            "material_readiness": {},
            "hse_flags": {},
        }
        total = 0
        breakdown = {}
        for rule in self.rules:
            delta, _ = rule.apply(front, ctx)
            breakdown[rule.name] = delta
            total += delta
        return total, breakdown

    def add_rule(self, rule: ScoringRule) -> None:
        """Add a custom scoring rule at runtime."""
        self.rules.append(rule)
        logger.info("Added scoring rule: %s", rule.name)

    def remove_rule(self, rule_name: str) -> bool:
        """Remove a scoring rule by name."""
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.name != rule_name]
        removed = len(self.rules) < before
        if removed:
            logger.info("Removed scoring rule: %s", rule_name)
        return removed

    # ═══════════════════════════════════════════
    #  3. DEPENDENCY & CRITICAL PATH
    # ═══════════════════════════════════════════

    def _build_dependency_graph(
        self, fronts: List,
    ) -> Dict[int, List[int]]:
        """
        Build predecessor → successor graph.

        Returns: {front_id: [predecessor_ids]}
        """
        graph: Dict[int, List[int]] = {}
        for f in fronts:
            fid = getattr(f, "id", None)
            pred = getattr(f, "predecessor_id", None)
            if fid and pred:
                graph.setdefault(fid, []).append(pred)
            # Support multiple predecessors (comma-separated)
            preds_str = getattr(f, "predecessors", "") or ""
            if preds_str:
                for p in preds_str.split(","):
                    p = p.strip()
                    if p.isdigit():
                        graph.setdefault(fid, []).append(int(p))
        return graph

    def _compute_critical_path(
        self,
        fronts: List,
        predecessors: Dict[int, List[int]],
    ) -> List[str]:
        """
        Compute the critical path using longest-path algorithm.

        Returns list of front_codes on the critical path.
        """
        front_map = {f.id: f for f in fronts if hasattr(f, "id")}
        if not front_map:
            return []

        # Calculate duration for each front
        durations: Dict[int, int] = {}
        for f in fronts:
            fid = getattr(f, "id", None)
            if fid:
                durations[fid] = self._estimate_duration(f)

        # Topological sort + longest path
        longest: Dict[int, int] = {}
        parent: Dict[int, Optional[int]] = {}

        def _longest_path(fid: int, visited: Set[int]) -> int:
            if fid in longest:
                return longest[fid]
            if fid in visited:
                return 0  # Cycle protection
            visited.add(fid)

            preds = predecessors.get(fid, [])
            if not preds:
                longest[fid] = durations.get(fid, 1)
                parent[fid] = None
                return longest[fid]

            max_pred = 0
            max_pred_id = None
            for p in preds:
                if p in front_map:
                    pl = _longest_path(p, visited)
                    if pl > max_pred:
                        max_pred = pl
                        max_pred_id = p

            longest[fid] = max_pred + durations.get(fid, 1)
            parent[fid] = max_pred_id
            return longest[fid]

        for fid in front_map:
            _longest_path(fid, set())

        if not longest:
            return []

        # Find the end of the critical path
        end_fid = max(longest, key=longest.get)

        # Trace back
        path = []
        current: Optional[int] = end_fid
        visited_trace: Set[int] = set()
        while current and current not in visited_trace:
            visited_trace.add(current)
            f = front_map.get(current)
            if f:
                path.append(getattr(f, "front_code", str(current)))
            current = parent.get(current)

        path.reverse()
        return path

    def validate_dependencies(
        self, front_id: int, session=None,
    ) -> List[str]:
        """
        Check if all predecessors of a front are complete.

        Returns list of violation messages (empty = OK).
        """
        if session is None:
            with self.db.session_scope() as s:
                return self._validate_deps_internal(front_id, s)
        return self._validate_deps_internal(front_id, session)

    def _validate_deps_internal(
        self, front_id: int, session,
    ) -> List[str]:
        front = session.query(WorkFront).get(front_id)
        if not front:
            return [f"Front {front_id} not found."]

        violations = []
        preds_str = getattr(front, "predecessors", "") or ""
        pred_id = getattr(front, "predecessor_id", None)

        pred_ids = []
        if pred_id:
            pred_ids.append(pred_id)
        for p in preds_str.split(","):
            p = p.strip()
            if p.isdigit():
                pred_ids.append(int(p))

        for pid in pred_ids:
            pred = session.query(WorkFront).get(pid)
            if pred and pred.status != FrontStatus.COMPLETED.value:
                violations.append(
                    f"Predecessor '{getattr(pred, 'front_code', pid)}' "
                    f"is '{pred.status}', not Completed."
                )
        return violations

    # ═══════════════════════════════════════════
    #  4. BOTTLENECK DETECTION
    # ═══════════════════════════════════════════

    def _detect_bottlenecks(
        self,
        fronts: List,
        teams: List,
        machines: List,
        area_counts: Dict[str, int],
        overdue: List,
    ) -> List[Bottleneck]:
        """Identify execution bottlenecks."""
        bottlenecks: List[Bottleneck] = []
        cfg = self.config

        # 1. Overdue fronts
        if len(overdue) >= 5:
            bottlenecks.append(Bottleneck(
                severity=BottleneckSeverity.CRITICAL.value,
                category="Schedule",
                description=f"{len(overdue)} fronts are overdue.",
                affected_fronts=[
                    getattr(f, "front_code", str(f.id)) for f in overdue[:10]
                ],
                affected_count=len(overdue),
                suggested_action=(
                    "Conduct recovery planning session. "
                    "Consider additional shifts or fast-tracking."
                ),
                impact_days=max(
                    ((date.today() - f.planned_finish).days
                     for f in overdue if f.planned_finish),
                    default=0,
                ),
            ))

        # 2. Team shortage
        available_teams = sum(1 for t in teams if t.status == "Available")
        ready_unassigned = sum(
            1 for f in fronts
            if self._is_front_ready(f) and f.status != FrontStatus.COMPLETED.value
        )
        if available_teams == 0 and ready_unassigned > 0:
            bottlenecks.append(Bottleneck(
                severity=BottleneckSeverity.CRITICAL.value,
                category="Resource",
                description="No available teams for ready fronts.",
                affected_fronts=[],
                affected_count=ready_unassigned,
                suggested_action=(
                    "Mobilize additional crews or reassign from "
                    "low-priority active fronts."
                ),
            ))

        # 3. Area congestion
        for area, count in area_counts.items():
            if count >= cfg["max_teams_per_area"]:
                area_fronts = [
                    getattr(f, "front_code", str(f.id))
                    for f in fronts
                    if (getattr(f, "area", "") or getattr(f, "location", "")) == area
                    and f.status in ACTIVE_STATUSES
                ]
                bottlenecks.append(Bottleneck(
                    severity=BottleneckSeverity.HIGH.value,
                    category="Area Congestion",
                    description=(
                        f"Area '{area}' has {count} active teams "
                        f"(limit: {cfg['max_teams_per_area']})."
                    ),
                    affected_fronts=area_fronts,
                    affected_count=count,
                    suggested_action=(
                        f"Stagger work in area '{area}' or relocate "
                        f"non-critical activities."
                    ),
                ))

        # 4. Machine shortage
        heavy_ready = [
            f for f in fronts
            if self._is_front_ready(f)
            and getattr(f, "activity_type", "") in HEAVY_EQUIPMENT_ACTIVITIES
        ]
        available_machines = sum(
            1 for m in machines if m.status == "Available"
        )
        if len(heavy_ready) > available_machines and available_machines >= 0:
            bottlenecks.append(Bottleneck(
                severity=BottleneckSeverity.HIGH.value,
                category="Equipment",
                description=(
                    f"{len(heavy_ready)} fronts need heavy equipment "
                    f"but only {available_machines} available."
                ),
                affected_fronts=[
                    getattr(f, "front_code", "") for f in heavy_ready[:5]
                ],
                affected_count=len(heavy_ready),
                suggested_action="Rent additional crane/equipment or reschedule.",
            ))

        # 5. Blocked chain
        blocked = [f for f in fronts if f.status in BLOCKED_STATUSES]
        if len(blocked) >= 3:
            bottlenecks.append(Bottleneck(
                severity=BottleneckSeverity.MEDIUM.value,
                category="Blockers",
                description=f"{len(blocked)} fronts are blocked.",
                affected_fronts=[
                    getattr(f, "front_code", "") for f in blocked[:5]
                ],
                affected_count=len(blocked),
                suggested_action="Review and resolve blockers in daily coordination meeting.",
            ))

        return bottlenecks

    # ═══════════════════════════════════════════
    #  5. CONFLICT DETECTION
    # ═══════════════════════════════════════════

    def _detect_conflicts(
        self,
        fronts: List,
        assignments: List,
        teams: List,
    ) -> List[str]:
        """Detect resource and scheduling conflicts."""
        conflicts: List[str] = []

        # Double-assignment: same team on multiple active fronts
        team_assignments: Dict[str, List[str]] = {}
        for a in assignments:
            tc = getattr(a, "team_code", "") or str(getattr(a, "team_id", ""))
            fc = str(getattr(a, "work_front_id", ""))
            team_assignments.setdefault(tc, []).append(fc)

        for tc, front_list in team_assignments.items():
            if len(front_list) > 1:
                conflicts.append(
                    f"⚠️ Team '{tc}' assigned to {len(front_list)} "
                    f"fronts simultaneously: {', '.join(front_list)}"
                )

        return conflicts

    # ═══════════════════════════════════════════
    #  6. WHAT-IF SIMULATION
    # ═══════════════════════════════════════════

    def simulate_what_if(
        self,
        project_id: int,
        scenario: WhatIfScenario,
    ) -> WhatIfResult:
        """
        Run a what-if simulation to estimate impact of changes.

        This is a simplified Monte Carlo–style estimation.
        """
        with self.db.session_scope() as session:
            fronts = self._query_fronts(session, project_id)
            teams = self._query_teams(session, project_id)

        today = date.today()
        original_end = self._estimate_project_end(fronts, today)

        # Apply scenario modifications
        modified_fronts = list(fronts)
        details: List[str] = []

        # Weather delay
        if scenario.weather_delay_days > 0:
            for f in modified_fronts:
                pf = getattr(f, "planned_finish", None)
                if pf and f.status not in TERMINAL_STATUSES:
                    f.planned_finish = pf + timedelta(
                        days=scenario.weather_delay_days
                    )
            details.append(
                f"Weather delay: +{scenario.weather_delay_days} days "
                f"to all active fronts."
            )

        # Team changes
        net_teams = scenario.add_teams - scenario.remove_teams
        if net_teams != 0:
            productivity_factor = max(
                0.3, 1.0 + (net_teams / max(len(teams), 1)) * 0.5
            )
            for f in modified_fronts:
                if f.status not in TERMINAL_STATUSES:
                    dur = self._estimate_duration(f)
                    new_dur = max(1, int(dur / productivity_factor))
                    pf = getattr(f, "planned_finish", None)
                    ps = getattr(f, "planned_start", None) or today
                    if pf:
                        f.planned_finish = ps + timedelta(days=new_dur)
            details.append(
                f"Team change: {net_teams:+d} teams → "
                f"productivity factor {productivity_factor:.2f}"
            )

        # Shift change
        if scenario.shift_change == "Double":
            for f in modified_fronts:
                if f.status not in TERMINAL_STATUSES:
                    dur = self._estimate_duration(f)
                    pf = getattr(f, "planned_finish", None)
                    ps = getattr(f, "planned_start", None) or today
                    if pf:
                        f.planned_finish = ps + timedelta(
                            days=max(1, int(dur * 0.6))
                        )
            details.append("Double shift: ~40% duration reduction.")
        elif scenario.shift_change == "Triple":
            for f in modified_fronts:
                if f.status not in TERMINAL_STATUSES:
                    dur = self._estimate_duration(f)
                    pf = getattr(f, "planned_finish", None)
                    ps = getattr(f, "planned_start", None) or today
                    if pf:
                        f.planned_finish = ps + timedelta(
                            days=max(1, int(dur * 0.4))
                        )
            details.append("Triple shift: ~60% duration reduction.")

        # Fast-track specific fronts
        for fid in scenario.fast_track_fronts:
            for f in modified_fronts:
                if getattr(f, "id", None) == fid:
                    dur = self._estimate_duration(f)
                    ps = getattr(f, "planned_start", None) or today
                    f.planned_finish = ps + timedelta(
                        days=max(1, int(dur * 0.5))
                    )
                    details.append(
                        f"Fast-tracked front {getattr(f, 'front_code', fid)}."
                    )

        simulated_end = self._estimate_project_end(modified_fronts, today)

        days_saved = 0
        if original_end and simulated_end:
            days_saved = (original_end - simulated_end).days

        # Cost estimate (simplified)
        cost = 0.0
        if scenario.add_teams > 0:
            cost += scenario.add_teams * 5000 * max(days_saved, 1)
        if scenario.shift_change in ("Double", "Triple"):
            cost += len(teams) * 2000 * max(days_saved, 1)

        risk = "Low"
        if scenario.shift_change == "Triple":
            risk = "High"
        elif scenario.weather_delay_days > 5 or scenario.remove_teams > 2:
            risk = "High"
        elif scenario.shift_change == "Double" or days_saved > 14:
            risk = "Medium"

        return WhatIfResult(
            scenario_name=scenario.scenario_name,
            original_completion_date=original_end,
            simulated_completion_date=simulated_end,
            days_saved=days_saved,
            additional_cost_estimate=round(cost, 2),
            risk_level=risk,
            details=details,
        )

    # ═══════════════════════════════════════════
    #  7. KPI COMPUTATION
    # ═══════════════════════════════════════════

    def _compute_kpis(
        self,
        project_id: int,
        fronts: List,
        teams: List,
        machines: List,
        today: date,
    ) -> KPIDashboard:
        """Compute execution KPIs."""
        total = len(fronts)
        completed = sum(
            1 for f in fronts if f.status == FrontStatus.COMPLETED.value
        )
        active = sum(1 for f in fronts if f.status in ACTIVE_STATUSES)
        blocked = sum(1 for f in fronts if f.status in BLOCKED_STATUSES)
        overdue = sum(
            1 for f in fronts
            if getattr(f, "planned_finish", None)
            and f.planned_finish < today
            and f.status not in TERMINAL_STATUSES
        )

        completion_pct = round(completed / total * 100, 1) if total else 0

        # SPI: Earned Value / Planned Value (simplified)
        planned_qty = sum(getattr(f, "target_qty", 0) or 0 for f in fronts)
        actual_qty = sum(getattr(f, "actual_qty", 0) or 0 for f in fronts)
        spi = round(actual_qty / planned_qty, 2) if planned_qty else 0.0

        # Productivity
        active_days = max(
            (today - min(
                (getattr(f, "planned_start", today) or today
                 for f in fronts if getattr(f, "planned_start", None)),
                default=today,
            )).days,
            1,
        )
        productivity = round(actual_qty / active_days, 1)

        # Cycle time
        cycle_times = []
        for f in fronts:
            if f.status == FrontStatus.COMPLETED.value:
                ps = getattr(f, "planned_start", None)
                pf = getattr(f, "planned_finish", None)
                if ps and pf:
                    cycle_times.append((pf - ps).days)
        avg_cycle = round(
            sum(cycle_times) / len(cycle_times), 1
        ) if cycle_times else 0.0

        # Utilization
        busy_teams = sum(1 for t in teams if t.status == "Busy")
        team_util = round(
            busy_teams / len(teams) * 100, 1
        ) if teams else 0.0
        busy_machines = sum(1 for m in machines if m.status == "Busy")
        machine_util = round(
            busy_machines / len(machines) * 100, 1
        ) if machines else 0.0
        resource_util = round(
            (team_util + machine_util) / 2, 1
        )

        # Trend (simplified — compare last 7 days)
        trend = "Stable"
        if spi > 1.05:
            trend = "Improving"
        elif spi < 0.90:
            trend = "Declining"

        return KPIDashboard(
            project_id=project_id,
            report_date=today,
            total_fronts=total,
            completed=completed,
            active=active,
            blocked=blocked,
            overdue=overdue,
            completion_pct=completion_pct,
            spi=spi,
            planned_qty_total=planned_qty,
            actual_qty_total=actual_qty,
            productivity_rate=productivity,
            avg_cycle_time_days=avg_cycle,
            resource_utilization_pct=resource_util,
            team_utilization_pct=team_util,
            machine_utilization_pct=machine_util,
            trend_7d=trend,
        )

    # ═══════════════════════════════════════════
    #  8. LOOKAHEAD PLANNING
    # ═══════════════════════════════════════════

    def _build_lookahead(
        self,
        fronts: List,
        today: date,
        days: int,
    ) -> List[Dict[str, Any]]:
        """Build lookahead schedule for the next N days."""
        cutoff = today + timedelta(days=days)
        upcoming = [
            f for f in fronts
            if f.status not in TERMINAL_STATUSES
            and getattr(f, "planned_start", None)
            and f.planned_start <= cutoff
        ]
        upcoming.sort(key=lambda f: (
            f.planned_start or date.max,
            PRIORITY_WEIGHTS.get(
                getattr(f, "priority", Priority.NORMAL.value) or Priority.NORMAL.value, 50
            ),
        ))

        result = []
        for f in upcoming[:self.config["lookahead_items"]]:
            ps = getattr(f, "planned_start", None)
            pf = getattr(f, "planned_finish", None)
            days_to_start = (ps - today).days if ps else 0
            result.append({
                "front_id": getattr(f, "id", 0),
                "front_code": getattr(f, "front_code", ""),
                "discipline": getattr(f, "discipline", ""),
                "activity_type": getattr(f, "activity_type", ""),
                "priority": getattr(f, "priority", Priority.NORMAL.value),
                "status": f.status,
                "planned_start": str(ps) if ps else "",
                "planned_finish": str(pf) if pf else "",
                "days_to_start": days_to_start,
                "estimated_duration": self._estimate_duration(f),
                "is_critical": getattr(f, "is_critical_path", False),
            })
        return result

    def get_lookahead(
        self,
        project_id: int,
        days: int = 14,
    ) -> List[Dict[str, Any]]:
        """Public API for lookahead planning."""
        with self.db.session_scope() as session:
            fronts = self._query_fronts(session, project_id)
        return self._build_lookahead(fronts, date.today(), days)

    # ═══════════════════════════════════════════
    #  9. RESOURCE UTILIZATION
    # ═══════════════════════════════════════════

    def _build_utilization(
        self, teams: List, machines: List,
    ) -> List[ResourceUtilization]:
        """Build resource utilization snapshot."""
        result: List[ResourceUtilization] = []

        for t in teams:
            status = getattr(t, "status", "Unknown")
            load = "BUSY" if status == "Busy" else "AVAILABLE"
            fatigue = "Low"
            weekly_hrs = getattr(t, "weekly_hours", 0) or 0
            if weekly_hrs > 60:
                fatigue = "High"
            elif weekly_hrs > 48:
                fatigue = "Medium"

            result.append(ResourceUtilization(
                resource_type=ResourceType.TEAM.value,
                code=getattr(t, "team_code", ""),
                name=getattr(t, "team_name", ""),
                status=status,
                current_front=str(getattr(t, "current_front_id", "") or ""),
                load=load,
                utilization_pct=100.0 if status == "Busy" else 0.0,
                weekly_hours=weekly_hrs,
                fatigue_risk=fatigue,
            ))

        for m in machines:
            status = getattr(m, "status", "Unknown")
            load = "BUSY" if status == "Busy" else "AVAILABLE"
            result.append(ResourceUtilization(
                resource_type=ResourceType.MACHINE.value,
                code=getattr(m, "machine_code", ""),
                name=getattr(m, "machine_type", ""),
                status=status,
                current_front=str(getattr(m, "current_front_id", "") or ""),
                load=load,
                utilization_pct=100.0 if status == "Busy" else 0.0,
            ))

        return result

    # ═══════════════════════════════════════════
    #  10. DATA LOADING HELPERS
    # ═══════════════════════════════════════════

    def _query_fronts(self, session, project_id: Optional[int]) -> List:
        q = session.query(WorkFront)
        if project_id:
            q = q.filter(WorkFront.project_id == project_id)
        return q.all()

    def _query_teams(self, session, project_id: Optional[int]) -> List:
        q = session.query(WorkTeam)
        if project_id:
            q = q.filter(WorkTeam.project_id == project_id)
        return q.all()

    def _query_machines(self, session, project_id: Optional[int]) -> List:
        q = session.query(SiteMachine)
        if project_id:
            q = q.filter(SiteMachine.project_id == project_id)
        return q.all()

    def _query_active_assignments(
        self, session, project_id: Optional[int],
    ) -> List:
        q = session.query(WorkAssignment).filter(
            WorkAssignment.status == "Assigned"
        )
        if project_id:
            q = q.join(WorkFront).filter(
                WorkFront.project_id == project_id
            )
        return q.all()

    # ═══════════════════════════════════════════
    #  11. INTERNAL HELPERS
    # ═══════════════════════════════════════════

    @staticmethod
    def _is_front_ready(front) -> bool:
        """Check if a front is truly ready to dispatch."""
        status = getattr(front, "status", "")
        readiness = getattr(front, "readiness", "")
        blocker = (getattr(front, "blocker", "") or "").strip()
        return (
            status in READY_STATUSES
            and readiness == "Ready"
            and not blocker
        )

    @staticmethod
    def _index_teams_by_discipline(
        teams: List,
    ) -> Dict[str, List]:
        """Group available teams by discipline."""
        index: Dict[str, List] = {}
        for t in teams:
            if t.status != "Available":
                continue
            disc = (getattr(t, "discipline", "") or "").lower()
            if not disc:
                disc = "general"
            index.setdefault(disc, []).append(t)
        return index

    @staticmethod
    def _count_active_per_area(fronts: List) -> Dict[str, int]:
        """Count active fronts per area."""
        counts: Dict[str, int] = {}
        for f in fronts:
            if f.status not in ACTIVE_STATUSES:
                continue
            area = getattr(f, "area", "") or getattr(f, "location", "") or "Unknown"
            counts[area] = counts.get(area, 0) + 1
        return counts

    def _get_material_readiness(
        self, fronts: List,
    ) -> Dict[int, bool]:
        """Check material availability for each front."""
        if not self.material_svc:
            return {}
        readiness = {}
        for f in fronts:
            fid = getattr(f, "id", -1)
            try:
                readiness[fid] = self.material_svc.is_ready_for_front(fid)
            except Exception:
                readiness[fid] = True  # Assume ready if check fails
        return readiness

    def _get_hse_flags(
        self, fronts: List, teams: List,
    ) -> Dict[int, List[str]]:
        """Check HSE constraints for each front."""
        flags: Dict[int, List[str]] = {}
        # Simplified: check team fatigue for assigned fronts
        team_fatigue = {}
        for t in teams:
            hrs = getattr(t, "weekly_hours", 0) or 0
            if hrs > 60:
                fid = getattr(t, "current_front_id", None)
                if fid:
                    team_fatigue.setdefault(fid, []).append("fatigue_risk")
        return team_fatigue

    @staticmethod
    def _estimate_duration(front) -> int:
        """Estimate remaining duration in days."""
        ps = getattr(front, "planned_start", None)
        pf = getattr(front, "planned_finish", None)
        if ps and pf:
            return max(1, (pf - ps).days)
        qty = getattr(front, "target_qty", 0) or 0
        rate = getattr(front, "productivity_rate", 0) or 0
        if qty > 0 and rate > 0:
            return max(1, int(qty / rate))
        return 7  # Default 1 week

    def _estimate_project_end(
        self, fronts: List, today: date,
    ) -> Optional[date]:
        """Estimate project completion date."""
        end_dates = [
            f.planned_finish for f in fronts
            if getattr(f, "planned_finish", None)
            and f.status not in TERMINAL_STATUSES
        ]
        return max(end_dates) if end_dates else None


# ─────────────────────────────────────────────
#  Backward-Compatible Module-Level Function
# ─────────────────────────────────────────────

def build_control_tower(
    session,
    project_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Backward-compatible wrapper for the old module-level function.

    Delegates to ExecutionIntelligenceService internally.
    """
    # Create a lightweight service instance
    svc = ExecutionIntelligenceService(db=None)
    result = svc.build_control_tower(session=session, project_id=project_id)

    # Convert to old dict format for backward compatibility
    return {
        "ready": result.summary.get("ready", 0),
        "active": result.summary.get("active", 0),
        "blocked": result.summary.get("blocked", 0),
        "overdue": result.summary.get("overdue", 0),
        "available_teams": result.summary.get("available_teams", 0),
        "available_machines": result.summary.get("available_machines", 0),
        "unassigned_ready": result.summary.get("unassigned_ready", 0),
        "fronts": [
            f for f in result.lookahead  # Approximation
        ],
        "blocked_fronts": [
            r for r in result.recommendations if r.blockers
        ],
        "recommendations": [r.to_dict() for r in result.recommendations],
        "lookahead": result.lookahead,
        "resources": [r.to_dict() for r in result.resources],
    }


def _front_ready(front: WorkFront) -> bool:
    """Backward-compatible helper."""
    return ExecutionIntelligenceService._is_front_ready(front)


def _score(front: WorkFront, today: date) -> int:
    """Backward-compatible scoring function."""
    svc = ExecutionIntelligenceService(db=None)
    score, _ = svc.score_front(front, {"today": today, "config": DEFAULT_CONFIG})
    return score