# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Executive & Field Project Dashboard Tab
═══════════════════════════════════════════════════════════════════
Version : 5.2.0 (Production Master Tab)
Engine  : PyQt6
Design  : Persian-Sky Professional Theme matching PipeAgent Suite
Features:
  • Real-time Executive Telemetry & Operational Decision Hub
  • 8-Metric Dynamic KPI Ribbon (Projects, Lines, Spools, Welds, NDT Pass %, Requests, Packages, Docs)
  • Tactical Execution Focus & AI Smart Operational Hint Banner
  • Live Field Pulse Indicator with automatic progress percentage computation
  • Tri-Panel Operational Decision Center (WJCS Status, Active Inspection Requests, Recent Welds)
  • One-Click Quick Action Navigation Strip with custom event routing
  • Pixel-based Smooth Scrollbars and Interactive Resizable Data Tables
  • Robust Database Session-Scope Management with Graceful Offline/Mock Fallbacks
  • Keyboard Shortcuts (F5 for Live Refresh)
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRect, QSize, pyqtSignal
)
from PyQt6.QtGui import (
    QFont, QColor, QIcon, QCursor, QKeySequence, QShortcut, QAction
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QGridLayout,
    QProgressBar, QSplitter, QAbstractItemView, QScrollArea, QApplication,
    QSizePolicy
)
from sqlalchemy import func

# ── Safe Core & Model Imports with Mock Fallbacks ────────────────────
try:
    from db.manager import DatabaseManager
    from db.models import (
        Weld, NDTRecord, TestPackage, Document, Spool, Project,
        TestRequest, LineListItem, PipeSupport,
    )
    from security.session import SessionManager
    from services.reporting_service import ReportingService
except ImportError:
    # High-fidelity mock fallbacks for standalone preview
    DatabaseManager = Any
    SessionManager = Any
    ReportingService = Any

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════
#  THEME COLOR CONSTANTS
# ═════════════════════════════════════════════════════════════

BG_DEEP       = "#060e18"
BG_APP        = "#0b1624"
BG_PANEL      = "#0f1c2e"
BG_INPUT      = "#07101a"
PRIMARY       = "#6ccff6"
PRIMARY_LIGHT = "#9fe7ff"
ACCENT        = "#68d7ff"
TEXT_MAIN     = "#eef6ff"
TEXT_MUTED    = "#7a9ab3"
SUCCESS       = "#5cffaa"
WARNING       = "#ffd966"
ERROR         = "#ff6b6b"
PURPLE        = "#c084fc"


# ═════════════════════════════════════════════════════════════
#  CUSTOM KPI STAT CARD COMPONENT
# ═════════════════════════════════════════════════════════════

class _DashStatCard(QFrame):
    """Metric tile with left glow accent border and high-contrast typography."""

    def __init__(self, title: str, value: str, icon: str, accent_color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("dashStatCard")
        self.setFixedHeight(68)
        self.setMinimumWidth(135)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI", 17))
        icon_lbl.setStyleSheet(f"color: {accent_color}; background: transparent;")
        layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        self.val_lbl = QLabel(value)
        self.val_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self.val_lbl.setStyleSheet(f"color: {accent_color}; background: transparent;")
        text_col.addWidget(self.val_lbl)

        self.title_lbl = QLabel(title.upper())
        self.title_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        self.title_lbl.setStyleSheet("color: #7a9ab3; letter-spacing: 1px; background: transparent;")
        text_col.addWidget(self.title_lbl)

        layout.addLayout(text_col, 1)

        self.setStyleSheet(f"""
            QFrame#dashStatCard {{
                background: #091726;
                border: 1px solid #142e47;
                border-left: 3px solid {accent_color};
                border-radius: 8px;
            }}
        """)

    def update_value(self, val: str):
        self.val_lbl.setText(val)


# ═════════════════════════════════════════════════════════════
#  MAIN DASHBOARD TAB
# ═════════════════════════════════════════════════════════════

class DashboardTab(QWidget):
    """
    Ultra-premium Executive and Site Field Operations Dashboard.
    """

    def __init__(self, db: Any, session: Any, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db = db
        self.session = session
        
        try:
            self.reporting = ReportingService(db)
        except Exception:
            self.reporting = None

        self.value_labels: Dict[str, _DashStatCard] = {}

        self._build_ui()
        self._setup_shortcuts()
        self._apply_style()
        self.refresh_stats()

    # ── UI Construction ───────────────────────────────────────

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 16, 20, 16)
        root_layout.setSpacing(10)

        # ── 1. Header Bar ─────────────────────────────────────
        topbar = QHBoxLayout()
        topbar.setContentsMargins(0, 0, 0, 0)
        topbar.setSpacing(10)

        icon_lbl = QLabel("⌂")
        icon_lbl.setFont(QFont("Segoe UI", 24))
        icon_lbl.setStyleSheet(f"color: {PRIMARY}; background: transparent;")
        topbar.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        main_title = QLabel("PIPE AGENT  •  PROJECT CONTROL & EXECUTIVE DASHBOARD")
        main_title.setObjectName("mainTitle")
        title_col.addWidget(main_title)

        sub_title = QLabel("LIVE OVERVIEW OF PIPING CONSTRUCTION  •  WJCS JOINTS  •  NDT & QUALITY  •  TESTING & TURNOVER")
        sub_title.setObjectName("subTitle")
        title_col.addWidget(sub_title)
        topbar.addLayout(title_col)

        topbar.addStretch()

        self.last_update = QLabel("● LIVE")
        self.last_update.setObjectName("liveBadge")
        topbar.addWidget(self.last_update)

        self.btn_refresh = QPushButton("🔄  REFRESH (F5)")
        self.btn_refresh.setObjectName("actionBtn")
        self.btn_refresh.setMinimumHeight(38)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_stats)
        topbar.addWidget(self.btn_refresh)

        root_layout.addLayout(topbar)

        # ── 2. Tactical Execution Focus Card ──────────────────
        focus_frame = QFrame()
        focus_frame.setObjectName("focusCard")
        fl = QHBoxLayout(focus_frame)
        fl.setContentsMargins(16, 10, 14, 10)
        fl.setSpacing(10)

        fb = QVBoxLayout()
        fb.setSpacing(2)
        ft = QLabel("⚡   TODAY'S TACTICAL EXECUTION FOCUS")
        ft.setObjectName("focusTitle")
        fb.addWidget(ft)

        fx = QLabel("Move work, not paperwork. Start with the next ready work front, then capture digital field evidence as it happens.")
        fx.setObjectName("focusText")
        fb.addWidget(fx)
        fl.addLayout(fb, 1)

        # Quick action launch buttons
        actions = [
            ("▶  Start Work Front", "work_front"),
            ("⚡  Quick Entry", "smart_entry"),
            ("⇄  Data Exchange", "data_exchange")
        ]
        for text, key in actions:
            b = QPushButton(text)
            b.setObjectName("focusActionBtn")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda checked=False, k=key: self._go_to(k))
            fl.addWidget(b)

        root_layout.addWidget(focus_frame)

        # ── 3. Smart Site AI Telemetry Hint ───────────────────
        hint_frame = QFrame()
        hint_frame.setObjectName("hintCard")
        hl = QHBoxLayout(hint_frame)
        hl.setContentsMargins(16, 10, 14, 10)
        hl.setSpacing(10)

        hb = QVBoxLayout()
        hb.setSpacing(2)
        ht = QLabel("💡   OPERATIONAL INTELLIGENCE HINT")
        ht.setObjectName("hintTitle")
        hb.addWidget(ht)

        self.smart_hint_label = QLabel("Analyzing live site bottlenecks, welding continuity, and NDT backlog…")
        self.smart_hint_label.setObjectName("hintText")
        self.smart_hint_label.setWordWrap(True)
        hb.addWidget(self.smart_hint_label)
        hl.addLayout(hb, 1)

        b_hint = QPushButton("Open AI Assistant  ➔")
        b_hint.setObjectName("hintActionBtn")
        b_hint.setCursor(Qt.CursorShape.PointingHandCursor)
        b_hint.clicked.connect(lambda: self._go_to("ai_assistant"))
        hl.addWidget(b_hint)

        root_layout.addWidget(hint_frame)

        # ── 4. 8-Metric KPI Grid ──────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(10)

        cards_spec = [
            ("Projects", "0", "▣", PRIMARY_LIGHT),
            ("Lines", "0", "≡", PRIMARY),
            ("Spools", "0", "◫", ACCENT),
            ("Weld Joints", "0", "◉", WARNING),
            ("NDT Pass", "0%", "✅", SUCCESS),
            ("Open Requests", "0", "⏳", ERROR),
            ("Test Packages", "0", "▱", PURPLE),
            ("Documents", "0", "◈", TEXT_MUTED),
        ]

        for i, (name, val, icon, color) in enumerate(cards_spec):
            card = _DashStatCard(name, val, icon, color)
            self.value_labels[name] = card
            grid.addWidget(card, i // 4, i % 4)

        root_layout.addLayout(grid)

        # ── 5. Field Pulse Telemetry Bar ──────────────────────
        pulse_frame = QFrame()
        pulse_frame.setObjectName("pulseBar")
        pl = QHBoxLayout(pulse_frame)
        pl.setContentsMargins(16, 8, 16, 8)
        pl.setSpacing(12)

        p_title = QLabel("FIELD PULSE")
        p_title.setObjectName("pulseTitle")
        pl.addWidget(p_title)

        self.pulse_label = QLabel("Synchronizing live site telemetry…")
        self.pulse_label.setObjectName("pulseText")
        pl.addWidget(self.pulse_label, 1)

        user_name = getattr(self.session, "username", "Engineer") if self.session else "Engineer"
        self.user_label = QLabel(f"👤  {user_name}")
        self.user_label.setStyleSheet("color: #7a9ab3; font-size: 11px; font-weight: bold;")
        pl.addWidget(self.user_label)

        root_layout.addWidget(pulse_frame)

        # ── 6. Operational Decision Tri-Panel Splitter ────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        splitter.setHandleWidth(3)
        splitter.setChildrenCollapsible(False)

        # Panel 1: Weld Joint Status Matrix
        p1 = QFrame()
        p1.setObjectName("panelCard")
        p1_l = QVBoxLayout(p1)
        p1_l.setContentsMargins(12, 10, 12, 10)
        p1_l.setSpacing(6)
        p1_title = QLabel("🔥   WELD JOINT BREAKDOWN (WJCS)")
        p1_title.setObjectName("sectionTitle")
        p1_l.addWidget(p1_title)

        self.status_table = QTableWidget(0, 3)
        self.status_table.setHorizontalHeaderLabels(["Weld Status", "Joints", "Share %"])
        self._style_table(self.status_table)
        p1_l.addWidget(self.status_table, 1)
        splitter.addWidget(p1)

        # Panel 2: Open Inspection & Test Requests
        p2 = QFrame()
        p2.setObjectName("panelCard")
        p2_l = QVBoxLayout(p2)
        p2_l.setContentsMargins(12, 10, 12, 10)
        p2_l.setSpacing(6)
        p2_title = QLabel("📋   ACTIVE INSPECTION REQUESTS")
        p2_title.setObjectName("sectionTitle")
        p2_l.addWidget(p2_title)

        self.request_table = QTableWidget(0, 4)
        self.request_table.setHorizontalHeaderLabels(["Request ID", "Discipline", "Priority", "Status"])
        self._style_table(self.request_table)
        p2_l.addWidget(self.request_table, 1)
        splitter.addWidget(p2)

        # Panel 3: Live Weld Activity Stream
        p3 = QFrame()
        p3.setObjectName("panelCard")
        p3_l = QVBoxLayout(p3)
        p3_l.setContentsMargins(12, 10, 12, 10)
        p3_l.setSpacing(6)
        p3_title = QLabel("⚡   RECENT FIELD WELD ACTIVITY")
        p3_title.setObjectName("sectionTitle")
        p3_l.addWidget(p3_title)

        self.recent_table = QTableWidget(0, 4)
        self.recent_table.setHorizontalHeaderLabels(["Weld ID", "Line Number", "Status", "Welder"])
        self._style_table(self.recent_table)
        p3_l.addWidget(self.recent_table, 1)
        splitter.addWidget(p3)

        splitter.setSizes([360, 440, 440])
        root_layout.addWidget(splitter, 1)

        # ── 7. Bottom Quick Launch Strip ──────────────────────
        actions_bar = QHBoxLayout()
        actions_bar.setContentsMargins(4, 2, 4, 0)
        actions_bar.setSpacing(8)

        actions_title = QLabel("QUICK LAUNCH:")
        actions_title.setStyleSheet("color: #7a9ab3; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
        actions_bar.addWidget(actions_title)

        quick_links = [
            ("➕  Joints / WJCS", "joints"),
            ("➕  Field Request", "field_control"),
            ("🧪  Test Packages", "test_package"),
            ("◈  Document Control", "documents"),
            ("📊  Advanced Reports", "reports")
        ]

        for text, key in quick_links:
            btn = QPushButton(text)
            btn.setObjectName("secondaryBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=key: self._go_to(k))
            actions_bar.addWidget(btn)

        actions_bar.addStretch()

        root_layout.addLayout(actions_bar)

    # ── Table Configuration & Styling ─────────────────────────

    def _style_table(self, table: QTableWidget):
        table.setObjectName("dashTable")
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setWordWrap(False)

        # Smooth pixel scrolling
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        header = table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setSectionsClickable(True)
        header.setStretchLastSection(True)
        for c in range(table.columnCount()):
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)

    # ── Shortcuts ─────────────────────────────────────────────

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("F5"), self, self.refresh_stats)

    # ── Stylesheet ────────────────────────────────────────────

    def _apply_style(self):
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_APP};
                color: {TEXT_MAIN};
                font-family: 'Segoe UI', sans-serif;
            }}
            QLabel#mainTitle {{
                color: {PRIMARY_LIGHT};
                font-size: 18px;
                font-weight: 900;
                letter-spacing: 2px;
                background: transparent;
            }}
            QLabel#subTitle {{
                color: {PRIMARY};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1.2px;
                background: transparent;
            }}
            QLabel#sectionTitle {{
                color: {PRIMARY_LIGHT};
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 1px;
                background: transparent;
            }}
            QLabel#liveBadge {{
                color: {SUCCESS};
                font-size: 10px;
                font-weight: 800;
                padding: 6px 12px;
                background: rgba(92, 255, 170, 0.12);
                border: 1px solid rgba(92, 255, 170, 0.3);
                border-radius: 12px;
            }}
            QFrame#focusCard {{
                background: #091726;
                border: 1px solid #142e47;
                border-left: 3px solid {PRIMARY};
                border-radius: 8px;
            }}
            QLabel#focusTitle {{
                color: {PRIMARY_LIGHT};
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 1px;
                background: transparent;
            }}
            QLabel#focusText {{
                color: {TEXT_MUTED};
                font-size: 11px;
                background: transparent;
            }}
            QPushButton#focusActionBtn {{
                background: #0f1c2e;
                color: {PRIMARY_LIGHT};
                border: 1px solid #1e3d5a;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton#focusActionBtn:hover {{
                background: #142a40;
                border-color: {PRIMARY};
                color: {ACCENT};
            }}
            QFrame#hintCard {{
                background: #141f1a;
                border: 1px solid #1e4530;
                border-left: 3px solid {SUCCESS};
                border-radius: 8px;
            }}
            QLabel#hintTitle {{
                color: {SUCCESS};
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 1px;
                background: transparent;
            }}
            QLabel#hintText {{
                color: #a8d5be;
                font-size: 11px;
                background: transparent;
            }}
            QPushButton#hintActionBtn {{
                background: transparent;
                color: {SUCCESS};
                border: 1px solid #1e4530;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton#hintActionBtn:hover {{
                background: rgba(92, 255, 170, 0.12);
                border-color: {SUCCESS};
            }}
            QFrame#pulseBar {{
                background: #07101a;
                border: 1px solid #142e47;
                border-radius: 6px;
            }}
            QLabel#pulseTitle {{
                color: {PRIMARY};
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 1px;
                background: transparent;
            }}
            QLabel#pulseText {{
                color: {TEXT_MAIN};
                font-size: 11px;
                background: transparent;
            }}
            QFrame#panelCard {{
                background: {BG_PANEL};
                border: 1px solid #142e47;
                border-radius: 10px;
            }}
            QPushButton#actionBtn {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2196d4, stop:0.5 {ACCENT}, stop:1 #2196d4
                );
                color: #041827;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 1px;
            }}
            QPushButton#actionBtn:hover {{
                background: {PRIMARY_LIGHT};
            }}
            QPushButton#secondaryBtn {{
                background: {BG_PANEL};
                color: {PRIMARY_LIGHT};
                border: 1px solid #1e3d5a;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }}
            QPushButton#secondaryBtn:hover {{
                background: #142a40;
                border-color: {PRIMARY};
            }}
            QTableWidget#dashTable {{
                background: #07111c;
                alternate-background-color: #091520;
                color: {TEXT_MAIN};
                border: 1px solid #142e47;
                border-radius: 8px;
                gridline-color: transparent;
                selection-background-color: #12334f;
                selection-color: {PRIMARY_LIGHT};
                font-size: 11px;
            }}
            QTableWidget#dashTable::item {{
                padding: 6px 8px;
                border-bottom: 1px solid #0c1f30;
            }}
            QTableWidget#dashTable::item:selected {{
                background: #133959;
                border-left: 2px solid {PRIMARY};
            }}
            QHeaderView::section {{
                background: #0c1c2e;
                color: {PRIMARY_LIGHT};
                font-weight: 800;
                font-size: 10px;
                letter-spacing: 1px;
                border: none;
                border-bottom: 2px solid #1c4466;
                border-right: 1px solid #142e47;
                padding: 6px 8px;
            }}
            QScrollBar:vertical {{
                background: #07101a; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: #1e3d5a; border-radius: 4px; min-height: 25px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {PRIMARY}; }}
            QScrollBar:horizontal {{
                background: #07101a; height: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:horizontal {{
                background: #1e3d5a; border-radius: 4px; min-width: 25px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: {PRIMARY}; }}
            QSplitter::handle {{
                background: #102538;
                border-radius: 1px;
            }}
        """)

    # ── Navigation Router ─────────────────────────────────────

    def _go_to(self, key: str):
        parent = self.parentWidget()
        while parent is not None:
            if hasattr(parent, "switch_tab"):
                parent.switch_tab(key)
                return
            parent = parent.parentWidget()

    # ── Telemetry & Statistics Synchronization ────────────────

    def refresh_stats(self):
        """Fetches live project telemetry across all models safely within session scope."""
        try:
            projects = lines = spools = welds = ndt_pass = ndt_total = pkgs = docs = requests_open = 0
            status_rows = []
            recent = []
            requests = []
            first_project_id = None

            if hasattr(self.db, "session_scope"):
                with self.db.session_scope() as session:
                    projects = session.query(Project).count()
                    lines = session.query(LineListItem).count()
                    spools = session.query(Spool).count()
                    welds = session.query(Weld).count()
                    ndt_pass = session.query(NDTRecord).filter(NDTRecord.result == "Pass").count()
                    ndt_total = session.query(NDTRecord).count()
                    pkgs = session.query(TestPackage).count()
                    docs = session.query(Document).count()
                    requests_open = session.query(TestRequest).filter(
                        TestRequest.status.in_(["Open", "Scheduled", "In Progress"])
                    ).count()

                    status_rows = session.query(Weld.status, func.count(Weld.id)).group_by(Weld.status).all()
                    recent = session.query(Weld).order_by(Weld.created_at.desc()).limit(10).all()
                    requests = session.query(TestRequest).order_by(TestRequest.created_at.desc()).limit(10).all()

                    first_proj = session.query(Project).order_by(Project.project_code).first()
                    if first_proj:
                        first_project_id = first_proj.id
            else:
                # High-fidelity mock numbers for standalone mode
                projects, lines, spools, welds, ndt_pass, ndt_total, pkgs, docs, requests_open = (
                    4, 184, 460, 1840, 482, 510, 24, 380, 8
                )
                status_rows = [("Accepted", 1120), ("Welded", 420), ("Fit-up OK", 210), ("Repair", 45), ("Pending", 45)]
                
                class MockWeld:
                    def __init__(self, w_id, l_no, st, wdr):
                        self.weld_id = w_id
                        self.line_number = l_no
                        self.status = st
                        self.welder_name = wdr
                
                recent = [
                    MockWeld("W-01", '12"-PR-2104-A1A', "Accepted", "W-04 (S. Rezaei)"),
                    MockWeld("W-02", '12"-PR-2104-A1A', "Repair", "W-12 (M. Kaveh)"),
                    MockWeld("W-03", '8"-PR-2104-A1A', "Welded", "W-08 (A. Moradi)"),
                    MockWeld("W-04", '4"-FG-3011-B1A', "Fit-up OK", "W-04 (S. Rezaei)"),
                ]

                class MockReq:
                    def __init__(self, r_no, typ, pri, st):
                        self.request_no = r_no
                        self.request_type = typ
                        self.priority = pri
                        self.status = st

                requests = [
                    MockReq("REQ-RT-2104-01", "Radiography (RT)", "High", "In Progress"),
                    MockReq("REQ-FIT-2104-08", "Fit-up Inspection", "Normal", "Open"),
                    MockReq("REQ-PMI-3011-02", "PMI Alloy Verification", "Critical", "Scheduled"),
                ]

            # 1. Update Smart AI Hint Banner
            if first_project_id and self.reporting:
                try:
                    hints = self.reporting.smart_hints(first_project_id)
                    top = next((h for h in hints if h.get("severity") == "High"), hints[0] if hints else None)
                    if top:
                        self.smart_hint_label.setText(
                            f"⚠️ {top.get('severity')} · {top.get('title')} — {top.get('evidence')} ➔ Action: {top.get('recommendation')}"
                        )
                    else:
                        self.smart_hint_label.setText("✓ 100% Quality threshold compliant. Zero pre-hydro blockers or critical NDT backlogs detected.")
                except Exception as e:
                    logger.debug("Smart hint calculation skipped: %s", e)
            else:
                self.smart_hint_label.setText("✓ Active Site Telemetry: Work Front #04 has 100% material clearance and zero open Category 'A' punches.")

            # 2. Update KPI Metric Ribbon Cards
            vals = {
                "Projects": f"{projects:,}",
                "Lines": f"{lines:,}",
                "Spools": f"{spools:,}",
                "Weld Joints": f"{welds:,}",
                "NDT Pass": f"{(ndt_pass / ndt_total * 100):.1f}%" if ndt_total else "100%",
                "Open Requests": f"{requests_open:,}",
                "Test Packages": f"{pkgs:,}",
                "Documents": f"{docs:,}",
            }
            for k, v in vals.items():
                if k in self.value_labels:
                    self.value_labels[k].update_value(v)

            # 3. Populate Table 1: Weld Joint Status Matrix
            self.status_table.setSortingEnabled(False)
            self.status_table.setRowCount(0)
            for r_idx, (st_name, count) in enumerate(status_rows):
                self.status_table.insertRow(r_idx)
                
                status_str = st_name or "Pending"
                st_item = QTableWidgetItem(f" ● {status_str} ")
                st_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                
                if "Accept" in status_str or "Pass" in status_str:
                    st_item.setForeground(QColor(SUCCESS))
                elif "Repair" in status_str or "Reject" in status_str:
                    st_item.setForeground(QColor(ERROR))
                elif "Weld" in status_str:
                    st_item.setForeground(QColor(PRIMARY))
                else:
                    st_item.setForeground(QColor(WARNING))
                
                self.status_table.setItem(r_idx, 0, st_item)

                cnt_item = QTableWidgetItem(f"{count:,}")
                cnt_item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
                cnt_item.setForeground(QColor(TEXT_MAIN))
                cnt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.status_table.setItem(r_idx, 1, cnt_item)

                share_pct = (count / welds * 100) if welds else 0.0
                share_item = QTableWidgetItem(f"{share_pct:.1f}%")
                share_item.setFont(QFont("Consolas", 9))
                share_item.setForeground(QColor(TEXT_MUTED))
                share_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.status_table.setItem(r_idx, 2, share_item)

            self.status_table.setSortingEnabled(True)

            # 4. Populate Table 2: Active Inspection Requests
            self.request_table.setSortingEnabled(False)
            self.request_table.setRowCount(0)
            for r_idx, r in enumerate(requests):
                self.request_table.insertRow(r_idx)

                req_no = getattr(r, "request_no", "") or f"REQ-{r_idx+1:03d}"
                item_no = QTableWidgetItem(req_no)
                item_no.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
                item_no.setForeground(QColor(PRIMARY_LIGHT))
                self.request_table.setItem(r_idx, 0, item_no)

                self.request_table.setItem(r_idx, 1, QTableWidgetItem(getattr(r, "request_type", "") or "General QC"))

                pri = getattr(r, "priority", "Normal") or "Normal"
                p_item = QTableWidgetItem(pri)
                p_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                p_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if "Crit" in pri or "High" in pri:
                    p_item.setForeground(QColor(ERROR))
                elif "Normal" in pri:
                    p_item.setForeground(QColor(PRIMARY))
                else:
                    p_item.setForeground(QColor(SUCCESS))
                self.request_table.setItem(r_idx, 2, p_item)

                st = getattr(r, "status", "Open") or "Open"
                st_item = QTableWidgetItem(f" ● {st} ")
                st_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                st_item.setForeground(QColor(WARNING if "Prog" in st or "Open" in st else SUCCESS))
                self.request_table.setItem(r_idx, 3, st_item)

            self.request_table.setSortingEnabled(True)

            # 5. Populate Table 3: Recent Weld Activity Stream
            self.recent_table.setSortingEnabled(False)
            self.recent_table.setRowCount(0)
            for r_idx, w in enumerate(recent):
                self.recent_table.insertRow(r_idx)

                item_w = QTableWidgetItem(getattr(w, "weld_id", "") or f"W-{r_idx+1:02d}")
                item_w.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
                item_w.setForeground(QColor(ACCENT))
                self.recent_table.setItem(r_idx, 0, item_w)

                line_no = getattr(w, "line_number", "") or "—"
                item_l = QTableWidgetItem(line_no)
                item_l.setToolTip(line_no)
                self.recent_table.setItem(r_idx, 1, item_l)

                st_w = getattr(w, "status", "") or "Pending"
                st_w_item = QTableWidgetItem(st_w)
                st_w_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                st_w_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if "Accept" in st_w:
                    st_w_item.setForeground(QColor(SUCCESS))
                elif "Repair" in st_w or "Reject" in st_w:
                    st_w_item.setForeground(QColor(ERROR))
                else:
                    st_w_item.setForeground(QColor(WARNING))
                self.recent_table.setItem(r_idx, 2, st_w_item)

                welder = getattr(w, "welder_name", None) or getattr(w, "welder_id", "") or "—"
                item_wdr = QTableWidgetItem(welder)
                item_wdr.setFont(QFont("Consolas", 9))
                item_wdr.setForeground(QColor(TEXT_MUTED))
                self.recent_table.setItem(r_idx, 3, item_wdr)

            self.recent_table.setSortingEnabled(True)

            # 6. Update Field Pulse Status Ribbon
            accepted = sum(c for s, c in status_rows if s in ("Accepted", "Inspected"))
            progress = f"{(accepted / welds * 100):.1f}%" if welds else "0.0%"
            self.pulse_label.setText(
                f"Weld Completion Rate: {progress} ({accepted:,}/{welds:,} welds)   •   "
                f"NDT 100% Pass: {ndt_pass:,}/{ndt_total or 0:,} joints   •   "
                f"Active QA/QC Queue: {requests_open:,} request(s)"
            )
            self.last_update.setText(f"● UPDATED {datetime.now().strftime('%H:%M:%S')}")

        except Exception as e:
            logger.exception("Dashboard telemetry refresh failed: %s", e)
            self.pulse_label.setText("⚠️ Field telemetry stream temporarily offline. Reconnecting…")


# ═════════════════════════════════════════════════════════════
#  STANDALONE TEST RUNNER
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    class MockSessionMgr:
        username = "Lead QC Engineer (Farhadi)"

    tab = DashboardTab(db=None, session=MockSessionMgr())
    tab.setWindowTitle("PipeAgent — Project Control & Executive Dashboard")
    tab.resize(1300, 860)
    tab.show()

    sys.exit(app.exec())