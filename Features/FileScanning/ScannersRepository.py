from Core.Database.DatabaseService import DatabaseService


GET_BY_NAME_SQL = (
    "SELECT ScannerName, Enabled, IntervalSec, BatchSize, DryRun, LastRunAt, LastUpdated "
    "FROM Scanners WHERE ScannerName = %s"
)


LIST_SQL = (
    "SELECT ScannerName, Enabled, IntervalSec, BatchSize, DryRun, LastRunAt, LastUpdated "
    "FROM Scanners ORDER BY ScannerName"
)


UPDATE_SQL = (
    "UPDATE Scanners "
    "SET Enabled = %s, IntervalSec = %s, BatchSize = %s, DryRun = %s, LastUpdated = NOW() "
    "WHERE ScannerName = %s"
)


HEARTBEAT_SQL = (
    "UPDATE Scanners SET LastRunAt = NOW() WHERE ScannerName = %s"
)


PAUSE_ALL_SQL = (
    "UPDATE Scanners SET Enabled = FALSE, LastUpdated = NOW() WHERE Enabled = TRUE"
)


# directive: audio-vertical-phase-1-completion | # see directive.md P3
class ScannersRepository:
    """Read/write the Scanners orchestrator config (one row per periodic scan service); no boot cache per db-is-authority."""

    # directive: audio-vertical-phase-1-completion | # see directive.md P3
    def Get(self, ScannerName):
        """Return one Scanner row by name as a dict, or None when unknown."""
        Rows = DatabaseService().ExecuteQuery(GET_BY_NAME_SQL, (ScannerName,))
        return Rows[0] if Rows else None

    # directive: audio-vertical-phase-1-completion | # see directive.md P3
    def List(self):
        """Return every Scanner row in stable name order."""
        return DatabaseService().ExecuteQuery(LIST_SQL) or []

    # directive: audio-vertical-phase-1-completion | # see directive.md P3
    def Update(self, ScannerName, Enabled, IntervalSec, BatchSize, DryRun):
        """Update one Scanner row; rejects unknown ScannerName by returning False."""
        if not self.Get(ScannerName):
            return False
        DatabaseService().ExecuteNonQuery(
            UPDATE_SQL,
            (bool(Enabled), max(60, int(IntervalSec)), max(1, int(BatchSize)), bool(DryRun), ScannerName),
        )
        return True

    # directive: audio-vertical-phase-1-completion | # see directive.md P3
    def RecordRun(self, ScannerName):
        """Stamp LastRunAt to NOW for the named scanner; called by each service at the end of a successful cycle."""
        DatabaseService().ExecuteNonQuery(HEARTBEAT_SQL, (ScannerName,))

    # directive: audio-vertical-phase-1-completion | # see directive.md P3
    def PauseAll(self):
        """Flip Enabled=FALSE on every row; returns the count of rows that were Enabled before."""
        Db = DatabaseService()
        Before = Db.ExecuteQuery("SELECT COUNT(*)::int AS c FROM Scanners WHERE Enabled = TRUE")
        Count = int(Before[0]['c']) if Before else 0
        if Count > 0:
            Db.ExecuteNonQuery(PAUSE_ALL_SQL)
        return Count
