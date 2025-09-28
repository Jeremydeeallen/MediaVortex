from typing import Dict, Any, Optional, List
from datetime import datetime
import json
from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


class ServiceCommandService:
    """Service for managing inter-service communication via database commands."""
    
    def __init__(self, DatabaseManagerInstance: DatabaseManager = None):
        self.DatabaseManager = DatabaseManagerInstance or DatabaseManager()
    
    def CreateCommand(self, CommandType: str, SourceService: str, TargetService: str, 
                     Parameters: Dict[str, Any] = None, Priority: int = 1, 
                     CreatedBy: str = "MediaVortex") -> Dict[str, Any]:
        """Create a new service command."""
        try:
            LoggingService.LogFunctionEntry("CreateCommand", "ServiceCommandService")
            
            # Prepare parameters as JSON string
            ParametersJson = json.dumps(Parameters) if Parameters else "{}"
            
            # Insert command into database
            query = """
            INSERT INTO ServiceCommands (
                CommandType, SourceService, TargetService, Parameters, 
                Status, Priority, CreatedBy, CreatedAt, UpdatedAt
            ) VALUES (?, ?, ?, ?, 'Pending', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
            
            params = (CommandType, SourceService, TargetService, ParametersJson, 
                     Priority, CreatedBy)
            
            CommandId = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, params)
            
            LoggingService.LogInfo(f"Created command {CommandId}: {CommandType} from {SourceService} to {TargetService}", 
                                 "ServiceCommandService", "CreateCommand")
            
            return {
                "Success": True,
                "CommandId": CommandId,
                "Message": f"Command {CommandType} queued for {TargetService}",
                "Status": "Pending"
            }
            
        except Exception as e:
            errorMsg = f"Error creating command: {str(e)}"
            LoggingService.LogException(errorMsg, e, "ServiceCommandService", "CreateCommand")
            return {"Success": False, "ErrorMessage": errorMsg}
    
    def GetPendingCommands(self, TargetService: str) -> List[Dict[str, Any]]:
        """Get pending commands for a specific service."""
        try:
            query = """
            SELECT Id, CommandType, SourceService, Parameters, Priority, CreatedAt
            FROM ServiceCommands 
            WHERE TargetService = ? AND Status = 'Pending'
            ORDER BY Priority DESC, CreatedAt ASC
            """
            
            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query, (TargetService,))
            
            commands = []
            for row in results:
                commands.append({
                    "Id": row[0],
                    "CommandType": row[1],
                    "SourceService": row[2],
                    "Parameters": json.loads(row[3]) if row[3] else {},
                    "Priority": row[4],
                    "CreatedAt": row[5]
                })
            
            return commands
            
        except Exception as e:
            LoggingService.LogException("Error getting pending commands", e, "ServiceCommandService", "GetPendingCommands")
            return []
    
    def UpdateCommandStatus(self, CommandId: int, Status: str, 
                           Result: Dict[str, Any] = None, ErrorMessage: str = None) -> bool:
        """Update command status and result."""
        try:
            ResultJson = json.dumps(Result) if Result else None
            
            query = """
            UPDATE ServiceCommands 
            SET Status = ?, ProcessedAt = CURRENT_TIMESTAMP, Result = ?, 
                ErrorMessage = ?, UpdatedAt = CURRENT_TIMESTAMP
            WHERE Id = ?
            """
            
            params = (Status, ResultJson, ErrorMessage, CommandId)
            self.DatabaseManager.DatabaseService.ExecuteNonQuery(query, params)
            
            LoggingService.LogInfo(f"Updated command {CommandId} status to {Status}", 
                                 "ServiceCommandService", "UpdateCommandStatus")
            return True
            
        except Exception as e:
            LoggingService.LogException("Error updating command status", e, "ServiceCommandService", "UpdateCommandStatus")
            return False
    
    def GetCommandResult(self, CommandId: int) -> Dict[str, Any]:
        """Get command result by ID."""
        try:
            query = """
            SELECT Status, Result, ErrorMessage, ProcessedAt
            FROM ServiceCommands 
            WHERE Id = ?
            """
            
            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query, (CommandId,))
            
            if not results:
                return {"Success": False, "ErrorMessage": "Command not found"}
            
            row = results[0]
            result = {
                "Success": True,
                "Status": row[0],
                "Result": json.loads(row[1]) if row[1] else {},
                "ErrorMessage": row[2],
                "ProcessedAt": row[3]
            }
            
            return result
            
        except Exception as e:
            LoggingService.LogException("Error getting command result", e, "ServiceCommandService", "GetCommandResult")
            return {"Success": False, "ErrorMessage": str(e)}
    
    def CleanupOldCommands(self, DaysOld: int = 7) -> int:
        """Clean up old completed commands."""
        try:
            query = """
            DELETE FROM ServiceCommands 
            WHERE Status IN ('Completed', 'Failed') 
            AND CreatedAt < datetime('now', '-{} days')
            """.format(DaysOld)
            
            DeletedCount = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query)
            
            LoggingService.LogInfo(f"Cleaned up {DeletedCount} old commands", 
                                 "ServiceCommandService", "CleanupOldCommands")
            return DeletedCount
            
        except Exception as e:
            LoggingService.LogException("Error cleaning up old commands", e, "ServiceCommandService", "CleanupOldCommands")
            return 0
