# -*- coding: utf-8 -*-
# ui/tabs/value_and_plans_tab.py – PipeAgent 5.3.0
# Commercial Value Realization, Tier Architecture & Operational ROI Engine
from __future__ import annotations

import csv
import logging
import datetime
from datetime import timezone
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QTextEdit, QMessageBox, QFrame,
    QProgressBar, QFileDialog, QApplication, QAbstractItemView,
    QSplitter,
)
from PyQt6.QtGui import (
    QColor, QFont, QBrush, QCursor, QDesktopServices,
)

from db.models import Project
from services.product_commercial import (
    PLANS, COMMERCIAL_PRINCIPLES, ValueEngine, plan_for_license_info,
)
from services.license import get_license_info

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  UTIL
# ─────────────────────────────────────────────
def _utcnow():
    """Naive UTC — replacement for deprecated datetime.utcnow()."""
    return datetime.datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────
#  FEATURE BADGES
# ─────────────────────────────────────────────
FEATURE_BADGES = {
    "Included":   {"bg": "#dcfce7", "fg": "#166534", "icon": "✅"},
    "Add-on":     {"bg": "#fef3c7", "fg": "#92400e", "icon": "🧩"},
    "Optional":   {"bg": "#e0f2fe", "fg": "#075985", "icon": "⚙️"},
    "Enterprise": {"bg": "#f3e8ff", "fg": "#6b21a8", "icon": "🏢"},
}
DEFAULT_BADGE = {"bg": "#f1f5f9", "fg": "#475569", "icon": "•"}


# ─────────────────────────────────────────────
#  STYLESHEET
# ─────────────────────────────────────────────
VALUE_TAB_STYLESHEET = """
    QWidget#valueAndPlansTab {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 #f8fafc, stop:1 #eef2f7);
    }
    QFrame#headerCard {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #0b6f8a, stop:1 #13a6b8);
        border-radius: 12px; padding: 14px;
    }
    QLabel#mainTitle {
        color: #ffffff; font-size: 22px; font-weight: 800;
        font-family: 'Segoe UI', sans-serif;
    }
    QLabel#subTitle { color: #d9f7fb; font-size: 12px; }
    QFrame#tierCard {
        background: white; border: 2px solid #cbd5e1;
        border-left: 6px solid #0f9fb5;
        border-radius: 8px; padding: 10px 14px;
    }
    QFrame#kpiCard {
        background: white; border: 1px solid #cbd5e1;
        border-radius: 8px; padding: 10px;
    }
    QLabel#kpiTitle {
        font-size: 11px; font-weight: 700; color: #64748b;
        text-transform: uppercase;
    }
    QLabel#kpiValue { font-size: 20px; font-weight: 800; color: #0f172a; }
    QGroupBox {
        font-size: 12px; font-weight: 800; color: #1e293b;
        border: 2px solid #cbd5e1; border-radius: 8px;
        margin-top: 10px; padding-top: 14px; background: white;
    }
    QGroupBox::title {
        subcontrol-origin: margin; subcontrol-position: top left;
        left: 10px; padding: 0 4px; background: white;
    }
    QTableWidget {
        background: white; border: 1px solid #cbd5e1;
        border-radius: 6px; gridline-color: #f1f5f9; font-size: 12px;
    }
    QTableWidget::item:selected { background: #e0f2fe; color: #0369a1; }
    QHeaderView::section {
        background: #f8fafc; color: #334155;
        font-weight: 700; font-size: 11px; padding: 8px;
        border: none; border-bottom: 2px solid #cbd5e1;
        border-right: 1px solid #f1f5f9;
    }
    QPushButton#primaryBtn {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #0f9fb5, stop:1 #087f98);
        color: white; border: none; padding: 8px 16px;
        border-radius: 6px; font-weight: 700;
    }
    QPushButton#primaryBtn:hover { background: #06697d; }
    QPushButton#secondaryBtn {
        background: white; color: #334155; border: 1px solid #cbd5e1;
        padding: 7px 14px; border-radius: 6px; font-weight: 600;
    }
    QPushButton#secondaryBtn:hover {
        background: #f8fafc; border-color: #0f9fb5; color: #0f9fb5;
    }
    QLineEdit, QComboBox, QTextEdit {
        padding: 6px 10px; border: 1px solid #cbd5e1;
        border-radius: 6px; font-size: 12px;
    }
"""


# ─────────────────────────────────────────────
#  BACKGROUND WORKER
# ─────────────────────────────────────────────
class ValueCalculationWorker(QThread):
    """
    Background worker that computes commercial / ROI indicators.

    Runs `ValueEngine.calculate(project_id)` off the UI thread
    to prevent freezes on large projects.
    """

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, engine: ValueEngine, project_id: int):
        super().__init__()
        self.engine = engine
        self.project_id = project_id

    def run(self):
        try:
            results = self.engine.calculate(self.project_id)
            self.finished.emit(results)
        except Exception as e:
            logger.exception("Value engine background computation failed")
            self.error.emit(str(e))


# ─────────────────────────────────────────────
#  FINANCIAL KPI CARD
# ─────────────────────────────────────────────
class FinancialKPICard(QFrame):
    def __init__(self, title: str, icon: str, color: str = "#0f9fb5"):
        super().__init__()
        self.setObjectName("kpiCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        top_lay = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"font-size: 18px; color: {color};")
        top_lay.addWidget(icon_lbl)
        top_lay.addStretch()

        self.val_lbl = QLabel("—")
        self.val_lbl.setObjectName("kpiValue")
        top_lay.addWidget(self.val_lbl)
        layout.addLayout(top_lay)

        t_lbl = QLabel(title)
        t_lbl.setObjectName("kpiTitle")
        layout.addWidget(t_lbl)

    def set_value(self, text: str, highlight: Optional[str] = None):
        self.val_lbl.setText(str(text))
        if highlight == "green":
            self.val_lbl.setStyleSheet(
                "color: #166534; font-size: 20px; font-weight: 800;"
            )
        elif highlight == "blue":
            self.val_lbl.setStyleSheet(
                "color: #0369a1; font-size: 20px; font-weight: 800;"
            )
        elif highlight == "amber":
            self.val_lbl.setStyleSheet(
                "color: #92400e; font-size: 20px; font-weight: 800;"
            )
        elif highlight == "red":
            self.val_lbl.setStyleSheet(
                "color: #991b1b; font-size: 20px; font-weight: 800;"
            )
        else:
            self.val_lbl.setStyleSheet(
                "color: #0f172a; font-size: 20px; font-weight: 800;"
            )


# ─────────────────────────────────────────────
#  MAIN TAB
# ─────────────────────────────────────────────
class ValueAndPlansTab(QWidget):
    """
    Commercial transparency, pricing plans, and engineering-evidence-based value.
    """

    def __init__(self, db, session):
        super().__init__()
        self.setObjectName("valueAndPlansTab")
        self.db = db
        self.session = session
        self.engine = ValueEngine(db)
        self._calc_worker: Optional[ValueCalculationWorker] = None
        self._cached_value_data: Optional[dict] = None

        self._build()
        self.setStyleSheet(VALUE_TAB_STYLESHEET)
        self.refresh()

    # ── UI BUILD ─────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # ── Header ───────────────────────────────────────────
        header_card = QFrame()
        header_card.setObjectName("headerCard")
        hdr_lay = QHBoxLayout(header_card)
        hdr_lay.setContentsMargins(14, 10, 14, 10)

        title_v = QVBoxLayout()
        t = QLabel("💰 PipeAgent Value Engine & Commercial Architecture")
        t.setObjectName("mainTitle")

        tagline = QLabel(
            "Know What's Next. Control What Matters. "
            "Piping Execution Operating System."
        )
        tagline.setStyleSheet(
            "color: #93c5fd; font-size: 13px; font-weight: 700;"
        )

        s = QLabel(
            "Evidence-based ROI, rework prevention analysis, bottleneck "
            "mitigation savings, and commercial tier overview."
        )
        s.setObjectName("subTitle")

        title_v.addWidget(t)
        title_v.addWidget(tagline)
        title_v.addWidget(s)
        hdr_lay.addLayout(title_v, 1)

        proj_box = QHBoxLayout()
        lbl_p = QLabel("Project:")
        lbl_p.setStyleSheet("color: white; font-weight: bold;")
        proj_box.addWidget(lbl_p)

        self.project = QComboBox()
        self.project.setMinimumWidth(220)
        self.project.currentIndexChanged.connect(self.refresh_value)
        proj_box.addWidget(self.project)

        self.btn_export_html = QPushButton("📂 Executive Report")
        self.btn_export_html.setObjectName("primaryBtn")
        self.btn_export_html.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.btn_export_html.clicked.connect(self.export_report)
        proj_box.addWidget(self.btn_export_html)

        self.btn_export_csv = QPushButton("📥 Export ROI CSV")
        self.btn_export_csv.setObjectName("secondaryBtn")
        self.btn_export_csv.clicked.connect(self.export_csv_summary)
        proj_box.addWidget(self.btn_export_csv)
        hdr_lay.addLayout(proj_box)

        root.addWidget(header_card)

        # ── Progress bar ─────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        # ── Active Tier banner ───────────────────────────────
        self.tier_box = QFrame()
        self.tier_box.setObjectName("tierCard")
        tier_lay = QHBoxLayout(self.tier_box)
        tier_lay.setContentsMargins(12, 8, 12, 8)

        tier_icon = QLabel("🏢")
        tier_icon.setStyleSheet("font-size: 26px; color: #0f9fb5;")
        tier_lay.addWidget(tier_icon)

        tier_text_v = QVBoxLayout()
        self.plan_title_lbl = QLabel("Commercial Tier Loading...")
        self.plan_title_lbl.setStyleSheet(
            "font-size: 16px; font-weight: 800; color: #0b5b78;"
        )
        self.plan_desc_lbl = QLabel(
            "Platform subscription & enterprise licensing terms."
        )
        self.plan_desc_lbl.setStyleSheet(
            "color: #475569; font-size: 12px;"
        )
        tier_text_v.addWidget(self.plan_title_lbl)
        tier_text_v.addWidget(self.plan_desc_lbl)
        tier_lay.addLayout(tier_text_v, 1)

        tier_badge = QLabel("Active License")
        tier_badge.setStyleSheet(
            "background: #dcfce7; color: #166534; "
            "font-weight: bold; padding: 4px 10px; border-radius: 6px;"
        )
        tier_lay.addWidget(tier_badge)
        root.addWidget(self.tier_box)

        # ── KPI Grid ─────────────────────────────────────────
        kpi_grid = QHBoxLayout()
        kpi_grid.setSpacing(8)

        self.card_total_value = FinancialKPICard(
            "Indicative ROI Value", "💎", "#10b981"
        )
        self.card_admin_eff = FinancialKPICard(
            "Admin Hours Saved", "⏱️", "#0f9fb5"
        )
        self.card_rework_opp = FinancialKPICard(
            "Rework Avoidance", "🛡️", "#8b5cf6"
        )
        self.card_constraint = FinancialKPICard(
            "Bottleneck Unlocking", "🚀", "#0ea5e9"
        )
        self.card_data_quality = FinancialKPICard(
            "Audit Data Quality", "📊", "#f59e0b"
        )

        for card in (self.card_total_value, self.card_admin_eff,
                     self.card_rework_opp, self.card_constraint,
                     self.card_data_quality):
            kpi_grid.addWidget(card)
        root.addLayout(kpi_grid)

        # ── Splitter with plans table + evidence ─────────────
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(8)

        # Plans table
        plans_box = QGroupBox(
            "📋 PIPEAGENT COMMERCIAL TIER ARCHITECTURE & MATRIX"
        )
        plans_lay = QVBoxLayout(plans_box)
        plans_lay.setContentsMargins(8, 12, 8, 8)

        self.plan_table = QTableWidget(0, 7)
        self.plan_table.setHorizontalHeaderLabels([
            "Commercial Plan", "Target Scope / Audience",
            "Field Mobile Ops", "Predictive Intelligence",
            "Digital Turnover", "Enterprise Integrations",
            "Multi-Project & SSO",
        ])
        self._setup_table_style(self.plan_table)
        plans_lay.addWidget(self.plan_table)
        splitter.addWidget(plans_box)

        # Bottom: Evidence + Principles
        bottom_frame = QFrame()
        bottom_lay = QHBoxLayout(bottom_frame)
        bottom_lay.setContentsMargins(0, 0, 0, 0)
        bottom_lay.setSpacing(8)

        evidence_box = QGroupBox(
            "🔍 OPERATIONAL EVIDENCE & VALUE ATTRIBUTION"
        )
        ev_lay = QVBoxLayout(evidence_box)
        ev_lay.setContentsMargins(8, 12, 8, 8)

        self.evidence = QTextEdit()
        self.evidence.setReadOnly(True)
        self.evidence.setStyleSheet(
            "background: #f8fafc; border: 1px solid #cbd5e1; "
            "border-radius: 6px; padding: 8px; font-size: 12px;"
        )
        ev_lay.addWidget(self.evidence)
        bottom_lay.addWidget(evidence_box, 3)

        principles_box = QGroupBox(
            "📜 COMMERCIAL GOVERNANCE PRINCIPLES"
        )
        pr_lay = QVBoxLayout(principles_box)
        pr_lay.setContentsMargins(8, 12, 8, 8)

        self.principles_lbl = QLabel(
            "<b>Piping Execution OS Principles:</b><br>• "
            + "<br>• ".join(COMMERCIAL_PRINCIPLES)
        )
        self.principles_lbl.setWordWrap(True)
        self.principles_lbl.setStyleSheet(
            "background: #f1f5f9; border: 1px solid #cbd5e1; "
            "border-radius: 6px; padding: 10px; color: #334155; "
            "font-size: 11px;"
        )
        pr_lay.addWidget(self.principles_lbl)
        bottom_lay.addWidget(principles_box, 2)

        splitter.addWidget(bottom_frame)
        splitter.setSizes([260, 220])
        root.addWidget(splitter, 1)

    def _setup_table_style(self, table: QTableWidget):
        table.setAlternatingRowColors(True)
        # ✅ FIXED: use QAbstractItemView enums
        table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(False)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

    def _apply_badge_to_cell(self, item: QTableWidgetItem, text: str):
        badge = FEATURE_BADGES.get(text, DEFAULT_BADGE)
        item.setText(f"{badge['icon']} {text}")
        item.setBackground(QBrush(QColor(badge["bg"])))
        item.setForeground(QBrush(QColor(badge["fg"])))
        f = item.font()
        f.setBold(True)
        item.setFont(f)

    # ══════════════════════════════════════════
    #  REFRESH
    # ══════════════════════════════════════════
    def refresh(self):
        """Reload license info, plan matrix, and project data."""
        # ── Load license info ────────────────────────────────
        try:
            lic = plan_for_license_info(get_license_info(self.db))
            self.plan_title_lbl.setText(
                f"{lic.name} Tier &middot; {lic.billing}"
            )
            self.plan_desc_lbl.setText(lic.summary)
        except Exception as e:
            logger.warning(f"Could not load license info: {e}")

        # ── Populate plan matrix ─────────────────────────────
        self._populate_plan_matrix()

        # ── Reload projects dropdown ─────────────────────────
        current = (
            self.project.currentData()
            if hasattr(self, "project") else None
        )
        self.project.blockSignals(True)
        self.project.clear()
        self.project.addItem("Select Project", None)

        try:
            with self.db.session_scope() as s:
                for p in (
                    s.query(Project)
                    .order_by(Project.project_code)
                    .all()
                ):
                    self.project.addItem(
                        f"{p.project_code} — {p.title}", p.id
                    )
        except Exception:
            logger.exception(
                "Failed to load projects in ValueAndPlansTab"
            )

        if current is not None:
            idx = self.project.findData(current)
            if idx >= 0:
                self.project.setCurrentIndex(idx)

        self.project.blockSignals(False)
        self.refresh_value()

    def _populate_plan_matrix(self):
        self.plan_table.setRowCount(0)
        for r, p in enumerate(PLANS.values()):
            self.plan_table.insertRow(r)

            p_name_item = QTableWidgetItem(p.name)
            p_name_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            self.plan_table.setItem(r, 0, p_name_item)

            self.plan_table.setItem(r, 1, QTableWidgetItem(p.audience))

            features = [
                "Included" if p.field_ops else "Add-on",
                "Included" if p.intelligence else "Add-on",
                "Included" if p.turnover else "Add-on",
                "Included" if p.integrations else "Optional",
                "Included" if p.sso else "Enterprise",
            ]

            for c, val in enumerate(features, start=2):
                item = QTableWidgetItem(val)
                self._apply_badge_to_cell(item, val)
                self.plan_table.setItem(r, c, item)

    # ══════════════════════════════════════════
    #  VALUE CALCULATION
    # ══════════════════════════════════════════
    def refresh_value(self):
        pid = self.project.currentData()
        if not pid:
            self._clear_cards()
            self.evidence.setHtml(
                "<b>Select a project</b> to initiate the evidence-based "
                "Value Realization simulation."
            )
            return

        # ✅ FIXED: cleanup previous thread before starting a new one
        self._stop_calc_worker()

        self.progress_bar.setVisible(True)
        self.btn_export_html.setEnabled(False)
        self.btn_export_csv.setEnabled(False)

        self._calc_worker = ValueCalculationWorker(self.engine, pid)
        self._calc_worker.finished.connect(self._on_value_calc_success)
        self._calc_worker.error.connect(self._on_value_calc_failed)
        self._calc_worker.start()

    def _stop_calc_worker(self):
        """Gracefully stop any in-flight calc worker."""
        if self._calc_worker is None:
            return
        try:
            if self._calc_worker.isRunning():
                self._calc_worker.requestInterruption()
                self._calc_worker.wait(2000)
            self._calc_worker.deleteLater()
        except Exception:
            logger.warning(
                "Value calc worker stop failed", exc_info=True
            )
        self._calc_worker = None

    def _on_value_calc_success(self, d: dict):
        self.progress_bar.setVisible(False)
        self.btn_export_html.setEnabled(True)
        self.btn_export_csv.setEnabled(True)
        self._cached_value_data = d

        o = d.get("opportunity_value", {})
        ind = d.get("operational_indicators", {})

        tot_val = o.get("total_indicated_value", 0.0)
        admin_eff = o.get("administrative_efficiency", 0.0)
        rework_opp = o.get("rework_opportunity", 0.0)
        const_opp = o.get("constraint_opportunity", 0.0)
        quality_score = ind.get("prediction_data_quality", 0)

        self.card_total_value.set_value(
            f"${tot_val:,.0f}", highlight="green"
        )
        self.card_admin_eff.set_value(f"${admin_eff:,.0f}")
        self.card_rework_opp.set_value(
            f"${rework_opp:,.0f}", highlight="blue"
        )
        self.card_constraint.set_value(f"${const_opp:,.0f}")

        if quality_score >= 80:
            q_highlight = "green"
        elif quality_score >= 50:
            q_highlight = "amber"
        else:
            q_highlight = "red"
        self.card_data_quality.set_value(
            f"{quality_score}/100", highlight=q_highlight
        )

        evidence_html = f"""
            <div style='line-height: 1.5;'>
                <b>📊 Realized Diagnostic Indicators:</b><br>
                • <b>Repairs Avoided / Logged:</b>
                <span style='color:#dc2626; font-weight:bold;'>
                {ind.get('repair_events', 0)}</span> events<br>
                • <b>Tracked Quality Drawings & Specs:</b>
                {ind.get('documents_tracked', 0)} documents<br>
                • <b>Affected / Blocked Critical Path Nodes:</b>
                {ind.get('blocked_or_affected_nodes', 0)} nodes<br>
                • <b>Open Schedule / Resource Impacts:</b>
                {ind.get('open_impacts', 0)} active risks<br>
                <br><b>🛡️ Deterministic Guardrail & Governance:</b><br>
                <i>{d.get('disclaimer', 'Value models are auditable and derived from historical field data.')}</i>
            </div>
        """
        self.evidence.setHtml(evidence_html)

        # ✅ FIXED: release worker resources
        if self._calc_worker is not None:
            self._calc_worker.deleteLater()
            self._calc_worker = None

    def _on_value_calc_failed(self, err_msg: str):
        self.progress_bar.setVisible(False)
        self.btn_export_html.setEnabled(True)
        self.btn_export_csv.setEnabled(True)
        self.evidence.setPlainText(
            f"Value calculation unavailable: {err_msg}"
        )

        # ✅ FIXED: release worker resources
        if self._calc_worker is not None:
            self._calc_worker.deleteLater()
            self._calc_worker = None

    def _clear_cards(self):
        for card in (
            self.card_total_value, self.card_admin_eff,
            self.card_rework_opp, self.card_constraint,
            self.card_data_quality,
        ):
            card.set_value("—")

    # ══════════════════════════════════════════
    #  EXPORT HTML
    # ══════════════════════════════════════════
    def export_report(self):
        pid = self.project.currentData()
        if not pid:
            QMessageBox.information(
                self, "Project Required", "Select a project first."
            )
            return

        try:
            path = self.engine.export_html(pid)
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(Path(path).resolve()))
            )
            QMessageBox.information(
                self, "Executive Report Generated",
                f"Executive Value Report created and opened:\n{path}"
            )
        except Exception as e:
            logger.exception("Failed to export value HTML report")
            QMessageBox.critical(
                self, "Export Failed",
                f"Could not generate report:\n{e}"
            )

    # ══════════════════════════════════════════
    #  EXPORT CSV
    # ══════════════════════════════════════════
    def export_csv_summary(self):
        if not self._cached_value_data:
            QMessageBox.warning(
                self, "No Data",
                "Calculate project value first before exporting."
            )
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_code = self.project.currentText().split("—")[0].strip()
        default_name = (
            f"PipeAgent_ROI_Breakdown_{proj_code}_{timestamp}.csv"
        )

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Value Ledger CSV", default_name,
            "CSV Files (*.csv)",
        )
        if not filename:
            return

        try:
            with open(filename, mode="w", newline="",
                      encoding="utf-8-sig") as f:
                writer = csv.writer(f)

                writer.writerow([
                    "=== PIPEAGENT VALUE REALIZATION & ROI REPORT ==="
                ])
                writer.writerow(["Project", self.project.currentText()])
                writer.writerow([
                    "Date Generated",
                    datetime.datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                ])
                writer.writerow([])

                writer.writerow([
                    "Metric Category",
                    "Calculated Value ($ USD)",
                    "Methodology / Source",
                ])
                o = self._cached_value_data.get("opportunity_value", {})
                writer.writerow([
                    "Administrative Efficiency",
                    f"{o.get('administrative_efficiency', 0.0):.2f}",
                    "Hours saved in document control & manual reporting",
                ])
                writer.writerow([
                    "Rework Avoidance",
                    f"{o.get('rework_opportunity', 0.0):.2f}",
                    "Weld repair prevention & pre-test quality holds",
                ])
                writer.writerow([
                    "Constraint & Bottleneck Mitigation",
                    f"{o.get('constraint_opportunity', 0.0):.2f}",
                    "Work front idle time reduction & active dispatch",
                ])
                writer.writerow([
                    "TOTAL INDICATED VALUE",
                    f"{o.get('total_indicated_value', 0.0):.2f}",
                    "Aggregated operational value created",
                ])
                writer.writerow([])

                writer.writerow(["=== OPERATIONAL INDICATORS ==="])
                ind = self._cached_value_data.get(
                    "operational_indicators", {}
                )
                for k, v in ind.items():
                    writer.writerow([
                        k.replace("_", " ").title(), v,
                    ])

            QMessageBox.information(
                self, "Export Complete",
                f"Value realization ledger successfully saved to:\n"
                f"{filename}"
            )
        except Exception as e:
            logger.exception("Failed to export ROI CSV")
            QMessageBox.critical(
                self, "Export Error",
                f"Could not create CSV file:\n{e}"
            )

    # ══════════════════════════════════════════
    #  CLEANUP
    # ══════════════════════════════════════════
    def closeEvent(self, event):
        """Ensure the value calc worker is stopped before widget closes."""
        self._stop_calc_worker()
        super().closeEvent(event)