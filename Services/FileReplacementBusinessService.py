import os
from typing import Dict, Any, List, Optional
from datetime import datetime
from Models.TranscodeAttemptModel import TranscodeAttemptModel
from Repositories.DatabaseManager import DatabaseManager
from Services.FileManagerService import FileManagerService
from Services.LoggingService import LoggingService


class FileReplacementBusinessService:
    """Business service for manual file replacement operations."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None, 
                 FileManagerInstance: FileManagerService = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
        self.FileManager = FileManagerInstance or FileManagerService()
    
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

            original_path = file_paths_result[0]['OriginalPath']
            local_source_path = file_paths_result[0]['LocalSourcePath']
            transcoded_path = file_paths_result[0]['LocalOutputPath']

            # Validate files exist - use LocalSourcePath instead of network path
            local_source_exists = self.FileManager.ValidateFileExists(local_source_path)
            transcoded_exists = self.FileManager.ValidateFileExists(transcoded_path)
            network_transcoded_path = os.path.join(os.path.dirname(original_path), os.path.basename(transcoded_path))
            network_transcoded_exists = self.FileManager.ValidateFileExists(network_transcoded_path)

            # Check if transcoded file exists either locally or at network location
            if not transcoded_exists and not network_transcoded_exists:
                return {
                    'Success': False,
                    'ErrorMessage': 'Transcoded file not found at local or network location'
                }

            # If transcoded file is already at network location, just update the database
            if network_transcoded_exists:
                # File was already moved, just update the database
                transcode_attempt.FileReplaced = True
                transcode_attempt.FileReplacedDate = datetime.now()
                transcode_attempt.ReplacementType = "Auto"
                self.DatabaseManager.SaveTranscodeAttempt(transcode_attempt)

                return {
                    'Success': True,
                    'Message': 'File was already replaced and moved to network location',
                    'OriginalFilePath': original_path,
                    'TranscodedFilePath': network_transcoded_path,
                    'VMAFScore': VMAFScore,
                    'KeepSource': False,
                    'StepsCompleted': ['File already moved to network location', 'Updated database']
                }
            
            # If local source doesn't exist but transcoded file exists locally, proceed with move
            if not local_source_exists and transcoded_exists:
                # Local source was deleted but transcoded file wasn't moved yet
                # Proceed with moving the transcoded file to network location
                LoggingService.LogInfo(f"Local source file was deleted but transcoded file exists, proceeding with move to network location", 
                                     "FileReplacementBusinessService", "ProcessFileReplacementWithVMAF")
            
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
            self._ArchiveOriginalFileDetails(original_path, TranscodeAttemptId)
            
            # Process the complete 3-step file replacement
            replacement_result = self._ProcessCompleteFileReplacement(
                original_path, 
                transcoded_path, 
                keep_source,
                original_path
            )
            
            if replacement_result.get('Success', False):
                # Update transcode attempt to mark replacement as completed
                transcode_attempt.FileReplaced = True
                transcode_attempt.FileReplacedDate = datetime.now()
                transcode_attempt.ReplacementType = "Auto"
                self.DatabaseManager.SaveTranscodeAttempt(transcode_attempt)
                
                LoggingService.LogInfo(f"Successfully replaced file for attempt {TranscodeAttemptId}", 
                                     "FileReplacementBusinessService", "ProcessFileReplacementWithVMAF")
                
                return {
                    'Success': True,
                    'Message': 'File replacement completed successfully',
                    'OriginalFilePath': original_path,
                    'TranscodedFilePath': transcoded_path,
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

            original_path = file_paths_result[0]['OriginalPath']
            local_source_path = file_paths_result[0]['LocalSourcePath']
            transcoded_path = file_paths_result[0]['LocalOutputPath']

            # Validate files exist - use LocalSourcePath instead of network path
            local_source_exists = self.FileManager.ValidateFileExists(local_source_path)
            transcoded_exists = self.FileManager.ValidateFileExists(transcoded_path)
            network_transcoded_path = os.path.join(os.path.dirname(original_path), os.path.basename(transcoded_path))
            network_transcoded_exists = self.FileManager.ValidateFileExists(network_transcoded_path)

            # Check if transcoded file exists either locally or at network location
            if not transcoded_exists and not network_transcoded_exists:
                return {
                    'Success': False,
                    'ErrorMessage': 'Transcoded file not found at local or network location'
                }

            # If transcoded file is already at network location, just update the database
            if network_transcoded_exists:
                # File was already moved, just update the database
                transcode_attempt.FileReplaced = True
                transcode_attempt.FileReplacedDate = datetime.now()
                transcode_attempt.ReplacementType = "Auto"
                self.DatabaseManager.SaveTranscodeAttempt(transcode_attempt)

                return {
                    'Success': True,
                    'Message': 'File was already replaced and moved to network location',
                    'OriginalFilePath': original_path,
                    'TranscodedFilePath': network_transcoded_path,
                    'VMAFScore': transcode_attempt.VMAF,
                    'KeepSource': False,
                    'StepsCompleted': ['File already moved to network location', 'Updated database']
                }
            
            # If local source doesn't exist but transcoded file exists locally, proceed with move
            if not local_source_exists and transcoded_exists:
                # Local source was deleted but transcoded file wasn't moved yet
                # Proceed with moving the transcoded file to network location
                LoggingService.LogInfo(f"Local source file was deleted but transcoded file exists, proceeding with move to network location", 
                                     "FileReplacementBusinessService", "ProcessFileReplacement")
            
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
                    logMessage = f"File replacement rejected due to size: {original_path}. Original: {transcode_attempt.OldSizeBytes:,} bytes, Transcoded: {transcode_attempt.NewSizeBytes:,} bytes. VMAF: {vmafScore:.2f}"
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
            self._ArchiveOriginalFileDetails(original_path, TranscodeAttemptId)
            
            # Process the complete 3-step file replacement
            replacement_result = self._ProcessCompleteFileReplacement(
                original_path, 
                transcoded_path, 
                keep_source,
                original_path
            )
            
            if replacement_result.get('Success', False):
                # Update transcode attempt to mark replacement as completed
                transcode_attempt.FileReplaced = True
                transcode_attempt.FileReplacementDate = datetime.now()
                self.DatabaseManager.SaveTranscodeAttempt(transcode_attempt)
                
                LoggingService.LogInfo(f"Successfully replaced file for attempt {TranscodeAttemptId}", 
                                     "FileReplacementBusinessService", "ProcessFileReplacement")
                
                return {
                    'Success': True,
                    'Message': 'File replacement completed successfully',
                    'OriginalFilePath': original_path,
                    'TranscodedFilePath': transcoded_path,
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
        """Process the complete 3-step file replacement process.
        
        Args:
            OriginalFilePath: Network path to the original file (Z:\\videos\\...)
            TranscodedFilePath: Path to the transcoded file
            KeepSource: Whether to keep the original file (rename to .old) or delete it
            NetworkOriginalPath: Network path to the original file (same as OriginalFilePath for backward compatibility)
        """
        try:
            LoggingService.LogFunctionEntry("_ProcessCompleteFileReplacement", "FileReplacementBusinessService", 
                                          OriginalFilePath, TranscodedFilePath, KeepSource)
            
            steps_completed = []
            
            # Step 1: Delete the temporary local source file from c:\mediavortex\source
            # This is the local copy used for transcoding
            temp_source_path = f"C:\\MediaVortex\\Source\\{os.path.basename(OriginalFilePath)}"
            if os.path.exists(temp_source_path):
                try:
                    os.remove(temp_source_path)
                    steps_completed.append("Deleted temporary local source file")
                    LoggingService.LogInfo(f"Successfully deleted temporary local source file: {temp_source_path}", 
                                         "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                except Exception as e:
                    LoggingService.LogWarning(f"Could not delete temporary local source file {temp_source_path}: {str(e)}", 
                                            "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
            else:
                LoggingService.LogInfo(f"Temporary local source file not found (may have been cleaned up): {temp_source_path}", 
                                     "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
            
            # Step 2: Handle original file based on KeepSource setting
            # Check if original file exists before trying to delete/rename it
            if os.path.exists(OriginalFilePath):
                if KeepSource:
                    # Rename original file to .old
                    original_dir = os.path.dirname(OriginalFilePath)
                    original_filename = os.path.basename(OriginalFilePath)
                    original_name, original_ext = os.path.splitext(original_filename)
                    renamed_path = os.path.join(original_dir, f"{original_name}.old{original_ext}")
                    
                    try:
                        os.rename(OriginalFilePath, renamed_path)
                        steps_completed.append(f"Renamed original file to {renamed_path}")
                        LoggingService.LogInfo(f"Successfully renamed original file to: {renamed_path}", 
                                             "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                    except Exception as e:
                        error_msg = f"Failed to rename original file to .old: {str(e)}"
                        LoggingService.LogError(error_msg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                        return {'Success': False, 'ErrorMessage': error_msg}
                else:
                    # Delete original file
                    try:
                        os.remove(OriginalFilePath)
                        steps_completed.append("Deleted original file")
                        LoggingService.LogInfo(f"Successfully deleted original file: {OriginalFilePath}", 
                                             "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                    except Exception as e:
                        error_msg = f"Failed to delete original file: {str(e)}"
                        LoggingService.LogError(error_msg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                        return {'Success': False, 'ErrorMessage': error_msg}
            else:
                # Original file doesn't exist (was already deleted)
                steps_completed.append("Original file was already deleted")
                LoggingService.LogInfo(f"Original file was already deleted: {OriginalFilePath}", 
                                     "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
            
            # Step 3: Move transcoded file to original location
            try:
                import shutil
                # Move transcoded file to same directory as original network path, but keep transcoded filename
                if NetworkOriginalPath:
                    original_dir = os.path.dirname(NetworkOriginalPath)
                else:
                    original_dir = os.path.dirname(OriginalFilePath)
                transcoded_filename = os.path.basename(TranscodedFilePath)
                new_path = os.path.join(original_dir, transcoded_filename)
                shutil.move(TranscodedFilePath, new_path)
                steps_completed.append("Moved transcoded file to original location")
                LoggingService.LogInfo(f"Successfully moved transcoded file to: {new_path}", 
                                     "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
            except Exception as e:
                error_msg = f"Failed to move transcoded file to original location: {str(e)}"
                LoggingService.LogError(error_msg, "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                return {'Success': False, 'ErrorMessage': error_msg}
            
            
            # Step 4: Update MediaFiles table with new file information
            # Calculate the new file path where the transcoded file was moved
            if NetworkOriginalPath:
                original_dir = os.path.dirname(NetworkOriginalPath)
                original_file_path = NetworkOriginalPath
            else:
                original_dir = os.path.dirname(OriginalFilePath)
                original_file_path = OriginalFilePath
            transcoded_filename = os.path.basename(TranscodedFilePath)
            new_file_path = os.path.join(original_dir, transcoded_filename)
            update_result = self._UpdateMediaFilesAfterReplacement(original_file_path, new_file_path)
            if update_result.get('Success', False):
                steps_completed.append("Updated MediaFiles table")
                LoggingService.LogInfo("Successfully updated MediaFiles table", 
                                     "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
            else:
                LoggingService.LogWarning(f"Failed to update MediaFiles table: {update_result.get('ErrorMessage', 'Unknown error')}", 
                                        "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                # Don't fail the entire process for this, but log the warning
            
            return {
                'Success': True,
                'StepsCompleted': steps_completed,
                'Message': f'File replacement completed successfully. Steps: {", ".join(steps_completed)}'
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
            media_file.ContainerFormat = metadata.get('ContainerFormat')
            media_file.OverallBitrate = metadata.get('OverallBitrate')
            
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
    
