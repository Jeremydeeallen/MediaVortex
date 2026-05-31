# Idempotent: DELETE SystemSettings WHERE settingkey='TranscodeOutputMode' (vestigial; see TranscodeJob.feature.md).
import argparse
import sys

sys.path.insert(0, '.')
from Core.Database.DatabaseService import DatabaseService


def Main() -> int:
    Parser = argparse.ArgumentParser(
        description="Remove vestigial TranscodeOutputMode SystemSettings row. Dry-run by default."
    )
    Parser.add_argument("--execute", action="store_true", help="Apply the DELETE.")
    Args = Parser.parse_args()

    Db = DatabaseService()

    Rows = Db.ExecuteQuery(
        "SELECT Id, settingkey, settingvalue FROM SystemSettings WHERE settingkey = 'TranscodeOutputMode'"
    )
    if not Rows:
        print("TranscodeOutputMode not found -- already removed. Nothing to do.")
        return 0

    Row = Rows[0]
    print(f"Found: Id={Row['Id']}  key='{Row['settingkey']}'  value='{Row['settingvalue']}'")

    if not Args.execute:
        print("DRY-RUN: re-run with --execute to delete.")
        return 0

    Db.ExecuteNonQuery("DELETE FROM SystemSettings WHERE settingkey = 'TranscodeOutputMode'")
    print("Deleted TranscodeOutputMode.")

    if Db.ExecuteQuery("SELECT Id FROM SystemSettings WHERE settingkey = 'TranscodeOutputMode'"):
        print("ERROR: row still present after DELETE.")
        return 1
    print("Verified absent. Done.")
    return 0


if __name__ == "__main__":
    sys.exit(Main())
