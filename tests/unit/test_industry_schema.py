# -*- coding: utf-8 -*-
"""Industry naming: physical columns, legacy synonyms, and SQLite upgrades."""

from __future__ import annotations

import sqlite3

from sqlalchemy import inspect, text

from db.manager import DatabaseManager
from db.models import (
    Document,
    LineListItem,
    MaterialTakeOff,
    NDTRecord,
    PipeSupport,
    PunchItem,
    TestPackage as HydroTestPackage,
    Weld,
    WeldReportDraft,
    Welder,
    WorkFront,
)
from tests.helpers import seed_project


def _column_names(engine, table: str) -> set[str]:
    return {col["name"] for col in inspect(engine).get_columns(table)}


def test_fresh_schema_uses_industry_column_names(db_manager):
    weld_cols = _column_names(db_manager.engine, "welds")
    assert "weld_number" in weld_cols
    assert "size_nps" in weld_cols
    assert "heat_number_filler" in weld_cols
    assert "welding_process" in weld_cols
    assert "vt_result" in weld_cols
    assert "base_material" in weld_cols
    assert "welder_stencil_number" in weld_cols
    assert "ndt_extent_rt_pct" in weld_cols
    assert "is_on_hold" in weld_cols
    assert "pwht_completed" in weld_cols
    assert "left_quantity" in weld_cols
    assert "weld_id" not in weld_cols
    assert "size" not in weld_cols
    assert "material" not in weld_cols
    assert "welder_id" not in weld_cols
    assert "ndt_percent_rt" not in weld_cols
    assert "hold" not in weld_cols

    ndt_cols = _column_names(db_manager.engine, "ndt_records")
    assert "weld_id" in ndt_cols
    assert "inspector_stamp" in ndt_cols
    assert "weld_id_fk" not in ndt_cols
    assert "inspector_id" not in ndt_cols
    assert "procedure_number" in ndt_cols
    assert "acceptance_standard" in ndt_cols

    line_cols = _column_names(db_manager.engine, "line_list")
    assert "corrosion_allowance_mm" in line_cols
    assert "ndt_extent_pt_pct" in line_cols
    assert "size_dn" in line_cols
    assert "sour_service" in line_cols
    assert "pcf_number" in line_cols
    assert "ndt_percent_pt" not in line_cols
    assert "dn" not in line_cols

    pack_cols = _column_names(db_manager.engine, "test_packages")
    assert "test_pressure_barg" in pack_cols
    assert "design_pressure_barg" in pack_cols
    assert "line_check_finished" in pack_cols
    assert "inch_metre" in pack_cols
    assert "dia_inch" in pack_cols
    assert "test_pressure_bar" not in pack_cols
    assert "linecheck_finished" not in pack_cols
    assert "inch_meter" not in pack_cols

    doc_cols = _column_names(db_manager.engine, "documents")
    assert "document_number" in doc_cols
    assert "document_type" in doc_cols
    assert "document_class" in doc_cols
    assert "doc_number" not in doc_cols
    assert "doc_type" not in doc_cols

    project_cols = _column_names(db_manager.engine, "projects")
    assert "contract_number" in project_cols
    assert "site_location" in project_cols

    mto_cols = _column_names(db_manager.engine, "material_takeoff")
    assert "two_year_quantity" in mto_cols
    assert "purchase_quantity" in mto_cols
    assert "miv_quantity" in mto_cols
    assert "two_year_qty" not in mto_cols

    support_cols = _column_names(db_manager.engine, "pipe_supports")
    assert "base_material" in support_cols
    assert "support_subtype" in support_cols
    assert "location_description" in support_cols
    assert "base_metal" not in support_cols
    assert "type_2" not in support_cols
    assert "location_desc" not in support_cols

    front_cols = _column_names(db_manager.engine, "work_fronts")
    assert "target_quantity" in front_cols
    assert "actual_quantity" in front_cols
    assert "target_qty" not in front_cols
    assert "actual_qty" not in front_cols

    punch_cols = _column_names(db_manager.engine, "punch_items")
    assert "location_description" in punch_cols
    assert "location_desc" not in punch_cols

    company_cols = _column_names(db_manager.engine, "companies")
    assert "logo_file_path" in company_cols
    assert "logo_path" not in company_cols


def test_legacy_python_names_still_roundtrip(db_manager):
    project_id = seed_project(db_manager, "SCH-01", "Schema Project")
    with db_manager.session_scope() as session:
        weld = Weld(
            project_id=project_id,
            weld_id="W-001",
            weld_type="Field",
            status="Welded",
            size="6",
            filler_heat_no="H-FILL-1",
        )
        session.add(weld)
        session.flush()
        assert weld.weld_number == "W-001"
        assert weld.joint_number == "W-001"
        assert weld.size_nps == "6"
        assert weld.dia_inch == "6"
        assert weld.heat_number_filler == "H-FILL-1"
        weld.welder_id = "A-12"
        weld.material = "A106 Gr.B"
        weld.hold = True
        weld.ndt_percent_rt = 10
        session.flush()
        assert weld.welder_stencil_number == "A-12"
        assert weld.base_material == "A106 Gr.B"
        assert weld.base_metal == "A106 Gr.B"
        assert weld.is_on_hold is True
        assert weld.ndt_extent_rt_pct == 10

        ndt = NDTRecord(
            weld_id_fk=weld.id,
            ndt_method="RT",
            result="Accept",
            procedure_number="NDT-RT-01",
            acceptance_standard="ASME B31.3",
        )
        session.add(ndt)
        session.flush()
        assert ndt.weld_id == weld.id

        line = LineListItem(
            project_id=project_id,
            line_number="10-P-001-6\"-A1",
            pid_number="P&ID-001",
            pipe_class="A1",
            from_point="V-101",
            corrosion_allowance_mm=1.5,
            sour_service=True,
        )
        session.add(line)
        session.flush()
        assert line.pandid_number == "P&ID-001"
        assert line.line_class == "A1"
        assert line.from_equipment == "V-101"

        package = HydroTestPackage(
            project_id=project_id,
            package_number="TP-001",
            design_pressure_bar=12.5,
            test_pressure_bar=18.75,
        )
        session.add(package)
        session.flush()
        assert package.design_pressure_barg == 12.5
        assert package.test_pressure_barg == 18.75

        welder = Welder(
            project_id=project_id,
            stencil_no="A-12",
            full_name="Jane Welder",
            certificate_no="WPQ-001",
            last_welded_date=None,
        )
        session.add(welder)
        session.flush()
        assert welder.stencil_number == "A-12"
        assert welder.certificate_number == "WPQ-001"

        draft = WeldReportDraft(
            report_no="WR-001",
            project_id=project_id,
            weld_pk=weld.id,
            weld_no="W-001",
            spool_no="SP-001",
        )
        session.add(draft)
        session.flush()
        assert draft.report_number == "WR-001"
        assert draft.weld_id == weld.id
        assert draft.weld_number == "W-001"
        assert draft.spool_number == "SP-001"

        support = PipeSupport(
            project_id=project_id,
            support_tag="PS-1",
            base_metal="A36",
            type_2="Guide",
            location_desc="EL +12.5",
        )
        session.add(support)
        session.flush()
        assert support.base_material == "A36"
        assert support.support_subtype == "Guide"
        assert support.location_description == "EL +12.5"

        front = WorkFront(
            project_id=project_id,
            front_code="WF-01",
            activity_type="Welding",
            target_qty=10,
            actual_qty=4,
        )
        session.add(front)
        session.flush()
        assert front.target_quantity == 10
        assert front.actual_quantity == 4

        punch = PunchItem(
            project_id=project_id,
            category="A",
            description="Missing support",
            location_desc="Unit 100",
        )
        session.add(punch)
        session.flush()
        assert punch.location_description == "Unit 100"

        takeoff = MaterialTakeOff(
            project_id=project_id,
            material_type="Elbow",
            two_year_qty=2,
            purchase_qty=8,
            miv_qty=3,
        )
        session.add(takeoff)
        session.flush()
        assert takeoff.two_year_quantity == 2
        assert takeoff.purchase_quantity == 8
        assert takeoff.miv_quantity == 3

        document = Document(
            project_id=project_id,
            doc_number="ISO-9",
            doc_type="Isometric",
        )
        session.add(document)
        session.flush()
        assert document.document_number == "ISO-9"
        assert document.document_type == "Isometric"


def test_ndt_synonym_is_queryable(db_manager):
    project_id = seed_project(db_manager, "SCH-02", "NDT Schema")
    with db_manager.session_scope() as session:
        weld = Weld(project_id=project_id, weld_id="W-010", status="Welded")
        session.add(weld)
        session.flush()
        session.add(NDTRecord(weld_id_fk=weld.id, ndt_method="PT", result="Accept"))
        session.flush()
        found = (
            session.query(NDTRecord)
            .filter(NDTRecord.weld_id_fk == weld.id)
            .one()
        )
        assert found.weld_id == weld.id
        by_number = session.query(Weld).filter(Weld.weld_id == "W-010").one()
        assert by_number.id == weld.id


def test_legacy_sqlite_file_renames_weld_id(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE welds (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            weld_id VARCHAR(100) NOT NULL,
            size VARCHAR(50)
        )
        """
    )
    conn.execute(
        "INSERT INTO welds (id, project_id, weld_id, size) VALUES (1, 1, 'W-001', '6')"
    )
    conn.execute(
        """
        CREATE TABLE ndt_records (
            id INTEGER PRIMARY KEY,
            weld_id_fk INTEGER NOT NULL,
            ndt_method VARCHAR(10) NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO ndt_records (id, weld_id_fk, ndt_method) VALUES (1, 1, 'RT')"
    )
    conn.commit()
    conn.close()

    db = DatabaseManager(f"sqlite:///{db_path}")
    assert db.initialize() is True

    weld_cols = _column_names(db.engine, "welds")
    assert "weld_number" in weld_cols
    assert "size_nps" in weld_cols
    assert "welding_process" in weld_cols
    assert "weld_id" not in weld_cols
    assert "size" not in weld_cols

    ndt_cols = _column_names(db.engine, "ndt_records")
    assert "weld_id" in ndt_cols
    assert "weld_id_fk" not in ndt_cols
    assert "procedure_number" in ndt_cols

    with db.engine.connect() as engine_conn:
        weld_row = engine_conn.execute(
            text("SELECT weld_number, size_nps FROM welds WHERE id = 1")
        ).one()
        assert weld_row[0] == "W-001"
        assert weld_row[1] == "6"
        ndt_row = engine_conn.execute(
            text("SELECT weld_id, ndt_method FROM ndt_records WHERE id = 1")
        ).one()
        assert ndt_row[0] == 1
        assert ndt_row[1] == "RT"


def test_legacy_sqlite_renames_5_2_7_site_columns(tmp_path):
    db_path = tmp_path / "legacy_527.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE welds (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            weld_id VARCHAR(100) NOT NULL,
            material VARCHAR(100),
            welder_id VARCHAR(100),
            ndt_percent_rt FLOAT,
            pwht_done BOOLEAN,
            hold BOOLEAN,
            left_qty FLOAT
        );
        INSERT INTO welds (
            id, project_id, weld_id, material, welder_id,
            ndt_percent_rt, pwht_done, hold, left_qty
        ) VALUES (1, 1, 'W-527', 'A106', 'A-12', 10, 1, 1, 2);

        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            doc_number VARCHAR(100) NOT NULL,
            doc_type VARCHAR(50) NOT NULL
        );
        INSERT INTO documents (id, project_id, doc_number, doc_type)
        VALUES (1, 1, 'ISO-527', 'Isometric');

        CREATE TABLE test_packages (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            package_number VARCHAR(100) NOT NULL,
            linecheck_finished BOOLEAN,
            inch_meter FLOAT,
            dia_inch_total FLOAT
        );
        INSERT INTO test_packages (
            id, project_id, package_number, linecheck_finished, inch_meter, dia_inch_total
        ) VALUES (1, 1, 'TP-527', 1, 12.5, 80);

        CREATE TABLE material_takeoff (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            material_type VARCHAR(100) NOT NULL,
            two_year_qty FLOAT,
            purchase_qty FLOAT,
            miv_qty FLOAT
        );
        INSERT INTO material_takeoff (
            id, project_id, material_type, two_year_qty, purchase_qty, miv_qty
        ) VALUES (1, 1, 'Elbow', 2, 8, 3);

        CREATE TABLE project_actions (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            action_type VARCHAR(80) NOT NULL,
            action_by_1 VARCHAR(100)
        );
        INSERT INTO project_actions (id, project_id, action_type, action_by_1)
        VALUES (1, 1, 'NDT', 'QC-01');

        CREATE TABLE pipe_supports (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            support_tag VARCHAR(100) NOT NULL,
            base_metal VARCHAR(100),
            type_2 VARCHAR(80),
            location_desc VARCHAR(200)
        );
        INSERT INTO pipe_supports (
            id, project_id, support_tag, base_metal, type_2, location_desc
        ) VALUES (1, 1, 'PS-527', 'A36', 'Guide', 'EL +12');

        CREATE TABLE work_fronts (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            front_code VARCHAR(100) NOT NULL,
            activity_type VARCHAR(80) NOT NULL,
            target_qty FLOAT,
            actual_qty FLOAT
        );
        INSERT INTO work_fronts (
            id, project_id, front_code, activity_type, target_qty, actual_qty
        ) VALUES (1, 1, 'WF-527', 'Welding', 10, 4);

        CREATE TABLE companies (
            id INTEGER PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            logo_path VARCHAR(500)
        );
        INSERT INTO companies (id, name, logo_path)
        VALUES (1, 'NOC', '/tmp/logo.png');

        CREATE TABLE punch_items (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            category VARCHAR(10) NOT NULL,
            description TEXT NOT NULL,
            location_desc VARCHAR(300)
        );
        INSERT INTO punch_items (
            id, project_id, category, description, location_desc
        ) VALUES (1, 1, 'A', 'Missing support', 'Unit 100');
        """
    )
    conn.commit()
    conn.close()

    db = DatabaseManager(f"sqlite:///{db_path}")
    assert db.initialize() is True

    weld_cols = _column_names(db.engine, "welds")
    assert "weld_number" in weld_cols
    assert "base_material" in weld_cols
    assert "welder_stencil_number" in weld_cols
    assert "ndt_extent_rt_pct" in weld_cols
    assert "pwht_completed" in weld_cols
    assert "is_on_hold" in weld_cols
    assert "left_quantity" in weld_cols
    assert "material" not in weld_cols
    assert "welder_id" not in weld_cols
    assert "ndt_percent_rt" not in weld_cols

    with db.engine.connect() as engine_conn:
        weld_row = engine_conn.execute(
            text(
                "SELECT weld_number, base_material, welder_stencil_number, "
                "ndt_extent_rt_pct, left_quantity FROM welds WHERE id = 1"
            )
        ).one()
        assert list(weld_row) == ["W-527", "A106", "A-12", 10, 2]
        doc_row = engine_conn.execute(
            text("SELECT document_number, document_type FROM documents WHERE id = 1")
        ).one()
        assert list(doc_row) == ["ISO-527", "Isometric"]
        pack_row = engine_conn.execute(
            text(
                "SELECT line_check_finished, inch_metre, dia_inch "
                "FROM test_packages WHERE id = 1"
            )
        ).one()
        assert pack_row[0] in (1, True)
        assert pack_row[1] == 12.5
        assert pack_row[2] == 80
        mto_row = engine_conn.execute(
            text(
                "SELECT two_year_quantity, purchase_quantity, miv_quantity "
                "FROM material_takeoff WHERE id = 1"
            )
        ).one()
        assert list(mto_row) == [2, 8, 3]
        action_row = engine_conn.execute(
            text("SELECT performed_by_1 FROM project_actions WHERE id = 1")
        ).one()
        assert action_row[0] == "QC-01"
        support_row = engine_conn.execute(
            text(
                "SELECT base_material, support_subtype, location_description "
                "FROM pipe_supports WHERE id = 1"
            )
        ).one()
        assert list(support_row) == ["A36", "Guide", "EL +12"]
        front_row = engine_conn.execute(
            text("SELECT target_quantity, actual_quantity FROM work_fronts WHERE id = 1")
        ).one()
        assert list(front_row) == [10, 4]
        company_row = engine_conn.execute(
            text("SELECT logo_file_path FROM companies WHERE id = 1")
        ).one()
        assert company_row[0] == "/tmp/logo.png"
        punch_row = engine_conn.execute(
            text("SELECT location_description FROM punch_items WHERE id = 1")
        ).one()
        assert punch_row[0] == "Unit 100"
