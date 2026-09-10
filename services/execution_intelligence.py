# -*- coding: utf-8 -*-
"""
services/execution_intelligence.py – PipeAgent
موتور هوش اجرایی و پایش پیشگیرانه شاخص‌های پیش‌نگر (Leading-Indicator Analytics Engine)
شامل: رادار گلوگاه‌های کارگاهی، تعادل صف NDT/جوشکاری بر مبنای اینچ-قطر،
مدل‌سازی چندبعدی ریسک پروژه، اولویت‌بندی اقدامات اصلاحی و شبیه‌ساز ظرفیت و سناریوهای What-If.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, and_, or_, desc, case
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from db.manager import DatabaseManager
from db.models import (
    Weld,
    NDTRecord,
    TestPackage,
    WorkFront,
    WorkAssignment,
    WeldReportDraft,
    FitupReportDraft,
    TurnoverDossier,
    PunchItem,
    NCRRecord,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Indicator Standards
# ──────────────────────────────────────────────

class HealthBand(str, Enum):
    EXCELLENT = "EXCELLENT"        # Implementation note.
    CONTROLLED = "CONTROLLED"      # Implementation note.
    WATCH = "WATCH"                # Implementation note.
    AT_RISK = "AT_RISK"            # Implementation note.
    CRITICAL = "CRITICAL"          # Implementation note.


class SignalCategory(str, Enum):
    DISPATCH = "DISPATCH"          # Implementation note.
    CONSTRAINT = "CONSTRAINT"      # Implementation note.
    SCHEDULE = "SCHEDULE"          # Implementation note.
    QUALITY = "QUALITY"            # Implementation note.
    NDT_FLOW = "NDT_FLOW"          # Implementation note.
    DOCUMENT = "DOCUMENT"          # Implementation note.
    COMPLETION = "COMPLETION"      # Implementation note.
    TURNOVER = "TURNOVER"          # Implementation note.


class SignalSeverity(str, Enum):
    CRITICAL = "CRITICAL"          # Implementation note.
    HIGH = "HIGH"                  # Implementation note.
    MEDIUM = "MEDIUM"              # Implementation note.
    LOW = "LOW"                    # Implementation note.


# ──────────────────────────────────────────────
#  Execution Intelligence Service
# ──────────────────────────────────────────────

class ExecutionIntelligence:
    """
    موتور محاسباتی پیشرفته هوش اجرایی و پایش زنده ریسک‌های ساخت و نصب پایپینگ
    """

    def __init__(self, db: DatabaseManager):
        self.db = db
    @staticmethod
    def what_if(ndt_queue: int, extra_shift_output: int, constraints: int, test_gates: int, recovery_days: int) -> Dict[str, Any]:
        """Transparent scenario calculation; not a schedule commitment."""
        return {
            "ndt_queue_after_extra_shift": max(0, int(extra_shift_output) - int(constraints) + int(recovery_days)),
            "constraint_dependency": int(constraints) > 0,
            "test_recovery_priority": int(test_gates) > 0 and int(recovery_days) > 0,
            "message": "Scenario only; not a schedule promise.",
        }


    # Implementation note.

    def analyze(self, project_id: int) -> Dict[str, Any]:
        """
        اسکن سریع و مستقیم دیتابیس با استفاده از توابع تجمعی SQL (بدون لود بیهوده رکوردها در RAM)
        و محاسبه شاخص‌های ترکیبی پیشرفت، کیفیت و موانع مسیر بحرانی.
        """
        today = date.today()

        with self.db.session_scope() as session:
            # Implementation note.
            weld_stats = session.query(
                func.count(Weld.id).label("total_welds"),
                func.sum(func.coalesce(Weld.dia_inch, 1.0)).label("total_dia_inch"),
                func.sum(case((Weld.status.in_(["WELDED", "WELDED_VT_PENDING", "VT_ACCEPTED", "NDT_REQUESTED", "NDT_CLEARED", "COMPLETED"]), func.coalesce(Weld.dia_inch, 1.0)), else_=0.0)).label("completed_dia_inch"),
                func.sum(case((Weld.status.in_(["WELDED", "WELDED_VT_PENDING", "NDT_REQUESTED"]), 1), else_=0)).label("awaiting_ndt_count"),
                func.sum(case((Weld.status.in_(["WELDED", "WELDED_VT_PENDING", "NDT_REQUESTED"]), func.coalesce(Weld.dia_inch, 1.0)), else_=0.0)).label("awaiting_ndt_dia_inch"),
                func.sum(case((getattr(Weld, "repair_count", 0) > 0, 1), else_=0)).label("repaired_welds_count"),
                func.sum(case((getattr(Weld, "repair_count", 0) > 0, func.coalesce(Weld.dia_inch, 1.0)), else_=0.0)).label("repaired_dia_inch"),
            ).filter(Weld.project_id == project_id).first()

            total_welds = weld_stats.total_welds or 0
            total_dia_inch = float(weld_stats.total_dia_inch or 0.0)
            completed_dia_inch = float(weld_stats.completed_dia_inch or 0.0)
            awaiting_ndt = weld_stats.awaiting_ndt_count or 0
            awaiting_ndt_dia_inch = float(weld_stats.awaiting_ndt_dia_inch or 0.0)
            repaired_welds = weld_stats.repaired_welds_count or 0
            repaired_dia_inch = float(weld_stats.repaired_dia_inch or 0.0)

            # Implementation note.
            ndt_rejected_count = session.query(func.count(NDTRecord.id)).join(
                Weld, NDTRecord.weld_id_fk == Weld.id
            ).filter(
                Weld.project_id == project_id,
                NDTRecord.verdict.in_(["REJ", "REJECTED", "FAIL", "RE_TEST"]),
            ).scalar() or 0

            # Implementation note.
            # Implementation note.
            assigned_front_ids = session.query(WorkAssignment.work_front_id).join(
                WorkFront, WorkAssignment.work_front_id == WorkFront.id
            ).filter(
                WorkFront.project_id == project_id,
                WorkAssignment.status == "Assigned",
            ).distinct().all()
            assigned_set = {r[0] for r in assigned_front_ids}

            fronts = session.query(WorkFront).filter(WorkFront.project_id == project_id).all()
            
            blocked_fronts = [f for f in fronts if f.status in ["Blocked", "Waiting"] or (getattr(f, "blocker", "") or "").strip()]
            overdue_fronts = [f for f in fronts if f.planned_finish and f.planned_finish < today and f.status != "Completed"]
            ready_fronts = [f for f in fronts if f.status in ["Ready", "Assigned", "In Progress"] and getattr(f, "readiness", "") == "Ready" and not (getattr(f, "blocker", "") or "").strip()]
            unassigned_ready = [f for f in ready_fronts if f.id not in assigned_set]

            # Implementation note.
            tp_stats = session.query(
                func.count(TestPackage.id).label("total_tps"),
                func.sum(case((TestPackage.status.in_(["Failed", "Re-test Required", "FAILED"]), 1), else_=0)).label("failed_tps"),
                func.sum(case((TestPackage.status.in_(["Ready for Test", "READY_FOR_TEST"]), 1), else_=0)).label("ready_tps"),
                func.sum(case((TestPackage.status.in_(["TEST_ACCEPTED", "CLOSED", "Dossier Closed"]), 1), else_=0)).label("tested_tps"),
            ).filter(TestPackage.project_id == project_id).first()

            failed_tests = tp_stats.failed_tps or 0
            ready_tests = tp_stats.ready_tps or 0

            # Implementation note.
            open_cat_a_punches = session.query(func.count(PunchItem.id)).filter(
                PunchItem.project_id == project_id,
                PunchItem.category == "A",
                PunchItem.status.notin_(["QC_CLEARED", "CLIENT_ACCEPTED", "CANCELLED"]),
            ).scalar() or 0

            # Implementation note.
            weld_drafts = session.query(func.count(WeldReportDraft.id)).filter(
                WeldReportDraft.project_id == project_id,
                WeldReportDraft.status != "Approved",
            ).scalar() or 0

            fitup_drafts = session.query(func.count(FitupReportDraft.id)).filter(
                FitupReportDraft.project_id == project_id,
                FitupReportDraft.status != "Approved",
            ).scalar() or 0

            # Implementation note.
            incomplete_dossiers = session.query(TurnoverDossier).filter(
                TurnoverDossier.project_id == project_id,
                TurnoverDossier.status.notin_(["Closed", "Issued", "APPROVED"]),
                TurnoverDossier.completeness_pct < 100.0,
            ).all()

            # Implementation note.
            open_ncrs = session.query(func.count(NCRRecord.id)).filter(
                NCRRecord.project_id == project_id,
                NCRRecord.status != "CLOSED",
            ).scalar() or 0

            # Implementation note.

            risk_points = 0
            signals: List[Dict[str, Any]] = []

            def emit_signal(
                severity: SignalSeverity,
                category: SignalCategory,
                title: str,
                evidence: str,
                prescriptive_action: str,
                impact_score: int,
            ) -> None:
                nonlocal risk_points
                risk_points += impact_score
                signals.append({
                    "severity": severity.value,
                    "category": category.value,
                    "title": title,
                    "evidence": evidence,
                    "action": prescriptive_action,
                    "points": impact_score,
                })

            # Implementation note.
            if blocked_fronts:
                emit_signal(
                    severity=SignalSeverity.HIGH,
                    category=SignalCategory.CONSTRAINT,
                    title="Constraint Backlog Restricting Field Velocity",
                    evidence=f"{len(blocked_fronts)} work front(s) are blocked by material, engineering holds, or permits.",
                    prescriptive_action="Execute immediate constraint triage: prioritize access and material issuance for next-critical fronts.",
                    impact_score=18,
                )

            # Implementation note.
            if unassigned_ready:
                emit_signal(
                    severity=SignalSeverity.HIGH,
                    category=SignalCategory.DISPATCH,
                    title="Ready Work Facing Idle Labor Risk",
                    evidence=f"{len(unassigned_ready)} fully ready work front(s) have no active crew assigned.",
                    prescriptive_action="Dispatch available piping and fit-up crews immediately before shift productivity drops.",
                    impact_score=16,
                )

            # Implementation note.
            if overdue_fronts:
                emit_signal(
                    severity=SignalSeverity.HIGH,
                    category=SignalCategory.SCHEDULE,
                    title="Schedule Slippage Pressure Detected",
                    evidence=f"{len(overdue_fronts)} work front(s) have passed their planned completion dates.",
                    prescriptive_action="Develop a targeted recovery plan and protect critical path isometrics from cascading delays.",
                    impact_score=15,
                )

            # Implementation note.
            joint_repair_rate = (repaired_welds / total_welds * 100) if total_welds > 0 else 0.0
            dia_inch_repair_rate = (repaired_dia_inch / total_dia_inch * 100) if total_dia_inch > 0 else 0.0

            if dia_inch_repair_rate >= 8.0:
                emit_signal(
                    severity=SignalSeverity.CRITICAL,
                    category=SignalCategory.QUALITY,
                    title="Weld Defect Rate Exceeding Critical Threshold",
                    evidence=f"Repair rate is {dia_inch_repair_rate:.1f}% ({repaired_dia_inch:.1f}/{total_dia_inch:.1f} Dia-Inch repaired).",
                    prescriptive_action="Conduct mandatory welder performance review, audit WPS parameters, and inspect electrode oven storage.",
                    impact_score=20,
                )
            elif dia_inch_repair_rate >= 5.0:
                emit_signal(
                    severity=SignalSeverity.MEDIUM,
                    category=SignalCategory.QUALITY,
                    title="Weld Repair Trend Deserves Quality Intervention",
                    evidence=f"Repair rate is {dia_inch_repair_rate:.1f}% (ASME standard benchmark: 5.0%).",
                    prescriptive_action="Analyze recurring defect patterns (e.g., Lack of Fusion / Porosity) by welder stencil.",
                    impact_score=10,
                )

            # Implementation note.
            daily_weld_capacity_estimate = max(10, total_welds // 30 if total_welds else 10)
            if awaiting_ndt >= (daily_weld_capacity_estimate * 2):
                emit_signal(
                    severity=SignalSeverity.HIGH,
                    category=SignalCategory.NDT_FLOW,
                    title="NDT Inspection Queue Forming Production Chokepoint",
                    evidence=f"{awaiting_ndt} weld(s) ({awaiting_ndt_dia_inch:.1f} Dia-Inch) are waiting for NDT clearance.",
                    prescriptive_action="Align NDT radiography shifts with fabrication pace to avoid blind welding without feedback.",
                    impact_score=16,
                )

            # Implementation note.
            if failed_tests > 0:
                emit_signal(
                    severity=SignalSeverity.CRITICAL,
                    category=SignalCategory.COMPLETION,
                    title="Failed Pressure Test Packages Require Recovery",
                    evidence=f"{failed_tests} test package(s) failed hydrotest or require re-testing.",
                    prescriptive_action="Investigate root cause of flange/weld leakage and clear all rework before reserving next test window.",
                    impact_score=18,
                )

            # Implementation note.
            if open_cat_a_punches > 0:
                emit_signal(
                    severity=SignalSeverity.CRITICAL,
                    category=SignalCategory.COMPLETION,
                    title="Category-A Punches Blocking Turnover & Hydrotest",
                    evidence=f"{open_cat_a_punches} open Category-A punch item(s) are actively stopping test readiness.",
                    prescriptive_action="Mobilize dedicated punch-clearing squad to eliminate Category-A items immediately.",
                    impact_score=19,
                )

            # Implementation note.
            unapproved_drafts_total = weld_drafts + fitup_drafts
            if unapproved_drafts_total >= 10:
                emit_signal(
                    severity=SignalSeverity.MEDIUM,
                    category=SignalCategory.DOCUMENT,
                    title="Field Inspection Reports Pending QC Approval",
                    evidence=f"{weld_drafts} welding and {fitup_drafts} fit-up draft report(s) are awaiting QC sign-off.",
                    prescriptive_action="Review and approve valid drafts to maintain real-time integrity of the official Weld Register.",
                    impact_score=8,
                )

            # Implementation note.
            if incomplete_dossiers:
                avg_completeness = sum(d.completeness_pct or 0.0 for d in incomplete_dossiers) / len(incomplete_dossiers)
                emit_signal(
                    severity=SignalSeverity.MEDIUM,
                    category=SignalCategory.TURNOVER,
                    title="Mechanical Completion Dossiers Incomplete",
                    evidence=f"{len(incomplete_dossiers)} dossier(s) below 100% completeness (Average: {avg_completeness:.0f}%).",
                    prescriptive_action="Resolve missing NDT reports, MTRs, and calibration certificates while field teams are still on site.",
                    impact_score=9,
                )

            # Implementation note.

            final_health_score = max(0, min(100, 100 - risk_points))
            
            if final_health_score >= 90:
                health_band = HealthBand.EXCELLENT
            elif final_health_score >= 80:
                health_band = HealthBand.CONTROLLED
            elif final_health_score >= 65:
                health_band = HealthBand.WATCH
            elif final_health_score >= 50:
                health_band = HealthBand.AT_RISK
            else:
                health_band = HealthBand.CRITICAL

            # Implementation note.

            prescriptive_actions = []
            for idx, sig in enumerate(sorted(signals, key=lambda x: -x["points"])[:8], start=1):
                prescriptive_actions.append({
                    "priority": idx,
                    "category": sig["category"],
                    "title": sig["action"],
                    "reason": sig["evidence"],
                    "impact_weight": sig["points"],
                    "severity": sig["severity"],
                })

            # Implementation note.

            return {
                "project_id": project_id,
                "timestamp": datetime.utcnow().isoformat(),
                "health_score": final_health_score,
                "health_label": health_band.value,
                "risk_points_deducted": risk_points,
                "signals": sorted(signals, key=lambda x: -x["points"]),
                "prescriptive_actions": prescriptive_actions,
                "kpis": {
                    "welding_metrics": {
                        "total_welds_count": total_welds,
                        "total_dia_inch": total_dia_inch,
                        "completed_dia_inch": completed_dia_inch,
                        "repaired_welds_count": repaired_welds,
                        "joint_repair_rate_pct": round(joint_repair_rate, 2),
                        "dia_inch_repair_rate_pct": round(dia_inch_repair_rate, 2),
                    },
                    "ndt_bottleneck": {
                        "awaiting_ndt_joints": awaiting_ndt,
                        "awaiting_ndt_dia_inch": awaiting_ndt_dia_inch,
                        "ndt_rejected_count": ndt_rejected_count,
                    },
                    "work_front_flow": {
                        "total_fronts": len(fronts),
                        "blocked_fronts": len(blocked_fronts),
                        "overdue_fronts": len(overdue_fronts),
                        "unassigned_ready": len(unassigned_ready),
                    },
                    "turnover_and_testing": {
                        "failed_pressure_tests": failed_tests,
                        "ready_for_test_packages": ready_tests,
                        "open_cat_a_punches": open_cat_a_punches,
                        "open_ncrs_count": open_ncrs,
                        "incomplete_dossiers_count": len(incomplete_dossiers),
                        "draft_reports_backlog": unapproved_drafts_total,
                    },
                },
                "scenario_simulation": self.simulate_capacity_what_if(
                    total_dia_inch=total_dia_inch,
                    awaiting_ndt_dia_inch=awaiting_ndt_dia_inch,
                    unassigned_ready_count=len(unassigned_ready),
                    blocked_count=len(blocked_fronts),
                    failed_tests_count=failed_tests,
                ),
            }

    # Implementation note.

    @staticmethod
    def simulate_capacity_what_if(
        total_dia_inch: float,
        awaiting_ndt_dia_inch: float,
        unassigned_ready_count: int,
        blocked_count: int,
        failed_tests_count: int,
        extra_ndt_crews: int = 1,
        extra_fitup_crews: int = 1,
    ) -> Dict[str, Any]:
        """
        شبیه‌سازی اثرات افزودن منابع، شیفت‌های مازاد و رفع موانع بر روی شاخص‌های کلیدی
        """
        # Implementation note.
        estimated_ndt_shift_capacity_dia_inch = 50.0 * extra_ndt_crews
        projected_ndt_backlog = max(0.0, awaiting_ndt_dia_inch - (estimated_ndt_shift_capacity_dia_inch * 3))  # Implementation note.

        # Implementation note.
        absorbable_fronts = min(unassigned_ready_count, extra_fitup_crews * 2)

        return {
            "simulation_parameters": {
                "extra_ndt_crews_added": extra_ndt_crews,
                "extra_piping_crews_added": extra_fitup_crews,
                "time_horizon_days": 3,
            },
            "projected_outcomes": {
                "current_ndt_queue_dia_inch": awaiting_ndt_dia_inch,
                "projected_ndt_queue_dia_inch": round(projected_ndt_backlog, 1),
                "ndt_queue_reduction_pct": round(((awaiting_ndt_dia_inch - projected_ndt_backlog) / awaiting_ndt_dia_inch * 100), 1) if awaiting_ndt_dia_inch > 0 else 0.0,
                "unassigned_fronts_absorbed": absorbable_fronts,
                "remaining_unassigned_fronts": unassigned_ready_count - absorbable_fronts,
            },
            "critical_dependencies": {
                "site_constraint_dependency": blocked_count > 0,
                "test_recovery_prerequisite": failed_tests_count > 0,
            },
            "expert_verdict": (
                f"Adding {extra_ndt_crews} NDT crew(s) will clear {estimated_ndt_shift_capacity_dia_inch * 3:.0f} Dia-Inch of inspection backlog in 3 days. "
                + ("However, clearing the " + str(blocked_count) + " blocked work front(s) remains the critical prerequisite to unlock sustained field flow." if blocked_count > 0 else "Field flow is clear to accelerate.")
            ),
        }