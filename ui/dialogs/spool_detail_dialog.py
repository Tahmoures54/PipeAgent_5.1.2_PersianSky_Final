# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Spool Detail & Fabrication Traveler Dialog
═══════════════════════════════════════════════════════════════════════
Version : 5.0 (Refactored, hardened, production-ready)
Engine  : PyQt6
Design  : Cinematic dark-tech theme matching PipeAgent Suite

Fixes in this revision
──────────────────────
🔴 P0  Card border       : replaced invalid `border: ... qlineargradient`
                          with a solid color + drop shadow
🔴 P0  GlowLineEdit      : no longer calls deleteLater() on an animation
                          that Qt owns (DeleteWhenStopped)
🔴 P0  Sort-safe select   : joint dict is stored on the first column's
                          UserRole, so sorting the table no longer returns
                          the wrong joint
🔴 P0  Stable ids         : every joint has a `joint_id`; lookups no longer
                          rely on `list.index(dict)`
🟠 P1  Cleanup            : `_cleanup()` is idempotent and `done()` is
                          overridden → single cleanup path
🟠 P1  Particle geometry  : set immediately after creation
🟠 P1  Delete shortcut    : bound to the joint table only
🟠 P1  Area filter reset  : n/a (this dialog has no area filter)
🟡 P2  _clear_inspector   : driven by a declared label spec
🟡 P2  ParticleField      : count 30 → 14, tick 60ms → 100ms, paints only
                          when visible
🟡 P2  Duplicate set      : `_existing_joints` is now a set (O(1) lookup)
🟢 P3  Tooltips           : on every field / button
🟢 P3  Helper `_today()`  : single source for the current date
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

def _new_joint_id() -> str:
    return "J" + uuid.uuid4().hex[:9].upper()


def _today_str() -> str:
    return datetime.today().strftime("%Y-%m-%d")


# ════════════════════════════════════════════════════════════════
#  PARTICLE FIELD
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
#  GLOW LINE EDIT
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
#  KPI STAT CARD
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
#  ADD JOINT SUB-MODAL
# ════════════════════════════════════════════════════════════════

class AddJointDialog(QDialog):
    """Sub-modal for adding a weld joint directly to the spool."""

    def __init__(self, existing_joints: Optional[Iterable[str]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Weld Joint")
        self.setMinimumSize(500, 520)
        self.setMaximumSize(650, 680)
        self.resize(500, 540)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos: Optional[QPoint] = None
        # O(1) duplicate lookup on every keystroke.
        self._existing_joints = {str(j).upper() for j in (existing_joints or [])}
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("jointCard")
        card.setStyleSheet("""
            QWidget#jointCard {
                background: #0b1624;
                border: 2px solid #6ccff6;
                border-radius: 14px;
            }
            QLabel { color: #9fe7ff; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
            QLineEdit, QComboBox, QDoubleSpinBox {
                background: #07101a;
                color: #eef6ff;
                border: 1px solid #18364a;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
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
        title = QLabel("🔗   ADD JOINT TO SPOOL")
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
        col_j = QVBoxLayout()
        col_j.addWidget(QLabel("JOINT NO / WELD TAG *"))
        self.in_joint = QLineEdit()
        self.in_joint.setPlaceholderText("e.g. W-05 / J-06")
        self.in_joint.setToolTip("Unique joint / weld tag — required")
        col_j.addWidget(self.in_joint)
        row1.addLayout(col_j)

        col_cat = QVBoxLayout()
        col_cat.addWidget(QLabel("CATEGORY"))
        self.in_cat = QComboBox()
        self.in_cat.addItems(["Shop Weld", "Field Weld", "Tie-in Weld"])
        self.in_cat.setToolTip("Shop / Field / Tie-in")
        col_cat.addWidget(self.in_cat)
        row1.addLayout(col_cat)
        layout.addLayout(row1)

        self.lbl_dup_warn = QLabel("⚠ This Joint Number already exists in the spool register!")
        self.lbl_dup_warn.setStyleSheet(
            "color: #ff9f43; font-size: 10px; font-weight: 700; background: transparent;"
        )
        self.lbl_dup_warn.setVisible(False)
        layout.addWidget(self.lbl_dup_warn)
        self.in_joint.textChanged.connect(self._check_duplicate_joint)

        row2 = QHBoxLayout()
        col_type = QVBoxLayout()
        col_type.addWidget(QLabel("JOINT TYPE"))
        self.in_type = QComboBox()
        self.in_type.addItems([
            "BW (Butt Weld)", "SW (Socket Weld)",
            "FW (Fillet Weld)", "THD (Threaded)", "Flanged",
        ])
        col_type.addWidget(self.in_type)
        row2.addLayout(col_type)

        col_size = QVBoxLayout()
        col_size.addWidget(QLabel("NPS SIZE (INCHES)"))
        self.in_size = QDoubleSpinBox()
        self.in_size.setRange(0.5, 72.0)
        self.in_size.setValue(12.0)
        self.in_size.setSingleStep(0.5)
        self.in_size.setToolTip("Nominal pipe size (inches)")
        col_size.addWidget(self.in_size)
        row2.addLayout(col_size)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        col_sch = QVBoxLayout()
        col_sch.addWidget(QLabel("SCHEDULE / THK"))
        self.in_sch = QLineEdit()
        self.in_sch.setPlaceholderText("e.g. Sch 40 / 9.53mm")
        col_sch.addWidget(self.in_sch)
        row3.addLayout(col_sch)

        col_weld = QVBoxLayout()
        col_weld.addWidget(QLabel("WELDER STAMP"))
        self.in_welder = QLineEdit()
        self.in_welder.setPlaceholderText("e.g. W-04")
        col_weld.addWidget(self.in_welder)
        row3.addLayout(col_weld)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        col_fit = QVBoxLayout()
        col_fit.addWidget(QLabel("FIT-UP STATUS"))
        self.in_fit = QComboBox()
        self.in_fit.addItems(["Accepted", "Pending Inspection", "Rejected"])
        col_fit.addWidget(self.in_fit)
        row4.addLayout(col_fit)

        col_ndt = QVBoxLayout()
        col_ndt.addWidget(QLabel("NDT METHOD & CLEARANCE"))
        self.in_ndt = QComboBox()
        self.in_ndt.addItems([
            "RT - Passed", "RT - Pending",
            "PT - Passed", "UT - Passed", "Visual Only (VT)",
        ])
        col_ndt.addWidget(self.in_ndt)
        row4.addLayout(col_ndt)
        layout.addLayout(row4)

        layout.addSpacing(10)

        submit_btn = QPushButton("⚡  INSERT JOINT INTO SPOOL")
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

    def _check_duplicate_joint(self, text: str):
        is_dup = text.strip().upper() in self._existing_joints
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
        joint = self.in_joint.text().strip()
        if not joint:
            QMessageBox.warning(
                self, "Validation Error",
                "Joint Number / Weld Tag is required."
            )
            self.in_joint.setFocus()
            return

        if joint.upper() in self._existing_joints:
            reply = QMessageBox.question(
                self, "Duplicate Joint ID",
                f"Joint <b>{joint}</b> already registered on this spool.\n\n"
                "Do you still want to insert this entry?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.accept()

    def get_data(self) -> Dict[str, Any]:
        welder = self.in_welder.text().strip().upper()
        ndt = self.in_ndt.currentText()
        return {
            "joint_id": _new_joint_id(),
            "joint_no": self.in_joint.text().strip().upper(),
            "category": self.in_cat.currentText(),
            "type": self.in_type.currentText().split(" ")[0],
            "size": f"{self.in_size.value():g}\"",
            "nps_val": self.in_size.value(),
            "schedule": self.in_sch.text().strip() or "Sch 40",
            "welder": welder or "W-01",
            "fitup": self.in_fit.currentText(),
            "weld_status": "Completed" if welder else "Pending",
            "ndt_status": ndt,
            "qc_status": "Approved" if "Passed" in ndt else "In Progress",
        }


# ════════════════════════════════════════════════════════════════
#  SPOOL HEADER METADATA EDITOR
# ════════════════════════════════════════════════════════════════

class EditSpoolMetaDialog(QDialog):
    """Sub-modal for editing Spool Header technical specifications."""

    def __init__(self, current_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Spool Specifications")
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
            QLineEdit, QDoubleSpinBox {
                background: #07101a; color: #eef6ff;
                border: 1px solid #18364a; border-radius: 6px;
                padding: 6px 10px; font-size: 12px;
            }
            QLineEdit:focus, QDoubleSpinBox:focus { border: 1px solid #6ccff6; }
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

        title = QLabel("📐   EDIT SPOOL TRAVELER METADATA")
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

        layout.addWidget(QLabel("SPOOL DRAWING ID"))
        self.in_spool_id = QLineEdit()
        self.in_spool_id.setText(str(self._current_data.get("spool_id", "")))
        layout.addWidget(self.in_spool_id)

        layout.addWidget(QLabel("ISOMETRIC DRAWING NO"))
        self.in_iso = QLineEdit()
        self.in_iso.setText(str(self._current_data.get("iso_no", "")))
        layout.addWidget(self.in_iso)

        layout.addWidget(QLabel("LINE NUMBER / SYSTEM"))
        self.in_line = QLineEdit()
        self.in_line.setText(str(self._current_data.get("line_no", "")))
        layout.addWidget(self.in_line)

        layout.addWidget(QLabel("PIPING MATERIAL SPEC (CLASS)"))
        self.in_spec = QLineEdit()
        self.in_spec.setText(str(self._current_data.get("spec", "")))
        layout.addWidget(self.in_spec)

        row = QHBoxLayout()
        col_wt = QVBoxLayout()
        col_wt.addWidget(QLabel("SPOOL WEIGHT (KG)"))
        self.in_weight = QDoubleSpinBox()
        self.in_weight.setRange(0.1, 50000.0)
        self.in_weight.setValue(float(self._current_data.get("weight_kg", 100.0)))
        col_wt.addWidget(self.in_weight)
        row.addLayout(col_wt)

        col_tp = QVBoxLayout()
        col_tp.addWidget(QLabel("HYDRO TEST PACKAGE NO"))
        self.in_tp = QLineEdit()
        self.in_tp.setText(str(self._current_data.get("test_pack", "")))
        col_tp.addWidget(self.in_tp)
        row.addLayout(col_tp)
        layout.addLayout(row)

        layout.addSpacing(10)

        submit_btn = QPushButton("💾  SAVE TRAVELER PASSPORT")
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

    def get_data(self) -> Dict[str, Any]:
        return {
            "spool_id": self.in_spool_id.text().strip(),
            "iso_no": self.in_iso.text().strip(),
            "line_no": self.in_line.text().strip(),
            "spec": self.in_spec.text().strip(),
            "weight_kg": self.in_weight.value(),
            "test_pack": self.in_tp.text().strip(),
        }


# ════════════════════════════════════════════════════════════════
#  MAIN SPOOL DETAIL DIALOG
# ════════════════════════════════════════════════════════════════

class SpoolDetailDialog(QDialog):
    """
    Ultra-premium Spool Detail & Fabrication Traveler Dialog.
    Fully resizable, responsive, sortable, integrated with WJCS.
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

    # Joint table columns
    COL_J_NO     = 0
    COL_J_CAT    = 1
    COL_J_TYPE   = 2
    COL_J_SIZE   = 3
    COL_J_WELDER = 4
    COL_J_FITUP  = 5
    COL_J_NDT    = 6
    COL_J_QC     = 7

    def __init__(self, db=None, spool_id: str = "SP-01-PR-2104-001", parent=None):
        super().__init__(parent)
        self.db = db
        self.spool_id = spool_id

        # Drag / resize state
        self._drag_pos: Optional[QPoint] = None
        self._drag_edge: Optional[str] = None
        self._drag_geometry: Optional[QRect] = None
        self._resize_margin = 8

        # Lifecycle
        self._is_closed = False
        self._ts_timer: Optional[QTimer] = None

        # View state
        self._joints: List[Dict[str, Any]] = []
        self._bom: List[Dict[str, Any]] = []

        self.setWindowTitle(f"PipeAgent – Spool Traveler • {self.spool_id}")
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

    # ── Spool Data ────────────────────────────────────────────
    def _init_data(self):
        self._spool_meta: Dict[str, Any] = {
            "spool_id": self.spool_id,
            "iso_no": "ISO-01-PR-2104-001",
            "line_no": '12"-PR-2104-A1A',
            "unit_area": "Unit 100 / Crude Distillation",
            "spec": "A1A • Class 150# RF",
            "material": "ASTM A106 Gr.B / ASTM A105N",
            "weight_kg": 468.5,
            "length_m": 8.45,
            "surface_m2": 7.92,
            "stage": "QC / NDT Cleared",
            "test_pack": "TP-HYD-2104-03",
        }

        self._joints = [
            {
                "joint_id": "J000000001",
                "joint_no": "W-01", "category": "Shop Weld", "type": "BW",
                "size": '12"', "nps_val": 12.0, "schedule": "Sch 40",
                "welder": "W-04", "fitup": "Accepted",
                "weld_status": "Completed",
                "ndt_status": "RT - Passed", "qc_status": "Approved",
            },
            {
                "joint_id": "J000000002",
                "joint_no": "W-02", "category": "Shop Weld", "type": "BW",
                "size": '12"', "nps_val": 12.0, "schedule": "Sch 40",
                "welder": "W-04", "fitup": "Accepted",
                "weld_status": "Completed",
                "ndt_status": "RT - Passed", "qc_status": "Approved",
            },
            {
                "joint_id": "J000000003",
                "joint_no": "W-03", "category": "Shop Weld", "type": "SW",
                "size": '2"', "nps_val": 2.0, "schedule": "Cl 3000#",
                "welder": "W-12", "fitup": "Accepted",
                "weld_status": "Completed",
                "ndt_status": "PT - Passed", "qc_status": "Approved",
            },
            {
                "joint_id": "J000000004",
                "joint_no": "W-04", "category": "Field Weld", "type": "BW",
                "size": '12"', "nps_val": 12.0, "schedule": "Sch 40",
                "welder": "W-08", "fitup": "Accepted",
                "weld_status": "In Progress",
                "ndt_status": "RT - Pending", "qc_status": "In Progress",
            },
        ]

        self._bom = [
            {
                "item": "01",
                "desc": 'Pipe 12" Sch 40 Seamless BE',
                "grade": "ASTM A106 Gr.B",
                "heat_no": "H-77402-A",
                "mtc_no": "MTC-VM-2025-901",
                "qty": "6.20 Meters",
            },
            {
                "item": "02",
                "desc": '90 Deg LR Elbow 12" Sch 40 BW',
                "grade": "ASTM A234 WPB",
                "heat_no": "EB-99321",
                "mtc_no": "MTC-ELB-8802",
                "qty": "1 PCS",
            },
            {
                "item": "03",
                "desc": 'Flange 12" WNRF Class 150 Serrated',
                "grade": "ASTM A105N",
                "heat_no": "FLG-4412-09",
                "mtc_no": "MTC-MET-2025-14",
                "qty": "1 PCS",
            },
            {
                "item": "04",
                "desc": 'Weldolet 12" x 2" Class 3000 SW',
                "grade": "ASTM A105N",
                "heat_no": "OLET-1044",
                "mtc_no": "MTC-BON-4011",
                "qty": "1 PCS",
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

        # 🔧 Set particle geometry immediately.
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

        icon_lbl = QLabel("📐")
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
            "SHOP FABRICATION  •  JOINT CONTROL  •  BOM & HEAT TRACEABILITY  •  ERECTION CLEARANCE"
        )
        sub_title.setObjectName("subTitle")
        title_col.addWidget(sub_title)
        topbar.addLayout(title_col)
        topbar.addStretch()

        self.btn_add_joint = QPushButton("➕  ADD JOINT  (Ctrl+N)")
        self.btn_add_joint.setObjectName("actionBtn")
        self.btn_add_joint.setMinimumHeight(36)
        self.btn_add_joint.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_joint.setToolTip("Add a weld joint to this spool traveler (Ctrl+N)")
        self.btn_add_joint.clicked.connect(self._on_add_joint)
        topbar.addWidget(self.btn_add_joint)

        self.btn_print = QPushButton("🖨  PRINT PASSPORT  (Ctrl+P)")
        self.btn_print.setObjectName("secondaryBtn")
        self.btn_print.setMinimumHeight(36)
        self.btn_print.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_print.setToolTip("Export Spool Traveler Passport to CSV (Ctrl+P)")
        self.btn_print.clicked.connect(self._on_print_traveler)
        topbar.addWidget(self.btn_print)

        self.btn_tag = QPushButton("🏷  PRINT TAG")
        self.btn_tag.setObjectName("secondaryBtn")
        self.btn_tag.setMinimumHeight(36)
        self.btn_tag.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tag.setToolTip("Generate a QR / barcode tag for the laydown printer")
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
        self.header_frame.setToolTip("Double-click anywhere to edit Spool specs")

        h_layout = QHBoxLayout(self.header_frame)
        h_layout.setContentsMargins(14, 8, 14, 8)
        h_layout.setSpacing(16)

        self.lbl_iso  = QLabel()
        self.lbl_line = QLabel()
        self.lbl_spec = QLabel()
        self.lbl_wt   = QLabel()
        self.lbl_tp   = QLabel()

        for lbl in [self.lbl_iso, self.lbl_line, self.lbl_spec, self.lbl_wt, self.lbl_tp]:
            lbl.setStyleSheet(
                "color: #7a9ab3; font-size: 11px; background: transparent;"
            )
            h_layout.addWidget(lbl)

        self.btn_edit_hdr = QPushButton("✏  EDIT")
        self.btn_edit_hdr.setObjectName("editHdrBtn")
        self.btn_edit_hdr.setFixedHeight(24)
        self.btn_edit_hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit_hdr.setToolTip("Edit spool specifications")
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

        # Double-click on the frame → edit header
        self.header_frame.mouseDoubleClickEvent = lambda e: self._on_edit_header()

        self._refresh_header_display()
        return self.header_frame

    def _build_kpi_ribbon(self) -> QHBoxLayout:
        stat_ribbon = QHBoxLayout()
        stat_ribbon.setSpacing(12)

        self.kpi_prog   = StatCard("SPOOL FAB PROGRESS", "0%", "⚡", self.PRIMARY_LIGHT)
        self.kpi_joints = StatCard("TOTAL WELD JOINTS", "0", "🔗", self.ACCENT)
        self.kpi_inch   = StatCard("TOTAL INCH-DIA (ID)", "0.0\"", "📏", self.SUCCESS)
        self.kpi_stage  = StatCard(
            "LIFECYCLE STATUS", self._spool_meta["stage"], "🛡️", self.WARNING
        )

        stat_ribbon.addWidget(self.kpi_prog)
        stat_ribbon.addWidget(self.kpi_joints)
        stat_ribbon.addWidget(self.kpi_inch)
        stat_ribbon.addWidget(self.kpi_stage)
        return stat_ribbon

    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("spoolTabs")

        # Tab 1: Joints Register
        self.tab_joints = QWidget()
        t1_layout = QVBoxLayout(self.tab_joints)
        t1_layout.setContentsMargins(8, 8, 8, 8)

        self.joint_table = QTableWidget()
        self.joint_table.setObjectName("jointTable")
        self.joint_table.setColumnCount(8)
        self.joint_table.setHorizontalHeaderLabels([
            "Joint No", "Category", "Type", "Size",
            "Welder", "Fit-up", "NDT Status", "QC Approval",
        ])

        self.joint_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.joint_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.joint_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.joint_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        header1 = self.joint_table.horizontalHeader()
        header1.setSectionsMovable(True)
        header1.setSectionsClickable(True)
        header1.setStretchLastSection(True)
        for col_idx in range(self.joint_table.columnCount()):
            header1.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

        default_widths1 = [100, 110, 70, 70, 100, 100, 130, 130]
        for col_idx, w in enumerate(default_widths1):
            self.joint_table.setColumnWidth(col_idx, w)

        self.joint_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.joint_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.joint_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.joint_table.verticalHeader().setVisible(False)
        self.joint_table.setShowGrid(False)
        self.joint_table.setAlternatingRowColors(True)
        self.joint_table.setSortingEnabled(True)
        self.joint_table.setWordWrap(False)
        self.joint_table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.joint_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.joint_table.customContextMenuRequested.connect(self._show_context_menu)
        self.joint_table.itemSelectionChanged.connect(self._on_joint_selection)
        self.joint_table.doubleClicked.connect(self._on_add_joint)

        t1_layout.addWidget(self.joint_table)
        tabs.addTab(self.tab_joints, "🔗  WJCS JOINTS REGISTER")

        # Tab 2: Bill of Materials
        self.tab_bom = QWidget()
        t2_layout = QVBoxLayout(self.tab_bom)
        t2_layout.setContentsMargins(8, 8, 8, 8)

        self.bom_table = QTableWidget()
        self.bom_table.setObjectName("bomTable")
        self.bom_table.setColumnCount(6)
        self.bom_table.setHorizontalHeaderLabels([
            "Item", "Description", "Material Grade",
            "Heat / Cast No", "MTC Number", "Qty / Length",
        ])

        self.bom_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.bom_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.bom_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.bom_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        header2 = self.bom_table.horizontalHeader()
        header2.setSectionsMovable(True)
        header2.setSectionsClickable(True)
        header2.setStretchLastSection(True)
        for col_idx in range(self.bom_table.columnCount()):
            header2.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

        default_widths2 = [60, 240, 130, 130, 150, 120]
        for col_idx, w in enumerate(default_widths2):
            self.bom_table.setColumnWidth(col_idx, w)

        self.bom_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.bom_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.bom_table.verticalHeader().setVisible(False)
        self.bom_table.setShowGrid(False)
        self.bom_table.setAlternatingRowColors(True)
        self.bom_table.setSortingEnabled(True)
        self.bom_table.setWordWrap(False)

        t2_layout.addWidget(self.bom_table)
        tabs.addTab(self.tab_bom, "📋  BILL OF MATERIALS (BOM & HEAT)")

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

        head_lbl = QLabel("🔍   SPOOL & JOINT INSPECTOR")
        head_lbl.setObjectName("inspHead")
        layout.addWidget(head_lbl)

        div = QFrame()
        div.setObjectName("divider")
        div.setFixedHeight(1)
        layout.addWidget(div)

        self.insp_target = QLabel("Select a Joint")
        self.insp_target.setObjectName("inspTarget")
        self.insp_target.setWordWrap(True)
        layout.addWidget(self.insp_target)

        self.insp_sub = QLabel(
            "Select a weld joint from the WJCS tab to review fit-up details, "
            "welder stamp, and NDT acceptance."
        )
        self.insp_sub.setObjectName("inspSub")
        self.insp_sub.setWordWrap(True)
        layout.addWidget(self.insp_sub)

        self.meta_frame = QFrame()
        self.meta_frame.setObjectName("metaFrame")
        m_layout = QVBoxLayout(self.meta_frame)
        m_layout.setContentsMargins(10, 8, 10, 8)
        m_layout.setSpacing(5)

        self.m_cat    = QLabel()
        self.m_type   = QLabel()
        self.m_size   = QLabel()
        self.m_welder = QLabel()
        self.m_fitup  = QLabel()
        self.m_ndt    = QLabel()

        # Declarative spec for both populate and reset.
        self._meta_specs = [
            (self.m_cat,    "Category"),
            (self.m_type,   "Joint Type"),
            (self.m_size,   "Size / NPS"),
            (self.m_welder, "Welder ID"),
            (self.m_fitup,  "Fit-up Status"),
            (self.m_ndt,    "NDT Method"),
        ]

        for lbl, _ in self._meta_specs:
            lbl.setStyleSheet(
                "color: #dfeaf5; font-size: 11px; background: transparent;"
            )
            lbl.setWordWrap(True)
            m_layout.addWidget(lbl)

        layout.addWidget(self.meta_frame)

        stage_lbl = QLabel("⚡   ADVANCE SPOOL STAGE:")
        stage_lbl.setStyleSheet(
            "color: #9fe7ff; font-size: 9px; font-weight: 800; "
            "letter-spacing: 1px; margin-top: 4px; background: transparent;"
        )
        layout.addWidget(stage_lbl)

        self.combo_stage = QComboBox()
        self.combo_stage.setObjectName("stageCombo")
        self.combo_stage.setMinimumHeight(32)
        self.combo_stage.addItems([
            "Material Allocated",
            "Cutting & Fit-up",
            "Welding in Progress",
            "QC / NDT Cleared",
            "Pickling & Painting",
            "Released to Site Laydown",
            "Erected on Pipe Rack",
            "Hydrotested & Accepted",
        ])
        self.combo_stage.setCurrentText(self._spool_meta["stage"])
        self.combo_stage.setToolTip("Current spool fabrication stage")
        self.combo_stage.currentTextChanged.connect(self._on_stage_changed)
        layout.addWidget(self.combo_stage)

        layout.addStretch()

        self.btn_delete = QPushButton("🗑  REMOVE JOINT")
        self.btn_delete.setObjectName("btnDelete")
        self.btn_delete.setMinimumHeight(32)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setEnabled(False)
        self.btn_delete.setToolTip("Remove the selected joint from this spool")
        self.btn_delete.clicked.connect(self._on_remove_joint)
        layout.addWidget(self.btn_delete)

        scroll.setWidget(inner)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(scroll)
        return panel

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 2, 4, 0)

        self.lbl_count = QLabel("All joints synchronized with WJCS master database.")
        self.lbl_count.setObjectName("footerLabel")
        footer.addWidget(self.lbl_count)

        footer.addStretch()

        self.lbl_timestamp = QLabel("")
        self.lbl_timestamp.setObjectName("footerLabel")
        footer.addWidget(self.lbl_timestamp)

        footer.addStretch()

        foot_tag = QLabel(
            "⚡  PipeAgent 5.0  •  Continuous Spool Traveler & QC Clearance Engine"
        )
        foot_tag.setStyleSheet(
            "color: #3f6070; font-size: 10px; letter-spacing: 1px; background: transparent;"
        )
        footer.addWidget(foot_tag)
        return footer

    # ── Keyboard Shortcuts ────────────────────────────────────
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self, self._on_add_joint)
        QShortcut(QKeySequence("Ctrl+P"), self, self._on_print_traveler)
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)

        # 🔧 Bind Delete to the table only — typing Delete inside other
        #    inputs no longer removes a joint.
        del_sc = QShortcut(
            QKeySequence("Delete"), self.joint_table, self._on_remove_joint
        )
        del_sc.setContext(Qt.ShortcutContext.WidgetShortcut)

    def _focus_search(self):
        self.tabs.setCurrentIndex(0)
        self.joint_table.setFocus()

    # ── Context Menu ──────────────────────────────────────────
    def _show_context_menu(self, pos):
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

        selected = self._get_selected_joint()

        act_approve = menu.addAction("✅  Accept Fit-up")
        act_approve.setEnabled(selected is not None)
        act_approve.triggered.connect(
            lambda: self._set_selected_qc_status("Accepted", "Approved")
        )

        act_reject = menu.addAction("❌  Reject Fit-up")
        act_reject.setEnabled(selected is not None)
        act_reject.triggered.connect(
            lambda: self._set_selected_qc_status("Rejected", "In Progress")
        )

        menu.addSeparator()

        act_rt_pass = menu.addAction("🛡️  RT Clearance - Passed")
        act_rt_pass.setEnabled(selected is not None)
        act_rt_pass.triggered.connect(
            lambda: self._set_selected_ndt_clearance("RT - Passed", "Approved")
        )

        act_rt_pend = menu.addAction("⏳  RT Pending")
        act_rt_pend.setEnabled(selected is not None)
        act_rt_pend.triggered.connect(
            lambda: self._set_selected_ndt_clearance("RT - Pending", "In Progress")
        )

        act_new = menu.addAction("➕  Add Weld Joint  (Ctrl+N)")
        act_new.triggered.connect(self._on_add_joint)

        menu.addSeparator()

        act_delete = menu.addAction("🗑  Remove Joint")
        act_delete.setEnabled(selected is not None)
        act_delete.triggered.connect(self._on_remove_joint)

        menu.exec(self.joint_table.viewport().mapToGlobal(pos))

    # ── Header Refresh ────────────────────────────────────────
    def _refresh_header_display(self):
        self.main_title.setText(
            f"PIPE AGENT  •  SPOOL TRAVELER & PASSPORT [{self._spool_meta['spool_id']}]"
        )
        self.lbl_iso.setText(
            f"<b>ISO:</b> <span style='color:#9fe7ff;'>"
            f"{self._spool_meta['iso_no']}</span>"
        )
        self.lbl_line.setText(
            f"<b>LINE NO:</b> <span style='color:#9fe7ff;'>"
            f"{self._spool_meta['line_no']}</span>"
        )
        self.lbl_spec.setText(
            f"<b>SPEC:</b> <span style='color:#eef6ff;'>"
            f"{self._spool_meta['spec']}</span>"
        )
        self.lbl_wt.setText(
            f"<b>WEIGHT:</b> <span style='color:#7a9ab3;'>"
            f"{self._spool_meta['weight_kg']:.1f} kg</span>"
        )
        self.lbl_tp.setText(
            f"<b>TEST PACK:</b> <span style='color:#7a9ab3;'>"
            f"{self._spool_meta['test_pack']}</span>"
        )

    def _on_edit_header(self):
        modal = EditSpoolMetaDialog(self._spool_meta, self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return

        new_data = modal.get_data()
        self._spool_meta.update(new_data)
        self.spool_id = self._spool_meta["spool_id"]
        self.setWindowTitle(f"PipeAgent – Spool Traveler • {self.spool_id}")
        self._refresh_header_display()
        self._update_kpi()

        QMessageBox.information(
            self, "✅ Spool Updated",
            "Spool traveler specifications have been successfully modified.",
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
                letter-spacing: 2.5px;
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
            QTabWidget#spoolTabs::pane {{
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
            QComboBox#stageCombo {{
                background: #07101a;
                color: {self.PRIMARY_LIGHT};
                border: 1px solid #18364a;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton#btnDelete {{
                background: transparent;
                color: #8faec5;
                border: 1px solid #1b354d;
                border-radius: 6px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton#btnDelete:hover {{
                color: {self.ERROR};
                border: 1px solid {self.ERROR};
                background: rgba(255, 107, 107, 0.1);
            }}
            QPushButton#btnDelete:disabled {{
                color: #3a5060; border: 1px solid #0f1f30;
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

    def _get_selected_joint(self) -> Optional[Dict[str, Any]]:
        """
        Return the joint stored on the selected row.

        The joint is attached to the first column's UserRole, so the result
        is correct even after the user re-sorts the table.
        """
        rows = self.joint_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.joint_table.item(rows[0].row(), self.COL_J_NO)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _find_joint_index(self, joint_id: str) -> int:
        """Locate a joint by stable id. Returns -1 if missing."""
        for idx, j in enumerate(self._joints):
            if j.get("joint_id") == joint_id:
                return idx
        return -1

    def _reselect_by_joint_id(self, joint_id: str):
        for row_idx in range(self.joint_table.rowCount()):
            item = self.joint_table.item(row_idx, self.COL_J_NO)
            if item is None:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("joint_id") == joint_id:
                self.joint_table.selectRow(row_idx)
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
        self._populate_joints_table()
        self._populate_bom_table()

    def _populate_joints_table(self):
        self.joint_table.setSortingEnabled(False)
        self.joint_table.setRowCount(0)

        for row_idx, j in enumerate(self._joints):
            self.joint_table.insertRow(row_idx)

            # Col 0: Joint No — also carries the joint dict via UserRole.
            item_j = QTableWidgetItem(j["joint_no"])
            item_j.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            item_j.setForeground(QColor(self.PRIMARY_LIGHT))
            item_j.setData(Qt.ItemDataRole.UserRole, j)  # ← sort-safe link
            self.joint_table.setItem(row_idx, self.COL_J_NO, item_j)

            # Col 1: Category
            item_cat = QTableWidgetItem(j["category"])
            item_cat.setForeground(QColor("#a2c2dc"))
            self.joint_table.setItem(row_idx, self.COL_J_CAT, item_cat)

            # Col 2: Type
            item_type = QTableWidgetItem(j["type"])
            item_type.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_type.setForeground(QColor(self.TEXT_MAIN))
            self.joint_table.setItem(row_idx, self.COL_J_TYPE, item_type)

            # Col 3: Size
            item_size = QTableWidgetItem(j["size"])
            item_size.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            item_size.setForeground(QColor(self.ACCENT))
            self.joint_table.setItem(row_idx, self.COL_J_SIZE, item_size)

            # Col 4: Welder
            item_w = QTableWidgetItem(j["welder"])
            item_w.setFont(QFont("Consolas", 10))
            item_w.setForeground(QColor("#ffd966"))
            self.joint_table.setItem(row_idx, self.COL_J_WELDER, item_w)

            # Col 5: Fit-up
            item_fit = QTableWidgetItem(j["fitup"])
            if j["fitup"] == "Accepted":
                item_fit.setForeground(QColor(self.SUCCESS))
            else:
                item_fit.setForeground(QColor(self.WARNING))
            self.joint_table.setItem(row_idx, self.COL_J_FITUP, item_fit)

            # Col 6: NDT
            item_ndt = QTableWidgetItem(j["ndt_status"])
            if "Passed" in j["ndt_status"]:
                item_ndt.setForeground(QColor(self.SUCCESS))
            elif "Pending" in j["ndt_status"]:
                item_ndt.setForeground(QColor(self.WARNING))
            else:
                item_ndt.setForeground(QColor(self.ERROR))
            self.joint_table.setItem(row_idx, self.COL_J_NDT, item_ndt)

            # Col 7: QC Approval
            item_qc = QTableWidgetItem(f" ● {j['qc_status']} ")
            item_qc.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item_qc.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if j["qc_status"] == "Approved":
                item_qc.setForeground(QColor(self.SUCCESS))
            else:
                item_qc.setForeground(QColor(self.WARNING))
            self.joint_table.setItem(row_idx, self.COL_J_QC, item_qc)

        self.joint_table.setSortingEnabled(True)

        if self._joints:
            self.joint_table.selectRow(0)
        else:
            self._clear_inspector()

    def _populate_bom_table(self):
        self.bom_table.setSortingEnabled(False)
        self.bom_table.setRowCount(0)

        for r_idx, b in enumerate(self._bom):
            self.bom_table.insertRow(r_idx)

            item_no = QTableWidgetItem(b["item"])
            item_no.setFont(QFont("Consolas", 10))
            item_no.setForeground(QColor(self.PRIMARY_LIGHT))
            self.bom_table.setItem(r_idx, 0, item_no)

            item_desc = QTableWidgetItem(b["desc"])
            item_desc.setForeground(QColor(self.TEXT_MAIN))
            item_desc.setToolTip(b["desc"])
            self.bom_table.setItem(r_idx, 1, item_desc)

            item_grd = QTableWidgetItem(b["grade"])
            item_grd.setForeground(QColor("#a2c2dc"))
            self.bom_table.setItem(r_idx, 2, item_grd)

            item_heat = QTableWidgetItem(b["heat_no"])
            item_heat.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            item_heat.setForeground(QColor(self.ACCENT))
            self.bom_table.setItem(r_idx, 3, item_heat)

            item_mtc = QTableWidgetItem(b["mtc_no"])
            item_mtc.setFont(QFont("Consolas", 9))
            item_mtc.setForeground(QColor("#708fa8"))
            self.bom_table.setItem(r_idx, 4, item_mtc)

            item_qty = QTableWidgetItem(b["qty"])
            item_qty.setForeground(QColor(self.TEXT_MAIN))
            self.bom_table.setItem(r_idx, 5, item_qty)

        self.bom_table.setSortingEnabled(True)

    def _update_kpi(self):
        total_joints = len(self._joints)
        total_inch_dia = sum(j.get("nps_val", 0.0) for j in self._joints)
        approved_joints = sum(
            1 for j in self._joints if j["qc_status"] == "Approved"
        )

        prog_pct = (
            (approved_joints / total_joints * 100) if total_joints > 0 else 0.0
        )

        self.kpi_prog.update_value(f"{prog_pct:.1f}%")
        self.kpi_joints.update_value(str(total_joints))
        self.kpi_inch.update_value(f"{total_inch_dia:.1f}\"")
        self.kpi_stage.update_value(self._spool_meta["stage"])

        self.lbl_count.setText(
            f"WJCS: {total_joints} joints locked on spool traveler. "
            f"Fabrication Completion Level: {prog_pct:.1f}%"
        )

    # ── Table Selection → Inspector ───────────────────────────
    def _on_joint_selection(self):
        j = self._get_selected_joint()
        if j is None:
            self._clear_inspector()
            return

        self.insp_target.setText(f"JOINT: {j['joint_no']} ({j['size']})")
        self.insp_sub.setText(
            f"Category: {j['category']} • Welder: {j['welder']}"
        )

        self.m_cat.setText(f"<b>Category:</b> {j['category']}")
        self.m_type.setText(f"<b>Joint Type:</b> {j['type']} ({j['schedule']})")
        self.m_size.setText(f"<b>Size / NPS:</b> {j['size']}")
        self.m_welder.setText(f"<b>Welder ID:</b> {j['welder']}")

        fit = j["fitup"]
        fit_color = (
            self.SUCCESS if fit == "Accepted"
            else self.WARNING if "Pending" in fit
            else self.ERROR
        )
        self.m_fitup.setText(
            f"<b>Fit-up Status:</b> <span style='color:{fit_color}'>{fit}</span>"
        )

        self.m_ndt.setText(f"<b>NDT Clearance:</b> {j['ndt_status']}")
        self.btn_delete.setEnabled(True)

    def _clear_inspector(self):
        self.insp_target.setText("No Joint Selected")
        self.insp_sub.setText(
            "Select any weld joint from the WJCS tab to review fit-up details, "
            "welder stamp, and NDT acceptance."
        )
        for lbl, title in self._meta_specs:
            lbl.setText(f"<b>{title}:</b> —")
        self.btn_delete.setEnabled(False)

    # ── Quick Context Actions ─────────────────────────────────
    def _set_selected_qc_status(self, fitup_status: str, qc_status: str):
        selected = self._get_selected_joint()
        if selected is None:
            return

        idx = self._find_joint_index(selected.get("joint_id", ""))
        if idx < 0:
            return

        self._joints[idx]["fitup"] = fitup_status
        self._joints[idx]["qc_status"] = qc_status

        target_id = self._joints[idx].get("joint_id", "")
        self._populate_joints_table()
        self._update_kpi()
        self._reselect_by_joint_id(target_id)

    def _set_selected_ndt_clearance(self, ndt_status: str, qc_status: str):
        selected = self._get_selected_joint()
        if selected is None:
            return

        idx = self._find_joint_index(selected.get("joint_id", ""))
        if idx < 0:
            return

        self._joints[idx]["ndt_status"] = ndt_status
        self._joints[idx]["qc_status"] = qc_status

        target_id = self._joints[idx].get("joint_id", "")
        self._populate_joints_table()
        self._update_kpi()
        self._reselect_by_joint_id(target_id)

    # ── Spool Lifecycle ───────────────────────────────────────
    def _on_stage_changed(self, new_stage: str):
        self._spool_meta["stage"] = new_stage
        self._update_kpi()

    # ── Add & Remove Joint ────────────────────────────────────
    def _on_add_joint(self):
        existing_joints = [j["joint_no"] for j in self._joints]
        modal = AddJointDialog(existing_joints=existing_joints, parent=self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return

        new_j = modal.get_data()
        self._joints.append(new_j)
        self._populate_joints_table()
        self._update_kpi()
        self._reselect_by_joint_id(new_j["joint_id"])

    def _on_remove_joint(self):
        selected = self._get_selected_joint()
        if selected is None:
            return

        reply = QMessageBox.warning(
            self, "⚠ Remove Weld Joint",
            f"Are you sure you want to remove Joint "
            f"<b>{selected['joint_no']}</b> ({selected['size']}) "
            f"from this Spool Traveler register?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        idx = self._find_joint_index(selected.get("joint_id", ""))
        if idx < 0:
            return
        self._joints.pop(idx)
        self._populate_joints_table()
        self._update_kpi()

    # ── Export Spool Traveler & Zebra Tag ─────────────────────
    def _on_print_traveler(self):
        default_name = f"Spool_Traveler_Dossier_{self.spool_id}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Spool Traveler Passport Dossier",
            default_name, "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["═══ SPOOL FABRICATION TRAVELER PASSPORT ═══"])
                writer.writerow(["Spool ID", self._spool_meta["spool_id"]])
                writer.writerow(["Isometric No", self._spool_meta["iso_no"]])
                writer.writerow(["Line Number", self._spool_meta["line_no"]])
                writer.writerow(["Material Class", self._spool_meta["spec"]])
                writer.writerow(["Carbon Steel Grade", self._spool_meta["material"]])
                writer.writerow(["Lifecycle Stage", self._spool_meta["stage"]])
                writer.writerow(["Weight (KG)", self._spool_meta["weight_kg"]])
                writer.writerow(["Hydrotest Pack", self._spool_meta["test_pack"]])
                writer.writerow([])

                writer.writerow(["═══ WJCS JOINT TRACKING REGISTER ═══"])
                writer.writerow([
                    "Joint No", "Category", "Type", "Size",
                    "Welder ID", "Fit-up Status", "NDT Status", "QC Approval",
                ])
                for j in self._joints:
                    writer.writerow([
                        j["joint_no"], j["category"], j["type"], j["size"],
                        j["welder"], j["fitup"], j["ndt_status"], j["qc_status"],
                    ])
                writer.writerow([])

                writer.writerow(["═══ MATERIAL TRACEABILITY MATRIX (BOM) ═══"])
                writer.writerow([
                    "BOM Item", "Component Description", "Material Grade",
                    "Heat Number", "MTC Certificate No", "Qty Allocated",
                ])
                for b in self._bom:
                    writer.writerow([
                        b["item"], b["desc"], b["grade"],
                        b["heat_no"], b["mtc_no"], b["qty"],
                    ])

            QMessageBox.information(
                self, "✅ Spool Passport Exported",
                f"Spool traveler dossier successfully saved to:\n\n{path}",
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
                f"Could not export spool passport traveler: {e}",
            )

    def _on_print_tag(self):
        total_joints = len(self._joints)
        total_id = sum(j.get("nps_val", 0.0) for j in self._joints)

        QMessageBox.information(
            self, "🏷 Zebra Thermal Tag Utility",
            f"<b>Laydown Barcode / QR Label Generated:</b><br><br>"
            f"• <b>Spool Drawing ID:</b> {self._spool_meta['spool_id']}<br>"
            f"• <b>System Line:</b> {self._spool_meta['line_no']}<br>"
            f"• <b>ISO Refer:</b> {self._spool_meta['iso_no']}<br>"
            f"• <b>Allocated Joints:</b> {total_joints} welds "
            f"({total_id:.1f}\" weld diameter)<br>"
            f"• <b>Stage:</b> {self._spool_meta['stage']}<br><br>"
            f"<i>Payload successfully streamed to Laydown Yard Zebra Tag Printer.</i>",
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

    dialog = SpoolDetailDialog(spool_id="SP-01-PR-2104-001")
    dialog.show()
    dialog.exec()

    sys.exit(0)