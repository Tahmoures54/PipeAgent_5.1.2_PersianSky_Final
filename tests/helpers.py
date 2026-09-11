# -*- coding: utf-8 -*-
"""Shared factories for PipeAgent tests."""

from __future__ import annotations

from pathlib import Path

from db.manager import DatabaseManager
from db.models import Project


def make_db(path: Path | None = None) -> DatabaseManager:
    """Create an initialized DatabaseManager for tests."""
    url = f"sqlite:///{path}" if path else "sqlite://"
    db = DatabaseManager(url)
    assert db.initialize()
    return db


def seed_project(db: DatabaseManager, code: str = "T-001", title: str = "Test Project") -> int:
    with db.session_scope() as session:
        project = Project(project_code=code, title=title, status="ACTIVE")
        session.add(project)
        session.flush()
        return project.id
