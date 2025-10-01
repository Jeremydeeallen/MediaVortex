import sqlite3
from datetime import datetime, timedelta

def check_scan_logs():
    try:
        conn = sqlite3.connect('Data/MediaVortex.db')
        cursor = conn.cursor()
        
        # Check for recent scan errors
        cursor.execute("""
            SELECT Timestamp, LogLevel, Message, Component, FunctionName 
            FROM Logs 
            WHERE LogLevel IN ('ERROR', 'WARNING') 
            AND (Message LIKE '%scan%' OR Message LIKE '%StartScan%' OR Message LIKE '%FileScanning%')
            AND Timestamp > datetime('now', '-2 hours')
            ORDER BY Timestamp DESC 
            LIMIT 10
        """)
        
        rows = cursor.fetchall()
        
        if rows:
            print("=== Recent Scan Errors/Warnings ===")
            for row in rows:
                print(f"{row[0]} [{row[1]}] {row[3]}.{row[4]}: {row[2]}")
        else:
            print("No recent scan errors found.")
        
        # Check for all recent errors
        cursor.execute("""
            SELECT Timestamp, LogLevel, Message, Component, FunctionName 
            FROM Logs 
            WHERE LogLevel = 'ERROR'
            AND Timestamp > datetime('now', '-2 hours')
            ORDER BY Timestamp DESC 
            LIMIT 10
        """)
        
        rows = cursor.fetchall()
        
        if rows:
            print("\n=== All Recent Errors ===")
            for row in rows:
                print(f"{row[0]} [{row[1]}] {row[3]}.{row[4]}: {row[2]}")
        else:
            print("\nNo recent errors found.")
        
        conn.close()
        
    except Exception as e:
        print(f"Error checking logs: {e}")

if __name__ == "__main__":
    check_scan_logs()
