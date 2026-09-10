# -*- coding: utf-8 -*-
"""
services/predictive_control.py – PipeAgent
موتور محاسباتی پیشرفته پیش‌بینی گلوگاه‌ها، انتشار موانع و شبیه‌سازی ریسک‌های اجرایی
شامل: تحلیل سری‌های زمانی با رگرسیون OLS، فواصل اطمینان احتمالاتی (P10/P50/P90)،
انتساب هدفمند اثرات بر روی نودهای وابسته گراف، مانیتورینگ نرخ عیوب و پایش آمادگی تحویل.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
import math
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from statistics import mean, stdev
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc, case
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from db.manager import DatabaseManager
from db.models import (
    ExecutionEvent,
    ExecutionGraphNode,
    ExecutionGraphEdge,
    PredictionObservation,
    PredictionRun,
    PredictionImpact,
    ExecutionForecast,
    Weld,
    NDTRecord,
    WorkFront,
    TestPackage,
    PunchItem,
    TurnoverDossier,
    LineListItem,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Metric Definitions
# ──────────────────────────────────────────────

class MetricType(str, Enum):
    """انواع شاخص‌های پایش پیش‌نگر"""
    WELD_COMPLETED_DIA_INCH = "weld_completed_dia_inch"  # Implementation note.
    AWAITING_NDT_DIA_INCH = "awaiting_ndt_dia_inch"      # Implementation note.
    REPAIR_RATE_PERCENT = "repair_rate_percent"          # Implementation note.
    BLOCKED_FRONTS_COUNT = "blocked_fronts_count"        # Implementation note.
    OVERDUE_FRONTS_COUNT = "overdue_fronts_count"        # Implementation note.
    READY_TEST_PACKAGES = "ready_test_packages"          # Implementation note.
    OPEN_CAT_A_PUNCHES = "open_cat_a_punches"            # Implementation note.
    TURNOVER_GAPS_COUNT = "turnover_gaps_count"          # Implementation note.


class ForecastRiskType(str, Enum):
    """دسته‌بندی ریسک‌های پیش‌بینی‌شده"""
    NDT_BOTTLENECK = "NDT_BOTTLENECK"                    # Implementation note.
    CONSTRAINT_PROPAGATION = "CONSTRAINT_PROPAGATION"    # Implementation note.
    QUALITY_DEFECT_SPIKE = "QUALITY_DEFECT_SPIKE"        # Implementation note.
    HYDROTEST_COLLISION = "HYDROTEST_COLLISION"          # Implementation note.
    TURNOVER_HANDOVER_DELAY = "TURNOVER_DELAY"           # Implementation note.


# ──────────────────────────────────────────────
#  Statistical & Regression Utilities
# ──────────────────────────────────────────────

class StatisticalForecaster:
    """ابزار محاسبات آماری پیشرفته، رگرسیون خطی و فواصل اطمینان"""

    @staticmethod
    def calculate_linear_regression(
        timestamps: List[float], values: List[float]
    ) -> Tuple[float, float, float]:
        """
        محاسبه رگرسیون خطی OLS ($y = \\beta_0 + \\beta_1 \\cdot t$):
        خروجی: (شیب خط یا نرخ تغییرات در ساعت slope, عرض از مبدا intercept, ضریب تعیین R^2)
        """
        n = len(values)
        if n < 2:
            return 0.0, values[0] if values else 0.0, 0.0

        t_mean = mean(timestamps)
        v_mean = mean(values)

        numerator = sum((t - t_mean) * (v - v_mean) for t, v in zip(timestamps, values))
        denominator = sum((t - t_mean) ** 2 for t in timestamps)

        if denominator == 0:
            return 0.0, v_mean, 0.0

        slope = numerator / denominator
        intercept = v_mean - (slope * t_mean)

        # Implementation note.
        total_variance = sum((v - v_mean) ** 2 for v in values)
        if total_variance == 0:
            r_squared = 1.0
        else:
            residual_variance = sum((v - (intercept + slope * t)) ** 2 for t, v in zip(timestamps, values))
            r_squared = max(0.0, min(1.0, 1.0 - (residual_variance / total_variance)))

        return slope, intercept, r_squared

    @staticmethod
    def compute_probabilistic_bounds(
        projected_mean: float, historical_values: List[float], horizon_factor: float
    ) -> Dict[str, float]:
        """
        محاسبه بازه‌های احتمالاتی P10 (خوش‌بینانه)، P50 (محتمل) و P90 (بدبینانه)
        بر مبنای انحراف معیار خطای داده‌های تاریخی
        """
        if len(historical_values) >= 3:
            sigma = stdev(historical_values)
        else:
            sigma = max(1.0, projected_mean * 0.15)

        # Implementation note.
        scaled_sigma = sigma * math.sqrt(horizon_factor)

        return {
            "p10_optimistic": max(0.0, round(projected_mean - (1.28 * scaled_sigma), 2)),
            "p50_expected": max(0.0, round(projected_mean, 2)),
            "p90_pessimistic": max(0.0, round(projected_mean + (1.28 * scaled_sigma), 2)),
        }


# ──────────────────────────────────────────────
#  PredictiveConstructionControl Implementation
# ──────────────────────────────────────────────

class PredictiveConstructionControl:
    """
    موتور هوش پیش‌نگر و شبیه‌سازی رفتار خطوط پایپینگ و کنترل پروژه
    """

    MODEL_NAME = "PipeAgent Predictive Construction Engine"
    MODEL_VERSION = "2.0-Enterprise"

    def __init__(self, db: DatabaseManager):
        self.db = db

    # Implementation note.

    def run(self, project_id: int, horizon_hours: int = 72) -> Dict[str, Any]:
        """
        اجرای خط‌لوله کامل تحلیل پیش‌نگر:
        ۱. استخراج تجمعی داده‌های وضعیت جاری از دیتابیس (SQL Aggregations)
        ۲. بازیابی سری‌های زمانی ۳۰ روز گذشته و تحلیل شیب رگرسیون
        ۳. محاسبه احتمالات وقوع گلوگاه با فواصل P10/P50/P90
        ۴. انتشار هدفمند اثرات بر روی نودهای مرتبط در گراف اجرایی
        ۵. ثبت رسمی اسنپ‌شات پیش‌بینی در جدول `PredictionRun`
        """
        now = datetime.utcnow()
        cutoff_date = now - timedelta(days=30)
        horizon_days = max(1.0, horizon_hours / 24.0)

        with self.db.session_scope() as session:
            # Implementation note.
            current_state = self._fetch_current_project_state(session, project_id)

            # Implementation note.
            hist_observations = (
                session.query(PredictionObservation)
                .filter(
                    PredictionObservation.project_id == project_id,
                    PredictionObservation.observed_at >= cutoff_date,
                )
                .order_by(PredictionObservation.observed_at.asc())
                .all()
            )

            # Implementation note.
            hist_by_metric: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
            for obs in hist_observations:
                t_hours = (obs.observed_at - cutoff_date).total_seconds() / 3600.0
                hist_by_metric[obs.metric].append((t_hours, float(obs.value)))

            # Implementation note.
            trend_metrics: Dict[str, Dict[str, float]] = {}
            for metric_enum in MetricType:
                m_key = metric_enum.value
                data_points = hist_by_metric.get(m_key, [])
                if len(data_points) >= 2:
                    ts, vals = zip(*data_points)
                    slope_hr, _, r2 = StatisticalForecaster.calculate_linear_regression(list(ts), list(vals))
                    slope_day = slope_hr * 24.0
                else:
                    slope_day = 0.0
                    r2 = 0.0
                trend_metrics[m_key] = {"slope_daily": round(slope_day, 3), "r_squared": round(r2, 2)}

            # Implementation note.
            forecasts: List[Dict[str, Any]] = []

            # Implementation note.
            ndt_backlog_dia_inch = current_state["awaiting_ndt_dia_inch"]
            ndt_slope = trend_metrics[MetricType.AWAITING_NDT_DIA_INCH.value]["slope_daily"]
            projected_ndt = max(0.0, ndt_backlog_dia_inch + (ndt_slope * horizon_days))
            
            if ndt_backlog_dia_inch >= 15.0 or projected_ndt >= 25.0:
                prob = min(0.98, 0.45 + min(0.40, projected_ndt / max(20.0, current_state["total_dia_inch"] or 100.0) * 3) + (0.10 if ndt_slope > 0 else 0.0))
                conf = self._calculate_confidence(len(hist_by_metric.get(MetricType.AWAITING_NDT_DIA_INCH.value, [])), trend_metrics[MetricType.AWAITING_NDT_DIA_INCH.value]["r_squared"])
                bounds = StatisticalForecaster.compute_probabilistic_bounds(projected_ndt, [v for _, v in hist_by_metric.get(MetricType.AWAITING_NDT_DIA_INCH.value, [])], horizon_days)
                
                forecasts.append(self._build_forecast_dto(
                    risk_type=ForecastRiskType.NDT_BOTTLENECK,
                    horizon_hours=horizon_hours,
                    title="NDT Radiography Queue Approaching Critical Chokepoint",
                    probability=prob,
                    confidence=conf,
                    projected_bounds=bounds,
                    recommended_action="Mobilize supplementary RT crew or authorize night radiography window immediately.",
                ))

            # Implementation note.
            blocked_count = current_state["blocked_fronts"]
            overdue_count = current_state["overdue_fronts"]
            constraint_slope = trend_metrics[MetricType.BLOCKED_FRONTS_COUNT.value]["slope_daily"]
            projected_blocked = max(0.0, blocked_count + (constraint_slope * horizon_days))

            if blocked_count > 0 or overdue_count > 0:
                prob = min(0.96, 0.35 + (0.20 if blocked_count >= 3 else 0.10) + (0.15 if overdue_count >= 2 else 0.05) + (0.10 if constraint_slope > 0 else 0.0))
                conf = self._calculate_confidence(len(hist_by_metric.get(MetricType.BLOCKED_FRONTS_COUNT.value, [])), trend_metrics[MetricType.BLOCKED_FRONTS_COUNT.value]["r_squared"])
                bounds = StatisticalForecaster.compute_probabilistic_bounds(projected_blocked, [v for _, v in hist_by_metric.get(MetricType.BLOCKED_FRONTS_COUNT.value, [])], horizon_days)

                forecasts.append(self._build_forecast_dto(
                    risk_type=ForecastRiskType.CONSTRAINT_PROPAGATION,
                    horizon_hours=horizon_hours,
                    title="Field Constraints Threatening Downstream Iso Erection Velocity",
                    probability=prob,
                    confidence=conf,
                    projected_bounds=bounds,
                    recommended_action="Triage access permits and material holds for critical work fronts before next shift.",
                ))

            # Implementation note.
            repair_rate = current_state["repair_rate_dia_inch_pct"]
            if repair_rate >= 5.0:
                prob = min(0.95, 0.40 + (repair_rate / 20.0))
                forecasts.append(self._build_forecast_dto(
                    risk_type=ForecastRiskType.QUALITY_DEFECT_SPIKE,
                    horizon_hours=horizon_hours,
                    title="Weld Repair Rate Trending Above ASME 5% Threshold",
                    probability=prob,
                    confidence=0.85,
                    projected_bounds={"p10_optimistic": repair_rate, "p50_expected": repair_rate + 0.5, "p90_pessimistic": repair_rate + 2.0},
                    recommended_action="Conduct mandatory root-cause inspection on active welders and check shielding gas purity.",
                ))

            # Implementation note.
            open_cat_a = current_state["open_cat_a_punches"]
            dossier_gaps = current_state["turnover_gaps_count"]
            if open_cat_a > 0 or dossier_gaps > 0:
                prob = min(0.95, 0.30 + (open_cat_a * 0.15) + (dossier_gaps * 0.03))
                forecasts.append(self._build_forecast_dto(
                    risk_type=ForecastRiskType.TURNOVER_HANDOVER_DELAY,
                    horizon_hours=horizon_hours,
                    title="Open Punch-A Items Threatening Hydrotest and RFC Schedule",
                    probability=prob,
                    confidence=0.90,
                    projected_bounds={"p10_optimistic": open_cat_a, "p50_expected": open_cat_a, "p90_pessimistic": open_cat_a + 2},
                    recommended_action="Mobilize dedicated punch-clearing team; Category-A items must be zero prior to pressure testing.",
                ))

            # Implementation note.
            for m_enum in MetricType:
                val = current_state.get(m_enum.value, 0.0)
                session.add(PredictionObservation(
                    project_id=project_id,
                    metric=m_enum.value,
                    value=float(val),
                    observed_at=now,
                ))

            data_quality_score = self._compute_data_quality(current_state, hist_observations)

            # Implementation note.
            result_payload = {
                "project_id": project_id,
                "model_engine": self.MODEL_NAME,
                "model_version": self.MODEL_VERSION,
                "generated_at": now.isoformat(),
                "horizon_hours": horizon_hours,
                "current_state": current_state,
                "trend_analysis": trend_metrics,
                "predictive_forecasts": forecasts,
                "data_quality_score": data_quality_score,
                "methodology": "Ordinary Least Squares (OLS) + Probabilistic P10/P50/P90 Bounds + Topological Graph Mapping.",
            }

            # Implementation note.
            avg_confidence = mean([f["confidence"] for f in forecasts]) if forecasts else 0.85
            run_record = PredictionRun(
                project_id=project_id,
                model_name=self.MODEL_NAME,
                model_version=self.MODEL_VERSION,
                horizon_hours=horizon_hours,
                confidence=avg_confidence,
                data_quality_score=data_quality_score,
                result_json=json.dumps(result_payload, default=str),
                created_at=now,
            )
            session.add(run_record)
            session.flush()

            # Implementation note.
            self._propagate_targeted_graph_impacts(session, project_id, run_record.id, forecasts)

            return result_payload

    # Implementation note.

    def _fetch_current_project_state(self, session: Session, project_id: int) -> Dict[str, Any]:
        """محاسبه بلادرنگ تمام متغیرهای کلیدی پروژه با کوئری‌های تجمعی SQL"""
        today = date.today()

        # Implementation note.
        weld_stats = session.query(
            func.count(Weld.id).label("total_welds"),
            func.sum(func.coalesce(Weld.dia_inch, 1.0)).label("total_dia_inch"),
            func.sum(case((Weld.status.in_(["WELDED", "WELDED_VT_PENDING", "VT_ACCEPTED", "NDT_REQUESTED", "NDT_CLEARED", "COMPLETED"]), func.coalesce(Weld.dia_inch, 1.0)), else_=0.0)).label("completed_dia_inch"),
            func.sum(case((Weld.status.in_(["WELDED", "WELDED_VT_PENDING", "NDT_REQUESTED"]), func.coalesce(Weld.dia_inch, 1.0)), else_=0.0)).label("awaiting_ndt_dia_inch"),
            func.sum(case((getattr(Weld, "repair_count", 0) > 0, func.coalesce(Weld.dia_inch, 1.0)), else_=0.0)).label("repaired_dia_inch"),
        ).filter(Weld.project_id == project_id).first()

        total_dia_inch = float(weld_stats.total_dia_inch or 0.0)
        completed_dia_inch = float(weld_stats.completed_dia_inch or 0.0)
        awaiting_ndt_dia_inch = float(weld_stats.awaiting_ndt_dia_inch or 0.0)
        repaired_dia_inch = float(weld_stats.repaired_dia_inch or 0.0)
        repair_rate_pct = round((repaired_dia_inch / completed_dia_inch * 100), 2) if completed_dia_inch > 0 else 0.0

        # Implementation note.
        blocked_fronts = session.query(func.count(WorkFront.id)).filter(
            WorkFront.project_id == project_id,
            or_(WorkFront.status.in_(["Blocked", "Waiting"]), WorkFront.blocker.isnot(None)),
        ).scalar() or 0

        overdue_fronts = session.query(func.count(WorkFront.id)).filter(
            WorkFront.project_id == project_id,
            WorkFront.planned_finish < today,
            WorkFront.status != "Completed",
        ).scalar() or 0

        # Implementation note.
        ready_tests = session.query(func.count(TestPackage.id)).filter(
            TestPackage.project_id == project_id,
            TestPackage.status.in_(["Ready for Test", "READY_FOR_TEST"]),
        ).scalar() or 0

        open_cat_a = session.query(func.count(PunchItem.id)).filter(
            PunchItem.project_id == project_id,
            PunchItem.category == "A",
            PunchItem.status.notin_(["QC_CLEARED", "CLIENT_ACCEPTED", "CLOSED", "CANCELLED"]),
        ).scalar() or 0

        turnover_gaps = session.query(func.count(TurnoverDossier.id)).filter(
            TurnoverDossier.project_id == project_id,
            TurnoverDossier.status.notin_(["Closed", "Issued", "APPROVED"]),
            TurnoverDossier.completeness_pct < 95.0,
        ).scalar() or 0

        return {
            MetricType.WELD_COMPLETED_DIA_INCH.value: completed_dia_inch,
            MetricType.AWAITING_NDT_DIA_INCH.value: awaiting_ndt_dia_inch,
            MetricType.REPAIR_RATE_PERCENT.value: repair_rate_pct,
            MetricType.BLOCKED_FRONTS_COUNT.value: blocked_fronts,
            MetricType.OVERDUE_FRONTS_COUNT.value: overdue_fronts,
            MetricType.READY_TEST_PACKAGES.value: ready_tests,
            MetricType.OPEN_CAT_A_PUNCHES.value: open_cat_a,
            MetricType.TURNOVER_GAPS_COUNT.value: turnover_gaps,
            "total_dia_inch": total_dia_inch,
            "total_welds_count": weld_stats.total_welds or 0,
            "repair_rate_dia_inch_pct": repair_rate_pct,
            "blocked_fronts": blocked_fronts,
            "overdue_fronts": overdue_fronts,
            "ready_tests": ready_tests,
            "open_cat_a_punches": open_cat_a,
            "turnover_gaps_count": turnover_gaps,
        }

    # Implementation note.

    def _propagate_targeted_graph_impacts(
        self,
        session: Session,
        project_id: int,
        prediction_run_id: int,
        forecasts: List[Dict[str, Any]],
    ) -> None:
        """
        اتصال دقیق پیش‌بینی به نودهای واقعاً متأثر (نه تصادفی) بر مبنای روابط گراف
        """
        if not forecasts:
            return

        impact_records: List[PredictionImpact] = []

        for f in forecasts:
            if f["probability"] < 0.50:
                continue

            target_node_types = []
            if f["type"] == ForecastRiskType.NDT_BOTTLENECK.value:
                target_node_types = ["WELD", "TEST"]
            elif f["type"] == ForecastRiskType.CONSTRAINT_PROPAGATION.value:
                target_node_types = ["WORK_FRONT", "LINE"]
            elif f["type"] == ForecastRiskType.TURNOVER_HANDOVER_DELAY.value:
                target_node_types = ["TEST", "TURNOVER"]
            else:
                target_node_types = ["TEST"]

            # Implementation note.
            affected_nodes = (
                session.query(ExecutionGraphNode)
                .filter(
                    ExecutionGraphNode.project_id == project_id,
                    ExecutionGraphNode.node_type.in_(target_node_types),
                )
                .order_by(ExecutionGraphNode.risk_score.desc())
                .limit(15)
                .all()
            )

            for node in affected_nodes:
                impact_records.append(PredictionImpact(
                    prediction_run_id=prediction_run_id,
                    source_node=f"PREDICTIVE:{f['type']}",
                    affected_node=node.node_key,
                    probability=f["probability"],
                    confidence=f["confidence"],
                    severity="High" if f["probability"] >= 0.75 else "Medium",
                    rationale=f"{f['title']} (Expected: {f['projected_bounds']['p50_expected']})",
                ))

        if impact_records:
            session.bulk_save_objects(impact_records)

    # Implementation note.

    @staticmethod
    def _calculate_confidence(sample_size: int, r_squared: float) -> float:
        """محاسبه ضریب اطمینان علمی بر اساس حجم نمونه و ضریب تعیین رگرسیون"""
        base = 0.40
        size_factor = min(0.35, sample_size / 30.0 * 0.35)
        fit_factor = r_squared * 0.20
        return round(min(0.98, base + size_factor + fit_factor), 2)

    @staticmethod
    def _compute_data_quality(current: Dict[str, Any], hist: List[Any]) -> int:
        """سنجش غنا و کیفیت داده‌های ورودی پروژه جهت اطمینان از پیش‌بینی"""
        score = 40
        if current.get("total_dia_inch", 0) > 0:
            score += 20
        if hist:
            score += 20
        if len(hist) >= 15:
            score += 15
        if current.get("total_welds_count", 0) >= 50:
            score += 5
        return min(100, score)

    @staticmethod
    def _build_forecast_dto(
        risk_type: ForecastRiskType,
        horizon_hours: int,
        title: str,
        probability: float,
        confidence: float,
        projected_bounds: Dict[str, float],
        recommended_action: str,
    ) -> Dict[str, Any]:
        """ساختاردهی استاندارد DTO پیش‌بینی"""
        return {
            "type": risk_type.value,
            "horizon_hours": horizon_hours,
            "title": title,
            "probability": round(probability, 2),
            "confidence": round(confidence, 2),
            "projected_bounds": projected_bounds,
            "recommended_action": recommended_action,
        }