#!/usr/bin/env python3
"""
Check Current Quality Testing Status
"""

import sqlite3
import os

def CheckCurrentStatus():
    """Check current quality testing status and logs."""
    try:
        # Connect to database
        db_path = os.path.join('Data', 'MediaVortex.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print('=== CURRENT QUALITY TESTING STATUS ===')
        
        # Check service status
        cursor.execute("SELECT ServiceName, Status FROM ServiceStatus WHERE ServiceName = 'QualityTestingService'")
        service_status = cursor.fetchone()
        print(f'QualityTestingService status: {service_status[1] if service_status else "Not found"}')
        
        # Check if there are any pending quality testing jobs
        cursor.execute("SELECT COUNT(*) FROM QualityTestingQueue WHERE Status = 'Pending'")
        pending_count = cursor.fetchone()
        print(f'Pending quality testing jobs: {pending_count[0] if pending_count else 0}')
        
        # Check if there are any completed transcodes needing quality tests
        cursor.execute("SELECT COUNT(*) FROM TranscodeAttempts WHERE Success = 1 AND QualityTestRequired = 1 AND QualityTestCompleted = 0")
        transcodes_count = cursor.fetchone()
        print(f'Completed transcodes needing quality tests: {transcodes_count[0] if transcodes_count else 0}')
        
        # Check recent logs
        cursor.execute("SELECT Timestamp, LogLevel, Message, Component, Operation, FunctionName FROM Logs WHERE date(Timestamp) = date('now') ORDER BY Timestamp DESC LIMIT 10")
        logs = cursor.fetchall()
        
        print('\n=== RECENT LOGS TODAY ===')
        if logs:
            for log in logs:
                timestamp, level, message, component, operation, function = log
                print(f'[{timestamp}] {level} - {component}.{function}')
                print(f'  Message: {message}')
                print()
        else:
            print('No logs found today')
        
        # Check for any errors today
        cursor.execute("SELECT Timestamp, LogLevel, Message, Component, Operation, FunctionName FROM Logs WHERE date(Timestamp) = date('now') AND (LogLevel = 'Error' OR LogLevel = 'Exception' OR LogLevel = 'Critical') ORDER BY Timestamp DESC LIMIT 10")
        error_logs = cursor.fetchall()
        
        print('\n=== ERRORS TODAY ===')
        if error_logs:
            for log in error_logs:
                timestamp, level, message, component, operation, function = log
                print(f'[{timestamp}] {level} - {component}.{function}')
                print(f'  Message: {message}')
                print()
        else:
            print('No errors found today')
        
        conn.close()
        
    except Exception as e:
        print(f'Error checking status: {e}')

if __name__ == "__main__":
    CheckCurrentStatus()
