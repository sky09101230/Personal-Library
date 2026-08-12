## 1. Preparation and contracts

- [x] 1.1 Record the PostgreSQL architecture decision, operator preparation, cutover boundary, and rollback conditions in project documentation.
- [x] 1.2 Freeze and verify the recovered SQLite source, capture per-table evidence, and create a secret-safe migration fixture outside the repository.

## 2. Database configuration

- [x] 2.1 Add the supported Psycopg 3 binary dependency without changing unrelated dependency edits.
- [x] 2.2 Implement explicit SQLite/PostgreSQL settings with required PostgreSQL environment validation and a minimal runnable configuration check.
- [x] 2.3 Validate both backend configurations and strictly validate the OpenSpec change before data import.

## 3. Schema and data migration

- [x] 3.1 Confirm the PostgreSQL target is empty, then apply all Django migrations as `agentsys_app`.
- [x] 3.2 Load the frozen fixture and verify all application-owned row counts, primary keys, relationships, constraints, and sequences against SQLite evidence.

## 4. Cutover verification and backup

- [x] 4.1 Verify Django checks, existing authentication, homepage rendering, MCP token lookup, literature publication/uploaders, and NAS-backed Skill releases on PostgreSQL.
- [x] 4.2 Create and verify a custom-format PostgreSQL backup outside Git and Syncthing while retaining the unchanged SQLite rollback source.
- [x] 4.3 Run focused/full automated checks and strict OpenSpec validation, then document verified and unverified boundaries.
