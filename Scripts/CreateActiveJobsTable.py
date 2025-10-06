#!/usr/bin/env python3
"""
Create ActiveJobs Table Script
Creates the ActiveJobs table for unified job tracking across all services.
"""

import sqlite3
import os
from datetime import datetime

def CreateActiveJobsTable():
    """Create the ActiveJobs table for tracking all service job PIDs."""
    try:
        # Get database path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(script_dir, "..", "Data", "MediaVortex.db")
        
        print(f"Creating ActiveJobs table in: {db_path}")
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create ActiveJobs table
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS ActiveJobs (
            Id INTEGER PRIMARY KEY AUTOINCREMENT,
            ServiceName TEXT NOT NULL,
            JobType TEXT NOT NULL,
            QueueId INTEGER NOT NULL,
            ProcessId INTEGER,
            ThreadId TEXT,
            StartedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            Status TEXT DEFAULT 'Running',
            CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UpdatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (QueueId) REFERENCES QualityTestingQueue(Id)
        );
        """
        
        cursor.execute(create_table_sql)
        
        # Create indexes for performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_ActiveJobs_ServiceName ON ActiveJobs(ServiceName);",
            "CREATE INDEX IF NOT EXISTS idx_ActiveJobs_Status ON ActiveJobs(Status);",
            "CREATE INDEX IF NOT EXISTS idx_ActiveJobs_QueueId ON ActiveJobs(QueueId);",
            "CREATE INDEX IF NOT EXISTS idx_ActiveJobs_StartedAt ON ActiveJobs(StartedAt);"
        ]
        
        for index_sql in indexes:
            cursor.execute(index_sql)
        
        # Commit changes
        conn.commit()
        print("✅ ActiveJobs table created successfully")
        
        # Verify table creation
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ActiveJobs';")
        result = cursor.fetchone()
        
        if result:
            print("✅ ActiveJobs table verified")
            
            # Show table structure
            cursor.execute("PRAGMA table_info(ActiveJobs);")
            columns = cursor.fetchall()
            print("\n📋 ActiveJobs table structure:")
            for col in columns:
                print(f"  - {col[1]} ({col[2]})")
        else:
            print("❌ ActiveJobs table creation failed")
            return False
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error creating ActiveJobs table: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Creating ActiveJobs table...")
    success = CreateActiveJobsTable()
    
    if success:
        print("\n✅ ActiveJobs table creation completed successfully!")
    else:
        print("\n❌ ActiveJobs table creation failed!")
