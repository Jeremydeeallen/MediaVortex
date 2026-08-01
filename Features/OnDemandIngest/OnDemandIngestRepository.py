# directive: probe-worker-decoupled -- claim + list for OnDemandScanRequests + OnDemandProbeRequests.
from typing import List, Optional
from Core.Database.DatabaseService import DatabaseService


class OnDemandIngestRepository:

    def __init__(self, Db: DatabaseService = None):
        self.Db = Db or DatabaseService()

    # ---- Insert ----

    def InsertScanRequest(self, StorageRootId: int, RelativePath: str) -> int:
        self.Db.ExecuteNonQuery(
            "INSERT INTO OnDemandScanRequests (StorageRootId, RelativePath) VALUES (%s, %s) RETURNING Id",
            (StorageRootId, RelativePath),
        )
        return int(self.Db.GetLastInsertId() or 0)

    def InsertProbeRequest(self, StorageRootId: int, RelativePath: str) -> int:
        self.Db.ExecuteNonQuery(
            "INSERT INTO OnDemandProbeRequests (StorageRootId, RelativePath) VALUES (%s, %s) RETURNING Id",
            (StorageRootId, RelativePath),
        )
        return int(self.Db.GetLastInsertId() or 0)

    # ---- Claim (atomic, single TX) ----

    def ClaimNextPendingScanRequest(self, WorkerName: str) -> Optional[dict]:
        Rows = self.Db.ExecuteReturning(
            "UPDATE OnDemandScanRequests SET Status='Claimed', ClaimedBy=%s, ClaimedAt=NOW() "
            "WHERE Id = (SELECT Id FROM OnDemandScanRequests WHERE Status='Pending' "
            "ORDER BY RequestedAt ASC FOR UPDATE SKIP LOCKED LIMIT 1) "
            "RETURNING Id, StorageRootId, RelativePath",
            (WorkerName,),
        )
        return Rows[0] if Rows else None

    def ClaimNextPendingProbeRequest(self, WorkerName: str) -> Optional[dict]:
        Rows = self.Db.ExecuteReturning(
            "UPDATE OnDemandProbeRequests SET Status='Claimed', ClaimedBy=%s, ClaimedAt=NOW() "
            "WHERE Id = (SELECT Id FROM OnDemandProbeRequests WHERE Status='Pending' "
            "ORDER BY RequestedAt ASC FOR UPDATE SKIP LOCKED LIMIT 1) "
            "RETURNING Id, StorageRootId, RelativePath",
            (WorkerName,),
        )
        return Rows[0] if Rows else None

    # ---- Complete / Fail ----

    def MarkScanComplete(self, RequestId: int, FilesDiscovered: int) -> None:
        self.Db.ExecuteNonQuery(
            "UPDATE OnDemandScanRequests SET Status='Complete', CompletedAt=NOW(), FilesDiscovered=%s WHERE Id=%s",
            (FilesDiscovered, RequestId),
        )

    def MarkScanFailed(self, RequestId: int, ErrorMessage: str) -> None:
        self.Db.ExecuteNonQuery(
            "UPDATE OnDemandScanRequests SET Status='Failed', CompletedAt=NOW(), ErrorMessage=%s WHERE Id=%s",
            (ErrorMessage[:2000], RequestId),
        )

    def MarkProbeComplete(self, RequestId: int, FilesProbed: int) -> None:
        self.Db.ExecuteNonQuery(
            "UPDATE OnDemandProbeRequests SET Status='Complete', CompletedAt=NOW(), FilesProbed=%s WHERE Id=%s",
            (FilesProbed, RequestId),
        )

    def MarkProbeFailed(self, RequestId: int, ErrorMessage: str) -> None:
        self.Db.ExecuteNonQuery(
            "UPDATE OnDemandProbeRequests SET Status='Failed', CompletedAt=NOW(), ErrorMessage=%s WHERE Id=%s",
            (ErrorMessage[:2000], RequestId),
        )

    # ---- Recent lists ----

    def RecentScanRequests(self, Limit: int = 20) -> List[dict]:
        return self.Db.ExecuteQuery(
            "SELECT Id, StorageRootId, RelativePath, RequestedAt, ClaimedBy, ClaimedAt, "
            "CompletedAt, Status, FilesDiscovered, ErrorMessage "
            "FROM OnDemandScanRequests ORDER BY RequestedAt DESC LIMIT %s",
            (Limit,),
        ) or []

    def RecentProbeRequests(self, Limit: int = 20) -> List[dict]:
        return self.Db.ExecuteQuery(
            "SELECT Id, StorageRootId, RelativePath, RequestedAt, ClaimedBy, ClaimedAt, "
            "CompletedAt, Status, FilesProbed, ErrorMessage "
            "FROM OnDemandProbeRequests ORDER BY RequestedAt DESC LIMIT %s",
            (Limit,),
        ) or []
