# -*- coding: utf-8 -*-
# ui/tabs/ndt_tab.py – PipeAgent
# Non-Destructive Testing (NDT) Quality Control & Requisition Register
#
# Fully redesigned with:
# • Multi-variable Real-time Search & Filter Engine (Method, Result, Line, Inspector)
# • Project Isolation & Automatic Weld Context Loading
# • Dynamic KPI Summary Metric Cards (Total NDTs, Pass Rate %, Defect/Fail Count, Pending Queue)
# • Full CRUD Support (Add, Edit, Delete, Bulk Re-inspection Logging)
# • Color-coded Visual Badges for Methods (RT, UT, PT, MT, PMI) and Results
# • Detailed Inspection Dossier Dialog & Defect Evaluation Breakdown
# • CSV Log Sheet Export Engine & Comprehensive Right-Click Context Menu

from __future__ import annotations

import csv
import logging
import datetime
from pathlib import Path
from typing import Optional, Any

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QTextEdit, QDateEdit, QFrame, QFileDialog,
    QApplication, QMenu, QAbstractItemView, QGroupBox
)
from PyQt6.QtGui import QColor, QFont, QBrush, QCursor, QAction

from db.manager import DatabaseManager
from db.models import Project, Weld, NDTRecord
from security.session import SessionManager
from services.ndt_service import NDTService

# Implementation note.
try:
    from config import NDT_METHODS
except ImportError:
    NDT_METHODS = ["RT (Radiography)", "UT (Ultrasonic)", "PT (Penetrant)", "MT (Magnetic)", "PMI (Material ID)", "Hardness", "PWHT-Hardness"]

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

NDT_RESULT_BADGES = {
    "Pass":    {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Accepted":{"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Fail":    {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Rejected":{"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Pending": {"bg": "#fef3c7", "fg": "#92400e", "icon": "⏳"},
    "NR":      {"bg": "#f1f5f9", "fg": "#475569", "icon": "⏸"},
    "Concession":{"bg": "#ffedd5", "fg": "#9a3412", "icon": "⚠️"},
}
DEFAULT_RESULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}

NDT_METHOD_BADGES = {
    "RT": {"bg": "#f3e8ff", "fg": "#6b21a8"},
    "UT": {"bg": "#e0e7ff", "fg": "#3730a3"},
    "PT": {"bg": "#fce7f3", "fg": "#9d174d"},
    "MT": {"bg": "#e0f2fe", "fg": "#075985"},
    "PMI":{"bg": "#ecfdf5", "fg": "#065f46"},
}

# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

NDT_STYLESHEET = """
    QWidget#ndtTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #112240, stop:1 #1e3c72);
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
    QLineEdit, QComboBox, QDateEdit, QTextEdit {
        padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 12px;
    }
"""

# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class NDTKPICard(QFrame):
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
        else:
            self.val_lbl.setStyleSheet("color: #0f172a; font-size: 19px; font-weight: 800;")


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class NDTRecordDialog(QDialog):
    def __init__(self, parent=None, welds: list = None, existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = existing_data is not None
        self.setWindowTitle("Edit NDT Inspection Record" if self.is_edit else "Register NDT Inspection Result")
        self.setMinimumWidth(500)
        self.setStyleSheet(NDT_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.weld_combo = QComboBox()
        if welds:
            for w in welds:
                self.weld_combo.addItem(f"{w.weld_id} | Line: {w.line_number or 'General'}", w.id)

        self.method_combo = QComboBox()
        self.method_combo.addItems(NDT_METHODS)

        self.result_combo = QComboBox()
        self.result_combo.addItems(["Pass", "Fail", "Pending", "NR", "Concession"])

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())

        self.inspector_edit = QLineEdit()
        self.inspector_edit.setPlaceholderText("Inspector Name or Certification ID")

        self.agency_edit = QLineEdit()
        self.agency_edit.setPlaceholderText("NDT Subcontractor / Agency (e.g. SGS, TUV)")

        self.report_edit = QLineEdit()
        self.report_edit.setPlaceholderText("Official QC Report No (e.g. NDT-RT-2024-001)")

        self.defect_edit = QLineEdit()
        self.defect_edit.setPlaceholderText("Defect Type if rejected (e.g. Lack of Penetration, Porosity)")

        self.remarks_edit = QTextEdit()
        self.remarks_edit.setPlaceholderText("Evaluation details, film density, sensitivity, or repair instructions...")
        self.remarks_edit.setMaximumHeight(70)

        form.addRow("Joint / Weld ID *:", self.weld_combo)
        form.addRow("NDT Method *:", self.method_combo)
        form.addRow("Quality Result *:", self.result_combo)
        form.addRow("Inspection Date:", self.date_edit)
        form.addRow("Qualified Inspector:", self.inspector_edit)
        form.addRow("NDT Agency / Lab:", self.agency_edit)
        form.addRow("Inspection Report No *:", self.report_edit)
        form.addRow("Observed Defects:", self.defect_edit)
        form.addRow("Evaluation Remarks:", self.remarks_edit)
        layout.addLayout(form)

        if self.is_edit and existing_data:
            # Implementation note.
            w_pk = existing_data.get("weld_pk")
            for i in range(self.weld_combo.count()):
                if self.weld_combo.itemData(i) == w_pk:
                    self.weld_combo.setCurrentIndex(i)
                    break
            self.weld_combo.setEnabled(False)  # Implementation note.
            self.method_combo.setCurrentText(existing_data.get("ndt_method", NDT_METHODS[0]))
            self.result_combo.setCurrentText(existing_data.get("result", "Pass"))
            
            d_val = existing_data.get("inspection_date")
            if isinstance(d_val, datetime.date):
                self.date_edit.setDate(QDate(d_val.year, d_val.month, d_val.day))
                
            self.inspector_edit.setText(existing_data.get("inspector_id", ""))
            self.agency_edit.setText(existing_data.get("agency", ""))
            self.report_edit.setText(existing_data.get("report_number", ""))
            self.defect_edit.setText(existing_data.get("defect_type", ""))
            self.remarks_edit.setPlainText(existing_data.get("remarks", ""))

        btns = QHBoxLayout()
        btn_save = QPushButton("Save NDT Record")
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
        if not self.weld_combo.currentData():
            QMessageBox.warning(self, "Validation", "Select a valid weld joint.")
            return
        if not self.report_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Inspection Report Number is required.")
            self.report_edit.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        qd = self.date_edit.date()
        return {
            "weld_pk": self.weld_combo.currentData(),
            "ndt_method": self.method_combo.currentText(),
            "result": self.result_combo.currentText(),
            "inspection_date": datetime.date(qd.year(), qd.month(), qd.day()),
            "inspector_id": self.inspector_edit.text().strip(),
            "agency": self.agency_edit.text().strip(),
            "report_number": self.report_edit.text().strip(),
            "defect_type": self.defect_edit.text().strip(),
            "remarks": self.remarks_edit.toPlainText().strip(),
        }


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class NDTDetailDialog(QDialog):
    def __init__(self, parent=None, record: dict = None):
        super().__init__(parent)
        self.setWindowTitle(f"🔍 NDT Dossier – Report: {record.get('report_number', 'N/A')}")
        self.setMinimumSize(560, 440)
        self.setStyleSheet(NDT_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hdr = QLabel(f"📋 Inspection Dossier: {record.get('report_number', 'N/A')}")
        hdr.setStyleSheet("font-size: 16px; font-weight: bold; color: #1e3c72;")
        layout.addWidget(hdr)

        info_box = QGroupBox("Inspection & Evaluation Details")
        info_grid = QGridLayout(info_box)
        info_grid.setSpacing(8)

        details = [
            ("Target Weld ID:", record.get("weld_id", "—")),
            ("Piping Line Number:", record.get("line_number", "—")),
            ("NDT Method:", record.get("ndt_method", "—")),
            ("Quality Result:", record.get("result", "Pending")),
            ("Inspection Date:", str(record.get("inspection_date") or "—")),
            ("Qualified Inspector:", record.get("inspector_id", "—")),
            ("NDT Subcontractor:", record.get("agency", "—")),
            ("Official Report No:", record.get("report_number", "—")),
            ("Identified Defects:", record.get("defect_type", "None")),
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

        # Implementation note.
        rem_box = QGroupBox("Evaluation Findings & Quality Remarks")
        rem_lay = QVBoxLayout(rem_box)
        txt_rem = QTextEdit()
        txt_rem.setReadOnly(True)
        txt_rem.setPlainText(record.get("remarks", "") or "No specific remarks or non-conformances noted.")
        rem_lay.addWidget(txt_rem)
        layout.addWidget(rem_box)

        btn_close = QPushButton("Close Dossier")
        btn_close.setObjectName("secondaryBtn")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class NDTTab(QWidget):
    def __init__(self, db: DatabaseManager, session: SessionManager):
        super().__init__()
        self.setObjectName("ndtTab")
        self.db = db
        self.session = session
        self.ndt_service = NDTService(db)
        self.project_id: Optional[int] = None
        self._cached_records: list[dict] = []

        self._build_ui()
        self.setStyleSheet(NDT_STYLESHEET)
        self._load_projects()

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
        t = QLabel("🔍 NDT Quality Control & Examination Register")
        t.setObjectName("mainTitle")
        s = QLabel("Non-Destructive Testing Management: Radiography, Ultrasonic, Penetrant, Magnetic, and Hardness QC Verification.")
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
        self.proj_combo.currentIndexChanged.connect(self._on_project_changed)
        proj_box.addWidget(self.proj_combo)

        btn_r = QPushButton("🔄 Refresh")
        btn_r.setObjectName("secondaryBtn")
        btn_r.clicked.connect(self.refresh)
        proj_box.addWidget(btn_r)
        hdr_lay.addLayout(proj_box)

        root.addWidget(header_card)

        # Implementation note.
        kpi_lay = QHBoxLayout()
        kpi_lay.setSpacing(8)

        self.kpi_total = NDTKPICard("Total Tests Logged", "🧪", "#3b82f6")
        self.kpi_passed = NDTKPICard("Accepted / Passed", "✅", "#10b981")
        self.kpi_rate = NDTKPICard("NDT Pass Rate", "📈", "#059669")
        self.kpi_failed = NDTKPICard("Defects / Repairs", "❌", "#ef4444")
        self.kpi_pending = NDTKPICard("Pending Evaluation", "⏳", "#f59e0b")

        for k in [self.kpi_total, self.kpi_passed, self.kpi_rate, self.kpi_failed, self.kpi_pending]:
            kpi_lay.addWidget(k)
        root.addLayout(kpi_lay)

        # Implementation note.
        filter_card = QFrame()
        filter_card.setStyleSheet("background: white; border: 1px solid #cbd5e1; border-radius: 8px;")
        filter_lay = QHBoxLayout(filter_card)
        filter_lay.setContentsMargins(10, 8, 10, 8)
        filter_lay.setSpacing(8)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 Search Weld ID, Line No, Report No, Inspector, Remarks...")
        self.txt_search.textChanged.connect(self._apply_filters)
        filter_lay.addWidget(self.txt_search, 1)

        self.cmb_filter_method = QComboBox()
        self.cmb_filter_method.addItem("All Methods", None)
        for m in NDT_METHODS:
            self.cmb_filter_method.addItem(m, m)
        self.cmb_filter_method.currentIndexChanged.connect(self._apply_filters)
        filter_lay.addWidget(self.cmb_filter_method)

        self.cmb_filter_result = QComboBox()
        self.cmb_filter_result.addItem("All Results", None)
        self.cmb_filter_result.addItems(["Pass", "Fail", "Pending", "NR", "Concession"])
        self.cmb_filter_result.currentIndexChanged.connect(self._apply_filters)
        filter_lay.addWidget(self.cmb_filter_result)

        btn_add = QPushButton("➕ Record NDT Result")
        btn_add.setObjectName("primaryBtn")
        btn_add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_add.clicked.connect(self._on_add)
        filter_lay.addWidget(btn_add)

        btn_exp = QPushButton("📥 Export NDT Log")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(self._export_ndt_csv)
        filter_lay.addWidget(btn_exp)

        btn_del = QPushButton("🗑️ Delete")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete_selected)
        filter_lay.addWidget(btn_del)

        root.addWidget(filter_card)

        # Implementation note.
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "ID", "Weld ID", "Piping Line No", "Method",
            "Quality Result", "Inspection Date", "Inspector", "Report No.", "Remarks / Defect"
        ])
        self.table.setColumnHidden(0, True) # Implementation note.
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self._on_row_double_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        root.addWidget(self.table, 1)

    # ══════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════

    def _load_projects(self):
        self.proj_combo.blockSignals(True)
        self.proj_combo.clear()
        try:
            with self.db.session_scope() as s:
                for p in s.query(Project).order_by(Project.project_code):
                    self.proj_combo.addItem(f"{p.project_code} – {p.title}", p.id)
        except Exception as e:
            logger.exception("Failed to load projects in NDTTab")

        self.proj_combo.blockSignals(False)
        if self.proj_combo.count():
            self._on_project_changed()

    def _on_project_changed(self):
        self.project_id = self.proj_combo.currentData()
        self.refresh()

    def refresh(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._cached_records = []

        if not self.project_id:
            self._update_kpis(0, 0, 0, 0)
            return

        try:
            with self.db.session_scope() as session:
                records = (
                    session.query(NDTRecord, Weld)
                    .join(Weld, NDTRecord.weld_id_fk == Weld.id)
                    .filter(Weld.project_id == self.project_id)
                    .order_by(NDTRecord.inspection_date.desc(), NDTRecord.id.desc())
                    .all()
                )

                pass_cnt = fail_cnt = pend_cnt = 0

                for rec, weld in records:
                    res_val = rec.result or "Pending"
                    if res_val in ("Pass", "Accepted"):
                        pass_cnt += 1
                    elif res_val in ("Fail", "Rejected"):
                        fail_cnt += 1
                    elif res_val == "Pending":
                        pend_cnt += 1

                    self._cached_records.append({
                        "id": rec.id,
                        "weld_pk": weld.id,
                        "weld_id": weld.weld_id,
                        "line_number": weld.line_number or "General",
                        "ndt_method": rec.ndt_method or "RT",
                        "result": res_val,
                        "inspection_date": rec.inspection_date,
                        "inspector_id": rec.inspector_id or "",
                        "agency": getattr(rec, "agency", "") or "QC Lab",
                        "report_number": rec.report_number or "",
                        "defect_type": getattr(rec, "defect_type", "") or "",
                        "remarks": rec.remarks or "",
                    })

                self._update_kpis(len(records), pass_cnt, fail_cnt, pend_cnt)
                self._apply_filters()

        except Exception as e:
            logger.exception("NDT refresh failed")
            QMessageBox.warning(self, "Error", f"Failed to load NDT records:\n{e}")

    def _update_kpis(self, total: int, passed: int, failed: int, pending: int):
        rate = (passed / total * 100) if total > 0 else 0.0
        self.kpi_total.set_value(str(total))
        self.kpi_passed.set_value(str(passed), highlight="green" if passed == total and total > 0 else None)
        self.kpi_rate.set_value(f"{rate:.1f}%", highlight="green" if rate >= 95.0 else ("red" if rate < 85.0 and total > 0 else None))
        self.kpi_failed.set_value(str(failed), highlight="red" if failed > 0 else "green")
        self.kpi_pending.set_value(str(pending), highlight="amber" if pending > 0 else None)

    def _apply_filters(self):
        query = self.txt_search.text().strip().lower()
        method_f = self.cmb_filter_method.currentData()
        result_f = self.cmb_filter_result.currentText() if self.cmb_filter_result.currentIndex() > 0 else None

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for r in self._cached_records:
            if method_f and r["ndt_method"] != method_f:
                continue

            if result_f and r["result"] != result_f:
                continue

            if query:
                combined = f"{r['weld_id']} {r['line_number']} {r['report_number']} {r['inspector_id']} {r['remarks']} {r['defect_type']}".lower()
                if query not in combined:
                    continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(str(r["id"])))
            self.table.setItem(row, 1, QTableWidgetItem(r["weld_id"]))
            self.table.setItem(row, 2, QTableWidgetItem(r["line_number"]))

            # Implementation note.
            method_item = QTableWidgetItem(r["ndt_method"])
            self.table.setItem(row, 3, method_item)

            # Implementation note.
            res_item = QTableWidgetItem(r["result"])
            badge = NDT_RESULT_BADGES.get(r["result"], DEFAULT_RESULT_BADGE)
            res_item.setText(f"{badge['icon']} {r['result']}")
            res_item.setBackground(QBrush(QColor(badge["bg"])))
            res_item.setForeground(QBrush(QColor(badge["fg"])))
            f = res_item.font()
            f.setBold(True)
            res_item.setFont(f)
            self.table.setItem(row, 4, res_item)

            d_str = r["inspection_date"].strftime("%Y-%m-%d") if r["inspection_date"] else "—"
            self.table.setItem(row, 5, QTableWidgetItem(d_str))
            self.table.setItem(row, 6, QTableWidgetItem(r["inspector_id"]))
            self.table.setItem(row, 7, QTableWidgetItem(r["report_number"]))
            self.table.setItem(row, 8, QTableWidgetItem(r["remarks"]))

        self.table.setSortingEnabled(True)

    # ══════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════

    def _get_project_welds(self) -> list:
        with self.db.session_scope() as session:
            welds = (
                session.query(Weld)
                .filter(Weld.project_id == self.project_id)
                .order_by(Weld.weld_id)
                .all()
            )
            return [type("W", (), {"id": w.id, "weld_id": w.weld_id, "line_number": w.line_number})() for w in welds]

    def _on_add(self):
        if not self.project_id:
            QMessageBox.information(self, "Info", "Select a project first.")
            return

        weld_list = self._get_project_welds()
        if not weld_list:
            QMessageBox.information(self, "Info", "No weld joints found in this project. Register welds first in the Joints/WJC tab.")
            return

        dlg = NDTRecordDialog(self, welds=weld_list)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        try:
            record = self.ndt_service.add_record(
                weld_pk=data["weld_pk"],
                ndt_method=data["ndt_method"],
                inspection_date=data["inspection_date"],
                inspector_id=data["inspector_id"],
                result=data["result"],
                report_number=data["report_number"],
                remarks=data["remarks"],
            )
            if record:
                self.refresh()
                QMessageBox.information(self, "Success", f"NDT Report {data['report_number']} registered successfully.")
            else:
                QMessageBox.warning(self, "Error", "Could not register NDT record (License limit or duplicate entry).")
        except Exception as e:
            logger.exception("Failed to add NDT record")
            QMessageBox.critical(self, "Error", f"Could not save record:\n{e}")

    def _edit_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "Selection", "Select an NDT record to edit.")
            return

        rec_id = int(self.table.item(rows[0].row(), 0).text())
        rec_data = next((x for x in self._cached_records if x["id"] == rec_id), None)
        if not rec_data:
            return

        weld_list = self._get_project_welds()
        dlg = NDTRecordDialog(self, welds=weld_list, existing_data=rec_data)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        try:
            with self.db.session_scope() as session:
                rec = session.query(NDTRecord).get(rec_id)
                if rec:
                    rec.ndt_method = data["ndt_method"]
                    rec.result = data["result"]
                    rec.inspection_date = data["inspection_date"]
                    rec.inspector_id = data["inspector_id"]
                    rec.report_number = data["report_number"]
                    rec.remarks = data["remarks"]
                    if hasattr(rec, "agency"):
                        rec.agency = data.get("agency", "")

            self.refresh()
            QMessageBox.information(self, "Updated", f"NDT Record {data['report_number']} updated successfully.")
        except Exception as e:
            logger.exception("Failed to update NDT record")
            QMessageBox.critical(self, "Error", f"Update failed:\n{e}")

    def _delete_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "Selection", "Select one or more NDT records to delete.")
            return

        rec_ids = [int(self.table.item(r.row(), 0).text()) for r in rows]
        rep_nos = [self.table.item(r.row(), 7).text() for r in rows]

        if QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(rec_ids)} NDT record(s)?\n\nReports: {', '.join(rep_nos[:5])}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as session:
                for r_id in rec_ids:
                    rec = session.query(NDTRecord).get(r_id)
                    if rec:
                        session.delete(rec)

            self.refresh()
            QMessageBox.information(self, "Deleted", "Selected NDT record(s) removed from register.")
        except Exception as e:
            logger.exception("Failed to delete NDT records")
            QMessageBox.critical(self, "Error", f"Could not delete records:\n{e}")

    # ══════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════

    def _on_row_double_click(self, index):
        row = index.row()
        rec_id = int(self.table.item(row, 0).text())
        rec_data = next((x for x in self._cached_records if x["id"] == rec_id), None)
        if rec_data:
            dlg = NDTDetailDialog(self, rec_data)
            dlg.exec()

    def _show_context_menu(self, pos):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: white; border: 1px solid #cbd5e1; } QMenu::item { padding: 6px 18px; }")

        act_dossier = QAction("🔍 View Full Inspection Dossier", self)
        act_dossier.triggered.connect(lambda: self._on_row_double_click(self.table.currentIndex()))
        menu.addAction(act_dossier)

        act_edit = QAction("✏️ Edit Inspection Record", self)
        act_edit.triggered.connect(self._edit_selected)
        menu.addAction(act_edit)

        menu.addSeparator()

        act_pass = QAction("✅ Mark as Passed", self)
        act_pass.triggered.connect(lambda: self._quick_update_result("Pass"))
        menu.addAction(act_pass)

        act_fail = QAction("❌ Mark as Rejected / Fail", self)
        act_fail.triggered.connect(lambda: self._quick_update_result("Fail"))
        menu.addAction(act_fail)

        menu.addSeparator()

        act_copy = QAction("📋 Copy Report Number", self)
        act_copy.triggered.connect(self._copy_selected_report_no)
        menu.addAction(act_copy)

        act_del = QAction("🗑️ Delete Selected", self)
        act_del.triggered.connect(self._delete_selected)
        menu.addAction(act_del)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _quick_update_result(self, result_text: str):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return

        rec_ids = [int(self.table.item(r.row(), 0).text()) for r in rows]
        try:
            with self.db.session_scope() as session:
                for r_id in rec_ids:
                    rec = session.query(NDTRecord).get(r_id)
                    if rec:
                        rec.result = result_text

            self.refresh()
        except Exception as e:
            logger.exception("Failed to quick update NDT result")
            QMessageBox.critical(self, "Error", f"Failed to update result:\n{e}")

    def _copy_selected_report_no(self):
        row = self.table.currentRow()
        if row >= 0:
            rep_no = self.table.item(row, 7).text()
            QApplication.clipboard().setText(rep_no)

    def _export_ndt_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "Export", "No NDT records available to export.")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_code = self.proj_combo.currentText().split("–")[0].strip()
        default_name = f"NDT_QC_LogSheet_{proj_code}_{timestamp}.csv"

        filename, _ = QFileDialog.getSaveFileName(self, "Export NDT Examination Log Sheet", default_name, "CSV Files (*.csv)")
        if not filename:
            return

        try:
            with open(filename, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                headers = [self.table.horizontalHeaderItem(c).text() for c in range(1, self.table.columnCount())]
                writer.writerow(headers)

                for r in range(self.table.rowCount()):
                    if not self.table.isRowHidden(r):
                        row_vals = [self.table.item(r, c).text().strip() if self.table.item(r, c) else "" for c in range(1, self.table.columnCount())]
                        writer.writerow(row_vals)

            QMessageBox.information(self, "Export Complete", f"NDT Log Sheet exported successfully to:\n{filename}")
        except Exception as e:
            logger.exception("Failed to export NDT CSV")
            QMessageBox.critical(self, "Export Error", f"Could not create CSV file:\n{e}")