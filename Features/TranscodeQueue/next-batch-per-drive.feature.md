# Feature: Next Batch -- Per-Drive Cards (TV + Movies)

**Slug:** next-batch-per-drive

## What It Does

Splits the single "Next Batch" card on the Media -> Transcode pane into two stacked cards on the same page:

1. **TV - Next Batch** (top) -- the existing card, drive filter pinned to `T:`. Renamed from "Next Batch."
2. **Movies - Next Batch** (directly below) -- new card, same format, drive filter pinned to `M:`.

Both cards consume the same `/api/ShowSettings/NextTranscodeBatch` endpoint with different `Drive` parameter values. The endpoint is a dedicated transcode-tab read path: WHERE `NeedsTranscode = TRUE` AND not-in-queue AND `SizeMB > 0` AND `HasExplicitEnglishAudio IS NOT FALSE`, ORDER BY `SizeMB DESC NULLS LAST`, count via `COUNT(*) OVER()` window (single roundtrip). Backed by partial index `idx_mediafiles_next_transcode_batch ON MediaFiles (SizeMB DESC NULLS LAST) WHERE NeedsTranscode = TRUE AND SizeMB > 0 AND HasExplicitEnglishAudio IS NOT FALSE`.

Each card maintains its own state (offset, batch items, search term, batch size). Search/size changes on one card do not affect the other. The "Add Batch" button on each card scopes admission to that card's items only.

## Concern

Operator dogfood (2026-05-30). With TV and Movies on different drives, a single card mixed both sources -- changing the search term meant losing the other drive's results. Operator wanted "show me the next 100 TV files I should transcode AND the next 100 Movies, side-by-side stacked, both auto-loaded on page open."

## Success Criteria

### Layout

1. The Media -> Transcode pane shows the TV - Next Batch card first, the Movies - Next Batch card immediately below it, both before any other content. Verifiable: visual inspection of `/media#transcode`.

2. The TV card's header reads `"TV - Next Batch"`. The Movies card's header reads `"Movies - Next Batch"`. Verifiable: page source contains both literal strings; previously-only `"Next Batch"` does not appear.

3. Both cards use the same visual format (Bootstrap card with primary border, header row with title + count badge + Search + Size + Profile selectors + Add Batch + Re-Analyze buttons; body with table of candidates and footer total). Verifiable: side-by-side inspection -- column set, badge colors, button styles match.

### Behavior

4. On page load, both cards auto-populate: TV card calls `NextTranscodeBatch` with `Drive='T:'`, Movies card calls `NextTranscodeBatch` with `Drive='M:'`. Independently. Verifiable: open `/media#transcode`, observe both cards finish loading within a few seconds; check `Logs` for two `NextTranscodeBatch` calls with different Drive params.

5. Each card maintains independent state -- offset for pagination, batch items selected, search text, sticky batch size. Editing the TV search box does NOT trigger a Movies refresh, and vice versa. Verifiable: type in TV search box, observe Movies BatchInfo line unchanged; check that the Movies AJAX request is NOT fired.

6. Each card's "Add Batch" button submits only its own items to `/api/ShowSettings/AddSuggestionsToQueue`. The TV add does not pick up Movies items, and vice versa. Verifiable: select 5 TV items, click Add Batch on TV card, observe 5 queue rows appear with paths starting `T:\`; no `M:\` rows added.

7. Sticky batch size for the Movies card is persisted under localStorage key `ShowSettings.MoviesBatchSize` (parallel to the existing `ShowSettings.BatchSize` for TV). Default 100, max 1000. Verifiable: change Movies size to 250, reload page, observe Movies card still shows 250 selected; TV card unchanged.

8. The Drive value sent by each card is hardcoded at the call site (`'T:'` for TV, `'M:'` for Movies). No UI surface lets the operator swap a card's drive -- if they want a different drive's next batch, they need a different card. Verifiable: grep the template JS for `Drive: 'T:'` (in `SmartPopulate`) and `Drive: 'M:'` (in `SmartPopulateMovies`); no UI selector binds to either.

### Endpoint shape

9. The endpoint `POST /api/ShowSettings/NextTranscodeBatch` accepts `Drive`, `Limit` (1-1000), `Offset`, `Search` (max 100 chars). The SQL has no `PriorityScore`, no `Mode`/`Focus` branching, no `SmartPopulate`-style mode multiplexer -- it is single-purpose. Verifiable: grep `QueueManagementBusinessService.NextTranscodeBatch` and confirm the `WHERE m.NeedsTranscode = TRUE` clause + `ORDER BY m.SizeMB DESC NULLS LAST`; no `PriorityScore` token appears in the function body.

10. Neither card sends a `Mode` parameter (the endpoint is transcode-only by construction). Verifiable: inspect both AJAX payloads -- only `Drive`, `Limit`, `Offset`, `Search`.

11. EXPLAIN ANALYZE on the `NextTranscodeBatch` SQL (no Drive, no Search) shows an `Index Scan` or `Bitmap Index Scan` on `idx_mediafiles_next_transcode_batch` rather than `Seq Scan on mediafiles`. Verifiable: `py Scripts/SQLScripts/AddNextTranscodeBatchIndex.py` prints the post-create EXPLAIN.

## Surface

`/media#transcode` (`Templates/ShowSettings.html`) -- the Media page Transcode pane. Two stacked cards instead of one.

The Quick Fix pane (`/media#quickfix`) and Library pane (`/media#library`) are untouched. Other consumers of `SmartPopulate` (the Remux card, the AudioFix card) are also untouched -- they remain TV-pinned per their existing implementations and are out of scope here.

## See also

The worker claim order mirrors this card's SQL contract -- largest non-compliant first, with a 195-200 manual override window layered on top. The claim contract is owned by `Features/TranscodeQueue/queue-priority.feature.md`.

## Status

COMPLETE 2026-05-30. WebService restarted; both cards render and populate independently (verified via /ShowSettings page HTML inspection + endpoint smoke tests: TV returned 11,645 candidates, Movies returned 1,063).

### Progress

- [x] 1. Renamed TV card header to "TV - Next Batch"; added Movies card directly below with `Movies` ID prefix.
- [x] 2. Cloned JS state vars: `MoviesAllSuggestions`, `MoviesBatchItems`, `MOVIES_BATCH_SIZE`, `MoviesCurrentSearch`, `MoviesSearchDebounceTimer`, `MoviesCurrentOffset`, `MoviesTotalCandidates`, `MoviesHasMore`.
- [x] 3. Added `SmartPopulateMovies`, `RenderMoviesBatch`, `RemoveFromMoviesBatch`, `AddMoviesBatchToQueue` -- structurally identical to TV versions but reading/writing Movies state and Movies DOM IDs. Drive hardcoded `'M:'`.
- [x] 4. Wired on-init: document-ready calls `SmartPopulate()` (TV) AND `SmartPopulateMovies()` (Movies) AND `SmartPopulateAudioFix()`.
- [x] 5. Wired search-debounce + size-change handlers for the Movies card (parallel to TV). Sticky size under `ShowSettings.MoviesBatchSize` localStorage key.
- [x] 6. `LoadProfiles` populates both `#BatchProfileSelect` and `#MoviesBatchProfileSelect`.
- [ ] 7. Live verify: open `/media#transcode` after WebService restart, observe both cards populated independently; test search, batch size change, Add Batch on each card.

## Scope

```
Templates/ShowSettings.html                                -- two cards, parallel JS
Features/TranscodeQueue/next-batch-per-drive.feature.md    -- this file
```

## Files

| File | Role |
|------|------|
| `Templates/ShowSettings.html` | DOM: TV + Movies cards stacked. JS: `SmartPopulate()` / `SmartPopulateMovies()` POST `/api/ShowSettings/NextTranscodeBatch` with hardcoded Drive. Each card maintains independent state (`AllSuggestions` / `MoviesAllSuggestions`, offsets, sticky sizes under `ShowSettings.BatchSize` and `ShowSettings.MoviesBatchSize`). Priority column removed -- size order is the contract. |
| `Features/ShowSettings/ShowSettingsController.py` | `POST /api/ShowSettings/NextTranscodeBatch` route: validates `Limit` / `Offset` / `Drive` / `Search` (max 100 chars), delegates to `QueueManagementBusinessService.NextTranscodeBatch`. |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | `NextTranscodeBatch(Limit, Offset, Drive, Search)`: WHERE `NeedsTranscode = TRUE AND NOT in queue AND SizeMB > 0 AND HasExplicitEnglishAudio IS NOT FALSE`, optional Drive (StorageRootId lookup) and Search (LOWER LIKE on FileName / first RelativePath segment, `EscapeLikePattern` + `ESCAPE '!'`), ORDER BY `SizeMB DESC NULLS LAST`, `COUNT(*) OVER()` window for `TotalCandidates` (single roundtrip). Returns `{Success, Suggestions[], TotalCandidates, Offset, Limit, Search, HasMore}`. No `PriorityScore` field in the response. |
| `Scripts/SQLScripts/AddNextTranscodeBatchIndex.py` | Idempotent migration: `CREATE INDEX IF NOT EXISTS idx_mediafiles_next_transcode_batch ON MediaFiles (SizeMB DESC NULLS LAST) WHERE NeedsTranscode = TRUE AND SizeMB > 0 AND HasExplicitEnglishAudio IS NOT FALSE`. Prints post-create EXPLAIN ANALYZE. |

## Deviation from conventions

None. Mirrors the existing parallel-card pattern (Card 1 / Card 1.5 / Card 1.7 in the same template). Single endpoint, multiple parameter values, independent client state.
