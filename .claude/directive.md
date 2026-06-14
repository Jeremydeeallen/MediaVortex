# Paged Query Core

**Set:** 2026-06-13
**Activated:** 2026-06-14
**Status:** Active -- phase: IMPLEMENTING
**Slug:** paged-query-core

## Outcome

A single `Core/Querying/` package owns the abstraction every Repository uses to serve paged, sorted, filtered reads. Repositories declare what they query; the package builds safe parameterised SQL with `LIMIT`/`OFFSET`, `ORDER BY` whitelisting, and filter-clause composition. No Repository hand-rolls `LIMIT %s` / `OFFSET %s` after migration. Backend serves the data contract `table-renderer-service` consumes.

## Acceptance Criteria

1. **`Core/Querying/PagedQuery.py` exists** with `PagedQuery` (value object: Page, PageSize, Sort, Filter), `QueryFilter` (clause + params + AND/OR composer), `QuerySort` (column + direction, whitelist-validated), `PagedQueryResult` (Rows + TotalCount + Page + PageSize), `PagedQueryBuilder` (composes a base SELECT + WHERE + ORDER BY + LIMIT/OFFSET against `DatabaseService`).

2. **SRP -- one responsibility per class.** Each class above lives in its own file. Verifiable: `ls Core/Querying/*.py` shows one class per file.

3. **OCP -- new filter type without builder change.** Adding a new `QueryFilter` type (range, IN-list, full-text) creates one new class implementing the filter interface. `PagedQueryBuilder` is not edited. Verifiable: add a `RangeFilter`; `git diff --stat Core/Querying/PagedQueryBuilder.py` is empty.

4. **LSP -- substitutable filters.** Any `QueryFilter` plugs into `PagedQueryBuilder` interchangeably. Verifiable: contract test passes `EqualsFilter`, `LikeFilter`, `RangeFilter`, `InListFilter` through the same builder method.

5. **DIP -- Repositories depend on `PagedQuery`, not on SQL strings.** Repository methods receive a `PagedQuery` and return a `PagedQueryResult`. Repositories do not assemble `LIMIT`/`OFFSET` SQL inline. Verifiable (narrowed per 2026-06-14 operator decision -- initial-set scope): `grep -E "LIMIT %s|OFFSET %s" <5 migrated files>` returns zero matches after migration. Tree-wide enforcement is a follow-up directive.

6. **ISP -- focused filter / sort interfaces.** `IQueryFilter` exposes `ToClause()` and `Params()` only. `IQuerySort` exposes `ToOrderBy()` only. No god-interface. Verifiable: interface files <=20 lines each.

7. **SQL injection safe.** Every column name (sort + filter) is validated against a per-query whitelist supplied by the Repository. Verifiable: contract test `TestPagedQueryInjection.py` passes `; DROP TABLE` and `1' OR '1'='1` strings and asserts they raise `InvalidColumnError`, not execute.

8. **`EscapeLikePattern` integration.** `LikeFilter` automatically applies `EscapeLikePattern()` and emits `ESCAPE '!'`. Verifiable: feed a path containing `%`, `_`, `!` -- query returns expected rows.

9. **PostgreSQL `RealDictCursor` -> `CaseInsensitiveDict`.** `PagedQueryResult.Rows` returns the project's existing `CaseInsensitiveDict`. Verifiable: contract test asserts `Row['ShowName']` and `Row['showname']` both work.

10. **Total count strategy.** `PagedQueryResult.TotalCount` is filled via a window function `COUNT(*) OVER ()` in the same query when efficient, or a separate `COUNT(*)` query when window-function cost is high. Strategy is selected per Repository via a `CountStrategy` enum. Verifiable: each migrated Repository declares its strategy; tests assert returned count matches actual filtered row count.

11. **Migration completeness.** Repositories serving paged endpoints route through `PagedQuery`. Initial migration set (mapped to actual methods per 2026-06-14 operator decision):
    - `ShowSettingsRepository.GetShowsWithStats` (today: no pagination)
    - `TranscodeQueueRepository.GetTranscodeQueueItemsPaginated` (today: inline LIMIT/OFFSET + Mode filter)
    - `FileScanningRepository.GetMediaFilesPaginated` (today: inline LIMIT/OFFSET + Search + Sort) -- substituted for the non-existent `MediaFilesRepository.GetMediaFiles`
    - `QualityTestRepository.GetQualityTestResults` (today: Limit/Offset args, no filter/sort)
    - `Features/ServiceControl/ActiveJobRepository.GetActiveJobsByService` (today: ServiceName + WorkerName + RunningOnly filters; no LIMIT/OFFSET) -- substituted for the non-existent `TranscodeJobRepository.GetActiveJobs`
    Verifiable: each method accepts `PagedQuery`, returns `PagedQueryResult`.

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
Features/ShowSettings/ShowSettingsRepository.py             -- EDIT: route GetShowsWithStats through PagedQuery
Features/TranscodeQueue/TranscodeQueueRepository.py         -- EDIT: route GetTranscodeQueueItemsPaginated through PagedQuery
Features/FileScanning/FileScanningRepository.py             -- EDIT: route GetMediaFilesPaginated through PagedQuery
Features/QualityTesting/QualityTestRepository.py            -- EDIT: route GetQualityTestResults through PagedQuery
Features/ServiceControl/ActiveJobRepository.py              -- EDIT: route GetActiveJobsByService through PagedQuery
Features/ShowSettings/ShowSettingsController.py             -- EDIT (if needed): pass PagedQuery from request
Features/TranscodeQueue/TranscodeQueueController.py         -- EDIT (if needed): pass PagedQuery from request
Features/FileScanning/FileScanningController.py             -- EDIT (if needed): pass PagedQuery from request
Features/QualityTesting/QualityTestController.py            -- EDIT (if needed): pass PagedQuery from request
```

### Plan

Sequence (commit per step; each step has the smoke or contract test that exits it):

1. **Core scaffolding (no callers yet).** Create `Core/Querying/__init__.py`, `Interfaces/IQueryFilter.py`, `Interfaces/IQuerySort.py`, `Exceptions.py` (InvalidColumnError, InvalidPageError), `PagedQueryConfig.py` (DefaultPageSize=25, MaxPageSize=500), `QuerySort.py` (whitelist + ASC/DESC validation), `QueryFilter.py` (EqualsFilter, LikeFilter, RangeFilter, InListFilter + AndComposer/OrComposer), `PagedQuery.py` (Page, PageSize, Sort, Filter value object), `PagedQueryResult.py` (Rows, TotalCount, Page, PageSize), `PagedQueryBuilder.py` (composes WHERE/ORDER BY/LIMIT/OFFSET from a base SELECT, calls `DatabaseService.ExecuteQuery`).
   Exit: `Tests/Contract/TestPagedQueryBuilder.py` + `TestPagedQueryInjection.py` + `TestPagedQuery.py` all green.

2. **Migrate `QualityTestRepository.GetQualityTestResults`.** Simplest case (Limit/Offset args only, no filter/sort). Validates the abstraction against a real call site before any complex migration. Existing controller signature preserved -- shim translates Limit/Offset -> PagedQuery internally if needed.
   Exit: `Tests/Contract/TestQualityTestRepository.py` (or focused new tests) green + `grep "LIMIT %s\\|OFFSET %s" Features/QualityTesting/QualityTestRepository.py` returns zero.

3. **Migrate `FileScanningRepository.GetMediaFilesPaginated`.** Adds LikeFilter (search) + QuerySort (SortBy/SortOrder) usage. Validates EscapeLikePattern integration.
   Exit: smoke -- hit `/api/MediaFiles` endpoint; verify pagination + search + sort still work.

4. **Migrate `TranscodeQueueRepository.GetTranscodeQueueItemsPaginated`.** Adds Mode filter (categorical EqualsFilter). Validates multi-filter AND composition.
   Exit: smoke -- hit `/Queue` page; verify Pending/InProgress/Completed tabs still filter + sort + page.

5. **Migrate `ShowSettingsRepository.GetShowsWithStats`.** Adds CountStrategy (this is an aggregate query with HAVING -- window-function COUNT may be expensive). Adds optional drive filter. Adds pagination where there was none.
   Exit: smoke -- hit `/ShowSettings` page; verify shows list renders + filters by drive.

6. **Migrate `ActiveJobRepository.GetActiveJobsByService`.** Adds pagination where there was none. Keep ServiceName + WorkerName + RunningOnly as PagedQuery filters (EqualsFilter).
   Exit: smoke -- hit `/Activity` dashboard; verify active jobs list renders.

7. **VERIFYING.** Record per-criterion evidence (13 entries). Run full contract suite.

8. **DELIVERING.** Create `Core/Querying/paged-query.feature.md` (R13 relaxes here). Populate `### Promotions`. Close.

### Seams enumerated (per `seam-verification.md`)

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| function-call: PagedQueryBuilder -> DatabaseService.ExecuteQuery | `PagedQueryBuilder.Execute` | `(sql: str, params: tuple)` -> `List[CaseInsensitiveDict]` | DatabaseService.ExecuteQuery contract: SELECT only, returns lowercase-key rows wrapped in CaseInsensitiveDict | `Tests/Contract/TestPagedQueryBuilder.py` runs builder against live DB |
| function-call: Repository -> PagedQueryBuilder | each migrated Repository | `(BaseSelect, PagedQuery, AllowedSortColumns)` -> `PagedQueryResult` | Repository receives Rows + TotalCount + echoed Page/PageSize | per-Repository contract test |
| wire-format: Controller request -> PagedQuery | Flask route (`request.args.get`) | `(page: int, pageSize: int, sortBy: str, sortOrder: str, search?: str, filterX?: str)` -> `PagedQuery` | PagedQueryConfig clamps PageSize to <= MaxPageSize; page >= 1; sortBy column rejected if not in whitelist | step 3-6 smoke tests (`/api/MediaFiles`, `/Queue`, `/ShowSettings`, `/Activity`) |
| wire-format: PagedQueryResult -> JSON response | Repository -> Controller -> jsonify | `{Rows: [...], TotalCount: int, Page: int, PageSize: int}` carried inside existing `{Success, Message, Data}` envelope | Frontend pagination controls consume `Data.TotalCount` + `Data.Rows` (existing shape preserved) | step 3-6 smoke tests confirm existing UI still works |
| state-store: PostgreSQL `RealDictCursor` -> CaseInsensitiveDict | DatabaseService.ExecuteQuery | rows with lowercase keys (`row['showname']`) | CaseInsensitiveDict allows `Row['ShowName']` and `Row['showname']` | criterion 9 contract test |
| state-store: aggregate query window-function COUNT | ShowSettingsRepository.GetShowsWithStats | `COUNT(*) OVER ()` echoed on each row OR separate COUNT query (CountStrategy enum) | TotalCount reflects HAVING-filtered + WHERE-filtered set | step 5 contract test |

### Promotions

To populate at DELIVERING.

### Verification

To populate at VERIFYING. 13 entries.

### Decisions Made

To accrete during IMPLEMENTING.
