# -*- coding: utf-8 -*-
# repositories/finishing_repository.py

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from sqlalchemy import func, or_, and_, desc, asc
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from repositories.base import BaseRepository
from db.models import (
    PaintingRecord,
    InsulationRecord,
    FlangeTorqueRecord,
    PWHTRecord,
    ReinstatementItem,
)
from db.queries import finishing_queries as q

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  Type & Enum Definitions
# ──────────────────────────────────────────────

T = TypeVar("T")


class RecordStatus(str, Enum):
    """وضعیت عمومی رکوردهای Finishing"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"
    ON_HOLD = "on_hold"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class PaginationResult(Generic[T]):
    """نتیجه صفحه‌بندی شده"""
    def __init__(
        self,
        items: List[T],
        total: int,
        page: int,
        per_page: int,
    ):
        self.items = items
        self.total = total
        self.page = page
        self.per_page = per_page
        self.total_pages = (total + per_page - 1) // per_page if per_page else 1
        self.has_next = page < self.total_pages
        self.has_prev = page > 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "per_page": self.per_page,
            "total_pages": self.total_pages,
            "has_next": self.has_next,
            "has_prev": self.has_prev,
        }


# ──────────────────────────────────────────────
#  Extended Base Repository
# ──────────────────────────────────────────────

class ExtendedBaseRepository(BaseRepository, Generic[T]):
    """
    ریپازیتوری پایه توسعه‌یافته با عملیات CRUD کامل،
    صفحه‌بندی، جستجو و آمارگیری.
    """

    def __init__(self, session: Session, model: Type[T]):
        super().__init__(session, model)
        self._model = model

    # ── CRUD ──────────────────────────────────

    def get_by_id(self, record_id: int) -> Optional[T]:
        """دریافت رکورد بر اساس شناسه"""
        try:
            return (
                self.session.query(self._model)
                .filter(self._model.id == record_id)
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"Error fetching {self._model.__name__} #{record_id}: {e}")
            raise

    def get_by_ids(self, record_ids: List[int]) -> List[T]:
        """دریافت چند رکورد بر اساس لیست شناسه‌ها"""
        if not record_ids:
            return []
        return (
            self.session.query(self._model)
            .filter(self._model.id.in_(record_ids))
            .all()
        )

    def update_record(
        self,
        record_id: int,
        updated_by: str,
        **kwargs,
    ) -> Optional[T]:
        """به‌روزرسانی رکورد با شناسه مشخص"""
        try:
            record = self.get_by_id(record_id)
            if not record:
                logger.warning(
                    f"{self._model.__name__} #{record_id} not found for update."
                )
                return None

            for key, value in kwargs.items():
                if hasattr(record, key):
                    setattr(record, key, value)

            # Implementation note.
            if hasattr(record, "updated_by"):
                record.updated_by = updated_by
            if hasattr(record, "updated_at"):
                record.updated_at = datetime.utcnow()

            self.session.commit()
            self.session.refresh(record)
            logger.info(
                f"{self._model.__name__} #{record_id} updated by {updated_by}."
            )
            return record

        except IntegrityError as e:
            self.session.rollback()
            logger.error(f"Integrity error updating #{record_id}: {e}")
            raise
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"DB error updating #{record_id}: {e}")
            raise

    def delete_record(
        self,
        record_id: int,
        soft: bool = True,
        deleted_by: str = "system",
    ) -> bool:
        """
        حذف رکورد (نرم یا سخت).
        soft=True → فقط فیلد is_deleted فعال می‌شود.
        """
        try:
            record = self.get_by_id(record_id)
            if not record:
                return False

            if soft and hasattr(record, "is_deleted"):
                record.is_deleted = True
                if hasattr(record, "deleted_by"):
                    record.deleted_by = deleted_by
                if hasattr(record, "deleted_at"):
                    record.deleted_at = datetime.utcnow()
                self.session.commit()
                logger.info(
                    f"{self._model.__name__} #{record_id} soft-deleted."
                )
            else:
                self.session.delete(record)
                self.session.commit()
                logger.info(
                    f"{self._model.__name__} #{record_id} hard-deleted."
                )
            return True

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Error deleting #{record_id}: {e}")
            raise

    def bulk_create(
        self,
        records_data: List[Dict[str, Any]],
    ) -> List[T]:
        """ایجاد دسته‌ای رکوردها"""
        try:
            instances = [self._model(**data) for data in records_data]
            self.session.bulk_save_objects(instances, return_defaults=True)
            self.session.commit()
            logger.info(
                f"Bulk-created {len(instances)} {self._model.__name__} records."
            )
            return instances
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Bulk create error: {e}")
            raise

    def bulk_update_status(
        self,
        record_ids: List[int],
        status: RecordStatus,
        updated_by: str,
    ) -> int:
        """به‌روزرسانی دسته‌ای وضعیت رکوردها"""
        try:
            update_values: Dict[str, Any] = {"status": status.value}
            if hasattr(self._model, "updated_by"):
                update_values["updated_by"] = updated_by
            if hasattr(self._model, "updated_at"):
                update_values["updated_at"] = datetime.utcnow()

            count = (
                self.session.query(self._model)
                .filter(self._model.id.in_(record_ids))
                .update(update_values, synchronize_session="fetch")
            )
            self.session.commit()
            logger.info(
                f"Bulk-updated {count} {self._model.__name__} to {status}."
            )
            return count
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Bulk status update error: {e}")
            raise

    # ── Pagination ────────────────────────────

    def get_paginated(
        self,
        query_filters: Dict[str, Any],
        page: int = 1,
        per_page: int = 25,
        sort_field: str = "id",
        sort_order: SortOrder = SortOrder.DESC,
    ) -> PaginationResult[T]:
        """دریافت نتایج صفحه‌بندی‌شده با فیلتر و مرتب‌سازی"""
        try:
            base_query = self.session.query(self._model)

            # Implementation note.
            for field, value in query_filters.items():
                if value is not None and hasattr(self._model, field):
                    base_query = base_query.filter(
                        getattr(self._model, field) == value
                    )

            # Implementation note.
            if hasattr(self._model, "is_deleted"):
                base_query = base_query.filter(self._model.is_deleted == False)

            total = base_query.count()

            # Implementation note.
            sort_column = getattr(self._model, sort_field, self._model.id)
            order_func = asc if sort_order == SortOrder.ASC else desc
            base_query = base_query.order_by(order_func(sort_column))

            # Implementation note.
            items = (
                base_query
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )

            return PaginationResult(
                items=items,
                total=total,
                page=page,
                per_page=per_page,
            )
        except SQLAlchemyError as e:
            logger.error(f"Pagination error: {e}")
            raise

    # ── Statistics ────────────────────────────

    def get_statistics(
        self,
        project_id: int,
        group_by_field: str = "status",
    ) -> Dict[str, int]:
        """آمار رکوردها بر اساس فیلد گروه‌بندی"""
        try:
            group_column = getattr(self._model, group_by_field, None)
            if group_column is None:
                return {}

            results = (
                self.session.query(group_column, func.count(self._model.id))
                .filter(self._model.project_id == project_id)
                .group_by(group_column)
                .all()
            )
            return {str(k): v for k, v in results}
        except SQLAlchemyError as e:
            logger.error(f"Statistics error: {e}")
            raise

    def count_records(
        self,
        project_id: int,
        **filters,
    ) -> int:
        """شمارش رکوردها با فیلتر"""
        query = (
            self.session.query(func.count(self._model.id))
            .filter(self._model.project_id == project_id)
        )
        for field, value in filters.items():
            if value is not None and hasattr(self._model, field):
                query = query.filter(getattr(self._model, field) == value)
        return query.scalar() or 0


# ──────────────────────────────────────────────
#  Painting Repository
# ──────────────────────────────────────────────

class PaintingRepository(ExtendedBaseRepository[PaintingRecord]):
    """
    ریپازیتوری رنگ‌آمیزی (Painting/Coating).
    مدیریت سوابق آماده‌سازی سطح، پرایمر، لایه‌های میانی و نهایی.
    """

    def __init__(self, session: Session):
        super().__init__(session, PaintingRecord)

    # Implementation note.

    def get_all(
        self,
        project_id: int,
        line_number: Optional[str] = None,
    ) -> List[PaintingRecord]:
        return q.get_painting_records(self.session, project_id, line_number)

    def get_by_line_and_spool(
        self,
        project_id: int,
        line_number: str,
        spool_number: Optional[str] = None,
    ) -> List[PaintingRecord]:
        """دریافت سوابق رنگ بر اساس خط و اسپول"""
        query = (
            self.session.query(PaintingRecord)
            .filter(PaintingRecord.project_id == project_id)
            .filter(PaintingRecord.line_number == line_number)
        )
        if spool_number:
            query = query.filter(PaintingRecord.spool_number == spool_number)
        return query.order_by(desc(PaintingRecord.created_at)).all()

    def get_by_surface_prep_grade(
        self,
        project_id: int,
        grade: str,
    ) -> List[PaintingRecord]:
        """فیلتر بر اساس درجه آماده‌سازی سطح (مثلاً Sa 2.5)"""
        return (
            self.session.query(PaintingRecord)
            .filter(
                PaintingRecord.project_id == project_id,
                PaintingRecord.surface_prep_grade == grade,
            )
            .all()
        )

    def get_incomplete_coating(
        self,
        project_id: int,
    ) -> List[PaintingRecord]:
        """رکوردهایی که لایه نهایی هنوز اعمال نشده"""
        return (
            self.session.query(PaintingRecord)
            .filter(
                PaintingRecord.project_id == project_id,
                or_(
                    PaintingRecord.top_coat_date.is_(None),
                    PaintingRecord.top_coat_dft.is_(None),
                ),
            )
            .all()
        )

    # Implementation note.

    def add_record(self, **kwargs) -> PaintingRecord:
        return q.create_painting_record(self.session, **kwargs)

    def update_dft_readings(
        self,
        record_id: int,
        dft_readings: Dict[str, float],
        inspector: str,
    ) -> Optional[PaintingRecord]:
        """
        به‌روزرسانی مقادیر DFT (ضخامت فیلم خشک).
        dft_readings مثال: {"primer": 75.0, "mid": 125.0, "top": 50.0}
        """
        update_data = {"inspector_name": inspector}
        for coat, value in dft_readings.items():
            field = f"{coat}_coat_dft"
            if hasattr(PaintingRecord, field):
                update_data[field] = value
        return self.update_record(record_id, inspector, **update_data)

    def approve_painting(
        self,
        record_id: int,
        approved_by: str,
        comments: str = "",
    ) -> Optional[PaintingRecord]:
        """تأیید نهایی رنگ‌آمیزی"""
        return self.update_record(
            record_id,
            approved_by,
            status=RecordStatus.COMPLETED.value,
            approval_date=datetime.utcnow(),
            approval_comments=comments,
        )

    # Implementation note.

    def get_coating_statistics(
        self,
        project_id: int,
    ) -> Dict[str, Any]:
        """آمار جامع رنگ‌آمیزی پروژه"""
        total = self.count_records(project_id)
        completed = self.count_records(
            project_id, status=RecordStatus.COMPLETED.value
        )
        pending = self.count_records(
            project_id, status=RecordStatus.PENDING.value
        )
        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "progress_pct": round((completed / total * 100), 2) if total else 0,
        }


# ──────────────────────────────────────────────
#  Insulation Repository
# ──────────────────────────────────────────────

class InsulationRepository(ExtendedBaseRepository[InsulationRecord]):
    """
    ریپازیتوری عایق‌کاری (Insulation).
    مدیریت عایق حرارتی، برودتی و حفاظت شخصی.
    """

    def __init__(self, session: Session):
        super().__init__(session, InsulationRecord)

    # Implementation note.

    def get_all(
        self,
        project_id: int,
        line_number: Optional[str] = None,
    ) -> List[InsulationRecord]:
        return q.get_insulation_records(self.session, project_id, line_number)

    def get_by_insulation_type(
        self,
        project_id: int,
        insulation_type: str,
    ) -> List[InsulationRecord]:
        """فیلتر بر اساس نوع عایق (Hot/Cold/Personal Protection)"""
        return (
            self.session.query(InsulationRecord)
            .filter(
                InsulationRecord.project_id == project_id,
                InsulationRecord.insulation_type == insulation_type,
            )
            .all()
        )

    def get_by_thickness_range(
        self,
        project_id: int,
        min_thickness: float,
        max_thickness: float,
    ) -> List[InsulationRecord]:
        """فیلتر بر اساس بازه ضخامت عایق (میلی‌متر)"""
        return (
            self.session.query(InsulationRecord)
            .filter(
                InsulationRecord.project_id == project_id,
                InsulationRecord.thickness >= min_thickness,
                InsulationRecord.thickness <= max_thickness,
            )
            .all()
        )

    def get_missing_cladding(
        self,
        project_id: int,
    ) -> List[InsulationRecord]:
        """عایق‌هایی که هنوز روکش (Cladding) ندارند"""
        return (
            self.session.query(InsulationRecord)
            .filter(
                InsulationRecord.project_id == project_id,
                InsulationRecord.cladding_installed == False,
                InsulationRecord.status == RecordStatus.COMPLETED.value,
            )
            .all()
        )

    # Implementation note.

    def add_record(self, **kwargs) -> InsulationRecord:
        return q.create_insulation_record(self.session, **kwargs)

    def install_cladding(
        self,
        record_id: int,
        cladding_type: str,
        installed_by: str,
    ) -> Optional[InsulationRecord]:
        """ثبت نصب روکش عایق"""
        return self.update_record(
            record_id,
            installed_by,
            cladding_installed=True,
            cladding_type=cladding_type,
            cladding_date=datetime.utcnow(),
        )

    def record_heat_trace(
        self,
        record_id: int,
        heat_trace_type: str,
        circuit_number: str,
        installed_by: str,
    ) -> Optional[InsulationRecord]:
        """ثبت اطلاعات Heat Tracing همراه عایق"""
        return self.update_record(
            record_id,
            installed_by,
            heat_trace_type=heat_trace_type,
            heat_trace_circuit=circuit_number,
        )

    # Implementation note.

    def get_insulation_statistics(
        self,
        project_id: int,
    ) -> Dict[str, Any]:
        """آمار جامع عایق‌کاری"""
        total = self.count_records(project_id)
        by_type = self.get_statistics(project_id, "insulation_type")
        return {
            "total_records": total,
            "by_type": by_type,
            "completion_pct": round(
                self.count_records(
                    project_id, status=RecordStatus.COMPLETED.value
                )
                / total
                * 100,
                2,
            )
            if total
            else 0,
        }


# ──────────────────────────────────────────────
#  Flange Torque Repository
# ──────────────────────────────────────────────

class FlangeTorqueRepository(ExtendedBaseRepository[FlangeTorqueRecord]):
    """
    ریپازیتوری تورک فلنج (Flange Torque/Tensioning).
    مدیریت مقادیر گشتاور و کشش پیچ‌های فلنج.
    """

    def __init__(self, session: Session):
        super().__init__(session, FlangeTorqueRecord)

    # Implementation note.

    def get_all(
        self,
        project_id: int,
        line_number: Optional[str] = None,
    ) -> List[FlangeTorqueRecord]:
        return q.get_flange_torque_records(self.session, project_id, line_number)

    def get_by_flange_size(
        self,
        project_id: int,
        flange_size: str,
        flange_class: Optional[str] = None,
    ) -> List[FlangeTorqueRecord]:
        """فیلتر بر اساس سایز و کلاس فلنج"""
        query = (
            self.session.query(FlangeTorqueRecord)
            .filter(
                FlangeTorqueRecord.project_id == project_id,
                FlangeTorqueRecord.flange_size == flange_size,
            )
        )
        if flange_class:
            query = query.filter(FlangeTorqueRecord.flange_class == flange_class)
        return query.all()

    def get_by_torque_method(
        self,
        project_id: int,
        method: str,
    ) -> List[FlangeTorqueRecord]:
        """فیلتر بر اساس روش: torque / tensioning / hydraulic"""
        return (
            self.session.query(FlangeTorqueRecord)
            .filter(
                FlangeTorqueRecord.project_id == project_id,
                FlangeTorqueRecord.torque_method == method,
            )
            .all()
        )

    def get_unverified(
        self,
        project_id: int,
    ) -> List[FlangeTorqueRecord]:
        """فلنج‌های تورک‌شده ولی تأیید نشده"""
        return (
            self.session.query(FlangeTorqueRecord)
            .filter(
                FlangeTorqueRecord.project_id == project_id,
                FlangeTorqueRecord.verified_by.is_(None),
            )
            .all()
        )

    def get_re_torque_due(
        self,
        project_id: int,
    ) -> List[FlangeTorqueRecord]:
        """فلنج‌هایی که نیاز به تورک مجدد دارند"""
        return (
            self.session.query(FlangeTorqueRecord)
            .filter(
                FlangeTorqueRecord.project_id == project_id,
                FlangeTorqueRecord.re_torque_required == True,
                FlangeTorqueRecord.re_torque_completed == False,
            )
            .all()
        )

    # Implementation note.

    def add_record(self, **kwargs) -> FlangeTorqueRecord:
        return q.create_flange_torque_record(self.session, **kwargs)

    def verify_torque(
        self,
        record_id: int,
        verified_by: str,
        actual_torque_value: float,
        comments: str = "",
    ) -> Optional[FlangeTorqueRecord]:
        """تأیید مقدار تورک اعمال‌شده"""
        return self.update_record(
            record_id,
            verified_by,
            verified_by=verified_by,
            verification_date=datetime.utcnow(),
            actual_torque_value=actual_torque_value,
            verification_comments=comments,
            status=RecordStatus.COMPLETED.value,
        )

    def record_re_torque(
        self,
        record_id: int,
        new_torque_value: float,
        performed_by: str,
    ) -> Optional[FlangeTorqueRecord]:
        """ثبت تورک مجدد"""
        return self.update_record(
            record_id,
            performed_by,
            re_torque_completed=True,
            re_torque_date=datetime.utcnow(),
            re_torque_value=new_torque_value,
        )

    def apply_bolt_pattern(
        self,
        record_id: int,
        pattern: str,
        performed_by: str,
    ) -> Optional[FlangeTorqueRecord]:
        """
        ثبت الگوی سفت‌کردن پیچ‌ها
        pattern: "star", "circular", "modified_star"
        """
        return self.update_record(
            record_id,
            performed_by,
            bolt_tightening_pattern=pattern,
        )

    # Implementation note.

    def get_torque_statistics(
        self,
        project_id: int,
    ) -> Dict[str, Any]:
        """آمار جامع تورک فلنج"""
        total = self.count_records(project_id)
        verified = self.count_records(project_id)  # placeholder
        by_method = self.get_statistics(project_id, "torque_method")
        return {
            "total_flanges": total,
            "by_method": by_method,
            "unverified_count": len(self.get_unverified(project_id)),
            "re_torque_due": len(self.get_re_torque_due(project_id)),
        }


# ──────────────────────────────────────────────
#  PWHT Repository
# ──────────────────────────────────────────────

class PWHTRepository(ExtendedBaseRepository[PWHTRecord]):
    """
    ریپازیتوری عملیات حرارتی پس از جوش (PWHT).
    مدیریت چرخه‌های حرارتی، نمودارها و تأییدیه‌ها.
    """

    def __init__(self, session: Session):
        super().__init__(session, PWHTRecord)

    # Implementation note.

    def get_all(
        self,
        project_id: int,
        weld_id_fk: Optional[int] = None,
    ) -> List[PWHTRecord]:
        return q.get_pwht_records(self.session, project_id, weld_id_fk)

    def get_by_weld(
        self,
        project_id: int,
        weld_id: int,
    ) -> List[PWHTRecord]:
        """تمام چرخه‌های PWHT یک جوش خاص"""
        return (
            self.session.query(PWHTRecord)
            .filter(
                PWHTRecord.project_id == project_id,
                PWHTRecord.weld_id_fk == weld_id,
            )
            .order_by(desc(PWHTRecord.cycle_number))
            .all()
        )

    def get_by_temperature_range(
        self,
        project_id: int,
        min_temp: float,
        max_temp: float,
    ) -> List[PWHTRecord]:
        """فیلتر بر اساس دمای soaking"""
        return (
            self.session.query(PWHTRecord)
            .filter(
                PWHTRecord.project_id == project_id,
                PWHTRecord.soaking_temperature >= min_temp,
                PWHTRecord.soaking_temperature <= max_temp,
            )
            .all()
        )

    def get_failed_cycles(
        self,
        project_id: int,
    ) -> List[PWHTRecord]:
        """چرخه‌های ناموفق PWHT"""
        return (
            self.session.query(PWHTRecord)
            .filter(
                PWHTRecord.project_id == project_id,
                PWHTRecord.status == RecordStatus.REJECTED.value,
            )
            .all()
        )

    def get_by_furnace(
        self,
        project_id: int,
        furnace_id: str,
    ) -> List[PWHTRecord]:
        """سوابق PWHT یک کوره خاص"""
        return (
            self.session.query(PWHTRecord)
            .filter(
                PWHTRecord.project_id == project_id,
                PWHTRecord.furnace_id == furnace_id,
            )
            .all()
        )

    # Implementation note.

    def add_record(self, **kwargs) -> PWHTRecord:
        return q.create_pwht_record(self.session, **kwargs)

    def start_cycle(
        self,
        record_id: int,
        operator: str,
    ) -> Optional[PWHTRecord]:
        """شروع چرخه حرارتی"""
        return self.update_record(
            record_id,
            operator,
            status=RecordStatus.IN_PROGRESS.value,
            heating_start_time=datetime.utcnow(),
            operator_name=operator,
        )

    def complete_cycle(
        self,
        record_id: int,
        operator: str,
        soaking_temp: float,
        soaking_duration_hours: float,
        heating_rate: float,
        cooling_rate: float,
        chart_reference: str,
    ) -> Optional[PWHTRecord]:
        """تکمیل چرخه و ثبت پارامترهای اصلی"""
        return self.update_record(
            record_id,
            operator,
            status=RecordStatus.COMPLETED.value,
            soaking_temperature=soaking_temp,
            soaking_duration=soaking_duration_hours,
            heating_rate=heating_rate,
            cooling_rate=cooling_rate,
            cooling_end_time=datetime.utcnow(),
            chart_reference=chart_reference,
        )

    def reject_cycle(
        self,
        record_id: int,
        rejected_by: str,
        reason: str,
    ) -> Optional[PWHTRecord]:
        """رد چرخه PWHT به دلیل عدم انطباق"""
        return self.update_record(
            record_id,
            rejected_by,
            status=RecordStatus.REJECTED.value,
            rejection_reason=reason,
            rejection_date=datetime.utcnow(),
        )

    def attach_thermocouple_data(
        self,
        record_id: int,
        tc_data: Dict[str, Any],
        updated_by: str,
    ) -> Optional[PWHTRecord]:
        """
        ضمیمه داده‌های ترموکوپل.
        tc_data: {"tc_count": 4, "tc_positions": [...], "max_deviation": 12.5}
        """
        return self.update_record(
            record_id,
            updated_by,
            thermocouple_count=tc_data.get("tc_count"),
            max_temperature_deviation=tc_data.get("max_deviation"),
        )

    # Implementation note.

    def get_pwht_statistics(
        self,
        project_id: int,
    ) -> Dict[str, Any]:
        """آمار جامع PWHT"""
        total = self.count_records(project_id)
        completed = self.count_records(
            project_id, status=RecordStatus.COMPLETED.value
        )
        failed = self.count_records(
            project_id, status=RecordStatus.REJECTED.value
        )
        return {
            "total_cycles": total,
            "completed": completed,
            "failed": failed,
            "success_rate_pct": round(
                (completed / total * 100), 2
            )
            if total
            else 0,
            "failed_cycles_detail": self.get_failed_cycles(project_id),
        }


# ──────────────────────────────────────────────
#  Reinstatement Repository
# ──────────────────────────────────────────────

class ReinstatementRepository(ExtendedBaseRepository[ReinstatementItem]):
    """
    ریپازیتوری بازسازی (Reinstatement).
    مدیریت آیتم‌های بازسازی پس از تست فشار/نشتی.
    """

    def __init__(self, session: Session):
        super().__init__(session, ReinstatementItem)

    # Implementation note.

    def get_all(
        self,
        project_id: int,
        test_package_id: Optional[int] = None,
    ) -> List[ReinstatementItem]:
        return q.get_reinstatement_items(
            self.session, project_id, test_package_id
        )

    def get_by_test_package(
        self,
        project_id: int,
        test_package_id: int,
    ) -> List[ReinstatementItem]:
        """آیتم‌های بازسازی یک Test Package"""
        return (
            self.session.query(ReinstatementItem)
            .filter(
                ReinstatementItem.project_id == project_id,
                ReinstatementItem.test_package_id == test_package_id,
            )
            .order_by(ReinstatementItem.priority.desc())
            .all()
        )

    def get_pending_items(
        self,
        project_id: int,
        test_package_id: Optional[int] = None,
    ) -> List[ReinstatementItem]:
        """آیتم‌های بازسازی‌نشده"""
        query = (
            self.session.query(ReinstatementItem)
            .filter(
                ReinstatementItem.project_id == project_id,
                ReinstatementItem.status != RecordStatus.COMPLETED.value,
            )
        )
        if test_package_id:
            query = query.filter(
                ReinstatementItem.test_package_id == test_package_id
            )
        return query.all()

    def get_overdue_items(
        self,
        project_id: int,
        deadline: Optional[datetime] = None,
    ) -> List[ReinstatementItem]:
        """آیتم‌های عقب‌افتاده از مهلت"""
        if deadline is None:
            deadline = datetime.utcnow()
        return (
            self.session.query(ReinstatementItem)
            .filter(
                ReinstatementItem.project_id == project_id,
                ReinstatementItem.status != RecordStatus.COMPLETED.value,
                ReinstatementItem.deadline < deadline,
            )
            .all()
        )

    def get_by_category(
        self,
        project_id: int,
        category: str,
    ) -> List[ReinstatementItem]:
        """
        فیلتر بر اساس دسته‌بندی:
        "blind_removal", "valve_reinstall", "gasket_replacement",
        "instrument_reinstall", "support_adjustment"
        """
        return (
            self.session.query(ReinstatementItem)
            .filter(
                ReinstatementItem.project_id == project_id,
                ReinstatementItem.category == category,
            )
            .all()
        )

    # Implementation note.

    def add_item(self, **kwargs) -> ReinstatementItem:
        return q.create_reinstatement_item(self.session, **kwargs)

    def complete_item(
        self,
        item_id: int,
        verified_by: str,
    ) -> Optional[ReinstatementItem]:
        """تکمیل و تأیید یک آیتم بازسازی"""
        return self.update_record(
            item_id,
            verified_by,
            status=RecordStatus.COMPLETED.value,
            verified_by=verified_by,
            completion_date=datetime.utcnow(),
        )

    def bulk_complete_items(
        self,
        item_ids: List[int],
        verified_by: str,
    ) -> int:
        """تکمیل دسته‌ای آیتم‌های بازسازی"""
        return self.bulk_update_status(
            item_ids, RecordStatus.COMPLETED, verified_by
        )

    def reject_item(
        self,
        item_id: int,
        rejected_by: str,
        reason: str,
    ) -> Optional[ReinstatementItem]:
        """رد آیتم بازسازی (نیاز به انجام مجدد)"""
        return self.update_record(
            item_id,
            rejected_by,
            status=RecordStatus.REJECTED.value,
            rejection_reason=reason,
            rejection_date=datetime.utcnow(),
        )

    def assign_item(
        self,
        item_id: int,
        assigned_to: str,
        assigned_by: str,
        deadline: Optional[datetime] = None,
    ) -> Optional[ReinstatementItem]:
        """تخصیص آیتم به شخص/تیم"""
        update_data = {
            "assigned_to": assigned_to,
            "status": RecordStatus.IN_PROGRESS.value,
        }
        if deadline:
            update_data["deadline"] = deadline
        return self.update_record(item_id, assigned_by, **update_data)

    # Implementation note.

    def get_reinstatement_statistics(
        self,
        project_id: int,
        test_package_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """آمار جامع بازسازی"""
        filters = {"project_id": project_id}
        if test_package_id:
            filters["test_package_id"] = test_package_id

        total = self.count_records(project_id, **filters)
        completed = self.count_records(
            project_id, status=RecordStatus.COMPLETED.value, **filters
        )
        by_category = self.get_statistics(project_id, "category")
        overdue = len(self.get_overdue_items(project_id))

        return {
            "total_items": total,
            "completed": completed,
            "pending": total - completed,
            "overdue": overdue,
            "completion_pct": round(
                (completed / total * 100), 2
            )
            if total
            else 0,
            "by_category": by_category,
        }

    def get_test_package_readiness(
        self,
        project_id: int,
        test_package_id: int,
    ) -> Dict[str, Any]:
        """بررسی آمادگی Test Package برای تحویل"""
        items = self.get_by_test_package(project_id, test_package_id)
        total = len(items)
        completed = sum(
            1
            for i in items
            if i.status == RecordStatus.COMPLETED.value
        )
        return {
            "test_package_id": test_package_id,
            "total_items": total,
            "completed_items": completed,
            "is_ready": total > 0 and completed == total,
            "remaining": total - completed,
        }


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────

class FinishingUnitOfWork:
    """
    الگوی Unit of Work برای مدیریت تراکنش‌های
    چند ریپازیتوری در یک عملیات واحد.
    """

    def __init__(self, session: Session):
        self.session = session
        self.painting = PaintingRepository(session)
        self.insulation = InsulationRepository(session)
        self.flange_torque = FlangeTorqueRepository(session)
        self.pwht = PWHTRepository(session)
        self.reinstatement = ReinstatementRepository(session)

    def commit(self) -> None:
        """ثبت تغییرات"""
        try:
            self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"UnitOfWork commit failed: {e}")
            raise

    def rollback(self) -> None:
        """بازگشت تغییرات"""
        self.session.rollback()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()