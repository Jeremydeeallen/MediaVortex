# Flow: Stuck Job Detection

**Slug:** stuck-job-detection

## Entry Point

`WorkerService/Main.py` -- a daemon thread (`_StuckJobDetectionLoop`) on each worker invokes `StuckJobDetectionService.DetectAndCleanStuckTranscodeJobs` every `SystemSettings.StuckJobDetectionIntervalSec` seconds (default 120). Plus the one-shot startup call that catches jobs left over from a prior crash.

Cross-worker abandonment is not this flow -- it runs through `AttemptAbandonmentSweeper` on heartbeat expiry (`.claude/rules/claim-authority.md`).

## Per-Cycle Decision Tree

| ID | Step | What happens | Failure mode |
|---|------|--------------|--------------|
| ST1 | List candidates | `GetRunningTranscodeJobs()` filtered to `ClaimedBy = self.WorkerName`. Owner-scoped. | Cross-host kills are categorically prevented at this filter. |
| ST2 | Load ActiveJob | `GetActiveJobsByService('TranscodeService')`, find row where `QueueId == job.Id`. | No ActiveJob row for a Running queue item = orphaned; proceed to cleanup. |
| ST3 | Read Phase | `GetJobPhase(ActiveJobId)` returns `(JobPhase, PhaseTransitionedAt)`. If NULL: not stuck (pre-Setup transition). | Phase-writer race guaranteed short-lived. |
| ST4 | Dispatch | `PhaseDetectorRegistry.GetDetector(Phase).Detect(Job, ActiveJob, PhaseTransitionedAt)`. Each detector uses its phase-appropriate liveness signal. | Only the current phase's signal is consulted; misuse of other-phase signals is structurally impossible. |
| ST5 | Cleanup -- host-locality guard | Verify `ActiveJob.WorkerName == WorkerContext.Current().WorkerName` before any `KillProcess` call. If not, log skip and proceed to DB-only cleanup. | Cross-host kills structurally impossible. |
| ST6 | Cleanup -- kill target | Kill `ActiveJobs.FFmpegPid` (never `ProcessId`). If FFmpegPid is NULL, scan FFmpeg children of the worker PID + kill those. | Never kills the worker Python process. |
| ST7 | Cleanup -- DB state | `TranscodeQueue.Status='Pending'`, clear `ClaimedBy`/`ClaimedAt`/`DateStarted`. In-flight `TranscodeAttempts.Success=FALSE` with reason. `ActiveJobs` row DELETE. `TranscodeProgress` rows DELETE for the failed attempt. | DB-only cleanup safe across hosts; runs even when ST5 skipped the kill. |

## Phase Detectors (Strategy Table)

| Phase | Detector | Signal | Threshold key (SystemSettings) | Default |
|---|---|---|---|---|
| Setup | `SetupPhaseDetector` | Phase-age | `SetupPhaseTimeoutMin` | 30 |
| PreEncode | `PreEncodePhaseDetector` | Phase-age (Demucs pipeline) | `PreEncodePhaseTimeoutMin` | 20 |
| Encoding | `EncodingPhaseDetector` | `TranscodeProgress.LastFrameAdvance` + FFmpegPid liveness | `FrozenProgressThresholdMin` | 5 |
| PostEncode | `PostEncodePhaseDetector` | Phase-age | `PostEncodePhaseTimeoutMin` | 15 |
| Verifying | `VerifyingPhaseDetector` | Phase-age | `VerifyingPhaseTimeoutMin` | 60 |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | Entry: `_StuckJobDetectionLoop -> ST1` | `WorkerService/Main.py` daemon thread | Per-cycle invocation on `StuckJobDetectionIntervalSec` cadence | `DetectAndCleanStuckTranscodeJobs` runs per worker | `SELECT COUNT(*) FROM Logs WHERE FunctionName='DetectAndCleanStuckTranscodeJobs' AND TimeStamp > NOW() - INTERVAL '5 minutes'` >= 1 |
| S2 | `ST3 -> ST4` (Phase load -> Detector dispatch) | `JobProcessor` / `VideoTranscodingService` / `QualityTestingBusinessService` write `ActiveJobs.Phase` at each stage boundary via `SetJobPhase(ActiveJobId, JobPhase)` | `ActiveJobs.(Phase TEXT NULL, PhaseTransitionedAt TIMESTAMP NULL)` | `IsJobStuck` reads Phase; `PhaseDetectorRegistry.GetDetector(Phase)` returns detector | `TestJobPhaseTransitions.py`, `TestStuckJobDetectionPhaseAware.py` |
| S3 | `EncodingPhaseDetector` consumes `TranscodeProgress.LastFrameAdvance` | ffmpeg progress callback via `SaveTranscodeProgress` (UPDATE bumps `LastFrameAdvance` only when `CurrentFrame` changes; INSERT seeds NULL) | `TranscodeProgress.(TranscodeAttemptId BIGINT UNIQUE, LastFrameAdvance TIMESTAMP NULL, CurrentFrame INT, ProgressPercent FLOAT)` | `EncodingPhaseDetector._CheckFrameAdvanceStale` interprets NULL as "not yet recorded" -> not stuck | `TestPhaseDetectors.py::EncodingPhaseDetectorTest` |
| S4 | `ST7 -> requeue` (DB state reset) | `CleanupStuckJob` writes `TranscodeQueue.Status='Pending'`, `TranscodeAttempts.Success=FALSE` | Queue row returns to claim eligibility; attempt closed | `TranscodeQueueRepository.ClaimNextPendingJob` claims on next tick | `SELECT Status FROM TranscodeQueue WHERE Id=<id>` -> Pending post-cleanup |
| S5 | Host-locality invariant | `_StuckJobDetectionLoop` per-worker invocation | `ActiveJob.WorkerName == WorkerContext.Current().WorkerName` precondition before any `KillProcess` | Guard refuses cross-host kills; falls back to DB-only cleanup | `Logs` show "skipped kill: not local" markers |

## State Tables

```
ActiveJobs
  Id                    BIGINT
  ServiceName           TEXT      -- 'TranscodeService' | 'QualityTestService'
  QueueId               BIGINT    -- TranscodeQueue.Id
  ProcessId             BIGINT    -- worker's Python PID; NEVER kill
  FFmpegPid             BIGINT    -- ffmpeg subprocess PID; the only legit kill target
  WorkerName            TEXT
  Status                TEXT      -- 'Running' | 'Failed' | 'Completed'
  Phase                 TEXT      -- {Setup, PreEncode, Encoding, PostEncode, Verifying}
  PhaseTransitionedAt   TIMESTAMP
  StartedAt             TIMESTAMP

TranscodeProgress
  TranscodeAttemptId    BIGINT UNIQUE
  CurrentPhase          TEXT      -- coarse label (Demucs stage / ffmpeg phase)
  CurrentFrame          INT       -- 0 until first ffmpeg frame; drives LastFrameAdvance bump
  LastFrameAdvance      TIMESTAMP NULL  -- NULL on INSERT; NOW() only when CurrentFrame changes
  LastProgressUpdate    TIMESTAMP -- always NOW() on every write
  ProgressPercent       FLOAT
  TotalFrames           BIGINT

SystemSettings (relevant)
  StuckJobDetectionIntervalSec   -- loop cadence, default 120
  SetupPhaseTimeoutMin           -- default 30
  PreEncodePhaseTimeoutMin       -- default 20
  FrozenProgressThresholdMin     -- Encoding-phase threshold, default 5
  PostEncodePhaseTimeoutMin      -- default 15
  VerifyingPhaseTimeoutMin       -- default 60
```

## Failure Modes

- **Worker died abruptly**: heartbeat goes stale; `AttemptAbandonmentSweeper` (cross-worker) releases the attempt row. This flow does not run on the dead worker.
- **FFmpeg crashed but `FFmpegPid` is NULL**: ST6 fallback scans FFmpeg children of worker PID + kills those. Logged.
- **Second claimant race**: DB `ta_one_inflight_per_mfid` partial UNIQUE index refuses. Claimer catches IntegrityError + retries.
- **Detection-cycle exception**: catches + logs + sleeps to next interval. Bad cycle does not crash worker.

## Out of Scope

- Cross-host kill. Host-locality guard categorically forbids; kill side is local-only. DB cleanup is the only cross-host action.
- Scheduling / priority (this flow is a janitor).
- Manual operator trigger UI (covered by `/api/Service/StuckJobs/Cleanup` admin endpoint).
