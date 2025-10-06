"""
CleanupTranscodingCommands.py
Clean up old transcoding ServiceCommands that are no longer needed
"""

import sys
import os
from datetime import datetime

# Add parent directory to path to import shared services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService


def CleanupOldTranscodingCommands():
    """Clean up old transcoding ServiceCommands."""
    try:
        LoggingService.LogFunctionEntry("CleanupOldTranscodingCommands", "CleanupTranscodingCommands")
        
        DatabaseManagerInstance = DatabaseManager()
        
        # Get count of old transcoding commands
        countQuery = """
        SELECT COUNT(*) FROM ServiceCommands 
        WHERE TargetService = 'TranscodeService' 
        AND CommandType IN ('StartTranscoding', 'StopTranscoding', 'PauseTranscoding', 'ResumeTranscoding')
        """
        
        countResult = DatabaseManagerInstance.DatabaseService.ExecuteQuery(countQuery)
        oldCommandCount = countResult[0][0] if countResult and len(countResult) > 0 else 0
        
        LoggingService.LogInfo(f"Found {oldCommandCount} old transcoding commands to clean up", 
                             "CleanupTranscodingCommands", "CleanupOldTranscodingCommands")
        
        if oldCommandCount > 0:
            # Delete old transcoding commands
            deleteQuery = """
            DELETE FROM ServiceCommands 
            WHERE TargetService = 'TranscodeService' 
            AND CommandType IN ('StartTranscoding', 'StopTranscoding', 'PauseTranscoding', 'ResumeTranscoding')
            """
            
            deletedCount = DatabaseManagerInstance.DatabaseService.ExecuteNonQuery(deleteQuery)
            
            LoggingService.LogInfo(f"Cleaned up {deletedCount} old transcoding commands", 
                                 "CleanupTranscodingCommands", "CleanupOldTranscodingCommands")
            
            return {
                "Success": True,
                "Message": f"Cleaned up {deletedCount} old transcoding commands",
                "DeletedCount": deletedCount
            }
        else:
            LoggingService.LogInfo("No old transcoding commands found to clean up", 
                                 "CleanupTranscodingCommands", "CleanupOldTranscodingCommands")
            return {
                "Success": True,
                "Message": "No old transcoding commands found",
                "DeletedCount": 0
            }
            
    except Exception as e:
        LoggingService.LogException("Error cleaning up old transcoding commands", e, 
                                  "CleanupTranscodingCommands", "CleanupOldTranscodingCommands")
        return {
            "Success": False,
            "ErrorMessage": str(e)
        }


def Main():
    """Main entry point for cleanup script."""
    try:
        LoggingService.LogInfo("Starting cleanup of old transcoding commands...", 
                             "CleanupTranscodingCommands", "Main")
        
        result = CleanupOldTranscodingCommands()
        
        if result.get("Success", False):
            LoggingService.LogInfo(f"Cleanup completed successfully: {result.get('Message', '')}", 
                                 "CleanupTranscodingCommands", "Main")
            print(f"SUCCESS: {result.get('Message', '')}")
        else:
            LoggingService.LogError(f"Cleanup failed: {result.get('ErrorMessage', 'Unknown error')}", 
                                  "CleanupTranscodingCommands", "Main")
            print(f"ERROR: {result.get('ErrorMessage', 'Unknown error')}")
            sys.exit(1)
            
    except Exception as e:
        LoggingService.LogException("Fatal error in cleanup script", e, 
                                  "CleanupTranscodingCommands", "Main")
        print(f"FATAL ERROR: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    Main()
