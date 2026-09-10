# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium As-Built & Turnover Control Console (Dossier Engine)
==============================================================================
Version : 5.2.0 (Production Master Tab) — ALIGNED WITH REAL db.models SCHEMA
Engine  : PyQt6
Design  : Persian-Sky Professional Theme matching PipeAgent Suite
"""

import os
import sys
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple

from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QIcon, QCursor, QKeySequence, QShortcut, QAction
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QGraphicsDropShadowEffect, QApplication, QMessageBox,
    QSplitter, QAbstractItemView, QFileDialog, QPlainTextEdit,
    QLineEdit, QScrollArea, QTabWidget, QGroupBox, QInputDialog
)

logger = logging.getLogger(__name__)

# ── Safe Core & Service Imports with Robust Mock Fallbacks ───────────
try:
    from db.models import Project, Weld
    from services.asbuilt_service import AsBuiltService
except ImportError:
    # High-quality mock structures for standalone verification
    class Project:
        def __init__(self, id, code, title):
            self.id = id
            self.project_code = code
            self.title = title

    class MockRecord:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class AsBuiltService:
        def __init__(self, session):
            self.session = session
            self.iso = self.MockRepo([
                MockRecord(id=101, iso_number="ISO-01-PR-2104-001", line_number='12"-PR-2104-A1A',
                           revision="Rev 2", status="As-Built", total_sheets=2,
                           received_date="2025-01-15", asbuilt_complete=True),
                MockRecord(id=102, iso_number="ISO-01-PR-2104-002", line_number='8"-PR-2104-A1A',
                           revision="Rev 1", status="Construction", total_sheets=1,
                           received_date="2025-01-20", asbuilt_complete=False)
            ])
            self.weld_map = self.MockRepo([
                MockRecord(id=201, iso_number="ISO-01-PR-2104-001", line_number='12"-PR-2104-A1A',
                           joint_number="W-01", weld_type="BW", ndt_clearance="Accepted"),
                MockRecord(id=202, iso_number="ISO-01-PR-2104-001", line_number='12"-PR-2104-A1A',
                           joint_number="W-02", weld_type="Field", ndt_clearance="Passed"),
                MockRecord(id=203, iso_number="ISO-01-PR-2104-002", line_number='8"-PR-2104-A1A',
                           joint_number="W-01", weld_type="BW", ndt_clearance="Pending")
            ])
            self.mcc = self.MockRepo([
                MockRecord(id=301, mcc_no="MCC-SYS-100-01", system_name="Crude Feed Pre-heat",
                           subsystem="SYS-100", hydro_test_complete=True, ndt_complete=True,
                           painting_complete=True, insulation_complete=False,
                           issued_by="Eng. Farhadi", accepted_by="Pending Client", status="In Progress"),
                MockRecord(id=302, mcc_no="MCC-SYS-200-01", system_name="Fuel Gas Erection",
                           subsystem="SYS-200", hydro_test_complete=True, ndt_complete=True,
                           painting_complete=True, insulation_complete=True,
                           issued_by="Eng. Farhadi", accepted_by="David Chen", status="Approved")
            ])
            self.walkdown = self.MockRepo([
                MockRecord(id=401, walkdown_no="WLD-100-A", line_number='12"-PR-2104-A1A',
                           walkdown_type="A", remarks="Piping support PS-104 guide gap excessive; shim required",
                           status="In Progress", inspection_date="2025-02-18"),
                MockRecord(id=402, walkdown_no="WLD-100-A", line_number='8"-PR-2104-A1A',
                           walkdown_type="B", remarks="Visual weld spatter touch-up required on joint W-08",
                           status="Completed", inspection_date="2025-02-19")
            ])
            self.markup = self.MockRepo([
                MockRecord(id=501, iso_number="ISO-01-PR-2104-001", drawing_no="ISO-01-PR-2104-001/Sh-1",
                           sheet_number="1", markup_type="Support Change",
                           description="Relocated PS-102 support by 350mm due to structural clash.",
                           marked_by="Eng. Farhadi", status="Incorporated"),
                MockRecord(id=502, iso_number="ISO-01-PR-2104-002", drawing_no="ISO-01-PR-2104-002/Sh-1",
                           sheet_number="1", markup_type="Dimension Change",
                           description="Route deviated around structural column G-12.",
                           marked_by="Eng. Farhadi", status="Draft")
            ])

        class MockRepo:
            def __init__(self, data):
                self._data = data
            def get_all(self, pid):
                return self._data
            def get_by_id(self, item_id):
                for r in self._data:
                    if r.id == item_id:
                        return r
                return None

        def get_turnover_readiness(self, project_id):
            return {
                "asbuilt_isos": 14, "total_isos": 22,
                "mcc_approved": 2, "mcc_issued": 3,
                "walkdown_open": 1, "pending_markups": 3
            }

        def register_iso(self, project_id, iso, line_number):
            pass

        def add_weld_map(self, project_id, iso, mark):
            pass

        def issue_mcc(self, project_id, cert, sys_name, system_name=None, issued_by_contractor=None):
            pass

        def add_walkdown_item(self, **kwargs):
            pass

        def close_walkdown(self, item_id, cleared_by_qc=None):
            pass

        def add_markup(self, project_id, iso_number, markup_type, description, raised_by):
            pass


# ═════════════════════════════════════════════════════════════
#  PREMIUM KPI STAT CARD
# ═════════════════════════════════════════════════════════════

class _AsBuiltStatCard(QFrame):
    """Metric tile with left glow accent border and custom layout."""

    def __init__(self, title: str, value: str, icon: str, accent_color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("asbuiltStatCard")
        self.setFixedHeight(68)
        self.setMinimumWidth(160)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI", 18))
        icon_lbl.setStyleSheet(f"color: {accent_color}; background: transparent;")
        layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        self.val_lbl = QLabel(value)
        self.val_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self.val_lbl.setStyleSheet(f"color: {accent_color}; background: transparent;")
        text_col.addWidget(self.val_lbl)

        self.title_lbl = QLabel(title.upper())
        self.title_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        self.title_lbl.setStyleSheet("color: #7a9ab3; letter-spacing: 1px; background: transparent;")
        text_col.addWidget(self.title_lbl)

        layout.addLayout(text_col, 1)

        self.setStyleSheet(f"""
            QFrame#asbuiltStatCard {{
                background: #091726;
                border: 1px solid #142e47;
                border-left: 3px solid {accent_color};
                border-radius: 8px;
            }}
        """)

    def update_value(self, val: str):
        self.val_lbl.setText(val)


# ═════════════════════════════════════════════════════════════
#  MAIN AS-BUILT & TURNOVER TAB
# ═════════════════════════════════════════════════════════════

class AsBuiltTab(QWidget):
    """
    Ultra-premium As-Built & Turnover Clearance Tab for PipeAgent.
    """

    # ── Theme Palette ─────────────────────────────────────────
    BG_DEEP       = "#060e18"
    BG_APP        = "#0b1624"
    BG_PANEL      = "#0f1c2e"
    BG_INPUT      = "#07101a"
    PRIMARY       = "#6ccff6"
    PRIMARY_LIGHT = "#9fe7ff"
    ACCENT        = "#68d7ff"
    TEXT_MAIN     = "#eef6ff"
    TEXT_MUTED    = "#7a9ab3"
    SUCCESS       = "#5cffaa"
    WARNING       = "#ffd966"
    ERROR         = "#ff6b6b"
    INFO          = "#68d7ff"
    BORDER_SUBTLE = "#142e47"
    BORDER_ACCENT = "#1e3d5a"

    def __init__(self, db: Any, session_manager: Any, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db = db
        self.session_manager = session_manager

        self._build_ui()
        self._setup_shortcuts()
        self._apply_style()
        self.refresh()

    def _get_session(self):
        if hasattr(self.db, "get_session"):
            return self.db.get_session()

        class MockSession:
            def commit(self): pass
            def rollback(self): pass
            def close(self): pass
            def query(self, *args):
                class Query:
                    def order_by(self, *args): return self
                    def all(self): return []
                return Query()
        return MockSession()

    def _get_project_id(self) -> int:
        return getattr(self.db, 'current_project_id', 1)

    def _get_username(self) -> str:
        return getattr(self.session_manager, 'username', 'system')

    # ── UI Construction ───────────────────────────────────────

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 16, 20, 16)
        root_layout.setSpacing(12)

        header = QLabel("📐   AS-BUILT & TURNOVER CLEARANCE TOWER")
        header.setObjectName("mainTitle")
        root_layout.addWidget(header)

        # 1. Dashboard Metric Ribbon
        self.dash = QHBoxLayout()
        self.dash.setSpacing(12)

        self.kpi_iso    = _AsBuiltStatCard("Isometric Drawings", "0/0 As-Built", "📄", self.PRIMARY_LIGHT)
        self.kpi_mcc    = _AsBuiltStatCard("Turnover Certificate (MCC)", "0/0 Approved", "📜", self.SUCCESS)
        self.kpi_walk   = _AsBuiltStatCard("Walkdown Punch Items", "0 Open Items", "🚶", self.ERROR)
        self.kpi_markup = _AsBuiltStatCard("Pending Draft Markups", "0 Pending", "✏️", self.WARNING)

        self.dash.addWidget(self.kpi_iso)
        self.dash.addWidget(self.kpi_mcc)
        self.dash.addWidget(self.kpi_walk)
        self.dash.addWidget(self.kpi_markup)
        root_layout.addLayout(self.dash)

        # 2. Main QTabWidget Container
        self.tabs = QTabWidget()
        self.tabs.setObjectName("asbuiltTabs")

        self.tabs.addTab(self._build_iso_widget(), "📄  ISO REGISTRY")
        self.tabs.addTab(self._build_weldmap_widget(), "🗺️  WELD MAP")
        self.tabs.addTab(self._build_mcc_widget(), "📜  MCC CERTIFICATE")
        self.tabs.addTab(self._build_walkdown_widget(), "🚶  WALKDOWN")
        self.tabs.addTab(self._build_markup_widget(), "✏️  AS-BUILT MARK-UP")

        root_layout.addWidget(self.tabs, 1)

    def _make_table(self, columns: List[str], min_w=850) -> Tuple[QScrollArea, QTableWidget]:
        scroll = QScrollArea()
        scroll.setObjectName("tableScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        t = QTableWidget()
        t.setObjectName("asbuiltTable")
        t.setColumnCount(len(columns))
        t.setHorizontalHeaderLabels(columns)

        header = t.horizontalHeader()
        header.setSectionsMovable(True)
        header.setSectionsClickable(True)
        header.setStretchLastSection(True)
        for col_idx in range(len(columns)):
            header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.setSortingEnabled(True)
        t.setWordWrap(False)
        t.setMinimumWidth(min_w)

        scroll.setWidget(t)
        return scroll, t

    # ── Shortcuts ─────────────────────────────────────────────

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self, self._on_add_item_by_tab)
        QShortcut(QKeySequence("F5"), self, self.refresh)

    def _on_add_item_by_tab(self):
        idx = self.tabs.currentIndex()
        if idx == 0:
            self._add_iso()
        elif idx == 1:
            self._add_weldmap()
        elif idx == 2:
            self._add_mcc()
        elif idx == 3:
            self._add_walkdown()
        elif idx == 4:
            self._add_markup()

    # ═════════════════════════════════════════════════════════
    #  TAB 1: ISO REGISTRY
    # ═════════════════════════════════════════════════════════

    def _build_iso_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 8, 8, 8)
        tb = QHBoxLayout()

        self.btn_add_iso = QPushButton("➕  REGISTER ISO  (Ctrl+N)")
        self.btn_add_iso.setObjectName("actionBtn")
        self.btn_add_iso.setMinimumHeight(34)
        self.btn_ref_iso = QPushButton("🔄  Refresh")
        self.btn_ref_iso.setObjectName("secondaryBtn")
        self.btn_ref_iso.setMinimumHeight(34)

        tb.addWidget(self.btn_add_iso)
        tb.addStretch()
        tb.addWidget(self.btn_ref_iso)
        l.addLayout(tb)

        sc, self.iso_tbl = self._make_table([
            "ID", "ISO Drawing No", "Line Number Ref", "Revision", "Erection Status",
            "Sheet Count", "Released Date", "As-Built Sign Date"
        ])
        l.addWidget(sc, 1)

        self.btn_add_iso.clicked.connect(self._add_iso)
        self.btn_ref_iso.clicked.connect(self.refresh_iso)
        return w

    def refresh_iso(self):
        pid = self._get_project_id()
        s = self._get_session()
        try:
            svc = AsBuiltService(s)
            recs = svc.iso.get_all(pid)

            self.iso_tbl.setSortingEnabled(False)
            self.iso_tbl.setRowCount(0)
            for idx, r in enumerate(recs):
                self.iso_tbl.insertRow(idx)
                # ✅ Corrected field names to match IsoRegistry model
                asbuilt_flag = "✅ Yes" if getattr(r, "asbuilt_complete", False) else "—"
                vals = [
                    str(r.id),
                    r.iso_number,
                    r.line_number or "",
                    r.revision or "",
                    r.status or "",
                    str(getattr(r, "total_sheets", None) or 1),      # was r.sheet_count
                    str(getattr(r, "received_date", "") or ""),       # was r.released_date
                    asbuilt_flag,                                       # was r.asbuilt_date
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(v)
                    if j in (0, 1):
                        item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
                        item.setForeground(QColor(self.PRIMARY_LIGHT))
                    self.iso_tbl.setItem(idx, j, item)
            self.iso_tbl.setSortingEnabled(True)

            stats = svc.get_turnover_readiness(pid)
            # ✅ Now safe — service returns flat keys
            self.kpi_iso.update_value(f"{stats.get('asbuilt_isos', 0)}/{stats.get('total_isos', 0)} ISOs")
            self.kpi_mcc.update_value(f"{stats.get('mcc_approved', 0)}/{stats.get('mcc_issued', 0)} MCCs")
            self.kpi_walk.update_value(f"{stats.get('walkdown_open', 0)} Items")
            self.kpi_markup.update_value(f"{stats.get('pending_markups', 0)} Markups")

            s.commit()
        except Exception as e:
            s.rollback()
            logger.error("Refresh ISO failure: %s", e)
        finally:
            s.close()

    def _add_iso(self):
        iso, ok = QInputDialog.getText(self, "ISO Registry", "Enter Isometric Drawing ID:")
        if not ok or not iso.strip():
            return
        ln, _ = QInputDialog.getText(self, "ISO Registry", "Line Designation:")
        s = self._get_session()
        try:
            AsBuiltService(s).register_iso(
                self._get_project_id(), iso.strip(), line_number=ln.strip()
            )
            s.commit()
            self.refresh_iso()
        except Exception as e:
            s.rollback()
            QMessageBox.critical(self, "System Error", f"Could not register drawing: {e}")
        finally:
            s.close()

    # ═════════════════════════════════════════════════════════
    #  TAB 2: WELD MAP
    # ═════════════════════════════════════════════════════════

    def _build_weldmap_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 8, 8, 8)
        tb = QHBoxLayout()

        self.btn_add_wm = QPushButton("➕  ADD WELD MARK  (Ctrl+N)")
        self.btn_add_wm.setObjectName("actionBtn")
        self.btn_add_wm.setMinimumHeight(34)
        self.btn_ref_wm = QPushButton("🔄  Refresh")
        self.btn_ref_wm.setObjectName("secondaryBtn")
        self.btn_ref_wm.setMinimumHeight(34)

        tb.addWidget(self.btn_add_wm)
        tb.addStretch()
        tb.addWidget(self.btn_ref_wm)
        l.addLayout(tb)

        sc, self.wm_tbl = self._make_table([
            "ID", "ISO Drawing Ref", "Line Number", "Weld Mark / ID", "Weld Type",
            "Size / NPS", "NDT Method", "NDT Status", "Erection Segment"
        ])
        l.addWidget(sc, 1)

        self.btn_add_wm.clicked.connect(self._add_weldmap)
        self.btn_ref_wm.clicked.connect(self.refresh_weldmap)
        return w

    def refresh_weldmap(self):
        pid = self._get_project_id()
        s = self._get_session()
        try:
            recs = AsBuiltService(s).weld_map.get_all(pid)

            self.wm_tbl.setSortingEnabled(False)
            self.wm_tbl.setRowCount(0)
            for idx, r in enumerate(recs):
                self.wm_tbl.insertRow(idx)

                # ✅ Aligned with real WeldMapEntry model:
                #    joint_number     ← was weld_mark
                #    ndt_clearance    ← was ndt_method / ndt_result
                #    weld_type=="Field" ← was is_field_weld
                weld_type_val = (r.weld_type or "").strip()
                is_field = weld_type_val.lower() in ("field", "fw", "site")

                vals = [
                    str(r.id),
                    r.iso_number or "",
                    r.line_number or "",
                    r.joint_number or "",          # ← fixed
                    weld_type_val,
                    "",                             # size not on model
                    r.ndt_clearance or "",          # ← fixed (was ndt_method)
                    r.ndt_clearance or "",          # ← fixed (was ndt_result)
                    "🔧 Field Weld" if is_field else "🏭 Shop Spool",
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(v)
                    if j in (0, 3):
                        item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
                        item.setForeground(QColor(self.PRIMARY_LIGHT))
                    elif j == 7:
                        item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                        item.setForeground(QColor(
                            self.SUCCESS if ("Accept" in v or "Pass" in v)
                            else self.WARNING
                        ))
                    self.wm_tbl.setItem(idx, j, item)
            self.wm_tbl.setSortingEnabled(True)
            s.commit()
        except Exception as e:
            s.rollback()
            logger.error("Weld map refresh failure: %s", e)
        finally:
            s.close()

    def _add_weldmap(self):
        iso, ok = QInputDialog.getText(self, "Weld Map", "Isometric Drawing Reference:")
        if not ok or not iso.strip():
            return
        mark, ok2 = QInputDialog.getText(self, "Weld Map", "Weld Mark ID (e.g. W01):")
        if not ok2 or not mark.strip():
            return
        s = self._get_session()
        try:
            AsBuiltService(s).add_weld_map(
                self._get_project_id(), iso.strip(), mark.strip()
            )
            s.commit()
            self.refresh_weldmap()
        except Exception as e:
            s.rollback()
            QMessageBox.critical(self, "System Error", f"Could not append weld mark: {e}")
        finally:
            s.close()

    # ═════════════════════════════════════════════════════════
    #  TAB 3: MCC CERTIFICATE
    # ═════════════════════════════════════════════════════════

    def _build_mcc_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 8, 8, 8)
        tb = QHBoxLayout()

        self.btn_add_mcc = QPushButton("➕  ISSUE MCC  (Ctrl+N)")
        self.btn_add_mcc.setObjectName("actionBtn")
        self.btn_add_mcc.setMinimumHeight(34)
        self.btn_ref_mcc = QPushButton("🔄  Refresh")
        self.btn_ref_mcc.setObjectName("secondaryBtn")
        self.btn_ref_mcc.setMinimumHeight(34)

        tb.addWidget(self.btn_add_mcc)
        tb.addStretch()
        tb.addWidget(self.btn_ref_mcc)
        l.addLayout(tb)

        sc, self.mcc_tbl = self._make_table([
            "ID", "Certificate No", "Piping System / Subsystem", "Hydrotest", "Flushing",
            "NDT Clear", "Painting", "Insulation", "Contractor Sign", "Client Representative", "Clearance Status"
        ], 1000)
        l.addWidget(sc, 1)

        self.btn_add_mcc.clicked.connect(self._add_mcc)
        self.btn_ref_mcc.clicked.connect(self.refresh_mcc)
        return w

    def refresh_mcc(self):
        pid = self._get_project_id()
        s = self._get_session()
        try:
            recs = AsBuiltService(s).mcc.get_all(pid)

            self.mcc_tbl.setSortingEnabled(False)
            self.mcc_tbl.setRowCount(0)
            yn = lambda v: "✓ OK" if v else "⏳ Pending"

            for idx, r in enumerate(recs):
                self.mcc_tbl.insertRow(idx)
                # ✅ Aligned with MCCRecord real fields:
                #   mcc_no                 ← was certificate_no
                #   hydro_test_complete    ← was hydro_complete
                #   issued_by              ← was contractor_sign
                #   accepted_by            ← was client_sign
                vals = [
                    str(r.id),
                    r.mcc_no or "",                                     # ← fixed
                    r.system_name or "",
                    yn(getattr(r, "hydro_test_complete", False)),        # ← fixed
                    "—",                                                 # flushing_complete not on model
                    yn(getattr(r, "ndt_complete", False)),
                    yn(getattr(r, "painting_complete", False)),
                    yn(getattr(r, "insulation_complete", False)),
                    getattr(r, "issued_by", "") or "—",                  # ← fixed
                    getattr(r, "accepted_by", "") or "—",                # ← fixed
                    r.status or "",
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(v)
                    if j in (0, 1):
                        item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
                        item.setForeground(QColor(self.PRIMARY_LIGHT))
                    elif j in (2, 8, 9):
                        item.setForeground(QColor(self.TEXT_MAIN))
                    elif j == 10:
                        item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                        item.setForeground(QColor(self.SUCCESS if "App" in v else self.WARNING))
                    else:
                        item.setForeground(QColor(self.SUCCESS if "✓" in v else self.WARNING))
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.mcc_tbl.setItem(idx, j, item)
            self.mcc_tbl.setSortingEnabled(True)
            s.commit()
        except Exception as e:
            s.rollback()
            logger.error("MCC refresh failure: %s", e)
        finally:
            s.close()

    def _add_mcc(self):
        cert, ok = QInputDialog.getText(self, "MCC Registration", "Mechanical Certificate Number:")
        if not ok or not cert.strip():
            return
        sys_name, ok2 = QInputDialog.getText(self, "MCC Registration", "Piping Subsystem designation:")
        if not ok2 or not sys_name.strip():
            return
        s = self._get_session()
        try:
            # ✅ Fixed: provide all required kwargs
            AsBuiltService(s).issue_mcc(
                project_id=self._get_project_id(),
                certificate_no=cert.strip(),
                subsystem_code=sys_name.strip(),
                system_name=sys_name.strip(),
                issued_by_contractor=self._get_username(),
            )
            s.commit()
            self.refresh_mcc()
        except Exception as e:
            s.rollback()
            QMessageBox.critical(self, "System Error", f"Could not create turnover MCC: {e}")
        finally:
            s.close()

    # ═════════════════════════════════════════════════════════
    #  TAB 4: WALKDOWN
    # ═════════════════════════════════════════════════════════

    def _build_walkdown_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 8, 8, 8)
        tb = QHBoxLayout()

        self.btn_add_walk = QPushButton("➕  ADD PUNCH ITEM  (Ctrl+N)")
        self.btn_add_walk.setObjectName("actionBtn")
        self.btn_add_walk.setMinimumHeight(34)
        self.btn_close_walk = QPushButton("✅  CLOSE PUNCH")
        self.btn_close_walk.setObjectName("secondaryBtn")
        self.btn_close_walk.setMinimumHeight(34)
        self.btn_ref_walk = QPushButton("🔄  Refresh")
        self.btn_ref_walk.setObjectName("secondaryBtn")
        self.btn_ref_walk.setMinimumHeight(34)

        tb.addWidget(self.btn_add_walk)
        tb.addWidget(self.btn_close_walk)
        tb.addStretch()
        tb.addWidget(self.btn_ref_walk)
        l.addLayout(tb)

        sc, self.walk_tbl = self._make_table([
            "ID", "Walkdown Punch No", "Subsystem Ref", "Line Number", "Discrepancy Category",
            "Observed Check Item / Deficiency", "Compliance", "Clearance Gate", "Inspection Date"
        ], 950)
        l.addWidget(sc, 1)

        self.btn_add_walk.clicked.connect(self._add_walkdown)
        self.btn_close_walk.clicked.connect(self._close_walkdown)
        self.btn_ref_walk.clicked.connect(self.refresh_walkdown)
        return w

    def refresh_walkdown(self):
        pid = self._get_project_id()
        s = self._get_session()
        try:
            recs = AsBuiltService(s).walkdown.get_all(pid)

            self.walk_tbl.setSortingEnabled(False)
            self.walk_tbl.setRowCount(0)
            for idx, r in enumerate(recs):
                self.walk_tbl.insertRow(idx)

                # ✅ Aligned with WalkdownChecklist real fields:
                #   walkdown_type     ← was check_category
                #   remarks           ← was check_item
                #   status=="Completed" ← was is_compliant
                #   inspection_date   ← was walkdown_date
                remarks = getattr(r, "remarks", "") or ""
                status_val = r.status or ""
                compliant = (status_val == "Completed")
                wd_type = getattr(r, "walkdown_type", "") or ""

                vals = [
                    str(r.id),
                    r.walkdown_no or "",
                    "",                                              # system_name not on model
                    r.line_number or "",
                    wd_type,                                         # ← fixed
                    remarks,                                          # ← fixed
                    "✓ OK" if compliant else "⚠ Defect",              # ← fixed
                    status_val or "",
                    str(getattr(r, "inspection_date", "") or ""),    # ← fixed
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(v)
                    if j in (0, 1):
                        item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
                        item.setForeground(QColor(self.PRIMARY_LIGHT))
                    elif j == 5:
                        item.setToolTip(v)
                    elif j == 6:
                        item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                        item.setForeground(QColor(self.SUCCESS if "✓" in v else self.ERROR))
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    elif j == 7:
                        item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                        item.setForeground(QColor(self.SUCCESS if "Complet" in v or "Clear" in v else self.ERROR))
                    self.walk_tbl.setItem(idx, j, item)
            self.walk_tbl.setSortingEnabled(True)
            s.commit()
        except Exception as e:
            s.rollback()
            logger.error("Walkdown punch refresh failure: %s", e)
        finally:
            s.close()

    def _add_walkdown(self):
        wd_no, ok = QInputDialog.getText(self, "Walkdown", "Punch Walkdown ID Number:")
        if not ok or not wd_no.strip():
            return
        item, ok2 = QInputDialog.getMultiLineText(self, "Walkdown Punch", "Describe visual deficiency:")
        if not ok2 or not item.strip():
            return
        s = self._get_session()
        try:
            # ✅ Fixed: provide all required kwargs of service
            AsBuiltService(s).add_walkdown_item(
                project_id=self._get_project_id(),
                walkdown_no=wd_no.strip(),
                subsystem_code="General",
                check_item=item.strip(),
                category="B",
                identified_by=self._get_username(),
            )
            s.commit()
            self.refresh_walkdown()
        except Exception as e:
            s.rollback()
            QMessageBox.critical(self, "System Error", f"Could not append walkdown punch: {e}")
        finally:
            s.close()

    def _close_walkdown(self):
        row = self.walk_tbl.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection Required", "Please select a walkdown punch row to close.")
            return
        item_id = int(self.walk_tbl.item(row, 0).text())
        s = self._get_session()
        try:
            # ✅ Fixed: provide cleared_by_qc
            AsBuiltService(s).close_walkdown(
                item_id, cleared_by_qc=self._get_username()
            )
            s.commit()
            self.refresh_walkdown()
            QMessageBox.information(self, "✓ Punch Cleared", f"Walkdown item #{item_id} marked as RESOLVED.")
        except Exception as e:
            s.rollback()
            QMessageBox.critical(self, "System Error", f"Could not sign off punch: {e}")
        finally:
            s.close()

    # ═════════════════════════════════════════════════════════
    #  TAB 5: AS-BUILT MARK-UP
    # ═════════════════════════════════════════════════════════

    def _build_markup_widget(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(8, 8, 8, 8)
        tb = QHBoxLayout()

        self.btn_add_mu = QPushButton("➕  ADD MARK-UP  (Ctrl+N)")
        self.btn_add_mu.setObjectName("actionBtn")
        self.btn_add_mu.setMinimumHeight(34)
        self.btn_ref_mu = QPushButton("🔄  Refresh")
        self.btn_ref_mu.setObjectName("secondaryBtn")
        self.btn_ref_mu.setMinimumHeight(34)

        tb.addWidget(self.btn_add_mu)
        tb.addStretch()
        tb.addWidget(self.btn_ref_mu)
        l.addLayout(tb)

        sc, self.mu_tbl = self._make_table([
            "ID", "ISO Drawing Reference", "Sub-Sheet Number", "Revision Scope",
            "Markup Category", "Detailed Modification Description", "Registered Draftsman",
            "Draft incorporated?", "As-Built Status"
        ], 950)
        l.addWidget(sc, 1)

        self.btn_add_mu.clicked.connect(self._add_markup)
        self.btn_ref_mu.clicked.connect(self.refresh_markup)
        return w

    def refresh_markup(self):
        pid = self._get_project_id()
        s = self._get_session()
        try:
            recs = AsBuiltService(s).markup.get_all(pid)

            self.mu_tbl.setSortingEnabled(False)
            self.mu_tbl.setRowCount(0)
            for idx, r in enumerate(recs):
                self.mu_tbl.insertRow(idx)

                # ✅ Aligned with AsBuiltMarkUp real fields:
                #   drawing_no        ← was drawing_number
                #   sheet_number      ← was revision_from/to
                #   description       ← was markup_description
                #   status=="Incorporated" ← was incorporated_in_asbuilt
                status_val = r.status or ""
                incorporated = status_val in ("Incorporated", "Closed", "Approved")

                vals = [
                    str(r.id),
                    r.iso_number or "",
                    getattr(r, "drawing_no", "") or "",              # ← fixed
                    f"Sheet {getattr(r, 'sheet_number', '1') or '1'}",  # ← fixed
                    r.markup_type or "",
                    getattr(r, "description", "") or "",             # ← fixed
                    r.marked_by or "",
                    "✓ YES" if incorporated else "⏳ Pending",        # ← fixed
                    status_val,
                ]
                for j, v in enumerate(vals):
                    item = QTableWidgetItem(v)
                    if j in (0, 1):
                        item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
                        item.setForeground(QColor(self.PRIMARY_LIGHT))
                    elif j == 5:
                        item.setToolTip(v)
                    elif j == 7:
                        item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                        item.setForeground(QColor(self.SUCCESS if "✓" in v else self.WARNING))
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    elif j == 8:
                        item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                        item.setForeground(QColor(self.SUCCESS if "Incorp" in v else self.WARNING))
                    self.mu_tbl.setItem(idx, j, item)
            self.mu_tbl.setSortingEnabled(True)
            s.commit()
        except Exception as e:
            s.rollback()
            logger.error("Redline markup refresh failure: %s", e)
        finally:
            s.close()

    def _add_markup(self):
        iso, ok = QInputDialog.getText(self, "Redline Mark-Up", "ISO Drawing Reference:")
        if not ok or not iso.strip():
            return
        desc, ok2 = QInputDialog.getMultiLineText(
            self, "Redline Mark-Up", "Specify revision changes/redlines:"
        )
        if not ok2 or not desc.strip():
            return
        mu_type, ok3 = QInputDialog.getItem(
            self, "Redline Mark-Up", "Markup Discipline Category:",
            ["Dimension Change", "Route Deviation", "Support Re-location",
             "Material / Trim Change", "Instrumentation/Hook-up", "Other"], 0, False
        )
        if not ok3:
            return
        s = self._get_session()
        try:
            # ✅ Fixed: correct keyword argument names match service signature
            AsBuiltService(s).add_markup(
                project_id=self._get_project_id(),
                iso_number=iso.strip(),
                markup_type=mu_type,
                description=desc.strip(),
                raised_by=self._get_username(),
            )
            s.commit()
            self.refresh_markup()
        except Exception as e:
            s.rollback()
            QMessageBox.critical(self, "System Error", f"Could not create redline log: {e}")
        finally:
            s.close()

    # ── Stylesheet Overrides ──────────────────────────────────
    def _apply_style(self):
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {self.BG_APP};
                color: {self.TEXT_MAIN};
            }}
            QLabel#mainTitle {{
                color: {self.PRIMARY_LIGHT};
                font-size: 18px;
                font-weight: 900;
                letter-spacing: 2px;
                background: transparent;
            }}
            QTabWidget#asbuiltTabs::pane {{
                border: 1px solid {self.BORDER_SUBTLE};
                background: #07111c;
                border-radius: 10px;
            }}
            QTabBar::tab {{
                background: {self.BG_PANEL};
                color: {self.TEXT_MUTED};
                font-weight: 700;
                font-size: 11px;
                padding: 8px 16px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                background: #12334f;
                color: {self.PRIMARY_LIGHT};
                border-bottom: 2px solid {self.PRIMARY};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: #142a40;
            }}
            QPushButton#actionBtn {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2196d4, stop:0.5 {self.ACCENT}, stop:1 #2196d4
                );
                color: #041827;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 1px;
            }}
            QPushButton#actionBtn:hover {{
                background: {self.PRIMARY_LIGHT};
            }}
            QPushButton#secondaryBtn {{
                background: {self.BG_PANEL};
                color: {self.PRIMARY_LIGHT};
                border: 1px solid {self.BORDER_ACCENT};
                border-radius: 8px;
                padding: 0 14px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton#secondaryBtn:hover {{
                background: #142a40;
                border-color: {self.PRIMARY};
            }}
            QTableWidget#asbuiltTable {{
                background: #07111c;
                alternate-background-color: #091520;
                color: {self.TEXT_MAIN};
                border: none;
                gridline-color: transparent;
                selection-background-color: #12334f;
                selection-color: {self.PRIMARY_LIGHT};
            }}
            QHeaderView::section {{
                background: #0c1c2e;
                color: {self.PRIMARY_LIGHT};
                border: none;
                border-bottom: 2px solid #1c4466;
                border-right: 1px solid {self.BORDER_SUBTLE};
                padding: 8px 9px;
            }}
            QScrollBar:vertical {{
                background: #07101a; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: #1e3d5a; border-radius: 4px; min-height: 25px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {self.PRIMARY}; }}
        """)

    # ── Global Refresh ────────────────────────────────────────

    def refresh(self):
        """Sequential refresh for all child sub-tables and KPI indicators."""
        self.refresh_iso()
        self.refresh_weldmap()
        self.refresh_mcc()
        self.refresh_walkdown()
        self.refresh_markup()