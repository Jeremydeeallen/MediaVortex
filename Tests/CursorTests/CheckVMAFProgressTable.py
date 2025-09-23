#!/usr/bin/env python3
"""
Check VMAF Progress Table
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckVMAFProgressTable():
    """Check VMAF Progress table for Job ID 8."""
    try:
        db = DatabaseManager()
        
        print('=== VMAF PROGRESS TABLE CHECK ===')
        query = '''
        SELECT Id, VMAFQueueId, Status, ProgressPercentage, CurrentStep, StartTime, EndTime
        FROM VMAFProgress 
        WHERE VMAFQueueId = 8
        ORDER BY Id DESC
        '''
        
        result = db.DatabaseService.ExecuteQuery(query)
        if result:
            for row in result:
                progress_id = row['Id']
                status = row['Status']
                progress = row['ProgressPercentage']
                step = row['CurrentStep']
                start_time = row['StartTime']
                end_time = row['EndTime']
                
                print(f'Progress ID {progress_id}: Status={status}, Progress={progress}%, Step={step}')
                print(f'  StartTime: {start_time}')
                print(f'  EndTime: {end_time}')
        else:
            print('No VMAFProgress records found for Job ID 8')
        
        print('\n=== ALL VMAF PROGRESS RECORDS ===')
        all_query = '''
        SELECT Id, VMAFQueueId, Status, ProgressPercentage, CurrentStep
        FROM VMAFProgress 
        ORDER BY Id DESC
        LIMIT 5
        '''
        
        all_result = db.DatabaseService.ExecuteQuery(all_query)
        if all_result:
            for row in all_result:
                progress_id = row['Id']
                queue_id = row['VMAFQueueId']
                status = row['Status']
                progress = row['ProgressPercentage']
                
                print(f'Progress ID {progress_id}: QueueId={queue_id}, Status={status}, Progress={progress}%')
        else:
            print('No VMAFProgress records found')
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    CheckVMAFProgressTable()
