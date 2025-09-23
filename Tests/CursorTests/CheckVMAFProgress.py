#!/usr/bin/env python3
"""
Check VMAF Progress Status
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckVMAFProgress():
    """Check VMAF progress and status."""
    try:
        db = DatabaseManager()
        
        print('=== VMAF PROGRESS CHECK ===')
        
        # Check VMAF queue status
        vmaf_query = '''
        SELECT JobId, Status, Progress, StartTime, EndTime, ErrorMessage
        FROM VMAFQueue 
        ORDER BY StartTime DESC 
        LIMIT 5
        '''
        
        vmaf_result = db.DatabaseService.ExecuteQuery(vmaf_query)
        
        if vmaf_result:
            for i, job in enumerate(vmaf_result, 1):
                print(f'\n--- VMAF Job {i} ---')
                print(f'JobId: {job["JobId"]}')
                print(f'Status: {job["Status"]}')
                print(f'Progress: {job["Progress"]}%')
                print(f'StartTime: {job["StartTime"]}')
                print(f'EndTime: {job["EndTime"]}')
                if job['ErrorMessage']:
                    print(f'Error: {job["ErrorMessage"]}')
        else:
            print('No VMAF jobs found')
        
        # Check for any running VMAF processes
        print('\n=== CHECKING FOR RUNNING VMAF PROCESSES ===')
        running_query = '''
        SELECT COUNT(*) as count
        FROM VMAFQueue 
        WHERE Status IN ('Pending', 'Running')
        '''
        
        running_result = db.DatabaseService.ExecuteQuery(running_query)
        if running_result:
            count = running_result[0]['count']
            print(f'Running/Pending VMAF jobs: {count}')
            
            if count > 0:
                # Show details of running jobs
                running_details_query = '''
                SELECT JobId, Status, Progress, StartTime, ErrorMessage
                FROM VMAFQueue 
                WHERE Status IN ('Pending', 'Running')
                ORDER BY StartTime DESC
                '''
                
                running_details = db.DatabaseService.ExecuteQuery(running_details_query)
                for job in running_details:
                    print(f'\nRunning Job {job["JobId"]}:')
                    print(f'  Status: {job["Status"]}')
                    print(f'  Progress: {job["Progress"]}%')
                    print(f'  StartTime: {job["StartTime"]}')
                    if job['ErrorMessage']:
                        print(f'  Error: {job["ErrorMessage"]}')
        
        # Check recent VMAF logs for any errors
        print('\n=== CHECKING RECENT VMAF LOGS ===')
        log_query = '''
        SELECT LogLevel, Message, LogTime
        FROM Logs 
        WHERE Message LIKE '%VMAF%' 
        ORDER BY LogTime DESC 
        LIMIT 5
        '''
        
        log_result = db.DatabaseService.ExecuteQuery(log_query)
        if log_result:
            for log in log_result:
                print(f'{log["LogTime"]} [{log["LogLevel"]}] {log["Message"]}')
        else:
            print('No recent VMAF logs found')
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    CheckVMAFProgress()
