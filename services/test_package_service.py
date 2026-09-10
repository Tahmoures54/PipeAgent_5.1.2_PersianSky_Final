# -*- coding: utf-8 -*-
"""
test_package_service.py - PipeAgent
====================================
Test Package lifecycle management service.

Handles creation, validation, status transitions, item association,
hydro-test / pneumatic-test readiness checks, and reporting for
piping test packages (also called "test packs" or "hydro packs").

Author : PipeAgent Engineering
Version: 5.0.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core.exceptions import (
    PipeAgentError,
    ValidationError,
    NotFoundError,
    StateTransitionError,
)
from core.constants import (
    TEST_PACKAGE_STATUS_DRAFT,
    TEST_PACKAGE_STATUS_READY,
    TEST_PACKAGE_STATUS_TESTING,
    TEST_PACKAGE_STATUS_PASSED,
    TEST_PACKAGE_STATUS_FAILED,
    TEST_PACKAGE_STATUS_REINSTATED,
    TEST_PACKAGE_STATUS_CANCELLED,
)

logger = logging.getLogger("pipeagent.services.test_package")


# ─────────────────────────────────────────────
#  Enums & Constants
# ─────────────────────────────────────────────

class TestType(str, Enum):
    HYDROSTATIC = "hydrostatic"
    PNEUMATIC = "pneumatic"
    HYDRO_PNEUMATIC = "hydro_pneumatic"
    SENSITIVITY_LEAK = "sensitivity_leak"
    SERVICE_TEST = "service_test"


class TestMedium(str, Enum):
    WATER = "water"
    GLYCOL_WATER = "glycol_water"
    AIR = "air"
    NITROGEN = "nitrogen"
    STEAM = "steam"
    SERVICE_FLUID = "service_fluid"


class PackageStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    READY = "ready"
    TESTING = "testing"
    PASSED = "passed"
    FAILED = "failed"
    REINSTATED = "reinstated"
    CANCELLED = "cancelled"


# Valid state transitions
_ALLOWED_TRANSITIONS: Dict[PackageStatus, List[PackageStatus]] = {
    PackageStatus.DRAFT: [
        PackageStatus.PENDING_REVIEW,
        PackageStatus.CANCELLED,
    ],
    PackageStatus.PENDING_REVIEW: [
        PackageStatus.APPROVED,
        PackageStatus.DRAFT,
        PackageStatus.CANCELLED,
    ],
    PackageStatus.APPROVED: [
        PackageStatus.READY,
        PackageStatus.DRAFT,
        PackageStatus.CANCELLED,
    ],
    PackageStatus.READY: [
        PackageStatus.TESTING,
        PackageStatus.APPROVED,
        PackageStatus.CANCELLED,
    ],
    PackageStatus.TESTING: [
        PackageStatus.PASSED,
        PackageStatus.FAILED,
    ],
    PackageStatus.PASSED: [
        PackageStatus.REINSTATED,
    ],
    PackageStatus.FAILED: [
        PackageStatus.READY,
        PackageStatus.CANCELLED,
    ],
    PackageStatus.REINSTATED: [],
    PackageStatus.CANCELLED: [],
}


# ─────────────────────────────────────────────
#  Data Classes
# ─────────────────────────────────────────────

@dataclass
class TestPackageItem:
    """A single item (weld / spool / valve / flange) inside a test package."""
    item_id: Optional[int] = None
    package_id: Optional[int] = None
    item_type: str = ""          # weld | spool | valve | flange | fitting
    item_number: str = ""
    line_number: str = ""
    drawing_number: str = ""
    is_boundary: bool = False    # boundary blind / isolation point
    remarks: str = ""


@dataclass
class TestPackageChecklist:
    """Pre-test checklist verification."""
    checklist_id: Optional[int] = None
    package_id: Optional[int] = None
    check_item: str = ""
    is_verified: bool = False
    verified_by: str = ""
    verified_date: Optional[datetime] = None
    remarks: str = ""


@dataclass
class TestResult:
    """Recorded test result for a package."""
    result_id: Optional[int] = None
    package_id: Optional[int] = None
    test_type: str = ""
    test_medium: str = ""
    test_pressure: float = 0.0       # bar / psi
    holding_time_minutes: int = 0
    ambient_temp_c: float = 0.0
    medium_temp_c: float = 0.0
    pressure_gauge_id: str = ""
    recorder_chart_no: str = ""
    result_status: str = ""          # pass | fail
    witnessed_by: str = ""
    client_witness: str = ""
    test_date: Optional[datetime] = None
    remarks: str = ""


@dataclass
class TestPackageSummary:
    """Lightweight summary for dashboard / list views."""
    package_id: int
    package_number: str
    system: str
    test_type: str
    status: str
    total_items: int
    completion_pct: float
    planned_date: Optional[date]
    actual_date: Optional[date]


# ─────────────────────────────────────────────
#  Main Service
# ─────────────────────────────────────────────

class TestPackageService:
    """
    Orchestrates all business logic related to piping test packages.

    Dependencies are injected via constructor so the service stays
    testable and decoupled from the persistence layer.
    """

    def __init__(
        self,
        repository,
        weld_repository=None,
        ndt_repository=None,
        spool_repository=None,
        valve_repository=None,
        qaqc_repository=None,
    ):
        self.repo = repository
        self.weld_repo = weld_repository
        self.ndt_repo = ndt_repository
        self.spool_repo = spool_repository
        self.valve_repo = valve_repository
        self.qaqc_repo = qaqc_repository

    # ── CRUD ────────────────────────────────

    def create_package(
        self,
        package_number: str,
        project_id: int,
        *,
        system: str = "",
        subsystem: str = "",
        test_type: str = TestType.HYDROSTATIC.value,
        test_medium: str = TestMedium.WATER.value,
        design_pressure: float = 0.0,
        test_pressure: float = 0.0,
        line_numbers: str = "",
        p_and_id_refs: str = "",
        planned_test_date: Optional[date] = None,
        created_by: str = "",
        remarks: str = "",
    ) -> int:
        """Create a new test package in DRAFT status.

        Returns the new package ID.
        """
        self._validate_package_number(package_number)
        self._validate_pressures(design_pressure, test_pressure)

        if self.repo.package_number_exists(package_number, project_id):
            raise ValidationError(
                f"Test package '{package_number}' already exists "
                f"in project {project_id}."
            )

        data = {
            "package_number": package_number.strip().upper(),
            "project_id": project_id,
            "system": system,
            "subsystem": subsystem,
            "test_type": test_type,
            "test_medium": test_medium,
            "design_pressure": design_pressure,
            "test_pressure": test_pressure,
            "line_numbers": line_numbers,
            "p_and_id_refs": p_and_id_refs,
            "planned_test_date": planned_test_date,
            "status": PackageStatus.DRAFT.value,
            "created_by": created_by,
            "created_at": datetime.utcnow(),
            "remarks": remarks,
        }

        pkg_id = self.repo.insert_package(data)
        logger.info("Created test package #%s  (id=%s)", package_number, pkg_id)
        return pkg_id

    def get_package(self, package_id: int) -> Dict[str, Any]:
        """Return full package dict or raise NotFoundError."""
        pkg = self.repo.get_package_by_id(package_id)
        if not pkg:
            raise NotFoundError(f"Test package id={package_id} not found.")
        return pkg

    def get_package_by_number(
        self, package_number: str, project_id: int
    ) -> Dict[str, Any]:
        pkg = self.repo.get_package_by_number(
            package_number.strip().upper(), project_id
        )
        if not pkg:
            raise NotFoundError(
                f"Test package '{package_number}' not found "
                f"in project {project_id}."
            )
        return pkg

    def list_packages(
        self,
        project_id: int,
        *,
        status: Optional[str] = None,
        system: Optional[str] = None,
        search: str = "",
        limit: int = 200,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return filtered list of packages for a project."""
        return self.repo.list_packages(
            project_id,
            status=status,
            system=system,
            search=search.strip(),
            limit=limit,
            offset=offset,
        )

    def update_package(
        self, package_id: int, updates: Dict[str, Any]
    ) -> bool:
        """Apply partial updates to a package.

        Status changes must go through ``transition_status``.
        """
        pkg = self.get_package(package_id)

        if "status" in updates:
            raise ValidationError(
                "Use transition_status() to change package status."
            )

        if "test_pressure" in updates or "design_pressure" in updates:
            dp = updates.get("design_pressure", pkg.get("design_pressure", 0))
            tp = updates.get("test_pressure", pkg.get("test_pressure", 0))
            self._validate_pressures(dp, tp)

        if "package_number" in updates:
            self._validate_package_number(updates["package_number"])

        updates["updated_at"] = datetime.utcnow()
        ok = self.repo.update_package(package_id, updates)
        if ok:
            logger.info("Updated test package id=%s", package_id)
        return ok

    def delete_package(self, package_id: int) -> bool:
        """Soft-delete (cancel) a package if it is still in DRAFT."""
        pkg = self.get_package(package_id)
        if pkg.get("status") != PackageStatus.DRAFT.value:
            raise StateTransitionError(
                "Only DRAFT packages can be deleted. "
                "Use transition_status() to CANCEL."
            )
        ok = self.repo.delete_package(package_id)
        if ok:
            logger.info("Deleted test package id=%s", package_id)
        return ok

    # ── Status Workflow ─────────────────────

    def transition_status(
        self,
        package_id: int,
        new_status: str,
        *,
        user: str = "",
        remarks: str = "",
    ) -> bool:
        """Move a package to a new status with validation.

        Raises ``StateTransitionError`` on illegal transitions.
        """
        pkg = self.get_package(package_id)
        current = PackageStatus(pkg["status"])
        target = PackageStatus(new_status)

        if target not in _ALLOWED_TRANSITIONS.get(current, []):
            raise StateTransitionError(
                f"Cannot move from {current.value} → {target.value}."
            )

        # Pre-transition guards
        if target == PackageStatus.READY:
            self._assert_readiness(package_id, pkg)
        elif target == PackageStatus.TESTING:
            self._assert_checklist_complete(package_id)
        elif target == PackageStatus.PASSED:
            self._assert_test_result_exists(package_id)

        ok = self.repo.update_package(package_id, {
            "status": target.value,
            "status_changed_by": user,
            "status_changed_at": datetime.utcnow(),
            "status_remarks": remarks,
            "updated_at": datetime.utcnow(),
        })

        if ok:
            logger.info(
                "Package #%s  %s → %s  (by %s)",
                pkg.get("package_number"), current.value, target.value, user,
            )
        return ok

    # ── Items (Welds / Spools / Valves) ─────

    def add_item(self, package_id: int, item: TestPackageItem) -> int:
        """Associate a weld, spool, valve, etc. with the package."""
        self.get_package(package_id)  # existence check
        item.package_id = package_id
        self._validate_item(item)

        if self.repo.item_exists_in_package(
            package_id, item.item_type, item.item_number
        ):
            raise ValidationError(
                f"{item.item_type} '{item.item_number}' is already "
                f"in package {package_id}."
            )

        item_id = self.repo.insert_item(item.__dict__)
        logger.debug(
            "Added %s '%s' to package %s",
            item.item_type, item.item_number, package_id,
        )
        return item_id

    def remove_item(self, package_id: int, item_id: int) -> bool:
        self.get_package(package_id)
        return self.repo.delete_item(item_id, package_id)

    def list_items(
        self, package_id: int, *, item_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        self.get_package(package_id)
        return self.repo.list_items(package_id, item_type=item_type)

    def bulk_add_welds(
        self, package_id: int, weld_numbers: List[str], line_number: str = ""
    ) -> Tuple[int, int]:
        """Add multiple welds at once.

        Returns (added_count, skipped_count).
        """
        added = skipped = 0
        for wn in weld_numbers:
            wn = wn.strip()
            if not wn:
                continue
            try:
                self.add_item(package_id, TestPackageItem(
                    item_type="weld",
                    item_number=wn,
                    line_number=line_number,
                ))
                added += 1
            except ValidationError:
                skipped += 1
        logger.info(
            "Bulk-add to package %s: %d added, %d skipped",
            package_id, added, skipped,
        )
        return added, skipped

    # ── Checklist ───────────────────────────

    def add_checklist_item(
        self, package_id: int, check_item: str
    ) -> int:
        self.get_package(package_id)
        entry = TestPackageChecklist(
            package_id=package_id, check_item=check_item
        )
        return self.repo.insert_checklist_item(entry.__dict__)

    def verify_checklist_item(
        self,
        checklist_id: int,
        *,
        verified_by: str,
        remarks: str = "",
    ) -> bool:
        return self.repo.update_checklist_item(checklist_id, {
            "is_verified": True,
            "verified_by": verified_by,
            "verified_date": datetime.utcnow(),
            "remarks": remarks,
        })

    def get_checklist(
        self, package_id: int
    ) -> List[Dict[str, Any]]:
        self.get_package(package_id)
        return self.repo.list_checklist(package_id)

    def is_checklist_complete(self, package_id: int) -> bool:
        items = self.get_checklist(package_id)
        if not items:
            return False
        return all(it.get("is_verified") for it in items)

    # ── Test Results ────────────────────────

    def record_test_result(
        self, package_id: int, result: TestResult
    ) -> int:
        """Persist a hydro / pneumatic test result."""
        self.get_package(package_id)
        result.package_id = package_id
        self._validate_test_result(result)
        result_id = self.repo.insert_test_result(result.__dict__)
        logger.info(
            "Recorded %s test result for package %s → %s",
            result.test_type, package_id, result.result_status,
        )
        return result_id

    def get_test_results(
        self, package_id: int
    ) -> List[Dict[str, Any]]:
        self.get_package(package_id)
        return self.repo.list_test_results(package_id)

    def get_latest_result(
        self, package_id: int
    ) -> Optional[Dict[str, Any]]:
        results = self.get_test_results(package_id)
        return results[-1] if results else None

    # ── Readiness & Intelligence ────────────

    def check_readiness(
        self, package_id: int
    ) -> Dict[str, Any]:
        """
        Comprehensive readiness report.

        Returns a dict with keys:
            is_ready        : bool
            total_welds     : int
            ndt_complete    : int
            ndt_pending     : int
            ndt_acceptance  : float (%)
            checklist_done  : bool
            checklist_total : int
            checklist_ok    : int
            warnings        : list[str]
        """
        pkg = self.get_package(package_id)
        items = self.list_items(package_id, item_type="weld")
        checklist = self.get_checklist(package_id)

        total_welds = len(items)
        ndt_complete = 0
        ndt_pending = 0
        warnings: List[str] = []

        for w in items:
            ndt_status = self._get_weld_ndt_status(w["item_number"])
            if ndt_status == "complete":
                ndt_complete += 1
            elif ndt_status == "pending":
                ndt_pending += 1
            elif ndt_status == "failed":
                warnings.append(
                    f"Weld {w['item_number']} has NDT failure."
                )

        checklist_total = len(checklist)
        checklist_ok = sum(
            1 for c in checklist if c.get("is_verified")
        )
        checklist_done = checklist_total > 0 and checklist_ok == checklist_total

        ndt_acceptance = (
            (ndt_complete / total_welds * 100) if total_welds else 0.0
        )

        is_ready = (
            total_welds > 0
            and ndt_pending == 0
            and ndt_complete == total_welds
            and checklist_done
            and not any("failure" in w.lower() for w in warnings)
        )

        return {
            "is_ready": is_ready,
            "total_welds": total_welds,
            "ndt_complete": ndt_complete,
            "ndt_pending": ndt_pending,
            "ndt_acceptance": round(ndt_acceptance, 1),
            "checklist_done": checklist_done,
            "checklist_total": checklist_total,
            "checklist_ok": checklist_ok,
            "warnings": warnings,
        }

    def get_package_summaries(
        self, project_id: int
    ) -> List[TestPackageSummary]:
        """Lightweight summaries for dashboard cards."""
        rows = self.repo.list_packages(project_id, limit=9999)
        summaries: List[TestPackageSummary] = []
        for r in rows:
            items = self.repo.list_items(r["id"])
            total = len(items)
            done = sum(
                1 for it in items
                if self._get_weld_ndt_status(it.get("item_number", "")) == "complete"
            )
            pct = (done / total * 100) if total else 0.0
            summaries.append(TestPackageSummary(
                package_id=r["id"],
                package_number=r["package_number"],
                system=r.get("system", ""),
                test_type=r.get("test_type", ""),
                status=r.get("status", ""),
                total_items=total,
                completion_pct=round(pct, 1),
                planned_date=r.get("planned_test_date"),
                actual_date=r.get("actual_test_date"),
            ))
        return summaries

    # ── Reporting ───────────────────────────

    def generate_test_certificate_data(
        self, package_id: int
    ) -> Dict[str, Any]:
        """
        Assemble all data needed to render a Hydro-Test Certificate
        (e.g. for PDF / HTML export).
        """
        pkg = self.get_package(package_id)
        items = self.list_items(package_id)
        results = self.get_test_results(package_id)
        checklist = self.get_checklist(package_id)
        latest = results[-1] if results else {}

        return {
            "package": pkg,
            "items": items,
            "test_result": latest,
            "checklist": checklist,
            "generated_at": datetime.utcnow().isoformat(),
            "total_items": len(items),
            "boundary_count": sum(
                1 for it in items if it.get("is_boundary")
            ),
        }

    # ── Statistics ──────────────────────────

    def get_project_statistics(
        self, project_id: int
    ) -> Dict[str, Any]:
        """Aggregate stats across all packages in a project."""
        packages = self.repo.list_packages(project_id, limit=9999)
        total = len(packages)
        by_status: Dict[str, int] = {}
        for p in packages:
            s = p.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1

        passed = by_status.get(PackageStatus.PASSED.value, 0)
        completion = (passed / total * 100) if total else 0.0

        return {
            "total_packages": total,
            "by_status": by_status,
            "passed": passed,
            "completion_pct": round(completion, 1),
        }

    # ── Internal Helpers ────────────────────

    @staticmethod
    def _validate_package_number(number: str) -> None:
        n = number.strip()
        if not n:
            raise ValidationError("Package number cannot be empty.")
        if len(n) > 50:
            raise ValidationError(
                "Package number must be ≤ 50 characters."
            )

    @staticmethod
    def _validate_pressures(
        design: float, test: float
    ) -> None:
        if design < 0 or test < 0:
            raise ValidationError("Pressures must be ≥ 0.")
        if test > 0 and design > 0 and test < design:
            raise ValidationError(
                f"Test pressure ({test}) cannot be lower than "
                f"design pressure ({design})."
            )

    @staticmethod
    def _validate_item(item: TestPackageItem) -> None:
        if not item.item_type:
            raise ValidationError("Item type is required.")
        if not item.item_number.strip():
            raise ValidationError("Item number is required.")

    @staticmethod
    def _validate_test_result(result: TestResult) -> None:
        if result.test_pressure <= 0:
            raise ValidationError("Test pressure must be > 0.")
        if result.holding_time_minutes <= 0:
            raise ValidationError("Holding time must be > 0 minutes.")

    def _assert_readiness(
        self, package_id: int, pkg: Dict[str, Any]
    ) -> None:
        readiness = self.check_readiness(package_id)
        if not readiness["is_ready"]:
            reasons = []
            if readiness["total_welds"] == 0:
                reasons.append("No welds assigned.")
            if readiness["ndt_pending"] > 0:
                reasons.append(
                    f"{readiness['ndt_pending']} weld(s) pending NDT."
                )
            if not readiness["checklist_done"]:
                reasons.append("Checklist incomplete.")
            if readiness["warnings"]:
                reasons.extend(readiness["warnings"])
            raise ValidationError(
                "Package not ready: " + " | ".join(reasons)
            )

    def _assert_checklist_complete(self, package_id: int) -> None:
        if not self.is_checklist_complete(package_id):
            raise ValidationError(
                "All checklist items must be verified before testing."
            )

    def _assert_test_result_exists(self, package_id: int) -> None:
        results = self.get_test_results(package_id)
        if not results:
            raise ValidationError(
                "At least one test result must be recorded."
            )

    def _get_weld_ndt_status(self, weld_number: str) -> str:
        """Query NDT repository for weld acceptance status.

        Returns 'complete' | 'pending' | 'failed' | 'unknown'.
        """
        if not self.ndt_repo or not weld_number:
            return "unknown"
        try:
            return self.ndt_repo.get_weld_ndt_status(weld_number)
        except Exception:
            return "unknown"