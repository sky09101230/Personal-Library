# postgresql-persistence Specification

## Purpose
Defines a single PostgreSQL source of truth for AgentSys runtime state and a verifiable migration boundary from the recovered SQLite database.
## Requirements
### Requirement: Explicit database backend selection
The system SHALL use PostgreSQL only when the local deployment explicitly selects the PostgreSQL backend and supplies all required connection settings. The system MUST retain an explicit SQLite backend for controlled development and rollback checks.

#### Scenario: PostgreSQL deployment starts with complete settings
- **WHEN** the PostgreSQL backend is selected with a database name, application user, password, loopback host, and port
- **THEN** Django connects through its PostgreSQL backend and reports no unapplied migrations

#### Scenario: PostgreSQL deployment has incomplete settings
- **WHEN** the PostgreSQL backend is selected without a required connection setting
- **THEN** startup fails with a configuration error before serving requests

### Requirement: Migrated data remains complete and linked
The migration MUST preserve the primary keys, field values, and relationships of application-owned SQLite records, including users, sessions, admin history, MCP access tokens, literature, uploads, metadata proposals, source configuration, Skills, releases, candidates, purposes, and sync jobs. PostgreSQL-incompatible NUL control characters in derived metadata text SHALL be normalized to spaces in the migration fixture with their locations and counts recorded, while the SQLite source and original files remain unchanged. Framework-generated content types and permissions SHALL be recreated from migrations rather than copied as authoritative data.

#### Scenario: Migration verification succeeds
- **WHEN** the SQLite source has been frozen and imported into an empty migrated PostgreSQL database
- **THEN** every application-owned table has the expected record count, documented NUL normalization is the only field transformation, no foreign-key violations or duplicate constrained identities exist, and generated sequences allocate values above existing primary keys

### Requirement: Existing runtime behavior survives cutover
The PostgreSQL-backed deployment SHALL preserve existing authentication, homepage queries, MCP token verification, literature publication relationships, and Skill release visibility.

#### Scenario: Runtime smoke checks pass
- **WHEN** the migrated PostgreSQL database is active
- **THEN** an existing user can authenticate, the homepage renders successfully, an existing active MCP token resolves to its owner, published literature retains its uploads and contributors, and NAS-backed Skill releases remain queryable

### Requirement: Migration remains recoverable
The migration MUST retain the frozen SQLite source until PostgreSQL verification completes and MUST create a restorable PostgreSQL backup outside Git and Syncthing before normal writes resume.

#### Scenario: Cutover verification fails
- **WHEN** any required data or runtime check fails before writes resume
- **THEN** the deployment can return to the unchanged SQLite source without merging partial PostgreSQL writes

#### Scenario: Cutover verification succeeds
- **WHEN** all required checks pass
- **THEN** a PostgreSQL backup is created and verified before Uvicorn resumes normal service
