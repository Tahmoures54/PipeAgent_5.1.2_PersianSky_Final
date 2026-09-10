# PipeAgent 4.1 — Persistent Execution Control

PipeAgent 4.1 turns the Execution Graph into a persistent, event-driven control layer.

## What changed

- Business changes to execution-relevant records are persisted as `ExecutionEvent` records.
- The execution graph is stored in `ExecutionGraphNode` and `ExecutionGraphEdge` tables and rebuilt deterministically from project evidence.
- Downstream effects are stored as `ExecutionImpact` records with severity, probability, evidence and recommended action.
- `ExecutionForecast` stores the current 24-hour dependency forecast so the application can recover the control picture after restart.
- The Execution OS UI now exposes event count, open impacts, dependency forecasts and the recommended action.

## Business rule

The engine does not automatically approve, reschedule or assign field work. It identifies evidence-backed dependencies and recommends controlled actions to the responsible professional.

## Forecast wording

When a constraint has downstream dependencies, PipeAgent can produce a statement equivalent to:

> Constraint not resolved today may affect downstream execution.

The forecast always carries affected nodes, probability, impact score and a recommended action. It is an operational risk signal, not a contractual schedule promise.
