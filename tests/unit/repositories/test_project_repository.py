# -*- coding: utf-8 -*-
import pytest
from db.models import Project
from repositories.project_repository import ProjectRepository


def test_create_project(db_manager):
    repo = ProjectRepository(db_manager)
    proj = Project(project_code="TST01", title="Test Project")
    saved = repo.create(proj)
    assert saved.id is not None
    assert saved.project_code == "TST01"


def test_get_by_code(db_manager):
    repo = ProjectRepository(db_manager)
    proj = Project(project_code="TST02", title="Another Test")
    repo.create(proj)

    fetched = repo.get_by_code("TST02")
    assert fetched is not None
    assert fetched.title == "Another Test"

    not_found = repo.get_by_code("NONEXIST")
    assert not_found is None