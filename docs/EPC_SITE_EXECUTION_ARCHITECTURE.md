# PipeAgent EPC Site Execution Architecture

PipeAgent is positioned as a Piping Execution Operating System within the wider EPC site execution environment.

## Execution domains
1. Engineering and document control
2. Procurement and material readiness
3. Spooling and fabrication
4. Piping erection
5. Welding, NDT, QA/QC, NCR, and punch
6. Supports, valves, painting, insulation, and reinstatement
7. Instrumentation installation, calibration, loop checks, and functional testing
8. Work fronts, permits, manpower, equipment, and field constraints
9. Pre-commissioning and commissioning
10. Turnover dossiers and as-built evidence
11. Predictive execution intelligence
12. Enterprise integration and reporting

## Instrumentation lifecycle
Instrument Tag → Datasheet → Material/Receipt → Installation → Calibration → Cable/Tube Completion → Continuity → Loop Check → Functional Test → Punch Clearance → System Completion → Turnover.

## OT integration boundary
PipeAgent should not directly operate safety-critical process equipment. Field PLC/DCS/SCADA systems remain the control authority. PipeAgent receives controlled execution and telemetry information through gateways and approved interfaces.

Typical integration paths:

- OPC UA for structured industrial information exchange
- MQTT for event/telemetry transport
- REST/HTTPS for enterprise APIs
- Modbus through an approved edge gateway
- ERP/EAM/CMMS interfaces for materials, assets, and maintenance
- P6/scheduling interfaces for planned and actual execution
- DMS/EDMS interfaces for controlled documents
- IFC/BIM exchange for spatial and asset context

## Predictive site control
The Site Execution Control Center highlights overdue calibration, expiring permits, unavailable equipment, open site issues, and commissioning turnover blockers. These signals can later feed the persistent Execution Graph and Work Front Autopilot.
