import os
import ntpath
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Repositories.DatabaseManager import DatabaseManager
from Services.FileManagerService import FileManagerService
from Core.Logging.LoggingService import LoggingService


class FileReplacementBusinessService:
    """Business service for manual file replacement operations."""

    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 FileManagerInstance: FileManagerService = None,
                 PathTranslation=None, FFprobePath: str = None, WorkerName: str = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FileManager = FileManagerInstance or FileManagerService(FFprobePath=FFprobePath)
        # PathTranslation kept on signature for backward compat with callers that
        # still pass it; actual path resolution now goes through PathStorage.Resolve.
        self.PathTranslation = PathTranslation
        if WorkerName is None:
            import socket
            from Core.WorkerContext import WorkerContext
            Ctx = WorkerContext.Current()
            WorkerName = (Ctx.WorkerName if Ctx else None) or socket.gethostname()
        self.WorkerName = WorkerName

    def _ToLocalPath(self, CanonicalPath: str) -> str:
        """Translate a canonical DB path to a local filesystem path.

        Parses CanonicalPath against StorageRoots to derive (StorageRootId, RelativePath),
        then resolves to the worker-local path. If the path does not match any
        StorageRoot (or PathStorage cannot resolve for this worker) the original
        string is returned unchanged."""
        if not CanonicalPath:
            return CanonicalPath
        try:
            from Core.PathStorage import LoadStorageRoots, Parse as PathParse, Resolve as PathResolve
            SrId, Rel = PathParse(CanonicalPath, LoadStorageRoots(self.DatabaseManager.DatabaseService))
            if SrId is None or Rel is None:
                return CanonicalPath
            return PathResolve(SrId, Rel, self.WorkerName, self.DatabaseManager.DatabaseService)
        except Exception as e:
            LoggingService.LogException(
                f"_ToLocalPath fallthrough for {CanonicalPath!r}",
                e, "FileReplacementBusinessService", "_ToLocalPath",
            )
            return CanonicalPath

    def GenerateOutputFilePath(self, InputFilePath: str) -> str:
        """Generate output file path for transcoded file (same logic as TranscodingBusinessService)."""
        try:
            # Get directory and filename
            directory = os.path.dirname(InputFilePath)
            filename = os.path.basename(InputFilePath)
            name, ext = os.path.splitext(filename)

            # Create output directory (add _transcoded suffix)
            outputDir = os.path.join(directory, "_transcoded")

            # Generate output filename
            outputFilename = f"{name}_transcoded.mp4"
            outputFilePath = os.path.join(outputDir, outputFilename)

            return outputFilePath

        except Exception as e:
            LoggingService.LogException("Exception generating output file path", e,
                                      "FileReplacementBusinessService", "GenerateOutputFilePath")
            return ""

    def GetFailedFileReplacements(self) -> List[Dict[str, Any]]:
        """Get list of transcoded files that passed VMAF but failed file replacement."""
        try:
            LoggingService.LogFunctionEntry("GetFailedFileReplacements", "FileReplacementBusinessService")

            # Get transcoded files that passed VMAF from database
            results = self.DatabaseManager.GetFailedFileReplacements(20)
            failed_replacements = []

            for row in results:
                attempt_id = row['Id']
                original_path = row['FilePath']
                transcoded_path = row['TranscodedFilePath']
                vmaf_score = row['VMAF']
                attempt_date = row['AttemptDate']
                vmaf_status = row['VMAFStatus']

                # Check if original file still exists (replacement may have failed)
                if self.FileManager.ValidateFileExists(original_path):
                    # Check if transcoded file exists
                    if self.FileManager.ValidateFileExists(transcoded_path):
                        failed_replacements.append({
                            'TranscodeAttemptId': attempt_id,
                            'OriginalFilePath': original_path,
                            'TranscodedFilePath': transcoded_path,
                            'VMAFScore': vmaf_score,
                            'AttemptDate': attempt_date,
                            'VMAFStatus': vmaf_status,
                            'OriginalFileName': os.path.basename(original_path),
                            'TranscodedFileName': os.path.basename(transcoded_path),
                            'OriginalFileSize': self.FileManager.GetFileSizeMB(original_path),
                            'TranscodedFileSize': self.FileManager.GetFileSizeMB(transcoded_path)
                        })

            LoggingService.LogInfo(f"Found {len(failed_replacements)} failed file replacements",
                                 "FileReplacementBusinessService", "GetFailedFileReplacements")
            return failed_replacements

        except Exception as e:
            LoggingService.LogException("Exception getting failed file replacements", e,
                                     "FileReplacementBusinessService", "GetFailedFileReplacements")
            return []

    def ProcessFileReplacement(self, TranscodeAttemptId: int) -> Dict[str, Any]:
        """Execute the file replacement for a transcode attempt.

        Single entry point. The disposition decision (whether to replace,
        what reason, whether VMAF was satisfied or bypassed) is owned by
        `PostTranscodeDispositionService` -- this function only EXECUTES the
        decision. Refuses to run unless the attempt's `Disposition` is
        `Replace` or `BypassReplace`.

        See `Features/QualityTesting/post-transcode-disposition.feature.md`
        criteria 3, 14.
        """
        try:
            # Read the disposition + the basic columns we need in one query
            # (avoids the model-coupling tax we'd otherwise pay).
            DispositionRows = self.DatabaseManager.DatabaseService.ExecuteQuery(
                """
                SELECT Disposition, DispositionReason, FileReplaced, FileReplacedDate,
                       NewSizeBytes, OldSizeBytes, VMAF, ProfileName
                FROM TranscodeAttempts WHERE Id = %s
                """,
                (TranscodeAttemptId,),
            )
            if not DispositionRows:
                return {'Success': False, 'ErrorMessage': f'Transcode attempt {TranscodeAttemptId} not found'}
            DispositionRow = DispositionRows[0]

            Disposition = DispositionRow.get('Disposition')
            if Disposition not in ('Replace', 'BypassReplace'):
                return {
                    'Success': False,
                    'ErrorMessage': (
                        f"Refusing to replace TranscodeAttempt {TranscodeAttemptId}: "
                        f"Disposition={Disposition!r} (must be Replace or BypassReplace). "
                        f"Reason={DispositionRow.get('DispositionReason')!r}."
                    ),
                }

            if DispositionRow.get('FileReplaced'):
                return {
                    'Success': False,
                    'ErrorMessage': (
                        f"File for transcode attempt {TranscodeAttemptId} was already "
                        f"replaced on {DispositionRow.get('FileReplacedDate')}"
                    ),
                }

            # Pull the model for the rest of the work (archive, save, etc.)
            transcode_attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not transcode_attempt:
                return {'Success': False, 'ErrorMessage': f'Transcode attempt {TranscodeAttemptId} not found'}

            # File paths
            file_paths_result = self.DatabaseManager.DatabaseService.ExecuteQuery(
                """
                SELECT OriginalPath, LocalSourcePath, LocalOutputPath FROM TemporaryFilePaths
                WHERE TranscodeAttemptId = %s
                """,
                (TranscodeAttemptId,),
            )
            if not file_paths_result:
                return {
                    'Success': False,
                    'ErrorMessage': f'No temporary file path found for transcode attempt {TranscodeAttemptId}',
                }
            OriginalPath = file_paths_result[0]['OriginalPath']
            TranscodedPath = file_paths_result[0]['LocalOutputPath']
            LocalTranscodedPath = self._ToLocalPath(TranscodedPath)

            if not self.FileManager.ValidateFileExists(LocalTranscodedPath):
                return {
                    'Success': False,
                    'ErrorMessage': f'Transcoded file not found at: {LocalTranscodedPath}',
                }

            # Defense-in-depth size guard (the disposition function should already
            # have routed NoSavings to Discard, but guard against bugs upstream).
            # Remux/SubtitleFix legitimately produce similar-or-slightly-larger
            # outputs (container change + audio re-encode) and are exempt.
            isRemux = (transcode_attempt.ProfileName or '') in ('Remux', 'SubtitleFix')
            if (not isRemux
                and transcode_attempt.NewSizeBytes is not None
                and transcode_attempt.OldSizeBytes is not None
                and transcode_attempt.NewSizeBytes >= transcode_attempt.OldSizeBytes):
                errorMsg = (
                    f"Defense-in-depth: refusing to replace because "
                    f"NewSize ({transcode_attempt.NewSizeBytes:,}) >= "
                    f"OldSize ({transcode_attempt.OldSizeBytes:,}). "
                    f"This case should have been routed to Disposition='Discard' "
                    f"upstream -- log a bug if it reaches here."
                )
                LoggingService.LogWarning(errorMsg, "FileReplacementBusinessService", "ProcessFileReplacement")
                return {'Success': False, 'ErrorMessage': errorMsg}

            keep_source = self.DatabaseManager.GetKeepSourceSetting(transcode_attempt.Id)
            if keep_source is None:
                return {
                    'Success': False,
                    'ErrorMessage': 'Could not determine KeepSource setting for this transcode attempt',
                }

            self._ArchiveOriginalFileDetails(OriginalPath, TranscodeAttemptId)

            replacement_result = self._ProcessCompleteFileReplacement(
                OriginalPath, TranscodedPath, keep_source, OriginalPath,
            )

            if replacement_result.get('Success', False):
                transcode_attempt.FileReplaced = True
                transcode_attempt.FileReplacedDate = datetime.now(timezone.utc)
                transcode_attempt.ReplacementType = (
                    'Bypass' if Disposition == 'BypassReplace' else 'Auto'
                )
                self.DatabaseManager.SaveTranscodeAttempt(transcode_attempt)

                self._CleanupTemporaryFilePaths(TranscodeAttemptId)

                LoggingService.LogInfo(
                    f"Replaced file for TranscodeAttempt {TranscodeAttemptId} "
                    f"(Disposition={Disposition}, Reason={DispositionRow.get('DispositionReason')})",
                    "FileReplacementBusinessService", "ProcessFileReplacement",
                )

                return {
                    'Success': True,
                    'Message': 'File replacement completed successfully',
                    'OriginalFilePath': OriginalPath,
                    'TranscodedFilePath': TranscodedPath,
                    'Disposition': Disposition,
                    'DispositionReason': DispositionRow.get('DispositionReason'),
                    'VMAFScore': transcode_attempt.VMAF,
                    'KeepSource': keep_source,
                    'StepsCompleted': replacement_result.get('StepsCompleted', []),
                }

            error_message = replacement_result.get('ErrorMessage', 'Unknown error during file replacement')
            LoggingService.LogError(
                f"File replacement failed for attempt {TranscodeAttemptId}: {error_message}",
                "FileReplacementBusinessService", "ProcessFileReplacement",
            )
            return {'Success': False, 'ErrorMessage': error_message}

        except Exception as e:
            LoggingService.LogException(
                f"Exception processing file replacement for attempt {TranscodeAttemptId}", e,
                "FileReplacementBusinessService", "ProcessFileReplacement",
            )
            return {'Success': False, 'ErrorMessage': f'Exception during file replacement: {str(e)}'}

    def GetFileReplacementStatus(self, TranscodeAttemptId: int) -> Dict[str, Any]:
        """Get the current status of file replacement for a transcode attempt."""
        try:
            transcode_attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not transcode_attempt:
                return {
                    'Success': False,
                    'ErrorMessage': f'Transcode attempt {TranscodeAttemptId} not found'
                }

            # Get the actual transcoded file path from QualityTestingQueue
            vmaf_query = '''
            SELECT TranscodedFilePath FROM QualityTestingQueue
            WHERE TranscodeAttemptId = %s
            '''
            vmaf_result = self.DatabaseManager.DatabaseService.ExecuteQuery(vmaf_query, (TranscodeAttemptId,))

            if not vmaf_result:
                return {
                    'Success': False,
                    'ErrorMessage': f'No VMAF queue entry found for transcode attempt {TranscodeAttemptId}'
                }

            transcoded_path = vmaf_result[0]['TranscodedFilePath']
            original_exists = self.FileManager.ValidateFileExists(transcode_attempt.FilePath)
            transcoded_exists = self.FileManager.ValidateFileExists(transcoded_path)

            return {
                'Success': True,
                'TranscodeAttemptId': TranscodeAttemptId,
                'OriginalFilePath': transcode_attempt.FilePath,
                'TranscodedFilePath': transcoded_path,
                'VMAFScore': transcode_attempt.VMAF,
                'OriginalFileExists': original_exists,
                'TranscodedFileExists': transcoded_exists,
                'FileReplaced': getattr(transcode_attempt, 'FileReplaced', False),
                'FileReplacementDate': getattr(transcode_attempt, 'FileReplacementDate', None),
                'CanReplace': original_exists and transcoded_exists and transcode_attempt.VMAF and transcode_attempt.VMAF >= 90
            }

        except Exception as e:
            LoggingService.LogException(f"Exception getting file replacement status for attempt {TranscodeAttemptId}", e,
                                      "FileReplacementBusinessService", "GetFileReplacementStatus")
            return {
                'Success': False,
                'ErrorMessage': f'Exception getting status: {str(e)}'
            }


    def PrepareReplacement(self, OriginalFilePath: str) -> Dict[str, Any]:
        """Rename source to `.orig` BEFORE FFmpeg runs.

        With the rename done up front, FFmpeg can write directly to the
        original source path (now free) -- no side-by-side suffix or strip
        step needed. Use this in worker job processors (ProcessRemuxJob,
        ProcessSubtitleFixJob) right after SetupFilePreparation and before
        BuildRemuxCommand. On any later failure, call RollbackReplacement
        to restore the original. On success, FinalizeReplacement (or the
        existing _ProcessCompleteFileReplacement which detects the
        already-renamed state) settles the .orig per KeepSource.

        Returns {Success, OrigBackupPath, Message}. Refuses to clobber a
        pre-existing `.orig` -- a prior failed run needs manual cleanup.
        """
        try:
            LocalOriginalPath = self._ToLocalPath(OriginalFilePath)
            if not os.path.exists(LocalOriginalPath):
                return {
                    'Success': False,
                    'ErrorMessage': f'Source file does not exist: {LocalOriginalPath}'
                }
            CandidateBackup = LocalOriginalPath + '.orig'
            if os.path.exists(CandidateBackup):
                return {
                    'Success': False,
                    'ErrorMessage': (
                        f"Pre-existing .orig backup at {CandidateBackup}. Refusing to "
                        f"overwrite -- a prior replacement may have failed and needs "
                        f"manual cleanup before this can proceed."
                    )
                }
            os.rename(LocalOriginalPath, CandidateBackup)
            LoggingService.LogInfo(
                f"PrepareReplacement: renamed {LocalOriginalPath} -> {CandidateBackup}",
                "FileReplacementBusinessService", "PrepareReplacement"
            )
            return {
                'Success': True,
                'OrigBackupPath': CandidateBackup,
                'Message': f'Renamed source to {CandidateBackup}'
            }
        except Exception as e:
            LoggingService.LogException(
                f"PrepareReplacement failed for {OriginalFilePath}",
                e, "FileReplacementBusinessService", "PrepareReplacement"
            )
            return {'Success': False, 'ErrorMessage': f'PrepareReplacement failed: {str(e)}'}

    def RollbackReplacement(self, OriginalFilePath: str, OrigBackupPath: str,
                             TargetFilePath: str = None) -> Dict[str, Any]:
        """Undo PrepareReplacement on any failure between Prepare and Finalize.

        - If TargetFilePath is supplied and exists, delete it (partial output).
        - If OrigBackupPath exists, rename it back to OriginalFilePath.

        Idempotent on the .orig rename: if the original is already in place
        (e.g. we're called twice), returns success silently. The TargetFilePath
        cleanup is best-effort -- a stuck partial file is logged but doesn't
        block the rename-back.
        """
        import shutil  # noqa: F401 (mirror imports of sibling methods)
        try:
            LocalOriginalPath = self._ToLocalPath(OriginalFilePath)
            LocalOrigBackup = self._ToLocalPath(OrigBackupPath)
            if TargetFilePath:
                LocalTargetPath = self._ToLocalPath(TargetFilePath)
                if os.path.exists(LocalTargetPath):
                    try:
                        os.remove(LocalTargetPath)
                        LoggingService.LogInfo(
                            f"Rollback: removed partial target {LocalTargetPath}",
                            "FileReplacementBusinessService", "RollbackReplacement"
                        )
                    except Exception as RmEx:
                        LoggingService.LogException(
                            f"Rollback: could not remove partial target {LocalTargetPath} (continuing)",
                            RmEx, "FileReplacementBusinessService", "RollbackReplacement"
                        )

            if os.path.exists(LocalOrigBackup):
                if os.path.exists(LocalOriginalPath):
                    LoggingService.LogWarning(
                        f"Rollback: original at {LocalOriginalPath} AND backup at {LocalOrigBackup} both exist. "
                        f"Refusing to clobber. Manual review required.",
                        "FileReplacementBusinessService", "RollbackReplacement"
                    )
                    return {
                        'Success': False,
                        'ErrorMessage': 'Both original and .orig exist; manual review required'
                    }
                os.rename(LocalOrigBackup, LocalOriginalPath)
                LoggingService.LogWarning(
                    f"Rollback: restored {LocalOriginalPath} from {LocalOrigBackup}",
                    "FileReplacementBusinessService", "RollbackReplacement"
                )
                return {'Success': True, 'Message': f'Restored {LocalOriginalPath} from .orig'}
            # No .orig to rollback (e.g. PrepareReplacement was never called)
            return {'Success': True, 'Message': 'No .orig backup to rollback'}
        except Exception as e:
            LoggingService.LogException(
                f"RollbackReplacement failed for {OriginalFilePath}",
                e, "FileReplacementBusinessService", "RollbackReplacement"
            )
            return {'Success': False, 'ErrorMessage': f'RollbackReplacement failed: {str(e)}'}

    def _ProcessCompleteFileReplacement(self, OriginalFilePath: str, TranscodedFilePath: str, KeepSource: bool, NetworkOriginalPath: str = None) -> Dict[str, Any]:
        """Atomic-replace pattern with rollback. Never mutates the original until
        a verified new file is in place; never leaves the disk in a half-moved
        state on failure.

        Sequence:
          1. Rename `original.ext` -> `original.ext.orig` (backup; instant on
             same filesystem). Refuses to clobber a pre-existing `.orig`.
          2. Compute final TargetPath. If the staged filename ends in
             `_remuxed.mp4` or `_subfix.mp4`, strip that side-by-side suffix
             so the final name matches the operator's expectation. Transcode
             jobs keep their resolution suffix (e.g. `_480p.mp4`).
          3. Move staged file to TargetPath.
          4. Verify TargetPath exists on disk and is non-zero.
          5. Update MediaFiles row (re-probe + metadata refresh).
          6. Settle the .orig backup: delete it if !KeepSource, otherwise
             rename to legacy `.old<ext>` convention for the operator.

        Rollback (any failure between steps 2-5):
          - Delete TargetPath if a partial new file landed there.
          - Rename `original.ext.orig` back to `original.ext`.
          - Return Success=False; original is bit-identical to its pre-call state.

        Step 5's DB update failure does NOT roll back -- the file is on disk
        correctly and a future probe reconciles the row. Same as before.

        All paths from the DB are canonical (T:\\...). PathTranslation converts them
        to local mount paths before any filesystem operation.

        Args:
            OriginalFilePath: Canonical path to the original file
            TranscodedFilePath: Canonical path to the staged file (e.g. file_remuxed.mp4)
            KeepSource: True keeps the .orig backup as `.old<ext>`; False deletes it
            NetworkOriginalPath: Canonical path for DB lookups (same as OriginalFilePath)
        """
        import shutil
        try:
            LocalOriginalPath = self._ToLocalPath(OriginalFilePath)
            LocalTranscodedPath = self._ToLocalPath(TranscodedFilePath)

            LoggingService.LogFunctionEntry("_ProcessCompleteFileReplacement", "FileReplacementBusinessService",
                                          LocalOriginalPath, LocalTranscodedPath, KeepSource)

            StepsCompleted = []

            # Compute the final target path: <original-basename>-mv<output-ext>.
            # Derives from the ORIGINAL filename (not the staged filename) so any
            # encode-time suffixes the staged file carries -- `_remuxed.mp4`,
            # `_subfix.mp4`, resolution suffixes like `_480p.mp4`, etc. -- are
            # uniformly retired into the single `-mv` marker.
            #
            # The `-mv` suffix is the canonical "MediaVortex transcoded this"
            # marker on disk. It is structurally distinct from any source
            # filename, which closes the same-name collision class that
            # destroyed source files in the BuildRemuxCommand bug fixed
            # 2026-05-09 (KNOWN-ISSUES.md:104) -- defense-in-depth at the
            # filename level. See Features/FileReplacement/transcoded-output-placement.feature.md
            # criteria 4, 5.
            OriginalDir = os.path.dirname(LocalOriginalPath)
            OriginalBasename = os.path.splitext(os.path.basename(LocalOriginalPath))[0]
            TargetExt = os.path.splitext(LocalTranscodedPath)[1] or ".mp4"
            TargetPath = os.path.join(OriginalDir, OriginalBasename + "-mv" + TargetExt)

            # Step 1: rename original to .orig (atomic backup). Three paths:
            # - "Self-managed" (legacy / transcode): we do the rename here
            # - "Pre-renamed" (rename-before-encode flow used by remux): the
            #   worker called PrepareReplacement before FFmpeg, so the
            #   original is already at .orig. We detect that and just track
            #   the backup path for the settle step.
            # - "Same-ext pre-renamed" (mp4-to-mp4 remux): PrepareReplacement
            #   renamed source.mp4 to source.mp4.orig, FFmpeg wrote output to
            #   source.mp4. LocalOriginalPath exists (it's the OUTPUT) and
            #   .orig exists (it's the original). This is NOT an inconsistent
            #   state -- it's the pre-renamed flow where the extension didn't
            #   change.
            OrigBackupPath = None
            CandidateBackup = LocalOriginalPath + ".orig"
            SamePathPreRenamed = (
                os.path.exists(CandidateBackup)
                and os.path.normpath(LocalOriginalPath) == os.path.normpath(LocalTranscodedPath)
            )
            if SamePathPreRenamed:
                # Same-ext pre-renamed flow: the file at LocalOriginalPath is
                # the FFmpeg output, not the original. The original is at .orig.
                OrigBackupPath = CandidateBackup
                StepsCompleted.append(f"Found pre-renamed backup at {OrigBackupPath} (same-ext remux)")
                LoggingService.LogInfo(
                    f"Same-ext pre-renamed flow: tracking existing .orig at {OrigBackupPath}",
                    "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                )
            elif os.path.exists(LocalOriginalPath):
                # Original is at its source path -- self-managed flow. Rename now.
                if os.path.exists(CandidateBackup):
                    ErrorMsg = (
                        f"Pre-existing .orig backup at {CandidateBackup} AND original is still at {LocalOriginalPath}. "
                        f"Inconsistent state -- a prior replacement failed mid-stream. Manual cleanup required."
                    )
                    LoggingService.LogError(ErrorMsg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                    return {'Success': False, 'ErrorMessage': ErrorMsg}
                try:
                    os.rename(LocalOriginalPath, CandidateBackup)
                    OrigBackupPath = CandidateBackup
                    StepsCompleted.append(f"Renamed original to backup: {OrigBackupPath}")
                    LoggingService.LogInfo(f"Renamed original to backup: {OrigBackupPath}",
                                         "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                except Exception as e:
                    ErrorMsg = f"Failed to rename original to .orig backup: {str(e)}"
                    LoggingService.LogError(ErrorMsg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                    return {'Success': False, 'ErrorMessage': ErrorMsg}
            elif os.path.exists(CandidateBackup):
                # Pre-renamed flow: PrepareReplacement already ran. Track the backup.
                OrigBackupPath = CandidateBackup
                StepsCompleted.append(f"Found pre-renamed backup at {OrigBackupPath} (PrepareReplacement was called)")
                LoggingService.LogInfo(
                    f"Pre-renamed flow: tracking existing .orig at {OrigBackupPath}",
                    "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                )
            else:
                # Neither original nor backup is present -- file was deleted by
                # something outside our control (operator, another process, etc.).
                StepsCompleted.append("Original was already absent (no backup needed)")
                LoggingService.LogInfo(f"Original was already absent: {LocalOriginalPath}",
                                     "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")

            def _Rollback(Reason: str) -> None:
                """Restore original from .orig backup. Removes any partial
                target file first. Logs the rollback reason loudly."""
                try:
                    if os.path.exists(TargetPath):
                        try:
                            os.remove(TargetPath)
                            LoggingService.LogInfo(f"Rollback: removed partial target {TargetPath}",
                                                 "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                        except Exception as RmEx:
                            LoggingService.LogException(
                                f"Rollback: could not remove partial target {TargetPath}",
                                RmEx, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                            )
                    if OrigBackupPath and os.path.exists(OrigBackupPath):
                        os.rename(OrigBackupPath, LocalOriginalPath)
                        LoggingService.LogWarning(
                            f"Rollback complete -- original restored from {OrigBackupPath} (cause: {Reason})",
                            "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                        )
                except Exception as RbEx:
                    LoggingService.LogException(
                        f"CRITICAL: rollback failed -- original may be at {OrigBackupPath} requiring manual recovery",
                        RbEx, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                    )

            # Step 2/3: move staged file to TargetPath when needed. Two paths:
            # - "Side-by-side" (legacy / transcode): staged path differs from
            #   target -- shutil.move it into place.
            # - "Pre-renamed" (rename-before-encode): staged path EQUALS target
            #   because PrepareReplacement freed the source path before FFmpeg
            #   wrote there directly. Skip the move; FFmpeg already produced
            #   the file at the right location.
            # shutil.move within the same filesystem is an atomic rename.
            try:
                if os.path.normpath(LocalTranscodedPath) == os.path.normpath(TargetPath):
                    # Pre-renamed flow -- file is already at target. Verify the
                    # original was indeed renamed (OrigBackupPath set above);
                    # if not, something is wrong (we'd be looking at the
                    # original itself, not the new output).
                    if not OrigBackupPath:
                        _Rollback("staging path equals target path AND no .orig backup exists -- this would clobber an original")
                        return {
                            'Success': False,
                            'ErrorMessage': (
                                "Staged file is at the target path with no .orig backup tracked. "
                                "Cannot safely distinguish new output from untouched original."
                            )
                        }
                    StepsCompleted.append(f"Staged file is already at target {TargetPath} (pre-renamed flow); no move needed")
                    LoggingService.LogInfo(
                        f"Pre-renamed flow: skipping move (staged file already at {TargetPath})",
                        "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                    )
                else:
                    shutil.move(LocalTranscodedPath, TargetPath)
                    StepsCompleted.append(f"Moved staged file to {TargetPath}")
                    LoggingService.LogInfo(f"Moved staged file to {TargetPath}",
                                         "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
            except Exception as e:
                _Rollback(f"shutil.move failed: {str(e)}")
                return {'Success': False, 'ErrorMessage': f"Failed to move staged file to target: {str(e)}"}

            # Step 4: verify target file is non-zero on disk before declaring success.
            try:
                TargetSize = os.path.getsize(TargetPath)
            except Exception as e:
                _Rollback(f"could not stat target after move: {str(e)}")
                return {'Success': False, 'ErrorMessage': f"Could not stat target after move: {str(e)}"}
            if TargetSize <= 0:
                _Rollback(f"target file is empty after move (size={TargetSize})")
                return {'Success': False, 'ErrorMessage': f"Target file is empty: {TargetPath}"}
            StepsCompleted.append(f"Verified target file exists and has {TargetSize} bytes")

            # Step 5: Update MediaFiles table with new file information.
            # NOTE: failure here does NOT roll back -- the new file is on disk
            # correctly; a future probe will reconcile the DB row. This matches
            # prior behavior. Only steps 1-4 (filesystem operations) trigger
            # rollback.
            CanonicalOriginal = NetworkOriginalPath or OriginalFilePath
            # Compute canonical (DB-shape) path for the new file: same directory
            # as the canonical original, basename matches the locally-resolved
            # TargetPath (which is `<originalbasename>-mv<ext>` after the
            # naming-convention change in transcoded-output-placement.feature.md).
            CanonicalNewPath = ntpath.join(ntpath.dirname(CanonicalOriginal), os.path.basename(TargetPath))
            UpdateResult = self._UpdateMediaFilesAfterReplacement(CanonicalOriginal, CanonicalNewPath)
            if UpdateResult.get('Success', False):
                StepsCompleted.append("Updated MediaFiles table")
                LoggingService.LogInfo("Successfully updated MediaFiles table",
                                     "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                # Recompute IsCompliant + RecommendedMode now that the file's
                # metadata has been updated (transcode-vs-remux-routing criterion 17).
                RecomputeMediaFileId = UpdateResult.get('MediaFileId')
                if RecomputeMediaFileId:
                    try:
                        from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
                        Updated = QueueManagementBusinessService().RecomputeForFiles([RecomputeMediaFileId])
                        StepsCompleted.append(f"Recomputed compliance (updated {Updated} row)")
                    except Exception as RecomputeEx:
                        LoggingService.LogException(
                            f"RecomputeForFiles failed for MediaFileId={RecomputeMediaFileId} after replacement",
                            RecomputeEx, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                        )
            else:
                LoggingService.LogWarning(
                    f"MediaFiles update skipped after successful replacement -- transcoded file is on disk "
                    f"but DB row still reflects the original (see prior LogError for FFprobe cause). "
                    f"Local: '{UpdateResult.get('LocalNewFilePath')}', Canonical: '{UpdateResult.get('CanonicalNewFilePath')}'",
                    "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                )

            # Step 6: settle the .orig backup. Replacement succeeded; original
            # is no longer needed unless KeepSource=True.
            if OrigBackupPath and os.path.exists(OrigBackupPath):
                if KeepSource:
                    OriginalFilename = os.path.basename(LocalOriginalPath)
                    OriginalName, OriginalExt = os.path.splitext(OriginalFilename)
                    LegacyOldPath = os.path.join(OriginalDir, f"{OriginalName}.old{OriginalExt}")
                    try:
                        os.rename(OrigBackupPath, LegacyOldPath)
                        StepsCompleted.append(f"Kept original backup as {LegacyOldPath}")
                        LoggingService.LogInfo(f"Kept original backup at {LegacyOldPath}",
                                             "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                    except Exception as e:
                        LoggingService.LogWarning(
                            f"Could not rename .orig to .old (left at {OrigBackupPath}): {str(e)}",
                            "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                        )
                else:
                    try:
                        os.remove(OrigBackupPath)
                        StepsCompleted.append("Deleted .orig backup")
                        LoggingService.LogInfo(f"Deleted .orig backup at {OrigBackupPath}",
                                             "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                    except Exception as e:
                        LoggingService.LogWarning(
                            f"Could not delete .orig backup (left at {OrigBackupPath}): {str(e)}",
                            "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                        )

            return {
                'Success': True,
                'StepsCompleted': StepsCompleted,
                'Message': f'File replacement completed successfully. Steps: {", ".join(StepsCompleted)}'
            }

        except Exception as e:
            LoggingService.LogException(f"Exception in complete file replacement process", e,
                                      "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
            return {
                'Success': False,
                'ErrorMessage': f'Exception during file replacement: {str(e)}'
            }

    def _UpdateMediaFilesAfterReplacement(self, OriginalFilePath: str, NewFilePath: str) -> Dict[str, Any]:
        """Update MediaFiles table with new file information after successful replacement."""
        try:
            LoggingService.LogFunctionEntry("_UpdateMediaFilesAfterReplacement", "FileReplacementBusinessService",
                                          OriginalFilePath, NewFilePath)

            # Get the existing MediaFile record using the original path
            media_file = self.DatabaseManager.GetMediaFileByPath(OriginalFilePath)
            if not media_file:
                return {
                    'Success': False,
                    'ErrorMessage': f'MediaFile record not found for path: {OriginalFilePath}'
                }

            # Extract new metadata from the transcoded file at its new location
            # Translate canonical DB path to local filesystem path for FFprobe
            LocalNewFilePath = self._ToLocalPath(NewFilePath)
            metadata = self.FileManager.ExtractMediaMetadata(LocalNewFilePath)
            if not metadata.get('Success', False):
                # Surface the original FFprobe error verbatim instead of wrapping it.
                # The previous "Failed to extract metadata: ..." prefix made it look like
                # a generic application error in the DB Logs; the actual FFprobe stderr is
                # what an operator needs to see.
                OriginalError = metadata.get('ErrorMessage', 'Unknown error')
                LoggingService.LogError(
                    f"Re-probe failed for transcoded file at '{LocalNewFilePath}' (canonical: '{NewFilePath}'): {OriginalError}",
                    "FileReplacementBusinessService", "_UpdateMediaFilesAfterReplacement"
                )
                return {
                    'Success': False,
                    'ErrorMessage': OriginalError,
                    'LocalNewFilePath': LocalNewFilePath,
                    'CanonicalNewFilePath': NewFilePath,
                }

            # Update the MediaFile with new file path and filename
            media_file.FilePath = NewFilePath  # Update to new file path
            media_file.FileName = ntpath.basename(NewFilePath)
            # Path-storage: derive (StorageRootId, RelativePath) for the new path so
            # SaveMediaFile writes them as the canonical identifier, not just FilePath.
            try:
                from Core.PathStorage import LoadStorageRoots, Parse as PathParse
                NewSrId, NewRel = PathParse(NewFilePath, LoadStorageRoots(self.DatabaseManager.DatabaseService))
                if NewSrId is not None:
                    media_file.StorageRootId = NewSrId
                    media_file.RelativePath = NewRel or ''
            except Exception as e:
                LoggingService.LogException(
                    f"Failed to derive StorageRootId/RelativePath for new path {NewFilePath!r}",
                    e, "FileReplacementBusinessService", "_UpdateMediaFilesAfterReplacement",
                )

            # Update all FFProbe columns with new transcoded file data
            media_file.SizeMB = metadata.get('FileSizeMB', media_file.SizeMB)
            media_file.VideoBitrateKbps = metadata.get('VideoBitrateKbps')
            media_file.AudioBitrateKbps = metadata.get('AudioBitrateKbps')
            media_file.Resolution = metadata.get('Resolution')
            media_file.Codec = metadata.get('VideoCodec')
            media_file.DurationMinutes = metadata.get('DurationMinutes')
            media_file.FrameRate = metadata.get('FrameRate')

            # Update new metadata fields
            media_file.TotalFrames = metadata.get('TotalFrames')
            media_file.CodecProfile = metadata.get('CodecProfile')
            media_file.ColorRange = metadata.get('ColorRange')
            media_file.FieldOrder = metadata.get('FieldOrder')
            media_file.HasBFrames = metadata.get('HasBFrames')
            media_file.RefFrames = metadata.get('RefFrames')
            media_file.PixelFormat = metadata.get('PixelFormat')
            media_file.Level = metadata.get('Level')
            media_file.AudioChannels = metadata.get('AudioChannels')
            media_file.AudioSampleRate = metadata.get('AudioSampleRate')
            media_file.AudioSampleFormat = metadata.get('AudioSampleFormat')
            media_file.AudioChannelLayout = metadata.get('AudioChannelLayout')
            media_file.AudioCodec = metadata.get('AudioCodec')
            media_file.SubtitleFormats = metadata.get('SubtitleFormats')
            media_file.ContainerFormat = metadata.get('ContainerFormat')
            media_file.OverallBitrate = metadata.get('OverallBitrate')
            media_file.AudioLanguages = metadata.get('AudioLanguages')
            media_file.HasExplicitEnglishAudio = metadata.get('HasExplicitEnglishAudio')

            # Derive ResolutionCategory from new Resolution. Width-primary
            # mapping (matches MediaProbeBusinessService._DeriveResolutionCategory,
            # DatabaseManager._ConvertPixelDimensionsToResolutionCategory, and
            # QueueManagementBusinessService._ResolutionCategoryFromPixels). The
            # strict-height-cutoff version of this logic misclassified 1280x718
            # broadcast-720p content as 480p, leaving Flash S05E14 marked
            # IsCompliant=false even after a successful remux. See the
            # 2026-05-09 width-primary fix.
            NewResolution = media_file.Resolution or ''
            if NewResolution and 'x' in NewResolution:
                try:
                    Parts = NewResolution.split('x', 1)
                    Width = int(Parts[0])
                    Height = int(Parts[1])
                    # Width-primary discrimination
                    if Width >= 3000:
                        media_file.ResolutionCategory = "2160p"
                    elif Width >= 1700:
                        media_file.ResolutionCategory = "1080p"
                    elif Width >= 1100:
                        media_file.ResolutionCategory = "720p"
                    elif Width >= 600:
                        media_file.ResolutionCategory = "480p"
                    elif Height >= 2000:
                        media_file.ResolutionCategory = "2160p"
                    elif Height >= 950:
                        media_file.ResolutionCategory = "1080p"
                    elif Height >= 650:
                        media_file.ResolutionCategory = "720p"
                    else:
                        media_file.ResolutionCategory = "480p"
                except (ValueError, IndexError):
                    pass

            # Set TranscodedByMediaVortex to True
            media_file.TranscodedByMediaVortex = True

            # Update LastScannedDate to current time
            from datetime import datetime
            media_file.LastScannedDate = datetime.now(timezone.utc)

            # Save the updated MediaFile
            self.DatabaseManager.SaveMediaFile(media_file)

            LoggingService.LogInfo(f"Successfully updated MediaFiles record for: {OriginalFilePath}",
                                 "FileReplacementBusinessService", "_UpdateMediaFilesAfterReplacement")

            return {
                'Success': True,
                'Message': 'MediaFiles table updated successfully',
                'MediaFileId': media_file.Id,
            }

        except Exception as e:
            LoggingService.LogException(f"Exception updating MediaFiles after replacement", e,
                                      "FileReplacementBusinessService", "_UpdateMediaFilesAfterReplacement")
            return {
                'Success': False,
                'ErrorMessage': f'Exception updating MediaFiles: {str(e)}'
            }

    def _CleanupTemporaryFilePaths(self, TranscodeAttemptId: int):
        """Delete the TemporaryFilePaths row after successful replacement."""
        try:
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                'DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId = %s',
                (TranscodeAttemptId,)
            )
            LoggingService.LogInfo(f"Cleaned up TemporaryFilePaths for attempt {TranscodeAttemptId}",
                                 "FileReplacementBusinessService", "_CleanupTemporaryFilePaths")
        except Exception as e:
            LoggingService.LogWarning(f"Failed to clean up TemporaryFilePaths for attempt {TranscodeAttemptId}: {str(e)}",
                                    "FileReplacementBusinessService", "_CleanupTemporaryFilePaths")

    def _ArchiveOriginalFileDetails(self, FilePath: str, TranscodeAttemptId: int) -> bool:
        """Archive original file details before replacement to preserve source data."""
        try:
            LoggingService.LogFunctionEntry("_ArchiveOriginalFileDetails", "FileReplacementBusinessService",
                                          FilePath, TranscodeAttemptId)

            # Get the MediaFile record for the original file
            media_file = self.DatabaseManager.GetMediaFileByPath(FilePath)
            if not media_file:
                LoggingService.LogWarning(f"MediaFile record not found for path: {FilePath}",
                                        "FileReplacementBusinessService", "_ArchiveOriginalFileDetails")
                return False

            # Archive original file details using INSERT SELECT
            ArchiveId = self.DatabaseManager.SaveMediaFileArchive(media_file.Id, TranscodeAttemptId)

            if ArchiveId:
                LoggingService.LogInfo(f"Successfully archived original file details for MediaFile {media_file.Id}, Archive ID: {ArchiveId}",
                                     "FileReplacementBusinessService", "_ArchiveOriginalFileDetails")
                return True
            else:
                LoggingService.LogError(f"Failed to archive original file details for MediaFile {media_file.Id}",
                                      "FileReplacementBusinessService", "_ArchiveOriginalFileDetails")
                return False

        except Exception as e:
            LoggingService.LogException("Exception archiving original file details", e,
                                      "FileReplacementBusinessService", "_ArchiveOriginalFileDetails")
            return False
