# -*- coding: utf-8 -*-
"""
db/manager.py – Database Manager for PipeAgent
===============================================
Handles engine creation, session management, schema creation,
and initial data seeding.
"""

from __future__ import annotations

import logging
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, Generator, Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from config import DATABASE_URL
from db.models import Base, User
import db.models_enterprise  # ensure models are registered
from core.exceptions import DatabaseError

# Implementation note.
from security.hashing import hash_password as secure_hash_password

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Central database manager for the application."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        self.database_url = database_url or DATABASE_URL
        self._engine = None
        self._session_factory = None
        self.SessionLocal = None
        self._initialized = False
        self._initializing = False

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
            self._engine = create_engine(self.database_url, echo=False, future=True)
            self._session_factory = sessionmaker(
                bind=self._engine,
                class_=Session,
                expire_on_commit=False,
                future=True,
            )

            self.SessionLocal = self._session_factory

            logger.info("Creating all tables...")
            Base.metadata.create_all(self._engine)

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

    # ──────────────────────────────
    # Session Management
    # ──────────────────────────────
    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Preferred: context-managed session with auto commit/rollback."""
        self._ensure_initialized()
        session = self._session_factory()
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
        return self._session_factory()

    # ──────────────────────────────
    # User convenience methods
    # ──────────────────────────────
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Fetch a user by username, or None if not found."""
        with self.session_scope() as session:
            user = session.query(User).filter(User.username == username).first()
            return user

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Fetch a user by primary key."""
        with self.session_scope() as session:
            return session.get(User, user_id)

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
                db_user.last_login = datetime.utcnow()

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
    def _seed_default_data(self) -> None:
        with self.session_scope() as session:
            admin = session.query(User).filter_by(username="admin").first()
            if not admin:
                admin = User(
                    username="admin",
                    password_hash=self._hash_password("admin"),
                    role="admin",
                    full_name="Administrator",
                    is_active=True,
                )
                session.add(admin)
                logger.info("Default admin user created (username: admin, password: admin).")
            else:
                logger.info("Admin user already exists; skipping creation.")

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