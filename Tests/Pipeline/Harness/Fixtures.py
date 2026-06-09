from __future__ import annotations

from typing import Optional, Tuple

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalExists
from Tests.Pipeline.Harness.HarnessPathResolver import BuildHarnessWorker, ResolveLocalPath


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
class NoCandidatesError(RuntimeError):
    """No DB rows match the requested fixture criteria + reachability."""


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def _PickReachable(Candidates: list[Tuple[int, Optional[int], str]]) -> Optional[int]:
    """First (Id, StorageRootId, RelativePath) whose local path resolves and exists on disk; None if none reachable."""
    Db = DatabaseService()
    W = BuildHarnessWorker(Db)
    for MediaFileId, StorageRootId, RelativePath in Candidates:
        LocalPath = ResolveLocalPath(W, StorageRootId, RelativePath)
        if LocalPath and LocalExists(LocalPath):
            return MediaFileId
    return None


_ORPHAN_NOT_EXISTS = (
    "AND NOT EXISTS ("
    "SELECT 1 FROM MediaFiles m2 "
    "WHERE m2.Id <> m.Id "
    "AND m2.StorageRootId = m.StorageRootId "
    "AND POSITION("
    "LOWER(SUBSTRING(m.RelativePath FROM 1 FOR LENGTH(m.RelativePath) - LENGTH("
    "SUBSTRING(m.RelativePath FROM E'\\.[^.\\\\/]+$')"
    ")) || '-mv') IN LOWER(m2.RelativePath)"
    ") = 1"
    ")"
)

_SHARED_PREDICATE = (
    "(m.AudioComplete IS NULL OR m.AudioComplete = FALSE) "
    "AND (m.AudioCorruptSuspect IS NULL OR m.AudioCorruptSuspect = FALSE) "
    "AND m.SizeMB BETWEEN %s AND %s "
    "AND m.HasExplicitEnglishAudio = TRUE "
    "AND m.SourceIntegratedLufs IS NOT NULL "
    "AND m.SourceLoudnessRangeLU IS NOT NULL "
    "AND m.SourceTruePeakDbtp IS NOT NULL "
    "AND m.SourceIntegratedThresholdLufs IS NOT NULL "
    "AND m.AssignedProfile IS NOT NULL "
)


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def QuickFixCandidate(MinSizeMB: int = 80, MaxSizeMB: int = 500, Limit: int = 25) -> int:
    """A MediaFileId that needs Quick Fix (WorkBucket Remux or AudioFixOnly); see pipeline-test-harness.feature.md S2."""
    Db = DatabaseService()
    Sql = (
        "SELECT m.Id, m.StorageRootId, m.RelativePath FROM MediaFiles m "
        "WHERE m.WorkBucket IN ('Remux', 'AudioFixOnly') "
        "AND " + _SHARED_PREDICATE + _ORPHAN_NOT_EXISTS + " "
        "ORDER BY m.SizeMB ASC LIMIT %s"
    )
    Rows = Db.ExecuteQuery(Sql, (MinSizeMB, MaxSizeMB, Limit))
    Candidates = [(int(R['Id']), R['StorageRootId'], R['RelativePath'] or '') for R in Rows]
    Picked = _PickReachable(Candidates)
    if Picked is None:
        raise NoCandidatesError(f"No reachable QuickFix candidate with {MinSizeMB} <= SizeMB <= {MaxSizeMB} (checked {len(Candidates)} rows)")
    LoggingService.LogInfo(f"QuickFixCandidate selected: Id={Picked}", "Fixtures", "QuickFixCandidate")
    return Picked


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def TranscodeCandidate(MinSizeMB: int = 80, MaxSizeMB: int = 500, Limit: int = 25) -> int:
    """A MediaFileId that needs Transcode (WorkBucket='Transcode'); see pipeline-test-harness.feature.md S2."""
    Db = DatabaseService()
    Sql = (
        "SELECT m.Id, m.StorageRootId, m.RelativePath FROM MediaFiles m "
        "WHERE m.WorkBucket = 'Transcode' "
        "AND " + _SHARED_PREDICATE + _ORPHAN_NOT_EXISTS + " "
        "ORDER BY m.SizeMB ASC LIMIT %s"
    )
    Rows = Db.ExecuteQuery(Sql, (MinSizeMB, MaxSizeMB, Limit))
    Candidates = [(int(R['Id']), R['StorageRootId'], R['RelativePath'] or '') for R in Rows]
    Picked = _PickReachable(Candidates)
    if Picked is None:
        raise NoCandidatesError(f"No reachable Transcode candidate with {MinSizeMB} <= SizeMB <= {MaxSizeMB} (checked {len(Candidates)} rows)")
    LoggingService.LogInfo(f"TranscodeCandidate selected: Id={Picked}", "Fixtures", "TranscodeCandidate")
    return Picked


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def AlreadyCompliant(Limit: int = 25) -> int:
    """A MediaFileId that is already compliant (WorkBucket IS NULL, IsCompliant=TRUE); see pipeline-test-harness.feature.md S2."""
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT Id, StorageRootId, RelativePath FROM MediaFiles "
        "WHERE IsCompliant = TRUE "
        "AND AudioComplete = TRUE "
        "AND WorkBucket IS NULL "
        "AND HasExplicitEnglishAudio = TRUE "
        "ORDER BY SizeMB ASC LIMIT %s",
        (Limit,),
    )
    Candidates = [(int(R['id']), R['storagerootid'], R['relativepath'] or '') for R in Rows]
    Picked = _PickReachable(Candidates)
    if Picked is None:
        raise NoCandidatesError(f"No reachable already-compliant candidate (checked {len(Candidates)} rows)")
    return Picked
