#!/usr/bin/env python3
"""
Check transcoding failure in database logs and recent attempts.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService
from datetime import datetime, timedelta

def CheckTranscodeFailure():
    """Check recent transcoding failures and logs."""
    try:
        print("=== TRANSCODE FAILURE INVESTIGATION ===")
        print()
        
        db = DatabaseManager()
        
        # 1. Check recent transcode attempts (last 24 hours)
        print("1. RECENT TRANSCODE ATTEMPTS (Last 24 hours):")
        print("-" * 50)
        
        query = """
            SELECT Id, FilePath, AttemptDate, Success, ErrorMessage, 
                   Quality, OldSizeBytes, NewSizeBytes, TranscodeDurationSeconds,
                   FfpmpegCommand, AudioBitrateKbps, VideoBitrateKbps, ProfileName
            FROM TranscodeAttempts 
            WHERE AttemptDate >= datetime('now', '-1 day')
            ORDER BY AttemptDate DESC
            LIMIT 10
        """
        
        attempts = db.DatabaseService.ExecuteQuery(query)
        
        if attempts:
            for attempt in attempts:
                print(f"ID: {attempt['Id']}")
                print(f"File: {os.path.basename(attempt['FilePath'])}")
                print(f"Date: {attempt['AttemptDate']}")
                print(f"Success: {attempt['Success']}")
                print(f"Error: {attempt['ErrorMessage']}")
                print(f"Quality: {attempt['Quality']}")
                print(f"Profile: {attempt['ProfileName']}")
                print(f"Command: {attempt['FfpmpegCommand']}")
                print("-" * 30)
        else:
            print("No recent attempts found.")
        
        print()
        
        # 2. Check current queue status
        print("2. CURRENT TRANSCODE QUEUE:")
        print("-" * 50)
        
        queue_query = """
            SELECT Id, FilePath, FileName, Status, Priority, DateAdded, DateStarted
            FROM TranscodeQueue 
            ORDER BY DateAdded DESC
            LIMIT 5
        """
        
        queue_items = db.DatabaseService.ExecuteQuery(queue_query)
        
        if queue_items:
            for item in queue_items:
                print(f"ID: {item['Id']}")
                print(f"File: {item['FileName']}")
                print(f"Status: {item['Status']}")
                print(f"Priority: {item['Priority']}")
                print(f"Added: {item['DateAdded']}")
                print(f"Started: {item['DateStarted']}")
                print("-" * 30)
        else:
            print("No queue items found.")
        
        print()
        
        # 3. Check recent logs for transcoding errors
        print("3. RECENT TRANSCODING LOGS (Last 2 hours):")
        print("-" * 50)
        
        logs_query = """
            SELECT Timestamp, LogLevel, FunctionName, Message, ExceptionMessage
            FROM Logs 
            WHERE (FunctionName LIKE '%Transcode%' OR FunctionName LIKE '%Command%' OR 
                   Message LIKE '%transcode%' OR Message LIKE '%command%' OR
                   ExceptionMessage LIKE '%transcode%' OR ExceptionMessage LIKE '%command%')
            AND Timestamp >= datetime('now', '-2 hours')
            ORDER BY Timestamp DESC
            LIMIT 20
        """
        
        logs = db.DatabaseService.ExecuteQuery(logs_query)
        
        if logs:
            for log in logs:
                print(f"Time: {log['Timestamp']}")
                print(f"Level: {log['LogLevel']}")
                print(f"Function: {log['FunctionName']}")
                print(f"Message: {log['Message']}")
                if log['ExceptionMessage']:
                    print(f"Exception: {log['ExceptionMessage']}")
                print("-" * 30)
        else:
            print("No recent transcoding logs found.")
        
        print()
        
        # 4. Check for specific error patterns
        print("4. ERROR PATTERN ANALYSIS:")
        print("-" * 50)
        
        error_query = """
            SELECT COUNT(*) as ErrorCount, ErrorMessage
            FROM TranscodeAttempts 
            WHERE Success = 0 AND AttemptDate >= datetime('now', '-1 day')
            GROUP BY ErrorMessage
            ORDER BY ErrorCount DESC
        """
        
        errors = db.DatabaseService.ExecuteQuery(error_query)
        
        if errors:
            for error in errors:
                print(f"Count: {error['ErrorCount']} - {error['ErrorMessage']}")
        else:
            print("No recent errors found.")
        
        print()
        
        # 5. Check profile settings for recent failures
        print("5. PROFILE SETTINGS FOR RECENT FAILURES:")
        print("-" * 50)
        
        profile_query = """
            SELECT DISTINCT ta.ProfileName, ta.Quality, ta.AudioBitrateKbps, ta.VideoBitrateKbps
            FROM TranscodeAttempts ta
            WHERE ta.Success = 0 AND ta.AttemptDate >= datetime('now', '-1 day')
        """
        
        profiles = db.DatabaseService.ExecuteQuery(profile_query)
        
        if profiles:
            for profile in profiles:
                print(f"Profile: {profile['ProfileName']}")
                print(f"Quality: {profile['Quality']}")
                print(f"Audio Bitrate: {profile['AudioBitrateKbps']}")
                print(f"Video Bitrate: {profile['VideoBitrateKbps']}")
                print("-" * 30)
        else:
            print("No profile data for recent failures.")
        
        print()
        print("=== INVESTIGATION COMPLETE ===")
        
    except Exception as e:
        print(f"Error during investigation: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    CheckTranscodeFailure()
