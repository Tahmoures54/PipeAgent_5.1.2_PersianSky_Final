# -*- coding: utf-8 -*-
"""
ASME B31.3 / IX code-compliance engine.

Closes the gap vs Weld-Console, Welding Manager and WeldTrace:

- NDE extent vs line-list percent (RT/UT/PT/MT), by joint and NPS-inch
- Deterministic (auditable) lot selection until the required percent is met
- Progressive examination: a rejected spot exam pulls two more joints from
  the same welder; a second reject escalates the remainder of that lot
- Hydrotest package clearance against real weld/punch/PWHT/NDE evidence
- Welder continuity countdown (ASME IX QW-322, 6 months)

Recommendations are advisory. They never auto-approve QC or engineering.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy.orm import Session

from db.manager import DatabaseManager
from db.models import (
    LineListItem,
    NDTRecord,
    PunchItem,
    SpringHangerRecord,
    TestPackage,
    TestPackageWeld,
    Weld,
    Welder,
)

logger = logging.getLogger(__name__)

NDE_METHODS = ("RT", "UT", "PT", "MT")
CONTINUITY_DAYS = 180
CONTINUITY_WARN_DAYS = 150
PROGRESSIVE_EXTRA = 2

_ACCEPTED = {"pass", "accepted", "accept", "acc", "ok"}
_REJECTED = {"fail", "failed", "rejected", "rej", "reject"}
_NPS_RE = re.compile(r"(\d+(?:\.\d+)?)")
_NOT_ELIGIBLE = {
    "pending",
    "fitup_pending",
    "fitup_rejected",
    "cut_out",
    "cut out",
    "cancelled",
    "canceled",
    "void",
}


def nps_inches(value: Any) -> float:
    """Parse NPS / DN text into a positive inch quantity for coverage math."""
    if value is None or value == "":
        return 1.0
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number > 0 else 1.0
    text = str(value).strip().upper().replace('"', "").replace("''", "")
    if text.startswith("DN"):
        match = _NPS_RE.search(text[2:])
        if match:
            return max(round(float(match.group(1)) / 25.4, 3), 0.5)
    match = _NPS_RE.search(text)
    if match:
        number = float(match.group(1))
        return number if number > 0 else 1.0
    return 1.0


def _bucket(result: Optional[str]) -> str:
    token = (result or "").strip().lower()
    if token in _ACCEPTED:
        return "accepted"
    if token in _REJECTED:
        return "rejected"
    if token in {"pending", "re-test", "retest", ""}:
        return "pending"
    return "other"


def _method_key(value: Optional[str]) -> str:
    text = (value or "").strip().upper()
    for method in NDE_METHODS:
        if text.startswith(method):
            return method
    return text[:10]


def _required_percent(line: Optional[LineListItem], method: str) -> float:
    if line is None:
        return 0.0
    attr = {
        "RT": "ndt_percent_rt",
        "UT": "ndt_percent_ut",
        "PT": "ndt_percent_pt",
        "MT": "ndt_percent_mt",
    }.get(method)
    if not attr:
        return 0.0
    return float(getattr(line, attr, 0) or 0)


def _eligible(weld: Weld) -> bool:
    status = (weld.status or "").strip().lower().replace("-", "_").replace(" ", "_")
    return status not in _NOT_ELIGIBLE


def _weld_number(weld: Weld) -> str:
    return getattr(weld, "weld_number", None) or getattr(weld, "weld_id", None) or f"W-{weld.id}"


def _lot_rank(weld_number: str) -> str:
    return hashlib.sha256(weld_number.encode("utf-8")).hexdigest()


def _latest_by_method(records: Sequence[NDTRecord]) -> Dict[int, Dict[str, NDTRecord]]:
    latest: Dict[int, Dict[str, NDTRecord]] = {}
    ordered = sorted(
        records,
        key=lambda rec: (
            rec.inspection_date or date.min,
            rec.id or 0,
        ),
    )
    for rec in ordered:
        weld_pk = rec.weld_id
        if weld_pk is None:
            continue
        latest.setdefault(weld_pk, {})[_method_key(rec.ndt_method)] = rec
    return latest


def line_coverage(
    session: Session,
    project_id: int,
    line_number: str,
    *,
    welds: Optional[Sequence[Weld]] = None,
    records: Optional[Sequence[NDTRecord]] = None,
) -> Dict[str, Any]:
    clean_line = (line_number or "").strip()
    line = (
        session.query(LineListItem)
        .filter(
            LineListItem.project_id == project_id,
            LineListItem.line_number == clean_line,
        )
        .first()
    )
    if welds is None:
        welds = (
            session.query(Weld)
            .filter(Weld.project_id == project_id, Weld.line_number == clean_line)
            .all()
        )
    eligible = [weld for weld in welds if _eligible(weld)]
    if records is None:
        weld_ids = [weld.id for weld in eligible]
        records = (
            session.query(NDTRecord).filter(NDTRecord.weld_id.in_(weld_ids)).all()
            if weld_ids
            else []
        )
    latest = _latest_by_method(records)
    total_inch = sum(nps_inches(getattr(weld, "size_nps", None) or getattr(weld, "dia_inch", None)) for weld in eligible)
    methods: Dict[str, Any] = {}
    deficits: List[str] = []
    for method in NDE_METHODS:
        required = _required_percent(line, method)
        accepted_ids = {
            weld.id
            for weld in eligible
            if _bucket(getattr(latest.get(weld.id, {}).get(method), "result", None)) == "accepted"
        }
        accepted_count = len(accepted_ids)
        accepted_inch = sum(
            nps_inches(getattr(weld, "size_nps", None) or getattr(weld, "dia_inch", None))
            for weld in eligible
            if weld.id in accepted_ids
        )
        joint_pct = round(accepted_count / len(eligible) * 100, 2) if eligible else 100.0
        inch_pct = round(accepted_inch / total_inch * 100, 2) if total_inch else 100.0
        needed = math.ceil(required / 100.0 * len(eligible)) if required > 0 else 0
        shortfall = max(0, needed - accepted_count)
        compliant = required <= 0 or joint_pct >= required or (eligible == [])
        methods[method] = {
            "required_percent": required,
            "accepted_welds": accepted_count,
            "needed_welds": needed,
            "shortfall_welds": shortfall,
            "actual_joint_percent": joint_pct,
            "actual_dia_inch_percent": inch_pct,
            "compliant": compliant,
        }
        if not compliant:
            deficits.append(f"{method} {joint_pct}% vs required {required}%")
    return {
        "project_id": project_id,
        "line_number": clean_line,
        "pipe_class": getattr(line, "pipe_class", None) if line else None,
        "total_welds": len(eligible),
        "total_dia_inch": round(total_inch, 2),
        "methods": methods,
        "deficits": deficits,
        "compliant": not deficits,
        "status": "COMPLIANT" if not deficits else "DEFICIT",
        # Back-compat keys used by NDTService.evaluate_line_ndt_coverage
        "required_rt_percent": methods["RT"]["required_percent"],
        "actual_rt_joint_percent": methods["RT"]["actual_joint_percent"],
        "actual_rt_dia_inch_percent": methods["RT"]["actual_dia_inch_percent"],
        "is_coverage_satisfied": methods["RT"]["compliant"] if methods["RT"]["required_percent"] > 0 else True,
    }


def select_nde_lots(
    session: Session,
    project_id: int,
) -> Dict[str, Any]:
    welds = session.query(Weld).filter(Weld.project_id == project_id).all()
    by_line: Dict[str, List[Weld]] = {}
    for weld in welds:
        if not _eligible(weld):
            continue
        by_line.setdefault((weld.line_number or "").strip() or "(unassigned)", []).append(weld)

    weld_ids = [weld.id for group in by_line.values() for weld in group]
    records = (
        session.query(NDTRecord).filter(NDTRecord.weld_id.in_(weld_ids)).all()
        if weld_ids
        else []
    )
    latest = _latest_by_method(records)
    selected: List[Dict[str, Any]] = []
    coverage_rows: List[Dict[str, Any]] = []

    for line_number, line_welds in sorted(by_line.items()):
        coverage = line_coverage(
            session, project_id, line_number, welds=line_welds, records=records,
        )
        coverage_rows.append(coverage)
        for method in NDE_METHODS:
            method_cov = coverage["methods"][method]
            required = method_cov["required_percent"]
            if required <= 0:
                continue

            def _state(weld: Weld) -> str:
                rec = latest.get(weld.id, {}).get(method)
                return _bucket(getattr(rec, "result", None))

            rejected_welders: Set[str] = set()
            penalty_failed_welders: Set[str] = set()
            for weld in line_welds:
                rec = latest.get(weld.id, {}).get(method)
                if rec is None or _bucket(rec.result) != "rejected":
                    continue
                welder = (weld.welder_id or "").strip()
                if not welder:
                    continue
                rejected_welders.add(welder)
                if getattr(rec, "is_penalty", False):
                    penalty_failed_welders.add(welder)

            picked_ids: Set[int] = set()
            for welder in sorted(rejected_welders):
                extras = [
                    item for item in line_welds
                    if (item.welder_id or "").strip() == welder
                    and _state(item) in {"pending", "other"}
                ]
                extras.sort(key=lambda item: _lot_rank(_weld_number(item)))
                reason = "progressive_100pct" if welder in penalty_failed_welders else "progressive_extra"
                limit = len(extras) if welder in penalty_failed_welders else PROGRESSIVE_EXTRA
                for item in extras[:limit]:
                    selected.append(_selection_row(item, method, reason, coverage))
                    picked_ids.add(item.id)

            untested = [
                weld for weld in line_welds
                if _state(weld) in {"pending", "other"} and weld.id not in picked_ids
            ]
            untested.sort(key=lambda weld: _lot_rank(_weld_number(weld)))
            still_need = max(0, method_cov["shortfall_welds"] - len(picked_ids))
            for weld in untested[:still_need]:
                selected.append(_selection_row(weld, method, "coverage_percent", coverage))
                picked_ids.add(weld.id)

    selected.sort(key=lambda row: (row["reason"] != "progressive_100pct", row["line_number"], row["weld_number"]))
    return {
        "project_id": project_id,
        "selected_count": len(selected),
        "selected": selected,
        "coverage": coverage_rows,
        "deficit_lines": [row["line_number"] for row in coverage_rows if not row["compliant"]],
        "rule": (
            "ASME B31.3 examination extent from the line list, with deterministic "
            "lot selection and progressive extra exams after a rejected spot test."
        ),
    }


def _selection_row(weld: Weld, method: str, reason: str, coverage: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "weld_id": weld.id,
        "weld_number": _weld_number(weld),
        "line_number": weld.line_number,
        "welder_id": weld.welder_id,
        "size_nps": getattr(weld, "size_nps", None),
        "method": method,
        "reason": reason,
        "required_percent": coverage["methods"][method]["required_percent"],
        "status": weld.status,
    }


def hydrotest_clearance(session: Session, test_package_id: int) -> Dict[str, Any]:
    package = session.get(TestPackage, test_package_id)
    if package is None:
        return {
            "can_proceed": False,
            "blockers": [f"Test package #{test_package_id} was not found."],
            "warnings": [],
            "package_number": None,
        }

    linked_ids = [
        row.weld_id
        for row in session.query(TestPackageWeld).filter(
            TestPackageWeld.test_package_id == test_package_id
        ).all()
    ]
    welds: List[Weld] = []
    if linked_ids:
        welds = session.query(Weld).filter(Weld.id.in_(linked_ids)).all()
    lines_raw = (package.line_numbers or "").replace(";", ",")
    package_lines = [item.strip() for item in lines_raw.split(",") if item.strip()]
    if not welds and package_lines:
        welds = (
            session.query(Weld)
            .filter(Weld.project_id == package.project_id, Weld.line_number.in_(package_lines))
            .all()
        )
    line_numbers = sorted({(weld.line_number or "").strip() for weld in welds if weld.line_number} | set(package_lines))

    blockers: List[str] = []
    warnings: List[str] = []

    punch_q = session.query(PunchItem).filter(
        PunchItem.project_id == package.project_id,
        PunchItem.category.in_(["A", "a"]),
        PunchItem.is_cleared.is_(False),
        PunchItem.status.notin_(["Closed", "Cancelled", "Canceled", "CLIENT_ACCEPTED"]),
    )
    punch_filters = [PunchItem.test_package_id == test_package_id]
    if line_numbers:
        punch_filters.append(PunchItem.line_number.in_(line_numbers))
    from sqlalchemy import or_
    open_punch_a = punch_q.filter(or_(*punch_filters)).all()
    if open_punch_a:
        blockers.append(
            f"{len(open_punch_a)} open Category-A punch item(s) remain on package "
            f"'{package.package_number}'."
        )

    weld_ids = [weld.id for weld in welds]
    records = session.query(NDTRecord).filter(NDTRecord.weld_id.in_(weld_ids)).all() if weld_ids else []
    latest = _latest_by_method(records)
    line_pwht = {}
    if line_numbers:
        for item in session.query(LineListItem).filter(
            LineListItem.project_id == package.project_id,
            LineListItem.line_number.in_(line_numbers),
        ).all():
            line_pwht[item.line_number] = bool(item.pwht_required)

    for weld in welds:
        label = _weld_number(weld)
        for method, rec in latest.get(weld.id, {}).items():
            if _bucket(rec.result) == "rejected":
                blockers.append(
                    f"Weld '{label}' has rejected {method} and is not cleared for hydrotest."
                )
        if weld.status in {"REPAIR_REQUIRED", "VT_REJECTED", "CUT_OUT"}:
            blockers.append(f"Weld '{label}' is still in status {weld.status}.")
        if line_pwht.get(weld.line_number) and not weld.pwht_done:
            blockers.append(f"Weld '{label}' still requires PWHT before hydrotest.")

    for line_number in line_numbers:
        coverage = line_coverage(session, package.project_id, line_number)
        if not coverage["compliant"]:
            blockers.append(
                f"Line '{line_number}' NDE coverage is short: {', '.join(coverage['deficits'])}."
            )

    hangers = []
    if line_numbers:
        hangers = session.query(SpringHangerRecord).filter(
            SpringHangerRecord.project_id == package.project_id,
            SpringHangerRecord.pin_removed.is_(True),
            SpringHangerRecord.line_number.in_(line_numbers),
        ).all()
    if hangers:
        warnings.append(
            f"{len(hangers)} spring hanger(s) have travel stops removed; lock pins before water fill."
        )

    return {
        "can_proceed": not blockers,
        "package_id": package.id,
        "package_number": package.package_number,
        "weld_count": len(welds),
        "open_punch_a": len(open_punch_a),
        "blockers": blockers,
        "warnings": warnings,
        "advisory": True,
    }


def welder_continuity(session: Session, project_id: int, today: Optional[date] = None) -> Dict[str, Any]:
    today = today or date.today()
    welders = session.query(Welder).filter(Welder.project_id == project_id).all()
    welds = session.query(Weld).filter(Weld.project_id == project_id).all()
    last_by_stencil: Dict[str, date] = {}
    for weld in welds:
        stencil = (weld.welder_id or "").strip()
        if not stencil:
            continue
        stamp = None
        end = getattr(weld, "weld_end_datetime", None)
        start = getattr(weld, "weld_start_datetime", None)
        if isinstance(end, datetime):
            stamp = end.date()
        elif isinstance(start, datetime):
            stamp = start.date()
        elif getattr(weld, "fitup_date", None):
            stamp = weld.fitup_date
        if stamp:
            current = last_by_stencil.get(stencil)
            if current is None or stamp > current:
                last_by_stencil[stencil] = stamp

    rows: List[Dict[str, Any]] = []
    at_risk: List[Dict[str, Any]] = []
    expired: List[Dict[str, Any]] = []
    for welder in welders:
        stencil = welder.stencil_number
        last_date = welder.last_welded_date or last_by_stencil.get(stencil)
        calendar_expired = bool(welder.expiry_date and welder.expiry_date < today)
        if last_date is None:
            status = "unknown"
            days_idle = None
            days_left = None
        else:
            days_idle = (today - last_date).days
            days_left = CONTINUITY_DAYS - days_idle
            if days_idle > CONTINUITY_DAYS:
                status = "expired"
            elif days_idle >= CONTINUITY_WARN_DAYS:
                status = "warning"
            else:
                status = "current"
        row = {
            "welder_id": welder.id,
            "stencil_number": stencil,
            "full_name": welder.full_name,
            "is_active": bool(welder.is_active),
            "last_welded_date": last_date.isoformat() if last_date else None,
            "days_idle": days_idle,
            "days_remaining": days_left,
            "status": status,
            "calendar_expired": calendar_expired,
        }
        rows.append(row)
        if status == "warning" or calendar_expired:
            at_risk.append(row)
        if status == "expired":
            expired.append(row)
    return {
        "project_id": project_id,
        "rule": "ASME IX QW-322 six-month continuity",
        "welders": rows,
        "at_risk": at_risk,
        "expired": expired,
    }


def execution_brief(session: Session, project_id: int) -> Dict[str, Any]:
    lots = select_nde_lots(session, project_id)
    continuity = welder_continuity(session, project_id)
    packages = session.query(TestPackage).filter(TestPackage.project_id == project_id).all()
    hydro_blocked = []
    hydro_ready = []
    for package in packages:
        report = hydrotest_clearance(session, package.id)
        if report["can_proceed"]:
            hydro_ready.append({
                "package_id": package.id,
                "package_number": package.package_number,
            })
        else:
            hydro_blocked.append({
                "package_id": package.id,
                "package_number": package.package_number,
                "blockers": report["blockers"][:5],
                "blocker_count": len(report["blockers"]),
            })

    repair_welds = (
        session.query(Weld)
        .filter(
            Weld.project_id == project_id,
            Weld.status.in_(["REPAIR_REQUIRED", "VT_REJECTED"]),
        )
        .all()
    )
    repair_queue = [
        {
            "weld_id": weld.id,
            "weld_number": _weld_number(weld),
            "line_number": weld.line_number,
            "repair_count": weld.repair_count or 0,
            "status": weld.status,
        }
        for weld in repair_welds
    ]

    next_actions: List[Dict[str, Any]] = []
    if lots["selected"]:
        progressive = sum(1 for row in lots["selected"] if row["reason"].startswith("progressive"))
        next_actions.append({
            "priority": 1 if progressive else 2,
            "category": "NDE",
            "title": "Issue today's NDE lot",
            "evidence": (
                f"{lots['selected_count']} joint(s) selected "
                f"({progressive} progressive / extra after reject)."
            ),
            "recommendation": "Give the NDE crew the selected weld numbers before the next shift.",
        })
    if lots["deficit_lines"]:
        next_actions.append({
            "priority": 1,
            "category": "NDE",
            "title": "Line-list NDE percent is not met",
            "evidence": f"{len(lots['deficit_lines'])} line(s) below specified RT/UT/PT/MT extent.",
            "recommendation": "Close the coverage shortfall before hydrotest package freeze.",
        })
    if continuity["expired"]:
        next_actions.append({
            "priority": 1,
            "category": "WELDER",
            "title": "Welder continuity has lapsed",
            "evidence": f"{len(continuity['expired'])} welder(s) idle more than {CONTINUITY_DAYS} days.",
            "recommendation": "Stop using those stencils until QW-322 renewal is complete.",
        })
    elif continuity["at_risk"]:
        next_actions.append({
            "priority": 2,
            "category": "WELDER",
            "title": "Welder continuity window is closing",
            "evidence": f"{len(continuity['at_risk'])} welder(s) inside the 30-day QW-322 warning.",
            "recommendation": "Assign a production weld this week or schedule renewal.",
        })
    if hydro_blocked:
        next_actions.append({
            "priority": 1,
            "category": "HYDROTEST",
            "title": "Test packages are not hydro-ready",
            "evidence": f"{len(hydro_blocked)} package(s) still have punch, NDE, repair or PWHT blockers.",
            "recommendation": "Clear Category-A punches and rejected NDE before filling water.",
        })
    if repair_queue:
        next_actions.append({
            "priority": 1,
            "category": "QUALITY",
            "title": "Repair queue is open",
            "evidence": f"{len(repair_queue)} weld(s) remain REPAIR_REQUIRED / VT_REJECTED.",
            "recommendation": "Complete R1/R2 and re-examination before adding those joints to a test pack.",
        })
    next_actions.sort(key=lambda item: item["priority"])
    return {
        "project_id": project_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "next_actions": next_actions,
        "nde_lots": lots,
        "welder_continuity": {
            "at_risk": continuity["at_risk"],
            "expired": continuity["expired"],
            "welder_count": len(continuity["welders"]),
        },
        "hydrotest": {
            "ready": hydro_ready,
            "blocked": hydro_blocked,
        },
        "repair_queue": repair_queue,
        "advisory": True,
        "message": "Advisory only. Does not replace approved NDE procedures, WPS or hydrotest ITP.",
    }


class CodeComplianceService:
    """Database-backed façade used by the API, UI and reporting hints."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def project_coverage(self, project_id: int) -> Dict[str, Any]:
        with self.db.session_scope() as session:
            lots = select_nde_lots(session, project_id)
            return {
                "project_id": project_id,
                "lines": lots["coverage"],
                "deficit_lines": lots["deficit_lines"],
                "compliant": not lots["deficit_lines"],
            }

    def nde_lots(self, project_id: int) -> Dict[str, Any]:
        with self.db.session_scope() as session:
            return select_nde_lots(session, project_id)

    def hydrotest_clearance(self, test_package_id: int) -> Dict[str, Any]:
        with self.db.session_scope() as session:
            return hydrotest_clearance(session, test_package_id)

    def welder_continuity(self, project_id: int) -> Dict[str, Any]:
        with self.db.session_scope() as session:
            return welder_continuity(session, project_id)

    def execution_brief(self, project_id: int) -> Dict[str, Any]:
        with self.db.session_scope() as session:
            return execution_brief(session, project_id)
