#!/usr/bin/env python3
"""
Check All VMAF Logs
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckVMAFAllLogs():
    """Check all VMAF logs."""
    try:
        db = DatabaseManager()
        
        # Check for ANY VMAF logs
        print('=== ALL VMAF LOGS (Last 24 hours) ===')
        log_query = '''
        SELECT LogLevel, Message, Timestamp
        FROM Logs 
        WHERE Message LIKE '%VMAF%' 
        AND Timestamp >= datetime('now', '-24 hours')
        ORDER BY Timestamp DESC 
        LIMIT 20
        '''
        
        log_result = db.DatabaseService.ExecuteQuery(log_query)
        if log_result:
            for log in log_result:
                print(f'{log["Timestamp"]} [{log["LogLevel"]}] {log["Message"]}')
        else:
            print('No VMAF logs found in last 24 hours')
        
        # Check for any logs around the time the VMAF job started
        print('\n=== LOGS AROUND VMAF START TIME (12:09) ===')
        start_time_query = '''
        SELECT LogLevel, Message, Timestamp
        FROM Logs 
        WHERE Timestamp BETWEEN '2025-09-23 12:05:00' AND '2025-09-23 12:20:00'
        ORDER BY Timestamp DESC 
        LIMIT 10
        '''
        
        start_result = db.DatabaseService.ExecuteQuery(start_time_query)
        if start_result:
            for log in start_result:
                print(f'{log["Timestamp"]} [{log["LogLevel"]}] {log["Message"]}')
        else:
            print('No logs found around VMAF start time')
            
        # Check for any process-related logs
        print('\n=== PROCESS-RELATED LOGS (Last 2 hours) ===')
        process_query = '''
        SELECT LogLevel, Message, Timestamp
        FROM Logs 
        WHERE (Message LIKE '%process%' OR Message LIKE '%Process%' OR Message LIKE '%subprocess%')
        AND Timestamp >= datetime('now', '-2 hours')
        ORDER BY Timestamp DESC 
        LIMIT 10
        '''
        
        process_result = db.DatabaseService.ExecuteQuery(process_query)
        if process_result:
            for log in process_result:
                print(f'{log["Timestamp"]} [{log["LogLevel"]}] {log["Message"]}')
        else:
            print('No process-related logs found')
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    CheckVMAFAllLogs()
