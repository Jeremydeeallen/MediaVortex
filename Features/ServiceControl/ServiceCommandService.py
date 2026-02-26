from typing import Dict, Any, Optional, List
from datetime import datetime
import json
from Repositories.DatabaseManager import DatabaseManager
from Core.Logging.LoggingService import LoggingService


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
            ) VALUES (%s, %s, %s, %s, 'Pending', %s, %s, NOW(), NOW())
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
            WHERE TargetService = %s AND Status = 'Pending'
            ORDER BY Priority DESC, CreatedAt ASC
            """

            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query, (TargetService,))

            commands = []
            for row in results:
                commands.append({
                    "Id": row['Id'],
                    "CommandType": row['CommandType'],
                    "SourceService": row['SourceService'],
                    "Parameters": json.loads(row['Parameters']) if row['Parameters'] else {},
                    "Priority": row['Priority'],
                    "CreatedAt": str(row['CreatedAt']) if row['CreatedAt'] else None
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
            SET Status = %s, ProcessedAt = NOW(), Result = %s,
                ErrorMessage = %s, UpdatedAt = NOW()
            WHERE Id = %s
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
            WHERE Id = %s
            """

            results = self.DatabaseManager.DatabaseService.ExecuteQuery(query, (CommandId,))

            if not results:
                return {"Success": False, "ErrorMessage": "Command not found"}

            row = results[0]
            result = {
                "Success": True,
                "Status": row['Status'],
                "Result": json.loads(row['Result']) if row['Result'] else {},
                "ErrorMessage": row['ErrorMessage'],
                "ProcessedAt": str(row['ProcessedAt']) if row['ProcessedAt'] else None
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
            AND CreatedAt < NOW() - INTERVAL '{} days'
            """.format(DaysOld)

            DeletedCount = self.DatabaseManager.DatabaseService.ExecuteNonQuery(query)

            LoggingService.LogInfo(f"Cleaned up {DeletedCount} old commands",
                                 "ServiceCommandService", "CleanupOldCommands")
            return DeletedCount

        except Exception as e:
            LoggingService.LogException("Error cleaning up old commands", e, "ServiceCommandService", "CleanupOldCommands")
            return 0

    def ProcessCommand(self, Command: Dict[str, Any]) -> Dict[str, Any]:
        """Process a service command."""
        try:
            LoggingService.LogFunctionEntry("ProcessCommand", "ServiceCommandService", Command['Id'])

            CommandId = Command['Id']
            CommandType = Command['CommandType']
            Parameters = Command['Parameters'] if 'Parameters' in Command else '{}'

            # Parse parameters if they're a JSON string
            if isinstance(Parameters, str):
                try:
                    Parameters = json.loads(Parameters)
                except json.JSONDecodeError:
                    Parameters = {}

            # Update command status to processing
            self.UpdateCommandStatus(CommandId, 'Processing')

            # Process command based on type
            Result = None
            Success = True
            ErrorMessage = None

            try:
                if CommandType == 'StartService':
                    Result = self.ProcessStartServiceCommand(Parameters)
                elif CommandType == 'StopService':
                    Result = self.ProcessStopServiceCommand(Parameters)
                elif CommandType == 'RestartService':
                    Result = self.ProcessRestartServiceCommand(Parameters)
                elif CommandType == 'GetStatus':
                    Result = self.ProcessGetStatusCommand(Parameters)
                elif CommandType == 'HealthCheck':
                    Result = self.ProcessHealthCheckCommand(Parameters)
                elif CommandType == 'StartQualityTesting':
                    Result = self.ProcessStartQualityTestingCommand(Parameters)
                else:
                    ErrorMessage = f"Unknown command type: {CommandType}"
                    Success = False

            except Exception as e:
                ErrorMessage = str(e)
                Success = False
                LoggingService.LogException(f"Error processing command {CommandId}", e,
                                          "ServiceCommandService", "ProcessCommand")

            # Update command status
            if Success:
                self.UpdateCommandStatus(CommandId, 'Completed', Result)
                LoggingService.LogInfo(f"Command {CommandId} processed successfully",
                                     "ServiceCommandService", "ProcessCommand")
            else:
                self.UpdateCommandStatus(CommandId, 'Failed', None, ErrorMessage)
                LoggingService.LogError(f"Command {CommandId} failed: {ErrorMessage}",
                                      "ServiceCommandService", "ProcessCommand")

            return {
                "Success": Success,
                "Result": Result,
                "ErrorMessage": ErrorMessage
            }

        except Exception as e:
            LoggingService.LogException("Exception processing command", e,
                                      "ServiceCommandService", "ProcessCommand")
            return {
                "Success": False,
                "Result": None,
                "ErrorMessage": str(e)
            }

    def ProcessStartServiceCommand(self, Parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Process start service command."""
        # This would typically start a service
        return {"Message": "Service start command processed", "Status": "Started"}

    def ProcessStopServiceCommand(self, Parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Process stop service command."""
        # This would typically stop a service
        return {"Message": "Service stop command processed", "Status": "Stopped"}

    def ProcessRestartServiceCommand(self, Parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Process restart service command."""
        # This would typically restart a service
        return {"Message": "Service restart command processed", "Status": "Restarted"}

    def ProcessGetStatusCommand(self, Parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Process get status command."""
        # This would typically return service status
        return {"Message": "Status command processed", "Status": "Running"}

    def ProcessHealthCheckCommand(self, Parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Process health check command."""
        # This would typically perform a health check
        return {"Message": "Health check command processed", "Status": "Healthy"}
