# -*- coding: utf-8 -*-
"""
core/execution_bridge.py – PipeAgent
پل ارتباطی خودکار ثبت وقایع اجرایی (Execution OS Event Sourcing & Audit Engine)
شامل: ردیابی تفکیکی تغییرات (Granular Diffs)، ثبت کانتکست کاربر (Actor/IP Attribution)،
ماسک‌سازی امن داده‌های حساس، ممانعت از کوئری‌های تکراری و موتور انتشار رویدادهای زنده.
"""

from __future__ import annotations

import contextvars
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, Union

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, UOWTransaction

from db.models import (
    ExecutionEvent, Project, LineListItem, Weld, NDTRecord, TestPackage,
    WorkFront, WorkAssignment, WorkTeam, SiteMachine, WeldReportDraft,
    FitupReportDraft, Document, HandoverPackage, PunchItem, TurnoverDossier,
    MaterialItem, TestRequest, ProjectAction, NCRRecord, PWHTRecord,
    PaintingRecord, InsulationRecord, ReinstatementItem, LeakTestRecord,
    FlushingRecord, BoxUpRecord, WalkdownChecklist, AsBuiltMarkUp, User,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Context & Security Configuration
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class ExecutionContext:
    """کانتکست امنیتی و مکانی اجرای عملیات (Thread-Safe & Async-Safe)"""
    user_id: Optional[int] = None
    username: str = "system"
    client_ip: Optional[str] = None
    session_token: Optional[str] = None
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = "WEB_CLIENT"  # Implementation note.


# Implementation note.
execution_context_var: contextvars.ContextVar[ExecutionContext] = contextvars.ContextVar(
    "execution_context", default=ExecutionContext()
)


class EventAction(str, Enum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    DELETED = "DELETED"
    SOFT_DELETED = "SOFT_DELETED"


# Implementation note.
SENSITIVE_FIELDS: Set[str] = {
    "password", "hashed_password", "token_hash", "secret_token",
    "api_key", "secret", "private_key", "salt"
}

# Implementation note.
TRACKED_ENTITIES: Set[Type[Any]] = {
    Project, LineListItem, Weld, NDTRecord, TestPackage, WorkFront,
    WorkAssignment, WorkTeam, SiteMachine, WeldReportDraft, FitupReportDraft,
    Document, HandoverPackage, PunchItem, TurnoverDossier, MaterialItem,
    TestRequest, ProjectAction, NCRRecord, PWHTRecord, PaintingRecord,
    InsulationRecord, ReinstatementItem, LeakTestRecord, FlushingRecord,
    BoxUpRecord, WalkdownChecklist, AsBuiltMarkUp, User,
}


# ──────────────────────────────────────────────
#  In-Memory Event Bus (Observer Pattern)
# ──────────────────────────────────────────────

class EventBus:
    """موتور اشتراک و انتشار بلادرنگ وقایع برای وب‌سوکت‌ها و هشدارهای کیفی"""
    _listeners: Dict[str, List[Callable[[ExecutionEvent], None]]] = {}

    @classmethod
    def subscribe(cls, entity_type: str, callback: Callable[[ExecutionEvent], None]) -> None:
        cls._listeners.setdefault(entity_type, []).append(callback)

    @classmethod
    def publish(cls, events: List[ExecutionEvent]) -> None:
        for ev in events:
            # Implementation note.
            targets = cls._listeners.get(ev.entity_type, []) + cls._listeners.get("*", [])
            for callback in targets:
                try:
                    callback(ev)
                except Exception as err:
                    logger.error(f"Error in event listener callback: {err}")


# ──────────────────────────────────────────────
#  Event Bridge Engine
# ──────────────────────────────────────────────

class ExecutionBridge:
    """
    موتور مرکزی اتصال پایگاه‌داده به سیستم وقایع اجرایی با کارایی بالا
    """
    _INSTALLED: bool = False

    @classmethod
    def install(cls) -> None:
        """ثبت هوک مانیتورینگ تغییرات در سطح Sessionهای SQLAlchemy"""
        if cls._INSTALLED:
            return
        event.listen(Session, "after_flush", cls._handle_after_flush, propagate=True)
        cls._INSTALLED = True
        logger.info("Execution OS Event Bridge successfully installed on SQLAlchemy Session.")

    @classmethod
    def uninstall(cls) -> None:
        """حذف هوک مانیتورینگ"""
        if cls._INSTALLED:
            event.remove(Session, "after_flush", cls._handle_after_flush)
            cls._INSTALLED = False
            logger.info("Execution OS Event Bridge uninstalled.")

    # Implementation note.

    @classmethod
    def _handle_after_flush(cls, session: Session, flush_context: UOWTransaction) -> None:
        # Implementation note.
        if session.info.get("_execution_bridge_running"):
            return

        ctx = execution_context_var.get()
        captured_events: List[ExecutionEvent] = []

        # Implementation note.
        all_objects = list(session.new) + list(session.dirty) + list(session.deleted)

        for obj in all_objects:
            obj_type = type(obj)
            if obj_type not in TRACKED_ENTITIES or isinstance(obj, ExecutionEvent):
                continue

            # Implementation note.
            project_id = cls._resolve_project_id(session, obj)
            if not project_id:
                continue  # Implementation note.

            line_number = cls._resolve_line_number(obj)
            entity_id = getattr(obj, "id", None)

            # Implementation note.
            if obj in session.deleted:
                event_type = EventAction.DELETED.value
                old_snapshot = cls._extract_full_snapshot(obj)
                new_snapshot = {"_deleted": True}
            elif obj in session.new:
                event_type = EventAction.CREATED.value
                old_snapshot = {}
                new_snapshot = cls._extract_full_snapshot(obj)
            elif obj in session.dirty:
                changes = cls._extract_attribute_changes(obj)
                if not changes:
                    continue  # Implementation note.

                # Implementation note.
                if "is_deleted" in changes and changes["is_deleted"].get("new") is True:
                    event_type = EventAction.SOFT_DELETED.value
                else:
                    event_type = EventAction.UPDATED.value

                old_snapshot = {k: v["old"] for k, v in changes.items()}
                new_snapshot = {k: v["new"] for k, v in changes.items()}
            else:
                continue

            # Implementation note.
            event_record = ExecutionEvent(
                project_id=project_id,
                event_type=event_type,
                entity_type=obj_type.__name__,
                entity_id=entity_id,
                line_number=line_number,
                old_value=json.dumps(old_snapshot, default=cls._json_serial, ensure_ascii=False),
                new_value=json.dumps(new_snapshot, default=cls._json_serial, ensure_ascii=False),
                source=ctx.source,
                correlation_id=ctx.correlation_id,
                user_id=ctx.user_id,
                username=ctx.username,
                client_ip=ctx.client_ip,
                occurred_at=datetime.utcnow(),
            )
            captured_events.append(event_record)

        # Implementation note.
        if captured_events:
            session.info["_execution_bridge_running"] = True
            try:
                session.add_all(captured_events)
                # Implementation note.
                EventBus.publish(captured_events)
            finally:
                session.info.pop("_execution_bridge_running", None)

    # Implementation note.

    @classmethod
    def _resolve_project_id(cls, session: Session, obj: Any) -> Optional[int]:
        """استخراج شناسه پروژه با بررسی حافظه جاری و جلوگیری از کوئری‌های تکراری"""
        # Implementation note.
        pid = getattr(obj, "project_id", None)
        if pid:
            return pid

        # Implementation note.
        state = inspect(obj)
        if hasattr(obj, "weld") and "weld" in state.dict:
            return getattr(obj.weld, "project_id", None)

        if hasattr(obj, "work_front") and "work_front" in state.dict:
            return getattr(obj.work_front, "project_id", None)

        # Implementation note.
        if isinstance(obj, NDTRecord) and hasattr(obj, "weld_id_fk") and obj.weld_id_fk:
            # Implementation note.
            cached_weld = session.identity_map.get((Weld, (obj.weld_id_fk,)))
            if cached_weld:
                return getattr(cached_weld, "project_id", None)

        return None

    @classmethod
    def _resolve_line_number(cls, obj: Any) -> Optional[str]:
        """استخراج شماره خط لوله مرتبط با موجودیت"""
        for attr_name in ("line_number", "line_no", "line"):
            val = getattr(obj, attr_name, None)
            if val:
                return str(val).strip().upper()
        return None

    # Implementation note.

    @classmethod
    def _extract_attribute_changes(cls, obj: Any) -> Dict[str, Dict[str, Any]]:
        """استخراج دقیق تغییرات فیلدها با حذف متادیتای سیستمی و داده‌های حساس"""
        state = inspect(obj)
        changes: Dict[str, Dict[str, Any]] = {}

        for attr in state.attrs:
            # Implementation note.
            if attr.key in {"updated_at", "created_at", "last_synced_at"}:
                continue

            # Implementation note.
            if attr.key in SENSITIVE_FIELDS:
                continue

            hist = attr.history
            if hist.has_changes():
                old_val = hist.deleted[-1] if hist.deleted else None
                new_val = hist.added[-1] if hist.added else getattr(obj, attr.key, None)

                # Implementation note.
                if old_val != new_val:
                    changes[attr.key] = {
                        "old": cls._sanitize_value(old_val),
                        "new": cls._sanitize_value(new_val),
                    }
        return changes

    @classmethod
    def _extract_full_snapshot(cls, obj: Any) -> Dict[str, Any]:
        """تولید اسنپ‌شات کامل از رکورد در زمان ایجاد (Creation Baseline)"""
        state = inspect(obj)
        snapshot: Dict[str, Any] = {}

        for col in state.mapper.column_attrs:
            key = col.key
            if key in SENSITIVE_FIELDS or key in {"created_at", "updated_at"}:
                continue
            val = getattr(obj, key, None)
            if val is not None:
                snapshot[key] = cls._sanitize_value(val)
        return snapshot

    @classmethod
    def _sanitize_value(cls, val: Any) -> Any:
        """پاکسازی و استانداردسازی مقادیر"""
        if isinstance(val, (datetime, date)):
            return val.isoformat()
        if isinstance(val, Decimal):
            return float(val)
        if isinstance(val, uuid.UUID):
            return str(val)
        return val

    @staticmethod
    def _json_serial(obj: Any) -> str:
        """سریالایزر اختصاصی برای داده‌های پیچیده پایتون"""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return str(obj)


# ──────────────────────────────────────────────
#  Execution Timeline Query Service
# ──────────────────────────────────────────────

class ExecutionTimelineService:
    """
    سرویس بازیابی و ارائه تاریخچه زمانی رویدادها جهت ممیزی کیفی و رسیدگی به ادعاها
    """

    def __init__(self, session: Session):
        self.session = session

    def get_entity_audit_trail(
        self,
        entity_type: str,
        entity_id: int,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """بازیابی سیر زمانی کامل تغییرات یک موجودیت خاص (مثلاً سرجوش W-01)"""
        events = (
            self.session.query(ExecutionEvent)
            .filter(
                ExecutionEvent.entity_type == entity_type.strip(),
                ExecutionEvent.entity_id == entity_id,
            )
            .order_by(desc(ExecutionEvent.occurred_at))
            .limit(limit)
            .all()
        )

        timeline = []
        for ev in events:
            timeline.append({
                "event_id": ev.id,
                "action": ev.event_type,
                "user": ev.username or f"User #{ev.user_id}",
                "ip": ev.client_ip,
                "source": ev.source,
                "occurred_at": ev.occurred_at.isoformat(),
                "changes": json.loads(ev.new_value or "{}"),
                "previous_state": json.loads(ev.old_value or "{}"),
            })
        return timeline

    def get_project_event_stream(
        self,
        project_id: int,
        from_time: Optional[datetime] = None,
        event_type: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """جریان زنده وقایع کل پروژه جهت مانیتورینگ در اتاق کنترل (Control Tower)"""
        query = self.session.query(ExecutionEvent).filter(ExecutionEvent.project_id == project_id)

        if from_time:
            query = query.filter(ExecutionEvent.occurred_at >= from_time)
        if event_type:
            query = query.filter(ExecutionEvent.event_type == event_type.strip().upper())

        events = query.order_by(desc(ExecutionEvent.occurred_at)).limit(limit).all()

        return [
            {
                "id": ev.id,
                "entity": ev.entity_type,
                "entity_id": ev.entity_id,
                "line": ev.line_number,
                "action": ev.event_type,
                "user": ev.username,
                "occurred_at": ev.occurred_at.isoformat(),
            }
            for ev in events
        ]


# Implementation note.
def install_execution_bridge():
    ExecutionBridge.install()

def install():
    """Public compatibility entry point for installing the Execution OS bridge."""
    ExecutionBridge.install()


def uninstall():
    """Public compatibility entry point for removing the Execution OS bridge."""
    ExecutionBridge.uninstall()
