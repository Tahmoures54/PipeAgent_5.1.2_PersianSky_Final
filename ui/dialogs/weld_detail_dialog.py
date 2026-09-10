# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Weld Joint Traveler & QC Passport Dialog (WJCS)
═══════════════════════════════════════════════════════════════════════════
Version : 5.0 (Refactored, hardened, production-ready)
Engine  : PyQt6
Design  : Cinematic dark-tech theme matching PipeAgent Suite

Fixes in this revision
──────────────────────
🔴 P0  Missing QMenu import : added to QtWidgets imports (was crashing on
                             right-click inside the pass/NDT tables)
🔴 P0  Card border          : replaced invalid `border: ... qlineargradient`
                             with a solid color + drop shadow
🔴 P0  GlowLineEdit         : no longer calls deleteLater() on an animation
                             that Qt owns (DeleteWhenStopped)
🔴 P0  Sort-safe selection  : each row stores its record dict on
                             QTableWidgetItem.UserRole
🔴 P0  Stable ids           : every pass and NDT record has a stable id;
                             lookups no longer rely on `list.index(dict)`
🟠 P1  Cleanup              : `_cleanup()` idempotent + `done()` overridden
🟠 P1  Particle geometry    : set immediately after creation
🟠 P1  KPI stylesheet       : `update_value` now respects the tile's own
                             accent — no more global setStyleSheet overwrite
🟠 P1  Sub-dialog buttons   : AddWeldPassDialog and AddNDTExamDialog now
                             have a CANCEL button (feature parity with the
                             other sub-modals in the suite)
🟠 P1  Signal storm on load : NDT/pass tables block signals during populate
🟡 P2  ParticleField        : count 30 → 14, tick 60ms → 100ms, paints
                             only when visible
🟡 P2  _clear_inspector     : driven by a declared label spec
🟢 P3  Tooltips             : on every field / button
🟢 P3  _today() helper      : single source for the current date
"""

from __future__ import annotations

import os
import sys
import csv
import random
import uuid
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any

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
    QSpinBox, QTextEdit, QScrollArea, QCheckBox,
    QMenu,  # 🔧 Added — was missing in the previous version.
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#  UTILITIES
# ════════════════════════════════════════════════════════════════

def _uid(prefix: str = "R") -> str:
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
    """QLineEdit with focus glow — animation lifetime fixed."""

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

    def set_accent(self, color: str):
        """Dynamically retint the tile (used when status flips)."""
        self._accent = color
        self.val_lbl.setStyleSheet(
            f"color: {color}; background: transparent;"
        )
        self._apply_style()


# ════════════════════════════════════════════════════════════════
#  ADD WELD PASS DIALOG
# ════════════════════════════════════════════════════════════════

class AddWeldPassDialog(QDialog):
    """Sub-modal for adding a weld pass to the execution log."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Weld Pass")
        self.setMinimumSize(480, 520)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos: Optional[QPoint] = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("passCard")
        card.setStyleSheet("""
            QWidget#passCard {
                background: #0b1624;
                border: 2px solid #6ccff6;
                border-radius: 14px;
            }
            QLabel { color: #9fe7ff; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
            QLineEdit, QComboBox {
                background: #07101a; color: #eef6ff;
                border: 1px solid #18364a; border-radius: 6px;
                padding: 6px 10px; font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #6ccff6; }
            QComboBox QAbstractItemView {
                background: #07101a;
                color: #eef6ff;
                selection-background-color: #14334f;
                selection-color: #9fe7ff;
                border: 1px solid #18364a;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(9)

        # Header
        head = QHBoxLayout()
        title = QLabel("🔥   LOG WELD PASS DETAILS")
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
        layout.addSpacing(4)

        layout.addWidget(QLabel("WELD PASS TYPE *"))
        self.in_pass_type = QComboBox()
        self.in_pass_type.addItems([
            "Root Pass", "Hot Pass", "Filling Pass", "Capping Pass"
        ])
        self.in_pass_type.setToolTip("Welding pass sequence")
        layout.addWidget(self.in_pass_type)

        layout.addWidget(QLabel("WELD PROCESS"))
        self.in_proc = QComboBox()
        self.in_proc.addItems([
            "GTAW (TIG)", "SMAW (Stick / Low-H)",
            "FCAW (Flux-Cored)", "GMAW (MIG)",
        ])
        self.in_proc.setToolTip("Welding process")
        layout.addWidget(self.in_proc)

        layout.addWidget(QLabel("WELDER STAMP ID *"))
        self.in_welder = QLineEdit()
        self.in_welder.setPlaceholderText("e.g. W-04 / W-12")
        self.in_welder.setToolTip("Welder stamp identifier — required")
        layout.addWidget(self.in_welder)

        row = QHBoxLayout()
        col_fil = QVBoxLayout()
        col_fil.addWidget(QLabel("FILLER METAL / ELECTRODE SPEC"))
        self.in_filler = QLineEdit()
        self.in_filler.setPlaceholderText("e.g. ER70S-6 (Ø 2.4 mm)")
        col_fil.addWidget(self.in_filler)
        row.addLayout(col_fil)

        col_heat = QVBoxLayout()
        col_heat.addWidget(QLabel("FILLER METAL HEAT / LOT NO."))
        self.in_heat = QLineEdit()
        self.in_heat.setPlaceholderText("e.g. HT-99214")
        col_heat.addWidget(self.in_heat)
        row.addLayout(col_heat)
        layout.addLayout(row)

        layout.addSpacing(10)

        submit_btn = QPushButton("💾  LOG PASS TO PASSPORT")
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
        if not self.in_welder.text().strip():
            QMessageBox.warning(
                self, "Validation Error", "Welder stamp is required."
            )
            self.in_welder.setFocus()
            return
        self.accept()

    def get_data(self) -> Dict[str, Any]:
        return {
            "pass_id": _uid("WPS"),
            "pass_type": self.in_pass_type.currentText(),
            "process": self.in_proc.currentText(),
            "welder_stamp": self.in_welder.text().strip().upper(),
            "filler_metal": self.in_filler.text().strip() or "Standard Wire",
            "filler_heat": self.in_heat.text().strip().upper() or "N/A",
            "date": _today(),
            "inspector": "QC Eng. Farhadi",
        }


# ════════════════════════════════════════════════════════════════
#  ADD NDT EXAMINATION RECORD DIALOG
# ════════════════════════════════════════════════════════════════

class AddNDTExamDialog(QDialog):
    """Sub-modal for registering an NDT / Inspection report under the joint."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add NDT Examination")
        self.setMinimumSize(480, 560)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos: Optional[QPoint] = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("ndtCard")
        card.setStyleSheet("""
            QWidget#ndtCard {
                background: #0b1624;
                border: 2px solid #6ccff6;
                border-radius: 14px;
            }
            QLabel { color: #9fe7ff; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
            QLineEdit, QComboBox {
                background: #07101a; color: #eef6ff;
                border: 1px solid #18364a; border-radius: 6px;
                padding: 6px 10px; font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #6ccff6; }
            QComboBox QAbstractItemView {
                background: #07101a;
                color: #eef6ff;
                selection-background-color: #14334f;
                selection-color: #9fe7ff;
                border: 1px solid #18364a;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(9)

        # Header
        head = QHBoxLayout()
        title = QLabel("🔬   ADD NDT / INSPECTION RECORD")
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
        layout.addSpacing(4)

        layout.addWidget(QLabel("EXAMINATION METHOD *"))
        self.in_method = QComboBox()
        self.in_method.addItems([
            "Visual Testing (VT)", "Radiographic Testing (RT)",
            "Ultrasonic Testing (UT)", "Liquid Penetrant (PT)",
            "Magnetic Particle (MT)", "Hardness Testing (HT)",
        ])
        self.in_method.setToolTip("NDT examination method")
        layout.addWidget(self.in_method)

        layout.addWidget(QLabel("INSPECTION REPORT NUMBER *"))
        self.in_report_no = QLineEdit()
        self.in_report_no.setPlaceholderText("e.g. NDT-RT-2025-088")
        self.in_report_no.setToolTip("Unique NDT report identifier — required")
        layout.addWidget(self.in_report_no)

        layout.addWidget(QLabel("QC EVALUATION RESULT"))
        self.in_eval = QComboBox()
        self.in_eval.addItems([
            "ACCEPTED (Satisfactory)",
            "REJECTED (Repair Required)",
            "RE-EXAMINATION REQUIRED",
        ])
        self.in_eval.setToolTip("QC evaluation result")
        layout.addWidget(self.in_eval)

        layout.addWidget(QLabel("EXAMINER / INSPECTOR SIGNATURE"))
        self.in_inspector = QLineEdit()
        self.in_inspector.setPlaceholderText("e.g. QC Inspector Farhadi")
        self.in_inspector.setToolTip("Name of the NDT examiner")
        layout.addWidget(self.in_inspector)

        layout.addWidget(QLabel("REMARKS / DEFECT COORDINATES (IF REJECT)"))
        self.in_remarks = QLineEdit()
        self.in_remarks.setPlaceholderText("e.g. slag inclusion at sector 1-2")
        self.in_remarks.setToolTip("Defect details or remarks")
        layout.addWidget(self.in_remarks)

        layout.addSpacing(10)

        submit_btn = QPushButton("💾  LOG INSPECTION TO PASSPORT")
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
        if not self.in_report_no.text().strip():
            QMessageBox.warning(
                self, "Validation Error", "Report Number is required."
            )
            self.in_report_no.setFocus()
            return
        self.accept()

    def get_data(self) -> Dict[str, Any]:
        return {
            "ndt_id": _uid("NDT"),
            "method": self.in_method.currentText(),
            "report_no": self.in_report_no.text().strip().upper(),
            "date": _today(),
            "result": self.in_eval.currentText().split(" (")[0],
            "inspector": self.in_inspector.text().strip() or "QC Inspector",
            "remarks": self.in_remarks.text().strip() or "Satisfactory",
        }


# ════════════════════════════════════════════════════════════════
#  EDIT JOINT METADATA DIALOG
# ════════════════════════════════════════════════════════════════

class EditJointMetaDialog(QDialog):
    """Sub-modal for editing Weld Joint Header technical specifications."""

    def __init__(self, current_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Joint Specifications")
        self.setMinimumSize(500, 520)
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

        title = QLabel("📐   EDIT JOINT PASSPORT METADATA")
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

        layout.addWidget(QLabel("WELD JOINT NO / TAG ID"))
        self.in_joint = QLineEdit()
        self.in_joint.setText(str(self._current_data.get("joint_no", "")))
        layout.addWidget(self.in_joint)

        layout.addWidget(QLabel("SPOOL DRAWING ID"))
        self.in_spool = QLineEdit()
        self.in_spool.setText(str(self._current_data.get("spool_id", "")))
        layout.addWidget(self.in_spool)

        layout.addWidget(QLabel("ISOMETRIC DRAWING REF"))
        self.in_iso = QLineEdit()
        self.in_iso.setText(str(self._current_data.get("iso_no", "")))
        layout.addWidget(self.in_iso)

        layout.addWidget(QLabel("LINE NUMBER / SYSTEM"))
        self.in_line = QLineEdit()
        self.in_line.setText(str(self._current_data.get("line_no", "")))
        layout.addWidget(self.in_line)

        row = QHBoxLayout()
        col_sz = QVBoxLayout()
        col_sz.addWidget(QLabel("NOMINAL NPS SIZE"))
        self.in_size = QLineEdit()
        self.in_size.setText(str(self._current_data.get("size", "")))
        col_sz.addWidget(self.in_size)
        row.addLayout(col_sz)

        col_wps = QVBoxLayout()
        col_wps.addWidget(QLabel("WPS NO"))
        self.in_wps = QLineEdit()
        self.in_wps.setText(str(self._current_data.get("wps_no", "")))
        col_wps.addWidget(self.in_wps)
        row.addLayout(col_wps)
        layout.addLayout(row)

        layout.addSpacing(10)

        submit_btn = QPushButton("💾  SAVE PASSPORT CHANGES")
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
            "joint_no": self.in_joint.text().strip(),
            "spool_id": self.in_spool.text().strip(),
            "iso_no": self.in_iso.text().strip(),
            "line_no": self.in_line.text().strip(),
            "size": self.in_size.text().strip(),
            "wps_no": self.in_wps.text().strip(),
        }


# ════════════════════════════════════════════════════════════════
#  MAIN WELD JOINT DETAIL DIALOG
# ════════════════════════════════════════════════════════════════

class WeldDetailDialog(QDialog):
    """
    Ultra-premium Weld Joint Traveler & QC Passport Dialog.
    Fully resizable, responsive, sortable, integrated with NDT audits.
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

    # Column anchors for sort-safe lookups
    COL_PASS_TYPE = 0
    COL_NDT_METHOD = 0

    def __init__(self, db=None, joint_no: str = "W-02", parent=None):
        super().__init__(parent)
        self.db = db
        self.joint_no = joint_no

        # Drag / resize state
        self._drag_pos: Optional[QPoint] = None
        self._drag_edge: Optional[str] = None
        self._drag_geometry: Optional[QRect] = None
        self._resize_margin = 8

        # Lifecycle
        self._is_closed = False
        self._ts_timer: Optional[QTimer] = None

        # View state
        self._passes: List[Dict[str, Any]] = []
        self._ndt_history: List[Dict[str, Any]] = []

        self.setWindowTitle(f"PipeAgent – Joint Passport • {self.joint_no}")
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

    # ── Sample Weld Data ──────────────────────────────────────
    def _init_data(self):
        self._joint_meta: Dict[str, Any] = {
            "joint_no": self.joint_no,
            "spool_id": "SP-01-PR-2104-001",
            "iso_no": "ISO-01-PR-2104-001",
            "line_no": '12"-PR-2104-A1A',
            "spec": "A1A • Class 150# RF",
            "size": '12"',
            "schedule": "Sch 40 (9.53 mm)",
            "material_1": "Pipe A106 Gr.B (H-77402-A)",
            "material_2": "90° Elbow A234 WPB (EB-99321)",
            "joint_type": "BW (Butt Weld)",
            "process": "GTAW + SMAW",
            "wps_no": "WPS-CS-12 (GTAW/SMAW)",
            "fitup_status": "Accepted",
            "weld_status": "Completed",
            "ndt_status": "RT - Lack of Fusion (Repair Req.)",
            "qc_status": "Hold for Repair",
        }

        self._fitup_checklist: Dict[str, str] = {
            "root_gap": "3.2 mm (Spec: 2.4 - 3.6)",
            "root_face": "1.6 mm (Spec: 1.2 - 2.0)",
            "hi_lo": "0.8 mm (Spec: < 1.6)",
            "bevel_angle": "37.5° (Spec: 35° - 40°)",
            "cleaning": "Satisfactory (No Rust/Scale)",
            "tack_welder": "W-04 (Approved GTAW)",
            "inspection_date": "2025-02-18",
            "inspector": "QC Eng. Farhadi",
        }

        self._passes = [
            {
                "pass_id": "WPS00000001",
                "pass_type": "Root Pass",
                "process": "GTAW (TIG)",
                "welder_stamp": "W-04",
                "filler_metal": "ER70S-6 (Ø 2.4 mm)",
                "filler_heat": "HT-99214",
                "date": "2025-02-19",
                "inspector": "QC Eng. Farhadi",
            },
            {
                "pass_id": "WPS00000002",
                "pass_type": "Hot Pass",
                "process": "GTAW (TIG)",
                "welder_stamp": "W-04",
                "filler_metal": "ER70S-6 (Ø 2.4 mm)",
                "filler_heat": "HT-99214",
                "date": "2025-02-19",
                "inspector": "QC Eng. Farhadi",
            },
            {
                "pass_id": "WPS00000003",
                "pass_type": "Filling Pass",
                "process": "SMAW (Low-H)",
                "welder_stamp": "W-12",
                "filler_metal": "E7018-1 (Ø 3.2 mm)",
                "filler_heat": "HT-EL-8840",
                "date": "2025-02-19",
                "inspector": "QC Eng. Farhadi",
            },
            {
                "pass_id": "WPS00000004",
                "pass_type": "Capping Pass",
                "process": "SMAW (Low-H)",
                "welder_stamp": "W-12",
                "filler_metal": "E7018-1 (Ø 4.0 mm)",
                "filler_heat": "HT-EL-8840",
                "date": "2025-02-20",
                "inspector": "QC Eng. Farhadi",
            },
        ]

        self._ndt_history = [
            {
                "ndt_id": "NDT00000001",
                "method": "Visual Testing (VT)",
                "report_no": "VT-2025-2104-002",
                "date": "2025-02-20",
                "result": "Accepted",
                "inspector": "QC Eng. Farhadi",
                "remarks": (
                    "Clean capping profile, no undercut, root verified "
                    "by boroscope."
                ),
            },
            {
                "ndt_id": "NDT00000002",
                "method": "Radiographic Testing (RT)",
                "report_no": "NDT-RT-2025-088",
                "date": "2025-02-21",
                "result": "REJECT - Repair Required",
                "inspector": "NDT Level-II Kaveh",
                "remarks": (
                    "Lack of Fusion (LF) observed at segment 2-3 "
                    "(Length 18 mm)."
                ),
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

        icon_lbl = QLabel("👨‍🏭")
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
            "ASME B31.3 PROCESS PIPING COMPLIANT  •  FIT-UP INSPECTION  •  "
            "MULTI-PASS WELDER TRACEABILITY"
        )
        sub_title.setObjectName("subTitle")
        title_col.addWidget(sub_title)
        topbar.addLayout(title_col)
        topbar.addStretch()

        self.btn_export = QPushButton("📤  EXPORT PASSPORT  (Ctrl+E)")
        self.btn_export.setObjectName("secondaryBtn")
        self.btn_export.setMinimumHeight(36)
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.setToolTip("Export Weld Joint Passport to CSV (Ctrl+E)")
        self.btn_export.clicked.connect(self._on_export_passport)
        topbar.addWidget(self.btn_export)

        self.btn_tag = QPushButton("🏷  WELD TAG BARCODE")
        self.btn_tag.setObjectName("secondaryBtn")
        self.btn_tag.setMinimumHeight(36)
        self.btn_tag.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tag.setToolTip("Send weld joint barcode label to printer")
        self.btn_tag.clicked.connect(self._on_print_tag)
        topbar.addWidget(self.btn_tag)

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
        self.header_frame.setToolTip("Double-click anywhere to edit Joint specs")

        h_layout = QHBoxLayout(self.header_frame)
        h_layout.setContentsMargins(14, 8, 14, 8)
        h_layout.setSpacing(16)

        self.lbl_spool = QLabel()
        self.lbl_line  = QLabel()
        self.lbl_iso   = QLabel()
        self.lbl_size  = QLabel()
        self.lbl_wps   = QLabel()

        for lbl in [self.lbl_spool, self.lbl_line, self.lbl_iso,
                     self.lbl_size, self.lbl_wps]:
            lbl.setStyleSheet(
                "color: #7a9ab3; font-size: 11px; background: transparent;"
            )
            h_layout.addWidget(lbl)

        self.btn_edit_hdr = QPushButton("✏  EDIT")
        self.btn_edit_hdr.setObjectName("editHdrBtn")
        self.btn_edit_hdr.setFixedHeight(24)
        self.btn_edit_hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit_hdr.setToolTip("Edit joint specifications")
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

        self.kpi_fitup = StatCard(
            "FIT-UP CLEARANCE", "APPROVED", "📐", self.PRIMARY_LIGHT
        )
        self.kpi_weld  = StatCard(
            "WELD COMPLETION", "100% DONE", "🔥", self.ACCENT
        )
        self.kpi_ndt   = StatCard(
            "NDT EXAM STATUS", "REJECTED (RT)", "🔬", self.ERROR
        )
        self.kpi_qc    = StatCard(
            "QC MASTER STATUS", "HOLD FOR REPAIR", "🛡️", self.WARNING
        )

        stat_ribbon.addWidget(self.kpi_fitup)
        stat_ribbon.addWidget(self.kpi_weld)
        stat_ribbon.addWidget(self.kpi_ndt)
        stat_ribbon.addWidget(self.kpi_qc)
        return stat_ribbon

    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("weldTabs")

        # Tab 1: Engineering & Fit-up
        self.tab_fitup = QWidget()
        t1_layout = QVBoxLayout(self.tab_fitup)
        t1_layout.setContentsMargins(14, 14, 14, 14)
        t1_layout.setSpacing(10)

        mat_box = QFrame()
        mat_box.setStyleSheet(
            "background: #07101a; border: 1px solid #142e47; "
            "border-radius: 8px; padding: 10px;"
        )
        mat_layout = QVBoxLayout(mat_box)
        self.lbl_mat1 = QLabel()
        self.lbl_mat2 = QLabel()
        self.lbl_jtype = QLabel()
        for lbl in [self.lbl_mat1, self.lbl_mat2, self.lbl_jtype]:
            lbl.setStyleSheet("color: #eef6ff; font-size: 11px;")
            mat_layout.addWidget(lbl)
        t1_layout.addWidget(mat_box)

        chk_title = QLabel("📐   FIT-UP INSPECTION PARAMETERS (ASME B31.3 LIMITS)")
        chk_title.setStyleSheet(
            "color: #9fe7ff; font-size: 10px; font-weight: 800; letter-spacing: 1px;"
        )
        t1_layout.addWidget(chk_title)

        self.fitup_table = QTableWidget()
        self.fitup_table.setObjectName("fitupTable")
        self.fitup_table.setColumnCount(3)
        self.fitup_table.setHorizontalHeaderLabels([
            "Fit-up Parameter", "Observed Value", "Inspection Status"
        ])
        self.fitup_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.fitup_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.fitup_table.verticalHeader().setVisible(False)
        self.fitup_table.setShowGrid(False)
        t1_layout.addWidget(self.fitup_table)

        tabs.addTab(self.tab_fitup, "📐  ENGINEERING & FIT-UP")

        # Tab 2: Welding Execution
        self.tab_execution = QWidget()
        t2_layout = QVBoxLayout(self.tab_execution)
        t2_layout.setContentsMargins(14, 14, 14, 14)
        t2_layout.setSpacing(10)

        pass_title = QLabel("🔥   MULTI-PASS WELDING LOG & WELDER STAMP MATRIX")
        pass_title.setStyleSheet(
            "color: #9fe7ff; font-size: 10px; font-weight: 800; letter-spacing: 1px;"
        )
        t2_layout.addWidget(pass_title)

        self.pass_table = QTableWidget()
        self.pass_table.setObjectName("passTable")
        self.pass_table.setColumnCount(6)
        self.pass_table.setHorizontalHeaderLabels([
            "Pass Type", "Process", "Welder Stamp",
            "Filler Metal Spec", "Heat / Lot No", "Weld Date",
        ])

        self.pass_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pass_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pass_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.pass_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        header2 = self.pass_table.horizontalHeader()
        header2.setSectionsMovable(True)
        header2.setSectionsClickable(True)
        header2.setStretchLastSection(True)
        for col_idx in range(self.pass_table.columnCount()):
            header2.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

        default_widths2 = [110, 110, 100, 150, 110, 110]
        for col_idx, w in enumerate(default_widths2):
            self.pass_table.setColumnWidth(col_idx, w)

        self.pass_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.pass_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.pass_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.pass_table.verticalHeader().setVisible(False)
        self.pass_table.setShowGrid(False)
        self.pass_table.setAlternatingRowColors(True)
        self.pass_table.setSortingEnabled(True)
        self.pass_table.setWordWrap(False)
        self.pass_table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.pass_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pass_table.customContextMenuRequested.connect(self._show_context_menu)

        t2_layout.addWidget(self.pass_table)
        tabs.addTab(self.tab_execution, "🔥  WELDING EXECUTION")

        # Tab 3: NDT
        self.tab_ndt = QWidget()
        t3_layout = QVBoxLayout(self.tab_ndt)
        t3_layout.setContentsMargins(14, 14, 14, 14)
        t3_layout.setSpacing(10)

        ndt_title = QLabel("🔬   NON-DESTRUCTIVE TESTING & INSPECTION DOSSIER")
        ndt_title.setStyleSheet(
            "color: #9fe7ff; font-size: 10px; font-weight: 800; letter-spacing: 1px;"
        )
        t3_layout.addWidget(ndt_title)

        self.ndt_table = QTableWidget()
        self.ndt_table.setObjectName("ndtTable")
        self.ndt_table.setColumnCount(5)
        self.ndt_table.setHorizontalHeaderLabels([
            "Exam Method", "Report Number", "Inspection Date",
            "QC Evaluation", "Inspectors",
        ])

        self.ndt_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.ndt_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.ndt_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.ndt_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        header3 = self.ndt_table.horizontalHeader()
        header3.setSectionsMovable(True)
        header3.setSectionsClickable(True)
        header3.setStretchLastSection(True)
        for col_idx in range(self.ndt_table.columnCount()):
            header3.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

        default_widths3 = [160, 180, 110, 180, 150]
        for col_idx, w in enumerate(default_widths3):
            self.ndt_table.setColumnWidth(col_idx, w)

        self.ndt_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.ndt_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.ndt_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ndt_table.verticalHeader().setVisible(False)
        self.ndt_table.setShowGrid(False)
        self.ndt_table.setAlternatingRowColors(True)
        self.ndt_table.setSortingEnabled(True)
        self.ndt_table.setWordWrap(False)
        self.ndt_table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.ndt_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ndt_table.customContextMenuRequested.connect(self._show_context_menu)
        self.ndt_table.itemSelectionChanged.connect(self._on_ndt_selection)

        t3_layout.addWidget(self.ndt_table)
        tabs.addTab(self.tab_ndt, "🔬  INSPECTION & NDT")

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

        head_lbl = QLabel("🔍   QC PASSPORT CLEARANCE")
        head_lbl.setObjectName("inspHead")
        layout.addWidget(head_lbl)

        div = QFrame()
        div.setObjectName("divider")
        div.setFixedHeight(1)
        layout.addWidget(div)

        self.insp_target = QLabel(self._joint_meta["joint_no"])
        self.insp_target.setObjectName("inspTarget")
        self.insp_target.setWordWrap(True)
        layout.addWidget(self.insp_target)

        self.insp_sub = QLabel(
            "Select any NDT or weld pass log from the tables to perform "
            "real-time verification and digital sign-off."
        )
        self.insp_sub.setObjectName("inspSub")
        self.insp_sub.setWordWrap(True)
        layout.addWidget(self.insp_sub)

        self.meta_frame = QFrame()
        self.meta_frame.setObjectName("metaFrame")
        m_layout = QVBoxLayout(self.meta_frame)
        m_layout.setContentsMargins(10, 8, 10, 8)
        m_layout.setSpacing(5)

        self.m_wps    = QLabel()
        self.m_type   = QLabel()
        self.m_size   = QLabel()
        self.m_status = QLabel()
        self.m_ndt    = QLabel()

        # Declarative spec for both populate and reset.
        self._meta_specs = [
            (self.m_wps,    "WPS"),
            (self.m_type,   "Joint Config"),
            (self.m_size,   "Size / NPS"),
            (self.m_status, "Weld Status"),
            (self.m_ndt,    "NDT Evaluation"),
        ]

        for lbl, _ in self._meta_specs:
            lbl.setStyleSheet(
                "color: #dfeaf5; font-size: 11px; background: transparent;"
            )
            lbl.setWordWrap(True)
            m_layout.addWidget(lbl)

        layout.addWidget(self.meta_frame)

        action_lbl = QLabel("⚡   QC AUTHORIZATION ACTIONS:")
        action_lbl.setStyleSheet(
            "color: #9fe7ff; font-size: 9px; font-weight: 800; "
            "letter-spacing: 1px; margin-top: 4px; background: transparent;"
        )
        layout.addWidget(action_lbl)

        self.btn_sign_fitup = QPushButton("📐  APPROVE FIT-UP REPORT")
        self.btn_sign_fitup.setObjectName("secondaryBtn")
        self.btn_sign_fitup.setMinimumHeight(32)
        self.btn_sign_fitup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sign_fitup.setToolTip("Approve the fit-up report for this joint")
        self.btn_sign_fitup.clicked.connect(self._on_approve_fitup)
        layout.addWidget(self.btn_sign_fitup)

        self.btn_sign_weld = QPushButton("🔥  APPROVE VISUAL INSPECTION (VT)")
        self.btn_sign_weld.setObjectName("secondaryBtn")
        self.btn_sign_weld.setMinimumHeight(32)
        self.btn_sign_weld.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sign_weld.setToolTip("Approve visual inspection (VT) and log it")
        self.btn_sign_weld.clicked.connect(self._on_approve_vt)
        layout.addWidget(self.btn_sign_weld)

        self.btn_clear_ndt = QPushButton("✅  ACCEPT JOINT (NDT CLEARANCE)")
        self.btn_clear_ndt.setObjectName("actionBtn")
        self.btn_clear_ndt.setMinimumHeight(34)
        self.btn_clear_ndt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_ndt.setToolTip("Grant NDT clearance to this joint")
        self.btn_clear_ndt.clicked.connect(self._on_clear_joint_ndt)
        self._add_glow(self.btn_clear_ndt, QColor(108, 207, 246, 100), blur=18)
        layout.addWidget(self.btn_clear_ndt)

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
            "All welding logs compliant with ASME Section IX WPS."
        )
        self.lbl_count.setObjectName("footerLabel")
        footer.addWidget(self.lbl_count)

        footer.addStretch()

        self.lbl_timestamp = QLabel("")
        self.lbl_timestamp.setObjectName("footerLabel")
        footer.addWidget(self.lbl_timestamp)

        footer.addStretch()

        foot_tag = QLabel(
            "⚡  PipeAgent 5.0  •  Weld Quality Traceability Matrix"
        )
        foot_tag.setStyleSheet(
            "color: #3f6070; font-size: 10px; letter-spacing: 1px; background: transparent;"
        )
        footer.addWidget(foot_tag)
        return footer

    # ── Keyboard Shortcuts ────────────────────────────────────
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self, self._on_add_item_by_tab)
        QShortcut(QKeySequence("Ctrl+E"), self, self._on_export_passport)
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)

        # Bind Delete on each table only (never on the dialog).
        del_pass = QShortcut(
            QKeySequence("Delete"), self.pass_table, self._on_remove_pass
        )
        del_pass.setContext(Qt.ShortcutContext.WidgetShortcut)

        del_ndt = QShortcut(
            QKeySequence("Delete"), self.ndt_table, self._on_remove_ndt
        )
        del_ndt.setContext(Qt.ShortcutContext.WidgetShortcut)

    def _focus_search(self):
        idx = self.tabs.currentIndex()
        if idx == 1:
            self.pass_table.setFocus()
        elif idx == 2:
            self.ndt_table.setFocus()

    # ── Context Menu ──────────────────────────────────────────
    def _show_context_menu(self, pos):
        idx = self.tabs.currentIndex()
        if idx == 0:
            return  # Fit-up parameters are read-only

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

        if idx == 1:
            selected_pass = self._get_selected_pass()

            act_new = menu.addAction("➕  Log New Weld Pass  (Ctrl+N)")
            act_new.triggered.connect(self._on_add_weld_pass)

            menu.addSeparator()

            act_delete = menu.addAction("🗑  Remove Weld Pass Record")
            act_delete.setEnabled(selected_pass is not None)
            act_delete.triggered.connect(self._on_remove_pass)

            menu.exec(self.pass_table.viewport().mapToGlobal(pos))

        elif idx == 2:
            selected_ndt = self._get_selected_ndt()

            act_accept = menu.addAction("✅  Status - Override Accepted")
            act_accept.setEnabled(selected_ndt is not None)
            act_accept.triggered.connect(
                lambda: self._set_selected_ndt_evaluation(
                    "ACCEPTED", "Cleared / OK"
                )
            )

            act_reject = menu.addAction("❌  Status - Override Rejected")
            act_reject.setEnabled(selected_ndt is not None)
            act_reject.triggered.connect(
                lambda: self._set_selected_ndt_evaluation(
                    "REJECT - Repair Required", "Hold for Repair"
                )
            )

            menu.addSeparator()

            act_new = menu.addAction("➕  Log New NDT Examination  (Ctrl+N)")
            act_new.triggered.connect(self._on_add_ndt_exam)

            menu.addSeparator()

            act_delete = menu.addAction("🗑  Remove NDT Record")
            act_delete.setEnabled(selected_ndt is not None)
            act_delete.triggered.connect(self._on_remove_ndt)

            menu.exec(self.ndt_table.viewport().mapToGlobal(pos))

    # ── Header Refresh ────────────────────────────────────────
    def _refresh_header_display(self):
        self.main_title.setText(
            f"WELD JOINT PASSPORT  •  WJCS QUALITY TRAVELER "
            f"[{self._joint_meta['joint_no']}]"
        )
        self.lbl_spool.setText(
            f"<b>SPOOL:</b> <span style='color:#9fe7ff;'>"
            f"{self._joint_meta['spool_id']}</span>"
        )
        self.lbl_line.setText(
            f"<b>LINE NO:</b> <span style='color:#9fe7ff;'>"
            f"{self._joint_meta['line_no']}</span>"
        )
        self.lbl_iso.setText(
            f"<b>ISO DWG:</b> <span style='color:#eef6ff;'>"
            f"{self._joint_meta['iso_no']}</span>"
        )
        self.lbl_size.setText(
            f"<b>SIZE / THK:</b> <span style='color:#7a9ab3;'>"
            f"{self._joint_meta['size']} ({self._joint_meta['schedule']})</span>"
        )
        self.lbl_wps.setText(
            f"<b>WPS REF:</b> <span style='color:#7a9ab3;'>"
            f"{self._joint_meta['wps_no']}</span>"
        )

        # Refresh material labels used on the first tab
        self.lbl_mat1.setText(
            f"<b>Joined Component 1:</b> {self._joint_meta['material_1']}"
        )
        self.lbl_mat2.setText(
            f"<b>Joined Component 2:</b> {self._joint_meta['material_2']}"
        )
        self.lbl_jtype.setText(
            f"<b>Joint Configuration:</b> {self._joint_meta['joint_type']}"
        )

    def _on_edit_header(self):
        modal = EditJointMetaDialog(self._joint_meta, self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return

        new_data = modal.get_data()
        self._joint_meta.update(new_data)
        self.joint_no = self._joint_meta["joint_no"]
        self.setWindowTitle(f"PipeAgent – Joint Passport • {self.joint_no}")
        self.insp_target.setText(self.joint_no)
        self._refresh_header_display()
        self._update_kpi()

        QMessageBox.information(
            self, "✅ Joint Updated",
            "Weld Joint technical specifications modified successfully.",
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
                /* QSS does not support gradients in `border`. */
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
            QTabWidget#weldTabs::pane {{
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

    # ── Sort-safe selection helpers ───────────────────────────
    def _get_selected_pass(self) -> Optional[Dict[str, Any]]:
        rows = self.pass_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.pass_table.item(rows[0].row(), self.COL_PASS_TYPE)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _get_selected_ndt(self) -> Optional[Dict[str, Any]]:
        rows = self.ndt_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.ndt_table.item(rows[0].row(), self.COL_NDT_METHOD)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _find_pass_index(self, pass_id: str) -> int:
        for idx, p in enumerate(self._passes):
            if p.get("pass_id") == pass_id:
                return idx
        return -1

    def _find_ndt_index(self, ndt_id: str) -> int:
        for idx, n in enumerate(self._ndt_history):
            if n.get("ndt_id") == ndt_id:
                return idx
        return -1

    def _reselect_pass_by_id(self, pass_id: str):
        for row_idx in range(self.pass_table.rowCount()):
            item = self.pass_table.item(row_idx, self.COL_PASS_TYPE)
            if item is None:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("pass_id") == pass_id:
                self.pass_table.selectRow(row_idx)
                return

    def _reselect_ndt_by_id(self, ndt_id: str):
        for row_idx in range(self.ndt_table.rowCount()):
            item = self.ndt_table.item(row_idx, self.COL_NDT_METHOD)
            if item is None:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("ndt_id") == ndt_id:
                self.ndt_table.selectRow(row_idx)
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
        self._populate_fitup_table()
        self._populate_pass_table()
        self._populate_ndt_table()

    def _populate_fitup_table(self):
        self.fitup_table.setRowCount(0)
        fitup_items = [
            ("Root Gap (Standard 3.2mm)", self._fitup_checklist["root_gap"], "Accepted"),
            ("Root Face (Standard 1.6mm)", self._fitup_checklist["root_face"], "Accepted"),
            ("Linear Misalignment (Hi-Lo)", self._fitup_checklist["hi_lo"], "Accepted"),
            ("Bevel Preparation Angle", self._fitup_checklist["bevel_angle"], "Accepted"),
            ("Internal & Bevel Cleaning", self._fitup_checklist["cleaning"], "Accepted"),
        ]

        for row_idx, (param, val, status) in enumerate(fitup_items):
            self.fitup_table.insertRow(row_idx)

            item_param = QTableWidgetItem(param)
            item_param.setForeground(QColor(self.TEXT_MAIN))
            self.fitup_table.setItem(row_idx, 0, item_param)

            item_val = QTableWidgetItem(val)
            item_val.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            item_val.setForeground(QColor(self.PRIMARY_LIGHT))
            self.fitup_table.setItem(row_idx, 1, item_val)

            item_st = QTableWidgetItem(f" ● {status} ")
            item_st.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item_st.setForeground(QColor(self.SUCCESS))
            item_st.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.fitup_table.setItem(row_idx, 2, item_st)

    def _populate_pass_table(self):
        self.pass_table.setSortingEnabled(False)
        self.pass_table.setRowCount(0)

        for row_idx, p in enumerate(self._passes):
            self.pass_table.insertRow(row_idx)

            # Col 0 — carries the pass record via UserRole.
            item_type = QTableWidgetItem(p["pass_type"])
            item_type.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item_type.setForeground(QColor(self.PRIMARY_LIGHT))
            item_type.setData(Qt.ItemDataRole.UserRole, p)  # sort-safe link
            self.pass_table.setItem(row_idx, 0, item_type)

            item_proc = QTableWidgetItem(p["process"])
            item_proc.setForeground(QColor(self.TEXT_MAIN))
            self.pass_table.setItem(row_idx, 1, item_proc)

            item_welder = QTableWidgetItem(p["welder_stamp"])
            item_welder.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            item_welder.setForeground(QColor(self.WARNING))
            self.pass_table.setItem(row_idx, 2, item_welder)

            item_fil = QTableWidgetItem(p["filler_metal"])
            item_fil.setForeground(QColor(self.TEXT_MUTED))
            self.pass_table.setItem(row_idx, 3, item_fil)

            item_heat = QTableWidgetItem(p["filler_heat"])
            item_heat.setFont(QFont("Consolas", 10))
            item_heat.setForeground(QColor(self.ACCENT))
            self.pass_table.setItem(row_idx, 4, item_heat)

            item_dt = QTableWidgetItem(p["date"])
            item_dt.setFont(QFont("Consolas", 9))
            item_dt.setForeground(QColor("#708fa8"))
            self.pass_table.setItem(row_idx, 5, item_dt)

        self.pass_table.setSortingEnabled(True)

        if self._passes:
            self.pass_table.selectRow(0)

    def _populate_ndt_table(self):
        self.ndt_table.setSortingEnabled(False)
        self.ndt_table.setRowCount(0)

        for row_idx, n in enumerate(self._ndt_history):
            self.ndt_table.insertRow(row_idx)

            # Col 0 — carries the NDT record via UserRole.
            item_meth = QTableWidgetItem(n["method"])
            item_meth.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item_meth.setForeground(QColor(self.PRIMARY_LIGHT))
            item_meth.setData(Qt.ItemDataRole.UserRole, n)  # sort-safe link
            self.ndt_table.setItem(row_idx, 0, item_meth)

            item_rep = QTableWidgetItem(n["report_no"])
            item_rep.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            item_rep.setForeground(QColor(self.ACCENT))
            self.ndt_table.setItem(row_idx, 1, item_rep)

            item_dt = QTableWidgetItem(n["date"])
            item_dt.setFont(QFont("Consolas", 9))
            item_dt.setForeground(QColor("#708fa8"))
            self.ndt_table.setItem(row_idx, 2, item_dt)

            res_str = n["result"]
            item_res = QTableWidgetItem(f" ● {res_str} ")
            item_res.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item_res.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if ("ACCEPTED" in res_str.upper()
                    or "SATISFACTORY" in res_str.upper()
                    or "CLEARED" in res_str.upper()):
                item_res.setForeground(QColor(self.SUCCESS))
            else:
                item_res.setForeground(QColor(self.ERROR))
            self.ndt_table.setItem(row_idx, 3, item_res)

            item_ins = QTableWidgetItem(n["inspector"])
            item_ins.setForeground(QColor(self.TEXT_MUTED))
            self.ndt_table.setItem(row_idx, 4, item_ins)

        self.ndt_table.setSortingEnabled(True)

        if self._ndt_history:
            self.ndt_table.selectRow(0)

    def _update_kpi(self):
        fitup = self._joint_meta["fitup_status"]
        weld = self._joint_meta["weld_status"]
        ndt = self._joint_meta["ndt_status"]
        qc = self._joint_meta["qc_status"]

        self.kpi_fitup.update_value(fitup.upper())
        self.kpi_weld.update_value("100% DONE" if weld == "Completed" else "PENDING")
        self.kpi_ndt.update_value(ndt.split(" (")[0].upper())
        self.kpi_qc.update_value(qc.upper())

        # Dynamically retint the NDT tile based on the current status.
        ndt_upper = ndt.upper()
        if "REJECT" in ndt_upper or "LACK" in ndt_upper or "REPAIR" in ndt_upper:
            self.kpi_ndt.set_accent(self.ERROR)
        else:
            self.kpi_ndt.set_accent(self.SUCCESS)

        self.lbl_count.setText(
            f"Joint passport traveler contains {len(self._passes)} recorded "
            f"welding passes. Total active NDT logs: {len(self._ndt_history)} report(s)."
        )

    # ── Table Selection → Inspector ───────────────────────────
    def _on_ndt_selection(self):
        selected = self._get_selected_ndt()
        if selected is None:
            self._clear_inspector()
            return

        self.insp_target.setText(f"{selected['method']}")
        self.insp_sub.setText(
            f"Report: {selected['report_no']} • "
            f"Remarks: {selected.get('remarks', 'N/A')}"
        )

        self.m_wps.setText(f"<b>WPS:</b> {self._joint_meta['wps_no']}")
        self.m_type.setText(f"<b>Weld Type:</b> {self._joint_meta['joint_type']}")
        self.m_size.setText(f"<b>Size / NPS:</b> {self._joint_meta['size']}")

        status = selected["result"]
        status_color = (
            self.SUCCESS if "ACCEPTED" in status.upper() else self.ERROR
        )
        self.m_status.setText(
            f"<b>Status:</b> <span style='color:{status_color}'>{status}</span>"
        )

        self.m_ndt.setText(f"<b>NDT Analyst:</b> {selected['inspector']}")

    def _clear_inspector(self):
        self.insp_target.setText("No Record Selected")
        self.insp_sub.setText(
            "Select any NDT or weld pass log from the tables to perform "
            "real-time verification and digital sign-off."
        )
        for lbl, title in self._meta_specs:
            lbl.setText(f"<b>{title}:</b> —")

    # ── Quick Context Actions ─────────────────────────────────
    def _set_selected_ndt_evaluation(self, eval_result: str, qc_status: str):
        selected = self._get_selected_ndt()
        if selected is None:
            return

        idx = self._find_ndt_index(selected.get("ndt_id", ""))
        if idx < 0:
            return

        self._ndt_history[idx]["result"] = eval_result

        # Sync master joint status with the latest evaluation.
        self._joint_meta["ndt_status"] = eval_result
        self._joint_meta["qc_status"] = qc_status

        target_id = self._ndt_history[idx]["ndt_id"]
        self._populate_ndt_table()
        self._update_kpi()
        self._reselect_ndt_by_id(target_id)

    # ── QC Approval Sign-off Actions ──────────────────────────
    def _on_approve_fitup(self):
        self._joint_meta["fitup_status"] = "Accepted"
        self._update_kpi()
        QMessageBox.information(
            self, "📐 QC Fit-up Clearance",
            f"Fit-up dimensions for Weld Joint <b>{self.joint_no}</b> verified "
            f"& signed-off under ASME B31.3 guidelines."
        )

    def _on_approve_vt(self):
        vt_rep = {
            "ndt_id": _uid("NDT"),
            "method": "Visual Testing (VT)",
            "report_no": f"VT-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "date": _today(),
            "result": "ACCEPTED",
            "inspector": "QC Eng. Farhadi",
            "remarks": (
                "Capping profile and root penetration verified via visual "
                "& boroscope."
            ),
        }
        self._ndt_history.insert(0, vt_rep)
        self._joint_meta["weld_status"] = "Completed"
        self._populate_ndt_table()
        self._update_kpi()
        self._reselect_ndt_by_id(vt_rep["ndt_id"])

        QMessageBox.information(
            self, "🔥 Visual Examination Signed",
            f"Visual examination (VT) passport stamp applied successfully "
            f"to Joint <b>{self.joint_no}</b>."
        )

    def _on_clear_joint_ndt(self):
        self._joint_meta["ndt_status"] = "Cleared (RT-Passed)"
        self._joint_meta["qc_status"] = "Cleared / OK"

        if self._ndt_history:
            self._ndt_history[0]["result"] = "ACCEPTED"
            self._ndt_history[0]["remarks"] = (
                "NDT evaluation cleared by Level-II inspector override."
            )

        self._populate_ndt_table()
        self._update_kpi()

        QMessageBox.information(
            self, "✅ Joint Quality Passport Cleared",
            f"Weld Joint <b>{self.joint_no}</b> has successfully cleared all "
            f"WJCS traveler checkpoints.<br>This joint is officially "
            f"<b>RELEASED</b>."
        )

    # ── Add / Remove Traveler Items ───────────────────────────
    def _on_add_item_by_tab(self):
        idx = self.tabs.currentIndex()
        if idx == 1:
            self._on_add_weld_pass()
        elif idx == 2:
            self._on_add_ndt_exam()

    def _on_add_weld_pass(self):
        modal = AddWeldPassDialog(self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        new_pass = modal.get_data()
        self._passes.append(new_pass)
        self._populate_pass_table()
        self._update_kpi()
        self.tabs.setCurrentIndex(1)
        self._reselect_pass_by_id(new_pass["pass_id"])

    def _on_remove_pass(self):
        selected = self._get_selected_pass()
        if selected is None:
            return

        reply = QMessageBox.warning(
            self, "⚠ Remove Weld Pass",
            f"Are you sure you want to delete the weld pass log for "
            f"<b>{selected['pass_type']}</b> "
            f"(Welder: {selected['welder_stamp']})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        idx = self._find_pass_index(selected.get("pass_id", ""))
        if idx < 0:
            return
        self._passes.pop(idx)
        self._populate_pass_table()
        self._update_kpi()

    def _on_add_ndt_exam(self):
        modal = AddNDTExamDialog(self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        new_ndt = modal.get_data()
        self._ndt_history.insert(0, new_ndt)
        self._populate_ndt_table()
        self._update_kpi()
        self.tabs.setCurrentIndex(2)
        self._reselect_ndt_by_id(new_ndt["ndt_id"])

    def _on_remove_ndt(self):
        selected = self._get_selected_ndt()
        if selected is None:
            return

        reply = QMessageBox.warning(
            self, "⚠ Remove NDT Record",
            f"Are you sure you want to delete the NDT report log "
            f"<b>{selected['report_no']}</b>?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        idx = self._find_ndt_index(selected.get("ndt_id", ""))
        if idx < 0:
            return
        self._ndt_history.pop(idx)
        self._populate_ndt_table()
        self._update_kpi()

    # ── Export Joint Passport ─────────────────────────────────
    def _on_export_passport(self):
        default_name = f"Joint_{self.joint_no}_Traveler_Passport.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Joint Quality Traveler Passport",
            default_name, "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["═══ WELD JOINT QUALITY PASSPORT TRAVELER ═══"])
                writer.writerow(["Joint Number", self._joint_meta["joint_no"]])
                writer.writerow(["Spool ID", self._joint_meta["spool_id"]])
                writer.writerow(["Isometric No", self._joint_meta["iso_no"]])
                writer.writerow(["Line Number", self._joint_meta["line_no"]])
                writer.writerow(["Material Specification", self._joint_meta["spec"]])
                writer.writerow(["Pipe Material A", self._joint_meta["material_1"]])
                writer.writerow(["Pipe Material B", self._joint_meta["material_2"]])
                writer.writerow([
                    "Nominal Size / Thk",
                    f"{self._joint_meta['size']} ({self._joint_meta['schedule']})",
                ])
                writer.writerow(["ASME WPS Ref", self._joint_meta["wps_no"]])
                writer.writerow(["Fitup Status", self._joint_meta["fitup_status"]])
                writer.writerow(["Weld Status", self._joint_meta["weld_status"]])
                writer.writerow(["NDT Examination", self._joint_meta["ndt_status"]])
                writer.writerow(["Clearance Gate", self._joint_meta["qc_status"]])
                writer.writerow([])

                writer.writerow(["═══ MULTI-PASS WELDING LOGS ═══"])
                writer.writerow([
                    "Pass Type", "Process", "Welder Stamp",
                    "Filler Metal Wire", "Heat/Lot Number", "Date Logged",
                ])
                for p in self._passes:
                    writer.writerow([
                        p["pass_type"], p["process"], p["welder_stamp"],
                        p["filler_metal"], p["filler_heat"], p["date"],
                    ])
                writer.writerow([])

                writer.writerow(["═══ NDT EXAMINATION & REPORT LOGS ═══"])
                writer.writerow([
                    "Method", "Report Number", "Date Logged",
                    "Evaluation", "QC Examiner", "Remarks",
                ])
                for n in self._ndt_history:
                    writer.writerow([
                        n["method"], n["report_no"], n["date"],
                        n["result"], n["inspector"], n["remarks"],
                    ])

            QMessageBox.information(
                self, "✅ Joint Passport Exported",
                f"Joint passport traveler dossier successfully saved to:\n\n{path}",
            )
        except PermissionError:
            QMessageBox.critical(
                self, "Export Error",
                "Permission denied. The file may be open in Excel.\n"
                "Please close it and try again.",
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Export Error",
                f"Could not export joint quality passport: {e}",
            )

    def _on_print_tag(self):
        # Collect welders from the pass log for the tag text.
        welders = sorted({p["welder_stamp"] for p in self._passes})
        welders_txt = " • ".join(welders) if welders else "—"

        QMessageBox.information(
            self, "🏷 Zebra Thermal Tag Utility",
            f"<b>Weld Joint Barcode / QR Label Generated:</b><br><br>"
            f"• <b>Joint No:</b> {self._joint_meta['joint_no']}<br>"
            f"• <b>Spool Drawing ID:</b> {self._joint_meta['spool_id']}<br>"
            f"• <b>Welders:</b> {welders_txt}<br>"
            f"• <b>WPS Ref:</b> {self._joint_meta['wps_no']}<br>"
            f"• <b>NDT Status:</b> {self._joint_meta['ndt_status']}<br><br>"
            f"<i>Payload successfully streamed to Laydown Yard Zebra Tag Printer.</i>"
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

    dialog = WeldDetailDialog(joint_no="W-02")
    dialog.show()
    dialog.exec()

    sys.exit(0)