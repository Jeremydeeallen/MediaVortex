from typing import Dict, Any, List
from Core.Logging.LoggingService import LoggingService


# directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C13
class ProcessSupervisor:
    """Tracks active ffmpeg processes; provides Stop/Cancel APIs for the worker shutdown + operator paths."""

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C13
    def __init__(self, DatabaseManager, ActiveJobsRef: List[Any]):
        """Inject DB + a shared reference to the worker's ActiveJobs list (so Stop/Cancel see the current set)."""
        self.DatabaseManager = DatabaseManager
        self.ActiveJobs = ActiveJobsRef

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C13
    def StopAllActive(self) -> Dict[str, Any]:
        """Stop every active ffmpeg subprocess started by this worker."""
        try:
            LoggingService.LogFunctionEntry("StopAllActive", "ProcessSupervisor")

            from Features.TranscodeJob.VideoTranscodingService import VideoTranscodingService
            VideoTranscoding = VideoTranscodingService()
            ActiveJobIds = VideoTranscoding.GetActiveJobs()

            for JobId in ActiveJobIds:
                try:
                    Result = VideoTranscoding.StopTranscoding(JobId)
                    if Result.get("Success", False):
                        LoggingService.LogInfo(f"Stopped transcoding process for job {JobId}", "ProcessSupervisor", "StopAllActive")
                    else:
                        LoggingService.LogWarning(f"Failed to stop transcoding process for job {JobId}: {Result.get('ErrorMessage', 'Unknown error')}", "ProcessSupervisor", "StopAllActive")
                except Exception as Ex:
                    LoggingService.LogException(f"Exception stopping transcoding process for job {JobId}", Ex, "ProcessSupervisor", "StopAllActive")

            LoggingService.LogInfo(f"Stopped {len(ActiveJobIds)} active transcoding processes", "ProcessSupervisor", "StopAllActive")
            return {"Success": True, "StoppedCount": len(ActiveJobIds)}

        except Exception as Ex:
            LoggingService.LogException("Exception stopping active transcoding processes", Ex, "ProcessSupervisor", "StopAllActive")
            return {"Success": False, "ErrorMessage": str(Ex)}

    # directive: perfect-solid-transcode-pipeline-phase3 | # see perfect-solid-transcode-pipeline-phase3.C13
    def CancelActive(self) -> Dict[str, Any]:
        """Cancel the currently-running transcode (operator-triggered)."""
        try:
            LoggingService.LogFunctionEntry("CancelActive", "ProcessSupervisor")

            RunningJobs = self.DatabaseManager.GetTranscodeQueueItemsByStatus("Running")
            if not RunningJobs:
                return {"Success": False, "ErrorMessage": "No active transcode job found"}

            Job = RunningJobs[0]
            JobId = Job.Id

            LoggingService.LogInfo(f"Cancelling active transcode job {JobId} for file: {Job.FileName}",
                                   "ProcessSupervisor", "CancelActive")

            from Services.ProcessManagementService import ProcessManagementService
            from Features.ServiceControl.ActiveJobRepository import ActiveJobRepository
            ProcessMgmt = ProcessManagementService()
            ActiveJobRepo = ActiveJobRepository()
            ActiveJobsFromRepo = ActiveJobRepo.GetActiveJobsByService(ActiveJobRepository.BuildActiveJobsQuery("TranscodeService"))
            for ActiveJob in ActiveJobsFromRepo:
                if ActiveJob.get('QueueId') == JobId:
                    Pid = ActiveJob.get('ProcessId')
                    if Pid:
                        try:
                            ProcessMgmt.KillProcess(Pid, Graceful=True)
                            LoggingService.LogInfo(f"Killed FFmpeg process PID {Pid} for job {JobId}",
                                                   "ProcessSupervisor", "CancelActive")
                        except Exception as Ex:
                            LoggingService.LogException(f"Error killing FFmpeg process PID {Pid}", Ex,
                                                        "ProcessSupervisor", "CancelActive")
                    ActiveJobRepo.CompleteActiveJob(ActiveJob['Id'], False, "Cancelled by user")
                    break

            self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                "UPDATE TranscodeAttempts SET Success = FALSE, ErrorMessage = 'Cancelled by user' "
                "WHERE MediaFileId = %s AND Success IS NULL", (Job.MediaFileId,))

            self.DatabaseManager.DatabaseService.ExecuteNonQuery(
                "DELETE FROM TranscodeProgress WHERE TranscodeAttemptId IN ("
                "SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s AND Success = FALSE)",
                (Job.MediaFileId,))

            self.DatabaseManager.DeleteTranscodeQueueItem(JobId)

            LoggingService.LogInfo(f"Successfully cancelled and removed transcode job {JobId} for file: {Job.FileName}",
                                   "ProcessSupervisor", "CancelActive")

            return {
                "Success": True,
                "Message": f"Transcode job cancelled and removed. File: {Job.FileName}",
                "JobId": JobId
            }

        except Exception as Ex:
            LoggingService.LogException("Error cancelling active transcode job", Ex,
                                        "ProcessSupervisor", "CancelActive")
            return {"Success": False, "ErrorMessage": str(Ex)}
