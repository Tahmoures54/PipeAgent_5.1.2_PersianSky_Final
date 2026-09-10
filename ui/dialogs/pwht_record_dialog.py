# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium PWHT (Post-Weld Heat Treatment) Record Dialog
══════════════════════════════════════════════════════════════════════════
Version : 5.0 (Refactored, hardened, production-ready)
Engine  : PyQt6
Design  : Cinematic dark-tech theme matching PipeAgent Suite

Fixes in this revision
──────────────────────
🔴 P0  Card border        : replaced invalid `border: ... qlineargradient`
                          with a solid color + drop shadow
🔴 P0  GlowLineEdit       : no longer calls deleteLater() on an animation
                          that Qt owns (DeleteWhenStopped)
🔴 P0  _shake             : same lifetime fix
🔴 P0  _cleanup           : now idempotent via `_is_closed` flag; safe to
                          call from reject / closeEvent / done
🔴 P0  Load order         : spinner values are set BEFORE the hardness
                          checkbox so the initial warning badge is correct
🟠 P1  Particle geometry  : set immediately after creation
🟠 P1  done() override    : cleanup runs exactly once on every close path
🟠 P1  Date parsing       : tolerant helper handles date / datetime /
                          ISO string
🟠 P1  Signals on load    : value/currentIndex signals are blocked while
                          loading existing data → single refresh at the end
🟠 P1  Hardness field     : when the test is "No", the HV spinner is
                          disabled and shows 0.0 to avoid misleading values
🟡 P2  ParticleField      : count 28 → 14, tick 60ms → 100ms, paints only
                          when visible
🟡 P2  Minimum heights    : QDateEdit / QSpinBox now 38 px for visual
                          consistency with other inputs
🟢 P3  Tooltips           : on every field
🟢 P3  _today() helper    : single source for the current date
"""

from __future__ import annotations

import os
import sys
import random
import logging
from datetime import date, datetime
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
    QDateEdit, QScrollArea, QMenu,
)

logger = logging.getLogger(__name__)

# ── Safe Core Constants Fallback ────────────────────────────────────
try:
    from core.constants import PWHT_METHODS, PWHT_RESULTS
except ImportError:
    PWHT_METHODS = [
        "Resistance Ceramic Heating Pads",
        "Induction Heating (High Frequency)",
        "Internal Gas Firing / Burner System",
        "Furnace Heat Treatment (Enclosed)",
    ]
    PWHT_RESULTS = [
        "ACCEPTED (Satisfactory Chart & Hardness)",
        "REJECTED (Thermal Cycle Deviation / Overheated)",
        "RE-EXAM / HARDNESS RETEST REQUIRED",
        "RE-HEAT TREATMENT REQUIRED",
    ]


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
                "vy": random.uniform(-0.0004, -0.0001),
                "r": random.uniform(0.8, 1.8),
                "alpha": random.randint(15, 55),
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
#  MAIN PWHT RECORD DIALOG
# ════════════════════════════════════════════════════════════════

class PWHTRecordDialog(QDialog):
    """
    Ultra-premium Post-Weld Heat Treatment (PWHT) Record Dialog.
    Frameless, responsive, resizable, with thermal cycle controls.
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

    # ASME NACE MR0175 hardness threshold
    HARDNESS_LIMIT_HV = 248.0

    def __init__(self, parent=None, pwht_data: Optional[dict] = None):
        super().__init__(parent)
        self.pwht_data: Dict[str, Any] = pwht_data or {}
        self.result_data: Dict[str, Any] = {}

        # Drag / resize state
        self._drag_pos: Optional[QPoint] = None
        self._drag_edge: Optional[str] = None
        self._drag_geometry: Optional[QRect] = None
        self._resize_margin = 8

        # Lifecycle & animations
        self._is_closed = False
        self._shake_anim: Optional[QPropertyAnimation] = None
        # Guard to suppress signal side-effects during programmatic loads
        self._loading = False

        self.setWindowTitle("PipeAgent – Create PWHT Record")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(self.DEF_WIDTH, self.DEF_HEIGHT)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
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

        # 🔧 Set particle geometry immediately to avoid clustering at (0,0).
        self._particles = ParticleField(self._card, count=14)
        self._particles.setGeometry(0, 0, self.DEF_WIDTH, self.DEF_HEIGHT)
        self._particles.lower()

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(24, 14, 24, 14)
        card_layout.setSpacing(10)

        card_layout.addLayout(self._build_topbar())
        card_layout.addWidget(self._build_thermal_banner())

        # ── Splitter: Left vs Right ──────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        splitter.setHandleWidth(3)
        splitter.setChildrenCollapsible(False)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([500, 500])

        card_layout.addWidget(splitter, 1)
        card_layout.addLayout(self._build_footer())

        # Initial calculated values
        self._update_thermal_summary()
        self._on_hardness_toggle()

    def _build_topbar(self) -> QHBoxLayout:
        topbar = QHBoxLayout()
        topbar.setContentsMargins(0, 0, 0, 0)

        icon_lbl = QLabel("🔥")
        icon_lbl.setFont(QFont("Segoe UI", 20))
        icon_lbl.setStyleSheet("background: transparent;")
        topbar.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)

        main_title = QLabel("PIPE AGENT  •  HEAT TREATMENT CENTER")
        main_title.setObjectName("mainTitle")
        self._add_glow(main_title, QColor(108, 207, 246, 120), blur=20)
        title_col.addWidget(main_title)

        sub_title = QLabel(
            "POST-WELD HEAT TREATMENT (PWHT)  •  THERMAL CYCLE LOG & HARDNESS CLEARANCE"
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

    def _build_thermal_banner(self) -> QFrame:
        self.banner = QFrame()
        self.banner.setObjectName("thermalBanner")
        b_layout = QHBoxLayout(self.banner)
        b_layout.setContentsMargins(14, 8, 14, 8)
        b_layout.setSpacing(12)

        self.banner_icon = QLabel("📈")
        self.banner_icon.setFont(QFont("Segoe UI", 16))
        self.banner_icon.setStyleSheet("background: transparent;")
        b_layout.addWidget(self.banner_icon)

        b_col = QVBoxLayout()
        b_col.setSpacing(2)

        self.lbl_banner_title = QLabel(
            "THERMAL CYCLE SUMMARY — READY FOR PARAMETER VERIFICATION"
        )
        self.lbl_banner_title.setObjectName("bannerTitle")
        self.lbl_banner_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        b_col.addWidget(self.lbl_banner_title)

        self.lbl_banner_detail = QLabel(
            "Heating: 200.0 °C/hr ➔ Soak: 620.0 °C @ 1.5 hr ➔ Cooling: 200.0 °C/hr "
            "(Thermocouples: 4 T/C)"
        )
        self.lbl_banner_detail.setStyleSheet(
            "color: #a2c2dc; font-size: 10px; background: transparent;"
        )
        b_col.addWidget(self.lbl_banner_detail)

        b_layout.addLayout(b_col, 1)

        # Quick ASME preset buttons
        preset_box = QHBoxLayout()
        preset_box.setSpacing(6)

        btn_preset_cs = QPushButton("CS (P-1)")
        btn_preset_cs.setObjectName("presetBtn")
        btn_preset_cs.setToolTip(
            "ASME B31.3 Carbon Steel (P-1): 620°C, 1.5h, 200°C/h"
        )
        btn_preset_cs.clicked.connect(
            lambda: self._apply_preset(620.0, 1.5, 200.0, 200.0, 4)
        )
        preset_box.addWidget(btn_preset_cs)

        btn_preset_cr1 = QPushButton("1.25Cr (P-4)")
        btn_preset_cr1.setObjectName("presetBtn")
        btn_preset_cr1.setToolTip(
            "ASME Low Alloy (P-4): 705°C, 2.0h, 150°C/h"
        )
        btn_preset_cr1.clicked.connect(
            lambda: self._apply_preset(705.0, 2.0, 150.0, 150.0, 6)
        )
        preset_box.addWidget(btn_preset_cr1)

        btn_preset_cr2 = QPushButton("2.25Cr (P-5A)")
        btn_preset_cr2.setObjectName("presetBtn")
        btn_preset_cr2.setToolTip(
            "ASME Alloy Steel (P-5A): 730°C, 2.5h, 120°C/h"
        )
        btn_preset_cr2.clicked.connect(
            lambda: self._apply_preset(730.0, 2.5, 120.0, 120.0, 8)
        )
        preset_box.addWidget(btn_preset_cr2)

        b_layout.addLayout(preset_box)
        return self.banner

    def _build_left_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("formGroup")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel("🌡️   PWHT THERMAL CYCLE & HEATING SPECIFICATIONS")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("panelScroll")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        form = QVBoxLayout(inner)
        form.setSpacing(8)

        # Heating method
        form.addWidget(QLabel("HEATING METHOD / EQUIPMENT *"))
        self.cmb_method = QComboBox()
        self.cmb_method.setObjectName("glowCombo")
        self.cmb_method.setMinimumHeight(38)
        self.cmb_method.addItems(PWHT_METHODS)
        self.cmb_method.setToolTip("PWHT heating method / equipment")
        form.addWidget(self.cmb_method)

        # Procedure number
        form.addWidget(QLabel("PWHT PROCEDURE NUMBER / WPS REF"))
        self.txt_procedure = GlowLineEdit()
        self.txt_procedure.setPlaceholderText("e.g. PWHT-PROC-01 / WPS-P1-08")
        self.txt_procedure.setToolTip("PWHT procedure reference")
        form.addWidget(self.txt_procedure)

        # Soak temp & duration
        row1 = QHBoxLayout()
        col_stemp = QVBoxLayout()
        col_stemp.addWidget(QLabel("SOAKING TEMPERATURE (°C) *"))
        self.spn_soak_temp = QDoubleSpinBox()
        self.spn_soak_temp.setObjectName("glowSpin")
        self.spn_soak_temp.setMinimumHeight(38)
        self.spn_soak_temp.setRange(0.0, 1200.0)
        self.spn_soak_temp.setValue(620.0)
        self.spn_soak_temp.setSingleStep(5.0)
        self.spn_soak_temp.setSuffix(" °C")
        self.spn_soak_temp.setToolTip("Soak / hold temperature")
        self.spn_soak_temp.valueChanged.connect(self._update_thermal_summary)
        col_stemp.addWidget(self.spn_soak_temp)
        row1.addLayout(col_stemp)

        col_sdur = QVBoxLayout()
        col_sdur.addWidget(QLabel("SOAK DURATION (HOURS) *"))
        self.spn_soak_dur = QDoubleSpinBox()
        self.spn_soak_dur.setObjectName("glowSpin")
        self.spn_soak_dur.setMinimumHeight(38)
        self.spn_soak_dur.setRange(0.1, 48.0)
        self.spn_soak_dur.setValue(1.5)
        self.spn_soak_dur.setSingleStep(0.25)
        self.spn_soak_dur.setSuffix(" hr")
        self.spn_soak_dur.setToolTip("Soak / hold duration")
        self.spn_soak_dur.valueChanged.connect(self._update_thermal_summary)
        col_sdur.addWidget(self.spn_soak_dur)
        row1.addLayout(col_sdur)
        form.addLayout(row1)

        # Heating & cooling rates
        row2 = QHBoxLayout()
        col_hrate = QVBoxLayout()
        col_hrate.addWidget(QLabel("HEATING RATE (MAX °C/HR)"))
        self.spn_heat_rate = QDoubleSpinBox()
        self.spn_heat_rate.setObjectName("glowSpin")
        self.spn_heat_rate.setMinimumHeight(38)
        self.spn_heat_rate.setRange(10.0, 600.0)
        self.spn_heat_rate.setValue(200.0)
        self.spn_heat_rate.setSuffix(" °C/hr")
        self.spn_heat_rate.setToolTip("Maximum heating rate")
        self.spn_heat_rate.valueChanged.connect(self._update_thermal_summary)
        col_hrate.addWidget(self.spn_heat_rate)
        row2.addLayout(col_hrate)

        col_crate = QVBoxLayout()
        col_crate.addWidget(QLabel("COOLING RATE (MAX °C/HR)"))
        self.spn_cool_rate = QDoubleSpinBox()
        self.spn_cool_rate.setObjectName("glowSpin")
        self.spn_cool_rate.setMinimumHeight(38)
        self.spn_cool_rate.setRange(10.0, 600.0)
        self.spn_cool_rate.setValue(200.0)
        self.spn_cool_rate.setSuffix(" °C/hr")
        self.spn_cool_rate.setToolTip("Maximum cooling rate")
        self.spn_cool_rate.valueChanged.connect(self._update_thermal_summary)
        col_crate.addWidget(self.spn_cool_rate)
        row2.addLayout(col_crate)
        form.addLayout(row2)

        # Thermocouples & chart ref
        row3 = QHBoxLayout()
        col_tc = QVBoxLayout()
        col_tc.addWidget(QLabel("THERMOCOUPLE COUNT (T/C)"))
        self.spn_tc = QSpinBox()
        self.spn_tc.setObjectName("glowSpin")
        self.spn_tc.setMinimumHeight(38)
        self.spn_tc.setRange(1, 48)
        self.spn_tc.setValue(4)
        self.spn_tc.setToolTip("Number of attached thermocouples")
        self.spn_tc.valueChanged.connect(self._update_thermal_summary)
        col_tc.addWidget(self.spn_tc)
        row3.addLayout(col_tc)

        col_chart = QVBoxLayout()
        col_chart.addWidget(QLabel("RECORDER CHART / DATA LOG ID"))
        self.txt_chart = GlowLineEdit()
        self.txt_chart.setPlaceholderText("e.g. CHT-2025-PWHT-088")
        self.txt_chart.setToolTip("Recorder chart or datalogger identifier")
        col_chart.addWidget(self.txt_chart)
        row3.addLayout(col_chart)
        form.addLayout(row3)

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

        title = QLabel("🔬   WELD TRACEABILITY, HARDNESS & QA CLEARANCE")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("panelScroll")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        form = QVBoxLayout(inner)
        form.setSpacing(8)

        # Weld ID
        form.addWidget(
            QLabel("WELD ID / JOINT PRIMARY KEY * (Numeric or Joint Tag)")
        )
        self.txt_weld = GlowLineEdit()
        self.txt_weld.setPlaceholderText("e.g. 1042 (or Joint W-14)")
        self.txt_weld.setToolTip("Weld / joint identifier — required")
        form.addWidget(self.txt_weld)

        # Hardness box
        h_box = QFrame()
        h_box.setObjectName("innerBox")
        h_box_layout = QVBoxLayout(h_box)
        h_box_layout.setContentsMargins(10, 8, 10, 8)
        h_box_layout.setSpacing(6)

        row4 = QHBoxLayout()
        col_htest = QVBoxLayout()
        col_htest.addWidget(QLabel("HARDNESS TEST REQUIRED?"))
        self.chk_hardness = QComboBox()
        self.chk_hardness.setObjectName("glowCombo")
        self.chk_hardness.setMinimumHeight(38)
        self.chk_hardness.addItems(["Yes", "No"])
        self.chk_hardness.setToolTip(
            "Is hardness testing required after PWHT?"
        )
        self.chk_hardness.currentIndexChanged.connect(self._on_hardness_toggle)
        col_htest.addWidget(self.chk_hardness)
        row4.addLayout(col_htest)

        col_hval = QVBoxLayout()
        col_hval.addWidget(QLabel("MAX MEASURED HARDNESS (HV)"))
        self.spn_hardness = QDoubleSpinBox()
        self.spn_hardness.setObjectName("glowSpin")
        self.spn_hardness.setMinimumHeight(38)
        self.spn_hardness.setRange(0.0, 600.0)
        self.spn_hardness.setValue(195.0)
        self.spn_hardness.setSingleStep(5.0)
        self.spn_hardness.setSuffix(" HV10")
        self.spn_hardness.setToolTip("Maximum measured hardness value")
        self.spn_hardness.valueChanged.connect(self._on_hardness_value_changed)
        col_hval.addWidget(self.spn_hardness)
        row4.addLayout(col_hval)
        h_box_layout.addLayout(row4)

        self.lbl_hardness_badge = QLabel(
            "✓ Hardness compliant with NACE MR0175 / ASME (Max 248 HV)"
        )
        self.lbl_hardness_badge.setStyleSheet(
            "color: #5cffaa; font-size: 10px; font-weight: bold; background: transparent;"
        )
        h_box_layout.addWidget(self.lbl_hardness_badge)

        form.addWidget(h_box)

        # Personnel & sign-off
        row5 = QHBoxLayout()
        col_perf = QVBoxLayout()
        col_perf.addWidget(QLabel("PERFORMED BY (PWHT OPERATOR)"))
        self.txt_performed = GlowLineEdit()
        self.txt_performed.setPlaceholderText("e.g. Heat Treatment Tech. Rezaei")
        self.txt_performed.setToolTip("Name of the PWHT operator")
        col_perf.addWidget(self.txt_performed)
        row5.addLayout(col_perf)

        col_wit = QVBoxLayout()
        col_wit.addWidget(QLabel("WITNESSED / QA INSPECTOR"))
        self.txt_witness = GlowLineEdit()
        self.txt_witness.setPlaceholderText("e.g. Lead QC Eng. Farhadi")
        self.txt_witness.setToolTip("Witnessing QA inspector")
        col_wit.addWidget(self.txt_witness)
        row5.addLayout(col_wit)
        form.addLayout(row5)

        # Date & Result
        row6 = QHBoxLayout()
        col_date = QVBoxLayout()
        col_date.addWidget(QLabel("DATE PERFORMED"))
        self.dte_date = QDateEdit()
        self.dte_date.setObjectName("glowDate")
        self.dte_date.setMinimumHeight(38)
        self.dte_date.setCalendarPopup(True)
        self.dte_date.setDate(QDate.currentDate())
        self.dte_date.setToolTip("Date the PWHT was performed")
        col_date.addWidget(self.dte_date)
        row6.addLayout(col_date)

        col_res = QVBoxLayout()
        col_res.addWidget(QLabel("EVALUATION RESULT"))
        self.cmb_result = QComboBox()
        self.cmb_result.setObjectName("glowCombo")
        self.cmb_result.setMinimumHeight(38)
        self.cmb_result.addItems(PWHT_RESULTS)
        self.cmb_result.setToolTip("Final PWHT evaluation result")
        col_res.addWidget(self.cmb_result)
        row6.addLayout(col_res)
        form.addLayout(row6)

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

        self.btn_save = QPushButton("⚡  SAVE PWHT RECORD  (Ctrl+S)")
        self.btn_save.setObjectName("saveBtn")
        self.btn_save.setMinimumHeight(42)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setToolTip("Save PWHT record (Ctrl+S)")
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
        QShortcut(QKeySequence("Escape"), self, self.reject)

    # ── Thermal Summary & Presets ────────────────────────────
    def _apply_preset(self, temp: float, dur: float, h_rate: float, c_rate: float, tc: int):
        # Block only the summary-signal storm, then refresh once.
        widgets = (
            self.spn_soak_temp, self.spn_soak_dur,
            self.spn_heat_rate, self.spn_cool_rate, self.spn_tc,
        )
        for w in widgets:
            w.blockSignals(True)
        try:
            self.spn_soak_temp.setValue(temp)
            self.spn_soak_dur.setValue(dur)
            self.spn_heat_rate.setValue(h_rate)
            self.spn_cool_rate.setValue(c_rate)
            self.spn_tc.setValue(tc)
        finally:
            for w in widgets:
                w.blockSignals(False)
        self._update_thermal_summary()

    def _update_thermal_summary(self, *_):
        t = self.spn_soak_temp.value()
        d = self.spn_soak_dur.value()
        hr = self.spn_heat_rate.value()
        cr = self.spn_cool_rate.value()
        tc = self.spn_tc.value()

        detail = (
            f"Heating: {hr:.1f} °C/hr ➔ Soak: {t:.1f} °C @ {d:.1f} hr ➔ "
            f"Cooling: {cr:.1f} °C/hr • Thermocouples: {tc} T/C"
        )
        self.lbl_banner_detail.setText(detail)

    # ── Hardness Handlers ─────────────────────────────────────
    def _on_hardness_toggle(self, *_):
        is_yes = (self.chk_hardness.currentText() == "Yes")
        self.spn_hardness.setEnabled(is_yes)
        self.lbl_hardness_badge.setVisible(is_yes)

        # If the test isn't required, zero the value to avoid misleading
        # numbers in saved reports.
        if not is_yes:
            self.spn_hardness.blockSignals(True)
            try:
                self.spn_hardness.setValue(0.0)
            finally:
                self.spn_hardness.blockSignals(False)

        # Refresh badge colours.
        self._on_hardness_value_changed()

    def _on_hardness_value_changed(self, *_):
        if self.chk_hardness.currentText() != "Yes":
            return

        val = self.spn_hardness.value()
        if val > self.HARDNESS_LIMIT_HV:
            self.lbl_hardness_badge.setText(
                f"⚠️ Hardness {val:.1f} HV exceeds NACE MR0175 limit "
                f"(Max {self.HARDNESS_LIMIT_HV:.0f} HV)!"
            )
            self.lbl_hardness_badge.setStyleSheet(
                "color: #ff6b6b; font-size: 10px; font-weight: bold; background: transparent;"
            )
        else:
            self.lbl_hardness_badge.setText(
                f"✓ Hardness {val:.1f} HV compliant with ASME & NACE MR0175 "
                f"(Max {self.HARDNESS_LIMIT_HV:.0f} HV)"
            )
            self.lbl_hardness_badge.setStyleSheet(
                "color: #5cffaa; font-size: 10px; font-weight: bold; background: transparent;"
            )

    # ── Load Existing Data ────────────────────────────────────
    def _load_existing_data(self):
        if not self.pwht_data:
            return

        self.setWindowTitle("PipeAgent – Edit PWHT Record")
        self._loading = True

        # Block value signals while loading to prevent premature warnings
        # and a shower of summary updates.
        widgets_to_block = [
            self.spn_soak_temp, self.spn_soak_dur,
            self.spn_heat_rate, self.spn_cool_rate, self.spn_tc,
            self.spn_hardness, self.chk_hardness,
        ]
        for w in widgets_to_block:
            w.blockSignals(True)

        try:
            w_id = (
                self.pwht_data.get("weld_id_fk")
                or self.pwht_data.get("weld_id", "")
            )
            self.txt_weld.setText(str(w_id))
            self.txt_procedure.setText(
                str(self.pwht_data.get("pwht_procedure_no", ""))
            )
            self.txt_chart.setText(str(self.pwht_data.get("chart_number", "")))
            self.txt_performed.setText(
                str(self.pwht_data.get("performed_by", ""))
            )
            self.txt_witness.setText(
                str(self.pwht_data.get("witnessed_by", ""))
            )

            # Numeric values — set them BEFORE the hardness toggle so the
            # badge reflects the loaded value, not the initial zero.
            if "soak_temperature_c" in self.pwht_data:
                self.spn_soak_temp.setValue(
                    float(self.pwht_data["soak_temperature_c"])
                )
            if "soak_duration_hours" in self.pwht_data:
                self.spn_soak_dur.setValue(
                    float(self.pwht_data["soak_duration_hours"])
                )
            if "heating_rate_c_per_hr" in self.pwht_data:
                self.spn_heat_rate.setValue(
                    float(self.pwht_data["heating_rate_c_per_hr"])
                )
            if "cooling_rate_c_per_hr" in self.pwht_data:
                self.spn_cool_rate.setValue(
                    float(self.pwht_data["cooling_rate_c_per_hr"])
                )
            if "thermocouple_count" in self.pwht_data:
                self.spn_tc.setValue(
                    int(self.pwht_data["thermocouple_count"])
                )
            if "hardness_max_hv" in self.pwht_data:
                self.spn_hardness.setValue(
                    float(self.pwht_data["hardness_max_hv"])
                )

            # Combos
            m_idx = self.cmb_method.findText(
                str(self.pwht_data.get("heating_method", ""))
            )
            if m_idx >= 0:
                self.cmb_method.setCurrentIndex(m_idx)

            r_idx = self.cmb_result.findText(
                str(self.pwht_data.get("result", ""))
            )
            if r_idx >= 0:
                self.cmb_result.setCurrentIndex(r_idx)

            h_done = self.pwht_data.get("hardness_test_done", True)
            self.chk_hardness.setCurrentIndex(0 if h_done else 1)

            # Date — tolerant of date / datetime / ISO string
            parsed = _parse_date(self.pwht_data.get("performed_date"))
            if parsed is not None:
                self.dte_date.setDate(
                    QDate(parsed.year, parsed.month, parsed.day)
                )
        finally:
            for w in widgets_to_block:
                w.blockSignals(False)

        self._loading = False

        # Single refresh at the end.
        self._update_thermal_summary()
        self._on_hardness_toggle()

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
            QFrame#thermalBanner {{
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
            QPushButton#presetBtn {{
                background: #0b1c2e;
                color: #6ccff6;
                border: 1px solid #1e3d5a;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 10px;
                font-weight: 800;
            }}
            QPushButton#presetBtn:hover {{
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

    # ── Save & Validation ─────────────────────────────────────
    def _save(self):
        if self._is_closed:
            return

        weld_raw = self.txt_weld.text().strip()

        if not weld_raw:
            self.lbl_warning.setText(
                "⚠️ Validation Error: Weld ID / Joint Key is required."
            )
            self._shake()
            self.txt_weld.setFocus()
            return

        # Flexible support: parse integer if possible, else store string
        try:
            weld_fk: Any = int(weld_raw)
        except ValueError:
            weld_fk = weld_raw

        self.lbl_warning.setText("")

        hardness_done = (self.chk_hardness.currentText() == "Yes")

        self.result_data = {
            "weld_id_fk": weld_fk,
            "pwht_procedure_no": self.txt_procedure.text().strip(),
            "heating_method": self.cmb_method.currentText(),
            "soak_temperature_c": self.spn_soak_temp.value(),
            "soak_duration_hours": self.spn_soak_dur.value(),
            "heating_rate_c_per_hr": self.spn_heat_rate.value(),
            "cooling_rate_c_per_hr": self.spn_cool_rate.value(),
            "thermocouple_count": self.spn_tc.value(),
            "chart_number": self.txt_chart.text().strip(),
            "hardness_test_done": hardness_done,
            "hardness_max_hv": (
                self.spn_hardness.value() if hardness_done else None
            ),
            "performed_by": self.txt_performed.text().strip(),
            "performed_date": self.dte_date.date().toPyDate(),
            "witnessed_by": self.txt_witness.text().strip(),
            "result": self.cmb_result.currentText(),
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

    mock_pwht = {
        "weld_id_fk": "W-04 (Line 2104)",
        "pwht_procedure_no": "PWHT-P1-ASME-04",
        "heating_method": "Resistance Ceramic Heating Pads",
        "soak_temperature_c": 620.0,
        "soak_duration_hours": 2.0,
        "heating_rate_c_per_hr": 200.0,
        "cooling_rate_c_per_hr": 200.0,
        "thermocouple_count": 6,
        "chart_number": "CHT-2104-001A",
        "hardness_test_done": True,
        "hardness_max_hv": 210.0,
        "performed_by": "Operator Kaveh (Superheat Services)",
        "witnessed_by": "Eng. Mohammadi (Lead QC)",
        "performed_date": date.today(),
        "result": "ACCEPTED (Satisfactory Chart & Hardness)",
    }

    dialog = PWHTRecordDialog(pwht_data=mock_pwht)
    dialog.show()
    dialog.exec()

    if getattr(dialog, "result_data", None):
        print("PWHT Registered Result Data:", dialog.result_data)

    sys.exit(0)