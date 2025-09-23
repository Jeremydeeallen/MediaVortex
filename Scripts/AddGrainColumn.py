#!/usr/bin/env python3
"""
Script to add Grain column to ProfileThresholds table if it doesn't exist.
"""

import sqlite3
import os
import sys

# Add the parent directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Services.LoggingService import LoggingService

def AddGrainColumn():
    """Add Grain column to ProfileThresholds table if it doesn't exist."""
    try:
        # Connect to the database
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Data', 'MediaVortex.db')
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        
        # Check if Grain column exists
        cursor.execute("PRAGMA table_info(ProfileThresholds)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'Grain' not in columns:
            LoggingService.LogInfo("Grain column not found. Adding it to ProfileThresholds table...")
            cursor.execute("ALTER TABLE ProfileThresholds ADD COLUMN Grain BIT DEFAULT 0")
            connection.commit()
            LoggingService.LogInfo("Grain column added successfully!")
        else:
            LoggingService.LogInfo("Grain column already exists in ProfileThresholds table.")
        
        connection.close()
        
    except Exception as e:
        LoggingService.LogException("Error adding Grain column", e)
        raise

if __name__ == "__main__":
    AddGrainColumn()
