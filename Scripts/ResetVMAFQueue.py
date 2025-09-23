import sqlite3

def ResetVMAFQueue():
    """Reset VMAFQueue item back to Pending status."""
    conn = sqlite3.connect('Data/MediaVortex.db')
    cursor = conn.cursor()
    
    try:
        # Reset VMAFQueue item to Pending
        cursor.execute("""
            UPDATE VMAFQueue 
            SET Status = 'Pending', 
                DateStarted = NULL, 
                DateCompleted = NULL, 
                ErrorMessage = NULL, 
                RetryCount = 0
            WHERE Id = 3
        """)
        
        # Delete VMAFProgress record
        cursor.execute("DELETE FROM VMAFProgress WHERE VMAFQueueId = 3")
        
        conn.commit()
        print("✅ VMAFQueue and VMAFProgress reset successfully")
        
        # Verify the reset
        cursor.execute("SELECT Status FROM VMAFQueue WHERE Id = 3")
        row = cursor.fetchone()
        print(f"VMAFQueue Status: {row[0] if row else 'Not found'}")
        
        cursor.execute("SELECT COUNT(*) FROM VMAFProgress WHERE VMAFQueueId = 3")
        count = cursor.fetchone()[0]
        print(f"VMAFProgress records: {count}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    ResetVMAFQueue()
