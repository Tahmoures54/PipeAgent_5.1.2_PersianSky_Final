from db.models import Project, LineListItem, WorkFront, Weld, ExecutionEvent
from services.execution_event_bridge import install
from services.execution_os import ExecutionOSService
from tests.helpers import make_db


def _db():
    db = make_db()
    install()
    return db


def test_business_change_becomes_persistent_event_and_forecast():
    db=_db()
    with db.session_scope() as s:
        p=Project(project_code="EVT-01", title="Event Control")
        s.add(p); s.flush()
        s.add(LineListItem(project_id=p.id,line_number="10-P-100"))
        s.add(WorkFront(project_id=p.id,front_code="WF-100",activity_type="Erection",line_number="10-P-100",status="Ready"))
        s.add(Weld(project_id=p.id,weld_id="W-100",line_number="10-P-100",status="Welded"))
        pid=p.id
    with db.session_scope() as s:
        front=s.query(WorkFront).filter_by(project_id=pid).first()
        front.status="Blocked"
        front.blocker="Crane unavailable"
    with db.session_scope() as s:
        events=s.query(ExecutionEvent).filter_by(project_id=pid).all()
        assert events
        assert any(e.entity_type=="WorkFront" and e.event_type=="UPDATED" for e in events)
    snap=ExecutionOSService(db).snapshot(pid)
    assert snap["persistent_control"]["event_count"] >= 2
    assert snap["persistent_control"]["open_impacts"] >= 1
    assert snap["persistent_control"]["forecasts"]
    assert "Constraint not resolved today may affect downstream execution" in snap["persistent_control"]["forecasts"][0]["title"]
