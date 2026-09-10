# -*- coding: utf-8 -*-
"""
repositories/spool_repository.py – PipeAgent v5.1
=================================================
مدیریت جامع اسپول‌های پایپینگ (Piping Spools)
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError

from db.models import Spool, Weld, PaintingRecord, TestPackage
WeldJoint = Weld  # Implementation note.

from repositories.base import BaseRepository
from db.manager import DatabaseManager

logger = logging.getLogger(__name__)


class SpoolStatus(str, Enum):
    DESIGN = "DESIGN"
    MATERIAL_ALLOCATED = "MATERIAL_ALLOCATED"
    CUTTING_FITUP = "CUTTING_FITUP"
    WELDING = "WELDING"
    FABRICATION_COMPLETED = "FAB_COMPLETED"
    NDT_CLEARED = "NDT_CLEARED"
    PWHT_COMPLETED = "PWHT_COMPLETED"
    PAINTING = "PAINTING"
    READY_TO_DISPATCH = "READY_TO_DISPATCH"
    IN_TRANSIT = "IN_TRANSIT"
    SITE_LAYDOWN = "SITE_LAYDOWN"
    ERECTED = "ERECTED"
    TESTED_PUNCHED = "TESTED"


class SpoolLocation(str, Enum):
    MAIN_FAB_SHOP = "FAB_SHOP"
    PAINTING_YARD = "PAINTING_YARD"
    MARSHALLING_YARD = "MARSHALLING_YARD"
    SITE_AREA = "SITE_AREA"
    INSTALLED_ON_LINE = "INSTALLED"


class SpoolRepository(BaseRepository[Spool]):
    """
    ریپازیتوری پیشرفته مدیریت پیش‌ساخت و نصب اسپول‌های پایپینگ
    """

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, Spool)

    def get_by_spool_number(
        self,
        project_id: int,
        spool_number: str,
        drawing_number: Optional[str] = None,
        load_welds: bool = False,
    ) -> Optional[Spool]:
        with self._session() as session:
            query = session.query(Spool).filter(
                Spool.project_id == project_id,
                func.upper(Spool.spool_number) == spool_number.strip().upper(),
            )
            return query.first()

    def search_spools(
        self,
        project_id: int,
        line_number: Optional[str] = None,
        drawing_number: Optional[str] = None,
        status: Optional[Union[SpoolStatus, str]] = None,
        location: Optional[Union[SpoolLocation, str]] = None,
        test_package_id: Optional[int] = None,
        is_on_hold: Optional[bool] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[List[Spool], int]:
        with self._session() as session:
            query = session.query(Spool).filter(Spool.project_id == project_id)

            if line_number:
                query = query.filter(Spool.line_number.ilike(f"%{line_number.strip()}%"))

            if status:
                stat_val = status.value if isinstance(status, SpoolStatus) else status
                query = query.filter(Spool.status == stat_val)

            total = query.count()
            items = (
                query.order_by(Spool.line_number.asc(), Spool.spool_number.asc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            return items, total

    def get_by_line(self, project_id: int, line_number: str) -> List[Spool]:
        with self._session() as session:
            return (
                session.query(Spool)
                .filter(
                    Spool.project_id == project_id,
                    Spool.line_number == line_number.strip(),
                )
                .order_by(Spool.spool_number.asc())
                .all()
            )

    def get_by_status(
        self, project_id: int, status: Union[SpoolStatus, str]
    ) -> List[Spool]:
        stat_val = status.value if isinstance(status, SpoolStatus) else status
        with self._session() as session:
            return (
                session.query(Spool)
                .filter(
                    Spool.project_id == project_id,
                    Spool.status == stat_val,
                )
                .all()
            )

    def update_status(
        self,
        spool_id: int,
        new_status: Union[SpoolStatus, str],
        updated_by: str,
        location: Optional[Union[SpoolLocation, str]] = None,
        remarks: str = "",
    ) -> Optional[Spool]:
        stat_val = new_status.value if isinstance(new_status, SpoolStatus) else new_status
        with self._session() as session:
            try:
                spool = session.query(Spool).filter(Spool.id == spool_id).first()
                if not spool:
                    return None

                spool.status = stat_val
                session.commit()
                session.refresh(spool)
                return spool
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error updating spool #{spool_id} status: {e}")
                raise

    def set_hold_status(
        self,
        spool_id: int,
        on_hold: bool,
        reason: str,
        action_by: str,
    ) -> Optional[Spool]:
        with self._session() as session:
            try:
                spool = session.query(Spool).filter(Spool.id == spool_id).first()
                if not spool:
                    return None

                spool.status = "HOLD" if on_hold else "Prefabrication"
                session.commit()
                session.refresh(spool)
                return spool
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error setting hold on spool #{spool_id}: {e}")
                raise

    def dispatch_spools_to_site(
        self,
        spool_ids: List[int],
        shipping_manifest_number: str,
        dispatched_by: str,
    ) -> int:
        with self._session() as session:
            try:
                updated_count = (
                    session.query(Spool)
                    .filter(
                        Spool.id.in_(spool_ids),
                    )
                    .update(
                        {
                            "status": SpoolStatus.IN_TRANSIT.value,
                        },
                        synchronize_session="fetch",
                    )
                )
                session.commit()
                return updated_count
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Failed to dispatch spools batch: {e}")
                raise

    def mark_spools_erected(
        self,
        spool_ids: List[int],
        erected_by: str,
        erection_date: Optional[date] = None,
    ) -> int:
        with self._session() as session:
            try:
                count = (
                    session.query(Spool)
                    .filter(Spool.id.in_(spool_ids))
                    .update(
                        {
                            "status": SpoolStatus.ERECTED.value,
                            "installed_date": erection_date or date.today(),
                        },
                        synchronize_session="fetch",
                    )
                )
                session.commit()
                return count
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error marking spools erected: {e}")
                raise

    def get_fabrication_kpis(self, project_id: int) -> Dict[str, Any]:
        with self._session() as session:
            total_spools = session.query(func.count(Spool.id)).filter(Spool.project_id == project_id).scalar() or 0
            fab_completed = session.query(func.count(Spool.id)).filter(
                Spool.project_id == project_id,
                Spool.status.in_([
                    SpoolStatus.FABRICATION_COMPLETED.value,
                    SpoolStatus.NDT_CLEARED.value,
                    SpoolStatus.PAINTING.value,
                    SpoolStatus.READY_TO_DISPATCH.value,
                    SpoolStatus.IN_TRANSIT.value,
                    SpoolStatus.SITE_LAYDOWN.value,
                    SpoolStatus.ERECTED.value,
                ]),
            ).scalar() or 0

            erected_spools = session.query(func.count(Spool.id)).filter(
                Spool.project_id == project_id,
                Spool.status == SpoolStatus.ERECTED.value,
            ).scalar() or 0

            total_weight_kg = float(session.query(func.sum(Spool.weight_kg)).filter(Spool.project_id == project_id).scalar() or 0.0)

            return {
                "project_id": project_id,
                "counts": {
                    "total_spools": total_spools,
                    "fabricated_spools": fab_completed,
                    "erected_spools": erected_spools,
                    "fabrication_count_pct": round((fab_completed / total_spools * 100), 2) if total_spools > 0 else 0.0,
                    "erection_count_pct": round((erected_spools / total_spools * 100), 2) if total_spools > 0 else 0.0,
                },
                "engineering_metrics": {
                    "total_tonnage": round(total_weight_kg / 1000.0, 2),
                },
            }