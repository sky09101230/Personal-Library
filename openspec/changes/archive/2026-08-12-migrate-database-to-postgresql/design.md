## Context

See `proposal.md` for motivation. The recovered production state is currently in `db.sqlite3`, Django and Uvicorn run on the same Windows host as PostgreSQL 18.4, PostgreSQL listens only on loopback, and the dedicated `agentsys_app` role owns an empty `agentsys` database. The worktree contains unrelated Zotero changes that must remain untouched.

## Goals / Non-Goals

**Goals:**

- Make PostgreSQL the selected backend for this host without embedding credentials in source control.
- Preserve application-owned records and primary keys with an auditable SQLite-to-PostgreSQL comparison.
- Keep a tested rollback source and produce a native PostgreSQL backup.

**Non-Goals:**

- Running multiple Django nodes, exposing PostgreSQL to the LAN, adding pooling, or introducing a managed database service.
- Refactoring models or changing business behavior during the backend migration.
- Synchronizing database storage or secrets between machines.

## Decisions

### Use Django's native PostgreSQL backend with Psycopg 3

`config/settings.py` will select either `django.db.backends.postgresql` or the existing SQLite backend from `AGENTSYS_DB_ENGINE`. PostgreSQL settings come from the existing local `.env` loader and are required when that backend is selected. `psycopg[binary]` is the only new dependency because it supports the current Windows/Python runtime without a compiler or separate client-library installation.

Alternatives rejected: `dj-database-url` adds a parser for six fixed values; a custom settings module duplicates configuration; Psycopg 2 is the legacy adapter.

### Use Django migrations plus a framework fixture for the one-time transfer

Freeze Uvicorn, export the SQLite database with primary keys and natural foreign keys, excluding `contenttypes` and `auth.permission`, migrate the empty PostgreSQL database, and load the fixture. Django recreates framework-generated rows and resets sequences after fixture loading.

SQLite JSON may legally contain escaped `\u0000`, but PostgreSQL text and JSON reject decoded NUL characters. A derived PostgreSQL fixture therefore replaces NUL with a space and records the affected model, primary key, field, and replacement count. The frozen SQLite database, original fixture, and original PDFs remain unchanged.

`skills.0010` seeds the research taxonomy. A fresh database assigns different primary keys to three taxonomy rows because the SQLite source already contained two older rows when that migration ran. Before fixture loading, verify that no PostgreSQL Skill or candidate references the fresh seed rows, remove only those migration-created taxonomy rows, and let the fixture restore all 29 rows with the SQLite primary keys.

Alternatives rejected: pgLoader adds an external migration tool and bypasses Django's model/migration contract; per-table custom copy code adds one-use logic and a larger data-loss surface.

### Validate the complete persistence boundary before resuming writes

Capture per-table SQLite counts and selected stable identities before import. Compare application-owned PostgreSQL counts, primary-key maxima, relationships, constraints, and sequence behavior after import. Run Django system checks plus direct authentication, homepage, MCP token, literature, and Skill queries against PostgreSQL.

### Keep rollback and backups outside synchronized state

The recovered SQLite file remains unchanged and ignored by Syncthing. The temporary fixture and a custom-format `pg_dump` are stored outside the repository and synchronization roots. PostgreSQL is not opened to non-loopback clients.

## Risks / Trade-offs

- [Fixture import encounters a backend-specific value or ordering issue] -> Import into the still-empty PostgreSQL database, inspect the exact failing model, reset the database, and retry without touching SQLite.
- [Derived metadata contains PostgreSQL-incompatible NUL] -> Normalize only those control characters in a separate fixture, retain transformation evidence, and verify all other serialized values remain equal.
- [Framework-generated permissions differ] -> Recreate them with migrations and compare expected generated counts rather than importing SQLite copies.
- [A sequence remains behind an imported primary key] -> Validate a rolled-back insert for every model table sequence before service startup.
- [Fresh taxonomy seed IDs differ from historical IDs] -> Clear only the unreferenced fresh seed rows before fixture import and restore the frozen taxonomy with its original primary keys.
- [Credentials leak through artifacts or commands] -> Read the password only from `.env`, redact outputs, exclude `.env` from Git and Syncthing, and never place it in OpenSpec or documentation.
- [Unrelated dirty worktree edits overlap] -> Limit code edits to settings, the dependency list, new migration documentation, and this change directory.

## Migration Plan

1. Confirm Uvicorn is stopped, PostgreSQL is loopback-only, the application role connects, and both database sources are backed up.
2. Capture the SQLite integrity result, migration state, table counts, and an export fixture outside the repository.
3. Add the backend selection and Psycopg dependency, then validate SQLite explicitly still opens the frozen source.
4. Run Django migrations against the empty PostgreSQL database and load the fixture.
5. Compare counts, primary keys, relationships, constraints, sequences, and required runtime smoke checks.
6. Create and verify a custom-format PostgreSQL backup outside Git and Syncthing.
7. Start Uvicorn on PostgreSQL and perform one HTTP login/homepage smoke test. Keep SQLite unchanged for rollback.

Rollback before normal writes resume: stop Uvicorn, select SQLite in the local environment, and restart. If PostgreSQL has accepted normal writes, do not roll back by file switching; restore or reconcile from the PostgreSQL backup instead.
