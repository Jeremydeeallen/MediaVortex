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
            
            # Get transcoded files that passed VMAF but may have failed replacement
            # Join with QualityTestingQueue to get the actual transcoded file paths
            query = '''
            SELECT ta.Id, ta.FilePath, ta.VMAF, ta.AttemptDate, ta.Success,
                   qtq.TranscodedFilePath, qtq.Status as VMAFStatus
            FROM TranscodeAttempts ta
            LEFT JOIN QualityTestingQueue qtq ON ta.Id = qtq.TranscodeAttemptId
            WHERE ta.VMAF IS NOT NULL 
            AND ta.VMAF >= 90
            AND ta.Success = 1
            AND qtq.TranscodedFilePath IS NOT NULL
            ORDER BY ta.AttemptDate DESC
            LIMIT 20
            '''
            
            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
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
        """Process manual file replacement for a specific transcode attempt."""
        try:
            LoggingService.LogFunctionEntry("ProcessFileReplacement", "FileReplacementBusinessService", TranscodeAttemptId)
            
            # Get the transcode attempt
            transcode_attempt = self.DatabaseManager.GetTranscodeAttemptById(TranscodeAttemptId)
            if not transcode_attempt:
                return {
                    'Success': False,
                    'ErrorMessage': f'Transcode attempt {TranscodeAttemptId} not found'
                }
            
            # Get the actual transcoded file path from QualityTestingQueue
            vmaf_query = '''
            SELECT TranscodedFilePath FROM QualityTestingQueue 
            WHERE TranscodeAttemptId = ?
            '''
            vmaf_result = self.DatabaseManager.DatabaseService.ExecuteQuery(vmaf_query, (TranscodeAttemptId,))
            
            if not vmaf_result:
                return {
                    'Success': False,
                    'ErrorMessage': f'No VMAF queue entry found for transcode attempt {TranscodeAttemptId}'
                }
            
            transcoded_path = vmaf_result[0]['TranscodedFilePath']
            
            # Validate files exist
            if not self.FileManager.ValidateFileExists(transcode_attempt.FilePath):
                return {
                    'Success': False,
                    'ErrorMessage': 'Original file not found'
                }
            
            if not self.FileManager.ValidateFileExists(transcoded_path):
                return {
                    'Success': False,
                    'ErrorMessage': 'Transcoded file not found'
                }
            
            # Check if VMAF score meets threshold
            if not transcode_attempt.VMAF or transcode_attempt.VMAF < 90:
                return {
                    'Success': False,
                    'ErrorMessage': f'VMAF score {transcode_attempt.VMAF} does not meet quality threshold (90)'
                }
            
            # Get KeepSource setting from profile threshold
            keep_source = self.DatabaseManager.GetKeepSourceSetting(transcode_attempt.Id)
            if keep_source is None:
                return {
                    'Success': False,
                    'ErrorMessage': 'Could not determine KeepSource setting for this transcode attempt'
                }
            
            # Process the complete 3-step file replacement
            replacement_result = self._ProcessCompleteFileReplacement(
                transcode_attempt.FilePath, 
                transcoded_path, 
                keep_source
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
                    'OriginalFilePath': transcode_attempt.FilePath,
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
            WHERE TranscodeAttemptId = ?
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
    
    
    def _ProcessCompleteFileReplacement(self, OriginalFilePath: str, TranscodedFilePath: str, KeepSource: bool) -> Dict[str, Any]:
        """Process the complete 3-step file replacement process."""
        try:
            LoggingService.LogFunctionEntry("_ProcessCompleteFileReplacement", "FileReplacementBusinessService", 
                                          OriginalFilePath, TranscodedFilePath, KeepSource)
            
            steps_completed = []
            
            # Step 1: Delete the temporary original file from c:\mediavortex\source
            temp_source_path = f"C:\\MediaVortex\\Source\\{os.path.basename(OriginalFilePath)}"
            if os.path.exists(temp_source_path):
                try:
                    os.remove(temp_source_path)
                    steps_completed.append("Deleted temporary source file")
                    LoggingService.LogInfo(f"Successfully deleted temporary source file: {temp_source_path}", 
                                         "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
                except Exception as e:
                    LoggingService.LogWarning(f"Could not delete temporary source file {temp_source_path}: {str(e)}", 
                                            "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
            else:
                LoggingService.LogInfo(f"Temporary source file not found (may have been cleaned up): {temp_source_path}", 
                                     "FileReplacementBusinessService", "_ProcessCompleteFileReplacement")
            
            # Step 2: Handle original file based on KeepSource setting
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
            
            # Step 3: Move transcoded file to original location
            try:
                import shutil
                # Move transcoded file to same directory as original, but keep transcoded filename
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
            original_dir = os.path.dirname(OriginalFilePath)
            transcoded_filename = os.path.basename(TranscodedFilePath)
            new_file_path = os.path.join(original_dir, transcoded_filename)
            update_result = self._UpdateMediaFilesAfterReplacement(OriginalFilePath, new_file_path)
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
    
