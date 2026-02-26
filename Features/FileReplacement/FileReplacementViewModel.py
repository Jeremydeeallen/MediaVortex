from typing import Dict, Any, List
from Features.FileReplacement.FileReplacementBusinessService import FileReplacementBusinessService
from Core.Logging.LoggingService import LoggingService


class FileReplacementViewModel:
    """ViewModel for file replacement operations."""

    def __init__(self, FileReplacementBusinessServiceInstance: FileReplacementBusinessService = None):
        self.FileReplacementBusinessService = FileReplacementBusinessServiceInstance or FileReplacementBusinessService()

    def GetFailedFileReplacements(self) -> Dict[str, Any]:
        """Get list of failed file replacements for the UI."""
        try:
            LoggingService.LogFunctionEntry("GetFailedFileReplacements", "FileReplacementViewModel")

            failed_replacements = self.FileReplacementBusinessService.GetFailedFileReplacements()

            return {
                'Success': True,
                'FailedReplacements': failed_replacements,
                'TotalCount': len(failed_replacements)
            }

        except Exception as e:
            LoggingService.LogException("Exception getting failed file replacements", e,
                                      "FileReplacementViewModel", "GetFailedFileReplacements")
            return {
                'Success': False,
                'ErrorMessage': f'Error getting failed file replacements: {str(e)}',
                'FailedReplacements': [],
                'TotalCount': 0
            }

    def ProcessFileReplacement(self, TranscodeAttemptId: int) -> Dict[str, Any]:
        """Process file replacement for a specific transcode attempt."""
        try:
            LoggingService.LogFunctionEntry("ProcessFileReplacement", "FileReplacementViewModel", TranscodeAttemptId)

            result = self.FileReplacementBusinessService.ProcessFileReplacement(TranscodeAttemptId)

            if result.get('Success', False):
                LoggingService.LogInfo(f"File replacement completed successfully for attempt {TranscodeAttemptId}",
                                     "FileReplacementViewModel", "ProcessFileReplacement")
            else:
                LoggingService.LogError(f"File replacement failed for attempt {TranscodeAttemptId}: {result.get('ErrorMessage', 'Unknown error')}",
                                      "FileReplacementViewModel", "ProcessFileReplacement")

            return result

        except Exception as e:
            LoggingService.LogException(f"Exception processing file replacement for attempt {TranscodeAttemptId}", e,
                                      "FileReplacementViewModel", "ProcessFileReplacement")
            return {
                'Success': False,
                'ErrorMessage': f'Exception during file replacement: {str(e)}'
            }

    def GetFileReplacementStatus(self, TranscodeAttemptId: int) -> Dict[str, Any]:
        """Get file replacement status for a specific transcode attempt."""
        try:
            LoggingService.LogFunctionEntry("GetFileReplacementStatus", "FileReplacementViewModel", TranscodeAttemptId)

            result = self.FileReplacementBusinessService.GetFileReplacementStatus(TranscodeAttemptId)

            return result

        except Exception as e:
            LoggingService.LogException(f"Exception getting file replacement status for attempt {TranscodeAttemptId}", e,
                                      "FileReplacementViewModel", "GetFileReplacementStatus")
            return {
                'Success': False,
                'ErrorMessage': f'Exception getting status: {str(e)}'
            }
