# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium NDT Examination & Quality Control Dialog
═══════════════════════════════════════════════════════════════════
Version : 5.0 (Refactored, hardened, production-ready)
Engine  : PyQt6
Design  : Cinematic dark-tech theme matching PipeAgent Suite

Fixes in this revision
──────────────────────
🔴 P0  Duplicate-joint check : fixed NameError from `[j.upper() for h in ...]`
                             and switched the resulting collection to a set
                             (O(1) lookup on every keystroke)
🔴 P0  Card border           : replaced invalid `border: ... qlineargradient`
                             with a solid color + drop shadow
🔴 P0  GlowLineEdit          : no longer calls deleteLater() on an animation
                             that Qt owns (DeleteWhenStopped)
🔴 P0  Sort-safe selection   : each row stores its record dict on
                             QTableWidgetItem.UserRole
🔴 P0  Stable record ids     : every record has a `record_id`; lookups use
                             that id instead of `list.index(dict)`
🟠 P1  Delete shortcut       : bound to the table only (WidgetShortcut)
🟠 P1  done() override       : single cleanup path for accept/reject/
                             Escape/X
🟠 P1  Particle geometry     : set immediately after creation
🟡 P2  _clear_inspector      : driven by a declared label spec
🟡 P2  ParticleField         : count 30 → 16, tick 60ms → 100ms, paints
                             only when visible
🟡 P2  Penalty tracers       : selection follows the last inserted tracer
🟢 P3  Tooltips               : on every topbar button
🟢 P3  _today() helper        : single source for the current date string
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
    QFileDialog, QSpinBox, QDoubleSpinBox, QMenu, QScrollArea,
    QCheckBox,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#  UTILITIES
# ════════════════════════════════════════════════════════════════

def _new_record_id() -> str:
    """Short, collision-resistant record identifier."""
    return "N" + uuid.uuid4().hex[:9].upper()


def _today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


# ════════════════════════════════════════════════════════════════
#  PARTICLE FIELD
# ════════════════════════════════════════════════════════════════

class ParticleField(QWidget):
    """Subtle floating particle background — optimized."""

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
#  ADD NDT RECORD SUB-MODAL
# ════════════════════════════════════════════════════════════════

class AddNDTRecordDialog(QDialog):
    """Sub-modal for registering an NDT joint examination entry."""

    def __init__(
        self,
        existing_joints: Optional[Iterable[str]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Register NDT Examination")
        self.setMinimumSize(540, 620)
        self.setMaximumSize(700, 780)
        self.resize(540, 640)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos: Optional[QPoint] = None

        # 🔧 FIX: was `[j.upper() for h in (...)]` → NameError.
        #    Also switched to a set for O(1) membership testing.
        self._existing_joints = {
            str(j).upper() for j in (existing_joints or [])
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

        # Header
        head = QHBoxLayout()
        title = QLabel("🔬   LOG NDT JOINT INSPECTION")
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

        # Row 1: Joint & Line / ISO
        row1 = QHBoxLayout()
        col_joint = QVBoxLayout()
        col_joint.addWidget(QLabel("JOINT NUMBER / WELD ID *"))
        self.in_joint = QLineEdit()
        self.in_joint.setPlaceholderText("e.g. W-14 / J-08")
        self.in_joint.setToolTip("Unique joint / weld identifier — required")
        col_joint.addWidget(self.in_joint)
        row1.addLayout(col_joint)

        col_iso = QVBoxLayout()
        col_iso.addWidget(QLabel("ISO DRAWING / LINE NUMBER"))
        self.in_iso = QLineEdit()
        self.in_iso.setPlaceholderText("e.g. ISO-01-PR-2104-001")
        self.in_iso.setToolTip("Related isometric drawing identifier")
        col_iso.addWidget(self.in_iso)
        row1.addLayout(col_iso)
        layout.addLayout(row1)

        # Row 2: NDT Method & Welder Stamp
        row2 = QHBoxLayout()
        col_method = QVBoxLayout()
        col_method.addWidget(QLabel("NDT METHOD"))
        self.in_method = QComboBox()
        self.in_method.addItems([
            "RT (Radiographic Testing)",
            "UT (Ultrasonic Testing)",
            "PAUT (Phased Array UT)",
            "MT / MPI (Magnetic Particle)",
            "PT / DPI (Liquid Penetrant)",
            "PMI (Material Identification)",
            "HT (Hardness Testing)",
            "VT (Visual Testing)",
        ])
        col_method.addWidget(self.in_method)
        row2.addLayout(col_method)

        col_welder = QVBoxLayout()
        col_welder.addWidget(QLabel("WELDER STAMP / ID *"))
        self.in_welder = QLineEdit()
        self.in_welder.setPlaceholderText("e.g. W-04 / W-12")
        self.in_welder.setToolTip("Welder stamp — required for traceability")
        col_welder.addWidget(self.in_welder)
        row2.addLayout(col_welder)
        layout.addLayout(row2)

        self.lbl_dup_warn = QLabel(
            "⚠ This Joint Number has already been registered!"
        )
        self.lbl_dup_warn.setStyleSheet(
            "color: #ff9f43; font-size: 10px; font-weight: 700; background: transparent;"
        )
        self.lbl_dup_warn.setVisible(False)
        layout.addWidget(self.lbl_dup_warn)
        self.in_joint.textChanged.connect(self._check_duplicate_joint)

        # Row 3: Size, Thickness & Process
        row3 = QHBoxLayout()
        col_size = QVBoxLayout()
        col_size.addWidget(QLabel("NOMINAL SIZE (NPS)"))
        self.in_size = QLineEdit()
        self.in_size.setPlaceholderText('e.g. 12" Sch 40')
        col_size.addWidget(self.in_size)
        row3.addLayout(col_size)

        col_thk = QVBoxLayout()
        col_thk.addWidget(QLabel("THICKNESS (mm)"))
        self.in_thk = QDoubleSpinBox()
        self.in_thk.setRange(0.1, 150.0)
        self.in_thk.setValue(9.53)
        self.in_thk.setSingleStep(0.5)
        col_thk.addWidget(self.in_thk)
        row3.addLayout(col_thk)

        col_proc = QVBoxLayout()
        col_proc.addWidget(QLabel("WELD PROCESS"))
        self.in_proc = QComboBox()
        self.in_proc.addItems(["GTAW + SMAW", "GTAW", "SMAW", "GMAW / FCAW", "SAW"])
        col_proc.addWidget(self.in_proc)
        row3.addLayout(col_proc)
        layout.addLayout(row3)

        # Row 4: Film / Scan ID & Report No
        row4 = QHBoxLayout()
        col_film = QVBoxLayout()
        col_film.addWidget(QLabel("FILM / SCAN REF / READER ID"))
        self.in_film = QLineEdit()
        self.in_film.setPlaceholderText("e.g. F-2025-088-A")
        col_film.addWidget(self.in_film)
        row4.addLayout(col_film)

        col_rep = QVBoxLayout()
        col_rep.addWidget(QLabel("REPORT NUMBER"))
        self.in_rep = QLineEdit()
        self.in_rep.setPlaceholderText("e.g. NDT-RT-2025-088")
        col_rep.addWidget(self.in_rep)
        row4.addLayout(col_rep)
        layout.addLayout(row4)

        # Row 5: Defect & Evaluation
        row5 = QHBoxLayout()
        col_def = QVBoxLayout()
        col_def.addWidget(QLabel("DEFECT / DISCONTINUITY TYPE"))
        self.in_defect = QComboBox()
        self.in_defect.setEditable(True)
        self.in_defect.addItems([
            "Nil (No Discontinuity)",
            "Porosity (P)",
            "Lack of Fusion (LF)",
            "Lack of Penetration (LOP)",
            "Slag Inclusion (SI)",
            "Tungsten Inclusion (TI)",
            "Internal Undercut (IUC)",
            "Root Concavity (RC)",
            "Crack (CRK)",
        ])
        col_def.addWidget(self.in_defect)
        row5.addLayout(col_def)

        col_eval = QVBoxLayout()
        col_eval.addWidget(QLabel("EVALUATION RESULT"))
        self.in_eval = QComboBox()
        self.in_eval.addItems([
            "ACCEPTED (ACC)",
            "REPAIR REQUIRED (REJ)",
            "RE-EXAM / RESHOOT (RST)",
        ])
        col_eval.addWidget(self.in_eval)
        row5.addLayout(col_eval)
        layout.addLayout(row5)

        layout.addSpacing(10)

        submit_btn = QPushButton("⚡  SUBMIT NDT EXAMINATION")
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
                "Joint Number / Weld ID is required."
            )
            self.in_joint.setFocus()
            return

        if not self.in_welder.text().strip():
            QMessageBox.warning(
                self, "Validation Error",
                "Welder ID is required for performance traceability."
            )
            self.in_welder.setFocus()
            return

        if joint.upper() in self._existing_joints:
            reply = QMessageBox.question(
                self, "Duplicate Joint ID",
                f"Joint <b>{joint}</b> already has an NDT record logged.\n\n"
                "Do you still want to register this entry?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.accept()

    def get_data(self) -> Dict[str, Any]:
        eval_text = self.in_eval.currentText()
        if "ACCEPTED" in eval_text:
            result = "ACCEPTED"
        elif "REPAIR" in eval_text:
            result = "REPAIR"
        else:
            result = "RE-EXAM"

        return {
            "record_id": _new_record_id(),
            "joint_no": self.in_joint.text().strip().upper(),
            "iso_no": self.in_iso.text().strip() or "ISO-GEN-001",
            "method": self.in_method.currentText().split(" ")[0],
            "welder": self.in_welder.text().strip().upper(),
            "size": self.in_size.text().strip() or '6" Sch 40',
            "thickness": f"{self.in_thk.value():.2f} mm",
            "process": self.in_proc.currentText(),
            "film_id": self.in_film.text().strip() or "N/A",
            "report_no": self.in_rep.text().strip() or "NDT-REP-2025",
            "defect": self.in_defect.currentText().split(" (")[0],
            "result": result,
            "date": _today(),
            "penalty_required": result == "REPAIR",
        }


# ════════════════════════════════════════════════════════════════
#  MAIN NDT RECORD DIALOG
# ════════════════════════════════════════════════════════════════

class NDTRecordDialog(QDialog):
    """
    Ultra-premium NDT Examination & Clearance Center for PipeAgent.
    Fully resizable, filterable, with automatic ASME penalty rules.
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
    DEF_WIDTH  = 1220
    DEF_HEIGHT = 800

    # Column indices (kept in one place)
    COL_JOINT  = 0
    COL_ISO    = 1
    COL_METHOD = 2
    COL_WELDER = 3
    COL_SIZE   = 4
    COL_DEFECT = 5
    COL_REPORT = 6
    COL_RESULT = 7

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
        self._records: List[Dict[str, Any]] = []
        self._filtered_records: List[Dict[str, Any]] = []

        self.setWindowTitle("PipeAgent – NDT Record & Examination Center")
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
        self._header_info = {
            "project": "South Pars Phase 14 • Area 100",
            "spec_code": "ASME B31.3 (Normal Fluid)",
            "agency": "TUV Nord NDT Inspection Services",
            "inspector": "Level-II Eng. Kaveh",
            "date": _today(),
        }

        self._records = [
            {
                "record_id": "N000000001",
                "joint_no": "W-01", "iso_no": "ISO-01-PR-2104-001",
                "method": "RT", "welder": "W-04",
                "size": '12" Sch 40', "thickness": "9.53 mm",
                "process": "GTAW + SMAW",
                "film_id": "F-01-2104-A", "report_no": "NDT-RT-2025-088",
                "defect": "Nil", "result": "ACCEPTED",
                "date": "2025-02-20", "penalty_required": False,
            },
            {
                "record_id": "N000000002",
                "joint_no": "W-02", "iso_no": "ISO-01-PR-2104-001",
                "method": "RT", "welder": "W-04",
                "size": '12" Sch 40', "thickness": "9.53 mm",
                "process": "GTAW + SMAW",
                "film_id": "F-01-2104-B", "report_no": "NDT-RT-2025-088",
                "defect": "Lack of Fusion (LF)", "result": "REPAIR",
                "date": "2025-02-20", "penalty_required": True,
            },
            {
                "record_id": "N000000003",
                "joint_no": "W-03", "iso_no": "ISO-01-PR-2104-001",
                "method": "PT", "welder": "W-12",
                "size": '12" Sch 40', "thickness": "9.53 mm",
                "process": "GTAW + SMAW",
                "film_id": "PT-SCAN-09", "report_no": "NDT-PT-2025-014",
                "defect": "Nil", "result": "ACCEPTED",
                "date": "2025-02-21", "penalty_required": False,
            },
            {
                "record_id": "N000000004",
                "joint_no": "W-08", "iso_no": "ISO-01-PR-2104-002",
                "method": "PAUT", "welder": "W-08",
                "size": '8" Sch 40', "thickness": "7.04 mm",
                "process": "GTAW",
                "film_id": "PAUT-DATA-044", "report_no": "NDT-UT-2025-099",
                "defect": "Porosity", "result": "ACCEPTED",
                "date": "2025-02-22", "penalty_required": False,
            },
            {
                "record_id": "N000000005",
                "joint_no": "W-14", "iso_no": "ISO-02-FG-3011-001A",
                "method": "PMI", "welder": "W-02",
                "size": '4" Sch 40', "thickness": "6.02 mm",
                "process": "GTAW",
                "film_id": "PMI-SPEC-110", "report_no": "NDT-PMI-2025-04",
                "defect": "Nil (SS 316L Confirmed)", "result": "ACCEPTED",
                "date": "2025-02-23", "penalty_required": False,
            },
            {
                "record_id": "N000000006",
                "joint_no": "W-19", "iso_no": "ISO-02-FG-3011-001A",
                "method": "RT", "welder": "W-12",
                "size": '4" Sch 40', "thickness": "6.02 mm",
                "process": "SMAW",
                "film_id": "F-02-3011-R", "report_no": "NDT-RT-2025-102",
                "defect": "Slag Inclusion", "result": "RE-EXAM",
                "date": "2025-02-23", "penalty_required": False,
            },
        ]
        self._filtered_records = list(self._records)

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

        # 🔧 Set particle geometry immediately so they don't cluster at (0,0).
        self._particles = ParticleField(self._card, count=16)
        self._particles.setGeometry(0, 0, self.DEF_WIDTH, self.DEF_HEIGHT)
        self._particles.lower()

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(24, 14, 24, 14)
        card_layout.setSpacing(10)

        card_layout.addLayout(self._build_topbar())
        card_layout.addWidget(self._build_header_frame())
        card_layout.addLayout(self._build_kpi_ribbon())
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

        icon_lbl = QLabel("🔬")
        icon_lbl.setFont(QFont("Segoe UI", 20))
        icon_lbl.setStyleSheet("background: transparent;")
        topbar.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)

        main_title = QLabel("PIPE AGENT  •  NDT EXAMINATION & CLEARANCE CENTER")
        main_title.setObjectName("mainTitle")
        self._add_glow(main_title, QColor(108, 207, 246, 120), blur=20)
        title_col.addWidget(main_title)

        sub_title = QLabel(
            "WELD JOINT NON-DESTRUCTIVE TESTING  •  ASME B31.3 ACCEPTANCE  •  PENALTY TRACERS"
        )
        sub_title.setObjectName("subTitle")
        title_col.addWidget(sub_title)
        topbar.addLayout(title_col)
        topbar.addStretch()

        self.btn_add_record = QPushButton("➕  LOG NDT  (Ctrl+N)")
        self.btn_add_record.setObjectName("actionBtn")
        self.btn_add_record.setMinimumHeight(36)
        self.btn_add_record.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_record.setToolTip("Log a new joint NDT record (Ctrl+N)")
        self.btn_add_record.clicked.connect(self._on_add_record)
        topbar.addWidget(self.btn_add_record)

        self.btn_export = QPushButton("📤  EXPORT  (Ctrl+E)")
        self.btn_export.setObjectName("secondaryBtn")
        self.btn_export.setMinimumHeight(36)
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.setToolTip("Export current NDT data register to CSV (Ctrl+E)")
        self.btn_export.clicked.connect(self._on_export_csv)
        topbar.addWidget(self.btn_export)

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
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(14, 8, 14, 8)
        h_layout.setSpacing(16)

        self.lbl_proj = QLabel(
            f"<b>PROJECT:</b> <span style='color:#9fe7ff;'>"
            f"{self._header_info['project']}</span>"
        )
        self.lbl_spec = QLabel(
            f"<b>CODE / SPEC:</b> <span style='color:#9fe7ff;'>"
            f"{self._header_info['spec_code']}</span>"
        )
        self.lbl_agency = QLabel(
            f"<b>NDT AGENCY:</b> <span style='color:#eef6ff;'>"
            f"{self._header_info['agency']}</span>"
        )
        self.lbl_lead = QLabel(
            f"<b>LEAD LEVEL-II:</b> <span style='color:#7a9ab3;'>"
            f"{self._header_info['inspector']}</span>"
        )

        for lbl in [self.lbl_proj, self.lbl_spec, self.lbl_agency, self.lbl_lead]:
            lbl.setStyleSheet(
                "color: #7a9ab3; font-size: 11px; background: transparent;"
            )
            h_layout.addWidget(lbl)

        return header_frame

    def _build_kpi_ribbon(self) -> QHBoxLayout:
        stat_ribbon = QHBoxLayout()
        stat_ribbon.setSpacing(12)

        self.kpi_total   = StatCard("TOTAL TESTED JOINTS", "0", "📊", self.PRIMARY_LIGHT)
        self.kpi_pass    = StatCard("PASS RATE (%)", "100%", "✅", self.SUCCESS)
        self.kpi_repairs = StatCard("REPAIRS REQUIRED", "0", "⚠️", self.ERROR)
        self.kpi_penalty = StatCard("PENALTY / TRACER QUEUE", "0", "🎯", self.WARNING)

        stat_ribbon.addWidget(self.kpi_total)
        stat_ribbon.addWidget(self.kpi_pass)
        stat_ribbon.addWidget(self.kpi_repairs)
        stat_ribbon.addWidget(self.kpi_penalty)
        return stat_ribbon

    def _build_filter_bar(self) -> QHBoxLayout:
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText(
            "🔍  Search Joint No, Welder, ISO, Film ID, Report No, Defect...  (Ctrl+F)"
        )
        self.search_input.setObjectName("searchInput")
        self.search_input.textChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.search_input, 3)

        self.combo_method = QComboBox()
        self.combo_method.setObjectName("filterCombo")
        self.combo_method.setMinimumHeight(38)
        self.combo_method.addItems([
            "All Methods", "RT", "UT", "PAUT",
            "MT", "PT", "PMI", "HT", "VT",
        ])
        self.combo_method.currentTextChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.combo_method, 1)

        self.combo_result = QComboBox()
        self.combo_result.setObjectName("filterCombo")
        self.combo_result.setMinimumHeight(38)
        self.combo_result.addItems([
            "All Results", "ACCEPTED", "REPAIR", "RE-EXAM",
        ])
        self.combo_result.currentTextChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.combo_result, 1)

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
        table.setObjectName("ndtTable")
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels([
            "Joint No", "ISO Drawing", "Method", "Welder",
            "Size & Thk", "Discontinuity", "Report No", "Evaluation",
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

        default_widths = [110, 240, 70, 80, 150, 150, 160, 130]
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
        table.doubleClicked.connect(self._on_add_record)
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

        head_lbl = QLabel("🔍   NDT JOINT & FILM INSPECTOR")
        head_lbl.setObjectName("inspHead")
        layout.addWidget(head_lbl)

        div = QFrame()
        div.setObjectName("divider")
        div.setFixedHeight(1)
        layout.addWidget(div)

        self.insp_joint = QLabel("Select a Joint")
        self.insp_joint.setObjectName("inspJoint")
        self.insp_joint.setWordWrap(True)
        layout.addWidget(self.insp_joint)

        self.insp_iso = QLabel(
            "Select any joint from the examination register to inspect defect "
            "coordinates, welder history and tracer requirements."
        )
        self.insp_iso.setObjectName("inspIso")
        self.insp_iso.setWordWrap(True)
        layout.addWidget(self.insp_iso)

        self.meta_frame = QFrame()
        self.meta_frame.setObjectName("metaFrame")
        m_layout = QVBoxLayout(self.meta_frame)
        m_layout.setContentsMargins(10, 8, 10, 8)
        m_layout.setSpacing(5)

        self.m_welder = QLabel()
        self.m_method = QLabel()
        self.m_size   = QLabel()
        self.m_proc   = QLabel()
        self.m_film   = QLabel()
        self.m_rep    = QLabel()
        self.m_tracer = QLabel()

        # Declarative spec used for both population and reset.
        self._meta_specs = [
            (self.m_welder, "Welder ID"),
            (self.m_method, "Test Method"),
            (self.m_size,   "Dimension"),
            (self.m_proc,   "Welding Process"),
            (self.m_film,   "Film / Scan ID"),
            (self.m_rep,    "Report No"),
            (self.m_tracer, "Penalty Status"),
        ]

        for lbl, _ in self._meta_specs:
            lbl.setStyleSheet(
                "color: #dfeaf5; font-size: 11px; background: transparent;"
            )
            lbl.setWordWrap(True)
            m_layout.addWidget(lbl)

        layout.addWidget(self.meta_frame)

        eval_lbl = QLabel("⚡   OVERRIDE / UPDATE EVALUATION:")
        eval_lbl.setStyleSheet(
            "color: #9fe7ff; font-size: 9px; font-weight: 800; "
            "letter-spacing: 1px; margin-top: 4px; background: transparent;"
        )
        layout.addWidget(eval_lbl)

        btn_row1 = QHBoxLayout()
        self.btn_set_acc = QPushButton("✅  ACCEPT")
        self.btn_set_acc.setObjectName("btnAccept")
        self.btn_set_acc.setMinimumHeight(34)
        self.btn_set_acc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_set_acc.setEnabled(False)
        self.btn_set_acc.clicked.connect(
            lambda: self._set_selected_eval("ACCEPTED")
        )
        btn_row1.addWidget(self.btn_set_acc)

        self.btn_set_rej = QPushButton("⚠️  REPAIR")
        self.btn_set_rej.setObjectName("btnReject")
        self.btn_set_rej.setMinimumHeight(34)
        self.btn_set_rej.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_set_rej.setEnabled(False)
        self.btn_set_rej.clicked.connect(
            lambda: self._set_selected_eval("REPAIR")
        )
        btn_row1.addWidget(self.btn_set_rej)
        layout.addLayout(btn_row1)

        self.btn_tracer = QPushButton("🎯  TRIGGER 2X PENALTY JOINTS")
        self.btn_tracer.setObjectName("secondaryBtn")
        self.btn_tracer.setMinimumHeight(32)
        self.btn_tracer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tracer.setEnabled(False)
        self.btn_tracer.clicked.connect(self._on_trigger_penalty)
        layout.addWidget(self.btn_tracer)

        layout.addStretch()

        self.btn_delete = QPushButton("🗑  REMOVE RECORD")
        self.btn_delete.setObjectName("btnDelete")
        self.btn_delete.setMinimumHeight(32)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._on_remove_record)
        layout.addWidget(self.btn_delete)

        scroll.setWidget(inner)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(scroll)
        return panel

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 2, 4, 0)

        self.lbl_count = QLabel("Showing 0 NDT records")
        self.lbl_count.setObjectName("footerLabel")
        footer.addWidget(self.lbl_count)

        footer.addStretch()

        self.lbl_timestamp = QLabel("")
        self.lbl_timestamp.setObjectName("footerLabel")
        footer.addWidget(self.lbl_timestamp)

        footer.addStretch()

        foot_tag = QLabel(
            "⚡  PipeAgent 5.0  •  Continuous Weld Quality Traceability & ASME Clearance Engine"
        )
        foot_tag.setStyleSheet(
            "color: #3f6070; font-size: 10px; letter-spacing: 1px; background: transparent;"
        )
        footer.addWidget(foot_tag)
        return footer

    # ── Keyboard Shortcuts ────────────────────────────────────
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self, self._on_add_record)
        QShortcut(QKeySequence("Ctrl+E"), self, self._on_export_csv)
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        QShortcut(QKeySequence("F5"),     self, self._apply_filters)

        # 🔧 Delete is bound to the table only, so typing Delete inside the
        #    search field no longer removes a joint record.
        del_sc = QShortcut(
            QKeySequence("Delete"), self.table, self._on_remove_record
        )
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

        selected = self._get_selected_record()

        act_accept = menu.addAction("✅  Accept")
        act_accept.setEnabled(selected is not None)
        act_accept.triggered.connect(lambda: self._set_selected_eval("ACCEPTED"))

        act_repair = menu.addAction("⚠️  Repair / Reject")
        act_repair.setEnabled(selected is not None)
        act_repair.triggered.connect(lambda: self._set_selected_eval("REPAIR"))

        act_reexam = menu.addAction("🔄  Re-examine")
        act_reexam.setEnabled(selected is not None)
        act_reexam.triggered.connect(lambda: self._set_selected_eval("RE-EXAM"))

        menu.addSeparator()

        act_tracer = menu.addAction("🎯  Trigger 2x Penalty Tracers")
        act_tracer.setEnabled(
            selected is not None and selected.get("result") == "REPAIR"
        )
        act_tracer.triggered.connect(self._on_trigger_penalty)

        act_new = menu.addAction("➕  Log New NDT Entry  (Ctrl+N)")
        act_new.triggered.connect(self._on_add_record)

        menu.addSeparator()

        act_delete = menu.addAction("🗑  Remove Joint Record")
        act_delete.setEnabled(selected is not None)
        act_delete.triggered.connect(self._on_remove_record)

        menu.exec(self.table.viewport().mapToGlobal(pos))

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
            QTableWidget#ndtTable {{
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
            QTableWidget#ndtTable::item {{
                padding: 7px 9px;
                border-bottom: 1px solid #0c1f30;
            }}
            QTableWidget#ndtTable::item:selected {{
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
            QLabel#inspJoint {{
                color: {self.ACCENT};
                font-size: 15px;
                font-weight: 800;
                background: transparent;
                font-family: Consolas, monospace;
            }}
            QLabel#inspIso {{
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

    def _get_selected_record(self) -> Optional[Dict[str, Any]]:
        """
        Return the record stored on the selected row.

        The record is attached to the first column's UserRole, so the result
        is correct even after the user re-sorts the table.
        """
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), self.COL_JOINT)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _find_record_index(self, record_id: str) -> int:
        """Locate a record in `self._records` by stable id. Returns -1 if missing."""
        for idx, r in enumerate(self._records):
            if r.get("record_id") == record_id:
                return idx
        return -1

    def _reselect_by_record_id(self, record_id: str):
        for row_idx, r in enumerate(self._filtered_records):
            if r.get("record_id") == record_id:
                self.table.selectRow(row_idx)
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

    # ── Filtering ─────────────────────────────────────────────
    def _apply_filters(self):
        search = self.search_input.text().strip().lower()
        selected_method = self.combo_method.currentText()
        selected_result = self.combo_result.currentText()

        filtered = []
        for r in self._records:
            if search:
                haystack = " ".join([
                    r["joint_no"], r["iso_no"], r["welder"],
                    r["film_id"], r["report_no"], r["defect"],
                ]).lower()
                if search not in haystack:
                    continue

            if selected_method != "All Methods":
                if r["method"].upper() != selected_method.upper():
                    continue

            if selected_result != "All Results":
                if r["result"].upper() != selected_result.upper():
                    continue

            filtered.append(r)

        self._filtered_records = filtered
        self._populate_table()
        self._update_kpi()

    def _reset_filters(self):
        # Block signals during reset so we refilter only once.
        for w in (self.search_input, self.combo_method, self.combo_result):
            w.blockSignals(True)
        try:
            self.search_input.clear()
            self.combo_method.setCurrentIndex(0)
            self.combo_result.setCurrentIndex(0)
        finally:
            for w in (self.search_input, self.combo_method, self.combo_result):
                w.blockSignals(False)
        self._apply_filters()

    def _populate_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for row_idx, r in enumerate(self._filtered_records):
            self.table.insertRow(row_idx)

            # Col 0: Joint No (also carries the record via UserRole)
            item_joint = QTableWidgetItem(r["joint_no"])
            item_joint.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            item_joint.setForeground(QColor(self.PRIMARY_LIGHT))
            item_joint.setData(Qt.ItemDataRole.UserRole, r)  # ← sort-safe link
            self.table.setItem(row_idx, self.COL_JOINT, item_joint)

            # Col 1: ISO Drawing
            item_iso = QTableWidgetItem(r["iso_no"])
            item_iso.setForeground(QColor(self.TEXT_MAIN))
            item_iso.setToolTip(r["iso_no"])
            self.table.setItem(row_idx, self.COL_ISO, item_iso)

            # Col 2: Method
            item_method = QTableWidgetItem(r["method"])
            item_method.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item_method.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_method.setForeground(QColor(self.ACCENT))
            self.table.setItem(row_idx, self.COL_METHOD, item_method)

            # Col 3: Welder
            item_welder = QTableWidgetItem(r["welder"])
            item_welder.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            item_welder.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_welder.setForeground(QColor("#ffd966"))
            self.table.setItem(row_idx, self.COL_WELDER, item_welder)

            # Col 4: Size & Thk
            item_size = QTableWidgetItem(f"{r['size']} ({r['thickness']})")
            item_size.setForeground(QColor(self.TEXT_MUTED))
            self.table.setItem(row_idx, self.COL_SIZE, item_size)

            # Col 5: Discontinuity
            item_def = QTableWidgetItem(r["defect"])
            if r["defect"] != "Nil":
                item_def.setForeground(QColor(self.WARNING))
                item_def.setToolTip(f"Discontinuity: {r['defect']}")
            else:
                item_def.setForeground(QColor("#708fa8"))
                item_def.setToolTip("Acceptable Quality Level")
            self.table.setItem(row_idx, self.COL_DEFECT, item_def)

            # Col 6: Report No
            item_rep = QTableWidgetItem(r["report_no"])
            item_rep.setFont(QFont("Consolas", 9))
            item_rep.setForeground(QColor("#8faec5"))
            self.table.setItem(row_idx, self.COL_REPORT, item_rep)

            # Col 7: Result
            item_res = QTableWidgetItem(f" ● {r['result']} ")
            item_res.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item_res.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_res.setForeground(QColor(self._result_color(r["result"])))
            self.table.setItem(row_idx, self.COL_RESULT, item_res)

        self.table.setSortingEnabled(True)

        total = len(self._records)
        shown = len(self._filtered_records)
        if shown == total:
            self.lbl_count.setText(f"Showing all {total} joint records")
        else:
            self.lbl_count.setText(
                f"Showing {shown} of {total} records (filtered)"
            )

        if self._filtered_records:
            self.table.selectRow(0)
        else:
            self._clear_inspector()

    def _result_color(self, result: str) -> str:
        s = (result or "").upper()
        if "ACCEPTED" in s:
            return self.SUCCESS
        if "REPAIR" in s:
            return self.ERROR
        if "RE-EXAM" in s:
            return self.WARNING
        return "#8faec5"

    def _update_kpi(self):
        total   = len(self._records)
        acc     = sum(1 for r in self._records if r["result"].upper() == "ACCEPTED")
        repairs = sum(1 for r in self._records if r["result"].upper() == "REPAIR")
        penalty = sum(1 for r in self._records if r.get("penalty_required", False))

        pass_pct = (acc / total * 100) if total > 0 else 100.0

        self.kpi_total.update_value(str(total))
        self.kpi_pass.update_value(f"{pass_pct:.1f}%")
        self.kpi_repairs.update_value(str(repairs))
        self.kpi_penalty.update_value(str(penalty * 2))

    # ── Table Selection → Inspector ───────────────────────────
    def _on_table_selection(self):
        r = self._get_selected_record()
        if r is None:
            self._clear_inspector()
            return

        self.insp_joint.setText(f"JOINT: {r['joint_no']} ({r['method']})")
        self.insp_iso.setText(f"Drawing: {r['iso_no']} • Defect: {r['defect']}")

        self.m_welder.setText(f"<b>Welder ID:</b> {r['welder']}")
        self.m_method.setText(
            f"<b>Test Method:</b> {r['method']} ({r.get('process', 'GTAW')})"
        )
        self.m_size.setText(f"<b>Size / Thk:</b> {r['size']} / {r['thickness']}")
        self.m_proc.setText(f"<b>Process:</b> {r.get('process', 'GTAW + SMAW')}")
        self.m_film.setText(f"<b>Film / Scan ID:</b> {r['film_id']}")
        self.m_rep.setText(f"<b>Report No:</b> {r['report_no']}")

        if r.get("penalty_required", False):
            self.m_tracer.setText(
                "<b>Penalty Status:</b> <span style='color:#ff6b6b;'>"
                "2x Tracer Joints Pending</span>"
            )
        else:
            self.m_tracer.setText(
                "<b>Penalty Status:</b> <span style='color:#5cffaa;'>"
                "Cleared (No Penalty)</span>"
            )

        self.btn_set_acc.setEnabled(True)
        self.btn_set_rej.setEnabled(True)
        self.btn_tracer.setEnabled(r["result"].upper() == "REPAIR")
        self.btn_delete.setEnabled(True)

    def _clear_inspector(self):
        self.insp_joint.setText("No Joint Selected")
        self.insp_iso.setText(
            "Select any joint from the examination register to inspect defect "
            "coordinates, welder history and tracer requirements."
        )
        # Reset driven by the declared spec — no string parsing.
        for lbl, title in self._meta_specs:
            lbl.setText(f"<b>{title}:</b> —")

        self.btn_set_acc.setEnabled(False)
        self.btn_set_rej.setEnabled(False)
        self.btn_tracer.setEnabled(False)
        self.btn_delete.setEnabled(False)

    # ── QC Decision & Penalty Tracers ─────────────────────────
    def _set_selected_eval(self, new_result: str):
        selected = self._get_selected_record()
        if selected is None:
            QMessageBox.warning(
                self, "Selection Required",
                "Please select a joint row to update evaluation.",
            )
            return

        idx = self._find_record_index(selected.get("record_id", ""))
        if idx < 0:
            QMessageBox.warning(
                self, "Record Not Found",
                "The selected joint record could no longer be located.",
            )
            return

        self._records[idx]["result"] = new_result
        self._records[idx]["penalty_required"] = (new_result == "REPAIR")

        target_id = self._records[idx].get("record_id", "")
        self._apply_filters()
        self._reselect_by_record_id(target_id)

    def _on_trigger_penalty(self):
        selected = self._get_selected_record()
        if selected is None:
            QMessageBox.warning(
                self, "Selection Required",
                "Select a rejected weld joint first.",
            )
            return

        if selected["result"] != "REPAIR":
            QMessageBox.information(
                self, "Penalty Trigger",
                "Penalty joints are only required for defective / rejected "
                "welds per ASME B31.3 Section 341.4.3.",
            )
            return

        base = {
            "iso_no": selected["iso_no"],
            "method": selected["method"],
            "welder": selected["welder"],
            "size": selected["size"],
            "thickness": selected["thickness"],
            "process": selected.get("process", "GTAW"),
            "film_id": "PENDING-TRACER",
            "report_no": f"PENALTY-{selected['report_no']}",
            "defect": "Pending Examination",
            "result": "RE-EXAM",
            "date": _today(),
            "penalty_required": False,
        }

        p1 = dict(base)
        p1["record_id"] = _new_record_id()
        p1["joint_no"] = f"{selected['joint_no']}-TR1"

        p2 = dict(base)
        p2["record_id"] = _new_record_id()
        p2["joint_no"] = f"{selected['joint_no']}-TR2"

        # Insert new tracers at the top, select the last inserted.
        self._records.insert(0, p2)
        self._records.insert(0, p1)
        self._apply_filters()
        self._reselect_by_record_id(p1["record_id"])

        QMessageBox.information(
            self, "🎯 Tracers Triggered",
            f"Per ASME B31.3 rules, <b>2 Penalty / Tracer Joints</b> have "
            f"been generated for Welder <b>{selected['welder']}</b>:<br><br>"
            f"• <b>{p1['joint_no']}</b><br>• <b>{p2['joint_no']}</b>",
        )

    # ── Add & Remove Record ───────────────────────────────────
    def _on_add_record(self):
        existing_joints = [r["joint_no"] for r in self._records]
        modal = AddNDTRecordDialog(existing_joints=existing_joints, parent=self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return

        new_rec = modal.get_data()
        self._records.insert(0, new_rec)
        self._apply_filters()
        self._reselect_by_record_id(new_rec["record_id"])

    def _on_remove_record(self):
        selected = self._get_selected_record()
        if selected is None:
            return

        reply = QMessageBox.warning(
            self, "⚠ Confirm Delete",
            f"Are you sure you want to remove the NDT record for Joint "
            f"<b>{selected['joint_no']}</b>?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        idx = self._find_record_index(selected.get("record_id", ""))
        if idx < 0:
            return
        self._records.pop(idx)
        self._apply_filters()

    # ── Export CSV ────────────────────────────────────────────
    def _on_export_csv(self):
        if self.chk_export_filtered.isChecked():
            export_records = self._filtered_records
            label = "filtered"
        else:
            export_records = self._records
            label = "all"

        if not export_records:
            QMessageBox.warning(
                self, "No Data",
                "No records to export. Adjust your filters.",
            )
            return

        default_name = (
            f"NDT_Weld_Quality_Register_{datetime.today().strftime('%Y%m%d')}.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export NDT Weld Quality Register",
            default_name, "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["═══ NDT AGENCY DOSSIER ═══"])
                writer.writerow(["Project", self._header_info["project"]])
                writer.writerow(["Inspection Standard", self._header_info["spec_code"]])
                writer.writerow(["Agency", self._header_info["agency"]])
                writer.writerow(["Lead Inspector", self._header_info["inspector"]])
                writer.writerow([])
                writer.writerow(["═══ NDT EXAMINATION REGISTER ═══"])
                writer.writerow([
                    "Joint No", "ISO Drawing", "Method", "Welder ID",
                    "Size", "Thickness", "Process", "Film ID", "Report No",
                    "Defect", "Evaluation", "Date", "Penalty Status",
                ])
                for r in export_records:
                    writer.writerow([
                        r["joint_no"], r["iso_no"], r["method"], r["welder"],
                        r["size"], r["thickness"], r.get("process", ""),
                        r["film_id"], r["report_no"], r["defect"],
                        r["result"], r["date"],
                        "Penalty Required" if r.get("penalty_required", False)
                        else "Cleared",
                    ])

            QMessageBox.information(
                self, "✅ Export Complete",
                f"Successfully exported {len(export_records)} {label} records to:\n\n{path}",
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
                f"Could not export NDT register: {e}",
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

    dialog = NDTRecordDialog()
    dialog.show()
    dialog.exec()

    sys.exit(0)