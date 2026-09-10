# -*- coding: utf-8 -*-
"""
services/document_evidence_service.py – PipeAgent
سرویس جامع ثبت، نگهداری و راستی‌آزمایی شواهد و مدارک فنی و کیفی (Immutable Evidence)
شامل: هش‌گذاری جریانی (Low-Memory SHA-256)، مخزن بایگانی اختصاصی (Vault Archiving)،
پایش عدم دستکاری فایل‌ها (Tamper-Proof Audit) و تجمیع مدارک پکیج‌های تکمیل مکانیکی.
"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import and_, desc
from sqlalchemy.exc import SQLAlchemyError

from db.models import DocumentEvidence

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Evidence Categories
# ──────────────────────────────────────────────

class EvidenceType(str, Enum):
    """انواع شواهد و مستندات فنی و کیفی پروژه"""
    MTR = "MTR"                                # Implementation note.
    NDT_REPORT = "NDT_REPORT"                  # Implementation note.
    HYDRO_CHART = "HYDRO_CHART"                # Implementation note.
    CALIBRATION_CERT = "CALIBRATION_CERT"      # Implementation note.
    AS_BUILT_REDLINE = "AS_BUILT_REDLINE"      # Implementation note.
    PMI_SPECTRUM = "PMI_SPECTRUM"              # Implementation note.
    PWHT_CHART = "PWHT_CHART"                  # Implementation note.
    FIELD_PHOTO = "FIELD_PHOTO"                # Implementation note.
    PUNCH_PROOF = "PUNCH_PROOF"                # Implementation note.


class EntityType(str, Enum):
    """موجودیت‌های بالادستی متصل به سند"""
    WELD_JOINT = "WELD_JOINT"
    SPOOL = "SPOOL"
    LINE = "LINE"
    TEST_PACKAGE = "TEST_PACKAGE"
    PUNCH_ITEM = "PUNCH_ITEM"
    VALVE = "VALVE"
    MATERIAL_ITEM = "MATERIAL_ITEM"
    WALKDOWN_ITEM = "WALKDOWN_ITEM"


# ──────────────────────────────────────────────
#  Custom Exceptions
# ──────────────────────────────────────────────

class EvidenceFileNotFoundError(Exception):
    """خطای عدم وجود فایل در مسیر مبدا"""
    pass


class EvidenceTamperedError(Exception):
    """خطای مغایرت اثر انگشت دیجیتال و دستکاری فایل"""
    pass


# ──────────────────────────────────────────────
#  DocumentEvidenceService Implementation
# ──────────────────────────────────────────────

class DocumentEvidenceService:
    """
    سرویس مدیریت شواهد انکارناپذیر، زنجیره تضمین کیفیت و راستی‌آزمایی مدارک مهندسی
    """

    CHUNK_SIZE = 1024 * 1024  # Implementation note.
    DEFAULT_VAULT_DIR = "storage/evidence_vault"

    def __init__(self, db_manager, vault_root: Optional[str] = None):
        self.db = db_manager
        self.vault_root = Path(vault_root or self.DEFAULT_VAULT_DIR)
        self.vault_root.mkdir(parents=True, exist_ok=True)

    # Implementation note.

    def register(
        self,
        project_id: int,
        entity_type: Union[EntityType, str],
        entity_key: str,
        evidence_type: Union[EvidenceType, str],
        file_path: Union[str, Path],
        captured_by: str = "system",
        revision: str = "0",
        metadata: Optional[Dict[str, Any]] = None,
        copy_to_vault: bool = True,
    ) -> int:
        """
        ثبت سند، محاسبه اثر انگشت SHA-256 با متد جریانی، انتقال امن به مخزن و ثبت در دیتابیس
        """
        src_path = Path(file_path)
        if not src_path.exists() or not src_path.is_file():
            raise EvidenceFileNotFoundError(f"Evidence file not found: {file_path}")

        # Implementation note.
        digest, file_size_bytes = self._compute_sha256_and_size(src_path)

        ent_type_val = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        ev_type_val = evidence_type.value if isinstance(evidence_type, EvidenceType) else str(evidence_type)
        mime_type, _ = mimetypes.guess_type(str(src_path))

        with self.db.session_scope() as session:
            # Implementation note.
            existing = (
                session.query(DocumentEvidence)
                .filter(
                    DocumentEvidence.project_id == project_id,
                    DocumentEvidence.sha256 == digest,
                )
                .first()
            )
            if existing:
                logger.info(
                    f"Evidence file '{src_path.name}' already registered (ID #{existing.id}). Returning existing ID."
                )
                return existing.id

            # Implementation note.
            final_stored_path = str(src_path)
            if copy_to_vault:
                vault_dest_path = self._build_vault_path(project_id, ent_type_val, digest, src_path.name)
                vault_dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Implementation note.
                shutil.copy2(src_path, vault_dest_path)
                final_stored_path = str(vault_dest_path)

            # Implementation note.
            full_metadata = metadata or {}
            full_metadata.update({
                "original_source_path": str(src_path),
                "file_size_bytes": file_size_bytes,
                "mime_type": mime_type or "application/octet-stream",
                "registered_at": datetime.utcnow().isoformat(),
            })

            # Implementation note.
            evidence_obj = DocumentEvidence(
                project_id=project_id,
                entity_type=ent_type_val,
                entity_key=str(entity_key).strip().upper(),
                evidence_type=ev_type_val,
                file_name=src_path.name,
                file_path=final_stored_path,
                sha256=digest,
                revision=str(revision).strip(),
                captured_by=captured_by,
                metadata_json=json.dumps(full_metadata, default=str),
            )
            session.add(evidence_obj)
            session.flush()

            logger.info(
                f"Evidence registered: ID #{evidence_obj.id} [{ev_type_val}] for {ent_type_val} '{entity_key}' (SHA: {digest[:10]}...)"
            )
            return evidence_obj.id

    # Implementation note.

    def verify_integrity(self, evidence_id: int) -> Tuple[bool, str]:
        """
        راستی‌آزمایی صحت فیزیکی فایل روی دیسک با اثر انگشت ثبت‌شده در دیتابیس
        خروجی: (صحت فایل True/False, گزارش توضیحی)
        """
        with self.db.session_scope() as session:
            record = session.query(DocumentEvidence).filter(DocumentEvidence.id == evidence_id).first()
            if not record:
                return False, f"Evidence record #{evidence_id} not found in database."

            stored_path = Path(record.file_path)
            if not stored_path.exists():
                return False, f"Physical file is missing from path: {record.file_path}"

            # Implementation note.
            current_digest, _ = self._compute_sha256_and_size(stored_path)

            if current_digest.lower() != record.sha256.lower():
                logger.critical(
                    f"TAMPER ALERT: Evidence #{evidence_id} hash mismatch! "
                    f"Expected: {record.sha256}, Actual: {current_digest}"
                )
                return False, "TAMPERING DETECTED: File content has been modified after registration!"

            return True, "VERIFIED: File is authentic, untampered, and matches stored SHA-256 signature."

    # Implementation note.

    def get_evidence_for_entity(
        self,
        project_id: int,
        entity_type: Union[EntityType, str],
        entity_key: str,
    ) -> List[Dict[str, Any]]:
        """دریافت کلیه شواهد و مدارک متصل به یک موجودیت مشخص (مثلاً تمام مدارک جوش W-01)"""
        ent_type_val = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        
        with self.db.session_scope() as session:
            records = (
                session.query(DocumentEvidence)
                .filter(
                    DocumentEvidence.project_id == project_id,
                    DocumentEvidence.entity_type == ent_type_val,
                    DocumentEvidence.entity_key == str(entity_key).strip().upper(),
                )
                .order_by(desc(DocumentEvidence.id))
                .all()
            )

            results = []
            for r in records:
                meta = json.loads(r.metadata_json or "{}")
                results.append({
                    "id": r.id,
                    "evidence_type": r.evidence_type,
                    "file_name": r.file_name,
                    "file_path": r.file_path,
                    "sha256": r.sha256,
                    "revision": r.revision,
                    "captured_by": r.captured_by,
                    "created_at": r.created_at.isoformat() if hasattr(r, "created_at") and r.created_at else None,
                    "metadata": meta,
                })
            return results

    def build_test_package_dossier_manifest(
        self,
        project_id: int,
        test_package_number: str,
    ) -> Dict[str, Any]:
        """
        استخراج مانیفست کامل مدارک اثباتی پکیج هیدروتست جهت ضمیمه در پرونده تحویل مکانیکی (MC Dossier)
        شامل: گزارش‌های NDT، سرتیفیکیت کالیبراسیون گیج‌ها، نمودار فشار و خطوط قرمز
        """
        with self.db.session_scope() as session:
            records = (
                session.query(DocumentEvidence)
                .filter(
                    DocumentEvidence.project_id == project_id,
                    DocumentEvidence.entity_key == str(test_package_number).strip().upper(),
                )
                .all()
            )

            manifest_items = []
            all_verified = True

            for r in records:
                is_valid, report = self.verify_integrity(r.id)
                if not is_valid:
                    all_verified = False

                manifest_items.append({
                    "evidence_id": r.id,
                    "type": r.evidence_type,
                    "file_name": r.file_name,
                    "sha256": r.sha256,
                    "is_intact": is_valid,
                    "status_report": report,
                })

            return {
                "project_id": project_id,
                "test_package_number": test_package_number,
                "total_evidence_files": len(manifest_items),
                "all_files_intact": all_verified and len(manifest_items) > 0,
                "manifest": manifest_items,
            }

    # Implementation note.

    def register_batch(
        self,
        project_id: int,
        evidence_items: List[Dict[str, Any]],
        captured_by: str = "batch_importer",
    ) -> Dict[str, Any]:
        """ثبت دسته‌ای چندین مدرک (مثلاً ایمپورت ۵۰ سرتیفیکیت MTR به صورت همزمان)"""
        registered_ids = []
        errors = []

        for item in evidence_items:
            try:
                e_id = self.register(
                    project_id=project_id,
                    entity_type=item["entity_type"],
                    entity_key=item["entity_key"],
                    evidence_type=item["evidence_type"],
                    file_path=item["file_path"],
                    captured_by=captured_by,
                    revision=item.get("revision", "0"),
                    metadata=item.get("metadata"),
                    copy_to_vault=item.get("copy_to_vault", True),
                )
                registered_ids.append(e_id)
            except Exception as exc:
                errors.append(f"Failed to register '{item.get('file_path')}': {exc}")

        return {
            "total_submitted": len(evidence_items),
            "successfully_registered": len(registered_ids),
            "registered_ids": registered_ids,
            "errors": errors,
        }

    # Implementation note.

    def _compute_sha256_and_size(self, path: Path) -> Tuple[str, int]:
        """
        محاسبه اثر انگشت دیجیتال SHA-256 و حجم فایل با الگوریتم جریانی (Streaming Chunks)
        مصرف حافظه RAM ثابت و زیر ۲ مگابایت حتی برای فایل‌های چند گیگابایتی.
        """
        hasher = hashlib.sha256()
        total_size = 0

        with open(path, "rb") as f:
            while chunk := f.read(self.CHUNK_SIZE):
                hasher.update(chunk)
                total_size += len(chunk)

        return hasher.hexdigest(), total_size

    def _build_vault_path(self, project_id: int, entity_type: str, digest: str, file_name: str) -> Path:
        """
        ساختاردهی هوشمند مسیر ذخیره‌سازی فایل در مخزن ایزوله:
        vault_root / project_{id} / {entity_type} / {digest[:2]} / {digest[:8]}_{filename}
        """
        sub_dir = f"{digest[:2]}"
        safe_name = f"{digest[:8]}_{file_name.replace(' ', '_')}"
        return self.vault_root / f"project_{project_id}" / entity_type.lower() / sub_dir / safe_name