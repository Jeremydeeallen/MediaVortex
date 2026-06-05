# File Replacement

**Slug:** filereplacement

## What It Does

Replaces original media files with verified transcoded output. Archives original metadata to MediaFilesArchive, swaps the file on disk, re-probes the new file via MediaProbe, and updates all MediaFiles columns.

## Success Criteria

C1. Original file metadata is archived to MediaFilesArchive before any destructive operation.
C2. Transcoded file replaces the original at the same path on disk.
C3. After replacement, the new file is re-probed and all MediaFiles columns are updated with fresh metadata.
C4. TranscodedByMediaVortex is set to true on successfully replaced files.
C5. If replacement fails (disk error, size mismatch), the original file is preserved and the error is logged.
C6. [BUG] FileReplacement depends on MediaProbe for re-probing after replacement, but there is no explicit interface contract between them. The post-replace flow (archive -> replace -> re-probe -> update MediaFiles) crosses FileReplacement and MediaProbe boundaries with no documented API or failure mode agreement.
C7. FileReplacement works on any machine (Windows or Linux). _ProcessCompleteFileReplacement() accepts PathTranslation and translates canonical DB paths to local mount paths before all filesystem operations. InPlace output mode skips shutil.move. No hardcoded Windows paths in the cleanup flow.
C8. **Canonical-path math uses `ntpath`, not `os.path`, so it works on Linux workers.** Canonical paths in the DB are always Windows-flavored (`T:\...`); using `os.path.dirname` on a Linux worker silently returned the empty string and produced a filename-only "new path" that the post-replacement re-probe couldn't find. After 2026-05-08 fix, `_ProcessCompleteFileReplacement` uses `ntpath.dirname` / `ntpath.join` so the canonical new-path is always reconstructed correctly regardless of host OS.
C9. **Re-probe failure surfaces in Logs with full context, not just "Failed to update MediaFiles table."** Previously the wrapper stripped the underlying FFprobe error; now `_UpdateMediaFilesAfterReplacement` propagates the original ExceptionMessage with the absolute path that FFprobe could not read.
C10. [BUG - FIXED 2026-05-13] **Remux files were discarded as "NoSavings" before reaching FileReplacement.** Root cause was in `PostTranscodeDispositionService._DecideFromInputs` -- the NoSavings gate (Row 2) fired before the QualityTestNotRequired bypass (Row 3). Fix: swapped the two rows. Remediation: `Scripts/SQLScripts/RemediateDiscardedRemuxFiles.py`. ~301 files still need remediation (113 Windows with stale `.orig`, 188 Linux pending redeploy).
C11. [BUG-0009] **FileReplacement does not silently fail in steady-state.** When `_ProcessCompleteFileReplacement` returns `Success=false` for an attempt whose transcode succeeded, the specific failure branch (size-guard, missing-output-file, archive failure, rename collision, etc.) must be identifiable from a log line emitted by `FileReplacementBusinessService.ProcessFileReplacement` -- not just from the downstream `OrphanCleanup` TFP-orphan warning. Recurring failures (1-3 per orphan sweep) indicate a real condition that should be diagnosed and resolved, not absorbed by the safety net.
C12. [BUG-0010 MET 2026-06-02] **TFP cleanup is owned by `PostTranscodeDispositionService.CleanupTemporaryFilePaths`** (the chokepoint named in `post-transcode-pipeline.C15`). FR's `ProcessFileReplacement` success branch delegates to it; non-Pending dispositions (`Discard`/`NoReplace`/`Requeue`) reach the same chokepoint via `_CommitDisposition`. The old FR-local `_CleanupTemporaryFilePaths` is gone. Verifiable: `grep -rn "_CleanupTemporaryFilePaths" --include="*.py" Features/FileReplacement/` returns zero; `SELECT COUNT(*) FROM TemporaryFilePaths tfp JOIN TranscodeAttempts ta ON ta.Id = tfp.TranscodeAttemptId WHERE ta.Success IS NOT NULL` returns 0 in steady state.
C14. [BUG-0021] **`_UpdateMediaFilesAfterReplacement` must persist every column it assigns, including `Codec`, `AudioCodec`, and `AudioComplete`.** Today these three columns are assigned on the model after the post-replacement re-probe but silently dropped by `Repositories/DatabaseManager.SaveMediaFile` because they are not in the UPDATE column list. BUG-0017 (resolved 2026-05-25) added 6 sibling columns (FileSize, LastModifiedDate, ResolutionCategory, IsInterlaced, AudioLanguages, HasExplicitEnglishAudio) but Codec/AudioCodec/AudioComplete remain uncovered. Observable failure: after a successful re-encode (HEVC -> AV1 verified on disk), `SELECT Codec, AudioCodec, AudioComplete FROM MediaFiles WHERE Id=<id>` returns the pre-replacement values. Operator-visible compliance tallies (Library Compliance counts, AudioFix routing) misreport this file class until the next manual probe. Verifiable: after any post-replacement re-probe writes a new value for these three columns, `SELECT Codec, AudioCodec, AudioComplete FROM MediaFiles WHERE Id=<id>` round-trips that value. Immediate patch: add the three columns to the UPDATE list (matching the BUG-0017 pattern). Architectural fix: `mediafile-persistence-no-drift` feature.

C13. [BUG-0020] **`_ProcessCompleteFileReplacement` must consult the cascade compliance predicate before the `.inprogress` -> final-name rename.** Today the rename fires when (a) the staged file exists and (b) its name ends in `.inprogress` (`FileReplacementBusinessService.py:441-465`). FFprobe sanity is verified upstream by the worker. Neither check answers "would this output still be picked up by the cascade?" -- so the rename can land `-mv.mp4` on a file whose audio is still wrong, savings still marginal, container still non-acceptable, etc. After the fix, the function probes the staged file, synthesizes a candidate `MediaFile`-shaped row (carrying forward source-row fields the probe cannot derive: `HasExplicitEnglishAudio`, `SourceIntegratedLufs`/`SourceLoudnessRangeLU`/`SourceTruePeakDbtp`/`SourceIntegratedThresholdLufs`, `AudioComplete`), calls `QueueManagementBusinessService._EvaluateCompliance`, and only renames when `(IsCompliant, RecommendedMode) == (True, None)`. Non-compliant outputs return Success=False with `ErrorMessage='ComplianceGateFailed: <specific cascade reason>'`, and the owning worker (per worker-lifecycle criterion 22) deletes the `.inprogress`. Verifiable: queue any file whose source has unnormalized audio AND a profile that does not include loudnorm in the emitted command -- the encode completes, the rename refuses, no `-mv.mp4` lands on disk, the `TranscodeAttempt` records `Disposition='NoReplace'`, `DispositionReason='ComplianceGateFailed'`.

## Seams

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| `TemporaryFilePaths` → `ProcessFileReplacement` | `ProcessTranscodeQueueService.PrivateCreateTemporaryFilePathRecord` | `TemporaryFilePaths.(TranscodeAttemptId BIGINT, SourceStorageRootId BIGINT NOT NULL, SourceRelativePath TEXT NOT NULL, OutputStorageRootId BIGINT NOT NULL, OutputRelativePath TEXT NOT NULL)` -- both source AND output typed pair MUST be present (legacy-row fallback removed) | `FileReplacementBusinessService.ProcessFileReplacement(AttemptId)` reads row, constructs `Path` instances for source and output, calls `Path.Resolve(Worker)` for worker-local strings before filesystem ops | `SELECT COUNT(*) FROM TemporaryFilePaths WHERE TranscodeAttemptId = <id>` → 1 row before replacement; 0 after disposition chokepoint cleanup |
| `TranscodeAttempts.VMAF` → disposition | `QualityTestingBusinessService` | `TranscodeAttempts.vmaf DOUBLE PRECISION NULL` (NULL=not tested); `ForceDisposition TEXT NULL` (operator override bypasses VMAF) | `PostTranscodeDispositionService._DecideFromInputs` gates Replace on `VMAF >= threshold` (default 80.0) unless `ForceDisposition` is set | `SELECT COUNT(*) FROM TranscodeAttempts WHERE QualityTestCompleted=TRUE AND VMAF IS NULL` → 0 |
| MediaProbe re-probe after replacement | `_ProcessCompleteFileReplacement` calls `_UpdateMediaFilesAfterReplacement(new_path)` | Local path of the newly-renamed `-mv.mp4` file | `MediaProbeBusinessService.ProbeFile` refreshes all MediaFiles metadata columns | Post-replacement `SELECT Codec, Resolution, SizeMB FROM MediaFiles WHERE Id=<id>` reflects the new file |
| `MediaFilesArchive` snapshot | `_ArchiveOriginalFileDetails` writes before any destructive op | All `MediaFiles` column values at time of replacement + `ArchiveDate` | Operator audit queries; no live code reads from this table | `SELECT COUNT(*) FROM MediaFilesArchive WHERE MediaFileId=<id>` → 1 per replacement |
| Jellyfin notify (fire-and-forget) | `_NotifyJellyfinOfReplacement` -> `JellyfinNotifyService.NotifyJellyfin` | HTTP POST to Jellyfin `/Library/Media/Updated` with parent folder path; 204 = queued (~60s coalescing window) | Jellyfin library refresh; failure is non-fatal (WARNING + continue) | See `jellyfin-push-notify.feature.md`; no automated verification |
| Path translation (canonical ↔ local) | `PathTranslation.ToLocalPath()` converts DB canonical `T:\...` to worker-local mount path | Canonical DB path → worker-native path string; `ntpath.dirname` / `ntpath.join` on canonical paths regardless of host OS | All filesystem ops (`os.remove`, `os.rename`, `shutil.move`) use local-translated paths | Post-replacement file exists at local-translated path; canonical path in `MediaFiles.FilePath` matches new name |

## Status

ACTIVE -- criteria 1-14 MET. FileReplacement decomposed by SRP via `filereplacement-decompose` directive 2026-06-02: ComplianceGate + TranscodedOutputPlacement extracted to their own files with own feature docs; FileReplacementBusinessService shrank to orchestration + read-only queries (1183 -> 396 lines).

## Scope

```
Features/FileReplacement/**
```

## Files

| File | Role |
|------|------|
| Features/FileReplacement/FileReplacementBusinessService.py | Orchestration (ProcessFileReplacement) + read-only queries (GetFailedFileReplacements, GetFileReplacementStatus) + archival + Jellyfin notify |
| Features/FileReplacement/ComplianceGate.py | Pre-rename cascade gate (see compliance-gated-rename.feature.md) |
| Features/FileReplacement/TranscodedOutputPlacement.py | .inprogress rename, MediaFiles refresh, original delete (see transcoded-output-placement.feature.md) |
| Features/FileReplacement/FileReplacementRepository.py | MediaFilesArchive and MediaFiles update queries |