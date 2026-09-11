# -*- coding: utf-8 -*-
# ui/tabs/test_package_tab.py – PipeAgent 5.3.0
# Hydrostatic & Pneumatic Test Package (HTP/PTP) Management & Pressure Clearance Hub
from __future__ import annotations

import csv
import logging
import datetime
from datetime import timezone
from typing import Optional

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QDoubleSpinBox, QSpinBox, QTextEdit,
    QFrame, QFileDialog, QApplication, QMenu, QAbstractItemView,
    QGroupBox, QCheckBox, QDateEdit,
)
from PyQt6.QtGui import QColor, QFont, QBrush, QCursor, QAction

from db.manager import DatabaseManager
from db.models import Project, TestPackage, LineListItem, ProjectAction
from security.session import SessionManager
from services.license import increment_usage
from services.record_fields import apply_fields

TP_FINISH_FIELDS = (
    "area_name", "install_location", "dia_inch_total", "inch_meter",
    "linecheck_finished", "linecheck_result", "linecheck_result_date",
    "linecheck_subcontractor", "cleaning_finished", "cleaning_result",
    "cleaning_result_date", "cleaning_subcontractor",
    "pressure_test_finished", "pressure_test_result",
    "pressure_test_result_date", "pressure_test_subcontractor",
    "flushing_finished", "flushing_result", "flushing_result_date",
    "flushing_subcontractor", "face_cleaning_finished",
    "face_cleaning_result", "face_cleaning_result_date",
    "face_cleaning_subcontractor", "reinstatement_finished",
    "reinstatement_result", "reinstatement_result_date",
    "reinstatement_subcontractor",
)

# ── Test package statuses (fallback if config missing) ────────
try:
    from config import TEST_PACKAGE_STATUSES
except ImportError:
    TEST_PACKAGE_STATUSES = [
        "Planned / Boundaries Draft", "Pre-Test Punch Clearance",
        "Ready for Test",
        "Filling & Pressurization", "Under Pressure Hold",
        "Passed / Accepted",
        "Depressurized & Draining", "Reinstated & Boxed-Up",
        "Failed / Leaking", "Cancelled",
    ]

TEST_MEDIUMS = [
    "Demineralized Water (Hydro)", "Inhibited Service Water",
    "Nitrogen Gas (Pneumatic)",
    "Dry Plant Air (Pneumatic)", "Water + Glycol (Winterization)",
    "Helium Tracer Mix", "Other",
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
TP_STATUS_BADGES = {
    "Passed / Accepted":            {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Reinstated & Boxed-Up":        {"bg": "#ccfbf1", "fg": "#115e59", "icon": "🔄"},
    "Ready for Test":               {"bg": "#e0f2fe", "fg": "#075985", "icon": "📋"},
    "Under Pressure Hold":          {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "⏱️"},
    "Filling & Pressurization":     {"bg": "#e0e7ff", "fg": "#3730a3", "icon": "💧"},
    "Pre-Test Punch Clearance":     {"bg": "#ffedd5", "fg": "#9a3412", "icon": "🔍"},
    "Planned / Boundaries Draft":   {"bg": "#f1f5f9", "fg": "#475569", "icon": "📝"},
    "Failed / Leaking":             {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Depressurized & Draining":     {"bg": "#fef3c7", "fg": "#92400e", "icon": "🌊"},
    "Cancelled":                    {"bg": "#f8fafc", "fg": "#64748b", "icon": "🚫"},
}
DEFAULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}


# ─────────────────────────────────────────────
#  STYLESHEET
# ─────────────────────────────────────────────
TEST_PACKAGE_STYLESHEET = """
    QWidget#testPackageTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #0c3547, stop:1 #1a536e);
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
    QLineEdit, QComboBox, QTextEdit, QDoubleSpinBox, QSpinBox, QDateEdit {
        padding: 6px 10px; border: 1px solid #cbd5e1;
        border-radius: 6px; font-size: 12px;
    }
"""


# ─────────────────────────────────────────────
#  KPI CARD
# ─────────────────────────────────────────────
class TestPackageKPICard(QFrame):
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
        elif highlight == "red":
            self.val_lbl.setStyleSheet(
                "color: #991b1b; font-size: 19px; font-weight: 800;"
            )
        else:
            self.val_lbl.setStyleSheet(
                "color: #0f172a; font-size: 19px; font-weight: 800;"
            )


# ─────────────────────────────────────────────
#  TEST PACKAGE DIALOG
# ─────────────────────────────────────────────
class TPDialog(QDialog):
    def __init__(self, parent=None, projects: list = None,
                 existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = existing_data is not None
        self.setWindowTitle(
            "Edit Test Package Specifications" if self.is_edit
            else "Register New Pressure Test Package"
        )
        self.setMinimumWidth(540)
        self.setStyleSheet(TEST_PACKAGE_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.project_combo = QComboBox()
        if projects:
            for p in projects:
                self.project_combo.addItem(
                    f"{p.project_code} – {p.title}", p.id
                )

        self.pkg = QLineEdit()
        self.pkg.setPlaceholderText("e.g. HTP-1001 or TP-04-HYD")

        self.desc = QLineEdit()
        self.desc.setPlaceholderText(
            "Test Package Description / Boundary Scope"
        )

        self.medium = QComboBox()
        self.medium.addItems(TEST_MEDIUMS)
        self.medium.setEditable(True)

        self.pressure = QDoubleSpinBox()
        self.pressure.setRange(0, 5000)
        self.pressure.setDecimals(2)
        self.pressure.setSuffix(" bar(g)")

        self.design_pressure = QDoubleSpinBox()
        self.design_pressure.setRange(0, 5000)
        self.design_pressure.setDecimals(2)
        self.design_pressure.setSuffix(" bar(g)")

        self.duration = QSpinBox()
        self.duration.setRange(1, 1440)
        self.duration.setValue(30)
        self.duration.setSuffix(" min")

        self.lines = QLineEdit()
        self.lines.setPlaceholderText(
            'Comma-separated line numbers '
            '(e.g. 6"-PL-101, 4"-PL-102)'
        )

        self.status_combo = QComboBox()
        self.status_combo.addItems(TEST_PACKAGE_STATUSES)

        self.cert_no = QLineEdit()
        self.cert_no.setPlaceholderText(
            "Official QC Hydrotest Certificate No "
            "(e.g. CERT-HTP-2024-01)"
        )

        self.gauge_info = QLineEdit()
        self.gauge_info.setPlaceholderText(
            "Calibrated Test Gauges ID / Expiry "
            "(e.g. PG-01, PG-02 Cal: Valid)"
        )

        self.chk_punch_a = QCheckBox(
            "Punch Category 'A' Items 100% Cleared & Signed-off"
        )

        self.area_name = QLineEdit()
        self.install_loc = QComboBox()
        self.install_loc.addItems(["", "AG", "UG"])
        self.dia_inch = QDoubleSpinBox()
        self.dia_inch.setRange(0, 1e6)
        self.inch_meter = QDoubleSpinBox()
        self.inch_meter.setRange(0, 1e6)
        self.step_widgets = {}
        for key, label in (
            ("linecheck", "Line check"),
            ("cleaning", "Cleaning"),
            ("pressure_test", "Pressure test"),
            ("flushing", "Flushing / draining"),
            ("face_cleaning", "Face cleaning"),
            ("reinstatement", "Reinstatement"),
        ):
            done = QCheckBox("Finished")
            result = QComboBox()
            result.addItems(["", "Accept", "Reject", "N/A", "Pending"])
            when = QDateEdit()
            when.setCalendarPopup(True)
            when.setDisplayFormat("yyyy-MM-dd")
            when.setSpecialValueText("—")
            when.setDate(QDate(2000, 1, 1))
            sub = QLineEdit()
            self.step_widgets[key] = (done, result, when, sub)

        form.addRow("Target Project *:", self.project_combo)
        form.addRow("Package Number *:", self.pkg)
        form.addRow("Boundary Description:", self.desc)
        form.addRow("Testing Medium *:", self.medium)
        form.addRow("Specified Test Pressure *:", self.pressure)
        form.addRow("Line Design Pressure:", self.design_pressure)
        form.addRow("Minimum Hold Duration *:", self.duration)
        form.addRow("Included Piping Lines *:", self.lines)
        form.addRow("Package Milestone Status:", self.status_combo)
        form.addRow("Official Certificate No:", self.cert_no)
        form.addRow("Calibration Instruments Ref:", self.gauge_info)
        form.addRow("Pre-test Hold Clearance:", self.chk_punch_a)
        form.addRow("Area:", self.area_name)
        form.addRow("AG / UG:", self.install_loc)
        form.addRow("Dia-Inch Total:", self.dia_inch)
        form.addRow("Inch-Meter:", self.inch_meter)
        for key, label in (
            ("linecheck", "Line check"),
            ("cleaning", "Cleaning"),
            ("pressure_test", "Pressure test"),
            ("flushing", "Flushing / draining"),
            ("face_cleaning", "Face cleaning"),
            ("reinstatement", "Reinstatement"),
        ):
            done, result, when, sub = self.step_widgets[key]
            row = QHBoxLayout()
            row.addWidget(done)
            row.addWidget(result)
            row.addWidget(when)
            row.addWidget(sub)
            form.addRow(f"{label}:", row)
        layout.addLayout(form)

        if self.is_edit and existing_data:
            pid = existing_data.get("project_id")
            for i in range(self.project_combo.count()):
                if self.project_combo.itemData(i) == pid:
                    self.project_combo.setCurrentIndex(i)
                    break
            self.pkg.setText(
                existing_data.get("package_number", "")
            )
            self.pkg.setReadOnly(True)
            self.desc.setText(existing_data.get("description", ""))
            self.medium.setCurrentText(
                existing_data.get("test_medium", TEST_MEDIUMS[0])
            )
            self.pressure.setValue(
                float(existing_data.get("test_pressure_bar") or 0.0)
            )
            self.design_pressure.setValue(
                float(
                    existing_data.get("design_pressure_bar") or 0.0
                )
            )
            self.duration.setValue(
                int(existing_data.get("test_duration_min") or 30)
            )
            self.lines.setText(
                existing_data.get("line_numbers", "")
            )
            self.status_combo.setCurrentText(
                existing_data.get(
                    "status", TEST_PACKAGE_STATUSES[0]
                )
            )
            self.cert_no.setText(
                existing_data.get("certificate_no", "")
            )
            self.gauge_info.setText(
                existing_data.get("gauge_info", "")
            )
            self.chk_punch_a.setChecked(
                bool(existing_data.get("punch_a_cleared", False))
            )
            self.area_name.setText(existing_data.get("area_name", ""))
            self.install_loc.setCurrentText(existing_data.get("install_location") or "")
            self.dia_inch.setValue(float(existing_data.get("dia_inch_total") or 0))
            self.inch_meter.setValue(float(existing_data.get("inch_meter") or 0))
            for key, widgets in self.step_widgets.items():
                done, result, when, sub = widgets
                done.setChecked(bool(existing_data.get(f"{key}_finished")))
                result.setCurrentText(existing_data.get(f"{key}_result") or "")
                sub.setText(existing_data.get(f"{key}_subcontractor") or "")
                raw = existing_data.get(f"{key}_result_date")
                if raw:
                    parsed = QDate.fromString(str(raw)[:10], "yyyy-MM-dd")
                    if parsed.isValid():
                        when.setDate(parsed)

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Test Package")
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
        if not self.pkg.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Package Number is mandatory."
            )
            self.pkg.setFocus()
            return
        if not self.lines.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Please specify at least one piping line number."
            )
            self.lines.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        data = {
            "project_id": self.project_combo.currentData(),
            "package_number": self.pkg.text().strip(),
            "description": self.desc.text().strip(),
            "test_medium": self.medium.currentText().strip(),
            "test_pressure_bar": (
                self.pressure.value()
                if self.pressure.value() > 0 else None
            ),
            "design_pressure_bar": (
                self.design_pressure.value()
                if self.design_pressure.value() > 0 else None
            ),
            "test_duration_min": (
                self.duration.value()
                if self.duration.value() > 0 else None
            ),
            "line_numbers": self.lines.text().strip(),
            "status": self.status_combo.currentText(),
            "certificate_no": self.cert_no.text().strip(),
            "gauge_info": self.gauge_info.text().strip(),
            "punch_a_cleared": self.chk_punch_a.isChecked(),
            "area_name": self.area_name.text().strip(),
            "install_location": self.install_loc.currentText().strip() or None,
            "dia_inch_total": self.dia_inch.value() or None,
            "inch_meter": self.inch_meter.value() or None,
        }
        for key, widgets in self.step_widgets.items():
            done, result, when, sub = widgets
            data[f"{key}_finished"] = done.isChecked()
            data[f"{key}_result"] = result.currentText().strip() or None
            data[f"{key}_result_date"] = (
                None if when.date() == QDate(2000, 1, 1) else when.date().toPyDate()
            )
            data[f"{key}_subcontractor"] = sub.text().strip() or None
        return data


# ─────────────────────────────────────────────
#  TEST PACKAGE DETAIL DIALOG
# ─────────────────────────────────────────────
class TPDetailDialog(QDialog):
    def __init__(self, parent=None, package_data: dict = None):
        super().__init__(parent)
        self.setWindowTitle(
            f"🔍 Test Package Dossier – "
            f"{package_data.get('package_number', 'Package')}"
        )
        self.setMinimumSize(580, 480)
        self.setStyleSheet(TEST_PACKAGE_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hdr = QLabel(
            f"📋 Hydro / Pneumatic Dossier: "
            f"{package_data.get('package_number')}"
        )
        hdr.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #0c3547;"
        )
        layout.addWidget(hdr)

        info_box = QGroupBox(
            "Pressure Test Engineering Specifications"
        )
        info_grid = QGridLayout(info_box)
        info_grid.setSpacing(8)

        details = [
            ("Package Identifier:",
             package_data.get("package_number", "—")),
            ("Testing Medium:",
             package_data.get("test_medium", "—")),
            ("Specified Test Pressure:",
             f"{package_data.get('test_pressure_bar') or '—'} bar(g)"),
            ("Design Pressure:",
             f"{package_data.get('design_pressure_bar') or '—'} bar(g)"),
            ("Holding Duration:",
             f"{package_data.get('test_duration_min') or '—'} Minutes"),
            ("Current Milestone:",
             package_data.get("status", "Planned")),
            ("Test Execution Date:",
             str(package_data.get("test_date", "—"))),
            ("Official Certificate No:",
             package_data.get("certificate_no", "—")),
            ("Punch 'A' Pre-Clearance:",
             "✅ Verified & Closed"
             if package_data.get("punch_a_cleared")
             else "❌ Outstanding Hold"),
            ("Calibrated Gauges:",
             package_data.get("gauge_info", "—")),
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

        lines_box = QGroupBox(
            "Included Piping Lines & Test Boundaries"
        )
        lines_lay = QVBoxLayout(lines_box)
        txt_lines = QTextEdit()
        txt_lines.setReadOnly(True)
        txt_lines.setPlainText(
            package_data.get("line_numbers", "")
            or "No lines bound."
        )
        lines_lay.addWidget(txt_lines)
        layout.addWidget(lines_box)

        btn_close = QPushButton("Close Dossier")
        btn_close.setObjectName("secondaryBtn")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class TestPackageTab(QWidget):
    def __init__(self, db: DatabaseManager,
                 session: SessionManager):
        super().__init__()
        self.setObjectName("testPackageTab")
        self.db = db
        self.session = session
        self.project_id: Optional[int] = None
        self._cached_packages: list[dict] = []

        self._build_ui()
        self.setStyleSheet(TEST_PACKAGE_STYLESHEET)
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
        t = QLabel("💧 Hydrostatic & Pneumatic Test Packages")
        t.setObjectName("mainTitle")
        s = QLabel(
            "Pressure Testing Governance: Boundary Management, "
            "Pre-Test Punch 'A' Clearance, Pressure Holds & Reinstatement."
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

        self.kpi_total = TestPackageKPICard(
            "Total Test Packages", "💧", "#3b82f6"
        )
        self.kpi_passed = TestPackageKPICard(
            "Tested & Accepted", "✅", "#10b981"
        )
        self.kpi_rate = TestPackageKPICard(
            "Test Clearance Rate", "📈", "#059669"
        )
        self.kpi_testing = TestPackageKPICard(
            "Active Under Pressure", "⏱️", "#8b5cf6"
        )
        self.kpi_punch_holds = TestPackageKPICard(
            "Pending Punch A Holds", "⚠️", "#f59e0b"
        )

        for k in (self.kpi_total, self.kpi_passed, self.kpi_rate,
                  self.kpi_testing, self.kpi_punch_holds):
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
            "🔍 Search Package No, Piping Lines, Description, "
            "Medium, Cert No..."
        )
        self.txt_search.textChanged.connect(self._apply_filters)
        filter_lay.addWidget(self.txt_search, 1)

        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.addItem(
            "All Milestone Statuses", None
        )
        for st in TEST_PACKAGE_STATUSES:
            self.cmb_filter_status.addItem(st, st)
        self.cmb_filter_status.currentIndexChanged.connect(
            self._apply_filters
        )
        filter_lay.addWidget(self.cmb_filter_status)

        self.cmb_filter_medium = QComboBox()
        self.cmb_filter_medium.addItem("All Test Mediums", None)
        for med in TEST_MEDIUMS:
            self.cmb_filter_medium.addItem(med, med)
        self.cmb_filter_medium.currentIndexChanged.connect(
            self._apply_filters
        )
        filter_lay.addWidget(self.cmb_filter_medium)

        btn_new = QPushButton("➕ New Package")
        btn_new.setObjectName("primaryBtn")
        btn_new.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_new.clicked.connect(self._add)
        filter_lay.addWidget(btn_new)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(self._export_packages_csv)
        filter_lay.addWidget(btn_exp)

        btn_del = QPushButton("🗑️ Delete")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete_selected)
        filter_lay.addWidget(btn_del)

        layout.addWidget(filter_card)

        # Main table
        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels([
            "ID", "Package Number", "Area", "AG / UG", "Test Boundary Scope",
            "Medium", "Test P (bar)", "Line Check", "Pressure Test",
            "Reinstatement", "Milestone Status", "Certificate No",
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
            "Batch Transition Selected Test Packages To:"
        )
        lbl_batch.setStyleSheet("font-weight: bold; color: #334155;")
        status_row.addWidget(lbl_batch)

        self.st_combo = QComboBox()
        self.st_combo.addItems(TEST_PACKAGE_STATUSES)
        status_row.addWidget(self.st_combo)

        btn_apply = QPushButton("Apply Milestone")
        btn_apply.setObjectName("secondaryBtn")
        btn_apply.clicked.connect(self._status)
        status_row.addWidget(btn_apply)

        btn_pass = QPushButton("✅ Mark Passed & Certified")
        btn_pass.setObjectName("secondaryBtn")
        btn_pass.clicked.connect(
            lambda: self._quick_batch_status("Passed / Accepted")
        )
        status_row.addWidget(btn_pass)

        btn_reinst = QPushButton("🔄 Mark Reinstated")
        btn_reinst.setObjectName("secondaryBtn")
        btn_reinst.clicked.connect(
            lambda: self._quick_batch_status("Reinstated & Boxed-Up")
        )
        status_row.addWidget(btn_reinst)

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
                "Failed to load projects in TestPackageTab"
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
        self._cached_packages = []

        if not self.project_id:
            self._update_kpis(0, 0, 0, 0)
            return

        try:
            with self.db.session_scope() as s:
                pkgs = (
                    s.query(TestPackage)
                    .filter(
                        TestPackage.project_id == self.project_id
                    )
                    .order_by(TestPackage.package_number)
                    .all()
                )

                passed_cnt = testing_cnt = punch_hold_cnt = 0

                for p in pkgs:
                    st = (
                        p.status or "Planned / Boundaries Draft"
                    )
                    if st in ("Passed / Accepted",
                              "Reinstated & Boxed-Up", "Passed"):
                        passed_cnt += 1
                    elif st in ("Under Pressure Hold",
                                "Filling & Pressurization"):
                        testing_cnt += 1
                    elif (st == "Pre-Test Punch Clearance"
                            or not getattr(
                                p, "punch_a_cleared", False
                            )):
                        punch_hold_cnt += 1

                    self._cached_packages.append({
                        "id": p.id,
                        "project_id": p.project_id,
                        "package_number": p.package_number,
                        "description": p.description or "",
                        "test_medium": (
                            p.test_medium
                            or "Demineralized Water (Hydro)"
                        ),
                        "test_pressure_bar": p.test_pressure_bar,
                        "design_pressure_bar": getattr(
                            p, "design_pressure_bar", None
                        ),
                        "test_duration_min": p.test_duration_min,
                        "status": st,
                        "line_numbers": p.line_numbers or "",
                        "certificate_no": (
                            getattr(p, "certificate_no", "") or ""
                        ),
                        "gauge_info": (
                            getattr(p, "gauge_info", "") or ""
                        ),
                        "punch_a_cleared": bool(
                            getattr(p, "punch_a_cleared", False)
                        ),
                        "test_date": (
                            getattr(p, "test_date", "") or ""
                        ),
                        "area_name": getattr(p, "area_name", "") or "",
                        "install_location": getattr(p, "install_location", "") or "",
                        "dia_inch_total": getattr(p, "dia_inch_total", None),
                        "inch_meter": getattr(p, "inch_meter", None),
                        "linecheck_finished": bool(getattr(p, "linecheck_finished", False)),
                        "linecheck_result": getattr(p, "linecheck_result", "") or "",
                        "linecheck_result_date": getattr(p, "linecheck_result_date", None),
                        "linecheck_subcontractor": getattr(p, "linecheck_subcontractor", "") or "",
                        "cleaning_finished": bool(getattr(p, "cleaning_finished", False)),
                        "cleaning_result": getattr(p, "cleaning_result", "") or "",
                        "cleaning_result_date": getattr(p, "cleaning_result_date", None),
                        "cleaning_subcontractor": getattr(p, "cleaning_subcontractor", "") or "",
                        "pressure_test_finished": bool(getattr(p, "pressure_test_finished", False)),
                        "pressure_test_result": getattr(p, "pressure_test_result", "") or "",
                        "pressure_test_result_date": getattr(p, "pressure_test_result_date", None),
                        "pressure_test_subcontractor": getattr(p, "pressure_test_subcontractor", "") or "",
                        "flushing_finished": bool(getattr(p, "flushing_finished", False)),
                        "flushing_result": getattr(p, "flushing_result", "") or "",
                        "flushing_result_date": getattr(p, "flushing_result_date", None),
                        "flushing_subcontractor": getattr(p, "flushing_subcontractor", "") or "",
                        "face_cleaning_finished": bool(getattr(p, "face_cleaning_finished", False)),
                        "face_cleaning_result": getattr(p, "face_cleaning_result", "") or "",
                        "face_cleaning_result_date": getattr(p, "face_cleaning_result_date", None),
                        "face_cleaning_subcontractor": getattr(p, "face_cleaning_subcontractor", "") or "",
                        "reinstatement_finished": bool(getattr(p, "reinstatement_finished", False)),
                        "reinstatement_result": getattr(p, "reinstatement_result", "") or "",
                        "reinstatement_result_date": getattr(p, "reinstatement_result_date", None),
                        "reinstatement_subcontractor": getattr(p, "reinstatement_subcontractor", "") or "",
                    })

                self._update_kpis(
                    len(pkgs), passed_cnt,
                    testing_cnt, punch_hold_cnt,
                )
                self._apply_filters()

        except Exception as e:
            logger.exception("Test Package refresh failed")
            QMessageBox.warning(
                self, "Error",
                f"Failed to load test packages:\n{e}"
            )

    def _update_kpis(self, total: int, passed: int,
                     testing: int, punch_holds: int):
        self.kpi_total.set_value(str(total))
        self.kpi_passed.set_value(
            str(passed),
            highlight=(
                "green" if passed == total and total > 0 else None
            ),
        )
        rate = (passed / total * 100) if total > 0 else 0.0
        self.kpi_rate.set_value(
            f"{rate:.1f}%",
            highlight="green" if rate >= 95.0 else None,
        )
        self.kpi_testing.set_value(
            str(testing), highlight="blue" if testing > 0 else None
        )
        self.kpi_punch_holds.set_value(
            str(punch_holds),
            highlight="amber" if punch_holds > 0 else "green",
        )

    def _apply_filters(self):
        query = self.txt_search.text().strip().lower()
        st_filter = self.cmb_filter_status.currentData()
        med_filter = self.cmb_filter_medium.currentData()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for p in self._cached_packages:
            if st_filter and p["status"] != st_filter:
                continue
            if med_filter and p["test_medium"] != med_filter:
                continue
            if query:
                combined = (
                    f"{p['package_number']} {p['line_numbers']} "
                    f"{p['description']} {p['test_medium']} "
                    f"{p['certificate_no']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.table.rowCount()
            self.table.insertRow(r)

            self.table.setItem(
                r, 0, QTableWidgetItem(str(p["id"]))
            )
            self.table.setItem(
                r, 1, QTableWidgetItem(p["package_number"])
            )
            self.table.setItem(
                r, 2, QTableWidgetItem(p.get("area_name") or "")
            )
            self.table.setItem(
                r, 3, QTableWidgetItem(p.get("install_location") or "")
            )
            self.table.setItem(
                r, 4, QTableWidgetItem(p["description"])
            )
            self.table.setItem(
                r, 5, QTableWidgetItem(p["test_medium"])
            )
            self.table.setItem(
                r, 6, QTableWidgetItem(
                    f"{p['test_pressure_bar'] or '—'} bar"
                )
            )
            self.table.setItem(
                r, 7, QTableWidgetItem(p.get("linecheck_result") or "")
            )
            self.table.setItem(
                r, 8, QTableWidgetItem(p.get("pressure_test_result") or "")
            )
            self.table.setItem(
                r, 9, QTableWidgetItem(p.get("reinstatement_result") or "")
            )

            st_item = QTableWidgetItem(p["status"])
            badge = TP_STATUS_BADGES.get(
                p["status"], DEFAULT_BADGE
            )
            st_item.setText(f"{badge['icon']} {p['status']}")
            st_item.setBackground(QBrush(QColor(badge["bg"])))
            st_item.setForeground(QBrush(QColor(badge["fg"])))
            f = st_item.font()
            f.setBold(True)
            st_item.setFont(f)
            self.table.setItem(r, 10, st_item)
            self.table.setItem(
                r, 11, QTableWidgetItem(p["certificate_no"])
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

        dlg = TPDialog(self, projects=proj_list)
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
                "Pressure test package creation limit reached "
                "under current license."
            )
            return

        try:
            with self.db.session_scope() as s:
                pkg = TestPackage(
                    project_id=d["project_id"],
                    package_number=d["package_number"],
                    description=d["description"],
                    test_medium=d["test_medium"],
                    test_pressure_bar=d["test_pressure_bar"],
                    test_duration_min=d["test_duration_min"],
                    line_numbers=d["line_numbers"],
                    status=d["status"],
                    # ✅ FIXED: use _utcnow() helper
                    created_at=_utcnow(),
                )
                if hasattr(pkg, "certificate_no"):
                    pkg.certificate_no = d["certificate_no"]
                if hasattr(pkg, "gauge_info"):
                    pkg.gauge_info = d["gauge_info"]
                if hasattr(pkg, "punch_a_cleared"):
                    pkg.punch_a_cleared = d["punch_a_cleared"]
                if hasattr(pkg, "design_pressure_bar"):
                    pkg.design_pressure_bar = d["design_pressure_bar"]
                apply_fields(pkg, d, TP_FINISH_FIELDS)
                s.add(pkg)

            self.refresh()
            QMessageBox.information(
                self, "Success",
                f"Test Package '{d['package_number']}' created."
            )
        except Exception as e:
            logger.exception("Failed to create test package")
            QMessageBox.critical(
                self, "Error",
                f"Could not create package "
                f"(Duplicate identifier?):\n{e}"
            )

    def _edit_selected_package(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection", "Select a test package to edit."
            )
            return

        pkg_id = int(self.table.item(rows[0].row(), 0).text())
        pkg_data = next(
            (x for x in self._cached_packages
             if x["id"] == pkg_id), None
        )
        if not pkg_data:
            return

        proj_list = self._get_project_lookups()
        dlg = TPDialog(
            self, projects=proj_list, existing_data=pkg_data
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.get_data()
        try:
            with self.db.session_scope() as s:
                # ✅ FIXED: SQLAlchemy 2.0 — s.get(Model, pk)
                p = s.get(TestPackage, pkg_id)
                if p:
                    p.description = d["description"]
                    p.test_medium = d["test_medium"]
                    p.test_pressure_bar = d["test_pressure_bar"]
                    p.test_duration_min = d["test_duration_min"]
                    p.line_numbers = d["line_numbers"]
                    p.status = d["status"]
                    if hasattr(p, "certificate_no"):
                        p.certificate_no = d["certificate_no"]
                    if hasattr(p, "gauge_info"):
                        p.gauge_info = d["gauge_info"]
                    if hasattr(p, "punch_a_cleared"):
                        p.punch_a_cleared = d["punch_a_cleared"]
                    if hasattr(p, "design_pressure_bar"):
                        p.design_pressure_bar = (
                            d["design_pressure_bar"]
                        )
                    apply_fields(p, d, TP_FINISH_FIELDS)

            self.refresh()
            QMessageBox.information(
                self, "Updated",
                f"Test Package '{pkg_data['package_number']}' "
                f"specifications updated."
            )
        except Exception as e:
            logger.exception("Failed to edit test package")
            QMessageBox.critical(
                self, "Error", f"Update failed:\n{e}"
            )

    def _delete_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select one or more test packages to delete."
            )
            return

        pkg_ids = [
            int(self.table.item(r.row(), 0).text()) for r in rows
        ]
        pkg_nos = [
            self.table.item(r.row(), 1).text() for r in rows
        ]

        if QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(pkg_ids)} test package(s)?\n\n"
            f"Packages: {', '.join(pkg_nos[:5])}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as s:
                for pid in pkg_ids:
                    # ✅ FIXED: SQLAlchemy 2.0
                    p = s.get(TestPackage, pid)
                    if p:
                        s.delete(p)

            self.refresh()
            QMessageBox.information(
                self, "Deleted", "Selected test package(s) deleted."
            )
        except Exception as e:
            logger.exception("Failed to delete test packages")
            QMessageBox.critical(
                self, "Error", f"Could not delete packages:\n{e}"
            )

    # ══════════════════════════════════════════
    #  STATUS TRANSITIONS
    # ══════════════════════════════════════════
    def _status(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select one or more test packages to update."
            )
            return

        new_status = self.st_combo.currentText()
        self._quick_batch_status(new_status)

    def _quick_batch_status(self, new_status: str):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection", "Select at least one test package."
            )
            return

        pkg_ids = [
            int(self.table.item(r.row(), 0).text()) for r in rows
        ]
        try:
            with self.db.session_scope() as s:
                for pid in pkg_ids:
                    # ✅ FIXED: SQLAlchemy 2.0
                    p = s.get(TestPackage, pid)
                    if p:
                        p.status = new_status
                        if (new_status in (
                                "Passed / Accepted", "Passed")
                                and not getattr(
                                    p, "test_date", None
                                )):
                            p.test_date = datetime.date.today()

            self.refresh()
            QMessageBox.information(
                self, "Status Applied",
                f"Updated milestone to '{new_status}' for "
                f"{len(pkg_ids)} package(s)."
            )
        except Exception as e:
            logger.exception(
                "Failed to update test package status"
            )
            QMessageBox.critical(
                self, "Error", f"Failed to apply status:\n{e}"
            )

    # ══════════════════════════════════════════
    #  DETAIL VIEW / CONTEXT MENU
    # ══════════════════════════════════════════
    def _on_row_double_click(self, index):
        row = index.row()
        pkg_id = int(self.table.item(row, 0).text())
        pkg_data = next(
            (x for x in self._cached_packages
             if x["id"] == pkg_id), None
        )
        if pkg_data:
            dlg = TPDetailDialog(self, package_data=pkg_data)
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

        act_dossier = QAction("🔍 View Test Package Dossier", self)
        act_dossier.triggered.connect(
            lambda: self._on_row_double_click(
                self.table.currentIndex()
            )
        )
        menu.addAction(act_dossier)

        act_edit = QAction("✏️ Edit Package Specifications", self)
        act_edit.triggered.connect(self._edit_selected_package)
        menu.addAction(act_edit)

        menu.addSeparator()

        act_pass = QAction("✅ Mark as Passed & Certified", self)
        act_pass.triggered.connect(
            lambda: self._quick_batch_status("Passed / Accepted")
        )
        menu.addAction(act_pass)

        act_reinst = QAction("🔄 Mark as Reinstated & Boxed-Up", self)
        act_reinst.triggered.connect(
            lambda: self._quick_batch_status(
                "Reinstated & Boxed-Up"
            )
        )
        menu.addAction(act_reinst)

        menu.addSeparator()

        act_copy = QAction("📋 Copy Package Number", self)
        act_copy.triggered.connect(
            lambda: QApplication.clipboard().setText(
                self.table.item(rows[0].row(), 1).text()
            )
        )
        menu.addAction(act_copy)

        act_del = QAction("🗑️ Delete Package(s)", self)
        act_del.triggered.connect(self._delete_selected)
        menu.addAction(act_del)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ══════════════════════════════════════════
    #  EXPORT
    # ══════════════════════════════════════════
    def _export_packages_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(
                self, "Export",
                "No test packages available to export."
            )
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_code = self.proj_combo.currentText().split("–")[0].strip()
        default_name = (
            f"Pressure_Test_Packages_Register_"
            f"{proj_code}_{timestamp}.csv"
        )

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Test Packages Register",
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
                f"Test package register exported successfully "
                f"to:\n{filename}"
            )
        except Exception as e:
            logger.exception(
                "Failed to export test packages CSV"
            )
            QMessageBox.critical(
                self, "Export Error",
                f"Could not create CSV file:\n{e}"
            )