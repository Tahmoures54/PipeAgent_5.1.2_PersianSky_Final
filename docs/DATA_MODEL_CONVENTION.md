# PipeAgent data model convention

PipeAgent stores piping execution records the way an EPC site actually works: line list, weld map, WPS/PQR, welder qualification, NDT, hydro packs, punch/NCR, and mechanical completion. Column names follow that language and ISO/ASME field practice (ASME B31.3 line list, ASME IX WPS/PQR and welder continuity, API 570/598 inspection and valve tests, ISO 9606 stencil identification).

## Naming rules

| Pattern | Meaning | Example |
|---|---|---|
| `id` | Surrogate primary key | `welds.id` |
| `*_id` | Integer foreign key to that table’s `id` | `ndt_records.weld_id` → `welds.id` |
| `*_number` / `*_code` | Business identifier shown on drawings and reports | `weld_number`, `wps_number`, `ncr_number`, `mcc_number` |
| `*_barg` / `*_c` / `*_mm` / `*_pct` / `*_inch` | Quantity with unit | `design_pressure_barg`, `preheat_min_c`, `wall_thickness_mm` |
| `size_nps` | Nominal pipe size (ASME B36.10 / B16.5), not a generic `size` | `welds.size_nps`, `line_list.size_nps` |

Do not name a string business key `weld_id`. That name is reserved for the integer FK to `welds.id`.

## Industry fields

- **Line list (B31.3):** design/operating/test pressure in barg, NPS and DN, pipe class, corrosion allowance, NDT extent (RT/UT/PT/MT), sour service, P&ID, PCF, isometric revision.
- **Weld map / ASME IX:** weld number (joint number), NPS, schedule, process, position, P-Number / Group, pipe and filler heat numbers, VT result.
- **Welder (ASME IX QW-322/350, ISO 9606):** stencil number, F-Number, diameter range, progression, backing, last welded date, certificate number.
- **WPS/PQR (ASME IX):** WPS/PQR numbers, P/F/A numbers, qualified thickness, position, gas backing.
- **NDT:** procedure number, acceptance standard, technique, extent %, indication, film density (RT).
- **Test package / hydro:** design and test pressure in barg, isolation boundary, P&ID limits.

## Compatibility

Existing Python attributes (`weld_id` on `Weld`, `weld_id_fk` on NDT, `report_no`, `stencil_no`, `test_pressure_bar`, …) remain available as SQLAlchemy synonyms. Existing SQLite files are renamed on startup before `create_all`, so the new names are not added as empty duplicate columns.
