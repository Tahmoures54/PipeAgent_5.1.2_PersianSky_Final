# PipeAgent 5.2.7 — Site registers, users, and workspace shell

## Why this revision

A live piping execution database (joint history, DCC, MTO/MIV, supports, technical queries, test-package finishing, company identity) showed gaps in the workspace shell: File/PipeAgent menu order, no users menu, uneven turquoise toolbar buttons, and missing site-register columns.

## Changes

- Menu bar is File, PipeAgent, Users, View, Help. Users opens the real `users` table and shows the signed-in access level.
- Sidebar and module shortcuts follow site roles (administrator, project manager, engineer, inspector, welder, storekeeper, document controller, client, viewer).
- Turquoise top bar actions (Support, Alerts, Refresh, Users) share the same 36 px height and padding.
- Weld, DCC, MTO, support, action and test-package registers take the Access columns under industry names. Technical Query and Company are first-class tables.
- Mapping: `docs/SITE_REGISTERS.md`.

## Validation

- `python3 -m pytest` is the release gate for this revision.
