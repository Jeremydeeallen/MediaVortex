# Enforces codec column agrees with usenvidiahardware/useintelhardware flags. Pre-validates rows; aborts on conflict.
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


CHECK_NAME = "chk_codec_implies_hw_flag"

CHECK_EXPR = (
    "( "
    "  (codec = 'av1_nvenc' AND COALESCE(usenvidiahardware,0) = 1 AND COALESCE(useintelhardware,0) = 0) "
    "  OR (codec = 'av1_qsv' AND COALESCE(useintelhardware,0) = 1 AND COALESCE(usenvidiahardware,0) = 0) "
    "  OR (codec NOT IN ('av1_nvenc','av1_qsv') AND COALESCE(usenvidiahardware,0) = 0 AND COALESCE(useintelhardware,0) = 0) "
    ")"
)


def Main():
    Db = DatabaseService()
    print("Step 1/2: Pre-validate every Profiles row agrees codec <-> hw flag")
    Conflicts = Db.ExecuteQuery(
        "SELECT id, profilename, codec, "
        "COALESCE(usenvidiahardware,0) AS nv, COALESCE(useintelhardware,0) AS intel "
        "FROM Profiles "
        f"WHERE NOT {CHECK_EXPR}"
    )
    if Conflicts:
        print(f"  ABORT -- {len(Conflicts)} rows violate codec<->hw-flag invariant:")
        for R in Conflicts[:20]:
            print(f"    id={R['id']} name='{R['profilename']}' codec='{R['codec']}' nv={R['nv']} intel={R['intel']}")
        sys.exit(2)
    print("  OK -- all rows consistent.")

    print(f"Step 2/2: Add CHECK constraint {CHECK_NAME} (idempotent)")
    Has = Db.ExecuteQuery(
        "SELECT count(*) AS n FROM pg_constraint WHERE conname = %s",
        (CHECK_NAME,)
    )
    if Has and Has[0].get('n') == 1:
        print("  SKIP -- constraint already present.")
    else:
        Db.ExecuteNonQuery(
            f"ALTER TABLE Profiles ADD CONSTRAINT {CHECK_NAME} CHECK {CHECK_EXPR}"
        )
        print("  OK -- constraint added.")


if __name__ == "__main__":
    Main()
