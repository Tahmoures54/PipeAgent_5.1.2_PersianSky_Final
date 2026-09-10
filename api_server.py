from __future__ import annotations
import json
from typing import Any
from fastapi import FastAPI, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from db.manager import DatabaseManager
from db.models import Project, ExecutionGraphNode, ExecutionGraphEdge, PredictionRun
from services.api_security import ApiSecurity
from services.field_sync_service import FieldSyncService
from services.telemetry_service import WeldingTelemetryService
from services.predictive_control import PredictiveConstructionControl
from services.enterprise_integration import IFCAdapter
from services.connector_catalog import ConnectorCatalog
from services.sso_service import OIDCService
from services.rbac import RBACService
from services.product_commercial import plan_catalog, ValueEngine
from config import APP_NAME, APP_VERSION, BRAND_TAGLINE, PRODUCT_POSITIONING, LICENSE_PURCHASE_URL

DB=DatabaseManager()
app=FastAPI(title=f'{APP_NAME} Enterprise API',version=APP_VERSION,description='Piping Execution Operating System API')

class SyncPayload(BaseModel):
    project_id:int; device_id:str; batch_uuid:str; events:list[dict[str,Any]]
class TelemetryPayload(BaseModel):
    project_id:int; payload:dict[str,Any]
class TokenRequest(BaseModel):
    name:str; scopes:list[str]=Field(default_factory=lambda:['projects:read','execution:read']); project_id:int|None=None; expires_days:int|None=None

def db():
    if not DB._is_initialized and not DB.initialize(): raise HTTPException(500,'Database initialization failed')
    return DB

def auth(scope:str, project_id:int|None=None, authorization:str|None=None, x_api_key:str|None=None, database=None):
    sec=ApiSecurity(database); token=x_api_key
    if token and sec.verify(token,scope,project_id): return {'auth':'api-key'}
    if authorization and authorization.lower().startswith('bearer '):
        bearer=authorization.split(' ',1)[1]
        try:
            claims=OIDCService().verify(bearer)
            role=str(claims.get('pipeagent_role') or claims.get('role') or 'viewer')
            subject=str(claims.get('preferred_username') or claims.get('email') or claims.get('sub') or '')
            with database.session_scope() as s:
                user=s.query(__import__('db.models',fromlist=['User']).User).filter_by(username=subject).first()
            if user and RBACService(database).allowed(user,scope,project_id): return {'auth':'oidc','user':subject}
            if role=='admin': return {'auth':'oidc','user':subject,'role':role}
        except Exception:
            pass
    raise HTTPException(401,'Valid PipeAgent API credential or configured OIDC identity required')

@app.get('/health')
def health(database=Depends(db)): return {'status':'ok','application':APP_NAME,'version':APP_VERSION,'database':database.test_connection()}


@app.get('/api/v1/commercial/catalog')
def commercial_catalog(database=Depends(db),authorization: str|None=Header(None),x_api_key:str|None=Header(None)):
    auth('projects:read',authorization=authorization,x_api_key=x_api_key,database=database)
    return {'product': PRODUCT_POSITIONING, 'tagline': BRAND_TAGLINE, 'plans': plan_catalog(), 'purchase_url': LICENSE_PURCHASE_URL}

@app.get('/api/v1/projects/{project_id}/value')
def project_value(project_id:int,database=Depends(db),authorization: str|None=Header(None),x_api_key:str|None=Header(None)):
    auth('reports:read',project_id,authorization,x_api_key,database)
    return ValueEngine(database).calculate(project_id)

@app.get('/api/v1/projects')
def projects(database=Depends(db),authorization: str|None=Header(None),x_api_key:str|None=Header(None)):
    auth('projects:read',authorization=authorization,x_api_key=x_api_key,database=database)
    with database.session_scope() as s: return [{'id':p.id,'code':p.project_code,'title':p.title,'client':p.client,'contractor':p.contractor} for p in s.query(Project).order_by(Project.project_code).all()]

@app.get('/api/v1/projects/{project_id}/execution-graph')
def graph(project_id:int,database=Depends(db),authorization: str|None=Header(None),x_api_key:str|None=Header(None)):
    auth('execution:read',project_id,authorization,x_api_key,database)
    with database.session_scope() as s:
        nodes=s.query(ExecutionGraphNode).filter_by(project_id=project_id).all(); edges=s.query(ExecutionGraphEdge).filter_by(project_id=project_id).all()
        return {'nodes':[{'key':n.node_key,'type':n.node_type,'label':n.label,'status':n.status,'risk':n.risk_score} for n in nodes], 'edges':[{'from':e.from_key,'to':e.to_key,'relation':e.relation,'weight':e.weight} for e in edges]}

@app.post('/api/v1/sync/batch')
def sync(payload:SyncPayload,database=Depends(db),authorization: str|None=Header(None),x_api_key:str|None=Header(None)):
    auth('field:sync',payload.project_id,authorization,x_api_key,database)
    return FieldSyncService(database).ingest_batch(payload.project_id,payload.device_id,payload.batch_uuid,payload.events)

@app.post('/api/v1/telemetry/welding')
def telemetry(payload:TelemetryPayload,database=Depends(db),authorization: str|None=Header(None),x_api_key:str|None=Header(None)):
    auth('telemetry:write',payload.project_id,authorization,x_api_key,database)
    return {'telemetry_id':WeldingTelemetryService(database).ingest(payload.project_id,payload.payload)}

@app.post('/api/v1/projects/{project_id}/predict')
def predict(project_id:int,horizon_hours:int=Query(72,ge=1,le=720),database=Depends(db),authorization: str|None=Header(None),x_api_key:str|None=Header(None)):
    auth('execution:write',project_id,authorization,x_api_key,database)
    return PredictiveConstructionControl(database).run(project_id,horizon_hours)

@app.get('/api/v1/projects/{project_id}/predictions/latest')
def latest(project_id:int,database=Depends(db),authorization: str|None=Header(None),x_api_key:str|None=Header(None)):
    auth('execution:read',project_id,authorization,x_api_key,database)
    with database.session_scope() as s:
        p=s.query(PredictionRun).filter_by(project_id=project_id).order_by(PredictionRun.generated_at.desc()).first()
        return json.loads(p.result_json) if p else {'status':'No prediction run yet'}

@app.get('/api/v1/integrations/catalog')
def integration_catalog(database=Depends(db),authorization: str|None=Header(None),x_api_key:str|None=Header(None)):
    auth('projects:read',authorization=authorization,x_api_key=x_api_key,database=database)
    return ConnectorCatalog.describe()

@app.post('/api/v1/bim/ifc/inventory')
def ifc_inventory(path: str, database=Depends(db),authorization: str|None=Header(None),x_api_key:str|None=Header(None)):
    auth('execution:read',authorization=authorization,x_api_key=x_api_key,database=database)
    return IFCAdapter().inventory(path)

def create_app():
    if not DB._is_initialized: DB.initialize()
    return app
