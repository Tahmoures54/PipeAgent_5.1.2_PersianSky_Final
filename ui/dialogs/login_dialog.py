# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Login Dialog
═══════════════════════════════════════════════════════════
Version : 4.0 (Refactored, hardened, production-ready)
Engine  : PyQt6
Design  : Cinematic dark-tech theme matching StartupSplash

Fixes in this revision
──────────────────────
🔴 P0  Card border        : replaced invalid `border: ... qlineargradient`
                           (QSS does not support gradients in `border`)
                           with a solid color + drop shadow for depth
🔴 P0  GlowLineEdit       : animation lifetime now tracked; a fresh
                           animation stops the previous one before
                           starting → no animated pile-up
🔴 P0  _shake             : previous shake is stopped before a new one
                           starts; guard against RuntimeError on a
                           C++-deleted animation
🟠 P1  Deferred login     : `QTimer.singleShot(400, lambda ...)` replaced
                           with a member QTimer; guarded against the
                           dialog being closed during the wait
🟠 P1  Cleanup on close   : `done()` overridden to stop every timer and
                           animation before the dialog is destroyed
🟠 P1  Password toggle    : reset to "hidden" state on failed login and
                           when the field is cleared
🟡 P2  Status message     : "Verifying…" now uses a neutral state instead
                           of the green success icon
🟡 P2  Deferred focus     : moved from `__init__` singleShot to
                           `showEvent` (first-show only)
🟡 P2  ParticleField      : count 28 → 16, tick 50ms → 100ms, paint only
                           when visible (CPU/GPU friendly)
🟢 P3  Module imports     : `random` moved to module level
🟢 P3  Aesthetic          : kept fixed size for a compact, cinematic
                           login window; drag still works normally
"""

from __future__ import annotations

import sys
import random
import logging
from typing import Optional, Callable

from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRect, QSize,
    QPropertyAnimation, QEasingCurve, pyqtSignal,
)
from PyQt6.QtGui import (
    QFont, QPixmap, QPainter, QColor, QLinearGradient,
    QRadialGradient, QPen, QBrush, QPainterPath, QMouseEvent,
    QKeyEvent, QIcon, QShowEvent,
)
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QFrame, QGraphicsDropShadowEffect,
    QWidget, QApplication, QMessageBox,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
#  GLOW RING — rotating halo behind the logo
# ════════════════════════════════════════════════════════════════

class GlowRing(QWidget):
    """Animated rotating glow ring (paints only when visible)."""

    def __init__(self, parent=None, size: int = 80):
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
        self._timer.stop()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        radius = self._ring_size // 2 - 4

        gradient = QRadialGradient(center.x(), center.y(), radius + 8)
        gradient.setColorAt(0.0, QColor(108, 207, 246, 0))
        gradient.setColorAt(0.75, QColor(108, 207, 246, 0))
        gradient.setColorAt(0.9, QColor(108, 207, 246, 45))
        gradient.setColorAt(1.0, QColor(108, 207, 246, 0))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, radius + 8, radius + 8)

        pen = QPen(QColor(104, 215, 255, 220), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        rect = QRect(
            center.x() - radius, center.y() - radius,
            radius * 2, radius * 2,
        )
        painter.drawArc(rect, self._angle * 16, 120 * 16)

        pen2 = QPen(QColor(159, 231, 255, 90), 1.5)
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen2)
        painter.drawArc(rect, (self._angle + 180) * 16, 90 * 16)

        painter.end()


# ════════════════════════════════════════════════════════════════
#  PARTICLE FIELD — light-weight animated background
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
                "vx": random.uniform(-0.0003, 0.0003),
                "vy": random.uniform(-0.0007, -0.0002),
                "r": random.uniform(0.8, 2.2),
                "alpha": random.randint(25, 90),
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
    """
    QLineEdit with a subtle focus glow.

    Fixed: the previous animation is now stopped before a new one
    starts, so rapid focus changes cannot stack multiple animations
    on the same shadow effect.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimumHeight(46)

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

        self._shadow.setColor(QColor(108, 207, 246, 160 if on else 0))

        anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        anim.setDuration(200)
        anim.setStartValue(self._shadow.blurRadius())
        anim.setEndValue(18 if on else 0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._current_anim = anim


# ════════════════════════════════════════════════════════════════
#  GLOW BUTTON
# ════════════════════════════════════════════════════════════════

class GlowButton(QPushButton):
    """Primary action button with an optional glow shadow."""

    def __init__(self, text: str = "", primary: bool = True, parent=None):
        super().__init__(text, parent)
        self._primary = primary
        self.setMinimumHeight(46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        if primary:
            self._shadow = QGraphicsDropShadowEffect(self)
            self._shadow.setBlurRadius(20)
            self._shadow.setColor(QColor(104, 215, 255, 120))
            self._shadow.setOffset(0, 2)
            self.setGraphicsEffect(self._shadow)


# ════════════════════════════════════════════════════════════════
#  MAIN LOGIN DIALOG
# ════════════════════════════════════════════════════════════════

class LoginDialog(QDialog):
    """
    Ultra-premium modal login dialog for PipeAgent.

    Features:
        • Frameless, draggable, custom-painted window
        • Animated particle background
        • Rotating glow ring behind the logo
        • Focus-glow input fields
        • Shake animation on failed login
        • Safe timer / animation lifetimes
    """

    # ── Palette ───────────────────────────────────────────────
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
    INFO          = "#9fe7ff"

    WIDTH  = 460
    HEIGHT = 620

    def __init__(self, auth_service, parent=None):
        super().__init__(parent)
        self.auth_service = auth_service
        self.authenticated_user = None

        # Window drag state
        self._drag_pos: Optional[QPoint] = None

        # Lifecycle / animation state
        self._is_closing = False
        self._first_show_handled = False
        self._shake_anim: Optional[QPropertyAnimation] = None
        self._login_timer: Optional[QTimer] = None
        self._success_timer: Optional[QTimer] = None

        self.setWindowTitle("PipeAgent – Login")
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._build_ui()
        self._center_on_screen()

    # ── UI construction ───────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._card = QWidget()
        self._card.setObjectName("card")
        self._card.setStyleSheet(self._stylesheet())

        card_shadow = QGraphicsDropShadowEffect(self._card)
        card_shadow.setBlurRadius(40)
        card_shadow.setColor(QColor(0, 0, 0, 180))
        card_shadow.setOffset(0, 8)
        self._card.setGraphicsEffect(card_shadow)

        outer.addWidget(self._card)

        # Particle background inside the card
        self._particles = ParticleField(self._card, count=16)
        self._particles.setGeometry(0, 0, self.WIDTH, self.HEIGHT)
        self._particles.lower()

        # ── Top bar with close button ────────────────────────
        topbar = QHBoxLayout()
        topbar.setContentsMargins(12, 10, 12, 0)
        topbar.addStretch()

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Close (Escape)")
        self.close_btn.clicked.connect(self.reject)
        topbar.addWidget(self.close_btn)

        # ── Main content ─────────────────────────────────────
        content = QVBoxLayout()
        content.setContentsMargins(48, 4, 48, 26)
        content.setSpacing(0)

        # Logo with glow ring
        logo_container = QWidget()
        logo_container.setFixedSize(90, 90)
        logo_container.setStyleSheet("background: transparent;")

        self._glow_ring = GlowRing(logo_container, size=90)
        self._glow_ring.move(0, 0)

        self.icon_label = QLabel(logo_container)
        self.icon_label.setFixedSize(90, 90)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setText("⚙")
        self.icon_label.setFont(QFont("Segoe UI", 32))
        self.icon_label.setStyleSheet(
            f"color: {self.PRIMARY_LIGHT}; background: transparent;"
        )

        logo_wrapper = QHBoxLayout()
        logo_wrapper.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_wrapper.addWidget(logo_container)
        content.addLayout(logo_wrapper)
        content.addSpacing(10)

        # Brand
        brand = QLabel("PIPE  AGENT")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._add_glow(brand, QColor(108, 207, 246, 100), blur=25)
        content.addWidget(brand)

        subtitle = QLabel("SECURE PROJECT WORKSPACE")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(subtitle)
        content.addSpacing(6)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        content.addWidget(divider)
        content.addSpacing(18)

        # Welcome
        welcome = QLabel("Welcome Back")
        welcome.setObjectName("welcome")
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(welcome)

        sign_in = QLabel("Sign in to continue to your project")
        sign_in.setObjectName("signIn")
        sign_in.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(sign_in)
        content.addSpacing(22)

        # Username
        user_label = QLabel("👤   USERNAME")
        user_label.setObjectName("fieldLabel")
        content.addWidget(user_label)
        content.addSpacing(4)

        self.username_input = GlowLineEdit()
        self.username_input.setPlaceholderText("Enter your username")
        self.username_input.setToolTip("Your PipeAgent username")
        content.addWidget(self.username_input)
        content.addSpacing(14)

        # Password
        pass_label = QLabel("🔒   PASSWORD")
        pass_label.setObjectName("fieldLabel")
        content.addWidget(pass_label)
        content.addSpacing(4)

        pass_row = QHBoxLayout()
        pass_row.setSpacing(0)

        self.password_input = GlowLineEdit()
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setToolTip("Your PipeAgent password")
        pass_row.addWidget(self.password_input)

        self.toggle_pw_btn = QPushButton("👁")
        self.toggle_pw_btn.setObjectName("togglePw")
        self.toggle_pw_btn.setFixedSize(46, 46)
        self.toggle_pw_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_pw_btn.setCheckable(True)
        self.toggle_pw_btn.setToolTip("Show / hide password")
        self.toggle_pw_btn.toggled.connect(self._toggle_password_visibility)
        pass_row.addWidget(self.toggle_pw_btn)

        content.addLayout(pass_row)
        content.addSpacing(12)

        # Remember + forgot
        opt_row = QHBoxLayout()

        self.remember_check = QCheckBox("  Remember me")
        self.remember_check.setObjectName("remember")
        self.remember_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remember_check.setToolTip("Remember your username on this machine")
        opt_row.addWidget(self.remember_check)
        opt_row.addStretch()

        forgot = QLabel(
            '<a href="#" style="color:#9fe7ff;text-decoration:none;">'
            'Forgot password?</a>'
        )
        forgot.setObjectName("forgot")
        forgot.setOpenExternalLinks(False)
        forgot.linkActivated.connect(self._on_forgot_password)
        opt_row.addWidget(forgot)

        content.addLayout(opt_row)
        content.addSpacing(20)

        # Status message area
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusMsg")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setMinimumHeight(18)
        content.addWidget(self.status_label)
        content.addSpacing(6)

        # Buttons
        self.login_btn = GlowButton("🔓   SIGN IN", primary=True)
        self.login_btn.setObjectName("loginBtn")
        self.login_btn.setDefault(True)
        self.login_btn.setToolTip("Sign in (Enter)")
        self.login_btn.clicked.connect(self._attempt_login)
        content.addWidget(self.login_btn)
        content.addSpacing(8)

        self.cancel_btn = GlowButton("Cancel", primary=False)
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setToolTip("Cancel and close")
        self.cancel_btn.clicked.connect(self.reject)
        content.addWidget(self.cancel_btn)

        content.addStretch()

        # Footer
        footer = QLabel("⚡  PipeAgent 5.0  •  Piping Execution Engine")
        footer.setObjectName("footer")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(footer)

        reassurance = QLabel(
            "🛡  Your project data stays in your configured workspace"
        )
        reassurance.setObjectName("reassurance")
        reassurance.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(reassurance)

        # Combine card layout
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        card_layout.addLayout(topbar)
        card_layout.addLayout(content)

        # ── Key navigation ───────────────────────────────────
        self.username_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self._attempt_login)

    # ── First-show focus ──────────────────────────────────────
    def showEvent(self, event: QShowEvent):  # noqa: N802
        super().showEvent(event)
        if not self._first_show_handled:
            self._first_show_handled = True
            QTimer.singleShot(150, self.username_input.setFocus)

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
                font-size: 26px;
                font-weight: 900;
                letter-spacing: 6px;
                background: transparent;
                padding-top: 4px;
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
            QLabel#welcome {{
                color: {self.TEXT_MAIN};
                font-size: 20px;
                font-weight: 700;
                background: transparent;
            }}
            QLabel#signIn {{
                color: {self.TEXT_MUTED};
                font-size: 11px;
                background: transparent;
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
                font-size: 13px;
                font-family: "Segoe UI", sans-serif;
                selection-background-color: {self.PRIMARY};
                selection-color: {self.BG_APP};
            }}
            QLineEdit:hover {{ border: 1px solid #2c5478; }}
            QLineEdit:focus {{
                border: 1px solid {self.PRIMARY};
                background: #0d1f30;
            }}
            QPushButton#togglePw {{
                background: {self.BG_INPUT};
                color: {self.TEXT_MUTED};
                border: 1px solid #1e3d5a;
                border-left: none;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                font-size: 14px;
            }}
            QPushButton#togglePw:hover {{
                color: {self.PRIMARY_LIGHT};
                background: #0d1f30;
            }}
            QPushButton#togglePw:checked {{ color: {self.ACCENT}; }}
            QCheckBox#remember {{
                color: {self.TEXT_MUTED};
                font-size: 11px;
                background: transparent;
                spacing: 4px;
            }}
            QCheckBox#remember::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid #2c5478;
                border-radius: 4px;
                background: {self.BG_INPUT};
            }}
            QCheckBox#remember::indicator:hover {{
                border: 1px solid {self.PRIMARY};
            }}
            QCheckBox#remember::indicator:checked {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {self.PRIMARY},
                    stop:1 {self.ACCENT}
                );
                border: 1px solid {self.PRIMARY};
                image: none;
            }}
            QLabel#forgot {{
                background: transparent;
                font-size: 11px;
            }}
            QLabel#statusMsg {{
                color: {self.ERROR};
                font-size: 11px;
                font-weight: 600;
                background: transparent;
            }}
            QPushButton#loginBtn {{
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
            QPushButton#loginBtn:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {self.ACCENT},
                    stop:0.5 {self.PRIMARY_LIGHT},
                    stop:1 {self.ACCENT}
                );
            }}
            QPushButton#loginBtn:pressed {{ background: #2196d4; }}
            QPushButton#loginBtn:disabled {{
                background: #1a3d54;
                color: #5a7a8a;
            }}
            QPushButton#cancelBtn {{
                background: transparent;
                color: {self.TEXT_MUTED};
                border: 1px solid #1e3d5a;
                border-radius: 10px;
                font-size: 12px;
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

    # ── Password visibility ───────────────────────────────────
    def _toggle_password_visibility(self, checked: bool):
        if checked:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_pw_btn.setText("🙈")
        else:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_pw_btn.setText("👁")

    def _reset_password_toggle(self):
        """Force the password field back to hidden state."""
        self.toggle_pw_btn.setChecked(False)  # triggers _toggle_password_visibility

    # ── Forgot password ───────────────────────────────────────
    def _on_forgot_password(self):
        QMessageBox.information(
            self,
            "Forgot Password",
            "Please contact your project administrator to reset your password.",
        )

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
        else:
            super().keyPressEvent(event)

    # ── Status messages ───────────────────────────────────────
    def _show_status(self, text: str, kind: str = "error"):
        """
        kind ∈ {"error", "success", "info"}.
        'info' is used for transient "verifying…" text — no ✓ or ⚠ icon.
        """
        color = {
            "error":   self.ERROR,
            "success": self.SUCCESS,
            "info":    self.INFO,
        }.get(kind, self.ERROR)

        icon = {"error": "⚠  ", "success": "✓  ", "info": ""}.get(kind, "")
        self.status_label.setStyleSheet(
            f"color: {color}; font-size: 11px; "
            f"font-weight: 600; background: transparent;"
        )
        self.status_label.setText(f"{icon}{text}")

    def _clear_status(self):
        self.status_label.setText("")

    # ── Shake animation ───────────────────────────────────────
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

    # ── Login flow ────────────────────────────────────────────
    def _attempt_login(self):
        if self._is_closing:
            return

        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username or not password:
            self._show_status(
                "Please enter both username and password.", kind="error"
            )
            self._shake()
            return

        self._clear_status()
        self.login_btn.setEnabled(False)
        self.login_btn.setText("🔄   AUTHENTICATING…")
        self._show_status("Verifying credentials…", kind="info")

        # Use an owned timer so the callback can be cancelled on close.
        if self._login_timer is not None:
            self._login_timer.stop()
            self._login_timer.deleteLater()
        self._login_timer = QTimer(self)
        self._login_timer.setSingleShot(True)
        self._login_timer.timeout.connect(
            lambda u=username, p=password: self._do_login(u, p)
        )
        self._login_timer.start(400)

    def _do_login(self, username: str, password: str):
        # Guard: the dialog may have been closed during the 400 ms delay.
        if self._is_closing or not self.isVisible():
            return

        try:
            success, user, message = self.auth_service.authenticate(
                username, password
            )
        except Exception as e:
            logger.exception("Authentication error")
            success, user, message = False, None, f"Authentication error: {e}"

        if self._is_closing:
            return

        self.login_btn.setEnabled(True)
        self.login_btn.setText("🔓   SIGN IN")

        if success and user:
            self.authenticated_user = user
            self._show_status(
                "Login successful! Welcome back.", kind="success"
            )
            self._schedule_accept(400)
        else:
            self._show_status(
                message or "Invalid username or password.", kind="error"
            )
            self._shake()
            self.password_input.clear()
            self._reset_password_toggle()
            self.password_input.setFocus()

    def _schedule_accept(self, ms: int):
        if self._success_timer is not None:
            self._success_timer.stop()
            self._success_timer.deleteLater()
        self._success_timer = QTimer(self)
        self._success_timer.setSingleShot(True)
        self._success_timer.timeout.connect(self._accept_if_visible)
        self._success_timer.start(ms)

    def _accept_if_visible(self):
        if self._is_closing or not self.isVisible():
            return
        self.accept()

    def get_authenticated_user(self):
        """Return the authenticated user (only meaningful after accept())."""
        return self.authenticated_user

    # ── Graceful close ────────────────────────────────────────
    def _cleanup(self):
        """Stop every timer and animation we own. Safe to call twice."""
        if self._is_closing:
            return
        self._is_closing = True

        if hasattr(self, "_glow_ring"):
            try:
                self._glow_ring.stop()
            except RuntimeError:
                pass

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

        if self._login_timer is not None:
            self._login_timer.stop()
            self._login_timer = None

        if self._success_timer is not None:
            self._success_timer.stop()
            self._success_timer = None

    def done(self, result: int):  # noqa: D401
        """
        Intercept every closing path (accept / reject / Escape / X).
        Cleanup happens exactly once, before the dialog is destroyed.
        """
        self._cleanup()
        super().done(result)


# ════════════════════════════════════════════════════════════════
#  STANDALONE TEST
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    class MockAuthService:
        """Mock authenticator for testing."""

        def authenticate(self, username, password):
            class MockUser:
                def __init__(self, name):
                    self.username = name
                    self.full_name = name.title()

            if username == "admin" and password == "admin":
                return True, MockUser("admin"), "Success"
            return False, None, "Invalid username or password."

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    dialog = LoginDialog(MockAuthService())
    result = dialog.exec()

    if result == QDialog.DialogCode.Accepted:
        user = dialog.get_authenticated_user()
        print(f"✓ Logged in as: {user.username}")
    else:
        print("✗ Login cancelled")

    sys.exit(0)