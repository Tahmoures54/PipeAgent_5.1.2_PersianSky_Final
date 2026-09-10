# -*- coding: utf-8 -*-
"""
db/queries/document_queries.py – PipeAgent v5.1
================================================
Enterprise Document Management System (DMS) Query Layer.

Handles lifecycle, revision control, auditing, and transmittal tracking
for all project documents including Isometrics, WPS/PQR, NDT Reports,
and Handover dossiers.

Key Features:
  • Auto-propagating document revisions (updates parent on new revision).
  • Advanced multi-criteria search (discipline, status, tags, etc.).
  • Full support for Transmittals and audit trials.
  • Integrated with Enterprise DocumentEvidence verification.
  • Performance optimized with eager loading and count queries.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from db.models import (
    Document,
    DocumentRevision,
    Project,
    Transmittal,
    TransmittalItem,
)

# Implementation note.
try:
    from db.models_enterprise import DocumentEvidence
except ImportError:
    DocumentEvidence = None

try:
    from core.exceptions import DatabaseError, ValidationError
except ImportError:
    class DatabaseError(Exception): pass
    class ValidationError(Exception): pass

logger = logging.getLogger(__name__)

__all__ = [
    # Document CRUD
    "get_documents",
    "get_document_by_id",
    "get_document_by_number",
    "create_document",
    "update_document",
    "delete_document",
    # Document Revisions
    "get_document_revisions",
    "get_revision_by_id",
    "create_document_revision",
    "get_latest_revision",
    "delete_document_revision",
    # Transmittals
    "get_transmittals",
    "get_transmittal_by_id",
    "get_transmittal_by_number",
    "create_transmittal",
    "delete_transmittal",
    # Evidence (Enterprise)
    "get_document_evidence",
    "create_document_evidence",
    # Stats / Analytics
    "get_dms_dashboard_stats",
]


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def _validate_project_id(project_id: int) -> None:
    if not isinstance(project_id, int) or project_id <= 0:
        raise ValidationError(f"Invalid project_id: {project_id!r}. Must be a positive integer.")


def _apply_pagination(query, *, offset: int = 0, limit: int = 100):
    if offset > 0:
        query = query.offset(offset)
    if limit is not None and limit > 0:
        query = query.limit(limit)
    return query


def _safe_update(obj: Any, data: Dict[str, Any], *, exclude: set[str] | None = None) -> int:
    exclude = exclude or {"id", "created_at", "project_id"}
    changed = 0
    for key, value in data.items():
        if key in exclude:
            continue
        if hasattr(obj, key):
            old = getattr(obj, key)
            if old != value:
                setattr(obj, key, value)
                changed += 1
    return changed


# ──────────────────────────────────────────────
#  1. Document CRUD
# ──────────────────────────────────────────────

def get_documents(
    session: Session,
    project_id: int,
    *,
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    discipline: Optional[str] = None,
    line_number: Optional[str] = None,
    spool_id: Optional[int] = None,
    weld_id: Optional[int] = None,
    test_package_id: Optional[int] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[Document]:
    """
    دریافت لیست اسناد با فیلترهای پیشرفته صنعتی و قابلیت جستجوی متنی.
    """
    _validate_project_id(project_id)
    q = session.query(Document).filter(Document.project_id == project_id)

    # Implementation note.
    if doc_type:
        q = q.filter(Document.doc_type == doc_type)
    if status:
        q = q.filter(Document.status == status)
    if discipline:
        q = q.filter(Document.discipline == discipline)
    if line_number:
        q = q.filter(Document.line_number == line_number)

    # Implementation note.
    if spool_id is not None:
        q = q.filter(Document.spool_id == spool_id)
    if weld_id is not None:
        q = q.filter(Document.weld_id == weld_id)
    if test_package_id is not None:
        q = q.filter(Document.test_package_id == test_package_id)

    # Implementation note.
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                Document.doc_number.ilike(pattern),
                Document.title.ilike(pattern),
                Document.originator.ilike(pattern),
                Document.line_number.ilike(pattern),
            )
        )

    # Implementation note.
    q = q.options(joinedload(Document.revisions))
    q = q.order_by(Document.doc_number)

    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_document_by_id(session: Session, doc_id: int) -> Optional[Document]:
    """دریافت اطلاعات سند بر اساس شناسه اصلی."""
    return session.query(Document).options(joinedload(Document.revisions)).filter(Document.id == doc_id).first()


def get_document_by_number(session: Session, project_id: int, doc_number: str) -> Optional[Document]:
    """دریافت اطلاعات سند بر اساس شماره یکتای سند در پروژه."""
    _validate_project_id(project_id)
    return (
        session.query(Document)
        .options(joinedload(Document.revisions))
        .filter(Document.project_id == project_id, Document.doc_number == doc_number)
        .first()
    )


def create_document(session: Session, **kwargs: Any) -> Document:
    """ایجاد یک ردیف مدرک جدید."""
    if "project_id" not in kwargs:
        raise ValidationError("project_id is required to create a Document.")
    _validate_project_id(kwargs["project_id"])

    doc = Document(**kwargs)
    session.add(doc)
    session.flush()
    logger.info("Created Document ID=%d Number=%s", doc.id, doc.doc_number)
    return doc


def update_document(session: Session, doc_id: int, **kwargs: Any) -> Optional[Document]:
    """به‌روزرسانی فیلدهای سند اصلی."""
    doc = session.get(Document, doc_id)
    if doc is None:
        logger.warning("Document ID=%d not found for update.", doc_id)
        return None

    changed = _safe_update(doc, kwargs)
    if changed:
        session.flush()
        logger.info("Updated Document ID=%d (%d fields modified).", doc_id, changed)
    return doc


def delete_document(session: Session, doc_id: int) -> bool:
    """حذف کامل یک سند به همراه تمامی آرشیو Revisions آن (به دلیل cascade cascade)."""
    doc = session.get(Document, doc_id)
    if doc is None:
        return False
    session.delete(doc)
    session.flush()
    logger.info("Deleted Document ID=%d and all its revisions.", doc_id)
    return True


# ──────────────────────────────────────────────
#  2. Document Revisions
# ──────────────────────────────────────────────

def get_document_revisions(session: Session, doc_id: int) -> List[DocumentRevision]:
    """دریافت تاریخچه‌ی کامل نسخه‌های ثبت شده برای یک سند."""
    return (
        session.query(DocumentRevision)
        .filter(DocumentRevision.document_id == doc_id)
        .order_by(DocumentRevision.created_at.desc())
        .all()
    )


def get_revision_by_id(session: Session, revision_id: int) -> Optional[DocumentRevision]:
    """دریافت یک نسخه خاص از مدرک."""
    return session.get(DocumentRevision, revision_id)


def create_document_revision(
    session: Session,
    doc_id: int,
    revision: str,
    file_path: str,
    *,
    comments: Optional[str] = None,
    reviewed_by: Optional[str] = None,
    approved_by: Optional[str] = None,
    auto_update_parent: bool = True,
) -> DocumentRevision:
    """
    ثبت یک نسخه‌ی جدید برای مدرک.
    
    به صورت خودکار فیلدهای `revision` و `file_path` سند اصلی را 
    با اطلاعات جدیدترین نسخه همگام‌سازی می‌کند.
    """
    doc = session.get(Document, doc_id)
    if doc is None:
        raise ValidationError(f"Cannot add revision. Document ID {doc_id} does not exist.")

    rev_record = DocumentRevision(
        document_id=doc_id,
        revision=revision,
        file_path=file_path,
        comments=comments,
        reviewed_by=reviewed_by,
        approved_by=approved_by,
        created_at=datetime.now(timezone.utc),
    )
    session.add(rev_record)

    # Implementation note.
    if auto_update_parent:
        doc.revision = revision
        doc.file_path = file_path
        doc.status = "Approved" if approved_by else "Under Review"

    session.flush()
    logger.info("Created Revision %s for Document ID=%d (Updated parent: %s)", revision, doc_id, auto_update_parent)
    return rev_record


def get_latest_revision(session: Session, doc_id: int) -> Optional[DocumentRevision]:
    """دریافت اطلاعات آخرین نسخه ثبت‌شده برای مدرک."""
    return (
        session.query(DocumentRevision)
        .filter(DocumentRevision.document_id == doc_id)
        .order_by(DocumentRevision.created_at.desc())
        .first()
    )


def delete_document_revision(session: Session, revision_id: int) -> bool:
    """حذف یک ردیف نسخه از تاریخچه مدارک."""
    rev = session.get(DocumentRevision, revision_id)
    if rev is None:
        return False
    session.delete(rev)
    session.flush()
    return True


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────

def get_transmittals(
    session: Session,
    project_id: int,
    *,
    to_company: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
) -> List[Transmittal]:
    """دریافت لیست ترنسمیتال‌ها."""
    _validate_project_id(project_id)
    q = session.query(Transmittal).filter(Transmittal.project_id == project_id)

    if to_company:
        q = q.filter(Transmittal.to_company.ilike(f"%{to_company}%"))

    q = q.options(joinedload(Transmittal.items))
    q = q.order_by(Transmittal.created_at.desc())

    return _apply_pagination(q, offset=offset, limit=limit).all()


def get_transmittal_by_id(session: Session, transmittal_id: int) -> Optional[Transmittal]:
    """دریافت ترنسمیتال با شناسه."""
    return (
        session.query(Transmittal)
        .options(joinedload(Transmittal.items))
        .filter(Transmittal.id == transmittal_id)
        .first()
    )


def get_transmittal_by_number(session: Session, project_id: int, transmittal_no: str) -> Optional[Transmittal]:
    """دریافت ترنسمیتال بر اساس شماره ثبت منحصر‌به‌فرد."""
    _validate_project_id(project_id)
    return (
        session.query(Transmittal)
        .options(joinedload(Transmittal.items))
        .filter(Transmittal.project_id == project_id, Transmittal.transmittal_no == transmittal_no)
        .first()
    )


def create_transmittal(
    session: Session,
    project_id: int,
    transmittal_no: str,
    to_company: str,
    *,
    purpose: Optional[str] = None,
    document_ids_with_revisions: Optional[List[Tuple[int, str]]] = None,
) -> Transmittal:
    """
    ایجاد یک ترنسمیتال جدید به همراه اسناد پیوست شده به آن.

    Args:
        document_ids_with_revisions: لیستی از توپل‌ها شامل [(doc_id, revision_code), ...]
    """
    _validate_project_id(project_id)

    # Implementation note.
    existing = (
        session.query(Transmittal)
        .filter(Transmittal.project_id == project_id, Transmittal.transmittal_no == transmittal_no)
        .first()
    )
    if existing:
        raise ValidationError(f"Transmittal No '{transmittal_no}' already exists in this project.")

    trans = Transmittal(
        project_id=project_id,
        transmittal_no=transmittal_no,
        to_company=to_company,
        purpose=purpose,
        created_at=datetime.now(timezone.utc),
    )
    session.add(trans)
    session.flush()

    # Implementation note.
    if document_ids_with_revisions:
        for doc_id, rev in document_ids_with_revisions:
            item = TransmittalItem(
                transmittal_id=trans.id,
                document_id_fk=doc_id,
                revision=rev,
            )
            session.add(item)

    session.flush()
    logger.info("Issued Transmittal ID=%d No=%s to %s", trans.id, trans.transmittal_no, to_company)
    return trans


def delete_transmittal(session: Session, transmittal_id: int) -> bool:
    """حذف ترنسمیتال (پیوست‌ها خودکار پاک می‌شوند)."""
    trans = session.get(Transmittal, transmittal_id)
    if trans is None:
        return False
    session.delete(trans)
    session.flush()
    return True


# ──────────────────────────────────────────────
#  4. Document Evidence (Enterprise)
# ──────────────────────────────────────────────

def get_document_evidence(
    session: Session,
    project_id: int,
    entity_key: str,
    *,
    entity_type: str = "Document",
) -> List[Any]:
    """
    دریافت مدارک و گواهی‌های اصالت اثبات‌شده (SHA256) برای ممیزی‌های بلاکچین/سازمانی.
    """
    if DocumentEvidence is None:
        logger.warning("Enterprise models not available; cannot query DocumentEvidence.")
        return []

    _validate_project_id(project_id)
    return (
        session.query(DocumentEvidence)
        .filter(
            DocumentEvidence.project_id == project_id,
            DocumentEvidence.entity_key == entity_key,
            DocumentEvidence.entity_type == entity_type,
        )
        .all()
    )


def create_document_evidence(session: Session, **kwargs: Any) -> Any:
    """ثبت هش دیجیتال و ممیزی مدرک برای امنیت بالاتر."""
    if DocumentEvidence is None:
        raise DatabaseError("Enterprise module 'DocumentEvidence' model is not loaded.")

    if "project_id" not in kwargs or "sha256" not in kwargs:
        raise ValidationError("project_id and sha256 are required to save document evidence.")

    evidence = DocumentEvidence(**kwargs)
    session.add(evidence)
    session.flush()
    return evidence


# ──────────────────────────────────────────────
#  5. DMS Statistics & Analytics
# ──────────────────────────────────────────────

def get_dms_dashboard_stats(session: Session, project_id: int) -> Dict[str, Any]:
    """
    ارائه آمار دقیق کنترل مدارک برای بخش مانیتورینگ پروژه.
    
    خروجی شامل:
      - تعداد مدارک کل پروژه
      - تفکیک وضعیت تایید (Draft, Under Review, Approved, Rejected)
      - تعداد ترنسمیتال‌های صادر شده
      - تفکیک مدارک بر اساس دیسیپلین (Piping, Structural, Instrument, Mechanical, ...)
    """
    _validate_project_id(project_id)

    total_docs = session.query(func.count(Document.id)).filter(Document.project_id == project_id).scalar() or 0

    # Implementation note.
    status_counts = (
        session.query(Document.status, func.count(Document.id))
        .filter(Document.project_id == project_id)
        .group_by(Document.status)
        .all()
    )
    status_map = {status or "Unknown": count for status, count in status_counts}

    # Implementation note.
    discipline_counts = (
        session.query(Document.discipline, func.count(Document.id))
        .filter(Document.project_id == project_id)
        .group_by(Document.discipline)
        .all()
    )
    discipline_map = {disc or "Other": count for disc, count in discipline_counts}

    # Implementation note.
    total_transmittals = session.query(func.count(Transmittal.id)).filter(Transmittal.project_id == project_id).scalar() or 0

    return {
        "total_documents": total_docs,
        "by_status": status_map,
        "by_discipline": discipline_map,
        "total_transmittals_issued": total_transmittals,
        "approved_ratio": round((status_map.get("Approved", 0) / total_docs * 100), 1) if total_docs else 0.0,
    }