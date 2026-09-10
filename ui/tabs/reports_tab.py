# -*- coding: utf-8 -*-
# ui/tabs/reports_tab.py – Site reports, analytics, test requests, Excel/HTML export.
from __future__ import annotations

import csv
import logging
import datetime
from datetime import timezone
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal, QTimer, QDate
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QComboBox, QTabWidget,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QTextEdit, QDateEdit,
    QGroupBox, QGridLayout, QFrame, QProgressBar, QMenu,
    QApplication, QFileDialog, QAbstractItemView,
)
from PyQt6.QtGui import (
    QDesktopServices, QColor, QFont, QBrush, QAction, QCursor,
)

from db.manager import DatabaseManager
from db.models import Project, TestRequest
from security.session import SessionManager
from services.reporting_service import ReportingService
from services.license import increment_usage
from config import NDT_METHODS

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  UTIL
# ─────────────────────────────────────────────
def _utcnow():
    """Naive UTC — replacement for deprecated datetime.utcnow()."""
    return datetime.datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
REQUEST_TYPES = ["NDT", "Fit-up", "Visual", "Hydro", "Final Inspection", "Other"]
PRIORITIES = ["Low", "Normal", "High", "Urgent"]
REQ_STATUSES = ["Open", "Scheduled", "In Progress", "Completed", "Cancelled"]

PRIORITY_BADGES = {
    "Urgent": {"bg": "#fee2e2", "fg": "#991b1b", "icon": "🚨"},
    "High":   {"bg": "#fff1e6", "fg": "#9a3412", "icon": "🟠"},
    "Normal": {"bg": "#e0f2fe", "fg": "#075985", "icon": "🔵"},
    "Low":    {"bg": "#f1f5f9", "fg": "#475569", "icon": "⚪"},
}

STATUS_BADGES = {
    "Open":        {"bg": "#fef3c7", "fg": "#92400e", "icon": "🔓"},
    "Scheduled":   {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "📅"},
    "In Progress": {"bg": "#e0f2fe", "fg": "#075985", "icon": "🔄"},
    "Completed":   {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Cancelled":   {"bg": "#f1f5f9", "fg": "#475569", "icon": "❌"},
}

RESULT_BADGES = {
    "Pass":     {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Fail":     {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Pending":  {"bg": "#fef3c7", "fg": "#92400e", "icon": "⏳"},
    "Accepted": {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Rejected": {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
}

DEFAULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}


REPORTS_STYLESHEET = """
    QWidget#reportsTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #1e3c72, stop:1 #2a5298);
        border-radius: 12px; padding: 14px;
    }
    QLabel#mainTitle {
        color: #ffffff; font-size: 22px; font-weight: 800;
        font-family: 'Segoe UI', sans-serif;
    }
    QLabel#subTitle { color: #cbd5e1; font-size: 12px; }
    QFrame#kpiCard {
        background: white; border: 1px solid #cbd5e1;
        border-radius: 8px; padding: 10px;
    }
    QLabel#kpiTitle {
        font-size: 10px; font-weight: 700; color: #64748b;
        text-transform: uppercase;
    }
    QLabel#kpiValue { font-size: 18px; font-weight: 800; }
    QTableWidget {
        background: white; border: 1px solid #cbd5e1;
        border-radius: 6px; gridline-color: #f1f5f9; font-size: 12px;
    }
    QTableWidget::item:selected { background: #e0f2fe; color: #0369a1; }
    QHeaderView::section {
        background: #f8fafc; color: #334155;
        font-weight: 700; font-size: 11px; padding: 7px;
        border: none; border-bottom: 2px solid #cbd5e1;
        border-right: 1px solid #f1f5f9;
    }
    QPushButton#primaryBtn {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #3b82f6, stop:1 #2563eb);
        color: white; border: none; padding: 7px 15px;
        border-radius: 6px; font-weight: 700;
    }
    QPushButton#primaryBtn:hover {
        background: #1d4ed8;
    }
    QPushButton#primaryBtn:disabled { background: #94a3b8; }
    QPushButton#successBtn {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #10b981, stop:1 #059669);
        color: white; border: none; padding: 7px 15px;
        border-radius: 6px; font-weight: 700;
    }
    QPushButton#successBtn:hover { background: #047857; }
    QPushButton#secondaryBtn {
        background: white; color: #334155;
        border: 1px solid #cbd5e1;
        padding: 6px 12px; border-radius: 6px; font-weight: 600;
    }
    QPushButton#secondaryBtn:hover {
        background: #f8fafc; border-color: #3b82f6; color: #3b82f6;
    }
    QPushButton#dangerBtn {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #ef4444, stop:1 #dc2626);
        color: white; border: none; padding: 6px 12px;
        border-radius: 6px; font-weight: 700;
    }
    QPushButton#dangerBtn:hover { background: #b91c1c; }
    QLineEdit, QComboBox, QDateEdit, QTextEdit {
        padding: 6px 10px; border: 1px solid #cbd5e1;
        border-radius: 6px; font-size: 12px;
    }
"""


# ─────────────────────────────────────────────
#  ASYNC EXPORTER
# ─────────────────────────────────────────────
class AsyncReportExporter(QThread):
    """Non-blocking report exporter — prevents UI freezes on heavy files."""
    finished = pyqtSignal(bool, str)

    def __init__(self, svc: ReportingService, project_id: int,
                 export_type: str, custom_data=None):
        super().__init__()
        self.svc = svc
        self.project_id = project_id
        self.export_type = export_type
        self.custom_data = custom_data

    def run(self):
        try:
            if self.export_type == "excel_pack":
                ok, path = self.svc.export_excel(
                    self.custom_data,
                    f"PipeAgent_Reports_P{self.project_id}_"
                    f"{datetime.date.today().isoformat()}.xlsx",
                )
                self.finished.emit(ok, path)
            elif self.export_type == "html_executive":
                path = self.svc.project_executive_html(self.project_id)
                self.finished.emit(True, str(path))
        except Exception as e:
            logger.exception("Background report extraction aborted.")
            self.finished.emit(False, str(e))


# ─────────────────────────────────────────────
#  KPI CARD
# ─────────────────────────────────────────────
class ReportKPICard(QFrame):
    def __init__(self, title: str, value: str, color: str):
        super().__init__()
        self.setObjectName("kpiCard")
        self.setStyleSheet(
            f"QFrame {{ background: white; "
            f"border-left: 4px solid {color}; "
            f"border-radius: 8px; padding: 10px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)

        t = QLabel(title)
        t.setStyleSheet(
            "color: #64748b; font-size: 11px; font-weight: 600; "
            "text-transform: uppercase;"
        )
        lay.addWidget(t)

        self.v = QLabel(value)
        self.v.setStyleSheet(
            f"color: {color}; font-size: 20px; font-weight: 800;"
        )
        lay.addWidget(self.v)


# ─────────────────────────────────────────────
#  TEST REQUEST DIALOG
# ─────────────────────────────────────────────
class TestRequestDialog(QDialog):
    def __init__(self, parent=None, projects=None,
                 existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = existing_data is not None
        self.setWindowTitle(
            "Edit Test Request" if self.is_edit
            else "New Test / Inspection Request"
        )
        self.setMinimumWidth(480)
        self.setStyleSheet(REPORTS_STYLESHEET)

        layout = QFormLayout(self)
        layout.setSpacing(8)

        self.project_combo = QComboBox()
        if projects:
            for p in projects:
                self.project_combo.addItem(f"{p.project_code}", p.id)

        self.req_no = QLineEdit()
        self.req_no.setPlaceholderText("Auto-generated if left blank")

        self.rtype = QComboBox()
        self.rtype.addItems(REQUEST_TYPES)

        self.method = QComboBox()
        self.method.setEditable(True)
        self.method.addItems([""] + list(NDT_METHODS) + ["Hydro", "Pneumatic"])

        self.weld = QLineEdit()
        self.line = QLineEdit()
        self.spool = QLineEdit()
        self.iso = QLineEdit()
        self.location = QLineEdit()

        self.priority = QComboBox()
        self.priority.addItems(PRIORITIES)
        self.priority.setCurrentText("Normal")

        self.req_date = QDateEdit()
        self.req_date.setCalendarPopup(True)
        self.req_date.setDate(QDate.currentDate())

        self.due = QDateEdit()
        self.due.setCalendarPopup(True)
        self.due.setDate(QDate.currentDate().addDays(2))

        self.remarks = QTextEdit()
        self.remarks.setMaximumHeight(65)

        layout.addRow("Target Project *:", self.project_combo)
        layout.addRow("Requisition Number:", self.req_no)
        layout.addRow("Inspection Type *:", self.rtype)
        layout.addRow("Standard Method:", self.method)
        layout.addRow("Joint / Weld ID:", self.weld)
        layout.addRow("Piping Line Number *:", self.line)
        layout.addRow("Spool Identifier:", self.spool)
        layout.addRow("ISO Drawing Ref:", self.iso)
        layout.addRow("Execution Location:", self.location)
        layout.addRow("Request Priority:", self.priority)
        layout.addRow("Inspection Request Date:", self.req_date)
        layout.addRow("Target Due Date *:", self.due)
        layout.addRow("Engineering Remarks:", self.remarks)

        if self.is_edit and existing_data:
            pid = existing_data.get("project_id")
            for i in range(self.project_combo.count()):
                if self.project_combo.itemData(i) == pid:
                    self.project_combo.setCurrentIndex(i)
                    break
            self.req_no.setText(existing_data.get("request_no", ""))
            self.req_no.setReadOnly(True)
            self.rtype.setCurrentText(existing_data.get("type", "NDT"))
            self.method.setCurrentText(existing_data.get("method", ""))
            self.weld.setText(existing_data.get("weld_id", ""))
            self.line.setText(existing_data.get("line", ""))
            self.priority.setCurrentText(
                existing_data.get("priority", "Normal")
            )

            req_d = existing_data.get("request_date")
            if isinstance(req_d, datetime.date):
                self.req_date.setDate(QDate(req_d.year, req_d.month, req_d.day))

            due_d = existing_data.get("required_date")
            if isinstance(due_d, datetime.date):
                self.due.setDate(QDate(due_d.year, due_d.month, due_d.day))

            self.remarks.setPlainText(existing_data.get("remarks", ""))

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Request")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._validate_and_accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        layout.addRow(btns)

    def _validate_and_accept(self):
        if not self.line.text().strip():
            QMessageBox.warning(
                self, "Validation", "Piping Line Number is mandatory."
            )
            self.line.setFocus()
            return
        self.accept()

    def data(self):
        qd = self.req_date.date()
        dd = self.due.date()
        return {
            "project_id": self.project_combo.currentData(),
            "request_no": self.req_no.text().strip(),
            "request_type": self.rtype.currentText(),
            "method": self.method.currentText().strip(),
            "weld_id": self.weld.text().strip(),
            "line_number": self.line.text().strip(),
            "spool_number": self.spool.text().strip(),
            "iso_number": self.iso.text().strip(),
            "location": self.location.text().strip(),
            "priority": self.priority.currentText(),
            "request_date": datetime.date(qd.year(), qd.month(), qd.day()),
            "required_date": datetime.date(dd.year(), dd.month(), dd.day()),
            "remarks": self.remarks.toPlainText().strip(),
        }


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class ReportsTab(QWidget):
    def __init__(self, db: DatabaseManager, session: SessionManager):
        super().__init__()
        self.setObjectName("reportsTab")
        self.db = db
        self.session = session
        self.svc = ReportingService(db)
        self.project_id: Optional[int] = None
        self._exporter_thread: Optional[AsyncReportExporter] = None

        self._build()
        self.setStyleSheet(REPORTS_STYLESHEET)
        self._load_projects()

    # ── UI BUILD ─────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        header_card = QFrame()
        header_card.setObjectName("headerCard")
        hdr_lay = QHBoxLayout(header_card)
        hdr_lay.setContentsMargins(14, 10, 14, 10)

        title_v = QVBoxLayout()
        t = QLabel("📊 Project Reports & Advanced Analytics")
        t.setObjectName("mainTitle")
        s = QLabel(
            "Construction Progress Analytics, Joint Logs, NDT Coverage Matrix, "
            "Smart Operational Insights, and Requisitions."
        )
        s.setObjectName("subTitle")
        title_v.addWidget(t)
        title_v.addWidget(s)
        hdr_lay.addLayout(title_v, 1)

        proj_box = QHBoxLayout()
        lbl_p = QLabel("Project:")
        lbl_p.setStyleSheet("color: white; font-weight: bold;")
        proj_box.addWidget(lbl_p)

        self.proj = QComboBox()
        self.proj.setMinimumWidth(220)
        self.proj.currentIndexChanged.connect(self._proj_changed)
        proj_box.addWidget(self.proj)

        self.btn_x = QPushButton("📥 Excel Pack")
        self.btn_x.setObjectName("secondaryBtn")
        self.btn_x.clicked.connect(self._export_pack)
        proj_box.addWidget(self.btn_x)

        self.btn_html = QPushButton("📂 Executive Report")
        self.btn_html.setObjectName("primaryBtn")
        self.btn_html.clicked.connect(self._export_executive_html)
        proj_box.addWidget(self.btn_html)
        hdr_lay.addLayout(proj_box)

        root.addWidget(header_card)

        self.export_progress = QProgressBar()
        self.export_progress.setRange(0, 0)
        self.export_progress.setFixedHeight(6)
        self.export_progress.setTextVisible(False)
        self.export_progress.setVisible(False)
        root.addWidget(self.export_progress)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_analytics_tab(), "📈 Dashboard & Welder KPI")
        self.tabs.addTab(self._build_insights_tab(), "💡 Smart Quality Insights")
        self.tabs.addTab(self._build_weld_log_tab(), "🔥 Weld Production Log")
        self.tabs.addTab(self._build_fitup_tab(), "🔧 Fit-up Report")
        self.tabs.addTab(self._build_ndt_tab(), "🛡️ NDT Quality Matrix")
        self.tabs.addTab(self._build_front_tab(), "🧱 Site Work Fronts")
        self.tabs.addTab(self._build_requests_tab(), "📋 Requisitions")
        root.addWidget(self.tabs, 1)

    def _setup_table_style(self, table: QTableWidget):
        table.setAlternatingRowColors(True)
        # ✅ FIXED: use QAbstractItemView enums
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

    def _apply_badge_to_cell(self, item: QTableWidgetItem, text: str,
                             badge_source: dict):
        badge = badge_source.get(text, DEFAULT_BADGE)
        item.setText(f"{badge['icon']} {text}")
        item.setBackground(QBrush(QColor(badge["bg"])))
        item.setForeground(QBrush(QColor(badge["fg"])))
        f = item.font()
        f.setBold(True)
        item.setFont(f)

    # ══════════════════════════════════════════════════════
    #  PROJECT LOADING
    # ══════════════════════════════════════════════════════
    def _load_projects(self):
        current = self.proj.currentData()
        self.proj.blockSignals(True)
        self.proj.clear()

        try:
            with self.db.session_scope() as s:
                projects = (
                    s.query(Project).order_by(Project.project_code).all()
                )
                for p in projects:
                    self.proj.addItem(
                        f"{p.project_code} – {p.title}", p.id
                    )
        except Exception as e:
            logger.exception("ReportsTab: failed to load projects")
            QMessageBox.warning(
                self, "Error", f"Could not load projects:\n{e}"
            )
        finally:
            self.proj.blockSignals(False)

        if current is not None:
            idx = self.proj.findData(current)
            if idx >= 0:
                self.proj.setCurrentIndex(idx)

        if self.proj.count():
            self._proj_changed()

    def _proj_changed(self):
        self.project_id = self.proj.currentData()
        if self.project_id:
            try:
                self.refresh()
            except Exception:
                logger.exception(
                    "ReportsTab: refresh on project change failed"
                )
        else:
            self.welder_table.setRowCount(0)
            self.insight_table.setRowCount(0)
            self.weld_table.setRowCount(0)
            self.fit_table.setRowCount(0)
            self.ndt_table.setRowCount(0)
            self.q_fitup.setRowCount(0)
            self.q_weld.setRowCount(0)
            self.q_ndt.setRowCount(0)
            self.q_spool.setRowCount(0)
            self.q_sup.setRowCount(0)
            self.q_test.setRowCount(0)
            self.req_table.setRowCount(0)

    # ══════════════════════════════════════════════════════
    #  1. ANALYTICS & WELDER KPI
    # ══════════════════════════════════════════════════════
    def _build_analytics_tab(self) -> QWidget:
        self.an_panel = QWidget()
        lay = QVBoxLayout(self.an_panel)
        lay.setContentsMargins(8, 10, 8, 8)

        self.kpi_grid = QGridLayout()
        self.kpi_grid.setSpacing(8)
        lay.addLayout(self.kpi_grid)

        box = QGroupBox("👨‍🏭 WELDER PERFORMANCE & REPAIR DEFECT RATES")
        box_lay = QVBoxLayout(box)

        self.welder_table = QTableWidget(0, 4)
        self.welder_table.setHorizontalHeaderLabels([
            "Welder Stamp / ID", "Total Joints Welded",
            "Accepted Joints", "Repaired Cut-outs",
        ])
        self._setup_table_style(self.welder_table)
        box_lay.addWidget(self.welder_table)

        btn_ra = QPushButton("Refresh Performance Metrics")
        btn_ra.setObjectName("secondaryBtn")
        btn_ra.clicked.connect(self._load_analytics)
        box_lay.addWidget(btn_ra)

        lay.addWidget(box, 1)
        return self.an_panel

    def _load_analytics(self):
        while self.kpi_grid.count():
            item = self.kpi_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.welder_table.setRowCount(0)
        if not self.project_id:
            return

        try:
            a = self.svc.analytics(self.project_id)
            w = a["welds"]
            cards = [
                ("Total Joints Welded", str(w["total"]), "#3498db"),
                ("Joint Acceptance Rate",
                 f"{w['acceptance_rate_pct']}%", "#27ae60"),
                ("NDT Failure Rate",
                 f"{w['rejection_rate_pct']}%", "#e74c3c"),
                ("Repair Rate (Cut-out)",
                 f"{w['repair_rate_pct']}%", "#f39c12"),
                ("NDT Method Pass %",
                 f"{a['ndt']['pass_rate_pct']}%", "#1abc9c"),
                ("Spools Erected",
                 f"{a['spools']['installed']}/{a['spools']['total']}",
                 "#8e44ad"),
                ("Test Packages Passed",
                 f"{a['test_packages']['passed']}/"
                 f"{a['test_packages']['total']}", "#2980b9"),
                ("Line List Scope Volume", f"{a['lines']} Lines", "#34495e"),
            ]
            for i, (t, v, c) in enumerate(cards):
                self.kpi_grid.addWidget(ReportKPICard(t, v, c), i // 4, i % 4)

            self.welder_table.setSortingEnabled(False)
            for welder, st in sorted(a["by_welder"].items()):
                r = self.welder_table.rowCount()
                self.welder_table.insertRow(r)
                self.welder_table.setItem(r, 0, QTableWidgetItem(welder))
                self.welder_table.setItem(r, 1, QTableWidgetItem(
                    str(st["total"])
                ))
                self.welder_table.setItem(r, 2, QTableWidgetItem(
                    str(st["accepted"])
                ))

                rep_cnt = st["repaired"]
                rep_item = QTableWidgetItem(str(rep_cnt))
                if rep_cnt > 0:
                    rep_item.setForeground(QBrush(QColor("#991b1b")))
                    f = rep_item.font()
                    f.setBold(True)
                    rep_item.setFont(f)
                self.welder_table.setItem(r, 3, rep_item)
            self.welder_table.setSortingEnabled(True)
        except Exception:
            logger.exception("Failed to load analytics dashboard")

    # ══════════════════════════════════════════════════════
    #  2. SMART QUALITY INSIGHTS
    # ══════════════════════════════════════════════════════
    def _build_insights_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 8)

        self.insight_summary = QLabel(
            "Select a project to generate evidence-based operational hints."
        )
        self.insight_summary.setWordWrap(True)
        self.insight_summary.setStyleSheet(
            "background:#fff8e6; padding:10px; border:1px solid #fef3c7; "
            "border-radius:6px; color:#92400e;"
        )
        lay.addWidget(self.insight_summary)

        self.insight_table = QTableWidget(0, 5)
        self.insight_table.setHorizontalHeaderLabels([
            "Threat Level / Severity", "Quality Class",
            "Diagnostic Finding", "System Evidence",
            "Recommended Corrective Action",
        ])
        self._setup_table_style(self.insight_table)
        lay.addWidget(self.insight_table)

        ib = QHBoxLayout()
        bi = QPushButton("Generate Deterministic Quality Hints")
        bi.setObjectName("primaryBtn")
        bi.clicked.connect(self._load_insights)
        ib.addWidget(bi)

        bs = QPushButton("Save to Quality Control History")
        bs.setObjectName("secondaryBtn")
        bs.clicked.connect(self._save_insights)
        ib.addWidget(bs)
        ib.addStretch()
        lay.addLayout(ib)
        return w

    def _load_insights(self):
        self.insight_table.setSortingEnabled(False)
        self.insight_table.setRowCount(0)
        if not self.project_id:
            return

        try:
            hints = self.svc.smart_hints(self.project_id)
            self.insight_table.setRowCount(len(hints))
            for r, h in enumerate(hints):
                sev = h.get("severity", "Medium")
                sev_item = QTableWidgetItem(sev)
                self._apply_badge_to_cell(sev_item, sev, PRIORITY_BADGES)
                self.insight_table.setItem(r, 0, sev_item)

                self.insight_table.setItem(r, 1, QTableWidgetItem(
                    str(h.get("category", ""))
                ))
                self.insight_table.setItem(r, 2, QTableWidgetItem(
                    str(h.get("title", ""))
                ))
                self.insight_table.setItem(r, 3, QTableWidgetItem(
                    str(h.get("evidence", ""))
                ))
                self.insight_table.setItem(r, 4, QTableWidgetItem(
                    str(h.get("recommendation", ""))
                ))

            self.insight_table.setSortingEnabled(True)
            high = sum(1 for h in hints if h["severity"] == "High")
            medium = sum(1 for h in hints if h["severity"] == "Medium")
            self.insight_summary.setText(
                f"<b>Piping Quality Intelligence Engine:</b> "
                f"{len(hints)} current anomalies detected &middot; "
                f"<span style='color:#991b1b; font-weight:bold;'>"
                f"{high} Critical Threat(s)</span> &middot; "
                f"{medium} Moderate. All diagnostic rules are "
                f"deterministically auditable."
            )
        except Exception:
            logger.exception("Failed to load quality insights")

    def _save_insights(self):
        if not self.project_id:
            return
        hints = self.svc.save_smart_hints(self.project_id)
        QMessageBox.information(
            self, "Audit Logged",
            f"Registered {len(hints)} active quality findings "
            f"into the permanent project history log.",
        )

    # ══════════════════════════════════════════════════════
    #  3. WELD LOG
    # ══════════════════════════════════════════════════════
    def _build_weld_log_tab(self) -> QWidget:
        w = QWidget()
        wl = QVBoxLayout(w)
        wl.setContentsMargins(8, 10, 8, 8)
        wl.setSpacing(6)

        wh = QHBoxLayout()
        self.weld_filter = QComboBox()
        self.weld_filter.addItems(["All", "Shop", "Field"])
        wh.addWidget(QLabel("Location Type:"))
        wh.addWidget(self.weld_filter)

        self.txt_weld_search = QLineEdit()
        self.txt_weld_search.setPlaceholderText(
            "🔍 Filter Weld Log (Weld ID, Line, Welder)..."
        )
        self.txt_weld_search.textChanged.connect(self._filter_weld_log)
        wh.addWidget(self.txt_weld_search, 1)

        btn_rw = QPushButton("Refresh")
        btn_rw.setObjectName("secondaryBtn")
        btn_rw.clicked.connect(self._load_weld_log)
        wh.addWidget(btn_rw)

        btn_cw = QPushButton("Export CSV")
        btn_cw.setObjectName("secondaryBtn")
        btn_cw.clicked.connect(lambda: self._export_csv("weld"))
        wh.addWidget(btn_cw)
        wl.addLayout(wh)

        self.weld_table = QTableWidget()
        self._setup_table_style(self.weld_table)
        wl.addWidget(self.weld_table)
        return w

    def _load_weld_log(self):
        if not self.project_id:
            return
        try:
            wt = self.weld_filter.currentText()
            rows = self.svc.weld_log(
                self.project_id,
                weld_type=None if wt == "All" else wt,
            )
            cols = [
                ("weld_id", "Weld ID"), ("weld_type", "Type"),
                ("line_number", "Line"), ("joint_type", "Joint"),
                ("size", "Size"), ("welder_id", "Welder"),
                ("status", "Status"), ("repair_count", "Repairs"),
                ("fitup_date", "Fit-up Date"),
            ]
            _fill_table(self.weld_table, rows, cols)
            self._filter_weld_log()
        except Exception:
            logger.exception("Failed to load weld log")

    def _filter_weld_log(self):
        query = self.txt_weld_search.text().strip().lower()
        for r in range(self.weld_table.rowCount()):
            w_id = (self.weld_table.item(r, 0).text().lower()
                    if self.weld_table.item(r, 0) else "")
            line = (self.weld_table.item(r, 2).text().lower()
                    if self.weld_table.item(r, 2) else "")
            welder = (self.weld_table.item(r, 5).text().lower()
                      if self.weld_table.item(r, 5) else "")
            match = query in w_id or query in line or query in welder
            self.weld_table.setRowHidden(r, not match)

    # ══════════════════════════════════════════════════════
    #  4. FIT-UP REPORT
    # ══════════════════════════════════════════════════════
    def _build_fitup_tab(self) -> QWidget:
        w = QWidget()
        fl = QVBoxLayout(w)
        fl.setContentsMargins(8, 10, 8, 8)
        fl.setSpacing(6)

        fh = QHBoxLayout()
        self.txt_fitup_search = QLineEdit()
        self.txt_fitup_search.setPlaceholderText(
            "🔍 Filter Fit-up Log (Weld ID, Line, Inspector)..."
        )
        self.txt_fitup_search.textChanged.connect(self._filter_fitup_log)
        fh.addWidget(self.txt_fitup_search, 1)

        btn_rf = QPushButton("Refresh")
        btn_rf.setObjectName("secondaryBtn")
        btn_rf.clicked.connect(self._load_fitup)
        fh.addWidget(btn_rf)

        btn_cf = QPushButton("Export CSV")
        btn_cf.setObjectName("secondaryBtn")
        btn_cf.clicked.connect(lambda: self._export_csv("fitup"))
        fh.addWidget(btn_cf)
        fl.addLayout(fh)

        self.fit_table = QTableWidget()
        self._setup_table_style(self.fit_table)
        fl.addWidget(self.fit_table)
        return w

    def _load_fitup(self):
        if not self.project_id:
            return
        try:
            rows = self.svc.fitup_report(self.project_id)
            cols = [
                ("weld_id", "Weld ID"), ("line_number", "Line"),
                ("joint_type", "Joint"), ("size", "Size"),
                ("fitup_inspector", "Inspector"), ("fitup_date", "Date"),
                ("current_status", "Status"), ("welder_id", "Welder"),
            ]
            _fill_table(self.fit_table, rows, cols)
            self._filter_fitup_log()
        except Exception:
            logger.exception("Failed to load fitup log")

    def _filter_fitup_log(self):
        query = self.txt_fitup_search.text().strip().lower()
        for r in range(self.fit_table.rowCount()):
            w_id = (self.fit_table.item(r, 0).text().lower()
                    if self.fit_table.item(r, 0) else "")
            line = (self.fit_table.item(r, 1).text().lower()
                    if self.fit_table.item(r, 1) else "")
            inspector = (self.fit_table.item(r, 4).text().lower()
                         if self.fit_table.item(r, 4) else "")
            match = query in w_id or query in line or query in inspector
            self.fit_table.setRowHidden(r, not match)

    # ══════════════════════════════════════════════════════
    #  5. NDT MATRIX
    # ══════════════════════════════════════════════════════
    def _build_ndt_tab(self) -> QWidget:
        w = QWidget()
        nl = QVBoxLayout(w)
        nl.setContentsMargins(8, 10, 8, 8)
        nl.setSpacing(6)

        nh = QHBoxLayout()
        self.txt_ndt_search = QLineEdit()
        self.txt_ndt_search.setPlaceholderText(
            "🔍 Filter NDT Matrix (Weld ID, Line)..."
        )
        self.txt_ndt_search.textChanged.connect(self._filter_ndt_log)
        nh.addWidget(self.txt_ndt_search, 1)

        btn_rn = QPushButton("Refresh")
        btn_rn.setObjectName("secondaryBtn")
        btn_rn.clicked.connect(self._load_ndt)
        nh.addWidget(btn_rn)

        btn_cn = QPushButton("Export CSV")
        btn_cn.setObjectName("secondaryBtn")
        btn_cn.clicked.connect(lambda: self._export_csv("ndt"))
        nh.addWidget(btn_cn)
        nl.addLayout(nh)

        self.ndt_table = QTableWidget()
        self._setup_table_style(self.ndt_table)
        nl.addWidget(self.ndt_table)
        return w

    def _load_ndt(self):
        if not self.project_id:
            return
        try:
            rows = self.svc.ndt_matrix(self.project_id)
            cols = [
                ("weld_id", "Weld ID"), ("line_number", "Line"),
                ("status", "Weld Status"), ("VT", "VT"), ("PT", "PT"),
                ("MT", "MT"), ("RT", "RT"), ("UT", "UT"),
            ]
            _fill_table(self.ndt_table, rows, cols)
            self._filter_ndt_log()
        except Exception:
            logger.exception("Failed to load NDT matrix")

    def _filter_ndt_log(self):
        query = self.txt_ndt_search.text().strip().lower()
        for r in range(self.ndt_table.rowCount()):
            w_id = (self.ndt_table.item(r, 0).text().lower()
                    if self.ndt_table.item(r, 0) else "")
            line = (self.ndt_table.item(r, 1).text().lower()
                    if self.ndt_table.item(r, 1) else "")
            match = query in w_id or query in line
            self.ndt_table.setRowHidden(r, not match)

    # ══════════════════════════════════════════════════════
    #  6. SITE FRONT WORK
    # ══════════════════════════════════════════════════════
    def _build_front_tab(self) -> QWidget:
        self.front_panel = QWidget()
        fr = QVBoxLayout(self.front_panel)
        fr.setContentsMargins(8, 10, 8, 8)

        self.front_summary = QLabel("")
        self.front_summary.setWordWrap(True)
        self.front_summary.setStyleSheet(
            "background:#eef5ff; border:1px solid #dbeafe; padding:10px; "
            "border-radius:6px; color:#1e40af;"
        )
        fr.addWidget(self.front_summary)

        self.front_tabs = QTabWidget()
        self.q_fitup = QTableWidget()
        self.q_weld = QTableWidget()
        self.q_ndt = QTableWidget()
        self.q_spool = QTableWidget()
        self.q_sup = QTableWidget()
        self.q_test = QTableWidget()

        for t, title in [
            (self.q_fitup, "Awaiting Fit-up"),
            (self.q_weld, "Ready to Weld"),
            (self.q_ndt, "Awaiting NDT"),
            (self.q_spool, "Spools to Install"),
            (self.q_sup, "Supports Pending"),
            (self.q_test, "Tests Pending"),
        ]:
            self._setup_table_style(t)
            self.front_tabs.addTab(t, title)

        fr.addWidget(self.front_tabs)

        btn_rf2 = QPushButton("Refresh Construction Front Queues")
        btn_rf2.setObjectName("secondaryBtn")
        btn_rf2.clicked.connect(self._load_front)
        fr.addWidget(btn_rf2)
        return self.front_panel

    def _load_front(self):
        if not self.project_id:
            self.front_summary.setText("Select a project.")
            return

        try:
            data = self.svc.site_front_work(self.project_id)
            c = data["counts"]
            q = data["queues"]
            self.front_summary.setText(
                f"<b>Construction Front Dashboard:</b> "
                f"Welds {c['welds_accepted']}/{c['welds_total']} accepted &middot; "
                f"Spools {c['spools_installed']}/{c['spools_total']} installed &middot; "
                f"Supports {c['supports_done']}/{c['supports_total']} verified. "
                f"<br>Outstanding: Fit-up {len(q['awaiting_fitup'])} &middot; "
                f"Ready weld {len(q['ready_to_weld'])} &middot; "
                f"NDT {len(q['awaiting_ndt'])} &middot; "
                f"Spools {len(q['spools_to_install'])} &middot; "
                f"Supports {len(q['supports_pending'])} &middot; "
                f"Tests {len(q['tests_pending'])}"
            )
            _fill_table(self.q_fitup, q["awaiting_fitup"], [
                ("weld_id", "Weld ID"), ("line", "Piping Line"),
                ("type", "Erection Area"),
            ])
            _fill_table(self.q_weld, q["ready_to_weld"], [
                ("weld_id", "Weld ID"), ("line", "Piping Line"),
                ("welder", "Welder"),
            ])
            _fill_table(self.q_ndt, q["awaiting_ndt"], [
                ("weld_id", "Weld ID"), ("line", "Piping Line"),
                ("status", "Quality Status"),
            ])
            _fill_table(self.q_spool, q["spools_to_install"], [
                ("spool", "Spool No"), ("line", "Piping Line"),
                ("status", "Installation Status"),
            ])
            _fill_table(self.q_sup, q["supports_pending"], [
                ("tag", "Support Tag"), ("line", "Piping Line"),
                ("type", "Support Type"),
            ])
            _fill_table(self.q_test, q["tests_pending"], [
                ("pkg", "Hydro Package ID"), ("status", "Test Status"),
                ("pressure", "Design P"),
            ])
        except Exception:
            logger.exception("Failed to load front construction queues")

    # ══════════════════════════════════════════════════════
    #  7. REQUISITIONS
    # ══════════════════════════════════════════════════════
    def _build_requests_tab(self) -> QWidget:
        req_box = QWidget()
        rl = QVBoxLayout(req_box)
        rl.setContentsMargins(8, 10, 8, 8)
        rl.setSpacing(6)

        rh = QHBoxLayout()
        self.txt_req_search = QLineEdit()
        self.txt_req_search.setPlaceholderText(
            "🔍 Filter Requests (Req No, Joint, Line)..."
        )
        self.txt_req_search.textChanged.connect(self._filter_requests)
        rh.addWidget(self.txt_req_search, 1)

        btn_nr = QPushButton("➕ Raise Request")
        btn_nr.setObjectName("primaryBtn")
        btn_nr.clicked.connect(self._new_request)
        rh.addWidget(btn_nr)

        btn_rr = QPushButton("Refresh")
        btn_rr.setObjectName("secondaryBtn")
        btn_rr.clicked.connect(self._load_requests)
        rh.addWidget(btn_rr)

        rh.addWidget(QLabel("Change Status →"))
        self.req_st = QComboBox()
        self.req_st.addItems(REQ_STATUSES)
        rh.addWidget(self.req_st)

        btn_as = QPushButton("Apply Status")
        btn_as.setObjectName("secondaryBtn")
        btn_as.clicked.connect(self._req_status)
        rh.addWidget(btn_as)

        btn_del_req = QPushButton("🗑️")
        btn_del_req.setObjectName("dangerBtn")
        btn_del_req.setToolTip("Delete Selected Request")
        btn_del_req.clicked.connect(self._delete_request)
        rh.addWidget(btn_del_req)

        rl.addLayout(rh)

        self.req_table = QTableWidget()
        self._setup_table_style(self.req_table)
        self.req_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.req_table.doubleClicked.connect(self._edit_selected_request)
        self.req_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.req_table.customContextMenuRequested.connect(
            self._show_request_context_menu
        )
        rl.addWidget(self.req_table)
        return req_box

    def _load_requests(self):
        self.req_table.setRowCount(0)
        if not self.project_id:
            return

        try:
            with self.db.session_scope() as s:
                rows = (
                    s.query(TestRequest)
                    .filter(TestRequest.project_id == self.project_id)
                    .order_by(
                        TestRequest.request_date.desc(),
                        TestRequest.id.desc(),
                    )
                    .all()
                )
                data = [
                    {
                        "id": r.id,
                        "project_id": r.project_id,
                        "request_no": r.request_no,
                        "type": r.request_type,
                        "method": r.method or "",
                        "weld_id": r.weld_id or "",
                        "line": r.line_number or "",
                        "spool_number": getattr(r, "spool_number", "") or "",
                        "iso_number": getattr(r, "iso_number", "") or "",
                        "location": getattr(r, "location", "") or "",
                        "priority": r.priority or "Normal",
                        "status": r.status or "Open",
                        "request_date": r.request_date,
                        "required_date": r.required_date,
                        "remarks": getattr(r, "remarks", "") or "",
                        "by": r.requested_by or "",
                    }
                    for r in rows
                ]

            self.req_table.setSortingEnabled(False)
            self.req_table.setColumnCount(10)
            self.req_table.setHorizontalHeaderLabels([
                "ID", "Request No", "Type", "Method", "Weld ID",
                "Line", "Priority", "Status", "Required", "Requested By",
            ])
            self.req_table.setColumnHidden(0, True)

            for i, row in enumerate(data):
                self.req_table.insertRow(i)
                self.req_table.setItem(i, 0, QTableWidgetItem(str(row["id"])))
                self.req_table.item(i, 0).setData(
                    Qt.ItemDataRole.UserRole, row["id"]
                )

                self.req_table.setItem(i, 1, QTableWidgetItem(row["request_no"]))
                self.req_table.setItem(i, 2, QTableWidgetItem(row["type"]))
                self.req_table.setItem(i, 3, QTableWidgetItem(row["method"]))
                self.req_table.setItem(i, 4, QTableWidgetItem(row["weld_id"]))
                self.req_table.setItem(i, 5, QTableWidgetItem(row["line"]))

                p_item = QTableWidgetItem(row["priority"])
                self._apply_badge_to_cell(
                    p_item, row["priority"], PRIORITY_BADGES
                )
                self.req_table.setItem(i, 6, p_item)

                st_item = QTableWidgetItem(row["status"])
                self._apply_badge_to_cell(
                    st_item, row["status"], STATUS_BADGES
                )
                self.req_table.setItem(i, 7, st_item)

                self.req_table.setItem(i, 8, QTableWidgetItem(
                    str(row["required_date"] or "")
                ))
                self.req_table.setItem(i, 9, QTableWidgetItem(row["by"]))

            self.req_table.setSortingEnabled(True)
            self._filter_requests()
        except Exception:
            logger.exception("Failed to load requisitions list")

    def _filter_requests(self):
        query = self.txt_req_search.text().strip().lower()
        for r in range(self.req_table.rowCount()):
            req_no = (self.req_table.item(r, 1).text().lower()
                      if self.req_table.item(r, 1) else "")
            w_id = (self.req_table.item(r, 4).text().lower()
                    if self.req_table.item(r, 4) else "")
            line = (self.req_table.item(r, 5).text().lower()
                    if self.req_table.item(r, 5) else "")
            match = query in req_no or query in w_id or query in line
            self.req_table.setRowHidden(r, not match)

    def _new_request(self):
        with self.db.session_scope() as s:
            projects = [
                type("P", (), {"id": p.id, "project_code": p.project_code})()
                for p in s.query(Project).order_by(Project.project_code)
            ]
        if not projects:
            QMessageBox.information(self, "Info", "Register a project first.")
            return

        dlg = TestRequestDialog(self, projects)
        if self.project_id:
            for i in range(dlg.project_combo.count()):
                if dlg.project_combo.itemData(i) == self.project_id:
                    dlg.project_combo.setCurrentIndex(i)
                    break
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.data()
        if not d["project_id"]:
            return
        if not increment_usage(self.db):
            QMessageBox.warning(
                self, "License Limit",
                "Inspection requisition limit reached under current license."
            )
            return

        # ✅ FIXED: datetime.datetime.now() ok
        req_no = (
            d["request_no"]
            or f"TR-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        user = getattr(self.session, "username", "admin")
        try:
            with self.db.session_scope() as s:
                s.add(TestRequest(
                    project_id=d["project_id"],
                    request_no=req_no,
                    request_type=d["request_type"],
                    method=d["method"],
                    weld_id=d["weld_id"],
                    line_number=d["line_number"],
                    spool_number=d["spool_number"],
                    iso_number=d["iso_number"],
                    location=d["location"],
                    priority=d["priority"],
                    request_date=d["request_date"],
                    required_date=d["required_date"],
                    requested_by=user,
                    status="Open",
                    remarks=d["remarks"],
                    # ✅ FIXED: use _utcnow() helper
                    created_at=_utcnow(),
                ))
            self._load_requests()
            QMessageBox.information(
                self, "Success",
                f"Requisition '{req_no}' registered successfully."
            )
        except Exception as e:
            logger.exception("Failed to create inspection request")
            QMessageBox.critical(
                self, "Error", f"Failed to save request:\n{e}"
            )

    def _edit_selected_request(self, index=None):
        rows = self.req_table.selectionModel().selectedRows()
        if not rows:
            return
        rid = int(self.req_table.item(rows[0].row(), 0).text())

        with self.db.session_scope() as s:
            # ✅ FIXED: SQLAlchemy 2.0 — s.get(Model, pk)
            r = s.get(TestRequest, rid)
            if not r:
                return
            existing_data = {
                "id": r.id,
                "project_id": r.project_id,
                "request_no": r.request_no,
                "type": r.request_type,
                "method": r.method,
                "weld_id": r.weld_id,
                "line": r.line_number,
                "spool_number": getattr(r, "spool_number", ""),
                "iso_number": getattr(r, "iso_number", ""),
                "location": getattr(r, "location", ""),
                "priority": r.priority,
                "request_date": r.request_date,
                "required_date": r.required_date,
                "remarks": getattr(r, "remarks", ""),
            }
            projects = [
                type("P", (), {"id": p.id, "project_code": p.project_code})()
                for p in s.query(Project).order_by(Project.project_code)
            ]

        dlg = TestRequestDialog(
            self, projects=projects, existing_data=existing_data
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.data()
        try:
            with self.db.session_scope() as s:
                # ✅ FIXED: s.get()
                obj = s.get(TestRequest, rid)
                if obj:
                    obj.request_type = d["request_type"]
                    obj.method = d["method"]
                    obj.weld_id = d["weld_id"]
                    obj.line_number = d["line_number"]
                    obj.spool_number = d["spool_number"]
                    obj.iso_number = d["iso_number"]
                    obj.location = d["location"]
                    obj.priority = d["priority"]
                    obj.request_date = d["request_date"]
                    obj.required_date = d["required_date"]
                    obj.remarks = d["remarks"]
            self._load_requests()
            QMessageBox.information(
                self, "Updated",
                f"Requisition '{existing_data['request_no']}' specs updated."
            )
        except Exception as e:
            logger.exception("Failed to edit test request")
            QMessageBox.critical(self, "Error", f"Update failed:\n{e}")

    def _delete_request(self):
        rows = self.req_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select one or more requisitions to delete."
            )
            return

        r_ids = [int(self.req_table.item(r.row(), 0).text()) for r in rows]
        r_nos = [self.req_table.item(r.row(), 1).text() for r in rows]

        if QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(r_ids)} inspection requisition(s)?\n\n"
            f"Requests: {', '.join(r_nos[:5])}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as s:
                for rid in r_ids:
                    # ✅ FIXED: SQLAlchemy 2.0
                    obj = s.get(TestRequest, rid)
                    if obj:
                        s.delete(obj)
            self._load_requests()
            QMessageBox.information(
                self, "Deleted", "Selected requisitions deleted."
            )
        except Exception as e:
            logger.exception("Failed to delete test requests")
            QMessageBox.critical(self, "Error", f"Delete failed:\n{e}")

    def _req_status(self):
        rows = self.req_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection", "Select at least one requisition."
            )
            return

        new_st = self.req_st.currentText()
        ids = [int(self.req_table.item(r.row(), 0).text()) for r in rows]
        try:
            with self.db.session_scope() as s:
                for rid in ids:
                    # ✅ FIXED
                    obj = s.get(TestRequest, rid)
                    if obj:
                        obj.status = new_st
                        if new_st == "Completed":
                            obj.completed_date = datetime.date.today()
            self._load_requests()
            QMessageBox.information(
                self, "Status Applied",
                f"Updated status to '{new_st}' for {len(ids)} requisition(s)."
            )
        except Exception:
            logger.exception("Failed to update status")

    def _show_request_context_menu(self, pos):
        rows = self.req_table.selectionModel().selectedRows()
        if not rows:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 18px; }"
        )

        act_edit = QAction("✏️ Edit Requisition Specs", self)
        act_edit.triggered.connect(self._edit_selected_request)
        menu.addAction(act_edit)

        menu.addSeparator()
        act_del = QAction("🗑️ Delete Requisition", self)
        act_del.triggered.connect(self._delete_request)
        menu.addAction(act_del)
        menu.exec(self.req_table.viewport().mapToGlobal(pos))

    # ══════════════════════════════════════════
    #  EXPORTS
    # ══════════════════════════════════════════
    def _export_pack(self):
        if not self.project_id:
            QMessageBox.warning(
                self, "Export", "Select a project first."
            )
            return

        self.btn_x.setEnabled(False)
        self.export_progress.setVisible(True)

        # ✅ FIXED: cleanup previous thread
        if self._exporter_thread is not None:
            try:
                if self._exporter_thread.isRunning():
                    self._exporter_thread.wait(2000)
                self._exporter_thread.deleteLater()
            except Exception:
                pass
            self._exporter_thread = None

        sheets = {
            "Weld Log": self.svc.weld_log(self.project_id),
            "Fit-up": self.svc.fitup_report(self.project_id),
            "NDT Matrix": self.svc.ndt_matrix(self.project_id),
        }

        self._exporter_thread = AsyncReportExporter(
            self.svc, self.project_id, "excel_pack", custom_data=sheets
        )
        self._exporter_thread.finished.connect(self._on_excel_export_complete)
        self._exporter_thread.start()

    def _on_excel_export_complete(self, ok: bool, path: str):
        self.btn_x.setEnabled(True)
        self.export_progress.setVisible(False)
        if ok:
            QMessageBox.information(
                self, "Excel Pack Exported",
                f"Successfully compiled and saved target "
                f"report package:\n{path}"
            )
        else:
            QMessageBox.critical(
                self, "Export Failed",
                f"Failed to generate Excel package:\n{path}"
            )
        if self._exporter_thread is not None:
            self._exporter_thread.deleteLater()
            self._exporter_thread = None

    def _export_executive_html(self):
        if not self.project_id:
            QMessageBox.information(
                self, "Project", "Select a project first."
            )
            return

        self.btn_html.setEnabled(False)
        self.export_progress.setVisible(True)

        # ✅ FIXED: cleanup previous thread
        if self._exporter_thread is not None:
            try:
                if self._exporter_thread.isRunning():
                    self._exporter_thread.wait(2000)
                self._exporter_thread.deleteLater()
            except Exception:
                pass
            self._exporter_thread = None

        self._exporter_thread = AsyncReportExporter(
            self.svc, self.project_id, "html_executive"
        )
        self._exporter_thread.finished.connect(self._on_html_export_complete)
        self._exporter_thread.start()

    def _on_html_export_complete(self, ok: bool, path: str):
        self.btn_html.setEnabled(True)
        self.export_progress.setVisible(False)
        if ok:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            QMessageBox.information(
                self, "Executive HTML Report",
                f"Report compiled & opened successfully:\n{path}"
            )
        else:
            QMessageBox.critical(
                self, "Report Error",
                f"Could not compile HTML executive dossier:\n{path}"
            )
        if self._exporter_thread is not None:
            self._exporter_thread.deleteLater()
            self._exporter_thread = None

    def _export_csv(self, kind: str):
        if not self.project_id:
            return

        try:
            if kind == "weld":
                rows = self.svc.weld_log(self.project_id)
                name = f"weld_log_{self.project_id}.csv"
            elif kind == "fitup":
                rows = self.svc.fitup_report(self.project_id)
                name = f"fitup_report_{self.project_id}.csv"
            else:
                rows = self.svc.ndt_matrix(self.project_id)
                name = f"ndt_matrix_{self.project_id}.csv"
            path = self.svc.export_csv(rows, name)
            QMessageBox.information(
                self, "Exported",
                f"Successfully exported log sheet to:\n{path}"
            )
        except Exception:
            logger.exception("Failed to export target log sheet")

    # ── ORCHESTRATION ────────────────────────────────────────
    def refresh(self):
        self._load_analytics()
        self._load_weld_log()
        self._load_fitup()
        self._load_ndt()
        self._load_front()
        self._load_requests()
        self._load_insights()

    # ── CLEANUP ──────────────────────────────────────────────
    def closeEvent(self, event):
        """Ensure the export thread is stopped before widget closes."""
        if self._exporter_thread is not None:
            try:
                if self._exporter_thread.isRunning():
                    self._exporter_thread.requestInterruption()
                    self._exporter_thread.wait(2000)
                self._exporter_thread.deleteLater()
            except Exception:
                pass
            self._exporter_thread = None
        super().closeEvent(event)


# ─────────────────────────────────────────────
#  UTILITY
# ─────────────────────────────────────────────
def _fill_table(table: QTableWidget, rows: list, cols: list):
    """Populate a table with a list of dictionaries."""
    table.setSortingEnabled(False)
    table.setRowCount(0)
    table.setColumnCount(len(cols))
    table.setHorizontalHeaderLabels([label for _, label in cols])

    for row_idx, row in enumerate(rows or []):
        table.insertRow(row_idx)
        for col_idx, (key, _label) in enumerate(cols):
            val = (
                row.get(key, "") if isinstance(row, dict)
                else getattr(row, key, "")
            )
            table.setItem(
                row_idx, col_idx,
                QTableWidgetItem("" if val is None else str(val)),
            )

    table.setSortingEnabled(True)