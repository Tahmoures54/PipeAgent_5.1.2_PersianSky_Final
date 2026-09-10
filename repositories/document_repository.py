# -*- coding: utf-8 -*-
"""
repositories/document_repository.py – PipeAgent v5.1
=====================================================
Enterprise Repository Layer for Document Management Systems (DMS).

Repositories covered:
  • DocumentRepository          – مدیریت شناسنامه مدارک و اسناد فنی
  • DocumentRevisionRepository  – مدیریت چرخه‌ی نسخه‌گذاری و تاییدات فنی
  • TransmittalRepository       – مدیریت ترنسمیتال‌ها و بسته‌های ارسالی مدارک
  • DocumentEvidenceRepository  – ممیزی اصالت و هش دیجیتال مدارک (Enterprise)
  • DMSDashboardRepository      – استخراج شاخص‌ها و آمار تجمیعی کنترل مدارک

Features:
  - Full Unit of Work support (accepts active Session or DatabaseManager)
  - Automatic parent revision propagation
  - Multi-criteria industrial filtering & text search
  - High-performance pagination and eager loading
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from sqlalchemy.orm import Session

from db.models import (
    Document,
    DocumentRevision,
    Transmittal,
    TransmittalItem,
)

# Implementation note.
try:
    from db.models_enterprise import DocumentEvidence
except ImportError:
    DocumentEvidence = None

from db.queries import document_queries as q
from repositories.base import BaseRepository

try:
    from db.manager import DatabaseManager
except ImportError:
    DatabaseManager = Any  # type: ignore

logger = logging.getLogger(__name__)

__all__ = [
    "DocumentRepository",
    "DocumentRevisionRepository",
    "TransmittalRepository",
    "DocumentEvidenceRepository",
    "DMSDashboardRepository",
]


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

class DocumentRepository(BaseRepository[Document]):
    """مخزن مدیریت شناسنامه‌ی مدارک و نقشه‌های مهندسی."""

    def __init__(self, session_or_db: Union[Session, DatabaseManager]) -> None:
        super().__init__(session_or_db, Document)

    def get_by_id(self, doc_id: int) -> Optional[Document]:
        """دریافت سند بر اساس شناسه اصلی همراه با نسخه‌های پیوست."""
        return q.get_document_by_id(self.session, doc_id)

    def get_by_doc_number(self, project_id: int, doc_number: str) -> Optional[Document]:
        """دریافت سند بر اساس شماره یکتای مدرک در پروژه."""
        return q.get_document_by_number(self.session, project_id, doc_number)

    def get_all(
        self,
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
        جستجو و دریافت اسناد با فیلترهای چندگانه و صفحه‌بندی.
        """
        return q.get_documents(
            self.session,
            project_id,
            doc_type=doc_type,
            status=status,
            discipline=discipline,
            line_number=line_number,
            spool_id=spool_id,
            weld_id=weld_id,
            test_package_id=test_package_id,
            search=search,
            offset=offset,
            limit=limit,
        )

    def get_by_project(self, project_id: int, offset: int = 0, limit: int = 100) -> List[Document]:
        """دریافت اسناد پروژه (سازگار با کدهای قدیمی + صفحه‌بندی)."""
        return self.get_all(project_id, offset=offset, limit=limit)

    def get_by_type(self, project_id: int, doc_type: str, offset: int = 0, limit: int = 100) -> List[Document]:
        """دریافت اسناد بر اساس نوع مدرک (سازگار با کدهای قدیمی)."""
        return self.get_all(project_id, doc_type=doc_type, offset=offset, limit=limit)

    def add(self, **kwargs: Any) -> Document:
        """ثبت شناسنامه سند جدید."""
        return q.create_document(self.session, **kwargs)

    def edit(self, doc_id: int, **kwargs: Any) -> Optional[Document]:
        """به‌روزرسانی مشخصات فنی مدرک."""
        return q.update_document(self.session, doc_id, **kwargs)

    def remove(self, doc_id: int) -> bool:
        """حذف سند و تمام سوابق بازنگری‌های آن."""
        return q.delete_document(self.session, doc_id)


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

class DocumentRevisionRepository(BaseRepository[DocumentRevision]):
    """مخزن مدیریت نسخه‌ها و بازنگری‌های اسناد مهندسی."""

    def __init__(self, session_or_db: Union[Session, DatabaseManager]) -> None:
        super().__init__(session_or_db, DocumentRevision)

    def get_by_id(self, revision_id: int) -> Optional[DocumentRevision]:
        """دریافت یک نسخه مشخص بر اساس شناسه."""
        return q.get_revision_by_id(self.session, revision_id)

    def get_for_document(self, doc_id: int) -> List[DocumentRevision]:
        """دریافت تاریخچه‌ی کامل تمام نسخه‌های یک مدرک."""
        return q.get_document_revisions(self.session, doc_id)

    def get_latest(self, doc_id: int) -> Optional[DocumentRevision]:
        """دریافت آخرین نسخه تاییدشده یا ثبت‌شده برای مدرک."""
        return q.get_latest_revision(self.session, doc_id)

    def add_revision(
        self,
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
        ثبت یک نسخه جدید برای مدرک و همگام‌سازی خودکار وضعیت سند والد.
        """
        return q.create_document_revision(
            self.session,
            doc_id,
            revision,
            file_path,
            comments=comments,
            reviewed_by=reviewed_by,
            approved_by=approved_by,
            auto_update_parent=auto_update_parent,
        )

    def remove(self, revision_id: int) -> bool:
        """حذف یک نسخه خاص از تاریخچه مدارک."""
        return q.delete_document_revision(self.session, revision_id)


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

class TransmittalRepository(BaseRepository[Transmittal]):
    """مخزن مدیریت ترنسمیتال‌ها و بسته‌های تبادل اسناد پروژه."""

    def __init__(self, session_or_db: Union[Session, DatabaseManager]) -> None:
        super().__init__(session_or_db, Transmittal)

    def get_by_id(self, transmittal_id: int) -> Optional[Transmittal]:
        """دریافت ترنسمیتال به همراه اقلام پیوست‌شده."""
        return q.get_transmittal_by_id(self.session, transmittal_id)

    def get_by_number(self, project_id: int, transmittal_no: str) -> Optional[Transmittal]:
        """دریافت ترنسمیتال بر اساس شماره ثبت رسمی."""
        return q.get_transmittal_by_number(self.session, project_id, transmittal_no)

    def get_all(
        self,
        project_id: int,
        *,
        to_company: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[Transmittal]:
        """دریافت لیست ترنسمیتال‌های صادرشده با صفحه‌بندی."""
        return q.get_transmittals(
            self.session,
            project_id,
            to_company=to_company,
            offset=offset,
            limit=limit,
        )

    def issue_transmittal(
        self,
        project_id: int,
        transmittal_no: str,
        to_company: str,
        *,
        purpose: Optional[str] = None,
        document_ids_with_revisions: Optional[List[Tuple[int, str]]] = None,
    ) -> Transmittal:
        """
        صدور ترنسمیتال رسمی جدید همراه با الصاق مدارک و کدهای بازنگری.
        """
        return q.create_transmittal(
            self.session,
            project_id,
            transmittal_no,
            to_company,
            purpose=purpose,
            document_ids_with_revisions=document_ids_with_revisions,
        )

    def remove(self, transmittal_id: int) -> bool:
        """حذف ترنسمیتال."""
        return q.delete_transmittal(self.session, transmittal_id)


# ══════════════════════════════════════════════
#  4. Document Evidence Repository (Enterprise)
# ══════════════════════════════════════════════

class DocumentEvidenceRepository:
    """مخزن کنترل اصالت، ممیزی و هشدارهای دستکاری اسناد (SHA256)."""

    def __init__(self, session_or_db: Union[Session, DatabaseManager]) -> None:
        if hasattr(session_or_db, "get_session"):
            self.session = session_or_db.get_session()
        else:
            self.session = session_or_db

    def get_evidence(
        self,
        project_id: int,
        entity_key: str,
        *,
        entity_type: str = "Document",
    ) -> List[Any]:
        """دریافت تاریخچه‌ی گواهی‌های اصالت هش فایل."""
        return q.get_document_evidence(
            self.session,
            project_id,
            entity_key,
            entity_type=entity_type,
        )

    def record_evidence(self, **kwargs: Any) -> Any:
        """ثبت هش امنیتی SHA256 مدرک تاییدشده."""
        return q.create_document_evidence(self.session, **kwargs)


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

class DMSDashboardRepository:
    """مخزن تجمیع و استخراج شاخص‌های عملکردی کنترل مدارک (DMS KPIs)."""

    def __init__(self, session_or_db: Union[Session, DatabaseManager]) -> None:
        if hasattr(session_or_db, "get_session"):
            self.session = session_or_db.get_session()
        else:
            self.session = session_or_db

    def get_stats(self, project_id: int) -> Dict[str, Any]:
        """استخراج گزارش آماری مدارک، وضعیت تاییدات و دیسیپلین‌ها."""
        return q.get_dms_dashboard_stats(self.session, project_id)