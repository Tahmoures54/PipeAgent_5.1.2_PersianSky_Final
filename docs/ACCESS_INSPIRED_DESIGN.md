# Access-inspired design notes

The supplied `PipeMaster_8.accdb` was reviewed as a functional reference. The Python application was not replaced by an Access clone; instead, useful operational concepts were mapped into the richer PyQt6/SQLAlchemy application.

## Concepts carried over

- Line List management and filtered line-list views
- WJCS / Joint History
- Fit-up and Weld report workflow
- RT / PT / UT / PWHT references
- Test Package tracking and report center
- Material Take-Off / MIV concepts
- Support management
- Employee / access level register
- Project actions / history
- Document Control
- Handover / completion

## Main workflow

Team execution -> Draft Report -> QC Review -> Approved Official Report -> Project Action / History -> Test / Handover.

The original Access database remains untouched. The Python application uses its own SQLite database and keeps the architecture maintainable for future multi-user/server deployment.
