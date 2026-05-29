"""Add QualityTestingQueue Status + ForceDisposition + OverrideSetAt columns.

Idempotent. See Features/QualityTesting/qt-queue-visibility-and-override.feature.md.

Backfill rule (existing rows):
  - DateCompleted IS NOT NULL -> Status='Completed'
  - DateStarted   IS NOT NULL -> Status='Running'
  - else                      -> Status='Pending'
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


def Main():
    Db = DatabaseService()
    print("[1/3] Adding columns (idempotent)...")
    Db.ExecuteNonQuery(
        "ALTER TABLE QualityTestingQueue "
        "ADD COLUMN IF NOT EXISTS Status TEXT NOT NULL DEFAULT 'Pending'"
    )
    Db.ExecuteNonQuery(
        "ALTER TABLE QualityTestingQueue "
        "ADD COLUMN IF NOT EXISTS ForceDisposition TEXT NULL"
    )
    Db.ExecuteNonQuery(
        "ALTER TABLE QualityTestingQueue "
        "ADD COLUMN IF NOT EXISTS OverrideSetAt TIMESTAMP NULL"
    )

    print("[2/3] Applying CHECK constraints (idempotent)...")
    # CHECKs added via DO block so they are idempotent.
    Db.ExecuteNonQuery("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='qtq_status_check') THEN
                ALTER TABLE QualityTestingQueue
                ADD CONSTRAINT qtq_status_check
                CHECK (Status IN ('Pending','Running','Completed','Cancelled','Failed'));
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='qtq_forcedisp_check') THEN
                ALTER TABLE QualityTestingQueue
                ADD CONSTRAINT qtq_forcedisp_check
                CHECK (ForceDisposition IS NULL OR ForceDisposition IN ('Replace','Discard'));
            END IF;
        END$$;
    """)

    print("[3/3] Backfilling Status from DateStarted/DateCompleted (only rows still at default 'Pending')...")
    # Only update rows that haven't been touched (Status='Pending' is the default).
    Rows = Db.ExecuteNonQuery("""
        UPDATE QualityTestingQueue
        SET Status = CASE
            WHEN DateCompleted IS NOT NULL THEN 'Completed'
            WHEN DateStarted   IS NOT NULL THEN 'Running'
            ELSE 'Pending'
        END
        WHERE Status = 'Pending'
    """)
    print(f"       backfilled rows: {Rows}")
    print("Done. Verify with:")
    print("  py Scripts/SQLScripts/QueryDatabase.py sql \"SELECT Status, COUNT(*) FROM QualityTestingQueue GROUP BY Status\"")


if __name__ == "__main__":
    Main()
