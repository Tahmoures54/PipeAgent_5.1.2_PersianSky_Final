# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Hydrotest Package & Turnover Clearance Dialog
═══════════════════════════════════════════════════════════════════════════
Version : 5.0 (Refactored, hardened, production-ready)
Engine  : PyQt6
Design  : Cinematic dark-tech theme matching PipeAgent Suite

Fixes in this revision
──────────────────────
🔴 P0  Card border       : replaced invalid `border: ... qlineargradient`
                          with a solid color + drop shadow
🔴 P0  GlowLineEdit      : no longer calls deleteLater() on an animation
                          that Qt owns (DeleteWhenStopped)
🔴 P0  Sort-safe select   : every row stores its record dict on
                          QTableWidgetItem.UserRole
🔴 P0  Stable ids         : lines / blinds / punches all have `_id` fields;
                          lookups no longer rely on `list.index(dict)`
🟠 P1  Export filter      : removed the phantom `chk_export_filtered`
                          reference; added a real checkbox in the topbar
🟠 P1  Cleanup            : `_cleanup()` idempotent + `done()` overridden
🟠 P1  Particle geometry  : set immediately after creation
🟠 P1  Empty-list KPI     : readiness score handled correctly when no
                          lines exist
🟠 P1  Delete shortcut    : bound to each table (WidgetShortcut)
🟡 P2  ParticleField      : count 32 → 14, tick 60ms → 100ms, paints only
                          when visible
🟡 P2  Duplicate check    : `_existing_lines` is now a set (O(1))
🟡 P2  Punch id collision : uses uuid instead of MM:SS
🟢 P3  Tooltips           : on every field / button
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
    QPropertyAnimation, QEasingCurve, pyqtSignal, QUrl,
)
from PyQt6.QtGui import (
    QFont, QPixmap, QPainter, QColor, QLinearGradient,
    QRadialGradient, QPen, QBrush, QPainterPath,
    QMouseEvent, QKeyEvent, QIcon, QCursor,
    QShortcut, QKeySequence, QAction,
)
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QGraphicsDropShadowEffect, QWidget,
    QApplication, QMessageBox, QSplitter, QAbstractItemView,
    QFileDialog, QTabWidget, QProgressBar, QDoubleSpinBox,
    QSpinBox, QMenu, QScrollArea, QCheckBox,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#  UTILITIES
# ════════════════════════════════════════════════════════════════

def _uid(prefix: str = "R") -> str:
    """Short, collision-resistant record identifier."""
    return prefix + uuid.uuid4().hex[:9].upper()


def _today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


# ════════════════════════════════════════════════════════════════
#  PARTICLE FIELD — Animated Background
# ════════════════════════════════════════════════════════════════

class ParticleField(QWidget):
    """Subtle floating particle background — optimized."""

    TICK_MS = 100

    def __init__(self, parent=None, count: int = 14):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

        self._particles = []
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

    def stop(self):
        self._timer.stop()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.setPen(Qt.PenStyle.NoPen)
        for p in self._particles:
            color = QColor(108, 207, 246, int(p["alpha"]))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(
                int(p["x"] * w), int(p["y"] * h),
                int(p["r"] * 2), int(p["r"] * 2),
            )
        painter.end()


# ════════════════════════════════════════════════════════════════
#  GLOW LINE EDIT — Focus Glow (Memory Leak Fixed)
# ════════════════════════════════════════════════════════════════

class GlowLineEdit(QLineEdit):
    """QLineEdit with focus glow effect — animation lifetime fixed."""

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
        # Qt owns it (started with DeleteWhenStopped).
        if self._current_anim is not None:
            try:
                self._current_anim.stop()
            except RuntimeError:
                pass
            self._current_anim = None

        self._shadow.setColor(QColor(108, 207, 246, 140 if on else 0))

        anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        anim.setDuration(180)
        anim.setStartValue(self._shadow.blurRadius())
        anim.setEndValue(14 if on else 0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._current_anim = anim


# ════════════════════════════════════════════════════════════════
#  KPI STAT CARD WIDGET
# ════════════════════════════════════════════════════════════════

class StatCard(QFrame):
    """Metric tile with left glow accent."""

    def __init__(self, title: str, value: str, icon: str, accent_color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
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
        text_col.setSpacing(1)

        self.val_lbl = QLabel(value)
        self.val_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self.val_lbl.setStyleSheet(f"color: {accent_color}; background: transparent;")
        text_col.addWidget(self.val_lbl)

        self.title_lbl = QLabel(title)
        self.title_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        self.title_lbl.setStyleSheet(
            "color: #7a9ab3; letter-spacing: 1px; background: transparent;"
        )
        text_col.addWidget(self.title_lbl)

        layout.addLayout(text_col, 1)

        self.setStyleSheet(f"""
            QFrame#statCard {{
                background: #0a1826;
                border: 1px solid rgba(108, 207, 246, 0.18);
                border-left: 3px solid {accent_color};
                border-radius: 8px;
            }}
        """)

    def update_value(self, val: str):
        self.val_lbl.setText(val)


# ════════════════════════════════════════════════════════════════
#  ADD LINE / ISO SUB-MODAL
# ════════════════════════════════════════════════════════════════

class AddLineDialog(QDialog):
    """Sub-modal for adding a piping line / ISO with validation."""

    def __init__(self, existing_lines: Optional[Iterable[str]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Line to Package")
        self.setMinimumSize(500, 500)
        self.setMaximumSize(650, 700)
        self.resize(500, 520)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos: Optional[QPoint] = None
        # Set membership → O(1) duplicate check on every keystroke.
        self._existing_lines = {str(l).upper() for l in (existing_lines or [])}
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
            QLabel { color: #9fe7ff; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
            QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {
                background: #07101a;
                color: #eef6ff;
                border: 1px solid #18364a;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {
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
        layout.setSpacing(9)

        head = QHBoxLayout()
        title = QLabel("📐   ADD LINE TO TEST PACKAGE")
        title.setStyleSheet(
            "font-size: 13px; color: #9fe7ff; "
            "font-weight: 900; letter-spacing: 2px;"
        )
        head.addWidget(title)
        head.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close (Escape)")
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

        layout.addWidget(QLabel("LINE NUMBER / DESIGNATION *"))
        self.in_line = QLineEdit()
        self.in_line.setPlaceholderText('e.g. 12"-PR-2104-A1A')
        self.in_line.setToolTip("Unique line number — required")
        layout.addWidget(self.in_line)

        self.lbl_dup_warn = QLabel(
            "⚠ This Line Number is already included in the boundary!"
        )
        self.lbl_dup_warn.setStyleSheet(
            "color: #ff9f43; font-size: 10px; font-weight: 700; background: transparent;"
        )
        self.lbl_dup_warn.setVisible(False)
        layout.addWidget(self.lbl_dup_warn)
        self.in_line.textChanged.connect(self._check_duplicate_line)

        row1 = QHBoxLayout()
        col_iso = QVBoxLayout()
        col_iso.addWidget(QLabel("ISO DRAWING NUMBER"))
        self.in_iso = QLineEdit()
        self.in_iso.setPlaceholderText("e.g. ISO-01-PR-2104-001")
        col_iso.addWidget(self.in_iso)
        row1.addLayout(col_iso)

        col_pid = QVBoxLayout()
        col_pid.addWidget(QLabel("P&ID REFERENCE"))
        self.in_pid = QLineEdit()
        self.in_pid.setPlaceholderText("e.g. PID-104-DWG-01")
        col_pid.addWidget(self.in_pid)
        row1.addLayout(col_pid)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        col_dp = QVBoxLayout()
        col_dp.addWidget(QLabel("DESIGN PRESS (BARG)"))
        self.in_dp = QDoubleSpinBox()
        self.in_dp.setRange(0.0, 500.0)
        self.in_dp.setValue(32.3)
        self.in_dp.setSingleStep(1.0)
        col_dp.addWidget(self.in_dp)
        row2.addLayout(col_dp)

        col_tp = QVBoxLayout()
        col_tp.addWidget(QLabel("TEST PRESS (BARG)"))
        self.in_tp = QDoubleSpinBox()
        self.in_tp.setRange(0.0, 750.0)
        self.in_tp.setValue(48.5)
        self.in_tp.setSingleStep(1.0)
        col_tp.addWidget(self.in_tp)
        row2.addLayout(col_tp)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        col_j = QVBoxLayout()
        col_j.addWidget(QLabel("TOTAL JOINTS"))
        self.in_joints = QSpinBox()
        self.in_joints.setRange(1, 1000)
        self.in_joints.setValue(34)
        col_j.addWidget(self.in_joints)
        row3.addLayout(col_j)

        col_ndt = QVBoxLayout()
        col_ndt.addWidget(QLabel("NDT 100% CLEARANCE"))
        self.in_ndt = QComboBox()
        self.in_ndt.addItems([
            "Cleared (100% Passed)", "Pending NDT", "Repairs Open"
        ])
        col_ndt.addWidget(self.in_ndt)
        row3.addLayout(col_ndt)
        layout.addLayout(row3)

        layout.addSpacing(10)

        submit_btn = QPushButton("⚡  INSERT LINE INTO PACKAGE")
        submit_btn.setMinimumHeight(44)
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

    def _check_duplicate_line(self, text: str):
        is_dup = text.strip().upper() in self._existing_lines
        self.lbl_dup_warn.setVisible(is_dup)

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
        else:
            super().keyPressEvent(event)

    def _validate_and_accept(self):
        line = self.in_line.text().strip()
        if not line:
            QMessageBox.warning(
                self, "Validation Error",
                "Line Number designation is required."
            )
            self.in_line.setFocus()
            return

        if line.upper() in self._existing_lines:
            reply = QMessageBox.question(
                self, "Duplicate Line ID",
                f"Line <b>{line}</b> is already included in this test package.\n\n"
                "Do you still want to insert this entry?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.accept()

    def get_data(self) -> Dict[str, Any]:
        ndt = self.in_ndt.currentText()
        status = "Cleared" if "Cleared" in ndt else "Pending"

        return {
            "line_id": _uid("LN"),
            "line_no": self.in_line.text().strip().upper(),
            "iso_no": self.in_iso.text().strip() or "ISO-GEN",
            "pid_no": self.in_pid.text().strip() or "PID-GEN",
            "design_p": f"{self.in_dp.value():.1f} Barg",
            "test_p": f"{self.in_tp.value():.1f} Barg",
            "joints": self.in_joints.value(),
            "ndt_status": status,
        }


# ════════════════════════════════════════════════════════════════
#  ADD PUNCH LIST ITEM SUB-MODAL
# ════════════════════════════════════════════════════════════════

class AddPunchDialog(QDialog):
    """Sub-modal for logging a Category A / B / C punch item."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Punch Item")
        self.setMinimumSize(500, 480)
        self.setMaximumSize(650, 680)
        self.resize(500, 500)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos: Optional[QPoint] = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("punchCard")
        card.setStyleSheet("""
            QWidget#punchCard {
                background: #0b1624;
                border: 2px solid #6ccff6;
                border-radius: 14px;
            }
            QLabel { color: #9fe7ff; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
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
        layout.setSpacing(9)

        head = QHBoxLayout()
        title = QLabel("⚠️   LOG PUNCH LIST ITEM")
        title.setStyleSheet(
            "font-size: 13px; color: #9fe7ff; "
            "font-weight: 900; letter-spacing: 2px;"
        )
        head.addWidget(title)
        head.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close (Escape)")
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

        row1 = QHBoxLayout()
        col_cat = QVBoxLayout()
        col_cat.addWidget(QLabel("PUNCH CATEGORY"))
        self.in_cat = QComboBox()
        self.in_cat.addItems([
            "Category A (Pre-Hydro Blocker — Must Clear)",
            "Category B (Post-Hydro / Reinstatement)",
            "Category C (Turnover / Documentation)",
        ])
        col_cat.addWidget(self.in_cat)
        row1.addLayout(col_cat)
        layout.addLayout(row1)

        layout.addWidget(QLabel("PUNCH DESCRIPTION & DEFICIENCY *"))
        self.in_desc = QLineEdit()
        self.in_desc.setPlaceholderText(
            "e.g. Pipe support PS-104 shoe not bolted; NDT RT report missing for W-04"
        )
        self.in_desc.setToolTip("Describe the defect / missing item — required")
        layout.addWidget(self.in_desc)

        row2 = QHBoxLayout()
        col_tag = QVBoxLayout()
        col_tag.addWidget(QLabel("LOCATION / ISO DRAWING"))
        self.in_loc = QLineEdit()
        self.in_loc.setPlaceholderText("e.g. Unit 100 / ISO-01-PR-2104-001")
        col_tag.addWidget(self.in_loc)
        row2.addLayout(col_tag)

        col_disc = QVBoxLayout()
        col_disc.addWidget(QLabel("ACTION DISCIPLINE"))
        self.in_disc = QComboBox()
        self.in_disc.addItems([
            "Piping Construction", "Welding / QC", "Piping Supports",
            "Painting & Insulation", "Instrumentation",
        ])
        col_disc.addWidget(self.in_disc)
        row2.addLayout(col_disc)
        layout.addLayout(row2)

        layout.addSpacing(10)

        submit_btn = QPushButton("⚡  INSERT PUNCH ITEM")
        submit_btn.setMinimumHeight(44)
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
        else:
            super().keyPressEvent(event)

    def _validate_and_accept(self):
        if not self.in_desc.text().strip():
            QMessageBox.warning(
                self, "Validation Error",
                "Punch description cannot be empty."
            )
            self.in_desc.setFocus()
            return
        self.accept()

    def get_data(self) -> Dict[str, Any]:
        cat_text = self.in_cat.currentText()
        if "Category A" in cat_text:
            cat_letter = "A"
        elif "Category B" in cat_text:
            cat_letter = "B"
        else:
            cat_letter = "C"

        # Use uuid instead of MM:SS to prevent collisions within the same minute.
        return {
            "punch_id": f"PNC-{cat_letter}-{uuid.uuid4().hex[:4].upper()}",
            "cat": f"Cat {cat_letter}",
            "desc": self.in_desc.text().strip(),
            "location": self.in_loc.text().strip() or "Area 1",
            "discipline": self.in_disc.currentText(),
            "status": "Open",
            "logged_date": _today(),
        }


# ════════════════════════════════════════════════════════════════
#  TEST PACKAGE HEADER SPEC EDITOR
# ════════════════════════════════════════════════════════════════

class EditPkgMetaDialog(QDialog):
    """Sub-modal for editing Test Package Header technical specifications."""

    def __init__(self, current_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Package Specifications")
        self.setMinimumSize(500, 480)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos: Optional[QPoint] = None
        self._current_data = current_data
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("hdrCard")
        card.setStyleSheet("""
            QWidget#hdrCard {
                background: #0b1624;
                border: 2px solid #6ccff6;
                border-radius: 14px;
            }
            QLabel { color: #9fe7ff; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
            QLineEdit {
                background: #07101a; color: #eef6ff;
                border: 1px solid #18364a; border-radius: 6px;
                padding: 6px 10px; font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #6ccff6; }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(9)

        head = QHBoxLayout()

        drag_hint = QLabel("⠿")
        drag_hint.setStyleSheet(
            "color: #2a4a5a; font-size: 14px; background: transparent;"
        )
        drag_hint.setToolTip("Drag to move window")
        head.addWidget(drag_hint)

        title = QLabel("🧪   EDIT TEST PACKAGE METADATA")
        title.setStyleSheet(
            "font-size: 13px; color: #9fe7ff; "
            "font-weight: 900; letter-spacing: 2px;"
        )
        head.addWidget(title)
        head.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close (Escape)")
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #7a9ab3;
                border: none; border-radius: 14px;
                font-weight: bold; font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(255, 107, 107, 0.2); color: #ff6b6b;
            }
        """)
        close_btn.clicked.connect(self.reject)
        head.addWidget(close_btn)
        layout.addLayout(head)

        layout.addWidget(QLabel("SYSTEM / BOUNDARY SPEC"))
        self.in_system = QLineEdit()
        self.in_system.setText(str(self._current_data.get("system", "")))
        layout.addWidget(self.in_system)

        layout.addWidget(QLabel("TEST MEDIUM / FLUID"))
        self.in_medium = QLineEdit()
        self.in_medium.setText(str(self._current_data.get("medium", "")))
        layout.addWidget(self.in_medium)

        layout.addWidget(QLabel("TARGET TEST PRESSURE"))
        self.in_tpress = QLineEdit()
        self.in_tpress.setText(str(self._current_data.get("test_press", "")))
        layout.addWidget(self.in_tpress)

        layout.addWidget(QLabel("MINIMUM HOLDING TIME"))
        self.in_hold = QLineEdit()
        self.in_hold.setText(str(self._current_data.get("holding_time", "")))
        layout.addWidget(self.in_hold)

        layout.addWidget(QLabel("SAFETY RELIEF VALVE TAG (PSV)"))
        self.in_psv = QLineEdit()
        self.in_psv.setText(str(self._current_data.get("relief_valve", "")))
        layout.addWidget(self.in_psv)

        layout.addSpacing(10)

        submit_btn = QPushButton("💾  SAVE PACKAGE PASSPORT")
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
        """)
        submit_btn.clicked.connect(self.accept)
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

        outer.addWidget(card)

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
        else:
            super().keyPressEvent(event)

    def get_data(self) -> Dict[str, str]:
        return {
            "system": self.in_system.text().strip(),
            "medium": self.in_medium.text().strip(),
            "test_press": self.in_tpress.text().strip(),
            "holding_time": self.in_hold.text().strip(),
            "relief_valve": self.in_psv.text().strip(),
        }


# ════════════════════════════════════════════════════════════════
#  MAIN TEST PACKAGE DIALOG
# ════════════════════════════════════════════════════════════════

class TestPackageDialog(QDialog):
    """
    Ultra-premium Test Package & Hydrotest Turnover Clearance Dialog.
    Fully resizable, responsive, with adaptive context menus and shortcuts.
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

    MIN_WIDTH  = 960
    MIN_HEIGHT = 620
    DEF_WIDTH  = 1240
    DEF_HEIGHT = 800

    def __init__(self, db=None, package_no: str = "TP-HYD-2104-03", parent=None):
        super().__init__(parent)
        self.db = db
        self.package_no = package_no

        # Drag / resize state
        self._drag_pos: Optional[QPoint] = None
        self._drag_edge: Optional[str] = None
        self._drag_geometry: Optional[QRect] = None
        self._resize_margin = 8

        # Lifecycle
        self._is_closed = False
        self._ts_timer: Optional[QTimer] = None

        # View state
        self._lines: List[Dict[str, Any]] = []
        self._blinds: List[Dict[str, Any]] = []
        self._punches: List[Dict[str, Any]] = []

        self.setWindowTitle(f"PipeAgent – Test Package • {self.package_no}")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(self.DEF_WIDTH, self.DEF_HEIGHT)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self._init_data()
        self._build_ui()
        self._setup_shortcuts()
        self._center_on_screen()
        self._populate_all()
        self._update_kpi()

    # ── Data Init ─────────────────────────────────────────────
    def _init_data(self):
        self._pkg_meta: Dict[str, Any] = {
            "package_no": self.package_no,
            "system": "Crude Feed & Pre-heat System",
            "unit": "Unit 100",
            "medium": "Demineralized Water (Hydrostatic)",
            "design_press": "32.3 Barg",
            "test_press": "48.5 Barg",
            "holding_time": "2.0 Hours",
            "relief_valve": "PSV-TP-2104 (Set @ 50.9 Barg)",
            "gauges": "2x Calibrated (Range 0-100 Bar)",
            "status": "Ready for Hydrotest",
        }

        # Every record carries a stable `_id` for safe lookups.
        self._lines = [
            {
                "line_id": "LN000000001",
                "line_no": '12"-PR-2104-A1A',
                "iso_no": "ISO-01-PR-2104-001",
                "pid_no": "PID-104-DWG-01",
                "design_p": "32.3 Barg",
                "test_p": "48.5 Barg",
                "joints": 34,
                "ndt_status": "Cleared",
            },
            {
                "line_id": "LN000000002",
                "line_no": '8"-PR-2104-A1A',
                "iso_no": "ISO-01-PR-2104-002",
                "pid_no": "PID-104-DWG-01",
                "design_p": "32.3 Barg",
                "test_p": "48.5 Barg",
                "joints": 22,
                "ndt_status": "Cleared",
            },
            {
                "line_id": "LN000000003",
                "line_no": '4"-PR-2104-A1A',
                "iso_no": "ISO-01-PR-2104-003",
                "pid_no": "PID-104-DWG-02",
                "design_p": "32.3 Barg",
                "test_p": "48.5 Barg",
                "joints": 16,
                "ndt_status": "Cleared",
            },
        ]

        self._blinds = [
            {
                "blind_id": "BL000000001",
                "tag": "BLD-01",
                "location": "Suction Nozzle V-101",
                "size": '12" Cl 150#',
                "thick": "22 mm",
                "installed_by": "Fitter Team A",
                "install_status": "Installed & Tagged",
                "removal_status": "Pending Test",
            },
            {
                "blind_id": "BL000000002",
                "tag": "BLD-02",
                "location": "Inlet Flange H-101",
                "size": '8" Cl 150#',
                "thick": "18 mm",
                "installed_by": "Fitter Team A",
                "install_status": "Installed & Tagged",
                "removal_status": "Pending Test",
            },
            {
                "blind_id": "BL000000003",
                "tag": "BLD-03",
                "location": "Drain Header Isolation",
                "size": '4" Cl 150#',
                "thick": "14 mm",
                "installed_by": "Fitter Team B",
                "install_status": "Installed & Tagged",
                "removal_status": "Pending Test",
            },
        ]

        self._punches = [
            {
                "punch_id": "PNC-A-01",
                "cat": "Cat A",
                "desc": "Pipe support PS-104 guide gap excessive; shim required",
                "location": "ISO-01-PR-2104-001",
                "discipline": "Piping Supports",
                "status": "Cleared",
                "logged_date": "2025-02-18",
            },
            {
                "punch_id": "PNC-A-02",
                "cat": "Cat A",
                "desc": "Temporary blind tag BLD-03 missing high-vis warning tape",
                "location": "Drain Header",
                "discipline": "Piping Construction",
                "status": "Cleared",
                "logged_date": "2025-02-19",
            },
            {
                "punch_id": "PNC-B-01",
                "cat": "Cat B",
                "desc": "Final top coat painting touch-up on weld joint W-08",
                "location": "ISO-01-PR-2104-002",
                "discipline": "Painting & Insulation",
                "status": "Open",
                "logged_date": "2025-02-20",
            },
            {
                "punch_id": "PNC-B-02",
                "cat": "Cat B",
                "desc": "Reinstall orifice plate FE-2104 after de-watering & flushing",
                "location": "ISO-01-PR-2104-001",
                "discipline": "Instrumentation",
                "status": "Open",
                "logged_date": "2025-02-21",
            },
        ]

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

        # Set particle geometry immediately to avoid clustering at (0,0).
        self._particles = ParticleField(self._card, count=14)
        self._particles.setGeometry(0, 0, self.DEF_WIDTH, self.DEF_HEIGHT)
        self._particles.lower()

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(24, 14, 24, 14)
        card_layout.setSpacing(10)

        card_layout.addLayout(self._build_topbar())
        card_layout.addWidget(self._build_header_frame())
        card_layout.addLayout(self._build_kpi_ribbon())

        # Splitter: Tab widget vs Inspector
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setObjectName("mainSplitter")
        self._splitter.setHandleWidth(3)
        self._splitter.setChildrenCollapsible(False)

        self.tabs = self._build_tabs()
        self._splitter.addWidget(self.tabs)

        self.inspector_panel = self._build_inspector_panel()
        self._splitter.addWidget(self.inspector_panel)

        self._splitter.setSizes([850, 340])
        card_layout.addWidget(self._splitter, 1)

        card_layout.addLayout(self._build_footer())

        # Live timestamp
        self._update_timestamp()
        self._ts_timer = QTimer(self)
        self._ts_timer.timeout.connect(self._update_timestamp)
        self._ts_timer.start(30_000)

    def _build_topbar(self) -> QHBoxLayout:
        topbar = QHBoxLayout()
        topbar.setContentsMargins(0, 0, 0, 0)
        topbar.setSpacing(8)

        icon_lbl = QLabel("🧪")
        icon_lbl.setFont(QFont("Segoe UI", 20))
        icon_lbl.setStyleSheet("background: transparent;")
        topbar.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)

        self.main_title = QLabel()
        self.main_title.setObjectName("mainTitle")
        self._add_glow(self.main_title, QColor(108, 207, 246, 120), blur=20)
        title_col.addWidget(self.main_title)

        sub_title = QLabel(
            "ASME B31.3 HYDROTEST & PNEUMATIC CLEARANCE  •  BLIND MATRIX  •  "
            "PUNCH LIST 'A' / 'B'  •  TURNOVER"
        )
        sub_title.setObjectName("subTitle")
        title_col.addWidget(sub_title)
        topbar.addLayout(title_col)
        topbar.addStretch()

        # Export filtered checkbox — the export handler uses this.
        self.chk_export_filtered = QCheckBox("Export Filtered Only")
        self.chk_export_filtered.setChecked(False)
        self.chk_export_filtered.setToolTip(
            "If checked, only rows from the currently active tab are exported."
        )
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
        topbar.addWidget(self.chk_export_filtered)

        self.btn_add_line = QPushButton("➕  ADD LINE  (Ctrl+N)")
        self.btn_add_line.setObjectName("actionBtn")
        self.btn_add_line.setMinimumHeight(36)
        self.btn_add_line.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_line.setToolTip("Add an ISO / Line boundary definition (Ctrl+N)")
        self.btn_add_line.clicked.connect(self._on_add_line)
        topbar.addWidget(self.btn_add_line)

        self.btn_add_punch = QPushButton("⚠️  LOG PUNCH")
        self.btn_add_punch.setObjectName("secondaryBtn")
        self.btn_add_punch.setMinimumHeight(36)
        self.btn_add_punch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_punch.setToolTip("Log a Category A/B/C punch item")
        self.btn_add_punch.clicked.connect(self._on_add_punch)
        topbar.addWidget(self.btn_add_punch)

        self.btn_dossier = QPushButton("📑  DOSSIER  (Ctrl+E)")
        self.btn_dossier.setObjectName("secondaryBtn")
        self.btn_dossier.setMinimumHeight(36)
        self.btn_dossier.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dossier.setToolTip("Export QC Test Dossier CSV (Ctrl+E)")
        self.btn_dossier.clicked.connect(self._on_export_dossier)
        topbar.addWidget(self.btn_dossier)

        min_btn = QPushButton("─")
        min_btn.setObjectName("minBtn")
        min_btn.setFixedSize(30, 30)
        min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        min_btn.setToolTip("Minimize")
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
        close_btn.setToolTip("Close (Escape)")
        close_btn.clicked.connect(self._on_close)
        topbar.addWidget(close_btn)

        return topbar

    def _build_header_frame(self) -> QFrame:
        self.header_frame = QFrame()
        self.header_frame.setObjectName("headerFrame")
        self.header_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_frame.setToolTip("Double-click anywhere to edit Package specs")

        h_layout = QHBoxLayout(self.header_frame)
        h_layout.setContentsMargins(14, 8, 14, 8)
        h_layout.setSpacing(16)

        self.lbl_system = QLabel()
        self.lbl_medium = QLabel()
        self.lbl_press  = QLabel()
        self.lbl_time   = QLabel()
        self.lbl_psv    = QLabel()

        for lbl in [self.lbl_system, self.lbl_medium, self.lbl_press,
                     self.lbl_time, self.lbl_psv]:
            lbl.setStyleSheet(
                "color: #7a9ab3; font-size: 11px; background: transparent;"
            )
            h_layout.addWidget(lbl)

        self.btn_edit_hdr = QPushButton("✏  EDIT")
        self.btn_edit_hdr.setObjectName("editHdrBtn")
        self.btn_edit_hdr.setFixedHeight(24)
        self.btn_edit_hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit_hdr.setToolTip("Edit test package specifications")
        self.btn_edit_hdr.clicked.connect(self._on_edit_header)
        self.btn_edit_hdr.setStyleSheet("""
            QPushButton#editHdrBtn {
                background: transparent; color: #6ccff6;
                border: 1px solid #1e3d5a; border-radius: 4px;
                padding: 0 8px; font-size: 10px; font-weight: 700;
            }
            QPushButton#editHdrBtn:hover {
                background: rgba(108, 207, 246, 0.1);
                border: 1px solid #6ccff6; color: #9fe7ff;
            }
        """)
        h_layout.addWidget(self.btn_edit_hdr)

        self.header_frame.mouseDoubleClickEvent = lambda e: self._on_edit_header()

        self._refresh_header_display()
        return self.header_frame

    def _build_kpi_ribbon(self) -> QHBoxLayout:
        stat_ribbon = QHBoxLayout()
        stat_ribbon.setSpacing(12)

        self.kpi_ready   = StatCard("TEST READINESS SCORE", "0%", "🎯", self.PRIMARY_LIGHT)
        self.kpi_joints  = StatCard("TOTAL JOINTS (100% NDT)", "0", "🔗", self.SUCCESS)
        self.kpi_punch_a = StatCard("CAT 'A' PUNCHES (BLOCKER)", "0 OPEN", "🚫", self.ERROR)
        self.kpi_punch_b = StatCard("CAT 'B' PUNCHES (POST-TEST)", "0 OPEN", "⏳", self.WARNING)

        stat_ribbon.addWidget(self.kpi_ready)
        stat_ribbon.addWidget(self.kpi_joints)
        stat_ribbon.addWidget(self.kpi_punch_a)
        stat_ribbon.addWidget(self.kpi_punch_b)
        return stat_ribbon

    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("pkgTabs")

        # Tab 1: Lines
        self.tab_lines = QWidget()
        t1_layout = QVBoxLayout(self.tab_lines)
        t1_layout.setContentsMargins(8, 8, 8, 8)
        self.line_table = QTableWidget()
        self.line_table.setObjectName("lineTable")
        self.line_table.setColumnCount(7)
        self.line_table.setHorizontalHeaderLabels([
            "Line Number", "ISO Drawing", "P&ID Ref", "Design Press",
            "Test Press", "Joints Count", "NDT Status",
        ])

        self.line_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.line_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.line_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.line_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        header1 = self.line_table.horizontalHeader()
        header1.setSectionsMovable(True)
        header1.setSectionsClickable(True)
        header1.setStretchLastSection(True)
        for col_idx in range(self.line_table.columnCount()):
            header1.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

        default_widths1 = [200, 180, 150, 110, 110, 100, 130]
        for col_idx, w in enumerate(default_widths1):
            self.line_table.setColumnWidth(col_idx, w)

        self.line_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.line_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.line_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.line_table.verticalHeader().setVisible(False)
        self.line_table.setShowGrid(False)
        self.line_table.setAlternatingRowColors(True)
        self.line_table.setSortingEnabled(True)
        self.line_table.setWordWrap(False)
        self.line_table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.line_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.line_table.customContextMenuRequested.connect(self._show_context_menu)
        self.line_table.itemSelectionChanged.connect(self._on_table_selection)
        self.line_table.doubleClicked.connect(self._on_add_line)

        t1_layout.addWidget(self.line_table)
        tabs.addTab(self.tab_lines, "📐  INCLUDED LINES & BOUNDARIES")

        # Tab 2: Blinds
        self.tab_blinds = QWidget()
        t2_layout = QVBoxLayout(self.tab_blinds)
        t2_layout.setContentsMargins(8, 8, 8, 8)
        self.blind_table = QTableWidget()
        self.blind_table.setObjectName("blindTable")
        self.blind_table.setColumnCount(7)
        self.blind_table.setHorizontalHeaderLabels([
            "Blind Tag", "Isolation Location", "Size & Rating", "Thickness",
            "Installed By", "Installation Status", "De-blinding Status",
        ])

        self.blind_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.blind_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.blind_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.blind_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        header2 = self.blind_table.horizontalHeader()
        header2.setSectionsMovable(True)
        header2.setSectionsClickable(True)
        header2.setStretchLastSection(True)
        for col_idx in range(self.blind_table.columnCount()):
            header2.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

        default_widths2 = [110, 240, 120, 100, 130, 150, 150]
        for col_idx, w in enumerate(default_widths2):
            self.blind_table.setColumnWidth(col_idx, w)

        self.blind_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.blind_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.blind_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.blind_table.verticalHeader().setVisible(False)
        self.blind_table.setShowGrid(False)
        self.blind_table.setAlternatingRowColors(True)
        self.blind_table.setSortingEnabled(True)
        self.blind_table.setWordWrap(False)
        self.blind_table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.blind_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.blind_table.customContextMenuRequested.connect(self._show_context_menu)
        self.blind_table.itemSelectionChanged.connect(self._on_table_selection)

        t2_layout.addWidget(self.blind_table)
        tabs.addTab(self.tab_blinds, "🛡️  BLIND & ISOLATION MATRIX")

        # Tab 3: Punches
        self.tab_punch = QWidget()
        t3_layout = QVBoxLayout(self.tab_punch)
        t3_layout.setContentsMargins(8, 8, 8, 8)
        self.punch_table = QTableWidget()
        self.punch_table.setObjectName("punchTable")
        self.punch_table.setColumnCount(7)
        self.punch_table.setHorizontalHeaderLabels([
            "Punch ID", "Cat", "Description & Deficiency", "Location / Drawing",
            "Discipline", "Logged Date", "Status",
        ])

        self.punch_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.punch_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.punch_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.punch_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        header3 = self.punch_table.horizontalHeader()
        header3.setSectionsMovable(True)
        header3.setSectionsClickable(True)
        header3.setStretchLastSection(True)
        for col_idx in range(self.punch_table.columnCount()):
            header3.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

        default_widths3 = [110, 70, 320, 160, 150, 110, 120]
        for col_idx, w in enumerate(default_widths3):
            self.punch_table.setColumnWidth(col_idx, w)

        self.punch_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.punch_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.punch_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.punch_table.verticalHeader().setVisible(False)
        self.punch_table.setShowGrid(False)
        self.punch_table.setAlternatingRowColors(True)
        self.punch_table.setSortingEnabled(True)
        self.punch_table.setWordWrap(False)
        self.punch_table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.punch_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.punch_table.customContextMenuRequested.connect(self._show_context_menu)
        self.punch_table.itemSelectionChanged.connect(self._on_table_selection)
        self.punch_table.doubleClicked.connect(self._on_add_punch)

        t3_layout.addWidget(self.punch_table)
        tabs.addTab(self.tab_punch, "⚠️  MASTER PUNCH LIST (CAT A / B)")

        return tabs

    def _build_inspector_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("inspectorCard")
        panel.setMinimumWidth(280)

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
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        head_lbl = QLabel("🔍   TEST PACKAGE CLEARANCE GATE")
        head_lbl.setObjectName("inspHead")
        layout.addWidget(head_lbl)

        div = QFrame()
        div.setObjectName("divider")
        div.setFixedHeight(1)
        layout.addWidget(div)

        self.insp_target = QLabel(self._pkg_meta["package_no"])
        self.insp_target.setObjectName("inspTarget")
        self.insp_target.setWordWrap(True)
        layout.addWidget(self.insp_target)

        self.insp_sub = QLabel(
            "Ensure 100% NDT clearance and zero open Category 'A' punches before "
            "authorizing water filling & pressurization."
        )
        self.insp_sub.setObjectName("inspSub")
        self.insp_sub.setWordWrap(True)
        layout.addWidget(self.insp_sub)

        self.meta_frame = QFrame()
        self.meta_frame.setObjectName("metaFrame")
        m_layout = QVBoxLayout(self.meta_frame)
        m_layout.setContentsMargins(10, 8, 10, 8)
        m_layout.setSpacing(5)

        self.m_status = QLabel()
        self.m_press  = QLabel()
        self.m_hold   = QLabel()
        self.m_psv    = QLabel()
        self.m_gauges = QLabel()

        for lbl in [self.m_status, self.m_press, self.m_hold, self.m_psv, self.m_gauges]:
            lbl.setStyleSheet(
                "color: #dfeaf5; font-size: 11px; background: transparent;"
            )
            lbl.setWordWrap(True)
            m_layout.addWidget(lbl)

        layout.addWidget(self.meta_frame)

        gate_lbl = QLabel("⚡   ADVANCE TEST GATE / LIFECYCLE:")
        gate_lbl.setStyleSheet(
            "color: #9fe7ff; font-size: 9px; font-weight: 800; "
            "letter-spacing: 1px; margin-top: 4px; background: transparent;"
        )
        layout.addWidget(gate_lbl)

        self.combo_gate = QComboBox()
        self.combo_gate.setObjectName("stageCombo")
        self.combo_gate.setMinimumHeight(32)
        self.combo_gate.addItems([
            "Package Preparation & Walkdown",
            "WJCS & NDT 100% Cleared",
            "Punch List 'A' Cleared",
            "Blinded & Manifold Installed",
            "Ready for Hydrotest",
            "Pressure Test In Progress",
            "Test Accepted by QC & Client",
            "De-watered, Dried & Reinstated",
            "Mechanical Completion Turnover",
        ])
        self.combo_gate.setCurrentText(self._pkg_meta["status"])
        self.combo_gate.setToolTip("Current test package lifecycle gate")
        self.combo_gate.currentTextChanged.connect(self._on_gate_changed)
        layout.addWidget(self.combo_gate)

        layout.addSpacing(4)

        self.btn_sign_test = QPushButton("✅  ISSUE HYDROTEST CERTIFICATE")
        self.btn_sign_test.setObjectName("actionBtn")
        self.btn_sign_test.setMinimumHeight(34)
        self.btn_sign_test.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sign_test.setToolTip("Issue the hydrotest certificate (Ctrl+D)")
        self.btn_sign_test.clicked.connect(self._on_issue_certificate)
        layout.addWidget(self.btn_sign_test)

        self.btn_clear_punch = QPushButton("🎯  CLEAR SELECTED PUNCH ITEM")
        self.btn_clear_punch.setObjectName("secondaryBtn")
        self.btn_clear_punch.setMinimumHeight(32)
        self.btn_clear_punch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_punch.setEnabled(False)
        self.btn_clear_punch.clicked.connect(self._on_clear_selected_punch)
        layout.addWidget(self.btn_clear_punch)

        layout.addStretch()

        scroll.setWidget(inner)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(scroll)

        return panel

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 2, 4, 0)

        self.lbl_count = QLabel(
            "All lines 100% inspected and verified against IFC isometric drawings."
        )
        self.lbl_count.setObjectName("footerLabel")
        footer.addWidget(self.lbl_count)

        footer.addStretch()

        self.lbl_timestamp = QLabel("")
        self.lbl_timestamp.setObjectName("footerLabel")
        footer.addWidget(self.lbl_timestamp)

        footer.addStretch()

        foot_tag = QLabel(
            "⚡  PipeAgent 5.0  •  Continuous Hydrotest Clearance & Mechanical Completion Engine"
        )
        foot_tag.setStyleSheet(
            "color: #3f6070; font-size: 10px; letter-spacing: 1px; background: transparent;"
        )
        footer.addWidget(foot_tag)
        return footer

    # ── Keyboard Shortcuts ────────────────────────────────────
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self, self._on_add_line)
        QShortcut(QKeySequence("Ctrl+E"), self, self._on_export_dossier)
        QShortcut(QKeySequence("Ctrl+D"), self, self._on_issue_certificate)
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)

        # Bind Delete to each table individually (WidgetShortcut) so typing
        # Delete inside a QLineEdit never removes a record.
        del_lines = QShortcut(
            QKeySequence("Delete"), self.line_table, self._on_remove_line
        )
        del_lines.setContext(Qt.ShortcutContext.WidgetShortcut)

        del_blinds = QShortcut(
            QKeySequence("Delete"), self.blind_table, self._on_remove_blind
        )
        del_blinds.setContext(Qt.ShortcutContext.WidgetShortcut)

        del_punches = QShortcut(
            QKeySequence("Delete"), self.punch_table, self._on_remove_punch
        )
        del_punches.setContext(Qt.ShortcutContext.WidgetShortcut)

    def _focus_search(self):
        idx = self.tabs.currentIndex()
        if idx == 0:
            self.line_table.setFocus()
        elif idx == 1:
            self.blind_table.setFocus()
        else:
            self.punch_table.setFocus()

    # ── Context Menu ──────────────────────────────────────────
    def _show_context_menu(self, pos):
        idx = self.tabs.currentIndex()
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #0b1624; color: #eef6ff;
                border: 1px solid #1e3d5a; border-radius: 6px; padding: 4px;
            }
            QMenu::item { padding: 8px 24px 8px 12px; border-radius: 4px; }
            QMenu::item:selected { background: #14334f; color: #9fe7ff; }
            QMenu::item:disabled { color: #3a5060; }
            QMenu::separator { height: 1px; background: #1e3d5a; margin: 4px 8px; }
        """)

        if idx == 0:
            selected = self._get_selected_line()

            act_ndt_clr = menu.addAction("✅  Override NDT Status - Cleared")
            act_ndt_clr.setEnabled(selected is not None)
            act_ndt_clr.triggered.connect(
                lambda: self._set_line_ndt_status("Cleared")
            )

            act_ndt_pend = menu.addAction("⏳  Override NDT Status - Pending")
            act_ndt_pend.setEnabled(selected is not None)
            act_ndt_pend.triggered.connect(
                lambda: self._set_line_ndt_status("Pending")
            )

            menu.addSeparator()

            act_new = menu.addAction("➕  Add Included Line  (Ctrl+N)")
            act_new.triggered.connect(self._on_add_line)

            act_delete = menu.addAction("🗑  Remove Line Boundary")
            act_delete.setEnabled(selected is not None)
            act_delete.triggered.connect(self._on_remove_line)

        elif idx == 1:
            selected = self._get_selected_blind()

            act_install = menu.addAction("🛡️  Status - Installed & Tagged")
            act_install.setEnabled(selected is not None)
            act_install.triggered.connect(
                lambda: self._set_blind_status(
                    "Installed & Tagged", "Pending Test"
                )
            )

            act_remove = menu.addAction("✅  Status - Restored & Signed-off")
            act_remove.setEnabled(selected is not None)
            act_remove.triggered.connect(
                lambda: self._set_blind_status(
                    "Installed & Tagged", "Removed & Restored"
                )
            )

            menu.addSeparator()

            act_delete = menu.addAction("🗑  Remove Blind Isolation Row")
            act_delete.setEnabled(selected is not None)
            act_delete.triggered.connect(self._on_remove_blind)

        else:
            selected = self._get_selected_punch()

            act_clr = menu.addAction("🎯  Clear Selected Punch Item")
            act_clr.setEnabled(
                selected is not None and selected.get("status") == "Open"
            )
            act_clr.triggered.connect(self._on_clear_selected_punch)

            menu.addSeparator()

            act_new = menu.addAction("➕  Log New Punch Item")
            act_new.triggered.connect(self._on_add_punch)

            act_delete = menu.addAction("🗑  Remove Punch Record")
            act_delete.setEnabled(selected is not None)
            act_delete.triggered.connect(self._on_remove_punch)

        menu.exec(self.tabs.currentWidget().mapToGlobal(pos))

    # ── Header Refresh ────────────────────────────────────────
    def _refresh_header_display(self):
        self.main_title.setText(
            f"PIPE AGENT  •  PRESSURE TEST PACKAGE CONTROL [{self._pkg_meta['package_no']}]"
        )
        self.lbl_system.setText(
            f"<b>SYSTEM:</b> <span style='color:#9fe7ff;'>"
            f"{self._pkg_meta['system']}</span>"
        )
        self.lbl_medium.setText(
            f"<b>MEDIUM:</b> <span style='color:#eef6ff;'>"
            f"{self._pkg_meta['medium']}</span>"
        )
        self.lbl_press.setText(
            f"<b>TEST PRESS:</b> <span style='color:#5cffaa; font-weight:bold;'>"
            f"{self._pkg_meta['test_press']}</span>"
        )
        self.lbl_time.setText(
            f"<b>HOLD TIME:</b> <span style='color:#7a9ab3;'>"
            f"{self._pkg_meta['holding_time']}</span>"
        )
        self.lbl_psv.setText(
            f"<b>RELIEF VALVE:</b> <span style='color:#7a9ab3;'>"
            f"{self._pkg_meta['relief_valve']}</span>"
        )

        self.m_status.setText(
            f"<b>Current Gate:</b> <span style='color:#5cffaa;'>"
            f"{self._pkg_meta['status']}</span>"
        )
        self.m_press.setText(
            f"<b>Test Pressure:</b> {self._pkg_meta['test_press']}"
        )
        self.m_hold.setText(
            f"<b>Holding Duration:</b> {self._pkg_meta['holding_time']}"
        )
        self.m_psv.setText(
            f"<b>Safety Valve Tag:</b> {self._pkg_meta['relief_valve']}"
        )
        self.m_gauges.setText(
            f"<b>Pressure Gauges:</b> {self._pkg_meta['gauges']}"
        )

    def _on_edit_header(self):
        modal = EditPkgMetaDialog(self._pkg_meta, self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return

        new_data = modal.get_data()
        self._pkg_meta.update(new_data)
        self.package_no = self._pkg_meta["package_no"]
        self.setWindowTitle(f"PipeAgent – Test Package • {self.package_no}")
        self._refresh_header_display()
        self._update_kpi()

        QMessageBox.information(
            self, "✅ Package Updated",
            "Test Package specifications have been successfully modified.",
        )

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
                /* QSS does not support gradients in `border`.
                   Depth comes from the drop shadow on the card. */
                border: 2px solid {self.PRIMARY};
                border-radius: 18px;
            }}
            QLabel#mainTitle {{
                color: {self.PRIMARY_LIGHT};
                font-size: 18px;
                font-weight: 900;
                letter-spacing: 2px;
                background: transparent;
            }}
            QLabel#subTitle {{
                color: {self.PRIMARY};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1.2px;
                background: transparent;
            }}
            QLabel#footerLabel {{
                color: #7a9ab3;
                font-size: 11px;
                background: transparent;
            }}
            QFrame#headerFrame {{
                background: #081422;
                border: 1px solid #142e47;
                border-radius: 8px;
            }}
            QFrame#headerFrame:hover {{ border: 1px solid #6ccff6; }}
            QFrame#divider {{
                background: rgba(108, 207, 246, 0.3);
                border: none;
            }}
            QTabWidget#pkgTabs::pane {{
                border: 1px solid #142e47;
                background: #07111c;
                border-radius: 10px;
            }}
            QTabBar::tab {{
                background: #091726;
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
            QPushButton#secondaryBtn:disabled {{
                background: #0a1420;
                color: #3a5060;
                border: 1px solid #0f1f30;
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
            QTableWidget {{
                background: #07111c;
                alternate-background-color: #091520;
                color: {self.TEXT_MAIN};
                border: none;
                gridline-color: transparent;
                selection-background-color: #12334f;
                selection-color: {self.PRIMARY_LIGHT};
                font-size: 12px;
            }}
            QTableWidget::item {{
                padding: 7px 9px;
                border-bottom: 1px solid #0c1f30;
            }}
            QTableWidget::item:selected {{
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
                padding: 8px 9px;
            }}
            QScrollBar:vertical {{
                background: #07101a; width: 10px;
                border-radius: 5px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: #1e3d5a; border-radius: 5px; min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {self.PRIMARY}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: #07101a; height: 10px;
                border-radius: 5px; margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: #1e3d5a; border-radius: 5px; min-width: 30px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: {self.PRIMARY}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            QFrame#inspectorCard {{
                background: #091726;
                border: 1px solid #183854;
                border-radius: 10px;
            }}
            QLabel#inspHead {{
                color: {self.PRIMARY_LIGHT};
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 1.5px;
                background: transparent;
            }}
            QLabel#inspTarget {{
                color: {self.ACCENT};
                font-size: 15px;
                font-weight: 800;
                background: transparent;
                font-family: Consolas, monospace;
            }}
            QLabel#inspSub {{
                color: {self.TEXT_MUTED};
                font-size: 11px;
                background: transparent;
            }}
            QFrame#metaFrame {{
                background: #06101c;
                border: 1px solid #10263b;
                border-radius: 8px;
            }}
            QComboBox#stageCombo {{
                background: #07101a;
                color: {self.PRIMARY_LIGHT};
                border: 1px solid #18364a;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }}
            QSplitter::handle {{
                background: #102538;
                border-radius: 2px;
            }}
            QSplitter::handle:hover {{ background: {self.PRIMARY}; }}
        """

    # ── Helper Utilities ──────────────────────────────────────
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

    # ── Sort-safe selection helpers ───────────────────────────
    def _get_selected_line(self) -> Optional[Dict[str, Any]]:
        rows = self.line_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.line_table.item(rows[0].row(), 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _get_selected_blind(self) -> Optional[Dict[str, Any]]:
        rows = self.blind_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.blind_table.item(rows[0].row(), 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _get_selected_punch(self) -> Optional[Dict[str, Any]]:
        rows = self.punch_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.punch_table.item(rows[0].row(), 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _find_line_index(self, line_id: str) -> int:
        for idx, l in enumerate(self._lines):
            if l.get("line_id") == line_id:
                return idx
        return -1

    def _find_blind_index(self, blind_id: str) -> int:
        for idx, b in enumerate(self._blinds):
            if b.get("blind_id") == blind_id:
                return idx
        return -1

    def _find_punch_index(self, punch_id: str) -> int:
        for idx, p in enumerate(self._punches):
            if p.get("punch_id") == punch_id:
                return idx
        return -1

    def _reselect_row_by_id(
        self, table: QTableWidget, id_key: str, id_val: str
    ):
        for row_idx in range(table.rowCount()):
            item = table.item(row_idx, 0)
            if item is None:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get(id_key) == id_val:
                table.selectRow(row_idx)
                return

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

        if (self._drag_pos and not self._drag_edge
                and event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return

        edge = self._get_resize_edge(event.position().toPoint())
        self._update_cursor_for_edge(edge)

    def mouseReleaseEvent(self, event: QMouseEvent):  # noqa: N802
        self._drag_pos = None
        self._drag_edge = None
        self._drag_geometry = None
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

    # ── Populate Tables ───────────────────────────────────────
    def _populate_all(self):
        self._populate_lines_table()
        self._populate_blinds_table()
        self._populate_punches_table()

    def _populate_lines_table(self):
        self.line_table.setSortingEnabled(False)
        self.line_table.setRowCount(0)

        for r_idx, l in enumerate(self._lines):
            self.line_table.insertRow(r_idx)

            item_line = QTableWidgetItem(l["line_no"])
            item_line.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            item_line.setForeground(QColor(self.PRIMARY_LIGHT))
            # Store the record on column 0 so lookups survive sorting.
            item_line.setData(Qt.ItemDataRole.UserRole, l)
            self.line_table.setItem(r_idx, 0, item_line)

            item_iso = QTableWidgetItem(l["iso_no"])
            item_iso.setForeground(QColor(self.TEXT_MAIN))
            item_iso.setToolTip(l["iso_no"])
            self.line_table.setItem(r_idx, 1, item_iso)

            item_pid = QTableWidgetItem(l["pid_no"])
            item_pid.setForeground(QColor("#708fa8"))
            self.line_table.setItem(r_idx, 2, item_pid)

            item_dp = QTableWidgetItem(l["design_p"])
            item_dp.setForeground(QColor(self.TEXT_MUTED))
            self.line_table.setItem(r_idx, 3, item_dp)

            item_tp = QTableWidgetItem(l["test_p"])
            item_tp.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            item_tp.setForeground(QColor(self.ACCENT))
            self.line_table.setItem(r_idx, 4, item_tp)

            item_j = QTableWidgetItem(str(l["joints"]))
            item_j.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_j.setForeground(QColor(self.TEXT_MAIN))
            self.line_table.setItem(r_idx, 5, item_j)

            item_ndt = QTableWidgetItem(f" ● {l['ndt_status']} ")
            item_ndt.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item_ndt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if l["ndt_status"] == "Cleared":
                item_ndt.setForeground(QColor(self.SUCCESS))
            else:
                item_ndt.setForeground(QColor(self.WARNING))
            self.line_table.setItem(r_idx, 6, item_ndt)

        self.line_table.setSortingEnabled(True)

        if self._lines:
            self.line_table.selectRow(0)

    def _populate_blinds_table(self):
        self.blind_table.setSortingEnabled(False)
        self.blind_table.setRowCount(0)

        for r_idx, b in enumerate(self._blinds):
            self.blind_table.insertRow(r_idx)

            item_tag = QTableWidgetItem(b["tag"])
            item_tag.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            item_tag.setForeground(QColor(self.PRIMARY_LIGHT))
            item_tag.setData(Qt.ItemDataRole.UserRole, b)
            self.blind_table.setItem(r_idx, 0, item_tag)

            item_loc = QTableWidgetItem(b["location"])
            item_loc.setForeground(QColor(self.TEXT_MAIN))
            item_loc.setToolTip(b["location"])
            self.blind_table.setItem(r_idx, 1, item_loc)

            item_sz = QTableWidgetItem(b["size"])
            item_sz.setForeground(QColor(self.ACCENT))
            self.blind_table.setItem(r_idx, 2, item_sz)

            item_thk = QTableWidgetItem(b["thick"])
            item_thk.setForeground(QColor(self.TEXT_MUTED))
            self.blind_table.setItem(r_idx, 3, item_thk)

            item_by = QTableWidgetItem(b["installed_by"])
            item_by.setForeground(QColor("#708fa8"))
            self.blind_table.setItem(r_idx, 4, item_by)

            item_ins = QTableWidgetItem(b["install_status"])
            item_ins.setForeground(QColor(self.SUCCESS))
            self.blind_table.setItem(r_idx, 5, item_ins)

            item_rem = QTableWidgetItem(b["removal_status"])
            if "Removed" in b["removal_status"]:
                item_rem.setForeground(QColor(self.SUCCESS))
            else:
                item_rem.setForeground(QColor(self.WARNING))
            self.blind_table.setItem(r_idx, 6, item_rem)

        self.blind_table.setSortingEnabled(True)

    def _populate_punches_table(self):
        self.punch_table.setSortingEnabled(False)
        self.punch_table.setRowCount(0)

        for r_idx, p in enumerate(self._punches):
            self.punch_table.insertRow(r_idx)

            item_id = QTableWidgetItem(p["punch_id"])
            item_id.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            item_id.setForeground(QColor(self.PRIMARY_LIGHT))
            item_id.setData(Qt.ItemDataRole.UserRole, p)
            self.punch_table.setItem(r_idx, 0, item_id)

            item_cat = QTableWidgetItem(p["cat"])
            item_cat.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item_cat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if "Cat A" in p["cat"]:
                item_cat.setForeground(QColor(self.ERROR))
            else:
                item_cat.setForeground(QColor(self.WARNING))
            self.punch_table.setItem(r_idx, 1, item_cat)

            item_desc = QTableWidgetItem(p["desc"])
            item_desc.setForeground(QColor(self.TEXT_MAIN))
            item_desc.setToolTip(p["desc"])
            self.punch_table.setItem(r_idx, 2, item_desc)

            item_loc = QTableWidgetItem(p["location"])
            item_loc.setForeground(QColor(self.TEXT_MUTED))
            self.punch_table.setItem(r_idx, 3, item_loc)

            item_disc = QTableWidgetItem(p["discipline"])
            item_disc.setForeground(QColor("#a2c2dc"))
            self.punch_table.setItem(r_idx, 4, item_disc)

            item_dt = QTableWidgetItem(p["logged_date"])
            item_dt.setFont(QFont("Consolas", 9))
            item_dt.setForeground(QColor("#708fa8"))
            self.punch_table.setItem(r_idx, 5, item_dt)

            item_st = QTableWidgetItem(f" ● {p['status']} ")
            item_st.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item_st.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if p["status"] == "Cleared":
                item_st.setForeground(QColor(self.SUCCESS))
            else:
                item_st.setForeground(
                    QColor(self.ERROR if "Cat A" in p["cat"] else self.WARNING)
                )
            self.punch_table.setItem(r_idx, 6, item_st)

        self.punch_table.setSortingEnabled(True)

    def _update_kpi(self):
        total_joints = sum(l.get("joints", 0) for l in self._lines)

        open_punch_a = sum(
            1 for p in self._punches
            if "Cat A" in p["cat"] and p["status"] == "Open"
        )
        open_punch_b = sum(
            1 for p in self._punches
            if "Cat B" in p["cat"] and p["status"] == "Open"
        )

        # `all(...)` on an empty list returns True — check for emptiness.
        ndt_cleared = bool(self._lines) and all(
            l.get("ndt_status") == "Cleared" for l in self._lines
        )

        readiness = 100
        if open_punch_a > 0:
            readiness -= (30 + 10 * open_punch_a)
        if not ndt_cleared:
            readiness -= 40
        if open_punch_b > 2:
            readiness -= 10
        readiness = max(5, min(100, readiness))

        self.kpi_ready.update_value(f"{readiness}%")
        self.kpi_joints.update_value(
            f"{total_joints} (100% OK)" if ndt_cleared
            else f"{total_joints} (NDT Pending)"
        )
        self.kpi_punch_a.update_value(f"{open_punch_a} OPEN")
        self.kpi_punch_b.update_value(f"{open_punch_b} OPEN")

        self.lbl_count.setText(
            f"Test package contains {len(self._lines)} line boundaries. "
            f"Active open Cat 'A' blockades: {open_punch_a} item(s)."
        )

    # ── Table Selection & Inspector Update ────────────────────
    def _on_table_selection(self):
        idx = self.tabs.currentIndex()
        if idx == 2:
            selected_punch = self._get_selected_punch()
            self.btn_clear_punch.setEnabled(
                selected_punch is not None
                and selected_punch.get("status") == "Open"
            )
        else:
            self.btn_clear_punch.setEnabled(False)

    # ── Quick Status Override Toggles ─────────────────────────
    def _set_line_ndt_status(self, new_status: str):
        selected = self._get_selected_line()
        if selected is None:
            return

        idx = self._find_line_index(selected.get("line_id", ""))
        if idx < 0:
            return

        self._lines[idx]["ndt_status"] = new_status
        target_id = self._lines[idx]["line_id"]

        self._populate_lines_table()
        self._update_kpi()
        self._reselect_row_by_id(self.line_table, "line_id", target_id)

    def _set_blind_status(self, inst_status: str, rem_status: str):
        selected = self._get_selected_blind()
        if selected is None:
            return

        idx = self._find_blind_index(selected.get("blind_id", ""))
        if idx < 0:
            return

        self._blinds[idx]["install_status"] = inst_status
        self._blinds[idx]["removal_status"] = rem_status
        target_id = self._blinds[idx]["blind_id"]

        self._populate_blinds_table()
        self._update_kpi()
        self._reselect_row_by_id(self.blind_table, "blind_id", target_id)

    # ── Lifecycle Gate Changed ────────────────────────────────
    def _on_gate_changed(self, new_gate: str):
        self._pkg_meta["status"] = new_gate
        self._refresh_header_display()

    # ── Add/Remove Items Actions ──────────────────────────────
    def _on_add_line(self):
        existing_lines = [l["line_no"] for l in self._lines]
        modal = AddLineDialog(existing_lines=existing_lines, parent=self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        new_l = modal.get_data()
        self._lines.append(new_l)
        self._populate_lines_table()
        self._update_kpi()
        self._reselect_row_by_id(self.line_table, "line_id", new_l["line_id"])

    def _on_remove_line(self):
        selected = self._get_selected_line()
        if selected is None:
            return

        reply = QMessageBox.warning(
            self, "⚠ Remove Line Boundary",
            f"Are you sure you want to remove Line <b>{selected['line_no']}</b> "
            f"from this test package boundary specs?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        idx = self._find_line_index(selected.get("line_id", ""))
        if idx < 0:
            return
        self._lines.pop(idx)
        self._populate_lines_table()
        self._update_kpi()

    def _on_remove_blind(self):
        selected = self._get_selected_blind()
        if selected is None:
            return

        reply = QMessageBox.warning(
            self, "⚠ Remove Isolation Blind",
            f"Are you sure you want to remove Blind <b>{selected['tag']}</b> "
            f"({selected['size']}) from the isolation matrix?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        idx = self._find_blind_index(selected.get("blind_id", ""))
        if idx < 0:
            return
        self._blinds.pop(idx)
        self._populate_blinds_table()
        self._update_kpi()

    def _on_add_punch(self):
        modal = AddPunchDialog(self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        new_p = modal.get_data()
        self._punches.insert(0, new_p)
        self._populate_punches_table()
        self._update_kpi()
        self.tabs.setCurrentIndex(2)
        self._reselect_row_by_id(self.punch_table, "punch_id", new_p["punch_id"])

    def _on_remove_punch(self):
        selected = self._get_selected_punch()
        if selected is None:
            return

        reply = QMessageBox.warning(
            self, "⚠ Remove Punch Item",
            f"Are you sure you want to delete Punch <b>{selected['punch_id']}</b>?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        idx = self._find_punch_index(selected.get("punch_id", ""))
        if idx < 0:
            return
        self._punches.pop(idx)
        self._populate_punches_table()
        self._update_kpi()

    def _on_clear_selected_punch(self):
        selected = self._get_selected_punch()
        if selected is None:
            QMessageBox.warning(
                self, "Selection Required",
                "Please select a punch row in Tab 3 to clear."
            )
            self.tabs.setCurrentIndex(2)
            return

        idx = self._find_punch_index(selected.get("punch_id", ""))
        if idx < 0:
            return

        self._punches[idx]["status"] = "Cleared"
        target_id = self._punches[idx]["punch_id"]

        self._populate_punches_table()
        self._update_kpi()
        self._reselect_row_by_id(self.punch_table, "punch_id", target_id)

        QMessageBox.information(
            self, "✅ Punch Cleared",
            f"Punch Item <b>{selected['punch_id']}</b> has been signed off and cleared."
        )

    # ── Issue Certificate & Export ────────────────────────────
    def _on_issue_certificate(self):
        open_a = sum(
            1 for p in self._punches
            if "Cat A" in p["cat"] and p["status"] == "Open"
        )
        if open_a > 0:
            QMessageBox.warning(
                self, "🚨 Pre-Hydro Blocked",
                f"Cannot authorize hydrotest! There are still <b>{open_a} open "
                f"Category 'A' punches</b>. Clear blockers first."
            )
            return

        self.combo_gate.setCurrentText("Test Accepted by QC & Client")
        QMessageBox.information(
            self, "✅ Hydrotest Certificate Issued",
            f"<b>HYDROSTATIC PRESSURE TEST CERTIFICATE GRANTED</b><br><br>"
            f"• <b>Package:</b> {self._pkg_meta['package_no']}<br>"
            f"• <b>Test Pressure:</b> {self._pkg_meta['test_press']} "
            f"(Holding: {self._pkg_meta['holding_time']})<br>"
            f"• <b>QC Inspector:</b> Verified & Signed<br>"
            f"• <b>Authorized Client Representative:</b> Countersigned<br><br>"
            f"<i>De-pressurization, de-watering, and reinstatement procedures authorized.</i>"
        )

    def _on_export_dossier(self):
        # Export behaviour: when filtered, only include records from the
        # currently active tab. Otherwise export the full package.
        filtered = self.chk_export_filtered.isChecked()
        active_tab = self.tabs.currentIndex()

        if filtered and active_tab == 0:
            export_lines = list(self._lines)
            export_blinds: List[Dict[str, Any]] = []
            export_punches: List[Dict[str, Any]] = []
            label = "lines only"
        elif filtered and active_tab == 1:
            export_lines = []
            export_blinds = list(self._blinds)
            export_punches = []
            label = "blinds only"
        elif filtered and active_tab == 2:
            export_lines = []
            export_blinds = []
            export_punches = list(self._punches)
            label = "punches only"
        else:
            export_lines = list(self._lines)
            export_blinds = list(self._blinds)
            export_punches = list(self._punches)
            label = "full package"

        default_name = f"Test_Package_{self.package_no}_Dossier.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Test Package Dossier",
            default_name, "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["═══ HYDROTEST QUALITY DOSSIER OVERVIEW ═══"])
                writer.writerow(["Package Number", self._pkg_meta["package_no"]])
                writer.writerow(["System Boundary", self._pkg_meta["system"]])
                writer.writerow(["Test Medium", self._pkg_meta["medium"]])
                writer.writerow(["Test Pressure", self._pkg_meta["test_press"]])
                writer.writerow(["Design Pressure", self._pkg_meta["design_press"]])
                writer.writerow(["Hold Time", self._pkg_meta["holding_time"]])
                writer.writerow(["Safety Relief Valve", self._pkg_meta["relief_valve"]])
                writer.writerow(["Calibration Gauges", self._pkg_meta["gauges"]])
                writer.writerow(["Clearance Status", self._pkg_meta["status"]])
                writer.writerow(["Export Scope", label])
                writer.writerow([])

                if export_lines:
                    writer.writerow(["═══ INCLUDED LINES & BOUNDARY SPEC ═══"])
                    writer.writerow([
                        "Line Number", "ISO Drawing", "P&ID Ref", "Design Press",
                        "Test Press", "Joints Count", "NDT Status",
                    ])
                    for l in export_lines:
                        writer.writerow([
                            l["line_no"], l["iso_no"], l["pid_no"],
                            l["design_p"], l["test_p"], l["joints"], l["ndt_status"],
                        ])
                    writer.writerow([])

                if export_blinds:
                    writer.writerow(["═══ BLIND & ISOLATION REGISTRY ═══"])
                    writer.writerow([
                        "Blind Tag", "Isolation Location", "Size & Rating", "Thickness",
                        "Installed By", "Installation Status", "De-blinding Status",
                    ])
                    for b in export_blinds:
                        writer.writerow([
                            b["tag"], b["location"], b["size"], b["thick"],
                            b["installed_by"], b["install_status"], b["removal_status"],
                        ])
                    writer.writerow([])

                if export_punches:
                    writer.writerow(["═══ MASTER PUNCH LIST ═══"])
                    writer.writerow([
                        "Punch ID", "Category", "Description", "Location / Drawing",
                        "Discipline", "Logged Date", "Status",
                    ])
                    for p in export_punches:
                        writer.writerow([
                            p["punch_id"], p["cat"], p["desc"], p["location"],
                            p["discipline"], p["logged_date"], p["status"],
                        ])

            QMessageBox.information(
                self, "✅ Dossier Exported",
                f"Test package QC dossier ({label}) successfully exported to:\n\n{path}",
            )
        except PermissionError:
            QMessageBox.critical(
                self, "Export Error",
                "Permission denied. The file may be open in another application.\n"
                "Please close it and try again.",
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Export Error",
                f"Could not export test package dossier: {e}",
            )

    # ── Graceful close ────────────────────────────────────────
    def _cleanup(self):
        """Stop every timer we own. Safe to call twice."""
        if self._is_closed:
            return
        self._is_closed = True

        if hasattr(self, "_particles"):
            try:
                self._particles.stop()
            except RuntimeError:
                pass

        if self._ts_timer is not None:
            self._ts_timer.stop()
            self._ts_timer = None

    def _on_close(self):
        self._cleanup()
        if self.isVisible():
            self.accept()

    def done(self, result: int):  # noqa: D401
        """
        Intercept every closing path (accept / reject / Escape / X).
        Cleanup runs exactly once, before the dialog is destroyed.
        """
        self._cleanup()
        super().done(result)

    def closeEvent(self, event):  # noqa: N802
        # Qt may still deliver this for Alt+F4 / WM close.
        self._cleanup()
        super().closeEvent(event)


# ════════════════════════════════════════════════════════════════
#  STANDALONE TEST RUNNER
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    dialog = TestPackageDialog(package_no="TP-HYD-2104-03")
    dialog.show()
    dialog.exec()

    sys.exit(0)