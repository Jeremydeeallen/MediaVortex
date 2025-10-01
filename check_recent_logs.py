import sqlite3
from datetime import datetime, timedelta

def check_recent_logs():
    try:
        conn = sqlite3.connect('Data/MediaVortex.db')
        cursor = conn.cursor()
        
        # Check for all recent logs (last 30 minutes)
        cursor.execute("""
            SELECT Timestamp, LogLevel, Message, Component, FunctionName 
            FROM Logs 
            WHERE Timestamp > datetime('now', '-30 minutes')
            ORDER BY Timestamp DESC 
            LIMIT 20
        """)
        
        rows = cursor.fetchall()
        
        if rows:
            print("=== Recent Logs (Last 30 minutes) ===")
            for row in rows:
                print(f"{row[0]} [{row[1]}] {row[3]}.{row[4]}: {row[2]}")
        else:
            print("No recent logs found.")
        
        # Check for FileScanningController logs specifically
        cursor.execute("""
            SELECT Timestamp, LogLevel, Message, Component, FunctionName 
            FROM Logs 
            WHERE Component = 'FileScanningController'
            AND Timestamp > datetime('now', '-1 hour')
            ORDER BY Timestamp DESC 
            LIMIT 10
        """)
        
        rows = cursor.fetchall()
        
        if rows:
            print("\n=== FileScanningController Logs (Last hour) ===")
            for row in rows:
                print(f"{row[0]} [{row[1]}] {row[3]}.{row[4]}: {row[2]}")
        else:
            print("\nNo FileScanningController logs found.")
        
        conn.close()
        
    except Exception as e:
        print(f"Error checking logs: {e}")

if __name__ == "__main__":
    check_recent_logs()
