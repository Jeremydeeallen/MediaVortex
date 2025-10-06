#!/usr/bin/env python3
"""
Add Quality Test Columns to TranscodeAttempts Script
Adds QualityTestRequired, QualityTestSkipped, and QualityTestCompleted columns to TranscodeAttempts table.
"""

import sqlite3
import os
from datetime import datetime

def AddQualityTestColumns():
    """Add quality test columns to TranscodeAttempts table."""
    try:
        # Get database path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(script_dir, "..", "Data", "MediaVortex.db")
        
        print(f"Adding quality test columns to TranscodeAttempts in: {db_path}")
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(TranscodeAttempts);")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Add columns if they don't exist
        columns_to_add = [
            ("QualityTestRequired", "BOOLEAN DEFAULT 0"),
            ("QualityTestSkipped", "BOOLEAN DEFAULT 0"),
            ("QualityTestCompleted", "BOOLEAN DEFAULT 0")
        ]
        
        for column_name, column_type in columns_to_add:
            if column_name not in columns:
                alter_sql = f"ALTER TABLE TranscodeAttempts ADD COLUMN {column_name} {column_type};"
                cursor.execute(alter_sql)
                print(f"✅ Added column: {column_name}")
            else:
                print(f"ℹ️  Column already exists: {column_name}")
        
        # Create indexes for performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_TranscodeAttempts_QualityTestRequired ON TranscodeAttempts(QualityTestRequired);",
            "CREATE INDEX IF NOT EXISTS idx_TranscodeAttempts_QualityTestCompleted ON TranscodeAttempts(QualityTestCompleted);"
        ]
        
        for index_sql in indexes:
            cursor.execute(index_sql)
            print(f"✅ Created index: {index_sql.split()[-1]}")
        
        # Commit changes
        conn.commit()
        print("✅ Quality test columns added successfully")
        
        # Verify column additions
        cursor.execute("PRAGMA table_info(TranscodeAttempts);")
        columns = cursor.fetchall()
        print("\n📋 TranscodeAttempts table structure (quality test columns):")
        for col in columns:
            if 'QualityTest' in col[1]:
                print(f"  - {col[1]} ({col[2]})")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error adding quality test columns: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Adding quality test columns to TranscodeAttempts...")
    success = AddQualityTestColumns()
    
    if success:
        print("\n✅ Quality test columns addition completed successfully!")
    else:
        print("\n❌ Quality test columns addition failed!")
