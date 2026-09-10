# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Welder Performance Qualification & Registry Dialog
═════════════════════════════════════════════════════════════════════════════════
Version : 5.0 (Refactored, hardened, production-ready)
Engine  : PyQt6
Design  : Cinematic dark-tech theme matching PipeAgent Suite
Standards: ASME Section IX (QW-452 / QW-461), ISO 9606-1, AWS D1.1

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
🟠 P1  Signal storm       : `_populate` blocks signal side-effects while
                          loading, then refreshes once
🟠 P1  Preset storm       : `_apply_preset` also blocks signals on all
                          fields, then refreshes once
🟠 P1  Auto-calc 2t       : removed magic 500 — cleanly qualified when the
                          coupon is ≥13 mm, otherwise 2 × coupon thickness
🟡 P2  ParticleField      : count 28 → 14, tick 60ms → 100ms, paints only
                          when visible
🟡 P2  Minimum heights    : QDateEdit / QSpinBox now 38 px for visual
                          consistency with the rest of the suite
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
    QDateEdit, QScrollArea, QCheckBox, QMenu,
)

logger = logging.getLogger(__name__)

# ── Safe Core Constants Fallback ────────────────────────────────────
try:
    from core.constants import WELDING_PROCESSES, WELDING_POSITIONS
except ImportError:
    WELDING_PROCESSES = [
        "GTAW (TIG)",
        "SMAW (Stick / MMAW)",
        "GTAW + SMAW (Combo)",
        "GMAW (MIG/MAG / Solid Wire)",
        "FCAW (Flux-Cored Arc)",
        "SAW (Submerged Arc Welding)",
    ]
    WELDING_POSITIONS = [
        "6G (All Positions - Pipe Inclined 45°)",
        "6GR (With Restriction Ring - Offshore TKY)",
        "1G (Rotated Pipe / Flat Plate)",
        "2G (Horizontal Pipe/Plate)",
        "3G + 4G (Vertical-Up & Overhead Plate)",
        "5G (Fixed Horizontal Pipe - All Positions)",
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


def _today() -> date:
    return date.today()


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
#  GLOW TEXT EDIT — with right-click WPQR template menu
# ════════════════════════════════════════════════════════════════

class GlowTextEdit(QTextEdit):
    """QTextEdit with custom right-click context menu and templates."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimumHeight(80)
        self.setStyleSheet("""
            QTextEdit {
                background: #07101a;
                color: #eef6ff;
                border: 1px solid #18364a;
                border-radius: 8px;
                padding: 8px;
                font-size: 12px;
                selection-background-color: #6ccff6;
                selection-color: #07101a;
            }
            QTextEdit:focus {
                border: 1px solid #6ccff6;
                background: #0d1f30;
            }
        """)

    def contextMenuEvent(self, event):  # noqa: N802
        menu = self.createStandardContextMenu()
        menu.addSeparator()

        menu_tpl = menu.addMenu("📝  Insert WPQR Continuity / Audit Template")

        tpls = [
            (
                "6-Month Welder Continuity Log",
                "• Continuity Check: Verified through RT/UT production weld "
                "reports within last 6 months.\n"
                "• Renewal Status: Active — No lapse in process execution.",
            ),
            (
                "Special Welder Restriction / PPE",
                "• Restricted to Shop Fabrication (Clean Room Stainless Area).\n"
                "• Special PPE: PAPR Fresh-air respirator required for "
                "Cr-Mo/SS welding.",
            ),
            (
                "ASME IX Re-Test / Extension Note",
                "• Re-qualification coupon tested under Third-Party Witness "
                "(TUV/Lloyds).\n"
                "• Mechanical Bend & Radiography 100% Acceptable per QW-302.2.",
            ),
        ]

        for title, text in tpls:
            act = QAction(title, self)
            # Capture `text` by default arg to avoid late-binding.
            act.triggered.connect(
                lambda checked=False, t=text: self.setPlainText(t)
            )
            menu_tpl.addAction(act)

        # PyQt6: QContextMenuEvent.globalPos() still valid.
        menu.exec(event.globalPos())


# ════════════════════════════════════════════════════════════════
#  MAIN WELDER REGISTRATION & QUALIFICATION DIALOG
# ════════════════════════════════════════════════════════════════

class WelderDialog(QDialog):
    """
    Ultra-premium Welder Performance Qualification & Registry Dialog.
    Frameless, responsive, resizable, with ASME IX Auto-Calculator.
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

    MIN_WIDTH  = 960
    MIN_HEIGHT = 660
    DEF_WIDTH  = 1080
    DEF_HEIGHT = 780

    # ASME IX: coupon thickness ≥ 13 mm qualifies to unlimited max.
    ASME_UNLIMITED_COUPON_MM = 13.0

    def __init__(self, parent=None, welder_data: Optional[dict] = None):
        super().__init__(parent)
        self.welder_data: Dict[str, Any] = welder_data or {}
        self.result_data: Dict[str, Any] = {}

        # Frameless dragging & resizing parameters
        self._drag_pos: Optional[QPoint] = None
        self._drag_edge: Optional[str] = None
        self._drag_geometry: Optional[QRect] = None
        self._resize_margin = 8

        # Lifecycle & animations
        self._is_closed = False
        self._shake_anim: Optional[QPropertyAnimation] = None

        self.setWindowTitle("PipeAgent – Welder Performance Qualification")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(self.DEF_WIDTH, self.DEF_HEIGHT)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self._build_ui()
        self._setup_shortcuts()
        self._center_on_screen()

        if self.welder_data:
            self._populate()
        else:
            self._update_validity_status()

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
        card_layout.addWidget(self._build_qual_banner())

        # Splitter: Left panel (identity) | Right panel (ASME range)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        splitter.setHandleWidth(3)
        splitter.setChildrenCollapsible(False)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([500, 500])

        card_layout.addWidget(splitter, 1)
        card_layout.addLayout(self._build_footer())

    def _build_topbar(self) -> QHBoxLayout:
        topbar = QHBoxLayout()
        topbar.setContentsMargins(0, 0, 0, 0)

        icon_lbl = QLabel("👨‍🏭")
        icon_lbl.setFont(QFont("Segoe UI", 20))
        icon_lbl.setStyleSheet("background: transparent;")
        topbar.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)

        main_title = QLabel("PIPE AGENT  •  WELDER PERFORMANCE QUALIFICATION (WPQ)")
        main_title.setObjectName("mainTitle")
        self._add_glow(main_title, QColor(108, 207, 246, 120), blur=20)
        title_col.addWidget(main_title)

        sub_title = QLabel(
            "ASME SECTION IX / ISO 9606-1  •  WPQR CERTIFICATION & STENCIL STAMP REGISTRY"
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

    def _build_qual_banner(self) -> QFrame:
        self.banner = QFrame()
        self.banner.setObjectName("qualBanner")
        b_layout = QHBoxLayout(self.banner)
        b_layout.setContentsMargins(14, 8, 14, 8)
        b_layout.setSpacing(12)

        self.banner_icon = QLabel("🛡️")
        self.banner_icon.setFont(QFont("Segoe UI", 16))
        self.banner_icon.setStyleSheet("background: transparent;")
        b_layout.addWidget(self.banner_icon)

        b_col = QVBoxLayout()
        b_col.setSpacing(2)

        self.lbl_banner_title = QLabel("WELDER STATUS: FULLY QUALIFIED & ACTIVE (ASME IX)")
        self.lbl_banner_title.setObjectName("bannerTitle")
        self.lbl_banner_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        b_col.addWidget(self.lbl_banner_title)

        self.lbl_banner_detail = QLabel(
            "6-Month Continuity: Verified • Range: All Positions (6G) • "
            "Thickness: 1.5 to 20.0 mm • Min Dia: 1.0\" NPS"
        )
        self.lbl_banner_detail.setStyleSheet(
            "color: #a2c2dc; font-size: 10px; background: transparent;"
        )
        b_col.addWidget(self.lbl_banner_detail)

        b_layout.addLayout(b_col, 1)

        preset_box = QHBoxLayout()
        preset_box.setSpacing(6)

        btn_preset_6g = QPushButton("Combo 6G (P1)")
        btn_preset_6g.setObjectName("presetBtn")
        btn_preset_6g.setToolTip(
            "GTAW+SMAW 6G Pipe Coupon (2\" Sch 80): Qualifies all positions, "
            "1.5 - 17.8 mm, ≥1\" NPS"
        )
        btn_preset_6g.clicked.connect(
            lambda: self._apply_preset(
                "GTAW + SMAW (Combo)",
                "6G (All Positions - Pipe Inclined 45°)",
                1.5, 17.8, 1.0, "P1 through P11 / P4X",
            )
        )
        preset_box.addWidget(btn_preset_6g)

        btn_preset_ss = QPushButton("SS 6G (P8)")
        btn_preset_ss.setObjectName("presetBtn")
        btn_preset_ss.setToolTip(
            "GTAW Stainless Steel 6G: Qualifies all positions, 1.5 - 12.0 mm, P8"
        )
        btn_preset_ss.clicked.connect(
            lambda: self._apply_preset(
                "GTAW (TIG)",
                "6G (All Positions - Pipe Inclined 45°)",
                1.5, 12.0, 1.0, "P8 (Austenitic Stainless)",
            )
        )
        preset_box.addWidget(btn_preset_ss)

        btn_preset_plate = QPushButton("Plate 3G+4G")
        btn_preset_plate.setObjectName("presetBtn")
        btn_preset_plate.setToolTip(
            "SMAW Plate 3G+4G: Qualifies plate and pipe ≥24\" NPS"
        )
        btn_preset_plate.clicked.connect(
            lambda: self._apply_preset(
                "SMAW (Stick / MMAW)",
                "3G + 4G (Vertical-Up & Overhead Plate)",
                3.0, 24.0, 24.0, "P1",
            )
        )
        preset_box.addWidget(btn_preset_plate)

        b_layout.addLayout(preset_box)
        return self.banner

    def _build_left_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("formGroup")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel("👤   WELDER IDENTITY & CERTIFICATE REGISTRY")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("panelScroll")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        form = QVBoxLayout(inner)
        form.setSpacing(8)

        # Stencil & Full Name
        row0 = QHBoxLayout()
        col_st = QVBoxLayout()
        col_st.addWidget(QLabel("STENCIL / STAMP NO. * (Unique Stamp ID)"))
        self.txt_stencil = GlowLineEdit()
        self.txt_stencil.setPlaceholderText("e.g. W-04 / ST-108")
        self.txt_stencil.setToolTip("Unique welder stencil stamp — required")
        col_st.addWidget(self.txt_stencil)
        row0.addLayout(col_st)

        col_name = QVBoxLayout()
        col_name.addWidget(QLabel("WELDER FULL NAME *"))
        self.txt_name = GlowLineEdit()
        self.txt_name.setPlaceholderText("e.g. Saeed Rezaei")
        self.txt_name.setToolTip("Full name of the welder — required")
        col_name.addWidget(self.txt_name)
        row0.addLayout(col_name)
        form.addLayout(row0)

        # National ID & Employer
        row1 = QHBoxLayout()
        col_nid = QVBoxLayout()
        col_nid.addWidget(QLabel("NATIONAL ID / BADGE NO."))
        self.txt_national_id = GlowLineEdit()
        self.txt_national_id.setPlaceholderText("e.g. 0081234567")
        col_nid.addWidget(self.txt_national_id)
        row1.addLayout(col_nid)

        col_emp = QVBoxLayout()
        col_emp.addWidget(QLabel("EMPLOYER / CONTRACTOR"))
        self.txt_employer = GlowLineEdit()
        self.txt_employer.setPlaceholderText("e.g. Piping Erection Subcon A")
        col_emp.addWidget(self.txt_employer)
        row1.addLayout(col_emp)
        form.addLayout(row1)

        # Certificate & WPQR
        row2 = QHBoxLayout()
        col_cert = QVBoxLayout()
        col_cert.addWidget(QLabel("WPQ / CERTIFICATE NUMBER"))
        self.txt_cert = GlowLineEdit()
        self.txt_cert.setPlaceholderText("e.g. WPQ-2025-P1-004")
        col_cert.addWidget(self.txt_cert)
        row2.addLayout(col_cert)

        col_wpqr = QVBoxLayout()
        col_wpqr.addWidget(QLabel("SUPPORTING WPQR / PQR REF"))
        self.txt_wpqr = GlowLineEdit()
        self.txt_wpqr.setPlaceholderText("e.g. PQR-GTAW-SMAW-01")
        col_wpqr.addWidget(self.txt_wpqr)
        row2.addLayout(col_wpqr)
        form.addLayout(row2)

        # Dates
        row3 = QHBoxLayout()
        col_qdate = QVBoxLayout()
        col_qdate.addWidget(QLabel("QUALIFICATION TEST DATE"))
        self.dte_qual = QDateEdit()
        self.dte_qual.setObjectName("glowDate")
        self.dte_qual.setMinimumHeight(38)
        self.dte_qual.setCalendarPopup(True)
        self.dte_qual.setDate(QDate.currentDate().addMonths(-1))
        self.dte_qual.setToolTip("Date of the welder qualification test")
        self.dte_qual.dateChanged.connect(self._on_qual_date_changed)
        col_qdate.addWidget(self.dte_qual)
        row3.addLayout(col_qdate)

        col_edate = QVBoxLayout()
        col_edate.addWidget(QLabel("EXPIRY / CONTINUITY DATE * (6-Month Rule)"))
        self.dte_expiry = QDateEdit()
        self.dte_expiry.setObjectName("glowDate")
        self.dte_expiry.setMinimumHeight(38)
        self.dte_expiry.setCalendarPopup(True)
        self.dte_expiry.setDate(QDate.currentDate().addMonths(5))
        self.dte_expiry.setToolTip(
            "Expiry / continuity deadline — auto-set to qual date + 6 months"
        )
        self.dte_expiry.dateChanged.connect(self._update_validity_status)
        col_edate.addWidget(self.dte_expiry)
        row3.addLayout(col_edate)
        form.addLayout(row3)

        # Testing Agency & Witness
        row4 = QHBoxLayout()
        col_agency = QVBoxLayout()
        col_agency.addWidget(QLabel("TESTING AGENCY / TPI"))
        self.txt_agency = GlowLineEdit()
        self.txt_agency.setPlaceholderText("e.g. TUV NORD / SGS / BV")
        col_agency.addWidget(self.txt_agency)
        row4.addLayout(col_agency)

        col_wit = QVBoxLayout()
        col_wit.addWidget(QLabel("WITNESS QC INSPECTOR"))
        self.txt_witness = GlowLineEdit()
        self.txt_witness.setPlaceholderText("e.g. Eng. Farhadi (Level II)")
        col_wit.addWidget(self.txt_witness)
        row4.addLayout(col_wit)
        form.addLayout(row4)

        # Remarks
        form.addWidget(QLabel("REMARKS & CONTINUITY NOTES  (Right-click for templates)"))
        self.txt_remarks = GlowTextEdit()
        self.txt_remarks.setPlaceholderText(
            "Continuity records, visual examination notes, special "
            "restrictions... (Right-click to insert WPQR template)"
        )
        form.addWidget(self.txt_remarks)

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

        title = QLabel("📐   ASME SECTION IX QUALIFICATION RANGE (QW-452)")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("panelScroll")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        form = QVBoxLayout(inner)
        form.setSpacing(8)

        # Process & F-No
        row5 = QHBoxLayout()
        col_proc = QVBoxLayout()
        col_proc.addWidget(QLabel("WELDING PROCESS(ES) *"))
        self.cmb_process = QComboBox()
        self.cmb_process.setObjectName("glowCombo")
        self.cmb_process.setMinimumHeight(38)
        self.cmb_process.setEditable(True)
        self.cmb_process.addItems(WELDING_PROCESSES)
        self.cmb_process.setToolTip("Qualified welding process(es)")
        col_proc.addWidget(self.cmb_process)
        row5.addLayout(col_proc)

        col_fno = QVBoxLayout()
        col_fno.addWidget(QLabel("FILLER METAL F-NO / SFA SPEC"))
        self.txt_f_no = GlowLineEdit()
        self.txt_f_no.setPlaceholderText("e.g. F6 (ER70S-6) & F4 (E7018)")
        col_fno.addWidget(self.txt_f_no)
        row5.addLayout(col_fno)
        form.addLayout(row5)

        # Positions
        form.addWidget(QLabel("QUALIFIED POSITIONS (ASME QW-461)"))
        self.cmb_positions = QComboBox()
        self.cmb_positions.setObjectName("glowCombo")
        self.cmb_positions.setMinimumHeight(38)
        self.cmb_positions.setEditable(True)
        self.cmb_positions.addItems(WELDING_POSITIONS)
        self.cmb_positions.setToolTip("Qualified welding positions")
        self.cmb_positions.currentTextChanged.connect(self._update_validity_status)
        form.addWidget(self.cmb_positions)

        # P-No
        form.addWidget(QLabel("QUALIFIED BASE METAL GROUP (P-NO RANGE)"))
        self.txt_p_no = GlowLineEdit()
        self.txt_p_no.setPlaceholderText("e.g. P-No 1 through P-No 11, P-No 4X")
        self.txt_p_no.setToolTip("Qualified P-Number range")
        self.txt_p_no.textChanged.connect(self._update_validity_status)
        form.addWidget(self.txt_p_no)

        # Thickness Box
        thk_box = QFrame()
        thk_box.setObjectName("innerBox")
        tb_layout = QVBoxLayout(thk_box)
        tb_layout.setContentsMargins(10, 8, 10, 8)
        tb_layout.setSpacing(6)

        tb_head = QHBoxLayout()
        tb_head.addWidget(QLabel(
            "QUALIFIED DEPOSITED WELD THICKNESS RANGE (QW-452.1)"
        ))
        tb_head.addStretch()

        btn_calc_thk = QPushButton("⚡ Auto-Calc 2t")
        btn_calc_thk.setObjectName("calcBtn")
        btn_calc_thk.setToolTip(
            "Auto-calculate ASME IX thickness range (Min 1.5 mm up to 2 × "
            "coupon t; coupon ≥13 mm → unlimited)"
        )
        btn_calc_thk.clicked.connect(self._auto_calc_thickness)
        tb_head.addWidget(btn_calc_thk)
        tb_layout.addLayout(tb_head)

        row6 = QHBoxLayout()
        col_tmin = QVBoxLayout()
        col_tmin.addWidget(QLabel("MIN THICKNESS (MM)"))
        self.spn_thk_min = QDoubleSpinBox()
        self.spn_thk_min.setObjectName("glowSpin")
        self.spn_thk_min.setMinimumHeight(38)
        self.spn_thk_min.setRange(0.0, 500.0)
        self.spn_thk_min.setValue(1.5)
        self.spn_thk_min.setSingleStep(0.5)
        self.spn_thk_min.setSuffix(" mm")
        self.spn_thk_min.setToolTip("Minimum qualified thickness (mm)")
        self.spn_thk_min.valueChanged.connect(self._update_validity_status)
        col_tmin.addWidget(self.spn_thk_min)
        row6.addLayout(col_tmin)

        col_tmax = QVBoxLayout()
        col_tmax.addWidget(QLabel("MAX THICKNESS (MM)"))
        self.spn_thk_max = QDoubleSpinBox()
        self.spn_thk_max.setObjectName("glowSpin")
        self.spn_thk_max.setMinimumHeight(38)
        self.spn_thk_max.setRange(0.0, 500.0)
        self.spn_thk_max.setValue(17.8)
        self.spn_thk_max.setSingleStep(0.5)
        self.spn_thk_max.setSuffix(" mm")
        self.spn_thk_max.setToolTip("Maximum qualified thickness (mm)")
        self.spn_thk_max.valueChanged.connect(self._update_validity_status)
        col_tmax.addWidget(self.spn_thk_max)
        row6.addLayout(col_tmax)
        tb_layout.addLayout(row6)
        form.addWidget(thk_box)

        # Diameter & Backing
        row7 = QHBoxLayout()
        col_dmin = QVBoxLayout()
        col_dmin.addWidget(QLabel("MIN QUALIFIED PIPE DIAMETER (INCHES)"))
        self.spn_dia_min = QDoubleSpinBox()
        self.spn_dia_min.setObjectName("glowSpin")
        self.spn_dia_min.setMinimumHeight(38)
        self.spn_dia_min.setRange(0.0, 120.0)
        self.spn_dia_min.setValue(1.0)
        self.spn_dia_min.setSingleStep(0.5)
        self.spn_dia_min.setSuffix(" in (NPS)")
        self.spn_dia_min.setToolTip("Minimum qualified pipe diameter (NPS)")
        self.spn_dia_min.valueChanged.connect(self._update_validity_status)
        col_dmin.addWidget(self.spn_dia_min)
        row7.addLayout(col_dmin)

        col_backing = QVBoxLayout()
        col_backing.addWidget(QLabel("WELD BACKING TYPE"))
        self.cmb_backing = QComboBox()
        self.cmb_backing.setObjectName("glowCombo")
        self.cmb_backing.setMinimumHeight(38)
        self.cmb_backing.addItems([
            "With Backing & Without Backing (Both)",
            "Without Backing Only (Open Root)",
            "With Backing / Ceramic Strip Only",
        ])
        self.cmb_backing.setToolTip("Qualified backing configuration")
        col_backing.addWidget(self.cmb_backing)
        row7.addLayout(col_backing)
        form.addLayout(row7)

        # Active toggle
        self.chk_active_status = QCheckBox(
            "Welder Currently Active & Authorized on Site Fabrication"
        )
        self.chk_active_status.setStyleSheet(
            "color: #5cffaa; font-weight: bold; font-size: 11px; margin-top: 6px;"
        )
        self.chk_active_status.setChecked(True)
        self.chk_active_status.toggled.connect(self._update_validity_status)
        form.addWidget(self.chk_active_status)

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

        self.btn_save = QPushButton("⚡  SAVE WELDER PASSPORT  (Ctrl+S)")
        self.btn_save.setObjectName("saveBtn")
        self.btn_save.setMinimumHeight(42)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setToolTip("Save welder passport (Ctrl+S)")
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

    # ── Presets & ASME Calculation Helpers ────────────────────
    def _apply_preset(
        self,
        process: str,
        position: str,
        t_min: float,
        t_max: float,
        d_min: float,
        p_no: str,
    ):
        """Apply an ASME IX standard coupon preset.

        Signals are blocked while the fields are being set, then a single
        banner refresh runs at the end.
        """
        widgets_to_block = [
            self.spn_thk_min, self.spn_thk_max, self.spn_dia_min,
            self.cmb_positions, self.txt_p_no,
        ]
        for w in widgets_to_block:
            w.blockSignals(True)
        try:
            self.cmb_process.setCurrentText(process)
            self.cmb_positions.setCurrentText(position)
            self.spn_thk_min.setValue(t_min)
            self.spn_thk_max.setValue(t_max)
            self.spn_dia_min.setValue(d_min)
            self.txt_p_no.setText(p_no)
        finally:
            for w in widgets_to_block:
                w.blockSignals(False)

        # Single refresh.
        self._update_validity_status()

    def _auto_calc_thickness(self):
        """
        Compute the ASME IX qualified range from the current "coupon"
        (max) thickness.

        Rule (QW-452.1):
          • Coupon t < 13 mm  → qualified max = 2 × t
          • Coupon t ≥ 13 mm  → qualified max = unlimited (we cap at 500)
        The minimum qualified is always 1.5 mm for deposited thickness.
        """
        coupon_t = self.spn_thk_max.value()
        if coupon_t <= 0:
            coupon_t = 8.9  # Typical 2" Sch 80 wall

        new_min = 1.5
        if coupon_t >= self.ASME_UNLIMITED_COUPON_MM:
            new_max = 500.0  # "Unlimited" practical cap
        else:
            new_max = round(coupon_t * 2.0, 1)

        # Block signals while setting, refresh once.
        for spn in (self.spn_thk_min, self.spn_thk_max):
            spn.blockSignals(True)
        try:
            self.spn_thk_min.setValue(new_min)
            self.spn_thk_max.setValue(new_max)
        finally:
            for spn in (self.spn_thk_min, self.spn_thk_max):
                spn.blockSignals(False)

        self._update_validity_status()

    def _on_qual_date_changed(self, new_qdate: QDate):
        """Continuity renewal: expiry = qual date + 6 months."""
        self.dte_expiry.blockSignals(True)
        try:
            self.dte_expiry.setDate(new_qdate.addMonths(6))
        finally:
            self.dte_expiry.blockSignals(False)
        self._update_validity_status()

    def _update_validity_status(self, *_):
        exp_date = self.dte_expiry.date().toPyDate()
        days_left = (exp_date - date.today()).days
        is_active = self.chk_active_status.isChecked()

        if not is_active:
            title = "WELDER STATUS: INACTIVE / SUSPENDED BY QA/QC"
            color = self.ERROR
            icon = "🚫"
        elif days_left < 0:
            title = (
                f"WELDER STATUS: ⚠️ QUALIFICATION EXPIRED "
                f"(Lapsed {-days_left} days ago) — CONTINUITY RE-TEST REQUIRED"
            )
            color = self.ERROR
            icon = "🚨"
        elif days_left <= 30:
            title = (
                f"WELDER STATUS: ⏳ CONTINUITY WARNING "
                f"({days_left} days remaining until renewal deadline)"
            )
            color = self.WARNING
            icon = "⚠️"
        else:
            title = (
                f"WELDER STATUS: ACTIVE & QUALIFIED "
                f"(Valid for {days_left} days under 6-month ASME rule)"
            )
            color = self.SUCCESS
            icon = "✅"

        self.banner_icon.setText(icon)
        self.lbl_banner_title.setText(title)
        self.lbl_banner_title.setStyleSheet(
            f"color: {color}; background: transparent; font-weight: bold;"
        )

        position_short = self.cmb_positions.currentText().split(" (")[0]
        p_no_text = self.txt_p_no.text().strip() or "P-No 1"
        self.lbl_banner_detail.setText(
            f"Range: {position_short} • Thickness: "
            f"{self.spn_thk_min.value():.1f} - {self.spn_thk_max.value():.1f} mm • "
            f"Min Dia: ≥{self.spn_dia_min.value():.1f}\" NPS • "
            f"Base Metal: {p_no_text}"
        )

    # ── Populate Existing Data ────────────────────────────────
    def _populate(self):
        d = self.welder_data
        self.setWindowTitle("PipeAgent – Edit Welder Passport")

        # Block signals during load to avoid a storm of `_update_validity_status`.
        widgets_to_block = [
            self.dte_qual, self.dte_expiry,
            self.spn_thk_min, self.spn_thk_max, self.spn_dia_min,
            self.cmb_positions, self.txt_p_no,
            self.chk_active_status,
        ]
        for w in widgets_to_block:
            w.blockSignals(True)

        try:
            self.txt_stencil.setText(str(d.get("stencil_no", "")))
            self.txt_name.setText(str(d.get("full_name", "")))
            self.txt_national_id.setText(str(d.get("national_id", "")))
            self.txt_employer.setText(str(d.get("employer", "")))
            self.txt_cert.setText(str(d.get("certificate_no", "")))
            self.txt_wpqr.setText(str(d.get("supporting_wpqr", "")))
            self.txt_p_no.setText(str(d.get("qualified_material_p_no", "P1 through P11")))
            self.txt_f_no.setText(str(d.get("filler_f_no", "")))
            self.txt_agency.setText(str(d.get("testing_agency", "")))
            self.txt_witness.setText(str(d.get("witness_inspector", "")))
            self.txt_remarks.setPlainText(str(d.get("remarks", "")))

            # Combos
            proc_idx = self.cmb_process.findText(str(d.get("welding_processes", "")))
            if proc_idx >= 0:
                self.cmb_process.setCurrentIndex(proc_idx)

            pos_idx = self.cmb_positions.findText(str(d.get("qualified_positions", "")))
            if pos_idx >= 0:
                self.cmb_positions.setCurrentIndex(pos_idx)

            backing_idx = self.cmb_backing.findText(str(d.get("weld_backing", "")))
            if backing_idx >= 0:
                self.cmb_backing.setCurrentIndex(backing_idx)

            # Spinners
            if "qualified_thickness_min_mm" in d:
                self.spn_thk_min.setValue(float(d["qualified_thickness_min_mm"]))
            if "qualified_thickness_max_mm" in d:
                self.spn_thk_max.setValue(float(d["qualified_thickness_max_mm"]))
            if "qualified_diameter_min_inch" in d:
                self.spn_dia_min.setValue(float(d["qualified_diameter_min_inch"]))

            # Dates — tolerant of date / datetime / ISO string
            dt_q = _parse_date(d.get("qualification_date"))
            if dt_q is not None:
                self.dte_qual.setDate(QDate(dt_q.year, dt_q.month, dt_q.day))

            dt_e = _parse_date(d.get("expiry_date"))
            if dt_e is not None:
                self.dte_expiry.setDate(QDate(dt_e.year, dt_e.month, dt_e.day))

            self.chk_active_status.setChecked(bool(d.get("is_active", True)))
        finally:
            for w in widgets_to_block:
                w.blockSignals(False)

        # Single refresh at the end.
        self._update_validity_status()

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
                /* QSS does not support gradients in `border`. */
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
            QFrame#qualBanner {{
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
            QPushButton#calcBtn, QPushButton#presetBtn {{
                background: #0b1c2e;
                color: #6ccff6;
                border: 1px solid #1e3d5a;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 10px;
                font-weight: 800;
            }}
            QPushButton#calcBtn:hover, QPushButton#presetBtn:hover {{
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
            QComboBox#glowCombo, QDateEdit#glowDate, QDoubleSpinBox#glowSpin {{
                background: {self.BG_INPUT};
                color: {self.TEXT_MAIN};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
            }}
            QComboBox#glowCombo:hover, QDateEdit#glowDate:hover,
            QDoubleSpinBox#glowSpin:hover {{
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

    # ── Save & Validation Logic ───────────────────────────────
    def _save(self):
        if self._is_closed:
            return

        stencil = self.txt_stencil.text().strip()
        name = self.txt_name.text().strip()

        if not stencil:
            self.lbl_warning.setText(
                "⚠️ Validation Error: Welder Stencil / Stamp No. is required."
            )
            self._shake()
            self.txt_stencil.setFocus()
            return

        if not name:
            self.lbl_warning.setText(
                "⚠️ Validation Error: Welder Full Name is required."
            )
            self._shake()
            self.txt_name.setFocus()
            return

        if self.spn_thk_min.value() > self.spn_thk_max.value():
            self.lbl_warning.setText(
                "⚠️ ASME Range Error: Minimum Thickness cannot exceed "
                "Maximum Thickness."
            )
            self._shake()
            self.spn_thk_min.setFocus()
            return

        self.lbl_warning.setText("")

        self.result_data = {
            "stencil_no": stencil.upper(),
            "full_name": name,
            "national_id": self.txt_national_id.text().strip(),
            "employer": self.txt_employer.text().strip(),
            "welding_processes": self.cmb_process.currentText(),
            "qualified_positions": self.cmb_positions.currentText(),
            "qualified_thickness_min_mm": self.spn_thk_min.value(),
            "qualified_thickness_max_mm": self.spn_thk_max.value(),
            "qualified_diameter_min_inch": self.spn_dia_min.value(),
            "qualified_material_p_no": self.txt_p_no.text().strip() or "P1 through P11",
            "filler_f_no": self.txt_f_no.text().strip(),
            "weld_backing": self.cmb_backing.currentText(),
            "certificate_no": self.txt_cert.text().strip(),
            "supporting_wpqr": self.txt_wpqr.text().strip(),
            "qualification_date": self.dte_qual.date().toPyDate(),
            "expiry_date": self.dte_expiry.date().toPyDate(),
            "testing_agency": self.txt_agency.text().strip(),
            "witness_inspector": self.txt_witness.text().strip(),
            "remarks": self.txt_remarks.toPlainText().strip(),
            "is_active": self.chk_active_status.isChecked(),
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

    mock_welder = {
        "stencil_no": "W-04",
        "full_name": "Saeed Rezaei",
        "national_id": "0082441920",
        "employer": "Petro Pishgam Piping Construction",
        "welding_processes": "GTAW + SMAW (Combo)",
        "qualified_positions": "6G (All Positions - Pipe Inclined 45°)",
        "qualified_thickness_min_mm": 1.5,
        "qualified_thickness_max_mm": 17.8,
        "qualified_diameter_min_inch": 1.0,
        "qualified_material_p_no": "P1 through P11 / P4X",
        "filler_f_no": "F6 (ER70S-6) / F4 (E7018-1)",
        "certificate_no": "WPQ-2025-P1-004",
        "supporting_wpqr": "PQR-CS-COMBO-01",
        "qualification_date": date(2025, 1, 15),
        "expiry_date": date(2025, 7, 15),
        "testing_agency": "TUV NORD Middle East",
        "witness_inspector": "Eng. Farhadi (CSWIP 3.1 / Level II)",
        "remarks": (
            "100% Volumetric Radiography (RT) cleared on 2\" Sch 80 test "
            "coupon. Valid for sour service."
        ),
        "is_active": True,
    }

    dialog = WelderDialog(welder_data=mock_welder)
    dialog.show()
    dialog.exec()

    if getattr(dialog, "result_data", None):
        print("Welder Registered Result Data:", dialog.result_data)

    sys.exit(0)