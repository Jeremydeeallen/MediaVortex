# Post-Transcode Pipeline Consistency

## What It Does

Makes the post-transcode pipeline (delete original, update DB) work on any worker -- Windows or Linux -- regardless of whether VMAF quality testing is enabled. With InPlace output the transcoded file is already next to the original. The only remaining work after transcode is: delete the original, update MediaFiles, mark TranscodedByMediaVortex=True.

## Concern

Both (code fix + deploy-anywhere infrastructure)

## Success Criteria

### Bridge decision (ShouldQualityTestService)
1. When QualityTestRequired=False on the TranscodeAttempt, ShouldQualityTestService skips the quality test queue entirely and proceeds directly to file cleanup. No QualityTestQueue row is created.
2. When QualityTestRequired=True, the existing VMAF queue flow is unchanged -- quality test is queued, WorkerService (with QualityTestEnabled) processes it, auto-replace triggers if VMAF is in range.
3. When quality testing capability is not running and QualityTestRequired=True, the quality test is still queued. The bridge does not conflate "capability not running" with "testing disabled."

### File cleanup (FileReplacementBusinessService)
4. After a successful transcode with QualityTestEnabled=OFF, the full DB state chain completes in order:
   a. MediaFilesArchive -- INSERT snapshot of original file metadata (resolution, codec, size, audio) before any destructive operation.
   b. Disk -- delete original file (or rename to .old if KeepSource=True).
   c. MediaFiles -- UPDATE: FilePath to transcoded file path, re-probe all metadata columns (Resolution, Codec, SizeMB, AudioLanguages, etc.), set TranscodedByMediaVortex=True, set LastScannedDate=now.
   d. TranscodeAttempts -- UPDATE: FileReplaced=True, FileReplacedDate=now.
   e. TemporaryFilePaths -- DELETE the row for this TranscodeAttemptId (cleanup after all paths are consumed).
5. File cleanup uses path translation (PathTranslationService) for all filesystem operations. Canonical DB paths (T:\...) are translated to local mount paths before any os.path.exists, os.remove, or shutil call.
6. For InPlace output mode, no shutil.move occurs -- the transcoded file is already in the final directory. The only filesystem operation is deleting the original.
7. No hardcoded Windows paths (C:\MediaVortex\Source\, C:\MediaVortex\Output\) appear in the cleanup flow. Temp source cleanup is skipped for InPlace mode since no local copy was made.

### Failure cleanup (HandleJobFailure)
8. When a transcode fails, the partial output file (if any) is deleted from disk using path translation. No orphaned partial files accumulate in media directories.
9. When a transcode fails, the TemporaryFilePaths row for that TranscodeAttemptId is deleted. No orphaned path records accumulate for attempts that will never reach replacement or VMAF.

### Deploy-anywhere
10. A Linux worker (e.g., Larry) running WorkerService with QualityTestEnabled=OFF completes the full pipeline: transcode, delete original, update DB. No other service needs to be running.
11. A Windows worker running WorkerService with QualityTestEnabled=OFF completes the same pipeline identically.
12. PathTranslation is passed from ProcessTranscodeQueueService (which already has it) through to FileReplacementBusinessService and HandleJobFailure. No new DB lookups or config loading in FileReplacement.
13. [FIXED] The re-probe step in file replacement uses the worker's FFprobe path (from Workers table via WorkerContext), not SystemSettings.FFprobePath. On a Linux worker, re-probing a transcoded file succeeds and MediaFiles is updated with new codec, resolution, and TranscodedByMediaVortex=True.

14. [FIXED 2026-05-08] **Re-probe path math uses `ntpath`, not `os.path`**, so canonical Windows-flavored DB paths reconstruct correctly when run on Linux workers. Previously `os.path.dirname("T:\\Show\\file.mkv")` on Linux returned the empty string, producing a filename-only "new path" that FFprobe couldn't find. Five files (Fire Country, Switched at Birth S01E11/S02E21, Hunting Hitler, 13 Reasons Why) had been transcoded and replaced on disk but their MediaFiles rows kept pointing at the missing original; recovery handled by `Scripts/FixStuckPostReplacementFiles.py`.

## Status

COMPLETE

### Progress

- [x] Update ShouldQualityTestService.ProcessTranscodedFile() to read QualityTestRequired from TranscodeAttempt
- [x] When QualityTestRequired=False, call FileReplacement with BypassVMAFCheck=True (same as current "Paused" path). Removed dead ShouldTestFile() method. Extracted _ReplaceFileDirectly() helper.
- [x] Add PathTranslation parameter to FileReplacementBusinessService constructor
- [x] Apply path translation in _ProcessCompleteFileReplacement() before all filesystem calls
- [x] Skip temp source cleanup (C:\MediaVortex\Source\) for InPlace output mode
- [x] Skip shutil.move when transcoded file is already in the original's directory (os.path.normpath comparison)
- [x] Pass PathTranslation from ProcessTranscodeQueueService through ShouldQualityTestService to FileReplacement
- [x] In HandleJobFailure: delete partial output file from disk (translate TemporaryFilePaths.LocalOutputPath to local path, delete if exists)
- [x] In HandleJobFailure: DELETE TemporaryFilePaths row for the failed TranscodeAttemptId
- [x] Verify on primary Windows machine: I9 completed DxD S04E01 end-to-end (Success=True, FileReplaced=True, TranscodedByMediaVortex=True, Codec=av1)
- [x] Verify on Linux worker: Larry workers completed transcode + file replacement, MediaFiles updated correctly
- [x] Update transcode.flow.md to remove [BUG] annotation and document the corrected bridge behavior
- [x] Update KNOWN-ISSUES.md to mark the post-transcode pipeline bug as FIXED

## Scope

```
Features/QualityTesting/ShouldQualityTestService.py
Features/FileReplacement/FileReplacementBusinessService.py
Features/TranscodeJob/ProcessTranscodeQueueService.py
```

## Files

| File | Change |
|------|--------|
| Features/QualityTesting/ShouldQualityTestService.py | Read QualityTestRequired from DB, skip queue when False |
| Features/FileReplacement/FileReplacementBusinessService.py | Accept PathTranslation, translate paths before filesystem ops, handle InPlace mode |
| Features/TranscodeJob/ProcessTranscodeQueueService.py | Pass PathTranslation through to ShouldQualityTest and FileReplacement; clean up partial output + TemporaryFilePaths on failure |
