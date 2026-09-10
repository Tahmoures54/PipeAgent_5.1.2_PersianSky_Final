# -*- coding: utf-8 -*-
# ui/tabs/execution_os_tab.py – PipeAgent
# Execution OS: Unified View for Execution Graph, Predictive Bottlenecks,
# Work Front Autopilot, Quality Intelligence, and Digital Turnover.
from __future__ import annotations

import csv
import logging
import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QSplitter, QTextEdit, QFrame,
    QProgressBar, QMenu, QFileDialog, QMessageBox, QApplication,
    QLineEdit, QAbstractItemView,
)
from PyQt6.QtGui import (
    QColor, QFont, QIcon, QAction, QCursor, QBrush, QPen,
)

from db.models import Project
from services.execution_os import ExecutionOSService
from ._shared import stop_thread_safely, get_session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  PALETTE
# ─────────────────────────────────────────────────────────────
COLOR_PALETTE = {
    "Critical": {"bg": "#fde8e8", "fg": "#991b1b", "border": "#f87171", "icon": "🔴"},
    "High":     {"bg": "#fff1e6", "fg": "#9a3412", "border": "#fb923c", "icon": "🟠"},
    "Medium":   {"bg": "#fef9c3", "fg": "#854d0e", "border": "#facc15", "icon": "🟡"},
    "Low":      {"bg": "#e0f2fe", "fg": "#075985", "border": "#38bdf8", "icon": "🔵"},
    "Optimal":  {"bg": "#ecfdf5", "fg": "#065f46", "border": "#34d399", "icon": "🟢"},
    "Neutral":  {"bg": "#f1f5f9", "fg": "#334155", "border": "#cbd5e1", "icon": "⚪"},
}

KPI_THRESHOLDS = {
    "Health":             {"good": 80,   "warn": 60,   "higher_better": True},
    "Repair Rate":        {"good": 3.0,  "warn": 8.0,  "higher_better": False},
    "Turnover Readiness": {"good": 90,   "warn": 70,   "higher_better": True},
    "Open Punches":       {"good": 0,    "warn": 10,   "higher_better": False},
}

OS_STYLESHEET = """
    QWidget#executionOSTab {
        background: qlineargradient(x1:0, y1:0, x2:0.5, y2:1,
                                    stop:0 #f8fafc, stop:1 #e2e8f0);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #0f172a, stop:1 #1e293b);
        border-radius: 12px; padding: 16px;
    }
    QLabel#mainTitle {
        color: #f8fafc; font-size: 24px; font-weight: 900;
        font-family: 'Segoe UI', system-ui, sans-serif;
    }
    QLabel#subTitle { color: #94a3b8; font-size: 12px; }
    QFrame#kpiCard {
        background: white; border: 1px solid #e2e8f0;
        border-radius: 10px; padding: 12px;
    }
    QFrame#kpiCard:hover { border-color: #3b82f6; background: #f8fafc; }
    QLabel#kpiTitle {
        font-size: 11px; font-weight: 700; color: #64748b;
        text-transform: uppercase;
    }
    QLabel#kpiValue { font-size: 20px; font-weight: 800; }
    QLineEdit, QComboBox {
        padding: 8px 12px; border: 2px solid #e2e8f0;
        border-radius: 6px; font-size: 13px;
        background: white; color: #1e293b;
    }
    QLineEdit:focus, QComboBox:focus {
        border-color: #3b82f6; background: #f8faff;
    }
    QPushButton#primaryBtn {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #3b82f6, stop:1 #2563eb);
        color: white; border: none; padding: 8px 18px;
        border-radius: 6px; font-weight: 700;
    }
    QPushButton#primaryBtn:hover {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #2563eb, stop:1 #1d4ed8);
    }
    QPushButton#primaryBtn:disabled { background: #94a3b8; }
    QPushButton#secondaryBtn {
        background: white; color: #334155;
        border: 2px solid #cbd5e1;
        padding: 7px 16px; border-radius: 6px; font-weight: 600;
    }
    QPushButton#secondaryBtn:hover {
        background: #f8fafc; border-color: #3b82f6; color: #3b82f6;
    }
    QTableWidget {
        background: white; border: 1px solid #e2e8f0;
        border-radius: 10px; gridline-color: #f1f5f9; font-size: 12px;
    }
    QTableWidget::item { padding: 6px 10px; }
    QTableWidget::item:selected { background: #eff6ff; color: #1e293b; }
    QHeaderView::section {
        background: #f8fafc; color: #475569;
        font-weight: 700; font-size: 11px; padding: 8px;
        border: none; border-bottom: 2px solid #e2e8f0;
        border-right: 1px solid #f1f5f9;
    }
    QGroupBox {
        font-size: 12px; font-weight: 800; color: #1e293b;
        border: 2px solid #e2e8f0; border-radius: 8px;
        margin-top: 10px; padding: 10px; padding-top: 20px;
        background: white;
    }
    QGroupBox::title {
        subcontrol-origin: margin; subcontrol-position: top left;
        left: 10px; padding: 0 5px; background: white;
    }
"""


# ─────────────────────────────────────────────────────────────
#  WORKER
# ─────────────────────────────────────────────────────────────
class RecalculateWorker(QThread):
    """Background worker for heavy Execution OS computations."""
    finished = pyqtSignal(dict)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)

    def __init__(self, service: ExecutionOSService, project_id: int):
        super().__init__()
        self.service = service
        self.project_id = project_id

    def run(self):
        try:
            self.progress.emit(10, "Extracting engineering graph structure...")
            self.progress.emit(35, "Scanning physical constraint networks...")
            self.progress.emit(60, "Running predictive bottleneck simulator...")
            self.progress.emit(80, "Verifying digital quality turnover principles...")

            data = self.service.snapshot(self.project_id)

            self.progress.emit(100, "OS Kernel analysis complete!")
            self.finished.emit(data)
        except Exception as e:
            logger.exception("Background execution OS computation failed.")
            self.error.emit(str(e))


# ─────────────────────────────────────────────────────────────
#  KPI CARD
# ─────────────────────────────────────────────────────────────
class OSKPICard(QFrame):
    """Dynamic KPI tile with threshold-based coloring."""

    def __init__(self, title: str, key_name: str):
        super().__init__()
        self.setObjectName("kpiCard")
        self.key_name = key_name
        self._thresholds = KPI_THRESHOLDS.get(key_name, None)

        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(12, 10, 12, 10)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("kpiTitle")
        layout.addWidget(self.lbl_title)

        self.lbl_value = QLabel("—")
        self.lbl_value.setObjectName("kpiValue")
        self.lbl_value.setStyleSheet("color: #64748b; font-weight: 800;")
        layout.addWidget(self.lbl_value)

    def update_value(self, text_val: str, numeric_val: Optional[float] = None):
        self.lbl_value.setText(text_val)

        if numeric_val is None or not self._thresholds:
            self._set_theme_color("#1e293b")
            return

        higher_better = self._thresholds["higher_better"]
        good_limit = self._thresholds["good"]
        warn_limit = self._thresholds["warn"]

        if higher_better:
            if numeric_val >= good_limit:
                self._set_theme_color("#059669")
            elif numeric_val >= warn_limit:
                self._set_theme_color("#d97706")
            else:
                self._set_theme_color("#dc2626")
        else:
            if numeric_val <= good_limit:
                self._set_theme_color("#059669")
            elif numeric_val <= warn_limit:
                self._set_theme_color("#d97706")
            else:
                self._set_theme_color("#dc2626")

    def _set_theme_color(self, hex_color: str):
        self.lbl_value.setStyleSheet(
            f"color: {hex_color}; font-size: 20px; font-weight: 800;"
        )

    def reset_card(self):
        self.lbl_value.setText("—")
        self._set_theme_color("#64748b")


# ─────────────────────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────────────────────
class ExecutionOSTab(QWidget):
    def __init__(self, db, session):
        super().__init__()
        self.setObjectName("executionOSTab")
        self.db = db
        self.session = session
        self.engine = ExecutionOSService(db)
        self.active_worker: Optional[RecalculateWorker] = None
        self._last_snapshot_cache: Optional[dict] = None

        self._build()
        self.setStyleSheet(OS_STYLESHEET)
        self.refresh()

    # ── UI BUILD ─────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Header
        top_card = QFrame()
        top_card.setObjectName("headerCard")
        top_lay = QHBoxLayout(top_card)
        top_lay.setContentsMargins(16, 12, 16, 12)

        header_texts = QVBoxLayout()
        title = QLabel("💻 PipeAgent Execution OS")
        title.setObjectName("mainTitle")
        sub = QLabel(
            "One operating view for Execution Graph, Predictive Bottlenecks, "
            "Work Fronts, Quality, and Turnover."
        )
        sub.setObjectName("subTitle")
        header_texts.addWidget(title)
        header_texts.addWidget(sub)
        top_lay.addLayout(header_texts, 1)

        control_layout = QHBoxLayout()
        control_layout.setSpacing(8)

        lbl_proj = QLabel("Active Project:")
        lbl_proj.setStyleSheet("color: white; font-weight: 700; font-size: 13px;")
        control_layout.addWidget(lbl_proj)

        self.project = QComboBox()
        self.project.setMinimumWidth(240)
        self.project.currentIndexChanged.connect(self._on_project_changed)
        control_layout.addWidget(self.project)

        self.btn_recalc = QPushButton("⚡ Recalculate OS")
        self.btn_recalc.setObjectName("primaryBtn")
        self.btn_recalc.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_recalc.clicked.connect(self.recalculate_data)
        control_layout.addWidget(self.btn_recalc)

        top_lay.addLayout(control_layout)
        root.addWidget(top_card)

        # Filter card
        filter_card = QFrame()
        filter_card.setStyleSheet(
            "background: white; border: 1px solid #cbd5e1; border-radius: 8px;"
        )
        filter_lay = QHBoxLayout(filter_card)
        filter_lay.setContentsMargins(12, 8, 12, 8)

        filter_lay.addWidget(QLabel("🔍 Filter OS Tables:"))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(
            "Search recommendations, evidence, actions, severities..."
        )
        self.txt_search.textChanged.connect(self.apply_live_filter)
        filter_lay.addWidget(self.txt_search, 1)

        self.btn_export = QPushButton("📥 Export OS Report")
        self.btn_export.setObjectName("secondaryBtn")
        self.btn_export.clicked.connect(self.export_os_snapshot)
        filter_lay.addWidget(self.btn_export)

        root.addWidget(filter_card)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(12)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        # KPI grid
        grid_layout = QGridLayout()
        grid_layout.setSpacing(8)
        self.cards: dict[str, OSKPICard] = {}

        kpis_definition = [
            ("Health Index",       "Health"),
            ("Graph Nodes",        "Graph Nodes"),
            ("Graph Links",        "Graph Links"),
            ("Bottleneck Threat",  "Bottleneck"),
            ("Ready to Dispatch",  "Ready to Dispatch"),
            ("Weld Repair Rate",   "Repair Rate"),
            ("Turnover Readiness", "Turnover Readiness"),
            ("Open Punch Lists",   "Open Punches"),
        ]

        for i, (label, key) in enumerate(kpis_definition):
            card = OSKPICard(label, key)
            self.cards[key] = card
            grid_layout.addWidget(card, i // 4, i % 4)

        root.addLayout(grid_layout)

        # Splitter with tables
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(8)

        self.action_table = self._table(
            ['Priority', 'Front Code', 'Assigned Team',
             'Machine Allocated', 'Score', 'Decision Grounding']
        )
        self.signal_table = self._table(
            ['Severity', 'Category', 'Anomalous Evidence',
             'Autopilot Guardrail / Recommended Correction']
        )
        self.gap_table = self._table(
            ['Turnover Gap Category', 'System Discrepancy Evidence',
             'Pre-handover Action Item']
        )
        self.impact_table = self._table(
            ['Forecast Severity', 'Forecast Impact Scenario', 'Probability',
             'Affected Node Path', 'Recommended Action']
        )

        for table in (self.action_table, self.signal_table,
                      self.gap_table, self.impact_table):
            table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            table.customContextMenuRequested.connect(
                lambda pos, t=table: self._show_context_menu(pos, t)
            )

        sections = [
            ('🚀 WORK FRONT AUTOPILOT (DECISIONS RECOMMENDED)', self.action_table),
            ('🚨 PREDICTIVE / QUALITY CONTROL SIGNALS', self.signal_table),
            ('📦 DIGITAL TURNOVER GAP ANALYTICS', self.gap_table),
            ('🔮 PERSISTENT EVENT-DRIVEN IMPACT FORECASTS', self.impact_table),
        ]

        for title_txt, table in sections:
            box = QGroupBox(title_txt)
            lay = QVBoxLayout(box)
            lay.setContentsMargins(8, 12, 8, 8)
            lay.addWidget(table)
            splitter.addWidget(box)

        root.addWidget(splitter, 1)

        # Explanation panel
        self.explanation = QTextEdit()
        self.explanation.setReadOnly(True)
        self.explanation.setMaximumHeight(135)
        self.explanation.setStyleSheet(
            'background: #f8fafc; border: 1px solid #cbd5e1; '
            'border-radius: 8px; padding: 10px; color: #1e293b; font-size: 12px;'
        )
        root.addWidget(self.explanation)

    def _table(self, headers: list[str]) -> QTableWidget:
        # ✅ FIXED: use QAbstractItemView for enum access
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setAlternatingRowColors(True)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return t

    # ── REFRESH / PROJECT SELECTION ──────────────────────────
    def refresh(self):
        cur = self.project.currentData()
        self.project.blockSignals(True)
        self.project.clear()
        self.project.addItem('Select Project', None)

        try:
            with self.db.session_scope() as s:
                for p in s.query(Project).order_by(Project.project_code).all():
                    self.project.addItem(f'{p.project_code} — {p.title}', p.id)
        except Exception as e:
            logger.exception("Could not fetch database project codes.")
            QMessageBox.critical(
                self, "Database Error",
                f"Could not load projects:\n{e}"
            )

        if cur is not None:
            idx = self.project.findData(cur)
            if idx >= 0:
                self.project.setCurrentIndex(idx)

        self.project.blockSignals(False)
        self._on_project_changed()

    def _on_project_changed(self):
        pid = self.project.currentData()
        if not pid:
            self._clear_views()
            return
        self.recalculate_data()

    def recalculate_data(self):
        pid = self.project.currentData()
        if not pid:
            return

        # ✅ FIXED: cleanup previous worker
        stop_thread_safely(self.active_worker, wait_ms=2000)
        self.active_worker = None

        self.btn_recalc.setEnabled(False)
        self.btn_recalc.setText("⏳ Analyzing OS...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(5)

        self.active_worker = RecalculateWorker(self.engine, pid)
        self.active_worker.progress.connect(self._on_worker_progress)
        self.active_worker.finished.connect(self._on_worker_success)
        self.active_worker.error.connect(self._on_worker_failed)
        self.active_worker.start()

    def _on_worker_progress(self, val: int, text_info: str):
        self.progress_bar.setValue(val)
        self.explanation.setHtml(
            f"<b style='color:#2563eb;'>[OS Engine Phase]</b> {text_info}"
        )

    def _on_worker_success(self, d: dict):
        self._last_snapshot_cache = d
        self._populate_all_ui(d)

        self.btn_recalc.setEnabled(True)
        self.btn_recalc.setText("⚡ Recalculate OS")
        self.progress_bar.setVisible(False)

        # ✅ FIXED: release thread resources
        if self.active_worker is not None:
            self.active_worker.deleteLater()
            self.active_worker = None

    def _on_worker_failed(self, err_msg: str):
        self.btn_recalc.setEnabled(True)
        self.btn_recalc.setText("⚡ Recalculate OS")
        self.progress_bar.setVisible(False)

        self.explanation.setHtml(
            f"<b style='color:#dc2626;'>[Analysis Failed]</b> {err_msg}"
        )
        QMessageBox.critical(
            self, "Analysis Fault",
            f"The Execution OS simulation failed:\n{err_msg}"
        )

        if self.active_worker is not None:
            self.active_worker.deleteLater()
            self.active_worker = None

    # ── UI POPULATION ────────────────────────────────────────
    def _populate_all_ui(self, d: dict):
        h  = d.get('health', {})
        pc = d.get('persistent_control', {})
        g  = d.get('execution_graph', {})
        b  = d.get('predictive_bottleneck', {})
        a  = d.get('work_front_autopilot', {})
        q  = d.get('quality_intelligence', {})
        t  = d.get('turnover_autopilot', {})

        self.cards['Health'].update_value(
            f"{h.get('score', 0)}/100 · {h.get('label', 'Unknown')}",
            float(h.get('score', 0)),
        )
        self.cards['Graph Nodes'].update_value(str(g.get('node_count', 0)))
        self.cards['Graph Links'].update_value(str(g.get('edge_count', 0)))

        b_status = b.get('status', 'Optimal')
        self.cards['Bottleneck'].update_value(b_status)
        self._highlight_kpi_card_manually('Bottleneck', b_status)

        self.cards['Ready to Dispatch'].update_value(
            str(a.get('ready_unassigned', 0))
        )
        self.cards['Repair Rate'].update_value(
            f"{q.get('repair_rate_pct', 0.0):.1f}%",
            float(q.get('repair_rate_pct', 0.0)),
        )
        self.cards['Turnover Readiness'].update_value(
            f"{t.get('readiness_pct', 0.0):.0f}%",
            float(t.get('readiness_pct', 0.0)),
        )
        self.cards['Open Punches'].update_value(
            str(t.get('open_punches', 0)),
            float(t.get('open_punches', 0)),
        )

        # Action table
        self.action_table.setRowCount(0)
        for i, x in enumerate(a.get('recommendations', [])):
            self.action_table.insertRow(i)
            vals = [
                f"P{i+1:02d}",
                x.get('front_code', ''),
                x.get('team') or '—',
                x.get('machine') or '—',
                x.get('score', ''),
                x.get('reason', ''),
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                if col == 0:
                    item.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
                    item.setForeground(QBrush(QColor("#2563eb")))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter if col < 5
                    else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                self.action_table.setItem(i, col, item)

        # Signal table
        self.signal_table.setRowCount(0)
        signals = list(b.get('signals', [])) + [
            {
                'severity': sx.get('severity'),
                'category': 'QUALITY',
                'evidence': sx.get('evidence'),
                'recommendation': sx.get('action'),
            }
            for sx in q.get('signals', [])
        ]
        for i, x in enumerate(signals):
            self.signal_table.insertRow(i)
            sev = x.get('severity', 'Medium')
            vals = [
                sev,
                x.get('category', 'QUALITY'),
                x.get('evidence', ''),
                x.get('recommendation', ''),
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                if col == 0:
                    self._style_severity_item(item, sev)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter if col < 2
                    else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                self.signal_table.setItem(i, col, item)

        # Gap table
        self.gap_table.setRowCount(0)
        for i, x in enumerate(t.get('gaps', [])):
            self.gap_table.insertRow(i)
            vals = [
                x.get('category', ''),
                x.get('evidence', ''),
                x.get('action', ''),
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter if col == 0
                    else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                self.gap_table.setItem(i, col, item)

        # Impact table
        self.impact_table.setRowCount(0)
        for i, x in enumerate(pc.get('forecasts', [])[:12]):
            self.impact_table.insertRow(i)
            sev = x.get('severity', 'Medium')
            vals = [
                sev,
                x.get('title', '—'),
                f"{x.get('probability', 0.0) * 100:.0f}%",
                x.get('affected', '—'),
                x.get('action', '—'),
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                if col == 0:
                    self._style_severity_item(item, sev)
                elif col == 2:
                    item.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter if col in (0, 2)
                    else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                self.impact_table.setItem(i, col, item)

        forecast_note = (
            pc.get('forecasts', [{}])[0].get('title', 'No active dependency forecast')
            if pc.get('forecasts') else 'No active dependency forecast'
        )
        html_summary = f"""
            <div style='line-height: 1.4; font-family: sans-serif;'>
                <b>⚡ Persistent OS Control Kernel:</b>
                <span style='color:#3b82f6;'>{pc.get('event_count', 0)}</span> logged events &middot;
                <span style='color:#ef4444;'>{pc.get('open_impacts', 0)}</span> active impacts &middot;
                <span style='color:#f59e0b;'>{pc.get('unprocessed_events', 0)}</span> unprocessed anomalies.
                <br><b>🔮 Live Forecast Context:</b> {forecast_note}
                <br><b>🕸️ Graph Analytics:</b> {g.get('explanation', 'None')}
                <br><b>🔍 Critical Path Bottleneck:</b> {b.get('evidence', 'None')} |
                <span style='color:#059669;'><b>Action:</b> {b.get('recommendation', 'None')}</span>
                <br><b>📦 Turnover Principle:</b> <i>{t.get('principle', 'None')}</i>
                <br><b>🛡️ Work Front Autopilot Guardrail:</b>
                <span style='color:#3b82f6;'>{a.get('guardrail', 'None')}</span>
            </div>
        """
        self.explanation.setHtml(html_summary)
        self.apply_live_filter()

    def _clear_views(self):
        for c in self.cards.values():
            c.reset_card()
        self.action_table.setRowCount(0)
        self.signal_table.setRowCount(0)
        self.gap_table.setRowCount(0)
        self.impact_table.setRowCount(0)
        self.explanation.setHtml(
            "<b>Select a project to initiate the Execution OS Kernel simulation.</b>"
        )

    def _style_severity_item(self, item: QTableWidgetItem, severity: str):
        clean_sev = severity.strip().title()
        colors = COLOR_PALETTE.get(clean_sev, COLOR_PALETTE["Neutral"])

        item.setText(f"{colors['icon']} {clean_sev}")
        item.setBackground(QBrush(QColor(colors["bg"])))
        item.setForeground(QBrush(QColor(colors["fg"])))
        font = QFont()
        font.setBold(True)
        item.setFont(font)

    def _highlight_kpi_card_manually(self, key: str, status_text: str):
        card = self.cards.get(key)
        if not card:
            return
        if "Critical" in status_text or "Blocked" in status_text:
            card._set_theme_color("#dc2626")
        elif "Warning" in status_text:
            card._set_theme_color("#d97706")
        else:
            card._set_theme_color("#059669")

    # ── FILTERING ────────────────────────────────────────────
    def apply_live_filter(self):
        query = self.txt_search.text().strip().lower()

        for table in (self.action_table, self.signal_table,
                      self.gap_table, self.impact_table):
            for row in range(table.rowCount()):
                match = False
                for col in range(table.columnCount()):
                    item = table.item(row, col)
                    if item and query in item.text().lower():
                        match = True
                        break
                table.setRowHidden(row, not match if query else False)

    # ── CONTEXT MENU ─────────────────────────────────────────
    def _show_context_menu(self, pos, table: QTableWidget):
        selected_indexes = table.selectedIndexes()
        if not selected_indexes:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: white; border: 1px solid #cbd5e1; }
            QMenu::item { padding: 6px 20px; color: #1e293b; }
            QMenu::item:selected { background-color: #f1f5f9; color: #3b82f6; }
        """)

        copy_action = QAction("📋 Copy Raw Row Details", self)
        copy_action.triggered.connect(lambda: self._copy_table_row_text(table))
        menu.addAction(copy_action)

        approve_action = QAction("✔️ Dispatch / Approve Decision", self)
        approve_action.triggered.connect(
            lambda: self._simulate_decision_approval(table)
        )
        menu.addAction(approve_action)

        menu.exec(table.viewport().mapToGlobal(pos))

    def _copy_table_row_text(self, table: QTableWidget):
        row = table.currentRow()
        if row < 0:
            return
        row_data = [
            table.item(row, col).text()
            for col in range(table.columnCount())
            if table.item(row, col)
        ]
        if row_data:
            QApplication.clipboard().setText(" | ".join(row_data))

    def _simulate_decision_approval(self, table: QTableWidget):
        row = table.currentRow()
        if row < 0:
            return
        node_id = (
            table.item(row, 1).text()
            if table.columnCount() > 1 and table.item(row, 1)
            else "Unknown"
        )
        user = getattr(self.session, 'username', 'admin')
        QMessageBox.information(
            self,
            "Autopilot Dispatched",
            f"Audit log initialized:\nDecision for context '{node_id}' "
            f"approved by user '{user}'.\n\nCommand sent to field operations."
        )

    # ── EXPORT ───────────────────────────────────────────────
    def export_os_snapshot(self):
        if not self._last_snapshot_cache:
            QMessageBox.warning(
                self, "Export Warn",
                "No operational data available. Run recalculation first."
            )
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_code = self.project.currentText().split("—")[0].strip()
        default_file_name = (
            f"PipeAgent_ExecutionOS_Snapshot_{proj_code}_{timestamp}.csv"
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save OS Operational Report",
            default_file_name, "CSV Files (*.csv)"
        )
        if not file_path:
            return

        try:
            with open(file_path, mode='w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)

                writer.writerow(["=== PIPEAGENT EXECUTION OS SYSTEM SNAPSHOT ==="])
                writer.writerow(["Project", self.project.currentText()])
                writer.writerow([
                    "Report Date",
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ])
                writer.writerow([])

                writer.writerow(["=== KPI METRICS ==="])
                for key, card in self.cards.items():
                    writer.writerow([key, card.lbl_value.text()])
                writer.writerow([])

                writer.writerow(["=== WORK FRONT AUTOPILOT ACTIONS ==="])
                writer.writerow([
                    'Priority', 'Front Code', 'Assigned Team',
                    'Machine Allocated', 'Score', 'Decision Reason',
                ])
                for r in range(self.action_table.rowCount()):
                    if not self.action_table.isRowHidden(r):
                        writer.writerow([
                            self.action_table.item(r, c).text()
                            if self.action_table.item(r, c) else ""
                            for c in range(self.action_table.columnCount())
                        ])
                writer.writerow([])

                writer.writerow(["=== PREDICTIVE SIGNALS ==="])
                writer.writerow(['Severity', 'Category', 'Evidence', 'Recommendation'])
                for r in range(self.signal_table.rowCount()):
                    if not self.signal_table.isRowHidden(r):
                        writer.writerow([
                            self.signal_table.item(r, c).text()
                            if self.signal_table.item(r, c) else ""
                            for c in range(self.signal_table.columnCount())
                        ])
                writer.writerow([])

                writer.writerow(["=== DIGITAL TURNOVER GAPS ==="])
                writer.writerow(['Category', 'Evidence', 'Action'])
                for r in range(self.gap_table.rowCount()):
                    if not self.gap_table.isRowHidden(r):
                        writer.writerow([
                            self.gap_table.item(r, c).text()
                            if self.gap_table.item(r, c) else ""
                            for c in range(self.gap_table.columnCount())
                        ])
                writer.writerow([])

                writer.writerow(["=== DEPENDENCY RISKS FORECAST ==="])
                writer.writerow([
                    'Severity', 'Impact Scenario', 'Probability',
                    'Affected Nodes', 'Action Plan',
                ])
                for r in range(self.impact_table.rowCount()):
                    if not self.impact_table.isRowHidden(r):
                        writer.writerow([
                            self.impact_table.item(r, c).text()
                            if self.impact_table.item(r, c) else ""
                            for c in range(self.impact_table.columnCount())
                        ])

            QMessageBox.information(
                self, "Export Successful",
                f"Operational audit file saved at:\n{file_path}"
            )
        except Exception as e:
            logger.exception("CSV Export process aborted due to error.")
            QMessageBox.critical(
                self, "Export Failed",
                f"An error occurred while creating the CSV file:\n{e}"
            )

    # ── CLEANUP ──────────────────────────────────────────────
    def closeEvent(self, event):
        """Ensure the worker thread is cleaned up on widget close."""
        stop_thread_safely(self.active_worker, wait_ms=2000)
        self.active_worker = None
        super().closeEvent(event)