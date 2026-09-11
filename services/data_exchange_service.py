# -*- coding: utf-8 -*-
"""
services/data_exchange_service.py – PipeAgent
ماژول جامع واردات و صادرات چندفرمتي داده‌های مهندسی و کیفی (Excel, CSV, JSON, HTML)
بهینه‌سازی شده برای بارگیری فایل‌های حجیم اکسل (Low-Memory footprint)
ایمن در برابر حملات XSS و بهینه‌شده با عملیات دسته‌ای دیتابیس (Bulk Operations).
"""

from __future__ import annotations

import csv
import html
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from db.models import (
    Project, Area, LineListItem, MaterialRequisition, PurchaseOrder, MaterialItem,
    MaterialTakeOff, Spool, WPS_PQR, Weld, JointHistory, NDTRecord, PipeSupport,
    TestPackage, TestPackageWeld, TestRequest, Document, DocumentRevision,
    Transmittal, TransmittalItem, HandoverPackage, ProjectAction, WorkFront,
    WorkTeam, SiteMachine, WorkAssignment, FieldSyncEvent, FieldAttachment,
    AIInsight, ProductivitySnapshot, TurnoverDossier, User, Company, TechnicalQuery,
)

logger = logging.getLogger(__name__)

# Implementation note.
MODEL_MAP = {
    "Projects": Project, "Areas": Area, "Line List": LineListItem,
    "Material Requisitions": MaterialRequisition, "Purchase Orders": PurchaseOrder,
    "Material Items": MaterialItem, "MTO": MaterialTakeOff, "Spools": Spool,
    "WPS / PQR": WPS_PQR, "Welds": Weld, "Joint History": JointHistory,
    "NDT Records": NDTRecord, "Pipe Supports": PipeSupport, "Test Packages": TestPackage,
    "Test Package Welds": TestPackageWeld, "Test Requests": TestRequest,
    "Documents": Document, "Document Revisions": DocumentRevision,
    "Transmittals": Transmittal, "Transmittal Items": TransmittalItem,
    "Handover Packages": HandoverPackage, "Project Actions": ProjectAction,
    "Work Fronts": WorkFront, "Work Teams": WorkTeam, "Site Machines": SiteMachine,
    "Work Assignments": WorkAssignment, "Field Sync Events": FieldSyncEvent,
    "Field Attachments": FieldAttachment, "AI Insights": AIInsight,
    "Productivity Snapshots": ProductivitySnapshot, "Turnover Dossiers": TurnoverDossier,
    "Users": User, "Companies": Company, "Technical Queries": TechnicalQuery,
}

# Implementation note. Keys are matched after _norm() (case, spaces, punctuation).
ALIASES = {
    "project code": "project_code", "project": "project_code", "project id": "project_id",
    "line no": "line_number", "lineno": "line_number", "line": "line_number",
    "iso no": "iso_number", "isono": "iso_number", "iso": "iso_number",
    "spool no": "spool_number", "spoolnumber": "spool_number", "spool": "spool_number",
    "weld no": "weld_number", "joint no": "weld_number", "jointnu": "weld_number",
    "weld id": "weld_number", "welder": "welder_name",
    "wps": "wps_number", "wpsid": "wps_number", "requestno": "request_number",
    "date": "work_date", "qty": "quantity", "tonnage": "weight_kg",
    "sheetno": "sheet_number", "sheetrev": "sheet_revision", "revstatus": "revision_status",
    "agug": "install_location", "ag/ug": "install_location",
    "pipeclass": "pipe_class", "lineservice": "line_service",
    "jointindex": "joint_index", "thk": "wall_thickness_mm",
    "jointsize": "size_nps", "jointtype": "joint_type", "jsch": "schedule",
    "pwhtreq": "pwht_required", "rtpercent": "ndt_percent_rt", "ptpercent": "ndt_percent_pt",
    "sf": "weld_type", "testpackageno": ("test_package_number", "package_number"),
    "jointstatus": "status", "basemetal": "material",
    "left": "left_component", "leftqty": "left_qty",
    "right": "right_component", "rightqty": "right_qty",
    "jointremark": "remarks", "isexpired": "is_expired",
    "documenttype": "document_type",
    "documentno": ("document_number", "doc_number", "source_document_number"),
    "documentdate": "document_date", "rtno": "rt_report_number",
    "actionsby1": "action_by_1", "actionsby2": "action_by_2",
    "workfront": "work_front", "link": "link_url",
    "addby": "created_by", "editby": "updated_by",
    "filelocation": "file_path",
    "class": "doc_class", "index": "doc_index", "sheet": "sheet_number",
    "receivetransno": "receive_transmittal_number",
    "receiveletterno": "receive_letter_number",
    "receivefrom": "received_from", "receivedate": "received_date",
    "descriptionfarsi": "description_fa",
    "sendto": "sent_to", "sendtransno": "send_transmittal_number",
    "senddate": "sent_date", "sendletterno": "send_letter_number",
    "doc no": "source_document_number", "docno": "source_document_number",
    "sizein": "size_nps", "thicknessmm": "thickness_mm", "lengthmm": "length_mm",
    "materialdescription": "description", "mtoqtypcs": "quantity_required",
    "2yearsqtypcs": "two_year_qty", "purchaseqtypcs": "purchase_qty",
    "commcode": "commodity_code", "mivno": "miv_number", "mivdate": "miv_date",
    "mivqty": "miv_qty", "item": "item_number",
    "joint": "joint_number", "weldstatus": "weld_status",
    "fabricationweight": "fabrication_weight_kg",
    "erectionweight": "erection_weight_kg",
    "type1": "support_type", "type2": "type_2",
    "fabfitupsupportreport": "fab_fitup_report_number",
    "fabfitupsupportdate": "fab_fitup_date",
    "fabfitupsupportresult": "fab_fitup_result",
    "fabfitupsupportcontractor": "fab_fitup_contractor",
    "fabweldsupportreport": "fab_weld_report_number",
    "fabweldsupportdate": "fab_weld_date",
    "fabweldsupportresult": "fab_weld_result",
    "fabweldsupportcontractor": "fab_weld_contractor",
    "erfitupsupportreport": "er_fitup_report_number",
    "erfitupsupportdate": "er_fitup_date",
    "erfitupsupportresult": "er_fitup_result",
    "erfitupsupportcontractor": "er_fitup_contractor",
    "erweldsupportreport": "er_weld_report_number",
    "erweldsupportdate": "er_weld_date",
    "erweldsupportresult": "er_weld_result",
    "erweldsupportcontractor": "er_weld_contractor",
    "weldername": "welder_name", "ptreportno": "pt_report_number",
    "ptdate": "pt_date", "ptresult": "pt_result", "remark": "remarks",
    "tqnumber": "tq_number", "dateraised": "raised_date",
    "datesubmittedsent": "submitted_date",
    "raisedbypersondepartment": "raised_by",
    "descriptionofquery": "description",
    "relateddocumentdrawing": "related_document",
    "duedate": "due_date", "responseresolution": "response",
    "dateresponsereceived": "response_received_date",
    "responsedate": "response_received_date",
    "statusopenclosed": "status", "assignedto": "assigned_to",
    "approvalby": "approved_by", "notesattachments": "notes",
    "diainch": "dia_inch_total",
    "inchmeter": "inch_meter", "tmedum": "test_medium", "tmedium": "test_medium",
    "testbar": "test_pressure_barg",
    "finlinecheck": "linecheck_finished",
    "linecheckresultdate": "linecheck_result_date",
    "linecheckresult": "linecheck_result",
    "linechecksubcon": "linecheck_subcontractor",
    "fincleaning": "cleaning_finished",
    "cleaningresultdate": "cleaning_result_date",
    "cleaningresult": "cleaning_result",
    "finpressuretest": "pressure_test_finished",
    "pressuretestresultdate": "pressure_test_result_date",
    "pressuretestresult": "pressure_test_result",
    "pressuretestsubcon": "pressure_test_subcontractor",
    "finflushingdraining": "flushing_finished",
    "flushingdrainingresultdate": "flushing_result_date",
    "flushingdrainingresult": "flushing_result",
    "flushingdrainingsubcon": "flushing_subcontractor",
    "finfacecleaning": "face_cleaning_finished",
    "facecleaningresultdate": "face_cleaning_result_date",
    "facecleaningresult": "face_cleaning_result",
    "finreinstate": "reinstatement_finished",
    "reinstateresultdate": "reinstatement_result_date",
    "reinstateresult": "reinstatement_result",
    "reinstatesubcon": "reinstatement_subcontractor",
    "compnayname": "name", "companyname": "name", "logo": "logo_path",
}

# Implementation note.
NATURAL_KEYS = {
    Project: ["project_code"], Area: ["project_id", "name"], LineListItem: ["project_id", "line_number"],
    MaterialRequisition: ["mr_number"], PurchaseOrder: ["po_number"], Spool: ["spool_number"],
    WPS_PQR: ["wps_number"], Weld: ["project_id", "weld_number"], TestRequest: ["request_number"],
    Document: ["doc_number"], WorkFront: ["front_code"], WorkTeam: ["team_code"],
    SiteMachine: ["machine_code"], WorkAssignment: ["id"], TurnoverDossier: ["dossier_number"],
    User: ["username"], TechnicalQuery: ["project_id", "tq_number"],
    Company: ["project_id"], PipeSupport: ["project_id", "support_tag"],
    TestPackage: ["package_number"], MaterialTakeOff: ["project_id", "item_number"],
}


# ──────────────────────────────────────────────
#  Formatting & Normalization Helpers
# ──────────────────────────────────────────────

def _norm(s: Any) -> str:
    """Match headers to columns without case, spaces, or punctuation."""
    text = str(s or "").strip().lower()
    for ch in ("_", "-", " ", "/", "\\", "[", "]", "(", ")", ".", "%"):
        text = text.replace(ch, "")
    return text


def resolve_import_column(header: str, column_names) -> Optional[str]:
    """Map an Access/Excel header onto a physical column name for one model."""
    key = _norm(header)
    names = list(column_names)
    for name in names:
        if _norm(name) == key:
            return name
    for alias, target in ALIASES.items():
        if _norm(alias) != key:
            continue
        targets = target if isinstance(target, (tuple, list)) else (target,)
        for candidate in targets:
            if candidate in names:
                return candidate
    return None


def _columns(model):
    """استخراج ستون‌های اصلی دیتابیسی مدل (بدون فیلد primary key عددی id)"""
    return [c for c in inspect(model).columns if not c.primary_key]


def _serialize(v: Any) -> Any:
    """سریالایز کردن مقادیر تاریخ و زمان برای خروجی‌های JSON/CSV"""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _convert(v: Any, col: Any) -> Any:
    """مبدل پیشرفته و ایمن مقادیر ورودی بر اساس نوع داده ستون دیتابیس (SQL Type Casting)"""
    if v in (None, ""):
        return None
    
    typ = str(col.type).upper()
    
    # Implementation note.
    if "BOOLEAN" in typ:
        if isinstance(v, bool):
            return v
        return _norm(v) in {"1", "true", "yes", "y", "on", "active", "checked"}
    
    # Implementation note.
    if "INTEGER" in typ:
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return None
            
    # Implementation note.
    if any(keyword in typ for keyword in ["FLOAT", "REAL", "NUMERIC", "DECIMAL"]):
        try:
            return float(v)
        except (ValueError, TypeError):
            return None
            
    # Implementation note.
    if "DATE" in typ and "TIME" not in typ:
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, date):
            return v
        v_str = str(v).strip().replace("/", "-")
        # Implementation note.
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(v_str, fmt).date()
            except ValueError:
                continue
        try:
            return date.fromisoformat(v_str)
        except ValueError:
            return None
            
    # Implementation note.
    if "DATETIME" in typ or "TIMESTAMP" in typ:
        if isinstance(v, datetime):
            return v
        v_str = str(v).strip().replace("/", "-")
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y %H:%M"):
            try:
                return datetime.strptime(v_str, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(v_str)
        except ValueError:
            return None
            
    # Implementation note.
    return str(v).strip()


# ──────────────────────────────────────────────
#  DataExchangeService Implementation
# ──────────────────────────────────────────────

class DataExchangeService:
    """
    سرویس جامع مبادله اطلاعات مهندسی و اجرایی کارگاه با بهینه‌سازی مصرف حافظه و امنیت بالا
    """

    def __init__(self, db_manager):
        self.db = db_manager

    @classmethod
    def model_names(cls) -> List[str]:
        return list(MODEL_MAP.keys())

    # Implementation note.

    def create_template(self, model_name: str, path: str, sample_rows: int = 3) -> str:
        """تولید قالب اختصاصی برای یک موجودیت با اعمال استایل‌های شرکتی"""
        model = MODEL_MAP[model_name]
        wb = Workbook()
        ws = wb.active
        ws.title = model_name[:31]
        
        # Implementation note.
        ws.views.sheetView[0].showGridLines = True
        
        cols = _columns(model)
        header_fill = PatternFill("solid", fgColor="123047")  # Implementation note.
        header_font = Font(bold=True, color="FFFFFF", name="Segoe UI", size=11)
        center_align = Alignment(horizontal="center", vertical="center")

        for i, col in enumerate(cols, 1):
            cell = ws.cell(1, i, col.name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        # Implementation note.
        for col_idx, col in enumerate(cols, 1):
            col_letter = ws.cell(1, col_idx).column_letter
            ws.column_dimensions[col_letter].width = min(max(len(col.name) + 4, 12), 35)

        wb.save(path)
        wb.close()
        return path

    # Implementation note.

    def _prepare_rows(self, model: Any, raw_rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        """آماده‌سازی و اعتبارسنجی فیلدهای ردیف‌های ورودی (بدون درگیری با دیتابیس)"""
        cols = {c.name: c for c in _columns(model)}
        prepared_data = []
        errors = []

        for row_idx, raw in enumerate(raw_rows, start=2):
            normalized_row = {}
            for k, v in raw.items():
                if k is None:
                    continue
                target_col = resolve_import_column(str(k), cols)
                if target_col in cols:
                    normalized_row[target_col] = v

            converted_row = {}
            for key, val in normalized_row.items():
                converted_row[key] = _convert(val, cols[key])

            # Implementation note.
            missing = [
                c.name for c in cols.values()
                if not c.nullable and c.default is None and c.name not in converted_row
            ]
            
            # Implementation note.
            if "project_id" in missing and "project_code" in normalized_row:
                missing.remove("project_id")

            if missing:
                errors.append(f"Row {row_idx}: Mandatory fields missing ({', '.join(missing)})")
                continue

            prepared_data.append(converted_row)

        return prepared_data, errors

    def import_rows(self, model_name: str, rows: List[Dict[str, Any]], update_existing: bool = True) -> Dict[str, Any]:
        """
        درج یا به‌روزرسانی دسته‌ای ردیف‌ها با راندمان بالا و تراکنش اتمیک
        """
        model = MODEL_MAP[model_name]
        prepared, errors = self._prepare_rows(model, rows)
        
        created = 0
        updated = 0
        skipped = 0

        with self.db.session_scope() as session:
            # Implementation note.
            projects = {p.project_code: p.id for p in session.query(Project).all()} if hasattr(model, "project_id") else {}
            keys = NATURAL_KEYS.get(model, [])

            for data in prepared:
                if not data:
                    skipped += 1
                    continue

                # Implementation note.
                if "project_code" in data and hasattr(model, "project_id"):
                    p_code = data.pop("project_code")
                    p_id = projects.get(p_code)
                    if p_id:
                        data["project_id"] = p_id
                    else:
                        skipped += 1
                        errors.append(f"Skipped row: Project Code '{p_code}' not found in database.")
                        continue

                existing_obj = None
                # Implementation note.
                if update_existing and keys:
                    filters = []
                    is_valid_key = True
                    for k in keys:
                        if k not in data or data[k] in (None, ""):
                            is_valid_key = False
                            break
                        filters.append(getattr(model, k) == data[k])
                    
                    if is_valid_key:
                        existing_obj = session.query(model).filter(*filters).first()

                if existing_obj:
                    for k, v in data.items():
                        setattr(existing_obj, k, v)
                    updated += 1
                else:
                    try:
                        new_record = model(**data)
                        session.add(new_record)
                        created += 1
                    except Exception as exc:
                        skipped += 1
                        errors.append(f"Database insertion failed: {exc}")
                        continue

            session.flush()

        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors[:100],  # Implementation note.
        }

    # Implementation note.

    def import_excel(self, path: str, sheet_name: Optional[str] = None, update_existing: bool = True) -> Dict[str, Any]:
        """
        واردات بهینه فایل‌های اکسل حجیم کارگاهی با استراتژی read_only=True جهت کاهش چشمگیر مصرف RAM
        """
        # Implementation note.
        wb = load_workbook(path, read_only=True, data_only=True)
        results = {}
        sheets = [sheet_name] if sheet_name else wb.sheetnames

        for sheet in sheets:
            if sheet not in wb.sheetnames:
                continue
            
            # Implementation note.
            target_model = next((n for n in MODEL_MAP if n[:31].lower() == sheet.lower() or n.lower() == sheet.lower()), None)
            if not target_model:
                continue

            ws = wb[sheet]
            rows_generator = ws.iter_rows(values_only=True)
            
            try:
                header_row = next(rows_generator)
            except StopIteration:
                continue

            if not header_row:
                continue

            headers = [str(h or "").strip() for h in header_row]
            data_payload = []

            for row_values in rows_generator:
                if not any(v not in (None, "") for v in row_values):
                    continue  # Implementation note.
                
                row_dict = dict(zip(headers, row_values))
                data_payload.append(row_dict)

            results[target_model] = self.import_rows(target_model, data_payload, update_existing)

        wb.close()
        return results

    # Implementation note.

    def preview_excel(self, path: str, model_name: Optional[str] = None, sheet_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        پیش‌نمایش و ارزیابی ساختار فایل اکسل (Dry-Run / Simulation) قبل از نوشتن قطعی در دیتابیس
        """
        wb = load_workbook(path, read_only=True, data_only=True)
        sheets = [sheet_name] if sheet_name else wb.sheetnames
        previews = []

        for sheet in sheets:
            if sheet not in wb.sheetnames:
                continue
            
            target = model_name or next((n for n in MODEL_MAP if n[:31].lower() == sheet.lower() or n.lower() == sheet.lower()), None)
            if not target:
                continue

            ws = wb[sheet]
            rows_generator = ws.iter_rows(values_only=True)
            try:
                header_row = next(rows_generator)
            except StopIteration:
                continue

            if not header_row:
                continue

            headers = [str(x or "").strip() for x in header_row]
            model = MODEL_MAP[target]
            cols = {c.name: c for c in _columns(model)}
            keys = NATURAL_KEYS.get(model, [])
            seen_keys_in_file = set()

            with self.db.session_scope() as session:
                for row_no, values in enumerate(rows_generator, start=2):
                    if not any(v not in (None, "") for v in values):
                        continue

                    raw = dict(zip(headers, values))
                    normalized = {}
                    for k, v in raw.items():
                        key = _norm(k)
                        dest = next((c for c in cols if _norm(c) == key), ALIASES.get(key))
                        if dest in cols:
                            normalized[dest] = v

                    data = {k: _convert(v, cols[k]) for k, v in normalized.items()}
                    errors = []

                    # Implementation note.
                    missing = [
                        c.name for c in cols.values()
                        if not c.nullable and c.default is None and c.name not in data
                    ]
                    if "project_id" in missing and "project_code" in normalized:
                        missing.remove("project_id")
                    if missing:
                        errors.append(f"Missing mandatory columns ({', '.join(missing)})")

                    # Implementation note.
                    key_tuple = tuple(data.get(k) for k in keys) if keys else None
                    if keys and key_tuple and all(v not in (None, "") for v in key_tuple):
                        if key_tuple in seen_keys_in_file:
                            errors.append("Duplicate record found within the Excel file")
                        seen_keys_in_file.add(key_tuple)

                    # Implementation note.
                    exists_in_db = False
                    if not errors and keys and key_tuple and all(v not in (None, "") for v in key_tuple):
                        filters = [getattr(model, k) == data[k] for k in keys]
                        exists_in_db = session.query(model).filter(*filters).first() is not None

                    previews.append({
                        "sheet": sheet,
                        "model": target,
                        "row": row_no,
                        "status": "ERROR" if errors else ("UPDATE" if exists_in_db else "NEW"),
                        "errors": "; ".join(errors),
                        "data": data,
                    })

        wb.close()
        return previews

    # Implementation note.

    def export_model(self, model_name: str, path: str, fmt: str = "xlsx", project_id: Optional[int] = None) -> str:
        """خروجی اطلاعات از دیتابیس در قالب فرمت‌های استاندارد"""
        model = MODEL_MAP[model_name]
        with self.db.session_scope() as session:
            query = session.query(model)
            if project_id and hasattr(model, "project_id"):
                query = query.filter(model.project_id == project_id)
            
            rows = []
            columns_list = [c.name for c in inspect(model).columns]
            for obj in query.all():
                record_dict = {col: _serialize(getattr(obj, col)) for col in columns_list}
                rows.append(record_dict)

        return self._write_rows(rows, path, fmt)

    def _write_rows(self, rows: List[Dict[str, Any]], path: str, fmt: str) -> str:
        """رشته‌سازی و ذخیره قطعی فایل خروجی با ایمن‌سازی بدنه متون"""
        path_obj = Path(path)
        fmt = fmt.lower()
        headers = list(rows[0].keys()) if rows else []

        if fmt == "xlsx":
            wb = Workbook()
            ws = wb.active
            ws.title = "Export"
            ws.views.sheetView[0].showGridLines = True
            
            # Implementation note.
            header_font = Font(bold=True, color="FFFFFF", name="Segoe UI")
            header_fill = PatternFill("solid", fgColor="123047")
            
            for i, h in enumerate(headers, 1):
                cell = ws.cell(1, i, h)
                cell.font = header_font
                cell.fill = header_fill
            
            for r, row in enumerate(rows, 2):
                for i, h in enumerate(headers, 1):
                    ws.cell(r, i, row.get(h))
                    
            wb.save(path_obj)
            wb.close()

        elif fmt == "csv":
            # Implementation note.
            with open(path_obj, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.rows_writer = writer.writerows(rows)

        elif fmt == "json":
            path_obj.write_text(
                json.dumps(rows, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

        elif fmt == "html":
            # Implementation note.
            th_tags = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
            tr_tags = []
            
            for r in rows:
                td_tags = "".join(f"<td>{html.escape(str(r.get(h, '') or ''))}</td>" for h in headers)
                tr_tags.append(f"<tr>{td_tags}</tr>")
                
            html_content = (
                f"<!doctype html><html><head><meta charset='utf-8'>"
                f"<title>PipeAgent Smart Export</title>"
                f"<style>body{{font-family:'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;margin:20px;}}"
                f"table{{border-collapse:collapse;width:100%;margin-top:20px;}}"
                f"th,td{{border:1px solid #ddd;padding:10px;text-align:left;}}"
                f"th{{background-color:#123047;color:white;font-weight:bold;}}"
                f"tr:nth-child(even){{background-color:#f9f9f9;}}"
                f"tr:hover{{background-color:#f1f1f1;}}</style></head>"
                f"<body><h2>PipeAgent - Export Records Report</h2>"
                f"<table><thead><tr>{th_tags}</tr></thead>"
                f"<tbody>{''.join(tr_tags)}</tbody></table></body></html>"
            )
            path_obj.write_text(html_content, encoding="utf-8")

        else:
            raise ValueError(f"Unsupported export format specified: {fmt}")

        return str(path_obj)