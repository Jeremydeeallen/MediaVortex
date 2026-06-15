# Table Renderer Service

**Set:** 2026-06-13
**Activated:** 2026-06-15 -- operator mandate: "Spin up agents and figure this out. Fix it, document it, if we use the same pattern anywhere else fix those too. Memory footprint should be much smaller and the pages should load near instantly. Best practices for datasets, SOLID, industry standards. Perfect implementation across the board."
**Status:** Active -- phase: IMPLEMENTING
**Slug:** table-renderer-service

## Outcome

Every tabular surface in the WebService (Activity, Queue, Stats, Operations, Optimization, SQLQueries, ShowSettings, FailedJobs, future tables) renders through a single in-house JS service whose decomposition follows SOLID. Pages declare table shape via configuration; rendering, sorting, filtering, pagination, virtualization, and inline editing are owned by composable controllers. Browser memory for a 4000+ row dataset stays under 200MB. Adding a new table to a page is a config-only change with zero edits to the renderer service.

## Acceptance Criteria

1. **Memory bound.** `/ShowSettings` loaded against a 4000+ row `MediaFiles` dataset consumes <200MB browser memory (Edge Task Manager process working set, fresh tab). Verifiable: open page, measure.

2. **Single renderer dependency.** Every `Templates/*.html` page that renders a table imports `TableRenderer` and uses no jQuery DOM mutation for sort, filter, paginate, or row rendering. Verifiable: `grep -rE "\.html?\.|\$\(['\"]#[A-Za-z]+TableBody['\"]\)\.html\(" Templates/` returns zero matches inside table-rendering code paths.

3. **OCP -- new column type without renderer change.** Adding a new column type (example: a progress-bar column) requires creating one `CellRenderer` subclass and registering it. No file in `static/js/TableRenderer/` core is edited. Verifiable: add a `ProgressBarCellRenderer`, ship it, `git diff --stat static/js/TableRenderer/` shows only the new file.

4. **LSP -- DataSource substitution.** Swapping a table's `ClientArrayDataSource` for a `ServerPagedDataSource` requires no changes to page code beyond the DataSource constructor argument. Verifiable: migrate one table from client to server paging; diff shows only the DataSource instantiation line changed.

5. **DIP -- service has no domain knowledge.** No file under `static/js/TableRenderer/` references MediaVortex domain terms (`Show`, `Profile`, `TranscodeJob`, `Worker`, `MediaFile`, etc.). Verifiable: grep returns zero matches.

6. **SRP -- one responsibility per controller.** Each of `TableRenderer`, `DataSource`, `SortController`, `FilterController`, `PaginationController`, `CellRenderer`, `InlineEditor`, `Virtualizer` is in its own file and exposes a single public surface. Verifiable: one class per file; each file has one `export class`.

7. **Inline editor decoupling.** The per-row profile `<select>` problem (`ShowSettings.html:713-717`) is replaced by a single shared editor opened on cell activation. The Library table on `/ShowSettings` contains zero per-row `<select>` elements at rest. Verifiable: `document.querySelectorAll('#LibraryTableBody select').length === 0` until a cell is clicked.

8. **Virtualization above threshold.** Tables with row count >500 use `Virtualizer`; only visible rows + a small buffer exist in the DOM. Verifiable: load a 4000-row table; `document.querySelectorAll('#LibraryTableBody tr').length < 150`.

9. **Server-paged search.** `/api/ShowSettings/Shows` accepts `?q=`, `?sort=`, `?page=`, `?pageSize=` and returns paged results with a total count. Backend filter pushes to SQL, not in-Python. Verifiable: hit endpoint with `?q=breaking&pageSize=20`; response contains <=20 rows and a total.

10. **Contract test coverage.** `Tests/Static/TestTableRenderer*` covers each controller's invariants (sort stability, filter idempotence, pagination boundaries, virtualization buffer math, inline-edit roundtrip). Verifiable: tests pass; uncovered controllers fail CI.

11. **Migration completeness.** Every existing page that renders a multi-column data table is migrated onto `TableRenderer`. Migrated pages: `/Activity`, `/TranscodeQueue`, `/Stats`, `/Operations`, `/Optimization`, `/SQLQueries`, `/ShowSettings`, `/FailedJobs`. Single-row status panels and forms are out of scope. Verifiable: each page in the list uses `TableRenderer`; none retain ad-hoc table-rendering JS.

12. **Feature doc owns the contract.** `Features/SharedTable/shared-table-renderer.feature.md` exists with Workflows (`W1..Wn`), Seams (`S1..Sn`), Success Criteria (`C1..Cn`), and Status. Code files carry `# see shared-table-renderer.S<N>` anchors at controller boundaries.

13. **ISP -- focused interfaces.** Pages that do not paginate do not depend on pagination API; pages that do not filter do not depend on filter API. Concretely: `ISortable`, `IPaginatable`, `IFilterable`, `IEditable` are separate interfaces, and `TableRenderer` accepts the controllers that match its declared capability set. Verifiable: instantiate a read-only non-paginated table; runtime exposes no `.NextPage()` / `.SetFilter()` methods on the public surface.

14. **Dependency direction.** `TableRenderer` core does not import any controller concrete; controllers do not import `TableRenderer`; both depend on shared interfaces in `static/js/TableRenderer/Interfaces/`. Verifiable: `grep -E "^import .* from '.*TableRenderer\\.js'" static/js/TableRenderer/{Sort,Filter,Pagination,Virtualizer,Cell,Inline}*.js` returns zero matches.

15. **Observable event contract.** `TableRenderer` exposes `Subscribe(EventName, Handler)` for `RowClicked`, `CellEdited`, `SortChanged`, `FilterChanged`, `PageChanged`, `SelectionChanged`. Pages consume events via subscription, not callback config. Verifiable: page code uses `Table.Subscribe('CellEdited', ...)`; no `onCellEdited:` config field exists.

16. **Backend paging abstraction.** A new `Core/Querying/PagedQuery.py` provides `PagedQuery`, `QueryFilter`, `QuerySort`, `PagedQueryBuilder`, `PagedQueryResult`. Every Repository method serving a paged endpoint routes through it -- no hand-rolled `LIMIT`/`OFFSET` in Repository SQL after migration. Verifiable: `grep -rE "LIMIT %s|OFFSET %s" Features/` returns zero matches outside `Core/Querying/`. Depends on the `paged-query-core` directive landing first.

17. **CSS ownership.** `static/css/TableRenderer.css` exists and owns every selector that styles a `TableRenderer`-rendered table. No page-level template defines table CSS for migrated tables. Verifiable: grep `Templates/*.html` for `<style>` rules targeting `.tr-table`, `.tr-row`, `.tr-cell` -- returns zero matches.

18. **Accessibility.** A `TableRenderer`-rendered table is keyboard-navigable (arrow keys, Tab, Enter to edit, Esc to cancel), uses semantic `<table>` with `<thead>`/`<tbody>`/`<th scope="col">`, exposes `aria-sort` on sortable headers, and announces filter/page changes via `aria-live`. Verifiable: axe-core or equivalent reports zero violations on `/ShowSettings`.

19. **API stability commitment.** `Features/SharedTable/shared-table-renderer.feature.md` declares a SemVer-style `**API Version:** X.Y.Z` field. Breaking changes to the public surface bump major and require a migration note for each consuming page. Verifiable: file contains the field; CI check (added with this directive) refuses a major bump without a corresponding `### Migration Notes` block.

20. **Controllers are unit-testable in isolation.** Each controller accepts its DataSource via constructor injection (no inner `new`), enabling stub DataSources in tests. Verifiable: each `Test*Controller.js` uses a `StubDataSource` and exercises the controller without DOM.

## Out of Scope

- Failure-accounting directive work (currently VERIFYING -- this directive queues behind it).
- Form rendering, modal rendering, notification UI, single-row status panels (each has its own backlog directive).
- The shared AJAX/HTTP client wrapper (see `ajax-client-service.md`).
- The client-side logging client (see `client-logging-service.md`).
- Replacing jQuery globally. `TableRenderer` is jQuery-free internally; pages that already use jQuery for non-table interactions are not touched here.
- Building a charting library or visualization framework.

## Sequencing

This directive depends on `paged-query-core` landing first (C16 requires it). Order of execution across the perfect-codebase directive set:

1. `paged-query-core` -- backend Repository paging primitive (precondition for C16 here).
2. `ajax-client-service` -- HTTP wrapper used by every page incl. table data sources.
3. `client-logging-service` -- so the renderer can log errors consistently.
4. `notification-service` -- the renderer's inline edit failure path emits notifications.
5. **this directive** -- table renderer.
6. `form-renderer-service` -- shares the `InlineEditor` pattern.
7. `modal-service` -- last (least coupled to the rest).

## Constraints

- No vendor table library (DataTables.js, AG Grid, ag-grid-community, Tabulator, etc.). SOLID-purity over pragmatism: the codebase owns the abstraction it depends on.
- PascalCase across JS class names, file names, method names, and config keys -- per CLAUDE.md.
- Each controller class lives in its own file (R8 single-responsibility surface).
- DataSource implementations expose an async-uniform interface so client/server sources are LSP-substitutable.
- No hardcoded thresholds in the renderer (virtualization row threshold, default page size, debounce intervals). All come from `TableRendererConfig`.
- Configuration over inheritance for column definitions -- a column is a config object, not a subclass.

## Escalation Defaults

- Tradeoff between simplicity and OCP -> OCP. This is the perfect-codebase directive; declarative beats imperative when in conflict.
- Tradeoff between bundle size and decomposition -> decomposition. Code splitting handles bundle size; SOLID does not bend for it.
- Risk tolerance: low for the renderer service itself (covered by tests); medium for per-page migrations (each migration is its own commit, verified live before next).

## Engineering Calls Already Made

- In-house renderer, not DataTables.js. Decision rationale: DataTables couples the codebase to a vendor concrete and violates DIP; we own our abstractions.
- ShowSettings is the proof-of-concept migration. It has the worst current symptom (1.1MB JSON -> 1.5GB browser memory) and exercises every feature (filter, sort, paginate, inline edit).
- Backend endpoints gain optional paging/sort/filter query params; existing callers without params continue to receive the full unpaged result during transition. Removal of unpaged-mode is a follow-up directive.

## Plan Supplement (2026-06-15 audit)

Antipattern audit confirmed by `Explore` agent + curl payload measurements:

| File | Render | Dataset | Risk |
|---|---|---|---|
| ShowSettings.html `RenderLibrary()` 666-734 | 3980 shows × 26-option `<select>` per row = ~131k DOM elements | 3980 | **CRITICAL** -- POC target |
| ShowSettings.html `RenderSearchTable()` 549-585 | 3980 rows eagerly even with empty search | 3980 | **CRITICAL** -- POC target |
| Queue.html QT queue render 741-781 | 1159 items full-render every 3s poll | 1159 | **CRITICAL** -- second migration |
| Queue.html `updateQueueTable()` 333-388 | already paginated (25/page) but on 30s poll | 224 | MODERATE -- migrate for consistency |
| Activity.html `RenderWorkers()` 928-954 | rebuilds every 2s; card-based | 5-10 | MODERATE -- migrate |
| FailedJobs.html `renderRows()` 117-137 | already paginated (100/page) | <100/page | MIGRATE for consistency |
| Status.html `RenderCoreTemperatures()` 492-532 | createElement loop | 16-32 cores | MIGRATE for consistency |
| Operations.html `DisplayResults()` 341-408 | createElement | <50 | MIGRATE for consistency |
| SQLQueries.html `DisplayResults()` 270-408 | createElement | variable | MIGRATE for consistency |

Curl payloads on /ShowSettings page load total ~1.23 MB (Shows endpoint 1.14 MB dominates); rendered into ~167k DOM elements per first paint. Backend not at fault (paged-query-core delivered the primitive); frontend amplification is the leak driver.

### Sequencing

1. **Phase 1 (Foundations)** -- create `static/js/TableRenderer/` package (Interfaces, controllers, data sources, virtualizer, cell renderer, inline editor, config). Contract tests for each.
2. **Phase 2 (POC migration)** -- ShowSettings Library + Search Cards as proof: lazy profile dropdown, 50-row virtualization, server-side paged Shows endpoint. **Operator measures Edge browser memory before/after.**
3. **Phase 3 (CRITICAL migration)** -- Queue.html QT queue (eliminate 3s eager re-render).
4. **Phase 4 (MODERATE migration)** -- Queue main, Activity workers, FailedJobs, Status, Operations, SQLQueries, Optimization.
5. **Phase 5 (Backend sweep)** -- ensure every migrated page's endpoint accepts paged params via paged-query-core.
6. **Phase 6 (Promotion)** -- create `Features/SharedTable/shared-table-renderer.feature.md` with W/S/C.

## Status

Active -- phase: NEEDS_PLAN. Activated 2026-06-15 by operator escalation.

### Files

```
static/js/TableRenderer/TableRenderer.js              -- CREATE: orchestrator; owns DOM mutation only
static/js/TableRenderer/DataSource.js                 -- CREATE: abstract DataSource interface
static/js/TableRenderer/ClientArrayDataSource.js      -- CREATE: in-memory array implementation
static/js/TableRenderer/ServerPagedDataSource.js      -- CREATE: server-side paged implementation
static/js/TableRenderer/ColumnDefinition.js           -- CREATE: declarative column config
static/js/TableRenderer/SortController.js             -- CREATE: sort state + DataSource interaction
static/js/TableRenderer/FilterController.js           -- CREATE: filter state + DataSource interaction
static/js/TableRenderer/PaginationController.js       -- CREATE: page state + DataSource interaction
static/js/TableRenderer/CellRenderer.js               -- CREATE: per-column rendering strategy base + built-ins
static/js/TableRenderer/InlineEditor.js               -- CREATE: per-cell editor strategy base + built-ins
static/js/TableRenderer/Virtualizer.js                -- CREATE: viewport-based DOM recycling
static/js/TableRenderer/TableRendererConfig.js        -- CREATE: thresholds, defaults (no magic numbers in code)
Features/SharedTable/shared-table-renderer.feature.md -- CREATE: the contract (W/S/C IDs)
Features/SharedTable/__init__.py                      -- CREATE: package marker (if Python utilities accompany)
Tests/Static/TestTableRenderer.js                     -- CREATE: renderer unit tests
Tests/Static/TestSortController.js                    -- CREATE
Tests/Static/TestFilterController.js                  -- CREATE
Tests/Static/TestPaginationController.js              -- CREATE
Tests/Static/TestVirtualizer.js                       -- CREATE
Tests/Static/TestInlineEditor.js                      -- CREATE
Features/ShowSettings/ShowSettingsController.py       -- EDIT: add paged/sortable/searchable variant to /Shows
Features/ShowSettings/ShowSettingsRepository.py       -- EDIT: push filter+sort+page into SQL
Templates/ShowSettings.html                           -- EDIT: migrate to TableRenderer (POC)
Templates/Activity.html                               -- EDIT: migrate (after POC validated)
Templates/Queue.html                                  -- EDIT: migrate
Templates/Stats.html                                  -- EDIT: migrate
Templates/Operations.html                             -- EDIT: migrate
Templates/Optimization.html                           -- EDIT: migrate
Templates/SQLQueries.html                             -- EDIT: migrate
Templates/FailedJobs.html                             -- EDIT: migrate
```

### Promotions

Required on close. Anticipated:

| Source artifact | Target file | Commit |
|---|---|---|
| Component decomposition + Seams | `Features/SharedTable/shared-table-renderer.feature.md` | TBD |
| DataSource paging contract | `Features/SharedTable/shared-table-renderer.feature.md` Seams | TBD |
| ShowSettings paged-API contract | `Features/ShowSettings/ShowSettings.feature.md` Seams | TBD |
| Per-page migration notes (if any per-page deviation) | each affected `*.feature.md` | TBD |

### Verification

To populate at VERIFYING. One entry per acceptance criterion (12 entries).

### Decisions Made

To accrete during IMPLEMENTING.

---

## Risk Notes

- **Virtualization is hard to get right.** Smooth scroll, sticky headers, sort while virtualized, and inline editor positioning are the failure modes. Budget extra time here and write tests against the math (visible-window calculation, buffer size) before integration.
- **Migration is per-page commits, not one big sweep.** ShowSettings (POC) lands first and is canary'd; each subsequent page is its own commit so a bad migration on Queue does not block the rest.
- **Backend paging changes the seam contract.** Endpoints that gain `?page`/`?sort`/`?q` must remain backward-compatible during transition (no params = unpaged response). Removal of unpaged-mode is a follow-up directive, NOT part of this one.
- **R12 / R14 apply to the new JS.** No multi-line comments; no annotation lines on docs. Plan for that during scaffolding to avoid hook friction.
