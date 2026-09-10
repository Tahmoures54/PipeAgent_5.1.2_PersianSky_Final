# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium License Management Dialog
═══════════════════════════════════════════════════════════
Version : 5.0 (Refactored, hardened, production-ready)
Engine  : PyQt6
Design  : Cinematic dark-tech theme matching Splash & Login

Fixes in this revision
──────────────────────
🔴 P0  GlowLineEdit        : no longer calls deleteLater() on an animation
                           that Qt already owns (DeleteWhenStopped) → no
                           "wrapped C/C++ object has been deleted"
🔴 P0  _shake              : same lifetime fix; guard against calling
                           stop() on an already-destroyed anim
🔴 P0  Card border         : replaced invalid `border: ... qlineargradient`
                           (QSS does not support gradients in `border`)
                           with a solid border + glow shadow
🟠 P1  Deferred activation : replaced `QTimer.singleShot(600, lambda ...)`
                           with a member QTimer so the callback cannot fire
                           after the dialog has been destroyed
🟠 P1  closeEvent chain    : split _cleanup() from _on_close() to avoid
                           accept() → closeEvent recursion
🟠 P1  Copy button reset   : styles restored to the empty string so the
                           inherited stylesheet is re-applied (no hardcoded
                           style duplication)
🟡 P2  Key format          : regex, placeholder, and hint all agree on
                           "XXXX-XXXX-XXXX-XXXX" (4 groups, 4 chars each);
                           auto-dash insertion now actually implemented
🟡 P2  Auto-close timer    : guarded with isVisible() to avoid running on
                           a hidden / destroyed dialog
🟡 P2  Status service      : defensive imports and clearer error text
🟢 P3  ParticleField       : count 22 → 14, tick 55ms → 100ms, paint only
                           when visible (CPU/GPU friendly)
🟢 P3  General             : single source of truth for state checks; no
                           duplicate `from datetime import date` alias
"""

from __future__ import annotations

import re
import sys
import random
import logging
from datetime import date as _date, datetime
from typing import Optional, Tuple

from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRect, QSize,
    QPropertyAnimation, QEasingCurve, pyqtSignal, QUrl,
)
from PyQt6.QtGui import (
    QFont, QPixmap, QPainter, QColor, QLinearGradient,
    QRadialGradient, QPen, QBrush, QPainterPath,
    QMouseEvent, QKeyEvent, QDesktopServices,
    QShortcut, QKeySequence,
)
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QFrame, QGraphicsDropShadowEffect,
    QWidget, QApplication, QMessageBox, QSizePolicy,
    QScrollArea, QProgressBar,
)

logger = logging.getLogger(__name__)

# ── Key Format ────────────────────────────────────────────────
# Canonical format: XXXX-XXXX-XXXX-XXXX  (4 groups of 4 alnum)
KEY_PATTERN = re.compile(r'^[A-Za-z0-9]{4}(-[A-Za-z0-9]{4}){3}$')
KEY_HINT    = "Expected format: XXXX-XXXX-XXXX-XXXX"
KEY_MAXLEN  = 19   # 16 chars + 3 dashes


# ════════════════════════════════════════════════════════════════
#  GLOW RING — Animated Rotating Ring
# ════════════════════════════════════════════════════════════════

class GlowRing(QWidget):
    """Animated rotating glow ring behind icon."""

    def __init__(self, parent=None, size=80):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._angle = 0
        self._ring_size = size
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(30)

    def _rotate(self):
        if not self.isVisible():
            return
        self._angle = (self._angle + 3) % 360
        self.update()

    def stop(self):
        """Graceful stop for cleanup."""
        self._timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        radius = self._ring_size // 2 - 4

        # Outer glow halo
        gradient = QRadialGradient(center.x(), center.y(), radius + 8)
        gradient.setColorAt(0.0, QColor(108, 207, 246, 0))
        gradient.setColorAt(0.75, QColor(108, 207, 246, 0))
        gradient.setColorAt(0.9, QColor(108, 207, 246, 45))
        gradient.setColorAt(1.0, QColor(108, 207, 246, 0))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, radius + 8, radius + 8)

        # Primary arc (120°)
        pen = QPen(QColor(104, 215, 255, 220), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        rect = QRect(
            center.x() - radius, center.y() - radius,
            radius * 2, radius * 2,
        )
        painter.drawArc(rect, self._angle * 16, 120 * 16)

        # Secondary arc (90°, opposite side, dimmer)
        pen2 = QPen(QColor(159, 231, 255, 90), 1.5)
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen2)
        painter.drawArc(rect, (self._angle + 180) * 16, 90 * 16)

        painter.end()


# ════════════════════════════════════════════════════════════════
#  PARTICLE FIELD — light-weight animated background
# ════════════════════════════════════════════════════════════════

class ParticleField(QWidget):
    """Subtle floating particle background — performance friendly."""

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
                "vx": random.uniform(-0.0003, 0.0003),
                "vy": random.uniform(-0.0006, -0.0002),
                "r": random.uniform(0.8, 2.0),
                "alpha": random.randint(20, 80),
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

    def paintEvent(self, event):
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
    """
    QLineEdit with focus glow.

    Fixed: the previous version called deleteLater() on an animation
    that Qt owns (started with DeleteWhenStopped), producing
    'wrapped C/C++ object has been deleted' on the next focus change.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimumHeight(44)

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
        # Qt owns the object (DeleteWhenStopped).
        if self._current_anim is not None:
            try:
                self._current_anim.stop()
            except RuntimeError:
                pass
            self._current_anim = None

        self._shadow.setColor(QColor(108, 207, 246, 150 if on else 0))

        anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        anim.setDuration(200)
        anim.setStartValue(self._shadow.blurRadius())
        anim.setEndValue(16 if on else 0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._current_anim = anim


# ════════════════════════════════════════════════════════════════
#  STATUS CARD
# ════════════════════════════════════════════════════════════════

class StatusCard(QFrame):
    """Rich license status display with colored indicator."""

    COLORS = {
        "active":  ("#5cffaa", "#0a2a1a", "#1e6b43"),
        "expired": ("#ff6b6b", "#2a0a0a", "#6b1e1e"),
        "trial":   ("#ffd966", "#2a220a", "#6b5a1e"),
        "none":    ("#ff9f43", "#2a1a0a", "#6b4a1e"),
        "error":   ("#ff6b6b", "#2a0a0a", "#6b1e1e"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusCard")
        self.setMinimumHeight(70)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)

        self.indicator = QLabel("●")
        self.indicator.setObjectName("indicator")
        self.indicator.setFont(QFont("Segoe UI", 18))
        layout.addWidget(self.indicator)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        self.status_title = QLabel("Checking License…")
        self.status_title.setObjectName("statusTitle")
        self.status_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        text_col.addWidget(self.status_title)

        self.status_detail = QLabel("Please wait…")
        self.status_detail.setObjectName("statusDetail")
        self.status_detail.setWordWrap(True)
        self.status_detail.setFont(QFont("Segoe UI", 10))
        text_col.addWidget(self.status_detail)

        layout.addLayout(text_col, 1)

        self.badge = QLabel("")
        self.badge.setObjectName("badge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setFixedSize(70, 26)
        self.badge.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        layout.addWidget(self.badge)

    def set_status(self, title: str, detail: str, state: str = "active"):
        fg, bg, border = self.COLORS.get(state, self.COLORS["none"])

        self.indicator.setStyleSheet(f"color: {fg}; background: transparent;")
        self.status_title.setText(title)
        self.status_title.setStyleSheet(
            f"color: {fg}; font-size: 13px; font-weight: 700; background: transparent;"
        )
        self.status_detail.setText(detail)
        self.status_detail.setStyleSheet(
            "color: #8faec5; font-size: 11px; background: transparent;"
        )

        badge_text = state.upper()
        self.badge.setText(badge_text)
        self.badge.setStyleSheet(f"""
            QLabel#badge {{
                color: {fg};
                background: rgba({self._hex_to_rgb(fg)}, 0.12);
                border: 1px solid {fg};
                border-radius: 12px;
                font-size: 8px;
                font-weight: 800;
                letter-spacing: 1px;
            }}
        """)

        self.setStyleSheet(f"""
            QFrame#statusCard {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 10px;
            }}
        """)

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> str:
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f"{r}, {g}, {b}"


# ════════════════════════════════════════════════════════════════
#  ACTIVATION PROGRESS
# ════════════════════════════════════════════════════════════════

class ActivationProgress(QFrame):
    """Indeterminate progress bar for activation state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("activationProgress")
        self.setFixedHeight(36)
        self.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        self.spinner = QLabel("🔄")
        self.spinner.setFont(QFont("Segoe UI", 12))
        self.spinner.setStyleSheet("background: transparent;")
        layout.addWidget(self.spinner)

        self.label = QLabel("Verifying activation key…")
        self.label.setStyleSheet(
            "color: #9fe7ff; font-size: 11px; font-weight: 600; "
            "letter-spacing: 1px; background: transparent;"
        )
        layout.addWidget(self.label, 1)

        self.setStyleSheet("""
            QFrame#activationProgress {
                background: rgba(108, 207, 246, 0.06);
                border: 1px solid rgba(108, 207, 246, 0.15);
                border-radius: 8px;
            }
        """)

        self._spin_index = 0
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._spin)

    def show_progress(self, text: str = "Verifying activation key…"):
        self.label.setText(text)
        self.setVisible(True)
        self._spin_timer.start(100)

    def hide_progress(self):
        self.setVisible(False)
        self._spin_timer.stop()

    def _spin(self):
        icons = ["🔄", "⏳"]
        self._spin_index = (self._spin_index + 1) % len(icons)
        self.spinner.setText(icons[self._spin_index])

    def stop(self):
        self._spin_timer.stop()


# ════════════════════════════════════════════════════════════════
#  KEY FORMAT INDICATOR
# ════════════════════════════════════════════════════════════════

class KeyFormatIndicator(QLabel):
    """Visual indicator for key format validity."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("keyIndicator")
        self.setFixedHeight(18)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.set_state("empty")

    def set_state(self, state: str):
        base = "font-size: 9px; font-weight: 600; letter-spacing: 1px; background: transparent;"
        if state == "empty":
            self.setText("")
            self.setStyleSheet(base)
        elif state == "valid":
            self.setText("✓  Valid key format")
            self.setStyleSheet(f"color: #5cffaa; {base}")
        elif state == "invalid":
            self.setText(f"⚠  {KEY_HINT}")
            self.setStyleSheet(f"color: #ff9f43; {base}")
        elif state == "short":
            self.setText(f"…  Keep typing  ({KEY_HINT})")
            self.setStyleSheet(f"color: #7a9ab3; {base}")


# ════════════════════════════════════════════════════════════════
#  MAIN LICENSE DIALOG
# ════════════════════════════════════════════════════════════════

class LicenseDialog(QDialog):
    """
    Ultra-premium license management dialog for PipeAgent.

    Frameless, resizable, particle background, live validation,
    inline status messages, and safe timer/animation lifetimes.
    """

    # ── Palette (identical to Splash & Login) ─────────────────
    BG_DEEP       = "#060e18"
    BG_APP        = "#0b1624"
    BG_PANEL      = "#0f1c2e"
    BG_INPUT      = "#0a1826"
    PRIMARY       = "#6ccff6"
    PRIMARY_LIGHT = "#9fe7ff"
    ACCENT        = "#68d7ff"
    TEXT_MAIN     = "#eef6ff"
    TEXT_MUTED    = "#7a9ab3"
    TEXT_FOOTER   = "#3f6070"
    ERROR         = "#ff6b6b"
    SUCCESS       = "#5cffaa"
    WARNING       = "#ffd966"

    MIN_WIDTH  = 460
    MIN_HEIGHT = 560
    DEF_WIDTH  = 540
    DEF_HEIGHT = 700

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db

        # Frameless drag/resize state
        self._drag_pos: Optional[QPoint] = None
        self._drag_edge: Optional[str] = None
        self._drag_geometry: Optional[QRect] = None
        self._resize_margin = 8

        # Behaviour state
        self._is_activating = False
        self._is_closed     = False
        self._shake_anim: Optional[QPropertyAnimation] = None
        self._activation_timer: Optional[QTimer] = None
        self._auto_close_timer: Optional[QTimer] = None

        self.setWindowTitle("PipeAgent – License")
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
        self._refresh_status()

    # ── UI construction ───────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QWidget()
        self._card.setObjectName("card")
        self._card.setStyleSheet(self._stylesheet())
        self._card.setMouseTracking(True)

        card_shadow = QGraphicsDropShadowEffect(self._card)
        card_shadow.setBlurRadius(40)
        card_shadow.setColor(QColor(0, 0, 0, 180))
        card_shadow.setOffset(0, 8)
        self._card.setGraphicsEffect(card_shadow)

        outer.addWidget(self._card)

        self._particles = ParticleField(self._card, count=14)
        self._particles.lower()

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Top bar
        topbar = QHBoxLayout()
        topbar.setContentsMargins(14, 10, 14, 0)

        drag_hint = QLabel("⠿")
        drag_hint.setStyleSheet("color: #2a4a5a; font-size: 14px; background: transparent;")
        drag_hint.setToolTip("Drag to move window")
        topbar.addWidget(drag_hint)
        topbar.addStretch()

        min_btn = QPushButton("─")
        min_btn.setObjectName("minBtn")
        min_btn.setFixedSize(28, 28)
        min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        min_btn.setToolTip("Minimize")
        min_btn.clicked.connect(self.showMinimized)
        min_btn.setStyleSheet("""
            QPushButton#minBtn {
                background: transparent; color: #7a9ab3;
                border: none; border-radius: 14px;
                font-size: 12px; font-weight: bold;
            }
            QPushButton#minBtn:hover {
                background: rgba(108, 207, 246, 0.12); color: #6ccff6;
            }
        """)
        topbar.addWidget(min_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Close (Escape)")
        self.close_btn.clicked.connect(self._on_close)
        topbar.addWidget(self.close_btn)

        card_layout.addLayout(topbar)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("contentScroll")
        scroll.setStyleSheet("""
            QScrollArea#contentScroll { border: none; background: transparent; }
            QScrollBar:vertical {
                background: #07101a; width: 6px; border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #1e3d5a; border-radius: 3px; min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #6ccff6; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        scroll_inner = QWidget()
        scroll_inner.setStyleSheet("background: transparent;")
        content = QVBoxLayout(scroll_inner)
        content.setContentsMargins(44, 4, 44, 22)
        content.setSpacing(0)

        # Logo + Glow Ring
        logo_container = QWidget()
        logo_container.setFixedSize(80, 80)
        logo_container.setStyleSheet("background: transparent;")

        self._glow_ring = GlowRing(logo_container, size=80)
        self._glow_ring.move(0, 0)

        self.icon_label = QLabel(logo_container)
        self.icon_label.setFixedSize(80, 80)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setText("🔑")
        self.icon_label.setFont(QFont("Segoe UI", 28))
        self.icon_label.setStyleSheet("background: transparent;")

        logo_wrapper = QHBoxLayout()
        logo_wrapper.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_wrapper.addWidget(logo_container)
        content.addLayout(logo_wrapper)
        content.addSpacing(6)

        # Brand
        brand = QLabel("PIPE  AGENT")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._add_glow(brand, QColor(108, 207, 246, 90), blur=22)
        content.addWidget(brand)

        subtitle = QLabel("LICENSE MANAGEMENT")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(subtitle)
        content.addSpacing(8)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        content.addWidget(divider)
        content.addSpacing(14)

        # Status card
        self.status_card = StatusCard()
        self.status_card.setToolTip("Current license status")
        content.addWidget(self.status_card)
        content.addSpacing(14)

        # Machine ID
        mid_label = QLabel("🖥   MACHINE ID")
        mid_label.setObjectName("fieldLabel")
        content.addWidget(mid_label)
        content.addSpacing(4)

        mid_row = QHBoxLayout()
        mid_row.setSpacing(0)

        self.mid_input = GlowLineEdit()
        self.mid_input.setReadOnly(True)
        self.mid_input.setObjectName("midInput")
        self.mid_input.setCursor(Qt.CursorShape.IBeamCursor)
        self.mid_input.setToolTip(
            "Your unique machine identifier — share with admin for activation"
        )
        try:
            from services.license import get_machine_id
            self.mid_input.setText(get_machine_id())
        except Exception:
            self.mid_input.setText("UNAVAILABLE")
        mid_row.addWidget(self.mid_input)

        self.copy_btn = QPushButton("📋  COPY")
        self.copy_btn.setObjectName("copyBtn")
        self.copy_btn.setFixedSize(84, 44)
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.setToolTip("Copy Machine ID to clipboard (Ctrl+Shift+C)")
        self.copy_btn.clicked.connect(self._copy_machine_id)
        mid_row.addWidget(self.copy_btn)

        content.addLayout(mid_row)
        content.addSpacing(14)

        # Activation key
        key_label = QLabel("🔐   ACTIVATION KEY")
        key_label.setObjectName("fieldLabel")
        content.addWidget(key_label)
        content.addSpacing(4)

        self.key_input = GlowLineEdit()
        self.key_input.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self.key_input.setToolTip("Enter your license activation key")
        self.key_input.setMaxLength(KEY_MAXLEN)
        self.key_input.textChanged.connect(self._on_key_text_changed)
        content.addWidget(self.key_input)

        content.addSpacing(4)

        self.key_indicator = KeyFormatIndicator()
        content.addWidget(self.key_indicator)
        content.addSpacing(6)

        # Progress (hidden by default)
        self.progress = ActivationProgress()
        content.addWidget(self.progress)

        # Inline message
        self.msg_label = QLabel("")
        self.msg_label.setObjectName("msgLabel")
        self.msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg_label.setMinimumHeight(20)
        self.msg_label.setWordWrap(True)
        content.addWidget(self.msg_label)
        content.addSpacing(8)

        # Activate
        self.activate_btn = QPushButton("⚡   ACTIVATE LICENSE")
        self.activate_btn.setObjectName("activateBtn")
        self.activate_btn.setMinimumHeight(46)
        self.activate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.activate_btn.setDefault(True)
        self.activate_btn.setToolTip("Validate and activate your license key (Enter)")
        self.activate_btn.clicked.connect(self._on_activate)
        self._add_glow(self.activate_btn, QColor(104, 215, 255, 100), blur=18)
        content.addWidget(self.activate_btn)
        content.addSpacing(8)

        # Secondary buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.purchase_btn = QPushButton("🛒   PURCHASE LICENSE")
        self.purchase_btn.setObjectName("purchaseBtn")
        self.purchase_btn.setMinimumHeight(42)
        self.purchase_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.purchase_btn.setToolTip("Open license purchase page in browser")
        self.purchase_btn.clicked.connect(self._on_purchase)
        btn_row.addWidget(self.purchase_btn)

        self.refresh_btn = QPushButton("🔄  REFRESH")
        self.refresh_btn.setObjectName("cancelBtn")
        self.refresh_btn.setMinimumHeight(42)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setToolTip("Refresh license status (F5)")
        self.refresh_btn.clicked.connect(self._refresh_status)
        btn_row.addWidget(self.refresh_btn)

        close_dialog_btn = QPushButton("CLOSE")
        close_dialog_btn.setObjectName("cancelBtn")
        close_dialog_btn.setMinimumHeight(42)
        close_dialog_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_dialog_btn.setToolTip("Close this dialog (Escape)")
        close_dialog_btn.clicked.connect(self._on_close)
        btn_row.addWidget(close_dialog_btn)

        content.addLayout(btn_row)
        content.addStretch()
        content.addSpacing(8)

        footer = QLabel("⚡  PipeAgent 5.0  •  Secure License Verification")
        footer.setObjectName("footer")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(footer)

        reassurance = QLabel(
            "🛡  Your license data is stored locally in your project workspace"
        )
        reassurance.setObjectName("reassurance")
        reassurance.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reassurance.setWordWrap(True)
        content.addWidget(reassurance)

        scroll.setWidget(scroll_inner)
        card_layout.addWidget(scroll, 1)

        self.key_input.returnPressed.connect(self._on_activate)

    # ── Keyboard shortcuts ────────────────────────────────────
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, self._copy_machine_id)
        QShortcut(QKeySequence("F5"), self, self._refresh_status)
        QShortcut(
            QKeySequence("Ctrl+V"), self,
            lambda: (self.key_input.setFocus(), self.key_input.paste())
        )

    # ── Stylesheet ────────────────────────────────────────────
    def _stylesheet(self) -> str:
        return f"""
            QWidget#card {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {self.BG_DEEP},
                    stop:0.4 {self.BG_APP},
                    stop:1 {self.BG_DEEP}
                );
                /* QSS does not support gradients in `border`.
                   Depth comes from the drop shadow on the card. */
                border: 2px solid {self.PRIMARY};
                border-radius: 20px;
            }}
            QLabel#brand {{
                color: {self.PRIMARY_LIGHT};
                font-size: 24px;
                font-weight: 900;
                letter-spacing: 6px;
                background: transparent;
            }}
            QLabel#subtitle {{
                color: {self.PRIMARY};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 3px;
                background: transparent;
            }}
            QFrame#divider {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 transparent,
                    stop:0.5 rgba(108, 207, 246, 0.4),
                    stop:1 transparent
                );
                border: none;
            }}
            QLabel#fieldLabel {{
                color: {self.PRIMARY_LIGHT};
                font-size: 9px;
                font-weight: 800;
                letter-spacing: 2px;
                background: transparent;
                padding-left: 4px;
            }}
            QLineEdit {{
                background: {self.BG_INPUT};
                color: {self.TEXT_MAIN};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 0 14px;
                font-size: 12px;
                font-family: Consolas, "Courier New", monospace;
                selection-background-color: {self.PRIMARY};
                selection-color: {self.BG_APP};
            }}
            QLineEdit:hover {{ border: 1px solid #2c5478; }}
            QLineEdit:focus {{
                border: 1px solid {self.PRIMARY};
                background: #0d1f30;
            }}
            QLineEdit#midInput {{
                color: {self.TEXT_MUTED};
                font-size: 11px;
                letter-spacing: 1px;
                border-top-right-radius: 0;
                border-bottom-right-radius: 0;
                border-right: none;
            }}
            QPushButton#copyBtn {{
                background: {self.BG_PANEL};
                color: {self.PRIMARY_LIGHT};
                border: 1px solid #1e3d5a;
                border-left: none;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton#copyBtn:hover {{
                background: #142a40; color: {self.ACCENT};
            }}
            QPushButton#copyBtn:pressed {{
                background: {self.PRIMARY}; color: {self.BG_APP};
            }}
            QLabel#msgLabel {{
                color: {self.ERROR};
                font-size: 11px;
                font-weight: 600;
                background: transparent;
            }}
            QPushButton#activateBtn {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2196d4,
                    stop:0.5 {self.ACCENT},
                    stop:1 #2196d4
                );
                color: #041827;
                border: none;
                border-radius: 10px;
                font-size: 13px;
                font-weight: 800;
                letter-spacing: 2px;
            }}
            QPushButton#activateBtn:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {self.ACCENT},
                    stop:0.5 {self.PRIMARY_LIGHT},
                    stop:1 {self.ACCENT}
                );
            }}
            QPushButton#activateBtn:pressed {{ background: #2196d4; }}
            QPushButton#activateBtn:disabled {{
                background: #1a3d54; color: #5a7a8a;
            }}
            QPushButton#purchaseBtn {{
                background: transparent;
                color: {self.PRIMARY_LIGHT};
                border: 1px solid {self.PRIMARY};
                border-radius: 10px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton#purchaseBtn:hover {{
                background: rgba(108, 207, 246, 0.08);
                color: {self.ACCENT};
            }}
            QPushButton#cancelBtn {{
                background: transparent;
                color: {self.TEXT_MUTED};
                border: 1px solid #1e3d5a;
                border-radius: 10px;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 1px;
            }}
            QPushButton#cancelBtn:hover {{
                color: {self.PRIMARY_LIGHT};
                border: 1px solid {self.PRIMARY};
                background: rgba(108, 207, 246, 0.05);
            }}
            QPushButton#closeBtn {{
                background: transparent;
                color: {self.TEXT_MUTED};
                border: none;
                border-radius: 14px;
                font-size: 14px;
                font-weight: 700;
            }}
            QPushButton#closeBtn:hover {{
                background: rgba(255, 107, 107, 0.15);
                color: {self.ERROR};
            }}
            QLabel#footer {{
                color: {self.TEXT_MUTED};
                font-size: 10px;
                letter-spacing: 1px;
                background: transparent;
                font-weight: 600;
            }}
            QLabel#reassurance {{
                color: {self.TEXT_FOOTER};
                font-size: 9px;
                background: transparent;
                padding-top: 2px;
            }}
            QScrollBar:vertical {{
                background: #07101a; width: 6px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: #1e3d5a; border-radius: 3px; min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {self.PRIMARY}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
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

    # ── Status messages ───────────────────────────────────────
    def _show_msg(self, text: str, is_error: bool = True):
        color = self.ERROR if is_error else self.SUCCESS
        icon = "⚠" if is_error else "✓"
        self.msg_label.setStyleSheet(
            f"color: {color}; font-size: 11px; "
            f"font-weight: 600; background: transparent;"
        )
        self.msg_label.setText(f"{icon}  {text}")

    def _clear_msg(self):
        self.msg_label.setText("")

    # ── Key format handling ───────────────────────────────────
    def _on_key_text_changed(self, text: str):
        """Live format validation with auto-dash insertion."""
        # 1. Strip everything except alphanumerics, uppercase
        stripped = re.sub(r'[^A-Za-z0-9]', '', text).upper()

        # 2. Insert a dash every 4 characters, up to 4 groups
        groups = [stripped[i:i + 4] for i in range(0, len(stripped), 4)]
        groups = groups[:4]
        cleaned = "-".join(groups)

        if cleaned != text:
            cursor_at_end = (self.key_input.cursorPosition() >= len(text))
            self.key_input.blockSignals(True)
            self.key_input.setText(cleaned)
            self.key_input.setCursorPosition(len(cleaned) if cursor_at_end else min(
                self.key_input.cursorPosition(), len(cleaned)
            ))
            self.key_input.blockSignals(False)

        # 3. Update the indicator based on the canonical format
        if not cleaned:
            self.key_indicator.set_state("empty")
        elif KEY_PATTERN.match(cleaned):
            self.key_indicator.set_state("valid")
        elif len(cleaned) < KEY_MAXLEN:
            self.key_indicator.set_state("short")
        else:
            self.key_indicator.set_state("invalid")

        if self.msg_label.text():
            self._clear_msg()

    # ── Shake animation ───────────────────────────────────────
    def _shake(self):
        # Stop any in-flight animation safely (it may already be gone).
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

    # ── Copy machine ID ───────────────────────────────────────
    def _copy_machine_id(self):
        mid = self.mid_input.text()
        if not mid or mid == "UNAVAILABLE":
            self._show_msg("Machine ID is not available.")
            return

        QApplication.clipboard().setText(mid)

        # Visual feedback for 1.5 s, then restore inherited stylesheet.
        self.copy_btn.setText("✓  DONE")
        self.copy_btn.setStyleSheet(
            f"background: {self.SUCCESS}; color: #041827; "
            f"border: 1px solid {self.SUCCESS}; "
            f"border-left: none; border-top-right-radius: 8px; "
            f"border-bottom-right-radius: 8px; "
            f"font-size: 10px; font-weight: 700;"
        )
        QTimer.singleShot(1500, self._reset_copy_btn)
        self._show_msg("Machine ID copied to clipboard.", is_error=False)

    def _reset_copy_btn(self):
        """Clear the local stylesheet so the inherited #copyBtn style returns."""
        if self.copy_btn is None:
            return
        self.copy_btn.setText("📋  COPY")
        # Empty string → Qt re-applies styles from the parent's stylesheet.
        self.copy_btn.setStyleSheet("")

    # ── Refresh status ────────────────────────────────────────
    def _refresh_status(self):
        try:
            from services.license import get_license_info, format_license_status
            from services.product_commercial import plan_for_license_info

            info = get_license_info(self.db)
            status_text = format_license_status(self.db)

            try:
                plan = plan_for_license_info(info)
                status_text = f"{status_text}\nCommercial tier: {plan.name}"
            except Exception:
                logger.debug("Commercial tier lookup failed", exc_info=True)

            state, title = ("none", "No Active License")
            if info is not None:
                state, title = self._detect_license_state(info)

            self.status_card.set_status(title, status_text, state)
            self._show_msg(
                f"Status refreshed at {datetime.now().strftime('%H:%M:%S')}",
                is_error=False,
            )

        except ImportError as e:
            logger.warning("License service not available: %s", e)
            self.status_card.set_status(
                "Service Unavailable",
                "License service modules could not be loaded.",
                "error",
            )
        except Exception as e:
            logger.exception("Failed to read license info")
            self.status_card.set_status(
                "Status Error",
                f"Could not read license data: {e}",
                "error",
            )

    @staticmethod
    def _detect_license_state(info) -> Tuple[str, str]:
        """Defensive state detection — works with any license API shape."""
        if getattr(info, "is_expired", False):
            return "expired", "License Expired"
        if getattr(info, "is_trial", False):
            return "trial", "Trial License"
        if getattr(info, "is_active", False):
            return "active", "License Active"

        status_attr = getattr(info, "status", None)
        if status_attr is not None:
            s = str(status_attr).lower()
            if "expired" in s:
                return "expired", "License Expired"
            if "trial" in s:
                return "trial", "Trial License"
            if "active" in s or "valid" in s:
                return "active", "License Active"

        expiry = getattr(info, "expiry_date", None)
        if expiry:
            try:
                if isinstance(expiry, str):
                    exp = datetime.strptime(expiry, "%Y-%m-%d").date()
                elif isinstance(expiry, _date):
                    exp = expiry
                else:
                    exp = None
                if exp and exp < _date.today():
                    return "expired", "License Expired"
                if exp:
                    return "active", "License Active"
            except (ValueError, TypeError):
                pass

        if info is not None:
            return "active", "License Registered"

        return "none", "No Active License"

    # ── Purchase ──────────────────────────────────────────────
    def _on_purchase(self):
        url = None
        try:
            from config import LICENSE_PURCHASE_URL
            url = LICENSE_PURCHASE_URL
        except (ImportError, AttributeError):
            pass

        if url:
            QDesktopServices.openUrl(QUrl(url))
            self._show_msg("Opening purchase page in browser…", is_error=False)
        else:
            self._show_msg(
                "Contact your PipeAgent administrator for a production license.",
                is_error=False,
            )

    # ── Activate ──────────────────────────────────────────────
    def _on_activate(self):
        if self._is_activating:
            return

        key = self.key_input.text().strip()

        if not key:
            self._show_msg("Please enter an activation key.")
            self._shake()
            self.key_input.setFocus()
            return

        if not KEY_PATTERN.match(key):
            self._show_msg(f"Invalid key format. {KEY_HINT}")
            self._shake()
            self.key_input.setFocus()
            return

        self._is_activating = True
        self._clear_msg()
        self.activate_btn.setEnabled(False)
        self.activate_btn.setText("🔄   VERIFYING…")
        self.key_input.setReadOnly(True)
        self.progress.show_progress("Validating activation key…")

        # Use a member QTimer so it is owned by self and cannot fire
        # after the dialog has been destroyed.
        if self._activation_timer is not None:
            self._activation_timer.stop()
            self._activation_timer.deleteLater()
        self._activation_timer = QTimer(self)
        self._activation_timer.setSingleShot(True)
        self._activation_timer.timeout.connect(
            lambda k=key: self._do_activate(k)
        )
        self._activation_timer.start(600)

    def _do_activate(self, key: str):
        if self._is_closed:
            self._is_activating = False
            return

        try:
            from services.license import activate_license
            success, msg = activate_license(key, self.db)
        except ImportError:
            success, msg = False, "License service not available."
        except Exception as e:
            logger.exception("License activation error")
            success, msg = False, f"Activation error: {e}"

        self.progress.hide_progress()
        self.activate_btn.setEnabled(True)
        self.activate_btn.setText("⚡   ACTIVATE LICENSE")
        self.key_input.setReadOnly(False)
        self._is_activating = False

        if success:
            self._show_msg(
                msg or "License activated successfully!", is_error=False
            )
            self._refresh_status()
            self.key_input.clear()
            self.key_indicator.set_state("empty")

            self.icon_label.setText("✅")
            QTimer.singleShot(
                1500,
                lambda: self.icon_label.setText("🔑") if not self._is_closed else None,
            )

            self._schedule_auto_close(2000)
        else:
            self._show_msg(msg or "Invalid activation key.")
            self._shake()
            self.key_input.selectAll()
            self.key_input.setFocus()
            self._refresh_status()

    def _schedule_auto_close(self, ms: int):
        if self._auto_close_timer is not None:
            self._auto_close_timer.stop()
            self._auto_close_timer.deleteLater()
        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self._auto_close_if_visible)
        self._auto_close_timer.start(ms)

    def _auto_close_if_visible(self):
        if self._is_closed or not self.isVisible():
            return
        self._on_close()

    # ── Graceful close ────────────────────────────────────────
    def _cleanup(self):
        """Stop every timer / animation we own. Safe to call twice."""
        if self._is_closed:
            return
        self._is_closed = True

        for attr in ("_glow_ring", "_particles"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.stop()
                except RuntimeError:
                    pass

        if hasattr(self, "progress"):
            try:
                self.progress.stop()
            except RuntimeError:
                pass

        if self._shake_anim is not None:
            try:
                self._shake_anim.stop()
            except RuntimeError:
                pass
            self._shake_anim = None

        if self._activation_timer is not None:
            self._activation_timer.stop()
            self._activation_timer = None

        if self._auto_close_timer is not None:
            self._auto_close_timer.stop()
            self._auto_close_timer = None

    def _on_close(self):
        self._cleanup()
        # accept() ends the modal loop; it does NOT trigger closeEvent.
        if self.isVisible():
            self.accept()

    def closeEvent(self, event):  # noqa: N802
        # Called by the window manager (Alt+F4, etc.).
        self._cleanup()
        super().closeEvent(event)


# ════════════════════════════════════════════════════════════════
#  STANDALONE TEST RUNNER
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import types

    # ── Mock dependencies for standalone testing ─────────────
    class MockDB:
        pass

    class MockLicenseInfo:
        is_active = True
        is_trial = False
        is_expired = False
        status = "active"
        expiry_date = "2026-12-31"

    class MockPlan:
        name = "Professional Edition"

    mock_license_mod = types.ModuleType("services.license")
    mock_license_mod.get_license_info = lambda db: MockLicenseInfo()
    mock_license_mod.activate_license = lambda key, db: (
        (True, "License activated successfully! All modules unlocked.")
        if len(key.replace("-", "")) == 16
        else (False, "Invalid activation key. Please check and try again.")
    )
    mock_license_mod.format_license_status = lambda db: (
        "Professional Edition  •  Expires: 2026-12-31  •  5 Seats  •  All Modules"
    )
    mock_license_mod.get_machine_id = lambda: "A7F3-B2C1-9D4E-8E6F"

    mock_commercial_mod = types.ModuleType("services.product_commercial")
    mock_commercial_mod.plan_for_license_info = lambda info: MockPlan()

    mock_config_mod = types.ModuleType("config")
    mock_config_mod.LICENSE_PURCHASE_URL = "https://pipeagent.io/purchase"

    sys.modules["services"] = types.ModuleType("services")
    sys.modules["services.license"] = mock_license_mod
    sys.modules["services.product_commercial"] = mock_commercial_mod
    sys.modules["config"] = mock_config_mod
    sys.modules["db"] = types.ModuleType("db")
    sys.modules["db.manager"] = types.ModuleType("db.manager")
    sys.modules["db.manager"].DatabaseManager = MockDB

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    dialog = LicenseDialog(MockDB())
    dialog.show()
    dialog.exec()

    sys.exit(0)