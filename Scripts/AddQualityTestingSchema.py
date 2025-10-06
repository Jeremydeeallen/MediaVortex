#!/usr/bin/env python3
"""
AddQualityTestingSchema.py

This script adds the missing database schema for Quality Testing:
- ActiveJobs table
- QualityTestRequired, QualityTestSkipped, QualityTestCompleted columns to TranscodeAttempts
"""

import sqlite3
import os
from datetime import datetime

def GetDatabasePath():
    """Get the path to the MediaVortex database."""
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(script_dir, "Data", "MediaVortex.db")

def AddActiveJobsTable(cursor):
    """Add ActiveJobs table for tracking all service job PIDs."""
    try:
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS ActiveJobs (
            Id INTEGER PRIMARY KEY AUTOINCREMENT,
            ServiceName TEXT NOT NULL,
            JobType TEXT NOT NULL,
            QueueId INTEGER,
            ProcessId INTEGER,
            ThreadId INTEGER,
            StartedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            Status TEXT DEFAULT 'Running',
            CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UpdatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        cursor.execute(create_table_sql)
        print("✅ ActiveJobs table created/verified")
        return True
        
    except Exception as e:
        print(f"❌ Error creating ActiveJobs table: {e}")
        return False

def AddTranscodeAttemptsColumns(cursor):
    """Add missing columns to TranscodeAttempts table."""
    try:
        # Check if columns exist first
        cursor.execute("PRAGMA table_info(TranscodeAttempts)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add QualityTestRequired column
        if 'QualityTestRequired' not in columns:
            cursor.execute("ALTER TABLE TranscodeAttempts ADD COLUMN QualityTestRequired BOOLEAN DEFAULT 0")
            print("✅ Added QualityTestRequired column to TranscodeAttempts")
        else:
            print("✅ QualityTestRequired column already exists")
        
        # Add QualityTestSkipped column
        if 'QualityTestSkipped' not in columns:
            cursor.execute("ALTER TABLE TranscodeAttempts ADD COLUMN QualityTestSkipped BOOLEAN DEFAULT 0")
            print("✅ Added QualityTestSkipped column to TranscodeAttempts")
        else:
            print("✅ QualityTestSkipped column already exists")
        
        # Add QualityTestCompleted column
        if 'QualityTestCompleted' not in columns:
            cursor.execute("ALTER TABLE TranscodeAttempts ADD COLUMN QualityTestCompleted BOOLEAN DEFAULT 0")
            print("✅ Added QualityTestCompleted column to TranscodeAttempts")
        else:
            print("✅ QualityTestCompleted column already exists")
        
        return True
        
    except Exception as e:
        print(f"❌ Error adding TranscodeAttempts columns: {e}")
        return False

def AddIndexes(cursor):
    """Add indexes for better performance."""
    try:
        # Add index for ActiveJobs
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ActiveJobs_ServiceName ON ActiveJobs(ServiceName)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ActiveJobs_Status ON ActiveJobs(Status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ActiveJobs_QueueId ON ActiveJobs(QueueId)")
        
        # Add index for TranscodeAttempts quality test columns
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_TranscodeAttempts_QualityTestRequired ON TranscodeAttempts(QualityTestRequired)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_TranscodeAttempts_QualityTestCompleted ON TranscodeAttempts(QualityTestCompleted)")
        
        print("✅ Indexes added successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error adding indexes: {e}")
        return False

def UpdateQualityTestingSchema():
    """Update the database schema for Quality Testing."""
    try:
        db_path = GetDatabasePath()
        
        if not os.path.exists(db_path):
            print(f"❌ Database not found at: {db_path}")
            return False
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("Adding Quality Testing database schema...")
        
        # Add ActiveJobs table
        if not AddActiveJobsTable(cursor):
            return False
        
        # Add missing columns to TranscodeAttempts
        if not AddTranscodeAttemptsColumns(cursor):
            return False
        
        # Add indexes
        if not AddIndexes(cursor):
            return False
        
        # Commit changes
        conn.commit()
        conn.close()
        
        print("✅ Quality Testing database schema updated successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error updating Quality Testing schema: {e}")
        return False

if __name__ == "__main__":
    print("Adding Quality Testing database schema...")
    success = UpdateQualityTestingSchema()
    if success:
        print("✅ Quality Testing schema added successfully")
    else:
        print("❌ Failed to add Quality Testing schema")
