import sqlite3

def ResetVMAFQueue():
    """Reset ALL running VMAFQueue items back to Pending status."""
    conn = sqlite3.connect('Data/MediaVortex.db')
    cursor = conn.cursor()
    
    try:
        # First, show what we're about to reset
        cursor.execute("""
            SELECT Id, Status, DateStarted, DateCompleted, ErrorMessage 
            FROM VMAFQueue 
            WHERE Status = 'Running' OR Status = 'Processing'
        """)
        running_jobs = cursor.fetchall()
        
        if not running_jobs:
            print("✅ No running VMAF jobs found - nothing to reset")
            return
        
        print(f"Found {len(running_jobs)} running VMAF job(s):")
        for job in running_jobs:
            print(f"  - ID: {job[0]}, Status: {job[1]}, Started: {job[2]}, Completed: {job[3]}, Error: {job[4]}")
        
        # Reset ALL running VMAFQueue items to Pending
        cursor.execute("""
            UPDATE VMAFQueue 
            SET Status = 'Pending', 
                DateStarted = NULL, 
                DateCompleted = NULL, 
                ErrorMessage = NULL, 
                RetryCount = 0
            WHERE Status = 'Running' OR Status = 'Processing'
        """)
        
        # Get the IDs of jobs we just reset
        cursor.execute("""
            SELECT Id FROM VMAFQueue 
            WHERE Status = 'Pending' AND DateStarted IS NULL
        """)
        reset_job_ids = [row[0] for row in cursor.fetchall()]
        
        # Delete VMAFProgress records for the reset jobs
        if reset_job_ids:
            placeholders = ','.join('?' for _ in reset_job_ids)
            cursor.execute(f"DELETE FROM VMAFProgress WHERE VMAFQueueId IN ({placeholders})", reset_job_ids)
        
        conn.commit()
        print(f"✅ Reset {len(reset_job_ids)} VMAF job(s) to Pending status")
        print("✅ Cleared associated VMAFProgress records")
        
        # Verify the reset
        cursor.execute("SELECT COUNT(*) FROM VMAFQueue WHERE Status = 'Pending'")
        pending_count = cursor.fetchone()[0]
        print(f"Total Pending VMAF jobs: {pending_count}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    ResetVMAFQueue()
