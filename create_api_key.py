import argparse
from db.manager import DatabaseManager
from services.api_security import ApiSecurity

p=argparse.ArgumentParser(description='Create a PipeAgent enterprise API credential')
p.add_argument('--name',required=True); p.add_argument('--scope',action='append',required=True); p.add_argument('--project-id',type=int); p.add_argument('--expires-days',type=int)
a=p.parse_args(); db=DatabaseManager();
if not db.initialize(): raise SystemExit('Database initialization failed')
print(ApiSecurity(db).issue_key(a.name,a.scope,a.project_id,a.expires_days))
