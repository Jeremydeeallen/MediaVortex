# Worker Runtime State + Activity Page Perfection

**Slug:** worker-runtime-state
**Set:** 2026-06-23
**Status:** Active -- phase: NEEDS_PLAN
**Continuation of:** `activity-admin-and-worker-telemetry` (closed 2026-06-23 with gaps; this directive closes them per operator review)

## Outcome

Workers are the authoritative source of truth for what they are doing RIGHT NOW. Three new worker-authored columns on `Workers`; one SRP writer class; WebService never writes them. `/Admin/Workers` renders two badges per tile -- Intent (operator-set) and Truth (worker-set) -- with a divergence warning when they disagree. `/Activity` carries the polished column shape per operator brief. Existing feature + flow docs reflect this contract in English. The 3-of-each smoke regression gate passes 9/9 against the live fleet WITHOUT the picker-tightening workaround applied earlier today.

## Acceptance Criteria

A1. **`/Activity` page renders ONLY two tables: Active Jobs + Active Scans.** Polls `/api/Activity/Snapshot` every 5 seconds. No worker tiles, no library-compliance card, no settings modals. Verifiable: `grep -E 'WorkersMount|VersionMismatchBanner|WorkerSettingsModal|ComplianceContainer' Templates/Activity.html` returns 0.

A2. **Active Jobs table columns** (renamed from "Active Transcode Jobs" to "Active Jobs"):
  - File / Size / Worker / Job Type / Speed / Progress / ETA
  - Plus three interesting columns: Target Resolution (e.g. `1080p -> 720p`), Codec Change (e.g. `h264 -> av1`), Estimated Savings (e.g. `-1.2 GB`; blank for Remux / AudioFix where the metric is not meaningful)
  - **Speed replaces FPS universally.** FPS is dropped (only meaningful for Transcode). `CurrentSpeed` (multiplier vs realtime) works for all three job types. Verifiable: `grep CurrentFPS Templates/Activity.html` returns 0 in the rendered template; `grep CurrentSpeed Templates/Activity.html` returns >= 1.

A3. **Active Scans table columns**: Drive / Worker / Phase / Progress / Files (processed of total) / ETA. Verifiable: rendered page has the six column headers.

A4. **`/Admin/Workers` tiles show TWO badges per worker**:
  - **Intent badge** = `Workers.Status` (operator-set: Online / Paused). Source: existing column.
  - **Truth badge** = `Workers.RuntimeState` (worker-set: Initializing / Idle / ClaimingJob / Encoding / Scanning / Draining / Paused / Faulted:<reason>). Source: new column written by `WorkerStateReporter`.
  When the two values disagree for >60s, the tile renders with an amber border + a tooltip explaining the divergence. Verifiable: stop a worker process while operator-Status is `Online`; observe the tile shows an amber border within 60s of the heartbeat going stale (RuntimeState frozen).

A5. **`/Admin/Compliance` renders library-compliance counts + bucket breakdown + audio-state breakdown.** Polls `/api/Admin/Compliance/Snapshot` every 5s. (Already in place from prior directive; just re-verify here.)

A6. **`/Compliance` legacy URL responds with HTTP 301 + Location `/Admin/Compliance`.** (Already in place; re-verify.)

A7. **Workers own their runtime state.** Three new columns on `Workers`:
  - `RuntimeState TEXT NULL` -- worker-authored
  - `CurrentAttemptId BIGINT NULL` -- non-null exactly when `RuntimeState='Encoding'`; points at `TranscodeAttempts.Id`
  - `LastRuntimeStateUpdate TIMESTAMP NULL` -- written every state transition AND every heartbeat tick (so freshness is observable)
  Migration: `Scripts/SQLScripts/AddWorkerRuntimeStateColumns.py` -- idempotent `ADD COLUMN IF NOT EXISTS`.

A8. **`WorkerStateReporter` is the only writer.** New SRP class at `WorkerService/Services/WorkerStateReporter.py`. Constructor-DI on `(Db, WorkerName)`. Single public method `Transition(NewState, AttemptId=None)`. Writes all three new columns atomically. WebService never writes them. Verifiable: `grep -rn 'RuntimeState\|CurrentAttemptId\|LastRuntimeStateUpdate' Features/ WebService/` returns 0 writes (only reads).

A9. **WebService-outage resilience proven end-to-end.** Test `TestWorkerStateReporterResilience.py`: stop WebService, drive a worker through its lifecycle (Idle -> ClaimingJob -> Encoding -> Idle), observe each transition in `Workers.RuntimeState`. Bring WebService back; `/api/Admin/Workers/Snapshot` reflects the current truth immediately without manual recompute.

A10. **SOLID-clean implementation.** No god-functions added to existing controllers. Every new responsibility is its own class:
  - `WorkerStateReporter` -- direct-DB state writer (SRP)
  - `AdminWorkersRepository` (existing) extended with one method `_DeriveDivergence` (pure function) -- no inline branching in the controller
  - Activity / AdminWorkers JS modules each own one concern -- single render function, single fetch path
  Constructor-DI throughout.

A11. **3-of-each smoke regression gate passes 9/9 with the BROAD candidate net.** Revert the picker tightening (`MaxAudioChannels=2 + Resolutions=['480p','720p']`) introduced earlier today as a workaround. To pass 9/9 with the broader net, this directive must ALSO fix the audio-bitrate-honors-profile-bar concern: `AudioCodecArgsBuilder.BuildAudioCodecArgs` must use `Profile.TargetAudioKbps` as the ceiling (rather than the channel-count default) when it is set. Verifiable: `Scripts/Smoke/ThreeOfEachBucketSmoke.py` 9/9; `Tests/Contract/TestAudioBitrateHonorsProfileBar.py` green.

A12. **Doc consolidation completed.** Existing feature + flow docs reflect the new contract IN ENGLISH, with the criteria above translated into per-doc verifiable statements:
  - `Features/Activity/activity.feature.md` -- updated What It Does + Workflows (W6/W7 worker actions removed since they moved) + Success Criteria (focused on tables, not worker UI)
  - `Features/Activity/activity-dashboard.flow.md` -- ST3 (worker tiles) removed; flow describes Active Jobs + Active Scans + queue counts only
  - `Features/Admin/Workers/admin-workers.feature.md` -- adds the Intent vs Truth two-badge contract + divergence warning + RuntimeState enum
  - `WorkerService/WorkerService.flow.md` -- adds ST14 (RuntimeState reporting) + seam S8 (worker-authored truth columns)
  - `memory/KNOWN-ISSUES.md` -- `BUG-0063 CLUSTER` marked CLOSED with reference to this directive

A13. **The 60s divergence threshold is operator-tunable** via `SystemSettings.WorkerIntentDivergenceSec` (default 60). Verifiable: `UPDATE SystemSettings SET SettingValue='30'` -- next page poll observes the new threshold.

## Files

| File | Role | Criterion |
|---|---|---|
| `Scripts/SQLScripts/AddWorkerRuntimeStateColumns.py` | NEW migration: 3 new Workers columns + WorkerIntentDivergenceSec SystemSetting | A7, A13 |
| `WorkerService/Services/WorkerStateReporter.py` | NEW SRP writer | A8 |
| `WorkerService/Services/__init__.py` | Package marker | A8 |
| `WorkerService/Main.py` | Wire WorkerStateReporter into lifecycle (Init, Idle, Claim, Encode, Drain, Pause, Fault transitions) | A8, A9 |
| `Features/Admin/Workers/AdminWorkersRepository.py` | Surface RuntimeState + CurrentAttemptId + LastRuntimeStateUpdate + Intent-vs-Truth divergence flag | A4 |
| `Features/Admin/Workers/AdminWorkersController.py` | Include divergence threshold in snapshot payload | A4, A13 |
| `Templates/AdminWorkers.html` | Two-badge tiles + divergence amber border | A4 |
| `Templates/Activity.html` | Add interesting columns (Target Res / Codec Change / Estimated Savings); ensure Speed not FPS | A2, A3 |
| `Features/Activity/ActivityController.py` | `/api/Activity/Snapshot` payload includes the new per-job columns | A2 |
| `Features/Activity/ActivityRepository.py` | Source columns for the new per-job interesting data | A2 |
| `Features/TranscodeJob/Emit/AudioCodecArgsBuilder.py` | Use Profile.TargetAudioKbps as ceiling | A11 |
| `Features/TranscodeJob/Emit/TranscodeShape.py` | Pass Profile.TargetAudioKbps to AudioCodecArgsBuilder | A11 |
| `Features/TranscodeJob/Emit/RemuxShape.py` | Same | A11 |
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

## Hook Pre-Flight

- R1: Read existing feature/flow docs in NEEDS_DOC_PREREAD before editing them at IMPLEMENTING.
- R11: Migration uses `ADD COLUMN IF NOT EXISTS` + `INSERT ... ON CONFLICT` for SystemSettings seed.
- R12: New class has 1-line class docstring; per-method comments capped at one line.
- R13: NO new `*.feature.md` files. The 4 doc updates are all EDITS to EXISTING files.
- R14: Doc edits delete superseded sections cleanly. No `removed YYYY-MM-DD` annotations.
- R15: Code edits in directive Files list carry `# directive: worker-runtime-state` anchor.
- R18: Feature doc reads with limit<=50.

## Status

NEEDS_PLAN. Operator-acknowledged that the prior directive was closed prematurely.
