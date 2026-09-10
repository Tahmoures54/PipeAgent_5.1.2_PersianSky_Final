# -*- coding: utf-8 -*-
# ui/tabs/joints_tab.py – PipeAgent 5.3.0
# Joint register, Weld Joint Control Sheet (WJC) & Traceability History
from __future__ import annotations

import csv
import logging
import datetime
from datetime import timezone
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QDoubleSpinBox, QTextEdit, QSplitter,
    QGroupBox, QFrame, QFileDialog, QApplication, QMenu,
    QAbstractItemView,
)
from PyQt6.QtGui import QColor, QFont, QBrush, QCursor, QAction

from db.manager import DatabaseManager
from db.models import Project, Weld
from security.session import SessionManager
from services.welding_service import WeldingService

# ── Joint types & statuses (fallback if config missing) ────────
try:
    from config import JOINT_TYPES, WELD_STATUSES
except ImportError:
    JOINT_TYPES = [
        "BW (Butt Weld)", "SW (Socket Weld)",
        "FW (Fillet Weld)", "Olet", "Threaded Seal",
    ]
    WELD_STATUSES = [
        "Pending", "Fitup Complete", "Welded", "NDT Pending",
        "Accepted", "Rejected", "Repaired",
    ]

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  UTIL
# ─────────────────────────────────────────────
def _utcnow():
    """Naive UTC — replacement for deprecated datetime.utcnow()."""
    return datetime.datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────
#  WELD STATUS BADGES
# ─────────────────────────────────────────────
WELD_BADGES = {
    "Accepted":       {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Rejected":       {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Pending":        {"bg": "#fef3c7", "fg": "#92400e", "icon": "⏳"},
    "Fitup Complete": {"bg": "#e0f2fe", "fg": "#075985", "icon": "🔧"},
    "Welded":         {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "⚡"},
    "NDT Pending":    {"bg": "#ffedd5", "fg": "#9a3412", "icon": "🛡️"},
    "Repaired":       {"bg": "#fce7f3", "fg": "#9d174d", "icon": "🔄"},
}
DEFAULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}


# ─────────────────────────────────────────────
#  STYLESHEET
# ─────────────────────────────────────────────
JOINTS_STYLESHEET = """
    QWidget#jointsTab {
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
    QGroupBox {
        font-size: 12px; font-weight: 800; color: #1e293b;
        border: 2px solid #e2e8f0; border-radius: 8px;
        margin-top: 10px; padding-top: 14px; background: white;
    }
    QGroupBox::title {
        subcontrol-origin: margin; subcontrol-position: top left;
        left: 10px; padding: 0 4px; background: white;
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
class WeldKPICard(QFrame):
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

    def set_value(self, text: str,
                  highlight: Optional[str] = None):
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
#  WELD DIALOG
# ─────────────────────────────────────────────
class WeldDialog(QDialog):
    def __init__(self, parent=None, projects=None,
                 existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = existing_data is not None
        self.setWindowTitle(
            "Edit Joint / WJC Entry" if self.is_edit
            else "Register New Joint / WJC"
        )
        self.setMinimumWidth(500)
        self.setStyleSheet(JOINTS_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.project_combo = QComboBox()
        if projects:
            for p in projects:
                self.project_combo.addItem(
                    f"{p.project_code} – {p.title}", p.id
                )

        self.weld_id = QLineEdit()
        self.weld_id.setPlaceholderText("e.g. W-01 or FW-102")

        self.weld_type = QComboBox()
        self.weld_type.addItems(["Shop", "Field"])

        self.line = QLineEdit()
        self.line.setPlaceholderText('e.g. 6"-PL-1001-A1A')

        self.iso = QLineEdit()
        self.iso.setPlaceholderText("e.g. ISO-01-DWG-001")

        self.joint = QComboBox()
        self.joint.addItems(JOINT_TYPES)

        self.size = QLineEdit()
        self.size.setPlaceholderText('e.g. 6" or 150mm')

        self.thk = QDoubleSpinBox()
        self.thk.setRange(0, 250)
        self.thk.setDecimals(2)
        self.thk.setSuffix(" mm")

        self.material = QLineEdit()
        self.material.setPlaceholderText("e.g. A106-B, SS316L")

        self.welder = QLineEdit()
        self.welder.setPlaceholderText(
            "e.g. W-04 (Welder Stamp/ID)"
        )

        self.wps_id = QLineEdit()
        self.wps_id.setPlaceholderText("e.g. WPS-CS-01")

        form.addRow("Project *:", self.project_combo)
        form.addRow("Joint / Weld ID *:", self.weld_id)
        form.addRow("Erection Location:", self.weld_type)
        form.addRow("Piping Line No *:", self.line)
        form.addRow("Isometric Drawing:", self.iso)
        form.addRow("Joint Configuration:", self.joint)
        form.addRow("Nominal Size (NPS):", self.size)
        form.addRow("Wall Thickness (SCH/mm):", self.thk)
        form.addRow("Base Material / Grade:", self.material)
        form.addRow("Assigned Welder Stamp:", self.welder)
        form.addRow("Qualified WPS No:", self.wps_id)
        layout.addLayout(form)

        if self.is_edit and existing_data:
            pid = existing_data.get("project_id")
            for i in range(self.project_combo.count()):
                if self.project_combo.itemData(i) == pid:
                    self.project_combo.setCurrentIndex(i)
                    break
            self.weld_id.setText(
                existing_data.get("weld_id", "")
            )
            self.weld_id.setReadOnly(True)
            self.weld_type.setCurrentText(
                existing_data.get("weld_type", "Shop")
            )
            self.line.setText(
                existing_data.get("line_number", "")
            )
            self.iso.setText(
                existing_data.get("iso_number", "")
            )
            self.joint.setCurrentText(
                existing_data.get("joint_type", JOINT_TYPES[0])
            )
            self.size.setText(existing_data.get("size", ""))
            self.thk.setValue(
                float(
                    existing_data.get("wall_thickness_mm") or 0.0
                )
            )
            self.material.setText(
                existing_data.get("material", "")
            )
            self.welder.setText(
                existing_data.get("welder_id", "")
            )
            self.wps_id.setText(
                existing_data.get("wps_id", "")
            )

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Entry")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _save(self):
        if not self.weld_id.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Joint / Weld ID is mandatory."
            )
            return
        if not self.line.text().strip():
            QMessageBox.warning(
                self, "Validation",
                "Piping Line Number is required."
            )
            return
        self.result_data = {
            "project_id": self.project_combo.currentData(),
            "weld_id": self.weld_id.text().strip(),
            "weld_type": self.weld_type.currentText(),
            "line_number": self.line.text().strip(),
            "iso_number": self.iso.text().strip(),
            "joint_type": self.joint.currentText(),
            "size": self.size.text().strip(),
            "wall_thickness_mm": (
                self.thk.value() if self.thk.value() > 0 else None
            ),
            "material": self.material.text().strip(),
            "welder_id": self.welder.text().strip(),
            "wps_id": self.wps_id.text().strip(),
        }
        self.accept()


# ─────────────────────────────────────────────
#  JOINT DETAIL DIALOG
# ─────────────────────────────────────────────
class JointDetailDialog(QDialog):
    def __init__(self, parent=None, weld_dict: dict = None,
                 history_records: list = None):
        super().__init__(parent)
        self.setWindowTitle(
            f"🔍 Joint Traceability Dossier – "
            f"{weld_dict.get('weld_id', 'Weld')}"
        )
        self.setMinimumSize(640, 520)
        self.setStyleSheet(JOINTS_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hdr = QLabel(
            f"📋 Technical Dossier: {weld_dict.get('weld_id')}"
        )
        hdr.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #1e3c72;"
        )
        layout.addWidget(hdr)

        # Engineering / material specs
        info_box = QGroupBox(
            "Engineering & Material Specifications"
        )
        info_grid = QGridLayout(info_box)
        info_grid.setSpacing(8)

        specs = [
            ("Piping Line:",
             weld_dict.get("line_number", "—")),
            ("Isometric DWG:",
             weld_dict.get("iso_number", "—")),
            ("Joint Type:", weld_dict.get("joint_type", "—")),
            ("Erection Area:",
             weld_dict.get("weld_type", "—")),
            ("Nominal Size:", weld_dict.get("size", "—")),
            ("Wall Thickness:",
             f"{weld_dict.get('wall_thickness_mm') or '—'} mm"),
            ("Base Material:",
             weld_dict.get("material", "—")),
            ("Assigned Welder:",
             weld_dict.get("welder_id", "—")),
            ("WPS Number:", weld_dict.get("wps_id", "—")),
            ("Current Status:",
             weld_dict.get("status", "Pending")),
            ("Total Repairs:",
             str(weld_dict.get("repair_count", 0))),
        ]

        for i, (label, val) in enumerate(specs):
            lbl_w = QLabel(f"<b>{label}</b>")
            lbl_w.setStyleSheet("color: #475569;")
            val_w = QLabel(str(val))
            val_w.setStyleSheet("color: #0f172a; font-weight: 600;")
            r, c = divmod(i, 2)
            info_grid.addWidget(lbl_w, r, c * 2)
            info_grid.addWidget(val_w, r, c * 2 + 1)

        layout.addWidget(info_box)

        # Audit trail / inspection history
        hist_box = QGroupBox(
            "Audit Trail & Inspection History Log"
        )
        hist_lay = QVBoxLayout(hist_box)
        hist_tbl = QTableWidget(0, 5)
        hist_tbl.setHorizontalHeaderLabels([
            "Timestamp", "Inspection Event", "Initial Value",
            "Updated Value", "Performed By",
        ])
        hist_tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        hist_tbl.setAlternatingRowColors(True)
        hist_tbl.verticalHeader().setVisible(False)

        if history_records:
            for h in history_records:
                row = hist_tbl.rowCount()
                hist_tbl.insertRow(row)
                t_str = (
                    h.timestamp.strftime("%Y-%m-%d %H:%M")
                    if hasattr(h, "timestamp") and h.timestamp
                    else ""
                )
                hist_tbl.setItem(
                    row, 0, QTableWidgetItem(t_str)
                )
                hist_tbl.setItem(
                    row, 1, QTableWidgetItem(
                        getattr(h, "event_type", "")
                    )
                )
                hist_tbl.setItem(
                    row, 2, QTableWidgetItem(
                        getattr(h, "old_value", "") or "—"
                    )
                )
                hist_tbl.setItem(
                    row, 3, QTableWidgetItem(
                        getattr(h, "new_value", "") or "—"
                    )
                )
                hist_tbl.setItem(
                    row, 4, QTableWidgetItem(
                        getattr(h, "user_name", "") or "System"
                    )
                )

        hist_lay.addWidget(hist_tbl)
        layout.addWidget(hist_box)

        btn_close = QPushButton("Close Dossier")
        btn_close.setObjectName("secondaryBtn")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class JointsTab(QWidget):
    def __init__(self, db: DatabaseManager,
                 session: SessionManager):
        super().__init__()
        self.setObjectName("jointsTab")
        self.db = db
        self.session = session
        self.svc = WeldingService(db)
        self.project_id: Optional[int] = None
        self._cached_welds: list[dict] = []

        self._build()
        self.setStyleSheet(JOINTS_STYLESHEET)
        self._load_projects()

    # ══════════════════════════════════════════
    #  UI BUILD
    # ══════════════════════════════════════════
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
        t = QLabel(
            "🔗 Joints Register & Weld Joint Control (WJC)"
        )
        t.setObjectName("mainTitle")
        s = QLabel(
            "Welding Quality Lifecycle: Fit-up Verification, "
            "Welding Production, NDT Tracking, and Repair Auditing."
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

        btn_r = QPushButton("🔄 Refresh")
        btn_r.setObjectName("secondaryBtn")
        btn_r.clicked.connect(self.refresh)
        proj_box.addWidget(btn_r)
        hdr_lay.addLayout(proj_box)

        root.addWidget(header_card)

        # KPI row
        kpi_lay = QHBoxLayout()
        kpi_lay.setSpacing(8)

        self.kpi_total = WeldKPICard(
            "Total Joints Registered", "🔗", "#3b82f6"
        )
        self.kpi_shop = WeldKPICard(
            "Shop Fabrication", "🏭", "#0ea5e9"
        )
        self.kpi_field = WeldKPICard(
            "Field Erection", "🏗️", "#8b5cf6"
        )
        self.kpi_accepted = WeldKPICard(
            "Accepted Joints", "✅", "#10b981"
        )
        self.kpi_rate = WeldKPICard(
            "QC Acceptance Rate", "📈", "#059669"
        )
        self.kpi_repairs = WeldKPICard(
            "Repair Cutouts", "⚠️", "#ef4444"
        )

        for k in (self.kpi_total, self.kpi_shop, self.kpi_field,
                  self.kpi_accepted, self.kpi_rate, self.kpi_repairs):
            kpi_lay.addWidget(k)
        root.addLayout(kpi_lay)

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
            "🔍 Quick Search Weld ID, Line Number, "
            "Welder Stamp, Material..."
        )
        self.txt_search.textChanged.connect(self._apply_filters)
        filter_lay.addWidget(self.txt_search, 1)

        self.cmb_filter_type = QComboBox()
        self.cmb_filter_type.addItem("All Types", None)
        self.cmb_filter_type.addItems(["Shop", "Field"])
        self.cmb_filter_type.currentIndexChanged.connect(
            self._apply_filters
        )
        filter_lay.addWidget(self.cmb_filter_type)

        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.addItem("All Statuses", None)
        for st in WELD_STATUSES:
            self.cmb_filter_status.addItem(st, st)
        self.cmb_filter_status.currentIndexChanged.connect(
            self._apply_filters
        )
        filter_lay.addWidget(self.cmb_filter_status)

        btn_n = QPushButton("➕ Register Joint")
        btn_n.setObjectName("primaryBtn")
        btn_n.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_n.clicked.connect(self._add)
        filter_lay.addWidget(btn_n)

        btn_exp = QPushButton("📥 Export WJC")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(self._export_wjc_csv)
        filter_lay.addWidget(btn_exp)

        root.addWidget(filter_card)

        # Master-detail splitter
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(8)

        # Left: WJC register
        left_box = QGroupBox(
            "📋 WELD JOINT CONTROL REGISTER (WJC)"
        )
        left_lay = QVBoxLayout(left_box)
        left_lay.setContentsMargins(8, 12, 8, 8)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "ID", "Weld / Joint ID", "Type", "Piping Line No",
            "Joint Type", "Size (NPS)", "Thickness",
            "Welder Stamp", "QC Status", "Repairs",
        ])
        self.table.setColumnHidden(0, True)
        self.table.setAlternatingRowColors(True)
        # ✅ FIXED: use QAbstractItemView enums
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.itemSelectionChanged.connect(self._show_history)
        self.table.doubleClicked.connect(self._on_row_double_click)
        self.table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table.customContextMenuRequested.connect(
            self._show_context_menu
        )
        left_lay.addWidget(self.table)
        split.addWidget(left_box)

        # Right: audit trail + quick actions
        right_box = QGroupBox(
            "🛡️ JOINT INSPECTION & AUDIT TRAIL"
        )
        rl = QVBoxLayout(right_box)
        rl.setContentsMargins(8, 12, 8, 8)
        rl.setSpacing(8)

        self.hist = QTableWidget(0, 5)
        self.hist.setHorizontalHeaderLabels([
            "Timestamp", "Inspection Action",
            "Old State", "New State", "Inspector",
        ])
        self.hist.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.hist.setAlternatingRowColors(True)
        self.hist.verticalHeader().setVisible(False)
        self.hist.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        rl.addWidget(self.hist, 1)

        # Quick action box
        act_box = QFrame()
        act_box.setStyleSheet(
            "background: #f8fafc; border: 1px solid #cbd5e1; "
            "border-radius: 6px; padding: 6px;"
        )
        act_lay = QVBoxLayout(act_box)
        act_lay.setSpacing(6)

        st_row = QHBoxLayout()
        st_row.addWidget(QLabel("Set Status:"))
        self.st_combo = QComboBox()
        self.st_combo.addItems(WELD_STATUSES)
        st_row.addWidget(self.st_combo, 1)

        btn_st = QPushButton("Apply Status")
        btn_st.setObjectName("secondaryBtn")
        btn_st.clicked.connect(self._change_status)
        st_row.addWidget(btn_st)
        act_lay.addLayout(st_row)

        quick_btns = QHBoxLayout()
        btn_fit = QPushButton("🔧 Verify Fit-up")
        btn_fit.setObjectName("secondaryBtn")
        btn_fit.clicked.connect(self._fitup)
        quick_btns.addWidget(btn_fit)

        btn_rep = QPushButton("⚠️ Record Repair")
        btn_rep.setObjectName("dangerBtn")
        btn_rep.clicked.connect(self._repair)
        quick_btns.addWidget(btn_rep)

        btn_edit = QPushButton("✏️ Edit Joint")
        btn_edit.setObjectName("secondaryBtn")
        btn_edit.clicked.connect(self._edit_selected_joint)
        quick_btns.addWidget(btn_edit)
        act_lay.addLayout(quick_btns)

        rl.addWidget(act_box)
        split.addWidget(right_box)

        split.setSizes([720, 480])
        root.addWidget(split, 1)

    # ══════════════════════════════════════════
    #  PROJECT LOADING
    # ══════════════════════════════════════════
    def _load_projects(self):
        self.proj.blockSignals(True)
        self.proj.clear()
        try:
            with self.db.session_scope() as s:
                for p in (
                    s.query(Project).order_by(Project.project_code)
                ):
                    self.proj.addItem(
                        f"{p.project_code} – {p.title}", p.id
                    )
        except Exception:
            logger.exception(
                "Failed to load projects in JointsTab"
            )

        self.proj.blockSignals(False)
        if self.proj.count():
            self._proj_changed()

    def _proj_changed(self):
        self.project_id = self.proj.currentData()
        self.refresh()

    # ══════════════════════════════════════════
    #  REFRESH
    # ══════════════════════════════════════════
    def refresh(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.hist.setRowCount(0)
        self._cached_welds = []

        if not self.project_id:
            self._update_kpi_metrics({})
            return

        try:
            welds = self.svc.list_by_project(self.project_id)
            for w in welds:
                self._cached_welds.append({
                    "id": w.id,
                    "project_id": w.project_id,
                    "weld_id": w.weld_id,
                    "weld_type": w.weld_type or "Shop",
                    "line_number": w.line_number or "",
                    "iso_number": (
                        getattr(w, "iso_number", "") or ""
                    ),
                    "joint_type": w.joint_type or "",
                    "size": w.size or "",
                    "wall_thickness_mm": w.wall_thickness_mm,
                    "material": getattr(w, "material", "") or "",
                    "welder_id": w.welder_id or "",
                    "wps_id": getattr(w, "wps_id", "") or "",
                    "status": w.status or "Pending",
                    "repair_count": w.repair_count or 0,
                })

            stats = self.svc.get_project_stats(self.project_id)
            self._update_kpi_metrics(stats)
            self._apply_filters()
        except Exception:
            logger.exception("Failed to refresh joints register")

    def _update_kpi_metrics(self, stats: dict):
        total = stats.get("total", len(self._cached_welds))
        accepted = stats.get(
            "accepted",
            sum(
                1 for w in self._cached_welds
                if w["status"] == "Accepted"
            ),
        )
        rate = stats.get(
            "acceptance_rate",
            round(
                (accepted / total * 100) if total > 0 else 0.0,
                1,
            ),
        )

        shop_count = sum(
            1 for w in self._cached_welds
            if w["weld_type"] == "Shop"
        )
        field_count = sum(
            1 for w in self._cached_welds
            if w["weld_type"] == "Field"
        )
        total_repairs = sum(
            w["repair_count"] for w in self._cached_welds
        )

        self.kpi_total.set_value(str(total))
        self.kpi_shop.set_value(str(shop_count))
        self.kpi_field.set_value(str(field_count))
        self.kpi_accepted.set_value(
            str(accepted),
            highlight=(
                "green" if accepted == total and total > 0 else None
            ),
        )
        self.kpi_rate.set_value(
            f"{rate}%",
            highlight=(
                "green" if rate >= 95.0
                else (
                    "red"
                    if rate < 85.0 and total > 0
                    else None
                )
            ),
        )
        self.kpi_repairs.set_value(
            str(total_repairs),
            highlight="red" if total_repairs > 0 else "green",
        )

    def _apply_filters(self):
        query = self.txt_search.text().strip().lower()
        type_filter = self.cmb_filter_type.currentData()
        status_filter = self.cmb_filter_status.currentData()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for w in self._cached_welds:
            if type_filter and w["weld_type"] != type_filter:
                continue
            if status_filter and w["status"] != status_filter:
                continue
            if query:
                combined = (
                    f"{w['weld_id']} {w['line_number']} "
                    f"{w['iso_number']} {w['welder_id']} "
                    f"{w['material']} {w['wps_id']}"
                ).lower()
                if query not in combined:
                    continue

            r = self.table.rowCount()
            self.table.insertRow(r)

            self.table.setItem(
                r, 0, QTableWidgetItem(str(w["id"]))
            )
            self.table.setItem(
                r, 1, QTableWidgetItem(w["weld_id"])
            )
            self.table.setItem(
                r, 2, QTableWidgetItem(w["weld_type"])
            )
            self.table.setItem(
                r, 3, QTableWidgetItem(w["line_number"])
            )
            self.table.setItem(
                r, 4, QTableWidgetItem(w["joint_type"])
            )
            self.table.setItem(
                r, 5, QTableWidgetItem(w["size"])
            )
            self.table.setItem(
                r, 6, QTableWidgetItem(
                    f"{w['wall_thickness_mm'] or '—'} mm"
                    if w["wall_thickness_mm"] else "—"
                )
            )
            self.table.setItem(
                r, 7, QTableWidgetItem(w["welder_id"])
            )

            # Status badge
            status_item = QTableWidgetItem(w["status"])
            badge = WELD_BADGES.get(w["status"], DEFAULT_BADGE)
            status_item.setText(f"{badge['icon']} {w['status']}")
            status_item.setBackground(QBrush(QColor(badge["bg"])))
            status_item.setForeground(QBrush(QColor(badge["fg"])))
            f = status_item.font()
            f.setBold(True)
            status_item.setFont(f)
            self.table.setItem(r, 8, status_item)

            # Repair count
            rep_item = QTableWidgetItem(str(w["repair_count"]))
            if w["repair_count"] > 0:
                rep_item.setForeground(QBrush(QColor("#991b1b")))
                f_rep = rep_item.font()
                f_rep.setBold(True)
                rep_item.setFont(f_rep)
            self.table.setItem(r, 9, rep_item)

        self.table.setSortingEnabled(True)

    # ══════════════════════════════════════════
    #  SELECTION HELPERS
    # ══════════════════════════════════════════
    def _selected_weld_records(self) -> list[dict]:
        rows = self.table.selectionModel().selectedRows()
        results = []
        for r in rows:
            pk = int(self.table.item(r.row(), 0).text())
            item = next(
                (x for x in self._cached_welds if x["id"] == pk),
                None,
            )
            if item:
                results.append(item)
        return results

    def _show_history(self):
        self.hist.setRowCount(0)
        selected = self._selected_weld_records()
        if not selected:
            return

        weld_pk = selected[0]["id"]
        try:
            records = self.svc.get_history(weld_pk)
            for h in records:
                r = self.hist.rowCount()
                self.hist.insertRow(r)
                when = (
                    h.timestamp.strftime("%Y-%m-%d %H:%M")
                    if hasattr(h, "timestamp") and h.timestamp
                    else ""
                )
                self.hist.setItem(
                    r, 0, QTableWidgetItem(when)
                )
                self.hist.setItem(
                    r, 1, QTableWidgetItem(
                        getattr(h, "event_type", "")
                    )
                )
                self.hist.setItem(
                    r, 2, QTableWidgetItem(
                        getattr(h, "old_value", "") or "—"
                    )
                )
                self.hist.setItem(
                    r, 3, QTableWidgetItem(
                        getattr(h, "new_value", "") or "—"
                    )
                )
                self.hist.setItem(
                    r, 4, QTableWidgetItem(
                        getattr(h, "user_name", "") or "System"
                    )
                )
        except Exception:
            logger.exception("Failed to load joint history")

    def _on_row_double_click(self, index):
        selected = self._selected_weld_records()
        if not selected:
            return
        weld = selected[0]
        history = self.svc.get_history(weld["id"])
        dlg = JointDetailDialog(self, weld, history)
        dlg.exec()

    # ══════════════════════════════════════════
    #  CRUD
    # ══════════════════════════════════════════
    def _add(self):
        with self.db.session_scope() as s:
            projects = (
                s.query(Project)
                .order_by(Project.project_code)
                .all()
            )
            proj_list = [
                type("P", (), {
                    "id": p.id,
                    "project_code": p.project_code,
                    "title": p.title,
                })()
                for p in projects
            ]

        if not proj_list:
            QMessageBox.information(
                self, "Info",
                "Please register a project first."
            )
            return

        dlg = WeldDialog(self, projects=proj_list)
        if self.project_id:
            for i in range(dlg.project_combo.count()):
                if dlg.project_combo.itemData(i) == self.project_id:
                    dlg.project_combo.setCurrentIndex(i)
                    break

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.result_data
        user = getattr(self.session, "username", "admin")

        w = self.svc.create_weld(
            d["project_id"], d["weld_id"],
            weld_type=d["weld_type"],
            line_number=d["line_number"],
            iso_number=d["iso_number"],
            joint_type=d["joint_type"], size=d["size"],
            wall_thickness_mm=d["wall_thickness_mm"],
            material=d["material"],
            welder_id=d["welder_id"], created_by=user,
        )
        if w:
            self.refresh()
            QMessageBox.information(
                self, "Success",
                f"Joint '{d['weld_id']}' created successfully."
            )
        else:
            QMessageBox.warning(
                self, "Error",
                "Could not create joint "
                "(Duplicate Weld ID or license limit reached)."
            )

    def _edit_selected_joint(self):
        selected = self._selected_weld_records()
        if not selected:
            QMessageBox.warning(
                self, "Selection",
                "Select a joint from the register to edit."
            )
            return

        weld_data = selected[0]
        with self.db.session_scope() as s:
            projects = (
                s.query(Project)
                .order_by(Project.project_code)
                .all()
            )
            proj_list = [
                type("P", (), {
                    "id": p.id,
                    "project_code": p.project_code,
                    "title": p.title,
                })()
                for p in projects
            ]

        dlg = WeldDialog(
            self, projects=proj_list, existing_data=weld_data
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.result_data
        try:
            with self.db.session_scope() as s:
                # ✅ FIXED: SQLAlchemy 2.0 — s.get(Model, pk)
                w = s.get(Weld, weld_data["id"])
                if w:
                    w.weld_type = d["weld_type"]
                    w.line_number = d["line_number"]
                    w.iso_number = d["iso_number"]
                    w.joint_type = d["joint_type"]
                    w.size = d["size"]
                    w.wall_thickness_mm = d["wall_thickness_mm"]
                    w.material = d["material"]
                    w.welder_id = d["welder_id"]
                    if hasattr(w, "wps_id"):
                        w.wps_id = d.get("wps_id", "")
                    # ✅ FIXED: use _utcnow() if field exists
                    if hasattr(w, "updated_at"):
                        w.updated_at = _utcnow()

            self.refresh()
            QMessageBox.information(
                self, "Updated",
                f"Joint '{weld_data['weld_id']}' "
                f"specifications updated."
            )
        except Exception as e:
            logger.exception("Failed to edit joint")
            QMessageBox.critical(
                self, "Error", f"Update failed:\n{e}"
            )

    # ══════════════════════════════════════════
    #  STATUS TRANSITIONS
    # ══════════════════════════════════════════
    def _change_status(self):
        selected = self._selected_weld_records()
        if not selected:
            QMessageBox.warning(
                self, "Selection",
                "Select one or more joints to update status."
            )
            return

        new_status = self.st_combo.currentText()
        user = getattr(self.session, "username", "admin")
        success_count = 0

        for w in selected:
            ok, _ = self.svc.change_status(
                w["weld_id"], new_status, updated_by=user
            )
            if ok:
                success_count += 1

        self.refresh()
        self._show_history()
        QMessageBox.information(
            self, "Status Applied",
            f"Updated status to '{new_status}' for "
            f"{success_count} joint(s)."
        )

    def _fitup(self):
        selected = self._selected_weld_records()
        if not selected:
            QMessageBox.warning(
                self, "Selection",
                "Select a joint to verify fit-up inspection."
            )
            return

        user = getattr(self.session, "username", "admin")
        for w in selected:
            self.svc.record_fitup(
                w["weld_id"], inspector=user, user=user
            )

        self.refresh()
        self._show_history()
        QMessageBox.information(
            self, "Fit-up Verified",
            f"Fit-up inspection recorded for "
            f"{len(selected)} joint(s)."
        )

    def _repair(self):
        selected = self._selected_weld_records()
        if not selected:
            QMessageBox.warning(
                self, "Selection",
                "Select a joint to log repair cutout."
            )
            return

        weld_id = selected[0]["weld_id"]
        if QMessageBox.question(
            self, "Confirm Repair",
            f"Record welding repair cut-out for Joint "
            f"'{weld_id}'?\n"
            f"This will increment the repair counter and reset "
            f"status to 'Repaired'.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        user = getattr(self.session, "username", "admin")
        ok, msg = self.svc.record_repair(
            weld_id, updated_by=user
        )
        self.refresh()
        self._show_history()
        QMessageBox.information(self, "Repair Result", msg)

    def _delete_selected(self):
        selected = self._selected_weld_records()
        if not selected:
            return

        weld_ids = [w["weld_id"] for w in selected]
        if QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(weld_ids)} joint(s) and "
            f"their inspection history from the WJC register?\n\n"
            f"Joints: {', '.join(weld_ids[:5])}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            with self.db.session_scope() as s:
                for w in selected:
                    # ✅ FIXED: SQLAlchemy 2.0
                    rec = s.get(Weld, w["id"])
                    if rec:
                        s.delete(rec)
            self.refresh()
            QMessageBox.information(
                self, "Deleted",
                "Selected joint(s) removed from project register."
            )
        except Exception as e:
            logger.exception("Failed to delete joints")
            QMessageBox.critical(
                self, "Error", f"Could not delete joints:\n{e}"
            )

    # ══════════════════════════════════════════
    #  CONTEXT MENU
    # ══════════════════════════════════════════
    def _show_context_menu(self, pos):
        selected = self._selected_weld_records()
        if not selected:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 18px; }"
        )

        act_dossier = QAction(
            "🔍 View Full Joint Dossier", self
        )
        act_dossier.triggered.connect(
            lambda: self._on_row_double_click(
                self.table.currentIndex()
            )
        )
        menu.addAction(act_dossier)

        act_edit = QAction("✏️ Edit Specifications", self)
        act_edit.triggered.connect(self._edit_selected_joint)
        menu.addAction(act_edit)

        menu.addSeparator()

        act_fit = QAction("🔧 Record Fit-up OK", self)
        act_fit.triggered.connect(self._fitup)
        menu.addAction(act_fit)

        act_accept = QAction("✅ Mark as Accepted", self)
        act_accept.triggered.connect(
            lambda: self._quick_set_status("Accepted")
        )
        menu.addAction(act_accept)

        act_repair = QAction("⚠️ Log Welding Repair", self)
        act_repair.triggered.connect(self._repair)
        menu.addAction(act_repair)

        menu.addSeparator()

        act_copy = QAction("📋 Copy Joint Details", self)
        act_copy.triggered.connect(self._copy_selected_row)
        menu.addAction(act_copy)

        act_del = QAction("🗑️ Delete Selected Joint(s)", self)
        act_del.triggered.connect(self._delete_selected)
        menu.addAction(act_del)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _quick_set_status(self, status: str):
        selected = self._selected_weld_records()
        user = getattr(self.session, "username", "admin")
        for w in selected:
            self.svc.change_status(
                w["weld_id"], status, updated_by=user
            )
        self.refresh()
        self._show_history()

    def _copy_selected_row(self):
        selected = self._selected_weld_records()
        if selected:
            w = selected[0]
            txt = (
                f"Weld ID: {w['weld_id']} | "
                f"Line: {w['line_number']} | "
                f"Size: {w['size']} | "
                f"Welder: {w['welder_id']} | "
                f"Status: {w['status']}"
            )
            QApplication.clipboard().setText(txt)

    # ══════════════════════════════════════════
    #  EXPORT
    # ══════════════════════════════════════════
    def _export_wjc_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(
                self, "Export",
                "No joint data available to export."
            )
            return

        timestamp = datetime.datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        proj_code = (
            self.proj.currentText().split("–")[0].strip()
        )
        default_name = (
            f"WJC_Joints_Register_{proj_code}_{timestamp}.csv"
        )

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Weld Joint Control Sheet",
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
                f"WJC Register exported to:\n{filename}"
            )
        except Exception as e:
            logger.exception("Failed to export WJC CSV")
            QMessageBox.critical(
                self, "Export Error",
                f"Could not create CSV file:\n{e}"
            )