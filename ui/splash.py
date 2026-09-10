# -*- coding: utf-8 -*-
# ui/startup_splash.py
"""
PipeAgent — Animated Startup Splash Screen (Corrected)
═══════════════════════════════════════════════════════════
Engine : PyQt6
Design : Cinematic dark-tech theme with real-time animations

Architecture change vs. previous version:
  • Frameless translucent QWidget instead of QSplashScreen + grab() loop
    → animations run at native frame rate, no CPU-heavy re-capture,
      rounded corners are truly transparent, no default click-to-hide.
  • animation_finished is emitted ONLY when both the animation has
    completed AND the host application reported readiness.
  • When the application becomes ready early, the progress bar accelerates
    instead of forcing the user to wait the full duration.
  • Fade-out via windowOpacity (graphics effects don't work on top-levels).
"""

from __future__ import annotations

import os
import random
import logging
from typing import Optional

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, QPoint, pyqtSignal,
)
from PyQt6.QtGui import (
    QFont, QPixmap, QPainter, QColor, QLinearGradient, QRadialGradient,
    QPen, QBrush, QPainterPath,
)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame,
    QGraphicsDropShadowEffect, QApplication, QPushButton,
)

logger = logging.getLogger(__name__)

# ── Branding constants (single source of truth = config.py) ──
try:
    from config import APP_VERSION
except Exception:  # standalone preview / tests
    APP_VERSION = "0.0.0"

try:
    from config import SUPPORT_PHONE
except Exception:
    SUPPORT_PHONE = "+98 916 068 4552"


# ────────────────────────────────────────────────────────────
#  ANIMATED GLOW RING
# ────────────────────────────────────────────────────────────
class GlowRing(QWidget):
    def __init__(self, parent=None, size: int = 100):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._angle = 0
        self._ring_size = size
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(30)

    def _rotate(self):
        self._angle = (self._angle + 3) % 360
        self.update()

    def stop(self):
        self._timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        radius = self._ring_size // 2 - 4

        gradient = QRadialGradient(center.x(), center.y(), radius + 10)
        gradient.setColorAt(0.0, QColor(108, 207, 246, 0))
        gradient.setColorAt(0.7, QColor(108, 207, 246, 0))
        gradient.setColorAt(0.85, QColor(108, 207, 246, 40))
        gradient.setColorAt(1.0, QColor(108, 207, 246, 0))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, radius + 10, radius + 10)

        rect = QRect(center.x() - radius, center.y() - radius, radius * 2, radius * 2)

        pen = QPen(QColor(104, 215, 255, 200), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, self._angle * 16, 120 * 16)

        pen2 = QPen(QColor(159, 231, 255, 80), 2)
        pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen2)
        painter.drawArc(rect, (self._angle + 180) * 16, 90 * 16)

        painter.setPen(QPen(QColor(108, 207, 246, 35), 1))
        inner_r = radius - 8
        painter.drawEllipse(center, inner_r, inner_r)
        painter.end()


# ────────────────────────────────────────────────────────────
#  PARTICLE FIELD
# ────────────────────────────────────────────────────────────
class ParticleField(QWidget):
    def __init__(self, parent=None, count: int = 35):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._particles = [
            {
                "x": random.uniform(0, 1),
                "y": random.uniform(0, 1),
                "vx": random.uniform(-0.0004, 0.0004),
                "vy": random.uniform(-0.0008, -0.0002),
                "r": random.uniform(1.0, 2.5),
                "alpha": random.randint(30, 100),
            }
            for _ in range(count)
        ]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def _tick(self):
        for p in self._particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            if p["y"] < -0.02:
                p["y"] = 1.02
                p["x"] = random.uniform(0, 1)
            if p["x"] < -0.02 or p["x"] > 1.02:
                p["x"] %= 1.0
        self.update()

    def stop(self):
        self._timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        w, h = self.width(), self.height()
        for p in self._particles:
            painter.setBrush(QBrush(QColor(108, 207, 246, p["alpha"])))
            d = int(p["r"] * 2)
            painter.drawEllipse(int(p["x"] * w), int(p["y"] * h), d, d)
        painter.end()


# ────────────────────────────────────────────────────────────
#  ANIMATED PROGRESS BAR
# ────────────────────────────────────────────────────────────
class GlowProgressBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(22)
        self._value = 0
        self._max = 100
        self._glow_offset = 0
        self._glow_timer = QTimer(self)
        self._glow_timer.timeout.connect(self._animate_glow)
        self._glow_timer.start(40)

    def _animate_glow(self):
        self._glow_offset = (self._glow_offset + 4) % 200
        if self._value > 0:
            self.update()

    def setValue(self, v: int):
        self._value = min(max(0, int(v)), self._max)
        self.update()

    def value(self) -> int:
        return self._value

    def stop(self):
        self._glow_timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        radius = h // 2

        path_bg = QPainterPath()
        path_bg.addRoundedRect(0, 0, w, h, radius, radius)
        painter.fillPath(path_bg, QColor(7, 17, 27))
        painter.setPen(QPen(QColor(40, 125, 165, 120), 1))
        painter.drawPath(path_bg)

        fill_w = max(0, int((self._value / max(1, self._max)) * w))
        if fill_w > 0:
            path_fill = QPainterPath()
            path_fill.addRoundedRect(0, 0, fill_w, h, radius, radius)

            grad = QLinearGradient(0, 0, fill_w, 0)
            grad.setColorAt(0.0, QColor(40, 180, 220))
            grad.setColorAt(0.5, QColor(104, 215, 255))
            grad.setColorAt(1.0, QColor(159, 231, 255))
            painter.fillPath(path_fill, QBrush(grad))

            shine_x = (self._glow_offset / 200.0) * fill_w
            shine = QRadialGradient(shine_x, h / 2, 40)
            shine.setColorAt(0.0, QColor(255, 255, 255, 70))
            shine.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillPath(path_fill, QBrush(shine))

            if fill_w > 4:
                glow = QRadialGradient(fill_w, h / 2, 20)
                glow.setColorAt(0.0, QColor(159, 231, 255, 120))
                glow.setColorAt(1.0, QColor(159, 231, 255, 0))
                painter.setBrush(QBrush(glow))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPoint(int(fill_w), h // 2), 15, 15)

        painter.setPen(QColor(255, 255, 255, 200))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self._value}%")
        painter.end()


# ────────────────────────────────────────────────────────────
#  TYPING TERMINAL LABEL
# ────────────────────────────────────────────────────────────
class TypingLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._full_text = ""
        self._char_index = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._type_char)

    def setTypingText(self, text: str, speed_ms: int = 18):
        self._full_text = text
        self._char_index = 0
        self.setText("")
        self._timer.start(speed_ms)

    def _type_char(self):
        if self._char_index < len(self._full_text):
            self._char_index += 1
            self.setText(self._full_text[: self._char_index] + "▌")
        else:
            self._timer.stop()
            self.setText(self._full_text)

    def setDirectText(self, text: str):
        self._timer.stop()
        self._full_text = text
        self._char_index = len(text)
        self.setText(text)

    def stop(self):
        self._timer.stop()


# ────────────────────────────────────────────────────────────
#  STATUS INDICATOR DOTS
# ────────────────────────────────────────────────────────────
class StatusDots(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 16)
        self._phase = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(350)

    def _tick(self):
        self._phase = (self._phase + 1) % 4
        self.update()

    def stop(self):
        self._timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            alpha = 200 if i < self._phase else 50
            painter.setBrush(QBrush(QColor(104, 215, 255, alpha)))
            painter.drawEllipse(i * 18 + 2, 4, 8, 8)
        painter.end()


# ────────────────────────────────────────────────────────────
#  MAIN SPLASH SCREEN
# ────────────────────────────────────────────────────────────
class StartupSplash(QWidget):
    """
    Frameless, translucent, animated startup splash.

    Signals
    -------
    animation_finished : emitted once, after the animation completed,
                         the application reported readiness AND the
                         fade-out finished. Connect MainWindow.show() here.
    skip_clicked       : emitted when the user presses Skip.

    Public API
    ----------
    message(text, value=None)  : update terminal text (optionally bump progress)
    finish_startup()           : tell the splash the application is ready
    finish(widget=None)        : QSplashScreen-compatible alias of finish_startup
    force_finish()             : emergency exit (emits animation_finished immediately)
    """

    animation_finished = pyqtSignal()
    skip_clicked = pyqtSignal()

    TERMINAL_STEPS = [
        "[SYS]      Establishing secure project workspace…",
        "[DB]       Initializing piping project database…",
        "[DOC]      Loading document control & revision workflow…",
        "[WJCS]     Synchronizing joint history / weld control…",
        "[QC]       Preparing inspection & NDT modules…",
        "[TEST]     Loading test package & hydrotest controls…",
        "[FIELD]    Preparing site execution workspace…",
        "[CONTROL]  Building lookahead & resource engine…",
        "[AI]       Ranking work fronts & constraint risks…",
        "[REPORT]   Loading reporting & handover engine…",
        "[CORE]     Rendering professional project dashboard…",
    ]

    FEATURES = [
        "🔗  WJCS tracks every joint from fit-up to final acceptance with full traceability.",
        "📋  Field crews create draft Fit-up & Welding reports — QC approves digitally.",
        "🔬  NDT, test packages, punch items and handover stay connected to live records.",
        "📑  Document Control keeps revisions, approvals and IFC / As-Built status visible.",
        "🏗️  One workspace for Engineering, Construction, QA/QC and Commissioning teams.",
        "🗼  Execution Control Tower prevents idle crews and equipment before it happens.",
        "🛡️  Constraint Radar exposes blockers early — supervisors act before downtime hits.",
        "✅  QA/QC module manages NCR, ITP and Punch List A/B/C with automatic workflow.",
        "🔧  Welder management with WPS/PQR, qualification expiry alerts and renewal reminders.",
        "🔩  Valve test tracking, flange torque control and gasket management all in one place.",
        "🎨  Finishing workflows: surface preparation, painting DFT, insulation and cladding.",
        "📐  As-Built ISO registry, Weld Map and MCC certificates ensure smooth turnover.",
    ]

    BG_DEEP       = "#063F46"
    BG_APP        = "#075D67"
    BG_PANEL      = "#087F8C"
    BG_TERMINAL   = "#04373D"
    PRIMARY       = "#55D2D8"
    PRIMARY_LIGHT = "#E2FFFF"
    TEXT_MUTED    = "#B7E2E5"
    TEXT_FOOTER   = "#8CC7CC"
    TERM_GREEN    = "#6ee8a5"
    SUCCESS       = "#5cffaa"

    WIDTH  = 800
    HEIGHT = 520

    def __init__(
        self,
        logo_path: Optional[str] = None,
        duration_ms: int = 6000,
        *,
        max_wait_ms: int = 45_000,
        stay_on_top: bool = True,
        parent: Optional[QWidget] = None,
    ):
        flags = (
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
        )
        if stay_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(parent, flags)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        # ── State ──
        self._total_steps = 100
        self._interval_ms = max(1, duration_ms // self._total_steps)
        self._fast_interval_ms = 8            # used once the app is ready
        self._max_wait_ms = max_wait_ms
        self._value = 0
        self._feature_index = 0
        self._step_index = 0
        self._finished = False
        self._app_ready = False
        self._waiting_for_app = False
        self._hold_message_until = -1         # progress value until which an external message is kept
        self._drag_pos: Optional[QPoint] = None

        # ── UI ──
        self._build_ui(logo_path)
        self._center_on_screen()

        # ── Timers ──
        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._animate)
        self._progress_timer.start(self._interval_ms)

        self._feature_timer = QTimer(self)
        self._feature_timer.timeout.connect(self._next_feature)
        self._feature_timer.start(2500)

        self._safety_timer = QTimer(self)
        self._safety_timer.setSingleShot(True)
        self._safety_timer.timeout.connect(self._on_safety_timeout)

        self._fade_anim: Optional[QPropertyAnimation] = None

    # ════════════════════════════════════════════════════════
    #  UI CONSTRUCTION
    # ════════════════════════════════════════════════════════
    def _build_ui(self, logo_path: Optional[str]):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Rounded host panel (the only opaque surface)
        self._host = QFrame()
        self._host.setObjectName("splashHost")
        self._host.setStyleSheet(self._host_stylesheet())
        outer.addWidget(self._host)

        c_layout = QVBoxLayout(self._host)
        c_layout.setContentsMargins(50, 24, 50, 20)
        c_layout.setSpacing(0)

        # Particles (background layer)
        self._particles = ParticleField(self._host)
        self._particles.setGeometry(0, 0, self.WIDTH, self.HEIGHT)
        self._particles.lower()

        # Logo + glow ring
        logo_container = QWidget()
        logo_container.setFixedSize(110, 110)
        logo_container.setStyleSheet("background: transparent;")
        self._glow_ring = GlowRing(logo_container, size=110)
        self._glow_ring.move(0, 0)

        self.icon_label = QLabel(logo_container)
        self.icon_label.setFixedSize(110, 110)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent;")
        self._set_icon(logo_path)

        logo_wrapper = QHBoxLayout()
        logo_wrapper.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_wrapper.addWidget(logo_container)
        c_layout.addLayout(logo_wrapper)
        c_layout.addSpacing(8)

        # Brand
        brand = QLabel("PIPE  AGENT")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._add_glow_shadow(brand, QColor(108, 207, 246, 100), blur=30)
        c_layout.addWidget(brand)

        engine = QLabel(f"V{APP_VERSION}  •  PIPING EXECUTION OPERATING SYSTEM")
        engine.setObjectName("engine")
        engine.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.addWidget(engine)
        c_layout.addSpacing(2)

        ribbon = QLabel("PIPING EXECUTION  ·  WORK FRONT  ·  QA/QC  ·  NDT  ·  TURNOVER")
        ribbon.setObjectName("ribbon")
        ribbon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.addWidget(ribbon)
        c_layout.addSpacing(18)

        # Terminal
        term_frame = QFrame()
        term_frame.setObjectName("termFrame")
        term_layout = QHBoxLayout(term_frame)
        term_layout.setContentsMargins(14, 9, 14, 9)
        term_layout.setSpacing(8)
        self._status_dots = StatusDots()
        term_layout.addWidget(self._status_dots)
        self.terminal = TypingLabel(self.TERMINAL_STEPS[0])
        self.terminal.setObjectName("terminal")
        term_layout.addWidget(self.terminal, 1)
        c_layout.addWidget(term_frame)
        c_layout.addSpacing(10)

        # Progress bar
        self.bar = GlowProgressBar()
        c_layout.addWidget(self.bar)
        c_layout.addSpacing(14)

        # Feature panel
        self._feature_frame = QFrame()
        self._feature_frame.setObjectName("featureFrame")
        self._add_glow_shadow(self._feature_frame, QColor(108, 207, 246, 40), blur=20)
        f_layout = QVBoxLayout(self._feature_frame)
        f_layout.setContentsMargins(18, 12, 18, 14)
        f_layout.setSpacing(6)
        self.feature_title = QLabel("💡   DID YOU KNOW?")
        self.feature_title.setObjectName("featureTitle")
        self.feature_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f_layout.addWidget(self.feature_title)
        self.feature = QLabel(self.FEATURES[0])
        self.feature.setObjectName("feature")
        self.feature.setWordWrap(True)
        self.feature.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f_layout.addWidget(self.feature)
        c_layout.addWidget(self._feature_frame)
        c_layout.addStretch()

        # Footer
        self.footer = QLabel(
            "⚡  Secure Piping Execution Workspace  •  Powered by AI & Field Intelligence"
            f"  •  Support: WhatsApp {SUPPORT_PHONE}"
        )
        self.footer.setObjectName("footer")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.addWidget(self.footer)

        # Skip button (real child widget → real clicks)
        self.skip_btn = QPushButton("Skip ⏭", self._host)
        self.skip_btn.setObjectName("skipBtn")
        self.skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.skip_btn.clicked.connect(self._handle_skip)
        self.skip_btn.adjustSize()
        self.skip_btn.move(self.WIDTH - self.skip_btn.width() - 16, 12)
        self.skip_btn.raise_()

    def _set_icon(self, logo_path: Optional[str]):
        if logo_path and os.path.exists(logo_path):
            pix = QPixmap(logo_path)
            if not pix.isNull():
                self.icon_label.setPixmap(
                    pix.scaled(
                        56, 56,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
            logger.warning("Splash logo could not be loaded: %s", logo_path)
        self.icon_label.setText("⚙")
        self.icon_label.setFont(QFont("Segoe UI", 36))
        self.icon_label.setStyleSheet(f"color: {self.PRIMARY_LIGHT}; background: transparent;")

    @staticmethod
    def _add_glow_shadow(widget: QWidget, color: QColor, blur: int = 20, offset=(0, 2)):
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur)
        shadow.setColor(color)
        shadow.setOffset(*offset)
        widget.setGraphicsEffect(shadow)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.center() - self.rect().center())

    def _host_stylesheet(self) -> str:
        return f"""
            QFrame#splashHost {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {self.BG_DEEP}, stop:0.4 {self.BG_APP}, stop:1 {self.BG_DEEP});
                border: 2px solid {self.PRIMARY};
                border-radius: 20px;
            }}
            QLabel#brand {{
                color: {self.PRIMARY_LIGHT}; font-size: 34px; font-weight: 900;
                letter-spacing: 8px; padding-top: 2px; background: transparent;
            }}
            QLabel#engine {{
                color: {self.PRIMARY}; font-size: 10px; font-weight: 700;
                letter-spacing: 3px; background: transparent;
            }}
            QLabel#ribbon {{
                color: {self.TEXT_MUTED}; font-size: 9px; font-weight: 600;
                letter-spacing: 2px; background: transparent;
            }}
            QFrame#termFrame {{
                background: {self.BG_TERMINAL}; border: 1px solid #0D6972; border-radius: 8px;
            }}
            QLabel#terminal {{
                color: {self.TERM_GREEN}; font-family: Consolas, "Courier New", monospace;
                font-size: 11px; background: transparent; padding: 0px;
            }}
            QLabel#terminal[state="success"] {{
                color: {self.SUCCESS}; font-weight: 600;
            }}
            QFrame#featureFrame {{
                background: {self.BG_PANEL}; border: 1px solid rgba(85, 210, 216, 0.35);
                border-radius: 10px;
            }}
            QLabel#featureTitle {{
                color: {self.PRIMARY_LIGHT}; font-size: 10px; font-weight: 800;
                letter-spacing: 2px; background: transparent;
            }}
            QLabel#feature {{
                color: #c8dcea; font-size: 12px; background: transparent;
            }}
            QLabel#feature[state="success"] {{
                color: {self.SUCCESS};
            }}
            QLabel#footer {{
                color: {self.TEXT_FOOTER}; font-size: 9px; letter-spacing: 1px;
                background: transparent;
            }}
            QPushButton#skipBtn {{
                background: rgba(20, 40, 60, 0.8); color: #9fe7ff;
                border: 1px solid rgba(108, 207, 246, 0.4); border-radius: 5px;
                padding: 4px 10px; font-size: 10px; font-weight: 600;
            }}
            QPushButton#skipBtn:hover {{
                background: rgba(40, 80, 110, 0.9); border-color: #6ccff6;
            }}
        """

    # ════════════════════════════════════════════════════════
    #  PUBLIC API
    # ════════════════════════════════════════════════════════
    def message(self, text: str, value: Optional[int] = None):
        """
        Update the terminal text from the host application.
        The message is held for a few progress points so internal
        step texts don't immediately overwrite it.
        If `value` is provided the progress never moves backwards.
        """
        if self._finished:
            return
        self.terminal.setTypingText(text)
        self._hold_message_until = min(99, self._value + 8)
        if value is not None and value > self._value:
            self._value = min(99, int(value))
            self.bar.setValue(self._value)

    def finish_startup(self):
        """Application is ready. Accelerate progress and finish when complete."""
        if self._finished or self._app_ready:
            return
        self._app_ready = True
        self._safety_timer.stop()

        if self._value >= 100 or self._waiting_for_app:
            self._show_success()
        else:
            # Speed up the remaining animation instead of forcing a wait.
            self._progress_timer.setInterval(self._fast_interval_ms)

    def finish(self, main_window: Optional[QWidget] = None):
        """QSplashScreen-compatible alias."""
        self.finish_startup()

    def force_finish(self):
        """Emergency exit without waiting for animation/app readiness."""
        if self._finished:
            return
        self._app_ready = True
        self._show_success(fade_delay_ms=0)

    # ════════════════════════════════════════════════════════
    #  ANIMATION LOOP
    # ════════════════════════════════════════════════════════
    def _animate(self):
        if self._finished:
            return

        if self._value < 100:
            self._value += 1
            self.bar.setValue(self._value)

        # Internal step text (unless an external message is being held)
        new_step = min(
            len(self.TERMINAL_STEPS) - 1,
            int((self._value / 100) * len(self.TERMINAL_STEPS)),
        )
        if new_step != self._step_index and self._value > self._hold_message_until:
            self._step_index = new_step
            if self._value < 90:
                self.terminal.setTypingText(self.TERMINAL_STEPS[self._step_index])

        if self._value >= 100:
            self._progress_timer.stop()
            if self._app_ready:
                self._show_success()
            else:
                self._enter_waiting_state()

    def _enter_waiting_state(self):
        """Animation done but the application is still booting."""
        self._waiting_for_app = True
        self.terminal.setTypingText("[SYS]      Finalizing workspace — please wait…")
        self._safety_timer.start(self._max_wait_ms)

    def _on_safety_timeout(self):
        logger.warning(
            "Splash: application did not report readiness within %d ms; forcing finish.",
            self._max_wait_ms,
        )
        self.force_finish()

    def _next_feature(self):
        if self._finished:
            return
        self._feature_index = (self._feature_index + 1) % len(self.FEATURES)
        self.feature.setText(self.FEATURES[self._feature_index])

    def _handle_skip(self):
        if self._finished:
            return
        self.skip_clicked.emit()
        self._value = 100
        self.bar.setValue(100)
        self._progress_timer.stop()
        if self._app_ready:
            self._show_success()
        else:
            self._enter_waiting_state()

    # ════════════════════════════════════════════════════════
    #  SUCCESS + FADE-OUT
    # ════════════════════════════════════════════════════════
    def _show_success(self, fade_delay_ms: int = 1000):
        if self._finished:
            return
        self._finished = True

        self._progress_timer.stop()
        self._feature_timer.stop()
        self._safety_timer.stop()
        self._glow_ring.stop()
        self._particles.stop()
        self._status_dots.stop()
        self.bar.stop()
        self.skip_btn.hide()

        self._value = 100
        self.bar.setValue(100)

        self.terminal.setDirectText("[SYS]      ✓  All systems operational — Launching workspace…")
        self._set_state(self.terminal, "success")

        self.feature_title.setText("✅   SYSTEM READY")
        self.feature.setText("Core workspace ready. Execution modules are loading in the background.")
        self._set_state(self.feature, "success")

        # Fade via windowOpacity — graphics effects don't work on top-level windows.
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(600)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._fade_anim.finished.connect(self._on_finish)
        QTimer.singleShot(max(0, fade_delay_ms), self._fade_anim.start)

    @staticmethod
    def _set_state(widget: QWidget, state: str):
        widget.setProperty("state", state)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _on_finish(self):
        self.hide()
        self.animation_finished.emit()
        self.deleteLater()

    # ════════════════════════════════════════════════════════
    #  EVENTS
    # ════════════════════════════════════════════════════════
    def mousePressEvent(self, event):
        # Allow dragging; never hide on click (unlike QSplashScreen).
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        event.accept()

    def closeEvent(self, event):
        for t in (self._progress_timer, self._feature_timer, self._safety_timer):
            t.stop()
        self._glow_ring.stop()
        self._particles.stop()
        self._status_dots.stop()
        self.bar.stop()
        self.terminal.stop()
        super().closeEvent(event)