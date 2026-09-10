# -*- coding: utf-8 -*-
# ui/tabs/spooling_tab.py – PipeAgent 5.3.0
# Shop Fabrication Spool Management, Status Tracking & Field Dispatch Hub
from __future__ import annotations

import csv
import logging
import datetime
from datetime import timezone
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QFrame, QFileDialog,
    QApplication, QMenu, QAbstractItemView, QGroupBox,
    QDoubleSpinBox,
)
from PyQt6.QtGui import QColor, QFont, QBrush, QCursor, QAction

from db.manager import DatabaseManager
from db.models import Spool, Project, Area, Weld, LineListItem
from security.session import SessionManager

# ── Spool statuses (fallback if config missing) ────────────────
try:
    from config import SPOOL_STATUSES
except ImportError:
    SPOOL_STATUSES = [
        "Draft", "In Fabrication", "Fitting / Fit-up", "Welded",
        "NDT Complete", "PWHT Done", "Hydro Tested", "Painted / Coated",
        "Released to Site", "Installed", "On Hold",
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
SPOOL_STATUS_BADGES = {
    "Installed":         {"bg": "#dcfce7", "fg": "#166534", "icon": "🟢"},
    "Released to Site":  {"bg": "#e0f2fe", "fg": "#075985", "icon": "🚚"},
    "Hydro Tested":      {"bg": "#e0e7ff", "fg": "#3730a3", "icon": "💧"},
    "Painted / Coated":  {"bg": "#fce7f3", "fg": "#9d174d", "icon": "🎨"},
    "NDT Complete":      {"bg": "#ffedd5", "fg": "#9a3412", "icon": "🛡️"},
    "Welded":            {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "🔥"},
    "In Fabrication":    {"bg": "#fef3c7", "fg": "#92400e", "icon": "⚙️"},
    "Fitting / Fit-up":  {"bg": "#fff1e6", "fg": "#9a3412", "icon": "🔧"},
    "Draft":             {"bg": "#f1f5f9", "fg": "#475569", "icon": "📝"},
    "On Hold":           {"bg": "#fee2e2", "fg": "#991b1b", "icon": "⏸️"},
    "PWHT Done":         {"bg": "#fce7f3", "fg": "#9d174d", "icon": "🌡️"},
}
DEFAULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}


# ─────────────────────────────────────────────
#  STYLESHEET
# ─────────────────────────────────────────────
SPOOLING_STYLESHEET = """
    QWidget#spoolingTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #102a43, stop:1 #1e3a5f);
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
    QLineEdit, QComboBox, QDoubleSpinBox {
        padding: 6px 10px; border: 1px solid #cbd5e1;
        border-radius: 6px; font-size: 12px;
    }
"""


# ─────────────────────────────────────────────
#  KPI CARD
# ─────────────────────────────────────────────
class SpoolKPICard(QFrame):
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
#  SPOOL DIALOG
# ─────────────────────────────────────────────
class SpoolDialog(QDialog):
    def __init__(self, parent=None, projects: list = None,
                 areas: list = None,
                 existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = existing_data is not None
        self.setWindowTitle(
            "Edit Spool Specifications" if self.is_edit
            else "Register New Pipe Spool"
        )
        self.setMinimumWidth(500)
        self.setStyleSheet(SPOOLING_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.project_combo = QComboBox()
        if projects:
            for p in projects:
                self.project_combo.addItem(
                    f"{p.project_code} – {p.title}", p.id
                )

        self.area_combo = QComboBox()
        self.area_combo.addItem("(None / General)", None)
        if areas:
            for a in areas:
                self.area_combo.addItem(a.name, a.id)

        self.spool_edit = QLineEdit()
        self.spool_edit.setPlaceholderText(
            'e.g. SP-01 or 6"-PL-1001-01'
        )

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText('e.g. 6"-PL-1001-A1A')

        self.iso_edit = QLineEdit()
        self.iso_edit.setPlaceholderText("e.g. ISO-1001-SHT-01")

        self.class_edit = QLineEdit()
        self.class_edit.setPlaceholderText("e.g. CS150 / A1A")

        self.weight_edit = QDoubleSpinBox()
        self.weight_edit.setRange(0, 100000)
        self.weight_edit.setDecimals(2)
        self.weight_edit.setSuffix(" kg")

        self.surface_edit = QDoubleSpinBox()
        self.surface_edit.setRange(0, 10000)
        self.surface_edit.setDecimals(2)
        self.surface_edit.setSuffix(" m²")

        self.status_combo = QComboBox()
        self.status_combo.addItems(SPOOL_STATUSES)

        form.addRow("Project *:", self.project_combo)
        form.addRow("Process Area / Unit:", self.area_combo)
        form.addRow("Spool Number *:", self.spool_edit)
        form.addRow("Piping Line Number *:", self.line_edit)
        form.addRow("Isometric DWG Reference:", self.iso_edit)
        form.addRow("Pipe Material Class:", self.class_edit)
        form.addRow("Estimated Weight:", self.weight_edit)
        form.addRow("Painting Surface Area:", self.surface_edit)
        form.addRow("Fabrication Milestone *:", self.status_combo)
        layout.addLayout(form)

        if self.is_edit and existing_data:
            pid = existing_data.get("project_id")
            for i in range(self.project_combo.count()):
                if self.project_combo.itemData(i) == pid:
                    self.project_combo.setCurrentIndex(i)
                    break
            aid = existing_data.get("area_id")
            for i in range(self.area_combo.count()):
                if self.area_combo.itemData(i) == aid:
                    self.area_combo.setCurrentIndex(i)
                    break
            self.spool_edit.setText(
                existing_data.get("spool_number", "")
            )
            self.spool_edit.setReadOnly(True)
            self.line_edit.setText(
                existing_data.get("line_number", "")
            )
            self.iso_edit.setText(
                existing_data.get("iso_number", "")
            )
            self.class_edit.setText(
                existing_data.get("pipe_class", "")
            )
            self.weight_edit.setValue(
                float(existing_data.get("weight_kg") or 0.0)
            )
            self.surface_edit.setValue(
                float(existing_data.get("surface_area_m2") or 0.0)
            )
            self.status_combo.setCurrentText(
                existing_data.get("status", SPOOL_STATUSES[0])
            )

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Spool")
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
        if not self.spool_edit.text().strip():
            QMessageBox.warning(
                self, "Validation", "Spool Number is mandatory."
            )
            self.spool_edit.setFocus()
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
            "area_id": self.area_combo.currentData(),
            "spool_number": self.spool_edit.text().strip(),
            "line_number": self.line_edit.text().strip(),
            "iso_number": self.iso_edit.text().strip(),
            "pipe_class": self.class_edit.text().strip(),
            "weight_kg": (
                self.weight_edit.value()
                if self.weight_edit.value() > 0 else None
            ),
            "surface_area_m2": (
                self.surface_edit.value()
                if self.surface_edit.value() > 0 else None
            ),
            "status": self.status_combo.currentText(),
        }


# ─────────────────────────────────────────────
#  SPOOL DETAIL DIALOG
# ─────────────────────────────────────────────
class SpoolDetailDialog(QDialog):
    def __init__(self, parent=None, spool_data: dict = None,
                 child_welds: list = None):
        super().__init__(parent)
        self.setWindowTitle(
            f"🔍 Spool Fabrication Dossier – "
            f"{spool_data.get('spool_number', 'Spool')}"
        )
        self.setMinimumSize(640, 520)
        self.setStyleSheet(SPOOLING_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hdr = QLabel(
            f"📋 Fabrication Dossier: {spool_data.get('spool_number')}"
        )
        hdr.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #102a43;"
        )
        layout.addWidget(hdr)

        # Engineering specs
        info_box = QGroupBox("Spool Engineering Specifications")
        info_grid = QGridLayout(info_box)
        info_grid.setSpacing(8)

        details = [
            ("Spool Identifier:", spool_data.get("spool_number", "—")),
            ("Piping Line No:", spool_data.get("line_number", "—")),
            ("Isometric Drawing:", spool_data.get("iso_number", "—")),
            ("Pipe Material Class:", spool_data.get("pipe_class", "—")),
            ("Process Unit / Area:", spool_data.get("area_name", "General")),
            ("Current Milestone:", spool_data.get("status", "Draft")),
            ("Calculated Weight:",
             f"{spool_data.get('weight_kg') or '—'} kg"),
            ("Painting Surface:",
             f"{spool_data.get('surface_area_m2') or '—'} m²"),
            ("Created Date:", str(spool_data.get("created_at", "—"))),
            ("Erection / Site Date:",
             str(spool_data.get("installed_date", "—"))),
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

        # Child welds
        child_welds = child_welds or []
        weld_box = QGroupBox(
            f"Attached Welds & Joints in Spool "
            f"({len(child_welds)} Joints)"
        )
        weld_lay = QVBoxLayout(weld_box)
        weld_tbl = QTableWidget(0, 5)
        weld_tbl.setHorizontalHeaderLabels([
            "Weld ID", "Joint Type", "Size", "Welder", "QC Status",
        ])
        weld_tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        weld_tbl.setAlternatingRowColors(True)
        weld_tbl.verticalHeader().setVisible(False)

        for w in child_welds:
            row = weld_tbl.rowCount()
            weld_tbl.insertRow(row)
            weld_tbl.setItem(
                row, 0, QTableWidgetItem(w.get("weld_id", ""))
            )
            weld_tbl.setItem(
                row, 1, QTableWidgetItem(w.get("joint_type", ""))
            )
            weld_tbl.setItem(
                row, 2, QTableWidgetItem(w.get("size", ""))
            )
            weld_tbl.setItem(
                row, 3, QTableWidgetItem(w.get("welder_id", ""))
            )
            weld_tbl.setItem(
                row, 4, QTableWidgetItem(w.get("status", "Pending"))
            )

        weld_lay.addWidget(weld_tbl)
        layout.addWidget(weld_box)

        btn_close = QPushButton("Close Dossier")
        btn_close.setObjectName("secondaryBtn")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class SpoolingTab(QWidget):
    def __init__(self, db: DatabaseManager, session: SessionManager):
        super().__init__()
        self.setObjectName("spoolingTab")
        self.db = db
        self.session = session
        self.project_id: Optional[int] = None
        self._cached_spools: list[dict] = []

        self._build_ui()
        self.setStyleSheet(SPOOLING_STYLESHEET)
        self._load_projects()

    # ══════════════════════════════════════════════════════
    #  UI BUILD
    # ══════════════════════════════════════════════════════
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
        t = QLabel("🔩 Spool Fabrication & Shop Tracking")
        t.setObjectName("mainTitle")
        s = QLabel(
            "Shop Fabrication Lifecycle: Spool Fit-up, Welding, "
            "NDT/Hydro Testing, Coating, Site Clearance & Erection."
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

        self.kpi_total = SpoolKPICard(
            "Total Spools in Scope", "🔩", "#3b82f6"
        )
        self.kpi_in_shop = SpoolKPICard(
            "In-Shop Fabrication", "⚙️", "#f59e0b"
        )
        self.kpi_tested = SpoolKPICard(
            "NDT / Hydro Passed", "🛡️", "#8b5cf6"
        )
        self.kpi_released = SpoolKPICard(
            "Released to Site", "🚚", "#0ea5e9"
        )
        self.kpi_installed = SpoolKPICard(
            "Installed on Site", "🟢", "#10b981"
        )

        for k in (self.kpi_total, self.kpi_in_shop, self.kpi_tested,
                  self.kpi_released, self.kpi_installed):
            kpi_lay.addWidget(k)
        layout.addLayout(kpi_lay)

        # Filters
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
            "🔍 Search Spool No, Line No, ISO, Pipe Class, Area..."
        )
        self.txt_search.textChanged.connect(self._apply_filters)
        filter_lay.addWidget(self.txt_search, 1)

        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.addItem("All Statuses", None)
        for st in SPOOL_STATUSES:
            self.cmb_filter_status.addItem(st, st)
        self.cmb_filter_status.currentIndexChanged.connect(
            self._apply_filters
        )
        filter_lay.addWidget(self.cmb_filter_status)

        self.cmb_filter_area = QComboBox()
        self.cmb_filter_area.addItem("All Process Areas", None)
        self.cmb_filter_area.currentIndexChanged.connect(
            self._apply_filters
        )
        filter_lay.addWidget(self.cmb_filter_area)

        btn_new = QPushButton("➕ New Spool")
        btn_new.setObjectName("primaryBtn")
        btn_new.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_new.clicked.connect(self._on_new)
        filter_lay.addWidget(btn_new)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(self._export_spools_csv)
        filter_lay.addWidget(btn_exp)

        btn_del = QPushButton("🗑️ Delete")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete_selected)
        filter_lay.addWidget(btn_del)

        layout.addWidget(filter_card)

        # Main table
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Spool Identifier", "Piping Line No", "ISO DWG Ref",
            "Pipe Class", "Milestone Status", "Process Area",
            "Created Date",
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
            "Batch Transition Selected Spools To:"
        )
        lbl_batch.setStyleSheet("font-weight: bold; color: #334155;")
        status_row.addWidget(lbl_batch)

        self.status_combo = QComboBox()
        self.status_combo.addItems(SPOOL_STATUSES)
        status_row.addWidget(self.status_combo)

        btn_apply = QPushButton("Apply Milestone")
        btn_apply.setObjectName("secondaryBtn")
        btn_apply.clicked.connect(self._on_change_status)
        status_row.addWidget(btn_apply)

        btn_release = QPushButton("🚚 Release to Site")
        btn_release.setObjectName("secondaryBtn")
        btn_release.clicked.connect(
            lambda: self._quick_batch_status("Released to Site")
        )
        status_row.addWidget(btn_release)

        btn_install = QPushButton("🟢 Mark Installed")
        btn_install.setObjectName("secondaryBtn")
        btn_install.clicked.connect(
            lambda: self._quick_batch_status("Installed")
        )
        status_row.addWidget(btn_install)

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
                for p in s.query(Project).order_by(Project.project_code):
                    self.proj_combo.addItem(
                        f"{p.project_code} – {p.title}", p.id
                    )
        except Exception:
            logger.exception(
                "Failed to load projects in SpoolingTab"
            )

        self.proj_combo.blockSignals(False)
        if self.proj_combo.count():
            self._on_project_changed()

    def _on_project_changed(self):
        self.project_id = self.proj_combo.currentData()
        self._load_areas_filter()
        self.refresh()

    def _load_areas_filter(self):
        self.cmb_filter_area.blockSignals(True)
        self.cmb_filter_area.clear()
        self.cmb_filter_area.addItem("All Process Areas", None)
        if self.project_id:
            try:
                with self.db.session_scope() as s:
                    areas = (
                        s.query(Area)
                        .filter(Area.project_id == self.project_id)
                        .order_by(Area.name)
                        .all()
                    )
                    for a in areas:
                        self.cmb_filter_area.addItem(a.name, a.id)
            except Exception:
                logger.exception("Failed to load area filters")
        self.cmb_filter_area.blockSignals(False)

    # ══════════════════════════════════════════
    #  REFRESH
    # ══════════════════════════════════════════
    def refresh(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._cached_spools = []

        if not self.project_id:
            self._update_kpis(0, 0, 0, 0, 0)
            return

        try:
            with self.db.session_scope() as session:
                spools = (
                    session.query(Spool)
                    .filter(Spool.project_id == self.project_id)
                    .order_by(Spool.spool_number)
                    .all()
                )
                area_map = {
                    a.id: a.name
                    for a in session.query(Area)
                    .filter(Area.project_id == self.project_id)
                    .all()
                }

                shop_cnt = tested_cnt = released_cnt = installed_cnt = 0

                for s in spools:
                    st = s.status or "Draft"
                    if st in ("In Fabrication", "Fitting / Fit-up",
                              "Welded", "Draft"):
                        shop_cnt += 1
                    elif st in ("NDT Complete", "Hydro Tested",
                                "PWHT Done", "Painted / Coated"):
                        tested_cnt += 1
                    elif st == "Released to Site":
                        released_cnt += 1
                    elif st == "Installed":
                        installed_cnt += 1

                    self._cached_spools.append({
                        "id": s.id,
                        "project_id": s.project_id,
                        "area_id": s.area_id,
                        "area_name": area_map.get(s.area_id, "General"),
                        "spool_number": s.spool_number,
                        "line_number": s.line_number or "",
                        "iso_number": (
                            getattr(s, "iso_number", "") or ""
                        ),
                        "pipe_class": s.pipe_class or "",
                        "weight_kg": getattr(s, "weight_kg", None),
                        "surface_area_m2": getattr(
                            s, "surface_area_m2", None
                        ),
                        "status": st,
                        "created_at": (
                            s.created_at.strftime("%Y-%m-%d")
                            if s.created_at else ""
                        ),
                        "installed_date": (
                            getattr(s, "installed_date", "") or ""
                        ),
                    })

                self._update_kpis(
                    len(spools), shop_cnt, tested_cnt,
                    released_cnt, installed_cnt,
                )
                self._apply_filters()

        except Exception as e:
            logger.exception("Spool refresh failed")
            QMessageBox.warning(
                self, "Error", f"Failed to load spools:\n{e}"
            )

    def _update_kpis(self, total: int, shop: int, tested: int,
                     released: int, installed: int):
        self.kpi_total.set_value(str(total))
        self.kpi_in_shop.set_value(
            str(shop), highlight="amber" if shop > 0 else None
        )
        self.kpi_tested.set_value(
            str(tested), highlight="blue" if tested > 0 else None
        )
        self.kpi_released.set_value(
            str(released), highlight="blue" if released > 0 else None
        )
        self.kpi_installed.set_value(
            str(installed),
            highlight=(
                "green" if installed == total and total > 0 else None
            ),
        )

    def _apply_filters(self):
        query = self.txt_search.text().strip().lower()
        st_filter = self.cmb_filter_status.currentData()
        area_filter = self.cmb_filter_area.currentData()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for s in self._cached_spools:
            if st_filter and s["status"] != st_filter:
                continue
            if area_filter and s["area_id"] != area_filter:
                continue
            if query:
                combined = (
                    f"{s['spool_number']} {s['line_number']} "
                    f"{s['iso_number']} {s['pipe_class']} "
                    f"{s['area_name']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.table.rowCount()
            self.table.insertRow(r)

            self.table.setItem(
                r, 0, QTableWidgetItem(str(s["id"]))
            )
            self.table.setItem(
                r, 1, QTableWidgetItem(s["spool_number"])
            )
            self.table.setItem(
                r, 2, QTableWidgetItem(s["line_number"])
            )
            self.table.setItem(
                r, 3, QTableWidgetItem(s["iso_number"])
            )
            self.table.setItem(
                r, 4, QTableWidgetItem(s["pipe_class"])
            )

            st_item = QTableWidgetItem(s["status"])
            badge = SPOOL_STATUS_BADGES.get(
                s["status"], DEFAULT_BADGE
            )
            st_item.setText(f"{badge['icon']} {s['status']}")
            st_item.setBackground(QBrush(QColor(badge["bg"])))
            st_item.setForeground(QBrush(QColor(badge["fg"])))
            f = st_item.font()
            f.setBold(True)
            st_item.setFont(f)
            self.table.setItem(r, 5, st_item)

            self.table.setItem(
                r, 6, QTableWidgetItem(s["area_name"])
            )
            self.table.setItem(
                r, 7, QTableWidgetItem(s["created_at"])
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
            areas = (
                session.query(Area)
                .filter(Area.project_id == self.project_id)
                .order_by(Area.name)
                .all()
                if self.project_id else []
            )
            proj_list = [
                type("P", (), {
                    "id": p.id,
                    "project_code": p.project_code,
                    "title": p.title,
                })()
                for p in projects
            ]
            area_list = [
                type("A", (), {"id": a.id, "name": a.name})()
                for a in areas
            ]
            return proj_list, area_list

    # ══════════════════════════════════════════
    #  CRUD
    # ══════════════════════════════════════════
    def _on_new(self):
        proj_list, area_list = self._get_project_lookups()
        if not proj_list:
            QMessageBox.information(
                self, "Info",
                "Create a Project first in Project Setup."
            )
            return

        dlg = SpoolDialog(self, projects=proj_list, areas=area_list)
        if self.project_id:
            for i in range(dlg.project_combo.count()):
                if dlg.project_combo.itemData(i) == self.project_id:
                    dlg.project_combo.setCurrentIndex(i)
                    break

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        try:
            with self.db.session_scope() as session:
                spool = Spool(
                    project_id=data["project_id"],
                    area_id=data["area_id"],
                    spool_number=data["spool_number"],
                    line_number=data["line_number"],
                    iso_number=data["iso_number"],
                    pipe_class=data["pipe_class"],
                    status=data["status"],
                    # ✅ FIXED: use _utcnow() helper
                    created_at=_utcnow(),
                )
                session.add(spool)

            self.refresh()
            QMessageBox.information(
                self, "Success",
                f"Spool '{data['spool_number']}' registered."
            )
        except Exception as e:
            logger.exception("Failed to create spool")
            QMessageBox.critical(
                self, "Error",
                f"Could not create spool "
                f"(Duplicate identifier?):\n{e}"
            )

    def _edit_selected_spool(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection", "Select a spool to edit."
            )
            return

        spool_id = int(self.table.item(rows[0].row(), 0).text())
        spool_data = next(
            (x for x in self._cached_spools if x["id"] == spool_id),
            None,
        )
        if not spool_data:
            return

        proj_list, area_list = self._get_project_lookups()
        dlg = SpoolDialog(
            self, projects=proj_list, areas=area_list,
            existing_data=spool_data,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        try:
            with self.db.session_scope() as session:
                # ✅ FIXED: SQLAlchemy 2.0 — session.get(Model, pk)
                s = session.get(Spool, spool_id)
                if s:
                    s.area_id = data["area_id"]
                    s.line_number = data["line_number"]
                    s.iso_number = data["iso_number"]
                    s.pipe_class = data["pipe_class"]
                    s.status = data["status"]
                    if hasattr(s, "weight_kg"):
                        s.weight_kg = data["weight_kg"]
                    if hasattr(s, "surface_area_m2"):
                        s.surface_area_m2 = data["surface_area_m2"]

            self.refresh()
            QMessageBox.information(
                self, "Updated",
                f"Spool '{spool_data['spool_number']}' updated."
            )
        except Exception as e:
            logger.exception("Failed to edit spool")
            QMessageBox.critical(
                self, "Error", f"Update failed:\n{e}"
            )

    def _delete_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select one or more spools to delete."
            )
            return

        spool_ids = [
            int(self.table.item(r.row(), 0).text()) for r in rows
        ]
        spool_nos = [
            self.table.item(r.row(), 1).text() for r in rows
        ]

        if QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(spool_ids)} spool(s)?\n\n"
            f"Spools: {', '.join(spool_nos[:5])}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as session:
                for sid in spool_ids:
                    # ✅ FIXED: SQLAlchemy 2.0
                    s = session.get(Spool, sid)
                    if s:
                        session.delete(s)

            self.refresh()
            QMessageBox.information(
                self, "Deleted", "Selected spool(s) deleted."
            )
        except Exception as e:
            logger.exception("Failed to delete spools")
            QMessageBox.critical(
                self, "Error", f"Could not delete spools:\n{e}"
            )

    # ══════════════════════════════════════════
    #  STATUS TRANSITIONS
    # ══════════════════════════════════════════
    def _on_change_status(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select one or more spools to update."
            )
            return

        new_status = self.status_combo.currentText()
        self._quick_batch_status(new_status)

    def _quick_batch_status(self, new_status: str):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection", "Select at least one spool."
            )
            return

        spool_ids = [
            int(self.table.item(r.row(), 0).text()) for r in rows
        ]
        try:
            with self.db.session_scope() as session:
                for sid in spool_ids:
                    # ✅ FIXED: SQLAlchemy 2.0
                    spool = session.get(Spool, sid)
                    if spool:
                        spool.status = new_status
                        if (new_status == "Installed"
                                and not getattr(
                                    spool, "installed_date", None
                                )):
                            spool.installed_date = (
                                datetime.date.today()
                            )

            self.refresh()
            QMessageBox.information(
                self, "Status Applied",
                f"Updated milestone to '{new_status}' for "
                f"{len(spool_ids)} spool(s)."
            )
        except Exception as e:
            logger.exception("Failed to update spool status")
            QMessageBox.critical(
                self, "Error", f"Failed to apply status:\n{e}"
            )

    # ══════════════════════════════════════════
    #  DETAIL VIEW / CONTEXT MENU
    # ══════════════════════════════════════════
    def _on_row_double_click(self, index):
        row = index.row()
        spool_id = int(self.table.item(row, 0).text())
        spool_data = next(
            (x for x in self._cached_spools if x["id"] == spool_id),
            None,
        )
        if not spool_data:
            return

        # Load child welds
        child_welds = []
        with self.db.session_scope() as s:
            welds = (
                s.query(Weld)
                .filter(Weld.spool_id == spool_id)
                .all()
            )
            if not welds:
                welds = (
                    s.query(Weld)
                    .filter(
                        Weld.project_id == self.project_id,
                        Weld.line_number == spool_data["line_number"],
                    )
                    .all()
                )
            for w in welds:
                child_welds.append({
                    "weld_id": w.weld_id,
                    "joint_type": w.joint_type or "BW",
                    "size": w.size or "—",
                    "welder_id": w.welder_id or "—",
                    "status": w.status or "Pending",
                })

        dlg = SpoolDetailDialog(
            self, spool_data=spool_data, child_welds=child_welds
        )
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

        act_dossier = QAction("🔍 View Spool Dossier", self)
        act_dossier.triggered.connect(
            lambda: self._on_row_double_click(
                self.table.currentIndex()
            )
        )
        menu.addAction(act_dossier)

        act_edit = QAction("✏️ Edit Spool Specs", self)
        act_edit.triggered.connect(self._edit_selected_spool)
        menu.addAction(act_edit)

        menu.addSeparator()

        act_release = QAction("🚚 Dispatch / Release to Site", self)
        act_release.triggered.connect(
            lambda: self._quick_batch_status("Released to Site")
        )
        menu.addAction(act_release)

        act_install = QAction("🟢 Mark as Installed on Site", self)
        act_install.triggered.connect(
            lambda: self._quick_batch_status("Installed")
        )
        menu.addAction(act_install)

        menu.addSeparator()

        act_copy = QAction("📋 Copy Spool Number", self)
        act_copy.triggered.connect(
            lambda: QApplication.clipboard().setText(
                self.table.item(rows[0].row(), 1).text()
            )
        )
        menu.addAction(act_copy)

        act_del = QAction("🗑️ Delete Spool(s)", self)
        act_del.triggered.connect(self._delete_selected)
        menu.addAction(act_del)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ══════════════════════════════════════════
    #  EXPORT
    # ══════════════════════════════════════════
    def _export_spools_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(
                self, "Export",
                "No spools available to export."
            )
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_code = self.proj_combo.currentText().split("–")[0].strip()
        default_name = (
            f"Spool_Fabrication_Register_{proj_code}_{timestamp}.csv"
        )

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Spool Fabrication Register",
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
                f"Spool register exported successfully to:\n"
                f"{filename}"
            )
        except Exception as e:
            logger.exception("Failed to export spool CSV")
            QMessageBox.critical(
                self, "Export Error",
                f"Could not create CSV file:\n{e}"
            )