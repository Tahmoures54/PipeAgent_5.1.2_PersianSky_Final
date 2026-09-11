# -*- coding: utf-8 -*-
"""Workspace module access for piping site roles.

Canonical role keys are stored on ``users.role``. Display names from the
user-admin dialog and the older session enums are normalised here so the
menu, sidebar and File/Users actions stay consistent.
"""

from __future__ import annotations

from typing import FrozenSet, Iterable, Mapping, Optional, Sequence, Tuple

# Keep in sync with ``MainWindow.NAV_STRUCTURE``.
MODULE_KEYS: Tuple[str, ...] = (
    "dashboard",
    "project",
    "line_list",
    "documents",
    "technical_query",
    "data_exchange",
    "procurement",
    "spooling",
    "joints",
    "welder_mgmt",
    "supports",
    "erection",
    "valves",
    "ndt",
    "qaqc",
    "test_package",
    "precomm",
    "finishing",
    "handover",
    "field_control",
    "work_front",
    "control_tower",
    "mobile_field",
    "site_execution",
    "reports",
    "ai_assistant",
    "smart_entry",
    "execution_intelligence",
    "execution_os",
    "value_plans",
    "asbuilt",
    "digital_turnover",
)

ALL_MODULES: FrozenSet[str] = frozenset(MODULE_KEYS)

# Piping site activity chain covered by the workspace (ISO / weld map /
# MTO / NDE / hydro finishing / TQ / DCC / turnover).
SITE_ACTIVITY_CHAIN: Tuple[Tuple[str, str], ...] = (
    ("project", "Company identity, project and area setup"),
    ("line_list", "Line list / piping class / fluid service"),
    ("documents", "Document control (DCC receive / issue)"),
    ("technical_query", "Technical query / RFI"),
    ("data_exchange", "Import / export of site registers"),
    ("procurement", "MTO, MIV and warehouse stock"),
    ("spooling", "Shop spool fabrication"),
    ("joints", "Weld joint control sheet / joint history"),
    ("welder_mgmt", "Welder qualification and continuity"),
    ("supports", "Pipe support fabrication and erection"),
    ("erection", "Field erection / installation"),
    ("valves", "In-line valves and hydro of valves"),
    ("ndt", "NDE / inspection"),
    ("qaqc", "Punch, NCR and ITP"),
    ("test_package", "Test package finishing sequence"),
    ("precomm", "Pre-commissioning"),
    ("finishing", "Painting, insulation, wrapping"),
    ("handover", "Mechanical completion / handover"),
    ("field_control", "Site actions, WJCS and reports"),
    ("work_front", "Work-front control"),
    ("site_execution", "Daily site execution"),
    ("asbuilt", "As-built and dossier"),
    ("digital_turnover", "Digital turnover package"),
)

# (canonical_key, menu label)
SITE_ROLES: Tuple[Tuple[str, str], ...] = (
    ("admin", "Administrator (full access)"),
    ("project_manager", "Project manager"),
    ("engineer", "Piping / project engineer"),
    ("planner", "Planning engineer"),
    ("inspector", "QA/QC manager / welding inspector"),
    ("supervisor", "Site execution supervisor"),
    ("welder", "Welder / fitter"),
    ("storekeeper", "Material controller / storekeeper"),
    ("document_controller", "Document controller (DCC)"),
    ("client_rep", "Client representative / TPI"),
    ("viewer", "Read-only viewer"),
)

ROLE_LABELS = {key: label for key, label in SITE_ROLES}

_ROLE_ALIASES = {
    "admin": "admin",
    "administrator": "admin",
    "super_admin": "admin",
    "super-admin": "admin",
    "project_manager": "project_manager",
    "project_mgr": "project_manager",
    "project manager": "project_manager",
    "engineer": "engineer",
    "planning_eng": "planner",
    "planner": "planner",
    "inspector": "inspector",
    "qc_manager": "inspector",
    "qc_inspector": "inspector",
    "qa/qc manager": "inspector",
    "welding inspector": "inspector",
    "welding inspector (level ii)": "inspector",
    "supervisor": "supervisor",
    "shop_supervisor": "supervisor",
    "site execution supervisor": "supervisor",
    "welder": "welder",
    "storekeeper": "storekeeper",
    "material controller": "storekeeper",
    "material controller / storekeeper": "storekeeper",
    "document_controller": "document_controller",
    "document controller": "document_controller",
    "document controller (dcc)": "document_controller",
    "client_rep": "client_rep",
    "client representative": "client_rep",
    "client representative / tpi": "client_rep",
    "viewer": "viewer",
    "guest": "viewer",
    "user": "engineer",
}


def canonical_role(role: Optional[str]) -> str:
    """Map stored / display / enum role strings to a canonical key."""
    raw = (role or "viewer").strip()
    if not raw:
        return "viewer"
    compact = raw.replace("-", "_")
    lookup_keys = (
        compact,
        compact.lower(),
        compact.upper(),
        compact.split(" (", 1)[0].strip().lower(),
        compact.replace("_", " ").lower(),
    )
    for key in lookup_keys:
        mapped = _ROLE_ALIASES.get(key)
        if mapped:
            return mapped
        mapped = _ROLE_ALIASES.get(key.lower())
        if mapped:
            return mapped
    lowered = compact.lower()
    if lowered in ROLE_LABELS:
        return lowered
    return "viewer"


def role_label(role: Optional[str]) -> str:
    key = canonical_role(role)
    return ROLE_LABELS.get(key, key.replace("_", " ").title())


_READ_REGISTERS = frozenset({
    "dashboard", "project", "line_list", "documents", "technical_query",
    "joints", "supports", "ndt", "qaqc", "test_package", "reports",
    "handover", "asbuilt", "valves", "spooling", "procurement",
    "finishing", "precomm", "field_control",
})

_ROLE_MODULES: Mapping[str, FrozenSet[str]] = {
    "admin": ALL_MODULES,
    "project_manager": ALL_MODULES,
    "engineer": ALL_MODULES - frozenset({"value_plans"}),
    "planner": frozenset({
        "dashboard", "project", "line_list", "documents", "technical_query",
        "data_exchange", "procurement", "spooling", "joints", "supports",
        "work_front", "control_tower", "reports", "execution_intelligence",
        "execution_os", "value_plans", "test_package", "handover",
        "smart_entry",
    }),
    "inspector": frozenset({
        "dashboard", "project", "line_list", "documents", "technical_query",
        "joints", "welder_mgmt", "supports", "valves", "ndt", "qaqc",
        "test_package", "precomm", "finishing", "handover", "field_control",
        "reports", "asbuilt", "digital_turnover", "smart_entry",
    }),
    "supervisor": frozenset({
        "dashboard", "project", "line_list", "spooling", "joints",
        "welder_mgmt", "supports", "erection", "valves", "ndt",
        "test_package", "finishing", "field_control", "work_front",
        "mobile_field", "site_execution", "reports", "smart_entry",
        "technical_query", "documents",
    }),
    "welder": frozenset({
        "dashboard", "joints", "welder_mgmt", "supports", "erection",
        "field_control", "mobile_field", "site_execution", "smart_entry",
    }),
    "storekeeper": frozenset({
        "dashboard", "project", "line_list", "procurement", "documents",
        "reports", "spooling", "smart_entry",
    }),
    "document_controller": frozenset({
        "dashboard", "project", "line_list", "documents", "technical_query",
        "data_exchange", "reports", "asbuilt", "digital_turnover",
        "handover",
    }),
    "client_rep": frozenset({
        "dashboard", "project", "documents", "technical_query", "qaqc",
        "ndt", "test_package", "handover", "reports", "asbuilt",
        "digital_turnover", "joints", "line_list",
    }),
    "viewer": _READ_REGISTERS,
}


def accessible_modules(role: Optional[str]) -> FrozenSet[str]:
    key = canonical_role(role)
    return _ROLE_MODULES.get(key, _READ_REGISTERS)


def can_access_module(role: Optional[str], module_key: str) -> bool:
    return module_key in accessible_modules(role)


def can_manage_users(role: Optional[str]) -> bool:
    return canonical_role(role) in {"admin", "project_manager"}


def can_backup_database(role: Optional[str]) -> bool:
    return canonical_role(role) in {"admin", "project_manager", "engineer"}


def first_allowed_module(role: Optional[str], preferred: str = "dashboard") -> str:
    allowed = accessible_modules(role)
    if preferred in allowed:
        return preferred
    for key in MODULE_KEYS:
        if key in allowed:
            return key
    return "dashboard"


def access_matrix_text() -> str:
    lines = [
        "PipeAgent access levels (site piping workspace)",
        "",
    ]
    for key, label in SITE_ROLES:
        modules = sorted(accessible_modules(key))
        lines.append(f"{label}  [{key}]")
        lines.append("  " + ", ".join(modules))
        lines.append("")
    return "\n".join(lines)


def iter_site_roles() -> Sequence[Tuple[str, str]]:
    return SITE_ROLES


def covered_activity_keys(nav_keys: Iterable[str]) -> FrozenSet[str]:
    return frozenset(key for key, _title in SITE_ACTIVITY_CHAIN if key in set(nav_keys))
