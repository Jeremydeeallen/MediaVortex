#!/usr/bin/env python3
"""
Check Transcode Attempts from Yesterday to See if Scaling Was Working
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckYesterdayTranscodes():
    """Check transcode attempts from yesterday to see if scaling was working."""
    try:
        db = DatabaseManager()
        
        # Get transcode attempts from the last 2 days
        query = '''
        SELECT AttemptDate, FilePath, FfpmpegCommand, Success
        FROM TranscodeAttempts 
        WHERE AttemptDate >= date('now', '-2 days')
        ORDER BY AttemptDate DESC 
        LIMIT 10
        '''
        
        result = db.DatabaseService.ExecuteQuery(query)
        
        print('=== TRANSCODE ATTEMPTS FROM LAST 2 DAYS ===')
        for i, attempt in enumerate(result, 1):
            print(f'\n--- Attempt {i} ---')
            print(f'Date: {attempt["AttemptDate"]}')
            print(f'File: {os.path.basename(attempt["FilePath"])}')
            print(f'Success: {attempt["Success"]}')
            
            # Check for scaling in the command
            cmd = attempt['FfpmpegCommand']
            if 'scale=' in cmd:
                print('✅ CONTAINS scaling filter')
                # Extract the scale part
                parts = cmd.split()
                for part in parts:
                    if 'scale=' in part:
                        print(f'   Scale: {part}')
            else:
                print('❌ MISSING scaling filter')
            
            # Show key video parameters
            key_parts = [part for part in cmd.split() if any(x in part for x in ['-c:v', '-crf', '-maxrate', '-vf', '-s', 'scale='])]
            print(f'Key video params: {" ".join(key_parts)}')
            
        # Also check if there are any attempts with scaling at all
        print('\n=== CHECKING FOR ANY ATTEMPTS WITH SCALING ===')
        scaling_query = '''
        SELECT COUNT(*) as count
        FROM TranscodeAttempts 
        WHERE FfpmpegCommand LIKE '%scale=%'
        '''
        
        scaling_result = db.DatabaseService.ExecuteQuery(scaling_query)
        if scaling_result:
            count = scaling_result[0]['count']
            print(f'Total attempts with scaling: {count}')
            
            if count > 0:
                # Show the most recent one with scaling
                recent_scaling_query = '''
                SELECT AttemptDate, FilePath, FfpmpegCommand
                FROM TranscodeAttempts 
                WHERE FfpmpegCommand LIKE '%scale=%'
                ORDER BY AttemptDate DESC 
                LIMIT 1
                '''
                
                recent_scaling_result = db.DatabaseService.ExecuteQuery(recent_scaling_query)
                if recent_scaling_result:
                    recent = recent_scaling_result[0]
                    print(f'\nMost recent attempt WITH scaling:')
                    print(f'Date: {recent["AttemptDate"]}')
                    print(f'File: {os.path.basename(recent["FilePath"])}')
                    print(f'Command: {recent["FfpmpegCommand"]}')
            else:
                print('❌ NO attempts found with scaling filters')
                
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    CheckYesterdayTranscodes()
