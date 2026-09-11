# PipeAgent 5.2.9 — Second industry column pass

## Why this revision

After 5.2.5/5.2.7, several physical columns still used Access shorthand (`qty`, `doc_*`, `linecheck_*`, `ndt_percent_*`, string `welder_id`, `action_by_*`) instead of ISO/ASME/EPC field names.

## Changes

- Welds: `base_material`, `welder_stencil_number`, `pwht_completed`, `ndt_extent_*_pct`, `left_quantity` / `right_quantity`, `is_on_hold`.
- Line list NDT extent and `size_dn`; documents `document_*`; MTO `*_quantity`; actions `performed_by_*`.
- Test packages: `line_check_*`, `inch_metre`, `dia_inch`; NDT `inspector_stamp`; company `logo_file_path`.
- Supports: `base_material`, `support_subtype`, `location_description`; work fronts `target_quantity` / `actual_quantity`; punches `location_description`.
- Existing Python names stay as SQLAlchemy synonyms. Existing SQLite files are renamed on startup before `create_all`.

See `docs/DATA_MODEL_CONVENTION.md` and `docs/SITE_REGISTERS.md`.

## Validation

- `python3 -m pytest` is the release gate for this revision.
