# see probe-worker-decoupled.C5 + C6 -- on-demand ingest queues; idempotent.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Core.Database.DatabaseService import DatabaseService


ScanTable = (
    "CREATE TABLE IF NOT EXISTS OnDemandScanRequests ("
    "  Id BIGSERIAL PRIMARY KEY,"
    "  StorageRootId BIGINT NOT NULL,"
    "  RelativePath TEXT NOT NULL,"
    "  RequestedAt TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
    "  ClaimedBy TEXT,"
    "  ClaimedAt TIMESTAMPTZ,"
    "  CompletedAt TIMESTAMPTZ,"
    "  Status TEXT NOT NULL DEFAULT 'Pending' "
    "    CHECK (Status IN ('Pending','Claimed','Complete','Failed')),"
    "  FilesDiscovered INT,"
    "  ErrorMessage TEXT"
    ")"
)
ScanIdx = "CREATE INDEX IF NOT EXISTS idx_ondemandscanrequests_pending ON OnDemandScanRequests (RequestedAt) WHERE Status = 'Pending'"

ProbeTable = (
    "CREATE TABLE IF NOT EXISTS OnDemandProbeRequests ("
    "  Id BIGSERIAL PRIMARY KEY,"
    "  StorageRootId BIGINT NOT NULL,"
    "  RelativePath TEXT NOT NULL,"
    "  RequestedAt TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
    "  ClaimedBy TEXT,"
    "  ClaimedAt TIMESTAMPTZ,"
    "  CompletedAt TIMESTAMPTZ,"
    "  Status TEXT NOT NULL DEFAULT 'Pending' "
    "    CHECK (Status IN ('Pending','Claimed','Complete','Failed')),"
    "  FilesProbed INT,"
    "  ErrorMessage TEXT"
    ")"
)
ProbeIdx = "CREATE INDEX IF NOT EXISTS idx_ondemandproberequests_pending ON OnDemandProbeRequests (RequestedAt) WHERE Status = 'Pending'"


def Run():
    Db = DatabaseService()
    Db.ExecuteNonQuery(ScanTable)
    Db.ExecuteNonQuery(ScanIdx)
    Db.ExecuteNonQuery(ProbeTable)
    Db.ExecuteNonQuery(ProbeIdx)
    print("Created OnDemandScanRequests + OnDemandProbeRequests (idempotent)")


if __name__ == '__main__':
    Run()
