# -*- coding: utf-8 -*-
"""
repositories/project_repository.py – PipeAgent v5.1
===================================================
مدیریت جامع موجودیت پروژه، چرخه حیات و شاخص‌های کلیدی عملکرد (KPIs)
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
    Project,
    Weld,
    NDTRecord,
    LeakTestRecord,
    PunchItem,
)
WeldJoint = Weld  # Implementation note.

from repositories.base import BaseRepository
from db.manager import DatabaseManager

logger = logging.getLogger(__name__)


class ProjectStatus(str, Enum):
    PLANNING = "PLANNING"
    ENGINEERING = "ENGINEERING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    MECHANICAL_COMPLETION = "MC"
    COMMISSIONING = "COMMISSIONING"
    HANDOVER = "HANDOVER"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class ProjectType(str, Enum):
    OIL_GAS_REFINERY = "OIL_GAS_REFINERY"
    PETROCHEMICAL = "PETROCHEMICAL"
    POWER_PLANT = "POWER_PLANT"
    PIPELINE = "PIPELINE"
    OFFSHORE_PLATFORM = "OFFSHORE_PLATFORM"
    TANK_FARM = "TANK_FARM"


class ProjectRepository(BaseRepository[Project]):
    """
    ریپازیتوری پیشرفته مدیریت پروژه‌ها
    """

    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager, Project)

    def get_by_code(
        self,
        project_code: str,
        load_relations: bool = False,
    ) -> Optional[Project]:
        with self._db_manager.session_scope() as session:
            query = session.query(Project).filter(
                func.upper(Project.project_code) == project_code.strip().upper()
            )
            return query.first()

    def get_by_id_with_details(self, project_id: int) -> Optional[Project]:
        with self._db_manager.session_scope() as session:
            return (
                session.query(Project)
                .filter(Project.id == project_id)
                .first()
            )

    def search_projects(
        self,
        keyword: Optional[str] = None,
        status: Optional[Union[ProjectStatus, str]] = None,
        client_name: Optional[str] = None,
        project_type: Optional[Union[ProjectType, str]] = None,
        is_active_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Project], int]:
        with self._db_manager.session_scope() as session:
            query = session.query(Project)

            if keyword:
                search_filter = or_(
                    Project.title.ilike(f"%{keyword.strip()}%"),
                    Project.project_code.ilike(f"%{keyword.strip()}%"),
                )
                query = query.filter(search_filter)

            if status:
                status_val = status.value if isinstance(status, ProjectStatus) else status
                query = query.filter(Project.status == status_val)

            if client_name:
                query = query.filter(Project.client.ilike(f"%{client_name.strip()}%"))

            if is_active_only:
                query = query.filter(
                    Project.status.in_([ProjectStatus.ACTIVE.value, "ACTIVE"])
                )

            total_count = query.count()
            projects = (
                query.order_by(desc(Project.id))
                .offset(offset)
                .limit(limit)
                .all()
            )

            return projects, total_count

    def get_active_projects(self) -> List[Project]:
        projects, _ = self.search_projects(is_active_only=True, limit=1000)
        return projects

    def create_project(
        self,
        project_code: str,
        title: str,
        client_name: str,
        start_date: Optional[date] = None,
        target_end_date: Optional[date] = None,
        project_type: Optional[ProjectType] = None,
        created_by: str = "system",
        **additional_fields,
    ) -> Project:
        with self._db_manager.session_scope() as session:
            try:
                existing = session.query(Project).filter(
                    func.upper(Project.project_code) == project_code.strip().upper()
                ).first()
                if existing:
                    raise ValueError(f"Project with code '{project_code}' already exists.")

                new_project = Project(
                    project_code=project_code.strip().upper(),
                    title=title.strip(),
                    client=client_name.strip(),
                    status=ProjectStatus.PLANNING.value,
                    **additional_fields,
                )

                session.add(new_project)
                session.flush()
                session.refresh(new_project)
                return new_project

            except SQLAlchemyError as e:
                logger.error("Error creating project %s: %s", project_code, e)
                raise

    def update_status(
        self,
        project_id: int,
        new_status: ProjectStatus,
        updated_by: str,
        remarks: str = "",
    ) -> Optional[Project]:
        with self._db_manager.session_scope() as session:
            try:
                project = session.query(Project).filter(Project.id == project_id).first()
                if not project:
                    return None

                old_status = project.status
                project.status = new_status.value
                session.flush()
                session.refresh(project)
                logger.info(
                    "Project #%s status %s -> %s by %s (%s)",
                    project_id, old_status, new_status.value, updated_by, remarks,
                )
                return project

            except SQLAlchemyError as e:
                logger.error("Failed to update status for project #%s: %s", project_id, e)
                raise

    def soft_delete_or_archive(
        self,
        project_id: int,
        deleted_by: str,
        archive_only: bool = True,
    ) -> bool:
        with self._db_manager.session_scope() as session:
            try:
                project = session.query(Project).filter(Project.id == project_id).first()
                if not project:
                    return False

                if archive_only:
                    project.status = ProjectStatus.ARCHIVED.value
                else:
                    project.soft_delete()

                return True
            except SQLAlchemyError as e:
                logger.error("Error archiving/deleting project #%s: %s", project_id, e)
                raise

    def get_project_executive_summary(self, project_id: int) -> Dict[str, Any]:
        with self._db_manager.session_scope() as session:
            project = session.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise ValueError(f"Project with ID #{project_id} not found.")

            table_names = session.get_bind().table_names()

            total_welds = 0
            completed_welds = 0
            if "welds" in table_names:
                total_welds = session.query(func.count(Weld.id)).filter(Weld.project_id == project_id).scalar() or 0
                completed_welds = session.query(func.count(Weld.id)).filter(
                    Weld.project_id == project_id,
                    Weld.weld_end_datetime.isnot(None),
                ).scalar() or 0

            ndt_passed = 0
            if "ndt_records" in table_names:
                ndt_passed = session.query(func.count(func.distinct(NDTRecord.weld_id_fk))).join(Weld, NDTRecord.weld_id_fk == Weld.id).filter(
                    Weld.project_id == project_id,
                    NDTRecord.result.in_(["Accept", "ACC"]),
                ).scalar() or 0

            total_leak_tests = 0
            passed_leak_tests = 0
            if "leak_test_records" in table_names:
                total_leak_tests = session.query(func.count(LeakTestRecord.id)).filter(LeakTestRecord.project_id == project_id).scalar() or 0
                passed_leak_tests = session.query(func.count(LeakTestRecord.id)).filter(
                    LeakTestRecord.project_id == project_id,
                    LeakTestRecord.result == "Pass",
                ).scalar() or 0

            open_category_a_punches = 0
            if "punch_items" in table_names:
                open_category_a_punches = session.query(func.count(PunchItem.id)).filter(
                    PunchItem.project_id == project_id,
                    PunchItem.category == "A",
                    PunchItem.is_cleared == False,
                ).scalar() or 0

            welding_pct = round((completed_welds / total_welds * 100), 2) if total_welds > 0 else 0.0
            ndt_pct = round((ndt_passed / completed_welds * 100), 2) if completed_welds > 0 else 0.0
            hydro_pct = round((passed_leak_tests / total_leak_tests * 100), 2) if total_leak_tests > 0 else 0.0

            return {
                "project_id": project.id,
                "project_code": project.project_code,
                "title": project.title,
                "status": project.status,
                "progress_metrics": {
                    "total_welds": total_welds,
                    "completed_welds": completed_welds,
                    "welding_progress_pct": welding_pct,
                    "ndt_cleared_welds": ndt_passed,
                    "ndt_clearance_pct": ndt_pct,
                    "total_pressure_tests": total_leak_tests,
                    "passed_pressure_tests": passed_leak_tests,
                    "hydrotest_progress_pct": hydro_pct,
                },
                "quality_flags": {
                    "blocking_punches_category_a": open_category_a_punches,
                    "ready_for_mc": (welding_pct == 100.0 and ndt_pct == 100.0 and hydro_pct == 100.0 and open_category_a_punches == 0),
                },
            }