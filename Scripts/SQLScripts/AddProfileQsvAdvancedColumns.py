# Adds QSV-specific knobs: lowpower on Profiles; rest on profilethresholds. Idempotent.
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


PROFILES_COLUMNS = [
    ("lowpower", "int"),
]

THRESHOLDS_COLUMNS = [
    ("qsvextbrc",         "int"),
    ("qsvadaptivei",      "int"),
    ("qsvadaptiveb",      "int"),
    ("qsvlookaheaddepth", "int"),
    ("qsvbstrategy",      "int"),
    ("qsvtilecols",       "int"),
    ("qsvtilerows",       "int"),
]


def AddColumns(Db, Table, Columns):
    for ColName, ColType in Columns:
        print(f"ALTER TABLE {Table} ADD COLUMN IF NOT EXISTS {ColName} {ColType}")
        Db.ExecuteNonQuery(
            f"ALTER TABLE {Table} ADD COLUMN IF NOT EXISTS {ColName} {ColType}"
        )


def Main():
    Db = DatabaseService()
    print("=== Profiles columns ===")
    AddColumns(Db, "Profiles", PROFILES_COLUMNS)
    print("=== profilethresholds columns ===")
    AddColumns(Db, "profilethresholds", THRESHOLDS_COLUMNS)

    # Verify
    AllExpected = [N for N, _ in PROFILES_COLUMNS] + [N for N, _ in THRESHOLDS_COLUMNS]
    Check = Db.ExecuteQuery(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE (table_name='profiles' AND column_name IN ('lowpower')) "
        "OR (table_name='profilethresholds' AND column_name IN "
        "('qsvextbrc','qsvadaptivei','qsvadaptiveb','qsvlookaheaddepth','qsvbstrategy','qsvtilecols','qsvtilerows'))"
    )
    Got = sorted([R['column_name'] for R in Check])
    Want = sorted(AllExpected)
    if Got == Want:
        print(f"  OK -- {len(Got)} columns present.")
    else:
        print(f"  ERROR -- expected {Want}, got {Got}")
        sys.exit(1)


if __name__ == "__main__":
    Main()
