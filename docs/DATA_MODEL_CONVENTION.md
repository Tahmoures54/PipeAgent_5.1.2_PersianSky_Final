# PipeAgent data model convention

PipeAgent stores piping execution records the way an EPC site actually works: line list, weld map, WPS/PQR, welder qualification, NDT, hydro packs, punch/NCR, and mechanical completion. Column names follow that language and ISO/ASME field practice (ASME B31.3 line list, ASME IX WPS/PQR and welder continuity, API 570/598 inspection and valve tests, ISO 9606 stencil identification).

## Naming rules

| Pattern | Meaning | Example |
|---|---|---|
| `id` | Surrogate primary key | `welds.id` |
| `*_id` | Integer foreign key to that table’s `id` | `ndt_records.weld_id` → `welds.id` |
| `*_number` / `*_code` | Business identifier shown on drawings and reports | `weld_number`, `wps_number`, `ncr_number`, `mcc_number` |
| `*_barg` / `*_c` / `*_mm` / `*_pct` / `*_inch` / `*_kg` | Quantity with unit | `design_pressure_barg`, `preheat_min_c`, `wall_thickness_mm` |
| `*_quantity` | Count or issued amount (not `qty`) | `left_quantity`, `two_year_quantity`, `target_quantity` |
| `size_nps` / `size_dn` | Nominal pipe size (ASME B36.10 / B16.5) and DN, not a generic `size` | `welds.size_nps`, `line_list.size_dn` |
| `is_*` | Boolean flag | `is_on_hold`, `is_expired` |
| `*_file_path` | Stored file location | `companies.logo_file_path` |

Do not name a string business key `weld_id`. That name is reserved for the integer FK to `welds.id`. Do not name a string stencil `welder_id`; use `welder_stencil_number` (ISO 9606 / ASME IX). NDT extent is `ndt_extent_*_pct`, not `ndt_percent_*`. Line-check finishing columns are `line_check_*`, not `linecheck_*`.

### Allowed `*_id` that are not foreign keys

Opaque identifiers from people, devices, or external systems keep `*_id` when that is the industry term:

- Personnel: `employee_id`, `national_id`
- Integration / telemetry: `external_id`, `device_id`, `correlation_id`, `machine_id`, `operator_id`
- Polymorphic event rows: `entity_id`, `record_id`, `resource_id`

`iso_number` is the isometric drawing number used on weld maps (EPC / ISO 15926 practice). `line_list.material` is the pipe material specification, not weld base metal (`welds.base_material`).

## Industry fields

- **Line list (B31.3):** design/operating/test pressure in barg, NPS and DN, pipe class, corrosion allowance, NDT extent (RT/UT/PT/MT), sour service, P&ID, PCF, isometric revision.
- **Weld map / ASME IX:** weld number (joint number), NPS, schedule, process, position, P-Number / Group, pipe and filler heat numbers, VT result, base material, welder stencil, hold/expired, left/right quantities.
- **Welder (ASME IX QW-322/350, ISO 9606):** stencil number, F-Number, diameter range, progression, backing, last welded date, certificate number, qualified P-Number.
- **WPS/PQR (ASME IX):** WPS/PQR numbers, P/F/A numbers, qualified thickness, position, gas backing.
- **NDT:** procedure number, acceptance standard, technique, extent %, indication, film density (RT), inspector stamp.
- **Test package / hydro:** design and test pressure in barg, isolation boundary, P&ID limits, dia-inch / inch-metre, plus the site finishing sequence (line check, cleaning, pressure test, flushing, face cleaning, reinstatement).
- **Joint register:** isometric sheet/revision, AG/UG, pipe class, shop/field, mating components, hold/expired, test package and spool numbers.
- **DCC / MTO / supports / TQ:** `document_*` (not `doc_*`), receive–send transmittals, MIV quantities, support subtype and location description, technical queries. See `docs/SITE_REGISTERS.md`.
- **Work fronts:** `target_quantity` / `actual_quantity`.

## Compatibility

Existing Python attributes (`weld_id` on `Weld`, `weld_id_fk` on NDT, `report_no`, `stencil_no`, `test_pressure_bar`, `ndt_percent_rt`, `linecheck_finished`, `doc_number`, `two_year_qty`, `action_by_1`, `target_qty`, `location_desc`, …) remain available as SQLAlchemy synonyms. Existing SQLite files are renamed on startup before `create_all`, so the new names are not added as empty duplicate columns.
