from flask import Blueprint, request, jsonify
from typing import Dict, Any
from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager
from datetime import datetime


# Create Blueprint for queue reset routes
QueueResetBlueprint = Blueprint('QueueReset', __name__, url_prefix='/api/QueueReset')


@QueueResetBlueprint.route('/ResetAllQueues', methods=['POST'])
def ResetAllQueues():
    """Reset all queues and clear all processing states."""
    try:
        LoggingService.LogFunctionEntry("ResetAllQueues", "QueueResetController")
        
        # Get parameters from request
        data = request.get_json() or {}
        resetType = data.get('ResetType', 'All')  # 'All', 'Transcode', 'Quality', 'Service'
        confirmReset = data.get('ConfirmReset', False)
        
        # Validate parameters
        if not confirmReset:
            errorMsg = "Reset operation requires confirmation. Set ConfirmReset to true."
            LoggingService.LogError(errorMsg, "QueueResetController", "ResetAllQueues")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400
        
        if resetType not in ['All', 'Transcode', 'Quality', 'Service']:
            errorMsg = "ResetType must be one of: All, Transcode, Quality, Service"
            LoggingService.LogError(errorMsg, "QueueResetController", "ResetAllQueues")
            return jsonify({"Success": False, "ErrorMessage": errorMsg}), 400
        
        # Create DatabaseManager instance
        databaseManager = DatabaseManager()
        
        # Perform reset operations based on type
        resetResults = {}
        
        if resetType in ['All', 'Transcode']:
            # Reset Transcode Queue
            transcodeResult = ResetTranscodeQueue(databaseManager)
            resetResults['TranscodeQueue'] = transcodeResult
            
            # Reset Transcode Attempts (mark as cancelled)
            attemptsResult = ResetTranscodeAttempts(databaseManager)
            resetResults['TranscodeAttempts'] = attemptsResult
            
            # Reset Transcode Progress
            progressResult = ResetTranscodeProgress(databaseManager)
            resetResults['TranscodeProgress'] = progressResult
        
        
        if resetType in ['All', 'Service']:
            # Reset Service Commands
            serviceResult = ResetServiceCommands(databaseManager)
            resetResults['ServiceCommands'] = serviceResult
        
        # Check if all operations were successful
        allSuccessful = all(result.get('Success', False) for result in resetResults.values())
        
        if allSuccessful:
            totalItemsReset = sum(result.get('ItemsReset', 0) for result in resetResults.values())
            LoggingService.LogInfo(f"Successfully reset all queues. Total items reset: {totalItemsReset}", 
                                 "QueueResetController", "ResetAllQueues")
            return jsonify({
                "Success": True,
                "Message": f"Successfully reset {resetType.lower()} queues",
                "TotalItemsReset": totalItemsReset,
                "ResetResults": resetResults,
                "Timestamp": datetime.now().isoformat()
            })
        else:
            failedOperations = [name for name, result in resetResults.items() if not result.get('Success', False)]
            errorMsg = f"Some reset operations failed: {', '.join(failedOperations)}"
            LoggingService.LogError(errorMsg, "QueueResetController", "ResetAllQueues")
            return jsonify({
                "Success": False,
                "ErrorMessage": errorMsg,
                "ResetResults": resetResults
            }), 500
            
    except Exception as e:
        errorMsg = f"Exception resetting queues: {str(e)}"
        LoggingService.LogException(errorMsg, e, "QueueResetController", "ResetAllQueues")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


def ResetTranscodeQueue(databaseManager: DatabaseManager) -> Dict[str, Any]:
    """Reset the TranscodeQueue table by putting running items back to pending."""
    try:
        LoggingService.LogFunctionEntry("ResetTranscodeQueue", "QueueResetController")
        
        # Get count of running items to be reset
        countQuery = "SELECT COUNT(*) as Count FROM TranscodeQueue WHERE Status = 'Running'"
        countResult = databaseManager.DatabaseService.ExecuteQuery(countQuery)
        
        if not countResult:
            return {"Success": False, "ErrorMessage": "Failed to count running queue items"}
        
        itemsToReset = countResult[0]['Count'] if countResult else 0
        
        # Reset running items back to pending status
        resetQuery = "UPDATE TranscodeQueue SET Status = 'Pending', DateStarted = NULL WHERE Status = 'Running'"
        resetResult = databaseManager.DatabaseService.ExecuteNonQuery(resetQuery)
        
        if resetResult is not None:
            LoggingService.LogInfo(f"Reset {itemsToReset} running items back to pending in TranscodeQueue", 
                                 "QueueResetController", "ResetTranscodeQueue")
            return {
                "Success": True,
                "ItemsReset": itemsToReset,
                "Message": f"Reset {itemsToReset} running items back to pending in TranscodeQueue"
            }
        else:
            return {"Success": False, "ErrorMessage": "Failed to reset TranscodeQueue"}
            
    except Exception as e:
        errorMsg = f"Exception resetting TranscodeQueue: {str(e)}"
        LoggingService.LogException(errorMsg, e, "QueueResetController", "ResetTranscodeQueue")
        return {"Success": False, "ErrorMessage": errorMsg}


def ResetTranscodeAttempts(databaseManager: DatabaseManager) -> Dict[str, Any]:
    """Reset running TranscodeAttempts by marking them as terminated."""
    try:
        LoggingService.LogFunctionEntry("ResetTranscodeAttempts", "QueueResetController")
        
        # Get count of running attempts
        countQuery = "SELECT COUNT(*) as Count FROM TranscodeAttempts WHERE Success IS NULL"
        countResult = databaseManager.DatabaseService.ExecuteQuery(countQuery)
        
        if not countResult:
            return {"Success": False, "ErrorMessage": "Failed to count transcode attempts"}
        
        itemsToReset = countResult[0]['Count'] if countResult else 0
        
        # Mark running attempts as terminated (set Success to False and add error message)
        updateQuery = """UPDATE TranscodeAttempts 
                        SET Success = FALSE,
                            ErrorMessage = 'Terminated due to system reset',
                            AttemptDate = NOW()
                        WHERE Success IS NULL"""
        updateResult = databaseManager.DatabaseService.ExecuteNonQuery(updateQuery)
        
        if updateResult is not None:
            LoggingService.LogInfo(f"Marked {itemsToReset} transcode attempts as terminated", 
                                 "QueueResetController", "ResetTranscodeAttempts")
            return {
                "Success": True,
                "ItemsReset": itemsToReset,
                "Message": f"Marked {itemsToReset} transcode attempts as terminated"
            }
        else:
            return {"Success": False, "ErrorMessage": "Failed to update TranscodeAttempts"}
            
    except Exception as e:
        errorMsg = f"Exception resetting TranscodeAttempts: {str(e)}"
        LoggingService.LogException(errorMsg, e, "QueueResetController", "ResetTranscodeAttempts")
        return {"Success": False, "ErrorMessage": errorMsg}


def ResetTranscodeProgress(databaseManager: DatabaseManager) -> Dict[str, Any]:
    """Reset TranscodeProgress entries."""
    try:
        LoggingService.LogFunctionEntry("ResetTranscodeProgress", "QueueResetController")
        
        # Get count of active progress entries
        countQuery = "SELECT COUNT(*) as Count FROM TranscodeProgress WHERE Status = 'Running'"
        countResult = databaseManager.DatabaseService.ExecuteQuery(countQuery)
        
        if not countResult:
            return {"Success": False, "ErrorMessage": "Failed to count progress entries"}
        
        itemsToReset = countResult[0]['Count'] if countResult else 0
        
        # Clear all running progress entries
        clearQuery = "DELETE FROM TranscodeProgress WHERE Status = 'Running'"
        clearResult = databaseManager.DatabaseService.ExecuteNonQuery(clearQuery)
        
        if clearResult is not None:
            LoggingService.LogInfo(f"Cleared {itemsToReset} progress entries", 
                                 "QueueResetController", "ResetTranscodeProgress")
            return {
                "Success": True,
                "ItemsReset": itemsToReset,
                "Message": f"Cleared {itemsToReset} progress entries"
            }
        else:
            return {"Success": False, "ErrorMessage": "Failed to clear TranscodeProgress"}
            
    except Exception as e:
        errorMsg = f"Exception resetting TranscodeProgress: {str(e)}"
        LoggingService.LogException(errorMsg, e, "QueueResetController", "ResetTranscodeProgress")
        return {"Success": False, "ErrorMessage": errorMsg}






def ResetServiceCommands(databaseManager: DatabaseManager) -> Dict[str, Any]:
    """Reset ServiceCommands by marking pending commands as cancelled."""
    try:
        LoggingService.LogFunctionEntry("ResetServiceCommands", "QueueResetController")
        
        # Get count of pending commands
        countQuery = "SELECT COUNT(*) as Count FROM ServiceCommands WHERE Status = 'Pending'"
        countResult = databaseManager.DatabaseService.ExecuteQuery(countQuery)
        
        if not countResult:
            return {"Success": False, "ErrorMessage": "Failed to count service commands"}
        
        itemsToReset = countResult[0]['Count'] if countResult else 0
        
        # Mark pending commands as cancelled
        updateQuery = """UPDATE ServiceCommands 
                        SET Status = 'Cancelled',
                            Result = 'Cancelled due to system reset',
                            ProcessedAt = NOW()
                        WHERE Status = 'Pending'"""
        updateResult = databaseManager.DatabaseService.ExecuteNonQuery(updateQuery)
        
        if updateResult is not None:
            LoggingService.LogInfo(f"Marked {itemsToReset} service commands as cancelled", 
                                 "QueueResetController", "ResetServiceCommands")
            return {
                "Success": True,
                "ItemsReset": itemsToReset,
                "Message": f"Marked {itemsToReset} service commands as cancelled"
            }
        else:
            return {"Success": False, "ErrorMessage": "Failed to update ServiceCommands"}
            
    except Exception as e:
        errorMsg = f"Exception resetting ServiceCommands: {str(e)}"
        LoggingService.LogException(errorMsg, e, "QueueResetController", "ResetServiceCommands")
        return {"Success": False, "ErrorMessage": errorMsg}


@QueueResetBlueprint.route('/GetQueueStatus', methods=['GET'])
def GetQueueStatus():
    """Get current status of all queues."""
    try:
        LoggingService.LogFunctionEntry("GetQueueStatus", "QueueResetController")
        
        # Create DatabaseManager instance
        databaseManager = DatabaseManager()
        
        # Get status of all queues
        queueStatus = {}
        
        # TranscodeQueue status
        transcodeQuery = "SELECT Status, COUNT(*) as Count FROM TranscodeQueue GROUP BY Status"
        transcodeResult = databaseManager.DatabaseService.ExecuteQuery(transcodeQuery)
        if transcodeResult:
            queueStatus['TranscodeQueue'] = {item['Status']: item['Count'] for item in transcodeResult}
        else:
            queueStatus['TranscodeQueue'] = {'Error': 'Failed to get status'}
        
        
        # ServiceCommands status
        serviceQuery = "SELECT Status, COUNT(*) as Count FROM ServiceCommands GROUP BY Status"
        serviceResult = databaseManager.DatabaseService.ExecuteQuery(serviceQuery)
        if serviceResult:
            queueStatus['ServiceCommands'] = {item['Status']: item['Count'] for item in serviceResult}
        else:
            queueStatus['ServiceCommands'] = {'Error': 'Failed to get status'}
        
        # TranscodeAttempts status
        attemptsQuery = "SELECT CASE WHEN Success IS NULL THEN 'Running' WHEN Success = TRUE THEN 'Completed' ELSE 'Failed' END as Status, COUNT(*) as Count FROM TranscodeAttempts GROUP BY Status"
        attemptsResult = databaseManager.DatabaseService.ExecuteQuery(attemptsQuery)
        if attemptsResult:
            queueStatus['TranscodeAttempts'] = {item['Status']: item['Count'] for item in attemptsResult}
        else:
            queueStatus['TranscodeAttempts'] = {'Error': 'Failed to get status'}
        
        return jsonify({
            "Success": True,
            "QueueStatus": queueStatus,
            "Timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        errorMsg = f"Exception getting queue status: {str(e)}"
        LoggingService.LogException(errorMsg, e, "QueueResetController", "GetQueueStatus")
        return jsonify({"Success": False, "ErrorMessage": errorMsg}), 500


class QueueResetController:
    """Controller class for queue reset operations."""
    
    def __init__(self):
        """Initialize the controller with required services."""
        self.DatabaseManager = DatabaseManager()
    
    def ResetAllQueues(self, resetType: str = 'All', confirmReset: bool = False) -> Dict[str, Any]:
        """Reset all queues and clear all processing states."""
        try:
            LoggingService.LogFunctionEntry(f"ResetAllQueues({resetType}, {confirmReset})", "QueueResetController")
            
            if not confirmReset:
                return {
                    "Success": False,
                    "ErrorMessage": "Reset operation requires confirmation"
                }
            
            if resetType not in ['All', 'Transcode', 'Quality', 'Service']:
                return {
                    "Success": False,
                    "ErrorMessage": "ResetType must be one of: All, Transcode, Quality, Service"
                }
            
            # Perform reset operations based on type
            resetResults = {}
            
            if resetType in ['All', 'Transcode']:
                resetResults['TranscodeQueue'] = ResetTranscodeQueue(self.DatabaseManager)
                resetResults['TranscodeAttempts'] = ResetTranscodeAttempts(self.DatabaseManager)
                resetResults['TranscodeProgress'] = ResetTranscodeProgress(self.DatabaseManager)
            
            
            if resetType in ['All', 'Service']:
                resetResults['ServiceCommands'] = ResetServiceCommands(self.DatabaseManager)
            
            # Check if all operations were successful
            allSuccessful = all(result.get('Success', False) for result in resetResults.values())
            
            if allSuccessful:
                totalItemsReset = sum(result.get('ItemsReset', 0) for result in resetResults.values())
                return {
                    "Success": True,
                    "Message": f"Successfully reset {resetType.lower()} queues",
                    "TotalItemsReset": totalItemsReset,
                    "ResetResults": resetResults
                }
            else:
                failedOperations = [name for name, result in resetResults.items() if not result.get('Success', False)]
                return {
                    "Success": False,
                    "ErrorMessage": f"Some reset operations failed: {', '.join(failedOperations)}",
                    "ResetResults": resetResults
                }
                
        except Exception as e:
            errorMsg = f"Exception resetting queues: {str(e)}"
            LoggingService.LogException(errorMsg, e, "QueueResetController", "ResetAllQueues")
            return {"Success": False, "ErrorMessage": errorMsg}
