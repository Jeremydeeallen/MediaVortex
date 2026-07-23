import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE VideoComplianceRules "
        "ADD COLUMN IF NOT EXISTS MinSizeMbPerMinuteToTranscode DOUBLE PRECISION NOT NULL DEFAULT 5.0"
    )
    Rows = Db.ExecuteQuery(
        "SELECT Id, MinSizeMbPerMinuteToTranscode FROM VideoComplianceRules ORDER BY Id"
    )
    print("Applied. VideoComplianceRules rows carrying MinSizeMbPerMinuteToTranscode:")
    for R in Rows:
        Rid = R.get('id')
        Val = R.get('minsizembperminutetotranscode')
        print(f"  Id={Rid}: {Val}")


if __name__ == '__main__':
    Main()
