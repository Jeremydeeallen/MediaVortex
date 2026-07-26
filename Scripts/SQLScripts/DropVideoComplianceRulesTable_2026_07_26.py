# directive: video-compliance-multiplier | # see video-encoding.C2
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: video-compliance-multiplier
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery("DROP TABLE IF EXISTS VideoComplianceRules")
    Rows = Db.ExecuteQuery(
        "SELECT tablename FROM pg_tables WHERE tablename = 'videocompliancerules'"
    )
    if Rows:
        print("FAIL: videocompliancerules still exists")
    else:
        print("Applied. VideoComplianceRules table dropped (codec allowlist retired).")


if __name__ == '__main__':
    Main()
