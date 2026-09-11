# PipeAgent databases — SQLite, SQL Express, PostgreSQL

SQLite is correct for one laptop. It is not a multi-user site database: writers lock the file, there is no real concurrent session model, and the file cannot sit on a flaky share.

## What to use

| Situation | Engine |
|---|---|
| One QC laptop, demo, offline camp | SQLite |
| Windows site server, several desktops on the LAN | **SQL Server Express** (then Standard if the 10 GB cap is too small) |
| Linux server, Docker, or a hosted “online” database | **PostgreSQL** |

PipeAgent already talks to these through SQLAlchemy. The desktop path is **File → Database Connection…**. IT can instead set `PIPEAGENT_DATABASE_URL` (that wins over the dialog).

## SQL Server / Express

1. Install SQL Server Express and create an empty database named `PipeAgent`.
2. Install **ODBC Driver 17 or 18 for SQL Server**.
3. `pip install pyodbc`
4. In PipeAgent choose SQL Server / Express. Host `localhost` (or the server name), instance `SQLEXPRESS`, Windows auth or a SQL login.
5. Restart PipeAgent. Set `PIPEAGENT_BOOTSTRAP_ADMIN_PASSWORD` so the first admin is created.

Named instance URLs use a backslash: `localhost\SQLEXPRESS`.

## PostgreSQL (LAN or online)

Use the `psycopg` driver from `requirements.txt`. Hosted Postgres (the usual “online database”) is the same URL with the provider host.

## Backups

SQLite: File → Backup Database (local `.db` copy). SQL Server / PostgreSQL: SSMS, `pg_dump`, or the host’s backup. Copy document evidence (`documents/`) with the database.

The per-workstation profile is `pipeagent.connection.json` (not committed). Passwords in that file are a site-LAN convenience; production should use the environment variable and a secret store.
