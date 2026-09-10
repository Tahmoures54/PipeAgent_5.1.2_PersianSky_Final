# -*- coding: utf-8 -*-
# ui/tabs/mobile_field_tab.py – PipeAgent 5.3.0
# Offline-first Field Mobile Hub
from __future__ import annotations

import csv
import json
import logging
import datetime
from datetime import timezone
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QGroupBox, QFileDialog,
    QMessageBox, QPlainTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QSplitter, QDialog, QFormLayout,
    QDialogButtonBox, QDoubleSpinBox, QProgressBar, QMenu,
    QApplication, QAbstractItemView, QSpinBox,
)
from PyQt6.QtGui import (
    QColor, QFont, QBrush, QCursor, QAction, QPixmap,
)

from db.manager import DatabaseManager
from db.models import Project
from security.session import SessionManager
from services.field_mobile_service import FieldMobileService

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  UTIL
# ─────────────────────────────────────────────
def _utcnow():
    """Naive UTC — replacement for deprecated datetime.utcnow()."""
    return datetime.datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────
#  EVENT BADGES
# ─────────────────────────────────────────────
EVENT_BADGES = {
    "FITUP":       {"bg": "#e0f2fe", "fg": "#075985", "icon": "🔧", "label": "Fit-up Verified"},
    "WELD":        {"bg": "#fef3c7", "fg": "#92400e", "icon": "🔥", "label": "Weld Production"},
    "PHOTO":       {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "📷", "label": "Photo Captured"},
    "QC":          {"bg": "#dbeafe", "fg": "#1e40af", "icon": "🔎", "label": "QC Inspection"},
    "NDT_REQUEST": {"bg": "#ffedd5", "fg": "#9a3412", "icon": "🧪", "label": "NDT Requisition"},
    "REPAIR":      {"bg": "#fee2e2", "fg": "#991b1b", "icon": "⚠️", "label": "Repair Logged"},
    "ACCEPTANCE":  {"bg": "#dcfce7", "fg": "#166534", "icon": "✅", "label": "Final Clearance"},
}
DEFAULT_EVENT_BADGE = {
    "bg": "#f1f5f9", "fg": "#475569", "icon": "⚡", "label": "Field Event",
}

SYNC_STATUS_BADGES = {
    "Pending": {"bg": "#fef3c7", "fg": "#92400e", "icon": "⏳"},
    "Synced":  {"bg": "#dcfce7", "fg": "#166534", "icon": "☁️"},
    "Failed":  {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
}


# ─────────────────────────────────────────────
#  STYLESHEET
# ─────────────────────────────────────────────
MOBILE_HUB_STYLESHEET = """
    QWidget#mobileFieldTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #102a43, stop:1 #243b53);
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
    QPushButton#actionBtn {
        background: #f8fafc; color: #0f172a;
        border: 2px solid #cbd5e1; border-radius: 8px;
        font-size: 13px; font-weight: 700; padding: 10px;
        text-align: center;
    }
    QPushButton#actionBtn:hover {
        background: #eff6ff; border-color: #3b82f6; color: #1d4ed8;
    }
    QPushButton#primaryBtn {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #3b82f6, stop:1 #2563eb);
        color: white; border: none; padding: 8px 16px;
        border-radius: 6px; font-weight: 700;
    }
    QPushButton#primaryBtn:hover { background: #1d4ed8; }
    QPushButton#syncBtn {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #10b981, stop:1 #059669);
        color: white; border: none; padding: 8px 16px;
        border-radius: 6px; font-weight: 700;
    }
    QPushButton#syncBtn:hover { background: #047857; }
    QPushButton#syncBtn:disabled { background: #94a3b8; }
    QPushButton#secondaryBtn {
        background: white; color: #334155; border: 1px solid #cbd5e1;
        padding: 6px 12px; border-radius: 6px; font-weight: 600;
    }
    QPushButton#secondaryBtn:hover {
        background: #f8fafc; border-color: #3b82f6; color: #3b82f6;
    }
    QLineEdit, QComboBox, QPlainTextEdit {
        padding: 6px 10px; border: 1px solid #cbd5e1;
        border-radius: 6px; font-size: 12px;
    }
"""


# ─────────────────────────────────────────────
#  BACKGROUND WORKER — SYNC
# ─────────────────────────────────────────────
class SyncWorker(QThread):
    """Background worker for syncing the offline queue."""

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, svc: FieldMobileService, project_id: int):
        super().__init__()
        self.svc = svc
        self.project_id = project_id

    def run(self):
        try:
            result = self.svc.sync_pending(self.project_id)
            self.finished.emit(result)
        except Exception as e:
            logger.exception("Background Mobile Hub Sync failed")
            self.error.emit(str(e))


# ─────────────────────────────────────────────
#  KPI CARD
# ─────────────────────────────────────────────
class MobileKPICard(QFrame):
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
                  highlight_color: Optional[str] = None):
        self.val_lbl.setText(str(text))
        if highlight_color:
            self.val_lbl.setStyleSheet(
                f"color: {highlight_color}; "
                f"font-size: 19px; font-weight: 800;"
            )
        else:
            self.val_lbl.setStyleSheet(
                "color: #0f172a; font-size: 19px; font-weight: 800;"
            )


# ─────────────────────────────────────────────
#  EVENT CAPTURE DIALOG
# ─────────────────────────────────────────────
class EventCaptureDialog(QDialog):
    """Captures supplementary parameters for accurate engineering traceability."""

    def __init__(self, parent=None, event_type: str = "FITUP",
                 entity_type: str = "Weld", entity_key: str = ""):
        super().__init__(parent)
        self.event_type = event_type
        self.entity_type = entity_type
        self.entity_key = entity_key
        self.custom_payload: dict = {}

        self.setWindowTitle(
            f"Field Workflow: {event_type} on {entity_type} [{entity_key}]"
        )
        self.setMinimumWidth(460)
        self.setStyleSheet(MOBILE_HUB_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.lbl_target = QLabel(
            f"<b>Target:</b> {entity_type} &middot; "
            f"<span style='color:#2563eb;'>{entity_key}</span>"
        )
        form.addRow("Context:", self.lbl_target)

        self.txt_notes = QLineEdit()
        self.txt_notes.setPlaceholderText(
            "Optional field observations or remarks..."
        )

        # ── Event-specific fields ────────────────────────────
        if event_type == "FITUP":
            self.spn_root = QDoubleSpinBox()
            self.spn_root.setRange(0, 50)
            self.spn_root.setValue(3.2)
            self.spn_root.setSuffix(" mm")

            self.spn_hilow = QDoubleSpinBox()
            self.spn_hilow.setRange(0, 50)
            self.spn_hilow.setValue(0.8)
            self.spn_hilow.setSuffix(" mm")

            form.addRow("Root Gap:", self.spn_root)
            form.addRow("Hi-Low Alignment:", self.spn_hilow)

        elif event_type == "WELD":
            self.txt_welder = QLineEdit()
            self.txt_welder.setPlaceholderText(
                "Welder Stamp (e.g. W-05)"
            )
            self.cmb_proc = QComboBox()
            self.cmb_proc.addItems([
                "GTAW + SMAW", "SMAW", "GTAW", "FCAW", "GMAW",
            ])
            form.addRow("Welder ID/Stamp *:", self.txt_welder)
            form.addRow("Welding Process:", self.cmb_proc)

        elif event_type == "NDT_REQUEST":
            self.cmb_ndt = QComboBox()
            self.cmb_ndt.addItems([
                "RT (Radiographic Testing)",
                "UT (Ultrasonic Testing)",
                "PT (Liquid Penetrant)",
                "MT (Magnetic Particle)",
                "PMI",
            ])
            self.cmb_priority = QComboBox()
            self.cmb_priority.addItems([
                "Normal Priority",
                "Urgent / Critical Path",
                "Immediate Hold",
            ])
            form.addRow("Requested NDT Method:", self.cmb_ndt)
            form.addRow("Priority:", self.cmb_priority)

        elif event_type == "REPAIR":
            self.cmb_defect = QComboBox()
            self.cmb_defect.addItems([
                "Lack of Fusion", "Porosity / Cluster",
                "Slag Inclusion", "Crater Crack",
                "Undercut", "Root Concavity",
            ])
            self.txt_loc = QLineEdit()
            self.txt_loc.setPlaceholderText(
                "e.g. 12 to 3 o'clock / Root pass"
            )
            form.addRow("Defect Category *:", self.cmb_defect)
            form.addRow("Defect Clock Location:", self.txt_loc)

        elif event_type in ("QC", "ACCEPTANCE"):
            self.cmb_res = QComboBox()
            self.cmb_res.addItems([
                "Accepted / Passed",
                "Rejected / Punch Listed",
                "Pending Verification",
            ])
            form.addRow("Inspection Result *:", self.cmb_res)

        form.addRow("Field Notes:", self.txt_notes)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_capture = QPushButton("⚡ Confirm & Capture Offline")
        btn_capture.setObjectName("primaryBtn")
        btn_capture.clicked.connect(self._validate_and_accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_capture)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _validate_and_accept(self):
        self.custom_payload = {
            "notes": self.txt_notes.text().strip()
        }

        if self.event_type == "FITUP":
            self.custom_payload["root_gap_mm"] = self.spn_root.value()
            self.custom_payload["hi_low_mm"] = self.spn_hilow.value()

        elif self.event_type == "WELD":
            w_stamp = self.txt_welder.text().strip()
            if not w_stamp:
                QMessageBox.warning(
                    self, "Validation",
                    "Welder Stamp / ID is mandatory."
                )
                return
            self.custom_payload["welder_id"] = w_stamp
            self.custom_payload["process"] = self.cmb_proc.currentText()

        elif self.event_type == "NDT_REQUEST":
            self.custom_payload["ndt_method"] = self.cmb_ndt.currentText()
            self.custom_payload["priority"] = (
                self.cmb_priority.currentText()
            )

        elif self.event_type == "REPAIR":
            self.custom_payload["defect_type"] = (
                self.cmb_defect.currentText()
            )
            self.custom_payload["defect_location"] = (
                self.txt_loc.text().strip()
            )

        elif self.event_type in ("QC", "ACCEPTANCE"):
            self.custom_payload["inspection_result"] = (
                self.cmb_res.currentText()
            )

        self.accept()


# ─────────────────────────────────────────────
#  QR VIEWER DIALOG
# ─────────────────────────────────────────────
class QRViewerDialog(QDialog):
    def __init__(self, parent=None, entity_key: str = "",
                 payload_str: str = "", image_path: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle(f"▣ QR Token Asset – {entity_key}")
        self.setMinimumSize(420, 480)
        self.setStyleSheet(MOBILE_HUB_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel(f"▣ QR Payload: {entity_key}")
        title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #102a43;"
        )
        layout.addWidget(title)

        self.lbl_img = QLabel()
        self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_img.setMinimumSize(220, 220)
        self.lbl_img.setStyleSheet(
            "background: white; border: 2px dashed #cbd5e1; "
            "border-radius: 8px; padding: 10px;"
        )

        if image_path and Path(image_path).is_file():
            pix = QPixmap(image_path).scaled(
                220, 220,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.lbl_img.setPixmap(pix)
        else:
            self.lbl_img.setText(
                "▣ [QR Image Ready]\n"
                "(Scan with PipeAgent Mobile App)"
            )

        layout.addWidget(self.lbl_img)

        self.txt_payload = QPlainTextEdit()
        self.txt_payload.setReadOnly(True)
        self.txt_payload.setPlainText(payload_str)
        self.txt_payload.setMaximumHeight(80)
        layout.addWidget(self.txt_payload)

        btns = QHBoxLayout()

        btn_copy = QPushButton("📋 Copy Payload String")
        btn_copy.setObjectName("secondaryBtn")

        def _copy():
            QApplication.clipboard().setText(payload_str)
            QMessageBox.information(
                self, "Copied", "QR payload copied to clipboard."
            )

        btn_copy.clicked.connect(_copy)
        btns.addWidget(btn_copy)

        btn_close = QPushButton("Close")
        btn_close.setObjectName("primaryBtn")
        btn_close.clicked.connect(self.accept)
        btns.addWidget(btn_close)
        layout.addLayout(btns)


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class MobileFieldTab(QWidget):
    """Offline-first tablet/site operation center."""

    def __init__(self, db: DatabaseManager,
                 session: SessionManager):
        super().__init__()
        self.setObjectName("mobileFieldTab")
        self.db = db
        self.session = session
        self.svc = FieldMobileService(
            db, getattr(session, "username", "DESKTOP")
        )
        self._sync_thread: Optional[SyncWorker] = None
        self._offline_queue_cache: list[dict] = []

        self._build()
        self.setStyleSheet(MOBILE_HUB_STYLESHEET)
        self.refresh()

    # ══════════════════════════════════════════
    #  UI BUILD
    # ══════════════════════════════════════════
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # ── Header ───────────────────────────────────────────
        header_card = QFrame()
        header_card.setObjectName("headerCard")
        hdr_lay = QHBoxLayout(header_card)
        hdr_lay.setContentsMargins(14, 10, 14, 10)

        title_v = QVBoxLayout()
        t = QLabel(
            "📱 Field Mobile Hub | Offline Execution, QR Engine & Sync"
        )
        t.setObjectName("mainTitle")
        s = QLabel(
            "Tablet & Site Operation Center: Rapid One-Tap Capture, "
            "Defect Tagging, Photo Audit, and Secure Sync."
        )
        s.setObjectName("subTitle")
        title_v.addWidget(t)
        title_v.addWidget(s)
        hdr_lay.addLayout(title_v, 1)

        proj_box = QHBoxLayout()
        lbl_p = QLabel("Active Project:")
        lbl_p.setStyleSheet("color: white; font-weight: bold;")
        proj_box.addWidget(lbl_p)

        self.project = QComboBox()
        self.project.setMinimumWidth(220)
        self.project.currentIndexChanged.connect(self.refresh)
        proj_box.addWidget(self.project)

        self.btn_sync = QPushButton("☁️ Sync Pending Queue")
        self.btn_sync.setObjectName("syncBtn")
        self.btn_sync.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.btn_sync.clicked.connect(self.sync)
        proj_box.addWidget(self.btn_sync)
        hdr_lay.addLayout(proj_box)

        root.addWidget(header_card)

        # ── KPI row ──────────────────────────────────────────
        kpi_lay = QHBoxLayout()
        kpi_lay.setSpacing(8)

        self.kpi_pending = MobileKPICard(
            "Offline Queue Pending", "⏳", "#f59e0b"
        )
        self.kpi_synced = MobileKPICard(
            "Events Synced Today", "☁️", "#10b981"
        )
        self.kpi_photos = MobileKPICard(
            "Attached Field Photos", "📷", "#8b5cf6"
        )
        self.kpi_mode = MobileKPICard(
            "Operating Engine Mode", "📶", "#0ea5e9"
        )

        for k in (self.kpi_pending, self.kpi_synced,
                  self.kpi_photos, self.kpi_mode):
            kpi_lay.addWidget(k)
        root.addLayout(kpi_lay)

        # ── Sync progress ────────────────────────────────────
        self.sync_progress = QProgressBar()
        self.sync_progress.setRange(0, 0)
        self.sync_progress.setFixedHeight(6)
        self.sync_progress.setTextVisible(False)
        self.sync_progress.setVisible(False)
        root.addWidget(self.sync_progress)

        # ── Splitter ─────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)

        # Left: one-tap actions
        left_box = QGroupBox("⚡ ONE-TAP FIELD EXECUTION STATION")
        left_lay = QVBoxLayout(left_box)
        left_lay.setContentsMargins(10, 12, 10, 10)
        left_lay.setSpacing(8)

        ctx_row = QHBoxLayout()
        ctx_row.addWidget(QLabel("Target Entity:"))
        self.entity = QComboBox()
        self.entity.addItems(["Weld", "Spool", "Work Front"])
        ctx_row.addWidget(self.entity)

        self.key = QLineEdit()
        self.key.setPlaceholderText(
            "Type or Scan Identifier (e.g. W-01, SP-101)..."
        )
        ctx_row.addWidget(self.key, 1)

        btn_paste = QPushButton("📋 Paste")
        btn_paste.setObjectName("secondaryBtn")
        btn_paste.clicked.connect(
            lambda: self.key.setText(
                QApplication.clipboard().text().strip()
            )
        )
        ctx_row.addWidget(btn_paste)
        left_lay.addLayout(ctx_row)

        # One-tap action grid
        action_grid = QGridLayout()
        action_grid.setSpacing(8)

        labels = [
            ("FITUP", "🔧\n1. Fit-up"),
            ("WELD", "🔥\n2. Weld"),
            ("PHOTO", "📷\nPhoto Audit"),
            ("QC", "🔎\nQC Check"),
            ("NDT_REQUEST", "🧪\nNDT Request"),
            ("REPAIR", "⚠️\nLog Repair"),
            ("ACCEPTANCE", "✅\nAcceptance"),
        ]

        for i, (k, label) in enumerate(labels):
            b = QPushButton(label)
            b.setObjectName("actionBtn")
            b.setMinimumHeight(65)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.clicked.connect(lambda _, x=k: self.capture(x))
            action_grid.addWidget(b, i // 3, i % 3)

        left_lay.addLayout(action_grid)

        # QR & Photo tools
        qr_tools = QHBoxLayout()
        btn_qr = QPushButton("▣ Generate & Display QR")
        btn_qr.setObjectName("secondaryBtn")
        btn_qr.clicked.connect(self.generate_qr)
        qr_tools.addWidget(btn_qr)

        btn_photo = QPushButton("📷 Attach & Tag Photo")
        btn_photo.setObjectName("secondaryBtn")
        btn_photo.clicked.connect(self.attach_photo)
        qr_tools.addWidget(btn_photo)
        left_lay.addLayout(qr_tools)

        left_lay.addWidget(QLabel("<b>Raw Token / Payload Log:</b>"))
        self.payload = QPlainTextEdit()
        self.payload.setReadOnly(True)
        self.payload.setPlaceholderText(
            "QR payload, parsed token string, or captured event "
            "metadata will appear here..."
        )
        self.payload.setMaximumHeight(90)
        left_lay.addWidget(self.payload)

        splitter.addWidget(left_box)

        # Right: live queue
        right_box = QGroupBox(
            "📋 LIVE OFFLINE EVENT QUEUE & AUDIT LOG"
        )
        right_lay = QVBoxLayout(right_box)
        right_lay.setContentsMargins(8, 12, 8, 8)
        right_lay.setSpacing(8)

        filter_bar = QHBoxLayout()
        self.txt_queue_search = QLineEdit()
        self.txt_queue_search.setPlaceholderText(
            "🔍 Filter Queue (Key, Event, Operator, Payload)..."
        )
        self.txt_queue_search.textChanged.connect(
            self._apply_queue_filters
        )
        filter_bar.addWidget(self.txt_queue_search, 1)

        self.cmb_filter_event = QComboBox()
        self.cmb_filter_event.addItem("All Events", None)
        for ev in EVENT_BADGES.keys():
            self.cmb_filter_event.addItem(ev, ev)
        self.cmb_filter_event.currentIndexChanged.connect(
            self._apply_queue_filters
        )
        filter_bar.addWidget(self.cmb_filter_event)

        btn_exp_queue = QPushButton("📥 Export CSV")
        btn_exp_queue.setObjectName("secondaryBtn")
        btn_exp_queue.clicked.connect(self._export_queue_csv)
        filter_bar.addWidget(btn_exp_queue)

        right_lay.addLayout(filter_bar)

        self.queue_table = QTableWidget(0, 6)
        self.queue_table.setHorizontalHeaderLabels([
            "ID / UUID", "Timestamp", "Workflow Action",
            "Target Entity", "Key / ID", "Captured Data / Metadata",
        ])
        self.queue_table.setAlternatingRowColors(True)
        # ✅ FIXED: use QAbstractItemView enums
        self.queue_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.queue_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.queue_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.setSortingEnabled(True)
        self.queue_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.queue_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.queue_table.customContextMenuRequested.connect(
            self._show_queue_context_menu
        )
        right_lay.addWidget(self.queue_table)

        splitter.addWidget(right_box)
        splitter.setSizes([480, 720])
        root.addWidget(splitter, 1)

    # ══════════════════════════════════════════
    #  REFRESH / PROJECT SELECTION
    # ══════════════════════════════════════════
    def refresh(self):
        cur = self.project.currentData()
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
            logger.exception(
                "Failed to load projects in MobileFieldTab"
            )

        if cur is not None:
            idx = self.project.findData(cur)
            if idx >= 0:
                self.project.setCurrentIndex(idx)

        self.project.blockSignals(False)

        pid = self.project.currentData()

        # ── Pending count ────────────────────────────────────
        pending_cnt = 0
        if pid:
            try:
                pending_cnt = self.svc.pending_count(pid)
            except Exception:
                logger.warning(
                    "Could not fetch pending count", exc_info=True
                )

        self.kpi_pending.set_value(
            str(pending_cnt),
            highlight_color="#f59e0b" if pending_cnt > 0 else "#10b981",
        )
        self.kpi_mode.set_value(
            "Offline-First (Active)", highlight_color="#059669"
        )

        self._load_offline_queue_records()

    def _load_offline_queue_records(self):
        pid = self.project.currentData()
        self._offline_queue_cache = []

        if not pid:
            self.queue_table.setRowCount(0)
            return

        try:
            events = None
            if hasattr(self.svc, "get_pending_events"):
                events = self.svc.get_pending_events(pid)
            else:
                events = getattr(self.svc, "_queue", [])

            for ev in events or []:
                self._offline_queue_cache.append({
                    "id": ev.get("id", "EV-LOC-01"),
                    "timestamp": ev.get(
                        "timestamp",
                        datetime.datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                    ),
                    "event_type": ev.get("event", "FITUP"),
                    "entity_type": ev.get("entity_type", "Weld"),
                    "entity_key": ev.get("entity_key", "—"),
                    "payload": ev.get("payload", {}),
                })
        except Exception as e:
            logger.warning(f"Failed to fetch queue events: {e}")

        self._apply_queue_filters()

    def _apply_queue_filters(self):
        query = self.txt_queue_search.text().strip().lower()
        ev_filter = self.cmb_filter_event.currentData()

        self.queue_table.setSortingEnabled(False)
        self.queue_table.setRowCount(0)

        photos_count = 0
        for ev in self._offline_queue_cache:
            if ev_filter and ev["event_type"] != ev_filter:
                continue

            payload = ev["payload"]
            payload_str = (
                json.dumps(payload)
                if isinstance(payload, dict)
                else str(payload)
            )

            if query:
                combined = (
                    f"{ev['id']} {ev['event_type']} "
                    f"{ev['entity_type']} {ev['entity_key']} "
                    f"{payload_str}"
                ).lower()
                if query not in combined:
                    continue

            if ev["event_type"] == "PHOTO":
                photos_count += 1

            r = self.queue_table.rowCount()
            self.queue_table.insertRow(r)

            self.queue_table.setItem(
                r, 0, QTableWidgetItem(str(ev["id"]))
            )
            self.queue_table.setItem(
                r, 1, QTableWidgetItem(str(ev["timestamp"]))
            )

            ev_item = QTableWidgetItem(ev["event_type"])
            badge = EVENT_BADGES.get(
                ev["event_type"], DEFAULT_EVENT_BADGE
            )
            ev_item.setText(f"{badge['icon']} {ev['event_type']}")
            ev_item.setBackground(QBrush(QColor(badge["bg"])))
            ev_item.setForeground(QBrush(QColor(badge["fg"])))
            font = ev_item.font()
            font.setBold(True)
            ev_item.setFont(font)
            self.queue_table.setItem(r, 2, ev_item)

            self.queue_table.setItem(
                r, 3, QTableWidgetItem(str(ev["entity_type"]))
            )
            self.queue_table.setItem(
                r, 4, QTableWidgetItem(str(ev["entity_key"]))
            )
            self.queue_table.setItem(
                r, 5, QTableWidgetItem(payload_str)
            )

        self.queue_table.setSortingEnabled(True)
        self.kpi_photos.set_value(str(photos_count))

    # ══════════════════════════════════════════
    #  ONE-TAP CAPTURE
    # ══════════════════════════════════════════
    def capture(self, event: str):
        pid = self.project.currentData()
        key = self.key.text().strip()

        if not pid or not key:
            QMessageBox.warning(
                self, "Field Validation",
                "Please select a Project and enter/scan a "
                "Target Identifier."
            )
            self.key.setFocus()
            return

        et = self.entity.currentText()

        dlg = EventCaptureDialog(
            self, event_type=event, entity_type=et, entity_key=key
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        payload = {
            "entity_key": key,
            "captured_by": getattr(self.session, "username", "admin"),
            "event": event,
            "mode": "offline-first",
            "timestamp": datetime.datetime.now().isoformat(),
            **dlg.custom_payload,
        }

        try:
            eid = self.svc.capture_event(pid, event, et, None, payload)
            self.payload.setPlainText(json.dumps(payload, indent=2))

            self._offline_queue_cache.insert(0, {
                "id": str(eid)[:12],
                "timestamp": datetime.datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "event_type": event,
                "entity_type": et,
                "entity_key": key,
                "payload": payload,
            })
            self._apply_queue_filters()

            pending_cnt = self.svc.pending_count(pid)
            self.kpi_pending.set_value(
                str(pending_cnt), highlight_color="#f59e0b"
            )

            QMessageBox.information(
                self, "Offline Event Logged",
                f"Action '{event}' saved to local offline database.\n"
                f"UUID: {eid}"
            )
        except Exception as e:
            logger.exception("Failed to capture mobile event")
            QMessageBox.critical(
                self, "Capture Error",
                f"Could not log offline action:\n{e}"
            )

    def generate_qr(self):
        pid = self.project.currentData()
        key = self.key.text().strip()

        if not pid or not key:
            QMessageBox.warning(
                self, "QR Generator",
                "Project and Entity Identifier are required."
            )
            return

        et = self.entity.currentText()
        payload = self.svc.make_qr_payload(et, key, pid)
        self.payload.setPlainText(payload)

        temp_qr_path = str(Path.home() / f"PipeAgent_QR_{key}.png")
        saved_path = None
        try:
            saved_path = self.svc.generate_qr(payload, temp_qr_path)
        except Exception:
            logger.warning("QR image generation failed", exc_info=True)

        dlg = QRViewerDialog(
            self, entity_key=key,
            payload_str=payload, image_path=saved_path,
        )
        dlg.exec()

    def attach_photo(self):
        pid = self.project.currentData()
        key = self.key.text().strip()

        if not pid or not key:
            QMessageBox.warning(
                self, "Photo Audit",
                "Please specify an Identifier (Weld ID, Spool No) "
                "before taking/attaching a photo."
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Select Field Inspection Photo", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.heic)",
        )
        if not path:
            return

        u_name = getattr(self.session, "username", "admin")
        payload = {
            "entity_key": key,
            "file_path": path,
            "captured_by": u_name,
            "timestamp": datetime.datetime.now().isoformat(),
        }

        try:
            self.svc.capture_event(
                pid, "PHOTO", self.entity.currentText(), None, payload
            )
            self.svc.attach_photo(
                pid, self.entity.currentText(), 0,
                path, f"Field QC Photo for {key}", u_name,
            )
            self.refresh()
            QMessageBox.information(
                self, "Photo Tagged",
                f"Field photo successfully attached to {key} "
                f"and queued for sync."
            )
        except Exception as e:
            logger.exception("Photo attachment failed")
            QMessageBox.critical(
                self, "Error", f"Failed to attach photo:\n{e}"
            )

    # ══════════════════════════════════════════
    #  SYNC WORKER
    # ══════════════════════════════════════════
    def sync(self):
        pid = self.project.currentData()
        if not pid:
            QMessageBox.warning(
                self, "Sync", "Select a project first."
            )
            return

        # ✅ FIXED: cleanup any previous sync thread
        self._stop_sync_thread()

        self.btn_sync.setEnabled(False)
        self.btn_sync.setText("☁️ Syncing in progress...")
        self.sync_progress.setVisible(True)

        self._sync_thread = SyncWorker(self.svc, pid)
        self._sync_thread.finished.connect(self._on_sync_success)
        self._sync_thread.error.connect(self._on_sync_failed)
        self._sync_thread.start()

    def _stop_sync_thread(self):
        """Gracefully stop any in-flight sync worker."""
        if self._sync_thread is None:
            return
        try:
            if self._sync_thread.isRunning():
                self._sync_thread.requestInterruption()
                self._sync_thread.wait(2000)
            self._sync_thread.deleteLater()
        except Exception:
            logger.warning(
                "Sync worker stop failed", exc_info=True
            )
        self._sync_thread = None

    def _on_sync_success(self, r: dict):
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("☁️ Sync Pending Queue")
        self.sync_progress.setVisible(False)

        synced = r.get("synced", 0)
        failed = r.get("failed", 0)

        self.kpi_synced.set_value(
            str(synced), highlight_color="#10b981"
        )
        self.refresh()

        QMessageBox.information(
            self, "Sync Complete",
            f"Data synchronization finished:\n\n"
            f"• Successfully Uploaded: {synced}\n"
            f"• Failed / Conflicts: {failed}"
        )

        # ✅ FIXED: release thread resources
        if self._sync_thread is not None:
            self._sync_thread.deleteLater()
            self._sync_thread = None

    def _on_sync_failed(self, error_msg: str):
        self.btn_sync.setEnabled(True)
        self.btn_sync.setText("☁️ Sync Pending Queue")
        self.sync_progress.setVisible(False)
        QMessageBox.critical(
            self, "Sync Fault",
            f"Failed to synchronize queue with remote server:\n"
            f"{error_msg}"
        )

        # ✅ FIXED: release thread resources
        if self._sync_thread is not None:
            self._sync_thread.deleteLater()
            self._sync_thread = None

    # ══════════════════════════════════════════
    #  QUEUE CONTEXT MENU
    # ══════════════════════════════════════════
    def _show_queue_context_menu(self, pos):
        selected_rows = self.queue_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 18px; }"
        )

        act_view = QAction("🔍 Inspect Raw Payload JSON", self)
        act_view.triggered.connect(self._inspect_selected_payload)
        menu.addAction(act_view)

        act_copy = QAction("📋 Copy Entity Key", self)
        act_copy.triggered.connect(self._copy_selected_key)
        menu.addAction(act_copy)

        menu.exec(self.queue_table.viewport().mapToGlobal(pos))

    def _inspect_selected_payload(self):
        row = self.queue_table.currentRow()
        if row >= 0:
            item = self.queue_table.item(row, 5)
            if item:
                self.payload.setPlainText(item.text())

    def _copy_selected_key(self):
        row = self.queue_table.currentRow()
        if row >= 0:
            item = self.queue_table.item(row, 4)
            if item:
                QApplication.clipboard().setText(item.text())

    # ══════════════════════════════════════════
    #  EXPORT
    # ══════════════════════════════════════════
    def _export_queue_csv(self):
        if self.queue_table.rowCount() == 0:
            QMessageBox.warning(
                self, "Export", "Offline event queue is empty."
            )
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Offline Queue",
            f"Mobile_Offline_Queue_{timestamp}.csv",
            "CSV Files (*.csv)",
        )
        if not filename:
            return

        try:
            with open(filename, mode="w", newline="",
                      encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                headers = [
                    self.queue_table.horizontalHeaderItem(c).text()
                    for c in range(self.queue_table.columnCount())
                ]
                writer.writerow(headers)

                for r in range(self.queue_table.rowCount()):
                    if not self.queue_table.isRowHidden(r):
                        row_vals = [
                            self.queue_table.item(r, c).text().strip()
                            if self.queue_table.item(r, c) else ""
                            for c in range(self.queue_table.columnCount())
                        ]
                        writer.writerow(row_vals)

            QMessageBox.information(
                self, "Export Complete",
                f"Queue audit log exported to:\n{filename}"
            )
        except Exception as e:
            logger.exception("Queue CSV export failed")
            QMessageBox.critical(
                self, "Export Error",
                f"Could not export CSV file:\n{e}"
            )

    # ══════════════════════════════════════════
    #  CLEANUP
    # ══════════════════════════════════════════
    def closeEvent(self, event):
        """Ensure the sync thread is stopped before widget closes."""
        self._stop_sync_thread()
        super().closeEvent(event)