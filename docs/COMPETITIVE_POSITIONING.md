# PipeAgent competitive positioning

PipeAgent is a **Piping Execution Operating System**, not a weld spreadsheet and not a generic construction dashboard.

## Who we compete with

| Competitor | What they sell | Where they are strong | Where PipeAgent should beat them |
|---|---|---|---|
| **Prometheus Weld-Console** | Weld / NDE / hydro completions for EPC | Design-model import, **automatic NDE/PWHT assignment**, B31.3 random/progressive RT, hydro clearance | Execution graph, next-best-action, work-front constraints, turnover evidence |
| **WeldTrace / Welding Manager / Field PM weld map** | Welder WPQ, continuity, weld log, NDE, test packs | QW-322 continuity, QR travelers, RT% dashboards | Line→ISO→spool→front→weld→NDT→test→punch chain in one OS |
| **Konnect xD Construction** | FPSO / plant construction intelligence | IDF/PCF ingest, earned value gated on inspection | Piping-specific code gates (B31.3 lots, hydro, QW-322) plus predictive brief |
| **Hexagon Smart Completions / Smart Materials** | Completions and material traceability at plant scale | CFIHOS, tag completeness, owner handover | Faster piping-crew daily decisions without an 18-month completions rollout |
| **Procore / generic PM** | Cost, RFI, daily reports | Budget and document control | They do not speak weld number, line class, NDE lot or hydro pack |

The market baseline is no longer “store a weld register”. Buyers expect **code-correct NDE lots**, **welder continuity**, **hydrotest gates that match the ITP**, and **a daily instruction list**.

## What 5.2.6 actually does

PipeAgent now issues the same class of daily instruction Weld-Console is known for, from data already in the line list and weld register:

1. **B31.3 examination extent** — RT/UT/PT/MT percent from the line list, measured by joint count and NPS-inch.
2. **Deterministic lot selection** — extra joints are chosen with a stable hash of `weld_number` so QC can audit why that joint was picked.
3. **Progressive examination** — a rejected spot test pulls two more joints from the same welder; a failed extra exam escalates the remainder of that lot.
4. **Hydrotest clearance** — Category-A punches, rejected NDE, PWHT, coverage shortfall, spring-hanger pins.
5. **QW-322 continuity** — 150-day warning and 180-day stop from `last_welded_date` or the latest production weld.
6. **Execution brief** — ranked next actions for NDE, welders, hydro packs and the repair queue (advisory only).

Exposed at:

- `GET /api/v1/projects/{id}/compliance/nde-coverage`
- `GET /api/v1/projects/{id}/compliance/nde-lots`
- `GET /api/v1/projects/{id}/compliance/execution-brief`
- `GET /api/v1/projects/{id}/test-packages/{id}/hydro-clearance`

Desktop: NDT tab KPI **NDE Coverage Gaps** and **NDE Lot (B31.3)**. Dashboard smart hints consume the same brief.

## Moat we keep

The OS question remains:

> **What should the project team do next, why, what evidence supports it, and what happens if we do nothing?**

Code compliance feeds that question. It does not auto-approve WPS, NDE or hydrotest.
