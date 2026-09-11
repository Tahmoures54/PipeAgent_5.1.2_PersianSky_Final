# -*- coding: utf-8 -*-
# ui/tabs/procurement_tab.py – PipeAgent 5.3.0
# Materials Receiving (MRR), Warehouse Inventory, Heat Number Traceability
# & MTO Allocation
from __future__ import annotations

import csv
import logging
import datetime
from datetime import timezone
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QDoubleSpinBox, QTabWidget, QCheckBox,
    QFrame, QFileDialog, QApplication, QMenu, QAbstractItemView,
    QGroupBox, QSpinBox, QDateEdit, QScrollArea,
)
from PyQt6.QtGui import QColor, QFont, QBrush, QCursor, QAction

from db.manager import DatabaseManager
from db.models import (
    Project, MaterialItem, MaterialTakeOff, ProjectAction,
)
from services.record_fields import apply_fields
from security.session import SessionManager
from services.material_tracking import MaterialTrackingService
from services.license import increment_usage

MTO_REGISTER_FIELDS = (
    "item_number", "thickness_mm", "length_mm", "two_year_qty",
    "purchase_qty", "phase", "commodity_code", "subject",
    "source_document_number", "revision", "page_number",
    "miv_number", "miv_date", "miv_qty",
)

# ── Material types (fallback if config missing) ────────────────
try:
    from config import MATERIAL_TYPES
except ImportError:
    MATERIAL_TYPES = [
        "Pipe", "Elbow 90°", "Elbow 45°", "Tee (Equal/Reducing)",
        "Reducer (Conc/Ecc)", "Flange (WN/SO/Blind)",
        "Valve (Gate/Globe/Ball/Check)",
        "Gasket", "Stud Bolt & Nuts", "Olet / Branch",
        "Pipe Support Steel",
    ]

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  UTIL
# ─────────────────────────────────────────────
def _utcnow():
    """Naive UTC — replacement for deprecated datetime.utcnow()."""
    return datetime.datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────
#  BADGES
# ─────────────────────────────────────────────
MTO_STATUS_BADGES = {
    "Fully Issued":     {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Partially Issued": {"bg": "#e0f2fe", "fg": "#075985", "icon": "🔄"},
    "Open":             {"bg": "#fef3c7", "fg": "#92400e", "icon": "⏳"},
    "Shortage":         {"bg": "#fee2e2", "fg": "#991b1b", "icon": "⚠️"},
    "Cancelled":        {"bg": "#f1f5f9", "fg": "#475569", "icon": "❌"},
}
DEFAULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}


# ─────────────────────────────────────────────
#  STYLESHEET
# ─────────────────────────────────────────────
PROCUREMENT_STYLESHEET = """
    QWidget#procurementTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #0f2942, stop:1 #1e456e);
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
        background: white; color: #0f2942;
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
class ProcurementKPICard(QFrame):
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
        elif highlight == "blue":
            self.val_lbl.setStyleSheet(
                "color: #0369a1; font-size: 19px; font-weight: 800;"
            )
        else:
            self.val_lbl.setStyleSheet(
                "color: #0f172a; font-size: 19px; font-weight: 800;"
            )


# ─────────────────────────────────────────────
#  MATERIAL DIALOG
# ─────────────────────────────────────────────
class MaterialDialog(QDialog):
    def __init__(self, parent=None, projects=None,
                 existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = existing_data is not None
        self.setWindowTitle(
            "Edit Warehouse Stock Item" if self.is_edit
            else "Receive Material (MRR Log)"
        )
        self.setMinimumWidth(480)
        self.setStyleSheet(PROCUREMENT_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.project_combo = QComboBox()
        if projects:
            for p in projects:
                self.project_combo.addItem(
                    f"{p.project_code} – {getattr(p, 'title', '')}",
                    p.id,
                )

        self.mtype = QComboBox()
        self.mtype.addItems(MATERIAL_TYPES)

        self.grade = QLineEdit()
        self.grade.setPlaceholderText(
            "e.g. ASTM A106 Gr.B / A105 / SS316L"
        )

        self.size = QLineEdit()
        self.size.setPlaceholderText('e.g. 6" (SCH 40) or DN150')

        self.heat = QLineEdit()
        self.heat.setPlaceholderText(
            "Manufacturer Heat / Melt Number *"
        )

        self.qty = QDoubleSpinBox()
        self.qty.setRange(0.001, 1e9)
        self.qty.setDecimals(3)
        self.qty.setValue(1.0)

        self.unit = QComboBox()
        self.unit.setEditable(True)
        self.unit.addItems([
            "EA (Pieces)", "M (Meters)", "FT (Feet)",
            "KG", "SET", "LOT",
        ])

        self.loc = QLineEdit()
        self.loc.setPlaceholderText(
            "Warehouse Bay / Rack / Laydown Yard No"
        )

        self.po_no = QLineEdit()
        self.po_no.setPlaceholderText(
            "PO / Delivery Note / MRR Reference"
        )

        self.mtr = QCheckBox(
            "Mill Test Certificate (MTR / 3.1) Verified & Attached"
        )
        self.mtr.setChecked(True)

        form.addRow("Project *:", self.project_combo)
        form.addRow("Commodity Type *:", self.mtype)
        form.addRow("Material Spec / Grade *:", self.grade)
        form.addRow("Nominal Size / Rating:", self.size)
        form.addRow("Heat / Batch Number *:", self.heat)
        form.addRow("Received Quantity *:", self.qty)
        form.addRow("Unit of Measurement:", self.unit)
        form.addRow("Warehouse Storage Location:", self.loc)
        form.addRow("PO / MRR Reference:", self.po_no)
        form.addRow("Quality Compliance:", self.mtr)
        layout.addLayout(form)

        if self.is_edit and existing_data:
            pid = existing_data.get("project_id")
            for i in range(self.project_combo.count()):
                if self.project_combo.itemData(i) == pid:
                    self.project_combo.setCurrentIndex(i)
                    break
            self.mtype.setCurrentText(
                existing_data.get("material_type", MATERIAL_TYPES[0])
            )
            self.grade.setText(existing_data.get("spec_grade", ""))
            self.size.setText(existing_data.get("size", ""))
            self.heat.setText(existing_data.get("heat_number", ""))
            self.qty.setValue(
                float(existing_data.get("quantity_received", 1.0))
            )
            self.unit.setCurrentText(
                existing_data.get("unit", "EA (Pieces)")
            )
            self.loc.setText(existing_data.get("location", ""))
            self.po_no.setText(existing_data.get("po_number", ""))
            self.mtr.setChecked(
                bool(existing_data.get("mtr_received", False))
            )

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Inventory Record")
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
        if not self.heat.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Heat / Batch number is mandatory for traceability."
            )
            self.heat.setFocus()
            return
        if not self.grade.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Material Spec / Grade is required."
            )
            self.grade.setFocus()
            return
        self.accept()

    def data(self):
        return {
            "project_id": self.project_combo.currentData(),
            "material_type": self.mtype.currentText(),
            "spec_grade": self.grade.text().strip(),
            "size": self.size.text().strip(),
            "heat_number": self.heat.text().strip(),
            "quantity": self.qty.value(),
            "unit": self.unit.currentText().split()[0].strip(),
            "location": self.loc.text().strip(),
            "po_number": self.po_no.text().strip(),
            "mtr_received": self.mtr.isChecked(),
        }


# ─────────────────────────────────────────────
#  MTO DIALOG
# ─────────────────────────────────────────────
class MTODialog(QDialog):
    def __init__(self, parent=None, projects=None,
                 existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = existing_data is not None
        self.setWindowTitle(
            "Edit MTO Requirement Line" if self.is_edit
            else "Add Material Take-Off (MTO) Line"
        )
        self.setMinimumWidth(520)
        self.setMinimumHeight(560)
        self.setStyleSheet(PROCUREMENT_STYLESHEET)

        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setSpacing(8)

        self.project_combo = QComboBox()
        if projects:
            for p in projects:
                self.project_combo.addItem(
                    f"{p.project_code} – {getattr(p, 'title', '')}",
                    p.id,
                )

        self.line = QLineEdit()
        self.line.setPlaceholderText(
            'Piping Line Number (e.g. 8"-PL-101)'
        )

        self.spool = QLineEdit()
        self.spool.setPlaceholderText(
            "Target Spool No (e.g. SP-01 / Field)"
        )

        self.mtype = QComboBox()
        self.mtype.addItems(MATERIAL_TYPES)

        self.desc = QLineEdit()
        self.desc.setPlaceholderText(
            "Component Description (e.g. 90 Deg LR Elbow BW)"
        )

        self.grade = QLineEdit()
        self.grade.setPlaceholderText(
            "Required Material Grade (e.g. ASTM A234 WPB)"
        )

        self.size = QLineEdit()
        self.size.setPlaceholderText(
            'Nominal Size & Schedule (e.g. 8" SCH 40)'
        )

        self.qty = QDoubleSpinBox()
        self.qty.setRange(0.001, 1e9)
        self.qty.setDecimals(3)
        self.qty.setValue(1.0)

        self.unit = QComboBox()
        self.unit.setEditable(True)
        self.unit.addItems([
            "EA (Pieces)", "M (Meters)", "FT (Feet)", "SET", "LOT",
        ])

        self.item_number = QLineEdit()
        self.thickness = QDoubleSpinBox()
        self.thickness.setRange(0, 200)
        self.thickness.setSuffix(" mm")
        self.length = QDoubleSpinBox()
        self.length.setRange(0, 1e7)
        self.length.setSuffix(" mm")
        self.two_year = QDoubleSpinBox()
        self.two_year.setRange(0, 1e9)
        self.purchase = QDoubleSpinBox()
        self.purchase.setRange(0, 1e9)
        self.phase = QLineEdit()
        self.commodity = QLineEdit()
        self.subject = QLineEdit()
        self.doc_no = QLineEdit()
        self.rev = QLineEdit()
        self.page = QLineEdit()
        self.miv_no = QLineEdit()
        self.miv_date = QDateEdit()
        self.miv_date.setCalendarPopup(True)
        self.miv_date.setDisplayFormat("yyyy-MM-dd")
        self.miv_date.setSpecialValueText("—")
        self.miv_date.setDate(QDate(2000, 1, 1))
        self.miv_qty = QDoubleSpinBox()
        self.miv_qty.setRange(0, 1e9)

        form.addRow("Project *:", self.project_combo)
        form.addRow("Piping Line No *:", self.line)
        form.addRow("Spool Identifier:", self.spool)
        form.addRow("Commodity Type *:", self.mtype)
        form.addRow("Item Number:", self.item_number)
        form.addRow("Item Description *:", self.desc)
        form.addRow("Required Spec / Grade:", self.grade)
        form.addRow("Size / Dimension:", self.size)
        form.addRow("Thickness (mm):", self.thickness)
        form.addRow("Length (mm):", self.length)
        form.addRow("Required Quantity *:", self.qty)
        form.addRow("2-Year Qty:", self.two_year)
        form.addRow("Purchase Qty:", self.purchase)
        form.addRow("Unit of Measurement:", self.unit)
        form.addRow("Phase:", self.phase)
        form.addRow("Commodity Code:", self.commodity)
        form.addRow("Subject:", self.subject)
        form.addRow("Source Document:", self.doc_no)
        form.addRow("Revision:", self.rev)
        form.addRow("Page:", self.page)
        form.addRow("MIV Number:", self.miv_no)
        form.addRow("MIV Date:", self.miv_date)
        form.addRow("MIV Qty:", self.miv_qty)
        scroll.setWidget(inner)
        layout.addWidget(scroll)

        if self.is_edit and existing_data:
            pid = existing_data.get("project_id")
            for i in range(self.project_combo.count()):
                if self.project_combo.itemData(i) == pid:
                    self.project_combo.setCurrentIndex(i)
                    break
            self.line.setText(existing_data.get("line_number", ""))
            self.spool.setText(existing_data.get("spool_number", ""))
            self.mtype.setCurrentText(
                existing_data.get("material_type", MATERIAL_TYPES[0])
            )
            self.desc.setText(existing_data.get("description", ""))
            self.grade.setText(existing_data.get("spec_grade", ""))
            self.size.setText(existing_data.get("size", ""))
            self.qty.setValue(
                float(existing_data.get("quantity_required", 1.0))
            )
            self.unit.setCurrentText(
                existing_data.get("unit", "EA (Pieces)")
            )
            self.item_number.setText(existing_data.get("item_number", ""))
            self.thickness.setValue(float(existing_data.get("thickness_mm") or 0))
            self.length.setValue(float(existing_data.get("length_mm") or 0))
            self.two_year.setValue(float(existing_data.get("two_year_qty") or 0))
            self.purchase.setValue(float(existing_data.get("purchase_qty") or 0))
            self.phase.setText(existing_data.get("phase", ""))
            self.commodity.setText(existing_data.get("commodity_code", ""))
            self.subject.setText(existing_data.get("subject", ""))
            self.doc_no.setText(existing_data.get("source_document_number", ""))
            self.rev.setText(existing_data.get("revision", ""))
            self.page.setText(existing_data.get("page_number", ""))
            self.miv_no.setText(existing_data.get("miv_number", ""))
            self.miv_qty.setValue(float(existing_data.get("miv_qty") or 0))
            raw = existing_data.get("miv_date")
            if raw:
                parsed = QDate.fromString(str(raw)[:10], "yyyy-MM-dd")
                if parsed.isValid():
                    self.miv_date.setDate(parsed)

        btns = QHBoxLayout()
        btn_save = QPushButton("Save MTO Item")
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
        if not self.line.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Piping Line Number is required."
            )
            self.line.setFocus()
            return
        if not self.desc.text().strip():
            QMessageBox.warning(
                self, "Validation", "Item Description is mandatory."
            )
            self.desc.setFocus()
            return
        self.accept()

    def data(self):
        return {
            "project_id": self.project_combo.currentData(),
            "line_number": self.line.text().strip(),
            "spool_number": self.spool.text().strip(),
            "material_type": self.mtype.currentText(),
            "description": self.desc.text().strip(),
            "spec_grade": self.grade.text().strip(),
            "size": self.size.text().strip(),
            "quantity_required": self.qty.value(),
            "unit": self.unit.currentText().split()[0].strip(),
            "item_number": self.item_number.text().strip(),
            "thickness_mm": self.thickness.value() or None,
            "length_mm": self.length.value() or None,
            "two_year_qty": self.two_year.value() or None,
            "purchase_qty": self.purchase.value() or None,
            "phase": self.phase.text().strip(),
            "commodity_code": self.commodity.text().strip(),
            "subject": self.subject.text().strip(),
            "source_document_number": self.doc_no.text().strip(),
            "revision": self.rev.text().strip(),
            "page_number": self.page.text().strip(),
            "miv_number": self.miv_no.text().strip(),
            "miv_date": None if self.miv_date.date() == QDate(2000, 1, 1) else self.miv_date.date().toPyDate(),
            "miv_qty": self.miv_qty.value() or None,
        }


# ─────────────────────────────────────────────
#  MATERIAL ISSUE DIALOG
# ─────────────────────────────────────────────
class MaterialIssueDialog(QDialog):
    """
    Allocates physical warehouse stock to an MTO line,
    binding the specific Heat Number for traceability.
    """

    def __init__(self, parent=None, mto_item: dict = None,
                 available_stock_items: list = None):
        super().__init__(parent)
        self.mto_item = mto_item or {}
        self.stock_items = available_stock_items or []
        self.setWindowTitle(
            f"📦 Issue Material from Warehouse – "
            f"Line: {self.mto_item.get('line_number')}"
        )
        self.setMinimumWidth(500)
        self.setStyleSheet(PROCUREMENT_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        req_qty = float(self.mto_item.get("quantity_required", 0))
        iss_qty = float(self.mto_item.get("quantity_issued", 0))
        balance = max(0.0, req_qty - iss_qty)

        summary_box = QLabel(
            f"<b>Target Line:</b> {self.mto_item.get('line_number')} "
            f"&middot; <b>Spool:</b> "
            f"{self.mto_item.get('spool_number') or 'Field'}<br>"
            f"<b>Item:</b> {self.mto_item.get('description')} "
            f"({self.mto_item.get('size')})<br>"
            f"<b>Required:</b> {req_qty} {self.mto_item.get('unit')} | "
            f"<b>Already Issued:</b> {iss_qty} | "
            f"<b>Balance:</b> "
            f"<span style='color:#991b1b; font-weight:bold;'>"
            f"{balance:.3f}</span>"
        )
        summary_box.setStyleSheet(
            "background: #f1f5f9; padding: 8px; border-radius: 6px;"
        )
        layout.addWidget(summary_box)

        self.stock_combo = QComboBox()
        for s in self.stock_items:
            avail = float(getattr(s, "quantity_available", 0) or 0)
            self.stock_combo.addItem(
                f"Heat: {s.heat_number} | {s.spec_grade} ({s.size}) – "
                f"Avail: {avail:.2f} {s.unit} @ {s.location or 'Yard'}",
                s.id,
            )

        if not self.stock_items:
            self.stock_combo.addItem(
                "❌ No available matching stock in warehouse!", None
            )
            self.stock_combo.setEnabled(False)

        self.spn_issue = QDoubleSpinBox()
        self.spn_issue.setRange(
            0.001, balance if balance > 0 else 1000.0
        )
        self.spn_issue.setDecimals(3)
        self.spn_issue.setValue(balance if balance > 0 else 1.0)
        self.spn_issue.setSuffix(
            f" {self.mto_item.get('unit', 'EA')}"
        )

        self.txt_recipient = QLineEdit()
        self.txt_recipient.setPlaceholderText(
            "Fabrication Shop Foreman / Contractor Rep"
        )

        form.addRow("Available Stock Batch *:", self.stock_combo)
        form.addRow("Quantity to Issue *:", self.spn_issue)
        form.addRow("Issued To / Recipient:", self.txt_recipient)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_issue = QPushButton("✔️ Confirm Material Issue")
        btn_issue.setObjectName("primaryBtn")
        btn_issue.clicked.connect(self._validate_and_accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_issue)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _validate_and_accept(self):
        if not self.stock_combo.currentData():
            QMessageBox.warning(
                self, "Validation",
                "Select a valid stock batch to issue from."
            )
            return
        if self.spn_issue.value() <= 0:
            QMessageBox.warning(
                self, "Validation",
                "Issue quantity must be greater than zero."
            )
            return
        self.accept()

    def get_issue_data(self):
        return {
            "stock_id": self.stock_combo.currentData(),
            "issue_qty": self.spn_issue.value(),
            "recipient": self.txt_recipient.text().strip(),
        }


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class ProcurementTab(QWidget):
    def __init__(self, db: DatabaseManager,
                 session: SessionManager):
        super().__init__()
        self.setObjectName("procurementTab")
        self.db = db
        self.session = session
        self.mat_svc = MaterialTrackingService(db)
        self.project_id: Optional[int] = None

        self._cached_stock: list[dict] = []
        self._cached_mto: list[dict] = []

        self._build()
        self.setStyleSheet(PROCUREMENT_STYLESHEET)
        self._load_projects()

    # ══════════════════════════════════════════
    #  UI BUILD
    # ══════════════════════════════════════════
    def _build(self):
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
            "📦 Procurement, Warehouse Inventory & MTO Allocations"
        )
        t.setObjectName("mainTitle")
        s = QLabel(
            "Material Receiving Reports (MRR), Heat Number Traceability, "
            "Warehouse Stock, and MTO Line Allocations."
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

        btn_refresh_all = QPushButton("🔄 Refresh All")
        btn_refresh_all.setObjectName("secondaryBtn")
        btn_refresh_all.clicked.connect(self.refresh)
        proj_box.addWidget(btn_refresh_all)
        hdr_lay.addLayout(proj_box)

        layout.addWidget(header_card)

        # KPI row
        kpi_lay = QHBoxLayout()
        kpi_lay.setSpacing(8)

        self.kpi_stock_total = ProcurementKPICard(
            "Total Stock Batches", "📦", "#3b82f6"
        )
        self.kpi_mtr_rate = ProcurementKPICard(
            "MTR 3.1 Compliance", "📜", "#10b981"
        )
        self.kpi_mto_lines = ProcurementKPICard(
            "MTO Bill of Quantities", "📋", "#8b5cf6"
        )
        self.kpi_mto_fulfilled = ProcurementKPICard(
            "MTO Issuance Rate", "📈", "#059669"
        )
        self.kpi_shortage = ProcurementKPICard(
            "Open MTO Shortages", "⚠️", "#ef4444"
        )

        for k in (self.kpi_stock_total, self.kpi_mtr_rate,
                  self.kpi_mto_lines, self.kpi_mto_fulfilled,
                  self.kpi_shortage):
            kpi_lay.addWidget(k)
        layout.addLayout(kpi_lay)

        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.addTab(
            self._build_stock_tab(),
            "🏬 Warehouse Stock & Receiving",
        )
        self.tabs.addTab(
            self._build_mto_tab(),
            "📋 Material Take-Off (MTO) & Allocations",
        )
        layout.addWidget(self.tabs, 1)

    # ══════════════════════════════════════════════════════
    #  STOCK TAB
    # ══════════════════════════════════════════════════════
    def _build_stock_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_stock = QLineEdit()
        self.txt_search_stock.setPlaceholderText(
            "🔍 Search Heat No, Spec/Grade, Size, Storage Location..."
        )
        self.txt_search_stock.textChanged.connect(self._filter_stock)
        tb.addWidget(self.txt_search_stock, 1)

        self.cmb_filter_type = QComboBox()
        self.cmb_filter_type.addItem("All Commodity Types", None)
        for mt in MATERIAL_TYPES:
            self.cmb_filter_type.addItem(mt, mt)
        self.cmb_filter_type.currentIndexChanged.connect(
            self._filter_stock
        )
        tb.addWidget(self.cmb_filter_type)

        self.cmb_filter_mtr = QComboBox()
        self.cmb_filter_mtr.addItems([
            "All MTR Statuses", "MTR Verified Only", "Missing MTR",
        ])
        self.cmb_filter_mtr.currentIndexChanged.connect(
            self._filter_stock
        )
        tb.addWidget(self.cmb_filter_mtr)

        btn_recv = QPushButton("➕ Receive Material (MRR)")
        btn_recv.setObjectName("primaryBtn")
        btn_recv.clicked.connect(self._recv)
        tb.addWidget(btn_recv)

        btn_exp_stock = QPushButton("📥 Export Stock CSV")
        btn_exp_stock.setObjectName("secondaryBtn")
        btn_exp_stock.clicked.connect(self._export_stock_csv)
        tb.addWidget(btn_exp_stock)

        btn_del_stock = QPushButton("🗑️ Delete")
        btn_del_stock.setObjectName("dangerBtn")
        btn_del_stock.clicked.connect(self._delete_selected_stock)
        tb.addWidget(btn_del_stock)
        l.addLayout(tb)

        self.stock_table = QTableWidget(0, 10)
        self.stock_table.setHorizontalHeaderLabels([
            "ID", "Commodity Type", "Spec / Grade", "Nominal Size",
            "Heat / Melt No.", "Qty Received", "Qty Available",
            "UOM", "Storage Location", "MTR Verified",
        ])
        self.stock_table.setColumnHidden(0, True)
        self._setup_table_style(self.stock_table)
        self.stock_table.doubleClicked.connect(self._edit_stock_item)
        self.stock_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.stock_table.customContextMenuRequested.connect(
            self._show_stock_context_menu
        )
        l.addWidget(self.stock_table)
        return w

    # ══════════════════════════════════════════════════════
    #  MTO TAB
    # ══════════════════════════════════════════════════════
    def _build_mto_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_mto = QLineEdit()
        self.txt_search_mto.setPlaceholderText(
            "🔍 Search Line Number, Spool, Description, Spec/Grade..."
        )
        self.txt_search_mto.textChanged.connect(self._filter_mto)
        tb.addWidget(self.txt_search_mto, 1)

        self.cmb_filter_mto_status = QComboBox()
        self.cmb_filter_mto_status.addItem(
            "All Allocation Statuses", None
        )
        for st in MTO_STATUS_BADGES.keys():
            self.cmb_filter_mto_status.addItem(st, st)
        self.cmb_filter_mto_status.currentIndexChanged.connect(
            self._filter_mto
        )
        tb.addWidget(self.cmb_filter_mto_status)

        btn_add_mto = QPushButton("➕ Add MTO Line")
        btn_add_mto.setObjectName("primaryBtn")
        btn_add_mto.clicked.connect(self._add_mto)
        tb.addWidget(btn_add_mto)

        btn_issue = QPushButton("⚡ Issue Stock to MTO")
        btn_issue.setObjectName("secondaryBtn")
        btn_issue.clicked.connect(self._issue_material_to_mto)
        tb.addWidget(btn_issue)

        btn_exp_mto = QPushButton("📥 Export BOQ CSV")
        btn_exp_mto.setObjectName("secondaryBtn")
        btn_exp_mto.clicked.connect(self._export_mto_csv)
        tb.addWidget(btn_exp_mto)

        btn_del_mto = QPushButton("🗑️ Delete")
        btn_del_mto.setObjectName("dangerBtn")
        btn_del_mto.clicked.connect(self._delete_selected_mto)
        tb.addWidget(btn_del_mto)
        l.addLayout(tb)

        self.mto_table = QTableWidget(0, 14)
        self.mto_table.setHorizontalHeaderLabels([
            "ID", "Piping Line No", "Target Spool", "Item", "Commodity Type",
            "Item Description", "Spec / Grade", "Size",
            "Qty Required", "Purchase Qty", "MIV No", "MIV Qty",
            "Qty Issued", "Allocation Status",
        ])
        self.mto_table.setColumnHidden(0, True)
        self._setup_table_style(self.mto_table)
        self.mto_table.doubleClicked.connect(self._edit_mto_item)
        self.mto_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.mto_table.customContextMenuRequested.connect(
            self._show_mto_context_menu
        )
        l.addWidget(self.mto_table)
        return w

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

    # ══════════════════════════════════════════════════════
    #  PROJECT LOADING
    # ══════════════════════════════════════════════════════
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
            logger.exception(
                "Failed to load projects in ProcurementTab"
            )

        self.proj.blockSignals(False)
        if self.proj.count():
            self._proj_changed()

    def _proj_changed(self):
        self.project_id = self.proj.currentData()
        self.refresh()

    def refresh(self):
        self._refresh_stock()
        self._refresh_mto()

    # ── STOCK REFRESH ────────────────────────────────────────
    def _refresh_stock(self):
        self.stock_table.setSortingEnabled(False)
        self.stock_table.setRowCount(0)
        self._cached_stock = []

        if not self.project_id:
            self._update_stock_kpis(0, 0)
            return

        try:
            with self.db.session_scope() as s:
                items = (
                    s.query(MaterialItem)
                    .filter(
                        MaterialItem.project_id == self.project_id
                    )
                    .all()
                )
                mtr_count = 0

                for it in items:
                    if it.mtr_received:
                        mtr_count += 1
                    self._cached_stock.append({
                        "id": it.id,
                        "project_id": it.project_id,
                        "material_type": it.material_type,
                        "spec_grade": it.spec_grade or "",
                        "size": it.size or "",
                        "heat_number": it.heat_number or "",
                        "quantity_received": float(
                            it.quantity_received or 0
                        ),
                        "quantity_available": float(
                            it.quantity_available or 0
                        ),
                        "unit": it.unit or "EA",
                        "location": it.location or "",
                        "po_number": (
                            getattr(it, "po_number", "") or ""
                        ),
                        "mtr_received": bool(it.mtr_received),
                    })

                self._update_stock_kpis(len(items), mtr_count)
                self._filter_stock()
        except Exception:
            logger.exception("Stock refresh failed")

    def _refresh_mto(self):
        self.mto_table.setSortingEnabled(False)
        self.mto_table.setRowCount(0)
        self._cached_mto = []

        if not self.project_id:
            self._update_mto_kpis(0, 0, 0)
            return

        try:
            with self.db.session_scope() as s:
                items = (
                    s.query(MaterialTakeOff)
                    .filter(
                        MaterialTakeOff.project_id == self.project_id
                    )
                    .all()
                )
                total_req = total_iss = shortage_cnt = 0

                for it in items:
                    req = float(it.quantity_required or 0)
                    iss = float(it.quantity_issued or 0)
                    bal = max(0.0, req - iss)
                    total_req += req
                    total_iss += iss

                    if iss >= req and req > 0:
                        status_calc = "Fully Issued"
                    elif iss > 0:
                        status_calc = "Partially Issued"
                    else:
                        status_calc = "Open"
                        shortage_cnt += 1

                    self._cached_mto.append({
                        "id": it.id,
                        "project_id": it.project_id,
                        "line_number": it.line_number or "",
                        "spool_number": it.spool_number or "",
                        "material_type": it.material_type,
                        "description": it.description or "",
                        "spec_grade": it.spec_grade or "",
                        "size": it.size or "",
                        "quantity_required": req,
                        "quantity_issued": iss,
                        "balance": bal,
                        "unit": it.unit or "EA",
                        "status": status_calc,
                        "item_number": getattr(it, "item_number", "") or "",
                        "thickness_mm": getattr(it, "thickness_mm", None),
                        "length_mm": getattr(it, "length_mm", None),
                        "two_year_qty": getattr(it, "two_year_qty", None),
                        "purchase_qty": getattr(it, "purchase_qty", None),
                        "phase": getattr(it, "phase", "") or "",
                        "commodity_code": getattr(it, "commodity_code", "") or "",
                        "subject": getattr(it, "subject", "") or "",
                        "source_document_number": getattr(it, "source_document_number", "") or "",
                        "revision": getattr(it, "revision", "") or "",
                        "page_number": getattr(it, "page_number", "") or "",
                        "miv_number": getattr(it, "miv_number", "") or "",
                        "miv_date": getattr(it, "miv_date", None),
                        "miv_qty": getattr(it, "miv_qty", None),
                    })

                issued_pct = (
                    (total_iss / total_req * 100)
                    if total_req > 0 else 0.0
                )
                self._update_mto_kpis(
                    len(items), issued_pct, shortage_cnt
                )
                self._filter_mto()
        except Exception:
            logger.exception("MTO refresh failed")

    def _update_stock_kpis(self, total: int, mtr_verified: int):
        self.kpi_stock_total.set_value(str(total))
        mtr_pct = (
            (mtr_verified / total * 100) if total > 0 else 100.0
        )
        self.kpi_mtr_rate.set_value(
            f"{mtr_pct:.1f}%",
            highlight="green" if mtr_pct >= 95.0 else "red",
        )

    def _update_mto_kpis(self, total_lines: int, issued_pct: float,
                          shortages: int):
        self.kpi_mto_lines.set_value(str(total_lines))
        self.kpi_mto_fulfilled.set_value(
            f"{issued_pct:.1f}%",
            highlight="green" if issued_pct >= 90.0 else None,
        )
        self.kpi_shortage.set_value(
            str(shortages),
            highlight="red" if shortages > 0 else "green",
        )

    # ── STOCK FILTER ─────────────────────────────────────────
    def _filter_stock(self):
        query = self.txt_search_stock.text().strip().lower()
        type_f = self.cmb_filter_type.currentData()
        mtr_f = self.cmb_filter_mtr.currentIndex()

        self.stock_table.setSortingEnabled(False)
        self.stock_table.setRowCount(0)

        for it in self._cached_stock:
            if type_f and it["material_type"] != type_f:
                continue

            if mtr_f == 1 and not it["mtr_received"]:
                continue
            elif mtr_f == 2 and it["mtr_received"]:
                continue

            if query:
                combined = (
                    f"{it['heat_number']} {it['spec_grade']} "
                    f"{it['size']} {it['location']} "
                    f"{it['material_type']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.stock_table.rowCount()
            self.stock_table.insertRow(r)

            self.stock_table.setItem(
                r, 0, QTableWidgetItem(str(it["id"]))
            )
            self.stock_table.setItem(
                r, 1, QTableWidgetItem(it["material_type"])
            )
            self.stock_table.setItem(
                r, 2, QTableWidgetItem(it["spec_grade"])
            )
            self.stock_table.setItem(
                r, 3, QTableWidgetItem(it["size"])
            )
            self.stock_table.setItem(
                r, 4, QTableWidgetItem(it["heat_number"])
            )
            self.stock_table.setItem(
                r, 5, QTableWidgetItem(
                    f"{it['quantity_received']:.3f}"
                )
            )

            avail_item = QTableWidgetItem(
                f"{it['quantity_available']:.3f}"
            )
            if it["quantity_available"] <= 0:
                avail_item.setForeground(QBrush(QColor("#991b1b")))
            self.stock_table.setItem(r, 6, avail_item)

            self.stock_table.setItem(
                r, 7, QTableWidgetItem(it["unit"])
            )
            self.stock_table.setItem(
                r, 8, QTableWidgetItem(it["location"])
            )

            mtr_item = QTableWidgetItem(
                "✅ Verified" if it["mtr_received"]
                else "❌ Missing MTR"
            )
            mtr_item.setForeground(QBrush(QColor(
                "#166534" if it["mtr_received"] else "#991b1b"
            )))
            f_bold = mtr_item.font()
            f_bold.setBold(True)
            mtr_item.setFont(f_bold)
            self.stock_table.setItem(r, 9, mtr_item)

        self.stock_table.setSortingEnabled(True)

    # ── MTO FILTER ───────────────────────────────────────────
    def _filter_mto(self):
        query = self.txt_search_mto.text().strip().lower()
        status_f = self.cmb_filter_mto_status.currentData()

        self.mto_table.setSortingEnabled(False)
        self.mto_table.setRowCount(0)

        for it in self._cached_mto:
            if status_f and it["status"] != status_f:
                continue
            if query:
                combined = (
                    f"{it['line_number']} {it['spool_number']} "
                    f"{it['description']} {it['spec_grade']} "
                    f"{it['size']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.mto_table.rowCount()
            self.mto_table.insertRow(r)

            self.mto_table.setItem(
                r, 0, QTableWidgetItem(str(it["id"]))
            )
            self.mto_table.setItem(
                r, 1, QTableWidgetItem(it["line_number"])
            )
            self.mto_table.setItem(
                r, 2, QTableWidgetItem(it["spool_number"])
            )
            self.mto_table.setItem(
                r, 3, QTableWidgetItem(it.get("item_number") or "")
            )
            self.mto_table.setItem(
                r, 4, QTableWidgetItem(it["material_type"])
            )
            self.mto_table.setItem(
                r, 5, QTableWidgetItem(it["description"])
            )
            self.mto_table.setItem(
                r, 6, QTableWidgetItem(it["spec_grade"])
            )
            self.mto_table.setItem(
                r, 7, QTableWidgetItem(it["size"])
            )
            self.mto_table.setItem(
                r, 8, QTableWidgetItem(
                    f"{it['quantity_required']:.3f} {it['unit']}"
                )
            )
            self.mto_table.setItem(
                r, 9, QTableWidgetItem(
                    "" if it.get("purchase_qty") is None else str(it.get("purchase_qty"))
                )
            )
            self.mto_table.setItem(
                r, 10, QTableWidgetItem(it.get("miv_number") or "")
            )
            self.mto_table.setItem(
                r, 11, QTableWidgetItem(
                    "" if it.get("miv_qty") is None else str(it.get("miv_qty"))
                )
            )
            self.mto_table.setItem(
                r, 12, QTableWidgetItem(
                    f"{it['quantity_issued']:.3f} {it['unit']}"
                )
            )

            status_item = QTableWidgetItem(it["status"])
            badge = MTO_STATUS_BADGES.get(
                it["status"], DEFAULT_BADGE
            )
            status_item.setText(f"{badge['icon']} {it['status']}")
            status_item.setBackground(QBrush(QColor(badge["bg"])))
            status_item.setForeground(QBrush(QColor(badge["fg"])))
            f = status_item.font()
            f.setBold(True)
            status_item.setFont(f)
            self.mto_table.setItem(r, 13, status_item)

        self.mto_table.setSortingEnabled(True)

    # ══════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════
    def _projects_snapshot(self):
        with self.db.session_scope() as s:
            return [
                type("P", (), {
                    "id": p.id,
                    "project_code": p.project_code,
                    "title": p.title,
                })()
                for p in (
                    s.query(Project).order_by(Project.project_code)
                )
            ]

    # ══════════════════════════════════════════
    #  STOCK CRUD
    # ══════════════════════════════════════════
    def _recv(self):
        projects = self._projects_snapshot()
        if not projects:
            QMessageBox.information(
                self, "Info", "Register a project first."
            )
            return

        dlg = MaterialDialog(self, projects)
        if self.project_id:
            for i in range(dlg.project_combo.count()):
                if dlg.project_combo.itemData(i) == self.project_id:
                    dlg.project_combo.setCurrentIndex(i)
                    break

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.data()
        item = self.mat_svc.receive_material(
            d["project_id"], d["material_type"],
            spec_grade=d["spec_grade"], size=d["size"],
            heat_number=d["heat_number"], quantity=d["quantity"],
            unit=d["unit"], location=d["location"],
            mtr_received=d["mtr_received"],
        )
        if item:
            self._refresh_stock()
            QMessageBox.information(
                self, "Success",
                f"Material Batch (Heat: {d['heat_number']}) "
                f"received in warehouse."
            )
        else:
            QMessageBox.warning(
                self, "Error",
                "Failed to register material receiving."
            )

    def _edit_stock_item(self):
        rows = self.stock_table.selectionModel().selectedRows()
        if not rows:
            return
        stock_id = int(self.stock_table.item(rows[0].row(), 0).text())
        stock_data = next(
            (x for x in self._cached_stock if x["id"] == stock_id),
            None,
        )
        if not stock_data:
            return

        projects = self._projects_snapshot()
        dlg = MaterialDialog(
            self, projects, existing_data=stock_data
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.data()
        try:
            with self.db.session_scope() as s:
                # ✅ FIXED: SQLAlchemy 2.0 — s.get(Model, pk)
                it = s.get(MaterialItem, stock_id)
                if it:
                    it.material_type = d["material_type"]
                    it.spec_grade = d["spec_grade"]
                    it.size = d["size"]
                    it.heat_number = d["heat_number"]
                    it.quantity_received = d["quantity"]
                    it.unit = d["unit"]
                    it.location = d["location"]
                    it.mtr_received = d["mtr_received"]
            self._refresh_stock()
            QMessageBox.information(
                self, "Updated",
                "Warehouse item specifications updated."
            )
        except Exception as e:
            logger.exception("Failed to edit stock item")
            QMessageBox.critical(
                self, "Error", f"Update failed:\n{e}"
            )

    def _delete_selected_stock(self):
        rows = self.stock_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select one or more stock batches to delete."
            )
            return

        ids = [
            int(self.stock_table.item(r.row(), 0).text())
            for r in rows
        ]
        if QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(ids)} warehouse "
            f"inventory record(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as s:
                for sid in ids:
                    # ✅ FIXED: SQLAlchemy 2.0
                    it = s.get(MaterialItem, sid)
                    if it:
                        s.delete(it)
            self._refresh_stock()
            QMessageBox.information(
                self, "Deleted", "Selected stock items deleted."
            )
        except Exception as e:
            logger.exception("Failed to delete stock")
            QMessageBox.critical(
                self, "Error", f"Could not delete:\n{e}"
            )

    # ══════════════════════════════════════════
    #  MTO CRUD
    # ══════════════════════════════════════════
    def _add_mto(self):
        projects = self._projects_snapshot()
        if not projects:
            QMessageBox.information(
                self, "Info", "Register a project first."
            )
            return

        dlg = MTODialog(self, projects)
        if self.project_id:
            for i in range(dlg.project_combo.count()):
                if dlg.project_combo.itemData(i) == self.project_id:
                    dlg.project_combo.setCurrentIndex(i)
                    break

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.data()
        if not increment_usage(self.db):
            QMessageBox.warning(
                self, "License Limit",
                "MTO creation limit reached under current license."
            )
            return

        try:
            with self.db.session_scope() as s:
                mto = MaterialTakeOff(
                    project_id=d["project_id"],
                    line_number=d["line_number"],
                    spool_number=d["spool_number"],
                    material_type=d["material_type"],
                    description=d["description"],
                    spec_grade=d["spec_grade"],
                    size=d["size"],
                    quantity_required=d["quantity_required"],
                    unit=d["unit"],
                    status="Open",
                    created_at=_utcnow(),
                )
                s.add(mto)
                s.flush()
                apply_fields(mto, d, MTO_REGISTER_FIELDS)
            self._refresh_mto()
            QMessageBox.information(
                self, "Success",
                f"MTO item added for Line {d['line_number']}."
            )
        except Exception as e:
            logger.exception("Failed to add MTO")
            QMessageBox.critical(
                self, "Error", f"Could not add MTO item:\n{e}"
            )

    def _edit_mto_item(self):
        rows = self.mto_table.selectionModel().selectedRows()
        if not rows:
            return
        mto_id = int(self.mto_table.item(rows[0].row(), 0).text())
        mto_data = next(
            (x for x in self._cached_mto if x["id"] == mto_id), None
        )
        if not mto_data:
            return

        projects = self._projects_snapshot()
        dlg = MTODialog(
            self, projects, existing_data=mto_data
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.data()
        try:
            with self.db.session_scope() as s:
                # ✅ FIXED: SQLAlchemy 2.0
                m = s.get(MaterialTakeOff, mto_id)
                if m:
                    m.line_number = d["line_number"]
                    m.spool_number = d["spool_number"]
                    m.material_type = d["material_type"]
                    m.description = d["description"]
                    m.spec_grade = d["spec_grade"]
                    m.size = d["size"]
                    m.quantity_required = d["quantity_required"]
                    m.unit = d["unit"]
                    apply_fields(m, d, MTO_REGISTER_FIELDS)
            self._refresh_mto()
            QMessageBox.information(
                self, "Updated", "MTO Line item updated."
            )
        except Exception as e:
            logger.exception("Failed to edit MTO item")
            QMessageBox.critical(
                self, "Error", f"Update failed:\n{e}"
            )

    def _delete_selected_mto(self):
        rows = self.mto_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select one or more MTO lines to delete."
            )
            return

        ids = [
            int(self.mto_table.item(r.row(), 0).text()) for r in rows
        ]
        if QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(ids)} MTO line requirement(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as s:
                for mid in ids:
                    # ✅ FIXED: SQLAlchemy 2.0
                    m = s.get(MaterialTakeOff, mid)
                    if m:
                        s.delete(m)
            self._refresh_mto()
            QMessageBox.information(
                self, "Deleted", "Selected MTO lines removed."
            )
        except Exception as e:
            logger.exception("Failed to delete MTO lines")
            QMessageBox.critical(
                self, "Error", f"Could not delete:\n{e}"
            )

    # ══════════════════════════════════════════
    #  MATERIAL ISSUANCE
    # ══════════════════════════════════════════
    def _issue_material_to_mto(self):
        rows = self.mto_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(
                self, "Selection",
                "Select an MTO line to issue stock against."
            )
            return

        mto_id = int(self.mto_table.item(rows[0].row(), 0).text())
        mto_data = next(
            (x for x in self._cached_mto if x["id"] == mto_id), None
        )
        if not mto_data:
            return

        # Load available matching stock
        with self.db.session_scope() as s:
            stock_items = (
                s.query(MaterialItem)
                .filter(
                    MaterialItem.project_id == self.project_id,
                    MaterialItem.material_type
                    == mto_data["material_type"],
                    MaterialItem.quantity_available > 0,
                )
                .all()
            )

        dlg = MaterialIssueDialog(
            self, mto_item=mto_data,
            available_stock_items=stock_items,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        issue_data = dlg.get_issue_data()
        stock_id = issue_data["stock_id"]
        qty = issue_data["issue_qty"]

        try:
            with self.db.session_scope() as s:
                # ✅ FIXED: SQLAlchemy 2.0
                stock_rec = s.get(MaterialItem, stock_id)
                if (not stock_rec
                        or (stock_rec.quantity_available or 0) < qty):
                    raise ValueError(
                        "Insufficient available quantity in "
                        "selected stock batch."
                    )
                stock_rec.quantity_available -= qty

                mto_rec = s.get(MaterialTakeOff, mto_id)
                if mto_rec:
                    mto_rec.quantity_issued = (
                        (mto_rec.quantity_issued or 0) + qty
                    )
                    if (mto_rec.quantity_issued
                            >= mto_rec.quantity_required):
                        mto_rec.status = "Fully Issued"
                    else:
                        mto_rec.status = "Partially Issued"

                s.add(ProjectAction(
                    project_id=self.project_id,
                    action_type="MATERIAL_ISSUE",
                    entity_type="MaterialTakeOff",
                    entity_id=mto_id,
                    line_number=mto_data["line_number"],
                    description=(
                        f"Issued {qty} {mto_data['unit']} "
                        f"(Heat: {stock_rec.heat_number}) to Spool "
                        f"{mto_data['spool_number'] or 'Field'}"
                    ),
                    user_name=getattr(
                        self.session, "username", "admin"
                    ),
                ))

            self.refresh()
            QMessageBox.information(
                self, "Material Issued",
                f"Successfully allocated {qty} "
                f"{mto_data['unit']} to Line "
                f"{mto_data['line_number']}."
            )
        except Exception as e:
            logger.exception("Material issue failed")
            QMessageBox.critical(
                self, "Issue Error",
                f"Failed to allocate material:\n{e}"
            )

    # ══════════════════════════════════════════
    #  CONTEXT MENUS
    # ══════════════════════════════════════════
    def _show_stock_context_menu(self, pos):
        rows = self.stock_table.selectionModel().selectedRows()
        if not rows:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 18px; }"
        )

        act_edit = QAction("✏️ Edit Batch Details", self)
        act_edit.triggered.connect(self._edit_stock_item)
        menu.addAction(act_edit)

        act_copy_heat = QAction("📋 Copy Heat Number", self)
        act_copy_heat.triggered.connect(
            lambda: QApplication.clipboard().setText(
                self.stock_table.item(rows[0].row(), 4).text()
            )
        )
        menu.addAction(act_copy_heat)

        menu.addSeparator()

        act_del = QAction("🗑️ Delete Selected", self)
        act_del.triggered.connect(self._delete_selected_stock)
        menu.addAction(act_del)

        menu.exec(self.stock_table.viewport().mapToGlobal(pos))

    def _show_mto_context_menu(self, pos):
        rows = self.mto_table.selectionModel().selectedRows()
        if not rows:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 18px; }"
        )

        act_issue = QAction("⚡ Allocate & Issue Stock", self)
        act_issue.triggered.connect(self._issue_material_to_mto)
        menu.addAction(act_issue)

        act_edit = QAction("✏️ Edit MTO Line", self)
        act_edit.triggered.connect(self._edit_mto_item)
        menu.addAction(act_edit)

        menu.addSeparator()

        act_copy_line = QAction("📋 Copy Piping Line No", self)
        act_copy_line.triggered.connect(
            lambda: QApplication.clipboard().setText(
                self.mto_table.item(rows[0].row(), 1).text()
            )
        )
        menu.addAction(act_copy_line)

        act_del = QAction("🗑️ Delete Selected", self)
        act_del.triggered.connect(self._delete_selected_mto)
        menu.addAction(act_del)

        menu.exec(self.mto_table.viewport().mapToGlobal(pos))

    # ══════════════════════════════════════════
    #  EXPORT
    # ══════════════════════════════════════════
    def _export_stock_csv(self):
        self._export_table_csv(
            self.stock_table, "Warehouse_Stock_Inventory"
        )

    def _export_mto_csv(self):
        self._export_table_csv(
            self.mto_table, "MTO_Bill_of_Quantities_BOQ"
        )

    def _export_table_csv(self, table: QTableWidget, prefix: str):
        if table.rowCount() == 0:
            QMessageBox.warning(
                self, "Export",
                "Table contains no data to export."
            )
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_code = self.proj.currentText().split("–")[0].strip()
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
                f"Report successfully saved to:\n{filename}"
            )
        except Exception as e:
            logger.exception("CSV export failed")
            QMessageBox.critical(
                self, "Export Error",
                f"Could not export CSV file:\n{e}"
            )