# -*- coding: utf-8 -*-
# ui/tabs/valves_tab.py – PipeAgent 5.3.0
# Valve Management, Workshop Pressure Testing (API 598 / ISO 5208)
# & Field Installation Register
from __future__ import annotations

import csv
import logging
import datetime
from datetime import timezone
from typing import Optional

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QTextEdit, QFrame, QFileDialog,
    QApplication, QMenu, QAbstractItemView, QGroupBox,
    QDoubleSpinBox, QCheckBox, QDateEdit, QSpinBox,
)
from PyQt6.QtGui import QColor, QFont, QBrush, QCursor, QAction

from db.manager import DatabaseManager
from db.models import Project, Valve
from security.session import SessionManager

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
VALVE_TYPES = [
    "Gate Valve", "Globe Valve", "Ball Valve",
    "Check Valve (Swing/Piston)",
    "Butterfly Valve", "Needle Valve", "Plug Valve",
    "Control Valve",
    "Pressure Safety Valve (PSV)", "Diaphragm Valve",
]

RATING_CLASSES = [
    "150# (PN 20)", "300# (PN 50)", "600# (PN 100)",
    "900# (PN 150)",
    "1500# (PN 250)", "2500# (PN 420)", "API 5000",
    "API 10000", "PN 16", "PN 25", "PN 40",
]

END_CONNECTIONS = [
    "Flanged (RF)", "Flanged (RTJ)", "Butt-Weld (BW)",
    "Socket-Weld (SW)",
    "Threaded (NPT)", "Wafer / Lug", "Union End",
]

VALVE_STATUSES = [
    "Received at Yard", "Workshop Tested (Passed)",
    "Test Failed / Overhaul",
    "Released for Erection", "Installed on Line",
    "Torqued & Boxed-Up", "Preserved / Inactive",
]


# ─────────────────────────────────────────────
#  BADGES
# ─────────────────────────────────────────────
VALVE_STATUS_BADGES = {
    "Installed on Line":        {"bg": "#dcfce7", "fg": "#166534", "icon": "🟢"},
    "Torqued & Boxed-Up":       {"bg": "#ccfbf1", "fg": "#115e59", "icon": "🔒"},
    "Workshop Tested (Passed)": {"bg": "#e0f2fe", "fg": "#075985", "icon": "🧪"},
    "Released for Erection":    {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "🚚"},
    "Received at Yard":         {"bg": "#fef3c7", "fg": "#92400e", "icon": "📦"},
    "Test Failed / Overhaul":   {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Preserved / Inactive":     {"bg": "#f1f5f9", "fg": "#475569", "icon": "🛡️"},
}
DEFAULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}

TEST_RESULT_BADGES = {
    "Passed":  {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Failed":  {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Pending": {"bg": "#fef3c7", "fg": "#92400e", "icon": "⏳"},
    "N/A":     {"bg": "#f1f5f9", "fg": "#64748b", "icon": "—"},
}


# ─────────────────────────────────────────────
#  STYLESHEET
# ─────────────────────────────────────────────
VALVES_STYLESHEET = """
    QWidget#valvesTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #1a3a50, stop:1 #2a5270);
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
class ValveKPICard(QFrame):
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
#  VALVE DIALOG
# ─────────────────────────────────────────────
class ValveDialog(QDialog):
    def __init__(self, parent=None, projects: list = None,
                 existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = existing_data is not None
        self.setWindowTitle(
            "Edit Valve Specifications" if self.is_edit
            else "Register New Valve"
        )
        self.setMinimumWidth(520)
        self.setStyleSheet(VALVES_STYLESHEET)

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
            'e.g. 6"-HV-1001 or V-04'
        )

        self.type_combo = QComboBox()
        self.type_combo.addItems(VALVE_TYPES)
        self.type_combo.setEditable(True)

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(
            'Piping Line No (e.g. 6"-PL-1001-A1A)'
        )

        self.size_edit = QLineEdit()
        self.size_edit.setPlaceholderText(
            'Nominal Size (e.g. 6" / DN150)'
        )

        self.rating_combo = QComboBox()
        self.rating_combo.addItems(RATING_CLASSES)
        self.rating_combo.setEditable(True)

        self.end_combo = QComboBox()
        self.end_combo.addItems(END_CONNECTIONS)

        self.body_mat = QLineEdit()
        self.body_mat.setPlaceholderText(
            "e.g. ASTM A216 WCB / SS316L / Dual Phase"
        )

        self.trim_mat = QLineEdit()
        self.trim_mat.setPlaceholderText(
            "e.g. 13Cr / Stellited / PTFE Seat"
        )

        self.mfr_edit = QLineEdit()
        self.mfr_edit.setPlaceholderText(
            "Valve Manufacturer (e.g. Cameron, KITZ, Flowserve)"
        )

        self.serial_edit = QLineEdit()
        self.serial_edit.setPlaceholderText(
            "Manufacturer Serial No / Heat No"
        )

        self.status_combo = QComboBox()
        self.status_combo.addItems(VALVE_STATUSES)

        self.remarks_edit = QTextEdit()
        self.remarks_edit.setPlaceholderText(
            "Special packing, locking device, gear-operator notes..."
        )
        self.remarks_edit.setMaximumHeight(65)

        form.addRow("Target Project *:", self.project_combo)
        form.addRow("Valve Tag Number *:", self.tag_edit)
        form.addRow("Valve Type *:", self.type_combo)
        form.addRow("Piping Line Number:", self.line_edit)
        form.addRow("Nominal Size (NPS):", self.size_edit)
        form.addRow("Pressure Rating Class:", self.rating_combo)
        form.addRow("End Connection:", self.end_combo)
        form.addRow("Body Material (MOC):", self.body_mat)
        form.addRow("Trim Specification:", self.trim_mat)
        form.addRow("Manufacturer:", self.mfr_edit)
        form.addRow("Serial / Heat Number:", self.serial_edit)
        form.addRow("Milestone Status:", self.status_combo)
        form.addRow("Engineering Remarks:", self.remarks_edit)
        layout.addLayout(form)

        if self.is_edit and existing_data:
            pid = existing_data.get("project_id")
            for i in range(self.project_combo.count()):
                if self.project_combo.itemData(i) == pid:
                    self.project_combo.setCurrentIndex(i)
                    break
            self.tag_edit.setText(
                existing_data.get("valve_tag", "")
            )
            self.tag_edit.setReadOnly(True)
            self.type_combo.setCurrentText(
                existing_data.get("valve_type", VALVE_TYPES[0])
            )
            self.line_edit.setText(
                existing_data.get("line_number", "")
            )
            self.size_edit.setText(
                existing_data.get("size_nps", "")
            )
            self.rating_combo.setCurrentText(
                existing_data.get(
                    "rating_class", RATING_CLASSES[0]
                )
            )
            self.end_combo.setCurrentText(
                existing_data.get(
                    "end_connection", END_CONNECTIONS[0]
                )
            )
            self.body_mat.setText(
                existing_data.get("body_material", "")
            )
            self.trim_mat.setText(
                existing_data.get("trim_material", "")
            )
            self.mfr_edit.setText(
                existing_data.get("manufacturer", "")
            )
            self.serial_edit.setText(
                existing_data.get("serial_number", "")
            )
            self.status_combo.setCurrentText(
                existing_data.get(
                    "status", VALVE_STATUSES[0]
                )
            )
            self.remarks_edit.setPlainText(
                existing_data.get("remarks", "")
            )

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Valve Record")
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
                "Valve Tag Number is mandatory."
            )
            self.tag_edit.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "project_id": self.project_combo.currentData(),
            "valve_tag": self.tag_edit.text().strip(),
            "valve_type": self.type_combo.currentText().strip(),
            "line_number": self.line_edit.text().strip(),
            "size_nps": self.size_edit.text().strip(),
            "rating_class": self.rating_combo.currentText().strip(),
            "end_connection": self.end_combo.currentText().strip(),
            "body_material": self.body_mat.text().strip(),
            "trim_material": self.trim_mat.text().strip(),
            "manufacturer": self.mfr_edit.text().strip(),
            "serial_number": self.serial_edit.text().strip(),
            "status": self.status_combo.currentText(),
            "remarks": self.remarks_edit.toPlainText().strip(),
        }


# ─────────────────────────────────────────────
#  VALVE TEST EXECUTION DIALOG (API 598)
# ─────────────────────────────────────────────
class ValveTestExecutionDialog(QDialog):
    def __init__(self, parent=None, valve_data: dict = None):
        super().__init__(parent)
        self.valve_data = valve_data or {}
        self.setWindowTitle(
            f"🧪 Record API 598 Pressure Test – "
            f"{self.valve_data.get('valve_tag', 'Valve')}"
        )
        self.setMinimumWidth(540)
        self.setStyleSheet(VALVES_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        info_banner = QLabel(
            f"<b>Tag:</b> {self.valve_data.get('valve_tag')} &middot; "
            f"<b>Type:</b> {self.valve_data.get('valve_type')} &middot; "
            f"<b>Size:</b> {self.valve_data.get('size_nps')} &middot; "
            f"<b>Class:</b> {self.valve_data.get('rating_class')}"
        )
        info_banner.setStyleSheet(
            "background: #f1f5f9; padding: 8px; border-radius: 6px; "
            "font-size: 12px;"
        )
        layout.addWidget(info_banner)

        self.chk_shell = QCheckBox(
            "Hydrostatic Shell Test Executed (1.5x Rating P)"
        )
        self.chk_shell.setChecked(True)

        self.spn_shell_p = QDoubleSpinBox()
        self.spn_shell_p.setRange(0, 2000)
        self.spn_shell_p.setValue(38.5)
        self.spn_shell_p.setSuffix(" bar(g)")

        self.spn_shell_dur = QSpinBox()
        self.spn_shell_dur.setRange(15, 3600)
        self.spn_shell_dur.setValue(60)
        self.spn_shell_dur.setSuffix(" sec")

        self.chk_seat = QCheckBox(
            "High-Pressure Hydrostatic Seat / Closure Test (1.1x)"
        )
        self.chk_seat.setChecked(True)

        self.spn_seat_p = QDoubleSpinBox()
        self.spn_seat_p.setRange(0, 2000)
        self.spn_seat_p.setValue(27.5)
        self.spn_seat_p.setSuffix(" bar(g)")

        self.chk_air = QCheckBox(
            "Low-Pressure Air Seat Test (6 bar(g) Bubble Leakage)"
        )
        self.chk_air.setChecked(True)

        self.chk_backseat = QCheckBox(
            "Backseat Test (For Gate/Globe Valves)"
        )
        if ("Gate" in self.valve_data.get("valve_type", "")
                or "Globe" in self.valve_data.get("valve_type", "")):
            self.chk_backseat.setChecked(True)

        self.txt_leakage = QLineEdit(
            "0 Drops/min (Zero Leakage per API 598 Rate A)"
        )
        self.txt_witness = QLineEdit(
            "Third Party QC Inspector (TPI)"
        )

        self.txt_cert = QLineEdit()
        self.txt_cert.setPlaceholderText("e.g. VTR-2024-001")

        self.dt_test = QDateEdit(QDate.currentDate())
        self.dt_test.setCalendarPopup(True)

        form.addRow("Shell Hydro Test:", self.chk_shell)
        form.addRow("Shell Test Pressure:", self.spn_shell_p)
        form.addRow("Shell Hold Duration:", self.spn_shell_dur)
        form.addRow("HP Hydro Seat Test:", self.chk_seat)
        form.addRow("Seat Test Pressure:", self.spn_seat_p)
        form.addRow("LP Air Seat Test:", self.chk_air)
        form.addRow("Backseat Seal Test:", self.chk_backseat)
        form.addRow("Measured Seat Leakage:", self.txt_leakage)
        form.addRow("Inspection Witness By:", self.txt_witness)
        form.addRow("Test Certificate No *:", self.txt_cert)
        form.addRow("Testing Date:", self.dt_test)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Test Certificate")
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
        if not self.txt_cert.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Test Certificate Number is required."
            )
            self.txt_cert.setFocus()
            return
        self.accept()

    def get_test_data(self) -> dict:
        qd = self.dt_test.date()
        return {
            "hydro_shell_test": self.chk_shell.isChecked(),
            "hydro_shell_pressure_bar": (
                self.spn_shell_p.value()
                if self.chk_shell.isChecked() else None
            ),
            "shell_duration_sec": self.spn_shell_dur.value(),
            "hydro_seat_test": self.chk_seat.isChecked(),
            "hydro_seat_pressure_bar": (
                self.spn_seat_p.value()
                if self.chk_seat.isChecked() else None
            ),
            "air_seat_test": self.chk_air.isChecked(),
            "backseat_test": self.chk_backseat.isChecked(),
            "leakage_rate": self.txt_leakage.text().strip(),
            "test_witness": self.txt_witness.text().strip(),
            "certificate_no": self.txt_cert.text().strip(),
            "test_date": datetime.date(
                qd.year(), qd.month(), qd.day()
            ),
        }


# ─────────────────────────────────────────────
#  VALVE DETAIL DIALOG
# ─────────────────────────────────────────────
class ValveDetailDialog(QDialog):
    def __init__(self, parent=None, valve: dict = None):
        super().__init__(parent)
        self.setWindowTitle(
            f"🔍 Valve Dossier – Tag: "
            f"{valve.get('valve_tag', 'Valve')}"
        )
        self.setMinimumSize(580, 480)
        self.setStyleSheet(VALVES_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hdr = QLabel(
            f"📋 Engineering & Inspection Dossier: "
            f"{valve.get('valve_tag')}"
        )
        hdr.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #1a3a50;"
        )
        layout.addWidget(hdr)

        info_box = QGroupBox(
            "Mechanical & Design Specifications"
        )
        info_grid = QGridLayout(info_box)
        info_grid.setSpacing(8)

        details = [
            ("Valve Tag Number:", valve.get("valve_tag", "—")),
            ("Functional Type:", valve.get("valve_type", "—")),
            ("Piping Line Number:", valve.get("line_number", "—")),
            ("Nominal Size:", valve.get("size_nps", "—")),
            ("Pressure Rating:", valve.get("rating_class", "—")),
            ("End Connection:", valve.get("end_connection", "—")),
            ("Body Material (MOC):", valve.get("body_material", "—")),
            ("Trim Specification:", valve.get("trim_material", "—")),
            ("Manufacturer:", valve.get("manufacturer", "—")),
            ("Serial / Heat Number:", valve.get("serial_number", "—")),
            ("Milestone Status:", valve.get("status", "Received")),
            ("Installation Date:",
             str(valve.get("installed_date") or "Not Installed")),
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

        test_box = QGroupBox(
            "API 598 Workshop Pressure Test Results"
        )
        test_grid = QGridLayout(test_box)
        test_grid.setSpacing(8)

        yn = lambda v: "✅ Passed" if v else "❌ Not Done / Failed"
        tests = [
            ("Shell Hydro Test:",
             yn(valve.get("hydro_shell_test"))),
            ("Shell Pressure:",
             f"{valve.get('hydro_shell_pressure_bar') or '—'} bar(g)"),
            ("HP Seat Closure:",
             yn(valve.get("hydro_seat_test"))),
            ("Seat Pressure:",
             f"{valve.get('hydro_seat_pressure_bar') or '—'} bar(g)"),
            ("Test Certificate:",
             valve.get("certificate_no", "—")),
            ("QC Witness:", valve.get("test_witness", "—")),
        ]

        for i, (label, val) in enumerate(tests):
            lbl_w = QLabel(f"<b>{label}</b>")
            lbl_w.setStyleSheet("color: #475569;")
            val_w = QLabel(str(val))
            val_w.setStyleSheet("color: #0f172a; font-weight: 600;")
            r, c = divmod(i, 2)
            test_grid.addWidget(lbl_w, r, c * 2)
            test_grid.addWidget(val_w, r, c * 2 + 1)

        layout.addWidget(test_box)

        btn_close = QPushButton("Close Dossier")
        btn_close.setObjectName("secondaryBtn")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class ValvesTab(QWidget):
    def __init__(self, db: DatabaseManager,
                 session_manager: SessionManager):
        super().__init__()
        self.setObjectName("valvesTab")
        self.db = db
        self.session_manager = session_manager
        self.project_id: Optional[int] = None
        self._cached_valves: list[dict] = []

        self._build_ui()
        self.setStyleSheet(VALVES_STYLESHEET)
        self._load_projects()

    # ── SESSION HELPER ───────────────────────────────────────
    def _get_session(self):
        return self.db.get_session()

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
        t = QLabel(
            "🔩 Valve Management, API 598 Testing & Site Erection"
        )
        t.setObjectName("mainTitle")
        s = QLabel(
            "Valve Quality Lifecycle: Receipt at Yard, "
            "Shell & Seat Hydro Testing, Calibration, Tagging, "
            "and On-Line Installation."
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

        self.kpi_total = ValveKPICard(
            "Total Valves Scope", "🔩", "#3b82f6"
        )
        self.kpi_tested = ValveKPICard(
            "Tested & Passed (API 598)", "🧪", "#10b981"
        )
        self.kpi_rate = ValveKPICard(
            "Testing Clearance %", "📈", "#059669"
        )
        self.kpi_untested = ValveKPICard(
            "Pending Workshop Test", "⏳", "#f59e0b"
        )
        self.kpi_installed = ValveKPICard(
            "Installed on Line", "🟢", "#0ea5e9"
        )

        for k in (self.kpi_total, self.kpi_tested, self.kpi_rate,
                  self.kpi_untested, self.kpi_installed):
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
            "🔍 Search Valve Tag, Line No, Size, Rating, "
            "Body Material, Manufacturer..."
        )
        self.txt_search.textChanged.connect(self._apply_filters)
        filter_lay.addWidget(self.txt_search, 1)

        self.cmb_filter_type = QComboBox()
        self.cmb_filter_type.addItem("All Valve Types", None)
        for vt in VALVE_TYPES:
            self.cmb_filter_type.addItem(vt, vt)
        self.cmb_filter_type.currentIndexChanged.connect(
            self._apply_filters
        )
        filter_lay.addWidget(self.cmb_filter_type)

        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.addItem("All Statuses", None)
        for st in VALVE_STATUSES:
            self.cmb_filter_status.addItem(st, st)
        self.cmb_filter_status.currentIndexChanged.connect(
            self._apply_filters
        )
        filter_lay.addWidget(self.cmb_filter_status)

        btn_add = QPushButton("➕ Register Valve")
        btn_add.setObjectName("primaryBtn")
        btn_add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_add.clicked.connect(self._add_valve)
        filter_lay.addWidget(btn_add)

        btn_test = QPushButton("🧪 Record API 598 Test")
        btn_test.setObjectName("secondaryBtn")
        btn_test.clicked.connect(self._record_test)
        filter_lay.addWidget(btn_test)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(self._export_valves_csv)
        filter_lay.addWidget(btn_exp)

        btn_del = QPushButton("🗑️ Delete")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete_selected)
        filter_lay.addWidget(btn_del)

        layout.addWidget(filter_card)

        # Main table
        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels([
            "ID", "Valve Tag", "Line Number", "Valve Type",
            "Size", "Rating", "Body Material", "Manufacturer",
            "Shell Test (Hydro)", "Seat Test (Closure)",
            "Installed", "Current Status",
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
            "Batch Transition Selected Valves To:"
        )
        lbl_batch.setStyleSheet("font-weight: bold; color: #334155;")
        status_row.addWidget(lbl_batch)

        self.st_combo = QComboBox()
        self.st_combo.addItems(VALVE_STATUSES)
        status_row.addWidget(self.st_combo)

        btn_apply = QPushButton("Apply Milestone")
        btn_apply.setObjectName("secondaryBtn")
        btn_apply.clicked.connect(self._on_apply_batch_status)
        status_row.addWidget(btn_apply)

        btn_release = QPushButton("🚚 Release for Erection")
        btn_release.setObjectName("secondaryBtn")
        btn_release.clicked.connect(
            lambda: self._quick_batch_status(
                "Released for Erection"
            )
        )
        status_row.addWidget(btn_release)

        btn_install = QPushButton("🟢 Mark Installed on Line")
        btn_install.setObjectName("secondaryBtn")
        btn_install.clicked.connect(self._mark_installed)
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
                for p in (
                    s.query(Project).order_by(Project.project_code)
                ):
                    self.proj_combo.addItem(
                        f"{p.project_code} – {p.title}", p.id
                    )
        except Exception:
            logger.exception(
                "Failed to load projects in ValvesTab"
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
        self._cached_valves = []

        if not self.project_id:
            self._update_kpis(0, 0, 0, 0)
            return

        session = self._get_session()
        try:
            from services.valve_service import ValveService
            svc = ValveService(session)
            report = svc.get_test_status_report(self.project_id)
            valves = svc.repo.get_all(self.project_id)

            tested_cnt = report.get("tested", 0)
            untested_cnt = report.get("untested", 0)
            installed_cnt = report.get("installed", 0)

            for v in valves:
                st = (
                    getattr(v, "status", "Received at Yard")
                    or "Received at Yard"
                )
                self._cached_valves.append({
                    "id": v.id,
                    "project_id": v.project_id,
                    "valve_tag": v.valve_tag,
                    "line_number": v.line_number or "",
                    "valve_type": v.valve_type or "",
                    "size_nps": v.size_nps or "",
                    "rating_class": v.rating_class or "",
                    "end_connection": (
                        getattr(v, "end_connection", "") or ""
                    ),
                    "body_material": v.body_material or "",
                    "trim_material": (
                        getattr(v, "trim_material", "") or ""
                    ),
                    "manufacturer": v.manufacturer or "",
                    "serial_number": (
                        getattr(v, "serial_number", "") or ""
                    ),
                    "hydro_shell_test": bool(v.hydro_shell_test),
                    "hydro_shell_pressure_bar": getattr(
                        v, "hydro_shell_pressure_bar", None
                    ),
                    "hydro_seat_test": bool(v.hydro_seat_test),
                    "hydro_seat_pressure_bar": getattr(
                        v, "hydro_seat_pressure_bar", None
                    ),
                    "certificate_no": (
                        getattr(v, "certificate_no", "") or ""
                    ),
                    "test_witness": (
                        getattr(v, "test_witness", "") or ""
                    ),
                    "installed_date": v.installed_date,
                    "status": st,
                    "remarks": (
                        getattr(v, "remarks", "") or ""
                    ),
                })

            self._update_kpis(
                len(valves), tested_cnt,
                untested_cnt, installed_cnt,
            )
            self._apply_filters()
            session.commit()
        except Exception as e:
            session.rollback()
            logger.exception("Valves refresh failed")
            QMessageBox.warning(
                self, "Error", f"Failed to load valves:\n{e}"
            )
        finally:
            session.close()

    def _update_kpis(self, total: int, tested: int,
                     untested: int, installed: int):
        self.kpi_total.set_value(str(total))
        self.kpi_tested.set_value(
            str(tested),
            highlight=(
                "green" if tested == total and total > 0 else None
            ),
        )
        rate = (tested / total * 100) if total > 0 else 0.0
        self.kpi_rate.set_value(
            f"{rate:.1f}%",
            highlight="green" if rate >= 90.0 else None,
        )
        self.kpi_untested.set_value(
            str(untested),
            highlight="amber" if untested > 0 else "green",
        )
        self.kpi_installed.set_value(
            str(installed), highlight="blue" if installed > 0 else None
        )

    def _apply_filters(self):
        query = self.txt_search.text().strip().lower()
        type_f = self.cmb_filter_type.currentData()
        status_f = self.cmb_filter_status.currentData()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for v in self._cached_valves:
            if type_f and v["valve_type"] != type_f:
                continue
            if status_f and v["status"] != status_f:
                continue
            if query:
                combined = (
                    f"{v['valve_tag']} {v['line_number']} "
                    f"{v['size_nps']} {v['rating_class']} "
                    f"{v['body_material']} {v['manufacturer']} "
                    f"{v['serial_number']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.table.rowCount()
            self.table.insertRow(r)

            self.table.setItem(
                r, 0, QTableWidgetItem(str(v["id"]))
            )
            self.table.setItem(
                r, 1, QTableWidgetItem(v["valve_tag"])
            )
            self.table.setItem(
                r, 2, QTableWidgetItem(v["line_number"])
            )
            self.table.setItem(
                r, 3, QTableWidgetItem(v["valve_type"])
            )
            self.table.setItem(
                r, 4, QTableWidgetItem(v["size_nps"])
            )
            self.table.setItem(
                r, 5, QTableWidgetItem(v["rating_class"])
            )
            self.table.setItem(
                r, 6, QTableWidgetItem(v["body_material"])
            )
            self.table.setItem(
                r, 7, QTableWidgetItem(v["manufacturer"])
            )

            # Shell test
            shell_item = QTableWidgetItem(
                "Passed" if v["hydro_shell_test"] else "Pending"
            )
            badge_shell = TEST_RESULT_BADGES.get(
                "Passed" if v["hydro_shell_test"] else "Pending",
                DEFAULT_BADGE,
            )
            shell_item.setText(
                f"{badge_shell['icon']} "
                f"{'Passed' if v['hydro_shell_test'] else 'Pending'}"
            )
            self._apply_badge_style(shell_item, badge_shell)
            self.table.setItem(r, 8, shell_item)

            # Seat test
            seat_item = QTableWidgetItem(
                "Passed" if v["hydro_seat_test"] else "Pending"
            )
            badge_seat = TEST_RESULT_BADGES.get(
                "Passed" if v["hydro_seat_test"] else "Pending",
                DEFAULT_BADGE,
            )
            seat_item.setText(
                f"{badge_seat['icon']} "
                f"{'Passed' if v['hydro_seat_test'] else 'Pending'}"
            )
            self._apply_badge_style(seat_item, badge_seat)
            self.table.setItem(r, 9, seat_item)

            # Installed
            inst_item = QTableWidgetItem(
                "✅ Yes" if v["installed_date"] else "❌ No"
            )
            inst_item.setForeground(QBrush(QColor(
                "#166534" if v["installed_date"] else "#991b1b"
            )))
            f_b = inst_item.font()
            f_b.setBold(True)
            inst_item.setFont(f_b)
            self.table.setItem(r, 10, inst_item)

            # Status
            st_item = QTableWidgetItem(v["status"])
            badge = VALVE_STATUS_BADGES.get(
                v["status"], DEFAULT_BADGE
            )
            st_item.setText(f"{badge['icon']} {v['status']}")
            self._apply_badge_style(st_item, badge)
            self.table.setItem(r, 11, st_item)

        self.table.setSortingEnabled(True)

    def _apply_badge_style(self, item: QTableWidgetItem,
                            badge: dict):
        item.setBackground(QBrush(QColor(badge["bg"])))
        item.setForeground(QBrush(QColor(badge["fg"])))
        f = item.font()
        f.setBold(True)
        item.setFont(f)

    # ══════════════════════════════════════════
    #  LOOKUP HELPER
    # ══════════════════════════════════════════
    def _get_projects_lookup(self):
        with self.db.session_scope() as s:
            projects = (
                s.query(Project).order_by(Project.project_code).all()
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
    def _add_valve(self):
        proj_list = self._get_projects_lookup()
        if not proj_list:
            QMessageBox.information(
                self, "Info",
                "Register a Project first in Project Setup."
            )
            return

        dlg = ValveDialog(self, projects=proj_list)
        if self.project_id:
            for i in range(dlg.project_combo.count()):
                if dlg.project_combo.itemData(i) == self.project_id:
                    dlg.project_combo.setCurrentIndex(i)
                    break

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        session = self._get_session()
        try:
            from services.valve_service import ValveService
            svc = ValveService(session)
            svc.register_valve(data["project_id"], **data)
            session.commit()
            self.refresh()
            QMessageBox.information(
                self, "Success",
                f"Valve '{data['valve_tag']}' registered."
            )
        except Exception as e:
            session.rollback()
            logger.exception("Failed to register valve")
            QMessageBox.critical(
                self, "Error",
                f"Failed to register valve (Duplicate Tag?):\n{e}"
            )
        finally:
            session.close()

    def _edit_selected_valve(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection", "Select a valve to edit."
            )
            return

        valve_id = int(self.table.item(rows[0].row(), 0).text())
        valve_data = next(
            (v for v in self._cached_valves
             if v["id"] == valve_id), None
        )
        if not valve_data:
            return

        proj_list = self._get_projects_lookup()
        dlg = ValveDialog(
            self, projects=proj_list, existing_data=valve_data
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        session = self._get_session()
        try:
            # ✅ FIXED: SQLAlchemy 2.0 — s.get(Model, pk)
            v = session.get(Valve, valve_id)
            if v:
                v.valve_type = data["valve_type"]
                v.line_number = data["line_number"]
                v.size_nps = data["size_nps"]
                v.rating_class = data["rating_class"]
                v.body_material = data["body_material"]
                v.manufacturer = data["manufacturer"]
                v.status = data["status"]
                if hasattr(v, "end_connection"):
                    v.end_connection = data["end_connection"]
                if hasattr(v, "trim_material"):
                    v.trim_material = data["trim_material"]
                if hasattr(v, "serial_number"):
                    v.serial_number = data["serial_number"]
                if hasattr(v, "remarks"):
                    v.remarks = data["remarks"]
            session.commit()
            self.refresh()
            QMessageBox.information(
                self, "Updated",
                f"Valve '{valve_data['valve_tag']}' "
                f"specifications updated."
            )
        except Exception as e:
            session.rollback()
            logger.exception("Failed to edit valve")
            QMessageBox.critical(
                self, "Error", f"Update failed:\n{e}"
            )
        finally:
            session.close()

    def _delete_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select one or more valves to delete."
            )
            return

        valve_ids = [
            int(self.table.item(r.row(), 0).text()) for r in rows
        ]
        valve_tags = [
            self.table.item(r.row(), 1).text() for r in rows
        ]

        if QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(valve_ids)} valve(s)?\n\n"
            f"Valves: {', '.join(valve_tags[:5])}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        session = self._get_session()
        try:
            for vid in valve_ids:
                # ✅ FIXED: SQLAlchemy 2.0
                v = session.get(Valve, vid)
                if v:
                    session.delete(v)
            session.commit()
            self.refresh()
            QMessageBox.information(
                self, "Deleted",
                "Selected valve(s) removed from database."
            )
        except Exception as e:
            session.rollback()
            logger.exception("Failed to delete valves")
            QMessageBox.critical(
                self, "Error", f"Could not delete valves:\n{e}"
            )
        finally:
            session.close()

    # ══════════════════════════════════════════
    #  TEST RECORDING
    # ══════════════════════════════════════════
    def _record_test(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select a valve from the table to record "
                "pressure testing."
            )
            return

        valve_id = int(self.table.item(rows[0].row(), 0).text())
        valve_data = next(
            (v for v in self._cached_valves
             if v["id"] == valve_id), None
        )
        if not valve_data:
            return

        dlg = ValveTestExecutionDialog(
            self, valve_data=valve_data
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        test_data = dlg.get_test_data()
        session = self._get_session()
        try:
            from services.valve_service import ValveService
            svc = ValveService(session)
            if test_data.get("hydro_shell_test"):
                svc.record_shell_test(
                    valve_id,
                    test_data["hydro_shell_pressure_bar"],
                    test_data.get("test_witness", ""),
                )
            if test_data.get("hydro_seat_test"):
                svc.record_seat_test(
                    valve_id,
                    test_data["hydro_seat_pressure_bar"],
                )

            # ✅ FIXED: SQLAlchemy 2.0 — session.get(Model, pk)
            v = session.get(Valve, valve_id)
            if v:
                v.status = "Workshop Tested (Passed)"
                if hasattr(v, "certificate_no"):
                    v.certificate_no = test_data["certificate_no"]
                if hasattr(v, "test_witness"):
                    v.test_witness = test_data["test_witness"]

            session.commit()
            self.refresh()
            QMessageBox.information(
                self, "Test Recorded",
                f"API 598 Test Certificate "
                f"'{test_data['certificate_no']}' logged for "
                f"Valve {valve_data['valve_tag']}."
            )
        except Exception as e:
            session.rollback()
            logger.exception("Failed to record valve test")
            QMessageBox.critical(
                self, "Error", f"Failed to record test:\n{e}"
            )
        finally:
            session.close()

    # ══════════════════════════════════════════
    #  INSTALLATION
    # ══════════════════════════════════════════
    def _mark_installed(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select one or more valves to mark as installed."
            )
            return

        valve_ids = [
            int(self.table.item(r.row(), 0).text()) for r in rows
        ]
        u_name = getattr(
            self.session_manager, "username", "admin"
        )

        if QMessageBox.question(
            self, "Confirm Installation",
            f"Mark {len(valve_ids)} valve(s) as installed on "
            f"line by inspector '{u_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        session = self._get_session()
        try:
            from services.valve_service import ValveService
            svc = ValveService(session)
            for vid in valve_ids:
                svc.mark_installed(vid, u_name)
            session.commit()
            self.refresh()
            QMessageBox.information(
                self, "Installed",
                f"Selected {len(valve_ids)} valve(s) registered "
                f"as Installed."
            )
        except Exception as e:
            session.rollback()
            logger.exception("Failed to mark valve installed")
            QMessageBox.critical(
                self, "Error", f"Could not mark installed:\n{e}"
            )
        finally:
            session.close()

    # ══════════════════════════════════════════
    #  BATCH STATUS
    # ══════════════════════════════════════════
    def _on_apply_batch_status(self):
        new_st = self.st_combo.currentText()
        self._quick_batch_status(new_st)

    def _quick_batch_status(self, new_status: str):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select at least one valve from the table."
            )
            return

        valve_ids = [
            int(self.table.item(r.row(), 0).text()) for r in rows
        ]
        session = self._get_session()
        try:
            for vid in valve_ids:
                # ✅ FIXED: SQLAlchemy 2.0
                v = session.get(Valve, vid)
                if v:
                    v.status = new_status
                    if (new_status == "Installed on Line"
                            and not v.installed_date):
                        v.installed_date = datetime.date.today()
            session.commit()
            self.refresh()
            QMessageBox.information(
                self, "Status Applied",
                f"Updated milestone to '{new_status}' for "
                f"{len(valve_ids)} valve(s)."
            )
        except Exception as e:
            session.rollback()
            QMessageBox.critical(
                self, "Error", f"Failed to apply status:\n{e}"
            )
        finally:
            session.close()

    # ══════════════════════════════════════════
    #  DETAIL VIEW / CONTEXT MENU
    # ══════════════════════════════════════════
    def _on_row_double_click(self, index):
        row = index.row()
        valve_id = int(self.table.item(row, 0).text())
        valve_data = next(
            (v for v in self._cached_valves
             if v["id"] == valve_id), None
        )
        if valve_data:
            dlg = ValveDetailDialog(self, valve_data)
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

        act_dossier = QAction(
            "🔍 View Full Valve Dossier", self
        )
        act_dossier.triggered.connect(
            lambda: self._on_row_double_click(
                self.table.currentIndex()
            )
        )
        menu.addAction(act_dossier)

        act_test = QAction(
            "🧪 Record API 598 Pressure Test", self
        )
        act_test.triggered.connect(self._record_test)
        menu.addAction(act_test)

        act_install = QAction(
            "🟢 Mark as Installed on Line", self
        )
        act_install.triggered.connect(self._mark_installed)
        menu.addAction(act_install)

        menu.addSeparator()

        act_edit = QAction("✏️ Edit Specifications", self)
        act_edit.triggered.connect(self._edit_selected_valve)
        menu.addAction(act_edit)

        act_copy = QAction("📋 Copy Valve Tag", self)
        act_copy.triggered.connect(
            lambda: QApplication.clipboard().setText(
                self.table.item(rows[0].row(), 1).text()
            )
        )
        menu.addAction(act_copy)

        act_del = QAction("🗑️ Delete Valve(s)", self)
        act_del.triggered.connect(self._delete_selected)
        menu.addAction(act_del)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ══════════════════════════════════════════
    #  EXPORT
    # ══════════════════════════════════════════
    def _export_valves_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(
                self, "Export",
                "No valves available to export."
            )
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_code = self.proj_combo.currentText().split("–")[0].strip()
        default_name = (
            f"Valves_Testing_Register_{proj_code}_{timestamp}.csv"
        )

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Valve Testing Register",
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
                f"Valve register exported successfully to:\n"
                f"{filename}"
            )
        except Exception as e:
            logger.exception("Failed to export valves CSV")
            QMessageBox.critical(
                self, "Export Error",
                f"Could not create CSV file:\n{e}"
            )