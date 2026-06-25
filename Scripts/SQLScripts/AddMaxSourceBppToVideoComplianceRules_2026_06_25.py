import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# from: .claude/directive.md
MAX_SOURCE_BPP_DEFAULT = 0.20


# directive: worker-runtime-state
def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "ALTER TABLE VideoComplianceRules ADD COLUMN IF NOT EXISTS MaxSourceBpp NUMERIC NOT NULL DEFAULT %s",
        (MAX_SOURCE_BPP_DEFAULT,),
    )
    print('VideoComplianceRules.MaxSourceBpp ensured (default 0.20).')
    print('Rollback:')
    print("  ALTER TABLE VideoComplianceRules DROP COLUMN IF EXISTS MaxSourceBpp;")
    return 0


if __name__ == '__main__':
    raise SystemExit(Main())
