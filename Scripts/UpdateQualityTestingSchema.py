#!/usr/bin/env python3
"""
Update Quality Testing Database Schema
Adds ActiveJobs table and updates TranscodeAttempts for quality testing
"""

import sqlite3
import os
import sys
from datetime import datetime

class QualityTestingSchemaUpdater:
    def __init__(self, database_path="Data/MediaVortex.db"):
        self.DatabasePath = database_path
        self.Connection = None
        
    def GetConnection(self):
        """Get database connection"""
        if self.Connection is None:
            self.Connection = sqlite3.connect(self.DatabasePath)
            self.Connection.row_factory = sqlite3.Row
        return self.Connection
    
    def CloseConnection(self):
        """Close database connection"""
        if self.Connection:
            self.Connection.close()
            self.Connection = None
    
    def CreateActiveJobsTable(self):
        """Create ActiveJobs table for tracking all service job PIDs"""
        try:
            connection = self.GetConnection()
            cursor = connection.cursor()
            
            # Check if table already exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='ActiveJobs'
            """)
            
            if cursor.fetchone():
                print("[INFO] ActiveJobs table already exists")
                return True
            
            # Create ActiveJobs table
            cursor.execute("""
                CREATE TABLE ActiveJobs (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ServiceName TEXT NOT NULL,
                    JobType TEXT NOT NULL,
                    QueueId INTEGER NOT NULL,
                    ProcessId INTEGER NOT NULL,
                    ThreadId INTEGER,
                    StartedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    Status TEXT DEFAULT 'Running',
                    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UpdatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for ActiveJobs
            cursor.execute("""
                CREATE INDEX idx_ActiveJobs_ServiceName ON ActiveJobs(ServiceName)
            """)
            
            cursor.execute("""
                CREATE INDEX idx_ActiveJobs_Status ON ActiveJobs(Status)
            """)
            
            cursor.execute("""
                CREATE INDEX idx_ActiveJobs_ProcessId ON ActiveJobs(ProcessId)
            """)
            
            connection.commit()
            print("[SUCCESS] Created ActiveJobs table with indexes")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to create ActiveJobs table: {e}")
            return False
    
    def UpdateTranscodeAttemptsTable(self):
        """Add quality testing columns to TranscodeAttempts table"""
        try:
            connection = self.GetConnection()
            cursor = connection.cursor()
            
            # Check if columns already exist
            cursor.execute("PRAGMA table_info(TranscodeAttempts)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            columns_to_add = [
                ('QualityTestRequired', 'BOOLEAN DEFAULT 0'),
                ('QualityTestSkipped', 'BOOLEAN DEFAULT 0'),
                ('QualityTestCompleted', 'BOOLEAN DEFAULT 0')
            ]
            
            for column_name, column_type in columns_to_add:
                if column_name not in columns:
                    cursor.execute(f"""
                        ALTER TABLE TranscodeAttempts 
                        ADD COLUMN {column_name} {column_type}
                    """)
                    print(f"[SUCCESS] Added {column_name} column to TranscodeAttempts")
                else:
                    print(f"[INFO] {column_name} column already exists in TranscodeAttempts")
            
            connection.commit()
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to update TranscodeAttempts table: {e}")
            return False
    
    def VerifyQualityTestingTables(self):
        """Verify that required quality testing tables exist"""
        try:
            connection = self.GetConnection()
            cursor = connection.cursor()
            
            required_tables = [
                'QualityTestingQueue',
                'QualityTestProgress', 
                'ServiceStatus'
            ]
            
            missing_tables = []
            
            for table_name in required_tables:
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name=?
                """, (table_name,))
                
                if not cursor.fetchone():
                    missing_tables.append(table_name)
            
            if missing_tables:
                print(f"[WARNING] Missing tables: {', '.join(missing_tables)}")
                return False
            else:
                print("[SUCCESS] All required quality testing tables exist")
                return True
                
        except Exception as e:
            print(f"[ERROR] Failed to verify tables: {e}")
            return False
    
    def UpdateServiceStatusTable(self):
        """Ensure ServiceStatus table has required columns for quality testing"""
        try:
            connection = self.GetConnection()
            cursor = connection.cursor()
            
            # Check if MaxConcurrentJobs column exists
            cursor.execute("PRAGMA table_info(ServiceStatus)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            if 'MaxConcurrentJobs' not in columns:
                cursor.execute("""
                    ALTER TABLE ServiceStatus 
                    ADD COLUMN MaxConcurrentJobs INTEGER DEFAULT 1
                """)
                print("[SUCCESS] Added MaxConcurrentJobs column to ServiceStatus")
            else:
                print("[INFO] MaxConcurrentJobs column already exists in ServiceStatus")
            
            if 'ActiveJobsCount' not in columns:
                cursor.execute("""
                    ALTER TABLE ServiceStatus 
                    ADD COLUMN ActiveJobsCount INTEGER DEFAULT 0
                """)
                print("[SUCCESS] Added ActiveJobsCount column to ServiceStatus")
            else:
                print("[INFO] ActiveJobsCount column already exists in ServiceStatus")
            
            connection.commit()
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to update ServiceStatus table: {e}")
            return False
    
    def UpdateSchema(self):
        """Update the database schema for quality testing"""
        print("=== QUALITY TESTING SCHEMA UPDATE ===")
        print(f"Timestamp: {datetime.now()}")
        print(f"Database: {self.DatabasePath}")
        print()
        
        success = True
        
        # Step 1: Create ActiveJobs table
        print("1. Creating ActiveJobs table...")
        if not self.CreateActiveJobsTable():
            success = False
        
        # Step 2: Update TranscodeAttempts table
        print("\n2. Updating TranscodeAttempts table...")
        if not self.UpdateTranscodeAttemptsTable():
            success = False
        
        # Step 3: Verify existing tables
        print("\n3. Verifying existing quality testing tables...")
        if not self.VerifyQualityTestingTables():
            success = False
        
        # Step 4: Update ServiceStatus table
        print("\n4. Updating ServiceStatus table...")
        if not self.UpdateServiceStatusTable():
            success = False
        
        print("\n=== SCHEMA UPDATE COMPLETE ===")
        if success:
            print("[SUCCESS] All schema updates completed successfully")
        else:
            print("[WARNING] Some schema updates failed - check logs above")
        
        return success

def main():
    """Main function"""
    if len(sys.argv) > 1:
        database_path = sys.argv[1]
    else:
        database_path = "Data/MediaVortex.db"
    
    if not os.path.exists(database_path):
        print(f"[ERROR] Database file not found: {database_path}")
        sys.exit(1)
    
    updater = QualityTestingSchemaUpdater(database_path)
    
    try:
        success = updater.UpdateSchema()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"[ERROR] Schema update failed: {e}")
        sys.exit(1)
    finally:
        updater.CloseConnection()

if __name__ == "__main__":
    main()
