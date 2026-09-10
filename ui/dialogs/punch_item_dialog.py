# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Punch Item Registration Dialog
═══════════════════════════════════════════════════════════════════════
Version : 5.0 (Refactored, hardened, production-ready)
Engine  : PyQt6
Design  : Cinematic dark-tech theme matching PipeAgent Suite

Fixes in this revision
──────────────────────
🔴 P0  Card border       : replaced invalid `border: ... qlineargradient`
                          (QSS does not support gradients in `border`)
                          with a solid color + drop shadow
🔴 P0  GlowLineEdit      : no longer calls deleteLater() on an animation
                          that Qt owns (DeleteWhenStopped)
🔴 P0  _shake            : same lifetime fix
🔴 P0  _cleanup          : now idempotent via `_is_closed` flag; safe to
                          call from reject / closeEvent / done
🟠 P1  Particle geometry  : set immediately after creation
🟠 P1  done() override    : cleanup runs exactly once on every close path
🟠 P1  target_clear_date  : loaded when editing an existing punch
🟠 P1  date parsing       : tolerant helper handles date/datetime/ISO string
🟡 P2  ParticleField      : count 26 → 14, tick 60ms → 100ms, paints only
                          when visible
🟡 P2  QDateEdit height   : minimumHeight(38) for visual consistency
🟡 P2  Category refresh   : driven by the combobox's currentData(), not by
                          a hardcoded index
🟢 P3  Tooltips           : on every field
🟢 P3  _today() helper    : single source for the current date string
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
    from core.constants import PUNCH_CATEGORIES, PUNCH_CATEGORY_DESC
except ImportError:
    PUNCH_CATEGORIES = ["A", "B", "C"]
    PUNCH_CATEGORY_DESC = {
        "A": "Critical Defect — Must clear BEFORE Hydrotest / Pressure Test",
        "B": "Major Defect — Must clear BEFORE Mechanical Completion (Pre-MC)",
        "C": "Minor / Cosmetic — Clear before Final Handover / Commissioning",
    }


# ════════════════════════════════════════════════════════════════
#  UTILITIES
# ════════════════════════════════════════════════════════════════

def _today() -> date:
    return date.today()


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
#  GLOW INPUT COMPONENTS
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


class GlowTextEdit(QTextEdit):
    """QTextEdit with custom right-click context menu and standard templates."""

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

        menu_tpl = menu.addMenu("📝  Insert Standard Piping Punch Template")

        tpls = [
            (
                "Missing Blind / Vent Plug",
                "• Condition: High-point vent flange missing spectacle blind / threaded plug.\n"
                "• Rectification: Install approved CS plug & torque per spec."
            ),
            (
                "Incomplete Weld / Undercut",
                "• Condition: Visual undercut > 0.5mm observed at root/cap of weld joint.\n"
                "• Rectification: Grind smooth, perform PT examination, reweld if required."
            ),
            (
                "Support / Spring Hanger Locked",
                "• Condition: Pipe spring hanger travel stops not removed prior to hydrotest.\n"
                "• Rectification: Verify cold setting position and unlock travel stops."
            ),
            (
                "Valve Flow Direction Inverted",
                "• Condition: Globe / Check valve installed opposite to process flow arrow.\n"
                "• Rectification: Reverse valve body orientation, replace gasket with new spiral-wound."
            ),
            (
                "Coating & Paint Touch-up",
                "• Condition: Field weld joint unpainted with surface flash rust.\n"
                "• Rectification: Power tool clean to St3 and apply 2 coats of 3-layer primer system."
            ),
        ]

        for title, text in tpls:
            act = QAction(title, self)
            # Capture `text` in the lambda default argument to avoid the
            # late-binding closure bug.
            act.triggered.connect(lambda checked=False, t=text: self.setPlainText(t))
            menu_tpl.addAction(act)

        # PyQt6: QContextMenuEvent.globalPos() is still valid.
        menu.exec(event.globalPos())


# ════════════════════════════════════════════════════════════════
#  MAIN PUNCH ITEM DIALOG
# ════════════════════════════════════════════════════════════════

class PunchItemDialog(QDialog):
    """
    Ultra-premium Punch List Item Creation & Clearance Center.
    Frameless, responsive, resizable, ergonomic.
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

    MIN_WIDTH  = 920
    MIN_HEIGHT = 640
    DEF_WIDTH  = 1020
    DEF_HEIGHT = 740

    def __init__(self, parent=None, punch_data: Optional[dict] = None):
        super().__init__(parent)
        self.punch_data: Dict[str, Any] = punch_data or {}
        self.result_data: Dict[str, Any] = {}

        # Drag / resize state
        self._drag_pos: Optional[QPoint] = None
        self._drag_edge: Optional[str] = None
        self._drag_geometry: Optional[QRect] = None
        self._resize_margin = 8

        # Lifecycle & animations
        self._is_closed = False
        self._shake_anim: Optional[QPropertyAnimation] = None

        self.setWindowTitle("PipeAgent – Create Punch Item")
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
        card_layout.addWidget(self._build_category_banner())

        # ── Splitter Dashboard (Left vs Right) ───────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        splitter.setHandleWidth(3)
        splitter.setChildrenCollapsible(False)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([480, 500])

        card_layout.addWidget(splitter, 1)
        card_layout.addLayout(self._build_footer())

        # Prime the category banner based on the current combobox selection.
        self._refresh_category_banner()

    def _build_topbar(self) -> QHBoxLayout:
        topbar = QHBoxLayout()
        topbar.setContentsMargins(0, 0, 0, 0)

        icon_lbl = QLabel("📌")
        icon_lbl.setFont(QFont("Segoe UI", 20))
        icon_lbl.setStyleSheet("background: transparent;")
        topbar.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)

        main_title = QLabel("PIPE AGENT  •  PUNCH LIST ENGINE")
        main_title.setObjectName("mainTitle")
        self._add_glow(main_title, QColor(108, 207, 246, 120), blur=20)
        title_col.addWidget(main_title)

        sub_title = QLabel(
            "WALKDOWN INSPECTION  •  TEST PACK CLEARANCE  •  PRE-HYDROTEST (CAT A/B/C)"
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

    def _build_category_banner(self) -> QFrame:
        self.cat_banner = QFrame()
        self.cat_banner.setObjectName("catBanner")
        cat_layout = QHBoxLayout(self.cat_banner)
        cat_layout.setContentsMargins(14, 8, 14, 8)
        cat_layout.setSpacing(12)

        self.cat_icon_lbl = QLabel("⚠️")
        self.cat_icon_lbl.setFont(QFont("Segoe UI", 16))
        self.cat_icon_lbl.setStyleSheet("background: transparent;")
        cat_layout.addWidget(self.cat_icon_lbl)

        cat_col = QVBoxLayout()
        cat_col.setSpacing(1)

        self.cat_title_lbl = QLabel(
            "CATEGORY A — CRITICAL PRE-HYDROTEST DEFECT"
        )
        self.cat_title_lbl.setObjectName("catTitle")
        self.cat_title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        cat_col.addWidget(self.cat_title_lbl)

        self.cat_desc_lbl = QLabel(PUNCH_CATEGORY_DESC.get("A", ""))
        self.cat_desc_lbl.setStyleSheet(
            "color: #a2c2dc; font-size: 10px; background: transparent;"
        )
        cat_col.addWidget(self.cat_desc_lbl)

        cat_layout.addLayout(cat_col, 1)
        return self.cat_banner

    def _build_left_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("formGroup")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel("🏷️   PUNCH IDENTIFICATION & SYSTEM")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("panelScroll")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        form = QVBoxLayout(inner)
        form.setSpacing(8)

        # Category
        form.addWidget(QLabel("PUNCH CATEGORY *"))
        self.cmb_cat = QComboBox()
        self.cmb_cat.setObjectName("glowCombo")
        self.cmb_cat.setMinimumHeight(38)
        for c in PUNCH_CATEGORIES:
            desc = PUNCH_CATEGORY_DESC.get(c, "")
            short = desc.split(" — ")[0] if " — " in desc else desc
            self.cmb_cat.addItem(f"Category {c}  •  {short}", c)
        self.cmb_cat.setToolTip("Punch severity category — A/B/C")
        self.cmb_cat.currentIndexChanged.connect(self._refresh_category_banner)
        form.addWidget(self.cmb_cat)

        # Punch Tag
        form.addWidget(QLabel("PUNCH ITEM TAG / ID"))
        self.txt_punch_tag = GlowLineEdit()
        self.txt_punch_tag.setPlaceholderText("e.g. PCH-TP2104-001 (Auto if empty)")
        self.txt_punch_tag.setToolTip("Unique punch identifier (auto-generated if empty)")
        form.addWidget(self.txt_punch_tag)

        # Line Number
        form.addWidget(QLabel("LINE NUMBER / SYSTEM"))
        self.txt_line = GlowLineEdit()
        self.txt_line.setPlaceholderText('e.g. 12"-PR-2104-A1A')
        self.txt_line.setToolTip("Piping line or system identifier")
        form.addWidget(self.txt_line)

        # Spool & Weld
        row1 = QHBoxLayout()
        col_spool = QVBoxLayout()
        col_spool.addWidget(QLabel("SPOOL NUMBER"))
        self.txt_spool = GlowLineEdit()
        self.txt_spool.setPlaceholderText("e.g. SP-2104-02")
        self.txt_spool.setToolTip("Related spool identifier")
        col_spool.addWidget(self.txt_spool)
        row1.addLayout(col_spool)

        col_weld = QVBoxLayout()
        col_weld.addWidget(QLabel("WELD NUMBER / JOINT ID"))
        self.txt_weld = GlowLineEdit()
        self.txt_weld.setPlaceholderText("e.g. W-14")
        self.txt_weld.setToolTip("Related weld joint identifier")
        col_weld.addWidget(self.txt_weld)
        row1.addLayout(col_weld)
        form.addLayout(row1)

        # Location
        form.addWidget(QLabel("PHYSICAL LOCATION / ELEVATION / GRID"))
        self.txt_location = GlowLineEdit()
        self.txt_location.setPlaceholderText("e.g. Unit 100 • Rack-02 • EL +14.500m")
        self.txt_location.setToolTip("Physical location of the punch item")
        form.addWidget(self.txt_location)

        # Raised By & Date
        row2 = QHBoxLayout()
        col_by = QVBoxLayout()
        col_by.addWidget(QLabel("RAISED BY (INSPECTOR)"))
        self.txt_raised_by = GlowLineEdit()
        self.txt_raised_by.setPlaceholderText("e.g. Eng. Mohammadi (QC)")
        self.txt_raised_by.setToolTip("Name of the QC inspector")
        col_by.addWidget(self.txt_raised_by)
        row2.addLayout(col_by)

        col_date = QVBoxLayout()
        col_date.addWidget(QLabel("DATE RAISED"))
        self.dte_date = QDateEdit()
        self.dte_date.setObjectName("glowDate")
        self.dte_date.setMinimumHeight(38)
        self.dte_date.setCalendarPopup(True)
        self.dte_date.setDate(QDate.currentDate())
        self.dte_date.setToolTip("Date the punch was raised")
        col_date.addWidget(self.dte_date)
        row2.addLayout(col_date)
        form.addLayout(row2)

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

        title = QLabel("🛠️   TECHNICAL DISCIPLINE & RECTIFICATION")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("panelScroll")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        form = QVBoxLayout(inner)
        form.setSpacing(8)

        # Discipline & Target Date
        row3 = QHBoxLayout()
        col_disc = QVBoxLayout()
        col_disc.addWidget(QLabel("DISCIPLINE"))
        self.cmb_discipline = QComboBox()
        self.cmb_discipline.setObjectName("glowCombo")
        self.cmb_discipline.setMinimumHeight(38)
        self.cmb_discipline.addItems([
            "Piping Erection", "Welding / NDT", "Supports & Hangers",
            "Valves & In-line Items", "Painting & Insulation",
            "Instrumentation",
        ])
        self.cmb_discipline.setToolTip("Discipline responsible for clearance")
        col_disc.addWidget(self.cmb_discipline)
        row3.addLayout(col_disc)

        col_target = QVBoxLayout()
        col_target.addWidget(QLabel("TARGET CLEARANCE DATE"))
        self.dte_target = QDateEdit()
        self.dte_target.setObjectName("glowDate")
        self.dte_target.setMinimumHeight(38)
        self.dte_target.setCalendarPopup(True)
        self.dte_target.setDate(QDate.currentDate().addDays(3))
        self.dte_target.setToolTip("Target date for punch clearance")
        col_target.addWidget(self.dte_target)
        row3.addLayout(col_target)
        form.addLayout(row3)

        # Description
        form.addWidget(QLabel("PUNCH DEFECT DESCRIPTION *  (Right-click for templates)"))
        self.txt_desc = GlowTextEdit()
        self.txt_desc.setPlaceholderText(
            "Describe the exact non-conformance or defect... "
            "(Right-click to insert standard piping template)"
        )
        self.txt_desc.setToolTip("Detailed defect description — required")
        form.addWidget(self.txt_desc)

        # Action Required
        form.addWidget(QLabel("ACTION REQUIRED TO CLEAR PUNCH"))
        self.txt_action = GlowTextEdit()
        self.txt_action.setPlaceholderText(
            "Describe rectification action needed by construction crew..."
        )
        self.txt_action.setToolTip("Rectification action required to clear this punch")
        form.addWidget(self.txt_action)

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
            "color: #ff6b6b; font-size: 11px; font-weight: bold; "
            "background: transparent;"
        )
        footer.addWidget(self.lbl_warning, 1)

        self.btn_save = QPushButton("⚡  SAVE PUNCH ITEM  (Ctrl+S)")
        self.btn_save.setObjectName("saveBtn")
        self.btn_save.setMinimumHeight(42)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setToolTip("Save punch item (Ctrl+S)")
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

    # ── Load Existing Data (for editing mode) ────────────────
    def _load_existing_data(self):
        if not self.punch_data:
            return

        self.setWindowTitle("PipeAgent – Edit Punch Item")

        # Category by data value (not by index — combobox rows may change)
        cat = str(self.punch_data.get("category", "A")).upper()
        idx = self.cmb_cat.findData(cat)
        if idx >= 0:
            self.cmb_cat.setCurrentIndex(idx)
            # currentIndexChanged fired → banner refresh, but call again
            # in case the index was already at 0.
            self._refresh_category_banner()

        self.txt_punch_tag.setText(str(self.punch_data.get("punch_tag", "")))
        self.txt_line.setText(str(self.punch_data.get("line_number", "")))
        self.txt_spool.setText(str(self.punch_data.get("spool_number", "")))
        self.txt_weld.setText(str(self.punch_data.get("weld_id", "")))
        self.txt_location.setText(str(self.punch_data.get("location_desc", "")))
        self.txt_raised_by.setText(str(self.punch_data.get("raised_by", "")))
        self.txt_desc.setPlainText(str(self.punch_data.get("description", "")))
        self.txt_action.setPlainText(
            str(self.punch_data.get("action_required", ""))
        )

        # Discipline
        disc = self.punch_data.get("discipline", "")
        d_idx = self.cmb_discipline.findText(disc)
        if d_idx >= 0:
            self.cmb_discipline.setCurrentIndex(d_idx)

        # Dates — tolerant of date / datetime / ISO string
        raised = _parse_date(self.punch_data.get("raised_date"))
        if raised is not None:
            self.dte_date.setDate(QDate(raised.year, raised.month, raised.day))

        target = _parse_date(self.punch_data.get("target_clear_date"))
        if target is not None:
            self.dte_target.setDate(
                QDate(target.year, target.month, target.day)
            )

    # ── Category Banner Refresh ───────────────────────────────
    def _refresh_category_banner(self, *_):
        """Update the banner using the combobox's currentData()."""
        cat = self.cmb_cat.currentData()

        if cat == "A":
            bg, border, fg = "#2a0d11", "#ff6b6b", "#ff6b6b"
            icon = "🚨"
            title = "CATEGORY A — CRITICAL PRE-HYDROTEST PUNCH"
        elif cat == "B":
            bg, border, fg = "#2a220a", "#ffd966", "#ffd966"
            icon = "⏳"
            title = "CATEGORY B — PRE-MECHANICAL COMPLETION (PRE-MC)"
        else:
            bg, border, fg = "#081e28", "#6ccff6", "#6ccff6"
            icon = "ℹ️"
            title = "CATEGORY C — MINOR / PRE-COMMISSIONING ITEM"

        desc = PUNCH_CATEGORY_DESC.get(cat, "")

        self.cat_icon_lbl.setText(icon)
        self.cat_title_lbl.setText(title)
        self.cat_title_lbl.setStyleSheet(
            f"color: {fg}; font-size: 11px; font-weight: 800; "
            f"background: transparent;"
        )
        self.cat_desc_lbl.setText(desc)

        self.cat_banner.setStyleSheet(f"""
            QFrame#catBanner {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)

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
            QComboBox#glowCombo, QDateEdit#glowDate {{
                background: {self.BG_INPUT};
                color: {self.TEXT_MAIN};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QComboBox#glowCombo:hover, QDateEdit#glowDate:hover {{
                border: 1px solid {self.PRIMARY};
            }}
            QComboBox#glowCombo QAbstractItemView {{
                background: #07101a;
                color: {self.TEXT_MAIN};
                selection-background-color: #14334f;
                selection-color: {self.PRIMARY_LIGHT};
                border: 1px solid #1e3d5a;
            }}
            QCalendarWidget QWidget {{
                background-color: #0b1624;
                color: #eef6ff;
            }}
            QCalendarWidget QAbstractItemView {{
                background-color: #07101a;
                selection-background-color: #14334f;
                selection-color: #6ccff6;
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

        desc = self.txt_desc.toPlainText().strip()

        if not desc:
            self.lbl_warning.setText(
                "⚠️ Validation Error: Punch Description is required."
            )
            self._shake()
            self.txt_desc.setFocus()
            return

        self.lbl_warning.setText("")

        punch_tag = self.txt_punch_tag.text().strip()
        if not punch_tag:
            punch_tag = (
                f"PCH-{self.cmb_cat.currentData()}-"
                f"{datetime.now().strftime('%H%M%S')}"
            )

        self.result_data = {
            "category": self.cmb_cat.currentData(),
            "punch_tag": punch_tag,
            "line_number": self.txt_line.text().strip(),
            "spool_number": self.txt_spool.text().strip(),
            "weld_id": self.txt_weld.text().strip(),
            "location_desc": self.txt_location.text().strip(),
            "raised_by": self.txt_raised_by.text().strip(),
            "raised_date": self.dte_date.date().toPyDate(),
            "discipline": self.cmb_discipline.currentText(),
            "target_clear_date": self.dte_target.date().toPyDate(),
            "description": desc,
            "action_required": self.txt_action.toPlainText().strip(),
            "status": "OPEN",
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

    mock_punch = {
        "category": "A",
        "punch_tag": "PCH-01-PR-2104-001",
        "line_number": '12"-PR-2104-A1A',
        "spool_number": "SP-2104-01",
        "weld_id": "W-04",
        "location_desc": "Unit 100 • Column C-12 • EL +18.200m",
        "raised_by": "Eng. Kaveh (Lead QC)",
        "raised_date": date.today(),
        "discipline": "Piping Erection",
        "target_clear_date": date.today(),
        "description": (
            "Flange pair bolted without temporary hydrotest blind at "
            "battery limit."
        ),
        "action_required": (
            "Install Class 300 test blind and torque bolts per procedure "
            "before filling line."
        ),
    }

    dialog = PunchItemDialog(punch_data=mock_punch)
    dialog.show()
    dialog.exec()

    if getattr(dialog, "result_data", None):
        print("Punch Registered Data:", dialog.result_data)

    sys.exit(0)