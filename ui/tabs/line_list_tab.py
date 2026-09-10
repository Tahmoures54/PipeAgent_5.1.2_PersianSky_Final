# -*- coding: utf-8 -*-
# ui/tabs/line_list_tab.py – PipeAgent
# Line List registration, editing, search, filters, CSV/Excel import/export.

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QCursor, QAction
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QDialog, QFormLayout,
    QLineEdit, QComboBox, QDialogButtonBox,
    QFileDialog, QDoubleSpinBox, QTextEdit,
    QFrame, QMenu, QApplication, QAbstractItemView,
)

from db.manager import DatabaseManager
from db.models import Project, LineListItem
from security.session import SessionManager
from services.line_list_service import LineListService
from config import FLUID_SERVICES, FLUID_CODES

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

HIGH_PRESSURE_LIMIT_BARG = 100.0
HIGH_TEMPERATURE_LIMIT_C = 400.0

TABLE_HEADERS = [
    "ID",
    "Line Number",
    "P&ID",
    "Iso",
    "Fluid Code",
    "Fluid Name",
    "Fluid Service",
    "Pipe Class",
    "Size",
    "Schedule",
    "Material",
    "Design P (barg)",
    "Design T (°C)",
    "From",
    "To",
]

LINE_LIST_STYLESHEET = """
    QWidget#lineListTab {
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 #f8fafc, stop:1 #eef2f7
        );
    }

    QFrame#headerCard {
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 #1e3c72, stop:1 #2a5298
        );
        border-radius: 14px;
        padding: 16px;
    }

    QLabel#mainTitle {
        color: white;
        font-size: 22px;
        font-weight: 800;
        font-family: "Segoe UI", sans-serif;
    }

    QLabel#mainSubtitle {
        color: #cbd5e1;
        font-size: 12px;
    }

    QFrame#statCard {
        background: white;
        border: 1px solid #dbe3ed;
        border-radius: 10px;
        padding: 10px;
    }

    QFrame#filterCard {
        background: white;
        border: 1px solid #dbe3ed;
        border-radius: 10px;
        padding: 10px;
    }

    QLabel#statTitle {
        color: #64748b;
        font-size: 10px;
        font-weight: 700;
    }

    QLabel#statValue {
        font-size: 21px;
        font-weight: 800;
    }

    QLineEdit, QComboBox, QDoubleSpinBox {
        padding: 7px 10px;
        border: 2px solid #e2e8f0;
        border-radius: 7px;
        background: white;
        color: #1e293b;
        font-size: 12px;
    }

    QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
        border-color: #3b82f6;
        background: #f8fbff;
    }

    QLineEdit:hover, QComboBox:hover, QDoubleSpinBox:hover {
        border-color: #94a3b8;
    }

    QPushButton#primaryBtn {
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 #3b82f6, stop:1 #2563eb
        );
        color: white;
        border: none;
        border-radius: 7px;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 700;
    }

    QPushButton#primaryBtn:hover {
        background: #1d4ed8;
    }

    QPushButton#successBtn {
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 #10b981, stop:1 #059669
        );
        color: white;
        border: none;
        border-radius: 7px;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 700;
    }

    QPushButton#successBtn:hover {
        background: #047857;
    }

    QPushButton#dangerBtn {
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 #ef4444, stop:1 #dc2626
        );
        color: white;
        border: none;
        border-radius: 7px;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 700;
    }

    QPushButton#dangerBtn:hover {
        background: #b91c1c;
    }

    QPushButton#secondaryBtn {
        background: white;
        color: #334155;
        border: 2px solid #d1d5db;
        border-radius: 7px;
        padding: 7px 14px;
        font-size: 12px;
        font-weight: 600;
    }

    QPushButton#secondaryBtn:hover {
        background: #f8fafc;
        border-color: #3b82f6;
        color: #2563eb;
    }

    QTableWidget {
        background: white;
        border: 1px solid #dbe3ed;
        border-radius: 10px;
        gridline-color: #f1f5f9;
        font-size: 12px;
        selection-background-color: #dbeafe;
        selection-color: #1e293b;
        alternate-background-color: #f8fafc;
    }

    QTableWidget::item {
        padding: 6px 8px;
        border-bottom: 1px solid #f1f5f9;
    }

    QTableWidget::item:hover {
        background: #eff6ff;
    }

    QHeaderView::section {
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 #f8fafc, stop:1 #eef2f7
        );
        color: #475569;
        font-size: 11px;
        font-weight: 700;
        padding: 9px 8px;
        border: none;
        border-bottom: 2px solid #dbe3ed;
        border-right: 1px solid #e2e8f0;
    }

    QScrollBar:vertical {
        background: #f1f5f9;
        width: 10px;
        border-radius: 5px;
    }

    QScrollBar::handle:vertical {
        background: #94a3b8;
        border-radius: 5px;
        min-height: 30px;
    }

    QScrollBar::handle:vertical:hover {
        background: #64748b;
    }
"""


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class StatCard(QFrame):
    """کارت کوچک نمایش KPI برای Line List."""

    def __init__(self, icon: str, title: str, color: str = "#3b82f6"):
        super().__init__()
        self.setObjectName("statCard")
        self.setMinimumWidth(145)
        self.setFixedHeight(78)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(1)

        top = QHBoxLayout()

        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size:18px; color:{color};")
        top.addWidget(icon_label)

        top.addStretch()

        self.value_label = QLabel("0")
        self.value_label.setObjectName("statValue")
        self.value_label.setStyleSheet(
            f"font-size:21px; font-weight:800; color:{color};"
        )
        top.addWidget(self.value_label)

        layout.addLayout(top)

        title_label = QLabel(title)
        title_label.setObjectName("statTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

    def set_value(self, value) -> None:
        self.value_label.setText(str(value))


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class LineDialog(QDialog):
    """ثبت یا ویرایش یک آیتم از Line List."""

    def __init__(
        self,
        parent=None,
        projects: list | None = None,
        existing_data: dict | None = None,
    ):
        super().__init__(parent)

        self.is_edit = existing_data is not None
        self.setWindowTitle(
            "✏️ Edit Line List Item"
            if self.is_edit
            else "➕ New Line List Item"
        )
        self.setMinimumWidth(560)
        self.setStyleSheet(LINE_LIST_STYLESHEET)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(18, 18, 18, 18)

        title = QLabel(
            "Edit Engineering Line Data"
            if self.is_edit
            else "Register Engineering Line Data"
        )
        title.setStyleSheet(
            "font-size:17px; font-weight:800; color:#1e3c72;"
        )
        root.addWidget(title)

        form = QFormLayout()
        form.setSpacing(8)

        self.project_combo = QComboBox()
        for project in projects or []:
            self.project_combo.addItem(
                f"{project.project_code} – {project.title}",
                project.id,
            )

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText('e.g. 6"-P-1001-A1A')

        self.pid_edit = QLineEdit()
        self.pid_edit.setPlaceholderText("e.g. PID-1001")

        self.iso_edit = QLineEdit()
        self.iso_edit.setPlaceholderText("e.g. ISO-1001-A")

        self.fluid_code = QComboBox()
        self.fluid_code.setEditable(True)
        self.fluid_code.addItems([""] + list(FLUID_CODES))

        self.fluid_name = QLineEdit()
        self.fluid_name.setPlaceholderText("e.g. Cooling Water")

        self.fluid_service = QComboBox()
        self.fluid_service.addItems(list(FLUID_SERVICES))

        self.dp = QDoubleSpinBox()
        self.dp.setRange(0, 10000)
        self.dp.setDecimals(2)
        self.dp.setSuffix(" barg")

        self.dt = QDoubleSpinBox()
        self.dt.setRange(-200, 1000)
        self.dt.setDecimals(1)
        self.dt.setSuffix(" °C")

        self.pipe_class = QLineEdit()
        self.pipe_class.setPlaceholderText("e.g. CS150")

        self.size_edit = QLineEdit()
        self.size_edit.setPlaceholderText('e.g. 6" / DN150')

        self.schedule = QLineEdit()
        self.schedule.setPlaceholderText("e.g. SCH 40")

        self.material = QLineEdit()
        self.material.setPlaceholderText("e.g. ASTM A106 Gr.B")

        self.from_edit = QLineEdit()
        self.from_edit.setPlaceholderText("Start point / equipment")

        self.to_edit = QLineEdit()
        self.to_edit.setPlaceholderText("End point / equipment")

        self.remarks = QTextEdit()
        self.remarks.setMaximumHeight(75)
        self.remarks.setPlaceholderText(
            "Engineering notes, insulation notes, special requirements..."
        )

        form.addRow("Project *", self.project_combo)
        form.addRow("Line Number *", self.line_edit)
        form.addRow("P&ID Number", self.pid_edit)
        form.addRow("Iso Number", self.iso_edit)
        form.addRow("Fluid Code", self.fluid_code)
        form.addRow("Fluid Name", self.fluid_name)
        form.addRow("Fluid Service", self.fluid_service)
        form.addRow("Design Pressure", self.dp)
        form.addRow("Design Temperature", self.dt)
        form.addRow("Pipe Class", self.pipe_class)
        form.addRow("Size (NPS / DN)", self.size_edit)
        form.addRow("Schedule", self.schedule)
        form.addRow("Material", self.material)
        form.addRow("From", self.from_edit)
        form.addRow("To", self.to_edit)
        form.addRow("Remarks", self.remarks)

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if existing_data:
            self._load_existing_data(existing_data)

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        """تنظیم مقدار ComboBox؛ در صورت نبودن مقدار، اضافه می‌شود."""
        value = value or ""
        index = combo.findText(value)

        if index < 0 and value:
            combo.addItem(value)
            index = combo.findText(value)

        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.isEditable():
            combo.setCurrentText(value)

    def _load_existing_data(self, data: dict) -> None:
        project_id = data.get("project_id")

        for index in range(self.project_combo.count()):
            if self.project_combo.itemData(index) == project_id:
                self.project_combo.setCurrentIndex(index)
                break

        self.line_edit.setText(data.get("line_number", ""))
        self.pid_edit.setText(data.get("pid_number", ""))
        self.iso_edit.setText(data.get("iso_number", ""))
        self._set_combo_value(self.fluid_code, data.get("fluid_code", ""))
        self.fluid_name.setText(data.get("fluid_name", ""))
        self._set_combo_value(
            self.fluid_service,
            data.get("fluid_service", ""),
        )

        self.dp.setValue(float(data.get("design_pressure_barg") or 0))
        self.dt.setValue(float(data.get("design_temp_c") or 0))

        self.pipe_class.setText(data.get("pipe_class", ""))
        self.size_edit.setText(data.get("size_nps", ""))
        self.schedule.setText(data.get("schedule", ""))
        self.material.setText(data.get("material", ""))
        self.from_edit.setText(data.get("from_point", ""))
        self.to_edit.setText(data.get("to_point", ""))
        self.remarks.setPlainText(data.get("remarks", ""))

    def _validate_and_accept(self) -> None:
        if not self.project_combo.currentData():
            QMessageBox.warning(
                self,
                "Validation",
                "Please select a project.",
            )
            return

        if not self.line_edit.text().strip():
            QMessageBox.warning(
                self,
                "Validation",
                "Line Number is required.",
            )
            self.line_edit.setFocus()
            return

        self.accept()

    def get_data(self) -> dict:
        return {
            "project_id": self.project_combo.currentData(),
            "line_number": self.line_edit.text().strip(),
            "pid_number": self.pid_edit.text().strip(),
            "iso_number": self.iso_edit.text().strip(),
            "fluid_code": self.fluid_code.currentText().strip(),
            "fluid_name": self.fluid_name.text().strip(),
            "fluid_service": self.fluid_service.currentText().strip(),
            "design_pressure_barg": (
                self.dp.value() if self.dp.value() != 0 else None
            ),
            "design_temp_c": (
                self.dt.value() if self.dt.value() != 0 else None
            ),
            "pipe_class": self.pipe_class.text().strip(),
            "size_nps": self.size_edit.text().strip(),
            "schedule": self.schedule.text().strip(),
            "material": self.material.text().strip(),
            "from_point": self.from_edit.text().strip(),
            "to_point": self.to_edit.text().strip(),
            "remarks": self.remarks.toPlainText().strip(),
        }


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class LineDetailsDialog(QDialog):
    """نمایش مشخصات مهندسی کامل یک خط."""

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.data = data

        self.setWindowTitle(
            f"📋 Line Details — {data.get('line_number', '')}"
        )
        self.setMinimumSize(580, 470)
        self.setStyleSheet(LINE_LIST_STYLESHEET)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel(
            f"📋 Engineering Line Dossier: "
            f"{data.get('line_number', 'N/A')}"
        )
        title.setStyleSheet(
            "font-size:18px; font-weight:800; color:#1e3c72;"
        )
        root.addWidget(title)

        form = QFormLayout()
        form.setSpacing(9)

        fields = [
            ("Project ID", data.get("project_id")),
            ("Line Number", data.get("line_number")),
            ("P&ID Number", data.get("pid_number")),
            ("Iso Number", data.get("iso_number")),
            ("Fluid Code", data.get("fluid_code")),
            ("Fluid Name", data.get("fluid_name")),
            ("Fluid Service", data.get("fluid_service")),
            ("Design Pressure", self._unit(data.get("design_pressure_barg"), "barg")),
            ("Design Temperature", self._unit(data.get("design_temp_c"), "°C")),
            ("Pipe Class", data.get("pipe_class")),
            ("Size", data.get("size_nps")),
            ("Schedule", data.get("schedule")),
            ("Material", data.get("material")),
            ("From", data.get("from_point")),
            ("To", data.get("to_point")),
            ("Remarks", data.get("remarks")),
        ]

        for label_text, value in fields:
            label = QLabel(f"{label_text}:")
            label.setStyleSheet(
                "font-weight:700; color:#475569;"
            )

            value_label = QLabel(str(value or "—"))
            value_label.setStyleSheet("color:#1e293b;")
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )

            form.addRow(label, value_label)

        root.addLayout(form)
        root.addStretch()

        button = QPushButton("Close")
        button.setObjectName("secondaryBtn")
        button.clicked.connect(self.accept)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button)
        root.addLayout(row)

    @staticmethod
    def _unit(value, unit: str) -> str:
        if value is None or value == "":
            return ""
        return f"{value} {unit}"


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class LineListTab(QWidget):
    """
    Line List Register.

    قابلیت‌ها:
    - ثبت دستی خط
    - ویرایش و حذف
    - CSV / Excel Import
    - CSV Export
    - جستجو و فیلتر سریع
    - کارت‌های آماری
    - نمایش جزئیات مهندسی خط
    - منوی راست‌کلیک
    """

    def __init__(self, db: DatabaseManager, session: SessionManager):
        super().__init__()

        self.setObjectName("lineListTab")

        self.db = db
        self.session = session
        self.service = LineListService(db)

        self.current_project_id: int | None = None
        self._cached_lines: list[dict] = []

        self._build_ui()
        self.setStyleSheet(LINE_LIST_STYLESHEET)
        self._load_projects()

    # ═══════════════════════════════════════
    # UI
    # ═══════════════════════════════════════

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        root.addWidget(self._build_header())
        root.addLayout(self._build_stat_cards())
        root.addWidget(self._build_filter_bar())
        root.addWidget(self._build_table(), stretch=1)
        root.addWidget(self._build_status_bar())

    def _build_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("headerCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)

        title_layout = QVBoxLayout()

        title = QLabel("📋 Line List Register")
        title.setObjectName("mainTitle")
        title_layout.addWidget(title)

        subtitle = QLabel(
            "Engineering register for piping lines, design conditions, "
            "fluid service, material class and line routing."
        )
        subtitle.setObjectName("mainSubtitle")
        title_layout.addWidget(subtitle)

        layout.addLayout(title_layout, stretch=1)

        controls = QHBoxLayout()

        lbl_project = QLabel("Project:")
        lbl_project.setStyleSheet(
            "color:white; font-weight:700; font-size:12px;"
        )
        controls.addWidget(lbl_project)

        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(250)
        self.project_combo.currentIndexChanged.connect(
            self._on_project_changed
        )
        controls.addWidget(self.project_combo)

        btn_refresh = QPushButton("↻ Refresh")
        btn_refresh.setObjectName("secondaryBtn")
        btn_refresh.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        btn_refresh.clicked.connect(self.refresh)
        controls.addWidget(btn_refresh)

        layout.addLayout(controls)

        return card

    def _build_stat_cards(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)

        self.stat_total = StatCard(
            "📋", "Total Lines", "#3b82f6"
        )
        self.stat_classes = StatCard(
            "🔧", "Pipe Classes", "#8b5cf6"
        )
        self.stat_high_pressure = StatCard(
            "⚠️", "P ≥ 100 barg", "#ef4444"
        )
        self.stat_high_temp = StatCard(
            "🔥", "T ≥ 400 °C", "#f59e0b"
        )
        self.stat_services = StatCard(
            "💧", "Fluid Services", "#10b981"
        )

        for card in [
            self.stat_total,
            self.stat_classes,
            self.stat_high_pressure,
            self.stat_high_temp,
            self.stat_services,
        ]:
            layout.addWidget(card)

        return layout

    def _build_filter_bar(self) -> QFrame:
        card = QFrame()
        card.setObjectName("filterCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(7)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "🔍 Search line, P&ID, ISO, fluid, class, material..."
        )
        self.search_edit.setMinimumWidth(280)
        self.search_edit.textChanged.connect(self._apply_filters)
        layout.addWidget(self.search_edit, stretch=1)

        self.service_filter = QComboBox()
        self.service_filter.addItem("All Services", None)
        for service in FLUID_SERVICES:
            self.service_filter.addItem(service, service)
        self.service_filter.currentIndexChanged.connect(
            self._apply_filters
        )
        layout.addWidget(self.service_filter)

        self.class_filter = QComboBox()
        self.class_filter.addItem("All Pipe Classes", None)
        self.class_filter.currentIndexChanged.connect(
            self._apply_filters
        )
        layout.addWidget(self.class_filter)

        self.btn_add = QPushButton("➕ Add Line")
        self.btn_add.setObjectName("successBtn")
        self.btn_add.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.btn_add.clicked.connect(self._on_add)
        layout.addWidget(self.btn_add)

        self.btn_import = QPushButton("📥 Import CSV/Excel")
        self.btn_import.setObjectName("primaryBtn")
        self.btn_import.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.btn_import.clicked.connect(self._on_import)
        layout.addWidget(self.btn_import)

        self.btn_export = QPushButton("⇩ Export CSV")
        self.btn_export.setObjectName("secondaryBtn")
        self.btn_export.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.btn_export.clicked.connect(self._export_csv)
        layout.addWidget(self.btn_export)

        self.btn_delete = QPushButton("🗑 Delete")
        self.btn_delete.setObjectName("dangerBtn")
        self.btn_delete.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.btn_delete.clicked.connect(self._delete_selected)
        layout.addWidget(self.btn_delete)

        return card

    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget(0, len(TABLE_HEADERS))
        self.table.setHorizontalHeaderLabels(TABLE_HEADERS)

        self.table.setColumnHidden(0, True)

        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        header.setStretchLastSection(True)

        column_widths = {
            1: 160,
            2: 120,
            3: 120,
            4: 100,
            5: 150,
            6: 145,
            7: 110,
            8: 90,
            9: 100,
            10: 150,
            11: 120,
            12: 120,
            13: 150,
            14: 150,
        }

        for column, width in column_widths.items():
            self.table.setColumnWidth(column, width)

        self.table.doubleClicked.connect(
            self._show_selected_details
        )

        self.table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table.customContextMenuRequested.connect(
            self._show_context_menu
        )

        return self.table

    def _build_status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setStyleSheet(
            "background:#f1f5f9; border-radius:7px; padding:5px 10px;"
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 3, 8, 3)

        self.summary_lbl = QLabel("Ready")
        self.summary_lbl.setStyleSheet(
            "color:#64748b; font-size:12px;"
        )
        layout.addWidget(self.summary_lbl)

        layout.addStretch()

        self.selection_lbl = QLabel("Selected: 0")
        self.selection_lbl.setStyleSheet(
            "color:#64748b; font-size:12px; font-weight:600;"
        )
        layout.addWidget(self.selection_lbl)

        self.table.selectionModel().selectionChanged.connect(
            self._update_selection_count
        )

        return bar

    # ═══════════════════════════════════════
    # Project loading
    # ═══════════════════════════════════════

    def _load_projects(self) -> None:
        current_project_id = self.project_combo.currentData()

        self.project_combo.blockSignals(True)
        self.project_combo.clear()

        try:
            with self.db.session_scope() as session:
                projects = (
                    session.query(Project)
                    .order_by(Project.project_code)
                    .all()
                )

                for project in projects:
                    self.project_combo.addItem(
                        f"{project.project_code} – {project.title}",
                        project.id,
                    )
        except Exception as exc:
            logger.exception("Load projects failed")
            QMessageBox.warning(
                self,
                "Project Load Error",
                f"Could not load projects:\n{exc}",
            )
        finally:
            self.project_combo.blockSignals(False)

        if self.project_combo.count():
            index = self.project_combo.findData(current_project_id)
            self.project_combo.setCurrentIndex(
                index if index >= 0 else 0
            )
            self._on_project_changed()
        else:
            self.current_project_id = None
            self._clear_table_and_stats()

    def _get_project_views(self) -> list:
        """ساخت آبجکت سبک پروژه برای استفاده ایمن در Dialog."""
        with self.db.session_scope() as session:
            projects = (
                session.query(Project)
                .order_by(Project.project_code)
                .all()
            )

            return [
                type(
                    "ProjectView",
                    (),
                    {
                        "id": p.id,
                        "project_code": p.project_code,
                        "title": p.title,
                    },
                )()
                for p in projects
            ]

    def _on_project_changed(self, *_args) -> None:
        self.current_project_id = self.project_combo.currentData()
        self.refresh()

    # ═══════════════════════════════════════
    # Load, cache, filters and statistics
    # ═══════════════════════════════════════

    def refresh(self) -> None:
        """بارگذاری مجدد داده‌های پروژه انتخاب‌شده."""
        self._cached_lines = []

        if not self.current_project_id:
            self._clear_table_and_stats()
            self.summary_lbl.setText("Select a project.")
            return

        self.summary_lbl.setText("Loading line list...")
        QApplication.processEvents()

        try:
            items = self.service.list_by_project(
                self.current_project_id
            )

            self._cached_lines = [
                self._to_line_dict(item)
                for item in items
            ]

            self._refresh_pipe_class_filter()
            self._update_stats()
            self._apply_filters()

        except Exception as exc:
            logger.exception("Line list refresh failed")
            self._clear_table_and_stats()
            QMessageBox.warning(
                self,
                "Line List Error",
                f"Could not load Line List:\n{exc}",
            )

    @staticmethod
    def _to_line_dict(item) -> dict:
        return {
            "id": getattr(item, "id", None),
            "project_id": getattr(item, "project_id", None),
            "line_number": getattr(item, "line_number", "") or "",
            "pid_number": getattr(item, "pid_number", "") or "",
            "iso_number": getattr(item, "iso_number", "") or "",
            "fluid_code": getattr(item, "fluid_code", "") or "",
            "fluid_name": getattr(item, "fluid_name", "") or "",
            "fluid_service": getattr(item, "fluid_service", "") or "",
            "design_pressure_barg": getattr(
                item,
                "design_pressure_barg",
                None,
            ),
            "design_temp_c": getattr(item, "design_temp_c", None),
            "pipe_class": getattr(item, "pipe_class", "") or "",
            "size_nps": getattr(item, "size_nps", "") or "",
            "schedule": getattr(item, "schedule", "") or "",
            "material": getattr(item, "material", "") or "",
            "from_point": getattr(item, "from_point", "") or "",
            "to_point": getattr(item, "to_point", "") or "",
            "remarks": getattr(item, "remarks", "") or "",
        }

    def _refresh_pipe_class_filter(self) -> None:
        current_value = self.class_filter.currentData()

        classes = sorted({
            line["pipe_class"]
            for line in self._cached_lines
            if line.get("pipe_class")
        })

        self.class_filter.blockSignals(True)
        self.class_filter.clear()
        self.class_filter.addItem("All Pipe Classes", None)

        for pipe_class in classes:
            self.class_filter.addItem(pipe_class, pipe_class)

        index = self.class_filter.findData(current_value)
        if index >= 0:
            self.class_filter.setCurrentIndex(index)

        self.class_filter.blockSignals(False)

    def _apply_filters(self, *_args) -> None:
        """اعمال جستجو و فیلترها روی cache محلی."""
        query = self.search_edit.text().strip().lower()
        service = self.service_filter.currentData()
        pipe_class = self.class_filter.currentData()

        filtered = []

        for line in self._cached_lines:
            if service and line["fluid_service"] != service:
                continue

            if pipe_class and line["pipe_class"] != pipe_class:
                continue

            if query:
                searchable = " ".join([
                    line["line_number"],
                    line["pid_number"],
                    line["iso_number"],
                    line["fluid_code"],
                    line["fluid_name"],
                    line["fluid_service"],
                    line["pipe_class"],
                    line["size_nps"],
                    line["schedule"],
                    line["material"],
                    line["from_point"],
                    line["to_point"],
                    line["remarks"],
                ]).lower()

                if query not in searchable:
                    continue

            filtered.append(line)

        self._populate_table(filtered)

        self.summary_lbl.setText(
            f"Showing {len(filtered)} of {len(self._cached_lines)} "
            f"line(s) in selected project."
        )

    def _populate_table(self, lines: list[dict]) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for line in lines:
            row = self.table.rowCount()
            self.table.insertRow(row)

            values = [
                line["id"],
                line["line_number"],
                line["pid_number"],
                line["iso_number"],
                line["fluid_code"],
                line["fluid_name"],
                line["fluid_service"],
                line["pipe_class"],
                line["size_nps"],
                line["schedule"],
                line["material"],
                self._number_text(line["design_pressure_barg"]),
                self._number_text(line["design_temp_c"]),
                line["from_point"],
                line["to_point"],
            ]

            for column, value in enumerate(values):
                item = QTableWidgetItem(
                    "" if value is None else str(value)
                )

                if column == 0:
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        line,
                    )

                if column == 11:
                    self._apply_pressure_color(
                        item,
                        line["design_pressure_barg"],
                    )

                if column == 12:
                    self._apply_temperature_color(
                        item,
                        line["design_temp_c"],
                    )

                self.table.setItem(row, column, item)

            self.table.setRowHeight(row, 34)

        self.table.setSortingEnabled(True)
        self._update_selection_count()

    @staticmethod
    def _number_text(value) -> str:
        if value is None or value == "":
            return ""

        try:
            return f"{float(value):g}"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _apply_pressure_color(
        item: QTableWidgetItem,
        pressure,
    ) -> None:
        try:
            if pressure is not None and float(pressure) >= HIGH_PRESSURE_LIMIT_BARG:
                item.setBackground(QColor("#fff1f2"))
                item.setForeground(QColor("#be123c"))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setToolTip(
                    f"High design pressure: {pressure} barg"
                )
        except (TypeError, ValueError):
            pass

    @staticmethod
    def _apply_temperature_color(
        item: QTableWidgetItem,
        temperature,
    ) -> None:
        try:
            if (
                temperature is not None
                and float(temperature) >= HIGH_TEMPERATURE_LIMIT_C
            ):
                item.setBackground(QColor("#fff7ed"))
                item.setForeground(QColor("#c2410c"))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setToolTip(
                    f"High design temperature: {temperature} °C"
                )
        except (TypeError, ValueError):
            pass

    def _update_stats(self) -> None:
        total = len(self._cached_lines)

        pipe_classes = {
            line["pipe_class"]
            for line in self._cached_lines
            if line["pipe_class"]
        }

        fluid_services = {
            line["fluid_service"]
            for line in self._cached_lines
            if line["fluid_service"]
        }

        high_pressure = sum(
            1
            for line in self._cached_lines
            if self._is_at_or_above(
                line.get("design_pressure_barg"),
                HIGH_PRESSURE_LIMIT_BARG,
            )
        )

        high_temperature = sum(
            1
            for line in self._cached_lines
            if self._is_at_or_above(
                line.get("design_temp_c"),
                HIGH_TEMPERATURE_LIMIT_C,
            )
        )

        self.stat_total.set_value(total)
        self.stat_classes.set_value(len(pipe_classes))
        self.stat_high_pressure.set_value(high_pressure)
        self.stat_high_temp.set_value(high_temperature)
        self.stat_services.set_value(len(fluid_services))

    @staticmethod
    def _is_at_or_above(value, threshold: float) -> bool:
        try:
            return value is not None and float(value) >= threshold
        except (TypeError, ValueError):
            return False

    def _clear_table_and_stats(self) -> None:
        self.table.setRowCount(0)
        self._cached_lines = []

        self.stat_total.set_value(0)
        self.stat_classes.set_value(0)
        self.stat_high_pressure.set_value(0)
        self.stat_high_temp.set_value(0)
        self.stat_services.set_value(0)

        self.selection_lbl.setText("Selected: 0")

    # ═══════════════════════════════════════
    # Selection helpers
    # ═══════════════════════════════════════

    def _selected_line_data(self) -> list[dict]:
        rows = self.table.selectionModel().selectedRows()
        result = []

        for model_index in rows:
            item = self.table.item(model_index.row(), 0)

            if not item:
                continue

            line = item.data(Qt.ItemDataRole.UserRole)

            if line:
                result.append(line)

        return result

    def _update_selection_count(self, *_args) -> None:
        count = len(
            self.table.selectionModel().selectedRows()
        )
        self.selection_lbl.setText(f"Selected: {count}")

    # ═══════════════════════════════════════
    # Create
    # ═══════════════════════════════════════

    def _on_add(self) -> None:
        try:
            projects = self._get_project_views()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Project Error",
                f"Could not load project list:\n{exc}",
            )
            return

        if not projects:
            QMessageBox.information(
                self,
                "Project Required",
                "Create a Project first.",
            )
            return

        dialog = LineDialog(self, projects=projects)

        if self.current_project_id:
            index = dialog.project_combo.findData(
                self.current_project_id
            )
            if index >= 0:
                dialog.project_combo.setCurrentIndex(index)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.get_data()

        try:
            item = self.service.add_line(
                data["project_id"],
                data["line_number"],
                pid_number=data["pid_number"],
                iso_number=data["iso_number"],
                fluid_code=data["fluid_code"],
                fluid_name=data["fluid_name"],
                fluid_service=data["fluid_service"],
                design_pressure_barg=data["design_pressure_barg"],
                design_temp_c=data["design_temp_c"],
                pipe_class=data["pipe_class"],
                size_nps=data["size_nps"],
                schedule=data["schedule"],
                material=data["material"],
                from_point=data["from_point"],
                to_point=data["to_point"],
                remarks=data["remarks"],
            )
        except Exception as exc:
            logger.exception("Add Line List item failed")
            QMessageBox.critical(
                self,
                "Save Error",
                f"Could not add Line List item:\n{exc}",
            )
            return

        if not item:
            QMessageBox.warning(
                self,
                "Line Not Added",
                "Could not add line.\n\n"
                "The line number may already exist or "
                "the license limit may have been reached.",
            )
            return

        self._switch_to_project(data["project_id"])

        QMessageBox.information(
            self,
            "Success",
            f"Line '{data['line_number']}' added successfully.",
        )

    # ═══════════════════════════════════════
    # Edit
    # ═══════════════════════════════════════

    def _edit_selected(self) -> None:
        selected = self._selected_line_data()

        if not selected:
            QMessageBox.information(
                self,
                "Select Line",
                "Select a line first.",
            )
            return

        line = selected[0]

        try:
            projects = self._get_project_views()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Project Error",
                str(exc),
            )
            return

        dialog = LineDialog(
            self,
            projects=projects,
            existing_data=line,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.get_data()

        try:
            with self.db.session_scope() as session:
                existing = (
                    session.query(LineListItem)
                    .filter(
                        LineListItem.project_id == data["project_id"],
                        LineListItem.line_number == data["line_number"],
                    )
                    .first()
                )

                if existing and existing.id != line["id"]:
                    raise ValueError(
                        "Another line with this Line Number already "
                        "exists in the selected project."
                    )

                record = session.get(LineListItem, line["id"])

                if not record:
                    raise ValueError(
                        "The selected Line List record no longer exists."
                    )

                record.project_id = data["project_id"]
                record.line_number = data["line_number"]
                record.pid_number = data["pid_number"]
                record.iso_number = data["iso_number"]
                record.fluid_code = data["fluid_code"]
                record.fluid_name = data["fluid_name"]
                record.fluid_service = data["fluid_service"]
                record.design_pressure_barg = data[
                    "design_pressure_barg"
                ]
                record.design_temp_c = data["design_temp_c"]
                record.pipe_class = data["pipe_class"]
                record.size_nps = data["size_nps"]
                record.schedule = data["schedule"]
                record.material = data["material"]
                record.from_point = data["from_point"]
                record.to_point = data["to_point"]
                record.remarks = data["remarks"]

            self._switch_to_project(data["project_id"])

            QMessageBox.information(
                self,
                "Updated",
                f"Line '{data['line_number']}' updated successfully.",
            )

        except Exception as exc:
            logger.exception("Edit Line List item failed")
            QMessageBox.critical(
                self,
                "Update Error",
                f"Could not update line:\n{exc}",
            )

    # ═══════════════════════════════════════
    # Delete
    # ═══════════════════════════════════════

    def _delete_selected(self) -> None:
        selected = self._selected_line_data()

        if not selected:
            QMessageBox.information(
                self,
                "Select Line",
                "Select one or more lines to delete.",
            )
            return

        line_numbers = [
            line["line_number"]
            for line in selected
        ]

        preview = "\n".join(
            f"• {line_number}"
            for line_number in line_numbers[:10]
        )

        if len(line_numbers) > 10:
            preview += (
                f"\n... and {len(line_numbers) - 10} more line(s)"
            )

        reply = QMessageBox.warning(
            self,
            "⚠️ Confirm Delete",
            f"Delete {len(selected)} selected line(s)?\n\n"
            f"{preview}\n\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted_count = 0

        try:
            with self.db.session_scope() as session:
                for line in selected:
                    record = session.get(
                        LineListItem,
                        line["id"],
                    )

                    if record:
                        session.delete(record)
                        deleted_count += 1

            self.refresh()

            QMessageBox.information(
                self,
                "Deleted",
                f"{deleted_count} line(s) deleted successfully.",
            )

        except Exception as exc:
            logger.exception("Delete Line List item failed")
            QMessageBox.critical(
                self,
                "Delete Error",
                f"Could not delete selected line(s):\n{exc}",
            )

    # ═══════════════════════════════════════
    # Import CSV / Excel
    # ═══════════════════════════════════════

    def _on_import(self) -> None:
        if not self.current_project_id:
            QMessageBox.information(
                self,
                "Project Required",
                "Select a project first.",
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Line List",
            "",
            (
                "CSV / Excel (*.csv *.xlsx *.xls);;"
                "CSV (*.csv);;"
                "Excel (*.xlsx *.xls)"
            ),
        )

        if not path:
            return

        update_existing = (
            QMessageBox.question(
                self,
                "Update Existing Lines?",
                "If a Line Number already exists in this project:\n\n"
                "Yes = Update existing record\n"
                "No = Skip duplicate line\n\n"
                "Continue?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            == QMessageBox.StandardButton.Yes
        )

        ext = Path(path).suffix.lower()

        self.btn_import.setEnabled(False)
        self.btn_import.setText("⏳ Importing...")
        QApplication.processEvents()

        try:
            if ext == ".csv":
                created, updated, errors = (
                    self.service.import_from_csv(
                        self.current_project_id,
                        path,
                        update_existing=update_existing,
                    )
                )
            elif ext in (".xlsx", ".xls"):
                created, updated, errors = (
                    self.service.import_from_excel(
                        self.current_project_id,
                        path,
                        update_existing=update_existing,
                    )
                )
            else:
                QMessageBox.warning(
                    self,
                    "Unsupported Format",
                    "Supported formats are .csv, .xlsx and .xls.",
                )
                return

            self.refresh()

            message = (
                f"Created: {created}\n"
                f"Updated: {updated}\n"
                f"Skipped / Errors: {len(errors)}"
            )

            if errors:
                message += (
                    "\n\nFirst import issues:\n"
                    + "\n".join(
                        f"• {error}"
                        for error in errors[:15]
                    )
                )

                if len(errors) > 15:
                    message += (
                        f"\n... and {len(errors) - 15} more issue(s)"
                    )

            QMessageBox.information(
                self,
                "Import Result",
                message,
            )

        except Exception as exc:
            logger.exception("Line List import failed")
            QMessageBox.critical(
                self,
                "Import Error",
                f"Could not import file:\n{exc}",
            )

        finally:
            self.btn_import.setEnabled(True)
            self.btn_import.setText("📥 Import CSV/Excel")

    # ═══════════════════════════════════════
    # Export CSV
    # ═══════════════════════════════════════

    def _export_csv(self) -> None:
        if self.table.rowCount() == 0:
            QMessageBox.information(
                self,
                "No Data",
                "There is no Line List data to export.",
            )
            return

        project_code = (
            self.project_combo.currentText()
            .split("–")[0]
            .strip()
            .replace(" ", "_")
        )

        default_name = f"Line_List_{project_code}.csv"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Line List to CSV",
            default_name,
            "CSV Files (*.csv)",
        )

        if not path:
            return

        try:
            with open(
                path,
                "w",
                newline="",
                encoding="utf-8-sig",
            ) as file:
                writer = csv.writer(file)

                headers = [
                    self.table.horizontalHeaderItem(column).text()
                    for column in range(1, self.table.columnCount())
                ]
                writer.writerow(headers)

                for row in range(self.table.rowCount()):
                    row_values = []

                    for column in range(
                        1,
                        self.table.columnCount(),
                    ):
                        item = self.table.item(row, column)
                        row_values.append(
                            item.text() if item else ""
                        )

                    writer.writerow(row_values)

            QMessageBox.information(
                self,
                "Export Complete",
                f"Line List exported successfully:\n{path}",
            )

        except Exception as exc:
            logger.exception("CSV export failed")
            QMessageBox.critical(
                self,
                "Export Error",
                f"Could not export CSV:\n{exc}",
            )

    # ═══════════════════════════════════════
    # Details and Context menu
    # ═══════════════════════════════════════

    def _show_selected_details(self, *_args) -> None:
        selected = self._selected_line_data()

        if not selected:
            return

        dialog = LineDetailsDialog(selected[0], self)
        dialog.exec()

    def _show_context_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())

        if row < 0:
            return

        self.table.selectRow(row)

        selected = self._selected_line_data()

        if not selected:
            return

        line = selected[0]

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background:white;
                border:1px solid #dbe3ed;
                border-radius:7px;
                padding:4px;
            }
            QMenu::item {
                padding:8px 24px;
                font-size:12px;
                border-radius:4px;
            }
            QMenu::item:selected {
                background:#eff6ff;
                color:#1d4ed8;
            }
            QMenu::separator {
                height:1px;
                background:#e2e8f0;
                margin:4px 8px;
            }
        """)

        action_details = QAction("📋 View Line Details", self)
        action_details.triggered.connect(
            self._show_selected_details
        )
        menu.addAction(action_details)

        action_edit = QAction("✏️ Edit Line", self)
        action_edit.triggered.connect(self._edit_selected)
        menu.addAction(action_edit)

        menu.addSeparator()

        action_copy_line = QAction(
            "📋 Copy Line Number",
            self,
        )
        action_copy_line.triggered.connect(
            lambda: self._copy_text(line["line_number"])
        )
        menu.addAction(action_copy_line)

        action_copy_pid = QAction(
            "📋 Copy P&ID Number",
            self,
        )
        action_copy_pid.triggered.connect(
            lambda: self._copy_text(line["pid_number"])
        )
        menu.addAction(action_copy_pid)

        menu.addSeparator()

        action_delete = QAction(
            "🗑 Delete Selected Line(s)",
            self,
        )
        action_delete.triggered.connect(
            self._delete_selected
        )
        menu.addAction(action_delete)

        menu.exec(
            self.table.viewport().mapToGlobal(pos)
        )

    def _copy_text(self, text: str) -> None:
        if text:
            QApplication.clipboard().setText(text)
            self.summary_lbl.setText(f"Copied: {text}")

    # ═══════════════════════════════════════
    # Misc helpers
    # ═══════════════════════════════════════

    def _switch_to_project(self, project_id: int) -> None:
        index = self.project_combo.findData(project_id)

        if index >= 0:
            if self.project_combo.currentIndex() != index:
                self.project_combo.setCurrentIndex(index)
            else:
                self.refresh()
        else:
            self.refresh()