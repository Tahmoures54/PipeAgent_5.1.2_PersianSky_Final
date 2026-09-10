# -*- coding: utf-8 -*-
"""
repositories/test_package_repository.py – PipeAgent v5.1
========================================================
مدیریت جامع پکیج‌های تست فشار (Test Packages)
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError

from db.models import (
    TestPackage,
    Weld,
    NDTRecord,
    PunchItem,
    ReinstatementItem,
    LeakTestRecord,
    Spool,
)
WeldJoint = Weld  # Implementation note.

from repositories.base import BaseRepository
from db.manager import DatabaseManager

logger = logging.getLogger(__name__)


class TestPackageStatus(str, Enum):
    DRAFT = "DRAFT"
    QA_QC_REVIEW = "QA_QC_REVIEW"
    WALKDOWN_PUNCHING = "WALKDOWN_PUNCHING"
    READY_FOR_TEST = "READY_FOR_TEST"
    TESTING_IN_PROGRESS = "TESTING"
    TEST_ACCEPTED = "TEST_ACCEPTED"
    DRAINING_DRYING = "DRAINING_DRYING"
    REINSTATEMENT = "REINSTATEMENT"
    DOSSIER_CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class TestMedium(str, Enum):
    POTABLE_WATER = "POTABLE_WATER"
    DEMIN_WATER = "DEMIN_WATER"
    PLANT_AIR = "PLANT_AIR"
    NITROGEN = "NITROGEN"
    HYDROCARBON_SERVICE = "SERVICE_FLUID"


class TestType(str, Enum):
    HYDROSTATIC = "HYDROSTATIC"
    PNEUMATIC = "PNEUMATIC"
    SENSITIVE_LEAK = "SENSITIVE_LEAK"
    INITIAL_SERVICE = "INITIAL_SERVICE"


class TestPackageBlockedError(Exception):
    pass


class NDTClearanceIncompleteError(Exception):
    pass


class TestPackageRepository(BaseRepository[TestPackage]):
    """
    ریپازیتوری پیشرفته مدیریت پکیج‌های آزمون فشار (Test Packages)
    """

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, TestPackage)

    def get_by_package_number(
        self,
        project_id: int,
        package_number: str,
        load_details: bool = False,
    ) -> Optional[TestPackage]:
        with self._session() as session:
            query = session.query(TestPackage).filter(
                TestPackage.project_id == project_id,
                func.upper(TestPackage.package_number) == package_number.strip().upper(),
            )
            return query.first()

    def search_packages(
        self,
        project_id: int,
        keyword: Optional[str] = None,
        status: Optional[Union[TestPackageStatus, str]] = None,
        test_type: Optional[Union[TestType, str]] = None,
        system_code: Optional[str] = None,
        subsystem_code: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[List[TestPackage], int]:
        with self._session() as session:
            query = session.query(TestPackage).filter(TestPackage.project_id == project_id)

            if keyword:
                query = query.filter(
                    or_(
                        TestPackage.package_number.ilike(f"%{keyword.strip()}%"),
                        TestPackage.description.ilike(f"%{keyword.strip()}%"),
                    )
                )

            if status:
                stat_val = status.value if isinstance(status, TestPackageStatus) else status
                query = query.filter(TestPackage.status == stat_val)

            total_count = query.count()
            packages = (
                query.order_by(TestPackage.package_number.asc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            return packages, total_count

    def get_by_status(
        self, project_id: int, status: Union[TestPackageStatus, str]
    ) -> List[TestPackage]:
        stat_val = status.value if isinstance(status, TestPackageStatus) else status
        with self._session() as session:
            return (
                session.query(TestPackage)
                .filter(
                    TestPackage.project_id == project_id,
                    TestPackage.status == stat_val,
                )
                .order_by(TestPackage.package_number.asc())
                .all()
            )

    def evaluate_hydro_readiness(
        self, project_id: int, package_id: int
    ) -> Dict[str, Any]:
        with self._session() as session:
            pkg = session.query(TestPackage).filter(TestPackage.id == package_id).first()
            if not pkg:
                raise ValueError(f"TestPackage #{package_id} not found.")

            # Implementation note.
            welds = session.query(Weld).filter(Weld.project_id == project_id).all()
            total_welds = len(welds)
            cleared_welds = sum(1 for w in welds if getattr(w, "status", "") == "NDT Accepted")
            ndt_100_cleared = (total_welds > 0) and (total_welds == cleared_welds)

            # Implementation note.
            open_cat_a_punches = session.query(PunchItem).filter(
                PunchItem.test_package_id == package_id,
                PunchItem.category == "A",
                PunchItem.is_cleared == False,
            ).all()

            # Implementation note.
            spools = session.query(Spool).filter(Spool.project_id == project_id).all()
            total_spools = len(spools)
            erected_spools = sum(1 for s in spools if getattr(s, "status", "") == "ERECTED")
            all_spools_erected = (total_spools == 0) or (total_spools == erected_spools)

            is_ready = ndt_100_cleared and (len(open_cat_a_punches) == 0) and all_spools_erected

            return {
                "package_id": pkg.id,
                "package_number": pkg.package_number,
                "ready_for_test": is_ready,
                "ndt_clearance": {
                    "total_welds": total_welds,
                    "cleared_welds": cleared_welds,
                    "is_100_percent": ndt_100_cleared,
                },
                "blocking_punches": {
                    "open_cat_a_count": len(open_cat_a_punches),
                    "punch_ids": [p.id for p in open_cat_a_punches],
                },
                "erection_status": {
                    "total_spools": total_spools,
                    "erected_spools": erected_spools,
                    "is_complete": all_spools_erected,
                },
            }

    def approve_for_hydrotest(
        self,
        package_id: int,
        approved_by_qc: str,
        approved_by_client: Optional[str] = None,
    ) -> TestPackage:
        with self._session() as session:
            try:
                pkg = session.query(TestPackage).filter(TestPackage.id == package_id).first()
                if not pkg:
                    raise ValueError(f"TestPackage #{package_id} not found.")

                readiness = self.evaluate_hydro_readiness(pkg.project_id, package_id)
                if not readiness["ready_for_test"]:
                    reasons = []
                    if not readiness["ndt_clearance"]["is_100_percent"]:
                        reasons.append("NDT Clearance is incomplete")
                    if readiness["blocking_punches"]["open_cat_a_count"] > 0:
                        reasons.append(f"{readiness['blocking_punches']['open_cat_a_count']} Open Category A Punches exist")
                    raise TestPackageBlockedError(f"Cannot approve Test Package #{package_id}: " + "; ".join(reasons))

                pkg.status = TestPackageStatus.READY_FOR_TEST.value
                pkg.tested_by = approved_by_qc
                pkg.test_date = date.today()

                session.commit()
                session.refresh(pkg)
                return pkg

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error approving TestPackage #{package_id}: {e}")
                raise

    def record_test_execution_pass(
        self,
        package_id: int,
        actual_test_pressure_bar: float,
        holding_time_minutes: int,
        test_medium: Union[TestMedium, str],
        witnessed_by_qc: str,
        witnessed_by_client: str,
        report_number: str,
    ) -> TestPackage:
        med_val = test_medium.value if isinstance(test_medium, TestMedium) else test_medium
        with self._session() as session:
            try:
                pkg = session.query(TestPackage).filter(TestPackage.id == package_id).first()
                if not pkg:
                    raise ValueError(f"TestPackage #{package_id} not found.")

                pkg.status = TestPackageStatus.TEST_ACCEPTED.value
                pkg.test_pressure_bar = actual_test_pressure_bar
                pkg.test_medium = med_val
                pkg.test_duration_min = holding_time_minutes
                pkg.tested_by = witnessed_by_qc
                pkg.witnessed_by = witnessed_by_client
                pkg.test_date = date.today()

                session.commit()
                session.refresh(pkg)
                return pkg

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error recording test execution for package #{package_id}: {e}")
                raise

    def close_and_handover_dossier(
        self,
        package_id: int,
        closed_by: str,
        qc_manager_sign: str,
        client_rep_sign: str,
    ) -> TestPackage:
        with self._session() as session:
            try:
                pkg = session.query(TestPackage).filter(TestPackage.id == package_id).first()
                if not pkg:
                    raise ValueError(f"TestPackage #{package_id} not found.")

                pending_reinstatements = session.query(ReinstatementItem).filter(
                    ReinstatementItem.test_package_id == package_id,
                    ReinstatementItem.status != "COMPLETED",
                ).count()

                if pending_reinstatements > 0:
                    raise ValueError(f"Cannot close package: {pending_reinstatements} Reinstatement items are still PENDING!")

                pkg.status = TestPackageStatus.DOSSIER_CLOSED.value
                pkg.tested_by = closed_by
                pkg.witnessed_by = client_rep_sign

                session.commit()
                session.refresh(pkg)
                return pkg

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error closing test package dossier #{package_id}: {e}")
                raise

    def get_project_hydrotest_kpis(self, project_id: int) -> Dict[str, Any]:
        with self._session() as session:
            total_packages = session.query(func.count(TestPackage.id)).filter(
                TestPackage.project_id == project_id
            ).scalar() or 0

            status_counts = (
                session.query(TestPackage.status, func.count(TestPackage.id))
                .filter(TestPackage.project_id == project_id)
                .group_by(TestPackage.status)
                .all()
            )
            status_map = {stat: cnt for stat, cnt in status_counts}

            prepared = status_map.get(TestPackageStatus.READY_FOR_TEST.value, 0)
            tested = (
                status_map.get(TestPackageStatus.TEST_ACCEPTED.value, 0)
                + status_map.get(TestPackageStatus.DRAINING_DRYING.value, 0)
                + status_map.get(TestPackageStatus.REINSTATEMENT.value, 0)
                + status_map.get(TestPackageStatus.DOSSIER_CLOSED.value, 0)
            )
            reinstated = (
                status_map.get(TestPackageStatus.REINSTATEMENT.value, 0)
                + status_map.get(TestPackageStatus.DOSSIER_CLOSED.value, 0)
            )
            closed = status_map.get(TestPackageStatus.DOSSIER_CLOSED.value, 0)

            tested_pct = round((tested / total_packages * 100), 2) if total_packages > 0 else 0.0
            closed_pct = round((closed / total_packages * 100), 2) if total_packages > 0 else 0.0

            return {
                "project_id": project_id,
                "total_test_packages": total_packages,
                "summary": {
                    "in_draft_or_review": status_map.get(TestPackageStatus.DRAFT.value, 0) + status_map.get(TestPackageStatus.QA_QC_REVIEW.value, 0),
                    "walkdown_punching": status_map.get(TestPackageStatus.WALKDOWN_PUNCHING.value, 0),
                    "ready_for_test": prepared,
                    "tested_successfully": tested,
                    "reinstatement_completed": reinstated,
                    "dossiers_closed": closed,
                },
                "progress_percentages": {
                    "tested_progress_pct": tested_pct,
                    "handover_closed_pct": closed_pct,
                },
            }