#!/usr/bin/env python3
"""
Update CodecFlags table with correct FFmpeg parameters based on actual encoder documentation.
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

def UpdateCodecFlagsConfiguration(cursor):
    """Update CodecFlags with correct FFmpeg parameters."""
    try:
        print("Updating CodecFlags configuration...")
        
        # Update libsvtav1 (AV1) configuration
        cursor.execute("""
            UPDATE CodecFlags SET
                PresetMin = -2,
                PresetMax = 13,
                PresetDefault = -2,
                FilmGrainMin = 0,
                FilmGrainMax = 50,
                FilmGrainDefault = 10
            WHERE CodecName = 'libsvtav1'
        """)
        
        # Update libx265 (H.265) configuration - add missing parameters
        cursor.execute("""
            UPDATE CodecFlags SET
                PresetMin = 0,
                PresetMax = 9,
                PresetDefault = 6
            WHERE CodecName = 'libx265'
        """)
        
        # Add additional parameters table for codec-specific options
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS CodecParameters (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                CodecFlagsId INTEGER NOT NULL,
                ParameterName TEXT NOT NULL,
                ParameterType TEXT NOT NULL,  -- 'string', 'integer', 'float', 'boolean'
                MinValue REAL,
                MaxValue REAL,
                DefaultValue TEXT,
                Description TEXT,
                FFmpegFlag TEXT NOT NULL,  -- The actual FFmpeg flag (e.g., '-crf', '-qp')
                CreatedDate DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (CodecFlagsId) REFERENCES CodecFlags(Id),
                UNIQUE(CodecFlagsId, ParameterName)
            )
        """)
        
        # Get CodecFlags IDs
        cursor.execute("SELECT Id, CodecName FROM CodecFlags WHERE CodecName IN ('libsvtav1', 'libx265')")
        codec_ids = {row[1]: row[0] for row in cursor.fetchall()}
        
        # Insert libsvtav1 parameters
        svtav1_params = [
            ('crf', 'integer', 0, 63, '0', 'Constant Rate Factor (0-63, lower = better quality)', '-crf'),
            ('qp', 'integer', 0, 63, '0', 'Initial Quantizer level (0-63)', '-qp'),
            ('film-grain', 'integer', 0, 50, '10', 'Film grain synthesis level (0-50, 0=off)', '-svtav1-params film-grain'),
        ]
        
        for param_name, param_type, min_val, max_val, default_val, description, ffmpeg_flag in svtav1_params:
            cursor.execute("""
                INSERT OR REPLACE INTO CodecParameters 
                (CodecFlagsId, ParameterName, ParameterType, MinValue, MaxValue, DefaultValue, Description, FFmpegFlag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (codec_ids['libsvtav1'], param_name, param_type, min_val, max_val, default_val, description, ffmpeg_flag))
        
        # Insert libx265 parameters
        x265_params = [
            ('crf', 'float', -1, 51, '23', 'Constant Rate Factor (-1 to 51, lower = better quality)', '-crf'),
            ('qp', 'integer', -1, 51, '23', 'Quantization Parameter (-1 to 51)', '-qp'),
            ('profile', 'string', None, None, 'main', 'H.265 profile (main, main10, mainstillpicture)', '-profile'),
            ('tune', 'string', None, None, 'none', 'Tuning option (grain, fastdecode, zerolatency, animation, psnr, ssim)', '-tune'),
        ]
        
        for param_name, param_type, min_val, max_val, default_val, description, ffmpeg_flag in x265_params:
            cursor.execute("""
                INSERT OR REPLACE INTO CodecParameters 
                (CodecFlagsId, ParameterName, ParameterType, MinValue, MaxValue, DefaultValue, Description, FFmpegFlag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (codec_ids['libx265'], param_name, param_type, min_val, max_val, default_val, description, ffmpeg_flag))
        
        print("CodecFlags configuration updated successfully")
        
    except Exception as e:
        print(f"Error updating CodecFlags configuration: {e}")
        raise

def VerifyConfiguration(cursor):
    """Verify the updated configuration."""
    try:
        print("\nVerifying updated configuration...")
        
        # Check CodecFlags
        cursor.execute("""
            SELECT CodecName, PresetType, PresetMin, PresetMax, PresetDefault, 
                   FilmGrainType, FilmGrainMin, FilmGrainMax, FilmGrainDefault
            FROM CodecFlags 
            WHERE CodecName IN ('libsvtav1', 'libx265')
            ORDER BY CodecName
        """)
        
        print("Updated CodecFlags:")
        for row in cursor.fetchall():
            codec, preset_type, preset_min, preset_max, preset_default, grain_type, grain_min, grain_max, grain_default = row
            print(f"  {codec}: Preset={preset_type} {preset_min}-{preset_max} (default: {preset_default}), FilmGrain={grain_type} {grain_min}-{grain_max} (default: {grain_default})")
        
        # Check CodecParameters
        cursor.execute("""
            SELECT cf.CodecName, cp.ParameterName, cp.ParameterType, cp.MinValue, cp.MaxValue, cp.DefaultValue, cp.FFmpegFlag
            FROM CodecParameters cp
            JOIN CodecFlags cf ON cp.CodecFlagsId = cf.Id
            WHERE cf.CodecName IN ('libsvtav1', 'libx265')
            ORDER BY cf.CodecName, cp.ParameterName
        """)
        
        print("\nCodecParameters:")
        for row in cursor.fetchall():
            codec, param_name, param_type, min_val, max_val, default_val, ffmpeg_flag = row
            range_str = f"{min_val}-{max_val}" if min_val is not None and max_val is not None else "N/A"
            print(f"  {codec}.{param_name}: {param_type} {range_str} (default: {default_val}) -> {ffmpeg_flag}")
        
    except Exception as e:
        print(f"Error verifying configuration: {e}")
        raise

def main():
    """Main function to update CodecFlags configuration."""
    try:
        db_path = GetDatabasePath()
        print(f"Database path: {db_path}")
        
        # Create backup
        backup_path = BackupDatabase(db_path)
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Update configuration
        UpdateCodecFlagsConfiguration(cursor)
        
        # Commit changes
        conn.commit()
        
        # Verify the changes
        VerifyConfiguration(cursor)
        
        conn.close()
        print("\nCodecFlags configuration update completed successfully!")
        
    except Exception as e:
        print(f"Update failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
