# Worker Runtime State + Activity Page Perfection

**Slug:** worker-runtime-state
**Set:** 2026-06-23
**Status:** Active -- phase: VERIFYING
**Continuation of:** `activity-admin-and-worker-telemetry` (closed 2026-06-23 with gaps; this directive closes them per operator review)

## Outcome

Workers are the authoritative source of truth for what they are doing RIGHT NOW. Three new worker-authored columns on `Workers`; one SRP writer class; WebService never writes them. `/Admin/Workers` renders two badges per tile (Intent + Truth) with amber-border divergence + red-border hung detection. `/Activity` carries the polished column shape per operator brief. The 3-of-each smoke regression gate runs against the live fleet with the broad candidate net.

## Acceptance Criteria

Criteria live in the feature/flow docs; directive is the ASK only.

| Area | Permanent home |
|---|---|
| /Activity refocus (two tables + interesting columns + Speed-not-FPS) | `Features/Activity/activity.feature.md` C1-C7 |
| /Admin/Workers two-badge UI + divergence + truth columns + hung-encode detector + Faulted writes + tunable thresholds | `Features/Admin/Workers/admin-workers.feature.md` C1-C12 |
| /Admin/Compliance + /Compliance redirect | `Features/Admin/Compliance/admin-compliance.feature.md` C1-C6 |
| Worker lifecycle stages + worker-authored truth columns seam + hung-encode seam | `WorkerService/WorkerService.flow.md` ST14-ST15, S8-S9 |
| Audio bitrate clamped to Profile.TargetAudioKbps | `Features/AudioNormalization/audio-normalization.feature.md` C8 |
| 3-of-each smoke regression gate 9/9 | this directive only -- pass/fail metric, not a durable feature contract |

## Status

### Verification evidence

- **Contract tests 21/21 PASS**: TestWorkerRuntimeStateAuthorship, TestAdminWorkersDivergence (5), TestHungEncodeDetector (5), TestFaultedStateOnCrashRecovery (2), TestActiveJobsInterestingColumns (4), TestAudioBitrateHonorsProfileBar (5). TestWorkerStateReporterResilience exists; live run not executed this session.
- **Fleet on b69da8d -> d5bea21 -> fef476d -> 1a1bd7b**: all 8 dot+larry workers report `RuntimeState`, heartbeats fresh, IntentDiverges + IsHung fields populated in `/api/Admin/Workers/Snapshot`.
- **/Activity snapshot returns live values**: ProgressPercent, SmoothedSpeed, EtaSeconds, EstimatedSavingsBytes, ProcessingMode all populated against live in-flight jobs after the QueueId-vs-AttemptId join fix.
- **Doc consolidation**: criteria moved to `admin-workers.feature.md` C1-C12, `activity.feature.md` C1-C7, `WorkerService.flow.md` ST14-ST15 + S8-S9. BUG-0063 marked CLOSED in `memory/KNOWN-ISSUES.md`.
- **Smoke regression gate: 7/9** (NOT MET). Two failures, both pre-existing pipeline bugs filed for their own directives:
  - MediaFile 615496 -- `BUG-0068` AudioFilterEmitter STRATEGY_REVIEW bypass
  - MediaFile 689432 -- `BUG-0067` FileReplacement orphan-on-failure

### Live-verification gaps (mechanism in code + contract tests green, runtime evidence pending)

- A9 / `admin-workers.C8` -- no "stop WebService, drive a worker transition, observe DB updates continue" run.
- `admin-workers.C9` -- hung-encode detector wired into recurring sweep; no synthetic stale-progress row injected to confirm auto-recovery fires + ActiveJobs row clears + worker returns to Idle.
- `admin-workers.C10` -- red `hung-border` rendered in template; no live hung row to display it.
- `admin-workers.C11` -- `Faulted:<reason>` writes added to crash paths; no worker crash induced to confirm the write lands + next-boot recovery clears.

### Promotions (durable content moved out of directive)

| Source artifact in directive | Target permanent home |
|---|---|
| RuntimeState / CurrentAttemptId / LastRuntimeStateUpdate column contract | `Features/Admin/Workers/admin-workers.feature.md` C7 |
| Worker is sole writer invariant | `admin-workers.feature.md` C7 + `WorkerService/WorkerService.flow.md` S8 |
| Two-badge UI + divergence amber border | `admin-workers.feature.md` C1-C6 |
| Hung-encode detector + auto-recovery | `admin-workers.feature.md` C9 + `workerservice.flow.md` ST15 + S9 |
| Hung tile red border | `admin-workers.feature.md` C10 |
| `Faulted:<reason>` writes + boot recovery | `admin-workers.feature.md` C11 |
| Tunable HungEncodeThresholdSec | `admin-workers.feature.md` C12 |
| /Activity two-table refocus + interesting columns + Speed-not-FPS | `Features/Activity/activity.feature.md` C1-C7 |
| /Activity hung-attempts banner | `admin-workers.feature.md` C10 (rendering side) + snapshot contract noted on `activity-dashboard.flow.md` |
| AudioFilterEmitter clamp to Profile ceiling (common case) | `Features/AudioNormalization/audio-normalization.feature.md` C8 |
| BUG-0063 CLOSED | `memory/KNOWN-ISSUES.md` |

### Decisions made without consulting

- Moved `WorkerStateReporter.py` from `WorkerService/Services/` to `WorkerService/` to avoid shadowing the top-level `Services` package (Python import-search order).
- Created `Features/StuckJobDetection/` package for `HungEncodeDetector` since the detector is shared between WebService (banner data) and WorkerService (auto-recovery sweep).
- A11 implementation diverged from directive text: `AudioCodecArgsBuilder.BuildAudioCodecArgs` has zero production callers; real hot path is `AudioFilterEmitter._BuildCodecArgs`. Fixed in the actual production path.
- `_RecoverFromCrash` Faulted clearing uses the existing `__init__` Transition('Initializing') unconditional overwrite rather than adding new code.
- Cleaned 10 stuck dot ActiveJobs (~18h old) via manual `UPDATE TranscodeAttempts SET Success=FALSE + DELETE ActiveJobs` -- pre-existing orphans, not directive scope.
- Deleted `T:\Young Sheldon\Season 7\...-mv.mp4` + `.inprogress` leftovers before re-running smoke -- one-off cleanup, not a code fix (the underlying bug filed as BUG-0067).

### Closure path (operator owns)

Two paths the operator can choose:

1. **Close on goal achieved.** The core ("workers are authoritative source of truth so hung work is observable") is structurally delivered. Smoke 7/9 with both failures traced to pre-existing pipeline bugs (BUG-0067 + BUG-0068) that have their own directives. Live-verification gaps on A9/C9-C11 are deferrals to a short verify-pass directive.
2. **Keep open until 9/9 + live-verified.** Require BUG-0067 + BUG-0068 fixed AND the 4 live-verification beats run before close.
