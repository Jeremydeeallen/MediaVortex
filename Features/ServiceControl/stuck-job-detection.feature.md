# Stuck Job Detection

**Slug:** stuck-job-detection

## What It Does

Each in-flight transcode job carries an `ActiveJobs.Phase` label (`Setup`, `PreEncode`, `Encoding`, `PostEncode`, `Verifying`). Every worker runs a recurring detector loop that dispatches each of its owned jobs to a phase-specific `IPhaseDetector`. Each detector uses the liveness signal appropriate to its phase. Kill happens only when the detector for the CURRENT phase reports stuck.

Owner-scoped: each worker inspects and cleans only jobs it owns. Cross-worker abandonment routes through `AttemptAbandonmentSweeper` (heartbeat-driven).

## Success Criteria

C1. **`JobPhase` enum drives dispatch.** `Features/ServiceControl/JobPhase.py` = `{Setup, PreEncode, Encoding, PostEncode, Verifying}`. `PhaseDetectorRegistry.GetDetector(Phase)` returns exactly one `IPhaseDetector` per phase. Adding a new phase = one enum value + one detector class + one registry row (Open/Closed). Verifiable: `Tests/Contract/TestPhaseDetectors.py` per detector; `Tests/Contract/TestStuckJobDetectionPhaseAware.py` for dispatch.

C2. **`SetupPhaseDetector`** signal = time since phase-entry. Threshold = `SystemSettings.SetupPhaseTimeoutMin` (default 30). Setup covers path-resolve + attempt-record creation, before any subprocess spawns.

C3. **`PreEncodePhaseDetector`** signal = time since phase-entry. Threshold = `SystemSettings.PreEncodePhaseTimeoutMin` (default 20). PreEncode covers the Demucs pipeline (downmix / isolate / premix / measure). No frame-advance check -- ffmpeg has not spawned yet.

C4. **`EncodingPhaseDetector`** signal = `TranscodeProgress.LastFrameAdvance` recency + FFmpeg PID liveness. Threshold = `SystemSettings.FrozenProgressThresholdMin` (default 5). Fires only when Phase='Encoding' -- the ffmpeg subprocess is the only in-scope process here.

C5. **`PostEncodePhaseDetector`** signal = time since phase-entry. Threshold = `SystemSettings.PostEncodePhaseTimeoutMin` (default 15). Covers post-ffmpeg attestation writes + Probe + file replacement handoff.

C6. **`VerifyingPhaseDetector`** signal = time since phase-entry. Threshold = `SystemSettings.VerifyingPhaseTimeoutMin` (default 60 for VMAF, shorter for checksum). Covers cross-worker VMAF / StreamCopy verification.

C7. **`TranscodeProgress.LastFrameAdvance` seeds NULL on INSERT.** `TranscodeJobRepository.SaveTranscodeProgress` INSERT sets `LastFrameAdvance = NULL`; UPDATE bumps to `NOW()` only when `CurrentFrame` changes from prior value. Coarse phase progress (Demucs stage names, "Building Command", etc.) still writes rows via the same method but keeps `CurrentFrame=0`, so LastFrameAdvance stays NULL until real ffmpeg frames arrive. `EncodingPhaseDetector` interprets NULL as "not yet recorded" -> not stuck.

C8. **Detector loop runs every `SystemSettings.StuckJobDetectionIntervalSec` seconds** (default 120) per worker. Daemon thread joined on `ShutdownEvent`.

C9. **Owner-scoped kill.** `CleanupStuckJob` reads `ActiveJobs.FFmpegPid` and kills that PID via `ProcessManagementService.KillProcess`, guarded by `WorkerName == WorkerContext.Current().WorkerName`. Cross-worker rows are left alone -- `AttemptAbandonmentSweeper` handles those.

C10. **Zero pre-C21 kill paths.** Grep of `StuckJobDetectionService` for `DetectAndCleanHungEncodes` returns 0. `HungEncodeDetector.IsHung` retained only for dashboard display in `Features/Activity/Services/DashboardSnapshotService.py`.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `JobProcessor -> ActiveJobs.Phase transitions` | JobProcessor at each stage boundary | `SetJobPhase(ActiveJobId, JobPhase)` | detector selects matching detector per row | `TestJobPhaseTransitions.py` |
| S2 | `StuckJobDetectionService.IsJobStuck -> PhaseDetectorRegistry.GetDetector(Phase)` | Detection loop | `Phase: JobPhase` | `IPhaseDetector` instance | `TestStuckJobDetectionPhaseAware.py` |
| S3 | `EncodingPhaseDetector -> TranscodeProgress.LastFrameAdvance` | ffmpeg progress callback via `SaveTranscodeProgress` UPDATE (LastFrameAdvance bumped only on CurrentFrame change) | `datetime OR NULL` | not-stuck when NULL | `TestPhaseDetectors.py::EncodingPhaseDetectorTest` |

## Status

ACTIVE. Reset 28 landed PreEncode phase + LastFrameAdvance NULL-on-INSERT fix at commit `73438de`.

## Scope

```
Features/ServiceControl/JobPhase.py
Features/ServiceControl/PhaseDetectors/*.py
Features/ServiceControl/PhaseDetectorRegistry.py
Features/ServiceControl/StuckJobDetectionService.py
Features/ServiceControl/AttemptAbandonmentSweeper.py
Features/TranscodeJob/Worker/JobProcessor.py    -- sets Phase=PreEncode before Demucs
Features/TranscodeJob/VideoTranscodingService.py -- sets Phase=Encoding at ffmpeg spawn
Features/TranscodeJob/TranscodeJobRepository.py  -- SaveTranscodeProgress INSERT with LastFrameAdvance=NULL
Features/QualityTesting/QualityTestingBusinessService.py -- sets Phase=Verifying
```

## Files

| File | Role |
|---|---|
| `Features/ServiceControl/JobPhase.py` | Enum: Setup/PreEncode/Encoding/PostEncode/Verifying |
| `Features/ServiceControl/PhaseDetectorRegistry.py` | Strategy dispatch |
| `Features/ServiceControl/PhaseDetectors/SetupPhaseDetector.py` | C2 |
| `Features/ServiceControl/PhaseDetectors/PreEncodePhaseDetector.py` | C3 |
| `Features/ServiceControl/PhaseDetectors/EncodingPhaseDetector.py` | C4 |
| `Features/ServiceControl/PhaseDetectors/PostEncodePhaseDetector.py` | C5 |
| `Features/ServiceControl/PhaseDetectors/VerifyingPhaseDetector.py` | C6 |
| `Features/ServiceControl/StuckJobDetectionService.py` | Loop + IsJobStuck dispatch + owner-scoped kill |
| `Features/ServiceControl/AttemptAbandonmentSweeper.py` | Cross-worker heartbeat sweeper |
| `Tests/Contract/TestPhaseDetectors.py` | Per-detector unit contracts |
| `Tests/Contract/TestJobPhaseTransitions.py` | Phase-write DB contract |
| `Tests/Contract/TestStuckJobDetectionPhaseAware.py` | Dispatch + owner-scope + regression fences |
