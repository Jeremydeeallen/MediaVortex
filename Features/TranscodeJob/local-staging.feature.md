# Local Staging

**Slug:** local-staging

## What It Does

Worker-local opt-in staging path for transcode encodes. When `Workers.LocalStagingEnabled=TRUE` AND `Workers.LocalScratchDir` is set AND source `SizeMB >= LocalStagingConfig.MinSizeMB` (default 500), the worker bulk-copies the source from the shared mount to local scratch before ffmpeg runs, encodes against the local path, and either (a) ships the `.inprogress` back to canonical for cross-worker VMAF (Mode B, default) or (b) runs VMAF locally first and decides Replace / Requeue inline (Mode A, when `LocalVmafFirst=TRUE`). Default-OFF per worker. Backplane-NFS workers (Linux containers) keep the in-place encode unchanged.

Motivation: the Microsoft SMB client on Windows drops long-duration file handles under GPU-paced reads (`memory/feedback_ms_nfs_client_unreliable.md`). Bulk sequential copy uses an IO pattern SMB handles reliably; the encode then runs against local storage.

## Workflows

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | Enable staging on a worker | `/Activity` worker modal "Local Staging" section | `POST /api/TeamStatus/Workers/<name>/LocalStaging` | `Features/TeamStatus/TeamStatusController.UpdateWorkerLocalStaging` |
| W2 | Adjust staging size floor | `/settings` "Local staging" collapsible card | `PUT /api/SystemSettings/LocalStagingConfig` | `Features/SystemSettings/SystemSettingsController.UpdateLocalStagingConfig` |
| W3 | Observe staging state | `/Activity` worker tile compact line + modal section | n/a (read-only render) | `Templates/Activity.html` worker-tile + worker-modal blocks |

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `ProcessTranscodeQueueService.SetupFilePreparation` -> `LocalStagingService.ShouldStage` | `ProcessTranscodeQueueService` | `(WorkerName: str, SourceSizeMB: float) -> bool` | Three-way AND of `Workers.LocalStagingEnabled`, non-empty `Workers.LocalScratchDir`, source `SizeMB >= LocalStagingConfig.MinSizeMB`; fresh DB read per call (R3 + db-is-authority) | `Tests/Contract/TestLocalStaging.py` 2x2x2 truth table + mid-test UPDATE |
| S2 | `LocalStagingService.StageSource` -> ffmpeg `-i` | `LocalStagingService` | `<LocalScratchDir>/<MediaFileId>/<basename>` on disk; size-verified against canonical | `CommandBuilder` emits `-i <local_path>` when staging active | TemporaryFilePaths row has `LocalSourcePath` populated; ffmpeg command's `-i` arg matches `LocalScratchDir/<MediaFileId>/<basename>` |
| S3 | Encode finalize -> Mode A VMAF | `ProcessTranscodeQueueService.ProcessJob` post-`_VerifyInProgressFile` | `LocalStagingService.IsLocalVmafFirst(WorkerName) -> bool`; if TRUE, `QualityTestingBusinessService.RunLocalVmafForAttempt(AttemptId, LocalSrcPath, LocalOutPath) -> {Success, VMAFScore}` | Score >= `PostTranscodeGateConfig.VmafAutoReplaceMinThreshold` -> fall through to S4 (Mode B copy-back); score < min -> set `SkipModeBCopyBack=True`, cleanup local, audit-only finalize | Synthetic verification 2026-06-09: VMAF=50.0966 against MinThreshold=84.0 -> Disposition=Requeue/VmafBelowMin via `PostTranscodeDispositionService.DecidePostTranscodeDisposition` |
| S4 | `_CopyBackStagedOutput` -> canonical `.inprogress` | `ProcessTranscodeQueueService._CopyBackStagedOutput` | local `.inprogress` -> `Path.Resolve` of canonical `(OutputStorageRootId, OutputRelativePath)`; size-verified | Downstream `FileReplacement` reads canonical paths unchanged; cross-worker VMAF (Mode B) reaches the canonical `.inprogress` from any host | live since 2026-06-08 on Mune Guardian (I9-2024) |
| S5 | Attempt finalize -> local cleanup | `ProcessTranscodeQueueService._CleanupLocalScratchForAttempt` | `LocalStagingService.CleanupJobScratchDir(WorkerName, MediaFileId)` -> `shutil.rmtree(<LocalScratchDir>/<MediaFileId>/, ignore_errors=True)` | Per-job scratch subdir gone after success / failure / Mode A fail | idempotent re-run is no-op |
| S6 | Crash recovery -> orphan sweep | `CrashRecoveryService._SweepLocalStagingOrphans` (TranscodeService startup) | Walks numeric subdirs of this worker's `LocalScratchDir`; for each, queries `TemporaryFilePaths` JOIN `TranscodeAttempts` WHERE `MediaFileId AND WorkerName=self AND Success IS NULL`; if no row, deletes the subdir | Numeric subdirs without an in-flight attempt for this worker are gone; non-numeric subdirs (HandBrakeCLI, Logs) preserved; cross-host safe (never reaches across hosts) | Synthetic verification 2026-06-09: 8 orphans swept (1 synthetic + 7 real prior-session) on I9-2024 |

## Success Criteria

C1. `Workers` gains three nullable columns via idempotent migration `Scripts/SQLScripts/AddLocalStagingColumns.py`: `LocalScratchDir TEXT NULL`, `LocalStagingEnabled BOOLEAN NOT NULL DEFAULT FALSE`, `LocalVmafFirst BOOLEAN NOT NULL DEFAULT FALSE`. `TemporaryFilePaths` gains `LocalSourcePath TEXT NULL` and `LocalOutputPath TEXT NULL`. `LocalStagingConfig` is a dedicated single-row table: `Id INTEGER PRIMARY KEY DEFAULT 1, MinSizeMB INTEGER NOT NULL DEFAULT 500, LastUpdated TIMESTAMP DEFAULT NOW(), CHECK (Id = 1)`. All operations use IF NOT EXISTS / ON CONFLICT DO NOTHING.

C2. Post-migration default state: every existing `Workers` row has `LocalStagingEnabled=FALSE`. No worker's behavior changes until operator explicitly enables.

C3. `Features/TranscodeJob/LocalStagingService.py` is single-responsibility: ShouldStage decision, source copy with verification, local-path resolution, cleanup on finalize. Composes `WorkersRepository` + `DatabaseService`; no inheritance; no `self._cached_*` fields; every staging-decision call reads Worker config fresh from DB.

C4. `ProcessTranscodeQueueService.SetupFilePreparation` delegates the staging decision to `LocalStagingService.ShouldStage` and the copy itself to `LocalStagingService.StageSource`. Setup code contains no inline path-copy logic.

C5. `ShouldStage` returns TRUE iff all three: `Workers.LocalStagingEnabled=TRUE`, `Workers.LocalScratchDir IS NOT NULL AND <> ''`, source `SizeMB >= LocalStagingConfig.MinSizeMB`. Size threshold read via `LocalStagingConfigRepository.Get()` per call.

C6. Backplane / NFS workers untouched by default. Docker-on-Linux workers (larry) and bare-metal Linux workers (wakko, dot) keep `LocalStagingEnabled=FALSE` post-migration. Job-claim and encode paths byte-identical to today.

C7. When staging is active, `CommandBuilder` emits ffmpeg `-i <local_source>` and `<local_output>.inprogress` in place of the canonical paths. `TemporaryFilePaths.LocalSourcePath` / `LocalOutputPath` columns populated.

C8. One-knob-per-attempt invariant. Staging changes ONLY the source/output paths the ffmpeg command sees. Codec, bitrate, scale, audio, loudnorm, pix_fmt arguments are byte-identical to the non-staged version of the same profile.

C9. **Mode A (local-only VMAF) -- `Workers.LocalVmafFirst=TRUE AND Workers.QualityTestEnabled=TRUE`:** after encode, the same worker runs VMAF against `LocalSourcePath` vs `LocalOutputPath` BEFORE shipping `.inprogress` back to canonical. Score >= `PostTranscodeGateConfig.VmafAutoReplaceMinThreshold` -> Mode B copy-back path runs, `FileReplacement` proceeds; score < min -> no canonical copy-back, no `FileReplacement`, attempt audited with VMAF populated, local scratch deleted.

C10. **Mode B (cross-worker VMAF hand-off) -- `Workers.LocalVmafFirst=FALSE` OR `Workers.QualityTestEnabled=FALSE`:** after encode, worker copies local `.inprogress` back to canonical side-by-side BEFORE enqueueing the `QualityTestingQueue` row. Any VMAF-capable worker (including a different host) can claim and run VMAF against canonical paths.

C11. Local scratch files deleted on every attempt-finalize code path: encode success (after VMAF disposition or copy-back), encode failure, crash recovery, stuck-job cleanup. Idempotent.

C12. Crash-recovery (`CrashRecoveryService.RecoverServiceJobs`) extended to delete orphaned files in `Workers.LocalScratchDir` whose `TemporaryFilePaths` row has been finalized (attempt complete). Only the calling worker's scratch dir; never reaches across hosts.

C13. `/Activity` worker modal "Local Staging" section: scratch dir input, "Enable staging" toggle, "Local VMAF first" toggle (disabled in UI when `QualityTestEnabled=FALSE`). Save POSTs to `POST /api/TeamStatus/Workers/<name>/LocalStaging` with `{LocalScratchDir, LocalStagingEnabled, LocalVmafFirst}`; validates non-empty path when Enabled=TRUE; standard `{Success, Message, Data}` envelope.

C14. Worker-tile compact line below profiles: `Staging: <ScratchDir or "off">` when `LocalStagingEnabled`; truncates to 80 chars with tooltip showing full path + toggles.

C15. `transcode.flow.md` Stage 5 (`ST6`) "File staging" subsection documents the conditional staging branch + Mode A vs Mode B. `## Seams` table S2 row (`ST6 -> ST7`) documents canonical / Mode B / Mode A producer variants.

C16. `/settings` "Local staging" collapsible card patterned on Queue admission: one number input bound to `LocalStagingConfig.MinSizeMB`, one Save button, lazy-load on `shown.bs.collapse`, server-side `GET` + `PUT /api/SystemSettings/LocalStagingConfig` delegating to `LocalStagingConfigRepository`. Mid-flight UPDATE honored by next `ShouldStage` call (db-is-authority).

C17. `Features/TranscodeJob/LocalStagingConfigRepository.py` is the sole emitter of SQL reads/writes against `LocalStagingConfig`. `Get() -> dict` + `Update(MinSizeMB=None) -> bool`; validates `MinSizeMB > 0`; stamps `LastUpdated = NOW()`. Composes `DatabaseService`; no inheritance; no caching.

## Status

COMPLETE. Verification evidence per criterion lives in the closing directive (`.claude/directives/closed/2026-06-09-local-staging.md`).

### Files

| # | File | Role |
|---|---|---|
| 1 | `Scripts/SQLScripts/AddLocalStagingColumns.py` | Schema migration (Workers + TemporaryFilePaths + LocalStagingConfig) -- C1 |
| 2 | `Features/TranscodeJob/LocalStagingConfigRepository.py` | Sole SQL emitter against `LocalStagingConfig` -- C17 |
| 3 | `Features/TranscodeJob/LocalStagingService.py` | Staging decision + copy + cleanup + Mode A predicate -- C3, C5, C7, C11 |
| 4 | `Features/TranscodeJob/ProcessTranscodeQueueService.py` | Setup delegation + Mode A dispatch + Mode B copy-back + per-attempt cleanup -- C4, C7, C8, C9, C10, C11 |
| 5 | `Models/CommandBuilder.py` | Local path routing for `-i` / output `.inprogress` -- C7, C8 |
| 6 | `Features/QualityTesting/QualityTestingBusinessService.py` | `RunLocalVmafForAttempt` Mode A pre-flight VMAF -- C9 |
| 7 | `Features/Workers/WorkersRepository.py` | `UpdateWorkerLocalStaging` + `GetWorkerLocalStagingConfig` -- C13 |
| 8 | `Features/TeamStatus/TeamStatusController.py` | `POST /api/TeamStatus/Workers/<name>/LocalStaging` + GET payload extension -- C13 |
| 9 | `Features/SystemSettings/SystemSettingsController.py` | `GET` + `PUT /api/SystemSettings/LocalStagingConfig` -- C16 |
| 10 | `Templates/Activity.html` | Worker modal "Local Staging" section + tile compact line -- C13, C14 |
| 11 | `Templates/Settings.html` | "Local staging" collapsible card -- C16 |
| 12 | `Features/ServiceControl/CrashRecoveryService.py` | `_SweepLocalStagingOrphans` orphan sweep -- C12 |
| 13 | `transcode.flow.md` | Stage 5 staging subsection + S2 seam -- C15 |
| 14 | `Tests/Contract/TestLocalStaging.py` | Contract tests -- C3, C5, C11 (16/16 pass) |
