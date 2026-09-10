# -*- coding: utf-8 -*-
# ui/tabs/smart_entry_tab.py – PipeAgent 5.3.0
# Smart Forms & Ultra-Fast Field Data Capture with Cascading Lookups
#
# Workflows Supported:
# 1. 🔥 Weld Production & Visual QC
# 2. 🔧 Joint Fit-Up Verification
# 3. 🧪 NDT Examination Record (RT, UT, PT, MT, PMI, Hardness)
# 4. 🚛 Spool Site Erection & Torquing Milestone
# 5. 📦 Material Heat Allocation & Receiving (MRR)
# 6. ⏱️ Work Front Daily Progress & Hours Tracker
from __future__ import annotations

import logging
import datetime
from datetime import timezone
from typing import Optional

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QDoubleSpinBox, QTextEdit,
    QGroupBox, QMessageBox, QFormLayout, QDateEdit, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QCheckBox, QAbstractItemView, QApplication, QStackedWidget,
)
from PyQt6.QtGui import QColor, QBrush, QCursor

from db.manager import DatabaseManager
from db.models import (
    Project, LineListItem, Spool, Weld, NDTRecord,
    MaterialItem, WorkFront, ProductivitySnapshot,
)
from security.session import SessionManager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  UTIL
# ─────────────────────────────────────────────
def _utcnow():
    """Naive UTC — replacement for deprecated datetime.utcnow()."""
    return datetime.datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────
#  ENTRY MODES & ICONS
# ─────────────────────────────────────────────
ENTRY_MODES = [
    "Weld Production & Visual QC",
    "Fit-Up Clearance Inspection",
    "NDT Examination Logging",
    "Spool Field Installation",
    "Material Receiving & Heat Log",
    "Work Front Daily Progress",
]

MODE_ICONS = {
    "Weld Production & Visual QC": "🔥",
    "Fit-Up Clearance Inspection": "🔧",
    "NDT Examination Logging": "🧪",
    "Spool Field Installation": "🚛",
    "Material Receiving & Heat Log": "📦",
    "Work Front Daily Progress": "⏱️",
}


# ─────────────────────────────────────────────
#  STYLESHEET
# ─────────────────────────────────────────────
SMART_ENTRY_STYLESHEET = """
    QWidget#smartEntryTab {
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
    QFrame#contextBanner {
        background: #f0fdf4; border: 1px solid #bbf7d0;
        border-radius: 8px; padding: 10px;
    }
    QGroupBox {
        font-size: 12px; font-weight: 800; color: #1e293b;
        border: 2px solid #cbd5e1; border-radius: 8px;
        margin-top: 10px; padding-top: 14px; background: white;
    }
    QGroupBox::title {
        subcontrol-origin: margin; subcontrol-position: top left;
        left: 10px; padding: 0 4px; background: white;
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
            stop:0 #10b981, stop:1 #059669);
        color: white; border: none; padding: 10px 20px;
        border-radius: 6px; font-weight: 800; font-size: 13px;
    }
    QPushButton#primaryBtn:hover { background: #047857; }
    QPushButton#secondaryBtn {
        background: white; color: #334155; border: 1px solid #cbd5e1;
        padding: 8px 16px; border-radius: 6px; font-weight: 600;
    }
    QPushButton#secondaryBtn:hover {
        background: #f8fafc; border-color: #3b82f6; color: #3b82f6;
    }
    QLineEdit, QComboBox, QDoubleSpinBox, QDateEdit, QTextEdit {
        padding: 6px 10px; border: 1px solid #cbd5e1;
        border-radius: 6px; font-size: 12px; background: white;
    }
    QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus,
    QDateEdit:focus, QTextEdit:focus {
        border-color: #3b82f6; background: #f8faff;
    }
"""


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class SmartEntryTab(QWidget):
    def __init__(self, db: DatabaseManager, session: SessionManager):
        super().__init__()
        self.setObjectName("smartEntryTab")
        self.db = db
        self.session = session

        self._build()
        self.setStyleSheet(SMART_ENTRY_STYLESHEET)
        self._load_projects()

    # ── UI BUILD ─────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Header
        header_card = QFrame()
        header_card.setObjectName("headerCard")
        hdr_lay = QHBoxLayout(header_card)
        hdr_lay.setContentsMargins(14, 10, 14, 10)

        title_v = QVBoxLayout()
        t = QLabel("⚡ Smart Field Entry & Rapid QC Capture Hub")
        t.setObjectName("mainTitle")
        s = QLabel(
            "Cascading Hierarchy: Project → Line → ISO → Spool → Weld. "
            "Existing specifications are auto-populated automatically."
        )
        s.setObjectName("subTitle")
        title_v.addWidget(t)
        title_v.addWidget(s)
        hdr_lay.addLayout(title_v, 1)

        btn_ref_all = QPushButton("🔄 Reset Lookups")
        btn_ref_all.setObjectName("secondaryBtn")
        btn_ref_all.clicked.connect(self._load_projects)
        hdr_lay.addWidget(btn_ref_all)
        root.addWidget(header_card)

        # Hierarchy selector
        nav_box = QGroupBox(
            "📍 STEP 1: SELECT ENGINEERING TARGET HIERARCHY"
        )
        nav_lay = QHBoxLayout(nav_box)
        nav_lay.setSpacing(8)

        p_box = QVBoxLayout()
        p_box.addWidget(QLabel("<b>1. Project:</b>"))
        self.project = QComboBox()
        self.project.setMinimumWidth(180)
        p_box.addWidget(self.project)
        nav_lay.addLayout(p_box, 2)

        l_box = QVBoxLayout()
        l_box.addWidget(QLabel("<b>2. Line Number:</b>"))
        self.line = QComboBox()
        self.line.setEditable(True)
        self.line.setMinimumWidth(160)
        l_box.addWidget(self.line)
        nav_lay.addLayout(l_box, 2)

        i_box = QVBoxLayout()
        i_box.addWidget(QLabel("<b>3. ISO Drawing:</b>"))
        self.iso = QComboBox()
        self.iso.setEditable(True)
        self.iso.setMinimumWidth(140)
        i_box.addWidget(self.iso)
        nav_lay.addLayout(i_box, 2)

        s_box = QVBoxLayout()
        s_box.addWidget(QLabel("<b>4. Spool No:</b>"))
        self.spool = QComboBox()
        self.spool.setEditable(True)
        self.spool.setMinimumWidth(130)
        s_box.addWidget(self.spool)
        nav_lay.addLayout(s_box, 2)

        w_box = QVBoxLayout()
        w_box.addWidget(QLabel("<b>5. Joint ID:</b>"))
        self.weld = QComboBox()
        self.weld.setEditable(True)
        self.weld.setMinimumWidth(130)
        w_box.addWidget(self.weld)
        nav_lay.addLayout(w_box, 2)

        root.addWidget(nav_box)

        # Context banner
        self.context_banner = QFrame()
        self.context_banner.setObjectName("contextBanner")
        banner_lay = QHBoxLayout(self.context_banner)
        banner_lay.setContentsMargins(10, 6, 10, 6)

        self.lbl_context = QLabel(
            "💡 <b>Engineering Target:</b> "
            "<span style='color:#64748b;'>Select hierarchy above "
            "to load auto-filled specifications...</span>"
        )
        self.lbl_context.setStyleSheet(
            "font-size: 12px; color: #166534;"
        )
        banner_lay.addWidget(self.lbl_context, 1)

        self.chk_keep_context = QCheckBox(
            "📌 Lock Line / Spool for Rapid Batch Entry"
        )
        self.chk_keep_context.setChecked(True)
        self.chk_keep_context.setStyleSheet(
            "font-weight: bold; color: #166534;"
        )
        banner_lay.addWidget(self.chk_keep_context)
        root.addWidget(self.context_banner)

        # Splitter: form / log
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)

        # Left panel — form
        left_box = QGroupBox("📝 STEP 2: CAPTURE FIELD DATA")
        left_lay = QVBoxLayout(left_box)
        left_lay.setContentsMargins(10, 12, 10, 10)
        left_lay.setSpacing(8)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("<b>Workflow Action:</b>"))
        self.cmb_mode = QComboBox()
        for m in ENTRY_MODES:
            self.cmb_mode.addItem(f"{MODE_ICONS.get(m, '⚡')} {m}", m)
        self.cmb_mode.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.cmb_mode, 1)
        left_lay.addLayout(mode_row)

        # Form stack — 6 forms, one per mode
        self.form_stack = QStackedWidget()
        self.form_stack.addWidget(self._build_weld_form())        # 0
        self.form_stack.addWidget(self._build_fitup_form())       # 1
        self.form_stack.addWidget(self._build_ndt_form())         # 2
        self.form_stack.addWidget(self._build_erection_form())    # 3
        self.form_stack.addWidget(self._build_material_form())    # 4
        self.form_stack.addWidget(self._build_progress_form())    # 5
        left_lay.addWidget(self.form_stack, 1)

        btn_bar = QHBoxLayout()
        self.btn_save = QPushButton("💾 Save & Commit Entry")
        self.btn_save.setObjectName("primaryBtn")
        self.btn_save.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.btn_save.clicked.connect(self.save)
        btn_bar.addWidget(self.btn_save, 2)

        self.btn_clear = QPushButton("Clear Fields")
        self.btn_clear.setObjectName("secondaryBtn")
        self.btn_clear.clicked.connect(self.clear_entry)
        btn_bar.addWidget(self.btn_clear, 1)
        left_lay.addLayout(btn_bar)

        splitter.addWidget(left_box)

        # Right panel — recent entries
        right_box = QGroupBox(
            "📋 RECENT ENTRIES & FIELD ACTIVITY LOG"
        )
        right_lay = QVBoxLayout(right_box)
        right_lay.setContentsMargins(8, 12, 8, 8)
        right_lay.setSpacing(6)

        self.recent_table = QTableWidget(0, 6)
        self.recent_table.setHorizontalHeaderLabels([
            "Time", "Workflow Type", "Line / Target",
            "Joint / Item", "Status / Result", "Recorded By",
        ])
        self.recent_table.setAlternatingRowColors(True)
        self.recent_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.recent_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        right_lay.addWidget(self.recent_table)

        btn_clear_log = QPushButton("Clear Session Table")
        btn_clear_log.setObjectName("secondaryBtn")
        btn_clear_log.clicked.connect(
            lambda: self.recent_table.setRowCount(0)
        )
        right_lay.addWidget(btn_clear_log)

        splitter.addWidget(right_box)
        splitter.setSizes([560, 640])
        root.addWidget(splitter, 1)

        # Cascade signals
        self.project.currentIndexChanged.connect(self.load_lines)
        self.line.currentIndexChanged.connect(self.load_iso)
        self.iso.currentIndexChanged.connect(self.load_spools)
        self.spool.currentIndexChanged.connect(self.load_welds)
        self.weld.currentIndexChanged.connect(self.autofill_context)

    # ══════════════════════════════════════════════════════
    #  FORM BUILDERS
    # ══════════════════════════════════════════════════════
    def _build_weld_form(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(8)

        self.weld_welder = QLineEdit()
        self.weld_welder.setPlaceholderText(
            "Welder Stamp / ID (e.g. W-04)"
        )
        self.weld_wps = QLineEdit()
        self.weld_wps.setPlaceholderText(
            "Qualified WPS (e.g. WPS-CS-01)"
        )
        self.weld_status = QComboBox()
        self.weld_status.addItems([
            "Welded", "Accepted", "Visual Pass", "Visual Reject",
            "Pending NDT",
        ])
        self.weld_date = QDateEdit(QDate.currentDate())
        self.weld_date.setCalendarPopup(True)
        self.weld_remarks = QTextEdit()
        self.weld_remarks.setMaximumHeight(65)
        self.weld_remarks.setPlaceholderText(
            "Visual inspection findings, preheat, interpass notes..."
        )

        form.addRow("Welder Stamp / ID *:", self.weld_welder)
        form.addRow("WPS Specification *:", self.weld_wps)
        form.addRow("Visual / QC Status *:", self.weld_status)
        form.addRow("Welding Date:", self.weld_date)
        form.addRow("QC Remarks:", self.weld_remarks)
        return w

    def _build_fitup_form(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(8)

        self.fit_root = QDoubleSpinBox()
        self.fit_root.setRange(0, 50)
        self.fit_root.setValue(3.2)
        self.fit_root.setSuffix(" mm")

        self.fit_hilow = QDoubleSpinBox()
        self.fit_hilow.setRange(0, 50)
        self.fit_hilow.setValue(0.8)
        self.fit_hilow.setSuffix(" mm")

        self.fit_inspector = QLineEdit()
        self.fit_inspector.setPlaceholderText("QC Inspector Name / Stamp")

        self.fit_result = QComboBox()
        self.fit_result.addItems([
            "Accepted", "Rejected", "Pending Re-alignment",
        ])

        self.fit_date = QDateEdit(QDate.currentDate())
        self.fit_date.setCalendarPopup(True)

        self.fit_remarks = QTextEdit()
        self.fit_remarks.setMaximumHeight(65)

        form.addRow("Root Gap Measured *:", self.fit_root)
        form.addRow("Hi-Low Alignment *:", self.fit_hilow)
        form.addRow("Fit-up Inspector:", self.fit_inspector)
        form.addRow("Fit-up Quality Result:", self.fit_result)
        form.addRow("Inspection Date:", self.fit_date)
        form.addRow("Remarks:", self.fit_remarks)
        return w

    def _build_ndt_form(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(8)

        self.ndt_method = QComboBox()
        self.ndt_method.addItems([
            "RT (Radiography)", "UT (Ultrasonic)",
            "PT (Liquid Penetrant)", "MT (Magnetic Particle)",
            "PMI (Material ID)", "Hardness",
        ])

        self.ndt_result = QComboBox()
        self.ndt_result.addItems([
            "Pass", "Fail", "Pending Film Review", "Concession",
        ])

        self.ndt_report_no = QLineEdit()
        self.ndt_report_no.setPlaceholderText("e.g. NDT-RT-2024-101")

        self.ndt_inspector = QLineEdit()
        self.ndt_inspector.setPlaceholderText(
            "Qualified Level II Inspector / Lab"
        )

        self.ndt_date = QDateEdit(QDate.currentDate())
        self.ndt_date.setCalendarPopup(True)

        self.ndt_remarks = QTextEdit()
        self.ndt_remarks.setMaximumHeight(65)

        form.addRow("NDT Examination Method *:", self.ndt_method)
        form.addRow("Evaluation Result *:", self.ndt_result)
        form.addRow("QC Report Document No *:", self.ndt_report_no)
        form.addRow("Certified Inspector:", self.ndt_inspector)
        form.addRow("Inspection Date:", self.ndt_date)
        form.addRow("Film Density / Defect Notes:", self.ndt_remarks)
        return w

    def _build_erection_form(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(8)

        self.erect_status = QComboBox()
        self.erect_status.addItems([
            "Installed", "Released to Site", "Tested",
            "Torqued & Aligned",
        ])

        self.erect_date = QDateEdit(QDate.currentDate())
        self.erect_date.setCalendarPopup(True)

        self.erect_location = QLineEdit()
        self.erect_location.setPlaceholderText(
            "Plant Grid / Structure Level (e.g. Level +12.50)"
        )

        self.erect_remarks = QTextEdit()
        self.erect_remarks.setMaximumHeight(75)

        form.addRow("Spool Erection Milestone *:", self.erect_status)
        form.addRow("Installation Date:", self.erect_date)
        form.addRow("Structure / Elevation Ref:", self.erect_location)
        form.addRow("Erection Remarks:", self.erect_remarks)
        return w

    def _build_material_form(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(8)

        self.mat_type = QComboBox()
        self.mat_type.addItems([
            "Pipe", "Elbow", "Tee", "Reducer", "Flange",
            "Valve", "Gasket", "Stud Bolt", "Olet",
        ])

        self.mat_grade = QLineEdit()
        self.mat_grade.setPlaceholderText(
            "Material Spec / Grade (e.g. ASTM A106 Gr.B)"
        )

        self.mat_size = QLineEdit()
        self.mat_size.setPlaceholderText(
            'Nominal Size (e.g. 6" SCH 40)'
        )

        self.mat_heat = QLineEdit()
        self.mat_heat.setPlaceholderText(
            "Manufacturer Heat / Melt Number *"
        )

        self.mat_qty = QDoubleSpinBox()
        self.mat_qty.setRange(0.001, 100000)
        self.mat_qty.setValue(1.0)

        self.mat_unit = QLineEdit("EA")

        self.mat_mtr = QCheckBox(
            "MTR 3.1 Mill Certificate Verified & Attached"
        )
        self.mat_mtr.setChecked(True)

        form.addRow("Commodity Type *:", self.mat_type)
        form.addRow("Material Grade *:", self.mat_grade)
        form.addRow("Nominal Size:", self.mat_size)
        form.addRow("Heat / Batch No *:", self.mat_heat)
        form.addRow("Quantity Received:", self.mat_qty)
        form.addRow("Unit of Measurement:", self.mat_unit)
        form.addRow("Compliance:", self.mat_mtr)
        return w

    def _build_progress_form(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(8)

        self.prog_front = QLineEdit()
        self.prog_front.setPlaceholderText(
            "Work Front Code (e.g. WF-UNIT100-PIPE)"
        )

        self.prog_qty = QDoubleSpinBox()
        self.prog_qty.setRange(0, 100000)
        self.prog_qty.setValue(12.5)
        self.prog_qty.setSuffix(" Dia-Inch / Qty")

        self.prog_actual_hrs = QDoubleSpinBox()
        self.prog_actual_hrs.setRange(0, 500)
        self.prog_actual_hrs.setValue(8.0)
        self.prog_actual_hrs.setSuffix(" Hrs")

        self.prog_prod_hrs = QDoubleSpinBox()
        self.prog_prod_hrs.setRange(0, 500)
        self.prog_prod_hrs.setValue(7.0)
        self.prog_prod_hrs.setSuffix(" Hrs")

        self.prog_idle_hrs = QDoubleSpinBox()
        self.prog_idle_hrs.setRange(0, 500)
        self.prog_idle_hrs.setValue(1.0)
        self.prog_idle_hrs.setSuffix(" Hrs")

        self.prog_notes = QTextEdit()
        self.prog_notes.setMaximumHeight(65)
        self.prog_notes.setPlaceholderText(
            "Daily accomplishments, crew constraints, delays..."
        )

        form.addRow("Target Work Front *:", self.prog_front)
        form.addRow("Progress Quantity Done:", self.prog_qty)
        form.addRow("Total Shift Hours:", self.prog_actual_hrs)
        form.addRow("Productive Working Hours:", self.prog_prod_hrs)
        form.addRow("Idle / Standby Hours:", self.prog_idle_hrs)
        form.addRow("Site Notes & Constraints:", self.prog_notes)
        return w

    def _on_mode_changed(self, idx: int):
        self.form_stack.setCurrentIndex(idx)

    # ══════════════════════════════════════════════════════
    #  CASCADING LOOKUPS
    # ══════════════════════════════════════════════════════
    def _load_projects(self):
        self.project.blockSignals(True)
        self.project.clear()
        try:
            with self.db.session_scope() as s:
                ps = (
                    s.query(Project)
                    .order_by(Project.project_code)
                    .all()
                )
                for p in ps:
                    self.project.addItem(
                        f"{p.project_code} — {p.title}", p.id
                    )
        except Exception:
            logger.exception("Failed to load projects")
        self.project.blockSignals(False)

        if self.project.count():
            self.load_lines()

    def load_lines(self):
        pid = self.project.currentData()
        self._clear_combo(self.line)
        if not pid:
            return

        try:
            with self.db.session_scope() as s:
                xs = (
                    s.query(LineListItem)
                    .filter_by(project_id=pid)
                    .order_by(LineListItem.line_number)
                    .all()
                )
                for x in xs:
                    self.line.addItem(x.line_number, x.id)
        except Exception:
            logger.exception("Failed to load lines")

        self.load_iso()

    def load_iso(self):
        pid = self.project.currentData()
        ln = self.line.currentText().strip()
        self._clear_combo(self.iso)
        if not pid or not ln:
            return

        try:
            with self.db.session_scope() as s:
                xs = (
                    s.query(LineListItem)
                    .filter_by(project_id=pid, line_number=ln)
                    .all()
                )
                seen = set()
                for x in xs:
                    if x.iso_number and x.iso_number not in seen:
                        self.iso.addItem(x.iso_number, x.id)
                        seen.add(x.iso_number)
        except Exception:
            logger.exception("Failed to load ISOs")

        self.load_spools()

    def load_spools(self):
        pid = self.project.currentData()
        ln = self.line.currentText().strip()
        iso = self.iso.currentText().strip()
        self._clear_combo(self.spool)
        if not pid:
            return

        try:
            with self.db.session_scope() as s:
                q = s.query(Spool).filter(Spool.project_id == pid)
                if ln:
                    q = q.filter(Spool.line_number == ln)
                if iso:
                    q = q.filter(Spool.iso_number == iso)
                xs = q.order_by(Spool.spool_number).all()
                for x in xs:
                    self.spool.addItem(x.spool_number, x.id)
        except Exception:
            logger.exception("Failed to load spools")

        self.load_welds()

    def load_welds(self):
        pid = self.project.currentData()
        sid = self.spool.currentData()
        ln = self.line.currentText().strip()
        self._clear_combo(self.weld)
        if not pid:
            return

        try:
            with self.db.session_scope() as s:
                q = s.query(Weld).filter(Weld.project_id == pid)
                if sid:
                    q = q.filter(Weld.spool_id == sid)
                elif ln:
                    q = q.filter(Weld.line_number == ln)
                xs = q.order_by(Weld.weld_id).all()
                for x in xs:
                    self.weld.addItem(x.weld_id, x.id)
        except Exception:
            logger.exception("Failed to load welds")

        self.autofill_context()

    def autofill_context(self):
        """Load upstream specifications and populate engineering preview."""
        pid = self.project.currentData()
        ln = self.line.currentText().strip()
        spool_no = self.spool.currentText().strip()
        weld_id = self.weld.currentText().strip()

        if not pid:
            self.lbl_context.setText(
                "💡 <b>Engineering Target:</b> "
                "<span style='color:#64748b;'>"
                "Select project above...</span>"
            )
            return

        ctx_parts = []
        if ln:
            ctx_parts.append(f"<b>Line:</b> {ln}")
        if spool_no:
            ctx_parts.append(f"<b>Spool:</b> {spool_no}")
        if weld_id:
            ctx_parts.append(f"<b>Joint:</b> {weld_id}")

        try:
            with self.db.session_scope() as s:
                if weld_id:
                    w = (
                        s.query(Weld)
                        .filter(
                            Weld.project_id == pid,
                            Weld.weld_id == weld_id,
                        )
                        .first()
                    )
                    if w:
                        ctx_parts.append(f"<b>Size:</b> {w.size or '—'}")
                        ctx_parts.append(
                            f"<b>Type:</b> {w.weld_type or '—'}"
                        )
                        if w.welder_id or w.welder_name:
                            self.weld_welder.setText(
                                w.welder_name or w.welder_id or ""
                            )
                        if (hasattr(w, "wps_id") and w.wps_id):
                            self.weld_wps.setText(w.wps_id)

                elif ln:
                    l_item = (
                        s.query(LineListItem)
                        .filter_by(project_id=pid, line_number=ln)
                        .first()
                    )
                    if l_item:
                        ctx_parts.append(
                            f"<b>Class:</b> "
                            f"{l_item.pipe_class or '—'}"
                        )
                        ctx_parts.append(
                            f"<b>Fluid:</b> "
                            f"{l_item.fluid_code or l_item.fluid_name or '—'}"
                        )
        except Exception:
            logger.exception("Failed to autofill engineering context")

        summary_txt = (
            " &middot; ".join(ctx_parts) if ctx_parts
            else "Select target components above..."
        )
        self.lbl_context.setText(
            f"💡 <b>Engineering Target:</b> {summary_txt}"
        )

    def _clear_combo(self, w: QComboBox):
        w.blockSignals(True)
        w.clear()
        w.blockSignals(False)

    # ══════════════════════════════════════════════════════
    #  SAVE
    # ══════════════════════════════════════════════════════
    def save(self):
        pid = self.project.currentData()
        if not pid:
            QMessageBox.warning(
                self, "Validation", "Please select a Project first."
            )
            return

        mode = self.cmb_mode.currentData()
        user = getattr(self.session, "username", "admin")
        ln = self.line.currentText().strip()
        iso = self.iso.currentText().strip()
        spool = self.spool.currentText().strip()
        wid = self.weld.currentText().strip()

        try:
            with self.db.session_scope() as s:
                # ── 1. Weld Production & Visual QC ───────────
                if mode == "Weld Production & Visual QC":
                    if not wid:
                        raise ValueError(
                            "Please select or enter a Joint / Weld ID."
                        )
                    w = (
                        s.query(Weld)
                        .filter(
                            Weld.project_id == pid, Weld.weld_id == wid
                        )
                        .first()
                    )
                    if not w:
                        w = Weld(
                            project_id=pid, weld_id=wid,
                            line_number=ln, iso_number=iso,
                            created_by=user,
                        )
                        s.add(w)
                    w.welder_name = (
                        self.weld_welder.text().strip() or w.welder_name
                    )
                    w.status = self.weld_status.currentText()
                    w.remarks = self.weld_remarks.toPlainText().strip()
                    if hasattr(w, "wps_id"):
                        w.wps_id = self.weld_wps.text().strip()

                    self._log_recent(
                        "Weld QC", ln or "—", wid, w.status, user
                    )

                # ── 2. Fit-Up Clearance Inspection ───────────
                elif mode == "Fit-Up Clearance Inspection":
                    if not wid:
                        raise ValueError(
                            "Select a Joint ID for Fit-up verification."
                        )
                    w = (
                        s.query(Weld)
                        .filter(
                            Weld.project_id == pid, Weld.weld_id == wid
                        )
                        .first()
                    )
                    if not w:
                        w = Weld(
                            project_id=pid, weld_id=wid,
                            line_number=ln, created_by=user,
                        )
                        s.add(w)
                    w.fitup_date = self.fit_date.date().toPyDate()
                    w.fitup_inspector = (
                        self.fit_inspector.text().strip() or user
                    )
                    w.status = (
                        "Fitup Complete"
                        if self.fit_result.currentText() == "Accepted"
                        else "Fitup Rejected"
                    )
                    w.remarks = (
                        f"Root: {self.fit_root.value()}mm, "
                        f"Hi-Low: {self.fit_hilow.value()}mm. "
                        f"{self.fit_remarks.toPlainText().strip()}"
                    )

                    self._log_recent(
                        "Fit-Up", ln or "—", wid,
                        self.fit_result.currentText(), user,
                    )

                # ── 3. NDT Examination Logging ───────────────
                elif mode == "NDT Examination Logging":
                    if not wid:
                        raise ValueError(
                            "Select a Joint ID for NDT recording."
                        )
                    w = (
                        s.query(Weld)
                        .filter(
                            Weld.project_id == pid, Weld.weld_id == wid
                        )
                        .first()
                    )
                    if not w:
                        raise ValueError(
                            f"Weld '{wid}' not found in project database."
                        )
                    ndt_rec = NDTRecord(
                        weld_id_fk=w.id,
                        ndt_method=self.ndt_method.currentText(),
                        inspection_date=self.ndt_date.date().toPyDate(),
                        inspector_id=(
                            self.ndt_inspector.text().strip() or user
                        ),
                        result=self.ndt_result.currentText(),
                        report_number=self.ndt_report_no.text().strip(),
                        remarks=self.ndt_remarks.toPlainText().strip(),
                    )
                    s.add(ndt_rec)
                    if self.ndt_result.currentText() == "Pass":
                        w.status = "Accepted"
                    elif self.ndt_result.currentText() == "Fail":
                        w.status = "Rejected"

                    self._log_recent(
                        "NDT Record", ln or "—",
                        f"{wid} ({self.ndt_method.currentText()})",
                        self.ndt_result.currentText(), user,
                    )

                # ── 4. Spool Field Installation ──────────────
                elif mode == "Spool Field Installation":
                    if not spool:
                        raise ValueError(
                            "Select a Spool identifier to record "
                            "site installation."
                        )
                    sp_obj = (
                        s.query(Spool)
                        .filter(
                            Spool.project_id == pid,
                            Spool.spool_number == spool,
                        )
                        .first()
                    )
                    if not sp_obj:
                        sp_obj = Spool(
                            project_id=pid, spool_number=spool,
                            line_number=ln, iso_number=iso,
                        )
                        s.add(sp_obj)
                    sp_obj.status = self.erect_status.currentText()
                    if self.erect_status.currentText() == "Installed":
                        sp_obj.installed_date = (
                            self.erect_date.date().toPyDate()
                        )

                    self._log_recent(
                        "Spool Erection", ln or "—",
                        spool, sp_obj.status, user,
                    )

                # ── 5. Material Receiving & Heat Log ─────────
                elif mode == "Material Receiving & Heat Log":
                    heat = self.mat_heat.text().strip()
                    if not heat:
                        raise ValueError(
                            "Heat / Melt Number is mandatory."
                        )
                    mat_item = MaterialItem(
                        project_id=pid,
                        material_type=self.mat_type.currentText(),
                        spec_grade=self.mat_grade.text().strip(),
                        size=self.mat_size.text().strip(),
                        heat_number=heat,
                        quantity_received=self.mat_qty.value(),
                        quantity_available=self.mat_qty.value(),
                        unit=self.mat_unit.text().strip(),
                        mtr_received=self.mat_mtr.isChecked(),
                        received_date=datetime.date.today(),
                    )
                    s.add(mat_item)

                    self._log_recent(
                        "Material MRR", heat,
                        f"{self.mat_type.currentText()} "
                        f"({self.mat_grade.text()})",
                        f"{self.mat_qty.value()} {self.mat_unit.text()}",
                        user,
                    )

                # ── 6. Work Front Daily Progress ─────────────
                elif mode == "Work Front Daily Progress":
                    wf_code = (
                        self.prog_front.text().strip() or spool or ln
                    )
                    if not wf_code:
                        raise ValueError(
                            "Please provide a Work Front / Line code."
                        )
                    wf = (
                        s.query(WorkFront)
                        .filter_by(project_id=pid, front_code=wf_code)
                        .first()
                    )
                    wf_id = wf.id if wf else None
                    unit_str = wf.unit if wf else "DIA-INCH"

                    s.add(ProductivitySnapshot(
                        project_id=pid,
                        resource_type="WORK_FRONT",
                        resource_code=wf_code,
                        work_front_id=wf_id,
                        work_date=datetime.date.today(),
                        planned_hours=self.prog_actual_hrs.value(),
                        actual_hours=self.prog_actual_hrs.value(),
                        productive_hours=self.prog_prod_hrs.value(),
                        idle_hours=self.prog_idle_hrs.value(),
                        quantity=self.prog_qty.value(),
                        unit=unit_str,
                        notes=self.prog_notes.toPlainText().strip(),
                    ))

                    self._log_recent(
                        "Daily Progress", wf_code,
                        f"{self.prog_qty.value()} {unit_str}",
                        f"{self.prog_prod_hrs.value()}h Prod",
                        user,
                    )

            QMessageBox.information(
                self, "Entry Committed",
                f"Successfully recorded '{mode}' into project database."
            )

            # Post-save behavior
            if not self.chk_keep_context.isChecked():
                self.clear_entry()
            else:
                self._quick_reset_inputs_only()

        except Exception as e:
            logger.exception("Failed to save smart entry")
            QMessageBox.critical(
                self, "Execution Error",
                f"Could not save field entry:\n{e}"
            )

    def _log_recent(self, w_type: str, target: str,
                    item: str, status: str, user: str):
        """Add a live entry to the current session log."""
        self.recent_table.insertRow(0)
        t_now = datetime.datetime.now().strftime("%H:%M:%S")

        self.recent_table.setItem(0, 0, QTableWidgetItem(t_now))
        self.recent_table.setItem(0, 1, QTableWidgetItem(w_type))
        self.recent_table.setItem(0, 2, QTableWidgetItem(target))
        self.recent_table.setItem(0, 3, QTableWidgetItem(item))

        st_item = QTableWidgetItem(status)
        if ("Accept" in status or "Pass" in status
                or "Installed" in status):
            st_item.setForeground(QBrush(QColor("#166534")))
            f = st_item.font()
            f.setBold(True)
            st_item.setFont(f)
        elif "Reject" in status or "Fail" in status:
            st_item.setForeground(QBrush(QColor("#991b1b")))
            f = st_item.font()
            f.setBold(True)
            st_item.setFont(f)
        self.recent_table.setItem(0, 4, st_item)

        self.recent_table.setItem(0, 5, QTableWidgetItem(user))

    def _quick_reset_inputs_only(self):
        """Clear only the free-text fields, keep hierarchy selection."""
        self.weld_remarks.clear()
        self.fit_remarks.clear()
        self.ndt_remarks.clear()
        self.erect_remarks.clear()
        self.prog_notes.clear()
        self.ndt_report_no.clear()

    def clear_entry(self):
        """Full reset — clear all fields and hierarchy selections."""
        self._quick_reset_inputs_only()
        self.weld_welder.clear()
        self.weld_wps.clear()
        self.fit_inspector.clear()
        self.ndt_inspector.clear()
        self.mat_heat.clear()
        self.prog_front.clear()
        self.weld.setCurrentIndex(-1)