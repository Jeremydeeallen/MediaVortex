import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-flow-canonical
def ColumnExists(Db, TableName, ColumnName):
    Rows = Db.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (TableName.lower(), ColumnName.lower()),
    )
    return bool(Rows)


# directive: transcode-flow-canonical
def ConstraintExists(Db, TableName, ConstraintName):
    Rows = Db.ExecuteQuery(
        "SELECT constraint_name FROM information_schema.table_constraints "
        "WHERE table_name = %s AND constraint_name = %s",
        (TableName.lower(), ConstraintName.lower()),
    )
    return bool(Rows)


# directive: transcode-flow-canonical
def RunMigration():
    Db = DatabaseService()

    if ColumnExists(Db, 'ActiveJobs', 'Phase'):
        print("ActiveJobs.Phase already exists -- skipping ADD COLUMN Phase")
    else:
        print("Adding ActiveJobs.Phase TEXT (nullable)...")
        Db.ExecuteNonQuery("ALTER TABLE ActiveJobs ADD COLUMN Phase TEXT", ())

    if ColumnExists(Db, 'ActiveJobs', 'PhaseTransitionedAt'):
        print("ActiveJobs.PhaseTransitionedAt already exists -- skipping ADD COLUMN PhaseTransitionedAt")
    else:
        print("Adding ActiveJobs.PhaseTransitionedAt TIMESTAMP (nullable)...")
        Db.ExecuteNonQuery("ALTER TABLE ActiveJobs ADD COLUMN PhaseTransitionedAt TIMESTAMP", ())

    print("Backfilling Running rows with Phase='Encoding' + PhaseTransitionedAt=NOW() where Phase IS NULL...")
    Backfilled = Db.ExecuteNonQuery(
        "UPDATE ActiveJobs SET Phase = 'Encoding', PhaseTransitionedAt = NOW() "
        "WHERE Status = 'Running' AND Phase IS NULL",
        (),
    )
    print(f"  backfilled rows: {Backfilled}")

    if ConstraintExists(Db, 'ActiveJobs', 'activejobs_phase_enum'):
        print("CHECK constraint activejobs_phase_enum already exists.")
    else:
        Db.ExecuteNonQuery(
            "ALTER TABLE ActiveJobs ADD CONSTRAINT activejobs_phase_enum "
            "CHECK (Phase IS NULL OR Phase IN ('Setup','Encoding','PostEncode','Verifying'))",
            (),
        )
        print("Added CHECK constraint activejobs_phase_enum.")


if __name__ == '__main__':
    RunMigration()
