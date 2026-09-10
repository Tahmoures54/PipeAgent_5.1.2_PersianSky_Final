# -*- coding: utf-8 -*-
"""
Access-inspired Site Field Control – PipeAgent
==============================================
WJCS + Draft/Approved Reports + Project Actions + Users.
"""
from __future__ import annotations

import csv
import logging
import datetime
from datetime import timezone
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import (
    QDesktopServices, QTextDocument, QColor, QFont,
    QCursor, QAction, QBrush,
)
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QDialog, QFormLayout,
    QLineEdit, QComboBox, QDialogButtonBox, QTabWidget,
    QSplitter, QTextEdit, QFileDialog, QDateEdit, QGroupBox,
    QFrame, QMenu, QApplication, QAbstractItemView,
    QCheckBox, QSizePolicy,
)

from config import EXPORT_DIR
from db.manager import DatabaseManager
from db.models import (
    Project, User, Weld, WeldReportDraft, WeldReport,
    FitupReportDraft, FitupReport, ProjectAction,
)
from security.session import SessionManager
from services.reporting_service import ReportingService

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  UTIL
# ─────────────────────────────────────────────
def _utcnow():
    """Naive UTC — replacement for deprecated datetime.utcnow()."""
    return datetime.datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────
#  STATUS COLOR MAPS
# ─────────────────────────────────────────────
RESULT_COLORS = {
    "Accepted": {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Rejected": {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Pending":  {"bg": "#fef3c7", "fg": "#92400e", "icon": "⏳"},
    "N/A":      {"bg": "#f1f5f9", "fg": "#64748b", "icon": "—"},
}

STATUS_COLORS = {
    "Draft":     {"bg": "#dbeafe", "fg": "#1e40af", "icon": "📝"},
    "Approved":  {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Rejected":  {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Submitted": {"bg": "#fef3c7", "fg": "#92400e", "icon": "📤"},
    "On Hold":   {"bg": "#e5e7eb", "fg": "#374151", "icon": "⏸"},
    "Closed":    {"bg": "#dcfce7", "fg": "#166534", "icon": "✔"},
    "Open":      {"bg": "#fef3c7", "fg": "#92400e", "icon": "🔓"},
}

DEFAULT_COLOR = {"bg": "#f8fafc", "fg": "#475569", "icon": "•"}

ROLE_COLORS = {
    "admin":     {"bg": "#fee2e2", "fg": "#991b1b"},
    "engineer":  {"bg": "#dbeafe", "fg": "#1e40af"},
    "inspector": {"bg": "#e0e7ff", "fg": "#3730a3"},
    "welder":    {"bg": "#fef3c7", "fg": "#92400e"},
    "viewer":    {"bg": "#f1f5f9", "fg": "#64748b"},
}


# ─────────────────────────────────────────────
#  STYLESHEET
# ─────────────────────────────────────────────
MAIN_STYLESHEET = """
    QWidget#fieldControlTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #1e3c72, stop:1 #2a5298);
        border-radius: 14px; padding: 16px;
    }
    QLabel#mainTitle {
        color: white; font-size: 22px; font-weight: 800;
    }
    QLabel#mainSubtitle { color: #cbd5e1; font-size: 12px; }
    QTabWidget::pane {
        border: 1px solid #e2e8f0; border-radius: 10px;
        background: white; top: -1px;
    }
    QTabBar::tab {
        background: transparent; color: #64748b;
        padding: 10px 20px; border: none;
        border-bottom: 3px solid transparent;
        font-size: 12px; font-weight: 700; margin-right: 4px;
    }
    QTabBar::tab:selected {
        color: #1e40af; border-bottom-color: #3b82f6; background: white;
    }
    QTabBar::tab:hover:!selected {
        color: #1e293b; background: #f1f5f9;
    }
    QFrame#filterCard, QFrame#statsCard {
        background: white; border: 1px solid #e2e8f0;
        border-radius: 10px; padding: 12px;
    }
    QLineEdit, QDateEdit {
        padding: 8px 12px; border: 2px solid #e2e8f0;
        border-radius: 6px; font-size: 13px; background: white;
    }
    QLineEdit:focus, QDateEdit:focus { border-color: #3b82f6; }
    QLineEdit:hover, QDateEdit:hover { border-color: #94a3b8; }
    QComboBox {
        padding: 8px 12px; border: 2px solid #e2e8f0;
        border-radius: 6px; font-size: 13px;
        background: white; min-width: 140px;
    }
    QComboBox:focus, QComboBox:hover { border-color: #3b82f6; }
    QComboBox::drop-down { border: none; width: 26px; }
    QComboBox::down-arrow {
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid #64748b; margin-right: 8px;
    }
    QPushButton#primaryBtn {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #3b82f6, stop:1 #2563eb);
        color: white; border: none; padding: 8px 18px;
        border-radius: 6px; font-size: 12px; font-weight: 700;
    }
    QPushButton#primaryBtn:hover {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #2563eb, stop:1 #1d4ed8);
    }
    QPushButton#successBtn {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #10b981, stop:1 #059669);
        color: white; border: none; padding: 8px 18px;
        border-radius: 6px; font-size: 12px; font-weight: 700;
    }
    QPushButton#successBtn:hover {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #059669, stop:1 #047857);
    }
    QPushButton#warningBtn {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #f59e0b, stop:1 #d97706);
        color: white; border: none; padding: 8px 18px;
        border-radius: 6px; font-size: 12px; font-weight: 700;
    }
    QPushButton#warningBtn:hover {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #d97706, stop:1 #b45309);
    }
    QPushButton#dangerBtn {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #ef4444, stop:1 #dc2626);
        color: white; border: none; padding: 8px 18px;
        border-radius: 6px; font-size: 12px; font-weight: 700;
    }
    QPushButton#dangerBtn:hover {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #dc2626, stop:1 #b91c1c);
    }
    QPushButton#secondaryBtn {
        background: white; color: #374151;
        border: 2px solid #d1d5db;
        padding: 7px 16px; border-radius: 6px;
        font-size: 12px; font-weight: 600;
    }
    QPushButton#secondaryBtn:hover {
        background: #f9fafb; border-color: #3b82f6; color: #3b82f6;
    }
    QTableWidget {
        background: white; border: 1px solid #e2e8f0;
        border-radius: 10px; gridline-color: #f1f5f9;
        font-size: 12px;
        selection-background-color: #dbeafe;
        selection-color: #1e293b;
        alternate-background-color: #f8fafc;
    }
    QTableWidget::item { padding: 6px 8px; border-bottom: 1px solid #f1f5f9; }
    QTableWidget::item:selected { background: #dbeafe; }
    QTableWidget::item:hover { background: #f0f7ff; }
    QHeaderView::section {
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #f8fafc, stop:1 #eef2f7);
        color: #475569; font-weight: 700; font-size: 11px;
        padding: 9px 8px; border: none;
        border-bottom: 2px solid #e2e8f0;
        border-right: 1px solid #e2e8f0;
    }
    QHeaderView::section:hover { background: #e2e8f0; }
    QScrollBar:vertical {
        background: #f1f5f9; width: 10px; border-radius: 5px;
    }
    QScrollBar::handle:vertical {
        background: #94a3b8; border-radius: 5px; min-height: 30px;
    }
    QScrollBar::handle:vertical:hover { background: #64748b; }
"""


# ─────────────────────────────────────────────
#  STAT CARD
# ─────────────────────────────────────────────
class StatCard(QFrame):
    """Small KPI card with icon + value + label."""

    def __init__(self, icon: str, label: str, value: str = "0",
                 color: str = "#3b82f6"):
        super().__init__()
        self.setObjectName("statsCard")
        self.setFixedHeight(75)
        self.setMinimumWidth(120)

        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(12, 8, 12, 8)

        top = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"font-size: 20px; color: {color};")
        top.addWidget(icon_lbl)
        top.addStretch()

        self.value_lbl = QLabel(str(value))
        self.value_lbl.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {color};"
        )
        top.addWidget(self.value_lbl)
        layout.addLayout(top)

        text_lbl = QLabel(label)
        text_lbl.setStyleSheet(
            "font-size: 10px; color: #64748b; font-weight: 500;"
        )
        text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text_lbl)

    def set_value(self, v):
        self.value_lbl.setText(str(v))


# ─────────────────────────────────────────────
#  TABLE HELPER
# ─────────────────────────────────────────────
def _set_table_enhanced(
    table: QTableWidget,
    headers: list,
    rows: list,
    color_columns: dict | None = None,
) -> None:
    """Populate a table with smart color-coding.

    color_columns: {col_index: 'result'|'status'|'role'}
    """
    table.clear()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    table.setSortingEnabled(False)

    color_columns = color_columns or {}

    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            text = "" if value is None else str(value)
            item = QTableWidgetItem(text)

            if c in color_columns:
                kind = color_columns[c]
                palette = None
                if kind == "result":
                    palette = RESULT_COLORS.get(text, DEFAULT_COLOR)
                elif kind == "status":
                    palette = STATUS_COLORS.get(text, DEFAULT_COLOR)
                elif kind == "role":
                    palette = ROLE_COLORS.get(text.lower(), DEFAULT_COLOR)

                if palette:
                    item.setBackground(QColor(palette["bg"]))
                    item.setForeground(QColor(palette["fg"]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                    if "icon" in palette:
                        item.setText(f"{palette['icon']} {text}")

            if c == 0:
                item.setData(Qt.ItemDataRole.UserRole, text)

            table.setItem(r, c, item)

    # ✅ FIXED: use QAbstractItemView enums (not QTableWidget)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents
    )
    table.horizontalHeader().setStretchLastSection(True)
    table.setSelectionBehavior(
        QAbstractItemView.SelectionBehavior.SelectRows
    )
    table.setSelectionMode(
        QAbstractItemView.SelectionMode.ExtendedSelection
    )
    table.setAlternatingRowColors(True)
    table.setEditTriggers(
        QAbstractItemView.EditTrigger.NoEditTriggers
    )
    table.verticalHeader().setVisible(False)
    table.setSortingEnabled(True)


# ─────────────────────────────────────────────
#  FIELD REPORT DIALOG
# ─────────────────────────────────────────────
class FieldReportDialog(QDialog):
    """Create a Draft Weld or Fit-up report."""

    def __init__(self, parent, kind, projects, welds, username):
        super().__init__(parent)
        self.kind = kind
        self.username = username
        self.setWindowTitle(
            f"📝 New Draft — {'Weld' if kind == 'weld' else 'Fit-up'} Report"
        )
        self.resize(680, 780)
        self.setStyleSheet(MAIN_STYLESHEET)

        main = QVBoxLayout(self)
        main.setSpacing(10)
        main.setContentsMargins(16, 16, 16, 16)

        title_lbl = QLabel(
            f"📝 New {'Weld' if kind == 'weld' else 'Fit-up'} Draft Report"
        )
        title_lbl.setStyleSheet(
            "font-size: 18px; font-weight: 800; color: #1e3c72; padding: 8px 0;"
        )
        main.addWidget(title_lbl)

        form = QFormLayout()
        form.setSpacing(8)

        self.project = QComboBox()
        for p in projects:
            self.project.addItem(f"{p.project_code} – {p.title}", p.id)

        self.weld = QComboBox()
        self.weld.addItem("— No linked weld —", None)
        self.weld_objects = {}
        for w in welds:
            self.weld_objects[w.id] = w
            self.weld.addItem(f"{w.weld_id} | {w.line_number or ''}", w.id)

        self.report_no = QLineEdit()
        self.report_no.setPlaceholderText("e.g. WR-2024-001")
        self.line = QLineEdit()
        self.iso = QLineEdit()
        self.weld_no = QLineEdit()
        self.spool = QLineEdit()
        self.person = QLineEdit()
        self.contractor = QLineEdit()
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(datetime.date.today())
        self.result = QComboBox()
        self.result.addItems(["Pending", "Accepted", "Rejected"])
        self.remarks = QTextEdit()
        self.remarks.setMaximumHeight(80)
        self.weld.currentIndexChanged.connect(self._sync_linked_weld)

        for label, widget in [
            ("Project *", self.project),
            ("Joint / Weld", self.weld),
            ("Report No *", self.report_no),
            ("Line No", self.line),
            ("ISO No", self.iso),
            ("Weld No", self.weld_no),
            ("Spool No", self.spool),
            ("Person", self.person),
            ("Contractor", self.contractor),
            ("Date", self.date_edit),
        ]:
            form.addRow(label, widget)

        if kind == "weld":
            self.process = QComboBox()
            self.process.addItems([
                "SMAW", "GTAW", "GTAW+SMAW", "GMAW",
                "FCAW", "SAW", "Other",
            ])
            self.joint_type = QComboBox()
            self.joint_type.addItems([
                "Butt", "Fillet", "Socket", "Flange",
                "Branch (Olet)", "Lap",
            ])
            self.wps = QLineEdit()
            self.filler = QLineEdit()
            self.preheat = QLineEdit()
            self.rt_no = QLineEdit()
            self.pt_no = QLineEdit()
            self.ut_no = QLineEdit()
            self.rt_result = QComboBox()
            self.pt_result = QComboBox()
            self.ut_result = QComboBox()
            for cb in (self.rt_result, self.pt_result, self.ut_result):
                cb.addItems(["Pending", "Accepted", "Rejected", "N/A"])

            form.addRow("Joint Type", self.joint_type)
            form.addRow("Process", self.process)
            form.addRow("WPS", self.wps)
            form.addRow("Filler", self.filler)
            form.addRow("Preheat", self.preheat)
            form.addRow("RT No / Result",
                        self._pair(self.rt_no, self.rt_result))
            form.addRow("PT No / Result",
                        self._pair(self.pt_no, self.pt_result))
            form.addRow("UT No / Result",
                        self._pair(self.ut_no, self.ut_result))
        else:
            self.fitup_no = QLineEdit()
            self.root_gap = QLineEdit()
            self.hi_low = QLineEdit()
            self.alignment = QLineEdit()
            self.bevel = QLineEdit()
            self.cleanliness = QLineEdit()
            self.tack = QLineEdit()

            form.addRow("Fit-up No", self.fitup_no)
            for label, widget in [
                ("Root Gap", self.root_gap),
                ("Hi-Low", self.hi_low),
                ("Alignment", self.alignment),
                ("Bevel", self.bevel),
                ("Cleanliness", self.cleanliness),
                ("Tack Quality", self.tack),
            ]:
                form.addRow(label, widget)

        form.addRow("Result", self.result)
        form.addRow("Remarks", self.remarks)
        main.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        main.addWidget(buttons)

    def _sync_linked_weld(self):
        weld = self.weld_objects.get(self.weld.currentData())
        if not weld:
            return
        try:
            self.line.setText(weld.line_number or "")
            self.iso.setText(getattr(weld, "iso_number", "") or "")
            self.weld_no.setText(weld.weld_id or "")
            self.person.setText(
                weld.welder_name or weld.welder_id or ""
            )
            spool = getattr(weld, "spool", None)
            if spool:
                self.spool.setText(
                    getattr(spool, "spool_number", "") or ""
                )
            if self.kind == "fitup":
                self.person.setText(
                    getattr(weld, "fitup_inspector", "") or ""
                )
        except Exception as e:
            logger.warning(f"Sync linked weld failed: {e}")

    def _pair(self, a, b):
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(6)
        l.addWidget(a)
        l.addWidget(b)
        return w

    def _validate_and_accept(self):
        if not self.project.currentData():
            QMessageBox.warning(
                self, "Validation", "Please select a project."
            )
            return
        if not self.report_no.text().strip():
            QMessageBox.warning(
                self, "Validation", "Report No. is required."
            )
            self.report_no.setFocus()
            return
        self.accept()

    def data(self):
        d = dict(
            project_id=self.project.currentData(),
            weld_pk=self.weld.currentData(),
            report_no=self.report_no.text().strip(),
            line_number=self.line.text().strip(),
            iso_number=self.iso.text().strip(),
            weld_no=self.weld_no.text().strip(),
            spool_no=self.spool.text().strip(),
            person=self.person.text().strip(),
            contractor=self.contractor.text().strip(),
            work_date=self.date_edit.date().toPyDate(),
            result=self.result.currentText(),
            remarks=self.remarks.toPlainText().strip(),
        )
        if self.kind == "weld":
            d.update(
                process=self.process.currentText(),
                joint_type=self.joint_type.currentText(),
                wps_id=self.wps.text().strip(),
                filler=self.filler.text().strip(),
                preheat=self.preheat.text().strip(),
                rt_no=self.rt_no.text().strip(),
                rt_result=self.rt_result.currentText(),
                pt_no=self.pt_no.text().strip(),
                pt_result=self.pt_result.currentText(),
                ut_no=self.ut_no.text().strip(),
                ut_result=self.ut_result.currentText(),
            )
        else:
            d.update(
                fitup_no=self.fitup_no.text().strip(),
                fitter=self.person.text().strip(),
                root_gap=self.root_gap.text().strip(),
                hi_low=self.hi_low.text().strip(),
                alignment=self.alignment.text().strip(),
                bevel=self.bevel.text().strip(),
                cleanliness=self.cleanliness.text().strip(),
                tack_quality=self.tack.text().strip(),
            )
        return d


# ─────────────────────────────────────────────
#  REJECT REASON DIALOG
# ─────────────────────────────────────────────
class RejectReasonDialog(QDialog):
    """Dialog requiring a rejection reason."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("❌ Reject Draft")
        self.setMinimumWidth(450)
        self.setStyleSheet(MAIN_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("❌ Reject Draft Report")
        title.setStyleSheet(
            "font-size: 16px; font-weight: 800; color: #991b1b;"
        )
        layout.addWidget(title)

        layout.addWidget(QLabel("Reason for rejection (required):"))

        self.reason = QTextEdit()
        self.reason.setPlaceholderText(
            "Explain why this report is being rejected…"
        )
        self.reason.setMinimumHeight(120)
        layout.addWidget(self.reason)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate(self):
        if not self.reason.toPlainText().strip():
            QMessageBox.warning(
                self, "Validation",
                "You must provide a reason for rejection."
            )
            return
        self.accept()

    def get_reason(self) -> str:
        return self.reason.toPlainText().strip()


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class FieldControlTab(QWidget):
    """
    Site Field Control tab.
    """

    def __init__(self, db: DatabaseManager, session: SessionManager):
        super().__init__()
        self.setObjectName("fieldControlTab")
        self.db = db
        self.session = session
        self.reporting = ReportingService(db)

        self._build()
        self.setStyleSheet(MAIN_STYLESHEET)
        self.refresh_all()

    # ═══════════════════════════════════════
    #  UI BUILD
    # ═══════════════════════════════════════
    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        root.addWidget(self._build_header())
        root.addLayout(self._build_stat_cards())

        self.tabs = QTabWidget()
        self.weld_drafts = QTableWidget()
        self.fit_drafts = QTableWidget()
        self.weld_official = QTableWidget()
        self.fit_official = QTableWidget()
        self.actions = QTableWidget()
        self.users = QTableWidget()

        self.tabs.addTab(
            self._report_page(self.weld_drafts, "weld", is_official=False),
            "📝 Weld Drafts",
        )
        self.tabs.addTab(
            self._report_page(self.fit_drafts, "fitup", is_official=False),
            "📝 Fit-up Drafts",
        )
        self.tabs.addTab(
            self._report_page(self.weld_official, "weld", is_official=True),
            "✅ Official Weld Reports",
        )
        self.tabs.addTab(
            self._report_page(self.fit_official, "fitup", is_official=True),
            "✅ Official Fit-up Reports",
        )
        self.tabs.addTab(self._actions_page(), "📋 Project Actions")
        self.tabs.addTab(self._users_page(), "👥 Employees")

        root.addWidget(self.tabs, stretch=1)
        root.addWidget(self._build_status_bar())

    def _build_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("headerCard")
        layout = QVBoxLayout(card)
        layout.setSpacing(4)

        t = QLabel(
            "🧰 Site Field Control  |  WJCS · Fit-up · Weld Reports · Actions"
        )
        t.setObjectName("mainTitle")
        layout.addWidget(t)

        s = QLabel(
            "Draft → QC Approval → Official Register. "
            "Auditable, role-based, traceable."
        )
        s.setObjectName("mainSubtitle")
        layout.addWidget(s)
        return card

    def _build_stat_cards(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)

        self.stat_drafts = StatCard("📝", "Draft Reports", "0", "#3b82f6")
        self.stat_official = StatCard("✅", "Official Reports", "0", "#10b981")
        self.stat_pending = StatCard("⏳", "Pending Approval", "0", "#f59e0b")
        self.stat_rejected = StatCard("❌", "Rejected", "0", "#ef4444")
        self.stat_actions = StatCard("📋", "Total Actions", "0", "#8b5cf6")
        self.stat_users = StatCard("👥", "Active Users", "0", "#0ea5e9")

        for c in (self.stat_drafts, self.stat_official, self.stat_pending,
                  self.stat_rejected, self.stat_actions, self.stat_users):
            layout.addWidget(c)
        return layout

    def _build_status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setStyleSheet(
            "background: #f1f5f9; border-radius: 8px; padding: 6px 12px;"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 12, 4)

        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet(
            "color: #64748b; font-size: 12px;"
        )
        layout.addWidget(self.lbl_status)
        layout.addStretch()

        user_role = getattr(self.session, "user_role", "") or "unknown"
        username = getattr(self.session, "username", "admin")
        self.lbl_user = QLabel(
            f"👤 {username}  •  Role: {user_role}"
        )
        self.lbl_user.setStyleSheet(
            "color: #64748b; font-size: 12px; font-weight: 600;"
        )
        layout.addWidget(self.lbl_user)
        return bar

    # ── TOOLBAR ──────────────────────────────────────────────
    def _toolbar(self, table: QTableWidget, kind: Optional[str] = None,
                 official: bool = False) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(6)

        search = QLineEdit()
        search.setPlaceholderText("🔍  Search rows…")
        search.setMaximumWidth(260)
        search.textChanged.connect(
            lambda t: self._filter_table(table, t)
        )
        l.addWidget(search)

        if not official:
            status_filter = QComboBox()
            status_filter.addItem("All Status", None)
            status_filter.addItems([
                "Draft", "Approved", "Rejected", "Submitted",
            ])
            status_filter.setMaximumWidth(140)
            status_filter.currentIndexChanged.connect(
                lambda: self._filter_by_status(
                    table, status_filter.currentData()
                )
            )
            l.addWidget(status_filter)

        l.addStretch()

        btn_refresh = QPushButton("↻ Refresh")
        btn_refresh.setObjectName("secondaryBtn")
        btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_refresh.clicked.connect(self.refresh_all)
        l.addWidget(btn_refresh)

        if kind and not official:
            btn_new = QPushButton("➕ New Draft")
            btn_new.setObjectName("successBtn")
            btn_new.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_new.clicked.connect(lambda: self.new_draft(kind))
            l.addWidget(btn_new)

            btn_approve = QPushButton("✓ Approve")
            btn_approve.setObjectName("primaryBtn")
            btn_approve.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_approve.clicked.connect(
                lambda: self.approve_selected(kind)
            )
            l.addWidget(btn_approve)

            btn_reject = QPushButton("✗ Reject")
            btn_reject.setObjectName("warningBtn")
            btn_reject.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_reject.clicked.connect(
                lambda: self.reject_selected(kind)
            )
            l.addWidget(btn_reject)

            btn_delete = QPushButton("🗑 Delete")
            btn_delete.setObjectName("dangerBtn")
            btn_delete.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_delete.clicked.connect(lambda: self.delete_draft(kind))
            l.addWidget(btn_delete)

        btn_export = QPushButton("⇩ CSV")
        btn_export.setObjectName("secondaryBtn")
        btn_export.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_export.clicked.connect(lambda: self.export_table(table))
        l.addWidget(btn_export)

        if kind:
            btn_html = QPushButton("📄 HTML")
            btn_html.setObjectName("secondaryBtn")
            btn_html.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_html.clicked.connect(
                lambda: self.export_selected_html(
                    kind, table, official=official
                )
            )
            l.addWidget(btn_html)

            btn_print = QPushButton("🖨 Print")
            btn_print.setObjectName("secondaryBtn")
            btn_print.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_print.clicked.connect(
                lambda: self.print_selected_html(
                    kind, table, official=official
                )
            )
            l.addWidget(btn_print)

        return w

    # ── REPORT PAGE ──────────────────────────────────────────
    def _report_page(self, table: QTableWidget, kind: str,
                     is_official: bool = False) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setSpacing(8)

        info_text = (
            "Field teams create drafts here. QC promotes them to Official."
            if not is_official
            else "Official register — approved, traceable project records only."
        )
        info = QLabel(info_text)
        info.setStyleSheet(
            "color: #64748b; font-size: 12px; "
            "background: #f8fafc; padding: 8px 12px; "
            "border-radius: 6px; border-left: 3px solid #3b82f6;"
        )
        l.addWidget(info)

        l.addWidget(self._toolbar(table, kind, official=is_official))

        table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        table.customContextMenuRequested.connect(
            lambda pos: self._show_report_context_menu(
                pos, table, kind, is_official
            )
        )
        table.doubleClicked.connect(
            lambda: self._show_row_details(table)
        )

        l.addWidget(table)
        return w

    # ── ACTIONS PAGE ─────────────────────────────────────────
    def _actions_page(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setSpacing(8)

        info = QLabel(
            "Track project actions, milestones, punches, and history."
        )
        info.setStyleSheet(
            "color: #64748b; font-size: 12px; "
            "background: #f8fafc; padding: 8px 12px; "
            "border-radius: 6px; border-left: 3px solid #8b5cf6;"
        )
        l.addWidget(info)

        bar = QHBoxLayout()
        bar.setSpacing(6)

        bar.addWidget(QLabel("Project:"))
        self.action_project = QComboBox()
        self.action_project.setMinimumWidth(220)
        bar.addWidget(self.action_project)

        self.action_search = QLineEdit()
        self.action_search.setPlaceholderText("🔍 Search actions…")
        self.action_search.setMaximumWidth(240)
        self.action_search.textChanged.connect(
            lambda t: self._filter_table(self.actions, t)
        )
        bar.addWidget(self.action_search)

        bar.addStretch()

        btn_add = QPushButton("➕ Add Action")
        btn_add.setObjectName("successBtn")
        btn_add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_add.clicked.connect(self.add_action)
        bar.addWidget(btn_add)

        btn_refresh = QPushButton("↻ Refresh")
        btn_refresh.setObjectName("secondaryBtn")
        btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_refresh.clicked.connect(self.refresh_actions)
        bar.addWidget(btn_refresh)

        btn_export = QPushButton("⇩ CSV")
        btn_export.setObjectName("secondaryBtn")
        btn_export.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_export.clicked.connect(
            lambda: self.export_table(self.actions)
        )
        bar.addWidget(btn_export)

        l.addLayout(bar)
        l.addWidget(self.actions)
        return w

    # ── USERS PAGE ───────────────────────────────────────────
    def _users_page(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setSpacing(8)

        info = QLabel(
            "Employee register — accounts, roles, and access control."
        )
        info.setStyleSheet(
            "color: #64748b; font-size: 12px; "
            "background: #f8fafc; padding: 8px 12px; "
            "border-radius: 6px; border-left: 3px solid #10b981;"
        )
        l.addWidget(info)

        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.user_search = QLineEdit()
        self.user_search.setPlaceholderText("🔍 Search employees…")
        self.user_search.setMaximumWidth(240)
        self.user_search.textChanged.connect(
            lambda t: self._filter_table(self.users, t)
        )
        bar.addWidget(self.user_search)

        bar.addStretch()

        btn_add = QPushButton("➕ New Employee")
        btn_add.setObjectName("successBtn")
        btn_add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_add.clicked.connect(self.add_employee)
        bar.addWidget(btn_add)

        btn_toggle = QPushButton("🔄 Toggle Active")
        btn_toggle.setObjectName("warningBtn")
        btn_toggle.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_toggle.clicked.connect(self.toggle_employee)
        bar.addWidget(btn_toggle)

        btn_refresh = QPushButton("↻ Refresh")
        btn_refresh.setObjectName("secondaryBtn")
        btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_refresh.clicked.connect(self.refresh_users)
        bar.addWidget(btn_refresh)

        l.addLayout(bar)
        l.addWidget(self.users)
        return w

    # ═══════════════════════════════════════
    #  FILTERS
    # ═══════════════════════════════════════
    def _filter_table(self, table: QTableWidget, text: str):
        text = text.strip().lower()
        for row in range(table.rowCount()):
            show = True
            if text:
                row_text = " ".join(
                    table.item(row, c).text().lower()
                    for c in range(table.columnCount())
                    if table.item(row, c)
                )
                show = text in row_text
            table.setRowHidden(row, not show)

    def _filter_by_status(self, table: QTableWidget,
                          status: Optional[str]):
        status_col = -1
        for c in range(table.columnCount()):
            header = table.horizontalHeaderItem(c)
            if header and header.text().lower() == "status":
                status_col = c
                break

        if status_col < 0:
            return

        for row in range(table.rowCount()):
            show = True
            if status:
                item = table.item(row, status_col)
                if item:
                    cell_text = item.text().split(" ", 1)[-1].strip()
                    show = cell_text == status
            table.setRowHidden(row, not show)

    # ═══════════════════════════════════════
    #  DATA LOADING
    # ═══════════════════════════════════════
    def _projects_welds(self):
        with self.db.session_scope() as s:
            projects = s.query(Project).order_by(Project.project_code).all()
            welds = s.query(Weld).order_by(Weld.weld_id).all()
            return projects, welds

    def refresh_all(self):
        self._set_status("Refreshing data…")
        QApplication.processEvents()
        self.refresh_drafts()
        self.refresh_official()
        self.refresh_actions()
        self.refresh_users()
        self._update_stats()
        self._set_status("Ready")

    def refresh_drafts(self):
        try:
            with self.db.session_scope() as s:
                wr = (
                    s.query(WeldReportDraft)
                    .order_by(WeldReportDraft.id.desc())
                    .all()
                )
                fr = (
                    s.query(FitupReportDraft)
                    .order_by(FitupReportDraft.id.desc())
                    .all()
                )

            _set_table_enhanced(
                self.weld_drafts,
                ["ID", "Report No", "Project", "Line", "Weld", "Welder",
                 "Date", "VT", "RT", "PT", "UT", "Status", "Prepared By"],
                [
                    (x.id, x.report_no, x.project_id, x.line_number,
                     x.weld_no, x.welder_name, x.weld_date,
                     x.visual_result, x.rt_result, x.pt_result,
                     x.ut_result, x.status, x.prepared_by)
                    for x in wr
                ],
                color_columns={
                    7: "result", 8: "result", 9: "result",
                    10: "result", 11: "status",
                },
            )
            _set_table_enhanced(
                self.fit_drafts,
                ["ID", "Report No", "Project", "Line", "Weld", "Fitter",
                 "Date", "Root Gap", "Hi-Low", "Alignment", "Result",
                 "Status", "Prepared By"],
                [
                    (x.id, x.report_no, x.project_id, x.line_number,
                     x.weld_no, x.fitter, x.fitup_date, x.root_gap,
                     x.hi_low, x.alignment, x.fitup_result, x.status,
                     x.prepared_by)
                    for x in fr
                ],
                color_columns={10: "result", 11: "status"},
            )
        except Exception as e:
            logger.exception("Refresh drafts failed")
            QMessageBox.warning(self, "Error", str(e))

    def refresh_official(self):
        try:
            with self.db.session_scope() as s:
                wr = (
                    s.query(WeldReport)
                    .order_by(WeldReport.id.desc())
                    .all()
                )
                fr = (
                    s.query(FitupReport)
                    .order_by(FitupReport.id.desc())
                    .all()
                )

            _set_table_enhanced(
                self.weld_official,
                ["ID", "Report No", "Project", "Line", "Weld", "Welder",
                 "Date", "VT", "RT", "PT", "UT", "Approved By",
                 "Approved At"],
                [
                    (x.id, x.report_no, x.project_id, x.line_number,
                     x.weld_no, x.welder_name, x.weld_date,
                     x.visual_result, x.rt_result, x.pt_result,
                     x.ut_result, x.approved_by, x.approved_at)
                    for x in wr
                ],
                color_columns={
                    7: "result", 8: "result", 9: "result", 10: "result",
                },
            )
            _set_table_enhanced(
                self.fit_official,
                ["ID", "Report No", "Project", "Line", "Weld", "Fitter",
                 "Date", "Root Gap", "Hi-Low", "Alignment", "Result",
                 "Approved By", "Approved At"],
                [
                    (x.id, x.report_no, x.project_id, x.line_number,
                     x.weld_no, x.fitter, x.fitup_date, x.root_gap,
                     x.hi_low, x.alignment, x.fitup_result,
                     x.approved_by, x.approved_at)
                    for x in fr
                ],
                color_columns={10: "result"},
            )
        except Exception as e:
            logger.exception("Refresh official failed")
            QMessageBox.warning(self, "Error", str(e))

    def _update_stats(self):
        try:
            with self.db.session_scope() as s:
                total_drafts = (
                    s.query(WeldReportDraft).count()
                    + s.query(FitupReportDraft).count()
                )
                total_official = (
                    s.query(WeldReport).count()
                    + s.query(FitupReport).count()
                )
                pending = (
                    s.query(WeldReportDraft)
                    .filter(WeldReportDraft.status == "Draft").count()
                    + s.query(FitupReportDraft)
                    .filter(FitupReportDraft.status == "Draft").count()
                )
                rejected = (
                    s.query(WeldReportDraft)
                    .filter(WeldReportDraft.status == "Rejected").count()
                    + s.query(FitupReportDraft)
                    .filter(FitupReportDraft.status == "Rejected").count()
                )
                total_actions = s.query(ProjectAction).count()
                active_users = (
                    s.query(User).filter(User.is_active == True).count()
                )

            self.stat_drafts.set_value(total_drafts)
            self.stat_official.set_value(total_official)
            self.stat_pending.set_value(pending)
            self.stat_rejected.set_value(rejected)
            self.stat_actions.set_value(total_actions)
            self.stat_users.set_value(active_users)
        except Exception as e:
            logger.warning(f"Stats update failed: {e}")

    # ═══════════════════════════════════════
    #  NEW DRAFT
    # ═══════════════════════════════════════
    def new_draft(self, kind):
        projects, welds = self._projects_welds()
        if not projects:
            QMessageBox.warning(self, "Project", "Create a project first.")
            return

        dlg = FieldReportDialog(
            self, kind, projects, welds,
            getattr(self.session, "username", "admin"),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        d = dlg.data()
        user = getattr(self.session, "username", "admin")

        try:
            with self.db.session_scope() as s:
                if d["weld_pk"]:
                    # ✅ FIXED: SQLAlchemy 2.0 — s.get(Model, pk)
                    linked = s.get(Weld, int(d["weld_pk"]))
                    if not linked:
                        raise ValueError(
                            "Selected weld/joint no longer exists."
                        )
                    if linked.project_id != d["project_id"]:
                        raise ValueError(
                            "Selected weld belongs to a different project."
                        )

                if kind == "weld":
                    obj = WeldReportDraft(
                        project_id=d["project_id"],
                        weld_pk=d["weld_pk"],
                        report_no=d["report_no"],
                        line_number=d["line_number"],
                        iso_number=d["iso_number"],
                        weld_no=d["weld_no"],
                        spool_no=d["spool_no"],
                        welder_name=d["person"],
                        weld_date=d["work_date"],
                        joint_type=d["joint_type"],
                        process=d["process"],
                        wps_id=d["wps_id"],
                        filler_material=d["filler"],
                        preheat=d["preheat"],
                        visual_result=d["result"],
                        rt_no=d["rt_no"], rt_result=d["rt_result"],
                        pt_no=d["pt_no"], pt_result=d["pt_result"],
                        ut_no=d["ut_no"], ut_result=d["ut_result"],
                        contractor=d["contractor"],
                        remarks=d["remarks"],
                        prepared_by=user,
                    )
                else:
                    obj = FitupReportDraft(
                        project_id=d["project_id"],
                        weld_pk=d["weld_pk"],
                        report_no=d["report_no"],
                        line_number=d["line_number"],
                        iso_number=d["iso_number"],
                        weld_no=d["weld_no"],
                        spool_no=d["spool_no"],
                        fitup_no=d["fitup_no"],
                        fitup_date=d["work_date"],
                        fitter=d["fitter"],
                        contractor=d["contractor"],
                        root_gap=d["root_gap"],
                        hi_low=d["hi_low"],
                        alignment=d["alignment"],
                        bevel=d["bevel"],
                        cleanliness=d["cleanliness"],
                        tack_quality=d["tack_quality"],
                        fitup_result=d["result"],
                        remarks=d["remarks"],
                        prepared_by=user,
                    )
                s.add(obj)
                s.flush()

                s.add(ProjectAction(
                    project_id=d["project_id"],
                    action_type="CREATE_DRAFT",
                    entity_type=(
                        "WeldReportDraft" if kind == "weld"
                        else "FitupReportDraft"
                    ),
                    entity_id=obj.id,
                    line_number=d["line_number"],
                    description=f"Draft {d['report_no']} created",
                    user_name=user,
                ))
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))
            return

        self.refresh_all()
        self._set_status(f"Draft {d['report_no']} created")

    # ═══════════════════════════════════════
    #  SELECTION HELPERS
    # ═══════════════════════════════════════
    def _selected_ids(self, table: QTableWidget) -> list[int]:
        rows = table.selectionModel().selectedRows()
        ids = []
        for r in rows:
            item = table.item(r.row(), 0)
            if item:
                try:
                    ids.append(int(item.text()))
                except ValueError:
                    pass
        return ids

    def _selected_id(self, table: QTableWidget) -> Optional[str]:
        ids = self._selected_ids(table)
        return str(ids[0]) if ids else None

    # ═══════════════════════════════════════
    #  BUSINESS RULES
    # ═══════════════════════════════════════
    def _validate_business_rules(self, d, kind):
        issues = []
        if not d.weld_pk:
            issues.append(
                "Report is not linked to a weld/joint record. "
                "Link it when traceability is required."
            )
        if kind == "fitup":
            fields = {
                "Root Gap": d.root_gap, "Hi-Low": d.hi_low,
                "Alignment": d.alignment, "Bevel": d.bevel,
                "Cleanliness": d.cleanliness,
                "Tack Quality": d.tack_quality,
            }
            missing = [k for k, v in fields.items() if not (v or "").strip()]
            if missing and d.fitup_result == "Accepted":
                issues.append(
                    "An Accepted fit-up must include all measurements: "
                    + ", ".join(missing)
                )
        else:
            if d.visual_result == "Accepted":
                declared = [
                    (d.rt_no, d.rt_result),
                    (d.pt_no, d.pt_result),
                    (d.ut_no, d.ut_result),
                ]
                incomplete = [
                    m for no, m in declared
                    if no and m in ("", "Pending")
                ]
                if incomplete:
                    issues.append(
                        "Every declared NDT method must have a final result."
                    )
            if d.visual_result == "Rejected" and d.status == "Approved":
                issues.append(
                    "A rejected visual cannot be promoted as accepted."
                )
        return issues

    def _can_approve(self):
        role = getattr(self.session, "user_role", "") or ""
        if not role and hasattr(self.session, "user"):
            role = getattr(self.session.user, "role", "") or ""
        return role.lower() in {"admin", "inspector", "engineer"}

    # ═══════════════════════════════════════
    #  APPROVAL
    # ═══════════════════════════════════════
    def approve_selected(self, kind):
        table = self.weld_drafts if kind == "weld" else self.fit_drafts
        ids = self._selected_ids(table)

        if not ids:
            QMessageBox.information(
                self, "Select", "Select one or more drafts first."
            )
            return

        if not self._can_approve():
            QMessageBox.warning(
                self, "Approval Restricted",
                "Only Engineer, Inspector, or Administrator can approve."
            )
            return

        reply = QMessageBox.question(
            self, "Confirm Approval",
            f"Approve {len(ids)} draft(s) and promote to Official?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        user = getattr(self.session, "username", "admin")
        approved = 0
        failed = 0
        errors = []

        for draft_id in ids:
            try:
                self._approve_single(draft_id, kind, user)
                approved += 1
            except Exception as e:
                failed += 1
                errors.append(f"ID {draft_id}: {e}")

        self.refresh_all()

        msg = f"Approved: {approved}\nFailed: {failed}"
        if errors:
            msg += "\n\nErrors:\n" + "\n".join(errors[:5])
        QMessageBox.information(self, "Bulk Approval", msg)
        self._set_status(f"Approved {approved} report(s)")

    def _approve_single(self, draft_id: int, kind: str, user: str):
        """Approve a single draft and promote to official."""
        with self.db.session_scope() as s:
            if kind == "weld":
                # ✅ FIXED: SQLAlchemy 2.0 — s.get(Model, pk)
                d = s.get(WeldReportDraft, draft_id)
                if not d:
                    raise ValueError("Draft not found")
                if d.status == "Approved":
                    raise ValueError("Already approved")

                issues = self._validate_business_rules(d, "weld")
                if issues:
                    raise ValueError(" | ".join(issues))

                d.status = "Approved"
                d.approved_by = user
                # ✅ FIXED: use _utcnow()
                d.approved_at = _utcnow()

                official = WeldReport(
                    draft_id=d.id, report_no=d.report_no,
                    project_id=d.project_id, weld_pk=d.weld_pk,
                    line_number=d.line_number, iso_number=d.iso_number,
                    weld_no=d.weld_no, spool_no=d.spool_no,
                    welder_id=d.welder_id, welder_name=d.welder_name,
                    weld_date=d.weld_date, joint_type=d.joint_type,
                    process=d.process, wps_id=d.wps_id,
                    filler_material=d.filler_material, preheat=d.preheat,
                    visual_result=d.visual_result, rt_no=d.rt_no,
                    rt_result=d.rt_result, pt_no=d.pt_no,
                    pt_result=d.pt_result, ut_no=d.ut_no,
                    ut_result=d.ut_result, pwht=d.pwht,
                    contractor=d.contractor, remarks=d.remarks,
                    approved_by=user, approved_at=_utcnow(),
                )
                s.add(official)
                entity = "WeldReport"
            else:
                # ✅ FIXED: SQLAlchemy 2.0
                d = s.get(FitupReportDraft, draft_id)
                if not d:
                    raise ValueError("Draft not found")
                if d.status == "Approved":
                    raise ValueError("Already approved")

                issues = self._validate_business_rules(d, "fitup")
                if issues:
                    raise ValueError(" | ".join(issues))

                d.status = "Approved"
                d.approved_by = user
                d.approved_at = _utcnow()

                official = FitupReport(
                    draft_id=d.id, report_no=d.report_no,
                    project_id=d.project_id, weld_pk=d.weld_pk,
                    line_number=d.line_number, iso_number=d.iso_number,
                    weld_no=d.weld_no, spool_no=d.spool_no,
                    fitup_no=d.fitup_no, fitup_date=d.fitup_date,
                    fitter=d.fitter, contractor=d.contractor,
                    root_gap=d.root_gap, hi_low=d.hi_low,
                    alignment=d.alignment, bevel=d.bevel,
                    cleanliness=d.cleanliness, tack_quality=d.tack_quality,
                    fitup_result=d.fitup_result, remarks=d.remarks,
                    approved_by=user, approved_at=_utcnow(),
                )
                s.add(official)
                entity = "FitupReport"

            s.add(ProjectAction(
                project_id=d.project_id,
                action_type="APPROVE_REPORT",
                entity_type=entity,
                entity_id=d.id,
                line_number=d.line_number,
                description=f"{d.report_no} promoted to Official",
                user_name=user, status="Closed",
            ))

    # ═══════════════════════════════════════
    #  REJECT
    # ═══════════════════════════════════════
    def reject_selected(self, kind):
        table = self.weld_drafts if kind == "weld" else self.fit_drafts
        ids = self._selected_ids(table)

        if not ids:
            QMessageBox.information(
                self, "Select", "Select one or more drafts first."
            )
            return

        if not self._can_approve():
            QMessageBox.warning(
                self, "Access Denied",
                "Only Engineer, Inspector, or Administrator can reject."
            )
            return

        dlg = RejectReasonDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        reason = dlg.get_reason()
        user = getattr(self.session, "username", "admin")
        rejected_count = 0

        try:
            with self.db.session_scope() as s:
                for draft_id in ids:
                    # ✅ FIXED: SQLAlchemy 2.0
                    if kind == "weld":
                        d = s.get(WeldReportDraft, draft_id)
                    else:
                        d = s.get(FitupReportDraft, draft_id)

                    if not d or d.status == "Approved":
                        continue

                    d.status = "Rejected"
                    if hasattr(d, "remarks"):
                        old_remarks = d.remarks or ""
                        d.remarks = (
                            f"{old_remarks}\n\n"
                            f"[REJECTED by {user}]: {reason}"
                        ).strip()

                    s.add(ProjectAction(
                        project_id=d.project_id,
                        action_type="REJECT_REPORT",
                        entity_type=(
                            "WeldReportDraft" if kind == "weld"
                            else "FitupReportDraft"
                        ),
                        entity_id=d.id,
                        line_number=d.line_number,
                        description=(
                            f"Draft {d.report_no} rejected. "
                            f"Reason: {reason[:100]}"
                        ),
                        user_name=user,
                        status="Closed",
                    ))
                    rejected_count += 1

            self.refresh_all()
            QMessageBox.information(
                self, "Rejected",
                f"Rejected {rejected_count} draft(s)."
            )
            self._set_status(f"Rejected {rejected_count} draft(s)")
        except Exception as e:
            logger.exception("Reject failed")
            QMessageBox.critical(self, "Error", str(e))

    # ═══════════════════════════════════════
    #  DELETE DRAFT
    # ═══════════════════════════════════════
    def delete_draft(self, kind):
        table = self.weld_drafts if kind == "weld" else self.fit_drafts
        ids = self._selected_ids(table)

        if not ids:
            QMessageBox.information(
                self, "Select", "Select drafts to delete."
            )
            return

        if not self._can_approve():
            QMessageBox.warning(
                self, "Access Denied",
                "Only Engineer, Inspector, or Administrator can delete."
            )
            return

        reply = QMessageBox.warning(
            self, "⚠️ Confirm Delete",
            f"Permanently delete {len(ids)} draft(s)?\n\n"
            f"This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            deleted = 0
            with self.db.session_scope() as s:
                for draft_id in ids:
                    # ✅ FIXED: SQLAlchemy 2.0
                    if kind == "weld":
                        d = s.get(WeldReportDraft, draft_id)
                    else:
                        d = s.get(FitupReportDraft, draft_id)

                    if d and d.status != "Approved":
                        s.delete(d)
                        deleted += 1

            self.refresh_all()
            QMessageBox.information(
                self, "Deleted", f"Deleted {deleted} draft(s)."
            )
            self._set_status(f"Deleted {deleted} draft(s)")
        except Exception as e:
            logger.exception("Delete failed")
            QMessageBox.critical(self, "Error", str(e))

    # ═══════════════════════════════════════
    #  HTML / PRINT
    # ═══════════════════════════════════════
    def _report_html(self, kind, table, official):
        sid = self._selected_id(table)
        if not sid:
            QMessageBox.information(
                self, "Select", "Select a report first."
            )
            return None
        try:
            path = self.reporting.export_report_html(
                kind, int(sid), official=official
            )
            return path
        except Exception as e:
            logger.exception("HTML report failed")
            QMessageBox.critical(self, "HTML Report Error", str(e))
            return None

    def export_selected_html(self, kind, table, official=False):
        path = self._report_html(kind, table, official)
        if path:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(Path(path).resolve()))
            )
            self._set_status(f"HTML report opened: {Path(path).name}")

    def print_selected_html(self, kind, table, official=False):
        path = self._report_html(kind, table, official)
        if not path:
            return
        try:
            doc = QTextDocument()
            doc.setHtml(Path(path).read_text(encoding="utf-8"))
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            preview = QPrintPreviewDialog(printer, self)
            preview.setWindowTitle("PipeAgent — Print Report")
            preview.resize(1100, 800)
            preview.paintRequested.connect(doc.print)
            preview.exec()
        except Exception as e:
            QMessageBox.warning(
                self, "Print",
                f"Print preview failed. HTML available at:\n{path}\n\n{e}"
            )

    # ═══════════════════════════════════════
    #  ACTIONS
    # ═══════════════════════════════════════
    def refresh_actions(self):
        try:
            with self.db.session_scope() as s:
                projects = (
                    s.query(Project)
                    .order_by(Project.project_code)
                    .all()
                )
                acts = (
                    s.query(ProjectAction)
                    .order_by(ProjectAction.id.desc())
                    .limit(2000)
                    .all()
                )

            current = self.action_project.currentData()
            self.action_project.blockSignals(True)
            self.action_project.clear()
            self.action_project.addItem("All Projects", None)
            for p in projects:
                self.action_project.addItem(
                    f"{p.project_code} – {p.title}", p.id
                )
            if current is not None:
                i = self.action_project.findData(current)
                if i >= 0:
                    self.action_project.setCurrentIndex(i)
            self.action_project.blockSignals(False)

            pid = self.action_project.currentData()
            if pid is not None:
                acts = [a for a in acts if a.project_id == pid]

            _set_table_enhanced(
                self.actions,
                ["ID", "Project", "Action", "Entity", "Line",
                 "Description", "Date", "User", "Status"],
                [
                    (a.id, a.project_id, a.action_type, a.entity_type,
                     a.line_number, a.description, a.action_date,
                     a.user_name, a.status)
                    for a in acts
                ],
                color_columns={8: "status"},
            )
        except Exception:
            logger.exception("Refresh actions failed")

    def add_action(self):
        pid = self.action_project.currentData()
        if not pid:
            QMessageBox.warning(
                self, "Project", "Select a specific project first."
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("➕ New Project Action")
        dlg.setMinimumWidth(500)
        dlg.setStyleSheet(MAIN_STYLESHEET)

        f = QFormLayout(dlg)
        typ = QComboBox()
        typ.addItems([
            "LINE_CHECK", "FITUP", "WELD", "NDT",
            "PRESSURE_TEST", "PUNCH", "DOCUMENT",
            "HANDOVER", "OTHER",
        ])
        line = QLineEdit()
        desc = QTextEdit()
        desc.setMaximumHeight(100)
        contractor = QLineEdit()

        f.addRow("Action Type", typ)
        f.addRow("Line No", line)
        f.addRow("Contractor", contractor)
        f.addRow("Description", desc)

        b = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        b.accepted.connect(dlg.accept)
        b.rejected.connect(dlg.reject)
        f.addRow(b)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        user = getattr(self.session, "username", "admin")
        try:
            with self.db.session_scope() as s:
                s.add(ProjectAction(
                    project_id=pid,
                    action_type=typ.currentText(),
                    line_number=line.text().strip(),
                    contractor=contractor.text().strip(),
                    description=desc.toPlainText().strip(),
                    user_name=user,
                ))
            self.refresh_actions()
            self._set_status("Action added")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ═══════════════════════════════════════
    #  USERS
    # ═══════════════════════════════════════
    def refresh_users(self):
        try:
            with self.db.session_scope() as s:
                us = (
                    s.query(User)
                    .order_by(User.full_name, User.username)
                    .all()
                )
            _set_table_enhanced(
                self.users,
                ["ID", "Employee ID", "Full Name", "Username", "Role",
                 "Department", "Company", "Phone", "Active"],
                [
                    (u.id, u.employee_id, u.full_name, u.username,
                     u.role, u.department, u.company, u.phone,
                     "Yes" if u.is_active else "No")
                    for u in us
                ],
                color_columns={4: "role"},
            )
        except Exception:
            logger.exception("Refresh users failed")

    def add_employee(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("➕ New Employee / User")
        dlg.setMinimumWidth(500)
        dlg.setStyleSheet(MAIN_STYLESHEET)

        f = QFormLayout(dlg)
        eid = QLineEdit()
        name = QLineEdit()
        username = QLineEdit()
        password = QLineEdit()
        password.setEchoMode(QLineEdit.EchoMode.Password)
        dept = QLineEdit()
        company = QLineEdit()
        phone = QLineEdit()
        role = QComboBox()
        role.addItems([
            "admin", "engineer", "inspector", "welder", "viewer",
        ])

        for lab, w in [
            ("Employee ID", eid), ("Full Name", name),
            ("Username *", username), ("Password *", password),
            ("Role", role), ("Department", dept),
            ("Company", company), ("Phone", phone),
        ]:
            f.addRow(lab, w)

        b = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        b.accepted.connect(dlg.accept)
        b.rejected.connect(dlg.reject)
        f.addRow(b)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        if not username.text().strip() or not password.text():
            QMessageBox.warning(
                self, "Validation", "Username/Password required."
            )
            return

        try:
            with self.db.session_scope() as s:
                from security.hashing import hash_password
                if s.query(User).filter_by(
                    username=username.text().strip()
                ).first():
                    raise ValueError("Username already exists")
                s.add(User(
                    employee_id=eid.text().strip() or None,
                    full_name=name.text().strip(),
                    username=username.text().strip(),
                    password_hash=hash_password(password.text()),
                    role=role.currentText(),
                    department=dept.text().strip(),
                    company=company.text().strip(),
                    phone=phone.text().strip(),
                    is_active=True,
                ))
            self.refresh_users()
            self._set_status(f"Employee {username.text()} added")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def toggle_employee(self):
        sid = self._selected_id(self.users)
        if not sid:
            QMessageBox.information(
                self, "Select", "Select an employee first."
            )
            return

        try:
            with self.db.session_scope() as s:
                # ✅ FIXED: SQLAlchemy 2.0 — s.get(Model, pk)
                u = s.get(User, int(sid))
                if u and u.username == "admin":
                    QMessageBox.warning(
                        self, "Restricted",
                        "The admin user cannot be deactivated."
                    )
                    return
                if u:
                    u.is_active = not bool(u.is_active)
            self.refresh_users()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ═══════════════════════════════════════
    #  EXPORT CSV
    # ═══════════════════════════════════════
    def export_table(self, table: QTableWidget):
        if table.rowCount() == 0:
            QMessageBox.warning(self, "No Data", "Nothing to export.")
            return

        default_name = (
            f"report_"
            f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV",
            str(Path(EXPORT_DIR) / default_name),
            "CSV (*.csv)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow([
                    table.horizontalHeaderItem(i).text()
                    for i in range(table.columnCount())
                ])
                for r in range(table.rowCount()):
                    if not table.isRowHidden(r):
                        w.writerow([
                            table.item(r, c).text()
                            if table.item(r, c) else ""
                            for c in range(table.columnCount())
                        ])
            QMessageBox.information(
                self, "Export",
                f"Exported successfully:\n{path}"
            )
            self._set_status(f"Exported to {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    # ═══════════════════════════════════════
    #  CONTEXT MENUS
    # ═══════════════════════════════════════
    def _show_report_context_menu(self, pos, table: QTableWidget,
                                  kind: str, is_official: bool):
        if table.rowCount() == 0:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: white; border: 1px solid #e2e8f0;
                border-radius: 8px; padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px; font-size: 13px; border-radius: 4px;
            }
            QMenu::item:selected {
                background: #eff6ff; color: #1e293b;
            }
            QMenu::separator {
                height: 1px; background: #e2e8f0; margin: 4px 8px;
            }
        """)

        act_view = menu.addAction("📋 View Details")
        act_view.triggered.connect(
            lambda: self._show_row_details(table)
        )

        menu.addSeparator()

        if not is_official:
            act_approve = menu.addAction("✓ Approve")
            act_approve.triggered.connect(
                lambda: self.approve_selected(kind)
            )
            act_reject = menu.addAction("✗ Reject")
            act_reject.triggered.connect(
                lambda: self.reject_selected(kind)
            )
            menu.addSeparator()
            act_delete = menu.addAction("🗑 Delete")
            act_delete.triggered.connect(
                lambda: self.delete_draft(kind)
            )
            menu.addSeparator()

        act_html = menu.addAction("📄 Export HTML")
        act_html.triggered.connect(
            lambda: self.export_selected_html(
                kind, table, official=is_official
            )
        )

        act_print = menu.addAction("🖨 Print")
        act_print.triggered.connect(
            lambda: self.print_selected_html(
                kind, table, official=is_official
            )
        )

        menu.addSeparator()

        act_copy = menu.addAction("📋 Copy Row")
        act_copy.triggered.connect(lambda: self._copy_row(table))

        menu.exec(table.viewport().mapToGlobal(pos))

    def _show_row_details(self, table: QTableWidget):
        row = table.currentRow()
        if row < 0:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("📋 Row Details")
        dlg.setMinimumSize(500, 400)
        dlg.setStyleSheet(MAIN_STYLESHEET)

        layout = QVBoxLayout(dlg)
        title = QLabel("📋 Row Details")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 800; color: #1e3c72;"
        )
        layout.addWidget(title)

        form = QFormLayout()
        for c in range(table.columnCount()):
            header = table.horizontalHeaderItem(c)
            item = table.item(row, c)
            if header and item:
                lbl = QLabel(f"{header.text()}:")
                lbl.setStyleSheet(
                    "font-weight: 700; color: #374151;"
                )
                val = QLabel(item.text())
                val.setStyleSheet("color: #1e293b;")
                val.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                val.setWordWrap(True)
                form.addRow(lbl, val)
        layout.addLayout(form)

        btn = QPushButton("Close")
        btn.setObjectName("secondaryBtn")
        btn.clicked.connect(dlg.close)
        layout.addWidget(btn)

        dlg.exec()

    def _copy_row(self, table: QTableWidget):
        row = table.currentRow()
        if row < 0:
            return
        texts = []
        for c in range(table.columnCount()):
            item = table.item(row, c)
            if item:
                texts.append(item.text())
        QApplication.clipboard().setText(" | ".join(texts))
        self._set_status("Row copied to clipboard")

    # ═══════════════════════════════════════
    #  MISC
    # ═══════════════════════════════════════
    def _set_status(self, msg: str):
        self.lbl_status.setText(msg)