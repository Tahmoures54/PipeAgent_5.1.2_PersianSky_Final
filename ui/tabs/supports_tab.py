# -*- coding: utf-8 -*-
# ui/tabs/supports_tab.py – PipeAgent 5.3.0
# Piping Supports Engineering, Shop Fabrication, Site Erection & QC Register
from __future__ import annotations

import csv
import logging
import datetime
from datetime import timezone
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QTextEdit, QFrame, QFileDialog,
    QApplication, QMenu, QAbstractItemView, QGroupBox,
    QDoubleSpinBox,
)
from PyQt6.QtGui import QColor, QFont, QBrush, QCursor, QAction

from db.manager import DatabaseManager
from db.models import Project, PipeSupport
from security.session import SessionManager
from services.license import increment_usage

# ── Support constants (fallback if config missing) ────────────
try:
    from config import SUPPORT_TYPES, SUPPORT_STATUSES
except ImportError:
    SUPPORT_TYPES = [
        "Shoe / Rest (Sliding)", "Guide (Lateral/Axial)",
        "Line Stop / Anchor",
        "Variable Spring Hanger", "Constant Spring Hanger",
        "Rigid Strut / Rod",
        "Trunnion / Dummy Leg", "U-Bolt / Pipe Clamp",
        "Saddle Support", "Special Engineered",
    ]
    SUPPORT_STATUSES = [
        "Engineering / MTO", "In Fabrication", "Fabricated (Shop)",
        "Delivered to Site", "Installed", "QC Inspected",
        "Accepted", "On Hold / Punch",
    ]

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  UTIL
# ─────────────────────────────────────────────
def _utcnow():
    """Naive UTC — replacement for deprecated datetime.utcnow()."""
    return datetime.datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────
#  STATUS BADGES
# ─────────────────────────────────────────────
SUPPORT_STATUS_BADGES = {
    "Accepted":          {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "QC Inspected":      {"bg": "#dcfce7", "fg": "#166534", "icon": "🔍"},
    "Installed":         {"bg": "#e0f2fe", "fg": "#075985", "icon": "🟢"},
    "Delivered to Site": {"bg": "#e0e7ff", "fg": "#3730a3", "icon": "🚚"},
    "Fabricated (Shop)": {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "🏭"},
    "In Fabrication":    {"bg": "#fef3c7", "fg": "#92400e", "icon": "⚙️"},
    "Engineering / MTO": {"bg": "#f1f5f9", "fg": "#475569", "icon": "📐"},
    "On Hold / Punch":   {"bg": "#fee2e2", "fg": "#991b1b", "icon": "⚠️"},
}
DEFAULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}

SUPPORT_TYPE_ICONS = {
    "Shoe": "🥿", "Guide": "↔️", "Anchor": "⚓", "Stop": "🛑",
    "Spring": "〰️", "Strut": "🦯", "Trunnion": "T",
    "Clamp": "🗜️", "Saddle": "💺",
}


# ─────────────────────────────────────────────
#  STYLESHEET
# ─────────────────────────────────────────────
SUPPORTS_STYLESHEET = """
    QWidget#supportsTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #1a2f4c, stop:1 #284b77);
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
    QLineEdit, QComboBox, QTextEdit, QDoubleSpinBox {
        padding: 6px 10px; border: 1px solid #cbd5e1;
        border-radius: 6px; font-size: 12px;
    }
"""


# ─────────────────────────────────────────────
#  KPI CARD
# ─────────────────────────────────────────────
class SupportKPICard(QFrame):
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

    def set_value(self, text: str, highlight: Optional[str] = None):
        self.val_lbl.setText(str(text))
        if highlight == "green":
            self.val_lbl.setStyleSheet(
                "color: #166534; font-size: 19px; font-weight: 800;"
            )
        elif highlight == "blue":
            self.val_lbl.setStyleSheet(
                "color: #0369a1; font-size: 19px; font-weight: 800;"
            )
        elif highlight == "amber":
            self.val_lbl.setStyleSheet(
                "color: #92400e; font-size: 19px; font-weight: 800;"
            )
        else:
            self.val_lbl.setStyleSheet(
                "color: #0f172a; font-size: 19px; font-weight: 800;"
            )


# ─────────────────────────────────────────────
#  SUPPORT DIALOG
# ─────────────────────────────────────────────
class SupportDialog(QDialog):
    def __init__(self, parent=None, projects: list = None,
                 existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = existing_data is not None
        self.setWindowTitle(
            "Edit Support Specifications" if self.is_edit
            else "Register New Pipe Support"
        )
        self.setMinimumWidth(500)
        self.setStyleSheet(SUPPORTS_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.project_combo = QComboBox()
        if projects:
            for p in projects:
                self.project_combo.addItem(
                    f"{p.project_code} – {p.title}", p.id
                )

        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText(
            "e.g. PS-1001-H01 or S-04A"
        )

        self.stype_combo = QComboBox()
        self.stype_combo.addItems(SUPPORT_TYPES)
        self.stype_combo.setEditable(True)

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText('e.g. 6"-PL-1001-A1A')

        self.iso_edit = QLineEdit()
        self.iso_edit.setPlaceholderText("e.g. ISO-1001-SHT-01")

        self.drawing_edit = QLineEdit()
        self.drawing_edit.setPlaceholderText(
            "Standard Support Detail DWG (e.g. STD-PS-012 Rev.2)"
        )

        self.location_edit = QLineEdit()
        self.location_edit.setPlaceholderText(
            "Plant Grid / Elevation / Structure Bay "
            "(e.g. EL +14.500 Rack B)"
        )

        self.weight_edit = QDoubleSpinBox()
        self.weight_edit.setRange(0, 50000)
        self.weight_edit.setDecimals(1)
        self.weight_edit.setSuffix(" kg")

        self.status_combo = QComboBox()
        self.status_combo.addItems(SUPPORT_STATUSES)

        self.remarks_edit = QTextEdit()
        self.remarks_edit.setPlaceholderText(
            "Pad reinforcement, welding to structure, "
            "spring cold load notes..."
        )
        self.remarks_edit.setMaximumHeight(65)

        form.addRow("Project *:", self.project_combo)
        form.addRow("Support Tag Identifier *:", self.tag_edit)
        form.addRow("Support Functional Type *:", self.stype_combo)
        form.addRow("Piping Line Number *:", self.line_edit)
        form.addRow("Isometric DWG Reference:", self.iso_edit)
        form.addRow("Support Detail DWG:", self.drawing_edit)
        form.addRow("Plant Location / Elev:", self.location_edit)
        form.addRow("Estimated Steel Weight:", self.weight_edit)
        form.addRow("Current Lifecycle Status:", self.status_combo)
        form.addRow("Engineering Remarks:", self.remarks_edit)
        layout.addLayout(form)

        if self.is_edit and existing_data:
            pid = existing_data.get("project_id")
            for i in range(self.project_combo.count()):
                if self.project_combo.itemData(i) == pid:
                    self.project_combo.setCurrentIndex(i)
                    break
            self.tag_edit.setText(
                existing_data.get("support_tag", "")
            )
            self.tag_edit.setReadOnly(True)
            self.stype_combo.setCurrentText(
                existing_data.get("support_type", SUPPORT_TYPES[0])
            )
            self.line_edit.setText(
                existing_data.get("line_number", "")
            )
            self.iso_edit.setText(
                existing_data.get("iso_number", "")
            )
            self.drawing_edit.setText(
                existing_data.get("drawing_no", "")
            )
            self.location_edit.setText(
                existing_data.get("location_desc", "")
            )
            self.status_combo.setCurrentText(
                existing_data.get("status", SUPPORT_STATUSES[0])
            )
            self.remarks_edit.setPlainText(
                existing_data.get("remarks", "")
            )

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Support")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._validate_and_accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _validate_and_accept(self):
        if not self.tag_edit.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Support Tag Identifier is mandatory."
            )
            self.tag_edit.setFocus()
            return
        if not self.line_edit.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Piping Line Number is required."
            )
            self.line_edit.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "project_id": self.project_combo.currentData(),
            "support_tag": self.tag_edit.text().strip(),
            "support_type": self.stype_combo.currentText().strip(),
            "line_number": self.line_edit.text().strip(),
            "iso_number": self.iso_edit.text().strip(),
            "drawing_no": self.drawing_edit.text().strip(),
            "location_desc": self.location_edit.text().strip(),
            "status": self.status_combo.currentText(),
            "remarks": self.remarks_edit.toPlainText().strip(),
        }


# ─────────────────────────────────────────────
#  SUPPORT DETAIL DIALOG
# ─────────────────────────────────────────────
class SupportDetailDialog(QDialog):
    def __init__(self, parent=None, support_data: dict = None):
        super().__init__(parent)
        self.setWindowTitle(
            f"🔍 Support Technical Dossier – "
            f"{support_data.get('support_tag', 'Support')}"
        )
        self.setMinimumSize(560, 440)
        self.setStyleSheet(SUPPORTS_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hdr = QLabel(
            f"📋 Engineering Dossier: "
            f"{support_data.get('support_tag')}"
        )
        hdr.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #1a2f4c;"
        )
        layout.addWidget(hdr)

        info_box = QGroupBox(
            "Support Design & Location Specifications"
        )
        info_grid = QGridLayout(info_box)
        info_grid.setSpacing(8)

        details = [
            ("Support Tag No:",
             support_data.get("support_tag", "—")),
            ("Functional Type:",
             support_data.get("support_type", "—")),
            ("Piping Line No:",
             support_data.get("line_number", "—")),
            ("Isometric Drawing:",
             support_data.get("iso_number", "—")),
            ("Detail Standard DWG:",
             support_data.get("drawing_no", "—")),
            ("Plant Location / Elev:",
             support_data.get("location_desc", "—")),
            ("Lifecycle Status:",
             support_data.get("status", "Pending")),
            ("Installation Date:",
             str(support_data.get("installed_date", "—"))),
        ]

        for i, (label, val) in enumerate(details):
            lbl_w = QLabel(f"<b>{label}</b>")
            lbl_w.setStyleSheet("color: #475569;")
            val_w = QLabel(str(val))
            val_w.setStyleSheet("color: #0f172a; font-weight: 600;")
            r, c = divmod(i, 2)
            info_grid.addWidget(lbl_w, r, c * 2)
            info_grid.addWidget(val_w, r, c * 2 + 1)

        layout.addWidget(info_box)

        rem_box = QGroupBox(
            "Engineering Remarks & Erection Notes"
        )
        rem_lay = QVBoxLayout(rem_box)
        txt_rem = QTextEdit()
        txt_rem.setReadOnly(True)
        txt_rem.setPlainText(
            support_data.get("remarks", "")
            or "No special fabrication or installation remarks recorded."
        )
        rem_lay.addWidget(txt_rem)
        layout.addWidget(rem_box)

        btn_close = QPushButton("Close Dossier")
        btn_close.setObjectName("secondaryBtn")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class SupportsTab(QWidget):
    def __init__(self, db: DatabaseManager,
                 session: SessionManager):
        super().__init__()
        self.setObjectName("supportsTab")
        self.db = db
        self.session = session
        self.project_id: Optional[int] = None
        self._cached_supports: list[dict] = []

        self._build_ui()
        self.setStyleSheet(SUPPORTS_STYLESHEET)
        self._load_projects()

    # ══════════════════════════════════════════
    #  UI BUILD
    # ══════════════════════════════════════════
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header
        header_card = QFrame()
        header_card.setObjectName("headerCard")
        hdr_lay = QHBoxLayout(header_card)
        hdr_lay.setContentsMargins(14, 10, 14, 10)

        title_v = QVBoxLayout()
        t = QLabel("🧱 Piping Supports & Restraints Register")
        t.setObjectName("mainTitle")
        s = QLabel(
            "Pipe Support Lifecycle: Engineering MTO, "
            "Shop Fabrication, Site Delivery, Erection & QC Sign-off."
        )
        s.setObjectName("subTitle")
        title_v.addWidget(t)
        title_v.addWidget(s)
        hdr_lay.addLayout(title_v, 1)

        proj_box = QHBoxLayout()
        lbl_p = QLabel("Project:")
        lbl_p.setStyleSheet("color: white; font-weight: bold;")
        proj_box.addWidget(lbl_p)

        self.proj_combo = QComboBox()
        self.proj_combo.setMinimumWidth(220)
        self.proj_combo.currentIndexChanged.connect(
            self._on_project_changed
        )
        proj_box.addWidget(self.proj_combo)

        btn_refresh_all = QPushButton("🔄 Refresh")
        btn_refresh_all.setObjectName("secondaryBtn")
        btn_refresh_all.clicked.connect(self.refresh)
        proj_box.addWidget(btn_refresh_all)
        hdr_lay.addLayout(proj_box)

        layout.addWidget(header_card)

        # KPI row
        kpi_lay = QHBoxLayout()
        kpi_lay.setSpacing(8)

        self.kpi_total = SupportKPICard(
            "Total Supports Scope", "🧱", "#3b82f6"
        )
        self.kpi_fab = SupportKPICard(
            "Fabricated / Delivered", "🚚", "#8b5cf6"
        )
        self.kpi_installed = SupportKPICard(
            "Installed on Line", "🟢", "#0ea5e9"
        )
        self.kpi_accepted = SupportKPICard(
            "QC Inspected & OK", "✅", "#10b981"
        )
        self.kpi_springs = SupportKPICard(
            "Spring Hangers Scope", "〰️", "#f59e0b"
        )

        for k in (self.kpi_total, self.kpi_fab, self.kpi_installed,
                  self.kpi_accepted, self.kpi_springs):
            kpi_lay.addWidget(k)
        layout.addLayout(kpi_lay)

        # Filter card
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
            "🔍 Search Support Tag, Line No, ISO, "
            "Standard DWG, Location..."
        )
        self.txt_search.textChanged.connect(self._apply_filters)
        filter_lay.addWidget(self.txt_search, 1)

        self.cmb_filter_type = QComboBox()
        self.cmb_filter_type.addItem("All Support Types", None)
        for st in SUPPORT_TYPES:
            self.cmb_filter_type.addItem(st, st)
        self.cmb_filter_type.currentIndexChanged.connect(
            self._apply_filters
        )
        filter_lay.addWidget(self.cmb_filter_type)

        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.addItem("All Statuses", None)
        for st in SUPPORT_STATUSES:
            self.cmb_filter_status.addItem(st, st)
        self.cmb_filter_status.currentIndexChanged.connect(
            self._apply_filters
        )
        filter_lay.addWidget(self.cmb_filter_status)

        btn_new = QPushButton("➕ New Support")
        btn_new.setObjectName("primaryBtn")
        btn_new.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_new.clicked.connect(self._add)
        filter_lay.addWidget(btn_new)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(self._export_supports_csv)
        filter_lay.addWidget(btn_exp)

        btn_del = QPushButton("🗑️ Delete")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete_selected)
        filter_lay.addWidget(btn_del)

        layout.addWidget(filter_card)

        # Main table
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "ID", "Support Tag No", "Support Type", "Piping Line No",
            "ISO DWG Ref", "Detail DWG", "Lifecycle Status",
            "Plant Location / Elev", "Remarks",
        ])
        self.table.setColumnHidden(0, True)
        self._setup_table_style(self.table)
        self.table.doubleClicked.connect(self._on_row_double_click)
        self.table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table.customContextMenuRequested.connect(
            self._show_context_menu
        )
        layout.addWidget(self.table, 1)

        # Batch action bar
        status_bar_card = QFrame()
        status_bar_card.setStyleSheet(
            "background: #f8fafc; border: 1px solid #cbd5e1; "
            "border-radius: 6px; padding: 6px;"
        )
        status_row = QHBoxLayout(status_bar_card)
        status_row.setContentsMargins(10, 4, 10, 4)
        status_row.setSpacing(8)

        lbl_batch = QLabel(
            "Batch Transition Selected Supports To:"
        )
        lbl_batch.setStyleSheet("font-weight: bold; color: #334155;")
        status_row.addWidget(lbl_batch)

        self.st_combo = QComboBox()
        self.st_combo.addItems(SUPPORT_STATUSES)
        status_row.addWidget(self.st_combo)

        btn_apply = QPushButton("Apply Milestone")
        btn_apply.setObjectName("secondaryBtn")
        btn_apply.clicked.connect(self._status)
        status_row.addWidget(btn_apply)

        btn_deliv = QPushButton("🚚 Delivered to Site")
        btn_deliv.setObjectName("secondaryBtn")
        btn_deliv.clicked.connect(
            lambda: self._quick_batch_status("Delivered to Site")
        )
        status_row.addWidget(btn_deliv)

        btn_inst = QPushButton("🟢 Mark Installed")
        btn_inst.setObjectName("secondaryBtn")
        btn_inst.clicked.connect(
            lambda: self._quick_batch_status("Installed")
        )
        status_row.addWidget(btn_inst)

        btn_acc = QPushButton("✅ QC Accepted")
        btn_acc.setObjectName("secondaryBtn")
        btn_acc.clicked.connect(
            lambda: self._quick_batch_status("Accepted")
        )
        status_row.addWidget(btn_acc)

        status_row.addStretch()
        layout.addWidget(status_bar_card)

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

    # ══════════════════════════════════════════
    #  PROJECT LOADING
    # ══════════════════════════════════════════
    def _load_projects(self):
        self.proj_combo.blockSignals(True)
        self.proj_combo.clear()
        try:
            with self.db.session_scope() as s:
                for p in (
                    s.query(Project).order_by(Project.project_code)
                ):
                    self.proj_combo.addItem(
                        f"{p.project_code} – {p.title}", p.id
                    )
        except Exception:
            logger.exception(
                "Failed to load projects in SupportsTab"
            )

        self.proj_combo.blockSignals(False)
        if self.proj_combo.count():
            self._on_project_changed()

    def _on_project_changed(self):
        self.project_id = self.proj_combo.currentData()
        self.refresh()

    # ══════════════════════════════════════════
    #  REFRESH
    # ══════════════════════════════════════════
    def refresh(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._cached_supports = []

        if not self.project_id:
            self._update_kpis(0, 0, 0, 0, 0)
            return

        try:
            with self.db.session_scope() as s:
                items = (
                    s.query(PipeSupport)
                    .filter(
                        PipeSupport.project_id == self.project_id
                    )
                    .order_by(PipeSupport.support_tag)
                    .all()
                )

                fab_cnt = inst_cnt = acc_cnt = spring_cnt = 0

                for sp in items:
                    st = sp.status or "Engineering / MTO"
                    stype = (
                        sp.support_type or "Shoe / Rest (Sliding)"
                    )

                    if st in ("Fabricated (Shop)",
                              "Delivered to Site"):
                        fab_cnt += 1
                    if st in ("Installed", "QC Inspected",
                              "Accepted"):
                        inst_cnt += 1
                    if st == "Accepted":
                        acc_cnt += 1
                    if "Spring" in stype or "Snubber" in stype:
                        spring_cnt += 1

                    self._cached_supports.append({
                        "id": sp.id,
                        "project_id": sp.project_id,
                        "support_tag": sp.support_tag,
                        "support_type": stype,
                        "line_number": sp.line_number or "",
                        "iso_number": sp.iso_number or "",
                        "drawing_no": sp.drawing_no or "",
                        "status": st,
                        "location_desc": sp.location_desc or "",
                        "remarks": (
                            getattr(sp, "remarks", "") or ""
                        ),
                        "installed_date": (
                            getattr(sp, "installed_date", "") or ""
                        ),
                    })

                self._update_kpis(
                    len(items), fab_cnt, inst_cnt,
                    acc_cnt, spring_cnt,
                )
                self._apply_filters()

        except Exception as e:
            logger.exception("Supports refresh failed")
            QMessageBox.warning(
                self, "Error",
                f"Failed to load pipe supports:\n{e}"
            )

    def _update_kpis(self, total: int, fab: int, inst: int,
                     acc: int, springs: int):
        self.kpi_total.set_value(str(total))
        self.kpi_fab.set_value(
            str(fab), highlight="blue" if fab > 0 else None
        )
        self.kpi_installed.set_value(
            str(inst), highlight="blue" if inst > 0 else None
        )
        self.kpi_accepted.set_value(
            str(acc),
            highlight=(
                "green" if acc == total and total > 0 else None
            ),
        )
        self.kpi_springs.set_value(
            str(springs), highlight="amber" if springs > 0 else None
        )

    def _apply_filters(self):
        query = self.txt_search.text().strip().lower()
        type_filter = self.cmb_filter_type.currentData()
        st_filter = self.cmb_filter_status.currentData()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for sp in self._cached_supports:
            if type_filter and sp["support_type"] != type_filter:
                continue
            if st_filter and sp["status"] != st_filter:
                continue
            if query:
                combined = (
                    f"{sp['support_tag']} {sp['support_type']} "
                    f"{sp['line_number']} {sp['iso_number']} "
                    f"{sp['drawing_no']} {sp['location_desc']} "
                    f"{sp['remarks']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.table.rowCount()
            self.table.insertRow(r)

            self.table.setItem(
                r, 0, QTableWidgetItem(str(sp["id"]))
            )
            self.table.setItem(
                r, 1, QTableWidgetItem(sp["support_tag"])
            )

            icon_str = next(
                (v for k, v in SUPPORT_TYPE_ICONS.items()
                 if k in sp["support_type"]),
                "🧱",
            )
            self.table.setItem(
                r, 2, QTableWidgetItem(
                    f"{icon_str} {sp['support_type']}"
                )
            )

            self.table.setItem(
                r, 3, QTableWidgetItem(sp["line_number"])
            )
            self.table.setItem(
                r, 4, QTableWidgetItem(sp["iso_number"])
            )
            self.table.setItem(
                r, 5, QTableWidgetItem(sp["drawing_no"])
            )

            st_item = QTableWidgetItem(sp["status"])
            badge = SUPPORT_STATUS_BADGES.get(
                sp["status"], DEFAULT_BADGE
            )
            st_item.setText(f"{badge['icon']} {sp['status']}")
            st_item.setBackground(QBrush(QColor(badge["bg"])))
            st_item.setForeground(QBrush(QColor(badge["fg"])))
            f = st_item.font()
            f.setBold(True)
            st_item.setFont(f)
            self.table.setItem(r, 6, st_item)

            self.table.setItem(
                r, 7, QTableWidgetItem(sp["location_desc"])
            )
            self.table.setItem(
                r, 8, QTableWidgetItem(sp["remarks"])
            )

        self.table.setSortingEnabled(True)

    # ══════════════════════════════════════════
    #  LOOKUP HELPER
    # ══════════════════════════════════════════
    def _get_project_lookups(self):
        with self.db.session_scope() as session:
            projects = (
                session.query(Project)
                .order_by(Project.project_code)
                .all()
            )
            return [
                type("P", (), {
                    "id": p.id,
                    "project_code": p.project_code,
                    "title": p.title,
                })()
                for p in projects
            ]

    # ══════════════════════════════════════════
    #  CRUD
    # ══════════════════════════════════════════
    def _add(self):
        proj_list = self._get_project_lookups()
        if not proj_list:
            QMessageBox.information(
                self, "Info",
                "Create a Project first in Project Setup."
            )
            return

        dlg = SupportDialog(self, projects=proj_list)
        if self.project_id:
            for i in range(dlg.project_combo.count()):
                if dlg.project_combo.itemData(i) == self.project_id:
                    dlg.project_combo.setCurrentIndex(i)
                    break

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.get_data()
        if not increment_usage(self.db):
            QMessageBox.warning(
                self, "License Limit",
                "Pipe support creation limit reached "
                "under current license."
            )
            return

        try:
            with self.db.session_scope() as s:
                s.add(PipeSupport(
                    project_id=d["project_id"],
                    support_tag=d["support_tag"],
                    support_type=d["support_type"],
                    line_number=d["line_number"],
                    iso_number=d["iso_number"],
                    drawing_no=d["drawing_no"],
                    location_desc=d["location_desc"],
                    status=d["status"],
                    remarks=d["remarks"],
                    # ✅ FIXED: use _utcnow() helper
                    created_at=_utcnow(),
                ))
            self.refresh()
            QMessageBox.information(
                self, "Success",
                f"Support '{d['support_tag']}' created."
            )
        except Exception as e:
            logger.exception("Failed to create support")
            QMessageBox.critical(
                self, "Error",
                f"Could not create support (Duplicate tag?):\n{e}"
            )

    def _edit_selected_support(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection", "Select a support to edit."
            )
            return

        sp_id = int(self.table.item(rows[0].row(), 0).text())
        sp_data = next(
            (x for x in self._cached_supports
             if x["id"] == sp_id), None
        )
        if not sp_data:
            return

        proj_list = self._get_project_lookups()
        dlg = SupportDialog(
            self, projects=proj_list, existing_data=sp_data
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.get_data()
        try:
            with self.db.session_scope() as s:
                # ✅ FIXED: SQLAlchemy 2.0 — s.get(Model, pk)
                sp = s.get(PipeSupport, sp_id)
                if sp:
                    sp.support_type = d["support_type"]
                    sp.line_number = d["line_number"]
                    sp.iso_number = d["iso_number"]
                    sp.drawing_no = d["drawing_no"]
                    sp.location_desc = d["location_desc"]
                    sp.status = d["status"]
                    if hasattr(sp, "remarks"):
                        sp.remarks = d["remarks"]
                    if (d["status"] in ("Installed", "Accepted")
                            and not getattr(
                                sp, "installed_date", None
                            )):
                        sp.installed_date = datetime.date.today()

            self.refresh()
            QMessageBox.information(
                self, "Updated",
                f"Support '{sp_data['support_tag']}' updated."
            )
        except Exception as e:
            logger.exception("Failed to edit support")
            QMessageBox.critical(
                self, "Error", f"Update failed:\n{e}"
            )

    def _delete_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select one or more supports to delete."
            )
            return

        sp_ids = [
            int(self.table.item(r.row(), 0).text()) for r in rows
        ]
        sp_tags = [
            self.table.item(r.row(), 1).text() for r in rows
        ]

        if QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(sp_ids)} pipe support(s)?\n\n"
            f"Supports: {', '.join(sp_tags[:5])}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as s:
                for sid in sp_ids:
                    # ✅ FIXED: SQLAlchemy 2.0
                    sp = s.get(PipeSupport, sid)
                    if sp:
                        s.delete(sp)

            self.refresh()
            QMessageBox.information(
                self, "Deleted", "Selected support(s) deleted."
            )
        except Exception as e:
            logger.exception("Failed to delete supports")
            QMessageBox.critical(
                self, "Error", f"Could not delete supports:\n{e}"
            )

    # ══════════════════════════════════════════
    #  STATUS TRANSITIONS
    # ══════════════════════════════════════════
    def _status(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select one or more supports to update."
            )
            return

        new_status = self.st_combo.currentText()
        self._quick_batch_status(new_status)

    def _quick_batch_status(self, new_status: str):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection", "Select at least one support."
            )
            return

        sp_ids = [
            int(self.table.item(r.row(), 0).text()) for r in rows
        ]
        try:
            with self.db.session_scope() as s:
                for sid in sp_ids:
                    # ✅ FIXED: SQLAlchemy 2.0
                    sp = s.get(PipeSupport, sid)
                    if sp:
                        sp.status = new_status
                        if (new_status in ("Installed", "Accepted")
                                and not getattr(
                                    sp, "installed_date", None
                                )):
                            sp.installed_date = datetime.date.today()

            self.refresh()
            QMessageBox.information(
                self, "Status Applied",
                f"Updated milestone to '{new_status}' for "
                f"{len(sp_ids)} support(s)."
            )
        except Exception as e:
            logger.exception("Failed to update support status")
            QMessageBox.critical(
                self, "Error", f"Failed to apply status:\n{e}"
            )

    # ══════════════════════════════════════════
    #  DETAIL VIEW / CONTEXT MENU
    # ══════════════════════════════════════════
    def _on_row_double_click(self, index):
        row = index.row()
        sp_id = int(self.table.item(row, 0).text())
        sp_data = next(
            (x for x in self._cached_supports
             if x["id"] == sp_id), None
        )
        if sp_data:
            dlg = SupportDetailDialog(self, support_data=sp_data)
            dlg.exec()

    def _show_context_menu(self, pos):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 18px; }"
        )

        act_dossier = QAction("🔍 View Support Dossier", self)
        act_dossier.triggered.connect(
            lambda: self._on_row_double_click(
                self.table.currentIndex()
            )
        )
        menu.addAction(act_dossier)

        act_edit = QAction("✏️ Edit Specifications", self)
        act_edit.triggered.connect(self._edit_selected_support)
        menu.addAction(act_edit)

        menu.addSeparator()

        act_deliv = QAction("🚚 Mark Delivered to Site", self)
        act_deliv.triggered.connect(
            lambda: self._quick_batch_status("Delivered to Site")
        )
        menu.addAction(act_deliv)

        act_install = QAction("🟢 Mark as Installed", self)
        act_install.triggered.connect(
            lambda: self._quick_batch_status("Installed")
        )
        menu.addAction(act_install)

        act_acc = QAction("✅ Mark QC Accepted", self)
        act_acc.triggered.connect(
            lambda: self._quick_batch_status("Accepted")
        )
        menu.addAction(act_acc)

        menu.addSeparator()

        act_copy = QAction("📋 Copy Support Tag", self)
        act_copy.triggered.connect(
            lambda: QApplication.clipboard().setText(
                self.table.item(rows[0].row(), 1).text()
            )
        )
        menu.addAction(act_copy)

        act_del = QAction("🗑️ Delete Support(s)", self)
        act_del.triggered.connect(self._delete_selected)
        menu.addAction(act_del)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ══════════════════════════════════════════
    #  EXPORT
    # ══════════════════════════════════════════
    def _export_supports_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(
                self, "Export",
                "No supports available to export."
            )
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_code = self.proj_combo.currentText().split("–")[0].strip()
        default_name = (
            f"Pipe_Supports_Register_{proj_code}_{timestamp}.csv"
        )

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Pipe Supports Register",
            default_name, "CSV Files (*.csv)",
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
                    if not self.table.isRowHidden(r):
                        row_vals = [
                            self.table.item(r, c).text().strip()
                            if self.table.item(r, c) else ""
                            for c in range(1, self.table.columnCount())
                        ]
                        writer.writerow(row_vals)

            QMessageBox.information(
                self, "Export Complete",
                f"Support register exported successfully to:\n"
                f"{filename}"
            )
        except Exception as e:
            logger.exception("Failed to export support CSV")
            QMessageBox.critical(
                self, "Export Error",
                f"Could not create CSV file:\n{e}"
            )