#!/usr/bin/env python3

import sys
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.append(str(Path(__file__).parent))

from Services.LoggingService import LoggingService
from Services.DatabaseService import DatabaseService

def test_logging():
    print("Testing LoggingService...")
    
    # Test database connection
    try:
        db = DatabaseService()
        conn = db.GetConnection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        print("✅ Database connection successful")
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return
    
    # Test logging
    try:
        LoggingService.LogInfo("Test log message from test_logging.py", "test_logging", "test_logging")
        print("✅ Log message sent successfully")
    except Exception as e:
        print(f"❌ Logging error: {e}")
        return
    
    # Check if log was written
    try:
        conn = db.GetConnection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Logs WHERE Message LIKE '%Test log message%'")
        count = cursor.fetchone()[0]
        if count > 0:
            print("✅ Log message found in database")
        else:
            print("❌ Log message not found in database")
    except Exception as e:
        print(f"❌ Error checking logs: {e}")

if __name__ == "__main__":
    test_logging()
