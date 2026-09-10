import os
from datetime import datetime
from db.manager import DatabaseManager
from db.models import Project, User
from services.api_security import ApiSecurity
from services.field_sync_service import FieldSyncService
from services.telemetry_service import WeldingTelemetryService
from services.document_evidence_service import DocumentEvidenceService
from services.predictive_control import PredictiveConstructionControl


def make_db(tmp_path):
    db=DatabaseManager(f"sqlite:///{tmp_path/'enterprise.db'}")
    assert db.initialize(); return db


def test_scoped_api_key_and_sync(tmp_path):
    db=make_db(tmp_path)
    key=ApiSecurity(db).issue_key('field',['field:sync'],project_id=7)
    assert ApiSecurity(db).verify(key['token'],'field:sync',7)
    assert not ApiSecurity(db).verify(key['token'],'telemetry:write',7)
    result=FieldSyncService(db).ingest_batch(7,'D-01','B-01',[{'event_uuid':'E-1','event_type':'WELD','entity_type':'Weld','entity_id':1,'payload':{'status':'Welded'}}])
    assert result['accepted']==1 and result['receipts'][0]['status']=='Accepted'


def test_telemetry_is_idempotent(tmp_path):
    db=make_db(tmp_path); svc=WeldingTelemetryService(db)
    payload={'idempotency_key':'T-1','machine_id':'WM-01','started_at':datetime.utcnow().isoformat(),'parameter_deviation_pct':20}
    a=svc.ingest(1,payload); b=svc.ingest(1,payload)
    assert a==b and svc.summary(1)['samples']==1 and svc.summary(1)['deviations']==1


def test_prediction_run_persists_history(tmp_path):
    db=make_db(tmp_path)
    r=PredictiveConstructionControl(db).run(1)
    assert 'data_quality_score' in r
    r2=PredictiveConstructionControl(db).run(1)
    with db.session_scope() as s:
        from db.models import PredictionRun, PredictionObservation
        assert s.query(PredictionRun).count()==2
        assert s.query(PredictionObservation).count() >= 16
