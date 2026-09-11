# PipeAgent 5.0.0 — Production Release Checklist

## Verified in build environment

- [x] Python compile check (`python -m compileall -q .`)
- [x] Automated tests: **26 passed**
- [x] FastAPI `/health` smoke test: **200 OK**
- [x] SQLite database initialization
- [x] Enterprise execution graph persistence
- [x] Field sync idempotency
- [x] Welding telemetry idempotency
- [x] Predictive history persistence
- [x] Commercial plan mapping
- [x] Value report is read-only and does not create prediction history
- [x] HTML Executive Value Report generation
- [x] English/international product positioning
- [x] Commercial tier model embedded in application

## Environment-dependent verification before customer go-live

- [ ] Install `requirements.txt` on target Windows workstation.
- [ ] Launch `python app.py` and complete a real PyQt6 UI smoke test.
- [ ] Verify printer / browser print-to-PDF for Welding and Fit-up HTML reports.
- [ ] Configure PostgreSQL or SQL Server Express and run a backup/restore rehearsal.
- [ ] Configure TLS and reverse proxy for Enterprise API.
- [ ] Configure OIDC/SSO with the customer's identity provider.
- [ ] Configure real ERP/DMS/scheduling/BIM endpoints.
- [ ] Test QR scanners and field devices.
- [ ] Test offline → online synchronization on real devices.
- [ ] Validate welding telemetry adapter against the actual machine/protocol.
- [ ] Run UAT with sanitized real project data.
- [ ] Replace demo/default administrator credentials and verify password policy.
- [ ] Configure a real commercial portal URL through `PIPEAGENT_LICENSE_PURCHASE_URL`.

## Commercial guardrails

- Do not present indicative ROI as guaranteed savings.
- Do not price per weld.
- Keep engineering/QC approvals under responsible human authority.
- Keep customer-specific pricing and contract terms outside construction business logic.
