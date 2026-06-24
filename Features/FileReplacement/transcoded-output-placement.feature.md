# Feature: Transcoded Output Placement (side-by-side + `-mv` suffix)

**Slug:** transcoded-output-placement

## What It Does

Standardizes where MediaVortex writes transcoded output and what it names the final file after replacement. Two changes, one feature doc, one PR -- both touch the same FileReplacement output-path logic.

1. **Placement.** Every worker writes the staged transcoded file to the same directory as its source ("InPlace" / side-by-side), unless the per-worker `LocalStagingEnabled=TRUE` opt-in routes the encode through worker-local scratch (see `Features/TranscodeJob/local-staging.feature.md` for the override contract; copy-back ensures the canonical side-by-side write still happens before downstream consumers read). The `Workers.StagingDirectory` column is no longer read; the column is dropped in this feature's migration.
2. **Final naming.** After successful FileReplacement the output file is named `<basename>-mv.<ext>` (e.g. `Show.mkv` source -> `Show-mv.mp4` final). The `-mv` suffix is permanent and survives.

Together these fix three problems with one change:
- **Cross-worker hand-off.** Per-worker scratch dirs were container-local; any other worker that claimed the VMAF row got "file not found". Side-by-side eliminates the inconsistency by writing next to the source on the shared NFS mount.
- **Same-name collision.** The 2026-05-09 `BuildRemuxCommand` bug (memory/KNOWN-ISSUES.md:104) destroyed source files when input ext == output ext and OutputPath == InputPath. A permanent `-mv` suffix on the final filename means source and output are structurally distinct on disk regardless of any future code regression.
- **On-disk audit gap.** Today only `MediaFiles.TranscodedByMediaVortex` knows which files MediaVortex produced. With `-mv` the filesystem itself is self-describing -- an operator browsing the share in Explorer / `ls` can tell at a glance.

## Concern

Operator dogfood, 2026-05-10. Two adjacent topics surfaced in the same conversation: VMAF cross-system reachability (sparked by larry-worker-1 vs 2/3/4 staging-path drift) and a request for an on-disk visibility marker that also serves as defense-in-depth against extension-collision regressions of the 2026-05-09 bug. Both concerns touch the FileReplacement output-path computation; bundling them avoids two near-simultaneous PRs that fight over the same lines.

## Surface

- **Operator-visible.** Final filenames on the NAS shift from `<basename>.<ext>` to `<basename>-mv.<ext>` for new transcodes going forward. Pre-existing transcoded files are NOT renamed.
- **Configuration.** `Workers.StagingDirectory` becomes obsolete; the column is dropped.
- **No new HTTP endpoints, no new UI.** The Activity / SQLQueries pages display the path computed from the `MediaFiles` typed pair (`StorageRootId`, `RelativePath`, `FileName`), which now ends in `-mv.<ext>` for new transcodes.
- **External library impact (Plex / Jellyfin / Kodi).** Filename changes by design -- libraries that match by probed metadata (GUID / episode signature) re-link cleanly; libraries that match by exact filename refresh their mapping. No data loss; some watch-progress reset is possible per library.

## Success Criteria

### A. Side-by-side placement

1. Every worker writes the staged transcoded file to a path whose directory equals the source directory. Verifiable: on i9 and any larry worker, after a transcode `os.path.dirname(LocalOutputPath) == os.path.dirname(LocalSourcePath)` for the matching `TemporaryFilePaths` row.

2. No live code reads `Workers.StagingDirectory`. Verifiable: `grep -rn "StagingDirectory\|stagingdirectory" --include="*.py"` outside `archive_*/` and the migration script returns no matches.

3. The worker that produces a transcoded file is not required for VMAF: any worker with `QualityTestEnabled=TRUE` can claim the VMAF row and read the transcoded file. Verifiable: cross-worker integration test -- worker A produces, worker B (different hostname, different OS) consumes the VMAF row and completes successfully against the same source/transcoded pair, with the canonical paths translated to each worker's local mount.

### B. `-mv` final naming

4. After a successful FileReplacement the final on-disk filename is `<basename>-mv.<ext>` where `<ext>` is the transcode output container (`mp4` today). The source file is removed. Verifiable: post-replacement of `T:\Show\Show.mkv`, the source no longer exists and `T:\Show\Show-mv.mp4` exists.

5. The `-mv` suffix applies to all MediaVortex output flows -- transcode, remux, subtitle-fix. Verifiable: a remux of `Show.avi` produces `Show-mv.mp4`; a transcode of `Show.mkv` produces `Show-mv.mp4`; a subfix of `Show.mp4` produces `Show-mv.mp4`. Three asserts in the integration suite.

6. A double-suffix `<basename>-mv-mv.<ext>` never appears on disk. The transcode pipeline refuses to admit a queue row whose source filename already ends in `-mv.<ext>`. Verifiable: queue a candidate whose `FileName` ends in `-mv.mp4`, run populate; the row is rejected with `Reason='AlreadyMediaVortexTranscoded'`. Audit query against MediaFiles also returns 0 rows matching `FileName LIKE '%-mv-mv.%'` on a healthy library.

7. The path stored on a newly-transcoded MediaFile row ends in `-mv.<ext>`. Path is the typed pair `(StorageRootId, RelativePath)` plus the `FileName` column (legacy `FilePath` column was migrated out per `BUG-0052` / Core.Path). Verifiable: `SELECT COUNT(*) FROM MediaFiles WHERE TranscodedByMediaVortex=TRUE AND FileName NOT LIKE '%-mv.%'` returns 0 for rows produced after the cutover; existing pre-cutover rows are out of scope (see C8).

### C. No backfill, no breakage

8. Pre-existing transcoded files keep their current names. No bulk rename. Verifiable: pre-cutover rows are identified by the absence of the `-mv` suffix on `FileName` together with `TranscodedByMediaVortex=TRUE`; the cleanup script does not rename them. The `-mv` convention applies only to new replacements.

10. The collision check at FileReplacement time refuses to overwrite an existing target. Verifiable: pre-place a `Show-mv.mp4` in the source directory, then trigger replacement for a transcode that would produce the same path. `TranscodedOutputPlacement.Execute` refuses BEFORE any rename happens (LocalExists check on TargetPath), returns `Success=False` with `ErrorMessage='Refusing to overwrite existing file at target: ...'`. No rollback is required because the rename has not occurred; the staged `.inprogress` file remains and the source is bit-identical to its pre-call state.

### D. Migration

11. SQL migration drops `Workers.StagingDirectory`. Verifiable: `\d Workers` no longer shows the column.

12. The migration is idempotent. Verifiable: run twice; the second run is a no-op (no error, no row count change).

### E. Rollback on MediaFiles update failure (BUG-0067)

13. When `_UpdateMediaFilesAfterReplacement` returns `Success=False` after the `.inprogress` -> `<basename>-mv.<ext>` rename has landed, `Execute` rolls the rename back and returns `Success=False` carrying the actual `_UpdateMediaFilesAfterReplacement` error. No orphan `-mv.<ext>` is left on disk; the source survives bit-identical. The `FinalizePartialReplacement` crash-recovery path returns `Success=False` with the real error rather than masking the failure as success. Verifiable: `Tests/Contract/TestFileReplacementRollbackOnUpdateFailure.py` mocks `_UpdateMediaFilesAfterReplacement` to return `Success=False` for both same-slot and non-same-slot inputs; the test asserts `Execute['Success']==False`, the target `-mv.<ext>` is absent, and the source file is intact at its pre-call path.

## Status

**ACTIVE.** Side-by-side placement + `-mv` naming + `Workers.StagingDirectory` migration shipped 2026-05-10 / 2026-05-21. SOLID decomposition shipped 2026-06-02 via `filereplacement-decompose` -- the rename + MediaFiles refresh + source delete extracted to `TranscodedOutputPlacement.Execute`; `ComplianceGate` extracted to its own class; orchestration is `FileReplacementBusinessService.ProcessFileReplacement`. C13 (rollback on `_UpdateMediaFilesAfterReplacement` failure) + S4 (rollback seam) shipped 2026-06-23 via `/t BUG-0067`.

### Progress

- [x] 1. Surfaced two related concerns (cross-worker scratch reachability, on-disk audit gap) on 2026-05-10
- [x] 2. Confirmed via DB query that i9 already InPlace (`StagingDirectory=NULL`) and three of four larry workers use the shared NFS staging path; `larry-worker-1` is the outlier
- [x] 3. Drafted this feature doc with 12 success criteria
- [x] 4. Operator approval of criteria (granted in same conversation; phase split agreed)
- [x] 5. **Phase 1.1.** Pragmatic point-fix: `UPDATE Workers SET StagingDirectory='/mnt/media_tv/MediaVortex/Staging' WHERE WorkerName='larry-worker-1'` -- closes criterion 3's blast radius for tonight's smoke without the full refactor. (Criterion 3, partial.)
- [x] 6. **Phase 1.2.** Compute final `TargetPath` in the FileReplacement rename step as `<originalbasename>-mv<ext>`, derived from the original filename rather than the staged filename's various suffixes (`_remuxed.mp4`, `_subfix.mp4`, resolution suffixes, etc.). (Criteria 4, 5.)
- [x] 7. **Phase 1.3.** Add the `-mv` admission guard to queue populate paths (criterion 6).
- [x] 7b. **Phase 1.3b** (added 2026-05-10): extend `-mv` suffix to the STAGED transcode output filename, not just the final FileReplacement target. Closes the same-name collision class structurally -- source `Show WEBDL-1080p.mp4` -> staged `Show WEBDL-1080p-mv.mp4`, different files by construction. `CommandBuilder.GenerateOutputFileName` now appends `-mv` to every output filename it generates. The SameSlot branch in `TranscodedOutputPlacement.Execute` handles the case where staged path equals target path. Defense-in-depth at the write step, not just the rename step.
- [x] 9. **Phase 1.5.** Update `transcode.flow.md` Stage 8 with the new naming.
- [x] 10. **Phase 1.6.** Smoke script `Scripts/Smoke/RunPostDispositionPipelineTest.py` to verify attempt 4394 end-to-end (lower threshold + manual disposition + FileReplacement + restore threshold).
- [x] 11. **Phase 2 (2026-05-21).** SQL migration `Scripts/SQLScripts/drop_local_staging_2026_05_21.py` drops `Workers.StagingDirectory` and deletes the `TranscodeFileMode` SystemSettings row in a single transaction. Idempotent: re-running the dry-run reports zero changes. Code refactor lands in the same branch: `Core/WorkerContext`, `Repositories/DatabaseManager` RegisterWorker / GetWorkerConfig, `WorkerService/Main.py` + `WebService/Main.py` init, `ProcessTranscodeQueueService` (LocalStaging branches removed from ProcessJob / ProcessRemuxJob / ProcessSubtitleFixJob / _ProcessSingleVariant; `GetTranscodeFileMode` / `GetTranscodeOutputMode` / `GetLocalStagingDir` / `CopyBackFromLocalStaging` / `CleanupLocalStagingFiles` deleted). `Features/TranscodeJob/TranscodingFileManagerService.py` and `archive_TranscodeService/` + `archive_QualityTestService/` removed outright.
- [x] 12. **Phase 2.** Cross-worker integration smoke test: in-place output places `.inprogress` next to source on the shared NFS mount, so any worker can claim the VMAF row. No further per-worker reachability concern.

## Scope

```
Features/TranscodeJob/ProcessTranscodeQueueService.py
Features/FileReplacement/FileReplacementBusinessService.py
Features/FileScanning/FileScanningBusinessService.py
Features/TranscodeQueue/QueueManagementBusinessService.py
Models/CommandBuilder.py
Scripts/SQLScripts/drop_local_staging_2026_05_21.py
transcode.flow.md
```

## Files

| File | Role |
|---|---|
| `Features/TranscodeJob/ProcessTranscodeQueueService.py` | Compute staging path side-by-side; stop reading `Workers.StagingDirectory` |
| `Features/FileReplacement/TranscodedOutputPlacement.py` | `Execute` owns the `.inprogress` -> `<basename>-mv.<ext>` rename, the MediaFiles re-probe, and the source delete. `FinalizePartialReplacement` is the crash-recovery completion path. Both fail loud + roll back when `_UpdateMediaFilesAfterReplacement` fails (C13). |
| `Features/FileReplacement/FileReplacementBusinessService.py` | Orchestration only -- `ProcessFileReplacement` validates disposition + dispatches to `TranscodedOutputPlacement.Execute`. |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | Refuse to admit queue rows whose source ends in `-mv.<ext>` |
| `Models/CommandBuilder.py` | `BuildTranscodeCommand` / `BuildRemuxCommand` / `BuildSubtitleFixCommand` -- output paths land side-by-side; staging suffix unchanged (`_transcoded.mp4` / `_remuxed.mp4` / `_subfix.mp4` during the encode) |
| `Scripts/SQLScripts/drop_local_staging_2026_05_21.py` | One-shot, idempotent column drop |
| `transcode.flow.md` | Stage 6 inputs no longer reference `StagingDirectory`; Stage 8 ACTION + Phase 7 lifecycle describe the current rename / re-probe / source-delete / rollback shape. |
| `memory/KNOWN-ISSUES.md` | Cross-worker hand-off (Risk 5 in 2026-05-10 sight pass) closed by criterion 3 |

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `FileReplacementBusinessService.ProcessFileReplacement -> TranscodedOutputPlacement.Execute` | Orchestrator dispatches after disposition is validated + archive snapshot taken | `(OriginalFilePath, TranscodedFilePath, NetworkOriginalPath, FFmpegCommand, SourceMediaFileId, Mode)` all canonical | `Execute` returns `{Success, StepsCompleted, ErrorMessage, CanonicalOriginalPath, CanonicalNewPath, ComplianceGateRefused?, CascadeReason?}` | Canary attempt 27614 (Impractical Jokers S07E11) 2026-06-03: dot-worker-1 executed end-to-end, source `.mkv` (756.0 MB) -> `-mv.mp4` (205.4 MB, 72.8% reduction); MediaFiles re-probed to `Codec='av1'`; TFP row deleted by dispositioner chokepoint. |
| S2 | `TranscodedOutputPlacement.Execute -> ComplianceGate.Evaluate` | Execute calls the gate before the rename step | `(LocalStagedPath, SourceMediaFileId, FFmpegCommand)` | `{Compliant, RefusalReason}` per `compliance-gated-rename.feature.md` | `Tests/Contract/TestComplianceGate.py` (planned) |
| S3 | `TranscodedOutputPlacement.FinalizePartialReplacement <- CrashRecoveryService` | CrashRecoveryService is the sole external caller (post-2026-06-02 extraction) | `(OriginalLocalPath, FinalLocalPath, CanonicalOriginalPath)` | `Execute`-compatible result dict; idempotent if either source file is missing | CrashRecoveryService import grep: 1 hit at the FinalizePartialReplacement call site |
| S4 | `TranscodedOutputPlacement.Execute -> filesystem rollback on update failure` | `Execute` after `_UpdateMediaFilesAfterReplacement` returns `Success=False` | Non-SameSlot: `os.remove(TargetPath)` reversing the `.inprogress` -> `-mv.<ext>` rename. SameSlot: `os.rename(TargetPath, LocalStagedPath)` + `os.rename(BackupPath, LocalOriginalPath)` reversing the rename dance. | Caller receives `{Success: False, ErrorMessage: <real update error>}`; filesystem is bit-identical to pre-call state minus the now-deleted `.inprogress` staging output. | `Tests/Contract/TestFileReplacementRollbackOnUpdateFailure.py` -- both branches; criterion C13. |

## Deviation from conventions

None.
