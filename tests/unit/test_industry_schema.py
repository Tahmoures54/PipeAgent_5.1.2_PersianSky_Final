# -*- coding: utf-8 -*-
"""Industry naming: physical columns, legacy synonyms, and SQLite upgrades."""

from __future__ import annotations

import sqlite3

from sqlalchemy import inspect, text

from db.manager import DatabaseManager
from db.models import (
    LineListItem,
    NDTRecord,
    TestPackage as HydroTestPackage,
    Weld,
    WeldReportDraft,
    Welder,
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
    assert "weld_id" not in weld_cols
    assert "size" not in weld_cols

    ndt_cols = _column_names(db_manager.engine, "ndt_records")
    assert "weld_id" in ndt_cols
    assert "weld_id_fk" not in ndt_cols
    assert "procedure_number" in ndt_cols
    assert "acceptance_standard" in ndt_cols

    line_cols = _column_names(db_manager.engine, "line_list")
    assert "corrosion_allowance_mm" in line_cols
    assert "ndt_percent_pt" in line_cols
    assert "sour_service" in line_cols
    assert "pcf_number" in line_cols

    pack_cols = _column_names(db_manager.engine, "test_packages")
    assert "test_pressure_barg" in pack_cols
    assert "design_pressure_barg" in pack_cols
    assert "test_pressure_bar" not in pack_cols

    project_cols = _column_names(db_manager.engine, "projects")
    assert "contract_number" in project_cols
    assert "site_location" in project_cols


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
