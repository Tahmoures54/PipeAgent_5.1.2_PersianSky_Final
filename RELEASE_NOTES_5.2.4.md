# PipeAgent 5.2.4 — Reliability, API and Security Hardening

## Why this revision

The 5.2.x codebase already had a full execution-OS surface, but several production paths were out of sync with each other: the database manager, pytest fixtures, FastAPI health check, API-key storage and OIDC entrypoint used different attribute names and contracts. This revision aligns those layers without changing the piping execution workflows.

## Fixes

- Database manager now uses a single initialization flag (`_initialized` / `_is_initialized`), SQLite `StaticPool` for in-memory databases, `check_same_thread=False` for the Qt desktop, `pool_pre_ping` for PostgreSQL, and a real `test_connection()` used by `/health`.
- Existing SQLite files receive additive schema patches for `projects.status`, `projects.project_type`, `users.email` and `users.auth_provider`.
- Repositories commit when they own a `DatabaseManager`, so `ProjectRepository.create()` and related tests persist rows.
- API keys are hashed at rest. Legacy plaintext rows are verified once and rewritten.
- API authentication no longer treats a JWT `role=admin` claim as a bypass. OIDC is used only when an issuer is configured and a local user exists.
- IFC inventory refuses paths outside `PIPEAGENT_BIM_ROOT`.
- Login lockout, password rehash-on-login, and persisted password changes are implemented in `AuthService`.
- Default admin seeding: PostgreSQL requires `PIPEAGENT_BOOTSTRAP_ADMIN_PASSWORD`; local SQLite may still create `admin`/`admin` with a warning.
- Runtime artefacts (`*.db`, logs, caches, exports) are gitignored. pytest and httpx are declared in `requirements.txt`.

## Validation

- `python -m pytest` is the release gate for this revision.
