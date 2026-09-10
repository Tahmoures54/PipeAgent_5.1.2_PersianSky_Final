# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Material Receipt & Inspection Dialog (MRIR)
═══════════════════════════════════════════════════════════════════════
Version : 5.0 (Refactored, hardened, production-ready)
Engine  : PyQt6
Design  : Cinematic dark-tech theme matching PipeAgent Suite

Fixes in this revision
──────────────────────
🔴 P0  Sort-safe selection : each row stores its item dict on
                           QTableWidgetItem.UserRole, so sorting the table
                           no longer returns the wrong item
🔴 P0  Item identity       : every item has a stable `item_id`; lookups use
                           that id instead of `list.index(dict)` (which could
                           match a *different* item that happened to have
                           identical content)
🔴 P0  GlowLineEdit        : no longer calls deleteLater() on an animation
                           that Qt owns (DeleteWhenStopped)
🔴 P0  Card border         : replaced invalid `border: ... qlineargradient`
                           with a solid border + drop shadow
🟠 P1  Delete shortcut     : bound to the table only (WidgetShortcut), so
                           typing Delete inside a search field is safe
🟠 P1  closeEvent chain    : split `_cleanup()` from `_on_close()`; dialog
                           cleanup runs exactly once
🟠 P1  Filter reset        : signals blocked during reset → single refilter
🟡 P2  _clear_inspector    : driven by a declared label spec, not by
                           string splitting
🟡 P2  ParticleField       : count 30 → 16, tick 60ms → 100ms, paint only
                           when visible
🟡 P2  Duplicate heat check: existing heats stored in a set() → O(1)
🟡 P2  EditHeaderDialog    : added drag handle, Cancel button, tooltips
🟢 P3  General             : single _today() helper, no double closeEvent,
                           no duplicate timers
"""

from __future__ import annotations

import os
import sys
import csv
import random
import uuid
import logging
from datetime import datetime
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
    QFileDialog, QSpinBox, QDoubleSpinBox, QTextEdit,
    QMenu, QScrollArea, QCheckBox,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#  UTILITIES
# ════════════════════════════════════════════════════════════════

def _new_item_id() -> str:
    """Short, collision-resistant item identifier."""
    return "I" + uuid.uuid4().hex[:9].upper()


def _today_str() -> str:
    return datetime.today().strftime("%Y-%m-%d")


# ════════════════════════════════════════════════════════════════
#  PARTICLE FIELD
# ════════════════════════════════════════════════════════════════

class ParticleField(QWidget):
    """Subtle floating particle background with optimized rendering."""

    TICK_MS = 100

    def __init__(self, parent=None, count: int = 16):
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
    """Metric tile with left glow border."""

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
#  ADD MATERIAL ITEM SUB-MODAL
# ════════════════════════════════════════════════════════════════

class AddMaterialItemDialog(QDialog):
    """Sub-modal for adding a piping material item into the MRIR receipt."""

    def __init__(self, existing_heats: Optional[Iterable[str]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Received Material Item")
        self.setMinimumSize(520, 620)
        self.setMaximumSize(700, 780)
        self.resize(520, 640)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos: Optional[QPoint] = None
        # Set for O(1) duplicate lookup.
        self._existing_heats = {h.upper() for h in (existing_heats or [])}
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("itemCard")
        card.setStyleSheet("""
            QWidget#itemCard {
                background: #0b1624;
                border: 2px solid #6ccff6;
                border-radius: 14px;
            }
            QLabel { color: #9fe7ff; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
            QLineEdit, QComboBox, QSpinBox {
                background: #07101a;
                color: #eef6ff;
                border: 1px solid #18364a;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #6ccff6;
            }
            QComboBox QAbstractItemView {
                background: #07101a;
                color: #eef6ff;
                selection-background-color: #14334f;
                selection-color: #9fe7ff;
                border: 1px solid #18364a;
            }
            QSpinBox::up-button, QSpinBox::down-button { width: 16px; }
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

        # Header
        head = QHBoxLayout()
        title = QLabel("📦   ADD PIPING COMPONENT TO MRIR")
        title.setStyleSheet(
            "font-size: 13px; color: #9fe7ff; "
            "font-weight: 900; letter-spacing: 2px;"
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

        # Category & Tag
        row0 = QHBoxLayout()
        col_cat = QVBoxLayout()
        col_cat.addWidget(QLabel("COMPONENT CATEGORY *"))
        self.in_cat = QComboBox()
        self.in_cat.addItems([
            "Pipe (Seamless/Welded)", "Flange (WN/Blind/SO)",
            "Fitting (Elbow/Tee/Reducer)",
            "Valve (Gate/Globe/Ball/Check)",
            "Gasket (Spiral Wound/RTJ)", "Stud Bolts & Nuts",
        ])
        col_cat.addWidget(self.in_cat)
        row0.addLayout(col_cat)

        col_tag = QVBoxLayout()
        col_tag.addWidget(QLabel("ITEM TAG / PO ITEM #"))
        self.in_tag = QLineEdit()
        self.in_tag.setPlaceholderText("Auto-generated if empty")
        col_tag.addWidget(self.in_tag)
        row0.addLayout(col_tag)
        layout.addLayout(row0)

        # Description
        layout.addWidget(QLabel("MATERIAL DESCRIPTION & SPECIFICATION *"))
        self.in_desc = QLineEdit()
        self.in_desc.setPlaceholderText(
            'e.g. Pipe 6" Sch 40 BE Seamless ASTM A106 Gr.B'
        )
        layout.addWidget(self.in_desc)

        # Grade & Size
        row1 = QHBoxLayout()
        col_grade = QVBoxLayout()
        col_grade.addWidget(QLabel("MATERIAL GRADE"))
        self.in_grade = QComboBox()
        self.in_grade.setEditable(True)
        self.in_grade.addItems([
            "ASTM A106 Gr.B", "ASTM A312 TP316L", "ASTM A312 TP304L",
            "ASTM A105N", "ASTM A234 WPB", "ASTM A182 F316L",
            "ASTM A350 LF2", "API 5L Gr.B / X52",
        ])
        col_grade.addWidget(self.in_grade)
        row1.addLayout(col_grade)

        col_size = QVBoxLayout()
        col_size.addWidget(QLabel("SIZE / RATING / SCHEDULE"))
        self.in_size = QLineEdit()
        self.in_size.setPlaceholderText('e.g. 6" Sch 40 / Cl 300#')
        col_size.addWidget(self.in_size)
        row1.addLayout(col_size)
        layout.addLayout(row1)

        # Heat & MTC
        row2 = QHBoxLayout()
        col_heat = QVBoxLayout()
        col_heat.addWidget(QLabel("HEAT / CAST / LOT NUMBER *"))
        self.in_heat = QLineEdit()
        self.in_heat.setPlaceholderText("e.g. H-88412-B")
        col_heat.addWidget(self.in_heat)
        row2.addLayout(col_heat)

        col_mtc = QVBoxLayout()
        col_mtc.addWidget(QLabel("MTC / CERTIFICATE NUMBER"))
        self.in_mtc = QLineEdit()
        self.in_mtc.setPlaceholderText("e.g. MTC-VAL-2025-99 (or leave for MISSING)")
        col_mtc.addWidget(self.in_mtc)
        row2.addLayout(col_mtc)
        layout.addLayout(row2)

        self.lbl_dup_warn = QLabel("⚠ This Heat Number already exists in this MRIR!")
        self.lbl_dup_warn.setStyleSheet(
            "color: #ff9f43; font-size: 10px; font-weight: 700; background: transparent;"
        )
        self.lbl_dup_warn.setVisible(False)
        layout.addWidget(self.lbl_dup_warn)
        self.in_heat.textChanged.connect(self._check_duplicate_heat)

        # Quantities
        row3 = QHBoxLayout()
        col_q_recv = QVBoxLayout()
        col_q_recv.addWidget(QLabel("QUANTITY RECEIVED"))
        self.in_q_recv = QSpinBox()
        self.in_q_recv.setRange(1, 100000)
        self.in_q_recv.setValue(10)
        col_q_recv.addWidget(self.in_q_recv)
        row3.addLayout(col_q_recv)

        col_unit = QVBoxLayout()
        col_unit.addWidget(QLabel("UNIT"))
        self.in_unit = QComboBox()
        self.in_unit.addItems([
            "Length (Meters)", "PCS (Pieces)",
            "Joints", "Sets", "KGs",
        ])
        col_unit.addWidget(self.in_unit)
        row3.addLayout(col_unit)

        col_stat = QVBoxLayout()
        col_stat.addWidget(QLabel("INITIAL QC STATUS"))
        self.in_status = QComboBox()
        self.in_status.addItems([
            "Accepted", "Quarantined", "Pending MTC", "Rejected",
        ])
        col_stat.addWidget(self.in_status)
        row3.addLayout(col_stat)
        layout.addLayout(row3)

        # PMI & Location
        row4 = QHBoxLayout()
        col_pmi = QVBoxLayout()
        col_pmi.addWidget(QLabel("PMI REQUIRED?"))
        self.in_pmi = QComboBox()
        self.in_pmi.addItems([
            "Yes - Passed", "Yes - Pending", "Not Required (CS)",
        ])
        col_pmi.addWidget(self.in_pmi)
        row4.addLayout(col_pmi)

        col_loc = QVBoxLayout()
        col_loc.addWidget(QLabel("STORAGE LOCATION / BAY"))
        self.in_loc = QLineEdit()
        self.in_loc.setPlaceholderText("e.g. Yard-B / Rack-04")
        col_loc.addWidget(self.in_loc)
        row4.addLayout(col_loc)
        layout.addLayout(row4)

        layout.addSpacing(10)

        # Submit
        submit_btn = QPushButton("⚡  INSERT INTO MRIR REGISTER")
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

        # Cancel
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

    def _check_duplicate_heat(self, text: str):
        is_dup = text.strip().upper() in self._existing_heats
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
        if not self.in_desc.text().strip():
            QMessageBox.warning(
                self, "Validation Error", "Item Description is required."
            )
            self.in_desc.setFocus()
            return

        heat = self.in_heat.text().strip()
        if not heat:
            QMessageBox.warning(
                self, "Validation Error",
                "Heat / Lot Number is required for piping traceability.",
            )
            self.in_heat.setFocus()
            return

        if heat.upper() in self._existing_heats:
            reply = QMessageBox.question(
                self, "Duplicate Heat Number",
                f"Heat number <b>{heat}</b> already exists in this MRIR.\n\n"
                "Do you still want to add this item?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.accept()

    def get_data(self) -> Dict[str, Any]:
        qty_recv = self.in_q_recv.value()
        status = self.in_status.currentText()
        return {
            "item_id": _new_item_id(),
            "tag": self.in_tag.text().strip(),  # empty = auto-generate later
            "category": self.in_cat.currentText().split(" ")[0],
            "desc": self.in_desc.text().strip(),
            "grade": self.in_grade.currentText().strip(),
            "size": self.in_size.text().strip() or "Standard",
            "heat_no": self.in_heat.text().strip().upper(),
            "mtc_no": self.in_mtc.text().strip() or "MISSING",
            "qty_recv": qty_recv,
            "qty_acc": qty_recv if status == "Accepted" else 0,
            "unit": self.in_unit.currentText().split(" ")[0],
            "status": status,
            "pmi": self.in_pmi.currentText(),
            "location": self.in_loc.text().strip() or "Laydown Yard",
        }


# ════════════════════════════════════════════════════════════════
#  MRIR HEADER EDITOR
# ════════════════════════════════════════════════════════════════

class EditHeaderDialog(QDialog):
    """Sub-modal for editing MRIR header information."""

    def __init__(self, current_data: Dict[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit MRIR Header")
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

        # Header bar
        head = QHBoxLayout()
        drag_hint = QLabel("⠿")
        drag_hint.setStyleSheet(
            "color: #2a4a5a; font-size: 14px; background: transparent;"
        )
        drag_hint.setToolTip("Drag to move window")
        head.addWidget(drag_hint)

        title = QLabel("📋   EDIT MRIR HEADER INFO")
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

        # Fields
        fields = [
            ("mrir_no", "MRIR NUMBER"),
            ("po_no", "PURCHASE ORDER"),
            ("vendor", "VENDOR / SUPPLIER"),
            ("delivery_note", "DELIVERY NOTE"),
            ("inspector", "QC INSPECTOR"),
            ("warehouse", "WAREHOUSE / LOCATION"),
        ]

        self.inputs: Dict[str, QLineEdit] = {}
        for key, label in fields:
            layout.addWidget(QLabel(label))
            fld = QLineEdit()
            fld.setText(str(self._current_data.get(key, "")))
            layout.addWidget(fld)
            self.inputs[key] = fld

        layout.addSpacing(10)

        # Save
        submit_btn = QPushButton("💾  SAVE HEADER CHANGES")
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

        # Cancel
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
        return {key: fld.text().strip() for key, fld in self.inputs.items()}


# ════════════════════════════════════════════════════════════════
#  MAIN MATERIAL RECEIPT DIALOG
# ════════════════════════════════════════════════════════════════

class MaterialReceiptDialog(QDialog):
    """
    Ultra-premium Material Receiving & Inspection (MRIR) Dialog.
    Fully resizable, filterable, with enhanced UX.
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

    # Column indices (kept in one place for clarity)
    COL_TAG     = 0
    COL_CAT     = 1
    COL_DESC    = 2
    COL_SIZE    = 3
    COL_HEAT    = 4
    COL_MTC     = 5
    COL_QTY     = 6
    COL_UNIT    = 7
    COL_STATUS  = 8

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db

        # Drag / resize state
        self._drag_pos: Optional[QPoint] = None
        self._drag_edge: Optional[str] = None
        self._drag_geometry: Optional[QRect] = None
        self._resize_margin = 8

        # Lifecycle
        self._is_closed = False
        self._ts_timer: Optional[QTimer] = None

        # View state
        self._items: List[Dict[str, Any]] = []
        self._filtered_items: List[Dict[str, Any]] = []

        self.setWindowTitle("PipeAgent – Material Receipt & Inspection (MRIR)")
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
        self._apply_filters()

    # ── Data Init ─────────────────────────────────────────────
    def _init_data(self):
        self._header_info: Dict[str, str] = {
            "mrir_no": "MRIR-2025-0188",
            "po_no": "PO-9942-PIP-VAL",
            "vendor": "Vallourec Mannesmann Oil & Gas",
            "delivery_note": "DN-VM-88401-25",
            "date": _today_str(),
            "inspector": "QC Eng. Farhadi",
            "warehouse": "Main Site Laydown Yard • Bay 03",
        }

        self._items = [
            {
                "item_id": "I000000001",
                "tag": "ITM-01", "category": "Pipe",
                "desc": 'Pipe 12" Sch 40 BE Seamless Carbon Steel',
                "grade": "ASTM A106 Gr.B", "size": '12" Sch 40',
                "heat_no": "H-77402-A", "mtc_no": "MTC-VM-2025-901",
                "qty_recv": 48, "qty_acc": 48, "unit": "Meters",
                "status": "Accepted", "pmi": "Not Required (CS)",
                "location": "Yard Bay 03",
            },
            {
                "item_id": "I000000002",
                "tag": "ITM-02", "category": "Pipe",
                "desc": 'Pipe 8" Sch 40 BE Seamless Stainless Steel',
                "grade": "ASTM A312 TP316L", "size": '8" Sch 40',
                "heat_no": "K-88190-SS", "mtc_no": "MTC-SAN-8810",
                "qty_recv": 36, "qty_acc": 36, "unit": "Meters",
                "status": "Accepted", "pmi": "Yes - Passed",
                "location": "SS Clean Zone",
            },
            {
                "item_id": "I000000003",
                "tag": "ITM-03", "category": "Flange",
                "desc": 'Flange 12" WNRF Class 300 Serrated Finish',
                "grade": "ASTM A105N", "size": '12" Cl 300#',
                "heat_no": "FLG-4412-09", "mtc_no": "MTC-MET-2025-14",
                "qty_recv": 12, "qty_acc": 12, "unit": "PCS",
                "status": "Accepted", "pmi": "Not Required (CS)",
                "location": "Warehouse Rack A1",
            },
            {
                "item_id": "I000000004",
                "tag": "ITM-04", "category": "Fitting",
                "desc": '90 Deg LR Elbow 6" Sch 40 BW Seamless',
                "grade": "ASTM A234 WPB", "size": '6" Sch 40',
                "heat_no": "EB-99321", "mtc_no": "MISSING",
                "qty_recv": 20, "qty_acc": 0, "unit": "PCS",
                "status": "Pending MTC", "pmi": "Not Required (CS)",
                "location": "Quarantine Area",
            },
            {
                "item_id": "I000000005",
                "tag": "ITM-05", "category": "Valve",
                "desc": 'Ball Valve 2" Class 800 SW Forged A105 Trim 8',
                "grade": "ASTM A105", "size": '2" Cl 800#',
                "heat_no": "V-55102", "mtc_no": "MTC-BV-770",
                "qty_recv": 8, "qty_acc": 0, "unit": "PCS",
                "status": "Quarantined", "pmi": "Yes - Pending",
                "location": "Quarantine Area",
            },
            {
                "item_id": "I000000006",
                "tag": "ITM-06", "category": "Flange",
                "desc": 'Flange 8" Blind RF Class 150 (Face Scratched)',
                "grade": "ASTM A105N", "size": '8" Cl 150#',
                "heat_no": "BL-1029", "mtc_no": "MTC-MET-2025-19",
                "qty_recv": 4, "qty_acc": 0, "unit": "PCS",
                "status": "Rejected", "pmi": "Not Required (CS)",
                "location": "Reject Bin - Zone R",
            },
            {
                "item_id": "I000000007",
                "tag": "ITM-07", "category": "Gasket",
                "desc": 'Spiral Wound Gasket 6" Cl 300# SS316L + Graphite',
                "grade": "ASME B16.20", "size": '6" Cl 300#',
                "heat_no": "GS-77021", "mtc_no": "MTC-FLX-450",
                "qty_recv": 24, "qty_acc": 24, "unit": "PCS",
                "status": "Accepted", "pmi": "Not Required (CS)",
                "location": "Warehouse Rack B2",
            },
        ]

        self._filtered_items = list(self._items)

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
        card_layout.addWidget(self._build_header_frame())

        # ── KPI ribbon ────────────────────────────────────────
        stat_ribbon = QHBoxLayout()
        stat_ribbon.setSpacing(12)

        self.kpi_total = StatCard("TOTAL RECEIVED", "0", "📦", self.PRIMARY_LIGHT)
        self.kpi_acc   = StatCard("QC ACCEPTED", "0", "✅", self.SUCCESS)
        self.kpi_quar  = StatCard("QUARANTINE / PENDING", "0", "⏳", self.WARNING)
        self.kpi_rej   = StatCard("REJECTED / DAMAGED", "0", "🚫", self.ERROR)

        stat_ribbon.addWidget(self.kpi_total)
        stat_ribbon.addWidget(self.kpi_acc)
        stat_ribbon.addWidget(self.kpi_quar)
        stat_ribbon.addWidget(self.kpi_rej)

        card_layout.addLayout(stat_ribbon)
        card_layout.addLayout(self._build_filter_bar())

        # ── Splitter: Table + Inspector ──────────────────────
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setObjectName("mainSplitter")
        self._splitter.setHandleWidth(3)
        self._splitter.setChildrenCollapsible(False)

        self.table = self._build_table()
        self._splitter.addWidget(self.table)

        self.inspector_panel = self._build_inspector_panel()
        self._splitter.addWidget(self.inspector_panel)

        self._splitter.setSizes([870, 340])
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

        icon_lbl = QLabel("📦")
        icon_lbl.setFont(QFont("Segoe UI", 20))
        icon_lbl.setStyleSheet("background: transparent;")
        topbar.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)

        main_title = QLabel("PIPE AGENT  •  MATERIAL RECEIPT & INSPECTION (MRIR)")
        main_title.setObjectName("mainTitle")
        self._add_glow(main_title, QColor(108, 207, 246, 120), blur=20)
        title_col.addWidget(main_title)

        sub_title = QLabel(
            "HEAT / MTC VERIFICATION  •  POSITIVE MATERIAL IDENTIFICATION  •  SITE INTAKE"
        )
        sub_title.setObjectName("subTitle")
        title_col.addWidget(sub_title)
        topbar.addLayout(title_col)

        topbar.addStretch()

        self.btn_add_item = QPushButton("➕  ADD  (Ctrl+N)")
        self.btn_add_item.setObjectName("actionBtn")
        self.btn_add_item.setMinimumHeight(36)
        self.btn_add_item.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_item.setToolTip("Add a new material line item (Ctrl+N)")
        self.btn_add_item.clicked.connect(self._on_add_item)
        topbar.addWidget(self.btn_add_item)

        self.btn_attach_mtc = QPushButton("📑  ATTACH MTC")
        self.btn_attach_mtc.setObjectName("secondaryBtn")
        self.btn_attach_mtc.setMinimumHeight(36)
        self.btn_attach_mtc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_attach_mtc.setToolTip("Attach Mill Test Certificate to selected item")
        self.btn_attach_mtc.clicked.connect(self._on_attach_mtc)
        topbar.addWidget(self.btn_attach_mtc)

        self.btn_export_mrir = QPushButton("🖨  EXPORT  (Ctrl+E)")
        self.btn_export_mrir.setObjectName("secondaryBtn")
        self.btn_export_mrir.setMinimumHeight(36)
        self.btn_export_mrir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_mrir.setToolTip("Export MRIR register to CSV (Ctrl+E)")
        self.btn_export_mrir.clicked.connect(self._on_export_csv)
        topbar.addWidget(self.btn_export_mrir)

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
        self.header_frame.setToolTip("Double-click to edit MRIR header info")

        h_layout = QHBoxLayout(self.header_frame)
        h_layout.setContentsMargins(14, 8, 14, 8)
        h_layout.setSpacing(16)

        self.lbl_mrir_no = QLabel()
        self.lbl_po_no   = QLabel()
        self.lbl_vendor  = QLabel()
        self.lbl_date    = QLabel()
        self.lbl_wh      = QLabel()

        for lbl in [self.lbl_mrir_no, self.lbl_po_no, self.lbl_vendor,
                     self.lbl_date, self.lbl_wh]:
            lbl.setStyleSheet(
                "color: #7a9ab3; font-size: 11px; background: transparent;"
            )
            h_layout.addWidget(lbl)

        self.btn_edit_hdr = QPushButton("✏  EDIT")
        self.btn_edit_hdr.setObjectName("editHdrBtn")
        self.btn_edit_hdr.setFixedHeight(24)
        self.btn_edit_hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit_hdr.setToolTip("Edit MRIR header information")
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

        # Double-click anywhere on the frame → edit header
        self.header_frame.mouseDoubleClickEvent = (
            lambda e: self._on_edit_header()
        )

        self._refresh_header_display()
        return self.header_frame

    def _build_filter_bar(self) -> QHBoxLayout:
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText(
            "🔍  Search by Tag, Heat No, Description, MTC, Grade...  (Ctrl+F)"
        )
        self.search_input.setObjectName("searchInput")
        self.search_input.textChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.search_input, 3)

        self.combo_category = QComboBox()
        self.combo_category.setObjectName("filterCombo")
        self.combo_category.setMinimumHeight(38)
        self.combo_category.addItems([
            "All Categories", "Pipe", "Flange", "Fitting",
            "Valve", "Gasket", "Stud",
        ])
        self.combo_category.currentTextChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.combo_category, 1)

        self.combo_status = QComboBox()
        self.combo_status.setObjectName("filterCombo")
        self.combo_status.setMinimumHeight(38)
        self.combo_status.addItems([
            "All Statuses", "Accepted", "Quarantined",
            "Pending MTC", "Rejected",
        ])
        self.combo_status.currentTextChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.combo_status, 1)

        self.chk_export_filtered = QCheckBox("Export Filtered")
        self.chk_export_filtered.setChecked(True)
        self.chk_export_filtered.setToolTip(
            "When checked, only rows matching the current filters are exported"
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
        filter_bar.addWidget(self.chk_export_filtered)

        btn_reset = QPushButton("↺  RESET")
        btn_reset.setObjectName("secondaryBtn")
        btn_reset.setMinimumHeight(38)
        btn_reset.setToolTip("Reset all filters")
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.clicked.connect(self._reset_filters)
        filter_bar.addWidget(btn_reset)

        return filter_bar

    def _build_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setObjectName("itemTable")
        table.setColumnCount(9)
        table.setHorizontalHeaderLabels([
            "Item", "Category", "Description & Grade", "Size/Rating",
            "Heat / Cast No", "MTC Number", "Qty", "Unit", "QC Status",
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

        default_widths = [70, 90, 320, 100, 130, 150, 60, 70, 130]
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
        table.doubleClicked.connect(self._on_attach_mtc)

        return table

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

        head_lbl = QLabel("🔍   HEAT & QC CLEARANCE INSPECTOR")
        head_lbl.setObjectName("inspHead")
        layout.addWidget(head_lbl)

        div = QFrame()
        div.setObjectName("divider")
        div.setFixedHeight(1)
        layout.addWidget(div)

        self.insp_heat = QLabel("Select an Item")
        self.insp_heat.setObjectName("inspHeat")
        self.insp_heat.setWordWrap(True)
        layout.addWidget(self.insp_heat)

        self.insp_desc = QLabel(
            "Select a component from the table to review inspection checklist, "
            "PMI and MTC certificate."
        )
        self.insp_desc.setObjectName("inspDesc")
        self.insp_desc.setWordWrap(True)
        layout.addWidget(self.insp_desc)

        self.meta_frame = QFrame()
        self.meta_frame.setObjectName("metaFrame")
        m_layout = QVBoxLayout(self.meta_frame)
        m_layout.setContentsMargins(10, 8, 10, 8)
        m_layout.setSpacing(5)

        self.m_grade = QLabel()
        self.m_size  = QLabel()
        self.m_mtc   = QLabel()
        self.m_pmi   = QLabel()
        self.m_loc   = QLabel()
        self.m_qty   = QLabel()

        # Declarative spec used for both population and reset.
        self._meta_specs = [
            (self.m_grade, "Grade"),
            (self.m_size,  "Size / Sch"),
            (self.m_mtc,   "MTC #"),
            (self.m_pmi,   "PMI Status"),
            (self.m_loc,   "Location"),
            (self.m_qty,   "Qty Status"),
        ]

        for lbl, _ in self._meta_specs:
            lbl.setStyleSheet(
                "color: #dfeaf5; font-size: 11px; background: transparent;"
            )
            lbl.setWordWrap(True)
            m_layout.addWidget(lbl)

        layout.addWidget(self.meta_frame)

        qc_lbl = QLabel("⚡   SET QC INSPECTION DECISION:")
        qc_lbl.setStyleSheet(
            "color: #9fe7ff; font-size: 9px; font-weight: 800; "
            "letter-spacing: 1px; margin-top: 4px; background: transparent;"
        )
        layout.addWidget(qc_lbl)

        btn_row1 = QHBoxLayout()
        self.btn_qc_accept = QPushButton("✅  ACCEPT")
        self.btn_qc_accept.setObjectName("btnAccept")
        self.btn_qc_accept.setMinimumHeight(34)
        self.btn_qc_accept.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_qc_accept.setEnabled(False)
        self.btn_qc_accept.clicked.connect(
            lambda: self._set_selected_qc("Accepted")
        )
        btn_row1.addWidget(self.btn_qc_accept)

        self.btn_qc_hold = QPushButton("⏳  QUARANTINE")
        self.btn_qc_hold.setObjectName("btnHold")
        self.btn_qc_hold.setMinimumHeight(34)
        self.btn_qc_hold.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_qc_hold.setEnabled(False)
        self.btn_qc_hold.clicked.connect(
            lambda: self._set_selected_qc("Quarantined")
        )
        btn_row1.addWidget(self.btn_qc_hold)
        layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        self.btn_qc_mtc = QPushButton("📑  HOLD FOR MTC")
        self.btn_qc_mtc.setObjectName("secondaryBtn")
        self.btn_qc_mtc.setMinimumHeight(32)
        self.btn_qc_mtc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_qc_mtc.setEnabled(False)
        self.btn_qc_mtc.clicked.connect(
            lambda: self._set_selected_qc("Pending MTC")
        )
        btn_row2.addWidget(self.btn_qc_mtc)

        self.btn_qc_reject = QPushButton("🚫  REJECT")
        self.btn_qc_reject.setObjectName("btnReject")
        self.btn_qc_reject.setMinimumHeight(32)
        self.btn_qc_reject.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_qc_reject.setEnabled(False)
        self.btn_qc_reject.clicked.connect(
            lambda: self._set_selected_qc("Rejected")
        )
        btn_row2.addWidget(self.btn_qc_reject)
        layout.addLayout(btn_row2)

        layout.addStretch()

        self.btn_remove = QPushButton("🗑  REMOVE LINE ITEM")
        self.btn_remove.setObjectName("btnDelete")
        self.btn_remove.setMinimumHeight(32)
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.setEnabled(False)
        self.btn_remove.clicked.connect(self._on_remove_item)
        layout.addWidget(self.btn_remove)

        scroll.setWidget(inner)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(scroll)
        return panel

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 2, 4, 0)

        self.lbl_count = QLabel("Total 0 components")
        self.lbl_count.setObjectName("footerLabel")
        footer.addWidget(self.lbl_count)

        footer.addStretch()

        self.lbl_timestamp = QLabel("")
        self.lbl_timestamp.setObjectName("footerLabel")
        footer.addWidget(self.lbl_timestamp)

        footer.addStretch()

        foot_tag = QLabel(
            "⚡  PipeAgent 5.0  •  Material Receiving Inspection & Heat Control"
        )
        foot_tag.setStyleSheet(
            "color: #3f6070; font-size: 10px; letter-spacing: 1px; background: transparent;"
        )
        footer.addWidget(foot_tag)
        return footer

    # ── Keyboard Shortcuts ────────────────────────────────────
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self, self._on_add_item)
        QShortcut(QKeySequence("Ctrl+E"), self, self._on_export_csv)
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        QShortcut(QKeySequence("F5"),     self, self._apply_filters)

        # Delete is bound to the table only → typing Delete inside the
        # search field no longer removes a material line item.
        del_sc = QShortcut(QKeySequence("Delete"), self.table, self._on_remove_item)
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
                border: 1px solid #1e3d5a; border-radius: 6px; padding: 4px;
            }
            QMenu::item { padding: 8px 24px 8px 12px; border-radius: 4px; }
            QMenu::item:selected { background: #14334f; color: #9fe7ff; }
            QMenu::item:disabled { color: #3a5060; }
            QMenu::separator { height: 1px; background: #1e3d5a; margin: 4px 8px; }
        """)

        selected = self._get_selected_item()

        act_accept = menu.addAction("✅  Accept")
        act_accept.setEnabled(selected is not None)
        act_accept.triggered.connect(lambda: self._set_selected_qc("Accepted"))

        act_hold = menu.addAction("⏳  Quarantine")
        act_hold.setEnabled(selected is not None)
        act_hold.triggered.connect(lambda: self._set_selected_qc("Quarantined"))

        act_mtc = menu.addAction("📑  Hold for MTC")
        act_mtc.setEnabled(selected is not None)
        act_mtc.triggered.connect(lambda: self._set_selected_qc("Pending MTC"))

        act_rej = menu.addAction("🚫  Reject")
        act_rej.setEnabled(selected is not None)
        act_rej.triggered.connect(lambda: self._set_selected_qc("Rejected"))

        menu.addSeparator()

        act_attach = menu.addAction("📑  Attach MTC file...")
        act_attach.setEnabled(selected is not None)
        act_attach.triggered.connect(self._on_attach_mtc)

        act_new = menu.addAction("➕  Add New Item  (Ctrl+N)")
        act_new.triggered.connect(self._on_add_item)

        menu.addSeparator()

        act_delete = menu.addAction("🗑  Remove Item")
        act_delete.setEnabled(selected is not None)
        act_delete.triggered.connect(self._on_remove_item)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ── Header Display ────────────────────────────────────────
    def _refresh_header_display(self):
        info = self._header_info
        self.lbl_mrir_no.setText(
            f"<b>MRIR NO:</b> <span style='color:#9fe7ff;'>{info['mrir_no']}</span>"
        )
        self.lbl_po_no.setText(
            f"<b>PO NO:</b> <span style='color:#9fe7ff;'>{info['po_no']}</span>"
        )
        self.lbl_vendor.setText(
            f"<b>VENDOR:</b> <span style='color:#eef6ff;'>{info['vendor']}</span>"
        )
        self.lbl_date.setText(
            f"<b>DATE:</b> <span style='color:#7a9ab3;'>{info['date']}</span>"
        )
        self.lbl_wh.setText(
            f"<b>LOCATION:</b> <span style='color:#7a9ab3;'>{info['warehouse']}</span>"
        )

    def _on_edit_header(self):
        modal = EditHeaderDialog(self._header_info, self)
        if modal.exec() == QDialog.DialogCode.Accepted:
            self._header_info.update(modal.get_data())
            self._refresh_header_display()
            QMessageBox.information(
                self, "✅ Header Updated",
                "MRIR header information has been updated successfully.",
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
            QLineEdit#searchInput {{
                background: {self.BG_INPUT};
                color: {self.TEXT_MAIN};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QLineEdit#searchInput:focus {{ border: 1px solid {self.PRIMARY}; }}
            QComboBox#filterCombo {{
                background: {self.BG_INPUT};
                color: {self.TEXT_MAIN};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 4px 12px;
                font-size: 12px;
            }}
            QComboBox#filterCombo:hover {{ border: 1px solid {self.PRIMARY}; }}
            QComboBox#filterCombo QAbstractItemView {{
                background: #07101a;
                color: {self.TEXT_MAIN};
                selection-background-color: #14334f;
                selection-color: {self.PRIMARY_LIGHT};
                border: 1px solid #1e3d5a;
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
            QTableWidget#itemTable {{
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
            QTableWidget#itemTable::item {{
                padding: 7px 9px;
                border-bottom: 1px solid #0c1f30;
            }}
            QTableWidget#itemTable::item:selected {{
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
            QLabel#inspHeat {{
                color: {self.ACCENT};
                font-size: 14px;
                font-weight: 800;
                background: transparent;
                font-family: Consolas, monospace;
            }}
            QLabel#inspDesc {{
                color: {self.TEXT_MUTED};
                font-size: 11px;
                background: transparent;
            }}
            QFrame#metaFrame {{
                background: #06101c;
                border: 1px solid #10263b;
                border-radius: 8px;
            }}
            QPushButton#btnAccept {{
                background: #0b3320;
                color: {self.SUCCESS};
                border: 1px solid #1c6640;
                border-radius: 6px;
                font-weight: 700;
                font-size: 11px;
            }}
            QPushButton#btnAccept:hover {{ background: #135233; }}
            QPushButton#btnAccept:disabled {{
                background: #0a1a12; color: #2a5a40;
                border: 1px solid #123322;
            }}
            QPushButton#btnHold {{
                background: #33280b;
                color: {self.WARNING};
                border: 1px solid #66501c;
                border-radius: 6px;
                font-weight: 700;
                font-size: 11px;
            }}
            QPushButton#btnHold:hover {{ background: #4d3d12; }}
            QPushButton#btnHold:disabled {{
                background: #1a1408; color: #5a4c1e;
                border: 1px solid #332810;
            }}
            QPushButton#btnReject {{
                background: #330b0b;
                color: {self.ERROR};
                border: 1px solid #661c1c;
                border-radius: 6px;
                font-weight: 700;
                font-size: 11px;
            }}
            QPushButton#btnReject:hover {{ background: #521313; }}
            QPushButton#btnReject:disabled {{
                background: #1a0808; color: #5a2828;
                border: 1px solid #331010;
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

    # ── Helper utilities ──────────────────────────────────────
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

    def _get_selected_item(self) -> Optional[Dict[str, Any]]:
        """
        Return the item dict stored on the selected row.

        The item is attached to the first column's UserRole, so the result
        is correct even after the user re-sorts the table.
        """
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), self.COL_TAG)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _find_item_index(self, item_id: str) -> int:
        """Locate an item in `self._items` by stable item_id. Returns -1 if missing."""
        for idx, itm in enumerate(self._items):
            if itm.get("item_id") == item_id:
                return idx
        return -1

    def _reselect_by_item_id(self, item_id: str):
        """Attempt to re-select a row after a filter / status change."""
        for row_idx, filt in enumerate(self._filtered_items):
            if filt.get("item_id") == item_id:
                self.table.selectRow(row_idx)
                return

    # ── Frameless drag & resize ───────────────────────────────
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

    # ── Filtering ─────────────────────────────────────────────
    def _apply_filters(self):
        search = self.search_input.text().strip().lower()
        selected_cat = self.combo_category.currentText()
        selected_status = self.combo_status.currentText()

        filtered = []
        for itm in self._items:
            if search:
                haystack = " ".join([
                    itm["tag"],
                    itm["heat_no"],
                    itm["desc"],
                    itm.get("mtc_no", ""),
                    itm.get("grade", ""),
                    itm.get("category", ""),
                ]).lower()
                if search not in haystack:
                    continue

            if selected_cat != "All Categories" and itm["category"] != selected_cat:
                continue

            if selected_status != "All Statuses" and itm["status"] != selected_status:
                continue

            filtered.append(itm)

        self._filtered_items = filtered
        self._populate_table()
        self._update_kpi()

    def _reset_filters(self):
        # Block signals so we only refilter once.
        for w in (self.search_input, self.combo_category, self.combo_status):
            w.blockSignals(True)
        try:
            self.search_input.clear()
            self.combo_category.setCurrentIndex(0)
            self.combo_status.setCurrentIndex(0)
        finally:
            for w in (self.search_input, self.combo_category, self.combo_status):
                w.blockSignals(False)
        self._apply_filters()

    # ── Populate Table ────────────────────────────────────────
    def _populate_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for row_idx, itm in enumerate(self._filtered_items):
            self.table.insertRow(row_idx)

            # Col 0: Tag (also carries the full item via UserRole)
            item_tag = QTableWidgetItem(itm["tag"])
            item_tag.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            item_tag.setForeground(QColor(self.PRIMARY_LIGHT))
            item_tag.setData(Qt.ItemDataRole.UserRole, itm)  # ← sort-safe link
            self.table.setItem(row_idx, self.COL_TAG, item_tag)

            # Col 1: Category
            item_cat = QTableWidgetItem(itm["category"])
            item_cat.setForeground(QColor("#a2c2dc"))
            self.table.setItem(row_idx, self.COL_CAT, item_cat)

            # Col 2: Description
            desc_text = f"{itm['desc']} ({itm['grade']})"
            item_desc = QTableWidgetItem(desc_text)
            item_desc.setForeground(QColor(self.TEXT_MAIN))
            item_desc.setToolTip(desc_text)
            self.table.setItem(row_idx, self.COL_DESC, item_desc)

            # Col 3: Size
            item_size = QTableWidgetItem(itm["size"])
            item_size.setForeground(QColor(self.TEXT_MUTED))
            self.table.setItem(row_idx, self.COL_SIZE, item_size)

            # Col 4: Heat No
            item_heat = QTableWidgetItem(itm["heat_no"])
            item_heat.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            item_heat.setForeground(QColor(self.ACCENT))
            item_heat.setToolTip(f"Heat / Cast Number: {itm['heat_no']}")
            self.table.setItem(row_idx, self.COL_HEAT, item_heat)

            # Col 5: MTC
            item_mtc = QTableWidgetItem(itm["mtc_no"])
            item_mtc.setFont(QFont("Consolas", 10))
            if itm["mtc_no"] == "MISSING":
                item_mtc.setForeground(QColor(self.ERROR))
                item_mtc.setToolTip("⚠ MTC certificate not received yet")
            else:
                item_mtc.setForeground(QColor("#708fa8"))
                item_mtc.setToolTip(f"MTC Certificate: {itm['mtc_no']}")
            self.table.setItem(row_idx, self.COL_MTC, item_mtc)

            # Col 6: Qty
            item_qty = QTableWidgetItem(str(itm["qty_recv"]))
            item_qty.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_qty.setForeground(QColor(self.TEXT_MAIN))
            item_qty.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            self.table.setItem(row_idx, self.COL_QTY, item_qty)

            # Col 7: Unit
            item_unit = QTableWidgetItem(itm["unit"])
            item_unit.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_unit.setForeground(QColor(self.TEXT_MUTED))
            self.table.setItem(row_idx, self.COL_UNIT, item_unit)

            # Col 8: Status
            item_stat = QTableWidgetItem(f" ● {itm['status']} ")
            item_stat.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item_stat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_stat.setForeground(QColor(self._status_color(itm["status"])))
            self.table.setItem(row_idx, self.COL_STATUS, item_stat)

        self.table.setSortingEnabled(True)

        total = len(self._items)
        shown = len(self._filtered_items)
        if shown == total:
            self.lbl_count.setText(f"Total {total} components in this delivery")
        else:
            self.lbl_count.setText(
                f"Showing {shown} of {total} components (filtered)"
            )

        if self._filtered_items:
            self.table.selectRow(0)
        else:
            self._clear_inspector()

    def _status_color(self, status: str) -> str:
        s = (status or "").upper()
        if "ACCEPTED" in s:
            return self.SUCCESS
        if "QUARANTINE" in s:
            return self.WARNING
        if "PENDING" in s:
            return self.INFO
        if "REJECTED" in s:
            return self.ERROR
        return "#8faec5"

    def _update_kpi(self):
        total = len(self._items)
        acc = sum(1 for d in self._items if d["status"].upper() == "ACCEPTED")
        quar = sum(
            1 for d in self._items
            if d["status"].upper() in ("QUARANTINED", "PENDING MTC")
        )
        rej = sum(1 for d in self._items if d["status"].upper() == "REJECTED")

        self.kpi_total.update_value(str(total))
        self.kpi_acc.update_value(str(acc))
        self.kpi_quar.update_value(str(quar))
        self.kpi_rej.update_value(str(rej))

    # ── Table Selection → Inspector ───────────────────────────
    def _on_table_selection(self):
        itm = self._get_selected_item()
        if itm is None:
            self._clear_inspector()
            return

        self.insp_heat.setText(f"HEAT: {itm['heat_no']}")
        self.insp_desc.setText(itm["desc"])

        self.m_grade.setText(f"<b>Grade:</b> {itm['grade']}")
        self.m_size.setText(f"<b>Size / Rating:</b> {itm['size']}")
        self.m_mtc.setText(f"<b>MTC Certificate:</b> {itm['mtc_no']}")

        pmi = itm.get("pmi", "N/A")
        pmi_color = (
            self.SUCCESS if "Passed" in pmi
            else self.WARNING if "Pending" in pmi
            else self.TEXT_MUTED
        )
        self.m_pmi.setText(
            f"<b>PMI Examination:</b> <span style='color:{pmi_color}'>{pmi}</span>"
        )

        self.m_loc.setText(
            f"<b>Storage Location:</b> {itm.get('location', 'Laydown')}"
        )
        self.m_qty.setText(
            f"<b>Quantity:</b> {itm['qty_recv']} {itm['unit']} "
            f"(Accepted: {itm['qty_acc']})"
        )

        self.btn_qc_accept.setEnabled(True)
        self.btn_qc_hold.setEnabled(True)
        self.btn_qc_mtc.setEnabled(True)
        self.btn_qc_reject.setEnabled(True)
        self.btn_remove.setEnabled(True)

    def _clear_inspector(self):
        self.insp_heat.setText("No Item Selected")
        self.insp_desc.setText(
            "Select a component from the table to review inspection checklist, "
            "PMI and MTC certificate."
        )
        # Reset driven by the declared spec — no string parsing.
        for lbl, title in self._meta_specs:
            lbl.setText(f"<b>{title}:</b> —")

        self.btn_qc_accept.setEnabled(False)
        self.btn_qc_hold.setEnabled(False)
        self.btn_qc_mtc.setEnabled(False)
        self.btn_qc_reject.setEnabled(False)
        self.btn_remove.setEnabled(False)

    # ── QC Actions ────────────────────────────────────────────
    def _set_selected_qc(self, new_status: str):
        itm = self._get_selected_item()
        if itm is None:
            QMessageBox.warning(
                self, "Selection Required",
                "Please select a material row to update QC status.",
            )
            return

        idx = self._find_item_index(itm.get("item_id", ""))
        if idx < 0:
            QMessageBox.warning(
                self, "Item Not Found",
                "The selected item could no longer be located.",
            )
            return

        self._items[idx]["status"] = new_status
        if new_status == "Accepted":
            self._items[idx]["qty_acc"] = self._items[idx]["qty_recv"]
        else:
            self._items[idx]["qty_acc"] = 0

        target_id = self._items[idx].get("item_id", "")
        self._apply_filters()
        self._reselect_by_item_id(target_id)

    # ── Add / Remove Items ────────────────────────────────────
    def _on_add_item(self):
        existing_heats = [itm["heat_no"] for itm in self._items]
        modal = AddMaterialItemDialog(existing_heats=existing_heats, parent=self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return

        new_item = modal.get_data()
        if not new_item["tag"]:
            new_item["tag"] = f"ITM-{len(self._items) + 1:02d}"

        self._items.append(new_item)
        self._apply_filters()

        QMessageBox.information(
            self, "✅ Item Added",
            f"Item <b>{new_item['tag']}</b> with Heat "
            f"<b>{new_item['heat_no']}</b> added to MRIR.",
        )

    def _on_remove_item(self):
        itm = self._get_selected_item()
        if itm is None:
            return

        reply = QMessageBox.warning(
            self, "⚠ Confirm Delete",
            f"Are you sure you want to remove:\n\n"
            f"<b>{itm['tag']}</b> — Heat: <b>{itm['heat_no']}</b>\n"
            f"{itm['desc']}\n\n"
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        idx = self._find_item_index(itm.get("item_id", ""))
        if idx < 0:
            return
        self._items.pop(idx)
        self._apply_filters()

    # ── MTC Attachment ────────────────────────────────────────
    def _on_attach_mtc(self):
        itm = self._get_selected_item()
        if itm is None:
            QMessageBox.warning(
                self, "Selection Required",
                "Please select an item to link an MTC certificate.",
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Attach Mill Test Certificate",
            "", "PDF Files (*.pdf);;All Files (*.*)",
        )
        if not path:
            return

        filename = os.path.basename(path)
        base = os.path.splitext(filename)[0]

        idx = self._find_item_index(itm.get("item_id", ""))
        if idx < 0:
            return

        self._items[idx]["mtc_no"] = f"MTC-{base[:20]}"
        if self._items[idx]["status"] == "Pending MTC":
            self._items[idx]["status"] = "Accepted"
            self._items[idx]["qty_acc"] = self._items[idx]["qty_recv"]

        target_id = self._items[idx].get("item_id", "")
        self._apply_filters()
        self._reselect_by_item_id(target_id)

        QMessageBox.information(
            self, "✅ MTC Linked",
            f"Mill Certificate <b>{filename}</b> successfully linked to "
            f"Heat #<b>{itm['heat_no']}</b>.",
        )

    # ── Export CSV ────────────────────────────────────────────
    def _on_export_csv(self):
        if self.chk_export_filtered.isChecked():
            export_items = self._filtered_items
            label = "filtered"
        else:
            export_items = self._items
            label = "all"

        if not export_items:
            QMessageBox.warning(
                self, "No Data",
                "No items to export. Adjust your filters.",
            )
            return

        default_name = (
            f"MRIR_{self._header_info['mrir_no']}_"
            f"{datetime.today().strftime('%Y%m%d')}.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export MRIR Material Receiving Report",
            default_name, "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["═══ MRIR HEADER ═══"])
                writer.writerow(["MRIR Number", self._header_info["mrir_no"]])
                writer.writerow(["Purchase Order", self._header_info["po_no"]])
                writer.writerow(["Vendor", self._header_info["vendor"]])
                writer.writerow(["Delivery Note", self._header_info["delivery_note"]])
                writer.writerow(["Date", self._header_info["date"]])
                writer.writerow(["Inspector", self._header_info["inspector"]])
                writer.writerow(["Warehouse", self._header_info["warehouse"]])
                writer.writerow([])
                writer.writerow(["═══ LINE ITEMS ═══"])
                writer.writerow([
                    "Item Tag", "Category", "Description", "Grade",
                    "Size/Rating", "Heat Number", "MTC Number",
                    "Qty Received", "Qty Accepted", "Unit",
                    "Status", "PMI", "Location",
                ])
                for itm in export_items:
                    writer.writerow([
                        itm["tag"], itm["category"], itm["desc"],
                        itm["grade"], itm["size"], itm["heat_no"],
                        itm["mtc_no"], itm["qty_recv"], itm["qty_acc"],
                        itm["unit"], itm["status"],
                        itm.get("pmi", ""), itm.get("location", ""),
                    ])

            QMessageBox.information(
                self, "✅ Export Complete",
                f"MRIR Report ({len(export_items)} {label} items) exported to:\n\n{path}",
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
                f"Could not export report:\n\n{e}",
            )

    # ── Graceful close ────────────────────────────────────────
    def _cleanup(self):
        """Stop every timer and animation we own. Safe to call twice."""
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


# ════════════════════════════════════════════════════════════════
#  STANDALONE TEST RUNNER
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    dialog = MaterialReceiptDialog()
    dialog.show()
    dialog.exec()

    sys.exit(0)