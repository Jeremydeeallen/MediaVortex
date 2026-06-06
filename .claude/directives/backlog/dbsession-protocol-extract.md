# Directive (backlog): DbSession Protocol Extract

**Slug:** dbsession-protocol-extract
**Prerequisite:** `db-monolith-decompose` (per-aggregate repos must exist before they can depend on a Protocol)

## Outcome

Per-aggregate repositories depend on a `Core.Database.DatabaseSession` Protocol (PEP 544 structural type), not the concrete `DatabaseService` + `psycopg2.RealDictCursor`. The Protocol exposes the operations every repo actually uses: `ExecuteQuery(sql: str, params: tuple) -> list[dict]`, `ExecuteNonQuery(sql: str, params: tuple) -> int`, `GetConnection()`, `CloseConnection(conn)`. Concrete implementations: `PostgresDatabaseSession` (the current behavior, wraps the existing DatabaseService) and `InMemoryDatabaseSession` (for unit tests; SQLite-backed). The directive ships the Protocol + the two implementations + a sweep of every repo's constructor to accept `DatabaseSession`.

After this directive: unit tests instantiate repos with `InMemoryDatabaseSession` (no DB required, no psycopg2 mocking). Engine swaps (DuckDB for analytics, SQLite for tests, a future managed Postgres) become a one-line constructor change.

## Acceptance Criteria

1. `Core/Database/DatabaseSession.py` defines the `DatabaseSession` Protocol with the 4 methods.
2. `Core/Database/PostgresDatabaseSession.py` implements the Protocol, wrapping the existing `DatabaseService` connection pool semantics.
3. `Core/Database/InMemoryDatabaseSession.py` implements the Protocol against an in-memory SQLite database; suitable for unit tests but does NOT need to match psycopg2's exact SQL dialect (tests using it should write SQLite-portable SQL or get explicitly skipped).
4. Every `<Aggregate>Repository.py` constructor accepts `session: DatabaseSession` (no default; required injection). Caller services update accordingly.
5. `Core/Database/DatabaseService.py` either implements the Protocol natively OR a thin adapter wraps it. No service depends on `DatabaseService` directly anymore.
6. Existing pytest suite green against `PostgresDatabaseSession` (live DB). New `pytest -k "_in_memory"` suite green against `InMemoryDatabaseSession`.
7. R-rule update (or new rule): repositories MUST type-hint `session: DatabaseSession` in their constructors. R-hook refuses concrete-type injection.

## Out of Scope

- Migrating production code paths off `PostgresDatabaseSession`. The protocol unlocks alternatives; switching engines is a separate operator decision.
- Multi-master / replication / read-replica concerns. Single-engine semantics for now.
- Async session support (asyncpg, etc.). Sync only; async is its own directive if/when needed.

## Why this is backlog

The SOLID win from `db-monolith-decompose` (per-aggregate repos) is necessary BEFORE this directive can land. Repos that don't exist can't depend on a Protocol. Sequence: `db-monolith-decompose` first, then this.

## Estimated scope

Medium. One Protocol file, two implementations (~150 LOC each), 20-30 repository constructor updates (one line each + caller sweep), test-suite split.
