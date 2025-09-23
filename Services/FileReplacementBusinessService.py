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
            # Join with VMAFQueue to get the actual transcoded file paths
            query = '''
            SELECT ta.Id, ta.FilePath, ta.VMAF, ta.AttemptDate, ta.Success,
                   vq.TranscodedFilePath, vq.Status as VMAFStatus
            FROM TranscodeAttempts ta
            LEFT JOIN VMAFQueue vq ON ta.Id = vq.TranscodeAttemptId
            WHERE ta.VMAF IS NOT NULL 
            AND ta.VMAF >= 90
            AND ta.Success = 1
            AND vq.TranscodedFilePath IS NOT NULL
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
            
            # Get the actual transcoded file path from VMAFQueue
            vmaf_query = '''
            SELECT TranscodedFilePath FROM VMAFQueue 
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
            
            # Attempt file replacement
            replace_result = self.FileManager.ReplaceFile(transcode_attempt.FilePath, transcoded_path)
            
            if replace_result.get('Success', False):
                # Update transcode attempt to mark replacement as completed
                transcode_attempt.FileReplaced = True
                transcode_attempt.FileReplacementDate = datetime.now()
                self.DatabaseManager.SaveTranscodeAttempt(transcode_attempt)
                
                # Clean up temporary transcoded file and directory
                self._CleanupTranscodedFiles(transcoded_path)
                
                LoggingService.LogInfo(f"Successfully replaced file for attempt {TranscodeAttemptId}", 
                                     "FileReplacementBusinessService", "ProcessFileReplacement")
                
                return {
                    'Success': True,
                    'Message': 'File replacement completed successfully',
                    'OriginalFilePath': transcode_attempt.FilePath,
                    'TranscodedFilePath': transcoded_path,
                    'VMAFScore': transcode_attempt.VMAF
                }
            else:
                error_message = replace_result.get('ErrorMessage', 'Unknown error during file replacement')
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
            
            # Get the actual transcoded file path from VMAFQueue
            vmaf_query = '''
            SELECT TranscodedFilePath FROM VMAFQueue 
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
    
    def _CleanupTranscodedFiles(self, TranscodedFilePath: str) -> None:
        """Clean up temporary transcoded files and directories after successful replacement."""
        try:
            LoggingService.LogFunctionEntry("_CleanupTranscodedFiles", "FileReplacementBusinessService", TranscodedFilePath)
            
            # The transcoded file should already be moved to the original location by ReplaceFile
            # But we need to clean up the _transcoded directory if it's empty
            transcoded_dir = os.path.dirname(TranscodedFilePath)
            
            if os.path.exists(transcoded_dir) and transcoded_dir.endswith('_transcoded'):
                # Check if directory is empty
                try:
                    if not os.listdir(transcoded_dir):
                        # Directory is empty, remove it
                        os.rmdir(transcoded_dir)
                        LoggingService.LogInfo(f"Removed empty transcoded directory: {transcoded_dir}", 
                                             "FileReplacementBusinessService", "_CleanupTranscodedFiles")
                    else:
                        LoggingService.LogInfo(f"Transcoded directory not empty, keeping: {transcoded_dir}", 
                                             "FileReplacementBusinessService", "_CleanupTranscodedFiles")
                except Exception as dir_error:
                    LoggingService.LogWarning(f"Could not remove transcoded directory {transcoded_dir}: {str(dir_error)}", 
                                            "FileReplacementBusinessService", "_CleanupTranscodedFiles")
            
        except Exception as e:
            LoggingService.LogException(f"Exception during cleanup of transcoded files: {TranscodedFilePath}", e, 
                                      "FileReplacementBusinessService", "_CleanupTranscodedFiles")
