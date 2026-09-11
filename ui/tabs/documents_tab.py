# -*- coding: utf-8 -*-
# ui/tabs/documents_tab.py – PipeAgent
# Document Control for piping drawings and quality documents.
from __future__ import annotations

import csv
import logging
import os
import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, QTimer, QThread, pyqtSignal, QDate
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QDialog, QFormLayout,
    QLineEdit, QComboBox, QDialogButtonBox, QFileDialog,
    QTextEdit, QFrame, QProgressBar, QMenu, QGroupBox,
    QAbstractItemView, QApplication, QTabWidget,
    QDateEdit, QCheckBox, QSplitter, QScrollArea,
)
from PyQt6.QtGui import (
    QDesktopServices, QColor, QFont, QBrush, QPen,
    QPainter, QAction, QCursor,
)

from db.manager import DatabaseManager
from db.models import Project, Document
from security.session import SessionManager
from services.document_workflow import DocumentWorkflowService
from services.record_fields import apply_fields
from config import DOCUMENT_TYPES, DOCUMENT_STATUSES

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  STATUS COLORS / CONSTANTS
# ─────────────────────────────────────────────
STATUS_COLORS: dict[str, dict[str, str]] = {
    "Draft":        {"bg": "#f0f4ff", "fg": "#3b5bdb", "border": "#5c7cfa"},
    "Submitted":    {"bg": "#fff4e6", "fg": "#e67700", "border": "#ffa94d"},
    "Under Review": {"bg": "#f3f0ff", "fg": "#7048e8", "border": "#9775fa"},
    "Approved":     {"bg": "#e6fcf5", "fg": "#087f5b", "border": "#38d9a9"},
    "Rejected":     {"bg": "#fff5f5", "fg": "#c92a2a", "border": "#ff6b6b"},
    "Issued":       {"bg": "#e7f5ff", "fg": "#1864ab", "border": "#4dabf7"},
    "Superseded":   {"bg": "#f8f9fa", "fg": "#868e96", "border": "#adb5bd"},
    "Cancelled":    {"bg": "#f8f9fa", "fg": "#495057", "border": "#868e96"},
    "On Hold":      {"bg": "#fff9db", "fg": "#e67700", "border": "#fcc419"},
    "IFR":          {"bg": "#e6fcf5", "fg": "#087f5b", "border": "#38d9a9"},
    "IFC":          {"bg": "#e7f5ff", "fg": "#1864ab", "border": "#4dabf7"},
    "IFA":          {"bg": "#f3f0ff", "fg": "#7048e8", "border": "#9775fa"},
    "AFC":          {"bg": "#e6fcf5", "fg": "#087f5b", "border": "#38d9a9"},
}

DEFAULT_STATUS_COLOR = {"bg": "#f8f9fa", "fg": "#495057", "border": "#ced4da"}

TABLE_COLUMNS = [
    "ID", "Doc Number", "Type", "Title", "Revision", "Status",
    "Line No.", "Area", "Class", "Receive Transmittal", "Send Transmittal",
    "Originator", "File", "Created", "Created By",
]

COLUMN_WIDTHS = [50, 150, 100, 180, 60, 100, 110, 90, 70, 130, 130, 110, 140, 120, 90]

DCC_FIELDS = (
    "description", "description_fa", "receive_transmittal_number",
    "receive_letter_number", "received_from", "received_date",
    "sent_to", "send_transmittal_number", "sent_date", "send_letter_number",
    "department", "area_name", "doc_class", "doc_index", "service",
    "sheet_number", "size_nps", "markup", "remarks",
)
MAX_DISPLAY_ROWS = 2000


MAIN_STYLESHEET = """
    QWidget#documentsTab {
        background: qlineargradient(x1:0, y1:0, x2:0.5, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #1e3a5f, stop:1 #1e3c72);
        border-radius: 16px; padding: 20px;
    }
    QLabel#mainTitle {
        color: white; font-size: 24px; font-weight: 800;
        font-family: 'Segoe UI', 'Vazirmatn', sans-serif;
    }
    QLabel#mainSubtitle { color: #94a3b8; font-size: 13px; }
    QFrame#filterCard, QFrame#statsCard, QFrame#actionsCard {
        background: white; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 16px;
    }
    QFrame#filterCard:hover, QFrame#statsCard:hover { border-color: #3b82f6; }
    QLabel#sectionTitle { color: #1e293b; font-size: 14px; font-weight: 700; }
    QLabel#statValue { font-size: 26px; font-weight: 800; }
    QLabel#statLabel { font-size: 11px; color: #64748b; font-weight: 500; }
    QLineEdit, QDateEdit {
        padding: 9px 12px; border: 2px solid #e2e8f0;
        border-radius: 8px; font-size: 13px;
        background: white; color: #1e293b;
    }
    QLineEdit:focus, QDateEdit:focus {
        border-color: #3b82f6; background: #f8faff;
    }
    QLineEdit:hover, QDateEdit:hover { border-color: #94a3b8; }
    QComboBox {
        padding: 9px 12px; border: 2px solid #e2e8f0;
        border-radius: 8px; font-size: 13px;
        background: white; color: #1e293b; min-width: 140px;
    }
    QComboBox:focus, QComboBox:hover { border-color: #3b82f6; }
    QComboBox::drop-down { border: none; width: 28px; }
    QComboBox::down-arrow {
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid #64748b; margin-right: 8px;
    }
    QComboBox QAbstractItemView {
        border: 2px solid #e2e8f0; border-radius: 8px;
        background: white;
        selection-background-color: #eff6ff; padding: 4px;
    }
    QPushButton#primaryBtn {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #3b82f6, stop:1 #2563eb);
        color: white; border: none; padding: 10px 22px;
        border-radius: 8px; font-size: 13px; font-weight: 700;
    }
    QPushButton#primaryBtn:hover {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #2563eb, stop:1 #1d4ed8);
    }
    QPushButton#successBtn {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #10b981, stop:1 #059669);
        color: white; border: none; padding: 10px 22px;
        border-radius: 8px; font-size: 13px; font-weight: 700;
    }
    QPushButton#successBtn:hover {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #059669, stop:1 #047857);
    }
    QPushButton#dangerBtn {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #ef4444, stop:1 #dc2626);
        color: white; border: none; padding: 10px 22px;
        border-radius: 8px; font-size: 13px; font-weight: 700;
    }
    QPushButton#dangerBtn:hover {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #dc2626, stop:1 #b91c1c);
    }
    QPushButton#warningBtn {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #f59e0b, stop:1 #d97706);
        color: white; border: none; padding: 10px 22px;
        border-radius: 8px; font-size: 13px; font-weight: 700;
    }
    QPushButton#warningBtn:hover {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #d97706, stop:1 #b45309);
    }
    QPushButton#secondaryBtn {
        background: white; color: #374151;
        border: 2px solid #d1d5db;
        padding: 9px 18px; border-radius: 8px;
        font-size: 13px; font-weight: 600;
    }
    QPushButton#secondaryBtn:hover {
        background: #f9fafb; border-color: #3b82f6; color: #3b82f6;
    }
    QTableWidget {
        background: white; border: 1px solid #e2e8f0;
        border-radius: 12px; gridline-color: #f1f5f9;
        font-size: 12px;
        selection-background-color: #dbeafe;
        selection-color: #1e293b;
        alternate-background-color: #f8fafc;
    }
    QTableWidget::item { padding: 7px 10px; border-bottom: 1px solid #f1f5f9; }
    QTableWidget::item:selected { background: #dbeafe; }
    QTableWidget::item:hover { background: #f0f7ff; }
    QHeaderView::section {
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 #f8fafc, stop:1 #eef2f7);
        color: #475569; font-weight: 700; font-size: 12px;
        padding: 10px 10px; border: none;
        border-bottom: 2px solid #e2e8f0;
        border-right: 1px solid #e2e8f0;
    }
    QHeaderView::section:hover { background: #e2e8f0; color: #1e293b; }
    QProgressBar {
        border: none; border-radius: 6px;
        background: #e2e8f0; height: 14px;
        text-align: center; font-size: 10px;
        font-weight: 700; color: white;
    }
    QProgressBar::chunk {
        border-radius: 6px;
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #3b82f6, stop:1 #10b981);
    }
    QScrollBar:vertical { background: #f1f5f9; width: 10px; border-radius: 5px; }
    QScrollBar::handle:vertical {
        background: #94a3b8; border-radius: 5px; min-height: 30px;
    }
    QScrollBar::handle:vertical:hover { background: #64748b; }
    QScrollBar:horizontal { background: #f1f5f9; height: 10px; border-radius: 5px; }
    QScrollBar::handle:horizontal {
        background: #94a3b8; border-radius: 5px; min-width: 30px;
    }
"""


# ─────────────────────────────────────────────
#  STAT CARD
# ─────────────────────────────────────────────
class StatCard(QFrame):
    def __init__(self, icon: str, label: str, value: str = "0",
                 color: str = "#3b82f6"):
        super().__init__()
        self.setObjectName("statsCard")
        self.setFixedHeight(90)
        self.setMinimumWidth(130)

        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(14, 10, 14, 10)

        top = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"font-size: 22px; color: {color};")
        top.addWidget(icon_lbl)
        top.addStretch()

        self.value_lbl = QLabel(str(value))
        self.value_lbl.setStyleSheet(
            f"font-size: 26px; font-weight: 800; color: {color};"
        )
        top.addWidget(self.value_lbl)
        layout.addLayout(top)

        text_lbl = QLabel(label)
        text_lbl.setObjectName("statLabel")
        text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text_lbl)

    def set_value(self, v):
        self.value_lbl.setText(str(v))


# ─────────────────────────────────────────────
#  BATCH UPLOAD THREAD
# ─────────────────────────────────────────────
class BatchUploadThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(int, int)
    error = pyqtSignal(str)

    def __init__(self, service, project_id, files: list[dict], username: str):
        super().__init__()
        self.service = service
        self.project_id = project_id
        self.files = files
        self.username = username

    def run(self):
        success = 0
        fail = 0
        total = len(self.files)

        for i, f in enumerate(self.files):
            pct = int((i + 1) / total * 100)
            self.progress.emit(
                pct,
                f"Registering {i + 1}/{total}: {f.get('doc_number', '?')}"
            )
            try:
                doc = self.service.register_document(
                    project_id=self.project_id,
                    doc_number=f["doc_number"],
                    doc_type=f.get(
                        "doc_type",
                        DOCUMENT_TYPES[0] if DOCUMENT_TYPES else "Drawing"
                    ),
                    title=f.get("title", ""),
                    revision=f.get("revision", "0"),
                    status=f.get(
                        "status",
                        DOCUMENT_STATUSES[0] if DOCUMENT_STATUSES else "Draft"
                    ),
                    line_number=f.get("line_number", ""),
                    originator=f.get("originator", ""),
                    source_file=f.get("source_file"),
                    created_by=self.username,
                )
                if doc:
                    success += 1
                else:
                    fail += 1
            except Exception:
                logger.exception("Batch register failed for %s", f)
                fail += 1

        self.finished.emit(success, fail)


# ─────────────────────────────────────────────
#  DOCUMENT DIALOG (Create / Edit)
# ─────────────────────────────────────────────
class DocumentDialog(QDialog):
    def __init__(self, parent=None, projects: list = None,
                 edit_data: dict | None = None):
        super().__init__(parent)
        self._source_file = ""
        self._is_edit = edit_data is not None

        self.setWindowTitle(
            "✏️ Edit Document" if self._is_edit
            else "📄 Register Document / Drawing"
        )
        self.setMinimumWidth(620)
        self.setMinimumHeight(640)

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QFormLayout(inner)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        self.project_combo = QComboBox()
        if projects:
            for p in projects:
                self.project_combo.addItem(
                    f"{p.project_code} – {p.title}", p.id
                )

        self.doc_number = QLineEdit()
        self.doc_number.setPlaceholderText("e.g. DWG-PIP-001")

        self.doc_type = QComboBox()
        self.doc_type.addItems(DOCUMENT_TYPES)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Document title")

        self.revision = QLineEdit("0")

        self.status = QComboBox()
        self.status.addItems(DOCUMENT_STATUSES)

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText('e.g. 6"-P-001-A1A')

        self.originator = QLineEdit()
        self.originator.setPlaceholderText("Company or person")

        self.description = QTextEdit()
        self.description.setMaximumHeight(60)
        self.description_fa = QLineEdit()
        self.recv_trans = QLineEdit()
        self.recv_letter = QLineEdit()
        self.recv_from = QLineEdit()
        self.recv_date = QDateEdit()
        self.recv_date.setCalendarPopup(True)
        self.recv_date.setDisplayFormat("yyyy-MM-dd")
        self.recv_date.setSpecialValueText("—")
        self.recv_date.setDate(QDate(2000, 1, 1))
        self.sent_to = QLineEdit()
        self.send_trans = QLineEdit()
        self.send_letter = QLineEdit()
        self.sent_date = QDateEdit()
        self.sent_date.setCalendarPopup(True)
        self.sent_date.setDisplayFormat("yyyy-MM-dd")
        self.sent_date.setSpecialValueText("—")
        self.sent_date.setDate(QDate(2000, 1, 1))
        self.department = QLineEdit()
        self.area_name = QLineEdit()
        self.doc_class = QLineEdit()
        self.doc_index = QLineEdit()
        self.service = QLineEdit()
        self.sheet_number = QLineEdit()
        self.size_nps = QLineEdit()
        self.markup = QLineEdit()

        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(80)
        self.notes_edit.setPlaceholderText("Optional notes…")

        self.file_lbl = QLabel("(no file selected)")
        self.file_lbl.setStyleSheet("color: #64748b; font-size: 12px;")
        btn_file = QPushButton("📎 Attach File…")
        btn_file.setObjectName("secondaryBtn")
        btn_file.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_file.clicked.connect(self._pick_file)
        file_row = QHBoxLayout()
        file_row.addWidget(self.file_lbl, 1)
        file_row.addWidget(btn_file)

        layout.addRow("Project *", self.project_combo)
        layout.addRow("Doc Number *", self.doc_number)
        layout.addRow("Doc Type *", self.doc_type)
        layout.addRow("Title", self.title_edit)
        layout.addRow("Revision", self.revision)
        layout.addRow("Status", self.status)
        layout.addRow("Line Number", self.line_edit)
        layout.addRow("Originator", self.originator)
        layout.addRow("Description", self.description)
        layout.addRow("Description (FA)", self.description_fa)
        layout.addRow("Department", self.department)
        layout.addRow("Area", self.area_name)
        layout.addRow("Class", self.doc_class)
        layout.addRow("Index", self.doc_index)
        layout.addRow("Service", self.service)
        layout.addRow("Sheet", self.sheet_number)
        layout.addRow("Size", self.size_nps)
        layout.addRow("Markup", self.markup)
        layout.addRow("Receive Transmittal", self.recv_trans)
        layout.addRow("Receive Letter No", self.recv_letter)
        layout.addRow("Received From", self.recv_from)
        layout.addRow("Receive Date", self.recv_date)
        layout.addRow("Send To", self.sent_to)
        layout.addRow("Send Transmittal", self.send_trans)
        layout.addRow("Send Letter No", self.send_letter)
        layout.addRow("Send Date", self.sent_date)
        layout.addRow("Notes", self.notes_edit)
        layout.addRow("File", file_row)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        if edit_data:
            self._fill_edit_data(edit_data)

    def _fill_edit_data(self, data: dict):
        pid = data.get("project_id")
        if pid is not None:
            for i in range(self.project_combo.count()):
                if self.project_combo.itemData(i) == pid:
                    self.project_combo.setCurrentIndex(i)
                    break

        self.doc_number.setText(data.get("doc_number", ""))
        self.doc_number.setReadOnly(True)

        doc_type = data.get("doc_type", "")
        idx = self.doc_type.findText(doc_type)
        if idx >= 0:
            self.doc_type.setCurrentIndex(idx)

        self.title_edit.setText(data.get("title", ""))
        self.revision.setText(data.get("revision", "0"))

        status = data.get("status", "")
        idx = self.status.findText(status)
        if idx >= 0:
            self.status.setCurrentIndex(idx)

        self.line_edit.setText(data.get("line_number", ""))
        self.originator.setText(data.get("originator", ""))
        self.notes_edit.setPlainText(
            data.get("remarks", "") or data.get("notes", "") or ""
        )
        self.description.setPlainText(data.get("description", ""))
        self.description_fa.setText(data.get("description_fa", ""))
        self.department.setText(data.get("department", ""))
        self.area_name.setText(data.get("area_name", ""))
        self.doc_class.setText(data.get("doc_class", ""))
        self.doc_index.setText(data.get("doc_index", ""))
        self.service.setText(data.get("service", ""))
        self.sheet_number.setText(data.get("sheet_number", ""))
        self.size_nps.setText(data.get("size_nps", ""))
        self.markup.setText(data.get("markup", ""))
        self.recv_trans.setText(data.get("receive_transmittal_number", ""))
        self.recv_letter.setText(data.get("receive_letter_number", ""))
        self.recv_from.setText(data.get("received_from", ""))
        self.send_trans.setText(data.get("send_transmittal_number", ""))
        self.send_letter.setText(data.get("send_letter_number", ""))
        self.sent_to.setText(data.get("sent_to", ""))
        for edit, key in (
            (self.recv_date, "received_date"),
            (self.sent_date, "sent_date"),
        ):
            raw = data.get(key)
            if raw:
                parsed = QDate.fromString(str(raw)[:10], "yyyy-MM-dd")
                if parsed.isValid():
                    edit.setDate(parsed)

        fp = data.get("file_path", "")
        if fp:
            self._source_file = fp
            self.file_lbl.setText(Path(fp).name)
            self.file_lbl.setStyleSheet(
                "color: #059669; font-weight: 600;"
            )

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select document file", "",
            "Documents (*.pdf *.dwg *.dxf *.docx *.xlsx *.pptx "
            "*.png *.jpg *.jpeg *.tif *.tiff *.rvt *.ifc);;"
            "All Files (*.*)",
        )
        if path:
            self._source_file = path
            self.file_lbl.setText(Path(path).name)
            self.file_lbl.setStyleSheet(
                "color: #059669; font-weight: 600;"
            )

    def _validate_and_accept(self):
        if not self.project_combo.currentData():
            QMessageBox.warning(
                self, "Validation", "Please select a project."
            )
            return
        if not self.doc_number.text().strip():
            QMessageBox.warning(
                self, "Validation", "Document number is required."
            )
            self.doc_number.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "project_id": self.project_combo.currentData(),
            "doc_number": self.doc_number.text().strip(),
            "doc_type": self.doc_type.currentText(),
            "title": self.title_edit.text().strip(),
            "revision": self.revision.text().strip() or "0",
            "status": self.status.currentText(),
            "line_number": self.line_edit.text().strip(),
            "originator": self.originator.text().strip(),
            "notes": self.notes_edit.toPlainText().strip(),
            "remarks": self.notes_edit.toPlainText().strip(),
            "source_file": self._source_file or None,
            "description": self.description.toPlainText().strip() or self.notes_edit.toPlainText().strip(),
            "description_fa": self.description_fa.text().strip(),
            "receive_transmittal_number": self.recv_trans.text().strip(),
            "receive_letter_number": self.recv_letter.text().strip(),
            "received_from": self.recv_from.text().strip(),
            "received_date": None if self.recv_date.date() == QDate(2000, 1, 1) else self.recv_date.date().toPyDate(),
            "sent_to": self.sent_to.text().strip(),
            "send_transmittal_number": self.send_trans.text().strip(),
            "send_letter_number": self.send_letter.text().strip(),
            "sent_date": None if self.sent_date.date() == QDate(2000, 1, 1) else self.sent_date.date().toPyDate(),
            "department": self.department.text().strip(),
            "area_name": self.area_name.text().strip(),
            "doc_class": self.doc_class.text().strip(),
            "doc_index": self.doc_index.text().strip(),
            "service": self.service.text().strip(),
            "sheet_number": self.sheet_number.text().strip(),
            "size_nps": self.size_nps.text().strip(),
            "markup": self.markup.text().strip(),
        }


# ─────────────────────────────────────────────
#  DOCUMENT DETAIL DIALOG
# ─────────────────────────────────────────────
class DocumentDetailDialog(QDialog):
    def __init__(self, doc_data: dict, parent=None):
        super().__init__(parent)
        self.doc_data = doc_data
        self.setWindowTitle(
            f"📋 {doc_data.get('doc_number', 'Document Details')}"
        )
        self.setMinimumSize(680, 520)
        self.setStyleSheet(MAIN_STYLESHEET)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel(f"📋 {self.doc_data.get('doc_number', 'N/A')}")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #1e3c72;"
        )
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e2e8f0; border-radius: 8px;
                background: white; padding: 12px;
            }
            QTabBar::tab {
                padding: 10px 20px; font-weight: 600; font-size: 12px;
                border: none; border-bottom: 3px solid transparent;
                color: #64748b;
            }
            QTabBar::tab:selected {
                color: #3b82f6; border-bottom-color: #3b82f6;
            }
            QTabBar::tab:hover { color: #1e293b; }
        """)

        tabs.addTab(self._tab_general(), "📄 General")
        tabs.addTab(self._tab_file(), "📎 File Info")
        tabs.addTab(self._tab_history(), "🕐 History")
        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_open = QPushButton("📂 Open File")
        btn_open.setObjectName("primaryBtn")
        btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_open.clicked.connect(self._open_file)
        btn_row.addWidget(btn_open)

        btn_close = QPushButton("Close")
        btn_close.setObjectName("secondaryBtn")
        btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _tab_general(self) -> QWidget:
        w = QWidget()
        g = QGridLayout(w)
        g.setSpacing(10)

        fields = [
            ("Doc Number:", self.doc_data.get("doc_number", "")),
            ("Type:", self.doc_data.get("doc_type", "")),
            ("Title:", self.doc_data.get("title", "")),
            ("Revision:", self.doc_data.get("revision", "")),
            ("Status:", self.doc_data.get("status", "")),
            ("Line No.:", self.doc_data.get("line_number", "")),
            ("Originator:", self.doc_data.get("originator", "")),
            ("Created:", self.doc_data.get("created_at", "")),
            ("Created By:", self.doc_data.get("created_by", "")),
        ]

        for row, (lbl, val) in enumerate(fields):
            l = QLabel(lbl)
            l.setStyleSheet("font-weight: 700; color: #374151;")
            v = QLabel(str(val or "—"))
            v.setStyleSheet("color: #1e293b;")
            v.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            g.addWidget(l, row, 0)
            g.addWidget(v, row, 1)

        g.setRowStretch(len(fields), 1)
        return w

    def _tab_file(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        fp = self.doc_data.get("file_path", "")
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setStyleSheet(
            "font-family: 'Consolas', monospace; font-size: 12px;"
        )

        if fp and Path(fp).exists():
            p = Path(fp)
            size_kb = p.stat().st_size / 1024
            info_text.setHtml(
                f"<b>File:</b> {p.name}<br>"
                f"<b>Path:</b> {p}<br>"
                f"<b>Size:</b> {size_kb:.1f} KB<br>"
                f"<b>Extension:</b> {p.suffix}<br>"
                f"<b>Modified:</b> "
                f"{datetime.datetime.fromtimestamp(p.stat().st_mtime)}"
            )
        elif fp:
            info_text.setPlainText(
                f"File path stored: {fp}\n(File not found on disk)"
            )
        else:
            info_text.setPlainText("No file attached.")

        layout.addWidget(info_text)
        return w

    def _tab_history(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        tbl = QTableWidget(0, 4)
        tbl.setHorizontalHeaderLabels([
            "Date", "Action", "User", "Details"
        ])
        tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        tbl.setAlternatingRowColors(True)

        tbl.insertRow(0)
        tbl.setItem(
            0, 0,
            QTableWidgetItem(str(self.doc_data.get("created_at", "")))
        )
        tbl.setItem(0, 1, QTableWidgetItem("Registered"))
        tbl.setItem(
            0, 2,
            QTableWidgetItem(str(self.doc_data.get("created_by", "")))
        )
        tbl.setItem(
            0, 3,
            QTableWidgetItem(
                f"Rev {self.doc_data.get('revision', '0')} — "
                f"{self.doc_data.get('status', '')}"
            )
        )
        layout.addWidget(tbl)
        return w

    def _open_file(self):
        fp = self.doc_data.get("file_path", "")
        if fp and Path(fp).is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(fp))
        else:
            QMessageBox.information(
                self, "Info", "No file available to open."
            )


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class DocumentsTab(QWidget):
    """Document Control tab — register, track, and manage documents."""

    def __init__(self, db: DatabaseManager, session: SessionManager):
        super().__init__()
        self.setObjectName("documentsTab")
        self.db = db
        self.session = session
        self.service = DocumentWorkflowService(db)
        self.current_project_id: int | None = None
        self._cached_docs: list[dict] = []
        self._batch_thread: BatchUploadThread | None = None

        self._build_ui()
        self.setStyleSheet(MAIN_STYLESHEET)
        self._load_projects()

    # ── UI BUILD ─────────────────────────────────────────────
    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(14)
        main.setContentsMargins(18, 18, 18, 18)

        main.addWidget(self._build_header())
        main.addLayout(self._build_stat_cards())
        main.addWidget(self._build_filter_section())
        main.addWidget(self._build_progress_section())
        main.addWidget(self._build_table(), stretch=1)
        main.addWidget(self._build_action_bar())
        main.addWidget(self._build_status_bar())

    def _build_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("headerCard")
        layout = QVBoxLayout(card)
        layout.setSpacing(4)

        t = QLabel("📁 Document Control  |  Drawings & Quality Documents")
        t.setObjectName("mainTitle")
        layout.addWidget(t)

        s = QLabel(
            "Register, track, review and manage piping drawings "
            "and quality documents across projects."
        )
        s.setObjectName("mainSubtitle")
        layout.addWidget(s)
        return card

    def _build_stat_cards(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(10)

        self.stat_total = StatCard("📁", "Total Docs", "0", "#3b82f6")
        self.stat_approved = StatCard("✅", "Approved", "0", "#10b981")
        self.stat_review = StatCard("🔍", "Under Review", "0", "#8b5cf6")
        self.stat_rejected = StatCard("❌", "Rejected", "0", "#ef4444")
        self.stat_draft = StatCard("📝", "Draft", "0", "#6366f1")
        self.stat_with_file = StatCard("📎", "With File", "0", "#0ea5e9")

        for c in (
            self.stat_total, self.stat_approved, self.stat_review,
            self.stat_rejected, self.stat_draft, self.stat_with_file,
        ):
            layout.addWidget(c)
        return layout

    def _build_filter_section(self) -> QFrame:
        card = QFrame()
        card.setObjectName("filterCard")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        lbl = QLabel("🔧 Filters & Actions")
        lbl.setObjectName("sectionTitle")
        layout.addWidget(lbl)

        # Row 1
        r1 = QHBoxLayout()
        r1.setSpacing(10)

        r1.addWidget(QLabel("Project:"))
        self.cmb_project = QComboBox()
        self.cmb_project.setMinimumWidth(240)
        self.cmb_project.currentIndexChanged.connect(self._on_project_changed)
        r1.addWidget(self.cmb_project)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(
            "🔍  Search doc number, title, originator…"
        )
        self.txt_search.setMinimumWidth(260)
        self.txt_search.textChanged.connect(self._apply_filters)
        r1.addWidget(self.txt_search)
        r1.addStretch()

        self.btn_refresh = QPushButton("↻ Refresh")
        self.btn_refresh.setObjectName("secondaryBtn")
        self.btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_refresh.clicked.connect(self.refresh)
        r1.addWidget(self.btn_refresh)
        layout.addLayout(r1)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #e2e8f0; max-height: 1px;")
        layout.addWidget(sep)

        # Row 2
        r2 = QHBoxLayout()
        r2.setSpacing(10)

        r2.addWidget(QLabel("Type:"))
        self.cmb_type = QComboBox()
        self.cmb_type.addItem("All Types", None)
        for t in DOCUMENT_TYPES:
            self.cmb_type.addItem(t, t)
        self.cmb_type.currentIndexChanged.connect(self._apply_filters)
        r2.addWidget(self.cmb_type)

        r2.addWidget(QLabel("Status:"))
        self.cmb_status = QComboBox()
        self.cmb_status.addItem("All Statuses", None)
        for s in DOCUMENT_STATUSES:
            self.cmb_status.addItem(s, s)
        self.cmb_status.currentIndexChanged.connect(self._apply_filters)
        r2.addWidget(self.cmb_status)

        r2.addWidget(QLabel("Line:"))
        self.txt_line_filter = QLineEdit()
        self.txt_line_filter.setPlaceholderText("Line No.")
        self.txt_line_filter.setMaximumWidth(140)
        self.txt_line_filter.textChanged.connect(self._apply_filters)
        r2.addWidget(self.txt_line_filter)
        r2.addStretch()

        self.btn_add = QPushButton("📄 Register")
        self.btn_add.setObjectName("successBtn")
        self.btn_add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_add.clicked.connect(self._on_add)
        r2.addWidget(self.btn_add)

        self.btn_batch = QPushButton("📦 Batch Upload")
        self.btn_batch.setObjectName("primaryBtn")
        self.btn_batch.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_batch.clicked.connect(self._on_batch_upload)
        r2.addWidget(self.btn_batch)

        self.btn_export = QPushButton("📥 CSV")
        self.btn_export.setObjectName("secondaryBtn")
        self.btn_export.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_export.clicked.connect(self._export_csv)
        r2.addWidget(self.btn_export)

        self.btn_delete = QPushButton("🗑 Delete")
        self.btn_delete.setObjectName("dangerBtn")
        self.btn_delete.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_delete.clicked.connect(self._delete_selected)
        r2.addWidget(self.btn_delete)

        layout.addLayout(r2)
        return card

    def _build_progress_section(self) -> QWidget:
        self.progress_widget = QWidget()
        self.progress_widget.setVisible(False)

        layout = QVBoxLayout(self.progress_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.progress_label = QLabel("Processing…")
        self.progress_label.setStyleSheet(
            "font-size: 12px; color: #3b82f6; font-weight: 600;"
        )
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumHeight(14)
        layout.addWidget(self.progress_bar)
        return self.progress_widget

    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(TABLE_COLUMNS)

        self.table.setAlternatingRowColors(True)
        # ✅ FIXED: use QAbstractItemView enums (correct class)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

        for i, w in enumerate(COLUMN_WIDTHS):
            if i < len(TABLE_COLUMNS):
                self.table.setColumnWidth(i, w)

        self.table.setColumnHidden(0, True)

        self.table.doubleClicked.connect(self._on_double_click)
        self.table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.selectionModel().selectionChanged.connect(
            self._update_selection_count
        )
        return self.table

    def _build_action_bar(self) -> QFrame:
        card = QFrame()
        card.setObjectName("actionsCard")
        layout = QHBoxLayout(card)
        layout.setSpacing(10)

        layout.addWidget(QLabel("⚡ Set status of selected:"))

        self.cmb_action_status = QComboBox()
        self.cmb_action_status.addItems(DOCUMENT_STATUSES)
        layout.addWidget(self.cmb_action_status)

        btn_apply = QPushButton("Apply Status")
        btn_apply.setObjectName("warningBtn")
        btn_apply.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_apply.clicked.connect(self._on_change_status)
        layout.addWidget(btn_apply)
        layout.addStretch()

        btn_open = QPushButton("📂 Open File")
        btn_open.setObjectName("secondaryBtn")
        btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_open.clicked.connect(self._on_open_file)
        layout.addWidget(btn_open)

        btn_edit = QPushButton("✏️ Edit")
        btn_edit.setObjectName("secondaryBtn")
        btn_edit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_edit.clicked.connect(self._on_edit)
        layout.addWidget(btn_edit)
        return card

    def _build_status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setStyleSheet(
            "background: #f1f5f9; border-radius: 8px; padding: 6px 12px;"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(20)

        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(self.lbl_status)
        layout.addStretch()

        self.lbl_rows = QLabel("Rows: 0")
        self.lbl_rows.setStyleSheet(
            "color: #64748b; font-size: 12px; font-weight: 600;"
        )
        layout.addWidget(self.lbl_rows)

        self.lbl_selected = QLabel("Selected: 0")
        self.lbl_selected.setStyleSheet(
            "color: #64748b; font-size: 12px; font-weight: 600;"
        )
        layout.addWidget(self.lbl_selected)
        return bar

    # ── DATA LOADING ─────────────────────────────────────────
    def _load_projects(self):
        self.cmb_project.blockSignals(True)
        self.cmb_project.clear()
        try:
            with self.db.session_scope() as s:
                projects = s.query(Project).order_by(Project.project_code).all()
                for p in projects:
                    self.cmb_project.addItem(
                        f"{p.project_code} – {p.title}", p.id
                    )
            if self.cmb_project.count():
                self.cmb_project.blockSignals(False)
                self._on_project_changed()
            else:
                self.cmb_project.blockSignals(False)
        except Exception as e:
            self.cmb_project.blockSignals(False)
            logger.exception("Load projects failed")
            QMessageBox.warning(
                self, "Error", f"Failed to load projects:\n{e}"
            )

    def _on_project_changed(self):
        self.current_project_id = self.cmb_project.currentData()
        self.refresh()

    def refresh(self):
        self._set_status("Loading documents…")
        QApplication.processEvents()

        if not self.current_project_id:
            self._cached_docs = []
            self._populate_table([])
            self._update_stats()
            self._set_status("Select a project to view documents.")
            return

        try:
            doc_type = self.cmb_type.currentData()
            docs = self.service.list_by_project(
                self.current_project_id, doc_type=doc_type
            )

            self._cached_docs = []
            for d in docs:
                self._cached_docs.append({
                    "id": getattr(d, "id", None),
                    "doc_number": getattr(d, "doc_number", "") or "",
                    "doc_type": getattr(d, "doc_type", "") or "",
                    "title": getattr(d, "title", "") or "",
                    "revision": getattr(d, "revision", "") or "",
                    "status": getattr(d, "status", "") or "",
                    "line_number": getattr(d, "line_number", "") or "",
                    "originator": getattr(d, "originator", "") or "",
                    "file_path": getattr(d, "file_path", "") or "",
                    "created_at": str(getattr(d, "created_at", "") or ""),
                    "created_by": getattr(d, "created_by", "") or "",
                    "notes": getattr(d, "remarks", "") or getattr(d, "notes", "") or "",
                    "remarks": getattr(d, "remarks", "") or "",
                    "project_id": getattr(d, "project_id", None),
                    "description": getattr(d, "description", "") or "",
                    "description_fa": getattr(d, "description_fa", "") or "",
                    "receive_transmittal_number": getattr(d, "receive_transmittal_number", "") or "",
                    "receive_letter_number": getattr(d, "receive_letter_number", "") or "",
                    "received_from": getattr(d, "received_from", "") or "",
                    "received_date": getattr(d, "received_date", None),
                    "sent_to": getattr(d, "sent_to", "") or "",
                    "send_transmittal_number": getattr(d, "send_transmittal_number", "") or "",
                    "sent_date": getattr(d, "sent_date", None),
                    "send_letter_number": getattr(d, "send_letter_number", "") or "",
                    "department": getattr(d, "department", "") or "",
                    "area_name": getattr(d, "area_name", "") or "",
                    "doc_class": getattr(d, "doc_class", "") or "",
                    "doc_index": getattr(d, "doc_index", "") or "",
                    "service": getattr(d, "service", "") or "",
                    "sheet_number": getattr(d, "sheet_number", "") or "",
                    "size_nps": getattr(d, "size_nps", "") or "",
                    "markup": getattr(d, "markup", "") or "",
                })

            self._apply_filters()
            self._update_stats()
            self._set_status(
                f"Loaded {len(self._cached_docs)} document(s)"
            )
        except Exception as e:
            logger.exception("Documents refresh failed")
            QMessageBox.warning(self, "Error", str(e))
            self._set_status(f"Error: {e}")

    # ── FILTERS ──────────────────────────────────────────────
    def _apply_filters(self):
        search = self.txt_search.text().strip().lower()
        status_f = self.cmb_status.currentData()
        line_f = self.txt_line_filter.text().strip().lower()

        filtered = []
        for d in self._cached_docs:
            if status_f and d.get("status") != status_f:
                continue
            if line_f and line_f not in d.get("line_number", "").lower():
                continue
            if search:
                haystack = " ".join([
                    d.get("doc_number", ""),
                    d.get("title", ""),
                    d.get("originator", ""),
                    d.get("doc_type", ""),
                    d.get("line_number", ""),
                    d.get("notes", ""),
                ]).lower()
                if search not in haystack:
                    continue
            filtered.append(d)

        self._populate_table(filtered)

    def _populate_table(self, docs: list[dict]):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for d in docs:
            row = self.table.rowCount()
            self.table.insertRow(row)

            values = [
                str(d.get("id", "")),
                d.get("doc_number", ""),
                d.get("doc_type", ""),
                d.get("title", ""),
                d.get("revision", ""),
                d.get("status", ""),
                d.get("line_number", ""),
                d.get("area_name", ""),
                d.get("doc_class", ""),
                d.get("receive_transmittal_number", ""),
                d.get("send_transmittal_number", ""),
                d.get("originator", ""),
                Path(d["file_path"]).name if d.get("file_path") else "",
                d.get("created_at", ""),
                d.get("created_by", ""),
            ]

            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col == 5:
                    colors = STATUS_COLORS.get(
                        str(val), DEFAULT_STATUS_COLOR
                    )
                    item.setBackground(QColor(colors["bg"]))
                    item.setForeground(QColor(colors["fg"]))
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)

                if col == 0:
                    item.setData(
                        Qt.ItemDataRole.UserRole, d.get("doc_number")
                    )
                    item.setData(
                        Qt.ItemDataRole.UserRole + 1,
                        d.get("file_path", ""),
                    )
                    item.setData(Qt.ItemDataRole.UserRole + 2, d)

                self.table.setItem(row, col, item)

            self.table.setRowHeight(row, 38)

        self.table.setSortingEnabled(True)
        self.lbl_rows.setText(f"Rows: {self.table.rowCount()}")
        self._update_selection_count()

    def _update_stats(self):
        total = len(self._cached_docs)
        approved = sum(
            1 for d in self._cached_docs
            if d.get("status") in ("Approved", "IFC", "AFC")
        )
        review = sum(
            1 for d in self._cached_docs
            if d.get("status") in ("Under Review", "Submitted", "IFR")
        )
        rejected = sum(
            1 for d in self._cached_docs if d.get("status") == "Rejected"
        )
        draft = sum(
            1 for d in self._cached_docs if d.get("status") == "Draft"
        )
        with_file = sum(
            1 for d in self._cached_docs if d.get("file_path")
        )

        self.stat_total.set_value(total)
        self.stat_approved.set_value(approved)
        self.stat_review.set_value(review)
        self.stat_rejected.set_value(rejected)
        self.stat_draft.set_value(draft)
        self.stat_with_file.set_value(with_file)

    # ── CRUD ─────────────────────────────────────────────────
    def _get_project_objects(self) -> list:
        with self.db.session_scope() as s:
            projects = s.query(Project).order_by(Project.project_code).all()
            return [
                type("P", (), {
                    "id": p.id,
                    "project_code": p.project_code,
                    "title": p.title,
                })()
                for p in projects
            ]

    def _on_add(self):
        proj_list = self._get_project_objects()
        if not proj_list:
            QMessageBox.information(
                self, "Info", "Create a Project first."
            )
            return

        dlg = DocumentDialog(self, projects=proj_list)
        if self.current_project_id:
            for i in range(dlg.project_combo.count()):
                if dlg.project_combo.itemData(i) == self.current_project_id:
                    dlg.project_combo.setCurrentIndex(i)
                    break

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()
        if not data["doc_number"] or not data["project_id"]:
            QMessageBox.warning(
                self, "Validation",
                "Project and Doc Number are required."
            )
            return

        try:
            doc = self.service.register_document(
                project_id=data["project_id"],
                doc_number=data["doc_number"],
                doc_type=data["doc_type"],
                title=data["title"],
                revision=data["revision"],
                status=data["status"],
                line_number=data["line_number"],
                originator=data["originator"],
                source_file=data["source_file"],
                created_by=getattr(self.session, "username", "") or "",
            )
            if doc:
                with self.db.session_scope() as s:
                    rec = s.get(Document, doc.id)
                    if rec:
                        apply_fields(rec, data, DCC_FIELDS)
                for i in range(self.cmb_project.count()):
                    if self.cmb_project.itemData(i) == data["project_id"]:
                        self.cmb_project.setCurrentIndex(i)
                        break
                self.refresh()
                QMessageBox.information(
                    self, "✅ Success",
                    f"Document {data['doc_number']} registered."
                )
            else:
                QMessageBox.warning(
                    self, "⚠️ Warning",
                    "Could not register (duplicate number "
                    "or license limit)."
                )
        except Exception as e:
            logger.exception("Register document failed")
            QMessageBox.critical(
                self, "Error", f"Registration failed:\n{e}"
            )

    def _on_edit(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(
                self, "Info", "Select a document to edit."
            )
            return

        row = rows[0].row()
        id_item = self.table.item(row, 0)
        if not id_item:
            return

        doc_data = id_item.data(Qt.ItemDataRole.UserRole + 2)
        if not doc_data:
            return

        proj_list = self._get_project_objects()
        dlg = DocumentDialog(self, projects=proj_list, edit_data=doc_data)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_data()

        try:
            with self.db.session_scope() as s:
                # ✅ FIXED: SQLAlchemy 2.0 — use s.get(Model, pk)
                doc = s.get(Document, doc_data.get("id"))
                if not doc:
                    QMessageBox.warning(
                        self, "Error", "Document not found."
                    )
                    return

                doc.doc_type = data["doc_type"]
                doc.title = data["title"]
                doc.revision = data["revision"]
                doc.status = data["status"]
                doc.line_number = data["line_number"]
                doc.originator = data["originator"]

                if data.get("source_file"):
                    doc.file_path = data["source_file"]
                apply_fields(doc, data, DCC_FIELDS)

                s.commit()

            self.refresh()
            QMessageBox.information(
                self, "✅ Updated",
                f"Document {data['doc_number']} updated."
            )
        except Exception as e:
            logger.exception("Edit document failed")
            QMessageBox.critical(
                self, "Error", f"Update failed:\n{e}"
            )

    def _delete_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(
                self, "Info", "Select documents to delete."
            )
            return

        ids = []
        names = []
        for r in rows:
            item = self.table.item(r.row(), 0)
            if item:
                doc_data = item.data(Qt.ItemDataRole.UserRole + 2)
                if doc_data:
                    ids.append(doc_data.get("id"))
                    names.append(doc_data.get("doc_number", "?"))

        if not ids:
            return

        names_text = "\n".join(f"  • {n}" for n in names[:15])
        if len(names) > 15:
            names_text += f"\n  … and {len(names) - 15} more"

        reply = QMessageBox.warning(
            self, "⚠️ Confirm Delete",
            f"Delete {len(ids)} document(s)?\n\n"
            f"{names_text}\n\n"
            f"This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            deleted = 0
            with self.db.session_scope() as s:
                for doc_id in ids:
                    # ✅ FIXED: SQLAlchemy 2.0
                    doc = s.get(Document, doc_id)
                    if doc:
                        s.delete(doc)
                        deleted += 1
                s.commit()

            self.refresh()
            QMessageBox.information(
                self, "✅ Deleted",
                f"Deleted {deleted} document(s)."
            )
            self._set_status(f"Deleted {deleted} document(s)")
        except Exception as e:
            logger.exception("Delete documents failed")
            QMessageBox.critical(
                self, "Error", f"Delete failed:\n{e}"
            )

    def _on_change_status(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(
                self, "Info", "Select one or more documents."
            )
            return

        new_status = self.cmb_action_status.currentText()
        ok = 0
        for r in rows:
            item = self.table.item(r.row(), 0)
            if item:
                doc_no = item.data(Qt.ItemDataRole.UserRole)
                if doc_no:
                    success, _ = self.service.change_status(
                        doc_no, new_status
                    )
                    if success:
                        ok += 1

        self.refresh()
        QMessageBox.information(
            self, "✅ Done",
            f"Updated status for {ok} document(s) to '{new_status}'."
        )

    # ── BATCH UPLOAD ─────────────────────────────────────────
    def _on_batch_upload(self):
        if not self.current_project_id:
            QMessageBox.warning(
                self, "Warning", "Select a project first."
            )
            return

        files, _ = QFileDialog.getOpenFileNames(
            self, "Select files to register", "",
            "Documents (*.pdf *.dwg *.dxf *.docx *.xlsx *.png "
            "*.jpg *.tif);;All Files (*.*)",
        )
        if not files:
            return

        file_data = []
        for f in files:
            name = Path(f).stem
            file_data.append({
                "doc_number": name,
                "doc_type": DOCUMENT_TYPES[0] if DOCUMENT_TYPES else "Drawing",
                "title": name.replace("-", " ").replace("_", " ").title(),
                "revision": "0",
                "status": DOCUMENT_STATUSES[0] if DOCUMENT_STATUSES else "Draft",
                "line_number": "",
                "originator": "",
                "source_file": f,
            })

        reply = QMessageBox.question(
            self, "Batch Upload",
            f"Register {len(file_data)} file(s) as documents?\n\n"
            f"Document numbers will be derived from file names.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # ✅ FIXED: cleanup previous batch thread
        if self._batch_thread is not None:
            try:
                if self._batch_thread.isRunning():
                    self._batch_thread.wait(2000)
                self._batch_thread.deleteLater()
            except Exception:
                pass
            self._batch_thread = None

        self.btn_batch.setEnabled(False)
        self.btn_batch.setText("⏳ Uploading…")
        self.progress_widget.setVisible(True)
        self.progress_bar.setValue(0)

        username = getattr(self.session, "username", "") or "admin"
        self._batch_thread = BatchUploadThread(
            self.service, self.current_project_id, file_data, username
        )
        self._batch_thread.progress.connect(self._on_batch_progress)
        self._batch_thread.finished.connect(self._on_batch_finished)
        self._batch_thread.error.connect(self._on_batch_error)
        self._batch_thread.start()

    def _on_batch_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.progress_label.setText(msg)
        self._set_status(msg)

    def _on_batch_finished(self, success: int, fail: int):
        self.btn_batch.setEnabled(True)
        self.btn_batch.setText("📦 Batch Upload")
        QTimer.singleShot(
            2000, lambda: self.progress_widget.setVisible(False)
        )
        self.refresh()
        QMessageBox.information(
            self, "✅ Batch Complete",
            f"Successfully registered: {success}\n"
            f"Failed / Skipped: {fail}"
        )
        if self._batch_thread is not None:
            self._batch_thread.deleteLater()
            self._batch_thread = None

    def _on_batch_error(self, msg: str):
        self.btn_batch.setEnabled(True)
        self.btn_batch.setText("📦 Batch Upload")
        self.progress_widget.setVisible(False)
        QMessageBox.critical(self, "❌ Batch Error", msg)
        if self._batch_thread is not None:
            self._batch_thread.deleteLater()
            self._batch_thread = None

    # ── EXPORT CSV ───────────────────────────────────────────
    def _export_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "No Data", "Nothing to export.")
            return

        default_name = (
            f"documents_"
            f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", default_name,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                headers = [
                    TABLE_COLUMNS[i]
                    for i in range(len(TABLE_COLUMNS)) if i != 0
                ]
                writer.writerow(headers)

                for row in range(self.table.rowCount()):
                    row_data = []
                    for col in range(len(TABLE_COLUMNS)):
                        if col == 0:
                            continue
                        item = self.table.item(row, col)
                        row_data.append(item.text() if item else "")
                    writer.writerow(row_data)

            QMessageBox.information(
                self, "✅ Exported",
                f"Exported {self.table.rowCount()} rows to:\n{path}"
            )
            self._set_status(f"Exported {self.table.rowCount()} rows")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    # ── FILE ACTIONS ─────────────────────────────────────────
    def _on_open_file(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Info", "Select a document.")
            return

        item = self.table.item(rows[0].row(), 0)
        if not item:
            return
        fp = item.data(Qt.ItemDataRole.UserRole + 1)
        if not fp or not Path(fp).is_file():
            QMessageBox.information(
                self, "Info", "No file attached or file not found."
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(fp))

    def _on_double_click(self, index):
        row = index.row()
        item = self.table.item(row, 0)
        if not item:
            return
        doc_data = item.data(Qt.ItemDataRole.UserRole + 2)
        if doc_data:
            dlg = DocumentDetailDialog(doc_data, self)
            dlg.exec()

    # ── CONTEXT MENU ─────────────────────────────────────────
    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: white; border: 1px solid #e2e8f0;
                border-radius: 8px; padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px; font-size: 13px; border-radius: 4px;
            }
            QMenu::item:selected { background: #eff6ff; color: #1e293b; }
            QMenu::separator {
                height: 1px; background: #e2e8f0; margin: 4px 8px;
            }
        """)

        act_view = menu.addAction("📋 View Details")
        act_view.triggered.connect(
            lambda: self._on_double_click(self.table.currentIndex())
        )

        act_edit = menu.addAction("✏️ Edit Document")
        act_edit.triggered.connect(self._on_edit)

        menu.addSeparator()

        act_open = menu.addAction("📂 Open File")
        act_open.triggered.connect(self._on_open_file)

        act_folder = menu.addAction("📁 Open Containing Folder")
        act_folder.triggered.connect(self._open_folder)

        menu.addSeparator()

        act_copy_no = menu.addAction("📋 Copy Doc Number")
        act_copy_no.triggered.connect(self._copy_doc_number)

        act_copy_path = menu.addAction("📋 Copy File Path")
        act_copy_path.triggered.connect(self._copy_file_path)

        menu.addSeparator()

        act_delete = menu.addAction("🗑 Delete Selected")
        act_delete.triggered.connect(self._delete_selected)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _open_folder(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 0)
        if not item:
            return
        fp = item.data(Qt.ItemDataRole.UserRole + 1)
        if fp:
            folder = os.path.dirname(fp)
            if os.path.isdir(folder):
                if os.name == "nt":
                    os.startfile(folder)
                else:
                    os.system(f'xdg-open "{folder}"')
            else:
                QMessageBox.warning(
                    self, "Not Found",
                    f"Folder does not exist:\n{folder}"
                )

    def _copy_doc_number(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            item = self.table.item(rows[0].row(), 1)
            if item:
                QApplication.clipboard().setText(item.text())
                self._set_status(f"Copied: {item.text()}")

    def _copy_file_path(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            item = self.table.item(rows[0].row(), 0)
            if item:
                fp = item.data(Qt.ItemDataRole.UserRole + 1)
                if fp:
                    QApplication.clipboard().setText(fp)
                    self._set_status("Copied path")

    # ── MISC ─────────────────────────────────────────────────
    def _update_selection_count(self, *_args):
        count = len(self.table.selectionModel().selectedRows())
        self.lbl_selected.setText(f"Selected: {count}")

    def _set_status(self, msg: str):
        self.lbl_status.setText(msg)

    # ── CLEANUP ──────────────────────────────────────────────
    def closeEvent(self, event):
        """Ensure batch thread is stopped before widget closes."""
        if self._batch_thread is not None:
            try:
                if self._batch_thread.isRunning():
                    self._batch_thread.requestInterruption()
                    self._batch_thread.wait(2000)
                self._batch_thread.deleteLater()
            except Exception:
                pass
            self._batch_thread = None
        super().closeEvent(event)