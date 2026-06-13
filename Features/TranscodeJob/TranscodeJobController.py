from flask import Blueprint, request, jsonify, render_template
from typing import Dict, Any
from ViewModels.ActivityViewModel import ActivityViewModel
from Core.Logging.LoggingService import LoggingService
from Features.TranscodeJob.TranscodingViewModel import TranscodingViewModel
from Services.ServiceStatusHelperService import ServiceStatusHelperService


# Create Blueprint for transcoding job routes
TranscodeJobBlueprint = Blueprint('TranscodeJob', __name__, url_prefix='/api/Transcode')

# Create shared service instances
SharedTranscodingService = TranscodingViewModel()
SharedStatusHelper = ServiceStatusHelperService()


@TranscodeJobBlueprint.route('/Start', methods=['POST'])
def StartTranscoding():
    """Start transcoding jobs via direct ServiceStatus update."""
    try:
        LoggingService.LogFunctionEntry("StartTranscoding", "TranscodeJobController")

        # Get parameters from request
        data = request.get_json() or {}
        maxConcurrentJobs = data.get('MaxConcurrentJobs', 1)

        # Validate parameters
        if not isinstance(maxConcurrentJobs, int) or maxConcurrentJobs < 1:
            errorMsg = "MaxConcurrentJobs must be a positive integer"
            LoggingService.LogError(errorMsg, "TranscodeJobController", "StartTranscoding")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        # Update ServiceStatus directly
        success = SharedStatusHelper.SetTranscodingStarted(maxConcurrentJobs)

        if success:
            LoggingService.LogInfo(f"Set transcoding status to started with {maxConcurrentJobs} concurrent jobs",
                                 "TranscodeJobController", "StartTranscoding")
            return jsonify({
                "Success": True,
                "Message": "Transcoding started successfully",
                "MaxConcurrentJobs": maxConcurrentJobs,
                "Status": "Started"
            })
        else:
            LoggingService.LogError("Failed to start transcoding", "TranscodeJobController", "StartTranscoding")
            return jsonify({
                "Success": False,
                "ErrorMessage": "Failed to start transcoding"
            }), 500

    except Exception as e:
        errorMsg = f"Exception starting transcoding: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "StartTranscoding")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeJobBlueprint.route('/TerminateNow', methods=['POST'])
def TerminateTranscodingNow():
    """Terminate transcoding immediately - kill processes and reset queue."""
    try:
        LoggingService.LogFunctionEntry("TerminateTranscodingNow", "TranscodeJobController")

        # Step 1: Immediately set status to Stopped to prevent restart
        SharedStatusHelper.SetTranscodingStopped()

        # Step 2: Terminate any active transcoding processes immediately
        try:
            from Features.TranscodeJob.VideoTranscodingService import VideoTranscodingService
            videoService = VideoTranscodingService()
            activeJobs = videoService.GetActiveJobs()

            for jobId in activeJobs:
                LoggingService.LogInfo(f"Terminating active transcoding process for job {jobId}",
                                     "TranscodeJobController", "TerminateTranscodingNow")
                videoService.StopTranscoding(jobId)
        except Exception as e:
            LoggingService.LogException("Error terminating active transcoding processes", e, "TranscodeJobController", "TerminateTranscodingNow")

        # Step 3: Reset any running jobs to Pending status
        try:
            from Services.QueueManagementService import QueueManagementService
            queueManager = QueueManagementService()
            resetResult = queueManager.ResetRunningJobsToPending("TranscodeQueue", "Transcoding terminated by user - immediate stop request")

            if not resetResult.get("Success", False):
                LoggingService.LogWarning(f"Failed to reset running jobs: {resetResult.get('ErrorMessage', 'Unknown error')}",
                                        "TranscodeJobController", "TerminateTranscodingNow")
        except Exception as e:
            LoggingService.LogException("Error resetting running jobs", e, "TranscodeJobController", "TerminateTranscodingNow")

        # Step 4: Update progress records for cancelled jobs
        try:
            from Repositories.DatabaseManager import DatabaseManager
            dbManager = DatabaseManager()

            # Update any running transcode attempts to cancelled (Success=NULL means in-progress)
            updateQuery = """
                UPDATE TranscodeAttempts
                SET Success = FALSE,
                    ErrorMessage = 'Transcoding terminated by user - immediate stop request'
                WHERE Success IS NULL
            """
            dbManager.DatabaseService.ExecuteNonQuery(updateQuery)

            # Update any running progress records to cancelled
            progressQuery = """
                UPDATE TranscodeProgress
                SET Status = 'Cancelled'
                WHERE Status = 'Running'
            """
            dbManager.DatabaseService.ExecuteNonQuery(progressQuery)

        except Exception as e:
            LoggingService.LogException("Error updating progress records", e, "TranscodeJobController", "TerminateTranscodingNow")

        LoggingService.LogInfo("Transcoding terminated immediately with process kill and queue reset",
                             "TranscodeJobController", "TerminateTranscodingNow")
        return jsonify({
            "Success": True,
            "Message": "Transcoding terminated immediately",
            "Status": "Stopped"
        })

    except Exception as e:
        errorMsg = f"Exception terminating transcoding: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "TerminateTranscodingNow")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeJobBlueprint.route('/Status', methods=['GET'])
def GetTranscodingStatus():
    """Get current transcoding status and progress."""
    try:
        LoggingService.LogFunctionEntry("GetTranscodingStatus", "TranscodeJobController")

        # Create ViewModel instance
        viewModel = ActivityViewModel(TranscodingService=SharedTranscodingService)

        # Get status
        result = viewModel.GetTranscodingStatus()

        if result.get("Success", False):
            # Reduced logging verbosity for routine status checks
            return jsonify(result)
        else:
            LoggingService.LogError(f"Failed to get transcoding status: {result.get('ErrorMessage', 'Unknown error')}", "TranscodeJobController", "GetTranscodingStatus")
            return jsonify(result), 500

    except Exception as e:
        errorMsg = f"Exception getting transcoding status: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "GetTranscodingStatus")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeJobBlueprint.route('/History', methods=['GET'])
def GetTranscodingHistory():
    """Get transcoding history."""
    try:
        LoggingService.LogFunctionEntry("GetTranscodingHistory", "TranscodeJobController")

        # Get parameters from request
        limit = request.args.get('Limit', 50, type=int)

        # Validate parameters
        if not isinstance(limit, int) or limit < 1 or limit > 500:
            errorMsg = "Limit must be an integer between 1 and 500"
            LoggingService.LogError(errorMsg, "TranscodeJobController", "GetTranscodingHistory")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        # Create ViewModel instance
        viewModel = ActivityViewModel(TranscodingService=SharedTranscodingService)

        # Get history
        result = viewModel.GetTranscodingHistory(limit)

        if result.get("Success", False):
            LoggingService.LogInfo(f"Retrieved {result.get('Count', 0)} history items", "TranscodeJobController", "GetTranscodingHistory")
            return jsonify(result)
        else:
            LoggingService.LogError(f"Failed to get transcoding history: {result.get('ErrorMessage', 'Unknown error')}", "TranscodeJobController", "GetTranscodingHistory")
            return jsonify(result), 500

    except Exception as e:
        errorMsg = f"Exception getting transcoding history: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "GetTranscodingHistory")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeJobBlueprint.route('/RecentAttempts', methods=['GET'])
def GetRecentAttempts():
    """Get recent transcoding attempts."""
    try:
        LoggingService.LogFunctionEntry("GetRecentAttempts", "TranscodeJobController")

        # Get parameters from request
        limit = request.args.get('Limit', 20, type=int)

        # Validate parameters
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            errorMsg = "Limit must be an integer between 1 and 100"
            LoggingService.LogError(errorMsg, "TranscodeJobController", "GetRecentAttempts")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        # Create ViewModel instance
        viewModel = ActivityViewModel(TranscodingService=SharedTranscodingService)

        # Get recent attempts using GetTranscodingHistory
        historyResult = viewModel.GetTranscodingHistory(limit)

        if historyResult.get("Success", False):
            result = {
                "Success": True,
                "RecentAttempts": historyResult.get("History", []),
                "Count": historyResult.get("Count", 0)
            }
        else:
            result = {
                "Success": False,
                "ErrorMessage": historyResult.get("ErrorMessage", "Failed to get recent attempts")
            }

        # Reduced logging verbosity for routine data retrieval
        return jsonify(result)

    except Exception as e:
        errorMsg = f"Exception getting recent attempts: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "GetRecentAttempts")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeJobBlueprint.route('/ProgressSummary', methods=['GET'])
def GetProgressSummary():
    """Get transcoding progress summary."""
    try:
        LoggingService.LogFunctionEntry("GetProgressSummary", "TranscodeJobController")

        # Create ViewModel instance
        viewModel = ActivityViewModel(TranscodingService=SharedTranscodingService)

        # Get progress summary
        summary = viewModel.GetProgressSummary()

        result = {
            "Success": True,
            "Summary": summary
        }

        # Reduced logging verbosity for routine progress retrieval
        return jsonify(result)

    except Exception as e:
        errorMsg = f"Exception getting progress summary: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "GetProgressSummary")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500

@TranscodeJobBlueprint.route('/Progress', methods=['GET'])
def GetCurrentProgress():
    """Get current transcoding progress from database."""
    try:
        # Function entry logging removed for frequent progress calls

        # Create ViewModel instance
        viewModel = ActivityViewModel(TranscodingService=SharedTranscodingService)

        # Get current progress
        progress = viewModel.GetCurrentTranscodeProgress()

        # Reduced logging verbosity for routine progress retrieval
        return jsonify(progress)

    except Exception as e:
        errorMsg = f"Exception getting current progress: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "GetCurrentProgress")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeJobBlueprint.route('/AllProgress', methods=['GET'])
def GetAllProgress():
    """Get progress for all active transcode jobs (supports concurrent transcoding)."""
    try:
        from Repositories.DatabaseManager import DatabaseManager
        DbManager = DatabaseManager()

        ProgressList = DbManager.GetAllCurrentTranscodeProgress()

        return jsonify({
            'Success': True,
            'Jobs': ProgressList,
            'Count': len(ProgressList)
        })

    except Exception as e:
        errorMsg = f"Exception getting all progress: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "GetAllProgress")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeJobBlueprint.route('/Refresh', methods=['POST'])
def RefreshStatus():
    """Refresh transcoding status and progress."""
    try:
        LoggingService.LogFunctionEntry("RefreshStatus", "TranscodeJobController")

        # Create ViewModel instance
        viewModel = ActivityViewModel(TranscodingService=SharedTranscodingService)

        # Refresh status
        result = viewModel.RefreshStatus()

        if result.get("Success", False):
            LoggingService.LogInfo("Refreshed transcoding status", "TranscodeJobController", "RefreshStatus")
            return jsonify(result)
        else:
            LoggingService.LogError(f"Failed to refresh status: {result.get('ErrorMessage', 'Unknown error')}", "TranscodeJobController", "RefreshStatus")
            return jsonify(result), 500

    except Exception as e:
        errorMsg = f"Exception refreshing status: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "RefreshStatus")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeJobBlueprint.route('/Health', methods=['GET'])
def HealthCheck():
    """Health check endpoint for transcoding service."""
    try:
        LoggingService.LogFunctionEntry("HealthCheck", "TranscodeJobController")

        # Create ViewModel instance
        viewModel = ActivityViewModel(TranscodingService=SharedTranscodingService)

        # Get basic status
        status = viewModel.GetTranscodingStatus()

        # Check FFmpeg availability
        ffmpegAvailable = viewModel.TranscodingService.FFmpegService.CheckAvailability()

        result = {
            "Success": True,
            "Service": "TranscodeJobController",
            "Status": "Healthy",
            "IsTranscoding": status.get("IsTranscoding", False),
            "FFmpegAvailable": ffmpegAvailable,
            "Timestamp": viewModel.TranscodingService.DatabaseManager.DatabaseService.GetCurrentTimestamp()
        }

        LoggingService.LogInfo("Health check completed", "TranscodeJobController", "HealthCheck")
        return jsonify(result)

    except Exception as e:
        errorMsg = f"Exception in health check: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "HealthCheck")
        return jsonify({
            "Success": False,
            "Service": "TranscodeJobController",
            "Status": "Unhealthy",
            "ErrorMessage": errorMsg
        }), 500


@TranscodeJobBlueprint.route('/CancelActive', methods=['POST'])
def CancelActiveTranscode():
    """Cancel the currently running transcode job."""
    try:
        LoggingService.LogFunctionEntry("CancelActiveTranscode", "TranscodeJobController")

        # Get ProcessTranscodeQueueService instance
        from Features.TranscodeJob.ProcessTranscodeQueueService import ProcessTranscodeQueueService
        from Repositories.DatabaseManager import DatabaseManager

        database_manager = DatabaseManager()
        transcode_service = ProcessTranscodeQueueService(DatabaseManagerInstance=database_manager)

        # Call CancelActiveTranscodeJob()
        result = transcode_service.CancelActiveTranscodeJob()

        if result.get("Success", False):
            LoggingService.LogInfo(f"Successfully cancelled active transcode job: {result.get('Message', '')}",
                                 "TranscodeJobController", "CancelActiveTranscode")
        else:
            LoggingService.LogWarning(f"Failed to cancel active transcode job: {result.get('Message', 'Unknown error')}",
                                    "TranscodeJobController", "CancelActiveTranscode")

        return jsonify(result)

    except Exception as e:
        errorMsg = f"Exception cancelling active transcode job: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "CancelActiveTranscode")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500

@TranscodeJobBlueprint.route('/Pause', methods=['POST'])
def PauseTranscoding():
    """Pause transcoding queue and migrate running jobs to E-cores (Game Mode)."""
    try:
        LoggingService.LogFunctionEntry("PauseTranscoding", "TranscodeJobController")

        from Repositories.DatabaseManager import DatabaseManager
        db_manager = DatabaseManager()

        success = db_manager.UpdateServiceStatus("TranscodeService", {
            'Status': 'Paused',
            'IsProcessing': False
        })

        # Migrate active FFmpeg jobs to E-cores so P-cores are free
        MigrationResult = None
        try:
            from Services.CpuAffinityService import GetCpuAffinityServiceInstance
            AffinityService = GetCpuAffinityServiceInstance()
            if AffinityService.CpuAffinityEnabled:
                MigrationResult = AffinityService.MigrateActiveJobsToTier("efficiency")
        except Exception as MigrationError:
            LoggingService.LogWarning(f"Failed to migrate jobs to E-cores on pause: {MigrationError}",
                                     "TranscodeJobController", "PauseTranscoding")

        if success:
            Message = "Transcoding paused - no new jobs will start"
            if MigrationResult and MigrationResult.get("MigratedCount", 0) > 0:
                Message += f", {MigrationResult['MigratedCount']} running job(s) moved to E-cores"
            LoggingService.LogInfo("Transcoding paused successfully",
                                 "TranscodeJobController", "PauseTranscoding")
            return jsonify({
                "Success": True,
                "Message": Message
            })
        else:
            return jsonify({
                "Success": False,
                "ErrorMessage": "Failed to pause transcoding"
            }), 500

    except Exception as e:
        errorMsg = f"Exception pausing transcoding: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "PauseTranscoding")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500

@TranscodeJobBlueprint.route('/SetPreferredAttempt/<int:attempt_id>', methods=['POST'])
def SetPreferredAttempt(attempt_id: int):
    """Set or unset a transcode attempt as preferred to prevent further retranscoding."""
    try:
        LoggingService.LogFunctionEntry("SetPreferredAttempt", "TranscodeJobController", attempt_id)

        from Repositories.DatabaseManager import DatabaseManager
        db_manager = DatabaseManager()

        # Get request data
        data = request.get_json() or {}
        is_preferred = data.get('IsPreferred', True)

        # Get the attempt to find its file path
        attempt = db_manager.GetTranscodeAttemptById(attempt_id)
        if not attempt:
            errorMsg = f"Transcode attempt {attempt_id} not found"
            LoggingService.LogError(errorMsg, "TranscodeJobController", "SetPreferredAttempt")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 404

        # Set preferred status using MediaFileId
        MediaFileId = db_manager.LookupMediaFileId(attempt.FilePath)
        success = db_manager.SetPreferredAttempt(attempt_id, MediaFileId, is_preferred)

        if success:
            action = "set as preferred" if is_preferred else "unset as preferred"
            LoggingService.LogInfo(f"Successfully {action} for attempt {attempt_id}",
                                 "TranscodeJobController", "SetPreferredAttempt")
            return jsonify({
                "Success": True,
                "Message": f"Attempt {attempt_id} {action} successfully",
                "AttemptId": attempt_id,
                "IsPreferred": is_preferred
            })
        else:
            errorMsg = f"Failed to set preferred status for attempt {attempt_id}"
            LoggingService.LogError(errorMsg, "TranscodeJobController", "SetPreferredAttempt")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500

    except Exception as e:
        errorMsg = f"Exception setting preferred attempt: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "SetPreferredAttempt")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeJobBlueprint.route('/SetCRFOverride', methods=['POST'])
def SetCRFOverride():
    """Set or clear a CRF override for a specific file to retry at a specific CRF value."""
    try:
        LoggingService.LogFunctionEntry("SetCRFOverride", "TranscodeJobController")

        from Repositories.DatabaseManager import DatabaseManager
        db_manager = DatabaseManager()

        # Get request data
        data = request.get_json() or {}
        file_path = data.get('FilePath')
        crf_value = data.get('CRF')

        # Validate inputs
        if not file_path:
            errorMsg = "FilePath is required"
            LoggingService.LogError(errorMsg, "TranscodeJobController", "SetCRFOverride")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        # If CRF is None or not provided, clear the override
        if crf_value is None:
            normalized_path = file_path.lower().replace('\\', '/')
            override_key = f"CRFOverride_{normalized_path}"
            success = db_manager.DeleteSystemSetting(override_key)

            if success:
                LoggingService.LogInfo(f"Cleared CRF override for {file_path}",
                                     "TranscodeJobController", "SetCRFOverride")
                return jsonify({
                    "Success": True,
                    "Message": f"CRF override cleared for {file_path}",
                    "FilePath": file_path,
                    "CRF": None
                })
            else:
                # Setting might not exist, which is fine
                LoggingService.LogInfo(f"CRF override not found for {file_path} (may not have been set)",
                                     "TranscodeJobController", "SetCRFOverride")
                return jsonify({
                    "Success": True,
                    "Message": f"CRF override cleared for {file_path}",
                    "FilePath": file_path,
                    "CRF": None
                })

        # Validate CRF value
        try:
            crf_int = int(crf_value)
            if crf_int < 15 or crf_int > 51:
                errorMsg = f"CRF value must be between 15 and 51, got {crf_int}"
                LoggingService.LogError(errorMsg, "TranscodeJobController", "SetCRFOverride")
                return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400
        except (ValueError, TypeError):
            errorMsg = f"Invalid CRF value: {crf_value}. Must be an integer."
            LoggingService.LogError(errorMsg, "TranscodeJobController", "SetCRFOverride")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        # Set the override
        normalized_path = file_path.lower().replace('\\', '/')
        override_key = f"CRFOverride_{normalized_path}"
        description = f"CRF override for {file_path} - will use CRF {crf_int} instead of adaptive quality calculation"
        success = db_manager.AddOrUpdateSystemSetting(override_key, str(crf_int), description, 'integer')

        if success:
            LoggingService.LogInfo(f"Set CRF override for {file_path} to CRF {crf_int}",
                                 "TranscodeJobController", "SetCRFOverride")
            return jsonify({
                "Success": True,
                "Message": f"CRF override set to {crf_int} for {file_path}",
                "FilePath": file_path,
                "CRF": crf_int
            })
        else:
            errorMsg = f"Failed to set CRF override for {file_path}"
            LoggingService.LogError(errorMsg, "TranscodeJobController", "SetCRFOverride")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500

    except Exception as e:
        errorMsg = f"Exception setting CRF override: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "SetCRFOverride")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500
