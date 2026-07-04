import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from Core.Database.DatabaseService import DatabaseService


# directive: transcode-flow-canonical | # see transcode.ST7
def AddSamplesJson(Db: DatabaseService) -> None:
    Rows = Db.ExecuteQuery(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'vmafconfidencestats' AND column_name = 'samplesjson'"
    )
    if Rows:
        print("SamplesJson already present")
        return
    print("Adding VmafConfidenceStats.SamplesJson (jsonb, DEFAULT '[]')")
    Db.ExecuteNonQuery(
        "ALTER TABLE VmafConfidenceStats ADD COLUMN SamplesJson JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


# directive: transcode-flow-canonical | # see transcode.ST7
def RunMigration() -> None:
    Db = DatabaseService()
    AddSamplesJson(Db)


if __name__ == '__main__':
    RunMigration()
