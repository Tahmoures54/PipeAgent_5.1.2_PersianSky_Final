# PipeAgent site registers — Access / SQL → industry names

The columns below came from a live piping execution database (`joint_history`, `project_actions`, `dcc_data`, `pip-mto`, `support_table`, `technical_query`, `TestPackage`, `Company`). PipeAgent stores them on the existing execution tables using the 5.2.5 naming rules (`id` PK, `*_id` FK, `*_number` business id, units on quantities). Access aliases remain as SQLAlchemy synonyms.

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
| PWHT-Req / RT-Percent / PT-Percent | `pwht_required`, `ndt_percent_rt`, `ndt_percent_pt` |
| SF | `weld_type` (synonym `shop_field`) |
| TestPackageNo / SpoolNumber | `test_package_number`, `spool_number` |
| JointStatus / BaseMetal / Contractor | `status`, `material` (`base_metal`), `contractor` |
| Insulation / Left / LeftQty / Right / RightQty | `insulation`, `left_component`, `left_qty`, `right_component`, `right_qty` |
| JointRemark / Hold / isExpired | `remarks`, `hold`, `is_expired` |

`joint_history` in PipeAgent remains the weld **event log**. The Access joint register is the `welds` row.

## Project actions → `project_actions`

Document type/number/date, subcontractor, RT report number, action-by 1/2, result, work front, link, remarks, created/updated by.

## Documents → `documents`

DCC receive/send transmittal and letter numbers, bilingual description, department, area, class, index, service, sheet, size, markup, remarks.

## MTO → `material_takeoff`

Source document, item, thickness/length, 2-year and purchase quantities, phase, commodity code, MIV number/date/qty.

## Supports → `pipe_supports`

AG/UG, sheet, service, size, base metal, joint, weld status, fab/erection weights and fit-up/weld reports, PT, test package.

## Technical query → `technical_queries`

New table: TQ number, dates, raised by, description, related document, category (includes RFI), priority, due date, response, status, assigned to, approval.

## Test package → `test_packages`

Area, AG/UG, dia-inch and inch-metre, then the site finishing sequence: line check → cleaning → pressure test → flushing/draining → face cleaning → reinstatement (finished flag, result, date, subcontractor).

## Company → `companies`

Company name, linked project, logo path. Edited from Project Setup.
