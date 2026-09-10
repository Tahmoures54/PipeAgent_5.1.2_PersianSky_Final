# -*- coding: utf-8 -*-
# ui/tabs/project_setup_tab.py – PipeAgent
# Master Project & Process Unit / Area Setup & Configuration
#
# Fully redesigned with:
# • Real-time Multivariable Search & Filter Engine for Projects & Plant Areas
# • Dynamic KPI Summary Metric Cards (Active Projects, Units, Piping Standards, Line Counts)
# • Full CRUD Support for Projects & Areas (Add, Edit, Safe Cascade Delete)
# • Master-Detail Splitter Layout with Linked Process Area Exploration
# • Color-coded Visual Badges for Design Standards (ASME B31.3, B31.1, B31.4, B31.8, API 1104)
# • Detailed Project Dossier & Plant Boundary Scope Dialog
# • CSV Log Sheet Export Engine for Projects & Unit WBS Breakdowns
# • Comprehensive Right-Click Context Menus with Quick Actions

from __future__ import annotations

import csv
import logging
import datetime
from pathlib import Path
from typing import Optional, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QTextEdit, QSplitter, QFrame, QFileDialog,
    QApplication, QMenu, QAbstractItemView, QGroupBox
)
from PyQt6.QtGui import QColor, QFont, QBrush, QCursor, QAction

from db.manager import DatabaseManager
from db.models import Project, Area, LineListItem, Weld, Spool
from security.session import SessionManager

# Implementation note.
try:
    from config import PIPING_CODES
except ImportError:
    PIPING_CODES = [
        "ASME B31.3 (Process Piping)",
        "ASME B31.1 (Power Piping)",
        "ASME B31.4 (Liquid Transportation)",
        "ASME B31.8 (Gas Transmission & Distribution)",
        "ASME B31.12 (Hydrogen Piping)",
        "API 1104 (Pipeline Welding)",
        "EN 13480 (Metallic Industrial Piping)"
    ]

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

STANDARD_BADGES = {
    "ASME B31.3": {"bg": "#dbeafe", "fg": "#1e40af", "icon": "📘"},
    "ASME B31.1": {"bg": "#fef3c7", "fg": "#92400e", "icon": "⚡"},
    "ASME B31.4": {"bg": "#e0f2fe", "fg": "#075985", "icon": "🛢️"},
    "ASME B31.8": {"bg": "#ffedd5", "fg": "#9a3412", "icon": "🔥"},
    "API 1104":   {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "🛡️"},
    "EN 13480":   {"bg": "#ecfdf5", "fg": "#065f46", "icon": "🇪🇺"},
}
DEFAULT_STANDARD_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "📐"}

# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

PROJECT_SETUP_STYLESHEET = """
    QWidget#projectSetupTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0b2545, stop:1 #134074);
        border-radius: 12px;
        padding: 14px;
    }
    QLabel#mainTitle {
        color: #ffffff;
        font-size: 22px;
        font-weight: 800;
        font-family: 'Segoe UI', sans-serif;
    }
    QLabel#subTitle {
        color: #94a3b8;
        font-size: 12px;
    }
    QFrame#kpiCard {
        background: white;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 10px;
    }
    QLabel#kpiTitle {
        font-size: 11px;
        font-weight: 700;
        color: #64748b;
        text-transform: uppercase;
    }
    QLabel#kpiValue {
        font-size: 19px;
        font-weight: 800;
        color: #0f172a;
    }
    QGroupBox {
        font-size: 12px;
        font-weight: 800;
        color: #1e293b;
        border: 2px solid #cbd5e1;
        border-radius: 8px;
        margin-top: 10px;
        padding-top: 14px;
        background: white;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 0 4px;
        background: white;
    }
    QTableWidget {
        background: white;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        gridline-color: #f1f5f9;
        font-size: 12px;
    }
    QTableWidget::item:selected {
        background: #e0f2fe;
        color: #0369a1;
    }
    QHeaderView::section {
        background: #f8fafc;
        color: #334155;
        font-weight: 700;
        font-size: 11px;
        padding: 7px;
        border: none;
        border-bottom: 2px solid #cbd5e1;
        border-right: 1px solid #f1f5f9;
    }
    QPushButton#primaryBtn {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #2563eb);
        color: white; border: none; padding: 7px 15px; border-radius: 6px; font-weight: 700;
    }
    QPushButton#primaryBtn:hover {
        background: #1d4ed8;
    }
    QPushButton#secondaryBtn {
        background: white; color: #334155; border: 1px solid #cbd5e1;
        padding: 6px 12px; border-radius: 6px; font-weight: 600;
    }
    QPushButton#secondaryBtn:hover {
        background: #f8fafc; border-color: #3b82f6; color: #3b82f6;
    }
    QPushButton#dangerBtn {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ef4444, stop:1 #dc2626);
        color: white; border: none; padding: 6px 12px; border-radius: 6px; font-weight: 700;
    }
    QPushButton#dangerBtn:hover {
        background: #b91c1c;
    }
    QLineEdit, QComboBox, QTextEdit {
        padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 12px;
    }
"""

# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class ProjectKPICard(QFrame):
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
            self.val_lbl.setStyleSheet("color: #166534; font-size: 19px; font-weight: 800;")
        elif highlight == "blue":
            self.val_lbl.setStyleSheet("color: #0369a1; font-size: 19px; font-weight: 800;")
        else:
            self.val_lbl.setStyleSheet("color: #0f172a; font-size: 19px; font-weight: 800;")


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class ProjectDialog(QDialog):
    """دیالوگ ایجاد و ویرایش مشخصات مهندسی پروژه"""

    def __init__(self, parent=None, project_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = project_data is not None
        self.setWindowTitle("Edit Project Specifications" if self.is_edit else "Register New Piping Project")
        self.setMinimumWidth(500)
        self.setStyleSheet(PROJECT_SETUP_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("Unique Project Code (e.g. PRJ-2024-01)")

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Official Project Title (e.g. Flare Gas Recovery Unit)")

        self.client_edit = QLineEdit()
        self.client_edit.setPlaceholderText("Owner / Client Name (e.g. National Oil Company)")

        self.contractor_edit = QLineEdit()
        self.contractor_edit.setPlaceholderText("EPC / General Contractor Name")

        self.standard_combo = QComboBox()
        self.standard_combo.addItems(PIPING_CODES)
        self.standard_combo.setEditable(True)

        self.location_edit = QLineEdit()
        self.location_edit.setPlaceholderText("Site / Plant Location (e.g. Refinery Complex Sector B)")

        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("Project scope summary, engineering battery limits, notes...")
        self.description_edit.setMaximumHeight(75)

        form.addRow("Project Code *:", self.code_edit)
        form.addRow("Project Title *:", self.title_edit)
        form.addRow("Client / Owner:", self.client_edit)
        form.addRow("EPC Contractor:", self.contractor_edit)
        form.addRow("Governing Piping Code *:", self.standard_combo)
        form.addRow("Site Location:", self.location_edit)
        form.addRow("Scope / Description:", self.description_edit)
        layout.addLayout(form)

        if self.is_edit and project_data:
            self.code_edit.setText(project_data.get("project_code", ""))
            self.code_edit.setReadOnly(True)  # Implementation note.
            self.title_edit.setText(project_data.get("title", ""))
            self.client_edit.setText(project_data.get("client", ""))
            self.contractor_edit.setText(project_data.get("contractor", ""))
            
            std_val = project_data.get("standard", "")
            idx = self.standard_combo.findText(std_val)
            if idx >= 0:
                self.standard_combo.setCurrentIndex(idx)
            else:
                self.standard_combo.setCurrentText(std_val)

            self.location_edit.setText(project_data.get("location", ""))
            self.description_edit.setPlainText(project_data.get("description", ""))

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Project")
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
        if not self.code_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Project Code is mandatory.")
            self.code_edit.setFocus()
            return
        if not self.title_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Project Title is mandatory.")
            self.title_edit.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "project_code": self.code_edit.text().strip(),
            "title": self.title_edit.text().strip(),
            "client": self.client_edit.text().strip(),
            "contractor": self.contractor_edit.text().strip(),
            "standard": self.standard_combo.currentText().strip(),
            "location": self.location_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip(),
        }


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class AreaDialog(QDialog):
    """دیالوگ ایجاد و ویرایش یونیت‌ها و نواحی فرآیندی پروژه"""

    def __init__(self, parent=None, area_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = area_data is not None
        self.setWindowTitle("Edit Process Area" if self.is_edit else "Register Process Area / Unit")
        self.setMinimumWidth(440)
        self.setStyleSheet(PROJECT_SETUP_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Area / Unit Tag (e.g. Unit 100 – Distillation)")

        self.code_tag_edit = QLineEdit()
        self.code_tag_edit.setPlaceholderText("Short Code (e.g. U-100 / AREA-A)")

        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("Process boundaries, equipment limits, notes...")
        self.desc_edit.setMaximumHeight(80)

        form.addRow("Area / Unit Name *:", self.name_edit)
        form.addRow("Short Code / Tag:", self.code_tag_edit)
        form.addRow("Process Description:", self.desc_edit)
        layout.addLayout(form)

        if self.is_edit and area_data:
            self.name_edit.setText(area_data.get("name", ""))
            self.code_tag_edit.setText(area_data.get("code_tag", ""))
            self.desc_edit.setPlainText(area_data.get("description", ""))

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Area")
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
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Area / Unit Name is required.")
            self.name_edit.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "code_tag": self.code_tag_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip(),
        }


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class ProjectOverviewDialog(QDialog):
    def __init__(self, parent=None, project_data: dict = None, metrics: dict = None):
        super().__init__(parent)
        self.setWindowTitle(f"🏗️ Project Engineering Dossier – {project_data.get('project_code', 'Project')}")
        self.setMinimumSize(580, 480)
        self.setStyleSheet(PROJECT_SETUP_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hdr = QLabel(f"📋 Project Dossier: {project_data.get('project_code')}")
        hdr.setStyleSheet("font-size: 16px; font-weight: bold; color: #0b2545;")
        layout.addWidget(hdr)

        info_box = QGroupBox("Administrative & Engineering Specifications")
        info_grid = QGridLayout(info_box)
        info_grid.setSpacing(8)

        details = [
            ("Project Identifier:", project_data.get("project_code", "—")),
            ("Project Full Title:", project_data.get("title", "—")),
            ("Owner / Client:", project_data.get("client", "—")),
            ("EPC Contractor:", project_data.get("contractor", "—")),
            ("Governing Code:", project_data.get("standard", "—")),
            ("Site Location:", project_data.get("location", "—")),
            ("Created Date:", str(project_data.get("created_at", "—"))),
            ("Process Areas / Units:", str(metrics.get("areas_count", 0))),
            ("Piping Lines In Scope:", str(metrics.get("lines_count", 0))),
            ("Weld Joints Registered:", str(metrics.get("welds_count", 0))),
            ("Pipe Spools Fabricated:", str(metrics.get("spools_count", 0))),
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

        desc_box = QGroupBox("Project Battery Limits & Scope Description")
        desc_lay = QVBoxLayout(desc_box)
        txt_desc = QTextEdit()
        txt_desc.setReadOnly(True)
        txt_desc.setPlainText(project_data.get("description", "") or "No detailed battery limits or scope notes recorded.")
        desc_lay.addWidget(txt_desc)
        layout.addWidget(desc_box)

        btn_close = QPushButton("Close Dossier")
        btn_close.setObjectName("secondaryBtn")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class ProjectSetupTab(QWidget):
    """ماژول جامع پیکربندی پروژه‌ها و تفکیک نواحی و یونیت‌های فرآیندی"""

    def __init__(self, db: DatabaseManager, session: SessionManager):
        super().__init__()
        self.setObjectName("projectSetupTab")
        self.db = db
        self.session = session
        self.current_project_id: Optional[int] = None

        # Implementation note.
        self._cached_projects: list[dict] = []
        self._cached_areas: list[dict] = []

        self._build_ui()
        self.setStyleSheet(PROJECT_SETUP_STYLESHEET)
        self.refresh_projects()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Implementation note.
        header_card = QFrame()
        header_card.setObjectName("headerCard")
        hdr_lay = QHBoxLayout(header_card)
        hdr_lay.setContentsMargins(14, 10, 14, 10)

        title_v = QVBoxLayout()
        t = QLabel("🏗️ Project & Process Unit (PBS) Setup")
        t.setObjectName("mainTitle")
        s = QLabel("Master Configuration: Project Identifiers, Design Standards, Client Hierarchy, and Process Area / Unit Breakdowns.")
        s.setObjectName("subTitle")
        title_v.addWidget(t)
        title_v.addWidget(s)
        hdr_lay.addLayout(title_v, 1)

        btn_refresh_all = QPushButton("🔄 Refresh All")
        btn_refresh_all.setObjectName("secondaryBtn")
        btn_refresh_all.clicked.connect(self.refresh_projects)
        hdr_lay.addWidget(btn_refresh_all)

        root.addWidget(header_card)

        # Implementation note.
        kpi_lay = QHBoxLayout()
        kpi_lay.setSpacing(8)

        self.kpi_total_projects = ProjectKPICard("Active Projects", "🏗️", "#3b82f6")
        self.kpi_total_areas = ProjectKPICard("Process Areas / Units", "🏭", "#10b981")
        self.kpi_total_lines = ProjectKPICard("Piping Lines In Scope", "📋", "#8b5cf6")
        self.kpi_total_welds = ProjectKPICard("Weld Joints Bound", "🔗", "#059669")
        self.kpi_standards = ProjectKPICard("Governing Code Types", "📐", "#f59e0b")

        for k in [self.kpi_total_projects, self.kpi_total_areas, self.kpi_total_lines, self.kpi_total_welds, self.kpi_standards]:
            kpi_lay.addWidget(k)
        root.addLayout(kpi_lay)

        # Implementation note.
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)

        # Implementation note.
        left_box = QGroupBox("📋 MASTER PROJECTS REGISTER")
        left_lay = QVBoxLayout(left_box)
        left_lay.setContentsMargins(8, 12, 8, 8)
        left_lay.setSpacing(6)

        proj_tb = QHBoxLayout()
        self.txt_search_proj = QLineEdit()
        self.txt_search_proj.setPlaceholderText("🔍 Search Code, Title, Client, Contractor, Standard...")
        self.txt_search_proj.textChanged.connect(self._filter_projects)
        proj_tb.addWidget(self.txt_search_proj, 1)

        btn_new_proj = QPushButton("➕ New Project")
        btn_new_proj.setObjectName("primaryBtn")
        btn_new_proj.clicked.connect(self._on_new_project)
        proj_tb.addWidget(btn_new_proj)

        btn_edit_proj = QPushButton("✏️ Edit")
        btn_edit_proj.setObjectName("secondaryBtn")
        btn_edit_proj.clicked.connect(self._on_edit_project)
        proj_tb.addWidget(btn_edit_proj)

        btn_exp_proj = QPushButton("📥 Export CSV")
        btn_exp_proj.setObjectName("secondaryBtn")
        btn_exp_proj.clicked.connect(self._export_projects_csv)
        proj_tb.addWidget(btn_exp_proj)

        btn_del_proj = QPushButton("🗑️")
        btn_del_proj.setObjectName("dangerBtn")
        btn_del_proj.setToolTip("Delete Selected Project")
        btn_del_proj.clicked.connect(self._on_delete_project)
        proj_tb.addWidget(btn_del_proj)

        left_lay.addLayout(proj_tb)

        self.proj_table = QTableWidget(0, 6)
        self.proj_table.setHorizontalHeaderLabels([
            "ID", "Project Code", "Official Title", "Client / Owner", "Contractor", "Governing Standard"
        ])
        self.proj_table.setColumnHidden(0, True) # Implementation note.
        self._setup_table_style(self.proj_table)
        self.proj_table.itemSelectionChanged.connect(self._on_project_selected)
        self.proj_table.doubleClicked.connect(self._on_project_double_clicked)
        self.proj_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.proj_table.customContextMenuRequested.connect(self._show_project_context_menu)
        left_lay.addWidget(self.proj_table)
        splitter.addWidget(left_box)

        # Implementation note.
        right_box = QGroupBox("🏭 PROCESS UNITS & BATTERY LIMITS (PBS)")
        right_lay = QVBoxLayout(right_box)
        right_lay.setContentsMargins(8, 12, 8, 8)
        right_lay.setSpacing(6)

        area_tb = QHBoxLayout()
        self.txt_search_area = QLineEdit()
        self.txt_search_area.setPlaceholderText("🔍 Search Unit / Area Name or Description...")
        self.txt_search_area.textChanged.connect(self._filter_areas)
        area_tb.addWidget(self.txt_search_area, 1)

        self.btn_new_area = QPushButton("➕ New Area")
        self.btn_new_area.setObjectName("primaryBtn")
        self.btn_new_area.setEnabled(False)
        self.btn_new_area.clicked.connect(self._on_new_area)
        area_tb.addWidget(self.btn_new_area)

        self.btn_edit_area = QPushButton("✏️ Edit Area")
        self.btn_edit_area.setObjectName("secondaryBtn")
        self.btn_edit_area.setEnabled(False)
        self.btn_edit_area.clicked.connect(self._on_edit_area)
        area_tb.addWidget(self.btn_edit_area)

        btn_exp_area = QPushButton("📥 Export")
        btn_exp_area.setObjectName("secondaryBtn")
        btn_exp_area.clicked.connect(self._export_areas_csv)
        area_tb.addWidget(btn_exp_area)

        self.btn_del_area = QPushButton("🗑️")
        self.btn_del_area.setObjectName("dangerBtn")
        self.btn_del_area.setToolTip("Delete Selected Area")
        self.btn_del_area.setEnabled(False)
        self.btn_del_area.clicked.connect(self._on_delete_area)
        area_tb.addWidget(self.btn_del_area)

        right_lay.addLayout(area_tb)

        self.area_table = QTableWidget(0, 3)
        self.area_table.setHorizontalHeaderLabels(["ID", "Unit / Area Name", "Process Scope / Boundary Description"])
        self.area_table.setColumnHidden(0, True)
        self._setup_table_style(self.area_table)
        self.area_table.doubleClicked.connect(self._on_edit_area)
        self.area_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.area_table.customContextMenuRequested.connect(self._show_area_context_menu)
        right_lay.addWidget(self.area_table)
        splitter.addWidget(right_box)

        splitter.setSizes([640, 460])
        root.addWidget(splitter, 1)

    def _setup_table_style(self, table: QTableWidget):
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    # ══════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════

    def refresh_projects(self):
        self.proj_table.setSortingEnabled(False)
        self.proj_table.setRowCount(0)
        self._cached_projects = []

        try:
            with self.db.session_scope() as session:
                projects = session.query(Project).order_by(Project.project_code).all()
                total_lines = session.query(LineListItem).count()
                total_welds = session.query(Weld).count()
                total_areas = session.query(Area).count()
                unique_stds = set()

                for p in projects:
                    std_val = p.standard or "ASME B31.3"
                    unique_stds.add(std_val)
                    self._cached_projects.append({
                        "id": p.id,
                        "project_code": p.project_code,
                        "title": p.title or "",
                        "client": p.client or "",
                        "contractor": p.contractor or "",
                        "standard": std_val,
                        "location": getattr(p, "location", "") or "",
                        "description": getattr(p, "description", "") or "",
                        "created_at": getattr(p, "created_at", datetime.datetime.now()),
                    })

                self.kpi_total_projects.set_value(str(len(projects)))
                self.kpi_total_areas.set_value(str(total_areas))
                self.kpi_total_lines.set_value(str(total_lines))
                self.kpi_total_welds.set_value(str(total_welds))
                self.kpi_standards.set_value(str(len(unique_stds)))

                self._filter_projects()

        except Exception as e:
            logger.exception("Failed to load projects in ProjectSetupTab")
            QMessageBox.warning(self, "Error", f"Could not load projects:\n{e}")

    def refresh_areas(self, project_id: int):
        self.area_table.setSortingEnabled(False)
        self.area_table.setRowCount(0)
        self._cached_areas = []

        if not project_id:
            return

        try:
            with self.db.session_scope() as session:
                areas = session.query(Area).filter(Area.project_id == project_id).order_by(Area.name).all()
                for a in areas:
                    self._cached_areas.append({
                        "id": a.id,
                        "project_id": a.project_id,
                        "name": a.name,
                        "code_tag": getattr(a, "code_tag", "") or "",
                        "description": a.description or "",
                    })
                self._filter_areas()
        except Exception as e:
            logger.exception("Failed to load areas in ProjectSetupTab")

    # ══════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════

    def _filter_projects(self):
        query = self.txt_search_proj.text().strip().lower()
        self.proj_table.setSortingEnabled(False)
        self.proj_table.setRowCount(0)

        for p in self._cached_projects:
            if query:
                combined = f"{p['project_code']} {p['title']} {p['client']} {p['contractor']} {p['standard']} {p['location']}".lower()
                if query not in combined:
                    continue

            r = self.proj_table.rowCount()
            self.proj_table.insertRow(r)

            self.proj_table.setItem(r, 0, QTableWidgetItem(str(p["id"])))
            self.proj_table.setItem(r, 1, QTableWidgetItem(p["project_code"]))
            self.proj_table.setItem(r, 2, QTableWidgetItem(p["title"]))
            self.proj_table.setItem(r, 3, QTableWidgetItem(p["client"]))
            self.proj_table.setItem(r, 4, QTableWidgetItem(p["contractor"]))

            # Implementation note.
            std_item = QTableWidgetItem(p["standard"])
            badge = next((v for k, v in STANDARD_BADGES.items() if k in p["standard"]), DEFAULT_STANDARD_BADGE)
            std_item.setText(f"{badge['icon']} {p['standard']}")
            std_item.setBackground(QBrush(QColor(badge["bg"])))
            std_item.setForeground(QBrush(QColor(badge["fg"])))
            f = std_item.font(); f.setBold(True); std_item.setFont(f)
            self.proj_table.setItem(r, 5, std_item)

        self.proj_table.setSortingEnabled(True)

    def _filter_areas(self):
        query = self.txt_search_area.text().strip().lower()
        self.area_table.setSortingEnabled(False)
        self.area_table.setRowCount(0)

        for a in self._cached_areas:
            if query:
                combined = f"{a['name']} {a['description']} {a['code_tag']}".lower()
                if query not in combined:
                    continue

            r = self.area_table.rowCount()
            self.area_table.insertRow(r)
            self.area_table.setItem(r, 0, QTableWidgetItem(str(a["id"])))
            self.area_table.setItem(r, 1, QTableWidgetItem(a["name"]))
            self.area_table.setItem(r, 2, QTableWidgetItem(a["description"]))

        self.area_table.setSortingEnabled(True)

    # ══════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════

    def _on_project_selected(self):
        rows = self.proj_table.selectionModel().selectedRows()
        if not rows:
            self.current_project_id = None
            self.btn_new_area.setEnabled(False)
            self.btn_edit_area.setEnabled(False)
            self.btn_del_area.setEnabled(False)
            self.area_table.setRowCount(0)
            return

        proj_id = int(self.proj_table.item(rows[0].row(), 0).text())
        self.current_project_id = proj_id
        self.btn_new_area.setEnabled(True)
        self.btn_edit_area.setEnabled(True)
        self.btn_del_area.setEnabled(True)
        self.refresh_areas(proj_id)

    def _on_project_double_clicked(self, index):
        rows = self.proj_table.selectionModel().selectedRows()
        if not rows:
            return
        proj_id = int(self.proj_table.item(rows[0].row(), 0).text())
        proj_data = next((p for p in self._cached_projects if p["id"] == proj_id), None)
        if not proj_data:
            return

        # Implementation note.
        metrics = {}
        with self.db.session_scope() as s:
            metrics["areas_count"] = s.query(Area).filter(Area.project_id == proj_id).count()
            metrics["lines_count"] = s.query(LineListItem).filter(LineListItem.project_id == proj_id).count()
            metrics["welds_count"] = s.query(Weld).filter(Weld.project_id == proj_id).count()
            metrics["spools_count"] = s.query(Spool).filter(Spool.project_id == proj_id).count()

        dlg = ProjectOverviewDialog(self, project_data=proj_data, metrics=metrics)
        dlg.exec()

    # ══════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════

    def _on_new_project(self):
        dlg = ProjectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        try:
            with self.db.session_scope() as session:
                p = Project(
                    project_code=data["project_code"],
                    title=data["title"],
                    client=data["client"],
                    contractor=data["contractor"],
                    standard=data["standard"],
                    created_at=datetime.datetime.utcnow(),
                )
                session.add(p)

            self.refresh_projects()
            QMessageBox.information(self, "Success", f"Project '{data['project_code']}' registered successfully.")
        except Exception as e:
            logger.exception("Failed to create project")
            QMessageBox.critical(self, "Error", f"Failed to create project (Duplicate code?):\n{e}")

    def _on_edit_project(self):
        rows = self.proj_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "Selection", "Select a project to edit.")
            return

        proj_id = int(self.proj_table.item(rows[0].row(), 0).text())
        proj_data = next((p for p in self._cached_projects if p["id"] == proj_id), None)
        if not proj_data:
            return

        dlg = ProjectDialog(self, project_data=proj_data)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new_data = dlg.get_data()
        try:
            with self.db.session_scope() as session:
                p = session.query(Project).get(proj_id)
                if p:
                    p.title = new_data["title"]
                    p.client = new_data["client"]
                    p.contractor = new_data["contractor"]
                    p.standard = new_data["standard"]

            self.refresh_projects()
            QMessageBox.information(self, "Updated", f"Project '{proj_data['project_code']}' updated.")
        except Exception as e:
            logger.exception("Failed to edit project")
            QMessageBox.critical(self, "Error", f"Update failed:\n{e}")

    def _on_delete_project(self):
        rows = self.proj_table.selectionModel().selectedRows()
        if not rows:
            return

        proj_id = int(self.proj_table.item(rows[0].row(), 0).text())
        proj_code = self.proj_table.item(rows[0].row(), 1).text()

        reply = QMessageBox.warning(
            self, "⚠️ Permanent Project Deletion",
            f"Are you sure you want to completely delete Project '{proj_code}'?\n\n"
            f"⚠️ WARNING: This will cascade and delete all associated Line Lists, Areas, Welds, and Quality Records under this project!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as session:
                p = session.query(Project).get(proj_id)
                if p:
                    session.delete(p)

            self.refresh_projects()
            QMessageBox.information(self, "Deleted", f"Project '{proj_code}' was removed from the database.")
        except Exception as e:
            logger.exception("Failed to delete project")
            QMessageBox.critical(self, "Error", f"Could not delete project:\n{e}")

    # ══════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════

    def _on_new_area(self):
        if not self.current_project_id:
            return
        dlg = AreaDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        try:
            with self.db.session_scope() as session:
                a = Area(
                    project_id=self.current_project_id,
                    name=data["name"],
                    description=data["description"],
                )
                session.add(a)

            self.refresh_areas(self.current_project_id)
            QMessageBox.information(self, "Success", f"Process Area '{data['name']}' added.")
        except Exception as e:
            logger.exception("Failed to create area")
            QMessageBox.critical(self, "Error", f"Failed to create area:\n{e}")

    def _on_edit_area(self):
        rows = self.area_table.selectionModel().selectedRows()
        if not rows:
            return

        area_id = int(self.area_table.item(rows[0].row(), 0).text())
        area_data = next((a for a in self._cached_areas if a["id"] == area_id), None)
        if not area_data:
            return

        dlg = AreaDialog(self, area_data=area_data)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new_data = dlg.get_data()
        try:
            with self.db.session_scope() as session:
                a = session.query(Area).get(area_id)
                if a:
                    a.name = new_data["name"]
                    a.description = new_data["description"]

            self.refresh_areas(self.current_project_id)
            QMessageBox.information(self, "Updated", f"Area '{new_data['name']}' updated.")
        except Exception as e:
            logger.exception("Failed to edit area")
            QMessageBox.critical(self, "Error", f"Update failed:\n{e}")

    def _on_delete_area(self):
        rows = self.area_table.selectionModel().selectedRows()
        if not rows:
            return

        area_id = int(self.area_table.item(rows[0].row(), 0).text())
        area_name = self.area_table.item(rows[0].row(), 1).text()

        if QMessageBox.question(self, "Confirm Delete", f"Delete Process Area '{area_name}'?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as session:
                a = session.query(Area).get(area_id)
                if a:
                    session.delete(a)

            self.refresh_areas(self.current_project_id)
            QMessageBox.information(self, "Deleted", "Area deleted successfully.")
        except Exception as e:
            logger.exception("Failed to delete area")
            QMessageBox.critical(self, "Error", f"Could not delete area:\n{e}")

    # ══════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════

    def _show_project_context_menu(self, pos):
        rows = self.proj_table.selectionModel().selectedRows()
        if not rows:
            return

        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: white; border: 1px solid #cbd5e1; } QMenu::item { padding: 6px 18px; }")

        act_dossier = QAction("🔍 View Full Project Dossier", self)
        act_dossier.triggered.connect(lambda: self._on_project_double_clicked(self.proj_table.currentIndex()))
        menu.addAction(act_dossier)

        act_edit = QAction("✏️ Edit Project Specs", self)
        act_edit.triggered.connect(self._on_edit_project)
        menu.addAction(act_edit)

        menu.addSeparator()

        act_copy = QAction("📋 Copy Project Code", self)
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(self.proj_table.item(rows[0].row(), 1).text()))
        menu.addAction(act_copy)

        act_del = QAction("🗑️ Delete Project", self)
        act_del.triggered.connect(self._on_delete_project)
        menu.addAction(act_del)

        menu.exec(self.proj_table.viewport().mapToGlobal(pos))

    def _show_area_context_menu(self, pos):
        rows = self.area_table.selectionModel().selectedRows()
        if not rows:
            return

        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: white; border: 1px solid #cbd5e1; } QMenu::item { padding: 6px 18px; }")

        act_edit = QAction("✏️ Edit Area Details", self)
        act_edit.triggered.connect(self._on_edit_area)
        menu.addAction(act_edit)

        act_copy = QAction("📋 Copy Area Name", self)
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(self.area_table.item(rows[0].row(), 1).text()))
        menu.addAction(act_copy)

        act_del = QAction("🗑️ Delete Area", self)
        act_del.triggered.connect(self._on_delete_area)
        menu.addAction(act_del)

        menu.exec(self.area_table.viewport().mapToGlobal(pos))

    def _export_projects_csv(self):
        self._export_table_to_csv(self.proj_table, "PipeAgent_Master_Projects")

    def _export_areas_csv(self):
        self._export_table_to_csv(self.area_table, "PipeAgent_Process_Areas")

    def _export_table_to_csv(self, table: QTableWidget, prefix: str):
        if table.rowCount() == 0:
            QMessageBox.warning(self, "Export", "Table is empty. Nothing to export.")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename, _ = QFileDialog.getSaveFileName(self, "Export CSV Report", f"{prefix}_{timestamp}.csv", "CSV Files (*.csv)")
        if not filename:
            return

        try:
            with open(filename, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                headers = [table.horizontalHeaderItem(c).text() for c in range(1, table.columnCount())]
                writer.writerow(headers)

                for r in range(table.rowCount()):
                    if not table.isRowHidden(r):
                        row_vals = [table.item(r, c).text().strip() if table.item(r, c) else "" for c in range(1, table.columnCount())]
                        writer.writerow(row_vals)

            QMessageBox.information(self, "Export Complete", f"Data exported successfully to:\n{filename}")
        except Exception as e:
            logger.exception("CSV export failed")
            QMessageBox.critical(self, "Export Error", f"Could not export CSV file:\n{e}")