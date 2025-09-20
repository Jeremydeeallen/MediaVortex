from flask import Blueprint, request, jsonify, render_template
from typing import Dict, Any
from ViewModels.TranscodeQueueViewModel import TranscodeQueueViewModel
from Services.LoggingService import LoggingService


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
        sortBy = request.args.get('sortBy', 'SizeMB')
        sortOrder = request.args.get('sortOrder', 'DESC')
        
        # Validate parameters
        if page < 1:
            page = 1
        if pageSize < 1 or pageSize > 100:
            pageSize = 25
        if sortBy not in ['SizeMB', 'Priority', 'DateAdded', 'FileName']:
            sortBy = 'SizeMB'
        if sortOrder not in ['ASC', 'DESC']:
            sortOrder = 'DESC'
        
        # Create ViewModel instance
        viewModel = TranscodeQueueViewModel()
        
        # Load queue items with pagination
        result = viewModel.LoadQueueItems(page, pageSize, sortBy, sortOrder)
        
        if result.get("Success", False):
            LoggingService.LogInfo(f"Retrieved {result.get('Count', 0)} queue items (page {page} of {result.get('TotalPages', 1)})", "TranscodeQueueController", "GetQueue")
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
        maxItems = data.get('MaxItems', 100)
        
        # Validate parameters
        if not isinstance(maxItems, int) or maxItems < 1 or maxItems > 1000:
            errorMsg = "MaxItems must be an integer between 1 and 1000"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "PopulateQueue")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400
        
        # Create ViewModel instance
        viewModel = TranscodeQueueViewModel()
        
        # Populate queue
        result = viewModel.PopulateQueue(maxItems)
        
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
        
        # Validate parameters
        if not mediaFileId:
            errorMsg = "MediaFileId is required"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "AddJob")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400
        
        if not isinstance(mediaFileId, int) or mediaFileId < 1:
            errorMsg = "MediaFileId must be a positive integer"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "AddJob")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400
        
        if priority is not None and (not isinstance(priority, int) or priority < 1 or priority > 100):
            errorMsg = "Priority must be an integer between 1 and 100"
            LoggingService.LogError(errorMsg, "TranscodeQueueController", "AddJob")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400
        
        # Create ViewModel instance
        viewModel = TranscodeQueueViewModel()
        
        # Add job to queue
        result = viewModel.AddJobToQueue(mediaFileId, priority, profileId)
        
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
        
        if not isinstance(newPriority, int) or newPriority < 1 or newPriority > 100:
            errorMsg = "NewPriority must be an integer between 1 and 100"
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


