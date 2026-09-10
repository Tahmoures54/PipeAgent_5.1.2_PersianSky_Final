# -*- coding: utf-8 -*-
"""
services/ai_assistant_service.py – PipeAgent
سرویس هوش مصنوعی هیبریدی جهت کنترل هوشمند پروژه‌های پایپینگ و پالایشگاهی
شامل: موتور تحلیل قطعی کارگاهی (Local Rule Engine)، کلاینت مقاوم ابری (LLM Integration)،
سیستم رادار گلوگاه‌ها (Constraint Radar) و تحلیل ریسک‌های کیفی و اجرایی.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from db.models import (
    AIInsight,
    WorkFront,
    WorkTeam,
    SiteMachine,
    Weld,
    NDTRecord,
    PunchItem,
    TestPackage,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Insight Classifications
# ──────────────────────────────────────────────

class AIMode(str, Enum):
    HYBRID = "hybrid"          # Implementation note.
    LOCAL_ONLY = "local"      # Implementation note.
    CLOUD_ONLY = "cloud"      # Implementation note.


class InsightSeverity(str, Enum):
    CRITICAL = "CRITICAL"      # Implementation note.
    HIGH = "HIGH"              # Implementation note.
    MEDIUM = "MEDIUM"          # Implementation note.
    LOW = "LOW"                # Implementation note.
    INFO = "INFO"              # Implementation note.


class InsightCategory(str, Enum):
    DISPATCH = "DISPATCH"              # Implementation note.
    CONSTRAINT = "CONSTRAINT"          # Implementation note.
    QUALITY_NDT = "QUALITY_NDT"        # Implementation note.
    TURNOVER = "TURNOVER"              # Implementation note.
    PRODUCTIVITY = "PRODUCTIVITY"      # Implementation note.


# ──────────────────────────────────────────────
#  Resilient Cloud LLM Client
# ──────────────────────────────────────────────

class ResilientLLMClient:
    """کلاینت مقاوم جهت برقراری ارتباط پایدار با سرویس‌های ابری هوش مصنوعی"""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: int = 35,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        # Implementation note.
        self.session = requests.Session()
        retries = Retry(
            total=max_retries,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def generate_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 1500,
    ) -> str:
        """ارسال پرامپت مهندسی و دریافت پاسخ با مدیریت کامل خطاها"""
        if not self.api_key:
            raise ValueError("OpenAI API Key is missing.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        url = f"{self.base_url}/chat/completions"
        response = self.session.post(url, headers=headers, json=payload, timeout=self.timeout)
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


# ──────────────────────────────────────────────
#  AIAssistantService Implementation
# ──────────────────────────────────────────────

class AIAssistantService:
    """
    سرویس جامع هوش مصنوعی هیبریدی برای کنترل هوشمند پروژه‌های پایپینگ و QA/QC
    """

    SYSTEM_PROMPT = (
        "You are PipeAgent AI, an auditable industrial piping project-control assistant.\n"
        "Your core objectives: enforce engineering standards (ASME B31.3 / ASME Sec IX / API 598), "
        "identify site bottlenecks, recommend optimal crew dispatching, and prevent quality defects.\n\n"
        "Strict Guidelines:\n"
        "1. Never invent or hallucinate project figures, joint numbers, or weld statistics.\n"
        "2. Ground every conclusion strictly in the provided project context.\n"
        "3. Explicitly distinguish between 'OBSERVED EVIDENCE' (facts) and 'RECOMMENDED ACTION' (prescriptive).\n"
        "4. Highlight critical safety & quality blockers (e.g., Cat-A punches, unverified hydrotests) with high urgency."
    )

    def __init__(
        self,
        db=None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        mode: Optional[str] = None,
    ):
        self.db = db

        # Implementation note.
        try:
            cfg = __import__("config")
        except ImportError:
            cfg = None

        self.api_key = api_key or (getattr(cfg, "OPENAI_API_KEY", "") if cfg else "")
        self.model = model or (getattr(cfg, "AI_MODEL", "gpt-4o-mini") if cfg else "gpt-4o-mini")
        
        mode_val = mode or (getattr(cfg, "AI_MODE", "hybrid") if cfg else "hybrid")
        self.mode = AIMode(mode_val.lower()) if mode_val in [m.value for m in AIMode] else AIMode.HYBRID

        self.llm_client = ResilientLLMClient(api_key=self.api_key, model=self.model) if self.api_key else None

    # Implementation note.

    def ask(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        force_local: bool = False,
    ) -> str:
        """
        پاسخ‌دهی به پرسش‌های کاربر:
        ابتدا پاسخ تحلیلی قطعی محلی تولید می‌شود؛ سپس در صورت فعال بودن مود ابری،
        پاسخ نهایی توسط مدل زبانی همراه با زمینه مهندسی تقویت می‌گردد.
        """
        clean_context = context or {}
        local_analysis = self.local_answer(prompt, clean_context)

        # Implementation note.
        if force_local or self.mode == AIMode.LOCAL_ONLY or not self.llm_client:
            return local_analysis

        try:
            user_message = (
                f"USER QUERY: {prompt}\n\n"
                f"=== STRUCTURED PROJECT EVIDENCE ===\n"
                f"{json.dumps(clean_context, indent=2, default=str, ensure_ascii=False)}\n\n"
                f"=== DETERMINISTIC LOCAL ENGINE ASSESSMENT ===\n"
                f"{local_analysis}\n\n"
                f"Based on the above facts, provide a concise, high-impact executive response."
            )

            cloud_response = self.llm_client.generate_completion(
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=user_message,
            )
            return cloud_response

        except Exception as exc:
            logger.warning(f"Cloud AI unavailable ({exc}); falling back to deterministic local intelligence.")
            return (
                f"{local_analysis}\n\n"
                f"──────────────────────────────────────────────\n"
                f"ℹ️ [Cloud AI offline; deterministic site intelligence engine used.]"
            )

    # Implementation note.

    def local_answer(self, prompt: str, context: Dict[str, Any]) -> str:
        """تحلیل هوشمند و قانون‌محور داده‌ها بر اساس الگوهای مهندسی سایت"""
        p = prompt.lower()

        # Implementation note.
        if any(term in p for term in ["work front", "front", "dispatch", "idle", "crew", "machine", "بیکار", "جبهه"]):
            return self._analyze_work_front_status(context)

        # Implementation note.
        if any(term in p for term in ["weld", "welder", "ndt", "rt", "repair", "dia-inch", "جوش", "رادیوگرافی"]):
            return self._analyze_welding_ndt_dynamics(context)

        # Implementation note.
        if any(term in p for term in ["turnover", "handover", "dossier", "punch", "hydro", "mc", "پکیج", "پانچ"]):
            return self._analyze_turnover_readiness(context)

        # Implementation note.
        return self._generate_generic_executive_summary(context)

    def _analyze_work_front_status(self, ctx: Dict[str, Any]) -> str:
        ready = ctx.get("ready_fronts", ctx.get("ready", 0))
        unassigned = ctx.get("unassigned_ready", 0)
        blocked = ctx.get("blocked_fronts", ctx.get("blocked", 0))
        idle_crews = ctx.get("idle_crews_count", 0)

        findings = [
            f"• Available Ready Fronts: {ready}",
            f"• Unassigned Ready Work: {unassigned}",
            f"• Blocked Fronts (Constraints): {blocked}",
            f"• Idle Crews / Machines: {idle_crews}",
        ]

        recommendations = []
        if unassigned > 0:
            recommendations.append(f"Immediate Action: Dispatch {unassigned} ready front(s) to suitable idle crews.")
        if blocked > 0:
            recommendations.append(f"Constraint Mitigation: Resolve material/permit holds on {blocked} blocked front(s) to avoid future delays.")
        if not recommendations:
            recommendations.append("Site Status: Resource allocation and work fronts are currently balanced.")

        return "📊 WORK FRONT & DISPATCH ASSESSMENT:\n" + "\n".join(findings) + "\n\n💡 RECOMMENDED NEXT ACTIONS:\n" + "\n".join(recommendations)

    def _analyze_welding_ndt_dynamics(self, ctx: Dict[str, Any]) -> str:
        total_welds = ctx.get("welds_total", 0)
        welded_completed = ctx.get("welds_completed", ctx.get("welds_accepted", 0))
        awaiting_ndt = ctx.get("awaiting_ndt", 0)
        repair_rate = ctx.get("welder_repair_rate_pct", 0.0)

        findings = [
            f"• Total Joints: {total_welds} | Completed: {welded_completed}",
            f"• NDT Queue Backlog: {awaiting_ndt} joints awaiting inspection",
            f"• Project Weld Repair Rate: {repair_rate}%",
        ]

        recommendations = []
        if awaiting_ndt > 20:
            recommendations.append(f"Critical Bottleneck: High NDT backlog ({awaiting_ndt} welds). Mobilize additional RT/PAUT crews to clear queue.")
        if repair_rate > 5.0:
            recommendations.append(f"Quality Alert: Repair rate ({repair_rate}%) exceeds standard 5% limit. Audit welder qualifications and WPS compliance.")
        if not recommendations:
            recommendations.append("Quality Status: Welding execution and NDT clearance rate are within acceptable thresholds.")

        return "🔬 WELDING & QA/QC DYNAMICS:\n" + "\n".join(findings) + "\n\n💡 RECOMMENDED NEXT ACTIONS:\n" + "\n".join(recommendations)

    def _analyze_turnover_readiness(self, ctx: Dict[str, Any]) -> str:
        completeness = ctx.get("completeness_pct", "N/A")
        open_cat_a = ctx.get("open_cat_a_punches", 0)
        open_cat_b = ctx.get("open_cat_b_punches", 0)
        test_packs_ready = ctx.get("test_packages_ready", 0)

        findings = [
            f"• Dossier Completeness: {completeness}%",
            f"• Blocking Cat-A Punches: {open_cat_a} (Zero tolerance before Hydrotest/MC)",
            f"• Non-blocking Cat-B Punches: {open_cat_b}",
            f"• Test Packages Ready for Execution: {test_packs_ready}",
        ]

        recommendations = []
        if open_cat_a > 0:
            recommendations.append(f"Safety Gatekeeper: {open_cat_a} Category-A punch items MUST be cleared before hydrotesting or MC handover.")
        if test_packs_ready > 0:
            recommendations.append(f"Turnover Priority: Coordinate joint QC/Client walkdown for {test_packs_ready} ready test packages.")

        return "📋 SYSTEM TURNOVER & DOSSIER READINESS:\n" + "\n".join(findings) + "\n\n💡 RECOMMENDED NEXT ACTIONS:\n" + "\n".join(recommendations)

    def _generate_generic_executive_summary(self, ctx: Dict[str, Any]) -> str:
        return (
            "📌 SITE INTELLIGENCE COCKPIT:\n"
            "PipeAgent AI engine active. Provide specific parameters or query topics "
            "(e.g., Work Front Bottlenecks, Welding NDT Queue, Hydrotest Turnover) for prescriptive recommendations."
        )

    # Implementation note.

    def generate_project_insights(self, project_id: int) -> List[Dict[str, Any]]:
        """
        اسکن کامل پروژه و تولید بینش‌های ساختاریافته در قالب یک تراکنش اتمیک (Single Transaction)
        """
        if not self.db:
            logger.warning("DatabaseManager instance not provided to AIAssistantService.")
            return []

        generated_insights: List[Dict[str, Any]] = []

        with self.db.session_scope() as session:
            # Implementation note.
            unassigned_count = session.query(WorkFront).filter(
                WorkFront.project_id == project_id,
                WorkFront.status == "READY",
                WorkFront.assigned_team_id.is_(None),
            ).count() if "work_fronts" in session.get_bind().table_names() else 0

            blocked_count = session.query(WorkFront).filter(
                WorkFront.project_id == project_id,
                WorkFront.status == "BLOCKED",
            ).count() if "work_fronts" in session.get_bind().table_names() else 0

            if unassigned_count > 0:
                insight = self._persist_insight(
                    session=session,
                    project_id=project_id,
                    category=InsightCategory.DISPATCH,
                    severity=InsightSeverity.HIGH,
                    title="Ready Work Awaiting Crew Dispatch",
                    recommendation=f"Assign available crews to {unassigned_count} ready work front(s) to avoid labor idle time.",
                    evidence={"unassigned_ready_fronts": unassigned_count},
                )
                generated_insights.append(insight)

            if blocked_count > 0:
                insight = self._persist_insight(
                    session=session,
                    project_id=project_id,
                    category=InsightCategory.CONSTRAINT,
                    severity=InsightSeverity.HIGH,
                    title="Work Fronts Blocked by Site Constraints",
                    recommendation=f"{blocked_count} front(s) are blocked by material or access holds. Review Constraint Radar immediately.",
                    evidence={"blocked_fronts_count": blocked_count},
                )
                generated_insights.append(insight)

            # Implementation note.
            open_cat_a = session.query(PunchItem).filter(
                PunchItem.project_id == project_id,
                PunchItem.category == "A",
                PunchItem.status.notin_(["QC_CLEARED", "CLIENT_ACCEPTED", "CANCELLED"]),
            ).count() if "punch_items" in session.get_bind().table_names() else 0

            if open_cat_a > 0:
                insight = self._persist_insight(
                    session=session,
                    project_id=project_id,
                    category=InsightCategory.TURNOVER,
                    severity=InsightSeverity.CRITICAL,
                    title="Critical Category-A Punches Blocking Hydrotest",
                    recommendation=f"{open_cat_a} open Category-A punch item(s) are actively blocking hydrotests and mechanical completion.",
                    evidence={"blocking_cat_a_count": open_cat_a},
                )
                generated_insights.append(insight)

            # Implementation note.
            awaiting_ndt = session.query(Weld).filter(
                Weld.project_id == project_id,
                Weld.status == "NDT_REQUESTED",
            ).count() if "weld_joints" in session.get_bind().table_names() else 0

            if awaiting_ndt >= 15:
                insight = self._persist_insight(
                    session=session,
                    project_id=project_id,
                    category=InsightCategory.QUALITY_NDT,
                    severity=InsightSeverity.HIGH,
                    title="Accumulating NDT Inspection Backlog",
                    recommendation=f"{awaiting_ndt} joints are waiting for NDT inspection. Increase radiography shifts to prevent testing bottlenecks.",
                    evidence={"joints_awaiting_ndt": awaiting_ndt},
                )
                generated_insights.append(insight)

        return generated_insights

    def _persist_insight(
        self,
        session,
        project_id: int,
        category: InsightCategory,
        severity: InsightSeverity,
        title: str,
        recommendation: str,
        evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        """ذخیره رکورد بینش در دیتابیس در همان سشن مشترک (بدون ایجاد سربار شبکه)"""
        insight_obj = AIInsight(
            project_id=project_id,
            insight_type=category.value,
            severity=severity.value,
            title=title.strip(),
            recommendation=recommendation.strip(),
            evidence_json=json.dumps(evidence, default=str),
            model_source="hybrid-pipeagent-engine",
            created_at=datetime.utcnow() if hasattr(AIInsight, "created_at") else None,
        )
        session.add(insight_obj)
        session.flush()  # Implementation note.

        return {
            "id": getattr(insight_obj, "id", None),
            "project_id": project_id,
            "category": category.value,
            "severity": severity.value,
            "title": title,
            "recommendation": recommendation,
            "evidence": evidence,
        }