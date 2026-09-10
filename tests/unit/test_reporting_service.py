from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Project, Weld, WeldReportDraft, FitupReportDraft
from db.manager import DatabaseManager
from services.reporting_service import ReportingService


def make_db():
    db = DatabaseManager("sqlite:///:memory:")
    db.engine = create_engine("sqlite:///:memory:")
    # A single connection is required for an in-memory SQLite database.
    from sqlalchemy.pool import StaticPool
    db.engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(db.engine)
    db.SessionLocal = sessionmaker(bind=db.engine, expire_on_commit=False)
    db._is_initialized = True
    return db


def test_weld_draft_html_contains_business_control(tmp_path, monkeypatch):
    db = make_db()
    with db.session_scope() as s:
        p = Project(project_code="P-TEST", title="Test Project")
        s.add(p); s.flush()
        w = Weld(project_id=p.id, weld_id="W-001", weld_type="Field", status="Welded", line_number="10-P-001")
        s.add(w); s.flush()
        d = WeldReportDraft(
            report_no="WR-001", project_id=p.id, weld_pk=w.id, line_number="10-P-001",
            weld_no="W-001", welder_name="John Doe", weld_date=date.today(),
            process="GTAW", visual_result="Pending", prepared_by="engineer"
        )
        s.add(d); s.flush(); did = d.id
    svc = ReportingService(db)
    path = svc.export_report_html("weld", did, official=False)
    text = open(path, encoding="utf-8").read()
    assert "DRAFT — NOT FOR CONSTRUCTION" in text
    assert "Welding Report" in text
    assert "WR-001" in text


def test_smart_hints_detect_ndt_backlog_and_repair_trend():
    db = make_db()
    with db.session_scope() as s:
        p = Project(project_code="P-HINT", title="Hint Project")
        s.add(p); s.flush()
        for i in range(10):
            s.add(Weld(project_id=p.id, weld_id=f"W-{i:03d}", status="Welded", repair_count=1 if i < 2 else 0))
    hints = ReportingService(db).smart_hints(1)
    titles = {h["title"] for h in hints}
    assert "NDT backlog needs attention" in titles or "NDT queue is becoming a production constraint" in titles
    assert "Repair trend deserves review" in titles or "Repair rate is above the control threshold" in titles
