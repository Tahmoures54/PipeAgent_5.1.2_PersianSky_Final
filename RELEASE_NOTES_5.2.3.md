# PipeAgent 5.2.3 — File, Help & Register UX Upgrade

## Highlights
- **PipeAgent** is now the first top-level menu and opens with Dashboard as its first command.
- File menu upgraded with project folder access, Excel/Data Exchange, full project export, database backup, backup folder access, current-view printing, refresh, logout and exit.
- Help menu now opens the English and Persian user guides stored in the project root.
- Added `PipeAgent_User_Guide_EN.html` and `PipeAgent_User_Guide_FA.html`. Both guides include practical workflows and restrained product-awareness content.
- Added centralized register-column normalization to improve naming consistency without changing existing row indexes.
- Operational tables automatically receive a **Description / Notes** column when no equivalent descriptive field exists.
- Existing horizontal and vertical scrolling behavior remains enabled.

## File Operations
- Database backups are timestamped and written to `backups/`; the live database is never overwritten by the backup command.
- Full project export delegates to the existing Data Exchange Center export pack.
- Printing uses the native Qt print dialog.

## Keyboard Shortcuts
- `Ctrl+D` Dashboard
- `Ctrl+Alt+I` Import Excel / Data
- `Ctrl+Alt+E` Export Full Project Pack
- `Ctrl+Alt+B` Backup Database
- `Ctrl+P` Print Current View

## Validation
- Python compilation: passed
- Automated test suite: **14 passed, 33 warnings**
