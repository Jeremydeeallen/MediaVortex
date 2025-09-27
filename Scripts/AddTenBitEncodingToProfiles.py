#!/usr/bin/env python3
"""
Add TenBitEncoding column to Profiles table to support 10-bit color encoding.
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

def AddTenBitEncodingColumn(cursor):
    """Add TenBitEncoding column to Profiles table."""
    try:
        print("Adding TenBitEncoding column to Profiles table...")
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(Profiles)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'TenBitEncoding' in columns:
            print("TenBitEncoding column already exists")
            return True
        
        # Add the column
        cursor.execute("ALTER TABLE Profiles ADD COLUMN TenBitEncoding BOOLEAN DEFAULT 0")
        
        print("TenBitEncoding column added successfully")
        return True
        
    except Exception as e:
        print(f"Error adding TenBitEncoding column: {e}")
        raise

def VerifyTenBitEncodingColumn(cursor):
    """Verify that the TenBitEncoding column was added correctly."""
    try:
        print("\nVerifying TenBitEncoding column...")
        
        cursor.execute("PRAGMA table_info(Profiles)")
        columns = cursor.fetchall()
        
        ten_bit_column = None
        for column in columns:
            if column[1] == 'TenBitEncoding':
                ten_bit_column = column
                break
        
        if ten_bit_column:
            print(f"✓ TenBitEncoding column found: {ten_bit_column[2]} (default: {ten_bit_column[4]})")
            return True
        else:
            print("✗ TenBitEncoding column not found")
            return False
            
    except Exception as e:
        print(f"Error verifying TenBitEncoding column: {e}")
        return False

def main():
    """Main function to add TenBitEncoding column to Profiles table."""
    try:
        db_path = GetDatabasePath()
        print(f"Database path: {db_path}")
        
        # Create backup
        backup_path = BackupDatabase(db_path)
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Add TenBitEncoding column
        success = AddTenBitEncodingColumn(cursor)
        
        if success:
            # Commit changes
            conn.commit()
            
            # Verify the changes
            VerifyTenBitEncodingColumn(cursor)
            
            print("\nTenBitEncoding column added successfully!")
            print("Next steps:")
            print("1. Run the database parameter script to add 10-bit encoding option")
            print("2. Test profile creation with 10-bit encoding enabled")
            print("3. Test transcoding with 10-bit encoding")
        else:
            print("Failed to add TenBitEncoding column")
            return False
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Update failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
