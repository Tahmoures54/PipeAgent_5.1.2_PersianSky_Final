# -*- coding: utf-8 -*-
# ui/main_window.py – PipeAgent 5.2.4 (Fixed & Enhanced)
"""
PipeAgent — Piping Execution Operating System
══════════════════════════════════════════════
Version : 5.2.3 (Production - Corrected)
Engine  : PyQt6
Design  : Persian-Sky Professional Workspace Shell

Fixes applied in this revision
──────────────────────────────
• Single-source QAction per module (no duplicate shortcuts)
• Ctrl+Alt+B conflict resolved (Backup → Ctrl+Shift+B)
• Sidebar toggle (Ctrl+B) and refresh (F5) registered once
• ActionRegistry hardened against duplicate keys
• Smallest font sizes bumped from 9px to 10px (QFont sanity)
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from html import escape
from urllib.parse import urlencode

from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QUrl, QPropertyAnimation, QEasingCurve,
    pyqtProperty, pyqtSignal,
)
from PyQt6.QtGui import (
    QColor, QAction, QKeySequence, QDesktopServices, QPainter,
)
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QStatusBar, QLabel, QMessageBox, QFrame,
    QPushButton, QToolButton, QSizePolicy, QScrollArea, QAbstractScrollArea,
    QTableWidget, QTableView, QTreeWidget, QHeaderView,
    QLineEdit,
    QGraphicsDropShadowEffect,
)

from config import (
    APP_NAME, APP_VERSION, ORG_NAME, BRAND_TAGLINE, PRODUCT_POSITIONING,
    DATABASE_PATH, BACKUP_DIR, PROJECT_ROOT,
)
from db.manager import DatabaseManager
from security.session import SessionManager
from services.license import check_license, format_license_status, get_license_info

# ── Tab Imports ───────────────────────────────────────────
from ui.tabs.dashboard_tab import DashboardTab
from ui.tabs.project_setup_tab import ProjectSetupTab
from ui.tabs.line_list_tab import LineListTab
from ui.tabs.documents_tab import DocumentsTab
from ui.tabs.procurement_tab import ProcurementTab
from ui.tabs.spooling_tab import SpoolingTab
from ui.tabs.joints_tab import JointsTab
from ui.tabs.supports_tab import SupportsTab
from ui.tabs.field_erection_tab import FieldErectionTab
from ui.tabs.ndt_tab import NDTTab
from ui.tabs.test_package_tab import TestPackageTab
from ui.tabs.handover_tab import HandoverTab
from ui.tabs.reports_tab import ReportsTab
from ui.tabs.ai_assistant_tab import AIAssistantTab
from ui.tabs.field_control_tab import FieldControlTab
from ui.tabs.work_front_tab import WorkFrontTab
from ui.tabs.control_tower_tab import ControlTowerTab
from ui.tabs.mobile_field_tab import MobileFieldTab
from ui.tabs.digital_turnover_tab import DigitalTurnoverTab
from ui.tabs.data_exchange_tab import DataExchangeTab
from ui.tabs.smart_entry_tab import SmartEntryTab
from ui.tabs.welder_mgmt_tab import WelderMgmtTab
from ui.tabs.qaqc_tab import QAQCTab
from ui.tabs.valves_tab import ValvesTab
from ui.tabs.finishing_tab import FinishingTab
from ui.tabs.precomm_tab import PreCommTab
from ui.tabs.asbuilt_tab import AsBuiltTab
from ui.tabs.execution_intelligence_tab import ExecutionIntelligenceTab
from ui.tabs.execution_os_tab import ExecutionOSTab
from ui.tabs.value_and_plans_tab import ValueAndPlansTab
from ui.tabs.site_execution_tab import SiteExecutionTab

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  NOTIFICATION CENTER
# ═══════════════════════════════════════════════════════════

class NotificationBadge(QLabel):
    """نشان تعداد اعلان‌ها"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("notifBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._count = 0
        self.hide()

    def set_count(self, count: int):
        self._count = count
        if count > 0:
            self.setText(str(min(count, 99)) if count < 100 else "99+")
            self.show()
        else:
            self.hide()


class NotificationCenter(QFrame):
    """مرکز اعلان‌ها با Signal برای تغییر تعداد"""

    countChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("notifPanel")
        self.setFixedWidth(380)
        self.setMaximumHeight(450)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header Bar
        header_bar = QHBoxLayout()
        header_bar.setContentsMargins(12, 8, 12, 8)
        header = QLabel("🔔  Notifications")
        header.setObjectName("notifHeader")
        clear_btn = QPushButton("Clear All")
        clear_btn.setObjectName("notifClearBtn")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self.clear_all)
        header_bar.addWidget(header, 1)
        header_bar.addWidget(clear_btn)

        header_frame = QFrame()
        header_frame.setObjectName("notifHeaderFrame")
        header_frame.setLayout(header_bar)
        layout.addWidget(header_frame)

        # Scroll Area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 8, 8, 8)
        self._content_layout.setSpacing(6)
        self._content_layout.addStretch()
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll, 1)

        self._empty_label = QLabel("No notifications")
        self._empty_label.setStyleSheet(
            "color:#7a9ab3; padding:30px; font-size:12px; background: transparent;"
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._content_layout.insertWidget(0, self._empty_label)

        self._notifications: list[dict] = []

    def add_notification(self, title: str, message: str, level: str = "info"):
        """اضافه کردن اعلان جدید"""
        notif = {"title": title, "message": message, "level": level, "time": datetime.now()}
        self._notifications.insert(0, notif)
        self._empty_label.hide()

        card = QFrame()
        card.setObjectName(f"notifCard_{level}")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setSpacing(2)

        top_row = QHBoxLayout()
        icon_map = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "success": "✅"}
        icon = QLabel(icon_map.get(level, "•"))
        icon.setStyleSheet("font-size:14px; background: transparent;")
        t = QLabel(f"<b>{escape(title)}</b>")
        t.setStyleSheet("color:#173B45; font-size:11px; background:transparent;")
        t.setWordWrap(True)
        top_row.addWidget(icon)
        top_row.addWidget(t, 1)

        m = QLabel(escape(message))
        m.setWordWrap(True)
        m.setStyleSheet(
            "color:#5F7D84; font-size:11px; padding-left:22px; background: transparent;"
        )
        ts = QLabel(notif["time"].strftime("%Y-%m-%d  %H:%M"))
        ts.setStyleSheet(
            "color:#3f6070; font-size:10px; padding-left:22px; background: transparent;"
        )
        ts.setAlignment(Qt.AlignmentFlag.AlignRight)

        cl.addLayout(top_row)
        cl.addWidget(m)
        cl.addWidget(ts)
        self._content_layout.insertWidget(0, card)

        self.countChanged.emit(self.count)

    @property
    def count(self) -> int:
        return len(self._notifications)

    def clear_all(self):
        """پاک کردن تمام اعلان‌ها"""
        self._notifications.clear()
        while self._content_layout.count() > 0:
            item = self._content_layout.takeAt(0)
            if item.widget() and item.widget() != self._empty_label:
                item.widget().deleteLater()
        self._content_layout.addStretch()
        self._empty_label.show()
        self._content_layout.insertWidget(0, self._empty_label)
        self.countChanged.emit(0)


# ═══════════════════════════════════════════════════════════
#  COLLAPSIBLE SIDEBAR
# ═══════════════════════════════════════════════════════════

class CollapsibleSidebar(QFrame):
    """Animated sidebar with smooth expand/collapse transitions."""

    EXPANDED_WIDTH = 260
    COLLAPSED_WIDTH = 58

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._expanded = True
        self._anim_width = self.EXPANDED_WIDTH
        self.setFixedWidth(self.EXPANDED_WIDTH)
        self.setMinimumWidth(self.COLLAPSED_WIDTH)

        self._animation = QPropertyAnimation(self, b"animWidth")
        self._animation.setDuration(280)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Toggle Button
        self._toggle_btn = QToolButton()
        self._toggle_btn.setObjectName("sidebarToggle")
        self._toggle_btn.setText("☰   PipeAgent")
        self._toggle_btn.setToolTip("Toggle Sidebar (Ctrl+B)")
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setFixedHeight(48)
        self._toggle_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._toggle_btn.clicked.connect(self.toggle)
        self._layout.addWidget(self._toggle_btn)

        # Search
        self._search = QLineEdit()
        self._search.setObjectName("navSearch")
        self._search.setPlaceholderText("🔍  Search PipeAgent…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._filter_nav)
        self._layout.addWidget(self._search)

        # Scrollable Nav
        self._scroll = QScrollArea()
        self._scroll.setObjectName("navScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._nav_container = QWidget()
        self._nav_layout = QVBoxLayout(self._nav_container)
        self._nav_layout.setContentsMargins(0, 4, 0, 4)
        self._nav_layout.setSpacing(0)
        self._scroll.setWidget(self._nav_container)
        self._layout.addWidget(self._scroll, 1)

        # Footer
        self._footer = QLabel(
            f"PipeAgent v{APP_VERSION}\n{PRODUCT_POSITIONING}\n{BRAND_TAGLINE}"
        )
        self._footer.setObjectName("sidebarFooter")
        self._footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._footer)

        self._nav_buttons: dict[str, QToolButton] = {}
        self._group_labels: list[QLabel] = []
        self._all_nav_widgets: list[QWidget] = []

    @pyqtProperty(int)
    def animWidth(self):
        return self._anim_width

    @animWidth.setter
    def animWidth(self, value):
        self._anim_width = value
        self.setFixedWidth(value)

    def toggle(self):
        self._expanded = not self._expanded
        target = self.EXPANDED_WIDTH if self._expanded else self.COLLAPSED_WIDTH
        self._animation.stop()
        self._animation.setStartValue(self.width())
        self._animation.setEndValue(target)
        self._animation.start()

        for btn in self._nav_buttons.values():
            self._update_button_text_visibility(btn, self._expanded)
        for lbl in self._group_labels:
            lbl.setVisible(self._expanded)
        self._search.setVisible(self._expanded)
        self._footer.setVisible(self._expanded)
        self._toggle_btn.setText("☰   PipeAgent" if self._expanded else "☰")

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    def add_group(self, title: str):
        lbl = QLabel(title)
        lbl.setObjectName("navGroupLabel")
        self._nav_layout.addWidget(lbl)
        self._group_labels.append(lbl)
        self._all_nav_widgets.append(lbl)

    def add_nav_button(self, key: str, icon: str, text: str, shortcut: str = None) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("navButton")
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        btn.setText(f"  {icon}   {text}")
        btn.setProperty("navIcon", icon)
        btn.setProperty("navText", text)
        btn.setProperty("navKey", key)
        btn.setToolTip(f"{text}" + (f"  ({shortcut})" if shortcut else ""))

        self._nav_layout.addWidget(btn)
        self._nav_buttons[key] = btn
        self._all_nav_widgets.append(btn)
        return btn

    def add_separator(self):
        sep = QFrame()
        sep.setObjectName("navSeparator")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        self._nav_layout.addWidget(sep)
        self._all_nav_widgets.append(sep)

    def finalize(self):
        self._nav_layout.addStretch()

    def set_active(self, key: str):
        for k, btn in self._nav_buttons.items():
            btn.setChecked(k == key)

    def _update_button_text_visibility(self, btn: QToolButton, show: bool):
        icon_char = btn.property("navIcon") or ""
        text = btn.property("navText") or ""
        btn.setText(f"  {icon_char}   {text}" if show else f"  {icon_char}")

    def _filter_nav(self, text: str):
        text_lower = text.lower().strip()
        for widget in self._all_nav_widgets:
            if isinstance(widget, QToolButton):
                nav_text = (widget.property("navText") or "").lower()
                widget.setVisible(text_lower in nav_text or text_lower == "")
            elif isinstance(widget, QLabel) and widget.objectName() == "navGroupLabel":
                widget.setVisible(text_lower == "")
            elif isinstance(widget, QFrame) and widget.objectName() == "navSeparator":
                widget.setVisible(text_lower == "")


# ═══════════════════════════════════════════════════════════
#  BREADCRUMB BAR
# ═══════════════════════════════════════════════════════════

class BreadcrumbBar(QFrame):
    """نوار مسیر ناوبری"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("breadcrumb")
        self.setFixedHeight(36)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(20, 0, 20, 0)
        self._layout.setSpacing(4)
        self._label = QLabel(
            "<span style='color:#6ccff6;'>⌂</span>  "
            "<span style='color:#9fe7ff; font-weight:700;'>PipeAgent</span>"
        )
        self._label.setObjectName("breadcrumbLabel")
        self._layout.addWidget(self._label)
        self._layout.addStretch()
        self._time_label = QLabel()
        self._time_label.setObjectName("breadcrumbTime")
        self._layout.addWidget(self._time_label)

    def set_path(self, group: str, module: str):
        safe_group = escape(group)
        safe_module = escape(module)
        self._label.setText(
            f"<span style='color:#6ccff6;'>⌂</span>  "
            f"<span style='color:#9fe7ff; font-weight:700;'>PipeAgent</span>  "
            f"<span style='color:#a2c2dc;'>›</span>  "
            f"<span style='color:#7a9ab3;'>{safe_group}</span>  "
            f"<span style='color:#a2c2dc;'>›</span>  "
            f"<span style='color:#9fe7ff; font-weight:700;'>{safe_module}</span>"
        )

    def update_time(self):
        self._time_label.setText(datetime.now().strftime("📅  %Y-%m-%d       🕒  %H:%M:%S"))


# ═══════════════════════════════════════════════════════════
#  ACTION REGISTRY (hardened)
# ═══════════════════════════════════════════════════════════

class ActionRegistry:
    """
    Central registry for QActions.

    Guarantees:
      • One action per key (duplicate keys are silently ignored).
      • A shortcut can only be registered to a single key. Attempts to
        reuse a shortcut produce a single warning, then the registration
        is rejected.
    """

    def __init__(self):
        self.actions: dict[str, QAction] = {}
        self.shortcuts: dict[str, str] = {}   # shortcut -> owning key

    def register(self, key: str, action: QAction, shortcut: Optional[str] = None) -> bool:
        """Register an action. Returns True if newly added, False otherwise."""
        if key in self.actions:
            logger.debug("Action '%s' already registered; ignoring duplicate", key)
            return False

        if shortcut:
            owner = self.shortcuts.get(shortcut)
            if owner is not None and owner != key:
                logger.warning(
                    "Shortcut '%s' is already bound to '%s'; refusing to bind it to '%s'",
                    shortcut, owner, key,
                )
                return False
            self.shortcuts[shortcut] = key

        self.actions[key] = action
        return True

    def get(self, key: str) -> Optional[QAction]:
        return self.actions.get(key)

    def get_all(self) -> list[QAction]:
        return list(self.actions.values())


# ═══════════════════════════════════════════════════════════
#  BACKUP SERVICE
# ═══════════════════════════════════════════════════════════

class BackupService:
    """سرویس پشتیبان‌گیری دیتابیس SQLite"""

    @staticmethod
    def backup_database(source_path, backup_dir: Path) -> Path:
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Database file not found: {source}")

        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = backup_dir / f"PipeAgent_Backup_{stamp}.db"

        try:
            with sqlite3.connect(source) as source_conn:
                with sqlite3.connect(target) as target_conn:
                    source_conn.backup(target_conn)
            logger.info("Database backup created successfully: %s", target)
            return target
        except sqlite3.DatabaseError as e:
            logger.exception("SQLite database backup failed")
            raise Exception(f"Database backup failed: {e}") from e
        except Exception:
            logger.exception("Unexpected error during backup")
            raise


# ═══════════════════════════════════════════════════════════
#  MAIN WINDOW
# ═══════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """PipeAgent — Piping Execution Operating System Shell."""

    # Navigation Structure (10 groups, 31 modules)
    NAV_STRUCTURE = [
        ("COMMAND CENTER", [
            ("⌂", "Dashboard",              "dashboard",        "Ctrl+D"),
            ("▣", "Project Setup",          "project",          "Ctrl+Alt+P"),
        ]),
        ("ENGINEERING", [
            ("≡", "Line List",              "line_list",        "Ctrl+Shift+L"),
            ("◈", "Document Control",       "documents",        "Ctrl+Shift+D"),
            ("⇄", "Data Exchange",          "data_exchange",    "Ctrl+E"),
        ]),
        ("PROCUREMENT", [
            ("▤", "Materials & MTO",        "procurement",      "Ctrl+Alt+M"),
        ]),
        ("FABRICATION", [
            ("◫", "Spooling",               "spooling",         "Ctrl+Alt+S"),
            ("◉", "Joints / WJCS",          "joints",           "Ctrl+Alt+J"),
            ("🔧", "Welder Qualification",   "welder_mgmt",      "Ctrl+Alt+W"),
        ]),
        ("CONSTRUCTION", [
            ("◇", "Pipe Supports",          "supports",         "Ctrl+Alt+U"),
            ("➤", "Field Erection",         "erection",         "Ctrl+Alt+F"),
            ("🔩", "Valves & In-line",       "valves",           "Ctrl+Alt+V"),
        ]),
        ("QA / QC & NDT", [
            ("◌", "NDT / Inspection",       "ndt",              "Ctrl+Alt+N"),
            ("✅", "QA/QC & Punch",          "qaqc",             "Ctrl+Alt+Q"),
        ]),
        ("TESTING & COMPLETION", [
            ("▱", "Test Packages",          "test_package",     "Ctrl+Shift+T"),
            ("🚀", "Pre-Commissioning",      "precomm",          "Ctrl+Shift+P"),
            ("🎨", "Finishing",              "finishing",        "Ctrl+Shift+F"),
            ("✓", "Handover / MC",          "handover",         "Ctrl+Shift+H"),
        ]),
        ("SITE OPERATIONS", [
            ("⚒", "Field Control",          "field_control",    "Ctrl+Shift+C"),
            ("▦", "Work Front",             "work_front",       "Ctrl+W"),
            ("◈", "Control Tower",          "control_tower",    "Ctrl+T"),
            ("📱", "Mobile Field Hub",       "mobile_field",     "Ctrl+M"),
            ("🏗", "Site Execution Control", "site_execution",   "Ctrl+Shift+E"),
        ]),
        ("ANALYTICS & INTELLIGENCE", [
            ("▥", "Reports & Analytics",    "reports",          "Ctrl+R"),
            ("✦", "AI Assistant",           "ai_assistant",     "Ctrl+Shift+A"),
            ("⚡", "Quick Entry",            "smart_entry",      "Ctrl+K"),
            ("🧠", "Execution Intelligence", "execution_intelligence", "Ctrl+I"),
            ("⚡", "Execution OS",           "execution_os",     "Ctrl+Shift+I"),
            ("$", "Value & Plans",          "value_plans",      "Ctrl+Alt+Y"),
        ]),
        ("TURNOVER & AS-BUILT", [
            ("📐", "As-Built & Dossier",    "asbuilt",          "Ctrl+Alt+B"),
            ("▣", "Digital Turnover",       "digital_turnover", "Ctrl+Alt+D"),
        ]),
    ]

    TAB_CLASSES = [
        ("dashboard",        DashboardTab),
        ("project",          ProjectSetupTab),
        ("line_list",        LineListTab),
        ("documents",        DocumentsTab),
        ("data_exchange",    DataExchangeTab),
        ("procurement",      ProcurementTab),
        ("spooling",         SpoolingTab),
        ("joints",           JointsTab),
        ("welder_mgmt",      WelderMgmtTab),
        ("supports",         SupportsTab),
        ("erection",         FieldErectionTab),
        ("valves",           ValvesTab),
        ("ndt",              NDTTab),
        ("qaqc",             QAQCTab),
        ("test_package",     TestPackageTab),
        ("precomm",          PreCommTab),
        ("finishing",        FinishingTab),
        ("handover",         HandoverTab),
        ("field_control",    FieldControlTab),
        ("work_front",       WorkFrontTab),
        ("control_tower",    ControlTowerTab),
        ("mobile_field",     MobileFieldTab),
        ("reports",          ReportsTab),
        ("ai_assistant",     AIAssistantTab),
        ("smart_entry",      SmartEntryTab),
        ("execution_intelligence", ExecutionIntelligenceTab),
        ("execution_os",     ExecutionOSTab),
        ("value_plans",      ValueAndPlansTab),
        ("site_execution",   SiteExecutionTab),
        ("asbuilt",          AsBuiltTab),
        ("digital_turnover", DigitalTurnoverTab),
    ]

    def __init__(self, db: DatabaseManager, session_manager: SessionManager):
        super().__init__()
        self.db = db
        self.session_manager = session_manager
        self.setWindowTitle(f"PipeAgent v{APP_VERSION} — Piping Execution Operating System")
        self.setMinimumSize(1280, 800)
        self.resize(1600, 960)

        # State
        self._current_group = "COMMAND CENTER"
        self._current_module = "Dashboard"
        self._current_key = "dashboard"
        self._force_close = False
        self._notif_btn: Optional[QPushButton] = None

        # Central registries
        self._action_registry = ActionRegistry()
        self._module_actions: dict[str, QAction] = {}

        self._apply_stylesheet()
        self._total_modules = len(self.TAB_CLASSES)

        self.tabs: dict[str, QWidget] = {}
        self._tab_pages: dict[str, QScrollArea] = {}

        # ⚠ ORDER MATTERS: build module actions FIRST so both
        # the sidebar and the menu bar can reuse them.
        self._build_module_actions()
        self._setup_ui()
        self._create_menu_bar()

        # Deferred loading
        self._tabs_loaded = False
        self._tabs_loading = False
        self._load_index = 0

        # Timers
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status_bar)
        self._status_timer.start(30_000)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._breadcrumb.update_time)
        self._clock_timer.start(1000)

        self._update_status_bar()
        self._breadcrumb.update_time()

        self._check_license()

        QTimer.singleShot(0, self._begin_tab_loading)
        logger.info(
            "PipeAgent v%s shell created; deferred module loading scheduled (user=%s)",
            APP_VERSION, session_manager.username
        )

    # ═══════════════════════════════════════════════════════
    #  MODULE ACTIONS — THE SINGLE SOURCE OF TRUTH
    # ═══════════════════════════════════════════════════════

    def _build_module_actions(self):
        """
        Create exactly ONE QAction per module in NAV_STRUCTURE.

        Both the sidebar and the menu bar will reference these instances.
        Shortcuts are attached to these actions only — never duplicated.
        """
        for group_name, items in self.NAV_STRUCTURE:
            for icon, text, key, shortcut in items:
                act = QAction(f"{icon}  {text}", self)
                if shortcut:
                    act.setShortcut(QKeySequence(shortcut))
                    act.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
                act.setStatusTip(f"Open {text}")
                act.triggered.connect(
                    lambda checked=False, k=key: self.switch_tab(k)
                )
                self.addAction(act)

                self._module_actions[key] = act
                self._action_registry.register(key, act, shortcut)

        logger.info("Registered %d module actions", len(self._module_actions))

    # ═══════════════════════════════════════════════════════
    #  LICENSE CHECK
    # ═══════════════════════════════════════════════════════

    def _check_license(self):
        try:
            license_valid = check_license(self.db)
        except Exception:
            logger.exception("License validation failed")
            license_valid = False

        if not license_valid:
            self._notif_center.add_notification(
                "License Warning",
                "Your license has expired or is invalid. Some features may be restricted.",
                "warning"
            )
            self._notif_badge.set_count(self._notif_center.count)
            QTimer.singleShot(
                250,
                lambda: QMessageBox.warning(
                    self,
                    "License Expired",
                    "Your license has expired or is invalid.\n\n"
                    "Please contact support for renewal.",
                    QMessageBox.StandardButton.Ok
                )
            )

    # ═══════════════════════════════════════════════════════
    #  STYLESHEET
    # ═══════════════════════════════════════════════════════

    def _apply_stylesheet(self):
        """Apply the PipeAgent Persian-Sky professional workspace theme."""
        self.setStyleSheet("""
        QMainWindow { background: #F4FBFC; }
        QWidget { font-family: 'Segoe UI'; font-size: 12px; color: #173B45; }
        QWidget:disabled { color: #8AA5AC; }
        QFrame#topbar { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #087F8C,stop:0.55 #13A7B5,stop:1 #55C7D0); border-bottom: 1px solid #08727D; }
        QLabel#brand { color: white; font-size: 22px; font-weight: 900; letter-spacing: 1px; background: transparent; }
        QLabel#brandSub { color: #DDFBFD; font-size: 10px; font-weight: 800; letter-spacing: 2px; background: transparent; }
        QLabel#userBadge { color: #075D67; background: #E8FAFB; border: 1px solid #A9E4E8; border-radius: 14px; padding: 6px 14px; font-weight: 700; font-size: 12px; }
        QLabel#liveIndicator { color: #EFFFFF; font-size: 10px; font-weight: 800; padding: 5px 10px; background: transparent; }
        QPushButton#topAction { background: rgba(255,255,255,0.14); color: white; border: 1px solid rgba(255,255,255,0.32); border-radius: 8px; padding: 7px 13px; font-weight: 700; font-size: 11px; }
        QPushButton#topAction:hover { background: rgba(255,255,255,0.25); border-color: white; }
        QPushButton#supportAction { background: white; color: #087F8C; border: none; border-radius: 8px; padding: 7px 13px; font-weight: 800; }
        QPushButton#supportAction:hover { background: #E7FAF8; color: #05616A; }
        QLabel#notifBadge { background: #E05A63; color: white; font-size: 10px; font-weight: 800; border-radius: 10px; min-width: 20px; min-height: 20px; padding: 2px 6px; }
        QFrame#sidebar { background: white; border-right: 1px solid #CBE8EB; }
        QToolButton#sidebarToggle { color: #087F8C; background: #F1FBFC; border: none; border-bottom: 1px solid #CBE8EB; font-size: 13px; font-weight: 900; text-align: left; padding-left: 16px; letter-spacing: 1px; }
        QToolButton#sidebarToggle:hover { background: #E2F7F8; color: #056A75; }
        QLineEdit#navSearch { background: #F7FCFD; color: #173B45; border: 1px solid #B9DDE1; border-radius: 8px; padding: 8px 10px; margin: 8px 12px; font-size: 12px; }
        QLineEdit#navSearch:focus { border-color: #13A7B5; background: white; }
        QLineEdit#navSearch::placeholder { color: #76959D; }
        QScrollArea#navScroll { background: transparent; border: none; }
        QLabel#navGroupLabel { color: #6C8D95; font-size: 10px; font-weight: 800; letter-spacing: 1.5px; padding: 14px 18px 4px 18px; background: transparent; }
        QFrame#navSeparator { background: #E0EFF1; margin: 4px 14px; }
        QToolButton#navButton { color: #3B5C64; background: transparent; border: none; border-radius: 8px; text-align: left; padding: 10px 14px; margin: 1px 8px; font-size: 12px; font-weight: 600; }
        QToolButton#navButton:hover { color: #087F8C; background: #EAF8F9; }
        QToolButton#navButton:checked { color: white; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #087F8C,stop:1 #13A7B5); font-weight: 800; }
        QLabel#sidebarFooter { color: #86A3AA; font-size: 10px; padding: 10px 14px; border-top: 1px solid #E0EFF1; background: transparent; }
        QFrame#breadcrumb { background: white; border-bottom: 1px solid #D6EAEC; }
        QLabel#breadcrumbLabel { color: #3B5C64; font-size: 12px; font-weight: 600; }
        QLabel#breadcrumbTime { color: #78949B; font-size: 11px; }
        QStackedWidget#contentStack { background: #F4FBFC; }
        QStatusBar { background: white; color: #6C8D95; border-top: 1px solid #D6EAEC; font-size: 11px; }
        QLabel#status_label { color: #6C8D95; padding: 3px 12px; font-size: 11px; background: transparent; }
        QFrame#notifPanel { background: white; border: 1px solid #B9DDE1; border-radius: 10px; }
        QFrame#notifHeaderFrame { background: #F2FBFC; border-bottom: 1px solid #D6EAEC; border-radius: 10px 10px 0 0; }
        QLabel#notifHeader { color: #087F8C; font-size: 13px; font-weight: 700; background: transparent; }
        QPushButton#notifClearBtn { background: transparent; color: #087F8C; border: none; font-size: 11px; font-weight: 700; padding: 4px 8px; }
        QFrame[objectName^="notifCard_"] { background: #F7FCFD; border: 1px solid #D6EAEC; border-radius: 6px; }
        QFrame#notifCard_warning { border-left: 3px solid #D79B1E; }
        QFrame#notifCard_error { border-left: 3px solid #D94B57; }
        QFrame#notifCard_info { border-left: 3px solid #13A7B5; }
        QFrame#notifCard_success { border-left: 3px solid #22A06B; }
        QTableWidget, QTableView, QTreeWidget, QTreeView, QListView { background: white; alternate-background-color: #F5FAFB; border: 1px solid #CBE8EB; border-radius: 7px; gridline-color: #E5F0F1; color: #173B45; selection-background-color: #CFF3F4; selection-color: #075D67; }
        QHeaderView::section { background: #E8F7F8; color: #17636C; font-weight: 800; font-size: 10px; padding: 8px 10px; border: none; border-bottom: 2px solid #8DD7DC; border-right: 1px solid #D6EAEC; }
        QScrollBar:vertical { background: #EDF7F8; width: 10px; border-radius: 5px; }
        QScrollBar::handle:vertical { background: #A8DCE0; border-radius: 5px; min-height: 30px; }
        QScrollBar::handle:vertical:hover { background: #13A7B5; }
        QScrollBar:horizontal { background: #EDF7F8; height: 10px; border-radius: 5px; }
        QScrollBar::handle:horizontal { background: #A8DCE0; border-radius: 5px; min-width: 30px; }
        QScrollBar::handle:horizontal:hover { background: #13A7B5; }
        QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
        QPushButton { background: white; color: #087F8C; border: 1px solid #A9DDE1; border-radius: 7px; padding: 8px 16px; font-weight: 800; font-size: 12px; }
        QPushButton:hover { background: #EAF8F9; border-color: #13A7B5; }
        QPushButton:pressed { background: #D5F1F3; }
        QPushButton[primary="true"], QPushButton#actionBtn, QPushButton#saveBtn { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #087F8C,stop:1 #13A7B5); color: white; border: none; font-weight: 800; }
        QPushButton[primary="true"]:hover, QPushButton#actionBtn:hover, QPushButton#saveBtn:hover { background: #056A75; color: white; }
        QGroupBox { font-weight: 800; font-size: 12px; color: #087F8C; border: 1px solid #CBE8EB; border-radius: 8px; margin-top: 12px; padding-top: 16px; background: white; }
        QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 8px; color: #13A7B5; }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTextEdit, QPlainTextEdit { background: white; border: 1px solid #B9DDE1; border-radius: 7px; padding: 7px 10px; color: #173B45; }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QTextEdit:focus, QPlainTextEdit:focus { border-color: #13A7B5; background: #FCFFFF; }
        QTabWidget::pane { border: 1px solid #CBE8EB; border-radius: 7px; background: white; }
        QTabBar::tab { background: #F0F9FA; color: #6C8D95; border: 1px solid #D6EAEC; border-bottom: none; border-radius: 6px 6px 0 0; padding: 8px 18px; margin-right: 2px; font-weight: 700; }
        QTabBar::tab:selected { background: white; color: #087F8C; border-bottom: 2px solid #13A7B5; }
        QMenuBar { background: white; color: #3B5C64; border-bottom: 1px solid #D6EAEC; padding: 3px; }
        QMenuBar::item:selected { background: #E6F7F8; color: #087F8C; }
        QMenu { background: white; color: #173B45; border: 1px solid #B9DDE1; border-radius: 7px; padding: 4px; }
        QMenu::item { padding: 8px 24px; border-radius: 4px; }
        QMenu::item:selected { background: #D8F5F6; color: #075D67; font-weight: bold; }
        QToolTip { background: #075D67; color: white; border: 1px solid #13A7B5; border-radius: 5px; padding: 5px 8px; font-size: 11px; }
        """)

    # ═══════════════════════════════════════════════════════
    #  UI SETUP
    # ═══════════════════════════════════════════════════════

    def _setup_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        topbar = self._build_topbar()
        root_layout.addWidget(topbar)

        self._breadcrumb = BreadcrumbBar()
        root_layout.addWidget(self._breadcrumb)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._sidebar = CollapsibleSidebar()
        self._build_navigation()
        body.addWidget(self._sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("contentStack")
        body.addWidget(self.stack, 1)

        root_layout.addLayout(body, 1)
        self.setCentralWidget(root)

        # Loading placeholder
        self._loading_label = QLabel("Preparing execution modules…")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setStyleSheet(
            "color:#087F8C; font-size:14px; font-weight:700; "
            "background:#FFFFFF; padding:40px;"
        )
        self.stack.addWidget(self._loading_label)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._build_status_bar()

        # ── Sidebar toggle action (created ONCE, reused by View menu) ──
        self._sidebar_toggle_action = QAction("☰  Toggle Sidebar", self)
        self._sidebar_toggle_action.setShortcut(QKeySequence("Ctrl+B"))
        self._sidebar_toggle_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self._sidebar_toggle_action.triggered.connect(self._sidebar.toggle)
        self.addAction(self._sidebar_toggle_action)
        self._action_registry.register("toggle_sidebar", self._sidebar_toggle_action, "Ctrl+B")

    def _begin_tab_loading(self):
        if self._tabs_loading or self._tabs_loaded:
            return
        self._tabs_loading = True
        self._load_index = 0
        self._load_next_tab()

    def _load_next_tab(self):
        if self._load_index >= len(self.TAB_CLASSES):
            self._tabs_loading = False
            self._tabs_loaded = True
            if self._loading_label is not None:
                self._loading_label.deleteLater()
                self._loading_label = None

            self.lbl_tabs_count.setText(f"📦  {len(self.tabs)} modules")

            self.show_dashboard()
            self._notif_center.add_notification(
                "Workspace Ready",
                f"Signed in as {self.session_manager.username}. "
                f"All {len(self.tabs)} execution modules loaded.",
                "success"
            )
            self._notif_badge.set_count(self._notif_center.count)
            logger.info(
                "PipeAgent v%s ready (user=%s, modules=%d)",
                APP_VERSION, self.session_manager.username, len(self.tabs)
            )
            return

        key, cls = self.TAB_CLASSES[self._load_index]
        self._load_index += 1

        try:
            widget = cls(self.db, self.session_manager)
            self._configure_scrollable_controls(widget)
            self._standardize_table_columns(widget)
            page = self._wrap_tab_page(widget, key)
            self.stack.addWidget(page)
            self.tabs[key] = widget
            self._tab_pages[key] = page
            logger.debug("Loaded tab: %s", key)
        except Exception as e:
            logger.exception("Failed to load tab '%s'", key)
            placeholder = self._make_error_placeholder(key, str(e))
            page = self._wrap_tab_page(placeholder, key)
            self.stack.addWidget(page)
            self.tabs[key] = placeholder
            self._tab_pages[key] = page

        QTimer.singleShot(0, self._load_next_tab)

    def _configure_scrollable_controls(self, root: QWidget) -> None:
        for widget in root.findChildren(QAbstractScrollArea):
            if isinstance(widget, QScrollArea):
                widget.setWidgetResizable(True)
                widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                continue

            widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

            if isinstance(widget, (QTableWidget, QTableView)):
                header = widget.horizontalHeader()
                header.setMinimumSectionSize(90)
                header.setStretchLastSection(False)
                header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            elif isinstance(widget, QTreeWidget):
                header = widget.header()
                header.setMinimumSectionSize(90)
                header.setStretchLastSection(False)
                header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
                widget.setSizeAdjustPolicy(
                    QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
                )

    def _standardize_table_columns(self, root: QWidget) -> None:
        replacements = {
            "ID": "Record ID",
            "ID / UUID": "Record ID / UUID",
            "Piping Line No": "Line Number",
            "Line No": "Line Number",
            "Line / Target": "Line / Target",
            "Spool Identifier": "Spool Number",
            "Spool No": "Spool Number",
            "Weld ID": "Weld Joint ID",
            "Weld / Joint ID": "Weld Joint ID",
            "Welder Stamp": "Welder Stamp / ID",
            "Stencil / Stamp": "Welder Stamp / ID",
            "ISO DWG Ref": "ISO Drawing",
            "ISO Drawing": "ISO Drawing",
            "Detail DWG": "Detail Drawing",
            "Official Title": "Project Title",
            "Client / Owner": "Client / Owner",
            "Cat": "Category",
            "Qty Received": "Quantity Received",
            "Qty Available": "Quantity Available",
            "Qty Required": "Quantity Required",
            "Qty Issued": "Quantity Issued",
            "UOM": "Unit of Measure",
            "Spec / Grade": "Specification / Grade",
            "Size": "Nominal Size",
            "Status": "Lifecycle Status",
            "Remarks": "Remarks / Notes",
            "Details": "Details / Notes",
            "Description & Grade": "Description / Grade",
            "Description & Deficiency": "Description / Deficiency",
        }
        description_tokens = (
            "description", "details", "remarks", "notes", "finding",
            "scope", "deficiency", "action", "comment",
        )
        for table in root.findChildren(QTableWidget):
            header = table.horizontalHeader()
            labels = []
            for col in range(table.columnCount()):
                item = table.horizontalHeaderItem(col)
                labels.append(item.text().strip() if item else f"Column {col + 1}")
            labels = [replacements.get(label, label) for label in labels]
            has_description = any(
                any(token in label.lower() for token in description_tokens)
                for label in labels
            )
            object_name = (table.objectName() or "").lower()
            compact = object_name in {"preview", "summary", "metricstable"}

            allow_notes = table.property("allowAutoNotesColumn")
            if allow_notes is None:
                allow_notes = True

            if not has_description and not compact and allow_notes:
                table.setColumnCount(table.columnCount() + 1)
                labels.append("Description / Notes")
            table.setHorizontalHeaderLabels(labels)
            header.setMinimumSectionSize(90)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            table.setWordWrap(False)
            table.setTextElideMode(Qt.TextElideMode.ElideRight)

    def _wrap_tab_page(self, widget: QWidget, key: str) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName(f"moduleScroll_{key}")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(widget)
        return scroll

    def _make_error_placeholder(self, key: str, error: str) -> QWidget:
        w = QWidget()
        w.setObjectName("failedTabPlaceholder")
        w.setStyleSheet(
            "QWidget#failedTabPlaceholder { background: #F4FBFC; } QLabel { background: transparent; }"
        )
        l = QVBoxLayout(w)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("⚠️")
        icon.setStyleSheet("font-size:64px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel(f"Module '{escape(key)}' Failed to Load")
        title.setStyleSheet("color:#ff6b6b; font-size:18px; font-weight:800; padding:12px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        detail = QLabel(f"<pre>{escape(error)}</pre>")
        detail.setStyleSheet(
            "color:#7a9ab3; font-size:12px; padding:20px; background:#091726; "
            "border:1px solid #3a1a1a; border-radius:6px; margin:20px; font-family: Consolas, monospace;"
        )
        detail.setWordWrap(True)
        detail.setAlignment(Qt.AlignmentFlag.AlignCenter)

        l.addStretch()
        l.addWidget(icon)
        l.addWidget(title)
        l.addWidget(detail)
        l.addStretch()
        return w

    def _build_topbar(self) -> QFrame:
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(72)
        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        brand_box = QVBoxLayout()
        brand_box.setSpacing(0)
        brand = QLabel("PipeAgent")
        brand.setObjectName("brand")
        sub = QLabel("PIPING EXECUTION OPERATING SYSTEM  •  KNOW WHAT'S NEXT")
        sub.setObjectName("brandSub")
        brand_box.addWidget(brand)
        brand_box.addWidget(sub)
        layout.addLayout(brand_box)
        layout.addStretch()

        live = QLabel("● SYSTEM ONLINE")
        live.setObjectName("liveIndicator")
        layout.addWidget(live)

        support_btn = QPushButton("💬  Support")
        support_btn.setObjectName("supportAction")
        support_btn.setToolTip("Open PipeAgent Support in WhatsApp Web")
        support_btn.clicked.connect(self._open_whatsapp_support)
        layout.addWidget(support_btn)

        self._notif_btn = QPushButton("🔔")
        self._notif_btn.setObjectName("topAction")
        self._notif_btn.setFixedSize(42, 38)
        self._notif_btn.setToolTip("Notifications (Ctrl+N)")
        self._notif_btn.clicked.connect(self._toggle_notifications)
        layout.addWidget(self._notif_btn)

        self._notif_badge = NotificationBadge(self._notif_btn)
        self._notif_badge.move(24, -2)
        self._notif_center = NotificationCenter(self)
        self._notif_center.countChanged.connect(self._notif_badge.set_count)

        user = QLabel(f"👤  {self.session_manager.username}")
        user.setObjectName("userBadge")
        layout.addWidget(user)

        # ⚠ No shortcut set here: the File menu owns the F5 shortcut.
        refresh_btn = QPushButton("↻  Refresh")
        refresh_btn.setObjectName("topAction")
        refresh_btn.setToolTip("Refresh current module (F5)")
        refresh_btn.clicked.connect(self._refresh_current)
        layout.addWidget(refresh_btn)

        return topbar

    def _build_navigation(self):
        """
        Build the sidebar. Every nav button simply triggers the
        module QAction created in `_build_module_actions()`.
        No new QAction, no duplicate shortcuts.
        """
        self._key_to_group: dict[str, str] = {}
        self._key_to_text: dict[str, str] = {}

        for group_name, items in self.NAV_STRUCTURE:
            self._sidebar.add_group(group_name)
            for icon, text, key, shortcut in items:
                btn = self._sidebar.add_nav_button(key, icon, text, shortcut)
                # Reuse the SAME action - this avoids duplicate shortcuts
                btn.clicked.connect(self._module_actions[key].trigger)
                self._key_to_group[key] = group_name
                self._key_to_text[key] = text
            self._sidebar.add_separator()

        self._sidebar.finalize()

    def _create_menu_bar(self):
        """
        Build the menu bar. Module entries reuse the same QActions
        from `self._module_actions` — no shortcuts are re-registered.
        """
        mb = self.menuBar()

        # ── PipeAgent menu ────────────────────────────────
        pa_menu = mb.addMenu("&PipeAgent")
        pa_menu.addAction(self._module_actions["dashboard"])
        pa_menu.addSeparator()

        for group_name, items in self.NAV_STRUCTURE:
            sub = pa_menu.addMenu(f"  {group_name}")
            for icon, text, key, sc in items:
                sub.addAction(self._module_actions[key])

        # ── File menu ─────────────────────────────────────
        file_menu = mb.addMenu("&File")

        act = QAction("📁  Open Project Folder", self)
        act.triggered.connect(self._open_project_folder)
        file_menu.addAction(act)

        act = QAction("📥  Import Excel / Data", self)
        act.setShortcut("Ctrl+Alt+I")
        act.triggered.connect(self._open_data_exchange)
        file_menu.addAction(act)

        act = QAction("📤  Export Full Project Pack", self)
        act.setShortcut("Ctrl+Alt+E")
        act.triggered.connect(self._export_project_pack)
        file_menu.addAction(act)

        file_menu.addSeparator()

        # 🔧 Changed: Ctrl+Alt+B → Ctrl+Shift+B (was conflicting with As-Built)
        act = QAction("💾  Backup Database", self)
        act.setShortcut("Ctrl+Shift+B")
        act.triggered.connect(self._backup_database)
        file_menu.addAction(act)

        act = QAction("📂  Open Backup Folder", self)
        act.triggered.connect(self._open_backup_folder)
        file_menu.addAction(act)

        file_menu.addSeparator()

        act = QAction("🖨  Print Current View", self)
        act.setShortcut("Ctrl+P")
        act.triggered.connect(self._print_current_view)
        file_menu.addAction(act)

        # 🔧 F5 registered ONCE (here in the menu)
        act = QAction("🔄  Refresh", self)
        act.setShortcut("F5")
        act.triggered.connect(self._refresh_current)
        file_menu.addAction(act)

        file_menu.addSeparator()

        act = QAction("🚪  Logout", self)
        act.setShortcut("Ctrl+L")
        act.triggered.connect(self._logout)
        file_menu.addAction(act)

        act = QAction("❌  Exit", self)
        act.setShortcut("Ctrl+Q")
        act.triggered.connect(self.close)
        file_menu.addAction(act)

        # ── View menu ─────────────────────────────────────
        view_menu = mb.addMenu("&View")
        # 🔧 Reuse the sidebar toggle action created in _setup_ui()
        view_menu.addAction(self._sidebar_toggle_action)

        act = QAction("🔔  Toggle Notifications", self)
        act.setShortcut("Ctrl+N")
        act.triggered.connect(self._toggle_notifications)
        view_menu.addAction(act)

        # ── Help menu ─────────────────────────────────────
        help_menu = mb.addMenu("&Help")

        act = QAction("📘  User Guide — English", self)
        act.triggered.connect(lambda: self._open_user_guide("PipeAgent_User_Guide_EN.html"))
        help_menu.addAction(act)

        act = QAction("📗  راهنمای کاربر — فارسی", self)
        act.triggered.connect(lambda: self._open_user_guide("PipeAgent_User_Guide_FA.html"))
        help_menu.addAction(act)

        help_menu.addSeparator()

        act = QAction("ℹ️  About PipeAgent", self)
        act.triggered.connect(self._show_about)
        help_menu.addAction(act)

        act = QAction("📜  License Information", self)
        act.triggered.connect(self._show_license_info)
        help_menu.addAction(act)

        act = QAction("⌨️  Keyboard Shortcuts", self)
        act.setShortcut("F1")
        act.triggered.connect(self._show_shortcuts)
        help_menu.addAction(act)

        act = QAction("💬  WhatsApp Support", self)
        act.triggered.connect(self._open_whatsapp_support)
        help_menu.addAction(act)

    # ═══════════════════════════════════════════════════════
    #  ACTIONS
    # ═══════════════════════════════════════════════════════

    def switch_tab(self, key: str):
        if key not in self.tabs:
            if self._tabs_loading:
                self.statusBar().showMessage(
                    "Module is still loading — please wait a moment.", 2000
                )
            else:
                logger.warning("Tab '%s' not found", key)
            return

        self.stack.setCurrentWidget(self._tab_pages.get(key, self.tabs[key]))
        self._sidebar.set_active(key)
        self._current_key = key

        group = self._key_to_group.get(key, "")
        text = self._key_to_text.get(key, key)
        self._breadcrumb.set_path(group, text)
        self._current_group = group
        self._current_module = text
        self._update_status_bar()

        widget = self.tabs[key]
        if hasattr(widget, "refresh"):
            try:
                widget.refresh()
            except Exception as e:
                logger.debug("Auto-refresh skipped for %s: %s", key, e)

        self.statusBar().showMessage(f"PipeAgent › {text} — ready", 3000)

    def show_dashboard(self):
        self.switch_tab("dashboard")

    def _refresh_current(self):
        widget = self.tabs.get(self._current_key)
        if widget is None:
            self.statusBar().showMessage("No active module", 2500)
            return

        refreshed = False
        for method_name in ("refresh_stats", "refresh"):
            method = getattr(widget, method_name, None)
            if callable(method):
                try:
                    method()
                    refreshed = True
                    break
                except Exception:
                    logger.exception(
                        "Failed to refresh module '%s' using %s",
                        self._current_key, method_name,
                    )

        self.statusBar().showMessage(
            "✓  Workspace refreshed" if refreshed else "Nothing to refresh",
            2500
        )

    def _open_project_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(PROJECT_ROOT)))

    def _open_backup_folder(self):
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(BACKUP_DIR)))

    def _open_data_exchange(self):
        self.switch_tab("data_exchange")
        self.statusBar().showMessage(
            "Data Exchange Center opened — choose a data type and select an Excel file.", 4000
        )

    def _export_project_pack(self):
        self.switch_tab("data_exchange")
        exchange = self.tabs.get("data_exchange")
        if exchange and hasattr(exchange, "export_pack"):
            exchange.export_pack()

    def _backup_database(self):
        try:
            target = BackupService.backup_database(DATABASE_PATH, BACKUP_DIR)
            QMessageBox.information(
                self, "Database Backup",
                f"Database backup created successfully.\n\n{target}",
            )
        except FileNotFoundError as e:
            QMessageBox.warning(self, "Database Backup", str(e))
        except Exception as exc:
            logger.exception("Database backup failed")
            QMessageBox.critical(self, "Database Backup Failed", str(exc))

    def _open_user_guide(self, filename: str):
        path = PROJECT_ROOT / filename
        if not path.exists():
            QMessageBox.warning(
                self, "User Guide",
                f"The user guide was not found in the PipeAgent project root:\n{path}",
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.information(
                self, "User Guide",
                f"Please open this file manually:\n{path}",
            )

    def _print_current_view(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return

        widget = self.tabs.get(self._current_key)
        if widget is None:
            self.statusBar().showMessage("No active module to print", 2500)
            return

        try:
            painter = QPainter()
            if not painter.begin(printer):
                raise RuntimeError("Unable to initialize printer painter")

            target = widget.viewport() if hasattr(widget, "viewport") else widget
            pixmap = target.grab()
            rect = painter.viewport()
            scaled = pixmap.scaled(
                rect.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            x = rect.x() + (rect.width() - scaled.width()) // 2
            y = rect.y() + (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.end()
            self.statusBar().showMessage("Current view sent to printer.", 3000)
        except Exception as exc:
            logger.exception("Print current view failed")
            QMessageBox.critical(self, "Print Failed", str(exc))

    def _toggle_notifications(self):
        if self._notif_center.isVisible():
            self._notif_center.hide()
        else:
            if self._notif_btn:
                btn_global = self._notif_btn.mapToGlobal(
                    QPoint(0, self._notif_btn.height())
                )
                x = btn_global.x() - self._notif_center.width() + self._notif_btn.width()
                self._notif_center.move(x, btn_global.y() + 4)
            self._notif_center.show()

    def notify(self, title: str, message: str, level: str = "info"):
        self._notif_center.add_notification(title, message, level)

    def _build_status_bar(self):
        self.lbl_license = QLabel()
        self.lbl_license.setObjectName("status_label")
        self.lbl_db = QLabel()
        self.lbl_db.setObjectName("status_label")
        self.lbl_time = QLabel()
        self.lbl_time.setObjectName("status_label")
        self.lbl_user = QLabel(f"👤  {self.session_manager.username}")
        self.lbl_user.setObjectName("status_label")
        self.lbl_module = QLabel()
        self.lbl_module.setObjectName("status_label")
        self.lbl_tabs_count = QLabel(f"📦  {self._total_modules} modules")
        self.lbl_tabs_count.setObjectName("status_label")

        self.status_bar.addWidget(self.lbl_license)
        self.status_bar.addWidget(self.lbl_module)
        self.status_bar.addPermanentWidget(self.lbl_tabs_count)
        self.status_bar.addPermanentWidget(self.lbl_user)
        self.status_bar.addPermanentWidget(self.lbl_db)
        self.status_bar.addPermanentWidget(self.lbl_time)

    def _update_status_bar(self):
        try:
            self.lbl_license.setText(f"📜  {format_license_status(self.db)}")
        except Exception:
            self.lbl_license.setText("📜  License: N/A")

        db_url = getattr(self.db, 'database_url', 'unknown')
        db_name = db_url.split("/")[-1] if "/" in db_url else db_url
        self.lbl_db.setText(f"🗄️  {db_name}")
        self.lbl_time.setText(f"🕒  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        self.lbl_module.setText(
            f"📍  PipeAgent › {self._current_group} › {self._current_module}"
        )

    def _open_whatsapp_support(self):
        phone = "989160684552"
        text = "Hello PipeAgent Support, I need assistance with PipeAgent."
        query = urlencode({"text": text})
        url = f"https://wa.me/{phone}?{query}"
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.information(
                self,
                "WhatsApp Support",
                "Please open WhatsApp Web and start a chat with +98 916 068 4552.",
            )

    def _logout(self):
        reply = QMessageBox.question(
            self,
            "Logout",
            "Are you sure you want to logout?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._force_close = True
            self.session_manager.end_session()
            self.close()

    def _show_about(self):
        QMessageBox.about(
            self,
            "About PipeAgent",
            f"<h2>PipeAgent <span style='color:#6ccff6;'>v{APP_VERSION}</span></h2>"
            f"<p><b>Piping Execution Operating System</b></p>"
            f"<p style='color:#5cffaa;'><b>✓ 100% Piping Site Coverage — {len(self.tabs)} Integrated Modules</b></p>"
            f"<hr>"
            f"<p>Full-lifecycle piping construction management:</p>"
            f"<ul>"
            f"<li>Engineering, Documents & Line Lists</li>"
            f"<li>Material Tracking, MTO & Procurement</li>"
            f"<li>Fabrication, Spooling & Welding QC</li>"
            f"<li>NDT, QA/QC, Punch Lists & NCR</li>"
            f"<li>Hydro-Test, Pre-Commissioning & Finishing</li>"
            f"<li>Valve Testing, Flange Torquing & PWHT</li>"
            f"<li>Work Front Control & Resource Dispatch</li>"
            f"<li>AI Insights, Execution Intelligence & Digital Turnover</li>"
            f"</ul>"
            f"<p>Organization: <b>{ORG_NAME}</b></p>"
            f"<p style='color:#7a9ab3;'>Built with PyQt6 + SQLAlchemy</p>"
        )

    def _show_license_info(self):
        try:
            info = get_license_info(self.db)
            days_left = info.get('remaining_days', 0)
            status = "Active ✅" if days_left > 0 else "Expired ❌"
            QMessageBox.information(
                self,
                "PipeAgent License Information",
                f"Type: {info.get('type', 'N/A')}\n"
                f"Days Remaining: {days_left}\n"
                f"Records Used: {info.get('records_used', 0)} / {info.get('max_records', 'N/A')}\n"
                f"Status: {status}"
            )
        except Exception as e:
            logger.exception("License info retrieval failed")
            QMessageBox.warning(self, "License Info", f"Unable to retrieve license: {e}")

    def _show_shortcuts(self):
        shortcuts = [
            ("F5", "Refresh current module"),
            ("F1", "This help dialog"),
            ("Ctrl+B", "Toggle Sidebar"),
            ("Ctrl+N", "Toggle Notifications"),
            ("Ctrl+D", "Dashboard"),
            ("Ctrl+E", "Data Exchange"),
            ("Ctrl+K", "Quick Entry / Smart Forms"),
            ("Ctrl+M", "Mobile Field Hub"),
            ("Ctrl+R", "Reports & Analytics"),
            ("Ctrl+T", "Control Tower"),
            ("Ctrl+W", "Work Front & Resources"),
            ("Ctrl+I", "Execution Intelligence"),
            ("Ctrl+Shift+I", "Execution OS"),
            ("Ctrl+L", "Logout"),
            ("Ctrl+Q", "Exit Application"),
        ]
        text = (
            "<h3>⌨️ PipeAgent Keyboard Shortcuts</h3>"
            "<table cellpadding='4' cellspacing='0'>"
            "<tr style='background:#091726;'>"
            "<th style='padding:6px 12px; color:#9fe7ff;'>Shortcut</th>"
            "<th style='padding:6px 12px; color:#9fe7ff;'>Action</th></tr>"
        )
        for sc, desc in shortcuts:
            text += (
                f"<tr>"
                f"<td style='padding:6px 12px; border-bottom:1px solid #142e47;'><b><code>{sc}</code></b></td>"
                f"<td style='padding:6px 12px; border-bottom:1px solid #142e47; color:#7a9ab3;'>{desc}</td>"
                f"</tr>"
            )
        text += "</table>"
        QMessageBox.information(self, "PipeAgent Keyboard Shortcuts", text)

    def closeEvent(self, event):
        if self._force_close:
            self._status_timer.stop()
            self._clock_timer.stop()
            event.accept()
            logger.info("PipeAgent closed after logout (%s)", self.session_manager.username)
            return

        reply = QMessageBox.question(
            self,
            "Exit PipeAgent",
            "Are you sure you want to exit PipeAgent?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._status_timer.stop()
            self._clock_timer.stop()
            event.accept()
            logger.info("PipeAgent closed by user (%s)", self.session_manager.username)
        else:
            event.ignore()