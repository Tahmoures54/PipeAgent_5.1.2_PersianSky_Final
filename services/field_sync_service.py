# -*- coding: utf-8 -*-
"""
services/field_sync_service.py – PipeAgent
موتور پیشرفته و ایزوله سمت سرور برای همگام‌سازی داده‌های کارگاهی (Server-Side Field Sync Engine)
شامل: تضمین کامل Idempotency، اعمال معتبر تغییرات روی مدل‌های اصلی سرور،
مدیریت هوشمند ارسال‌های مجدد (Retries)، حل تعارضات و صدور رسیدهای ساختاریافته (Receipts).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from db.manager import DatabaseManager
from db.models import (
    FieldSyncBatch,
    FieldSyncReceipt,
    FieldSyncEvent,
    Weld,
    Spool,
    WorkFront,
    PunchItem,
    NDTRecord,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Sync Status Standards
# ──────────────────────────────────────────────

class ReceiptStatus(str, Enum):
    ACCEPTED = "Accepted"              # Implementation note.
    DUPLICATE = "Duplicate"            # Implementation note.
    CONFLICT = "Conflict"              # Implementation note.
    REJECTED = "Rejected"              # Implementation note.
    ERROR = "Error"                    # Implementation note.


class EventType(str, Enum):
    FITUP = "FITUP"
    WELD = "WELD"
    VISUAL_QC = "VISUAL_QC"
    NDT_REQUEST = "NDT_REQUEST"
    REPAIR_MARK = "REPAIR_MARK"
    PUNCH_CLEAR = "PUNCH_CLEAR"
    SPOOL_ERECTION = "SPOOL_ERECTION"
    PHOTO = "PHOTO"


# ──────────────────────────────────────────────
#  FieldSyncService Implementation
# ──────────────────────────────────────────────

class FieldSyncService:
    """
    سرویس سرور برای دریافت امن، معتبر و مقاومت‌دربرابر-قطعی بسته‌های همگام‌سازی تبلت‌ها
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    # Implementation note.

    def ingest_batch(
        self,
        project_id: int,
        device_id: str,
        batch_uuid: str,
        events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        دریافت دسته‌ای رویدادهای آفلاین کلاینت، اعمال تغییرات روی جداول اصلی سرور،
        صدور رسیدهای ساختاریافته و تضمین صددرصدی Idempotency.
        """
        clean_device = str(device_id).strip().upper()
        clean_batch_uuid = str(batch_uuid).strip()

        with self.db.session_scope() as session:
            # Implementation note.
            batch = (
                session.query(FieldSyncBatch)
                .filter(FieldSyncBatch.batch_uuid == clean_batch_uuid)
                .first()
            )

            if batch and batch.status == "Completed":
                logger.info(f"Batch UUID '{clean_batch_uuid}' already processed. Returning cached receipts.")
                existing_receipts = (
                    session.query(FieldSyncReceipt)
                    .filter(FieldSyncReceipt.batch_id == batch.id)
                    .all()
                )
                return {
                    "batch_uuid": clean_batch_uuid,
                    "received": len(events),
                    "accepted": batch.accepted_count,
                    "rejected": batch.rejected_count,
                    "conflicts": batch.conflict_count,
                    "duplicates": getattr(batch, "duplicate_count", 0),
                    "receipts": [
                        {
                            "event_uuid": r.event_uuid,
                            "status": r.status,
                            "server_event_id": r.server_event_id,
                            "message": r.message,
                        }
                        for r in existing_receipts
                    ],
                }

            if not batch:
                batch = FieldSyncBatch(
                    project_id=project_id,
                    device_id=clean_device,
                    batch_uuid=clean_batch_uuid,
                    received_count=len(events),
                    status="Processing",
                    created_at=datetime.utcnow(),
                )
                session.add(batch)
                session.flush()

            accepted_count = 0
            rejected_count = 0
            conflict_count = 0
            duplicate_count = 0

            receipts_to_add = []

            for item in events:
                event_uuid = str(item.get("event_uuid") or "").strip()
                if not event_uuid:
                    rejected_count += 1
                    receipts_to_add.append(FieldSyncReceipt(
                        batch_id=batch.id,
                        event_uuid="UNKNOWN",
                        status=ReceiptStatus.REJECTED.value,
                        message="Missing mandatory 'event_uuid' field.",
                    ))
                    continue

                # Implementation note.
                existing_receipt = (
                    session.query(FieldSyncReceipt)
                    .filter(
                        FieldSyncReceipt.batch_id == batch.id,
                        FieldSyncReceipt.event_uuid == event_uuid,
                    )
                    .first()
                )
                if existing_receipt:
                    duplicate_count += 1
                    continue

                # Implementation note.
                global_existing_event = (
                    session.query(FieldSyncEvent)
                    .filter(FieldSyncEvent.event_uuid == event_uuid)
                    .first()
                )

                if global_existing_event:
                    # Implementation note.
                    if global_existing_event.sync_status == "Synced":
                        duplicate_count += 1
                        receipts_to_add.append(FieldSyncReceipt(
                            batch_id=batch.id,
                            event_uuid=event_uuid,
                            status=ReceiptStatus.DUPLICATE.value,
                            server_event_id=global_existing_event.id,
                            message="Event already processed successfully (Idempotent Retry).",
                        ))
                    else:
                        conflict_count += 1
                        receipts_to_add.append(FieldSyncReceipt(
                            batch_id=batch.id,
                            event_uuid=event_uuid,
                            status=ReceiptStatus.CONFLICT.value,
                            server_event_id=global_existing_event.id,
                            message="Event UUID exists with conflicting state.",
                        ))
                    continue

                # Implementation note.
                try:
                    event_type = item.get("event_type")
                    entity_type = str(item.get("entity_type", "")).strip().upper()
                    entity_id = item.get("entity_id")
                    payload = item.get("payload", {})

                    # Implementation note.
                    self._apply_server_side_mutation(
                        session=session,
                        project_id=project_id,
                        event_type=event_type,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        payload=payload,
                    )

                    # Implementation note.
                    sync_event = FieldSyncEvent(
                        project_id=project_id,
                        device_id=clean_device,
                        event_uuid=event_uuid,
                        event_type=event_type,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        payload_json=json.dumps(payload, default=str, ensure_ascii=False),
                        sync_status="Synced",
                        synced_at=datetime.utcnow(),
                    )
                    session.add(sync_event)
                    session.flush()

                    accepted_count += 1
                    receipts_to_add.append(FieldSyncReceipt(
                        batch_id=batch.id,
                        event_uuid=event_uuid,
                        status=ReceiptStatus.ACCEPTED.value,
                        server_event_id=sync_event.id,
                        message="Successfully accepted and applied to server model.",
                    ))

                except Exception as exc:
                    rejected_count += 1
                    logger.error(f"Failed to ingest field event {event_uuid}: {exc}")
                    receipts_to_add.append(FieldSyncReceipt(
                        batch_id=batch.id,
                        event_uuid=event_uuid,
                        status=ReceiptStatus.REJECTED.value,
                        message=f"Server mutation error: {str(exc)}",
                    ))

            if receipts_to_add:
                session.add_all(receipts_to_add)

            # Implementation note.
            batch.accepted_count = accepted_count
            batch.rejected_count = rejected_count
            batch.conflict_count = conflict_count
            if hasattr(batch, "duplicate_count"):
                batch.duplicate_count = duplicate_count
            batch.status = "Completed"
            batch.completed_at = datetime.utcnow()
            session.flush()

            all_receipts = (
                session.query(FieldSyncReceipt)
                .filter(FieldSyncReceipt.batch_id == batch.id)
                .all()
            )

            return {
                "batch_uuid": clean_batch_uuid,
                "received": len(events),
                "accepted": accepted_count,
                "rejected": rejected_count,
                "conflicts": conflict_count,
                "duplicates": duplicate_count,
                "receipts": [
                    {
                        "event_uuid": r.event_uuid,
                        "status": r.status,
                        "server_event_id": r.server_event_id,
                        "message": r.message,
                    }
                    for r in all_receipts
                ],
            }

    # Implementation note.

    def _apply_server_side_mutation(
        self,
        session: Session,
        project_id: int,
        event_type: str,
        entity_type: str,
        entity_id: Optional[int],
        payload: Dict[str, Any],
    ) -> None:
        """
        به‌روزرسانی قطعی و رسمی جداول اصلی دیتابیس سرور (مانند Weld, Spool, PunchItem)
        متناسب با رویداد ارسالی از تبلت بازرس.
        """
        if not entity_id:
            return

        now = datetime.utcnow()

        if entity_type == "WELD":
            weld = session.query(Weld).filter(Weld.id == entity_id, Weld.project_id == project_id).first()
            if not weld:
                return

            if event_type == EventType.FITUP.value:
                is_pass = payload.get("is_passed", True)
                weld.status = "FITUP_ACCEPTED" if is_pass else "FITUP_REJECTED"
                weld.fitup_inspector = payload.get("inspector_name")
                weld.fitup_date = now

            elif event_type == EventType.WELD.value:
                weld.status = "WELDED"
                weld.root_welder_id = payload.get("root_welder_stencil")
                weld.wps_number = payload.get("wps_number")
                weld.welding_date = now.date()

            elif event_type == EventType.VISUAL_QC.value:
                is_pass = payload.get("is_passed", True)
                weld.status = "VT_ACCEPTED" if is_pass else "VT_REJECTED"
                weld.vt_inspector = payload.get("inspector_name")
                weld.vt_date = now

            elif event_type == EventType.REPAIR_MARK.value:
                weld.status = "REPAIR_REQUIRED"
                weld.repair_count = (getattr(weld, "repair_count", 0) or 0) + 1
                weld.defect_description = f"{payload.get('defect_type')} at {payload.get('defect_location')}"

        elif entity_type == "SPOOL":
            spool = session.query(Spool).filter(Spool.id == entity_id, Spool.project_id == project_id).first()
            if spool and event_type == "SPOOL_ERECTION":
                spool.status = "ERECTED"
                spool.erection_date = now.date()

        elif entity_type == "PUNCH_ITEM":
            punch = session.query(PunchItem).filter(PunchItem.id == entity_id, PunchItem.project_id == project_id).first()
            if punch and event_type == EventType.PUNCH_CLEAR.value:
                punch.status = "QC_CLEARED"
                punch.cleared_by = payload.get("cleared_by")
                punch.cleared_date = now