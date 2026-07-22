import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-flow-canonical -- C33 5-branch WorkBucket including Compliant + Unclassified
GENERATED_EXPR_SQL = (
    "ALTER TABLE MediaFiles ADD COLUMN WorkBucket TEXT GENERATED ALWAYS AS ("
    "CASE "
    "WHEN VideoCompliant IS NULL OR ContainerCompliant IS NULL OR AudioCompliant IS NULL THEN 'Unclassified' "
    "WHEN VideoCompliant AND ContainerCompliant AND AudioCompliant THEN 'Compliant' "
    "WHEN NOT VideoCompliant THEN 'Transcode' "
    "WHEN NOT ContainerCompliant THEN 'Remux' "
    "ELSE 'AudioFix' "
    "END"
    ") STORED"
)


# directive: transcode-flow-canonical -- C33
def Run():
    DB = DatabaseService()

    Existing = DB.ExecuteQuery(
        "SELECT column_name, is_generated, generation_expression "
        "FROM information_schema.columns "
        "WHERE table_name = 'mediafiles' AND column_name = 'workbucket'"
    )
    if Existing:
        print(f"WorkBucket current state: is_generated={Existing[0]['is_generated']} expr={Existing[0]['generation_expression']!r}")
        print("Dropping existing WorkBucket column to redefine...")
        DB.ExecuteNonQuery("ALTER TABLE MediaFiles DROP COLUMN WorkBucket")
    else:
        print("WorkBucket column not present; will add fresh.")

    print("Creating WorkBucket generated column with C33 5-branch expression...")
    DB.ExecuteNonQuery(GENERATED_EXPR_SQL)

    Verify = DB.ExecuteQuery(
        "SELECT column_name, is_generated, generation_expression "
        "FROM information_schema.columns "
        "WHERE table_name = 'mediafiles' AND column_name = 'workbucket'"
    )
    if Verify:
        print(f"WorkBucket post-migration: is_generated={Verify[0]['is_generated']}")
        print(f"Expression: {Verify[0]['generation_expression']}")
    else:
        raise RuntimeError("WorkBucket missing after migration")

    Distribution = DB.ExecuteQuery(
        "SELECT WorkBucket, COUNT(*) AS n FROM MediaFiles GROUP BY WorkBucket ORDER BY n DESC"
    )
    print("\nPost-migration bucket distribution:")
    for R in Distribution:
        print(f"  {R.get('workbucket') or '<null>'}: {R['n']}")


if __name__ == '__main__':
    Run()
