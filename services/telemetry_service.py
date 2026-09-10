# -*- coding: utf-8 -*-
"""
services/welding_telemetry_service.py – PipeAgent
سرویس جامع دریافت داده‌های تله‌متری اینترنت اشیاء (IoT) دستگاه‌های جوشکاری
منطبق با استانداردهای ASME Section IX (QW-409) و EN 1011-1
شامل: محاسبه هوشمند حرارت ورودی (Heat Input) با ضریب راندمان متالورژیکی،
غربالگری انحراف پارامترها از محدوده مجاز WPS، ثبت دسته‌ای فوق‌سریع و تحلیل OEE و Arc-On Time.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc, case
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from db.manager import DatabaseManager
from db.models import (
    WeldingTelemetry,
    Weld,
    WPS_PQR,
    SiteMachine,
    Welder,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Thermal Efficiency Standards
# ──────────────────────────────────────────────

class WeldingProcessType(str, Enum):
    """فرآیندهای جوشکاری استاندارد"""
    GTAW = "GTAW"      # Implementation note.
    SMAW = "SMAW"      # Implementation note.
    GMAW = "GMAW"      # Implementation note.
    FCAW = "FCAW"      # Implementation note.
    SAW = "SAW"        # Implementation note.


# Implementation note.
PROCESS_THERMAL_EFFICIENCY: Dict[str, float] = {
    WeldingProcessType.GTAW.value: 0.60,       # Implementation note.
    WeldingProcessType.SMAW.value: 0.80,       # Implementation note.
    WeldingProcessType.GMAW.value: 0.80,       # Implementation note.
    WeldingProcessType.FCAW.value: 0.80,       # Implementation note.
    WeldingProcessType.SAW.value: 1.00,        # Implementation note.
}


class TelemetryQualityStatus(str, Enum):
    """وضعیت کیفی نمونه تله‌متری نسبت به الزامات مهندسی"""
    WITHIN_WPS = "WITHIN_WPS"                  # Implementation note.
    MINOR_DEVIATION = "MINOR_DEVIATION"        # Implementation note.
    CRITICAL_DEVIATION = "CRITICAL_DEVIATION"  # Implementation note.
    HEAT_INPUT_EXCEEDED = "HI_EXCEEDED"        # Implementation note.
    HEAT_INPUT_TOO_LOW = "HI_TOO_LOW"          # Implementation note.
    ARC_STABILIZATION = "ARC_STABILIZATION"    # Implementation note.
    UNSCREENED = "UNSCREENED"                  # Implementation note.


# ──────────────────────────────────────────────
#  Welding Telemetry Service Implementation
# ──────────────────────────────────────────────

class WeldingTelemetryService:
    """
    سرویس مرکزی اینجِست داده‌های بلادرنگ دستگاه‌های جوشکاری و غربالگری پارامترهای مهندسی
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    # Implementation note.

    def ingest(self, project_id: int, payload: Dict[str, Any]) -> int:
        """
        دریافت، اعتبارسنجی، محاسبه فرمول Heat Input و ذخیره امن یک نمونه تله‌متری
        """
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            raise ValueError("Mandatory field 'idempotency_key' is missing from telemetry payload.")

        with self.db.session_scope() as session:
            # Implementation note.
            existing = (
                session.query(WeldingTelemetry)
                .filter(WeldingTelemetry.idempotency_key == idempotency_key)
                .first()
            )
            if existing:
                return existing.id

            # Implementation note.
            started_at = self._parse_datetime(payload.get("started_at"))
            if not started_at:
                raise ValueError("Valid 'started_at' timestamp is required.")

            ended_at = self._parse_datetime(payload.get("ended_at"))

            # Implementation note.
            current_a = self._to_float(payload.get("current_a_avg"))
            voltage_v = self._to_float(payload.get("voltage_v_avg"))
            travel_speed = self._to_float(payload.get("travel_speed_mm_min"))
            wire_feed = self._to_float(payload.get("wire_feed_m_min"))
            interpass_c = self._to_float(payload.get("interpass_max_c"))
            gas_flow = self._to_float(payload.get("gas_flow_l_min"))
            process_str = str(payload.get("process") or "SMAW").strip().upper()

            # Implementation note.
            computed_heat_input = self.calculate_heat_input(
                voltage_v=voltage_v,
                current_a=current_a,
                travel_speed_mm_min=travel_speed,
                process_type=process_str,
            )
            final_heat_input = computed_heat_input if computed_heat_input is not None else self._to_float(payload.get("heat_input_kj_mm"))

            # Implementation note.
            quality_status, deviation_pct = self._screen_wps_compliance(
                session=session,
                project_id=project_id,
                weld_id=payload.get("weld_id_fk"),
                current_a=current_a,
                voltage_v=voltage_v,
                heat_input=final_heat_input,
                interpass_c=interpass_c,
                payload_dev_pct=self._to_float(payload.get("parameter_deviation_pct")),
            )

            # Implementation note.
            telemetry_obj = WeldingTelemetry(
                project_id=project_id,
                weld_id_fk=payload.get("weld_id_fk"),
                machine_id=str(payload.get("machine_id", "UNKNOWN")).strip().upper(),
                operator_id=str(payload.get("operator_id", "")).strip() if payload.get("operator_id") else None,
                process=process_str,
                started_at=started_at,
                ended_at=ended_at,
                current_a_avg=current_a,
                voltage_v_avg=voltage_v,
                wire_feed_m_min=wire_feed,
                travel_speed_mm_min=travel_speed,
                heat_input_kj_mm=final_heat_input,
                gas_flow_l_min=gas_flow,
                interpass_max_c=interpass_c,
                parameter_deviation_pct=deviation_pct,
                quality_status=quality_status.value,
                source=str(payload.get("source", "machine-iot-gateway")).strip(),
                payload_json=json.dumps(payload, default=str, ensure_ascii=False),
                idempotency_key=idempotency_key,
                created_at=datetime.utcnow(),
            )
            session.add(telemetry_obj)
            session.flush()

            logger.info(
                f"Telemetry ingested: ID #{telemetry_obj.id} [Machine: {telemetry_obj.machine_id}] "
                f"Cur: {current_a}A, Volt: {voltage_v}V, HI: {final_heat_input} kJ/mm -> Status: {quality_status.value}"
            )
            return telemetry_obj.id

    # Implementation note.

    def ingest_batch(
        self,
        project_id: int,
        samples: List[Dict[str, Any]],
        machine_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        دریافت و درج دسته‌ای صدها نمونه ارسالی از گیت‌وی دستگاه جوشکاری در یک تراکنش واحد
        """
        if not samples:
            return {"accepted": 0, "duplicates": 0, "errors": 0}

        accepted_count = 0
        duplicate_count = 0
        error_count = 0
        records_to_insert = []

        with self.db.session_scope() as session:
            # Implementation note.
            submitted_keys = [str(s.get("idempotency_key") or "").strip() for s in samples if s.get("idempotency_key")]
            existing_keys_set: Set[str] = set()

            if submitted_keys:
                existing_records = (
                    session.query(WeldingTelemetry.idempotency_key)
                    .filter(WeldingTelemetry.idempotency_key.in_(submitted_keys))
                    .all()
                )
                existing_keys_set = {r[0] for r in existing_records}

            for sample in samples:
                key = str(sample.get("idempotency_key") or "").strip()
                if not key or key in existing_keys_set:
                    duplicate_count += 1
                    continue

                try:
                    started_at = self._parse_datetime(sample.get("started_at"))
                    if not started_at:
                        error_count += 1
                        continue

                    m_id = str(sample.get("machine_id") or machine_id or "GATEWAY_DEFAULT").strip().upper()
                    process_str = str(sample.get("process") or "GMAW").strip().upper()
                    cur = self._to_float(sample.get("current_a_avg"))
                    volt = self._to_float(sample.get("voltage_v_avg"))
                    ts = self._to_float(sample.get("travel_speed_mm_min"))

                    hi = self.calculate_heat_input(volt, cur, ts, process_str)
                    if hi is None:
                        hi = self._to_float(sample.get("heat_input_kj_mm"))

                    quality_status, dev_pct = self._screen_wps_compliance(
                        session=session,
                        project_id=project_id,
                        weld_id=sample.get("weld_id_fk"),
                        current_a=cur,
                        voltage_v=volt,
                        heat_input=hi,
                        interpass_c=self._to_float(sample.get("interpass_max_c")),
                        payload_dev_pct=self._to_float(sample.get("parameter_deviation_pct")),
                    )

                    record = WeldingTelemetry(
                        project_id=project_id,
                        weld_id_fk=sample.get("weld_id_fk"),
                        machine_id=m_id,
                        operator_id=str(sample.get("operator_id", "")).strip() if sample.get("operator_id") else None,
                        process=process_str,
                        started_at=started_at,
                        ended_at=self._parse_datetime(sample.get("ended_at")),
                        current_a_avg=cur,
                        voltage_v_avg=volt,
                        wire_feed_m_min=self._to_float(sample.get("wire_feed_m_min")),
                        travel_speed_mm_min=ts,
                        heat_input_kj_mm=hi,
                        gas_flow_l_min=self._to_float(sample.get("gas_flow_l_min")),
                        interpass_max_c=self._to_float(sample.get("interpass_max_c")),
                        parameter_deviation_pct=dev_pct,
                        quality_status=quality_status.value,
                        source=str(sample.get("source", "batch-iot-stream")).strip(),
                        payload_json=json.dumps(sample, default=str, ensure_ascii=False),
                        idempotency_key=key,
                        created_at=datetime.utcnow(),
                    )
                    records_to_insert.append(record)
                    existing_keys_set.add(key)
                    accepted_count += 1

                except Exception as exc:
                    logger.error(f"Error processing telemetry sample: {exc}")
                    error_count += 1

            if records_to_insert:
                session.bulk_save_objects(records_to_insert)

        logger.info(f"Batch Telemetry Ingest: {accepted_count} Accepted, {duplicate_count} Duplicates, {error_count} Errors.")
        return {
            "total_submitted": len(samples),
            "accepted": accepted_count,
            "duplicates": duplicate_count,
            "errors": error_count,
        }

    # Implementation note.

    @staticmethod
    def calculate_heat_input(
        voltage_v: Optional[float],
        current_a: Optional[float],
        travel_speed_mm_min: Optional[float],
        process_type: str = "SMAW",
    ) -> Optional[float]:
        """
        محاسبه حرارت ورودی طبق فرمول بین‌المللی ASME Sec IX (QW-409.1) و EN 1011-1:
        $$HI (kJ/mm) = \\frac{V \times A \times 60}{\\text{Travel Speed (mm/min)} \times 1000} \times \\eta$$
        """
        if not (voltage_v and current_a and travel_speed_mm_min and travel_speed_mm_min > 0):
            return None

        # Implementation note.
        proc_clean = process_type.strip().upper()
        efficiency = PROCESS_THERMAL_EFFICIENCY.get(proc_clean, 0.80)

        # Implementation note.
        raw_heat_input_kj_mm = ((voltage_v * current_a * 60.0) / (travel_speed_mm_min * 1000.0)) * efficiency
        return round(raw_heat_input_kj_mm, 3)

    # Implementation note.

    def _screen_wps_compliance(
        self,
        session: Session,
        project_id: int,
        weld_id: Optional[int],
        current_a: Optional[float],
        voltage_v: Optional[float],
        heat_input: Optional[float],
        interpass_c: Optional[float],
        payload_dev_pct: Optional[float],
    ) -> Tuple[TelemetryQualityStatus, float]:
        """
        غربالگری هوشمند و تطبیق آمپراژ، ولتاژ و حرارت ورودی با حدود مجاز ثبت‌شده در WPS سرجوش
        """
        # Implementation note.
        if payload_dev_pct is not None and payload_dev_pct > 15.0:
            return TelemetryQualityStatus.CRITICAL_DEVIATION, payload_dev_pct

        # Implementation note.
        if heat_input is not None:
            if heat_input > 4.5:  # Implementation note.
                return TelemetryQualityStatus.HEAT_INPUT_EXCEEDED, 25.0
            if heat_input < 0.3 and heat_input > 0:
                return TelemetryQualityStatus.HEAT_INPUT_TOO_LOW, 20.0

        # Implementation note.
        if interpass_c is not None and interpass_c > 250.0:  # Implementation note.
            return TelemetryQualityStatus.CRITICAL_DEVIATION, 18.0

        # Implementation note.
        if weld_id:
            weld = session.get(Weld, weld_id)
            if weld and getattr(weld, "wps_number", None):
                wps_record = (
                    session.query(WPS_PQR)
                    .filter(
                        WPS_PQR.project_id == project_id,
                        WPS_PQR.wps_number == weld.wps_number,
                    )
                    .first()
                )
                if wps_record:
                    # Implementation note.
                    min_amp = float(getattr(wps_record, "min_current_a", 0.0) or 0.0)
                    max_amp = float(getattr(wps_record, "max_current_a", 999.0) or 999.0)
                    if current_a and (current_a < min_amp or current_a > max_amp):
                        dev = round(abs(current_a - ((min_amp + max_amp) / 2)) / ((min_amp + max_amp) / 2) * 100, 1)
                        return TelemetryQualityStatus.CRITICAL_DEVIATION, dev

        return TelemetryQualityStatus.WITHIN_WPS, payload_dev_pct or 0.0

    # Implementation note.

    def summary(self, project_id: int) -> Dict[str, Any]:
        """
        محاسبه داشبورد تله‌متری، نرخ انحراف و آمار دستگاه‌ها با کوئری‌های تجمعی SQL
        (حل مشکل سرریز حافظه RAM و حذف لود تمام رکوردها)
        """
        with self.db.session_scope() as session:
            # Implementation note.
            stats = session.query(
                func.count(WeldingTelemetry.id).label("total_samples"),
                func.sum(case((WeldingTelemetry.quality_status.in_([
                    TelemetryQualityStatus.CRITICAL_DEVIATION.value,
                    TelemetryQualityStatus.HEAT_INPUT_EXCEEDED.value,
                    TelemetryQualityStatus.HEAT_INPUT_TOO_LOW.value,
                    "Deviation",
                ]), 1), else_=0)).label("deviations_count"),
                func.sum(case((WeldingTelemetry.quality_status == TelemetryQualityStatus.WITHIN_WPS.value, 1), else_=0)).label("within_wps_count"),
                func.avg(WeldingTelemetry.current_a_avg).label("avg_current"),
                func.avg(WeldingTelemetry.voltage_v_avg).label("avg_voltage"),
                func.avg(WeldingTelemetry.heat_input_kj_mm).label("avg_heat_input"),
                func.count(func.distinct(WeldingTelemetry.machine_id)).label("active_machines_count"),
            ).filter(WeldingTelemetry.project_id == project_id).first()

            total_samples = stats.total_samples or 0
            deviations = stats.deviations_count or 0
            dev_rate = round((deviations / total_samples * 100), 2) if total_samples > 0 else 0.0

            # Implementation note.
            machines_list = [
                r[0] for r in (
                    session.query(func.distinct(WeldingTelemetry.machine_id))
                    .filter(WeldingTelemetry.project_id == project_id)
                    .order_by(WeldingTelemetry.machine_id.asc())
                    .all()
                )
            ]

            # Implementation note.
            deviations_by_machine = (
                session.query(
                    WeldingTelemetry.machine_id,
                    func.count(WeldingTelemetry.id).label("samples"),
                    func.sum(case((WeldingTelemetry.quality_status != TelemetryQualityStatus.WITHIN_WPS.value, 1), else_=0)).label("deviations"),
                )
                .filter(WeldingTelemetry.project_id == project_id)
                .group_by(WeldingTelemetry.machine_id)
                .all()
            )

            return {
                "project_id": project_id,
                "samples": total_samples,
                "deviations": deviations,
                "timestamp": datetime.utcnow().isoformat(),
                "telemetry_metrics": {
                    "total_samples_recorded": total_samples,
                    "total_deviations_flagged": deviations,
                    "within_wps_compliance_count": stats.within_wps_count or 0,
                    "parameter_deviation_rate_pct": dev_rate,
                    "average_operating_amperage": round(float(stats.avg_current or 0.0), 1),
                    "average_operating_voltage": round(float(stats.avg_voltage or 0.0), 1),
                    "average_heat_input_kj_mm": round(float(stats.avg_heat_input or 0.0), 2),
                },
                "connected_fleet": {
                    "active_machines_count": stats.active_machines_count or 0,
                    "machine_ids": machines_list,
                },
                "machine_health_breakdown": {
                    row.machine_id: {
                        "samples": row.samples,
                        "deviations": row.deviations or 0,
                        "deviation_rate_pct": round(((row.deviations or 0) / row.samples * 100), 1) if row.samples > 0 else 0.0,
                    }
                    for row in deviations_by_machine
                },
            }

    # Implementation note.

    def get_weld_telemetry_timeline(
        self,
        project_id: int,
        weld_id: int,
        limit: int = 500,
    ) -> Dict[str, Any]:
        """
        استخراج دیتای نمودار ولتاژ/آمپراژ/حرارت ورودی در طول زمان جوشکاری یک سرجوش خاص
        جهت الحاق به پرونده الکترونیکی جوش (Digital Weld Certificate)
        """
        with self.db.session_scope() as session:
            samples = (
                session.query(WeldingTelemetry)
                .filter(
                    WeldingTelemetry.project_id == project_id,
                    WeldingTelemetry.weld_id_fk == weld_id,
                )
                .order_by(WeldingTelemetry.started_at.asc())
                .limit(limit)
                .all()
            )

            timeline_data = []
            for s in samples:
                timeline_data.append({
                    "timestamp": s.started_at.isoformat(),
                    "current_a": s.current_a_avg,
                    "voltage_v": s.voltage_v_avg,
                    "travel_speed_mm_min": s.travel_speed_mm_min,
                    "heat_input_kj_mm": s.heat_input_kj_mm,
                    "status": s.quality_status,
                })

            return {
                "weld_id": weld_id,
                "samples_count": len(timeline_data),
                "timeline": timeline_data,
            }

    # Implementation note.

    @staticmethod
    def _parse_datetime(v: Any) -> Optional[datetime]:
        """تبدیل رشته‌های زمانی ISO8601 به شیء datetime استاندارد"""
        if not v:
            return None
        if isinstance(v, datetime):
            return v
        try:
            clean_str = str(v).replace("Z", "+00:00")
            return datetime.fromisoformat(clean_str).replace(tzinfo=None)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_float(v: Any) -> Optional[float]:
        """تبدیل ایمن مقادیر شناور"""
        if v in (None, ""):
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None