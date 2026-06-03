# Post-Transcode Pipeline Consistency

**Slug:** post-transcode-pipeline

## What It Does

Makes the post-transcode pipeline (delete original, update DB) work on any worker -- Windows or Linux -- regardless of whether VMAF quality testing is enabled. With InPlace output the transcoded file is already next to the original. The only remaining work after transcode is: delete the original, update MediaFiles, mark TranscodedByMediaVortex=True.

## Concern

Both (code fix + deploy-anywhere infrastructure)

## Success Criteria

### Bridge decision (ShouldQualityTestService) -- SUPERSEDED 2026-05-10

**Criteria 1, 2, 3 are superseded by `Features/QualityTesting/post-transcode-disposition.feature.md`.** The split bridge decisions are replaced by a single `DecidePostTranscodeDisposition(TranscodeAttemptId)` function with explicit `(Disposition, Reason)` outputs persisted to `TranscodeAttempts`. `ShouldQualityTestService` is deleted entirely; the criteria below remain documented for the historical fix that landed before the unified disposition was designed, but the implementation is no longer present.

1. ~~When QualityTestRequired=False on the TranscodeAttempt, ShouldQualityTestService skips the quality test queue entirely and proceeds directly to file cleanup. No QualityTestQueue row is created.~~ Superseded -- the disposition function returns `(BypassReplace, QualityTestNotRequired)` for this case.
2. ~~When QualityTestRequired=True, the existing VMAF queue flow is unchanged -- quality test is queued, WorkerService (with QualityTestEnabled) processes it, auto-replace triggers if VMAF is in range.~~ Superseded -- disposition returns `Pending` until VMAF lands, then re-decides per the canonical decision table.
3. ~~When quality testing capability is not running and QualityTestRequired=True, the quality test is still queued. The bridge does not conflate "capability not running" with "testing disabled."~~ Superseded -- `WhenVmafUnavailable='block'` (default) returns `(NoReplace, VmafServicePaused)`; `'bypass'` returns `(BypassReplace, VmafServicePausedBypassed)`. The conflation is impossible because the reason vocabulary distinguishes them.

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

### Terminal-state cleanup (all dispositions, all queue tables)
15. TemporaryFilePaths rows are deleted at *every* TranscodeAttempt terminal state, not just successful Replace/BypassReplace. A row exists iff the attempt is still in flight (`TranscodeAttempts.Success IS NULL AND CompletedDate IS NULL`). Terminal states that must trigger TFP deletion: FFmpeg failure, FFprobe-verify failure, VMAF failure, every Disposition value (`Replace`, `BypassReplace`, `Discard`, `NoReplace`, `Requeue`), and crash-recovery transitions. Verifiable: with all workers Paused, `SELECT COUNT(*) FROM TemporaryFilePaths tfp JOIN TranscodeAttempts ta ON ta.Id = tfp.TranscodeAttemptId WHERE ta.Success IS NOT NULL` returns 0. **Implementation (live as of 2026-06-02 `filereplacement-decompose` directive):** the chokepoint is `PostTranscodeDispositionService.CleanupTemporaryFilePaths(TranscodeAttemptId)` -- a single public method that owns the DELETE. `_CommitDisposition` calls it for non-Pending Discard/NoReplace/Requeue terminal dispositions; `FileReplacementBusinessService.ProcessFileReplacement` calls it on success (BUG-0010 closure). `HandleJobFailure` in `ProcessTranscodeQueueService` cleans TFP for FFmpeg/FFprobe-verify failures. Crash-recovery transitions are caught by the recurring orphan sweep as a safety net. Canary verification (attempt 27614, 2026-06-03): TFP row created at encode start, 0 rows after disposition committed -- chokepoint fired.

16. ActiveJobs rows cannot survive their parent queue row's deletion in steady state. `ActiveJobs.QueueId` is a polymorphic reference (TranscodeQueue OR QualityTestingQueue, discriminated by `ServiceName`), so a direct FK is not viable -- a DB trigger would hide the leaking caller. Instead: (a) the root-cause queue-delete caller that leaves ActiveJobs behind is identified and fixed at the source so the normal path is correct, and (b) the recurring orphan sweep (see `Features/ServiceControl/orphan-cleanup.flow.md`) catches any future regression and emits one WARN log per removal naming the gone parent. Verifiable: `SELECT COUNT(*) FROM ActiveJobs aj LEFT JOIN TranscodeQueue tq ON tq.Id = aj.QueueId AND aj.ServiceName='TranscodeService' LEFT JOIN QualityTestingQueue qtq ON qtq.Id = aj.QueueId AND aj.ServiceName='QualityTestingService' WHERE (aj.ServiceName='TranscodeService' AND tq.Id IS NULL) OR (aj.ServiceName='QualityTestingService' AND qtq.Id IS NULL)` returns 0 in steady state; any non-zero rate produces WARN entries naming the orphaned row's `ServiceName`/`QueueId` so the leaking caller can be tracked.

17. QualityTestingQueue rows pointing at TranscodeAttempts already finished elsewhere (`Success IS NOT NULL` and `QualityTestCompleted=True`) get deleted by the same recurring orphan sweep that handles ActiveJobs orphans (see `Features/ServiceControl/orphan-cleanup.flow.md`). Prevents the operator-visible "in flight" QT job that has actually been done for hours. Verifiable: with a fresh `Success=True` attempt and a stale QualityTestingQueue row pointing at it, one sweep cycle leaves QualityTestingQueue empty.

18. TranscodeProgress duplicates are prevented at the schema level: `UNIQUE (TranscodeAttemptId)`. Existing duplicates are deduped in the migration before the constraint is added. The `CleanupOrphanedProgressRecords` sweep runs on a recurring timer in `WorkerService` (folded into the same orphan-cleanup loop as criteria 16 and 17, not a separate thread), not only at worker startup. Verifiable: schema check shows the unique index; `SELECT COUNT(*) FROM Logs WHERE FunctionName LIKE '%OrphanCleanup%' AND TimeStamp > NOW() - INTERVAL '1 hour'` returns >= 1 from each running worker.

19. **[BUG-0002]** Media files whose on-disk file has zero audio streams must not exist in the DB. A cleanup script identifies every `MediaFiles` row where `ffprobe` on the actual file returns no audio stream, then deletes the row and every dependent record (`TranscodeAttempts`, `TranscodeFiles`, `MediaFilesArchive`, `QualityTestResults`, `QualityTestProgress`, `TranscodeQueue`, `QualityTestingQueue`, `ActiveJobs`, `TemporaryFilePaths`, `ScanJobs` if linked, `ProblemFiles` if linked) in a single transaction per file. Before deletion the script writes every removed file's `RelativePath` (or full `FilePath` when relative path is missing) to a timestamped `.md` report at the repo root (e.g. `deleted-silent-files-2026-05-16.md`) grouped by show, so the operator can re-acquire if desired. Going forward, the post-replacement re-probe in `_UpdateMediaFilesAfterReplacement` must fail loud when the new file has no audio stream — disposition becomes `Discard`, the on-disk silent file is removed, and the original (`.orig` / `.inprogress`) is restored if still present. Verifiable: (a) after the cleanup script runs, `SELECT COUNT(*) FROM mediafiles m WHERE NOT EXISTS (SELECT 1 FROM <ffprobe stream check>)` returns 0 for the set the script processed; (b) `deleted-silent-files-<date>.md` exists and lists every removed path; (c) a newly-transcoded file that comes out silent does NOT replace its source and produces a `Discard` disposition log entry.

### Deploy-anywhere
10. A Linux worker (e.g., Larry) running WorkerService with QualityTestEnabled=OFF completes the full pipeline: transcode, delete original, update DB. No other service needs to be running.
11. A Windows worker running WorkerService with QualityTestEnabled=OFF completes the same pipeline identically.
12. PathTranslation is passed from ProcessTranscodeQueueService (which already has it) through to FileReplacementBusinessService and HandleJobFailure. No new DB lookups or config loading in FileReplacement.
13. [FIXED] The re-probe step in file replacement uses the worker's FFprobe path (from Workers table via WorkerContext), not SystemSettings.FFprobePath. On a Linux worker, re-probing a transcoded file succeeds and MediaFiles is updated with new codec, resolution, and TranscodedByMediaVortex=True.

14. [FIXED 2026-05-08] **Re-probe path math uses `ntpath`, not `os.path`**, so canonical Windows-flavored DB paths reconstruct correctly when run on Linux workers. Previously `os.path.dirname("T:\\Show\\file.mkv")` on Linux returned the empty string, producing a filename-only "new path" that FFprobe couldn't find. Five files (Fire Country, Switched at Birth S01E11/S02E21, Hunting Hitler, 13 Reasons Why) had been transcoded and replaced on disk but their MediaFiles rows kept pointing at the missing original; recovery handled by `Scripts/FixStuckPostReplacementFiles.py`.

## Status

COMPLETE 2026-05-17 -- all 18 criteria implemented and live-verified.

### Progress (stuck-item cleanup, criteria 15-18)

- [x] Create flow doc `Features/ServiceControl/orphan-cleanup.flow.md` documenting the recurring orphan sweep (entry point, per-cycle steps, failure modes)
- [x] Migration `Scripts/SQLScripts/AddOrphanCleanupAndUniqueProgress.py` -- dedupe existing `TranscodeProgress` duplicates, add `UNIQUE (TranscodeAttemptId)`, idempotent. Applied to dev DB 2026-05-16 (no duplicates found; constraint added).
- [x] Add explicit `ActiveJobs` cleanup to `QueueManagementBusinessService.RemoveJobFromQueue` so the highest-volume user path no longer relies on the sweep (criterion 16 -- known leaking caller fixed at source; sweep remains the safety net)
- [x] Add TFP DELETE to `PostTranscodeDispositionService._CommitDisposition` for terminal dispositions `Discard`/`NoReplace`/`Requeue` (criterion 15). `Replace`/`BypassReplace` defer to FileReplacement's existing success-branch cleanup since the canonical paths are still needed.
- [x] Add TFP DELETE to the VMAF-failure path in `QualityTestingBusinessService` via `_CleanupTemporaryFilePathsForVmafFailure` helper (criterion 15)
- [x] New `OrphanCleanupService` + recurring `_OrphanCleanupLoop` in `WorkerService/Main.py`, sibling to `_StuckJobDetectionLoop`, same interval (criteria 16, 17, 18)
- [x] Verify on I9 (2026-05-16 manual sweep): 550 TFP orphans removed in one cycle; other categories already 0 from operator cleanup. WARN log fired naming the leak count.
- [x] Verify on I9 (2026-05-17 live worker): two `OrphanCleanup swept: TFP=0 ActiveJobs(Transcode)=0 ActiveJobs(QualityTest)=0 QTQueue=0 Progress=0` log lines 120s apart from the running WorkerService process. Steady-state holds.

### Progress (original feature, criteria 1-14)

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
- [x] Update memory/KNOWN-ISSUES.md to mark the post-transcode pipeline bug as FIXED

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
