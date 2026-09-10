# -*- coding: utf-8 -*-
"""
PipeAgent — Shared theme, widgets and utilities for all Tab modules.
Version : 5.3.0
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional, Dict

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor, QBrush
from PyQt6.QtWidgets import (
    QFrame, QLabel, QHBoxLayout, QVBoxLayout, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QWidget,
)

logger = logging.getLogger(__name__)

# ═════════════════════════════════════════════════════════════
#  THEME PALETTE — Persian-Sky Professional
# ═════════════════════════════════════════════════════════════
BG_DEEP        = "#060e18"
BG_APP         = "#0b1624"
BG_PANEL       = "#0f1c2e"
BG_INPUT       = "#07101a"
BORDER_SUBTLE  = "#142e47"
BORDER_ACCENT  = "#1e3d5a"
PRIMARY        = "#6ccff6"
PRIMARY_LIGHT  = "#9fe7ff"
ACCENT         = "#68d7ff"
TEXT_MAIN      = "#eef6ff"
TEXT_MUTED     = "#7a9ab3"
SUCCESS        = "#5cffaa"
WARNING        = "#ffd966"
ERROR          = "#ff6b6b"
PURPLE         = "#c084fc"
INFO           = "#68d7ff"

# Light palette (reports / documents tabs)
LIGHT_HEADER_1 = "#1e3c72"
LIGHT_HEADER_2 = "#2a5298"
LIGHT_ACCENT   = "#3b82f6"
LIGHT_ACCENT_2 = "#2563eb"
LIGHT_SUCCESS  = "#10b981"
LIGHT_DANGER   = "#ef4444"
LIGHT_WARNING  = "#f59e0b"


# ═════════════════════════════════════════════════════════════
#  UNIVERSAL STAT CARD
# ═════════════════════════════════════════════════════════════
class StatCard(QFrame):
    """Universal KPI tile with left glow accent border."""

    def __init__(
        self,
        title: str,
        value: str = "0",
        icon: str = "▣",
        accent_color: str = PRIMARY,
        parent: Optional[QWidget] = None,
        *,
        light: bool = False,
        fixed_height: int = 68,
        min_width: int = 150,
    ):
        super().__init__(parent)
        self.setObjectName("universalStatCard")
        self.setFixedHeight(fixed_height)
        self.setMinimumWidth(min_width)

        bg          = "#ffffff" if light else "#091726"
        border      = "#e2e8f0" if light else BORDER_SUBTLE
        title_color = "#64748b" if light else TEXT_MUTED

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI", 18))
        icon_lbl.setStyleSheet(f"color: {accent_color}; background: transparent;")
        layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        self.val_lbl = QLabel(value)
        self.val_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self.val_lbl.setStyleSheet(f"color: {accent_color}; background: transparent;")
        text_col.addWidget(self.val_lbl)

        self.title_lbl = QLabel(title.upper())
        self.title_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        self.title_lbl.setStyleSheet(
            f"color: {title_color}; letter-spacing: 1px; background: transparent;"
        )
        text_col.addWidget(self.title_lbl)

        layout.addLayout(text_col, 1)

        self.setStyleSheet(f"""
            QFrame#universalStatCard {{
                background: {bg};
                border: 1px solid {border};
                border-left: 3px solid {accent_color};
                border-radius: 8px;
            }}
        """)

    def update_value(self, val: str) -> None:
        self.val_lbl.setText(str(val))

    # Backwards-compat alias
    set_value = update_value


# ═════════════════════════════════════════════════════════════
#  TABLE CONFIGURATION HELPERS
# ═════════════════════════════════════════════════════════════
def style_table(
    table: QTableWidget,
    *,
    stretch_last: bool = True,
    stretch_column: Optional[int] = None,
    word_wrap: bool = False,
    alternating: bool = True,
    pixel_scroll: bool = True,
    single_selection: bool = False,
) -> None:
    """Apply consistent, correct table configuration across all tabs.

    IMPORTANT: uses QAbstractItemView (NOT QTableWidget) for enum access.
    """
    table.setAlternatingRowColors(alternating)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(
        QAbstractItemView.SelectionMode.SingleSelection
        if single_selection
        else QAbstractItemView.SelectionMode.ExtendedSelection
    )
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.setShowGrid(False)
    table.setWordWrap(word_wrap)
    table.setSortingEnabled(True)

    if pixel_scroll:
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    header = table.horizontalHeader()
    header.setSectionsMovable(True)
    header.setSectionsClickable(True)
    header.setStretchLastSection(stretch_last)

    for col in range(table.columnCount()):
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

    if stretch_column is not None and 0 <= stretch_column < table.columnCount():
        header.setSectionResizeMode(stretch_column, QHeaderView.ResizeMode.Stretch)


def apply_badge(
    item: QTableWidgetItem,
    text: str,
    badge: Dict[str, str],
    *,
    with_icon: bool = True,
) -> None:
    """Apply colored badge style to a table cell."""
    display = f"{badge.get('icon', '')} {text}".strip() if with_icon else text
    item.setText(display)
    item.setBackground(QBrush(QColor(badge.get("bg", "#f1f5f9"))))
    item.setForeground(QBrush(QColor(badge.get("fg", "#475569"))))
    f = item.font(); f.setBold(True); item.setFont(f)


def make_item(
    text: Any,
    *,
    mono: bool = False,
    color: Optional[str] = None,
    bold: bool = False,
    align: Optional[Qt.AlignmentFlag] = None,
    tooltip: Optional[str] = None,
    user_data: Any = None,
) -> QTableWidgetItem:
    """Factory to reduce boilerplate when building QTableWidgetItem rows."""
    item = QTableWidgetItem("" if text is None else str(text))
    if mono:
        f = item.font(); f.setFamily("Consolas"); f.setBold(bold); item.setFont(f)
    elif bold:
        f = item.font(); f.setBold(True); item.setFont(f)
    if color:
        item.setForeground(QBrush(QColor(color)))
    if align is not None:
        item.setTextAlignment(align)
    if tooltip:
        item.setToolTip(tooltip)
    if user_data is not None:
        item.setData(Qt.ItemDataRole.UserRole, user_data)
    return item


# ═════════════════════════════════════════════════════════════
#  SAFE SESSION WRAPPER
# ═════════════════════════════════════════════════════════════
class _MockQuery:
    def filter(self, *_a, **_k): return self
    def filter_by(self, *_a, **_k): return self
    def order_by(self, *_a, **_k): return self
    def limit(self, *_a, **_k): return self
    def all(self): return []
    def first(self): return None
    def count(self): return 0
    def get(self, *_a, **_k): return None


class _MockSession:
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass
    def flush(self): pass
    def add(self, *_a, **_k): pass
    def delete(self, *_a, **_k): pass
    def get(self, *_a, **_k): return None
    def query(self, *_a, **_k): return _MockQuery()


def get_session(db: Any):
    """Return a context manager yielding a working session, or a no-op mock.

    Usage:
        with get_session(self.db) as s:
            rows = s.query(Project).all()
    """
    if db is None:
        return _SessionCtx(_MockSession(), real=False)

    if hasattr(db, "session_scope"):
        return _SessionCtx(db.session_scope, real=True, is_scope=True)

    if hasattr(db, "get_session"):
        return _SessionCtx(db.get_session(), real=True, is_scope=False)

    return _SessionCtx(_MockSession(), real=False)


class _SessionCtx:
    def __init__(self, source, *, real: bool, is_scope: bool = False):
        self._source = source
        self._real = real
        self._is_scope = is_scope
        self._ctx = None
        self._session = None

    def __enter__(self):
        if not self._real:
            self._session = self._source
            return self._session
        if self._is_scope:
            self._ctx = self._source()
            self._session = self._ctx.__enter__()
        else:
            self._session = self._source
        return self._session

    def __exit__(self, exc_type, exc, tb):
        if not self._real:
            return False
        try:
            if self._is_scope and self._ctx is not None:
                return self._ctx.__exit__(exc_type, exc, tb)
            if exc_type is not None:
                self._session.rollback()
            else:
                self._session.commit()
            self._session.close()
        except Exception as e:
            logger.warning("Session cleanup failed: %s", e)
        return False


# ═════════════════════════════════════════════════════════════
#  DATETIME HELPERS
# ═════════════════════════════════════════════════════════════
def utc_now_naive() -> datetime:
    """Naive UTC timestamp — replacement for deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today() -> date:
    return date.today()


def fmt_date(value: Any, default: str = "—") -> str:
    """Format a date or datetime safely to YYYY-MM-DD."""
    if value is None or value == "":
        return default
    try:
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")
        if isinstance(value, date):
            return value.strftime("%Y-%m-%d")
        return str(value)[:10]
    except Exception:
        return default


# ═════════════════════════════════════════════════════════════
#  DARK STYLESHEET BUILDER
# ═════════════════════════════════════════════════════════════
def build_dark_stylesheet(*, with_tabs: bool = False, with_inputs: bool = True) -> str:
    base = f"""
        QWidget {{
            background-color: {BG_APP};
            color: {TEXT_MAIN};
            font-family: 'Segoe UI', sans-serif;
        }}
        QLabel#mainTitle {{
            color: {PRIMARY_LIGHT}; font-size: 18px; font-weight: 900;
            letter-spacing: 2px; background: transparent;
        }}
        QLabel#subTitle {{
            color: {PRIMARY}; font-size: 9px; font-weight: 700;
            letter-spacing: 1.2px; background: transparent;
        }}
        QLabel#sectionTitle {{
            color: {PRIMARY_LIGHT}; font-size: 11px; font-weight: 800;
            letter-spacing: 1px; background: transparent;
        }}
        QLabel#footerLabel {{
            color: {TEXT_MUTED}; font-size: 11px; background: transparent;
        }}
        QFrame#panelCard {{
            background: {BG_PANEL};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 10px;
        }}
        QPushButton#actionBtn {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #2196d4, stop:0.5 {ACCENT}, stop:1 #2196d4);
            color: #041827; border: none; border-radius: 8px;
            padding: 0 16px; font-size: 11px; font-weight: 800;
            letter-spacing: 1px;
        }}
        QPushButton#actionBtn:hover {{ background: {PRIMARY_LIGHT}; }}
        QPushButton#actionBtn:disabled {{ background: #334155; color: #94a3b8; }}
        QPushButton#secondaryBtn {{
            background: {BG_PANEL}; color: {PRIMARY_LIGHT};
            border: 1px solid {BORDER_ACCENT};
            border-radius: 8px; padding: 0 14px;
            font-size: 11px; font-weight: 700; letter-spacing: 1px;
        }}
        QPushButton#secondaryBtn:hover {{
            background: #142a40; border-color: {PRIMARY};
        }}
        QTableWidget#towerTable, QTableWidget#aiTable, QTableWidget#asbuiltTable {{
            background: #07111c; alternate-background-color: #091520;
            color: {TEXT_MAIN}; border: 1px solid {BORDER_SUBTLE};
            border-radius: 8px; gridline-color: transparent;
            selection-background-color: #12334f;
            selection-color: {PRIMARY_LIGHT}; font-size: 12px;
        }}
        QTableWidget#towerTable::item:selected,
        QTableWidget#aiTable::item:selected,
        QTableWidget#asbuiltTable::item:selected {{
            background: #133959; border-left: 2px solid {PRIMARY};
        }}
        QHeaderView::section {{
            background: #0c1c2e; color: {PRIMARY_LIGHT};
            font-weight: 800; font-size: 10px; letter-spacing: 1px;
            border: none; border-bottom: 2px solid #1c4466;
            border-right: 1px solid {BORDER_SUBTLE}; padding: 8px 9px;
        }}
        QScrollBar:vertical {{ background: #07101a; width: 8px; border-radius: 4px; }}
        QScrollBar::handle:vertical {{ background: #1e3d5a; border-radius: 4px; min-height: 25px; }}
        QScrollBar::handle:vertical:hover {{ background: {PRIMARY}; }}
        QSplitter::handle {{ background: #102538; border-radius: 1px; }}
    """

    if with_inputs:
        base += f"""
        QComboBox, QLineEdit {{
            background: {BG_INPUT}; color: {TEXT_MAIN};
            border: 1px solid {BORDER_ACCENT};
            border-radius: 8px; padding: 6px 12px;
            font-size: 12px; font-weight: bold;
        }}
        QComboBox:hover, QLineEdit:hover {{ border-color: {PRIMARY}; }}
        QComboBox QAbstractItemView {{
            background: {BG_INPUT}; color: {TEXT_MAIN};
            selection-background-color: #14334f;
            selection-color: {PRIMARY_LIGHT};
            border: 1px solid {BORDER_ACCENT}; padding: 4px;
        }}
        QPlainTextEdit {{
            background: {BG_INPUT}; color: {TEXT_MAIN};
            border: 1px solid {BORDER_ACCENT};
            border-radius: 8px; padding: 8px; font-size: 12px;
        }}
        QPlainTextEdit:focus {{ border: 1px solid {PRIMARY}; background: #0d2133; }}
        """

    if with_tabs:
        base += f"""
        QTabWidget::pane {{
            border: 1px solid {BORDER_SUBTLE};
            background: #07111c; border-radius: 10px;
        }}
        QTabBar::tab {{
            background: {BG_PANEL}; color: {TEXT_MUTED};
            font-weight: 700; font-size: 11px;
            padding: 8px 16px;
            border-top-left-radius: 8px; border-top-right-radius: 8px;
            margin-right: 4px;
        }}
        QTabBar::tab:selected {{
            background: #12334f; color: {PRIMARY_LIGHT};
            border-bottom: 2px solid {PRIMARY};
        }}
        QTabBar::tab:hover:!selected {{ background-color: #142a40; }}
        """
    return base


# ═════════════════════════════════════════════════════════════
#  THREAD CLEANUP HELPER
# ═════════════════════════════════════════════════════════════
def stop_thread_safely(thread, *, wait_ms: int = 3000) -> None:
    """Gracefully stop and dispose of a QThread."""
    if thread is None:
        return
    try:
        if thread.isRunning():
            try:
                thread.requestInterruption()
            except Exception:
                pass
            thread.wait(wait_ms)
        thread.deleteLater()
    except Exception as e:
        logger.warning("Thread stop failed: %s", e)