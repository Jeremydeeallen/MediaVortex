import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from DatabaseHelper import DatabaseHelper

class LogAnalyzer:
    """Analyzer for MediaVortex logs to identify issues and patterns."""
    
    def __init__(self, DatabasePath: str = "Data/MediaVortex.db"):
        self.DatabaseHelper = DatabaseHelper(DatabasePath)
    
    def AnalyzeVMAFFailure(self, TimeWindowMinutes: int = 30) -> Dict[str, Any]:
        """Analyze VMAF failures within the specified time window."""
        cutoff_time = datetime.now() - timedelta(minutes=TimeWindowMinutes)
        
        with self.DatabaseHelper.GetConnection() as conn:
            cursor = conn.cursor()
            
            # Get VMAF-related logs within time window
            cursor.execute("""
                SELECT Id, Timestamp, LogLevel, Component, Message, SourceFunction
                FROM Logs 
                WHERE (Message LIKE '%VMAF%' OR Message LIKE '%vmaf%' OR Component LIKE '%VMAF%')
                AND Timestamp >= ?
                ORDER BY Id DESC
            """, (cutoff_time,))
            
            vmafLogs = [dict(row) for row in cursor.fetchall()]
            
            # Get error logs within time window
            cursor.execute("""
                SELECT Id, Timestamp, LogLevel, Component, Message, SourceFunction
                FROM Logs 
                WHERE LogLevel = 'ERROR' AND Timestamp >= ?
                ORDER BY Id DESC
            """, (cutoff_time,))
            
            errorLogs = [dict(row) for row in cursor.fetchall()]
            
            # Get VMAF queue items with errors
            cursor.execute("""
                SELECT Id, Status, VMAFScore, DateStarted, DateCompleted, ErrorMessage
                FROM VMAFQueue 
                WHERE ErrorMessage IS NOT NULL AND ErrorMessage != ''
                ORDER BY DateAdded DESC
                LIMIT 10
            """)
            
            failedVMAFItems = [dict(row) for row in cursor.fetchall()]
            
            return {
                "VMAFLogs": vmafLogs,
                "ErrorLogs": errorLogs,
                "FailedVMAFItems": failedVMAFItems,
                "AnalysisTime": datetime.now(),
                "TimeWindow": f"{TimeWindowMinutes} minutes"
            }
    
    def FindVMAFSuccessPattern(self) -> Dict[str, Any]:
        """Find patterns in successful VMAF processing."""
        with self.DatabaseHelper.GetConnection() as conn:
            cursor = conn.cursor()
            
            # Get successful VMAF items
            cursor.execute("""
                SELECT Id, TranscodeAttemptId, VMAFScore, DateStarted, DateCompleted
                FROM VMAFQueue 
                WHERE Status = 'Completed' AND VMAFScore IS NOT NULL
                ORDER BY DateCompleted DESC
                LIMIT 5
            """)
            
            successfulVMAF = [dict(row) for row in cursor.fetchall()]
            
            # Get corresponding TranscodeAttempts
            if successfulVMAF:
                attemptIds = [item['TranscodeAttemptId'] for item in successfulVMAF]
                placeholders = ','.join('?' * len(attemptIds))
                cursor.execute(f"""
                    SELECT Id, VMAF, Success, AttemptDate
                    FROM TranscodeAttempts 
                    WHERE Id IN ({placeholders})
                """, attemptIds)
                
                correspondingAttempts = [dict(row) for row in cursor.fetchall()]
            else:
                correspondingAttempts = []
            
            return {
                "SuccessfulVMAFItems": successfulVMAF,
                "CorrespondingAttempts": correspondingAttempts,
                "AnalysisTime": datetime.now()
            }
    
    def IdentifyVMAFBreakingPoint(self) -> Dict[str, Any]:
        """Identify where VMAF process is breaking on success."""
        analysis = self.AnalyzeVMAFFailure(60)  # Last hour
        
        # Look for specific error patterns
        errorPatterns = {
            "DatabaseMethodMissing": [],
            "FileOperationErrors": [],
            "VMAFScoreExtractionErrors": [],
            "GeneralErrors": []
        }
        
        for log in analysis["ErrorLogs"]:
            message = log["Message"]
            if "no attribute" in message.lower() and "gettranscodeattemptbyid" in message.lower():
                errorPatterns["DatabaseMethodMissing"].append(log)
            elif "file" in message.lower() and ("not found" in message.lower() or "missing" in message.lower()):
                errorPatterns["FileOperationErrors"].append(log)
            elif "vmaf" in message.lower() and ("score" in message.lower() or "extract" in message.lower()):
                errorPatterns["VMAFScoreExtractionErrors"].append(log)
            else:
                errorPatterns["GeneralErrors"].append(log)
        
        # Check for successful VMAF scores that weren't saved
        vmafQueueItems = self.DatabaseHelper.GetRecentVMAFQueueItems(10)
        transcodeAttempts = self.DatabaseHelper.GetRecentTranscodeAttempts(10)
        
        unsavedScores = []
        for vmafItem in vmafQueueItems:
            if vmafItem['VMAFScore'] and vmafItem['VMAFScore'] > 0:
                # Find corresponding TranscodeAttempt
                for attempt in transcodeAttempts:
                    if attempt['Id'] == vmafItem['TranscodeAttemptId']:
                        if not attempt['VMAF'] or attempt['VMAF'] != vmafItem['VMAFScore']:
                            unsavedScores.append({
                                "VMAFQueueItem": vmafItem,
                                "TranscodeAttempt": attempt,
                                "Issue": "VMAF score not saved to TranscodeAttempts"
                            })
                        break
        
        return {
            "ErrorPatterns": errorPatterns,
            "UnsavedVMAFScores": unsavedScores,
            "AnalysisTime": datetime.now()
        }
    
    def PrintVMAFAnalysis(self):
        """Print comprehensive VMAF analysis."""
        print("=== VMAF PROCESS ANALYSIS ===")
        print(f"Analysis Time: {datetime.now()}")
        print()
        
        # Get current status
        self.DatabaseHelper.PrintStatusSummary()
        
        # Analyze failures
        failureAnalysis = self.AnalyzeVMAFFailure(60)
        print("RECENT VMAF FAILURES:")
        for item in failureAnalysis["FailedVMAFItems"]:
            print(f"  VMAFQueue ID: {item['Id']}")
            print(f"    Status: {item['Status']}")
            print(f"    VMAFScore: {item['VMAFScore']}")
            print(f"    Error: {item['ErrorMessage']}")
            print()
        
        # Identify breaking point
        breakingPoint = self.IdentifyVMAFBreakingPoint()
        print("ERROR PATTERNS:")
        for pattern, errors in breakingPoint["ErrorPatterns"].items():
            if errors:
                print(f"  {pattern}: {len(errors)} errors")
                for error in errors[:3]:  # Show first 3
                    print(f"    {error['Timestamp']}: {error['Message'][:100]}...")
                print()
        
        print("UNSAVED VMAF SCORES:")
        for item in breakingPoint["UnsavedVMAFScores"]:
            print(f"  VMAFQueue ID: {item['VMAFQueueItem']['Id']}")
            print(f"    VMAFScore: {item['VMAFQueueItem']['VMAFScore']}")
            print(f"    TranscodeAttempt VMAF: {item['TranscodeAttempt']['VMAF']}")
            print(f"    Issue: {item['Issue']}")
            print()

if __name__ == "__main__":
    analyzer = LogAnalyzer()
    analyzer.PrintVMAFAnalysis()
