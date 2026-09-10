# -*- coding: utf-8 -*-
"""Pytest fixtures for PipeAgent tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base
from db.manager import DatabaseManager

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_manager():
    """Provide a DatabaseManager connected to an in-memory SQLite DB."""
    db = DatabaseManager(database_url=TEST_DB_URL)
    # Override engine creation to keep everything in memory
    db.engine = create_engine(TEST_DB_URL, echo=False)
    Base.metadata.create_all(db.engine)
    db.SessionLocal = sessionmaker(bind=db.engine, expire_on_commit=False)
    db._is_initialized = True
    yield db
    db.close()


@pytest.fixture(scope="function")
def session(db_manager):
    """Return a fresh session, automatically rolled back after test."""
    session = db_manager.get_session()
    transaction = session.begin_nested()   # SAVEPOINT
    yield session
    session.rollback()                     # discard changes
    session.close()