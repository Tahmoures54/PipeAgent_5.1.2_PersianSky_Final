# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Document Control Center (DCC)
═══════════════════════════════════════════════════════════
Version : 5.0 (Refactored, hardened, production-ready)
Engine  : PyQt6
Design  : Cinematic dark-tech theme matching PipeAgent Suite

Fixes in this revision
──────────────────────
🔴 P0  Sort-safe selection : document stored in QTableWidgetItem.UserRole
                           (previously selecting a row after sorting could
                            return a DIFFERENT document, risking wrong-
                            document bump/delete → data corruption)
🔴 P0  GlowLineEdit        : no longer calls deleteLater() on a C++ object
                           that Qt has already deleted → no more
                           "wrapped C/C++ object has been deleted"
🟠 P1  DocumentRepository  : single source of truth for list/add/update/
                           delete; write-back hooks ready for the DB layer
🟠 P1  Delete shortcut     : bound to the table only (WidgetShortcut), so
                           pressing Delete inside the search field no longer
                           triggers document deletion
🟡 P2  Card border         : replaced invalid `border: ... qlineargradient`
                           with a solid color + glow shadow (QSS does not
                           support gradients in `border`)
🟡 P2  _clear_inspector    : now driven by a declared label spec table,
                           not by fragile string splitting
🟡 P2  ParticleField       : count 32 → 16, tick 60ms → 110ms, only paints
                           when the widget is visible (CPU/GPU friendly)
🟢 P3  Duplicate check     : existing doc numbers stored in a set() → O(1)
🟢 P3  Document IDs        : every record now has a stable `doc_id`
🟢 P3  Filter pipeline     : area combo refresh, KPI, and table re-population
                           all flow through DocumentRepository
"""

from __future__ import annotations

import os
import sys
import csv
import random
import uuid
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Iterable

from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRect, QSize,
    QPropertyAnimation, QEasingCurve, pyqtSignal, QUrl
)
from PyQt6.QtGui import (
    QFont, QPixmap, QPainter, QColor, QLinearGradient,
    QRadialGradient, QPen, QBrush, QPainterPath,
    QMouseEvent, QKeyEvent, QIcon, QCursor, QAction,
    QShortcut, QKeySequence
)
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QGraphicsDropShadowEffect, QWidget,
    QApplication, QMessageBox, QSplitter, QAbstractItemView,
    QFileDialog, QMenu, QScrollArea, QSizePolicy, QCheckBox
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#  UTILITIES
# ════════════════════════════════════════════════════════════════

def _new_doc_id() -> str:
    """Short, collision-resistant document identifier."""
    return uuid.uuid4().hex[:12]


def _next_revision(current: str) -> str:
    """
    Compute the next revision string.

    'Rev 0'  → 'Rev 1'   |   'Rev 2'  → 'Rev 3'
    'Rev A'  → 'Rev B'   |   'Rev Z'  → 'Rev Z.1'
    anything else        → '<current>.1'
    """
    if not current:
        return "Rev 0"

    value = current.replace("Rev ", "").strip() if "Rev " in current else current.strip()

    if value.isdigit():
        return f"Rev {int(value) + 1}"

    if len(value) == 1 and value.isalpha():
        nxt = chr(ord(value.upper()) + 1)
        if nxt <= "Z":
            return f"Rev {nxt}"
        return f"Rev {value}.1"

    return f"Rev {value}.1" if not value.endswith(".1") else f"Rev {value}"


# ════════════════════════════════════════════════════════════════
#  DOCUMENT REPOSITORY — single source of truth
# ════════════════════════════════════════════════════════════════

class DocumentRepository:
    """
    In-memory store with optional database write-back.

    The DCC talks only to this class; it never mutates raw lists.
    Persistence methods check for the existence of the corresponding
    method on the DB object, so hooking up a real backend later
    requires no changes to the UI code.
    """

    def __init__(self, db=None):
        self.db = db
        self._records: List[Dict[str, Any]] = []
        self._load()

    # ── Loading ───────────────────────────────────────────────
    def _load(self):
        if self.db and hasattr(self.db, "get_all_documents"):
            try:
                db_docs = self.db.get_all_documents()
                if db_docs:
                    for d in db_docs:
                        d.setdefault("doc_id", _new_doc_id())
                    self._records = list(db_docs)
                    logger.info("Loaded %d documents from database", len(db_docs))
                    return
            except Exception as e:
                logger.warning("Failed to load documents from database: %s", e)

        self._records = self._build_sample_data()
        logger.info("Loaded %d sample documents", len(self._records))

    @staticmethod
    def _build_sample_data() -> List[Dict[str, Any]]:
        return [
            {
                "doc_id": "D001",
                "doc_no": "ISO-01-PR-2104-001",
                "title": '12"-PR-2104-A1A • Crude Feed From V-101 To Heater H-101',
                "type": "Isometric (ISO)",
                "rev": "Rev 2",
                "status": "IFC",
                "area": "Unit 100",
                "date": "2025-02-10",
                "author": "Eng. Rezaei",
                "joints": 34,
                "spools": 8,
            },
            {
                "doc_id": "D002",
                "doc_no": "ISO-01-PR-2104-002",
                "title": '8"-PR-2104-A1A • Heater H-101 Convection Bypass Line',
                "type": "Isometric (ISO)",
                "rev": "Rev 1",
                "status": "IFC",
                "area": "Unit 100",
                "date": "2025-02-14",
                "author": "Eng. Rezaei",
                "joints": 22,
                "spools": 5,
            },
            {
                "doc_id": "D003",
                "doc_no": "PID-00-104-DWG-01",
                "title": "P&ID • Atmospheric Distillation Column & Overhead System",
                "type": "P&ID",
                "rev": "Rev B",
                "status": "IFA",
                "area": "Unit 100",
                "date": "2025-01-28",
                "author": "Lead Process",
                "joints": 0,
                "spools": 0,
            },
            {
                "doc_id": "D004",
                "doc_no": "WM-01-PR-2104-01",
                "title": "Weld Map & Joint Traceability Register • Line 2104",
                "type": "Weld Map",
                "rev": "Rev 2",
                "status": "IFC",
                "area": "Unit 100",
                "date": "2025-02-15",
                "author": "QC Dept",
                "joints": 56,
                "spools": 13,
            },
            {
                "doc_id": "D005",
                "doc_no": "TP-HYD-2104-03",
                "title": "Hydrotest Package • 2104 Line Test Pressure 48.5 Barg",
                "type": "Test Package",
                "rev": "Rev 0",
                "status": "Under Review",
                "area": "Unit 100",
                "date": "2025-02-18",
                "author": "QA/QC Lead",
                "joints": 56,
                "spools": 13,
            },
            {
                "doc_id": "D006",
                "doc_no": "NDT-RT-PR-2025-088",
                "title": "Radiographic Testing (RT) Report • Joints W01-W14",
                "type": "NDT Report",
                "rev": "Rev 0",
                "status": "IFC",
                "area": "Unit 100",
                "date": "2025-02-20",
                "author": "NDT Level-II",
                "joints": 14,
                "spools": 4,
            },
            {
                "doc_id": "D007",
                "doc_no": "MTC-FLG-316L-992",
                "title": 'MTC • 12" WNRF Class 300 ASTM A182 F316L Heat #K992',
                "type": "MTC",
                "rev": "Rev 0",
                "status": "As-Built",
                "area": "Warehouse",
                "date": "2025-01-12",
                "author": "Material Controller",
                "joints": 0,
                "spools": 0,
            },
            {
                "doc_id": "D008",
                "doc_no": "ISO-02-FG-3011-001",
                "title": '4"-FG-3011-B1A • Fuel Gas Supply to Primary Reboiler',
                "type": "Isometric (ISO)",
                "rev": "Rev 0",
                "status": "Void",
                "area": "Unit 200",
                "date": "2024-11-05",
                "author": "Eng. Mohammadi",
                "joints": 18,
                "spools": 4,
            },
            {
                "doc_id": "D009",
                "doc_no": "ISO-02-FG-3011-001A",
                "title": '4"-FG-3011-B1A • Fuel Gas Header (Supersedes Rev 0)',
                "type": "Isometric (ISO)",
                "rev": "Rev 1",
                "status": "IFC",
                "area": "Unit 200",
                "date": "2025-02-02",
                "author": "Eng. Mohammadi",
                "joints": 19,
                "spools": 4,
            },
            {
                "doc_id": "D010",
                "doc_no": "ISO-03-CW-4001-001",
                "title": '6"-CW-4001-C1A • Cooling Water Supply Header',
                "type": "Isometric (ISO)",
                "rev": "Rev 0",
                "status": "IFA",
                "area": "Unit 300",
                "date": "2025-03-01",
                "author": "Eng. Ahmadi",
                "joints": 28,
                "spools": 6,
            },
            {
                "doc_id": "D011",
                "doc_no": "PID-00-200-DWG-01",
                "title": "P&ID • Fuel Gas Distribution System",
                "type": "P&ID",
                "rev": "Rev A",
                "status": "IFC",
                "area": "Unit 200",
                "date": "2025-01-15",
                "author": "Lead Process",
                "joints": 0,
                "spools": 0,
            },
            {
                "doc_id": "D012",
                "doc_no": "NDT-UT-PR-2025-045",
                "title": "Ultrasonic Testing (UT) Report • Header Butt Welds",
                "type": "NDT Report",
                "rev": "Rev 1",
                "status": "IFC",
                "area": "Unit 100",
                "date": "2025-02-22",
                "author": "NDT Level-II",
                "joints": 8,
                "spools": 2,
            },
        ]

    # ── Public API ────────────────────────────────────────────
    def list(self) -> List[Dict[str, Any]]:
        """Shallow copy of the record list (records themselves are shared)."""
        return list(self._records)

    def all_doc_numbers(self) -> set:
        return {r.get("doc_no", "").upper() for r in self._records}

    def areas(self) -> List[str]:
        return sorted({r.get("area", "") for r in self._records if r.get("area")})

    def find(self, doc_id: str) -> Optional[Dict[str, Any]]:
        for r in self._records:
            if r.get("doc_id") == doc_id:
                return r
        return None

    def add(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        doc.setdefault("doc_id", _new_doc_id())
        self._records.insert(0, doc)
        self._persist("add", doc)
        return doc

    def update_revision(
        self, doc_id: str, new_rev: str, new_status: str, new_date: str
    ) -> bool:
        doc = self.find(doc_id)
        if doc is None:
            return False
        doc["rev"] = new_rev
        doc["status"] = new_status
        doc["date"] = new_date
        self._persist("update", doc)
        return True

    def delete(self, doc_id: str) -> bool:
        before = len(self._records)
        self._records = [r for r in self._records if r.get("doc_id") != doc_id]
        if len(self._records) == before:
            return False
        self._persist("delete", {"doc_id": doc_id})
        return True

    # ── Persistence hooks ─────────────────────────────────────
    def _persist(self, action: str, payload: Dict[str, Any]):
        """No-op unless the DB layer exposes the matching write method."""
        if not self.db:
            return
        method_name = {
            "add": "add_document",
            "update": "update_document",
            "delete": "delete_document",
        }.get(action)
        if not method_name:
            return
        method = getattr(self.db, method_name, None)
        if not callable(method):
            return
        try:
            method(payload)
        except Exception:
            logger.exception("Persistence failed for action '%s'", action)


# ════════════════════════════════════════════════════════════════
#  PARTICLE FIELD — light-weight animated background
# ════════════════════════════════════════════════════════════════

class ParticleField(QWidget):
    """
    Subtle floating particle background.

    Performance notes:
      • Particle count reduced to 16 and tick rate to ~9 FPS.
      • Painting is skipped while the widget is hidden.
    """

    TICK_MS = 110

    def __init__(self, parent=None, count: int = 16):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

        self._particles: List[Dict[str, float]] = []
        for _ in range(count):
            self._particles.append({
                "x": random.uniform(0, 1),
                "y": random.uniform(0, 1),
                "vx": random.uniform(-0.0002, 0.0002),
                "vy": random.uniform(-0.0005, -0.0001),
                "r": random.uniform(0.8, 1.8),
                "alpha": random.randint(15, 60),
            })

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self.TICK_MS)

    def _tick(self):
        if not self.isVisible():
            return
        for p in self._particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            if p["y"] < -0.02:
                p["y"] = 1.02
                p["x"] = random.uniform(0, 1)
            if p["x"] < -0.02 or p["x"] > 1.02:
                p["x"] = p["x"] % 1.0
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.setPen(Qt.PenStyle.NoPen)
        for p in self._particles:
            color = QColor(108, 207, 246, int(p["alpha"]))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(
                int(p["x"] * w),
                int(p["y"] * h),
                int(p["r"] * 2),
                int(p["r"] * 2),
            )
        painter.end()


# ════════════════════════════════════════════════════════════════
#  GLOW LINE EDIT
# ════════════════════════════════════════════════════════════════

class GlowLineEdit(QLineEdit):
    """
    QLineEdit with a focus glow effect.

    Fixed: the previous version called deleteLater() on an animation that
    Qt had already deleted (via DeleteWhenStopped). That produced
    'wrapped C/C++ object has been deleted' at runtime.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimumHeight(38)

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(0)
        self._shadow.setColor(QColor(108, 207, 246, 0))
        self._shadow.setOffset(0, 0)
        self.setGraphicsEffect(self._shadow)

        self._current_anim: Optional[QPropertyAnimation] = None

    def focusInEvent(self, event):  # noqa: N802
        super().focusInEvent(event)
        self._animate_glow(True)

    def focusOutEvent(self, event):  # noqa: N802
        super().focusOutEvent(event)
        self._animate_glow(False)

    def _animate_glow(self, on: bool):
        # Stop any in-flight animation. Do NOT delete manually —
        # the previous animation was started with DeleteWhenStopped,
        # so Qt owns its lifetime.
        if self._current_anim is not None:
            try:
                self._current_anim.stop()
            except RuntimeError:
                # Underlying C++ object already gone; nothing to do.
                pass
            self._current_anim = None

        # Update color instantly (blur is animated, color is not).
        self._shadow.setColor(QColor(108, 207, 246, 140 if on else 0))

        anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        anim.setDuration(180)
        anim.setStartValue(self._shadow.blurRadius())
        anim.setEndValue(14 if on else 0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._current_anim = anim


# ════════════════════════════════════════════════════════════════
#  KPI STAT CARD
# ════════════════════════════════════════════════════════════════

class StatCard(QFrame):
    """Metric tile with accent border and highlight counter."""

    def __init__(self, title: str, value: str, icon: str, accent_color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setFixedHeight(72)
        self.setMinimumWidth(160)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI", 20))
        icon_lbl.setStyleSheet(f"color: {accent_color}; background: transparent;")
        layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)

        self.val_lbl = QLabel(value)
        self.val_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.val_lbl.setStyleSheet(f"color: {accent_color}; background: transparent;")
        text_col.addWidget(self.val_lbl)

        self.title_lbl = QLabel(title)
        self.title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.title_lbl.setStyleSheet(
            "color: #7a9ab3; letter-spacing: 1px; background: transparent;"
        )
        text_col.addWidget(self.title_lbl)

        layout.addLayout(text_col, 1)

        self._accent = accent_color
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(f"""
            QFrame#statCard {{
                background: #0a1826;
                border: 1px solid rgba(108, 207, 246, 0.18);
                border-left: 3px solid {self._accent};
                border-radius: 8px;
            }}
        """)

    def update_value(self, val: str):
        self.val_lbl.setText(val)


# ════════════════════════════════════════════════════════════════
#  ADD DOCUMENT DIALOG
# ════════════════════════════════════════════════════════════════

class AddDocumentDialog(QDialog):
    """Sub-modal for registering a new document or revision."""

    def __init__(self, existing_doc_numbers: Optional[Iterable[str]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Register Document")
        self.setMinimumSize(480, 540)
        self.setMaximumSize(600, 650)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos: Optional[QPoint] = None

        # Set membership → O(1) duplicate lookup on every keystroke.
        self._existing_numbers = {
            n.upper() for n in (existing_doc_numbers or [])
        }
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("addCard")
        card.setStyleSheet("""
            QWidget#addCard {
                background: #0b1624;
                border: 2px solid #6ccff6;
                border-radius: 14px;
            }
            QLabel { color: #9fe7ff; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
            QLineEdit, QComboBox {
                background: #07101a;
                color: #eef6ff;
                border: 1px solid #18364a;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #6ccff6;
            }
            QComboBox QAbstractItemView {
                background: #07101a;
                color: #eef6ff;
                selection-background-color: #14334f;
                selection-color: #9fe7ff;
                border: 1px solid #18364a;
            }
        """)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: #07101a; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #1e3d5a; border-radius: 4px; min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #6ccff6; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        form_widget = QWidget()
        form_widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(form_widget)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(10)

        # Header
        head = QHBoxLayout()
        title = QLabel("📄   REGISTER NEW DOCUMENT")
        title.setStyleSheet(
            "font-size: 14px; color: #9fe7ff; font-weight: 900; letter-spacing: 2px;"
        )
        head.addWidget(title)
        head.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #7a9ab3;
                border: 1px solid transparent; border-radius: 14px;
                font-weight: bold; font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(255, 107, 107, 0.2); color: #ff6b6b;
                border: 1px solid rgba(255, 107, 107, 0.3);
            }
        """)
        close_btn.clicked.connect(self.reject)
        head.addWidget(close_btn)
        layout.addLayout(head)

        layout.addSpacing(4)

        # Doc Number
        layout.addWidget(QLabel("DOCUMENT NUMBER / ISO ID *"))
        self.in_doc_no = QLineEdit()
        self.in_doc_no.setPlaceholderText("e.g. ISO-01-PR-2104-001")
        layout.addWidget(self.in_doc_no)

        self.lbl_dup_warn = QLabel(
            "⚠ This document number already exists in the register!"
        )
        self.lbl_dup_warn.setStyleSheet(
            "color: #ff6b6b; font-size: 10px; font-weight: 700; background: transparent;"
        )
        self.lbl_dup_warn.setVisible(False)
        layout.addWidget(self.lbl_dup_warn)
        self.in_doc_no.textChanged.connect(self._check_duplicate)

        # Title
        layout.addWidget(QLabel("DOCUMENT TITLE / LINE DESCRIPTION"))
        self.in_title = QLineEdit()
        self.in_title.setPlaceholderText(
            'e.g. 12"-PR-2104-A1A • Header From V-101 To E-102'
        )
        layout.addWidget(self.in_title)

        # Row: Type & Rev
        row1 = QHBoxLayout()
        col_type = QVBoxLayout()
        col_type.addWidget(QLabel("DOCUMENT TYPE"))
        self.in_type = QComboBox()
        self.in_type.addItems([
            "Isometric (ISO)", "P&ID", "Weld Map",
            "Test Package", "NDT Report", "MTC",
        ])
        col_type.addWidget(self.in_type)
        row1.addLayout(col_type)

        col_rev = QVBoxLayout()
        col_rev.addWidget(QLabel("REVISION"))
        self.in_rev = QComboBox()
        self.in_rev.setEditable(True)
        self.in_rev.addItems([
            "Rev 0", "Rev 1", "Rev 2", "Rev 3",
            "Rev A", "Rev B", "Rev C",
        ])
        col_rev.addWidget(self.in_rev)
        row1.addLayout(col_rev)
        layout.addLayout(row1)

        # Row: Status & Area
        row2 = QHBoxLayout()
        col_stat = QVBoxLayout()
        col_stat.addWidget(QLabel("LIFECYCLE STATUS"))
        self.in_status = QComboBox()
        self.in_status.addItems([
            "IFC (Issued for Construction)",
            "IFA (Issued for Approval)",
            "Under Review",
            "As-Built",
            "Void / Superseded",
        ])
        col_stat.addWidget(self.in_status)
        row2.addLayout(col_stat)

        col_area = QVBoxLayout()
        col_area.addWidget(QLabel("AREA / UNIT"))
        self.in_area = QLineEdit()
        self.in_area.setPlaceholderText("e.g. Unit 100 / Area 2")
        col_area.addWidget(self.in_area)
        row2.addLayout(col_area)
        layout.addLayout(row2)

        # Row: Author & Joints
        row3 = QHBoxLayout()
        col_author = QVBoxLayout()
        col_author.addWidget(QLabel("ORIGINATOR / AUTHOR"))
        self.in_author = QLineEdit()
        self.in_author.setPlaceholderText("e.g. Eng. Rezaei")
        col_author.addWidget(self.in_author)
        row3.addLayout(col_author)

        col_joints = QVBoxLayout()
        col_joints.addWidget(QLabel("JOINT COUNT"))
        self.in_joints = QLineEdit()
        self.in_joints.setPlaceholderText("e.g. 34")
        col_joints.addWidget(self.in_joints)
        row3.addLayout(col_joints)
        layout.addLayout(row3)

        layout.addSpacing(12)

        submit_btn = QPushButton("⚡  CONFIRM & REGISTER")
        submit_btn.setMinimumHeight(42)
        submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        submit_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2196d4, stop:1 #68d7ff);
                color: #041827; border: none; border-radius: 8px;
                font-weight: 800; letter-spacing: 1px; font-size: 12px;
            }
            QPushButton:hover { background: #68d7ff; }
            QPushButton:pressed { background: #2196d4; }
        """)
        submit_btn.clicked.connect(self._validate_and_accept)
        layout.addWidget(submit_btn)

        cancel_btn = QPushButton("CANCEL")
        cancel_btn.setMinimumHeight(36)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #7a9ab3;
                border: 1px solid #1e3d5a; border-radius: 8px;
                font-weight: 700; font-size: 11px; letter-spacing: 1px;
            }
            QPushButton:hover {
                background: #142a40; border: 1px solid #6ccff6; color: #9fe7ff;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        scroll.setWidget(form_widget)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(scroll)

        outer.addWidget(card)

    def _check_duplicate(self, text: str):
        is_dup = text.strip().upper() in self._existing_numbers
        self.lbl_dup_warn.setVisible(is_dup)

    # ── Frameless drag ────────────────────────────────────────
    def mousePressEvent(self, event: QMouseEvent):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):  # noqa: N802
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):  # noqa: N802
        self._drag_pos = None

    def keyPressEvent(self, event: QKeyEvent):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Avoid stealing Enter from an open combo box popup.
            if isinstance(self.focusWidget(), QComboBox) and self.focusWidget().view().isVisible():
                super().keyPressEvent(event)
                return
            self._validate_and_accept()
        else:
            super().keyPressEvent(event)

    def _validate_and_accept(self):
        doc_no = self.in_doc_no.text().strip()

        if not doc_no:
            QMessageBox.warning(
                self, "Validation Error", "Document Number is required."
            )
            self.in_doc_no.setFocus()
            return

        if doc_no.upper() in self._existing_numbers:
            reply = QMessageBox.question(
                self, "Duplicate Warning",
                f"Document <b>{doc_no}</b> already exists.\n\n"
                "Do you still want to register it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        joints_text = self.in_joints.text().strip()
        if joints_text and not joints_text.isdigit():
            QMessageBox.warning(
                self, "Validation Error",
                "Joint Count must be a valid number.",
            )
            self.in_joints.setFocus()
            return

        self.accept()

    def get_data(self) -> Dict[str, Any]:
        status_text = self.in_status.currentText()
        if "IFC" in status_text:
            status = "IFC"
        elif "IFA" in status_text:
            status = "IFA"
        elif "Under" in status_text:
            status = "Under Review"
        elif "As-Built" in status_text:
            status = "As-Built"
        else:
            status = "Void"

        joints_text = self.in_joints.text().strip()
        joints = int(joints_text) if joints_text.isdigit() else 0

        return {
            "doc_no": self.in_doc_no.text().strip(),
            "title": self.in_title.text().strip() or "Untitled Piping Document",
            "type": self.in_type.currentText(),
            "rev": self.in_rev.currentText().strip() or "Rev 0",
            "status": status,
            "area": self.in_area.text().strip() or "Area 1",
            "date": datetime.today().strftime("%Y-%m-%d"),
            "author": self.in_author.text().strip() or "QC Engineer",
            "joints": joints,
            "spools": max(0, joints // 4),
        }


# ════════════════════════════════════════════════════════════════
#  MAIN DOCUMENT CONTROL CENTER DIALOG
# ════════════════════════════════════════════════════════════════

class DocumentControlCenter(QDialog):
    """
    Ultra-premium Document Control Center for PipeAgent.
    Fully resizable, scrollable, with enhanced UX.
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
    TEXT_FOOTER   = "#3f6070"
    SUCCESS       = "#5cffaa"
    WARNING       = "#ffd966"
    ERROR         = "#ff6b6b"
    INFO          = "#68d7ff"

    MIN_WIDTH  = 900
    MIN_HEIGHT = 600
    DEF_WIDTH  = 1200
    DEF_HEIGHT = 780

    # Column indices (kept in one place for clarity)
    COL_DOC_NO  = 0
    COL_TITLE   = 1
    COL_TYPE    = 2
    COL_REV     = 3
    COL_STATUS  = 4
    COL_AREA    = 5
    COL_DATE    = 6
    COL_AUTHOR  = 7

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db
        self._repo = DocumentRepository(db)

        self._drag_pos: Optional[QPoint] = None
        self._drag_edge: Optional[str] = None
        self._drag_geometry: Optional[QRect] = None
        self._resize_margin = 8

        # View state
        self._documents: List[Dict[str, Any]] = []
        self._filtered_docs: List[Dict[str, Any]] = []

        self.setWindowTitle("PipeAgent – Document Control Center")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(self.DEF_WIDTH, self.DEF_HEIGHT)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self._build_ui()
        self._setup_shortcuts()
        self._center_on_screen()
        self._reload_from_repo()

    # ── Reload pipeline ───────────────────────────────────────
    def _reload_from_repo(self):
        """Fetch records from repo and re-render everything."""
        self._documents = self._repo.list()
        self._rebuild_area_filter()
        self._apply_filters()

    # ── UI Construction ───────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QWidget()
        self._card.setObjectName("mainCard")
        self._card.setStyleSheet(self._stylesheet())
        self._card.setMouseTracking(True)

        card_shadow = QGraphicsDropShadowEffect(self._card)
        card_shadow.setBlurRadius(45)
        card_shadow.setColor(QColor(0, 0, 0, 200))
        card_shadow.setOffset(0, 10)
        self._card.setGraphicsEffect(card_shadow)

        outer.addWidget(self._card)

        self._particles = ParticleField(self._card, count=16)
        self._particles.lower()

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(24, 14, 24, 14)
        card_layout.setSpacing(10)

        card_layout.addLayout(self._build_topbar())
        card_layout.addLayout(self._build_kpi_ribbon())
        card_layout.addLayout(self._build_filter_bar())

        # Splitter: Table + Inspector
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setObjectName("mainSplitter")
        self._splitter.setHandleWidth(3)
        self._splitter.setChildrenCollapsible(False)

        self.table = self._build_table()
        self._splitter.addWidget(self.table)

        self.detail_panel = self._build_inspector_panel()
        self._splitter.addWidget(self.detail_panel)

        self._splitter.setSizes([820, 320])
        card_layout.addWidget(self._splitter, 1)

        card_layout.addLayout(self._build_footer())

        # Timestamp ticker
        self._update_timestamp()
        self._ts_timer = QTimer(self)
        self._ts_timer.timeout.connect(self._update_timestamp)
        self._ts_timer.start(30_000)

    def _build_topbar(self) -> QHBoxLayout:
        topbar = QHBoxLayout()
        topbar.setContentsMargins(0, 0, 0, 0)
        topbar.setSpacing(10)

        icon_lbl = QLabel("📑")
        icon_lbl.setFont(QFont("Segoe UI", 20))
        icon_lbl.setStyleSheet("background: transparent;")
        topbar.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)

        main_title = QLabel("PIPE AGENT  •  DOCUMENT CONTROL CENTER")
        main_title.setObjectName("mainTitle")
        self._add_glow(main_title, QColor(108, 207, 246, 120), blur=20)
        title_col.addWidget(main_title)

        sub_title = QLabel(
            "ENGINEERING & EXECUTION REVISION WORKFLOW • IFC REGISTER • WJCS LINKED"
        )
        sub_title.setObjectName("subTitle")
        title_col.addWidget(sub_title)
        topbar.addLayout(title_col)

        topbar.addStretch()

        self.btn_new_doc = QPushButton("➕  REGISTER  (Ctrl+N)")
        self.btn_new_doc.setObjectName("actionBtn")
        self.btn_new_doc.setMinimumHeight(36)
        self.btn_new_doc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new_doc.clicked.connect(self._on_register_doc)
        topbar.addWidget(self.btn_new_doc)

        self.btn_export = QPushButton("📤  EXPORT  (Ctrl+E)")
        self.btn_export.setObjectName("secondaryBtn")
        self.btn_export.setMinimumHeight(36)
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.clicked.connect(self._on_export_transmittal)
        topbar.addWidget(self.btn_export)

        min_btn = QPushButton("─")
        min_btn.setObjectName("minBtn")
        min_btn.setFixedSize(30, 30)
        min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        min_btn.clicked.connect(self.showMinimized)
        min_btn.setStyleSheet("""
            QPushButton#minBtn {
                background: transparent; color: #7a9ab3;
                border: none; border-radius: 15px;
                font-size: 14px; font-weight: bold;
            }
            QPushButton#minBtn:hover {
                background: rgba(108, 207, 246, 0.15); color: #6ccff6;
            }
        """)
        topbar.addWidget(min_btn)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self._on_close)
        topbar.addWidget(close_btn)

        return topbar

    def _build_kpi_ribbon(self) -> QHBoxLayout:
        ribbon = QHBoxLayout()
        ribbon.setSpacing(12)

        self.kpi_total = StatCard("TOTAL REGISTERED", "0", "📚", self.PRIMARY_LIGHT)
        self.kpi_ifc   = StatCard("IFC (READY)",       "0", "✅", self.SUCCESS)
        self.kpi_ifa   = StatCard("UNDER APPROVAL",    "0", "⏳", self.WARNING)
        self.kpi_void  = StatCard("SUPERSEDED",        "0", "🚫", self.ERROR)

        ribbon.addWidget(self.kpi_total)
        ribbon.addWidget(self.kpi_ifc)
        ribbon.addWidget(self.kpi_ifa)
        ribbon.addWidget(self.kpi_void)
        return ribbon

    def _build_filter_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText(
            "🔍  Search by Doc No, Title, Area, Author...  (Ctrl+F)"
        )
        self.search_input.setObjectName("searchInput")
        self.search_input.textChanged.connect(self._apply_filters)
        bar.addWidget(self.search_input, 3)

        self.combo_type = QComboBox()
        self.combo_type.setObjectName("filterCombo")
        self.combo_type.setMinimumHeight(38)
        self.combo_type.addItems([
            "All Document Types", "Isometric (ISO)", "P&ID",
            "Weld Map", "Test Package", "NDT Report", "MTC",
        ])
        self.combo_type.currentTextChanged.connect(self._apply_filters)
        bar.addWidget(self.combo_type, 1)

        self.combo_status = QComboBox()
        self.combo_status.setObjectName("filterCombo")
        self.combo_status.setMinimumHeight(38)
        self.combo_status.addItems([
            "All Statuses", "IFC", "IFA",
            "Under Review", "As-Built", "Void",
        ])
        self.combo_status.currentTextChanged.connect(self._apply_filters)
        bar.addWidget(self.combo_status, 1)

        self.combo_area = QComboBox()
        self.combo_area.setObjectName("filterCombo")
        self.combo_area.setMinimumHeight(38)
        self.combo_area.addItem("All Areas")
        self.combo_area.currentTextChanged.connect(self._apply_filters)
        bar.addWidget(self.combo_area, 1)

        self.chk_export_filtered = QCheckBox("Export Filtered")
        self.chk_export_filtered.setChecked(True)
        self.chk_export_filtered.setStyleSheet("""
            QCheckBox {
                color: #7a9ab3; font-size: 10px;
                spacing: 4px; background: transparent;
            }
            QCheckBox::indicator {
                width: 14px; height: 14px;
                border: 1px solid #1e3d5a; border-radius: 3px;
                background: #07101a;
            }
            QCheckBox::indicator:checked {
                background: #6ccff6; border: 1px solid #6ccff6;
            }
        """)
        bar.addWidget(self.chk_export_filtered)

        btn_reset = QPushButton("↺  RESET")
        btn_reset.setObjectName("secondaryBtn")
        btn_reset.setMinimumHeight(38)
        btn_reset.setToolTip("Reset All Filters")
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.clicked.connect(self._reset_filters)
        bar.addWidget(btn_reset)

        return bar

    def _build_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setObjectName("docTable")
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels([
            "Doc Number / ISO", "Title / Description", "Type",
            "Rev", "Status", "Area / Unit", "Issue Date", "Author",
        ])

        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        header = table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setSectionsClickable(True)
        header.setStretchLastSection(True)
        for col_idx in range(table.columnCount()):
            header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

        default_widths = [200, 340, 120, 60, 110, 100, 100, 120]
        for col_idx, w in enumerate(default_widths):
            table.setColumnWidth(col_idx, w)

        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        table.setWordWrap(False)
        table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_context_menu)
        table.itemSelectionChanged.connect(self._on_table_selection)
        table.doubleClicked.connect(self._on_open_file)
        return table

    def _build_inspector_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("inspectorCard")
        panel.setMinimumWidth(260)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: #07101a; width: 6px; border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #1e3d5a; border-radius: 3px; min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #6ccff6; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        head_lbl = QLabel("🔍   DOCUMENT INSPECTOR")
        head_lbl.setObjectName("inspHead")
        layout.addWidget(head_lbl)

        div = QFrame()
        div.setObjectName("divider")
        div.setFixedHeight(1)
        layout.addWidget(div)

        self.insp_doc_no = QLabel("Select a document")
        self.insp_doc_no.setObjectName("inspDocNo")
        self.insp_doc_no.setWordWrap(True)
        layout.addWidget(self.insp_doc_no)

        self.insp_title = QLabel(
            "Select any document from the list to view metadata, "
            "revision workflow and joint links."
        )
        self.insp_title.setObjectName("inspTitle")
        self.insp_title.setWordWrap(True)
        layout.addWidget(self.insp_title)

        layout.addSpacing(6)

        self.meta_frame = QFrame()
        self.meta_frame.setObjectName("metaFrame")
        m_layout = QVBoxLayout(self.meta_frame)
        m_layout.setContentsMargins(12, 10, 12, 10)
        m_layout.setSpacing(6)

        self.m_type   = QLabel()
        self.m_rev    = QLabel()
        self.m_status = QLabel()
        self.m_area   = QLabel()
        self.m_date   = QLabel()
        self.m_author = QLabel()
        self.m_joints = QLabel()

        # Declarative spec for the metadata block:
        # (label widget, plain title) — used for both population and reset.
        self._meta_specs = [
            (self.m_type,   "Type"),
            (self.m_rev,    "Revision"),
            (self.m_status, "Status"),
            (self.m_area,   "Area / Unit"),
            (self.m_date,   "Issued Date"),
            (self.m_author, "Originator"),
            (self.m_joints, "Connected Joints"),
        ]

        meta_style = "color: #dfeaf5; font-size: 11px; background: transparent;"
        for lbl, _ in self._meta_specs:
            lbl.setStyleSheet(meta_style)
            lbl.setWordWrap(True)
            m_layout.addWidget(lbl)

        layout.addWidget(self.meta_frame)
        layout.addStretch()

        btn_style = """
            QPushButton {
                background: #0f1c2e; color: #9fe7ff;
                border: 1px solid #1e3d5a; border-radius: 8px;
                padding: 8px 12px; font-size: 11px;
                font-weight: 700; letter-spacing: 1px;
            }
            QPushButton:hover {
                background: #142a40; border: 1px solid #6ccff6; color: #68d7ff;
            }
            QPushButton:disabled {
                background: #0a1420; color: #3a5060; border: 1px solid #0f1f30;
            }
        """

        self.btn_open_file = QPushButton("📂   OPEN / PREVIEW")
        self.btn_open_file.setMinimumHeight(36)
        self.btn_open_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_file.setStyleSheet(btn_style)
        self.btn_open_file.clicked.connect(self._on_open_file)
        self.btn_open_file.setEnabled(False)
        layout.addWidget(self.btn_open_file)

        self.btn_bump_rev = QPushButton("🔄   BUMP REVISION")
        self.btn_bump_rev.setMinimumHeight(36)
        self.btn_bump_rev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_bump_rev.setStyleSheet(btn_style)
        self.btn_bump_rev.clicked.connect(self._on_bump_rev)
        self.btn_bump_rev.setEnabled(False)
        layout.addWidget(self.btn_bump_rev)

        self.btn_delete_doc = QPushButton("🗑   DELETE DOCUMENT")
        self.btn_delete_doc.setMinimumHeight(36)
        self.btn_delete_doc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete_doc.setStyleSheet("""
            QPushButton {
                background: #0f1c2e; color: #ff6b6b;
                border: 1px solid #3a1a1a; border-radius: 8px;
                padding: 8px 12px; font-size: 11px;
                font-weight: 700; letter-spacing: 1px;
            }
            QPushButton:hover {
                background: rgba(255, 107, 107, 0.12);
                border: 1px solid #ff6b6b; color: #ff9999;
            }
            QPushButton:disabled {
                background: #0a1420; color: #3a2020; border: 1px solid #1a0f0f;
            }
        """)
        self.btn_delete_doc.clicked.connect(self._on_delete_doc)
        self.btn_delete_doc.setEnabled(False)
        layout.addWidget(self.btn_delete_doc)

        scroll.setWidget(inner)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(scroll)
        return panel

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 2, 4, 0)

        self.lbl_count = QLabel("Showing 0 documents")
        self.lbl_count.setObjectName("footerLabel")
        footer.addWidget(self.lbl_count)

        footer.addStretch()

        self.lbl_timestamp = QLabel("")
        self.lbl_timestamp.setObjectName("footerLabel")
        footer.addWidget(self.lbl_timestamp)

        footer.addStretch()

        foot_tag = QLabel("⚡  PipeAgent 5.0  •  Continuous Document Traceability Engine")
        foot_tag.setStyleSheet(
            "color: #3f6070; font-size: 10px; letter-spacing: 1px; background: transparent;"
        )
        footer.addWidget(foot_tag)
        return footer

    # ── Keyboard Shortcuts ────────────────────────────────────
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self, self._on_register_doc)
        QShortcut(QKeySequence("Ctrl+E"), self, self._on_export_transmittal)
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        QShortcut(QKeySequence("F5"),     self, self._apply_filters)

        # Delete is bound to the TABLE, not to the dialog, so typing
        # Delete inside the search field no longer triggers deletion.
        del_sc = QShortcut(QKeySequence("Delete"), self.table, self._on_delete_doc)
        del_sc.setContext(Qt.ShortcutContext.WidgetShortcut)

    def _focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()

    # ── Context Menu ──────────────────────────────────────────
    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #0b1624; color: #eef6ff;
                border: 1px solid #1e3d5a; border-radius: 6px;
                padding: 4px;
            }
            QMenu::item { padding: 8px 24px 8px 12px; border-radius: 4px; }
            QMenu::item:selected { background: #14334f; color: #9fe7ff; }
            QMenu::separator { height: 1px; background: #1e3d5a; margin: 4px 8px; }
        """)

        selected = self._get_selected_doc()

        act_open = menu.addAction("📂  Open / Preview")
        act_open.setEnabled(selected is not None)
        act_open.triggered.connect(self._on_open_file)

        act_bump = menu.addAction("🔄  Bump Revision")
        act_bump.setEnabled(selected is not None)
        act_bump.triggered.connect(self._on_bump_rev)

        menu.addSeparator()

        act_new = menu.addAction("➕  Register New Document  (Ctrl+N)")
        act_new.triggered.connect(self._on_register_doc)

        act_export = menu.addAction("📤  Export Register  (Ctrl+E)")
        act_export.triggered.connect(self._on_export_transmittal)

        menu.addSeparator()

        act_delete = menu.addAction("🗑  Delete Document")
        act_delete.setEnabled(selected is not None)
        act_delete.triggered.connect(self._on_delete_doc)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ── Area Filter Rebuild ───────────────────────────────────
    def _rebuild_area_filter(self):
        current = self.combo_area.currentText()
        self.combo_area.blockSignals(True)
        self.combo_area.clear()
        self.combo_area.addItem("All Areas")
        self.combo_area.addItems(self._repo.areas())
        idx = self.combo_area.findText(current)
        if idx >= 0:
            self.combo_area.setCurrentIndex(idx)
        self.combo_area.blockSignals(False)

    # ── Stylesheet ────────────────────────────────────────────
    def _stylesheet(self) -> str:
        return f"""
            QWidget#mainCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {self.BG_DEEP},
                    stop:0.35 {self.BG_APP},
                    stop:1 {self.BG_DEEP}
                );
                /* QSS does not support gradients in `border`;
                   use a solid color. Depth comes from the drop shadow. */
                border: 2px solid {self.PRIMARY};
                border-radius: 18px;
            }}
            QLabel#mainTitle {{
                color: {self.PRIMARY_LIGHT};
                font-size: 18px;
                font-weight: 900;
                letter-spacing: 3px;
                background: transparent;
            }}
            QLabel#subTitle {{
                color: {self.PRIMARY};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1.5px;
                background: transparent;
            }}
            QLabel#footerLabel {{
                color: #7a9ab3;
                font-size: 11px;
                background: transparent;
            }}
            QFrame#divider {{
                background: rgba(108, 207, 246, 0.3);
                border: none;
            }}
            QLineEdit#searchInput {{
                background: {self.BG_INPUT};
                color: {self.TEXT_MAIN};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QLineEdit#searchInput:focus {{
                border: 1px solid {self.PRIMARY};
            }}
            QComboBox#filterCombo {{
                background: {self.BG_INPUT};
                color: {self.TEXT_MAIN};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 4px 12px;
                font-size: 12px;
            }}
            QComboBox#filterCombo:hover {{
                border: 1px solid {self.PRIMARY};
            }}
            QComboBox#filterCombo QAbstractItemView {{
                background: #07101a;
                color: {self.TEXT_MAIN};
                selection-background-color: #14334f;
                selection-color: {self.PRIMARY_LIGHT};
                border: 1px solid #1e3d5a;
            }}
            QComboBox#filterCombo::drop-down {{
                border: none;
                padding-right: 8px;
            }}
            QPushButton#actionBtn {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2196d4,
                    stop:0.5 {self.ACCENT},
                    stop:1 #2196d4
                );
                color: #041827;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 1px;
            }}
            QPushButton#actionBtn:hover {{ background: {self.PRIMARY_LIGHT}; }}
            QPushButton#actionBtn:pressed {{ background: #2196d4; }}
            QPushButton#secondaryBtn {{
                background: {self.BG_PANEL};
                color: {self.PRIMARY_LIGHT};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 0 14px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton#secondaryBtn:hover {{
                background: #142a40;
                border: 1px solid {self.PRIMARY};
                color: {self.ACCENT};
            }}
            QPushButton#closeBtn {{
                background: transparent;
                color: {self.TEXT_MUTED};
                border: none;
                border-radius: 15px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton#closeBtn:hover {{
                background: rgba(255, 107, 107, 0.2);
                color: {self.ERROR};
            }}
            QTableWidget#docTable {{
                background: #07111c;
                alternate-background-color: #091520;
                color: {self.TEXT_MAIN};
                border: 1px solid #142e47;
                border-radius: 10px;
                gridline-color: transparent;
                selection-background-color: #12334f;
                selection-color: {self.PRIMARY_LIGHT};
                font-size: 12px;
            }}
            QTableWidget#docTable::item {{
                padding: 8px 10px;
                border-bottom: 1px solid #0c1f30;
            }}
            QTableWidget#docTable::item:selected {{
                background: #133959;
                border-left: 2px solid {self.PRIMARY};
            }}
            QHeaderView::section {{
                background: #0c1c2e;
                color: {self.PRIMARY_LIGHT};
                font-weight: 800;
                font-size: 10px;
                letter-spacing: 1px;
                border: none;
                border-bottom: 2px solid #1c4466;
                border-right: 1px solid #142e47;
                padding: 8px 10px;
            }}
            QScrollBar:vertical {{
                background: #07101a;
                width: 10px;
                border-radius: 5px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: #1e3d5a;
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {self.PRIMARY}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            QScrollBar:horizontal {{
                background: #07101a;
                height: 10px;
                border-radius: 5px;
                margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: #1e3d5a;
                border-radius: 5px;
                min-width: 30px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: {self.PRIMARY}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
            QFrame#inspectorCard {{
                background: #091726;
                border: 1px solid #183854;
                border-radius: 10px;
            }}
            QLabel#inspHead {{
                color: {self.PRIMARY_LIGHT};
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 2px;
                background: transparent;
            }}
            QLabel#inspDocNo {{
                color: {self.ACCENT};
                font-size: 14px;
                font-weight: 800;
                background: transparent;
            }}
            QLabel#inspTitle {{
                color: {self.TEXT_MUTED};
                font-size: 11px;
                background: transparent;
            }}
            QFrame#metaFrame {{
                background: #06101c;
                border: 1px solid #10263b;
                border-radius: 8px;
            }}
            QSplitter::handle {{ background: #102538; border-radius: 2px; }}
            QSplitter::handle:hover {{ background: {self.PRIMARY}; }}
        """

    # ── Helpers ───────────────────────────────────────────────
    @staticmethod
    def _add_glow(widget, color, blur=20, offset=(0, 2)):
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur)
        shadow.setColor(color)
        shadow.setOffset(*offset)
        widget.setGraphicsEffect(shadow)

    def _center_on_screen(self):
        screen = self.screen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _update_timestamp(self):
        now = datetime.now().strftime("%Y-%m-%d  %H:%M")
        self.lbl_timestamp.setText(f"🕐 {now}")

    def _get_selected_doc(self) -> Optional[Dict[str, Any]]:
        """
        Return the document stored in the selected row.

        The doc dict is stored on the first column's UserRole, so the
        result is correct even after the user re-sorts the table.
        """
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), self.COL_DOC_NO)
        if item is None:
            return None
        doc = item.data(Qt.ItemDataRole.UserRole)
        return doc if isinstance(doc, dict) else None

    # ── Frameless Drag & Resize ───────────────────────────────
    def _get_resize_edge(self, pos: QPoint) -> Optional[str]:
        m = self._resize_margin
        r = self.rect()
        edges = []
        if pos.y() <= m: edges.append("top")
        if pos.y() >= r.height() - m: edges.append("bottom")
        if pos.x() <= m: edges.append("left")
        if pos.x() >= r.width() - m: edges.append("right")
        return "+".join(edges) if edges else None

    def _update_cursor_for_edge(self, edge: Optional[str]):
        if edge is None:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif edge in ("top", "bottom"):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif edge in ("left", "right"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edge in ("top+left", "bottom+right"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edge in ("top+right", "bottom+left"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event: QMouseEvent):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._get_resize_edge(event.position().toPoint())
            if edge:
                self._drag_edge = edge
                self._drag_pos = event.globalPosition().toPoint()
                self._drag_geometry = self.geometry()
                event.accept()
                return
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            self._drag_edge = None
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):  # noqa: N802
        if self._drag_edge and self._drag_pos and self._drag_geometry:
            delta = event.globalPosition().toPoint() - self._drag_pos
            geo = QRect(self._drag_geometry)

            if "right" in self._drag_edge:
                geo.setWidth(max(self.MIN_WIDTH, geo.width() + delta.x()))
            if "bottom" in self._drag_edge:
                geo.setHeight(max(self.MIN_HEIGHT, geo.height() + delta.y()))
            if "left" in self._drag_edge:
                new_w = max(self.MIN_WIDTH, geo.width() - delta.x())
                if new_w != geo.width():
                    geo.setLeft(geo.right() - new_w)
            if "top" in self._drag_edge:
                new_h = max(self.MIN_HEIGHT, geo.height() - delta.y())
                if new_h != geo.height():
                    geo.setTop(geo.bottom() - new_h)

            self.setGeometry(geo)
            event.accept()
            return

        if (
            self._drag_pos
            and event.buttons() & Qt.MouseButton.LeftButton
            and not self._drag_edge
        ):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return

        edge = self._get_resize_edge(event.position().toPoint())
        self._update_cursor_for_edge(edge)

    def mouseReleaseEvent(self, event: QMouseEvent):  # noqa: N802
        self._drag_pos = None
        self._drag_edge = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "_particles"):
            self._particles.setGeometry(0, 0, self.width(), self.height())

    def keyPressEvent(self, event: QKeyEvent):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._on_close()
        else:
            super().keyPressEvent(event)

    # ── Filtering ─────────────────────────────────────────────
    def _apply_filters(self):
        search = self.search_input.text().strip().lower()
        selected_type = self.combo_type.currentText()
        selected_status = self.combo_status.currentText()
        selected_area = self.combo_area.currentText() if hasattr(self, "combo_area") else "All Areas"

        filtered: List[Dict[str, Any]] = []
        for doc in self._documents:
            if search:
                haystack = " ".join([
                    doc.get("doc_no", ""),
                    doc.get("title", ""),
                    doc.get("area", ""),
                    doc.get("author", ""),
                    doc.get("rev", ""),
                    doc.get("type", ""),
                ]).lower()
                if search not in haystack:
                    continue

            if selected_type != "All Document Types" and doc["type"] != selected_type:
                continue

            if selected_status != "All Statuses":
                if doc["status"].lower() != selected_status.lower():
                    continue

            if selected_area != "All Areas" and doc["area"] != selected_area:
                continue

            filtered.append(doc)

        self._filtered_docs = filtered
        self._populate_table()
        self._update_kpi()

    def _reset_filters(self):
        self.search_input.clear()
        self.combo_type.setCurrentIndex(0)
        self.combo_status.setCurrentIndex(0)
        if hasattr(self, "combo_area"):
            self.combo_area.setCurrentIndex(0)
        self._apply_filters()

    # ── Table population ──────────────────────────────────────
    def _populate_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for row_idx, doc in enumerate(self._filtered_docs):
            self.table.insertRow(row_idx)

            # ── Col 0: Doc Number (also carries the full doc via UserRole)
            item_no = QTableWidgetItem(doc["doc_no"])
            item_no.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            item_no.setForeground(QColor(self.PRIMARY_LIGHT))
            item_no.setData(Qt.ItemDataRole.UserRole, doc)  # ← sort-safe link
            self.table.setItem(row_idx, self.COL_DOC_NO, item_no)

            # ── Col 1: Title
            item_title = QTableWidgetItem(doc["title"])
            item_title.setForeground(QColor(self.TEXT_MAIN))
            item_title.setToolTip(doc["title"])
            self.table.setItem(row_idx, self.COL_TITLE, item_title)

            # ── Col 2: Type
            item_type = QTableWidgetItem(doc["type"])
            item_type.setForeground(QColor("#a2c2dc"))
            self.table.setItem(row_idx, self.COL_TYPE, item_type)

            # ── Col 3: Revision
            item_rev = QTableWidgetItem(doc["rev"])
            item_rev.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item_rev.setForeground(QColor(self.ACCENT))
            item_rev.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, self.COL_REV, item_rev)

            # ── Col 4: Status
            item_stat = QTableWidgetItem(f" ● {doc['status']} ")
            item_stat.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item_stat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_stat.setForeground(QColor(self._status_color(doc["status"])))
            self.table.setItem(row_idx, self.COL_STATUS, item_stat)

            # ── Col 5: Area
            item_area = QTableWidgetItem(doc["area"])
            item_area.setForeground(QColor(self.TEXT_MUTED))
            self.table.setItem(row_idx, self.COL_AREA, item_area)

            # ── Col 6: Date
            item_date = QTableWidgetItem(doc["date"])
            item_date.setForeground(QColor("#708fa8"))
            item_date.setFont(QFont("Consolas", 10))
            self.table.setItem(row_idx, self.COL_DATE, item_date)

            # ── Col 7: Author
            item_author = QTableWidgetItem(doc.get("author", "—"))
            item_author.setForeground(QColor(self.TEXT_MUTED))
            self.table.setItem(row_idx, self.COL_AUTHOR, item_author)

        self.table.setSortingEnabled(True)

        total = len(self._documents)
        shown = len(self._filtered_docs)
        if shown == total:
            self.lbl_count.setText(f"Showing all {total} documents")
        else:
            self.lbl_count.setText(
                f"Showing {shown} of {total} documents (filtered)"
            )

        if self._filtered_docs:
            self.table.selectRow(0)
        else:
            self._clear_inspector()

    def _status_color(self, status: str) -> str:
        s = (status or "").upper()
        if "IFC" in s:
            return self.SUCCESS
        if "IFA" in s:
            return self.WARNING
        if "REVIEW" in s:
            return self.INFO
        if "VOID" in s:
            return self.ERROR
        return "#8faec5"

    def _update_kpi(self):
        total = len(self._documents)
        ifc = sum(1 for d in self._documents if d["status"].upper() == "IFC")
        ifa = sum(
            1 for d in self._documents
            if d["status"].upper() in ("IFA", "UNDER REVIEW")
        )
        void = sum(1 for d in self._documents if d["status"].upper() == "VOID")

        self.kpi_total.update_value(str(total))
        self.kpi_ifc.update_value(str(ifc))
        self.kpi_ifa.update_value(str(ifa))
        self.kpi_void.update_value(str(void))

    # ── Selection → Inspector ─────────────────────────────────
    def _on_table_selection(self):
        doc = self._get_selected_doc()
        if doc is None:
            self._clear_inspector()
            return

        self.insp_doc_no.setText(doc["doc_no"])
        self.insp_title.setText(doc["title"])

        self.m_type.setText(f"<b>Type:</b> {doc['type']}")
        self.m_rev.setText(f"<b>Revision:</b> {doc['rev']}")

        color = self._status_color(doc["status"])
        self.m_status.setText(
            f"<b>Status:</b> <span style='color:{color}'>{doc['status']}</span>"
        )

        self.m_area.setText(f"<b>Area / Unit:</b> {doc['area']}")
        self.m_date.setText(f"<b>Issued Date:</b> {doc['date']}")
        self.m_author.setText(f"<b>Originator:</b> {doc.get('author', 'Engineering')}")

        joints = doc.get("joints", 0)
        spools = doc.get("spools", 0)
        self.m_joints.setText(
            f"<b>Connected Joints:</b> {joints} joints • {spools} spools"
        )

        self.btn_open_file.setEnabled(True)
        self.btn_bump_rev.setEnabled(True)
        self.btn_delete_doc.setEnabled(True)

    def _clear_inspector(self):
        self.insp_doc_no.setText("No document selected")
        self.insp_title.setText(
            "Select any document from the list to view metadata, "
            "revision workflow and joint links."
        )
        # Reset driven by the declared spec — no string parsing.
        for lbl, title in self._meta_specs:
            lbl.setText(f"<b>{title}:</b> —")

        self.btn_open_file.setEnabled(False)
        self.btn_bump_rev.setEnabled(False)
        self.btn_delete_doc.setEnabled(False)

    # ── User Actions ──────────────────────────────────────────
    def _on_register_doc(self):
        modal = AddDocumentDialog(
            existing_doc_numbers=self._repo.all_doc_numbers(),
            parent=self,
        )
        if modal.exec() != QDialog.DialogCode.Accepted:
            return

        new_data = modal.get_data()
        self._repo.add(new_data)
        self._reload_from_repo()

        QMessageBox.information(
            self, "✅ Document Registered",
            f"Document <b>{new_data['doc_no']}</b> ({new_data['rev']}) "
            f"has been successfully added to the register."
        )

    def _on_bump_rev(self):
        doc = self._get_selected_doc()
        if doc is None:
            QMessageBox.warning(
                self, "Selection Required",
                "Please select a document to bump its revision."
            )
            return

        cur_rev = doc["rev"]
        new_rev = _next_revision(cur_rev)

        reply = QMessageBox.question(
            self, "Confirm Revision Bump",
            f"Bump <b>{doc['doc_no']}</b> from <b>{cur_rev}</b> to <b>{new_rev}</b>?\n\n"
            f"Status will be set to <i>Under Review</i>.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        ok = self._repo.update_revision(
            doc_id=doc["doc_id"],
            new_rev=new_rev,
            new_status="Under Review",
            new_date=datetime.today().strftime("%Y-%m-%d"),
        )
        if not ok:
            QMessageBox.warning(
                self, "Update Failed",
                "The document could not be located for update."
            )
            return

        self._reload_from_repo()
        QMessageBox.information(
            self, "✅ Revision Updated",
            f"Document <b>{doc['doc_no']}</b> → <b>{new_rev}</b>\n"
            f"Status set to <i>Under Review</i>."
        )

    def _on_delete_doc(self):
        doc = self._get_selected_doc()
        if doc is None:
            return

        reply = QMessageBox.warning(
            self, "⚠ Confirm Delete",
            f"Are you sure you want to delete:\n\n"
            f"<b>{doc['doc_no']}</b>\n{doc['title']}\n\n"
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if not self._repo.delete(doc["doc_id"]):
            QMessageBox.warning(
                self, "Delete Failed",
                "The document could not be located for deletion."
            )
            return

        self._reload_from_repo()
        QMessageBox.information(
            self, "Deleted",
            f"Document <b>{doc['doc_no']}</b> has been removed from the register."
        )

    def _on_open_file(self):
        doc = self._get_selected_doc()
        if doc is None:
            return

        QMessageBox.information(
            self, "📂 Drawing Viewer",
            f"Simulating file open for:\n\n"
            f"<b>{doc['doc_no']}</b> ({doc['rev']})\n"
            f"{doc['title']}\n\n"
            f"<i>In production, this would open the associated PDF/DWG file.</i>"
        )

    def _on_export_transmittal(self):
        if self.chk_export_filtered.isChecked():
            export_docs = self._filtered_docs
            label = "filtered"
        else:
            export_docs = self._documents
            label = "all"

        if not export_docs:
            QMessageBox.warning(
                self, "No Data",
                "No documents to export. Adjust your filters."
            )
            return

        default_name = (
            f"Piping_Document_Register_"
            f"{datetime.today().strftime('%Y%m%d')}.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Document Transmittal",
            default_name,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Doc Number", "Title", "Type", "Revision",
                    "Status", "Area", "Issue Date", "Author",
                    "Joints", "Spools",
                ])
                for d in export_docs:
                    writer.writerow([
                        d["doc_no"], d["title"], d["type"], d["rev"],
                        d["status"], d["area"], d["date"],
                        d.get("author", ""),
                        d.get("joints", 0), d.get("spools", 0),
                    ])

            QMessageBox.information(
                self, "✅ Export Complete",
                f"Successfully exported {len(export_docs)} {label} documents to:\n\n{path}"
            )
        except PermissionError:
            QMessageBox.critical(
                self, "Export Error",
                "Permission denied. The file may be open in another application.\n"
                "Please close it and try again."
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Export Error",
                f"Could not export register:\n\n{e}"
            )

    def _on_close(self):
        """Graceful close."""
        self.accept()


# ════════════════════════════════════════════════════════════════
#  STANDALONE TEST RUNNER
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    dialog = DocumentControlCenter()
    dialog.show()
    dialog.exec()

    sys.exit(0)