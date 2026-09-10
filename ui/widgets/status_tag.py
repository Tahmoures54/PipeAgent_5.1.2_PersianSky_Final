# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Reusable Status Tag & Badge Widget
═══════════════════════════════════════════════════════════════════════
Version : 5.3.0 (Production Master Component)
Engine  : PyQt6
Design  : Persian-Sky Professional Theme matching PipeAgent Suite

Features:
  • Smart Keyword Auto-Detection (IFC, Accepted, Rejected, Cat A/B, etc.)
  • Translucent Dark-Glass Capsule / Pill Badge Design
  • Dynamic Leading Status Dot Indicator (●)
  • Four Visual Archetypes: PILL (default), OUTLINE, SOLID, MINIMAL
  • Backward-compatible API (legacy `text` and `color` parameters)
  • High-Contrast Segoe UI Typography with custom letter-spacing
  • Fully encapsulated QSS generator with custom alpha-channel blending

Fixed in 5.3.0:
  • Removed unused imports (QColor, QFrame, QHBoxLayout, QVBoxLayout,
    QApplication)
  • Preserves explicitly-set `status_type` across `set_style_mode()`
  • Cleaner detection engine with clearer keyword groups
  • Added `reset_to_auto()` helper
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QWidget

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════
#  SEMANTIC COLOR MATRIX
# ═════════════════════════════════════════════════════════════

SEMANTIC_STYLES: Dict[str, Dict[str, str]] = {
    "success": {
        "fg": "#5cffaa",
        "bg": "rgba(92, 255, 170, 0.12)",
        "border": "rgba(92, 255, 170, 0.35)",
    },
    "warning": {
        "fg": "#ffd966",
        "bg": "rgba(255, 217, 102, 0.12)",
        "border": "rgba(255, 217, 102, 0.35)",
    },
    "error": {
        "fg": "#ff6b6b",
        "bg": "rgba(255, 107, 107, 0.14)",
        "border": "rgba(255, 107, 107, 0.40)",
    },
    "info": {
        "fg": "#68d7ff",
        "bg": "rgba(104, 215, 255, 0.12)",
        "border": "rgba(104, 215, 255, 0.35)",
    },
    "neutral": {
        "fg": "#8faec5",
        "bg": "rgba(143, 174, 197, 0.10)",
        "border": "rgba(143, 174, 197, 0.25)",
    },
}


# ═════════════════════════════════════════════════════════════
#  KEYWORD DETECTION TABLES
# ═════════════════════════════════════════════════════════════

_SUCCESS_KEYWORDS = (
    "ACCEPTED", "PASSED", "CLEARED", "ACTIVE", "IFC",
    "APPROVED", "COMPLETED", "OK", "RELEASED", "100%",
    "SUCCESS", "INSTALLED", "TESTED",
)

_WARNING_KEYWORDS = (
    "PENDING", "REVIEW", "IFA", "HOLD", "QUARANTINE",
    "CAT B", "IN PROGRESS", "RE-EXAM", "WARNING",
    "WAITING", "BLOCKED", "ON HOLD",
)

_ERROR_KEYWORDS = (
    "REJECT", "REPAIR", "VOID", "EXPIRED", "CAT A",
    "FAIL", "SUSPEND", "DAMAGED", "ERROR", "BLOCK",
    "CRITICAL",
)

_INFO_KEYWORDS = (
    "AS-BUILT", "INFO", "VT", "HT", "PMI", "TEST",
    "STAGE", "INSPECTED", "DRAFT", "SUBMITTED",
)


# ═════════════════════════════════════════════════════════════
#  REUSABLE STATUS TAG BADGE WIDGET
# ═════════════════════════════════════════════════════════════

class StatusTag(QLabel):
    """
    Ultra-modern, reusable status tag / badge component for data tables,
    cards, inspection panels, and dialogs.
    """

    # Visual archetypes
    STYLE_PILL    = "pill"     # Glowing translucent + subtle border
    STYLE_OUTLINE = "outline"  # Transparent bg + bright border
    STYLE_SOLID   = "solid"    # High-contrast solid fill
    STYLE_MINIMAL = "minimal"  # Text & dot only (no border/background)

    def __init__(
        self,
        text: str = "",
        status_type: Optional[str] = None,
        show_dot: bool = True,
        style_mode: str = STYLE_PILL,
        parent: Optional[QWidget] = None,
        # Backward compatibility:
        color: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setObjectName("statusTag")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(24)

        self._show_dot = show_dot
        self._style_mode = style_mode
        self._custom_color: Optional[str] = color
        self._raw_text = text
        self._status_type: Optional[str] = status_type  # explicit override

        self.set_status(
            text, status_type=status_type, color=color
        )

    # ── Detection engine ─────────────────────────────────────

    def _detect_status_type(self, text: str) -> str:
        """Map status text into a semantic bucket."""
        t = text.strip().upper()

        if any(k in t for k in _SUCCESS_KEYWORDS):
            return "success"
        if any(k in t for k in _ERROR_KEYWORDS):
            return "error"
        if any(k in t for k in _WARNING_KEYWORDS):
            return "warning"
        if any(k in t for k in _INFO_KEYWORDS):
            return "info"
        return "neutral"

    # ── Public API ───────────────────────────────────────────

    def set_status(
        self,
        text: str,
        status_type: Optional[str] = None,
        color: Optional[str] = None,
    ) -> None:
        """Update badge text and reapply the semantic or custom style."""
        self._raw_text = text.strip()
        self._status_type = status_type  # remember explicit override
        self._custom_color = color

        formatted = (
            f"● {self._raw_text}"
            if self._show_dot and self._raw_text
            else self._raw_text
        )
        self.setText(formatted)

        if color:
            self._apply_custom_color_style(color)
        else:
            resolved = (
                status_type
                or self._detect_status_type(self._raw_text)
            )
            self._apply_semantic_style(resolved)

    def set_custom_color(self, hex_color: str) -> None:
        """Explicitly set a custom hex color for text and border."""
        self._custom_color = hex_color
        self._apply_custom_color_style(hex_color)

    def set_style_mode(self, style_mode: str) -> None:
        """Switch badge appearance mode while preserving semantic type."""
        self._style_mode = style_mode
        # Re-apply current state without losing explicit status_type
        self.set_status(
            self._raw_text,
            status_type=self._status_type,
            color=self._custom_color,
        )

    def reset_to_auto(self) -> None:
        """Forget explicit status_type / color and re-detect from text."""
        self._status_type = None
        self._custom_color = None
        self.set_status(self._raw_text)

    def set_dot_visible(self, visible: bool) -> None:
        """Toggle the leading status dot indicator."""
        self._show_dot = visible
        formatted = (
            f"● {self._raw_text}"
            if visible and self._raw_text
            else self._raw_text
        )
        self.setText(formatted)

    # ── Styling ──────────────────────────────────────────────

    def _apply_semantic_style(self, status_type: str) -> None:
        palette = SEMANTIC_STYLES.get(
            status_type, SEMANTIC_STYLES["neutral"]
        )
        fg = palette["fg"]
        bg = palette["bg"]
        border = palette["border"]

        if self._style_mode == self.STYLE_OUTLINE:
            bg = "transparent"
            border = fg
        elif self._style_mode == self.STYLE_SOLID:
            bg = fg
            fg = "#041827"
            border = "transparent"
        elif self._style_mode == self.STYLE_MINIMAL:
            bg = "transparent"
            border = "transparent"

        self.setStyleSheet(f"""
            QLabel#statusTag {{
                color: {fg};
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 12px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }}
        """)

    def _apply_custom_color_style(self, hex_color: str) -> None:
        """Legacy hex-color override."""
        # Respect the current style mode where possible
        if self._style_mode == self.STYLE_SOLID:
            fg = "#041827"
            bg = hex_color
            border = "transparent"
        elif self._style_mode == self.STYLE_OUTLINE:
            fg = hex_color
            bg = "transparent"
            border = hex_color
        elif self._style_mode == self.STYLE_MINIMAL:
            fg = hex_color
            bg = "transparent"
            border = "transparent"
        else:  # PILL
            fg = hex_color
            bg = "rgba(255, 255, 255, 0.05)"
            border = hex_color

        self.setStyleSheet(f"""
            QLabel#statusTag {{
                color: {fg};
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 12px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }}
        """)


# ═════════════════════════════════════════════════════════════
#  STANDALONE SHOWCASE RUNNER
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import (
        QApplication, QVBoxLayout, QHBoxLayout
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    demo_window = QWidget()
    demo_window.setWindowTitle(
        "PipeAgent — StatusTag v5.3 Master Showcase"
    )
    demo_window.resize(750, 400)
    demo_window.setStyleSheet("background-color: #060e18;")

    main_layout = QVBoxLayout(demo_window)
    main_layout.setContentsMargins(24, 24, 24, 24)
    main_layout.setSpacing(16)

    # ── Section 1: Auto-detection ────────────────────────────
    sec1_title = QLabel(
        "1. AUTO-DETECTION BY STATUS KEYWORDS:"
    )
    sec1_title.setStyleSheet(
        "color: #6ccff6; font-weight: 900; font-size: 11px; "
        "letter-spacing: 1px;"
    )
    main_layout.addWidget(sec1_title)

    row1 = QHBoxLayout()
    row1.setSpacing(10)
    for txt in [
        "IFC (Ready for Site)",
        "QC Accepted",
        "Under Review",
        "Quarantined",
        "RT Repair Required",
        "Void / Superseded",
    ]:
        row1.addWidget(StatusTag(txt))
    row1.addStretch()
    main_layout.addLayout(row1)

    # ── Section 2: Explicit semantic types ───────────────────
    sec2_title = QLabel(
        "2. PUNCH LIST & TEST PACKAGE GATES:"
    )
    sec2_title.setStyleSheet(
        "color: #6ccff6; font-weight: 900; font-size: 11px; "
        "letter-spacing: 1px;"
    )
    main_layout.addWidget(sec2_title)

    row2 = QHBoxLayout()
    row2.setSpacing(10)
    row2.addWidget(StatusTag("Cat A Blocker", status_type="error"))
    row2.addWidget(StatusTag("Cat B Post-Hydro", status_type="warning"))
    row2.addWidget(StatusTag("100% NDT Cleared", status_type="success"))
    row2.addWidget(StatusTag("As-Built Registered", status_type="info"))
    row2.addWidget(StatusTag("Draft Passport", status_type="neutral"))
    row2.addStretch()
    main_layout.addLayout(row2)

    # ── Section 3: Style archetypes ──────────────────────────
    sec3_title = QLabel(
        "3. BADGE STYLE ARCHETYPES "
        "(PILL, OUTLINE, SOLID, MINIMAL):"
    )
    sec3_title.setStyleSheet(
        "color: #6ccff6; font-weight: 900; font-size: 11px; "
        "letter-spacing: 1px;"
    )
    main_layout.addWidget(sec3_title)

    row3 = QHBoxLayout()
    row3.setSpacing(10)
    row3.addWidget(StatusTag(
        "PILL (Standard)",
        style_mode=StatusTag.STYLE_PILL,
        status_type="success",
    ))
    row3.addWidget(StatusTag(
        "OUTLINE",
        style_mode=StatusTag.STYLE_OUTLINE,
        status_type="warning",
    ))
    row3.addWidget(StatusTag(
        "SOLID BADGE",
        style_mode=StatusTag.STYLE_SOLID,
        status_type="error",
    ))
    row3.addWidget(StatusTag(
        "MINIMAL DOT",
        style_mode=StatusTag.STYLE_MINIMAL,
        status_type="info",
    ))
    row3.addStretch()
    main_layout.addLayout(row3)

    main_layout.addStretch()
    demo_window.show()
    sys.exit(app.exec())