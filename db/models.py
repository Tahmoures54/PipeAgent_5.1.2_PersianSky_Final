# -*- coding: utf-8 -*-
"""
db/models.py – PipeAgent v5.1
==============================
Complete SQLAlchemy ORM model registry for the PipeAgent platform.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    relationship,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
#  0. Base & Helpers
# ══════════════════════════════════════════════

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ══════════════════════════════════════════════
#  1. Mixins
# ══════════════════════════════════════════════

class TimestampMixin:
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)


class CreatedOnlyMixin:
    created_at = Column(DateTime, default=_utcnow, nullable=False)


class SoftDeleteMixin:
    deleted_at = Column(DateTime, nullable=True, index=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = _utcnow()

    def restore(self) -> None:
        self.deleted_at = None


class ReprMixin:
    _repr_fields: tuple[str, ...] = ("id",)

    def __repr__(self) -> str:
        cls = self.__class__.__name__
        parts = []
        for f in self._repr_fields:
            val = getattr(self, f, "?")
            parts.append(f"{f}={val!r}")
        return f"<{cls}({', '.join(parts)})>"


# ══════════════════════════════════════════════
#  2. Core Models
# ══════════════════════════════════════════════

class User(Base, TimestampMixin, ReprMixin):
    __tablename__ = "users"
    _repr_fields = ("id", "username", "role")

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="viewer")
    is_active = Column(Boolean, default=True, index=True)
    department = Column(String(100), default="")
    employee_id = Column(String(50), unique=True, index=True)
    full_name = Column(String(150), default="")
    company = Column(String(150), default="")
    phone = Column(String(50), default="")
    email = Column(String(255), nullable=True, index=True)
    auth_provider = Column(String(40), default="local")
    last_login = Column(DateTime, nullable=True)

    audit_logs = relationship("AuditLog", back_populates="user", lazy="dynamic")
    project_memberships = relationship(
        "ProjectMembership", back_populates="user", cascade="all, delete-orphan",
    )
    api_credentials = relationship(
        "ApiCredential", back_populates="created_by_user", lazy="dynamic",
    )


class LicenseInfo(Base, ReprMixin):
    __tablename__ = "license_info"
    _repr_fields = ("key",)

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)


class Project(Base, TimestampMixin, ReprMixin, SoftDeleteMixin):
    __tablename__ = "projects"
    _repr_fields = ("id", "project_code", "title")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_code = Column(String(50), unique=True, nullable=False, index=True)
    title = Column(String(300), nullable=False)
    client = Column(String(200))
    contractor = Column(String(200))
    standard = Column(String(100))
    status = Column(String(40), default="ACTIVE", nullable=False, index=True)
    project_type = Column(String(50))

    areas = relationship("Area", back_populates="project", cascade="all, delete-orphan")
    line_items = relationship("LineListItem", back_populates="project", cascade="all, delete-orphan")
    material_requisitions = relationship("MaterialRequisition", back_populates="project", cascade="all, delete-orphan")
    purchase_orders = relationship("PurchaseOrder", back_populates="project", cascade="all, delete-orphan")
    material_items = relationship("MaterialItem", back_populates="project", cascade="all, delete-orphan")
    material_takeoffs = relationship("MaterialTakeOff", back_populates="project", cascade="all, delete-orphan")
    spools = relationship("Spool", back_populates="project", cascade="all, delete-orphan")
    wps_pqrs = relationship("WPS_PQR", back_populates="project", cascade="all, delete-orphan")
    welds = relationship("Weld", back_populates="project", cascade="all, delete-orphan")
    pipe_supports = relationship("PipeSupport", back_populates="project", cascade="all, delete-orphan")
    test_packages = relationship("TestPackage", back_populates="project", cascade="all, delete-orphan")
    test_requests = relationship("TestRequest", back_populates="project", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    transmittals = relationship("Transmittal", back_populates="project", cascade="all, delete-orphan")
    handover_packages = relationship("HandoverPackage", back_populates="project", cascade="all, delete-orphan")
    project_actions = relationship("ProjectAction", back_populates="project", cascade="all, delete-orphan")
    work_fronts = relationship("WorkFront", back_populates="project", cascade="all, delete-orphan")
    work_teams = relationship("WorkTeam", back_populates="project", cascade="all, delete-orphan")
    site_machines = relationship("SiteMachine", back_populates="project", cascade="all, delete-orphan")
    field_sync_events = relationship("FieldSyncEvent", back_populates="project", cascade="all, delete-orphan")
    field_attachments = relationship("FieldAttachment", back_populates="project", cascade="all, delete-orphan")
    ai_insights = relationship("AIInsight", back_populates="project", cascade="all, delete-orphan")
    execution_events = relationship("ExecutionEvent", back_populates="project", cascade="all, delete-orphan")
    welders = relationship("Welder", back_populates="project", cascade="all, delete-orphan")
    punch_items = relationship("PunchItem", back_populates="project", cascade="all, delete-orphan")
    ncr_records = relationship("NCRRecord", back_populates="project", cascade="all, delete-orphan")
    itp_items = relationship("ITPItem", back_populates="project", cascade="all, delete-orphan")
    valve_records = relationship("ValveRecord", back_populates="project", cascade="all, delete-orphan")
    memberships = relationship("ProjectMembership", back_populates="project", cascade="all, delete-orphan")


class Area(Base, ReprMixin):
    __tablename__ = "areas"
    _repr_fields = ("id", "name")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)

    project = relationship("Project", back_populates="areas")
    line_items = relationship("LineListItem", back_populates="area")
    spools = relationship("Spool", back_populates="area")

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_area_name_per_project"),
    )


# ══════════════════════════════════════════════
#  3. Line List & Material
# ══════════════════════════════════════════════

class LineListItem(Base, TimestampMixin, ReprMixin):
    __tablename__ = "line_list"
    _repr_fields = ("id", "line_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True, index=True)
    line_number = Column(String(100), nullable=False, index=True)
    pid_number = Column(String(100), index=True)
    iso_number = Column(String(100), index=True)
    fluid_code = Column(String(50))
    fluid_name = Column(String(150))
    fluid_service = Column(String(80))
    design_pressure_barg = Column(Float)
    design_temp_c = Column(Float)
    operating_pressure_barg = Column(Float)
    operating_temp_c = Column(Float)
    test_pressure_barg = Column(Float)
    test_medium = Column(String(50), default="Water")
    pipe_class = Column(String(50), index=True)
    pipe_spec = Column(String(100))
    size_nps = Column(String(30))
    schedule = Column(String(30))
    material = Column(String(100))
    insulation = Column(String(50))
    tracing = Column(String(50))
    painting_code = Column(String(50))
    ndt_percent_rt = Column(Float, default=0)
    ndt_percent_ut = Column(Float, default=0)
    pwht_required = Column(Boolean, default=False)
    from_point = Column(String(150))
    to_point = Column(String(150))
    status = Column(String(30), default="Active", index=True)
    remarks = Column(Text)

    project = relationship("Project", back_populates="line_items")
    area = relationship("Area", back_populates="line_items")

    __table_args__ = (
        UniqueConstraint("project_id", "line_number", name="uq_line_per_project"),
    )


class MaterialRequisition(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "material_requisitions"
    _repr_fields = ("id", "mr_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    mr_number = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text)
    required_date = Column(Date)
    status = Column(String(30), default="Open", index=True)

    project = relationship("Project", back_populates="material_requisitions")
    purchase_orders = relationship("PurchaseOrder", back_populates="material_requisition")


class PurchaseOrder(Base, ReprMixin):
    __tablename__ = "purchase_orders"
    _repr_fields = ("id", "po_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    mr_id = Column(Integer, ForeignKey("material_requisitions.id", ondelete="SET NULL"), nullable=True)
    po_number = Column(String(100), unique=True, nullable=False, index=True)
    supplier = Column(String(200))
    order_date = Column(Date)
    delivery_date = Column(Date)
    status = Column(String(30), default="Open", index=True)

    project = relationship("Project", back_populates="purchase_orders")
    material_requisition = relationship("MaterialRequisition", back_populates="purchase_orders")
    material_items = relationship("MaterialItem", back_populates="purchase_order")


class MaterialItem(Base, ReprMixin):
    __tablename__ = "material_items"
    _repr_fields = ("id", "material_type", "heat_number")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    po_id = Column(Integer, ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True)
    material_type = Column(String(100), nullable=False)
    spec_grade = Column(String(200))
    size = Column(String(50))
    heat_number = Column(String(100), index=True)
    batch_number = Column(String(100))
    quantity_received = Column(Float, default=0)
    quantity_available = Column(Float, default=0)
    unit = Column(String(20), default="EA")
    location = Column(String(200))
    mtr_received = Column(Boolean, default=False)
    received_date = Column(Date)
    remarks = Column(Text)

    project = relationship("Project", back_populates="material_items")
    purchase_order = relationship("PurchaseOrder", back_populates="material_items")
    preservation_records = relationship("MaterialPreservationRecord", back_populates="material_item")
    document_evidences = relationship("DocumentEvidence", back_populates="material_item")


class MaterialTakeOff(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "material_takeoff"
    _repr_fields = ("id", "line_number", "material_type")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number = Column(String(100), index=True)
    spool_number = Column(String(100), index=True)
    material_type = Column(String(100), nullable=False)
    description = Column(String(300))
    spec_grade = Column(String(200))
    size = Column(String(50))
    quantity_required = Column(Float, default=0)
    quantity_issued = Column(Float, default=0)
    quantity_installed = Column(Float, default=0)
    unit = Column(String(20), default="EA")
    status = Column(String(30), default="Open", index=True)
    remarks = Column(Text)

    project = relationship("Project", back_populates="material_takeoffs")


class MTRRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "mtr_records"
    _repr_fields = ("id", "heat_number", "material_spec")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    heat_number = Column(String(100), nullable=False, index=True)
    certificate_number = Column(String(120), index=True)
    manufacturer = Column(String(200))
    material_spec = Column(String(150))
    material_grade = Column(String(100))
    chemical_c = Column(Float)
    chemical_mn = Column(Float)
    chemical_si = Column(Float)
    chemical_p = Column(Float)
    chemical_s = Column(Float)
    chemical_cr = Column(Float)
    chemical_ni = Column(Float)
    chemical_mo = Column(Float)
    ce_value = Column(Float)
    yield_strength_mpa = Column(Float)
    tensile_strength_mpa = Column(Float)
    elongation_pct = Column(Float)
    impact_temp_c = Column(Float)
    impact_energy_j = Column(Float)
    file_path = Column(String(500))
    status = Column(String(30), default="Accepted", index=True)
    remarks = Column(Text)

    project = relationship("Project")


class MaterialReceiptRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "material_receipt_records"
    _repr_fields = ("id", "mrir_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    mrir_number = Column(String(100), unique=True, nullable=False, index=True)
    po_number = Column(String(100), index=True)
    supplier = Column(String(200))
    delivery_note_no = Column(String(100))
    received_date = Column(Date, default=date.today)
    inspector = Column(String(100))
    visual_inspection = Column(String(30), default="Pass")
    dimensional_inspection = Column(String(30), default="Pass")
    documentation_status = Column(String(30), default="Complete")
    status = Column(String(30), default="Accepted", index=True)
    remarks = Column(Text)

    project = relationship("Project")


class MaterialIssueRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "material_issue_records"
    _repr_fields = ("id", "issue_slip_no", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    issue_slip_no = Column(String(100), unique=True, nullable=False, index=True)
    line_number = Column(String(100), index=True)
    spool_number = Column(String(100), index=True)
    material_item_id = Column(Integer, ForeignKey("material_items.id", ondelete="SET NULL"), nullable=True)
    issued_qty = Column(Float, default=0)
    issued_to = Column(String(150))
    issued_by = Column(String(100))
    issue_date = Column(Date, default=date.today)
    status = Column(String(30), default="Issued", index=True)
    remarks = Column(Text)

    project = relationship("Project")
    material_item = relationship("MaterialItem")


# ══════════════════════════════════════════════
#  4. Spool & Welding
# ══════════════════════════════════════════════

class Spool(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "spools"
    _repr_fields = ("id", "spool_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True)
    spool_number = Column(String(100), unique=True, nullable=False, index=True)
    line_number = Column(String(100), index=True)
    pipe_class = Column(String(50))
    iso_number = Column(String(100))
    status = Column(String(30), default="Prefabrication", index=True)
    weight_kg = Column(Float)
    released_date = Column(Date)
    installed_date = Column(Date)

    project = relationship("Project", back_populates="spools")
    area = relationship("Area", back_populates="spools")
    shop_welds = relationship("Weld", back_populates="spool", cascade="all, delete-orphan")
    dimensional_checks = relationship("DimensionalCheckRecord", back_populates="spool")


class SpoolErectionRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "spool_erection_records"
    _repr_fields = ("id", "spool_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    spool_id = Column(Integer, ForeignKey("spools.id", ondelete="CASCADE"), nullable=True, index=True)
    spool_number = Column(String(100), nullable=False, index=True)
    line_number = Column(String(100), index=True)
    erected_date = Column(Date, default=date.today)
    erected_by = Column(String(150))
    rigging_supervisor = Column(String(100))
    elevation_checked = Column(Boolean, default=True)
    orientation_checked = Column(Boolean, default=True)
    status = Column(String(30), default="Erected", index=True)
    remarks = Column(Text)

    project = relationship("Project")
    spool = relationship("Spool")


class WPS_PQR(Base, ReprMixin):
    __tablename__ = "wps_pqr"
    _repr_fields = ("id", "wps_id")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    wps_id = Column(String(100), unique=True, nullable=False, index=True)
    pqr_id = Column(String(100), nullable=True)
    description = Column(Text)
    welding_process = Column(String(50))
    base_material = Column(String(200))
    filler_material = Column(String(200))
    preheat_min_c = Column(Float)
    interpass_max_c = Column(Float)
    pwht_required = Column(Boolean, default=False)

    project = relationship("Project", back_populates="wps_pqrs")
    welds = relationship("Weld", back_populates="wps_pqr")
    welders = relationship("Welder", back_populates="wps_pqr")


class Weld(Base, TimestampMixin, ReprMixin, SoftDeleteMixin):
    __tablename__ = "welds"
    _repr_fields = ("id", "weld_id", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    spool_id = Column(Integer, ForeignKey("spools.id", ondelete="SET NULL"), nullable=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True)
    weld_id = Column(String(100), unique=True, nullable=False, index=True)
    weld_type = Column(String(30), default="Shop", index=True)
    line_number = Column(String(100), index=True)
    iso_number = Column(String(100), index=True)
    joint_type = Column(String(50))
    size = Column(String(50))
    wall_thickness_mm = Column(Float)
    material = Column(String(100))
    wps_pqr_id = Column(Integer, ForeignKey("wps_pqr.id", ondelete="SET NULL"), nullable=True)
    welder_id = Column(String(100), index=True)
    welder_name = Column(String(150))
    fitup_inspector = Column(String(100))
    fitup_date = Column(Date)
    weld_start_datetime = Column(DateTime)
    weld_end_datetime = Column(DateTime)
    preheat_temp_c = Column(Float)
    interpass_temp_c = Column(Float)
    filler_heat_no = Column(String(100))
    root_consumable = Column(String(100))
    fill_consumable = Column(String(100))
    status = Column(String(30), default="Pending", index=True)
    repair_count = Column(Integer, default=0)
    pwht_done = Column(Boolean, default=False)
    pwht_date = Column(Date)
    remarks = Column(Text)
    created_by = Column(String(100))
    updated_by = Column(String(100))

    project = relationship("Project", back_populates="welds")
    spool = relationship("Spool", back_populates="shop_welds")
    wps_pqr = relationship("WPS_PQR", back_populates="welds")
    ndt_records = relationship("NDTRecord", back_populates="weld", cascade="all, delete-orphan")
    history = relationship(
        "JointHistory", back_populates="weld",
        cascade="all, delete-orphan", order_by="JointHistory.timestamp",
    )
    pwht_records = relationship("PWHTRecord", back_populates="weld", cascade="all, delete-orphan")
    test_packages = relationship("TestPackage", secondary="test_package_welds", back_populates="welds")


class JointHistory(Base, ReprMixin):
    __tablename__ = "joint_history"
    _repr_fields = ("id", "event_type")

    id = Column(Integer, primary_key=True, autoincrement=True)
    weld_id_fk = Column(Integer, ForeignKey("welds.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    old_value = Column(String(200))
    new_value = Column(String(200))
    notes = Column(Text)
    user_name = Column(String(100))
    timestamp = Column(DateTime, default=_utcnow, index=True)

    weld = relationship("Weld", back_populates="history")


class NDTRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "ndt_records"
    _repr_fields = ("id", "ndt_method", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    weld_id_fk = Column(Integer, ForeignKey("welds.id", ondelete="CASCADE"), nullable=False, index=True)
    ndt_method = Column(String(10), nullable=False, index=True)
    inspection_date = Column(Date)
    inspector_id = Column(String(100), index=True)
    result = Column(String(20), default="Pending", index=True)
    report_number = Column(String(100))
    remarks = Column(Text)

    weld = relationship("Weld", back_populates="ndt_records")


# ══════════════════════════════════════════════
#  5. Pipe Support & Test Packages
# ══════════════════════════════════════════════

class PipeSupport(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "pipe_supports"
    _repr_fields = ("id", "support_tag", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True)
    support_tag = Column(String(100), nullable=False, index=True)
    support_type = Column(String(80))
    line_number = Column(String(100), index=True)
    iso_number = Column(String(100))
    drawing_no = Column(String(100))
    location_desc = Column(String(200))
    status = Column(String(30), default="Pending", index=True)
    installed_date = Column(Date)
    inspector = Column(String(100))
    remarks = Column(Text)

    project = relationship("Project", back_populates="pipe_supports")

    __table_args__ = (
        UniqueConstraint("project_id", "support_tag", name="uq_support_per_project"),
    )


class TestPackage(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "test_packages"
    _repr_fields = ("id", "package_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True)
    package_number = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(300))
    test_medium = Column(String(50), default="Water")
    test_pressure_bar = Column(Float)
    test_duration_min = Column(Integer)
    test_date = Column(Date)
    status = Column(String(30), default="Planned", index=True)
    line_numbers = Column(Text)
    punch_a_count = Column(Integer, default=0)
    punch_b_count = Column(Integer, default=0)
    punch_c_count = Column(Integer, default=0)
    certificate_no = Column(String(100))
    tested_by = Column(String(100))
    witnessed_by = Column(String(100))
    remarks = Column(Text)

    project = relationship("Project", back_populates="test_packages")
    welds = relationship("Weld", secondary="test_package_welds", back_populates="test_packages")
    punch_items = relationship("PunchItem", back_populates="test_package")
    reinstatement_items = relationship("ReinstatementItem", back_populates="test_package")
    leak_test_records = relationship("LeakTestRecord", back_populates="test_package")


class TestPackageWeld(Base):
    __tablename__ = "test_package_welds"
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="CASCADE"), primary_key=True)
    weld_id = Column(Integer, ForeignKey("welds.id", ondelete="CASCADE"), primary_key=True)


class BlindListRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "blind_list_records"
    _repr_fields = ("id", "blind_tag", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    blind_tag = Column(String(100), nullable=False, index=True)
    line_number = Column(String(100), index=True)
    location_desc = Column(String(200))
    size_nps = Column(String(30))
    rating_class = Column(String(30))
    installed_date = Column(Date)
    installed_by = Column(String(100))
    removed_date = Column(Date)
    removed_by = Column(String(100))
    status = Column(String(30), default="Installed", index=True)
    remarks = Column(Text)

    project = relationship("Project")
    test_package = relationship("TestPackage")


class TestRequest(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "test_requests"
    _repr_fields = ("id", "request_no", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    request_no = Column(String(100), unique=True, nullable=False, index=True)
    request_type = Column(String(50), nullable=False, index=True)
    method = Column(String(50))
    weld_id = Column(String(100), index=True)
    line_number = Column(String(100), index=True)
    spool_number = Column(String(100))
    iso_number = Column(String(100))
    location = Column(String(200))
    requested_by = Column(String(100))
    request_date = Column(Date, default=date.today)
    required_date = Column(Date)
    priority = Column(String(20), default="Normal", index=True)
    status = Column(String(30), default="Open", index=True)
    assigned_to = Column(String(100))
    completed_date = Column(Date)
    result = Column(String(50))
    remarks = Column(Text)

    project = relationship("Project", back_populates="test_requests")


# ══════════════════════════════════════════════
#  6. Reports
# ══════════════════════════════════════════════

class WeldReportDraft(Base, ReprMixin):
    __tablename__ = "weld_report_drafts"
    _repr_fields = ("id", "report_no", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_no = Column(String(100), unique=True, nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    weld_pk = Column(Integer, ForeignKey("welds.id", ondelete="SET NULL"), nullable=True, index=True)
    line_number = Column(String(100), index=True)
    iso_number = Column(String(100))
    weld_no = Column(String(100), index=True)
    spool_no = Column(String(100), index=True)
    welder_id = Column(String(100))
    welder_name = Column(String(150))
    weld_date = Column(Date)
    joint_type = Column(String(50))
    process = Column(String(50))
    wps_id = Column(String(100))
    filler_material = Column(String(150))
    preheat = Column(String(50))
    visual_result = Column(String(30), default="Pending")
    rt_no = Column(String(100))
    rt_result = Column(String(30))
    pt_no = Column(String(100))
    pt_result = Column(String(30))
    ut_no = Column(String(100))
    ut_result = Column(String(30))
    pwht = Column(String(30))
    contractor = Column(String(150))
    remarks = Column(Text)
    prepared_by = Column(String(100))
    prepared_at = Column(DateTime, default=_utcnow)
    status = Column(String(30), default="Draft", index=True)
    approved_by = Column(String(100))
    approved_at = Column(DateTime)

    approved_report = relationship("WeldReport", back_populates="draft", uselist=False)


class WeldReport(Base, ReprMixin):
    __tablename__ = "weld_reports"
    _repr_fields = ("id", "report_no")

    id = Column(Integer, primary_key=True, autoincrement=True)
    draft_id = Column(Integer, ForeignKey("weld_report_drafts.id", ondelete="CASCADE"), unique=True, nullable=False)
    report_no = Column(String(100), unique=True, nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    weld_pk = Column(Integer, ForeignKey("welds.id", ondelete="SET NULL"), nullable=True)
    line_number = Column(String(100), index=True)
    iso_number = Column(String(100))
    weld_no = Column(String(100), index=True)
    spool_no = Column(String(100))
    welder_id = Column(String(100))
    welder_name = Column(String(150))
    weld_date = Column(Date)
    joint_type = Column(String(50))
    process = Column(String(50))
    wps_id = Column(String(100))
    filler_material = Column(String(150))
    preheat = Column(String(50))
    visual_result = Column(String(30))
    rt_no = Column(String(100))
    rt_result = Column(String(30))
    pt_no = Column(String(100))
    pt_result = Column(String(30))
    ut_no = Column(String(100))
    ut_result = Column(String(30))
    pwht = Column(String(30))
    contractor = Column(String(150))
    remarks = Column(Text)
    approved_by = Column(String(100))
    approved_at = Column(DateTime, default=_utcnow)

    draft = relationship("WeldReportDraft", back_populates="approved_report")


class FitupReportDraft(Base, ReprMixin):
    __tablename__ = "fitup_report_drafts"
    _repr_fields = ("id", "report_no", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_no = Column(String(100), unique=True, nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    weld_pk = Column(Integer, ForeignKey("welds.id", ondelete="SET NULL"), nullable=True, index=True)
    line_number = Column(String(100), index=True)
    iso_number = Column(String(100))
    weld_no = Column(String(100), index=True)
    spool_no = Column(String(100))
    fitup_no = Column(String(100))
    fitup_date = Column(Date)
    fitter = Column(String(150))
    contractor = Column(String(150))
    root_gap = Column(String(50))
    hi_low = Column(String(50))
    alignment = Column(String(50))
    bevel = Column(String(50))
    cleanliness = Column(String(50))
    tack_quality = Column(String(50))
    fitup_result = Column(String(30), default="Pending")
    remarks = Column(Text)
    prepared_by = Column(String(100))
    prepared_at = Column(DateTime, default=_utcnow)
    status = Column(String(30), default="Draft", index=True)
    approved_by = Column(String(100))
    approved_at = Column(DateTime)

    approved_report = relationship("FitupReport", back_populates="draft", uselist=False)


class FitupReport(Base, ReprMixin):
    __tablename__ = "fitup_reports"
    _repr_fields = ("id", "report_no")

    id = Column(Integer, primary_key=True, autoincrement=True)
    draft_id = Column(Integer, ForeignKey("fitup_report_drafts.id", ondelete="CASCADE"), unique=True, nullable=False)
    report_no = Column(String(100), unique=True, nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    weld_pk = Column(Integer, ForeignKey("welds.id", ondelete="SET NULL"), nullable=True)
    line_number = Column(String(100), index=True)
    iso_number = Column(String(100))
    weld_no = Column(String(100), index=True)
    spool_no = Column(String(100))
    fitup_no = Column(String(100))
    fitup_date = Column(Date)
    fitter = Column(String(150))
    contractor = Column(String(150))
    root_gap = Column(String(50))
    hi_low = Column(String(50))
    alignment = Column(String(50))
    bevel = Column(String(50))
    cleanliness = Column(String(50))
    tack_quality = Column(String(50))
    fitup_result = Column(String(30))
    remarks = Column(Text)
    approved_by = Column(String(100))
    approved_at = Column(DateTime, default=_utcnow)

    draft = relationship("FitupReportDraft", back_populates="approved_report")


class ProjectAction(Base, ReprMixin):
    __tablename__ = "project_actions"
    _repr_fields = ("id", "action_type", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(String(80), nullable=False, index=True)
    entity_type = Column(String(80))
    entity_id = Column(Integer)
    line_number = Column(String(100), index=True)
    description = Column(Text)
    old_value = Column(String(200))
    new_value = Column(String(200))
    contractor = Column(String(150))
    action_date = Column(DateTime, default=_utcnow, index=True)
    user_name = Column(String(100))
    status = Column(String(30), default="Open", index=True)

    project = relationship("Project", back_populates="project_actions")


# ══════════════════════════════════════════════
#  7. Documents & Transmittals
# ══════════════════════════════════════════════

class Document(Base, TimestampMixin, ReprMixin):
    __tablename__ = "documents"
    _repr_fields = ("id", "doc_number", "revision")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True)
    doc_number = Column(String(100), unique=True, nullable=False, index=True)
    doc_type = Column(String(50), nullable=False, index=True)
    title = Column(String(300))
    revision = Column(String(10), default="0")
    status = Column(String(30), default="Draft", index=True)
    file_path = Column(String(500))
    line_number = Column(String(100), index=True)
    spool_id = Column(Integer, ForeignKey("spools.id", ondelete="SET NULL"), nullable=True)
    weld_id = Column(Integer, ForeignKey("welds.id", ondelete="SET NULL"), nullable=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="SET NULL"), nullable=True)
    discipline = Column(String(50), default="Piping")
    originator = Column(String(100))
    issued_date = Column(Date)
    created_by = Column(String(100))

    project = relationship("Project", back_populates="documents")
    revisions = relationship("DocumentRevision", back_populates="document", cascade="all, delete-orphan")


class DocumentRevision(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "document_revisions"
    _repr_fields = ("id", "revision")

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    revision = Column(String(10), nullable=False)
    file_path = Column(String(500))
    comments = Column(Text)
    reviewed_by = Column(String(100))
    approved_by = Column(String(100))

    document = relationship("Document", back_populates="revisions")


class DocumentEvidence(Base, TimestampMixin, ReprMixin):
    """ثبت مدارک و شواهد مرتبط با ردیابی متریال و اقلام پروژه."""
    __tablename__ = "document_evidences"
    _repr_fields = ("id", "evidence_type", "entity_type", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    material_item_id = Column(Integer, ForeignKey("material_items.id", ondelete="SET NULL"), nullable=True, index=True)
    weld_id_fk = Column(Integer, ForeignKey("welds.id", ondelete="SET NULL"), nullable=True, index=True)
    spool_id = Column(Integer, ForeignKey("spools.id", ondelete="SET NULL"), nullable=True, index=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    document_id_fk = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    evidence_type = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(80), nullable=False, index=True)
    entity_reference = Column(String(150), index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text)
    file_path = Column(String(500), nullable=False)
    file_name = Column(String(255))
    file_size_bytes = Column(Integer)
    mime_type = Column(String(100))
    sha256 = Column(String(64), index=True)
    heat_number = Column(String(100), index=True)
    certificate_number = Column(String(120), index=True)
    supplier = Column(String(200))
    manufacturer = Column(String(200))
    batch_number = Column(String(100))
    status = Column(String(30), default="Pending", index=True)
    verified_by = Column(String(100))
    verified_date = Column(Date)
    rejection_reason = Column(Text)
    source = Column(String(50), default="Manual")
    captured_by = Column(String(100))
    captured_at = Column(DateTime, default=_utcnow)
    remarks = Column(Text)

    project = relationship("Project")
    material_item = relationship("MaterialItem", back_populates="document_evidences")
    weld = relationship("Weld")
    spool = relationship("Spool")
    test_package = relationship("TestPackage")
    document = relationship("Document")

    __table_args__ = (
        Index("ix_doc_evidence_entity", "entity_type", "entity_reference"),
        Index("ix_doc_evidence_project_type", "project_id", "evidence_type"),
    )


class Transmittal(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "transmittals"
    _repr_fields = ("id", "transmittal_no")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    transmittal_no = Column(String(100), unique=True, nullable=False)
    to_company = Column(String(200))
    purpose = Column(Text)

    project = relationship("Project", back_populates="transmittals")
    items = relationship("TransmittalItem", back_populates="transmittal", cascade="all, delete-orphan")


class TransmittalItem(Base, ReprMixin):
    __tablename__ = "transmittal_items"
    _repr_fields = ("id", "revision")

    id = Column(Integer, primary_key=True, autoincrement=True)
    transmittal_id = Column(Integer, ForeignKey("transmittals.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id_fk = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    revision = Column(String(10))

    transmittal = relationship("Transmittal", back_populates="items")


# ══════════════════════════════════════════════
#  8. Handover & Audit
# ══════════════════════════════════════════════

class HandoverPackage(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "handover_packages"
    _repr_fields = ("id", "package_no", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    package_no = Column(String(100), unique=True, nullable=False, index=True)
    system_name = Column(String(200))
    subsystem = Column(String(200))
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(30), default="In Progress", index=True)
    punch_open = Column(Integer, default=0)
    docs_complete = Column(Boolean, default=False)
    tests_complete = Column(Boolean, default=False)
    handed_over_date = Column(Date)
    accepted_by = Column(String(100))
    remarks = Column(Text)

    project = relationship("Project", back_populates="handover_packages")


class AuditLog(Base, ReprMixin):
    __tablename__ = "audit_logs"
    _repr_fields = ("id", "action")

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(200), nullable=False, index=True)
    table_name = Column(String(100), index=True)
    record_id = Column(Integer)
    details = Column(Text)
    timestamp = Column(DateTime, default=_utcnow, index=True)

    user = relationship("User", back_populates="audit_logs")


class ProjectMembership(Base, TimestampMixin, ReprMixin):
    __tablename__ = "project_memberships"
    _repr_fields = ("id", "user_id", "project_id", "role")

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(30), default="viewer")
    is_active = Column(Boolean, default=True, index=True)

    user = relationship("User", back_populates="project_memberships")
    project = relationship("Project", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("user_id", "project_id", name="uq_user_project_membership"),
    )


class ApiCredential(Base, TimestampMixin, ReprMixin):
    __tablename__ = "api_credentials"
    _repr_fields = ("id", "name", "is_active")

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    api_key = Column(String(255), unique=True, nullable=False, index=True)
    # Compatibility fields used by the v5 enterprise API-key service.
    token_prefix = Column(String(80), index=True)
    token_hash = Column(String(255), index=True)
    scopes = Column(String(500), default="read")
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    ip_whitelist = Column(String(500))
    revoked_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    scope = Column(String(200), default="read")
    is_active = Column(Boolean, default=True, index=True)
    expires_at = Column(DateTime)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_by_user = relationship("User", back_populates="api_credentials")


# ══════════════════════════════════════════════
#  9. Work Front & Resources
# ══════════════════════════════════════════════

class WorkFront(Base, TimestampMixin, ReprMixin):
    __tablename__ = "work_fronts"
    _repr_fields = ("id", "front_code", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    front_code = Column(String(100), nullable=False, index=True)
    area = Column(String(100), index=True)
    discipline = Column(String(50), default="Piping", index=True)
    activity_type = Column(String(80), nullable=False, index=True)
    description = Column(String(300))
    line_number = Column(String(100), index=True)
    iso_number = Column(String(100))
    spool_number = Column(String(100))
    planned_start = Column(Date)
    planned_finish = Column(Date)
    priority = Column(String(20), default="Normal", index=True)
    status = Column(String(30), default="Planned", index=True)
    readiness = Column(String(30), default="Ready", index=True)
    blocker = Column(String(300))
    progress_pct = Column(Float, default=0)
    target_qty = Column(Float, default=0)
    actual_qty = Column(Float, default=0)
    unit = Column(String(30), default="EA")
    shift = Column(String(30), default="Day")
    supervisor = Column(String(100))
    remarks = Column(Text)
    created_by = Column(String(100))

    project = relationship("Project", back_populates="work_fronts")
    team_assignments = relationship("WorkAssignment", back_populates="work_front", cascade="all, delete-orphan")
    teams = relationship("WorkTeam", back_populates="current_front")
    machines = relationship("SiteMachine", back_populates="current_front")

    __table_args__ = (
        UniqueConstraint("project_id", "front_code", name="uq_workfront_code_per_project"),
    )


class WorkTeam(Base, ReprMixin):
    __tablename__ = "work_teams"
    _repr_fields = ("id", "team_code", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    team_code = Column(String(80), nullable=False, index=True)
    team_name = Column(String(150), nullable=False)
    discipline = Column(String(50), default="Piping")
    skill = Column(String(100))
    supervisor = Column(String(100))
    manpower = Column(Integer, default=0)
    available_from = Column(Date)
    shift = Column(String(30), default="Day")
    status = Column(String(30), default="Available", index=True)
    current_front_id = Column(Integer, ForeignKey("work_fronts.id", ondelete="SET NULL"), nullable=True)
    remarks = Column(Text)

    project = relationship("Project", back_populates="work_teams")
    current_front = relationship("WorkFront", back_populates="teams")

    __table_args__ = (
        UniqueConstraint("project_id", "team_code", name="uq_team_code_per_project"),
    )


class SiteMachine(Base, ReprMixin):
    __tablename__ = "site_machines"
    _repr_fields = ("id", "machine_code", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    machine_code = Column(String(80), nullable=False, index=True)
    machine_type = Column(String(100), nullable=False)
    description = Column(String(200))
    capacity = Column(String(100))
    operator = Column(String(100))
    status = Column(String(30), default="Available", index=True)
    current_front_id = Column(Integer, ForeignKey("work_fronts.id", ondelete="SET NULL"), nullable=True)
    next_available = Column(Date)
    remarks = Column(Text)

    project = relationship("Project", back_populates="site_machines")
    current_front = relationship("WorkFront", back_populates="machines")

    __table_args__ = (
        UniqueConstraint("project_id", "machine_code", name="uq_machine_code_per_project"),
    )


class WorkAssignment(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "work_assignments"
    _repr_fields = ("id", "resource_type", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    work_front_id = Column(Integer, ForeignKey("work_fronts.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_type = Column(String(20), nullable=False, index=True)
    resource_id = Column(Integer, nullable=False, index=True)
    assigned_date = Column(Date, default=date.today)
    release_date = Column(Date)
    status = Column(String(30), default="Assigned", index=True)
    planned_hours = Column(Float, default=0)
    actual_hours = Column(Float, default=0)
    notes = Column(Text)
    assigned_by = Column(String(100))

    work_front = relationship("WorkFront", back_populates="team_assignments")

    __table_args__ = (
        Index("ix_work_assignment_resource", "resource_type", "resource_id"),
    )


# ══════════════════════════════════════════════
#  10. Field Sync & Offline
# ══════════════════════════════════════════════

class FieldSyncEvent(Base, ReprMixin):
    __tablename__ = "field_sync_events"
    _repr_fields = ("id", "event_type", "sync_status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(100), index=True)
    event_uuid = Column(String(80), unique=True, nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(80), nullable=False)
    entity_id = Column(Integer, nullable=True)
    payload_json = Column(Text, nullable=False)
    captured_at = Column(DateTime, default=_utcnow, index=True)
    sync_status = Column(String(20), default="Pending", index=True)
    synced_at = Column(DateTime)
    error_message = Column(Text)

    project = relationship("Project", back_populates="field_sync_events")


class FieldAttachment(Base, ReprMixin):
    __tablename__ = "field_attachments"
    _repr_fields = ("id", "entity_type", "file_path")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(80), nullable=False, index=True)
    entity_id = Column(Integer, nullable=True)
    file_path = Column(String(500), nullable=False)
    caption = Column(String(300))
    captured_by = Column(String(100))
    captured_at = Column(DateTime, default=_utcnow)
    sha256 = Column(String(64), index=True)
    sync_status = Column(String(20), default="Local")

    project = relationship("Project", back_populates="field_attachments")


# ══════════════════════════════════════════════
#  11. AI / Insights / Predictions
# ══════════════════════════════════════════════

class AIInsight(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "ai_insights"
    _repr_fields = ("id", "insight_type", "severity")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    insight_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), default="Info", index=True)
    title = Column(String(250), nullable=False)
    recommendation = Column(Text, nullable=False)
    evidence_json = Column(Text)
    model_source = Column(String(80), default="rule-engine")
    resolved = Column(Boolean, default=False, index=True)

    project = relationship("Project", back_populates="ai_insights")


class ProductivitySnapshot(Base, ReprMixin):
    __tablename__ = "productivity_snapshots"
    _repr_fields = ("id", "resource_code", "work_date")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_type = Column(String(20), nullable=False, index=True)
    resource_code = Column(String(100), nullable=False, index=True)
    work_front_id = Column(Integer, ForeignKey("work_fronts.id", ondelete="SET NULL"), nullable=True)
    work_date = Column(Date, nullable=False, index=True)
    planned_hours = Column(Float, default=0)
    actual_hours = Column(Float, default=0)
    productive_hours = Column(Float, default=0)
    idle_hours = Column(Float, default=0)
    quantity = Column(Float, default=0)
    unit = Column(String(30), default="EA")
    notes = Column(Text)


class TurnoverDossier(Base, ReprMixin):
    __tablename__ = "turnover_dossiers"
    _repr_fields = ("id", "dossier_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    dossier_number = Column(String(100), unique=True, nullable=False, index=True)
    scope_type = Column(String(50), default="Line")
    scope_key = Column(String(150), nullable=False, index=True)
    status = Column(String(30), default="Draft", index=True)
    completeness_pct = Column(Float, default=0)
    generated_path = Column(String(500))
    generated_at = Column(DateTime)
    generated_by = Column(String(100))
    remarks = Column(Text)


# ══════════════════════════════════════════════
#  12. Execution OS
# ══════════════════════════════════════════════

class ExecutionEvent(Base, ReprMixin):
    __tablename__ = "execution_events"
    _repr_fields = ("id", "event_type", "entity_type")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(80), nullable=False, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    line_number = Column(String(100), index=True)
    old_value = Column(Text)
    new_value = Column(Text)
    source = Column(String(40), default="application")
    actor = Column(String(100))
    occurred_at = Column(DateTime, default=_utcnow, index=True)
    processed_at = Column(DateTime, index=True)
    correlation_id = Column(String(80), index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    username = Column(String(100))
    client_ip = Column(String(64))

    project = relationship("Project", back_populates="execution_events")
    impacts = relationship("ExecutionImpact", back_populates="event", cascade="all, delete-orphan")


class ExecutionGraphNode(Base, TimestampMixin, ReprMixin):
    __tablename__ = "execution_graph_nodes"
    _repr_fields = ("id", "node_key", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    node_key = Column(String(180), nullable=False, index=True)
    node_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    label = Column(String(250), nullable=False)
    status = Column(String(50), default="Unknown", index=True)
    line_number = Column(String(100), index=True)
    risk_score = Column(Float, default=0)

    __table_args__ = (
        UniqueConstraint("project_id", "node_key", name="uq_execution_node"),
    )


class ExecutionGraphEdge(Base, TimestampMixin, ReprMixin):
    __tablename__ = "execution_graph_edges"
    _repr_fields = ("id", "from_key", "to_key")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    from_key = Column(String(180), nullable=False, index=True)
    to_key = Column(String(180), nullable=False, index=True)
    relation = Column(String(60), nullable=False, default="DEPENDS_ON")
    weight = Column(Float, default=1.0)

    __table_args__ = (
        UniqueConstraint("project_id", "from_key", "to_key", "relation", name="uq_execution_edge"),
    )


class ExecutionImpact(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "execution_impacts"
    _repr_fields = ("id", "severity", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(Integer, ForeignKey("execution_events.id", ondelete="CASCADE"), nullable=False, index=True)
    source_node_key = Column(String(180), nullable=False, index=True)
    affected_node_key = Column(String(180), nullable=False, index=True)
    affected_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), default="Medium", index=True)
    probability = Column(Float, default=0.5)
    impact_score = Column(Float, default=0)
    explanation = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=False)
    status = Column(String(30), default="Open", index=True)
    resolved_at = Column(DateTime)

    event = relationship("ExecutionEvent", back_populates="impacts")


class ExecutionForecast(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "execution_forecasts"
    _repr_fields = ("id", "forecast_type", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    forecast_type = Column(String(60), nullable=False, index=True)
    horizon_hours = Column(Integer, default=72)
    severity = Column(String(20), default="Medium", index=True)
    title = Column(String(250), nullable=False)
    probability = Column(Float, default=0.5)
    impact_score = Column(Float, default=0)
    evidence_json = Column(Text)
    recommended_action = Column(Text, nullable=False)
    generated_at = Column(DateTime, default=_utcnow, index=True)
    valid_until = Column(DateTime)
    status = Column(String(30), default="Open", index=True)


# ══════════════════════════════════════════════
#  13. Site Coverage & QA/QC
# ══════════════════════════════════════════════

class Welder(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "welders"
    _repr_fields = ("id", "stencil_no", "full_name")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    stencil_no = Column(String(50), nullable=False, index=True)
    full_name = Column(String(150), nullable=False)
    national_id = Column(String(50))
    welding_processes = Column(String(100))
    qualified_positions = Column(String(100))
    qualified_thickness_min_mm = Column(Float)
    qualified_thickness_max_mm = Column(Float)
    qualified_diameter_min_inch = Column(Float)
    qualified_material_p_no = Column(String(50))
    wps_pqr_id = Column(Integer, ForeignKey("wps_pqr.id", ondelete="SET NULL"), nullable=True)
    qualification_date = Column(Date)
    expiry_date = Column(Date, index=True)
    certificate_no = Column(String(100))
    is_active = Column(Boolean, default=True, index=True)
    remarks = Column(Text)

    project = relationship("Project", back_populates="welders")
    wps_pqr = relationship("WPS_PQR", back_populates="welders")

    __table_args__ = (
        UniqueConstraint("project_id", "stencil_no", name="uq_welder_stencil_per_project"),
    )


class PunchItem(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "punch_items"
    _repr_fields = ("id", "category", "is_cleared")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    line_number = Column(String(100), index=True)
    spool_number = Column(String(100))
    weld_id = Column(String(100))
    category = Column(String(10), nullable=False, index=True)
    description = Column(Text, nullable=False)
    location_desc = Column(String(300))
    raised_by = Column(String(100))
    raised_date = Column(Date, default=date.today)
    cleared_by = Column(String(100))
    cleared_date = Column(Date)
    is_cleared = Column(Boolean, default=False, index=True)
    status = Column(String(30), default="Open", index=True)
    remarks = Column(Text)

    project = relationship("Project", back_populates="punch_items")
    test_package = relationship("TestPackage", back_populates="punch_items")


class NCRRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "ncr_records"
    _repr_fields = ("id", "ncr_no", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    ncr_no = Column(String(100), unique=True, nullable=False, index=True)
    item_type = Column(String(50), nullable=False)
    item_reference = Column(String(150))
    line_number = Column(String(100), index=True)
    description = Column(Text, nullable=False)
    root_cause = Column(Text)
    disposition = Column(String(50))
    corrective_action = Column(Text)
    preventive_action = Column(Text)
    raised_by = Column(String(100))
    raised_date = Column(Date, default=date.today)
    closed_by = Column(String(100))
    closed_date = Column(Date)
    status = Column(String(30), default="Open", index=True)
    remarks = Column(Text)

    project = relationship("Project", back_populates="ncr_records")


class ITPItem(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "itp_items"
    _repr_fields = ("id", "itp_number", "activity_description", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    itp_number = Column(String(100), index=True)
    activity_code = Column(String(50), index=True)
    activity_description = Column(String(300), nullable=False)
    controlling_doc = Column(String(200))
    acceptance_criteria = Column(String(300))
    verifying_doc = Column(String(200))
    contractor_point = Column(String(20), default="H")
    client_point = Column(String(20), default="W")
    tpi_point = Column(String(20), default="R")
    status = Column(String(30), default="Open", index=True)
    inspected_date = Column(Date)
    inspected_by = Column(String(100))
    remarks = Column(Text)

    project = relationship("Project", back_populates="itp_items")


class ValveRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "valve_records"
    _repr_fields = ("id", "valve_tag", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    valve_tag = Column(String(100), nullable=False, index=True)
    line_number = Column(String(100), index=True)
    valve_type = Column(String(50))
    size_nps = Column(String(30))
    rating_class = Column(String(30))
    body_material = Column(String(100))
    trim_material = Column(String(100))
    heat_number = Column(String(100))
    manufacturer = Column(String(150))
    model_number = Column(String(100))
    hydro_shell_test = Column(Boolean, default=False)
    hydro_shell_pressure_bar = Column(Float)
    hydro_shell_date = Column(Date)
    hydro_seat_test = Column(Boolean, default=False)
    hydro_seat_pressure_bar = Column(Float)
    hydro_seat_date = Column(Date)
    test_witness = Column(String(100))
    installed_date = Column(Date)
    installed_by = Column(String(100))
    status = Column(String(30), default="Received", index=True)
    remarks = Column(Text)

    project = relationship("Project", back_populates="valve_records")

    __table_args__ = (
        UniqueConstraint("project_id", "valve_tag", name="uq_valve_per_project"),
    )


class PWHTRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "pwht_records"
    _repr_fields = ("id", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    weld_id_fk = Column(Integer, ForeignKey("welds.id", ondelete="CASCADE"), nullable=False, index=True)
    pwht_procedure_no = Column(String(100))
    heating_method = Column(String(50))
    soak_temperature_c = Column(Float)
    soak_duration_hours = Column(Float)
    heating_rate_c_per_hr = Column(Float)
    cooling_rate_c_per_hr = Column(Float)
    thermocouple_count = Column(Integer)
    chart_number = Column(String(100))
    chart_file_path = Column(String(500))
    hardness_test_done = Column(Boolean, default=False)
    hardness_max_hv = Column(Float)
    performed_by = Column(String(100))
    performed_date = Column(Date)
    witnessed_by = Column(String(100))
    result = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)

    weld = relationship("Weld", back_populates="pwht_records")


class FlangeTorqueRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "flange_torque_records"
    _repr_fields = ("id", "flange_tag", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number = Column(String(100), index=True)
    flange_tag = Column(String(100), index=True)
    flange_type = Column(String(50))
    size_nps = Column(String(30))
    rating_class = Column(String(30))
    gasket_type = Column(String(100))
    bolt_spec = Column(String(100))
    bolt_size = Column(String(30))
    bolt_count = Column(Integer)
    torque_value_nm = Column(Float)
    torque_method = Column(String(50))
    pass_1_pct = Column(Float, default=30)
    pass_2_pct = Column(Float, default=60)
    pass_3_pct = Column(Float, default=100)
    pass_4_cross = Column(Boolean, default=True)
    performed_by = Column(String(100))
    performed_date = Column(Date)
    witnessed_by = Column(String(100))
    status = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)


class BlastingRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "blasting_records"
    _repr_fields = ("id", "line_number", "cleanliness_grade", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number = Column(String(100), index=True)
    spool_number = Column(String(100), index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True)
    abrasive_type = Column(String(80), default="Garnet")
    cleanliness_grade = Column(String(30), default="Sa 2.5")
    surface_profile_micron = Column(Float)
    dust_level = Column(String(20), default="Class 2")
    salt_contamination_ppm = Column(Float)
    relative_humidity_pct = Column(Float)
    ambient_temp_c = Column(Float)
    steel_temp_c = Column(Float)
    dew_point_c = Column(Float)
    performed_by = Column(String(100))
    performed_date = Column(Date)
    inspector = Column(String(100))
    result = Column(String(30), default="Pass", index=True)
    remarks = Column(Text)


class PaintingRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "painting_records"
    _repr_fields = ("id", "line_number", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number = Column(String(100), index=True)
    spool_number = Column(String(100), index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True)
    painting_code = Column(String(50))
    surface_prep_method = Column(String(50))
    surface_prep_grade = Column(String(30))
    primer_coat = Column(String(100))
    primer_dft_micron = Column(Float)
    intermediate_coat = Column(String(100))
    intermediate_dft_micron = Column(Float)
    finish_coat = Column(String(100))
    finish_dft_micron = Column(Float)
    total_dft_micron = Column(Float)
    color_code = Column(String(50))
    performed_by = Column(String(100))
    performed_date = Column(Date)
    inspector = Column(String(100))
    result = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)


class InsulationRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "insulation_records"
    _repr_fields = ("id", "line_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number = Column(String(100), index=True)
    spool_number = Column(String(100), index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True)
    insulation_type = Column(String(80))
    insulation_material = Column(String(150))
    thickness_mm = Column(Float)
    density_kg_m3 = Column(Float)
    jacket_material = Column(String(100))
    tracing_type = Column(String(50))
    surface_temp_c = Column(Float)
    performed_by = Column(String(100))
    performed_date = Column(Date)
    inspector = Column(String(100))
    status = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)


class WrappingRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "wrapping_records"
    _repr_fields = ("id", "line_number", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number = Column(String(100), index=True)
    spool_number = Column(String(100), index=True)
    weld_id = Column(String(100), index=True)
    wrapping_material = Column(String(150))
    primer_type = Column(String(100))
    overlap_pct = Column(Float, default=50.0)
    holiday_test_voltage_kv = Column(Float)
    holiday_test_result = Column(String(30), default="Pass")
    performed_by = Column(String(100))
    performed_date = Column(Date)
    inspector = Column(String(100))
    result = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)


class FireproofingRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "fireproofing_records"
    _repr_fields = ("id", "structure_tag", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    structure_tag = Column(String(120), index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True)
    material_type = Column(String(150))
    thickness_mm = Column(Float)
    rating_hours = Column(Float)
    performed_by = Column(String(100))
    performed_date = Column(Date)
    inspector = Column(String(100))
    result = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)


# ══════════════════════════════════════════════
#  14. Inspections & Precommissioning
# ══════════════════════════════════════════════

class LeakTestRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "leak_test_records"
    _repr_fields = ("id", "test_type", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    line_number = Column(String(100), index=True)
    test_type = Column(String(50), nullable=False, default="Hydrostatic")
    test_pressure_bar = Column(Float)
    holding_time_min = Column(Integer)
    test_medium = Column(String(50), default="Water")
    gauge_number_1 = Column(String(100))
    gauge_number_2 = Column(String(100))
    temp_ambient_c = Column(Float)
    temp_medium_c = Column(Float)
    performed_by = Column(String(100))
    performed_date = Column(Date)
    witnessed_by = Column(String(100))
    result = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)

    project = relationship("Project")
    test_package = relationship("TestPackage", back_populates="leak_test_records")


class PMIRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "pmi_records"
    _repr_fields = ("id", "component_tag", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number = Column(String(100), index=True)
    component_tag = Column(String(120), index=True)
    component_type = Column(String(80))
    heat_number = Column(String(100), index=True)
    required_material = Column(String(150))
    identified_material = Column(String(150))
    method = Column(String(50), default="XRF")
    instrument_serial = Column(String(100))
    performed_by = Column(String(100))
    performed_date = Column(Date)
    result = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)


class HardnessTestRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "hardness_test_records"
    _repr_fields = ("id", "weld_id_fk", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    weld_id_fk = Column(Integer, ForeignKey("welds.id", ondelete="CASCADE"), nullable=True, index=True)
    line_number = Column(String(100), index=True)
    test_method = Column(String(50), default="Vickers")
    hardness_val_base = Column(Float)
    hardness_val_weld = Column(Float)
    hardness_val_haz = Column(Float)
    max_allowed_hv = Column(Float)
    test_date = Column(Date)
    inspector = Column(String(100))
    result = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)


class FerriteTestRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "ferrite_test_records"
    _repr_fields = ("id", "weld_id_fk", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    weld_id_fk = Column(Integer, ForeignKey("welds.id", ondelete="CASCADE"), nullable=True, index=True)
    line_number = Column(String(100), index=True)
    ferrite_number_fn = Column(Float)
    min_fn = Column(Float)
    max_fn = Column(Float)
    test_date = Column(Date)
    inspector = Column(String(100))
    result = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)


class DimensionalCheckRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "dimensional_check_records"
    _repr_fields = ("id", "check_no", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    spool_id = Column(Integer, ForeignKey("spools.id", ondelete="CASCADE"), nullable=True, index=True)
    check_no = Column(String(100), index=True)
    drawing_no = Column(String(100))
    revision = Column(String(10))
    overall_length_mm = Column(Float)
    tolerance_mm = Column(Float)
    deviation_mm = Column(Float)
    angular_deviation_deg = Column(Float)
    flange_face_deviation_mm = Column(Float)
    performed_by = Column(String(100))
    performed_date = Column(Date)
    inspector = Column(String(100))
    result = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)

    spool = relationship("Spool", back_populates="dimensional_checks")


class MaterialPreservationRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "material_preservation_records"
    _repr_fields = ("id", "material_ref", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    material_item_id = Column(Integer, ForeignKey("material_items.id", ondelete="CASCADE"), nullable=True, index=True)
    material_ref = Column(String(150), index=True)
    preservation_type = Column(String(80))
    storage_location = Column(String(200))
    environment_condition = Column(String(150))
    inspection_frequency_days = Column(Integer, default=30)
    last_inspection_date = Column(Date)
    next_inspection_date = Column(Date, index=True)
    inspector = Column(String(100))
    status = Column(String(30), default="Active", index=True)
    remarks = Column(Text)

    material_item = relationship("MaterialItem", back_populates="preservation_records")


class ReinstatementItem(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "reinstatement_items"
    _repr_fields = ("id", "line_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    line_number = Column(String(100), index=True)
    spool_number = Column(String(100))
    item_type = Column(String(80), nullable=False)
    item_description = Column(String(300))
    original_position = Column(String(200))
    removed_for_test = Column(Boolean, default=True)
    removed_date = Column(Date)
    reinstalled_date = Column(Date)
    torque_applied_nm = Column(Float)
    gasket_replaced = Column(Boolean, default=False)
    performed_by = Column(String(100))
    inspector = Column(String(100))
    status = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)

    test_package = relationship("TestPackage", back_populates="reinstatement_items")


class FlushingRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "flushing_records"
    _repr_fields = ("id", "line_number", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    line_number = Column(String(100), index=True)
    flushing_medium = Column(String(50), default="Water")
    flushing_method = Column(String(50))
    velocity_m_s = Column(Float)
    duration_min = Column(Integer)
    mesh_size = Column(String(30))
    cleanliness_criteria = Column(String(150))
    performed_by = Column(String(100))
    performed_date = Column(Date)
    witnessed_by = Column(String(100))
    result = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)


class DryingRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "drying_records"
    _repr_fields = ("id", "line_number", "dew_point_c", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    line_number = Column(String(100), index=True)
    drying_medium = Column(String(50), default="Hot Air")
    dew_point_c = Column(Float)
    target_dew_point_c = Column(Float, default=-20.0)
    duration_hours = Column(Float)
    performed_by = Column(String(100))
    performed_date = Column(Date)
    witnessed_by = Column(String(100))
    result = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)


class BlowingRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "blowing_records"
    _repr_fields = ("id", "line_number", "target_plate_result", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    line_number = Column(String(100), index=True)
    blowing_medium = Column(String(50), default="Air")
    pressure_bar = Column(Float)
    target_plate_material = Column(String(100))
    target_plate_result = Column(String(30), default="Clean")
    performed_by = Column(String(100))
    performed_date = Column(Date)
    witnessed_by = Column(String(100))
    result = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)


class PurgingRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "purging_records"
    _repr_fields = ("id", "line_number", "o2_content_pct", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    line_number = Column(String(100), index=True)
    purging_medium = Column(String(50), default="Nitrogen")
    pressure_bar = Column(Float)
    o2_content_pct = Column(Float)
    target_o2_pct = Column(Float, default=0.5)
    performed_by = Column(String(100))
    performed_date = Column(Date)
    witnessed_by = Column(String(100))
    result = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)


class BoxUpRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "boxup_records"
    _repr_fields = ("id", "equipment_tag", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    equipment_tag = Column(String(120), index=True)
    line_number = Column(String(100), index=True)
    manway_flange_no = Column(String(100))
    internal_cleanliness = Column(Boolean, default=True)
    internals_installed = Column(Boolean, default=True)
    debris_removed = Column(Boolean, default=True)
    gasket_verified = Column(Boolean, default=True)
    bolting_torqued = Column(Boolean, default=True)
    inspector = Column(String(100))
    client_witness = Column(String(100))
    inspected_date = Column(Date)
    status = Column(String(30), default="Approved", index=True)
    remarks = Column(Text)

    project = relationship("Project")
    test_package = relationship("TestPackage")


class SpringHangerRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "spring_hanger_records"
    _repr_fields = ("id", "support_tag", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    support_tag = Column(String(100), nullable=False, index=True)
    line_number = Column(String(100), index=True)
    hanger_type = Column(String(50))
    cold_load_kn = Column(Float)
    hot_load_kn = Column(Float)
    cold_travel_mm = Column(Float)
    hot_travel_mm = Column(Float)
    pin_removed = Column(Boolean, default=False)
    pin_removed_date = Column(Date)
    inspector = Column(String(100))
    status = Column(String(30), default="Locked", index=True)
    remarks = Column(Text)

    project = relationship("Project")
    test_package = relationship("TestPackage")


class TieInRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "tie_in_records"
    _repr_fields = ("id", "tie_in_no", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    tie_in_no = Column(String(100), unique=True, nullable=False, index=True)
    line_number = Column(String(100), index=True)
    existing_line = Column(String(100))
    location = Column(String(200))
    tie_in_type = Column(String(50), default="Hot Tap")
    shutdown_required = Column(Boolean, default=False)
    execution_date = Column(Date)
    status = Column(String(30), default="Planned", index=True)
    responsible_person = Column(String(100))
    remarks = Column(Text)

    project = relationship("Project")


class ExpansionJointRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "expansion_joint_records"
    _repr_fields = ("id", "joint_tag", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    joint_tag = Column(String(100), nullable=False, index=True)
    line_number = Column(String(100), index=True)
    joint_type = Column(String(80))
    manufacturer = Column(String(150))
    shipping_bars_removed = Column(Boolean, default=False)
    shipping_bars_removed_date = Column(Date)
    installed_date = Column(Date)
    inspector = Column(String(100))
    status = Column(String(30), default="Installed", index=True)
    remarks = Column(Text)

    project = relationship("Project")


class PicklingPassivationRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "pickling_passivation_records"
    _repr_fields = ("id", "line_number", "result")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    line_number = Column(String(100), index=True)
    spool_number = Column(String(100), index=True)
    chemical_used = Column(String(150))
    ferroxyl_test_done = Column(Boolean, default=True)
    ferroxyl_test_result = Column(String(30), default="Pass")
    performed_by = Column(String(100))
    performed_date = Column(Date)
    inspector = Column(String(100))
    result = Column(String(30), default="Pending", index=True)
    remarks = Column(Text)

    project = relationship("Project")


class IsoRegistry(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "iso_registry"
    _repr_fields = ("id", "iso_number", "revision", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True, index=True)
    line_number = Column(String(100), index=True)
    iso_number = Column(String(100), nullable=False, index=True)
    sheet_number = Column(String(20), default="1")
    total_sheets = Column(Integer, default=1)
    revision = Column(String(20), default="0")
    title = Column(String(300))
    drawing_file_path = Column(String(500))
    design_status = Column(String(50), default="IFC", index=True)
    spool_count = Column(Integer, default=0)
    weld_count = Column(Integer, default=0)
    total_length_m = Column(Float, default=0.0)
    received_date = Column(Date, default=date.today)
    asbuilt_complete = Column(Boolean, default=False, index=True)
    status = Column(String(30), default="Active", index=True)
    remarks = Column(Text)

    project = relationship("Project")
    area = relationship("Area")

    __table_args__ = (
        UniqueConstraint("project_id", "iso_number", "sheet_number", name="uq_iso_sheet_per_project"),
    )


class AsBuiltRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "asbuilt_records"
    _repr_fields = ("id", "drawing_no", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    drawing_no = Column(String(100), index=True)
    iso_number = Column(String(100), index=True)
    line_number = Column(String(100), index=True)
    revision = Column(String(20), default="0")
    redline_path = Column(String(500))
    asbuilt_path = Column(String(500))
    status = Column(String(30), default="Draft", index=True)
    prepared_by = Column(String(100))
    prepared_date = Column(Date)
    approved_by = Column(String(100))
    approved_date = Column(Date)
    remarks = Column(Text)

    project = relationship("Project")
    markups = relationship("AsBuiltMarkUp", back_populates="asbuilt_record", cascade="all, delete-orphan")


class AsBuiltMarkUp(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "asbuilt_markups"
    _repr_fields = ("id", "drawing_no", "markup_type", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    asbuilt_record_id = Column(Integer, ForeignKey("asbuilt_records.id", ondelete="CASCADE"), nullable=True, index=True)
    drawing_no = Column(String(100), index=True)
    line_number = Column(String(100), index=True)
    iso_number = Column(String(100), index=True)
    markup_type = Column(String(50), default="Redline")
    description = Column(Text)
    sheet_number = Column(String(30))
    coordinate_reference = Column(String(100))
    marked_by = Column(String(100))
    marked_date = Column(Date, default=date.today)
    status = Column(String(30), default="Draft", index=True)
    incorporated_by = Column(String(100))
    incorporated_date = Column(Date)
    attachment_path = Column(String(500))
    remarks = Column(Text)

    project = relationship("Project")
    asbuilt_record = relationship("AsBuiltRecord", back_populates="markups")


class WeldMapEntry(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "weld_map_entries"
    _repr_fields = ("id", "iso_number", "joint_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    weld_id_fk = Column(Integer, ForeignKey("welds.id", ondelete="CASCADE"), nullable=True, index=True)
    iso_number = Column(String(100), nullable=False, index=True)
    sheet_number = Column(String(20), default="1")
    line_number = Column(String(100), index=True)
    spool_number = Column(String(100), index=True)
    joint_number = Column(String(100), nullable=False, index=True)
    weld_type = Column(String(30), default="Shop")
    drawing_coord_x = Column(Float)
    drawing_coord_y = Column(Float)
    welder_stencil = Column(String(100))
    wps_number = Column(String(100))
    ndt_clearance = Column(String(30), default="Pending", index=True)
    asbuilt_verified = Column(Boolean, default=False, index=True)
    status = Column(String(30), default="Draft", index=True)
    remarks = Column(Text)

    project = relationship("Project")
    weld = relationship("Weld")


class WalkdownChecklist(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "walkdown_checklists"
    _repr_fields = ("id", "walkdown_no", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    area_id = Column(Integer, ForeignKey("areas.id", ondelete="SET NULL"), nullable=True, index=True)
    line_number = Column(String(100), index=True)
    iso_number = Column(String(100), index=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    walkdown_no = Column(String(100), unique=True, nullable=False, index=True)
    walkdown_type = Column(String(50), default="Pre-Hydro")
    inspection_date = Column(Date, default=date.today)
    lead_inspector = Column(String(100))
    contractor_rep = Column(String(100))
    client_rep = Column(String(100))
    tpi_rep = Column(String(100))
    is_p_id_verified = Column(Boolean, default=True)
    is_slope_verified = Column(Boolean, default=True)
    is_supports_verified = Column(Boolean, default=True)
    is_valves_verified = Column(Boolean, default=True)
    is_instruments_verified = Column(Boolean, default=True)
    is_accessibility_verified = Column(Boolean, default=True)
    punch_a_found = Column(Integer, default=0)
    punch_b_found = Column(Integer, default=0)
    punch_c_found = Column(Integer, default=0)
    status = Column(String(30), default="In Progress", index=True)
    remarks = Column(Text)

    project = relationship("Project")
    area = relationship("Area")
    test_package = relationship("TestPackage")


class PrecommRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "precomm_records"
    _repr_fields = ("id", "system_name", "activity_type", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_package_id = Column(Integer, ForeignKey("test_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    system_name = Column(String(150), index=True)
    subsystem = Column(String(150), index=True)
    activity_type = Column(String(80), nullable=False, index=True)
    target_date = Column(Date)
    completed_date = Column(Date)
    status = Column(String(30), default="Pending", index=True)
    lead_engineer = Column(String(100))
    witness_client = Column(String(100))
    remarks = Column(Text)

    project = relationship("Project")
    test_package = relationship("TestPackage")


class CalibrationRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "calibration_records"
    _repr_fields = ("id", "equipment_tag", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    equipment_tag = Column(String(100), nullable=False, index=True)
    equipment_type = Column(String(100), nullable=False)
    serial_number = Column(String(100))
    manufacturer = Column(String(150))
    model = Column(String(100))
    calibrated_date = Column(Date)
    expiry_date = Column(Date, index=True)
    certificate_number = Column(String(120))
    certificate_path = Column(String(500))
    calibrated_by = Column(String(150))
    status = Column(String(30), default="Valid", index=True)
    remarks = Column(Text)

    project = relationship("Project")


class MCCRecord(Base, CreatedOnlyMixin, ReprMixin):
    __tablename__ = "mcc_records"
    _repr_fields = ("id", "mcc_no", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    mcc_no = Column(String(100), unique=True, nullable=False, index=True)
    system_name = Column(String(200))
    subsystem = Column(String(200))
    scope_description = Column(Text)
    hydro_test_complete = Column(Boolean, default=False)
    ndt_complete = Column(Boolean, default=False)
    pwht_complete = Column(Boolean, default=False)
    reinstatement_complete = Column(Boolean, default=False)
    painting_complete = Column(Boolean, default=False)
    insulation_complete = Column(Boolean, default=False)
    punch_a_open = Column(Integer, default=0)
    punch_b_open = Column(Integer, default=0)
    issued_date = Column(Date)
    issued_by = Column(String(100))
    accepted_by = Column(String(100))
    status = Column(String(30), default="Draft", index=True)
    remarks = Column(Text)


# ══════════════════════════════════════════════
#  15. Compatibility Aliases
# ══════════════════════════════════════════════

# Implementation note.
Line = LineListItem
LineList = LineListItem
LineItem = LineListItem
Material = MaterialItem
MTO = MaterialTakeOff
MTR = MTRRecord
MaterialCertificate = MTRRecord
MaterialTestReport = MTRRecord
MRIRecord = MaterialReceiptRecord
MaterialReceipt = MaterialReceiptRecord
MaterialIssue = MaterialIssueRecord
MaterialPreservation = MaterialPreservationRecord

# Implementation note.
WeldJoint = Weld
JointRecord = Weld
WelderQualification = Welder
WPS = WPS_PQR
PQR = WPS_PQR
Support = PipeSupport

# Implementation note.
Punch = PunchItem
NCR = NCRRecord
Valve = ValveRecord
ITP = ITPItem
InspectionTestPlan = ITPItem
ITPRecord = ITPItem
EquipmentCalibration = CalibrationRecord

# Implementation note.
PipeWrappingRecord = WrappingRecord
JointCoatingRecord = WrappingRecord
PassiveFireproofingRecord = FireproofingRecord
SurfaceBlastingRecord = BlastingRecord
SandblastingRecord = BlastingRecord

# Implementation note.
PMITestRecord = PMIRecord
PMITest = PMIRecord
PMI = PMIRecord
HardnessRecord = HardnessTestRecord
FerriteRecord = FerriteTestRecord
LeakTest = LeakTestRecord
HydroTestRecord = LeakTestRecord
PneumaticTestRecord = LeakTestRecord

# Implementation note.
MCCCertificate = MCCRecord
MechanicalCompletionCertificate = MCCRecord
MCC = MCCRecord
BoxUp = BoxUpRecord
Drying = DryingRecord
AirBlowingRecord = BlowingRecord
SteamBlowingRecord = BlowingRecord
NitrogenPurgingRecord = PurgingRecord
InertingRecord = PurgingRecord
SpringHanger = SpringHangerRecord
SpringSupportRecord = SpringHangerRecord
TieIn = TieInRecord
TieInPoint = TieInRecord
ExpansionJoint = ExpansionJointRecord
PicklingRecord = PicklingPassivationRecord
PrecommissioningRecord = PrecommRecord
PrecommActivity = PrecommRecord

# Implementation note.
IsometricRegistry = IsoRegistry
IsoDrawingRecord = IsoRegistry
IsometricRecord = IsoRegistry
Iso = IsoRegistry
AsBuiltMarkup = AsBuiltMarkUp
RedlineMarkUp = AsBuiltMarkUp
RedlineMarkup = AsBuiltMarkUp
AsbuiltMarkUp = AsBuiltMarkUp
AsbuiltMarkup = AsBuiltMarkUp
AsbuiltRecord = AsBuiltRecord
AsBuiltDrawing = AsBuiltRecord
RedlineRecord = AsBuiltRecord
DrawingRecord = AsBuiltRecord
WeldMap = WeldMapEntry
WeldMapping = WeldMapEntry
WeldMapRecord = WeldMapEntry
WeldMappingRecord = WeldMapEntry
Walkdown = WalkdownChecklist
WalkdownRecord = WalkdownChecklist
WalkdownInspection = WalkdownChecklist
WalkdownItem = WalkdownChecklist
WalkdownCheck = WalkdownChecklist

# Implementation note.
TestPackageBlind = BlindListRecord
BlindItem = BlindListRecord
SpoolErection = SpoolErectionRecord
DimensionalInspectionRecord = DimensionalCheckRecord

# Implementation note.
DocEvidence = DocumentEvidence
MaterialEvidence = DocumentEvidence
EvidenceRecord = DocumentEvidence
# Enterprise model compatibility exports.
# Kept here so existing integrations/tests can continue to import the
# public model registry from db.models while the implementation remains
# modular in db.models_enterprise.
try:
    from db.models_enterprise import (  # noqa: E402,F401
        Organization, IntegrationEndpoint, IntegrationJob, ExternalMapping,
        WeldingTelemetry, FieldSyncBatch, FieldSyncReceipt,
        EnterpriseDocumentEvidence, PredictionObservation, PredictionRun,
        PredictionImpact,
    )
except ImportError:
    # During the first phase of the circular import, db.manager will load
    # db.models_enterprise immediately afterwards and complete registration.
    pass

# ══════════════════════════════════════════════
#  99. Site Execution Control Models
# ══════════════════════════════════════════════

class InstrumentRecord(Base, TimestampMixin, ReprMixin):
    __tablename__ = "instrument_records"
    _repr_fields = ("id", "tag_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    tag_number = Column(String(100), nullable=False, index=True)
    description = Column(String(250))
    instrument_type = Column(String(100))
    service = Column(String(150))
    area = Column(String(100), index=True)
    loop_number = Column(String(100), index=True)
    vendor = Column(String(150))
    serial_number = Column(String(100))
    calibration_due = Column(Date)
    installation_status = Column(String(50), default="Not Installed", index=True)
    calibration_status = Column(String(50), default="Pending")
    loop_check_status = Column(String(50), default="Not Started")
    functional_test_status = Column(String(50), default="Not Started")
    punch_status = Column(String(50), default="Open")
    status = Column(String(50), default="In Progress", index=True)
    remarks = Column(Text)


class PermitRecord(Base, TimestampMixin, ReprMixin):
    __tablename__ = "permit_records"
    _repr_fields = ("id", "permit_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    permit_number = Column(String(100), unique=True, nullable=False, index=True)
    permit_type = Column(String(80), nullable=False)
    work_front = Column(String(150))
    area = Column(String(100))
    requested_by = Column(String(100))
    issuer = Column(String(100))
    start_at = Column(DateTime)
    expires_at = Column(DateTime)
    risk_level = Column(String(30), default="Medium")
    status = Column(String(40), default="Requested", index=True)
    isolation_required = Column(Boolean, default=False)
    gas_test_required = Column(Boolean, default=False)
    remarks = Column(Text)


class EquipmentRecord(Base, TimestampMixin, ReprMixin):
    __tablename__ = "equipment_records"
    _repr_fields = ("id", "asset_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    asset_number = Column(String(100), unique=True, nullable=False, index=True)
    equipment_type = Column(String(100), nullable=False)
    description = Column(String(250))
    owner = Column(String(150))
    operator = Column(String(100))
    area = Column(String(100))
    availability_pct = Column(Float, default=100.0)
    utilization_pct = Column(Float, default=0.0)
    inspection_due = Column(Date)
    status = Column(String(50), default="Available", index=True)
    hour_meter = Column(Float, default=0.0)
    remarks = Column(Text)


class SiteIssueRecord(Base, TimestampMixin, ReprMixin):
    __tablename__ = "site_issue_records"
    _repr_fields = ("id", "issue_number", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    issue_number = Column(String(100), unique=True, nullable=False, index=True)
    category = Column(String(80), nullable=False)
    discipline = Column(String(80))
    area = Column(String(100))
    title = Column(String(250), nullable=False)
    description = Column(Text)
    priority = Column(String(30), default="Medium", index=True)
    owner = Column(String(100))
    due_date = Column(Date)
    status = Column(String(40), default="Open", index=True)
    root_cause = Column(Text)
    corrective_action = Column(Text)
    closure_evidence = Column(String(500))


class CommissioningRecord(Base, TimestampMixin, ReprMixin):
    __tablename__ = "commissioning_records"
    _repr_fields = ("id", "system_code", "status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    system_code = Column(String(100), nullable=False, index=True)
    subsystem = Column(String(150))
    area = Column(String(100))
    commissioning_phase = Column(String(80), default="Mechanical Completion")
    checklist_total = Column(Integer, default=0)
    checklist_complete = Column(Integer, default=0)
    punch_open = Column(Integer, default=0)
    test_status = Column(String(50), default="Not Started")
    turnover_status = Column(String(50), default="Not Ready")
    status = Column(String(50), default="In Progress", index=True)
    responsible = Column(String(100))
    remarks = Column(Text)
