# -*- coding: utf-8 -*-
"""Central Persian Sky theme for PipeAgent's PyQt6 interface.

Keep application-wide colors here so standard widgets and dialogs share one
accessible palette. Custom-painted splash artwork may retain its animation,
but interactive forms use the same turquoise/sky visual language.
"""
from __future__ import annotations

from PyQt6.QtGui import QFont

PRIMARY = "#0F9D9A"
SKY = "#54C5E8"
BG = "#EAF4F6"
SURFACE = "#FFFFFF"
TEXT = "#173B45"
MUTED = "#527780"
BORDER = "#B9DDE1"
HOVER = "#D8F5F6"


def apply_persian_sky(app) -> None:
    """Apply the shared Persian Sky palette before any window is created."""
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet("""
        QWidget {
            color: #173B45;
            font-family: "Segoe UI";
            font-size: 10pt;
        }
        QDialog, QMessageBox { background: #EAF4F6; }
        QLabel { background: transparent; }
        QLineEdit, QPlainTextEdit, QTextEdit, QComboBox,
        QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit {
            color: #173B45;
            background: #FFFFFF;
            border: 1px solid #B9DDE1;
            border-radius: 7px;
            padding: 7px 9px;
            selection-background-color: #0F9D9A;
            selection-color: #FFFFFF;
        }
        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
        QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
        QDateEdit:focus, QTimeEdit:focus {
            border: 2px solid #0F9D9A;
            background: #FCFFFF;
        }
        QPushButton {
            color: #0F7776;
            background: #FFFFFF;
            border: 1px solid #9BD6D8;
            border-radius: 7px;
            padding: 7px 14px;
            font-weight: 600;
        }
        QPushButton:hover {
            background: #D8F5F6;
            border-color: #0F9D9A;
        }
        QPushButton:pressed { background: #C4EBED; }
        QPushButton:disabled {
            color: #8AA5AC;
            background: #F0F6F7;
            border-color: #D7E7E9;
        }
        QCheckBox, QRadioButton { spacing: 7px; }
        QCheckBox::indicator, QRadioButton::indicator {
            width: 16px; height: 16px;
        }
        QCheckBox::indicator:checked {
            background: #0F9D9A;
            border: 1px solid #0F9D9A;
            border-radius: 3px;
        }
        QGroupBox {
            color: #0F7776;
            background: #FFFFFF;
            border: 1px solid #B9DDE1;
            border-radius: 8px;
            margin-top: 12px;
            padding: 14px 8px 8px 8px;
            font-weight: 700;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
            color: #0F9D9A;
        }
        QComboBox QAbstractItemView {
            color: #173B45;
            background: #FFFFFF;
            selection-background-color: #D8F5F6;
            selection-color: #075D67;
            border: 1px solid #B9DDE1;
        }
        QScrollBar:vertical {
            background: #EDF7F8; width: 10px; border-radius: 5px;
        }
        QScrollBar::handle:vertical {
            background: #A8DCE0; border-radius: 5px; min-height: 24px;
        }
        QScrollBar::handle:vertical:hover { background: #0F9D9A; }
        QToolTip {
            color: #FFFFFF; background: #075D67;
            border: 1px solid #54C5E8; padding: 5px;
        }
    """)
