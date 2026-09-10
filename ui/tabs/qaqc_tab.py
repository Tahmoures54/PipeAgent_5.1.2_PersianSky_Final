# -*- coding: utf-8 -*-
# ui/tabs/qaqc_tab.py – PipeAgent 5.3.0
# Quality Assurance & Quality Control (QA/QC) Management Hub
#
# Modules Included:
# 1. 🔨 Master Punch List (Categories A, B, C Tracking & Clearance)
# 2. 🚫 Non-Conformance Reports (NCR Issuance, Disposition & Closure)
# 3. 📋 Inspection & Test Plan (ITP Activity Matrix & Witness Points)
from __future__ import annotations

import csv
import logging
import datetime
from datetime import timezone
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QMessageBox, QHeaderView, QGroupBox, QComboBox,
    QFormLayout, QLineEdit, QDateEdit,
    QDialog, QCheckBox, QTextEdit, QFrame, QFileDialog,
    QApplication, QMenu, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor, QFont, QBrush, QCursor, QAction

from db.manager import DatabaseManager
from db.models import Project, ProjectAction

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  UTIL
# ─────────────────────────────────────────────
def _utcnow():
    """Naive UTC — replacement for deprecated datetime.utcnow()."""
    return datetime.datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────
#  BADGE PALETTES
# ─────────────────────────────────────────────
PUNCH_CAT_BADGES = {
    "A": {"bg": "#fee2e2", "fg": "#991b1b", "icon": "🔴", "label": "Cat A (Pre-Hydro Hold)"},
    "B": {"bg": "#ffedd5", "fg": "#9a3412", "icon": "🟠", "label": "Cat B (Pre-Commissioning)"},
    "C": {"bg": "#e0f2fe", "fg": "#075985", "icon": "🔵", "label": "Cat C (Handover / Minor)"},
}

NCR_STATUS_BADGES = {
    "Open":          {"bg": "#fee2e2", "fg": "#991b1b", "icon": "🔴"},
    "Under Review":  {"bg": "#fef3c7", "fg": "#92400e", "icon": "🟡"},
    "Dispositioned": {"bg": "#e0f2fe", "fg": "#075985", "icon": "🔄"},
    "Closed":        {"bg": "#dcfce7", "fg": "#166534", "icon": "🟢"},
}

ITP_POINT_BADGES = {
    "Hold (H)":         {"bg": "#fee2e2", "fg": "#991b1b", "icon": "🛑"},
    "Witness (W)":      {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "👁️"},
    "Review (R)":       {"bg": "#e0f2fe", "fg": "#075985", "icon": "📄"},
    "Surveillance (S)": {"bg": "#ecfdf5", "fg": "#065f46", "icon": "🔍"},
}
DEFAULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}


# ─────────────────────────────────────────────
#  STYLESHEET
# ─────────────────────────────────────────────
QAQC_STYLESHEET = """
    QWidget#qaqcTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #1a3a50, stop:1 #2d5a7b);
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
        background: white; color: #1a3a50;
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
    QPushButton#primaryBtn:hover { background: #1d4ed8; }
    QPushButton#successBtn {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #10b981, stop:1 #059669);
        color: white; border: none; padding: 7px 15px;
        border-radius: 6px; font-weight: 700;
    }
    QPushButton#successBtn:hover { background: #047857; }
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
    QLineEdit, QComboBox, QDateEdit, QTextEdit {
        padding: 6px 10px; border: 1px solid #cbd5e1;
        border-radius: 6px; font-size: 12px;
    }
"""


# ─────────────────────────────────────────────
#  KPI CARD
# ─────────────────────────────────────────────
class QAQCKPICard(QFrame):
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
        elif highlight == "red":
            self.val_lbl.setStyleSheet(
                "color: #991b1b; font-size: 19px; font-weight: 800;"
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
#  PUNCH ITEM DIALOG
# ─────────────────────────────────────────────
class PunchItemDialog(QDialog):
    def __init__(self, parent=None,
                 existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = existing_data is not None
        self.setWindowTitle(
            "Edit Punch Item" if self.is_edit
            else "Raise New Punch Item"
        )
        self.setMinimumWidth(500)
        self.setStyleSheet(QAQC_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.cmb_cat = QComboBox()
        self.cmb_cat.addItems([
            "A - Critical (Pre-Hydro Test Hold)",
            "B - Major (Pre-Commissioning Hold)",
            "C - Minor (Handover / Cosmetic)",
        ])

        self.txt_line = QLineEdit()
        self.txt_line.setPlaceholderText(
            'Piping Line Number (e.g. 6"-P-1001-A1A)'
        )

        self.txt_spool = QLineEdit()
        self.txt_spool.setPlaceholderText("Spool Number (e.g. SP-01)")

        self.txt_weld = QLineEdit()
        self.txt_weld.setPlaceholderText(
            "Weld / Joint ID (e.g. W-04 / FW-02)"
        )

        self.txt_loc = QLineEdit()
        self.txt_loc.setPlaceholderText(
            "Physical Location / Drawing Grid (e.g. Rack B, Bay 4)"
        )

        self.txt_desc = QTextEdit()
        self.txt_desc.setPlaceholderText(
            "Detailed defect description, non-conformance finding, "
            "or missing item..."
        )
        self.txt_desc.setMaximumHeight(80)

        self.txt_raised_by = QLineEdit("QC Inspector")
        self.dt_raised = QDateEdit()
        self.dt_raised.setCalendarPopup(True)
        self.dt_raised.setDate(QDate.currentDate())

        self.chk_cleared = QCheckBox(
            "Mark as Verified & Cleared (Closed)"
        )

        form.addRow("Punch Category *:", self.cmb_cat)
        form.addRow("Line Number *:", self.txt_line)
        form.addRow("Spool Number:", self.txt_spool)
        form.addRow("Weld Joint ID:", self.txt_weld)
        form.addRow("Plant Location:", self.txt_loc)
        form.addRow("Defect Description *:", self.txt_desc)
        form.addRow("Raised By Inspector:", self.txt_raised_by)
        form.addRow("Date Raised:", self.dt_raised)
        if self.is_edit:
            form.addRow("Clearance Status:", self.chk_cleared)
        layout.addLayout(form)

        if self.is_edit and existing_data:
            cat_val = existing_data.get("category", "A")
            idx = 0 if cat_val == "A" else (
                1 if cat_val == "B" else 2
            )
            self.cmb_cat.setCurrentIndex(idx)
            self.txt_line.setText(existing_data.get("line_number", ""))
            self.txt_spool.setText(existing_data.get("spool_number", ""))
            self.txt_weld.setText(existing_data.get("weld_id", ""))
            self.txt_desc.setPlainText(
                existing_data.get("description", "")
            )
            self.txt_raised_by.setText(existing_data.get("raised_by", ""))
            self.chk_cleared.setChecked(
                bool(existing_data.get("is_cleared", False))
            )

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Punch Item")
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
        if not self.txt_line.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Piping line number is required."
            )
            self.txt_line.setFocus()
            return
        if not self.txt_desc.toPlainText().strip():
            QMessageBox.warning(
                self, "Validation",
                "Defect description is mandatory."
            )
            self.txt_desc.setFocus()
            return
        self.result_data = {
            "category": self.cmb_cat.currentText().split()[0].strip(),
            "line_number": self.txt_line.text().strip(),
            "spool_number": self.txt_spool.text().strip(),
            "weld_id": self.txt_weld.text().strip(),
            "location": self.txt_loc.text().strip(),
            "description": self.txt_desc.toPlainText().strip(),
            "raised_by": self.txt_raised_by.text().strip(),
            "is_cleared": (
                self.chk_cleared.isChecked() if self.is_edit else False
            ),
        }
        self.accept()


# ─────────────────────────────────────────────
#  NCR DIALOG
# ─────────────────────────────────────────────
class NCRDialog(QDialog):
    def __init__(self, parent=None,
                 existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = existing_data is not None
        self.setWindowTitle(
            "Edit NCR Record" if self.is_edit
            else "Issue Non-Conformance Report (NCR)"
        )
        self.setMinimumWidth(520)
        self.setStyleSheet(QAQC_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.txt_ncr_no = QLineEdit()
        self.txt_ncr_no.setPlaceholderText("e.g. NCR-2024-PIP-001")

        self.cmb_type = QComboBox()
        self.cmb_type.addItems([
            "Welding / NDT Defect", "Material Spec Violation",
            "Dimensional Out-of-Tolerance", "Damage / Preservation",
            "Coating / Painting Failure", "Erection Alignment",
        ])

        self.txt_ref = QLineEdit()
        self.txt_ref.setPlaceholderText(
            "DWG No / PO No / Spec Reference"
        )

        self.txt_line = QLineEdit()
        self.txt_line.setPlaceholderText(
            "Affected Line / System Number"
        )

        self.txt_desc = QTextEdit()
        self.txt_desc.setPlaceholderText(
            "Describe the nature of the non-conformance and "
            "non-compliance..."
        )
        self.txt_desc.setMaximumHeight(80)

        self.cmb_disposition = QComboBox()
        self.cmb_disposition.addItems([
            "Rework / Repair as per WPS",
            "Scrap & Replace Material",
            "Use-As-Is (Engineering Concession)",
            "Return to Vendor (RTV)",
        ])

        self.txt_corrective = QTextEdit()
        self.txt_corrective.setPlaceholderText(
            "Root cause analysis & preventive action plan "
            "to prevent recurrence..."
        )
        self.txt_corrective.setMaximumHeight(70)

        self.cmb_status = QComboBox()
        self.cmb_status.addItems([
            "Open", "Under Review", "Dispositioned", "Closed",
        ])

        form.addRow("NCR Number *:", self.txt_ncr_no)
        form.addRow("Discipline / Item Type:", self.cmb_type)
        form.addRow("Specification Reference:", self.txt_ref)
        form.addRow("Piping Line / Component:", self.txt_line)
        form.addRow("Non-Conformance Details *:", self.txt_desc)
        form.addRow("Proposed Disposition:", self.cmb_disposition)
        form.addRow("Corrective Action Plan:", self.txt_corrective)
        form.addRow("NCR Current Status:", self.cmb_status)
        layout.addLayout(form)

        if self.is_edit and existing_data:
            self.txt_ncr_no.setText(existing_data.get("ncr_no", ""))
            self.txt_ncr_no.setReadOnly(True)
            self.cmb_type.setCurrentText(
                existing_data.get("item_type", "Welding / NDT Defect")
            )
            self.txt_ref.setText(
                existing_data.get("item_reference", "")
            )
            self.txt_line.setText(
                existing_data.get("line_number", "")
            )
            self.txt_desc.setPlainText(
                existing_data.get("description", "")
            )
            self.cmb_disposition.setCurrentText(
                existing_data.get(
                    "disposition", "Rework / Repair as per WPS"
                )
            )
            self.txt_corrective.setPlainText(
                existing_data.get("corrective_action", "")
            )
            self.cmb_status.setCurrentText(
                existing_data.get("status", "Open")
            )

        btns = QHBoxLayout()
        btn_save = QPushButton("Save NCR")
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
        if not self.txt_ncr_no.text().strip():
            QMessageBox.warning(
                self, "Validation", "NCR Number is mandatory."
            )
            self.txt_ncr_no.setFocus()
            return
        if not self.txt_desc.toPlainText().strip():
            QMessageBox.warning(
                self, "Validation",
                "Description of non-conformance is required."
            )
            self.txt_desc.setFocus()
            return
        self.result_data = {
            "ncr_no": self.txt_ncr_no.text().strip(),
            "item_type": self.cmb_type.currentText(),
            "item_reference": self.txt_ref.text().strip(),
            "line_number": self.txt_line.text().strip(),
            "description": self.txt_desc.toPlainText().strip(),
            "disposition": self.cmb_disposition.currentText(),
            "corrective_action": (
                self.txt_corrective.toPlainText().strip()
            ),
            "status": self.cmb_status.currentText(),
        }
        self.accept()


# ─────────────────────────────────────────────
#  ITP DIALOG
# ─────────────────────────────────────────────
class ITPDialog(QDialog):
    def __init__(self, parent=None,
                 existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = existing_data is not None
        self.setWindowTitle(
            "Edit ITP Activity" if self.is_edit
            else "Add ITP Activity & Inspection Point"
        )
        self.setMinimumWidth(500)
        self.setStyleSheet(QAQC_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.txt_itp_no = QLineEdit()
        self.txt_itp_no.setPlaceholderText(
            "e.g. ITP-PIP-001 (Piping Erection & Testing)"
        )

        self.txt_code = QLineEdit()
        self.txt_code.setPlaceholderText(
            "Activity Code (e.g. 1.01 / NDT-02)"
        )

        self.txt_desc = QTextEdit()
        self.txt_desc.setPlaceholderText(
            "Activity Description (e.g. Visual & Dimensional "
            "Inspection of Root Pass)"
        )
        self.txt_desc.setMaximumHeight(75)

        self.txt_ref = QLineEdit()
        self.txt_ref.setPlaceholderText(
            "Standard / Procedure (e.g. ASME B31.3 / PR-QC-05)"
        )

        self.cmb_type = QComboBox()
        self.cmb_type.addItems([
            "Hold (H)", "Witness (W)", "Review (R)", "Surveillance (S)",
        ])

        self.chk_client = QCheckBox(
            "Client / Owner Witness Required (Mandatory Sign-off)"
        )
        self.chk_client.setChecked(True)

        self.cmb_status = QComboBox()
        self.cmb_status.addItems([
            "Pending Inspection", "Completed / Cleared", "Waived",
        ])

        form.addRow("ITP Document No *:", self.txt_itp_no)
        form.addRow("Activity Code *:", self.txt_code)
        form.addRow("Activity Scope *:", self.txt_desc)
        form.addRow("Reference Standard / Spec:", self.txt_ref)
        form.addRow("Inspection Point Class:", self.cmb_type)
        form.addRow("Sign-off Governance:", self.chk_client)
        form.addRow("Activity Status:", self.cmb_status)
        layout.addLayout(form)

        if self.is_edit and existing_data:
            self.txt_itp_no.setText(
                existing_data.get("itp_number", "")
            )
            self.txt_code.setText(
                existing_data.get("activity_code", "")
            )
            self.txt_desc.setPlainText(
                existing_data.get("activity_description", "")
            )
            self.txt_ref.setText(
                existing_data.get("reference_doc", "")
            )
            self.cmb_type.setCurrentText(
                existing_data.get("inspection_type", "Hold (H)")
            )
            self.chk_client.setChecked(
                bool(existing_data.get("client_witness", False))
            )
            self.cmb_status.setCurrentText(
                existing_data.get("status", "Pending Inspection")
            )

        btns = QHBoxLayout()
        btn_save = QPushButton("Save ITP Item")
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
        if (not self.txt_itp_no.text().strip()
                or not self.txt_code.text().strip()):
            QMessageBox.warning(
                self, "Validation",
                "ITP Document Number and Activity Code are required."
            )
            return
        if not self.txt_desc.toPlainText().strip():
            QMessageBox.warning(
                self, "Validation",
                "Activity description is mandatory."
            )
            return
        self.result_data = {
            "itp_number": self.txt_itp_no.text().strip(),
            "activity_code": self.txt_code.text().strip(),
            "activity_description": (
                self.txt_desc.toPlainText().strip()
            ),
            "reference_doc": self.txt_ref.text().strip(),
            "inspection_type": self.cmb_type.currentText(),
            "client_witness": self.chk_client.isChecked(),
            "status": self.cmb_status.currentText(),
        }
        self.accept()


# ─────────────────────────────────────────────
#  DETAIL DIALOG
# ─────────────────────────────────────────────
class QAQCDetailDialog(QDialog):
    def __init__(self, parent=None, title: str = "Details",
                 data: dict = None):
        super().__init__(parent)
        self.setWindowTitle(f"🔍 Quality Record Dossier – {title}")
        self.setMinimumSize(560, 440)
        self.setStyleSheet(QAQC_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hdr = QLabel(f"📋 Quality Record Dossier: {title}")
        hdr.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #1a3a50;"
        )
        layout.addWidget(hdr)

        info_box = QGroupBox("Inspection & Traceability Findings")
        info_grid = QGridLayout(info_box)
        info_grid.setSpacing(8)

        data = data or {}
        row_idx = 0
        for k, v in data.items():
            if k in ("id", "description", "corrective_action", "remarks"):
                continue
            lbl_w = QLabel(f"<b>{k.replace('_', ' ').title()}:</b>")
            lbl_w.setStyleSheet("color: #475569;")
            val_w = QLabel(str(v or "—"))
            val_w.setStyleSheet("color: #0f172a; font-weight: 600;")
            r, c = divmod(row_idx, 2)
            info_grid.addWidget(lbl_w, r, c * 2)
            info_grid.addWidget(val_w, r, c * 2 + 1)
            row_idx += 1

        layout.addWidget(info_box)

        desc_box = QGroupBox(
            "Detailed Scope / Defect / Corrective Action"
        )
        desc_lay = QVBoxLayout(desc_box)
        txt_desc = QTextEdit()
        txt_desc.setReadOnly(True)
        full_text = (
            f"Scope / Finding:\n{data.get('description', '—')}\n\n"
            f"Corrective Action / Action Plan:\n"
            f"{data.get('corrective_action', data.get('remarks', '—'))}"
        )
        txt_desc.setPlainText(full_text)
        desc_lay.addWidget(txt_desc)
        layout.addWidget(desc_box)

        btn_close = QPushButton("Close Dossier")
        btn_close.setObjectName("secondaryBtn")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class QAQCTab(QWidget):
    def __init__(self, db: DatabaseManager,
                 session_manager):
        super().__init__()
        self.setObjectName("qaqcTab")
        self.db = db
        self.session_manager = session_manager
        self.project_id: Optional[int] = None

        self._cached_punches: list[dict] = []
        self._cached_ncrs: list[dict] = []
        self._cached_itps: list[dict] = []

        self._build_ui()
        self.setStyleSheet(QAQC_STYLESHEET)
        self._load_projects()

    # ── SESSION HELPER ───────────────────────────────────────
    def _get_session(self):
        return self.db.get_session()

    # ══════════════════════════════════════════
    #  UI BUILD
    # ══════════════════════════════════════════
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Header
        header_card = QFrame()
        header_card.setObjectName("headerCard")
        hdr_lay = QHBoxLayout(header_card)
        hdr_lay.setContentsMargins(14, 10, 14, 10)

        title_v = QVBoxLayout()
        t = QLabel("✅ Quality Assurance & Quality Control (QA/QC)")
        t.setObjectName("mainTitle")
        s = QLabel(
            "Piping Quality Management: Punch Clearance Lifecycle, "
            "Non-Conformance Reports (NCR) & ITP Surveillance Schedule."
        )
        s.setObjectName("subTitle")
        title_v.addWidget(t)
        title_v.addWidget(s)
        hdr_lay.addLayout(title_v, 1)

        proj_box = QHBoxLayout()
        lbl_p = QLabel("Project:")
        lbl_p.setStyleSheet("color: white; font-weight: bold;")
        proj_box.addWidget(lbl_p)

        self.cmb_project = QComboBox()
        self.cmb_project.setMinimumWidth(220)
        self.cmb_project.currentIndexChanged.connect(
            self._on_project_changed
        )
        proj_box.addWidget(self.cmb_project)

        btn_r = QPushButton("🔄 Refresh All")
        btn_r.setObjectName("secondaryBtn")
        btn_r.clicked.connect(self.refresh)
        proj_box.addWidget(btn_r)
        hdr_lay.addLayout(proj_box)

        root.addWidget(header_card)

        # KPI row
        kpi_lay = QHBoxLayout()
        kpi_lay.setSpacing(8)

        self.kpi_punch_a = QAQCKPICard(
            "Punch Cat A (Hold)", "🔴", "#ef4444"
        )
        self.kpi_punch_b = QAQCKPICard(
            "Punch Cat B (Pre-Comm)", "🟠", "#f59e0b"
        )
        self.kpi_punch_c = QAQCKPICard(
            "Punch Cat C (Handover)", "🔵", "#0ea5e9"
        )
        self.kpi_ncrs_open = QAQCKPICard(
            "Active Open NCRs", "🚫", "#dc2626"
        )
        self.kpi_itp_witness = QAQCKPICard(
            "ITP Witness Points", "📋", "#10b981"
        )

        for k in (self.kpi_punch_a, self.kpi_punch_b, self.kpi_punch_c,
                  self.kpi_ncrs_open, self.kpi_itp_witness):
            kpi_lay.addWidget(k)
        root.addLayout(kpi_lay)

        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.addTab(
            self._build_punch_widget(), "🔨 Punch List Master"
        )
        self.tabs.addTab(
            self._build_ncr_widget(), "🚫 Non-Conformance Reports (NCR)"
        )
        self.tabs.addTab(
            self._build_itp_widget(),
            "📋 Inspection & Test Plan (ITP)",
        )
        root.addWidget(self.tabs, 1)

    def _load_projects(self):
        self.cmb_project.blockSignals(True)
        self.cmb_project.clear()
        try:
            with self.db.session_scope() as s:
                for p in (
                    s.query(Project)
                    .order_by(Project.project_code)
                ):
                    self.cmb_project.addItem(
                        f"{p.project_code} – {p.title}", p.id
                    )
        except Exception:
            logger.exception("Failed to load projects in QAQCTab")

        self.cmb_project.blockSignals(False)
        if self.cmb_project.count():
            self._on_project_changed()

    def _on_project_changed(self):
        self.project_id = self.cmb_project.currentData()
        self.refresh()

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

    def _apply_badge(self, item: QTableWidgetItem, badge_dict: dict):
        item.setBackground(QBrush(QColor(badge_dict["bg"])))
        item.setForeground(QBrush(QColor(badge_dict["fg"])))
        f = item.font()
        f.setBold(True)
        item.setFont(f)

    # ══════════════════════════════════════════════════════
    #  1. PUNCH LIST
    # ══════════════════════════════════════════════════════
    def _build_punch_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_punch = QLineEdit()
        self.txt_search_punch.setPlaceholderText(
            "🔍 Search Line, Spool, Weld, Defect Description, Inspector..."
        )
        self.txt_search_punch.textChanged.connect(self._filter_punches)
        tb.addWidget(self.txt_search_punch, 1)

        self.cmb_punch_cat = QComboBox()
        self.cmb_punch_cat.addItem("All Categories", None)
        self.cmb_punch_cat.addItems(["A", "B", "C"])
        self.cmb_punch_cat.currentIndexChanged.connect(self._filter_punches)
        tb.addWidget(self.cmb_punch_cat)

        self.cmb_punch_status = QComboBox()
        self.cmb_punch_status.addItems([
            "All Statuses", "Open Only", "Cleared Only",
        ])
        self.cmb_punch_status.currentIndexChanged.connect(
            self._filter_punches
        )
        tb.addWidget(self.cmb_punch_status)

        btn_add = QPushButton("➕ New Punch")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_punch)
        tb.addWidget(btn_add)

        btn_clr = QPushButton("✅ Clear Selected")
        btn_clr.setObjectName("successBtn")
        btn_clr.clicked.connect(self._clear_punch)
        tb.addWidget(btn_clr)

        btn_exp = QPushButton("📥 Export PML CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(
            lambda: self._export_to_csv(
                self.punch_table, "Punch_Master_List"
            )
        )
        tb.addWidget(btn_exp)

        btn_del = QPushButton("🗑️")
        btn_del.setObjectName("dangerBtn")
        btn_del.setToolTip("Delete Selected Punch")
        btn_del.clicked.connect(self._delete_punch)
        tb.addWidget(btn_del)
        l.addLayout(tb)

        self.punch_table = QTableWidget(0, 10)
        self.punch_table.setHorizontalHeaderLabels([
            "ID", "Cat", "Piping Line No", "Target Spool", "Weld ID",
            "Defect Finding Description", "Raised By", "Date Raised",
            "Clearance Status", "Cleared By",
        ])
        self.punch_table.setColumnHidden(0, True)
        self._setup_table_style(self.punch_table)
        self.punch_table.doubleClicked.connect(
            lambda: self._on_row_double_clicked(
                self.punch_table, self._cached_punches, "Punch Item"
            )
        )
        self.punch_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.punch_table.customContextMenuRequested.connect(
            self._show_punch_context_menu
        )
        l.addWidget(self.punch_table)
        return w

    def refresh_punches(self):
        if not self.project_id:
            return
        session = self._get_session()
        self._cached_punches = []
        try:
            from services.qaqc_service import QAQCService
            svc = QAQCService(session)
            items = svc.punch_repo.get_items(self.project_id)

            cnt_a = cnt_b = cnt_c = 0
            for p in items:
                cat_str = p.category or "A"
                if not p.is_cleared:
                    if cat_str == "A":
                        cnt_a += 1
                    elif cat_str == "B":
                        cnt_b += 1
                    elif cat_str == "C":
                        cnt_c += 1

                self._cached_punches.append({
                    "id": p.id,
                    "category": cat_str,
                    "line_number": p.line_number or "",
                    "spool_number": p.spool_number or "",
                    "weld_id": p.weld_id or "",
                    "description": p.description or "",
                    "raised_by": p.raised_by or "",
                    "raised_date": str(p.raised_date or ""),
                    "is_cleared": bool(p.is_cleared),
                    "cleared_by": (
                        getattr(p, "cleared_by", "")
                        or ("Yes" if p.is_cleared else "No")
                    ),
                })

            self.kpi_punch_a.set_value(
                str(cnt_a), highlight="red" if cnt_a > 0 else "green"
            )
            self.kpi_punch_b.set_value(
                str(cnt_b), highlight="amber" if cnt_b > 0 else "green"
            )
            self.kpi_punch_c.set_value(str(cnt_c))

            self._filter_punches()
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Error in refresh_punches")
        finally:
            session.close()

    def _filter_punches(self):
        query = self.txt_search_punch.text().strip().lower()
        cat_f = self.cmb_punch_cat.currentData()
        st_f = self.cmb_punch_status.currentText()

        self.punch_table.setSortingEnabled(False)
        self.punch_table.setRowCount(0)

        for p in self._cached_punches:
            if cat_f and p["category"] != cat_f:
                continue
            if st_f == "Open Only" and p["is_cleared"]:
                continue
            elif st_f == "Cleared Only" and not p["is_cleared"]:
                continue
            if query:
                combined = (
                    f"{p['line_number']} {p['spool_number']} "
                    f"{p['weld_id']} {p['description']} "
                    f"{p['raised_by']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.punch_table.rowCount()
            self.punch_table.insertRow(r)

            self.punch_table.setItem(
                r, 0, QTableWidgetItem(str(p["id"]))
            )

            cat_item = QTableWidgetItem(p["category"])
            b_info = PUNCH_CAT_BADGES.get(p["category"], DEFAULT_BADGE)
            cat_item.setText(f"{b_info['icon']} {p['category']}")
            self._apply_badge(cat_item, b_info)
            self.punch_table.setItem(r, 1, cat_item)

            self.punch_table.setItem(
                r, 2, QTableWidgetItem(p["line_number"])
            )
            self.punch_table.setItem(
                r, 3, QTableWidgetItem(p["spool_number"])
            )
            self.punch_table.setItem(
                r, 4, QTableWidgetItem(p["weld_id"])
            )
            self.punch_table.setItem(
                r, 5, QTableWidgetItem(p["description"])
            )
            self.punch_table.setItem(
                r, 6, QTableWidgetItem(p["raised_by"])
            )
            self.punch_table.setItem(
                r, 7, QTableWidgetItem(p["raised_date"])
            )

            st_item = QTableWidgetItem(
                "✅ Cleared" if p["is_cleared"] else "🔴 Open"
            )
            st_item.setForeground(QBrush(QColor(
                "#166534" if p["is_cleared"] else "#991b1b"
            )))
            f_b = st_item.font()
            f_b.setBold(True)
            st_item.setFont(f_b)
            self.punch_table.setItem(r, 8, st_item)

            self.punch_table.setItem(
                r, 9, QTableWidgetItem(p["cleared_by"])
            )

        self.punch_table.setSortingEnabled(True)

    def _add_punch(self):
        if not self.project_id:
            QMessageBox.warning(
                self, "Project", "Select a project first."
            )
            return
        dlg = PunchItemDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            session = self._get_session()
            try:
                from services.qaqc_service import QAQCService
                svc = QAQCService(session)
                svc.raise_punch(self.project_id, **dlg.result_data)
                session.commit()
                self.refresh_punches()
                QMessageBox.information(
                    self, "Success", "Punch item registered."
                )
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    def _clear_punch(self):
        rows = self.punch_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select one or more punch items to clear."
            )
            return

        punch_ids = [
            int(self.punch_table.item(r.row(), 0).text()) for r in rows
        ]
        if QMessageBox.question(
            self, "Confirm Clearance",
            f"Verify and Clear {len(punch_ids)} selected punch item(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        session = self._get_session()
        try:
            from services.qaqc_service import QAQCService
            svc = QAQCService(session)
            u_name = getattr(self.session_manager, "username", "admin")
            for pid in punch_ids:
                svc.clear_punch(pid, u_name)
            session.commit()
            self.refresh_punches()
            QMessageBox.information(
                self, "Cleared",
                f"{len(punch_ids)} Punch item(s) marked as Cleared "
                f"by {u_name}."
            )
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Error", str(e))
        finally:
            session.close()

    def _delete_punch(self):
        rows = self.punch_table.selectionModel().selectedRows()
        if not rows:
            return
        punch_ids = [
            int(self.punch_table.item(r.row(), 0).text()) for r in rows
        ]
        if QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(punch_ids)} punch item(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        session = self._get_session()
        try:
            from db.models import PunchItem
            for pid in punch_ids:
                # ✅ FIXED: SQLAlchemy 2.0 — session.get(Model, pk)
                item = session.get(PunchItem, pid)
                if item:
                    session.delete(item)
            session.commit()
            self.refresh_punches()
            QMessageBox.information(self, "Deleted", "Punch items deleted.")
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Error", str(e))
        finally:
            session.close()

    # ══════════════════════════════════════════════════════
    #  2. NCR
    # ══════════════════════════════════════════════════════
    def _build_ncr_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_ncr = QLineEdit()
        self.txt_search_ncr.setPlaceholderText(
            "🔍 Search NCR No, Item Type, Reference, Description..."
        )
        self.txt_search_ncr.textChanged.connect(self._filter_ncrs)
        tb.addWidget(self.txt_search_ncr, 1)

        self.cmb_ncr_status = QComboBox()
        self.cmb_ncr_status.addItem("All Statuses", None)
        for st in NCR_STATUS_BADGES.keys():
            self.cmb_ncr_status.addItem(st, st)
        self.cmb_ncr_status.currentIndexChanged.connect(self._filter_ncrs)
        tb.addWidget(self.cmb_ncr_status)

        btn_add = QPushButton("➕ Issue NCR")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_ncr)
        tb.addWidget(btn_add)

        btn_cls = QPushButton("🔒 Close NCR")
        btn_cls.setObjectName("secondaryBtn")
        btn_cls.clicked.connect(self._close_ncr)
        tb.addWidget(btn_cls)

        btn_exp = QPushButton("📥 Export NCR Log")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(
            lambda: self._export_to_csv(
                self.ncr_table, "NCR_Register_Log"
            )
        )
        tb.addWidget(btn_exp)

        btn_del = QPushButton("🗑️")
        btn_del.setObjectName("dangerBtn")
        btn_del.setToolTip("Delete Selected NCR")
        btn_del.clicked.connect(self._delete_ncr)
        tb.addWidget(btn_del)
        l.addLayout(tb)

        self.ncr_table = QTableWidget(0, 9)
        self.ncr_table.setHorizontalHeaderLabels([
            "ID", "NCR No", "Discipline / Type", "Spec Reference",
            "Piping Line No", "Non-Conformance Scope",
            "Proposed Disposition", "Date Issued", "Status",
        ])
        self.ncr_table.setColumnHidden(0, True)
        self._setup_table_style(self.ncr_table)
        self.ncr_table.doubleClicked.connect(
            lambda: self._on_row_double_clicked(
                self.ncr_table, self._cached_ncrs,
                "Non-Conformance Report (NCR)"
            )
        )
        self.ncr_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.ncr_table.customContextMenuRequested.connect(
            self._show_ncr_context_menu
        )
        l.addWidget(self.ncr_table)
        return w

    def refresh_ncrs(self):
        if not self.project_id:
            return
        session = self._get_session()
        self._cached_ncrs = []
        try:
            from services.qaqc_service import QAQCService
            svc = QAQCService(session)
            records = svc.ncr_repo.get_records(self.project_id)

            open_cnt = 0
            for n in records:
                st_val = n.status or "Open"
                if st_val != "Closed":
                    open_cnt += 1

                self._cached_ncrs.append({
                    "id": n.id,
                    "ncr_no": n.ncr_no,
                    "item_type": n.item_type or "Welding",
                    "item_reference": n.item_reference or "",
                    "line_number": n.line_number or "",
                    "description": n.description or "",
                    "disposition": n.disposition or "",
                    "corrective_action": (
                        getattr(n, "corrective_action", "") or ""
                    ),
                    "raised_date": str(n.raised_date or ""),
                    "status": st_val,
                })

            self.kpi_ncrs_open.set_value(
                str(open_cnt),
                highlight="red" if open_cnt > 0 else "green",
            )
            self._filter_ncrs()
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Error in refresh_ncrs")
        finally:
            session.close()

    def _filter_ncrs(self):
        query = self.txt_search_ncr.text().strip().lower()
        st_f = self.cmb_ncr_status.currentData()

        self.ncr_table.setSortingEnabled(False)
        self.ncr_table.setRowCount(0)

        for n in self._cached_ncrs:
            if st_f and n["status"] != st_f:
                continue
            if query:
                combined = (
                    f"{n['ncr_no']} {n['item_type']} "
                    f"{n['item_reference']} {n['line_number']} "
                    f"{n['description']} {n['disposition']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.ncr_table.rowCount()
            self.ncr_table.insertRow(r)

            self.ncr_table.setItem(
                r, 0, QTableWidgetItem(str(n["id"]))
            )
            self.ncr_table.setItem(
                r, 1, QTableWidgetItem(n["ncr_no"])
            )
            self.ncr_table.setItem(
                r, 2, QTableWidgetItem(n["item_type"])
            )
            self.ncr_table.setItem(
                r, 3, QTableWidgetItem(n["item_reference"])
            )
            self.ncr_table.setItem(
                r, 4, QTableWidgetItem(n["line_number"])
            )
            self.ncr_table.setItem(
                r, 5, QTableWidgetItem(n["description"])
            )
            self.ncr_table.setItem(
                r, 6, QTableWidgetItem(n["disposition"])
            )
            self.ncr_table.setItem(
                r, 7, QTableWidgetItem(n["raised_date"])
            )

            st_item = QTableWidgetItem(n["status"])
            badge = NCR_STATUS_BADGES.get(n["status"], DEFAULT_BADGE)
            st_item.setText(f"{badge['icon']} {n['status']}")
            self._apply_badge(st_item, badge)
            self.ncr_table.setItem(r, 8, st_item)

        self.ncr_table.setSortingEnabled(True)

    def _add_ncr(self):
        if not self.project_id:
            QMessageBox.warning(
                self, "Project", "Select a project first."
            )
            return
        dlg = NCRDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            session = self._get_session()
            try:
                from services.qaqc_service import QAQCService
                svc = QAQCService(session)
                svc.issue_ncr(self.project_id, **dlg.result_data)
                session.commit()
                self.refresh_ncrs()
                QMessageBox.information(
                    self, "Success",
                    f"NCR {dlg.result_data['ncr_no']} issued successfully."
                )
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    def _close_ncr(self):
        rows = self.ncr_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection", "Select an NCR to close."
            )
            return

        ncr_id = int(self.ncr_table.item(rows[0].row(), 0).text())
        ncr_no = self.ncr_table.item(rows[0].row(), 1).text()

        dlg = QDialog(self)
        dlg.setWindowTitle(f"🔒 Close NCR {ncr_no}")
        dlg.setMinimumWidth(450)
        dlg.setStyleSheet(QAQC_STYLESHEET)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()

        txt_corrective = QTextEdit()
        txt_corrective.setPlaceholderText(
            "Detail corrective action taken, inspection sign-off, "
            "and preventive steps..."
        )
        txt_corrective.setMaximumHeight(90)
        form.addRow("Corrective Action Sign-off *:", txt_corrective)
        lay.addLayout(form)

        btns = QHBoxLayout()
        btn_confirm = QPushButton("Close NCR")
        btn_confirm.setObjectName("primaryBtn")

        def _confirm():
            if not txt_corrective.toPlainText().strip():
                QMessageBox.warning(
                    dlg, "Validation",
                    "Corrective action text is required."
                )
                return
            dlg.accept()

        btn_confirm.clicked.connect(_confirm)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(dlg.reject)
        btns.addStretch()
        btns.addWidget(btn_confirm)
        btns.addWidget(btn_cancel)
        lay.addLayout(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        session = self._get_session()
        try:
            from services.qaqc_service import QAQCService
            svc = QAQCService(session)
            u_name = getattr(self.session_manager, "username", "admin")
            svc.close_ncr(
                ncr_id, u_name,
                corrective_action=txt_corrective.toPlainText().strip(),
            )
            session.commit()
            self.refresh_ncrs()
            QMessageBox.information(
                self, "Closed", f"NCR {ncr_no} closed and archived."
            )
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Error", str(e))
        finally:
            session.close()

    def _delete_ncr(self):
        rows = self.ncr_table.selectionModel().selectedRows()
        if not rows:
            return
        ncr_ids = [
            int(self.ncr_table.item(r.row(), 0).text()) for r in rows
        ]
        if QMessageBox.question(
            self, "Confirm Delete",
            f"Delete {len(ncr_ids)} NCR record(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        session = self._get_session()
        try:
            from db.models import NCRRecord
            for nid in ncr_ids:
                # ✅ FIXED: SQLAlchemy 2.0
                rec = session.get(NCRRecord, nid)
                if rec:
                    session.delete(rec)
            session.commit()
            self.refresh_ncrs()
            QMessageBox.information(
                self, "Deleted", "NCR records deleted."
            )
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Error", str(e))
        finally:
            session.close()

    # ══════════════════════════════════════════════════════
    #  3. ITP
    # ══════════════════════════════════════════════════════
    def _build_itp_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_itp = QLineEdit()
        self.txt_search_itp.setPlaceholderText(
            "🔍 Search ITP Doc No, Activity Code, Description, Standard..."
        )
        self.txt_search_itp.textChanged.connect(self._filter_itps)
        tb.addWidget(self.txt_search_itp, 1)

        self.cmb_itp_type = QComboBox()
        self.cmb_itp_type.addItem("All Inspection Points", None)
        for pt in ITP_POINT_BADGES.keys():
            self.cmb_itp_type.addItem(pt, pt)
        self.cmb_itp_type.currentIndexChanged.connect(self._filter_itps)
        tb.addWidget(self.cmb_itp_type)

        btn_add = QPushButton("➕ Add ITP Activity")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_itp)
        tb.addWidget(btn_add)

        btn_exp = QPushButton("📥 Export ITP Matrix")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(
            lambda: self._export_to_csv(
                self.itp_table, "ITP_Inspection_Matrix"
            )
        )
        tb.addWidget(btn_exp)

        btn_del = QPushButton("🗑️")
        btn_del.setObjectName("dangerBtn")
        btn_del.setToolTip("Delete Selected ITP Item")
        btn_del.clicked.connect(self._delete_itp)
        tb.addWidget(btn_del)
        l.addLayout(tb)

        self.itp_table = QTableWidget(0, 8)
        self.itp_table.setHorizontalHeaderLabels([
            "ID", "ITP No", "Activity Code",
            "Inspection Scope / Activity", "Standard Reference",
            "Inspection Point Class", "Client Witness", "Activity Status",
        ])
        self.itp_table.setColumnHidden(0, True)
        self._setup_table_style(self.itp_table)
        self.itp_table.doubleClicked.connect(
            lambda: self._on_row_double_clicked(
                self.itp_table, self._cached_itps, "ITP Activity"
            )
        )
        self.itp_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.itp_table.customContextMenuRequested.connect(
            self._show_itp_context_menu
        )
        l.addWidget(self.itp_table)
        return w

    def refresh_itp(self):
        if not self.project_id:
            return
        session = self._get_session()
        self._cached_itps = []
        try:
            from services.qaqc_service import QAQCService
            svc = QAQCService(session)
            items = svc.itp_repo.get_items(self.project_id)

            witness_cnt = 0
            for it in items:
                if it.client_witness:
                    witness_cnt += 1

                self._cached_itps.append({
                    "id": it.id,
                    "itp_number": it.itp_number,
                    "activity_code": it.activity_code or "",
                    "activity_description": (
                        it.activity_description or ""
                    ),
                    "reference_doc": it.reference_doc or "",
                    "inspection_type": (
                        it.inspection_type or "Hold (H)"
                    ),
                    "client_witness": bool(it.client_witness),
                    "status": it.status or "Pending Inspection",
                })

            self.kpi_itp_witness.set_value(f"{witness_cnt}/{len(items)}")
            self._filter_itps()
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Error in refresh_itp")
        finally:
            session.close()

    def _filter_itps(self):
        query = self.txt_search_itp.text().strip().lower()
        pt_f = self.cmb_itp_type.currentData()

        self.itp_table.setSortingEnabled(False)
        self.itp_table.setRowCount(0)

        for it in self._cached_itps:
            if pt_f and it["inspection_type"] != pt_f:
                continue
            if query:
                combined = (
                    f"{it['itp_number']} {it['activity_code']} "
                    f"{it['activity_description']} "
                    f"{it['reference_doc']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.itp_table.rowCount()
            self.itp_table.insertRow(r)

            self.itp_table.setItem(
                r, 0, QTableWidgetItem(str(it["id"]))
            )
            self.itp_table.setItem(
                r, 1, QTableWidgetItem(it["itp_number"])
            )
            self.itp_table.setItem(
                r, 2, QTableWidgetItem(it["activity_code"])
            )
            self.itp_table.setItem(
                r, 3, QTableWidgetItem(it["activity_description"])
            )
            self.itp_table.setItem(
                r, 4, QTableWidgetItem(it["reference_doc"])
            )

            pt_item = QTableWidgetItem(it["inspection_type"])
            badge = ITP_POINT_BADGES.get(
                it["inspection_type"], DEFAULT_BADGE
            )
            pt_item.setText(f"{badge['icon']} {it['inspection_type']}")
            self._apply_badge(pt_item, badge)
            self.itp_table.setItem(r, 5, pt_item)

            cw_item = QTableWidgetItem(
                "✅ Mandatory Witness" if it["client_witness"]
                else "— Standard"
            )
            cw_item.setForeground(QBrush(QColor(
                "#166534" if it["client_witness"] else "#64748b"
            )))
            self.itp_table.setItem(r, 6, cw_item)

            self.itp_table.setItem(
                r, 7, QTableWidgetItem(it["status"])
            )

        self.itp_table.setSortingEnabled(True)

    def _add_itp(self):
        if not self.project_id:
            QMessageBox.warning(
                self, "Project", "Select a project first."
            )
            return
        dlg = ITPDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            session = self._get_session()
            try:
                from services.qaqc_service import QAQCService
                svc = QAQCService(session)
                data = dlg.result_data
                svc.add_itp_activity(
                    self.project_id, data["itp_number"],
                    data["activity_code"],
                    data["activity_description"],
                    reference_doc=data["reference_doc"],
                    inspection_type=data["inspection_type"],
                    client_witness=data["client_witness"],
                )
                session.commit()
                self.refresh_itp()
                QMessageBox.information(
                    self, "Success",
                    f"ITP Activity {data['activity_code']} added."
                )
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    def _delete_itp(self):
        rows = self.itp_table.selectionModel().selectedRows()
        if not rows:
            return
        itp_ids = [
            int(self.itp_table.item(r.row(), 0).text()) for r in rows
        ]
        if QMessageBox.question(
            self, "Confirm Delete",
            f"Delete {len(itp_ids)} ITP item(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        session = self._get_session()
        try:
            from db.models import ITPActivity
            for iid in itp_ids:
                # ✅ FIXED: SQLAlchemy 2.0
                it = session.get(ITPActivity, iid)
                if it:
                    session.delete(it)
            session.commit()
            self.refresh_itp()
            QMessageBox.information(
                self, "Deleted", "ITP items deleted."
            )
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Error", str(e))
        finally:
            session.close()

    # ══════════════════════════════════════════════════════
    #  REFRESH / DOUBLE-CLICK / CONTEXT MENUS
    # ══════════════════════════════════════════════════════
    def refresh(self):
        self.refresh_punches()
        self.refresh_ncrs()
        self.refresh_itp()

    def _on_row_double_clicked(self, table: QTableWidget,
                                cache: list[dict], title: str):
        rows = table.selectionModel().selectedRows()
        if not rows:
            return
        item_id = int(table.item(rows[0].row(), 0).text())
        rec_data = next(
            (x for x in cache if x["id"] == item_id), None
        )
        if rec_data:
            dlg = QAQCDetailDialog(self, title=title, data=rec_data)
            dlg.exec()

    def _show_punch_context_menu(self, pos):
        rows = self.punch_table.selectionModel().selectedRows()
        if not rows:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 18px; }"
        )

        act_view = QAction("🔍 View Full Punch Dossier", self)
        act_view.triggered.connect(
            lambda: self._on_row_double_clicked(
                self.punch_table, self._cached_punches, "Punch Item"
            )
        )
        menu.addAction(act_view)

        act_clr = QAction("✅ Mark as Cleared", self)
        act_clr.triggered.connect(self._clear_punch)
        menu.addAction(act_clr)

        menu.addSeparator()
        act_del = QAction("🗑️ Delete Punch Item", self)
        act_del.triggered.connect(self._delete_punch)
        menu.addAction(act_del)
        menu.exec(self.punch_table.viewport().mapToGlobal(pos))

    def _show_ncr_context_menu(self, pos):
        rows = self.ncr_table.selectionModel().selectedRows()
        if not rows:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 18px; }"
        )

        act_view = QAction("🔍 View Full NCR Dossier", self)
        act_view.triggered.connect(
            lambda: self._on_row_double_clicked(
                self.ncr_table, self._cached_ncrs,
                "Non-Conformance Report (NCR)"
            )
        )
        menu.addAction(act_view)

        act_cls = QAction("🔒 Close / Sign-off NCR", self)
        act_cls.triggered.connect(self._close_ncr)
        menu.addAction(act_cls)

        menu.addSeparator()
        act_del = QAction("🗑️ Delete NCR", self)
        act_del.triggered.connect(self._delete_ncr)
        menu.addAction(act_del)
        menu.exec(self.ncr_table.viewport().mapToGlobal(pos))

    def _show_itp_context_menu(self, pos):
        rows = self.itp_table.selectionModel().selectedRows()
        if not rows:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 18px; }"
        )

        act_view = QAction("🔍 View ITP Scope", self)
        act_view.triggered.connect(
            lambda: self._on_row_double_clicked(
                self.itp_table, self._cached_itps, "ITP Activity"
            )
        )
        menu.addAction(act_view)

        menu.addSeparator()
        act_del = QAction("🗑️ Delete ITP Item", self)
        act_del.triggered.connect(self._delete_itp)
        menu.addAction(act_del)
        menu.exec(self.itp_table.viewport().mapToGlobal(pos))

    # ══════════════════════════════════════════════════════
    #  EXPORT
    # ══════════════════════════════════════════════════════
    def _export_to_csv(self, table: QTableWidget, prefix: str):
        if table.rowCount() == 0:
            QMessageBox.warning(
                self, "Export", "Table is empty. Nothing to export."
            )
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export CSV Report",
            f"{prefix}_{timestamp}.csv",
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
                f"Data exported successfully to:\n{filename}"
            )
        except Exception as e:
            logger.exception("Failed to export QA/QC CSV")
            QMessageBox.critical(
                self, "Export Error",
                f"Failed to save CSV file:\n{e}"
            )