# Flow: Stuck Job Detection

**Slug:** stuck-job-detection

## Entry Point

`WorkerService/Main.py` -- a daemon thread (`_StuckJobDetectionLoop`) on
each worker invokes `StuckJobDetectionService.DetectAndCleanStuckTranscodeJobs`
every `SystemSettings.StuckJobDetectionIntervalSec` seconds (default 120).
Plus the existing one-shot call at worker startup that catches jobs left
over from a prior crash.

The detector has one job: when a worker has claimed a transcode and either
the FFmpeg child has died or the encoder has frozen, reset the queue item
to Pending so another worker (or the same one, on its next cycle) can
retry. Killing the wrong PID -- the worker itself, an unrelated FFmpeg on
another job, or anything on a different host -- is the failure shape this
flow is built to prevent.

## Per-Cycle Decision Tree

| ID | Step | What happens | Failure mode |
|---|------|--------------|--------------|
| ST1 | List candidates | `GetRunningTranscodeJobs()` filtered to `ClaimedBy = self.WorkerName`. Each worker only inspects its own jobs. | Cross-host kills are categorically prevented at this filter. |
| ST2 | Per-job: load ActiveJob | `GetActiveJobsByService('TranscodeService')`, find row where `QueueId == job.Id`. | If no ActiveJob row exists for a Running queue item, the job is stuck (orphaned) and proceeds to cleanup. |
| ST3 | Tier 1: worker heartbeat | If the owning worker's `Workers.LastHeartbeat` is older than 5 min OR `Status='Offline'`, the job is stuck. | Catches dead-worker crashes where the worker can't clean up its own jobs. |
| ST4 | Tier 2: frame stagnation | Read latest `TranscodeProgress.LastUpdate` for the attempt. If older than `FrozenProgressThresholdMin` minutes (default 5), the job is stuck. | Catches SVT-AV1 tail stalls where FFmpeg is still alive but no longer advancing frames. |
| ST5 | Tier 3: FFmpeg-PID liveness | Read `ActiveJobs.FFmpegPid`. **If NULL, return `not stuck`** -- FFmpeg may not have spawned yet, defer to Tier 2 once it does. If non-NULL: check that PID is alive AND its process name is `ffmpeg`/`ffmpeg.exe`. Mismatch on either condition = stuck. | Catches the case where FFmpeg crashed silently (parent doesn't notice promptly). The "no FFmpeg processes on system" heuristic was retired -- false-positived during the pre-spawn window and self-killed I9 on 2026-05-09. |
| ST6 | Cleanup -- host-locality guard | Before any `KillProcess` call, verify `ActiveJob.WorkerName == socket.gethostname()`. If not, log skip and proceed to DB-only cleanup. | Cross-host kills are still impossible even if ST1's filter were bypassed in some future code path. |
| ST7 | Cleanup -- kill target | Kill `FFmpegPid` (not `ProcessId`). If `FFmpegPid` is NULL, find FFmpeg child processes of the worker PID and kill those. **Never** kill the worker PID. | The pid-reuse / wrong-target class of bugs (Incidents 1 and 2 from the feature doc) is closed by always targeting an FFmpeg-by-name process. |
| ST8 | Cleanup -- DB state | Reset `TranscodeQueue.Status='Pending'`, clear `ClaimedBy`/`ClaimedAt`/`DateStarted`. Mark in-flight `TranscodeAttempts` as Success=FALSE with reason. Set `ActiveJobs.Status='Failed'`. Delete `TranscodeProgress` rows for the failed attempt. | DB-only cleanup is safe across hosts, runs even when ST6 skipped the kill. |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | Entry: `_StuckJobDetectionLoop` -> ST1 | `WorkerService/Main.py` daemon thread | Per-cycle invocation with `SystemSettings.StuckJobDetectionIntervalSec` cadence (default 120s) | `DetectAndCleanStuckTranscodeJobs` runs per worker | `SELECT COUNT(*) FROM Logs WHERE FunctionName='DetectAndCleanStuckTranscodeJobs' AND TimeStamp > NOW() - INTERVAL '5 minutes'` >= 1 on any idle worker |
| S2 | `ST2 -> ST5` (ActiveJob load -> Tier 3) | `ProcessTranscodeQueueService` writes `ActiveJobs.FFmpegPid` immediately after `Popen.pid` returns | `ActiveJobs.(FFmpegPid BIGINT NULL, ProcessId BIGINT, ServiceName='TranscodeService', WorkerName TEXT, Status='Running')` | `IsJobStuck` reads FFmpegPid + ProcessId; FFmpegPid NULL defers to Tier 2 | `SELECT FFmpegPid FROM ActiveJobs WHERE Status='Running' AND ServiceName='TranscodeService'` -- non-NULL for live encodes (post-spawn) |
| S3 | `ST4` consumes `TranscodeProgress.LastUpdate` | `ProcessTranscodeQueueService` writes per-frame progress | `TranscodeProgress.(TranscodeAttemptId BIGINT UNIQUE, LastUpdate TIMESTAMP NOT NULL, AverageFPS, CurrentFrame)` | Tier 2 compares `LastUpdate` to NOW() against `FrozenProgressThresholdMin` | `SELECT NOW() - LastUpdate FROM TranscodeProgress WHERE TranscodeAttemptId=<id>` -- < threshold for healthy encodes |
| S4 | `ST8 -> requeue` (DB state reset) | `CleanupStuckJob` writes `TranscodeQueue.Status='Pending', ClaimedBy=NULL` + `TranscodeAttempts.Success=FALSE` | Queue row returns to claim eligibility; attempt is closed | `DatabaseManager.ClaimNextPendingTranscodeJob` (`transcode.flow.md::S1`) claims it on next worker tick | After a forced stuck-job cleanup, `SELECT Status FROM TranscodeQueue WHERE Id=<id>` -> `'Pending'`, claimable again |
| S5 | host-locality invariant | `_StuckJobDetectionLoop` per-worker invocation | `ActiveJob.WorkerName == socket.gethostname()` precondition before any kill | Guard refuses cross-host kills; logs and falls back to DB-only cleanup | `Logs` for cross-host candidates show "skipped kill: not local" markers; no `Get-Process` invocations log for unrelated workers |

## State Tables

```
ActiveJobs
  Id              BIGINT       -- row id
  ServiceName     TEXT         -- 'TranscodeService' for transcode jobs
  QueueId         BIGINT       -- TranscodeQueue.Id
  ProcessId       BIGINT       -- worker's Python PID (os.getpid()) -- DOCUMENTED, do not kill
  FFmpegPid       BIGINT       -- (NEW) the FFmpeg subprocess PID, written when Popen returns
  WorkerName      TEXT         -- the worker that owns the job
  Status          TEXT         -- 'Running' / 'Failed' / etc.
  StartedAt       TIMESTAMP

SystemSettings (relevant rows)
  StuckJobDetectionIntervalSec   -- recurring loop cadence, default 120
  FrozenProgressThresholdMin     -- Tier 2 threshold, default 5
```

## Failure Modes

- **Worker process died abruptly** (Incident 2 root cause was here): Tier 1's heartbeat check on subsequent cycles will mark the worker offline; jobs will be reset by surviving workers. Local detection on the dead worker doesn't run anymore by definition.
- **FFmpeg crashed but `FFmpegPid` is NULL** (legacy ActiveJobs row from before this feature): step 7's fallback finds FFmpeg children of the worker and kills them. Logged so the operator can see the legacy-row path was taken.
- **A second worker tries to claim the same job after cleanup**: dedupe in queue-population paths, plus the queue claim is `SELECT FOR UPDATE SKIP LOCKED`, so this is already handled by the queue layer.
- **Detection cycle errors** (DB unreachable, etc.): the cycle catches and logs, then sleeps for the next interval. One bad cycle does not crash the worker.

## Out of Scope

- Cross-host PID killing. The host-locality guard categorically forbids it; this flow is local-cleanup-only for the kill side. DB cleanup is the only cross-host action.
- Rich scheduling (priority queues, work-stealing, etc.) -- this flow is a janitor, not a scheduler.
- UI for the operator to manually trigger cleanup. The existing `/api/Service/StuckJobs/Cleanup` admin endpoint covers manual invocation; this flow is about the automatic recurring path.
