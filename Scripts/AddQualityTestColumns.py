#!/usr/bin/env python3
"""
Add missing columns to QualityTestingQueue table for simple QualityTest methods
"""

import sqlite3
import os
from datetime import datetime

def AddQualityTestColumns():
    """Add missing columns to QualityTestingQueue table"""
    try:
        # Get database path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.dirname(script_dir)
        db_path = os.path.join(project_dir, "Data", "MediaVortex.db")
        
        print(f"Adding columns to QualityTestingQueue table in {db_path}")
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if columns exist and add them if they don't
        cursor.execute("PRAGMA table_info(QualityTestingQueue)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        columns_to_add = [
            ("VMAFScore", "REAL"),
            ("CreatedDate", "DATETIME"),
            ("CompletedDate", "DATETIME")
        ]
        
        for column_name, column_type in columns_to_add:
            if column_name not in existing_columns:
                print(f"Adding column: {column_name} {column_type}")
                cursor.execute(f"ALTER TABLE QualityTestingQueue ADD COLUMN {column_name} {column_type}")
            else:
                print(f"Column {column_name} already exists")
        
        # Commit changes
        conn.commit()
        print("Successfully added columns to QualityTestingQueue table")
        
        # Show final table structure
        cursor.execute("PRAGMA table_info(QualityTestingQueue)")
        columns = cursor.fetchall()
        print("\nFinal QualityTestingQueue table structure:")
        for col in columns:
            print(f"  {col[1]} - {col[2]}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error adding columns: {e}")
        return False

if __name__ == "__main__":
    success = AddQualityTestColumns()
    if success:
        print("\nColumn addition completed successfully")
    else:
        print("\nColumn addition failed")
