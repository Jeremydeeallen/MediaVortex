# Transcode Queue

**Slug:** transcodequeue

## What It Does

Populates and manages the queue of files awaiting FFmpeg transcoding. Filters files by resolution against profile thresholds, enforces safety guards, and provides queue management controls.

## Success Criteria

1. PopulateQueue filters MediaFiles by comparing their Resolution against the assigned profile's ProfileThresholds.TranscodeDownTo to determine which files need transcoding.
2. Files without explicit English audio (HasExplicitEnglishAudio = false) are blocked from queue population. Files with NULL (not yet probed) are allowed through.
3. Files where the video stream was re-encoded by MediaVortex (TranscodedByMediaVortex = true) with VMAF >= 80 are not re-queued. A file that has only been remuxed / audio-fixed (RemuxedByMediaVortex = true, TranscodedByMediaVortex = false) remains eligible for transcode admission -- the remux flag does not satisfy the "already transcoded" predicate. See `Features/FileReplacement/remuxed-flag.feature.md` for the two-flag model.
4. Files with VMAF < 80 get CRF adjustment. Adjusted CRF cannot go below 15 -- files that would need lower CRF are logged as ProblemFiles.
5. Queue items are sortable by size, priority, and date added.
6. Queue supports pagination (10/25/50/100 per page).
7. Bulk operations are available: clear entire queue, remove items by file size threshold, cleanup duplicates.
8. Navigation bar shows a live queue count badge that refreshes automatically.
9. The `/Queue` page (legacy `/TranscodeQueue` 301-redirects here) renders four stacked cards in a single host container -- one per ProcessingMode family: `Transcode`, `Remux`, `Audio` (AudioFix), `VMAF`. Each card carries: (a) a left grip-handle that makes the card draggable; drop-on-card reorders the cards within the host and persists the new order to `localStorage['MvQueueOrder']`. (b) A chevron toggle that collapses the card body (table + pagination); state persists per-card key to `localStorage['MvQueueCollapsed']`. **All four cards default to collapsed** when no prior collapse state exists -- the page opens to a four-row summary view, operator expands the queues they want to act on. (c) A summary line in the header showing `(<PendingCount> pending • <RunningCount> running • <TotalSizeGB> total)` for the three TranscodeQueue cards, `(<PendingCount> pending • <RunningCount> running • <FailedCount> failed)` for the VMAF card. (d) A count badge showing `<TotalCount> items`. Summary + badge are populated from `/api/TranscodeQueue/AggregateStats?mode=<Mode>` (per TranscodeQueue card) and `/api/QualityTest/AggregateStats` (VMAF card); both are single-query aggregate endpoints (GROUP BY Status + SUM(SizeMB)) so the summary reflects whole-queue totals, not just the visible page. Verifiable: `curl /Queue` renders four `.queue-card` elements with `data-key` values `Transcode`, `Remux`, `Audio`, `VMAF`; first load shows all four with `.collapsed` class; `/api/TranscodeQueue/AggregateStats?mode=AudioFix` returns `{Success: true, Data: {TotalCount, PendingCount, RunningCount, FailedCount, TotalSizeMB}}` with non-zero values when AudioFix queue is non-empty.
10. **[BUG-0061]** Encode-failure retry has a configurable cap (sibling to `PostTranscodeGateConfig.MaxRequeueAttempts`, default 3) counting consecutive `TranscodeAttempts.Success=FALSE` rows since the last `Success=TRUE` (or since file creation if no prior success). The cap is consulted in BOTH `ClaimNextPendingTranscodeJob` (skip Pending rows whose MediaFile has exceeded cap) AND `QueueManagementBusinessService.RecomputeForFiles` (do not INSERT a new queue row for a MediaFile that has exceeded cap). Capped MediaFiles surface in an operator-visible "Failed Jobs" panel with filename, failure count, last ErrorMessage, last AttemptDate, AssignedProfile, last WorkerName; operator can reset (re-allow next claim) or view full attempt log. Verifiable: live DB query `SELECT MediaFileId, COUNT(*) FROM TranscodeAttempts WHERE Success=FALSE GROUP BY MediaFileId HAVING COUNT(*) > <cap>` returns zero rows that also appear in `TranscodeQueue` with `Status='Pending'`.

## Concurrency Notes

The TranscodeQueue admission path has two known TOCTOU windows that are explicitly accepted as known debt under the single-operator dev-system stance.

1. **AdmitOne check-then-insert race.** `QueueAdmissionRepository.AdmitOne` (deleted; replaced by routing through `QueueManagementBusinessService.AddJobToQueue` per `transcode-worker-unification` directive) performed a SELECT-existing-Pending then INSERT-if-absent without a unique index on (MediaFileId, Status='Pending'). Two concurrent admissions could both INSERT. The replacement `AddJobToQueue` has the same shape; production-safe fix would be a partial unique index `(MediaFileId) WHERE Status='Pending'`. Mitigation: single-operator dev box; one admission UI; not observed in practice.

2. **AdmitSeries candidate-count window.** Before/after candidate counting (`BeforeCandidates - AfterCandidates`) is used to compute `Inserted`. Under concurrent admissions on the same series, the `Inserted` count can over-state actual inserts (concurrent peer admitted a row between our counts; our INSERT-NOT-EXISTS guard prevents duplicates but our count reports the candidate that we DIDN'T actually insert). Mitigation: same as above.

Both windows accept the single-operator dev-system as the mitigation. Multi-operator or production deployments would require partial unique indexes + count-by-rowcount-returning patterns. The accept-as-debt decision is recorded in `.claude/directives/closed/2026-06-28-transcode-worker-unification.md` (will archive there on close).

## Status

COMPLETE

## Scope

```
Features/TranscodeQueue/**
```

## Files

| File | Role |
|------|------|
| Features/TranscodeQueue/TranscodeQueueController.py | Flask Blueprint -- queue endpoints |
| Features/TranscodeQueue/TranscodeQueueBusinessService.py | Queue population logic, safety guards |
| Features/TranscodeQueue/TranscodeQueueRepository.py | TranscodeQueue database queries |
| Templates/Queue.html | Queue UI page |

## Cross-Vertical Contract

### Columns the TranscodeQueue vertical WRITES

| Column | Written by |
|---|---|
| TranscodeQueue row INSERT/DELETE/UPDATE | QueueManagementBusinessService.PopulateQueue + AddSuggestionsToQueue + claim path |
| MediaFiles.PriorityScore | RecomputeForFiles writes the materialized priority |
| AudioFixPriorityHints.* | PinAudioFixFolder |

### Columns the TranscodeQueue vertical READS from external tables

| Column | Read by | Owner |
|---|---|---|
| MediaFiles.{WorkBucket, IsCompliant, AssignedProfile, AudioCompliant, VideoCompliant, ContainerCompliant} | Queue admission + claim path | per-vertical writes; WorkBucket+IsCompliant are GENERATED |
| Profiles.* + ProfileThresholds.* | _LoadPriorityLookupTable | Profiles vertical |
| Workers.{TranscodeEnabled, Status, ProfileAllowlist} | Claim query | Workers data accessor |

### Stable function entry points

| Class.method | External caller(s) |
|---|---|
| QueueManagementBusinessService.RecomputeForFiles(ids) -> int | MediaProbe post-flight; FileReplacement post-rename re-probe |
| QueueManagementBusinessService.EvaluateCandidateCompliance(row) -> dict | FileReplacement.ComplianceGate.Evaluate |
| QueueManagementBusinessService.PopulateQueue / NextTranscodeBatch / SmartPopulateQueue | Operator UI buttons |

### HTTP API surface

| Method + URL | Purpose |
|---|---|
| GET /api/TranscodeQueue/GetQueue | Paginated queue list |
| POST /api/TranscodeQueue/Clear | Clear queue |
| POST /api/TranscodeQueue/AudioFix/PinFolder | Pin AudioFix folder |
| POST /api/WorkBucket/NextTranscodeBatch | Smart batch admission |

### What is EXPLICITLY NOT a contract

- The internal SQL of PopulateQueue / NextTranscodeBatch -- changes freely
- _GetEffectiveProfileFromCache cache invalidation -- internal
- Priority-score formula coefficients -- tunable; defined in queue-priority.feature.md
- The exact set of admission predicates -- documented in companion feature docs
