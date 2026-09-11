# -*- coding: utf-8 -*-
"""Management and statistical HTML reports sliced by unit, contractor, material and service."""

from __future__ import annotations

import html
import logging
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from config import EXPORT_DIR
from db.models import (
    Area,
    LineListItem,
    NDTRecord,
    Project,
    PunchItem,
    Spool,
    TestPackage,
    Weld,
)

logger = logging.getLogger(__name__)

UNASSIGNED = "Unassigned"

ACCEPTED_STATUSES = {
    "NDT_CLEARED",
    "NDT Accepted",
    "NDT_ACCEPTED",
    "COMPLETED",
    "Completed",
    "Accepted",
    "Tested",
}
REPAIR_STATUSES = {
    "REPAIR_REQUIRED",
    "VT_REJECTED",
    "Rejected",
    "Repair",
}
AWAITING_NDT_STATUSES = {
    "WELDED",
    "Welded",
    "WELDED_VT_PENDING",
    "NDT_REQUESTED",
    "VT_ACCEPTED",
}
PASSED_PACKAGE_STATUSES = {"Passed", "PASSED", "Tested", "Complete", "Completed"}
FAIL_NDT = {"fail", "failed", "rejected", "rej"}
PASS_NDT = {"pass", "passed", "accepted", "acc"}

SLICE_SPECS = (
    ("by_unit", "By Unit / Area", "How welding and quality are moving in each plant unit."),
    ("by_contractor", "By Contractor", "Workload and repair pressure on each executing contractor."),
    ("by_material", "By Pipe Material", "Progress and repairs by base material / grade."),
    ("by_service", "By Fluid Service", "Where each process service sits in the execution chain."),
    ("by_pipe_class", "By Pipe Class", "Class mix and the joints still waiting NDT."),
    ("by_nps", "By NPS Band", "Size-band workload — large-bore joints dominate dia-inch."),
    ("quality_and_test", "Quality, NDT and Test Packages", "Inspection results, punch and hydro readiness."),
)


def nps_to_dia_inch(value: Any) -> float:
    """Parse NPS / size text into a dia-inch float. Unknown values become 0."""
    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number == number else 0.0
    text = str(value).strip().upper()
    if not text:
        return 0.0
    text = (
        text.replace("NPS", " ")
        .replace("DN", " ")
        .replace('"', " ")
        .replace("″", " ")
        .replace("''", " ")
        .replace("INCH", " ")
        .replace("IN", " ")
    )
    text = re.sub(r"[A-Z]+", " ", text)
    compact = re.sub(r"\s+", "", text)
    mixed = re.match(r"^(\d+)[-/](\d+)/(\d+)$", compact)
    if mixed:
        return float(mixed.group(1)) + float(mixed.group(2)) / float(mixed.group(3))
    fraction = re.match(r"^(\d+)/(\d+)$", compact)
    if fraction:
        denom = float(fraction.group(2))
        return float(fraction.group(1)) / denom if denom else 0.0
    try:
        return float(compact)
    except ValueError:
        found = re.search(r"(\d+(?:\.\d+)?)", str(value))
        return float(found.group(1)) if found else 0.0


def nps_band(dia_inch: float) -> str:
    if dia_inch <= 0:
        return "Size not stated"
    if dia_inch <= 2:
        return "≤ 2 in"
    if dia_inch <= 6:
        return "2–6 in"
    if dia_inch <= 12:
        return "6–12 in"
    return "> 12 in"


def _label(raw: Any, fallback: str = UNASSIGNED) -> str:
    text = " ".join(str(raw or "").split())
    return text if text else fallback


def _norm_key(label: str) -> str:
    return label.casefold()


def _pct(part: float, whole: float) -> float:
    if whole <= 0:
        return 0.0
    return round(part / whole * 100, 1)


def _is_accepted(status: Optional[str]) -> bool:
    return (status or "") in ACCEPTED_STATUSES


def _is_repair(status: Optional[str], repair_count: int) -> bool:
    return (status or "") in REPAIR_STATUSES or repair_count > 0


def _is_awaiting_ndt(status: Optional[str]) -> bool:
    return (status or "") in AWAITING_NDT_STATUSES


def build_management_snapshot(db, project_id: int) -> dict[str, Any]:
    """Load the live register once and derive every management slice."""
    with db.session_scope() as session:
        project = session.get(Project, project_id)
        project_name = (
            f"{project.project_code} – {project.title}" if project else f"Project {project_id}"
        )
        project_meta = {
            "code": getattr(project, "project_code", "") or "",
            "title": getattr(project, "title", "") or "",
            "client": getattr(project, "client", "") or "",
            "contractor": getattr(project, "contractor", "") or "",
            "status": getattr(project, "status", "") or "",
        }
        areas = {
            row.id: row.name
            for row in session.query(Area).filter(Area.project_id == project_id).all()
        }
        lines = session.query(LineListItem).filter(LineListItem.project_id == project_id).all()
        line_by_number = {row.line_number: row for row in lines if row.line_number}
        welds = session.query(Weld).filter(Weld.project_id == project_id).all()
        ndt_rows = (
            session.query(NDTRecord)
            .join(Weld, NDTRecord.weld_id == Weld.id)
            .filter(Weld.project_id == project_id)
            .all()
        )
        spools = session.query(Spool).filter(Spool.project_id == project_id).all()
        packages = session.query(TestPackage).filter(TestPackage.project_id == project_id).all()
        punches = session.query(PunchItem).filter(PunchItem.project_id == project_id).all()

        weld_rows = []
        for weld in welds:
            line = line_by_number.get(weld.line_number)
            dia = nps_to_dia_inch(getattr(weld, "size_nps", None))
            unit = _label(weld.area_name) if (weld.area_name or "").strip() else _label(
                areas.get(weld.area_id)
            )
            material = _label(weld.base_material) if (weld.base_material or "").strip() else _label(
                getattr(line, "material", None)
            )
            service = _label(weld.line_service) if (weld.line_service or "").strip() else _label(
                getattr(line, "fluid_service", None)
            )
            pipe_class = _label(weld.pipe_class) if (weld.pipe_class or "").strip() else _label(
                getattr(line, "pipe_class", None)
            )
            contractor = _label(weld.contractor) if (weld.contractor or "").strip() else _label(
                project_meta["contractor"]
            )
            repair_count = int(getattr(weld, "repair_count", 0) or 0)
            weld_rows.append(
                {
                    "unit": unit,
                    "contractor": contractor,
                    "material": material,
                    "service": service,
                    "pipe_class": pipe_class,
                    "nps_band": nps_band(dia),
                    "dia_inch": dia,
                    "status": weld.status or "Unknown",
                    "repair_count": repair_count,
                    "accepted": _is_accepted(weld.status),
                    "repair": _is_repair(weld.status, repair_count),
                    "awaiting_ndt": _is_awaiting_ndt(weld.status),
                    "on_hold": bool(getattr(weld, "is_on_hold", False)),
                    "weld_type": weld.weld_type or UNASSIGNED,
                }
            )

        ndt = []
        for rec in ndt_rows:
            result = (rec.result or "Pending").strip()
            ndt.append(
                {
                    "method": (rec.ndt_method or "UNK").upper().strip(),
                    "result": result,
                    "fail": result.lower() in FAIL_NDT,
                    "pass": result.lower() in PASS_NDT,
                }
            )

        spool_rows = [
            {
                "status": sp.status or "Unknown",
                "erected": (sp.status or "") in ("Installed", "Tested", "ERECTED", "Erected"),
            }
            for sp in spools
        ]
        package_rows = [
            {
                "number": pkg.package_number,
                "status": pkg.status or "Unknown",
                "unit": _label(pkg.area_name) if (pkg.area_name or "").strip() else _label(
                    areas.get(pkg.area_id)
                ),
                "passed": (pkg.status or "") in PASSED_PACKAGE_STATUSES,
                "punch_a": int(pkg.punch_a_count or 0),
                "punch_b": int(pkg.punch_b_count or 0),
                "punch_c": int(pkg.punch_c_count or 0),
            }
            for pkg in packages
        ]
        punch_rows = [
            {
                "category": (item.category or "?").upper(),
                "cleared": bool(item.is_cleared) or (item.status or "") in ("Cleared", "Closed"),
                "status": item.status or "Open",
            }
            for item in punches
        ]

    groups = {
        "by_unit": _group_welds(weld_rows, "unit"),
        "by_contractor": _group_welds(weld_rows, "contractor"),
        "by_material": _group_welds(weld_rows, "material"),
        "by_service": _group_welds(weld_rows, "service"),
        "by_pipe_class": _group_welds(weld_rows, "pipe_class"),
        "by_nps": _group_welds(weld_rows, "nps_band"),
        "by_status": _group_welds(weld_rows, "status"),
        "by_weld_type": _group_welds(weld_rows, "weld_type"),
    }
    totals = _totals(weld_rows, ndt, spool_rows, package_rows, punch_rows, len(lines))
    return {
        "project_id": project_id,
        "project_name": project_name,
        "project_meta": project_meta,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "groups": groups,
        "totals": totals,
        "ndt_by_method": _ndt_by_method(ndt),
        "packages": package_rows,
        "cross_unit_contractor": _cross_table(weld_rows, "unit", "contractor"),
        "findings": _findings(groups, totals, package_rows),
    }


def _empty_bucket(label: str) -> dict[str, Any]:
    return {
        "label": label,
        "welds": 0,
        "dia_inch": 0.0,
        "accepted": 0,
        "accepted_di": 0.0,
        "repaired": 0,
        "awaiting_ndt": 0,
        "on_hold": 0,
        "progress_pct": 0.0,
        "repair_pct": 0.0,
    }


def _group_welds(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        label = _label(row.get(field))
        key = _norm_key(label)
        if key not in buckets:
            buckets[key] = _empty_bucket(label)
            order.append(key)
        bucket = buckets[key]
        bucket["welds"] += 1
        bucket["dia_inch"] += row["dia_inch"]
        if row["accepted"]:
            bucket["accepted"] += 1
            bucket["accepted_di"] += row["dia_inch"]
        if row["repair"]:
            bucket["repaired"] += 1
        if row["awaiting_ndt"]:
            bucket["awaiting_ndt"] += 1
        if row["on_hold"]:
            bucket["on_hold"] += 1
    result = []
    for key in order:
        bucket = buckets[key]
        bucket["dia_inch"] = round(bucket["dia_inch"], 2)
        bucket["accepted_di"] = round(bucket["accepted_di"], 2)
        bucket["progress_pct"] = _pct(bucket["accepted_di"], bucket["dia_inch"]) or _pct(
            bucket["accepted"], bucket["welds"]
        )
        bucket["repair_pct"] = _pct(bucket["repaired"], bucket["welds"])
        result.append(bucket)
    result.sort(key=lambda item: (-item["dia_inch"], -item["welds"], item["label"]))
    return result


def _totals(welds, ndt, spools, packages, punches, line_count: int) -> dict[str, Any]:
    weld_count = len(welds)
    dia = round(sum(row["dia_inch"] for row in welds), 2)
    accepted = sum(1 for row in welds if row["accepted"])
    accepted_di = round(sum(row["dia_inch"] for row in welds if row["accepted"]), 2)
    repaired = sum(1 for row in welds if row["repair"])
    awaiting = sum(1 for row in welds if row["awaiting_ndt"])
    holds = sum(1 for row in welds if row["on_hold"])
    ndt_fail = sum(1 for row in ndt if row["fail"])
    ndt_pass = sum(1 for row in ndt if row["pass"])
    erected = sum(1 for row in spools if row["erected"])
    pkg_passed = sum(1 for row in packages if row["passed"])
    punch_open_a = sum(
        1 for row in punches if row["category"].startswith("A") and not row["cleared"]
    )
    return {
        "lines": line_count,
        "welds": weld_count,
        "dia_inch": dia,
        "accepted": accepted,
        "accepted_di": accepted_di,
        "progress_pct": _pct(accepted_di, dia) or _pct(accepted, weld_count),
        "repaired": repaired,
        "repair_pct": _pct(repaired, weld_count),
        "awaiting_ndt": awaiting,
        "on_hold": holds,
        "ndt_total": len(ndt),
        "ndt_pass": ndt_pass,
        "ndt_fail": ndt_fail,
        "ndt_pass_pct": _pct(ndt_pass, len(ndt)),
        "spools": len(spools),
        "spools_erected": erected,
        "packages": len(packages),
        "packages_passed": pkg_passed,
        "punch_open_a": punch_open_a,
        "punches": len(punches),
        "punches_open": sum(1 for row in punches if not row["cleared"]),
    }


def _ndt_by_method(ndt: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0, "other": 0})
    for row in ndt:
        bucket = buckets[row["method"]]
        bucket["total"] += 1
        if row["pass"]:
            bucket["pass"] += 1
        elif row["fail"]:
            bucket["fail"] += 1
        else:
            bucket["other"] += 1
    rows = []
    for method, bucket in sorted(buckets.items()):
        rows.append(
            {
                "label": method,
                "total": bucket["total"],
                "pass": bucket["pass"],
                "fail": bucket["fail"],
                "other": bucket["other"],
                "pass_pct": _pct(bucket["pass"], bucket["total"]),
            }
        )
    return rows


def _cross_table(
    welds: list[dict[str, Any]], row_field: str, col_field: str, limit: int = 12
) -> dict[str, Any] | None:
    row_labels = []
    col_labels = []
    seen_rows: set[str] = set()
    seen_cols: set[str] = set()
    for weld in welds:
        r = _label(weld[row_field])
        c = _label(weld[col_field])
        if _norm_key(r) not in seen_rows:
            seen_rows.add(_norm_key(r))
            row_labels.append(r)
        if _norm_key(c) not in seen_cols:
            seen_cols.add(_norm_key(c))
            col_labels.append(c)
    if not (2 <= len(row_labels) <= limit and 2 <= len(col_labels) <= limit):
        return None
    grid = {
        (_norm_key(r), _norm_key(c)): {"welds": 0, "accepted": 0}
        for r in row_labels
        for c in col_labels
    }
    for weld in welds:
        cell = grid[(_norm_key(_label(weld[row_field])), _norm_key(_label(weld[col_field])))]
        cell["welds"] += 1
        if weld["accepted"]:
            cell["accepted"] += 1
    return {"rows": row_labels, "cols": col_labels, "cells": grid}


def _findings(
    groups: dict[str, list[dict[str, Any]]],
    totals: dict[str, Any],
    packages: list[dict[str, Any]],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if totals["welds"] == 0:
        findings.append(
            {
                "severity": "Medium",
                "title": "No weld register yet",
                "evidence": "This project has no joints in the execution register.",
                "action": "Load the weld map / joint history before using management analytics.",
            }
        )
        return findings

    units = [row for row in groups["by_unit"] if row["welds"] >= 3]
    if units:
        lag = min(units, key=lambda row: (row["progress_pct"], -row["welds"]))
        lead = max(units, key=lambda row: (row["progress_pct"], row["welds"]))
        if lag["progress_pct"] + 15 <= lead["progress_pct"]:
            findings.append(
                {
                    "severity": "High",
                    "title": f"{lag['label']} is lagging other units",
                    "evidence": (
                        f"{lag['label']} is at {lag['progress_pct']}% accepted dia-inch "
                        f"({lag['accepted']}/{lag['welds']} joints) versus "
                        f"{lead['label']} at {lead['progress_pct']}%."
                    ),
                    "action": "Protect crew and NDT capacity on the lagging unit before hydro windows slip.",
                }
            )

    contractors = [row for row in groups["by_contractor"] if row["welds"] >= 3]
    if contractors:
        worst = max(contractors, key=lambda row: (row["repair_pct"], row["repaired"]))
        if worst["repair_pct"] >= 5:
            findings.append(
                {
                    "severity": "High",
                    "title": f"Repair pressure on {worst['label']}",
                    "evidence": (
                        f"{worst['label']} has a {worst['repair_pct']}% repair rate "
                        f"({worst['repaired']} of {worst['welds']} joints)."
                    ),
                    "action": "Review WPS fit, welder qualification and repeat defect type with that contractor.",
                }
            )

    services = [row for row in groups["by_service"] if row["awaiting_ndt"] >= 5]
    if services:
        queued = max(services, key=lambda row: row["awaiting_ndt"])
        findings.append(
            {
                "severity": "High",
                "title": f"NDT queue on service {queued['label']}",
                "evidence": (
                    f"{queued['awaiting_ndt']} welded joints on {queued['label']} are waiting NDT."
                ),
                "action": "Raise NDT requests by line criticality for this service before the hydro package is boxed.",
            }
        )

    materials = groups["by_material"]
    if materials and totals["dia_inch"] > 0:
        top = materials[0]
        share = _pct(top["dia_inch"], totals["dia_inch"])
        if share >= 60 and top["label"] != UNASSIGNED:
            findings.append(
                {
                    "severity": "Medium",
                    "title": f"{top['label']} dominates the pipe material mix",
                    "evidence": f"{share}% of recorded dia-inch is {top['label']}.",
                    "action": "Confirm WPS coverage and filler stock for this grade before the next campaign.",
                }
            )

    if totals["punch_open_a"] > 0:
        findings.append(
            {
                "severity": "High",
                "title": "Open category-A punches are blocking hydro",
                "evidence": f"{totals['punch_open_a']} category-A punch item(s) are still open.",
                "action": "Clear A-punches on the next test packages before scheduling hydrotest.",
            }
        )

    blocked_pkg = [
        pkg for pkg in packages if (not pkg["passed"]) and pkg["punch_a"] > 0
    ]
    if blocked_pkg:
        names = ", ".join(pkg["number"] for pkg in blocked_pkg[:5])
        findings.append(
            {
                "severity": "High",
                "title": "Test packages held by A-punches",
                "evidence": f"{len(blocked_pkg)} package(s) still carry A-punches: {names}.",
                "action": "Close the A-list and re-verify line check before the test window.",
            }
        )

    if totals["on_hold"] >= 3:
        findings.append(
            {
                "severity": "Medium",
                "title": "Joints on hold",
                "evidence": f"{totals['on_hold']} joints are flagged on hold.",
                "action": "Walk the hold list (material, TQ, access) so fit-up crews are not starved.",
            }
        )

    if totals["awaiting_ndt"] >= 15:
        findings.append(
            {
                "severity": "High",
                "title": "Site-wide NDT backlog",
                "evidence": f"{totals['awaiting_ndt']} welded joints are awaiting NDT.",
                "action": "Increase NDT coverage or freeze further welding on non-critical lines.",
            }
        )

    if not findings:
        findings.append(
            {
                "severity": "Low",
                "title": "No material control exception in this slice",
                "evidence": "Repair rate, NDT queue and unit spread are inside the default watch limits.",
                "action": "Keep weekly review of unit and contractor slices as the weld map grows.",
            }
        )
    return findings


def _esc(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _bar(pct: float) -> str:
    width = max(0, min(100, pct))
    return (
        f'<div class="bar" title="{width}%">'
        f'<i style="width:{width}%"></i></div>'
        f'<span class="bar-n">{width}%</span>'
    )


def _kpi_cards(totals: dict[str, Any]) -> str:
    cards = [
        ("Joints", str(totals["welds"]), f"{totals['dia_inch']:.1f} dia-inch"),
        ("Accepted progress", f"{totals['progress_pct']}%", f"{totals['accepted']} joints"),
        ("Repair rate", f"{totals['repair_pct']}%", f"{totals['repaired']} repaired"),
        ("Awaiting NDT", str(totals["awaiting_ndt"]), "welded, not cleared"),
        ("NDT pass", f"{totals['ndt_pass_pct']}%", f"{totals['ndt_pass']}/{totals['ndt_total']}"),
        ("Test packages", f"{totals['packages_passed']}/{totals['packages']}", "passed / total"),
    ]
    cells = []
    for title, value, note in cards:
        cells.append(
            f'<div class="kpi"><div class="l">{_esc(title)}</div>'
            f'<div class="n">{_esc(value)}</div>'
            f'<div class="s">{_esc(note)}</div></div>'
        )
    return '<div class="kpis">' + "".join(cells) + "</div>"


def _findings_html(findings: list[dict[str, str]]) -> str:
    if not findings:
        return "<p class='note'>No analytical findings for this project yet.</p>"
    blocks = []
    for item in findings:
        high = " high" if item["severity"] == "High" else ""
        blocks.append(
            f"<div class='hint{high}'><b>{_esc(item['severity'])} · {_esc(item['title'])}</b>"
            f"<br>{_esc(item['evidence'])}"
            f"<br><b>Next action:</b> {_esc(item['action'])}</div>"
        )
    return "".join(blocks)


def _group_table(rows: list[dict[str, Any]], label_header: str) -> str:
    if not rows:
        return "<p class='note'>No records in this slice.</p>"
    head = (
        f"<table><tr><th>{_esc(label_header)}</th><th>Joints</th><th>Dia-inch</th>"
        "<th>Accepted</th><th>Progress</th><th>Repairs</th><th>Repair %</th>"
        "<th>Awaiting NDT</th><th>On hold</th></tr>"
    )
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{_esc(row['label'])}</td>"
            f"<td>{row['welds']}</td>"
            f"<td>{row['dia_inch']:.1f}</td>"
            f"<td>{row['accepted']}</td>"
            f"<td>{_bar(row['progress_pct'])}</td>"
            f"<td>{row['repaired']}</td>"
            f"<td>{row['repair_pct']}%</td>"
            f"<td>{row['awaiting_ndt']}</td>"
            f"<td>{row['on_hold']}</td>"
            "</tr>"
        )
    return head + "".join(body) + "</table>"


def _ndt_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p class='note'>No NDT records on this project yet.</p>"
    html_rows = [
        "<table><tr><th>Method</th><th>Tests</th><th>Pass</th><th>Fail</th>"
        "<th>Other / pending</th><th>Pass %</th></tr>"
    ]
    for row in rows:
        html_rows.append(
            "<tr>"
            f"<td>{_esc(row['label'])}</td>"
            f"<td>{row['total']}</td>"
            f"<td>{row['pass']}</td>"
            f"<td>{row['fail']}</td>"
            f"<td>{row['other']}</td>"
            f"<td>{_bar(row['pass_pct'])}</td>"
            "</tr>"
        )
    return "".join(html_rows) + "</table>"


def _package_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p class='note'>No test packages on this project yet.</p>"
    html_rows = [
        "<table><tr><th>Package</th><th>Unit</th><th>Status</th>"
        "<th>A punches</th><th>B</th><th>C</th></tr>"
    ]
    for row in rows:
        html_rows.append(
            "<tr>"
            f"<td>{_esc(row['number'])}</td>"
            f"<td>{_esc(row['unit'])}</td>"
            f"<td>{_esc(row['status'])}</td>"
            f"<td>{row['punch_a']}</td>"
            f"<td>{row['punch_b']}</td>"
            f"<td>{row['punch_c']}</td>"
            "</tr>"
        )
    return "".join(html_rows) + "</table>"


def _cross_html(cross: dict[str, Any] | None) -> str:
    if not cross:
        return ""
    head = "<tr><th>Unit \\ Contractor</th>" + "".join(
        f"<th>{_esc(col)}</th>" for col in cross["cols"]
    ) + "</tr>"
    body = []
    for row in cross["rows"]:
        cells = [f"<td>{_esc(row)}</td>"]
        for col in cross["cols"]:
            cell = cross["cells"][(_norm_key(row), _norm_key(col))]
            if cell["welds"] == 0:
                cells.append("<td class='muted'>—</td>")
            else:
                cells.append(
                    f"<td>{cell['accepted']}/{cell['welds']}</td>"
                )
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        "<h2>Unit × contractor (accepted / joints)</h2>"
        "<table>" + head + "".join(body) + "</table>"
    )


def _intro(snapshot: dict[str, Any], subtitle: str) -> str:
    meta = snapshot["project_meta"]
    return f"""
    <p class="note">Management and statistical report — not a construction or QC acceptance document.
    Figures are taken from the live execution register.</p>
    <div class="cover-meta">
      <div><span class="label">Project:</span> {_esc(snapshot['project_name'])}</div>
      <div><span class="label">Status:</span> {_esc(meta.get('status'))}</div>
      <div><span class="label">Client:</span> {_esc(meta.get('client'))}</div>
      <div><span class="label">Main contractor:</span> {_esc(meta.get('contractor'))}</div>
      <div><span class="label">Generated:</span> {_esc(snapshot['generated_at'])}</div>
      <div><span class="label">Slice:</span> {_esc(subtitle)}</div>
    </div>
    """


def render_index_body(snapshot: dict[str, Any]) -> str:
    groups = snapshot["groups"]
    totals = snapshot["totals"]
    toc = "".join(
        f"<li><a href='{key}.html'>{_esc(title)}</a> — {_esc(blurb)}</li>"
        for key, title, blurb in SLICE_SPECS
    )
    sections = [
        "<h1>Management Analytics Pack</h1>",
        _intro(snapshot, "Full pack"),
        "<h2>Execution snapshot</h2>",
        _kpi_cards(totals),
        "<h2>Analytical findings</h2>",
        _findings_html(snapshot["findings"]),
        "<h2>Reports in this pack</h2>",
        f"<ol class='toc'>{toc}</ol>",
        "<h2>By unit / area</h2>",
        _group_table(groups["by_unit"], "Unit"),
        "<h2>By contractor</h2>",
        _group_table(groups["by_contractor"], "Contractor"),
        "<h2>By pipe material</h2>",
        _group_table(groups["by_material"], "Material"),
        "<h2>By fluid service</h2>",
        _group_table(groups["by_service"], "Service"),
        _cross_html(snapshot["cross_unit_contractor"]),
        "<p class='note'>Open the linked files in this folder to print one slice, or print this index for the full pack.</p>",
    ]
    return "".join(sections)


def render_slice_body(snapshot: dict[str, Any], key: str) -> str:
    spec = next(item for item in SLICE_SPECS if item[0] == key)
    _, title, blurb = spec
    parts = [
        f"<h1>{_esc(title)}</h1>",
        _intro(snapshot, title),
        f"<p>{_esc(blurb)}</p>",
        _kpi_cards(snapshot["totals"]),
    ]
    if key == "quality_and_test":
        parts.extend(
            [
                "<h2>Analytical findings</h2>",
                _findings_html(snapshot["findings"]),
                "<h2>NDT by method</h2>",
                _ndt_table(snapshot["ndt_by_method"]),
                "<h2>Joints by status</h2>",
                _group_table(snapshot["groups"]["by_status"], "Status"),
                "<h2>Shop / field mix</h2>",
                _group_table(snapshot["groups"]["by_weld_type"], "Weld type"),
                "<h2>Test packages</h2>",
                _package_table(snapshot["packages"]),
            ]
        )
    else:
        header = {
            "by_unit": "Unit",
            "by_contractor": "Contractor",
            "by_material": "Pipe material",
            "by_service": "Fluid service",
            "by_pipe_class": "Pipe class",
            "by_nps": "NPS band",
        }[key]
        parts.extend(
            [
                f"<h2>{_esc(title)}</h2>",
                _group_table(snapshot["groups"][key], header),
                "<h2>Findings that touch this slice</h2>",
                _findings_html(snapshot["findings"]),
            ]
        )
        if key == "by_unit":
            parts.append(_cross_html(snapshot["cross_unit_contractor"]))
    parts.append("<p class='note'><a href='index.html'>Back to pack index</a></p>")
    return "".join(parts)


def write_management_pack(
    html_shell: Callable[..., str],
    project_id: int,
    snapshot: dict[str, Any],
    *,
    export_dir: Optional[Path] = None,
) -> str:
    """Write index + slice HTML files. Returns the index path."""
    folder = Path(export_dir or EXPORT_DIR) / "html_reports" / (
        f"PipeAgent_Management_P{project_id}_{date.today().isoformat()}"
    )
    folder.mkdir(parents=True, exist_ok=True)
    name = snapshot["project_name"]
    index_body = render_index_body(snapshot)
    index_path = folder / "index.html"
    index_path.write_text(
        html_shell(f"Management Analytics — {name}", index_body),
        encoding="utf-8",
    )
    for key, title, _blurb in SLICE_SPECS:
        path = folder / f"{key}.html"
        path.write_text(
            html_shell(f"{title} — {name}", render_slice_body(snapshot, key)),
            encoding="utf-8",
        )
    logger.info("Wrote management analytics pack for project %s to %s", project_id, folder)
    return str(index_path)


def group_rows_as_dicts(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten grouping rows for Excel export."""
    return [
        {
            "Group": row["label"],
            "Joints": row["welds"],
            "Dia-inch": row["dia_inch"],
            "Accepted": row["accepted"],
            "Progress %": row["progress_pct"],
            "Repaired": row["repaired"],
            "Repair %": row["repair_pct"],
            "Awaiting NDT": row["awaiting_ndt"],
            "On hold": row["on_hold"],
        }
        for row in rows
    ]
