#!/usr/bin/env python3
"""
Update CodecFlags and CodecParameters with friendly descriptions and correct configurations.
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

def UpdateCodecFlagsWithFriendlyNotes(cursor):
    """Update CodecFlags with better defaults and friendly information."""
    try:
        print("Updating CodecFlags with friendly notes...")
        
        # Update libsvtav1 (AV1) - fix defaults to be more practical
        cursor.execute("""
            UPDATE CodecFlags SET
                PresetDefault = 6,  -- More practical default than -2
                FilmGrainDefault = 10
            WHERE CodecName = 'libsvtav1'
        """)
        
        # Update libx265 (H.265) - ensure correct defaults
        cursor.execute("""
            UPDATE CodecFlags SET
                PresetDefault = 6,  -- medium preset
                FilmGrainDefault = 0  -- off by default
            WHERE CodecName = 'libx265'
        """)
        
        print("CodecFlags updated successfully")
        
    except Exception as e:
        print(f"Error updating CodecFlags: {e}")
        raise

def UpdateCodecParametersWithFriendlyNotes(cursor):
    """Update CodecParameters with friendly descriptions and correct defaults."""
    try:
        print("Updating CodecParameters with friendly notes...")
        
        # Get CodecFlags IDs
        cursor.execute("SELECT Id, CodecName FROM CodecFlags WHERE CodecName IN ('libsvtav1', 'libx265', 'libx264', 'libvpx-vp9')")
        codec_ids = {row[1]: row[0] for row in cursor.fetchall()}
        
        # Clear existing parameters
        cursor.execute("DELETE FROM CodecParameters")
        
        # libsvtav1 (AV1) parameters with friendly descriptions
        svtav1_params = [
            ('preset', 'integer', -2, 13, '6', 
             'Encoding speed vs quality balance. Lower = better quality but slower. 6 is a good balance.',
             '-preset'),
            ('crf', 'integer', 0, 63, '30', 
             'Constant Rate Factor for quality control. Lower = better quality, larger files. 30 is good for most content.',
             '-crf'),
            ('qp', 'integer', 0, 63, '30', 
             'Quantization Parameter. Lower = better quality, larger files. Usually same as CRF.',
             '-qp'),
            ('film-grain', 'integer', 0, 50, '10', 
             'Film grain synthesis level. 0=off, 10-20=light grain, 30-50=heavy grain. Helps preserve film texture.',
             '-svtav1-params film-grain'),
            ('tune', 'integer', 0, 2, '0', 
             'Optimization target: 0=visual quality, 1=PSNR metric, 2=VMAF metric. Use 0 for best visual results.',
             '-svtav1-params tune'),
        ]
        
        for param_name, param_type, min_val, max_val, default_val, description, ffmpeg_flag in svtav1_params:
            cursor.execute("""
                INSERT INTO CodecParameters 
                (CodecFlagsId, ParameterName, ParameterType, MinValue, MaxValue, DefaultValue, Description, FFmpegFlag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (codec_ids['libsvtav1'], param_name, param_type, min_val, max_val, default_val, description, ffmpeg_flag))
        
        # libx265 (H.265) parameters with friendly descriptions
        x265_params = [
            ('preset', 'string', None, None, 'medium', 
             'Encoding speed vs quality balance. Options: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow, placebo. Medium is a good balance.',
             '-preset'),
            ('crf', 'float', -1, 51, '23', 
             'Constant Rate Factor for quality control. Lower = better quality, larger files. 23 is good for most content, 18-28 is typical range.',
             '-crf'),
            ('qp', 'integer', -1, 51, '23', 
             'Quantization Parameter. Lower = better quality, larger files. Usually same as CRF.',
             '-qp'),
            ('profile', 'string', None, None, 'main', 
             'H.265 profile for compatibility. main=good compatibility, main10=10-bit color (better quality, newer devices), mainstillpicture=still images only.',
             '-profile'),
            ('tune', 'string', None, None, 'none', 
             'Content optimization: none=default, grain=preserve film grain, fastdecode=optimize for playback, zerolatency=streaming, animation=cartoons, psnr/ssim=metrics.',
             '-tune'),
        ]
        
        for param_name, param_type, min_val, max_val, default_val, description, ffmpeg_flag in x265_params:
            cursor.execute("""
                INSERT INTO CodecParameters 
                (CodecFlagsId, ParameterName, ParameterType, MinValue, MaxValue, DefaultValue, Description, FFmpegFlag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (codec_ids['libx265'], param_name, param_type, min_val, max_val, default_val, description, ffmpeg_flag))
        
        # libx264 (H.264) parameters with friendly descriptions
        x264_params = [
            ('preset', 'string', None, None, 'medium', 
             'Encoding speed vs quality balance. Options: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow, placebo. Medium is a good balance.',
             '-preset'),
            ('crf', 'integer', 0, 51, '23', 
             'Constant Rate Factor for quality control. Lower = better quality, larger files. 23 is good for most content, 18-28 is typical range.',
             '-crf'),
            ('qp', 'integer', 0, 51, '23', 
             'Quantization Parameter. Lower = better quality, larger files. Usually same as CRF.',
             '-qp'),
            ('profile', 'string', None, None, 'high', 
             'H.264 profile for compatibility. baseline=oldest devices, main=good compatibility, high=best quality (most common).',
             '-profile'),
            ('tune', 'string', None, None, 'none', 
             'Content optimization: none=default, film=preserve film grain, animation=cartoons, grain=preserve grain, fastdecode=optimize for playback, zerolatency=streaming.',
             '-tune'),
        ]
        
        for param_name, param_type, min_val, max_val, default_val, description, ffmpeg_flag in x264_params:
            cursor.execute("""
                INSERT INTO CodecParameters 
                (CodecFlagsId, ParameterName, ParameterType, MinValue, MaxValue, DefaultValue, Description, FFmpegFlag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (codec_ids['libx264'], param_name, param_type, min_val, max_val, default_val, description, ffmpeg_flag))
        
        # libvpx-vp9 (VP9) parameters with friendly descriptions
        vp9_params = [
            ('preset', 'integer', 0, 5, '2', 
             'Encoding speed vs quality balance. 0=best quality (slowest), 5=fastest encoding. 2 is a good balance.',
             '-preset'),
            ('crf', 'integer', 0, 63, '30', 
             'Constant Rate Factor for quality control. Lower = better quality, larger files. 30 is good for most content.',
             '-crf'),
            ('qp', 'integer', 0, 63, '30', 
             'Quantization Parameter. Lower = better quality, larger files. Usually same as CRF.',
             '-qp'),
        ]
        
        for param_name, param_type, min_val, max_val, default_val, description, ffmpeg_flag in vp9_params:
            cursor.execute("""
                INSERT INTO CodecParameters 
                (CodecFlagsId, ParameterName, ParameterType, MinValue, MaxValue, DefaultValue, Description, FFmpegFlag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (codec_ids['libvpx-vp9'], param_name, param_type, min_val, max_val, default_val, description, ffmpeg_flag))
        
        print("CodecParameters updated successfully")
        
    except Exception as e:
        print(f"Error updating CodecParameters: {e}")
        raise

def AddPresetOptionsTable(cursor):
    """Add a table to store preset options for string-based presets."""
    try:
        print("Adding PresetOptions table...")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS PresetOptions (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                CodecFlagsId INTEGER NOT NULL,
                PresetValue TEXT NOT NULL,
                PresetName TEXT NOT NULL,
                Description TEXT,
                SortOrder INTEGER DEFAULT 0,
                CreatedDate DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (CodecFlagsId) REFERENCES CodecFlags(Id),
                UNIQUE(CodecFlagsId, PresetValue)
            )
        """)
        
        # Get CodecFlags IDs for string presets
        cursor.execute("SELECT Id, CodecName FROM CodecFlags WHERE PresetType = 'string'")
        string_codecs = {row[1]: row[0] for row in cursor.fetchall()}
        
        # libx265 preset options
        x265_presets = [
            ('ultrafast', 'Ultra Fast', 'Fastest encoding, lowest compression efficiency', 0),
            ('superfast', 'Super Fast', 'Very fast encoding, low compression', 1),
            ('veryfast', 'Very Fast', 'Fast encoding, moderate compression', 2),
            ('faster', 'Faster', 'Faster than default, good compression', 3),
            ('fast', 'Fast', 'Fast encoding, good compression', 4),
            ('medium', 'Medium', 'Default preset - good balance of speed and quality', 5),
            ('slow', 'Slow', 'Slower encoding, better compression', 6),
            ('slower', 'Slower', 'Slower encoding, better compression', 7),
            ('veryslow', 'Very Slow', 'Very slow encoding, best compression', 8),
            ('placebo', 'Placebo', 'Slowest encoding, best compression (not recommended)', 9),
        ]
        
        for preset_value, preset_name, description, sort_order in x265_presets:
            cursor.execute("""
                INSERT OR REPLACE INTO PresetOptions 
                (CodecFlagsId, PresetValue, PresetName, Description, SortOrder)
                VALUES (?, ?, ?, ?, ?)
            """, (string_codecs['libx265'], preset_value, preset_name, description, sort_order))
        
        # libx264 preset options (same as x265)
        for preset_value, preset_name, description, sort_order in x265_presets:
            cursor.execute("""
                INSERT OR REPLACE INTO PresetOptions 
                (CodecFlagsId, PresetValue, PresetName, Description, SortOrder)
                VALUES (?, ?, ?, ?, ?)
            """, (string_codecs['libx264'], preset_value, preset_name, description, sort_order))
        
        print("PresetOptions table created and populated successfully")
        
    except Exception as e:
        print(f"Error creating PresetOptions table: {e}")
        raise

def VerifyConfiguration(cursor):
    """Verify the updated configuration."""
    try:
        print("\nVerifying updated configuration...")
        
        # Check CodecFlags
        cursor.execute("""
            SELECT CodecName, DisplayName, PresetType, PresetMin, PresetMax, PresetDefault, 
                   FilmGrainType, FilmGrainMin, FilmGrainMax, FilmGrainDefault
            FROM CodecFlags 
            ORDER BY CodecName
        """)
        
        print("Updated CodecFlags:")
        for row in cursor.fetchall():
            codec, display, preset_type, preset_min, preset_max, preset_default, grain_type, grain_min, grain_max, grain_default = row
            print(f"  {codec} ({display}): Preset={preset_type} {preset_min}-{preset_max} (default: {preset_default}), FilmGrain={grain_type} {grain_min}-{grain_max} (default: {grain_default})")
        
        # Check CodecParameters
        cursor.execute("""
            SELECT cf.CodecName, cp.ParameterName, cp.ParameterType, cp.MinValue, cp.MaxValue, cp.DefaultValue, cp.Description
            FROM CodecParameters cp
            JOIN CodecFlags cf ON cp.CodecFlagsId = cf.Id
            ORDER BY cf.CodecName, cp.ParameterName
        """)
        
        print("\nCodecParameters with friendly descriptions:")
        for row in cursor.fetchall():
            codec, param_name, param_type, min_val, max_val, default_val, description = row
            range_str = f"{min_val}-{max_val}" if min_val is not None and max_val is not None else "N/A"
            print(f"  {codec}.{param_name}: {param_type} {range_str} (default: {default_val})")
            print(f"    Description: {description}")
        
        # Check PresetOptions
        cursor.execute("""
            SELECT cf.CodecName, po.PresetValue, po.PresetName, po.Description
            FROM PresetOptions po
            JOIN CodecFlags cf ON po.CodecFlagsId = cf.Id
            ORDER BY cf.CodecName, po.SortOrder
        """)
        
        print("\nPresetOptions:")
        current_codec = None
        for row in cursor.fetchall():
            codec, preset_value, preset_name, description = row
            if codec != current_codec:
                print(f"  {codec}:")
                current_codec = codec
            print(f"    {preset_value} ({preset_name}): {description}")
        
    except Exception as e:
        print(f"Error verifying configuration: {e}")
        raise

def main():
    """Main function to update codec configuration with friendly notes."""
    try:
        db_path = GetDatabasePath()
        print(f"Database path: {db_path}")
        
        # Create backup
        backup_path = BackupDatabase(db_path)
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Update configuration
        UpdateCodecFlagsWithFriendlyNotes(cursor)
        UpdateCodecParametersWithFriendlyNotes(cursor)
        AddPresetOptionsTable(cursor)
        
        # Commit changes
        conn.commit()
        
        # Verify the changes
        VerifyConfiguration(cursor)
        
        conn.close()
        print("\nCodec configuration update completed successfully!")
        
    except Exception as e:
        print(f"Update failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
