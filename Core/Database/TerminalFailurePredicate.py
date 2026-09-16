# directive: bug-0095-failure-classification | # see failure-accounting.C11
from typing import Tuple


# directive: bug-0095-failure-classification | # see failure-accounting.C11
_ALLOWED_MEDIAFILE_COLUMNS = frozenset({
    "mf.Id",
    "mfarchive.Id",
    "MediaFiles.Id",
    "TranscodeQueue.MediaFileId",
    "tq.MediaFileId",
    "MediaFileId",
})


# directive: bug-0095-failure-classification | # see failure-accounting.C11
def BuildTerminalGate(MediaFileIdColumn: str = "mf.Id") -> Tuple[str, tuple]:
    """Emit the SQL fragment that ADMITS a MediaFile when its latest post-reset failing attempt has FailureClass with Terminal=FALSE (or is unclassified, or no failing attempt exists). Refuses when Terminal=TRUE.

    Every claim / admission / requeue query calls this alongside BuildCapPredicate. Reads FailureClasses.Terminal fresh at SQL evaluation time -- operator toggles in /settings observed by the next claim tick with no restart / no backfill (db-is-authority).

    Whitelisted column names only; ValueError on unknown to prevent SQL injection.
    """
    if MediaFileIdColumn not in _ALLOWED_MEDIAFILE_COLUMNS:
        raise ValueError(
            f"BuildTerminalGate: '{MediaFileIdColumn}' is not a whitelisted MediaFile-Id column. "
            f"Add it to _ALLOWED_MEDIAFILE_COLUMNS if it is a real column reference in an existing query."
        )
    SqlFragment = (
        "NOT EXISTS ("
        "  SELECT 1 FROM ("
        "    SELECT tf.FailureClass "
        "    FROM TranscodeAttempts tf "
        "    WHERE tf.MediaFileId = " + MediaFileIdColumn + " "
        "      AND tf.Success = FALSE "
        "      AND tf.AttemptDate > COALESCE("
        "        (SELECT LastFailureResetAt FROM MediaFiles WHERE Id = " + MediaFileIdColumn + "), "
        "        'epoch'::timestamp"
        "      ) "
        "    ORDER BY tf.AttemptDate DESC "
        "    LIMIT 1"
        "  ) latest "
        "  JOIN FailureClasses fc ON fc.ClassName = latest.FailureClass "
        "  WHERE fc.Terminal = TRUE"
        ")"
    )
    return SqlFragment, ()


# directive: bug-0095-failure-classification | # see failure-accounting.C11
def IsMediaFileTerminalBlocked(MediaFileId: int, Db=None) -> bool:
    """Python-side point query mirroring BuildTerminalGate's semantics. Used by AddJobToQueue single-file admission to shape the Terminal-envelope response. Reads FailureClasses fresh per call."""
    from Core.Database.DatabaseService import DatabaseService
    _Db = Db or DatabaseService()
    Rows = _Db.ExecuteQuery(
        "SELECT fc.ClassName, fc.Remediation "
        "FROM ( "
        "  SELECT tf.FailureClass "
        "  FROM TranscodeAttempts tf "
        "  WHERE tf.MediaFileId = %s "
        "    AND tf.Success = FALSE "
        "    AND tf.AttemptDate > COALESCE( "
        "      (SELECT LastFailureResetAt FROM MediaFiles WHERE Id = %s), "
        "      'epoch'::timestamp"
        "    ) "
        "  ORDER BY tf.AttemptDate DESC "
        "  LIMIT 1"
        ") latest "
        "JOIN FailureClasses fc ON fc.ClassName = latest.FailureClass "
        "WHERE fc.Terminal = TRUE",
        (int(MediaFileId), int(MediaFileId)),
    )
    if not Rows:
        return False
    return True


# directive: bug-0095-failure-classification | # see failure-accounting.C11
def GetTerminalRemediation(MediaFileId: int, Db=None):
    """Returns (ClassName, Remediation) tuple when Terminal-blocked; None otherwise. For shaping the AddJobToQueue Terminal-envelope response."""
    from Core.Database.DatabaseService import DatabaseService
    _Db = Db or DatabaseService()
    Rows = _Db.ExecuteQuery(
        "SELECT fc.ClassName, fc.Remediation "
        "FROM ( "
        "  SELECT tf.FailureClass "
        "  FROM TranscodeAttempts tf "
        "  WHERE tf.MediaFileId = %s "
        "    AND tf.Success = FALSE "
        "    AND tf.AttemptDate > COALESCE( "
        "      (SELECT LastFailureResetAt FROM MediaFiles WHERE Id = %s), "
        "      'epoch'::timestamp"
        "    ) "
        "  ORDER BY tf.AttemptDate DESC "
        "  LIMIT 1"
        ") latest "
        "JOIN FailureClasses fc ON fc.ClassName = latest.FailureClass "
        "WHERE fc.Terminal = TRUE",
        (int(MediaFileId), int(MediaFileId)),
    )
    if not Rows:
        return None
    R = Rows[0]
    return (R['ClassName'], R['Remediation'])
