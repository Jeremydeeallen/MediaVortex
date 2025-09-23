#!/usr/bin/env python3
"""
Manual File Replacement After VMAF Test
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager
from Services.TranscodingBusinessService import TranscodingBusinessService
from Models.TranscodeAttemptModel import TranscodeAttemptModel

def ManualFileReplacement():
    """Manually trigger file replacement for the SexArt file."""
    try:
        db = DatabaseManager()
        transcoding_service = TranscodingBusinessService()
        
        print('=== MANUAL FILE REPLACEMENT ===')
        
        # Get the most recent transcode attempt for SexArt
        query = '''
        SELECT Id, FilePath, VMAF, Success, AttemptDate
        FROM TranscodeAttempts 
        WHERE FilePath LIKE '%SexArt%'
        ORDER BY AttemptDate DESC 
        LIMIT 1
        '''
        
        result = db.DatabaseService.ExecuteQuery(query)
        if not result:
            print('❌ No transcode attempt found for SexArt file')
            return
        
        attempt_data = result[0]
        attempt_id = attempt_data['Id']
        original_file = attempt_data['FilePath']
        vmaf_score = attempt_data['VMAF']
        
        print(f'Found transcode attempt ID: {attempt_id}')
        print(f'Original file: {original_file}')
        print(f'VMAF score: {vmaf_score}')
        
        # Construct the transcoded file path
        transcoded_file = original_file.replace('Z:\\videos\\Couple\\', 'c:\\MediaVortex\\')
        transcoded_file = transcoded_file.replace('.mp4', '.mkv')
        
        print(f'Transcoded file: {transcoded_file}')
        
        # Check if files exist
        if not os.path.exists(original_file):
            print(f'❌ Original file not found: {original_file}')
            return
            
        if not os.path.exists(transcoded_file):
            print(f'❌ Transcoded file not found: {transcoded_file}')
            return
        
        print('✅ Both files exist')
        
        # Get the transcode attempt model
        transcode_attempt = db.GetTranscodeAttemptById(attempt_id)
        if not transcode_attempt:
            print(f'❌ Could not load transcode attempt model for ID: {attempt_id}')
            return
        
        print('✅ Transcode attempt model loaded')
        
        # Trigger file replacement
        print('\n=== STARTING FILE REPLACEMENT ===')
        result = transcoding_service.ProcessFileReplacement(
            original_file,
            transcoded_file,
            transcode_attempt,
            vmaf_score
        )
        
        print(f'File replacement result: {result}')
        
        if result.get('Success', False):
            print('✅ File replacement completed successfully!')
        else:
            print(f'❌ File replacement failed: {result.get("ErrorMessage", "Unknown error")}')
        
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    ManualFileReplacement()
