# Stuck Job Detection -- recurring scheduler, correct kill target, host-locality guard

**Slug:** stuck-job-detection

## What It Does

Closes four gaps in `StuckJobDetectionService` that made today's hung-FFmpeg incident (Bizarre Foods S13E05 stalled at 95% for 13 minutes on I9-2024, 2026-05-09) require manual intervention via `taskkill`. The detection logic itself is sound -- `LastFrameAdvance` is the right signal -- but it (a) only runs once at worker startup so it never re-checked the hang, (b) waits 15 minutes which is too long for SVT-AV1 tail stalls, (c) would have killed the entire Python worker process instead of the FFmpeg child if it had fired, and (d) would have killed a local PID for a job claimed by a different host.

After this feature, every worker self-monitors its own jobs every ~2 minutes, kills only the FFmpeg child of the stuck job (worker stays alive), and never touches PIDs that don't belong to this host.

## Concern

Two operator incidents on 2026-05-09:

**Incident 1 (Bizarre Foods stall):** SVT-AV1 + Bizarre Foods S13E05, frame counter stopped advancing at 95% on I9-2024. ETA stayed at "00:00:02" indefinitely. Operator killed FFmpeg PID 25676 manually via PowerShell to unblock a worker deploy. Diagnostic queries confirmed `frame_advance_age_sec=796` (13.3 min) while `progress_age_sec=0` -- exactly the hang shape `_IsJobFrozen` is designed to catch. Investigation revealed the four gaps above. Recurring tail-stalls are a known SVT-AV1 behavior; manual intervention shouldn't be required every time.

**Incident 2 (I9 self-kill):** I9-2024 worker crashed immediately after claiming Job 76776 (Sister Wives S04E03). DateStarted 17:34:45, last heartbeat 17:34:20, "Stuck job detected" warning at 17:34:47 -- two seconds after claim. No ERROR log, no traceback; process exited cleanly. Root cause: `ActiveJobs.ProcessId` is the Python worker PID (documented at `IsProcessAlive` line 261-263), and `CleanupStuckJob` calls `KillProcess(processId)` against that PID -- killing the worker itself. The detector mis-flagged the job as stuck because Tier 3's "no FFmpeg processes on system" check fires during the gap between job claim and FFmpeg spawn. I9 is the only worker hit because Tier 3 only runs for `IsLocalJob` (worker hostname == `socket.gethostname()` of the WebService host), and only I9 is co-located with WebService; larry-worker-1..4 escape Tier 3 entirely.

Both incidents reinforce the same fix: kill the FFmpeg child PID, never the worker PID; gate kill calls behind a host-locality guard; add a recurring scheduler so detection runs more than once per worker lifetime.

## Success Criteria

### A. Recurring detection on each worker

1. `WorkerService.Run()` starts a background thread that calls `StuckJobDetectionService.DetectAndCleanStuckTranscodeJobs` (and `DetectAndCleanStuckQualityTestJobs`) every `StuckJobDetectionIntervalSec` seconds. The interval is read from `SystemSettings` with default `120`. Thread is daemon, joins on `ShutdownEvent`. Verifiable: with the worker idle for 5 minutes, `SELECT COUNT(*) FROM Logs WHERE FunctionName='DetectAndCleanStuckTranscodeJobs' AND TimeStamp > NOW() - INTERVAL '5 minutes'` returns >= 2.

2. The today's startup-only call at `WorkerService/Main.py:312` remains -- the recurring thread is *additional*, not a replacement. Startup detection picks up jobs left over from the prior run; the recurring thread catches new hangs while the worker is alive. Verifiable: code inspection.

### B. Threshold tuning

3. `FROZEN_PROGRESS_THRESHOLD_MINUTES` lowered from 15 to 5. SVT-AV1 at the FPS rates we observe (54-103 fps) never goes >30s without a frame advance during normal encode; 5 min is well clear of any legitimate transient pause. Verifiable: code constant changed; the prior incident (13.3 min stall) would have been killed at the 5-min mark.

4. Threshold is configurable via `SystemSettings.FrozenProgressThresholdMin` (integer, default 5). Reading the setting is per-detection-cycle so the operator can tune without restarting any worker. Verifiable: `UPDATE SystemSettings SET Value='3' WHERE Key='FrozenProgressThresholdMin'`; next detection cycle uses 3.

### C. FFmpeg child PID tracking and correct kill target

5. `ActiveJobs` schema gains a nullable `FFmpegPid BIGINT` column. Migration script `Scripts/SQLScripts/AddFFmpegPidColumn.py` runs idempotently (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`). Verifiable: `\d ActiveJobs` shows the column.

6. `ProcessTranscodeQueueService` (or whichever method invokes FFmpeg via `subprocess.Popen`) captures `Popen.pid` and writes it to the row's `FFmpegPid` column **before** waiting on the process. The write happens within the same transaction as the FFmpeg start, or within 1 second after. Verifiable: during a normal transcode, `SELECT FFmpegPid FROM ActiveJobs WHERE QueueId=<live job>` returns a non-null PID that matches `Get-Process ffmpeg`.

7. `CleanupStuckJob` reads `FFmpegPid` (not `ProcessId`) and calls `KillProcess` against that. The `ProcessId` (Python worker PID) is no longer touched. Verifiable: induce a stuck job, observe via logs that the kill target matches the FFmpeg PID and that the worker process keeps running and emits its next heartbeat on schedule.

8. If `FFmpegPid` is NULL (legacy ActiveJobs row from before this feature, or FFmpeg not yet started), cleanup falls back to `ProcessManagementService.FindFFmpegProcesses()` filtered to children of the worker PID, kills any matches. Logs the fallback so the operator can see the legacy-row path was hit. Verifiable: a hand-crafted ActiveJobs row with `FFmpegPid=NULL` for a real running FFmpeg gets cleaned correctly.

### D'. Pre-spawn window protection (Incident 2)

D1. The `IsJobStuck` Tier 3 check no longer treats "no FFmpeg processes on system" as a stuck signal on its own. If `ActiveJobs.FFmpegPid` is NULL (FFmpeg hasn't started yet, or row predates this feature), Tier 3 returns `not stuck` and detection relies on Tier 2 (frame stagnation) for hang detection. If `FFmpegPid` is set and that PID is no longer running OR is no longer an `ffmpeg`/`ffmpeg.exe` process by name, Tier 3 reports stuck. Verifiable: claim a queue job, do not let FFmpeg start (e.g. simulate a long file-prep delay), wait one detection cycle, observe that the job is NOT flagged stuck and NOT cleaned up. Verifiable counterpart: kill an FFmpeg child of a running job manually, observe that the job IS flagged within one cycle.

D2. The "PID may have been reused" log message in `IsJobStuck` is removed -- it was misleading because the PID was the worker's, not FFmpeg's. Replacement message when D1 fires: `"FFmpeg PID <n> recorded for job <id> is no longer alive (process name was '<actual_name>')"`. Verifiable: code search for the old phrase returns no results; the new message appears in logs when D1 triggers.

### D. Host-locality guard

9. `CleanupStuckJob` checks `ActiveJob.WorkerName == socket.gethostname()` before *any* call to `KillProcess`. If the WorkerName is different (cross-host stuck job), the cleanup logs the skip, leaves the PID alone, and **still** resets the DB state (TranscodeQueue back to Pending, TranscodeAttempts marked failed, ActiveJobs marked Failed). The DB-only cleanup is safe across hosts; the kill is not. Verifiable: an ActiveJobs row with WorkerName='other-host' triggers the skip log but DB-only fields still update.

10. Each worker's recurring detection thread filters running jobs to `ClaimedBy = self.WorkerName` before checking each one. This makes criterion 9 belt-and-suspenders: the thread shouldn't find another host's jobs in the first place, but if it somehow does (race during failover), the host-locality guard still applies. Verifiable: with 5 workers running, only the worker that owns a stuck job logs `Stuck job detected: ...`. The other 4 logs read `No running jobs to check` for that cycle.

### E. Observability

11. Each detection cycle that finds stuck jobs logs at WARNING (existing). Each detection cycle that finds no stuck jobs logs at INFO at most once per hour per worker, suppressed by a per-thread timer -- avoids drowning the Logs table when 5 workers each emit "no stuck jobs" every 2 minutes (1,800 noise rows/hour). Verifiable: `SELECT COUNT(*) FROM Logs WHERE LogLevel='INFO' AND FunctionName='DetectAndCleanStuckTranscodeJobs' AND TimeStamp > NOW() - INTERVAL '1 hour'` returns <= 5 (one per worker per hour, not per cycle).

12. When a kill happens, the WARNING log entry includes: worker name, queue id, file name, frame_advance_age_minutes, FFmpeg PID, kill outcome (Success / Failed). All on one line so a single grep is sufficient. Verifiable: induce a stuck job, observe the log row contains all six fields.

## Status

COMPLETE -- I9 self-kill fix verified 2026-05-09. Two enhancement items (D10 per-worker filter, E11-E12 log throttling) deliberately deferred as non-blocking; they enhance observability and belt-and-suspenders, not the actual I9 fix.

### Progress

- [x] Read prior issues (no related entry in `memory/KNOWN-ISSUES.md`)
- [x] Surveyed existing `StuckJobDetectionService` and called sites
- [x] Feature doc updated with both incidents
- [x] Flow doc created: `Features/ServiceControl/stuck-job-detection.flow.md`
- [x] Schema migration `Scripts/SQLScripts/AddFFmpegPidColumn.py` (run -- column added to ActiveJobs)
- [x] Settings seeds `Scripts/SQLScripts/SeedStuckDetectionSettings.py` (run -- StuckJobDetectionIntervalSec=120, FrozenProgressThresholdMin=5)
- [x] B3-B4: Threshold lowered 15->5; reads `FrozenProgressThresholdMin` per cycle via `_GetFrozenProgressThresholdMin()`
- [x] C5-C7: `ActiveJobs.FFmpegPid` column + `DatabaseManager.SetActiveJobFFmpegPid` helper + `VideoTranscodingService.TranscodeVideo` records `Process.pid` after `Popen`
- [x] C8: legacy fallback in `CleanupStuckJob` walks worker's child processes for FFmpeg when `FFmpegPid` is NULL
- [x] D1-D2 (the I9 fix): `IsJobStuck` Tier 3 no longer fires on "no FFmpeg processes on system"; FFmpegPid-NULL returns not-stuck (defers to Tier 2). New helpers `_GetProcessName` and `_IsFFmpegProcessName` reject `python`/`python.exe` as kill targets.
- [x] D9: `CleanupStuckJob` host-locality guard -- only kills PIDs on `socket.gethostname()`; cross-host runs DB-only cleanup
- [x] A1: `WorkerService._StartStuckJobDetection` + `_StuckJobDetectionLoop` runs every `StuckJobDetectionIntervalSec` (default 120) via daemon thread, gated by `ShutdownEvent`
- [x] A2: startup-time `_DetectAndCleanStuckJobs` call retained (additional, not replacement)
- [x] `GetActiveJobsByService` SELECT extended to include `FFmpegPid` so cleanup sees it
- [x] `transcode.flow.md` Stage 4 safety guards updated with new cadence + FFmpegPid kill-target note
- [ ] D10: per-worker filter in detection thread (`ClaimedBy = self.WorkerName`) -- recurring loop currently runs the existing `DetectAndCleanStuckTranscodeJobs` which checks all running jobs; belt-and-suspenders filter is deferred (host-locality guard at the kill site already prevents cross-host kills)
- [ ] E11-E12: log throttling + structured kill log line -- deferred (current behavior logs WARNING per detection on stuck-found and INFO per cycle; throttling not blocking the I9 fix)
- [x] Smoke test 1 (2026-05-09): kill FFmpeg manually mid-job; worker survived; queue item reset to Pending within one detection cycle.
- [x] Smoke test 2 / I9 regression (2026-05-09): I9 (co-located WebService+Worker) claimed jobs without false-positive self-kill; recurring loop running cleanly.

NEXT: D10 per-worker filter and E11-E12 log throttling are open as enhancement work; pick up only if log noise from the recurring loop becomes a problem.

## Scope

```
Features/ServiceControl/StuckJobDetectionService.py      -- threshold constant, host-locality guard, FFmpegPid use, log-noise suppression
WorkerService/Main.py                                    -- new background detection thread (Run() spawns, _MainLoop joins on ShutdownEvent)
Features/TranscodeJob/ProcessTranscodeQueueService.py    -- capture Popen.pid into ActiveJobs.FFmpegPid at FFmpeg start
Repositories/DatabaseManager.py                          -- helper(s) to UPDATE ActiveJobs.FFmpegPid by row id
Scripts/SQLScripts/AddFFmpegPidColumn.py                 -- NEW. ALTER TABLE ActiveJobs ADD COLUMN IF NOT EXISTS FFmpegPid BIGINT NULL
Scripts/SQLScripts/SeedStuckDetectionSettings.py         -- NEW. INSERT SystemSettings rows StuckJobDetectionIntervalSec=120, FrozenProgressThresholdMin=5 ON CONFLICT DO NOTHING
transcode.flow.md                                        -- note recurring detection cadence in Stage 4
```

## Files

| File | Role |
|------|------|
| `Features/ServiceControl/StuckJobDetectionService.py` | Drop FROZEN_PROGRESS_THRESHOLD_MINUTES from 15 to 5 (or read from SystemSettings per cycle). `CleanupStuckJob` uses `FFmpegPid` instead of `ProcessId`, falls back to FFmpeg-children-of-worker scan if NULL, gates on `WorkerName == socket.gethostname()` before KillProcess. INFO logs throttled to 1/hour per worker. |
| `WorkerService/Main.py` | New `_StartStuckJobDetectionLoop()` similar to `_StartHealthMonitoring()`, runs on `StuckJobDetectionIntervalSec` cadence, daemon thread, joined via ShutdownEvent. |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py` | At FFmpeg `Popen` start, capture `.pid` and call `DatabaseManager.SetActiveJobFFmpegPid(activeJobId, ffmpegPid)` before `process.wait()`. |
| `Repositories/DatabaseManager.py` | New helper `SetActiveJobFFmpegPid(ActiveJobId, FFmpegPid)`. |
| `Scripts/SQLScripts/AddFFmpegPidColumn.py` | NEW. Idempotent `ALTER TABLE ActiveJobs ADD COLUMN IF NOT EXISTS FFmpegPid BIGINT`. |
| `Scripts/SQLScripts/SeedStuckDetectionSettings.py` | NEW. INSERTs `StuckJobDetectionIntervalSec=120` and `FrozenProgressThresholdMin=5` into SystemSettings ON CONFLICT DO NOTHING. |
| `transcode.flow.md` | Stage 4 (stuck-detection mention) updated to note recurring 120s cadence and the FFmpeg-PID kill target. |

## Deviation from conventions

None. Each criterion is observable: DB schema check, log query, induced-hang smoke test. The `FFmpegPid` column is nullable and the cleanup has a legacy fallback, so this is a backwards-compatible addition.
