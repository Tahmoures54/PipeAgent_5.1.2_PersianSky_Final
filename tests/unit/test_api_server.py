from fastapi.testclient import TestClient

from api_server import create_app
from db.models import Project
from services.api_security import ApiSecurity
from tests.helpers import make_db


def _client(tmp_path):
    db = make_db(tmp_path / "api.db")
    return TestClient(create_app(db)), db


def test_health_endpoint(tmp_path):
    client, _ = _client(tmp_path)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert "version" in body


def test_projects_require_credentials(tmp_path):
    client, _ = _client(tmp_path)
    response = client.get("/api/v1/projects")
    assert response.status_code == 401


def test_scoped_api_key_can_list_projects_and_is_not_stored_in_plaintext(tmp_path):
    client, db = _client(tmp_path)
    with db.session_scope() as session:
        session.add(Project(project_code="API-01", title="API Project", status="ACTIVE"))

    issued = ApiSecurity(db).issue_key("reader", ["projects:read"])
    token = issued["token"]
    assert "_REDACTED" not in token

    with db.session_scope() as session:
        from db.models import ApiCredential
        stored = session.query(ApiCredential).filter_by(id=issued["id"]).one()
        assert stored.api_key != token
        assert stored.token_hash
        assert token not in (stored.api_key or "")

    response = client.get("/api/v1/projects", headers={"x-api-key": token})
    assert response.status_code == 200
    codes = {row["code"] for row in response.json()}
    assert "API-01" in codes


def test_wrong_scope_is_rejected(tmp_path):
    client, db = _client(tmp_path)
    issued = ApiSecurity(db).issue_key("field", ["field:sync"])
    response = client.get("/api/v1/projects", headers={"x-api-key": issued["token"]})
    assert response.status_code == 401


def test_ifc_inventory_rejects_path_escape(tmp_path):
    client, db = _client(tmp_path)
    issued = ApiSecurity(db).issue_key("bim", ["execution:read"])
    response = client.post(
        "/api/v1/bim/ifc/inventory",
        params={"path": "/etc/passwd"},
        headers={"x-api-key": issued["token"]},
    )
    assert response.status_code == 400
