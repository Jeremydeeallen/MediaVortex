import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


DEAD_COLUMNS = [
    'bpptranscodethreshold',
    'minsizembperminutetotranscode',
    'minsourcebpp_deprecated_2026_06_29',
    'maxsourcebpp_deprecated_2026_06_29',
    'estimatedsavingsmbthreshold',
    'preventupscale',
    'resolutionexceedsprofiletarget',
]


def Main():
    Db = DatabaseService()
    Existing = {(R.get('column_name') or R.get('COLUMN_NAME')).lower() for R in Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns WHERE table_name='videocompliancerules'"
    )}
    Dropped = []
    for Col in DEAD_COLUMNS:
        if Col in Existing:
            Db.ExecuteNonQuery(f'ALTER TABLE videocompliancerules DROP COLUMN IF EXISTS {Col}')
            Dropped.append(Col)
    print(f"Dropped {len(Dropped)} columns: {Dropped}")
    Remaining = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns WHERE table_name='videocompliancerules' ORDER BY ordinal_position"
    )
    print("Remaining columns:")
    for R in Remaining:
        print(f"  {R.get('column_name') or R.get('COLUMN_NAME')}")


if __name__ == '__main__':
    Main()
