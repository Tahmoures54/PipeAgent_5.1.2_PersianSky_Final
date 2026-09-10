# -*- coding: utf-8 -*-
# ui/tabs/work_front_tab.py – PipeAgent 5.3.0
# Work Front Control, Resource Allocation, Machine Utilization & Dispatch Board
from __future__ import annotations

import csv
import logging
import datetime
from datetime import timezone
from typing import Optional

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QLineEdit, QTextEdit,
    QSpinBox, QDoubleSpinBox, QDialogButtonBox, QTabWidget,
    QFileDialog, QGroupBox, QDateEdit, QSplitter, QFrame,
    QMenu, QApplication, QAbstractItemView,
)
from PyQt6.QtGui import QColor, QFont, QBrush, QCursor, QAction

from db.manager import DatabaseManager
from db.models import (
    Project, WorkFront, WorkTeam, SiteMachine,
    WorkAssignment, ProjectAction,
)
from security.session import SessionManager

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
STATUS = [
    "Planned", "Ready", "Assigned", "In Progress",
    "Waiting", "Completed", "Blocked",
]
READINESS = [
    "Ready", "Material", "Drawing/ISO", "Access",
    "Permit", "Equipment", "Manpower", "QC/NDT", "Blocked",
]
PRIORITY = ["Low", "Normal", "High", "Urgent"]
ACTIVITIES = [
    "Material Handling", "Fit-up", "Welding", "NDT", "Repair",
    "Pipe Erection", "Support Installation", "Spool Installation",
    "Valve Installation", "Line Check", "Pressure Test", "Flushing",
    "Punch Clearance", "Painting/Insulation", "Documentation",
]


def _utcnow():
    """Naive UTC — replaces deprecated datetime.utcnow()."""
    return datetime.datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────
#  BADGE PALETTES
# ─────────────────────────────────────────────
PRIORITY_BADGES = {
    "Urgent": {"bg": "#fee2e2", "fg": "#991b1b", "icon": "🚨"},
    "High":   {"bg": "#fff1e6", "fg": "#9a3412", "icon": "🟠"},
    "Normal": {"bg": "#e0f2fe", "fg": "#075985", "icon": "🔵"},
    "Low":    {"bg": "#f1f5f9", "fg": "#475569", "icon": "⚪"},
}

STATUS_BADGES = {
    "Completed":   {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "In Progress": {"bg": "#e0f2fe", "fg": "#075985", "icon": "▶️"},
    "Assigned":    {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "📋"},
    "Ready":       {"bg": "#ccfbf1", "fg": "#115e59", "icon": "🟢"},
    "Planned":     {"bg": "#f1f5f9", "fg": "#475569", "icon": "📝"},
    "Waiting":     {"bg": "#fef3c7", "fg": "#92400e", "icon": "⏳"},
    "Blocked":     {"bg": "#fee2e2", "fg": "#991b1b", "icon": "⛔"},
}

READINESS_BADGES = {
    "Ready":       {"bg": "#dcfce7", "fg": "#166534", "icon": "🟢"},
    "Material":    {"bg": "#fee2e2", "fg": "#991b1b", "icon": "📦"},
    "Drawing/ISO": {"bg": "#fff1e6", "fg": "#9a3412", "icon": "📐"},
    "Access":      {"bg": "#fef3c7", "fg": "#92400e", "icon": "🪜"},
    "Permit":      {"bg": "#fee2e2", "fg": "#991b1b", "icon": "📜"},
    "Equipment":   {"bg": "#ffedd5", "fg": "#9a3412", "icon": "🚜"},
    "Manpower":    {"bg": "#fef3c7", "fg": "#92400e", "icon": "👷"},
    "QC/NDT":      {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "🛡️"},
    "Blocked":     {"bg": "#fee2e2", "fg": "#991b1b", "icon": "🚫"},
}

RESOURCE_STATUS_BADGES = {
    "Available":   {"bg": "#dcfce7", "fg": "#166534", "icon": "🟢"},
    "Busy":        {"bg": "#e0f2fe", "fg": "#075985", "icon": "⚙️"},
    "Standby":     {"bg": "#fef3c7", "fg": "#92400e", "icon": "⏳"},
    "Maintenance": {"bg": "#fee2e2", "fg": "#991b1b", "icon": "🔧"},
    "Unavailable": {"bg": "#f1f5f9", "fg": "#475569", "icon": "❌"},
}

DEFAULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}


WORKFRONT_STYLESHEET = """
    QWidget#workFrontTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #123b5d, stop:1 #1e527d);
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
    QTabWidget::pane {
        border: 1px solid #cbd5e1; border-radius: 8px;
        background: white; top: -1px;
    }
    QTabBar::tab {
        background: #f1f5f9; color: #475569;
        padding: 9px 18px; border: 1px solid #cbd5e1;
        border-bottom: none;
        border-top-left-radius: 6px; border-top-right-radius: 6px;
        font-weight: 700; font-size: 12px; margin-right: 2px;
    }
    QTabBar::tab:selected {
        background: white; color: #123b5d;
        border-bottom: 2px solid #3b82f6;
    }
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
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #2563eb, stop:1 #1d4ed8);
    }
    QPushButton#successBtn {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #10b981, stop:1 #059669);
        color: white; border: none; padding: 7px 15px;
        border-radius: 6px; font-weight: 700;
    }
    QPushButton#successBtn:hover {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #059669, stop:1 #047857);
    }
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
    QPushButton#dangerBtn:hover {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #dc2626, stop:1 #b91c1c);
    }
    QLineEdit, QComboBox, QTextEdit, QDoubleSpinBox, QSpinBox, QDateEdit {
        padding: 6px 10px; border: 1px solid #cbd5e1;
        border-radius: 6px; font-size: 12px;
    }
"""


# ─────────────────────────────────────────────
#  KPI CARD
# ─────────────────────────────────────────────
class WorkFrontKPICard(QFrame):
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
        elif highlight == "red":
            self.val_lbl.setStyleSheet("color: #991b1b; font-size: 19px; font-weight: 800;")
        elif highlight == "amber":
            self.val_lbl.setStyleSheet("color: #92400e; font-size: 19px; font-weight: 800;")
        elif highlight == "blue":
            self.val_lbl.setStyleSheet("color: #0369a1; font-size: 19px; font-weight: 800;")
        else:
            self.val_lbl.setStyleSheet("color: #0f172a; font-size: 19px; font-weight: 800;")


# ─────────────────────────────────────────────
#  WORK FRONT DIALOG
# ─────────────────────────────────────────────
class WorkFrontDialog(QDialog):
    def __init__(self, parent=None, projects=None, existing=None):
        super().__init__(parent)
        self.existing = existing
        self.is_edit = existing is not None
        self.setWindowTitle(
            "Edit Work Front Execution Plan" if self.is_edit
            else "Register New Work Front"
        )
        self.setMinimumWidth(580)
        self.setStyleSheet(WORKFRONT_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.project = QComboBox()
        if projects:
            for p in projects:
                self.project.addItem(
                    f"{p.project_code} — {getattr(p, 'title', '')}", p.id
                )

        self.code = QLineEdit()
        self.code.setPlaceholderText(
            "Unique Front Code * (e.g. WF-U100-PIPE-01)"
        )

        self.area = QLineEdit()
        self.area.setPlaceholderText(
            "Process Unit / Area (e.g. Unit 100 / Rack B)"
        )

        self.discipline = QComboBox()
        self.discipline.addItems([
            "Piping", "Mechanical", "E&I", "Civil",
            "QA/QC", "Commissioning", "Other",
        ])

        self.activity = QComboBox()
        self.activity.addItems(ACTIVITIES)
        self.activity.setEditable(True)

        self.description = QLineEdit()
        self.description.setPlaceholderText(
            "Scope summary / Work boundary description"
        )

        self.line = QLineEdit()
        self.line.setPlaceholderText(
            'Piping Line No (e.g. 8"-PL-101-A1A)'
        )

        self.iso = QLineEdit()
        self.iso.setPlaceholderText("ISO DWG Reference")

        self.spool = QLineEdit()
        self.spool.setPlaceholderText("Spool Identifier")

        self.start = QDateEdit(QDate.currentDate())
        self.start.setCalendarPopup(True)

        self.finish = QDateEdit(QDate.currentDate().addDays(3))
        self.finish.setCalendarPopup(True)

        self.priority = QComboBox()
        self.priority.addItems(PRIORITY)
        self.priority.setCurrentText("Normal")

        self.status = QComboBox()
        self.status.addItems(STATUS)

        self.ready = QComboBox()
        self.ready.addItems(READINESS)

        self.blocker = QLineEdit()
        self.blocker.setPlaceholderText(
            "Constraint reason if not ready (e.g. Awaiting Scaffolding / NDT)"
        )

        self.target = QDoubleSpinBox()
        self.target.setMaximum(1_000_000)
        self.target.setDecimals(2)
        self.target.setValue(100.0)

        self.unit = QLineEdit("DIA-INCH")
        self.shift = QComboBox()
        self.shift.addItems(["Day", "Night", "Both Shifts"])

        self.supervisor = QLineEdit()
        self.supervisor.setPlaceholderText(
            "Responsible Superintendent / Lead Foreman"
        )

        self.remarks = QTextEdit()
        self.remarks.setPlaceholderText(
            "Execution constraints, permit requirements, safety notes..."
        )
        self.remarks.setMaximumHeight(65)

        form.addRow("Target Project *:", self.project)
        form.addRow("Work Front Code *:", self.code)
        form.addRow("Process Area / Unit:", self.area)
        form.addRow("Discipline:", self.discipline)
        form.addRow("Activity Scope *:", self.activity)
        form.addRow("Scope Description:", self.description)
        form.addRow("Piping Line Number:", self.line)
        form.addRow("Isometric DWG:", self.iso)
        form.addRow("Spool Number:", self.spool)
        form.addRow("Planned Start Date:", self.start)
        form.addRow("Target Finish Date:", self.finish)
        form.addRow("Priority Level:", self.priority)
        form.addRow("Lifecycle Status:", self.status)
        form.addRow("Readiness Check:", self.ready)
        form.addRow("Blocker / Waiting For:", self.blocker)
        form.addRow("Target Quantity:", self.target)
        form.addRow("Unit of Measurement:", self.unit)
        form.addRow("Assigned Shift:", self.shift)
        form.addRow("Field Supervisor:", self.supervisor)
        form.addRow("Execution Remarks:", self.remarks)
        layout.addLayout(form)

        if self.is_edit and self.existing:
            self._load_existing_data()

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Work Front")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._validate_and_accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _load_existing_data(self):
        x = self.existing
        pid = getattr(x, "project_id", None)
        if pid:
            idx = self.project.findData(pid)
            if idx >= 0:
                self.project.setCurrentIndex(idx)

        self.code.setText(getattr(x, "front_code", ""))
        self.code.setReadOnly(True)
        self.area.setText(getattr(x, "area", "") or "")
        self.discipline.setCurrentText(
            getattr(x, "discipline", "Piping") or "Piping"
        )
        self.activity.setCurrentText(
            getattr(x, "activity_type", ACTIVITIES[0])
        )
        self.description.setText(getattr(x, "description", "") or "")
        self.line.setText(getattr(x, "line_number", "") or "")
        self.iso.setText(getattr(x, "iso_number", "") or "")
        self.spool.setText(getattr(x, "spool_number", "") or "")

        s_date = getattr(x, "planned_start", None)
        if s_date and isinstance(s_date, datetime.date):
            self.start.setDate(QDate(s_date.year, s_date.month, s_date.day))

        f_date = getattr(x, "planned_finish", None)
        if f_date and isinstance(f_date, datetime.date):
            self.finish.setDate(QDate(f_date.year, f_date.month, f_date.day))

        self.priority.setCurrentText(getattr(x, "priority", "Normal") or "Normal")
        self.status.setCurrentText(getattr(x, "status", "Planned") or "Planned")
        self.ready.setCurrentText(getattr(x, "readiness", "Ready") or "Ready")
        self.blocker.setText(getattr(x, "blocker", "") or "")
        self.target.setValue(float(getattr(x, "target_qty", 0.0) or 0.0))
        self.unit.setText(getattr(x, "unit", "DIA-INCH") or "DIA-INCH")
        self.shift.setCurrentText(getattr(x, "shift", "Day") or "Day")
        self.supervisor.setText(getattr(x, "supervisor", "") or "")
        self.remarks.setPlainText(getattr(x, "remarks", "") or "")

    def _validate_and_accept(self):
        if not self.code.text().strip():
            QMessageBox.warning(
                self, "Validation", "Work Front Code is mandatory."
            )
            self.code.setFocus()
            return
        self.accept()

    def data(self) -> dict:
        return {
            "project_id": self.project.currentData(),
            "front_code": self.code.text().strip(),
            "area": self.area.text().strip(),
            "discipline": self.discipline.currentText(),
            "activity_type": self.activity.currentText(),
            "description": self.description.text().strip(),
            "line_number": self.line.text().strip(),
            "iso_number": self.iso.text().strip(),
            "spool_number": self.spool.text().strip(),
            "planned_start": self.start.date().toPyDate(),
            "planned_finish": self.finish.date().toPyDate(),
            "priority": self.priority.currentText(),
            "status": self.status.currentText(),
            "readiness": self.ready.currentText(),
            "blocker": self.blocker.text().strip(),
            "target_qty": self.target.value(),
            "unit": self.unit.text().strip() or "DIA-INCH",
            "shift": self.shift.currentText(),
            "supervisor": self.supervisor.text().strip(),
            "remarks": self.remarks.toPlainText().strip(),
        }


# ─────────────────────────────────────────────
#  RESOURCE DIALOG (Team / Machine)
# ─────────────────────────────────────────────
class ResourceDialog(QDialog):
    def __init__(self, parent=None, kind: str = "team",
                 projects=None, existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.kind = kind
        self.is_edit = existing_data is not None
        self.setWindowTitle(
            ("Edit Execution Team" if self.is_edit
             else "Register New Execution Team")
            if kind == "team"
            else ("Edit Machine / Equipment" if self.is_edit
                  else "Register Machine / Equipment")
        )
        self.setMinimumWidth(480)
        self.setStyleSheet(WORKFRONT_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.project = QComboBox()
        if projects:
            for p in projects:
                self.project.addItem(
                    f"{p.project_code} — {getattr(p, 'title', '')}", p.id
                )

        self.code = QLineEdit()
        self.code.setPlaceholderText(
            "Team Code (e.g. T-PIP-01)" if kind == "team"
            else "Machine Code (e.g. CR-50T-01)"
        )

        self.name = QLineEdit()
        self.name.setPlaceholderText(
            "Team Name (e.g. Piping Erection Crew A)"
            if kind == "team"
            else "Machine Type (e.g. 50T Mobile Crane)"
        )

        self.discipline = QLineEdit("Piping")
        self.status = QComboBox()
        self.status.addItems([
            "Available", "Busy", "Standby", "Maintenance", "Unavailable",
        ])

        form.addRow("Project *:", self.project)
        form.addRow("Resource Code *:", self.code)
        form.addRow("Resource Name / Type *:", self.name)
        form.addRow("Discipline:", self.discipline)

        if kind == "team":
            self.skill = QLineEdit("6G Certified Welders & Pipefitters")
            self.supervisor = QLineEdit()
            self.supervisor.setPlaceholderText("Foreman / Gang Boss Name")
            self.manpower = QSpinBox()
            self.manpower.setRange(1, 500)
            self.manpower.setValue(6)
            self.shift = QComboBox()
            self.shift.addItems(["Day", "Night", "Both"])

            form.addRow("Skill / Trade:", self.skill)
            form.addRow("Team Supervisor:", self.supervisor)
            form.addRow("Manpower Headcount:", self.manpower)
            form.addRow("Assigned Shift:", self.shift)
        else:
            self.capacity = QLineEdit()
            self.capacity.setPlaceholderText(
                "Rating / Tonnage (e.g. 50 Tons / 400A)"
            )
            self.operator = QLineEdit()
            self.operator.setPlaceholderText(
                "Certified Operator Name / Badge"
            )

            form.addRow("Rated Capacity:", self.capacity)
            form.addRow("Assigned Operator:", self.operator)

        form.addRow("Operational Status:", self.status)
        layout.addLayout(form)

        if self.is_edit and existing_data:
            pid = existing_data.get("project_id")
            for i in range(self.project.count()):
                if self.project.itemData(i) == pid:
                    self.project.setCurrentIndex(i)
                    break
            self.code.setText(existing_data.get("code", ""))
            self.code.setReadOnly(True)
            self.name.setText(existing_data.get("name", ""))
            self.discipline.setText(existing_data.get("discipline", "Piping"))
            self.status.setCurrentText(existing_data.get("status", "Available"))

            if kind == "team":
                self.skill.setText(existing_data.get("skill", ""))
                self.supervisor.setText(existing_data.get("supervisor", ""))
                self.manpower.setValue(
                    int(existing_data.get("manpower") or 6)
                )
                if hasattr(self, "shift") and existing_data.get("shift"):
                    self.shift.setCurrentText(existing_data.get("shift"))
            else:
                self.capacity.setText(existing_data.get("capacity", ""))
                self.operator.setText(existing_data.get("operator", ""))

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Resource")
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
        if not self.code.text().strip():
            QMessageBox.warning(
                self, "Validation", "Resource Code is mandatory."
            )
            self.code.setFocus()
            return
        if not self.name.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Resource Name / Description is required."
            )
            self.name.setFocus()
            return
        self.accept()

    def data(self) -> dict:
        d = {
            "project_id": self.project.currentData(),
            "code": self.code.text().strip(),
            "name": self.name.text().strip(),
            "discipline": self.discipline.text().strip(),
            "status": self.status.currentText(),
        }
        if self.kind == "team":
            d.update({
                "skill": self.skill.text().strip(),
                "supervisor": self.supervisor.text().strip(),
                "manpower": self.manpower.value(),
                "shift": self.shift.currentText(),
            })
        else:
            d.update({
                "capacity": self.capacity.text().strip(),
                "operator": self.operator.text().strip(),
            })
        return d


# ─────────────────────────────────────────────
#  QUICK PROGRESS DIALOG
# ─────────────────────────────────────────────
class QuickProgressDialog(QDialog):
    def __init__(self, parent=None, front_data: dict = None):
        super().__init__(parent)
        self.front_data = front_data or {}
        self.setWindowTitle(
            f"⚡ Update Progress – Front: {self.front_data.get('front_code')}"
        )
        self.setMinimumWidth(440)
        self.setStyleSheet(WORKFRONT_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        target = float(self.front_data.get("target_qty") or 100.0)
        actual = float(self.front_data.get("actual_qty") or 0.0)
        unit = self.front_data.get("unit", "EA")

        info_lbl = QLabel(
            f"<b>Front Code:</b> {self.front_data.get('front_code')}<br>"
            f"<b>Activity:</b> {self.front_data.get('activity_type')} "
            f"&middot; <b>Target:</b> {target:.2f} {unit}"
        )
        info_lbl.setStyleSheet(
            "background: #f1f5f9; padding: 8px; border-radius: 6px;"
        )
        layout.addWidget(info_lbl)

        self.spn_actual = QDoubleSpinBox()
        self.spn_actual.setRange(0, 1_000_000)
        self.spn_actual.setDecimals(2)
        self.spn_actual.setValue(actual)
        self.spn_actual.setSuffix(f" {unit}")

        self.spn_progress = QDoubleSpinBox()
        self.spn_progress.setRange(0, 100)
        self.spn_progress.setDecimals(1)
        init_pct = (actual / target * 100.0) if target > 0 else 0.0
        self.spn_progress.setValue(min(100.0, init_pct))
        self.spn_progress.setSuffix(" %")

        self.spn_actual.valueChanged.connect(
            lambda v: self.spn_progress.setValue(
                min(100.0, (v / target * 100.0) if target > 0 else 0.0)
            )
        )

        self.cmb_status = QComboBox()
        self.cmb_status.addItems(STATUS)
        self.cmb_status.setCurrentText(
            self.front_data.get("status", "In Progress")
        )

        self.txt_notes = QTextEdit()
        self.txt_notes.setPlaceholderText(
            "Today's accomplishments, constraints, roadblocks..."
        )
        self.txt_notes.setMaximumHeight(65)

        form.addRow("Cumulative Actual Qty:", self.spn_actual)
        form.addRow("Physical Progress %:", self.spn_progress)
        form.addRow("Front Milestone Status:", self.cmb_status)
        form.addRow("Daily Progress Notes:", self.txt_notes)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_save = QPushButton("Apply Progress")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def get_progress_data(self) -> dict:
        return {
            "actual_qty": self.spn_actual.value(),
            "progress_pct": self.spn_progress.value(),
            "status": self.cmb_status.currentText(),
            "notes": self.txt_notes.toPlainText().strip(),
        }


# ─────────────────────────────────────────────
#  DETAIL DIALOG
# ─────────────────────────────────────────────
class WorkFrontDetailDialog(QDialog):
    def __init__(self, parent=None, front: dict = None,
                 assignments: list = None):
        super().__init__(parent)
        self.setWindowTitle(
            f"🔍 Work Front Dossier – {front.get('front_code', 'Front')}"
        )
        self.setMinimumSize(600, 500)
        self.setStyleSheet(WORKFRONT_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hdr = QLabel(
            f"📋 Construction Execution Dossier: {front.get('front_code')}"
        )
        hdr.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #123b5d;"
        )
        layout.addWidget(hdr)

        info_box = QGroupBox(
            "Work Front Planning & Engineering Parameters"
        )
        info_grid = QGridLayout(info_box)
        info_grid.setSpacing(8)

        details = [
            ("Front Code:", front.get("front_code", "—")),
            ("Activity Scope:", front.get("activity_type", "—")),
            ("Discipline:", front.get("discipline", "Piping")),
            ("Process Area / Unit:", front.get("area", "—")),
            ("Piping Line Number:", front.get("line_number", "—")),
            ("Isometric DWG:", front.get("iso_number", "—")),
            ("Target Spool No:", front.get("spool_number", "—")),
            ("Target / Actual Qty:",
             f"{front.get('actual_qty', 0)} / "
             f"{front.get('target_qty', 0)} {front.get('unit', '')}"),
            ("Physical Progress:", f"{front.get('progress_pct', 0):.1f}%"),
            ("Priority:", front.get("priority", "Normal")),
            ("Lifecycle Status:", front.get("status", "Planned")),
            ("Readiness Constraint:", front.get("readiness", "Ready")),
            ("Responsible Supervisor:", front.get("supervisor", "—")),
            ("Schedule Window:",
             f"{front.get('planned_start', '—')} to "
             f"{front.get('planned_finish', '—')}"),
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

        if front.get("blocker"):
            blk_box = QGroupBox(
                "⛔ Active Roadblock / Waiting Constraint"
            )
            blk_lay = QVBoxLayout(blk_box)
            lbl_blk = QLabel(
                f"<span style='color:#991b1b; font-weight:bold;'>"
                f"{front.get('blocker')}</span>"
            )
            lbl_blk.setWordWrap(True)
            blk_lay.addWidget(lbl_blk)
            layout.addWidget(blk_box)

        res_box = QGroupBox(
            f"Assigned Execution Resources "
            f"({len(assignments) if assignments else 0})"
        )
        res_lay = QVBoxLayout(res_box)
        res_tbl = QTableWidget(0, 5)
        res_tbl.setHorizontalHeaderLabels([
            "Resource Type", "Resource Tag / Code",
            "Assigned Date", "Plan Hours", "Status",
        ])
        res_tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        res_tbl.setAlternatingRowColors(True)
        res_tbl.verticalHeader().setVisible(False)

        if assignments:
            for a in assignments:
                row = res_tbl.rowCount()
                res_tbl.insertRow(row)
                res_tbl.setItem(row, 0, QTableWidgetItem(
                    a.get("resource_type", "")
                ))
                res_tbl.setItem(row, 1, QTableWidgetItem(
                    a.get("resource_code", "")
                ))
                res_tbl.setItem(row, 2, QTableWidgetItem(
                    str(a.get("assigned_date", ""))
                ))
                res_tbl.setItem(row, 3, QTableWidgetItem(
                    str(a.get("planned_hours", ""))
                ))
                res_tbl.setItem(row, 4, QTableWidgetItem(
                    a.get("status", "")
                ))

        res_lay.addWidget(res_tbl)
        layout.addWidget(res_box)

        btn_close = QPushButton("Close Dossier")
        btn_close.setObjectName("secondaryBtn")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class WorkFrontTab(QWidget):
    def __init__(self, db: DatabaseManager, session: SessionManager):
        super().__init__()
        self.setObjectName("workFrontTab")
        self.db = db
        self.session = session
        self.project_id: Optional[int] = None

        self._cached_fronts: list[dict] = []
        self._cached_teams: list[dict] = []
        self._cached_machines: list[dict] = []
        self._cached_dispatch: list[dict] = []

        self._build()
        self.setStyleSheet(WORKFRONT_STYLESHEET)
        self.refresh_all()

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
        t = QLabel("⚒️ Work Front Control & Resource Allocation Engine")
        t.setObjectName("mainTitle")
        s = QLabel(
            "Daily Execution Work Fronts, Piping Construction Progress, "
            "Constraint Mitigation, Gang Assignment & Equipment Dispatch."
        )
        s.setObjectName("subTitle")
        title_v.addWidget(t)
        title_v.addWidget(s)
        hdr_lay.addLayout(title_v, 1)

        proj_box = QHBoxLayout()
        lbl_p = QLabel("Project:")
        lbl_p.setStyleSheet("color: white; font-weight: bold;")
        proj_box.addWidget(lbl_p)

        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(220)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        proj_box.addWidget(self.project_combo)

        btn_refresh_all = QPushButton("🔄 Refresh All")
        btn_refresh_all.setObjectName("secondaryBtn")
        btn_refresh_all.clicked.connect(self.refresh_all)
        proj_box.addWidget(btn_refresh_all)
        hdr_lay.addLayout(proj_box)

        root.addWidget(header_card)

        kpi_lay = QHBoxLayout()
        kpi_lay.setSpacing(8)

        self.kpi_ready = WorkFrontKPICard(
            "Ready Work Fronts", "🟢", "#10b981"
        )
        self.kpi_active = WorkFrontKPICard(
            "In Progress (Active)", "▶️", "#3b82f6"
        )
        self.kpi_blocked = WorkFrontKPICard(
            "Blocked / Waiting", "⛔", "#ef4444"
        )
        self.kpi_teams = WorkFrontKPICard(
            "Available Gangs", "👷", "#0ea5e9"
        )
        self.kpi_machines = WorkFrontKPICard(
            "Available Cranes/Equip", "🚜", "#8b5cf6"
        )
        self.kpi_unassigned = WorkFrontKPICard(
            "Unassigned Ready", "⏳", "#f59e0b"
        )

        for k in (self.kpi_ready, self.kpi_active, self.kpi_blocked,
                  self.kpi_teams, self.kpi_machines, self.kpi_unassigned):
            kpi_lay.addWidget(k)
        root.addLayout(kpi_lay)

        self.tabs = QTabWidget()
        self.tabs.addTab(
            self._build_fronts_board(), "📋 Daily Work Fronts Master"
        )
        self.tabs.addTab(
            self._build_teams_board(), "👷 Technical & Execution Gangs"
        )
        self.tabs.addTab(
            self._build_machines_board(), "🚜 Site Machines & Rigging Cranes"
        )
        self.tabs.addTab(
            self._build_dispatch_board(),
            "⚡ Resource Dispatch & Assignment Board",
        )
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

    def _apply_badge_style(self, item: QTableWidgetItem, badge: dict):
        item.setBackground(QBrush(QColor(badge["bg"])))
        item.setForeground(QBrush(QColor(badge["fg"])))
        f = item.font()
        f.setBold(True)
        item.setFont(f)

    # ══════════════════════════════════════════════════════
    #  FRONTS BOARD
    # ══════════════════════════════════════════════════════
    def _build_fronts_board(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_front = QLineEdit()
        self.txt_search_front.setPlaceholderText(
            "🔍 Search Front Code, Line No, Spool, Activity, Area, Supervisor..."
        )
        self.txt_search_front.textChanged.connect(self._filter_fronts)
        tb.addWidget(self.txt_search_front, 1)

        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.addItem("All Statuses", None)
        for st in STATUS:
            self.cmb_filter_status.addItem(st, st)
        self.cmb_filter_status.currentIndexChanged.connect(self._filter_fronts)
        tb.addWidget(self.cmb_filter_status)

        self.cmb_filter_priority = QComboBox()
        self.cmb_filter_priority.addItem("All Priorities", None)
        for pr in PRIORITY:
            self.cmb_filter_priority.addItem(pr, pr)
        self.cmb_filter_priority.currentIndexChanged.connect(self._filter_fronts)
        tb.addWidget(self.cmb_filter_priority)

        btn_add = QPushButton("➕ New Front")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self.add_front)
        tb.addWidget(btn_add)

        btn_prog = QPushButton("⚡ Update Progress")
        btn_prog.setObjectName("secondaryBtn")
        btn_prog.clicked.connect(self._quick_progress_update)
        tb.addWidget(btn_prog)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(
            lambda: self._export_table_to_csv(
                self.fronts_table, "Work_Fronts_Master"
            )
        )
        tb.addWidget(btn_exp)

        btn_del = QPushButton("🗑️")
        btn_del.setObjectName("dangerBtn")
        btn_del.setToolTip("Delete Selected Work Front")
        btn_del.clicked.connect(self._delete_front)
        tb.addWidget(btn_del)
        l.addLayout(tb)

        self.fronts_table = QTableWidget(0, 14)
        self.fronts_table.setHorizontalHeaderLabels([
            "ID", "Front Code", "Area", "Activity Scope", "Line No",
            "ISO DWG", "Priority", "Readiness", "Status", "Progress %",
            "Target", "Actual", "Blocker / Waiting For", "Supervisor",
        ])
        self.fronts_table.setColumnHidden(0, True)
        self._setup_table_style(self.fronts_table)
        self.fronts_table.doubleClicked.connect(self._on_front_double_click)
        self.fronts_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.fronts_table.customContextMenuRequested.connect(
            self._show_front_context_menu
        )
        l.addWidget(self.fronts_table)

        action_bar = QHBoxLayout()
        btn_start = QPushButton("▶️ Start / Set Active")
        btn_start.setObjectName("secondaryBtn")
        btn_start.clicked.connect(
            lambda: self._bulk_status_fronts("In Progress", "Ready")
        )
        action_bar.addWidget(btn_start)

        btn_block = QPushButton("⛔ Mark Roadblocked / Waiting")
        btn_block.setObjectName("secondaryBtn")
        btn_block.clicked.connect(
            lambda: self._bulk_status_fronts("Waiting", "Blocked")
        )
        action_bar.addWidget(btn_block)

        btn_done = QPushButton("✅ Mark 100% Completed")
        btn_done.setObjectName("successBtn")
        btn_done.clicked.connect(self._complete_selected_fronts)
        action_bar.addWidget(btn_done)
        action_bar.addStretch()
        l.addLayout(action_bar)
        return w

    # ══════════════════════════════════════════════════════
    #  TEAMS BOARD
    # ══════════════════════════════════════════════════════
    def _build_teams_board(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_teams = QLineEdit()
        self.txt_search_teams.setPlaceholderText(
            "🔍 Search Team Code, Name, Trade, Supervisor..."
        )
        self.txt_search_teams.textChanged.connect(self._filter_teams)
        tb.addWidget(self.txt_search_teams, 1)

        btn_add_team = QPushButton("➕ Register Team")
        btn_add_team.setObjectName("primaryBtn")
        btn_add_team.clicked.connect(lambda: self.add_resource("team"))
        tb.addWidget(btn_add_team)

        btn_edit_team = QPushButton("✏️ Edit Team")
        btn_edit_team.setObjectName("secondaryBtn")
        btn_edit_team.clicked.connect(lambda: self._edit_resource("team"))
        tb.addWidget(btn_edit_team)

        btn_exp_team = QPushButton("📥 Export CSV")
        btn_exp_team.setObjectName("secondaryBtn")
        btn_exp_team.clicked.connect(
            lambda: self._export_table_to_csv(
                self.teams_table, "Execution_Teams_Register"
            )
        )
        tb.addWidget(btn_exp_team)

        btn_del_team = QPushButton("🗑️")
        btn_del_team.setObjectName("dangerBtn")
        btn_del_team.clicked.connect(lambda: self._delete_resource("team"))
        tb.addWidget(btn_del_team)
        l.addLayout(tb)

        self.teams_table = QTableWidget(0, 10)
        self.teams_table.setHorizontalHeaderLabels([
            "ID", "Team Code", "Team Name / Trade", "Discipline",
            "Skill Description", "Supervisor", "Headcount", "Shift",
            "Operational Status", "Current Work Front",
        ])
        self.teams_table.setColumnHidden(0, True)
        self._setup_table_style(self.teams_table)
        self.teams_table.doubleClicked.connect(
            lambda: self._edit_resource("team")
        )
        self.teams_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.teams_table.customContextMenuRequested.connect(
            lambda pos: self._show_resource_context_menu(pos, "team")
        )
        l.addWidget(self.teams_table)
        return w

    # ══════════════════════════════════════════════════════
    #  MACHINES BOARD
    # ══════════════════════════════════════════════════════
    def _build_machines_board(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_mach = QLineEdit()
        self.txt_search_mach.setPlaceholderText(
            "🔍 Search Machine Code, Equipment Type, Operator..."
        )
        self.txt_search_mach.textChanged.connect(self._filter_machines)
        tb.addWidget(self.txt_search_mach, 1)

        btn_add_mach = QPushButton("➕ Register Machine")
        btn_add_mach.setObjectName("primaryBtn")
        btn_add_mach.clicked.connect(lambda: self.add_resource("machine"))
        tb.addWidget(btn_add_mach)

        btn_edit_mach = QPushButton("✏️ Edit Machine")
        btn_edit_mach.setObjectName("secondaryBtn")
        btn_edit_mach.clicked.connect(lambda: self._edit_resource("machine"))
        tb.addWidget(btn_edit_mach)

        btn_exp_mach = QPushButton("📥 Export CSV")
        btn_exp_mach.setObjectName("secondaryBtn")
        btn_exp_mach.clicked.connect(
            lambda: self._export_table_to_csv(
                self.machines_table, "Site_Machines_Register"
            )
        )
        tb.addWidget(btn_exp_mach)

        btn_del_mach = QPushButton("🗑️")
        btn_del_mach.setObjectName("dangerBtn")
        btn_del_mach.clicked.connect(lambda: self._delete_resource("machine"))
        tb.addWidget(btn_del_mach)
        l.addLayout(tb)

        self.machines_table = QTableWidget(0, 9)
        self.machines_table.setHorizontalHeaderLabels([
            "ID", "Machine Code", "Equipment Type", "Rated Capacity",
            "Assigned Operator", "Operational Status",
            "Current Work Front", "Next Available Time", "Discipline",
        ])
        self.machines_table.setColumnHidden(0, True)
        self._setup_table_style(self.machines_table)
        self.machines_table.doubleClicked.connect(
            lambda: self._edit_resource("machine")
        )
        self.machines_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.machines_table.customContextMenuRequested.connect(
            lambda pos: self._show_resource_context_menu(pos, "machine")
        )
        l.addWidget(self.machines_table)
        return w

    # ══════════════════════════════════════════════════════
    #  DISPATCH BOARD
    # ══════════════════════════════════════════════════════
    def _build_dispatch_board(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_dispatch = QLineEdit()
        self.txt_search_dispatch.setPlaceholderText(
            "🔍 Search Dispatch Assignments (Front, Resource Code, Notes)..."
        )
        self.txt_search_dispatch.textChanged.connect(self._filter_dispatch)
        tb.addWidget(self.txt_search_dispatch, 1)

        btn_assign = QPushButton("⚡ Assign Resource to Front")
        btn_assign.setObjectName("primaryBtn")
        btn_assign.clicked.connect(self.assign_resource)
        tb.addWidget(btn_assign)

        btn_release = QPushButton("🔄 Release Resource (Task Done)")
        btn_release.setObjectName("secondaryBtn")
        btn_release.clicked.connect(self._release_assignment)
        tb.addWidget(btn_release)

        btn_exp_disp = QPushButton("📥 Export CSV")
        btn_exp_disp.setObjectName("secondaryBtn")
        btn_exp_disp.clicked.connect(
            lambda: self._export_table_to_csv(
                self.dispatch_table, "Dispatch_Board_Log"
            )
        )
        tb.addWidget(btn_exp_disp)

        btn_del_disp = QPushButton("🗑️")
        btn_del_disp.setObjectName("dangerBtn")
        btn_del_disp.clicked.connect(self._delete_assignment)
        tb.addWidget(btn_del_disp)
        l.addLayout(tb)

        self.dispatch_table = QTableWidget(0, 10)
        self.dispatch_table.setHorizontalHeaderLabels([
            "ID", "Work Front Code", "Resource Class",
            "Resource Tag / Code", "Assigned Date", "Release Date",
            "Assignment Status", "Plan Hours", "Actual Hours",
            "Operational Notes",
        ])
        self.dispatch_table.setColumnHidden(0, True)
        self._setup_table_style(self.dispatch_table)
        self.dispatch_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.dispatch_table.customContextMenuRequested.connect(
            self._show_dispatch_context_menu
        )
        l.addWidget(self.dispatch_table)
        return w

    # ══════════════════════════════════════════
    #  PROJECT LOADING
    # ══════════════════════════════════════════
    def _get_projects_lookup(self):
        with self.db.session_scope() as s:
            projects = s.query(Project).order_by(Project.project_code).all()
            return [
                type("P", (), {
                    "id": p.id,
                    "project_code": p.project_code,
                    "title": p.title,
                })()
                for p in projects
            ]

    def _on_project_changed(self):
        self.project_id = self.project_combo.currentData()
        self.refresh_fronts()
        self.refresh_teams()
        self.refresh_machines()
        self.refresh_dispatch()

    def refresh_all(self):
        projects = self._get_projects_lookup()
        cur = self.project_combo.currentData()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self.project_combo.addItem("All Projects", None)
        for p in projects:
            self.project_combo.addItem(
                f"{p.project_code} — {p.title}", p.id
            )
        if cur is not None:
            idx = self.project_combo.findData(cur)
            if idx >= 0:
                self.project_combo.setCurrentIndex(idx)
        self.project_combo.blockSignals(False)

        self.project_id = self.project_combo.currentData()
        self.refresh_fronts()
        self.refresh_teams()
        self.refresh_machines()
        self.refresh_dispatch()

    # ── REFRESH: FRONTS ──────────────────────────────────────
    def refresh_fronts(self):
        self.fronts_table.setSortingEnabled(False)
        self.fronts_table.setRowCount(0)
        self._cached_fronts = []

        try:
            with self.db.session_scope() as s:
                q = s.query(WorkFront).order_by(
                    WorkFront.priority.desc(),
                    WorkFront.planned_start,
                    WorkFront.id.desc(),
                )
                if self.project_id:
                    rows = q.filter(
                        WorkFront.project_id == self.project_id
                    ).all()
                else:
                    rows = q.all()

                assigned = s.query(WorkAssignment).filter(
                    WorkAssignment.status.in_(["Assigned", "In Progress"])
                ).all()
                assigned_fronts = {a.work_front_id for a in assigned}

                ready_cnt = active_cnt = blocked_cnt = unassigned_cnt = 0

                for x in rows:
                    st = x.status or "Planned"
                    rd = x.readiness or "Ready"
                    pr = x.priority or "Normal"

                    if rd == "Ready":
                        ready_cnt += 1
                    if st == "In Progress":
                        active_cnt += 1
                    if st in ("Waiting", "Blocked") or rd == "Blocked":
                        blocked_cnt += 1
                    if rd == "Ready" and x.id not in assigned_fronts:
                        unassigned_cnt += 1

                    self._cached_fronts.append({
                        "id": x.id,
                        "project_id": x.project_id,
                        "front_code": x.front_code,
                        "area": x.area or "",
                        "discipline": x.discipline or "Piping",
                        "activity_type": x.activity_type,
                        "description": x.description or "",
                        "line_number": x.line_number or "",
                        "iso_number": x.iso_number or "",
                        "spool_number": x.spool_number or "",
                        "priority": pr,
                        "readiness": rd,
                        "status": st,
                        "progress_pct": float(x.progress_pct or 0.0),
                        "target_qty": float(x.target_qty or 0.0),
                        "actual_qty": float(x.actual_qty or 0.0),
                        "unit": x.unit or "DIA-INCH",
                        "blocker": x.blocker or "",
                        "supervisor": x.supervisor or "",
                        "planned_start": str(x.planned_start or ""),
                        "planned_finish": str(x.planned_finish or ""),
                        "remarks": getattr(x, "remarks", "") or "",
                    })

                self.kpi_ready.set_value(
                    str(ready_cnt),
                    highlight="green" if ready_cnt > 0 else None,
                )
                self.kpi_active.set_value(
                    str(active_cnt),
                    highlight="blue" if active_cnt > 0 else None,
                )
                self.kpi_blocked.set_value(
                    str(blocked_cnt),
                    highlight="red" if blocked_cnt > 0 else "green",
                )
                self.kpi_unassigned.set_value(
                    str(unassigned_cnt),
                    highlight="amber" if unassigned_cnt > 0 else None,
                )
                self._filter_fronts()
        except Exception:
            logger.exception("Failed to load work fronts")

    def _filter_fronts(self):
        query = self.txt_search_front.text().strip().lower()
        st_filter = self.cmb_filter_status.currentData()
        pr_filter = self.cmb_filter_priority.currentData()

        self.fronts_table.setSortingEnabled(False)
        self.fronts_table.setRowCount(0)

        for x in self._cached_fronts:
            if st_filter and x["status"] != st_filter:
                continue
            if pr_filter and x["priority"] != pr_filter:
                continue
            if query:
                combined = (
                    f"{x['front_code']} {x['area']} {x['activity_type']} "
                    f"{x['line_number']} {x['spool_number']} "
                    f"{x['supervisor']} {x['blocker']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.fronts_table.rowCount()
            self.fronts_table.insertRow(r)
            self.fronts_table.setItem(r, 0, QTableWidgetItem(str(x["id"])))
            self.fronts_table.setItem(r, 1, QTableWidgetItem(x["front_code"]))
            self.fronts_table.setItem(r, 2, QTableWidgetItem(x["area"]))
            self.fronts_table.setItem(r, 3, QTableWidgetItem(x["activity_type"]))
            self.fronts_table.setItem(r, 4, QTableWidgetItem(x["line_number"]))
            self.fronts_table.setItem(r, 5, QTableWidgetItem(x["iso_number"]))

            pr_item = QTableWidgetItem(x["priority"])
            badge_pr = PRIORITY_BADGES.get(x["priority"], DEFAULT_BADGE)
            pr_item.setText(f"{badge_pr['icon']} {x['priority']}")
            self._apply_badge_style(pr_item, badge_pr)
            self.fronts_table.setItem(r, 6, pr_item)

            rd_item = QTableWidgetItem(x["readiness"])
            badge_rd = READINESS_BADGES.get(x["readiness"], DEFAULT_BADGE)
            rd_item.setText(f"{badge_rd['icon']} {x['readiness']}")
            self._apply_badge_style(rd_item, badge_rd)
            self.fronts_table.setItem(r, 7, rd_item)

            st_item = QTableWidgetItem(x["status"])
            badge_st = STATUS_BADGES.get(x["status"], DEFAULT_BADGE)
            st_item.setText(f"{badge_st['icon']} {x['status']}")
            self._apply_badge_style(st_item, badge_st)
            self.fronts_table.setItem(r, 8, st_item)

            pct_item = QTableWidgetItem(f"{x['progress_pct']:.1f}%")
            if x["progress_pct"] >= 100.0:
                pct_item.setForeground(QBrush(QColor("#166534")))
                f = pct_item.font()
                f.setBold(True)
                pct_item.setFont(f)
            self.fronts_table.setItem(r, 9, pct_item)

            self.fronts_table.setItem(r, 10, QTableWidgetItem(
                f"{x['target_qty']} {x['unit']}"
            ))
            self.fronts_table.setItem(r, 11, QTableWidgetItem(
                f"{x['actual_qty']} {x['unit']}"
            ))

            blk_item = QTableWidgetItem(x["blocker"])
            if x["blocker"]:
                blk_item.setForeground(QBrush(QColor("#991b1b")))
            self.fronts_table.setItem(r, 12, blk_item)

            self.fronts_table.setItem(r, 13, QTableWidgetItem(x["supervisor"]))

        self.fronts_table.setSortingEnabled(True)

    # ── REFRESH: TEAMS ───────────────────────────────────────
    def refresh_teams(self):
        self.teams_table.setSortingEnabled(False)
        self.teams_table.setRowCount(0)
        self._cached_teams = []

        try:
            with self.db.session_scope() as s:
                q = s.query(WorkTeam).order_by(
                    WorkTeam.status, WorkTeam.team_code
                )
                if self.project_id:
                    xs = q.filter_by(project_id=self.project_id).all()
                else:
                    xs = q.all()

                front_map = {
                    f.id: f.front_code for f in s.query(WorkFront).all()
                }
                avail_cnt = 0

                for x in xs:
                    st = x.status or "Available"
                    if st == "Available":
                        avail_cnt += 1
                    self._cached_teams.append({
                        "id": x.id,
                        "project_id": x.project_id,
                        "code": x.team_code,
                        "name": x.team_name,
                        "discipline": x.discipline or "Piping",
                        "skill": x.skill or "",
                        "supervisor": x.supervisor or "",
                        "manpower": x.manpower or 6,
                        "shift": getattr(x, "shift", "Day") or "Day",
                        "status": st,
                        "current_front": front_map.get(
                            x.current_front_id, "—"
                        ),
                    })

                self.kpi_teams.set_value(
                    str(avail_cnt),
                    highlight="green" if avail_cnt > 0 else None,
                )
                self._filter_teams()
        except Exception:
            logger.exception("Failed to load teams")

    def _filter_teams(self):
        query = self.txt_search_teams.text().strip().lower()
        self.teams_table.setSortingEnabled(False)
        self.teams_table.setRowCount(0)

        for x in self._cached_teams:
            if query:
                combined = (
                    f"{x['code']} {x['name']} {x['discipline']} "
                    f"{x['skill']} {x['supervisor']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.teams_table.rowCount()
            self.teams_table.insertRow(r)
            self.teams_table.setItem(r, 0, QTableWidgetItem(str(x["id"])))
            self.teams_table.setItem(r, 1, QTableWidgetItem(x["code"]))
            self.teams_table.setItem(r, 2, QTableWidgetItem(x["name"]))
            self.teams_table.setItem(r, 3, QTableWidgetItem(x["discipline"]))
            self.teams_table.setItem(r, 4, QTableWidgetItem(x["skill"]))
            self.teams_table.setItem(r, 5, QTableWidgetItem(x["supervisor"]))
            self.teams_table.setItem(r, 6, QTableWidgetItem(
                f"{x['manpower']} Men"
            ))
            self.teams_table.setItem(r, 7, QTableWidgetItem(x["shift"]))

            st_item = QTableWidgetItem(x["status"])
            badge = RESOURCE_STATUS_BADGES.get(x["status"], DEFAULT_BADGE)
            st_item.setText(f"{badge['icon']} {x['status']}")
            self._apply_badge_style(st_item, badge)
            self.teams_table.setItem(r, 8, st_item)

            self.teams_table.setItem(r, 9, QTableWidgetItem(x["current_front"]))

        self.teams_table.setSortingEnabled(True)

    # ── REFRESH: MACHINES ────────────────────────────────────
    def refresh_machines(self):
        self.machines_table.setSortingEnabled(False)
        self.machines_table.setRowCount(0)
        self._cached_machines = []

        try:
            with self.db.session_scope() as s:
                q = s.query(SiteMachine).order_by(
                    SiteMachine.status, SiteMachine.machine_code
                )
                if self.project_id:
                    xs = q.filter_by(project_id=self.project_id).all()
                else:
                    xs = q.all()

                front_map = {
                    f.id: f.front_code for f in s.query(WorkFront).all()
                }
                avail_cnt = 0

                for x in xs:
                    st = x.status or "Available"
                    if st == "Available":
                        avail_cnt += 1
                    self._cached_machines.append({
                        "id": x.id,
                        "project_id": x.project_id,
                        "code": x.machine_code,
                        "name": x.machine_type,
                        "capacity": x.capacity or "—",
                        "operator": x.operator or "—",
                        "status": st,
                        "current_front": front_map.get(
                            x.current_front_id, "—"
                        ),
                        "next_available": str(
                            getattr(x, "next_available", "") or "—"
                        ),
                        "discipline": getattr(x, "discipline", "Piping") or "Piping",
                    })

                self.kpi_machines.set_value(
                    str(avail_cnt),
                    highlight="green" if avail_cnt > 0 else None,
                )
                self._filter_machines()
        except Exception:
            logger.exception("Failed to load machines")

    def _filter_machines(self):
        query = self.txt_search_mach.text().strip().lower()
        self.machines_table.setSortingEnabled(False)
        self.machines_table.setRowCount(0)

        for x in self._cached_machines:
            if query:
                combined = (
                    f"{x['code']} {x['name']} {x['capacity']} {x['operator']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.machines_table.rowCount()
            self.machines_table.insertRow(r)
            self.machines_table.setItem(r, 0, QTableWidgetItem(str(x["id"])))
            self.machines_table.setItem(r, 1, QTableWidgetItem(x["code"]))
            self.machines_table.setItem(r, 2, QTableWidgetItem(x["name"]))
            self.machines_table.setItem(r, 3, QTableWidgetItem(x["capacity"]))
            self.machines_table.setItem(r, 4, QTableWidgetItem(x["operator"]))

            st_item = QTableWidgetItem(x["status"])
            badge = RESOURCE_STATUS_BADGES.get(x["status"], DEFAULT_BADGE)
            st_item.setText(f"{badge['icon']} {x['status']}")
            self._apply_badge_style(st_item, badge)
            self.machines_table.setItem(r, 5, st_item)

            self.machines_table.setItem(r, 6, QTableWidgetItem(x["current_front"]))
            self.machines_table.setItem(r, 7, QTableWidgetItem(x["next_available"]))
            self.machines_table.setItem(r, 8, QTableWidgetItem(x["discipline"]))

        self.machines_table.setSortingEnabled(True)

    # ── REFRESH: DISPATCH ────────────────────────────────────
    def refresh_dispatch(self):
        self.dispatch_table.setSortingEnabled(False)
        self.dispatch_table.setRowCount(0)
        self._cached_dispatch = []

        try:
            with self.db.session_scope() as s:
                q = s.query(WorkAssignment).order_by(
                    WorkAssignment.assigned_date.desc(),
                    WorkAssignment.id.desc(),
                )
                xs = q.all()
                front_map = {
                    f.id: f for f in s.query(WorkFront).all()
                }
                team_map = {
                    t.id: f"{t.team_code} ({t.team_name})"
                    for t in s.query(WorkTeam).all()
                }
                mach_map = {
                    m.id: f"{m.machine_code} ({m.machine_type})"
                    for m in s.query(SiteMachine).all()
                }

                for a in xs:
                    front_obj = front_map.get(a.work_front_id)
                    if (self.project_id and front_obj
                            and front_obj.project_id != self.project_id):
                        continue

                    res_tag = (
                        team_map.get(a.resource_id, "—")
                        if a.resource_type == "TEAM"
                        else mach_map.get(a.resource_id, "—")
                    )

                    self._cached_dispatch.append({
                        "id": a.id,
                        "work_front_id": a.work_front_id,
                        "front_code": (
                            front_obj.front_code if front_obj else "—"
                        ),
                        "resource_type": a.resource_type,
                        "resource_id": a.resource_id,
                        "resource_tag": res_tag,
                        "assigned_date": str(a.assigned_date or ""),
                        "release_date": str(a.release_date or "Active"),
                        "status": a.status or "Assigned",
                        "planned_hours": float(a.planned_hours or 0.0),
                        "actual_hours": float(a.actual_hours or 0.0),
                        "notes": a.notes or "",
                    })

                self._filter_dispatch()
        except Exception:
            logger.exception("Failed to load dispatch assignments")

    def _filter_dispatch(self):
        query = self.txt_search_dispatch.text().strip().lower()
        self.dispatch_table.setSortingEnabled(False)
        self.dispatch_table.setRowCount(0)

        for a in self._cached_dispatch:
            if query:
                combined = (
                    f"{a['front_code']} {a['resource_type']} "
                    f"{a['resource_tag']} {a['notes']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.dispatch_table.rowCount()
            self.dispatch_table.insertRow(r)
            self.dispatch_table.setItem(r, 0, QTableWidgetItem(str(a["id"])))
            self.dispatch_table.setItem(r, 1, QTableWidgetItem(a["front_code"]))
            self.dispatch_table.setItem(r, 2, QTableWidgetItem(
                "👷 Gang Crew" if a["resource_type"] == "TEAM"
                else "🚜 Heavy Machine"
            ))
            self.dispatch_table.setItem(r, 3, QTableWidgetItem(a["resource_tag"]))
            self.dispatch_table.setItem(r, 4, QTableWidgetItem(a["assigned_date"]))
            self.dispatch_table.setItem(r, 5, QTableWidgetItem(a["release_date"]))

            st_item = QTableWidgetItem(a["status"])
            badge = STATUS_BADGES.get(a["status"], DEFAULT_BADGE)
            st_item.setText(f"{badge['icon']} {a['status']}")
            self._apply_badge_style(st_item, badge)
            self.dispatch_table.setItem(r, 6, st_item)

            self.dispatch_table.setItem(r, 7, QTableWidgetItem(
                f"{a['planned_hours']} Hrs"
            ))
            self.dispatch_table.setItem(r, 8, QTableWidgetItem(
                f"{a['actual_hours']} Hrs"
            ))
            self.dispatch_table.setItem(r, 9, QTableWidgetItem(a["notes"]))

        self.dispatch_table.setSortingEnabled(True)

    # ══════════════════════════════════════════
    #  WORK FRONT CRUD
    # ══════════════════════════════════════════
    def add_front(self):
        projects = self._get_projects_lookup()
        if not projects:
            QMessageBox.warning(
                self, "Project Required",
                "Create a project first in Project Setup."
            )
            return

        dlg = WorkFrontDialog(self, projects=projects)
        if self.project_id:
            for i in range(dlg.project.count()):
                if dlg.project.itemData(i) == self.project_id:
                    dlg.project.setCurrentIndex(i)
                    break

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.data()
        try:
            with self.db.session_scope() as s:
                obj = WorkFront(
                    **d,
                    created_by=getattr(self.session, 'username', 'admin'),
                )
                s.add(obj)
                s.flush()
                s.add(ProjectAction(
                    project_id=obj.project_id,
                    action_type="WORK_FRONT_CREATE",
                    entity_type="WorkFront",
                    entity_id=obj.id,
                    line_number=obj.line_number,
                    description=(
                        f"Created work front '{obj.front_code}' "
                        f"({obj.activity_type})"
                    ),
                    user_name=getattr(self.session, 'username', 'admin'),
                ))

            self.refresh_fronts()
            QMessageBox.information(
                self, "Success",
                f"Work Front '{d['front_code']}' registered successfully."
            )
        except Exception as e:
            logger.exception("Failed to create work front")
            QMessageBox.critical(
                self, "Save Error",
                f"Could not create work front (Duplicate code?):\n{e}"
            )

    def _edit_front(self):
        rows = self.fronts_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "Selection", "Select a work front to edit.")
            return

        fid = int(self.fronts_table.item(rows[0].row(), 0).text())
        with self.db.session_scope() as s:
            x = s.get(WorkFront, fid)
            if not x:
                return
            vals = {
                c.name: getattr(x, c.name)
                for c in WorkFront.__table__.columns if c.name != 'id'
            }

        class SnapshotObj:
            pass

        snap = SnapshotObj()
        for k, v in vals.items():
            setattr(snap, k, v)

        projects = self._get_projects_lookup()
        dlg = WorkFrontDialog(self, projects=projects, existing=snap)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        nd = dlg.data()
        try:
            with self.db.session_scope() as s:
                x = s.get(WorkFront, fid)
                if x:
                    for k, v in nd.items():
                        setattr(x, k, v)
                    # ✅ FIXED: use naive UTC helper
                    x.updated_at = _utcnow()

            self.refresh_fronts()
            QMessageBox.information(
                self, "Updated",
                f"Work Front '{nd['front_code']}' updated."
            )
        except Exception as e:
            logger.exception("Failed to edit work front")
            QMessageBox.critical(self, "Error", f"Update failed:\n{e}")

    def _quick_progress_update(self):
        rows = self.fronts_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select a work front from the table to record progress."
            )
            return

        fid = int(self.fronts_table.item(rows[0].row(), 0).text())
        front_data = next(
            (f for f in self._cached_fronts if f["id"] == fid), None
        )
        if not front_data:
            return

        dlg = QuickProgressDialog(self, front_data=front_data)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        p_data = dlg.get_progress_data()
        try:
            with self.db.session_scope() as s:
                f = s.get(WorkFront, fid)
                if f:
                    f.actual_qty = p_data["actual_qty"]
                    f.progress_pct = p_data["progress_pct"]
                    f.status = p_data["status"]
                    if p_data["notes"]:
                        f.remarks = (
                            f"{f.remarks or ''}\n"
                            f"[{datetime.date.today()}]: {p_data['notes']}"
                        ).strip()
                    # ✅ FIXED
                    f.updated_at = _utcnow()

            self.refresh_fronts()
            QMessageBox.information(
                self, "Progress Updated",
                f"Work Front '{front_data['front_code']}' updated to "
                f"{p_data['progress_pct']:.1f}% completion."
            )
        except Exception as e:
            logger.exception("Failed to update progress")
            QMessageBox.critical(
                self, "Error", f"Could not update progress:\n{e}"
            )

    def _bulk_status_fronts(self, status: str, readiness: Optional[str] = None):
        rows = self.fronts_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection", "Select one or more work fronts."
            )
            return

        f_ids = [int(self.fronts_table.item(r.row(), 0).text()) for r in rows]
        try:
            with self.db.session_scope() as s:
                for fid in f_ids:
                    x = s.get(WorkFront, fid)
                    if x:
                        x.status = status
                        if readiness:
                            x.readiness = readiness
                        # ✅ FIXED
                        x.updated_at = _utcnow()

            self.refresh_fronts()
            QMessageBox.information(
                self, "Status Applied",
                f"Updated {len(f_ids)} front(s) to '{status}'."
            )
        except Exception as e:
            logger.exception("Failed to bulk transition fronts")
            QMessageBox.critical(
                self, "Error", f"Failed to update status:\n{e}"
            )

    def _complete_selected_fronts(self):
        rows = self.fronts_table.selectionModel().selectedRows()
        if not rows:
            return
        f_ids = [int(self.fronts_table.item(r.row(), 0).text()) for r in rows]
        if QMessageBox.question(
            self, "Confirm Completion",
            f"Mark {len(f_ids)} work front(s) as 100% Completed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as s:
                for fid in f_ids:
                    x = s.get(WorkFront, fid)
                    if x:
                        x.status = "Completed"
                        x.progress_pct = 100.0
                        x.actual_qty = x.target_qty
                        # ✅ FIXED
                        x.updated_at = _utcnow()

            self.refresh_fronts()
            QMessageBox.information(
                self, "Completed",
                "Selected work fronts marked as Completed."
            )
        except Exception:
            logger.exception("Failed to complete fronts")

    def _delete_front(self):
        rows = self.fronts_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection", "Select work front(s) to delete."
            )
            return

        f_ids = [int(self.fronts_table.item(r.row(), 0).text()) for r in rows]
        codes = [self.fronts_table.item(r.row(), 1).text() for r in rows]

        if QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(f_ids)} work front(s)?\n\n"
            f"Fronts: {', '.join(codes[:5])}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as s:
                for fid in f_ids:
                    x = s.get(WorkFront, fid)
                    if x:
                        s.delete(x)
            self.refresh_fronts()
            QMessageBox.information(self, "Deleted", "Selected work fronts deleted.")
        except Exception as e:
            logger.exception("Failed to delete work front")
            QMessageBox.critical(self, "Error", f"Could not delete:\n{e}")

    # ══════════════════════════════════════════
    #  RESOURCE CRUD
    # ══════════════════════════════════════════
    def add_resource(self, kind: str):
        projects = self._get_projects_lookup()
        if not projects:
            QMessageBox.warning(
                self, "Project Required", "Create a project first."
            )
            return

        dlg = ResourceDialog(self, kind=kind, projects=projects)
        if self.project_id:
            for i in range(dlg.project.count()):
                if dlg.project.itemData(i) == self.project_id:
                    dlg.project.setCurrentIndex(i)
                    break

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        x = dlg.data()
        try:
            with self.db.session_scope() as s:
                if kind == "team":
                    s.add(WorkTeam(
                        project_id=x["project_id"],
                        team_code=x["code"],
                        team_name=x["name"],
                        discipline=x["discipline"],
                        skill=x["skill"],
                        supervisor=x["supervisor"],
                        manpower=x["manpower"],
                        shift=x.get("shift", "Day"),
                        status=x["status"],
                    ))
                else:
                    s.add(SiteMachine(
                        project_id=x["project_id"],
                        machine_code=x["code"],
                        machine_type=x["name"],
                        capacity=x["capacity"],
                        operator=x["operator"],
                        status=x["status"],
                        discipline=x.get("discipline", "Piping"),
                    ))
            if kind == "team":
                self.refresh_teams()
            else:
                self.refresh_machines()
            QMessageBox.information(
                self, "Success",
                f"{kind.title()} '{x['code']}' registered successfully."
            )
        except Exception as e:
            logger.exception(f"Failed to add {kind}")
            QMessageBox.critical(
                self, "Save Error", f"Could not add {kind}:\n{e}"
            )

    def _edit_resource(self, kind: str):
        table = self.teams_table if kind == "team" else self.machines_table
        rows = table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection", f"Select a {kind} to edit."
            )
            return

        rid = int(table.item(rows[0].row(), 0).text())
        cache = (
            self._cached_teams if kind == "team" else self._cached_machines
        )
        res_data = next((r for r in cache if r["id"] == rid), None)
        if not res_data:
            return

        projects = self._get_projects_lookup()
        dlg = ResourceDialog(
            self, kind=kind, projects=projects, existing_data=res_data
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        x = dlg.data()
        try:
            with self.db.session_scope() as s:
                if kind == "team":
                    t = s.get(WorkTeam, rid)
                    if t:
                        t.team_name = x["name"]
                        t.discipline = x["discipline"]
                        t.skill = x["skill"]
                        t.supervisor = x["supervisor"]
                        t.manpower = x["manpower"]
                        t.shift = x.get("shift", "Day")
                        t.status = x["status"]
                else:
                    m = s.get(SiteMachine, rid)
                    if m:
                        m.machine_type = x["name"]
                        m.capacity = x["capacity"]
                        m.operator = x["operator"]
                        m.status = x["status"]

            if kind == "team":
                self.refresh_teams()
            else:
                self.refresh_machines()
            QMessageBox.information(
                self, "Updated",
                f"{kind.title()} '{res_data['code']}' updated."
            )
        except Exception as e:
            logger.exception(f"Failed to edit {kind}")
            QMessageBox.critical(self, "Error", f"Update failed:\n{e}")

    def _delete_resource(self, kind: str):
        table = self.teams_table if kind == "team" else self.machines_table
        rows = table.selectionModel().selectedRows()
        if not rows:
            return

        r_ids = [int(table.item(r.row(), 0).text()) for r in rows]
        codes = [table.item(r.row(), 1).text() for r in rows]

        if QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(r_ids)} {kind}(s)?\n\n"
            f"Items: {', '.join(codes[:5])}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as s:
                for rid in r_ids:
                    obj = s.get(
                        WorkTeam if kind == "team" else SiteMachine, rid
                    )
                    if obj:
                        s.delete(obj)
            if kind == "team":
                self.refresh_teams()
            else:
                self.refresh_machines()
            QMessageBox.information(self, "Deleted", f"Selected {kind}(s) deleted.")
        except Exception as e:
            logger.exception(f"Failed to delete {kind}")
            QMessageBox.critical(self, "Error", f"Could not delete:\n{e}")

    # ══════════════════════════════════════════
    #  DISPATCH / ASSIGNMENT
    # ══════════════════════════════════════════
    def assign_resource(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("⚡ Dispatch & Assign Resource to Work Front")
        dlg.setMinimumWidth(480)
        dlg.setStyleSheet(WORKFRONT_STYLESHEET)

        f = QFormLayout(dlg)
        f.setSpacing(8)

        front_combo = QComboBox()
        with self.db.session_scope() as s:
            q = s.query(WorkFront).filter(
                WorkFront.status.in_(
                    ["Planned", "Ready", "Waiting", "Assigned", "In Progress"]
                )
            )
            if self.project_id:
                fronts = q.filter_by(project_id=self.project_id).all()
            else:
                fronts = q.all()
            for x in fronts:
                front_combo.addItem(
                    f"{x.front_code} — {x.activity_type} ({x.readiness})",
                    x.id,
                )

        typ_combo = QComboBox()
        typ_combo.addItems(["TEAM", "MACHINE"])

        resource_combo = QComboBox()
        hours_spin = QDoubleSpinBox()
        hours_spin.setRange(0.5, 1000)
        hours_spin.setValue(8.0)
        hours_spin.setSuffix(" Hours")

        notes_edit = QLineEdit()
        notes_edit.setPlaceholderText(
            "Specific task instructions or shift details..."
        )

        def _load_available_resources():
            resource_combo.clear()
            with self.db.session_scope() as s:
                if typ_combo.currentText() == "TEAM":
                    q = s.query(WorkTeam).filter_by(status="Available")
                    if self.project_id:
                        q = q.filter_by(project_id=self.project_id)
                    for t in q.all():
                        resource_combo.addItem(
                            f"👷 {t.team_code} — {t.team_name} "
                            f"({t.manpower} Men)",
                            t.id,
                        )
                else:
                    q = s.query(SiteMachine).filter_by(status="Available")
                    if self.project_id:
                        q = q.filter_by(project_id=self.project_id)
                    for m in q.all():
                        resource_combo.addItem(
                            f"🚜 {m.machine_code} — {m.machine_type} "
                            f"({m.capacity})",
                            m.id,
                        )

        typ_combo.currentIndexChanged.connect(_load_available_resources)
        _load_available_resources()

        form_rows = [
            ("Target Work Front *:", front_combo),
            ("Resource Class *:", typ_combo),
            ("Available Resource *:", resource_combo),
            ("Budgeted Shift Hours:", hours_spin),
            ("Operational Notes:", notes_edit),
        ]
        for l_txt, w_obj in form_rows:
            f.addRow(l_txt, w_obj)

        btns = QHBoxLayout()
        btn_confirm = QPushButton("Confirm Dispatch")
        btn_confirm.setObjectName("primaryBtn")
        btn_confirm.clicked.connect(
            lambda: dlg.accept()
            if resource_combo.currentData()
            else QMessageBox.warning(
                dlg, "Validation", "Select an available resource."
            )
        )
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(dlg.reject)
        btns.addStretch()
        btns.addWidget(btn_confirm)
        btns.addWidget(btn_cancel)
        f.addRow(btns)

        if (dlg.exec() != QDialog.DialogCode.Accepted
                or not resource_combo.currentData()):
            return

        fid = front_combo.currentData()
        res_type = typ_combo.currentText()
        res_id = resource_combo.currentData()
        user = getattr(self.session, 'username', 'admin')

        try:
            with self.db.session_scope() as s:
                a = WorkAssignment(
                    work_front_id=fid,
                    resource_type=res_type,
                    resource_id=res_id,
                    planned_hours=hours_spin.value(),
                    notes=notes_edit.text().strip(),
                    assigned_by=user,
                    status="In Progress",
                    assigned_date=datetime.date.today(),
                )
                s.add(a)

                wf = s.get(WorkFront, fid)
                if wf:
                    wf.status = "In Progress"
                    wf.readiness = "Ready"

                if res_type == "TEAM":
                    t = s.get(WorkTeam, res_id)
                    if t:
                        t.status = "Busy"
                        t.current_front_id = fid
                else:
                    m = s.get(SiteMachine, res_id)
                    if m:
                        m.status = "Busy"
                        m.current_front_id = fid

            self.refresh_all()
            QMessageBox.information(
                self, "Dispatched",
                "Resource successfully dispatched and allocated to Work Front."
            )
        except Exception as e:
            logger.exception("Failed to assign resource")
            QMessageBox.critical(self, "Error", f"Dispatching failed:\n{e}")

    def _release_assignment(self):
        rows = self.dispatch_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select a dispatch record to release."
            )
            return

        aid = int(self.dispatch_table.item(rows[0].row(), 0).text())
        if QMessageBox.question(
            self, "Release Resource",
            "Mark task as completed and set resource back to Available?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as s:
                a = s.get(WorkAssignment, aid)
                if a:
                    a.status = "Completed"
                    a.release_date = datetime.date.today()

                    if a.resource_type == "TEAM":
                        t = s.get(WorkTeam, a.resource_id)
                        if t:
                            t.status = "Available"
                            t.current_front_id = None
                    else:
                        m = s.get(SiteMachine, a.resource_id)
                        if m:
                            m.status = "Available"
                            m.current_front_id = None

            self.refresh_all()
            QMessageBox.information(
                self, "Released",
                "Resource released and marked Available."
            )
        except Exception as e:
            logger.exception("Failed to release assignment")
            QMessageBox.critical(self, "Error", f"Could not release:\n{e}")

    def _delete_assignment(self):
        rows = self.dispatch_table.selectionModel().selectedRows()
        if not rows:
            return
        a_ids = [int(self.dispatch_table.item(r.row(), 0).text()) for r in rows]
        if QMessageBox.question(
            self, "Confirm Delete",
            f"Delete {len(a_ids)} dispatch record(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as s:
                for aid in a_ids:
                    a = s.get(WorkAssignment, aid)
                    if a:
                        s.delete(a)
            self.refresh_dispatch()
            QMessageBox.information(self, "Deleted", "Dispatch records removed.")
        except Exception:
            logger.exception("Failed to delete assignment")

    # ══════════════════════════════════════════
    #  DETAIL VIEWS & CONTEXT MENUS
    # ══════════════════════════════════════════
    def _on_front_double_click(self, index):
        row = index.row()
        fid = int(self.fronts_table.item(row, 0).text())
        front_data = next(
            (f for f in self._cached_fronts if f["id"] == fid), None
        )
        if not front_data:
            return

        assignments = []
        with self.db.session_scope() as s:
            team_map = {
                t.id: t.team_code for t in s.query(WorkTeam).all()
            }
            mach_map = {
                m.id: m.machine_code for m in s.query(SiteMachine).all()
            }
            for a in s.query(WorkAssignment).filter_by(
                work_front_id=fid
            ).all():
                res_code = (
                    team_map.get(a.resource_id, "—")
                    if a.resource_type == "TEAM"
                    else mach_map.get(a.resource_id, "—")
                )
                assignments.append({
                    "resource_type": a.resource_type,
                    "resource_code": res_code,
                    "assigned_date": a.assigned_date,
                    "planned_hours": a.planned_hours,
                    "status": a.status,
                })

        dlg = WorkFrontDetailDialog(
            self, front=front_data, assignments=assignments
        )
        dlg.exec()

    def _show_front_context_menu(self, pos):
        rows = self.fronts_table.selectionModel().selectedRows()
        if not rows:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 18px; }"
        )

        act_dossier = QAction("🔍 View Work Front Dossier", self)
        act_dossier.triggered.connect(
            lambda: self._on_front_double_click(self.fronts_table.currentIndex())
        )
        menu.addAction(act_dossier)

        act_prog = QAction("⚡ Update Physical Progress", self)
        act_prog.triggered.connect(self._quick_progress_update)
        menu.addAction(act_prog)

        menu.addSeparator()

        act_start = QAction("▶️ Start / Set Active", self)
        act_start.triggered.connect(
            lambda: self._bulk_status_fronts("In Progress", "Ready")
        )
        menu.addAction(act_start)

        act_block = QAction("⛔ Mark Roadblocked", self)
        act_block.triggered.connect(
            lambda: self._bulk_status_fronts("Waiting", "Blocked")
        )
        menu.addAction(act_block)

        act_done = QAction("✅ Mark 100% Completed", self)
        act_done.triggered.connect(self._complete_selected_fronts)
        menu.addAction(act_done)

        menu.addSeparator()

        act_edit = QAction("✏️ Edit Specifications", self)
        act_edit.triggered.connect(self._edit_front)
        menu.addAction(act_edit)

        act_copy = QAction("📋 Copy Front Code", self)
        act_copy.triggered.connect(
            lambda: QApplication.clipboard().setText(
                self.fronts_table.item(rows[0].row(), 1).text()
            )
        )
        menu.addAction(act_copy)

        act_del = QAction("🗑️ Delete Front(s)", self)
        act_del.triggered.connect(self._delete_front)
        menu.addAction(act_del)

        menu.exec(self.fronts_table.viewport().mapToGlobal(pos))

    def _show_resource_context_menu(self, pos, kind: str):
        table = self.teams_table if kind == "team" else self.machines_table
        rows = table.selectionModel().selectedRows()
        if not rows:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 18px; }"
        )

        act_edit = QAction(f"✏️ Edit {kind.title()} Details", self)
        act_edit.triggered.connect(lambda: self._edit_resource(kind))
        menu.addAction(act_edit)

        act_avail = QAction("🟢 Set as Available", self)
        act_avail.triggered.connect(
            lambda: self._quick_resource_status(kind, "Available")
        )
        menu.addAction(act_avail)

        act_maint = QAction("🔧 Set Maintenance / Standby", self)
        act_maint.triggered.connect(
            lambda: self._quick_resource_status(kind, "Maintenance")
        )
        menu.addAction(act_maint)

        menu.addSeparator()
        act_del = QAction(f"🗑️ Delete {kind.title()}", self)
        act_del.triggered.connect(lambda: self._delete_resource(kind))
        menu.addAction(act_del)
        menu.exec(table.viewport().mapToGlobal(pos))

    def _quick_resource_status(self, kind: str, status: str):
        table = self.teams_table if kind == "team" else self.machines_table
        rows = table.selectionModel().selectedRows()
        if not rows:
            return
        r_ids = [int(table.item(r.row(), 0).text()) for r in rows]
        try:
            with self.db.session_scope() as s:
                for rid in r_ids:
                    obj = s.get(
                        WorkTeam if kind == "team" else SiteMachine, rid
                    )
                    if obj:
                        obj.status = status
            if kind == "team":
                self.refresh_teams()
            else:
                self.refresh_machines()
        except Exception:
            logger.exception("Failed to quick change status")

    def _show_dispatch_context_menu(self, pos):
        rows = self.dispatch_table.selectionModel().selectedRows()
        if not rows:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 18px; }"
        )

        act_rel = QAction("🔄 Release Resource (Task Finished)", self)
        act_rel.triggered.connect(self._release_assignment)
        menu.addAction(act_rel)

        act_del = QAction("🗑️ Delete Dispatch Record", self)
        act_del.triggered.connect(self._delete_assignment)
        menu.addAction(act_del)
        menu.exec(self.dispatch_table.viewport().mapToGlobal(pos))

    # ══════════════════════════════════════════
    #  CSV EXPORT
    # ══════════════════════════════════════════
    def _export_table_to_csv(self, table: QTableWidget, prefix: str):
        if table.rowCount() == 0:
            QMessageBox.warning(
                self, "Export", "Table contains no data to export."
            )
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_code = self.project_combo.currentText().split("—")[0].strip()
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export CSV Report",
            f"{prefix}_{proj_code}_{timestamp}.csv",
            "CSV Files (*.csv)",
        )
        if not filename:
            return

        try:
            with open(filename, mode="w", newline="",
                      encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                headers = [
                    table.horizontalHeaderItem(c).text()
                    for c in range(1, table.columnCount())
                ]
                writer.writerow(headers)

                for r in range(table.rowCount()):
                    if not table.isRowHidden(r):
                        row_vals = [
                            table.item(r, c).text().strip()
                            if table.item(r, c) else ""
                            for c in range(1, table.columnCount())
                        ]
                        writer.writerow(row_vals)

            QMessageBox.information(
                self, "Export Complete",
                f"Data successfully saved to:\n{filename}"
            )
        except Exception as e:
            logger.exception("Failed to export CSV")
            QMessageBox.critical(
                self, "Export Error", f"Could not create CSV file:\n{e}"
            )