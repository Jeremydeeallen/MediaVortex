# Worker Lifecycle Simplification

## Summary

Simplify worker status model from three states (Online/Draining/Paused) to two (Online/Paused), replace destructive `.orig` file rename with safe `.inprogress` output pattern, and unify crash/kill recovery into a single startup path. Redesign Activity page tiles with hybrid layout: status + pause on tiles, settings in a modal.

## Surface

- `WorkerService/Main.py` -- status handling, crash recovery
- `Features/FileReplacement/FileReplacementBusinessService.py` -- file replacement sequence
- `Templates/Activity.html` -- worker tiles, per-machine pause, settings modal
- `POST /api/TeamStatus/Workers/<name>/Status` -- status control endpoint

## Scope

- WorkerService/**
- Features/FileReplacement/**
- Features/TeamStatus/**
- Templates/Activity.html

## Success Criteria

### Worker Status

1. Workers have exactly two operator-settable states: Online and Paused. No other status values exist in the Workers table or code.
2. Paused means: set StopRequested on every capability (transcode, remux, VMAF, scan), finish all in-flight jobs, stop claiming new work. Worker process stays alive and keeps sending heartbeats.
3. Offline is a derived display state shown on the UI when a worker's heartbeat is stale (not a value in the Workers.Status column).
4. The Draining state, `_DrainAndStop` method, and drain waiter thread do not exist in the codebase.
5. Workers register with Status=Paused on first startup. The operator sets them to Online after verifying the deploy is good.

### File Replacement

6. FFmpeg writes output to `<filename>-mv.mp4.inprogress`. The original source file is never renamed or moved during processing.
7. After FFmpeg completes with return code 0, the `.inprogress` file is FFprobed to verify it is a valid media file before any further action.
8. On successful verification: `.inprogress` is renamed to drop the `.inprogress` suffix, MediaFiles.FilePath is updated to the new name, then the original source file is deleted. This is the only point the original is touched.
9. On FFmpeg failure or FFprobe verification failure: the `.inprogress` file is deleted. The original source file remains untouched.

### Crash Recovery

10. Crash and kill follow the same recovery path. There is no special DB state for a killed worker. When a worker starts, crash recovery runs and cleans up all orphaned state from any prior run.
11. Crash recovery rule 1: any `.inprogress` file on disk for this worker's active jobs is deleted (incomplete output).
12. Crash recovery rule 2: if a `-mv.mp4` file AND the original source both exist, delete the original and update MediaFiles.FilePath (replacement succeeded but cleanup didn't finish).
13. Crash recovery rule 3: orphaned ActiveJobs rows for this worker are deleted. TranscodeAttempts with no CompletedDate for this worker are marked failed with reason "worker crashed/restarted".

### UI

14. Activity page tiles show: worker name, machine group, status badge (Online/Paused/Offline), and a pause/resume button. No settings controls on the tile itself.
15. Each machine group header has a "Pause Machine" button that pauses all workers in that group in a single action, and a "Resume Machine" button to set them all Online.
16. Clicking a worker tile opens a modal with that worker's settings: capability toggles (transcode, remux, VMAF, scan), concurrency values per capability, and other per-worker configuration.
17. Capabilities (transcode/remux/VMAF/scan enabled, concurrency) are per-worker, not per-machine.

### Polling and Concurrency

18. Concurrency values have a floor of 1 and no upper ceiling.
19. Capability and concurrency changes take effect within one polling interval. The polling interval matches the documented default (15s) and is configurable via SystemSettings.

### Mount Validation

20. Before a worker transitions to Online (at startup or on resume), it validates that every storage mount it needs is present, accessible, AND contains data. A mount point that exists but is empty (local filesystem showing through instead of NFS) fails validation. The worker stays Paused and logs an ERROR naming the mount path, what it expected, and what it found. The Activity page shows the failure reason on the worker tile so the operator can fix the mount without reading logs.
21. A worker that fails mount validation does not claim any jobs. The mount check fires once before any job loop starts, not per-file after claiming -- so a broken-mount worker cannot bump FFprobeFailureCount on rows whose files exist and are simply unreachable through this worker.

## Status

COMPLETE 2026-05-16 -- all 21 criteria implemented. Mount-validation slice (20, 21) shipped 2026-05-15; status-model collapse, `.inprogress` rewrite, crash recovery, Activity tile redesign, and polling-interval verification shipped 2026-05-16.

### Progress

- [x] Design complete (this document)
- [x] Flow doc updated (step 7a + Failure Modes row, 2026-05-15)
- [x] Criteria 20, 21: cross-platform `_ValidateStorageMounts()` + `_ApplyMountValidationResult()` gate startup and Paused-to-Online transitions; `Workers.MountValidationError` column added; on failure worker stays Paused and claims zero jobs.
- [x] Surface MountValidationError on Activity tiles (criterion 20 second sentence): `/api/TeamStatus/Workers` now returns `MountValidationError`; Activity tile renders a red alert above the metadata block when set. Verified live: all 17 enabled workers return `MountValidationError=NULL` (no false positives on healthy fleet).
- [x] Criteria 1-5: collapsed Online/Draining/Paused to Online/Paused. Removed `_DrainAndStop` and the drain-waiter thread from `WorkerService/Main.py`; dropped `Draining` from TeamStatusController, Activity badge map, DatabaseManager docstrings. `RegisterWorker` now inserts new rows with `Status='Paused'` so operators must verify deploys before enabling.
- [x] Criteria 6-9: `.inprogress` output pattern. FFmpeg writes to `<basename>-mv.<ext>.inprogress`; FFprobe verify post-encode; FileReplacement renames to drop the suffix, updates MediaFiles, then deletes the original. `PrepareReplacement`/`RollbackReplacement` and the `.orig` backup dance are gone. 9 legacy `.orig` scripts deleted.
- [x] Criteria 10-13: crash recovery handles `.inprogress` cleanup (rule 1) and partial-replacement finalization (rule 2) via `_RecoverInProgressArtifacts` + `FileReplacementBusinessService.FinalizePartialReplacement`. TranscodeAttempts marked failed by recovery get `ErrorMessage='worker crashed/restarted'` (rule 3).
- [x] Criteria 14-17: Activity tiles redesigned. Workers grouped by machine prefix with per-machine Resume/Pause buttons in the group header. Tile shows name, version, heartbeat, status badge, and a single Online/Pause toggle button. Settings (capability toggles, per-capability concurrency, enable/disable) moved into a click-to-open Bootstrap modal.
- [x] Criterion 19: `_LoadCapabilityPollingInterval` reads `CapabilityPollingIntervalSec` from SystemSettings with a 15-second default; `_CapabilityPollingLoop` + `_ApplyConcurrencyChanges` apply both capability and concurrency edits to running services within one interval (no restart). SetWorkerConcurrency response message corrected to reflect no-restart semantics.

### Post-deploy verification

- [ ] **VMAF on `.inprogress` (criterion 6 integration)** -- VMAF now reads `TranscodedFilePath` from `TemporaryFilePaths.LocalOutputPath`, which after this PR ends in `.inprogress`. Verify a full transcode -> VMAF -> Replace cycle runs end-to-end and produces a valid VMAF score against the `.inprogress` file (FFmpeg/FFprobe should ignore the extension and read content). Pick one queued transcode after deploy, watch the `QualityTestResults` row land with `Success=True`, confirm `MediaFiles.FilePath` ends in `-mv.<ext>` (no `.inprogress` lingering).
- [ ] **Activity UI in a browser (criteria 14-17)** -- open `/Activity`, confirm workers are grouped by machine prefix, click a tile to open the settings modal, toggle a capability, change a concurrency value, verify the changes apply within one polling interval. The JS was not browser-verified during implementation.
