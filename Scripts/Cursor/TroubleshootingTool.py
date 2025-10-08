#!/usr/bin/env python3
"""
Troubleshooting Tool for MediaVortex
Flexible script for database queries and log analysis
"""

import sqlite3
import sys
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

class TroubleshootingTool:
    """Flexible troubleshooting tool for MediaVortex."""
    
    def __init__(self, DatabasePath: str = "Data/MediaVortex.db"):
        self.DatabasePath = DatabasePath
    
    def GetConnection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.DatabasePath)
        conn.row_factory = sqlite3.Row
        return conn
    
    def ExecuteQuery(self, Query: str, Params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a SQL query and return results as list of dictionaries."""
        try:
            with self.GetConnection() as conn:
                cursor = conn.cursor()
                cursor.execute(Query, Params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"Error executing query: {e}")
            return []
    
    def GetRecentTranscodeAttempts(self, Limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent transcode attempts."""
        query = """
            SELECT Id, FilePath, AttemptDate, Success, VMAF, OldSizeBytes, NewSizeBytes, 
                   SizeReductionPercent, ErrorMessage, ProfileName
            FROM TranscodeAttempts 
            ORDER BY AttemptDate DESC 
            LIMIT ?
        """
        return self.ExecuteQuery(query, (Limit,))
    
    def GetTranscodeAttemptById(self, AttemptId: int) -> Optional[Dict[str, Any]]:
        """Get specific transcode attempt by ID."""
        query = """
            SELECT Id, FilePath, AttemptDate, Success, VMAF, OldSizeBytes, NewSizeBytes,
                   SizeReductionPercent, ErrorMessage, ProfileName, FfpmpegCommand
            FROM TranscodeAttempts 
            WHERE Id = ?
        """
        results = self.ExecuteQuery(query, (AttemptId,))
        return results[0] if results else None
    
    def GetQualityTestQueue(self, Limit: int = 10) -> List[Dict[str, Any]]:
        """Get quality test queue items."""
        query = """
            SELECT Id, OriginalFilePath, TranscodedFilePath, Status, VMAFScore, CreatedDate, TranscodeAttemptId
            FROM QualityTestingQueue 
            ORDER BY CreatedDate DESC 
            LIMIT ?
        """
        return self.ExecuteQuery(query, (Limit,))
    
    def GetTranscodeQueue(self, Limit: int = 10) -> List[Dict[str, Any]]:
        """Get transcode queue items."""
        query = """
            SELECT Id, FilePath, FileName, Status, Priority, DateAdded, DateStarted
            FROM TranscodeQueue 
            ORDER BY DateAdded DESC 
            LIMIT ?
        """
        return self.ExecuteQuery(query, (Limit,))
    
    def GetServiceStatus(self) -> List[Dict[str, Any]]:
        """Get service status information."""
        query = """
            SELECT ServiceName, Status, HealthStatus, StartTime, LastHealthCheck,
                   UptimeSeconds, MemoryUsage, CPUUsage, ActiveJobsCount, IsProcessing
            FROM ServiceStatus 
            ORDER BY LastHealthCheck DESC
        """
        return self.ExecuteQuery(query)
    
    def GetRecentLogs(self, Limit: int = 50, Component: str = None, LogLevel: str = None) -> List[Dict[str, Any]]:
        """Get recent logs with optional filters."""
        query = "SELECT Id, Timestamp, LogLevel, Component, Message, SourceFunction FROM Logs WHERE 1=1"
        params = []
        
        if Component:
            query += " AND Component = ?"
            params.append(Component)
        
        if LogLevel:
            query += " AND LogLevel = ?"
            params.append(LogLevel)
        
        query += " ORDER BY Id DESC LIMIT ?"
        params.append(Limit)
        
        return self.ExecuteQuery(query, tuple(params))
    
    def GetLogErrorsAndWarnings(self, Limit: int = 100) -> List[Dict[str, Any]]:
        """Get all errors and warnings from logs."""
        query = """
            SELECT Id, Timestamp, LogLevel, Component, Message, SourceFunction
            FROM Logs 
            WHERE LogLevel IN ('ERROR', 'WARNING', 'CRITICAL')
            ORDER BY Id DESC 
            LIMIT ?
        """
        return self.ExecuteQuery(query, (Limit,))
    
    def CreateQualityTestEntry(self, TranscodeAttemptId: int, OriginalFilePath: str, TranscodedFilePath: str) -> bool:
        """Create a quality test queue entry."""
        try:
            # Extract filename from path
            FileName = os.path.basename(OriginalFilePath)
            
            query = """
                INSERT INTO QualityTestingQueue (
                    TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, FileName, Status, 
                    DateAdded, CreatedDate
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            params = (TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, FileName, 'Pending', 
                     datetime.now(), datetime.now())
            
            with self.GetConnection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                print(f"Created quality test entry for TranscodeAttempt {TranscodeAttemptId}")
                return True
        except Exception as e:
            print(f"Error creating quality test entry: {e}")
            return False
    
    def GetTableInfo(self, TableName: str) -> List[Dict[str, Any]]:
        """Get table schema information."""
        query = f"PRAGMA table_info({TableName})"
        return self.ExecuteQuery(query)
    
    def ListTables(self) -> List[str]:
        """List all tables in the database."""
        query = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        results = self.ExecuteQuery(query)
        return [row['name'] for row in results]
    
    def PrintRecentTranscodeAttempts(self, Limit: int = 5):
        """Print recent transcode attempts."""
        print(f"\n=== RECENT TRANSCODE ATTEMPTS (Last {Limit}) ===")
        attempts = self.GetRecentTranscodeAttempts(Limit)
        for attempt in attempts:
            print(f"ID: {attempt['Id']}")
            print(f"  File: {attempt['FilePath'][-60:]}")
            print(f"  Success: {attempt['Success']}")
            print(f"  Date: {attempt['AttemptDate']}")
            print(f"  VMAF: {attempt['VMAF']}")
            print(f"  Size Reduction: {attempt['SizeReductionPercent']}%")
            if attempt['ErrorMessage']:
                print(f"  Error: {attempt['ErrorMessage']}")
            print()
    
    def PrintQualityTestQueue(self, Limit: int = 5):
        """Print quality test queue."""
        print(f"\n=== QUALITY TEST QUEUE (Last {Limit}) ===")
        items = self.GetQualityTestQueue(Limit)
        for item in items:
            print(f"ID: {item['Id']}")
            print(f"  Original: {item['OriginalFilePath'][-50:]}")
            print(f"  Transcoded: {item['TranscodedFilePath'][-50:]}")
            print(f"  Status: {item['Status']}")
            print(f"  VMAF Score: {item['VMAFScore']}")
            print(f"  Created: {item['CreatedDate']}")
            print(f"  TranscodeAttemptId: {item['TranscodeAttemptId']}")
            print()
    
    def PrintLogErrorsAndWarnings(self, Limit: int = 20):
        """Print recent errors and warnings."""
        print(f"\n=== RECENT ERRORS AND WARNINGS (Last {Limit}) ===")
        logs = self.GetLogErrorsAndWarnings(Limit)
        for log in logs:
            print(f"[{log['Timestamp']}] {log['LogLevel']} - {log['Component']}.{log['SourceFunction']}")
            print(f"  {log['Message']}")
            print()
    
    def PrintServiceStatus(self):
        """Print service status."""
        print("\n=== SERVICE STATUS ===")
        services = self.GetServiceStatus()
        for service in services:
            print(f"Service: {service['ServiceName']}")
            print(f"  Status: {service['Status']}")
            print(f"  Health: {service['HealthStatus']}")
            print(f"  Active Jobs: {service['ActiveJobsCount']}")
            print(f"  Is Processing: {service['IsProcessing']}")
            print(f"  Last Check: {service['LastHealthCheck']}")
            print()

def main():
    """Main function with command line interface."""
    tool = TroubleshootingTool()
    
    if len(sys.argv) < 2:
        print("Usage: python TroubleshootingTool.py <command> [args...]")
        print("\nCommands:")
        print("  recent-transcodes [limit]     - Show recent transcode attempts")
        print("  transcode <id>                - Show specific transcode attempt")
        print("  quality-queue [limit]         - Show quality test queue")
        print("  transcode-queue [limit]       - Show transcode queue")
        print("  service-status                - Show service status")
        print("  logs [limit] [component]      - Show recent logs")
        print("  errors [limit]                - Show errors and warnings")
        print("  create-quality-test <id>      - Create quality test for transcode attempt")
        print("  tables                        - List all tables")
        print("  table-info <table>            - Show table schema")
        print("  query <sql>                   - Execute custom SQL query")
        return
    
    command = sys.argv[1].lower()
    
    try:
        if command == "recent-transcodes":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            tool.PrintRecentTranscodeAttempts(limit)
        
        elif command == "transcode":
            if len(sys.argv) < 3:
                print("Usage: python TroubleshootingTool.py transcode <id>")
                return
            attempt_id = int(sys.argv[2])
            attempt = tool.GetTranscodeAttemptById(attempt_id)
            if attempt:
                print(f"\n=== TRANSCODE ATTEMPT {attempt_id} ===")
                for key, value in attempt.items():
                    print(f"{key}: {value}")
            else:
                print(f"Transcode attempt {attempt_id} not found")
        
        elif command == "quality-queue":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            tool.PrintQualityTestQueue(limit)
        
        elif command == "transcode-queue":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            items = tool.GetTranscodeQueue(limit)
            print(f"\n=== TRANSCODE QUEUE (Last {limit}) ===")
            for item in items:
                print(f"ID: {item['Id']}, Status: {item['Status']}, File: {item['FilePath'][-50:]}")
        
        elif command == "service-status":
            tool.PrintServiceStatus()
        
        elif command == "logs":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
            component = sys.argv[3] if len(sys.argv) > 3 else None
            logs = tool.GetRecentLogs(limit, component)
            print(f"\n=== RECENT LOGS (Last {limit}) ===")
            for log in logs:
                print(f"[{log['Timestamp']}] {log['LogLevel']} - {log['Component']}.{log['SourceFunction']}")
                print(f"  {log['Message']}")
                print()
        
        elif command == "errors":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
            tool.PrintLogErrorsAndWarnings(limit)
        
        elif command == "create-quality-test":
            if len(sys.argv) < 3:
                print("Usage: python TroubleshootingTool.py create-quality-test <transcode_attempt_id>")
                return
            attempt_id = int(sys.argv[2])
            attempt = tool.GetTranscodeAttemptById(attempt_id)
            if attempt:
                # Create quality test entry
                success = tool.CreateQualityTestEntry(
                    attempt_id, 
                    attempt['FilePath'], 
                    attempt['FilePath']  # Using same path for now
                )
                if success:
                    print("Quality test entry created successfully!")
                else:
                    print("Failed to create quality test entry")
            else:
                print(f"Transcode attempt {attempt_id} not found")
        
        elif command == "tables":
            tables = tool.ListTables()
            print("\n=== DATABASE TABLES ===")
            for table in tables:
                print(f"  {table}")
        
        elif command == "table-info":
            if len(sys.argv) < 3:
                print("Usage: python TroubleshootingTool.py table-info <table_name>")
                return
            table_name = sys.argv[2]
            info = tool.GetTableInfo(table_name)
            print(f"\n=== TABLE SCHEMA: {table_name} ===")
            for column in info:
                print(f"  {column['name']} ({column['type']}) - {'NOT NULL' if column['notnull'] else 'NULL'}")
        
        elif command == "query":
            if len(sys.argv) < 3:
                print("Usage: python TroubleshootingTool.py query \"<sql_query>\"")
                return
            sql = sys.argv[2]
            results = tool.ExecuteQuery(sql)
            print(f"\n=== QUERY RESULTS ===")
            for row in results:
                print(row)
        
        else:
            print(f"Unknown command: {command}")
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
