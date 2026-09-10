# -*- coding: utf-8 -*-
"""Cross-discipline site execution control services."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from db.models import (
    CommissioningRecord,
    EquipmentRecord,
    InstrumentRecord,
    PermitRecord,
    SiteIssueRecord,
)


class SiteExecutionService:
    """Provide reusable site-control KPIs and predictive flags."""

    def __init__(self, db):
        self.db = db

    def kpis(self) -> dict[str, Any]:
        with self.db.session_scope() as session:
            instruments = session.query(InstrumentRecord).all()
            permits = session.query(PermitRecord).all()
            equipment = session.query(EquipmentRecord).all()
            issues = session.query(SiteIssueRecord).all()
            commissioning = session.query(CommissioningRecord).all()

            overdue_calibration = sum(
                1 for x in instruments if x.calibration_due and x.calibration_due < date.today()
            )
            expiring_permits = sum(
                1 for x in permits
                if x.expires_at and datetime.now() <= x.expires_at <= datetime.now() + timedelta(hours=24)
                and x.status not in {"Closed", "Cancelled"}
            )
            unavailable_equipment = sum(
                1 for x in equipment if x.status in {"Down", "Maintenance", "Unavailable"}
            )
            open_issues = sum(1 for x in issues if x.status not in {"Closed", "Cancelled"})
            turnover_blockers = sum(
                1 for x in commissioning if x.turnover_status not in {"Ready", "Turned Over"}
            )
            return {
                "instruments": len(instruments),
                "calibration_overdue": overdue_calibration,
                "permits": len(permits),
                "permits_expiring": expiring_permits,
                "equipment": len(equipment),
                "equipment_unavailable": unavailable_equipment,
                "open_issues": open_issues,
                "commissioning_systems": len(commissioning),
                "turnover_blockers": turnover_blockers,
            }

    def predictive_flags(self) -> list[dict[str, str]]:
        k = self.kpis()
        flags: list[dict[str, str]] = []
        if k["calibration_overdue"]:
            flags.append({"severity": "High", "title": "Calibration risk", "detail": f"{k['calibration_overdue']} instruments are past calibration due date."})
        if k["permits_expiring"]:
            flags.append({"severity": "High", "title": "Permit expiry risk", "detail": f"{k['permits_expiring']} permits expire within 24 hours."})
        if k["equipment_unavailable"]:
            flags.append({"severity": "Medium", "title": "Equipment availability", "detail": f"{k['equipment_unavailable']} site assets are unavailable."})
        if k["open_issues"]:
            flags.append({"severity": "Medium", "title": "Site issue backlog", "detail": f"{k['open_issues']} site issues remain open."})
        if k["turnover_blockers"]:
            flags.append({"severity": "Medium", "title": "Turnover blockers", "detail": f"{k['turnover_blockers']} commissioning systems are not turnover-ready."})
        return flags
