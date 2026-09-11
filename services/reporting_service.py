# -*- coding: utf-8 -*-
"""
services/reporting_service.py – PipeAgent
سرویس متمرکز و بهینه‌شده تولید گزارش‌های فنی، محاسبات Dia-Inch، ماتریس تست‌های غیرمخرب (NDT)
و ارزیابی آمادگی پکیج‌های هیدروتست با ممانعت صریح از آسیب‌پذیری‌های امنیتی XSS و نشت حافظه.
"""

from __future__ import annotations

import csv
import html
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import select, func, and_, or_, desc, case
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.exc import SQLAlchemyError

from config import EXPORT_DIR
from db.manager import DatabaseManager
from db.models import (
    Weld, NDTRecord, Spool, PipeSupport, TestPackage,
    Document, LineListItem, Project, MaterialItem, MaterialTakeOff, AIInsight, WorkFront,
    WeldReportDraft, WeldReport, FitupReportDraft, FitupReport,
)

logger = logging.getLogger(__name__)


def _safe_esc(v: Any) -> str:
    """ایمن‌سازی و پاکسازی رشته‌ها برای جلوگیری از نفوذ کدهای مخرب (Anti-XSS Filter)"""
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return html.escape(str(v).strip())


class ReportingService:
    """
    سرویس مهندسی گزارش‌گیری، مانیتورینگ کارگاهی و تحلیل‌های آماری پروژه
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    # Implementation note.

    def weld_log(
        self,
        project_id: int,
        *,
        weld_type: Optional[str] = None,
        status: Optional[str] = None,
        line_number: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """بازیابی ثبت رسمی سرجوش‌ها به همراه اطلاعات دقیق متالورژیکی و اینچ-قطر (Dia-Inch)"""
        with self.db.session_scope() as session:
            query = session.query(Weld).filter(Weld.project_id == project_id)
            
            if weld_type:
                query = query.filter(Weld.weld_type == weld_type.strip())
            if status:
                query = query.filter(Weld.status == status.strip())
            if line_number:
                query = query.filter(Weld.line_number == line_number.strip().upper())
                
            welds = query.order_by(Weld.weld_number if hasattr(Weld, "weld_number") else Weld.id).all()
            
            return [
                {
                    "weld_id": w.id,
                    "weld_number": getattr(w, "weld_number", f"W-{w.id}"),
                    "weld_type": w.weld_type,
                    "line_number": w.line_number,
                    "drawing_number": getattr(w, "drawing_number", getattr(w, "iso_number", "N/A")),
                    "size_inch": getattr(w, "size_inch", getattr(w, "size", 1.0)),
                    "dia_inch": float(getattr(w, "dia_inch", getattr(w, "size", 1.0)) or 1.0),
                    "thickness_mm": getattr(w, "thickness_mm", getattr(w, "wall_thickness_mm", 0.0)),
                    "material_grade": getattr(w, "material_grade", getattr(w, "material", "CS")),
                    "root_welder": getattr(w, "root_welder_id", w.welder_id),
                    "cap_welder": getattr(w, "cap_welder_id", w.welder_id),
                    "fitup_inspector": getattr(w, "fitup_inspector", None),
                    "fitup_date": getattr(w, "fitup_date", None),
                    "status": w.status,
                    "repair_count": getattr(w, "repair_count", 0) or 0,
                    "pwht_done": getattr(w, "pwht_done", False),
                }
                for w in welds
            ]

    # Implementation note.

    def fitup_report(self, project_id: int) -> List[Dict[str, Any]]:
        """استخراج سرجوش‌های فیت‌آپ‌شده و مورد تایید چشمی کارگاه"""
        with self.db.session_scope() as session:
            rows = (
                session.query(Weld)
                .filter(
                    Weld.project_id == project_id,
                    Weld.status.in_([
                        "FITUP_ACCEPTED", "WELDED", "WELDED_VT_PENDING",
                        "VT_ACCEPTED", "NDT_REQUESTED", "NDT_CLEARED", "COMPLETED"
                    ]),
                )
                .order_by(desc(Weld.fitup_date), Weld.id)
                .all()
            )
            return [
                {
                    "weld_id": w.id,
                    "weld_number": getattr(w, "weld_number", f"W-{w.id}"),
                    "line_number": w.line_number,
                    "drawing_number": getattr(w, "drawing_number", getattr(w, "iso_number", "N/A")),
                    "size_inch": getattr(w, "size_inch", getattr(w, "size", 1.0)),
                    "fitup_inspector": getattr(w, "fitup_inspector", "—"),
                    "fitup_date": getattr(w, "fitup_date", None),
                    "current_status": w.status,
                    "root_gap_mm": getattr(w, "root_gap", 0.0),
                    "hi_lo_alignment_mm": getattr(w, "hi_lo_alignment", 0.0),
                }
                for w in rows
            ]

    # Implementation note.

    def ndt_matrix(self, project_id: int) -> List[Dict[str, Any]]:
        """
        تولید ماتریس وضعیت NDT سرجوش‌ها به صورت بهینه با لود جریانی
        بدون ایجاد باگ N+1 و بدون نشت حافظه RAM
        """
        with self.db.session_scope() as session:
            # Implementation note.
            welds = (
                session.query(Weld)
                .filter(Weld.project_id == project_id)
                .options(selectinload(Weld.ndt_records))
                .all()
            )
            
            matrix_data = []
            for w in welds:
                recs = {n.ndt_method.upper().strip(): n for n in (w.ndt_records or [])}
                matrix_data.append({
                    "weld_number": getattr(w, "weld_number", f"W-{w.id}"),
                    "line_number": w.line_number,
                    "dia_inch": float(getattr(w, "dia_inch", getattr(w, "size", 1.0)) or 1.0),
                    "status": w.status,
                    "VT": recs["VT"].result if "VT" in recs else "",
                    "PT": recs["PT"].result if "PT" in recs else "",
                    "MT": recs["MT"].result if "MT" in recs else "",
                    "RT": recs["RT"].result if "RT" in recs else "",
                    "UT": recs["UT"].result if "UT" in recs else "",
                })
            return matrix_data

    # Implementation note.

    def site_front_work(self, project_id: int) -> Dict[str, Any]:
        """گزارش عملیاتی زنده برای اکیپ‌های فیت‌آپ، جوشکاری، رادیوگرافی و تست فشار"""
        with self.db.session_scope() as session:
            welds = session.query(Weld).filter(Weld.project_id == project_id).all()
            spools = session.query(Spool).filter(Spool.project_id == project_id).all()
            supports = session.query(PipeSupport).filter(PipeSupport.project_id == project_id).all()
            tps = session.query(TestPackage).filter(TestPackage.project_id == project_id).all()

            def calculate_group_counts(items, attr="status"):
                summary: Dict[str, int] = {}
                for it in items:
                    st = getattr(it, attr, None) or "Unknown"
                    summary[st] = summary.get(st, 0) + 1
                return summary

            pending_fitup = [w for w in welds if (w.status or "") in ("FITUP_PENDING", "Pending")]
            fitup_done = [w for w in welds if (w.status or "") in ("FITUP_ACCEPTED", "Fit-up")]
            awaiting_ndt = [w for w in welds if (w.status or "") in ("WELDED", "WELDED_VT_PENDING", "NDT_REQUESTED")]
            rejected = [w for w in welds if (w.status or "") in ("REPAIR_REQUIRED", "VT_REJECTED", "Rejected")]
            spools_to_install = [sp for sp in spools if (sp.status or "") in ("Released to Site", "READY_TO_DISPATCH")]
            supports_pending = [x for x in supports if (x.status or "") in ("Pending", "Fabricated")]
            tp_ready = [t for t in tps if (t.status or "") in ("READY_FOR_TEST", "Ready for Test")]

            return {
                "weld_by_status": calculate_group_counts(welds),
                "spool_by_status": calculate_group_counts(spools),
                "support_by_status": calculate_group_counts(supports),
                "test_pkg_by_status": calculate_group_counts(tps),
                "queues": {
                    "awaiting_fitup": [
                        {"weld_number": getattr(w, "weld_number", f"W-{w.id}"), "line": w.line_number, "dia_inch": getattr(w, "dia_inch", 1.0)}
                        for w in pending_fitup[:50]
                    ],
                    "ready_to_weld": [
                        {"weld_number": getattr(w, "weld_number", f"W-{w.id}"), "line": w.line_number, "root_welder": getattr(w, "root_welder_id", w.welder_id)}
                        for w in fitup_done[:50]
                    ],
                    "awaiting_ndt": [
                        {"weld_number": getattr(w, "weld_number", f"W-{w.id}"), "line": w.line_number, "dia_inch": getattr(w, "dia_inch", 1.0)}
                        for w in awaiting_ndt[:50]
                    ],
                    "rejected_joints": [
                        {"weld_number": getattr(w, "weld_number", f"W-{w.id}"), "line": w.line_number, "repairs": getattr(w, "repair_count", 0)}
                        for w in rejected[:30]
                    ],
                    "spools_to_install": [
                        {"spool": sp.spool_number, "line": sp.line_number, "status": sp.status}
                        for sp in spools_to_install[:50]
                    ],
                    "supports_pending": [
                        {"tag": x.support_tag, "line": x.line_number, "type": x.support_type}
                        for x in supports_pending[:50]
                    ],
                    "tests_pending": [
                        {"pkg": t.package_number, "status": t.status, "pressure": getattr(t, "test_pressure_bar", 0.0)}
                        for t in tp_ready[:30]
                    ],
                },
                "counts": {
                    "welds_total": len(welds),
                    "welds_accepted": sum(1 for w in welds if w.status == "NDT_CLEARED"),
                    "spools_total": len(spools),
                    "spools_installed": sum(1 for sp in spools if (sp.status or "") in ("Installed", "Tested", "ERECTED")),
                    "supports_total": len(supports),
                    "supports_done": sum(1 for x in supports if (x.status or "") in ("Installed", "Inspected", "Accepted")),
                },
            }

    # Implementation note.

    def analytics(self, project_id: int) -> Dict[str, Any]:
        """
        محاسبه شاخص‌های آماری و راندمان جوشکاری و بازرسی بر مبنای اینچ-قطر (Dia-Inch)
        محاسبه تجمعی در سطح دیتابیس جهت ممانعت از کرش کردن حافظه سرور
        """
        with self.db.session_scope() as session:
            # Implementation note.
            weld_stats = session.query(
                func.count(Weld.id).label("total_welds"),
                func.sum(func.coalesce(Weld.dia_inch, 1.0)).label("total_dia_inch"),
                func.sum(case((Weld.status == "NDT_CLEARED", func.coalesce(Weld.dia_inch, 1.0)), else_=0.0)).label("accepted_dia_inch"),
                func.sum(case((Weld.status == "NDT_CLEARED", 1), else_=0)).label("accepted_count"),
                func.sum(case((Weld.status == "REPAIR_REQUIRED", 1), else_=0)).label("rejected_count"),
                func.sum(case((getattr(Weld, "repair_count", 0) > 0, 1), else_=0)).label("repaired_count"),
                func.sum(case((Weld.weld_type == "Shop", func.coalesce(Weld.dia_inch, 1.0)), else_=0.0)).label("shop_dia_inch"),
                func.sum(case((Weld.weld_type == "Field", func.coalesce(Weld.dia_inch, 1.0)), else_=0.0)).label("field_dia_inch"),
            ).filter(Weld.project_id == project_id).first()

            total_welds = weld_stats.total_welds or 0
            total_dia_inch = float(weld_stats.total_dia_inch or 0.0) if weld_stats else 0.0
            accepted_dia_inch = float(weld_stats.accepted_dia_inch or 0.0) if weld_stats else 0.0
            repaired_count = (weld_stats.repaired_count or 0) if weld_stats else 0

            # Implementation note.
            ndt_stats = session.query(
                func.count(NDTRecord.id).label("total_ndt"),
                func.sum(case((NDTRecord.result == "Pass", 1), else_=0)).label("pass_ndt"),
                func.sum(case((NDTRecord.result == "Fail", 1), else_=0)).label("fail_ndt"),
            ).join(Weld, NDTRecord.weld_id_fk == Weld.id).filter(Weld.project_id == project_id).first()

            total_ndt = ndt_stats.total_ndt or 0
            passed_ndt = ndt_stats.pass_ndt or 0

            # Implementation note.
            spools_total = session.query(func.count(Spool.id)).filter(Spool.project_id == project_id).scalar() or 0
            spools_erected = session.query(func.count(Spool.id)).filter(Spool.project_id == project_id, Spool.status == "ERECTED").scalar() or 0
            lines_count = session.query(func.count(LineListItem.id)).filter(LineListItem.project_id == project_id).scalar() or 0
            docs_count = session.query(func.count(Document.id)).filter(Document.project_id == project_id).scalar() or 0
            tps_count = session.query(func.count(TestPackage.id)).filter(TestPackage.project_id == project_id).scalar() or 0
            tps_passed = session.query(func.count(TestPackage.id)).filter(TestPackage.project_id == project_id, TestPackage.status == "Passed").scalar() or 0

            # Implementation note.
            welder_stats = session.query(
                Weld.welder_id,
                func.count(Weld.id).label("total_welds"),
                func.sum(case((Weld.status == "NDT_CLEARED", 1), else_=0)).label("accepted_welds"),
                func.sum(case((getattr(Weld, "repair_count", 0) > 0, 1), else_=0)).label("repaired_welds"),
            ).filter(Weld.project_id == project_id).group_by(Weld.welder_id).all()

            by_welder = {
                (w.welder_id or "Unassigned"): {
                    "total": w.total_welds,
                    "accepted": w.accepted_welds or 0,
                    "repaired": w.repaired_welds or 0,
                    "defect_rate_pct": round((w.repaired_welds or 0) / w.total_welds * 100, 1) if w.total_welds > 0 else 0.0,
                }
                for w in welder_stats
            }

            accepted_count = (weld_stats.accepted_count or 0) if weld_stats else 0
            rejected_count = (weld_stats.rejected_count or 0) if weld_stats else 0
            acceptance_joint_pct = round(accepted_count / total_welds * 100, 1) if total_welds else 0.0
            repair_pct = round(repaired_count / total_welds * 100, 1) if total_welds else 0.0
            rejection_pct = round(rejected_count / total_welds * 100, 1) if total_welds else 0.0
            acceptance_di_pct = (
                round(accepted_dia_inch / total_dia_inch * 100, 1) if total_dia_inch > 0 else 0.0
            )
            welds_block = {
                "total": total_welds,
                "total_joints_count": total_welds,
                "total_dia_inch": total_dia_inch,
                "completed_dia_inch": accepted_dia_inch,
                "accepted_dia_inch": accepted_dia_inch,
                "shop_dia_inch": float((weld_stats.shop_dia_inch or 0.0) if weld_stats else 0.0),
                "field_dia_inch": float((weld_stats.field_dia_inch or 0.0) if weld_stats else 0.0),
                "accepted_count": accepted_count,
                "rejected_count": rejected_count,
                "repaired_count": repaired_count,
                "acceptance_rate_pct": acceptance_joint_pct,
                "acceptance_rate_dia_inch_pct": acceptance_di_pct,
                "repair_rate_pct": repair_pct,
                "repair_rate_joint_pct": repair_pct,
                "rejection_rate_pct": rejection_pct,
            }
            return {
                "lines": lines_count,
                "lines_count": lines_count,
                "documents_count": docs_count,
                "welds": welds_block,
                "ndt": {
                    "total_inspections": total_ndt,
                    "passed_inspections": passed_ndt,
                    "failed_inspections": ndt_stats.fail_ndt or 0,
                    "pass_rate_pct": round(passed_ndt / total_ndt * 100, 1) if total_ndt > 0 else 0.0,
                },
                "spools": {
                    "total": spools_total,
                    "installed": spools_erected,
                    "installed_erected": spools_erected,
                },
                "test_packages": {
                    "total": tps_count,
                    "passed": tps_passed,
                },
                "by_welder": by_welder,
                "by_welder_kpis": by_welder,
            }

    # Implementation note.

    def smart_hints(self, project_id: int) -> List[Dict[str, Any]]:
        """
        پایش انطباق فنی و استخراج هوشمند انحرافات به روش کاملاً قطعی و قابل ممیزی
        """
        with self.db.session_scope() as s:
            welds = s.query(Weld).filter(Weld.project_id == project_id).all()
            fronts = s.query(WorkFront).filter(WorkFront.project_id == project_id).all()
            ndt = (s.query(NDTRecord).join(Weld, NDTRecord.weld_id_fk == Weld.id)
                   .filter(Weld.project_id == project_id).all())
            tps = s.query(TestPackage).filter(TestPackage.project_id == project_id).all()
            drafts_w = s.query(WeldReportDraft).filter(WeldReportDraft.project_id == project_id,
                                                        WeldReportDraft.status == "Draft").count()
            drafts_f = s.query(FitupReportDraft).filter(FitupReportDraft.project_id == project_id,
                                                        FitupReportDraft.status == "Draft").count()

        hints: List[Dict[str, Any]] = []
        total = len(welds)
        if total == 0:
            return []

        repaired = sum(1 for w in welds if (getattr(w, "repair_count", 0) or 0) > 0)
        rejected = sum(1 for w in welds if w.status in ("REPAIR_REQUIRED", "VT_REJECTED"))
        awaiting_ndt = sum(1 for w in welds if w.status in ("WELDED", "WELDED_VT_PENDING", "NDT_REQUESTED"))
        ndt_fail = sum(1 for n in ndt if (n.result or "").lower() in ("fail", "failed", "rejected", "rej"))
        overdue = sum(1 for f in fronts if f.planned_finish and f.planned_finish < date.today() and f.status != "Completed")
        unassigned_ready = sum(1 for f in fronts if f.status in ("Ready", "Assigned") and f.readiness == "Ready"
                               and not (getattr(f, "blocker", "") or "").strip())
        blocked = sum(1 for f in fronts if f.status in ("Blocked", "Waiting") or (getattr(f, "blocker", "") or "").strip())
        
        repair_pct = round(repaired / total * 100, 1)
        reject_pct = round(rejected / total * 100, 1)

        def add(severity, title, evidence, action, category):
            hints.append({"severity": severity, "title": title, "evidence": evidence,
                          "recommendation": action, "category": category})

        if awaiting_ndt >= 15:
            add("High", "NDT queue is becoming a production constraint",
                f"{awaiting_ndt} welded joints are awaiting NDT action.",
                "Review NDT capacity and prioritize requests by line criticality.", "QUALITY")
        if repair_pct >= 5.0:
            add("High", "Repair rate is above the control threshold",
                f"Repair rate is {repair_pct}% ({repaired} of {total} welds).",
                "Investigate welder qualifications, WPS compliance and review repeat defect patterns.", "WELDING")
        if ndt_fail:
            add("High", "NDT failures require controlled follow-up",
                f"{ndt_fail} failed NDT results detected.",
                "Verify defect excavation, R1 re-weld and re-radiography before hydrotest.", "QUALITY")
        if overdue:
            add("High", "Overdue work fronts detected",
                f"{overdue} work front(s) are past planned finish.",
                "Review constraints, resource assignments and recovery dates.", "EXECUTION")
        if unassigned_ready:
            add("High", "Ready work is not yet fully dispatched",
                f"{unassigned_ready} ready work front(s) have no active assignment.",
                "Assign available teams and required equipment immediately before productive hours are lost.", "DISPATCH")
        if blocked:
            add("Medium", "Execution constraints are accumulating",
                f"{blocked} work front(s) are blocked or waiting.",
                "Analyze permit and material holds and clear path for the field crews.", "EXECUTION")
        if drafts_w or drafts_f:
            add("Medium", "Draft field reports awaiting QC approval",
                f"{drafts_w} welding drafts and {drafts_f} fit-up drafts are pending.",
                "Review and approve valid drafts so the official register remains current.", "DOCUMENT CONTROL")

        try:
            from services.code_compliance import CodeComplianceService
            brief = CodeComplianceService(self.db).execution_brief(project_id)
            for action in brief.get("next_actions") or []:
                add(
                    "High" if action.get("priority", 2) == 1 else "Medium",
                    action["title"],
                    action["evidence"],
                    action["recommendation"],
                    action.get("category", "EXECUTION"),
                )
        except Exception:
            logger.exception("Failed to attach code-compliance hints")

        # If welded joints exist but no NDT records are present, surface the operational queue explicitly.
        try:
            with self.db.session_scope() as session:
                welded_count = session.query(func.count(Weld.id)).filter(
                    Weld.project_id == project_id,
                    Weld.status.in_(["Welded", "WELDED"]),
                ).scalar() or 0
                ndt_count = session.query(func.count(NDTRecord.id)).join(
                    Weld, NDTRecord.weld_id_fk == Weld.id
                ).filter(Weld.project_id == project_id).scalar() or 0
            if welded_count > ndt_count:
                hints.append({
                    "severity": "High",
                    "title": "NDT backlog needs attention",
                    "evidence": f"{welded_count - ndt_count} welded joint(s) have no NDT record.",
                    "recommendation": "Prioritize NDT requests before the queue constrains downstream acceptance.",
                    "category": "QUALITY",
                })
        except Exception:
            logger.exception("Failed to calculate NDT backlog hint")

        return hints

    def save_smart_hints(self, project_id: int) -> List[Dict[str, Any]]:
        """ذخیره و ممیزی هشدارهای فعال پروژه در دیتابیس"""
        hints = self.smart_hints(project_id)
        with self.db.session_scope() as s:
            for h in hints:
                s.add(AIInsight(
                    project_id=project_id,
                    insight_type=h["category"],
                    severity=h["severity"],
                    title=h["title"],
                    recommendation=h["recommendation"],
                    evidence_json=json.dumps({"evidence": h["evidence"]}, ensure_ascii=False),
                    model_source="local-rule-ai"
                ))
        return hints

    # Implementation note.

    def _html_shell(self, title: str, body: str, *, draft: bool = False) -> str:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        mark = '<div class="watermark">DRAFT — NOT FOR CONSTRUCTION</div>' if draft else ''
        return f"""<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{html.escape(title)}</title>
<style>{self._report_css()}</style>
</head>
<body>
{mark}
<div class='header'>
  <div class='brand'>PipeAgent</div>
  <div class='subtitle'>Piping Execution Operating System · Controlled Project Report</div>
</div>
{body}
<div class='footer'>
  Generated by PipeAgent · {stamp} · This report is evidence-based and should be reviewed against approved project records.
</div>
</body>
</html>"""

    def _report_body(self, obj: Any, kind: str, project_name: str, status_label: str) -> str:
        if kind == "weld":
            rows = [
                ("Report No.", obj.report_no), ("Project", project_name), ("Line No.", obj.line_number),
                ("ISO No.", obj.iso_number), ("Weld No.", obj.weld_no), ("Spool No.", obj.spool_no),
                ("Welder", obj.welder_name or obj.welder_id), ("Weld Date", obj.weld_date),
                ("Joint Type", obj.joint_type), ("Process", obj.process), ("WPS", obj.wps_id),
                ("Filler Material", obj.filler_material), ("Preheat", obj.preheat),
                ("Visual Result", obj.visual_result), ("RT", f"{obj.rt_no or ''} / {obj.rt_result or ''}"),
                ("PT", f"{obj.pt_no or ''} / {obj.pt_result or ''}"), ("UT", f"{obj.ut_no or ''} / {obj.ut_result or ''}"),
                ("PWHT", obj.pwht), ("Contractor", obj.contractor), ("Prepared / Approved By", getattr(obj, 'prepared_by', None) or getattr(obj, 'approved_by', None)),
                ("Approved At", getattr(obj, 'approved_at', None)), ("Remarks", obj.remarks),
            ]
            heading = "Welding Report"
        else:
            rows = [
                ("Report No.", obj.report_no), ("Project", project_name), ("Fit-up No.", obj.fitup_no),
                ("Line No.", obj.line_number), ("ISO No.", obj.iso_number), ("Weld No.", obj.weld_no),
                ("Spool No.", obj.spool_no), ("Fitter", obj.fitter), ("Fit-up Date", obj.fitup_date),
                ("Root Gap", obj.root_gap), ("Hi-Low", obj.hi_low), ("Alignment", obj.alignment),
                ("Bevel", obj.bevel), ("Cleanliness", obj.cleanliness), ("Tack Quality", obj.tack_quality),
                ("Fit-up Result", obj.fitup_result), ("Contractor", obj.contractor),
                ("Prepared / Approved By", getattr(obj, 'prepared_by', None) or getattr(obj, 'approved_by', None)),
                ("Approved At", getattr(obj, 'approved_at', None)), ("Remarks", obj.remarks),
            ]
            heading = "Fit-up Inspection Report"
            
        meta = "".join(f"<div><span class='label'>{_safe_esc(k)}:</span> {_safe_esc(v)}</div>" for k, v in rows)
        status_cls = "official" if status_label == "OFFICIAL" else "draft"
        return f"<h1>{heading}</h1><div class='meta'>{meta}</div><p><span class='status {status_cls}'>{status_label}</span></p><h2>Document Control</h2><table><tr><th>Control</th><th>Value</th></tr><tr><td>Record State</td><td>{status_label}</td></tr><tr><td>Business Rule</td><td>Draft records require QC review before becoming official project evidence.</td></tr></table>"

    def export_report_html(self, kind: str, report_id: int, *, official: bool = False) -> str:
        model = WeldReport if kind == "weld" and official else FitupReport if kind == "fitup" and official else WeldReportDraft if kind == "weld" else FitupReportDraft
        with self.db.session_scope() as s:
            obj = s.get(model, int(report_id))
            if not obj:
                raise ValueError("Report record not found.")
            project_name = self._project_name(s, obj.project_id)
            title = f"{kind.title()} Report {obj.report_no}"
            body = self._report_body(obj, kind, project_name, "OFFICIAL" if official else "DRAFT")
            
        path = Path(EXPORT_DIR) / "html_reports"
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / f"{kind}_report_{obj.report_no.replace('/', '_')}.html"
        file_path.write_text(self._html_shell(title, body, draft=not official), encoding="utf-8")
        return str(file_path)

    def project_executive_html(self, project_id: int) -> str:
        with self.db.session_scope() as s:
            p = s.get(Project, project_id)
            name = f"{p.project_code} – {p.title}" if p else f"Project {project_id}"
            
        a = self.analytics(project_id)
        h = self.smart_hints(project_id)
        w = a["welds"]
        
        cards = f"""<table>
          <tr>
            <th>Total Welds</th>
            <th>Welding Progress (DI)</th>
            <th>Repair Rate (Joint)</th>
            <th>NDT Pass Rate</th>
            <th>Spools Installed</th>
            <th>Tests Passed</th>
          </tr>
          <tr>
            <td>{w['total_joints_count']}</td>
            <td>{w['completed_dia_inch']:.1f} / {w['total_dia_inch']:.1f} in</td>
            <td>{w['repair_rate_joint_pct']}%</td>
            <td>{a['ndt']['pass_rate_pct']}%</td>
            <td>{a['spools']['installed_erected']}/{a['spools']['total']}</td>
            <td>{a['test_packages']['passed']}/{a['test_packages']['total']}</td>
          </tr>
        </table>"""
        
        hints = "".join(f"<div class='hint {'high' if x['severity']=='High' else ''}'><b>{_safe_esc(x['severity'])} · {_safe_esc(x['title'])}</b><br>{_safe_esc(x['evidence'])}<br><b>Next action:</b> {_safe_esc(x['recommendation'])}</div>" for x in h)
        weld_rows = self.weld_log(project_id)[:100]
        
        table = "<table><tr><th>Weld No</th><th>Line No</th><th>Weld Type</th><th>Root Welder</th><th>Status</th><th>Repairs</th></tr>" + "".join(f"<tr><td>{_safe_esc(r['weld_number'])}</td><td>{_safe_esc(r['line_number'])}</td><td>{_safe_esc(r['weld_type'])}</td><td>{_safe_esc(r['root_welder'])}</td><td>{_safe_esc(r['status'])}</td><td>{_safe_esc(r['repair_count'])}</td></tr>" for r in weld_rows) + "</table>"
        body = f"<h1>Project Executive Report</h1><p><b>{_safe_esc(name)}</b></p><h2>Execution & Quality Snapshot</h2>{cards}<h2>Smart Operational Hints</h2>{hints}<h2>Weld Register Snapshot (Top 100)</h2>{table}"
        
        path = Path(EXPORT_DIR) / "html_reports"
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / f"PipeAgent_Executive_Report_P{project_id}_{date.today().isoformat()}.html"
        file_path.write_text(self._html_shell(f"Executive Report — {name}", body), encoding="utf-8")
        return str(file_path)

    def export_management_analytics_pack(self, project_id: int) -> str:
        """Write the unit / contractor / material / service HTML pack. Returns index path."""
        from services.management_analytics import build_management_snapshot, write_management_pack

        snapshot = build_management_snapshot(self.db, project_id)
        return write_management_pack(self._html_shell, project_id, snapshot)

    def management_group_sheets(self, project_id: int) -> Dict[str, List[Dict[str, Any]]]:
        from services.management_analytics import (
            SLICE_SPECS,
            build_management_snapshot,
            group_rows_as_dicts,
        )

        snapshot = build_management_snapshot(self.db, project_id)
        sheets: Dict[str, List[Dict[str, Any]]] = {}
        for key, title, _blurb in SLICE_SPECS:
            if key == "quality_and_test":
                continue
            sheets[title[:31]] = group_rows_as_dicts(snapshot["groups"][key])
        sheets["Findings"] = [
            {
                "Severity": item["severity"],
                "Title": item["title"],
                "Evidence": item["evidence"],
                "Next action": item["action"],
            }
            for item in snapshot["findings"]
        ]
        return sheets

    # ── Export helpers ────────────────────────────────────────────────
    def export_csv(self, rows: List[Dict[str, Any]], filename: str) -> str:
        path = Path(EXPORT_DIR) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            path.write_text("", encoding="utf-8")
            return str(path)
        fieldnames = list(rows[0].keys())
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for row in rows:
                w.writerow({k: _safe_esc(row.get(k)) for k in fieldnames})
        return str(path)

    def export_excel(
        self,
        sheets: Dict[str, List[Dict[str, Any]]],
        filename: str,
    ) -> Tuple[bool, str]:
        """Multi-sheet workbook. Returns (ok, path_or_error)."""
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment
        except ImportError:
            return False, "openpyxl required: pip install openpyxl"

        path = Path(EXPORT_DIR) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        wb = Workbook()
        default = wb.active
        first = True
        header_fill = PatternFill("solid", fgColor="1E3C72")
        header_font = Font(color="FFFFFF", bold=True)

        for name, rows in sheets.items():
            safe_name = (name or "Sheet")[:31]
            if first:
                ws = default
                ws.title = safe_name
                first = False
            else:
                ws = wb.create_sheet(safe_name)
            if not rows:
                ws.append(["(no data)"])
                continue
            headers = list(rows[0].keys())
            ws.append(headers)
            for col, _ in enumerate(headers, 1):
                cell = ws.cell(1, col)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center")
            for row in rows:
                ws.append([_safe_esc(row.get(h)) for h in headers])
            for col in ws.columns:
                width = min(40, max(10, max(len(str(c.value or "")) for c in col) + 2))
                ws.column_dimensions[col[0].column_letter].width = width

        wb.save(path)
        return True, str(path)

    def _report_css(self) -> str:
        return """
        @page { size: A4; margin: 14mm; }
        * { box-sizing: border-box; }
        body { font-family: Segoe UI, Arial, Helvetica, sans-serif; color:#1f2937; font-size:10.5pt; margin:0; line-height: 1.4; }
        .header { border-bottom:3px solid #17365d; padding-bottom:10px; margin-bottom:14px; }
        .brand { color:#17365d; font-size:20pt; font-weight:700; }
        .subtitle { color:#64748b; font-size:9pt; }
        h1 { font-size:17pt; color:#17365d; margin:12px 0 8px; }
        h2 { font-size:12pt; color:#17365d; margin:14px 0 6px; border-bottom:1px solid #cbd5e1; padding-bottom:4px; }
        table { width:100%; border-collapse:collapse; margin:7px 0 12px; }
        th, td { border:1px solid #cbd5e1; padding:5px 6px; vertical-align:top; }
        th { background:#e8eef6; color:#17365d; text-align:left; }
        .meta { display:grid; grid-template-columns:1fr 1fr; gap:4px 14px; }
        .meta div { padding:3px 0; }
        .label { color:#64748b; font-weight:700; }
        .status { display:inline-block; padding:3px 8px; border-radius:10px; font-weight:700; }
        .draft { background:#fff3cd; color:#7a5200; }
        .official { background:#dcfce7; color:#166534; }
        .hint { border-left:4px solid #f59e0b; background:#fffbeb; padding:7px 9px; margin:6px 0; }
        .hint.high { border-left-color:#dc2626; background:#fef2f2; }
        .footer { margin-top:16px; padding-top:7px; border-top:1px solid #cbd5e1; color:#64748b; font-size:8pt; }
        .watermark { position:fixed; top:45%; left:10%; right:10%; text-align:center; font-size:36pt; color:rgba(120,80,0,.08); transform:rotate(-25deg); font-weight:700; }
        .page-break { page-break-before:always; }
        @media print { .no-print { display:none !important; } }
        .kpis { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin:10px 0 16px; }
        .kpi { border:1px solid #cbd5e1; border-left:4px solid #17365d; padding:8px 10px; background:#f8fafc; }
        .kpi .n { font-size:16pt; font-weight:800; color:#17365d; }
        .kpi .l { font-size:8pt; color:#64748b; text-transform:uppercase; font-weight:700; letter-spacing:.03em; }
        .kpi .s { font-size:8pt; color:#64748b; }
        .bar { display:inline-block; vertical-align:middle; background:#e8eef6; height:8px; width:72px; border-radius:4px; overflow:hidden; margin-right:6px; }
        .bar > i { display:block; height:100%; background:#2563eb; }
        .bar-n { font-variant-numeric:tabular-nums; }
        .toc { columns:2; gap:18px; margin:8px 0 16px; }
        .toc a { color:#17365d; }
        .note { color:#64748b; font-size:9pt; }
        .muted { color:#94a3b8; text-align:center; }
        .cover-meta { display:grid; grid-template-columns:1fr 1fr; gap:4px 18px; margin:8px 0 12px; }
        """

    def _project_name(self, s, project_id: int) -> str:
        p = s.get(Project, project_id)
        return f"{p.project_code} – {p.title}" if p else f"Project {project_id}"