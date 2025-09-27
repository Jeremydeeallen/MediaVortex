#!/usr/bin/env python3
"""
Add 10-bit encoding option to AV1 (libsvtav1) codec configuration.
This adds a pixel format parameter to enable yuv420p10le for better color depth and reduced banding.
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

def Add10BitEncodingParameter(cursor):
    """Add 10-bit encoding parameter to AV1 codec configuration."""
    try:
        print("Adding 10-bit encoding parameter to AV1 configuration...")
        
        # Get AV1 codec ID
        cursor.execute("SELECT Id FROM CodecFlags WHERE CodecName = 'libsvtav1'")
        av1_codec_id = cursor.fetchone()
        
        if not av1_codec_id:
            print("ERROR: AV1 codec not found in CodecFlags table")
            return False
        
        av1_id = av1_codec_id[0]
        
        # Check if 10-bit parameter already exists
        cursor.execute("""
            SELECT Id FROM CodecParameters 
            WHERE CodecFlagsId = ? AND ParameterName = '10bit-encoding'
        """, (av1_id,))
        
        if cursor.fetchone():
            print("10-bit encoding parameter already exists, updating...")
            # Update existing parameter
            cursor.execute("""
                UPDATE CodecParameters SET
                    ParameterType = 'boolean',
                    MinValue = 0,
                    MaxValue = 1,
                    DefaultValue = 'false',
                    Description = 'Enable 10-bit color encoding (yuv420p10le) to reduce color banding and improve quality. Requires compatible playback devices.',
                    FFmpegFlag = '-pix_fmt'
                WHERE CodecFlagsId = ? AND ParameterName = '10bit-encoding'
            """, (av1_id,))
        else:
            # Insert new parameter
            cursor.execute("""
                INSERT INTO CodecParameters 
                (CodecFlagsId, ParameterName, ParameterType, MinValue, MaxValue, DefaultValue, Description, FFmpegFlag)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (av1_id, '10bit-encoding', 'boolean', 0, 1, 'false', 
                  'Enable 10-bit color encoding (yuv420p10le) to reduce color banding and improve quality. Requires compatible playback devices.',
                  '-pix_fmt'))
        
        print("10-bit encoding parameter added successfully")
        return True
        
    except Exception as e:
        print(f"Error adding 10-bit encoding parameter: {e}")
        raise

def Verify10BitParameter(cursor):
    """Verify that the 10-bit parameter was added correctly."""
    try:
        print("\nVerifying 10-bit encoding parameter...")
        
        cursor.execute("""
            SELECT cf.CodecName, cp.ParameterName, cp.ParameterType, cp.MinValue, cp.MaxValue, 
                   cp.DefaultValue, cp.Description, cp.FFmpegFlag
            FROM CodecParameters cp
            JOIN CodecFlags cf ON cp.CodecFlagsId = cf.Id
            WHERE cf.CodecName = 'libsvtav1' AND cp.ParameterName = '10bit-encoding'
        """)
        
        result = cursor.fetchone()
        if result:
            codec, param_name, param_type, min_val, max_val, default_val, description, ffmpeg_flag = result
            print(f"✓ {codec}.{param_name}: {param_type} {min_val}-{max_val} (default: {default_val})")
            print(f"  FFmpeg Flag: {ffmpeg_flag}")
            print(f"  Description: {description}")
            return True
        else:
            print("✗ 10-bit encoding parameter not found")
            return False
            
    except Exception as e:
        print(f"Error verifying 10-bit parameter: {e}")
        return False

def main():
    """Main function to add 10-bit encoding option to AV1."""
    try:
        db_path = GetDatabasePath()
        print(f"Database path: {db_path}")
        
        # Create backup
        backup_path = BackupDatabase(db_path)
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Add 10-bit encoding parameter
        success = Add10BitEncodingParameter(cursor)
        
        if success:
            # Commit changes
            conn.commit()
            
            # Verify the changes
            Verify10BitParameter(cursor)
            
            print("\n10-bit encoding option added successfully!")
            print("Next steps:")
            print("1. Update CommandBuilder to handle -pix_fmt yuv420p10le when 10-bit is enabled")
            print("2. Add UI controls for the 10-bit encoding option")
            print("3. Test transcoding with 10-bit encoding enabled")
        else:
            print("Failed to add 10-bit encoding parameter")
            return False
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Update failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
