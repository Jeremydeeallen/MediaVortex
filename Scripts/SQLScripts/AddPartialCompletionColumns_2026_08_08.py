# directive: partial-pipeline-completion
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: partial-pipeline-completion
def RunMigration():
    Db = DatabaseService()
    Conn = Db.GetConnection()
    Cur = Conn.cursor()
    try:
        Cur.execute(
            "ALTER TABLE TranscodeQueue "
            "ADD COLUMN IF NOT EXISTS AudioSlotOverride TEXT NULL"
        )
        print("Added TranscodeQueue.AudioSlotOverride (nullable, values NULL or 'Copy').")

        Cur.execute(
            "ALTER TABLE TranscodeQueue "
            "ADD COLUMN IF NOT EXISTS ParentTranscodeAttemptId BIGINT NULL "
            "REFERENCES TranscodeAttempts(Id) ON DELETE SET NULL"
        )
        print("Added TranscodeQueue.ParentTranscodeAttemptId (nullable FK to TranscodeAttempts).")

        Cur.execute(
            "ALTER TABLE TranscodeQueue "
            "DROP CONSTRAINT IF EXISTS transcodequeue_audioslotoverride_check"
        )
        Cur.execute(
            "ALTER TABLE TranscodeQueue "
            "ADD CONSTRAINT transcodequeue_audioslotoverride_check "
            "CHECK (AudioSlotOverride IS NULL OR AudioSlotOverride = 'Copy')"
        )
        print("Added CHECK constraint on AudioSlotOverride (NULL or 'Copy').")

        Cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_transcodequeue_parent_attempt "
            "ON TranscodeQueue (ParentTranscodeAttemptId) "
            "WHERE ParentTranscodeAttemptId IS NOT NULL"
        )
        print("Created partial index on ParentTranscodeAttemptId (populated rows only).")

        Conn.commit()
        print("Migration committed.")

        Cur.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'transcodequeue' "
            "  AND column_name IN ('audioslotoverride', 'parenttranscodeattemptid') "
            "ORDER BY column_name"
        )
        for Row in Cur.fetchall():
            print(f"  verified: {Row[0]} {Row[1]} nullable={Row[2]}")
    except Exception:
        Conn.rollback()
        raise
    finally:
        Cur.close()
        Db.CloseConnection(Conn)


if __name__ == '__main__':
    RunMigration()
