"""Add detail-metric columns to QualityTestResults.

Stores the richer per-VMAF-run statistics that libvmaf already produces
but we were throwing away after extracting the mean. With these stored,
operators can answer "where did this VMAF run actually struggle?" without
re-running, and the future CRF-recommendation feature can train on
distribution shape rather than means alone.

Columns added (all DOUBLE PRECISION NULL):
  - VMAFMin           pooled_metrics.min (lowest single-frame score)
  - VMAFMax           pooled_metrics.max (highest single-frame score)
  - VMAFHarmonicMean  pooled_metrics.harmonic_mean (penalizes outliers)
  - VMAFStdDev        computed from per-frame scores
  - VMAFP1            1st percentile (worst 1% of frames)
  - VMAFP5            5th percentile
  - VMAFP10           10th percentile
  - VMAFP25           25th percentile

Idempotent: ADD COLUMN IF NOT EXISTS per column.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from Core.Database.DatabaseService import DatabaseService


COLUMNS = [
    ('VMAFMin', 'DOUBLE PRECISION'),
    ('VMAFMax', 'DOUBLE PRECISION'),
    ('VMAFHarmonicMean', 'DOUBLE PRECISION'),
    ('VMAFStdDev', 'DOUBLE PRECISION'),
    ('VMAFP1', 'DOUBLE PRECISION'),
    ('VMAFP5', 'DOUBLE PRECISION'),
    ('VMAFP10', 'DOUBLE PRECISION'),
    ('VMAFP25', 'DOUBLE PRECISION'),
]


def Main():
    Db = DatabaseService()
    for Name, Type_ in COLUMNS:
        Sql = f'ALTER TABLE QualityTestResults ADD COLUMN IF NOT EXISTS {Name} {Type_}'
        print(f"  {Sql}")
        Db.ExecuteNonQuery(Sql)
    print()
    print("Done. Verifying schema...")
    Rows = Db.ExecuteQuery(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'qualitytestresults' AND column_name ILIKE 'vmaf%'
        ORDER BY column_name
        """
    )
    for R in Rows:
        print(f"  {R['column_name']:25} {R['data_type']}")


if __name__ == "__main__":
    Main()
