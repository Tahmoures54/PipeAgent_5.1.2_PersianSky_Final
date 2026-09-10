# -*- coding: utf-8 -*-
# ui/tabs/field_erection_tab.py – Field installation progress overview
from __future__ import annotations

import csv
import logging
import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QSplitter, QLineEdit, QFrame, QProgressBar,
    QMenu, QFileDialog, QMessageBox, QApplication, QAbstractItemView,
)
from PyQt6.QtGui import QColor, QFont, QBrush, QAction, QCursor

from db.manager import DatabaseManager
from db.models import Project, Spool, Weld, PipeSupport
from security.session import SessionManager

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  PALETTE & STYLES
# ─────────────────────────────────────────────────────────────
STATUS_PALETTE = {
    "Installed":         {"bg": "#dcfce7", "fg": "#166534", "icon": "🟢"},
    "Released to Site":  {"bg": "#e0f2fe", "fg": "#075985", "icon": "🔵"},
    "Tested":            {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "🟣"},
    "NDT Complete":      {"bg": "#e0e7ff", "fg": "#3730a3", "icon": "🛡️"},
    "Fabricated":        {"bg": "#f1f5f9", "fg": "#334155", "icon": "⚙️"},
    "Accepted":          {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Rejected":          {"bg": "#fee2e2", "fg": "#991b1b", "icon": "❌"},
    "Pending":           {"bg": "#fef3c7", "fg": "#92400e", "icon": "⏳"},
    "Fitup Complete":    {"bg": "#fff1e6", "fg": "#9a3412", "icon": "🔧"},
}
DEFAULT_STATUS = {"bg": "#f8fafc", "fg": "#475569", "icon": "•"}

ERECTION_STYLESHEET = """
    QWidget#fieldErectionTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #102a43, stop:1 #1e3a5f);
        border-radius: 12px; padding: 16px;
    }
    QLabel#mainTitle {
        color: #f8fafc; font-size: 24px; font-weight: 900;
        font-family: 'Segoe UI', -apple-system, sans-serif;
    }
    QLabel#subTitle { color: #94a3b8; font-size: 12px; }
    QFrame#kpiCard {
        background: white; border: 1px solid #cbd5e1;
        border-radius: 10px; padding: 10px 14px;
    }
    QFrame#kpiCard:hover { border-color: #3b82f6; background: #f8fafc; }
    QLabel#kpiTitle {
        font-size: 11px; font-weight: 700; color: #64748b;
        text-transform: uppercase;
    }
    QLabel#kpiValue { font-size: 20px; font-weight: 800; color: #0f172a; }
    QLineEdit, QComboBox {
        padding: 8px 12px; border: 2px solid #cbd5e1;
        border-radius: 6px; font-size: 13px;
        background: white; color: #0f172a;
    }
    QLineEdit:focus, QComboBox:focus {
        border-color: #3b82f6; background: #f8faff;
    }
    QTableWidget {
        background: white; border: 1px solid #cbd5e1;
        border-radius: 8px; gridline-color: #f1f5f9; font-size: 12px;
    }
    QTableWidget::item:selected { background: #eff6ff; color: #1e293b; }
    QHeaderView::section {
        background: #f1f5f9; color: #475569;
        font-weight: 700; font-size: 11px; padding: 8px;
        border: none; border-bottom: 2px solid #cbd5e1;
        border-right: 1px solid #e2e8f0;
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
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #3b82f6, stop:1 #2563eb);
        color: white; border: none; padding: 8px 16px;
        border-radius: 6px; font-weight: 700;
    }
    QPushButton#primaryBtn:hover {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #2563eb, stop:1 #1d4ed8);
    }
    QPushButton#secondaryBtn {
        background: white; color: #334155;
        border: 2px solid #cbd5e1;
        padding: 7px 14px; border-radius: 6px; font-weight: 600;
    }
    QPushButton#secondaryBtn:hover {
        background: #f8fafc; border-color: #3b82f6; color: #3b82f6;
    }
"""

# ─────────────────────────────────────────────────────────────
#  WORKER
# ─────────────────────────────────────────────────────────────
class ErectionCalcWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, db: DatabaseManager, project_id: int):
        super().__init__()
        self.db = db
        self.project_id = project_id

    def run(self):
        try:
            results = {}
            with self.db.session_scope() as s:
                spools = s.query(Spool).filter(Spool.project_id == self.project_id).all()
                results["spools_data"] = [
                    {
                        "id": sp.id,
                        "number": sp.spool_number,
                        "line": sp.line_number or "",
                        "class": sp.pipe_class or "",
                        "status": sp.status or "Fabricated",
                        "installed_date": str(sp.installed_date or ""),
                    } for sp in spools
                ]

                welds = s.query(Weld).filter(
                    Weld.project_id == self.project_id,
                    Weld.weld_type == "Field",
                ).all()
                results["welds_data"] = [
                    {
                        "id": w.id,
                        "weld_id": w.weld_id,
                        "line": w.line_number or "",
                        "size": w.size or "",
                        "status": w.status or "Pending",
                        "welder": w.welder_id or "",
                    } for w in welds
                ]

                supports = s.query(PipeSupport).filter(
                    PipeSupport.project_id == self.project_id
                ).all()
                results["supports_total"] = len(supports)
                results["supports_installed"] = sum(
                    1 for x in supports
                    if (x.status or "") in ("Installed", "Inspected", "Accepted")
                )

            self.finished.emit(results)
        except Exception as e:
            logger.exception("Erection worker background error.")
            self.error.emit(str(e))


# ─────────────────────────────────────────────────────────────
#  KPI CARD
# ─────────────────────────────────────────────────────────────
class ErectionKPICard(QFrame):
    def __init__(self, title: str, icon: str, accent_color: str = "#3b82f6"):
        super().__init__()
        self.setObjectName("kpiCard")
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(12, 10, 12, 10)

        top = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"font-size: 20px; color: {accent_color};")
        top.addWidget(icon_lbl); top.addStretch()

        self.lbl_value = QLabel("—")
        self.lbl_value.setObjectName("kpiValue")
        top.addWidget(self.lbl_value)
        layout.addLayout(top)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("kpiTitle")
        layout.addWidget(self.lbl_title)

    def set_stats(self, value_text: str, highlight: bool = False):
        self.lbl_value.setText(value_text)
        if highlight:
            self.lbl_value.setStyleSheet(
                "color: #166534; font-size: 20px; font-weight: 800;"
            )


# ─────────────────────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────────────────────
class FieldErectionTab(QWidget):
    """Comprehensive site installation progress dashboard."""

    def __init__(self, db: DatabaseManager, session: SessionManager):
        super().__init__()
        self.setObjectName("fieldErectionTab")
        self.db = db
        self.session = session
        self.project_id: Optional[int] = None
        self._worker: Optional[ErectionCalcWorker] = None

        self._local_spools: list[dict] = []
        self._local_welds: list[dict] = []

        self._build()
        self.setStyleSheet(ERECTION_STYLESHEET)
        self._load_projects()

    # ── BUILD UI ─────────────────────────────────────────────
    def _build(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        header_card = QFrame()
        header_card.setObjectName("headerCard")
        hdr_layout = QHBoxLayout(header_card)
        hdr_layout.setContentsMargins(16, 12, 16, 12)

        title_lay = QVBoxLayout()
        title = QLabel("🛠️ Field Erection Progress")
        title.setObjectName("mainTitle")
        sub = QLabel(
            "Operational control center for on-site spools, field joints, "
            "and piping support erection."
        )
        sub.setObjectName("subTitle")
        title_lay.addWidget(title)
        title_lay.addWidget(sub)
        hdr_layout.addLayout(title_lay, 1)

        ctrl_lay = QHBoxLayout()
        ctrl_lay.setSpacing(8)
        lbl_proj = QLabel("Active Project:")
        lbl_proj.setStyleSheet("color: white; font-weight: 700; font-size: 13px;")
        ctrl_lay.addWidget(lbl_proj)

        self.proj = QComboBox()
        self.proj.setMinimumWidth(220)
        self.proj.currentIndexChanged.connect(self._proj_changed)
        ctrl_lay.addWidget(self.proj)

        self.btn_refresh = QPushButton("↻ Refresh OS")
        self.btn_refresh.setObjectName("secondaryBtn")
        self.btn_refresh.clicked.connect(self.refresh)
        ctrl_lay.addWidget(self.btn_refresh)
        hdr_layout.addLayout(ctrl_lay)

        main_layout.addWidget(header_card)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        kpi_grid = QHBoxLayout()
        kpi_grid.setSpacing(8)

        self.card_spools_site    = ErectionKPICard("Spools Received", "🚛", "#0ea5e9")
        self.card_spools_install = ErectionKPICard("Installed Rate", "🟢", "#10b981")
        self.card_field_joints   = ErectionKPICard("Field Welds OK", "⚡", "#f59e0b")
        self.card_supports       = ErectionKPICard("Supports Erected", "🔩", "#8b5cf6")
        for card in (self.card_spools_site, self.card_spools_install,
                     self.card_field_joints, self.card_supports):
            kpi_grid.addWidget(card)
        main_layout.addLayout(kpi_grid)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(8)

        # Spools panel
        spool_box = QGroupBox("🚛 SPOOLS RECEIVED ON SITE / INSTALLED")
        spool_lay = QVBoxLayout(spool_box)
        spool_lay.setContentsMargins(8, 12, 8, 8)

        spool_filter_lay = QHBoxLayout()
        self.txt_spool_search = QLineEdit()
        self.txt_spool_search.setPlaceholderText(
            "🔍 Quick Search Spools (e.g., Line No, Spool No)..."
        )
        self.txt_spool_search.textChanged.connect(self._apply_spool_filter)
        spool_filter_lay.addWidget(self.txt_spool_search, 1)

        self.cmb_spool_status = QComboBox()
        self.cmb_spool_status.addItem("All Statuses", None)
        self.cmb_spool_status.addItems(
            ["Released to Site", "Installed", "Tested", "NDT Complete", "Fabricated"]
        )
        self.cmb_spool_status.currentIndexChanged.connect(self._apply_spool_filter)
        spool_filter_lay.addWidget(self.cmb_spool_status)

        btn_exp_spools = QPushButton("📥 Export Spools")
        btn_exp_spools.setObjectName("secondaryBtn")
        btn_exp_spools.clicked.connect(self._export_spools_csv)
        spool_filter_lay.addWidget(btn_exp_spools)
        spool_lay.addLayout(spool_filter_lay)

        self.spool_table = QTableWidget(0, 6)
        self.spool_table.setHorizontalHeaderLabels([
            "ID", "Spool Identifier", "Piping Line No", "Pipe Class",
            "Field Installation Status", "Erection Date",
        ])
        self._style_table(self.spool_table)
        self.spool_table.setColumnHidden(0, True)
        self.spool_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.spool_table.customContextMenuRequested.connect(self._show_spool_context_menu)
        spool_lay.addWidget(self.spool_table)
        splitter.addWidget(spool_box)

        # Welds panel
        weld_box = QGroupBox("🔥 FIELD JOINTS & ERECTION WELDS")
        weld_lay = QVBoxLayout(weld_box)
        weld_lay.setContentsMargins(8, 12, 8, 8)

        weld_filter_lay = QHBoxLayout()
        self.txt_weld_search = QLineEdit()
        self.txt_weld_search.setPlaceholderText(
            "🔍 Quick Search Field Joint (e.g., Weld ID, Welder ID)..."
        )
        self.txt_weld_search.textChanged.connect(self._apply_weld_filter)
        weld_filter_lay.addWidget(self.txt_weld_search, 1)

        self.cmb_weld_status = QComboBox()
        self.cmb_weld_status.addItem("All Statuses", None)
        self.cmb_weld_status.addItems(
            ["Accepted", "Rejected", "Pending", "Fitup Complete"]
        )
        self.cmb_weld_status.currentIndexChanged.connect(self._apply_weld_filter)
        weld_filter_lay.addWidget(self.cmb_weld_status)

        btn_exp_welds = QPushButton("📥 Export Welds")
        btn_exp_welds.setObjectName("secondaryBtn")
        btn_exp_welds.clicked.connect(self._export_welds_csv)
        weld_filter_lay.addWidget(btn_exp_welds)
        weld_lay.addLayout(weld_filter_lay)

        self.weld_table = QTableWidget(0, 6)
        self.weld_table.setHorizontalHeaderLabels([
            "ID", "Field Weld ID", "Piping Line No", "Joint Size",
            "Erection Quality Status", "Assigned Welder",
        ])
        self._style_table(self.weld_table)
        self.weld_table.setColumnHidden(0, True)
        self.weld_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.weld_table.customContextMenuRequested.connect(self._show_weld_context_menu)
        weld_lay.addWidget(self.weld_table)
        splitter.addWidget(weld_box)

        main_layout.addWidget(splitter, 1)

        tip_card = QFrame()
        tip_card.setStyleSheet(
            "background: #f1f5f9; border-radius: 6px; padding: 6px 12px;"
        )
        tip_lay = QHBoxLayout(tip_card)
        tip_lbl = QLabel(
            "💡 <b>Field OS Tip:</b> Spool statuses are integrated from Spooling, "
            "welding inspection workflows can be updated directly from the "
            "<b>Joints/WJC</b> tab."
        )
        tip_lbl.setStyleSheet("color: #475569; font-size: 11px;")
        tip_lay.addWidget(tip_lbl)
        main_layout.addWidget(tip_card)

    def _style_table(self, table: QTableWidget):
        # ✅ FIXED: use QAbstractItemView enums (not QTableWidget)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    # ── DATA LOADING ─────────────────────────────────────────
    def _load_projects(self):
        self.proj.blockSignals(True)
        self.proj.clear()
        try:
            with self.db.session_scope() as s:
                for p in s.query(Project).order_by(Project.project_code):
                    self.proj.addItem(f"{p.project_code} – {p.title}", p.id)
        except Exception:
            logger.exception("Erection UI - Failed to query database projects.")
        self.proj.blockSignals(False)
        if self.proj.count():
            self._proj_changed()

    def _proj_changed(self):
        self.project_id = self.proj.currentData()
        self.refresh()

    def refresh(self):
        if not self.project_id:
            self._clear_kpis_and_tables()
            return

        self.progress_bar.setVisible(True)
        self.btn_refresh.setEnabled(False)

        # ✅ FIXED: avoid leaked threads
        if self._worker is not None:
            try:
                if self._worker.isRunning():
                    self._worker.wait(2000)
                self._worker.deleteLater()
            except Exception:
                pass
            self._worker = None

        self._worker = ErectionCalcWorker(self.db, self.project_id)
        self._worker.finished.connect(self._on_calc_success)
        self._worker.error.connect(self._on_calc_failed)
        self._worker.start()

    def _on_calc_success(self, results: dict):
        self.progress_bar.setVisible(False)
        self.btn_refresh.setEnabled(True)

        self._local_spools = results["spools_data"]
        self._local_welds = results["welds_data"]

        total_spools = len(self._local_spools)
        site_spools = sum(
            1 for x in self._local_spools
            if x["status"] in
            ("Released to Site", "Installed", "Tested", "NDT Complete")
        )
        installed_spools = sum(
            1 for x in self._local_spools if x["status"] in ("Installed", "Tested")
        )

        total_welds = len(self._local_welds)
        accepted_welds = sum(
            1 for x in self._local_welds if x["status"] == "Accepted"
        )

        self.card_spools_site.set_stats(f"{site_spools}/{total_spools}")

        install_pct = (installed_spools / total_spools * 100) if total_spools else 0.0
        self.card_spools_install.set_stats(
            f"{install_pct:.1f}%", highlight=(install_pct > 75.0)
        )
        self.card_field_joints.set_stats(f"{accepted_welds}/{total_welds}")

        supports_total = results["supports_total"]
        supports_installed = results["supports_installed"]
        self.card_supports.set_stats(f"{supports_installed}/{supports_total}")

        self._apply_spool_filter()
        self._apply_weld_filter()

        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _on_calc_failed(self, error_msg: str):
        self.progress_bar.setVisible(False)
        self.btn_refresh.setEnabled(True)
        QMessageBox.critical(
            self, "Calculation Fault",
            f"Error computing erection stats:\n{error_msg}"
        )
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _clear_kpis_and_tables(self):
        self.spool_table.setRowCount(0)
        self.weld_table.setRowCount(0)
        self.card_spools_site.set_stats("—")
        self.card_spools_install.set_stats("—")
        self.card_field_joints.set_stats("—")
        self.card_supports.set_stats("—")

    # ── FILTERS ──────────────────────────────────────────────
    def _apply_spool_filter(self):
        query = self.txt_spool_search.text().strip().lower()
        status_f = (
            self.cmb_spool_status.currentText()
            if self.cmb_spool_status.currentIndex() > 0 else None
        )

        self.spool_table.setSortingEnabled(False)
        self.spool_table.setRowCount(0)

        for sp in self._local_spools:
            if status_f and sp["status"] != status_f:
                continue
            if query:
                block = " ".join([sp["number"], sp["line"], sp["class"]]).lower()
                if query not in block:
                    continue

            row = self.spool_table.rowCount()
            self.spool_table.insertRow(row)
            self.spool_table.setItem(row, 0, QTableWidgetItem(str(sp["id"])))
            self.spool_table.setItem(row, 1, QTableWidgetItem(sp["number"]))
            self.spool_table.setItem(row, 2, QTableWidgetItem(sp["line"]))
            self.spool_table.setItem(row, 3, QTableWidgetItem(sp["class"]))

            status_item = QTableWidgetItem(sp["status"])
            self._apply_badge_style(status_item, sp["status"])
            self.spool_table.setItem(row, 4, status_item)

            self.spool_table.setItem(row, 5, QTableWidgetItem(sp["installed_date"]))

        self.spool_table.setSortingEnabled(True)

    def _apply_weld_filter(self):
        query = self.txt_weld_search.text().strip().lower()
        status_f = (
            self.cmb_weld_status.currentText()
            if self.cmb_weld_status.currentIndex() > 0 else None
        )

        self.weld_table.setSortingEnabled(False)
        self.weld_table.setRowCount(0)

        for w in self._local_welds:
            if status_f and w["status"] != status_f:
                continue
            if query:
                block = " ".join([w["weld_id"], w["line"], w["welder"]]).lower()
                if query not in block:
                    continue

            row = self.weld_table.rowCount()
            self.weld_table.insertRow(row)
            self.weld_table.setItem(row, 0, QTableWidgetItem(str(w["id"])))
            self.weld_table.setItem(row, 1, QTableWidgetItem(w["weld_id"]))
            self.weld_table.setItem(row, 2, QTableWidgetItem(w["line"]))
            self.weld_table.setItem(row, 3, QTableWidgetItem(w["size"]))

            status_item = QTableWidgetItem(w["status"])
            self._apply_badge_style(status_item, w["status"])
            self.weld_table.setItem(row, 4, status_item)

            self.weld_table.setItem(row, 5, QTableWidgetItem(w["welder"]))

        self.weld_table.setSortingEnabled(True)

    def _apply_badge_style(self, item: QTableWidgetItem, status_txt: str):
        config = STATUS_PALETTE.get(status_txt, DEFAULT_STATUS)
        item.setText(f"{config['icon']} {status_txt}")
        item.setBackground(QBrush(QColor(config["bg"])))
        item.setForeground(QBrush(QColor(config["fg"])))
        f = item.font(); f.setBold(True); item.setFont(f)

    # ── CONTEXT MENUS ────────────────────────────────────────
    def _show_spool_context_menu(self, pos):
        if not self.spool_table.selectedIndexes():
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 16px; color: #0f172a; } "
            "QMenu::item:selected { background: #f1f5f9; color: #2563eb; }"
        )
        act_install = QAction("🟢 Mark as Installed", self)
        act_install.triggered.connect(self._quick_action_mark_installed)
        menu.addAction(act_install)
        menu.addSeparator()

        act_copy_spool = QAction("📋 Copy Spool Identifier", self)
        act_copy_spool.triggered.connect(
            lambda: self._copy_cell_from_selected(self.spool_table, 1)
        )
        menu.addAction(act_copy_spool)

        act_copy_line = QAction("📋 Copy Piping Line No", self)
        act_copy_line.triggered.connect(
            lambda: self._copy_cell_from_selected(self.spool_table, 2)
        )
        menu.addAction(act_copy_line)

        menu.exec(self.spool_table.viewport().mapToGlobal(pos))

    def _show_weld_context_menu(self, pos):
        if not self.weld_table.selectedIndexes():
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #cbd5e1; } "
            "QMenu::item { padding: 6px 16px; }"
        )
        act_copy_weld = QAction("📋 Copy Weld ID", self)
        act_copy_weld.triggered.connect(
            lambda: self._copy_cell_from_selected(self.weld_table, 1)
        )
        menu.addAction(act_copy_weld)

        act_copy_line = QAction("📋 Copy Piping Line No", self)
        act_copy_line.triggered.connect(
            lambda: self._copy_cell_from_selected(self.weld_table, 2)
        )
        menu.addAction(act_copy_line)
        menu.exec(self.weld_table.viewport().mapToGlobal(pos))

    def _copy_cell_from_selected(self, table: QTableWidget, col_idx: int):
        row = table.currentRow()
        if row >= 0:
            item = table.item(row, col_idx)
            if item:
                QApplication.clipboard().setText(item.text().strip())

    def _quick_action_mark_installed(self):
        rows = self.spool_table.selectionModel().selectedRows()
        if not rows:
            return

        spool_ids = []
        spool_names = []
        for r in rows:
            spool_ids.append(int(self.spool_table.item(r.row(), 0).text()))
            spool_names.append(self.spool_table.item(r.row(), 1).text())

        reply = QMessageBox.question(
            self, "Confirm Site Progress Update",
            f"Set erection status to 'Installed' and capture current date as "
            f"Erection Date for {len(spool_ids)} Spool(s)?\n\n"
            f"Spools: {', '.join(spool_names[:5])}"
            + ("..." if len(spool_names) > 5 else ""),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            today_date = datetime.date.today()
            with self.db.session_scope() as s:
                for s_id in spool_ids:
                    spool = s.get(Spool, s_id)
                    if spool:
                        spool.status = "Installed"
                        spool.installed_date = today_date
            self.refresh()
            QMessageBox.information(
                self, "Progress Logged",
                "Selected spools registered successfully as 'Installed'."
            )
        except Exception as e:
            logger.exception("Erection UI quick update failed.")
            QMessageBox.critical(
                self, "Erection Update Failure",
                f"Failed to log site progress:\n{e}"
            )

    # ── EXPORT ───────────────────────────────────────────────
    def _export_spools_csv(self):
        self._export_table_to_csv(self.spool_table, "Site_Erection_Spools_Status")

    def _export_welds_csv(self):
        self._export_table_to_csv(self.weld_table, "Site_Erection_Field_Joints")

    def _export_table_to_csv(self, table: QTableWidget, prefix: str):
        if table.rowCount() == 0:
            QMessageBox.warning(
                self, "No Data",
                "There is no filtered data in the current table grid to export."
            )
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"{prefix}_{timestamp}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Audit Log", default_name, "CSV Files (*.csv)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                headers = [
                    table.horizontalHeaderItem(c).text()
                    for c in range(table.columnCount()) if c != 0
                ]
                writer.writerow(headers)

                for row in range(table.rowCount()):
                    if table.isRowHidden(row):
                        continue
                    row_data = []
                    for col in range(table.columnCount()):
                        if col == 0:
                            continue
                        item = table.item(row, col)
                        row_data.append(item.text().strip() if item else "")
                    writer.writerow(row_data)

            QMessageBox.information(
                self, "Export Complete",
                f"Data exported successfully to:\n{file_path}"
            )
        except Exception as e:
            logger.exception("CSV export aborted.")
            QMessageBox.critical(
                self, "Export Fault",
                f"Could not create target CSV document:\n{e}"
            )