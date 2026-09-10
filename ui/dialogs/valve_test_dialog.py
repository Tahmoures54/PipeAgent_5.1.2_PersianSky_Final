# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Valve Register & Hydrostatic Testing Dialog
═══════════════════════════════════════════════════════════════════════════
Version : 5.0 (Refactored, hardened, production-ready)
Engine  : PyQt6
Design  : Cinematic dark-tech theme matching PipeAgent Suite
Standards: API 598, API 6D, ISO 5208, ASME B16.34

Fixes in this revision
──────────────────────
🔴 P0  Card border        : replaced invalid `border: ... qlineargradient`
                          with a solid color + drop shadow
🔴 P0  GlowLineEdit       : no longer calls deleteLater() on an animation
                          that Qt owns (DeleteWhenStopped)
🔴 P0  _shake             : same lifetime fix
🔴 P0  _cleanup           : idempotent via `_is_closed` flag; safe to call
                          from reject / closeEvent / done
🟠 P1  Particle geometry  : set immediately after creation
🟠 P1  done() override    : cleanup runs exactly once on every close path
🟠 P1  Date parsing       : tolerant helper handles date / datetime /
                          ISO string
🟠 P1  Signal storm       : `_auto_calc_pressures` blocks signals while
                          setting the spinboxes → single banner refresh
🟡 P2  ParticleField      : count 28 → 14, tick 60ms → 100ms, paints only
                          when visible
🟡 P2  Minimum heights    : QDateEdit / QSpinBox now 38 px for visual
                          consistency
🟡 P2  GlowTextEdit n/a   : this dialog has no text edits
🟢 P3  Tooltips           : on every field / button
🟢 P3  _today() helper    : single source for the current date
"""

from __future__ import annotations

import os
import sys
import random
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRect, QSize, QDate,
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
    QDateEdit, QScrollArea, QCheckBox,
)

logger = logging.getLogger(__name__)

# ── Safe Core Constants Fallback ────────────────────────────────────
try:
    from core.constants import VALVE_TYPES, VALVE_RATINGS
except ImportError:
    VALVE_TYPES = [
        "Gate Valve (Wedge / Slab)",
        "Globe Valve (Stop / Needle)",
        "Ball Valve (Floating / Trunnion)",
        "Check Valve (Swing / Piston / Dual Plate)",
        "Butterfly Valve (Concentric / Triple Offset)",
        "Plug Valve (Lubricated / Sleeved)",
        "DBB Valve (Double Block & Bleed)",
        "Control Valve / ESDV (Safety Shut-off)",
    ]
    VALVE_RATINGS = [
        "Class 150# (PN 20)",
        "Class 300# (PN 50)",
        "Class 600# (PN 100)",
        "Class 800# (Forged)",
        "Class 900# (PN 150)",
        "Class 1500# (PN 250)",
        "Class 2500# (PN 420)",
    ]

# ── API 598 / ASME B16.34 Approximate Pressure Matrix (Bar) ─────────
# Based on Standard Carbon Steel (A105 / A216 WCB) @ Ambient Temperature
API_598_PRESSURE_MAP = {
    "150":  {"shell": 30.0,  "seat_hydro": 22.0,  "seat_air": 6.0},
    "300":  {"shell": 77.0,  "seat_hydro": 56.5,  "seat_air": 6.0},
    "600":  {"shell": 153.0, "seat_hydro": 112.5, "seat_air": 6.0},
    "800":  {"shell": 207.0, "seat_hydro": 152.0, "seat_air": 6.0},
    "900":  {"shell": 230.0, "seat_hydro": 168.0, "seat_air": 6.0},
    "1500": {"shell": 383.0, "seat_hydro": 281.0, "seat_air": 6.0},
    "2500": {"shell": 638.0, "seat_hydro": 468.0, "seat_air": 6.0},
}


# ════════════════════════════════════════════════════════════════
#  UTILITIES
# ════════════════════════════════════════════════════════════════

def _parse_date(value: Any) -> Optional[date]:
    """Best-effort date parser: date / datetime / 'YYYY-MM-DD' / None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


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
#  MAIN VALVE TEST DIALOG
# ════════════════════════════════════════════════════════════════

class ValveTestDialog(QDialog):
    """
    Ultra-premium Valve Register & Testing / Clearance Dialog.
    Frameless, responsive, resizable, with API 598 Pressure Calculator.
    """

    # ── Cinematic Dark Palette ───────────────────────────────
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

    MIN_WIDTH  = 940
    MIN_HEIGHT = 650
    DEF_WIDTH  = 1050
    DEF_HEIGHT = 760

    def __init__(self, parent=None, valve_data: Optional[dict] = None):
        super().__init__(parent)
        self.valve_data: Dict[str, Any] = valve_data or {}
        self.result_data: Dict[str, Any] = {}

        # Frameless dragging & resizing parameters
        self._drag_pos: Optional[QPoint] = None
        self._drag_edge: Optional[str] = None
        self._drag_geometry: Optional[QRect] = None
        self._resize_margin = 8

        # Lifecycle & animations
        self._is_closed = False
        self._shake_anim: Optional[QPropertyAnimation] = None

        self.setWindowTitle("PipeAgent – Valve Register & Pressure Testing")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(self.DEF_WIDTH, self.DEF_HEIGHT)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self._build_ui()
        self._setup_shortcuts()
        self._center_on_screen()
        self._load_existing_data()

    # ── UI Construction ───────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QWidget()
        self._card.setObjectName("mainCard")
        self._card.setStyleSheet(self._stylesheet())
        self._card.setMouseTracking(True)

        card_shadow = QGraphicsDropShadowEffect(self._card)
        card_shadow.setBlurRadius(40)
        card_shadow.setColor(QColor(0, 0, 0, 180))
        card_shadow.setOffset(0, 8)
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
        card_layout.addWidget(self._build_test_banner())

        # ── Split Dashboard (Left vs Right Panel) ────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        splitter.setHandleWidth(3)
        splitter.setChildrenCollapsible(False)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([500, 500])

        card_layout.addWidget(splitter, 1)
        card_layout.addLayout(self._build_footer())

        # Initial Auto-Calculation
        self._auto_calc_pressures()

    def _build_topbar(self) -> QHBoxLayout:
        topbar = QHBoxLayout()
        topbar.setContentsMargins(0, 0, 0, 0)

        icon_lbl = QLabel("🚰")
        icon_lbl.setFont(QFont("Segoe UI", 20))
        icon_lbl.setStyleSheet("background: transparent;")
        topbar.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)

        main_title = QLabel("PIPE AGENT  •  VALVE TESTING & QC CLEARANCE CENTER")
        main_title.setObjectName("mainTitle")
        self._add_glow(main_title, QColor(108, 207, 246, 120), blur=20)
        title_col.addWidget(main_title)

        sub_title = QLabel(
            "API 598 / ISO 5208 PRESSURE TESTING  •  SHELL & SEAT TIGHTNESS  •  TRACEABILITY"
        )
        sub_title.setObjectName("subTitle")
        title_col.addWidget(sub_title)
        topbar.addLayout(title_col)
        topbar.addStretch()

        min_btn = QPushButton("─")
        min_btn.setObjectName("controlBtn")
        min_btn.setFixedSize(28, 28)
        min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        min_btn.setToolTip("Minimize")
        min_btn.clicked.connect(self.showMinimized)
        min_btn.setStyleSheet("""
            QPushButton#controlBtn {
                background: transparent; color: #7a9ab3;
                border: none; border-radius: 14px;
            }
            QPushButton#controlBtn:hover {
                background: rgba(108, 207, 246, 0.15); color: #6ccff6;
            }
        """)
        topbar.addWidget(min_btn)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close (Escape)")
        close_btn.clicked.connect(self.reject)
        topbar.addWidget(close_btn)

        return topbar

    def _build_test_banner(self) -> QFrame:
        self.banner = QFrame()
        self.banner.setObjectName("testBanner")
        b_layout = QHBoxLayout(self.banner)
        b_layout.setContentsMargins(14, 8, 14, 8)
        b_layout.setSpacing(12)

        self.banner_icon = QLabel("🛡️")
        self.banner_icon.setFont(QFont("Segoe UI", 16))
        self.banner_icon.setStyleSheet("background: transparent;")
        b_layout.addWidget(self.banner_icon)

        b_col = QVBoxLayout()
        b_col.setSpacing(2)

        self.lbl_banner_title = QLabel("VALVE STATUS: PENDING TEST REGISTRATION")
        self.lbl_banner_title.setObjectName("bannerTitle")
        self.lbl_banner_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        b_col.addWidget(self.lbl_banner_title)

        self.lbl_banner_detail = QLabel(
            "API 598 Target: Shell Hydro @ 30.0 Bar ➔ "
            "High-Pressure Seat @ 22.0 Bar ➔ Air Seat @ 6.0 Bar"
        )
        self.lbl_banner_detail.setStyleSheet(
            "color: #a2c2dc; font-size: 10px; background: transparent;"
        )
        b_col.addWidget(self.lbl_banner_detail)

        b_layout.addLayout(b_col, 1)

        self.btn_autocalc = QPushButton("⚡ Auto-Calc (API 598)")
        self.btn_autocalc.setObjectName("calcBtn")
        self.btn_autocalc.setToolTip(
            "Auto-calculate Shell and Seat Test pressures based on Rating Class"
        )
        self.btn_autocalc.clicked.connect(self._auto_calc_pressures)
        b_layout.addWidget(self.btn_autocalc)

        return self.banner

    def _build_left_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("formGroup")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel("🏷️   VALVE SPECIFICATIONS & TRACEABILITY")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("panelScroll")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        form = QVBoxLayout(inner)
        form.setSpacing(8)

        # Tag & Line No
        row0 = QHBoxLayout()
        col_tag = QVBoxLayout()
        col_tag.addWidget(QLabel("VALVE TAG / ITEM NO *"))
        self.txt_tag = GlowLineEdit()
        self.txt_tag.setPlaceholderText("e.g. XV-2104-01 / V-102")
        self.txt_tag.setToolTip("Unique valve tag identifier — required")
        col_tag.addWidget(self.txt_tag)
        row0.addLayout(col_tag)

        col_line = QVBoxLayout()
        col_line.addWidget(QLabel("LINE NUMBER / SYSTEM"))
        self.txt_line = GlowLineEdit()
        self.txt_line.setPlaceholderText('e.g. 12"-PR-2104-A1A')
        self.txt_line.setToolTip("Piping line or system identifier")
        col_line.addWidget(self.txt_line)
        row0.addLayout(col_line)
        form.addLayout(row0)

        # Type
        form.addWidget(QLabel("VALVE TYPE / DESIGN"))
        self.cmb_type = QComboBox()
        self.cmb_type.setObjectName("glowCombo")
        self.cmb_type.setMinimumHeight(38)
        self.cmb_type.addItems(VALVE_TYPES)
        self.cmb_type.setToolTip("Valve design type")
        form.addWidget(self.cmb_type)

        # Size & Rating
        row1 = QHBoxLayout()
        col_size = QVBoxLayout()
        col_size.addWidget(QLabel("SIZE / NPS"))
        self.txt_size = GlowLineEdit()
        self.txt_size.setPlaceholderText('e.g. 4" / DN 100')
        self.txt_size.setToolTip("Nominal pipe size of valve")
        col_size.addWidget(self.txt_size)
        row1.addLayout(col_size)

        col_rat = QVBoxLayout()
        col_rat.addWidget(QLabel("PRESSURE RATING (CLASS) *"))
        self.cmb_rating = QComboBox()
        self.cmb_rating.setObjectName("glowCombo")
        self.cmb_rating.setMinimumHeight(38)
        self.cmb_rating.addItems(VALVE_RATINGS)
        self.cmb_rating.setToolTip("ASME pressure class rating")
        self.cmb_rating.currentIndexChanged.connect(self._auto_calc_pressures)
        col_rat.addWidget(self.cmb_rating)
        row1.addLayout(col_rat)
        form.addLayout(row1)

        # Body Material & Trim
        row2 = QHBoxLayout()
        col_body = QVBoxLayout()
        col_body.addWidget(QLabel("BODY MATERIAL"))
        self.txt_body = GlowLineEdit()
        self.txt_body.setPlaceholderText("e.g. ASTM A216 WCB / A105")
        self.txt_body.setToolTip("Valve body material specification")
        col_body.addWidget(self.txt_body)
        row2.addLayout(col_body)

        col_trim = QVBoxLayout()
        col_trim.addWidget(QLabel("TRIM SPECIFICATION"))
        self.txt_trim = GlowLineEdit()
        self.txt_trim.setPlaceholderText("e.g. Trim 8 (13Cr / HF)")
        self.txt_trim.setToolTip("Internal trim material specification")
        col_trim.addWidget(self.txt_trim)
        row2.addLayout(col_trim)
        form.addLayout(row2)

        # Manufacturer & Heat Number
        row3 = QHBoxLayout()
        col_mfr = QVBoxLayout()
        col_mfr.addWidget(QLabel("MANUFACTURER / VENDOR"))
        self.txt_mfr = GlowLineEdit()
        self.txt_mfr.setPlaceholderText("e.g. Cameron / Bonney Forge")
        self.txt_mfr.setToolTip("Valve manufacturer")
        col_mfr.addWidget(self.txt_mfr)
        row3.addLayout(col_mfr)

        col_heat = QVBoxLayout()
        col_heat.addWidget(QLabel("HEAT / CAST / LOT NO."))
        self.txt_heat = GlowLineEdit()
        self.txt_heat.setPlaceholderText("e.g. H-88420-B")
        self.txt_heat.setToolTip("Heat / cast number for traceability")
        col_heat.addWidget(self.txt_heat)
        row3.addLayout(col_heat)
        form.addLayout(row3)

        # MTC / Serial
        form.addWidget(QLabel("MILL TEST CERTIFICATE (MTC) / SERIAL NUMBER"))
        self.txt_mtc = GlowLineEdit()
        self.txt_mtc.setPlaceholderText("e.g. MTC-VAL-2025-992 / SN-4401")
        self.txt_mtc.setToolTip("MTC certificate or valve serial number")
        form.addWidget(self.txt_mtc)

        form.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        return card

    def _build_right_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("formGroup")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel("🧪   API 598 / ISO 5208 TEST VERIFICATION")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("panelScroll")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        form = QVBoxLayout(inner)
        form.setSpacing(10)

        # 1. Shell Hydro Test Box
        box_shell = QFrame()
        box_shell.setObjectName("innerBox")
        bs_layout = QVBoxLayout(box_shell)
        bs_layout.setContentsMargins(10, 8, 10, 8)
        bs_layout.setSpacing(6)

        head_shell = QHBoxLayout()
        self.chk_shell = QCheckBox("HYDROSTATIC SHELL TEST (1.5x CWP)")
        self.chk_shell.setStyleSheet(
            "color: #9fe7ff; font-weight: bold; font-size: 11px;"
        )
        self.chk_shell.setChecked(True)
        self.chk_shell.setToolTip("Enable hydrostatic shell test")
        self.chk_shell.toggled.connect(self._update_banner_status)
        head_shell.addWidget(self.chk_shell)
        head_shell.addStretch()

        self.lbl_shell_res = QLabel("● PASSED")
        self.lbl_shell_res.setStyleSheet(
            "color: #5cffaa; font-weight: bold; font-size: 10px;"
        )
        head_shell.addWidget(self.lbl_shell_res)
        bs_layout.addLayout(head_shell)

        row_sp = QHBoxLayout()
        col_sp = QVBoxLayout()
        col_sp.addWidget(QLabel("TEST PRESSURE (BAR)"))
        self.spn_shell_p = QDoubleSpinBox()
        self.spn_shell_p.setObjectName("glowSpin")
        self.spn_shell_p.setMinimumHeight(38)
        self.spn_shell_p.setRange(0.0, 2000.0)
        self.spn_shell_p.setValue(30.0)
        self.spn_shell_p.setSuffix(" bar")
        self.spn_shell_p.setToolTip("Shell test pressure (bar)")
        self.spn_shell_p.valueChanged.connect(self._update_banner_status)
        col_sp.addWidget(self.spn_shell_p)
        row_sp.addLayout(col_sp)

        col_sdur = QVBoxLayout()
        col_sdur.addWidget(QLabel("DURATION (SEC)"))
        self.spn_shell_dur = QSpinBox()
        self.spn_shell_dur.setObjectName("glowSpin")
        self.spn_shell_dur.setMinimumHeight(38)
        self.spn_shell_dur.setRange(15, 600)
        self.spn_shell_dur.setValue(60)
        self.spn_shell_dur.setSuffix(" s")
        self.spn_shell_dur.setToolTip("Test duration (seconds)")
        col_sdur.addWidget(self.spn_shell_dur)
        row_sp.addLayout(col_sdur)

        col_sdate = QVBoxLayout()
        col_sdate.addWidget(QLabel("DATE OF TEST"))
        self.dte_shell = QDateEdit()
        self.dte_shell.setObjectName("glowDate")
        self.dte_shell.setMinimumHeight(38)
        self.dte_shell.setCalendarPopup(True)
        self.dte_shell.setDate(QDate.currentDate())
        self.dte_shell.setToolTip("Date of shell test")
        col_sdate.addWidget(self.dte_shell)
        row_sp.addLayout(col_sdate)
        bs_layout.addLayout(row_sp)
        form.addWidget(box_shell)

        # 2. High-Pressure Seat Test Box
        box_seat = QFrame()
        box_seat.setObjectName("innerBox")
        bseat_layout = QVBoxLayout(box_seat)
        bseat_layout.setContentsMargins(10, 8, 10, 8)
        bseat_layout.setSpacing(6)

        head_seat = QHBoxLayout()
        self.chk_seat = QCheckBox("HYDROSTATIC SEAT TEST (1.1x CWP)")
        self.chk_seat.setStyleSheet(
            "color: #9fe7ff; font-weight: bold; font-size: 11px;"
        )
        self.chk_seat.setChecked(True)
        self.chk_seat.setToolTip("Enable hydrostatic seat test")
        self.chk_seat.toggled.connect(self._update_banner_status)
        head_seat.addWidget(self.chk_seat)
        head_seat.addStretch()

        self.lbl_seat_res = QLabel("● ZERO LEAKAGE")
        self.lbl_seat_res.setStyleSheet(
            "color: #5cffaa; font-weight: bold; font-size: 10px;"
        )
        head_seat.addWidget(self.lbl_seat_res)
        bseat_layout.addLayout(head_seat)

        row_seatp = QHBoxLayout()
        col_seatp = QVBoxLayout()
        col_seatp.addWidget(QLabel("SEAT PRESSURE (BAR)"))
        self.spn_seat_p = QDoubleSpinBox()
        self.spn_seat_p.setObjectName("glowSpin")
        self.spn_seat_p.setMinimumHeight(38)
        self.spn_seat_p.setRange(0.0, 2000.0)
        self.spn_seat_p.setValue(22.0)
        self.spn_seat_p.setSuffix(" bar")
        self.spn_seat_p.setToolTip("Seat test pressure (bar)")
        self.spn_seat_p.valueChanged.connect(self._update_banner_status)
        col_seatp.addWidget(self.spn_seat_p)
        row_seatp.addLayout(col_seatp)

        col_seattype = QVBoxLayout()
        col_seattype.addWidget(QLabel("SEAT TIGHTNESS CLASS"))
        self.cmb_seat_tight = QComboBox()
        self.cmb_seat_tight.setObjectName("glowCombo")
        self.cmb_seat_tight.setMinimumHeight(38)
        self.cmb_seat_tight.addItems([
            "API 598 Rate A (Zero Leak)",
            "ISO 5208 Rate A (Bubble Tight)",
            "FCI 70-2 Class IV / VI",
        ])
        self.cmb_seat_tight.setToolTip("Required seat tightness class")
        col_seattype.addWidget(self.cmb_seat_tight)
        row_seatp.addLayout(col_seattype)

        col_seatdate = QVBoxLayout()
        col_seatdate.addWidget(QLabel("DATE OF TEST"))
        self.dte_seat = QDateEdit()
        self.dte_seat.setObjectName("glowDate")
        self.dte_seat.setMinimumHeight(38)
        self.dte_seat.setCalendarPopup(True)
        self.dte_seat.setDate(QDate.currentDate())
        self.dte_seat.setToolTip("Date of seat test")
        col_seatdate.addWidget(self.dte_seat)
        row_seatp.addLayout(col_seatdate)
        bseat_layout.addLayout(row_seatp)
        form.addWidget(box_seat)

        # 3. Witness & QA Sign-off
        row_wit = QHBoxLayout()
        col_wit = QVBoxLayout()
        col_wit.addWidget(QLabel("QC WITNESSED BY (INSPECTOR)"))
        self.txt_witness = GlowLineEdit()
        self.txt_witness.setPlaceholderText("e.g. QC Eng. Farhadi")
        self.txt_witness.setToolTip("Name of witnessing QC inspector")
        col_wit.addWidget(self.txt_witness)
        row_wit.addLayout(col_wit)

        col_stamp = QVBoxLayout()
        col_stamp.addWidget(QLabel("INSPECTOR STAMP / ID"))
        self.txt_stamp = GlowLineEdit()
        self.txt_stamp.setPlaceholderText("e.g. QC-VALVE-04")
        self.txt_stamp.setToolTip("Inspector digital stamp identifier")
        col_stamp.addWidget(self.txt_stamp)
        row_wit.addLayout(col_stamp)
        form.addLayout(row_wit)

        form.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        return card

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.lbl_warning = QLabel("")
        self.lbl_warning.setObjectName("warningLabel")
        self.lbl_warning.setStyleSheet(
            "color: #ff6b6b; font-size: 11px; font-weight: bold; background: transparent;"
        )
        footer.addWidget(self.lbl_warning, 1)

        self.btn_save = QPushButton("⚡  SAVE VALVE RECORD  (Ctrl+S)")
        self.btn_save.setObjectName("saveBtn")
        self.btn_save.setMinimumHeight(42)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setToolTip("Save valve record (Ctrl+S)")
        self.btn_save.clicked.connect(self._save)
        self._add_glow(self.btn_save, QColor(104, 215, 255, 100), blur=18)
        footer.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("CANCEL")
        self.btn_cancel.setObjectName("cancelBtn")
        self.btn_cancel.setMinimumHeight(42)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setToolTip("Discard and close (Escape)")
        self.btn_cancel.clicked.connect(self.reject)
        footer.addWidget(self.btn_cancel)

        return footer

    # ── Shortcuts ─────────────────────────────────────────────
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+S"), self, self._save)
        QShortcut(QKeySequence("Ctrl+T"), self, self._auto_calc_pressures)
        QShortcut(QKeySequence("Escape"), self, self.reject)

    # ── API 598 Pressure Calculator ───────────────────────────
    def _auto_calc_pressures(self, *_):
        """
        Compute shell & seat pressures from the rating class.

        Blocks signals while setting the spinboxes, then refreshes the
        banner once at the end.
        """
        rating_text = self.cmb_rating.currentText()
        matched_class = None
        for k in API_598_PRESSURE_MAP.keys():
            if f"Class {k}" in rating_text:
                matched_class = k
                break

        if matched_class and matched_class in API_598_PRESSURE_MAP:
            p_data = API_598_PRESSURE_MAP[matched_class]

            # Block value signals so we don't refresh the banner twice.
            for spn in (self.spn_shell_p, self.spn_seat_p):
                spn.blockSignals(True)
            try:
                self.spn_shell_p.setValue(p_data["shell"])
                self.spn_seat_p.setValue(p_data["seat_hydro"])
            finally:
                for spn in (self.spn_shell_p, self.spn_seat_p):
                    spn.blockSignals(False)

        self._update_banner_status()

    def _update_banner_status(self, *_):
        sh_ok = self.chk_shell.isChecked()
        st_ok = self.chk_seat.isChecked()

        if sh_ok and st_ok:
            title = "VALVE STATUS: FULLY TESTED & HYDROSTATICALLY CLEARED (API 598)"
            color = self.SUCCESS
            icon = "✅"
        elif sh_ok:
            title = "VALVE STATUS: SHELL TEST COMPLETED — SEAT TEST PENDING"
            color = self.WARNING
            icon = "⏳"
        else:
            title = "VALVE STATUS: PENDING TEST REGISTRATION & WITNESS"
            color = self.PRIMARY_LIGHT
            icon = "🛡️"

        self.banner_icon.setText(icon)
        self.lbl_banner_title.setText(title)
        self.lbl_banner_title.setStyleSheet(
            f"color: {color}; background: transparent; font-weight: bold;"
        )
        self.lbl_banner_detail.setText(
            f"API 598 Target: Shell Hydro @ {self.spn_shell_p.value():.1f} Bar ➔ "
            f"High-Pressure Seat @ {self.spn_seat_p.value():.1f} Bar ➔ Air Seat @ 6.0 Bar"
        )

    # ── Load Existing Data ────────────────────────────────────
    def _load_existing_data(self):
        if not self.valve_data:
            return

        self.setWindowTitle("PipeAgent – Edit Valve Test Record")

        # Block value signals while loading to avoid a shower of
        # `_update_banner_status` calls.
        blocked_widgets = [
            self.spn_shell_p, self.spn_seat_p,
            self.chk_shell, self.chk_seat,
        ]
        for w in blocked_widgets:
            w.blockSignals(True)

        try:
            self.txt_tag.setText(str(self.valve_data.get("valve_tag", "")))
            self.txt_line.setText(str(self.valve_data.get("line_number", "")))
            self.txt_size.setText(str(self.valve_data.get("size_nps", "")))
            self.txt_body.setText(str(self.valve_data.get("body_material", "")))
            self.txt_trim.setText(str(self.valve_data.get("trim_material", "")))
            self.txt_mfr.setText(str(self.valve_data.get("manufacturer", "")))
            self.txt_heat.setText(str(self.valve_data.get("heat_number", "")))
            self.txt_mtc.setText(str(self.valve_data.get("mtc_number", "")))
            self.txt_witness.setText(str(self.valve_data.get("test_witness", "")))
            self.txt_stamp.setText(str(self.valve_data.get("witness_stamp_id", "")))

            # Combos
            type_idx = self.cmb_type.findText(
                str(self.valve_data.get("valve_type", ""))
            )
            if type_idx >= 0:
                self.cmb_type.setCurrentIndex(type_idx)

            rat_idx = self.cmb_rating.findText(
                str(self.valve_data.get("rating_class", ""))
            )
            if rat_idx >= 0:
                self.cmb_rating.setCurrentIndex(rat_idx)

            # Checkboxes & pressures
            self.chk_shell.setChecked(
                bool(self.valve_data.get("hydro_shell_test", True))
            )
            self.chk_seat.setChecked(
                bool(self.valve_data.get("hydro_seat_test", True))
            )

            if "hydro_shell_pressure_bar" in self.valve_data:
                self.spn_shell_p.setValue(
                    float(self.valve_data["hydro_shell_pressure_bar"])
                )
            if "hydro_seat_pressure_bar" in self.valve_data:
                self.spn_seat_p.setValue(
                    float(self.valve_data["hydro_seat_pressure_bar"])
                )

            # Dates — tolerant of date / datetime / ISO string
            dt_shell = _parse_date(self.valve_data.get("hydro_shell_date"))
            if dt_shell is not None:
                self.dte_shell.setDate(
                    QDate(dt_shell.year, dt_shell.month, dt_shell.day)
                )

            dt_seat = _parse_date(self.valve_data.get("hydro_seat_date"))
            if dt_seat is not None:
                self.dte_seat.setDate(
                    QDate(dt_seat.year, dt_seat.month, dt_seat.day)
                )
        finally:
            for w in blocked_widgets:
                w.blockSignals(False)

        # Single banner refresh at the end.
        self._update_banner_status()

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
            self.reject()
        else:
            super().keyPressEvent(event)

    # ── Shake Animation ───────────────────────────────────────
    def _shake(self):
        if self._shake_anim is not None:
            try:
                self._shake_anim.stop()
            except RuntimeError:
                pass
            self._shake_anim = None

        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(320)
        start = self.pos()
        anim.setKeyValueAt(0.0, start)
        anim.setKeyValueAt(0.1, start + QPoint(-8, 0))
        anim.setKeyValueAt(0.25, start + QPoint(8, 0))
        anim.setKeyValueAt(0.4, start + QPoint(-6, 0))
        anim.setKeyValueAt(0.55, start + QPoint(6, 0))
        anim.setKeyValueAt(0.7, start + QPoint(-3, 0))
        anim.setKeyValueAt(0.85, start + QPoint(3, 0))
        anim.setKeyValueAt(1.0, start)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._shake_anim = anim

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
            QLabel#sectionTitle {{
                color: {self.PRIMARY_LIGHT};
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 1.5px;
                background: transparent;
                padding-bottom: 4px;
            }}
            QFrame#formGroup {{
                background: #091726;
                border: 1px solid #183854;
                border-radius: 10px;
            }}
            QFrame#innerBox {{
                background: #06101c;
                border: 1px solid #10263b;
                border-radius: 8px;
            }}
            QFrame#testBanner {{
                background: #081e28;
                border: 1px solid #1e3d5a;
                border-left: 3px solid #6ccff6;
                border-radius: 8px;
            }}
            QLabel#bannerTitle {{
                color: {self.PRIMARY_LIGHT};
                background: transparent;
                letter-spacing: 1px;
            }}
            QPushButton#calcBtn {{
                background: #0b1c2e;
                color: #6ccff6;
                border: 1px solid #1e3d5a;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 10px;
                font-weight: 800;
            }}
            QPushButton#calcBtn:hover {{
                background: #14334f;
                color: #9fe7ff;
                border: 1px solid #6ccff6;
            }}
            QLabel {{
                color: {self.PRIMARY_LIGHT};
                font-size: 9px;
                font-weight: 800;
                letter-spacing: 1px;
                background: transparent;
            }}
            QLineEdit {{
                background: {self.BG_INPUT};
                color: {self.TEXT_MAIN};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {self.PRIMARY};
                background: #0d1f30;
            }}
            QComboBox#glowCombo, QDateEdit#glowDate,
            QDoubleSpinBox#glowSpin, QSpinBox#glowSpin {{
                background: {self.BG_INPUT};
                color: {self.TEXT_MAIN};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
            }}
            QComboBox#glowCombo:hover, QDateEdit#glowDate:hover,
            QDoubleSpinBox#glowSpin:hover, QSpinBox#glowSpin:hover {{
                border: 1px solid {self.PRIMARY};
            }}
            QComboBox#glowCombo QAbstractItemView {{
                background: #07101a;
                color: {self.TEXT_MAIN};
                selection-background-color: #14334f;
                selection-color: {self.PRIMARY_LIGHT};
                border: 1px solid #1e3d5a;
            }}
            QPushButton#saveBtn {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2196d4,
                    stop:0.5 {self.ACCENT},
                    stop:1 #2196d4
                );
                color: #041827;
                border: none;
                border-radius: 8px;
                padding: 0 24px;
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 1px;
            }}
            QPushButton#saveBtn:hover {{ background: {self.PRIMARY_LIGHT}; }}
            QPushButton#cancelBtn {{
                background: transparent;
                color: {self.PRIMARY_LIGHT};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 0 18px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton#cancelBtn:hover {{
                background: #142a40;
                border: 1px solid {self.PRIMARY};
            }}
            QPushButton#closeBtn {{
                background: transparent;
                color: {self.TEXT_MUTED};
                border: none;
                border-radius: 14px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton#closeBtn:hover {{
                background: rgba(255, 107, 107, 0.2);
                color: {self.ERROR};
            }}
            QScrollArea#panelScroll {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: #07101a; width: 6px;
                border-radius: 3px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: #1e3d5a; border-radius: 3px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {self.PRIMARY}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QSplitter::handle {{
                background: #102538;
                border-radius: 1px;
            }}
        """

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

    # ── Save & Validation Logic ───────────────────────────────
    def _save(self):
        if self._is_closed:
            return

        tag = self.txt_tag.text().strip()

        if not tag:
            self.lbl_warning.setText(
                "⚠️ Validation Error: Valve Tag / Item ID is required."
            )
            self._shake()
            self.txt_tag.setFocus()
            return

        self.lbl_warning.setText("")

        self.result_data = {
            "valve_tag": tag,
            "line_number": self.txt_line.text().strip(),
            "valve_type": self.cmb_type.currentText(),
            "size_nps": self.txt_size.text().strip(),
            "rating_class": self.cmb_rating.currentText(),
            "body_material": self.txt_body.text().strip(),
            "trim_material": self.txt_trim.text().strip(),
            "manufacturer": self.txt_mfr.text().strip(),
            "heat_number": self.txt_heat.text().strip(),
            "mtc_number": self.txt_mtc.text().strip(),
            "hydro_shell_test": self.chk_shell.isChecked(),
            "hydro_shell_pressure_bar": self.spn_shell_p.value(),
            "hydro_shell_duration_s": self.spn_shell_dur.value(),
            "hydro_shell_date": self.dte_shell.date().toPyDate(),
            "hydro_seat_test": self.chk_seat.isChecked(),
            "hydro_seat_pressure_bar": self.spn_seat_p.value(),
            "seat_tightness_class": self.cmb_seat_tight.currentText(),
            "hydro_seat_date": self.dte_seat.date().toPyDate(),
            "test_witness": self.txt_witness.text().strip(),
            "witness_stamp_id": self.txt_stamp.text().strip(),
            "status": (
                "APPROVED"
                if (self.chk_shell.isChecked() and self.chk_seat.isChecked())
                else "PENDING"
            ),
        }

        self.accept()

    # ── Graceful close ────────────────────────────────────────
    def _cleanup(self):
        """Stop every timer / animation we own. Safe to call twice."""
        if self._is_closed:
            return
        self._is_closed = True

        if hasattr(self, "_particles"):
            try:
                self._particles.stop()
            except RuntimeError:
                pass

        if self._shake_anim is not None:
            try:
                self._shake_anim.stop()
            except RuntimeError:
                pass
            self._shake_anim = None

    def reject(self):
        self._cleanup()
        super().reject()

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

    # Sample mock data for preview/testing
    mock_valve = {
        "valve_tag": "12-XV-2104-01",
        "line_number": '12"-PR-2104-A1A',
        "valve_type": "Ball Valve (Floating / Trunnion)",
        "size_nps": '12" (DN 300)',
        "rating_class": "Class 300# (PN 50)",
        "body_material": "ASTM A216 WCB",
        "manufacturer": "Cameron Valves Ltd.",
        "heat_number": "H-99210-A",
        "hydro_shell_test": True,
        "hydro_shell_pressure_bar": 77.0,
        "hydro_shell_date": date.today(),
        "hydro_seat_test": True,
        "hydro_seat_pressure_bar": 56.5,
        "hydro_seat_date": date.today(),
        "test_witness": "Eng. Farhadi (Lead QC Inspector)",
    }

    dialog = ValveTestDialog(valve_data=mock_valve)
    dialog.show()
    dialog.exec()

    if getattr(dialog, "result_data", None):
        print("Valve Registered Result Data:", dialog.result_data)

    sys.exit(0)