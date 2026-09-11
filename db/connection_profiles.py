# -*- coding: utf-8 -*-
"""Local connection profiles for SQLite, PostgreSQL and SQL Server / Express."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

ENGINE_SQLITE = "sqlite"
ENGINE_POSTGRESQL = "postgresql"
ENGINE_MSSQL = "mssql"

ENGINE_LABELS = {
    ENGINE_SQLITE: "Local SQLite (single workstation)",
    ENGINE_POSTGRESQL: "PostgreSQL (LAN or online)",
    ENGINE_MSSQL: "SQL Server / Express (site server)",
}

DEFAULT_MSSQL_DRIVERS = (
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "ODBC Driver 13 for SQL Server",
    "SQL Server",
)


@dataclass
class ConnectionProfile:
    engine: str = ENGINE_SQLITE
    sqlite_path: str = ""
    host: str = "localhost"
    port: str = ""
    instance: str = "SQLEXPRESS"
    database: str = "PipeAgent"
    username: str = ""
    password: str = ""
    windows_auth: bool = False
    driver: str = "ODBC Driver 17 for SQL Server"
    encrypt: bool = False
    trust_server_certificate: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("password"):
            data["password"] = "***"
        return data


def profile_from_mapping(raw: Mapping[str, Any] | None) -> ConnectionProfile:
    data = dict(raw or {})
    password = data.get("password") or ""
    if password == "***":
        password = ""
    return ConnectionProfile(
        engine=str(data.get("engine") or ENGINE_SQLITE),
        sqlite_path=str(data.get("sqlite_path") or ""),
        host=str(data.get("host") or "localhost"),
        port=str(data.get("port") or ""),
        instance=str(data.get("instance") or ""),
        database=str(data.get("database") or "PipeAgent"),
        username=str(data.get("username") or ""),
        password=str(password),
        windows_auth=bool(data.get("windows_auth")),
        driver=str(data.get("driver") or DEFAULT_MSSQL_DRIVERS[1]),
        encrypt=bool(data.get("encrypt")),
        trust_server_certificate=bool(data.get("trust_server_certificate", True)),
    )


def load_profile(path: Path) -> Optional[ConnectionProfile]:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Could not read database connection profile %s", path)
        return None
    if not isinstance(raw, dict):
        return None
    return profile_from_mapping(raw)


def save_profile(path: Path, profile: ConnectionProfile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(profile)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def sqlite_url_for_path(sqlite_path: Path) -> str:
    resolved = sqlite_path.expanduser()
    try:
        resolved = resolved.resolve()
    except OSError:
        pass
    return "sqlite:///" + resolved.as_posix()


def _host_with_instance(host: str, instance: str) -> str:
    host = (host or "localhost").strip()
    instance = (instance or "").strip().lstrip("\\")
    if not instance:
        return host
    if "\\" in host:
        return host
    return f"{host}\\{instance}"


def build_url(profile: ConnectionProfile, *, default_sqlite: Optional[Path] = None) -> str:
    engine = (profile.engine or ENGINE_SQLITE).lower()
    if engine == ENGINE_SQLITE:
        path = Path(profile.sqlite_path) if profile.sqlite_path else (default_sqlite or Path("pipeagent.db"))
        return sqlite_url_for_path(path)
    if engine == ENGINE_POSTGRESQL:
        port = int(profile.port or 5432)
        return URL.create(
            "postgresql+psycopg",
            username=profile.username or "pipeagent",
            password=profile.password or None,
            host=profile.host or "localhost",
            port=port,
            database=profile.database or "pipeagent",
        ).render_as_string(hide_password=False)
    if engine == ENGINE_MSSQL:
        host = _host_with_instance(profile.host, profile.instance)
        query: dict[str, str] = {
            "driver": profile.driver or DEFAULT_MSSQL_DRIVERS[1],
        }
        if profile.windows_auth:
            query["trusted_connection"] = "yes"
        if profile.encrypt:
            query["Encrypt"] = "yes"
        if profile.trust_server_certificate:
            query["TrustServerCertificate"] = "yes"
        url = URL.create(
            "mssql+pyodbc",
            username=None if profile.windows_auth else (profile.username or None),
            password=None if profile.windows_auth else (profile.password or None),
            host=host,
            port=int(profile.port) if str(profile.port).strip().isdigit() else None,
            database=profile.database or "PipeAgent",
            query=query,
        )
        return url.render_as_string(hide_password=False)
    raise ValueError(f"Unsupported database engine: {profile.engine}")


def url_from_saved_profile(path: Path, *, default_sqlite: Optional[Path] = None) -> Optional[str]:
    profile = load_profile(path)
    if profile is None:
        return None
    try:
        return build_url(profile, default_sqlite=default_sqlite)
    except (ValueError, TypeError):
        logger.exception("Saved database profile is invalid")
        return None


def resolve_database_url(
    *,
    env_url: Optional[str] = None,
    profile_path: Optional[Path] = None,
    sqlite_path: Optional[Path] = None,
) -> str:
    env = (env_url or "").strip()
    if env:
        return env
    if profile_path is not None:
        saved = url_from_saved_profile(profile_path, default_sqlite=sqlite_path)
        if saved:
            return saved
    if sqlite_path is not None:
        return sqlite_url_for_path(sqlite_path)
    return "sqlite://"


def redact_database_url(url: str) -> str:
    try:
        parsed = make_url(url)
        return parsed.render_as_string(hide_password=True)
    except Exception:
        return url.split("@")[-1] if "@" in url else url


def describe_database_target(url: str) -> str:
    try:
        parsed = make_url(url)
    except Exception:
        return "Database"
    backend = parsed.get_backend_name()
    if backend == "sqlite":
        database = parsed.database or "memory"
        name = Path(database).name if database != ":memory:" else "memory"
        return f"SQLite · {name}"
    if backend == "postgresql":
        return f"PostgreSQL · {parsed.host}/{parsed.database}"
    if backend == "mssql":
        return f"SQL Server · {parsed.host}/{parsed.database}"
    return f"{backend} · {parsed.database or parsed.host or 'server'}"


def engine_kind(url: str) -> str:
    try:
        return make_url(url).get_backend_name()
    except Exception:
        text_url = (url or "").lower()
        if text_url.startswith("sqlite:"):
            return "sqlite"
        if "postgresql" in text_url or text_url.startswith("postgres"):
            return "postgresql"
        if "mssql" in text_url:
            return "mssql"
        return "unknown"


def odbc_driver_names() -> list[str]:
    try:
        import pyodbc  # type: ignore
    except Exception:
        return list(DEFAULT_MSSQL_DRIVERS)
    names = [str(item) for item in pyodbc.drivers()]
    ordered = [name for name in DEFAULT_MSSQL_DRIVERS if name in names]
    extra = [name for name in names if name not in ordered]
    return ordered + extra or list(DEFAULT_MSSQL_DRIVERS)


def test_database_url(url: str, timeout_seconds: int = 8) -> tuple[bool, str]:
    """Open a short-lived engine and run SELECT 1. Does not create tables."""
    kind = engine_kind(url)
    if kind == "mssql":
        try:
            import pyodbc  # noqa: F401  # type: ignore
        except Exception:
            return (
                False,
                "SQL Server needs the pyodbc package and a Microsoft ODBC driver "
                "on this workstation (ODBC Driver 17 or 18).",
            )
    connect_args: dict[str, Any] = {}
    kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}
    if kind == "sqlite":
        connect_args["check_same_thread"] = False
        kwargs["connect_args"] = connect_args
    elif kind == "postgresql":
        kwargs["connect_args"] = {"connect_timeout": timeout_seconds}
    try:
        engine = create_engine(url, **kwargs)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
        return True, f"Connected ({describe_database_target(url)})."
    except ModuleNotFoundError as exc:
        missing = exc.name or "driver"
        if missing in {"psycopg", "psycopg2"}:
            return False, "PostgreSQL needs the psycopg package (already in requirements.txt)."
        if missing == "pyodbc":
            return False, "SQL Server needs pyodbc and the Microsoft ODBC driver."
        return False, f"Missing database driver: {missing}"
    except SQLAlchemyError as exc:
        logger.info("Database test failed: %s", exc)
        return False, str(exc.orig if getattr(exc, "orig", None) else exc)
    except Exception as exc:
        logger.info("Database test failed: %s", exc)
        return False, str(exc)


def quote_plus_password(password: str) -> str:
    return quote_plus(password or "")
