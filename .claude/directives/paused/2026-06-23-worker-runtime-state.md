# Worker Runtime State + Activity Page Perfection

**Slug:** worker-runtime-state
**Set:** 2026-06-23
**Status:** PAUSED -- 2026-06-25 -- awaiting audio cluster shipment to unblock smoke 9/9
**Continuation of:** `activity-admin-and-worker-telemetry` (closed 2026-06-23 with gaps; this directive closes them per operator review)

## Paused: 2026-06-25

Beats C8/C9/C10/C11 verified live (see Status block); C10 IsHung wiring bug found + fixed (commit 5b8f0c4 + new contract test). Smoke gate still 7/9 because BUG-0068 (AudioFilterEmitter STRATEGY_REVIEW bypass + TranscodeShape bare `-c:a copy` fallback) blocks the last point. Operator chose 2026-06-25 to ship the SOLID + DDD audio cluster (`audio-pipeline-fail-loud`) before resuming this directive, rather than fold a surgical BUG-0068 patch that would recreate the silent-fallback anti-pattern.

**Resume conditions:**
1. `audio-pipeline-fail-loud` closes (BUG-0068 closed within it, smoke MediaFile 615496 passes during the cluster's phase D exit gate).
2. `git mv .claude/directives/paused/2026-06-23-worker-runtime-state.md .claude/directive.md`
3. Edit Status line back to `Active -- phase: VERIFYING`.
4. Re-run `Scripts/Smoke/ThreeOfEachBucketSmoke.py`; confirm 9/9 (BUG-0067 + BUG-0068 both closed at smoke level).
5. Record final smoke evidence in Status; advance to DELIVERING; populate Promotions; close.

## Files

| File | Role |
|---|---|
| `Features/FileReplacement/TranscodedOutputPlacement.py` | `Execute` lines 219-230 + `FinalizePartialReplacement` lines 278-284: replace orphan-on-failure fallback with rollback + loud failure (BUG-0067). SameSlot path: defer BackupPath delete until after MediaFiles update succeeds. |
| `Features/FileReplacement/transcoded-output-placement.feature.md` | Add C13 (rollback-on-update-failure invariant) + S4 (rollback seam) covering the BUG-0067 fix. |
| `Tests/Contract/TestFileReplacementRollbackOnUpdateFailure.py` | New contract test asserting Execute returns Success=False on update failure AND the `-mv.mp4` orphan is removed AND the source survives (both SameSlot + non-SameSlot). |
| `Scripts/SQLScripts/CleanupDuplicateSourcesFromBug0067.py` | One-shot cleanup: deletes the SOURCE file + DB row for Cat A+B pairs in `memory/duplicate-shows-2026-06-23.md` (legitimate MV -mv.<ext> output paired with a resurrected source). Dry-run default; --execute to actually delete. Cat C surfaced for separate operator review. |
| `Scripts/SQLScripts/AlterTranscodeAttemptsMediaFileIdNullable_2026_06_23.py` | Fix schema conflict surfaced by BUG-0067 cleanup: `TranscodeAttempts.mediafileid` declared NOT NULL while FK declares `ON DELETE SET NULL` -- mutually inconsistent. Migration drops NOT NULL to match the FK's declared intent, preserving audit history when a MediaFile is deleted. Idempotent. |
| `transcode.flow.md` | Stage 8 (ACTION) + Phase 7 (lifecycle reference) carry stale claims that don't match current code: `.orig` backup that doesn't exist, `ProfileThresholds.KeepSource` references that no code reads, `.old` rename that doesn't happen, `_ProcessCompleteFileReplacement` / `_CleanupTemporaryFilePaths` / `BypassVMAFCheck` function/parameter names that have been renamed or retired, no documentation of BUG-0067 update-failure rollback, no documentation of SameSlot vs non-SameSlot rename paths. Rewrite both sections to match current code (post 2026-05-21 `drop-local-staging`, post 2026-06-02 `filereplacement-decompose`, post 2026-06-23 BUG-0067 fix). |

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
- **Smoke regression gate: 7/9** (NOT MET). Two failures, both pre-existing pipeline bugs:
  - MediaFile 615496 -- `BUG-0068` AudioFilterEmitter STRATEGY_REVIEW bypass (open)
  - MediaFile 689432 -- `BUG-0067` FileReplacement orphan-on-failure -- **fix landed via /t BUG-0067 2026-06-23**: `TranscodedOutputPlacement.Execute` failure branch now rolls back the rename + returns `Success=False` with the real update error (was silent `Success=True` + orphan on disk); `FinalizePartialReplacement` parallel fix; SameSlot path defers BackupPath delete until after update commits so rollback can restore source. Evidence: `Tests/Contract/TestFileReplacementRollbackOnUpdateFailure.py` 3/3 PASS + **live smoke against MediaFile 689432**: 126MB orphan renamed to `.inprogress`, Execute invoked on real DB + real filesystem, `_UpdateMediaFilesAfterReplacement` returned Success=False (ffprobe path-shape error), rollback fired, target `-mv.mp4` removed, source `.mkv` (624MB) intact at pre-call state -- `Result.Success=False`, `RollbackErrors=None`, StepsCompleted recorded rename + verify + rollback sequence. C13 + S4 promoted to `Features/FileReplacement/transcoded-output-placement.feature.md`. Accumulated duplicate-pair state from prior pre-fix failures cleaned up via `Scripts/SQLScripts/CleanupDuplicateSourcesFromBug0067.py --execute --include-unflagged-both`: 105 disk-aware pairs resolved (66 BothOnDisk -> source file + row deleted; 1 OnlyMvOnDisk -> stale src row deleted; 37 OnlySrcOnDisk -> stale mv row deleted; 1 NeitherOnDisk -> both rows deleted); 66 files removed from disk; 106 MediaFile rows deleted (38 mv + 68 src); final dry-run confirms 0 pairs remain. **Schema conflict surfaced + fixed**: `TranscodeAttempts.mediafileid` was `NOT NULL` while FK declared `ON DELETE SET NULL` -- mutually inconsistent. Migration `Scripts/SQLScripts/AlterTranscodeAttemptsMediaFileIdNullable_2026_06_23.py` dropped NOT NULL (is_nullable NO -> YES); idempotent (re-run reports no-op); cleanup script's manual TranscodeAttempts/TranscodeFiles prune removed since FK SET NULL now fires correctly preserving audit rows; FailureBudgetResets still explicit (no declared FK). Report: `memory/duplicate-shows-2026-06-23.md`; execute log: `memory/cleanup-duplicate-shows-execute-2026-06-23.log`.

### Live-verification beats run 2026-06-24

- **A9 / `admin-workers.C8` -- GREEN.** WebService stopped on I9 (PIDs 32560 + 39376) at 20:22:52 local; held down ~90s. All 8 active workers (dot-1..4, larry-1..4) advanced `Workers.LastHeartbeat` + `LastRuntimeStateUpdate` during the down-window (e.g. dot-worker-1: 02:21:43.55 -> 02:23:13.56 UTC). Verifies workers write to DB independently of WebService. WebService restarted; parent+child = 2 processes confirmed.
- **`admin-workers.C9` -- GREEN.** Synthetic `TranscodeAttempts.Id=39555` (Success=NULL); `wakko-worker-1` injected with `RuntimeState='Encoding'`, `CurrentAttemptId=39555`, `LastRuntimeStateUpdate=NOW()-700s`. `StuckJobDetectionService().DetectAndCleanHungEncodes()` returned `{'HungFound':1, 'JobsCleaned':1, 'Hung':[{'AttemptId':39555,'WorkerName':'wakko-worker-1','FFmpegPid':None}]}`. After: `TranscodeAttempts.Success=False, ErrorMessage='hung_encode_detector'`. Synthetic state cleaned.
- **`admin-workers.C10` -- GREEN (after bug fix).** Discovered + fixed regression in `Features/Admin/Workers/AdminWorkersRepository.GetTiles`: `Tile = dict(R)` stripped the `CaseInsensitiveDict` wrapper, so `Tile.get('runtimestate')` returned `None` -- `IsHung` and `IntentDiverges` both wired to lowercase keys that no longer existed in the unwrapped dict, both stuck at `False` regardless of actual state. Fix: `Tile = CaseInsensitiveDict(R)` (one-line). New contract test `Tests/Contract/TestAdminWorkersIsHungWiredToSnapshot.py` PASSES (catches regression). Live verification post-fix + WebService restart: `/api/Admin/Workers/Snapshot` for synthetic hung wakko-worker-1 returns `IsHung=True, IntentDiverges=True, RuntimeState='Encoding', runtimestateagesec=704`.
- **`admin-workers.C11` -- GREEN.** Synthetic `Workers.RuntimeState='Faulted:SyntheticC11'` written on wakko-worker-1; `WorkerStateReporter(Db, 'wakko-worker-1').Transition('Initializing')` (same call worker `__init__` makes on boot) flipped state to `RuntimeState='Initializing', CurrentAttemptId=NULL`. Boot-recovery clearance verified end-to-end. Existing `Tests/Contract/TestFaultedStateOnCrashRecovery.py` 2/2 covers the Faulted-write side mechanically.

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
