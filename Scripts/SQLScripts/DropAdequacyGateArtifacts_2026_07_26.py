# directive: video-compliance-multiplier | # see video-encoding.C3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: video-compliance-multiplier
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "DELETE FROM SystemSettings WHERE SettingKey IN ('AdequacyGateEnabled', 'AdequacyGateMarginPercent')"
    )
    Db.ExecuteNonQuery("ALTER TABLE MediaFiles DROP COLUMN IF EXISTS AdequacyDecision")
    Db.ExecuteNonQuery("ALTER TABLE MediaFiles DROP COLUMN IF EXISTS AdequacyDecisionAt")
    RemainingRows = Db.ExecuteQuery(
        "SELECT SettingKey FROM SystemSettings WHERE SettingKey LIKE 'AdequacyGate%'"
    )
    RemainingCols = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'mediafiles' AND column_name LIKE 'adequacydecision%'"
    )
    if RemainingRows or RemainingCols:
        print(f"FAIL: rows={RemainingRows} cols={RemainingCols}")
    else:
        print("Applied. AdequacyGate artifacts dropped (SystemSettings + MediaFiles columns).")


if __name__ == '__main__':
    Main()
