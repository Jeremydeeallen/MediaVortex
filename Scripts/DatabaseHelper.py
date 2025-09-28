import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

class DatabaseHelper:
    """Helper class for database analysis and debugging."""
    
    def __init__(self, DatabasePath: str = "Data/MediaVortex.db"):
        self.DatabasePath = DatabasePath
    
    def GetConnection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.DatabasePath)
        conn.row_factory = sqlite3.Row
        return conn
    
    def GetTranscodeQueueStatus(self) -> Dict[str, int]:
        """Get current TranscodeQueue status counts."""
        with self.GetConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT Status, COUNT(*) as Count FROM TranscodeQueue GROUP BY Status")
            return {row['Status']: row['Count'] for row in cursor.fetchall()}
    
    def GetVMAFQueueStatus(self) -> Dict[str, int]:
        """Get current VMAFQueue status counts."""
        with self.GetConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT Status, COUNT(*) as Count FROM VMAFQueue GROUP BY Status")
            return {row['Status']: row['Count'] for row in cursor.fetchall()}
    
    def GetVMAFProgressStatus(self) -> Dict[str, int]:
        """Get current QualityTestProgress status counts."""
        with self.GetConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT Status, COUNT(*) as Count FROM QualityTestProgress GROUP BY Status")
            return {row['Status']: row['Count'] for row in cursor.fetchall()}
    
    def GetRecentTranscodeAttempts(self, Limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent TranscodeAttempts with VMAF scores."""
        with self.GetConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT Id, FilePath, AttemptDate, Success, VMAF, OldSizeBytes, NewSizeBytes
                FROM TranscodeAttempts 
                ORDER BY AttemptDate DESC 
                LIMIT ?
            """, (Limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def GetRecentVMAFQueueItems(self, Limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent VMAFQueue items."""
        with self.GetConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT Id, TranscodeAttemptId, Status, VMAFScore, DateStarted, DateCompleted, ErrorMessage
                FROM VMAFQueue 
                ORDER BY DateAdded DESC 
                LIMIT ?
            """, (Limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def GetRecentVMAFProgressItems(self, Limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent QualityTestProgress items."""
        with self.GetConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT Id, VMAFQueueId, Status, ProgressPercentage, CurrentStep, StartTime, EndTime, ETA
                FROM QualityTestProgress 
                ORDER BY CreatedAt DESC 
                LIMIT ?
            """, (Limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def GetRecentLogs(self, Limit: int = 20, SourceFilter: str = None) -> List[Dict[str, Any]]:
        """Get recent logs with optional source filter."""
        with self.GetConnection() as conn:
            cursor = conn.cursor()
            if SourceFilter:
                cursor.execute("""
                SELECT Id, Timestamp, LogLevel, Component, Message, SourceFunction
                FROM Logs 
                WHERE Component = ?
                ORDER BY Id DESC 
                LIMIT ?
            """, (SourceFilter, Limit))
            else:
                cursor.execute("""
                    SELECT Id, Timestamp, LogLevel, Component, Message, SourceFunction
                    FROM Logs 
                    ORDER BY Id DESC 
                    LIMIT ?
                """, (Limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def GetVMAFRelatedLogs(self, Limit: int = 50) -> List[Dict[str, Any]]:
        """Get logs related to VMAF processing."""
        with self.GetConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT Id, Timestamp, LogLevel, Component, Message, SourceFunction
                FROM Logs 
                WHERE Message LIKE '%VMAF%' OR Message LIKE '%vmaf%' OR Component LIKE '%VMAF%'
                ORDER BY Id DESC 
                LIMIT ?
            """, (Limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def GetTranscodeRelatedLogs(self, Limit: int = 50) -> List[Dict[str, Any]]:
        """Get logs related to transcoding."""
        with self.GetConnection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT Id, Timestamp, LogLevel, Component, Message, SourceFunction
                FROM Logs 
                WHERE Message LIKE '%transcode%' OR Message LIKE '%Transcode%' OR Component LIKE '%Transcode%'
                ORDER BY Id DESC 
                LIMIT ?
            """, (Limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def PrintStatusSummary(self):
        """Print a comprehensive status summary."""
        print("=== DATABASE STATUS SUMMARY ===")
        print(f"Timestamp: {datetime.now()}")
        print()
        
        print("TRANSCODE QUEUE:")
        transcodeStatus = self.GetTranscodeQueueStatus()
        for status, count in transcodeStatus.items():
            print(f"  {status}: {count} items")
        if not transcodeStatus:
            print("  No items")
        print()
        
        print("VMAF QUEUE:")
        vmafStatus = self.GetVMAFQueueStatus()
        for status, count in vmafStatus.items():
            print(f"  {status}: {count} items")
        if not vmafStatus:
            print("  No items")
        print()
        
        print("VMAF PROGRESS:")
        progressStatus = self.GetVMAFProgressStatus()
        for status, count in progressStatus.items():
            print(f"  {status}: {count} items")
        if not progressStatus:
            print("  No items")
        print()
        
        print("RECENT TRANSCODE ATTEMPTS:")
        attempts = self.GetRecentTranscodeAttempts(3)
        for attempt in attempts:
            print(f"  ID: {attempt['Id']}, Success: {attempt['Success']}, VMAF: {attempt['VMAF']}, File: {attempt['FilePath'][-50:]}")
        print()
        
        print("RECENT VMAF QUEUE ITEMS:")
        vmafItems = self.GetRecentVMAFQueueItems(3)
        for item in vmafItems:
            print(f"  ID: {item['Id']}, Status: {item['Status']}, VMAFScore: {item['VMAFScore']}, Error: {item['ErrorMessage']}")
        print()

if __name__ == "__main__":
    helper = DatabaseHelper()
    helper.PrintStatusSummary()
