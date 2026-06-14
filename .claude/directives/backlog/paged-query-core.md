# Paged Query Core

**Set:** 2026-06-13
**Status:** Backlog -- sequence position 1 in perfect-codebase set
**Slug:** paged-query-core

## Outcome

A single `Core/Querying/` package owns the abstraction every Repository uses to serve paged, sorted, filtered reads. Repositories declare what they query; the package builds safe parameterised SQL with `LIMIT`/`OFFSET`, `ORDER BY` whitelisting, and filter-clause composition. No Repository hand-rolls `LIMIT %s` / `OFFSET %s` after migration. Backend serves the data contract `table-renderer-service` consumes.

## Acceptance Criteria

1. **`Core/Querying/PagedQuery.py` exists** with `PagedQuery` (value object: Page, PageSize, Sort, Filter), `QueryFilter` (clause + params + AND/OR composer), `QuerySort` (column + direction, whitelist-validated), `PagedQueryResult` (Rows + TotalCount + Page + PageSize), `PagedQueryBuilder` (composes a base SELECT + WHERE + ORDER BY + LIMIT/OFFSET against `DatabaseService`).

2. **SRP -- one responsibility per class.** Each class above lives in its own file. Verifiable: `ls Core/Querying/*.py` shows one class per file.

3. **OCP -- new filter type without builder change.** Adding a new `QueryFilter` type (range, IN-list, full-text) creates one new class implementing the filter interface. `PagedQueryBuilder` is not edited. Verifiable: add a `RangeFilter`; `git diff --stat Core/Querying/PagedQueryBuilder.py` is empty.

4. **LSP -- substitutable filters.** Any `QueryFilter` plugs into `PagedQueryBuilder` interchangeably. Verifiable: contract test passes `EqualsFilter`, `LikeFilter`, `RangeFilter`, `InListFilter` through the same builder method.

5. **DIP -- Repositories depend on `PagedQuery`, not on SQL strings.** Repository methods receive a `PagedQuery` and return a `PagedQueryResult`. Repositories do not assemble `LIMIT`/`OFFSET` SQL inline. Verifiable: `grep -rE "LIMIT %s|OFFSET %s" Features/` returns zero matches after migration.

6. **ISP -- focused filter / sort interfaces.** `IQueryFilter` exposes `ToClause()` and `Params()` only. `IQuerySort` exposes `ToOrderBy()` only. No god-interface. Verifiable: interface files <=20 lines each.

7. **SQL injection safe.** Every column name (sort + filter) is validated against a per-query whitelist supplied by the Repository. Verifiable: contract test `TestPagedQueryInjection.py` passes `; DROP TABLE` and `1' OR '1'='1` strings and asserts they raise `InvalidColumnError`, not execute.

8. **`EscapeLikePattern` integration.** `LikeFilter` automatically applies `EscapeLikePattern()` and emits `ESCAPE '!'`. Verifiable: feed a path containing `%`, `_`, `!` -- query returns expected rows.

9. **PostgreSQL `RealDictCursor` -> `CaseInsensitiveDict`.** `PagedQueryResult.Rows` returns the project's existing `CaseInsensitiveDict`. Verifiable: contract test asserts `Row['ShowName']` and `Row['showname']` both work.

10. **Total count strategy.** `PagedQueryResult.TotalCount` is filled via a window function `COUNT(*) OVER ()` in the same query when efficient, or a separate `COUNT(*)` query when window-function cost is high. Strategy is selected per Repository via a `CountStrategy` enum. Verifiable: each migrated Repository declares its strategy; tests assert returned count matches actual filtered row count.

11. **Migration completeness.** Repositories serving paged endpoints route through `PagedQuery`. Initial migration set: `ShowSettingsRepository.GetShowsWithStats`, `TranscodeJobRepository.GetActiveJobs`, `TranscodeQueueRepository.GetQueueItems`, `MediaFilesRepository.GetMediaFiles`, `QualityTestRepository.GetResults`. Verifiable: each method accepts `PagedQuery`, returns `PagedQueryResult`.

12. **Feature doc owns the contract.** `Core/Querying/paged-query.feature.md` exists with Workflows, Seams, Criteria, API Version field.

13. **Contract tests cover invariants.** `Tests/Contract/TestPagedQuery.py` covers: empty filter, multi-filter AND, OR composition, sort whitelist enforcement, page boundary (page 0, last page, beyond last), total count accuracy, injection rejection.

## Out of Scope

- Frontend table rendering (see `table-renderer-service.md`).
- Writes (INSERT/UPDATE/DELETE) -- this is a read-side abstraction.
- Full-text search ranking (separate concern; defer).
- Cursor-based pagination (offset/limit only for v1; cursor is a follow-up if needed for very large tables).

## Constraints

- Pure Python. No new dependencies.
- PascalCase per CLAUDE.md.
- Uses existing `DatabaseService.ExecuteQuery` -- does not bypass it.
- No hardcoded defaults in builder; all defaults read from a `PagedQueryConfig` (default page size, max page size).
- Whitelist enforcement is mandatory; opt-in is not an option.

## Engineering Calls Already Made

- Window-function `COUNT(*) OVER ()` over separate count query as default for tables under ~100k rows; per-Repository override possible.
- Offset/limit over cursor pagination for v1; cursor is a follow-up if perf demands.
- `CaseInsensitiveDict` rows over Pydantic models -- matches existing Repository contract; conversion is a separate refactor.

## Status

Backlog 2026-06-13 -- sequence position 1 (precondition for `table-renderer-service`).

### Files

```
Core/Querying/__init__.py                            -- CREATE
Core/Querying/PagedQuery.py                          -- CREATE: value object
Core/Querying/QueryFilter.py                         -- CREATE: filter interface + Equals/Like/Range/InList
Core/Querying/QuerySort.py                           -- CREATE: sort with whitelist validation
Core/Querying/PagedQueryResult.py                    -- CREATE: result value object
Core/Querying/PagedQueryBuilder.py                   -- CREATE: SQL assembly
Core/Querying/PagedQueryConfig.py                    -- CREATE: defaults (page size, max page size)
Core/Querying/Interfaces/IQueryFilter.py             -- CREATE
Core/Querying/Interfaces/IQuerySort.py               -- CREATE
Core/Querying/Exceptions.py                          -- CREATE: InvalidColumnError, etc.
Core/Querying/paged-query.feature.md                 -- CREATE: the contract
Tests/Contract/TestPagedQuery.py                     -- CREATE
Tests/Contract/TestPagedQueryInjection.py            -- CREATE
Tests/Contract/TestPagedQueryBuilder.py              -- CREATE
Features/ShowSettings/ShowSettingsRepository.py      -- EDIT: route GetShowsWithStats through PagedQuery
Features/TranscodeJob/TranscodeJobRepository.py      -- EDIT
Features/TranscodeQueue/TranscodeQueueRepository.py  -- EDIT
Features/MediaFiles/MediaFilesRepository.py          -- EDIT (if exists; else CREATE seam)
Features/QualityTesting/QualityTestRepository.py     -- EDIT
```

### Promotions

To populate at DELIVERING.

### Verification

To populate at VERIFYING. 13 entries.

### Decisions Made

To accrete during IMPLEMENTING.
