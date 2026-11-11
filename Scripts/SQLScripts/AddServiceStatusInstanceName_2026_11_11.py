# directive: farm-server
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


# directive: farm-server | # see single-instance-startup.C7 -- the deploy-assigned instance that owns a ServiceStatus row; NULL = owned before instance tracking
def Run():
    Db = DatabaseService()
    Db.ExecuteNonQuery("ALTER TABLE ServiceStatus ADD COLUMN IF NOT EXISTS InstanceName TEXT NULL")
    for R in Db.ExecuteQuery("SELECT ServiceName, InstanceName, ProcessId, UpdatedAt FROM ServiceStatus ORDER BY ServiceName"):
        print(f"  {R.get('ServiceName')}: InstanceName={R.get('InstanceName')} ProcessId={R.get('ProcessId')} UpdatedAt={R.get('UpdatedAt')}")
    return 0


if __name__ == '__main__':
    raise SystemExit(Run())
