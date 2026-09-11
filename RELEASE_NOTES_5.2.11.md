# PipeAgent 5.2.11 — Shared database connection

## Why this revision

SQLite is a single-workstation file. A piping site with several concurrent users needs a shared server. PipeAgent already had PostgreSQL via `PIPEAGENT_DATABASE_URL`; this revision adds SQL Server / Express and a desktop connection dialog.

## Changes

- **File → Database Connection…** — SQLite, SQL Server / Express, or PostgreSQL. Test, then save a workstation profile (`pipeagent.connection.json`).
- If startup cannot open the database, the same dialog is offered once.
- `PIPEAGENT_DATABASE_URL` still overrides the profile (IT lock-in).
- Status bar shows the engine (SQLite / SQL Server / PostgreSQL) without the password.
- Local file backup stays SQLite-only; server databases are backed up with DBA tools.
- See `docs/DATABASE.md`.

## Validation

- `python3 -m pytest` is the release gate for this revision.
