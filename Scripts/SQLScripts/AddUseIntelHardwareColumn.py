# Adds Profiles.useintelhardware bigint (parallel to usenvidiahardware) + CHECK mutex. Idempotent.
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


def Main():
    Db = DatabaseService()
    print("Step 1/3: ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS useintelhardware bigint DEFAULT 0")
    Db.ExecuteNonQuery(
        "ALTER TABLE Profiles ADD COLUMN IF NOT EXISTS useintelhardware bigint DEFAULT 0"
    )

    print("Step 2/3: Pre-validate no row has both flags set")
    Conflicts = Db.ExecuteQuery(
        "SELECT count(*) AS n FROM Profiles "
        "WHERE COALESCE(usenvidiahardware,0) + COALESCE(useintelhardware,0) > 1"
    )
    if Conflicts and Conflicts[0].get('n', 0) > 0:
        print(f"  ABORT -- {Conflicts[0]['n']} rows already violate mutex. Investigate before constraint add.")
        sys.exit(2)
    print("  OK -- 0 conflicts.")

    print("Step 3/3: Add CHECK constraint chk_profile_single_hw_encoder (idempotent)")
    Has = Db.ExecuteQuery(
        "SELECT count(*) AS n FROM pg_constraint "
        "WHERE conname = 'chk_profile_single_hw_encoder'"
    )
    if Has and Has[0].get('n') == 1:
        print("  SKIP -- constraint already present.")
    else:
        Db.ExecuteNonQuery(
            "ALTER TABLE Profiles ADD CONSTRAINT chk_profile_single_hw_encoder "
            "CHECK (COALESCE(usenvidiahardware,0) + COALESCE(useintelhardware,0) <= 1)"
        )
        print("  OK -- constraint added.")


if __name__ == "__main__":
    Main()
