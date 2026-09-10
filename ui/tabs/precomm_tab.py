# -*- coding: utf-8 -*-
# ui/tabs/precomm_tab.py – PipeAgent 5.0
# Pre-Commissioning Operations & Quality Clearance Hub
#
# Modules Included:
# 1. 💧 Flushing & Chemical Cleaning
# 2. 🔍 Sensitive Leak & Tightness Testing
# 3. 📦 Equipment / Piping Final Box-Up
# 4. ⚗️ Positive Material Identification (PMI)
# 5. 📏 Spool Dimensional & Tolerance Inspection
# 6. 🔧 Spring Hangers & Expansion Joints Commissioning
# 7. 🛡️ Piping & Valve Preservation / Nitrogen Purge

from __future__ import annotations

import csv
import logging
import datetime
from pathlib import Path
from typing import Optional, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QMessageBox, QHeaderView, QGroupBox, QComboBox,
    QScrollArea, QFormLayout, QLineEdit, QDoubleSpinBox,
    QDateEdit, QDialog, QCheckBox, QSpinBox, QTextEdit,
    QFrame, QFileDialog, QApplication, QMenu, QAbstractItemView
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor, QFont, QBrush, QCursor, QAction

from db.manager import DatabaseManager
from db.models import Project
from security.session import SessionManager

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

PRECOMM_BADGES = {
    "Accepted":    {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Passed":      {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Completed":   {"bg": "#dcfce7", "fg": "#166534", "icon": "🟢"},
    "In Service":  {"bg": "#dcfce7", "fg": "#166534", "icon": "🟢"},
    "Good":        {"bg": "#dcfce7", "fg": "#166534", "icon": "🟢"},
    "Rejected":    {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Failed":      {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Leak Found":  {"bg": "#fee2e2", "fg": "#991b1b", "icon": "⚠️"},
    "Pending":     {"bg": "#fef3c7", "fg": "#92400e", "icon": "⏳"},
    "In Progress": {"bg": "#e0f2fe", "fg": "#075985", "icon": "🔄"},
    "Open":        {"bg": "#fff1e6", "fg": "#9a3412", "icon": "📂"},
}
DEFAULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}

# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

PRECOMM_STYLESHEET = """
    QWidget#precommTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0e304a, stop:1 #1e4b6e);
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
    QTabWidget::pane {
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        background: white;
        top: -1px;
    }
    QTabBar::tab {
        background: #f1f5f9;
        color: #475569;
        padding: 9px 15px;
        border: 1px solid #cbd5e1;
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        font-weight: 700;
        font-size: 11px;
        margin-right: 2px;
    }
    QTabBar::tab:selected {
        background: white;
        color: #0e304a;
        border-bottom: 2px solid #3b82f6;
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
    QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit, QTextEdit {
        padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 12px;
    }
"""

# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class PreCommKPICard(QFrame):
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
        else:
            self.val_lbl.setStyleSheet("color: #0f172a; font-size: 19px; font-weight: 800;")


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class PreCommTab(QWidget):
    def __init__(self, db: DatabaseManager, session_manager: SessionManager):
        super().__init__()
        self.setObjectName("precommTab")
        self.db = db
        self.session_manager = session_manager
        self.project_id: Optional[int] = None

        self._build_ui()
        self.setStyleSheet(PRECOMM_STYLESHEET)
        self._load_projects()

    def _get_session(self):
        return self.db.get_session()

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
        t = QLabel("🚀 Piping Pre-Commissioning & Quality Clearance")
        t.setObjectName("mainTitle")
        s = QLabel("Line Flushing, Sensitive Leak Testing, Vessel Box-up, PMI Spectroscopy, Dimensional Checks, Spring Hangers & Preservation.")
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
        self.cmb_project.currentIndexChanged.connect(self._on_project_changed)
        proj_box.addWidget(self.cmb_project)

        btn_r = QPushButton("🔄 Refresh All")
        btn_r.setObjectName("secondaryBtn")
        btn_r.clicked.connect(self.refresh)
        proj_box.addWidget(btn_r)
        hdr_lay.addLayout(proj_box)

        root.addWidget(header_card)

        # Implementation note.
        kpi_lay = QHBoxLayout()
        kpi_lay.setSpacing(8)

        self.kpi_flush = PreCommKPICard("Flushing Done", "💧", "#0ea5e9")
        self.kpi_leak = PreCommKPICard("Leak Test Cleared", "🔍", "#10b981")
        self.kpi_boxup = PreCommKPICard("Box-Up Closed", "📦", "#8b5cf6")
        self.kpi_pmi = PreCommKPICard("PMI Verified", "⚗️", "#f59e0b")
        self.kpi_spring = PreCommKPICard("Springs In-Service", "🔧", "#059669")

        for k in [self.kpi_flush, self.kpi_leak, self.kpi_boxup, self.kpi_pmi, self.kpi_spring]:
            kpi_lay.addWidget(k)
        root.addLayout(kpi_lay)

        # Implementation note.
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_flushing_widget(), "💧 Flushing / Blowing")
        self.tabs.addTab(self._build_leak_widget(), "🔍 Sensitive Leak Test")
        self.tabs.addTab(self._build_boxup_widget(), "📦 Final Box-Up")
        self.tabs.addTab(self._build_pmi_widget(), "⚗️ PMI Material Check")
        self.tabs.addTab(self._build_dim_widget(), "📏 Spool Dimensions")
        self.tabs.addTab(self._build_spring_widget(), "🔧 Spring Hangers")
        self.tabs.addTab(self._build_preservation_widget(), "🛡️ Preservation Logs")
        root.addWidget(self.tabs, 1)

    def _load_projects(self):
        self.cmb_project.blockSignals(True)
        self.cmb_project.clear()
        try:
            with self.db.session_scope() as s:
                for p in s.query(Project).order_by(Project.project_code):
                    self.cmb_project.addItem(f"{p.project_code} – {p.title}", p.id)
        except Exception as e:
            logger.exception("Failed to load projects in PreCommTab")

        self.cmb_project.blockSignals(False)
        if self.cmb_project.count():
            self._on_project_changed()

    def _on_project_changed(self):
        self.project_id = self.cmb_project.currentData()
        self.refresh()

    def _setup_table_style(self, table: QTableWidget):
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _apply_badge(self, item: QTableWidgetItem, text: str):
        badge = PRECOMM_BADGES.get(text, DEFAULT_BADGE)
        item.setText(f"{badge['icon']} {text}")
        item.setBackground(QBrush(QColor(badge["bg"])))
        item.setForeground(QBrush(QColor(badge["fg"])))
        f = item.font()
        f.setBold(True)
        item.setFont(f)

    # ══════════════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════════════

    def _build_flushing_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_flush = QLineEdit()
        self.txt_search_flush.setPlaceholderText("🔍 Search Line Number, Method, Certificate No...")
        self.txt_search_flush.textChanged.connect(self._filter_flushing)
        tb.addWidget(self.txt_search_flush, 1)

        self.cmb_filter_flush = QComboBox()
        self.cmb_filter_flush.addItems(["All Results", "Accepted", "Pending", "Rejected"])
        self.cmb_filter_flush.currentIndexChanged.connect(self._filter_flushing)
        tb.addWidget(self.cmb_filter_flush)

        btn_add = QPushButton("➕ Record Flushing")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_flushing)
        tb.addWidget(btn_add)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(lambda: self._export_to_csv(self.flush_tbl, "Flushing_Report"))
        tb.addWidget(btn_exp)

        btn_ref = QPushButton("🔄 Refresh")
        btn_ref.setObjectName("secondaryBtn")
        btn_ref.clicked.connect(self.refresh_flushing)
        tb.addWidget(btn_ref)
        l.addLayout(tb)

        self.flush_tbl = QTableWidget(0, 9)
        self.flush_tbl.setHorizontalHeaderLabels([
            "ID", "Line Number", "Cleaning Method", "Medium",
            "Velocity (m/s)", "Duration (Hrs)", "QC Result", "Execution Date", "Certificate No"
        ])
        self._setup_table_style(self.flush_tbl)
        self.flush_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.flush_tbl.customContextMenuRequested.connect(
            lambda pos: self._table_context_menu(pos, self.flush_tbl, "flushing")
        )
        l.addWidget(self.flush_tbl)
        return w

    def refresh_flushing(self):
        if not self.project_id:
            return
        s = self._get_session()
        try:
            from services.precomm_service import PreCommService
            recs = PreCommService(s).flushing.get_all(self.project_id)
            self.flush_tbl.setSortingEnabled(False)
            self.flush_tbl.setRowCount(0)
            passed = 0

            for r in recs:
                row = self.flush_tbl.rowCount()
                self.flush_tbl.insertRow(row)
                self.flush_tbl.setItem(row, 0, QTableWidgetItem(str(r.id)))
                self.flush_tbl.setItem(row, 1, QTableWidgetItem(r.line_number or ""))
                self.flush_tbl.setItem(row, 2, QTableWidgetItem(r.flush_method or ""))
                self.flush_tbl.setItem(row, 3, QTableWidgetItem(r.flush_medium or ""))
                self.flush_tbl.setItem(row, 4, QTableWidgetItem(str(r.flow_velocity_mps or "")))
                self.flush_tbl.setItem(row, 5, QTableWidgetItem(str(r.duration_hours or "")))

                res_txt = r.result or "Pending"
                res_item = QTableWidgetItem(res_txt)
                self._apply_badge(res_item, res_txt)
                self.flush_tbl.setItem(row, 6, res_item)

                self.flush_tbl.setItem(row, 7, QTableWidgetItem(str(r.start_date or "")))
                self.flush_tbl.setItem(row, 8, QTableWidgetItem(r.certificate_no or ""))

                if res_txt in ("Accepted", "Passed"):
                    passed += 1

            self.flush_tbl.setSortingEnabled(True)
            self.kpi_flush.set_value(f"{passed}/{len(recs)}", highlight="green" if passed == len(recs) and len(recs) > 0 else None)
            s.commit()
        except Exception as e:
            s.rollback()
            logger.exception("Error in refresh_flushing")
        finally:
            s.close()

    def _filter_flushing(self):
        query = self.txt_search_flush.text().strip().lower()
        res_f = self.cmb_filter_flush.currentText()
        for r in range(self.flush_tbl.rowCount()):
            line = self.flush_tbl.item(r, 1).text().lower()
            cert = self.flush_tbl.item(r, 8).text().lower()
            res = self.flush_tbl.item(r, 6).text()
            match_txt = query in line or query in cert
            match_res = (res_f == "All Results") or (res_f in res)
            self.flush_tbl.setRowHidden(r, not (match_txt and match_res))

    def _add_flushing(self):
        if not self.project_id:
            QMessageBox.warning(self, "Project", "Select a project first.")
            return
        dlg = FlushingDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            s = self._get_session()
            try:
                from services.precomm_service import PreCommService
                PreCommService(s).record_flushing(self.project_id, **dlg.result_data)
                s.commit()
                self.refresh_flushing()
                QMessageBox.information(self, "Success", "Flushing record registered.")
            except Exception as e:
                s.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                s.close()

    # ══════════════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════════════

    def _build_leak_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_leak = QLineEdit()
        self.txt_search_leak.setPlaceholderText("🔍 Search Line, Test Method, Medium...")
        self.txt_search_leak.textChanged.connect(self._filter_leak)
        tb.addWidget(self.txt_search_leak, 1)

        self.cmb_filter_leak = QComboBox()
        self.cmb_filter_leak.addItems(["All Results", "Passed", "Leak Found", "Pending"])
        self.cmb_filter_leak.currentIndexChanged.connect(self._filter_leak)
        tb.addWidget(self.cmb_filter_leak)

        btn_add = QPushButton("➕ Record Leak Test")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_leak)
        tb.addWidget(btn_add)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(lambda: self._export_to_csv(self.leak_tbl, "Leak_Test_Report"))
        tb.addWidget(btn_exp)

        btn_ref = QPushButton("🔄 Refresh")
        btn_ref.setObjectName("secondaryBtn")
        btn_ref.clicked.connect(self.refresh_leak)
        tb.addWidget(btn_ref)
        l.addLayout(tb)

        self.leak_tbl = QTableWidget(0, 10)
        self.leak_tbl.setHorizontalHeaderLabels([
            "ID", "Piping Line No", "Test Technique", "Test Medium",
            "Pressure (bar)", "Duration (min)", "Joints Checked", "Leaks Detected", "Result", "Test Date"
        ])
        self._setup_table_style(self.leak_tbl)
        self.leak_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.leak_tbl.customContextMenuRequested.connect(
            lambda pos: self._table_context_menu(pos, self.leak_tbl, "leak")
        )
        l.addWidget(self.leak_tbl)
        return w

    def refresh_leak(self):
        if not self.project_id:
            return
        s = self._get_session()
        try:
            from services.precomm_service import PreCommService
            recs = PreCommService(s).leak_test.get_all(self.project_id)
            self.leak_tbl.setSortingEnabled(False)
            self.leak_tbl.setRowCount(0)
            passed = 0

            for r in recs:
                row = self.leak_tbl.rowCount()
                self.leak_tbl.insertRow(row)
                self.leak_tbl.setItem(row, 0, QTableWidgetItem(str(r.id)))
                self.leak_tbl.setItem(row, 1, QTableWidgetItem(r.line_number or ""))
                self.leak_tbl.setItem(row, 2, QTableWidgetItem(r.leak_test_method or ""))
                self.leak_tbl.setItem(row, 3, QTableWidgetItem(r.test_medium or ""))
                self.leak_tbl.setItem(row, 4, QTableWidgetItem(str(r.test_pressure_bar or "")))
                self.leak_tbl.setItem(row, 5, QTableWidgetItem(str(r.test_duration_min or "")))
                self.leak_tbl.setItem(row, 6, QTableWidgetItem(str(r.joints_tested or 0)))

                leak_cnt = r.leaks_found or 0
                leak_item = QTableWidgetItem(str(leak_cnt))
                if leak_cnt > 0:
                    leak_item.setForeground(QBrush(QColor("#991b1b")))
                    f_bold = leak_item.font(); f_bold.setBold(True); leak_item.setFont(f_bold)
                self.leak_tbl.setItem(row, 7, leak_item)

                res_txt = r.result or ("Passed" if leak_cnt == 0 else "Leak Found")
                res_item = QTableWidgetItem(res_txt)
                self._apply_badge(res_item, res_txt)
                self.leak_tbl.setItem(row, 8, res_item)

                self.leak_tbl.setItem(row, 9, QTableWidgetItem(str(r.test_date or "")))

                if res_txt in ("Passed", "Accepted"):
                    passed += 1

            self.leak_tbl.setSortingEnabled(True)
            rate = (passed / len(recs) * 100) if recs else 0.0
            self.kpi_leak.set_value(f"{rate:.1f}%", highlight="green" if rate >= 98.0 else ("red" if rate < 90.0 and len(recs) > 0 else None))
            s.commit()
        except Exception as e:
            s.rollback()
            logger.exception("Error in refresh_leak")
        finally:
            s.close()

    def _filter_leak(self):
        query = self.txt_search_leak.text().strip().lower()
        res_f = self.cmb_filter_leak.currentText()
        for r in range(self.leak_tbl.rowCount()):
            line = self.leak_tbl.item(r, 1).text().lower()
            method = self.leak_tbl.item(r, 2).text().lower()
            res = self.leak_tbl.item(r, 8).text()
            match_txt = query in line or query in method
            match_res = (res_f == "All Results") or (res_f in res)
            self.leak_tbl.setRowHidden(r, not (match_txt and match_res))

    def _add_leak(self):
        if not self.project_id:
            QMessageBox.warning(self, "Project", "Select a project first.")
            return
        dlg = LeakTestDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            s = self._get_session()
            try:
                from services.precomm_service import PreCommService
                PreCommService(s).record_leak_test(self.project_id, **dlg.result_data)
                s.commit()
                self.refresh_leak()
                QMessageBox.information(self, "Success", "Leak test results registered.")
            except Exception as e:
                s.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                s.close()

    # ══════════════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════════════

    def _build_boxup_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_box = QLineEdit()
        self.txt_search_box.setPlaceholderText("🔍 Search Line Number, Equipment Tag...")
        self.txt_search_box.textChanged.connect(self._filter_boxup)
        tb.addWidget(self.txt_search_box, 1)

        self.cmb_filter_box = QComboBox()
        self.cmb_filter_box.addItems(["All Statuses", "Completed", "Open", "Pending"])
        self.cmb_filter_box.currentIndexChanged.connect(self._filter_boxup)
        tb.addWidget(self.cmb_filter_box)

        btn_add = QPushButton("➕ Register Box-Up")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_boxup)
        tb.addWidget(btn_add)

        btn_comp = QPushButton("✅ Mark Closed & Sealed")
        btn_comp.setObjectName("secondaryBtn")
        btn_comp.clicked.connect(self._complete_boxup)
        tb.addWidget(btn_comp)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(lambda: self._export_to_csv(self.box_tbl, "BoxUp_Register"))
        tb.addWidget(btn_exp)

        btn_ref = QPushButton("🔄 Refresh")
        btn_ref.setObjectName("secondaryBtn")
        btn_ref.clicked.connect(self.refresh_boxup)
        tb.addWidget(btn_ref)
        l.addLayout(tb)

        self.box_tbl = QTableWidget(0, 10)
        self.box_tbl.setHorizontalHeaderLabels([
            "ID", "Line Number", "Equipment Tag", "Internal Insp.", "Cleanliness",
            "FOD Free", "Gasket Verified", "Bolt Torque", "Status", "Box-Up Date"
        ])
        self._setup_table_style(self.box_tbl)
        self.box_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.box_tbl.customContextMenuRequested.connect(
            lambda pos: self._table_context_menu(pos, self.box_tbl, "boxup")
        )
        l.addWidget(self.box_tbl)
        return w

    def refresh_boxup(self):
        if not self.project_id:
            return
        s = self._get_session()
        try:
            from services.precomm_service import PreCommService
            recs = PreCommService(s).boxup.get_all(self.project_id)
            self.box_tbl.setSortingEnabled(False)
            self.box_tbl.setRowCount(0)
            closed_cnt = 0
            yn = lambda v: "✅ Verified" if v else "❌ Pending"

            for r in recs:
                row = self.box_tbl.rowCount()
                self.box_tbl.insertRow(row)
                self.box_tbl.setItem(row, 0, QTableWidgetItem(str(r.id)))
                self.box_tbl.setItem(row, 1, QTableWidgetItem(r.line_number or ""))
                self.box_tbl.setItem(row, 2, QTableWidgetItem(r.equipment_tag or ""))
                self.box_tbl.setItem(row, 3, QTableWidgetItem(yn(r.internal_inspection_done)))
                self.box_tbl.setItem(row, 4, QTableWidgetItem(yn(r.cleanliness_verified)))
                self.box_tbl.setItem(row, 5, QTableWidgetItem(yn(r.foreign_material_free)))
                self.box_tbl.setItem(row, 6, QTableWidgetItem(yn(r.gasket_installed)))
                self.box_tbl.setItem(row, 7, QTableWidgetItem(yn(r.bolt_torque_verified)))

                st_txt = r.status or "Open"
                st_item = QTableWidgetItem(st_txt)
                self._apply_badge(st_item, st_txt)
                self.box_tbl.setItem(row, 8, st_item)

                self.box_tbl.setItem(row, 9, QTableWidgetItem(str(r.boxup_date or "")))

                if st_txt in ("Completed", "Closed", "Accepted"):
                    closed_cnt += 1

            self.box_tbl.setSortingEnabled(True)
            self.kpi_boxup.set_value(f"{closed_cnt}/{len(recs)}", highlight="green" if closed_cnt == len(recs) and len(recs) > 0 else None)
            s.commit()
        except Exception as e:
            s.rollback()
            logger.exception("Error in refresh_boxup")
        finally:
            s.close()

    def _filter_boxup(self):
        query = self.txt_search_box.text().strip().lower()
        st_f = self.cmb_filter_box.currentText()
        for r in range(self.box_tbl.rowCount()):
            line = self.box_tbl.item(r, 1).text().lower()
            eq = self.box_tbl.item(r, 2).text().lower()
            st = self.box_tbl.item(r, 8).text()
            match_txt = query in line or query in eq
            match_st = (st_f == "All Statuses") or (st_f in st)
            self.box_tbl.setRowHidden(r, not (match_txt and match_st))

    def _add_boxup(self):
        if not self.project_id:
            QMessageBox.warning(self, "Project", "Select a project first.")
            return
        dlg = BoxUpDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            s = self._get_session()
            try:
                from services.precomm_service import PreCommService
                PreCommService(s).record_boxup(self.project_id, **dlg.result_data)
                s.commit()
                self.refresh_boxup()
                QMessageBox.information(self, "Success", "Box-Up protocol registered.")
            except Exception as e:
                s.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                s.close()

    def _complete_boxup(self):
        row = self.box_tbl.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection", "Select a Box-Up entry from the table first.")
            return
        bid = int(self.box_tbl.item(row, 0).text())
        s = self._get_session()
        try:
            from services.precomm_service import PreCommService
            u_name = getattr(self.session_manager, 'username', 'admin')
            PreCommService(s).complete_boxup(bid, u_name)
            s.commit()
            self.refresh_boxup()
            QMessageBox.information(self, "Verified", f"Box-Up Protocol ID {bid} marked as Completed & Sealed by {u_name}.")
        except Exception as e:
            s.rollback()
            QMessageBox.critical(self, "Error", str(e))
        finally:
            s.close()

    # ══════════════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════════════

    def _build_pmi_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_pmi = QLineEdit()
        self.txt_search_pmi.setPlaceholderText("🔍 Search Heat Number, Specified/Actual Material, Component...")
        self.txt_search_pmi.textChanged.connect(self._filter_pmi)
        tb.addWidget(self.txt_search_pmi, 1)

        self.cmb_filter_pmi = QComboBox()
        self.cmb_filter_pmi.addItems(["All Results", "Accepted", "Rejected", "Pending"])
        self.cmb_filter_pmi.currentIndexChanged.connect(self._filter_pmi)
        tb.addWidget(self.cmb_filter_pmi)

        btn_add = QPushButton("➕ Record PMI Test")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_pmi)
        tb.addWidget(btn_add)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(lambda: self._export_to_csv(self.pmi_tbl, "PMI_Inspection_Report"))
        tb.addWidget(btn_exp)

        btn_ref = QPushButton("🔄 Refresh")
        btn_ref.setObjectName("secondaryBtn")
        btn_ref.clicked.connect(self.refresh_pmi)
        tb.addWidget(btn_ref)
        l.addLayout(tb)

        self.pmi_tbl = QTableWidget(0, 9)
        self.pmi_tbl.setHorizontalHeaderLabels([
            "ID", "Line Number", "Heat Number", "Component Type",
            "Specified Material", "Actual Measured Material", "PMI Technique", "Result", "Test Date"
        ])
        self._setup_table_style(self.pmi_tbl)
        self.pmi_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pmi_tbl.customContextMenuRequested.connect(
            lambda pos: self._table_context_menu(pos, self.pmi_tbl, "pmi")
        )
        l.addWidget(self.pmi_tbl)
        return w

    def refresh_pmi(self):
        if not self.project_id:
            return
        s = self._get_session()
        try:
            from services.precomm_service import PreCommService
            recs = PreCommService(s).pmi.get_all(self.project_id)
            self.pmi_tbl.setSortingEnabled(False)
            self.pmi_tbl.setRowCount(0)
            verified = 0

            for r in recs:
                row = self.pmi_tbl.rowCount()
                self.pmi_tbl.insertRow(row)
                self.pmi_tbl.setItem(row, 0, QTableWidgetItem(str(r.id)))
                self.pmi_tbl.setItem(row, 1, QTableWidgetItem(r.line_number or ""))
                self.pmi_tbl.setItem(row, 2, QTableWidgetItem(r.heat_number or ""))
                self.pmi_tbl.setItem(row, 3, QTableWidgetItem(r.component_type or ""))
                self.pmi_tbl.setItem(row, 4, QTableWidgetItem(r.specified_material or ""))
                self.pmi_tbl.setItem(row, 5, QTableWidgetItem(r.actual_material or ""))
                self.pmi_tbl.setItem(row, 6, QTableWidgetItem(r.pmi_method or "XRF Analyzer"))

                res_txt = r.result or "Accepted"
                res_item = QTableWidgetItem(res_txt)
                self._apply_badge(res_item, res_txt)
                self.pmi_tbl.setItem(row, 7, res_item)

                self.pmi_tbl.setItem(row, 8, QTableWidgetItem(str(r.test_date or "")))

                if res_txt in ("Accepted", "Passed"):
                    verified += 1

            self.pmi_tbl.setSortingEnabled(True)
            self.kpi_pmi.set_value(f"{verified}/{len(recs)}", highlight="green" if verified == len(recs) and len(recs) > 0 else None)
            s.commit()
        except Exception as e:
            s.rollback()
            logger.exception("Error in refresh_pmi")
        finally:
            s.close()

    def _filter_pmi(self):
        query = self.txt_search_pmi.text().strip().lower()
        res_f = self.cmb_filter_pmi.currentText()
        for r in range(self.pmi_tbl.rowCount()):
            heat = self.pmi_tbl.item(r, 2).text().lower()
            spec = self.pmi_tbl.item(r, 4).text().lower()
            act = self.pmi_tbl.item(r, 5).text().lower()
            res = self.pmi_tbl.item(r, 7).text()
            match_txt = query in heat or query in spec or query in act
            match_res = (res_f == "All Results") or (res_f in res)
            self.pmi_tbl.setRowHidden(r, not (match_txt and match_res))

    def _add_pmi(self):
        if not self.project_id:
            QMessageBox.warning(self, "Project", "Select a project first.")
            return
        dlg = PMIDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            s = self._get_session()
            try:
                from services.precomm_service import PreCommService
                PreCommService(s).record_pmi(self.project_id, **dlg.result_data)
                s.commit()
                self.refresh_pmi()
                QMessageBox.information(self, "Success", "PMI Spectroscopy result registered.")
            except Exception as e:
                s.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                s.close()

    # ══════════════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════════════

    def _build_dim_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_dim = QLineEdit()
        self.txt_search_dim.setPlaceholderText("🔍 Search Spool Number, ISO Drawing, Inspector...")
        self.txt_search_dim.textChanged.connect(self._filter_dim)
        tb.addWidget(self.txt_search_dim, 1)

        self.cmb_filter_dim = QComboBox()
        self.cmb_filter_dim.addItems(["All Results", "Accepted", "Rejected", "Pending"])
        self.cmb_filter_dim.currentIndexChanged.connect(self._filter_dim)
        tb.addWidget(self.cmb_filter_dim)

        btn_add = QPushButton("➕ Record Dimensional")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_dim)
        tb.addWidget(btn_add)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(lambda: self._export_to_csv(self.dim_tbl, "Spool_Dimensional_Report"))
        tb.addWidget(btn_exp)

        btn_ref = QPushButton("🔄 Refresh")
        btn_ref.setObjectName("secondaryBtn")
        btn_ref.clicked.connect(self.refresh_dim)
        tb.addWidget(btn_ref)
        l.addLayout(tb)

        self.dim_tbl = QTableWidget(0, 9)
        self.dim_tbl.setHorizontalHeaderLabels([
            "ID", "Spool Identifier", "ISO Drawing", "Design Length (mm)",
            "Tolerance (±mm)", "Actual Length (mm)", "QC Result", "Inspector", "Check Date"
        ])
        self._setup_table_style(self.dim_tbl)
        self.dim_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.dim_tbl.customContextMenuRequested.connect(
            lambda pos: self._table_context_menu(pos, self.dim_tbl, "dimensional")
        )
        l.addWidget(self.dim_tbl)
        return w

    def refresh_dim(self):
        if not self.project_id:
            return
        s = self._get_session()
        try:
            from services.precomm_service import PreCommService
            recs = PreCommService(s).dimensional.get_all(self.project_id)
            self.dim_tbl.setSortingEnabled(False)
            self.dim_tbl.setRowCount(0)

            for r in recs:
                row = self.dim_tbl.rowCount()
                self.dim_tbl.insertRow(row)
                self.dim_tbl.setItem(row, 0, QTableWidgetItem(str(r.id)))
                self.dim_tbl.setItem(row, 1, QTableWidgetItem(r.spool_number or ""))
                self.dim_tbl.setItem(row, 2, QTableWidgetItem(r.iso_number or ""))
                self.dim_tbl.setItem(row, 3, QTableWidgetItem(str(r.overall_length_mm or "")))
                self.dim_tbl.setItem(row, 4, QTableWidgetItem(f"±{r.tolerance_mm or 3.0}"))
                self.dim_tbl.setItem(row, 5, QTableWidgetItem(str(r.actual_length_mm or "")))

                res_txt = r.result or "Accepted"
                res_item = QTableWidgetItem(res_txt)
                self._apply_badge(res_item, res_txt)
                self.dim_tbl.setItem(row, 6, res_item)

                self.dim_tbl.setItem(row, 7, QTableWidgetItem(r.inspector or "QC Team"))
                self.dim_tbl.setItem(row, 8, QTableWidgetItem(str(r.check_date or "")))

            self.dim_tbl.setSortingEnabled(True)
            s.commit()
        except Exception as e:
            s.rollback()
            logger.exception("Error in refresh_dim")
        finally:
            s.close()

    def _filter_dim(self):
        query = self.txt_search_dim.text().strip().lower()
        res_f = self.cmb_filter_dim.currentText()
        for r in range(self.dim_tbl.rowCount()):
            spool = self.dim_tbl.item(r, 1).text().lower()
            iso = self.dim_tbl.item(r, 2).text().lower()
            res = self.dim_tbl.item(r, 6).text()
            match_txt = query in spool or query in iso
            match_res = (res_f == "All Results") or (res_f in res)
            self.dim_tbl.setRowHidden(r, not (match_txt and match_res))

    def _add_dim(self):
        if not self.project_id:
            QMessageBox.warning(self, "Project", "Select a project first.")
            return
        dlg = DimensionalDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            s = self._get_session()
            try:
                from services.precomm_service import PreCommService
                PreCommService(s).record_dimensional(self.project_id, **dlg.result_data)
                s.commit()
                self.refresh_dim()
                QMessageBox.information(self, "Success", "Dimensional verification logged.")
            except Exception as e:
                s.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                s.close()

    # ══════════════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════════════

    def _build_spring_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_spring = QLineEdit()
        self.txt_search_spring.setPlaceholderText("🔍 Search Support Tag, Line Number, Spring Type...")
        self.txt_search_spring.textChanged.connect(self._filter_spring)
        tb.addWidget(self.txt_search_spring, 1)

        self.cmb_filter_spring = QComboBox()
        self.cmb_filter_spring.addItems(["All Statuses", "In Service", "Pin Removed", "Pending Unlock"])
        self.cmb_filter_spring.currentIndexChanged.connect(self._filter_spring)
        tb.addWidget(self.cmb_filter_spring)

        btn_add = QPushButton("➕ Register Spring Hanger")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_spring)
        tb.addWidget(btn_add)

        btn_pin = QPushButton("🔓 Release Travel Pin")
        btn_pin.setObjectName("secondaryBtn")
        btn_pin.clicked.connect(self._release_spring_pin)
        tb.addWidget(btn_pin)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(lambda: self._export_to_csv(self.spring_tbl, "Spring_Hangers_Register"))
        tb.addWidget(btn_exp)

        btn_ref = QPushButton("🔄 Refresh")
        btn_ref.setObjectName("secondaryBtn")
        btn_ref.clicked.connect(self.refresh_spring)
        tb.addWidget(btn_ref)
        l.addLayout(tb)

        self.spring_tbl = QTableWidget(0, 10)
        self.spring_tbl.setHorizontalHeaderLabels([
            "ID", "Support Tag", "Line Number", "Spring Type", "Spring Size",
            "Design Load (kg)", "Cold Set OK", "Hot Set OK", "Travel Pin Removed", "Operating Status"
        ])
        self._setup_table_style(self.spring_tbl)
        self.spring_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.spring_tbl.customContextMenuRequested.connect(
            lambda pos: self._table_context_menu(pos, self.spring_tbl, "spring")
        )
        l.addWidget(self.spring_tbl)
        return w

    def refresh_spring(self):
        if not self.project_id:
            return
        s = self._get_session()
        try:
            from services.precomm_service import PreCommService
            recs = PreCommService(s).spring.get_all(self.project_id)
            self.spring_tbl.setSortingEnabled(False)
            self.spring_tbl.setRowCount(0)
            in_service = 0
            yn = lambda v: "✅ Yes" if v else "❌ No"

            for r in recs:
                row = self.spring_tbl.rowCount()
                self.spring_tbl.insertRow(row)
                self.spring_tbl.setItem(row, 0, QTableWidgetItem(str(r.id)))
                self.spring_tbl.setItem(row, 1, QTableWidgetItem(r.support_tag or ""))
                self.spring_tbl.setItem(row, 2, QTableWidgetItem(r.line_number or ""))
                self.spring_tbl.setItem(row, 3, QTableWidgetItem(r.spring_type or "Variable Spring"))
                self.spring_tbl.setItem(row, 4, QTableWidgetItem(r.spring_size or ""))
                self.spring_tbl.setItem(row, 5, QTableWidgetItem(str(r.design_load_kg or "")))
                self.spring_tbl.setItem(row, 6, QTableWidgetItem(yn(r.cold_set_verified)))
                self.spring_tbl.setItem(row, 7, QTableWidgetItem(yn(r.hot_set_verified)))
                self.spring_tbl.setItem(row, 8, QTableWidgetItem(yn(r.travel_pin_removed)))

                st_txt = r.status or ("In Service" if r.travel_pin_removed else "Pending Unlock")
                st_item = QTableWidgetItem(st_txt)
                self._apply_badge(st_item, st_txt)
                self.spring_tbl.setItem(row, 9, st_item)

                if r.travel_pin_removed:
                    in_service += 1

            self.spring_tbl.setSortingEnabled(True)
            self.kpi_spring.set_value(f"{in_service}/{len(recs)}", highlight="green" if in_service == len(recs) and len(recs) > 0 else None)
            s.commit()
        except Exception as e:
            s.rollback()
            logger.exception("Error in refresh_spring")
        finally:
            s.close()

    def _filter_spring(self):
        query = self.txt_search_spring.text().strip().lower()
        st_f = self.cmb_filter_spring.currentText()
        for r in range(self.spring_tbl.rowCount()):
            tag = self.spring_tbl.item(r, 1).text().lower()
            line = self.spring_tbl.item(r, 2).text().lower()
            st = self.spring_tbl.item(r, 9).text()
            match_txt = query in tag or query in line
            match_st = (st_f == "All Statuses") or (st_f in st)
            self.spring_tbl.setRowHidden(r, not (match_txt and match_st))

    def _add_spring(self):
        if not self.project_id:
            QMessageBox.warning(self, "Project", "Select a project first.")
            return
        dlg = SpringHangerDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            s = self._get_session()
            try:
                from services.precomm_service import PreCommService
                PreCommService(s).record_spring_hanger(self.project_id, **dlg.result_data)
                s.commit()
                self.refresh_spring()
                QMessageBox.information(self, "Success", "Spring Hanger registered.")
            except Exception as e:
                s.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                s.close()

    def _release_spring_pin(self):
        row = self.spring_tbl.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection", "Select a spring hanger from the table.")
            return
        sp_id = int(self.spring_tbl.item(row, 0).text())
        s = self._get_session()
        try:
            from db.models import SpringHangerRecord
            rec = s.query(SpringHangerRecord).get(sp_id)
            if rec:
                rec.travel_pin_removed = True
                rec.status = "In Service"
                s.commit()
                self.refresh_spring()
                QMessageBox.information(self, "Unlocked", f"Travel Pin removed for {rec.support_tag}. Hanger is now In-Service.")
        except Exception as e:
            s.rollback()
            QMessageBox.critical(self, "Error", str(e))
        finally:
            s.close()

    # ══════════════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════════════

    def _build_preservation_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 10, 8, 8)
        l.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_pres = QLineEdit()
        self.txt_search_pres.setPlaceholderText("🔍 Search Heat / Asset No, Storage Location, Preservation Method...")
        self.txt_search_pres.textChanged.connect(self._filter_pres)
        tb.addWidget(self.txt_search_pres, 1)

        self.cmb_filter_pres = QComboBox()
        self.cmb_filter_pres.addItems(["All Conditions", "Good", "Needs Inspection", "Expired"])
        self.cmb_filter_pres.currentIndexChanged.connect(self._filter_pres)
        tb.addWidget(self.cmb_filter_pres)

        btn_add = QPushButton("➕ Record Preservation")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_pres)
        tb.addWidget(btn_add)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(lambda: self._export_to_csv(self.pres_tbl, "Preservation_Log"))
        tb.addWidget(btn_exp)

        btn_ref = QPushButton("🔄 Refresh")
        btn_ref.setObjectName("secondaryBtn")
        btn_ref.clicked.connect(self.refresh_pres)
        tb.addWidget(btn_ref)
        l.addLayout(tb)

        self.pres_tbl = QTableWidget(0, 8)
        self.pres_tbl.setHorizontalHeaderLabels([
            "ID", "Heat / Tag No", "Material / Equipment Type", "Storage Location",
            "Preservation Technique", "Visual Condition", "Next Due Date", "Log Date"
        ])
        self._setup_table_style(self.pres_tbl)
        self.pres_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pres_tbl.customContextMenuRequested.connect(
            lambda pos: self._table_context_menu(pos, self.pres_tbl, "preservation")
        )
        l.addWidget(self.pres_tbl)
        return w

    def refresh_pres(self):
        if not self.project_id:
            return
        s = self._get_session()
        try:
            from services.precomm_service import PreCommService
            recs = PreCommService(s).preservation.get_all(self.project_id)
            self.pres_tbl.setSortingEnabled(False)
            self.pres_tbl.setRowCount(0)

            for r in recs:
                row = self.pres_tbl.rowCount()
                self.pres_tbl.insertRow(row)
                self.pres_tbl.setItem(row, 0, QTableWidgetItem(str(r.id)))
                self.pres_tbl.setItem(row, 1, QTableWidgetItem(r.heat_number or ""))
                self.pres_tbl.setItem(row, 2, QTableWidgetItem(r.material_type or ""))
                self.pres_tbl.setItem(row, 3, QTableWidgetItem(r.storage_location or "Laydown Area"))
                self.pres_tbl.setItem(row, 4, QTableWidgetItem(r.preservation_method or "End Cap + VCI"))

                cond_txt = r.condition or "Good"
                cond_item = QTableWidgetItem(cond_txt)
                self._apply_badge(cond_item, cond_txt)
                self.pres_tbl.setItem(row, 5, cond_item)

                self.pres_tbl.setItem(row, 6, QTableWidgetItem(str(r.next_inspection_date or "")))
                self.pres_tbl.setItem(row, 7, QTableWidgetItem(str(r.preservation_date or "")))

            self.pres_tbl.setSortingEnabled(True)
            s.commit()
        except Exception as e:
            s.rollback()
            logger.exception("Error in refresh_pres")
        finally:
            s.close()

    def _filter_pres(self):
        query = self.txt_search_pres.text().strip().lower()
        cond_f = self.cmb_filter_pres.currentText()
        for r in range(self.pres_tbl.rowCount()):
            heat = self.pres_tbl.item(r, 1).text().lower()
            loc = self.pres_tbl.item(r, 3).text().lower()
            cond = self.pres_tbl.item(r, 5).text()
            match_txt = query in heat or query in loc
            match_cond = (cond_f == "All Conditions") or (cond_f in cond)
            self.pres_tbl.setRowHidden(r, not (match_txt and match_cond))

    def _add_pres(self):
        if not self.project_id:
            QMessageBox.warning(self, "Project", "Select a project first.")
            return
        dlg = PreservationDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            s = self._get_session()
            try:
                from services.precomm_service import PreCommService
                PreCommService(s).record_preservation(self.project_id, **dlg.result_data)
                s.commit()
                self.refresh_pres()
                QMessageBox.information(self, "Success", "Preservation routine logged.")
            except Exception as e:
                s.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                s.close()

    # ══════════════════════════════════════════════════════
    #  General Refresh & Context Menu Helpers
    # ══════════════════════════════════════════════════════

    def refresh(self):
        self.refresh_flushing()
        self.refresh_leak()
        self.refresh_boxup()
        self.refresh_pmi()
        self.refresh_dim()
        self.refresh_spring()
        self.refresh_pres()

    def _table_context_menu(self, pos, table: QTableWidget, module_name: str):
        row = table.rowAt(pos.y())
        if row < 0:
            return

        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: white; border: 1px solid #cbd5e1; } QMenu::item { padding: 6px 18px; }")

        act_copy = QAction("📋 Copy Selected Row", self)
        act_copy.triggered.connect(lambda: self._copy_row_text(table, row))
        menu.addAction(act_copy)

        act_del = QAction("🗑️ Delete Record", self)
        act_del.triggered.connect(lambda: self._delete_record(table, row, module_name))
        menu.addAction(act_del)

        menu.exec(table.viewport().mapToGlobal(pos))

    def _copy_row_text(self, table: QTableWidget, row: int):
        data = [table.item(row, c).text() for c in range(table.columnCount()) if table.item(row, c)]
        QApplication.clipboard().setText(" | ".join(data))

    def _delete_record(self, table: QTableWidget, row: int, module: str):
        rec_id = int(table.item(row, 0).text())
        if QMessageBox.question(self, "Confirm Delete", f"Permanently delete {module.title()} entry ID {rec_id}?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return

        s = self._get_session()
        try:
            from db.models import (
                FlushingRecord, SensitiveLeakTest, BoxUpRecord,
                PMIRecord, DimensionalCheck, SpringHangerRecord, PreservationRecord
            )
            model_map = {
                "flushing": FlushingRecord, "leak": SensitiveLeakTest,
                "boxup": BoxUpRecord, "pmi": PMIRecord,
                "dimensional": DimensionalCheck, "spring": SpringHangerRecord,
                "preservation": PreservationRecord
            }
            target_model = model_map.get(module)
            if target_model:
                rec = s.query(target_model).get(rec_id)
                if rec:
                    s.delete(rec)
                    s.commit()
                    self.refresh()
                    QMessageBox.information(self, "Deleted", "Record removed successfully.")
        except Exception as e:
            s.rollback()
            logger.exception("Failed to delete precomm record")
            QMessageBox.critical(self, "Error", f"Failed to delete record:\n{e}")
        finally:
            s.close()

    def _export_to_csv(self, table: QTableWidget, filename_prefix: str):
        if table.rowCount() == 0:
            QMessageBox.warning(self, "Export", "Table is empty. Nothing to export.")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename, _ = QFileDialog.getSaveFileName(self, "Export CSV", f"{filename_prefix}_{timestamp}.csv", "CSV Files (*.csv)")
        if not filename:
            return

        try:
            with open(filename, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
                writer.writerow(headers)

                for r in range(table.rowCount()):
                    if not table.isRowHidden(r):
                        row_vals = [table.item(r, c).text().strip() if table.item(r, c) else "" for c in range(table.columnCount())]
                        writer.writerow(row_vals)

            QMessageBox.information(self, "Export Complete", f"Data exported successfully to:\n{filename}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV file:\n{e}")


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class FlushingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Register Pipe Flushing & Cleaning")
        self.setMinimumWidth(460)
        self.setStyleSheet(PRECOMM_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.txt_line = QLineEdit()
        self.cmb_method = QComboBox()
        self.cmb_method.addItems(["Water Hydro-Flush", "High Pressure Air Blow", "Steam Blow", "Chemical Degreasing & Pickling", "Oil Lube Flushing"])
        self.txt_medium = QLineEdit("Demineralized Water")
        self.spn_vel = QDoubleSpinBox(); self.spn_vel.setRange(0, 100); self.spn_vel.setValue(3.5); self.spn_vel.setSuffix(" m/s")
        self.spn_dur = QDoubleSpinBox(); self.spn_dur.setRange(0, 200); self.spn_dur.setValue(2.0); self.spn_dur.setSuffix(" Hrs")
        self.cmb_res = QComboBox(); self.cmb_res.addItems(["Accepted", "Pending Target Check", "Rejected"])
        self.txt_cert = QLineEdit()
        self.txt_cert.setPlaceholderText("e.g. CERT-FLUSH-2024-001")

        form.addRow("Line Number *:", self.txt_line)
        form.addRow("Flushing Method *:", self.cmb_method)
        form.addRow("Cleaning Medium:", self.txt_medium)
        form.addRow("Flow Velocity:", self.spn_vel)
        form.addRow("Flushing Duration:", self.spn_dur)
        form.addRow("Target Plate QC Result:", self.cmb_res)
        form.addRow("Quality Certificate No:", self.txt_cert)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Record")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(btn_save); btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _save(self):
        if not self.txt_line.text().strip():
            QMessageBox.warning(self, "Validation", "Piping line number is required.")
            return
        self.result_data = {
            "line_number": self.txt_line.text().strip(),
            "flush_method": self.cmb_method.currentText(),
            "flush_medium": self.txt_medium.text().strip(),
            "flow_velocity_mps": self.spn_vel.value(),
            "duration_hours": self.spn_dur.value(),
            "result": self.cmb_res.currentText(),
            "certificate_no": self.txt_cert.text().strip(),
            "start_date": datetime.date.today()
        }
        self.accept()


class LeakTestDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Register Sensitive Leak Test")
        self.setMinimumWidth(460)
        self.setStyleSheet(PRECOMM_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.txt_line = QLineEdit()
        self.cmb_method = QComboBox()
        self.cmb_method.addItems(["Sensitive Soap Bubble Test", "Helium Mass Spectrometer Sniffing", "Nitrogen Pressure Hold / Decay", "Ultrasonic Acoustic Detection"])
        self.cmb_medium = QComboBox()
        self.cmb_medium.addItems(["Nitrogen (N2) + 1% Helium Tracer", "Pure Nitrogen (N2)", "Dry Plant Air", "Inert Gas"])
        self.spn_p = QDoubleSpinBox(); self.spn_p.setRange(0, 500); self.spn_p.setValue(5.0); self.spn_p.setSuffix(" bar")
        self.spn_dur = QSpinBox(); self.spn_dur.setRange(1, 1440); self.spn_dur.setValue(30); self.spn_dur.setSuffix(" min")
        self.spn_j = QSpinBox(); self.spn_j.setRange(1, 5000); self.spn_j.setValue(12)
        self.spn_l = QSpinBox(); self.spn_l.setRange(0, 100); self.spn_l.setValue(0)

        form.addRow("Line / System Number *:", self.txt_line)
        form.addRow("Testing Technique:", self.cmb_method)
        form.addRow("Test Medium:", self.cmb_medium)
        form.addRow("Test Pressure:", self.spn_p)
        form.addRow("Hold Duration:", self.spn_dur)
        form.addRow("Total Flange Joints Checked:", self.spn_j)
        form.addRow("Leaks Detected:", self.spn_l)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Test Result")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(btn_save); btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _save(self):
        if not self.txt_line.text().strip():
            QMessageBox.warning(self, "Validation", "Line number is mandatory.")
            return
        self.result_data = {
            "line_number": self.txt_line.text().strip(),
            "leak_test_method": self.cmb_method.currentText(),
            "test_medium": self.cmb_medium.currentText(),
            "test_pressure_bar": self.spn_p.value(),
            "test_duration_min": self.spn_dur.value(),
            "joints_tested": self.spn_j.value(),
            "leaks_found": self.spn_l.value(),
            "result": "Passed" if self.spn_l.value() == 0 else "Leak Found",
            "test_date": datetime.date.today()
        }
        self.accept()


class BoxUpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Register Equipment / Flange Box-Up")
        self.setMinimumWidth(460)
        self.setStyleSheet(PRECOMM_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.txt_line = QLineEdit()
        self.txt_eq = QLineEdit()
        self.txt_eq.setPlaceholderText("e.g. Vessel V-101 / Pump Suction")

        self.chk_internals = QCheckBox("Internal Visual Inspection Cleared")
        self.chk_internals.setChecked(True)
        self.chk_clean = QCheckBox("Cleanliness & Debris Verification Approved")
        self.chk_clean.setChecked(True)
        self.chk_fod = QCheckBox("Foreign Material Free (FOD Inspection Verified)")
        self.chk_fod.setChecked(True)
        self.chk_gasket = QCheckBox("Permanent Specified Gasket Installed & Tagged")
        self.chk_gasket.setChecked(True)
        self.chk_torque = QCheckBox("Bolt Torquing & Criss-Cross Tightening Verified")
        self.chk_torque.setChecked(True)

        form.addRow("Line Number:", self.txt_line)
        form.addRow("Equipment / Nozzle Tag *:", self.txt_eq)
        form.addRow("Quality Check 1:", self.chk_internals)
        form.addRow("Quality Check 2:", self.chk_clean)
        form.addRow("Quality Check 3:", self.chk_fod)
        form.addRow("Quality Check 4:", self.chk_gasket)
        form.addRow("Quality Check 5:", self.chk_torque)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Protocol")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(btn_save); btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _save(self):
        if not self.txt_eq.text().strip():
            QMessageBox.warning(self, "Validation", "Equipment Tag is mandatory.")
            return
        all_ok = (self.chk_internals.isChecked() and self.chk_clean.isChecked() and
                  self.chk_fod.isChecked() and self.chk_gasket.isChecked() and self.chk_torque.isChecked())
        self.result_data = {
            "line_number": self.txt_line.text().strip(),
            "equipment_tag": self.txt_eq.text().strip(),
            "internal_inspection_done": self.chk_internals.isChecked(),
            "cleanliness_verified": self.chk_clean.isChecked(),
            "foreign_material_free": self.chk_fod.isChecked(),
            "gasket_installed": self.chk_gasket.isChecked(),
            "bolt_torque_verified": self.chk_torque.isChecked(),
            "status": "Completed" if all_ok else "Open",
            "boxup_date": datetime.date.today()
        }
        self.accept()


class PMIDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Register Positive Material Identification (PMI)")
        self.setMinimumWidth(460)
        self.setStyleSheet(PRECOMM_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.txt_line = QLineEdit()
        self.txt_heat = QLineEdit()
        self.txt_comp = QComboBox(); self.txt_comp.addItems(["Pipe Spool", "Fitting / Elbow", "Flange", "Weld Metal", "Valve Body", "Instrument Nozzle"])
        self.txt_spec = QLineEdit("ASTM A312 TP316L")
        self.txt_act = QLineEdit("SS 316L (Cr:17.2%, Ni:12.1%, Mo:2.2%)")
        self.cmb_meth = QComboBox(); self.cmb_meth.addItems(["X-Ray Fluorescence (XRF)", "Optical Emission Spectrometry (OES)"])
        self.cmb_res = QComboBox(); self.cmb_res.addItems(["Accepted", "Rejected", "Pending Lab Verification"])

        form.addRow("Piping Line No:", self.txt_line)
        form.addRow("Material Heat Number *:", self.txt_heat)
        form.addRow("Component Type:", self.txt_comp)
        form.addRow("Specified Metallurgy *:", self.txt_spec)
        form.addRow("Actual Analyzed Chemistry:", self.txt_act)
        form.addRow("Spectroscopy Method:", self.cmb_meth)
        form.addRow("Acceptance Result:", self.cmb_res)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_save = QPushButton("Save PMI Log")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(btn_save); btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _save(self):
        if not self.txt_heat.text().strip():
            QMessageBox.warning(self, "Validation", "Heat number is mandatory.")
            return
        self.result_data = {
            "line_number": self.txt_line.text().strip(),
            "heat_number": self.txt_heat.text().strip(),
            "component_type": self.txt_comp.currentText(),
            "specified_material": self.txt_spec.text().strip(),
            "actual_material": self.txt_act.text().strip(),
            "pmi_method": self.cmb_meth.currentText(),
            "result": self.cmb_res.currentText(),
            "test_date": datetime.date.today()
        }
        self.accept()


class DimensionalDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Register Spool Dimensional Verification")
        self.setMinimumWidth(460)
        self.setStyleSheet(PRECOMM_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.txt_spool = QLineEdit()
        self.txt_iso = QLineEdit()
        self.spn_des = QDoubleSpinBox(); self.spn_des.setRange(0, 100000); self.spn_des.setValue(4500.0); self.spn_des.setSuffix(" mm")
        self.spn_tol = QDoubleSpinBox(); self.spn_tol.setRange(0, 50); self.spn_tol.setValue(3.0); self.spn_tol.setPrefix("± "); self.spn_tol.setSuffix(" mm")
        self.spn_act = QDoubleSpinBox(); self.spn_act.setRange(0, 100000); self.spn_act.setValue(4501.5); self.spn_act.setSuffix(" mm")
        self.txt_insp = QLineEdit("QC Inspector")

        form.addRow("Spool Identifier *:", self.txt_spool)
        form.addRow("ISO Drawing Reference:", self.txt_iso)
        form.addRow("Design Length / Offset:", self.spn_des)
        form.addRow("Allowable Tolerance:", self.spn_tol)
        form.addRow("Actual Measured Dimension:", self.spn_act)
        form.addRow("Certified Inspector:", self.txt_insp)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Dimensions")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(btn_save); btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _save(self):
        if not self.txt_spool.text().strip():
            QMessageBox.warning(self, "Validation", "Spool Identifier is mandatory.")
            return
        diff = abs(self.spn_act.value() - self.spn_des.value())
        is_ok = diff <= self.spn_tol.value()
        self.result_data = {
            "spool_number": self.txt_spool.text().strip(),
            "iso_number": self.txt_iso.text().strip(),
            "overall_length_mm": self.spn_des.value(),
            "tolerance_mm": self.spn_tol.value(),
            "actual_length_mm": self.spn_act.value(),
            "result": "Accepted" if is_ok else "Rejected",
            "inspector": self.txt_insp.text().strip(),
            "check_date": datetime.date.today()
        }
        self.accept()


class SpringHangerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Register Spring Hanger / Support")
        self.setMinimumWidth(460)
        self.setStyleSheet(PRECOMM_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.txt_tag = QLineEdit()
        self.txt_line = QLineEdit()
        self.cmb_type = QComboBox(); self.cmb_type.addItems(["Variable Effort Spring", "Constant Effort Spring", "Rigid Strut", "Snubber / Shock Absorber"])
        self.txt_size = QLineEdit("Size 12 Type B")
        self.spn_load = QDoubleSpinBox(); self.spn_load.setRange(0, 100000); self.spn_load.setValue(1250.0); self.spn_load.setSuffix(" kg")
        self.chk_cold = QCheckBox("Cold Set Load Position Verified")
        self.chk_cold.setChecked(True)
        self.chk_hot = QCheckBox("Hot Preset Position Verified")
        self.chk_hot.setChecked(True)
        self.chk_pin = QCheckBox("Travel Stop Pin Removed (Hanger In-Service)")

        form.addRow("Support / Hanger Tag *:", self.txt_tag)
        form.addRow("Piping Line Number:", self.txt_line)
        form.addRow("Hanger Design Type:", self.cmb_type)
        form.addRow("Spring Size / Series:", self.txt_size)
        form.addRow("Design Operating Load:", self.spn_load)
        form.addRow("Pre-commissioning 1:", self.chk_cold)
        form.addRow("Pre-commissioning 2:", self.chk_hot)
        form.addRow("Final Commissioning:", self.chk_pin)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Spring Log")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(btn_save); btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _save(self):
        if not self.txt_tag.text().strip():
            QMessageBox.warning(self, "Validation", "Support Tag is mandatory.")
            return
        self.result_data = {
            "support_tag": self.txt_tag.text().strip(),
            "line_number": self.txt_line.text().strip(),
            "spring_type": self.cmb_type.currentText(),
            "spring_size": self.txt_size.text().strip(),
            "design_load_kg": self.spn_load.value(),
            "cold_set_verified": self.chk_cold.isChecked(),
            "hot_set_verified": self.chk_hot.isChecked(),
            "travel_pin_removed": self.chk_pin.isChecked(),
            "status": "In Service" if self.chk_pin.isChecked() else "Pending Unlock"
        }
        self.accept()


class PreservationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Register Piping & Equipment Preservation")
        self.setMinimumWidth(460)
        self.setStyleSheet(PRECOMM_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.txt_heat = QLineEdit()
        self.txt_heat.setPlaceholderText("Heat Number, Valve Tag or Line No")
        self.txt_mat = QLineEdit("Duplex Stainless Steel / Valve Trim")
        self.txt_loc = QLineEdit("Yard Laydown Area B")
        self.cmb_meth = QComboBox(); self.cmb_meth.addItems(["Nitrogen (N2) Positive Purge (0.2 bar)", "Vapor Corrosion Inhibitor (VCI) Bags", "End Cap Sealed + Desiccant", "Anti-Rust Oil Coating", "Flange Grease Tape"])
        self.cmb_cond = QComboBox(); self.cmb_cond.addItems(["Good", "Needs Inspection", "Regreasing Required", "Expired Barrier"])
        self.dt_due = QDateEdit(); self.dt_due.setCalendarPopup(True); self.dt_due.setDate(QDate.currentDate().addDays(90))

        form.addRow("Asset / Tag / Heat No *:", self.txt_heat)
        form.addRow("Material / Asset Description:", self.txt_mat)
        form.addRow("Storage Location:", self.txt_loc)
        form.addRow("Preservation Method:", self.cmb_meth)
        form.addRow("Current Condition:", self.cmb_cond)
        form.addRow("Next Inspection Due Date:", self.dt_due)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Preservation Log")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(); btns.addWidget(btn_save); btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _save(self):
        if not self.txt_heat.text().strip():
            QMessageBox.warning(self, "Validation", "Asset/Heat Identifier is mandatory.")
            return
        qd = self.dt_due.date()
        self.result_data = {
            "heat_number": self.txt_heat.text().strip(),
            "material_type": self.txt_mat.text().strip(),
            "storage_location": self.txt_loc.text().strip(),
            "preservation_method": self.cmb_meth.currentText(),
            "condition": self.cmb_cond.currentText(),
            "next_inspection_date": datetime.date(qd.year(), qd.month(), qd.day()),
            "preservation_date": datetime.date.today()
        }
        self.accept()