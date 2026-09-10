# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium Global Persian-Sky Professional Theme
═══════════════════════════════════════════════════════════════
Version : 5.2.0 (Production Master Theme)
Engine  : PyQt6
Design  : Persian-Sky Turquoise / Clean Professional Palette
Features:
  • 100% Comprehensive Qt Widget Styling (Tables, Trees, Calendars, Tooltips)
  • Pixel-perfect Scrollbars (both Horizontal & Vertical)
  • Dark Mode Calendar Widget (Eliminates blinding white default popups)
  • Dynamic Button Archetypes ([primary="true"], [danger="true"], [success="true"])
  • Consistent High-Contrast Typography & Accessibility
  • Programmatic Palette Export via get_theme_palette()
  • Memory-safe and valid Python import across the entire suite
"""

from typing import Dict, Any

# ═════════════════════════════════════════════════════════════
#  GLOBAL COLOR PALETTE CONSTANTS
# ═════════════════════════════════════════════════════════════

BG_DEEP       = "#F4FBFC"  # Deepest background (App frame, Menu bars)
BG_APP        = "#FFFFFF"  # Main container background
BG_PANEL      = "#F7FCFD"  # Elevated cards, inspection panels, sidebars
BG_INPUT      = "#FFFFFF"  # Text fields, Combos, Spinboxes, Table background
BG_ELEVATED   = "#E6F7F8"  # Hovered elements, active selection states

PRIMARY       = "#13A7B5"  # Core Cyan / Highlight color
PRIMARY_LIGHT = "#087F8C"  # Radiant cyan for titles, headers & focus rings
ACCENT        = "#0EA0AD"  # Action gradient & glow accent

TEXT_MAIN     = "#173B45"  # High-contrast clean white-blue text
TEXT_MUTED    = "#6C8D95"  # Secondary text / metadata labels
TEXT_FOOTER   = "#86A3AA"  # Subtle stamps, footers, and dividers

BORDER_SUBTLE = "#CBE8EB"  # Card and table perimeter borders
BORDER_ACCENT = "#B9DDE1"  # Active inputs & interactive widget borders
BORDER_FOCUS  = "#13A7B5"  # Focused state borders

SUCCESS       = "#5cffaa"  # Emerald green (Cleared, Accepted, 100% Pass)
WARNING       = "#ffd966"  # Warm amber (Pending, Under Review, Category B)
ERROR         = "#ff6b6b"  # Crimson red (Rejected, Category A, Expired)
INFO          = "#13A7B5"  # Information & tracer indicator


def get_theme_palette() -> Dict[str, str]:
    """Returns a dictionary containing all active theme color constants."""
    return {k: v for k, v in globals().items() if k.isupper() and isinstance(v, str)}


# ═════════════════════════════════════════════════════════════
#  MASTER QT STYLESHEET (QSS)
# ═════════════════════════════════════════════════════════════

MAIN_WINDOW_QSS = f"""
/* ── Global Base Configuration ────────────────────────────── */
QMainWindow, QDialog {{
    background-color: {BG_APP};
    color: {TEXT_MAIN};
}}

QWidget {{
    font-family: 'Segoe UI', 'SF Pro Display', 'Roboto', sans-serif;
    font-size: 12px;
    color: {TEXT_MAIN};
    selection-background-color: #12334f;
    selection-color: {PRIMARY_LIGHT};
}}

QWidget:disabled {{
    color: #4a6375;
}}

/* ── Panels, Cards & Frames ───────────────────────────────── */
QFrame#mainCard, QWidget#mainCard {{
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 {BG_DEEP},
        stop:0.35 {BG_APP},
        stop:1 {BG_DEEP}
    );
    border: 2px solid qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 {PRIMARY},
        stop:0.5 #287da5,
        stop:1 {PRIMARY}
    );
    border-radius: 18px;
}}

QFrame#panelCard, QFrame#inspectorCard, QFrame#detailPanel, QFrame#formGroup {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 10px;
}}

QFrame#headerFrame, QFrame#innerBox, QFrame#metaFrame {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
}}

QFrame#headerFrame:hover {{
    border: 1px solid {PRIMARY};
}}

QFrame#divider {{
    background: rgba(108, 207, 246, 0.25);
    border: none;
    height: 1px;
}}

/* ── Typography & Headers ─────────────────────────────────── */
QLabel#mainTitle {{
    color: {PRIMARY_LIGHT};
    font-size: 18px;
    font-weight: 900;
    letter-spacing: 2px;
    background: transparent;
}}

QLabel#subTitle {{
    color: {PRIMARY};
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.2px;
    background: transparent;
}}

QLabel#sectionTitle {{
    color: {PRIMARY_LIGHT};
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1.5px;
    background: transparent;
    padding-bottom: 2px;
}}

QLabel#muted, QLabel#footerLabel {{
    color: {TEXT_MUTED};
    font-size: 11px;
    background: transparent;
}}

/* ── GroupBox Container ───────────────────────────────────── */
QGroupBox {{
    font-weight: 800;
    font-size: 11px;
    color: {PRIMARY_LIGHT};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 14px;
    background-color: {BG_PANEL};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {PRIMARY};
}}

/* ── Input Fields & Controls ──────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {{
    background-color: {BG_INPUT};
    color: {TEXT_MAIN};
    border: 1px solid {BORDER_ACCENT};
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus {{
    border: 1px solid {BORDER_FOCUS};
    background-color: #0d2133;
}}

QLineEdit::placeholder, QTextEdit::placeholder {{
    color: {TEXT_MUTED};
}}

/* ComboBox Specials */
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox QAbstractItemView {{
    background-color: {BG_INPUT};
    color: {TEXT_MAIN};
    selection-background-color: #14334f;
    selection-color: {PRIMARY_LIGHT};
    border: 1px solid {BORDER_ACCENT};
    padding: 4px;
}}

/* SpinBox Specials */
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 16px;
    background: transparent;
}}

/* ── Dark Calendar Widget Popup ───────────────────────────── */
QCalendarWidget QWidget {{
    background-color: {BG_APP};
    color: {TEXT_MAIN};
}}

QCalendarWidget QAbstractItemView:enabled {{
    background-color: {BG_INPUT};
    color: {TEXT_MAIN};
    selection-background-color: #14334f;
    selection-color: {PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
}}

QCalendarWidget QAbstractItemView:disabled {{
    color: #4a6375;
}}

QCalendarWidget QSpinBox {{
    background-color: {BG_INPUT};
    color: {TEXT_MAIN};
    border: 1px solid {BORDER_ACCENT};
}}

/* ── Buttons & Action Controls ────────────────────────────── */
QPushButton {{
    background-color: {BG_PANEL};
    color: {PRIMARY_LIGHT};
    border: 1px solid {BORDER_ACCENT};
    border-radius: 8px;
    padding: 7px 15px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

QPushButton:hover {{
    background-color: #142a40;
    border-color: {PRIMARY};
    color: {ACCENT};
}}

QPushButton:pressed {{
    background-color: #0c1c2e;
}}

QPushButton:disabled {{
    background-color: #0a1420;
    color: #3f5567;
    border-color: #102130;
}}

/* Primary Action Buttons */
QPushButton[primary="true"], QPushButton#actionBtn, QPushButton#saveBtn {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #2196d4,
        stop:0.5 {ACCENT},
        stop:1 #2196d4
    );
    color: #041827;
    border: none;
    font-weight: 800;
    letter-spacing: 1px;
}}

QPushButton[primary="true"]:hover, QPushButton#actionBtn:hover, QPushButton#saveBtn:hover {{
    background: {PRIMARY_LIGHT};
    color: #041827;
}}

QPushButton[primary="true"]:pressed, QPushButton#actionBtn:pressed, QPushButton#saveBtn:pressed {{
    background: #2196d4;
}}

/* Success Buttons */
QPushButton[success="true"], QPushButton#btnAccept {{
    background-color: #0b3320;
    color: {SUCCESS};
    border: 1px solid #1c6640;
    font-weight: 700;
}}

QPushButton[success="true"]:hover, QPushButton#btnAccept:hover {{
    background-color: #135233;
}}

/* Warning / Hold Buttons */
QPushButton[warning="true"], QPushButton#btnHold {{
    background-color: #33280b;
    color: {WARNING};
    border: 1px solid #66501c;
    font-weight: 700;
}}

QPushButton[warning="true"]:hover, QPushButton#btnHold:hover {{
    background-color: #4d3d12;
}}

/* Danger / Delete Buttons */
QPushButton[danger="true"], QPushButton#btnReject, QPushButton#btnDelete {{
    background-color: #330b0b;
    color: {ERROR};
    border: 1px solid #661c1c;
    font-weight: 700;
}}

QPushButton[danger="true"]:hover, QPushButton#btnReject:hover, QPushButton#btnDelete:hover {{
    background-color: #521313;
}}

/* Window Close Button */
QPushButton#closeBtn {{
    background: transparent;
    color: {TEXT_MUTED};
    border: none;
    border-radius: 14px;
    font-size: 14px;
    font-weight: bold;
}}

QPushButton#closeBtn:hover {{
    background: rgba(255, 107, 107, 0.2);
    color: {ERROR};
}}

/* ── CheckBox & RadioButtons ──────────────────────────────── */
QCheckBox, QRadioButton {{
    color: {TEXT_MAIN};
    font-size: 11px;
    spacing: 8px;
    background: transparent;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {BORDER_ACCENT};
    border-radius: 3px;
    background-color: {BG_INPUT};
}}

QRadioButton::indicator {{
    border-radius: 8px;
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {PRIMARY};
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {PRIMARY};
    border-color: {PRIMARY};
    image: none;
}}

/* ── Data Tables & Views ──────────────────────────────────── */
QTableWidget, QTableView, QTreeWidget, QTreeView, QListView {{
    background-color: #07111c;
    alternate-background-color: #091520;
    color: {TEXT_MAIN};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
    gridline-color: transparent;
    font-size: 12px;
}}

QTableWidget::item, QTableView::item {{
    padding: 7px 9px;
    border-bottom: 1px solid #0c1f30;
}}

QTableWidget::item:selected, QTableView::item:selected {{
    background-color: #133959;
    color: {PRIMARY_LIGHT};
    border-left: 2px solid {PRIMARY};
}}

QHeaderView::section {{
    background-color: #0c1c2e;
    color: {PRIMARY_LIGHT};
    font-weight: 800;
    font-size: 10px;
    letter-spacing: 1px;
    border: none;
    border-bottom: 2px solid #1c4466;
    border-right: 1px solid {BORDER_SUBTLE};
    padding: 8px 9px;
}}

QHeaderView::section:hover {{
    background-color: {BG_ELEVATED};
}}

/* ── Tabs & TabWidget ─────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {BORDER_SUBTLE};
    background-color: #07111c;
    border-radius: 8px;
    top: -1px;
}}

QTabBar::tab {{
    background-color: {BG_PANEL};
    color: {TEXT_MUTED};
    font-weight: 700;
    font-size: 11px;
    padding: 8px 16px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 4px;
    border: 1px solid {BORDER_SUBTLE};
    border-bottom: none;
}}

QTabBar::tab:selected {{
    background-color: #12334f;
    color: {PRIMARY_LIGHT};
    border-bottom: 2px solid {PRIMARY};
}}

QTabBar::tab:hover:!selected {{
    background-color: #142a40;
    color: {TEXT_MAIN};
}}

/* ── Progress Bar ─────────────────────────────────────────── */
QProgressBar {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER_ACCENT};
    border-radius: 6px;
    text-align: center;
    color: {TEXT_MAIN};
    font-weight: bold;
    font-size: 10px;
}}

QProgressBar::chunk {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #2196d4,
        stop:1 {ACCENT}
    );
    border-radius: 5px;
}}

/* ── Scrollbars (Horizontal & Vertical) ───────────────────── */
QScrollBar:vertical {{
    background-color: {BG_INPUT};
    width: 10px;
    border-radius: 5px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: {BORDER_ACCENT};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {PRIMARY};
}}

QScrollBar:horizontal {{
    background-color: {BG_INPUT};
    height: 10px;
    border-radius: 5px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background-color: {BORDER_ACCENT};
    border-radius: 5px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {PRIMARY};
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}

QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ── Menus & Toolbars ─────────────────────────────────────── */
QMenuBar {{
    background-color: {BG_APP};
    color: {TEXT_MAIN};
    border-bottom: 1px solid {BORDER_SUBTLE};
    padding: 3px;
}}

QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 4px;
}}

QMenuBar::item:selected {{
    background-color: {BG_PANEL};
    color: {PRIMARY};
}}

QMenu {{
    background-color: {BG_APP};
    color: {TEXT_MAIN};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 6px;
    padding: 4px;
}}

QMenu::item {{
    padding: 7px 24px 7px 12px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: #14334f;
    color: {PRIMARY_LIGHT};
}}

QMenu::separator {{
    height: 1px;
    background-color: {BORDER_SUBTLE};
    margin: 4px 8px;
}}

/* ── Splitters & ToolTips ─────────────────────────────────── */
QSplitter::handle {{
    background-color: #102538;
    border-radius: 2px;
}}

QSplitter::handle:hover {{
    background-color: {PRIMARY};
}}

QToolTip {{
    background-color: {BG_APP};
    color: {PRIMARY_LIGHT};
    border: 1px solid {PRIMARY};
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 11px;
}}
"""


def apply_theme(app_or_widget) -> None:
    """Applies the master PipeAgent professional stylesheet to the application or a widget."""
    app_or_widget.setStyleSheet(MAIN_WINDOW_QSS)