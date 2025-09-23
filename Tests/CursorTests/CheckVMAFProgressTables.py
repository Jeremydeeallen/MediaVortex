#!/usr/bin/env python3
"""
Check VMAF Progress Tables and Database Sync Issue
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Repositories.DatabaseManager import DatabaseManager

def CheckVMAFProgressTables():
    """Check VMAF progress tables and database sync issue."""
    try:
        db = DatabaseManager()
        
        # Check if there's a VMAFProgress table
        print('=== CHECKING FOR VMAF PROGRESS TABLE ===')
        try:
            progress_query = 'SELECT * FROM VMAFProgress ORDER BY Id DESC LIMIT 3'
            progress_result = db.DatabaseService.ExecuteQuery(progress_query)
            
            if progress_result:
                print('VMAFProgress table found:')
                for i, row in enumerate(progress_result, 1):
                    print(f'\n--- Progress Row {i} ---')
                    for key in row.keys():
                        print(f'{key}: {row[key]}')
            else:
                print('No VMAFProgress data found')
        except Exception as e:
            print(f'VMAFProgress table error: {e}')
        
        # Check all tables to see what VMAF-related tables exist
        print('\n=== CHECKING ALL VMAF TABLES ===')
        tables_query = "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%VMAF%'"
        tables_result = db.DatabaseService.ExecuteQuery(tables_query)
        
        for table in tables_result:
            print(f'VMAF table: {table["name"]}')
            
        # Check VMAFQueue again with more details
        print('\n=== DETAILED VMAF QUEUE CHECK ===')
        queue_query = '''
        SELECT Id, Status, DateStarted, DateCompleted, ErrorMessage, RetryCount
        FROM VMAFQueue 
        WHERE Id = 8
        '''
        
        queue_result = db.DatabaseService.ExecuteQuery(queue_query)
        if queue_result:
            row = queue_result[0]
            print(f'Job ID 8 Details:')
            print(f'  Status: {row["Status"]}')
            print(f'  DateStarted: {row["DateStarted"]}')
            print(f'  DateCompleted: {row["DateCompleted"]}')
            print(f'  ErrorMessage: {row["ErrorMessage"]}')
            print(f'  RetryCount: {row["RetryCount"]}')
        
        # Check recent logs for VMAF activity
        print('\n=== RECENT VMAF LOGS ===')
        log_query = '''
        SELECT LogLevel, Message, LogTime
        FROM Logs 
        WHERE Message LIKE '%VMAF%' 
        ORDER BY LogTime DESC 
        LIMIT 10
        '''
        
        log_result = db.DatabaseService.ExecuteQuery(log_query)
        if log_result:
            for log in log_result:
                print(f'{log["LogTime"]} [{log["LogLevel"]}] {log["Message"]}')
        else:
            print('No recent VMAF logs found')
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    CheckVMAFProgressTables()
