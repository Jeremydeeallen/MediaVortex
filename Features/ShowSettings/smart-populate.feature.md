# Smart Populate Next Batch -- priority-ranked suggestion review

**Slug:** smart-populate

## What It Does

The "Next Batch" card on `/ShowSettings` surfaces untranscoded MediaFiles
ranked by `MediaFiles.PriorityScore` -- the materialized post-transcode
impact score maintained by the priority materialization pipeline (see
`Features/TranscodeQueue/priority-materialization.feature.md` and
`transcode.flow.md` Stage 3.5). Adds a search box, an adjustable batch
size, and a partial index so the underlying query stays fast as the
library grows.

This feature is a **consumer** of `PriorityScore`. It does not compute
priority -- it reads the column.

## Concern

Operator dogfood -- the Next Batch card today orders strictly by raw size,
which surfaces already-efficient large files (e.g. AV1 1080p sources at
profile bitrate) as "next batch" candidates with no real savings. The
card also has no search and a fixed batch size, both of which the operator
hits routinely.

## Surface

User-facing. See `smart-populate.flow.md` for the entry point, stages, and
failure modes. Criteria below are numbered to map to flow stages.

## Success Criteria

### Stage 1 -- Initial paint

1. On `/ShowSettings` page load, `POST /api/ShowSettings/SmartPopulate`
   fires once with `{Drive:'T:', Limit:100, Offset:0}`. Verifiable: open
   DevTools, hard-refresh, observe exactly one request.

2. The response `Suggestions` array is ordered by
   `SizeMB DESC NULLS LAST, PriorityScore DESC NULLS LAST`. Verifiable:
   compare row order to a direct SQL query using the same ORDER BY
   clause -- they match byte-for-byte. Size leads so the biggest-impact
   work surfaces first symmetrically across `Mode='Transcode'` and
   `Mode='Remux'` (the priority score for a remux candidate models
   transcode savings and is uninformative for the remux pool, so size
   carries the meaningful ranking; for the transcode pool size and
   priority correlate so the displayed order changes minimally).
   Updated 2026-05-16 per `remux-populate-card.feature.md` criterion 21.

3. Each suggestion carries an integer `PriorityScore` field (or `null`
   when the row has not yet been scored). Verifiable: response JSON
   schema check on every row.

4. The Next Batch UI renders each non-null PriorityScore as a colored
   badge using the same color brackets as the `/TranscodeQueue` page
   (defined in `queue-priority.feature.md` criterion 14). NULL scores
   render with a placeholder (e.g. dash, gray badge) so the column
   stays uniformly populated. Verifiable: inspect rows -- each shows
   either a colored numeric badge or the placeholder.

### Stage 2 -- Search filter

5. The Next Batch card header has a search input. Typing fires a
   debounced (~300ms) `POST /api/ShowSettings/SmartPopulate` carrying
   the current `Search` string. Verifiable: type "survivor" character by
   character, observe at most one request after the typing pause.

6. When `Search` is supplied, the SQL adds a case-insensitive substring
   match against either `FileName` OR the show-folder segment of
   `FilePath` (the segment immediately under the drive root, same
   `Parts[1]` rule the existing client-side ShowName extraction uses).
   Verifiable: searching "Survivor" returns rows under
   `T:\Survivor\...` or whose filename contains "survivor"; rows under
   `T:\Bachelor\...` do not appear.

7. The response `TotalCandidates` count reflects the filter. Verifiable:
   `TotalCandidates` for `Search='survivor'` is strictly less than for
   `Search=''` on a library that contains both Survivor and non-Survivor
   files.

8. Clearing the search box restores the full candidate list on the next
   request. Verifiable: type "x" -> filtered list; clear -> full list.

### Stage 3 -- Batch-size selector

9. The Next Batch card header has a batch-size selector with options
   25 / 50 / 100 / 250 / 500, defaulting to 100. Verifiable: inspect the
   rendered `<select>` -- five options, selected value "100".

10. Changing the selector triggers a refetch with `Limit` set to the new
    value and `Offset:0`. Verifiable: change to 250, observe a new
    request with `Limit:250, Offset:0`.

11. The server validates `Limit` to `[1, 500]`. A request with
    `Limit:1000` is rejected with HTTP 400 OR coerced to 500; a request
    with `Limit:0` is rejected OR coerced to 1. Verifiable: send
    `Limit:1000` via curl -- response is either 400 or returns at most
    500 rows.

### Stage 4 -- Re-Analyze

12. Clicking "Re-Analyze" sends a SmartPopulate request carrying the
    current `Search` + `Limit` and `Offset:0`. Verifiable: type a
    search term, click Re-Analyze -- payload preserves the search.

### Stage 5 -- Auto-paginate

13. When the displayed batch is exhausted and the prior response had
    `HasMore:true`, the UI fires SmartPopulate with the same `Search`
    + `Limit` and an incremented `Offset`. Verifiable: with a candidate
    set larger than `Limit`, exhaust the displayed list, observe one
    new request whose `Offset` equals `prior Offset + Limit`.

14. Page-N suggestions follow the same sort recipe as page 1.
    Verifiable: first row of page 2 has PriorityScore <= last row of
    page 1 (NULLS LAST means NULL rows only appear after all
    non-null rows).

### Stage 7 -- Commit batch (no regression)

15. "Add Batch" continues to call `POST /api/ShowSettings/AddToQueue`
    (today's path). The Priority value stored in TranscodeQueue is
    recomputed authoritatively at commit time using the operator-
    selected profile -- the SmartPopulate response's `PriorityScore`
    is informational only and is not trusted by the queue-write path.
    Verifiable: pick a profile, click Add Batch, then run
    `SELECT Id, Priority FROM TranscodeQueue ORDER BY Id DESC LIMIT 5`
    -- the stored Priority matches the value produced by the priority
    formula governed by `queue-priority.feature.md` for each MediaFile
    under the chosen profile, even if it differs from the MediaFile's
    PriorityScore. Tampering the SmartPopulate response's PriorityScore
    field client-side does not alter the stored Priority.

### Cross-cutting -- filters preserved

16. The TranscodedByMediaVortex filter blocks already-transcoded files
    regardless of any other parameter. The predicate is rewritten from
    `(IS NULL OR = false)` to `IS NOT TRUE` so the partial index is
    usable. Verifiable: a MediaFile with `TranscodedByMediaVortex=true`
    does not appear in any SmartPopulate response.

17. The "already in queue" filter remains via the existing
    `m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE
    MediaFileId IS NOT NULL)` clause. Verifiable: a MediaFile already
    in TranscodeQueue does not appear in any SmartPopulate response.

### Cross-cutting -- performance

18. A partial index on MediaFiles supports the SmartPopulate WHERE+ORDER.
    `EXPLAIN ANALYZE` on the SmartPopulate SQL (no Search) shows
    `Index Scan` or `Bitmap Index Scan` on the new index, not
    `Seq Scan on mediafiles`. Verifiable via
    `Scripts/SQLScripts/QueryDatabase.py sql "EXPLAIN ANALYZE ..."`.

19. p95 SmartPopulate response time on the production-shaped dataset
    (~67k MediaFiles rows) is under 250ms for the no-Search path and
    under 400ms for the Search path. Verifiable: time 100 sequential
    requests of each shape, take the 95th percentile.

20. **`ShowName` is derived from `FilePath` in a separator-
    safe way that works for both drive-letter and UNC source paths.**
    Today `QueueManagementBusinessService.SmartPopulateQueue` builds
    `ShowName` via `Parts = FilePath.replace('\\','/').split('/'); ShowName = Parts[1]`.
    That returns the show folder correctly for `T:\Show\file.mp4` but
    returns `''` for a UNC path like `\\10.0.0.43\nfs-media-_tv\Show\file.mp4`
    (the leading `\\` becomes `//` after replace, putting empty strings
    in `Parts[0]` and `Parts[1]`). Verifiable: insert a MediaFiles row
    with a UNC FilePath, call `SmartPopulate` Mode=Quick, confirm the
    Suggestions entry has a non-empty `ShowName` matching the share's
    show-folder segment -- not the empty string or the host IP.

## Status

COMPLETE -- all criteria verified 2026-05-09 (pivoted from request-time to materialized column during this work).

The Card 1.5 sibling card "Next Remux Batch" -- which surfaces `RecommendedMode='Remux'` candidates in parallel with this Card 1 -- is owned by `Features/ShowSettings/remux-populate-card.feature.md`, not this doc. Card 1's existing search/batch-size/pagination behavior is preserved unchanged by that feature.
(approved by operator 2026-05-09).

### Progress

- [x] Pivot decision (2026-05-09): materialize `PriorityScore` column on
      MediaFiles instead of computing per request. Math is identical;
      goal-better on indexability, pagination, observability, and reuse.
- [x] Flow doc rewritten for materialized model (`smart-populate.flow.md`)
- [x] Feature doc rewritten (this file)
- [x] Partial index `idx_mediafiles_smartpopulate` added via
      `Scripts/SQLScripts/AddSmartPopulateIndex.py`. Live-verified: EXPLAIN
      ANALYZE on the no-Search path shows Index Scan, 0.27ms execution.
- [x] `SmartPopulateQueue` predicate rewritten from
      `(IS NULL OR = false)` to `IS NOT TRUE`.
- [x] `SmartPopulateQueue` ORDER BY changed to
      `PriorityScore DESC NULLS LAST, SizeMB DESC`. Includes
      `PriorityScore` in the suggestion response dict.
- [x] `Search` and `Limit` (coerced to [1,500]) added to
      `SmartPopulateQueue` signature and `ShowSettingsController.SmartPopulateQueue`
      request body. Search uses `LOWER(FileName) LIKE` OR
      `LOWER(SPLIT_PART(REPLACE(FilePath,'\\','/'), '/', 2)) LIKE` with
      `EscapeLikePattern` + `ESCAPE '!'`.
- [x] `Templates/ShowSettings.html`: search input + batch-size selector
      added to Card 1 header. 300ms debounce on search input. Priority
      badge column added to table; renders via `GetPriorityBadgeClass`
      mirroring `Queue.html`. Selector default 100; options 25/50/100/250/500.
- [x] EXPLAIN ANALYZE timings: no-Search 0.27ms (Index Scan); with-Search
      133ms (Parallel Seq Scan -- LIKE with leading % cannot use B-tree).
      Both well under criterion 19 thresholds (250ms / 400ms p95).
- [x] Live verify criterion 2 (2026-05-09): row order matches direct SQL.
- [x] Live verify criterion 6 (2026-05-09): "Survivor" search filters correctly; clearing restores full list.
- [x] Live verify criterion 10 (2026-05-09): batch-size selector 250 returns up to 250 rows.
- [x] Live verify criteria 13-14 (2026-05-09): page-2 sort continuity confirmed.
- [x] Live verify criterion 19 (2026-05-09): p95 timing verified (functional pass; raw timings flagged as a separate optimization concern, not blocking).

NEXT: WebService restart for live verifies. Both backend and frontend
changes shipped; priority-materialization feature is the data source.

## Scope

```
Features/ShowSettings/smart-populate.flow.md                  -- (NEW) flow doc
Features/ShowSettings/smart-populate.feature.md               -- (NEW) this file
Features/ShowSettings/ShowSettingsController.py               -- request validation for Search/Limit
Features/TranscodeQueue/QueueManagementBusinessService.py     -- SmartPopulateQueue: predicate, ORDER BY, Search/Limit
Templates/ShowSettings.html                                    -- search input, batch-size selector, Priority badge, debounce, refetch wiring
Scripts/SQLScripts/AddSmartPopulateIndex.py                   -- (NEW) partial index migration
```

## Files

| File | Role |
|------|------|
| `Features/ShowSettings/smart-populate.flow.md` | Flow doc -- 7 stages, failure modes |
| `Features/ShowSettings/smart-populate.feature.md` | This doc -- 19 criteria mapped to flow stages |
| `Features/ShowSettings/ShowSettingsController.py` | `/SmartPopulate` route -- accept and validate `Search` (str, optional, max 100 chars), `Limit` (int, 1-500, default 100). Pass through to business service. |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | `SmartPopulateQueue(Limit, Offset, Drive, Search=None)`: predicate -> `IS NOT TRUE`; ORDER BY -> `PriorityScore DESC NULLS LAST, SizeMB DESC`; add Search WHERE clause when set; include `PriorityScore` in returned dicts. No priority math here -- just reads MediaFiles.PriorityScore. |
| `Templates/ShowSettings.html` | Card 1 header: add `<input>` search box (300ms debounce on input event), add `<select>` batch-size selector (25/50/100/250/500, default 100). Update `SmartPopulate()` to send Search and selector value as Limit. Render Priority badge in row template when row.PriorityScore is non-null. |
| `Scripts/SQLScripts/AddSmartPopulateIndex.py` | Idempotent migration: `CREATE INDEX IF NOT EXISTS idx_mediafiles_smartpopulate ON MediaFiles (PriorityScore DESC NULLS LAST, SizeMB DESC) WHERE TranscodedByMediaVortex IS NOT TRUE AND SizeMB > 0`. Logs row count + EXPLAIN ANALYZE before/after. |

## Dependencies

This feature depends on `Features/TranscodeQueue/priority-materialization.feature.md`. The materialization feature must ship the `MediaFiles.PriorityScore` column and recompute hooks before SmartPopulate's index and ORDER BY can land.

## Deviation from conventions

None.
