# PipeAgent Instrumentation Integration

## Current capability

PipeAgent 5.2.0 is an execution management system with an industrial telemetry ingestion layer. It can receive structured welding telemetry and use that data for WPS screening, heat-input analysis, quality intelligence, and execution analytics.

The current desktop release does **not** claim to be a PLC/SCADA driver. Direct field-device communication should be performed through an OT-safe gateway or protocol adapter.

## Recommended architecture

```text
Field Instruments / Welding Machines / PLCs
        |
        +-- Modbus RTU/TCP
        +-- OPC UA
        +-- Vendor PLC protocol (S7, EtherNet/IP, etc.)
        |
        v
OT Edge Gateway / Protocol Adapter
        |
        +-- Local buffering
        +-- Validation / normalization
        +-- Timestamping
        +-- Device health
        |
        +---- MQTT / HTTPS / REST ----> PipeAgent
                                      |
                                      +-- Welding Telemetry
                                      +-- Execution Graph
                                      +-- Quality Intelligence
                                      +-- Predictive Bottleneck
                                      +-- Work Front Intelligence
```

## Instrumentation use cases

PipeAgent should treat instrumentation as an execution discipline, not only as a tag list. The target workflow is:

1. Instrument Tag / Loop ID registration
2. Datasheet and hook-up document association
3. Calibration record
4. Installation / hook-up status
5. Cable and tubing completion
6. Continuity / insulation checks where applicable
7. Loop Check
8. Functional Test
9. Punch linkage
10. Turnover dossier evidence

## Protocol strategy

- **OPC UA:** preferred for structured, secure plant data exchange when available.
- **Modbus RTU/TCP:** appropriate for simple field devices, meters, analyzers, and legacy equipment.
- **MQTT:** preferred as the northbound transport from an edge gateway to PipeAgent when many devices or unreliable links are involved.
- **REST/HTTPS:** suitable for controlled batch or event-based integrations.

PipeAgent should not directly write to safety-critical PLC outputs from the desktop application. Any control/write operation must be explicitly designed, authorized, audited, and isolated through the site's OT architecture.

## What PipeAgent can do with the data

Once normalized telemetry reaches PipeAgent, the data can be correlated with Project, Line, Spool, Weld, Work Front, Test Package, QA/QC, Punch, and Turnover records. This is where PipeAgent adds value: the instrument signal becomes execution evidence instead of an isolated SCADA value.
