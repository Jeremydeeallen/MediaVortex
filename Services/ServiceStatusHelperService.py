"""
ServiceStatusHelperService
Simplified state management using ServiceStatus table as single source of truth
"""

from typing import Dict, Any, Optional
from datetime import datetime
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class ServiceStatusHelperService:
    """Helper service for managing transcoding state via ServiceStatus table."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
    
    def UpdateTranscodingStatus(self, Status: str, IsProcessing: bool = None, 
                               ActiveJobsCount: int = None) -> bool:
        """Update transcoding status in ServiceStatus table."""
        try:
            LoggingService.LogFunctionEntry("UpdateTranscodingStatus", "ServiceStatusHelperService")
            
            # Build update query dynamically based on provided parameters
            updateFields = ["Status = %s", "UpdatedAt = NOW()"]
            params = [Status]
            
            if IsProcessing is not None:
                updateFields.append("IsProcessing = %s")
                params.append(IsProcessing)
            
            if ActiveJobsCount is not None:
                updateFields.append("ActiveJobsCount = %s")
                params.append(ActiveJobsCount)
            
            params.append("TranscodeService")  # For WHERE clause
            
            query = f"""
            UPDATE ServiceStatus 
            SET {', '.join(updateFields)}
            WHERE ServiceName = %s
            """
            
            result = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, params)
            
            LoggingService.LogInfo(f"Updated TranscodeService status to: {Status}", 
                                 "ServiceStatusHelperService", "UpdateTranscodingStatus")
            return True
            
        except Exception as e:
            LoggingService.LogException("Error updating transcoding status", e, 
                                      "ServiceStatusHelperService", "UpdateTranscodingStatus")
            return False
    
    def GetTranscodingStatus(self) -> Dict[str, Any]:
        """Get current transcoding status from ServiceStatus table."""
        try:
            LoggingService.LogFunctionEntry("GetTranscodingStatus", "ServiceStatusHelperService")
            
            query = """
            SELECT Status, IsProcessing, ActiveJobsCount, LastHealthCheck
            FROM ServiceStatus 
            WHERE ServiceName = 'TranscodeService'
            """
            
            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query)
            
            if results and len(results) > 0:
                row = results[0]
                return {
                    "Success": True,
                    "Status": row['Status'],
                    "IsProcessing": bool(row['IsProcessing']) if row['IsProcessing'] is not None else False,
                    "ActiveJobsCount": row['ActiveJobsCount'] or 0,
                    "LastHealthCheck": str(row['LastHealthCheck']) if row['LastHealthCheck'] else None,
                    "IsTranscoding": bool(row['IsProcessing']) if row['IsProcessing'] is not None else False
                }
            else:
                return {
                    "Success": False,
                    "ErrorMessage": "TranscodeService status not found"
                }
                
        except Exception as e:
            LoggingService.LogException("Error getting transcoding status", e, 
                                      "ServiceStatusHelperService", "GetTranscodingStatus")
            return {
                "Success": False,
                "ErrorMessage": str(e)
            }
    
    def SetTranscodingStopped(self) -> bool:
        """Set transcoding status to stopped."""
        try:
            LoggingService.LogFunctionEntry("SetTranscodingStopped", "ServiceStatusHelperService")
            
            return self.UpdateTranscodingStatus(
                Status="Stopped",
                IsProcessing=False,
                ActiveJobsCount=0
            )
            
        except Exception as e:
            LoggingService.LogException("Error setting transcoding to stopped", e, 
                                      "ServiceStatusHelperService", "SetTranscodingStopped")
            return False
    
    def SetTranscodingStarted(self, MaxConcurrentJobs: int = 1) -> bool:
        """Set transcoding status to started."""
        try:
            LoggingService.LogFunctionEntry("SetTranscodingStarted", "ServiceStatusHelperService")
            
            return self.UpdateTranscodingStatus(
                Status="Running",
                IsProcessing=True,
                ActiveJobsCount=0  # Will be updated as jobs start
            )
            
        except Exception as e:
            LoggingService.LogException("Error setting transcoding to started", e, 
                                      "ServiceStatusHelperService", "SetTranscodingStarted")
            return False
    
    def SetTranscodingPaused(self) -> bool:
        """Set transcoding status to paused."""
        try:
            LoggingService.LogFunctionEntry("SetTranscodingPaused", "ServiceStatusHelperService")
            
            return self.UpdateTranscodingStatus(
                Status="Paused",
                IsProcessing=False
            )
            
        except Exception as e:
            LoggingService.LogException("Error setting transcoding to paused", e, 
                                      "ServiceStatusHelperService", "SetTranscodingPaused")
            return False
    
    def SetTranscodingResumed(self) -> bool:
        """Set transcoding status to resumed."""
        try:
            LoggingService.LogFunctionEntry("SetTranscodingResumed", "ServiceStatusHelperService")
            
            return self.UpdateTranscodingStatus(
                Status="Running",
                IsProcessing=True
            )
            
        except Exception as e:
            LoggingService.LogException("Error setting transcoding to resumed", e, 
                                      "ServiceStatusHelperService", "SetTranscodingResumed")
            return False
    
    def UpdateActiveJobsCount(self, ActiveJobsCount: int) -> bool:
        """Update the active jobs count."""
        try:
            LoggingService.LogFunctionEntry("UpdateActiveJobsCount", "ServiceStatusHelperService")
            
            return self.UpdateTranscodingStatus(
                Status="Running",  # Keep current status
                ActiveJobsCount=ActiveJobsCount
            )
            
        except Exception as e:
            LoggingService.LogException("Error updating active jobs count", e, 
                                      "ServiceStatusHelperService", "UpdateActiveJobsCount")
            return False
    
    
    
    
    
