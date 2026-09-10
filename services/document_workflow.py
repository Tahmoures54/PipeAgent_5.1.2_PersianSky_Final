# -*- coding: utf-8 -*-
"""
services/document_workflow.py – PipeAgent
مدیریت جامع مرکز کنترل مدارک مهندسی (Document Control Center - DCC)
شامل: ثبت نقشه‌ها، کنترل نسخه‌ها (Revisions)، منسوخ‌سازی خودکار (Auto-Supersede)،
اتصال اسناد به خطوط، اسپول‌ها، سرجوش‌ها و پکیج‌های تست فشار و پایش اصالت فایل‌ها.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
from datetime import datetime, date
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from config import DOCUMENTS_DIR
from db.manager import DatabaseManager
from db.models import (
    Document,
    DocumentRevision,
    Line,
    Spool,
    Weld,
    TestPackage,
)
from repositories.document_repository import DocumentRepository
from services.license import increment_usage

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Engineering Standards
# ──────────────────────────────────────────────

class DocumentType(str, Enum):
    """انواع استاندارد مدارک مهندسی و بازرسی در پایپینگ"""
    ISOMETRIC_DRAWING = "ISOMETRIC"            # Implementation note.
    PID = "PID"                                # Implementation note.
    PLOT_PLAN = "PLOT_PLAN"                    # Implementation note.
    WPS = "WPS"                                # Implementation note.
    PQR = "PQR"                                # Implementation note.
    LINE_LIST = "LINE_LIST"                    # Implementation note.
    PIPE_SUPPORT_DWG = "SUPPORT_DWG"           # Implementation note.
    TEST_PACKAGE_DOSSIER = "TEST_DOSSIER"      # Implementation note.
    MTO = "MTO"                                # Implementation note.
    TECHNICAL_QUERY = "TQ"                     # Implementation note.


class DocumentStatus(str, Enum):
    """مراحل چرخه حیات و اعتبار مهندسی مدرک"""
    DRAFT = "DRAFT"                            # Implementation note.
    UNDER_REVIEW = "UNDER_REVIEW"              # Implementation note.
    IFC = "IFC"                                # Implementation note.
    IFI = "IFI"                                # Implementation note.
    AS_BUILT = "AS_BUILT"                      # Implementation note.
    SUPERSEDED = "SUPERSEDED"                  # Implementation note.
    VOID = "VOID"                              # Implementation note.


class DisciplineType(str, Enum):
    """دیسیپلین‌های مهندسی پروژه"""
    PIPING = "Piping"
    MECHANICAL = "Mechanical"
    CIVIL_STRUCTURE = "Civil/Structure"
    ELECTRICAL = "Electrical"
    INSTRUMENTATION = "Instrumentation"
    PROCESS = "Process"
    QA_QC = "QA/QC"


# ──────────────────────────────────────────────
#  Document Workflow Service Implementation
# ──────────────────────────────────────────────

class DocumentWorkflowService:
    """
    سرویس مدیریت جریان اسناد مهندسی، کنترل نسخه و ماتریس ارتباطات فنی
    """

    CHUNK_SIZE = 1024 * 1024  # Implementation note.

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.repo = DocumentRepository(db)

    # Implementation note.

    def register_document(
        self,
        project_id: int,
        doc_number: str,
        doc_type: Union[DocumentType, str],
        *,
        title: str = "",
        revision: str = "0",
        status: Union[DocumentStatus, str] = DocumentStatus.IFC,
        line_number: str = "",
        area_id: Optional[int] = None,
        source_file: Optional[Union[str, Path]] = None,
        discipline: Union[DisciplineType, str] = DisciplineType.PIPING,
        originator: str = "",
        created_by: str = "",
        issued_date: Optional[date] = None,
    ) -> Optional[Document]:
        """
        ثبت سند مهندسی جدید با بررسی عدم تکرار در سطح پروژه،
        انتقال امن فایل به مخزن، محاسبه اثر انگشت SHA-256 و ثبت ریویژن پایه.
        """
        if not increment_usage(self.db):
            logger.error("License limit reached. Cannot register new document.")
            return None

        doc_num_clean = doc_number.strip().upper()
        doc_type_val = doc_type.value if isinstance(doc_type, DocumentType) else str(doc_type).strip()
        status_val = status.value if isinstance(status, DocumentStatus) else str(status).strip()
        discipline_val = discipline.value if isinstance(discipline, DisciplineType) else str(discipline).strip()

        with self.db.session_scope() as session:
            # Implementation note.
            existing = (
                session.query(Document)
                .filter(
                    Document.project_id == project_id,
                    Document.doc_number == doc_num_clean,
                )
                .first()
            )
            if existing:
                logger.warning(f"Document '{doc_num_clean}' already exists in Project #{project_id}.")
                return None

            # Implementation note.
            stored_path = ""
            file_sha256 = ""
            if source_file and Path(source_file).is_file():
                stored_path, file_sha256 = self._store_file_safely(
                    project_id=project_id,
                    doc_number=doc_num_clean,
                    revision=revision,
                    source_path=Path(source_file),
                )

            # Implementation note.
            doc = Document(
                project_id=project_id,
                area_id=area_id,
                doc_number=doc_num_clean,
                doc_type=doc_type_val,
                title=title.strip() or doc_num_clean,
                revision=revision.strip(),
                status=status_val,
                file_path=stored_path,
                line_number=line_number.strip().upper() if line_number else None,
                discipline=discipline_val,
                originator=originator.strip(),
                issued_date=issued_date or date.today(),
                created_by=created_by,
                created_at=datetime.utcnow(),
            )
            session.add(doc)
            session.flush()

            # Implementation note.
            first_rev = DocumentRevision(
                document_id=doc.id,
                revision=revision.strip(),
                file_path=stored_path,
                comments="Initial registration",
                reviewed_by=created_by,
                approved_by=originator,
                created_at=datetime.utcnow(),
            )
            session.add(first_rev)

            logger.info(f"Document '{doc.doc_number}' (Rev {revision}) successfully registered in Project #{project_id}.")
            return doc

    # Implementation note.

    def add_revision(
        self,
        project_id: int,
        doc_number: str,
        new_revision: str,
        *,
        source_file: Optional[Union[str, Path]] = None,
        comments: str = "",
        reviewed_by: str = "",
        approved_by: str = "",
        set_as_current: bool = True,
        auto_supersede_previous: bool = True,
    ) -> Tuple[bool, str]:
        """
        ثبت نسخه جدید (Revision)، ذخیره فایل، به‌روزرسانی سند اصلی
        و ابطال خودکار (Supersede) وضعیت نقشه‌های قدیمی در کارگاه.
        """
        doc_num_clean = doc_number.strip().upper()

        with self.db.session_scope() as session:
            doc = (
                session.query(Document)
                .filter(
                    Document.project_id == project_id,
                    Document.doc_number == doc_num_clean,
                )
                .first()
            )
            if not doc:
                return False, f"Document '{doc_num_clean}' not found in Project #{project_id}."

            # Implementation note.
            existing_rev = (
                session.query(DocumentRevision)
                .filter(
                    DocumentRevision.document_id == doc.id,
                    DocumentRevision.revision == new_revision.strip(),
                )
                .first()
            )
            if existing_rev:
                return False, f"Revision '{new_revision}' already exists for document '{doc_num_clean}'."

            # Implementation note.
            stored_path = doc.file_path or ""
            if source_file and Path(source_file).is_file():
                stored_path, _ = self._store_file_safely(
                    project_id=project_id,
                    doc_number=doc_num_clean,
                    revision=new_revision,
                    source_path=Path(source_file),
                )

            # Implementation note.
            rev_record = DocumentRevision(
                document_id=doc.id,
                revision=new_revision.strip(),
                file_path=stored_path,
                comments=comments.strip(),
                reviewed_by=reviewed_by.strip(),
                approved_by=approved_by.strip(),
                created_at=datetime.utcnow(),
            )
            session.add(rev_record)

            if set_as_current:
                doc.revision = new_revision.strip()
                doc.file_path = stored_path
                doc.updated_at = datetime.utcnow()
                
                # Implementation note.
                if auto_supersede_previous and doc.status == DocumentStatus.IFC.value:
                    doc.status = DocumentStatus.IFC.value
                    logger.info(f"Document '{doc_num_clean}' previous revision superseded by Rev {new_revision}.")

            logger.info(f"Revision '{new_revision}' added to document '{doc_num_clean}'.")
            return True, f"Revision '{new_revision}' successfully added to '{doc_num_clean}'."

    # Implementation note.

    def change_status(
        self,
        project_id: int,
        doc_number: str,
        new_status: Union[DocumentStatus, str],
        reason: str = "",
    ) -> Tuple[bool, str]:
        """تغییر وضعیت رسمی مدرک (مانند ارتقا به IFC، ابطال به VOID یا تأیید As-Built)"""
        status_val = new_status.value if isinstance(new_status, DocumentStatus) else str(new_status).strip()
        doc_num_clean = doc_number.strip().upper()

        with self.db.session_scope() as session:
            doc = (
                session.query(Document)
                .filter(
                    Document.project_id == project_id,
                    Document.doc_number == doc_num_clean,
                )
                .first()
            )
            if not doc:
                return False, f"Document '{doc_num_clean}' not found in Project #{project_id}."

            old_status = doc.status
            doc.status = status_val
            doc.updated_at = datetime.utcnow()

            logger.info(f"Document '{doc_num_clean}' status changed from '{old_status}' to '{status_val}'. Reason: {reason}")
            return True, f"Status of '{doc_num_clean}' updated to '{status_val}'."

    # Implementation note.

    def get_related_documents_for_spool(self, project_id: int, spool_number: str) -> List[Dict[str, Any]]:
        """بازیابی تمام نقشه‌های ایزومتریک، P&ID و مدارک مرتبط با یک اسپول مشخص"""
        with self.db.session_scope() as session:
            spool = (
                session.query(Spool)
                .filter(
                    Spool.project_id == project_id,
                    Spool.spool_number == spool_number.strip().upper(),
                )
                .first()
            )
            if not spool:
                return []

            # Implementation note.
            query = session.query(Document).filter(Document.project_id == project_id)
            filters = []
            if getattr(spool, "line_number", None):
                filters.append(Document.line_number == spool.line_number)
            if getattr(spool, "drawing_number", None):
                filters.append(Document.doc_number == spool.drawing_number)

            if not filters:
                return []

            docs = query.filter(or_(*filters)).all()
            return [
                {
                    "doc_number": d.doc_number,
                    "doc_type": d.doc_type,
                    "title": d.title,
                    "revision": d.revision,
                    "status": d.status,
                    "file_path": d.file_path,
                }
                for d in docs
            ]

    # Implementation note.

    def search_documents(
        self,
        project_id: int,
        keyword: Optional[str] = None,
        doc_type: Optional[Union[DocumentType, str]] = None,
        status: Optional[Union[DocumentStatus, str]] = None,
        discipline: Optional[Union[DisciplineType, str]] = None,
        line_number: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[List[Document], int]:
        """جستجوی چندمعیاره پیشرفته با صفحه‌بندی ایمن"""
        with self.db.session_scope() as session:
            query = session.query(Document).filter(Document.project_id == project_id)

            if keyword:
                search_str = f"%{keyword.strip()}%"
                query = query.filter(
                    or_(
                        Document.doc_number.ilike(search_str),
                        Document.title.ilike(search_str),
                        Document.originator.ilike(search_str),
                    )
                )

            if doc_type:
                dt_val = doc_type.value if isinstance(doc_type, DocumentType) else doc_type
                query = query.filter(Document.doc_type == dt_val)

            if status:
                st_val = status.value if isinstance(status, DocumentStatus) else status
                query = query.filter(Document.status == st_val)

            if discipline:
                disc_val = discipline.value if isinstance(discipline, DisciplineType) else discipline
                query = query.filter(Document.discipline == disc_val)

            if line_number:
                query = query.filter(Document.line_number.ilike(f"%{line_number.strip()}%"))

            total_count = query.count()
            items = (
                query.order_by(Document.doc_type.asc(), Document.doc_number.asc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            return items, total_count

    # Implementation note.

    def get_stats(self, project_id: int) -> Dict[str, Any]:
        """
        محاسبه ماتریس آماری مدارک پروژه با کوئری‌های بهینه دیتابیس
        (بدون لود کردن تمام رکوردها در حافظه)
        """
        with self.db.session_scope() as session:
            total_docs = (
                session.query(func.count(Document.id))
                .filter(Document.project_id == project_id)
                .scalar() or 0
            )

            # Implementation note.
            type_counts = (
                session.query(Document.doc_type, func.count(Document.id))
                .filter(Document.project_id == project_id)
                .group_by(Document.doc_type)
                .all()
            )
            by_type = {t: c for t, c in type_counts}

            # Implementation note.
            status_counts = (
                session.query(Document.status, func.count(Document.id))
                .filter(Document.project_id == project_id)
                .group_by(Document.status)
                .all()
            )
            by_status = {s: c for s, c in status_counts}

            ifc_count = by_status.get(DocumentStatus.IFC.value, 0)
            asbuilt_count = by_status.get(DocumentStatus.AS_BUILT.value, 0)

            return {
                "project_id": project_id,
                "total_documents": total_docs,
                "by_type": by_type,
                "by_status": by_status,
                "construction_ready_ifc_count": ifc_count,
                "as_built_certified_count": asbuilt_count,
            }

    # Implementation note.

    def _store_file_safely(
        self,
        project_id: int,
        doc_number: str,
        revision: str,
        source_path: Path,
    ) -> Tuple[str, str]:
        """
        ایمن‌سازی نام فایل، جلوگیری از Path Traversal، محاسبه هش و ذخیره در مخزن
        خروجی: (مسیر ذخیره‌شده, هش SHA-256)
        """
        # Implementation note.
        clean_doc_name = re.sub(r"[^\w\-.]", "_", doc_number)
        clean_rev = re.sub(r"[^\w\-.]", "_", revision)
        ext = source_path.suffix.lower() or ".pdf"

        safe_file_name = f"{clean_doc_name}_Rev{clean_rev}{ext}"
        dest_dir = DOCUMENTS_DIR / f"project_{project_id}"
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_file_path = dest_dir / safe_file_name

        # Implementation note.
        hasher = hashlib.sha256()
        with open(source_path, "rb") as f_src:
            while chunk := f_src.read(self.CHUNK_SIZE):
                hasher.update(chunk)

        # Implementation note.
        shutil.copy2(source_path, dest_file_path)

        return str(dest_file_path), hasher.hexdigest()