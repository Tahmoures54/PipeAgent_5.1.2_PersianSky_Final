# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Reusable KPI StatCard Widget
═══════════════════════════════════════════════════════════════════════
Version : 5.3.0 (Production Master Component)
Engine  : PyQt6
Design  : Persian-Sky Professional Theme matching PipeAgent Suite

Features:
  • High-Contrast Dark-Glass Panel with Left Glow Accent Border
  • Multi-Element Structure:
        Icon Container · Bold Value · Metric Title · Trend Badge
  • Interactive Click Support (emits `clicked` signal for drill-down)
  • Responsive Hover Transitions with cursor feedback
  • Backward-compatible API (legacy `set_value` and `color` arguments)
  • Built-in Palette Presets (Cyan, Green, Amber, Red, Purple)
  • Clean encapsulated stylesheet without global namespace leakage

Fixed in 5.3.0:
  • Removed unused imports (QPropertyAnimation, QEasingCurve, QCursor)
  • Added WA_Hover attribute for reliable :hover QSS behaviour
  • Correct `QMouseEvent` import path preserved
  • Icon label reference stored as Optional (safe removal handling)
"""
from __future__ import annotations

import logging
from typing import Optional, Union

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QMouseEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QWidget,
)

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════
#  THEME COLOR PRESETS
# ═════════════════════════════════════════════════════════════

THEME_CYAN   = "#6ccff6"  # Primary highlight & default
THEME_LIGHT  = "#9fe7ff"  # Radiant light cyan
THEME_GREEN  = "#5cffaa"  # Success / Passed / Cleared
THEME_AMBER  = "#ffd966"  # Warning / Under Review / Pending
THEME_RED    = "#ff6b6b"  # Error / Rejected / Category A
THEME_PURPLE = "#c084fc"  # Analytics / AI / Special KPI


# ═════════════════════════════════════════════════════════════
#  REUSABLE STAT CARD WIDGET
# ═════════════════════════════════════════════════════════════

class StatCard(QFrame):
    """
    Ultra-modern, reusable KPI Stat Card for dashboards, inspection
    towers, and workflow registers.
    """

    # Signal emitted on click; passes the title/ID of the card
    clicked = pyqtSignal(str)

    def __init__(
        self,
        title: str,
        value: Union[str, int, float] = "0",
        icon: str = "📊",
        accent_color: str = THEME_CYAN,
        subtitle: Optional[str] = None,
        is_clickable: bool = False,
        parent: Optional[QWidget] = None,
        # Backward compatibility alias:
        color: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setMinimumHeight(68)
        self.setMinimumWidth(160)

        # Enable :hover pseudo-state to trigger reliably
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        self._accent_color = color if color else accent_color
        self._title = title
        self._value = str(value)
        self._icon_str = icon
        self._subtitle = subtitle
        self._is_clickable = is_clickable

        self._icon_lbl: Optional[QLabel] = None

        self._build_ui()
        self._apply_style()

    # ── UI ───────────────────────────────────────────────────

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        # Left Icon Container
        if self._icon_str:
            self._icon_lbl = QLabel(self._icon_str)
            self._icon_lbl.setObjectName("statIcon")
            self._icon_lbl.setFont(QFont("Segoe UI", 18))
            self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._icon_lbl.setStyleSheet(
                f"color: {self._accent_color}; background: transparent;"
            )
            layout.addWidget(self._icon_lbl)

        # Text Column (Value, Title, Subtitle/Trend)
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        # Value
        self.val_lbl = QLabel(self._value)
        self.val_lbl.setObjectName("statValue")
        self.val_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.val_lbl.setStyleSheet(
            f"color: {self._accent_color}; background: transparent;"
        )
        text_col.addWidget(self.val_lbl)

        # Title
        self.title_lbl = QLabel(self._title.upper())
        self.title_lbl.setObjectName("statTitle")
        self.title_lbl.setFont(
            QFont("Segoe UI", 8, QFont.Weight.DemiBold)
        )
        self.title_lbl.setStyleSheet(
            "color: #7a9ab3; letter-spacing: 1px; "
            "background: transparent;"
        )
        text_col.addWidget(self.title_lbl)

        # Subtitle / Trend Badge
        self.sub_lbl = QLabel(self._subtitle or "")
        self.sub_lbl.setObjectName("statSubtitle")
        self.sub_lbl.setFont(QFont("Segoe UI", 8))
        self.sub_lbl.setStyleSheet(
            "color: #5a7a8f; background: transparent;"
        )
        if not self._subtitle:
            self.sub_lbl.hide()
        text_col.addWidget(self.sub_lbl)

        layout.addLayout(text_col, 1)

        if self._is_clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip(
                f"Click to filter workspace by {self._title}"
            )

    def _apply_style(self):
        hover_style = ""
        if self._is_clickable:
            hover_style = f"""
                QFrame#statCard:hover {{
                    background: #10263c;
                    border: 1px solid {self._accent_color};
                    border-left: 3px solid {self._accent_color};
                }}
            """

        self.setStyleSheet(f"""
            QFrame#statCard {{
                background: #091726;
                border: 1px solid #142e47;
                border-left: 3px solid {self._accent_color};
                border-radius: 8px;
            }}
            {hover_style}
        """)

    # ── Public API ───────────────────────────────────────────

    def set_value(self, new_value: Union[str, int, float]) -> None:
        """Legacy alias for `update_value`."""
        self.update_value(new_value)

    def update_value(self, new_value: Union[str, int, float]) -> None:
        """Update the metric value displayed on the card."""
        self._value = str(new_value)
        self.val_lbl.setText(self._value)

    def set_title(self, new_title: str) -> None:
        """Update the title text of the card."""
        self._title = new_title
        self.title_lbl.setText(new_title.upper())

    def set_icon(self, icon_str: str) -> None:
        """Update the icon glyph of the card."""
        self._icon_str = icon_str
        if self._icon_lbl is not None:
            self._icon_lbl.setText(icon_str)

    def set_subtitle(self, text: str,
                     color: Optional[str] = None) -> None:
        """Set or update the subtitle / trend badge text."""
        self._subtitle = text
        self.sub_lbl.setText(text)
        if color:
            self.sub_lbl.setStyleSheet(
                f"color: {color}; font-weight: bold; "
                "background: transparent;"
            )
        self.sub_lbl.show()

    def set_trend(self, percentage_text: str,
                  is_positive: bool = True) -> None:
        """Set a pre-formatted trend badge (e.g. '+12% vs last week')."""
        arrow = "▲" if is_positive else "▼"
        color = THEME_GREEN if is_positive else THEME_RED
        self.set_subtitle(f"{arrow} {percentage_text}", color=color)

    def set_accent_color(self, hex_color: str) -> None:
        """Dynamically update the accent color and refresh the style."""
        self._accent_color = hex_color
        self.val_lbl.setStyleSheet(
            f"color: {hex_color}; background: transparent;"
        )
        if self._icon_lbl is not None:
            self._icon_lbl.setStyleSheet(
                f"color: {hex_color}; background: transparent;"
            )
        self._apply_style()

    def set_clickable(self, clickable: bool = True) -> None:
        """Enable or disable card click events and hand cursor."""
        self._is_clickable = clickable
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if clickable
            else Qt.CursorShape.ArrowCursor
        )
        self._apply_style()

    # ── Mouse Events ─────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if (event.button() == Qt.MouseButton.LeftButton
                and self._is_clickable):
            self.clicked.emit(self._title)
            event.accept()
        else:
            super().mousePressEvent(event)


# ═════════════════════════════════════════════════════════════
#  STANDALONE TEST / PREVIEW RUNNER
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication, QVBoxLayout

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    preview_window = QWidget()
    preview_window.setWindowTitle(
        "PipeAgent — StatCard v5.3 Master Showcase"
    )
    preview_window.resize(900, 260)
    preview_window.setStyleSheet("background-color: #060e18;")

    main_layout = QVBoxLayout(preview_window)
    main_layout.setContentsMargins(20, 20, 20, 20)
    main_layout.setSpacing(14)

    ribbon = QHBoxLayout()
    ribbon.setSpacing(12)

    card_total = StatCard(
        title="Total Registered",
        value="1,248",
        icon="📚",
        accent_color=THEME_LIGHT,
        subtitle="Across all units",
    )

    card_ifc = StatCard(
        title="IFC Ready (Site)",
        value="842",
        icon="✅",
        accent_color=THEME_GREEN,
        is_clickable=True,
    )
    card_ifc.set_trend("+8.4% this week", is_positive=True)

    card_review = StatCard(
        title="Under Review",
        value="284",
        icon="⏳",
        accent_color=THEME_AMBER,
        subtitle="QA/QC Pending",
        is_clickable=True,
    )

    card_void = StatCard(
        title="Superseded / Void",
        value="122",
        icon="🚫",
        accent_color=THEME_RED,
        is_clickable=True,
    )
    card_void.set_trend("-3.1% resolved", is_positive=False)

    ribbon.addWidget(card_total)
    ribbon.addWidget(card_ifc)
    ribbon.addWidget(card_review)
    ribbon.addWidget(card_void)
    main_layout.addLayout(ribbon)

    feedback_lbl = QLabel(
        "Click on any interactive KPI card above to test "
        "drill-down signals..."
    )
    feedback_lbl.setStyleSheet(
        "color: #6ccff6; font-size: 11px; font-weight: bold; "
        "margin-top: 10px;"
    )
    feedback_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    main_layout.addWidget(feedback_lbl)

    card_ifc.clicked.connect(
        lambda t: feedback_lbl.setText(
            f"⚡ KPI Card Clicked: Filtered workspace by '{t}'"
        )
    )
    card_review.clicked.connect(
        lambda t: feedback_lbl.setText(
            f"⚡ KPI Card Clicked: Filtered workspace by '{t}'"
        )
    )
    card_void.clicked.connect(
        lambda t: feedback_lbl.setText(
            f"⚡ KPI Card Clicked: Filtered workspace by '{t}'"
        )
    )

    preview_window.show()
    sys.exit(app.exec())