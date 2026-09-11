# -*- coding: utf-8 -*-
"""Connection profile URLs for SQLite, PostgreSQL and SQL Server / Express."""

from pathlib import Path

from db.manager import DatabaseManager
from db.connection_profiles import (
    ENGINE_MSSQL,
    ENGINE_POSTGRESQL,
    ConnectionProfile,
    build_url,
    describe_database_target,
    redact_database_url,
    resolve_database_url,
    sqlite_url_for_path,
)


def test_sqlite_url_uses_posix_path(tmp_path):
    url = sqlite_url_for_path(tmp_path / "site.db")
    assert url.startswith("sqlite:///")
    assert url.endswith("site.db")


def test_postgresql_url_encodes_credentials():
    profile = ConnectionProfile(
        engine=ENGINE_POSTGRESQL,
        host="db.site.local",
        port="5432",
        database="pipeagent",
        username="pa",
        password="p@ss:word",
    )
    url = build_url(profile)
    assert url.startswith("postgresql+psycopg://")
    assert "db.site.local" in url
    assert "pipeagent" in url
    redacted = redact_database_url(url)
    assert "p@ss:word" not in redacted
    assert describe_database_target(url) == "PostgreSQL · db.site.local/pipeagent"


def test_sql_express_named_instance_and_windows_auth():
    sql_auth = ConnectionProfile(
        engine=ENGINE_MSSQL,
        host="SITE-SQL",
        instance="SQLEXPRESS",
        database="PipeAgent",
        username="sa",
        password="Secret",
        driver="ODBC Driver 17 for SQL Server",
        trust_server_certificate=True,
    )
    url = build_url(sql_auth)
    assert url.startswith("mssql+pyodbc://")
    assert "SITE-SQL" in url
    assert "SQLEXPRESS" in url
    assert "PipeAgent" in url
    assert "ODBC+Driver+17" in url or "ODBC Driver 17" in url

    trusted = ConnectionProfile(
        engine=ENGINE_MSSQL,
        host="localhost",
        instance="SQLEXPRESS",
        database="PipeAgent",
        windows_auth=True,
        driver="ODBC Driver 17 for SQL Server",
    )
    trusted_url = build_url(trusted)
    assert "trusted_connection" in trusted_url.lower()
    assert describe_database_target(trusted_url).startswith("SQL Server")


def test_env_url_overrides_saved_profile(tmp_path):
    profile_path = tmp_path / "pipeagent.connection.json"
    profile_path.write_text(
        '{"engine":"postgresql","host":"ignored","database":"ignored","username":"x"}',
        encoding="utf-8",
    )
    url = resolve_database_url(
        env_url="postgresql+psycopg://locked@host/prod",
        profile_path=profile_path,
        sqlite_path=tmp_path / "pipeagent.db",
    )
    assert url == "postgresql+psycopg://locked@host/prod"


def test_saved_profile_beats_sqlite_default(tmp_path):
    from db.connection_profiles import save_profile

    profile_path = tmp_path / "pipeagent.connection.json"
    save_profile(
        profile_path,
        ConnectionProfile(
            engine=ENGINE_POSTGRESQL,
            host="10.0.0.8",
            port="5432",
            database="site",
            username="pipeagent",
            password="n",
        ),
    )
    url = resolve_database_url(
        env_url="",
        profile_path=profile_path,
        sqlite_path=tmp_path / "pipeagent.db",
    )
    assert "10.0.0.8" in url
    assert url.startswith("postgresql+psycopg://")


def test_schema_patch_ddl_for_sql_server():
    ddl = DatabaseManager._patch_column_ddl("BOOLEAN DEFAULT 0", "mssql")
    assert "BIT" in ddl
    pg = DatabaseManager._patch_column_ddl("BOOLEAN DEFAULT 0", "postgresql")
    assert "FALSE" in pg


def test_sqlite_default_when_no_profile(tmp_path):
    url = resolve_database_url(
        env_url="",
        profile_path=tmp_path / "missing.json",
        sqlite_path=tmp_path / "pipeagent.db",
    )
    assert url.startswith("sqlite:///")
    assert describe_database_target(url).startswith("SQLite")
