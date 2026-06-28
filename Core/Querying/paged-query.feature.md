# Paged Query Core

**Slug:** paged-query
**API Version:** 1.0.0
**Status:** COMPLETE

## What It Does

`Core/Querying/` is the abstraction every Repository uses to serve paged, sorted, filtered reads. Repositories declare what they query (a `SELECT ... FROM ...` template plus optional `GROUP BY` / `HAVING`); the package builds safe parameterised SQL with `LIMIT` / `OFFSET`, `ORDER BY` whitelisting, and filter-clause composition. No Repository in the migration set hand-rolls `LIMIT %s` / `OFFSET %s` after this contract lands.

Backend serves the data contract `table-renderer-service` (sequence position 5 in the perfect-codebase set) will consume.

## Workflows

| #  | Operator action / system event | Surface element | Handler | Backing class.method |
|----|--------------------------------|-----------------|---------|----------------------|
| W1 | View `/MediaFiles` page | Pagination + sort + search controls | `GET /api/MediaFiles` | `Features/FileScanning/FileScanningRepository.GetMediaFilesPaginated` |
| W2 | View `/TranscodeQueue` page | Tabs (Transcode / Remux / AudioFix) + sort + pagination | `GET /api/TranscodeQueue` | `Features/TranscodeQueue/TranscodeQueueRepository.GetTranscodeQueueItemsPaginated` |
| W3 | View `/Work/<bucket>` series list | Drive filter + sort | `GET /api/WorkBucket/Shows` | `Features/WorkBucket/WorkBucketRepository.GetShowsWithStats` |
| W4 | View VMAF results history | Pagination | `GET /api/QualityTest/History` | `Features/QualityTesting/QualityTestRepository.GetQualityTestResults` |
| W5 | Worker / supervisor reads currently-running jobs by service | n/a (internal) | direct call | `Features/ServiceControl/ActiveJobRepository.GetActiveJobsByService` |

## Success Criteria

C1. **Package shape.** `Core/Querying/` exists with `PagedQuery` (value object: Page, PageSize, Sort, Filters), `QueryFilter` family + composers, `QuerySort` (whitelist + direction validation), `PagedQueryResult` (Rows + TotalCount + Page + PageSize + TotalPages + iterable), `PagedQueryBuilder` (composes base SELECT + WHERE + GROUP BY + HAVING + ORDER BY + LIMIT/OFFSET against `DatabaseService`), `PagedQueryConfig` (PageSize clamp defaults), `CountStrategy` enum (WINDOW / SEPARATE / NONE), `Exceptions` (InvalidColumnError, InvalidPageError).

C2. **SRP -- one class per file, strict.** Every class in `Core/Querying/` lives in its own file. Verifiable: `Tests/Contract/TestPagedQueryStructure.py` parses every `.py` under `Core/Querying/` (excluding `__init__.py`) via AST and asserts each file has exactly one top-level `ClassDef`. The 16 named classes (PagedQuery, PagedQueryBuilder, PagedQueryConfig, PagedQueryResult, QuerySort, EqualsFilter, LikeFilter, NotLikeFilter, RangeFilter, InListFilter, AndComposer, OrComposer, InvalidColumnError, InvalidPageError, IQueryFilter, IQuerySort) each have a dedicated file at their canonical path.

C3. **OCP -- new filter type without builder change.** Adding a new `IQueryFilter` implementor (e.g. `NotLikeFilter`) creates one new class. `PagedQueryBuilder.py` is not edited.

C4. **LSP -- substitutable filters.** Any `IQueryFilter` plugs into `PagedQueryBuilder.Execute` interchangeably via `ToClause()` + `Params()`.

C5. **DIP -- Repositories depend on PagedQuery, not on SQL strings.** Each Repository method in the migration set receives a `PagedQuery` and returns a `PagedQueryResult`. The method body assembles no inline `LIMIT %s` / `OFFSET %s` SQL.

C6. **ISP -- focused interfaces.** `IQueryFilter` exposes `ToClause()` + `Params()` only. `IQuerySort` exposes `ToOrderBy()` only. Each interface file ≤ 20 LOC.

C7. **SQL injection safe.** Every column name (sort + filter) is validated against a per-query whitelist supplied by the Repository. Injection attempts (`; DROP TABLE`, `1' OR '1'='1`, quote-in-column, semicolon-in-column, paren-in-column, space-in-column) raise `InvalidColumnError` before any SQL is composed.

C8. **EscapeLikePattern integration.** `LikeFilter` and `NotLikeFilter` automatically apply `EscapeLikePattern()` and emit `ESCAPE '!'`. A path containing `%`, `_`, `!` matches literally.

C9. **CaseInsensitiveDict rows.** `PagedQueryResult.Rows` carries the project's existing `CaseInsensitiveDict`. Both `Row['ShowName']` and `Row['showname']` resolve identically.

C10. **Total count strategy.** `PagedQueryResult.TotalCount` is filled via a window function `COUNT(*) OVER ()` in the same query (WINDOW strategy) or a separate `COUNT(*)` query (SEPARATE strategy) or skipped (NONE returns `-1`). Strategy is selected per Repository via the `CountStrategy` enum. Returned count matches actual filtered row count.

C11. **Migration completeness (initial set).** Per the 2026-06-14 operator decision, the initial migration set is the 5 methods named in the directive Status block. Each accepts `PagedQuery` and returns `PagedQueryResult`.

C12. **Feature doc owns the contract.** This file.

C13. **Contract tests cover invariants.** `Tests/Contract/TestPagedQuery.py` + `TestPagedQueryInjection.py` + `TestPagedQueryBuilder.py` -- 43 tests in total -- cover: empty filter, multi-filter AND, OR composition, sort whitelist enforcement, page boundary (Page=0 rejected; page beyond last returns 0 rows + TotalCount=0), total count accuracy (window and separate), injection rejection.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `PagedQueryBuilder.Execute` → `DatabaseService.ExecuteQuery` | `Core.Querying.PagedQueryBuilder` | `(sql: str, params: tuple)` → `List[CaseInsensitiveDict]` | DatabaseService.ExecuteQuery contract: SELECT only, returns lowercase-key rows wrapped in `CaseInsensitiveDict` | `Tests/Contract/TestPagedQueryBuilder.py` |
| S2 | Repository → `PagedQueryBuilder.Execute` | each migrated Repository (Quality / FileScanning / TranscodeQueue / WorkBucket / ActiveJob) | `(RowsSelect, Query, StaticWhere?, GroupBy?, Having?, OrderByOverride?, CountStrategyChoice, CountSelect?)` → `PagedQueryResult` | Repository receives Rows + TotalCount + echoed Page/PageSize | per-Repository contract test (smoke) |
| S3 | ViewModel / Controller request → `PagedQuery` | Flask `request.args.get`, ViewModel builder | `(Page, PageSize, Sort, Filters)` value object; `QuerySort.Create` clamps to whitelist; `PagedQueryConfig.ClampPageSize` clamps to MaxPageSize | Whitelist-validated `QuerySort` + filter primitives; unknown columns raise `InvalidColumnError` | injection tests + ViewModel smoke |
| S4 | `PagedQueryResult` → JSON response | Repository → Controller → `jsonify` | `{Rows: [...], TotalCount: int, Page: int, PageSize: int, TotalPages: int}` inside the existing `{Success, Message, Data}` envelope (per-controller) | Frontend pagination controls consume the existing shape; new Pagination blocks alongside Data where added | controller-level edits verified via response shape |
| S5 | `RealDictCursor` → `CaseInsensitiveDict` | `DatabaseService.ExecuteQuery` | rows with lowercase keys; `_parse_select_columns` relocates to PascalCase aliases | `Row['ShowName'] == Row['showname']` | C9 contract test |
| S6 | Aggregate window-function COUNT | `WorkBucketRepository.GetShowsWithStats` | `COUNT(*) OVER ()` evaluated after `GROUP BY` + `HAVING` | `__TotalCount` column on each grouped row equals distinct post-HAVING group count | live smoke 3980 shows total, 648 Drive=T: |

## Files

| File | Role |
|------|------|
| `Core/Querying/__init__.py` | Package exports |
| `Core/Querying/PagedQuery.py` | Value object: Page, PageSize, Sort, Filters |
| `Core/Querying/PagedQueryBuilder.py` | SQL assembly: WHERE / GROUP BY / HAVING / ORDER BY / LIMIT / OFFSET; CountStrategy dispatch |
| `Core/Querying/PagedQueryConfig.py` | Default + max page-size clamp |
| `Core/Querying/PagedQueryResult.py` | Rows + TotalCount + Page + PageSize; iterable + len()-able |
| `Core/Querying/QuerySort.py` | Whitelist-validated sort column + direction + NULLS LAST |
| `Core/Querying/CountStrategy.py` | WINDOW / SEPARATE / NONE enum |
| `Core/Querying/Filters/__init__.py` | Filter package exports |
| `Core/Querying/Filters/_ColumnSafety.py` | `AssertSafeColumn` -- identifier-charset + whitelist guard shared by every filter |
| `Core/Querying/Filters/EqualsFilter.py` | `Column = %s` / `Column IS NULL` |
| `Core/Querying/Filters/LikeFilter.py` | `LOWER(Column) LIKE LOWER(%s) ESCAPE '!'` with auto EscapeLikePattern |
| `Core/Querying/Filters/NotLikeFilter.py` | `LOWER(Column) NOT LIKE LOWER(%s) ESCAPE '!'` |
| `Core/Querying/Filters/RangeFilter.py` | `Column >= %s [AND Column <= %s]` |
| `Core/Querying/Filters/InListFilter.py` | `Column IN (%s, %s, ...)` |
| `Core/Querying/Filters/AndComposer.py` | `(F1 AND F2 AND ...)` |
| `Core/Querying/Filters/OrComposer.py` | `(F1 OR F2 OR ...)` |
| `Core/Querying/Exceptions/__init__.py` | Exception package exports |
| `Core/Querying/Exceptions/InvalidColumnError.py` | Raised on injection / whitelist miss |
| `Core/Querying/Exceptions/InvalidPageError.py` | Raised on Page < 1 / PageSize < 1 |
| `Core/Querying/Interfaces/__init__.py` | Interface package exports |
| `Core/Querying/Interfaces/IQueryFilter.py` | `ToClause()` + `Params()` ABC |
| `Core/Querying/Interfaces/IQuerySort.py` | `ToOrderBy()` ABC |
| `Tests/Contract/TestPagedQuery.py` | Value-object + filter + sort + config + result contract tests |
| `Tests/Contract/TestPagedQueryInjection.py` | SQL-injection rejection tests |
| `Tests/Contract/TestPagedQueryBuilder.py` | Live-DB builder round-trip tests |
| `Tests/Contract/TestPagedQueryStructure.py` | SRP one-class-per-file AST assertion (C2) |

## Out of Scope

- Frontend table rendering (see `table-renderer-service.md` -- sequence position 5).
- Writes (INSERT/UPDATE/DELETE) -- this is a read-side abstraction.
- Full-text search ranking.
- Cursor-based pagination (offset/limit only for v1).
- Tree-wide grep enforcement -- only the 5 migrated methods are gated by C5 in v1; sibling methods in the same files (e.g. `GetMissedQualityTests`) defer to a follow-up directive.
