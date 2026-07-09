# directive: transcode-flow-canonical | # see transcode-flow-canonical.C25
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


REMAP = {
    'NVENC AV1 P7 HQ CQ29 G480 ANIME -720p': 'AV1 Tier 2 Good',
    'NVENC AV1 P7 VBR 30pct -720p': 'AV1 Tier 1 Efficient',
    'NVENC AV1 P7 UHQ CQ32 -720p': 'AV1 Tier 3 Better',
    'NVENC AV1 P7 UHQ CQ32 -480p': 'AV1 Tier 2 Good',
}


# directive: transcode-flow-canonical
def Main():
    Db = DatabaseService()
    for Old, New in REMAP.items():
        Affected = Db.ExecuteNonQuery(
            "UPDATE ContentClassificationRules SET AssignProfileName = %s WHERE AssignProfileName = %s",
            (New, Old),
        )
        print(f"  {Old!r} -> {New!r}: {Affected} rule(s) remapped")
    print("\nPost-remap state:")
    Rows = Db.ExecuteQuery(
        "SELECT Priority, RuleName, AssignProfileName, IsActive FROM ContentClassificationRules ORDER BY Priority"
    )
    for R in Rows:
        print(f"  P={R['Priority']} {R['RuleName']:<24} -> {R['AssignProfileName']!r} (Active={R['IsActive']})")


if __name__ == '__main__':
    Main()
