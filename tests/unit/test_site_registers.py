# -*- coding: utf-8 -*-
"""Site execution registers aligned with the Access/SQL joint, DCC, MTO, TQ set."""

from __future__ import annotations

import sqlite3

from sqlalchemy import inspect, text

from db.manager import DatabaseManager
from db.models import (
    Company,
    Document,
    MaterialTakeOff,
    PipeSupport,
    ProjectAction,
    TechnicalQuery,
    TestPackage as HydroTestPackage,
    Weld,
)
from tests.helpers import seed_project


def _column_names(engine, table: str) -> set[str]:
    return {col["name"] for col in inspect(engine).get_columns(table)}


def test_fresh_schema_has_site_register_columns(db_manager):
    weld_cols = _column_names(db_manager.engine, "welds")
    assert "install_location" in weld_cols
    assert "test_package_number" in weld_cols
    assert "left_component" in weld_cols
    assert "is_expired" in weld_cols

    assert "technical_queries" in inspect(db_manager.engine).get_table_names()
    assert "companies" in inspect(db_manager.engine).get_table_names()

    mto_cols = _column_names(db_manager.engine, "material_takeoff")
    assert "miv_number" in mto_cols
    assert "commodity_code" in mto_cols
    assert "thickness_mm" in mto_cols

    support_cols = _column_names(db_manager.engine, "pipe_supports")
    assert "fab_fitup_report_number" in support_cols
    assert "er_weld_report_number" in support_cols
    assert "pt_report_number" in support_cols
    assert "base_material" in support_cols
    assert "support_subtype" in support_cols
    assert "location_description" in support_cols
    assert "base_metal" not in support_cols
    assert "type_2" not in support_cols

    pack_cols = _column_names(db_manager.engine, "test_packages")
    assert "line_check_result" in pack_cols
    assert "reinstatement_finished" in pack_cols
    assert "inch_metre" in pack_cols
    assert "line_check_finished" in pack_cols
    assert "linecheck_finished" not in pack_cols

    action_cols = _column_names(db_manager.engine, "project_actions")
    assert "rt_report_number" in action_cols
    assert "performed_by_1" in action_cols
    assert "work_front" in action_cols
    assert "action_by_1" not in action_cols

    doc_cols = _column_names(db_manager.engine, "documents")
    assert "receive_transmittal_number" in doc_cols
    assert "send_transmittal_number" in doc_cols
    assert "description_fa" in doc_cols
    assert "remarks" in doc_cols


def test_site_register_synonyms_and_crud(db_manager):
    project_id = seed_project(db_manager, "SITE-01", "Site Registers")
    with db_manager.session_scope() as session:
        weld = Weld(
            project_id=project_id,
            weld_number="FW-101",
            weld_type="Field",
            install_location="AG",
            left_component="Pipe",
            left_qty=1,
            hold=True,
        )
        session.add(weld)
        session.flush()
        assert weld.ag_ug == "AG"
        assert weld.shop_field == "Field"
        assert weld.base_metal == weld.material

        session.add(TechnicalQuery(
            project_id=project_id,
            tq_number="TQ-001",
            category="Welding",
            priority="High",
            status="Open",
            description="Clarify PWHT hold time",
        ))
        session.add(Company(
            project_id=project_id,
            name="National Oil Company",
            project_name="Site Registers",
        ))
        session.add(MaterialTakeOff(
            project_id=project_id,
            material_type="Elbow 90°",
            description="LR elbow",
            miv_number="MIV-12",
            commodity_code="EL90",
            quantity_required=4,
        ))
        session.add(PipeSupport(
            project_id=project_id,
            support_tag="PS-1001",
            install_location="UG",
            fab_fitup_report_number="FF-01",
        ))
        pack = HydroTestPackage(
            project_id=project_id,
            package_number="TP-200",
            linecheck_finished=True,
            linecheck_result="Accept",
        )
        session.add(pack)
        session.add(ProjectAction(
            project_id=project_id,
            action_type="NDT",
            rt_report_number="RT-009",
            action_by_1="QC-01",
        ))
        session.add(Document(
            project_id=project_id,
            doc_number="ISO-1001",
            doc_type="Isometric",
            receive_transmittal_number="TR-IN-1",
            send_transmittal_number="TR-OUT-1",
        ))
        session.flush()
        assert weld.ag_ug == "AG"
        assert pack.ag_ug is None


def test_legacy_sqlite_gains_site_register_columns(tmp_path):
    db_path = tmp_path / "legacy_site.db"
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
    conn.commit()
    conn.close()

    db = DatabaseManager(f"sqlite:///{db_path}")
    assert db.initialize() is True
    weld_cols = _column_names(db.engine, "welds")
    assert "install_location" in weld_cols
    assert "test_package_number" in weld_cols
    assert "sheet_number" in weld_cols
    with db.engine.connect() as engine_conn:
        row = engine_conn.execute(
            text("SELECT weld_number FROM welds WHERE id = 1")
        ).one()
        assert row[0] == "W-001"


def test_access_headers_map_to_industry_columns():
    from services.data_exchange_service import resolve_import_column

    weld_cols = {
        "iso_number", "sheet_number", "install_location", "weld_number",
        "ndt_extent_rt_pct", "pwht_required", "weld_type", "base_material",
        "left_component", "test_package_number", "remarks",
    }
    assert resolve_import_column("IsoNo", weld_cols) == "iso_number"
    assert resolve_import_column("AG/UG", weld_cols) == "install_location"
    assert resolve_import_column("JointNu", weld_cols) == "weld_number"
    assert resolve_import_column("RT-Percent", weld_cols) == "ndt_extent_rt_pct"
    assert resolve_import_column("PWHT-Req", weld_cols) == "pwht_required"
    assert resolve_import_column("SF", weld_cols) == "weld_type"
    assert resolve_import_column("BaseMetal", weld_cols) == "base_material"
    assert resolve_import_column("Left", weld_cols) == "left_component"
    assert resolve_import_column("TestPackageNo", weld_cols) == "test_package_number"

    action_cols = {"document_number", "rt_report_number", "performed_by_1"}
    assert resolve_import_column("Document No", action_cols) == "document_number"
    assert resolve_import_column("RTNo", action_cols) == "rt_report_number"
    assert resolve_import_column("Actions By1", action_cols) == "performed_by_1"

    doc_cols = {"document_number", "receive_transmittal_number", "description_fa"}
    assert resolve_import_column("DocumentNo", doc_cols) == "document_number"
    assert resolve_import_column("ReceiveTransNo", doc_cols) == "receive_transmittal_number"
    assert resolve_import_column("DescriptionFarsi", doc_cols) == "description_fa"

    mto_cols = {
        "source_document_number", "commodity_code", "miv_number",
        "two_year_quantity",
    }
    assert resolve_import_column("Doc NO", mto_cols) == "source_document_number"
    assert resolve_import_column("COMM-CODE", mto_cols) == "commodity_code"
    assert resolve_import_column("MIV_No", mto_cols) == "miv_number"
    assert resolve_import_column("2 YEARS  QTY (pcs)", mto_cols) == "two_year_quantity"

    support_cols = {
        "fab_fitup_report_number", "er_weld_report_number",
        "pt_report_number", "support_subtype", "base_material",
    }
    assert resolve_import_column("FabFitupSupportReport", support_cols) == "fab_fitup_report_number"
    assert resolve_import_column("ErWeldSupportReport", support_cols) == "er_weld_report_number"
    assert resolve_import_column("PtReportNo", support_cols) == "pt_report_number"
    assert resolve_import_column("Type2", support_cols) == "support_subtype"
    assert resolve_import_column("BaseMetal", support_cols) == "base_material"

    tq_cols = {"tq_number", "raised_date", "related_document_number", "status"}
    assert resolve_import_column("TQ Number", tq_cols) == "tq_number"
    assert resolve_import_column("Date Raised", tq_cols) == "raised_date"
    assert resolve_import_column("Related Document/Drawing", tq_cols) == "related_document_number"
    assert resolve_import_column("Status (Open/Closed)", tq_cols) == "status"

    pack_cols = {
        "package_number", "install_location", "line_check_finished",
        "pressure_test_result", "reinstatement_finished", "test_medium",
    }
    assert resolve_import_column("TestPackageNo", pack_cols) == "package_number"
    assert resolve_import_column("Ag_Ug", pack_cols) == "install_location"
    assert resolve_import_column("Fin_Linecheck", pack_cols) == "line_check_finished"
    assert resolve_import_column("Pressuretest_result", pack_cols) == "pressure_test_result"
    assert resolve_import_column("Fin_Reinstate", pack_cols) == "reinstatement_finished"
    assert resolve_import_column("T_Medum", pack_cols) == "test_medium"

    company_cols = {"name", "logo_file_path"}
    assert resolve_import_column("Compnay Name", company_cols) == "name"
    assert resolve_import_column("Logo", company_cols) == "logo_file_path"
