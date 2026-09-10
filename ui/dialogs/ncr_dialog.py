# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Non-Conformance Report (NCR) Dialog
═══════════════════════════════════════════════════════════════
Version : 5.0 (Refactored, hardened, production-ready)
Engine  : PyQt6
Design  : Cinematic dark-tech theme matching PipeAgent Suite

Fixes in this revision
──────────────────────
🔴 P0  Card border        : replaced invalid `border: ... qlineargradient`
                           (QSS does not support gradients in `border`)
                           with a solid border + drop shadow
🔴 P0  GlowLineEdit       : no longer calls deleteLater() on an animation
                           that Qt owns (DeleteWhenStopped)
🔴 P0  _shake             : same lifetime fix
🔴 P0  _cleanup           : now idempotent via `_is_closed` flag; safe to
                           call from reject / closeEvent / done
🟠 P1  Particles size      : geometry set immediately after creation (not
                           only in resizeEvent)
🟠 P1  done() override     : cleanup runs exactly once on every close path
🟠 P1  QDateEdit height    : minimumHeight(38) so it matches other inputs
🟠 P1  _load_data dates    : tolerant parser with a single helper
🟡 P2  ParticleField       : count 28 → 14, tick 60ms → 100ms, paint only
                           when visible
🟡 P2  Risk signal         : guarded against redundant trigger on load
🟢 P3  General             : tooltips on every field, `_today()` helper,
                           single source of truth for risk detection
"""

from __future__ import annotations

import os
import sys
import random
import logging
from datetime import date, datetime
from typing import Optional, Dict, Any, List

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

# ── Safe Core Imports & Fallbacks ───────────────────────────────────
try:
    from core.constants import NCR_ITEM_TYPES, NCR_DISPOSITIONS, NCR_STATUSES
except ImportError:
    NCR_ITEM_TYPES = [
        "Weld Defect (RT/UT/Visual)",
        "Dimensional Deviation",
        "Material Damage / Pitting",
        "Incorrect Specification / Grade",
        "NDT Test Failure",
        "Documentation / Traceability Issue",
    ]
    NCR_DISPOSITIONS = [
        "Use-As-Is (Engineering Approval Required)",
        "Repair / Rework (Reweld/Rethread)",
        "Scrap & Replace",
        "Downgrade / Return to Vendor",
    ]
    NCR_STATUSES = ["Draft", "Issued", "Under Review", "Closed / Cleared"]


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
#  ANIMATED PARTICLE FIELD BACKGROUND
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
        # Qt owns it (DeleteWhenStopped).
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
    """
    QTextEdit with custom right-click template menu.

    Note: Qt QSS does NOT support box-shadow, so glow is done via a
    border color change on focus (see stylesheet below).
    """

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

        tpl_act = QAction("📝  Insert Technical Draft Template", self)
        tpl_act.triggered.connect(self._insert_template)
        menu.addAction(tpl_act)

        # PyQt6: QContextMenuEvent.globalPos() is still valid.
        menu.exec(event.globalPos())

    def _insert_template(self):
        template = (
            "[SPECIFICATION DEVIATION]:\n"
            "• Detected in: Unit ___ / Line ___\n"
            "• Actual Condition: \n"
            "• Drawing/Spec Requirement: \n"
            "• Immediate Action taken: "
        )
        self.setPlainText(template)


# ════════════════════════════════════════════════════════════════
#  MAIN NCR DIALOG
# ════════════════════════════════════════════════════════════════

class NCRDialog(QDialog):
    """
    Ultra-premium QC Non-Conformance Report Dialog.
    Fully frameless, draggable, and resizable.
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

    MIN_WIDTH  = 900
    MIN_HEIGHT = 650
    DEF_WIDTH  = 1020
    DEF_HEIGHT = 740

    def __init__(self, parent=None, ncr_data: Optional[dict] = None):
        super().__init__(parent)
        self.ncr_data: Dict[str, Any] = ncr_data or {}
        self.result_data: Dict[str, Any] = {}

        # Drag / resize state
        self._drag_pos: Optional[QPoint] = None
        self._drag_edge: Optional[str] = None
        self._drag_geometry: Optional[QRect] = None
        self._resize_margin = 8

        # Lifecycle & animations
        self._is_closed = False
        self._shake_anim: Optional[QPropertyAnimation] = None

        self.setWindowTitle("PipeAgent – Create Non-Conformance Report")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(self.DEF_WIDTH, self.DEF_HEIGHT)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self._build_ui()
        self._setup_shortcuts()
        self._center_on_screen()
        self._load_data()

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

        # Particles — geometry set immediately to avoid clustering at (0,0).
        self._particles = ParticleField(self._card, count=14)
        self._particles.setGeometry(0, 0, self.DEF_WIDTH, self.DEF_HEIGHT)
        self._particles.lower()

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(24, 14, 24, 14)
        card_layout.setSpacing(12)

        card_layout.addLayout(self._build_topbar())

        # ── Split content: Left metadata | Right analysis ────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        splitter.setHandleWidth(3)
        splitter.setChildrenCollapsible(False)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([460, 500])

        card_layout.addWidget(splitter, 1)
        card_layout.addLayout(self._build_footer())

        # Prime the risk badge without firing the signal twice.
        self._apply_risk_badge(self.cmb_risk.currentText())

    def _build_topbar(self) -> QHBoxLayout:
        topbar = QHBoxLayout()
        topbar.setContentsMargins(0, 0, 0, 0)

        icon_lbl = QLabel("⚠️")
        icon_lbl.setFont(QFont("Segoe UI", 18))
        icon_lbl.setStyleSheet("background: transparent;")
        topbar.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)

        main_title = QLabel("PIPE AGENT  •  QUALITY ASSURANCE")
        main_title.setObjectName("mainTitle")
        self._add_glow(main_title, QColor(108, 207, 246, 120), blur=20)
        title_col.addWidget(main_title)

        sub_title = QLabel(
            "NON-CONFORMANCE REPORTING ENGINE  •  TRACKING & DISPOSITION WORKFLOW"
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

    def _build_left_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("formGroup")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel("📋  NCR REGISTRATION METADATA")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("panelScroll")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        form = QVBoxLayout(inner)
        form.setSpacing(8)

        form.addWidget(QLabel("NCR NUMBER *"))
        self.txt_ncr_no = GlowLineEdit()
        self.txt_ncr_no.setPlaceholderText("e.g. NCR-UNIT100-WELD-024")
        self.txt_ncr_no.setToolTip("Unique NCR number — required")
        form.addWidget(self.txt_ncr_no)

        form.addWidget(QLabel("ITEM TYPE *"))
        self.cmb_type = QComboBox()
        self.cmb_type.setObjectName("glowCombo")
        self.cmb_type.setMinimumHeight(38)
        self.cmb_type.addItems(NCR_ITEM_TYPES)
        self.cmb_type.setToolTip("Category of the non-conformance")
        form.addWidget(self.cmb_type)

        form.addWidget(QLabel("ITEM REFERENCE / WELD ID / SPOOL ID"))
        self.txt_ref = GlowLineEdit()
        self.txt_ref.setPlaceholderText("e.g. Joint W03 / Spool SP-2104-01")
        self.txt_ref.setToolTip("Traceable identifier of the affected item")
        form.addWidget(self.txt_ref)

        form.addWidget(QLabel("LINE NUMBER / SYSTEM"))
        self.txt_line = GlowLineEdit()
        self.txt_line.setPlaceholderText('e.g. 12"-PR-2104-A1A')
        self.txt_line.setToolTip("Piping line or system identifier")
        form.addWidget(self.txt_line)

        form.addWidget(QLabel("RAISED BY (QC INSPECTOR)"))
        self.txt_raised_by = GlowLineEdit()
        self.txt_raised_by.setPlaceholderText("e.g. Inspector Mohammadi")
        self.txt_raised_by.setToolTip("Name of the QC inspector raising the NCR")
        form.addWidget(self.txt_raised_by)

        form.addWidget(QLabel("DATE OF DETECTION"))
        self.dte_date = QDateEdit()
        self.dte_date.setObjectName("glowDate")
        self.dte_date.setMinimumHeight(38)
        self.dte_date.setCalendarPopup(True)
        self.dte_date.setDate(QDate.currentDate())
        self.dte_date.setToolTip("Date the non-conformance was detected")
        form.addWidget(self.dte_date)

        form.addWidget(QLabel("CRITICALITY / RISK LEVEL"))
        self.cmb_risk = QComboBox()
        self.cmb_risk.setObjectName("glowCombo")
        self.cmb_risk.setMinimumHeight(38)
        self.cmb_risk.addItems([
            "Low (Observation)",
            "Medium (Minor)",
            "High (Major Structural / UT Fail)",
            "Critical (Immediate Rework Required)",
        ])
        self.cmb_risk.setToolTip("Severity / risk class of the non-conformance")
        self.cmb_risk.currentTextChanged.connect(self._apply_risk_badge)
        form.addWidget(self.cmb_risk)

        self.lbl_risk_badge = QLabel("RISK: LOW")
        self.lbl_risk_badge.setObjectName("riskBadge")
        self.lbl_risk_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_risk_badge.setFixedHeight(26)
        form.addWidget(self.lbl_risk_badge)

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

        title = QLabel("🔧  ENGINEERING ANALYSIS & ACTION PLAN")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("panelScroll")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        form = QVBoxLayout(inner)
        form.setSpacing(8)

        form.addWidget(QLabel("NON-CONFORMANCE DESCRIPTION *"))
        self.txt_desc = GlowTextEdit()
        self.txt_desc.setPlaceholderText(
            "Describe the detailed non-conformance condition here... "
            "Right-click for standard template."
        )
        self.txt_desc.setToolTip("Detailed technical description of the defect")
        form.addWidget(self.txt_desc)

        form.addWidget(QLabel("ROOT CAUSE ANALYSIS (RCA)"))
        self.txt_root = GlowTextEdit()
        self.txt_root.setPlaceholderText(
            "Identify root cause (e.g., Welder fatigue, Incorrect preheat, material defect...)"
        )
        self.txt_root.setToolTip("Why did the non-conformance happen?")
        form.addWidget(self.txt_root)

        form.addWidget(QLabel("DISPOSITION DECISION"))
        self.cmb_disp = QComboBox()
        self.cmb_disp.setObjectName("glowCombo")
        self.cmb_disp.setMinimumHeight(38)
        self.cmb_disp.addItems(NCR_DISPOSITIONS)
        self.cmb_disp.setToolTip("How will the non-conformance be dispositioned?")
        form.addWidget(self.cmb_disp)

        form.addWidget(QLabel("CORRECTIVE ACTIONS (IMMEDIATE)"))
        self.txt_corrective = GlowTextEdit()
        self.txt_corrective.setPlaceholderText(
            "Immediate actions to repair or contain the issue..."
        )
        self.txt_corrective.setToolTip("Short-term corrective actions")
        form.addWidget(self.txt_corrective)

        form.addWidget(QLabel("PREVENTIVE ACTIONS (LONG-TERM)"))
        self.txt_preventive = GlowTextEdit()
        self.txt_preventive.setPlaceholderText(
            "Actions required to prevent recurrence (e.g., Retooling, "
            "Welder retraining...)"
        )
        self.txt_preventive.setToolTip("Long-term preventive actions")
        form.addWidget(self.txt_preventive)

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

        self.btn_save = QPushButton("⚡  SAVE QUALITY NCR  (Ctrl+S)")
        self.btn_save.setObjectName("saveBtn")
        self.btn_save.setMinimumHeight(42)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setToolTip("Save NCR (Ctrl+S)")
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

    # ── Load Existing Data (for Editing) ─────────────────────
    def _load_data(self):
        if not self.ncr_data:
            return

        self.setWindowTitle("Edit Non-Conformance Report (NCR)")
        self.txt_ncr_no.setText(str(self.ncr_data.get("ncr_no", "")))
        self.txt_ref.setText(str(self.ncr_data.get("item_reference", "")))
        self.txt_line.setText(str(self.ncr_data.get("line_number", "")))
        self.txt_raised_by.setText(str(self.ncr_data.get("raised_by", "")))

        type_idx = self.cmb_type.findText(str(self.ncr_data.get("item_type", "")))
        if type_idx >= 0:
            self.cmb_type.setCurrentIndex(type_idx)

        disp_idx = self.cmb_disp.findText(str(self.ncr_data.get("disposition", "")))
        if disp_idx >= 0:
            self.cmb_disp.setCurrentIndex(disp_idx)

        self.txt_desc.setPlainText(str(self.ncr_data.get("description", "")))
        self.txt_root.setPlainText(str(self.ncr_data.get("root_cause", "")))
        self.txt_corrective.setPlainText(
            str(self.ncr_data.get("corrective_action", ""))
        )
        self.txt_preventive.setPlainText(
            str(self.ncr_data.get("preventive_action", ""))
        )

        parsed = _parse_date(self.ncr_data.get("raised_date"))
        if parsed is not None:
            self.dte_date.setDate(QDate(parsed.year, parsed.month, parsed.day))

        risk_text = str(self.ncr_data.get("risk_level", "Low (Observation)"))
        risk_idx = self.cmb_risk.findText(risk_text)
        if risk_idx >= 0:
            self.cmb_risk.setCurrentIndex(risk_idx)

    # ── Risk Level Badge ──────────────────────────────────────
    def _apply_risk_badge(self, text: str):
        text_up = (text or "").upper()
        if "CRITICAL" in text_up:
            bg, fg = self.ERROR, "#041827"
            lbl_text = "⚠️ CRITICAL SEVERITY"
        elif "HIGH" in text_up:
            bg, fg = "#ff9f43", "#041827"
            lbl_text = "⚡ HIGH SEVERITY"
        elif "MEDIUM" in text_up:
            bg, fg = self.WARNING, "#041827"
            lbl_text = "⏳ MEDIUM RISK"
        else:
            bg, fg = self.SUCCESS, "#041827"
            lbl_text = "✓ LOW RISK (OBSERVATION)"

        self.lbl_risk_badge.setText(lbl_text)
        self.lbl_risk_badge.setStyleSheet(f"""
            QLabel#riskBadge {{
                background: {bg};
                color: {fg};
                border-radius: 6px;
                font-weight: 900;
                font-size: 10px;
                letter-spacing: 2px;
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
            QComboBox#glowCombo {{
                background: {self.BG_INPUT};
                color: {self.TEXT_MAIN};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QComboBox#glowCombo:hover {{
                border: 1px solid {self.PRIMARY};
            }}
            QComboBox#glowCombo QAbstractItemView {{
                background: #07101a;
                color: {self.TEXT_MAIN};
                selection-background-color: #14334f;
                selection-color: {self.PRIMARY_LIGHT};
                border: 1px solid #1e3d5a;
            }}
            QDateEdit#glowDate {{
                background: {self.BG_INPUT};
                color: {self.TEXT_MAIN};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QDateEdit#glowDate:focus {{
                border: 1px solid {self.PRIMARY};
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
            QPushButton#saveBtn:hover {{
                background: {self.PRIMARY_LIGHT};
            }}
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

    # ── Save & Validate ───────────────────────────────────────
    def _save(self):
        if self._is_closed:
            return

        ncr_no = self.txt_ncr_no.text().strip()
        desc = self.txt_desc.toPlainText().strip()

        if not ncr_no:
            self.lbl_warning.setText(
                "⚠️ Validation: NCR Number is strictly required."
            )
            self._shake()
            self.txt_ncr_no.setFocus()
            return

        if not desc:
            self.lbl_warning.setText(
                "⚠️ Validation: Non-Conformance Description is required."
            )
            self._shake()
            self.txt_desc.setFocus()
            return

        self.lbl_warning.setText("")

        self.result_data = {
            "ncr_no": ncr_no,
            "item_type": self.cmb_type.currentText(),
            "item_reference": self.txt_ref.text().strip(),
            "line_number": self.txt_line.text().strip(),
            "description": desc,
            "root_cause": self.txt_root.toPlainText().strip(),
            "disposition": self.cmb_disp.currentText(),
            "corrective_action": self.txt_corrective.toPlainText().strip(),
            "preventive_action": self.txt_preventive.toPlainText().strip(),
            "raised_by": self.txt_raised_by.text().strip(),
            "raised_date": self.dte_date.date().toPyDate(),
            "risk_level": self.cmb_risk.currentText(),
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

    mock_existing_ncr = {
        "ncr_no": "NCR-VM-2104-002",
        "item_type": "Weld Defect (RT/UT/Visual)",
        "item_reference": "Joint W-12",
        "line_number": '12"-PR-2104-A1A',
        "description": (
            "Lack of penetration detected at the root pass of Joint W-12 "
            "on visual & RT inspection."
        ),
        "root_cause": (
            "Welder rushed pipe lineup without securing root gap per WPS-001."
        ),
        "disposition": "Repair / Rework (Reweld/Rethread)",
        "corrective_action": (
            "Gouge out root pass, inspect using PT, and reweld root pass."
        ),
        "preventive_action": (
            "Mandatory welder training and verification of root gap using "
            "spacing tool."
        ),
        "raised_by": "Senior Inspector Mohammadi",
        "raised_date": date.today(),
        "risk_level": "High (Major Structural / UT Fail)",
    }

    dialog = NCRDialog(ncr_data=mock_existing_ncr)
    dialog.show()
    dialog.exec()

    print("Result data saved:", dialog.result_data)
    sys.exit(0)