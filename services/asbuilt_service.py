# -*- coding: utf-8 -*-
"""
services/asbuilt_service.py – PipeAgent
سرویس جامع مدیریت فرآیندهای مهندسی چون‌ساخت (As-Built)، تطبیق نقشه جوش (Weld Map)،
کنترل ردلاین‌های سایت، گشت‌های واک‌ثرو (Walkdowns) و صدور گواهینامه‌های تکمیل مکانیکی (MCC).

این نسخه با مدل‌های واقعی db/models.py هماهنگ شده است:
  • WalkdownChecklist  (به‌جای WalkdownItem)
  • WeldMapEntry       (به‌جای WeldMap)
  • AsBuiltMarkUp      (به‌جای AsBuiltMarkup)
  • MCCRecord          (به‌جای MechanicalCompletionCertificate)
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from repositories.asbuilt_repository import (
    IsoRegistryRepository,
    WeldMapRepository,
    MCCRepository,
    WalkdownRepository,
    AsBuiltMarkupRepository,
)

# Implementation note.
from db.models import (
    IsoRegistry,
    WeldMapEntry,          # Implementation note.
    MCCRecord,             # Implementation note.
    WalkdownChecklist,     # Implementation note.
    AsBuiltMarkUp,         # Implementation note.
    Weld,                  # Implementation note.
    NDTRecord,
    AsBuiltRecord,
)

# Implementation note.
WeldMap = WeldMapEntry
WalkdownItem = WalkdownChecklist
AsBuiltMarkup = AsBuiltMarkUp
MechanicalCompletionCertificate = MCCRecord
WeldJoint = Weld


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & Turnover Standards
# ──────────────────────────────────────────────

class IsoStatus(str, Enum):
    IFC = "IFC"
    REDLINE_IN_PROGRESS = "REDLINE_PROGRESS"
    AS_BUILT_DRAFT = "AS_BUILT_DRAFT"
    AS_BUILT_APPROVED = "AS_BUILT_APPROVED"
    SUPERSEDED = "SUPERSEDED"


class MCCStatus(str, Enum):
    DRAFT = "DRAFT"
    WALKDOWN_IN_PROGRESS = "WALKDOWN"
    PUNCH_LISTED = "PUNCH_LISTED"
    APPROVED = "APPROVED"
    TRANSFERRED_TO_COMM = "TRANSFERRED"


class WalkdownCategory(str, Enum):
    CAT_A = "A"
    CAT_B = "B"
    CAT_C = "C"


class MarkupType(str, Enum):
    ROUTING_CHANGE = "ROUTING_CHANGE"
    COMPONENT_REPLACEMENT = "COMPONENT_REPLACE"
    ADDITIONAL_WELD = "ADDITIONAL_WELD"
    SUPPORT_RELOCATION = "SUPPORT_RELOCATION"
    VALVE_TAG_CORRECTION = "VALVE_CORRECTION"


# ──────────────────────────────────────────────
#  Custom Domain Exceptions
# ──────────────────────────────────────────────

class AsBuiltValidationError(Exception):
    """خطای عدم احراز شرایط تأیید نقشه چون‌ساخت"""
    pass


class MCCIssuanceBlockedError(Exception):
    """خطای مسدود بودن صدور MCC به دلیل پانچ‌های باز دسته A"""
    pass


# ──────────────────────────────────────────────
#  AsBuilt Service Implementation
# ──────────────────────────────────────────────

class AsBuiltService:
    """
    سرویس اصلی هماهنگ‌کننده مستندات تحویل نهایی، نقشه‌های چون‌ساخت و پکیج‌های MC
    """

    def __init__(self, session: Session):
        self.session = session
        self.iso = IsoRegistryRepository(session)
        self.weld_map = WeldMapRepository(session)
        self.mcc = MCCRepository(session)
        self.walkdown = WalkdownRepository(session)
        self.markup = AsBuiltMarkupRepository(session)

    # Implementation note.

    def register_iso(
        self,
        project_id: int,
        iso_number: str,
        line_number: str,
        sheet_number: int = 1,
        total_sheets: int = 1,
        revision: str = "0",
        area_code: Optional[str] = None,
        subsystem_code: Optional[str] = None,
        created_by: str = "system",
    ) -> IsoRegistry:
        """ثبت نقشه ایزومتریک جدید با وضعیت ساخت (IFC)"""
        iso_clean = iso_number.strip().upper()
        existing = (
            self.session.query(IsoRegistry)
            .filter(
                IsoRegistry.project_id == project_id,
                IsoRegistry.iso_number == iso_clean,
                IsoRegistry.sheet_number == str(sheet_number),
            )
            .first()
        )
        if existing:
            raise ValueError(f"ISO '{iso_clean}' (Sheet {sheet_number}) already registered.")

        iso_obj = IsoRegistry(
            project_id=project_id,
            iso_number=iso_clean,
            line_number=line_number.strip().upper(),
            sheet_number=str(sheet_number),
            total_sheets=total_sheets,
            revision=revision.strip(),
            design_status=IsoStatus.IFC.value,
            spool_count=0,
            weld_count=0,
            total_length_m=0.0,
            received_date=date.today(),
            status="Active",
            remarks=f"Created by {created_by}",
        )
        self.session.add(iso_obj)
        self.session.commit()
        self.session.refresh(iso_obj)

        logger.info(f"ISO '{iso_clean}' registered successfully for Project #{project_id}.")
        return iso_obj

    # Implementation note.

    def approve_asbuilt_iso(
        self,
        iso_id: int,
        approved_by: str,
        client_approval_ref: Optional[str] = None,
        asbuilt_drawing_file: Optional[str] = None,
    ) -> IsoRegistry:
        """
        تأیید نهایی نقشه چون‌ساخت پس از احراز شروط:
          ۱. اعمال ۱۰۰٪ خطوط قرمز روی نقشه
          ۲. تطبیق کامل سرجوش‌های نقشه جوش
        """
        iso_record = self.session.query(IsoRegistry).filter(IsoRegistry.id == iso_id).first()
        if not iso_record:
            raise ValueError(f"ISO Registry record #{iso_id} not found.")

        # Implementation note.
        pending_markups = (
            self.session.query(AsBuiltMarkUp)
            .filter(
                AsBuiltMarkUp.iso_number == iso_record.iso_number,
                AsBuiltMarkUp.status.notin_(["Incorporated", "Closed", "Approved"]),
            )
            .count()
        )
        if pending_markups > 0:
            raise AsBuiltValidationError(
                f"Cannot certify As-Built: {pending_markups} redline markup(s) "
                f"are not yet incorporated!"
            )

        # Implementation note.
        unreconciled_welds = (
            self.session.query(WeldMapEntry)
            .filter(
                WeldMapEntry.iso_number == iso_record.iso_number,
                WeldMapEntry.asbuilt_verified == False,
            )
            .count()
        )
        if unreconciled_welds > 0:
            raise AsBuiltValidationError(
                f"Cannot certify As-Built: {unreconciled_welds} weld map item(s) "
                f"are not fully reconciled!"
            )

        iso_record.status = "As-Built"
        iso_record.asbuilt_complete = True
        if asbuilt_drawing_file:
            iso_record.drawing_file_path = asbuilt_drawing_file
        if client_approval_ref:
            iso_record.remarks = (
                f"Client approval ref: {client_approval_ref} | Approved by {approved_by}"
            )

        self.session.commit()
        self.session.refresh(iso_record)
        logger.info(f"ISO '{iso_record.iso_number}' certified as AS-BUILT by {approved_by}.")
        return iso_record

    # Implementation note.

    def add_weld_map(
        self,
        project_id: int,
        iso_number: str,
        weld_mark: str,
        weld_joint_id: Optional[int] = None,
        weld_type: str = "BW",
        size_inch: float = 2.0,
        drawing_coordinates: Optional[str] = None,
        **kwargs,
    ) -> WeldMapEntry:
        """افزودن نشانه سرجوش روی نقشه ایزومتریک"""
        iso_clean = iso_number.strip().upper()
        mark_clean = weld_mark.strip().upper()

        entry = WeldMapEntry(
            project_id=project_id,
            iso_number=iso_clean,
            joint_number=mark_clean,          # Implementation note.
            weld_id_fk=weld_joint_id,         # Implementation note.
            weld_type=weld_type,
            sheet_number=str(kwargs.get("sheet_number", "1")),
            spool_number=kwargs.get("spool_number", ""),
            line_number=kwargs.get("line_number", ""),
            welder_stencil=kwargs.get("welder_stencil", ""),
            wps_number=kwargs.get("wps_number", ""),
            ndt_clearance=kwargs.get("ndt_clearance", "Pending"),
            asbuilt_verified=False,           # Implementation note.
            status=kwargs.get("status", "Draft"),
            remarks=(
                f"Size: {size_inch}\" | Coords: {drawing_coordinates or 'N/A'}"
            ),
        )
        self.session.add(entry)
        self.session.commit()
        self.session.refresh(entry)
        return entry

    def reconcile_weld_map_with_actuals(
        self,
        project_id: int,
        iso_number: str,
    ) -> Dict[str, Any]:
        """تطبیق خودکار علائم نقشه جوش با سوابق بازرسی"""
        iso_clean = iso_number.strip().upper()
        weld_maps = (
            self.session.query(WeldMapEntry)
            .filter(
                WeldMapEntry.project_id == project_id,
                WeldMapEntry.iso_number == iso_clean,
            )
            .all()
        )

        total_marks = len(weld_maps)
        reconciled_count = 0
        discrepancies: List[str] = []

        for wm in weld_maps:
            if not wm.weld_id_fk:
                discrepancies.append(
                    f"Weld mark '{wm.joint_number}' is not linked to any physical Weld Joint ID."
                )
                continue

            weld_obj = self.session.query(Weld).filter(Weld.id == wm.weld_id_fk).first()
            if not weld_obj:
                discrepancies.append(
                    f"Weld Joint ID #{wm.weld_id_fk} linked to '{wm.joint_number}' does not exist."
                )
                continue

            # Implementation note.
            if weld_obj.status in ("Accepted", "NDT_CLEARED", "COMPLETED", "VT_ACCEPTED", "Inspected"):
                wm.asbuilt_verified = True
                wm.ndt_clearance = "Accepted"
                reconciled_count += 1
            else:
                discrepancies.append(
                    f"Weld '{weld_obj.weld_id}' ({wm.joint_number}) has incomplete "
                    f"QC status: '{weld_obj.status}'"
                )

        self.session.commit()

        return {
            "iso_number": iso_clean,
            "total_weld_marks": total_marks,
            "reconciled_count": reconciled_count,
            "is_fully_reconciled": total_marks > 0 and total_marks == reconciled_count,
            "discrepancies": discrepancies,
        }

    # Implementation note.

    def add_markup(
        self,
        project_id: int,
        iso_number: str,
        markup_type: Union[MarkupType, str],
        description: str,
        raised_by: str,
        sheet_number: int = 1,
        site_sketch_file: Optional[str] = None,
        technical_query_no: Optional[str] = None,
    ) -> AsBuiltMarkUp:
        """ثبت خط قرمز جدید ناشی از تغییرات اجرایی در سایت"""
        m_type = markup_type.value if isinstance(markup_type, MarkupType) else str(markup_type)
        iso_clean = iso_number.strip().upper()

        markup = AsBuiltMarkUp(
            project_id=project_id,
            iso_number=iso_clean,
            sheet_number=str(sheet_number),
            markup_type=m_type,
            description=description.strip(),
            marked_by=raised_by.strip(),         # Implementation note.
            marked_date=date.today(),
            status="Draft",                      # Implementation note.
            remarks=(
                f"TQ: {technical_query_no or 'N/A'} | Sketch: {site_sketch_file or 'N/A'}"
            ),
        )
        self.session.add(markup)

        # Implementation note.
        self.session.query(IsoRegistry).filter(
            IsoRegistry.project_id == project_id,
            IsoRegistry.iso_number == iso_clean,
        ).update(
            {"design_status": IsoStatus.REDLINE_IN_PROGRESS.value},
            synchronize_session=False,
        )

        self.session.commit()
        self.session.refresh(markup)

        logger.info(f"Redline markup registered on ISO '{iso_clean}' ({m_type}) by {raised_by}.")
        return markup

    def incorporate_markup_into_draft(
        self,
        markup_id: int,
        incorporated_by_cad: str,
        drawing_revision: str,
    ) -> AsBuiltMarkUp:
        """تأیید اعمال تغییرات خط قرمز در فایل نهایی CAD"""
        markup = self.session.query(AsBuiltMarkUp).filter(AsBuiltMarkUp.id == markup_id).first()
        if not markup:
            raise ValueError(f"Markup #{markup_id} not found.")

        markup.status = "Incorporated"           # Implementation note.
        markup.incorporated_by = incorporated_by_cad.strip()
        markup.incorporated_date = date.today()
        markup.remarks = (
            f"{markup.remarks or ''} | Target revision: {drawing_revision}"
        ).strip(" |")

        self.session.commit()
        self.session.refresh(markup)
        return markup

    # Implementation note.

    def add_walkdown_item(
        self,
        project_id: int,
        walkdown_no: str,
        subsystem_code: str,
        check_item: str,
        category: Union[WalkdownCategory, str],
        identified_by: str,
        assigned_contractor: Optional[str] = None,
        target_closure_date: Optional[date] = None,
    ) -> WalkdownChecklist:
        """ثبت پانچ استخراج‌شده از گشت مشترک واک‌ثرو"""
        cat_val = category.value if isinstance(category, WalkdownCategory) else str(category)

        # Implementation note.
        punch_a = 1 if cat_val == "A" else 0
        punch_b = 1 if cat_val == "B" else 0
        punch_c = 1 if cat_val == "C" else 0

        wd = WalkdownChecklist(
            project_id=project_id,
            walkdown_no=walkdown_no.strip().upper(),
            walkdown_type=cat_val,                 # Implementation note.
            inspection_date=target_closure_date or date.today(),  # Implementation note.
            lead_inspector=identified_by.strip(),
            contractor_rep=assigned_contractor.strip() if assigned_contractor else None,
            is_p_id_verified=True,
            is_slope_verified=True,
            is_supports_verified=True,
            is_valves_verified=True,
            is_instruments_verified=True,
            is_accessibility_verified=True,
            punch_a_found=punch_a,
            punch_b_found=punch_b,
            punch_c_found=punch_c,
            status="In Progress",
            remarks=f"[{cat_val}] {check_item.strip()} | Subsystem: {subsystem_code.strip().upper()}",
        )
        self.session.add(wd)
        self.session.commit()
        self.session.refresh(wd)
        return wd

    def close_walkdown(
        self,
        item_id: int,
        cleared_by_qc: str,
        cleared_by_client: Optional[str] = None,
        closure_remarks: str = "",
    ) -> WalkdownChecklist:
        """بستن و تأیید رفع مورد واک‌ثرو"""
        item = self.session.query(WalkdownChecklist).filter(
            WalkdownChecklist.id == item_id
        ).first()
        if not item:
            raise ValueError(f"Walkdown item #{item_id} not found.")

        item.status = "Completed"
        if cleared_by_client:
            item.client_rep = cleared_by_client
        item.remarks = (
            f"{item.remarks or ''} | Closed by {cleared_by_qc}: {closure_remarks}"
        ).strip(" |")

        self.session.commit()
        self.session.refresh(item)
        logger.info(f"Walkdown item #{item_id} CLOSED by QC: {cleared_by_qc}.")
        return item

    # Implementation note.

    def issue_mcc(
        self,
        project_id: int,
        certificate_no: str,
        subsystem_code: str,
        system_name: str,
        issued_by_contractor: str,
    ) -> MCCRecord:
        """
        صدور گواهینامه تکمیل مکانیکی ساب‌سیستم با بررسی عدم وجود پانچ دسته A.
        """
        subsys_clean = subsystem_code.strip().upper()

        # Implementation note.
        blocking_walkdowns = (
            self.session.query(WalkdownChecklist)
            .filter(
                WalkdownChecklist.project_id == project_id,
                WalkdownChecklist.walkdown_type == WalkdownCategory.CAT_A.value,
                WalkdownChecklist.status != "Completed",
            )
            .count()
        )

        if blocking_walkdowns > 0:
            raise MCCIssuanceBlockedError(
                f"Cannot issue MCC for Subsystem '{subsys_clean}': "
                f"{blocking_walkdowns} Open Category-A walkdown items must be cleared first!"
            )

        mcc = MCCRecord(
            project_id=project_id,
            mcc_no=certificate_no.strip().upper(),     # Implementation note.
            system_name=system_name.strip(),
            subsystem=subsys_clean,                    # Implementation note.
            scope_description=f"Issued by {issued_by_contractor}",
            status=MCCStatus.DRAFT.value,
            issued_date=date.today(),
            issued_by=issued_by_contractor.strip(),    # Implementation note.
            hydro_test_complete=False,
            ndt_complete=False,
            pwht_complete=False,
            reinstatement_complete=False,
            painting_complete=False,
            insulation_complete=False,
            punch_a_open=0,
            punch_b_open=0,
        )
        self.session.add(mcc)
        self.session.commit()
        self.session.refresh(mcc)

        logger.info(f"MCC '{certificate_no}' ISSUED for Subsystem '{subsys_clean}'.")
        return mcc

    def approve_and_handover_mcc(
        self,
        mcc_id: int,
        approved_by_qa_qc: str,
        approved_by_client: str,
        handover_remarks: str = "",
    ) -> MCCRecord:
        """امضای نهایی گواهینامه MCC و واگذاری ساب‌سیستم به راه‌اندازی"""
        mcc = self.session.query(MCCRecord).filter(MCCRecord.id == mcc_id).first()
        if not mcc:
            raise ValueError(f"MCC #{mcc_id} not found.")

        mcc.status = MCCStatus.APPROVED.value
        mcc.accepted_by = f"{approved_by_qa_qc} | {approved_by_client}"  # Implementation note.
        mcc.remarks = handover_remarks.strip()
        mcc.issued_date = mcc.issued_date or date.today()

        self.session.commit()
        self.session.refresh(mcc)
        logger.info(f"MCC '{mcc.mcc_no}' APPROVED & HANDED OVER to Commissioning.")
        return mcc

    # Implementation note.

    def get_turnover_readiness(self, project_id: int) -> Dict[str, Any]:
        """محاسبه ماتریس آمادگی تحویل نهایی با کوئری‌های تجمعی SQL"""
        # Implementation note.
        total_isos = self.session.query(func.count(IsoRegistry.id)).filter(
            IsoRegistry.project_id == project_id
        ).scalar() or 0

        asbuilt_isos = self.session.query(func.count(IsoRegistry.id)).filter(
            IsoRegistry.project_id == project_id,
            or_(
                IsoRegistry.status == "As-Built",
                IsoRegistry.asbuilt_complete == True,
            ),
        ).scalar() or 0

        # Implementation note.
        total_mccs = self.session.query(func.count(MCCRecord.id)).filter(
            MCCRecord.project_id == project_id
        ).scalar() or 0

        approved_mccs = self.session.query(func.count(MCCRecord.id)).filter(
            MCCRecord.project_id == project_id,
            MCCRecord.status == MCCStatus.APPROVED.value,
        ).scalar() or 0

        # Implementation note.
        open_cat_a = self.session.query(func.count(WalkdownChecklist.id)).filter(
            WalkdownChecklist.project_id == project_id,
            WalkdownChecklist.walkdown_type == WalkdownCategory.CAT_A.value,
            WalkdownChecklist.status != "Completed",
        ).scalar() or 0

        open_cat_b = self.session.query(func.count(WalkdownChecklist.id)).filter(
            WalkdownChecklist.project_id == project_id,
            WalkdownChecklist.walkdown_type == WalkdownCategory.CAT_B.value,
            WalkdownChecklist.status != "Completed",
        ).scalar() or 0

        # Implementation note.
        pending_markups = self.session.query(func.count(AsBuiltMarkUp.id)).filter(
            AsBuiltMarkUp.project_id == project_id,
            AsBuiltMarkUp.status.notin_(["Incorporated", "Closed", "Approved"]),
        ).scalar() or 0

        iso_asbuilt_pct = round((asbuilt_isos / total_isos * 100), 2) if total_isos > 0 else 0.0
        mcc_progress_pct = round((approved_mccs / total_mccs * 100), 2) if total_mccs > 0 else 0.0

        # Implementation note.
        return {
            # Implementation note.
            "asbuilt_isos":    asbuilt_isos,
            "total_isos":      total_isos,
            "mcc_approved":    approved_mccs,
            "mcc_issued":      total_mccs,
            "walkdown_open":   open_cat_a + open_cat_b,
            "pending_markups": pending_markups,

            # Implementation note.
            "project_id": project_id,
            "iso_progress": {
                "total_isos": total_isos,
                "asbuilt_certified_isos": asbuilt_isos,
                "asbuilt_completion_pct": iso_asbuilt_pct,
            },
            "mcc_turnover": {
                "total_mccs_issued": total_mccs,
                "approved_mccs": approved_mccs,
                "mcc_approval_pct": mcc_progress_pct,
            },
            "turnover_blockers": {
                "blocking_walkdown_cat_a": open_cat_a,
                "non_blocking_walkdown_cat_b": open_cat_b,
                "unincorporated_redlines": pending_markups,
                "is_turnover_ready": (
                    open_cat_a == 0
                    and pending_markups == 0
                    and iso_asbuilt_pct == 100.0
                ),
            },
        }