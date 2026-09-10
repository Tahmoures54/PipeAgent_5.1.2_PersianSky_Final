# -*- coding: utf-8 -*-
"""
repositories/asbuilt_repository.py – PipeAgent v5.1
====================================================
Enterprise Repository Pattern implementation for As-Built & Turnover domains.

Repositories covered:
  • IsoRegistryRepository        – مدیریت رجیستری ایزومتریک‌ها
  • WeldMapRepository            – مدیریت نقشه جوش روی ایزو
  • MCCRepository                – مدیریت گواهی‌های تکمیل مکانیکی
  • WalkdownRepository           – مدیریت چک‌لیست‌های بازدید نهایی
  • AsBuiltMarkupRepository      – مدیریت اصلاحات نقشه‌های چون‌ساخت
  • AsBuiltDashboardRepository   – تجمیع آمارهای مانیتورینگ As-Built

Design:
  - Inherits from BaseRepository[T]
  - Fully typed with Python 3.10+ annotations
  - Wraps db.queries.asbuilt_queries with domain encapsulation
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from db.models import (
    AsBuiltMarkUp,
    IsoRegistry,
    MCCRecord,              # Implementation note.
    WalkdownChecklist,
    WeldMapEntry,
)
from db.queries import asbuilt_queries as q
from repositories.base import BaseRepository

logger = logging.getLogger(__name__)

__all__ = [
    "IsoRegistryRepository",
    "WeldMapRepository",
    "MCCRepository",
    "WalkdownRepository",
    "AsBuiltMarkupRepository",
    "AsBuiltDashboardRepository",
]


# ══════════════════════════════════════════════
#  1. ISO Registry Repository
# ══════════════════════════════════════════════

class IsoRegistryRepository(BaseRepository[IsoRegistry]):
    """مخزن مدیریت مدارک و رجیستری نقشه‌های ایزومتریک."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, IsoRegistry)

    def get_by_id(self, iso_id: int) -> Optional[IsoRegistry]:
        """دریافت ایزومتریک بر اساس شناسه اصلی."""
        return q.get_iso_by_id(self.session, iso_id)

    def get_by_number(self, project_id: int, iso_number: str) -> Optional[IsoRegistry]:
        """دریافت ایزومتریک بر اساس شماره نقشه در پروژه."""
        return q.get_iso_by_number(self.session, project_id, iso_number)

    def get_all(
        self,
        project_id: int,
        *,
        status: Optional[str] = None,
        line_number: Optional[str] = None,
        area_id: Optional[int] = None,
        search: Optional[str] = None,
        offset: int = 0,
        limit: int = 200,
    ) -> List[IsoRegistry]:
        """دریافت لیست ایزومتریک‌ها با فیلترهای چندگانه و صفحه‌بندی."""
        return q.get_iso_registry(
            self.session,
            project_id,
            status=status,
            line_number=line_number,
            area_id=area_id,
            search=search,
            offset=offset,
            limit=limit,
        )

    def count(self, project_id: int, *, status: Optional[str] = None) -> int:
        """شمارش تعداد ایزومتریک‌ها در سطح پروژه."""
        return q.count_isos(self.session, project_id, status=status)

    def add(self, **kwargs: Any) -> IsoRegistry:
        """ایجاد یک ایزومتریک جدید."""
        return q.create_iso(self.session, **kwargs)

    def edit(self, iso_id: int, **kwargs: Any) -> Optional[IsoRegistry]:
        """به‌روزرسانی فیلدهای ایزومتریک."""
        return q.update_iso(self.session, iso_id, **kwargs)

    def remove(self, iso_id: int) -> bool:
        """حذف ایزومتریک از پایگاه داده."""
        return q.delete_iso(self.session, iso_id)


# ══════════════════════════════════════════════
#  2. Weld Map Repository
# ══════════════════════════════════════════════

class WeldMapRepository(BaseRepository[WeldMapEntry]):
    """مخزن مدیریت نقشه‌های جوش روی ایزومتریک (Weld Map)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, WeldMapEntry)

    def get_by_id(self, entry_id: int) -> Optional[WeldMapEntry]:
        """دریافت آیتم نقشه جوش بر اساس شناسه."""
        return q.get_weld_map_entry_by_id(self.session, entry_id)

    def get_all(
        self,
        project_id: int,
        *,
        iso_number: Optional[str] = None,
        line_number: Optional[str] = None,
        is_field_weld: Optional[bool] = None,
        offset: int = 0,
        limit: int = 500,
    ) -> List[WeldMapEntry]:
        """دریافت آیتم‌های نقشه جوش با فیلتر ایزو، خط و جوش‌های میدانی."""
        return q.get_weld_map(
            self.session,
            project_id,
            iso_number=iso_number,
            line_number=line_number,
            is_field_weld=is_field_weld,
            offset=offset,
            limit=limit,
        )

    def count(self, project_id: int, *, iso_number: Optional[str] = None) -> int:
        """شمارش آیتم‌های نقشه جوش."""
        return q.count_weld_map_entries(self.session, project_id, iso_number=iso_number)

    def add(self, **kwargs: Any) -> WeldMapEntry:
        """افزودن یک نشانه‌گذاری جوش جدید روی نقشه."""
        return q.create_weld_map_entry(self.session, **kwargs)

    def add_bulk(self, entries: Sequence[Dict[str, Any]], *, batch_size: int = 100) -> int:
        """ثبت دسته‌ای نشانه‌گذاری‌های جوش از فایل اکسل."""
        return q.create_weld_map_entries_bulk(self.session, entries, batch_size=batch_size)

    def edit(self, entry_id: int, **kwargs: Any) -> Optional[WeldMapEntry]:
        """به‌روزرسانی آیتم نقشه جوش."""
        return q.update_weld_map_entry(self.session, entry_id, **kwargs)

    def remove(self, entry_id: int) -> bool:
        """حذف نشانه‌گذاری جوش از نقشه."""
        return q.delete_weld_map_entry(self.session, entry_id)


# ══════════════════════════════════════════════
#  3. MCC Repository (Mechanical Completion)
# ══════════════════════════════════════════════

class MCCRepository(BaseRepository[MCCRecord]):
    """مخزن مدیریت گواهی‌های تکمیل مکانیکی سیستم‌ها (MCC)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, MCCRecord)

    def get_by_id(self, mcc_id: int) -> Optional[MCCRecord]:
        """دریافت گواهی MCC بر اساس شناسه."""
        return q.get_mcc_by_id(self.session, mcc_id)

    def get_all(
        self,
        project_id: int,
        *,
        status: Optional[str] = None,
        system_name: Optional[str] = None,
        area_id: Optional[int] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[MCCRecord]:
        """دریافت لیست گواهی‌های تکمیل مکانیکی با فیلتر وضعیت و سیستم."""
        return q.get_mcc_certificates(
            self.session,
            project_id,
            status=status,
            system_name=system_name,
            area_id=area_id,
            offset=offset,
            limit=limit,
        )

    def count(self, project_id: int, *, status: Optional[str] = None) -> int:
        """شمارش تعداد گواهی‌های MCC."""
        return q.count_mcc_certificates(self.session, project_id, status=status)

    def add(self, **kwargs: Any) -> MCCRecord:
        """ایجاد پرونده گواهی تکمیل مکانیکی جدید."""
        return q.create_mcc(self.session, **kwargs)

    def edit(self, mcc_id: int, **kwargs: Any) -> Optional[MCCRecord]:
        """به‌روزرسانی اطلاعات گواهی MCC."""
        return q.update_mcc(self.session, mcc_id, **kwargs)

    def remove(self, mcc_id: int) -> bool:
        """حذف گواهی MCC."""
        return q.delete_mcc(self.session, mcc_id)


# ══════════════════════════════════════════════
#  4. Walkdown Repository
# ══════════════════════════════════════════════

class WalkdownRepository(BaseRepository[WalkdownChecklist]):
    """مخزن مدیریت چک‌لیست‌های بازدید نهایی و Punch Walk."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, WalkdownChecklist)

    def get_by_id(self, item_id: int) -> Optional[WalkdownChecklist]:
        """دریافت آیتم بازدید بر اساس شناسه."""
        return q.get_walkdown_by_id(self.session, item_id)

    def get_all(
        self,
        project_id: int,
        *,
        status: Optional[str] = None,
        walkdown_type: Optional[str] = None,
        line_number: Optional[str] = None,
        area_id: Optional[int] = None,
        is_compliant: Optional[bool] = None,
        offset: int = 0,
        limit: int = 200,
    ) -> List[WalkdownChecklist]:
        """دریافت چک‌لیست‌های بازدید با فیلترهای چندگانه."""
        return q.get_walkdowns(
            self.session,
            project_id,
            status=status,
            walkdown_type=walkdown_type,
            line_number=line_number,
            area_id=area_id,
            is_compliant=is_compliant,
            offset=offset,
            limit=limit,
        )

    def count(self, project_id: int, *, status: Optional[str] = None) -> int:
        """شمارش آیتم‌های چک‌لیست بازدید."""
        return q.count_walkdowns(self.session, project_id, status=status)

    def add(self, **kwargs: Any) -> WalkdownChecklist:
        """افزودن آیتم جدید به چک‌لیست بازدید."""
        return q.create_walkdown(self.session, **kwargs)

    def edit(self, item_id: int, **kwargs: Any) -> Optional[WalkdownChecklist]:
        """به‌روزرسانی آیتم چک‌لیست بازدید."""
        return q.update_walkdown(self.session, item_id, **kwargs)

    def close_item(
        self, item_id: int, *, closed_by: Optional[str] = None
    ) -> Optional[WalkdownChecklist]:
        """بستن و تایید رفع عیب آیتم بازدید (تغییر وضعیت به Closed)."""
        return q.close_walkdown_item(self.session, item_id, closed_by=closed_by)

    def remove(self, item_id: int) -> bool:
        """حذف آیتم بازدید."""
        return q.delete_walkdown(self.session, item_id)


# ══════════════════════════════════════════════
#  5. As-Built Mark-Up Repository
# ══════════════════════════════════════════════

class AsBuiltMarkupRepository(BaseRepository[AsBuiltMarkUp]):
    """مخزن مدیریت تغییرات و اصلاحات نقشه‌های چون‌ساخت (Mark-Ups)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, AsBuiltMarkUp)

    def get_by_id(self, markup_id: int) -> Optional[AsBuiltMarkUp]:
        """دریافت اصلاحیه نقشه بر اساس شناسه."""
        return q.get_markup_by_id(self.session, markup_id)

    def get_all(
        self,
        project_id: int,
        *,
        iso_number: Optional[str] = None,
        drawing_number: Optional[str] = None,
        status: Optional[str] = None,
        markup_type: Optional[str] = None,
        incorporated_only: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> List[AsBuiltMarkUp]:
        """دریافت لیست اصلاحات نقشه‌ها با فیلترهای فنی."""
        return q.get_asbuilt_markups(
            self.session,
            project_id,
            iso_number=iso_number,
            drawing_number=drawing_number,
            status=status,
            markup_type=markup_type,
            incorporated_only=incorporated_only,
            offset=offset,
            limit=limit,
        )

    def count(self, project_id: int, *, status: Optional[str] = None) -> int:
        """شمارش اصلاحات نقشه‌ها."""
        return q.count_markups(self.session, project_id, status=status)

    def add(self, **kwargs: Any) -> AsBuiltMarkUp:
        """ثبت یک اصلاحیه جدید برای نقشه چون‌ساخت."""
        return q.create_markup(self.session, **kwargs)

    def edit(self, markup_id: int, **kwargs: Any) -> Optional[AsBuiltMarkUp]:
        """به‌روزرسانی اصلاحیه نقشه."""
        return q.update_markup(self.session, markup_id, **kwargs)

    def remove(self, markup_id: int) -> bool:
        """حذف رکورد اصلاحیه نقشه."""
        return q.delete_markup(self.session, markup_id)


# ══════════════════════════════════════════════
#  6. As-Built Dashboard Aggregator Repository
# ══════════════════════════════════════════════

class AsBuiltDashboardRepository:
    """مخزن تخصصی محاسبات آماری و شاخص‌های تجمیعی حوزه As-Built."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_stats(self, project_id: int) -> Dict[str, Any]:
        """استخراج کامل آمارهای داشبورد چون‌ساخت پروژه."""
        return q.get_asbuilt_dashboard_stats(self.session, project_id)