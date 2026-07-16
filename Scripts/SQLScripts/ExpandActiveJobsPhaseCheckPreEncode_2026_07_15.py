import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-flow-canonical
def RunMigration():
    Db = DatabaseService()
    Existing = Db.ExecuteQuery(
        "SELECT pg_get_constraintdef(oid) AS def FROM pg_constraint WHERE conname = %s",
        ('activejobs_phase_enum',),
    )
    if Existing and "'PreEncode'" in Existing[0]['def']:
        print("activejobs_phase_enum already includes PreEncode -- skipping")
        return
    print("Dropping stale activejobs_phase_enum...")
    Db.ExecuteNonQuery("ALTER TABLE ActiveJobs DROP CONSTRAINT IF EXISTS activejobs_phase_enum", ())
    print("Re-adding activejobs_phase_enum with PreEncode...")
    Db.ExecuteNonQuery(
        "ALTER TABLE ActiveJobs ADD CONSTRAINT activejobs_phase_enum "
        "CHECK (Phase IS NULL OR Phase IN ('Setup','PreEncode','Encoding','PostEncode','Verifying'))",
        (),
    )
    print("Done.")


if __name__ == '__main__':
    RunMigration()
