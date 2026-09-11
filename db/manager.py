# -*- coding: utf-8 -*-
"""
db/manager.py – Database Manager for PipeAgent
===============================================
Handles engine creation, session management, schema creation,
lightweight schema patches, and initial data seeding.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Optional, Generator, Any

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from config import (
    DATABASE_URL,
    BOOTSTRAP_ADMIN_PASSWORD,
    ALLOW_INSECURE_DEFAULTS,
)
from db.models import Base, User
import db.models_enterprise  # ensure models are registered
from core.exceptions import DatabaseError
from security.hashing import hash_password as secure_hash_password

logger = logging.getLogger(__name__)

_SCHEMA_PATCHES = (
    ("projects", "status", "VARCHAR(40) DEFAULT 'ACTIVE'"),
    ("projects", "project_type", "VARCHAR(50)"),
    ("users", "email", "VARCHAR(255)"),
    ("users", "auth_provider", "VARCHAR(40) DEFAULT 'local'"),
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:")


def _is_memory_sqlite(url: str) -> bool:
    normalized = url.replace("\\", "/").lower()
    return normalized in {"sqlite://", "sqlite:///:memory:"} or ":memory:" in normalized


def _engine_kwargs(url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "echo": False,
        "future": True,
        "pool_pre_ping": True,
    }
    if _is_sqlite(url):
        kwargs["connect_args"] = {"check_same_thread": False}
        if _is_memory_sqlite(url):
            kwargs["poolclass"] = StaticPool
    return kwargs


def _register_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            if not _is_memory_sqlite(str(engine.url)):
                cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


class DatabaseManager:
    """Central database manager for the application."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        self.database_url = database_url or DATABASE_URL
        self._engine: Optional[Engine] = None
        self._session_factory = None
        self.SessionLocal = None
        self._initialized = False
        self._initializing = False

    # Legacy aliases used by tests and the enterprise API.
    @property
    def _is_initialized(self) -> bool:
        return self._initialized

    @_is_initialized.setter
    def _is_initialized(self, value: bool) -> None:
        self._initialized = bool(value)

    @property
    def engine(self) -> Optional[Engine]:
        return self._engine

    @engine.setter
    def engine(self, value: Optional[Engine]) -> None:
        self._engine = value
        if value is not None:
            self._session_factory = sessionmaker(
                bind=value,
                class_=Session,
                expire_on_commit=False,
                future=True,
            )
            self.SessionLocal = self._session_factory

    # ──────────────────────────────
    # Initialization
    # ──────────────────────────────
    def initialize(self) -> bool:
        if self._initialized:
            return True
        if self._initializing:
            logger.warning("DatabaseManager.initialize() called while already initializing.")
            return False

        self._initializing = True
        try:
            logger.info("Initializing database engine...")
            if self._engine is None:
                self._engine = create_engine(self.database_url, **_engine_kwargs(self.database_url))
                if _is_sqlite(self.database_url):
                    _register_sqlite_pragmas(self._engine)

            self._session_factory = sessionmaker(
                bind=self._engine,
                class_=Session,
                expire_on_commit=False,
                future=True,
            )
            self.SessionLocal = self._session_factory

            logger.info("Creating all tables...")
            Base.metadata.create_all(self._engine)
            self._apply_schema_patches()

            self._initialized = True

            logger.info("Seeding default data...")
            self._seed_default_data()

            logger.info("Database initialization completed successfully.")
            return True

        except Exception as exc:
            self._initialized = False
            logger.exception("Database initialization failed.")
            raise DatabaseError(f"Unexpected DB init error: {exc}") from exc
        finally:
            self._initializing = False

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    def _apply_schema_patches(self) -> None:
        """Add columns introduced after the original SQLite file was created."""
        if self._engine is None:
            return
        inspector = inspect(self._engine)
        tables = set(inspector.get_table_names())
        for table, column, ddl in _SCHEMA_PATCHES:
            if table not in tables:
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            if column in existing:
                continue
            logger.info("Applying schema patch: %s.%s", table, column)
            with self._engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))

    # ──────────────────────────────
    # Session Management
    # ──────────────────────────────
    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Preferred: context-managed session with auto commit/rollback."""
        self._ensure_initialized()
        factory = self._session_factory or self.SessionLocal
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_session(self) -> Session:
        """
        Return a new raw Session.
        Caller is responsible for closing it (session.close()).
        """
        self._ensure_initialized()
        factory = self._session_factory or self.SessionLocal
        return factory()

    def test_connection(self) -> bool:
        """Return True when the engine can execute a trivial statement."""
        try:
            self._ensure_initialized()
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            logger.exception("Database connectivity check failed")
            return False

    # ──────────────────────────────
    # User convenience methods
    # ──────────────────────────────
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Fetch a user by username, or None if not found."""
        with self.session_scope() as session:
            user = session.query(User).filter(User.username == username).first()
            if user is None:
                return None
            session.expunge(user)
            return user

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Fetch a user by primary key."""
        with self.session_scope() as session:
            user = session.get(User, user_id)
            if user is None:
                return None
            session.expunge(user)
            return user

    def create_user(self, username: str, password: str, role: str = "viewer", **kwargs) -> User:
        """Create a new user and return the detached object."""
        with self.session_scope() as session:
            user = User(
                username=username,
                password_hash=self._hash_password(password),
                role=role,
                **kwargs
            )
            session.add(user)
            session.flush()
            session.expunge(user)
            return user

    def update_user_last_login(self, user: User) -> None:
        """Update the last_login timestamp for the given user."""
        with self.session_scope() as session:
            db_user = session.get(User, user.id)
            if db_user:
                db_user.last_login = _utcnow()

    def update_user_password_hash(self, user_id: int, password_hash: str) -> None:
        with self.session_scope() as session:
            db_user = session.get(User, user_id)
            if db_user:
                db_user.password_hash = password_hash

    @staticmethod
    def _hash_password(password: str) -> str:
        """
        Hash password using the same secure algorithm used by
        security.hashing.verify_password (Argon2id → Bcrypt → PBKDF2).
        """
        return secure_hash_password(password)

    # ──────────────────────────────
    # Seed Data
    # ──────────────────────────────
    def _resolve_bootstrap_password(self) -> Optional[str]:
        if BOOTSTRAP_ADMIN_PASSWORD:
            return BOOTSTRAP_ADMIN_PASSWORD
        if "postgresql" in (self.database_url or "").lower():
            logger.warning(
                "Skipping default admin on PostgreSQL. Set PIPEAGENT_BOOTSTRAP_ADMIN_PASSWORD."
            )
            return None
        if not ALLOW_INSECURE_DEFAULTS:
            logger.warning("Insecure default admin is disabled; no bootstrap admin was created.")
            return None
        logger.warning(
            "Creating default admin user with password 'admin'. "
            "Change this immediately and never use it in production."
        )
        return "admin"

    def _seed_default_data(self) -> None:
        with self.session_scope() as session:
            admin = session.query(User).filter_by(username="admin").first()
            if admin:
                logger.info("Admin user already exists; skipping creation.")
                return

            password = self._resolve_bootstrap_password()
            if not password:
                return

            admin = User(
                username="admin",
                password_hash=self._hash_password(password),
                role="admin",
                full_name="Administrator",
                is_active=True,
                auth_provider="local",
            )
            session.add(admin)
            logger.info("Bootstrap admin user created (username: admin).")

        logger.info("Default data seeding completed.")

    # ──────────────────────────────
    # Utility methods
    # ──────────────────────────────
    def get_engine(self):
        self._ensure_initialized()
        return self._engine

    def get_session_factory(self):
        self._ensure_initialized()
        return self._session_factory

    def close(self) -> None:
        """Compatibility alias for integrations/tests."""
        self.dispose()

    def dispose(self) -> None:
        if self._engine:
            self._engine.dispose()
        self._initialized = False
        self._initializing = False
        self._engine = None
        self._session_factory = None
        self.SessionLocal = None
