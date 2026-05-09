# Priority Materialization -- denormalized PriorityScore on MediaFiles

## What It Does

Adds a denormalized `PriorityScore` integer column to `MediaFiles` that is
kept up to date by the system whenever any input to the priority formula
changes. Replaces the per-request priority computation pattern with a
read-only column that is indexable, paginate-friendly, and observable
system-wide.

The score is computed by the same `CalculatePriority` function defined in
`queue-priority.feature.md` -- this feature is about **storing and
maintaining** the value, not redefining it.

## Concern

Three concerns motivate materialization:

1. **Pagination correctness.** Sorting candidates by an unmaterialized
   priority requires either fetching all rows and sorting in memory, or
   computing priority in SQL (the formula uses `log10` and a per-resolution
   lookup that is awkward to express in SQL). Both approaches break down
   at library scale.
2. **Reuse.** Multiple features want "the most impactful next file" --
   today's queue, the SmartPopulate Next Batch card, future automation,
   reports. A single column keeps the answer consistent across consumers.
3. **Observability.** Operator can run
   `SELECT FilePath, PriorityScore FROM MediaFiles ORDER BY PriorityScore DESC LIMIT 20`
   from the SQL Queries page and see what the system thinks is most
   worth doing. Today this requires walking the queue or replaying the
   formula by hand.

## Surface

Internal infrastructure (no direct UI). Observable effects: a column on
MediaFiles, recompute behavior tied to existing pipeline events, and an
admin endpoint for full-library backfill. See `transcode.flow.md` Stage
3.5 for the pipeline integration.

## Success Criteria

### Schema

1. `MediaFiles.PriorityScore` column exists, type INTEGER, nullable. NULL
   means the row has not been scored yet (e.g. probed before this feature
   shipped, or probed but no AssignedProfile). Verifiable: `\d MediaFiles`
   shows the column with type integer and no NOT NULL constraint.

2. A partial index exists on
   `MediaFiles (PriorityScore DESC NULLS LAST, SizeMB DESC) WHERE
   TranscodedByMediaVortex IS NOT TRUE AND SizeMB > 0`. Verifiable:
   `\di MediaFiles*` lists the index; `EXPLAIN ANALYZE` of the
   SmartPopulate query shows it being used.

3. The migration script that adds the column and index is idempotent
   (uses `ADD COLUMN IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`).
   Verifiable: running the migration script twice on a fresh schema
   produces no errors and no duplicate objects.

### Compute function

4. `Features/TranscodeQueue/QueueManagementBusinessService.ComputePriorityScore(MediaFileId)`
   exists. It loads the MediaFile row and its AssignedProfile's
   per-resolution `ProfileThresholds`, calls `CalculatePriority`, and
   writes the result to `MediaFiles.PriorityScore` for that row. Pure
   side-effect-on-DB function -- given the same DB inputs, produces the
   same DB output.

5. When `MediaFile.AssignedProfile` is NULL or no `ProfileThresholds`
   row exists for the resolution category, `ComputePriorityScore`
   writes the fallback value (size * 0.5 -- per
   `queue-priority.feature.md` criterion 4) and emits a `LogWarning`
   naming the MediaFileId and missing input. Silent fallbacks forbidden
   per the loud-failure rule. Verifiable: nullify a row's
   AssignedProfile, call ComputePriorityScore, observe both the column
   write AND a Logs row.

6. A bulk variant `ComputePriorityScoresForFiles(MediaFileIds: List[int])`
   computes scores for many files in a single transaction, with one
   ProfileThresholds lookup cache for the duration of the call.
   Verifiable: scoring 1000 rows in a single call produces 1000 column
   writes and at most one DB round-trip per distinct profile-resolution
   pair (not 1000 lookups).

### Recompute hooks

7. **On probe completion**: when `MediaProbeBusinessService.ProbeFile`
   successfully writes a probe result for a MediaFile, it then invokes
   `ComputePriorityScore(MediaFileId)`. Verifiable: probe a single file,
   confirm `PriorityScore` is non-null after the probe completes (or
   has the fallback value with a warning logged if AssignedProfile is
   NULL).

8. **On AssignedProfile bulk-update** (`POST /api/Profiles/AssignProfileToRootFolder`,
   `POST /api/ShowSettings/Save`, `POST /api/ShowSettings/BulkUpdate`):
   after the AssignedProfile UPDATE, the affected MediaFileIds are
   passed to `ComputePriorityScoresForFiles`. Verifiable: assign a new
   profile to a folder containing 50 files, query
   `SELECT COUNT(*) FROM MediaFiles WHERE FilePath LIKE 'T:\NewFolder\%' AND PriorityScore IS NOT NULL`
   = 50 within seconds of the API call returning.

9. **On ProfileThresholds change** (any UPDATE to `ProfileThresholds`):
   the operator is offered an explicit "Recompute affected files"
   action; recompute does NOT happen automatically. The action calls
   the bulk admin endpoint (criterion 11) scoped to that profile's
   AssignedProfile filter. Verifiable: edit a ProfileThresholds row
   via the Profiles UI, observe a non-blocking notification or button
   offering recompute; click it, observe affected files' PriorityScore
   refresh.

10. **On AssignedProfile change for a single file** (rare -- this happens
    when QueueByFolder or AddSuggestionsToQueue assigns profiles to
    individual files at queue time per `transcode.flow.md` Stage 3 path
    3): `ComputePriorityScore` is invoked for that MediaFileId.
    Verifiable: queue a single file via the Add Job dialog with a
    profile that differs from any prior AssignedProfile; observe the
    MediaFile's PriorityScore update.

### Backfill

11. An admin endpoint `POST /api/PriorityMaterialization/Recompute`
    accepts an optional `ProfileName` (recompute only files whose
    AssignedProfile matches) or `Drive` (recompute only files whose
    FilePath starts with that drive prefix). With no parameters,
    recomputes the entire library. Returns
    `{Success, RowCount, ElapsedMs}`. Verifiable: call the endpoint
    with no filter on a fresh DB; observe `RowCount` equal to the
    count of MediaFiles rows.

12. The endpoint is gated behind a one-shot script `Scripts/SQLScripts/BackfillPriorityScores.py`
    that reads in batches (default 1000) and writes via a single UPDATE
    per batch. Verifiable: run the script on a 67k-row table; it
    completes in under 60 seconds wall-clock and uses bounded memory
    (no `SELECT *` materialization of the full table in memory).

13. The backfill is idempotent. Running it twice on the same DB state
    produces the same final column values. Verifiable: run, snapshot
    the column, run again, snapshot again, diff -- empty diff.

### Recompute lifecycle

14. The recompute hook never blocks the triggering operation. Probe
    completion writes the probe result and returns to the caller; the
    recompute happens in-line but its failure does not roll back the
    probe. Same for the AssignedProfile UPDATE path. Verifiable: induce
    a recompute failure (e.g. drop ProfileThresholds for the resolution
    transiently), confirm the probe/assign API call still returns
    Success=True and the MediaFile's probe / AssignedProfile column
    reflects the new value, even though PriorityScore was not updated.

15. A failed recompute (e.g. database error, missing inputs) leaves the
    PriorityScore column untouched -- it does NOT write NULL or zero,
    because that would silently downrank a file that previously had a
    valid score. Verifiable: induce a transient failure, confirm the
    column retains its prior value and a Logs row is emitted explaining
    the failure.

### No regression to existing priority math

16. The value written to `PriorityScore` for a (MediaFile, AssignedProfile)
    pair equals the value `CalculatePriority` returns when invoked with
    the same inputs at queue-write time. Verifiable: pick a file,
    inspect its PriorityScore; queue the file with its AssignedProfile;
    inspect the Priority value stored in TranscodeQueue -- both equal.

17. The TranscodeQueue.Priority value is still authoritative at claim
    time. Workers continue to claim by `ORDER BY Priority DESC,
    DateAdded ASC` from TranscodeQueue, NOT by MediaFiles.PriorityScore.
    Verifiable: review `Repositories/DatabaseManager.ClaimNextPendingTranscodeJob`
    -- the FROM clause is TranscodeQueue, the ORDER BY references
    TranscodeQueue.Priority. No change to worker claim path.

## Status

DRAFTED -- awaiting operator approval.

### Progress

- [x] Flow stage drafted (will land in `transcode.flow.md` Stage 3.5)
- [x] Feature doc drafted (this file)
- [x] Schema migration `Scripts/SQLScripts/AddPriorityScoreColumn.py` (idempotent ADD COLUMN). Run on 2026-05-09 -- 59195 MediaFiles rows.
- [x] `ComputePriorityScore(MediaFileId)` + `ComputePriorityScoresForFiles(MediaFileIds)` bulk variant in `QueueManagementBusinessService.py`. Bulk path uses pre-computed `_LoadPriorityLookupTable` cache and a single UPDATE FROM VALUES per batch.
- [x] `CalculatePriority` extended with `SuppressFallbackWarning=True` so bulk recompute emits one rolled-up warning per batch instead of per-row spam.
- [x] Probe-completion hook in `MediaProbeBusinessService._ExecuteProbe` (try/except -- failure logged but does not roll back probe per criterion 14).
- [x] AssignedProfile bulk-update hook in `ProfileRepository.UpdateMediaFilesProfileByRootFolder` (captures affected IDs before UPDATE, recomputes in 1000-row batches).
- [x] AssignedProfile single-file hook in `QueueManagementBusinessService.AddSuggestionsToQueue` (recomputes after MediaFile.AssignedProfile is set + saved).
- [x] `transcode.flow.md` extended with Stage 3.5 PRIORITY (and stage overview updated).
- [x] One-shot backfill script `Scripts/SQLScripts/BackfillPriorityScores.py` (batched, idempotent, --dry-run + --limit + --batch-size flags).
- [x] Live verified criterion 12: full backfill of 58195 rows in 7.5s (target <60s -- 8x headroom).
- [ ] Live verify criterion 7: probe a single file, observe PriorityScore updated for that row.
- [ ] Live verify criterion 8: bulk-assign a profile to a folder, confirm affected MediaFiles rows refreshed.
- [ ] Live verify criterion 14: induce recompute failure (e.g. delete ProfileThresholds row mid-flight), observe triggering operation still returns Success=True and prior PriorityScore unchanged.
- [ ] Live verify criterion 16: pick a file, queue it, confirm TranscodeQueue.Priority equals MediaFiles.PriorityScore for that (file, profile) pair.
- [ ] (Deferred) `POST /api/PriorityMaterialization/Recompute` admin endpoint -- backfill script covers the full-library case today; the admin endpoint is deferred until needed for finer-grained scope (e.g. recompute only one profile after threshold change).
- [ ] (Deferred) ProfileThresholds-change UI hook -- the Scripts/ backfill script is the MVP per criterion 9; UI offer can come later.

NEXT: WebService restart for live verifies of criteria 7, 8, 14, 16.
The deferred items (admin endpoint and threshold-change UI) are
not blockers for SmartPopulate consumption.

## Scope

```
Scripts/SQLScripts/AddPriorityScoreColumn.py                  -- (NEW) ADD COLUMN migration
Scripts/SQLScripts/BackfillPriorityScores.py                  -- (NEW) one-shot backfill
Features/TranscodeQueue/QueueManagementBusinessService.py     -- ComputePriorityScore + bulk variant
Features/MediaProbe/MediaProbeBusinessService.py              -- probe-completion hook
Features/Profiles/ProfilesController.py                       -- AssignProfileToRootFolder hook
Features/ShowSettings/ShowSettingsController.py               -- Save / BulkUpdate hooks
Features/PriorityMaterialization/                             -- (NEW) admin endpoint feature dir
  PriorityMaterializationController.py
  PriorityMaterializationBusinessService.py
transcode.flow.md                                              -- (UPDATED) new Stage 3.5
```

## Files

| File | Role |
|------|------|
| `Scripts/SQLScripts/AddPriorityScoreColumn.py` | Idempotent migration: `ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS PriorityScore INTEGER`. Logs current row count and how many rows have PriorityScore IS NULL after column add. |
| `Scripts/SQLScripts/BackfillPriorityScores.py` | One-shot batched backfill. Reads `SELECT Id FROM MediaFiles WHERE PriorityScore IS NULL ORDER BY Id LIMIT 1000`, calls `ComputePriorityScoresForFiles`, repeats. Logs progress every batch. |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | `ComputePriorityScore(MediaFileId)` -- single-file recompute. `ComputePriorityScoresForFiles(MediaFileIds)` -- bulk variant with profile-thresholds cache. Both write to MediaFiles.PriorityScore. Reuse existing `CalculatePriority`. |
| `Features/MediaProbe/MediaProbeBusinessService.py` | After successful `ProbeFile` write, invoke `ComputePriorityScore(MediaFileId)`. In-line. Failure logged but does not roll back probe. |
| `Features/Profiles/ProfilesController.py` | `AssignProfileToRootFolder` -- after the bulk UPDATE on MediaFiles, collect affected Ids and call `ComputePriorityScoresForFiles`. |
| `Features/ShowSettings/ShowSettingsController.py` | `Save` and `BulkUpdate` -- after AssignedProfile changes, recompute affected. |
| `Features/PriorityMaterialization/PriorityMaterializationController.py` | (NEW) `POST /api/PriorityMaterialization/Recompute` admin endpoint. Accepts optional `ProfileName` or `Drive` filter. |
| `Features/PriorityMaterialization/PriorityMaterializationBusinessService.py` | (NEW) Selects affected MediaFileIds in batches, calls `ComputePriorityScoresForFiles`, returns row count + elapsed time. |
| `transcode.flow.md` | (UPDATED) Insert Stage 3.5 PRIORITY between ASSIGN and QUEUE describing the recompute lifecycle. |

## Deviation from conventions

The new admin feature lives in `Features/PriorityMaterialization/` rather
than rolling into `Features/TranscodeQueue/` because the admin endpoint
spans probe + assign + queue paths, not just queue. This matches the
project's vertical-slice convention (one feature dir per cohesive surface).
