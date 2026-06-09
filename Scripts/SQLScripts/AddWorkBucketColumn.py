import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C7
def Run():
    DB = DatabaseService()

    DB.ExecuteNonQuery("ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS WorkBucket TEXT NULL")
    DB.ExecuteNonQuery("ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS OperationsNeededCsv TEXT NULL")
    DB.ExecuteNonQuery("ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS ComplianceGateBlocked TEXT NULL")
    DB.ExecuteNonQuery("ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS ComplianceEvaluatedAt TIMESTAMP NULL")
    DB.ExecuteNonQuery("ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS HasForcedSubtitles BOOLEAN NULL")

    Rows = DB.ExecuteQuery(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'mediafiles' "
        "AND column_name IN ('workbucket', 'operationsneededcsv', 'compliancegateblocked', 'complianceevaluatedat', 'hasforcedsubtitles') "
        "ORDER BY column_name"
    )
    print("MediaFiles columns present:")
    for Row in Rows:
        print("  " + Row['column_name'])


if __name__ == '__main__':
    Run()
