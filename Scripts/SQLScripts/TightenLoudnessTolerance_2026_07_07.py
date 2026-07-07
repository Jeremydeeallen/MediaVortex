# directive: transcode-flow-canonical
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# from: Docs/Codecs/4K-AV1-Streaming-Sweep-2026-07-06.md
NewTolerance = 3.0


# directive: transcode-flow-canonical
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE AudioNormalizationConfig ALTER COLUMN LoudnessTolerance SET DEFAULT %s",
        (NewTolerance,),
    )
    print(f"Schema DEFAULT updated to {NewTolerance}")
    Db.ExecuteNonQuery(
        "UPDATE AudioNormalizationConfig SET LoudnessTolerance = %s WHERE LoudnessTolerance > %s",
        (NewTolerance, NewTolerance),
    )
    Rows = Db.ExecuteQuery(
        "SELECT Scope, ScopeKey, LoudnessTolerance FROM AudioNormalizationConfig ORDER BY Scope, ScopeKey"
    )
    for R in Rows:
        print(f"Scope={R['scope']} Key={R['scopekey']} LoudnessTolerance={R['loudnesstolerance']}")
    print("Done.")


if __name__ == '__main__':
    Main()
