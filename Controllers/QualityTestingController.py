from flask import Blueprint, request, jsonify
from typing import Dict, Any
from ViewModels.QualityTestingViewModel import QualityTestingViewModel
from Services.LoggingService import LoggingService
from Services.ServiceCommandService import ServiceCommandService


# Create Blueprint for quality testing routes
QualityTestingBlueprint = Blueprint('QualityTesting', __name__, url_prefix='/api/QualityTesting')

# Create shared service instances
SharedQualityTestingViewModel = QualityTestingViewModel()
SharedCommandService = ServiceCommandService()


@QualityTestingBlueprint.route('/Queue', methods=['GET'])
def GetQualityTestingQueue():
    """Get current quality testing queue status with pagination and sorting."""
    try:
        LoggingService.LogFunctionEntry("GetQualityTestingQueue", "QualityTestingController")
        
        # Get query parameters
        Page = int(request.args.get('page', 1))
        PageSize = int(request.args.get('pageSize', 25))
        SortBy = request.args.get('sortBy', 'DateAdded')
        SortOrder = request.args.get('sortOrder', 'DESC')
        
        # Validate parameters
        if Page < 1:
            Page = 1
        if PageSize < 1 or PageSize > 100:
            PageSize = 25
        if SortBy not in ['DateAdded', 'Priority', 'Status', 'FileName', 'VMAFScore']:
            SortBy = 'DateAdded'
        if SortOrder not in ['ASC', 'DESC']:
            SortOrder = 'DESC'
        
        # Get queue items with pagination
        Result = SharedQualityTestingViewModel.GetQualityTestingQueue(Page, PageSize, SortBy, SortOrder)
        
        if Result.get("Success", False):
            LoggingService.LogDebug(f"Retrieved {Result.get('Count', 0)} quality testing queue items", "QualityTestingController", "GetQualityTestingQueue")
            return jsonify(Result)
        else:
            LoggingService.LogError(f"Failed to get quality testing queue: {Result.get('ErrorMessage', 'Unknown error')}", "QualityTestingController", "GetQualityTestingQueue")
            return jsonify(Result), 500
            
    except Exception as e:
        ErrorMsg = f"Exception getting quality testing queue: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestingController", "GetQualityTestingQueue")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@QualityTestingBlueprint.route('/Status', methods=['GET'])
def GetQualityTestingStatus():
    """Get quality testing service status."""
    try:
        LoggingService.LogFunctionEntry("GetQualityTestingStatus", "QualityTestingController")
        
        # Get status from ViewModel
        Result = SharedQualityTestingViewModel.GetQualityTestingStatus()
        
        if Result.get("Success", False):
            LoggingService.LogInfo("Quality testing status retrieved successfully", "QualityTestingController", "GetQualityTestingStatus")
            return jsonify(Result)
        else:
            LoggingService.LogError(f"Failed to get quality testing status: {Result.get('ErrorMessage', 'Unknown error')}", "QualityTestingController", "GetQualityTestingStatus")
            return jsonify(Result), 500
            
    except Exception as e:
        ErrorMsg = f"Exception getting quality testing status: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestingController", "GetQualityTestingStatus")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@QualityTestingBlueprint.route('/Start', methods=['POST'])
def StartQualityTesting():
    """Start quality testing jobs via database command."""
    try:
        LoggingService.LogFunctionEntry("StartQualityTesting", "QualityTestingController")
        
        # Get parameters from request
        Data = request.get_json() or {}
        MaxConcurrentJobs = Data.get('MaxConcurrentJobs', 1)
        
        # Validate parameters
        if not isinstance(MaxConcurrentJobs, int) or MaxConcurrentJobs < 1 or MaxConcurrentJobs > 5:
            ErrorMsg = "MaxConcurrentJobs must be an integer between 1 and 5"
            LoggingService.LogError(ErrorMsg, "QualityTestingController", "StartQualityTesting")
            return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 400
        
        # Create database command instead of direct service call
        Parameters = {"MaxConcurrentJobs": MaxConcurrentJobs}
        Result = SharedCommandService.CreateCommand(
            CommandType="StartQualityTesting",
            SourceService="MediaVortex",
            TargetService="QualityCompareService",
            Parameters=Parameters,
            Priority=5,
            CreatedBy="QualityTestingController"
        )
        
        if Result.get("Success", False):
            LoggingService.LogInfo(f"Quality testing start command created successfully", "QualityTestingController", "StartQualityTesting")
            return jsonify({
                "Success": True,
                "Message": "Quality testing start command created successfully",
                "CommandId": Result.get("CommandId")
            })
        else:
            LoggingService.LogError(f"Failed to create quality testing start command: {Result.get('ErrorMessage', 'Unknown error')}", "QualityTestingController", "StartQualityTesting")
            return jsonify(Result), 500
            
    except Exception as e:
        ErrorMsg = f"Exception starting quality testing: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestingController", "StartQualityTesting")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@QualityTestingBlueprint.route('/History', methods=['GET'])
def GetQualityTestingHistory():
    """Get quality testing history."""
    try:
        LoggingService.LogFunctionEntry("GetQualityTestingHistory", "QualityTestingController")
        
        # Get parameters from request
        Limit = request.args.get('Limit', 50, type=int)
        
        # Validate parameters
        if not isinstance(Limit, int) or Limit < 1 or Limit > 500:
            ErrorMsg = "Limit must be an integer between 1 and 500"
            LoggingService.LogError(ErrorMsg, "QualityTestingController", "GetQualityTestingHistory")
            return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 400
        
        # Get history from ViewModel
        Result = SharedQualityTestingViewModel.GetQualityTestingHistory(Limit)
        
        if Result.get("Success", False):
            LoggingService.LogInfo(f"Retrieved {Result.get('Count', 0)} quality testing history items", "QualityTestingController", "GetQualityTestingHistory")
            return jsonify(Result)
        else:
            LoggingService.LogError(f"Failed to get quality testing history: {Result.get('ErrorMessage', 'Unknown error')}", "QualityTestingController", "GetQualityTestingHistory")
            return jsonify(Result), 500
            
    except Exception as e:
        ErrorMsg = f"Exception getting quality testing history: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestingController", "GetQualityTestingHistory")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@QualityTestingBlueprint.route('/Progress', methods=['GET'])
def GetQualityTestingProgress():
    """Get current quality testing progress."""
    try:
        LoggingService.LogFunctionEntry("GetQualityTestingProgress", "QualityTestingController")
        
        # Get progress from ViewModel
        Result = SharedQualityTestingViewModel.GetQualityTestingProgress()
        
        if Result.get("Success", False):
            LoggingService.LogInfo("Quality testing progress retrieved successfully", "QualityTestingController", "GetQualityTestingProgress")
            return jsonify(Result)
        else:
            LoggingService.LogError(f"Failed to get quality testing progress: {Result.get('ErrorMessage', 'Unknown error')}", "QualityTestingController", "GetQualityTestingProgress")
            return jsonify(Result), 500
            
    except Exception as e:
        ErrorMsg = f"Exception getting quality testing progress: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestingController", "GetQualityTestingProgress")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@QualityTestingBlueprint.route('/Stop', methods=['POST'])
def StopQualityTesting():
    """Stop quality testing jobs via database command."""
    try:
        LoggingService.LogFunctionEntry("StopQualityTesting", "QualityTestingController")
        
        # Create database command instead of direct service call
        Parameters = {}
        Result = SharedCommandService.CreateCommand(
            CommandType="StopQualityTesting",
            SourceService="MediaVortex",
            TargetService="QualityCompareService",
            Parameters=Parameters,
            Priority=5,
            CreatedBy="QualityTestingController"
        )
        
        if Result.get("Success", False):
            LoggingService.LogInfo("Quality testing stop command created successfully", "QualityTestingController", "StopQualityTesting")
            return jsonify({
                "Success": True,
                "Message": "Quality testing stop command created successfully",
                "CommandId": Result.get("CommandId")
            })
        else:
            LoggingService.LogError(f"Failed to create quality testing stop command: {Result.get('ErrorMessage', 'Unknown error')}", "QualityTestingController", "StopQualityTesting")
            return jsonify(Result), 500
            
    except Exception as e:
        ErrorMsg = f"Exception stopping quality testing: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestingController", "StopQualityTesting")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@QualityTestingBlueprint.route('/Health', methods=['GET'])
def HealthCheck():
    """Health check endpoint for quality testing service."""
    try:
        LoggingService.LogFunctionEntry("HealthCheck", "QualityTestingController")
        
        # Get basic status
        Status = SharedQualityTestingViewModel.GetQualityTestingStatus()
        
        Result = {
            "Success": True,
            "Service": "QualityTestingController",
            "Status": "Healthy",
            "IsQualityTesting": Status.get("IsQualityTesting", False),
            "Timestamp": SharedQualityTestingViewModel.DatabaseManager.DatabaseService.GetCurrentTimestamp()
        }
        
        LoggingService.LogInfo("Quality testing health check completed", "QualityTestingController", "HealthCheck")
        return jsonify(Result)
        
    except Exception as e:
        ErrorMsg = f"Exception in quality testing health check: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestingController", "HealthCheck")
        return jsonify({
            "Success": False,
            "Service": "QualityTestingController",
            "Status": "Unhealthy",
            "ErrorMessage": ErrorMsg
        }), 500


@QualityTestingBlueprint.route('/Retry/<int:QueueId>', methods=['POST'])
def RetryQualityTestingJob(QueueId):
    """Retry a failed quality testing job."""
    try:
        LoggingService.LogFunctionEntry(f"RetryQualityTestingJob({QueueId})", "QualityTestingController")
        
        # Validate parameters
        if not isinstance(QueueId, int) or QueueId < 1:
            ErrorMsg = "Queue ID must be a positive integer"
            LoggingService.LogError(ErrorMsg, "QualityTestingController", "RetryQualityTestingJob")
            return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 400
        
        # Retry job via ViewModel
        Result = SharedQualityTestingViewModel.RetryQualityTestingJob(QueueId)
        
        if Result.get("Success", False):
            LoggingService.LogInfo(f"Quality testing job {QueueId} retry initiated successfully", "QualityTestingController", "RetryQualityTestingJob")
            return jsonify(Result)
        else:
            LoggingService.LogError(f"Failed to retry quality testing job {QueueId}: {Result.get('ErrorMessage', 'Unknown error')}", "QualityTestingController", "RetryQualityTestingJob")
            return jsonify(Result), 500
            
    except Exception as e:
        ErrorMsg = f"Exception retrying quality testing job {QueueId}: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestingController", "RetryQualityTestingJob")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@QualityTestingBlueprint.route('/Details/<int:QueueId>', methods=['GET'])
def GetQualityTestingDetails(QueueId):
    """Get detailed information about a quality testing job."""
    try:
        LoggingService.LogFunctionEntry(f"GetQualityTestingDetails({QueueId})", "QualityTestingController")
        
        # Validate parameters
        if not isinstance(QueueId, int) or QueueId < 1:
            ErrorMsg = "Queue ID must be a positive integer"
            LoggingService.LogError(ErrorMsg, "QualityTestingController", "GetQualityTestingDetails")
            return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 400
        
        # Get details via ViewModel
        Result = SharedQualityTestingViewModel.GetQualityTestingDetails(QueueId)
        
        if Result.get("Success", False):
            LoggingService.LogInfo(f"Quality testing details for job {QueueId} retrieved successfully", "QualityTestingController", "GetQualityTestingDetails")
            return jsonify(Result)
        else:
            LoggingService.LogError(f"Failed to get quality testing details for job {QueueId}: {Result.get('ErrorMessage', 'Unknown error')}", "QualityTestingController", "GetQualityTestingDetails")
            return jsonify(Result), 500
            
    except Exception as e:
        ErrorMsg = f"Exception getting quality testing details for job {QueueId}: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestingController", "GetQualityTestingDetails")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500


@QualityTestingBlueprint.route('/LogError', methods=['POST'])
def LogVMAFError():
    """Log VMAF processing errors to database."""
    try:
        LoggingService.LogFunctionEntry("LogVMAFError", "QualityTestingController")
        
        # Get error data from request
        Data = request.get_json() or {}
        ErrorMessage = Data.get('ErrorMessage', '')
        ErrorContext = Data.get('ErrorContext', '')
        RequestUrl = Data.get('RequestUrl', '')
        
        # Validate required fields
        if not ErrorMessage:
            ErrorMsg = "ErrorMessage is required"
            LoggingService.LogError(ErrorMsg, "QualityTestingController", "LogVMAFError")
            return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 400
        
        # Log the error using LoggingService
        LoggingService.LogError(
            f"VMAF Error - {ErrorMessage}",
            "LogVMAFError",
            "QualityTestingController",
            f"Context: {ErrorContext}, URL: {RequestUrl}"
        )
        
        LoggingService.LogInfo(f"VMAF error logged successfully: {ErrorMessage[:100]}...", "QualityTestingController", "LogVMAFError")
        
        return jsonify({
            "Success": True,
            "Message": "VMAF error logged successfully"
        })
        
    except Exception as e:
        ErrorMsg = f"Exception logging VMAF error: {str(e)}"
        LoggingService.LogException(ErrorMsg, e, "QualityTestingController", "LogVMAFError")
        return jsonify({"Success": False, "ErrorMessage": ErrorMsg}), 500