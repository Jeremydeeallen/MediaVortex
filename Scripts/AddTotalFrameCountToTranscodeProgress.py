#!/usr/bin/env python3
"""
Migration script to add TotalFrameCount column to TranscodeProgress table.
This will allow accurate progress percentage calculations.
"""

import sqlite3
import os
from pathlib import Path

def AddTotalFrameCountColumn():
    """Add TotalFrameCount column to TranscodeProgress table."""
    
    # Get database path
    ScriptDir = Path(__file__).parent
    ProjectRoot = ScriptDir.parent
    DatabasePath = ProjectRoot / "Data" / "MediaVortex.db"
    
    if not DatabasePath.exists():
        print(f"ERROR: Database not found at {DatabasePath}")
        return False
    
    try:
        # Connect to database
        Connection = sqlite3.connect(DatabasePath)
        Cursor = Connection.cursor()
        
        print("Adding TotalFrameCount column to TranscodeProgress table...")
        
        # Add TotalFrameCount column
        Cursor.execute("""
            ALTER TABLE TranscodeProgress 
            ADD COLUMN TotalFrameCount INTEGER DEFAULT 0
        """)
        
        # Commit changes
        Connection.commit()
        
        print("✅ Successfully added TotalFrameCount column to TranscodeProgress table")
        
        # Verify the column was added
        Cursor.execute("PRAGMA table_info(TranscodeProgress)")
        Columns = Cursor.fetchall()
        
        ColumnNames = [Column[1] for Column in Columns]
        if 'TotalFrameCount' in ColumnNames:
            print("✅ Verified: TotalFrameCount column exists")
        else:
            print("❌ ERROR: TotalFrameCount column not found after migration")
            return False
        
        Connection.close()
        return True
        
    except Exception as e:
        print(f"❌ ERROR: Failed to add TotalFrameCount column: {str(e)}")
        if 'Connection' in locals():
            Connection.close()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("TranscodeProgress Migration: Add TotalFrameCount Column")
    print("=" * 60)
    
    Success = AddTotalFrameCountColumn()
    
    if Success:
        print("\n✅ Migration completed successfully!")
        print("The TranscodeProgress table now has a TotalFrameCount column.")
        print("This will allow accurate progress percentage calculations.")
    else:
        print("\n❌ Migration failed!")
        print("Please check the error messages above.")
    
    print("=" * 60)
