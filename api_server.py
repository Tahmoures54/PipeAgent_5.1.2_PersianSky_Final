from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import (
    APP_NAME,
    APP_VERSION,
    BIM_IMPORT_ROOT,
    BRAND_TAGLINE,
    LICENSE_PURCHASE_URL,
    OIDC_ISSUER_URL,
    PRODUCT_POSITIONING,
)
from core.exceptions import PipeAgentError, to_http_response
from db.manager import DatabaseManager
from db.models import Project, ExecutionGraphNode, ExecutionGraphEdge, PredictionRun, User
from services.api_security import ApiSecurity
from services.connector_catalog import ConnectorCatalog
from services.enterprise_integration import IFCAdapter
from services.field_sync_service import FieldSyncService
from services.predictive_control import PredictiveConstructionControl
from services.product_commercial import plan_catalog, ValueEngine
from services.rbac import RBACService
from services.sso_service import OIDCService
from services.telemetry_service import WeldingTelemetryService

ALLOWED_IFC_SUFFIXES = {".ifc", ".ifczip"}


class SyncPayload(BaseModel):
    project_id: int
    device_id: str
    batch_uuid: str
    events: list[dict[str, Any]]


class TelemetryPayload(BaseModel):
    project_id: int
    payload: dict[str, Any]


class TokenRequest(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=lambda: ["projects:read", "execution:read"])
    project_id: int | None = None
    expires_days: int | None = None


def _get_db(request: Request) -> DatabaseManager:
    database: DatabaseManager = request.app.state.db
    if not database._initialized and not database.initialize():
        raise HTTPException(status_code=500, detail="Database initialization failed")
    return database


def _authorize(
    scope: str,
    *,
    project_id: int | None = None,
    authorization: str | None = None,
    x_api_key: str | None = None,
    database: DatabaseManager,
    client_ip: str | None = None,
) -> dict[str, Any]:
    sec = ApiSecurity(database)
    token = x_api_key
    if token:
        info = sec.verify(token, scope, project_id, client_ip=client_ip)
        if info:
            return {"auth": "api-key", "key_id": info.id, "name": info.name}

    if authorization and authorization.lower().startswith("bearer "):
        if not OIDC_ISSUER_URL:
            raise HTTPException(
                status_code=401,
                detail="OIDC is not configured on this PipeAgent instance",
            )
        bearer = authorization.split(" ", 1)[1]
        try:
            claims = OIDCService().verify(bearer)
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid OIDC token") from exc

        subject = str(
            claims.get("preferred_username")
            or claims.get("email")
            or claims.get("sub")
            or ""
        )
        if not subject:
            raise HTTPException(status_code=401, detail="OIDC token is missing a subject")

        with database.session_scope() as session:
            user = (
                session.query(User)
                .filter(User.username == subject)
                .first()
            )
            if user is None and claims.get("email"):
                user = session.query(User).filter(User.email == claims.get("email")).first()
            if user is None:
                raise HTTPException(status_code=403, detail="OIDC identity is not provisioned")
            if not RBACService(database).allowed(user, scope, project_id):
                raise HTTPException(status_code=403, detail="Insufficient permission")
            return {"auth": "oidc", "user": subject}

    raise HTTPException(
        status_code=401,
        detail="Valid PipeAgent API credential or configured OIDC identity required",
    )


def _safe_ifc_path(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    try:
        resolved = candidate.resolve(strict=False)
        root = BIM_IMPORT_ROOT.expanduser().resolve(strict=False)
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Invalid IFC path") from exc

    try:
        resolved.relative_to(root)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="IFC path must be under the configured BIM import directory",
        )

    if resolved.suffix.lower() not in ALLOWED_IFC_SUFFIXES:
        raise HTTPException(status_code=400, detail="Only .ifc / .ifczip files are accepted")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="IFC file not found")
    return resolved


def create_app(database: Optional[DatabaseManager] = None) -> FastAPI:
    application = FastAPI(
        title=f"{APP_NAME} Enterprise API",
        version=APP_VERSION,
        description="Piping Execution Operating System API",
    )
    db = database or DatabaseManager()
    if not db._initialized:
        db.initialize()
    application.state.db = db

    @application.exception_handler(PipeAgentError)
    async def _pipeagent_error_handler(request: Request, exc: PipeAgentError):
        payload = to_http_response(exc)
        return JSONResponse(status_code=int(payload.get("http_status") or 500), content=payload)

    @application.exception_handler(HTTPException)
    async def _http_error_handler(request: Request, exc: HTTPException):
        return await http_exception_handler(request, exc)

    @application.get("/health")
    def health(database: DatabaseManager = Depends(_get_db)):
        connected = database.test_connection()
        return {
            "status": "ok" if connected else "degraded",
            "application": APP_NAME,
            "version": APP_VERSION,
            "database": connected,
        }

    @application.get("/api/v1/commercial/catalog")
    def commercial_catalog(
        request: Request,
        database: DatabaseManager = Depends(_get_db),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ):
        _authorize(
            "projects:read",
            authorization=authorization,
            x_api_key=x_api_key,
            database=database,
            client_ip=request.client.host if request.client else None,
        )
        return {
            "product": PRODUCT_POSITIONING,
            "tagline": BRAND_TAGLINE,
            "plans": plan_catalog(),
            "purchase_url": LICENSE_PURCHASE_URL,
        }

    @application.get("/api/v1/projects/{project_id}/value")
    def project_value(
        project_id: int,
        request: Request,
        database: DatabaseManager = Depends(_get_db),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ):
        _authorize(
            "reports:read",
            project_id=project_id,
            authorization=authorization,
            x_api_key=x_api_key,
            database=database,
            client_ip=request.client.host if request.client else None,
        )
        return ValueEngine(database).calculate(project_id)

    @application.get("/api/v1/projects")
    def projects(
        request: Request,
        database: DatabaseManager = Depends(_get_db),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ):
        _authorize(
            "projects:read",
            authorization=authorization,
            x_api_key=x_api_key,
            database=database,
            client_ip=request.client.host if request.client else None,
        )
        with database.session_scope() as session:
            return [
                {
                    "id": project.id,
                    "code": project.project_code,
                    "title": project.title,
                    "client": project.client,
                    "contractor": project.contractor,
                    "status": getattr(project, "status", None),
                }
                for project in session.query(Project).order_by(Project.project_code).all()
            ]

    @application.get("/api/v1/projects/{project_id}/execution-graph")
    def graph(
        project_id: int,
        request: Request,
        database: DatabaseManager = Depends(_get_db),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ):
        _authorize(
            "execution:read",
            project_id=project_id,
            authorization=authorization,
            x_api_key=x_api_key,
            database=database,
            client_ip=request.client.host if request.client else None,
        )
        with database.session_scope() as session:
            nodes = session.query(ExecutionGraphNode).filter_by(project_id=project_id).all()
            edges = session.query(ExecutionGraphEdge).filter_by(project_id=project_id).all()
            return {
                "nodes": [
                    {
                        "key": node.node_key,
                        "type": node.node_type,
                        "label": node.label,
                        "status": node.status,
                        "risk": node.risk_score,
                    }
                    for node in nodes
                ],
                "edges": [
                    {
                        "from": edge.from_key,
                        "to": edge.to_key,
                        "relation": edge.relation,
                        "weight": edge.weight,
                    }
                    for edge in edges
                ],
            }

    @application.post("/api/v1/sync/batch")
    def sync(
        payload: SyncPayload,
        request: Request,
        database: DatabaseManager = Depends(_get_db),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ):
        _authorize(
            "field:sync",
            project_id=payload.project_id,
            authorization=authorization,
            x_api_key=x_api_key,
            database=database,
            client_ip=request.client.host if request.client else None,
        )
        return FieldSyncService(database).ingest_batch(
            payload.project_id,
            payload.device_id,
            payload.batch_uuid,
            payload.events,
        )

    @application.post("/api/v1/telemetry/welding")
    def telemetry(
        payload: TelemetryPayload,
        request: Request,
        database: DatabaseManager = Depends(_get_db),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ):
        _authorize(
            "telemetry:write",
            project_id=payload.project_id,
            authorization=authorization,
            x_api_key=x_api_key,
            database=database,
            client_ip=request.client.host if request.client else None,
        )
        return {
            "telemetry_id": WeldingTelemetryService(database).ingest(
                payload.project_id,
                payload.payload,
            )
        }

    @application.post("/api/v1/projects/{project_id}/predict")
    def predict(
        project_id: int,
        request: Request,
        horizon_hours: int = Query(72, ge=1, le=720),
        database: DatabaseManager = Depends(_get_db),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ):
        _authorize(
            "execution:write",
            project_id=project_id,
            authorization=authorization,
            x_api_key=x_api_key,
            database=database,
            client_ip=request.client.host if request.client else None,
        )
        return PredictiveConstructionControl(database).run(project_id, horizon_hours)

    @application.get("/api/v1/projects/{project_id}/predictions/latest")
    def latest(
        project_id: int,
        request: Request,
        database: DatabaseManager = Depends(_get_db),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ):
        _authorize(
            "execution:read",
            project_id=project_id,
            authorization=authorization,
            x_api_key=x_api_key,
            database=database,
            client_ip=request.client.host if request.client else None,
        )
        with database.session_scope() as session:
            prediction = (
                session.query(PredictionRun)
                .filter_by(project_id=project_id)
                .order_by(PredictionRun.generated_at.desc())
                .first()
            )
            return json.loads(prediction.result_json) if prediction else {"status": "No prediction run yet"}

    @application.get("/api/v1/integrations/catalog")
    def integration_catalog(
        request: Request,
        database: DatabaseManager = Depends(_get_db),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ):
        _authorize(
            "projects:read",
            authorization=authorization,
            x_api_key=x_api_key,
            database=database,
            client_ip=request.client.host if request.client else None,
        )
        return ConnectorCatalog.describe()

    @application.post("/api/v1/bim/ifc/inventory")
    def ifc_inventory(
        path: str,
        request: Request,
        database: DatabaseManager = Depends(_get_db),
        authorization: str | None = Header(None),
        x_api_key: str | None = Header(None),
    ):
        _authorize(
            "execution:read",
            authorization=authorization,
            x_api_key=x_api_key,
            database=database,
            client_ip=request.client.host if request.client else None,
        )
        return IFCAdapter().inventory(str(_safe_ifc_path(path)))

    return application


app = create_app()
