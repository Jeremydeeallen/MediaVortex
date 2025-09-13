#!/usr/bin/env python3
"""
Development script to add the ScanJobs table for subprocess state tracking.
This script creates the table and indexes needed for scan job management.
"""

import os
import sys
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent.parent))

from Services.DatabaseService import DatabaseService


class ScanJobsTableCreator:
    """Creates the ScanJobs table for subprocess state tracking."""
    
    def __init__(self):
        self.DatabaseService = DatabaseService()
    
    def CreateScanJobsTable(self):
        """Create the ScanJobs table and indexes."""
        try:
            print("Creating ScanJobs table...")
            
            # Create the ScanJobs table
            CreateTableQuery = """
            CREATE TABLE ScanJobs (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                JobId TEXT UNIQUE NOT NULL,
                RootFolderPath TEXT NOT NULL,
                Recursive BOOLEAN NOT NULL DEFAULT 1,
                Status TEXT NOT NULL DEFAULT 'Pending',
                ProcessId INTEGER,
                StartTime TIMESTAMP,
                EndTime TIMESTAMP,
                Progress REAL DEFAULT 0.0,
                CurrentDirectory TEXT,
                TotalFiles INTEGER DEFAULT 0,
                ProcessedFiles INTEGER DEFAULT 0,
                SkippedFiles INTEGER DEFAULT 0,
                EncodingErrors INTEGER DEFAULT 0,
                NewFiles INTEGER DEFAULT 0,
                UpdatedFiles INTEGER DEFAULT 0,
                DeletedFiles INTEGER DEFAULT 0,
                ErrorMessage TEXT,
                LastUpdated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
            
            self.DatabaseService.ExecuteNonQuery(CreateTableQuery)
            print("✓ ScanJobs table created successfully")
            
            # Create indexes
            Indexes = [
                ("idx_ScanJobs_Status", "CREATE INDEX idx_ScanJobs_Status ON ScanJobs(Status);"),
                ("idx_ScanJobs_JobId", "CREATE INDEX idx_ScanJobs_JobId ON ScanJobs(JobId);"),
                ("idx_ScanJobs_ProcessId", "CREATE INDEX idx_ScanJobs_ProcessId ON ScanJobs(ProcessId);")
            ]
            
            for IndexName, IndexQuery in Indexes:
                try:
                    self.DatabaseService.ExecuteNonQuery(IndexQuery)
                    print(f"✓ Index {IndexName} created successfully")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        print(f"⚠ Index {IndexName} already exists")
                    else:
                        print(f"✗ Error creating index {IndexName}: {str(e)}")
            
            print("ScanJobs table setup completed successfully!")
            
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ ScanJobs table already exists")
            else:
                print(f"✗ Error creating ScanJobs table: {str(e)}")
                raise
    
    def VerifyTableExists(self) -> bool:
        """Verify that the ScanJobs table exists and has the correct structure."""
        try:
            Query = "SELECT name FROM sqlite_master WHERE type='table' AND name='ScanJobs';"
            Result = self.DatabaseService.ExecuteQuery(Query)
            
            if Result:
                print("✓ ScanJobs table exists")
                
                # Check if it has the expected columns
                ColumnsQuery = "PRAGMA table_info(ScanJobs);"
                Columns = self.DatabaseService.ExecuteQuery(ColumnsQuery)
                
                ExpectedColumns = [
                    'Id', 'JobId', 'RootFolderPath', 'Recursive', 'Status', 
                    'ProcessId', 'StartTime', 'EndTime', 'Progress', 'CurrentDirectory',
                    'TotalFiles', 'ProcessedFiles', 'SkippedFiles', 'EncodingErrors',
                    'NewFiles', 'UpdatedFiles', 'DeletedFiles', 'ErrorMessage', 'LastUpdated'
                ]
                
                ActualColumns = [col['name'] for col in Columns]
                
                if set(ExpectedColumns).issubset(set(ActualColumns)):
                    print("✓ ScanJobs table has correct structure")
                    return True
                else:
                    print("✗ ScanJobs table structure is incorrect")
                    return False
            else:
                print("✗ ScanJobs table does not exist")
                return False
                
        except Exception as e:
            print(f"✗ Error verifying ScanJobs table: {str(e)}")
            return False


def main():
    """Main function to create the ScanJobs table."""
    try:
        Creator = ScanJobsTableCreator()
        
        # Check if table already exists
        if Creator.VerifyTableExists():
            print("ScanJobs table already exists and is properly configured.")
        else:
            Creator.CreateScanJobsTable()
            Creator.VerifyTableExists()
        
        print("ScanJobs table setup completed!")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
