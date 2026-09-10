# -*- coding: utf-8 -*-
"""
db/models_test_request_snippet.py – PipeAgent v5.1
==================================================
Helper & extension models for the TestRequest workflow.

Provides:
  • TestRequestStatusHistory: Audit trail of every status transition
  • TestRequestComment: Threaded discussion on each request
  • TestRequestAttachment: File evidence attached to requests
  • TestRequestType: Enumeration / configuration table
  • TestRequestWorkflowRule: Project-level workflow customization
  • TestRequestMetricsView: Materialized counters (optional)
  • Status enum constants

This module re-uses the same `Base` and mixins from db.models so the
tables are picked up by `Base.metadata.create_all()`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from db.models import (
    Base,
    ReprMixin,
    TimestampMixin,
    CreatedOnlyMixin,
    Project,
    TestRequest,
    _utcnow,
)


# ══════════════════════════════════════════════
#  0. Enumerations
# ══════════════════════════════════════════════

class TestRequestStatus:
    """مقادیر ثابت برای status فیلد TestRequest."""
    OPEN = "Open"
    SCHEDULED = "Scheduled"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"
    ON_HOLD = "On Hold"

    ALL = (OPEN, SCHEDULED, IN_PROGRESS, COMPLETED, CANCELLED, REJECTED, ON_HOLD)
    TERMINAL = (COMPLETED, CANCELLED, REJECTED)


class TestRequestPriority:
    LOW = "Low"
    NORMAL = "Normal"
    HIGH = "High"
    URGENT = "Urgent"
    ALL = (LOW, NORMAL, HIGH, URGENT)


class TestRequestType:
    NDT = "NDT"
    FITUP = "Fit-up"
    HYDRO = "Hydro"
    VISUAL = "Visual"
    FINAL = "Final"
    PWHT = "PWHT"
    PMI = "PMI"
    LEAK_TEST = "Leak Test"
    ALL = (NDT, FITUP, HYDRO, VISUAL, FINAL, PWHT, PMI, LEAK_TEST)


# Allowed status transitions (workflow state machine)
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    TestRequestStatus.OPEN:        (TestRequestStatus.SCHEDULED, TestRequestStatus.CANCELLED, TestRequestStatus.ON_HOLD),
    TestRequestStatus.SCHEDULED:   (TestRequestStatus.IN_PROGRESS, TestRequestStatus.CANCELLED, TestRequestStatus.ON_HOLD),
    TestRequestStatus.IN_PROGRESS: (TestRequestStatus.COMPLETED, TestRequestStatus.REJECTED, TestRequestStatus.ON_HOLD),
    TestRequestStatus.ON_HOLD:     (TestRequestStatus.OPEN, TestRequestStatus.SCHEDULED, TestRequestStatus.CANCELLED),
    TestRequestStatus.REJECTED:    (TestRequestStatus.OPEN, TestRequestStatus.CANCELLED),
    # terminal: COMPLETED, CANCELLED → no transitions
}


def is_transition_allowed(old_status: str, new_status: str) -> bool:
    """آیا انتقال از وضعیت قدیم به جدید مجاز است؟"""
    if old_status == new_status:
        return True
    return new_status in ALLOWED_TRANSITIONS.get(old_status, ())


# ══════════════════════════════════════════════
#  1. TestRequestStatusHistory
# ══════════════════════════════════════════════

class TestRequestStatusHistory(Base, ReprMixin):
    """تاریخچه‌ی کامل تغییر وضعیت یک TestRequest (Audit Trail)."""
    __tablename__ = "test_request_status_history"
    _repr_fields = ("id", "old_status", "new_status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_request_id = Column(
        Integer, ForeignKey("test_requests.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    old_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=False, index=True)
    changed_by = Column(String(100), nullable=False)
    changed_at = Column(DateTime, default=_utcnow, nullable=False, index=True)
    comment = Column(Text, nullable=True)

    test_request = relationship("TestRequest")

    __table_args__ = (
        Index("ix_treq_history_request_time", "test_request_id", "changed_at"),
    )


# ══════════════════════════════════════════════
#  2. TestRequestComment
# ══════════════════════════════════════════════

class TestRequestComment(Base, CreatedOnlyMixin, ReprMixin):
    """نظرات و گفت‌وگو روی هر TestRequest (threaded)."""
    __tablename__ = "test_request_comments"
    _repr_fields = ("id", "author", "test_request_id")

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_request_id = Column(
        Integer, ForeignKey("test_requests.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    parent_comment_id = Column(
        Integer, ForeignKey("test_request_comments.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    author = Column(String(100), nullable=False)
    body = Column(Text, nullable=False)
    is_internal = Column(Boolean, default=False, index=True)

    test_request = relationship("TestRequest", foreign_keys=[test_request_id])
    replies = relationship(
        "TestRequestComment",
        backref=__import__("sqlalchemy").orm.backref("parent", remote_side=[id]),
        cascade="all, delete-orphan",
    )


# ══════════════════════════════════════════════
#  3. TestRequestAttachment
# ══════════════════════════════════════════════

class TestRequestAttachment(Base, CreatedOnlyMixin, ReprMixin):
    """فایل‌های پیوست‌شده به TestRequest (عکس، گزارش، ITR)."""
    __tablename__ = "test_request_attachments"
    _repr_fields = ("id", "file_name", "sha256")

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_request_id = Column(
        Integer, ForeignKey("test_requests.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    file_name = Column(String(300), nullable=False)
    file_path = Column(String(500), nullable=False)
    sha256 = Column(String(64), nullable=True, index=True)
    file_size_bytes = Column(Integer, nullable=True)
    mime_type = Column(String(120), nullable=True)
    caption = Column(String(300), nullable=True)
    uploaded_by = Column(String(100), nullable=False)

    test_request = relationship("TestRequest", foreign_keys=[test_request_id])


# ══════════════════════════════════════════════
#  4. TestRequestType (Config Table)
# ══════════════════════════════════════════════

class TestRequestTypeConfig(Base, ReprMixin):
    """پیکربندی انواع درخواست تست در سطح پروژه (قابل تنظیم توسط کاربر)."""
    __tablename__ = "test_request_type_config"
    _repr_fields = ("id", "code", "label")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    code = Column(String(50), nullable=False, index=True)
    label = Column(String(150), nullable=False)
    default_method = Column(String(50), nullable=True)
    requires_witness = Column(Boolean, default=False)
    sla_hours = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    sort_order = Column(Integer, default=100)

    project = relationship("Project")

    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_treq_type_per_project"),
    )


# ══════════════════════════════════════════════
#  5. TestRequestWorkflowRule
# ══════════════════════════════════════════════

class TestRequestWorkflowRule(Base, ReprMixin):
    """قوانین workflow سفارشی برای هر نوع درخواست در هر پروژه."""
    __tablename__ = "test_request_workflow_rules"
    _repr_fields = ("id", "request_type", "from_status", "to_status")

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    request_type = Column(String(50), nullable=False, index=True)
    from_status = Column(String(30), nullable=False)
    to_status = Column(String(30), nullable=False)
    required_role = Column(String(50), nullable=True)  # Implementation note.
    auto_assign_to = Column(String(100), nullable=True)  # Implementation note.
    notify_emails = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, index=True)

    project = relationship("Project")

    __table_args__ = (
        UniqueConstraint(
            "project_id", "request_type", "from_status", "to_status",
            name="uq_treq_workflow_rule",
        ),
    )


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════

def record_status_change(
    session,
    test_request_id: int,
    *,
    old_status: Optional[str],
    new_status: str,
    changed_by: str,
    comment: Optional[str] = None,
) -> TestRequestStatusHistory:
    """
    ثبت تغییر وضعیت و ایجاد ردیف تاریخچه.

    Raises:
        ValueError: اگر انتقال وضعیت مجاز نباشد
    """
    if old_status is not None and not is_transition_allowed(old_status, new_status):
        raise ValueError(
            f"Invalid status transition: {old_status} → {new_status}",
        )

    history = TestRequestStatusHistory(
        test_request_id=test_request_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        comment=comment,
    )
    session.add(history)
    return history


def get_open_count_for_project(session, project_id: int) -> int:
    """تعداد TestRequestهای باز یک پروژه."""
    return (
        session.query(TestRequest)
        .filter(
            TestRequest.project_id == project_id,
            TestRequest.status.notin_(TestRequestStatus.TERMINAL),
        )
        .count()
    )# placeholder - TestRequest is appended via models update in same commit
