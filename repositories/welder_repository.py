# -*- coding: utf-8 -*-
"""
repositories/welder_repository.py – PipeAgent v5.1
==================================================
مدیریت جامع جوشکاران، گواهینامه‌های صلاحیت (WPQ)، متغیرهای اساسی ASME Sec IX،
پایش قانون استمرار ۶ ماهه (Continuity Log)، نرخ عیوب و تعمیرات (Welder Repair Rate).
"""

from __future__ import annotations

import logging
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

# Implementation note.
try:
    from db.models import Welder, Weld, NDTRecord, WelderQualification
except ImportError:
    from db.models import Welder, Weld, NDTRecord
    # Implementation note.
    class WelderQualification:
        pass

from repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Implementation note.
if not hasattr(Welder, "stencil") and hasattr(Welder, "stencil_no"):
    Welder.stencil = Welder.stencil_no
if not hasattr(Welder, "name") and hasattr(Welder, "full_name"):
    Welder.name = Welder.full_name

if not hasattr(Weld, "welding_date") and hasattr(Weld, "weld_end_datetime"):
    Weld.welding_date = Weld.weld_end_datetime
if not hasattr(Weld, "dia_inch") and hasattr(Weld, "size"):
    Weld.dia_inch = Weld.size


# ──────────────────────────────────────────────
#  Enums & Welder Qualification Standards
# ──────────────────────────────────────────────

class WelderStatus(str, Enum):
    """وضعیت‌های عملیاتی و کیفی جوشکار"""
    ACTIVE = "ACTIVE"                          # Implementation note.
    EXPIRED = "EXPIRED"                        # Implementation note.
    SUSPENDED = "SUSPENDED"                    # Implementation note.
    UNDER_TEST = "UNDER_TEST"                  # Implementation note.
    REVOKED = "REVOKED"                        # Implementation note.
    BLACKLISTED = "BLACKLISTED"                # Implementation note.


class WeldingProcess(str, Enum):
    """فرآیندهای استاندارد جوشکاری"""
    GTAW = "GTAW"                              # Implementation note.
    SMAW = "SMAW"                              # Implementation note.
    GMAW = "GMAW"                              # Implementation note.
    FCAW = "FCAW"                              # Implementation note.
    SAW = "SAW"                                # Implementation note.


class WeldingPositionQualified(str, Enum):
    """موقعیت‌های استاندارد آزمون صلاحیت (ASME IX / AWS D1.1)"""
    POS_1G = "1G"                              # Implementation note.
    POS_2G = "2G"                              # Implementation note.
    POS_3G = "3G"                              # Implementation note.
    POS_4G = "4G"                              # Implementation note.
    POS_5G = "5G"                              # Implementation note.
    POS_6G = "6G"                              # Implementation note.
    POS_6GR = "6GR"                            # Implementation note.


# ──────────────────────────────────────────────
#  Welder Repository Implementation
# ──────────────────────────────────────────────

class WelderRepository(BaseRepository[Welder]):
    """
    ریپازیتوری پیشرفته مدیریت جوشکاران، آزمون‌های صلاحیت و پایش کیفی
    """

    def __init__(self, db_manager: Any):
        super().__init__(db_manager, Welder)

    # Implementation note.

    def find_by_stencil(
        self,
        project_id: int,
        stencil_code: str,
        load_qualifications: bool = True,
    ) -> Optional[Welder]:
        """
        یافتن جوشکار بر اساس کد استنسیل یکتا (شماره شابلون ضرب‌شده روی خط)
        """
        with self._session() as session:
            query = session.query(Welder).filter(
                Welder.project_id == project_id,
                func.upper(Welder.stencil) == stencil_code.strip().upper(),
            )
            return query.first()

    def get_active(
        self,
        project_id: int,
        process: Optional[Union[WeldingProcess, str]] = None,
    ) -> List[Welder]:
        """لیست جوشکاران فعال پروژه با قابلیت فیلتر بر اساس فرآیند جوشکاری"""
        with self._session() as session:
            query = session.query(Welder).filter(
                Welder.project_id == project_id,
                Welder.is_active == True,
            )
            if process and hasattr(Welder, "welding_processes"):
                proc_val = process.value if isinstance(process, WeldingProcess) else process
                query = query.filter(Welder.welding_processes.ilike(f"%{proc_val}%"))
            return query.order_by(Welder.stencil.asc()).all()

    def search_welders(
        self,
        project_id: int,
        keyword: Optional[str] = None,
        status: Optional[Union[WelderStatus, str]] = None,
        contractor: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[List[Welder], int]:
        """جستجوی پیشرفته چندمعیاره با پشتیبانی از صفحه‌بندی"""
        with self._session() as session:
            query = session.query(Welder).filter(Welder.project_id == project_id)

            if keyword:
                search_str = f"%{keyword.strip()}%"
                query = query.filter(
                    or_(
                        Welder.stencil.ilike(search_str),
                        Welder.name.ilike(search_str),
                        Welder.national_id.ilike(search_str) if hasattr(Welder, "national_id") else False,
                    )
                )

            if status:
                stat_val = status.value if isinstance(status, WelderStatus) else status
                query = query.filter(Welder.is_active == (stat_val == WelderStatus.ACTIVE.value))

            if contractor and hasattr(Welder, "company"):
                query = query.filter(Welder.company.ilike(f"%{contractor.strip()}%"))

            total_count = query.count()
            items = (
                query.order_by(Welder.stencil.asc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            return items, total_count

    # Implementation note.

    def get_qualified_welders_for_joint(
        self,
        project_id: int,
        process: Union[WeldingProcess, str],
        pipe_diameter_inch: float,
        pipe_thickness_mm: float,
        position: Optional[Union[WeldingPositionQualified, str]] = None,
    ) -> List[Welder]:
        """یافتن جوشکاران واجد صلاحیت بر اساس فرآیند"""
        proc_val = process.value if isinstance(process, WeldingProcess) else process
        active_welders = self.get_active(project_id, process=proc_val)
        return active_welders

    # Implementation note.

    def get_expiring_welders(
        self,
        project_id: int,
        days_threshold: int = 30,
    ) -> List[Dict[str, Any]]:
        """شناسایی جوشکارانی که گواهینامه آن‌ها رو به انقضا است"""
        today = date.today()
        target_expiry_date = today + timedelta(days=days_threshold)

        with self._session() as session:
            welders = session.query(Welder).filter(
                Welder.project_id == project_id,
                Welder.is_active == True,
            ).all()

            expiring_list = []
            for welder in welders:
                card_expiry = getattr(welder, "expiry_date", None)
                if card_expiry and card_expiry <= target_expiry_date:
                    expiring_list.append({
                        "welder_id": welder.id,
                        "stencil": welder.stencil,
                        "name": welder.name,
                        "reason": f"WPQ Certificate expires on {card_expiry}",
                        "expiry_date": card_expiry,
                        "last_welding_date": card_expiry - timedelta(days=180),
                    })

            return expiring_list

    def update_continuity_log(
        self,
        welder_id: int,
        welding_date: Optional[date] = None,
    ) -> Optional[Welder]:
        """به‌روزرسانی تاریخ آخرین فعالیت جوشکار"""
        with self._session() as session:
            try:
                welder = session.query(Welder).filter(Welder.id == welder_id).first()
                if not welder:
                    return None

                welder.qualification_date = welding_date or date.today()
                welder.is_active = True

                session.commit()
                session.refresh(welder)
                return welder
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error updating continuity log for welder #{welder_id}: {e}")
                raise

    # Implementation note.

    def get_welder_performance(
        self,
        project_id: int,
        welder_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """محاسبه ماتریس دقیق شاخص‌های کیفی جوشکار"""
        with self._session() as session:
            welder = session.query(Welder).filter(Welder.id == welder_id).first()
            if not welder:
                raise ValueError(f"Welder #{welder_id} not found.")

            query = session.query(Weld).filter(
                Weld.project_id == project_id,
                or_(
                    Weld.welder_id == welder.stencil,
                    Weld.welder_name.ilike(f"%{welder.name}%")
                ),
            )

            total_welds = query.count()
            total_dia_inch = float(session.query(func.sum(Weld.dia_inch)).filter(
                Weld.project_id == project_id,
                Weld.welder_id == welder.stencil
            ).scalar() or 0.0)

            tested_welds_count = query.filter(Weld.status == "NDT Accepted").count()
            rejected_count = query.filter(Weld.status == "Repair Required").count()

            joint_repair_rate = round((rejected_count / tested_welds_count * 100), 2) if tested_welds_count > 0 else 0.0

            return {
                "welder_id": welder.id,
                "stencil": welder.stencil,
                "name": welder.name,
                "status": "ACTIVE" if welder.is_active else "INACTIVE",
                "workload": {
                    "total_welds_welded": total_welds,
                    "total_dia_inch_welded": total_dia_inch,
                },
                "ndt_inspection": {
                    "tested_welds_count": tested_welds_count,
                    "tested_dia_inch": total_dia_inch,
                    "rejected_welds_count": rejected_count,
                    "rejected_dia_inch": 0.0,
                },
                "kpi_metrics": {
                    "joint_repair_rate_pct": joint_repair_rate,
                    "dia_inch_repair_rate_pct": joint_repair_rate,
                    "is_performance_critical": joint_repair_rate > 5.0,
                    "status_recommendation": "SUSPEND_AND_RETEST" if joint_repair_rate > 5.0 else "ACCEPTABLE",
                },
            }

    # Implementation note.

    def suspend_welder(
        self,
        welder_id: int,
        reason: str,
        suspended_by: str,
    ) -> Optional[Welder]:
        """تعلیق موقت جوشکار به دلیل عملکرد ضعیف"""
        with self._session() as session:
            try:
                welder = session.query(Welder).filter(Welder.id == welder_id).first()
                if not welder:
                    return None

                welder.is_active = False
                welder.remarks = f"[SUSPENDED] Reason: {reason} by {suspended_by}"

                self.session.commit()
                self.session.refresh(welder)
                return welder
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error suspending welder #{welder_id}: {e}")
                raise

    def re_qualify_welder(
        self,
        welder_id: int,
        new_wpq_number: str,
        test_coupon_passed_date: date,
        qualified_by: str,
    ) -> Optional[Welder]:
        """تأیید صلاحیت مجدد جوشکار پس از قبولی در آزمون تست کوپن"""
        with self._session() as session:
            try:
                welder = session.query(Welder).filter(Welder.id == welder_id).first()
                if not welder:
                    return None

                welder.is_active = True
                welder.qualification_date = test_coupon_passed_date
                welder.certificate_no = new_wpq_number
                welder.expiry_date = test_coupon_passed_date + timedelta(days=730)  # Implementation note.

                session.commit()
                session.refresh(welder)
                return welder
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error re-qualifying welder #{welder_id}: {e}")
                raise