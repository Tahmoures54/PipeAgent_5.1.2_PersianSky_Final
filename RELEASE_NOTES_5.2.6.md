# PipeAgent 5.2.6 — Code-compliance execution engine

## Why this revision

Competitors such as Prometheus Weld-Console, WeldTrace and Welding Manager win piping jobs on three capabilities PipeAgent documented but did not execute against the real schema: B31.3 NDE lot selection, hydrotest package clearance, and ASME IX QW-322 welder continuity.

## Changes

- `CodeComplianceService` computes RT/UT/PT/MT coverage from the line list, selects an auditable NDE lot, applies progressive extras after a reject, and ranks a daily execution brief.
- Hydrotest gate uses `test_package_welds`, Category-A punches, rejected NDE, line-list PWHT and spring-hanger pins — not fictional `Weld.test_package_id` columns.
- NDT recording and penalty tracers persist on the real `ndt_records` columns (`weld_id`, `indication`, `is_penalty`).
- API + NDT tab surface coverage gaps and the B31.3 lot list. Smart hints include the brief.

See `docs/COMPETITIVE_POSITIONING.md`.

## Validation

- `python3 -m pytest` is the release gate for this revision.
