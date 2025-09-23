#!/usr/bin/env python3
"""
CheckLogsForIssues.py - Flexible log analysis tool for MediaVortex
Usage: python CheckLogsForIssues.py [issue_type] [options]
"""

import sys
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any

class LogChecker:
    def __init__(self, DatabasePath: str = "Data/MediaVortex.db"):
        self.DatabasePath = DatabasePath
    
    def ConnectToDatabase(self):
        """Connect to the SQLite database."""
        try:
            Connection = sqlite3.connect(self.DatabasePath)
            Connection.row_factory = sqlite3.Row
            return Connection
        except Exception as e:
            print(f"Error connecting to database: {e}")
            return None
    
    def CheckFileScanningIssues(self, HoursBack: int = 24, Limit: int = 50):
        """Check for file scanning related issues."""
        print(f"\n=== File Scanning Issues (Last {HoursBack} hours) ===")
        
        Connection = self.ConnectToDatabase()
        if not Connection:
            return
        
        try:
            Cursor = Connection.cursor()
            
            # Check for errors and warnings
            ErrorQuery = """
                SELECT Timestamp, LogLevel, Message, Component, FunctionName
                FROM Logs 
                WHERE LogLevel IN ('ERROR', 'WARNING') 
                AND (Message LIKE '%scan%' OR Message LIKE '%ffprobe%' OR Message LIKE '%ffmpeg%' OR Message LIKE '%file%')
                AND Timestamp > datetime('now', '-{} hours')
                ORDER BY Timestamp DESC
                LIMIT {}
            """.format(HoursBack, Limit)
            
            Rows = Cursor.execute(ErrorQuery).fetchall()
            
            if Rows:
                print(f"Found {len(Rows)} errors/warnings:")
                for Row in Rows:
                    print(f"  {Row['Timestamp']} [{Row['LogLevel']}] {Row['Component']}.{Row['FunctionName']}: {Row['Message']}")
            else:
                print("No file scanning errors/warnings found.")
            
            # Check for scan completion messages
            CompletionQuery = """
                SELECT Timestamp, Message, Component, FunctionName
                FROM Logs 
                WHERE Message LIKE '%scan%' AND (Message LIKE '%complete%' OR Message LIKE '%finished%' OR Message LIKE '%stopped%')
                AND Timestamp > datetime('now', '-{} hours')
                ORDER BY Timestamp DESC
                LIMIT 10
            """.format(HoursBack)
            
            CompletionRows = Cursor.execute(CompletionQuery).fetchall()
            
            if CompletionRows:
                print(f"\nScan completion messages:")
                for Row in CompletionRows:
                    print(f"  {Row['Timestamp']} {Row['Component']}.{Row['FunctionName']}: {Row['Message']}")
            
        except Exception as e:
            print(f"Error checking file scanning issues: {e}")
        finally:
            Connection.close()
    
    def CheckDatabaseIssues(self, HoursBack: int = 24, Limit: int = 50):
        """Check for database related issues."""
        print(f"\n=== Database Issues (Last {HoursBack} hours) ===")
        
        Connection = self.ConnectToDatabase()
        if not Connection:
            return
        
        try:
            Cursor = Connection.cursor()
            
            # Check for database errors
            ErrorQuery = """
                SELECT Timestamp, LogLevel, Message, Component, FunctionName
                FROM Logs 
                WHERE LogLevel IN ('ERROR', 'WARNING') 
                AND (Message LIKE '%database%' OR Message LIKE '%sql%' OR Message LIKE '%table%' OR Message LIKE '%column%')
                AND Timestamp > datetime('now', '-{} hours')
                ORDER BY Timestamp DESC
                LIMIT {}
            """.format(HoursBack, Limit)
            
            Rows = Cursor.execute(ErrorQuery).fetchall()
            
            if Rows:
                print(f"Found {len(Rows)} database errors/warnings:")
                for Row in Rows:
                    print(f"  {Row['Timestamp']} [{Row['LogLevel']}] {Row['Component']}.{Row['FunctionName']}: {Row['Message']}")
            else:
                print("No database errors/warnings found.")
            
        except Exception as e:
            print(f"Error checking database issues: {e}")
        finally:
            Connection.close()
    
    def CheckFFmpegIssues(self, HoursBack: int = 24, Limit: int = 50):
        """Check for FFmpeg/FFprobe related issues."""
        print(f"\n=== FFmpeg/FFprobe Issues (Last {HoursBack} hours) ===")
        
        Connection = self.ConnectToDatabase()
        if not Connection:
            return
        
        try:
            Cursor = Connection.cursor()
            
            # Check for FFmpeg errors
            ErrorQuery = """
                SELECT Timestamp, LogLevel, Message, Component, FunctionName
                FROM Logs 
                WHERE LogLevel IN ('ERROR', 'WARNING') 
                AND (Message LIKE '%ffmpeg%' OR Message LIKE '%ffprobe%' OR Message LIKE '%command%' OR Message LIKE '%executable%')
                AND Timestamp > datetime('now', '-{} hours')
                ORDER BY Timestamp DESC
                LIMIT {}
            """.format(HoursBack, Limit)
            
            Rows = Cursor.execute(ErrorQuery).fetchall()
            
            if Rows:
                print(f"Found {len(Rows)} FFmpeg/FFprobe errors/warnings:")
                for Row in Rows:
                    print(f"  {Row['Timestamp']} [{Row['LogLevel']}] {Row['Component']}.{Row['FunctionName']}: {Row['Message']}")
            else:
                print("No FFmpeg/FFprobe errors/warnings found.")
            
        except Exception as e:
            print(f"Error checking FFmpeg issues: {e}")
        finally:
            Connection.close()
    
    def CheckRecentActivity(self, HoursBack: int = 2, Limit: int = 100):
        """Check recent activity across all components."""
        print(f"\n=== Recent Activity (Last {HoursBack} hours) ===")
        
        Connection = self.ConnectToDatabase()
        if not Connection:
            return
        
        try:
            Cursor = Connection.cursor()
            
            # Get recent logs
            Query = """
                SELECT Timestamp, LogLevel, Message, Component, FunctionName
                FROM Logs 
                WHERE Timestamp > datetime('now', '-{} hours')
                ORDER BY Timestamp DESC
                LIMIT {}
            """.format(HoursBack, Limit)
            
            Rows = Cursor.execute(Query).fetchall()
            
            if Rows:
                print(f"Found {len(Rows)} recent log entries:")
                for Row in Rows:
                    Level = Row['LogLevel']
                    Color = "🔴" if Level == "ERROR" else "🟡" if Level == "WARNING" else "🔵"
                    print(f"  {Color} {Row['Timestamp']} [{Level}] {Row['Component']}.{Row['FunctionName']}: {Row['Message']}")
            else:
                print("No recent activity found.")
            
        except Exception as e:
            print(f"Error checking recent activity: {e}")
        finally:
            Connection.close()
    
    def CheckSpecificError(self, ErrorPattern: str, HoursBack: int = 24, Limit: int = 50):
        """Check for specific error patterns."""
        print(f"\n=== Specific Error Pattern: '{ErrorPattern}' (Last {HoursBack} hours) ===")
        
        Connection = self.ConnectToDatabase()
        if not Connection:
            return
        
        try:
            Cursor = Connection.cursor()
            
            # Search for specific error pattern
            Query = """
                SELECT Timestamp, LogLevel, Message, Component, FunctionName
                FROM Logs 
                WHERE Message LIKE ?
                AND Timestamp > datetime('now', '-{} hours')
                ORDER BY Timestamp DESC
                LIMIT {}
            """.format(HoursBack, Limit)
            
            Rows = Cursor.execute(Query, (f'%{ErrorPattern}%',)).fetchall()
            
            if Rows:
                print(f"Found {len(Rows)} matching entries:")
                for Row in Rows:
                    print(f"  {Row['Timestamp']} [{Row['LogLevel']}] {Row['Component']}.{Row['FunctionName']}: {Row['Message']}")
            else:
                print(f"No entries found matching pattern: {ErrorPattern}")
            
        except Exception as e:
            print(f"Error checking specific error: {e}")
        finally:
            Connection.close()

def PrintUsage():
    """Print usage information."""
    print("""
CheckLogsForIssues.py - Flexible log analysis tool for MediaVortex

Usage:
  python CheckLogsForIssues.py [command] [options]

Commands:
  scan [hours] [limit]     - Check file scanning issues (default: 24 hours, 50 limit)
  database [hours] [limit] - Check database issues (default: 24 hours, 50 limit)
  ffmpeg [hours] [limit]   - Check FFmpeg/FFprobe issues (default: 24 hours, 50 limit)
  recent [hours] [limit]   - Check recent activity (default: 2 hours, 100 limit)
  search <pattern> [hours] [limit] - Search for specific error pattern (default: 24 hours, 50 limit)
  all [hours]              - Run all checks (default: 24 hours)

Examples:
  python CheckLogsForIssues.py scan
  python CheckLogsForIssues.py scan 48 100
  python CheckLogsForIssues.py search "stopped" 12
  python CheckLogsForIssues.py recent 1
  python CheckLogsForIssues.py all 6
""")

def main():
    """Main function to handle command line arguments."""
    if len(sys.argv) < 2:
        PrintUsage()
        return
    
    Command = sys.argv[1].lower()
    Checker = LogChecker()
    
    if Command == "scan":
        HoursBack = int(sys.argv[2]) if len(sys.argv) > 2 else 24
        Limit = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        Checker.CheckFileScanningIssues(HoursBack, Limit)
    
    elif Command == "database":
        HoursBack = int(sys.argv[2]) if len(sys.argv) > 2 else 24
        Limit = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        Checker.CheckDatabaseIssues(HoursBack, Limit)
    
    elif Command == "ffmpeg":
        HoursBack = int(sys.argv[2]) if len(sys.argv) > 2 else 24
        Limit = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        Checker.CheckFFmpegIssues(HoursBack, Limit)
    
    elif Command == "recent":
        HoursBack = int(sys.argv[2]) if len(sys.argv) > 2 else 2
        Limit = int(sys.argv[3]) if len(sys.argv) > 3 else 100
        Checker.CheckRecentActivity(HoursBack, Limit)
    
    elif Command == "search":
        if len(sys.argv) < 3:
            print("Error: search command requires a pattern")
            PrintUsage()
            return
        Pattern = sys.argv[2]
        HoursBack = int(sys.argv[3]) if len(sys.argv) > 3 else 24
        Limit = int(sys.argv[4]) if len(sys.argv) > 4 else 50
        Checker.CheckSpecificError(Pattern, HoursBack, Limit)
    
    elif Command == "all":
        HoursBack = int(sys.argv[2]) if len(sys.argv) > 2 else 24
        Checker.CheckFileScanningIssues(HoursBack, 50)
        Checker.CheckDatabaseIssues(HoursBack, 50)
        Checker.CheckFFmpegIssues(HoursBack, 50)
        Checker.CheckRecentActivity(2, 100)
    
    else:
        print(f"Unknown command: {Command}")
        PrintUsage()

if __name__ == "__main__":
    main()
