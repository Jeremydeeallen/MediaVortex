# Current Directive

**Set:** 2026-10-11
**Status:** Active -- phase: VERIFYING
**Slug:** crash-recovery-audiofix-type
**Replaces:** `directives/closed/2026-10-11-demucs-liveness.md` (closed Success)

## Outcome

When a worker starts, it releases every job it was running when it died, whatever kind of job it was: the attempt is marked failed with `worker crashed/restarted` and the queue row returns to `Pending` before the worker begins claiming. Today boot recovery walks leftover active-job records and only recognises the job type `Transcode`; an `AudioFix` or `Remux` job logs `Unknown job type` and sits `Running` with no owner for 30 minutes (backlog row 28; wakko 2026-10-11, queue row 225415, attempt 99831). Recovery now goes by what the database says the worker owns, the code that could never run is deleted, and crash recovery is described in one document.

## Acceptance Criteria

1. A worker killed mid-Audio job and restarted leaves, by the time it logs that crash recovery completed: the job's queue row `Pending` with no claimant, and the job's attempt `Success = FALSE` with `ErrorMessage = 'worker crashed/restarted'`. Verify: live kill of the I9 worker during an Audio job, then SQL on the queue row and attempt.
2. The same end state holds for every processing mode and for a job that died before its active-job record was written. Verify: contract test, one case per `ProcessingModes` row plus a case with no active-job record.
3. That boot's log has no `Unknown job type` and no `Failed to reset job` line. Verify: log of the boot in criterion 1.
4. The released job is claimed again without waiting for stuck-job detection's grace (`SystemSettings.SetupPhaseTimeoutMin`). Verify: restart-to-reclaim time in criterion 1's run.
5. A booting worker changes no attempt, queue row or progress row owned by another worker. Verify: contract test with a second worker's in-flight job present before recovery and identical after.
6. An attempt that finished encoding and is waiting for its quality test is not failed by its worker's boot, and its queue row is not released. Verify: contract test.
7. If boot recovery cannot complete, the worker process exits non-zero before claiming anything. Verify: contract test with the database write failing.

## Call-Graph Audit

- **Flow docs:** `WorkerService/WorkerService.flow.md` (ST5), `transcode.flow.md` (Crash Recovery section, stage 1.5 row), `Features/ServiceControl/stuck-job-detection.flow.md`. The first two describe the same operation; this directive makes `WorkerService.flow.md` ST5 the one description and the other a pointer. Stuck-job detection is a different trigger (periodic tick, live owner) and stays its own doc.
- **Orchestration mode branches:** `CrashRecoveryService.ResetJobInQueue` and `.CleanupProgressRecords` branch on the job-type name. Removed: recovery no longer reads a job type.
- **Shared output columns:** `TranscodeAttempts.ErrorMessage` / `FailureClass` on crashed attempts: Transcode gets `worker crashed/restarted`, Audio and Remux get the stuck-detect text 30 minutes later. Closed by criteria 1-2.
- **Signal 5:** no flag involved.
- **OOS categories:** below.

## Out of Scope

- (b) `_RecoverInProgressArtifacts` and `_SweepLocalStagingOrphans` (disk cleanup at boot) keep catching and logging their own errors. Backlog row 35.
- (b) Boot recovery kills the process whose id is recorded on a leftover active-job record without checking what that process is. Unchanged. Backlog row 36.
- (b) The claim contract tests leave the rows they claim `Running` (source of the six stale rows). The rows are released in this directive; fixing the tests is backlog row 37.
- (b) A worker that dies and never boots again: its attempts are released by the abandonment sweeper, its queue rows stay `Running` (owner-only cleanup). Unchanged. Backlog row 38.

## Constraints

- `claim-authority.md`: every recovery write is scoped to the booting worker.
- `worker-lifecycle-invariants.md` I1, I4.
- No production config changed for testing. Pausing `dot-worker-1` / `wakko-worker-1` to steer one job to I9 is restored in the same step (operator approved 2026-10-12).

## Escalation Defaults

- Risk tolerance: medium.

## Engineering Calls Already Made

- Operator 2026-10-12: release by ownership, not by job type.
- Operator 2026-10-12: delete all dead crash-recovery code (never-run QualityTest branch, unused methods, `DatabaseCleanupService`, the two `Scripts/TestCrashRecovery*.py`).
- Operator 2026-10-12: a failed boot recovery stops the worker from starting.
- Operator 2026-10-12: live proof = release the six stale test-claimed queue rows, steer one to I9, kill I9 mid-job.
- The job type written on an active-job record stays the processing mode (Activity page and SQL queries read it).

## Status

### Files

```
Features/ServiceControl/CrashRecoveryService.py        -- EDIT: release by ownership; delete type dispatch, QualityTest branch, unused methods; no swallowed errors on the release path
Features/TranscodeJob/TranscodeJobRepository.py        -- EDIT: one owner-scoped "mark crashed" method replaces the per-queue and the all-workers ones
WorkerService/Main.py                                  -- EDIT: _RecoverFromCrash lets a recovery failure stop the boot; imports the service from its real module
Services/CrashRecoveryService.py                       -- DELETE: re-export shim, no remaining importer
Services/DatabaseCleanupService.py                     -- DELETE: no production caller
Scripts/TestCrashRecovery.py                           -- DELETE: calls a service name that does not exist
Scripts/TestCrashRecoveryFix.py                        -- DELETE: same
Docs/SystemWide/AutomatedCrashRecovery.md              -- DELETE: describes a three-process layout that no longer exists
Tests/Contract/TestCrashRecoveryOwnership.py           -- CREATE: criteria 2, 5, 6, 7
WorkerService/WorkerService.flow.md                    -- EDIT: ST5 becomes the single description of boot recovery
transcode.flow.md                                      -- EDIT: Crash Recovery section + stage 1.5 row become a pointer
WorkerService/worker-lifecycle.feature.md              -- EDIT: C13 wording to ownership; pointer
Features/ServiceControl/ServiceControl.feature.md      -- EDIT: criterion 4 pointer
.claude/rules/worker-lifecycle-invariants.md           -- EDIT: I2 names boot recovery (not stuck-job detection) as the writer
Features/TranscodeJob/local-staging.feature.md         -- EDIT: C12 names the renamed entry method
Tests/Contract/failloud_baseline.json                  -- EDIT: ratchet the three touched files (deleted file removed, two counts lowered)
.claude/directives/backlog/_bucket-rules-phase-2.md    -- EDIT: close row 28, add rows 35-38
```

### Plan

Boot recovery (`CrashRecoveryService`), every statement scoped to the booting worker's name, in this order:

1. Kill a still-running process recorded on this worker's leftover active-job records (existing behaviour, self-kill guard kept).
2. Fail this worker's in-flight attempts (`Success IS NULL AND WorkerName = self`), except those with an unfinished `QualityTestingQueue` row. Message `worker crashed/restarted`, failure class filled as today.
3. Delete progress rows of this worker's failed attempts.
4. Release this worker's queue rows (`ClaimedBy = self AND Status = 'Running'`) whose media file has no in-flight attempt left.
5. Existing disk cleanup (`.ip` artifacts, local scratch), unchanged.
6. `WorkerService.Main` deletes this worker's active-job records (existing).

Steps 2-4 raise on failure; `_RecoverFromCrash` does not catch.

Commits: (1) code + test + deletions; (2) docs. Then restart I9, release the six rows, live kill.

Seams changed:

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| Claim -> boot recovery | `TranscodeQueueRepository.ClaimNextPendingJob` | `TranscodeQueue.(Status='Running', ClaimedBy=WorkerName TEXT)` | recovery matches `ClaimedBy = self` | contract test, live kill |
| Attempt create -> boot recovery | `CreateTranscodeAttempt` | `TranscodeAttempts.(Success NULL, WorkerName TEXT)` | recovery matches `WorkerName = self` | contract test, live kill |
| Encode -> quality test (`transcode.S2`) | encode success | attempt `Success NULL` + `QualityTestingQueue` row `DateCompleted NULL` | recovery skips it | contract test (criterion 6) |
| Recovery -> boot | `CrashRecoveryService` | exception on failure | `WorkerService.Main.Run` exits non-zero | contract test (criterion 7) |

### Promotions

### Verification

- **Commit:** `104ee697`, pushed. I9-2024 restarted onto it 2026-10-12 15:34 UTC (`Workers.Version` = `104ee697...`, heartbeat fresh, 2 worker processes).
- **Criteria 2, 5, 6, 7:** `py -m pytest Tests/Contract/TestCrashRecoveryOwnership.py` -> 7 passed, 3 subtests (Transcode, Remux, AudioFix). Rows live in an uncommitted transaction; `MediaFiles` leftovers = 0 after the run.
- **Boot on new code (I9-2024, ST5):** Logs 64274879-64274898: `Crash recovery completed for I9-2024: {'JobsReleased': 0, 'AttemptsFailed': 0, ... 'LocalStagingOrphansCleaned': 1}`, then `ActiveJobs sweep: deleted 0 row(s)`. No `Unknown job type` line.
- **Fleet:** `py deploy/deploy-fleet.py` 2026-10-12 16:17 UTC, 9 workers OK on `71035fe9`.
- **Criteria 1, 3, 4 -- real kill, I9-2024, AudioFix (2026-10-13 UTC):** `RemuxEnabled` set TRUE on I9 for the test, queue row 221750 released, I9 claimed it 02:09:55. At 02:10:34 the job was mid-flight (ActiveJobs 1534432 `JobType=AudioFix`, phase PreEncode, Demucs 20%, attempt 99885). Worker processes hard-killed 02:10:41; before restart the row was `Running`/`I9-2024`, attempt in flight, 1 active-job record. Worker started 02:10:58. Logs 64300983-64300988: `Crash recovery completed for I9-2024: {'JobsReleased': 1, 'AttemptsFailed': 1, 'ProgressDeleted': 1, ...}`, `ActiveJobs sweep: deleted 1 row(s)`; no `Unknown job type`, no `Failed to reset job`. Attempt 99885: `Success=FALSE`, `ErrorMessage='worker crashed/restarted'`, `FailureClass='worker_crashed_restarted'`. Queue row re-claimed by dot-worker-1 at 02:11:01 (3 s after boot, 20 s after the kill; grace is 30 min), new attempt 99886. `RemuxEnabled` restored to FALSE while the worker was down.
- **Staged leftover, I9-2024:** row 221752 + in-flight attempt 99883 + AudioFix active-job record staged under I9's name with the worker stopped. Boot 02:08:53: `JobsReleased: 1`, active-job record deleted, row re-claimed by wakko-worker-1 at 02:08:55. The attempt had already been failed `owner_abandoned` by the abandonment sweeper (I9 was Paused and down for hours), so `AttemptsFailed: 0` there.
- **Real kill on a Linux worker:** NOT RUN. The session's permission classifier refuses the remote kill over ssh; needs the operator to run it on the host.
- **Test side effects:** scan jobs orphaned by the two hard kills on I9 were marked `Failed` by hand (97633 and the one running at 02:10:41). The four other stale test-claimed rows (214664, 214784, 221749, 221751) released to `Pending` 02:12 UTC. dot-worker-1 paused 02:09-02:10 to steer the claim, restored.
- **Regression:** `TestAbandonmentSweeper`, `TestClaimAuthority` pass. `TestFailLoud` 2 failures are the stale-baseline pair already in backlog row 30; none of this directive's files appear in them.

### Decisions Made

- Disk cleanup at boot (`.ip` files, partial replacements, local scratch) now runs on every boot. Before, it ran only when leftover active-job records existed. First boot removed `C:\MediaVortex\699524`, a staged copy left by failed attempt 90385 (2026-09-09).
- `CrashRecoveryService` requires a worker name; the "all workers" mode had only the deleted scripts as callers.
- The contract test uses one uncommitted transaction instead of committed sentinel rows: a released test row would be `Pending` and claimable by a live worker.
- Fail-loud baseline lowered only for the three files this directive touched.
