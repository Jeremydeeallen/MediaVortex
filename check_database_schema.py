#!/usr/bin/env python3
"""
Check Database Schema for Quality Testing Implementation
"""

import sqlite3
import os

def CheckDatabaseSchema():
    """Check if the database schema is properly set up for quality testing."""
    try:
        # Connect to database
        db_path = os.path.join('Data', 'MediaVortex.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print('=== DATABASE SCHEMA CHECK ===')
        
        # Check if ActiveJobs table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ActiveJobs';")
        active_jobs_exists = cursor.fetchone()
        print(f'ActiveJobs table exists: {active_jobs_exists is not None}')
        
        # Check TranscodeAttempts columns
        cursor.execute('PRAGMA table_info(TranscodeAttempts);')
        columns = cursor.fetchall()
        transcode_columns = [col[1] for col in columns]
        
        print(f'TranscodeAttempts has QualityTestRequired: {"QualityTestRequired" in transcode_columns}')
        print(f'TranscodeAttempts has QualityTestCompleted: {"QualityTestCompleted" in transcode_columns}')
        
        # Check if there are any completed transcodes needing quality tests
        cursor.execute('''
        SELECT COUNT(*) as count
        FROM TranscodeAttempts 
        WHERE Success = 1 
        AND QualityTestRequired = 1 
        AND QualityTestCompleted = 0
        ''')
        result = cursor.fetchone()
        print(f'Completed transcodes needing quality tests: {result[0] if result else 0}')
        
        # Check QualityTestingQueue
        cursor.execute('SELECT COUNT(*) as count FROM QualityTestingQueue WHERE Status = "Pending"')
        result = cursor.fetchone()
        print(f'Pending quality testing jobs: {result[0] if result else 0}')
        
        # Check ActiveJobs
        if active_jobs_exists:
            cursor.execute('SELECT COUNT(*) as count FROM ActiveJobs WHERE Status = "Running"')
            result = cursor.fetchone()
            print(f'Active jobs running: {result[0] if result else 0}')
        else:
            print('Active jobs running: N/A (table does not exist)')
        
        # Check service status
        cursor.execute('SELECT Status FROM ServiceStatus WHERE ServiceName = "QualityTestingService"')
        service_status = cursor.fetchone()
        print(f'QualityTestingService status: {service_status[0] if service_status else "Not found"}')
        
        conn.close()
        
    except Exception as e:
        print(f'Error checking database schema: {e}')

if __name__ == "__main__":
    CheckDatabaseSchema()
