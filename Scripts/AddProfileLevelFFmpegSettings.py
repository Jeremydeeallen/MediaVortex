#!/usr/bin/env python3
"""
Database migration script to add profile-level FFmpeg settings to the Profiles table.
This moves codec settings from ProfileThresholds to Profiles table and adds new settings.

New columns added to Profiles table:
- Codec: Video codec (libsvtav1, libx265, libx264, libvpx-vp9)
- Preset: Encoding preset (0-13, default 6)
- FilmGrain: Film grain level (0-50, default 10)
- YadifMode: Deinterlacing mode (0=off, 1=on, 2=spatial, 3=temporal, default 1)
- YadifParity: Deinterlacing parity (0=auto, 1=top, -1=bottom, default 1)
- YadifDeint: Deinterlacing type (0=all, 1=interlaced, default 1)

The existing Codec column in ProfileThresholds will be removed after migration.
"""

import sqlite3
import os
import sys
from datetime import datetime

def GetDatabasePath():
    """Get the database path relative to the script location."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    return os.path.join(project_root, 'Data', 'MediaVortex.db')

def BackupDatabase(db_path):
    """Create a backup of the database before making changes."""
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"Creating database backup: {backup_path}")
    
    # Copy the database file
    import shutil
    shutil.copy2(db_path, backup_path)
    print(f"Backup created successfully: {backup_path}")
    return backup_path

def AddProfileLevelColumns(cursor):
    """Add new profile-level FFmpeg settings columns to Profiles table."""
    print("Adding new columns to Profiles table...")
    
    # Add new columns with default values
    columns_to_add = [
        ("Codec", "TEXT", "libsvtav1", "Video codec for transcoding"),
        ("Preset", "INTEGER", "6", "Encoding preset (0-13, higher = slower but better quality)"),
        ("FilmGrain", "INTEGER", "10", "Film grain level (0-50, 0=off)"),
        ("YadifMode", "INTEGER", "1", "Deinterlacing mode (0=off, 1=on, 2=spatial, 3=temporal)"),
        ("YadifParity", "INTEGER", "1", "Deinterlacing parity (0=auto, 1=top, -1=bottom)"),
        ("YadifDeint", "INTEGER", "1", "Deinterlacing type (0=all, 1=interlaced)")
    ]
    
    for column_name, column_type, default_value, description in columns_to_add:
        try:
            # Check if column already exists
            cursor.execute(f"PRAGMA table_info(Profiles)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if column_name not in columns:
                print(f"  Adding column: {column_name} ({column_type})")
                cursor.execute(f"ALTER TABLE Profiles ADD COLUMN {column_name} {column_type} DEFAULT {default_value}")
            else:
                print(f"  Column {column_name} already exists, skipping...")
                
        except Exception as e:
            print(f"  Error adding column {column_name}: {e}")
            raise

def MigrateCodecData(cursor):
    """Migrate existing codec data from ProfileThresholds to Profiles table."""
    print("Migrating codec data from ProfileThresholds to Profiles...")
    
    # Get all unique profile IDs and their most common codec
    cursor.execute("""
        SELECT ProfileId, Codec, COUNT(*) as count
        FROM ProfileThresholds 
        WHERE Codec IS NOT NULL AND Codec != ''
        GROUP BY ProfileId, Codec
        ORDER BY ProfileId, count DESC
    """)
    
    codec_data = cursor.fetchall()
    
    # Update profiles with the most common codec for each profile
    for profile_id, codec, count in codec_data:
        try:
            # Get the most common codec for this profile
            cursor.execute("""
                SELECT Codec, COUNT(*) as count
                FROM ProfileThresholds 
                WHERE ProfileId = ? AND Codec IS NOT NULL AND Codec != ''
                GROUP BY Codec
                ORDER BY count DESC
                LIMIT 1
            """, (profile_id,))
            
            result = cursor.fetchone()
            if result:
                most_common_codec = result[0]
                print(f"  Updating Profile {profile_id} with codec: {most_common_codec}")
                cursor.execute("UPDATE Profiles SET Codec = ? WHERE Id = ?", (most_common_codec, profile_id))
                
        except Exception as e:
            print(f"  Error migrating codec for Profile {profile_id}: {e}")
            # Continue with other profiles

def RemoveCodecFromThresholds(cursor):
    """Remove the Codec column from ProfileThresholds table since it's now in Profiles."""
    print("Removing Codec column from ProfileThresholds table...")
    
    # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
    try:
        # Get the current table structure
        cursor.execute("PRAGMA table_info(ProfileThresholds)")
        columns = cursor.fetchall()
        
        # Create new table without Codec column
        new_columns = []
        for col in columns:
            if col[1] != 'Codec':  # Skip the Codec column
                new_columns.append(f"{col[1]} {col[2]}")
        
        # Create new table
        create_sql = f"""
        CREATE TABLE ProfileThresholds_new (
            {', '.join(new_columns)}
        )
        """
        cursor.execute(create_sql)
        
        # Copy data (excluding Codec column)
        old_columns = [col[1] for col in columns if col[1] != 'Codec']
        insert_sql = f"""
        INSERT INTO ProfileThresholds_new ({', '.join(old_columns)})
        SELECT {', '.join(old_columns)} FROM ProfileThresholds
        """
        cursor.execute(insert_sql)
        
        # Drop old table and rename new one
        cursor.execute("DROP TABLE ProfileThresholds")
        cursor.execute("ALTER TABLE ProfileThresholds_new RENAME TO ProfileThresholds")
        
        # Recreate indexes
        cursor.execute("CREATE UNIQUE INDEX idx_ProfileThresholds_ProfileId_Resolution ON ProfileThresholds(ProfileId, Resolution)")
        
        print("  Codec column removed from ProfileThresholds table")
        
    except Exception as e:
        print(f"  Error removing Codec column: {e}")
        raise

def VerifyMigration(cursor):
    """Verify that the migration was successful."""
    print("Verifying migration...")
    
    # Check Profiles table has new columns
    cursor.execute("PRAGMA table_info(Profiles)")
    profile_columns = [row[1] for row in cursor.fetchall()]
    
    expected_columns = ['Codec', 'Preset', 'FilmGrain', 'YadifMode', 'YadifParity', 'YadifDeint']
    for col in expected_columns:
        if col in profile_columns:
            print(f"  ✓ Profiles table has {col} column")
        else:
            print(f"  ✗ Profiles table missing {col} column")
    
    # Check ProfileThresholds table no longer has Codec column
    cursor.execute("PRAGMA table_info(ProfileThresholds)")
    threshold_columns = [row[1] for row in cursor.fetchall()]
    
    if 'Codec' not in threshold_columns:
        print("  ✓ Codec column removed from ProfileThresholds table")
    else:
        print("  ✗ Codec column still exists in ProfileThresholds table")
    
    # Check data migration
    cursor.execute("SELECT COUNT(*) FROM Profiles WHERE Codec IS NOT NULL")
    profiles_with_codec = cursor.fetchone()[0]
    print(f"  ✓ {profiles_with_codec} profiles have codec settings")

def main():
    """Main migration function."""
    print("=== Profile Level FFmpeg Settings Migration ===")
    print(f"Started at: {datetime.now()}")
    
    db_path = GetDatabasePath()
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)
    
    # Create backup
    backup_path = BackupDatabase(db_path)
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("Connected to database successfully")
        
        # Add new columns to Profiles table
        AddProfileLevelColumns(cursor)
        
        # Migrate existing codec data
        MigrateCodecData(cursor)
        
        # Remove Codec column from ProfileThresholds
        RemoveCodecFromThresholds(cursor)
        
        # Commit changes
        conn.commit()
        print("Database changes committed successfully")
        
        # Verify migration
        VerifyMigration(cursor)
        
        print("\n=== Migration completed successfully ===")
        print(f"Backup created at: {backup_path}")
        
    except Exception as e:
        print(f"\nError during migration: {e}")
        print(f"Database backup available at: {backup_path}")
        conn.rollback()
        sys.exit(1)
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()
