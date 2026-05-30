"""Add operator-visible detail columns to QualityTestingQueue + QualityTestProgress.

Idempotent. Closes the UI gap where workers / size / numeric fps / numeric eta
were not persisted for VMAF runs (only embedded in free-text fields).

Adds:
- QualityTestingQueue.ClaimedBy TEXT NULL
    Worker that claimed the row. Written by ClaimQualityTestJob.
- QualityTestProgress.CurrentFps DOUBLE PRECISION NULL
- QualityTestProgress.AverageFps DOUBLE PRECISION NULL
- QualityTestProgress.EtaSeconds DOUBLE PRECISION NULL
    Numeric variants of the values that currently live embedded in
    `currentstep` / `eta` text fields.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


def Main():
    Db = DatabaseService()
    print("[1/2] Adding QualityTestingQueue.ClaimedBy...")
    Db.ExecuteNonQuery("ALTER TABLE QualityTestingQueue ADD COLUMN IF NOT EXISTS ClaimedBy TEXT NULL")

    print("[2/2] Adding QualityTestProgress.CurrentFps, AverageFps, EtaSeconds...")
    Db.ExecuteNonQuery("ALTER TABLE QualityTestProgress ADD COLUMN IF NOT EXISTS CurrentFps DOUBLE PRECISION NULL")
    Db.ExecuteNonQuery("ALTER TABLE QualityTestProgress ADD COLUMN IF NOT EXISTS AverageFps DOUBLE PRECISION NULL")
    Db.ExecuteNonQuery("ALTER TABLE QualityTestProgress ADD COLUMN IF NOT EXISTS EtaSeconds DOUBLE PRECISION NULL")

    print("Done.")


if __name__ == "__main__":
    Main()
