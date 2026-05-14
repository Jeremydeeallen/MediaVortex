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

13b. [BUG] Files with zero audio streams never appear as candidates in either card. A file with `AudioCodec IS NULL` and no `AudioLanguages` that has been probed (has `Resolution` set) is excluded from SmartPopulate results regardless of `HasExplicitEnglishAudio` value. Verifiable: a MediaFile with `AudioCodec IS NULL AND Resolution IS NOT NULL` returns zero rows from SmartPopulate for both Mode='Transcode' and Mode='Remux'.

### F. Performance and pagination

14. The partial index `idx_mediafiles_smartpopulate` continues to support both Card queries. EXPLAIN ANALYZE on a SmartPopulate request with `Mode='Remux'` shows Index Scan or Bitmap Index Scan, not Seq Scan. Verifiable: run `EXPLAIN ANALYZE SELECT ... WHERE IsCompliant IS NOT TRUE AND RecommendedMode='Remux' ...` against the live DB; plan shows Index Scan.

15. Pagination is per-card independent. Auto-paginate on Card 1.5 sends `{Mode:'Remux', Offset:Offset+Limit}`; Card 1's offset is unaffected. Verifiable: with both cards exhausted to page 2 simultaneously, network requests show two separate `Offset` trackers.

### G. Empty / edge states

16. When `RecommendedMode='Remux'` candidates count is zero (operator has drained the pool), Card 1.5 renders "No remux candidates -- library is fully normalized" or equivalent. Same for Card 1 when transcode pool is zero. Verifiable: temporary DB state where no rows match -- card body shows the empty-state message, not a misleading spinner.

17. When the cascade has not yet run (cold start, all `RecommendedMode IS NULL`), both cards render an empty state pointing to the admin recompute endpoint. Verifiable: NULL-everything DB state, both cards show "Run admin recompute to populate" or similar guidance.

### H. Accessibility / clarity

18. Card 1.5's header label clarifies what "remux" means in operator-facing terms. Title is "Next Remux Batch"; subtitle reads "Audio normalize + container fix (no video re-encode)" so an operator who hasn't read the docs can understand the difference from Card 1. Verifiable: visual inspection.

## Status

IN PROGRESS -- operator approved 2026-05-09; manual-entry tweak folded into criterion 8.

### Progress

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
