"""
Database Migration Script: Add MaxConcurrentJobs column to ServiceStatus table
This script adds the missing MaxConcurrentJobs column to the ServiceStatus table.
"""

import sqlite3
import os
import sys
from datetime import datetime

# Add the project root to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.DatabaseService import DatabaseService
from Services.LoggingService import LoggingService

def AddMaxConcurrentJobsColumn():
    """Add MaxConcurrentJobs column to ServiceStatus table if it doesn't exist."""
    try:
        LoggingService.LogInfo("Starting database migration: Add MaxConcurrentJobs column", "Migration", "AddMaxConcurrentJobsColumn")
        
        # Initialize database service
        db_service = DatabaseService()
        
        # Check if column already exists
        check_query = """
        PRAGMA table_info(ServiceStatus)
        """
        columns = db_service.ExecuteQuery(check_query)
        
        column_exists = any(col['name'] == 'MaxConcurrentJobs' for col in columns)
        
        if column_exists:
            LoggingService.LogInfo("MaxConcurrentJobs column already exists in ServiceStatus table", "Migration", "AddMaxConcurrentJobsColumn")
            return True
        
        # Add the column
        alter_query = """
        ALTER TABLE ServiceStatus ADD COLUMN MaxConcurrentJobs INTEGER DEFAULT 1
        """
        
        db_service.ExecuteNonQuery(alter_query)
        LoggingService.LogInfo("Successfully added MaxConcurrentJobs column to ServiceStatus table", "Migration", "AddMaxConcurrentJobsColumn")
        
        # Update existing records with default value
        update_query = """
        UPDATE ServiceStatus SET MaxConcurrentJobs = 1 WHERE MaxConcurrentJobs IS NULL
        """
        
        db_service.ExecuteNonQuery(update_query)
        LoggingService.LogInfo("Updated existing ServiceStatus records with default MaxConcurrentJobs value", "Migration", "AddMaxConcurrentJobsColumn")
        
        return True
        
    except Exception as e:
        LoggingService.LogException("Error adding MaxConcurrentJobs column", e, "Migration", "AddMaxConcurrentJobsColumn")
        return False

def VerifyColumnExists():
    """Verify that the MaxConcurrentJobs column exists and is accessible."""
    try:
        db_service = DatabaseService()
        
        # Test query to verify column exists and is accessible
        test_query = """
        SELECT ServiceName, MaxConcurrentJobs FROM ServiceStatus LIMIT 1
        """
        
        result = db_service.ExecuteQuery(test_query)
        LoggingService.LogInfo(f"MaxConcurrentJobs column verification successful. Sample data: {result}", "Migration", "VerifyColumnExists")
        return True
        
    except Exception as e:
        LoggingService.LogException("Error verifying MaxConcurrentJobs column", e, "Migration", "VerifyColumnExists")
        return False

if __name__ == "__main__":
    print("MediaVortex Database Migration: Add MaxConcurrentJobs Column")
    print("=" * 60)
    
    # Run the migration
    success = AddMaxConcurrentJobsColumn()
    
    if success:
        print("✓ Migration completed successfully")
        
        # Verify the column works
        if VerifyColumnExists():
            print("✓ Column verification successful")
            print("\nThe MaxConcurrentJobs column has been added to the ServiceStatus table.")
            print("You can now edit MaxConcurrentJobs values in the interface.")
        else:
            print("✗ Column verification failed")
    else:
        print("✗ Migration failed")
        sys.exit(1)
