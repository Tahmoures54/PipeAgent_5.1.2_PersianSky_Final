# -*- coding: utf-8 -*-
# ui/tabs/finishing_tab.py – PipeAgent 5.0
# Comprehensive Finishing Control: Painting, Insulation, Flange Torque, PWHT & Reinstatement

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
    QDateEdit, QDialog, QTextEdit, QFrame, QFileDialog,
    QApplication, QMenu, QAbstractItemView, QSpinBox
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor, QFont, QBrush, QCursor, QAction

# Implementation note.
try:
    from core.constants import (
        SURFACE_PREP_GRADES, INSULATION_TYPES, INSULATION_MATERIALS,
        TORQUE_METHODS, PWHT_METHODS, PWHT_RESULTS,
    )
except ImportError:
    SURFACE_PREP_GRADES = ["St 2", "St 3", "Sa 1", "Sa 2", "Sa 2.5", "Sa 3"]
    INSULATION_TYPES = ["Hot", "Cold", "Acoustic", "Personnel Protection", "None"]
    INSULATION_MATERIALS = ["Mineral Wool", "Cellular Glass", "PUF/PIR", "Aerogel", "Calcium Silicate"]
    TORQUE_METHODS = ["Manual Torque Wrench", "Hydraulic Torque Wrench", "Pneumatic Tensioner", "Direct Tension Indicator"]
    PWHT_METHODS = ["Electrical Resistance", "Induction Heating", "Gas Fired Furnace", "Local Flame"]
    PWHT_RESULTS = ["Accepted", "Rejected", "Pending", "Concession"]

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

STATUS_BADGES = {
    "Accepted":   {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Completed":  {"bg": "#dcfce7", "fg": "#166534", "icon": "🟢"},
    "Pass":       {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Rejected":   {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Fail":       {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Pending":    {"bg": "#fef3c7", "fg": "#92400e", "icon": "⏳"},
    "In Progress":{"bg": "#e0f2fe", "fg": "#075985", "icon": "🔄"},
    "Verified":   {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "🛡️"},
    "Concession": {"bg": "#ffedd5", "fg": "#9a3412", "icon": "⚠️"},
}
DEFAULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}

# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

FINISHING_STYLESHEET = """
    QWidget#finishingTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a3a50, stop:1 #275270);
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
        font-size: 18px;
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
        padding: 9px 18px;
        border: 1px solid #cbd5e1;
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        font-weight: 700;
        font-size: 12px;
        margin-right: 2px;
    }
    QTabBar::tab:selected {
        background: white;
        color: #1a3a50;
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
        color: white; border: none; padding: 7px 14px; border-radius: 6px; font-weight: 700;
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
    QLineEdit, QComboBox {
        padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 12px;
    }
"""

# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class MetricCard(QFrame):
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

    def set_value(self, text: str):
        self.val_lbl.setText(str(text))


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class FinishingTab(QWidget):
    def __init__(self, db, session_manager):
        super().__init__()
        self.setObjectName("finishingTab")
        self.db = db
        self.session_manager = session_manager
        self._current_project_id: Optional[int] = None

        self._build_ui()
        self.setStyleSheet(FINISHING_STYLESHEET)
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
        t = QLabel("🎨 Finishing & Pre-Commissioning Control")
        t.setObjectName("mainTitle")
        s = QLabel("Painting, Insulation, Flange Joint Tightening, PWHT Records, and Line Reinstatement Verification.")
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

        btn_global_ref = QPushButton("🔄 Refresh All")
        btn_global_ref.setObjectName("secondaryBtn")
        btn_global_ref.clicked.connect(self.refresh)
        proj_box.addWidget(btn_global_ref)
        hdr_lay.addLayout(proj_box)

        root.addWidget(header_card)

        # Implementation note.
        kpi_lay = QHBoxLayout()
        kpi_lay.setSpacing(8)
        self.kpi_paint = MetricCard("Painting Passed", "🖌️", "#10b981")
        self.kpi_insul = MetricCard("Insulated Spools", "🧊", "#0ea5e9")
        self.kpi_flange = MetricCard("Flanges Torqued", "🔩", "#f59e0b")
        self.kpi_pwht = MetricCard("PWHT Done", "🔥", "#8b5cf6")
        self.kpi_reinst = MetricCard("Reinstated Lines", "🔄", "#059669")

        for k in [self.kpi_paint, self.kpi_insul, self.kpi_flange, self.kpi_pwht, self.kpi_reinst]:
            kpi_lay.addWidget(k)
        root.addLayout(kpi_lay)

        # Implementation note.
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_painting_widget(), "🖌️ Painting Records")
        self.tabs.addTab(self._build_insulation_widget(), "🧊 Insulation Records")
        self.tabs.addTab(self._build_flange_widget(), "🔩 Flange Joint Management")
        self.tabs.addTab(self._build_pwht_widget(), "🔥 PWHT Quality Logs")
        self.tabs.addTab(self._build_reinst_widget(), "🔄 Reinstatement Punchlists")
        root.addWidget(self.tabs, 1)

    def _load_projects(self):
        self.cmb_project.blockSignals(True)
        self.cmb_project.clear()
        try:
            from db.models import Project
            session = self._get_session()
            projects = session.query(Project).order_by(Project.project_code).all()
            for p in projects:
                self.cmb_project.addItem(f"{p.project_code} – {p.title}", p.id)
            session.close()
        except Exception as e:
            logger.exception("Failed to load projects in FinishingTab")
            
        self.cmb_project.blockSignals(False)
        if self.cmb_project.count() > 0:
            self._on_project_changed()

    def _on_project_changed(self):
        self._current_project_id = self.cmb_project.currentData()
        self.refresh()

    def _setup_table_style(self, table: QTableWidget):
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _apply_badge(self, item: QTableWidgetItem, text: str):
        badge = STATUS_BADGES.get(text, DEFAULT_BADGE)
        item.setText(f"{badge['icon']} {text}")
        item.setBackground(QBrush(QColor(badge["bg"])))
        item.setForeground(QBrush(QColor(badge["fg"])))
        f = item.font()
        f.setBold(True)
        item.setFont(f)

    # ══════════════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════════════

    def _build_painting_widget(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 8)
        lay.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_paint = QLineEdit()
        self.txt_search_paint.setPlaceholderText("🔍 Search Line, Spool, Paint Code...")
        self.txt_search_paint.textChanged.connect(self._filter_painting)
        tb.addWidget(self.txt_search_paint, 1)

        self.cmb_filter_paint = QComboBox()
        self.cmb_filter_paint.addItems(["All Results", "Accepted", "Pending", "Rejected"])
        self.cmb_filter_paint.currentIndexChanged.connect(self._filter_painting)
        tb.addWidget(self.cmb_filter_paint)

        btn_add = QPushButton("➕ Record Painting")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_painting)
        tb.addWidget(btn_add)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(lambda: self._export_to_csv(self.paint_table, "Painting_Report"))
        tb.addWidget(btn_exp)

        btn_ref = QPushButton("🔄 Refresh")
        btn_ref.setObjectName("secondaryBtn")
        btn_ref.clicked.connect(self.refresh_painting)
        tb.addWidget(btn_ref)
        lay.addLayout(tb)

        self.paint_table = QTableWidget(0, 9)
        self.paint_table.setHorizontalHeaderLabels([
            "ID", "Line No", "Spool Identifier", "Paint System Code",
            "Surface Prep", "Primer (μm)", "Finish (μm)", "Total DFT (μm)", "Inspection Result"
        ])
        self._setup_table_style(self.paint_table)
        self.paint_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.paint_table.customContextMenuRequested.connect(
            lambda pos: self._table_context_menu(pos, self.paint_table, self._edit_painting, self._delete_painting)
        )
        lay.addWidget(self.paint_table)
        return w

    def refresh_painting(self):
        if not self._current_project_id:
            return
        session = self._get_session()
        try:
            from services.finishing_service import FinishingService
            svc = FinishingService(session)
            records = svc.painting_repo.get_all(self._current_project_id)
            
            self.paint_table.setSortingEnabled(False)
            self.paint_table.setRowCount(0)
            passed_cnt = 0

            for r in records:
                row = self.paint_table.rowCount()
                self.paint_table.insertRow(row)
                self.paint_table.setItem(row, 0, QTableWidgetItem(str(r.id)))
                self.paint_table.setItem(row, 1, QTableWidgetItem(r.line_number or ""))
                self.paint_table.setItem(row, 2, QTableWidgetItem(r.spool_number or ""))
                self.paint_table.setItem(row, 3, QTableWidgetItem(r.painting_code or ""))
                self.paint_table.setItem(row, 4, QTableWidgetItem(r.surface_prep_grade or ""))
                self.paint_table.setItem(row, 5, QTableWidgetItem(str(r.primer_dft_micron or 0.0)))
                self.paint_table.setItem(row, 6, QTableWidgetItem(str(r.finish_dft_micron or 0.0)))
                self.paint_table.setItem(row, 7, QTableWidgetItem(str(r.total_dft_micron or 0.0)))
                
                res_txt = r.result or "Pending"
                res_item = QTableWidgetItem(res_txt)
                self._apply_badge(res_item, res_txt)
                self.paint_table.setItem(row, 8, res_item)

                if res_txt == "Accepted":
                    passed_cnt += 1

            self.paint_table.setSortingEnabled(True)
            self.kpi_paint.set_value(f"{passed_cnt}/{len(records)}")
            session.commit()
        except Exception as e:
            session.rollback()
            logger.exception("Error in refresh_painting")
        finally:
            session.close()

    def _filter_painting(self):
        query = self.txt_search_paint.text().strip().lower()
        filter_val = self.cmb_filter_paint.currentText()
        for r in range(self.paint_table.rowCount()):
            line = self.paint_table.item(r, 1).text().lower()
            spool = self.paint_table.item(r, 2).text().lower()
            code = self.paint_table.item(r, 3).text().lower()
            res = self.paint_table.item(r, 8).text()

            match_txt = query in line or query in spool or query in code
            match_res = (filter_val == "All Results") or (filter_val in res)
            self.paint_table.setRowHidden(r, not (match_txt and match_res))

    def _add_painting(self):
        if not self._current_project_id:
            QMessageBox.warning(self, "Project", "Select a project first.")
            return
        dlg = _PaintingDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            session = self._get_session()
            try:
                from services.finishing_service import FinishingService
                svc = FinishingService(session)
                svc.record_painting(self._current_project_id, **dlg.result_data)
                session.commit()
                self.refresh_painting()
                QMessageBox.information(self, "Success", "Painting record added successfully.")
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    def _edit_painting(self, row: int):
        rec_id = int(self.paint_table.item(row, 0).text())
        existing = {
            "line_number": self.paint_table.item(row, 1).text(),
            "spool_number": self.paint_table.item(row, 2).text(),
            "painting_code": self.paint_table.item(row, 3).text(),
            "surface_prep_grade": self.paint_table.item(row, 4).text(),
            "primer_dft_micron": float(self.paint_table.item(row, 5).text() or 0),
            "finish_dft_micron": float(self.paint_table.item(row, 6).text() or 0),
            "total_dft_micron": float(self.paint_table.item(row, 7).text() or 0),
            "result": self.paint_table.item(row, 8).text().split()[-1],
        }
        dlg = _PaintingDialog(self, existing_data=existing)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            session = self._get_session()
            try:
                from db.models import PaintingRecord
                rec = session.query(PaintingRecord).get(rec_id)
                if rec:
                    for k, v in dlg.result_data.items():
                        setattr(rec, k, v)
                    session.commit()
                    self.refresh_painting()
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    def _delete_painting(self, row: int):
        rec_id = int(self.paint_table.item(row, 0).text())
        if QMessageBox.question(self, "Confirm Delete", f"Delete painting record ID {rec_id}?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            session = self._get_session()
            try:
                from db.models import PaintingRecord
                rec = session.query(PaintingRecord).get(rec_id)
                if rec:
                    session.delete(rec)
                    session.commit()
                    self.refresh_painting()
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    # ══════════════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════════════

    def _build_insulation_widget(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 8)
        lay.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_insul = QLineEdit()
        self.txt_search_insul.setPlaceholderText("🔍 Search Line, Spool, Material...")
        self.txt_search_insul.textChanged.connect(self._filter_insulation)
        tb.addWidget(self.txt_search_insul, 1)

        self.cmb_filter_insul = QComboBox()
        self.cmb_filter_insul.addItems(["All Statuses", "Completed", "Pending", "In Progress"])
        self.cmb_filter_insul.currentIndexChanged.connect(self._filter_insulation)
        tb.addWidget(self.cmb_filter_insul)

        btn_add = QPushButton("➕ Record Insulation")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_insulation)
        tb.addWidget(btn_add)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(lambda: self._export_to_csv(self.insul_table, "Insulation_Report"))
        tb.addWidget(btn_exp)

        btn_ref = QPushButton("🔄 Refresh")
        btn_ref.setObjectName("secondaryBtn")
        btn_ref.clicked.connect(self.refresh_insulation)
        tb.addWidget(btn_ref)
        lay.addLayout(tb)

        self.insul_table = QTableWidget(0, 8)
        self.insul_table.setHorizontalHeaderLabels([
            "ID", "Line No", "Spool No", "Insulation Class",
            "Core Material", "Thickness (mm)", "Cladding Specification", "Work Status"
        ])
        self._setup_table_style(self.insul_table)
        self.insul_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.insul_table.customContextMenuRequested.connect(
            lambda pos: self._table_context_menu(pos, self.insul_table, self._edit_insulation, self._delete_insulation)
        )
        lay.addWidget(self.insul_table)
        return w

    def refresh_insulation(self):
        if not self._current_project_id:
            return
        session = self._get_session()
        try:
            from services.finishing_service import FinishingService
            svc = FinishingService(session)
            records = svc.insulation_repo.get_all(self._current_project_id)
            
            self.insul_table.setSortingEnabled(False)
            self.insul_table.setRowCount(0)
            comp_cnt = 0

            for r in records:
                row = self.insul_table.rowCount()
                self.insul_table.insertRow(row)
                self.insul_table.setItem(row, 0, QTableWidgetItem(str(r.id)))
                self.insul_table.setItem(row, 1, QTableWidgetItem(r.line_number or ""))
                self.insul_table.setItem(row, 2, QTableWidgetItem(r.spool_number or ""))
                self.insul_table.setItem(row, 3, QTableWidgetItem(r.insulation_type or ""))
                self.insul_table.setItem(row, 4, QTableWidgetItem(r.insulation_material or ""))
                self.insul_table.setItem(row, 5, QTableWidgetItem(str(r.thickness_mm or 0)))
                self.insul_table.setItem(row, 6, QTableWidgetItem(r.cladding_material or ""))
                
                st_txt = r.status or "Pending"
                st_item = QTableWidgetItem(st_txt)
                self._apply_badge(st_item, st_txt)
                self.insul_table.setItem(row, 7, st_item)

                if st_txt == "Completed":
                    comp_cnt += 1

            self.insul_table.setSortingEnabled(True)
            self.kpi_insul.set_value(f"{comp_cnt}/{len(records)}")
            session.commit()
        except Exception as e:
            session.rollback()
            logger.exception("Error in refresh_insulation")
        finally:
            session.close()

    def _filter_insulation(self):
        query = self.txt_search_insul.text().strip().lower()
        filter_val = self.cmb_filter_insul.currentText()
        for r in range(self.insul_table.rowCount()):
            line = self.insul_table.item(r, 1).text().lower()
            spool = self.insul_table.item(r, 2).text().lower()
            mat = self.insul_table.item(r, 4).text().lower()
            st = self.insul_table.item(r, 7).text()

            match_txt = query in line or query in spool or query in mat
            match_st = (filter_val == "All Statuses") or (filter_val in st)
            self.insul_table.setRowHidden(r, not (match_txt and match_st))

    def _add_insulation(self):
        if not self._current_project_id:
            QMessageBox.warning(self, "Project", "Select a project first.")
            return
        dlg = _InsulationDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            session = self._get_session()
            try:
                from services.finishing_service import FinishingService
                svc = FinishingService(session)
                svc.record_insulation(self._current_project_id, **dlg.result_data)
                session.commit()
                self.refresh_insulation()
                QMessageBox.information(self, "Success", "Insulation record saved.")
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    def _edit_insulation(self, row: int):
        rec_id = int(self.insul_table.item(row, 0).text())
        existing = {
            "line_number": self.insul_table.item(row, 1).text(),
            "spool_number": self.insul_table.item(row, 2).text(),
            "insulation_type": self.insul_table.item(row, 3).text(),
            "insulation_material": self.insul_table.item(row, 4).text(),
            "thickness_mm": float(self.insul_table.item(row, 5).text() or 0),
            "cladding_material": self.insul_table.item(row, 6).text(),
            "status": self.insul_table.item(row, 7).text().split()[-1],
        }
        dlg = _InsulationDialog(self, existing_data=existing)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            session = self._get_session()
            try:
                from db.models import InsulationRecord
                rec = session.query(InsulationRecord).get(rec_id)
                if rec:
                    for k, v in dlg.result_data.items():
                        setattr(rec, k, v)
                    session.commit()
                    self.refresh_insulation()
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    def _delete_insulation(self, row: int):
        rec_id = int(self.insul_table.item(row, 0).text())
        if QMessageBox.question(self, "Confirm Delete", f"Delete insulation record ID {rec_id}?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            session = self._get_session()
            try:
                from db.models import InsulationRecord
                rec = session.query(InsulationRecord).get(rec_id)
                if rec:
                    session.delete(rec)
                    session.commit()
                    self.refresh_insulation()
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    # ══════════════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════════════

    def _build_flange_widget(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 8)
        lay.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_flange = QLineEdit()
        self.txt_search_flange.setPlaceholderText("🔍 Search Line, Tag, Gasket...")
        self.txt_search_flange.textChanged.connect(self._filter_flange)
        tb.addWidget(self.txt_search_flange, 1)

        self.cmb_filter_flange = QComboBox()
        self.cmb_filter_flange.addItems(["All Statuses", "Completed", "Pending", "Torqued"])
        self.cmb_filter_flange.currentIndexChanged.connect(self._filter_flange)
        tb.addWidget(self.cmb_filter_flange)

        btn_add = QPushButton("➕ Record Flange Torque")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_flange)
        tb.addWidget(btn_add)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(lambda: self._export_to_csv(self.flange_table, "Flange_Torque_Report"))
        tb.addWidget(btn_exp)

        btn_ref = QPushButton("🔄 Refresh")
        btn_ref.setObjectName("secondaryBtn")
        btn_ref.clicked.connect(self.refresh_flange)
        tb.addWidget(btn_ref)
        lay.addLayout(tb)

        self.flange_table = QTableWidget(0, 9)
        self.flange_table.setHorizontalHeaderLabels([
            "ID", "Line No", "Flange Tag No", "Flange Type",
            "Size (NPS)", "Gasket Class", "Torque Applied (Nm)", "Torque Method", "Inspection Status"
        ])
        self._setup_table_style(self.flange_table)
        self.flange_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.flange_table.customContextMenuRequested.connect(
            lambda pos: self._table_context_menu(pos, self.flange_table, self._edit_flange, self._delete_flange)
        )
        lay.addWidget(self.flange_table)
        return w

    def refresh_flange(self):
        if not self._current_project_id:
            return
        session = self._get_session()
        try:
            from services.finishing_service import FinishingService
            svc = FinishingService(session)
            records = svc.flange_repo.get_all(self._current_project_id)
            
            self.flange_table.setSortingEnabled(False)
            self.flange_table.setRowCount(0)
            torqued_cnt = 0

            for r in records:
                row = self.flange_table.rowCount()
                self.flange_table.insertRow(row)
                self.flange_table.setItem(row, 0, QTableWidgetItem(str(r.id)))
                self.flange_table.setItem(row, 1, QTableWidgetItem(r.line_number or ""))
                self.flange_table.setItem(row, 2, QTableWidgetItem(r.flange_tag or ""))
                self.flange_table.setItem(row, 3, QTableWidgetItem(r.flange_type or ""))
                self.flange_table.setItem(row, 4, QTableWidgetItem(r.size_nps or ""))
                self.flange_table.setItem(row, 5, QTableWidgetItem(r.gasket_type or ""))
                self.flange_table.setItem(row, 6, QTableWidgetItem(str(r.torque_value_nm or 0.0)))
                self.flange_table.setItem(row, 7, QTableWidgetItem(r.torque_method or ""))

                st_txt = r.status or "Pending"
                st_item = QTableWidgetItem(st_txt)
                self._apply_badge(st_item, st_txt)
                self.flange_table.setItem(row, 8, st_item)

                if st_txt in ("Completed", "Torqued", "Accepted"):
                    torqued_cnt += 1

            self.flange_table.setSortingEnabled(True)
            self.kpi_flange.set_value(f"{torqued_cnt}/{len(records)}")
            session.commit()
        except Exception as e:
            session.rollback()
            logger.exception("Error in refresh_flange")
        finally:
            session.close()

    def _filter_flange(self):
        query = self.txt_search_flange.text().strip().lower()
        filter_val = self.cmb_filter_flange.currentText()
        for r in range(self.flange_table.rowCount()):
            line = self.flange_table.item(r, 1).text().lower()
            tag = self.flange_table.item(r, 2).text().lower()
            gasket = self.flange_table.item(r, 5).text().lower()
            st = self.flange_table.item(r, 8).text()

            match_txt = query in line or query in tag or query in gasket
            match_st = (filter_val == "All Statuses") or (filter_val in st)
            self.flange_table.setRowHidden(r, not (match_txt and match_st))

    def _add_flange(self):
        if not self._current_project_id:
            QMessageBox.warning(self, "Project", "Select a project first.")
            return
        dlg = _FlangeDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            session = self._get_session()
            try:
                from services.finishing_service import FinishingService
                svc = FinishingService(session)
                svc.record_flange_torque(self._current_project_id, **dlg.result_data)
                session.commit()
                self.refresh_flange()
                QMessageBox.information(self, "Success", "Flange torque record logged.")
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    def _edit_flange(self, row: int):
        rec_id = int(self.flange_table.item(row, 0).text())
        existing = {
            "line_number": self.flange_table.item(row, 1).text(),
            "flange_tag": self.flange_table.item(row, 2).text(),
            "flange_type": self.flange_table.item(row, 3).text(),
            "size_nps": self.flange_table.item(row, 4).text(),
            "gasket_type": self.flange_table.item(row, 5).text(),
            "torque_value_nm": float(self.flange_table.item(row, 6).text() or 0),
            "torque_method": self.flange_table.item(row, 7).text(),
            "status": self.flange_table.item(row, 8).text().split()[-1],
        }
        dlg = _FlangeDialog(self, existing_data=existing)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            session = self._get_session()
            try:
                from db.models import FlangeTorqueRecord
                rec = session.query(FlangeTorqueRecord).get(rec_id)
                if rec:
                    for k, v in dlg.result_data.items():
                        setattr(rec, k, v)
                    session.commit()
                    self.refresh_flange()
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    def _delete_flange(self, row: int):
        rec_id = int(self.flange_table.item(row, 0).text())
        if QMessageBox.question(self, "Confirm Delete", f"Delete flange torque record ID {rec_id}?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            session = self._get_session()
            try:
                from db.models import FlangeTorqueRecord
                rec = session.query(FlangeTorqueRecord).get(rec_id)
                if rec:
                    session.delete(rec)
                    session.commit()
                    self.refresh_flange()
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    # ══════════════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════════════

    def _build_pwht_widget(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 8)
        lay.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_pwht = QLineEdit()
        self.txt_search_pwht.setPlaceholderText("🔍 Search Weld ID, Procedure, Method...")
        self.txt_search_pwht.textChanged.connect(self._filter_pwht)
        tb.addWidget(self.txt_search_pwht, 1)

        self.cmb_filter_pwht = QComboBox()
        self.cmb_filter_pwht.addItems(["All Results", "Accepted", "Rejected", "Pending"])
        self.cmb_filter_pwht.currentIndexChanged.connect(self._filter_pwht)
        tb.addWidget(self.cmb_filter_pwht)

        btn_add = QPushButton("➕ Record PWHT")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_pwht)
        tb.addWidget(btn_add)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(lambda: self._export_to_csv(self.pwht_table, "PWHT_Report"))
        tb.addWidget(btn_exp)

        btn_ref = QPushButton("🔄 Refresh")
        btn_ref.setObjectName("secondaryBtn")
        btn_ref.clicked.connect(self.refresh_pwht)
        tb.addWidget(btn_ref)
        lay.addLayout(tb)

        self.pwht_table = QTableWidget(0, 9)
        self.pwht_table.setHorizontalHeaderLabels([
            "ID", "Weld Joint ID", "Procedure No", "Heating Method",
            "Soak Temp (°C)", "Duration (Hrs)", "Hardness (HV)", "Execution Date", "Quality Result"
        ])
        self._setup_table_style(self.pwht_table)
        self.pwht_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pwht_table.customContextMenuRequested.connect(
            lambda pos: self._table_context_menu(pos, self.pwht_table, None, self._delete_pwht)
        )
        lay.addWidget(self.pwht_table)
        return w

    def refresh_pwht(self):
        if not self._current_project_id:
            return
        session = self._get_session()
        try:
            from services.finishing_service import FinishingService
            svc = FinishingService(session)
            records = svc.pwht_repo.get_all(self._current_project_id)
            
            self.pwht_table.setSortingEnabled(False)
            self.pwht_table.setRowCount(0)
            accepted_cnt = 0

            for r in records:
                row = self.pwht_table.rowCount()
                self.pwht_table.insertRow(row)
                self.pwht_table.setItem(row, 0, QTableWidgetItem(str(r.id)))
                self.pwht_table.setItem(row, 1, QTableWidgetItem(str(r.weld_id_fk)))
                self.pwht_table.setItem(row, 2, QTableWidgetItem(r.pwht_procedure_no or ""))
                self.pwht_table.setItem(row, 3, QTableWidgetItem(r.heating_method or ""))
                self.pwht_table.setItem(row, 4, QTableWidgetItem(str(r.soak_temperature_c or "")))
                self.pwht_table.setItem(row, 5, QTableWidgetItem(str(r.soak_duration_hours or "")))
                hv = str(r.hardness_max_hv) if getattr(r, 'hardness_test_done', False) else "N/A"
                self.pwht_table.setItem(row, 6, QTableWidgetItem(hv))
                self.pwht_table.setItem(row, 7, QTableWidgetItem(str(r.performed_date or "")))

                res_txt = r.result or "Pending"
                res_item = QTableWidgetItem(res_txt)
                self._apply_badge(res_item, res_txt)
                self.pwht_table.setItem(row, 8, res_item)

                if res_txt == "Accepted":
                    accepted_cnt += 1

            self.pwht_table.setSortingEnabled(True)
            self.kpi_pwht.set_value(f"{accepted_cnt}/{len(records)}")
            session.commit()
        except Exception as e:
            session.rollback()
            logger.exception("Error in refresh_pwht")
        finally:
            session.close()

    def _filter_pwht(self):
        query = self.txt_search_pwht.text().strip().lower()
        filter_val = self.cmb_filter_pwht.currentText()
        for r in range(self.pwht_table.rowCount()):
            weld = self.pwht_table.item(r, 1).text().lower()
            proc = self.pwht_table.item(r, 2).text().lower()
            method = self.pwht_table.item(r, 3).text().lower()
            res = self.pwht_table.item(r, 8).text()

            match_txt = query in weld or query in proc or query in method
            match_res = (filter_val == "All Results") or (filter_val in res)
            self.pwht_table.setRowHidden(r, not (match_txt and match_res))

    def _add_pwht(self):
        if not self._current_project_id:
            QMessageBox.warning(self, "Project", "Select a project first.")
            return
        try:
            from ui.dialogs.pwht_record_dialog import PWHTRecordDialog
            dlg = PWHTRecordDialog(self)
        except ImportError:
            dlg = _PWHTSimpleDialog(self)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            session = self._get_session()
            try:
                from services.finishing_service import FinishingService
                svc = FinishingService(session)
                data = dlg.result_data
                weld_fk = data.pop("weld_id_fk")
                svc.record_pwht(self._current_project_id, weld_fk, **data)
                session.commit()
                self.refresh_pwht()
                QMessageBox.information(self, "Success", "PWHT record registered successfully.")
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    def _delete_pwht(self, row: int):
        rec_id = int(self.pwht_table.item(row, 0).text())
        if QMessageBox.question(self, "Confirm Delete", f"Delete PWHT Record ID {rec_id}?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            session = self._get_session()
            try:
                from db.models import PWHTRecord
                rec = session.query(PWHTRecord).get(rec_id)
                if rec:
                    session.delete(rec)
                    session.commit()
                    self.refresh_pwht()
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    # ══════════════════════════════════════════════════════
    # Implementation note.
    # ══════════════════════════════════════════════════════

    def _build_reinst_widget(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 8)
        lay.setSpacing(6)

        tb = QHBoxLayout()
        self.txt_search_reinst = QLineEdit()
        self.txt_search_reinst.setPlaceholderText("🔍 Search Line, Test Package, Description...")
        self.txt_search_reinst.textChanged.connect(self._filter_reinst)
        tb.addWidget(self.txt_search_reinst, 1)

        self.cmb_filter_reinst = QComboBox()
        self.cmb_filter_reinst.addItems(["All Items", "Completed", "Pending", "Verified"])
        self.cmb_filter_reinst.currentIndexChanged.connect(self._filter_reinst)
        tb.addWidget(self.cmb_filter_reinst)

        btn_add = QPushButton("➕ Add Punch Item")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_reinst)
        tb.addWidget(btn_add)

        btn_comp = QPushButton("✅ Mark Verified")
        btn_comp.setObjectName("secondaryBtn")
        btn_comp.clicked.connect(self._complete_reinst)
        tb.addWidget(btn_comp)

        btn_exp = QPushButton("📥 Export CSV")
        btn_exp.setObjectName("secondaryBtn")
        btn_exp.clicked.connect(lambda: self._export_to_csv(self.reinst_table, "Reinstatement_Punchlist"))
        tb.addWidget(btn_exp)

        btn_ref = QPushButton("🔄 Refresh")
        btn_ref.setObjectName("secondaryBtn")
        btn_ref.clicked.connect(self.refresh_reinst)
        tb.addWidget(btn_ref)
        lay.addLayout(tb)

        self.reinst_table = QTableWidget(0, 7)
        self.reinst_table.setHorizontalHeaderLabels([
            "ID", "Hydro Test Package", "Line Number", "Category / Type",
            "Punch Description", "Verified By Inspector", "Punch Status"
        ])
        self._setup_table_style(self.reinst_table)
        self.reinst_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.reinst_table.customContextMenuRequested.connect(
            lambda pos: self._table_context_menu(pos, self.reinst_table, None, self._delete_reinst)
        )
        lay.addWidget(self.reinst_table)
        return w

    def refresh_reinst(self):
        if not self._current_project_id:
            return
        session = self._get_session()
        try:
            from services.reinstatement_service import ReinstatementService
            svc = ReinstatementService(session)
            items = svc.repo.get_all(self._current_project_id)
            
            self.reinst_table.setSortingEnabled(False)
            self.reinst_table.setRowCount(0)
            verified_cnt = 0

            for r in items:
                row = self.reinst_table.rowCount()
                self.reinst_table.insertRow(row)
                self.reinst_table.setItem(row, 0, QTableWidgetItem(str(r.id)))
                self.reinst_table.setItem(row, 1, QTableWidgetItem(str(r.test_package_id)))
                self.reinst_table.setItem(row, 2, QTableWidgetItem(r.line_number or ""))
                self.reinst_table.setItem(row, 3, QTableWidgetItem(r.item_type or "Punch Item"))
                self.reinst_table.setItem(row, 4, QTableWidgetItem(r.item_description or ""))
                self.reinst_table.setItem(row, 5, QTableWidgetItem(r.verified_by or "Unassigned"))

                st_txt = r.status or "Pending"
                st_item = QTableWidgetItem(st_txt)
                self._apply_badge(st_item, st_txt)
                self.reinst_table.setItem(row, 6, st_item)

                if st_txt in ("Completed", "Verified", "Accepted"):
                    verified_cnt += 1

            self.reinst_table.setSortingEnabled(True)
            self.kpi_reinst.set_value(f"{verified_cnt}/{len(items)}")
            session.commit()
        except Exception as e:
            session.rollback()
            logger.exception("Error in refresh_reinst")
        finally:
            session.close()

    def _filter_reinst(self):
        query = self.txt_search_reinst.text().strip().lower()
        filter_val = self.cmb_filter_reinst.currentText()
        for r in range(self.reinst_table.rowCount()):
            tp = self.reinst_table.item(r, 1).text().lower()
            line = self.reinst_table.item(r, 2).text().lower()
            desc = self.reinst_table.item(r, 4).text().lower()
            st = self.reinst_table.item(r, 6).text()

            match_txt = query in tp or query in line or query in desc
            match_st = (filter_val == "All Items") or (filter_val in st)
            self.reinst_table.setRowHidden(r, not (match_txt and match_st))

    def _add_reinst(self):
        if not self._current_project_id:
            QMessageBox.warning(self, "Project", "Select a project first.")
            return
        dlg = _ReinstatementDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            session = self._get_session()
            try:
                from services.reinstatement_service import ReinstatementService
                svc = ReinstatementService(session)
                data = dlg.result_data
                svc.add_item(
                    self._current_project_id, 
                    data["test_package_id"], 
                    data["description"], 
                    line_number=data.get("line_number"),
                    item_type=data.get("item_type")
                )
                session.commit()
                self.refresh_reinst()
                QMessageBox.information(self, "Success", "Reinstatement item logged.")
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    def _complete_reinst(self):
        row = self.reinst_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Warning", "Select a reinstatement item from the table first.")
            return
        item_id = int(self.reinst_table.item(row, 0).text())
        session = self._get_session()
        try:
            from services.reinstatement_service import ReinstatementService
            svc = ReinstatementService(session)
            u_name = getattr(self.session_manager, 'username', 'admin')
            svc.complete_item(item_id, u_name)
            session.commit()
            self.refresh_reinst()
            QMessageBox.information(self, "Verified", f"Item ID {item_id} marked as Completed by {u_name}.")
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Error", str(e))
        finally:
            session.close()

    def _delete_reinst(self, row: int):
        item_id = int(self.reinst_table.item(row, 0).text())
        if QMessageBox.question(self, "Confirm Delete", f"Delete reinstatement punch item ID {item_id}?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            session = self._get_session()
            try:
                from db.models import ReinstatementItem
                rec = session.query(ReinstatementItem).get(item_id)
                if rec:
                    session.delete(rec)
                    session.commit()
                    self.refresh_reinst()
            except Exception as e:
                session.rollback()
                QMessageBox.critical(self, "Error", str(e))
            finally:
                session.close()

    # ══════════════════════════════════════════════════════
    #  Global Actions & Helpers
    # ══════════════════════════════════════════════════════

    def refresh(self):
        self.refresh_painting()
        self.refresh_insulation()
        self.refresh_flange()
        self.refresh_pwht()
        self.refresh_reinst()

    def _table_context_menu(self, pos, table: QTableWidget, edit_func, delete_func):
        row = table.rowAt(pos.y())
        if row < 0:
            return
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: white; border: 1px solid #cbd5e1; } QMenu::item { padding: 6px 18px; }")

        act_copy = QAction("📋 Copy Row Information", self)
        act_copy.triggered.connect(lambda: self._copy_row_text(table, row))
        menu.addAction(act_copy)

        if edit_func:
            act_edit = QAction("✏️ Edit Record", self)
            act_edit.triggered.connect(lambda: edit_func(row))
            menu.addAction(act_edit)

        if delete_func:
            act_del = QAction("🗑️ Delete Record", self)
            act_del.triggered.connect(lambda: delete_func(row))
            menu.addAction(act_del)

        menu.exec(table.viewport().mapToGlobal(pos))

    def _copy_row_text(self, table: QTableWidget, row: int):
        data = [table.item(row, c).text() for c in range(table.columnCount()) if table.item(row, c)]
        QApplication.clipboard().setText(" | ".join(data))

    def _export_to_csv(self, table: QTableWidget, prefix: str):
        if table.rowCount() == 0:
            QMessageBox.warning(self, "Export", "Table contains no data to export.")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename, _ = QFileDialog.getSaveFileName(self, "Export CSV", f"{prefix}_{timestamp}.csv", "CSV Files (*.csv)")
        if not filename:
            return

        try:
            with open(filename, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
                writer.writerow(headers)

                for r in range(table.rowCount()):
                    if not table.isRowHidden(r):
                        row_vals = []
                        for c in range(table.columnCount()):
                            it = table.item(r, c)
                            row_vals.append(it.text().strip() if it else "")
                        writer.writerow(row_vals)

            QMessageBox.information(self, "Export Complete", f"Data exported successfully to:\n{filename}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to save CSV file:\n{e}")


# ─────────────────────────────────────────────
# Implementation note.
# ─────────────────────────────────────────────

class _PaintingDialog(QDialog):
    def __init__(self, parent=None, existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Painting Record" if existing_data else "Record Painting Inspection")
        self.setMinimumWidth(440)
        self.setStyleSheet(FINISHING_STYLESHEET)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.txt_line = QLineEdit()
        self.txt_spool = QLineEdit()
        self.txt_code = QLineEdit()
        self.cmb_prep = QComboBox()
        self.cmb_prep.addItems(SURFACE_PREP_GRADES)
        
        self.spn_primer = QDoubleSpinBox()
        self.spn_primer.setRange(0, 9999)
        self.spn_primer.setSuffix(" μm")
        self.spn_primer.valueChanged.connect(self._calc_total)

        self.spn_finish = QDoubleSpinBox()
        self.spn_finish.setRange(0, 9999)
        self.spn_finish.setSuffix(" μm")
        self.spn_finish.valueChanged.connect(self._calc_total)

        self.spn_total = QDoubleSpinBox()
        self.spn_total.setRange(0, 19999)
        self.spn_total.setSuffix(" μm")

        self.cmb_result = QComboBox()
        self.cmb_result.addItems(["Accepted", "Pending", "Rejected"])

        form.addRow("Line Number *:", self.txt_line)
        form.addRow("Spool Number *:", self.txt_spool)
        form.addRow("Painting System Code:", self.txt_code)
        form.addRow("Surface Prep Grade:", self.cmb_prep)
        form.addRow("Primer Dry Film Thk:", self.spn_primer)
        form.addRow("Finish Dry Film Thk:", self.spn_finish)
        form.addRow("Total Measured DFT:", self.spn_total)
        form.addRow("QC Inspection Result:", self.cmb_result)
        layout.addLayout(form)

        if existing_data:
            self.txt_line.setText(existing_data.get("line_number", ""))
            self.txt_spool.setText(existing_data.get("spool_number", ""))
            self.txt_code.setText(existing_data.get("painting_code", ""))
            self.cmb_prep.setCurrentText(existing_data.get("surface_prep_grade", "Sa 2.5"))
            self.spn_primer.setValue(existing_data.get("primer_dft_micron", 0))
            self.spn_finish.setValue(existing_data.get("finish_dft_micron", 0))
            self.spn_total.setValue(existing_data.get("total_dft_micron", 0))
            self.cmb_result.setCurrentText(existing_data.get("result", "Accepted"))

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Record")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _calc_total(self):
        self.spn_total.setValue(self.spn_primer.value() + self.spn_finish.value())

    def _save(self):
        if not self.txt_line.text().strip():
            QMessageBox.warning(self, "Validation", "Piping line number is required.")
            return
        self.result_data = {
            "line_number": self.txt_line.text().strip(),
            "spool_number": self.txt_spool.text().strip(),
            "painting_code": self.txt_code.text().strip(),
            "surface_prep_grade": self.cmb_prep.currentText(),
            "primer_dft_micron": self.spn_primer.value(),
            "finish_dft_micron": self.spn_finish.value(),
            "total_dft_micron": self.spn_total.value(),
            "result": self.cmb_result.currentText(),
        }
        self.accept()


class _InsulationDialog(QDialog):
    def __init__(self, parent=None, existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Insulation Record" if existing_data else "Record Thermal Insulation")
        self.setMinimumWidth(440)
        self.setStyleSheet(FINISHING_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.txt_line = QLineEdit()
        self.txt_spool = QLineEdit()
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(INSULATION_TYPES)
        self.cmb_mat = QComboBox()
        self.cmb_mat.addItems(INSULATION_MATERIALS)
        self.spn_thk = QDoubleSpinBox()
        self.spn_thk.setRange(0, 500)
        self.spn_thk.setSuffix(" mm")
        self.txt_clad = QLineEdit()
        self.cmb_status = QComboBox()
        self.cmb_status.addItems(["Completed", "Pending", "In Progress"])

        form.addRow("Line Number *:", self.txt_line)
        form.addRow("Spool Number *:", self.txt_spool)
        form.addRow("Insulation Class:", self.cmb_type)
        form.addRow("Core Material:", self.cmb_mat)
        form.addRow("Nominal Thickness:", self.spn_thk)
        form.addRow("Cladding Spec / MOC:", self.txt_clad)
        form.addRow("Installation Status:", self.cmb_status)
        layout.addLayout(form)

        if existing_data:
            self.txt_line.setText(existing_data.get("line_number", ""))
            self.txt_spool.setText(existing_data.get("spool_number", ""))
            self.cmb_type.setCurrentText(existing_data.get("insulation_type", "Hot"))
            self.cmb_mat.setCurrentText(existing_data.get("insulation_material", "Mineral Wool"))
            self.spn_thk.setValue(existing_data.get("thickness_mm", 50))
            self.txt_clad.setText(existing_data.get("cladding_material", ""))
            self.cmb_status.setCurrentText(existing_data.get("status", "Completed"))

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Insulation")
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
        if not self.txt_line.text().strip():
            QMessageBox.warning(self, "Validation", "Piping line number is required.")
            return
        self.result_data = {
            "line_number": self.txt_line.text().strip(),
            "spool_number": self.txt_spool.text().strip(),
            "insulation_type": self.cmb_type.currentText(),
            "insulation_material": self.cmb_mat.currentText(),
            "thickness_mm": self.spn_thk.value(),
            "cladding_material": self.txt_clad.text().strip(),
            "status": self.cmb_status.currentText(),
        }
        self.accept()


class _FlangeDialog(QDialog):
    def __init__(self, parent=None, existing_data: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Flange Torque" if existing_data else "Record Flange Bolt Torquing")
        self.setMinimumWidth(440)
        self.setStyleSheet(FINISHING_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.txt_line = QLineEdit()
        self.txt_tag = QLineEdit()
        self.txt_type = QLineEdit()
        self.txt_type.setPlaceholderText("e.g., WN, SO, Blind, RTJ...")
        self.txt_size = QLineEdit()
        self.txt_gasket = QLineEdit()
        self.spn_torque = QDoubleSpinBox()
        self.spn_torque.setRange(0, 99999)
        self.spn_torque.setSuffix(" Nm")
        self.cmb_method = QComboBox()
        self.cmb_method.addItems(TORQUE_METHODS)
        self.cmb_status = QComboBox()
        self.cmb_status.addItems(["Completed", "Pending", "Torqued"])

        form.addRow("Line Number *:", self.txt_line)
        form.addRow("Flange Tag Identifier *:", self.txt_tag)
        form.addRow("Flange Facing / Type:", self.txt_type)
        form.addRow("Nominal Size (NPS):", self.txt_size)
        form.addRow("Gasket Type & Material:", self.txt_gasket)
        form.addRow("Applied Torque Value:", self.spn_torque)
        form.addRow("Torquing Tool / Method:", self.cmb_method)
        form.addRow("Joint Status:", self.cmb_status)
        layout.addLayout(form)

        if existing_data:
            self.txt_line.setText(existing_data.get("line_number", ""))
            self.txt_tag.setText(existing_data.get("flange_tag", ""))
            self.txt_type.setText(existing_data.get("flange_type", ""))
            self.txt_size.setText(existing_data.get("size_nps", ""))
            self.txt_gasket.setText(existing_data.get("gasket_type", ""))
            self.spn_torque.setValue(existing_data.get("torque_value_nm", 0))
            self.cmb_method.setCurrentText(existing_data.get("torque_method", "Manual Torque Wrench"))
            self.cmb_status.setCurrentText(existing_data.get("status", "Completed"))

        btns = QHBoxLayout()
        btn_save = QPushButton("Save Torque Log")
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
        if not self.txt_line.text().strip() or not self.txt_tag.text().strip():
            QMessageBox.warning(self, "Validation", "Line number and Flange Tag are mandatory.")
            return
        self.result_data = {
            "line_number": self.txt_line.text().strip(),
            "flange_tag": self.txt_tag.text().strip(),
            "flange_type": self.txt_type.text().strip(),
            "size_nps": self.txt_size.text().strip(),
            "gasket_type": self.txt_gasket.text().strip(),
            "torque_value_nm": self.spn_torque.value(),
            "torque_method": self.cmb_method.currentText(),
            "status": self.cmb_status.currentText(),
        }
        self.accept()


class _ReinstatementDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Line Reinstatement Item")
        self.setMinimumWidth(440)
        self.setStyleSheet(FINISHING_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.spn_tp = QSpinBox()
        self.spn_tp.setRange(1, 999999)
        self.txt_line = QLineEdit()
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(["Gasket Replacement", "Blind Flange Removal", "Valve Installation", "Spectacle Blind Swapped", "Support Realignment", "General"])
        self.txt_desc = QTextEdit()
        self.txt_desc.setMaximumHeight(90)

        form.addRow("Test Package ID *:", self.spn_tp)
        form.addRow("Line Number:", self.txt_line)
        form.addRow("Item Category:", self.cmb_type)
        form.addRow("Punch / Action Description *:", self.txt_desc)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_save = QPushButton("Add Item")
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
        desc = self.txt_desc.toPlainText().strip()
        if not desc:
            QMessageBox.warning(self, "Validation", "Description is mandatory.")
            return
        self.result_data = {
            "test_package_id": self.spn_tp.value(),
            "line_number": self.txt_line.text().strip(),
            "item_type": self.cmb_type.currentText(),
            "description": desc,
        }
        self.accept()


class _PWHTSimpleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Record PWHT Entry")
        self.setMinimumWidth(440)
        self.setStyleSheet(FINISHING_STYLESHEET)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.spn_weld = QSpinBox()
        self.spn_weld.setRange(1, 999999)
        self.txt_proc = QLineEdit()
        self.cmb_method = QComboBox()
        self.cmb_method.addItems(PWHT_METHODS)
        self.spn_temp = QDoubleSpinBox()
        self.spn_temp.setRange(0, 1500)
        self.spn_temp.setValue(620)
        self.spn_temp.setSuffix(" °C")
        self.spn_dur = QDoubleSpinBox()
        self.spn_dur.setRange(0, 100)
        self.spn_dur.setValue(2.0)
        self.spn_dur.setSuffix(" Hrs")
        self.cmb_res = QComboBox()
        self.cmb_res.addItems(PWHT_RESULTS)

        form.addRow("Weld Joint ID FK *:", self.spn_weld)
        form.addRow("PWHT Procedure No:", self.txt_proc)
        form.addRow("Heating Method:", self.cmb_method)
        form.addRow("Soak Temperature:", self.spn_temp)
        form.addRow("Soak Duration:", self.spn_dur)
        form.addRow("Quality Result:", self.cmb_res)
        layout.addLayout(form)

        btns = QHBoxLayout()
        btn_save = QPushButton("Save PWHT")
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
        self.result_data = {
            "weld_id_fk": self.spn_weld.value(),
            "pwht_procedure_no": self.txt_proc.text().strip(),
            "heating_method": self.cmb_method.currentText(),
            "soak_temperature_c": self.spn_temp.value(),
            "soak_duration_hours": self.spn_dur.value(),
            "result": self.cmb_res.currentText(),
            "performed_date": datetime.date.today(),
        }
        self.accept()