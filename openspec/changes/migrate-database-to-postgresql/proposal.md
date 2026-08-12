## Why

Syncthing cannot safely reconcile concurrent SQLite database files, and the resulting conflict selected an older schema and data snapshot. AgentSys needs one transactional database owned by the local application host so all runtime state has a single source of truth.

## What Changes

- Configure Django to use the local PostgreSQL service when explicitly selected by environment variables, while retaining SQLite as an explicit development and rollback backend.
- Add the supported Psycopg 3 driver for the existing Python 3.14 and Django 5.2 runtime.
- Migrate the recovered SQLite records into PostgreSQL without changing primary keys, publication state, credentials, object-storage paths, or source configuration.
- Verify record counts, constraints, sequences, login, homepage, MCP access-token lookup, literature relationships, and Skill release visibility before cutover.
- Keep database files and credentials outside Git and Syncthing, and create a PostgreSQL backup after verification.

## Capabilities

### New Capabilities
- `postgresql-persistence`: AgentSys can use a local PostgreSQL database as its authoritative runtime store and migrate the recovered SQLite state with verified completeness and rollback boundaries.

### Modified Capabilities

None.

## Impact

- Affects `config/settings.py`, `requirements.txt`, local database environment variables, operational preparation/decision documentation, and the one-time database migration procedure.
- Adds Psycopg 3 as a runtime dependency.
- Does not change HTTP, MCP, literature-storage, Zotero, or Skill archive APIs.
- Requires a brief write outage during the final SQLite export and PostgreSQL import; the recovered SQLite database remains available for rollback.
