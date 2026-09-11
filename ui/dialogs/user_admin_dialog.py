# -*- coding: utf-8 -*-
"""
PipeAgent — Ultra-Premium User Administration & Security Control Dialog
═══════════════════════════════════════════════════════════════════════════
Version : 5.0 (Refactored, hardened, production-ready)
Engine  : PyQt6
Design  : Cinematic dark-tech theme matching PipeAgent Suite

Fixes in this revision
──────────────────────
🔴 P0  Missing QMenu import : added to QtWidgets imports (was crashing on
                             right-click because QMenu was undefined)
🔴 P0  Card border          : replaced invalid `border: ... qlineargradient`
                             with a solid color + drop shadow
🔴 P0  GlowLineEdit         : no longer calls deleteLater() on an animation
                             that Qt owns (DeleteWhenStopped)
🔴 P0  Sort-safe selection  : every row stores its user dict on
                             QTableWidgetItem.UserRole
🔴 P0  Stable user ids      : every user has a `user_id`; lookups no longer
                             rely on `list.index(dict)`
🟠 P1  Cleanup              : `_cleanup()` idempotent + `done()` overridden
🟠 P1  Particle geometry    : set immediately after creation
🟠 P1  Delete shortcut      : bound to the table only (WidgetShortcut)
🟡 P2  ParticleField        : count 30 → 14, tick 60ms → 100ms, paints only
                             when visible
🟡 P2  Duplicate check      : `_existing_usernames` is now a set (O(1))
🟡 P2  _clear_inspector     : driven by a declared label spec
🟢 P3  Tooltips             : on every field / button
"""

from __future__ import annotations

import os
import sys
import csv
import random
import uuid
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Iterable

from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRect, QSize,
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
    QFileDialog, QCheckBox, QScrollArea,
    QMenu,   # 🔧 Added — was missing in the previous version.
)

from db.models import User
from services.module_access import SITE_ROLES, canonical_role, role_label

logger = logging.getLogger(__name__)


def _employee_id(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text or text.upper() == "N/A":
        return None
    return text


# ════════════════════════════════════════════════════════════════
#  UTILITIES
# ════════════════════════════════════════════════════════════════

def _uid() -> str:
    return "U" + uuid.uuid4().hex[:9].upper()


def _today_str() -> str:
    return datetime.today().strftime("%Y-%m-%d")


# ════════════════════════════════════════════════════════════════
#  PARTICLE FIELD — Animated Background
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
                "vy": random.uniform(-0.0005, -0.0001),
                "r": random.uniform(0.8, 1.8),
                "alpha": random.randint(15, 60),
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
#  GLOW LINE EDIT — Focus Glow (Memory Leak Fixed)
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


# ════════════════════════════════════════════════════════════════
#  KPI STAT CARD
# ════════════════════════════════════════════════════════════════

class StatCard(QFrame):
    """Metric tile with left glow accent."""

    def __init__(self, title: str, value: str, icon: str, accent_color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setFixedHeight(68)
        self.setMinimumWidth(160)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI", 18))
        icon_lbl.setStyleSheet(f"color: {accent_color}; background: transparent;")
        layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)

        self.val_lbl = QLabel(value)
        self.val_lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self.val_lbl.setStyleSheet(f"color: {accent_color}; background: transparent;")
        text_col.addWidget(self.val_lbl)

        self.title_lbl = QLabel(title)
        self.title_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        self.title_lbl.setStyleSheet(
            "color: #7a9ab3; letter-spacing: 1px; background: transparent;"
        )
        text_col.addWidget(self.title_lbl)

        layout.addLayout(text_col, 1)

        self.setStyleSheet(f"""
            QFrame#statCard {{
                background: #0a1826;
                border: 1px solid rgba(108, 207, 246, 0.18);
                border-left: 3px solid {accent_color};
                border-radius: 8px;
            }}
        """)

    def update_value(self, val: str):
        self.val_lbl.setText(val)


# ════════════════════════════════════════════════════════════════
#  ADD / EDIT USER SUB-MODAL
# ════════════════════════════════════════════════════════════════

class AddEditUserDialog(QDialog):
    """Sub-modal for registering or editing a user account."""

    def __init__(
        self,
        user_data: Optional[Dict[str, Any]] = None,
        existing_usernames: Optional[Iterable[str]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.user_data = user_data
        self.is_edit = user_data is not None
        # Set membership → O(1) duplicate lookup.
        self._existing_usernames = {str(u).lower() for u in (existing_usernames or [])}

        self.setWindowTitle("User Account Configuration")
        self.setMinimumSize(520, 620)
        self.setMaximumSize(700, 780)
        self.resize(520, 640)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos: Optional[QPoint] = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("userCard")
        card.setStyleSheet("""
            QWidget#userCard {
                background: #0b1624;
                border: 2px solid #6ccff6;
                border-radius: 14px;
            }
            QLabel { color: #9fe7ff; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
            QLineEdit, QComboBox {
                background: #07101a;
                color: #eef6ff;
                border: 1px solid #18364a;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #6ccff6;
            }
            QComboBox QAbstractItemView {
                background: #07101a;
                color: #eef6ff;
                selection-background-color: #14334f;
                selection-color: #9fe7ff;
                border: 1px solid #18364a;
            }
            QCheckBox {
                color: #c8dcea;
                font-size: 11px;
            }
        """)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: #07101a; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #1e3d5a; border-radius: 4px; min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #6ccff6; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        form_widget = QWidget()
        form_widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(form_widget)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(9)

        head = QHBoxLayout()
        title_text = "👤   EDIT USER PROFILE" if self.is_edit else "👤   CREATE NEW USER ACCOUNT"
        title = QLabel(title_text)
        title.setStyleSheet(
            "font-size: 13px; color: #9fe7ff; "
            "font-weight: 900; letter-spacing: 2px;"
        )
        head.addWidget(title)
        head.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close (Escape)")
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #7a9ab3;
                border: 1px solid transparent; border-radius: 14px;
                font-weight: bold; font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(255, 107, 107, 0.2); color: #ff6b6b;
                border: 1px solid rgba(255, 107, 107, 0.3);
            }
        """)
        close_btn.clicked.connect(self.reject)
        head.addWidget(close_btn)
        layout.addLayout(head)

        layout.addSpacing(4)

        row1 = QHBoxLayout()
        col_u = QVBoxLayout()
        col_u.addWidget(QLabel("USERNAME / LOGIN ID *"))
        self.in_username = QLineEdit()
        self.in_username.setPlaceholderText("e.g. kaveh.qc")
        self.in_username.setToolTip("Unique login identifier — required")
        if self.is_edit:
            self.in_username.setText(self.user_data.get("username", ""))
            self.in_username.setReadOnly(True)
            self.in_username.setStyleSheet("color: #7a9ab3;")
            self.in_username.setToolTip("Username cannot be changed after creation")
        col_u.addWidget(self.in_username)
        row1.addLayout(col_u)

        col_fn = QVBoxLayout()
        col_fn.addWidget(QLabel("FULL NAME & TITLE *"))
        self.in_fullname = QLineEdit()
        self.in_fullname.setPlaceholderText("e.g. Eng. Kaveh Farhadi")
        self.in_fullname.setToolTip("Full name and title — required")
        if self.is_edit:
            self.in_fullname.setText(self.user_data.get("fullname", ""))
        col_fn.addWidget(self.in_fullname)
        row1.addLayout(col_fn)
        layout.addLayout(row1)

        self.lbl_dup_warn = QLabel("⚠ This Username is already taken!")
        self.lbl_dup_warn.setStyleSheet(
            "color: #ff9f43; font-size: 10px; font-weight: 700; background: transparent;"
        )
        self.lbl_dup_warn.setVisible(False)
        layout.addWidget(self.lbl_dup_warn)
        self.in_username.textChanged.connect(self._check_duplicate_username)

        row2 = QHBoxLayout()
        col_em = QVBoxLayout()
        col_em.addWidget(QLabel("CORPORATE EMAIL"))
        self.in_email = QLineEdit()
        self.in_email.setPlaceholderText("e.g. kaveh@pipeagent.com")
        self.in_email.setToolTip("Email address for notifications")
        if self.is_edit:
            self.in_email.setText(self.user_data.get("email", ""))
        col_em.addWidget(self.in_email)
        row2.addLayout(col_em)

        col_st = QVBoxLayout()
        col_st.addWidget(QLabel("QC / INSPECTOR STAMP ID"))
        self.in_stamp = QLineEdit()
        self.in_stamp.setPlaceholderText("e.g. QC-STAMP-04")
        self.in_stamp.setToolTip("Digital signature stamp identifier")
        if self.is_edit:
            self.in_stamp.setText(self.user_data.get("stamp_id", ""))
        col_st.addWidget(self.in_stamp)
        row2.addLayout(col_st)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        col_role = QVBoxLayout()
        col_role.addWidget(QLabel("PRIMARY PROJECT ROLE"))
        self.in_role = QComboBox()
        for key, label in SITE_ROLES:
            self.in_role.addItem(label, key)
        self.in_role.setToolTip("Primary RBAC role on the project")
        if self.is_edit:
            current = canonical_role(self.user_data.get("role", "viewer"))
            idx = self.in_role.findData(current)
            if idx >= 0:
                self.in_role.setCurrentIndex(idx)
        col_role.addWidget(self.in_role)
        row3.addLayout(col_role)

        col_dept = QVBoxLayout()
        col_dept.addWidget(QLabel("DEPARTMENT"))
        self.in_dept = QComboBox()
        self.in_dept.addItems([
            "Quality Assurance / QC", "Construction / Piping",
            "Engineering & DCC", "Warehouse & Logistics",
            "Project Management", "Client PMT",
        ])
        self.in_dept.setToolTip("Department assignment")
        if self.is_edit:
            self.in_dept.setCurrentText(
                self.user_data.get("dept", "Quality Assurance / QC")
            )
        col_dept.addWidget(self.in_dept)
        row3.addLayout(col_dept)
        layout.addLayout(row3)

        if not self.is_edit:
            layout.addWidget(QLabel("INITIAL PASSWORD *"))
            self.in_password = QLineEdit()
            self.in_password.setEchoMode(QLineEdit.EchoMode.Password)
            self.in_password.setPlaceholderText("Min. 8 characters")
            self.in_password.setToolTip("Initial login password — minimum 8 characters")
            layout.addWidget(self.in_password)

        layout.addWidget(QLabel("AUTHORIZED DIGITAL SIGN-OFF PRIVILEGES"))
        perm_frame = QFrame()
        perm_frame.setStyleSheet(
            "background: #07101a; border: 1px solid #18364a; "
            "border-radius: 6px; padding: 6px;"
        )
        p_layout = QVBoxLayout(perm_frame)
        p_layout.setSpacing(4)

        self.chk_wjcs = QCheckBox("Can Approve Fit-up & Welding Reports (WJCS)")
        self.chk_ndt  = QCheckBox("Can Authorize & Clear NDT Records (RT, UT, PAUT)")
        self.chk_dcc  = QCheckBox("Can Issue IFC Drawings & Bump Revisions (DCC)")
        self.chk_mrir = QCheckBox("Can Clear Material Receiving Inspection (MRIR)")
        self.chk_hyd  = QCheckBox("Can Sign-off Hydrotest & Turnover Dossiers")

        for chk in [self.chk_wjcs, self.chk_ndt, self.chk_dcc, self.chk_mrir, self.chk_hyd]:
            p_layout.addWidget(chk)

        if self.is_edit:
            perms = self.user_data.get("perms", {})
            self.chk_wjcs.setChecked(perms.get("wjcs", False))
            self.chk_ndt.setChecked(perms.get("ndt", False))
            self.chk_dcc.setChecked(perms.get("dcc", False))
            self.chk_mrir.setChecked(perms.get("mrir", False))
            self.chk_hyd.setChecked(perms.get("hydro", False))
        else:
            self.chk_wjcs.setChecked(True)
            self.chk_ndt.setChecked(True)

        layout.addWidget(perm_frame)

        self.chk_active = QCheckBox("Account Active & Enabled")
        self.chk_active.setChecked(
            True if not self.is_edit
            else self.user_data.get("status", "Active") == "Active"
        )
        layout.addWidget(self.chk_active)

        layout.addSpacing(6)

        submit_btn = QPushButton("⚡  CONFIRM & SAVE USER")
        submit_btn.setMinimumHeight(44)
        submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        submit_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2196d4, stop:1 #68d7ff);
                color: #041827; border: none; border-radius: 8px;
                font-weight: 800; letter-spacing: 1px; font-size: 12px;
            }
            QPushButton:hover { background: #68d7ff; }
            QPushButton:pressed { background: #2196d4; }
        """)
        submit_btn.clicked.connect(self._validate_and_accept)
        layout.addWidget(submit_btn)

        cancel_btn = QPushButton("CANCEL")
        cancel_btn.setMinimumHeight(36)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #7a9ab3;
                border: 1px solid #1e3d5a; border-radius: 8px;
                font-weight: 700; font-size: 11px; letter-spacing: 1px;
            }
            QPushButton:hover {
                background: #142a40; border: 1px solid #6ccff6; color: #9fe7ff;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        scroll.setWidget(form_widget)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(scroll)

        outer.addWidget(card)

    def _check_duplicate_username(self, text: str):
        if self.is_edit:
            return
        is_dup = text.strip().lower() in self._existing_usernames
        self.lbl_dup_warn.setVisible(is_dup)

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

    def _validate_and_accept(self):
        username = self.in_username.text().strip().lower()
        if not username:
            QMessageBox.warning(
                self, "Validation Error", "Username is required."
            )
            self.in_username.setFocus()
            return

        if not self.is_edit and username in self._existing_usernames:
            reply = QMessageBox.question(
                self, "Username Taken",
                f"Username <b>{username}</b> is already registered.\n\n"
                "Do you still want to register with this login ID?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        if not self.in_fullname.text().strip():
            QMessageBox.warning(
                self, "Validation Error", "Full Name is required."
            )
            self.in_fullname.setFocus()
            return

        if not self.is_edit and len(self.in_password.text().strip()) < 8:
            QMessageBox.warning(
                self, "Validation Error",
                "Password must be at least 8 characters."
            )
            self.in_password.setFocus()
            return

        self.accept()

    def get_data(self) -> Dict[str, Any]:
        return {
            "user_id": (
                self.user_data.get("user_id", _uid())
                if self.is_edit else _uid()
            ),
            "username": self.in_username.text().strip().lower(),
            "fullname": self.in_fullname.text().strip(),
            "email": self.in_email.text().strip() or "user@pipeagent.com",
            "stamp_id": self.in_stamp.text().strip().upper() or "N/A",
            "role": self.in_role.currentData() or canonical_role(self.in_role.currentText()),
            "password": self.in_password.text().strip() if hasattr(self, "in_password") else "",
            "dept": self.in_dept.currentText(),
            "status": "Active" if self.chk_active.isChecked() else "Suspended",
            "last_login": (
                self.user_data.get("last_login", "Never")
                if self.is_edit else "Never"
            ),
            "created_date": (
                self.user_data.get("created_date", _today_str())
                if self.is_edit else _today_str()
            ),
            "perms": {
                "wjcs": self.chk_wjcs.isChecked(),
                "ndt": self.chk_ndt.isChecked(),
                "dcc": self.chk_dcc.isChecked(),
                "mrir": self.chk_mrir.isChecked(),
                "hydro": self.chk_hyd.isChecked(),
            },
        }


# ════════════════════════════════════════════════════════════════
#  RESET PASSWORD MODAL
# ════════════════════════════════════════════════════════════════

class ResetPasswordDialog(QDialog):
    """Sub-modal for administrative password resets."""

    def __init__(self, username: str, parent=None):
        super().__init__(parent)
        self.username = username
        self.setWindowTitle(f"Reset Password • {self.username}")
        self.setFixedSize(420, 340)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos: Optional[QPoint] = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("resetCard")
        card.setStyleSheet("""
            QWidget#resetCard {
                background: #0b1624;
                border: 2px solid #6ccff6;
                border-radius: 14px;
            }
            QLabel { color: #9fe7ff; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
            QLineEdit {
                background: #07101a;
                color: #eef6ff;
                border: 1px solid #18364a;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #6ccff6; }
            QCheckBox { color: #c8dcea; font-size: 11px; }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(26, 20, 26, 20)
        layout.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel(f"🔐   RESET PASSWORD: {self.username.upper()}")
        title.setStyleSheet(
            "font-size: 11px; color: #9fe7ff; "
            "font-weight: 900; letter-spacing: 1.5px;"
        )
        head.addWidget(title)
        head.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close (Escape)")
        close_btn.setStyleSheet(
            "background:transparent; color:#7a9ab3; border:none; font-weight:bold;"
        )
        close_btn.clicked.connect(self.reject)
        head.addWidget(close_btn)
        layout.addLayout(head)

        layout.addSpacing(6)

        layout.addWidget(QLabel("NEW TEMPORARY PASSWORD"))
        self.in_new_pw = QLineEdit()
        self.in_new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_new_pw.setPlaceholderText("Enter new secure password (Min 8 char)")
        self.in_new_pw.setToolTip("New password — minimum 8 characters")
        layout.addWidget(self.in_new_pw)

        layout.addWidget(QLabel("CONFIRM NEW PASSWORD"))
        self.in_conf_pw = QLineEdit()
        self.in_conf_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_conf_pw.setPlaceholderText("Re-type password")
        self.in_conf_pw.setToolTip("Re-type to confirm")
        layout.addWidget(self.in_conf_pw)

        self.chk_force = QCheckBox("Require password change at next login")
        self.chk_force.setChecked(True)
        layout.addWidget(self.chk_force)

        layout.addSpacing(8)

        btn_save = QPushButton("⚡  APPLY PASSWORD RESET")
        btn_save.setMinimumHeight(40)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2196d4, stop:1 #68d7ff);
                color: #041827; border: none; border-radius: 8px;
                font-weight: 800; letter-spacing: 1px; font-size: 11px;
            }
            QPushButton:hover { background: #68d7ff; }
        """)
        btn_save.clicked.connect(self._validate_and_accept)
        layout.addWidget(btn_save)

        outer.addWidget(card)

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

    def _validate_and_accept(self):
        p1 = self.in_new_pw.text().strip()
        p2 = self.in_conf_pw.text().strip()
        if len(p1) < 8:
            QMessageBox.warning(
                self, "Validation", "Password must be at least 8 characters."
            )
            return
        if p1 != p2:
            QMessageBox.warning(
                self, "Validation", "Passwords do not match."
            )
            return
        self.password = p1
        self.accept()

    def get_password(self) -> str:
        return getattr(self, "password", "")


# ════════════════════════════════════════════════════════════════
#  PROJECT SECURITY CONFIGS EDITOR
# ════════════════════════════════════════════════════════════════

class EditSecurityMetaDialog(QDialog):
    """Sub-modal for editing Project Security Metadata and LDAP server specs."""

    def __init__(self, current_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Security Parameters")
        self.setMinimumSize(500, 480)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos: Optional[QPoint] = None
        self._current_data = current_data
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("hdrCard")
        card.setStyleSheet("""
            QWidget#hdrCard {
                background: #0b1624;
                border: 2px solid #6ccff6;
                border-radius: 14px;
            }
            QLabel { color: #9fe7ff; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
            QLineEdit {
                background: #07101a; color: #eef6ff;
                border: 1px solid #18364a; border-radius: 6px;
                padding: 6px 10px; font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #6ccff6; }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(9)

        head = QHBoxLayout()

        drag_hint = QLabel("⠿")
        drag_hint.setStyleSheet(
            "color: #2a4a5a; font-size: 14px; background: transparent;"
        )
        drag_hint.setToolTip("Drag to move window")
        head.addWidget(drag_hint)

        title = QLabel("🛡️   PROJECT SECURITY PARAMETERS")
        title.setStyleSheet(
            "font-size: 13px; color: #9fe7ff; "
            "font-weight: 900; letter-spacing: 2px;"
        )
        head.addWidget(title)
        head.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close (Escape)")
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #7a9ab3;
                border: none; border-radius: 14px;
                font-weight: bold; font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(255, 107, 107, 0.2); color: #ff6b6b;
            }
        """)
        close_btn.clicked.connect(self.reject)
        head.addWidget(close_btn)
        layout.addLayout(head)

        layout.addWidget(QLabel("ACTIVE PIPING PROJECT NAME"))
        self.in_project = QLineEdit()
        self.in_project.setText(str(self._current_data.get("project", "")))
        layout.addWidget(self.in_project)

        layout.addWidget(QLabel("PRIMARY AUTHENTICATION MODE"))
        self.in_auth = QLineEdit()
        self.in_auth.setText(str(self._current_data.get("auth_mode", "")))
        layout.addWidget(self.in_auth)

        layout.addWidget(QLabel("LDAP / CORPORATE DIRECTORY SERVER"))
        self.in_ldap = QLineEdit()
        self.in_ldap.setText(str(self._current_data.get("ldap_server", "")))
        layout.addWidget(self.in_ldap)

        layout.addWidget(QLabel("STAMP DIGITAL SIGNATURE PROTOCOL"))
        self.in_crypto = QLineEdit()
        self.in_crypto.setText(str(self._current_data.get("crypto", "")))
        layout.addWidget(self.in_crypto)

        layout.addWidget(QLabel("SECURITY OFFICER CONTACT EMAIL"))
        self.in_so = QLineEdit()
        self.in_so.setText(str(self._current_data.get("so_contact", "")))
        layout.addWidget(self.in_so)

        layout.addSpacing(10)

        submit_btn = QPushButton("💾  SAVE ACCESS PROTOCOLS")
        submit_btn.setMinimumHeight(42)
        submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        submit_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2196d4, stop:1 #68d7ff);
                color: #041827; border: none; border-radius: 8px;
                font-weight: 800; letter-spacing: 1px; font-size: 12px;
            }
            QPushButton:hover { background: #68d7ff; }
        """)
        submit_btn.clicked.connect(self.accept)
        layout.addWidget(submit_btn)

        cancel_btn = QPushButton("CANCEL")
        cancel_btn.setMinimumHeight(36)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #7a9ab3;
                border: 1px solid #1e3d5a; border-radius: 8px;
                font-weight: 700; font-size: 11px; letter-spacing: 1px;
            }
            QPushButton:hover {
                background: #142a40; border: 1px solid #6ccff6; color: #9fe7ff;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        outer.addWidget(card)

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

    def get_data(self) -> Dict[str, str]:
        return {
            "project": self.in_project.text().strip(),
            "auth_mode": self.in_auth.text().strip(),
            "ldap_server": self.in_ldap.text().strip(),
            "crypto": self.in_crypto.text().strip(),
            "so_contact": self.in_so.text().strip(),
        }


# ════════════════════════════════════════════════════════════════
#  MAIN USER ADMINISTRATION DIALOG
# ════════════════════════════════════════════════════════════════

class UserAdminDialog(QDialog):
    """
    Ultra-premium User Administration & Access Control Dialog.
    Fully resizable, responsive, sortable, integrated with secure RBAC.
    """

    # ── Theme Palette ─────────────────────────────────────────
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
    INFO          = "#68d7ff"

    MIN_WIDTH  = 960
    MIN_HEIGHT = 620
    DEF_WIDTH  = 1240
    DEF_HEIGHT = 800

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self.db = db

        # Drag / resize state
        self._drag_pos: Optional[QPoint] = None
        self._drag_edge: Optional[str] = None
        self._drag_geometry: Optional[QRect] = None
        self._resize_margin = 8

        # Lifecycle
        self._is_closed = False
        self._ts_timer: Optional[QTimer] = None

        # View state
        self._users: List[Dict[str, Any]] = []
        self._filtered_users: List[Dict[str, Any]] = []

        self.setWindowTitle("PipeAgent – User Administration & Security")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(self.DEF_WIDTH, self.DEF_HEIGHT)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self._init_data()
        self._build_ui()
        self._setup_shortcuts()
        self._center_on_screen()
        self._apply_filters()
        self._update_kpi()

    def _user_to_row(self, user: User) -> Dict[str, Any]:
        last_login = "Never"
        if user.last_login:
            last_login = user.last_login.strftime("%Y-%m-%d %H:%M")
        created = ""
        if getattr(user, "created_at", None):
            created = user.created_at.strftime("%Y-%m-%d")
        return {
            "user_id": str(user.id),
            "pk": user.id,
            "username": user.username,
            "fullname": user.full_name or user.username,
            "email": user.email or "",
            "stamp_id": user.employee_id or "",
            "role": canonical_role(user.role),
            "role_label": role_label(user.role),
            "dept": user.department or "",
            "status": "Active" if user.is_active else "Suspended",
            "last_login": last_login,
            "created_date": created,
            "perms": {"wjcs": True, "ndt": True, "dcc": True, "mrir": True, "hydro": True},
        }

    def _init_data(self):
        self._project_security_meta: Dict[str, str] = {
            "project": "PipeAgent workspace",
            "auth_mode": "Local Encrypted Database",
            "ldap_server": "",
            "crypto": "Argon2id / PBKDF2 password hashing",
            "so_contact": "",
        }
        self._users = []
        if self.db is None:
            return
        try:
            with self.db.session_scope() as session:
                users = session.query(User).order_by(User.username).all()
                self._users = [self._user_to_row(user) for user in users]
        except Exception:
            logger.exception("Failed to load users from database")
            self._users = []
        self._filtered_users = list(self._users)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QWidget()
        self._card.setObjectName("mainCard")
        self._card.setStyleSheet(self._stylesheet())
        self._card.setMouseTracking(True)

        card_shadow = QGraphicsDropShadowEffect(self._card)
        card_shadow.setBlurRadius(45)
        card_shadow.setColor(QColor(0, 0, 0, 200))
        card_shadow.setOffset(0, 10)
        self._card.setGraphicsEffect(card_shadow)

        outer.addWidget(self._card)

        # Particles — set geometry immediately to avoid clustering at (0,0).
        self._particles = ParticleField(self._card, count=14)
        self._particles.setGeometry(0, 0, self.DEF_WIDTH, self.DEF_HEIGHT)
        self._particles.lower()

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(24, 14, 24, 14)
        card_layout.setSpacing(10)

        card_layout.addLayout(self._build_topbar())
        card_layout.addWidget(self._build_header_frame())
        card_layout.addLayout(self._build_kpi_ribbon())
        card_layout.addLayout(self._build_filter_bar())

        # Splitter: Table + Inspector
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setObjectName("mainSplitter")
        self._splitter.setHandleWidth(3)
        self._splitter.setChildrenCollapsible(False)

        self.table = self._build_table()
        self._splitter.addWidget(self.table)

        self.inspector_panel = self._build_inspector_panel()
        self._splitter.addWidget(self.inspector_panel)

        self._splitter.setSizes([850, 340])
        card_layout.addWidget(self._splitter, 1)

        card_layout.addLayout(self._build_footer())

        # Live timestamp
        self._update_timestamp()
        self._ts_timer = QTimer(self)
        self._ts_timer.timeout.connect(self._update_timestamp)
        self._ts_timer.start(30_000)

    def _build_topbar(self) -> QHBoxLayout:
        topbar = QHBoxLayout()
        topbar.setContentsMargins(0, 0, 0, 0)
        topbar.setSpacing(8)

        icon_lbl = QLabel("👥")
        icon_lbl.setFont(QFont("Segoe UI", 20))
        icon_lbl.setStyleSheet("background: transparent;")
        topbar.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)

        main_title = QLabel("PIPE AGENT  •  USER ADMINISTRATION & ACCESS CONTROL")
        main_title.setObjectName("mainTitle")
        self._add_glow(main_title, QColor(108, 207, 246, 120), blur=20)
        title_col.addWidget(main_title)

        sub_title = QLabel(
            "ROLE-BASED ACCESS CONTROL (RBAC)  •  DIGITAL SIGN-OFF STAMPS  •  QA/QC PRIVILEGES"
        )
        sub_title.setObjectName("subTitle")
        title_col.addWidget(sub_title)
        topbar.addLayout(title_col)
        topbar.addStretch()

        self.btn_add_user = QPushButton("➕  ADD USER  (Ctrl+N)")
        self.btn_add_user.setObjectName("actionBtn")
        self.btn_add_user.setMinimumHeight(36)
        self.btn_add_user.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_user.setToolTip("Register a new user account (Ctrl+N)")
        self.btn_add_user.clicked.connect(self._on_add_user)
        topbar.addWidget(self.btn_add_user)

        self.btn_export = QPushButton("📤  EXPORT AUDIT  (Ctrl+E)")
        self.btn_export.setObjectName("secondaryBtn")
        self.btn_export.setMinimumHeight(36)
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.setToolTip("Export Security Access Audit Register to CSV (Ctrl+E)")
        self.btn_export.clicked.connect(self._on_export_audit)
        topbar.addWidget(self.btn_export)

        min_btn = QPushButton("─")
        min_btn.setObjectName("minBtn")
        min_btn.setFixedSize(30, 30)
        min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        min_btn.setToolTip("Minimize")
        min_btn.clicked.connect(self.showMinimized)
        min_btn.setStyleSheet("""
            QPushButton#minBtn {
                background: transparent; color: #7a9ab3;
                border: none; border-radius: 15px;
                font-size: 14px; font-weight: bold;
            }
            QPushButton#minBtn:hover {
                background: rgba(108, 207, 246, 0.15); color: #6ccff6;
            }
        """)
        topbar.addWidget(min_btn)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close (Escape)")
        close_btn.clicked.connect(self._on_close)
        topbar.addWidget(close_btn)

        return topbar

    def _build_header_frame(self) -> QFrame:
        self.header_frame = QFrame()
        self.header_frame.setObjectName("headerFrame")
        self.header_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_frame.setToolTip("Double-click anywhere to edit security configs")

        h_layout = QHBoxLayout(self.header_frame)
        h_layout.setContentsMargins(14, 8, 14, 8)
        h_layout.setSpacing(16)

        self.lbl_proj   = QLabel()
        self.lbl_auth   = QLabel()
        self.lbl_ldap   = QLabel()
        self.lbl_crypto = QLabel()

        for lbl in [self.lbl_proj, self.lbl_auth, self.lbl_ldap, self.lbl_crypto]:
            lbl.setStyleSheet(
                "color: #7a9ab3; font-size: 11px; background: transparent;"
            )
            h_layout.addWidget(lbl)

        self.btn_edit_hdr = QPushButton("✏  EDIT")
        self.btn_edit_hdr.setObjectName("editHdrBtn")
        self.btn_edit_hdr.setFixedHeight(24)
        self.btn_edit_hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit_hdr.setToolTip("Edit project security parameters")
        self.btn_edit_hdr.clicked.connect(self._on_edit_header)
        self.btn_edit_hdr.setStyleSheet("""
            QPushButton#editHdrBtn {
                background: transparent; color: #6ccff6;
                border: 1px solid #1e3d5a; border-radius: 4px;
                padding: 0 8px; font-size: 10px; font-weight: 700;
            }
            QPushButton#editHdrBtn:hover {
                background: rgba(108, 207, 246, 0.1);
                border: 1px solid #6ccff6; color: #9fe7ff;
            }
        """)
        h_layout.addWidget(self.btn_edit_hdr)

        self.header_frame.mouseDoubleClickEvent = lambda e: self._on_edit_header()

        self._refresh_header_display()
        return self.header_frame

    def _build_kpi_ribbon(self) -> QHBoxLayout:
        stat_ribbon = QHBoxLayout()
        stat_ribbon.setSpacing(12)

        self.kpi_total   = StatCard("REGISTERED ACCOUNTS", "0", "👥", self.PRIMARY_LIGHT)
        self.kpi_active  = StatCard("ACTIVE SESSIONS", "0", "✅", self.SUCCESS)
        self.kpi_qc      = StatCard("AUTHORIZED QC SIGNERS", "0", "🛡️", self.ACCENT)
        self.kpi_suspend = StatCard("SUSPENDED / LOCKED", "0", "🚫", self.ERROR)

        stat_ribbon.addWidget(self.kpi_total)
        stat_ribbon.addWidget(self.kpi_active)
        stat_ribbon.addWidget(self.kpi_qc)
        stat_ribbon.addWidget(self.kpi_suspend)
        return stat_ribbon

    def _build_filter_bar(self) -> QHBoxLayout:
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText(
            "🔍  Search by Username, Full Name, Email, Stamp ID, Role, Department...  (Ctrl+F)"
        )
        self.search_input.setObjectName("searchInput")
        self.search_input.textChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.search_input, 3)

        self.combo_role = QComboBox()
        self.combo_role.setObjectName("filterCombo")
        self.combo_role.setMinimumHeight(38)
        self.combo_role.addItem("All Roles", None)
        for key, label in SITE_ROLES:
            self.combo_role.addItem(label, key)
        self.combo_role.currentTextChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.combo_role, 1)

        self.combo_status = QComboBox()
        self.combo_status.setObjectName("filterCombo")
        self.combo_status.setMinimumHeight(38)
        self.combo_status.addItems(["All Statuses", "Active", "Suspended"])
        self.combo_status.currentTextChanged.connect(self._apply_filters)
        filter_bar.addWidget(self.combo_status, 1)

        self.chk_export_filtered = QCheckBox("Export Filtered")
        self.chk_export_filtered.setChecked(True)
        self.chk_export_filtered.setToolTip(
            "When checked, only rows matching the current filters are exported"
        )
        self.chk_export_filtered.setStyleSheet("""
            QCheckBox {
                color: #7a9ab3; font-size: 10px;
                spacing: 4px; background: transparent;
            }
            QCheckBox::indicator {
                width: 14px; height: 14px;
                border: 1px solid #1e3d5a; border-radius: 3px;
                background: #07101a;
            }
            QCheckBox::indicator:checked {
                background: #6ccff6; border: 1px solid #6ccff6;
            }
        """)
        filter_bar.addWidget(self.chk_export_filtered)

        btn_reset = QPushButton("↺  RESET")
        btn_reset.setObjectName("secondaryBtn")
        btn_reset.setMinimumHeight(38)
        btn_reset.setToolTip("Reset all filters")
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.clicked.connect(self._reset_filters)
        filter_bar.addWidget(btn_reset)

        return filter_bar

    def _build_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setObjectName("userTable")
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            "Username", "Full Name & Title", "Role",
            "Department", "QC Stamp ID", "Last Login", "Status",
        ])

        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        header = table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setSectionsClickable(True)
        header.setStretchLastSection(True)
        for col_idx in range(table.columnCount()):
            header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

        default_widths = [120, 220, 160, 160, 110, 130, 100]
        for col_idx, w in enumerate(default_widths):
            table.setColumnWidth(col_idx, w)

        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        table.setWordWrap(False)
        table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_context_menu)
        table.itemSelectionChanged.connect(self._on_user_selection)
        table.doubleClicked.connect(self._on_edit_user)
        return table

    def _build_inspector_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("inspectorCard")
        panel.setMinimumWidth(280)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: #07101a; width: 6px; border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #1e3d5a; border-radius: 3px; min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #6ccff6; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        head_lbl = QLabel("🔍   USER IDENTITY & PRIVILEGES")
        head_lbl.setObjectName("inspHead")
        layout.addWidget(head_lbl)

        div = QFrame()
        div.setObjectName("divider")
        div.setFixedHeight(1)
        layout.addWidget(div)

        self.insp_target = QLabel("Select a User")
        self.insp_target.setObjectName("inspTarget")
        self.insp_target.setWordWrap(True)
        layout.addWidget(self.insp_target)

        self.insp_sub = QLabel(
            "Select an account from the table to review electronic sign-off permissions, "
            "stamp validity, and credentials."
        )
        self.insp_sub.setObjectName("inspSub")
        self.insp_sub.setWordWrap(True)
        layout.addWidget(self.insp_sub)

        self.meta_frame = QFrame()
        self.meta_frame.setObjectName("metaFrame")
        m_layout = QVBoxLayout(self.meta_frame)
        m_layout.setContentsMargins(10, 8, 10, 8)
        m_layout.setSpacing(5)

        self.m_role   = QLabel()
        self.m_dept   = QLabel()
        self.m_email  = QLabel()
        self.m_stamp  = QLabel()
        self.m_create = QLabel()

        # Declarative spec for both populate and reset.
        self._meta_specs = [
            (self.m_role,   "Role"),
            (self.m_dept,   "Department"),
            (self.m_email,  "Email"),
            (self.m_stamp,  "Stamp ID"),
            (self.m_create, "Created"),
        ]

        for lbl, _ in self._meta_specs:
            lbl.setStyleSheet(
                "color: #dfeaf5; font-size: 11px; background: transparent;"
            )
            lbl.setWordWrap(True)
            m_layout.addWidget(lbl)

        layout.addWidget(self.meta_frame)

        perm_title = QLabel("⚡   AUTHORIZED SIGN-OFF SCOPE:")
        perm_title.setStyleSheet(
            "color: #9fe7ff; font-size: 9px; font-weight: 800; "
            "letter-spacing: 1px; margin-top: 4px; background: transparent;"
        )
        layout.addWidget(perm_title)

        self.lbl_perms = QLabel("—")
        self.lbl_perms.setWordWrap(True)
        self.lbl_perms.setStyleSheet("""
            color: #5cffaa; font-size: 10px;
            background: #07101a; border: 1px solid #142e47;
            border-radius: 6px; padding: 6px;
        """)
        layout.addWidget(self.lbl_perms)

        btn_row1 = QHBoxLayout()
        self.btn_edit = QPushButton("✏️  EDIT USER")
        self.btn_edit.setObjectName("secondaryBtn")
        self.btn_edit.setMinimumHeight(34)
        self.btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit.setEnabled(False)
        self.btn_edit.clicked.connect(self._on_edit_user)
        btn_row1.addWidget(self.btn_edit)

        self.btn_reset_pw = QPushButton("🔐  RESET PWD")
        self.btn_reset_pw.setObjectName("secondaryBtn")
        self.btn_reset_pw.setMinimumHeight(34)
        self.btn_reset_pw.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_pw.setEnabled(False)
        self.btn_reset_pw.clicked.connect(self._on_reset_password)
        btn_row1.addWidget(self.btn_reset_pw)
        layout.addLayout(btn_row1)

        self.btn_toggle_status = QPushButton("🚫  SUSPEND / ENABLE ACCOUNT")
        self.btn_toggle_status.setObjectName("secondaryBtn")
        self.btn_toggle_status.setMinimumHeight(34)
        self.btn_toggle_status.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_status.setEnabled(False)
        self.btn_toggle_status.clicked.connect(self._on_toggle_status)
        layout.addWidget(self.btn_toggle_status)

        layout.addStretch()

        self.btn_delete = QPushButton("🗑  DELETE ACCOUNT")
        self.btn_delete.setObjectName("btnDelete")
        self.btn_delete.setMinimumHeight(32)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._on_delete_user)
        layout.addWidget(self.btn_delete)

        scroll.setWidget(inner)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(scroll)
        return panel

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 2, 4, 0)

        self.lbl_count = QLabel("Showing 0 user accounts")
        self.lbl_count.setObjectName("footerLabel")
        footer.addWidget(self.lbl_count)

        footer.addStretch()

        self.lbl_timestamp = QLabel("")
        self.lbl_timestamp.setObjectName("footerLabel")
        footer.addWidget(self.lbl_timestamp)

        footer.addStretch()

        foot_tag = QLabel(
            "⚡  PipeAgent 5.0  •  Role-Based Access Control & Cryptographic Identity Engine"
        )
        foot_tag.setStyleSheet(
            "color: #3f6070; font-size: 10px; letter-spacing: 1px; background: transparent;"
        )
        footer.addWidget(foot_tag)
        return footer

    # ── Keyboard Shortcuts ────────────────────────────────────
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+N"), self, self._on_add_user)
        QShortcut(QKeySequence("Ctrl+E"), self, self._on_export_audit)
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        QShortcut(QKeySequence("F5"),     self, self._apply_filters)

        # Bind Delete to the table only, so typing Delete inside the search
        # field doesn't delete a user account.
        del_sc = QShortcut(
            QKeySequence("Delete"), self.table, self._on_delete_user
        )
        del_sc.setContext(Qt.ShortcutContext.WidgetShortcut)

    def _focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()

    # ── Context Menu ──────────────────────────────────────────
    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #0b1624; color: #eef6ff;
                border: 1px solid #1e3d5a; border-radius: 6px; padding: 4px;
            }
            QMenu::item { padding: 8px 24px 8px 12px; border-radius: 4px; }
            QMenu::item:selected { background: #14334f; color: #9fe7ff; }
            QMenu::item:disabled { color: #3a5060; }
            QMenu::separator { height: 1px; background: #1e3d5a; margin: 4px 8px; }
        """)

        selected = self._get_selected_user()
        is_admin = selected is not None and selected.get("username") == "admin"

        act_edit = menu.addAction("✏️  Edit Profile Details")
        act_edit.setEnabled(selected is not None)
        act_edit.triggered.connect(self._on_edit_user)

        act_reset = menu.addAction("🔐  Reset Password")
        act_reset.setEnabled(selected is not None)
        act_reset.triggered.connect(self._on_reset_password)

        act_toggle = menu.addAction("🚫  Suspend / Enable Account")
        act_toggle.setEnabled(selected is not None and not is_admin)
        act_toggle.triggered.connect(self._on_toggle_status)

        menu.addSeparator()

        act_new = menu.addAction("➕  Register New Account  (Ctrl+N)")
        act_new.triggered.connect(self._on_add_user)

        act_export = menu.addAction("📤  Export Access Audit  (Ctrl+E)")
        act_export.triggered.connect(self._on_export_audit)

        menu.addSeparator()

        act_delete = menu.addAction("🗑  Delete User Account")
        act_delete.setEnabled(selected is not None and not is_admin)
        act_delete.triggered.connect(self._on_delete_user)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ── Header Display ────────────────────────────────────────
    def _refresh_header_display(self):
        meta = self._project_security_meta
        self.lbl_proj.setText(
            f"<b>PROJECT:</b> <span style='color:#9fe7ff;'>{meta['project']}</span>"
        )
        self.lbl_auth.setText(
            f"<b>AUTH MODE:</b> <span style='color:#9fe7ff;'>{meta['auth_mode']}</span>"
        )
        self.lbl_ldap.setText(
            f"<b>LDAP SERVER:</b> <span style='color:#eef6ff;'>{meta['ldap_server']}</span>"
        )
        self.lbl_crypto.setText(
            f"<b>CRYPTOGRAPHY:</b> <span style='color:#7a9ab3;'>{meta['crypto']}</span>"
        )

    def _on_edit_header(self):
        modal = EditSecurityMetaDialog(self._project_security_meta, self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        self._project_security_meta.update(modal.get_data())
        self._refresh_header_display()
        QMessageBox.information(
            self, "✅ Security Protocols Saved",
            "LDAP project connection & signature protocols updated successfully.",
        )

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
                /* QSS does not support gradients in `border`. */
                border: 2px solid {self.PRIMARY};
                border-radius: 18px;
            }}
            QLabel#mainTitle {{
                color: {self.PRIMARY_LIGHT};
                font-size: 18px;
                font-weight: 900;
                letter-spacing: 2.5px;
                background: transparent;
            }}
            QLabel#subTitle {{
                color: {self.PRIMARY};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1.2px;
                background: transparent;
            }}
            QLabel#footerLabel {{
                color: #7a9ab3;
                font-size: 11px;
                background: transparent;
            }}
            QFrame#headerFrame {{
                background: #081422;
                border: 1px solid #142e47;
                border-radius: 8px;
            }}
            QFrame#headerFrame:hover {{ border: 1px solid #6ccff6; }}
            QFrame#divider {{
                background: rgba(108, 207, 246, 0.3);
                border: none;
            }}
            QLineEdit#searchInput {{
                background: {self.BG_INPUT};
                color: {self.TEXT_MAIN};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
            }}
            QLineEdit#searchInput:focus {{ border: 1px solid {self.PRIMARY}; }}
            QComboBox#filterCombo {{
                background: {self.BG_INPUT};
                color: {self.TEXT_MAIN};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 4px 12px;
                font-size: 12px;
            }}
            QComboBox#filterCombo:hover {{ border: 1px solid {self.PRIMARY}; }}
            QComboBox#filterCombo QAbstractItemView {{
                background: #07101a;
                color: {self.TEXT_MAIN};
                selection-background-color: #14334f;
                selection-color: {self.PRIMARY_LIGHT};
                border: 1px solid #1e3d5a;
            }}
            QPushButton#actionBtn {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2196d4,
                    stop:0.5 {self.ACCENT},
                    stop:1 #2196d4
                );
                color: #041827;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 1px;
            }}
            QPushButton#actionBtn:hover {{ background: {self.PRIMARY_LIGHT}; }}
            QPushButton#secondaryBtn {{
                background: {self.BG_PANEL};
                color: {self.PRIMARY_LIGHT};
                border: 1px solid #1e3d5a;
                border-radius: 8px;
                padding: 0 14px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
            QPushButton#secondaryBtn:hover {{
                background: #142a40;
                border: 1px solid {self.PRIMARY};
                color: {self.ACCENT};
            }}
            QPushButton#secondaryBtn:disabled {{
                background: #0a1420;
                color: #3a5060;
                border: 1px solid #0f1f30;
            }}
            QPushButton#closeBtn {{
                background: transparent;
                color: {self.TEXT_MUTED};
                border: none;
                border-radius: 15px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton#closeBtn:hover {{
                background: rgba(255, 107, 107, 0.2);
                color: {self.ERROR};
            }}
            QTableWidget#userTable {{
                background: #07111c;
                alternate-background-color: #091520;
                color: {self.TEXT_MAIN};
                border: 1px solid #142e47;
                border-radius: 10px;
                gridline-color: transparent;
                selection-background-color: #12334f;
                selection-color: {self.PRIMARY_LIGHT};
                font-size: 12px;
            }}
            QTableWidget#userTable::item {{
                padding: 7px 9px;
                border-bottom: 1px solid #0c1f30;
            }}
            QTableWidget#userTable::item:selected {{
                background: #133959;
                border-left: 2px solid {self.PRIMARY};
            }}
            QHeaderView::section {{
                background: #0c1c2e;
                color: {self.PRIMARY_LIGHT};
                font-weight: 800;
                font-size: 10px;
                letter-spacing: 1px;
                border: none;
                border-bottom: 2px solid #1c4466;
                border-right: 1px solid #142e47;
                padding: 8px 9px;
            }}
            QScrollBar:vertical {{
                background: #07101a; width: 10px;
                border-radius: 5px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: #1e3d5a; border-radius: 5px; min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {self.PRIMARY}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: #07101a; height: 10px;
                border-radius: 5px; margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: #1e3d5a; border-radius: 5px; min-width: 30px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: {self.PRIMARY}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            QFrame#inspectorCard {{
                background: #091726;
                border: 1px solid #183854;
                border-radius: 10px;
            }}
            QLabel#inspHead {{
                color: {self.PRIMARY_LIGHT};
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 1.5px;
                background: transparent;
            }}
            QLabel#inspTarget {{
                color: {self.ACCENT};
                font-size: 15px;
                font-weight: 800;
                background: transparent;
                font-family: Consolas, monospace;
            }}
            QLabel#inspSub {{
                color: {self.TEXT_MUTED};
                font-size: 11px;
                background: transparent;
            }}
            QFrame#metaFrame {{
                background: #06101c;
                border: 1px solid #10263b;
                border-radius: 8px;
            }}
            QPushButton#btnDelete {{
                background: transparent;
                color: #8faec5;
                border: 1px solid #1b354d;
                border-radius: 6px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton#btnDelete:hover {{
                color: {self.ERROR};
                border: 1px solid {self.ERROR};
                background: rgba(255, 107, 107, 0.1);
            }}
            QPushButton#btnDelete:disabled {{
                color: #3a5060; border: 1px solid #0f1f30;
            }}
            QSplitter::handle {{ background: #102538; border-radius: 2px; }}
            QSplitter::handle:hover {{ background: {self.PRIMARY}; }}
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

    def _update_timestamp(self):
        now = datetime.now().strftime("%Y-%m-%d  %H:%M")
        self.lbl_timestamp.setText(f"🕐 {now}")

    # ── Sort-safe selection helpers ───────────────────────────
    def _get_selected_user(self) -> Optional[Dict[str, Any]]:
        """
        Return the user stored on the selected row.
        Survives sorting because the dict lives on the item's UserRole.
        """
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _find_user_index(self, user_id: str) -> int:
        """Locate a user by stable id. Returns -1 if missing."""
        for idx, u in enumerate(self._users):
            if u.get("user_id") == user_id:
                return idx
        return -1

    def _reselect_by_user_id(self, user_id: str):
        for row_idx in range(self.table.rowCount()):
            item = self.table.item(row_idx, 0)
            if item is None:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("user_id") == user_id:
                self.table.selectRow(row_idx)
                return

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

    def keyPressEvent(self, event: QKeyEvent):  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._on_close()
        else:
            super().keyPressEvent(event)

    # ── Filtering ─────────────────────────────────────────────
    def _apply_filters(self):
        search = self.search_input.text().strip().lower()
        selected_role = self.combo_role.currentData()
        selected_status = self.combo_status.currentText()

        filtered = []
        for u in self._users:
            if search:
                haystack = " ".join([
                    u["username"], u["fullname"], u["email"],
                    u["stamp_id"], u["dept"], u["role"], role_label(u.get("role")),
                ]).lower()
                if search not in haystack:
                    continue

            if selected_role and canonical_role(u["role"]) != selected_role:
                continue

            if selected_status != "All Statuses" and u["status"] != selected_status:
                continue

            filtered.append(u)

        self._filtered_users = filtered
        self._populate_table()
        self._update_kpi()

    def _reset_filters(self):
        # Block signals so we refilter once.
        widgets = (self.search_input, self.combo_role, self.combo_status)
        for w in widgets:
            w.blockSignals(True)
        try:
            self.search_input.clear()
            self.combo_role.setCurrentIndex(0)
            self.combo_status.setCurrentIndex(0)
        finally:
            for w in widgets:
                w.blockSignals(False)
        self._apply_filters()

    def _populate_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for row_idx, u in enumerate(self._filtered_users):
            self.table.insertRow(row_idx)

            # Col 0 — carries the user dict via UserRole.
            item_u = QTableWidgetItem(u["username"])
            item_u.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            item_u.setForeground(QColor(self.PRIMARY_LIGHT))
            item_u.setData(Qt.ItemDataRole.UserRole, u)  # sort-safe link
            self.table.setItem(row_idx, 0, item_u)

            item_fn = QTableWidgetItem(u["fullname"])
            item_fn.setForeground(QColor(self.TEXT_MAIN))
            item_fn.setToolTip(u["fullname"])
            self.table.setItem(row_idx, 1, item_fn)

            item_role = QTableWidgetItem(role_label(u["role"]))
            item_role.setForeground(QColor(self.ACCENT))
            self.table.setItem(row_idx, 2, item_role)

            item_dept = QTableWidgetItem(u["dept"])
            item_dept.setForeground(QColor(self.TEXT_MUTED))
            self.table.setItem(row_idx, 3, item_dept)

            item_st = QTableWidgetItem(u["stamp_id"])
            item_st.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            item_st.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_st.setForeground(QColor("#ffd966"))
            self.table.setItem(row_idx, 4, item_st)

            item_ll = QTableWidgetItem(u["last_login"])
            item_ll.setFont(QFont("Consolas", 9))
            item_ll.setForeground(QColor("#708fa8"))
            self.table.setItem(row_idx, 5, item_ll)

            stat_str = u["status"]
            item_stat = QTableWidgetItem(f" ● {stat_str} ")
            item_stat.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item_stat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if stat_str == "Active":
                item_stat.setForeground(QColor(self.SUCCESS))
            else:
                item_stat.setForeground(QColor(self.ERROR))
            self.table.setItem(row_idx, 6, item_stat)

        self.table.setSortingEnabled(True)

        total = len(self._users)
        shown = len(self._filtered_users)
        if shown == total:
            self.lbl_count.setText(f"Showing all {total} user accounts")
        else:
            self.lbl_count.setText(
                f"Showing {shown} of {total} accounts (filtered)"
            )

        if self._filtered_users:
            self.table.selectRow(0)
        else:
            self._clear_inspector()

    def _update_kpi(self):
        total   = len(self._users)
        active  = sum(1 for u in self._users if u["status"] == "Active")
        qc_auth = sum(
            1 for u in self._users
            if u.get("perms", {}).get("wjcs", False)
            or u.get("perms", {}).get("ndt", False)
        )
        suspend = sum(1 for u in self._users if u["status"] == "Suspended")

        self.kpi_total.update_value(str(total))
        self.kpi_active.update_value(str(active))
        self.kpi_qc.update_value(str(qc_auth))
        self.kpi_suspend.update_value(str(suspend))

    # ── Table Selection → Inspector ───────────────────────────
    def _on_user_selection(self):
        u = self._get_selected_user()
        if u is None:
            self._clear_inspector()
            return

        self.insp_target.setText(f"{u['fullname']} ({u['username']})")
        self.insp_sub.setText(
            f"Department: {u['dept']} • Stamp: {u['stamp_id']}"
        )

        self.m_role.setText(f"<b>Role:</b> {role_label(u['role'])}")
        self.m_dept.setText(f"<b>Department:</b> {u['dept']}")
        self.m_email.setText(f"<b>Email:</b> {u['email']}")
        self.m_stamp.setText(f"<b>Stamp ID:</b> {u['stamp_id']}")
        self.m_create.setText(
            f"<b>Created:</b> {u.get('created_date', '2024-01-01')}"
        )

        perms = u.get("perms", {})
        p_list = []
        if perms.get("wjcs"): p_list.append("✓ WJCS Weld Approval")
        if perms.get("ndt"):  p_list.append("✓ NDT Record Sign-off")
        if perms.get("dcc"):  p_list.append("✓ IFC Revision Control")
        if perms.get("mrir"): p_list.append("✓ MRIR Material Clearance")
        if perms.get("hydro"): p_list.append("✓ Hydrotest Dossier Sign-off")

        self.lbl_perms.setText(
            "<br>".join(p_list) if p_list
            else "No active digital sign-off privileges"
        )

        is_admin = u["username"] == "admin"
        self.btn_edit.setEnabled(True)
        self.btn_reset_pw.setEnabled(True)
        self.btn_toggle_status.setEnabled(not is_admin)
        self.btn_delete.setEnabled(not is_admin)

    def _clear_inspector(self):
        self.insp_target.setText("No User Selected")
        self.insp_sub.setText(
            "Select an account from the table to review electronic sign-off "
            "permissions, stamp validity, and credentials."
        )
        # Reset driven by the declared spec — no string parsing.
        for lbl, title in self._meta_specs:
            lbl.setText(f"<b>{title}:</b> —")

        self.lbl_perms.setText("—")

        self.btn_edit.setEnabled(False)
        self.btn_reset_pw.setEnabled(False)
        self.btn_toggle_status.setEnabled(False)
        self.btn_delete.setEnabled(False)

    # ── User Actions ──────────────────────────────────────────
    def _on_add_user(self):
        existing_usernames = [u["username"] for u in self._users]
        modal = AddEditUserDialog(
            user_data=None,
            existing_usernames=existing_usernames,
            parent=self,
        )
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        new_u = modal.get_data()
        if self.db is not None:
            try:
                created = self.db.create_user(
                    username=new_u["username"],
                    password=new_u.get("password") or "ChangeMe1!",
                    role=canonical_role(new_u.get("role")),
                    full_name=new_u.get("fullname") or "",
                    email=new_u.get("email") or None,
                    department=new_u.get("dept") or "",
                    employee_id=_employee_id(new_u.get("stamp_id")),
                    is_active=new_u.get("status", "Active") == "Active",
                )
                new_u = self._user_to_row(created)
            except Exception as exc:
                QMessageBox.critical(self, "User", str(exc))
                return
        self._users.insert(0, new_u)
        self._apply_filters()
        self._reselect_by_user_id(new_u["user_id"])

    def _on_edit_user(self):
        selected = self._get_selected_user()
        if selected is None:
            QMessageBox.warning(
                self, "Selection Required",
                "Please select a user to edit."
            )
            return

        idx = self._find_user_index(selected.get("user_id", ""))
        if idx < 0:
            return

        modal = AddEditUserDialog(user_data=selected, parent=self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        updated_data = modal.get_data()
        if self.db is not None:
            try:
                pk = int(selected.get("pk") or selected.get("user_id"))
                with self.db.session_scope() as session:
                    user = session.get(User, pk)
                    if user:
                        user.full_name = updated_data.get("fullname") or user.full_name
                        user.email = updated_data.get("email") or user.email
                        user.role = canonical_role(updated_data.get("role"))
                        user.department = updated_data.get("dept") or ""
                        user.employee_id = _employee_id(updated_data.get("stamp_id"))
                        user.is_active = updated_data.get("status", "Active") == "Active"
                        session.flush()
                        updated_data = self._user_to_row(user)
            except Exception as exc:
                QMessageBox.critical(self, "User", str(exc))
                return
        self._users[idx].update(updated_data)

        target_id = self._users[idx].get("user_id", "")
        self._apply_filters()
        self._reselect_by_user_id(target_id)

    def _on_reset_password(self):
        selected = self._get_selected_user()
        if selected is None:
            return

        modal = ResetPasswordDialog(username=selected["username"], parent=self)
        if modal.exec() == QDialog.DialogCode.Accepted:
            password = modal.get_password()
            if self.db is not None and password:
                try:
                    pk = int(selected.get("pk") or selected.get("user_id"))
                    self.db.update_user_password_hash(
                        pk, self.db._hash_password(password)
                    )
                except Exception as exc:
                    QMessageBox.critical(self, "Password", str(exc))
                    return
            QMessageBox.information(
                self, "✅ Password Reset",
                f"Password for user <b>{selected['username']}</b> "
                f"has been successfully updated."
            )

    def _on_toggle_status(self):
        selected = self._get_selected_user()
        if selected is None:
            return

        if selected["username"] == "admin":
            QMessageBox.warning(
                self, "Security Rule",
                "Cannot suspend the primary administrator account."
            )
            return

        idx = self._find_user_index(selected.get("user_id", ""))
        if idx < 0:
            return

        new_status = "Suspended" if selected["status"] == "Active" else "Active"
        if self.db is not None:
            try:
                pk = int(selected.get("pk") or selected.get("user_id"))
                with self.db.session_scope() as session:
                    user = session.get(User, pk)
                    if user:
                        user.is_active = new_status == "Active"
            except Exception as exc:
                QMessageBox.critical(self, "User", str(exc))
                return
        self._users[idx]["status"] = new_status

        target_id = self._users[idx].get("user_id", "")
        self._apply_filters()
        self._reselect_by_user_id(target_id)

    def _on_delete_user(self):
        selected = self._get_selected_user()
        if selected is None:
            return

        if selected["username"] == "admin":
            QMessageBox.warning(
                self, "Security Rule",
                "Cannot delete the primary administrator account."
            )
            return

        reply = QMessageBox.warning(
            self, "⚠ Confirm Delete",
            f"Are you sure you want to permanently delete account "
            f"<b>{selected['username']}</b>?\n\n"
            f"All digital signature logs will preserve history, but the user "
            f"will lose system access immediately.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        idx = self._find_user_index(selected.get("user_id", ""))
        if idx < 0:
            return
        if self.db is not None:
            try:
                pk = int(selected.get("pk") or selected.get("user_id"))
                with self.db.session_scope() as session:
                    user = session.get(User, pk)
                    if user:
                        session.delete(user)
            except Exception as exc:
                QMessageBox.critical(self, "User", str(exc))
                return
        self._users.pop(idx)
        self._apply_filters()

    # ── Export Audit ──────────────────────────────────────────
    def _on_export_audit(self):
        if self.chk_export_filtered.isChecked():
            export_users = self._filtered_users
            label = "filtered"
        else:
            export_users = self._users
            label = "all"

        if not export_users:
            QMessageBox.warning(
                self, "No Data",
                "No user records to export. Adjust your filters."
            )
            return

        default_name = (
            f"User_Security_Access_Audit_"
            f"{datetime.today().strftime('%Y%m%d')}.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Security Audit & User Register",
            default_name, "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["═══ PIPEAGENT ACCESS AUDIT DOSSIER OVERVIEW ═══"])
                writer.writerow(["Project Scope", self._project_security_meta["project"]])
                writer.writerow(["Authentication", self._project_security_meta["auth_mode"]])
                writer.writerow(["LDAP Endpoint", self._project_security_meta["ldap_server"]])
                writer.writerow(["Stamp Encryption", self._project_security_meta["crypto"]])
                writer.writerow(["SO Contact", self._project_security_meta["so_contact"]])
                writer.writerow([])
                writer.writerow(["═══ SECURITY AUDIT & USER REGISTER ═══"])
                writer.writerow([
                    "Username", "Full Name", "Email", "Role",
                    "Department", "Stamp ID", "Last Login",
                    "Created Date", "Status",
                ])
                for u in export_users:
                    writer.writerow([
                        u["username"], u["fullname"], u["email"], u["role"],
                        u["dept"], u["stamp_id"], u["last_login"],
                        u.get("created_date", ""), u["status"],
                    ])

            QMessageBox.information(
                self, "✅ Audit Dossier Exported",
                f"Successfully exported {len(export_users)} {label} records to:\n\n{path}",
            )
        except PermissionError:
            QMessageBox.critical(
                self, "Export Error",
                "Permission denied. The file may be open in another application.\n"
                "Please close it and try again.",
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Export Error",
                f"Could not export audit register: {e}",
            )

    # ── Graceful close ────────────────────────────────────────
    def _cleanup(self):
        """Stop every timer we own. Safe to call twice."""
        if self._is_closed:
            return
        self._is_closed = True

        if hasattr(self, "_particles"):
            try:
                self._particles.stop()
            except RuntimeError:
                pass

        if self._ts_timer is not None:
            self._ts_timer.stop()
            self._ts_timer = None

    def _on_close(self):
        self._cleanup()
        if self.isVisible():
            self.accept()

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

    dialog = UserAdminDialog()
    dialog.show()
    dialog.exec()

    sys.exit(0)