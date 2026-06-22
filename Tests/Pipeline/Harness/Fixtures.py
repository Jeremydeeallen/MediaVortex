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


# directive: compliance-symmetry
def _RecomputeAndVerify(MediaFileId: int, ExpectedBucket: str) -> bool:
    from Features.AudioNormalization.AudioVertical import AudioVertical
    from Features.VideoEncoding.VideoVertical import VideoVertical
    from Features.ContainerFormat.ContainerVertical import ContainerVertical
    AudioVertical().RecomputeFor([MediaFileId])
    VideoVertical().RecomputeFor([MediaFileId])
    ContainerVertical().RecomputeFor([MediaFileId])
    Check = DatabaseService().ExecuteQuery("SELECT WorkBucket FROM MediaFiles WHERE Id = %s", (MediaFileId,))
    return bool(Check) and Check[0]['workbucket'] == ExpectedBucket


# directive: compliance-symmetry
def TranscodeCandidate(MinSizeMB: int = 80, MaxSizeMB: int = 500, Limit: int = 25) -> int:
    Db = DatabaseService()
    Sql = (
        "SELECT m.Id, m.StorageRootId, m.RelativePath FROM MediaFiles m "
        "JOIN Profiles p ON p.ProfileName = m.AssignedProfile "
        "WHERE LOWER(m.Codec) <> LOWER(p.StreamCodecName) "
        "AND p.Active = TRUE AND p.Draft = FALSE "
        "AND " + _SHARED_PREDICATE + _ORPHAN_NOT_EXISTS + " "
        "ORDER BY m.SizeMB ASC LIMIT %s"
    )
    Rows = Db.ExecuteQuery(Sql, (MinSizeMB, MaxSizeMB, Limit))
    Candidates = [(int(R['Id']), R['StorageRootId'], R['RelativePath'] or '') for R in Rows]
    Picked = _PickReachable(Candidates)
    if Picked is None:
        raise NoCandidatesError(f"No reachable Transcode candidate (codec mismatch) with {MinSizeMB} <= SizeMB <= {MaxSizeMB} (checked {len(Candidates)} rows)")
    if not _RecomputeAndVerify(Picked, 'Transcode'):
        raise NoCandidatesError(f"Picked candidate {Picked} did not settle as Transcode bucket post-recompute")
    LoggingService.LogInfo(f"TranscodeCandidate selected: Id={Picked}", "Fixtures", "TranscodeCandidate")
    return Picked


# directive: compliance-symmetry
def RemuxCandidate(MinSizeMB: int = 80, MaxSizeMB: int = 500, Limit: int = 25) -> int:
    Db = DatabaseService()
    Sql = (
        "SELECT m.Id, m.StorageRootId, m.RelativePath FROM MediaFiles m "
        "JOIN Profiles p ON p.ProfileName = m.AssignedProfile "
        "WHERE LOWER(m.Codec) = LOWER(p.StreamCodecName) "
        "AND m.ContainerFormat = 'matroska,webm' "
        "AND p.Container IN ('mp4','m4v','mov') "
        "AND p.Active = TRUE AND p.Draft = FALSE "
        "AND " + _SHARED_PREDICATE + _ORPHAN_NOT_EXISTS + " "
        "ORDER BY m.SizeMB ASC LIMIT %s"
    )
    Rows = Db.ExecuteQuery(Sql, (MinSizeMB, MaxSizeMB, Limit))
    Candidates = [(int(R['Id']), R['StorageRootId'], R['RelativePath'] or '') for R in Rows]
    Picked = _PickReachable(Candidates)
    if Picked is None:
        raise NoCandidatesError(f"No reachable Remux candidate (container mismatch) with {MinSizeMB} <= SizeMB <= {MaxSizeMB} (checked {len(Candidates)} rows)")
    if not _RecomputeAndVerify(Picked, 'Remux'):
        raise NoCandidatesError(f"Picked candidate {Picked} did not settle as Remux bucket post-recompute")
    LoggingService.LogInfo(f"RemuxCandidate selected: Id={Picked}", "Fixtures", "RemuxCandidate")
    return Picked


# directive: compliance-symmetry
def AudioFixOnlyCandidate(MinSizeMB: int = 80, MaxSizeMB: int = 500, Limit: int = 25) -> int:
    Db = DatabaseService()
    Sql = (
        "SELECT m.Id, m.StorageRootId, m.RelativePath FROM MediaFiles m "
        "JOIN Profiles p ON p.ProfileName = m.AssignedProfile "
        "WHERE LOWER(m.Codec) = LOWER(p.StreamCodecName) "
        "AND m.ContainerFormat ILIKE ('%%' || p.Container || '%%') "
        "AND (m.AudioComplete IS NULL OR m.AudioComplete = FALSE) "
        "AND p.Active = TRUE AND p.Draft = FALSE "
        "AND " + _SHARED_PREDICATE + _ORPHAN_NOT_EXISTS + " "
        "ORDER BY m.SizeMB ASC LIMIT %s"
    )
    Rows = Db.ExecuteQuery(Sql, (MinSizeMB, MaxSizeMB, Limit))
    Candidates = [(int(R['Id']), R['StorageRootId'], R['RelativePath'] or '') for R in Rows]
    Picked = _PickReachable(Candidates)
    if Picked is None:
        raise NoCandidatesError(f"No reachable AudioFixOnly candidate (audio incomplete with codec+container match) with {MinSizeMB} <= SizeMB <= {MaxSizeMB} (checked {len(Candidates)} rows)")
    if not _RecomputeAndVerify(Picked, 'AudioFixOnly'):
        raise NoCandidatesError(f"Picked candidate {Picked} did not settle as AudioFixOnly bucket post-recompute")
    LoggingService.LogInfo(f"AudioFixOnlyCandidate selected: Id={Picked}", "Fixtures", "AudioFixOnlyCandidate")
    return Picked


# directive: compliance-symmetry
def AlreadyCompliant(Limit: int = 50) -> int:
    """Pick by raw metadata matching per-profile bar; recompute verticals; verify post-recompute WorkBucket is NULL."""
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT m.Id, m.StorageRootId, m.RelativePath FROM MediaFiles m "
        "JOIN Profiles p ON p.ProfileName = m.AssignedProfile "
        "WHERE LOWER(m.Codec) = LOWER(p.StreamCodecName) "
        "AND LOWER(m.AudioCodec) = LOWER(p.AudioCodec) "
        "AND m.AudioComplete = TRUE "
        "AND m.HasExplicitEnglishAudio = TRUE "
        "AND (m.AudioCorruptSuspect IS NULL OR m.AudioCorruptSuspect = FALSE) "
        "AND m.ContainerFormat ILIKE '%%mp4%%' "
        "AND p.Container = 'mp4' "
        "AND p.Active = TRUE AND p.Draft = FALSE "
        "ORDER BY m.SizeMB ASC LIMIT %s",
        (Limit,),
    )
    Candidates = [(int(R['id']), R['storagerootid'], R['relativepath'] or '') for R in Rows]
    Picked = _PickReachable(Candidates)
    if Picked is None:
        raise NoCandidatesError(f"No reachable compliant candidate matching the per-profile bar (checked {len(Candidates)} rows)")
    from Features.AudioNormalization.AudioVertical import AudioVertical
    from Features.VideoEncoding.VideoVertical import VideoVertical
    from Features.ContainerFormat.ContainerVertical import ContainerVertical
    AudioVertical().RecomputeFor([Picked])
    VideoVertical().RecomputeFor([Picked])
    ContainerVertical().RecomputeFor([Picked])
    Check = Db.ExecuteQuery("SELECT WorkBucket FROM MediaFiles WHERE Id = %s", (Picked,))
    if Check and Check[0]['workbucket'] is not None:
        raise NoCandidatesError(f"Picked candidate {Picked} did not settle compliant post-recompute (bucket={Check[0]['workbucket']!r})")
    LoggingService.LogInfo(f"AlreadyCompliant selected: Id={Picked}", "Fixtures", "AlreadyCompliant")
    return Picked
