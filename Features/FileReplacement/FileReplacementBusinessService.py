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

            # Resolve paths dynamically from (StorageRootId, RelativePath) --
            # NOT from the legacy text-string columns. The text columns drift
            # across worker platforms (Linux POSIX paths vs Windows UNC/drive-
            # letter) and led to BUG-? where a Linux worker's lookup against
            # MediaFiles.FilePath failed because the stored canonical was
            # corrupted by the legacy normalization path.
            file_paths_result = self.DatabaseManager.DatabaseService.ExecuteQuery(
                """
                SELECT SourceStorageRootId, SourceRelativePath,
                       OutputStorageRootId, OutputRelativePath,
                       LocalOutputPath
                FROM TemporaryFilePaths
                WHERE TranscodeAttemptId = %s
                """,
                (TranscodeAttemptId,),
            )
            if not file_paths_result:
                return {
                    'Success': False,
                    'ErrorMessage': f'No temporary file path found for transcode attempt {TranscodeAttemptId}',
                }
            FP = file_paths_result[0]
            SourceSrId = FP.get('SourceStorageRootId')
            SourceRel = FP.get('SourceRelativePath')
            OutputSrId = FP.get('OutputStorageRootId')
            OutputRel = FP.get('OutputRelativePath')
            LocalOutputPathStr = FP.get('LocalOutputPath')

            # Build canonical paths dynamically -- no text-string drift possible.
            from Core.PathStorage import CanonicalFor
            if SourceSrId is None or SourceRel is None:
                return {
                    'Success': False,
                    'ErrorMessage': (
                        f'TemporaryFilePaths for attempt {TranscodeAttemptId} is '
                        f'missing SourceStorageRootId / SourceRelativePath (legacy row?). '
                        f'Cannot resolve canonical source path.'
                    ),
                }
            OriginalPath = CanonicalFor(SourceSrId, SourceRel)
            if OutputSrId is not None and OutputRel is not None:
                CanonicalNewPath = CanonicalFor(OutputSrId, OutputRel)
            else:
                CanonicalNewPath = None  # _ProcessCompleteFileReplacement derives if absent

            # Look up source MediaFile.Id for the compliance gate's carry-forward.
            # Keyed on (StorageRootId, RelativePath) -- matches BUG-0014 path-storage
            # fix (commit e0244d3); no legacy text-path lookup.
            SourceMediaFileId = None
            try:
                MfRows = self.DatabaseManager.DatabaseService.ExecuteQuery(
                    "SELECT Id FROM MediaFiles WHERE StorageRootId = %s AND RelativePath = %s LIMIT 1",
                    (SourceSrId, SourceRel),
                )
                if MfRows:
                    SourceMediaFileId = MfRows[0].get('Id')
            except Exception as MfLookupEx:
                LoggingService.LogException(
                    f"MediaFile lookup by (StorageRootId={SourceSrId}, RelativePath={SourceRel}) failed",
                    MfLookupEx, "FileReplacementBusinessService", "ProcessFileReplacement",
                )

            TranscodedPath = LocalOutputPathStr
            LocalTranscodedPath = self._ToLocalPath(TranscodedPath) if TranscodedPath else None

            if not LocalTranscodedPath or not self.FileManager.ValidateFileExists(LocalTranscodedPath):
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
                FFmpegCommand=getattr(transcode_attempt, 'FfpmpegCommand', None),
                SourceMediaFileId=SourceMediaFileId,
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

                self._NotifyJellyfinOfReplacement(
                    replacement_result.get('CanonicalOriginalPath') or OriginalPath,
                    replacement_result.get('CanonicalNewPath'),
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

            # Compliance gate refused -- record the disposition override
            # (compliance-gated-rename.feature.md criterion 2). The TFP cleanup
            # for the NoReplace disposition is handled by _CommitDisposition.
            if replacement_result.get('ComplianceGateRefused'):
                CascadeReason = replacement_result.get('CascadeReason') or 'unknown'
                try:
                    from Features.QualityTesting.PostTranscodeDispositionService import PostTranscodeDispositionService
                    PostTranscodeDispositionService().RecordComplianceGateFailure(
                        TranscodeAttemptId, CascadeReason
                    )
                except Exception as DispEx:
                    LoggingService.LogException(
                        f"Failed to record ComplianceGateFailed disposition for attempt {TranscodeAttemptId}",
                        DispEx, "FileReplacementBusinessService", "ProcessFileReplacement",
                    )
                LoggingService.LogWarning(
                    f"Compliance gate refused replace for attempt {TranscodeAttemptId}: {CascadeReason}. "
                    f"Disposition flipped to NoReplace/ComplianceGateFailed.",
                    "FileReplacementBusinessService", "ProcessFileReplacement",
                )
                return {'Success': False, 'ErrorMessage': error_message,
                        'ComplianceGateRefused': True, 'CascadeReason': CascadeReason}

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

            self._NotifyJellyfinOfReplacement(CanonicalOriginalPath, CanonicalNewPath)

            return {'Success': True, 'StepsCompleted': StepsCompleted}
        except Exception as e:
            LoggingService.LogException(
                f"FinalizePartialReplacement failed for {OriginalLocalPath} -> {FinalLocalPath}",
                e, "FileReplacementBusinessService", "FinalizePartialReplacement"
            )
            return {'Success': False, 'ErrorMessage': str(e)}

    def _RunComplianceGate(self, LocalStagedPath: str, SourceMediaFileId: int,
                           FFmpegCommand: Optional[str] = None) -> Dict[str, Any]:
        """Pre-rename compliance gate. Owns `compliance-gated-rename.feature.md`
        criteria 1, 4 (BUG-0020 Slice 1).

        Probes the staged `.inprogress` file, synthesizes a candidate
        MediaFile-shaped row by combining the probe output with carry-forward
        fields from the source MediaFiles row (audio language, loudness
        measurements, AudioComplete, AssignedProfile, AudioCorruptSuspect),
        and calls `QueueManagementBusinessService.EvaluateCandidateCompliance`.

        Returns:
            {'Compliant': True,  'RefusalReason': None}                   on pass
            {'Compliant': False, 'RefusalReason': '<cascade_reason>'}     on refuse
            {'Compliant': False, 'RefusalReason': 'source_row_missing'}   when the
                  source MediaFile cannot be located (criterion 4 edge case).
            {'Compliant': False, 'RefusalReason': 'gate_evaluation_error'} on
                  exception -- safe-failure: refuse rather than promote on error.

        The gate FAILS CLOSED on error: any internal exception returns Compliant=False
        so the rename refuses. False negatives (refused encodes that are actually
        compliant) surface as canary failures and prompt investigation; false
        positives (promoted encodes that are non-compliant) reintroduce -mv-mv.
        """
        try:
            from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService

            if not os.path.exists(LocalStagedPath):
                return {'Compliant': False, 'RefusalReason': 'staged_file_missing'}

            # FFprobe pass on the .inprogress.
            ProbeResult = self.FileManager.ExtractMediaMetadata(LocalStagedPath)
            if not ProbeResult.get('Success', False):
                return {'Compliant': False, 'RefusalReason': 'probe_failed'}

            # Source-row carry-forward. Keyed on MediaFiles.Id (passed in by
            # the caller, derived from TFP (SourceStorageRootId, SourceRelativePath)).
            SourceRows = self.DatabaseManager.DatabaseService.ExecuteQuery(
                """
                SELECT Id, FilePath, AssignedProfile,
                       HasExplicitEnglishAudio, AudioLanguages,
                       SourceIntegratedLufs, SourceLoudnessRangeLU,
                       SourceTruePeakDbtp, SourceIntegratedThresholdLufs,
                       LoudnessMeasuredAt, LoudnessMeasurementFailureReason,
                       AudioComplete, AudioCorruptSuspect
                FROM MediaFiles WHERE Id = %s
                """,
                (SourceMediaFileId,),
            )
            if not SourceRows:
                return {'Compliant': False, 'RefusalReason': 'source_row_missing'}
            Src = SourceRows[0]

            # Synthesize the candidate row -- probe fields override, source
            # carries forward the things ffprobe can't derive.
            Resolution = ProbeResult.get('Resolution')
            ResolutionCategory = None
            try:
                Height = None
                if Resolution and 'x' in Resolution:
                    Height = int(Resolution.split('x')[1])
                if Height is not None:
                    if Height >= 2000:
                        ResolutionCategory = '2160p'
                    elif Height >= 1000:
                        ResolutionCategory = '1080p'
                    elif Height >= 700:
                        ResolutionCategory = '720p'
                    elif Height >= 400:
                        ResolutionCategory = '480p'
            except Exception:
                pass

            # SizeMB from the staged file directly -- it's the candidate.
            try:
                SizeMB = os.path.getsize(LocalStagedPath) / (1024.0 * 1024.0)
            except Exception:
                SizeMB = 0

            CandidateRow = {
                # From probe (the candidate's actual measurements):
                'FilePath': Src.get('FilePath'),  # source path -- profile cascade keys on this
                'Resolution': Resolution,
                'ResolutionCategory': ResolutionCategory,
                'Codec': ProbeResult.get('VideoCodec'),
                'ContainerFormat': ProbeResult.get('ContainerFormat'),
                'AudioCodec': ProbeResult.get('AudioCodec'),
                'AudioChannels': ProbeResult.get('AudioChannels'),
                'AudioBitrateKbps': ProbeResult.get('AudioBitrateKbps'),
                'VideoBitrateKbps': ProbeResult.get('VideoBitrateKbps'),
                'DurationMinutes': ProbeResult.get('DurationMinutes'),
                'SizeMB': SizeMB,
                # From source (carried forward -- the encode preserves these):
                'AssignedProfile': Src.get('AssignedProfile'),
                'HasExplicitEnglishAudio': Src.get('HasExplicitEnglishAudio'),
                'AudioLanguages': Src.get('AudioLanguages'),
                'AudioComplete': Src.get('AudioComplete'),
                'AudioCorruptSuspect': Src.get('AudioCorruptSuspect'),
                'SourceIntegratedLufs': Src.get('SourceIntegratedLufs'),
                'SourceLoudnessRangeLU': Src.get('SourceLoudnessRangeLU'),
                'SourceTruePeakDbtp': Src.get('SourceTruePeakDbtp'),
                'SourceIntegratedThresholdLufs': Src.get('SourceIntegratedThresholdLufs'),
                'LoudnessMeasuredAt': Src.get('LoudnessMeasuredAt'),
                'LoudnessMeasurementFailureReason': Src.get('LoudnessMeasurementFailureReason'),
            }

            # Special case: this very encode just ran loudnorm. The source row
            # still shows AudioComplete=False at gate time because MarkAudioComplete
            # fires AFTER the rename (post-rename branch in _ProcessCompleteFileReplacement).
            # Without this override, the gate would refuse the very encode that
            # normalized audio -- a false negative that breaks every first-pass
            # transcode of unnormalized content. Detect loudnorm in the command
            # and set AudioComplete=True in the candidate row so the cascade
            # skips both the LUFS-measurement gate and the AudioConfirmedOffTarget
            # check (both predicates short-circuit when AudioComplete is True).
            try:
                from Features.AudioCompletion.AudioCompletionService import AudioCompletionService
                if FFmpegCommand and AudioCompletionService.DetectNormalizationInCommand(FFmpegCommand):
                    CandidateRow['AudioComplete'] = True
            except Exception:
                pass  # fail-open on the override only -- if detect fails, gate
                      # still uses the source row's AudioComplete (which may
                      # cause a false negative; the canary catches it).

            Eval = QueueManagementBusinessService().EvaluateCandidateCompliance(CandidateRow)

            if Eval.get('IsCompliant') is True and Eval.get('RecommendedMode') is None:
                return {'Compliant': True, 'RefusalReason': None}

            RefusalReason = Eval.get('RefusalReason') or (
                f"undecidable_{Eval.get('RecommendedMode') or 'unknown'}"
                if Eval.get('IsCompliant') is None
                else f"non_compliant_{Eval.get('RecommendedMode') or 'unknown'}"
            )
            return {'Compliant': False, 'RefusalReason': RefusalReason}

        except Exception as e:
            LoggingService.LogException(
                f"Compliance gate raised for staged={LocalStagedPath}, SourceMediaFileId={SourceMediaFileId}",
                e, "FileReplacementBusinessService", "_RunComplianceGate"
            )
            return {'Compliant': False, 'RefusalReason': 'gate_evaluation_error'}

    def _ProcessCompleteFileReplacement(self, OriginalFilePath: str, TranscodedFilePath: str, NetworkOriginalPath: str = None, FFmpegCommand: Optional[str] = None, SourceMediaFileId: Optional[int] = None) -> Dict[str, Any]:
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

            # Same-slot replacement: the source IS the target (re-transcode of a
            # `-mv.<ext>` file -- compliance-gated-rename.feature.md criterion 7).
            # `_CollapseMvSuffix` in CommandBuilder collapses `foo-mv.<src>` to
            # produce `foo-mv.<dst>.inprogress` instead of `foo-mv-mv.<dst>.inprogress`.
            # When the source and target paths match, the standard refuse-on-target-exists
            # check would incorrectly trip; instead we do a safe rename dance.
            SameSlotReplacement = (
                os.path.normcase(os.path.normpath(TargetPath))
                == os.path.normcase(os.path.normpath(LocalOriginalPath))
            )

            if os.path.exists(TargetPath) and not SameSlotReplacement:
                ErrorMsg = (
                    f"Refusing to overwrite existing file at target: {TargetPath}. "
                    f"A prior replacement may have partially succeeded and left this artifact behind."
                )
                LoggingService.LogError(ErrorMsg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                return {'Success': False, 'ErrorMessage': ErrorMsg}

            # ── Compliance gate (compliance-gated-rename.feature.md C1, C3) ──
            # The cascade predicate is the gatekeeper for the `-mv` rename.
            # FFmpeg returning 0 + valid container is necessary but no longer
            # sufficient: if the next cascade pass would re-queue this output,
            # we must NOT promote it -- doing so creates `-mv-mv.<ext>`.
            # Gate fails closed (refuse on any error -- prevents -mv-mv).
            # SourceMediaFileId is optional only to preserve the FinalizePartialReplacement
            # crash-recovery entry point; the normal ProcessFileReplacement path
            # always supplies it.
            if SourceMediaFileId is not None:
                GateResult = self._RunComplianceGate(LocalStagedPath, SourceMediaFileId, FFmpegCommand)
                if not GateResult.get('Compliant', False):
                    CascadeReason = GateResult.get('RefusalReason') or 'unknown'
                    ErrorMsg = f'ComplianceGateFailed: {CascadeReason}'
                    LoggingService.LogWarning(
                        f"Compliance gate refused rename for {LocalStagedPath}: {CascadeReason}. "
                        f"Deleting `.inprogress`; source `{LocalOriginalPath}` untouched.",
                        "FileReplacementBusinessService", "_ProcessCompleteFileReplacement",
                    )
                    # Delete the .inprogress (criterion 3). Source file untouched.
                    try:
                        if os.path.exists(LocalStagedPath):
                            os.remove(LocalStagedPath)
                    except Exception as DelEx:
                        LoggingService.LogException(
                            f"Compliance gate refused but failed to delete `.inprogress` {LocalStagedPath}",
                            DelEx, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                        )
                    return {
                        'Success': False,
                        'ErrorMessage': ErrorMsg,
                        'ComplianceGateRefused': True,
                        'CascadeReason': CascadeReason,
                    }

            if SameSlotReplacement:
                # Source path == target path (re-transcode of a `-mv.<ext>` file).
                # Atomic rename dance with a `.replacing.bak` to keep the slot
                # recoverable across a mid-rename crash. Sequence:
                #   1. rename source -> source.replacing.bak  (target slot free)
                #   2. rename .inprogress -> target           (publish new file)
                #   3. delete source.replacing.bak           (cleanup)
                # Rollback on (2) failure restores the source from the backup so
                # the file is never lost. A leftover .replacing.bak from a crash
                # between (2) and (3) is operator-cleanable; the new file is
                # already at the canonical name so DB consistency is preserved.
                BackupPath = LocalOriginalPath + '.replacing.bak'
                try:
                    if os.path.exists(BackupPath):
                        try:
                            os.remove(BackupPath)
                            LoggingService.LogInfo(
                                f"Removed pre-existing backup before same-slot replacement: {BackupPath}",
                                "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                            )
                        except Exception as PreBakEx:
                            ErrorMsg = (
                                f"Same-slot replacement: pre-existing backup {BackupPath} could not be cleared: {str(PreBakEx)}. "
                                f"Refusing to proceed."
                            )
                            LoggingService.LogError(ErrorMsg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                            return {'Success': False, 'ErrorMessage': ErrorMsg}

                    os.rename(LocalOriginalPath, BackupPath)
                    StepsCompleted.append(
                        f"Same-slot replacement: backed up source to {os.path.basename(BackupPath)}"
                    )
                    try:
                        os.rename(LocalStagedPath, TargetPath)
                        StepsCompleted.append(f"Renamed {os.path.basename(LocalStagedPath)} -> {os.path.basename(TargetPath)}")
                        LoggingService.LogInfo(
                            f"Same-slot replacement: dropped .inprogress suffix: {LocalStagedPath} -> {TargetPath}",
                            "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                        )
                    except Exception as RenameEx:
                        # Rollback: restore source from backup.
                        try:
                            os.rename(BackupPath, LocalOriginalPath)
                            LoggingService.LogWarning(
                                f"Same-slot replacement: restored source from backup after rename failure",
                                "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                            )
                        except Exception as RestoreEx:
                            LoggingService.LogException(
                                f"Same-slot replacement: rollback FAILED -- source at {BackupPath}, "
                                f"in-progress at {LocalStagedPath}. Manual recovery required.",
                                RestoreEx, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                            )
                        ErrorMsg = f"Same-slot replacement: failed to rename .inprogress to target: {str(RenameEx)}"
                        LoggingService.LogError(ErrorMsg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                        return {'Success': False, 'ErrorMessage': ErrorMsg}

                    # Step 3: delete backup. Best-effort.
                    try:
                        os.remove(BackupPath)
                        StepsCompleted.append(f"Removed backup {os.path.basename(BackupPath)}")
                    except Exception as DelBakEx:
                        LoggingService.LogWarning(
                            f"Same-slot replacement: backup {BackupPath} could not be deleted (operator cleanup): {str(DelBakEx)}",
                            "FileReplacementBusinessService", "_ProcessCompleteFileReplacement"
                        )
                except Exception as e:
                    ErrorMsg = f"Same-slot replacement: rename dance failed before published: {str(e)}"
                    LoggingService.LogError(ErrorMsg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                    return {'Success': False, 'ErrorMessage': ErrorMsg}
            else:
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
            UpdateResult = self._UpdateMediaFilesAfterReplacement(CanonicalOriginal, CanonicalNewPath,
                                                                   FFmpegCommand=FFmpegCommand)
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
                'Message': f'File replacement completed successfully. Steps: {", ".join(StepsCompleted)}',
                'CanonicalOriginalPath': CanonicalOriginal,
                'CanonicalNewPath': CanonicalNewPath,
            }

        except Exception as e:
            LoggingService.LogException(f"Exception in complete file replacement process", e,
                                      "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
            return {
                'Success': False,
                'ErrorMessage': f'Exception during file replacement: {str(e)}'
            }

    def _UpdateMediaFilesAfterReplacement(self, OriginalFilePath: str, NewFilePath: str,
                                          FFmpegCommand: Optional[str] = None) -> Dict[str, Any]:
        """Update MediaFiles table with new file information after successful replacement.

        FFmpegCommand (optional): the command that just produced the new file.
        When supplied, AudioNormalizationMode is derived from it
        (linear-loudnorm.feature.md C14 / BUG-0019).
        """
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

            # Derive IsInterlaced from FieldOrder on the re-probe. FFprobe's
            # field_order is 'progressive' for progressive content and one of
            # 'tt'/'bb'/'tb'/'bt'/'tff'/'bff' for interlaced. Stored as text
            # '0'/'1' to match the existing column convention.
            NewFieldOrder = (metadata.get('FieldOrder') or '').strip().lower()
            if NewFieldOrder:
                media_file.IsInterlaced = '0' if NewFieldOrder == 'progressive' else '1'

            # Derive AudioNormalizationMode from the just-run FFmpeg command
            # (linear-loudnorm.feature.md C14, BUG-0019). When the command is
            # not supplied (FinalizePartialReplacement crash recovery path),
            # leave the column untouched -- we don't know which mode ran.
            if FFmpegCommand:
                try:
                    from Features.AudioCompletion.AudioCompletionService import AudioCompletionService
                    DerivedMode = AudioCompletionService.DetectNormalizationMode(FFmpegCommand)
                    if DerivedMode is not None:
                        media_file.AudioNormalizationMode = DerivedMode
                except Exception as ModeEx:
                    LoggingService.LogException(
                        f"Failed to derive AudioNormalizationMode from command",
                        ModeEx, "FileReplacementBusinessService", "_UpdateMediaFilesAfterReplacement",
                    )

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

            # Clear operator-triggered NeedsReprobe flag. The post-replacement
            # FFprobe above already refreshed every metadata column the
            # MediaProbe batch would have refreshed, so leaving the flag set
            # would queue a second redundant probe on the next batch pass.
            # Direct UPDATE because NeedsReprobe is not on the SaveMediaFile
            # UPDATE column list.
            try:
                self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                    "UPDATE MediaFiles SET NeedsReprobe = FALSE WHERE Id = %s AND NeedsReprobe = TRUE",
                    (media_file.Id,),
                )
            except Exception as ReprobeEx:
                LoggingService.LogException(
                    f"Failed to clear NeedsReprobe after replacement for MediaFileId={media_file.Id}",
                    ReprobeEx, "FileReplacementBusinessService", "_UpdateMediaFilesAfterReplacement",
                )

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

    def _NotifyJellyfinOfReplacement(self, CanonicalOriginalPath: str, CanonicalNewPath: str) -> None:
        """Fire-and-forget Jellyfin notify after a successful file replacement.

        Owns jellyfin-push-notify.feature.md criterion 1 (FileReplacement
        choke point). Always sends a single `Modified` for the new path.
        `/Library/Media/Updated` is a directory-coalescing endpoint -- the
        ~60s same-folder scan naturally sweeps stale entries for the old
        filename without us needing to send a `Deleted` event.

        The prior shape (`Deleted(old)` + `Created(new)` batched in one
        POST when the path changed) caused Jellyfin to orphan the new
        item -- it lost the series/episode association when source and
        target shared the same extension (e.g. re-transcode of an
        existing `-mv.mp4`). Modified-only avoids that race; the
        coalescing sweep handles the stale-entry cleanup.
        """
        try:
            from Services.JellyfinNotifyService import NotifyJellyfin
            if not CanonicalNewPath:
                return
            Updates = [{'Path': CanonicalNewPath, 'UpdateType': 'Modified'}]
            NotifyJellyfin(Updates, self.DatabaseManager.DatabaseService)
        except Exception as Ex:
            LoggingService.LogException(
                "Jellyfin notify swallowed at FileReplacement boundary",
                Ex, "FileReplacementBusinessService", "_NotifyJellyfinOfReplacement",
            )

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
