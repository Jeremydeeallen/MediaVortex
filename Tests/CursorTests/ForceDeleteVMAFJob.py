#!/usr/bin/env python3
"""
Force Delete Stuck VMAF Job
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def ForceDeleteVMAFJob():
    """Force delete the stuck VMAF job using direct database connection."""
    try:
        db = DatabaseManager()
        
        print('=== FORCE DELETE VMAF JOB 8 ===')
        
        # Check current status
        print('Current VMAF jobs:')
        query = '''
        SELECT Id, Status, DateStarted, DateCompleted, ErrorMessage
        FROM VMAFQueue 
        ORDER BY Id DESC
        LIMIT 5
        '''
        
        result = db.DatabaseService.ExecuteQuery(query)
        if result:
            for job in result:
                print(f'Job {job["Id"]}: Status={job["Status"]}, Started={job["DateStarted"]}, Completed={job["DateCompleted"]}')
        else:
            print('No VMAF jobs found')
        
        # Force delete using direct database connection
        print('\nForce deleting VMAF Job ID 8...')
        try:
            # Delete from VMAFQueue
            db.DatabaseService.DatabaseConnection.execute('DELETE FROM VMAFQueue WHERE Id = 8')
            print('✅ Deleted from VMAFQueue')
            
            # Delete from VMAFProgress
            db.DatabaseService.DatabaseConnection.execute('DELETE FROM VMAFProgress WHERE VMAFQueueId = 8')
            print('✅ Deleted from VMAFProgress')
            
            # Commit the transaction
            db.DatabaseService.DatabaseConnection.commit()
            print('✅ Transaction committed')
            
        except Exception as e:
            print(f'Error during deletion: {e}')
            db.DatabaseService.DatabaseConnection.rollback()
            print('❌ Transaction rolled back')
        
        # Check final status
        print('\n=== FINAL STATUS ===')
        result = db.DatabaseService.ExecuteQuery(query)
        if result:
            for job in result:
                print(f'Job {job["Id"]}: Status={job["Status"]}, Started={job["DateStarted"]}, Completed={job["DateCompleted"]}')
        else:
            print('No VMAF jobs found')
        
        print('\n✅ VMAF job deletion complete! You can now start a fresh VMAF job from the Quality Queue.')
        
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    ForceDeleteVMAFJob()
