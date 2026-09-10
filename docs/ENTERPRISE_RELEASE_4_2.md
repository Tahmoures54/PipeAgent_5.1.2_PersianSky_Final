# PipeAgent 4.2 Enterprise Release

PipeAgent 4.2 is the enterprise hardening layer for the Piping Execution Operating System.

## Industrial-grade execution data

- QR payloads for Line / ISO / Spool / Weld / Work Front identities.
- Offline field event queue with device identity.
- Server-side batch synchronization with idempotent event UUIDs and receipts.
- SHA-256 document evidence registration.
- Welding telemetry ingestion with machine identity, current, voltage, wire-feed speed, travel speed, heat input and deviation screening.

## Predictive Construction Control

- Persistent prediction observations.
- Historical trend calculation over a rolling 30-day window.
- Probability and confidence separated from one another.
- Data-quality score for every prediction run.
- Prediction runs and impact records persisted in the database.
- Execution graph remains the dependency context.
- Recommendations are advisory; they never auto-approve QC or silently change the schedule.

## Enterprise integration

- SQLite remains the zero-setup default.
- PostgreSQL is supported through `PIPEAGENT_DATABASE_URL` and SQLAlchemy.
- REST API via FastAPI.
- API credentials are hashed at rest and scope/project limited.
- OIDC/JWT verification adapter for enterprise SSO.
- ERP, scheduling, DMS and BIM connector contracts.
- HTTP integration job queue with idempotency.
- IFC/STEP inventory adapter for BIM model exchange.
- External-system mapping table for stable cross-system IDs.
- Multi-project data model with project membership and project-scoped credentials.

## API

Start the API:

```bash
python run_api.py
```

Create a scoped credential:

```bash
python create_api_key.py --name field-device-01 --scope field:sync --scope telemetry:write --project-id 1
```

Use the returned token as `X-API-Key`.

## Production recommendations

1. Use PostgreSQL for multi-user deployments.
2. Put the API behind TLS and an enterprise reverse proxy.
3. Use OIDC/SSO and short-lived gateway credentials where available.
4. Store document evidence on managed object storage rather than a local workstation.
5. Run scheduled prediction jobs and retain PredictionRun history.
6. Configure ERP, DMS, scheduling and BIM endpoints with explicit ownership and retry policies.
7. Back up the database and evidence store together.
