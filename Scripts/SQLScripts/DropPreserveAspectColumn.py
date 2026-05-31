# Idempotent: ALTER TABLE ProfileThresholds DROP COLUMN preserveaspect (unread after width-anchored scale-filter refactor).
import argparse
import sys

sys.path.insert(0, '.')
from Core.Database.DatabaseService import DatabaseService


def Main() -> int:
    Parser = argparse.ArgumentParser(
        description="Drop vestigial ProfileThresholds.preserveaspect column. Dry-run by default."
    )
    Parser.add_argument("--execute", action="store_true", help="Apply the DROP COLUMN.")
    Args = Parser.parse_args()

    Db = DatabaseService()

    Rows = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'profilethresholds' AND column_name = 'preserveaspect'"
    )
    if not Rows:
        print("preserveaspect not found on ProfileThresholds -- already dropped. Nothing to do.")
        return 0

    print("Found: ProfileThresholds.preserveaspect (BOOLEAN, unread by current code).")

    if not Args.execute:
        print("DRY-RUN: re-run with --execute to drop.")
        return 0

    Db.ExecuteNonQuery("ALTER TABLE ProfileThresholds DROP COLUMN preserveaspect")
    print("Dropped ProfileThresholds.preserveaspect.")

    Verify = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'profilethresholds' AND column_name = 'preserveaspect'"
    )
    if Verify:
        print("ERROR: column still present after DROP.")
        return 1
    print("Verified absent. Done.")
    return 0


if __name__ == "__main__":
    sys.exit(Main())
