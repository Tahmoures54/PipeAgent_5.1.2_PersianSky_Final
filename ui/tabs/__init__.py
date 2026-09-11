# -*- coding: utf-8 -*-
"""
PipeAgent — Tabs package (Central Export Router)
Version : 5.3.0
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Shared utilities (import first so child modules can use) ────
from . import _shared

# ── Core operations ─────────────────────────────────────────────
from .dashboard_tab              import DashboardTab
from .project_setup_tab          import ProjectSetupTab
from .line_list_tab              import LineListTab

# ── Engineering registers ───────────────────────────────────────
from .joints_tab                 import JointsTab
from .ndt_tab                    import NDTTab
from .welder_mgmt_tab            import WelderMgmtTab
from .valves_tab                 import ValvesTab
from .supports_tab               import SupportsTab
from .spooling_tab               import SpoolingTab
from .test_package_tab           import TestPackageTab

# ── Site execution ──────────────────────────────────────────────
from .work_front_tab             import WorkFrontTab
from .field_erection_tab         import FieldErectionTab
from .field_control_tab          import FieldControlTab
from .site_execution_tab         import SiteExecutionTab

# ── Quality & completion ────────────────────────────────────────
from .qaqc_tab                   import QAQCTab
from .finishing_tab              import FinishingTab
from .precomm_tab                import PreCommTab
from .handover_tab               import HandoverTab
from .asbuilt_tab                import AsBuiltTab
from .digital_turnover_tab       import DigitalTurnoverTab

# ── Materials & procurement ─────────────────────────────────────
from .procurement_tab            import ProcurementTab

# ── Documents & data ────────────────────────────────────────────
from .documents_tab              import DocumentsTab
from .technical_query_tab        import TechnicalQueryTab
from .data_exchange_tab          import DataExchangeTab
from .smart_entry_tab            import SmartEntryTab
from .mobile_field_tab           import MobileFieldTab

# ── Intelligence & analytics ────────────────────────────────────
from .reports_tab                import ReportsTab
from .execution_intelligence_tab import ExecutionIntelligenceTab
from .execution_os_tab           import ExecutionOSTab
from .control_tower_tab          import ControlTowerTab
from .ai_assistant_tab           import AIAssistantTab
from .value_and_plans_tab        import ValueAndPlansTab


__all__ = [
    "_shared",
    # Core
    "DashboardTab", "ProjectSetupTab", "LineListTab",
    # Engineering
    "JointsTab", "NDTTab", "WelderMgmtTab", "ValvesTab",
    "SupportsTab", "SpoolingTab", "TestPackageTab",
    # Site
    "WorkFrontTab", "FieldErectionTab", "FieldControlTab", "SiteExecutionTab",
    # Quality
    "QAQCTab", "FinishingTab", "PreCommTab", "HandoverTab",
    "AsBuiltTab", "DigitalTurnoverTab",
    # Materials
    "ProcurementTab",
    # Documents / data
    "DocumentsTab", "TechnicalQueryTab", "DataExchangeTab", "SmartEntryTab", "MobileFieldTab",
    # Intelligence
    "ReportsTab", "ExecutionIntelligenceTab", "ExecutionOSTab",
    "ControlTowerTab", "AIAssistantTab", "ValueAndPlansTab",
]