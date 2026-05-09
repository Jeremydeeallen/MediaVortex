from flask import Blueprint, request, jsonify, render_template
from typing import Dict, Any, Tuple
from Features.TranscodeQueue.TranscodeQueueViewModel import TranscodeQueueViewModel
from Core.Logging.LoggingService import LoggingService
from Core.DateTimeHelpers import ToUtcIsoZ
from ViewModels.TranscodingViewModel import TranscodingViewModel
from datetime import datetime, timezone


# Create Blueprint for transcoding queue routes
TranscodeQueueBlueprint = Blueprint('TranscodeQueue', __name__, url_prefix='/api/TranscodeQueue')


@TranscodeQueueBlueprint.route('/GetQueue', methods=['GET'])
def GetQueue():
    """Get current transcoding queue status with pagination and sorting."""
    try:
        LoggingService.LogFunctionEntry("GetQueue", "TranscodeQueueController")

        # Get query parameters
        page = int(request.args.get('page', 1))
        pageSize = int(request.args.get('pageSize', 25))
        sortBy = request.args.get('sortBy', 'Priority')
        sortOrder = request.args.get('sortOrder', 'DESC')

        # Validate parameters
        if page < 1:
            page = 1
        if pageSize < 1 or pageSize > 100:
            pageSize = 25
        if sortBy not in ['SizeMB', 'Priority', 'DateAdded', 'FileName']:
            sortBy = 'Priority'
        if sortOrder not in ['ASC', 'DESC']:
            sortOrder = 'DESC'

        # Create ViewModel instance
        viewModel = TranscodeQueueViewModel()

        # Load queue items with pagination
        result = viewModel.LoadQueueItems(page, pageSize, sortBy, sortOrder)

        if result.get("Success", False):
            # Reduced logging verbosity for routine queue retrieval
            return jsonify(result)
        else:
            LoggingService.LogError(f"Failed to get queue: {result.get('ErrorMessage', 'Unknown error')}", "TranscodeQueueController", "GetQueue")
            return jsonify(result), 500

    except Exception as e:
        errorMsg = f"Exception getting queue: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeQueueController", "GetQueue")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeQueueBlueprint.route('/PopulateQueue', methods=['POST'])
def PopulateQueue():
    """Populate transcoding queue from MediaFiles."""
    try:
        LoggingService.LogFunctionEntry("PopulateQueue", "TranscodeQueueController")

        # Get parameters from request
        data = request.get_json() or {}
        rootFolderPath = data.get('RootFolderPath')
        profileId = data.get('ProfileId')
        compatibilityOnly = data.get('CompatibilityOnly', False)

        if profileId is not None and (not isinstance(profileId, int) or profileId < 1):
            errorMsg = "ProfileId must be a positive integer"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "PopulateQueue")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        # Create ViewModel instance
        viewModel = TranscodeQueueViewModel()

        # Populate queue - no limits, all matching files are added
        result = viewModel.PopulateQueue(rootFolderPath, profileId, compatibilityOnly)

        if result.get("Success", False):
            itemsAdded = result.get("ItemsAdded", 0)
            message = result.get("Message", f"Populated queue with {itemsAdded} items")
            LoggingService.LogInfo(f"Populated queue with {itemsAdded} items", "TranscodeQueueController", "PopulateQueue")
            return jsonify(result)
        else:
            errorMessage = result.get("ErrorMessage", "Unknown error")
            LoggingService.LogError(f"Failed to populate queue: {errorMessage}", "TranscodeQueueController", "PopulateQueue")
            return jsonify(result), 500

    except Exception as e:
        errorMsg = f"Exception populating queue: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeQueueController", "PopulateQueue")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeQueueBlueprint.route('/ClearQueue', methods=['POST'])
def ClearQueue():
    """Clear all items from the transcoding queue."""
    try:
        LoggingService.LogFunctionEntry("ClearQueue", "TranscodeQueueController")

        # Call ViewModel to clear the queue
        viewModel = TranscodeQueueViewModel()
        result = viewModel.ClearQueue()

        if result.get("Success", False):
            itemsCleared = result.get("ItemsCleared", 0)
            message = result.get("Message", f"Successfully cleared {itemsCleared} items from the queue")
            LoggingService.LogInfo(f"Cleared {itemsCleared} items from queue", "TranscodeQueueController", "ClearQueue")
            return jsonify(result)
        else:
            errorMessage = result.get("ErrorMessage", "Unknown error")
            LoggingService.LogError(f"Failed to clear queue: {errorMessage}", "TranscodeQueueController", "ClearQueue")
            return jsonify(result), 500

    except Exception as e:
        errorMsg = f"Exception clearing queue: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeQueueController", "ClearQueue")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeQueueBlueprint.route('/Count', methods=['GET'])
def GetQueueCount():
    """Lightweight endpoint that returns only the queue count."""
    try:
        from Repositories.DatabaseManager import DatabaseManager
        db = DatabaseManager()
        rows = db.DatabaseService.ExecuteQuery("SELECT COUNT(*) as Count FROM TranscodeQueue")
        count = rows[0]['Count'] if rows else 0
        return jsonify({"Success": True, "Count": count})
    except Exception as e:
        LoggingService.LogException("Failed to get queue count", e, "TranscodeQueueController", "GetQueueCount")
        return jsonify({"Success": False, "Count": 0}), 500


@TranscodeQueueBlueprint.route('/GetMkvCount', methods=['GET'])
def GetMkvCount():
    """Get count of MKV files available for remuxing."""
    try:
        viewModel = TranscodeQueueViewModel()
        result = viewModel.GetMkvFileCount()
        return jsonify(result)
    except Exception as e:
        errorMsg = f"Exception getting MKV count: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeQueueController", "GetMkvCount")
        return jsonify({"Success": False, "MkvFileCount": 0, "ErrorMessage": errorMsg}), 500


@TranscodeQueueBlueprint.route('/AddJob', methods=['POST'])
def AddJob():
    """Manually add a job to the transcoding queue."""
    try:
        LoggingService.LogFunctionEntry("AddJob", "TranscodeQueueController")

        # Get parameters from request
        data = request.get_json() or {}
        mediaFileId = data.get('MediaFileId')
        priority = data.get('Priority')
        profileId = data.get('ProfileId')
        startTime = data.get('StartTime')
        forceAdd = data.get('ForceAdd', False)

        # Validate parameters
        if not mediaFileId:
            errorMsg = "MediaFileId is required"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "AddJob")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        if not isinstance(mediaFileId, int) or mediaFileId < 1:
            errorMsg = "MediaFileId must be a positive integer"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "AddJob")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        if priority is not None and (not isinstance(priority, int) or priority < 1 or priority > 200):
            # Auto-assignment uses 1-194 (impact-based score). Operators can manually
            # set 195-200 to guarantee jumping ahead of any auto-prioritized item.
            errorMsg = "Priority must be an integer between 1 and 200"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "AddJob")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        # Create ViewModel instance
        viewModel = TranscodeQueueViewModel()

        # Add job to queue
        result = viewModel.AddJobToQueue(mediaFileId, priority, profileId, startTime, forceAdd)

        if result.get("Success", False):
            itemId = result.get("ItemId")
            fileName = result.get("FileName", "Unknown")
            LoggingService.LogInfo(f"Added job {itemId} for {fileName} to queue", "TranscodeQueueController", "AddJob")
            return jsonify(result)
        else:
            LoggingService.LogError(f"Failed to add job: {result.get('ErrorMessage', 'Unknown error')}", "TranscodeQueueController", "AddJob")
            return jsonify(result), 500

    except Exception as e:
        errorMsg = f"Exception adding job: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeQueueController", "AddJob")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeQueueBlueprint.route('/RemoveJob', methods=['POST'])
def RemoveJob():
    """Remove a job from the transcoding queue."""
    try:
        LoggingService.LogFunctionEntry("RemoveJob", "TranscodeQueueController")

        # Get parameters from request
        data = request.get_json() or {}
        itemId = data.get('ItemId')

        # Validate parameters
        if not itemId:
            errorMsg = "ItemId is required"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "RemoveJob")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        if not isinstance(itemId, int) or itemId < 1:
            errorMsg = "ItemId must be a positive integer"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "RemoveJob")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        # Create ViewModel instance
        viewModel = TranscodeQueueViewModel()

        # Remove job from queue
        result = viewModel.RemoveJobFromQueue(itemId)

        if result.get("Success", False):
            fileName = result.get("FileName", "Unknown")
            LoggingService.LogInfo(f"Removed job {itemId} ({fileName}) from queue", "TranscodeQueueController", "RemoveJob")
            return jsonify(result)
        else:
            LoggingService.LogError(f"Failed to remove job: {result.get('ErrorMessage', 'Unknown error')}", "TranscodeQueueController", "RemoveJob")
            return jsonify(result), 500

    except Exception as e:
        errorMsg = f"Exception removing job: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeQueueController", "RemoveJob")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeQueueBlueprint.route('/RemoveBySize', methods=['POST'])
def RemoveBySize():
    """Remove all pending queue items smaller than a given size in MB."""
    try:
        LoggingService.LogFunctionEntry("RemoveBySize", "TranscodeQueueController")

        data = request.get_json() or {}
        maxSizeMB = data.get('MaxSizeMB')

        if maxSizeMB is None or not isinstance(maxSizeMB, (int, float)) or maxSizeMB <= 0:
            errorMsg = "MaxSizeMB must be a positive number"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "RemoveBySize")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        viewModel = TranscodeQueueViewModel()
        result = viewModel.RemoveBySize(maxSizeMB)

        if result.get("Success", False):
            LoggingService.LogInfo(f"Removed {result.get('ItemsRemoved', 0)} queue items smaller than {maxSizeMB} MB",
                                 "TranscodeQueueController", "RemoveBySize")
            return jsonify(result)
        else:
            LoggingService.LogError(f"Failed to remove by size: {result.get('ErrorMessage', 'Unknown error')}",
                                  "TranscodeQueueController", "RemoveBySize")
            return jsonify(result), 500

    except Exception as e:
        errorMsg = f"Exception removing by size: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeQueueController", "RemoveBySize")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


@TranscodeQueueBlueprint.route('/PrioritizeJob', methods=['POST'])
def PrioritizeJob():
    """Update the priority of a queue item."""
    try:
        LoggingService.LogFunctionEntry("PrioritizeJob", "TranscodeQueueController")

        # Get parameters from request
        data = request.get_json() or {}
        itemId = data.get('ItemId')
        newPriority = data.get('NewPriority')

        # Validate parameters
        if not itemId:
            errorMsg = "ItemId is required"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "PrioritizeJob")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        if not isinstance(itemId, int) or itemId < 1:
            errorMsg = "ItemId must be a positive integer"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "PrioritizeJob")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        if not newPriority:
            errorMsg = "NewPriority is required"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "PrioritizeJob")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        if not isinstance(newPriority, int) or newPriority < 1 or newPriority > 200:
            # Auto-assignment uses 1-194 (impact-based score). Operators can manually
            # set 195-200 to guarantee jumping ahead of any auto-prioritized item.
            errorMsg = "NewPriority must be an integer between 1 and 200"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "PrioritizeJob")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400

        # Create ViewModel instance
        viewModel = TranscodeQueueViewModel()

        # Update job priority
        result = viewModel.PrioritizeJob(itemId, newPriority)

        if result.get("Success", False):
            fileName = result.get("FileName", "Unknown")
            oldPriority = result.get("OldPriority", 0)
            LoggingService.LogInfo(f"Updated priority for job {itemId} ({fileName}) from {oldPriority} to {newPriority}", "TranscodeQueueController", "PrioritizeJob")
            return jsonify(result)
        else:
            LoggingService.LogError(f"Failed to update job priority: {result.get('ErrorMessage', 'Unknown error')}", "TranscodeQueueController", "PrioritizeJob")
            return jsonify(result), 500

    except Exception as e:
        errorMsg = f"Exception updating job priority: {str(e)}"
        LoggingService.LogException(errorMsg, e, "TranscodeQueueController", "PrioritizeJob")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


class TranscodeQueueController:
    """Controller class for transcoding queue operations."""

    def __init__(self):
        """Initialize the controller with required services."""
        self.TranscodingService = TranscodingViewModel()
        self.ViewModel = TranscodeQueueViewModel(TranscodingService=self.TranscodingService)

    def StartTranscoding(self) -> Tuple[Dict[str, Any], int]:
        """Start transcoding the next item in the queue."""
        try:
            LoggingService.LogFunctionEntry("StartTranscoding", "TranscodeQueueController")

            # Get the next item from the queue
            result = self.TranscodingService.StartTranscoding()

            if result.get("Success", False):
                LoggingService.LogInfo(f"Started transcoding job: {result.get('JobId', 'Unknown')}", "TranscodeQueueController", "StartTranscoding")
                return result, 200
            else:
                errorCode = result.get("ErrorCode", "UNKNOWN_ERROR")
                if errorCode == "NO_QUEUE_ITEMS":
                    return result, 400
                else:
                    return result, 500

        except Exception as e:
            errorMsg = f"Exception starting transcoding: {str(e)}"
            LoggingService.LogException(errorMsg, e, "TranscodeQueueController", "StartTranscoding")
            return {
                "Success": False,
                "Error": errorMsg,
                "ErrorCode": "INTERNAL_SERVER_ERROR",
                "Timestamp": ToUtcIsoZ(datetime.now(timezone.utc))
            }, 500

    def GetTranscodeStatus(self, JobId: str) -> Tuple[Dict[str, Any], int]:
        """Get the status of a transcoding job."""
        try:
            LoggingService.LogFunctionEntry(f"GetTranscodeStatus({JobId})", "TranscodeQueueController")

            # Get job status from transcoding service
            result = self.TranscodingService.GetTranscodeStatus(JobId)

            if result.get("Success", False):
                # Reduced logging verbosity for routine status retrieval
                return result, 200
            else:
                errorCode = result.get("ErrorCode", "UNKNOWN_ERROR")
                if errorCode == "JOB_NOT_FOUND":
                    return result, 404
                else:
                    return result, 500

        except Exception as e:
            errorMsg = f"Exception getting transcoding status: {str(e)}"
            LoggingService.LogException(errorMsg, e, "TranscodeQueueController", "GetTranscodeStatus")
            return {
                "Success": False,
                "Error": errorMsg,
                "ErrorCode": "INTERNAL_SERVER_ERROR",
                "Timestamp": ToUtcIsoZ(datetime.now(timezone.utc))
            }, 500

    def GetTranscodeQueue(self) -> Tuple[Dict[str, Any], int]:
        """Get the current transcoding queue."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodeQueue", "TranscodeQueueController")

            # Get queue from transcoding service
            result = self.TranscodingService.GetTranscodeQueue()

            if result.get("Success", False):
                totalItems = result.get("TotalItems", 0)
                # Reduced logging verbosity for routine queue retrieval
                return result, 200
            else:
                return result, 500

        except Exception as e:
            errorMsg = f"Exception getting transcoding queue: {str(e)}"
            LoggingService.LogException(errorMsg, e, "TranscodeQueueController", "GetTranscodeQueue")
            return {
                "Success": False,
                "Error": errorMsg,
                "ErrorCode": "INTERNAL_SERVER_ERROR",
                "Timestamp": ToUtcIsoZ(datetime.now(timezone.utc))
            }, 500
