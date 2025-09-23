#!/usr/bin/env python3
"""
Check Actual FFmpeg Command from TranscodeAttempts
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckActualFFmpegCommand():
    """Check the actual FFmpeg command that was generated."""
    try:
        db = DatabaseManager()
        
        # Get the most recent transcode attempt for the SexArt file
        query = '''
        SELECT AttemptDate, FfpmpegCommand, Success, VideoBitrateKbps, AudioBitrateKbps, Quality
        FROM TranscodeAttempts 
        WHERE FilePath LIKE '%SexArt%'
        ORDER BY AttemptDate DESC 
        LIMIT 1
        '''
        
        result = db.DatabaseService.ExecuteQuery(query)
        
        if result:
            attempt = result[0]
            print('=== MOST RECENT TRANSCODE ATTEMPT ===')
            print(f'Date: {attempt["AttemptDate"]}')
            print(f'Success: {attempt["Success"]}')
            print(f'Video Bitrate: {attempt["VideoBitrateKbps"]} kbps')
            print(f'Audio Bitrate: {attempt["AudioBitrateKbps"]} kbps')
            print(f'Quality: {attempt["Quality"]}')
            print()
            print('=== ACTUAL FFMPEG COMMAND GENERATED ===')
            print(attempt['FfpmpegCommand'])
            print()
            
            # Check if scaling is present
            if 'scale=' in attempt['FfpmpegCommand']:
                print('✅ Command CONTAINS scaling filter')
            else:
                print('❌ Command MISSING scaling filter')
                
            # Check for other resolution-related parameters
            if '-s ' in attempt['FfpmpegCommand']:
                print('✅ Command contains -s parameter')
            else:
                print('❌ Command missing -s parameter')
                
            # Check for video filter
            if '-vf ' in attempt['FfpmpegCommand']:
                print('✅ Command contains -vf parameter')
            else:
                print('❌ Command missing -vf parameter')
                
        else:
            print('No transcode attempts found for SexArt file')
            
        # Also check a few more recent attempts to see if this is a pattern
        print('\n=== CHECKING RECENT TRANSCODE ATTEMPTS ===')
        recent_query = '''
        SELECT AttemptDate, FilePath, FfpmpegCommand
        FROM TranscodeAttempts 
        ORDER BY AttemptDate DESC 
        LIMIT 3
        '''
        
        recent_result = db.DatabaseService.ExecuteQuery(recent_query)
        
        for i, attempt in enumerate(recent_result, 1):
            print(f'\n--- Attempt {i} ---')
            print(f'Date: {attempt["AttemptDate"]}')
            print(f'File: {os.path.basename(attempt["FilePath"])}')
            
            if 'scale=' in attempt['FfpmpegCommand']:
                print('✅ Contains scaling')
            else:
                print('❌ Missing scaling')
                
            # Show just the key parts of the command
            cmd_parts = attempt['FfpmpegCommand'].split()
            key_parts = [part for part in cmd_parts if any(x in part for x in ['-c:v', '-crf', '-maxrate', '-vf', '-s', 'scale='])]
            print(f'Key parameters: {" ".join(key_parts)}')
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    CheckActualFFmpegCommand()
