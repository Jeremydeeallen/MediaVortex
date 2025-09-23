import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckTranscodeAttemptsSchema():
    try:
        db = DatabaseManager()
        
        print('=== TRANSCODE ATTEMPTS TABLE SCHEMA ===')
        
        # Get table schema
        schema_query = "PRAGMA table_info(TranscodeAttempts)"
        schema = db.DatabaseService.ExecuteQuery(schema_query)
        
        for column in schema:
            print(f'{column["name"]}: {column["type"]}')
        
        print('\n=== SAMPLE DATA ===')
        # Get a sample record
        sample_query = "SELECT * FROM TranscodeAttempts LIMIT 1"
        sample = db.DatabaseService.ExecuteQuery(sample_query)
        
        if sample:
            row = sample[0]
            print('Sample record columns:')
            for key in row.keys():
                print(f'  {key}: {row[key]}')
        else:
            print('No records found in TranscodeAttempts table')

    except Exception as e:
        print(f'Error: {e}')

if __name__ == '__main__':
    CheckTranscodeAttemptsSchema()

