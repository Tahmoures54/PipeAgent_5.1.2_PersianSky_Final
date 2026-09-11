# -*- coding: utf-8 -*-
"""
services/integration_service.py – PipeAgent
مدیریت جامع یکپارچه‌سازی، صف‌بندی وب‌هوک‌ها، استخراج مدل‌های سه‌بعدی IFC/BIM
و نگاشت تطبیقی شناسه‌ها با سیستم‌های ERP (SAP/Oracle) و زمان‌بندی (Primavera P6).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set, Tuple, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from sqlalchemy import func, and_, or_, desc
from sqlalchemy.exc import SQLAlchemyError

from db.manager import DatabaseManager
from db.models import IntegrationEndpoint, IntegrationJob, ExternalMapping

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Integration Configurations
# ──────────────────────────────────────────────

class JobStatus(str, Enum):
    """چرخه حیات صف پیام‌ها و وب‌هوک‌ها"""
    PENDING = "PENDING"                # Implementation note.
    PROCESSING = "PROCESSING"          # Implementation note.
    RETRYING = "RETRYING"              # Implementation note.
    COMPLETED = "COMPLETED"            # Implementation note.
    FAILED = "FAILED"                  # Implementation note.
    CANCELLED = "CANCELLED"            # Implementation note.


class SystemType(str, Enum):
    """انواع سیستم‌های متصل به هاب یکپارچه‌سازی"""
    ERP_SAP = "ERP_SAP"
    ERP_ORACLE = "ERP_ORACLE"
    PRIMAVERA_P6 = "PRIMAVERA_P6"
    MS_PROJECT = "MS_PROJECT"
    DMS_ACONEX = "DMS_ACONEX"
    BIM_AVEVA = "BIM_AVEVA"
    BIM_REVIT = "BIM_REVIT"


class HttpMethod(str, Enum):
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    GET = "GET"


# ──────────────────────────────────────────────
#  1. Integration Service Implementation
# ──────────────────────────────────────────────

class IntegrationService:
    """
    سرویس مدیریت صف پیام‌ها، ارسال وب‌هوک‌ها و تضمین تحویل تراکنش‌ها به سیستم‌های خارجی
    """

    MAX_RETRIES = 5
    INITIAL_BACKOFF_SECONDS = 5  # Implementation note.

    def __init__(self, db: DatabaseManager, default_timeout: int = 25):
        self.db = db
        self.timeout = default_timeout

    # Implementation note.

    def queue_job(
        self,
        project_id: Optional[int],
        endpoint_id: Optional[int],
        job_type: str,
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = None,
        priority: int = 10,
        headers: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        ثبت پیام در صف ارسال با کلید یکتایی (Idempotency Key) جهت جلوگیری از ارسال تکراری
        """
        # Implementation note.
        computed_key = idempotency_key or hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        with self.db.session_scope() as session:
            existing_job = (
                session.query(IntegrationJob)
                .filter(IntegrationJob.idempotency_key == computed_key)
                .first()
            )
            if existing_job:
                logger.info(f"Idempotent hit: Job #{existing_job.id} already queued with key '{computed_key[:10]}...'")
                return existing_job.id

            job = IntegrationJob(
                project_id=project_id,
                endpoint_id=endpoint_id,
                job_type=job_type.strip().upper(),
                idempotency_key=computed_key,
                payload_json=json.dumps(payload, default=str),
                status=JobStatus.PENDING.value,
                attempts=0,
                max_attempts=self.MAX_RETRIES,
                priority=priority,
                headers_json=json.dumps(headers or {}),
                created_at=datetime.utcnow(),
            )
            session.add(job)
            session.flush()

            logger.info(f"Integration Job #{job.id} ({job_type}) queued successfully.")
            return job.id

    # Implementation note.

    def dispatch(self, job_id: int) -> Dict[str, Any]:
        """
        ارسال قطعی پیام وب‌هوک با امضای دیجیتال HMAC، مدیریت خطا و محاسبه زمان بازآزمایی بعدی
        """
        with self.db.session_scope() as session:
            job = session.query(IntegrationJob).filter(IntegrationJob.id == job_id).first()
            if not job:
                raise ValueError(f"Integration job #{job_id} not found.")

            if job.status == JobStatus.COMPLETED.value:
                return {"status": JobStatus.COMPLETED.value, "job_id": job_id, "message": "Already completed"}

            endpoint = session.query(IntegrationEndpoint).filter(
                IntegrationEndpoint.id == job.endpoint_id
            ).first() if job.endpoint_id else None

            job.attempts += 1
            job.status = JobStatus.PROCESSING.value
            job.last_attempt_at = datetime.utcnow()

            if not endpoint or not endpoint.base_url:
                job.status = JobStatus.FAILED.value
                job.last_error = "No active endpoint configured for this integration job."
                logger.error(f"Job #{job_id} failed: {job.last_error}")
                return {"status": JobStatus.FAILED.value, "error": job.last_error}

            # Implementation note.
            payload_str = job.payload_json or "{}"
            request_headers = {
                "Content-Type": "application/json",
                "X-PipeAgent-Job-ID": str(job.id),
                "X-PipeAgent-Job-Type": job.job_type,
                "X-PipeAgent-Timestamp": datetime.utcnow().isoformat(),
            }

            # Implementation note.
            custom_headers = json.loads(getattr(job, "headers_json", None) or "{}")
            request_headers.update(custom_headers)

            # Implementation note.
            if hasattr(endpoint, "secret_token") and endpoint.secret_token:
                signature = hmac.new(
                    endpoint.secret_token.encode("utf-8"),
                    payload_str.encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                request_headers["X-PipeAgent-Signature"] = signature

            # Implementation note.
            try:
                response = requests.post(
                    url=endpoint.base_url,
                    data=payload_str.encode("utf-8"),
                    headers=request_headers,
                    timeout=self.timeout,
                )

                response.raise_for_status()

                # Implementation note.
                job.status = JobStatus.COMPLETED.value
                job.completed_at = datetime.utcnow()
                job.response_status_code = response.status_code
                job.response_body = response.text[:2000]  # Implementation note.
                job.last_error = None

                logger.info(f"Job #{job.id} dispatched successfully to '{endpoint.base_url}' (HTTP {response.status_code}).")
                return {
                    "status": JobStatus.COMPLETED.value,
                    "job_id": job.id,
                    "http_status": response.status_code,
                    "response": response.text[:500],
                }

            except requests.exceptions.RequestException as exc:
                error_msg = f"HTTP error during dispatch: {str(exc)}"
                if hasattr(exc, "response") and exc.response is not None:
                    error_msg += f" | Body: {exc.response.text[:500]}"

                job.last_error = error_msg
                job.response_status_code = getattr(exc.response, "status_code", None)

                # Implementation note.
                if job.attempts < job.max_attempts:
                    job.status = JobStatus.RETRYING.value
                    backoff_delay = self.INITIAL_BACKOFF_SECONDS * (2 ** (job.attempts - 1))
                    job.next_retry_at = datetime.utcnow() + timedelta(seconds=backoff_delay)
                    logger.warning(f"Job #{job.id} failed (Attempt {job.attempts}/{job.max_attempts}). Retrying in {backoff_delay}s.")
                else:
                    job.status = JobStatus.FAILED.value
                    job.next_retry_at = None
                    logger.error(f"Job #{job.id} permanently FAILED after {job.attempts} attempts.")

                return {"status": job.status, "job_id": job.id, "error": error_msg}

    # Implementation note.

    def process_pending_jobs(self, batch_size: int = 20) -> Dict[str, int]:
        """
        پردازش دوره‌ای و دسته‌ای پیام‌های معلق و پیام‌های موعد بازآزمایی رسیده
        """
        now = datetime.utcnow()
        with self.db.session_scope() as session:
            candidate_job_ids = [
                j.id for j in (
                    session.query(IntegrationJob.id)
                    .filter(
                        or_(
                            IntegrationJob.status == JobStatus.PENDING.value,
                            and_(
                                IntegrationJob.status == JobStatus.RETRYING.value,
                                IntegrationJob.next_retry_at <= now,
                            ),
                        )
                    )
                    .order_by(IntegrationJob.priority.desc(), IntegrationJob.id.asc())
                    .limit(batch_size)
                    .all()
                )
            ]

        processed = 0
        succeeded = 0
        failed = 0

        for j_id in candidate_job_ids:
            res = self.dispatch(j_id)
            processed += 1
            if res.get("status") == JobStatus.COMPLETED.value:
                succeeded += 1
            else:
                failed += 1

        return {"processed": processed, "succeeded": succeeded, "failed": failed}


# ──────────────────────────────────────────────
#  2. Memory-Safe IFC/STEP BIM Adapter
# ──────────────────────────────────────────────

class IFCAdapter:
    """
    استخراج‌کننده فوق‌سریع و سبک اطلاعات مدل‌های سه‌بعدی IFC بدون نیاز به پکیج‌های سنگین
    بهینه‌سازی شده با متد جریانی (Line-by-Line Streaming) جهت ممانعت از سرریز حافظه RAM.
    """

    # Implementation note.
    ENTITY_PATTERN = re.compile(r"^#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)\);$", re.IGNORECASE)
    HEADER_SCHEMA_PATTERN = re.compile(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'\s*\)\s*\);", re.IGNORECASE)
    GLOBAL_ID_PATTERN = re.compile(r"'\s*([0-9A-Za-z_$]{22})\s*'", re.IGNORECASE)

    # Implementation note.
    PIPING_ENTITIES = {
        "IFCPIPESEGMENT", "IFCPIPEFITTING", "IFCVALVE", "IFCFLOWCONTROLLER",
        "IFCFLOWFITTING", "IFCFLOWSEGMENT", "IFCDISTRIBUTIONELEMENT",
        "IFCDISCRETEACCESSORY", "IFCMECHANICALEQUIPMENT"
    }

    def stream_entities(self, file_path: Union[str, Path]) -> Generator[Tuple[int, str, str], None, None]:
        """خوانش جریانی ردیف به ردیف المان‌های فایل IFC (مصرف RAM زیر ۵ مگابایت)"""
        path_obj = Path(file_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"IFC file not found: {file_path}")

        with open(path_obj, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                clean_line = line.strip()
                if not clean_line or clean_line.startswith("/*"):
                    continue
                match = self.ENTITY_PATTERN.match(clean_line)
                if match:
                    yield int(match.group(1)), match.group(2).upper(), match.group(3)

    def extract_inventory(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        استخراج خلاصه شناسنامه مدل، متادیتای هدر، آمار المان‌های پایپینگ و نمونه‌های GUID
        """
        path_obj = Path(file_path)
        entity_counts: Dict[str, int] = {}
        piping_items: List[Dict[str, Any]] = []
        schema_version = "IFC2X3"  # Implementation note.

        # Implementation note.
        with open(path_obj, "r", encoding="utf-8", errors="ignore") as f:
            for _ in range(50):  # Implementation note.
                line = f.readline()
                if "FILE_SCHEMA" in line:
                    schema_match = self.HEADER_SCHEMA_PATTERN.search(line)
                    if schema_match:
                        schema_version = schema_match.group(1)
                    break

        # Implementation note.
        total_entities = 0
        for step_id, entity_type, raw_params in self.stream_entities(path_obj):
            total_entities += 1
            entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1

            # Implementation note.
            if entity_type in self.PIPING_ENTITIES and len(piping_items) < 200:
                guid_match = self.GLOBAL_ID_PATTERN.search(raw_params)
                guid = guid_match.group(1) if guid_match else None
                piping_items.append({
                    "step_id": step_id,
                    "type": entity_type,
                    "global_id": guid,
                })

        return {
            "file_name": path_obj.name,
            "file_size_bytes": path_obj.stat().st_size,
            "schema_version": schema_version,
            "total_entities_count": total_entities,
            "entity_type_breakdown": entity_counts,
            "piping_components_sample": piping_items,
            "piping_components_total": sum(entity_counts.get(k, 0) for k in self.PIPING_ENTITIES),
            "status": "Inventory parsed safely with streaming engine.",
        }

    def inventory(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Alias used by the enterprise API."""
        return self.extract_inventory(file_path)


# ──────────────────────────────────────────────
#  3. Bidirectional External Mapping Service
# ──────────────────────────────────────────────

class ExternalMappingService:
    """
    سرویس مدیریت تطابق شناسه‌های سیستم‌های خارجی (Cross-System ID Resolution)
    امکان تبدیل کدهای SAP Material / P6 Activity / Aconex Doc No به موجودیت‌های داخلی PipeAgent.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    def upsert_mapping(
        self,
        project_id: int,
        system_type: Union[SystemType, str],
        external_key: str,
        entity_type: str,
        entity_id: Optional[int],
        revision: str = "0",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """ثبت یا به‌روزرسانی تطابق کلید خارجی با موجودیت داخلی"""
        sys_val = system_type.value if isinstance(system_type, SystemType) else str(system_type).strip().upper()
        ext_key_clean = str(external_key).strip()

        with self.db.session_scope() as session:
            mapping = (
                session.query(ExternalMapping)
                .filter(
                    ExternalMapping.project_id == project_id,
                    ExternalMapping.system_type == sys_val,
                    ExternalMapping.external_key == ext_key_clean,
                )
                .first()
            )

            if not mapping:
                mapping = ExternalMapping(
                    project_id=project_id,
                    system_type=sys_val,
                    external_key=ext_key_clean,
                    entity_type=entity_type.strip().upper(),
                    entity_id=entity_id,
                    created_at=datetime.utcnow() if hasattr(ExternalMapping, "created_at") else None,
                )
                session.add(mapping)

            mapping.entity_id = entity_id
            mapping.external_revision = revision
            mapping.metadata_json = json.dumps(metadata or {}, default=str)
            mapping.last_synced_at = datetime.utcnow()

            session.flush()
            logger.info(f"Mapping upserted: [{sys_val}] '{ext_key_clean}' <==> {entity_type} #{entity_id}")
            return mapping.id

    def resolve_to_internal_id(
        self,
        project_id: int,
        system_type: Union[SystemType, str],
        external_key: str,
    ) -> Optional[int]:
        """یافتن شناسه داخلی موجودیت PipeAgent از روی کلید سیستم خارجی (مثلاً یافتن سرجوش از روی کد فعالیت P6)"""
        sys_val = system_type.value if isinstance(system_type, SystemType) else str(system_type).strip().upper()

        with self.db.session_scope() as session:
            mapping = (
                session.query(ExternalMapping)
                .filter(
                    ExternalMapping.project_id == project_id,
                    ExternalMapping.system_type == sys_val,
                    ExternalMapping.external_key == str(external_key).strip(),
                )
                .first()
            )
            return mapping.entity_id if mapping else None

    def resolve_to_external_key(
        self,
        project_id: int,
        system_type: Union[SystemType, str],
        entity_type: str,
        entity_id: int,
    ) -> Optional[str]:
        """یافتن کلید سیستم خارجی بر اساس شناسه داخلی موجودیت (مثلاً دریافت کد متریال SAP برای یک قطعه لوله)"""
        sys_val = system_type.value if isinstance(system_type, SystemType) else str(system_type).strip().upper()

        with self.db.session_scope() as session:
            mapping = (
                session.query(ExternalMapping)
                .filter(
                    ExternalMapping.project_id == project_id,
                    ExternalMapping.system_type == sys_val,
                    ExternalMapping.entity_type == entity_type.strip().upper(),
                    ExternalMapping.entity_id == entity_id,
                )
                .first()
            )
            return mapping.external_key if mapping else None

    def bulk_upsert_mappings(
        self,
        project_id: int,
        system_type: Union[SystemType, str],
        mappings_data: List[Dict[str, Any]],
    ) -> int:
        """ثبت دسته‌ای تطابق هزاران رکورد به صورت همزمان (مثلاً ایمپورت کل کدهای کالای SAP)"""
        sys_val = system_type.value if isinstance(system_type, SystemType) else str(system_type).strip().upper()
        now = datetime.utcnow()
        count = 0

        with self.db.session_scope() as session:
            for item in mappings_data:
                ext_key = str(item["external_key"]).strip()
                mapping = (
                    session.query(ExternalMapping)
                    .filter(
                        ExternalMapping.project_id == project_id,
                        ExternalMapping.system_type == sys_val,
                        ExternalMapping.external_key == ext_key,
                    )
                    .first()
                )

                if not mapping:
                    mapping = ExternalMapping(
                        project_id=project_id,
                        system_type=sys_val,
                        external_key=ext_key,
                        entity_type=item["entity_type"].strip().upper(),
                        entity_id=item.get("entity_id"),
                    )
                    session.add(mapping)

                mapping.entity_id = item.get("entity_id")
                mapping.external_revision = item.get("revision", "0")
                mapping.metadata_json = json.dumps(item.get("metadata", {}), default=str)
                mapping.last_synced_at = now
                count += 1

            session.flush()

        logger.info(f"Bulk-upserted {count} mappings for System '{sys_val}' in Project #{project_id}.")
        return count