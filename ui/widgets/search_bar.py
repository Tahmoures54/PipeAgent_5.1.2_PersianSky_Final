# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Search & Multi-Criteria Filter Bar Widget
═══════════════════════════════════════════════════════════════════════
Version : 5.3.0 (Refactored & Enhanced)
Engine  : PyQt6
Design  : Persian-Sky Professional Theme matching PipeAgent Suite

Features:
  • Real-time Asynchronous Search with Smart Debounce Timer (250ms)
  • Integrated Glow Focus Animation (Cyan ambient light)
  • Dynamic Categorical Filter Selector (Multi-Criteria Scope)
  • One-Click Quick Reset (↺) and Built-in Clear (✕) Action
  • Emits high-level PyQt Signals:
        textChanged, filterChanged, searchSubmitted, searchCleared
  • Global Keyboard Shortcuts: Ctrl+F to focus, Escape to clear
  • Fully encapsulated stylesheet matching master palette constants

Fixed in 5.3.0:
  • Animation lifecycle: no more double-free with DeleteWhenStopped
  • Removed unused imports (QFont, QCursor, QSizePolicy, QApplication)
  • Unified clear() so searchCleared fires exactly once
  • Escape shortcut added
"""
from __future__ import annotations

import logging
from typing import List, Optional

from PyQt6.QtCore import (
    Qt,
    QTimer,
    pyqtSignal,
    QPropertyAnimation,
    QEasingCurve,
)
from PyQt6.QtGui import (
    QColor,
    QKeySequence,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QComboBox,
    QPushButton,
    QLabel,
    QFrame,
    QGraphicsDropShadowEffect,
)

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════
#  MEMORY-SAFE GLOW LINE EDIT (Custom Search Input)
# ═════════════════════════════════════════════════════════════

class _GlowSearchInput(QLineEdit):
    """QLineEdit with focus glow effect and safe animation recycling."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimumHeight(38)
        self.setClearButtonEnabled(True)

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(0)
        self._shadow.setColor(QColor(108, 207, 246, 0))
        self._shadow.setOffset(0, 0)
        self.setGraphicsEffect(self._shadow)

        self._current_anim: Optional[QPropertyAnimation] = None

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._animate_glow(True)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._animate_glow(False)

    def _animate_glow(self, on: bool):
        # Safe stop of any previous animation (avoid double-free)
        if self._current_anim is not None:
            try:
                self._current_anim.stop()
            except RuntimeError:
                # Qt object already deleted (C++ side)
                pass
            self._current_anim = None

        anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        anim.setDuration(180)
        anim.setStartValue(self._shadow.blurRadius())
        anim.setEndValue(14 if on else 0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Parent = self → auto-cleaned when widget destroyed.
        # No manual deleteLater() and no DeleteWhenStopped policy.
        anim.start()
        self._current_anim = anim

        self._shadow.setColor(
            QColor(108, 207, 246, 140 if on else 0)
        )


# ═════════════════════════════════════════════════════════════
#  MAIN REUSABLE SEARCH BAR WIDGET
# ═════════════════════════════════════════════════════════════

class SearchBar(QWidget):
    """
    Ultra-modern, reusable search bar component with category filtering,
    glow focus animation, and debounce timers.
    """

    # Custom PyQt Signals for effortless integration into tabs/dialogs
    textChanged = pyqtSignal(str)              # Debounced search query
    filterChanged = pyqtSignal(str)            # Selected category string
    searchSubmitted = pyqtSignal(str, str)     # (query, category) on Enter/Click
    searchCleared = pyqtSignal()               # When search & filter are reset

    def __init__(
        self,
        placeholder: str = "Search by Tag, ID, Spool, Line, Heat No...",
        filters: Optional[List[str]] = None,
        debounce_ms: int = 250,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._debounce_ms = debounce_ms
        self._last_emitted_text: str = ""  # tracks last debounced value

        self._build_ui(placeholder, filters or [])
        self._setup_signals()
        self._apply_style()

    # ── UI ───────────────────────────────────────────────────

    def _build_ui(self, placeholder: str, filters: List[str]):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.container = QFrame()
        self.container.setObjectName("searchContainer")
        container_layout = QHBoxLayout(self.container)
        container_layout.setContentsMargins(4, 4, 4, 4)
        container_layout.setSpacing(6)

        # Search Icon Accent
        self.icon_label = QLabel("🔍")
        self.icon_label.setObjectName("searchIcon")
        container_layout.addWidget(self.icon_label)

        # Main Glow Search LineEdit
        self.search_input = _GlowSearchInput()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText(placeholder)
        container_layout.addWidget(self.search_input, 3)

        # Category Filter ComboBox
        self.filter_combo = QComboBox()
        self.filter_combo.setObjectName("filterCombo")
        self.filter_combo.setMinimumHeight(38)
        self.filter_combo.setMinimumWidth(160)
        self.filter_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        if filters:
            self.set_filter_items(filters)
        else:
            self.filter_combo.hide()
        container_layout.addWidget(self.filter_combo, 1)

        # Search Action / Submit Button
        self.search_btn = QPushButton("SEARCH")
        self.search_btn.setObjectName("searchActionBtn")
        self.search_btn.setMinimumHeight(38)
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        container_layout.addWidget(self.search_btn)

        # Quick Reset Button (↺)
        self.reset_btn = QPushButton("↺")
        self.reset_btn.setObjectName("searchResetBtn")
        self.reset_btn.setFixedSize(38, 38)
        self.reset_btn.setToolTip("Reset Search and Filters (Esc)")
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        container_layout.addWidget(self.reset_btn)

        main_layout.addWidget(self.container)

        # Debounce Timer for high-performance live search
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(self._debounce_ms)

    def _setup_signals(self):
        # Text editing → debounce
        self.search_input.textChanged.connect(self._on_text_changed)
        self.search_input.returnPressed.connect(self._on_search_clicked)

        # Debounce timeout emits the textChanged signal
        self._debounce_timer.timeout.connect(self._emit_debounced_text)

        # Filter combo selection
        self.filter_combo.currentTextChanged.connect(
            self._on_filter_changed
        )

        # Buttons
        self.search_btn.clicked.connect(self._on_search_clicked)
        self.reset_btn.clicked.connect(self.clear)

        # Ctrl+F → focus input
        self._sc_focus = QShortcut(QKeySequence("Ctrl+F"), self)
        self._sc_focus.activated.connect(self.set_focus)

        # Esc → clear (only when the input has focus)
        self._sc_escape = QShortcut(
            QKeySequence(Qt.Key.Key_Escape), self.search_input
        )
        self._sc_escape.activated.connect(self.clear)

    # ── Internal slots ───────────────────────────────────────

    def _on_text_changed(self, _text: str):
        # Restart debounce timer on every keystroke
        self._debounce_timer.stop()
        self._debounce_timer.start()

    def _emit_debounced_text(self):
        text = self.get_search_text()

        # Avoid re-emitting identical values
        if text == self._last_emitted_text:
            return

        was_empty = not self._last_emitted_text
        self._last_emitted_text = text
        self.textChanged.emit(text)

        # Emit searchCleared only when transitioning from non-empty → empty
        if not text and not was_empty:
            self.searchCleared.emit()

    def _on_filter_changed(self, category: str):
        self.filterChanged.emit(category)
        # Force re-emit even if text hasn't changed
        self._last_emitted_text = None  # type: ignore[assignment]
        self._emit_debounced_text()

    def _on_search_clicked(self):
        self._debounce_timer.stop()
        query = self.get_search_text()
        cat = self.get_selected_filter()
        self.searchSubmitted.emit(query, cat)

    # ── Public API ───────────────────────────────────────────

    def set_placeholder(self, text: str):
        """Update the placeholder text of the search input."""
        self.search_input.setPlaceholderText(text)

    def set_filter_items(
        self, items: List[str], default_index: int = 0
    ):
        """Populate the category filter combobox and display it."""
        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        self.filter_combo.addItems(items)
        if 0 <= default_index < len(items):
            self.filter_combo.setCurrentIndex(default_index)
        self.filter_combo.show()
        self.filter_combo.blockSignals(False)

    def get_search_text(self) -> str:
        """Return the trimmed search input text."""
        return self.search_input.text().strip()

    def get_selected_filter(self) -> str:
        """Return the currently selected filter category string."""
        return (
            self.filter_combo.currentText()
            if self.filter_combo.isVisible() else ""
        )

    def clear(self):
        """Clear search input, reset filter, and emit signals exactly once."""
        had_text = bool(self.search_input.text())

        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)

        if self.filter_combo.count() > 0:
            self.filter_combo.blockSignals(True)
            self.filter_combo.setCurrentIndex(0)
            self.filter_combo.blockSignals(False)

        # Reset debounce state
        self._debounce_timer.stop()
        self._last_emitted_text = ""

        if had_text:
            self.textChanged.emit("")
        self.searchCleared.emit()

    def set_focus(self):
        """Focus and select all text in the search input."""
        self.search_input.setFocus()
        self.search_input.selectAll()

    # ── Styling ──────────────────────────────────────────────

    def _apply_style(self):
        self.setStyleSheet("""
            QFrame#searchContainer {
                background: #091726;
                border: 1px solid #142e47;
                border-radius: 10px;
            }
            QLabel#searchIcon {
                font-size: 14px;
                padding-left: 6px;
                background: transparent;
            }
            QLineEdit#searchInput {
                background: #07101a;
                color: #eef6ff;
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QLineEdit#searchInput:focus {
                border: 1px solid #6ccff6;
                background: #0d2133;
            }
            QComboBox#filterCombo {
                background: #07101a;
                color: #eef6ff;
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QComboBox#filterCombo:hover {
                border: 1px solid #6ccff6;
            }
            QComboBox#filterCombo QAbstractItemView {
                background: #07101a;
                color: #eef6ff;
                selection-background-color: #14334f;
                selection-color: #9fe7ff;
                border: 1px solid #1e3d5a;
                padding: 4px;
            }
            QPushButton#searchActionBtn {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2196d4, stop:0.5 #68d7ff, stop:1 #2196d4
                );
                color: #041827;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            QPushButton#searchActionBtn:hover {
                background: #9fe7ff;
            }
            QPushButton#searchActionBtn:pressed {
                background: #2196d4;
            }
            QPushButton#searchResetBtn {
                background: #0f1c2e;
                color: #9fe7ff;
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton#searchResetBtn:hover {
                background: #142a40;
                border: 1px solid #6ccff6;
                color: #68d7ff;
            }
            QPushButton#searchResetBtn:pressed {
                background: #07101a;
            }
        """)


# ═════════════════════════════════════════════════════════════
#  STANDALONE PREVIEW RUNNER
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication, QVBoxLayout

    app = QApplication(sys.argv)

    window = QWidget()
    window.setWindowTitle("PipeAgent — SearchBar Demo")
    window.resize(900, 150)
    window.setStyleSheet("background-color: #060e18;")

    layout = QVBoxLayout(window)
    layout.setContentsMargins(20, 20, 20, 20)

    search_bar = SearchBar(
        placeholder="🔍 Search lines, spools, joints, welds, materials...",
        filters=[
            "All Categories", "Isometric (ISO)", "Spools",
            "Weld Joints", "P&ID",
        ],
    )
    layout.addWidget(search_bar)

    output_lbl = QLabel(
        "Type in the search bar above to test live debounced signals..."
    )
    output_lbl.setStyleSheet(
        "color: #5cffaa; font-size: 12px; font-weight: bold; "
        "margin-top: 10px;"
    )
    layout.addWidget(output_lbl)

    search_bar.textChanged.connect(
        lambda text: output_lbl.setText(
            f"✓ Debounced Query: '{text}'  |  "
            f"Category: '{search_bar.get_selected_filter()}'"
        )
    )
    search_bar.searchSubmitted.connect(
        lambda q, cat: output_lbl.setText(
            f"⚡ Search Submitted: Query='{q}', Category='{cat}'"
        )
    )
    search_bar.searchCleared.connect(
        lambda: output_lbl.setText("↺ Search cleared and reset.")
    )

    window.show()
    sys.exit(app.exec())