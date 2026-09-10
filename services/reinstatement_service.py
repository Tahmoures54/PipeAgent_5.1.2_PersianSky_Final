# -*- coding: utf-8 -*-
"""
services/reinstatement_service.py – PipeAgent
سرویس جامع مدیریت بازگردانی مدار پس از هیدروتست (Piping Reinstatement Governance)
شامل: ردیابی خروج صفحات مسدودکننده (Blind Pulling Guard)، تعویض گسکت‌های دائم،
نصب مجدد شیرآلات کنترلی و این‌لاین، تاییدیه ترکمتر فلنج‌ها و صدور مجوز تکمیل مکانیکی (MC).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc, case
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from core.exceptions import AppError
from repositories.finishing_repository import ReinstatementRepository
from db.models import (
    ReinstatementItem,
    TestPackage,
    LineListItem,
    FlangeTorqueRecord,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Engineering Definitions
# ──────────────────────────────────────────────

class ReinstatementCategory(str, Enum):
    """دسته‌بندی‌های استاندارد اقلام بازگردانی مدار طبق ASME B31.3"""
    BLIND_REMOVAL = "BLIND_REMOVAL"            # Implementation note.
    SPECTACLE_BLIND_ROTATE = "SP_BLIND_ROTATE" # Implementation note.
    GASKET_REPLACEMENT = "GASKET_REPLACE"      # Implementation note.
    VALVE_REINSTALLATION = "VALVE_REINSTALL"  # Implementation note.
    INSTRUMENT_HOOKUP = "INSTRUMENT_HOOKUP"    # Implementation note.
    STRAINER_CLEANING = "STRAINER_CLEANING"    # Implementation note.
    SUPPORT_SPRING_UNLOCK = "SPRING_UNLOCK"    # Implementation note.
    BOLT_FINAL_TORQUE = "FINAL_TORQUE"        # Implementation note.


class ReinstatementStatus(str, Enum):
    """وضعیت‌های فرآیندی آیتم بازگردانی"""
    PENDING = "PENDING"                        # Implementation note.
    IN_PROGRESS = "IN_PROGRESS"                # Implementation note.
    RECTIFIED_FIELD = "RECTIFIED_FIELD"        # Implementation note.
    COMPLETED = "COMPLETED"                    # Implementation note.
    REJECTED = "REJECTED"                      # Implementation note.


class ItemPriority(str, Enum):
    CRITICAL_SAFETY = "CRITICAL"  # Implementation note.
    HIGH = "HIGH"                 # Implementation note.
    NORMAL = "NORMAL"             # Implementation note.


# ──────────────────────────────────────────────
#  Custom Exceptions
# ──────────────────────────────────────────────

class ReinstatementGatekeeperError(AppError):
    """خطای مسدود بودن تحویل مکانیکی به دلیل بازماندن اقلام بازگردانی"""
    pass


class BlindSafetyError(AppError):
    """خطای بحرانی ایمنی ناشی از عدم خروج بلایندهای تست"""
    pass


# ──────────────────────────────────────────────
#  Reinstatement Service Implementation
# ──────────────────────────────────────────────

class ReinstatementService:
    """
    سرویس مرکزی مدیریت، اعتبارسنجی و ممیزی فرآیندهای بازگردانی مدارک و خطوط پایپینگ
    """

    def __init__(self, session: Session):
        self.session = session
        self.repo = ReinstatementRepository(session)

    # Implementation note.

    def add_item(
        self,
        project_id: int,
        test_package_id: int,
        line_number: str,
        category: Union[ReinstatementCategory, str],
        description: str,
        *,
        location_tag: str = "",
        gasket_spec_verified: bool = False,
        flow_direction_verified: bool = False,
        priority: Union[ItemPriority, str] = ItemPriority.NORMAL,
        assigned_to: Optional[str] = None,
        target_closure_date: Optional[date] = None,
    ) -> ReinstatementItem:
        """
        ثبت آیتم چک‌لیست بازگردانی با اعمال دسته‌بندی و اولویت‌های مهندسی
        """
        cat_val = category.value if isinstance(category, ReinstatementCategory) else str(category).strip().upper()
        prio_val = priority.value if isinstance(priority, ItemPriority) else str(priority).strip().upper()
        line_clean = line_number.strip().upper()

        # Implementation note.
        if cat_val in [ReinstatementCategory.BLIND_REMOVAL.value, ReinstatementCategory.VALVE_REINSTALLATION.value]:
            prio_val = ItemPriority.CRITICAL_SAFETY.value

        item = self.repo.add_item(
            project_id=project_id,
            test_package_id=test_package_id,
            line_number=line_clean,
            category=cat_val,
            item_description=description.strip(),
            location_tag=location_tag.strip().upper() if location_tag else None,
            priority=prio_val,
            gasket_verified=gasket_spec_verified,
            flow_direction_verified=flow_direction_verified,
            status=ReinstatementStatus.PENDING.value,
            assigned_to=assigned_to.strip() if assigned_to else None,
            target_date=target_closure_date,
            created_at=datetime.utcnow(),
        )
        self.session.commit()

        logger.info(
            f"Reinstatement item registered: ID #{item.id} [{cat_val}] on Line '{line_clean}' "
            f"(Test Package #{test_package_id})."
        )
        return item

    # Implementation note.

    def auto_generate_reinstatement_checklist(
        self,
        project_id: int,
        test_package_id: int,
        generated_by: str = "system",
    ) -> List[ReinstatementItem]:
        """
        استخراج و تولید هوشمند چک‌لیست استاندارد بازگردانی بر مبنای پکیج تست هیدرواستاتیک:
        ۱. ایجاد آیتم‌های خروج تمام بلایندهای موقت تست
        ۲. ایجاد آیتم تعویض واشرهای موقت
        ۳. ایجاد آیتم نصب مجدد اینترنال شیرهای یکطرفه و ادوات کنترلی
        ۴. ایجاد آیتم تنظیم و آزادسازی ساپورت‌های فنری
        """
        tp = self.session.get(TestPackage, test_package_id)
        if not tp:
            raise AppError(f"TestPackage #{test_package_id} not found.")

        lines_raw = (getattr(tp, "line_numbers", "") or "").replace(";", ",")
        package_lines = [l.strip().upper() for l in lines_raw.split(",") if l.strip()]

        created_items = []

        for line_no in package_lines:
            # Implementation note.
            item_blind = ReinstatementItem(
                project_id=project_id,
                test_package_id=test_package_id,
                line_number=line_no,
                category=ReinstatementCategory.BLIND_REMOVAL.value,
                item_description=f"Remove all temporary test spades/blinds and verify open bore on line {line_no}.",
                priority=ItemPriority.CRITICAL_SAFETY.value,
                status=ReinstatementStatus.PENDING.value,
                created_at=datetime.utcnow(),
            )
            created_items.append(item_blind)

            # Implementation note.
            item_gasket = ReinstatementItem(
                project_id=project_id,
                test_package_id=test_package_id,
                line_number=line_no,
                category=ReinstatementCategory.GASKET_REPLACEMENT.value,
                item_description=f"Replace all temporary test gaskets with new approved permanent service gaskets on line {line_no}.",
                priority=ItemPriority.HIGH.value,
                status=ReinstatementStatus.PENDING.value,
                created_at=datetime.utcnow(),
            )
            created_items.append(item_gasket)

            # Implementation note.
            item_valves = ReinstatementItem(
                project_id=project_id,
                test_package_id=test_package_id,
                line_number=line_no,
                category=ReinstatementCategory.VALVE_REINSTALLATION.value,
                item_description=f"Reinstall control valves, PSVs, check valve flappers and orifice plates on line {line_no}.",
                priority=ItemPriority.HIGH.value,
                status=ReinstatementStatus.PENDING.value,
                created_at=datetime.utcnow(),
            )
            created_items.append(item_valves)

        if created_items:
            self.session.add_all(created_items)
            self.session.commit()

        logger.info(f"Auto-generated {len(created_items)} standard reinstatement items for TestPackage #{test_package_id}.")
        return created_items

    # Implementation note.

    def verify_and_complete_item(
        self,
        item_id: int,
        verified_by_qc: str,
        *,
        client_witness: Optional[str] = None,
        gasket_type_confirmed: bool = True,
        flow_direction_confirmed: bool = True,
        torque_report_ref: Optional[str] = None,
        verification_remarks: str = "",
    ) -> ReinstatementItem:
        """
        تکمیل و تایید رسمی آیتم بازگردانی با تاییدیه دوگانه بازرس QC و نماینده کارفرما
        همراه با تایید فنی واشر، جهت جریان و شماره صورتجلسه ترکمتر.
        """
        item = self.session.get(ReinstatementItem, item_id)
        if not item:
            raise AppError(f"Reinstatement item #{item_id} not found.")

        # Implementation note.
        if item.category == ReinstatementCategory.GASKET_REPLACEMENT.value and not gasket_type_confirmed:
            raise AppError(f"Cannot complete Item #{item_id}: Permanent gasket specification is not confirmed!")

        if item.category == ReinstatementCategory.VALVE_REINSTALLATION.value and not flow_direction_confirmed:
            raise AppError(f"Cannot complete Item #{item_id}: Valve/Inline instrument flow direction is not verified!")

        item.status = ReinstatementStatus.COMPLETED.value
        item.verified_by = verified_by_qc.strip()
        item.client_witness = client_witness.strip() if client_witness else None
        item.gasket_verified = gasket_type_confirmed
        item.flow_direction_verified = flow_direction_confirmed
        item.torque_report_number = torque_report_ref.strip() if torque_report_ref else None
        item.completion_date = datetime.utcnow()
        item.remarks = verification_remarks.strip()

        self.session.commit()
        self.session.refresh(item)

        logger.info(
            f"Reinstatement Item #{item_id} [{item.category}] COMPLETED by QC: {verified_by_qc} "
            f"(Client: {client_witness or 'N/A'})."
        )
        return item

    def bulk_complete_items(
        self,
        item_ids: List[int],
        verified_by_qc: str,
        client_witness: Optional[str] = None,
    ) -> Dict[str, Any]:
        """تکمیل و ترخیص دسته‌ای آیتم‌های بازگردانی پس از واک‌ثرو مشترک"""
        if not item_ids:
            return {"updated_count": 0}

        now = datetime.utcnow()
        updated_count = (
            self.session.query(ReinstatementItem)
            .filter(
                ReinstatementItem.id.in_(item_ids),
                ReinstatementItem.status != ReinstatementStatus.COMPLETED.value,
            )
            .update(
                {
                    "status": ReinstatementStatus.COMPLETED.value,
                    "verified_by": verified_by_qc.strip(),
                    "client_witness": client_witness.strip() if client_witness else None,
                    "completion_date": now,
                    "gasket_verified": True,
                    "flow_direction_verified": True,
                },
                synchronize_session="fetch",
            )
        )
        self.session.commit()

        logger.info(f"Bulk completed {updated_count} reinstatement items by QC {verified_by_qc}.")
        return {"requested": len(item_ids), "completed": updated_count}

    # Implementation note.

    def verify_package_reinstatement_clearance(
        self,
        project_id: int,
        test_package_id: int,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        ارزیابی بدون‌اغماض و سخت‌گیرانه اتمام بازگردانی مدار جهت صدور تاییدیه تکمیل مکانیکی (MC Clearance):
        ۱. صفر بودن مطلق بلایندهای بازمانده در خط (Blind Removal = 100%)
        ۲. تکمیل ۱۰۰٪ تعویض گسکت‌ها و نصب مجدد ادوات این‌لاین
        """
        blockers: List[str] = []

        # Implementation note.
        pending_blinds = (
            self.session.query(ReinstatementItem)
            .filter(
                ReinstatementItem.project_id == project_id,
                ReinstatementItem.test_package_id == test_package_id,
                ReinstatementItem.category.in_([
                    ReinstatementCategory.BLIND_REMOVAL.value,
                    ReinstatementCategory.SPECTACLE_BLIND_ROTATE.value,
                ]),
                ReinstatementItem.status != ReinstatementStatus.COMPLETED.value,
            )
            .all()
        )

        if pending_blinds:
            for pb in pending_blinds:
                blockers.append(
                    f"CRITICAL SAFETY: Test Blind on Line '{pb.line_number}' (Tag: {pb.location_tag or 'N/A'}) is still PENDING removal!"
                )

        # Implementation note.
        all_pending_items = (
            self.session.query(ReinstatementItem)
            .filter(
                ReinstatementItem.project_id == project_id,
                ReinstatementItem.test_package_id == test_package_id,
                ReinstatementItem.status != ReinstatementStatus.COMPLETED.value,
            )
            .all()
        )

        if all_pending_items and not pending_blinds:
            blockers.append(f"{len(all_pending_items)} non-blind reinstatement item(s) are still pending completion.")

        is_cleared = len(blockers) == 0

        summary = self.get_completion_status(project_id, test_package_id)

        details = {
            "test_package_id": test_package_id,
            "is_reinstatement_fully_cleared": is_cleared,
            "critical_blinds_pending_count": len(pending_blinds),
            "total_pending_items_count": len(all_pending_items),
            "summary_metrics": summary,
            "blocking_reasons": blockers,
        }

        return is_cleared, blockers, details

    # Implementation note.

    def get_completion_status(self, project_id: int, test_package_id: int) -> Dict[str, Any]:
        """
        محاسبه وضعیت پیشرفت بازگردانی با اجرای کوئری تجمعی در دیتابیس (بدون لود دیتا در RAM)
        """
        stats = (
            self.session.query(
                func.count(ReinstatementItem.id).label("total"),
                func.sum(case((ReinstatementItem.status == ReinstatementStatus.COMPLETED.value, 1), else_=0)).label("completed"),
                func.sum(case((and_(ReinstatementItem.category == ReinstatementCategory.BLIND_REMOVAL.value, ReinstatementItem.status == ReinstatementStatus.COMPLETED.value), 1), else_=0)).label("blinds_removed"),
                func.sum(case((and_(ReinstatementItem.category == ReinstatementCategory.BLIND_REMOVAL.value, ReinstatementItem.status != ReinstatementStatus.COMPLETED.value), 1), else_=0)).label("blinds_pending"),
            )
            .filter(
                ReinstatementItem.project_id == project_id,
                ReinstatementItem.test_package_id == test_package_id,
            )
            .first()
        )

        total = stats.total or 0
        done = stats.completed or 0
        pending = total - done
        pct = round((done / total * 100), 1) if total > 0 else 100.0

        return {
            "test_package_id": test_package_id,
            "total": total,
            "completed": done,
            "pending": pending,
            "completion_percentage": pct,
            "blinds_removed_count": stats.blinds_removed or 0,
            "blinds_pending_count": stats.blinds_pending or 0,
            "is_ready_for_turnover": total > 0 and pending == 0,
        }

    def get_project_reinstatement_dashboard(self, project_id: int) -> Dict[str, Any]:
        """
        محاسبه داشبورد کلان بازگردانی کل پروژه به تفکیک دسته‌بندی اقلام مهندسی
        """
        overall_stats = (
            self.session.query(
                func.count(ReinstatementItem.id).label("total"),
                func.sum(case((ReinstatementItem.status == ReinstatementStatus.COMPLETED.value, 1), else_=0)).label("completed"),
            )
            .filter(ReinstatementItem.project_id == project_id)
            .first()
        )

        by_category = (
            self.session.query(
                ReinstatementItem.category,
                func.count(ReinstatementItem.id).label("total"),
                func.sum(case((ReinstatementItem.status == ReinstatementStatus.COMPLETED.value, 1), else_=0)).label("completed"),
            )
            .filter(ReinstatementItem.project_id == project_id)
            .group_by(ReinstatementItem.category)
            .all()
        )

        total = overall_stats.total or 0
        completed = overall_stats.completed or 0

        return {
            "project_id": project_id,
            "timestamp": datetime.utcnow().isoformat(),
            "overall_metrics": {
                "total_items": total,
                "completed_items": completed,
                "pending_items": total - completed,
                "overall_progress_pct": round((completed / total * 100), 2) if total > 0 else 0.0,
            },
            "category_breakdown": {
                row.category: {
                    "total": row.total,
                    "completed": row.completed or 0,
                    "pending": row.total - (row.completed or 0),
                    "progress_pct": round(((row.completed or 0) / row.total * 100), 1) if row.total > 0 else 0.0,
                }
                for row in by_category
            },
        }

    def get_checklist(self, project_id: int, test_package_id: int) -> List[ReinstatementItem]:
        """بازیابی لیست چک‌لیست بازگردانی یک پکیج تست با مرتب‌سازی اولویت"""
        return (
            self.session.query(ReinstatementItem)
            .filter(
                ReinstatementItem.project_id == project_id,
                ReinstatementItem.test_package_id == test_package_id,
            )
            .order_by(
                ReinstatementItem.priority.asc(),
                ReinstatementItem.line_number.asc(),
                ReinstatementItem.id.asc(),
            )
            .all()
        )