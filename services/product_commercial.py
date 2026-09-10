# -*- coding: utf-8 -*-
"""
services/commercial.py – PipeAgent
Commercial licensing, quota, value modeling, and ROI engine.
Includes plan quota limits, P10/P50/P90 scenario analysis,
multi-currency support, SVG reporting, and smart upgrade recommendations.
"""

from __future__ import annotations

import html
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from config import (
    APP_NAME,
    APP_VERSION,
    BRAND_TAGLINE,
    EXPORT_DIR,
    PRODUCT_POSITIONING,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Commercial Constants
# ──────────────────────────────────────────────

class PlanCode(str, Enum):
    PILOT = "pilot"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    AED = "AED"
    SAR = "SAR"
    IRR = "IRR"


# Implementation note.
FX_RATES_TO_USD: Dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "AED": 0.2722,
    "SAR": 0.2667,
    "IRR": 0.0000238,  # Implementation note.
}


# ──────────────────────────────────────────────
#  Plan & Quantitative Entitlements
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class PlanEntitlements:
    """Quota limits and technical entitlements for each subscription tier"""
    max_projects: int                          # Implementation note.
    max_field_users: int                       # Implementation note.
    max_weld_records_per_month: int            # Implementation note.
    max_storage_gb: float                      # Implementation note.
    api_access: bool                           # Implementation note.
    bim_ifc_import: bool                       # Implementation note.
    erp_integration: bool                      # Implementation note.
    ai_intelligence: bool                      # Implementation note.
    digital_turnover: bool                     # Implementation note.
    sso_saml: bool                             # Implementation note.
    custom_branding: bool                      # Implementation note.
    support_tier: str                          # Implementation note.


@dataclass(frozen=True)
class Plan:
    """Define a complete commercial plan"""
    code: str
    name: str
    audience: str
    billing: str
    summary: str
    entitlements: PlanEntitlements
    platform: bool = True
    field_ops: bool = True
    intelligence: bool = False
    turnover: bool = False
    integrations: bool = False
    multi_project: bool = False
    sso: bool = False
    support: str = "Standard"


PLANS: Dict[str, Plan] = {
    PlanCode.PILOT.value: Plan(
        code="pilot",
        name="Pilot / Evaluation",
        audience="Pilot projects and initial evaluation",
        billing="Fixed 90-day evaluation period",
        summary="Evaluate execution visibility, field tablet synchronization, and operational value on a single project.",
        entitlements=PlanEntitlements(
            max_projects=1, max_field_users=5, max_weld_records_per_month=2000,
            max_storage_gb=5.0, api_access=False, bim_ifc_import=False,
            erp_integration=False, ai_intelligence=False, digital_turnover=False,
            sso_saml=False, custom_branding=False, support_tier="Email support with a 48-hour response target",
        ),
        platform=True, field_ops=True, intelligence=False, turnover=False,
        integrations=False, multi_project=False, sso=False, support="Standard Email",
    ),
    PlanCode.PROFESSIONAL.value: Plan(
        code="professional",
        name="Professional Project",
        audience="Mid-size projects and single-project EPC megaprojects",
        billing="Annual subscription",
        summary="Full piping execution operations with offline field workflows, NDT quality intelligence, and digital turnover.",
        entitlements=PlanEntitlements(
            max_projects=3, max_field_users=25, max_weld_records_per_month=50000,
            max_storage_gb=100.0, api_access=True, bim_ifc_import=True,
            erp_integration=False, ai_intelligence=True, digital_turnover=True,
            sso_saml=False, custom_branding=False, support_tier="Business-hours support with an 8-hour response target",
        ),
        platform=True, field_ops=True, intelligence=True, turnover=True,
        integrations=False, multi_project=False, sso=False, support="Business Hours",
    ),
    PlanCode.ENTERPRISE.value: Plan(
        code="enterprise",
        name="Enterprise Multi-Project",
        audience="Large groups, major EPC contractors, and energy owners",
        billing="Annual enterprise agreement",
        summary="Enterprise execution intelligence, ERP and BIM integration, advanced SSO security, and dedicated 24/7 support.",
        entitlements=PlanEntitlements(
            max_projects=999, max_field_users=999, max_weld_records_per_month=999999,
            max_storage_gb=2000.0, api_access=True, bim_ifc_import=True,
            erp_integration=True, ai_intelligence=True, digital_turnover=True,
            sso_saml=True, custom_branding=True, support_tier="Dedicated 24/7 support with a one-hour SLA",
        ),
        platform=True, field_ops=True, intelligence=True, turnover=True,
        integrations=True, multi_project=True, sso=True, support="Priority / 24-7 SLA",
    ),
}


COMMERCIAL_PRINCIPLES = [
    "Platform subscription + field seats + intelligence and integration modules",
    "No per-weld charging (customers should not be penalized for higher production output)",
    "Engineering and implementation services are quoted transparently rather than hidden inside software fees",
    "ROI reporting is evidence-based and uses transparent probability scenarios",
    "Human approval remains mandatory for critical engineering and QA/QC decisions",
]


# ──────────────────────────────────────────────
#  Plan Helpers & Quota Checks
# ──────────────────────────────────────────────

def plan_for_license_type(license_type: str) -> str:
    """Map an active license key to a commercial plan code"""
    mapping = {
        "trial": PlanCode.PILOT.value,
        "3month": PlanCode.PILOT.value,
        "6month": PlanCode.PROFESSIONAL.value,
        "1year": PlanCode.PROFESSIONAL.value,
        "unlimited": PlanCode.ENTERPRISE.value,
    }
    return mapping.get(license_type, PlanCode.PILOT.value)


def plan_for_license_info(info: Dict[str, Any]) -> Plan:
    """Get the active commercial plan from current license data"""
    return PLANS[plan_for_license_type(str(info.get("type", "trial")))]


def plan_catalog() -> List[Dict[str, Any]]:
    """Public plan catalog for UI presentation"""
    return [asdict(p) for p in PLANS.values()]


def has_feature(license_info: Dict[str, Any], feature_name: str) -> bool:
    """Check feature access using the active license"""
    plan = plan_for_license_info(license_info)
    # Implementation note.
    if hasattr(plan, feature_name):
        return bool(getattr(plan, feature_name))
    if hasattr(plan.entitlements, feature_name):
        return bool(getattr(plan.entitlements, feature_name))
    return False


def get_upgrade_advisor(
    license_info: Dict[str, Any],
    usage_metrics: Dict[str, float],
) -> Optional[Dict[str, Any]]:
    """
    Analyze usage and recommend an upgrade when resource utilization exceeds 80%
    """
    plan = plan_for_license_info(license_info)
    if plan.code == PlanCode.ENTERPRISE.value:
        return None

    ent = plan.entitlements
    limits = {
        "active_projects": (usage_metrics.get("active_projects", 0), ent.max_projects),
        "field_users": (usage_metrics.get("field_users", 0), ent.max_field_users),
        "storage_gb": (usage_metrics.get("storage_gb", 0), ent.max_storage_gb),
    }

    near_capacity_warnings = []
    for metric_name, (current, maximum) in limits.items():
        if maximum > 0 and current >= (maximum * 0.80):
            near_capacity_warnings.append({
                "metric": metric_name,
                "current_usage": current,
                "quota_limit": maximum,
                "utilization_pct": round((current / maximum * 100), 1),
            })

    if not near_capacity_warnings:
        return None

    target_plan = PLANS[PlanCode.ENTERPRISE.value] if plan.code == PlanCode.PROFESSIONAL.value else PLANS[PlanCode.PROFESSIONAL.value]

    return {
        "current_plan_name": plan.name,
        "recommended_upgrade_plan": target_plan.name,
        "recommended_plan_code": target_plan.code,
        "warnings": near_capacity_warnings,
        "upgrade_benefit": target_plan.summary,
    }


# ──────────────────────────────────────────────
#  Value / ROI Modeling Engine
# ──────────────────────────────────────────────

class ValueEngine:
    """
    Economic value and ROI modeling engine using P10/P50/P90 scenarios
    """

    def __init__(self, db):
        self.db = db

    def calculate(
        self,
        project_id: int,
        *,
        hourly_admin_cost: float = 35.0,
        rework_cost_per_weld: float = 1200.0,
        delay_day_cost: float = 5000.0,
        evidence_hours_saved_per_week: float = 8.0,
        currency: Union[Currency, str] = Currency.USD,
    ) -> Dict[str, Any]:
        """
        Calculate financial value opportunities from rework reduction, audit-time reduction, and constraint removal
        with separate conservative (P10), likely (P50), and optimistic (P90) outputs.
        """
        from services.reporting_service import ReportingService
        from services.execution_os_service import ExecutionOSService
        from db.models import PredictionRun

        report = ReportingService(self.db)
        analytics = report.analytics(project_id)
        os_snapshot = ExecutionOSService(self.db).snapshot(project_id)

        with self.db.session_scope() as s:
            latest_prediction = (
                s.query(PredictionRun)
                .filter(PredictionRun.project_id == project_id)
                .order_by(
                    PredictionRun.created_at.desc()
                    if hasattr(PredictionRun, "created_at")
                    else PredictionRun.id.desc()
                )
                .first()
            )

        # Implementation note.
        repaired_welds = float(analytics.get("repair_count", analytics.get("repaired_welds", 0)) or 0)
        docs_count = float(analytics.get("documents", analytics.get("documents_count", 0)) or 0)

        # Implementation note.
        bottleneck_data = os_snapshot.get("predictive_bottleneck", {})
        blocked_fronts = float(bottleneck_data.get("value", 0) or 0)
        if blocked_fronts == 0:
            signals = bottleneck_data.get("signals", [])
            blocked_fronts = sum(
                float(sig.get("value", 0))
                for sig in signals
                if sig.get("category") == "FIELD CONSTRAINT"
            )

        persistent = os_snapshot.get("persistent_control", {})
        open_impacts = float(persistent.get("active_impact_alerts_count", persistent.get("open_impacts", 0)) or 0)

        # Implementation note.
        scenarios = self._compute_scenarios(
            repaired=repaired_welds,
            docs=docs_count,
            blocked=blocked_fronts,
            impacts=open_impacts,
            hourly_admin_cost=hourly_admin_cost,
            rework_cost=rework_cost_per_weld,
            delay_day_cost=delay_day_cost,
            evidence_hours_saved=evidence_hours_saved_per_week,
        )

        data_quality = 0.0
        if latest_prediction:
            data_quality = float(
                getattr(latest_prediction, "data_quality_score", 0)
                or getattr(latest_prediction, "confidence", 0)
                or 0
            )

        # Implementation note.
        curr_str = currency.value if isinstance(currency, Currency) else str(currency).upper()
        fx_rate = FX_RATES_TO_USD.get(curr_str, 1.0)

        def to_curr(val_usd: float) -> float:
            return round(val_usd / fx_rate, 2) if fx_rate else round(val_usd, 2)

        result_payload = {
            "calculation_id": str(uuid.uuid4()),
            "generated_at": datetime.utcnow().isoformat(),
            "project_id": project_id,
            "currency": curr_str,
            "economic_parameters": {
                "hourly_admin_cost_usd": hourly_admin_cost,
                "rework_cost_per_weld_usd": rework_cost_per_weld,
                "delay_day_cost_usd": delay_day_cost,
                "evidence_hours_saved_per_week": evidence_hours_saved_per_week,
                "exchange_rate_to_usd": fx_rate,
            },
            "observed_indicators": {
                "recorded_repair_events": int(repaired_welds),
                "managed_engineering_documents": int(docs_count),
                "blocked_constrained_fronts": int(blocked_fronts),
                "active_downstream_impacts": int(open_impacts),
                "prediction_data_quality_score": round(data_quality, 1),
            },
            "opportunity_scenarios": {
                "p10_conservative": {k: to_curr(v) for k, v in scenarios["p10"].items()},
                "p50_expected": {k: to_curr(v) for k, v in scenarios["p50"].items()},
                "p90_optimistic": {k: to_curr(v) for k, v in scenarios["p90"].items()},
            },
            "commercial_disclaimer": (
                "This estimate represents operational value potential only and is not a contractual commitment or profit guarantee. "
                "Before commercial negotiations, economic parameters should be validated against the customer project accounting model. "
                "PipeAgent does not charge based on the number of welds."
            ),
        }

        # Implementation note.
        self._audit_log_calculation(project_id, result_payload)

        return result_payload

    def _compute_scenarios(
        self,
        repaired: float,
        docs: float,
        blocked: float,
        impacts: float,
        hourly_admin_cost: float,
        rework_cost: float,
        delay_day_cost: float,
        evidence_hours_saved: float,
    ) -> Dict[str, Dict[str, float]]:
        """Calculate value using three risk factors"""
        configs = {
            "p10": {"admin_wks": 36, "rework_factor": 0.02, "constraint_factor": 0.10, "doc_val": 1.0},
            "p50": {"admin_wks": 52, "rework_factor": 0.05, "constraint_factor": 0.25, "doc_val": 2.0},
            "p90": {"admin_wks": 52, "rework_factor": 0.10, "constraint_factor": 0.45, "doc_val": 3.5},
        }

        scenarios = {}
        for sc_key, cfg in configs.items():
            admin_eff = evidence_hours_saved * cfg["admin_wks"] * hourly_admin_cost
            rework_opp = repaired * rework_cost * cfg["rework_factor"]
            constraint_opp = min(blocked, 12) * delay_day_cost * cfg["constraint_factor"]
            evidence_val = min(docs, 3000) * cfg["doc_val"]
            total = admin_eff + rework_opp + constraint_opp + evidence_val

            scenarios[sc_key] = {
                "administrative_efficiency": round(admin_eff, 2),
                "rework_prevention_opportunity": round(rework_opp, 2),
                "constraint_mitigation_opportunity": round(constraint_opp, 2),
                "evidence_traceability_value": round(evidence_val, 2),
                "total_indicated_value": round(total, 2),
            }

        return scenarios

    def _audit_log_calculation(self, project_id: int, payload: Dict[str, Any]) -> None:
        """Store ROI calculation audit records in JSON"""
        try:
            audit_dir = EXPORT_DIR / "commercial_audit"
            audit_dir.mkdir(parents=True, exist_ok=True)
            log_file = audit_dir / f"ROI_P{project_id}_{date.today().isoformat()}.json"
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str, ensure_ascii=False)
        except Exception as err:
            logger.warning(f"Failed to record commercial audit log: {err}")

    # Implementation note.

    def export_html(
        self,
        project_id: int,
        *,
        filename: Optional[str] = None,
        currency: Union[Currency, str] = Currency.USD,
        client_name: str = "",
    ) -> str:
        """Generate an offline executive ROI report with an inline SVG bar chart"""
        data = self.calculate(project_id, currency=currency)
        out_path = EXPORT_DIR / (
            filename or f"PipeAgent_ROI_Report_P{project_id}_{date.today().isoformat()}.html"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)

        curr = data["currency"]
        scenarios = data["opportunity_scenarios"]
        p50 = scenarios["p50_expected"]
        indicators = data["observed_indicators"]

        svg_chart = self._generate_svg_chart(scenarios, curr)

        val_rows = "".join(
            f"<tr><td>{html.escape(k.replace('_', ' ').title())}</td>"
            f"<td style='text-align:right;font-weight:700;color:#123047'>{curr} {v:,.2f}</td></tr>"
            for k, v in p50.items()
        )

        ind_rows = "".join(
            f"<tr><td>{html.escape(k.replace('_', ' ').title())}</td>"
            f"<td style='text-align:right;font-weight:600'>{html.escape(str(v))}</td></tr>"
            for k, v in indicators.items()
        )

        client_tag = f"<div style='color:#347fa8;font-size:14px;margin-bottom:8px'>Prepared for: <strong>{html.escape(client_name)}</strong></div>" if client_name else ""

        html_doc = f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<title>Economic Value and ROI Report – {html.escape(APP_NAME)}</title>
<style>
@page {{ size: A4; margin: 15mm; }}
body {{ font-family: 'Segoe UI', Tahoma, Arial, sans-serif; color: #172b3a; background: #fff; max-width: 820px; margin: 0 auto; padding: 25px; line-height: 1.6; }}
.header {{ border-bottom: 2px solid #123047; padding-bottom: 12px; margin-bottom: 20px; }}
.app-tag {{ font-size: 13px; color: #347fa8; font-weight: bold; letter-spacing: 0.5px; }}
h1 {{ color: #123047; margin: 5px 0; font-size: 24px; }}
.hero-box {{ background: linear-gradient(135deg, #f0f7fa, #e3eff5); border: 1px solid #b8dbe8; border-radius: 12px; padding: 22px; text-align: center; margin: 20px 0; }}
.hero-box h2 {{ margin: 0 0 6px 0; font-size: 16px; color: #123047; }}
.big-val {{ font-size: 38px; font-weight: 900; color: #0d7a3e; margin: 5px 0; }}
.range-text {{ font-size: 13px; color: #486581; }}
table {{ width: 100%; border-collapse: collapse; margin: 18px 0; }}
th, td {{ border: 1px solid #d8e2e8; padding: 10px 12px; text-align: right; font-size: 13px; }}
th {{ background: #eef5f8; color: #123047; font-weight: bold; }}
.chart-container {{ background: #fafbfc; border: 1px solid #e1e8ed; border-radius: 8px; padding: 15px; margin: 20px 0; text-align: center; }}
.principles {{ background: #fffde6; border: 1px solid #fae69e; border-radius: 8px; padding: 15px; margin: 20px 0; }}
.principles ul {{ margin: 5px 0 0 20px; padding: 0; }}
.principles li {{ font-size: 12px; color: #5c4e00; margin-bottom: 4px; }}
.disclaimer {{ font-size: 11px; color: #627d98; margin-top: 25px; border-top: 1px solid #d8e2e8; padding-top: 10px; }}
</style>
</head>
<body>

<div class="header">
  <div class="app-tag">{html.escape(APP_NAME)} · {html.escape(APP_VERSION)}</div>
  <h1>Operational Value and ROI Report (Executive ROI)</h1>
  <p style="margin:2px 0;color:#627d98;font-size:13px">{html.escape(BRAND_TAGLINE)}</p>
  {client_tag}
</div>

<div class="hero-box">
  <h2>Estimated Annual Value (Likely P50 Scenario)</h2>
  <div class="big-val">{curr} {p50['total_indicated_value']:,.2f}</div>
  <div class="range-text">
    Probability range: {curr} {scenarios['p10_conservative']['total_indicated_value']:,.2f} (Conservative)
    تا {curr} {scenarios['p90_optimistic']['total_indicated_value']:,.2f} (Optimistic)
  </div>
</div>

<h3 style="color:#123047;border-bottom:1px solid #eef5f8;padding-bottom:5px">Visual Comparison of ROI Scenarios</h3>
<div class="chart-container">
  {svg_chart}
</div>

<h3 style="color:#123047;border-bottom:1px solid #eef5f8;padding-bottom:5px">Financial Savings Opportunities (P50 Expected)</h3>
<table>
  <thead>
    <tr><th>Value Category</th><th style="text-align:right">Estimated Value ({curr})</th></tr>
  </thead>
  <tbody>
    {val_rows}
  </tbody>
</table>

<h3 style="color:#123047;border-bottom:1px solid #eef5f8;padding-bottom:5px">Observed Operational Indicators and Evidence</h3>
<table>
  <thead>
    <tr><th>Operational Indicator</th><th style="text-align:right">Recorded Value</th></tr>
  </thead>
  <tbody>
    {ind_rows}
  </tbody>
</table>

<div class="principles">
  <strong>PipeAgent Commercial Principles:</strong>
  <ul>
    {''.join(f"<li>{html.escape(p)}</li>" for p in COMMERCIAL_PRINCIPLES)}
  </ul>
</div>

<div class="disclaimer">
  <strong>Commercial Disclaimer:</strong> {html.escape(data['commercial_disclaimer'])}<br>
  Calculation ID: {data['calculation_id']} | Issued: {data['generated_at'][:10]}
</div>

</body>
</html>"""

        out_path.write_text(html_doc, encoding="utf-8")
        logger.info(f"Commercial Value HTML report exported to: {out_path}")
        return str(out_path)

    def _generate_svg_chart(self, scenarios: Dict[str, Dict[str, float]], currency: str) -> str:
        """Build a comparative SVG bar chart with category colors"""
        metrics = [
            ("Audit Efficiency", "administrative_efficiency", "#347fa8"),
            ("Rework Prevention", "rework_prevention_opportunity", "#e8853d"),
            ("Constraint Mitigation", "constraint_mitigation_opportunity", "#d94f4f"),
            ("Turnover Evidence Value", "evidence_traceability_value", "#2ea86f"),
        ]

        sc_keys = [
            ("P10", "p10_conservative", "#9ecae1"),
            ("P50", "p50_expected", "#3182bd"),
            ("P90", "p90_optimistic", "#08519c"),
        ]

        max_val = max(scenarios[sk]["total_indicated_value"] for _, sk, _ in sc_keys) or 1.0

        bar_w = 42
        group_gap = 25
        plot_h = 160
        chart_w = len(metrics) * (len(sc_keys) * bar_w + group_gap) + 70

        bars = []
        for m_idx, (m_label, m_key, _) in enumerate(metrics):
            for sc_idx, (_, sc_key, sc_color) in enumerate(sc_keys):
                val = scenarios[sc_key].get(m_key, 0.0)
                bh = (val / max_val) * plot_h if max_val > 0 else 0
                x = 50 + m_idx * (len(sc_keys) * bar_w + group_gap) + sc_idx * bar_w
                y = plot_h - bh + 20
                bars.append(f'<rect x="{x}" y="{y}" width="{bar_w - 4}" height="{bh}" fill="{sc_color}" rx="3"/>')
                if bh > 15:
                    bars.append(f'<text x="{x + bar_w/2 - 2}" y="{y - 4}" text-anchor="middle" font-size="9" fill="#333">{val:,.0f}</text>')

            label_center = 50 + m_idx * (len(sc_keys) * bar_w + group_gap) + (len(sc_keys) * bar_w) / 2
            bars.append(f'<text x="{label_center}" y="{plot_h + 38}" text-anchor="middle" font-size="11" fill="#333" font-weight="bold">{m_label}</text>')

        legend = (
            f'<rect x="60" y="215" width="12" height="12" fill="#9ecae1" rx="2"/>'
            f'<text x="80" y="225" font-size="10" fill="#555">P10 Conservative</text>'
            f'<rect x="180" y="215" width="12" height="12" fill="#3182bd" rx="2"/>'
            f'<text x="200" y="225" font-size="10" fill="#555">P50 Likely</text>'
            f'<rect x="270" y="215" width="12" height="12" fill="#08519c" rx="2"/>'
            f'<text x="290" y="225" font-size="10" fill="#555">P90 Optimistic</text>'
        )

        return f"""<svg viewBox="0 0 {chart_w} 240" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:{chart_w}px">
  <line x1="45" y1="20" x2="45" y2="{plot_h + 20}" stroke="#ccd7e0" stroke-width="1"/>
  <line x1="45" y1="{plot_h + 20}" x2="{chart_w}" y2="{plot_h + 20}" stroke="#ccd7e0" stroke-width="1"/>
  {''.join(bars)}
  {legend}
</svg>"""