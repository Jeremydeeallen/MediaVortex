#!/usr/bin/env python3
"""
Check VMAF Logs for Hung Process
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckVMAFLogs():
    """Check VMAF logs for hung process."""
    try:
        db = DatabaseManager()
        
        # Check recent logs for VMAF activity
        print('=== RECENT VMAF LOGS (Last 2 hours) ===')
        log_query = '''
        SELECT LogLevel, Message, Timestamp
        FROM Logs 
        WHERE Message LIKE '%VMAF%' 
        AND Timestamp >= datetime('now', '-2 hours')
        ORDER BY Timestamp DESC 
        LIMIT 15
        '''
        
        log_result = db.DatabaseService.ExecuteQuery(log_query)
        if log_result:
            for log in log_result:
                print(f'{log["Timestamp"]} [{log["LogLevel"]}] {log["Message"]}')
        else:
            print('No recent VMAF logs found')
        
        # Check for any error logs
        print('\n=== RECENT ERROR LOGS ===')
        error_query = '''
        SELECT LogLevel, Message, Timestamp
        FROM Logs 
        WHERE LogLevel = 'ERROR'
        AND Timestamp >= datetime('now', '-2 hours')
        ORDER BY Timestamp DESC 
        LIMIT 10
        '''
        
        error_result = db.DatabaseService.ExecuteQuery(error_query)
        if error_result:
            for log in error_result:
                print(f'{log["Timestamp"]} [{log["LogLevel"]}] {log["Message"]}')
        else:
            print('No recent error logs found')
            
        # Check for any FFmpeg-related logs that might indicate VMAF issues
        print('\n=== RECENT FFMPEG LOGS (Last 2 hours) ===')
        ffmpeg_query = '''
        SELECT LogLevel, Message, Timestamp
        FROM Logs 
        WHERE Message LIKE '%ffmpeg%' OR Message LIKE '%FFmpeg%'
        AND Timestamp >= datetime('now', '-2 hours')
        ORDER BY Timestamp DESC 
        LIMIT 10
        '''
        
        ffmpeg_result = db.DatabaseService.ExecuteQuery(ffmpeg_query)
        if ffmpeg_result:
            for log in ffmpeg_result:
                print(f'{log["Timestamp"]} [{log["LogLevel"]}] {log["Message"]}')
        else:
            print('No recent FFmpeg logs found')
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    CheckVMAFLogs()
