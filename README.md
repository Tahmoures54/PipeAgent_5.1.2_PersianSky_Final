# PipeAgent 5.2.12 — Piping Execution Operating System

> **Know What’s Next. Control What Matters.**
>
> Connect the field. Predict the risk. Control the execution.

**PipeAgent** is an English-first industrial Piping Execution Operating System for EPC and construction teams. It connects execution data, quality evidence, Work Fronts, NDT, testing and turnover into a persistent execution graph and an explainable predictive control layer.

This release hardens the database layer, desktop/API authentication, and the enterprise HTTP API so the product can be run and tested reliably on a workstation or in CI.

## Run Desktop

```bash
python -m pip install -r requirements.txt
python app.py
```

## Run Enterprise API

```bash
python run_api.py
```

The default API binds to `127.0.0.1:8765`. Copy `.env.example` to `.env` to override database, OIDC and bootstrap settings.

## Tests

```bash
python -m pytest
```

## Database

SQLite is the default for **one workstation**. Several people on one project need a shared server.

In the app: **File → Database Connection…** (administrators and project managers). Pick:

- **SQL Server / Express** — typical on a Windows site PC (`localhost\SQLEXPRESS`). Install ODBC Driver 17/18 and `pip install pyodbc`.
- **PostgreSQL** — office LAN or an online hosted database. Driver is already in `requirements.txt`.
- **SQLite** — single laptop / demo.

IT can lock the target with an environment variable (this overrides the dialog):

```text
PIPEAGENT_DATABASE_URL=postgresql+psycopg://user:password@host:5432/pipeagent
PIPEAGENT_BOOTSTRAP_ADMIN_PASSWORD=<strong password>
PIPEAGENT_ALLOW_INSECURE_DEFAULTS=false
```

SQL Server Express example:

```text
PIPEAGENT_DATABASE_URL=mssql+pyodbc://sa:change-me@localhost\SQLEXPRESS/PipeAgent?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes
```

Create the empty database on the server first. Shared servers do not create `admin`/`admin`; set `PIPEAGENT_BOOTSTRAP_ADMIN_PASSWORD`. Local file backup is SQLite only — back up SQL Server / PostgreSQL with the DBA tools.

See `docs/DATABASE.md`.

## Security

- Never use default credentials in production. Local SQLite may still bootstrap `admin` / `admin` with a warning; PostgreSQL and SQL Server will not.
- API keys are stored as hashes. The raw token is shown once at issue time.
- Use TLS at the API boundary.
- Use project-scoped API credentials.
- Configure OIDC/SSO for enterprise deployments. Bearer tokens are accepted only when `PIPEAGENT_OIDC_ISSUER_URL` is set, and the identity must exist locally.
- BIM/IFC import paths must stay under `PIPEAGENT_BIM_ROOT` (default: `documents/`).
- Back up database and document evidence together.

## Product Positioning

PipeAgent uses a B2B subscription model: **Platform + Field Operations + Intelligence + Digital Turnover + Enterprise Integrations + Professional Services**. It is intentionally not priced per weld.

Open **Value & Plans** inside the application for the commercial model. See `docs/COMMERCIAL_MODEL.md` and `docs/GO_TO_MARKET.md`.

## Core capabilities

- Piping execution master data: Project, Line, ISO, Spool, Weld, Material and WPS/PQR.
- Fit-up, welding, NDT, repair, PWHT, testing, punch and turnover workflows.
- Printable HTML Welding and Fit-up Draft / Official Reports.
- Management analytics HTML pack by unit, contractor, pipe material, fluid service, pipe class and NPS.
- QR-driven field execution and offline event capture.
- Enterprise field synchronization with idempotent receipts.
- Welding machine telemetry ingestion and deviation screening.
- Persistent Execution Graph and event-driven impact propagation.
- Predictive Construction Control with history, trend, probability, confidence and data-quality scoring.
- Site Execution Control Center for instrumentation, PTW, HSE and commissioning readiness.
- Work Front Autopilot recommendations with human approval guardrails.
- Quality Intelligence and Digital Turnover Autopilot.
- PostgreSQL-ready multi-project architecture.
- RBAC-ready project membership and scoped API credentials.
- OIDC/JWT SSO adapter.

The architecture stays above the OT control boundary. PLC/DCS/SCADA remain the control authority.

## Product principle

> Detect → Explain → Predict → Recommend → Human Decision

PipeAgent is a decision-support system. It does not replace engineering authority, QC acceptance, approved schedules or contractual controls.

Column naming follows EPC weld-map / line-list practice; see `docs/DATA_MODEL_CONVENTION.md`. Site register mapping from execution databases: `docs/SITE_REGISTERS.md`. Shared SQLite / SQL Server / PostgreSQL setup: `docs/DATABASE.md`. Competitive NDE/hydro/continuity engine: `docs/COMPETITIVE_POSITIONING.md`. Release notes: `RELEASE_NOTES_5.2.4.md`, `RELEASE_NOTES_5.2.5.md`, `RELEASE_NOTES_5.2.6.md`, `RELEASE_NOTES_5.2.7.md`, `RELEASE_NOTES_5.2.9.md`, `RELEASE_NOTES_5.2.10.md`, `RELEASE_NOTES_5.2.11.md`, `RELEASE_NOTES_5.2.12.md`.
