from repositories.project_repository import ProjectRepository, ProjectStatus


def test_initialize_memory_sqlite_and_connection(db_manager):
    assert db_manager._initialized is True
    assert db_manager._is_initialized is True
    assert db_manager.test_connection() is True
    assert db_manager.engine is not None
    assert db_manager.SessionLocal is not None


def test_bootstrap_admin_exists_on_sqlite(db_manager):
    admin = db_manager.get_user_by_username("admin")
    assert admin is not None
    assert admin.role == "admin"
    assert admin.is_active is True


def test_project_status_roundtrip(db_manager):
    repo = ProjectRepository(db_manager)
    project = repo.create_project(
        "ST-01",
        "Status Project",
        "Client Co",
        project_type=None,
    )
    assert project.status == ProjectStatus.PLANNING.value
    updated = repo.update_status(project.id, ProjectStatus.ACTIVE, "tester")
    assert updated is not None
    fetched = repo.get_by_code("ST-01")
    assert fetched is not None
    assert fetched.status == ProjectStatus.ACTIVE.value
