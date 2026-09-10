# -*- coding: utf-8 -*-
# ui/tabs/execution_intelligence_tab.py – PipeAgent 5.3.0
# Execution Intelligence: KPIs, Next-Best-Actions, Leading Indicators,
# and interactive What-If scenarios.
from __future__ import annotations

import csv
import datetime
import logging
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFrame, QProgressBar, QMenu,
    QDialog, QTextEdit, QTabWidget, QFormLayout,
    QAbstractItemView, QApplication, QFileDialog,
    QMessageBox, QSlider, QSpinBox, QSizePolicy,
    QDialogButtonBox,
)
from PyQt6.QtGui import (
    QColor, QFont, QCursor, QLinearGradient,
    QBrush, QPainter,
)

from db.models import Project
from services.execution_intelligence import ExecutionIntelligence

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  COLOR PALETTES
# ─────────────────────────────────────────────
SEVERITY_COLORS = {
    "Critical": {"bg": "#fde8e8", "fg": "#991b1b", "icon": "🔴"},
    "High":     {"bg": "#fff1e6", "fg": "#9a3412", "icon": "🟠"},
    "Medium":   {"bg": "#fef9c3", "fg": "#854d0e", "icon": "🟡"},
    "Low":      {"bg": "#e0f2fe", "fg": "#075985", "icon": "🔵"},
    "Info":     {"bg": "#f0fdf4", "fg": "#166534", "icon": "🟢"},
}
DEFAULT_SEVERITY = {"bg": "#f8fafc", "fg": "#475569", "icon": "⚪"}

PRIORITY_COLORS = {
    "P0": {"bg": "#fde8e8", "fg": "#991b1b"},
    "P1": {"bg": "#fff1e6", "fg": "#9a3412"},
    "P2": {"bg": "#fef9c3", "fg": "#854d0e"},
    "P3": {"bg": "#e0f2fe", "fg": "#075985"},
    "P4": {"bg": "#f0fdf4", "fg": "#166534"},
}
DEFAULT_PRIORITY = {"bg": "#f8fafc", "fg": "#475569"}

KPI_THRESHOLDS = {
    "Health Score":     {"good": 80, "warn": 60, "unit": "/100", "higher_better": True},
    "Weld Repair Rate": {"good": 3,  "warn": 7,  "unit": "%",    "higher_better": False},
    "Awaiting NDT":     {"good": 5,  "warn": 15, "unit": "",     "higher_better": False},
    "Blocked Fronts":   {"good": 0,  "warn": 3,  "unit": "",     "higher_better": False},
    "Overdue Fronts":   {"good": 0,  "warn": 2,  "unit": "",     "higher_better": False},
    "Draft Backlog":    {"good": 5,  "warn": 15, "unit": "",     "higher_better": False},
    "Failed Tests":     {"good": 0,  "warn": 2,  "unit": "",     "higher_better": False},
    "Turnover Gaps":    {"good": 0,  "warn": 3,  "unit": "",     "higher_better": False},
}

ACTION_COLUMNS = ["Priority", "Action", "Reason", "Score", "Category"]
SIGNAL_COLUMNS = ["Severity", "Category", "Signal", "Evidence", "Recommended Action"]


# ─────────────────────────────────────────────
#  STYLESHEET
# ─────────────────────────────────────────────
MAIN_STYLESHEET = """
    QWidget#execIntelTab {
        background: qlineargradient(x1:0, y1:0, x2:0.3, y2:1,
                                    stop:0 #f0f4f8, stop:1 #e2e8f0);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #0b2545, stop:1 #134074);
        border-radius: 16px; padding: 20px;
    }
    QLabel#mainTitle {
        color: white; font-size: 24px; font-weight: 800;
        font-family: 'Segoe UI', 'Vazirmatn', sans-serif;
    }
    QLabel#mainSubtitle { color: #8da9c4; font-size: 12px; }
    QFrame#filterCard, QFrame#actionsCard {
        background: white; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 14px;
    }

    /* KPI Cards — accent applied via dynamic property */
    QFrame#kpiCard {
        background: white; border: 2px solid #e2e8f0;
        border-radius: 12px; padding: 14px; min-height: 85px;
        border-left: 5px solid #94a3b8;
    }
    QFrame#kpiCard:hover { border-color: #3b82f6; }
    QFrame#kpiCard[accent="good"]    { border-left: 5px solid #10b981; }
    QFrame#kpiCard[accent="warn"]    { border-left: 5px solid #f59e0b; }
    QFrame#kpiCard[accent="bad"]     { border-left: 5px solid #ef4444; }
    QFrame#kpiCard[accent="neutral"] { border-left: 5px solid #94a3b8; }

    QLabel#kpiTitle {
        font-size: 11px; font-weight: 600;
        color: #64748b; text-transform: uppercase;
    }
    QLabel#kpiValue { font-size: 24px; font-weight: 800; }
    QLabel#sectionTitle { color: #1e293b; font-size: 14px; font-weight: 700; }

    QLineEdit {
        padding: 9px 12px; border: 2px solid #e2e8f0;
        border-radius: 8px; font-size: 13px; background: white;
    }
    QLineEdit:focus { border-color: #3b82f6; }
    QLineEdit:hover { border-color: #94a3b8; }

    QComboBox {
        padding: 9px 12px; border: 2px solid #e2e8f0;
        border-radius: 8px; font-size: 13px;
        background: white; min-width: 160px;
    }
    QComboBox:focus, QComboBox:hover { border-color: #3b82f6; }
    QComboBox::drop-down { border: none; width: 28px; }
    QComboBox::down-arrow {
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid #64748b; margin-right: 8px;
    }
    QComboBox QAbstractItemView {
        border: 2px solid #e2e8f0; border-radius: 8px;
        background: white;
        selection-background-color: #eff6ff; padding: 4px;
    }

    QPushButton#primaryBtn {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #3b82f6, stop:1 #2563eb);
        color: white; border: none; padding: 10px 22px;
        border-radius: 8px; font-size: 13px; font-weight: 700;
    }
    QPushButton#primaryBtn:hover {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #2563eb, stop:1 #1d4ed8);
    }
    QPushButton#primaryBtn:disabled { background: #94a3b8; }
    QPushButton#successBtn {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #10b981, stop:1 #059669);
        color: white; border: none; padding: 10px 22px;
        border-radius: 8px; font-size: 13px; font-weight: 700;
    }
    QPushButton#successBtn:hover {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #059669, stop:1 #047857);
    }
    QPushButton#secondaryBtn {
        background: white; color: #374151;
        border: 2px solid #d1d5db;
        padding: 9px 18px; border-radius: 8px;
        font-size: 13px; font-weight: 600;
    }
    QPushButton#secondaryBtn:hover {
        background: #f9fafb; border-color: #3b82f6; color: #3b82f6;
    }
    QPushButton#dangerBtn {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #ef4444, stop:1 #dc2626);
        color: white; border: none; padding: 10px 22px;
        border-radius: 8px; font-size: 13px; font-weight: 700;
    }

    QTableWidget {
        background: white; border: 1px solid #e2e8f0;
        border-radius: 12px; gridline-color: #f1f5f9;
        font-size: 12px;
        selection-background-color: #dbeafe;
        selection-color: #1e293b;
        alternate-background-color: #f8fafc;
    }
    QTableWidget::item { padding: 7px 10px; border-bottom: 1px solid #f1f5f9; }
    QTableWidget::item:selected { background: #dbeafe; }
    QTableWidget::item:hover { background: #f0f7ff; }
    QHeaderView::section {
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #f8fafc, stop:1 #eef2f7);
        color: #475569; font-weight: 700; font-size: 12px;
        padding: 10px; border: none;
        border-bottom: 2px solid #e2e8f0;
        border-right: 1px solid #e2e8f0;
    }
    QHeaderView::section:hover { background: #e2e8f0; }

    QProgressBar {
        border: none; border-radius: 6px;
        background: #e2e8f0; height: 14px;
        text-align: center; font-size: 10px;
        font-weight: 700; color: white;
    }
    QProgressBar::chunk {
        border-radius: 6px;
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #3b82f6, stop:1 #8b5cf6);
    }

    QGroupBox {
        font-size: 13px; font-weight: 700; color: #374151;
        border: 2px solid #e5e7eb; border-radius: 10px;
        margin-top: 12px; padding: 14px; padding-top: 26px;
    }
    QGroupBox::title {
        subcontrol-origin: margin; subcontrol-position: top left;
        left: 14px; padding: 2px 8px;
        background: white; border-radius: 4px;
    }

    QScrollBar:vertical {
        background: #f1f5f9; width: 10px; border-radius: 5px;
    }
    QScrollBar::handle:vertical {
        background: #94a3b8; border-radius: 5px; min-height: 30px;
    }
    QScrollBar::handle:vertical:hover { background: #64748b; }
"""


# ─────────────────────────────────────────────
#  KPI CARD
# ─────────────────────────────────────────────
class KPICard(QFrame):
    """
    KPI tile with dynamic accent coloring driven by Qt property selectors.

    Uses `setProperty("accent", ...)` + style repolish — the correct,
    reliable pattern for Qt6 dynamic styling.
    """

    def __init__(self, title: str, kpi_key: str):
        super().__init__()
        self.setObjectName("kpiCard")
        self.kpi_key = kpi_key
        self._threshold = KPI_THRESHOLDS.get(kpi_key, {})
        self.setFixedHeight(90)

        # Set the initial accent state
        self.setProperty("accent", "neutral")

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(14, 10, 14, 10)

        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("kpiTitle")
        layout.addWidget(self.title_lbl)

        self.value_lbl = QLabel("—")
        self.value_lbl.setObjectName("kpiValue")
        self.value_lbl.setStyleSheet(
            "font-size: 24px; font-weight: 800; color: #94a3b8;"
        )
        layout.addWidget(self.value_lbl)

    # ── Public API ───────────────────────────────────────────
    def set_value(self, text: str, numeric_value: float | None = None):
        self.value_lbl.setText(text)
        if numeric_value is None:
            self._set_state("neutral")
            return

        higher = self._threshold.get("higher_better", False)
        good = self._threshold.get("good", 0)
        warn = self._threshold.get("warn", 0)

        if higher:
            if numeric_value >= good:
                self._set_state("good")
            elif numeric_value >= warn:
                self._set_state("warn")
            else:
                self._set_state("bad")
        else:
            if numeric_value <= good:
                self._set_state("good")
            elif numeric_value <= warn:
                self._set_state("warn")
            else:
                self._set_state("bad")

    def reset(self):
        self.value_lbl.setText("—")
        self._set_state("neutral")

    # ── Internal ─────────────────────────────────────────────
    def _set_state(self, state: str):
        # ✅ FIXED: only touch the dynamic property; never change objectName.
        # Re-polish the widget so stylesheet selectors re-evaluate.
        self.setProperty("accent", state)
        self.style().unpolish(self)
        self.style().polish(self)

        fg_colors = {
            "good":    "#059669",
            "warn":    "#d97706",
            "bad":     "#dc2626",
            "neutral": "#94a3b8",
        }
        color = fg_colors.get(state, fg_colors["neutral"])
        self.value_lbl.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {color};"
        )


# ─────────────────────────────────────────────
#  BACKGROUND WORKER
# ─────────────────────────────────────────────
class IntelligenceCalcThread(QThread):
    """Background computation of execution-intelligence metrics."""

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(int, str)

    def __init__(self, engine, project_id: int):
        super().__init__()
        self.engine = engine
        self.project_id = project_id

    def run(self):
        try:
            self.progress.emit(15, "Loading project data…")
            self.progress.emit(35, "Analyzing weld records…")
            self.progress.emit(55, "Computing NDT queues…")
            self.progress.emit(70, "Evaluating front constraints…")
            self.progress.emit(85, "Generating recommendations…")

            result = self.engine.analyze(self.project_id)

            self.progress.emit(100, "Complete!")
            self.finished.emit(result)
        except Exception as e:
            logger.exception("Execution intelligence calc failed.")
            self.error.emit(str(e))


# ─────────────────────────────────────────────
#  DETAIL DIALOG
# ─────────────────────────────────────────────
class DetailDialog(QDialog):
    """Displays the details of an action or signal."""

    def __init__(self, title: str, data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"📋 {title}")
        self.setMinimumSize(600, 400)
        self.setStyleSheet(MAIN_STYLESHEET)
        self._build_ui(data)

    def _build_ui(self, data: dict):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title_lbl = QLabel(
            f"📋 {data.get('title', data.get('Action', 'Details'))}"
        )
        title_lbl.setStyleSheet(
            "font-size: 20px; font-weight: 800; color: #102a43;"
        )
        layout.addWidget(title_lbl)

        form = QFormLayout()
        form.setSpacing(10)

        for key, val in data.items():
            lbl = QLabel(f"{key}:")
            lbl.setStyleSheet("font-weight: 700; color: #374151;")

            val_lbl = QLabel(str(val))
            val_lbl.setStyleSheet("color: #1e293b;")
            val_lbl.setWordWrap(True)
            val_lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            form.addRow(lbl, val_lbl)

        layout.addLayout(form)
        layout.addStretch()

        btn = QPushButton("Close")
        btn.setObjectName("secondaryBtn")
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.clicked.connect(self.close)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class ExecutionIntelligenceTab(QWidget):
    """
    Execution Intelligence tab.
    """

    def __init__(self, db, session):
        super().__init__()
        self.setObjectName("execIntelTab")
        self.db = db
        self.session = session
        self.engine = ExecutionIntelligence(db)
        self._calc_thread: IntelligenceCalcThread | None = None
        self._cached_data: dict | None = None
        self._calc_start_time: datetime.datetime | None = None

        self._build_ui()
        self.setStyleSheet(MAIN_STYLESHEET)
        self._load_projects()

    # ═══════════════════════════════════════
    #  UI BUILD
    # ═══════════════════════════════════════
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(18, 18, 18, 18)

        root.addWidget(self._build_header())
        root.addLayout(self._build_kpi_grid())
        root.addWidget(self._build_filter_section())
        root.addWidget(self._build_progress_section())
        root.addWidget(self._build_actions_section(), stretch=1)
        root.addWidget(self._build_signals_section(), stretch=2)
        root.addWidget(self._build_scenario_section())
        root.addWidget(self._build_status_bar())

    def _build_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("headerCard")
        layout = QVBoxLayout(card)
        layout.setSpacing(6)

        top = QHBoxLayout()
        title = QLabel("🧠 Execution Intelligence")
        title.setObjectName("mainTitle")
        top.addWidget(title)
        top.addStretch()

        top.addWidget(QLabel("Project:"))
        self.cmb_project = QComboBox()
        self.cmb_project.setMinimumWidth(260)
        self.cmb_project.currentIndexChanged.connect(
            self._on_project_changed
        )
        top.addWidget(self.cmb_project)

        self.btn_recalc = QPushButton("⚡ Recalculate")
        self.btn_recalc.setObjectName("successBtn")
        self.btn_recalc.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_recalc.clicked.connect(self.refresh)
        top.addWidget(self.btn_recalc)

        layout.addLayout(top)

        sub = QLabel(
            "Leading indicators, next-best-actions and transparent "
            "what-if scenarios. Recommendations never replace "
            "engineering, QC or approved schedule decisions."
        )
        sub.setObjectName("mainSubtitle")
        sub.setWordWrap(True)
        layout.addWidget(sub)
        return card

    def _build_kpi_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(10)

        kpi_names = [
            "Health Score", "Weld Repair Rate", "Awaiting NDT",
            "Blocked Fronts", "Overdue Fronts", "Draft Backlog",
            "Failed Tests", "Turnover Gaps",
        ]

        self.cards: dict[str, KPICard] = {}
        for i, name in enumerate(kpi_names):
            card = KPICard(name, name)
            self.cards[name] = card
            grid.addWidget(card, i // 4, i % 4)

        return grid

    def _build_filter_section(self) -> QFrame:
        card = QFrame()
        card.setObjectName("filterCard")
        layout = QHBoxLayout(card)
        layout.setSpacing(10)

        layout.addWidget(QLabel("🔍 Search:"))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(
            "Search actions, signals, reasons…"
        )
        self.txt_search.setMinimumWidth(280)
        self.txt_search.textChanged.connect(self._apply_filters)
        layout.addWidget(self.txt_search)

        layout.addWidget(QLabel("Severity:"))
        self.cmb_severity = QComboBox()
        self.cmb_severity.addItem("All", None)
        for s in SEVERITY_COLORS.keys():
            self.cmb_severity.addItem(
                f"{SEVERITY_COLORS[s]['icon']} {s}", s
            )
        self.cmb_severity.currentIndexChanged.connect(self._apply_filters)
        layout.addWidget(self.cmb_severity)

        layout.addWidget(QLabel("Priority:"))
        self.cmb_priority = QComboBox()
        self.cmb_priority.addItem("All", None)
        for p in PRIORITY_COLORS.keys():
            self.cmb_priority.addItem(p, p)
        self.cmb_priority.currentIndexChanged.connect(self._apply_filters)
        layout.addWidget(self.cmb_priority)
        layout.addStretch()

        self.btn_export = QPushButton("📥 Export CSV")
        self.btn_export.setObjectName("secondaryBtn")
        self.btn_export.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_export.clicked.connect(self._export_csv)
        layout.addWidget(self.btn_export)
        return card

    def _build_progress_section(self) -> QWidget:
        self.progress_widget = QWidget()
        self.progress_widget.setVisible(False)

        layout = QVBoxLayout(self.progress_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.progress_label = QLabel("Calculating…")
        self.progress_label.setStyleSheet(
            "font-size: 12px; color: #8b5cf6; font-weight: 600;"
        )
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(14)
        layout.addWidget(self.progress_bar)
        return self.progress_widget

    def _build_actions_section(self) -> QGroupBox:
        box = QGroupBox("🎯 NEXT BEST ACTIONS")
        layout = QVBoxLayout(box)

        self.action_table = QTableWidget(0, len(ACTION_COLUMNS))
        self.action_table.setHorizontalHeaderLabels(ACTION_COLUMNS)
        self._style_table(self.action_table)
        self.action_table.doubleClicked.connect(self._on_action_double_click)
        self.action_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.action_table.customContextMenuRequested.connect(
            lambda pos: self._show_context_menu(
                self.action_table, "action", pos
            )
        )
        layout.addWidget(self.action_table)
        return box

    def _build_signals_section(self) -> QGroupBox:
        box = QGroupBox("⚠️ EARLY WARNING / LEADING INDICATORS")
        layout = QVBoxLayout(box)

        self.signal_table = QTableWidget(0, len(SIGNAL_COLUMNS))
        self.signal_table.setHorizontalHeaderLabels(SIGNAL_COLUMNS)
        self._style_table(self.signal_table)
        self.signal_table.doubleClicked.connect(self._on_signal_double_click)
        self.signal_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.signal_table.customContextMenuRequested.connect(
            lambda pos: self._show_context_menu(
                self.signal_table, "signal", pos
            )
        )
        layout.addWidget(self.signal_table)
        return box

    def _build_scenario_section(self) -> QFrame:
        card = QFrame()
        card.setObjectName("filterCard")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("🔮 Transparent What-If Scenario")
        title.setObjectName("sectionTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(12)

        ctrl_row.addWidget(QLabel("Extra NDT Shifts:"))
        self.spin_shifts = QSpinBox()
        self.spin_shifts.setRange(0, 10)
        self.spin_shifts.setValue(1)
        self.spin_shifts.setStyleSheet(
            "padding: 6px; border: 2px solid #e2e8f0; "
            "border-radius: 6px; font-size: 13px;"
        )
        self.spin_shifts.valueChanged.connect(self._recalc_scenario)
        ctrl_row.addWidget(self.spin_shifts)

        ctrl_row.addWidget(QLabel("Crew Multiplier:"))
        self.spin_crew = QSpinBox()
        self.spin_crew.setRange(1, 5)
        self.spin_crew.setValue(1)
        self.spin_crew.setStyleSheet(
            "padding: 6px; border: 2px solid #e2e8f0; "
            "border-radius: 6px; font-size: 13px;"
        )
        self.spin_crew.valueChanged.connect(self._recalc_scenario)
        ctrl_row.addWidget(self.spin_crew)
        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        self.scenario_lbl = QLabel(
            "Select a project and recalculate to see what-if scenarios."
        )
        self.scenario_lbl.setWordWrap(True)
        self.scenario_lbl.setStyleSheet(
            "background: #eef7fb; border: 1px solid #c9e1eb; "
            "border-radius: 8px; padding: 12px; color: #17445b; "
            "font-size: 13px; line-height: 1.6;"
        )
        self.scenario_lbl.setMinimumHeight(60)
        layout.addWidget(self.scenario_lbl)
        return card

    def _build_status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setStyleSheet(
            "background: #f1f5f9; border-radius: 8px; padding: 6px 12px;"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(20)

        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(self.lbl_status)
        layout.addStretch()

        self.lbl_actions_count = QLabel("Actions: 0")
        self.lbl_actions_count.setStyleSheet(
            "color: #64748b; font-size: 12px; font-weight: 600;"
        )
        layout.addWidget(self.lbl_actions_count)

        self.lbl_signals_count = QLabel("Signals: 0")
        self.lbl_signals_count.setStyleSheet(
            "color: #64748b; font-size: 12px; font-weight: 600;"
        )
        layout.addWidget(self.lbl_signals_count)

        self.lbl_calc_time = QLabel("")
        self.lbl_calc_time.setStyleSheet(
            "color: #64748b; font-size: 12px;"
        )
        layout.addWidget(self.lbl_calc_time)
        return bar

    # ── TABLE CONFIG ─────────────────────────────────────────
    def _style_table(self, t: QTableWidget):
        t.setAlternatingRowColors(True)
        # ✅ FIXED: use QAbstractItemView enums
        t.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        t.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        t.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        t.setSortingEnabled(True)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

    # ═══════════════════════════════════════
    #  PROJECT LOADING
    # ═══════════════════════════════════════
    def _load_projects(self):
        self.cmb_project.blockSignals(True)
        self.cmb_project.clear()
        self.cmb_project.addItem("— Select Project —", None)

        try:
            with self.db.session_scope() as s:
                projects = (
                    s.query(Project)
                    .order_by(Project.project_code)
                    .all()
                )
                for p in projects:
                    self.cmb_project.addItem(
                        f"{p.project_code} — {p.title}", p.id
                    )
        except Exception:
            logger.exception("Load projects failed")

        self.cmb_project.blockSignals(False)
        self._clear_all()

    def _on_project_changed(self):
        pid = self.cmb_project.currentData()
        if pid:
            self.refresh()
        else:
            self._clear_all()

    # ═══════════════════════════════════════
    #  REFRESH / COMPUTE
    # ═══════════════════════════════════════
    def refresh(self):
        pid = self.cmb_project.currentData()
        if not pid:
            self._clear_all()
            self._set_status("Select a project.")
            return

        # ✅ FIXED: stop previous thread before starting a new one
        self._stop_calc_thread()

        self.btn_recalc.setEnabled(False)
        self.btn_recalc.setText("⏳ Calculating…")
        self.progress_widget.setVisible(True)
        self.progress_bar.setValue(0)
        self._set_status("Calculating execution intelligence…")

        self._calc_start_time = datetime.datetime.now()

        self._calc_thread = IntelligenceCalcThread(self.engine, pid)
        self._calc_thread.progress.connect(self._on_calc_progress)
        self._calc_thread.finished.connect(self._on_calc_finished)
        self._calc_thread.error.connect(self._on_calc_error)
        self._calc_thread.start()

    def _stop_calc_thread(self):
        """Gracefully stop any in-flight calc thread."""
        if self._calc_thread is None:
            return
        try:
            if self._calc_thread.isRunning():
                self._calc_thread.requestInterruption()
                self._calc_thread.wait(2000)
            self._calc_thread.deleteLater()
        except Exception:
            logger.warning("Calc thread stop failed", exc_info=True)
        self._calc_thread = None

    def _on_calc_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.progress_label.setText(msg)
        self._set_status(msg)

    def _on_calc_finished(self, data: dict):
        self.btn_recalc.setEnabled(True)
        self.btn_recalc.setText("⚡ Recalculate")
        QTimer.singleShot(
            1500, lambda: self.progress_widget.setVisible(False)
        )

        self._cached_data = data
        self._display_results(data)

        if self._calc_start_time is not None:
            elapsed = datetime.datetime.now() - self._calc_start_time
            self.lbl_calc_time.setText(
                f"Calc time: {elapsed.total_seconds():.1f}s"
            )

        self._set_status(
            f"Intelligence calculated for "
            f"{self.cmb_project.currentText()}"
        )

        # ✅ FIXED: release thread resources
        if self._calc_thread is not None:
            self._calc_thread.deleteLater()
            self._calc_thread = None

    def _on_calc_error(self, msg: str):
        self.btn_recalc.setEnabled(True)
        self.btn_recalc.setText("⚡ Recalculate")
        self.progress_widget.setVisible(False)
        self._set_status(f"Error: {msg}")
        QMessageBox.critical(
            self, "Calculation Error",
            f"Failed to calculate intelligence:\n\n{msg}"
        )

        # ✅ FIXED: release thread resources
        if self._calc_thread is not None:
            self._calc_thread.deleteLater()
            self._calc_thread = None

    # ═══════════════════════════════════════
    #  DISPLAY
    # ═══════════════════════════════════════
    def _display_results(self, data: dict):
        try:
            kpis = data.get("kpis", {})

            health = data.get("health_score", 0)
            health_label = data.get("health_label", "")
            self.cards["Health Score"].set_value(
                f"{health}/100 · {health_label}", health
            )

            repair = kpis.get("repair_rate_pct", 0)
            self.cards["Weld Repair Rate"].set_value(
                f"{repair:.1f}%", repair
            )

            ndt = kpis.get("awaiting_ndt", 0)
            self.cards["Awaiting NDT"].set_value(str(ndt), ndt)

            blocked = kpis.get("blocked_fronts", 0)
            self.cards["Blocked Fronts"].set_value(str(blocked), blocked)

            overdue = kpis.get("overdue_fronts", 0)
            self.cards["Overdue Fronts"].set_value(str(overdue), overdue)

            draft = kpis.get("draft_backlog", 0)
            self.cards["Draft Backlog"].set_value(str(draft), draft)

            failed = kpis.get("failed_tests", 0)
            self.cards["Failed Tests"].set_value(str(failed), failed)

            gaps = kpis.get("turnover_gap_count", 0)
            self.cards["Turnover Gaps"].set_value(str(gaps), gaps)

            self._populate_actions(data.get("actions", []))
            self._populate_signals(data.get("signals", []))
            self._recalc_scenario()
        except Exception:
            logger.exception("Display results failed")
            self._set_status("Display error")

    def _populate_actions(self, actions: list):
        self.action_table.setSortingEnabled(False)
        self.action_table.setRowCount(0)

        for a in actions:
            row = self.action_table.rowCount()
            self.action_table.insertRow(row)

            values = [
                a.get("priority", ""),
                a.get("title", ""),
                a.get("reason", ""),
                str(a.get("score", "")),
                a.get("category", ""),
            ]

            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col == 0:
                    colors = PRIORITY_COLORS.get(
                        str(val), DEFAULT_PRIORITY
                    )
                    item.setBackground(QColor(colors["bg"]))
                    item.setForeground(QColor(colors["fg"]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)

                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, a)

                self.action_table.setItem(row, col, item)

            self.action_table.setRowHeight(row, 38)

        self.action_table.setSortingEnabled(True)
        self.lbl_actions_count.setText(
            f"Actions: {self.action_table.rowCount()}"
        )

    def _populate_signals(self, signals: list):
        self.signal_table.setSortingEnabled(False)
        self.signal_table.setRowCount(0)

        for x in signals:
            row = self.signal_table.rowCount()
            self.signal_table.insertRow(row)

            values = [
                x.get("severity", ""),
                x.get("category", ""),
                x.get("title", ""),
                x.get("evidence", ""),
                x.get("action", ""),
            ]

            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                if col >= 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col == 0:
                    sev = str(val)
                    colors = SEVERITY_COLORS.get(sev, DEFAULT_SEVERITY)
                    item.setBackground(QColor(colors["bg"]))
                    item.setForeground(QColor(colors["fg"]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                    item.setText(f"{colors['icon']} {sev}")

                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, x)

                self.signal_table.setItem(row, col, item)

            self.signal_table.setRowHeight(row, 42)

        self.signal_table.setSortingEnabled(True)
        self.lbl_signals_count.setText(
            f"Signals: {self.signal_table.rowCount()}"
        )

    # ═══════════════════════════════════════
    #  FILTERS
    # ═══════════════════════════════════════
    def _apply_filters(self):
        search = self.txt_search.text().strip().lower()
        sev_filter = self.cmb_severity.currentData()
        pri_filter = self.cmb_priority.currentData()

        self._filter_table(
            self.action_table, search, pri_filter, "priority"
        )
        self._filter_table(
            self.signal_table, search, sev_filter, "severity"
        )

    def _filter_table(
        self,
        table: QTableWidget,
        search: str,
        level_filter: str | None,
        level_col_name: str,
    ):
        for row in range(table.rowCount()):
            show = True

            if level_filter:
                first_item = table.item(row, 0)
                if first_item:
                    data = first_item.data(Qt.ItemDataRole.UserRole)
                    if (data
                            and data.get(level_col_name, "") != level_filter):
                        show = False

            if show and search:
                row_text = " ".join(
                    table.item(row, c).text().lower()
                    for c in range(table.columnCount())
                    if table.item(row, c)
                )
                if search not in row_text:
                    show = False

            table.setRowHidden(row, not show)

    # ═══════════════════════════════════════
    #  WHAT-IF SCENARIO
    # ═══════════════════════════════════════
    def _recalc_scenario(self):
        if not self._cached_data:
            return

        scenario = self._cached_data.get("scenario", {})
        if not scenario:
            self.scenario_lbl.setText(
                "No scenario data available for this project."
            )
            return

        extra_shifts = self.spin_shifts.value()
        crew_mult = self.spin_crew.value()

        assumption = scenario.get("assumption", "N/A")
        base_queue = scenario.get("ndt_queue_after_extra_shift", "N/A")
        message = scenario.get("message", "")

        try:
            base_val = (
                float(str(base_queue).split()[0])
                if base_queue != "N/A" else 0
            )
            adjusted = max(0, base_val - (extra_shifts - 1) * 5) / crew_mult
            adjusted_str = f"{adjusted:.0f}"
        except (ValueError, TypeError, IndexError):
            adjusted_str = str(base_queue)

        self.scenario_lbl.setText(
            f"<b>🔮 Transparent What-If:</b> {assumption}<br><br>"
            f"▸ Extra NDT Shifts: <b>{extra_shifts}</b> &nbsp;|&nbsp; "
            f"Crew Multiplier: <b>×{crew_mult}</b><br>"
            f"▸ Illustrative NDT queue: <b>{adjusted_str}</b> "
            f"(base: {base_queue})<br><br>"
            f"<i>{message}</i>"
        )

    # ═══════════════════════════════════════
    #  ROW DETAIL / CONTEXT MENU
    # ═══════════════════════════════════════
    def _on_action_double_click(self, index):
        row = index.row()
        item = self.action_table.item(row, 0)
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                dlg = DetailDialog("Action Details", data, self)
                dlg.exec()

    def _on_signal_double_click(self, index):
        row = index.row()
        item = self.signal_table.item(row, 0)
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                dlg = DetailDialog("Signal Details", data, self)
                dlg.exec()

    def _show_context_menu(self, table: QTableWidget, kind: str, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: white; border: 1px solid #e2e8f0;
                border-radius: 8px; padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px; font-size: 13px; border-radius: 4px;
            }
            QMenu::item:selected { background: #eff6ff; color: #1e293b; }
            QMenu::separator {
                height: 1px; background: #e2e8f0; margin: 4px 8px;
            }
        """)

        act_view = menu.addAction("📋 View Details")
        act_view.triggered.connect(lambda: self._view_detail(table))

        act_copy = menu.addAction("📋 Copy Row Text")
        act_copy.triggered.connect(lambda: self._copy_row(table))

        menu.addSeparator()

        act_export = menu.addAction("📥 Export All to CSV")
        act_export.triggered.connect(self._export_csv)

        menu.exec(table.viewport().mapToGlobal(pos))

    def _view_detail(self, table: QTableWidget):
        row = table.currentRow()
        if row < 0:
            return
        item = table.item(row, 0)
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                dlg = DetailDialog("Details", data, self)
                dlg.exec()

    def _copy_row(self, table: QTableWidget):
        row = table.currentRow()
        if row < 0:
            return
        texts = []
        for c in range(table.columnCount()):
            item = table.item(row, c)
            if item:
                texts.append(item.text())
        QApplication.clipboard().setText(" | ".join(texts))
        self._set_status("Row copied to clipboard")

    # ═══════════════════════════════════════
    #  EXPORT
    # ═══════════════════════════════════════
    def _export_csv(self):
        if not self._cached_data:
            QMessageBox.warning(
                self, "No Data", "Calculate intelligence first."
            )
            return

        default_name = (
            f"execution_intelligence_"
            f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", default_name,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)

                writer.writerow(["=== KPIs ==="])
                kpis = self._cached_data.get("kpis", {})
                writer.writerow([
                    "Health Score",
                    self._cached_data.get("health_score", ""),
                ])
                writer.writerow([
                    "Health Label",
                    self._cached_data.get("health_label", ""),
                ])
                for k, v in kpis.items():
                    writer.writerow([k, v])
                writer.writerow([])

                writer.writerow(["=== Next Best Actions ==="])
                writer.writerow(ACTION_COLUMNS)
                for a in self._cached_data.get("actions", []):
                    writer.writerow([
                        a.get("priority", ""),
                        a.get("title", ""),
                        a.get("reason", ""),
                        a.get("score", ""),
                        a.get("category", ""),
                    ])
                writer.writerow([])

                writer.writerow(["=== Leading Indicators ==="])
                writer.writerow(SIGNAL_COLUMNS)
                for x in self._cached_data.get("signals", []):
                    writer.writerow([
                        x.get("severity", ""),
                        x.get("category", ""),
                        x.get("title", ""),
                        x.get("evidence", ""),
                        x.get("action", ""),
                    ])

            QMessageBox.information(
                self, "✅ Exported",
                f"Intelligence data exported to:\n{path}"
            )
            self._set_status("Exported to CSV")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    # ═══════════════════════════════════════
    #  RESET / STATUS
    # ═══════════════════════════════════════
    def _clear_all(self):
        for card in self.cards.values():
            card.reset()
        self.action_table.setRowCount(0)
        self.signal_table.setRowCount(0)
        self.scenario_lbl.setText(
            "Select a project and click Recalculate."
        )
        self.lbl_actions_count.setText("Actions: 0")
        self.lbl_signals_count.setText("Signals: 0")
        self.lbl_calc_time.setText("")
        self._cached_data = None

    def _set_status(self, msg: str):
        self.lbl_status.setText(msg)

    # ═══════════════════════════════════════
    #  CLEANUP
    # ═══════════════════════════════════════
    def closeEvent(self, event):
        """Ensure the calc thread is stopped before widget closes."""
        self._stop_calc_thread()
        super().closeEvent(event)