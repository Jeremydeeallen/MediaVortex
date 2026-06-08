import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: local-staging | # see local-staging.C1
def Run():
    DB = DatabaseService()
    DB.ExecuteNonQuery("ALTER TABLE Workers ADD COLUMN IF NOT EXISTS LocalScratchDir TEXT NULL")
    DB.ExecuteNonQuery("ALTER TABLE Workers ADD COLUMN IF NOT EXISTS LocalStagingEnabled BOOLEAN NOT NULL DEFAULT FALSE")
    DB.ExecuteNonQuery("ALTER TABLE Workers ADD COLUMN IF NOT EXISTS LocalVmafFirst BOOLEAN NOT NULL DEFAULT FALSE")
    DB.ExecuteNonQuery("ALTER TABLE TemporaryFilePaths ADD COLUMN IF NOT EXISTS LocalSourcePath TEXT NULL")
    DB.ExecuteNonQuery("ALTER TABLE TemporaryFilePaths ADD COLUMN IF NOT EXISTS LocalOutputPath TEXT NULL")
    CreateTableSql = (
        "CREATE TABLE IF NOT EXISTS LocalStagingConfig ("
        "Id INTEGER PRIMARY KEY DEFAULT 1, "
        "MinSizeMB INTEGER NOT NULL DEFAULT 500, "
        "LastUpdated TIMESTAMP DEFAULT NOW(), "
        "CHECK (Id = 1), "
        "CHECK (MinSizeMB > 0))"
    )
    DB.ExecuteNonQuery(CreateTableSql)
    DB.ExecuteNonQuery("INSERT INTO LocalStagingConfig (Id) VALUES (1) ON CONFLICT (Id) DO NOTHING")
    print("Added Workers.LocalScratchDir / LocalStagingEnabled / LocalVmafFirst (opt-in, default OFF)")
    print("Added TemporaryFilePaths.LocalSourcePath / LocalOutputPath")
    print("Created LocalStagingConfig (Id=1) with MinSizeMB=500 default; operator-tunable via /settings 'Local staging' card (C16)")


if __name__ == '__main__':
    Run()
