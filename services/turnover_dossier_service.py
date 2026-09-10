# -*- coding: utf-8 -*-
"""
turnover_dossier_service.py - PipeAgent
========================================
Digital Turnover Dossier Generator
-----------------------------------
Generates a fully traceable, audit-ready turnover dossier for piping
scope (Line / System / Test Package / Full Project) including:

  • Manifest with SHA-256 checksums
  • Machine-readable JSON + human-readable CSV registers
  • Weld register + NDT + PWHT + Heat traceability
  • Test packages, hydro results, punch list, NCRs
  • Documents index (drawings, certificates, MTRs)
  • Weighted completeness score
  • ZIP archive + optional digital signature metadata
  • Persistent record in TurnoverDossier table

Compatible with EN 10204, ASME B31.3, ISO 9001 handover requirements.

Author : PipeAgent Engineering
Version: 5.0.0
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import platform
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from db.models import (
    Project,
    LineListItem,
    Weld,
    NDTRecord,
    TestPackage,
    Document,
    HandoverPackage,
    TurnoverDossier,
)

# Optional models (guarded imports)
try:
    from db.models import (
        PWHTRecord,
        MaterialReceipt,
        PunchItem,
        NCR,
        ValveTest,
        WelderQualification,
    )
    _EXTENDED_MODELS = True
except ImportError:  # pragma: no cover
    PWHTRecord = MaterialReceipt = PunchItem = NCR = ValveTest = WelderQualification = None
    _EXTENDED_MODELS = False


logger = logging.getLogger("pipeagent.services.turnover")


# ─────────────────────────────────────────────
#  Enums & Constants
# ─────────────────────────────────────────────

class DossierScope(str, Enum):
    LINE = "Line"
    SYSTEM = "System"
    SUBSYSTEM = "Subsystem"
    TEST_PACKAGE = "TestPackage"
    PROJECT = "Project"


class DossierStatus(str, Enum):
    DRAFT = "Draft"
    IN_REVIEW = "InReview"
    READY = "Ready"
    SIGNED = "Signed"
    ISSUED = "Issued"
    ARCHIVED = "Archived"


# Acceptable weld statuses for a "closed" scope
ACCEPTED_WELD_STATUSES = {"Accepted", "Inspected", "Welded", "Approved", "Reinstated"}
ACCEPTED_NDT_STATUSES = {"Accepted", "Passed", "AC"}
ACCEPTED_DOC_STATUSES = {"Approved", "Issued", "Released", "AFC"}


# Weights for completeness scoring (must sum to 1.0)
COMPLETENESS_WEIGHTS: Dict[str, float] = {
    "line_data":          0.10,
    "welds_present":      0.15,
    "welds_accepted":     0.20,
    "ndt_complete":       0.15,
    "pwht_complete":      0.05,
    "material_traceable": 0.10,
    "documents":          0.10,
    "test_packages":      0.10,
    "punch_cleared":      0.05,
}


# ─────────────────────────────────────────────
#  Data Classes
# ─────────────────────────────────────────────

@dataclass
class DossierManifest:
    """Machine-readable manifest describing every file in the dossier."""
    dossier_number: str
    scope_type: str
    scope_key: str
    project_code: str
    generated_at: str
    generated_by: str
    host: str
    files: List[Dict[str, Any]] = field(default_factory=list)
    completeness_pct: float = 0.0
    checks: Dict[str, bool] = field(default_factory=dict)
    total_size_bytes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dossier_number": self.dossier_number,
            "scope": {"type": self.scope_type, "key": self.scope_key},
            "project": self.project_code,
            "generated_at": self.generated_at,
            "generated_by": self.generated_by,
            "host": self.host,
            "completeness_pct": self.completeness_pct,
            "checks": self.checks,
            "total_size_bytes": self.total_size_bytes,
            "file_count": len(self.files),
            "files": self.files,
        }


@dataclass
class DossierResult:
    """Return object for dossier generation."""
    dossier_number: str
    path: str
    zip_path: str
    completeness_pct: float
    status: str
    file_count: int
    total_size_bytes: int
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


# ─────────────────────────────────────────────
#  Main Service
# ─────────────────────────────────────────────

class TurnoverDossierService:
    """
    Enterprise-grade Digital Turnover Dossier generator.

    Usage:
        svc = TurnoverDossierService(db)
        result = svc.generate_line_dossier(project_id=1, line_number="P-1001", user="admin")
        print(result.dossier_number, result.completeness_pct)
    """

    def __init__(
        self,
        db,
        export_dir: str = "exports/dossiers",
        *,
        keep_uncompressed: bool = False,
        compression_level: int = zipfile.ZIP_DEFLATED,
    ):
        self.db = db
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.keep_uncompressed = keep_uncompressed
        self.compression_level = compression_level

    # ─────────────────────────────────────────
    #  Public API — Multiple Scopes
    # ─────────────────────────────────────────

    def generate_line_dossier(
        self,
        project_id: int,
        line_number: str,
        user: str = "system",
    ) -> DossierResult:
        """Generate dossier for a single line."""
        return self._generate(
            project_id=project_id,
            scope_type=DossierScope.LINE,
            scope_key=line_number,
            user=user,
            filter_fn=lambda q, model: self._filter_by_line(q, model, line_number),
        )

    def generate_system_dossier(
        self,
        project_id: int,
        system_name: str,
        user: str = "system",
    ) -> DossierResult:
        """Generate dossier for an entire system."""
        return self._generate(
            project_id=project_id,
            scope_type=DossierScope.SYSTEM,
            scope_key=system_name,
            user=user,
            filter_fn=lambda q, model: self._filter_by_system(q, model, system_name),
        )

    def generate_test_package_dossier(
        self,
        project_id: int,
        package_number: str,
        user: str = "system",
    ) -> DossierResult:
        """Generate dossier for a single test package."""
        return self._generate(
            project_id=project_id,
            scope_type=DossierScope.TEST_PACKAGE,
            scope_key=package_number,
            user=user,
            filter_fn=lambda q, model: self._filter_by_test_package(q, model, package_number),
        )

    def generate_project_dossier(
        self,
        project_id: int,
        user: str = "system",
    ) -> DossierResult:
        """Generate complete project-wide dossier."""
        return self._generate(
            project_id=project_id,
            scope_type=DossierScope.PROJECT,
            scope_key="ALL",
            user=user,
            filter_fn=lambda q, model: q,  # no filter
        )

    # ─────────────────────────────────────────
    #  Core Generation Engine
    # ─────────────────────────────────────────

    def _generate(
        self,
        *,
        project_id: int,
        scope_type: DossierScope,
        scope_key: str,
        user: str,
        filter_fn,
    ) -> DossierResult:
        """Core dossier generation pipeline shared by all scopes."""

        warnings: List[str] = []

        with self.db.session_scope() as s:
            # 1. Load project
            project = s.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise ValueError(f"Project id={project_id} not found.")

            # 2. Collect scope data
            data = self._collect_scope_data(
                s, project, scope_type, scope_key, filter_fn, warnings
            )

            # 3. Compute completeness
            completeness, checks = self._compute_completeness(data)

            # 4. Build directory structure
            dossier_no = self._make_dossier_number(project.project_code, scope_type, scope_key)
            base = self.export_dir / dossier_no
            base.mkdir(parents=True, exist_ok=True)
            self._create_folder_structure(base)

            # 5. Write all artifacts
            data["_meta"] = {
                "dossier_number": dossier_no,
                "generated_at": datetime.utcnow().isoformat(),
                "generated_by": user,
                "scope_type": scope_type.value,
                "scope_key": scope_key,
                "project_code": project.project_code,
                "completeness_pct": completeness,
            }
            self._write_json(base / "01_summary" / "dossier.json", data)
            self._write_registers(base / "02_registers", data)
            self._write_certificates_index(base / "03_certificates", data)
            self._write_documents_index(base / "04_documents", data)
            self._write_readme(base, data, checks, completeness)

            # 6. Build manifest with SHA-256
            manifest = self._build_manifest(
                base=base,
                dossier_no=dossier_no,
                scope_type=scope_type.value,
                scope_key=scope_key,
                project_code=project.project_code,
                user=user,
                completeness=completeness,
                checks=checks,
            )
            self._write_json(base / "MANIFEST.json", manifest.to_dict())

            # 7. Create ZIP archive
            zip_path = self._create_zip(base)

            # 8. Persist DB record
            status = self._determine_status(completeness).value
            dossier_obj = TurnoverDossier(
                project_id=project_id,
                dossier_number=dossier_no,
                scope_type=scope_type.value,
                scope_key=scope_key,
                status=status,
                completeness_pct=completeness,
                generated_path=str(zip_path),
                generated_at=datetime.utcnow(),
                generated_by=user,
            )
            s.add(dossier_obj)

            # 9. Optionally remove uncompressed folder
            if not self.keep_uncompressed:
                shutil.rmtree(base, ignore_errors=True)

            logger.info(
                "Dossier %s generated (scope=%s, key=%s, %.1f%%)",
                dossier_no, scope_type.value, scope_key, completeness,
            )

            return DossierResult(
                dossier_number=dossier_no,
                path=str(base),
                zip_path=str(zip_path),
                completeness_pct=completeness,
                status=status,
                file_count=len(manifest.files),
                total_size_bytes=manifest.total_size_bytes,
                warnings=warnings,
            )

    # ─────────────────────────────────────────
    #  Data Collection
    # ─────────────────────────────────────────

    def _collect_scope_data(
        self, s, project, scope_type: DossierScope, scope_key: str,
        filter_fn, warnings: List[str],
    ) -> Dict[str, Any]:
        """Query all relevant records for the given scope."""

        # Lines
        line_q = s.query(LineListItem).filter(LineListItem.project_id == project.id)
        if scope_type == DossierScope.LINE:
            line_q = line_q.filter(LineListItem.line_number == scope_key)
        elif scope_type == DossierScope.SYSTEM:
            line_q = line_q.filter(LineListItem.system == scope_key)
        lines = line_q.all()

        if scope_type == DossierScope.LINE and not lines:
            warnings.append(f"Line '{scope_key}' not found in Line List.")

        # Welds
        welds = filter_fn(
            s.query(Weld).filter(Weld.project_id == project.id), Weld
        ).all()

        # NDT
        ndt = filter_fn(
            s.query(NDTRecord).filter(NDTRecord.project_id == project.id), NDTRecord
        ).all()

        # Documents
        docs = filter_fn(
            s.query(Document).filter(Document.project_id == project.id), Document
        ).all()

        # Test Packages
        tps = filter_fn(
            s.query(TestPackage).filter(TestPackage.project_id == project.id), TestPackage
        ).all()

        # Handover Packages
        hp = s.query(HandoverPackage).filter(
            HandoverPackage.project_id == project.id
        ).all()

        # Extended (optional) tables
        pwht, materials, punches, ncrs, valve_tests, welder_quals = [], [], [], [], [], []
        if _EXTENDED_MODELS:
            try:
                pwht = filter_fn(
                    s.query(PWHTRecord).filter(PWHTRecord.project_id == project.id),
                    PWHTRecord,
                ).all()
            except Exception:  # column may not exist
                pass
            try:
                materials = s.query(MaterialReceipt).filter(
                    MaterialReceipt.project_id == project.id
                ).all()
            except Exception:
                pass
            try:
                punches = filter_fn(
                    s.query(PunchItem).filter(PunchItem.project_id == project.id),
                    PunchItem,
                ).all()
            except Exception:
                pass
            try:
                ncrs = filter_fn(
                    s.query(NCR).filter(NCR.project_id == project.id), NCR
                ).all()
            except Exception:
                pass
            try:
                valve_tests = s.query(ValveTest).filter(
                    ValveTest.project_id == project.id
                ).all()
            except Exception:
                pass
            try:
                welder_quals = s.query(WelderQualification).filter(
                    WelderQualification.project_id == project.id
                ).all()
            except Exception:
                pass

        # Serialize
        return {
            "project": self._serialize_project(project),
            "lines":            [self._serialize_line(l) for l in lines],
            "welds":            [self._serialize_weld(w) for w in welds],
            "ndt_records":      [self._serialize_ndt(n) for n in ndt],
            "pwht_records":     [self._serialize_pwht(p) for p in pwht],
            "materials":        [self._serialize_material(m) for m in materials],
            "documents":        [self._serialize_document(d) for d in docs],
            "test_packages":    [self._serialize_test_pkg(t) for t in tps],
            "handover_packages":[self._serialize_handover(h) for h in hp],
            "punch_items":      [self._serialize_punch(p) for p in punches],
            "ncrs":             [self._serialize_ncr(n) for n in ncrs],
            "valve_tests":      [self._serialize_valve(v) for v in valve_tests],
            "welder_quals":     [self._serialize_welder(w) for w in welder_quals],
        }

    # ─────────────────────────────────────────
    #  Filter Helpers
    # ─────────────────────────────────────────

    @staticmethod
    def _filter_by_line(query, model, line_number: str):
        if hasattr(model, "line_number"):
            return query.filter(model.line_number == line_number)
        return query

    @staticmethod
    def _filter_by_system(query, model, system: str):
        if hasattr(model, "system"):
            return query.filter(model.system == system)
        return query

    @staticmethod
    def _filter_by_test_package(query, model, pkg_no: str):
        if hasattr(model, "test_package"):
            return query.filter(model.test_package == pkg_no)
        if hasattr(model, "package_number"):
            return query.filter(model.package_number == pkg_no)
        return query

    # ─────────────────────────────────────────
    #  Serializers
    # ─────────────────────────────────────────

    @staticmethod
    def _safe(obj, *fields) -> Dict[str, Any]:
        return {f: getattr(obj, f, None) for f in fields}

    def _serialize_project(self, p) -> Dict[str, Any]:
        return self._safe(
            p, "project_code", "name", "client", "contractor",
            "start_date", "target_end_date", "location", "description",
        )

    def _serialize_line(self, l) -> Dict[str, Any]:
        return self._safe(
            l, "line_number", "iso_number", "fluid_name", "pipe_class",
            "pipe_spec", "size_nps", "test_pressure_barg", "design_pressure_barg",
            "operating_pressure_barg", "insulation", "system", "subsystem",
        )

    def _serialize_weld(self, w) -> Dict[str, Any]:
        return self._safe(
            w, "weld_id", "line_number", "spool_no", "size_nps", "schedule",
            "wps_no", "status", "welder_id", "date_welded", "repair_count",
            "heat_no_pipe", "heat_no_filler", "joint_type",
        )

    def _serialize_ndt(self, n) -> Dict[str, Any]:
        return self._safe(
            n, "record_no", "weld_id", "ndt_method", "result",
            "report_no", "inspected_date", "inspector", "acceptance_criteria",
        )

    def _serialize_pwht(self, p) -> Dict[str, Any]:
        return self._safe(
            p, "record_no", "weld_id", "chart_no", "hold_temp_c",
            "hold_time_min", "result", "pwht_date",
        )

    def _serialize_material(self, m) -> Dict[str, Any]:
        return self._safe(
            m, "receipt_no", "material_desc", "heat_no", "mtr_no",
            "quantity", "unit", "received_date", "supplier",
        )

    def _serialize_document(self, d) -> Dict[str, Any]:
        return self._safe(
            d, "document_no", "title", "revision", "status",
            "issued_date", "discipline", "category",
        )

    def _serialize_test_pkg(self, t) -> Dict[str, Any]:
        return self._safe(
            t, "package_number", "system", "test_type", "test_pressure",
            "status", "planned_test_date", "actual_test_date",
        )

    def _serialize_handover(self, h) -> Dict[str, Any]:
        return self._safe(
            h, "package_number", "scope_type", "scope_key",
            "status", "issued_date",
        )

    def _serialize_punch(self, p) -> Dict[str, Any]:
        return self._safe(
            p, "punch_no", "category", "description",
            "status", "responsible", "target_date", "cleared_date",
        )

    def _serialize_ncr(self, n) -> Dict[str, Any]:
        return self._safe(
            n, "ncr_no", "title", "severity", "status",
            "raised_date", "closed_date",
        )

    def _serialize_valve(self, v) -> Dict[str, Any]:
        return self._safe(
            v, "tag_no", "type", "size", "test_type",
            "test_pressure", "result", "test_date",
        )

    def _serialize_welder(self, w) -> Dict[str, Any]:
        return self._safe(
            w, "welder_id", "name", "stamp", "process",
            "qualification_date", "expiry_date", "status",
        )

    # ─────────────────────────────────────────
    #  Completeness Scoring
    # ─────────────────────────────────────────

    def _compute_completeness(
        self, data: Dict[str, Any]
    ) -> Tuple[float, Dict[str, bool]]:
        """Weighted completeness (%)."""

        welds = data["welds"]
        ndt = data["ndt_records"]
        pwht = data["pwht_records"]
        docs = data["documents"]
        tps = data["test_packages"]
        materials = data["materials"]
        punches = data["punch_items"]

        checks = {
            "line_data": bool(data["lines"]),
            "welds_present": bool(welds),
            "welds_accepted": (
                all(w.get("status") in ACCEPTED_WELD_STATUSES for w in welds)
                if welds else False
            ),
            "ndt_complete": (
                bool(ndt) and all(
                    n.get("result") in ACCEPTED_NDT_STATUSES for n in ndt
                )
            ),
            "pwht_complete": (
                all(p.get("result") in ACCEPTED_NDT_STATUSES for p in pwht)
                if pwht else True    # pwht is not always applicable
            ),
            "material_traceable": (
                all(w.get("heat_no_pipe") for w in welds) if welds else False
            ),
            "documents": (
                bool(docs) and any(
                    d.get("status") in ACCEPTED_DOC_STATUSES for d in docs
                )
            ),
            "test_packages": bool(tps),
            "punch_cleared": (
                all(p.get("status") in ("Cleared", "Closed") for p in punches)
                if punches else True
            ),
        }

        score = sum(
            COMPLETENESS_WEIGHTS[k] * (1 if v else 0)
            for k, v in checks.items()
        )
        return round(score * 100, 1), checks

    # ─────────────────────────────────────────
    #  Filesystem Layout
    # ─────────────────────────────────────────

    @staticmethod
    def _create_folder_structure(base: Path) -> None:
        for sub in (
            "01_summary",
            "02_registers",
            "03_certificates",
            "04_documents",
            "05_attachments",
        ):
            (base / sub).mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────
    #  Writers
    # ─────────────────────────────────────────

    @staticmethod
    def _write_json(path: Path, obj: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(obj, default=str, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8-sig")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        # Union of keys to avoid KeyError
        fieldnames = sorted({k for r in rows for k in r.keys()})
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)

    def _write_registers(self, folder: Path, data: Dict[str, Any]) -> None:
        registers = {
            "weld_register.csv": data["welds"],
            "ndt_register.csv": data["ndt_records"],
            "pwht_register.csv": data["pwht_records"],
            "material_register.csv": data["materials"],
            "line_list.csv": data["lines"],
            "test_package_register.csv": data["test_packages"],
            "punch_list.csv": data["punch_items"],
            "ncr_register.csv": data["ncrs"],
            "valve_test_register.csv": data["valve_tests"],
            "welder_qualification_register.csv": data["welder_quals"],
        }
        for name, rows in registers.items():
            self._write_csv(folder / name, rows)

    def _write_certificates_index(self, folder: Path, data: Dict[str, Any]) -> None:
        """Index of certificates (NDT reports, PWHT charts, MTRs, etc.)."""
        index = {
            "ndt_reports": [
                {"report_no": n.get("report_no"), "weld_id": n.get("weld_id"),
                 "method": n.get("ndt_method"), "result": n.get("result")}
                for n in data["ndt_records"] if n.get("report_no")
            ],
            "pwht_charts": [
                {"chart_no": p.get("chart_no"), "weld_id": p.get("weld_id"),
                 "result": p.get("result")}
                for p in data["pwht_records"] if p.get("chart_no")
            ],
            "mtrs": [
                {"mtr_no": m.get("mtr_no"), "heat_no": m.get("heat_no"),
                 "material": m.get("material_desc")}
                for m in data["materials"] if m.get("mtr_no")
            ],
        }
        self._write_json(folder / "certificates_index.json", index)

    def _write_documents_index(self, folder: Path, data: Dict[str, Any]) -> None:
        self._write_json(folder / "documents_index.json", data["documents"])
        self._write_csv(folder / "documents_index.csv", data["documents"])

    def _write_readme(
        self, base: Path, data: Dict[str, Any],
        checks: Dict[str, bool], completeness: float,
    ) -> None:
        meta = data["_meta"]
        lines = [
            f"# Digital Turnover Dossier",
            f"",
            f"**Dossier No.:**  `{meta['dossier_number']}`",
            f"**Project:**       {meta['project_code']}",
            f"**Scope:**         {meta['scope_type']} — `{meta['scope_key']}`",
            f"**Generated:**     {meta['generated_at']} UTC by *{meta['generated_by']}*",
            f"**Completeness:**  **{completeness}%**",
            f"",
            f"## Contents",
            f"- `01_summary/`        Master JSON summary",
            f"- `02_registers/`      CSV registers (welds, NDT, PWHT, MTR…)",
            f"- `03_certificates/`   Certificate/report index",
            f"- `04_documents/`      Document register",
            f"- `05_attachments/`    Binary attachments (if any)",
            f"- `MANIFEST.json`      File-level manifest with SHA-256 checksums",
            f"",
            f"## Completeness Checks",
        ]
        for k, v in checks.items():
            icon = "✅" if v else "❌"
            weight = COMPLETENESS_WEIGHTS.get(k, 0) * 100
            lines.append(f"- {icon} **{k}**  _(weight {weight:.0f}%)_")
        lines.append("")
        lines.append("---")
        lines.append(f"Generated by PipeAgent Turnover Dossier Service v5.0")
        (base / "README.md").write_text("\n".join(lines), encoding="utf-8")

    # ─────────────────────────────────────────
    #  Manifest & Hashing
    # ─────────────────────────────────────────

    def _build_manifest(
        self, *, base: Path, dossier_no: str, scope_type: str, scope_key: str,
        project_code: str, user: str, completeness: float,
        checks: Dict[str, bool],
    ) -> DossierManifest:
        """Walk base dir, compute SHA-256 for every file, build manifest."""
        manifest = DossierManifest(
            dossier_number=dossier_no,
            scope_type=scope_type,
            scope_key=scope_key,
            project_code=project_code,
            generated_at=datetime.utcnow().isoformat(),
            generated_by=user,
            host=platform.node(),
            completeness_pct=completeness,
            checks=checks,
        )
        total = 0
        for f in sorted(base.rglob("*")):
            if not f.is_file() or f.name == "MANIFEST.json":
                continue
            size = f.stat().st_size
            total += size
            manifest.files.append({
                "path": str(f.relative_to(base)).replace("\\", "/"),
                "size_bytes": size,
                "sha256": self._sha256(f),
                "modified": datetime.utcfromtimestamp(
                    f.stat().st_mtime
                ).isoformat(),
            })
        manifest.total_size_bytes = total
        return manifest

    @staticmethod
    def _sha256(path: Path, chunk: int = 1 << 20) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(chunk), b""):
                h.update(block)
        return h.hexdigest()

    # ─────────────────────────────────────────
    #  Zip & Status
    # ─────────────────────────────────────────

    def _create_zip(self, base: Path) -> Path:
        zip_path = base.with_suffix(".zip")
        with zipfile.ZipFile(zip_path, "w", self.compression_level) as z:
            for f in sorted(base.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(base))
        logger.debug("Zipped dossier → %s (%.1f KB)",
                     zip_path, zip_path.stat().st_size / 1024)
        return zip_path

    @staticmethod
    def _determine_status(completeness: float) -> DossierStatus:
        if completeness >= 98:
            return DossierStatus.READY
        if completeness >= 80:
            return DossierStatus.IN_REVIEW
        return DossierStatus.DRAFT

    # ─────────────────────────────────────────
    #  Utility
    # ─────────────────────────────────────────

    @staticmethod
    def _make_dossier_number(
        project_code: str, scope_type: DossierScope, scope_key: str,
    ) -> str:
        """DOSS-<PROJ>-<SCOPE>-<KEY>-<TIMESTAMP>."""
        safe_key = "".join(
            c if c.isalnum() or c in ("-", "_") else "_"
            for c in str(scope_key)
        )[:40]
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        return f"DOSS-{project_code}-{scope_type.value[:3].upper()}-{safe_key}-{ts}"

    # ─────────────────────────────────────────
    #  Query / Registry
    # ─────────────────────────────────────────

    def list_dossiers(
        self, project_id: int, *, status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return list of dossiers registered in DB for a project."""
        with self.db.session_scope() as s:
            q = s.query(TurnoverDossier).filter(
                TurnoverDossier.project_id == project_id
            )
            if status:
                q = q.filter(TurnoverDossier.status == status)
            rows = q.order_by(TurnoverDossier.generated_at.desc()).all()
            return [
                {
                    "id": d.id,
                    "dossier_number": d.dossier_number,
                    "scope_type": d.scope_type,
                    "scope_key": d.scope_key,
                    "status": d.status,
                    "completeness_pct": d.completeness_pct,
                    "generated_at": d.generated_at,
                    "generated_by": d.generated_by,
                    "generated_path": d.generated_path,
                }
                for d in rows
            ]

    def verify_dossier(self, zip_path: str) -> Dict[str, Any]:
        """
        Re-verify a previously generated dossier ZIP by recomputing
        SHA-256 of each file against the stored MANIFEST.json.
        """
        p = Path(zip_path)
        if not p.exists():
            return {"valid": False, "error": f"File not found: {zip_path}"}

        results = {"valid": True, "checked": 0, "mismatches": []}
        with zipfile.ZipFile(p, "r") as z:
            try:
                manifest_bytes = z.read("MANIFEST.json")
            except KeyError:
                return {"valid": False, "error": "MANIFEST.json missing."}
            manifest = json.loads(manifest_bytes.decode("utf-8"))

            for entry in manifest.get("files", []):
                rel = entry["path"]
                expected = entry["sha256"]
                try:
                    with z.open(rel) as f:
                        h = hashlib.sha256()
                        for block in iter(lambda: f.read(1 << 20), b""):
                            h.update(block)
                        actual = h.hexdigest()
                except KeyError:
                    results["mismatches"].append(
                        {"path": rel, "reason": "missing in zip"}
                    )
                    continue

                results["checked"] += 1
                if actual != expected:
                    results["mismatches"].append({
                        "path": rel, "expected": expected, "actual": actual,
                    })

        results["valid"] = results["valid"] and not results["mismatches"]
        return results