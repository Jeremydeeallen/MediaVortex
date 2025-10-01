import sqlite3
from datetime import datetime, timedelta

def check_file_scan_logs():
    try:
        conn = sqlite3.connect('Data/MediaVortex.db')
        cursor = conn.cursor()
        
        # Check for recent FileScanning logs
        cursor.execute("""
            SELECT Timestamp, LogLevel, Message, Component, FunctionName 
            FROM Logs 
            WHERE Component LIKE '%FileScanning%'
            AND Timestamp > datetime('now', '-1 hour')
            ORDER BY Timestamp DESC 
            LIMIT 10
        """)
        
        rows = cursor.fetchall()
        
        if rows:
            print("=== Recent FileScanning Logs (Last hour) ===")
            for row in rows:
                print(f"{row[0]} [{row[1]}] {row[3]}.{row[4]}: {row[2]}")
        else:
            print("No recent FileScanning logs found.")
        
        # Check for MediaVortex logs
        cursor.execute("""
            SELECT Timestamp, LogLevel, Message, Component, FunctionName 
            FROM Logs 
            WHERE Component = 'MediaVortexApp'
            ORDER BY Timestamp DESC 
            LIMIT 5
        """)
        
        rows = cursor.fetchall()
        
        if rows:
            print("=== Recent MediaVortex Logs ===")
            for row in rows:
                print(f"{row[0]} [{row[1]}] {row[3]}.{row[4]}: {row[2]}")
        else:
            print("No MediaVortex logs found.")
        
        # Check for all recent logs
        cursor.execute("""
            SELECT Timestamp, LogLevel, Message, Component, FunctionName 
            FROM Logs 
            WHERE Timestamp > datetime('now', '-1 hour')
            ORDER BY Timestamp DESC 
            LIMIT 10
        """)
        
        rows = cursor.fetchall()
        
        if rows:
            print("\n=== All Recent Logs (Last hour) ===")
            for row in rows:
                print(f"{row[0]} [{row[1]}] {row[3]}.{row[4]}: {row[2]}")
        else:
            print("\nNo recent logs found at all.")
        
        conn.close()
        
    except Exception as e:
        print(f"Error checking logs: {e}")

if __name__ == "__main__":
    check_file_scan_logs()
