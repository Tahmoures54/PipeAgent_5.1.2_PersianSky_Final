# PipeAgent 5.2.12 — Management analytics HTML reports

## Why this revision

Site managers need printable progress and quality views by unit, contractor, pipe material and fluid service — not only a weld log and a single executive snapshot.

## Changes

- **Reports & Analytics → Management Analytics** (and **File → Export Management Analytics…**) writes a self-contained HTML pack:
  - index (KPIs + findings + summary tables)
  - by unit / area
  - by contractor
  - by pipe material
  - by fluid service
  - by pipe class and NPS band
  - quality, NDT and test packages
- Analytical findings flag lagging units, contractor repair pressure, NDT queues by service, material concentration, and open A-punches.
- Excel Pack now includes the same grouping sheets.
- Dashboard / executive `analytics()` keys are aligned (`completed_dia_inch`, `welds.total`, `by_welder`, spool `installed`).

## Validation

- `python3 -m pytest` is the release gate for this revision.
