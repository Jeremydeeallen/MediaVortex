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

11. **[BUG-0078]** `QueueManagementBusinessService.AddJobToQueue(ForceAdd=True)` bypasses BOTH the marginal-savings gate AND the RetranscodeDecider VMAF>=80 gate. When invoked against a MediaFile whose latest `TranscodeAttempt` has `VMAF >= 80`, the function inserts a `TranscodeQueue` row and returns `{Success: True, Skipped: False, ItemId: <int>}`; a WARN log records the override (`Force adding ... despite VMAF>=80 on latest attempt (VMAF gate overridden)`). Symmetrically, `QueueAdmissionAppService.AdmitOne` maps `Result.Skipped=True` to `AdmitOneResult.Status='skipped'` (not `'queued'`); the log line reads `status=skipped reason=<message>` and `POST /api/Work/<bucket>/Queue/<id>` returns `Message='Skipped (quality already acceptable)'`. Verifiable: `py -m pytest Tests/Contract/TestAddJobToQueueForceAdd.py` passes; a manual repro that reproduced the bug (ForceAdd against MediaFileId with latest VMAF>=80) now yields a Pending row within one second in `SELECT count(*) FROM transcodequeue WHERE mediafileid=<id>`.

## Concurrency Notes

The TranscodeQueue admission path is race-safe by construction. The invariant is **at most one Pending non-variant TranscodeQueue row per MediaFileId**, enforced atomically by a partial unique index plus `INSERT ... ON CONFLICT DO NOTHING`.

- **Partial unique index** `idx_transcodequeue_pending_per_mediafile` (`Scripts/SQLScripts/AddTranscodeQueuePendingUniqueIndex_2026_06_29.py`): `UNIQUE (MediaFileId) WHERE Status='Pending' AND TestVariantSetId IS NULL`. Multi-variant testing rows (where the same MediaFileId may have multiple Pending entries — one per variant set) are not gated; the partial index scope excludes them.
- **Admission INSERTs** in `TranscodeQueueRepository.SaveTranscodeQueueItem` + `.BulkInsertQueueItems`, `QueueManagementBusinessService.AddSuggestionsToQueue` + `.QueueAllMatching`, and `Features/AudioNormalization/SelfHealing/Remediations/EnqueueRetranscode.py` all carry `ON CONFLICT (MediaFileId) WHERE Status='Pending' AND TestVariantSetId IS NULL DO NOTHING RETURNING Id`. The PostgreSQL engine serializes concurrent INSERTs at the unique-index level; the winner gets the new Id back from `RETURNING`, every loser returns `None`/zero rowcount silently — no exception path involved.
- **Caller signal**: `fetchone()` returns row → inserted; returns `None` → already-queued. Bulk paths read `cursor.rowcount` to count successes vs ON-CONFLICT no-ops.

Stress-tested by 10 concurrent threads admitting the same MediaFileId: 1 winner, 9 silent no-ops, 0 exceptions, exactly 1 final Pending row. The prior "single-operator dev box mitigates this in practice" stance was retired after the race was observed in production (Love Island S01E34 admitted twice on 2026-06-29; both queue rows claimed, both transcoded, both ran VMAF — wasted compute, no data loss).

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
