#!/usr/bin/env python3
"""
Create CodecFlags table to store codec-specific configuration options.
This allows each codec to have its own set of parameters and presets.
"""

import sqlite3
import os
import shutil
from datetime import datetime

def GetDatabasePath():
    """Get the database path."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    return os.path.join(project_root, 'Data', 'MediaVortex.db')

def BackupDatabase(db_path):
    """Create a backup of the database."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    print(f"Database backed up to: {backup_path}")
    return backup_path

def CreateCodecFlagsTable(cursor):
    """Create the CodecFlags table."""
    try:
        print("Creating CodecFlags table...")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS CodecFlags (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                CodecName TEXT NOT NULL UNIQUE,
                DisplayName TEXT NOT NULL,
                PresetType TEXT NOT NULL,  -- 'string' or 'numeric'
                PresetMin INTEGER,         -- For numeric presets
                PresetMax INTEGER,         -- For numeric presets
                PresetDefault INTEGER,     -- Default preset value
                PresetOptions TEXT,        -- JSON string of preset options for string presets
                FilmGrainType TEXT NOT NULL,  -- 'boolean' or 'numeric'
                FilmGrainMin INTEGER,      -- For numeric film grain
                FilmGrainMax INTEGER,      -- For numeric film grain
                FilmGrainDefault INTEGER,  -- Default film grain value
                TuneOptions TEXT,          -- JSON string of available tune options
                CreatedDate DATETIME DEFAULT CURRENT_TIMESTAMP,
                LastModified DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        print("CodecFlags table created successfully")
        
    except Exception as e:
        print(f"Error creating CodecFlags table: {e}")
        raise

def InsertCodecConfigurations(cursor):
    """Insert default codec configurations."""
    try:
        print("Inserting codec configurations...")
        
        # H.265 (libx265) configuration
        cursor.execute("""
            INSERT OR REPLACE INTO CodecFlags (
                CodecName, DisplayName, PresetType, PresetMin, PresetMax, PresetDefault,
                PresetOptions, FilmGrainType, FilmGrainMin, FilmGrainMax, FilmGrainDefault,
                TuneOptions
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'libx265',
            'H.265 (libx265)',
            'string',
            0, 9, 6,  # Preset range 0-9, default 6 (medium)
            '["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow", "placebo"]',
            'boolean',
            0, 1, 0,  # Boolean film grain, default off
            '["grain", "fastdecode", "zerolatency", "animation", "psnr", "ssim"]'
        ))
        
        # AV1 (libsvtav1) configuration
        cursor.execute("""
            INSERT OR REPLACE INTO CodecFlags (
                CodecName, DisplayName, PresetType, PresetMin, PresetMax, PresetDefault,
                PresetOptions, FilmGrainType, FilmGrainMin, FilmGrainMax, FilmGrainDefault,
                TuneOptions
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'libsvtav1',
            'AV1 (libsvtav1)',
            'numeric',
            0, 13, 6,  # Preset range 0-13, default 6
            'null',  # No string presets for AV1
            'numeric',
            0, 50, 10,  # Numeric film grain 0-50, default 10
            'null'  # No tune options for AV1
        ))
        
        # H.264 (libx264) configuration
        cursor.execute("""
            INSERT OR REPLACE INTO CodecFlags (
                CodecName, DisplayName, PresetType, PresetMin, PresetMax, PresetDefault,
                PresetOptions, FilmGrainType, FilmGrainMin, FilmGrainMax, FilmGrainDefault,
                TuneOptions
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'libx264',
            'H.264 (libx264)',
            'string',
            0, 9, 6,  # Preset range 0-9, default 6 (medium)
            '["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow", "placebo"]',
            'boolean',
            0, 1, 0,  # Boolean film grain, default off
            '["film", "animation", "grain", "stillimage", "fastdecode", "zerolatency", "psnr", "ssim"]'
        ))
        
        # VP9 (libvpx-vp9) configuration
        cursor.execute("""
            INSERT OR REPLACE INTO CodecFlags (
                CodecName, DisplayName, PresetType, PresetMin, PresetMax, PresetDefault,
                PresetOptions, FilmGrainType, FilmGrainMin, FilmGrainMax, FilmGrainDefault,
                TuneOptions
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'libvpx-vp9',
            'VP9 (libvpx-vp9)',
            'numeric',
            0, 5, 2,  # Preset range 0-5, default 2
            'null',  # No string presets for VP9
            'boolean',
            0, 1, 0,  # Boolean film grain, default off
            'null'  # No tune options for VP9
        ))
        
        print("Codec configurations inserted successfully")
        
    except Exception as e:
        print(f"Error inserting codec configurations: {e}")
        raise

def UpdateProfilesTable(cursor):
    """Update Profiles table to reference CodecFlags."""
    try:
        print("Updating Profiles table...")
        
        # Add CodecFlagsId column to Profiles table
        cursor.execute("""
            ALTER TABLE Profiles ADD COLUMN CodecFlagsId INTEGER
        """)
        
        # Update existing profiles to reference the correct CodecFlags
        cursor.execute("""
            UPDATE Profiles 
            SET CodecFlagsId = (
                SELECT Id FROM CodecFlags 
                WHERE CodecFlags.CodecName = Profiles.Codec
            )
        """)
        
        print("Profiles table updated successfully")
        
    except Exception as e:
        print(f"Error updating Profiles table: {e}")
        raise

def main():
    """Main function to create CodecFlags table and populate it."""
    try:
        db_path = GetDatabasePath()
        print(f"Database path: {db_path}")
        
        # Create backup
        backup_path = BackupDatabase(db_path)
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create table and insert data
        CreateCodecFlagsTable(cursor)
        InsertCodecConfigurations(cursor)
        UpdateProfilesTable(cursor)
        
        # Commit changes
        conn.commit()
        print("All changes committed successfully")
        
        # Verify the table
        cursor.execute("SELECT * FROM CodecFlags")
        rows = cursor.fetchall()
        print(f"\nCodecFlags table contains {len(rows)} entries:")
        for row in rows:
            print(f"  {row[1]} ({row[2]}) - Preset: {row[3]}, FilmGrain: {row[7]}")
        
        conn.close()
        print("\nMigration completed successfully!")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
