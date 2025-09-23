#!/usr/bin/env python3
"""
Delete VMAF Progress Record
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def DeleteVMAFProgress():
    """Delete the VMAF Progress record for Job ID 8."""
    try:
        db = DatabaseManager()
        
        print('=== DELETE VMAF PROGRESS RECORD ===')
        
        # Delete the VMAFProgress record entirely
        delete_query = '''
        DELETE FROM VMAFProgress 
        WHERE Id = 8
        '''
        
        result = db.DatabaseService.ExecuteQuery(delete_query)
        print('✅ VMAF Progress record deleted')
        
        # Check if it's gone
        print('\n=== CHECKING DELETION ===')
        check_query = '''
        SELECT Id, VMAFQueueId, Status, ProgressPercentage
        FROM VMAFProgress 
        WHERE Id = 8
        '''
        
        result = db.DatabaseService.ExecuteQuery(check_query)
        if result:
            print('❌ Record still exists')
            for row in result:
                progress_id = row['Id']
                status = row['Status']
                print(f'Progress ID {progress_id}: Status={status}')
        else:
            print('✅ Record successfully deleted')
        
        print('\n✅ VMAF Progress record deletion complete!')
        
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    DeleteVMAFProgress()
