# -*- coding: utf-8 -*-
"""Management HTML analytics by unit, contractor, material and service."""

from pathlib import Path

from db.models import Area, LineListItem, NDTRecord, Project, PunchItem, Weld
from db.models import TestPackage as HydroTestPackage
from services.management_analytics import (
    SLICE_SPECS,
    build_management_snapshot,
    nps_to_dia_inch,
    write_management_pack,
)
from services.reporting_service import ReportingService
from tests.helpers import make_db


def test_nps_to_dia_inch_parses_fractions_and_text():
    assert nps_to_dia_inch("6") == 6.0
    assert nps_to_dia_inch('2"') == 2.0
    assert nps_to_dia_inch("1-1/2") == 1.5
    assert nps_to_dia_inch("3/4") == 0.75
    assert nps_to_dia_inch("NPS 10") == 10.0
    assert nps_to_dia_inch(None) == 0.0
    assert nps_to_dia_inch("") == 0.0


def _seed_project(db):
    with db.session_scope() as session:
        project = Project(
            project_code="P-MGMT",
            title="Management Sample",
            client="Owner Co",
            contractor="Main EPC",
            status="ACTIVE",
        )
        session.add(project)
        session.flush()
        pid = project.id
        a101 = Area(project_id=pid, name="U-101")
        a102 = Area(project_id=pid, name="U-102")
        session.add_all([a101, a102])
        session.flush()
        session.add_all(
            [
                LineListItem(
                    project_id=pid,
                    area_id=a101.id,
                    line_number="10-HC-001",
                    fluid_service="HC",
                    material="A106-B",
                    pipe_class="150#",
                    size_nps="6",
                ),
                LineListItem(
                    project_id=pid,
                    area_id=a102.id,
                    line_number="20-ST-001",
                    fluid_service="Steam",
                    material="A312-TP316",
                    pipe_class="300#",
                    size_nps="4",
                ),
            ]
        )
        welds = []
        for i in range(4):
            welds.append(
                Weld(
                    project_id=pid,
                    area_id=a101.id,
                    area_name="U-101",
                    weld_number=f"MG-101-{i:03d}",
                    line_number="10-HC-001",
                    status="NDT_CLEARED",
                    size_nps="6",
                    base_material="A106-B",
                    line_service="HC",
                    pipe_class="150#",
                    contractor="ShopCo",
                    weld_type="Shop",
                    repair_count=0,
                )
            )
        for i in range(4):
            welds.append(
                Weld(
                    project_id=pid,
                    area_id=a102.id,
                    area_name="U-102",
                    weld_number=f"MG-102-{i:03d}",
                    line_number="20-ST-001",
                    status="WELDED",
                    size_nps="4",
                    base_material="A312-TP316",
                    line_service="Steam",
                    pipe_class="300#",
                    contractor="FieldCo",
                    weld_type="Field",
                    repair_count=1 if i < 2 else 0,
                )
            )
        session.add_all(welds)
        session.flush()
        session.add(
            NDTRecord(
                weld_id=welds[0].id,
                ndt_method="RT",
                result="Pass",
            )
        )
        session.add(
            NDTRecord(
                weld_id=welds[5].id,
                ndt_method="RT",
                result="Fail",
            )
        )
        session.add(
            HydroTestPackage(
                project_id=pid,
                area_id=a102.id,
                area_name="U-102",
                package_number="TP-MGMT-102",
                status="READY_FOR_TEST",
                punch_a_count=2,
                punch_b_count=1,
            )
        )
        session.add(
            PunchItem(
                project_id=pid,
                line_number="20-ST-001",
                category="A",
                description="Missing support",
                is_cleared=False,
                status="Open",
            )
        )
        return pid


def test_management_snapshot_groups_unit_contractor_material_service():
    db = make_db()
    pid = _seed_project(db)
    snap = build_management_snapshot(db, pid)
    units = {row["label"]: row for row in snap["groups"]["by_unit"]}
    assert units["U-101"]["welds"] == 4
    assert units["U-101"]["accepted"] == 4
    assert units["U-102"]["awaiting_ndt"] == 4
    assert units["U-101"]["dia_inch"] == 24.0
    contractors = {row["label"]: row for row in snap["groups"]["by_contractor"]}
    assert contractors["ShopCo"]["progress_pct"] == 100.0
    assert contractors["FieldCo"]["repair_pct"] == 50.0
    materials = {row["label"] for row in snap["groups"]["by_material"]}
    assert "A106-B" in materials
    assert "A312-TP316" in materials
    services = {row["label"] for row in snap["groups"]["by_service"]}
    assert "HC" in services
    assert "Steam" in services
    titles = {item["title"] for item in snap["findings"]}
    assert any("U-102" in title for title in titles)
    assert any("FieldCo" in title for title in titles)
    assert any("A" in title or "punch" in title.lower() for title in titles)


def test_management_html_pack_writes_slices(tmp_path):
    db = make_db()
    pid = _seed_project(db)
    snap = build_management_snapshot(db, pid)
    svc = ReportingService(db)
    index = Path(
        write_management_pack(svc._html_shell, pid, snap, export_dir=tmp_path)
    )
    assert index.name == "index.html"
    text = index.read_text(encoding="utf-8")
    assert "Management Analytics Pack" in text
    assert "U-101" in text
    assert "ShopCo" in text
    assert "A106-B" in text
    assert "Steam" in text
    assert "not a construction or QC acceptance document" in text
    for key, title, _blurb in SLICE_SPECS:
        path = index.parent / f"{key}.html"
        assert path.is_file(), key
        body = path.read_text(encoding="utf-8")
        assert title.split("/")[0].strip() in body or title in body
        assert "PipeAgent" in body


def test_analytics_keys_work_for_dashboard_and_executive(tmp_path, monkeypatch):
    db = make_db()
    pid = _seed_project(db)
    monkeypatch.setattr("services.reporting_service.EXPORT_DIR", tmp_path)
    svc = ReportingService(db)
    stats = svc.analytics(pid)
    welds = stats["welds"]
    assert welds["total"] == 8
    assert "acceptance_rate_pct" in welds
    assert "rejection_rate_pct" in welds
    assert welds["completed_dia_inch"] == welds["accepted_dia_inch"]
    assert stats["spools"]["installed"] == stats["spools"]["installed_erected"]
    assert stats["lines"] == stats["lines_count"]
    assert "by_welder" in stats
    path = Path(svc.project_executive_html(pid))
    html = path.read_text(encoding="utf-8")
    assert "Project Executive Report" in html
    assert "P-MGMT" in html


def test_empty_project_management_pack(tmp_path):
    db = make_db()
    with db.session_scope() as session:
        project = Project(project_code="P-EMPTY", title="Empty")
        session.add(project)
        session.flush()
        pid = project.id
    snap = build_management_snapshot(db, pid)
    assert snap["totals"]["welds"] == 0
    svc = ReportingService(db)
    index = Path(write_management_pack(svc._html_shell, pid, snap, export_dir=tmp_path))
    assert "No weld register yet" in index.read_text(encoding="utf-8")
