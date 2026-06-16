# Shared Table Renderer

**Slug:** shared-table-renderer
**API Version:** 1.0.0
**Status:** COMPLETE

## What It Does

`Static/js/TableRenderer/` is the single in-house JavaScript service that every tabular surface in the MediaVortex WebService uses to render rows. Pages declare table shape via configuration; rendering, sorting, filtering, pagination, virtualization, and inline editing are owned by composable controllers with one-class-per-file SRP. The package has no domain knowledge -- it knows about rows, columns, capabilities, and an EventBus, nothing else. Adding a new table to a page is a config-only change with zero edits to the renderer service.

## Workflows

| #  | Operator action / system event | Surface element | Handler | Backing class.method |
|----|--------------------------------|-----------------|---------|----------------------|
| W1 | Browse Media Library + Title Search on `/ShowSettings` | Library Card + Search Card (paged + sortable + inline profile editor) | `GET /api/ShowSettings/Shows?page=N&pageSize=N&sort=Key:DIR&q=text&filter.Drive=T:` | `Templates/ShowSettings.html` (module script); `ServerPagedDataSource` |
| W2 | Inspect Transcode + QualityTest queues on `/TranscodeQueue` | Queue table + QT queue table | `GET /api/TranscodeQueue/GetQueue?page=N&pageSize=N&sort=Key:DIR&filter.Mode=Transcode` and `GET /api/QualityTest/Queue?page=N&pageSize=N&sort=Key:DIR` | `Templates/Queue.html` (module script); `ServerPagedDataSource` |
| W3 | Watch live workers + jobs + scans on `/Activity` | Active Jobs + Active Scans + Workers tables (5s poll -> Table.Refresh()) | `LoadOverview` -> `/api/Activity/Snapshot`, `LoadWorkers` -> `/api/TeamStatus/Workers` | `Templates/Activity.html` (module script); `ClientArrayDataSource.SetRows()` + `Table.Refresh()` |
| W4 | Review failure cap exceptions on `/FailedJobs` | Failed jobs table (paged + sortable + search + reset action) | `GET /api/FailedJobs?page=N&pageSize=N&sort=Key:DIR&q=text` | `Templates/FailedJobs.html` (module script); `ServerPagedDataSource` |
| W5 | Review savings + CPU temperatures on `/Stats` | Savings By Volume table + per-core temperature card grid | `LoadSavingsByVolume` -> `/api/TeamStatus/SavingsByVolume`; CPU poll -> Refresh | `Templates/Status.html` (module script); `ClientArrayDataSource` |
| W6 | Run operator queries on `/SQLQueries` | Result table (virtualized above 500 rows) | `DisplayResults(rows)` -> `SetRows + Refresh` | `Templates/SQLQueries.html` (module script); `ClientArrayDataSource` + `Virtualizer` |
| W7 | Run maintenance ops on `/Operations` | DisplayResults + LoadRecentSuccesses + LoadRecentFailures + LoadRecentScans + LoadStuckJobs (5 tables on one page) | per-operation fetch -> `SetRows + Refresh` | `Templates/Operations.html` (module script); `ClientArrayDataSource` per table |
| W8 | Drill into optimization breakdowns on `/Optimization` | renderBreakdownTable (x3) + toggleDetails + Jellyfin analysis + renderFileTable + log-files + GPU devices | each surface owns a `TableRenderer` instance | `Templates/Optimization.html` (module script); `ClientArrayDataSource` |
| W9 | Compose a clip set on `/ClipBuilder` | Clip table (HTML5 drag-to-reorder) + export history + browse file picker | drag drops mutate `ClientArrayDataSource._Rows`, then `Refresh()` | `Templates/ClipBuilder.html` (module script) |

## Success Criteria

C1. **Memory bound.** A 3,980-row dataset on `/ShowSettings` consumes <200MB browser process working set (Edge Task Manager). Verifiable: operator measured 99MB on 2026-06-15 (12x reduction from 1.17GB pre-migration baseline). Headroom: 50%.

C2. **Site-wide standard, no antipattern survives.** Every `Templates/*.html` page that renders a multi-row data table imports `/static/js/TableRenderer/...`. Verifiable: `grep -rE "forEach\s*\([^)]*\)\s*\{[^}]*(innerHTML\s*=|\.html\()" Templates/` returns zero matches.

C3. **OCP -- new column type without renderer change.** Adding a new `CellRenderer` subclass is a single new file (or an inline `class` in the page's module script for page-specific renderers). `Static/js/TableRenderer/TableRenderer.js` is not edited.

C4. **LSP -- DataSource substitution.** `ClientArrayDataSource` and `ServerPagedDataSource` both implement `IDataSource` (async `GetRows(query)` + `GetTotalCount(query)`); swap requires changing the constructor argument only.

C5. **DIP -- no domain knowledge in shared package.** `grep -rE "\b(MediaFile|TranscodeJob|TranscodeAttempt|TranscodeQueue|QualityTest|FFmpeg|Jellyfin|VMAF)\b" Static/js/TableRenderer/` returns zero matches.

C6. **SRP -- one class per file.** `TableRenderer`, `TableRendererConfig`, `ColumnDefinition`, `EventBus`, `SortController`, `FilterController`, `PaginationController`, `Virtualizer`, `ClientArrayDataSource`, `ServerPagedDataSource`, each `CellRenderer*`, each `InlineEditor*`, each `Registry`, each `I*` interface all live in their own file.

C7. **Inline editor decoupling.** `/ShowSettings` Library table contains zero per-row `<select>` elements at rest; the profile editor opens on dblclick of the Profile cell, persists via `/api/ShowSettings/SetSeriesProfile`, then `Table.Refresh()`.

C8. **Virtualization above threshold.** `SQLQueries.html` instantiates `TableRenderer` with `Capabilities.Virtualized = true` and switches on when row count exceeds `TableRendererConfig.VirtualizationThreshold` (default 500).

C9. **Server-paged search.** `/api/ShowSettings/Shows` accepts `?q=`, `?sort=Key:Dir`, `?page=` (0-based), `?pageSize=`, `?filter.Drive=` and returns `{Rows, TotalCount, Page, PageSize, TotalPages}`. Backend filter pushes to SQL via `Core.Querying.PagedQueryBuilder`.

C10. **Contract test coverage.** `Tests/Static/*.js` exercises every controller invariant. Verifiable: `node --test Tests/Static/*.js` -> 71/71 pass.

C11. **Migration completeness.** All 9 in-scope pages route through `TableRenderer`: `/ShowSettings`, `/TranscodeQueue`, `/Activity`, `/FailedJobs`, `/Stats`, `/Operations`, `/SQLQueries`, `/Optimization`, `/ClipBuilder`. `/VmafCompare` audited and verified non-tabular (visual button grid -- not the antipattern).

C12. **Feature doc owns the contract.** This file.

C13. **ISP -- focused interfaces.** `IDataSource`, `ISortController`, `IFilterController`, `IPaginationController`, `IVirtualizer`, `ICellRenderer`, `IInlineEditor` are separate. A `TableRenderer` instantiated with `Capabilities.Paginatable = false` exposes `undefined` for `NextPage()` / `PrevPage()` / `GoToPage()` on its public surface.

C14. **Dependency direction.** Controllers depend on interfaces in `Static/js/TableRenderer/Interfaces/`, not on `TableRenderer.js` or each other. `TableRenderer.js` depends on `TableRendererConfig`, `EventBus`, `ColumnDefinition`, the two registries, and `BuildQuery` from `Interfaces/IDataSource.js` -- no controller concretes.

C15. **Observable event contract.** `Subscribe(EventName, Handler) -> unsubscribe` for `RowClicked`, `CellEdited`, `SortChanged`, `FilterChanged`, `PageChanged`, `SelectionChanged`. Event names live in `EventBus.EventNames`. No callback-config fields.

C16. **Backend paging abstraction.** Every paged endpoint routes through `Core.Querying.PagedQueryBuilder` -- ShowSettings.GetShowsWithStats, QualityTestRepository.GetQualityTestQueuePaged, TranscodeQueueRepository.GetTranscodeQueueItemsPaginated, FileScanningRepository.GetMediaFilesPaginated, ActiveJobRepository.GetActiveJobsByService. No hand-rolled `LIMIT %s` / `OFFSET %s` in the 5 migrated methods. (paged-query-core directive, sibling.)

C17. **CSS ownership.** `Static/css/TableRenderer.css` is loaded by `Templates/Base.html` and owns every `.tr-*` selector. Page-specific layout overrides (e.g. `.activity-tr-mount .tr-table { ... }` in Activity.html) are scoped to the consumer page.

C18. **Accessibility.** `<table>` semantic with `<thead>`/`<tbody>`/`<th scope="col">`. `aria-sort` on sortable headers. `aria-live` region announces row count after Refresh. Keyboard: Enter/Space on a sortable header triggers SetSort; `tabIndex=0`.

C19. **API stability commitment.** This file declares `**API Version:** 1.0.0`. Breaking changes to the public surface bump major and require a `### Migration Notes` block.

C20. **Controllers are unit-testable in isolation.** Each controller's constructor takes its DataSource + Bus + Config positionally. `Tests/Static/_StubDataSource.js` provides the substitution stub used across the suite.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `TableRenderer` → `DataSource` | `TableRenderer._BuildCurrentQuery()` | `{Page, PageSize, Sort: {Key, Direction}, Filters: {...}}` | `DataSource.GetRows(query) -> Promise<Array>`, `DataSource.GetTotalCount(query) -> Promise<number>` | `Tests/Static/TestServerPagedDataSource.js`, `TestClientArrayDataSource.js` |
| S2 | Controller → `EventBus` | `SortController.SetSort`, `FilterController.SetFilter`, `PaginationController.SetPage` | `Bus.Emit(EventName, payload)` | TableRenderer subscribes on construction and calls `Refresh()` on any change | `Tests/Static/TestSortController.js`, `TestFilterController.js`, `TestPaginationController.js` |
| S3 | `EventBus.Subscribe` → page code | `EventBus` | `(EventName: 'RowClicked'|'CellEdited'|'SortChanged'|'FilterChanged'|'PageChanged'|'SelectionChanged', handler: fn) -> Unsubscribe fn` | Page-level subscribers like ShowSettings' Profile inline-edit handler | `Tests/Static/TestEventBus.js` |
| S4 | `ServerPagedDataSource._BuildUrl` → backend endpoint | `ServerPagedDataSource` | URL params: `page=N` (0-based), `pageSize=N`, `sort=Key:DIR`, `q=text`, `filter.Key=value` | Backend endpoint accepts BOTH legacy (PascalCase, 1-based Page) AND TableRenderer-lowercase conventions; mirrors `ShowSettingsController.GetShows` shape | Backend smokes per W1/W2/W4 endpoints |
| S5 | Backend Repository → JSON response | each paged Repository method | `{Rows: [...], TotalCount: int, Page: int, PageSize: int, TotalPages: int}` + legacy field for back-compat | Page-level `ServerPagedDataSource` reads `Rows`/`TotalCount`; legacy field served for any non-migrated caller | `Tests/Contract/TestPagedQueryBuilder.py` for the underlying primitive |
| S6 | `TableRenderer` → DOM mutation | `_RenderFullBody` / `_RenderVirtualizedBody` | DocumentFragment append into `_TbodyEl` after `innerHTML = ''` | Live DOM mirrors the current page slice of rows; aria-live announces row count | Manual: load /ShowSettings, observe row count badge updates after sort/page change |

## Files

| File | Role |
|------|------|
| `Static/js/TableRenderer/TableRenderer.js` | Orchestrator; owns DOM mutation only; composes Config + Bus + DataSource + optional controllers per Capabilities |
| `Static/js/TableRenderer/TableRendererConfig.js` | DefaultPageSize, VirtualizationThreshold, DebounceMs, BufferRows, RowHeightPx, DefaultSortDirection |
| `Static/js/TableRenderer/ColumnDefinition.js` | `{Key, Header, Sortable, Filterable, CellRendererName, EditorName, Width, Align}` |
| `Static/js/TableRenderer/EventBus.js` | Tiny pub/sub: `Subscribe(name, handler) -> Unsubscribe`; `Emit(name, payload)`; `EventNames` enum |
| `Static/js/TableRenderer/SortController.js` | Sort state + emits `SortChanged` |
| `Static/js/TableRenderer/FilterController.js` | Filter state, debounced, emits `FilterChanged` |
| `Static/js/TableRenderer/PaginationController.js` | Page state + emits `PageChanged` |
| `Static/js/TableRenderer/Virtualizer.js` | Viewport-based DOM recycling; buffer = `Config.BufferRows` |
| `Static/js/TableRenderer/DataSources/ClientArrayDataSource.js` | In-memory array; client-side sort/filter/paginate; `SetRows(rows)` for live updates |
| `Static/js/TableRenderer/DataSources/ServerPagedDataSource.js` | Fetches paged URL; `Options.Fetch` injectable; per-query cache (LRU, MaxCached) |
| `Static/js/TableRenderer/CellRenderers/{Text,Number,Badge,Button}.js` + `CellRendererRegistry.js` | Generic built-ins; `Registry.Register(name, ClassRef)` for per-page extensions |
| `Static/js/TableRenderer/InlineEditors/{Text,Select}.js` + `InlineEditorRegistry.js` | Inline-edit strategies; cell opens editor on dblclick when `Capabilities.Editable && Col.Editable` |
| `Static/js/TableRenderer/Interfaces/{IDataSource,ISortController,IFilterController,IPaginationController,IVirtualizer,ICellRenderer,IInlineEditor}.js` | ABC contracts; controllers + DataSources extend |
| `Static/css/TableRenderer.css` | Shared `.tr-*` styles; loaded by `Templates/Base.html` |
| `Tests/Static/*.js` (11 suites + 2 helpers + package.json) | `node --test` -> 71/71 |

## Out of Scope

- Form rendering, modal rendering, notification UI, single-row status panels (separate backlog directives).
- Multi-field sort (single `{Key, Direction}` for v1; multi-field deferred to a future minor version per C19 stability).
- Charting (Status.html savings chart stays Chart.js-based; not a tabular surface).
