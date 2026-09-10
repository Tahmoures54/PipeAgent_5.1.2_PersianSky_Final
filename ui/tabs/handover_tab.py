# -*- coding: utf-8 -*-
# ui/tabs/handover_tab.py – System / subsystem handover & Mechanical Completion (MC)
from __future__ import annotations

import csv
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QCheckBox, QTextEdit, QFrame, QFileDialog,
    QApplication, QMenu, QAbstractItemView, QProgressBar,
)
from PyQt6.QtGui import QColor, QFont, QBrush, QCursor, QAction

from db.manager import DatabaseManager
from db.models import (
    Project, HandoverPackage, TestPackage, Document,
    Weld, Spool, ProjectAction,
)
from security.session import SessionManager
from config import HANDOVER_STATUSES
from services.license import increment_usage

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  UTIL
# ─────────────────────────────────────────────
def _utcnow():
    """Naive UTC — replacement for deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────
#  STATUS BADGES
# ─────────────────────────────────────────────
HANDOVER_BADGES = {
    "Accepted":              {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Ready for Review":      {"bg": "#e0f2fe", "fg": "#075985", "icon": "📋"},
    "In Progress":           {"bg": "#fef3c7", "fg": "#92400e", "icon": "⏳"},
    "Punch Listed":          {"bg": "#ffedd5", "fg": "#9a3412", "icon": "⚠️"},
    "Rejected":              {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Transferred to Comm.":  {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "🚀"},
}
DEFAULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}


# ─────────────────────────────────────────────
#  STYLESHEET
# ─────────────────────────────────────────────
HANDOVER_STYLESHEET = """
    QWidget#handoverTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #0f2b48, stop:1 #1e4b75);
        border-radius: 12px; padding: 14px;
    }
    QLabel#mainTitle {
        color: #ffffff; font-size: 22px; font-weight: 800;
        font-family: 'Segoe UI', sans-serif;
    }
    QLabel#subTitle { color: #94a3b8; font-size: 12px; }
    QFrame#kpiCard {
        background: white; border: 1px solid #cbd5e1;
        border-radius: 8px; padding: 10px;
    }
    QLabel#kpiTitle {
        font-size: 11px; font-weight: 700; color: #64748b;
        text-transform: uppercase;
    }
    QLabel#kpiValue { font-size: 19px; font-weight: 800; color: #0f172a; }
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
    QPushButton#primaryBtn:hover { background: #1d4ed8; }
    QPushButton#secondaryBtn {
        background: white; color: #334155; border: 1px solid #cbd5e1;
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
    QLineEdit, QComboBox {
        padding: 6px 10px; border: 1px solid #cbd5e1;
        border-radius: 6px; font-size: 12px;
    }
"""


# ─────────────────────────────────────────────
#  KPI CARD
# ─────────────────────────────────────────────
class HandoverKPICard(QFrame):
    def __init__(self, title: str, icon: str, color: str = "#3b82f6"):
        super().__init__()
        self.setObjectName("kpiCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        top_lay = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"font-size: 18px; color: {color};")
        top_lay.addWidget(icon_lbl)
        top_lay.addStretch()

        self.val_lbl = QLabel("0")
        self.val_lbl.setObjectName("kpiValue")
        top_lay.addWidget(self.val_lbl)
        layout.addLayout(top_lay)

        t_lbl = QLabel(title)
        t_lbl.setObjectName("kpiTitle")
        layout.addWidget(t_lbl)

    def set_value(self, text: str, highlight_green: bool = False):
        self.val_lbl.setText(str(text))
        if highlight_green:
            self.val_lbl.setStyleSheet(
                "color: #166534; font-size: 19px; font-weight: 800;"
            )
        else:
            self.val_lbl.setStyleSheet(
                "color: #0f172a; font-size: 19px; font-weight: 800;"
            )


# ─────────────────────────────────────────────
#  HANDOVER PACKAGE DIALOG (Create / Edit)
# ─────────────────────────────────────────────
class HandoverPackageDialog(QDialog):
    def __init__(self, parent=None, projects: list = None,
                 existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.existing_id = (
            existing_data.get("id") if existing_data else None
        )
        self.setWindowTitle(
            "Edit Handover Package" if existing_data
            else "New Handover / MC Package"
        )
        self.setMinimumWidth(480)
        self.setStyleSheet(HANDOVER_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.project_combo = QComboBox()
        if projects:
            for p in projects:
                self.project_combo.addItem(
                    f"{p.project_code} – {p.title}", p.id
                )

        self.txt_pkg = QLineEdit()
        self.txt_pkg.setPlaceholderText("e.g. HO-SYS-01-A")
        self.txt_system = QLineEdit()
        self.txt_system.setPlaceholderText("e.g. Fuel Gas / Cooling Water")
        self.txt_subsystem = QLineEdit()
        self.txt_subsystem.setPlaceholderText(
            "e.g. Header Line / Flare Subsystem"
        )

        self.cmb_status = QComboBox()
        self.cmb_status.addItems(HANDOVER_STATUSES)

        self.chk_docs = QCheckBox(
            "Engineering & As-Built Documents Completed & Approved"
        )
        self.chk_tests = QCheckBox(
            "Hydrostatic & Pneumatic Pressure Tests Passed"
        )

        self.txt_remarks = QTextEdit()
        self.txt_remarks.setPlaceholderText(
            "Notes, walkdown items, exceptions..."
        )
        self.txt_remarks.setMaximumHeight(70)

        form.addRow("Project *:", self.project_combo)
        form.addRow("Package Number *:", self.txt_pkg)
        form.addRow("System Name:", self.txt_system)
        form.addRow("Subsystem / Boundary:", self.txt_subsystem)
        form.addRow("Current Status:", self.cmb_status)
        form.addRow("Quality Dossier:", self.chk_docs)
        form.addRow("Testing Verification:", self.chk_tests)
        form.addRow("Remarks:", self.txt_remarks)
        layout.addLayout(form)

        if existing_data:
            pid = existing_data.get("project_id")
            for i in range(self.project_combo.count()):
                if self.project_combo.itemData(i) == pid:
                    self.project_combo.setCurrentIndex(i)
                    break
            self.txt_pkg.setText(existing_data.get("package_no", ""))
            self.txt_system.setText(existing_data.get("system_name", ""))
            self.txt_subsystem.setText(existing_data.get("subsystem", ""))
            self.cmb_status.setCurrentText(
                existing_data.get("status", "In Progress")
            )
            self.chk_docs.setChecked(
                bool(existing_data.get("docs_complete", False))
            )
            self.chk_tests.setChecked(
                bool(existing_data.get("tests_complete", False))
            )
            self.txt_remarks.setPlainText(
                existing_data.get("remarks", "")
            )

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Package")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _save(self):
        if not self.txt_pkg.text().strip():
            QMessageBox.warning(
                self, "Validation", "Package Number is mandatory."
            )
            return
        if not self.project_combo.currentData():
            QMessageBox.warning(
                self, "Validation", "Please select a valid Project."
            )
            return
        self.result_data = {
            "project_id": self.project_combo.currentData(),
            "package_no": self.txt_pkg.text().strip(),
            "system_name": self.txt_system.text().strip(),
            "subsystem": self.txt_subsystem.text().strip(),
            "status": self.cmb_status.currentText(),
            "docs_complete": self.chk_docs.isChecked(),
            "tests_complete": self.chk_tests.isChecked(),
            "remarks": self.txt_remarks.toPlainText().strip(),
        }
        self.accept()


# ─────────────────────────────────────────────
#  BLOCKER DIAGNOSTICS DIALOG
# ─────────────────────────────────────────────
class BlockerDiagnosticsDialog(QDialog):
    def __init__(self, parent=None, diagnostic_data: dict = None):
        super().__init__(parent)
        self.setWindowTitle("🔍 Mechanical Completion Readiness Diagnostics")
        self.setMinimumSize(600, 480)
        self.setStyleSheet(HANDOVER_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QLabel("Detailed Handover Clearance Audit")
        header.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #0f2b48;"
        )
        layout.addWidget(header)

        self.txt_details = QTextEdit()
        self.txt_details.setReadOnly(True)
        layout.addWidget(self.txt_details)

        diagnostic_data = diagnostic_data or {}
        html_lines = ["<h3>Project Handover Readiness Breakdown:</h3><ul>"]

        for k, v in diagnostic_data.get("metrics", {}).items():
            status_color = "#166534" if v["is_ready"] else "#991b1b"
            icon = "✅" if v["is_ready"] else "❌"
            html_lines.append(
                f"<li><b>{k}:</b> "
                f"<span style='color:{status_color}; font-weight:bold;'>"
                f"{icon} {v['passed']}/{v['total']} ({v['pct']:.1f}%)</span> "
                f"– <i>{v['note']}</i></li>"
            )
        html_lines.append("</ul>")

        html_lines.append(
            "<hr><h4>Outstanding Items / Blockers:</h4>"
        )
        blockers = diagnostic_data.get("blockers", [])
        if blockers:
            html_lines.append("<ol>")
            for b in blockers:
                html_lines.append(
                    f"<li style='color:#991b1b;'><b>{b}</b></li>"
                )
            html_lines.append("</ol>")
        else:
            html_lines.append(
                "<p style='color:#166534; font-weight:bold;'>"
                "🎉 No technical blockers found! All piping lines, welds, "
                "test packages, and docs meet Mechanical Completion criteria."
                "</p>"
            )

        self.txt_details.setHtml("".join(html_lines))

        btn_close = QPushButton("Close Audit Window")
        btn_close.setObjectName("secondaryBtn")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class HandoverTab(QWidget):
    def __init__(self, db: DatabaseManager, session: SessionManager):
        super().__init__()
        self.setObjectName("handoverTab")
        self.db = db
        self.session = session
        self.project_id: Optional[int] = None
        self._cached_packages: list[dict] = []

        self._build()
        self.setStyleSheet(HANDOVER_STYLESHEET)
        self._load_projects()

    # ══════════════════════════════════════════
    #  UI BUILD
    # ══════════════════════════════════════════
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Header
        header_card = QFrame()
        header_card.setObjectName("headerCard")
        hdr_lay = QHBoxLayout(header_card)
        hdr_lay.setContentsMargins(14, 10, 14, 10)

        title_v = QVBoxLayout()
        t = QLabel("📤 System / Subsystem Handover Control")
        t.setObjectName("mainTitle")
        s = QLabel(
            "Mechanical Completion (MC), Quality Dossier Sign-offs, "
            "Readiness Audits, and Commissioning Turnover."
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

        btn_r = QPushButton("🔄 Refresh")
        btn_r.setObjectName("secondaryBtn")
        btn_r.clicked.connect(self.refresh)
        proj_box.addWidget(btn_r)
        hdr_lay.addLayout(proj_box)

        root.addWidget(header_card)

        # KPI Row
        kpi_lay = QHBoxLayout()
        kpi_lay.setSpacing(8)

        self.kpi_total = HandoverKPICard(
            "Total MC Packages", "📦", "#3b82f6"
        )
        self.kpi_accepted = HandoverKPICard(
            "Fully Accepted", "✅", "#10b981"
        )
        self.kpi_review = HandoverKPICard(
            "Ready for Review", "📋", "#0ea5e9"
        )
        self.kpi_progress = HandoverKPICard(
            "In Progress / Punch", "⏳", "#f59e0b"
        )
        self.kpi_mc_gauge = HandoverKPICard(
            "Project MC Readiness", "🎯", "#8b5cf6"
        )

        for k in (self.kpi_total, self.kpi_accepted, self.kpi_review,
                  self.kpi_progress, self.kpi_mc_gauge):
            kpi_lay.addWidget(k)
        root.addLayout(kpi_lay)

        # Filter Card
        filter_card = QFrame()
        filter_card.setStyleSheet(
            "background: white; border: 1px solid #cbd5e1; "
            "border-radius: 8px;"
        )
        filter_lay = QHBoxLayout(filter_card)
        filter_lay.setContentsMargins(10, 8, 10, 8)
        filter_lay.setSpacing(8)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(
            "🔍 Search Package No, System, Subsystem, Remarks..."
        )
        self.txt_search.textChanged.connect(self._apply_filter)
        filter_lay.addWidget(self.txt_search, 1)

        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.addItem("All Statuses", None)
        for st in HANDOVER_STATUSES:
            self.cmb_filter_status.addItem(st, st)
        self.cmb_filter_status.currentIndexChanged.connect(
            self._apply_filter
        )
        filter_lay.addWidget(self.cmb_filter_status)

        btn_n = QPushButton("➕ New MC Package")
        btn_n.setObjectName("primaryBtn")
        btn_n.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_n.clicked.connect(self._add)
        filter_lay.addWidget(btn_n)

        btn_diag = QPushButton("🔬 Detailed Audit")
        btn_diag.setObjectName("secondaryBtn")
        btn_diag.setToolTip(
            "View exact pending items blocking overall project handover"
        )
        btn_diag.clicked.connect(self._open_detailed_diagnostics)
        filter_lay.addWidget(btn_diag)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(self._export_csv)
        filter_lay.addWidget(btn_exp)

        root.addWidget(filter_card)

        # Main Table
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Package Identifier", "Main System",
            "Subsystem Boundary", "Handover Status",
            "Quality Docs", "Testing OK", "Accepted / Handover Date",
        ])
        self.table.setColumnHidden(0, True)
        self.table.setAlternatingRowColors(True)
        # ✅ FIXED: use QAbstractItemView enums
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.doubleClicked.connect(self._on_row_double_click)
        self.table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table.customContextMenuRequested.connect(
            self._show_context_menu
        )
        root.addWidget(self.table, 1)

        # Batch action row
        action_row = QHBoxLayout()
        action_row.setSpacing(6)

        lbl_batch = QLabel(
            "Batch Update Status of Selected Packages:"
        )
        lbl_batch.setStyleSheet("font-weight: bold; color: #334155;")
        action_row.addWidget(lbl_batch)

        self.st = QComboBox()
        self.st.addItems(HANDOVER_STATUSES)
        action_row.addWidget(self.st)

        btn_apply = QPushButton("Apply Status")
        btn_apply.setObjectName("secondaryBtn")
        btn_apply.clicked.connect(self._status)
        action_row.addWidget(btn_apply)

        btn_del = QPushButton("🗑️ Delete Selected")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete_selected)
        action_row.addWidget(btn_del)

        action_row.addStretch()
        root.addLayout(action_row)

        # Readiness Card
        self.readiness_card = QFrame()
        self.readiness_card.setStyleSheet(
            "background: #f8fafc; border: 1px solid #cbd5e1; "
            "border-radius: 8px; padding: 10px;"
        )
        readiness_v = QVBoxLayout(self.readiness_card)
        readiness_v.setContentsMargins(10, 8, 10, 8)
        readiness_v.setSpacing(4)

        self.readiness_lbl = QLabel("")
        self.readiness_lbl.setWordWrap(True)
        self.readiness_lbl.setStyleSheet(
            "color: #1e293b; font-size: 12px; line-height: 1.5;"
        )
        readiness_v.addWidget(self.readiness_lbl)

        self.readiness_bar = QProgressBar()
        self.readiness_bar.setRange(0, 100)
        self.readiness_bar.setValue(0)
        self.readiness_bar.setFixedHeight(12)
        self.readiness_bar.setTextVisible(False)
        self.readiness_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #cbd5e1; border-radius: 6px;
                background: #e2e8f0;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #10b981);
                border-radius: 5px;
            }
        """)
        readiness_v.addWidget(self.readiness_bar)
        root.addWidget(self.readiness_card)

    # ══════════════════════════════════════════
    #  PROJECT LOADING
    # ══════════════════════════════════════════
    def _load_projects(self):
        self.proj.blockSignals(True)
        self.proj.clear()
        try:
            with self.db.session_scope() as s:
                for p in s.query(Project).order_by(Project.project_code):
                    self.proj.addItem(
                        f"{p.project_code} – {p.title}", p.id
                    )
        except Exception:
            logger.exception("Failed to load projects in HandoverTab")

        self.proj.blockSignals(False)
        if self.proj.count():
            self._proj_changed()

    def _proj_changed(self):
        self.project_id = self.proj.currentData()
        self.refresh()
        self._readiness()

    # ══════════════════════════════════════════
    #  DATA LOADING
    # ══════════════════════════════════════════
    def refresh(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._cached_packages = []

        if not self.project_id:
            return

        with self.db.session_scope() as s:
            pkgs = (
                s.query(HandoverPackage)
                .filter(HandoverPackage.project_id == self.project_id)
                .order_by(HandoverPackage.package_no)
                .all()
            )

            for p in pkgs:
                self._cached_packages.append({
                    "id": p.id,
                    "project_id": p.project_id,
                    "package_no": p.package_no,
                    "system_name": p.system_name or "",
                    "subsystem": p.subsystem or "",
                    "status": p.status or "In Progress",
                    "docs_complete": bool(p.docs_complete),
                    "tests_complete": bool(p.tests_complete),
                    "handed_over_date": str(p.handed_over_date or ""),
                    "remarks": getattr(p, "remarks", "") or "",
                })

        self._apply_filter()
        self._update_kpi_cards()
        self._readiness()

    def _update_kpi_cards(self):
        total = len(self._cached_packages)
        accepted = sum(
            1 for x in self._cached_packages if x["status"] == "Accepted"
        )
        review = sum(
            1 for x in self._cached_packages
            if x["status"] == "Ready for Review"
        )
        in_prog = sum(
            1 for x in self._cached_packages
            if x["status"] in ("In Progress", "Punch Listed")
        )

        self.kpi_total.set_value(str(total))
        self.kpi_accepted.set_value(
            str(accepted), highlight_green=(accepted == total and total > 0)
        )
        self.kpi_review.set_value(str(review))
        self.kpi_progress.set_value(str(in_prog))

    def _apply_filter(self):
        query = self.txt_search.text().strip().lower()
        status_filter = self.cmb_filter_status.currentData()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for p in self._cached_packages:
            if status_filter and p["status"] != status_filter:
                continue

            if query:
                combined_txt = (
                    f"{p['package_no']} {p['system_name']} "
                    f"{p['subsystem']} {p['remarks']}"
                ).lower()
                if query not in combined_txt:
                    continue

            r = self.table.rowCount()
            self.table.insertRow(r)

            self.table.setItem(r, 0, QTableWidgetItem(str(p["id"])))
            self.table.setItem(r, 1, QTableWidgetItem(p["package_no"]))
            self.table.setItem(r, 2, QTableWidgetItem(p["system_name"]))
            self.table.setItem(r, 3, QTableWidgetItem(p["subsystem"]))

            # Status badge
            status_item = QTableWidgetItem(p["status"])
            badge = HANDOVER_BADGES.get(p["status"], DEFAULT_BADGE)
            status_item.setText(f"{badge['icon']} {p['status']}")
            status_item.setBackground(QBrush(QColor(badge["bg"])))
            status_item.setForeground(QBrush(QColor(badge["fg"])))
            font = status_item.font()
            font.setBold(True)
            status_item.setFont(font)
            self.table.setItem(r, 4, status_item)

            docs_item = QTableWidgetItem(
                "✅ Complete" if p["docs_complete"] else "❌ Incomplete"
            )
            docs_item.setForeground(QBrush(QColor(
                "#166534" if p["docs_complete"] else "#991b1b"
            )))
            self.table.setItem(r, 5, docs_item)

            tests_item = QTableWidgetItem(
                "✅ Passed" if p["tests_complete"] else "⏳ Pending"
            )
            tests_item.setForeground(QBrush(QColor(
                "#166534" if p["tests_complete"] else "#92400e"
            )))
            self.table.setItem(r, 6, tests_item)

            self.table.setItem(r, 7, QTableWidgetItem(p["handed_over_date"]))

        self.table.setSortingEnabled(True)

    # ══════════════════════════════════════════
    #  ADD / EDIT
    # ══════════════════════════════════════════
    def _add(self):
        with self.db.session_scope() as s:
            projects = (
                s.query(Project).order_by(Project.project_code).all()
            )
            proj_list = [
                type("P", (), {
                    "id": p.id,
                    "project_code": p.project_code,
                    "title": p.title,
                })()
                for p in projects
            ]

        if not proj_list:
            QMessageBox.information(
                self, "Info", "Please register a project first."
            )
            return

        dlg = HandoverPackageDialog(self, projects=proj_list)
        if self.project_id:
            for i in range(dlg.project_combo.count()):
                if dlg.project_combo.itemData(i) == self.project_id:
                    dlg.project_combo.setCurrentIndex(i)
                    break

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.result_data
        if not increment_usage(self.db):
            QMessageBox.warning(
                self, "License Limit",
                "Handover package creation limit reached "
                "under current license."
            )
            return

        try:
            with self.db.session_scope() as s:
                pkg = HandoverPackage(
                    project_id=d["project_id"],
                    package_no=d["package_no"],
                    system_name=d["system_name"],
                    subsystem=d["subsystem"],
                    remarks=d["remarks"],
                    status=d["status"],
                    docs_complete=d["docs_complete"],
                    tests_complete=d["tests_complete"],
                    # ✅ FIXED: use _utcnow() helper
                    created_at=_utcnow(),
                )
                s.add(pkg)
                s.flush()

                s.add(ProjectAction(
                    project_id=d["project_id"],
                    action_type="CREATE_HANDOVER_PKG",
                    entity_type="HandoverPackage",
                    entity_id=pkg.id,
                    description=(
                        f"Created Handover Package {d['package_no']} "
                        f"({d['system_name']})"
                    ),
                    user_name=getattr(self.session, "username", "admin"),
                ))

            self.refresh()
            QMessageBox.information(
                self, "Success",
                f"Handover Package {d['package_no']} created successfully."
            )
        except Exception as e:
            logger.exception("Failed to create handover package")
            QMessageBox.critical(
                self, "Error", f"Could not create package:\n{e}"
            )

    def _edit_package(self, pkg_id: int):
        pkg_data = next(
            (x for x in self._cached_packages if x["id"] == pkg_id), None
        )
        if not pkg_data:
            return

        with self.db.session_scope() as s:
            projects = (
                s.query(Project).order_by(Project.project_code).all()
            )
            proj_list = [
                type("P", (), {
                    "id": p.id,
                    "project_code": p.project_code,
                    "title": p.title,
                })()
                for p in projects
            ]

        dlg = HandoverPackageDialog(
            self, projects=proj_list, existing_data=pkg_data
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.result_data
        try:
            with self.db.session_scope() as s:
                # ✅ FIXED: SQLAlchemy 2.0 — s.get(Model, pk)
                p = s.get(HandoverPackage, pkg_id)
                if p:
                    p.package_no = d["package_no"]
                    p.system_name = d["system_name"]
                    p.subsystem = d["subsystem"]
                    p.status = d["status"]
                    p.docs_complete = d["docs_complete"]
                    p.tests_complete = d["tests_complete"]
                    p.remarks = d["remarks"]
                    if d["status"] == "Accepted" and not p.handed_over_date:
                        p.handed_over_date = date.today()
                        p.accepted_by = getattr(
                            self.session, "username", "admin"
                        )

            self.refresh()
            QMessageBox.information(
                self, "Updated",
                f"Handover Package {d['package_no']} updated."
            )
        except Exception as e:
            logger.exception("Failed to update handover package")
            QMessageBox.critical(
                self, "Error", f"Could not update package:\n{e}"
            )

    # ══════════════════════════════════════════
    #  DELETE
    # ══════════════════════════════════════════
    def _delete_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select at least one package to delete."
            )
            return

        pkg_ids = [int(self.table.item(r.row(), 0).text()) for r in rows]
        pkg_nos = [self.table.item(r.row(), 1).text() for r in rows]

        if QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete "
            f"{len(pkg_ids)} handover package(s)?\n\n"
            f"Packages: {', '.join(pkg_nos[:5])}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as s:
                for hid in pkg_ids:
                    # ✅ FIXED: SQLAlchemy 2.0
                    p = s.get(HandoverPackage, hid)
                    if p:
                        s.delete(p)
            self.refresh()
            QMessageBox.information(
                self, "Deleted",
                "Selected package(s) deleted successfully."
            )
        except Exception as e:
            logger.exception("Failed to delete handover packages")
            QMessageBox.critical(
                self, "Error", f"Could not delete packages:\n{e}"
            )

    # ══════════════════════════════════════════
    #  BATCH STATUS
    # ══════════════════════════════════════════
    def _status(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select at least one package from the table."
            )
            return

        new_st = self.st.currentText()
        pkg_ids = [int(self.table.item(r.row(), 0).text()) for r in rows]
        user = getattr(self.session, "username", "admin")

        try:
            with self.db.session_scope() as s:
                for hid in pkg_ids:
                    # ✅ FIXED
                    p = s.get(HandoverPackage, hid)
                    if p:
                        p.status = new_st
                        if new_st == "Accepted":
                            p.handed_over_date = date.today()
                            p.accepted_by = user

            self.refresh()
            QMessageBox.information(
                self, "Status Applied",
                f"Updated status to '{new_st}' for "
                f"{len(pkg_ids)} package(s)."
            )
        except Exception as e:
            logger.exception("Failed to apply batch status")
            QMessageBox.critical(
                self, "Error", f"Could not update status:\n{e}"
            )

    # ══════════════════════════════════════════
    #  READINESS DIAGNOSTICS
    # ══════════════════════════════════════════
    def _collect_readiness_diagnostics(self) -> dict:
        if not self.project_id:
            return {"metrics": {}, "blockers": [], "score": 0}

        blockers = []
        with self.db.session_scope() as s:
            welds = (
                s.query(Weld)
                .filter(Weld.project_id == self.project_id)
                .all()
            )
            total_w = len(welds)
            accepted_w = sum(1 for w in welds if w.status == "Accepted")
            if total_w > accepted_w:
                blockers.append(
                    f"{total_w - accepted_w} joint(s) pending "
                    f"weld/NDT inspection."
                )

            spools = (
                s.query(Spool)
                .filter(Spool.project_id == self.project_id)
                .all()
            )
            total_spools = len(spools)
            installed_spools = sum(
                1 for sp in spools
                if (sp.status or "") in ("Installed", "Tested")
            )
            if total_spools > installed_spools:
                blockers.append(
                    f"{total_spools - installed_spools} spool(s) "
                    f"not installed/tested on site."
                )

            tps = (
                s.query(TestPackage)
                .filter(TestPackage.project_id == self.project_id)
                .all()
            )
            total_tps = len(tps)
            passed_tps = sum(
                1 for t in tps
                if (t.status or "") in ("Passed", "Approved")
            )
            if total_tps > passed_tps:
                blockers.append(
                    f"{total_tps - passed_tps} hydrostatic/pneumatic "
                    f"test package(s) not passed."
                )

            docs = (
                s.query(Document)
                .filter(Document.project_id == self.project_id)
                .all()
            )
            total_docs = len(docs)
            approved_docs = sum(
                1 for d in docs
                if (d.status or "") in (
                    "Issued for Construction", "As-Built",
                    "Approved", "AFC",
                )
            )
            if total_docs > approved_docs:
                blockers.append(
                    f"{total_docs - approved_docs} engineering/quality "
                    f"drawing(s) not approved as As-Built."
                )

        weld_pct = (accepted_w / total_w * 100) if total_w > 0 else 100.0
        spool_pct = (
            (installed_spools / total_spools * 100)
            if total_spools > 0 else 100.0
        )
        tp_pct = (
            (passed_tps / total_tps * 100) if total_tps > 0 else 100.0
        )
        doc_pct = (
            (approved_docs / total_docs * 100) if total_docs > 0 else 100.0
        )

        overall_score = (
            (weld_pct * 0.35)
            + (spool_pct * 0.25)
            + (tp_pct * 0.25)
            + (doc_pct * 0.15)
        )

        return {
            "metrics": {
                "Welding & NDT": {
                    "passed": accepted_w, "total": total_w,
                    "pct": weld_pct,
                    "is_ready": (total_w == accepted_w),
                    "note": "100% Weld Acceptance required for MC",
                },
                "Spool Field Erection": {
                    "passed": installed_spools, "total": total_spools,
                    "pct": spool_pct,
                    "is_ready": (total_spools == installed_spools),
                    "note": "All spools must be on-line & torqued",
                },
                "Pressure Test Packages": {
                    "passed": passed_tps, "total": total_tps,
                    "pct": tp_pct,
                    "is_ready": (total_tps == passed_tps),
                    "note": "Hydro/Pneumatic tests signed off",
                },
                "As-Built Quality Docs": {
                    "passed": approved_docs, "total": total_docs,
                    "pct": doc_pct,
                    "is_ready": (total_docs == approved_docs),
                    "note": "Drawings stamped As-Built / Approved",
                },
            },
            "blockers": blockers,
            "score": overall_score,
        }

    def _readiness(self):
        if not self.project_id:
            self.readiness_lbl.setText(
                "<b>Select a project to initiate Mechanical Completion "
                "(MC) readiness audit.</b>"
            )
            self.readiness_bar.setValue(0)
            self.kpi_mc_gauge.set_value("0%")
            return

        diag = self._collect_readiness_diagnostics()
        score = diag["score"]
        self.readiness_bar.setValue(int(score))
        self.kpi_mc_gauge.set_value(
            f"{score:.1f}%", highlight_green=(score >= 99.9)
        )

        m = diag["metrics"]
        summary_html = f"""
            <div style='line-height: 1.4;'>
                <b>🛡️ Project Mechanical Completion (MC) Readiness Snapshot:</b><br>
                • <b>Welds Accepted:</b> {m['Welding & NDT']['passed']}/{m['Welding & NDT']['total']} ({m['Welding & NDT']['pct']:.0f}%) &nbsp;|&nbsp;
                • <b>Spools Erected:</b> {m['Spool Field Erection']['passed']}/{m['Spool Field Erection']['total']} ({m['Spool Field Erection']['pct']:.0f}%) &nbsp;|&nbsp;
                • <b>Tests Passed:</b> {m['Pressure Test Packages']['passed']}/{m['Pressure Test Packages']['total']} ({m['Pressure Test Packages']['pct']:.0f}%) &nbsp;|&nbsp;
                • <b>As-Built Docs:</b> {m['As-Built Quality Docs']['passed']}/{m['As-Built Quality Docs']['total']} ({m['As-Built Quality Docs']['pct']:.0f}%)
                <br>{'<span style="color:#166534; font-weight:bold;">✓ System boundary is fully clear & ready for final Commissioning handover.</span>' if len(diag['blockers']) == 0 else f'<span style="color:#991b1b; font-weight:bold;">✗ Outstanding punchlist / blockers remain ({len(diag["blockers"])} pending items). Click "Detailed Audit" for specifics.</span>'}
            </div>
        """
        self.readiness_lbl.setHtml(summary_html)

    def _open_detailed_diagnostics(self):
        if not self.project_id:
            QMessageBox.warning(
                self, "Project", "Select a project first."
            )
            return
        diag_data = self._collect_readiness_diagnostics()
        dlg = BlockerDiagnosticsDialog(self, diag_data)
        dlg.exec()

    # ══════════════════════════════════════════
    #  ROW EVENTS
    # ══════════════════════════════════════════
    def _on_row_double_click(self, index):
        row = index.row()
        pkg_id = int(self.table.item(row, 0).text())
        self._edit_package(pkg_id)

    # ══════════════════════════════════════════
    #  CONTEXT MENU
    # ══════════════════════════════════════════
    def _show_context_menu(self, pos):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 18px; }"
        )

        row = selected_rows[0].row()
        pkg_id = int(self.table.item(row, 0).text())

        act_edit = QAction("✏️ Edit Package Details", self)
        act_edit.triggered.connect(lambda: self._edit_package(pkg_id))
        menu.addAction(act_edit)

        act_accept = QAction("✅ Mark as 'Accepted'", self)
        act_accept.triggered.connect(
            lambda: self._quick_set_status(pkg_id, "Accepted")
        )
        menu.addAction(act_accept)

        act_review = QAction("📋 Mark as 'Ready for Review'", self)
        act_review.triggered.connect(
            lambda: self._quick_set_status(pkg_id, "Ready for Review")
        )
        menu.addAction(act_review)

        menu.addSeparator()

        act_copy = QAction("📋 Copy Package Info", self)
        act_copy.triggered.connect(lambda: self._copy_row_text(row))
        menu.addAction(act_copy)

        act_del = QAction("🗑️ Delete Package", self)
        act_del.triggered.connect(self._delete_selected)
        menu.addAction(act_del)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _quick_set_status(self, pkg_id: int, new_status: str):
        try:
            with self.db.session_scope() as s:
                # ✅ FIXED: SQLAlchemy 2.0
                p = s.get(HandoverPackage, pkg_id)
                if p:
                    p.status = new_status
                    if new_status == "Accepted":
                        p.handed_over_date = date.today()
                        p.accepted_by = getattr(
                            self.session, "username", "admin"
                        )
            self.refresh()
        except Exception as e:
            logger.exception("Failed to quick set status")
            QMessageBox.critical(
                self, "Error", f"Failed to update status:\n{e}"
            )

    def _copy_row_text(self, row: int):
        data = [
            self.table.item(row, c).text()
            for c in range(1, self.table.columnCount())
            if self.table.item(row, c)
        ]
        QApplication.clipboard().setText(" | ".join(data))

    # ══════════════════════════════════════════
    #  EXPORT
    # ══════════════════════════════════════════
    def _export_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(
                self, "Export",
                "No handover packages available to export."
            )
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_code = self.proj.currentText().split("–")[0].strip()
        default_name = (
            f"Handover_Packages_{proj_code}_{timestamp}.csv"
        )

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Handover Report", default_name,
            "CSV Files (*.csv)",
        )
        if not filename:
            return

        try:
            with open(filename, mode="w", newline="",
                      encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                headers = [
                    self.table.horizontalHeaderItem(c).text()
                    for c in range(1, self.table.columnCount())
                ]
                writer.writerow(headers)

                for r in range(self.table.rowCount()):
                    row_vals = []
                    for c in range(1, self.table.columnCount()):
                        item = self.table.item(r, c)
                        row_vals.append(item.text().strip() if item else "")
                    writer.writerow(row_vals)

            QMessageBox.information(
                self, "Export Complete",
                f"Handover report exported to:\n{filename}"
            )
        except Exception as e:
            logger.exception("Failed to export handover CSV")
            QMessageBox.critical(
                self, "Export Error", f"Could not create CSV file:\n{e}"
            )