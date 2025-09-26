#!/usr/bin/env python3
"""
Remove Grain column from ProfileThresholds table.

The Grain setting is now handled at the profile level (Profiles.FilmGrain)
and should not be duplicated in ProfileThresholds table.
"""

import os
import sys
import sqlite3
from datetime import datetime

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Services.LoggingService import LoggingService
from Repositories.DatabaseManager import DatabaseManager

def RemoveGrainFromProfileThresholds():
    """Remove the Grain column from ProfileThresholds table."""
    try:
        LoggingService.LogFunctionEntry("RemoveGrainFromProfileThresholds", "MigrationScript")
        
        # Get database path
        db_path = os.path.join(project_root, 'Data', 'MediaVortex.db')
        
        # Create backup
        backup_path = BackupDatabase(db_path)
        LoggingService.LogInfo(f"Database backed up to: {backup_path}", "RemoveGrainFromProfileThresholds", "MigrationScript")
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        try:
            # Check if Grain column exists
            cursor.execute("PRAGMA table_info(ProfileThresholds)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if 'Grain' not in column_names:
                LoggingService.LogInfo("Grain column does not exist in ProfileThresholds table", "RemoveGrainFromProfileThresholds", "MigrationScript")
                return True
            
            LoggingService.LogInfo("Grain column found in ProfileThresholds table, removing it...", "RemoveGrainFromProfileThresholds", "MigrationScript")
            
            # Drop new table if it exists from previous failed attempt
            cursor.execute("DROP TABLE IF EXISTS ProfileThresholds_new")
            
            # Create new table without Grain column
            cursor.execute("""
                CREATE TABLE ProfileThresholds_new (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ProfileId INTEGER NOT NULL,
                    Resolution TEXT NOT NULL,
                    Under30MinMB INTEGER NOT NULL DEFAULT 0,
                    Under65MinMB INTEGER NOT NULL DEFAULT 0,
                    Over65MinMB INTEGER NOT NULL DEFAULT 0,
                    VideoBitrateKbps INTEGER NOT NULL DEFAULT 0,
                    AudioBitrateKbps INTEGER NOT NULL DEFAULT 0,
                    FallbackVideoBitrateKbps INTEGER NOT NULL DEFAULT 0,
                    FallbackAudioBitrateKbps INTEGER NOT NULL DEFAULT 0,
                    TranscodeDownTo TEXT NOT NULL DEFAULT '',
                    Quality INTEGER,
                    KeepSource BOOLEAN NOT NULL DEFAULT 0,
                    ContainerType TEXT NOT NULL DEFAULT 'mp4',
                    FOREIGN KEY (ProfileId) REFERENCES Profiles (Id) ON DELETE CASCADE,
                    UNIQUE(ProfileId, Resolution)
                )
            """)
            
            # Copy data from old table to new table (excluding Grain column)
            cursor.execute("""
                INSERT INTO ProfileThresholds_new 
                (Id, ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB,
                 VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps,
                 FallbackAudioBitrateKbps, TranscodeDownTo, Quality, KeepSource, ContainerType)
                SELECT Id, ProfileId, Resolution, Under30MinMB, Under65MinMB, Over65MinMB,
                       VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps,
                       FallbackAudioBitrateKbps, 
                       COALESCE(TranscodeDownTo, '') as TranscodeDownTo, 
                       Quality, KeepSource, ContainerType
                FROM ProfileThresholds
            """)
            
            # Drop old table
            cursor.execute("DROP TABLE ProfileThresholds")
            
            # Rename new table
            cursor.execute("ALTER TABLE ProfileThresholds_new RENAME TO ProfileThresholds")
            
            # Commit changes
            conn.commit()
            
            LoggingService.LogInfo("Successfully removed Grain column from ProfileThresholds table", "RemoveGrainFromProfileThresholds", "MigrationScript")
            return True
            
        except Exception as e:
            conn.rollback()
            LoggingService.LogException("Error removing Grain column", e, "RemoveGrainFromProfileThresholds", "MigrationScript")
            return False
        finally:
            conn.close()
            
    except Exception as e:
        LoggingService.LogException("Error in RemoveGrainFromProfileThresholds", e, "RemoveGrainFromProfileThresholds", "MigrationScript")
        return False

def BackupDatabase(db_path):
    """Create a backup of the database before making changes."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    
    import shutil
    shutil.copy2(db_path, backup_path)
    return backup_path

if __name__ == "__main__":
    success = RemoveGrainFromProfileThresholds()
    if success:
        print("✅ Successfully removed Grain column from ProfileThresholds table")
        print("Film grain settings are now handled exclusively by Profiles.FilmGrain")
    else:
        print("❌ Failed to remove Grain column from ProfileThresholds table")
        sys.exit(1)
