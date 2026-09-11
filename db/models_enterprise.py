# -*- coding: utf-8 -*-
"""
db/models_enterprise.py – PipeAgent v5.1
=========================================
Enterprise-grade models separated from the base models to keep concerns
modular and avoid circular dependencies.

Included groups:
  • Multi-tenant: Organization
  • Integration: IntegrationEndpoint, IntegrationJob, ExternalMapping
  • IoT / Telemetry: WeldingTelemetry
  • Field Sync (Batch): FieldSyncBatch, FieldSyncReceipt
  • Document Vault: EnterpriseDocumentEvidence
  • Predictive / AI: PredictionObservation, PredictionRun, PredictionImpact

All models inherit the same `Base` defined in db.models to ensure
`Base.metadata.create_all()` discovers them via the registered import
in db.manager (`import db.models_enterprise`).

NOTE: `ProjectMembership` and `ApiCredential` have been removed from
this file because they are already defined in `db.models.py`.
`DocumentEvidence` has been renamed to `EnterpriseDocumentEvidence`
to avoid a name clash with the `DocumentEvidence` class in `db.models.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship, synonym

# Implementation note.
from db.models import (
    Base,
    ReprMixin,
    TimestampMixin,
    CreatedOnlyMixin,
    SoftDeleteMixin,
    Project,
    User,
    _utcnow,
)


# ══════════════════════════════════════════════
#  1. Multi-Tenant
# ══════════════════════════════════════════════

class Organization(Base, CreatedOnlyMixin, ReprMixin):
    """سازمان/شرکت والد برای چندپروژه‌ای (multi-tenant)."""
    __tablename__ = "organizations"
    _repr_fields = ("id", "org_code", "name")

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_code = Column(String(80), unique=True, nullable=False, index=True)
    name = Column(String(250), nullable=False)
    external_id = Column(String(150), index=True)
    is_active = Column(Boolean, default=True, index=True)


# ══════════════════════════════════════════════
#  2. API & Auth
# ══════════════════════════════════════════════
# Implementation note.


# ══════════════════════════════════════════════
#  3. External Integration
# ══════════════════════════════════════════════

class IntegrationEndpoint(Base, TimestampMixin, ReprMixin):
    """نقطه‌ی پایانی سیستم‌های خارجی (ERP, BIM, DMS, Webhook)."""
    __tablename__ = "integration_endpoints"
    _repr_fields = ("id", "name", "integration_type")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    name = Column(String(150), nullable=False)
    integration_type = Column(
        String(50), nullable=False, index=True,
        # Implementation note.
    )
    base_url = Column(String(500))
    auth_mode = Column(String(40), default="none")  # none, basic, oauth2, api_key
    configuration_json = Column(Text, default="{}")
    is_active = Column(Boolean, default=True, index=True)

    jobs = relationship("IntegrationJob", back_populates="endpoint", cascade="all, delete-orphan")


class IntegrationJob(Base, CreatedOnlyMixin, ReprMixin):
    """صف Job برای سینک با سیستم‌های خارجی (Idempotent)."""
    __tablename__ = "integration_jobs"
    _repr_fields = ("id", "job_type", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    endpoint_id = Column(
        Integer, ForeignKey("integration_endpoints.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    job_type = Column(String(80), nullable=False, index=True)
    idempotency_key = Column(String(120), unique=True, nullable=False, index=True)
    payload_json = Column(Text, nullable=False)
    status = Column(String(30), default="Pending", index=True)
    attempts = Column(Integer, default=0)
    last_error = Column(Text)

    completed_at = Column(DateTime, nullable=True)

    endpoint = relationship("IntegrationEndpoint", back_populates="jobs")


class ExternalMapping(Base, ReprMixin):
    """نگاشت کلید خارجی ↔ موجودیت داخلی (برای سینک)."""
    __tablename__ = "external_mappings"
    _repr_fields = ("id", "system_type", "external_key")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    system_type = Column(
        String(50), nullable=False, index=True,
        # Implementation note.
    )
    external_key = Column(String(200), nullable=False, index=True)
    entity_type = Column(String(80), nullable=False)
    entity_id = Column(Integer, nullable=True, index=True)
    external_revision = Column(String(50))
    metadata_json = Column(Text, default="{}")
    last_synced_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "system_type", "external_key",
            name="uq_external_mapping",
        ),
    )


# ══════════════════════════════════════════════
#  4. IoT / Welding Telemetry
# ══════════════════════════════════════════════

class WeldingTelemetry(Base, CreatedOnlyMixin, ReprMixin):
    """داده‌های تله‌متری دستگاه جوش (current, voltage, heat input, ...)."""
    __tablename__ = "welding_telemetry"
    _repr_fields = ("id", "machine_id", "process")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    weld_id = Column(
        Integer, ForeignKey("welds.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    weld_id_fk = synonym("weld_id")
    machine_id = Column(String(120), nullable=False, index=True)
    operator_id = Column(String(100), index=True)
    process = Column(String(50), index=True)  # GTAW, SMAW, FCAW, GMAW

    started_at = Column(DateTime, nullable=False, index=True)
    ended_at = Column(DateTime, nullable=True)
    current_a_avg = Column(Float, nullable=True)
    voltage_v_avg = Column(Float, nullable=True)
    wire_feed_m_min = Column(Float, nullable=True)
    travel_speed_mm_min = Column(Float, nullable=True)
    heat_input_kj_mm = Column(Float, nullable=True)
    gas_flow_l_min = Column(Float, nullable=True)
    interpass_max_c = Column(Float, nullable=True)
    parameter_deviation_pct = Column(Float, default=0)

    source = Column(String(50), default="machine-gateway")
    payload_json = Column(Text, nullable=True)
    quality_status = Column(String(30), default="Unreviewed", index=True)
    received_at = Column(DateTime, default=_utcnow, index=True)
    idempotency_key = Column(String(120), unique=True, nullable=False, index=True)

    project = relationship("Project")
    weld = relationship("Weld")


# ══════════════════════════════════════════════
#  5. Field Sync (Batch)
# ══════════════════════════════════════════════

class FieldSyncBatch(Base, CreatedOnlyMixin, ReprMixin):
    """بچ ارسالی از دستگاه موبایل/فیلد برای سینک آفلاین."""
    __tablename__ = "field_sync_batches"
    _repr_fields = ("id", "device_id", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    device_id = Column(String(120), nullable=False, index=True)
    batch_uuid = Column(String(120), unique=True, nullable=False, index=True)
    received_count = Column(Integer, default=0)
    accepted_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    conflict_count = Column(Integer, default=0)
    status = Column(String(30), default="Received", index=True)
    completed_at = Column(DateTime, nullable=True)

    receipts = relationship(
        "FieldSyncReceipt", back_populates="batch", cascade="all, delete-orphan",
    )


class FieldSyncReceipt(Base, CreatedOnlyMixin, ReprMixin):
    """رسید تک‌تک رویدادهای یک بچ سینک (Acceptance/Rejection)."""
    __tablename__ = "field_sync_receipts"
    _repr_fields = ("id", "event_uuid", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(
        Integer, ForeignKey("field_sync_batches.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    event_uuid = Column(String(120), nullable=False, index=True)
    status = Column(String(30), nullable=False)  # Accepted, Rejected, Conflict
    server_event_id = Column(Integer, nullable=True)
    message = Column(Text, nullable=True)

    batch = relationship("FieldSyncBatch", back_populates="receipts")

    __table_args__ = (
        UniqueConstraint("batch_id", "event_uuid", name="uq_sync_receipt_event"),
    )


# ══════════════════════════════════════════════
#  6. Document Vault
# ══════════════════════════════════════════════

class EnterpriseDocumentEvidence(Base, CreatedOnlyMixin, ReprMixin):
    """شاهد مدرک (file + sha256) برای ممیزی و Traceability.
    نام کلاس برای جلوگیری از تداخل با DocumentEvidence در db.models تغییر کرده است."""
    __tablename__ = "document_evidence"
    _repr_fields = ("id", "file_name", "sha256")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    entity_type = Column(String(80), nullable=False, index=True)
    entity_key = Column(String(180), nullable=False, index=True)
    evidence_type = Column(String(80), nullable=False)
    file_name = Column(String(300), nullable=False)
    file_path = Column(String(500), nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    revision = Column(String(30), default="0")
    status = Column(String(30), default="Available", index=True)
    captured_by = Column(String(120))
    metadata_json = Column(Text, default="{}")


# ══════════════════════════════════════════════
#  7. Predictive / AI
# ══════════════════════════════════════════════

class PredictionObservation(Base, ReprMixin):
    """مشاهدات پیش‌بینی (سری زمانی متریک‌ها)."""
    __tablename__ = "prediction_observations"
    _repr_fields = ("id", "metric", "value")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    metric = Column(String(100), nullable=False, index=True)
    value = Column(Float, nullable=False)
    observed_at = Column(DateTime, default=_utcnow, index=True)
    source = Column(String(80), default="execution-engine")
    context_json = Column(Text, default="{}")


class PredictionRun(Base, CreatedOnlyMixin, ReprMixin):
    """اجرای مدل پیش‌بینی (Run log)."""
    __tablename__ = "prediction_runs"
    _repr_fields = ("id", "model_name", "horizon_hours")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    model_name = Column(String(120), nullable=False)
    model_version = Column(String(50), default="1.0")
    horizon_hours = Column(Integer, default=72)
    generated_at = Column(DateTime, default=_utcnow, index=True)
    confidence = Column(Float, default=0)
    data_quality_score = Column(Float, default=0)
    result_json = Column(Text, nullable=False)

    impacts = relationship(
        "PredictionImpact", back_populates="run", cascade="all, delete-orphan",
    )


class PredictionImpact(Base, CreatedOnlyMixin, ReprMixin):
    """اثر پیش‌بینی‌شده روی nodeهای گراف اجرایی."""
    __tablename__ = "prediction_impacts"
    _repr_fields = ("id", "source_node", "affected_node")

    id = Column(Integer, primary_key=True, autoincrement=True)
    prediction_run_id = Column(
        Integer, ForeignKey("prediction_runs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    source_node = Column(String(180), nullable=False, index=True)
    affected_node = Column(String(180), nullable=False, index=True)
    probability = Column(Float, default=0.5)
    confidence = Column(Float, default=0.5)
    severity = Column(String(20), default="Medium")
    rationale = Column(Text, nullable=False)

    run = relationship("PredictionRun", back_populates="impacts")