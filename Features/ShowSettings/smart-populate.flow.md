# Flow: Smart Populate Next Batch (/ShowSettings)

**Slug:** smart-populate

## Entry Point

`Templates/ShowSettings.html` -- the Quick Fix card (`Mode='Quick'` + `Focus`),
the legacy Remux card (`Mode='Remux'`), and the legacy AudioFix card
(`Mode='AudioFix'`) all surface ranked candidates scoped by their respective
`MediaFiles` flags and accept the user's commit to the queue.

API entry: `POST /api/ShowSettings/SmartPopulate` ->
`Features/ShowSettings/ShowSettingsController.SmartPopulateQueue` ->
`Features/TranscodeQueue/QueueManagementBusinessService.SmartPopulateQueue`.

The endpoint accepts a `Mode` parameter (`Quick` | `Remux` | `AudioFix` |
`Transcode`) that filters to the matching `MediaFiles` flag and routes the
resulting queue items to the corresponding `ProcessingMode`. Each card hits
the same endpoint with its own `Mode` value plus independent state
(search, batch size, offset).

**Scope note.** The Transcode pane's TV / Movies "Next Batch" cards do NOT
go through this flow. They consume the purpose-built
`POST /api/ShowSettings/NextTranscodeBatch` endpoint (WHERE `NeedsTranscode = TRUE`,
ORDER BY `SizeMB DESC NULLS LAST`, partial index
`idx_mediafiles_next_transcode_batch`). See
`Features/TranscodeQueue/next-batch-per-drive.feature.md` for that surface.
The stages, seams, and failure modes below describe the SmartPopulate path
only -- they apply to the Quick Fix / Remux / AudioFix cards.

The ranking value (`MediaFiles.PriorityScore`) is **maintained
continuously** by the priority materialization pipeline -- see
`transcode.flow.md` Stage 3.5 and
`Features/TranscodeQueue/priority-materialization.feature.md`. SmartPopulate
itself never computes priority; it only reads the column.

## Stages

| ID | Stage | Trigger | What user sees | Failure mode |
|---|-------|---------|----------------|--------------|
| ST1 | Initial paint | Page load (`$(document).ready`) | "Next Batch" card with the first page of suggestions sorted by `SizeMB DESC NULLS LAST, PriorityScore DESC NULLS LAST` | Empty card with error toast if API fails |
| ST2 | Search filter | User types in the search box (debounced ~300ms) | Suggestions refetch filtered to rows whose FileName or show-folder name matches; `TotalCandidates` count updates | Empty list with "No matches" message; clearing the search restores the full set |
| ST3 | Batch-size change | User picks a value in the size selector (25/50/100/250/500) | Next refetch returns up to the new Limit; pagination resumes from offset 0 | Default selector to 100 if the request fails |
| ST4 | Re-Analyze | User clicks "Re-Analyze" button | Same as initial paint, using the current Search + Limit | Toast surfaces the error; previous data stays |
| ST5 | Auto-paginate | Client batch exhausted, `HasMore=true` | Next page fetched with same Search + Limit, incremented Offset; appended to displayed list | "No more candidates" message when offset exceeds total |
| ST6 | Per-row remove | User clicks "x" on a row | Row hides client-side only; not sent to server. State lost on next refetch | Idempotent (no server effect) |
| ST7 | Commit batch | User clicks "Add Batch" | `{Mode, ProfileId, MediaFileIds}` POSTs to `AddToQueue`; server runs one `INSERT...SELECT FROM MediaFiles` with NOT EXISTS dedup; queue grows; next batch auto-loads | Whole-batch failure surfaces in a toast (atomic insert; no partial success) |
| ST8 | Queue all matching | User clicks "Queue All" on Card 1.5 | `{Mode:'Remux', Search, Drive}` POSTs to `QueueAllMatching`; server runs one `INSERT...SELECT` against the full cascade-filtered set; card refreshes | Whole-statement failure surfaces in a toast; confirm prompt before sending |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1/ST2/ST5` -> SQL fetch | `QueueManagementBusinessService.SmartPopulateQueue` | JSON body: `{Mode, Drive, Limit, Offset, Search}` | SQL recipe reads `MediaFiles` filtered to `RecommendedMode=Mode`, `TranscodedByMediaVortex IS NOT TRUE`, not already queued; orders by `SizeMB DESC NULLS LAST, PriorityScore DESC NULLS LAST` | DevTools Network: response carries `{Suggestions, TotalCandidates, HasMore}` with rows ordered as documented |
| S2 | `ST1` reads `MediaFiles.PriorityScore` | Priority materialization pipeline (`transcode.flow.md::ST4`) | `MediaFiles.(PriorityScore INTEGER NULL, RecommendedMode TEXT NULL)` populated by `priority-materialization.feature.md` | This flow only READS PriorityScore -- never writes | `SELECT COUNT(*) FROM MediaFiles WHERE PriorityScore IS NULL AND RecommendedMode IS NOT NULL` = 0 in steady state |
| S3 | `ST7 -> transcode.S1` (commit -> queue) | `AddSuggestionsToQueue` runs `INSERT INTO TranscodeQueue ... SELECT ... FROM MediaFiles WHERE Id = ANY(%s) AND NOT EXISTS (already queued)` | Per row: `TranscodeQueue.(MediaFileId, AssignedProfile, ProcessingMode, Priority, Status='Pending', DateAdded=NOW())` | Workers claim through `transcode.flow.md::S1` (`ClaimNextPendingTranscodeJob`) | Browser Network: response `{Success:true, InsertedCount:N}`; SQL `SELECT COUNT(*) FROM TranscodeQueue WHERE Status='Pending' AND MediaFileId = ANY(...)` matches `InsertedCount` |
| S4 | `ST8` (Queue All) | `QueueAllMatching` runs one cascading INSERT...SELECT against the full filter set | Same shape as S3 but no client ID list -- server filters | Same as S3 -- workers don't care how rows arrive | Same SQL verification but row count = `TotalCandidates` from S1 |
| S5 | dedup invariant | `NOT EXISTS (SELECT 1 FROM TranscodeQueue tq WHERE tq.FilePath = m.FilePath)` | Prevents duplicate queue rows per file | Operator sees no double-queueing | `SELECT FilePath, COUNT(*) FROM TranscodeQueue WHERE Status='Pending' GROUP BY FilePath HAVING COUNT(*) > 1` -> 0 |
| S6 | `ST1/ST5` query performance gate | (operator-maintained DB index) | `CREATE INDEX idx_mediafiles_pending_size ON MediaFiles (TranscodedByMediaVortex, SizeMB DESC) WHERE TranscodedByMediaVortex IS NOT TRUE` (partial index) -- the SmartPopulate query orders by `SizeMB DESC NULLS LAST` and filters on `TranscodedByMediaVortex IS NOT TRUE`; without the partial index, full table scans across ~67k rows | Service-side: query returns under 200ms p95 | EXPLAIN ANALYZE the SmartPopulate query on production; expect Index Scan, not Seq Scan; without the index the first page-load on `/ShowSettings` takes >2s and the search debounce piles up |
| S7 | `RecommendedMode` write coupling (cascade dependency) | `QueueManagementBusinessService._EvaluateCompliance` writes `MediaFiles.(IsCompliant, RecommendedMode)` after every probe + every replacement (`transcode.flow.md::ST4` recompute) | `MediaFiles.RecommendedMode TEXT NULL IN ('Transcode','Remux','AudioFix',NULL)` -- NULL = "not yet evaluated OR already compliant" (two semantically distinct states share the same value) | This flow's SQL filters by `RecommendedMode=%s`; rows with NULL are silently excluded | **Non-obvious failure mode:** a profile change on a file does NOT auto-trigger recompute; the file's `RecommendedMode` stays at its old cascade verdict. SmartPopulate then either hides or shows the file based on stale routing. Workaround: operator runs `RecomputeForFiles([ids])` admin endpoint after a profile change. Verify: `SELECT RecommendedMode FROM MediaFiles WHERE Id=<id>` before vs after a profile change AND a recompute |
| S8 | client-side state persistence | `localStorage.ShowSettings.BatchSize` + `.MoviesBatchSize` writes | Per-card batch size (default 100, max 1000) | Stages `ST3/ST5` use the stored value for `Limit` parameter | **Non-obvious:** the priority-ranking *server-side* sort is stable, but a too-large client batch (operator sets 1000) causes initial paint to fetch 1000 rows in one shot, which can saturate the WebService DB connection pool if multiple operators load `/ShowSettings` simultaneously. **Cap is enforced server-side too:** `min(client_limit, 1000)`. Verify: `localStorage.setItem('ShowSettings.BatchSize', '5000')`, reload, observe response carries `Suggestions.length <= 1000` |
| S9 | `ST7` priority preserved across modes | `AddSuggestionsToQueue` writes `Priority = COALESCE(MediaFiles.PriorityScore, sizeMB-based fallback)` per `queue-priority.feature.md` | `TranscodeQueue.Priority INTEGER NOT NULL` in range [1, 200]; 195-200 reserved for manual operator overrides | Workers claim `ORDER BY Priority DESC, DateAdded ASC` (`transcode.flow.md::S1`) | **Non-obvious:** if `MediaFiles.PriorityScore` is NULL (pre-materialization row), the fallback gives a SIZE-based priority -- which means an unscored 8GB 4K file outranks a scored 500MB high-savings file. Run `Scripts/Backfill/PriorityScore.py` to eliminate NULL scores; verify `SELECT COUNT(*) FROM MediaFiles WHERE PriorityScore IS NULL AND RecommendedMode IS NOT NULL` = 0 |

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
