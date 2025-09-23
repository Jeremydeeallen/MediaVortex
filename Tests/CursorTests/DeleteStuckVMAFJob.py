#!/usr/bin/env python3
"""
Delete Stuck VMAF Job Completely
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def DeleteStuckVMAFJob():
    """Delete the stuck VMAF job completely so it can be restarted fresh."""
    try:
        db = DatabaseManager()
        
        print('=== DELETING STUCK VMAF JOB ===')
        
        # Check current status
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
        else:
            print('  Job not found')
        
        # Delete the stuck job completely
        print('\nDeleting stuck VMAF job...')
        delete_query = '''
        DELETE FROM VMAFQueue 
        WHERE Id = 8
        '''
        
        db.DatabaseService.ExecuteQuery(delete_query)
        print('✅ VMAF Job ID 8 deleted completely')
        
        # Also delete any progress records
        progress_delete_query = '''
        DELETE FROM VMAFProgress 
        WHERE VMAFQueueId = 8
        '''
        
        db.DatabaseService.ExecuteQuery(progress_delete_query)
        print('✅ VMAF Progress records deleted')
        
        # Verify deletion
        print('\nVerifying deletion:')
        result = db.DatabaseService.ExecuteQuery(query)
        if result:
            print('❌ Job still exists')
        else:
            print('✅ Job successfully deleted')
        
        print('\n✅ VMAF job completely removed! You can now start a fresh VMAF job from the Quality Queue.')
        
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    DeleteStuckVMAFJob()
