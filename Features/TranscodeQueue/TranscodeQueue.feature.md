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
9. The /TranscodeQueue page displays all pending queue items with file details.
10. **[BUG-0061]** Encode-failure retry has a configurable cap (sibling to `PostTranscodeGateConfig.MaxRequeueAttempts`, default 3) counting consecutive `TranscodeAttempts.Success=FALSE` rows since the last `Success=TRUE` (or since file creation if no prior success). The cap is consulted in BOTH `ClaimNextPendingTranscodeJob` (skip Pending rows whose MediaFile has exceeded cap) AND `QueueManagementBusinessService.RecomputeForFiles` (do not INSERT a new queue row for a MediaFile that has exceeded cap). Capped MediaFiles surface in an operator-visible "Failed Jobs" panel with filename, failure count, last ErrorMessage, last AttemptDate, AssignedProfile, last WorkerName; operator can reset (re-allow next claim) or view full attempt log. Verifiable: live DB query `SELECT MediaFileId, COUNT(*) FROM TranscodeAttempts WHERE Success=FALSE GROUP BY MediaFileId HAVING COUNT(*) > <cap>` returns zero rows that also appear in `TranscodeQueue` with `Status='Pending'`.

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
| POST /api/ShowSettings/NextTranscodeBatch | Smart batch admission |

### What is EXPLICITLY NOT a contract

- The internal SQL of PopulateQueue / NextTranscodeBatch -- changes freely
- _GetEffectiveProfileFromCache cache invalidation -- internal
- Priority-score formula coefficients -- tunable; defined in queue-priority.feature.md
- The exact set of admission predicates -- documented in companion feature docs
