import os
from flask import Blueprint, request, jsonify, render_template
from typing import Dict, Any
from ViewModels.ActivityViewModel import ActivityViewModel
from Services.LoggingService import LoggingService
from Services.VMAFQueueBusinessService import VMAFQueueBusinessService
from Models.VMAFProgressModel import VMAFProgressModel


# Create Blueprint for VMAF job routes
VMAFJobBlueprint = Blueprint('VMAFJob', __name__, url_prefix='/api/VMAF')

# Create shared service instance to avoid multiple initializations
SharedVMAFService = VMAFQueueBusinessService()


@VMAFJobBlueprint.route('/Start', methods=['POST'])
def StartVMAFProcessing():
    """Start VMAF quality analysis processing."""
    try:
        LoggingService.LogFunctionEntry("StartVMAFProcessing", "VMAFJobController")
        
        # Get parameters from request
        Data = request.get_json() or {}
        MaxConcurrentJobs = Data.get('MaxConcurrentJobs', 1)
        
        # Validate parameters
        if not isinstance(MaxConcurrentJobs, int) or MaxConcurrentJobs < 1 or MaxConcurrentJobs > 5:
            ErrorMsg = "MaxConcurrentJobs must be an integer between 1 and 5"
            LoggingService.LogError(ErrorMsg, "VMAFJobController", "StartVMAFProcessing")
            return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 400
        
        # Start VMAF processing
        Result = SharedVMAFService.StartVMAFProcessing(MaxConcurrentJobs)
        
        if Result.get("Success", False):
            LoggingService.LogInfo(f"Started VMAF processing with {MaxConcurrentJobs} concurrent jobs", "VMAFJobController", "StartVMAFProcessing")
            return jsonify(Result)
        else:
            LoggingService.LogError(f"Failed to start VMAF processing: {Result.get('ErrorMessage', 'Unknown error')}", "VMAFJobController", "StartVMAFProcessing")
            return jsonify(Result), 500
            
    except Exception as e:
        ErrorMsg = f"Exception starting VMAF processing: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "VMAFJobController", "StartVMAFProcessing")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@VMAFJobBlueprint.route('/Stop', methods=['POST'])
def StopVMAFProcessing():
    """Stop VMAF quality analysis processing."""
    try:
        LoggingService.LogFunctionEntry("StopVMAFProcessing", "VMAFJobController")
        
        # Stop VMAF processing
        Result = SharedVMAFService.StopVMAFProcessing()
        
        if Result.get("Success", False):
            LoggingService.LogInfo("Stopped VMAF processing", "VMAFJobController", "StopVMAFProcessing")
            return jsonify(Result)
        else:
            LoggingService.LogError(f"Failed to stop VMAF processing: {Result.get('ErrorMessage', 'Unknown error')}", "VMAFJobController", "StopVMAFProcessing")
            return jsonify(Result), 500
            
    except Exception as e:
        ErrorMsg = f"Exception stopping VMAF processing: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "VMAFJobController", "StopVMAFProcessing")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@VMAFJobBlueprint.route('/Status', methods=['GET'])
def GetVMAFStatus():
    """Get current VMAF processing status and progress."""
    try:
        LoggingService.LogFunctionEntry("GetVMAFStatus", "VMAFJobController")
        
        # Get VMAF status
        Result = SharedVMAFService.GetVMAFQueueStatus()
        
        # Ensure the result has Success field for consistency
        if "Success" not in Result:
            Result["Success"] = True
        
        # Reduced logging verbosity for routine status checks
        return jsonify(Result)
        
    except Exception as e:
        ErrorMsg = f"Exception getting VMAF status: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "VMAFJobController", "GetVMAFStatus")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@VMAFJobBlueprint.route('/Queue', methods=['GET'])
def GetVMAFQueue():
    """Get current VMAF queue items."""
    try:
        LoggingService.LogFunctionEntry("GetVMAFQueue", "VMAFJobController")
        
        # Get VMAF queue items (exclude completed items for cleaner UI)
        AllQueueItems = SharedVMAFService.DatabaseManager.GetAllVMAFQueueItems()
        QueueItems = [item for item in AllQueueItems if item.Status in ['Pending', 'Running', 'Failed']]
        
        # Format queue items for response
        FormattedItems = []
        for Item in QueueItems:
            FormattedItems.append({
                'Id': Item.Id,
                'TranscodeAttemptId': Item.TranscodeAttemptId,
                'FileName': Item.FileName,
                'Status': Item.Status,
                'Priority': Item.Priority,
                'DateAdded': Item.DateAdded.isoformat() if Item.DateAdded and hasattr(Item.DateAdded, 'isoformat') else Item.DateAdded,
                'DateStarted': Item.DateStarted.isoformat() if Item.DateStarted and hasattr(Item.DateStarted, 'isoformat') else Item.DateStarted,
                'DateCompleted': Item.DateCompleted.isoformat() if Item.DateCompleted and hasattr(Item.DateCompleted, 'isoformat') else Item.DateCompleted,
                'VMAFScore': Item.VMAFScore,
                'QualityThreshold': Item.QualityThreshold,
                'ErrorMessage': Item.ErrorMessage,
                'RetryCount': Item.RetryCount,
                'MaxRetries': Item.MaxRetries
            })
        
        Result = {
            "Success": True,
            "Message": "VMAF queue retrieved successfully",
            "QueueItems": FormattedItems,
            "TotalItems": len(FormattedItems)
        }
        
        LoggingService.LogInfo(f"Retrieved {len(FormattedItems)} VMAF queue items", "VMAFJobController", "GetVMAFQueue")
        return jsonify(Result)
        
    except Exception as e:
        ErrorMsg = f"Exception getting VMAF queue: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "VMAFJobController", "GetVMAFQueue")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@VMAFJobBlueprint.route('/Add', methods=['POST'])
def AddToVMAFQueue():
    """Add a transcoded file to the VMAF queue."""
    try:
        LoggingService.LogFunctionEntry("AddToVMAFQueue", "VMAFJobController")
        
        # Get parameters from request
        Data = request.get_json() or {}
        TranscodeAttemptId = Data.get('TranscodeAttemptId')
        OriginalFilePath = Data.get('OriginalFilePath')
        TranscodedFilePath = Data.get('TranscodedFilePath')
        QualityThreshold = Data.get('QualityThreshold', 90.0)
        
        # Validate required parameters
        if not TranscodeAttemptId:
            ErrorMsg = "TranscodeAttemptId is required"
            LoggingService.LogError(ErrorMsg, "VMAFJobController", "AddToVMAFQueue")
            return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 400
        
        if not OriginalFilePath:
            ErrorMsg = "OriginalFilePath is required"
            LoggingService.LogError(ErrorMsg, "VMAFJobController", "AddToVMAFQueue")
            return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 400
        
        if not TranscodedFilePath:
            ErrorMsg = "TranscodedFilePath is required"
            LoggingService.LogError(ErrorMsg, "VMAFJobController", "AddToVMAFQueue")
            return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 400
        
        # Add to VMAF queue
        Result = SharedVMAFService.AddToVMAFQueue(
            TranscodeAttemptId,
            OriginalFilePath,
            TranscodedFilePath,
            QualityThreshold
        )
        
        if Result.get("Success", False):
            LoggingService.LogInfo(f"Added file to VMAF queue: {Result.get('VMAFQueueId')}", "VMAFJobController", "AddToVMAFQueue")
            return jsonify(Result)
        else:
            LoggingService.LogError(f"Failed to add to VMAF queue: {Result.get('ErrorMessage', 'Unknown error')}", "VMAFJobController", "AddToVMAFQueue")
            return jsonify(Result), 500
            
    except Exception as e:
        ErrorMsg = f"Exception adding to VMAF queue: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "VMAFJobController", "AddToVMAFQueue")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@VMAFJobBlueprint.route('/Statistics', methods=['GET'])
def GetVMAFStatistics():
    """Get VMAF queue statistics."""
    try:
        LoggingService.LogFunctionEntry("GetVMAFStatistics", "VMAFJobController")
        
        # Get VMAF statistics
        Statistics = SharedVMAFService.GetVMAFQueueStatistics()
        
        Result = {
            "Success": True,
            "Statistics": Statistics
        }
        
        # Reduced logging verbosity for routine statistics retrieval
        return jsonify(Result)
        
    except Exception as e:
        ErrorMsg = f"Exception getting VMAF statistics: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "VMAFJobController", "GetVMAFStatistics")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@VMAFJobBlueprint.route('/Health', methods=['GET'])
def HealthCheck():
    """Health check endpoint for VMAF service."""
    try:
        LoggingService.LogFunctionEntry("HealthCheck", "VMAFJobController")
        
        # Get basic status
        Status = SharedVMAFService.GetVMAFQueueStatus()
        
        Result = {
            "Success": True,
            "Service": "VMAFJobController",
            "Status": "Healthy",
            "IsProcessing": Status.get("IsRunning", False),
            "Timestamp": SharedVMAFService.DatabaseManager.DatabaseService.GetCurrentTimestamp()
        }
        
        LoggingService.LogInfo("VMAF health check completed", "VMAFJobController", "HealthCheck")
        return jsonify(Result)
        
    except Exception as e:
        ErrorMsg = f"Exception in VMAF health check: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "VMAFJobController", "HealthCheck")
        return jsonify({
            "Success": False,
            "Service": "VMAFJobController",
            "Status": "Unhealthy",
            "ErrorMessage": ErrorMsg
        }), 500


@VMAFJobBlueprint.route('/LogError', methods=['POST'])
def LogFrontendError():
    """Log frontend errors to the database."""
    try:
        LoggingService.LogFunctionEntry("LogFrontendError", "VMAFJobController")
        
        # Get error data from request
        Data = request.get_json() or {}
        ErrorMessage = Data.get('ErrorMessage', 'Unknown frontend error')
        ErrorContext = Data.get('ErrorContext', 'Frontend')
        UserAgent = request.headers.get('User-Agent', 'Unknown')
        RequestUrl = Data.get('RequestUrl', 'Unknown')
        
        # Log the error to database
        LoggingService.LogError(f"Frontend Error: {ErrorMessage} | Context: {ErrorContext} | URL: {RequestUrl} | UserAgent: {UserAgent}", 
                              "Frontend", "VMAFQueue")
        
        return jsonify({
            "Success": True,
            "Message": "Error logged successfully"
        })
        
    except Exception as e:
        ErrorMsg = f"Exception logging frontend error: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "VMAFJobController", "LogFrontendError")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@VMAFJobBlueprint.route('/Progress', methods=['GET'])
def GetVMAFProgress():
    """Get VMAF progress status for UI updates."""
    try:
        LoggingService.LogFunctionEntry("GetVMAFProgress", "VMAFJobController")
        
        # Get VMAF queue status
        StatusResult = SharedVMAFService.GetVMAFQueueStatus()
        
        if not StatusResult.get("Success", False):
            return jsonify(StatusResult), 500
        
        # Get current running job progress if any
        CurrentJob = StatusResult.get("CurrentVMAFJob")
        ProgressData = None
        
        if CurrentJob:
            VMAFProgressItem = SharedVMAFService.DatabaseManager.GetVMAFProgressByQueueId(CurrentJob["Id"])
            if VMAFProgressItem:
                ProgressData = {
                    "VMAFQueueId": VMAFProgressItem.VMAFQueueId,
                    "TranscodeAttemptId": VMAFProgressItem.TranscodeAttemptId,
                    "Status": VMAFProgressItem.Status,
                    "ProgressPercentage": VMAFProgressItem.ProgressPercentage,
                    "CurrentStep": VMAFProgressItem.CurrentStep,
                    "StartTime": VMAFProgressItem.StartTime.isoformat() if VMAFProgressItem.StartTime and hasattr(VMAFProgressItem.StartTime, 'isoformat') else VMAFProgressItem.StartTime,
                    "EndTime": VMAFProgressItem.EndTime.isoformat() if VMAFProgressItem.EndTime and hasattr(VMAFProgressItem.EndTime, 'isoformat') else VMAFProgressItem.EndTime,
                    "ETA": VMAFProgressItem.ETA,
                    "ErrorMessage": VMAFProgressItem.ErrorMessage,
                    "Duration": VMAFProgressItem.GetFormattedDuration()
                }
        
        Result = {
            "Success": True,
            "Message": "VMAF progress retrieved successfully",
            "IsRunning": StatusResult.get("IsRunning", False),
            "CurrentJob": CurrentJob,
            "Progress": ProgressData,
            "QueueStatistics": StatusResult.get("QueueStatistics", {})
        }
        
        return jsonify(Result)
        
    except Exception as e:
        ErrorMsg = f"Exception getting VMAF progress: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "VMAFJobController", "GetVMAFProgress")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@VMAFJobBlueprint.route('/History', methods=['GET'])
def GetVMAFHistory():
    """Get recent VMAF test results for activity display."""
    try:
        LoggingService.LogFunctionEntry("GetVMAFHistory", "VMAFJobController")
        
        # Get parameters from request
        Limit = request.args.get('Limit', 5, type=int)
        
        # Validate parameters
        if not isinstance(Limit, int) or Limit < 1 or Limit > 50:
            ErrorMsg = "Limit must be an integer between 1 and 50"
            LoggingService.LogError(ErrorMsg, "VMAFJobController", "GetVMAFHistory")
            return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 400
        
        # Get recent VMAF results from TranscodeAttempts table
        RecentVMAFResults = SharedVMAFService.DatabaseManager.GetRecentVMAFResults(Limit)
        
        # Format results for response
        FormattedResults = []
        for Result in RecentVMAFResults:
            FormattedResults.append({
                'Id': Result.Id,
                'FileName': os.path.basename(Result.FilePath) if Result.FilePath else 'Unknown',
                'FilePath': Result.FilePath,
                'AttemptDate': Result.AttemptDate.isoformat() if Result.AttemptDate and hasattr(Result.AttemptDate, 'isoformat') else Result.AttemptDate,
                'VMAFScore': Result.VMAF,
                'Quality': Result.Quality,
                'ProfileName': Result.ProfileName,
                'Success': Result.Success,
                'SizeReductionPercent': Result.SizeReductionPercent,
                'TranscodeDurationSeconds': Result.TranscodeDurationSeconds,
                'ErrorMessage': Result.ErrorMessage
            })
        
        Result = {
            "Success": True,
            "Message": "VMAF history retrieved successfully",
            "VMAFResults": FormattedResults,
            "Count": len(FormattedResults)
        }
        
        # Reduced logging verbosity for routine data retrieval
        return jsonify(Result)
        
    except Exception as e:
        ErrorMsg = f"Exception getting VMAF history: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "VMAFJobController", "GetVMAFHistory")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500
