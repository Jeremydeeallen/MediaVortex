import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Repositories.DatabaseManager import DatabaseManager
from Services.FileManagerService import FileManagerService
from Core.Logging.LoggingService import LoggingService


class FileReplacementBusinessService:
    """Business service for manual file replacement operations."""

    def __init__(self, DatabaseManagerInstance: DatabaseManager = None,
                 FileManagerInstance: FileManagerService = None,
                 PathTranslation=None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FileManager = FileManagerInstance or FileManagerService()
        self.PathTranslation = PathTranslation

    def _ToLocalPath(self, CanonicalPath: str) -> str:
        """Translate a canonical DB path to a local filesystem path using PathTranslation if available."""
        if self.PathTranslation and CanonicalPath:
            return self.PathTranslation.ToLocalPath(CanonicalPath)
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

    def ProcessFileReplacementWithVMAF(self, TranscodeAttemptId: int, VMAFScore: float, BypassVMAFCheck: bool = True) -> Dict[str, Any]:
        """Process file replacement with a specific VMAF score (used by auto-replace to avoid race conditions)."""
        try:
            LoggingService.LogFunctionEntry("ProcessFileReplacementWithVMAF", "FileReplacementBusinessService", TranscodeAttemptId, VMAFScore)

            # Get the transcode attempt
            transcode_attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not transcode_attempt:
                return {
                    'Success': False,
                    'ErrorMessage': f'Transcode attempt {TranscodeAttemptId} not found'
                }

            # Check if file was already replaced
            if transcode_attempt.FileReplaced:
                return {
                    'Success': False,
                    'ErrorMessage': f'File for transcode attempt {TranscodeAttemptId} was already replaced on {transcode_attempt.FileReplacedDate}'
                }

            # Get the file paths from TemporaryFilePaths
            file_paths_query = '''
            SELECT OriginalPath, LocalSourcePath, LocalOutputPath FROM TemporaryFilePaths
            WHERE TranscodeAttemptId = %s
            '''
            file_paths_result = self.DatabaseManager.DatabaseService.ExecuteQuery(file_paths_query, (TranscodeAttemptId,))

            if not file_paths_result:
                return {
                    'Success': False,
                    'ErrorMessage': f'No temporary file path found for transcode attempt {TranscodeAttemptId}'
                }

            OriginalPath = file_paths_result[0]['OriginalPath']
            TranscodedPath = file_paths_result[0]['LocalOutputPath']

            # Translate canonical paths to local for filesystem validation
            LocalTranscodedPath = self._ToLocalPath(TranscodedPath)

            # Check if transcoded file exists (using translated local path)
            if not self.FileManager.ValidateFileExists(LocalTranscodedPath):
                return {
                    'Success': False,
                    'ErrorMessage': f'Transcoded file not found at: {LocalTranscodedPath}'
                }

            # Check if VMAF score meets threshold (unless bypassed for manual replacement)
            if not BypassVMAFCheck:
                vmaf_thresholds = self.DatabaseManager.GetVMAFThresholds()
                if not vmaf_thresholds:
                    return {
                        'Success': False,
                        'ErrorMessage': 'Could not retrieve VMAF thresholds from system settings'
                    }

                min_threshold = vmaf_thresholds.get('MinThreshold')
                max_threshold = vmaf_thresholds.get('MaxThreshold')

                if min_threshold is None or max_threshold is None:
                    return {
                        'Success': False,
                        'ErrorMessage': 'VMAF thresholds not found in database'
                    }

                if not VMAFScore or VMAFScore < min_threshold or VMAFScore > max_threshold:
                    return {
                        'Success': False,
                        'ErrorMessage': f'VMAF score {VMAFScore} does not meet quality threshold ({min_threshold}-{max_threshold})'
                    }
            else:
                LoggingService.LogInfo(f"Bypassing VMAF threshold check for manual replacement of attempt {TranscodeAttemptId}",
                                     "FileReplacementBusinessService", "ProcessFileReplacementWithVMAF")

            # CRITICAL: Check file size - never replace smaller file with larger file
            # This is especially important when CRF is lowered (higher quality = larger file size)
            if transcode_attempt.NewSizeBytes is not None and transcode_attempt.OldSizeBytes is not None:
                if transcode_attempt.NewSizeBytes >= transcode_attempt.OldSizeBytes:
                    errorMsg = f"Cannot replace file: transcoded file is not smaller than original (New: {transcode_attempt.NewSizeBytes:,} bytes >= Old: {transcode_attempt.OldSizeBytes:,} bytes)"

                    # Log rejection at Warning level
                    logMessage = f"File replacement rejected due to size: {original_path}. Original: {transcode_attempt.OldSizeBytes:,} bytes, Transcoded: {transcode_attempt.NewSizeBytes:,} bytes. VMAF: {VMAFScore:.2f}"
                    LoggingService.LogWarning(logMessage, "FileReplacementBusinessService", "ProcessFileReplacementWithVMAF")

                    return {
                        'Success': False,
                        'ErrorMessage': errorMsg
                    }

            # Get KeepSource setting from profile threshold
            keep_source = self.DatabaseManager.GetKeepSourceSetting(transcode_attempt.Id)
            if keep_source is None:
                return {
                    'Success': False,
                    'ErrorMessage': 'Could not determine KeepSource setting for this transcode attempt'
                }

            # Archive original file details before replacement
            self._ArchiveOriginalFileDetails(OriginalPath, TranscodeAttemptId)

            # Process file replacement
            replacement_result = self._ProcessCompleteFileReplacement(
                OriginalPath,
                TranscodedPath,
                keep_source,
                OriginalPath
            )

            if replacement_result.get('Success', False):
                # Update transcode attempt to mark replacement as completed
                transcode_attempt.FileReplaced = True
                transcode_attempt.FileReplacedDate = datetime.now()
                transcode_attempt.ReplacementType = "Auto"
                self.DatabaseManager.SaveTranscodeAttempt(transcode_attempt)

                # Clean up TemporaryFilePaths
                self._CleanupTemporaryFilePaths(TranscodeAttemptId)

                LoggingService.LogInfo(f"Successfully replaced file for attempt {TranscodeAttemptId}",
                                     "FileReplacementBusinessService", "ProcessFileReplacementWithVMAF")

                return {
                    'Success': True,
                    'Message': 'File replacement completed successfully',
                    'OriginalFilePath': OriginalPath,
                    'TranscodedFilePath': TranscodedPath,
                    'VMAFScore': VMAFScore,
                    'KeepSource': keep_source,
                    'StepsCompleted': replacement_result.get('StepsCompleted', [])
                }
            else:
                error_message = replacement_result.get('ErrorMessage', 'Unknown error during file replacement')
                LoggingService.LogError(f"File replacement failed for attempt {TranscodeAttemptId}: {error_message}",
                                      "FileReplacementBusinessService", "ProcessFileReplacementWithVMAF")

                return {
                    'Success': False,
                    'ErrorMessage': error_message
                }

        except Exception as e:
            LoggingService.LogException(f"Exception processing file replacement for attempt {TranscodeAttemptId}", e,
                                      "FileReplacementBusinessService", "ProcessFileReplacementWithVMAF")
            return {
                'Success': False,
                'ErrorMessage': f'Exception during file replacement: {str(e)}'
            }

    def ProcessFileReplacement(self, TranscodeAttemptId: int, BypassVMAFCheck: bool = True) -> Dict[str, Any]:
        """Process manual file replacement for a specific transcode attempt.

        Args:
            TranscodeAttemptId: ID of the transcode attempt to replace
            BypassVMAFCheck: If True, bypass VMAF threshold check (default for manual replacement)
        """
        try:
            LoggingService.LogFunctionEntry("ProcessFileReplacement", "FileReplacementBusinessService", TranscodeAttemptId)

            # Get the transcode attempt
            transcode_attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not transcode_attempt:
                return {
                    'Success': False,
                    'ErrorMessage': f'Transcode attempt {TranscodeAttemptId} not found'
                }

            # Check if file was already replaced
            if transcode_attempt.FileReplaced:
                return {
                    'Success': False,
                    'ErrorMessage': f'File for transcode attempt {TranscodeAttemptId} was already replaced on {transcode_attempt.FileReplacedDate}'
                }

            # Get the file paths from TemporaryFilePaths
            file_paths_query = '''
            SELECT OriginalPath, LocalSourcePath, LocalOutputPath FROM TemporaryFilePaths
            WHERE TranscodeAttemptId = %s
            '''
            file_paths_result = self.DatabaseManager.DatabaseService.ExecuteQuery(file_paths_query, (TranscodeAttemptId,))

            if not file_paths_result:
                return {
                    'Success': False,
                    'ErrorMessage': f'No temporary file path found for transcode attempt {TranscodeAttemptId}'
                }

            OriginalPath = file_paths_result[0]['OriginalPath']
            TranscodedPath = file_paths_result[0]['LocalOutputPath']

            # Translate canonical paths to local for filesystem validation
            LocalTranscodedPath = self._ToLocalPath(TranscodedPath)

            # Check if transcoded file exists (using translated local path)
            if not self.FileManager.ValidateFileExists(LocalTranscodedPath):
                return {
                    'Success': False,
                    'ErrorMessage': f'Transcoded file not found at: {LocalTranscodedPath}'
                }

            # Check if VMAF score meets threshold (unless bypassed for manual replacement)
            if not BypassVMAFCheck:
                vmaf_thresholds = self.DatabaseManager.GetVMAFThresholds()
                if not vmaf_thresholds:
                    return {
                        'Success': False,
                        'ErrorMessage': 'Could not retrieve VMAF thresholds from system settings'
                    }

                min_threshold = vmaf_thresholds.get('MinThreshold')
                max_threshold = vmaf_thresholds.get('MaxThreshold')

                if min_threshold is None or max_threshold is None:
                    return {
                        'Success': False,
                        'ErrorMessage': 'VMAF thresholds not found in database'
                    }

                if not transcode_attempt.VMAF or transcode_attempt.VMAF < min_threshold or transcode_attempt.VMAF > max_threshold:
                    return {
                        'Success': False,
                        'ErrorMessage': f'VMAF score {transcode_attempt.VMAF} does not meet quality threshold ({min_threshold}-{max_threshold})'
                    }
            else:
                LoggingService.LogInfo(f"Bypassing VMAF threshold check for manual replacement of attempt {TranscodeAttemptId}",
                                     "FileReplacementBusinessService", "ProcessFileReplacement")

            # CRITICAL: Check file size - never replace smaller file with larger file
            # This is especially important when CRF is lowered (higher quality = larger file size)
            # Skip this check for remux jobs (container change may produce similar or slightly larger file)
            isRemux = transcode_attempt.ProfileName in ('Remux', 'SubtitleFix')
            if not isRemux and transcode_attempt.NewSizeBytes is not None and transcode_attempt.OldSizeBytes is not None:
                if transcode_attempt.NewSizeBytes >= transcode_attempt.OldSizeBytes:
                    errorMsg = f"Cannot replace file: transcoded file is not smaller than original (New: {transcode_attempt.NewSizeBytes:,} bytes >= Old: {transcode_attempt.OldSizeBytes:,} bytes)"

                    # Log rejection at Warning level
                    vmafScore = transcode_attempt.VMAF or 0.0
                    logMessage = f"File replacement rejected due to size: {OriginalPath}. Original: {transcode_attempt.OldSizeBytes:,} bytes, Transcoded: {transcode_attempt.NewSizeBytes:,} bytes. VMAF: {vmafScore:.2f}"
                    LoggingService.LogWarning(logMessage, "FileReplacementBusinessService", "ProcessFileReplacement")

                    return {
                        'Success': False,
                        'ErrorMessage': errorMsg
                    }

            # Get KeepSource setting from profile threshold
            keep_source = self.DatabaseManager.GetKeepSourceSetting(transcode_attempt.Id)
            if keep_source is None:
                return {
                    'Success': False,
                    'ErrorMessage': 'Could not determine KeepSource setting for this transcode attempt'
                }

            # Archive original file details before replacement
            self._ArchiveOriginalFileDetails(OriginalPath, TranscodeAttemptId)

            # Process file replacement
            replacement_result = self._ProcessCompleteFileReplacement(
                OriginalPath,
                TranscodedPath,
                keep_source,
                OriginalPath
            )

            if replacement_result.get('Success', False):
                # Update transcode attempt to mark replacement as completed
                transcode_attempt.FileReplaced = True
                transcode_attempt.FileReplacementDate = datetime.now()
                self.DatabaseManager.SaveTranscodeAttempt(transcode_attempt)

                # Clean up TemporaryFilePaths
                self._CleanupTemporaryFilePaths(TranscodeAttemptId)

                LoggingService.LogInfo(f"Successfully replaced file for attempt {TranscodeAttemptId}",
                                     "FileReplacementBusinessService", "ProcessFileReplacement")

                return {
                    'Success': True,
                    'Message': 'File replacement completed successfully',
                    'OriginalFilePath': OriginalPath,
                    'TranscodedFilePath': TranscodedPath,
                    'VMAFScore': transcode_attempt.VMAF,
                    'KeepSource': keep_source,
                    'StepsCompleted': replacement_result.get('StepsCompleted', [])
                }
            else:
                error_message = replacement_result.get('ErrorMessage', 'Unknown error during file replacement')
                LoggingService.LogError(f"File replacement failed for attempt {TranscodeAttemptId}: {error_message}",
                                      "FileReplacementBusinessService", "ProcessFileReplacement")

                return {
                    'Success': False,
                    'ErrorMessage': error_message
                }

        except Exception as e:
            LoggingService.LogException(f"Exception processing file replacement for attempt {TranscodeAttemptId}", e,
                                      "FileReplacementBusinessService", "ProcessFileReplacement")
            return {
                'Success': False,
                'ErrorMessage': f'Exception during file replacement: {str(e)}'
            }

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


    def _ProcessCompleteFileReplacement(self, OriginalFilePath: str, TranscodedFilePath: str, KeepSource: bool, NetworkOriginalPath: str = None) -> Dict[str, Any]:
        """Process file replacement: delete original, update DB.

        All paths from the DB are canonical (T:\\...). PathTranslation converts them
        to local mount paths before any filesystem operation.

        Args:
            OriginalFilePath: Canonical path to the original file
            TranscodedFilePath: Canonical path to the transcoded file
            KeepSource: Whether to keep the original file (rename to .old) or delete it
            NetworkOriginalPath: Canonical path for DB lookups (same as OriginalFilePath)
        """
        try:
            # Translate canonical paths to local filesystem paths
            LocalOriginalPath = self._ToLocalPath(OriginalFilePath)
            LocalTranscodedPath = self._ToLocalPath(TranscodedFilePath)

            LoggingService.LogFunctionEntry("_ProcessCompleteFileReplacement", "FileReplacementBusinessService",
                                          LocalOriginalPath, LocalTranscodedPath, KeepSource)

            StepsCompleted = []

            # Step 1: Handle original file based on KeepSource setting
            if os.path.exists(LocalOriginalPath):
                if KeepSource:
                    OriginalDir = os.path.dirname(LocalOriginalPath)
                    OriginalFilename = os.path.basename(LocalOriginalPath)
                    OriginalName, OriginalExt = os.path.splitext(OriginalFilename)
                    RenamedPath = os.path.join(OriginalDir, f"{OriginalName}.old{OriginalExt}")

                    try:
                        os.rename(LocalOriginalPath, RenamedPath)
                        StepsCompleted.append(f"Renamed original file to {RenamedPath}")
                        LoggingService.LogInfo(f"Successfully renamed original file to: {RenamedPath}",
                                             "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                    except Exception as e:
                        ErrorMsg = f"Failed to rename original file to .old: {str(e)}"
                        LoggingService.LogError(ErrorMsg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                        return {'Success': False, 'ErrorMessage': ErrorMsg}
                else:
                    try:
                        os.remove(LocalOriginalPath)
                        StepsCompleted.append("Deleted original file")
                        LoggingService.LogInfo(f"Successfully deleted original file: {LocalOriginalPath}",
                                             "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                    except Exception as e:
                        ErrorMsg = f"Failed to delete original file: {str(e)}"
                        LoggingService.LogError(ErrorMsg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                        return {'Success': False, 'ErrorMessage': ErrorMsg}
            else:
                StepsCompleted.append("Original file was already deleted")
                LoggingService.LogInfo(f"Original file was already deleted: {LocalOriginalPath}",
                                     "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")

            # Step 2: Move transcoded file to original directory if needed (InPlace = already there)
            OriginalDir = os.path.dirname(LocalOriginalPath)
            TranscodedFilename = os.path.basename(LocalTranscodedPath)
            TargetPath = os.path.join(OriginalDir, TranscodedFilename)

            if os.path.normpath(LocalTranscodedPath) != os.path.normpath(TargetPath):
                try:
                    import shutil
                    shutil.move(LocalTranscodedPath, TargetPath)
                    StepsCompleted.append(f"Moved transcoded file to {TargetPath}")
                    LoggingService.LogInfo(f"Successfully moved transcoded file to: {TargetPath}",
                                         "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                except Exception as e:
                    ErrorMsg = f"Failed to move transcoded file to original location: {str(e)}"
                    LoggingService.LogError(ErrorMsg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                    return {'Success': False, 'ErrorMessage': ErrorMsg}
            else:
                StepsCompleted.append("Transcoded file already in correct location (InPlace)")
                LoggingService.LogInfo("Transcoded file already in correct location (InPlace output mode)",
                                     "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")

            # Step 3: Update MediaFiles table with new file information
            # Use canonical path for DB lookup, canonical target path for the new FilePath
            CanonicalOriginal = NetworkOriginalPath or OriginalFilePath
            CanonicalNewPath = os.path.join(os.path.dirname(CanonicalOriginal), TranscodedFilename)
            UpdateResult = self._UpdateMediaFilesAfterReplacement(CanonicalOriginal, CanonicalNewPath)
            if UpdateResult.get('Success', False):
                StepsCompleted.append("Updated MediaFiles table")
                LoggingService.LogInfo("Successfully updated MediaFiles table",
                                     "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
            else:
                LoggingService.LogWarning(f"Failed to update MediaFiles table: {UpdateResult.get('ErrorMessage', 'Unknown error')}",
                                        "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")

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
            metadata = self.FileManager.ExtractMediaMetadata(NewFilePath)
            if not metadata.get('Success', False):
                return {
                    'Success': False,
                    'ErrorMessage': f'Failed to extract metadata from transcoded file: {metadata.get("ErrorMessage", "Unknown error")}'
                }

            # Update the MediaFile with new file path and filename
            media_file.FilePath = NewFilePath  # Update to new file path
            media_file.FileName = os.path.basename(NewFilePath)  # Update to new filename

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

            # Derive ResolutionCategory from new Resolution
            NewResolution = media_file.Resolution or ''
            if NewResolution and 'x' in NewResolution:
                try:
                    Height = int(NewResolution.split('x')[1])
                    if Height >= 2160:
                        media_file.ResolutionCategory = "2160p"
                    elif Height >= 1080:
                        media_file.ResolutionCategory = "1080p"
                    elif Height >= 720:
                        media_file.ResolutionCategory = "720p"
                    else:
                        media_file.ResolutionCategory = "480p"
                except (ValueError, IndexError):
                    pass

            # Set TranscodedByMediaVortex to True
            media_file.TranscodedByMediaVortex = True

            # Update LastScannedDate to current time
            from datetime import datetime
            media_file.LastScannedDate = datetime.now()

            # Save the updated MediaFile
            self.DatabaseManager.SaveMediaFile(media_file)

            LoggingService.LogInfo(f"Successfully updated MediaFiles record for: {OriginalFilePath}",
                                 "FileReplacementBusinessService", "_UpdateMediaFilesAfterReplacement")

            return {
                'Success': True,
                'Message': 'MediaFiles table updated successfully'
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
