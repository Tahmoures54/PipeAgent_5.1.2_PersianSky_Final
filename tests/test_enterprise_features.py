from datetime import datetime

from services.api_security import ApiSecurity
from services.field_sync_service import FieldSyncService
from services.telemetry_service import WeldingTelemetryService
from services.predictive_control import PredictiveConstructionControl
from tests.helpers import make_db, seed_project


def test_scoped_api_key_and_sync(tmp_path):
    db = make_db(tmp_path / "enterprise.db")
    project_id = seed_project(db, "E-07", "Enterprise Sync")
    key = ApiSecurity(db).issue_key("field", ["field:sync"], project_id=project_id)
    assert ApiSecurity(db).verify(key["token"], "field:sync", project_id)
    assert not ApiSecurity(db).verify(key["token"], "telemetry:write", project_id)
    result = FieldSyncService(db).ingest_batch(
        project_id,
        "D-01",
        "B-01",
        [{
            "event_uuid": "E-1",
            "event_type": "WELD",
            "entity_type": "Weld",
            "entity_id": 1,
            "payload": {"status": "Welded"},
        }],
    )
    assert result["accepted"] == 1 and result["receipts"][0]["status"] == "Accepted"


def test_telemetry_is_idempotent(tmp_path):
    db = make_db(tmp_path / "telemetry.db")
    project_id = seed_project(db, "TEL-01", "Telemetry")
    svc = WeldingTelemetryService(db)
    payload = {
        "idempotency_key": "T-1",
        "machine_id": "WM-01",
        "started_at": datetime.utcnow().isoformat(),
        "parameter_deviation_pct": 20,
    }
    first = svc.ingest(project_id, payload)
    second = svc.ingest(project_id, payload)
    summary = svc.summary(project_id)
    assert first == second and summary["samples"] == 1 and summary["deviations"] == 1


def test_prediction_run_persists_history(tmp_path):
    db = make_db(tmp_path / "predict.db")
    project_id = seed_project(db, "PRD-01", "Predict")
    first = PredictiveConstructionControl(db).run(project_id)
    assert "data_quality_score" in first
    PredictiveConstructionControl(db).run(project_id)
    with db.session_scope() as session:
        from db.models import PredictionRun, PredictionObservation
        assert session.query(PredictionRun).count() == 2
        assert session.query(PredictionObservation).count() >= 16
