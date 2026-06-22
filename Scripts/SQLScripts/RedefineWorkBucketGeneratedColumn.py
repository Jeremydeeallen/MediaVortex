import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-symmetry
GENERATED_EXPR_SQL = (
    "ALTER TABLE MediaFiles ADD COLUMN WorkBucket TEXT GENERATED ALWAYS AS ("
    "CASE "
    "WHEN VideoCompliant IS NULL OR ContainerCompliant IS NULL OR AudioCompliant IS NULL THEN NULL "
    "WHEN VideoCompliant = FALSE THEN 'Transcode' "
    "WHEN ContainerCompliant = FALSE THEN 'Remux' "
    "WHEN AudioCompliant = FALSE THEN 'AudioFixOnly' "
    "ELSE NULL "
    "END"
    ") STORED"
)


# directive: compliance-symmetry
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

    print("Creating WorkBucket generated column with NULL-aware CASE expression...")
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
        print("ERROR: WorkBucket missing after migration")


if __name__ == '__main__':
    Run()
