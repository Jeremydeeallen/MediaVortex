# directive: label-decides-command | # see transcode.ST6
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


RETIRED_MODES = ('Quick', 'SubtitleFix')


# directive: label-decides-command | # see transcode.ST6
def Run():
    Db = DatabaseService()
    InUse = Db.ExecuteQuery(
        "SELECT ProcessingMode, COUNT(*) AS N FROM TranscodeQueue WHERE ProcessingMode = ANY(%s) GROUP BY ProcessingMode",
        (list(RETIRED_MODES),),
    )
    if InUse:
        print(f"REFUSED: queue rows still carry a retired label: {[dict(R) for R in InUse]}")
        return 1
    Deleted = Db.ExecuteNonQuery(
        "DELETE FROM ProcessingModes WHERE Name = ANY(%s)",
        (list(RETIRED_MODES),),
    )
    print(f"Deleted {Deleted} ProcessingModes row(s).")
    for R in Db.ExecuteQuery("SELECT Name FROM ProcessingModes ORDER BY Name"):
        print(f"  {R.get('Name')}")
    return 0


if __name__ == '__main__':
    raise SystemExit(Run())
