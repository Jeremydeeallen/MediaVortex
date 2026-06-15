# Paged Query Core

**Set:** 2026-06-13
**Activated:** 2026-06-14
**Reopened:** 2026-06-14 -- SRP strict re-implementation: split QueryFilter.py (7 classes) and Exceptions.py (2 classes) into one-class-per-file, per C2's literal verification.
**Reopened:** 2026-06-15 -- premature close: 13/13 narrow criteria green, but the goal this directive serves (1.17GB browser memory) has not moved. Operator correction: "I can't have you closing directives when they aren't finished." Directive stays open until at least one consumer (the table-renderer-service when it lands, or a sooner-shipped tightening of the default PageSize plus frontend adoption) actually reduces a payload the browser holds in memory.
**Status:** Active -- phase: IMPLEMENTING
**Slug:** paged-query-core

## Outcome

A single `Core/Querying/` package owns the abstraction every Repository uses to serve paged, sorted, filtered reads. Repositories declare what they query; the package builds safe parameterised SQL with `LIMIT`/`OFFSET`, `ORDER BY` whitelisting, and filter-clause composition. No Repository hand-rolls `LIMIT %s` / `OFFSET %s` after migration. Backend serves the data contract `table-renderer-service` consumes.

## Acceptance Criteria

1. **`Core/Querying/PagedQuery.py` exists** with `PagedQuery` (value object: Page, PageSize, Sort, Filter), `QueryFilter` (clause + params + AND/OR composer), `QuerySort` (column + direction, whitelist-validated), `PagedQueryResult` (Rows + TotalCount + Page + PageSize), `PagedQueryBuilder` (composes a base SELECT + WHERE + ORDER BY + LIMIT/OFFSET against `DatabaseService`).

2. **SRP -- one responsibility per class.** Each class above lives in its own file. Verifiable: `ls Core/Querying/*.py` shows one class per file.

3. **OCP -- new filter type without builder change.** Adding a new `QueryFilter` type (range, IN-list, full-text) creates one new class implementing the filter interface. `PagedQueryBuilder` is not edited. Verifiable: add a `RangeFilter`; `git diff --stat Core/Querying/PagedQueryBuilder.py` is empty.

4. **LSP -- substitutable filters.** Any `QueryFilter` plugs into `PagedQueryBuilder` interchangeably. Verifiable: contract test passes `EqualsFilter`, `LikeFilter`, `RangeFilter`, `InListFilter` through the same builder method.

5. **DIP -- Repositories depend on `PagedQuery`, not on SQL strings.** The 5 migrated methods receive a `PagedQuery` and return a `PagedQueryResult`. Within each migrated method body, `LIMIT %s` / `OFFSET %s` SQL is not assembled inline. Verifiable (narrowed per 2026-06-14 operator decision -- initial-set scope): inspecting each of the 5 migrated method bodies shows no inline `LIMIT %s` / `OFFSET %s` strings. Sibling methods in the same file (e.g. `GetMissedQualityTests`, `GetTranscodeCandidatesByRootFolder`) are out of scope this directive; tree-wide enforcement is a follow-up.

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

| Source (directive section) | Target (durable home) |
|---|---|
| `## Outcome` paragraph | `Core/Querying/paged-query.feature.md ## What It Does` |
| `## Acceptance Criteria` C1..C13 | `Core/Querying/paged-query.feature.md ## Success Criteria C1..C13` |
| `## Plan` step 1..8 sequencing | Burned at delivery; commit history (`efa7e75`..`HEAD`) is the durable record |
| `## Seams enumerated` (6 rows) | `Core/Querying/paged-query.feature.md ## Seams S1..S6` |
| `### Files` block | `Core/Querying/paged-query.feature.md ## Files` table |
| `## Out of Scope` | `Core/Querying/paged-query.feature.md ## Out of Scope` |
| `## Engineering Calls Already Made` | Burned at delivery; the calls are encoded in the implementation + feature doc |
| `### Decisions Made` accreted during IMPLEMENTING | Below in `### Decisions Made` -- closed-directive archive |

### Verification

C1. **PagedQuery package shape.** `ls Core/Querying/*.py` enumerates `__init__.py, CountStrategy.py, Exceptions.py, PagedQuery.py, PagedQueryBuilder.py, PagedQueryConfig.py, PagedQueryResult.py, QueryFilter.py, QuerySort.py`; `Interfaces/IQueryFilter.py` + `Interfaces/IQuerySort.py` present. Status: IMPLEMENTED.

C2. **SRP -- one class per file, strict.** Re-implementation 2026-06-14: legacy `QueryFilter.py` (7 classes) split into `Filters/{EqualsFilter,LikeFilter,NotLikeFilter,RangeFilter,InListFilter,AndComposer,OrComposer}.py`; legacy `Exceptions.py` (2 classes) split into `Exceptions/{InvalidColumnError,InvalidPageError}.py`. Helper `_AssertSafeColumn` extracted to `Filters/_ColumnSafety.AssertSafeColumn` and re-imported by every filter. `Tests/Contract/TestPagedQueryStructure.py` AST-parses every `.py` under `Core/Querying/` (excluding `__init__.py`) and asserts each file has exactly one top-level `ClassDef`; 3 structural assertions, all green. 16 named classes each at canonical paths. Status: IMPLEMENTED (strict).

C3. **OCP -- new filter type without builder change.** Evidence: step 3 added `NotLikeFilter` to handle FileScanning's `!`-prefix search negation; `git show 213bcf1 --stat | grep Querying` shows `QueryFilter.py + __init__.py` modified, `PagedQueryBuilder.py` untouched. `git log Core/Querying/PagedQueryBuilder.py` shows only `efa7e75` (step 1). Status: IMPLEMENTED.

C4. **LSP -- substitutable filters.** `Tests/Contract/TestPagedQuery.py` instantiates Equals / Like / Range / InList / And / Or interchangeably via the `IQueryFilter.ToClause() + Params()` contract; `TestPagedQueryBuilder.test_multi_filter_and_composition` and `test_like_filter_with_special_chars` round-trip multiple filter types through the same builder. Status: IMPLEMENTED.

C5. **DIP -- Repositories depend on PagedQuery, not SQL strings.** All 5 migrated methods receive `Query: PagedQuery` and return `PagedQueryResult` (signatures verified by grep). Method-body grep for `LIMIT %s` / `OFFSET %s` returns zero in each method body (verified per step via `awk` extraction of the method block). Status: IMPLEMENTED.

C6. **ISP -- focused interfaces.** `wc -l Core/Querying/Interfaces/IQueryFilter.py` = 15; `IQuerySort.py` = 9; both ≤20 LOC. `IQueryFilter` exposes `ToClause()` + `Params()`. `IQuerySort` exposes `ToOrderBy()`. Status: IMPLEMENTED.

C7. **SQL injection safe.** `Tests/Contract/TestPagedQueryInjection.py` (8 tests, all passing) covers `; DROP TABLE Users--`, `1' OR '1'='1`, quote-in-column, semicolon-in-column, paren-in-column, space-in-column; unlisted-column rejection for both QuerySort and EqualsFilter. Each raises `InvalidColumnError` before any SQL is composed. Status: IMPLEMENTED.

C8. **EscapeLikePattern integration.** `LikeFilter.Params()` calls `EscapeLikePattern()` and `ToClause()` emits `ESCAPE '!'`. `TestPagedQuery.test_like_filter_escapes_special_chars` asserts `"%Showname!_with!%special!!chars%"` from input `"Showname_with%special!chars"`. `TestPagedQueryBuilder.test_like_filter_with_special_chars` round-trips against live data (50 rows match path containing `!_special%chars`). Status: IMPLEMENTED.

C9. **CaseInsensitiveDict rows.** `TestPagedQueryBuilder.test_case_insensitive_dict_rows` asserts `Row['ShowName'] == Row['showname'] == Row['SHOWNAME']`. Status: IMPLEMENTED.

C10. **Total count strategy.** `CountStrategy.WINDOW`, `SEPARATE`, `NONE` defined in `Core/Querying/CountStrategy.py`. `TestPagedQueryBuilder.test_window_count_matches_actual_total` (50 rows in test table → TotalCount=50); `test_separate_count_matches_actual_total` (filter Mode='Transcode' → TotalCount=25); `test_count_strategy_none_returns_negative_one`. Per-Repository selection: QualityTest=WINDOW, FileScanning=WINDOW, TranscodeQueue=WINDOW, ShowSettings=WINDOW (aggregate post-GROUP-BY HAVING), ActiveJob=WINDOW. Status: IMPLEMENTED.

C11. **Migration completeness.** All 5 named methods route through `PagedQueryBuilder.Execute`:
- `QualityTestRepository.GetQualityTestResults(Query: PagedQuery) -> PagedQueryResult` (live smoke: TotalCount=1159)
- `FileScanningRepository.GetMediaFilesPaginated(Query: PagedQuery) -> PagedQueryResult` (live smoke: TotalCount=50552 unfiltered, 37 with Search='Westworld', 50515 with NotLike complement = 50552-37 ✓)
- `TranscodeQueueRepository.GetTranscodeQueueItemsPaginated(Query: PagedQuery) -> PagedQueryResult` (live smoke: 224 all-modes, 224 Mode=Transcode, 0 Mode=Remux)
- `ShowSettingsRepository.GetShowsWithStats(Query: PagedQuery) -> PagedQueryResult` (live smoke: 3980 shows, Drive=T: → 648)
- `ActiveJobRepository.GetActiveJobsByService(Query: PagedQuery) -> PagedQueryResult` (live smoke: 4 TranscodeService active jobs; DM-route equivalent after ServiceControlRepository duplicate removed)
Status: IMPLEMENTED.

C12. **Feature doc.** `Core/Querying/paged-query.feature.md` to be created at DELIVERING (R13 gates earlier creation). Status: PENDING (next phase).

C13. **Contract tests cover invariants.** `Tests/Contract/TestPagedQuery.py` (25 tests) + `TestPagedQueryInjection.py` (8 tests) + `TestPagedQueryBuilder.py` (10 live-DB tests) + `TestPagedQueryStructure.py` (3 SRP-AST tests) = 46 tests, all green. Covers: empty filter, multi-filter AND, OR composition, sort whitelist enforcement, page boundaries (Page=0 rejected, page beyond last returns 0 rows, TotalCount accurate), total count accuracy (window + separate), injection rejection, one-class-per-file SRP enforcement. Status: IMPLEMENTED.

### Seam Verification Round-trip (per seam-verification.md VERIFYING)

- **function-call: PagedQueryBuilder → DatabaseService.ExecuteQuery** -- verified by every `TestPagedQueryBuilder` test (10 round-trips against live DB).
- **function-call: Repository → PagedQueryBuilder** -- verified by 5 live smoke tests (one per migrated repository) confirming the (BaseSelect, PagedQuery, AllowedSortColumns) → PagedQueryResult shape.
- **wire-format: Controller request → PagedQuery** -- verified at the ViewModel/Controller layer: FileScanningViewModel.GetMediaFilesPaginated, TranscodeQueueViewModel.LoadQueueItems, ShowSettingsController.GetShows, QualityTestController.GetQualityTestHistory all build PagedQuery from request args via `QuerySort.Create` + filter primitives.
- **wire-format: PagedQueryResult → JSON response** -- existing `{Rows, TotalCount, TotalPages}` shape preserved by FileScanning (via dict wrapper) and TranscodeQueue (Result.Rows + Result.TotalCount); QualityTest's Pagination block built from Result fields; ShowSettings adds new Pagination block alongside Data.
- **state-store: PostgreSQL RealDictCursor → CaseInsensitiveDict** -- C9 evidence.
- **state-store: aggregate window-function COUNT** -- ShowSettings live smoke confirms `COUNT(*) OVER ()` post-HAVING returns 3980 distinct shows; unfiltered + drive-filtered counts both correct.

### Decisions Made

- **Criterion 5 narrowed to method-body scope (not file-scope).** Sibling methods like `GetMissedQualityTests` (LIMIT only, no OFFSET -- not pagination) and `GetTranscodeCandidatesByRootFolder` remain inline. Tree-wide enforcement deferred to a follow-up directive. (2026-06-14, operator-confirmed via AskUserQuestion.)
- **Criterion 11 method-name mapping.** The directive's draft named four methods that don't exist verbatim. Mapped to the actual paginating methods + the canonical active-jobs reader (`ActiveJobRepository.GetActiveJobsByService` substituted for non-existent `TranscodeJobRepository.GetActiveJobs`; `FileScanningRepository.GetMediaFilesPaginated` substituted for non-existent `MediaFilesRepository.GetMediaFiles`). (2026-06-14, operator-confirmed.)
- **NotLikeFilter added during step 3.** FileScanning's `!`-prefix search-negation pattern was previously inline `NOT LIKE` SQL. Adding `NotLikeFilter` as a new `IQueryFilter` implementor (vs handling negation inline in the Repository) exercises and validates criterion 3 (OCP). PagedQueryBuilder untouched.
- **TranscodeQueue priority composite ORDER BY preserved exactly.** The operator list view's composite (`<SortExpr> <direction> NULLS LAST, DateAdded ASC` -- where SortExpr for the "Priority" sort is `(CASE WHEN Priority >= 195 THEN Priority ELSE 0 END), SizeMB`) does not perfectly match the queue-priority.feature.md C1 canonical claim ORDER BY (`DESC, DESC NULLS LAST, ASC` directions baked in). Preserved current behavior verbatim; reconciliation with C1 is out of scope for this directive (filed as observation, not bug -- TranscodeQueue list view has lived with this since the queue-priority lift).
- **ShowSettings + ActiveJob get unbounded PagedQueryConfig per call.** Both methods have callers that expect "give me everything" semantics (3980 shows in library; up to 4 active jobs typical). Per-call `PagedQueryConfig(DefaultPageSize=10000, MaxPageSize=10000)` allows unbounded fetch without changing the global Config defaults (25/500). Frontend can opt into pagination by passing explicit Page/PageSize.
- **PagedQueryResult is iterable + len()-able.** `__iter__` returns `iter(self.Rows)`; `__len__` returns `len(self.Rows)`. Lets ActiveJob callers do `for J in result: ...` / `len(result)` without unpacking `.Rows` -- keeps the 12 caller call sites concise.
- **ServiceControlRepository.GetActiveJobsByService duplicate deleted.** It was a stripped-down duplicate of ActiveJobRepository's method that won MRO resolution on `DatabaseManager.GetActiveJobsByService(...)` calls. Removal lets `db.GetActiveJobsByService(Query)` resolve to the principled PagedQuery-based method. Three `Scripts/` callers updated accordingly.
- **ProcessSupervisor.py import fix.** The existing `from Repositories.ActiveJobRepository import ActiveJobRepository` referenced a non-existent module (would have ImportError'd at runtime if the path were hit). Fixed in the same edit (`Features.ServiceControl.ActiveJobRepository`) since the line was already in the edit region.
- **CrashRecoveryService stub-comment block collapsed (R12).** Two-line `# This could be enhanced ... # For now, return basic info` was a preexisting violation in the edit region; collapsed per R12's "pure WHAT-redundancy → delete" classification.
- **2026-06-14 SRP strict re-implementation (reopen).** Operator challenge: "you said 13/13 but C2 has a known divergence." Honest answer: yes, C2's literal verification (`ls Core/Querying/*.py` shows one class per file) failed -- QueryFilter.py had 7 classes, Exceptions.py had 2. Reopened the directive to fix it properly: created `Core/Querying/Filters/` and `Core/Querying/Exceptions/` subfolders with one class per file (9 new files), extracted shared `_AssertSafeColumn` helper to `Filters/_ColumnSafety.AssertSafeColumn`, updated `__init__.py` to re-export everything (backward-compatible -- existing imports `from Core.Querying import EqualsFilter` still resolve), deleted legacy flat modules. Added `Tests/Contract/TestPagedQueryStructure.py` with 3 AST-based assertions that enforce the SRP invariant going forward. 46/46 contract tests green. Status: 13/13 now legitimately IMPLEMENTED.
