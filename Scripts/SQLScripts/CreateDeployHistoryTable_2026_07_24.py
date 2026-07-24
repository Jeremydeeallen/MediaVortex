# directive: deploy-worker-identity-invariants | # see worker-deploy.C19
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from Core.Database.DatabaseService import DatabaseService


def Main():
    Db = DatabaseService()
    Db.ExecuteNonQuery(
        "CREATE TABLE IF NOT EXISTS DeployHistory ("
        "  Id BIGSERIAL PRIMARY KEY,"
        "  StartedAt TIMESTAMP NOT NULL DEFAULT NOW(),"
        "  CompletedAt TIMESTAMP,"
        "  PriorSha TEXT,"
        "  NewSha TEXT NOT NULL,"
        "  ElapsedSeconds INTEGER,"
        "  HostsAttempted TEXT,"
        "  HostsSucceeded TEXT,"
        "  Outcome TEXT NOT NULL DEFAULT 'RUNNING',"
        "  ErrorMessage TEXT"
        ")"
    )
    Db.ExecuteNonQuery(
        "CREATE INDEX IF NOT EXISTS ix_deployhistory_startedat_desc ON DeployHistory (StartedAt DESC)"
    )
    Row = Db.ExecuteQuery("SELECT COUNT(*) AS n FROM DeployHistory")
    N = Row[0].get('n') if Row else 0
    print(f"DeployHistory table ready. Rows: {N}")


if __name__ == '__main__':
    Main()
