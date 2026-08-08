import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: mediavortex-output-terminal -- WorkBucket short-circuits TranscodedByMediaVortex=TRUE to Compliant per transcode.flow.md D7 (our outputs are terminal; re-encoding compounds artifacts and cannot start from a deleted source)
GENERATED_EXPR_SQL = (
    "ALTER TABLE MediaFiles ADD COLUMN WorkBucket TEXT GENERATED ALWAYS AS ("
    "CASE "
    "WHEN TranscodedByMediaVortex = TRUE THEN 'Compliant' "
    "WHEN VideoCompliant IS NULL OR ContainerCompliant IS NULL OR AudioCompliant IS NULL THEN 'Unclassified' "
    "WHEN VideoCompliant AND ContainerCompliant AND AudioCompliant THEN 'Compliant' "
    "WHEN NOT VideoCompliant THEN 'Transcode' "
    "WHEN NOT ContainerCompliant THEN 'Remux' "
    "ELSE 'AudioFix' "
    "END"
    ") STORED"
)


def Run():
    DB = DatabaseService()

    Existing = DB.ExecuteQuery(
        "SELECT column_name, generation_expression FROM information_schema.columns "
        "WHERE table_name = 'mediafiles' AND column_name = 'workbucket'"
    )
    if Existing:
        print(f"WorkBucket current expr: {Existing[0].get('generation_expression')!r}")
        DB.ExecuteNonQuery("ALTER TABLE MediaFiles DROP COLUMN WorkBucket")

    DB.ExecuteNonQuery(GENERATED_EXPR_SQL)

    Verify = DB.ExecuteQuery(
        "SELECT generation_expression FROM information_schema.columns "
        "WHERE table_name = 'mediafiles' AND column_name = 'workbucket'"
    )
    print(f"WorkBucket new expr: {Verify[0].get('generation_expression')!r}")

    StaleCount = DB.ExecuteQuery(
        "SELECT COUNT(*) AS N FROM MediaFiles WHERE TranscodedByMediaVortex=TRUE AND WorkBucket != 'Compliant'"
    )
    print(f"MV outputs not in Compliant post-migration: {StaleCount[0].get('n', 0)}")

    Distribution = DB.ExecuteQuery(
        "SELECT WorkBucket, COUNT(*) AS n FROM MediaFiles GROUP BY WorkBucket ORDER BY n DESC"
    )
    print("Bucket distribution:")
    for R in Distribution:
        print(f"  {R.get('workbucket') or '<null>'}: {R['n']}")


if __name__ == '__main__':
    Run()
