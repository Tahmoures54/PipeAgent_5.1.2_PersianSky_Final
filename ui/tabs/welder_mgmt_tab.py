# -*- coding: utf-8 -*-
# ui/tabs/welder_mgmt_tab.py – PipeAgent 5.3.0
# Welder Performance Qualification (WPQ / WQT), Continuity Tracking
# & Certification Management
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
    QDoubleSpinBox, QDateEdit, QCheckBox,
)
from PyQt6.QtGui import QColor, QFont, QBrush, QCursor, QAction

from db.manager import DatabaseManager
from db.models import Project, User, Weld, Welder
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
WELDING_PROCESSES = [
    "GTAW (TIG)", "SMAW (Stick)", "GTAW + SMAW",
    "FCAW (Flux Cored)",
    "GMAW (MIG/MAG)", "SAW (Submerged Arc)",
    "PAW (Plasma Arc)",
]

QUALIFIED_POSITIONS = [
    "1G (Flat)", "2G (Horizontal)", "3G (Vertical Up)",
    "4G (Overhead)",
    "5G (Multiple Fixed)",
    "6G (Inclined 45° All Position)",
    "6GR (With Restriction Ring)",
    "1F / 2F / 3F / 4F (Fillet)",
    "All Positions (1G to 6G)",
]

P_NUMBERS = [
    "P-No 1 (Carbon Steels)",
    "P-No 3 (Low Alloy Cr-Mo)",
    "P-No 4 (1.25Cr-0.5Mo)",
    "P-No 5A/5B (2.25Cr-1Mo / 5Cr)",
    "P-No 8 (Austenitic Stainless SS304/316)",
    "P-No 9A/9B (Nickel Steels)",
    "P-No 10H (Duplex / Super Duplex SS)",
    "P-No 41-49 (Nickel Alloys)",
    "P-No 51-53 (Titanium Alloys)",
]


# ─────────────────────────────────────────────
#  BADGES
# ─────────────────────────────────────────────
QUALIFICATION_BADGES = {
    "Active / Valid":       {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Expiring (≤30 Days)":  {"bg": "#fef3c7", "fg": "#92400e", "icon": "⚠️"},
    "Expired":              {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Deactivated":          {"bg": "#f1f5f9", "fg": "#475569", "icon": "⏸️"},
}
DEFAULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}


# ─────────────────────────────────────────────
#  STYLESHEET
# ─────────────────────────────────────────────
WELDER_MGMT_STYLESHEET = """
    QWidget#welderMgmtTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #102a43, stop:1 #1e3c72);
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
    QLineEdit, QComboBox, QTextEdit, QDoubleSpinBox, QDateEdit {
        padding: 6px 10px; border: 1px solid #cbd5e1;
        border-radius: 6px; font-size: 12px;
    }
"""


# ─────────────────────────────────────────────
#  KPI CARD
# ─────────────────────────────────────────────
class WelderKPICard(QFrame):
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
#  WELDER DIALOG
# ─────────────────────────────────────────────
class WelderDialog(QDialog):
    def __init__(self, parent=None, projects: list = None,
                 existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = existing_data is not None
        self.setWindowTitle(
            "Edit Welder Performance Qualification"
            if self.is_edit
            else "Register Welder Qualification (WPQ)"
        )
        self.setMinimumWidth(540)
        self.setStyleSheet(WELDER_MGMT_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.project_combo = QComboBox()
        if projects:
            for p in projects:
                self.project_combo.addItem(
                    f"{p.project_code} – {p.title}", p.id
                )

        self.stencil_edit = QLineEdit()
        self.stencil_edit.setPlaceholderText(
            "Welder Stamp / Stencil No * (e.g. W-04 or ST-12)"
        )

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Welder Full Legal Name *")

        self.national_id = QLineEdit()
        self.national_id.setPlaceholderText(
            "National ID / Passport / Badge Number"
        )

        self.process_combo = QComboBox()
        self.process_combo.addItems(WELDING_PROCESSES)
        self.process_combo.setEditable(True)

        self.position_combo = QComboBox()
        self.position_combo.addItems(QUALIFIED_POSITIONS)
        self.position_combo.setEditable(True)

        # Thickness limits
        thk_lay = QHBoxLayout()
        self.thk_min = QDoubleSpinBox()
        self.thk_min.setRange(0, 500)
        self.thk_min.setValue(1.6)
        self.thk_min.setSuffix(" mm")

        self.thk_max = QDoubleSpinBox()
        self.thk_max.setRange(0, 1000)
        self.thk_max.setValue(25.4)
        self.thk_max.setSuffix(" mm (Max)")

        thk_lay.addWidget(QLabel("Min:"))
        thk_lay.addWidget(self.thk_min)
        thk_lay.addWidget(QLabel("Max:"))
        thk_lay.addWidget(self.thk_max)

        self.pno_combo = QComboBox()
        self.pno_combo.addItems(P_NUMBERS)
        self.pno_combo.setEditable(True)

        self.diameter_edit = QLineEdit()
        self.diameter_edit.setPlaceholderText(
            'Qualified Pipe OD Range '
            '(e.g. ≥ 2" NPS / 60.3mm OD)'
        )

        self.fno_edit = QLineEdit()
        self.fno_edit.setPlaceholderText(
            "Filler Metal F-No (e.g. F-No 6 / F-No 4 with Backing)"
        )

        self.wpqr_ref = QLineEdit()
        self.wpqr_ref.setPlaceholderText(
            "Supporting WPQR / Test Certificate No"
        )

        self.test_date = QDateEdit(QDate.currentDate())
        self.test_date.setCalendarPopup(True)

        self.expiry_date = QDateEdit(
            QDate.currentDate().addMonths(6)
        )
        self.expiry_date.setCalendarPopup(True)

        self.is_active = QCheckBox(
            "Welder Currently Active & Authorized for Production"
        )
        self.is_active.setChecked(True)

        form.addRow("Target Project *:", self.project_combo)
        form.addRow("Welder Stencil / Stamp *:", self.stencil_edit)
        form.addRow("Full Name *:", self.name_edit)
        form.addRow("Badge / National ID:", self.national_id)
        form.addRow("Qualified Process *:", self.process_combo)
        form.addRow("Qualified Positions *:", self.position_combo)
        form.addRow("Qualified Thickness:", thk_lay)
        form.addRow("Base Metal Group:", self.pno_combo)
        form.addRow("Diameter Range:", self.diameter_edit)
        form.addRow("Filler F-No / A-No:", self.fno_edit)
        form.addRow("WPQR Document Ref:", self.wpqr_ref)
        form.addRow("Initial Test Date:", self.test_date)
        form.addRow("Continuity Expiry Date *:", self.expiry_date)
        form.addRow("Authorization Status:", self.is_active)
        layout.addLayout(form)

        if self.is_edit and existing_data:
            pid = existing_data.get("project_id")
            for i in range(self.project_combo.count()):
                if self.project_combo.itemData(i) == pid:
                    self.project_combo.setCurrentIndex(i)
                    break
            self.stencil_edit.setText(
                existing_data.get("stencil_no", "")
            )
            self.stencil_edit.setReadOnly(True)
            self.name_edit.setText(
                existing_data.get("full_name", "")
            )
            self.national_id.setText(
                existing_data.get("national_id", "")
            )
            self.process_combo.setCurrentText(
                existing_data.get(
                    "welding_processes", WELDING_PROCESSES[0]
                )
            )
            self.position_combo.setCurrentText(
                existing_data.get(
                    "qualified_positions", QUALIFIED_POSITIONS[0]
                )
            )
            self.thk_min.setValue(
                float(
                    existing_data.get(
                        "qualified_thickness_min_mm"
                    ) or 1.6
                )
            )
            self.thk_max.setValue(
                float(
                    existing_data.get(
                        "qualified_thickness_max_mm"
                    ) or 25.4
                )
            )
            self.pno_combo.setCurrentText(
                existing_data.get(
                    "qualified_material_p_no", P_NUMBERS[0]
                )
            )
            self.diameter_edit.setText(
                existing_data.get("qualified_diameter", "")
            )
            self.fno_edit.setText(
                existing_data.get("filler_f_no", "")
            )
            self.wpqr_ref.setText(
                existing_data.get("wpqr_no", "")
            )

            exp_d = existing_data.get("expiry_date")
            if isinstance(exp_d, datetime.date):
                self.expiry_date.setDate(
                    QDate(exp_d.year, exp_d.month, exp_d.day)
                )

            self.is_active.setChecked(
                bool(existing_data.get("is_active", True))
            )

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Welder Qualification")
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
        if not self.stencil_edit.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Welder Stencil / Stamp No is mandatory."
            )
            self.stencil_edit.setFocus()
            return
        if not self.name_edit.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Welder Full Name is required."
            )
            self.name_edit.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        t_qd = self.test_date.date()
        e_qd = self.expiry_date.date()
        return {
            "project_id": self.project_combo.currentData(),
            "stencil_no": self.stencil_edit.text().strip(),
            "full_name": self.name_edit.text().strip(),
            "national_id": self.national_id.text().strip(),
            "welding_processes": (
                self.process_combo.currentText().strip()
            ),
            "qualified_positions": (
                self.position_combo.currentText().strip()
            ),
            "qualified_thickness_min_mm": self.thk_min.value(),
            "qualified_thickness_max_mm": self.thk_max.value(),
            "qualified_material_p_no": (
                self.pno_combo.currentText().strip()
            ),
            "qualified_diameter": (
                self.diameter_edit.text().strip()
            ),
            "filler_f_no": self.fno_edit.text().strip(),
            "wpqr_no": self.wpqr_ref.text().strip(),
            "test_date": datetime.date(
                t_qd.year(), t_qd.month(), t_qd.day()
            ),
            "expiry_date": datetime.date(
                e_qd.year(), e_qd.month(), e_qd.day()
            ),
            "is_active": self.is_active.isChecked(),
        }


# ─────────────────────────────────────────────
#  WELDER CONTINUITY DIALOG  (ASME IX QW-322)
# ─────────────────────────────────────────────
class WelderContinuityDialog(QDialog):
    """6-month continuity renewal per ASME IX QW-322."""

    def __init__(self, parent=None, welder_data: dict = None):
        super().__init__(parent)
        self.welder_data = welder_data or {}
        self.setWindowTitle(
            f"🔄 Welder Continuity Extension – "
            f"Stamp: {welder_data.get('stencil_no')}"
        )
        self.setMinimumWidth(480)
        self.setStyleSheet(WELDER_MGMT_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        info_banner = QLabel(
            f"<b>Welder:</b> {welder_data.get('full_name')} &middot; "
            f"<b>Stamp:</b> {welder_data.get('stencil_no')}<br>"
            f"<b>Process:</b> {welder_data.get('welding_processes')} "
            f"&middot; <b>Current Expiry:</b> "
            f"{welder_data.get('expiry_date')}"
        )
        info_banner.setStyleSheet(
            "background: #f1f5f9; padding: 8px; border-radius: 6px; "
            "font-size: 12px;"
        )
        layout.addWidget(info_banner)

        self.weld_ref = QLineEdit()
        self.weld_ref.setPlaceholderText(
            "Production Joint ID welded within last 6 months "
            "(e.g. W-104)"
        )

        self.ndt_ref = QLineEdit()
        self.ndt_ref.setPlaceholderText(
            "NDT (RT/UT) Inspection Report No with "
            "Acceptable result"
        )

        self.extension_months = QComboBox()
        self.extension_months.addItems([
            "6 Months (Standard ASME IX)",
            "12 Months (ISO 9606 Revalidation)",
        ])

        self.verifier_edit = QLineEdit(
            "Welding Inspector / QAQC Manager"
        )

        self.remarks = QTextEdit()
        self.remarks.setPlaceholderText(
            "Verification notes, radiographic examination result..."
        )
        self.remarks.setMaximumHeight(65)

        form.addRow("Verification Joint ID *:", self.weld_ref)
        form.addRow("NDT Examination Report *:", self.ndt_ref)
        form.addRow("Extension Period:", self.extension_months)
        form.addRow("Certified Verifier:", self.verifier_edit)
        form.addRow("Continuity Notes:", self.remarks)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_renew = QPushButton("✔️ Grant Continuity Renewal")
        btn_renew.setObjectName("primaryBtn")
        btn_renew.clicked.connect(self._validate_and_accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_renew)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _validate_and_accept(self):
        if not self.weld_ref.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Verification production joint ID is mandatory."
            )
            return
        if not self.ndt_ref.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "NDT acceptance report reference is required."
            )
            return
        self.accept()

    def get_extension_months(self) -> int:
        return (
            6 if "6 Months" in self.extension_months.currentText()
            else 12
        )


# ─────────────────────────────────────────────
#  WELDER DOSSIER DIALOG
# ─────────────────────────────────────────────
class WelderDossierDialog(QDialog):
    def __init__(self, parent=None, welder: dict = None,
                 production_stats: dict = None):
        super().__init__(parent)
        self.setWindowTitle(
            f"🔍 Welder Technical Dossier – "
            f"Stamp: {welder.get('stencil_no', 'Welder')}"
        )
        self.setMinimumSize(600, 480)
        self.setStyleSheet(WELDER_MGMT_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hdr = QLabel(
            f"📋 Welder Performance Dossier: "
            f"{welder.get('full_name')} "
            f"[{welder.get('stencil_no')}]"
        )
        hdr.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #102a43;"
        )
        layout.addWidget(hdr)

        info_box = QGroupBox(
            "ASME IX / AWS Qualified Essential Variables"
        )
        info_grid = QGridLayout(info_box)
        info_grid.setSpacing(8)

        details = [
            ("Stencil / Stamp No:",
             welder.get("stencil_no", "—")),
            ("Full Legal Name:", welder.get("full_name", "—")),
            ("Badge / National ID:",
             welder.get("national_id", "—")),
            ("Welding Processes:",
             welder.get("welding_processes", "—")),
            ("Qualified Positions:",
             welder.get("qualified_positions", "—")),
            ("Thickness Limits:",
             f"{welder.get('qualified_thickness_min_mm') or 1.6}"
             f" to "
             f"{welder.get('qualified_thickness_max_mm') or 25.4} mm"),
            ("Diameter Range:",
             welder.get("qualified_diameter")
             or "All Standard Diameters"),
            ("Material P-Numbers:",
             welder.get("qualified_material_p_no", "P-No 1")),
            ("Filler F-Numbers:",
             welder.get("filler_f_no", "F-No 6")),
            ("WPQR Certificate:",
             welder.get("wpqr_no", "—")),
            ("Continuity Expiry:",
             str(welder.get("expiry_date", "—"))),
            ("Current Status:",
             "Active & Authorized"
             if welder.get("is_active")
             else "Suspended / Inactive"),
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

        prod_box = QGroupBox(
            "Project Welding Production & Quality Performance"
        )
        prod_grid = QGridLayout(prod_box)
        prod_grid.setSpacing(8)

        production_stats = production_stats or {}
        tot_w = production_stats.get("total_welds", 0)
        acc_w = production_stats.get("accepted_welds", 0)
        rep_w = production_stats.get("repaired_welds", 0)
        rate = (acc_w / tot_w * 100) if tot_w > 0 else 100.0

        p_stats = [
            ("Total Joints Welded:", str(tot_w)),
            ("Accepted Joints (Pass):", str(acc_w)),
            ("NDT Cut-outs (Repairs):", str(rep_w)),
            ("Quality Acceptance Rate:", f"{rate:.1f}%"),
        ]

        for i, (label, val) in enumerate(p_stats):
            lbl_w = QLabel(f"<b>{label}</b>")
            lbl_w.setStyleSheet("color: #475569;")
            val_w = QLabel(str(val))
            val_w.setStyleSheet(
                "color: #166534; font-weight: bold;"
                if "%" in val
                else "color: #0f172a; font-weight: 600;"
            )
            r, c = divmod(i, 2)
            prod_grid.addWidget(lbl_w, r, c * 2)
            prod_grid.addWidget(val_w, r, c * 2 + 1)

        layout.addWidget(prod_box)

        btn_close = QPushButton("Close Dossier")
        btn_close.setObjectName("secondaryBtn")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class WelderMgmtTab(QWidget):
    def __init__(self, db: DatabaseManager,
                 session_manager: SessionManager):
        super().__init__()
        self.setObjectName("welderMgmtTab")
        self.db = db
        self.session_manager = session_manager
        self.project_id: Optional[int] = None
        self._cached_welders: list[dict] = []

        self._build_ui()
        self.setStyleSheet(WELDER_MGMT_STYLESHEET)
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
        t = QLabel(
            "👨‍🏭 Welder Performance Qualification & "
            "Continuity Management"
        )
        t.setObjectName("mainTitle")
        s = QLabel(
            "ASME Section IX / AWS D1.1 WPQ Register: "
            "Qualified Ranges, P-Numbers, Positions, "
            "6-Month Continuity & Expiration Auditing."
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

        self.kpi_total = WelderKPICard(
            "Total Registered", "👨‍🏭", "#3b82f6"
        )
        self.kpi_active = WelderKPICard(
            "Active & Certified", "✅", "#10b981"
        )
        self.kpi_expiring = WelderKPICard(
            "Expiring (≤30 Days)", "⚠️", "#f59e0b"
        )
        self.kpi_expired = WelderKPICard(
            "Expired / Suspended", "❌", "#ef4444"
        )
        self.kpi_processes = WelderKPICard(
            "Covered Processes", "🔥", "#8b5cf6"
        )

        for k in (self.kpi_total, self.kpi_active, self.kpi_expiring,
                  self.kpi_expired, self.kpi_processes):
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
            "🔍 Search Stencil No, Full Name, P-No, "
            "Positions, WPQR..."
        )
        self.txt_search.textChanged.connect(self._apply_filters)
        filter_lay.addWidget(self.txt_search, 1)

        self.cmb_filter_proc = QComboBox()
        self.cmb_filter_proc.addItem("All Welding Processes", None)
        for pr in WELDING_PROCESSES:
            self.cmb_filter_proc.addItem(pr, pr)
        self.cmb_filter_proc.currentIndexChanged.connect(
            self._apply_filters
        )
        filter_lay.addWidget(self.cmb_filter_proc)

        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.addItem(
            "All Qualification Statuses", None
        )
        self.cmb_filter_status.addItems([
            "Active / Valid", "Expiring (≤30 Days)",
            "Expired", "Deactivated",
        ])
        self.cmb_filter_status.currentIndexChanged.connect(
            self._apply_filters
        )
        filter_lay.addWidget(self.cmb_filter_status)

        btn_add = QPushButton("➕ Register Welder")
        btn_add.setObjectName("primaryBtn")
        btn_add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_add.clicked.connect(self._add_welder)
        filter_lay.addWidget(btn_add)

        btn_prolong = QPushButton("🔄 Renew Continuity")
        btn_prolong.setObjectName("secondaryBtn")
        btn_prolong.clicked.connect(self._renew_continuity)
        filter_lay.addWidget(btn_prolong)

        btn_exp = QPushButton("📥 Export WPQ Matrix")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(self._export_welders_csv)
        filter_lay.addWidget(btn_exp)

        btn_del = QPushButton("🗑️ Delete")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete_selected)
        filter_lay.addWidget(btn_del)

        layout.addWidget(filter_card)

        # Main table
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "ID", "Stencil / Stamp", "Welder Full Name",
            "Processes", "Qualified Positions",
            "Thickness Limits (mm)", "Base Metal P-No",
            "Continuity Expiry", "Status", "Authorization",
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
                "Failed to load projects in WelderMgmtTab"
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
        self._cached_welders = []

        if not self.project_id:
            self._update_kpis(0, 0, 0, 0, 0)
            return

        today = datetime.date.today()
        active_cnt = expiring_cnt = expired_cnt = 0
        unique_procs = set()

        try:
            from services.welder_qualification_service import (
                WelderQualificationService,
            )
            with self.db.session_scope() as session:
                svc = WelderQualificationService(session)

                # Prefer get_all() for admin view; fallback to
                # get_active() if not available.
                if hasattr(svc.repo, "get_all"):
                    welders = svc.repo.get_all(self.project_id)
                else:
                    welders = svc.repo.get_active(self.project_id)

                for w in welders:
                    is_act = bool(w.is_active)
                    exp_date = getattr(w, "expiry_date", None)

                    if not is_act:
                        status_str = "Deactivated"
                    elif exp_date and exp_date < today:
                        status_str = "Expired"
                        expired_cnt += 1
                    elif (exp_date
                            and (exp_date - today).days <= 30):
                        status_str = "Expiring (≤30 Days)"
                        expiring_cnt += 1
                        active_cnt += 1
                    else:
                        status_str = "Active / Valid"
                        active_cnt += 1

                    proc_str = w.welding_processes or "SMAW"
                    unique_procs.add(proc_str)

                    self._cached_welders.append({
                        "id": w.id,
                        "project_id": getattr(
                            w, "project_id", self.project_id
                        ),
                        "stencil_no": w.stencil_no,
                        "full_name": w.full_name,
                        "national_id": (
                            getattr(w, "national_id", "") or ""
                        ),
                        "welding_processes": proc_str,
                        "qualified_positions": (
                            w.qualified_positions or "6G"
                        ),
                        "qualified_thickness_min_mm": getattr(
                            w, "qualified_thickness_min_mm", 1.6
                        ),
                        "qualified_thickness_max_mm": getattr(
                            w, "qualified_thickness_max_mm", 25.4
                        ),
                        "qualified_material_p_no": (
                            w.qualified_material_p_no or "P-No 1"
                        ),
                        "qualified_diameter": (
                            getattr(w, "qualified_diameter", "")
                            or ""
                        ),
                        "filler_f_no": (
                            getattr(w, "filler_f_no", "") or ""
                        ),
                        "wpqr_no": (
                            getattr(w, "wpqr_no", "") or ""
                        ),
                        "expiry_date": exp_date,
                        "is_active": is_act,
                        "calculated_status": status_str,
                    })

                self._update_kpis(
                    len(welders), active_cnt,
                    expiring_cnt, expired_cnt,
                    len(unique_procs),
                )
                self._apply_filters()

        except Exception as exc:
            logger.exception(
                "Failed to refresh welder qualifications"
            )
            QMessageBox.warning(
                self, "Welder Management Error",
                f"Could not load welder records:\n{exc}"
            )

    def _update_kpis(self, total: int, active: int,
                     expiring: int, expired: int,
                     processes_cnt: int):
        self.kpi_total.set_value(str(total))
        self.kpi_active.set_value(
            str(active), highlight="green" if active > 0 else None
        )
        self.kpi_expiring.set_value(
            str(expiring),
            highlight="amber" if expiring > 0 else "green",
        )
        self.kpi_expired.set_value(
            str(expired),
            highlight="red" if expired > 0 else "green",
        )
        self.kpi_processes.set_value(str(processes_cnt))

    def _apply_filters(self):
        query = self.txt_search.text().strip().lower()
        proc_filter = self.cmb_filter_proc.currentData()
        status_filter = (
            self.cmb_filter_status.currentText()
            if self.cmb_filter_status.currentIndex() > 0
            else None
        )

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for w in self._cached_welders:
            if proc_filter and proc_filter not in w["welding_processes"]:
                continue
            if status_filter and w["calculated_status"] != status_filter:
                continue
            if query:
                combined = (
                    f"{w['stencil_no']} {w['full_name']} "
                    f"{w['welding_processes']} "
                    f"{w['qualified_positions']} "
                    f"{w['qualified_material_p_no']} "
                    f"{w['wpqr_no']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.table.rowCount()
            self.table.insertRow(r)

            self.table.setItem(
                r, 0, QTableWidgetItem(str(w["id"]))
            )
            self.table.setItem(
                r, 1, QTableWidgetItem(w["stencil_no"])
            )
            self.table.setItem(
                r, 2, QTableWidgetItem(w["full_name"])
            )
            self.table.setItem(
                r, 3, QTableWidgetItem(w["welding_processes"])
            )
            self.table.setItem(
                r, 4, QTableWidgetItem(w["qualified_positions"])
            )
            self.table.setItem(
                r, 5, QTableWidgetItem(
                    f"{w['qualified_thickness_min_mm'] or 1.6} - "
                    f"{w['qualified_thickness_max_mm'] or 25.4} mm"
                )
            )
            self.table.setItem(
                r, 6, QTableWidgetItem(w["qualified_material_p_no"])
            )
            self.table.setItem(
                r, 7, QTableWidgetItem(
                    str(w["expiry_date"] or "—")
                )
            )

            st_item = QTableWidgetItem(w["calculated_status"])
            badge = QUALIFICATION_BADGES.get(
                w["calculated_status"], DEFAULT_BADGE
            )
            st_item.setText(f"{badge['icon']} {w['calculated_status']}")
            st_item.setBackground(QBrush(QColor(badge["bg"])))
            st_item.setForeground(QBrush(QColor(badge["fg"])))
            f = st_item.font()
            f.setBold(True)
            st_item.setFont(f)
            self.table.setItem(r, 8, st_item)

            auth_item = QTableWidgetItem(
                "🟢 Authorized" if w["is_active"] else "🔴 Revoked"
            )
            auth_item.setForeground(QBrush(QColor(
                "#166534" if w["is_active"] else "#991b1b"
            )))
            self.table.setItem(r, 9, auth_item)

        self.table.setSortingEnabled(True)

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
    def _add_welder(self):
        if not self.project_id:
            QMessageBox.information(
                self, "Info",
                "Select a Project first in the header."
            )
            return

        proj_list = self._get_projects_lookup()
        dlg = WelderDialog(self, projects=proj_list)
        if self.project_id:
            for i in range(dlg.project_combo.count()):
                if dlg.project_combo.itemData(i) == self.project_id:
                    dlg.project_combo.setCurrentIndex(i)
                    break

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        try:
            from services.welder_qualification_service import (
                WelderQualificationService,
            )
            with self.db.session_scope() as session:
                svc = WelderQualificationService(session)
                svc.register_welder(data["project_id"], **data)

            self.refresh()
            QMessageBox.information(
                self, "Success",
                f"Welder '{data['full_name']}' "
                f"[{data['stencil_no']}] registered."
            )
        except Exception as exc:
            logger.exception("Failed to register welder")
            QMessageBox.critical(
                self, "Registration Error",
                f"Could not register welder "
                f"(Duplicate Stencil?):\n{exc}"
            )

    def _edit_selected_welder(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select a welder from the table to edit."
            )
            return

        welder_id = int(self.table.item(rows[0].row(), 0).text())
        welder_data = next(
            (w for w in self._cached_welders
             if w["id"] == welder_id), None
        )
        if not welder_data:
            return

        proj_list = self._get_projects_lookup()
        dlg = WelderDialog(
            self, projects=proj_list, existing_data=welder_data
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        try:
            with self.db.session_scope() as session:
                # ✅ FIXED: SQLAlchemy 2.0 — session.get(Model, pk)
                w = session.get(Welder, welder_id)
                if w:
                    w.full_name = data["full_name"]
                    w.welding_processes = data["welding_processes"]
                    w.qualified_positions = (
                        data["qualified_positions"]
                    )
                    w.qualified_thickness_min_mm = (
                        data["qualified_thickness_min_mm"]
                    )
                    w.qualified_thickness_max_mm = (
                        data["qualified_thickness_max_mm"]
                    )
                    w.qualified_material_p_no = (
                        data["qualified_material_p_no"]
                    )
                    w.expiry_date = data["expiry_date"]
                    w.is_active = data["is_active"]
                    if hasattr(w, "national_id"):
                        w.national_id = data["national_id"]
                    if hasattr(w, "qualified_diameter"):
                        w.qualified_diameter = (
                            data["qualified_diameter"]
                        )
                    if hasattr(w, "filler_f_no"):
                        w.filler_f_no = data["filler_f_no"]
                    if hasattr(w, "wpqr_no"):
                        w.wpqr_no = data["wpqr_no"]
                    # ✅ FIXED: use _utcnow() helper
                    if hasattr(w, "updated_at"):
                        w.updated_at = _utcnow()

            self.refresh()
            QMessageBox.information(
                self, "Updated",
                f"Welder '{welder_data['stencil_no']}' "
                f"qualification updated."
            )
        except Exception as exc:
            logger.exception("Failed to edit welder")
            QMessageBox.critical(
                self, "Update Error",
                f"Failed to update welder specifications:\n{exc}"
            )

    def _renew_continuity(self):
        """Grant 6-month continuity renewal per ASME IX QW-322."""
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select a welder to grant 6-month continuity "
                "renewal."
            )
            return

        welder_id = int(self.table.item(rows[0].row(), 0).text())
        welder_data = next(
            (w for w in self._cached_welders
             if w["id"] == welder_id), None
        )
        if not welder_data:
            return

        dlg = WelderContinuityDialog(self, welder_data=welder_data)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        months = dlg.get_extension_months()
        try:
            with self.db.session_scope() as session:
                # ✅ FIXED: SQLAlchemy 2.0
                w = session.get(Welder, welder_id)
                new_exp = None
                if w:
                    # Base date: max(today, current_expiry)
                    base_date = max(
                        datetime.date.today(),
                        w.expiry_date
                        if w.expiry_date
                        else datetime.date.today(),
                    )
                    # 6 months ≈ 183 days; 12 months ≈ 365 days
                    extension_days = (
                        183 if months == 6 else 365
                    )
                    new_exp = base_date + datetime.timedelta(
                        days=extension_days
                    )
                    w.expiry_date = new_exp
                    w.is_active = True

            self.refresh()
            if new_exp is not None:
                QMessageBox.information(
                    self, "Continuity Extended",
                    f"Granted {months}-Month WPQ renewal for "
                    f"Welder '{welder_data['stencil_no']}'.\n"
                    f"New Expiry Date: "
                    f"{new_exp.strftime('%Y-%m-%d')}"
                )
        except Exception as exc:
            logger.exception("Continuity extension failed")
            QMessageBox.critical(
                self, "Error",
                f"Failed to prolong qualification:\n{exc}"
            )

    def _toggle_active(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return

        welder_id = int(self.table.item(rows[0].row(), 0).text())
        try:
            with self.db.session_scope() as session:
                # ✅ FIXED: SQLAlchemy 2.0
                w = session.get(Welder, welder_id)
                if w:
                    w.is_active = not bool(w.is_active)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _delete_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select one or more welders to delete."
            )
            return

        welder_ids = [
            int(self.table.item(r.row(), 0).text()) for r in rows
        ]
        stencils = [
            self.table.item(r.row(), 1).text() for r in rows
        ]

        if QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(welder_ids)} welder "
            f"qualification record(s)?\n\n"
            f"Stamps: {', '.join(stencils[:5])}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as session:
                for wid in welder_ids:
                    # ✅ FIXED: SQLAlchemy 2.0
                    w = session.get(Welder, wid)
                    if w:
                        session.delete(w)

            self.refresh()
            QMessageBox.information(
                self, "Deleted",
                "Selected welder qualification records deleted."
            )
        except Exception as exc:
            logger.exception("Failed to delete welders")
            QMessageBox.critical(
                self, "Error",
                f"Could not delete welders:\n{exc}"
            )

    # ══════════════════════════════════════════
    #  DETAIL VIEW / CONTEXT MENU
    # ══════════════════════════════════════════
    def _on_row_double_click(self, index):
        row = index.row()
        welder_id = int(self.table.item(row, 0).text())
        welder_data = next(
            (w for w in self._cached_welders
             if w["id"] == welder_id), None
        )
        if not welder_data:
            return

        # Production stats — count welds by stencil or name
        stats = {}
        try:
            with self.db.session_scope() as s:
                welds = (
                    s.query(Weld)
                    .filter(
                        Weld.project_id == self.project_id,
                        (Weld.welder_id
                         == welder_data["stencil_no"])
                        | (Weld.welder_name
                           == welder_data["full_name"]),
                    )
                    .all()
                )
                stats["total_welds"] = len(welds)
                stats["accepted_welds"] = sum(
                    1 for x in welds if x.status == "Accepted"
                )
                stats["repaired_welds"] = sum(
                    x.repair_count or 0 for x in welds
                )
        except Exception:
            logger.warning(
                "Could not compute welder production stats",
                exc_info=True,
            )

        dlg = WelderDossierDialog(
            self, welder=welder_data, production_stats=stats
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

        act_dossier = QAction(
            "🔍 View Full Welder Dossier", self
        )
        act_dossier.triggered.connect(
            lambda: self._on_row_double_click(
                self.table.currentIndex()
            )
        )
        menu.addAction(act_dossier)

        act_renew = QAction(
            "🔄 6-Month Continuity Extension", self
        )
        act_renew.triggered.connect(self._renew_continuity)
        menu.addAction(act_renew)

        menu.addSeparator()

        act_edit = QAction("✏️ Edit WPQ Variables", self)
        act_edit.triggered.connect(self._edit_selected_welder)
        menu.addAction(act_edit)

        act_toggle = QAction(
            "⏸️ Authorize / Deactivate Welder", self
        )
        act_toggle.triggered.connect(self._toggle_active)
        menu.addAction(act_toggle)

        menu.addSeparator()

        act_copy = QAction("📋 Copy Stencil Stamp", self)
        act_copy.triggered.connect(
            lambda: QApplication.clipboard().setText(
                self.table.item(rows[0].row(), 1).text()
            )
        )
        menu.addAction(act_copy)

        act_del = QAction("🗑️ Delete Record(s)", self)
        act_del.triggered.connect(self._delete_selected)
        menu.addAction(act_del)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ══════════════════════════════════════════
    #  EXPORT
    # ══════════════════════════════════════════
    def _export_welders_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(
                self, "Export",
                "No welders available in current table view."
            )
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_code = self.proj_combo.currentText().split("–")[0].strip()
        default_name = (
            f"WPQ_Welder_Matrix_{proj_code}_{timestamp}.csv"
        )

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Welder Qualification Matrix",
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
                f"Welder Qualification Matrix exported "
                f"successfully to:\n{filename}"
            )
        except Exception as exc:
            logger.exception(
                "Failed to export welder matrix CSV"
            )
            QMessageBox.critical(
                self, "Export Error",
                f"Could not create CSV file:\n{exc}"
            )