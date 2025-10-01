#!/usr/bin/env python3

import sys
from pathlib import Path
from datetime import datetime

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent))

from Services.DatabaseService import DatabaseService

def cleanup_stuck_scans():
    print("Cleaning up stuck scans...")
    
    try:
        db = DatabaseService()
        conn = db.GetConnection()
        cursor = conn.cursor()
        
        # Update stuck pending scans to failed
        cursor.execute("""
            UPDATE ScanJobs 
            SET Status = 'Failed', 
                EndTime = ?, 
                LastUpdated = ?,
                ErrorMessage = 'Cleaned up stuck scan from subprocess approach'
            WHERE Status = 'Pending'
        """, (datetime.now(), datetime.now()))
        
        affected_rows = cursor.rowcount
        conn.commit()
        conn.close()
        
        print(f"✅ Updated {affected_rows} stuck scans to 'Failed' status")
        
    except Exception as e:
        print(f"❌ Error cleaning up scans: {e}")

if __name__ == "__main__":
    cleanup_stuck_scans()
