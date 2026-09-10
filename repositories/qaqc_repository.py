# -*- coding: utf-8 -*-
"""
repositories/qaqc_repository.py – PipeAgent v5.1
===============================================
مدیریت جامع فرآیندهای کنترل کیفیت و تضمین کیفیت (QA/QC)
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError

from repositories.base import BaseRepository
from db.models import PunchItem, NCRRecord, ITPItem

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Enums & QA/QC Engineering Definitions
# ──────────────────────────────────────────────

class PunchCategory(str, Enum):
    CAT_A = "A"
    CAT_B = "B"
    CAT_C = "C"


class PunchStatus(str, Enum):
    OPEN = "OPEN"
    RECTIFIED = "RECTIFIED"
    QC_CLEARED = "QC_CLEARED"
    CLIENT_ACCEPTED = "CLIENT_ACCEPTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class NCRStatus(str, Enum):
    ISSUED = "ISSUED"
    UNDER_REVIEW = "UNDER_REVIEW"
    DISPOSITION_PROPOSED = "DISPOSITION_PROPOSED"
    DISPOSITION_APPROVED = "DISPOSITION_APPROVED"
    RECTIFIED = "RECTIFIED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class NCRDisposition(str, Enum):
    REWORK = "REWORK"
    REPAIR = "REPAIR"
    USE_AS_IS = "USE_AS_IS"
    SCRAP = "SCRAP"
    RETURN_TO_VENDOR = "RTV"


class ITPPointType(str, Enum):
    HOLD = "H"
    WITNESS = "W"
    MONITORING = "M"
    REVIEW = "R"
    SURVEILLANCE = "S"


class ITPInspectionStatus(str, Enum):
    PENDING = "PENDING"
    RFI_ISSUED = "RFI_ISSUED"
    INSPECTED_PASS = "PASS"
    INSPECTED_FAIL = "FAIL"
    WAIVED = "WAIVED"


class PunchBlockingError(Exception):
    pass


class NCRDispositionError(Exception):
    pass


# ──────────────────────────────────────────────
#  1. Punch Repository Implementation
# ──────────────────────────────────────────────

class PunchRepository(BaseRepository[PunchItem]):
    """
    ریپازیتوری پیشرفته مدیریت پانچ‌لیست‌های پروژه‌های پایپینگ و مکانیکال
    """

    def __init__(self, db_manager: Any):
        super().__init__(db_manager, PunchItem)

    def get_items(
        self,
        project_id: int,
        category: Optional[Union[PunchCategory, str]] = None,
        status: Optional[Union[PunchStatus, str]] = None,
        test_package_id: Optional[int] = None,
        subsystem: Optional[str] = None,
        assigned_to: Optional[str] = None,
        is_cleared: Optional[bool] = None,
    ) -> List[PunchItem]:
        with self._session() as session:
            query = session.query(PunchItem).filter(PunchItem.project_id == project_id)

            if category:
                cat_val = category.value if isinstance(category, PunchCategory) else category
                query = query.filter(PunchItem.category == cat_val)

            if status:
                stat_val = status.value if isinstance(status, PunchStatus) else status
                query = query.filter(PunchItem.is_cleared == (stat_val == PunchStatus.QC_CLEARED.value))

            if test_package_id is not None:
                query = query.filter(PunchItem.test_package_id == test_package_id)

            if is_cleared is not None:
                query = query.filter(PunchItem.is_cleared == is_cleared)

            return query.order_by(PunchItem.category.asc(), desc(PunchItem.id)).all()

    def get_blocking_punches(
        self,
        project_id: int,
        test_package_id: Optional[int] = None,
    ) -> List[PunchItem]:
        return self.get_items(
            project_id=project_id,
            category=PunchCategory.CAT_A,
            test_package_id=test_package_id,
            is_cleared=False,
        )

    def add_punch(
        self,
        project_id: int,
        punch_number: str,
        category: Union[PunchCategory, str],
        description: str,
        raised_by: str,
        test_package_id: Optional[int] = None,
        line_number: Optional[str] = None,
        drawing_number: Optional[str] = None,
        assigned_contractor: Optional[str] = None,
        target_closure_date: Optional[date] = None,
    ) -> PunchItem:
        with self._session() as session:
            try:
                cat_val = category.value if isinstance(category, PunchCategory) else category
                punch = PunchItem(
                    project_id=project_id,
                    test_package_id=test_package_id,
                    line_number=line_number,
                    category=cat_val,
                    description=description.strip(),
                    raised_by=raised_by,
                    is_cleared=False,
                    remarks=f"Assigned to {assigned_contractor}" if assigned_contractor else ""
                )
                session.add(punch)
                session.commit()
                session.refresh(punch)
                return punch
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error creating punch item {punch_number}: {e}")
                raise

    def mark_rectified(
        self,
        punch_id: int,
        rectified_by: str,
        contractor_remarks: str = "",
    ) -> Optional[PunchItem]:
        with self._session() as session:
            try:
                punch = session.query(PunchItem).filter(PunchItem.id == punch_id).first()
                if not punch:
                    return None

                punch.cleared_by = rectified_by
                punch.remarks = contractor_remarks

                session.commit()
                session.refresh(punch)
                return punch
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error rectifying punch #{punch_id}: {e}")
                raise

    def clear_item(
        self,
        punch_id: int,
        cleared_by: str,
        client_witness: Optional[str] = None,
        qc_comments: str = "",
    ) -> Optional[PunchItem]:
        with self._session() as session:
            try:
                punch = session.query(PunchItem).filter(PunchItem.id == punch_id).first()
                if not punch:
                    return None

                punch.is_cleared = True
                punch.cleared_by = cleared_by
                punch.cleared_date = date.today()
                punch.remarks = qc_comments

                session.commit()
                session.refresh(punch)
                return punch
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error clearing punch #{punch_id}: {e}")
                raise

    def bulk_clear_punches(
        self,
        punch_ids: List[int],
        cleared_by: str,
    ) -> int:
        with self._session() as session:
            try:
                updated_count = (
                    session.query(PunchItem)
                    .filter(
                        PunchItem.id.in_(punch_ids),
                    )
                    .update(
                        {
                            "is_cleared": True,
                            "cleared_by": cleared_by,
                            "cleared_date": date.today(),
                        },
                        synchronize_session="fetch",
                    )
                )
                session.commit()
                return updated_count
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Bulk clear punches error: {e}")
                raise

    def get_summary(
        self,
        project_id: int,
        test_package_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self._session() as session:
            query = session.query(
                PunchItem.category,
                PunchItem.is_cleared,
                func.count(PunchItem.id).label("count"),
            ).filter(PunchItem.project_id == project_id)

            if test_package_id is not None:
                query = query.filter(PunchItem.test_package_id == test_package_id)

            results = query.group_by(PunchItem.category, PunchItem.is_cleared).all()

            summary = {
                "A": {"OPEN": 0, "CLEARED": 0, "TOTAL": 0},
                "B": {"OPEN": 0, "CLEARED": 0, "TOTAL": 0},
                "C": {"OPEN": 0, "CLEARED": 0, "TOTAL": 0},
            }

            total_punches = 0
            total_cleared = 0

            for cat, is_cleared, count in results:
                if cat in summary:
                    summary[cat]["TOTAL"] += count
                    total_punches += count
                    if is_cleared:
                        summary[cat]["CLEARED"] += count
                        total_cleared += count
                    else:
                        summary[cat]["OPEN"] += count

            return {
                "project_id": project_id,
                "test_package_id": test_package_id,
                "matrix": summary,
                "total_punches": total_punches,
                "total_cleared": total_cleared,
                "clearance_percentage": round((total_cleared / total_punches * 100), 2) if total_punches > 0 else 100.0,
                "is_hydrotest_blocked": summary["A"]["OPEN"] > 0,
                "blocking_cat_a_count": summary["A"]["OPEN"],
            }


# ──────────────────────────────────────────────
#  2. NCR Repository Implementation
# ──────────────────────────────────────────────

class NCRRepository(BaseRepository[NCRRecord]):
    """
    ریپازیتوری مدیریت گزارشات عدم انطباق (Non-Conformance Reports)
    """

    def __init__(self, db_manager: Any):
        super().__init__(db_manager, NCRRecord)

    def get_records(
        self,
        project_id: int,
        status: Optional[Union[NCRStatus, str]] = None,
        severity: Optional[str] = None,
        discipline: Optional[str] = None,
    ) -> List[NCRRecord]:
        with self._session() as session:
            query = session.query(NCRRecord).filter(NCRRecord.project_id == project_id)

            if status:
                stat_val = status.value if isinstance(status, NCRStatus) else status
                query = query.filter(NCRRecord.status == stat_val)

            return query.order_by(desc(NCRRecord.id)).all()

    def get_open_critical_ncrs(self, project_id: int) -> List[NCRRecord]:
        with self._session() as session:
            return (
                session.query(NCRRecord)
                .filter(
                    NCRRecord.project_id == project_id,
                    NCRRecord.status.notin_([NCRStatus.CLOSED.value, "Closed"]),
                )
                .order_by(NCRRecord.id.desc())
                .all()
            )

    def issue_ncr(
        self,
        project_id: int,
        ncr_number: str,
        title: str,
        description: str,
        issued_by: str,
        issued_to_contractor: str,
        spec_requirement: str,
        actual_condition: str,
        severity: str = "MAJOR",
        discipline: str = "PIPING",
    ) -> NCRRecord:
        with self._session() as session:
            try:
                ncr = NCRRecord(
                    project_id=project_id,
                    ncr_no=ncr_number.strip().upper(),
                    item_type=discipline,
                    item_reference=title.strip(),
                    description=description.strip(),
                    raised_by=issued_by,
                    status=NCRStatus.ISSUED.value,
                    raised_date=date.today(),
                )
                session.add(ncr)
                session.commit()
                session.refresh(ncr)
                return ncr
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error issuing NCR {ncr_number}: {e}")
                raise

    def propose_disposition(
        self,
        ncr_id: int,
        disposition_type: Union[NCRDisposition, str],
        proposed_action_details: str,
        root_cause_analysis: str,
        proposed_by: str,
        target_rectification_date: Optional[date] = None,
    ) -> Optional[NCRRecord]:
        with self._session() as session:
            try:
                ncr = session.query(NCRRecord).filter(NCRRecord.id == ncr_id).first()
                if not ncr:
                    return None

                disp_val = disposition_type.value if isinstance(disposition_type, NCRDisposition) else disposition_type

                ncr.disposition = disp_val
                ncr.corrective_action = proposed_action_details
                ncr.root_cause = root_cause_analysis
                ncr.status = NCRStatus.DISPOSITION_PROPOSED.value

                session.commit()
                session.refresh(ncr)
                return ncr
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error proposing disposition for NCR #{ncr_id}: {e}")
                raise

    def approve_disposition(
        self,
        ncr_id: int,
        approved_by_engineering: str,
        client_approval_ref: Optional[str] = None,
        comments: str = "",
    ) -> Optional[NCRRecord]:
        with self._session() as session:
            try:
                ncr = session.query(NCRRecord).filter(NCRRecord.id == ncr_id).first()
                if not ncr:
                    return None

                ncr.status = NCRStatus.DISPOSITION_APPROVED.value
                ncr.remarks = comments

                session.commit()
                session.refresh(ncr)
                return ncr
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error approving NCR #{ncr_id} disposition: {e}")
                raise

    def close_record(
        self,
        ncr_id: int,
        closed_by: str,
        corrective_preventive_action_verified: bool = True,
        verification_report_ref: Optional[str] = None,
        closure_remarks: str = "",
    ) -> Optional[NCRRecord]:
        with self._session() as session:
            try:
                ncr = session.query(NCRRecord).filter(NCRRecord.id == ncr_id).first()
                if not ncr:
                    return None

                ncr.status = NCRStatus.CLOSED.value
                ncr.closed_by = closed_by
                ncr.closed_date = date.today()
                ncr.remarks = closure_remarks

                session.commit()
                session.refresh(ncr)
                return ncr
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error closing NCR #{ncr_id}: {e}")
                raise

    def get_ncr_aging_report(self, project_id: int) -> List[Dict[str, Any]]:
        with self._session() as session:
            open_ncrs = (
                session.query(NCRRecord)
                .filter(
                    NCRRecord.project_id == project_id,
                    NCRRecord.status != NCRStatus.CLOSED.value,
                )
                .all()
            )

            now = date.today()
            aging_list = []
            for ncr in open_ncrs:
                days_open = (now - ncr.raised_date).days
                aging_list.append({
                    "ncr_id": ncr.id,
                    "ncr_number": ncr.ncr_no,
                    "title": ncr.item_reference,
                    "status": ncr.status,
                    "days_open": days_open,
                    "is_critical_delay": days_open > 14,
                })

            return sorted(aging_list, key=lambda x: x["days_open"], reverse=True)


# ──────────────────────────────────────────────
#  3. ITP Repository Implementation
# ──────────────────────────────────────────────

class ITPRepository(BaseRepository[ITPItem]):
    """
    ریپازیتوری ماتریس برنامه بازرسی و تست (Inspection & Test Plan)
    """

    def __init__(self, db_manager: Any):
        super().__init__(db_manager, ITPItem)

    def get_items(
        self,
        project_id: int,
        itp_number: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> List[ITPItem]:
        with self._session() as session:
            query = session.query(ITPItem).filter(ITPItem.project_id == project_id)
            if itp_number:
                query = query.filter(ITPItem.itp_number == itp_number.strip())
            return query.order_by(ITPItem.id.asc()).all()

    def add_itp_item(
        self,
        project_id: int,
        itp_number: str,
        activity_description: str,
        reference_spec_code: str,
        contractor_point: Union[ITPPointType, str] = ITPPointType.HOLD,
        client_point: Union[ITPPointType, str] = ITPPointType.WITNESS,
        required_record_form: Optional[str] = None,
        sequence: int = 1,
    ) -> ITPItem:
        with self._session() as session:
            try:
                c_pt = contractor_point.value if isinstance(contractor_point, ITPPointType) else contractor_point
                cl_pt = client_point.value if isinstance(client_point, ITPPointType) else client_point

                item = ITPItem(
                    project_id=project_id,
                    itp_number=itp_number.strip().upper(),
                    activity_code=str(sequence),
                    activity_description=activity_description.strip(),
                    controlling_doc=reference_spec_code.strip(),
                    contractor_point=c_pt,
                    client_point=cl_pt,
                    status=ITPInspectionStatus.PENDING.value,
                )
                session.add(item)
                session.commit()
                session.refresh(item)
                return item
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error adding ITP item to {itp_number}: {e}")
                raise

    def record_inspection_signoff(
        self,
        itp_item_id: int,
        rfi_number: str,
        inspector_qc: str,
        inspector_client: Optional[str] = None,
        is_passed: bool = True,
        is_waived_by_client: bool = False,
        comments: str = "",
    ) -> Optional[ITPItem]:
        with self._session() as session:
            try:
                itp_item = session.query(ITPItem).filter(ITPItem.id == itp_item_id).first()
                if not itp_item:
                    return None

                if is_waived_by_client:
                    itp_item.status = ITPInspectionStatus.WAIVED.value
                else:
                    itp_item.status = (
                        ITPInspectionStatus.INSPECTED_PASS.value
                        if is_passed
                        else ITPInspectionStatus.INSPECTED_FAIL.value
                    )

                itp_item.inspected_by = inspector_qc
                itp_item.inspected_date = date.today()
                itp_item.remarks = comments

                session.commit()
                session.refresh(itp_item)
                return itp_item
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error signing off ITP item #{itp_item_id}: {e}")
                raise


# ──────────────────────────────────────────────
#  4. QA/QC Unit of Work
# ──────────────────────────────────────────────

class QAQCUnitOfWork:
    """
    هماهنگ‌کننده کیفیت و صحت پرونده‌های تکمیل مکانیکی
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.punches = PunchRepository(db_manager)
        self.ncrs = NCRRepository(db_manager)
        self.itp = ITPRepository(db_manager)

    def verify_package_qc_clearance(
        self, project_id: int, test_package_id: int
    ) -> Dict[str, Any]:
        blocking_punches = self.punches.get_blocking_punches(
            project_id=project_id,
            test_package_id=test_package_id,
        )
        open_ncrs = self.ncrs.get_open_critical_ncrs(project_id=project_id)

        is_cleared = (len(blocking_punches) == 0) and (len(open_ncrs) == 0)

        return {
            "test_package_id": test_package_id,
            "quality_clearance_approved": is_cleared,
            "blocking_punch_a_count": len(blocking_punches),
            "open_critical_ncr_count": len(open_ncrs),
            "blocking_punch_ids": [p.id for p in blocking_punches],
            "open_ncr_numbers": [n.ncr_no for n in open_ncrs],
        }