# -*- coding: utf-8 -*-
"""Pytest fixtures for PipeAgent tests."""

import pytest

from tests.helpers import make_db


@pytest.fixture(scope="function")
def db_manager():
    """Provide a DatabaseManager connected to an isolated SQLite database."""
    db = make_db()
    yield db
    db.close()


@pytest.fixture(scope="function")
def session(db_manager):
    """Return a fresh session, automatically rolled back after test."""
    session = db_manager.get_session()
    yield session
    session.rollback()
    session.close()
