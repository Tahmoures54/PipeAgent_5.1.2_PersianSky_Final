# PipeAgent Reporting & Operational Intelligence

## Field report lifecycle

PipeAgent treats field reports as controlled project evidence:

`Draft → QC Review → Official`

A draft is never treated as an official record. Draft HTML output is visibly marked **DRAFT — NOT FOR CONSTRUCTION**. Official HTML output is marked **OFFICIAL** and includes approval information.

## Welding report controls

Before an accepted welding report can be approved:

- The report should be linked to the relevant weld/joint when traceability is required.
- The visual result must be final.
- Any declared RT/PT/UT method must have a final result rather than `Pending`.
- Approval is restricted to Administrator, Engineer or Inspector roles.

## Fit-up report controls

Before an accepted Fit-up report can be approved, the following checks must be populated:

- Root Gap
- Hi-Low
- Alignment
- Bevel
- Cleanliness
- Tack Quality

## HTML and printing

Every welding and Fit-up draft/official record can be:

1. Generated as a self-contained HTML report.
2. Opened in the system browser for sharing or archival.
3. Sent to the native Qt print preview for paper/PDF printing.

The HTML uses A4 print CSS and includes document-control language, report status, project identity and approval information.

## Smart operational hints

PipeAgent uses deterministic, evidence-based rules for timely hints. Current controls include:

- NDT queue growth
- Weld repair rate
- Weld rejection rate
- NDT failures
- Overdue Work Fronts
- Ready but undispatched Work Fronts
- Blocked/Waiting Work Fronts
- Draft field reports waiting for QC approval
- Failed or re-test-required test packages
- Multiple test packages ready for scheduling

Every hint contains:

- Severity
- Category
- Evidence
- Recommended next action

The rules are intentionally auditable. They assist project control but do not replace approved engineering, inspection or QC decisions.

## Executive HTML report

The Executive HTML Report combines:

- Execution and quality KPIs
- Weld acceptance/repair/rejection indicators
- NDT performance
- Spool installation status
- Test package status
- Smart operational hints
- A weld-register snapshot

This creates a practical management report without requiring external reporting software.

## Management analytics HTML pack

**Reports & Analytics → Management Analytics**, or **File → Export Management Analytics…**, writes a print-ready HTML folder:

- Index with KPIs, analytical findings, and unit / contractor / material / service tables
- Separate slice files: by unit, contractor, pipe material, fluid service, pipe class, NPS band, plus quality / NDT / test packages

Grouping uses the live weld register (`area_name` / Area, `contractor`, `base_material`, `line_service`) and falls back to the line list when a joint field is blank. Dia-inch is parsed from `size_nps` (including `1-1/2` style sizes).

The pack is a **management report**, not QC acceptance evidence. Excel Pack includes the same grouping sheets.
