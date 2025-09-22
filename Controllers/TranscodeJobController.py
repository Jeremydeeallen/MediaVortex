from flask import Blueprint, request, jsonify, render_template
from typing import Dict, Any
from ViewModels.ActivityViewModel import ActivityViewModel
from Services.LoggingService import LoggingService
from Services.TranscodingBusinessService import TranscodingBusinessService


# Create Blueprint for transcoding job routes
TranscodeJobBlueprint = Blueprint('TranscodeJob', __name__, url_prefix='/api/Transcode')

# Create shared service instance to avoid multiple initializations
SharedTranscodingService = TranscodingBusinessService()


@TranscodeJobBlueprint.route('/Start', methods=['POST'])
def StartTranscoding():
    """Start transcoding jobs."""
    try:
        LoggingService.LogFunctionEntry("StartTranscoding", "TranscodeJobController")
        
        # Get parameters from request
        data = request.get_json() or {}
        maxConcurrentJobs = data.get('MaxConcurrentJobs', 1)
        
        # Validate parameters
        if not isinstance(maxConcurrentJobs, int) or maxConcurrentJobs < 1 or maxConcurrentJobs > 5:
            errorMsg = "MaxConcurrentJobs must be an integer between 1 and 5"
            LoggingService.LogError(errorMsg, "TranscodeJobController", "StartTranscoding")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400
        
        # Create ViewModel instance
        viewModel = ActivityViewModel(TranscodingService=SharedTranscodingService)
        
        # Start transcoding
        result = viewModel.StartTranscoding(maxConcurrentJobs)
        
        if result.get("Success", False):
            LoggingService.LogInfo(f"Started transcoding with {maxConcurrentJobs} concurrent jobs", "TranscodeJobController", "StartTranscoding")
            return jsonify(result)
        else:
            LoggingService.LogError(f"Failed to start transcoding: {result.get('ErrorMessage', 'Unknown error')}", "TranscodeJobController", "StartTranscoding")
            return jsonify(result), 500
            
    except Exception as e:
        errorMsg = f"Exception starting transcoding: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "StartTranscoding")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeJobBlueprint.route('/Stop', methods=['POST'])
def StopTranscoding():
    """Stop transcoding jobs."""
    try:
        LoggingService.LogFunctionEntry("StopTranscoding", "TranscodeJobController")
        
        # Create ViewModel instance
        viewModel = ActivityViewModel(TranscodingService=SharedTranscodingService)
        
        # Stop transcoding
        result = viewModel.StopTranscoding()
        
        if result.get("Success", False):
            LoggingService.LogInfo("Stopped transcoding", "TranscodeJobController", "StopTranscoding")
            return jsonify(result)
        else:
            LoggingService.LogError(f"Failed to stop transcoding: {result.get('ErrorMessage', 'Unknown error')}", "TranscodeJobController", "StopTranscoding")
            return jsonify(result), 500
            
    except Exception as e:
        errorMsg = f"Exception stopping transcoding: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeJobController", "StopTranscoding")
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
        
        # Get recent attempts
        recentAttempts = viewModel.GetRecentAttempts(limit)
        
        result = {
            "Success": True,
            "RecentAttempts": recentAttempts,
            "Count": len(recentAttempts)
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

@TranscodeJobBlueprint.route('/CurrentProgress', methods=['GET'])
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
