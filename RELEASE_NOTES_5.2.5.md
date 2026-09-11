# PipeAgent 5.2.5 — Industry data-model alignment

## Why this revision

Database columns mixed business identifiers with foreign keys (`weld_id` was a string joint number; NDT used `weld_id_fk`) and used shorthand (`_no`, `size`, `test_pressure_bar`) that does not match EPC line-list, weld-map, WPS/PQR and hydro-pack practice.

## Changes

- Canonical names: `id` = PK, `*_id` = integer FK, `*_number` / `*_code` = business id, quantities carry units (`_barg`, `_c`, `_mm`, `_pct`).
- `welds.weld_id` → `weld_number`; child inspection tables use `weld_id` as the integer FK to `welds.id`.
- NPS stored as `size_nps`; test and design pressures as `*_barg`.
- Added B31.3 / ASME IX / NDT / hydro fields that were missing from the line list, weld, welder, WPS/PQR, NDT and test-package tables.
- Existing Python attribute names are kept as SQLAlchemy synonyms. Existing SQLite files are renamed on startup (before `create_all`).

See `docs/DATA_MODEL_CONVENTION.md`.

## Validation

- `python -m pytest` is the release gate for this revision.
