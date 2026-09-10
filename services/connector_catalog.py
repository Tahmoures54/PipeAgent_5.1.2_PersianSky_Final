# -*- coding: utf-8 -*-
"""
integrations/connector_catalog.py – PipeAgent
کاتالوگ جامع قراردادهای یکپارچه‌سازی (Integration Contracts) با سیستم‌های سازمانی
شامل: تعریف Schema موجودیت‌ها، نسخه‌بندی قراردادها، جهت‌مندی و حالت همگام‌سازی،
سیاست حل تعارض (Conflict Resolution) و کلیدهای همبستگی (Correlation Keys).

اصل معماری: هر سیستم خارجی مرجع رسمی (System of Record) دامنه خودش است.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Integration Semantics
# ──────────────────────────────────────────────

class SystemDomain(str, Enum):
    """دامنه‌های سیستم‌های خارجی متصل به PipeAgent"""
    ERP = "ERP"                        # Implementation note.
    SCHEDULING = "SCHEDULING"          # Implementation note.
    DMS = "DMS"                        # Implementation note.
    BIM = "BIM"                        # Implementation note.
    HSE = "HSE"                        # Implementation note.
    LIMS = "LIMS"                      # Implementation note.


class SyncDirection(str, Enum):
    """جهت جریان داده نسبت به PipeAgent"""
    INBOUND = "INBOUND"                # Implementation note.
    OUTBOUND = "OUTBOUND"              # Implementation note.
    BIDIRECTIONAL = "BIDIRECTIONAL"    # Implementation note.


class SyncMode(str, Enum):
    """حالت همگام‌سازی داده"""
    REALTIME_PUSH = "REALTIME_PUSH"    # Implementation note.
    BATCH_PULL = "BATCH_PULL"          # Implementation note.
    ON_DEMAND = "ON_DEMAND"            # Implementation note.
    FILE_DROP = "FILE_DROP"            # Implementation note.


class ConflictPolicy(str, Enum):
    """سیاست حل تعارض در همگام‌سازی دوطرفه"""
    EXTERNAL_WINS = "EXTERNAL_WINS"    # Implementation note.
    PIPEAGENT_WINS = "PIPEAGENT_WINS"  # Implementation note.
    LATEST_TIMESTAMP = "LATEST_WINS"   # Implementation note.
    MANUAL_REVIEW = "MANUAL_REVIEW"    # Implementation note.


class FieldType(str, Enum):
    """انواع داده استاندارد فیلدهای قرارداد"""
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    ENUM = "enum"
    REFERENCE = "reference"            # Implementation note.


# ──────────────────────────────────────────────
#  Contract Data Structures
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class FieldSpec:
    """مشخصات یک فیلد در Schema موجودیت"""
    name: str
    field_type: FieldType
    required: bool = False
    description: str = ""
    external_field_hint: Optional[str] = None   # Implementation note.
    enum_values: Optional[Tuple[str, ...]] = None


@dataclass(frozen=True)
class EntityContract:
    """قرارداد کامل یک موجودیت قابل تبادل"""
    entity_name: str
    direction: SyncDirection
    sync_mode: SyncMode
    correlation_key: str                          # Implementation note.
    fields: Tuple[FieldSpec, ...]
    conflict_policy: ConflictPolicy = ConflictPolicy.EXTERNAL_WINS
    description: str = ""
    version: str = "1.0"

    def validate_payload(self, payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """اعتبارسنجی ساختاری Payload دریافتی در برابر Schema قرارداد"""
        errors: List[str] = []

        known_fields = {f.name for f in self.fields}
        required_fields = {f.name for f in self.fields if f.required}

        # Implementation note.
        missing = required_fields - set(payload.keys())
        if missing:
            errors.append(f"Missing required fields: {sorted(missing)}")

        # Implementation note.
        if self.correlation_key not in payload or payload.get(self.correlation_key) in (None, ""):
            errors.append(f"Correlation key '{self.correlation_key}' is missing or empty.")

        # Implementation note.
        unknown = set(payload.keys()) - known_fields
        if unknown:
            logger.debug(f"[{self.entity_name}] Unknown fields ignored: {sorted(unknown)}")

        # Implementation note.
        for f in self.fields:
            if f.field_type == FieldType.ENUM and f.name in payload and f.enum_values:
                if payload[f.name] not in f.enum_values:
                    errors.append(
                        f"Field '{f.name}' value '{payload[f.name]}' not in allowed values {f.enum_values}."
                    )

        return len(errors) == 0, errors


@dataclass(frozen=True)
class DomainContract:
    """قرارداد کامل یک دامنه سیستمی (مثلاً کل ERP)"""
    domain: SystemDomain
    authoritative_note: str
    entities: Tuple[EntityContract, ...]
    catalog_version: str = "2.0"

    def get_entity(self, entity_name: str) -> Optional[EntityContract]:
        for e in self.entities:
            if e.entity_name == entity_name:
                return e
        return None


# ──────────────────────────────────────────────
#  Canonical Contract Definitions
# ──────────────────────────────────────────────

def _f(name: str, ftype: FieldType, required: bool = False, hint: str = None, desc: str = "", enums: tuple = None) -> FieldSpec:
    """هلپر ساخت سریع FieldSpec"""
    return FieldSpec(
        name=name, field_type=ftype, required=required,
        external_field_hint=hint, description=desc, enum_values=enums,
    )


ERP_CONTRACT = DomainContract(
    domain=SystemDomain.ERP,
    authoritative_note="ERP is the System of Record for materials, POs, vendors, and cost codes.",
    entities=(
        EntityContract(
            entity_name="material",
            direction=SyncDirection.INBOUND,
            sync_mode=SyncMode.BATCH_PULL,
            correlation_key="material_code",
            conflict_policy=ConflictPolicy.EXTERNAL_WINS,
            description="Master material records incl. heat numbers and certificates.",
            fields=(
                _f("material_code", FieldType.STRING, True, hint="MATNR (SAP)"),
                _f("description", FieldType.STRING, True),
                _f("heat_number", FieldType.STRING, False, hint="CHARG"),
                _f("quantity_available", FieldType.DECIMAL, True),
                _f("unit", FieldType.STRING, True, hint="MEINS"),
                _f("warehouse_code", FieldType.STRING, False),
            ),
        ),
        EntityContract(
            entity_name="purchase_order",
            direction=SyncDirection.INBOUND,
            sync_mode=SyncMode.REALTIME_PUSH,
            correlation_key="po_number",
            fields=(
                _f("po_number", FieldType.STRING, True, hint="EBELN"),
                _f("vendor_code", FieldType.STRING, True, hint="LIFNR"),
                _f("delivery_due_date", FieldType.DATE, False),
                _f("status", FieldType.ENUM, True, enums=("OPEN", "PARTIAL", "COMPLETED", "CANCELLED")),
            ),
        ),
        EntityContract(
            entity_name="material_issue",
            direction=SyncDirection.OUTBOUND,
            sync_mode=SyncMode.REALTIME_PUSH,
            correlation_key="miv_number",
            description="Material Issue Vouchers generated on site by PipeAgent.",
            fields=(
                _f("miv_number", FieldType.STRING, True),
                _f("material_code", FieldType.STRING, True),
                _f("quantity_issued", FieldType.DECIMAL, True),
                _f("issued_to_workfront", FieldType.STRING, False),
                _f("issue_datetime", FieldType.DATETIME, True),
            ),
        ),
    ),
)

SCHEDULING_CONTRACT = DomainContract(
    domain=SystemDomain.SCHEDULING,
    authoritative_note="Primavera/MSP is the System of Record for baseline and activity network.",
    entities=(
        EntityContract(
            entity_name="activity",
            direction=SyncDirection.INBOUND,
            sync_mode=SyncMode.BATCH_PULL,
            correlation_key="activity_id",
            fields=(
                _f("activity_id", FieldType.STRING, True, hint="P6 Activity ID"),
                _f("wbs_code", FieldType.STRING, True),
                _f("planned_start", FieldType.DATE, True),
                _f("planned_finish", FieldType.DATE, True),
            ),
        ),
        EntityContract(
            entity_name="progress",
            direction=SyncDirection.OUTBOUND,
            sync_mode=SyncMode.BATCH_PULL,
            correlation_key="activity_id",
            description="Physical progress (Dia-Inch based) reported back to the scheduler.",
            fields=(
                _f("activity_id", FieldType.STRING, True),
                _f("physical_pct", FieldType.DECIMAL, True),
                _f("data_date", FieldType.DATE, True),
                _f("earned_dia_inch", FieldType.DECIMAL, False),
            ),
        ),
    ),
)

DMS_CONTRACT = DomainContract(
    domain=SystemDomain.DMS,
    authoritative_note="DMS is the System of Record for engineering documents and transmittals.",
    entities=(
        EntityContract(
            entity_name="document",
            direction=SyncDirection.INBOUND,
            sync_mode=SyncMode.REALTIME_PUSH,
            correlation_key="document_number",
            fields=(
                _f("document_number", FieldType.STRING, True),
                _f("revision", FieldType.STRING, True),
                _f("status", FieldType.ENUM, True, enums=("IFR", "IFC", "AS_BUILT", "SUPERSEDED")),
                _f("file_url", FieldType.STRING, False),
            ),
        ),
        EntityContract(
            entity_name="turnover_dossier",
            direction=SyncDirection.OUTBOUND,
            sync_mode=SyncMode.ON_DEMAND,
            correlation_key="dossier_number",
            description="Final MC dossier package export to client DMS.",
            fields=(
                _f("dossier_number", FieldType.STRING, True),
                _f("subsystem_code", FieldType.STRING, True),
                _f("completeness_pct", FieldType.DECIMAL, True),
                _f("evidence_index", FieldType.STRING, False, desc="JSON index of attached evidence"),
            ),
        ),
    ),
)

BIM_CONTRACT = DomainContract(
    domain=SystemDomain.BIM,
    authoritative_note="BIM/CAD is the System of Record for 3D geometry and spatial breakdown.",
    entities=(
        EntityContract(
            entity_name="ifc_model",
            direction=SyncDirection.INBOUND,
            sync_mode=SyncMode.FILE_DROP,
            correlation_key="model_guid",
            fields=(
                _f("model_guid", FieldType.STRING, True, hint="IFC GlobalId"),
                _f("discipline", FieldType.STRING, True),
                _f("revision", FieldType.STRING, True),
            ),
        ),
        EntityContract(
            entity_name="execution_status",
            direction=SyncDirection.OUTBOUND,
            sync_mode=SyncMode.BATCH_PULL,
            correlation_key="asset_guid",
            description="4D construction status color-coding pushed back to the model.",
            fields=(
                _f("asset_guid", FieldType.STRING, True),
                _f("status", FieldType.ENUM, True,
                   enums=("NOT_STARTED", "FABRICATED", "ERECTED", "TESTED", "COMPLETED")),
                _f("status_date", FieldType.DATE, True),
            ),
        ),
    ),
)


# ──────────────────────────────────────────────
#  ConnectorCatalog Implementation
# ──────────────────────────────────────────────

class ConnectorCatalog:
    """
    کاتالوگ مرکزی قراردادهای یکپارچه‌سازی PipeAgent.
    سیستم‌های خارجی مرجع رسمی دامنه‌های خود باقی می‌مانند (System of Record).
    """

    _DOMAINS: Dict[SystemDomain, DomainContract] = {
        SystemDomain.ERP: ERP_CONTRACT,
        SystemDomain.SCHEDULING: SCHEDULING_CONTRACT,
        SystemDomain.DMS: DMS_CONTRACT,
        SystemDomain.BIM: BIM_CONTRACT,
    }

    # Implementation note.

    @classmethod
    def describe(cls, verbose: bool = False) -> Dict[str, Any]:
        """
        توصیف کامل کاتالوگ (سازگار با نسخه قبلی + حالت تفصیلی)
        """
        if not verbose:
            # Implementation note.
            return {
                domain.value: {
                    "inbound": [e.entity_name for e in c.entities if e.direction in (SyncDirection.INBOUND, SyncDirection.BIDIRECTIONAL)],
                    "outbound": [e.entity_name for e in c.entities if e.direction in (SyncDirection.OUTBOUND, SyncDirection.BIDIRECTIONAL)],
                }
                for domain, c in cls._DOMAINS.items()
            }

        # Implementation note.
        return {
            domain.value: {
                "authoritative_note": c.authoritative_note,
                "catalog_version": c.catalog_version,
                "entities": [
                    {
                        "name": e.entity_name,
                        "version": e.version,
                        "direction": e.direction.value,
                        "sync_mode": e.sync_mode.value,
                        "correlation_key": e.correlation_key,
                        "conflict_policy": e.conflict_policy.value,
                        "fields": [
                            {
                                "name": f.name,
                                "type": f.field_type.value,
                                "required": f.required,
                                "external_hint": f.external_field_hint,
                            }
                            for f in e.fields
                        ],
                    }
                    for e in c.entities
                ],
            }
            for domain, c in cls._DOMAINS.items()
        }

    @classmethod
    def get_contract(cls, domain: SystemDomain | str, entity_name: str) -> Optional[EntityContract]:
        """بازیابی قرارداد یک موجودیت خاص جهت اعتبارسنجی یا نگاشت"""
        dom = SystemDomain(domain) if isinstance(domain, str) else domain
        domain_contract = cls._DOMAINS.get(dom)
        if not domain_contract:
            return None
        return domain_contract.get_entity(entity_name)

    # Implementation note.

    @classmethod
    def validate(
        cls,
        domain: SystemDomain | str,
        entity_name: str,
        payload: Dict[str, Any],
    ) -> Tuple[bool, List[str]]:
        """
        اعتبارسنجی Payload در برابر Schema قرارداد پیش از پردازش:
        خروجی: (معتبر است؟، لیست خطاها)
        """
        contract = cls.get_contract(domain, entity_name)
        if not contract:
            return False, [f"No contract found for entity '{entity_name}' in domain '{domain}'."]
        return contract.validate_payload(payload)

    @classmethod
    def list_domains(cls) -> List[str]:
        """لیست دامنه‌های پشتیبانی‌شده"""
        return [d.value for d in cls._DOMAINS.keys()]