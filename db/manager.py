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

# Physical DB column renames applied BEFORE create_all so SQLAlchemy does not
# add empty duplicates next to the legacy names.
_COLUMN_RENAMES = (
    ("welds", "weld_id", "weld_number"),
    ("welds", "size", "size_nps"),
    ("welds", "filler_heat_no", "heat_number_filler"),
    ("wps_pqr", "wps_id", "wps_number"),
    ("wps_pqr", "pqr_id", "pqr_number"),
    ("welders", "stencil_no", "stencil_number"),
    ("welders", "certificate_no", "certificate_number"),
    ("ncr_records", "ncr_no", "ncr_number"),
    ("handover_packages", "package_no", "package_number"),
    ("mcc_records", "mcc_no", "mcc_number"),
    ("walkdown_checklists", "walkdown_no", "walkdown_number"),
    ("tie_in_records", "tie_in_no", "tie_in_number"),
    ("test_requests", "request_no", "request_number"),
    ("test_requests", "weld_id", "weld_number"),
    ("punch_items", "weld_id", "weld_number"),
    ("wrapping_records", "weld_id", "weld_number"),
    ("asbuilt_records", "drawing_no", "drawing_number"),
    ("asbuilt_markups", "drawing_no", "drawing_number"),
    ("pipe_supports", "drawing_no", "drawing_number"),
    ("dimensional_check_records", "drawing_no", "drawing_number"),
    ("dimensional_check_records", "check_no", "check_number"),
    ("material_issue_records", "issue_slip_no", "issue_slip_number"),
    ("material_receipt_records", "delivery_note_no", "delivery_note_number"),
    ("material_items", "size", "size_nps"),
    ("material_takeoff", "size", "size_nps"),
    ("weld_report_drafts", "report_no", "report_number"),
    ("weld_report_drafts", "weld_pk", "weld_id"),
    ("weld_report_drafts", "weld_no", "weld_number"),
    ("weld_report_drafts", "spool_no", "spool_number"),
    ("weld_report_drafts", "wps_id", "wps_number"),
    ("weld_reports", "report_no", "report_number"),
    ("weld_reports", "weld_pk", "weld_id"),
    ("weld_reports", "weld_no", "weld_number"),
    ("weld_reports", "spool_no", "spool_number"),
    ("weld_reports", "wps_id", "wps_number"),
    ("fitup_report_drafts", "report_no", "report_number"),
    ("fitup_report_drafts", "weld_pk", "weld_id"),
    ("fitup_report_drafts", "weld_no", "weld_number"),
    ("fitup_report_drafts", "spool_no", "spool_number"),
    ("fitup_report_drafts", "fitup_no", "fitup_number"),
    ("fitup_reports", "report_no", "report_number"),
    ("fitup_reports", "weld_pk", "weld_id"),
    ("fitup_reports", "weld_no", "weld_number"),
    ("fitup_reports", "spool_no", "spool_number"),
    ("fitup_reports", "fitup_no", "fitup_number"),
    ("transmittals", "transmittal_no", "transmittal_number"),
    ("ndt_records", "weld_id_fk", "weld_id"),
    ("joint_history", "weld_id_fk", "weld_id"),
    ("pwht_records", "weld_id_fk", "weld_id"),
    ("pwht_records", "pwht_procedure_no", "pwht_procedure_number"),
    ("hardness_test_records", "weld_id_fk", "weld_id"),
    ("ferrite_test_records", "weld_id_fk", "weld_id"),
    ("weld_map_entries", "weld_id_fk", "weld_id"),
    ("welding_telemetry", "weld_id_fk", "weld_id"),
    ("document_evidences", "weld_id_fk", "weld_id"),
    ("document_evidences", "document_id_fk", "document_id"),
    ("transmittal_items", "document_id_fk", "document_id"),
    ("test_packages", "test_pressure_bar", "test_pressure_barg"),
    ("test_packages", "certificate_no", "certificate_number"),
    ("leak_test_records", "test_pressure_bar", "test_pressure_barg"),
    ("valve_records", "hydro_shell_pressure_bar", "hydro_shell_pressure_barg"),
    ("valve_records", "hydro_seat_pressure_bar", "hydro_seat_pressure_barg"),
)

_SCHEMA_PATCHES = (
    ("projects", "status", "VARCHAR(40) DEFAULT 'ACTIVE'"),
    ("projects", "project_type", "VARCHAR(50)"),
    ("projects", "contract_number", "VARCHAR(100)"),
    ("projects", "site_location", "VARCHAR(200)"),
    ("projects", "start_date", "DATE"),
    ("projects", "target_completion_date", "DATE"),
    ("users", "email", "VARCHAR(255)"),
    ("users", "auth_provider", "VARCHAR(40) DEFAULT 'local'"),
    ("line_list", "corrosion_allowance_mm", "FLOAT"),
    ("line_list", "ndt_percent_pt", "FLOAT DEFAULT 0"),
    ("line_list", "ndt_percent_mt", "FLOAT DEFAULT 0"),
    ("line_list", "insulation_thickness_mm", "FLOAT"),
    ("line_list", "sour_service", "BOOLEAN DEFAULT 0"),
    ("line_list", "dn", "VARCHAR(30)"),
    ("line_list", "pcf_number", "VARCHAR(100)"),
    ("line_list", "isometric_revision", "VARCHAR(20)"),
    ("welds", "schedule", "VARCHAR(30)"),
    ("welds", "welding_process", "VARCHAR(50)"),
    ("welds", "welding_position", "VARCHAR(30)"),
    ("welds", "p_number", "VARCHAR(20)"),
    ("welds", "group_number", "VARCHAR(20)"),
    ("welds", "heat_number_pipe", "VARCHAR(100)"),
    ("welds", "vt_result", "VARCHAR(30)"),
    ("welders", "qualified_diameter_max_inch", "FLOAT"),
    ("welders", "f_number", "VARCHAR(20)"),
    ("welders", "progression", "VARCHAR(20)"),
    ("welders", "backing", "VARCHAR(20)"),
    ("welders", "last_welded_date", "DATE"),
    ("wps_pqr", "p_number", "VARCHAR(20)"),
    ("wps_pqr", "f_number", "VARCHAR(20)"),
    ("wps_pqr", "a_number", "VARCHAR(20)"),
    ("wps_pqr", "thickness_min_mm", "FLOAT"),
    ("wps_pqr", "thickness_max_mm", "FLOAT"),
    ("wps_pqr", "position", "VARCHAR(30)"),
    ("wps_pqr", "gas_backing", "BOOLEAN DEFAULT 0"),
    ("ndt_records", "procedure_number", "VARCHAR(100)"),
    ("ndt_records", "acceptance_standard", "VARCHAR(100)"),
    ("ndt_records", "technique", "VARCHAR(80)"),
    ("ndt_records", "extent_pct", "FLOAT"),
    ("ndt_records", "indication", "TEXT"),
    ("ndt_records", "film_density", "FLOAT"),
    ("ndt_records", "is_penalty", "BOOLEAN DEFAULT 0"),
    ("ndt_records", "penalty_source_weld_id", "INTEGER"),
    ("test_packages", "design_pressure_barg", "FLOAT"),
    ("test_packages", "isolation_boundary", "TEXT"),
    ("test_packages", "pid_limits", "VARCHAR(200)"),
    ("welds", "sheet_number", "VARCHAR(50)"),
    ("welds", "sheet_revision", "VARCHAR(20)"),
    ("welds", "revision_status", "VARCHAR(40)"),
    ("welds", "install_location", "VARCHAR(20)"),
    ("welds", "region", "VARCHAR(80)"),
    ("welds", "pipe_class", "VARCHAR(50)"),
    ("welds", "line_service", "VARCHAR(80)"),
    ("welds", "joint_index", "VARCHAR(50)"),
    ("welds", "ndt_percent_rt", "FLOAT"),
    ("welds", "ndt_percent_pt", "FLOAT"),
    ("welds", "pwht_required", "BOOLEAN DEFAULT 0"),
    ("welds", "test_package_number", "VARCHAR(100)"),
    ("welds", "spool_number", "VARCHAR(100)"),
    ("welds", "contractor", "VARCHAR(150)"),
    ("welds", "insulation", "VARCHAR(80)"),
    ("welds", "left_component", "VARCHAR(150)"),
    ("welds", "left_qty", "FLOAT"),
    ("welds", "right_component", "VARCHAR(150)"),
    ("welds", "right_qty", "FLOAT"),
    ("welds", "hold", "BOOLEAN DEFAULT 0"),
    ("welds", "is_expired", "BOOLEAN DEFAULT 0"),
    ("welds", "area_name", "VARCHAR(100)"),
    ("pipe_supports", "revision", "VARCHAR(20)"),
    ("pipe_supports", "install_location", "VARCHAR(20)"),
    ("pipe_supports", "sheet_number", "VARCHAR(50)"),
    ("pipe_supports", "service", "VARCHAR(80)"),
    ("pipe_supports", "size_nps", "VARCHAR(50)"),
    ("pipe_supports", "base_metal", "VARCHAR(100)"),
    ("pipe_supports", "joint_number", "VARCHAR(100)"),
    ("pipe_supports", "weld_status", "VARCHAR(40)"),
    ("pipe_supports", "fabrication_weight_kg", "FLOAT"),
    ("pipe_supports", "erection_weight_kg", "FLOAT"),
    ("pipe_supports", "type_2", "VARCHAR(80)"),
    ("pipe_supports", "fab_fitup_report_number", "VARCHAR(100)"),
    ("pipe_supports", "fab_fitup_date", "DATE"),
    ("pipe_supports", "fab_fitup_result", "VARCHAR(40)"),
    ("pipe_supports", "fab_fitup_contractor", "VARCHAR(150)"),
    ("pipe_supports", "fab_weld_report_number", "VARCHAR(100)"),
    ("pipe_supports", "fab_weld_date", "DATE"),
    ("pipe_supports", "fab_weld_result", "VARCHAR(40)"),
    ("pipe_supports", "fab_weld_contractor", "VARCHAR(150)"),
    ("pipe_supports", "er_fitup_report_number", "VARCHAR(100)"),
    ("pipe_supports", "er_fitup_date", "DATE"),
    ("pipe_supports", "er_fitup_result", "VARCHAR(40)"),
    ("pipe_supports", "er_fitup_contractor", "VARCHAR(150)"),
    ("pipe_supports", "er_weld_report_number", "VARCHAR(100)"),
    ("pipe_supports", "er_weld_date", "DATE"),
    ("pipe_supports", "er_weld_result", "VARCHAR(40)"),
    ("pipe_supports", "er_weld_contractor", "VARCHAR(150)"),
    ("pipe_supports", "welder_name", "VARCHAR(150)"),
    ("pipe_supports", "pt_report_number", "VARCHAR(100)"),
    ("pipe_supports", "pt_date", "DATE"),
    ("pipe_supports", "pt_result", "VARCHAR(40)"),
    ("pipe_supports", "test_package_number", "VARCHAR(100)"),
    ("test_packages", "area_name", "VARCHAR(100)"),
    ("test_packages", "install_location", "VARCHAR(20)"),
    ("test_packages", "dia_inch_total", "FLOAT"),
    ("test_packages", "inch_meter", "FLOAT"),
    ("test_packages", "linecheck_finished", "BOOLEAN DEFAULT 0"),
    ("test_packages", "linecheck_result", "VARCHAR(40)"),
    ("test_packages", "linecheck_result_date", "DATE"),
    ("test_packages", "linecheck_subcontractor", "VARCHAR(150)"),
    ("test_packages", "cleaning_finished", "BOOLEAN DEFAULT 0"),
    ("test_packages", "cleaning_result", "VARCHAR(40)"),
    ("test_packages", "cleaning_result_date", "DATE"),
    ("test_packages", "cleaning_subcontractor", "VARCHAR(150)"),
    ("test_packages", "pressure_test_finished", "BOOLEAN DEFAULT 0"),
    ("test_packages", "pressure_test_result", "VARCHAR(40)"),
    ("test_packages", "pressure_test_result_date", "DATE"),
    ("test_packages", "pressure_test_subcontractor", "VARCHAR(150)"),
    ("test_packages", "flushing_finished", "BOOLEAN DEFAULT 0"),
    ("test_packages", "flushing_result", "VARCHAR(40)"),
    ("test_packages", "flushing_result_date", "DATE"),
    ("test_packages", "flushing_subcontractor", "VARCHAR(150)"),
    ("test_packages", "face_cleaning_finished", "BOOLEAN DEFAULT 0"),
    ("test_packages", "face_cleaning_result", "VARCHAR(40)"),
    ("test_packages", "face_cleaning_result_date", "DATE"),
    ("test_packages", "face_cleaning_subcontractor", "VARCHAR(150)"),
    ("test_packages", "reinstatement_finished", "BOOLEAN DEFAULT 0"),
    ("test_packages", "reinstatement_result", "VARCHAR(40)"),
    ("test_packages", "reinstatement_result_date", "DATE"),
    ("test_packages", "reinstatement_subcontractor", "VARCHAR(150)"),
    ("project_actions", "document_type", "VARCHAR(80)"),
    ("project_actions", "document_number", "VARCHAR(100)"),
    ("project_actions", "document_date", "DATE"),
    ("project_actions", "subcontractor", "VARCHAR(150)"),
    ("project_actions", "rt_report_number", "VARCHAR(100)"),
    ("project_actions", "action_by_1", "VARCHAR(100)"),
    ("project_actions", "action_by_2", "VARCHAR(100)"),
    ("project_actions", "result", "VARCHAR(80)"),
    ("project_actions", "work_front", "VARCHAR(100)"),
    ("project_actions", "link_url", "VARCHAR(500)"),
    ("project_actions", "created_by", "VARCHAR(100)"),
    ("project_actions", "updated_by", "VARCHAR(100)"),
    ("project_actions", "remarks", "TEXT"),
    ("documents", "description", "TEXT"),
    ("documents", "description_fa", "TEXT"),
    ("documents", "receive_transmittal_number", "VARCHAR(100)"),
    ("documents", "receive_letter_number", "VARCHAR(100)"),
    ("documents", "received_from", "VARCHAR(150)"),
    ("documents", "received_date", "DATE"),
    ("documents", "sent_to", "VARCHAR(150)"),
    ("documents", "send_transmittal_number", "VARCHAR(100)"),
    ("documents", "sent_date", "DATE"),
    ("documents", "send_letter_number", "VARCHAR(100)"),
    ("documents", "department", "VARCHAR(100)"),
    ("documents", "area_name", "VARCHAR(100)"),
    ("documents", "doc_class", "VARCHAR(50)"),
    ("documents", "doc_index", "VARCHAR(50)"),
    ("documents", "service", "VARCHAR(80)"),
    ("documents", "sheet_number", "VARCHAR(50)"),
    ("documents", "size_nps", "VARCHAR(50)"),
    ("documents", "markup", "VARCHAR(80)"),
    ("documents", "remarks", "TEXT"),
    ("material_takeoff", "subject", "VARCHAR(200)"),
    ("material_takeoff", "source_document_number", "VARCHAR(100)"),
    ("material_takeoff", "revision", "VARCHAR(20)"),
    ("material_takeoff", "page_number", "VARCHAR(30)"),
    ("material_takeoff", "item_number", "VARCHAR(50)"),
    ("material_takeoff", "thickness_mm", "FLOAT"),
    ("material_takeoff", "length_mm", "FLOAT"),
    ("material_takeoff", "two_year_qty", "FLOAT"),
    ("material_takeoff", "purchase_qty", "FLOAT"),
    ("material_takeoff", "phase", "VARCHAR(50)"),
    ("material_takeoff", "commodity_code", "VARCHAR(50)"),
    ("material_takeoff", "miv_number", "VARCHAR(100)"),
    ("material_takeoff", "miv_date", "DATE"),
    ("material_takeoff", "miv_qty", "FLOAT"),
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

            logger.info("Applying industry column renames...")
            self._apply_column_renames()

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

    def _quote_ident(self, name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    def _apply_column_renames(self) -> None:
        """Rename legacy columns to industry-standard names on existing databases."""
        if self._engine is None:
            return
        inspector = inspect(self._engine)
        for table, old, new in _COLUMN_RENAMES:
            inspector.clear_cache()
            tables = set(inspector.get_table_names())
            if table not in tables:
                continue
            columns = {col["name"]: col for col in inspector.get_columns(table)}
            if old in columns and new not in columns:
                rename_sql = (
                    f"ALTER TABLE {self._quote_ident(table)} "
                    f"RENAME COLUMN {self._quote_ident(old)} TO {self._quote_ident(new)}"
                )
                try:
                    with self._engine.begin() as conn:
                        conn.execute(text(rename_sql))
                    logger.info("Renamed column %s.%s -> %s", table, old, new)
                except Exception:
                    logger.warning(
                        "RENAME COLUMN failed for %s.%s; copying into %s instead.",
                        table, old, new, exc_info=True,
                    )
                    self._copy_column(table, old, new, columns[old])
            elif old in columns and new in columns:
                self._copy_column(table, old, new, columns[old])

    def _copy_column(self, table: str, old: str, new: str, old_meta: dict[str, Any]) -> None:
        """Add `new` if needed and copy values from `old` where `new` is null."""
        if self._engine is None:
            return
        inspector = inspect(self._engine)
        inspector.clear_cache()
        existing = {col["name"] for col in inspector.get_columns(table)}
        if new not in existing:
            ddl_type = str(old_meta.get("type") or "TEXT")
            add_sql = (
                f"ALTER TABLE {self._quote_ident(table)} "
                f"ADD COLUMN {self._quote_ident(new)} {ddl_type}"
            )
            with self._engine.begin() as conn:
                conn.execute(text(add_sql))
            logger.info("Added column %s.%s for legacy copy from %s", table, new, old)
        copy_sql = (
            f"UPDATE {self._quote_ident(table)} "
            f"SET {self._quote_ident(new)} = {self._quote_ident(old)} "
            f"WHERE {self._quote_ident(new)} IS NULL "
            f"AND {self._quote_ident(old)} IS NOT NULL"
        )
        with self._engine.begin() as conn:
            conn.execute(text(copy_sql))

    def _apply_schema_patches(self) -> None:
        """Add columns introduced after the original SQLite file was created."""
        if self._engine is None:
            return
        inspector = inspect(self._engine)
        inspector.clear_cache()
        tables = set(inspector.get_table_names())
        for table, column, ddl in _SCHEMA_PATCHES:
            if table not in tables:
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            if column in existing:
                continue
            logger.info("Applying schema patch: %s.%s", table, column)
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        f"ALTER TABLE {self._quote_ident(table)} "
                        f"ADD COLUMN {self._quote_ident(column)} {ddl}"
                    )
                )
            inspector.clear_cache()

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
