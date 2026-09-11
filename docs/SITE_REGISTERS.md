# PipeAgent site registers — Access / SQL → industry names

The columns below came from a live piping execution database (`joint_history`, `project_actions`, `dcc_data`, `pip-mto`, `support_table`, `technical_query`, `TestPackage`, `Company`). PipeAgent stores them on the existing execution tables using the data-model rules in `docs/DATA_MODEL_CONVENTION.md` (`id` PK, `*_id` FK, `*_number` business id, units on quantities). Access aliases remain as SQLAlchemy synonyms.

## Joint history → `welds`

| Source | PipeAgent |
|---|---|
| IsoNo | `iso_number` |
| SheetNo / SheetRev / RevStatus | `sheet_number`, `sheet_revision`, `revision_status` |
| AG/UG | `install_location` (synonym `ag_ug`) |
| LineNo / Area / Region | `line_number`, `area_name`, `region` |
| PipeClass / LineService | `pipe_class`, `line_service` |
| JointNu / JointIndex | `weld_number`, `joint_index` |
| Thk / JointSize / JointType / jSch | `wall_thickness_mm`, `size_nps`, `joint_type`, `schedule` |
| PWHT-Req / RT-Percent / PT-Percent | `pwht_required`, `ndt_extent_rt_pct`, `ndt_extent_pt_pct` |
| SF | `weld_type` (synonym `shop_field`) |
| TestPackageNo / SpoolNumber | `test_package_number`, `spool_number` |
| JointStatus / BaseMetal / Contractor | `status`, `base_material` (`base_metal`, `material`), `contractor` |
| Insulation / Left / LeftQty / Right / RightQty | `insulation`, `left_component`, `left_quantity`, `right_component`, `right_quantity` |
| JointRemark / Hold / isExpired | `remarks`, `is_on_hold`, `is_expired` |

`joint_history` in PipeAgent remains the weld **event log**. The Access joint register is the `welds` row.

## Project actions → `project_actions`

Document type/number/date, subcontractor, RT report number, performed-by 1/2, result, work front, link, remarks, created/updated by.

## Documents → `documents`

`document_number`, `document_type`, `document_class`, `document_index`, DCC receive/send transmittal and letter numbers, bilingual description, department, area, service, sheet, size, markup, remarks.

## MTO → `material_takeoff`

Source document, item, thickness/length, `two_year_quantity` / `purchase_quantity` / `miv_quantity`, phase, commodity code, MIV number/date.

## Supports → `pipe_supports`

AG/UG, sheet, service, size, `base_material`, joint, weld status, fab/erection weights and fit-up/weld reports, PT, test package, `support_subtype`, `location_description`.

## Technical query → `technical_queries`

TQ number, dates, raised by, description, `related_document_number`, category (includes RFI), priority, due date, response, status, assigned to, approval.

## Test package → `test_packages`

Area, AG/UG, `dia_inch` and `inch_metre`, then the site finishing sequence: line check → cleaning → pressure test → flushing/draining → face cleaning → reinstatement (`line_check_finished`, result, date, subcontractor).

## Company → `companies`

Company name, linked project, `logo_file_path`. Edited from Project Setup.
