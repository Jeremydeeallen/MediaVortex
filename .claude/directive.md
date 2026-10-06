# Current Directive

**Set:** 2026-10-06
**Status:** Active -- phase: IMPLEMENTING
**Slug:** auto-handoff
**Replaces:** `directives/closed/2026-10-06-label-decides-command.md` (closed Success)

## Outcome

When a stage's output is placed, the next stage the file's bucket names is queued without an operator click. A file never loses its library row because a scan overlapped its replacement. Backlog rows 13 + 18 of `.claude/directives/backlog/_bucket-rules-phase-2.md`; approved plan `~/.claude/plans/we-have-to-simplify-refactored-hearth.md`.

## Acceptance Criteria

1. A library scan that overlaps a replacement leaves the replaced file's row intact: same row id, new path, transcoded flag kept, attempt still linked. Verify: contract test replays the overlap (disk listing taken before the replacement, library read after); live: `SELECT COUNT(*) FROM TranscodeAttempts WHERE FileReplaced IS TRUE AND MediaFileId IS NULL AND AttemptDate > <ship>` = 0.
2. After a stage's output is placed, if the file's bucket names more work, exactly one pending job with that bucket's label exists for the file. Verify: live TV file with no prior failures runs Transcode, then AudioFix is queued and runs with no operator action, ending Compliant.
3. A stage never queues its own label again. Verify: contract test -- placement by label X with bucket still X queues nothing and logs an error.
4. Queueing a file whose bucket names no work, with no label given, is refused with a message; it is never labelled Transcode. Verify: contract test on a Compliant file.
5. A job claimed less than the setup timeout ago with no active-job record yet is not declared stuck; past the timeout it is. Verify: contract test both sides of the threshold.
6. A failed read of active jobs raises to the caller instead of reading as "no active jobs". Verify: contract test.

## Call-Graph Audit

- **Flow docs:** `transcode.flow.md` (ST2 admission, ST9 placement), `ingest.flow.md` (ST1-ST3 scan), `Features/ServiceControl/stuck-job-detection.flow.md`. Three distinct pipelines; no pair describes one operation.
- **Orchestration mode branches:** none added. Hand-off reads the bucket (data) and passes it as the label; same call for every label. `AddJobToQueue` `IsTranscodeMode` gate branch is preexisting, driven by `ProcessingModeMetadata.RequiresProfileGates` (data).
- **Signal 5:** no flag added. Hand-off always runs; bucket value decides whether a row is inserted.
- **Shared output columns sparse by mode:** `TranscodeAttempts.MediaFileId` NULL on replaced attempts (the row-18 symptom) -- fixed by criterion 1. No new columns.
- **OOS categories:** below.

## Out of Scope

- (b) Repair of rows already lost (attempts with `MediaFileId` NULL, unflagged `-mv` files) -> backlog row 15.
- (b) `fk_transcodeattempts_mediafileid ON DELETE SET NULL` and scan hard-delete semantics (BUG-0096) -- untouched; this directive stops the wrong delete, not the delete mechanism.
- (b) Other silent label defaults (backlog row 19) except the one inside `AddJobToQueue` this directive edits.
- (b) Bulk-queue profile rewrite (row 2), stale tests (row 7), 6 `_test-*` Running queue rows (row 15).

## Constraints

- Workers drained before deploy (fleet script). No schema change.
- Live verification on one TV file with zero prior attempts.

## Escalation Defaults

- Hand-off insert refused by an admission gate -> log and leave the file in its bucket; the placement still succeeds.
- Risk tolerance: medium.

## Engineering Calls Already Made

- Operator 2026-10-06: hand-off automatic; never queue the label that just ran; grace uses `SetupPhaseTimeoutMin`; fail loud; do not overengineer.
- Hand-off lives at the end of `TranscodedOutputPlacement.Execute` after its recompute and calls existing `AddJobToQueue`.

## Status

### Root cause (row 18, confirmed)

`PerformScan` lists the disk, stats every file (~2 min for 47,540 TV files), then reads the library, then diffs. Logs 2026-10-06: walk done 20:27:50.966, replacement of 750868 at 20:29:42, `Scan complete for T:\: new=1 ... deleted=1` at 20:29:45. The stale listing still held the `.mkv`; the fresh library read held the `-mv.mp4`. The diff inserted the `.mkv` as new and deleted the live row; the FK then nulled the attempt's `MediaFileId`. Rename pairing did not catch it (size and name both differ). Fix: a path is inserted only if it exists on disk at write time, and a row is deleted only if its file is absent at write time.

### Files

```
Features/FileScanning/FileScanningBusinessService.py        -- EDIT: PerformScan confirms new / deleted keys against disk before writing
Features/FileReplacement/TranscodedOutputPlacement.py       -- EDIT: Execute queues the next stage after recompute
Features/TranscodeQueue/QueueManagementBusinessService.py   -- EDIT: AddJobToQueue refuses when bucket names no work; strict label lookup
Features/ServiceControl/StuckJobDetectionService.py         -- EDIT: IsJobStuck grace between claim and active-job row
Features/ServiceControl/ActiveJobRepository.py              -- EDIT: GetActiveJobsByService raises on query failure
Tests/Contract/TestScanReplacementRace.py                   -- CREATE
Tests/Contract/TestAutoHandoff.py                           -- CREATE
Tests/Contract/TestStuckJobDetectionPhaseAware.py           -- EDIT: missing-active-job case sits past the grace
Tests/Contract/TestAddJobToQueueForceAddAutoReset.py, TestFailureClassTerminal.py, TestNonVideoContainersExcluded.py -- EDIT: unprobed fixtures name their label
transcode.flow.md, ingest.flow.md, stuck-job-detection.flow.md -- EDIT at DELIVERING
```

### Plan

Commit units (code + tests together):

1. **Scan confirms against disk.** In `PerformScan`, before rename pairing: drop new keys whose file no longer exists; drop deleted keys whose file exists. Test replays the overlap.
2. **Hand-off.** `AddJobToQueue`: no label + bucket outside the label set -> refuse; label looked up strictly. `Execute`: after recompute read `WorkBucket`; work label != label that ran -> `AddJobToQueue(MediaFileId, ProcessingMode=<bucket>)`; equal -> log error, queue nothing.
3. **Stuck grace.** `IsJobStuck`: no active-job row and claim age < `SetupPhaseTimeoutMin` -> not stuck. `GetActiveJobsByService` re-raises.

Seams added or changed:

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| Scan diff -> library write | `PerformScan` | sets of lowercased relative paths | every inserted path exists on disk now; every deleted row's file is absent now | `TestScanReplacementRace` |
| Placement -> queue | `TranscodedOutputPlacement.Execute` | `MediaFiles.WorkBucket TEXT` after recompute | `AddJobToQueue(ProcessingMode=<bucket>)` inserts one Pending row; label != label that ran | `TestAutoHandoff`, live |
| Queue claim -> stuck detect | claim `UPDATE TranscodeQueue SET DateStarted = NOW()` | `DateStarted TIMESTAMP` | `IsJobStuck` tolerates a missing active-job row until `SetupPhaseTimeoutMin` | `TestAutoHandoff` |

### Promotions

### Verification

### Decisions Made

- Scan fix confirms each insert / delete against the disk at write time rather than reordering the walk and the library read: either order leaves a window, and reading the library first would delete the live row by id.
- Hand-off runs after the original is deleted, as the last step of placement. A hand-off error is logged and does not fail a placement that is already on disk.
- Hand-off calls `AddJobToQueue` without force: the audio admission gate may still defer the file; that is logged and the file stays in its bucket.
- The next job can be claimed before the placing attempt is marked finished. The one-in-flight-attempt index refuses it, the claim releases the row, and a later claim takes it (existing behaviour, `TranscodeJobRepository` UniqueViolation path).
- `AddJobToQueue` with no label on a file whose bucket names no work now returns a refusal. Four existing tests queued unprobed fixture files and relied on the old `Transcode` default; they now pass the label.
- Missing claim time on a Running row, or a missing `SetupPhaseTimeoutMin` setting, raises inside `IsJobStuck`; its existing handler logs the exception and reports not-stuck.
