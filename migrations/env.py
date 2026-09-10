# -*- coding: utf-8 -*-
"""
migrations/env.py – PipeAgent v5.1
===================================
Alembic migration runtime environment script.

Key Enhancements:
  • Robust sys.path bootstrap (runs from any working directory).
  • Dynamic DB URL resolution from config.py / DATABASE_URL.
  • Full metadata discovery across all model layers (Core, Enterprise, Snippets).
  • Automatic SQLite Batch Mode (`render_as_batch=True`) for safe ALTER/DROP.
  • Deep schema diffing (`compare_type=True`, `compare_server_default=True`).
  • Thread-safe SQLite connection parameters.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import engine_from_config, pool
from alembic import context

# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────
# Implementation note.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────
try:
    from config import DATABASE_URL
    if DATABASE_URL:
        config.set_main_option("sqlalchemy.url", str(DATABASE_URL))
except ImportError:
    # Implementation note.
    pass

# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────
# Implementation note.
from db.models import Base

# Implementation note.
try:
    import db.models_enterprise  # noqa: F401
except ImportError:
    pass

# Implementation note.
try:
    import db.models_test_request_snippet  # noqa: F401
except ImportError:
    pass

# Implementation note.
target_metadata = Base.metadata


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────
def include_object(
    object_: Any,
    name: Optional[str],
    type_: str,
    reflected: bool,
    compare_to: Optional[Any],
) -> bool:
    """
    جلوگیری از تغییر جداول داخلی سیستم یا جداول موقت.
    """
    # Implementation note.
    if type_ == "table" and name and name.startswith("sqlite_"):
        return False
    return True


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────
def run_migrations_offline() -> None:
    """
    اجرای مایگریشن در حالت آفلاین.
    دستورات SQL تولید شده و بدون اعمال مستقیم، چاپ یا ذخیره می‌شوند.
    """
    url = config.get_main_option("sqlalchemy.url")
    is_sqlite = "sqlite" in (url or "").lower()

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=is_sqlite,  # Implementation note.
        compare_type=True,          # Implementation note.
        compare_server_default=True,# Implementation note.
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────
def run_migrations_online() -> None:
    """
    اجرای مایگریشن در حالت آنلاین.
    مستقیماً به دیتابیس متصل شده و تراکنش‌ها را اعمال می‌کند.
    """
    # Implementation note.
    configuration: Dict[str, Any] = config.get_section(config.config_ini_section) or {}
    
    # Implementation note.
    db_url = config.get_main_option("sqlalchemy.url")
    if db_url:
        configuration["sqlalchemy.url"] = db_url

    # Implementation note.
    connect_args: Dict[str, Any] = {}
    is_sqlite = "sqlite" in (db_url or "").lower()
    if is_sqlite:
        connect_args["check_same_thread"] = False

    # Implementation note.
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    with connectable.connect() as connection:
        # Implementation note.
        dialect_is_sqlite = connection.dialect.name == "sqlite"

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=dialect_is_sqlite,  # Implementation note.
            compare_type=True,                  # Implementation note.
            compare_server_default=True,        # Implementation note.
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()