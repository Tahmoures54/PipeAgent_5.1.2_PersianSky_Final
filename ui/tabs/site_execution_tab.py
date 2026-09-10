# -*- coding: utf-8 -*-
"""Integrated EPC site execution control center."""
from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QGroupBox,
    QLineEdit, QComboBox, QMessageBox, QFormLayout, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QDateEdit, QTextEdit, QSpinBox,
)

from db.models import (
    CommissioningRecord, EquipmentRecord, InstrumentRecord, PermitRecord,
    SiteIssueRecord,
)
from services.site_execution_service import SiteExecutionService


class SiteExecutionTab(QWidget):
    """Field-oriented workspace for cross-discipline site control."""

    def __init__(self, db, session_manager):
        super().__init__()
        self.db = db
        self.session_manager = session_manager
        self.service = SiteExecutionService(db)
        self.setObjectName("siteExecutionTab")
        self._build_ui()
        self.refresh_all()

    # ── UI BUILD ─────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("Site Execution Control Center")
        title.setStyleSheet("font-size:24px;font-weight:900;color:#087F8C;")
        root.addWidget(title)

        subtitle = QLabel(
            "Instrumentation, permits, HSE actions, equipment, commissioning, "
            "and site issues in one execution workflow."
        )
        subtitle.setStyleSheet("color:#5F7D84;font-size:12px;")
        root.addWidget(subtitle)

        self.kpi_grid = QGridLayout()
        self.kpi_labels = {}
        keys = (
            "instruments", "calibration_overdue", "permits_expiring",
            "equipment_unavailable", "open_issues", "turnover_blockers",
        )
        for i, key in enumerate(keys):
            card = QGroupBox(key.replace("_", " ").title())
            value = QLabel("0")
            value.setStyleSheet("font-size:22px;font-weight:900;color:#087F8C;")
            box = QVBoxLayout(card)
            box.addWidget(value)
            self.kpi_labels[key] = value
            self.kpi_grid.addWidget(card, 0, i)
        root.addLayout(self.kpi_grid)

        actions = QHBoxLayout()
        refresh = QPushButton("Refresh Control Center")
        refresh.clicked.connect(self.refresh_all)
        actions.addWidget(refresh)
        actions.addStretch()
        root.addLayout(actions)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._instrument_tab(),       "Instrumentation & Loop Checks")
        self.tabs.addTab(self._permit_tab(),           "HSE & Permits")
        self.tabs.addTab(self._equipment_tab(),        "Equipment & Resources")
        self.tabs.addTab(self._issue_tab(),            "Site Issues & Actions")
        self.tabs.addTab(self._commissioning_tab(),    "Commissioning & Turnover")
        root.addWidget(self.tabs, 1)

        self.alert_label = QLabel()
        self.alert_label.setWordWrap(True)
        root.addWidget(self.alert_label)

    def _table(self, headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.setAlternatingRowColors(True)
        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        return t

    def _instrument_tab(self):
        w = QWidget(); layout = QVBoxLayout(w)
        bar = QHBoxLayout()
        add = QPushButton("Add Instrument")
        add.clicked.connect(self._add_instrument)
        bar.addWidget(add); bar.addStretch(); layout.addLayout(bar)
        self.instrument_table = self._table(
            ["Tag", "Type", "Area", "Loop", "Calibration", "Loop Check", "Status"]
        )
        layout.addWidget(self.instrument_table); return w

    def _permit_tab(self):
        w = QWidget(); layout = QVBoxLayout(w)
        bar = QHBoxLayout()
        add = QPushButton("Add Permit")
        add.clicked.connect(self._add_permit)
        bar.addWidget(add); bar.addStretch(); layout.addLayout(bar)
        self.permit_table = self._table(
            ["Permit", "Type", "Area", "Risk", "Expires", "Status"]
        )
        layout.addWidget(self.permit_table); return w

    def _equipment_tab(self):
        w = QWidget(); layout = QVBoxLayout(w)
        bar = QHBoxLayout()
        add = QPushButton("Add Equipment")
        add.clicked.connect(self._add_equipment)
        bar.addWidget(add); bar.addStretch(); layout.addLayout(bar)
        self.equipment_table = self._table(
            ["Asset", "Type", "Area", "Availability", "Utilization", "Inspection", "Status"]
        )
        layout.addWidget(self.equipment_table); return w

    def _issue_tab(self):
        w = QWidget(); layout = QVBoxLayout(w)
        bar = QHBoxLayout()
        add = QPushButton("Add Site Issue")
        add.clicked.connect(self._add_issue)
        bar.addWidget(add); bar.addStretch(); layout.addLayout(bar)
        self.issue_table = self._table(
            ["Issue", "Category", "Discipline", "Priority", "Owner", "Due", "Status"]
        )
        layout.addWidget(self.issue_table); return w

    def _commissioning_tab(self):
        w = QWidget(); layout = QVBoxLayout(w)
        bar = QHBoxLayout()
        add = QPushButton("Add System")
        add.clicked.connect(self._add_commissioning)
        bar.addWidget(add); bar.addStretch(); layout.addLayout(bar)
        self.commissioning_table = self._table(
            ["System", "Subsystem", "Phase", "Progress", "Punch", "Test", "Turnover"]
        )
        layout.addWidget(self.commissioning_table); return w

    # ── REFRESH ──────────────────────────────────────────────
    def refresh_all(self):
        k = self.service.kpis()
        for key, label in self.kpi_labels.items():
            label.setText(str(k.get(key, 0)))

        flags = self.service.predictive_flags()
        if flags:
            self.alert_label.setText(
                "<b>Execution Watch:</b> " +
                " | ".join(
                    f"<b>{x['severity']}</b> {x['title']}: {x['detail']}"
                    for x in flags
                )
            )
            self.alert_label.setStyleSheet(
                "background:#FFF8E6;border:1px solid #F0D58A;"
                "border-radius:7px;padding:9px;color:#735B18;"
            )
        else:
            self.alert_label.setText(
                "<b>Execution Watch:</b> No active cross-discipline blockers detected."
            )
            self.alert_label.setStyleSheet(
                "background:#EAF8F3;border:1px solid #B5E2D0;"
                "border-radius:7px;padding:9px;color:#146B4E;"
            )

        self._load_instruments()
        self._load_permits()
        self._load_equipment()
        self._load_issues()
        self._load_commissioning()

    def _load_instruments(self):
        with self.db.session_scope() as s:
            rows = s.query(InstrumentRecord).order_by(InstrumentRecord.id.desc()).all()
            self.instrument_table.setRowCount(len(rows))
            for r, x in enumerate(rows):
                vals = [
                    x.tag_number, x.instrument_type or "", x.area or "",
                    x.loop_number or "", str(x.calibration_status),
                    str(x.loop_check_status), str(x.status),
                ]
                for c, v in enumerate(vals):
                    self.instrument_table.setItem(r, c, QTableWidgetItem(v))

    def _load_permits(self):
        with self.db.session_scope() as s:
            rows = s.query(PermitRecord).order_by(PermitRecord.id.desc()).all()
            self.permit_table.setRowCount(len(rows))
            for r, x in enumerate(rows):
                vals = [
                    x.permit_number, x.permit_type, x.area or "",
                    x.risk_level,
                    x.expires_at.strftime("%Y-%m-%d %H:%M") if x.expires_at else "",
                    x.status,
                ]
                for c, v in enumerate(vals):
                    self.permit_table.setItem(r, c, QTableWidgetItem(v))

    def _load_equipment(self):
        with self.db.session_scope() as s:
            rows = s.query(EquipmentRecord).order_by(EquipmentRecord.id.desc()).all()
            self.equipment_table.setRowCount(len(rows))
            for r, x in enumerate(rows):
                vals = [
                    x.asset_number, x.equipment_type, x.area or "",
                    f"{x.availability_pct:.0f}%", f"{x.utilization_pct:.0f}%",
                    str(x.inspection_due or ""), x.status,
                ]
                for c, v in enumerate(vals):
                    self.equipment_table.setItem(r, c, QTableWidgetItem(v))

    def _load_issues(self):
        with self.db.session_scope() as s:
            rows = s.query(SiteIssueRecord).order_by(SiteIssueRecord.id.desc()).all()
            self.issue_table.setRowCount(len(rows))
            for r, x in enumerate(rows):
                vals = [
                    x.issue_number, x.category, x.discipline or "",
                    x.priority, x.owner or "", str(x.due_date or ""), x.status,
                ]
                for c, v in enumerate(vals):
                    self.issue_table.setItem(r, c, QTableWidgetItem(v))

    def _load_commissioning(self):
        with self.db.session_scope() as s:
            rows = s.query(CommissioningRecord).order_by(CommissioningRecord.id.desc()).all()
            self.commissioning_table.setRowCount(len(rows))
            for r, x in enumerate(rows):
                progress = (
                    f"{(x.checklist_complete / x.checklist_total * 100):.0f}%"
                    if x.checklist_total else "0%"
                )
                vals = [
                    x.system_code, x.subsystem or "", x.commissioning_phase,
                    progress, str(x.punch_open), x.test_status, x.turnover_status,
                ]
                for c, v in enumerate(vals):
                    self.commissioning_table.setItem(r, c, QTableWidgetItem(v))

    # ── DIALOG HELPER ────────────────────────────────────────
    def _dialog(self, title, fields):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        form = QFormLayout(dialog)
        widgets = {}
        for name, widget in fields:
            form.addRow(name, widget)
            widgets[name] = widget
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        return dialog, widgets

    # ── ADD HANDLERS ─────────────────────────────────────────
    def _add_instrument(self):
        fields = [
            ("Tag Number", QLineEdit()), ("Instrument Type", QLineEdit()),
            ("Area", QLineEdit()), ("Loop Number", QLineEdit()),
            ("Calibration Status", QComboBox()), ("Loop Check", QComboBox()),
        ]
        fields[4][1].addItems(["Pending", "Passed", "Failed", "Expired"])
        fields[5][1].addItems(["Not Started", "Ready", "Passed", "Failed"])
        d, w = self._dialog("Add Instrument", fields)
        if d.exec():
            with self.db.session_scope() as s:
                s.add(InstrumentRecord(
                    tag_number=w["Tag Number"].text().strip(),
                    instrument_type=w["Instrument Type"].text(),
                    area=w["Area"].text(),
                    loop_number=w["Loop Number"].text(),
                    calibration_status=w["Calibration Status"].currentText(),
                    loop_check_status=w["Loop Check"].currentText(),
                ))
            self.refresh_all()

    def _add_permit(self):
        fields = [
            ("Permit Number", QLineEdit()), ("Permit Type", QComboBox()),
            ("Area", QLineEdit()), ("Risk", QComboBox()),
        ]
        fields[1][1].addItems([
            "Hot Work", "Confined Space", "Work at Height", "Excavation",
            "Lifting", "Electrical", "General",
        ])
        fields[3][1].addItems(["Low", "Medium", "High", "Critical"])
        d, w = self._dialog("Add Permit", fields)
        if d.exec():
            with self.db.session_scope() as s:
                s.add(PermitRecord(
                    permit_number=w["Permit Number"].text().strip(),
                    permit_type=w["Permit Type"].currentText(),
                    area=w["Area"].text(),
                    risk_level=w["Risk"].currentText(),
                ))
            self.refresh_all()

    def _add_equipment(self):
        fields = [
            ("Asset Number", QLineEdit()), ("Equipment Type", QLineEdit()),
            ("Area", QLineEdit()), ("Availability %", QDoubleSpinBox()),
            ("Utilization %", QDoubleSpinBox()), ("Status", QComboBox()),
        ]
        fields[3][1].setRange(0, 100)
        fields[4][1].setRange(0, 100)
        fields[5][1].addItems([
            "Available", "In Use", "Maintenance", "Down", "Unavailable",
        ])
        d, w = self._dialog("Add Equipment", fields)
        if d.exec():
            with self.db.session_scope() as s:
                s.add(EquipmentRecord(
                    asset_number=w["Asset Number"].text().strip(),
                    equipment_type=w["Equipment Type"].text(),
                    area=w["Area"].text(),
                    availability_pct=w["Availability %"].value(),
                    utilization_pct=w["Utilization %"].value(),
                    status=w["Status"].currentText(),
                ))
            self.refresh_all()

    def _add_issue(self):
        fields = [
            ("Issue Number", QLineEdit()), ("Category", QComboBox()),
            ("Discipline", QLineEdit()), ("Title", QLineEdit()),
            ("Priority", QComboBox()), ("Owner", QLineEdit()),
        ]
        fields[1][1].addItems([
            "Constraint", "Safety", "Quality", "Material",
            "Engineering", "Document", "Interface", "Logistics", "Access",
        ])
        fields[4][1].addItems(["Low", "Medium", "High", "Critical"])
        d, w = self._dialog("Add Site Issue", fields)
        if d.exec():
            with self.db.session_scope() as s:
                s.add(SiteIssueRecord(
                    issue_number=w["Issue Number"].text().strip(),
                    category=w["Category"].currentText(),
                    discipline=w["Discipline"].text(),
                    title=w["Title"].text(),
                    priority=w["Priority"].currentText(),
                    owner=w["Owner"].text(),
                ))
            self.refresh_all()

    def _add_commissioning(self):
        fields = [
            ("System Code", QLineEdit()), ("Subsystem", QLineEdit()),
            ("Phase", QComboBox()), ("Checklist Total", QLineEdit()),
            ("Checklist Complete", QLineEdit()), ("Punch Open", QLineEdit()),
        ]
        fields[2][1].addItems([
            "Mechanical Completion", "Pre-Commissioning", "Commissioning",
            "Energization", "Start-Up", "Performance Test",
        ])
        d, w = self._dialog("Add Commissioning System", fields)
        if d.exec():
            with self.db.session_scope() as s:
                s.add(CommissioningRecord(
                    system_code=w["System Code"].text().strip(),
                    subsystem=w["Subsystem"].text(),
                    commissioning_phase=w["Phase"].currentText(),
                    checklist_total=int(w["Checklist Total"].text() or 0),
                    checklist_complete=int(w["Checklist Complete"].text() or 0),
                    punch_open=int(w["Punch Open"].text() or 0),
                ))
            self.refresh_all()