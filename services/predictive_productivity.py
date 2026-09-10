# -*- coding: utf-8 -*-
"""
services/predictive_productivity.py – PipeAgent
موتور پیشرفته و قابل ممیزی پایش بهره‌وری، تحلیل ریسک بیکاری (Idle Risk) و توازن منابع کارگاهی
شامل: محاسبه شاخص Dia-Inch بر نفر-ساعت (DI/MH)، پایش گلوگاه ماشین‌آلات سنگین،
کشف زودهنگام اکیپ‌های معطل/سربار، پیش‌بینی راندمان شیفت‌های آتی و ثبت اسنپ‌شات‌های روزانه.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc, case
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from db.manager import DatabaseManager
from db.models import (
    WorkFront,
    WorkTeam,
    SiteMachine,
    ProductivitySnapshot,
    WorkAssignment,
    Weld,
    Spool,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Productivity Classifications
# ──────────────────────────────────────────────

class ProductivityRiskType(str, Enum):
    """انواع ریسک‌های مرتبط با نیروی انسانی، ماشین‌آلات و بهره‌وری"""
    TEAM_IDLE_RISK = "TEAM_IDLE_RISK"                  # Implementation note.
    TEAM_OVERLOAD = "TEAM_OVERLOAD"                    # Implementation note.
    MACHINE_BOTTLENECK = "MACHINE_BOTTLENECK"          # Implementation note.
    DISCIPLINE_MISMATCH = "DISCIPLINE_MISMATCH"        # Implementation note.
    EFFICIENCY_DEGRADATION = "EFFICIENCY_DEGRADATION"  # Implementation note.
    HIGH_IDLE_HOURS = "HIGH_IDLE_HOURS"                # Implementation note.


class RiskSeverity(str, Enum):
    CRITICAL = "CRITICAL"      # Implementation note.
    HIGH = "HIGH"              # Implementation note.
    MEDIUM = "MEDIUM"          # Implementation note.
    LOW = "LOW"                # Implementation note.


class TeamDiscipline(str, Enum):
    PIPING_ERECTION = "Piping"
    WELDING = "Welding"
    FITUP = "Fitup"
    RIGGING = "Rigging"
    SCAFFOLDING = "Scaffolding"
    HYDROTEST = "Hydrotest"
    PAINTING = "Painting"
    INSULATION = "Insulation"


# ──────────────────────────────────────────────
#  Predictive Productivity Implementation
# ──────────────────────────────────────────────

class PredictiveProductivity:
    """
    سرویس مرکزی تحلیل بهره‌وری، پیش‌بینی خروجی شیفت‌های کاری و رادار ریسک بیکاری منابع
    """

    # Implementation note.
    STANDARD_DI_PER_MANHOUR_BENCHMARK = 1.5

    def __init__(self, db: DatabaseManager):
        self.db = db

    # Implementation note.

    def forecast(self, project_id: int, days_window: int = 30) -> Dict[str, Any]:
        """
        تحلیل چندبعدی راندمان کارگاهی با اجرای کوئری‌های تجمعی SQL و ممانعت از لود اضافی در RAM:
        ۱. محاسبه دقیق ساعات کارکرد واقعی، مفید و بیکاری در بازه مشخص
        ۲. محاسبه راندمان اینچ-قطر بر نفر-ساعت (Dia-Inch/MH)
        ۳. سنجش بار کاری فعال اکیپ‌ها و ماشین‌آلات (با فیلتر دقیق چندمستأجری پروژه)
        ۴. تولید سیگنال‌های پیش‌نگر برای اکیپ‌های در معرض بیکاری یا اضافه بار
        """
        cutoff_date = date.today() - timedelta(days=days_window)

        with self.db.session_scope() as session:
            # Implementation note.
            snap_stats = session.query(
                func.sum(func.coalesce(ProductivitySnapshot.actual_hours, 0.0)).label("total_actual"),
                func.sum(func.coalesce(ProductivitySnapshot.productive_hours, 0.0)).label("total_productive"),
                func.sum(func.coalesce(ProductivitySnapshot.idle_hours, 0.0)).label("total_idle"),
                func.count(ProductivitySnapshot.id).label("snapshots_count"),
            ).filter(
                ProductivitySnapshot.project_id == project_id,
                ProductivitySnapshot.work_date >= cutoff_date,
            ).first()

            total_actual = float(snap_stats.total_actual or 0.0)
            total_productive = float(snap_stats.total_productive or 0.0)
            total_idle = float(snap_stats.total_idle or 0.0)

            utilization_pct = round((total_productive / total_actual * 100), 2) if total_actual > 0 else 0.0
            idle_ratio_pct = round((total_idle / total_actual * 100), 2) if total_actual > 0 else 0.0

            # Implementation note.
            completed_dia_inch = float(session.query(
                func.sum(func.coalesce(Weld.dia_inch, 1.0))
            ).filter(
                Weld.project_id == project_id,
                Weld.status.in_(["WELDED", "WELDED_VT_PENDING", "VT_ACCEPTED", "NDT_REQUESTED", "NDT_CLEARED", "COMPLETED"]),
                Weld.welding_date >= cutoff_date if hasattr(Weld, "welding_date") else True,
            ).scalar() or 0.0)

            di_per_manhour = round(completed_dia_inch / total_actual, 2) if total_actual > 0 else 0.0

            # Implementation note.
            teams = session.query(WorkTeam).filter(WorkTeam.project_id == project_id).all()
            machines = session.query(SiteMachine).filter(SiteMachine.project_id == project_id).all()
            fronts = session.query(WorkFront).filter(WorkFront.project_id == project_id).all()

            # Implementation note.
            active_assignments = (
                session.query(WorkAssignment)
                .join(WorkFront, WorkAssignment.work_front_id == WorkFront.id)
                .filter(
                    WorkFront.project_id == project_id,
                    WorkAssignment.status.in_(["Assigned", "In Progress", "ASSIGNED", "IN_PROGRESS"]),
                )
                .all()
            )

            # Implementation note.
            assigned_front_ids: Set[int] = {a.work_front_id for a in active_assignments}

            # Implementation note.
            team_load: Dict[str, int] = {t.team_code: 0 for t in teams}
            machine_load: Dict[str, int] = {m.machine_code: 0 for m in machines}

            team_id_to_code = {t.id: t.team_code for t in teams}
            machine_id_to_code = {m.id: m.machine_code for m in machines}

            for a in active_assignments:
                res_type = str(getattr(a, "resource_type", "")).upper()
                res_id = getattr(a, "resource_id", None)

                if res_type in ["TEAM", "WORK_TEAM"] and res_id in team_id_to_code:
                    team_load[team_id_to_code[res_id]] += 1
                elif res_type in ["MACHINE", "SITE_MACHINE"] and res_id in machine_id_to_code:
                    machine_load[machine_id_to_code[res_id]] += 1

            # Implementation note.
            ready_fronts = [
                f for f in fronts
                if f.status in ("Ready", "READY", "In Progress")
                and getattr(f, "readiness", "") in ("Ready", "READY", "")
                and not bool((getattr(f, "blocker", "") or "").strip())
            ]
            unassigned_ready_fronts = [f for f in ready_fronts if f.id not in assigned_front_ids]
            blocked_fronts = [f for f in fronts if f.status in ("Blocked", "Waiting") or bool((getattr(f, "blocker", "") or "").strip())]

            # Implementation note.
            risks: List[Dict[str, Any]] = []

            # Implementation note.
            for t in teams:
                t_code = t.team_code
                t_status = getattr(t, "status", "Available")
                load = team_load.get(t_code, 0)
                t_discipline = getattr(t, "discipline", "Piping") or "Piping"

                # Implementation note.
                matching_unassigned = [
                    f for f in unassigned_ready_fronts
                    if (getattr(f, "discipline", "") or "").lower() == t_discipline.lower()
                ]

                # Implementation note.
                if t_status == "Available" and load == 0:
                    if matching_unassigned:
                        risks.append({
                            "type": ProductivityRiskType.TEAM_IDLE_RISK.value,
                            "severity": RiskSeverity.HIGH.value,
                            "resource_code": t_code,
                            "resource_type": "TEAM",
                            "risk_score": 85,
                            "title": f"Crew '{t_code}' ({t_discipline}) is Idle while Matching Work Exists",
                            "message": f"Crew is available and 0 assignments active; {len(matching_unassigned)} ready {t_discipline} front(s) are waiting for dispatch.",
                            "recommended_action": f"Dispatch '{t_code}' immediately to Front '{matching_unassigned[0].front_code}'.",
                        })
                    else:
                        risks.append({
                            "type": ProductivityRiskType.TEAM_IDLE_RISK.value,
                            "severity": RiskSeverity.MEDIUM.value,
                            "resource_code": t_code,
                            "resource_type": "TEAM",
                            "risk_score": 60,
                            "title": f"Crew '{t_code}' Available but No Matching Ready Scope",
                            "message": f"Crew is unassigned, but no {t_discipline} fronts are currently marked as Ready.",
                            "recommended_action": f"Clear constraints on blocked {t_discipline} fronts to feed this crew.",
                        })

                # Implementation note.
                elif load >= 2:
                    risks.append({
                        "type": ProductivityRiskType.TEAM_OVERLOAD.value,
                        "severity": RiskSeverity.HIGH.value if load >= 3 else RiskSeverity.MEDIUM.value,
                        "resource_code": t_code,
                        "resource_type": "TEAM",
                        "risk_score": 75 if load == 2 else 90,
                        "title": f"Crew '{t_code}' Overloaded with {load} Concurrent Fronts",
                        "message": f"Crew has {load} active work assignments, which can fragment labor efficiency and cause supervision deficit.",
                        "recommended_action": f"Re-sequence work fronts or split tasks to avoid parallel bottlenecks.",
                    })

            # Implementation note.
            crane_heavy_fronts = [
                f for f in unassigned_ready_fronts
                if getattr(f, "activity_type", "") in {"Pipe Erection", "Spool Installation", "Heavy Rigging", "Valve Installation"}
            ]
            available_machines_count = sum(1 for m in machines if getattr(m, "status", "") == "Available" and machine_load.get(m.machine_code, 0) == 0)

            if len(crane_heavy_fronts) > available_machines_count and available_machines_count == 0:
                risks.append({
                    "type": ProductivityRiskType.MACHINE_BOTTLENECK.value,
                    "severity": RiskSeverity.HIGH.value,
                    "resource_code": "CRANE_RIGGING_FLEET",
                    "resource_type": "MACHINE",
                    "risk_score": 80,
                    "title": "Rigging & Lifting Equipment Chokepoint Detected",
                    "message": f"{len(crane_heavy_fronts)} heavy erection front(s) are waiting, but 0 lifting machines are available.",
                    "recommended_action": "Reallocate crane from low-priority area or mobilize additional mobile crane unit.",
                })

            # Implementation note.
            if total_actual >= 500 and utilization_pct < 65.0:
                risks.append({
                    "type": ProductivityRiskType.HIGH_IDLE_HOURS.value,
                    "severity": RiskSeverity.HIGH.value,
                    "resource_code": "PROJECT_LABOR_POOL",
                    "resource_type": "PROJECT",
                    "risk_score": 75,
                    "title": f"Excessive Idle Ratio ({idle_ratio_pct:.1f}% Idle Hours)",
                    "message": f"{total_idle:.1f} idle hours recorded out of {total_actual:.1f} actual hours. Productive utilization is only {utilization_pct:.1f}%.",
                    "recommended_action": "Conduct site delay analysis on permits, weather holds, and material staging delays.",
                })

            risks.sort(key=lambda x: -x["risk_score"])

            # Implementation note.
            projected_daily_di = round((total_productive / max(1, days_window)) * di_per_manhour, 1) if total_productive else 0.0

            return {
                "project_id": project_id,
                "analysis_window_days": days_window,
                "timestamp": datetime.utcnow().isoformat(),
                "productivity_kpis": {
                    "utilization_rate_pct": utilization_pct,
                    "idle_ratio_pct": idle_ratio_pct,
                    "total_actual_manhours": total_actual,
                    "total_productive_manhours": total_productive,
                    "total_idle_manhours": total_idle,
                    "completed_dia_inch": completed_dia_inch,
                    "dia_inch_per_manhour": di_per_manhour,
                    "benchmark_di_per_manhour": self.STANDARD_DI_PER_MANHOUR_BENCHMARK,
                    "performance_index": round((di_per_manhour / self.STANDARD_DI_PER_MANHOUR_BENCHMARK), 2) if di_per_manhour else 0.0,
                },
                "resource_status": {
                    "total_crews_count": len(teams),
                    "available_crews_count": sum(1 for t in teams if getattr(t, "status", "") == "Available" and team_load.get(t.team_code, 0) == 0),
                    "total_machines_count": len(machines),
                    "available_machines_count": available_machines_count,
                    "ready_unassigned_fronts_count": len(unassigned_ready_fronts),
                    "blocked_fronts_count": len(blocked_fronts),
                },
                "identified_productivity_risks": risks[:15],
                "forward_projection": {
                    "estimated_daily_dia_inch_output": projected_daily_di,
                    "next_3_shifts_projected_dia_inch": round(projected_daily_di * 3, 1),
                    "confidence_level": "High" if len(teams) > 0 and total_actual > 200 else "Preliminary",
                },
            }

    # Implementation note.

    def record_shift_snapshot(
        self,
        project_id: int,
        work_date: date,
        shift_type: str = "DAY",  # DAY / NIGHT
        team_id: Optional[int] = None,
        actual_manhours: float = 0.0,
        productive_manhours: float = 0.0,
        idle_manhours: float = 0.0,
        dia_inch_produced: float = 0.0,
        idle_reason_category: Optional[str] = None,  # PERMIT_DELAY, MATERIAL_SHORTAGE, WEATHER, EQUIPMENT_BREAKDOWN
        recorded_by: str = "timekeeper",
        remarks: str = "",
    ) -> Dict[str, Any]:
        """
        ثبت رسمی آمار کارکرد و توقفات شیفت کاری جهت تغذیه موتور تحلیل بهره‌وری
        """
        if actual_manhours < (productive_manhours + idle_manhours):
            actual_manhours = productive_manhours + idle_manhours

        with self.db.session_scope() as session:
            snapshot = ProductivitySnapshot(
                project_id=project_id,
                team_id=team_id,
                work_date=work_date,
                shift_type=shift_type.strip().upper(),
                actual_hours=actual_manhours,
                productive_hours=productive_manhours,
                idle_hours=idle_manhours,
                dia_inch_output=dia_inch_produced,
                idle_reason=idle_reason_category,
                recorded_by=recorded_by.strip(),
                remarks=remarks.strip(),
                created_at=datetime.utcnow(),
            )
            session.add(snapshot)
            session.flush()

            snapshot_id = snapshot.id
            logger.info(
                f"Productivity Snapshot #{snapshot_id} recorded for Project #{project_id} "
                f"({work_date} {shift_type}): {productive_manhours}/{actual_manhours} MH, {dia_inch_produced} DI."
            )

        return {
            "snapshot_id": snapshot_id,
            "project_id": project_id,
            "work_date": work_date.isoformat(),
            "actual_hours": actual_manhours,
            "productive_hours": productive_manhours,
            "idle_hours": idle_manhours,
            "utilization_pct": round((productive_manhours / actual_manhours * 100), 1) if actual_manhours > 0 else 0.0,
            "dia_inch_output": dia_inch_produced,
        }