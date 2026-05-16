# Remux Populate Card -- sibling card on /ShowSettings for the Remux queue

## What It Does

Adds a sibling card "Next Remux Batch" directly under Card 1 "Next Batch"
on `/ShowSettings`. Identical layout shape to Card 1, scoped to MediaFiles
where `RecommendedMode='Remux'` (per the cascade owned by
`Features/TranscodeQueue/transcode-vs-remux-routing.feature.md`). Lets
the operator drain the remux pool aggressively in parallel with paced
transcode work, without flipping a tab or losing visibility of either
queue.

The two cards share the same SmartPopulate endpoint with a new `Mode`
parameter (`Transcode` | `Remux`) that filters and routes appropriately.
State (search box, batch-size selector, displayed batch) is **per-card
independent** -- the operator can have a Survivor search active on the
Transcode side while the Remux side shows the global list.

This feature is a **consumer** of `MediaFiles.RecommendedMode`. It does
not compute the routing decision; it only presents the rows the cascade
has already classified.

## Concern

Operationally these are very different workloads. Remux jobs finish in
5-30 seconds (audio re-encode + container fix only); transcode jobs
take hours. On the live DB right now the cascade reports ~17,200 remux
candidates and ~18,100 transcode candidates. The operator wants to
drain the remux pool quickly (it's the easy-wins thread) and pace the
transcode pool deliberately. A single Card 1 with a mode toggle hides
one queue while the other is showing -- the operator can't see "17.2k
remux / 18.1k transcode" at a glance, can't plan workload, can't
search both lists independently.

UX-reviewer recommendation 2026-05-09: "**Card 1.5 sibling card** with
parallel structure, both visible on page load." That's what this
feature implements.

## Surface

User-facing. See `smart-populate.flow.md` for entry point, stages, and
failure modes -- the Remux card mirrors Card 1's flow with `Mode='Remux'`
filter and route. Criteria below are numbered to map to flow stages,
parallel to `smart-populate.feature.md`.

## Success Criteria

### A. Card placement and identity

1. `Templates/ShowSettings.html` renders a new card titled "Next Remux Batch" directly under Card 1 "Next Batch", before Card 2 "Title Search". The new card has a distinct visual accent so the operator can tell at a glance it's not Card 1 (specific styling at implementation discretion; today's codebase suggests `border-info` or a non-primary Bootstrap class but the criterion does not require any specific framework). Verifiable: hard-refresh `/ShowSettings`, inspect the DOM order under `<div class="container-fluid px-4">` -- Card 1 -> Card 1.5 -> Card 2 -> Card 3.

2. Both Card 1 and Card 1.5 are visible on page load without operator action. Neither hides the other; no tab toggle or accordion. Verifiable: render the page, both cards are in the DOM with no `display:none` style.

3. Each card displays its own count badge in the header (number of candidates currently in its scope). The badges reflect the cascade's classification: Card 1 shows the count where `RecommendedMode='Transcode'`, Card 1.5 shows the count where `RecommendedMode='Remux'`. Verifiable: DB query `SELECT RecommendedMode, COUNT(*) FROM MediaFiles WHERE IsCompliant IS NOT TRUE AND RecommendedMode IN ('Transcode','Remux') GROUP BY 1` reconciles with the two badge values.

### B. Backend Mode parameter

4. `POST /api/ShowSettings/SmartPopulate` accepts an optional `Mode` parameter with values `'Transcode'` or `'Remux'`. When supplied, the SQL adds `AND m.RecommendedMode = %s`. When absent or invalid, behavior is unchanged from today (returns whatever the cascade decided, no Mode filter). Verifiable: two requests differing only on `Mode` against the same dataset return disjoint candidate sets matching `MediaFiles.RecommendedMode='Transcode'` and `'Remux'` respectively.

5. `POST /api/ShowSettings/AddToQueue` accepts items with `Mode='Remux'` AND `ProfileId=null`. When Mode='Remux', the server skips profile resolution entirely and inserts the queue row with `ProcessingMode='Remux'`, no `AssignedProfile` lookup. Verifiable: send a payload with `{MediaFileIds:[X], Mode:'Remux', ProfileId:null}` for a real Remux candidate; observe one new TranscodeQueue row with `ProcessingMode='Remux'` and Priority recomputed by the existing CalculatePriority path.

6. The `Mode` parameter on `AddToQueue` is validated against `{'Transcode', 'Remux'}`. Other values return HTTP 400 with `Message` naming the offending field. Verifiable: curl with `Mode='Invalid'` returns 400.

### C. Card 1.5 controls (parallel structure)

7. Card 1.5 has its own search input (`#RemuxSearch`), batch-size selector (`#RemuxSizeSelect`), and Re-Analyze button (`#RemuxAnalyzeBtn`). State is independent of Card 1. Typing in `#RemuxSearch` does not affect Card 1's filter; changing `#BatchSizeSelect` (Card 1) does not affect Card 1.5's batch size. Verifiable: open DevTools, type "Survivor" in `#RemuxSearch`, confirm one debounced request fires with `{Mode:'Remux', Search:'Survivor'}`; Card 1's request payload (if any fires) does not include the search term.

8. Card 1.5's batch-size control is an `<input type="number" min="1" max="500" step="1">` -- the operator can type any integer 1-500. Default value is `250` (higher than Card 1's `100`); rationale: remux jobs finish in 5-30s, larger batches finish quickly. **For parity, Card 1's existing batch-size selector is also converted to the same number-input control** (default 100, same min/max). Both cards retain the small set of "common" values via an associated `<datalist>` (25/50/100/250/500) so the operator can dropdown-pick OR type, especially the "1" case which isn't on the canned list and is useful for testing one job at a time. Verifiable: inspect both `#BatchSizeSelect` and `#RemuxSizeSelect` -- both are `<input type="number">` with `min=1 max=500`; entering `1` and pressing Enter triggers a refetch with `Limit:1`.

9. Card 1.5 has **no profile dropdown.** The cascade has already decided "container/audio fix only" for these rows; there is no profile choice to make. The header shows a static caption like "Audio normalize + container fix" where Card 1 has its profile select. Verifiable: DOM inspection -- no `<select>` for profile inside Card 1.5; static `<small>` caption is present with the documented text.

10. Card 1.5's "Add Batch" button posts `{Mode:'Remux', ProfileId:null, MediaFileIds:[...]}` to `/api/ShowSettings/AddToQueue`. Verifiable: DevTools network tab -- click Add Batch, observe request payload `Mode='Remux'` and `ProfileId=null`.

### D. Card 1 unchanged

11. Card 1's existing behavior is preserved: search box, batch-size selector (default 100), Re-Analyze, Add Batch all still work as before. Card 1's calls to SmartPopulate either omit `Mode` (backward-compat) or send `Mode='Transcode'` (new code). Either way, Card 1 displays only `RecommendedMode='Transcode'` candidates. Verifiable: regression-walk Card 1's search/batch-size/pagination flow per `smart-populate.feature.md` criteria 5-14.

12. The existing `getPriorityBadgeClass` helper renders the Priority badge identically in both cards. Verifiable: a row at Priority=85 renders the same blue `bg-info` badge whether it appears on Card 1 or Card 1.5.

### E. Filters preserved (cross-cutting from smart-populate.feature.md)

13. Both cards respect the existing exclusions: `IsCompliant IS NOT TRUE`, `TranscodedByMediaVortex IS NOT TRUE`, `m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL)`, `SizeMB > 0`. The `Mode` filter is added on top, never replaces. Verifiable: a MediaFile with `IsCompliant=true AND RecommendedMode='Remux'` does NOT appear on Card 1.5 -- compliance trumps the Mode filter.

13b. Files with zero audio streams are valid remux candidates. When queued, the remux command builder detects `HasAudio=False` via FFprobe analysis and builds a video-only command (no `-map 0:a:*`, no audio codec/filter args). The file is remuxed to MP4 with video copy only. Verifiable: queue a video-only file for remux; it completes successfully with `TranscodeAttempts.Success=true` and `MediaFiles.ContainerFormat` updates to MP4.

### F. Performance and pagination

14. The partial index `idx_mediafiles_smartpopulate` continues to support both Card queries. EXPLAIN ANALYZE on a SmartPopulate request with `Mode='Remux'` shows Index Scan or Bitmap Index Scan, not Seq Scan. Verifiable: run `EXPLAIN ANALYZE SELECT ... WHERE IsCompliant IS NOT TRUE AND RecommendedMode='Remux' ...` against the live DB; plan shows Index Scan.

15. Pagination is per-card independent. Auto-paginate on Card 1.5 sends `{Mode:'Remux', Offset:Offset+Limit}`; Card 1's offset is unaffected. Verifiable: with both cards exhausted to page 2 simultaneously, network requests show two separate `Offset` trackers.

### G. Empty / edge states

16. When `RecommendedMode='Remux'` candidates count is zero (operator has drained the pool), Card 1.5 renders "No remux candidates -- library is fully normalized" or equivalent. Same for Card 1 when transcode pool is zero. Verifiable: temporary DB state where no rows match -- card body shows the empty-state message, not a misleading spinner.

17. When the cascade has not yet run (cold start, all `RecommendedMode IS NULL`), both cards render an empty state pointing to the admin recompute endpoint. Verifiable: NULL-everything DB state, both cards show "Run admin recompute to populate" or similar guidance.

### H. Accessibility / clarity

18. Card 1.5's header label clarifies what "remux" means in operator-facing terms. Title is "Next Remux Batch"; subtitle reads "Audio normalize + container fix (no video re-encode)" so an operator who hasn't read the docs can understand the difference from Card 1. Verifiable: visual inspection.

### J. Sort parity and header parity with transcode queue [BUG]

21. **[BUG 2026-05-16]** Card 1 ("Next Batch") and Card 1.5 ("Next Remux Batch") must use the same sort key and the same count-badge format -- the only operator-visible differences should be (a) the per-card search input (independent state) and (b) the filter criterion (`Mode='Transcode'` vs `Mode='Remux'`, mapped by the cascade's `RecommendedMode` partition: resolution-threshold mismatch vs non-matching container + audio mismatch). Two specific defects today:

    **21a. Count-badge format diverges.** Card 1's badge renders `BatchItems.length` (next-batch size). Card 1.5's badge renders `RemuxTotalCandidates` (total pool remaining). Operator cannot eyeball "what gets queued vs what's left" from the badges. Fixed = both cards' badges render `<next batch>/<total>` (e.g. `100/17045`, `250/7439`). Verifiable: hard-refresh `/ShowSettings`, both badges show two numbers separated by `/`; the first equals the current `BatchItems`/`RemuxBatchItems` length, the second equals the API's `TotalCandidates`.

    **21b. Sort does not consider size meaningfully on Card 1.5.** Today both cards `ORDER BY PriorityScore DESC NULLS LAST, SizeMB DESC` and PriorityScore is materialized for 100% of rows. But PriorityScore for a `RecommendedMode='Remux'` row models *transcode savings* (the formula assumes re-encode to the profile target bitrate) -- meaningless for a remux operation that does not re-encode video. Result: Card 1.5's top row is a 217 MB MP4 at PriorityScore 85, while a 1,956 MB Ghostbusters MKV (genuinely the largest-impact remux) sits at row 2 with PriorityScore 84. Operator expects "the biggest impactful work first" symmetrically across both cards. Fixed = `SmartPopulateQueue` sorts by `SizeMB DESC NULLS LAST, PriorityScore DESC NULLS LAST` for both modes -- size becomes the primary key, PriorityScore the tiebreaker. Card 1 ordering changes minimally because size correlates with priority for transcode candidates; Card 1.5 ordering flips so the largest remux candidates lead. Verifiable: query `SELECT Id, SizeMB, PriorityScore FROM MediaFiles WHERE IsCompliant IS NOT TRUE AND TranscodedByMediaVortex IS NOT TRUE AND SizeMB > 0 AND RecommendedMode = 'Remux' ORDER BY SizeMB DESC NULLS LAST, PriorityScore DESC NULLS LAST LIMIT 10` and confirm the first 10 ids match the Card 1.5 display top 10 after refresh.

    Look first: `Features/TranscodeQueue/QueueManagementBusinessService.py::SmartPopulateQueue` ORDER BY clause (~line 324) -- update the SQL. `Templates/ShowSettings.html` -- count-badge rendering in `SmartPopulate` (~line 644) and `SmartPopulateRemux` (~line 702); `RenderBatch` (~line 847) also writes BatchCount on every render and needs to use the new format. The `idx_mediafiles_smartpopulate` partial index in `Scripts/SQLScripts/AddSmartPopulateIndex.py` is keyed on `(PriorityScore DESC NULLS LAST, SizeMB DESC)` -- after this change, EXPLAIN ANALYZE on the new ORDER BY may need a new index keyed on `(SizeMB DESC NULLS LAST, PriorityScore DESC NULLS LAST)` to avoid a Seq Scan.

### I. Responsiveness

19. Clicking Card 1.5's "Add Batch" button completes in under 1 second on the live DB (250-item default batch). The Mode='Remux' path in `AddSuggestionsToQueue` must not issue per-item DB lookups for profile-target bitrates (those are meaningless for a no-re-encode operation). Verifiable: time the "Add Batch" click on Card 1.5 -- under 1s for a 250-item batch.

20. Card 1.5's Add Batch is data-driven end-to-end with minimal client bookkeeping. All of the following hold simultaneously:

    - **Slimmed payload.** `/api/ShowSettings/AddToQueue` accepts `{Mode:'Remux', MediaFileIds:[...]}` (IDs only). The server reads FilePath/SizeMB/Resolution from MediaFiles, not from the client. Verifiable: DevTools network tab shows the request body contains only Mode + MediaFileIds; queueing 250 items produces a request under ~5KB (today ~52KB).
    - **Single-statement insert.** The server-side commit is a single `INSERT INTO TranscodeQueue (...) SELECT ... FROM MediaFiles WHERE Id = ANY(%s) AND NOT EXISTS (SELECT 1 FROM TranscodeQueue tq WHERE tq.FilePath = m.FilePath)` (or equivalent). No Python per-item loop building `PendingInserts`. Verifiable: a 5000-item batch completes in one DB round-trip (EXPLAIN ANALYZE shows one INSERT plan); total wall time scales with row count linearly on the server, not with N round-trips.
    - **Display cap separated from queue cap.** Card 1.5 has two distinct limits: a display cap (default 250, governs how many rows render in the table for preview/remove) and a queue cap (effectively unbounded, governs how many rows the Add Batch button commits). Verifiable: enter `5000` in the size selector -- the table still renders at most the display cap (table stays responsive), but clicking Add Batch queues 5000 rows.
    - **"Queue all matching" affordance.** A separate button on Card 1.5 commits every candidate currently matching the cascade filter (and search, if active) in one server-side INSERT...SELECT -- no client-side ID enumeration. Verifiable: clicking the button with 17,200 candidates queues all 17,200 in a single request without the browser allocating an Items array.
    - **Sticky size selector.** The `#RemuxSizeSelect` value persists across page reloads via localStorage. Verifiable: set size to 100, reload, value is still 100.
    - **Legacy removed.** The per-row `Item.get('Mode')` fallback in `AddSuggestionsToQueue` (Mode is a top-level param now), the dead `'Priority': int(float(...))` assignment in `QueueByFolder`, the per-item-insert fallback after bulk-insert failure (verify it has never fired in Logs; if it has not, delete it), and the suspicious `Drive: 'T:'` hardcoding in the SmartPopulate payload are all removed. Verifiable: grep for each pattern returns no matches.
    - **Simpler client state.** The `RemuxAllSuggestions` + `RemuxBatchItems` two-array bookkeeping and the splice/concat auto-pagination collapse to a simpler model now that the queue cap is independent of the display cap. Verifiable: Card 1.5 JS section has one source-of-truth array for the displayed rows; auto-pagination logic is gone or trivial.

    Look first: `Templates/ShowSettings.html` Card 1.5 JS (`AddRemuxBatchToQueue`, `SmartPopulateRemux`, state vars), `Features/ShowSettings/ShowSettingsController.py` `/AddToQueue` route, `Features/TranscodeQueue/QueueManagementBusinessService.py` `AddSuggestionsToQueue`, `Features/TranscodeQueue/TranscodeQueueRepository.py` `BulkInsertQueueItems` (likely deletable after the INSERT...SELECT refactor).

## Status

IN PROGRESS -- operator approved 2026-05-09; manual-entry tweak folded into criterion 8.

### Progress

- [x] Criterion 21 (2026-05-16): sort parity + header parity with Card 1
  - Backend: `SmartPopulateQueue` ORDER BY changed to `SizeMB DESC NULLS LAST, PriorityScore DESC NULLS LAST` (was `PriorityScore DESC NULLS LAST, SizeMB DESC`). Both modes use the same key; size is now the meaningful primary because remux priority models transcode savings and is uninformative for the remux pool. Transcode display unchanged in practice (size/priority correlate); remux display now leads with the largest candidates (verified: 2,666 MB JFK MKV at top vs prior 217 MB MP4).
  - Frontend: Card 1 and Card 1.5 count badges both render `<batch>/<total>` (e.g. `100/17,045` and `250/7,439`). `BatchCount` set inside `RenderBatch`; `RemuxCount` set inside `RenderRemuxBatch` -- removes the prior SmartPopulate-side set that showed only the total. Card 1.5's "Audio normalize + container fix (no video re-encode)" subtitle and "no profile needed" italic caption removed per operator request.
  - Docs: `smart-populate.feature.md` criterion 2 and `smart-populate.flow.md` Stage 1 + Data Flow updated to the new sort key.
  - EXPLAIN ANALYZE shows 97 ms top-N heapsort on Seq Scan (was Index Scan on the old order); well under the 250 ms p95 threshold per `smart-populate.feature.md` criterion 19. Index `idx_mediafiles_smartpopulate` is now keyed for the prior sort; can be replaced or supplemented in a follow-up if p95 trends up.
- [x] UX-reviewer guidance obtained 2026-05-09: option B (sibling card)
- [x] Flow doc extended (`smart-populate.flow.md` Entry Point updated to mention both cards)
- [x] Feature doc drafted (this file)
- [ ] Operator approves criteria 1-18
- [ ] Backend: extend `SmartPopulateQueue` business-service to accept `Mode` param, filter on `RecommendedMode`
- [ ] Backend: extend `ShowSettingsController.SmartPopulate` route to plumb `Mode` through
- [ ] Backend: extend `AddToQueue` route + `AddSuggestionsToQueue` to accept `Mode='Remux'` with `ProfileId=null`
- [ ] Frontend: insert Card 1.5 markup in `Templates/ShowSettings.html` after Card 1
- [ ] Frontend: parallel JS section for Card 1.5 -- own state vars, own debounce, own AJAX calls
- [ ] Frontend: remove profile dropdown from Card 1.5 markup; static caption
- [ ] Live verify criterion 4: two requests differing on `Mode` return disjoint sets
- [ ] Live verify criterion 5: posting Mode='Remux' produces TranscodeQueue row with ProcessingMode='Remux'
- [ ] Live verify criteria 7, 9, 10: DOM inspection, payload inspection
- [ ] Live verify criterion 14: EXPLAIN ANALYZE shows Index Scan with Mode filter
- [ ] Update `smart-populate.feature.md` Status note pointing to this feature doc as the parent of Card 1.5

NEXT: operator approval to start implementation. Recommended order:

1. Backend Mode param on SmartPopulate + AddToQueue (the data contract)
2. Insert Card 1.5 markup with placeholder JS that hits the new Mode='Remux' API
3. Wire Card 1.5 JS state + handlers (independent debounce, batch size, etc.)
4. Confirm Card 1 regression-clean via the existing live verifies in smart-populate.feature.md
5. Live verifies 4, 5, 7, 9, 10, 14 for Card 1.5

## Scope

```
Templates/ShowSettings.html                                     -- Card 1.5 markup + parallel JS
Features/ShowSettings/ShowSettingsController.py                 -- SmartPopulate Mode param, AddToQueue Mode param + null ProfileId
Features/TranscodeQueue/QueueManagementBusinessService.py       -- SmartPopulateQueue Mode filter, AddSuggestionsToQueue Mode='Remux' path
Features/ShowSettings/smart-populate.flow.md                    -- Entry Point updated (already done in this feature)
Features/ShowSettings/smart-populate.feature.md                 -- Status note pointing here
```

## Files

| File | Role |
|------|------|
| `Features/ShowSettings/remux-populate-card.feature.md` | This doc -- 18 criteria for the sibling card |
| `Features/ShowSettings/smart-populate.flow.md` | Entry Point already extended to describe both cards + the Mode parameter |
| `Templates/ShowSettings.html` | Insert Card 1.5 markup directly under Card 1, before Card 2. Parallel JS section after Card 1's block. New IDs: `RemuxCard`, `RemuxCount`, `RemuxSearch`, `RemuxSizeSelect`, `RemuxAnalyzeBtn`, `RemuxAddBatchBtn`, `RemuxTableBody`, `RemuxBatchInfo`, `RemuxTotalSize`. No profile dropdown. |
| `Features/ShowSettings/ShowSettingsController.py` | `/SmartPopulate` accepts `Mode` (validated against `{'Transcode','Remux'}`); plumbs through to business service. `/AddToQueue` accepts `Mode='Remux'` with `ProfileId=null` and treats that as the route to `AddSuggestionsToQueue` Remux path. |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | `SmartPopulateQueue` adds `AND m.RecommendedMode = %s` when Mode is supplied. `AddSuggestionsToQueue` recognizes Mode='Remux' and constructs `TranscodeQueueModel(ProcessingMode='Remux', ...)` with `Priority` from `CalculatePriority` (no profile lookup needed -- the existing `_DecideQueueMode` path already handles Mode='Remux' once transcode-vs-remux-routing step 6 ships; this feature is the UI sibling that lets the operator drive that path). |
| `Features/ShowSettings/smart-populate.feature.md` | Add a one-line note in Status that Card 1.5 is documented in `remux-populate-card.feature.md`. |

## Dependencies

This feature depends on:
- `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` -- the cascade that populates `MediaFiles.RecommendedMode`. Without it, all rows have NULL RecommendedMode and Card 1.5 stays empty.
- `Features/ShowSettings/smart-populate.feature.md` -- the parent UX (Card 1) that this feature mirrors. Card 1 must remain regression-clean per its existing criteria.

## Deviation from conventions

None. Each criterion is observable from outside (DOM inspection, network payload check, DB query, EXPLAIN plan). The new card is a sibling of Card 1, not a tab/toggle/accordion -- preserves the codebase's existing card-per-purpose convention rather than introducing a new pattern.
