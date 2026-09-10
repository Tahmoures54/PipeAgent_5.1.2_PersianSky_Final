
## PipeAgent 5.2.0 — EPC Site Execution Expansion

PipeAgent now includes a cross-discipline **Site Execution Control Center** covering: 

- Instrumentation tags, calibration, loop checks, functional testing, punch, and turnover readiness
- Permit-to-work and high-risk activity tracking
- HSE/site issue and corrective-action tracking
- Construction equipment availability and utilization
- Commissioning system progress and turnover blockers
- Cross-discipline predictive execution watch

The architecture keeps PipeAgent above the OT control boundary. PLC/DCS/SCADA remain the control authority; PipeAgent is designed to consume controlled execution and telemetry data through approved gateways and enterprise interfaces.

See `docs/EPC_SITE_EXECUTION_ARCHITECTURE.md` for the integration model.

# PipeAgent 5.0.0 — Piping Execution Operating System

> **Know What’s Next. Control What Matters.**
>
> Connect the field. Predict the risk. Control the execution.

**PipeAgent** is an English-first, industrial Piping Execution Operating System for EPC and construction teams.

It connects execution data, quality evidence, Work Fronts, NDT, testing and turnover into a persistent execution graph and an explainable predictive control layer.

## Product Positioning

PipeAgent is an intelligent **Piping Execution Operating System**. It connects field execution, quality, productivity and turnover to detect constraints, predict downstream impact and recommend the next best action.

## Commercial Model

PipeAgent uses a B2B subscription model: **Platform + Field Operations + Intelligence + Digital Turnover + Enterprise Integrations + Professional Services**. It is intentionally not priced per weld.

- **Pilot** — controlled evaluation / small project
- **Professional** — small and mid-size EPC projects
- **Enterprise** — large EPC and multi-project organizations

Open **Value & Plans** inside the application for the commercial model and the evidence-based Executive Value Report.

See `docs/COMMERCIAL_MODEL.md` and `docs/GO_TO_MARKET.md`.

## Core capabilities

- Piping execution master data: Project, Line, ISO, Spool, Weld, Material and WPS/PQR.
- Fit-up, welding, NDT, repair, PWHT, testing, punch and turnover workflows.
- Printable HTML Welding and Fit-up Draft / Official Reports.
- QR-driven field execution and offline event capture.
- Enterprise field synchronization with idempotent receipts.
- Welding machine telemetry ingestion and deviation screening.
- Persistent Execution Graph and event-driven impact propagation.
- Predictive Construction Control with history, trend, probability, confidence and data-quality scoring.
- Work Front Autopilot recommendations with human approval guardrails.
- Quality Intelligence and Digital Turnover Autopilot.
- PostgreSQL-ready multi-project architecture.
- RBAC-ready project membership and scoped API credentials.
- OIDC/JWT SSO adapter.
- ERP, scheduling, DMS and BIM/IFC integration contracts.

## Run Desktop

```bash
python -m pip install -r requirements.txt
python app.py
```

## Run Enterprise API

```bash
python run_api.py
```

The default API is available on `127.0.0.1:8765`.

## Database

SQLite is the default for a single workstation.

For production, set:

```text
PIPEAGENT_DATABASE_URL=postgresql+psycopg://user:password@host:5432/pipeagent
```

and install the PostgreSQL driver appropriate for your environment.

## Security

- Never use default credentials in production.
- Use TLS at the API boundary.
- Use project-scoped API credentials.
- Configure OIDC/SSO for enterprise deployments.
- Back up database and document evidence together.

## Product principle

> Detect → Explain → Predict → Recommend → Human Decision

PipeAgent is a decision-support system. It does not replace engineering authority, QC acceptance, approved schedules or contractual controls.

## Release validation

The release is compile-checked and the automated test suite must pass before packaging.
