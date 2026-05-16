# Flow: Smart Populate Next Batch (/ShowSettings)

## Entry Point

`Templates/ShowSettings.html` -- Card 1 "Next Batch" + Card 1.5 "Next
Remux Batch" (parallel sibling). The user lands on `/ShowSettings` to
find files worth queuing. Both cards surface ranked candidates, scoped
by `MediaFiles.RecommendedMode`, and accept the user's commit to the
queue.

API entry: `POST /api/ShowSettings/SmartPopulate` ->
`Features/ShowSettings/ShowSettingsController.SmartPopulateQueue` ->
`Features/TranscodeQueue/QueueManagementBusinessService.SmartPopulateQueue`.

The endpoint accepts a `Mode` parameter (`Transcode` | `Remux`) that
filters to the matching `RecommendedMode` and routes the resulting
queue items to the corresponding `ProcessingMode`. Both cards hit the
same endpoint with their own `Mode` value plus independent state
(search, batch size, offset) so an operator can search Survivor on
the Transcode side without affecting the Remux side, and vice versa.

The ranking value (`MediaFiles.PriorityScore`) is **maintained
continuously** by the priority materialization pipeline -- see
`transcode.flow.md` Stage 3.5 and
`Features/TranscodeQueue/priority-materialization.feature.md`. SmartPopulate
itself never computes priority; it only reads the column.

## Stages

| # | Stage | Trigger | What user sees | Failure mode |
|---|-------|---------|----------------|--------------|
| 1 | Initial paint | Page load (`$(document).ready`) | "Next Batch" card with the first page of suggestions sorted by `SizeMB DESC NULLS LAST, PriorityScore DESC NULLS LAST` | Empty card with error toast if API fails |
| 2 | Search filter | User types in the search box (debounced ~300ms) | Suggestions refetch filtered to rows whose FileName or show-folder name matches; `TotalCandidates` count updates | Empty list with "No matches" message; clearing the search restores the full set |
| 3 | Batch-size change | User picks a value in the size selector (25/50/100/250/500) | Next refetch returns up to the new Limit; pagination resumes from offset 0 | Default selector to 100 if the request fails |
| 4 | Re-Analyze | User clicks "Re-Analyze" button | Same as initial paint, using the current Search + Limit | Toast surfaces the error; previous data stays |
| 5 | Auto-paginate | Client batch exhausted, `HasMore=true` | Next page fetched with same Search + Limit, incremented Offset; appended to displayed list | "No more candidates" message when offset exceeds total |
| 6 | Per-row remove | User clicks "x" on a row | Row hides client-side only; not sent to server. State lost on next refetch | Idempotent (no server effect) |
| 7 | Commit batch | User clicks "Add Batch" | `{Mode, ProfileId, MediaFileIds}` POSTs to `AddToQueue`; server runs one `INSERT...SELECT FROM MediaFiles` with NOT EXISTS dedup; queue grows; next batch auto-loads | Whole-batch failure surfaces in a toast (atomic insert; no partial success) |
| 8 | Queue all matching | User clicks "Queue All" on Card 1.5 | `{Mode:'Remux', Search, Drive}` POSTs to `QueueAllMatching`; server runs one `INSERT...SELECT` against the full cascade-filtered set; card refreshes | Whole-statement failure surfaces in a toast; confirm prompt before sending |

## Data Flow per Stage

```
Stage 1 (initial paint):
  JS              -> POST /api/ShowSettings/SmartPopulate {Drive:'T:', Limit:100, Offset:0}
  Controller      -> QueueManagementBusinessService.SmartPopulateQueue(Limit=100, Offset=0)
  Service         -> SQL: WHERE TranscodedByMediaVortex IS NOT TRUE
                          AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL)
                          AND m.SizeMB > 0
                          ORDER BY SizeMB DESC NULLS LAST, PriorityScore DESC NULLS LAST
                          LIMIT 100 OFFSET 0
  Service         -> rows -> Suggestions (each row carries PriorityScore from MediaFiles)
  JS              -> render rows with Priority badge

Stage 2 (search):
  JS              -> POST /api/ShowSettings/SmartPopulate {..., Search:'survivor'}
  Service         -> SQL adds: AND (LOWER(m.FileName) LIKE %s ESCAPE '!'
                                  OR LOWER(SUBSTRING(m.FilePath ...)) LIKE %s ESCAPE '!')
  Service         -> TotalCandidates count reflects filtered total

Stage 3 (batch-size change) and Stage 4 (Re-Analyze):
  Same as Stage 1, but Limit/Search reflect the current UI state.

Stage 5 (paginate):
  JS              -> POST /api/ShowSettings/SmartPopulate {..., Offset:Offset+Limit}
  Service         -> same recipe with new offset; HasMore = (Offset+len(rows)) < TotalCandidates

Stage 7 (commit):
  JS              -> POST /api/ShowSettings/AddToQueue {Mode, ProfileId, MediaFileIds:[...]}
  Controller      -> QueueManagementBusinessService.AddSuggestionsToQueue(MediaFileIds=...)
  Service         -> (Transcode + ProfileId) bulk-UPDATE MediaFiles.AssignedProfile;
                     INSERT INTO TranscodeQueue (...) SELECT ... FROM MediaFiles WHERE Id = ANY(%s)
                     AND NOT EXISTS (SELECT 1 FROM TranscodeQueue tq WHERE tq.FilePath = m.FilePath);
                     Priority is COALESCE(materialized PriorityScore, SizeMB-based fallback computed inline).
  -- Slim payload: server reads FilePath/SizeMB/Priority etc. from MediaFiles, not the request body.
  -- One INSERT statement, no per-item Python loop, no per-item DB lookup.

Stage 8 (queue all matching):
  JS              -> POST /api/ShowSettings/QueueAllMatching {Mode:'Remux', Search, Drive}
  Controller      -> QueueManagementBusinessService.QueueAllMatching(...)
  Service         -> INSERT INTO TranscodeQueue (...) SELECT ... FROM MediaFiles m
                     WHERE m.RecommendedMode = %s AND m.TranscodedByMediaVortex IS NOT TRUE
                       AND m.SizeMB > 0 AND m.HasExplicitEnglishAudio IS NULL OR true
                       AND NOT EXISTS (already-queued)
                       AND optional Search / Drive filters;
                     Priority via COALESCE(PriorityScore, size-based fallback).
  -- No client-side ID enumeration. Scales to the full candidate pool in one round-trip.
```

## Failure Modes

- **API 500 on SmartPopulate**: card retains last-good rows, toast shows the error message. User can click Re-Analyze to retry.
- **Empty result with filters**: card body shows "No matching candidates" (search) or "No untranscoded files left" (no search).
- **Slow query (>2s)**: spinner stays in card header; no implicit timeout. Operator sees a sluggish refresh and can investigate via DB Logs.
- **Stale display vs newly-queued**: when another worker/UI session adds a file to the queue between two SmartPopulate calls, the next call's `NOT IN TranscodeQueue` excludes it. No duplicate-suggestion bug.
- **Stale PriorityScore vs current AssignedProfile**: priority materialization recomputes on probe and on AssignedProfile change. Between those events, PriorityScore is the score for the file at the time of the last recompute. A file with NULL PriorityScore (never probed, or probed before this feature shipped) sorts last (NULLS LAST). The operator can trigger a backfill via the materialization admin endpoint.
- **No-audio files appearing as candidates**: Files with `HasExplicitEnglishAudio = false` are excluded by the SmartPopulate WHERE clause. Additionally, `_EvaluateCompliance` hard-blocks them so `RecommendedMode = NULL` (materialized). If a file's `HasExplicitEnglishAudio` is updated manually, `RecomputeForFiles([id])` must be called to clear `RecommendedMode`. Files with `HasExplicitEnglishAudio = NULL` (old probes) pass through -- they need a fresh probe to be properly classified.

## Out of Scope (intentional)

- Real-time push of queue/transcode progress into this card. The card is read-mostly with explicit refetch triggers.
- Per-row priority override from this UI.
- Profile-override-aware ordering. The PriorityScore reflects each file's AssignedProfile. If the operator picks a different profile in the dropdown to commit a batch, the displayed order is still ranked by AssignedProfile-relative priority -- which is acceptable because (a) the formula is log-scaled so the relative ranking is robust across profile choices and (b) the priority committed at queue time is recomputed authoritatively against the selected profile.
