# -*- coding: utf-8 -*-
"""
services/execution_os_service.py – PipeAgent
موتور یکپارچه سیستم‌عامل اجرایی (Execution Operating System Engine)
شامل: ایجاد گراف وابستگی‌های اجرایی (Execution Graph)، هدایت خودکار اکیپ‌ها (Dispatch Autopilot)،
پیش‌بینی هوشمند گلوگاه‌ها، تحلیل کیفیت بر مبنای Dia-Inch و مانیتورینگ زنجیره تحویل (Turnover).
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, and_, or_, desc, case
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from db.manager import DatabaseManager
from db.models import (
    Project, LineListItem, Weld, NDTRecord, TestPackage, WorkFront,
    WorkAssignment, WorkTeam, SiteMachine, WeldReportDraft, FitupReportDraft,
    TurnoverDossier, Document, MaterialItem, HandoverPackage, PunchItem,
    ExecutionEvent, ExecutionGraphNode, ExecutionGraphEdge, ExecutionImpact,
    ExecutionForecast,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Constants
# ──────────────────────────────────────────────

class NodeType(str, Enum):
    LINE = "LINE"
    WELD = "WELD"
    NDT = "NDT"
    WORK_FRONT = "WORK_FRONT"
    TEST_PACKAGE = "TEST"
    TURNOVER = "TURNOVER"
    HANDOVER = "HANDOVER"
    PUNCH = "PUNCH"


class EdgeRelation(str, Enum):
    EXECUTION = "EXECUTION"              # Implementation note.
    QUALITY_GATE = "QUALITY_GATE"        # Implementation note.
    WORK_SCOPE = "WORK_SCOPE"            # Implementation note.
    TEST_GATE = "TEST_GATE"              # Implementation note.
    TURNOVER_EVIDENCE = "TURNOVER_EV"    # Implementation note.
    CLOSEOUT_GATE = "CLOSEOUT_GATE"      # Implementation note.


# ──────────────────────────────────────────────
#  ExecutionOSService Implementation
# ──────────────────────────────────────────────

class ExecutionOSService:
    """
    موتور محاسباتی هوش اجرایی، تحلیل گراف وابستگی‌ها و بهینه‌سازی جریان کار پایپینگ
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    def _health(self, constraint: dict, dispatch: dict, quality: dict, turnover: dict) -> Dict[str, Any]:
        """Deterministic lightweight health contract used by UI/automation checks."""
        score = 100
        if str(constraint.get("severity", "")).lower() == "high": score -= 15
        score -= min(10, int(dispatch.get("ready_unassigned", 0) or 0))
        score -= min(20, int(float(quality.get("repair_rate_pct", 0) or 0)))
        score -= min(20, len(turnover.get("gaps", []) or []) * 5)
        score = max(0, min(100, score))
        label = "Excellent" if score >= 90 else "Controlled" if score >= 80 else "Watch" if score >= 65 else "At Risk" if score >= 50 else "Critical"
        return {"score": score, "label": label}

    # Implementation note.

    def snapshot(self, project_id: int) -> Dict[str, Any]:
        """
        تولید گزارش جامع و تحلیل چندبعدی پروژه در یک اسکن فوق‌سریع
        """
        with self.db.session_scope() as session:
            project = session.query(Project).filter(Project.id == project_id).first()
            if not project:
                return {"error": f"Project #{project_id} not found"}

            # Implementation note.
            lines = session.query(LineListItem).filter(LineListItem.project_id == project_id).all()
            welds = session.query(Weld).filter(Weld.project_id == project_id).all()
            ndts = session.query(NDTRecord).join(Weld, NDTRecord.weld_id_fk == Weld.id).filter(Weld.project_id == project_id).all()
            fronts = session.query(WorkFront).filter(WorkFront.project_id == project_id).all()
            teams = session.query(WorkTeam).filter(WorkTeam.project_id == project_id).all()
            machines = session.query(SiteMachine).filter(SiteMachine.project_id == project_id).all()
            
            # Implementation note.
            assignments = (
                session.query(WorkAssignment)
                .join(WorkFront, WorkAssignment.work_front_id == WorkFront.id)
                .filter(WorkFront.project_id == project_id, WorkAssignment.status == "Assigned")
                .all()
            )

            drafts_w = session.query(func.count(WeldReportDraft.id)).filter(
                WeldReportDraft.project_id == project_id, WeldReportDraft.status != "Approved"
            ).scalar() or 0

            drafts_f = session.query(func.count(FitupReportDraft.id)).filter(
                FitupReportDraft.project_id == project_id, FitupReportDraft.status != "Approved"
            ).scalar() or 0

            tests = session.query(TestPackage).filter(TestPackage.project_id == project_id).all()
            dossiers = session.query(TurnoverDossier).filter(TurnoverDossier.project_id == project_id).all()
            docs = session.query(Document).filter(Document.project_id == project_id).all()
            materials_count = session.query(func.count(MaterialItem.id)).filter(MaterialItem.project_id == project_id).scalar() or 0
            handovers = session.query(HandoverPackage).filter(HandoverPackage.project_id == project_id).all()
            punches = session.query(PunchItem).filter(PunchItem.project_id == project_id).all()

            # Implementation note.
            line_by_number = {l.line_number.strip().upper(): l for l in lines if l.line_number}
            weld_by_id = {w.id: w for w in welds}

            # Implementation note.
            self._persist_execution_graph(session, project_id, lines, welds, ndts, fronts, tests, dossiers, handovers, punches, line_by_number, weld_by_id)
            impacts = self._process_execution_events(session, project_id)
            forecasts = self._refresh_forecasts(session, project_id, impacts)
            
            graph_summary = self._execution_graph_summary(lines, welds, ndts, fronts, tests, dossiers, handovers, punches, line_by_number, weld_by_id)
            bottlenecks = self._predictive_bottleneck(welds, ndts, fronts, teams, machines, tests)
            autopilot = self._work_front_autopilot(fronts, teams, machines, assignments)
            quality = self._quality_intelligence(welds, ndts)
            turnover = self._turnover_autopilot(lines, welds, ndts, tests, docs, dossiers, handovers, punches)
            health = self._calculate_composite_health(bottlenecks, autopilot, quality, turnover)

            unprocessed_events = session.query(func.count(ExecutionEvent.id)).filter(
                ExecutionEvent.project_id == project_id, ExecutionEvent.processed_at.is_(None)
            ).scalar() or 0

            total_events = session.query(func.count(ExecutionEvent.id)).filter(
                ExecutionEvent.project_id == project_id
            ).scalar() or 0

            open_impacts_count = session.query(func.count(ExecutionImpact.id)).filter(
                ExecutionImpact.project_id == project_id, ExecutionImpact.status == "Open"
            ).scalar() or 0

            return {
                "project": {"id": project.id, "code": project.project_code, "title": project.title},
                "health": health,
                "execution_graph": graph_summary,
                "predictive_bottleneck": bottlenecks,
                "work_front_autopilot": autopilot,
                "quality_intelligence": quality,
                "turnover_autopilot": turnover,
                "persistent_control": {
                    "total_events_logged": total_events,
                    "event_count": total_events,
                    "open_impacts": open_impacts_count,
                    "unprocessed_events_queue": unprocessed_events,
                    "active_impact_alerts_count": open_impacts_count,
                    "forecasts": forecasts,
                    "top_impact_alerts": impacts[:10],
                },
                "project_inventory_counts": {
                    "lines_count": len(lines),
                    "welds_count": len(welds),
                    "ndt_records_count": len(ndts),
                    "work_fronts_count": len(fronts),
                    "documents_count": len(docs),
                    "materials_count": materials_count,
                    "draft_reports_pending": drafts_w + drafts_f,
                },
            }

    # Implementation note.

    def _persist_execution_graph(
        self,
        session: Session,
        project_id: int,
        lines: List[LineListItem],
        welds: List[Weld],
        ndts: List[NDTRecord],
        fronts: List[WorkFront],
        tests: List[TestPackage],
        dossiers: List[TurnoverDossier],
        handovers: List[HandoverPackage],
        punches: List[PunchItem],
        line_by_number: Dict[str, LineListItem],
        weld_by_id: Dict[int, Weld],
    ) -> None:
        """
        تولید و ثبت اتمیک گراف اجرایی بدون کوئری‌های تکراری و با نگاشت O(1)
        """
        # Implementation note.
        session.query(ExecutionGraphEdge).filter(ExecutionGraphEdge.project_id == project_id).delete(synchronize_session=False)
        session.query(ExecutionGraphNode).filter(ExecutionGraphNode.project_id == project_id).delete(synchronize_session=False)

        nodes: List[ExecutionGraphNode] = []
        edges: List[ExecutionGraphEdge] = []

        def add_node(key: str, kind: NodeType, entity_id: Optional[int], label: str, status: str = "Unknown", line: Optional[str] = None, risk: int = 0):
            nodes.append(ExecutionGraphNode(
                project_id=project_id,
                node_key=key,
                node_type=kind.value,
                entity_id=entity_id,
                label=str(label or key)[:100],
                status=str(status or "Unknown")[:50],
                line_number=str(line).strip().upper() if line else None,
                risk_score=risk,
            ))

        def add_edge(from_k: str, to_k: str, relation: EdgeRelation, weight: float = 1.0):
            edges.append(ExecutionGraphEdge(
                project_id=project_id,
                from_key=from_k,
                to_key=to_k,
                relation=relation.value,
                weight=weight,
            ))

        # Implementation note.
        for l in lines:
            add_node(f"LINE:{l.id}", NodeType.LINE, l.id, l.line_number, l.status, l.line_number)

        # Implementation note.
        for w in welds:
            w_line = w.line_number.strip().upper() if w.line_number else None
            add_node(f"WELD:{w.id}", NodeType.WELD, w.id, w.weld_number if hasattr(w, "weld_number") else f"W-{w.id}", w.status, w_line)
            if w_line and w_line in line_by_number:
                line_obj = line_by_number[w_line]
                add_edge(f"LINE:{line_obj.id}", f"WELD:{w.id}", EdgeRelation.EXECUTION)

        # Implementation note.
        for n in ndts:
            w_parent = weld_by_id.get(n.weld_id_fk)
            n_line = w_parent.line_number.strip().upper() if w_parent and w_parent.line_number else None
            add_node(f"NDT:{n.id}", NodeType.NDT, n.id, getattr(n, "report_number", None) or f"NDT-{n.id}", n.verdict if hasattr(n, "verdict") else n.result, n_line)
            if w_parent:
                add_edge(f"WELD:{w_parent.id}", f"NDT:{n.id}", EdgeRelation.QUALITY_GATE)

        # Implementation note.
        for f in fronts:
            is_blocked = f.status in {"Blocked", "Waiting"} or bool((getattr(f, "blocker", "") or "").strip())
            f_line = f.line_number.strip().upper() if f.line_number else None
            add_node(f"FRONT:{f.id}", NodeType.WORK_FRONT, f.id, f.front_code, f.status, f_line, risk=85 if is_blocked else 0)
            if f_line and f_line in line_by_number:
                line_obj = line_by_number[f_line]
                add_edge(f"LINE:{line_obj.id}", f"FRONT:{f.id}", EdgeRelation.WORK_SCOPE)

        # Implementation note.
        for t in tests:
            add_node(f"TEST:{t.id}", NodeType.TEST_PACKAGE, t.id, t.package_number, t.status, None)
            raw_lines = (getattr(t, "line_numbers", "") or "").replace(";", ",")
            for ln in [x.strip().upper() for x in raw_lines.split(",") if x.strip()]:
                if ln in line_by_number:
                    line_obj = line_by_number[ln]
                    add_edge(f"LINE:{line_obj.id}", f"TEST:{t.id}", EdgeRelation.TEST_GATE)

        # Implementation note.
        for d in dossiers:
            scope_ln = getattr(d, "scope_key", None)
            add_node(f"DOSSIER:{d.id}", NodeType.TURNOVER, d.id, d.dossier_number, f"{d.completeness_pct or 0:.0f}%", scope_ln)
            if scope_ln and scope_ln.strip().upper() in line_by_number:
                line_obj = line_by_number[scope_ln.strip().upper()]
                add_edge(f"LINE:{line_obj.id}", f"DOSSIER:{d.id}", EdgeRelation.TURNOVER_EVIDENCE)

        # Implementation note.
        for p in punches:
            if getattr(p, "test_package_id", None):
                is_open = str(getattr(p, "status", "")).upper() not in {"QC_CLEARED", "CLIENT_ACCEPTED", "CLOSED"}
                p_line = p.line_number.strip().upper() if p.line_number else None
                add_node(f"PUNCH:{p.id}", NodeType.PUNCH, p.id, f"Punch #{getattr(p, 'punch_number', p.id)}", "Open" if is_open else "Closed", p_line, risk=80 if is_open and getattr(p, "category", "") == "A" else 30)
                add_edge(f"TEST:{p.test_package_id}", f"PUNCH:{p.id}", EdgeRelation.CLOSEOUT_GATE)

        # Implementation note.
        if nodes:
            session.bulk_save_objects(nodes)
        if edges:
            session.bulk_save_objects(edges)

    # Implementation note.

    def _process_execution_events(self, session: Session, project_id: int) -> List[Dict[str, Any]]:
        """
        تبدیل وقایع اخیر به اثرات ساختاریافته بر روی موجودیت‌های پایین‌دستی
        """
        unprocessed_events = (
            session.query(ExecutionEvent)
            .filter(ExecutionEvent.project_id == project_id, ExecutionEvent.processed_at.is_(None))
            .order_by(ExecutionEvent.occurred_at.asc())
            .limit(200)
            .all()
        )
        if not unprocessed_events:
            return []

        # Implementation note.
        nodes = session.query(ExecutionGraphNode).filter(ExecutionGraphNode.project_id == project_id).all()
        nodes_by_line = defaultdict(list)
        for n in nodes:
            if n.line_number:
                nodes_by_line[n.line_number.strip().upper()].append(n)

        impacts: List[Dict[str, Any]] = []
        new_impact_records: List[ExecutionImpact] = []
        now = datetime.utcnow()

        for ev in unprocessed_events:
            source_key = f"{ev.entity_type.upper()}:{ev.entity_id}" if ev.entity_id else (f"LINE:{ev.line_number}" if ev.line_number else "PROJECT")
            
            # Implementation note.
            candidates = []
            if ev.line_number and ev.line_number.strip().upper() in nodes_by_line:
                candidates = [n for n in nodes_by_line[ev.line_number.strip().upper()] if n.node_key != source_key]

            # Implementation note.
            if not candidates and ev.entity_type in {"TestPackage", "PunchItem", "WorkFront"}:
                candidates = [n for n in nodes if n.node_type in {NodeType.TEST_PACKAGE.value, NodeType.TURNOVER.value} and n.node_key != source_key][:6]

            for target in candidates[:10]:
                is_high_impact = ev.event_type in {"DELETED", "UPDATED"} and target.node_type in {NodeType.TEST_PACKAGE.value, NodeType.TURNOVER.value, NodeType.WORK_FRONT.value}
                severity = "High" if is_high_impact else "Medium"
                probability = 0.80 if severity == "High" else 0.50
                impact_score = round(probability * (85 if severity == "High" else 45), 1)

                explanation = f"{ev.entity_type} #{ev.entity_id or ''} triggered {ev.event_type}. Downstream {target.node_type} on scope '{target.line_number or 'Project'}' requires verification."
                action = {
                    NodeType.WORK_FRONT.value: "Verify work constraints and re-sequence crew dispatch.",
                    NodeType.WELD.value: "Protect NDT inspection and fit-up release flow.",
                    NodeType.NDT.value: "Expedite radiography evaluation to clear quality gate.",
                    NodeType.TEST_PACKAGE.value: "Re-validate test boundary prerequisites and blind list.",
                    NodeType.TURNOVER.value: "Audit dossier evidence gap prior to final MC signoff.",
                    NodeType.PUNCH.value: "Assign immediate punch rectification squad.",
                }.get(target.node_type, "Review downstream dependency.")

                impact_data = {
                    "event_id": ev.id,
                    "source": source_key,
                    "affected": target.node_key,
                    "affected_type": target.node_type,
                    "severity": severity,
                    "probability": probability,
                    "impact_score": impact_score,
                    "explanation": explanation,
                    "action": action,
                }
                impacts.append(impact_data)

                new_impact_records.append(ExecutionImpact(
                    project_id=project_id,
                    event_id=ev.id,
                    source_node_key=source_key,
                    affected_node_key=target.node_key,
                    affected_type=target.node_type,
                    severity=severity,
                    probability=probability,
                    impact_score=impact_score,
                    explanation=explanation,
                    recommended_action=action,
                    status="Open",
                    created_at=now,
                ))

            ev.processed_at = now

        if new_impact_records:
            session.bulk_save_objects(new_impact_records)

        return sorted(impacts, key=lambda x: x["impact_score"], reverse=True)

    # Implementation note.

    def _refresh_forecasts(self, session: Session, project_id: int, impacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """ایجاد پیش‌بینی‌های ۲۴ تا ۷۲ ساعته از خطرات بالقوه مسیر بحرانی"""
        session.query(ExecutionForecast).filter(
            ExecutionForecast.project_id == project_id, ExecutionForecast.status == "Open"
        ).update({"status": "Superseded"}, synchronize_session=False)

        forecast_rows = []
        new_forecasts = []
        now = datetime.utcnow()

        top_impacts = impacts[:5]
        for imp in top_impacts:
            title = f"Downstream Risk on {imp['affected_type'].title()} [{imp['affected']}]"
            new_forecasts.append(ExecutionForecast(
                project_id=project_id,
                forecast_type="DEPENDENCY_IMPACT",
                horizon_hours=24,
                severity=imp["severity"],
                title=title,
                probability=imp["probability"],
                impact_score=imp["impact_score"],
                evidence_json=json.dumps(imp, default=str),
                recommended_action=imp["action"],
                status="Open",
                valid_until=now + timedelta(hours=24),
                created_at=now,
            ))
            forecast_rows.append({
                "severity": imp["severity"],
                "title": title,
                "probability": imp["probability"],
                "impact_score": imp["impact_score"],
                "affected": imp["affected"],
                "action": imp["action"],
            })

        if top_impacts:
            forecast_rows.insert(0, {
                "severity": "High",
                "title": "Constraint not resolved today may affect downstream execution — Critical Path Bottlenecks Require Active Triage Today",
                "probability": max(x["probability"] for x in top_impacts),
                "impact_score": round(sum(x["impact_score"] for x in top_impacts), 1),
                "affected": ", ".join(x["affected"] for x in top_impacts[:3]),
                "action": "Resolve top constraint today to prevent compounding delays.",
            })

        if new_forecasts:
            session.bulk_save_objects(new_forecasts)

        return forecast_rows

    # Implementation note.

    def _predictive_bottleneck(
        self,
        welds: List[Weld],
        ndts: List[NDTRecord],
        fronts: List[WorkFront],
        teams: List[WorkTeam],
        machines: List[SiteMachine],
        tests: List[TestPackage],
    ) -> Dict[str, Any]:
        """پایش زنده ۵ گلوگاه اصلی ساخت و تست پایپینگ"""
        total_welds = len(welds)
        welded_count = sum(1 for w in welds if str(w.status).upper() in {"WELDED", "WELDED_VT_PENDING", "VT_ACCEPTED", "NDT_REQUESTED", "NDT_CLEARED", "COMPLETED"})
        
        # Implementation note.
        ndt_queue_dia_inch = sum(float(getattr(w, "dia_inch", 1.0) or 1.0) for w in welds if str(w.status).upper() in {"WELDED", "WELDED_VT_PENDING", "NDT_REQUESTED"})
        ndt_queue_count = sum(1 for w in welds if str(w.status).upper() in {"WELDED", "WELDED_VT_PENDING", "NDT_REQUESTED"})

        blocked_fronts = sum(1 for f in fronts if f.status in {"Blocked", "Waiting"} or bool((getattr(f, "blocker", "") or "").strip()))
        overdue_fronts = sum(1 for f in fronts if f.planned_finish and f.planned_finish < date.today() and f.status != "Completed")
        ready_tests = sum(1 for t in tests if str(t.status).upper() in {"READY_FOR_TEST", "READY FOR TEST"})
        
        avail_teams = sum(1 for t in teams if getattr(t, "status", "") == "Available")
        avail_machines = sum(1 for m in machines if getattr(m, "status", "") == "Available")

        signals = []

        # Implementation note.
        if ndt_queue_count >= max(5, int(max(welded_count, 1) * 0.08)):
            signals.append({
                "category": "NDT CAPACITY",
                "severity": "High",
                "value": ndt_queue_count,
                "evidence": f"{ndt_queue_count} weld(s) ({ndt_queue_dia_inch:.1f} Dia-Inch) awaiting NDT clearance.",
                "recommendation": "Mobilize additional radiography shifts before blind welding accumulates.",
            })

        # Implementation note.
        if blocked_fronts > 0:
            signals.append({
                "category": "FIELD CONSTRAINT",
                "severity": "High",
                "value": blocked_fronts,
                "evidence": f"{blocked_fronts} work front(s) blocked by permits, material, or access holds.",
                "recommendation": "Triage constraints by near-term production impact to unlock crew flow.",
            })

        # Implementation note.
        if overdue_fronts > 0:
            signals.append({
                "category": "SCHEDULE RECOVERY",
                "severity": "Medium",
                "value": overdue_fronts,
                "evidence": f"{overdue_fronts} work front(s) are past planned finish dates.",
                "recommendation": "Re-sequence critical isometrics and establish firm recovery milestones.",
            })

        # Implementation note.
        if ready_tests >= 3:
            signals.append({
                "category": "HYDROTESTING",
                "severity": "Medium",
                "value": ready_tests,
                "evidence": f"{ready_tests} test package(s) fully ready for hydrotest execution.",
                "recommendation": "Coordinate water filling, manifold hookups, and joint QC/Client walkdown.",
            })

        # Implementation note.
        if avail_teams == 0 and any(f.status in {"Ready", "READY"} for f in fronts):
            signals.append({
                "category": "CREW SHORTAGE",
                "severity": "High",
                "value": 0,
                "evidence": "Zero available teams while executable ready work fronts exist.",
                "recommendation": "Reassign or rebalance piping and fit-up crews to active fronts.",
            })

        signals.sort(key=lambda x: (0 if x["severity"] == "High" else 1, -x["value"]))
        top = signals[0] if signals else {
            "category": "FLOW CONTROLLED",
            "severity": "Info",
            "value": 0,
            "evidence": "No leading bottlenecks exceeded critical thresholds.",
            "recommendation": "Maintain standard production pace and quality surveillance.",
        }

        return {
            "status": top["category"],
            "severity": top["severity"],
            "value": top["value"],
            "horizon": "next 24–72 hours" if top["severity"] in {"High", "Medium"} else "next shift",
            "evidence": top["evidence"],
            "recommendation": top["recommendation"],
            "signals": signals,
        }

    # Implementation note.

    def _work_front_autopilot(
        self,
        fronts: List[WorkFront],
        teams: List[WorkTeam],
        machines: List[SiteMachine],
        assignments: List[WorkAssignment],
    ) -> Dict[str, Any]:
        """
        هدایت هوشمند و رتبه‌بندی جبهه‌های کاری برای اعزام اکیپ‌ها بر مبنای اولویت و دیسیپلین
        """
        assigned_front_ids = {a.work_front_id for a in assignments}
        available_teams = [t for t in teams if getattr(t, "status", "") == "Available"]
        available_machines = [m for m in machines if getattr(m, "status", "") == "Available"]

        # Implementation note.
        candidates = [
            f for f in fronts
            if f.status in {"Ready", "READY", "In Progress"}
            and getattr(f, "readiness", "") in {"Ready", "READY", ""}
            and not bool((getattr(f, "blocker", "") or "").strip())
            and f.id not in assigned_front_ids
        ]

        today = date.today()

        def compute_dispatch_score(f: WorkFront) -> int:
            base = {"Urgent": 100, "High": 80, "Normal": 50, "Low": 20}.get(getattr(f, "priority", "Normal"), 50)
            if f.planned_finish:
                delta_days = (f.planned_finish - today).days
                if delta_days <= 0:
                    base += 40  # Implementation note.
                elif delta_days <= 2:
                    base += 25
                elif delta_days <= 7:
                    base += 10
            return base

        candidates.sort(key=compute_dispatch_score, reverse=True)
        recommendations = []

        for f in candidates[:10]:
            f_discipline = (getattr(f, "discipline", "") or "").lower()
            
            # Implementation note.
            matching_team = next((t for t in available_teams if (getattr(t, "discipline", "") or "").lower() == f_discipline), None)
            if not matching_team and available_teams:
                matching_team = available_teams[0]  # Implementation note.

            # Implementation note.
            assigned_machine = None
            f_activity = getattr(f, "activity_type", "")
            if f_activity in {"Pipe Erection", "Spool Installation", "Heavy Rigging", "Valve Installation"} and available_machines:
                assigned_machine = available_machines[0]

            recommendations.append({
                "front_id": f.id,
                "front_code": f.front_code,
                "activity_type": f_activity,
                "priority": getattr(f, "priority", "Normal"),
                "dispatch_score": compute_dispatch_score(f),
                "recommended_team": matching_team.team_code if matching_team else None,
                "recommended_machine": assigned_machine.machine_code if assigned_machine else None,
                "reason": "Optimal resource & discipline match" if matching_team else "Ready work front awaiting crew mobilization",
                "requires_supervisor_approval": True,
            })

        return {
            "ready_unassigned_fronts_count": len(candidates),
            "available_crews_count": len(available_teams),
            "available_machines_count": len(available_machines),
            "recommendations": recommendations,
            "guardrail_notice": "Autopilot recommendations are advisory. Official dispatch requires field supervisor confirmation.",
        }

    # Implementation note.

    def _quality_intelligence(self, welds: List[Weld], ndts: List[NDTRecord]) -> Dict[str, Any]:
        """تحلیل عیوب جوشکاری بر مبنای اینچ-قطر و توزیع پارتو جوشکاران"""
        total_welds = len(welds)
        total_dia_inch = sum(float(getattr(w, "dia_inch", 1.0) or 1.0) for w in welds)
        
        repaired_welds = [w for w in welds if (getattr(w, "repair_count", 0) or 0) > 0]
        repaired_dia_inch = sum(float(getattr(w, "dia_inch", 1.0) or 1.0) for w in repaired_welds)

        joint_repair_rate = (len(repaired_welds) / total_welds * 100) if total_welds > 0 else 0.0
        dia_inch_repair_rate = (repaired_dia_inch / total_dia_inch * 100) if total_dia_inch > 0 else 0.0

        # Implementation note.
        welder_defect_counter = Counter(
            (getattr(w, "welder_id", None) or getattr(w, "root_welder_id", None) or "Unassigned") for w in repaired_welds
        )
        process_defect_counter = Counter((getattr(w, "welding_process", None) or getattr(w, "process", None) or "Unknown") for w in repaired_welds)

        ndt_failed_count = sum(1 for n in ndts if str(getattr(n, "verdict", getattr(n, "result", ""))).upper() in {"REJ", "REJECTED", "FAIL", "FAILED"})

        signals = []
        if dia_inch_repair_rate >= 8.0:
            signals.append({
                "severity": "High",
                "title": "Dia-Inch Defect Rate Above Critical 8% Limit",
                "evidence": f"{dia_inch_repair_rate:.1f}% Dia-Inch repaired ({repaired_dia_inch:.1f}/{total_dia_inch:.1f} in).",
                "action": "Audit electrode handling ovens, shielding gas purity, and suspend high-defect welders.",
            })
        elif dia_inch_repair_rate >= 5.0:
            signals.append({
                "severity": "Medium",
                "title": "Weld Repair Trend Deserves Proactive Control",
                "evidence": f"Current repair rate is {dia_inch_repair_rate:.1f}% (Standard limit: 5.0%).",
                "action": "Inspect recurring defects (Porosity/LOF) by welder stencil.",
            })

        if ndt_failed_count > 0:
            signals.append({
                "severity": "High",
                "title": "Unresolved NDT Failures in System",
                "evidence": f"{ndt_failed_count} rejected NDT inspections pending repair signoff.",
                "action": "Verify defect excavation, R1 re-weld and re-radiography before hydrotest.",
            })

        return {
            "total_welds_count": total_welds,
            "total_dia_inch": round(total_dia_inch, 1),
            "repaired_dia_inch": round(repaired_dia_inch, 1),
            "joint_repair_rate_pct": round(joint_repair_rate, 2),
            "dia_inch_repair_rate_pct": round(dia_inch_repair_rate, 2),
            "repair_rate_pct": round(dia_inch_repair_rate, 2),
            "ndt_failures_count": ndt_failed_count,
            "ndt_failures": ndt_failed_count,
            "top_defect_welders": welder_defect_counter.most_common(6),
            "top_defect_processes": process_defect_counter.most_common(4),
            "signals": signals,
        }

    # Implementation note.

    def _turnover_autopilot(
        self,
        lines: List[LineListItem],
        welds: List[Weld],
        ndts: List[NDTRecord],
        tests: List[TestPackage],
        docs: List[Document],
        dossiers: List[TurnoverDossier],
        handovers: List[HandoverPackage],
        punches: List[PunchItem],
    ) -> Dict[str, Any]:
        """پایش پیوسته شواهد تحویل و جلوگیری از شکار مدارک در انتهای پروژه"""
        evidence_gaps = []

        if lines and not welds:
            evidence_gaps.append({"category": "Weld Population", "evidence": "Line list registered but no weld records are linked."})
        if welds and not ndts:
            evidence_gaps.append({"category": "NDT Traceability", "evidence": "Weld population exists with zero NDT inspection records."})
        if not docs:
            evidence_gaps.append({"category": "Engineering Documents", "evidence": "No isometric drawings or P&IDs registered."})
        if not tests:
            evidence_gaps.append({"category": "Test Packages", "evidence": "No pressure test packages defined for lines."})

        open_cat_a_punches = sum(1 for p in punches if getattr(p, "category", "") == "A" and str(getattr(p, "status", "")).upper() not in {"QC_CLEARED", "CLIENT_ACCEPTED", "CLOSED"})
        open_cat_b_punches = sum(1 for p in punches if getattr(p, "category", "") == "B" and str(getattr(p, "status", "")).upper() not in {"QC_CLEARED", "CLIENT_ACCEPTED", "CLOSED"})

        if open_cat_a_punches > 0:
            evidence_gaps.append({"category": "Blocking Punches", "evidence": f"{open_cat_a_punches} Category-A punch(es) blocking hydrotest/MC."})

        avg_completeness = round(sum((d.completeness_pct or 0.0) for d in dossiers) / len(dossiers), 1) if dossiers else 0.0
        ready_dossiers = sum(1 for d in dossiers if (d.completeness_pct or 0.0) >= 95.0 and str(getattr(d, "status", "")).upper() not in {"CLOSED", "ISSUED"})

        return {
            "dossier_average_completeness_pct": avg_completeness,
            "total_turnover_dossiers": len(dossiers),
            "ready_for_handover_dossiers": ready_dossiers,
            "open_blocking_cat_a_punches": open_cat_a_punches,
            "open_non_blocking_cat_b_punches": open_cat_b_punches,
            "evidence_gaps": evidence_gaps,
            "is_ready_for_mc": (open_cat_a_punches == 0 and len(evidence_gaps) == 0 and avg_completeness >= 95.0),
        }

    # Implementation note.

    def _calculate_composite_health(
        self,
        bottlenecks: Dict[str, Any],
        autopilot: Dict[str, Any],
        quality: Dict[str, Any],
        turnover: Dict[str, Any],
    ) -> Dict[str, Any]:
        """محاسبه نمره سلامت کل پروژه (۰ تا ۱۰۰) با جریمه‌های وزنی"""
        penalty = 0

        # Implementation note.
        if bottlenecks.get("severity") == "High":
            penalty += 20
        elif bottlenecks.get("severity") == "Medium":
            penalty += 10

        # Implementation note.
        unassigned_count = autopilot.get("ready_unassigned_fronts_count", 0)
        penalty += min(20, unassigned_count * 3)

        # Implementation note.
        dia_inch_repair = quality.get("dia_inch_repair_rate_pct", 0.0)
        if dia_inch_repair >= 8.0:
            penalty += 20
        elif dia_inch_repair >= 5.0:
            penalty += 10

        # Implementation note.
        if turnover.get("open_blocking_cat_a_punches", 0) > 0:
            penalty += 25
        penalty += min(15, len(turnover.get("evidence_gaps", [])) * 5)

        final_score = max(0, min(100, 100 - penalty))
        label = "Controlled" if final_score >= 85 else "Watch" if final_score >= 70 else "At Risk" if final_score >= 50 else "Critical"

        return {
            "score": final_score,
            "label": label,
            "penalty_points_deducted": penalty,
        }

    # Implementation note.

    def _execution_graph_summary(
        self,
        lines: List[LineListItem],
        welds: List[Weld],
        ndts: List[NDTRecord],
        fronts: List[WorkFront],
        tests: List[TestPackage],
        dossiers: List[TurnoverDossier],
        handovers: List[HandoverPackage],
        punches: List[PunchItem],
        line_by_number: Dict[str, LineListItem],
        weld_by_id: Dict[int, Weld],
    ) -> Dict[str, Any]:
        """تولید خروجی خلاصه و ساختاریافته گراف جهت رندر در فرانت‌اند (Cytoscape/D3.js)"""
        node_counts = Counter()
        edges_summary = []
        nodes_summary = []

        # Implementation note.
        for l in lines[:100]:
            nodes_summary.append({"id": f"LINE:{l.id}", "type": "LINE", "label": l.line_number, "status": l.status or "Active"})
            node_counts["LINE"] += 1

        # Implementation note.
        for w in welds[:250]:
            w_key = f"WELD:{w.id}"
            nodes_summary.append({"id": w_key, "type": "WELD", "label": getattr(w, "weld_number", f"W-{w.id}"), "status": w.status or "Pending"})
            node_counts["WELD"] += 1
            if w.line_number and w.line_number.strip().upper() in line_by_number:
                l_obj = line_by_number[w.line_number.strip().upper()]
                edges_summary.append({"from": f"LINE:{l_obj.id}", "to": w_key, "relation": "EXECUTION"})

        # Implementation note.
        for n in ndts[:200]:
            n_key = f"NDT:{n.id}"
            nodes_summary.append({"id": n_key, "type": "NDT", "label": getattr(n, "report_number", f"NDT-{n.id}"), "status": getattr(n, "verdict", "Pending")})
            node_counts["NDT"] += 1
            if n.weld_id_fk in weld_by_id:
                edges_summary.append({"from": f"WELD:{n.weld_id_fk}", "to": n_key, "relation": "QUALITY_GATE"})

        # Implementation note.
        for t in tests[:50]:
            nodes_summary.append({"id": f"TEST:{t.id}", "type": "TEST", "label": t.package_number, "status": t.status or "Planned"})
            node_counts["TEST"] += 1

        return {
            "total_nodes_sampled": len(nodes_summary),
            "total_edges_sampled": len(edges_summary),
            "node_type_breakdown": dict(node_counts),
            "nodes": nodes_summary,
            "edges": edges_summary,
            "topology_model": "Line -> Weld -> NDT -> Test Package -> Turnover Dossier",
        }