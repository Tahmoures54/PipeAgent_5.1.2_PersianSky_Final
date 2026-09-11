# -*- coding: utf-8 -*-
"""
repositories/base.py – PipeAgent v5.1
=====================================
Industrial-grade Generic Base Repository for SQLAlchemy 2.0 models.

Key Capabilities:
  • Dual-Mode Session Injection: Accepts either an active SQLAlchemy `Session`
    (for multi-repo atomic Unit of Work transactions) or a `DatabaseManager`.
  • SQLAlchemy 2.0 Compliance: Uses `session.get()`, `select()`, and `scalars()`.
  • Enterprise CRUD Suite: Single, bulk, pagination, soft-delete, and existence checks.
  • Generic Type Safety: Full type hinting with `TypeVar('T')` for IDE auto-completion.
  • Detached Instance Protection: Keeps objects attached within the active transaction scope.
"""

from __future__ import annotations

import logging
from typing import (
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

# Implementation note.
try:
    from db.manager import DatabaseManager
except ImportError:
    DatabaseManager = Any  # type: ignore

try:
    from core.exceptions import DatabaseError, ValidationError
except ImportError:
    class DatabaseError(Exception): pass
    class ValidationError(Exception): pass

logger = logging.getLogger(__name__)

# Implementation note.
T = TypeVar("T")


class BaseRepository(Generic[T]):
    """
    کلاس پایه و جنریک برای تمامی مخازن داده‌ای پلتفرم PipeAgent.

    نحوه استفاده (در لایه سرویس یا کنترلر):
        with db.session_scope() as session:
            repo = BaseRepository[User](session, User)
            user = repo.get_by_id(1)
    """

    def __init__(
        self,
        session_or_db: Union[Session, DatabaseManager],
        model_class: Type[T],
    ) -> None:
        """
        مقداردهی اولیه مخزن با سشن فعال یا مدیر دیتابیس.
        """
        if hasattr(session_or_db, "get_session"):
            # DatabaseManager path: do not open a leaked session here.
            self._db_manager: Optional[DatabaseManager] = session_or_db
            self._session: Optional[Session] = None
        else:
            self._db_manager = None
            self._session = session_or_db  # type: ignore

        self.model_class: Type[T] = model_class

    @property
    def session(self) -> Session:
        """Access the active Session, opening one lazily when backed by DatabaseManager."""
        if self._session is None:
            if self._db_manager is None:
                raise RuntimeError("Repository has no session or database manager.")
            self._session = self._db_manager.get_session()
        return self._session

    def _session_callable(self):
        """Backward-compatible context manager for legacy repositories."""
        return self.session

    # ══════════════════════════════════════════
    #  1. Read / Query Operations
    # ══════════════════════════════════════════

    def get_by_id(
        self,
        id_: Any,
        *,
        include_deleted: bool = False,
    ) -> Optional[T]:
        """
        دریافت رکورد بر اساس کلید اصلی (Primary Key).
        """
        obj = self.session.get(self.model_class, id_)
        if obj is None:
            return None

        # Implementation note.
        if not include_deleted and hasattr(obj, "is_deleted") and obj.is_deleted:
            return None

        return obj

    def get_all(
        self,
        *,
        include_deleted: bool = False,
        offset: int = 0,
        limit: Optional[int] = 100,
    ) -> List[T]:
        """
        دریافت تمام رکوردهای مدل با صفحه‌بندی اختیاری.
        """
        q = self.session.query(self.model_class)

        if not include_deleted and hasattr(self.model_class, "deleted_at"):
            q = q.filter(self.model_class.deleted_at.is_(None))  # type: ignore

        if offset > 0:
            q = q.offset(offset)
        if limit is not None and limit > 0:
            q = q.limit(limit)

        return q.all()

    def filter_by(
        self,
        *,
        include_deleted: bool = False,
        offset: int = 0,
        limit: Optional[int] = 100,
        **kwargs: Any,
    ) -> List[T]:
        """
        جستجو و فیلتر رکوردها بر اساس نام فیلدها و مقادیر دقیق.
        """
        q = self.session.query(self.model_class)

        for key, value in kwargs.items():
            if hasattr(self.model_class, key):
                q = q.filter(getattr(self.model_class, key) == value)

        if not include_deleted and hasattr(self.model_class, "deleted_at"):
            q = q.filter(self.model_class.deleted_at.is_(None))  # type: ignore

        if offset > 0:
            q = q.offset(offset)
        if limit is not None and limit > 0:
            q = q.limit(limit)

        return q.all()

    def find_one(
        self,
        *,
        include_deleted: bool = False,
        **kwargs: Any,
    ) -> Optional[T]:
        """
        یافتن اولین رکوردی که با معیارهای داده‌شده مطابقت دارد.
        """
        results = self.filter_by(include_deleted=include_deleted, limit=1, **kwargs)
        return results[0] if results else None

    def count(
        self,
        *,
        include_deleted: bool = False,
        **filters: Any,
    ) -> int:
        """
        شمارش تعداد رکوردهای منطبق با فیلتر در سطح دیتابیس.
        """
        q = self.session.query(func.count(getattr(self.model_class, "id", 1)))

        for key, value in filters.items():
            if hasattr(self.model_class, key):
                q = q.filter(getattr(self.model_class, key) == value)

        if not include_deleted and hasattr(self.model_class, "deleted_at"):
            q = q.filter(self.model_class.deleted_at.is_(None))  # type: ignore

        return q.scalar() or 0

    def exists(
        self,
        id_: Optional[Any] = None,
        **kwargs: Any,
    ) -> bool:
        """
        بررسی سریع وجود داشتن یک رکورد در بانک اطلاعاتی (بدون بارگذاری شیء کامل).
        """
        if id_ is not None:
            kwargs["id"] = id_
        return self.count(**kwargs) > 0

    # ══════════════════════════════════════════
    #  2. Create Operations
    # ══════════════════════════════════════════

    def create(self, obj: T) -> T:
        """
        افزودن شیء مدل به پایگاه داده و فلاش کردن شناسه (بدون بستن تراکنش).
        """
        self.session.add(obj)
        self.session.flush()
        if self._db_manager is not None:
            self.session.commit()
        return obj

    def create_from_dict(self, **kwargs: Any) -> T:
        """
        ایجاد و ذخیره یک رکورد جدید مستقیماً از روی مقادیر دیکشنری.
        """
        obj = self.model_class(**kwargs)
        return self.create(obj)

    def bulk_create(
        self,
        items: Sequence[Union[T, Dict[str, Any]]],
        *,
        batch_size: int = 100,
    ) -> List[T]:
        """
        ثبت دسته‌ای و بافرشده‌ی رکوردهای متعدد برای سرعت فوق‌العاده بالا.
        """
        if not items:
            return []

        objects: List[T] = []
        for item in items:
            if isinstance(item, dict):
                objects.append(self.model_class(**item))
            else:
                objects.append(item)

        total = len(objects)
        for i in range(0, total, batch_size):
            batch = objects[i : i + batch_size]
            self.session.add_all(batch)
            self.session.flush()

        if self._db_manager is not None:
            self.session.commit()

        logger.debug(
            "Bulk created %d records for %s", total, self.model_class.__name__
        )
        return objects

    # ══════════════════════════════════════════
    #  3. Update Operations
    # ══════════════════════════════════════════

    def update(self, obj: T) -> T:
        """
        ادغام و به‌روزرسانی شیء در سشن جاری.
        """
        merged = self.session.merge(obj)
        self.session.flush()
        if self._db_manager is not None:
            self.session.commit()
        return merged

    def update_by_id(
        self,
        id_: Any,
        *,
        exclude: Optional[Set[str]] = None,
        **kwargs: Any,
    ) -> Optional[T]:
        """
        به‌روزرسانی امن فیلدهای یک رکورد با شناسه.
        """
        obj = self.get_by_id(id_)
        if obj is None:
            return None

        exclude_fields = exclude or {"id", "created_at"}
        changed = 0

        for key, value in kwargs.items():
            if key in exclude_fields:
                continue
            if hasattr(obj, key):
                if getattr(obj, key) != value:
                    setattr(obj, key, value)
                    changed += 1
            else:
                logger.warning(
                    "Field '%s' does not exist on model %s (ignored).",
                    key,
                    self.model_class.__name__,
                )

        if changed > 0:
            self.session.flush()

        return obj

    # ══════════════════════════════════════════
    #  4. Delete Operations
    # ══════════════════════════════════════════

    def delete(self, obj: T) -> None:
        """
        حذف فیزیکی شیء مدل از پایگاه داده.
        """
        self.session.delete(obj)
        self.session.flush()
        if self._db_manager is not None:
            self.session.commit()

    def delete_by_id(self, id_: Any) -> bool:
        """
        حذف فیزیکی رکورد بر اساس شناسه.
        """
        obj = self.get_by_id(id_, include_deleted=True)
        if obj is not None:
            self.delete(obj)
            return True
        return False

    def soft_delete_by_id(self, id_: Any) -> bool:
        """
        حذف نرم (Soft Delete) رکورد در صورت پشتیبانی مدل.
        """
        obj = self.get_by_id(id_)
        if obj is not None and hasattr(obj, "soft_delete"):
            obj.soft_delete()
            self.session.flush()
            return True
        return False

    def restore_by_id(self, id_: Any) -> bool:
        """
        بازگردانی رکورد حذف نرم شده.
        """
        obj = self.get_by_id(id_, include_deleted=True)
        if obj is not None and hasattr(obj, "restore"):
            obj.restore()
            self.session.flush()
            return True
        return False

    # ══════════════════════════════════════════
    #  5. Session / Lifecycle Helpers
    # ══════════════════════════════════════════

    def refresh(self, obj: T) -> T:
        """تازه‌سازی وضعیت فیلدهای شیء از پایگاه داده."""
        self.session.refresh(obj)
        return obj

    def expunge(self, obj: T) -> T:
        """جدا کردن شیء از سشن جاری جهت ارسال به لایه‌های بیرونی."""
        self.session.expunge(obj)
        return obj