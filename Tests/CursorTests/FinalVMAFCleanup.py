#!/usr/bin/env python3
"""
Final VMAF Job Cleanup
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def FinalVMAFCleanup():
    """Final cleanup of the stuck VMAF job."""
    try:
        db = DatabaseManager()
        
        print('=== FINAL VMAF JOB CLEANUP ===')
        
        # Delete VMAF Job ID 8
        print('Deleting VMAF Job ID 8...')
        delete_query = 'DELETE FROM VMAFQueue WHERE Id = 8'
        db.DatabaseService.ExecuteQuery(delete_query)
        print('✅ VMAF Job deleted')
        
        # Delete progress records
        progress_delete_query = 'DELETE FROM VMAFProgress WHERE VMAFQueueId = 8'
        db.DatabaseService.ExecuteQuery(progress_delete_query)
        print('✅ VMAF Progress records deleted')
        
        # Check final status
        print('\nFinal VMAF jobs:')
        check_query = '''
        SELECT Id, Status, DateStarted, DateCompleted
        FROM VMAFQueue 
        ORDER BY Id DESC
        LIMIT 5
        '''
        
        result = db.DatabaseService.ExecuteQuery(check_query)
        if result:
            for job in result:
                job_id = job['Id']
                status = job['Status']
                print(f'Job {job_id}: Status={status}')
        else:
            print('No VMAF jobs found')
        
        print('\n✅ VMAF cleanup complete! You can now start a fresh VMAF job from the Quality Queue.')
        
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    FinalVMAFCleanup()
