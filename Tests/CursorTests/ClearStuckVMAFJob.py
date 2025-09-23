#!/usr/bin/env python3
"""
Clear Stuck VMAF Job
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def ClearStuckVMAFJob():
    """Clear the stuck VMAF job so it can be restarted."""
    try:
        db = DatabaseManager()
        
        print('=== CLEARING STUCK VMAF JOB ===')
        
        # First, let's see the current stuck job
        print('Current VMAF Job ID 8 status:')
        query = '''
        SELECT Id, Status, DateStarted, DateCompleted, ErrorMessage, RetryCount
        FROM VMAFQueue 
        WHERE Id = 8
        '''
        
        result = db.DatabaseService.ExecuteQuery(query)
        if result:
            job = result[0]
            print(f'  Status: {job["Status"]}')
            print(f'  DateStarted: {job["DateStarted"]}')
            print(f'  DateCompleted: {job["DateCompleted"]}')
            print(f'  ErrorMessage: {job["ErrorMessage"]}')
            print(f'  RetryCount: {job["RetryCount"]}')
        
        # Clear the stuck job by setting it to Failed
        print('\nClearing stuck VMAF job...')
        clear_query = '''
        UPDATE VMAFQueue 
        SET Status = 'Failed', 
            DateCompleted = datetime('now'),
            ErrorMessage = 'Cleared stuck job - will retry'
        WHERE Id = 8
        '''
        
        db.DatabaseService.ExecuteQuery(clear_query)
        print('✅ VMAF Job ID 8 cleared and marked as Failed')
        
        # Also clear any stuck progress records
        progress_clear_query = '''
        UPDATE VMAFProgress 
        SET Status = 'Failed',
            EndTime = datetime('now'),
            ErrorMessage = 'Cleared stuck progress - will retry'
        WHERE VMAFQueueId = 8 AND Status = 'Running'
        '''
        
        db.DatabaseService.ExecuteQuery(progress_clear_query)
        print('✅ VMAF Progress records cleared')
        
        # Show the updated status
        print('\nUpdated VMAF Job ID 8 status:')
        result = db.DatabaseService.ExecuteQuery(query)
        if result:
            job = result[0]
            print(f'  Status: {job["Status"]}')
            print(f'  DateStarted: {job["DateStarted"]}')
            print(f'  DateCompleted: {job["DateCompleted"]}')
            print(f'  ErrorMessage: {job["ErrorMessage"]}')
            print(f'  RetryCount: {job["RetryCount"]}')
        
        print('\n✅ VMAF job cleared! You can now start it again from the Quality Queue.')
        
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    ClearStuckVMAFJob()
