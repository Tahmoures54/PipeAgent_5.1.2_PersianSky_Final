# -*- coding: utf-8 -*-
"""Site role → module access for the PipeAgent workspace shell."""

from __future__ import annotations

import re
from pathlib import Path

from services.module_access import (
    MODULE_KEYS,
    SITE_ACTIVITY_CHAIN,
    accessible_modules,
    can_access_module,
    can_backup_database,
    can_manage_users,
    canonical_role,
    first_allowed_module,
    role_label,
)


def test_session_enum_roles_map_to_site_keys():
    assert canonical_role("SUPER_ADMIN") == "admin"
    assert canonical_role("PROJECT_MGR") == "project_manager"
    assert canonical_role("QC_MANAGER") == "inspector"
    assert canonical_role("QC_INSPECTOR") == "inspector"
    assert canonical_role("CLIENT_REP") == "client_rep"
    assert canonical_role("SHOP_SUPERVISOR") == "supervisor"
    assert canonical_role("PLANNING_ENG") == "planner"
    assert canonical_role("STOREKEEPER") == "storekeeper"


def test_admin_sees_every_module():
    assert accessible_modules("admin") == frozenset(MODULE_KEYS)
    assert can_manage_users("project_manager")
    assert can_backup_database("engineer")
    assert not can_manage_users("viewer")
    assert not can_backup_database("welder")


def test_storekeeper_and_welder_are_scoped():
    store = accessible_modules("storekeeper")
    assert "procurement" in store
    assert "ndt" not in store
    welder = accessible_modules("welder")
    assert "joints" in welder
    assert "documents" not in welder
    assert can_access_module("inspector", "technical_query")
    assert not can_access_module("viewer", "execution_os")


def test_nav_structure_covers_module_keys():
    text = (Path(__file__).resolve().parents[2] / "ui" / "main_window.py").read_text(
        encoding="utf-8"
    )
    nav_keys = set(re.findall(r'"([a-z_]+)",\s+"Ctrl', text))
    missing = set(MODULE_KEYS) - nav_keys
    extra = nav_keys - set(MODULE_KEYS)
    assert not missing, missing
    assert not extra, extra
    activity_keys = {key for key, _title in SITE_ACTIVITY_CHAIN}
    assert activity_keys <= set(MODULE_KEYS)
    assert "technical_query" in activity_keys
    assert first_allowed_module("welder") == "dashboard"
    assert role_label("admin").lower().startswith("admin")


def test_shell_uses_teamwork_and_help_for_support():
    text = (Path(__file__).resolve().parents[2] / "ui" / "main_window.py").read_text(
        encoding="utf-8"
    )
    assert 'addMenu("&Teamwork")' in text
    assert 'QPushButton("Teamwork")' in text
    assert "Contact Support" in text
    assert 'QPushButton("Support")' not in text
    assert 'addMenu("&Users")' not in text
    assert "AlignLeft" in text
