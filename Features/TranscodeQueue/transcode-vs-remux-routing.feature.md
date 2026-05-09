# No-Benefit Handling -- skip transcodes that won't save disk space

## What It Does

Two gates that stop the system from spending worker CPU on transcodes
that don't shrink files:

1. **Pre-flight gate** at queue-item creation -- if estimated savings is
   below a threshold, the file is either remuxed (container fix only,
   no re-encode) or skipped entirely.
2. **Post-flight gate** at FileReplacement -- if the actual transcoded
   output is the same size or larger than the source, the original is
   kept and the file is marked so future queue runs don't retry it.

A new `MediaFiles.LastTranscodeOutcome` column carries the post-flight
verdict; queue-population paths filter on it the same way they filter
on `TranscodedByMediaVortex IS NOT TRUE`.

Reuses the priority-materialization helpers and the existing
`Mode='Remux'` worker path. No new infrastructure -- just decision logic.

## Concern

Operator dogfood (2026-05-09): a 290 MB / 720p / h264 / 935 kbps MKV
would estimate ~27 MB savings against a typical 480p/720p target. That
is a "heavy transcode for minimal gain" case -- the workers would spend
hours and likely produce a same-size or larger output. The fix is to
detect those cases up front and either remux them (if the container
should change anyway) or skip them.

The post-flight gate exists because the formula has prediction error.
A file the formula said would save 200 MB might actually come out 50
MB larger. Today FileReplacement replaces unconditionally and we end
up with a bigger file than we started with. That has to stop.

**Related fix shipped 2026-05-09:** before this feature, the Remux path
copied audio with `-c:a copy` when the source codec was MP4-compatible,
which silently bypassed the `loudnorm`/`acompressor` filter chain. With
no-benefit routing more files to Remux, that gap would have expanded the
un-normalized portion of the library. `BuildRemuxCommand` and
`BuildSubtitleFixCommand` now always re-encode audio to AAC 128k so the
filter chain applies uniformly. See `Docs/AudioStrategy.md` decision
matrix. Audio re-encode is cheap (~5-20 seconds per hour of content)
relative to video, so the cost is negligible.

## Surface

Mostly internal pipeline behavior in `transcode.flow.md` Stages 4 and 7.
Thin user-visible surfaces:

- `POST /api/MediaFiles/<id>/ResetTranscodeOutcome` -- operator override
- Observable on `/ShowSettings` Card 1: files at or below threshold no
  longer appear; remux candidates show with `Mode='Remux'`
- `LogWarning` rows when post-flight gate fires (loud-failure rule)
- `MediaFiles.LastTranscodeOutcome` queryable from the SQL Queries page

## Success Criteria

### Pre-flight gate (at queue-item creation)

1. A new helper -- `QueueManagementBusinessService._DecideQueueMode(MediaFile, ProfileSettings) -> {'Mode': str, 'Reason': str} | None` -- is called by every queue-entry path. The function reads `SystemSetting('MinTranscodeSavingsMB')` (default 150) and `SystemSetting('CompatibleContainers')` (default `'mp4,mov,m4v'`). Pure function in the formula sense -- given the same inputs, returns the same output.

2. When estimated savings is **at or above** the threshold, `_DecideQueueMode` returns `{'Mode': 'Transcode', 'Reason': 'EstimatedSavingsAboveThreshold'}`. Verifiable: pick a file where `(SizeMB - target_size_mb) >= 150`, call the helper, observe `Mode='Transcode'`.

3. When estimated savings is **below** the threshold AND the source container (case-insensitive match against `MediaFiles.ContainerFormat`) is in the compatible list, `_DecideQueueMode` returns `None` (skip). The caller does not create a queue item. Verifiable: pick a file with `ContainerFormat='mp4'` and `(SizeMB - target_size_mb) < 150`, call any queue-entry endpoint targeting that file -- the response reports it skipped, no row appears in TranscodeQueue, and one `LogInfo` row exists naming the MediaFileId and reason "AlreadyOptimal".

4. When estimated savings is below the threshold AND the source container is **not** in the compatible list, `_DecideQueueMode` returns `{'Mode': 'Remux', 'Reason': 'BelowThresholdRemuxOnly'}`. The caller creates a queue item with `ProcessingMode='Remux'`. Verifiable: pick a file with `ContainerFormat='mkv'` and `(SizeMB - target_size_mb) < 150`, queue it via any entry path, observe a TranscodeQueue row with `ProcessingMode='Remux'`.

5. The operator's MKV example case (290 MB, 720p, h264, 935 kbps, MKV container) routed through the SmartPopulate -> AddSuggestionsToQueue path with a typical 720p/480p profile selected lands as `Mode='Remux'`, not `Mode='Transcode'`. Verifiable: ad-hoc -- find a row matching that shape, queue it through Card 1 + a chosen profile, observe the queue row.

6. `_DecideQueueMode` is called from all four queue-entry sites:
   - `CreateQueueItemFromMediaFileWithProfile` (full populate)
   - `AddSuggestionsToQueue` (SmartPopulate / Card 1)
   - `AddJobToQueue` (Add Job dialog / Card 2 per-row +)
   - `QueueByFolder` (Card 2 bulk)
   Verifiable: searching the codebase for `def _DecideQueueMode` shows exactly one definition; searching for callers shows the four sites listed (and any helpers they call into).

### Estimated-savings calculation

7. The estimated-savings formula matches the priority calculation -- both call a single shared helper `_EstimateTargetSizeMb(durationMinutes, videoKbps, audioKbps) -> float`. Extracting this helper is part of the implementation. Verifiable: `CalculatePriority` and `_DecideQueueMode` both invoke `_EstimateTargetSizeMb` for the target size; no duplicated arithmetic.

8. When any input to the savings calculation is missing (NULL `DurationMinutes`, NULL `AssignedProfile`, no matching `ProfileThresholds` row, or NULL `VideoBitrateKbps`), `_DecideQueueMode` returns `None` (skip) and emits a `LogWarning` naming the MediaFileId and missing input. The caller does not queue the file. Verifiable: nullify a row's DurationMinutes, queue it via Add Job -- response reports skipped, Logs row exists, no TranscodeQueue row.

### Post-flight gate (at FileReplacement)

9. `FileReplacementBusinessService.ProcessFileReplacementWithVMAF` checks `attempt.NewSizeMB >= attempt.OriginalSizeMB` immediately before the archive/delete/move steps. When the comparison is true, the function returns `{'Success': False, 'Reason': 'NoSavings'}` (or equivalent) WITHOUT archiving, deleting, or moving anything. Verifiable: synthesize a TranscodeAttempt where `NewSizeMB > OriginalSizeMB`, invoke ProcessFileReplacementWithVMAF, observe the original file untouched on disk and no MediaFilesArchive insert.

10. When the post-flight gate fires, the staged transcoded file is deleted from its temporary location (no orphan files left around). Verifiable: induce the gate, observe the file at `attempt.TranscodedFilePath` (or wherever the staged output lives) is gone after the call returns.

11. When the post-flight gate fires, `MediaFiles.LastTranscodeOutcome` is set to `'NoSavings'` for that MediaFileId. Verifiable: induce the gate, query `SELECT LastTranscodeOutcome FROM MediaFiles WHERE Id = X` -- value is `'NoSavings'`.

12. When the post-flight gate fires, a `LogWarning` row is emitted naming the MediaFileId, the OriginalSizeMB, the NewSizeMB, the configured profile name, and the message "Transcode produced no savings -- formula prediction error, original kept." Loud-failure rule applies. Verifiable: induce the gate, query Logs for the MediaFileId.

13. When `attempt.NewSizeMB < attempt.OriginalSizeMB` (today's normal case), the post-flight gate is a no-op. The replacement proceeds exactly as today. Verifiable: existing happy-path tests pass without modification.

### Schema and queue-population filter

14. `MediaFiles.LastTranscodeOutcome` column exists, type `VARCHAR(32)`, nullable. NULL means "never attempted by us" (or attempted and replaced successfully -- in which case `TranscodedByMediaVortex` is the relevant marker). Verifiable: `\d MediaFiles` shows the column.

15. The migration script that adds the column is idempotent (`ADD COLUMN IF NOT EXISTS`). Running it twice on a fresh schema is a no-op. Verifiable: run the migration script twice, no errors, no duplicate columns.

16. Every queue-entry path's WHERE clause includes `AND COALESCE(LastTranscodeOutcome, '') != 'NoSavings'` (or equivalent IS DISTINCT FROM check). The check lives in the same single helper that already enforces `TranscodedByMediaVortex IS NOT TRUE`, so adding it is one place. Verifiable: searching the codebase for the new predicate shows it in the helper definition and not duplicated in caller queries.

17. The SmartPopulate partial index `idx_mediafiles_smartpopulate` is updated (or replaced) so the WHERE clause `TranscodedByMediaVortex IS NOT TRUE AND SizeMB > 0 AND COALESCE(LastTranscodeOutcome, '') != 'NoSavings'` still uses the index. Verifiable: `EXPLAIN ANALYZE` of the SmartPopulate query continues to show `Index Scan` or `Bitmap Index Scan`, not `Seq Scan on mediafiles`.

### Operator override

18. `POST /api/MediaFiles/<id>/ResetTranscodeOutcome` accepts a MediaFileId path parameter, clears `LastTranscodeOutcome` for that row (sets it to NULL), and returns `{Success, Message}`. Verifiable: mark a file `'NoSavings'`, call the endpoint, query MediaFiles -- the column is NULL.

19. The reset endpoint is operator-triggered only -- it does not auto-fire on profile change, threshold change, or any other system event. The operator decides when a previously-skipped file should be retried. (No automatic reset is in scope for this feature; it would be a separate decision.) Verifiable: change a profile or threshold, observe `LastTranscodeOutcome` stays `'NoSavings'` until the endpoint is called.

### SystemSettings

20. `SystemSetting('MinTranscodeSavingsMB')` reads the threshold (integer, default 150). Changes take effect at the next queue-entry call -- no service restart required. Verifiable: set the value to 50, queue a borderline file (e.g. 100 MB estimated savings), observe `Mode='Transcode'`; reset to 150, queue it again (after a reset of LastTranscodeOutcome) -- observe Remux/Skip.

21. `SystemSetting('CompatibleContainers')` reads a comma-separated case-insensitive list (default `'mp4,mov,m4v'`). The pre-flight gate compares the source `ContainerFormat` to this list when deciding remux-vs-skip. Verifiable: add `'avi'` to the setting, queue a low-savings AVI file -- observe it skipped; remove `'avi'`, queue again -- observe `Mode='Remux'`.

### Reporting (no new UI in this feature)

22. The operator can query no-savings files from the SQL Queries page using:
    `SELECT FilePath, SizeMB, AssignedProfile, LastTranscodeOutcome FROM MediaFiles WHERE LastTranscodeOutcome = 'NoSavings' ORDER BY SizeMB DESC`
    No dedicated UI is built in this feature; if the result set grows large enough to warrant a page, that's a follow-up. Verifiable: run the query, get results.

## Status

DRAFTED -- awaiting operator approval.

### Progress

- [x] Operator-approved design (2026-05-09): 150 MB threshold, two gates, override endpoint, no new UI in scope
- [x] `transcode.flow.md` Stage 4 + Stage 7 extended with the new gates
- [x] Feature doc drafted (this file)
- [ ] Operator approves criteria 1-22
- [ ] Schema migration `Scripts/SQLScripts/AddLastTranscodeOutcomeColumn.py` (idempotent ADD COLUMN)
- [ ] SystemSettings seeds: `MinTranscodeSavingsMB=150`, `CompatibleContainers='mp4,mov,m4v'` (idempotent INSERT ... ON CONFLICT)
- [ ] Extract `_EstimateTargetSizeMb` helper in `QueueManagementBusinessService.py` (reused by CalculatePriority and _DecideQueueMode)
- [ ] Implement `_DecideQueueMode(MediaFile, ProfileSettings)` helper
- [ ] Wire pre-flight gate into all four queue-entry sites: CreateQueueItemFromMediaFileWithProfile, AddSuggestionsToQueue, AddJobToQueue, QueueByFolder
- [ ] Add post-flight gate to `FileReplacementBusinessService.ProcessFileReplacementWithVMAF` (before archive/delete/move steps)
- [ ] Add no-savings filter to the queue-population WHERE-clause helper (single helper, same place TranscodedByMediaVortex IS NOT TRUE lives)
- [ ] Drop and recreate `idx_mediafiles_smartpopulate` partial index with the LastTranscodeOutcome predicate added (so the index still covers the full WHERE)
- [ ] `POST /api/MediaFiles/<id>/ResetTranscodeOutcome` endpoint
- [ ] Live verify criterion 5: queue the operator's 290 MB MKV example, observe Mode='Remux'
- [ ] Live verify criterion 9: induce a NewSizeMB >= OriginalSizeMB attempt, observe gate fires and original is untouched
- [ ] Live verify criterion 17: EXPLAIN ANALYZE still shows Index Scan after partial-index recreation
- [ ] Live verify criterion 20: change MinTranscodeSavingsMB at runtime, observe behavior change without restart
- [ ] Live verify criterion 22: SQL query returns no-savings rows

NEXT: operator approval to start implementation. Recommended order:
schema migration + system-setting seeds -> shared `_EstimateTargetSizeMb` helper -> `_DecideQueueMode` -> wire into 4 entry paths -> post-flight gate -> queue-population filter + partial-index update -> override endpoint -> live verifies.

## Scope

```
Features/TranscodeQueue/no-benefit-handling.feature.md          -- (NEW) this file
Features/TranscodeQueue/QueueManagementBusinessService.py       -- _EstimateTargetSizeMb, _DecideQueueMode, 4 queue-entry callers, queue-population WHERE-clause helper
Features/TranscodeQueue/TranscodeQueueController.py             -- AddJobToQueue route consumes _DecideQueueMode result
Features/ShowSettings/ShowSettingsController.py                 -- AddToQueue + QueueByFolder routes consume _DecideQueueMode result
Features/FileReplacement/FileReplacementBusinessService.py      -- post-flight gate before archive/delete/move
Features/MediaFiles/                                             -- (NEW dir) MediaFilesController.py with ResetTranscodeOutcome route
Repositories/DatabaseManager.py                                  -- GetTranscodeQueueItemsPaginated WHERE-clause uses the shared helper; SmartPopulate partial index recreate
Scripts/SQLScripts/AddLastTranscodeOutcomeColumn.py             -- (NEW) ADD COLUMN migration
Scripts/SQLScripts/AddSmartPopulateIndex.py                     -- (UPDATED) drop + recreate partial index with LastTranscodeOutcome predicate
transcode.flow.md                                                -- (UPDATED) Stage 4 + Stage 7 gate descriptions
```

## Files

| File | Role |
|------|------|
| `Scripts/SQLScripts/AddLastTranscodeOutcomeColumn.py` | (NEW) Idempotent migration: `ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS LastTranscodeOutcome VARCHAR(32)`. Logs row count and how many rows have non-NULL value after add. |
| `Scripts/SQLScripts/AddSmartPopulateIndex.py` | (UPDATED) Drop and recreate `idx_mediafiles_smartpopulate` so the partial-index WHERE clause matches the new query (adds `AND COALESCE(LastTranscodeOutcome, '') != 'NoSavings'`). EXPLAIN ANALYZE before/after. |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | New `_EstimateTargetSizeMb` helper extracted from CalculatePriority. New `_DecideQueueMode(MediaFile, ProfileSettings)` helper. New `_NoSavingsWhereClause()` helper appended to existing TranscodedByMediaVortex predicate. Four queue-entry callers updated to consult `_DecideQueueMode` and act on its result. |
| `Features/TranscodeQueue/TranscodeQueueController.py` | `AddJob` route: when `_DecideQueueMode` returns None, response includes `Skipped=True` and the reason; when it returns Mode='Remux', response confirms the remux mode. |
| `Features/ShowSettings/ShowSettingsController.py` | `AddToQueue` and `QueueByFolder` route response shapes updated to include skip/remux counts so the UI can render an honest "added: X transcode, Y remux, Z skipped (already optimal)" message. |
| `Features/FileReplacement/FileReplacementBusinessService.py` | `ProcessFileReplacementWithVMAF`: post-flight gate before the archive/delete/move sequence. When `NewSizeMB >= OriginalSizeMB`: delete staged output, set `MediaFiles.LastTranscodeOutcome='NoSavings'`, LogWarning, return `Success=False, Reason='NoSavings'`. |
| `Features/MediaFiles/MediaFilesController.py` | (NEW) Flask Blueprint with one route: `POST /api/MediaFiles/<id>/ResetTranscodeOutcome`. Sets `LastTranscodeOutcome = NULL` for the given Id. Returns `{Success, Message}`. |
| `Repositories/DatabaseManager.py` | `GetTranscodeQueueItemsPaginated` and any other MediaFiles read paths consume the shared `_NoSavingsWhereClause` so the predicate isn't duplicated. |
| `transcode.flow.md` | (UPDATED in this PR) Stage 4 safety-guards summary lists the new gates; Stage 7 step list includes the post-flight gate at the correct ordinal position before archive/delete. |

## Deviation from conventions

`Features/MediaFiles/` is a new feature directory created just for the
override endpoint. The existing codebase has no Features/MediaFiles/
folder despite MediaFiles being a core table -- queries against it are
spread across DatabaseManager, MediaProbeRepository, etc. Adding a
single-file feature dir for one route is a small precedent for a future
MediaFiles vertical slice. If that direction is wrong, the route can
move into Features/TranscodeQueue/ instead -- the override conceptually
belongs to "queue eligibility," not to MediaFiles itself.
