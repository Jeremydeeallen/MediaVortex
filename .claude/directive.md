# Worker Runtime State + Activity Page Perfection

**Slug:** worker-runtime-state
**Set:** 2026-06-23
**Status:** Active -- phase: IMPLEMENTING (REOPENED 2026-06-23 -- criteria narrower than goal; see A14-A17)
**Continuation of:** `activity-admin-and-worker-telemetry` (closed 2026-06-23 with gaps; this directive closes them per operator review)

## Outcome

Workers are the authoritative source of truth for what they are doing RIGHT NOW. Three new worker-authored columns on `Workers`; one SRP writer class; WebService never writes them. `/Admin/Workers` renders two badges per tile -- Intent (operator-set) and Truth (worker-set) -- with a divergence warning when they disagree. `/Activity` carries the polished column shape per operator brief. Existing feature + flow docs reflect this contract in English. The 3-of-each smoke regression gate passes 9/9 against the live fleet WITHOUT the picker-tightening workaround applied earlier today.

## Acceptance Criteria

Criteria live in the feature/flow docs; directive is the ASK only.

| Area | Permanent home |
|---|---|
| /Activity refocus (two tables + interesting columns + Speed-not-FPS) | `Features/Activity/activity.feature.md` C1-C7 |
| /Admin/Workers two-badge UI + divergence + truth columns + hung-encode detector + Faulted writes + tunable thresholds | `Features/Admin/Workers/admin-workers.feature.md` C1-C12 |
| /Admin/Compliance + /Compliance redirect | `Features/Admin/Compliance/admin-compliance.feature.md` C1-C6 |
| Worker lifecycle stages + worker-authored truth columns seam + hung-encode seam | `WorkerService/WorkerService.flow.md` ST14-ST15, S8-S9 |
| Audio bitrate clamped to Profile.TargetAudioKbps | `Features/AudioNormalization/audio-normalization.feature.md` C8 (encoder honors per-profile ceiling) |
| 3-of-each smoke regression gate 9/9 | this directive only -- pass/fail metric, not a durable feature contract |
| SOLID + constructor-DI throughout | judgment standard from `.claude/standards/index.md` -- not a per-criterion contract |

## Files

| File | Role | Criterion |
|---|---|---|
| `Scripts/SQLScripts/AddWorkerRuntimeStateColumns.py` | NEW migration: 3 new Workers columns + WorkerIntentDivergenceSec SystemSetting | A7, A13 |
| `WorkerService/WorkerStateReporter.py` | NEW SRP writer (single-file at WorkerService root to avoid shadowing top-level Services package); also writes Faulted:<reason> on uncaught exception | admin-workers.C7-C11 |
| `Scripts/SQLScripts/AddHungEncodeThresholdSetting.py` | NEW idempotent: seeds SystemSettings.HungEncodeThresholdSec=600 | admin-workers.C12 |
| `Features/StuckJobDetection/HungEncodeDetector.py` | NEW pure function (RuntimeState, AttemptId, RuntimeStateAge, ProgressAge, Threshold, Now) -> bool | admin-workers.C9 |
| `Features/StuckJobDetection/StuckJobDetectionService.py` | EXTEND: invoke HungEncodeDetector + kill ffmpeg + flip Attempt.Success=False + clear ActiveJobs row | admin-workers.C9 |
| `Tests/Contract/TestHungEncodeDetector.py` | NEW | admin-workers.C9 |
| `Tests/Contract/TestFaultedStateOnCrashRecovery.py` | NEW | admin-workers.C11 |
| `WorkerService/Main.py` | Wire WorkerStateReporter into lifecycle (Init, Idle, Claim, Encode, Drain, Pause, Fault transitions) | A8, A9 |
| `Features/Admin/Workers/AdminWorkersRepository.py` | Surface RuntimeState + CurrentAttemptId + LastRuntimeStateUpdate + Intent-vs-Truth divergence flag | A4 |
| `Features/Admin/Workers/AdminWorkersController.py` | Include divergence threshold in snapshot payload | A4, A13 |
| `Templates/AdminWorkers.html` | Two-badge tiles + divergence amber border | A4 |
| `Templates/Activity.html` | Add interesting columns (Target Res / Codec Change / Estimated Savings); ensure Speed not FPS | A2, A3 |
| `Features/Activity/ActivityController.py` | `/api/Activity/Snapshot` payload includes the new per-job columns | A2 |
| `Features/Activity/ActivityRepository.py` | Source columns for the new per-job interesting data | A2 |
| `Features/AudioNormalization/AudioFilterEmitter.py` | Clamp TrackConfig.Bitrate down to EffectiveProfile.TargetAudioKbps when set | A11 |
| `Scripts/Smoke/ThreeOfEachBucketSmoke.py` | Revert picker tightening | A11 |
| `Features/Activity/activity.feature.md` | Doc consolidation | A12 |
| `Features/Activity/activity-dashboard.flow.md` | Doc consolidation | A12 |
| `Features/Admin/Workers/admin-workers.feature.md` | Doc consolidation | A12 |
| `WorkerService/WorkerService.flow.md` | Doc consolidation | A12 |
| `memory/KNOWN-ISSUES.md` | BUG-0063 closed | A12 |
| `Tests/Contract/TestWorkerStateReporterResilience.py` | NEW resilience test | A9 |
| `Tests/Contract/TestWorkerRuntimeStateAuthorship.py` | NEW: grep-based check that only WorkerStateReporter writes the three columns | A8 |
| `Tests/Contract/TestAdminWorkersDivergence.py` | NEW: tile-level divergence flag in snapshot payload | A4 |
| `Tests/Contract/TestActiveJobsInterestingColumns.py` | NEW: snapshot endpoint contains Target / CodecChange / SavingsEstimate fields | A2 |
| `Tests/Contract/TestAudioBitrateHonorsProfileBar.py` | NEW | A11 |

## SOLID Plan

| Class | Single responsibility | DI |
|---|---|---|
| `WorkerStateReporter` | Direct-DB worker-state writes | `(Db, WorkerName, Clock)` |
| `WorkerRuntimeContext` (NEW) | In-memory tracking of `CurrentAttemptId` between Encode-start and Encode-end | none (thread-local) |
| `AdminWorkersRepository.GetTiles` | Worker tile data with divergence flag computed at fetch time | existing |
| `_DeriveDivergence` (pure function) | Given (Status, RuntimeState, LastRuntimeStateUpdate, ThresholdSec) return bool | n/a |

## Hook Pre-Flight + Ordering

The hook gates are deterministic. The plan executes in the only order that NEVER trips them:

| Rule | Trip pattern | Avoidance ordering |
|---|---|---|
| R1 | Edit code without reading colocated `*.feature.md` / `*.flow.md` | All prereads done in NEEDS_DOC_PREREAD phase; partial reads with `# see <slug>.<ID>` anchors. |
| R2 | INSERT numeric literal without `# from: <path>` citation; cited path must EXIST and CONTAIN the literal | **Update feature doc FIRST** with the literal value as part of the contract text, **THEN** write the migration citing that feature doc. |
| R11 | `CREATE TABLE` / `CREATE INDEX` without `IF NOT EXISTS`; `INSERT INTO` without `ON CONFLICT` | Migration always uses both. |
| R12 | Consecutive `#` comments > 1 line; docstrings > 1 line; module-level docstrings | Single-line class docstring; per-method 1-line WHY comments only. |
| R13 | NEW `*.feature.md` / `*.flow.md` outside DELIVERING phase | NO new feature/flow docs. All 4 doc updates target EXISTING files. |
| R14 | Annotation lines (`removed YYYY-MM-DD`, `deprecated`, `previously`) on existing feature doc edits | Delete superseded sections cleanly. Replace with single-line pointer or new prose. |
| R15 | Edits to functions in directive `## Files` without `# directive: worker-runtime-state` anchor | Carry the anchor on every edited def/class. |
| R16 | Feature doc lacks `**Slug:** <slug>` in first 15 lines | The 4 existing docs already have slugs. Verified. |
| R18 | `Read(*.feature.md)` without `limit<=50` | All feature doc reads use `limit=50` (or smaller) + offset paging. |

**Implementation order (each step pre-cleared against the hook):**

1. Update `Features/Admin/Workers/admin-workers.feature.md` with the new criteria text INCLUDING the `WorkerIntentDivergenceSec=60` literal. This becomes R2's citation source for the migration.
2. Update `Features/Activity/activity.feature.md` (refocus W6/W7 worker rows + Success Criteria) + `Features/Activity/activity-dashboard.flow.md` (remove worker stage; note RuntimeState seam).
3. Update `WorkerService/WorkerService.flow.md` adding ST14 (RuntimeState writes) + S8 (worker-authored truth columns).
4. Write `Scripts/SQLScripts/AddWorkerRuntimeStateColumns.py` citing the admin-workers feature doc for the `60` literal (R2 cleared).
5. Run migration; verify columns present.
6. Write `WorkerService/Services/WorkerStateReporter.py` (SRP).
7. Wire into `WorkerService/Main.py` at appropriate lifecycle hooks.
8. Update `AdminWorkersRepository.GetTiles` to surface RuntimeState + divergence flag.
9. Update `AdminWorkersController` snapshot payload.
10. Update `Templates/AdminWorkers.html` with two-badge UI + divergence border.
11. Update `Features/TranscodeJob/Emit/AudioCodecArgsBuilder.py` to honor `Profile.TargetAudioKbps`.
12. Update `Features/TranscodeJob/Emit/TranscodeShape.py` + `RemuxShape.py` callers.
13. Update `Templates/Activity.html` with interesting columns (Target / Codec Change / Savings).
14. Update `ActivityRepository` + `DashboardSnapshotService` to source the new per-job columns.
15. Revert smoke picker tightening.
16. Mark `BUG-0063` closed in `memory/KNOWN-ISSUES.md`.
17. Write 5 contract tests.
18. Restart WebService + redeploy workers.
19. Run smoke regression gate; require 9/9.
20. VERIFYING + DELIVERING + close.

## Status

NEEDS_PLAN. Operator-acknowledged that the prior directive was closed prematurely.
