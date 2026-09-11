from security.hashing import hash_password, verify_password, validate_password_strength
from services.auth.service import AuthService
from services.api_security import ApiSecurity
from tests.helpers import make_db, seed_project


def test_password_roundtrip_and_policy():
    hashed = hash_password("CorrectHorse9")
    assert hashed != "CorrectHorse9"
    assert verify_password("CorrectHorse9", hashed)
    assert not verify_password("wrong", hashed)
    ok, errors = validate_password_strength("short")
    assert ok is False and errors


def test_authenticate_and_lockout(db_manager):
    db_manager.create_user("qa.user", "ValidPass1", role="engineer", full_name="QA User")
    auth = AuthService(db_manager)

    ok, user, message = auth.authenticate("qa.user", "ValidPass1")
    assert ok and user is not None
    assert "successful" in message.lower()

    for _ in range(5):
        failed, _, _ = auth.authenticate("qa.user", "bad-password")
        assert failed is False

    locked, _, lock_message = auth.authenticate("qa.user", "ValidPass1")
    assert locked is False
    assert "locked" in lock_message.lower()


def test_change_password_is_persisted(db_manager):
    created = db_manager.create_user("changer", "OldPass12", role="viewer")
    auth = AuthService(db_manager)
    ok, message = auth.change_password(created, "OldPass12", "NewPass34")
    assert ok, message
    ok, user, _ = auth.authenticate("changer", "NewPass34")
    assert ok and user is not None
    ok, _, _ = auth.authenticate("changer", "OldPass12")
    assert ok is False


def test_api_key_scope_and_project_isolation(tmp_path):
    db = make_db(tmp_path / "keys.db")
    project_a = seed_project(db, "ISO-A", "Isolation A")
    project_b = seed_project(db, "ISO-B", "Isolation B")
    issued = ApiSecurity(db).issue_key("field", ["field:sync"], project_id=project_a)
    assert ApiSecurity(db).verify(issued["token"], "field:sync", project_a)
    assert not ApiSecurity(db).verify(issued["token"], "telemetry:write", project_a)
    assert not ApiSecurity(db).verify(issued["token"], "field:sync", project_b)
