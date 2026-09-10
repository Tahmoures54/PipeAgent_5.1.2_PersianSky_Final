# -*- coding: utf-8 -*-
"""
services/field_mobile_service.py – PipeAgent
سرویس جامع آفلاین-فرست عملیات کارگاهی و بازرسی‌های مبتنی بر بارکدهای دوبعدی (QR Codes)
شامل: ثبت بلادرنگ فیت‌آپ، جوش، NDT، عکس‌های بازرسی، حل تعارضات همزمانی (Conflict Resolution)،
اعمال محلی تغییرات وضعیت بر روی مدل‌های پایپینگ و همگام‌سازی چندمرحله‌ای با سرور مرکزی.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from db.manager import DatabaseManager
from db.models import (
    FieldSyncEvent,
    FieldAttachment,
    Weld,
    Spool,
    WorkFront,
    PunchItem,
    NDTRecord,
)

logger = logging.getLogger(__name__)

# Implementation note.
try:
    import qrcode
    from qrcode.image.styledpil import StyledPilImage
    _HAS_QRCODE = True
except ImportError:
    qrcode = None
    _HAS_QRCODE = False


# ──────────────────────────────────────────────
#  Enums & Event Definitions
# ──────────────────────────────────────────────

class FieldEventType(str, Enum):
    """انواع رویدادهای بازرسی و اجرایی در تبلت‌های کارگاهی"""
    FITUP_INSPECTION = "FITUP"                # Implementation note.
    WELD_RECORD = "WELD"                      # Implementation note.
    VISUAL_QC = "VISUAL_QC"                   # Implementation note.
    NDT_REQUEST = "NDT_REQUEST"              # Implementation note.
    REPAIR_MARK = "REPAIR_MARK"              # Implementation note.
    PUNCH_CLEAR = "PUNCH_CLEAR"              # Implementation note.
    SPOOL_ERECTION = "SPOOL_ERECTION"        # Implementation note.
    PHOTO_ATTACHMENT = "PHOTO"                # Implementation note.


class SyncStatus(str, Enum):
    """وضعیت‌های همگام‌سازی رویداد کارگاهی"""
    PENDING = "PENDING"                      # Implementation note.
    SYNCED = "SYNCED"                        # Implementation note.
    CONFLICT = "CONFLICT"                    # Implementation note.
    REJECTED = "REJECTED"                    # Implementation note.
    ERROR = "ERROR"                          # Implementation note.


class EntityType(str, Enum):
    WELD = "WELD"
    SPOOL = "SPOOL"
    WORK_FRONT = "WORK_FRONT"
    PUNCH_ITEM = "PUNCH_ITEM"
    LINE = "LINE"


# Implementation note.
EVENT_PAYLOAD_SCHEMAS: Dict[FieldEventType, List[str]] = {
    FieldEventType.FITUP_INSPECTION: ["is_passed", "inspector_name", "root_gap_mm", "hi_lo_mm"],
    FieldEventType.WELD_RECORD: ["root_welder_stencil", "wps_number", "welding_date", "process"],
    FieldEventType.VISUAL_QC: ["is_passed", "inspector_name", "report_number"],
    FieldEventType.NDT_REQUEST: ["ndt_method", "requested_by"],
    FieldEventType.REPAIR_MARK: ["defect_type", "defect_location", "repair_wps"],
    FieldEventType.PUNCH_CLEAR: ["cleared_by", "rectification_details"],
    FieldEventType.SPOOL_ERECTION: ["erected_by", "erection_date"],
}


# ──────────────────────────────────────────────
#  Field Mobile Service Implementation
# ──────────────────────────────────────────────

class FieldMobileService:
    """
    سرویس مرکزی تبلت‌های کارگاهی و همگام‌سازی آفلاین پایپینگ
    """

    QR_APP_SIGNATURE = "PipeAgent-Industrial-v2"
    CHUNK_SIZE = 1024 * 1024  # Implementation note.

    def __init__(self, db: DatabaseManager, device_id: str = "TABLET_FIELD_01"):
        self.db = db
        self.device_id = str(device_id).strip().upper()

    # Implementation note.

    @classmethod
    def make_qr_payload(
        cls,
        project_id: int,
        entity_type: Union[EntityType, str],
        entity_key: str,
        display_label: Optional[str] = None,
        security_checksum: bool = True,
    ) -> str:
        """
        تولید پی‌لود استاندارد، فشرده و دارای چک‌سام امنیتی برای چاپ روی لیبل‌های ضدآب شاپ و سایت
        """
        ent_val = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type).strip().upper()
        key_clean = str(entity_key).strip().upper()

        payload_dict = {
            "app": cls.QR_APP_SIGNATURE,
            "pid": project_id,
            "type": ent_val,
            "key": key_clean,
            "lbl": (display_label or key_clean)[:30],
            "ts": int(datetime.utcnow().timestamp()),
        }

        if security_checksum:
            # Implementation note.
            raw_signature = f"{cls.QR_APP_SIGNATURE}|{project_id}|{ent_val}|{key_clean}"
            payload_dict["crc"] = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()[:8]

        return json.dumps(payload_dict, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def parse_qr_payload(cls, raw_payload_string: str) -> Dict[str, Any]:
        """
        پارس، اعتبارسنجی امضا و استخراج مشخصات موجودیت از روی بارکد اسکن‌شده
        """
        if not raw_payload_string or not raw_payload_string.strip():
            raise ValueError("Empty QR code payload.")

        try:
            data = json.loads(raw_payload_string.strip())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Corrupted or invalid QR code format: {exc}")

        if data.get("app") != cls.QR_APP_SIGNATURE:
            raise ValueError(f"Unsupported QR signature: '{data.get('app')}'. Expected {cls.QR_APP_SIGNATURE}")

        # Implementation note.
        if "crc" in data:
            expected_sig = f"{cls.QR_APP_SIGNATURE}|{data['pid']}|{data['type']}|{data['key']}"
            computed_crc = hashlib.sha256(expected_sig.encode("utf-8")).hexdigest()[:8]
            if computed_crc != data["crc"]:
                raise ValueError("QR Security Checksum mismatch: Code is damaged, tampered or invalid!")

        return {
            "project_id": data["pid"],
            "entity_type": data["type"],
            "entity_key": data["key"],
            "display_label": data.get("lbl", data["key"]),
            "timestamp": datetime.fromtimestamp(data.get("ts", 0)),
        }

    def generate_qr_image(
        self,
        payload_string: str,
        output_path: Union[str, Path],
        add_human_readable_text: bool = True,
    ) -> str:
        """
        رندر تصویر بارکد QR با بالاترین سطح تصحیح خطا (Level H) و ذخیره بر روی دیسک
        """
        path_obj = Path(output_path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)

        if not _HAS_QRCODE or qrcode is None:
            # Implementation note.
            txt_path = path_obj.with_suffix(".txt")
            txt_path.write_text(payload_string, encoding="utf-8")
            logger.warning(f"qrcode library missing. Wrote fallback text payload to {txt_path}")
            return str(txt_path)

        qr = qrcode.QRCode(
            version=None,  # Implementation note.
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # Implementation note.
            box_size=10,
            border=4,
        )
        qr.add_data(payload_string)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        img.save(str(path_obj))
        logger.info(f"QR Code generated and saved to {path_obj}")
        return str(path_obj)

    # Implementation note.

    def capture_event(
        self,
        project_id: int,
        event_type: Union[FieldEventType, str],
        entity_type: Union[EntityType, str],
        entity_id: Optional[int],
        payload: Dict[str, Any],
        gps_coordinates: Optional[str] = None,
        operator_username: str = "field_operator",
    ) -> str:
        """
        ثبت رویداد در صف آفلاین تبلت و اعمال مستقیم تغییر وضعیت روی مدل‌های دیتابیس محلی (Local State Transition)
        """
        ev_type_enum = FieldEventType(event_type) if isinstance(event_type, str) else event_type
        ent_type_val = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type).strip().upper()

        # Implementation note.
        self._validate_event_payload(ev_type_enum, payload)

        event_uuid = str(uuid.uuid4())
        captured_time = datetime.utcnow()

        enriched_payload = dict(payload)
        enriched_payload.update({
            "captured_by_user": operator_username,
            "captured_at_device": captured_time.isoformat(),
            "gps_coordinates": gps_coordinates,
            "device_id": self.device_id,
        })

        with self.db.session_scope() as session:
            # Implementation note.
            sync_record = FieldSyncEvent(
                project_id=project_id,
                device_id=self.device_id,
                event_uuid=event_uuid,
                event_type=ev_type_enum.value,
                entity_type=ent_type_val,
                entity_id=entity_id,
                payload_json=json.dumps(enriched_payload, default=str, ensure_ascii=False),
                sync_status=SyncStatus.PENDING.value,
                created_at=captured_time,
            )
            session.add(sync_record)

            # Implementation note.
            # Implementation note.
            self._apply_event_locally(
                session=session,
                project_id=project_id,
                event_type=ev_type_enum,
                entity_type=ent_type_val,
                entity_id=entity_id,
                payload=enriched_payload,
            )

        logger.info(f"Field event '{ev_type_enum.value}' captured offline [UUID: {event_uuid[:8]}...] for {ent_type_val} #{entity_id}.")
        return event_uuid

    # Implementation note.

    def _apply_event_locally(
        self,
        session: Session,
        project_id: int,
        event_type: FieldEventType,
        entity_type: str,
        entity_id: Optional[int],
        payload: Dict[str, Any],
    ) -> None:
        """به‌روزرسانی جداول اصلی SQLite تبلت متناسب با رویداد ثبت‌شده"""
        now = datetime.utcnow()

        if entity_type == EntityType.WELD.value and entity_id:
            weld = session.query(Weld).filter(Weld.id == entity_id).first()
            if weld:
                if event_type == FieldEventType.FITUP_INSPECTION:
                    is_pass = payload.get("is_passed", True)
                    weld.status = "FITUP_ACCEPTED" if is_pass else "FITUP_REJECTED"
                    weld.fitup_inspector = payload.get("inspector_name")
                    weld.fitup_date = now

                elif event_type == FieldEventType.WELD_RECORD:
                    weld.status = "WELDED"
                    weld.root_welder_id = payload.get("root_welder_stencil")
                    weld.wps_number = payload.get("wps_number")
                    weld.welding_date = now.date()

                elif event_type == FieldEventType.VISUAL_QC:
                    is_pass = payload.get("is_passed", True)
                    weld.status = "VT_ACCEPTED" if is_pass else "VT_REJECTED"
                    weld.vt_inspector = payload.get("inspector_name")
                    weld.vt_date = now

                elif event_type == FieldEventType.REPAIR_MARK:
                    weld.status = "REPAIR_REQUIRED"
                    weld.repair_count = (getattr(weld, "repair_count", 0) or 0) + 1
                    weld.defect_description = f"{payload.get('defect_type')} at {payload.get('defect_location')}"

        elif entity_type == EntityType.SPOOL.value and entity_id:
            spool = session.query(Spool).filter(Spool.id == entity_id).first()
            if spool and event_type == FieldEventType.SPOOL_ERECTION:
                spool.status = "ERECTED"
                spool.erection_date = now.date()

        elif entity_type == EntityType.PUNCH_ITEM.value and entity_id:
            punch = session.query(PunchItem).filter(PunchItem.id == entity_id).first()
            if punch and event_type == FieldEventType.PUNCH_CLEAR:
                punch.status = "QC_CLEARED"
                punch.cleared_by = payload.get("cleared_by")
                punch.cleared_date = now

    # Implementation note.

    def attach_photo(
        self,
        project_id: int,
        entity_type: Union[EntityType, str],
        entity_id: int,
        file_path: Union[str, Path],
        caption: str = "",
        captured_by: str = "inspector",
        gps_coordinates: Optional[str] = None,
    ) -> int:
        """
        ثبت عکس کارگاهی با محاسبه جریانی اثر انگشت SHA-256 و علامت‌گذاری برای آپلود در سینک بعدی
        """
        path_obj = Path(file_path)
        if not path_obj.exists() or not path_obj.is_file():
            raise FileNotFoundError(f"Photo file not found: {file_path}")

        ent_type_val = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type).strip().upper()

        # Implementation note.
        hasher = hashlib.sha256()
        with open(path_obj, "rb") as f:
            while chunk := f.read(self.CHUNK_SIZE):
                hasher.update(chunk)
        digest = hasher.hexdigest()

        with self.db.session_scope() as session:
            attachment = FieldAttachment(
                project_id=project_id,
                entity_type=ent_type_val,
                entity_id=entity_id,
                file_path=str(path_obj.resolve()),
                caption=caption.strip(),
                captured_by=captured_by,
                sha256=digest,
                sync_status=SyncStatus.PENDING.value,
                created_at=datetime.utcnow(),
            )
            session.add(attachment)
            session.flush()

            logger.info(f"Field Photo attached: ID #{attachment.id} for {ent_type_val} #{entity_id} (SHA: {digest[:8]}...).")
            return attachment.id

    # Implementation note.

    def sync_to_enterprise_api(
        self,
        base_url: str,
        project_id: int,
        api_key: str,
        batch_uuid: Optional[str] = None,
        timeout: int = 35,
    ) -> Dict[str, Any]:
        """
        همگام‌سازی دوفازی با سرور مرکزی:
        فاز ۱: ارسال دسته‌ای رویدادهای JSON و دریافت رسیدها
        فاز ۲: آپلود جریانی عکس‌ها و فایل‌های باینری پیوست
        """
        import requests

        server_url = base_url.rstrip("/")
        batch_id = batch_uuid or str(uuid.uuid4())

        # Implementation note.
        with self.db.session_scope() as session:
            pending_events = (
                session.query(FieldSyncEvent)
                .filter(
                    FieldSyncEvent.project_id == project_id,
                    FieldSyncEvent.sync_status == SyncStatus.PENDING.value,
                )
                .order_by(FieldSyncEvent.id.asc())
                .limit(250)
                .all()
            )

            if not pending_events:
                return {"status": "SUCCESS", "message": "No pending events to synchronize.", "synced_events": 0}

            events_payload = [
                {
                    "event_uuid": e.event_uuid,
                    "event_type": e.event_type,
                    "entity_type": e.entity_type,
                    "entity_id": e.entity_id,
                    "payload": json.loads(e.payload_json or "{}"),
                }
                for e in pending_events
            ]

        # Implementation note.
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-PipeAgent-Device-ID": self.device_id,
        }

        try:
            response = requests.post(
                url=f"{server_url}/api/v1/sync/batch",
                json={
                    "project_id": project_id,
                    "device_id": self.device_id,
                    "batch_uuid": batch_id,
                    "events": events_payload,
                },
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            result_data = response.json()

            accepted_uuids: Set[str] = {
                r["event_uuid"] for r in result_data.get("receipts", []) if r.get("status") == "Accepted"
            }
            rejected_uuids: Set[str] = {
                r["event_uuid"] for r in result_data.get("receipts", []) if r.get("status") == "Rejected"
            }

            # Implementation note.
            with self.db.session_scope() as session:
                for ev in session.query(FieldSyncEvent).filter(
                    FieldSyncEvent.project_id == project_id,
                    FieldSyncEvent.sync_status == SyncStatus.PENDING.value,
                ).all():
                    if ev.event_uuid in accepted_uuids:
                        ev.sync_status = SyncStatus.SYNCED.value
                        ev.synced_at = datetime.utcnow()
                    elif ev.event_uuid in rejected_uuids:
                        ev.sync_status = SyncStatus.REJECTED.value

            # Implementation note.
            self._upload_pending_attachments(server_url, project_id, api_key, timeout)

            return {
                "status": "SUCCESS",
                "batch_uuid": batch_id,
                "total_submitted": len(events_payload),
                "accepted_count": len(accepted_uuids),
                "rejected_count": len(rejected_uuids),
                "server_receipts": result_data.get("receipts", []),
            }

        except requests.exceptions.RequestException as exc:
            error_msg = f"Transport sync failed: {exc}"
            logger.error(error_msg)
            return {"status": "FAILED", "error": error_msg, "pending_count": len(events_payload)}

    def _upload_pending_attachments(self, server_url: str, project_id: int, api_key: str, timeout: int) -> int:
        """آپلود جریانی عکس‌های بازرسی ذخیره‌شده روی تبلت به سرور مرکزی"""
        import requests

        uploaded_count = 0
        with self.db.session_scope() as session:
            pending_photos = (
                session.query(FieldAttachment)
                .filter(
                    FieldAttachment.project_id == project_id,
                    FieldAttachment.sync_status == SyncStatus.PENDING.value,
                )
                .limit(20)
                .all()
            )

            for photo in pending_photos:
                photo_path = Path(photo.file_path)
                if not photo_path.exists():
                    continue

                headers = {"Authorization": f"Bearer {api_key}"}
                try:
                    with open(photo_path, "rb") as f_data:
                        files = {"file": (photo_path.name, f_data, "image/jpeg")}
                        data = {
                            "project_id": project_id,
                            "entity_type": photo.entity_type,
                            "entity_id": photo.entity_id,
                            "caption": photo.caption,
                            "sha256": photo.sha256,
                        }
                        res = requests.post(f"{server_url}/api/v1/sync/attachments", headers=headers, data=data, files=files, timeout=timeout)
                        if res.status_code in [200, 201]:
                            photo.sync_status = SyncStatus.SYNCED.value
                            photo.synced_at = datetime.utcnow()
                            uploaded_count += 1
                except Exception as exc:
                    logger.warning(f"Failed to upload photo #{photo.id}: {exc}")

        return uploaded_count

    # Implementation note.

    def _validate_event_payload(self, event_type: FieldEventType, payload: Dict[str, Any]) -> None:
        """اعتبارسنجی وجود فیلدهای اجباری برای هر نوع رخداد کارگاهی"""
        required_fields = EVENT_PAYLOAD_SCHEMAS.get(event_type, [])
        missing_fields = [f for f in required_fields if f not in payload or payload[f] in (None, "")]
        if missing_fields:
            raise ValueError(f"Payload validation failed for '{event_type.value}'. Mandatory fields missing: {missing_fields}")