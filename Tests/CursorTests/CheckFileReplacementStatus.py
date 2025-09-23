import sys
import os
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager
from Services.LoggingService import LoggingService

def CheckFileReplacementStatus():
    try:
        db = DatabaseManager()
        
        print('=== CHECKING FILE REPLACEMENT STATUS ===')
        
        # Get transcoded files that passed VMAF but may have failed replacement
        # Join with VMAFQueue to get the actual transcoded file paths
        query = '''
        SELECT ta.Id, ta.FilePath, ta.VMAF, ta.AttemptDate, ta.Success,
               vq.TranscodedFilePath, vq.Status as VMAFStatus
        FROM TranscodeAttempts ta
        LEFT JOIN VMAFQueue vq ON ta.Id = vq.TranscodeAttemptId
        WHERE ta.VMAF IS NOT NULL 
        AND ta.VMAF >= 90
        AND ta.Success = 1
        AND vq.TranscodedFilePath IS NOT NULL
        ORDER BY ta.AttemptDate DESC
        LIMIT 10
        '''
        
        results = db.DatabaseService.ExecuteQuery(query)
        
        print(f'Found {len(results)} transcode attempts with VMAF >= 90:')
        
        failed_replacements = []
        for row in results:
            attempt_id = row['Id']
            original_path = row['FilePath']
            transcoded_path = row['TranscodedFilePath']
            vmaf_score = row['VMAF']
            attempt_date = row['AttemptDate']
            vmaf_status = row['VMAFStatus']
            
            print(f'\n--- Attempt {attempt_id} ---')
            print(f'Date: {attempt_date}')
            print(f'VMAF Score: {vmaf_score}')
            print(f'VMAF Status: {vmaf_status}')
            print(f'Original: {original_path}')
            print(f'Transcoded: {transcoded_path}')
            
            # Check if files exist
            original_exists = os.path.exists(original_path)
            transcoded_exists = os.path.exists(transcoded_path)
            
            print(f'Original exists: {original_exists}')
            print(f'Transcoded exists: {transcoded_exists}')
            
            if original_exists and transcoded_exists:
                failed_replacements.append({
                    'Id': attempt_id,
                    'OriginalPath': original_path,
                    'TranscodedPath': transcoded_path,
                    'VMAF': vmaf_score
                })
                print('❌ REPLACEMENT FAILED - Both files still exist')
            elif not original_exists and transcoded_exists:
                print('✅ REPLACEMENT SUCCESSFUL - Original deleted, transcoded exists')
            elif original_exists and not transcoded_exists:
                print('⚠️  TRANSCODE FAILED - Original exists, transcoded missing')
            else:
                print('❌ BOTH FILES MISSING - Something went wrong')
        
        print(f'\n=== SUMMARY ===')
        print(f'Total attempts with VMAF >= 90: {len(results)}')
        print(f'Failed replacements (both files exist): {len(failed_replacements)}')
        
        if failed_replacements:
            print('\n=== FAILED REPLACEMENTS ===')
            for replacement in failed_replacements:
                print(f'Attempt {replacement["Id"]}: VMAF {replacement["VMAF"]:.2f}')
                print(f'  Original: {replacement["OriginalPath"]}')
                print(f'  Transcoded: {replacement["TranscodedPath"]}')
        else:
            print('\n✅ No failed replacements found - all successful VMAF tests had their files properly replaced!')
        
        # Also check recent VMAF activity
        print('\n=== RECENT VMAF ACTIVITY ===')
        recent_vmaf_query = '''
        SELECT ta.Id, ta.FilePath, ta.VMAF, ta.AttemptDate
        FROM TranscodeAttempts ta
        WHERE ta.VMAF IS NOT NULL
        ORDER BY ta.AttemptDate DESC
        LIMIT 5
        '''
        
        recent_vmaf = db.DatabaseService.ExecuteQuery(recent_vmaf_query)
        for row in recent_vmaf:
            print(f'Attempt {row["Id"]}: VMAF {row["VMAF"]:.2f} on {row["AttemptDate"]}')

    except Exception as e:
        print(f'Error: {e}')
        LoggingService.LogException("Error checking file replacement status", e, 'CheckFileReplacementStatus', 'CheckFileReplacementStatus')

if __name__ == '__main__':
    CheckFileReplacementStatus()
