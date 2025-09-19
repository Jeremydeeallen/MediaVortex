#!/usr/bin/env python3
"""
Script to add Quality column to ProfileThresholds table if it doesn't exist.
"""

import sqlite3
import os
import sys

# Add the parent directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.LoggingService import LoggingService

def AddQualityColumn():
    """Add Quality column to ProfileThresholds table if it doesn't exist."""
    try:
        # Connect to the database
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Data', 'MediaVortex.db')
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        
        # Check if Quality column exists
        cursor.execute("PRAGMA table_info(ProfileThresholds)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'Quality' not in columns:
            LoggingService.LogInfo("Quality column not found. Adding it to ProfileThresholds table...")
            cursor.execute("ALTER TABLE ProfileThresholds ADD COLUMN Quality INTEGER")
            connection.commit()
            LoggingService.LogInfo("Quality column added successfully!")
        else:
            LoggingService.LogInfo("Quality column already exists in ProfileThresholds table.")
        
        connection.close()
        
    except Exception as e:
        LoggingService.LogException("Error adding Quality column", e)
        raise

if __name__ == "__main__":
    AddQualityColumn()
