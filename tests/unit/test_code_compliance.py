# -*- coding: utf-8 -*-
"""ASME B31.3 NDE lot selection, hydro clearance and QW-322 continuity."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from api_server import create_app
from db.models import (
    LineListItem,
    NDTRecord,
    PunchItem,
    TestPackage as HydroTestPackage,
    TestPackageWeld as HydroTestPackageWeld,
    Weld,
    Welder,
)
from services.api_security import ApiSecurity
from services.code_compliance import CodeComplianceService, nps_inches
from services.rule_engine import PipingRuleEngine
from tests.helpers import make_db, seed_project


def test_nps_inches_parses_dn_and_quoted_size():
    assert nps_inches('6"') == 6.0
    assert nps_inches("DN150") == 5.906


def _seed_line_and_welds(db, project_id: int, *, rejected: bool = False):
    with db.session_scope() as session:
        session.add(
            LineListItem(
                project_id=project_id,
                line_number="10-P-001",
                ndt_percent_rt=10.0,
                ndt_percent_ut=0,
                ndt_percent_pt=0,
                ndt_percent_mt=0,
            )
        )
        welds = []
        for index in range(10):
            weld = Weld(
                project_id=project_id,
                weld_id=f"W-{index:03d}",
                line_number="10-P-001",
                status="Welded",
                size_nps="6",
                welder_id="A-12",
            )
            session.add(weld)
            welds.append(weld)
        session.flush()
        if rejected:
            session.add(
                NDTRecord(
                    weld_id=welds[0].id,
                    ndt_method="RT",
                    result="Fail",
                    is_penalty=False,
                )
            )
        return [weld.id for weld in welds]


def test_coverage_deficit_and_deterministic_lot(db_manager):
    project_id = seed_project(db_manager, "NDE-01", "NDE Project")
    _seed_line_and_welds(db_manager, project_id)
    service = CodeComplianceService(db_manager)
    coverage = service.project_coverage(project_id)
    assert coverage["compliant"] is False
    assert coverage["deficit_lines"] == ["10-P-001"]
    lots = service.nde_lots(project_id)
    assert lots["selected_count"] == 1
    assert lots["selected"][0]["method"] == "RT"
    assert lots["selected"][0]["reason"] == "coverage_percent"
    again = service.nde_lots(project_id)
    assert [row["weld_number"] for row in again["selected"]] == [
        row["weld_number"] for row in lots["selected"]
    ]


def test_rejected_spot_exam_adds_progressive_extras(db_manager):
    project_id = seed_project(db_manager, "NDE-02", "Progressive")
    _seed_line_and_welds(db_manager, project_id, rejected=True)
    lots = CodeComplianceService(db_manager).nde_lots(project_id)
    reasons = {row["reason"] for row in lots["selected"]}
    assert "progressive_extra" in reasons
    extras = [row for row in lots["selected"] if row["reason"] == "progressive_extra"]
    assert len(extras) == 2
    assert all(row["welder_id"] == "A-12" for row in extras)


def test_hydrotest_blocked_by_punch_and_clears_when_empty(db_manager):
    project_id = seed_project(db_manager, "HYD-01", "Hydro")
    with db_manager.session_scope() as session:
        weld = Weld(
            project_id=project_id,
            weld_id="W-100",
            line_number="10-P-100",
            status="NDT_CLEARED",
            size_nps="4",
        )
        session.add(weld)
        session.flush()
        session.add(
            LineListItem(
                project_id=project_id,
                line_number="10-P-100",
                ndt_percent_rt=0,
            )
        )
        session.add(
            NDTRecord(weld_id=weld.id, ndt_method="RT", result="Pass")
        )
        package = HydroTestPackage(
            project_id=project_id,
            package_number="TP-100",
            line_numbers="10-P-100",
        )
        session.add(package)
        session.flush()
        session.add(HydroTestPackageWeld(test_package_id=package.id, weld_id=weld.id))
        session.add(
            PunchItem(
                project_id=project_id,
                test_package_id=package.id,
                category="A",
                description="Missing vent",
                is_cleared=False,
                status="Open",
            )
        )
        package_id = package.id

    blocked = CodeComplianceService(db_manager).hydrotest_clearance(package_id)
    assert blocked["can_proceed"] is False
    assert any("Category-A" in item for item in blocked["blockers"])

    session = db_manager.get_session()
    try:
        ok, messages = PipingRuleEngine.can_proceed_to_hydrotest(package_id, session)
        assert ok is False
        assert messages
    finally:
        session.close()

    with db_manager.session_scope() as session:
        punch = session.query(PunchItem).one()
        punch.is_cleared = True
        punch.status = "Closed"

    cleared = CodeComplianceService(db_manager).hydrotest_clearance(package_id)
    assert cleared["can_proceed"] is True


def test_welder_continuity_warning_window(db_manager):
    project_id = seed_project(db_manager, "WPQ-01", "Continuity")
    idle_since = date.today() - timedelta(days=160)
    with db_manager.session_scope() as session:
        session.add(
            Welder(
                project_id=project_id,
                stencil_no="B-09",
                full_name="Idle Welder",
                last_welded_date=idle_since,
                is_active=True,
            )
        )
    report = CodeComplianceService(db_manager).welder_continuity(project_id)
    assert report["at_risk"]
    assert report["at_risk"][0]["stencil_number"] == "B-09"
    assert report["at_risk"][0]["status"] == "warning"


def test_execution_brief_and_api(tmp_path):
    db = make_db(tmp_path / "brief.db")
    project_id = seed_project(db, "BRF-01", "Brief")
    _seed_line_and_welds(db, project_id)
    brief = CodeComplianceService(db).execution_brief(project_id)
    titles = {item["title"] for item in brief["next_actions"]}
    assert "Issue today's NDE lot" in titles or "Line-list NDE percent is not met" in titles

    client = TestClient(create_app(db))
    token = ApiSecurity(db).issue_key("qc", ["quality:read", "execution:read"])["token"]
    coverage = client.get(
        f"/api/v1/projects/{project_id}/compliance/nde-coverage",
        headers={"x-api-key": token},
    )
    assert coverage.status_code == 200
    assert coverage.json()["compliant"] is False
    lots = client.get(
        f"/api/v1/projects/{project_id}/compliance/nde-lots",
        headers={"x-api-key": token},
    )
    assert lots.status_code == 200
    assert lots.json()["selected_count"] >= 1
    brief_resp = client.get(
        f"/api/v1/projects/{project_id}/compliance/execution-brief",
        headers={"x-api-key": token},
    )
    assert brief_resp.status_code == 200
    assert brief_resp.json()["advisory"] is True
