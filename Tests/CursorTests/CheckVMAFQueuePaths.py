import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckVMAFQueuePaths():
    try:
        db = DatabaseManager()
        
        print('=== VMAF QUEUE PATHS ===')
        
        # Check VMAFQueue table for file paths
        vmaf_query = '''
        SELECT Id, TranscodeAttemptId, OriginalFilePath, TranscodedFilePath, Status, VMAFScore
        FROM VMAFQueue
        ORDER BY Id DESC
        LIMIT 5
        '''
        
        vmaf_results = db.DatabaseService.ExecuteQuery(vmaf_query)
        
        if vmaf_results:
            for row in vmaf_results:
                print(f'\n--- VMAF Queue Item {row["Id"]} ---')
                print(f'TranscodeAttemptId: {row["TranscodeAttemptId"]}')
                print(f'Original: {row["OriginalFilePath"]}')
                print(f'Transcoded: {row["TranscodedFilePath"]}')
                print(f'Status: {row["Status"]}')
                print(f'VMAF Score: {row["VMAFScore"]}')
                
                # Check if files exist
                original_exists = os.path.exists(row["OriginalFilePath"]) if row["OriginalFilePath"] else False
                transcoded_exists = os.path.exists(row["TranscodedFilePath"]) if row["TranscodedFilePath"] else False
                print(f'Original exists: {original_exists}')
                print(f'Transcoded exists: {transcoded_exists}')
        else:
            print('No VMAF queue items found')
        
        print('\n=== CHECKING C:\\MediaVortex\\ DIRECTORY ===')
        mediavortex_dir = r'C:\MediaVortex'
        if os.path.exists(mediavortex_dir):
            files = os.listdir(mediavortex_dir)
            print(f'Files in {mediavortex_dir}:')
            for file in files[:10]:  # Show first 10 files
                print(f'  {file}')
        else:
            print(f'{mediavortex_dir} does not exist')

    except Exception as e:
        print(f'Error: {e}')

if __name__ == '__main__':
    CheckVMAFQueuePaths()

