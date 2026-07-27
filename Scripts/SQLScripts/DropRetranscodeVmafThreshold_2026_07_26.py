# directive: verify-signal-cleanup | # see DOMAIN.md 2026-07-26 Vmaf-truthful rule
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: verify-signal-cleanup
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE PostTranscodeGateConfig DROP COLUMN IF EXISTS RetranscodeVmafThreshold"
    )
    Cols = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'posttranscodegateconfig' AND column_name = 'retranscodevmafthreshold'"
    )
    if Cols:
        print("FAIL: RetranscodeVmafThreshold still present")
    else:
        print("Applied. PostTranscodeGateConfig.RetranscodeVmafThreshold dropped.")


if __name__ == '__main__':
    Main()
