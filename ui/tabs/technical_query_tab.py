# -*- coding: utf-8 -*-
"""Technical Query / RFI register — PipeAgent 5.2.7."""
from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from typing import Optional

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QBrush, QColor, QCursor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from db.manager import DatabaseManager
from db.models import Project, TechnicalQuery
from security.session import SessionManager

logger = logging.getLogger(__name__)

TQ_CATEGORIES = [
    "Engineering", "Construction", "Material", "Welding",
    "NDE", "Test Package", "Supports", "Document", "RFI", "Other",
]
TQ_PRIORITIES = ["Low", "Normal", "High", "Critical"]
TQ_STATUSES = ["Open", "Submitted", "Answered", "Closed", "Rejected"]

STATUS_BADGES = {
    "Open": {"bg": "#fef3c7", "fg": "#92400e"},
    "Submitted": {"bg": "#e0f2fe", "fg": "#075985"},
    "Answered": {"bg": "#ede9fe", "fg": "#5b21b6"},
    "Closed": {"bg": "#dcfce7", "fg": "#166534"},
    "Rejected": {"bg": "#fee2e2", "fg": "#991b1b"},
}

COLUMNS = [
    "ID", "TQ Number", "Date Raised", "Raised By", "Category",
    "Priority", "Related Document", "Due Date", "Assigned To",
    "Status", "Response Date",
]


def _qdate(value) -> QDate:
    if isinstance(value, date) and not isinstance(value, datetime):
        return QDate(value.year, value.month, value.day)
    if isinstance(value, datetime):
        return QDate(value.year, value.month, value.day)
    if isinstance(value, str) and value:
        parsed = QDate.fromString(value[:10], "yyyy-MM-dd")
        if parsed.isValid():
            return parsed
    return QDate()


def _date_or_none(edit: QDateEdit):
    if not edit.date().isValid() or edit.date() == QDate(2000, 1, 1) and not edit.text():
        return None
    py = edit.date().toPyDate()
    return py


class TechnicalQueryDialog(QDialog):
    def __init__(self, parent=None, projects=None, existing: Optional[dict] = None):
        super().__init__(parent)
        self.is_edit = existing is not None
        self.setWindowTitle("Edit Technical Query" if self.is_edit else "Raise Technical Query")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.project_combo = QComboBox()
        if projects:
            for p in projects:
                self.project_combo.addItem(f"{p.project_code} – {p.title}", p.id)

        self.tq_number = QLineEdit()
        self.tq_number.setPlaceholderText("e.g. TQ-PIP-001")
        self.raised_date = QDateEdit()
        self.raised_date.setCalendarPopup(True)
        self.raised_date.setDisplayFormat("yyyy-MM-dd")
        self.raised_date.setDate(QDate.currentDate())
        self.submitted_date = QDateEdit()
        self.submitted_date.setCalendarPopup(True)
        self.submitted_date.setDisplayFormat("yyyy-MM-dd")
        self.submitted_date.setSpecialValueText("—")
        self.submitted_date.setDate(QDate(2000, 1, 1))
        self.raised_by = QLineEdit()
        self.category = QComboBox()
        self.category.addItems(TQ_CATEGORIES)
        self.priority = QComboBox()
        self.priority.addItems(TQ_PRIORITIES)
        self.priority.setCurrentText("Normal")
        self.related = QLineEdit()
        self.related.setPlaceholderText("ISO / P&ID / specification")
        self.due_date = QDateEdit()
        self.due_date.setCalendarPopup(True)
        self.due_date.setDisplayFormat("yyyy-MM-dd")
        self.due_date.setDate(QDate.currentDate().addDays(7))
        self.assigned = QLineEdit()
        self.status = QComboBox()
        self.status.addItems(TQ_STATUSES)
        self.approved_by = QLineEdit()
        self.description = QTextEdit()
        self.description.setMaximumHeight(90)
        self.response = QTextEdit()
        self.response.setMaximumHeight(80)
        self.response_date = QDateEdit()
        self.response_date.setCalendarPopup(True)
        self.response_date.setDisplayFormat("yyyy-MM-dd")
        self.response_date.setSpecialValueText("—")
        self.response_date.setDate(QDate(2000, 1, 1))
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(60)

        form.addRow("Project *", self.project_combo)
        form.addRow("TQ Number *", self.tq_number)
        form.addRow("Date Raised", self.raised_date)
        form.addRow("Date Submitted", self.submitted_date)
        form.addRow("Raised By", self.raised_by)
        form.addRow("Category", self.category)
        form.addRow("Priority", self.priority)
        form.addRow("Related Document", self.related)
        form.addRow("Due Date", self.due_date)
        form.addRow("Assigned To", self.assigned)
        form.addRow("Status", self.status)
        form.addRow("Approval By", self.approved_by)
        form.addRow("Description of Query", self.description)
        form.addRow("Response / Resolution", self.response)
        form.addRow("Response Date", self.response_date)
        form.addRow("Notes", self.notes)
        layout.addLayout(form)

        if existing:
            pid = existing.get("project_id")
            for i in range(self.project_combo.count()):
                if self.project_combo.itemData(i) == pid:
                    self.project_combo.setCurrentIndex(i)
                    break
            self.tq_number.setText(existing.get("tq_number", ""))
            self.tq_number.setReadOnly(True)
            rd = _qdate(existing.get("raised_date"))
            if rd.isValid():
                self.raised_date.setDate(rd)
            sd = _qdate(existing.get("submitted_date"))
            if sd.isValid():
                self.submitted_date.setDate(sd)
            self.raised_by.setText(existing.get("raised_by", ""))
            self.category.setCurrentText(existing.get("category") or TQ_CATEGORIES[0])
            self.priority.setCurrentText(existing.get("priority") or "Normal")
            self.related.setText(existing.get("related_document", ""))
            dd = _qdate(existing.get("due_date"))
            if dd.isValid():
                self.due_date.setDate(dd)
            self.assigned.setText(existing.get("assigned_to", ""))
            self.status.setCurrentText(existing.get("status") or "Open")
            self.approved_by.setText(existing.get("approved_by", ""))
            self.description.setPlainText(existing.get("description", ""))
            self.response.setPlainText(existing.get("response", ""))
            rpd = _qdate(existing.get("response_received_date"))
            if rpd.isValid():
                self.response_date.setDate(rpd)
            self.notes.setPlainText(existing.get("notes", ""))

        buttons = QHBoxLayout()
        save = QPushButton("Save Query")
        save.setProperty("primary", True)
        save.clicked.connect(self._save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    def _optional_date(self, edit: QDateEdit):
        if edit.date() == QDate(2000, 1, 1):
            return None
        return edit.date().toPyDate()

    def _save(self):
        if not self.tq_number.text().strip():
            QMessageBox.warning(self, "Validation", "TQ Number is required.")
            return
        if not self.project_combo.currentData():
            QMessageBox.warning(self, "Validation", "Select a project.")
            return
        self.result_data = {
            "project_id": self.project_combo.currentData(),
            "tq_number": self.tq_number.text().strip().upper(),
            "raised_date": self.raised_date.date().toPyDate(),
            "submitted_date": self._optional_date(self.submitted_date),
            "raised_by": self.raised_by.text().strip(),
            "category": self.category.currentText(),
            "priority": self.priority.currentText(),
            "related_document": self.related.text().strip(),
            "due_date": self.due_date.date().toPyDate(),
            "assigned_to": self.assigned.text().strip(),
            "status": self.status.currentText(),
            "approved_by": self.approved_by.text().strip(),
            "description": self.description.toPlainText().strip(),
            "response": self.response.toPlainText().strip(),
            "response_received_date": self._optional_date(self.response_date),
            "notes": self.notes.toPlainText().strip(),
        }
        self.accept()


class TechnicalQueryTab(QWidget):
    def __init__(self, db: DatabaseManager, session: SessionManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.session = session
        self.project_id: Optional[int] = None
        self._rows: list[dict] = []
        self.setObjectName("technicalQueryTab")
        self._build()
        self._load_projects()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        header = QLabel("Technical Query / RFI Register")
        header.setStyleSheet("font-size: 20px; font-weight: 800; color: #087F8C;")
        sub = QLabel(
            "Site engineering queries against drawings, specifications and packages."
        )
        sub.setStyleSheet("color: #64748b;")
        root.addWidget(header)
        root.addWidget(sub)

        kpi = QHBoxLayout()
        self.kpi_open = QLabel("Open: 0")
        self.kpi_overdue = QLabel("Overdue: 0")
        self.kpi_closed = QLabel("Closed: 0")
        for w in (self.kpi_open, self.kpi_overdue, self.kpi_closed):
            w.setStyleSheet(
                "background: white; border: 1px solid #CBE8EB; border-radius: 8px;"
                " padding: 10px 16px; font-weight: 700;"
            )
            kpi.addWidget(w)
        kpi.addStretch()
        root.addLayout(kpi)

        bar = QHBoxLayout()
        self.proj = QComboBox()
        self.proj.currentIndexChanged.connect(self._proj_changed)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search TQ number, description, drawing…")
        self.search.textChanged.connect(self._apply_filters)
        self.filter_status = QComboBox()
        self.filter_status.addItem("All statuses", None)
        for st in TQ_STATUSES:
            self.filter_status.addItem(st, st)
        self.filter_status.currentIndexChanged.connect(self._apply_filters)
        add_btn = QPushButton("Raise TQ")
        add_btn.setProperty("primary", True)
        add_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        add_btn.clicked.connect(self._add)
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export)
        bar.addWidget(QLabel("Project"))
        bar.addWidget(self.proj, 1)
        bar.addWidget(self.search, 2)
        bar.addWidget(self.filter_status)
        bar.addWidget(add_btn)
        bar.addWidget(export_btn)
        root.addLayout(bar)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setColumnHidden(0, True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.doubleClicked.connect(self._edit)
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit)
        close_btn = QPushButton("Mark Closed")
        close_btn.clicked.connect(self._close_selected)
        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(self._delete)
        actions.addWidget(edit_btn)
        actions.addWidget(close_btn)
        actions.addWidget(del_btn)
        actions.addStretch()
        root.addLayout(actions)

    def _load_projects(self):
        self.proj.blockSignals(True)
        self.proj.clear()
        try:
            with self.db.session_scope() as s:
                for p in s.query(Project).order_by(Project.project_code):
                    self.proj.addItem(f"{p.project_code} – {p.title}", p.id)
        except Exception:
            logger.exception("Failed to load projects for technical queries")
        self.proj.blockSignals(False)
        if self.proj.count():
            self._proj_changed()

    def _proj_changed(self):
        self.project_id = self.proj.currentData()
        self.refresh()

    def refresh(self):
        self._rows = []
        if not self.project_id:
            self._apply_filters()
            return
        try:
            with self.db.session_scope() as s:
                items = (
                    s.query(TechnicalQuery)
                    .filter(TechnicalQuery.project_id == self.project_id)
                    .order_by(TechnicalQuery.tq_number)
                    .all()
                )
                for tq in items:
                    self._rows.append({
                        "id": tq.id,
                        "project_id": tq.project_id,
                        "tq_number": tq.tq_number,
                        "raised_date": tq.raised_date,
                        "submitted_date": tq.submitted_date,
                        "raised_by": tq.raised_by or "",
                        "category": tq.category or "",
                        "priority": tq.priority or "Normal",
                        "related_document": tq.related_document or "",
                        "due_date": tq.due_date,
                        "assigned_to": tq.assigned_to or "",
                        "status": tq.status or "Open",
                        "response_received_date": tq.response_received_date,
                        "approved_by": tq.approved_by or "",
                        "description": tq.description or "",
                        "response": tq.response or "",
                        "notes": tq.notes or "",
                    })
        except Exception:
            logger.exception("Failed to load technical queries")
        self._apply_filters()

    def _fmt(self, value) -> str:
        if value is None:
            return ""
        if isinstance(value, (date, datetime)):
            return value.strftime("%Y-%m-%d")
        return str(value)

    def _apply_filters(self):
        query = self.search.text().strip().lower()
        status = self.filter_status.currentData()
        today = date.today()
        self.table.setRowCount(0)
        open_n = overdue = closed = 0
        for row in self._rows:
            if row["status"] == "Closed":
                closed += 1
            elif row["status"] in {"Open", "Submitted"}:
                open_n += 1
                due = row.get("due_date")
                if isinstance(due, date) and due < today:
                    overdue += 1
            if status and row["status"] != status:
                continue
            if query:
                blob = " ".join(str(row.get(k) or "") for k in (
                    "tq_number", "raised_by", "category", "related_document",
                    "assigned_to", "description", "response",
                )).lower()
                if query not in blob:
                    continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            values = [
                row["id"], row["tq_number"], self._fmt(row["raised_date"]),
                row["raised_by"], row["category"], row["priority"],
                row["related_document"], self._fmt(row["due_date"]),
                row["assigned_to"], row["status"],
                self._fmt(row["response_received_date"]),
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                if col == 9:
                    badge = STATUS_BADGES.get(row["status"], {})
                    if badge:
                        item.setBackground(QBrush(QColor(badge["bg"])))
                        item.setForeground(QBrush(QColor(badge["fg"])))
                self.table.setItem(r, col, item)
        self.kpi_open.setText(f"Open: {open_n}")
        self.kpi_overdue.setText(f"Overdue: {overdue}")
        self.kpi_closed.setText(f"Closed: {closed}")

    def _selected(self) -> Optional[dict]:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        pk = int(self.table.item(rows[0].row(), 0).text())
        return next((x for x in self._rows if x["id"] == pk), None)

    def _project_lookups(self):
        with self.db.session_scope() as s:
            projects = s.query(Project).order_by(Project.project_code).all()
            return [
                type("P", (), {"id": p.id, "project_code": p.project_code, "title": p.title})()
                for p in projects
            ]

    def _add(self):
        projects = self._project_lookups()
        if not projects:
            QMessageBox.information(self, "Project", "Register a project first.")
            return
        dlg = TechnicalQueryDialog(self, projects=projects)
        if self.project_id:
            for i in range(dlg.project_combo.count()):
                if dlg.project_combo.itemData(i) == self.project_id:
                    dlg.project_combo.setCurrentIndex(i)
                    break
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.result_data
        try:
            with self.db.session_scope() as s:
                s.add(TechnicalQuery(**d))
            self.refresh()
        except Exception as exc:
            logger.exception("Failed to create technical query")
            QMessageBox.critical(self, "Error", str(exc))

    def _edit(self):
        row = self._selected()
        if not row:
            QMessageBox.information(self, "Select", "Select a technical query.")
            return
        dlg = TechnicalQueryDialog(self, projects=self._project_lookups(), existing=row)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.result_data
        try:
            with self.db.session_scope() as s:
                rec = s.get(TechnicalQuery, row["id"])
                if rec:
                    for key, value in d.items():
                        if key != "project_id":
                            setattr(rec, key, value)
            self.refresh()
        except Exception as exc:
            logger.exception("Failed to update technical query")
            QMessageBox.critical(self, "Error", str(exc))

    def _close_selected(self):
        row = self._selected()
        if not row:
            return
        try:
            with self.db.session_scope() as s:
                rec = s.get(TechnicalQuery, row["id"])
                if rec:
                    rec.status = "Closed"
                    rec.response_received_date = rec.response_received_date or date.today()
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _delete(self):
        row = self._selected()
        if not row:
            return
        if QMessageBox.question(
            self, "Delete", f"Delete {row['tq_number']}?",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            with self.db.session_scope() as s:
                rec = s.get(TechnicalQuery, row["id"])
                if rec:
                    s.delete(rec)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _export(self):
        if not self._rows:
            QMessageBox.information(self, "Export", "No technical queries to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export TQ register", "technical_queries.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self._rows[0].keys()))
            writer.writeheader()
            writer.writerows(self._rows)
