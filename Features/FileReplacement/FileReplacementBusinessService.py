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

            self._ArchiveOriginalFileDetails(OriginalPath, TranscodeAttemptId)

            replacement_result = self._ProcessCompleteFileReplacement(
                OriginalPath, TranscodedPath, OriginalPath,
                FFmpegCommand=getattr(transcode_attempt, 'FFpmpegCommand', None),
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


    def FinalizePartialReplacement(self, OriginalLocalPath: str, FinalLocalPath: str,
                                    CanonicalOriginalPath: str) -> Dict[str, Any]:
        """Complete a file replacement that got past the `.inprogress` rename
        but did not reach the original-delete step (worker crashed/restarted
        mid-flight). Owns worker-lifecycle.feature.md criterion 12.

        Updates MediaFiles.FilePath to point at the new file, then deletes the
        original. Safe to call when only one of the two files exists -- the
        missing-original branch is a no-op for the delete step.
        """
        try:
            StepsCompleted = []
            if not os.path.exists(FinalLocalPath):
                return {'Success': False, 'ErrorMessage': f'Final file does not exist: {FinalLocalPath}'}

            CanonicalNewPath = ntpath.join(ntpath.dirname(CanonicalOriginalPath), os.path.basename(FinalLocalPath))
            UpdateResult = self._UpdateMediaFilesAfterReplacement(CanonicalOriginalPath, CanonicalNewPath)
            if UpdateResult.get('Success', False):
                StepsCompleted.append("Updated MediaFiles table")
            else:
                LoggingService.LogWarning(
                    f"FinalizePartialReplacement: MediaFiles update failed; original NOT deleted. "
                    f"Local: '{UpdateResult.get('LocalNewFilePath')}'",
                    "FileReplacementBusinessService", "FinalizePartialReplacement"
                )
                return {'Success': True, 'StepsCompleted': StepsCompleted, 'Message': 'Partial: MediaFiles update failed; original retained'}

            if os.path.normpath(OriginalLocalPath) == os.path.normpath(FinalLocalPath):
                StepsCompleted.append("Original and final are the same path; no delete needed")
            elif os.path.exists(OriginalLocalPath):
                try:
                    os.remove(OriginalLocalPath)
                    StepsCompleted.append(f"Deleted original {os.path.basename(OriginalLocalPath)}")
                    LoggingService.LogInfo(f"FinalizePartialReplacement: deleted original {OriginalLocalPath}",
                                         "FileReplacementBusinessService", "FinalizePartialReplacement")
                except Exception as e:
                    LoggingService.LogWarning(
                        f"FinalizePartialReplacement: could not delete original (left at {OriginalLocalPath}): {str(e)}",
                        "FileReplacementBusinessService", "FinalizePartialReplacement"
                    )
            else:
                StepsCompleted.append("Original already absent")

            return {'Success': True, 'StepsCompleted': StepsCompleted}
        except Exception as e:
            LoggingService.LogException(
                f"FinalizePartialReplacement failed for {OriginalLocalPath} -> {FinalLocalPath}",
                e, "FileReplacementBusinessService", "FinalizePartialReplacement"
            )
            return {'Success': False, 'ErrorMessage': str(e)}

    def _ProcessCompleteFileReplacement(self, OriginalFilePath: str, TranscodedFilePath: str, NetworkOriginalPath: str = None, FFmpegCommand: Optional[str] = None) -> Dict[str, Any]:
        """Finalize a transcode by renaming the `.inprogress` staged file to its
        final name, updating MediaFiles, and deleting the original source.

        The original source file is untouched until the final delete -- this is
        the only point in the entire pipeline that mutates it. See
        worker-lifecycle.feature.md criteria 6-9.

        Sequence:
          1. Verify the staged file (a `.inprogress` produced by FFmpeg) exists.
          2. Compute the final target path by dropping the `.inprogress` suffix
             from the staged path. Refuse if it does not have that suffix --
             the only producer of this function's input is the new pattern.
          3. Rename `.inprogress` -> final target (atomic on same filesystem).
          4. Verify target is non-zero on disk.
          5. Update MediaFiles row (re-probe + metadata refresh) so
             MediaFiles.FilePath points at the new file.
          6. Delete the original source file.

        Failure handling:
          - Steps 1-3: staged file is unchanged, original untouched. Caller
            sees Success=False and can delete `.inprogress` separately (or
            leave it for crash recovery to clean up).
          - Step 4: rename succeeded but stat failed -- new file is on disk
            at the final name; we keep going (next scan will reconcile).
          - Step 5: rename succeeded but DB update failed -- a future probe
            reconciles the row. The original is NOT deleted.
          - Step 6: best-effort. If the original delete fails, the new file
            is at its final location and MediaFiles points at it; a leftover
            original is a cleanup issue, not a correctness one.

        Args:
            OriginalFilePath: Canonical path to the original source file.
            TranscodedFilePath: Canonical path to the staged `.inprogress` file.
            NetworkOriginalPath: Canonical path for DB lookups (defaults to OriginalFilePath).
        """
        try:
            LocalOriginalPath = self._ToLocalPath(OriginalFilePath)
            LocalStagedPath = self._ToLocalPath(TranscodedFilePath)

            LoggingService.LogFunctionEntry("_ProcessCompleteFileReplacement", "FileReplacementBusinessService",
                                          LocalOriginalPath, LocalStagedPath)

            StepsCompleted = []

            if not os.path.exists(LocalStagedPath):
                ErrorMsg = f"Staged file not found: {LocalStagedPath}"
                LoggingService.LogError(ErrorMsg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                return {'Success': False, 'ErrorMessage': ErrorMsg}

            if not LocalStagedPath.endswith('.inprogress'):
                ErrorMsg = (
                    f"Staged file does not end in .inprogress: {LocalStagedPath}. "
                    f"The .inprogress pattern is the only supported producer for FileReplacement."
                )
                LoggingService.LogError(ErrorMsg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                return {'Success': False, 'ErrorMessage': ErrorMsg}

            TargetPath = LocalStagedPath[:-len('.inprogress')]

            if os.path.exists(TargetPath):
                ErrorMsg = (
                    f"Refusing to overwrite existing file at target: {TargetPath}. "
                    f"A prior replacement may have partially succeeded and left this artifact behind."
                )
                LoggingService.LogError(ErrorMsg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                return {'Success': False, 'ErrorMessage': ErrorMsg}

            try:
                os.rename(LocalStagedPath, TargetPath)
                StepsCompleted.append(f"Renamed {os.path.basename(LocalStagedPath)} -> {os.path.basename(TargetPath)}")
                LoggingService.LogInfo(f"Dropped .inprogress suffix: {LocalStagedPath} -> {TargetPath}",
                                     "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
            except Exception as e:
                ErrorMsg = f"Failed to rename .inprogress to final target: {str(e)}"
                LoggingService.LogError(ErrorMsg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                return {'Success': False, 'ErrorMessage': ErrorMsg}

            try:
                TargetSize = os.path.getsize(TargetPath)
                if TargetSize <= 0:
                    LoggingService.LogWarning(
                        f"Target file is empty after rename (size={TargetSize}): {TargetPath}",
                        "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                    )
                else:
                    StepsCompleted.append(f"Verified target file has {TargetSize} bytes")
            except Exception as e:
                LoggingService.LogWarning(
                    f"Could not stat target after rename ({TargetPath}): {str(e)}",
                    "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                )

            CanonicalOriginal = NetworkOriginalPath or OriginalFilePath
            CanonicalNewPath = ntpath.join(ntpath.dirname(CanonicalOriginal), os.path.basename(TargetPath))
            UpdateResult = self._UpdateMediaFilesAfterReplacement(CanonicalOriginal, CanonicalNewPath)
            if UpdateResult.get('Success', False):
                StepsCompleted.append("Updated MediaFiles table")
                RecomputeMediaFileId = UpdateResult.get('MediaFileId')
                if RecomputeMediaFileId:
                    # Mark audio complete BEFORE recompute so the cascade sees
                    # fresh state. The just-finished FFmpeg command containing
                    # `loudnorm` is the signal that this file just went through
                    # its one-shot normalize pass; subsequent encodes must
                    # stream-copy audio. See audio-completion.feature.md C12.
                    try:
                        from Features.AudioCompletion.AudioCompletionService import AudioCompletionService
                        if AudioCompletionService.DetectNormalizationInCommand(FFmpegCommand):
                            if AudioCompletionService.MarkAudioComplete(RecomputeMediaFileId):
                                StepsCompleted.append("Marked AudioComplete=true (post-normalize)")
                    except Exception as AudioEx:
                        LoggingService.LogException(
                            f"MarkAudioComplete failed for MediaFileId={RecomputeMediaFileId} -- "
                            f"replacement still succeeded; next admin recompute will reconcile",
                            AudioEx, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                        )
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
                    f"MediaFiles update skipped after successful rename -- transcoded file is on disk "
                    f"but DB row still reflects the original. Original NOT deleted; future probe will reconcile. "
                    f"Local: '{UpdateResult.get('LocalNewFilePath')}', Canonical: '{UpdateResult.get('CanonicalNewFilePath')}'",
                    "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                )
                return {
                    'Success': True,
                    'StepsCompleted': StepsCompleted,
                    'Message': 'Rename succeeded; MediaFiles re-probe deferred to next scan; original retained.',
                }

            if os.path.normpath(LocalOriginalPath) == os.path.normpath(TargetPath):
                StepsCompleted.append("Original and target are the same path; no original to delete")
            elif os.path.exists(LocalOriginalPath):
                try:
                    os.remove(LocalOriginalPath)
                    StepsCompleted.append(f"Deleted original {os.path.basename(LocalOriginalPath)}")
                    LoggingService.LogInfo(f"Deleted original source file: {LocalOriginalPath}",
                                         "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                except Exception as e:
                    LoggingService.LogWarning(
                        f"Could not delete original source (left at {LocalOriginalPath}): {str(e)}",
                        "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                    )
            else:
                StepsCompleted.append("Original source was already absent")

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

            # Re-stamp filesystem timestamps from the NEW file on disk
            # (FileScanning criterion 26: same naive-UTC pattern used by
            # FileScanningBusinessService.GetFileModificationTime so cross-tz
            # workers compute identical values). Without this, the next file
            # scan reads disk mtime >> stored mtime and flips HasFileChanged
            # True for every remux/transcode-replaced file -- wasteful
            # rewrites and broken incremental-skip semantics.
            try:
                NewMtime = datetime.fromtimestamp(
                    os.path.getmtime(LocalNewFilePath), tz=timezone.utc
                ).replace(tzinfo=None)
                media_file.FileModificationTime = NewMtime
                media_file.LastModifiedDate = NewMtime
                media_file.FileSize = os.path.getsize(LocalNewFilePath)
            except Exception as e:
                LoggingService.LogException(
                    f"Failed to re-stamp filesystem timestamps from {LocalNewFilePath}",
                    e, "FileReplacementBusinessService", "_UpdateMediaFilesAfterReplacement"
                )

            # Update LastScannedDate to current time (datetime imported at module top)
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
