#!/usr/bin/env python3
"""
Register QualityTestingService in ServiceStatus table
"""

import sqlite3
import os
from datetime import datetime

def RegisterQualityTestingService():
    """Register QualityTestingService in the ServiceStatus table."""
    try:
        # Connect to database
        db_path = os.path.join('Data', 'MediaVortex.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("Registering QualityTestingService in ServiceStatus table...")
        
        # Check if service already exists
        cursor.execute("SELECT Id FROM ServiceStatus WHERE ServiceName = 'QualityTestingService'")
        existing = cursor.fetchone()
        
        if existing:
            print("QualityTestingService already exists in ServiceStatus table")
            return True
        
        # Insert new service status
        insert_query = """
        INSERT INTO ServiceStatus (
            ServiceName, Status, HealthStatus, IsProcessing, ActiveJobsCount, 
            MaxConcurrentJobs, LastHealthCheck, StartTime, 
            ErrorCount, LastErrorMessage, DatabaseConnection, 
            DiskSpace, CreatedAt, UpdatedAt
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        now = datetime.now()
        cursor.execute(insert_query, (
            'QualityTestingService',  # ServiceName
            'Stopped',               # Status
            'Unknown',               # HealthStatus
            False,                   # IsProcessing
            0,                       # ActiveJobsCount
            1,                       # MaxConcurrentJobs
            now,                     # LastHealthCheck
            None,                    # StartTime
            0,                       # ErrorCount
            None,                    # LastErrorMessage
            True,                    # DatabaseConnection
            None,                    # DiskSpace
            now,                     # CreatedAt
            now                      # UpdatedAt
        ))
        
        conn.commit()
        print("✅ QualityTestingService registered successfully")
        
        # Verify registration
        cursor.execute("SELECT ServiceName, Status, MaxConcurrentJobs FROM ServiceStatus WHERE ServiceName = 'QualityTestingService'")
        result = cursor.fetchone()
        if result:
            print(f"✅ Verified: {result[0]} - Status: {result[1]}, MaxConcurrentJobs: {result[2]}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error registering QualityTestingService: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Registering QualityTestingService...")
    success = RegisterQualityTestingService()
    
    if success:
        print("\n✅ QualityTestingService registration completed successfully!")
    else:
        print("\n❌ QualityTestingService registration failed!")
