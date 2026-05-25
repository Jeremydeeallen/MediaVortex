"""Data-driven test file selection for pipeline tests.

Each function queries the live DB for a MediaFile that matches a stated
intent (e.g. "needs Quick Fix only", "needs Transcode + audio fix").
Selection is filtered to safe candidates (not suspect, has a real local
path, under a size cap) and ordered by recency or randomly within the
eligible set.

The point: the test asserts what SHOULD happen for a category of file.
The fixture picks the file. Tests stay stable across library churn.

See Tests/Pipeline/pipeline-test-harness.feature.md criteria 15-16.
"""

from __future__ import annotations

import os
from typing import Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


def _ResolveLocalPath(CanonicalPath: str) -> Optional[str]:
    try:
        from Core.PathStorage import LoadStorageRoots, Parse as PathParse, Resolve as PathResolve
        from Core.WorkerContext import WorkerContext
        Db = DatabaseService()
        SrId, Rel = PathParse(CanonicalPath, LoadStorageRoots(Db))
        Ctx = WorkerContext.Current()
        WorkerName = Ctx.WorkerName if Ctx else os.environ.get('MEDIAVORTEX_WORKER_NAME', 'I9-2024')
        if SrId is not None and Rel is not None:
            return PathResolve(SrId, Rel, WorkerName, Db)
    except Exception:
        return None
    return None


def _PickReachable(CandidateIds: list[tuple[int, str]]) -> Optional[int]:
    """From a list of (Id, FilePath), return the first whose local path resolves and exists."""
    for MediaFileId, FilePath in CandidateIds:
        LocalPath = _ResolveLocalPath(FilePath)
        if LocalPath and os.path.exists(LocalPath):
            return MediaFileId
    return None


class NoCandidatesError(RuntimeError):
    """No DB rows match the requested fixture criteria + reachability."""


def QuickFixCandidate(MinSizeMB: int = 80, MaxSizeMB: int = 500, Limit: int = 25) -> int:
    """Return a MediaFileId that needs Quick Fix (Remux / audio normalize).

    Eligible row criteria:
      - RecommendedMode IN ('Quick', 'Remux')  -- routing flagged it
      - AudioComplete is not True              -- audio still needs work
      - AudioCorruptSuspect is not True        -- safe to encode
      - MinSizeMB <= SizeMB <= MaxSizeMB       -- big enough that subsequent
                                                  Transcode produces savings,
                                                  small enough that tests stay fast
      - HasExplicitEnglishAudio = True         -- audio stream selectable
      - All four loudness measurements populated -- linear-loudnorm gate passes
      - File reachable from this worker's filesystem
    """
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        """
        SELECT Id, FilePath FROM MediaFiles
        WHERE RecommendedMode IN ('Quick', 'Remux')
          AND (AudioComplete IS NULL OR AudioComplete = FALSE)
          AND (AudioCorruptSuspect IS NULL OR AudioCorruptSuspect = FALSE)
          AND SizeMB BETWEEN %s AND %s
          AND HasExplicitEnglishAudio = TRUE
          AND SourceIntegratedLufs IS NOT NULL
          AND SourceLoudnessRangeLU IS NOT NULL
          AND SourceTruePeakDbtp IS NOT NULL
          AND SourceIntegratedThresholdLufs IS NOT NULL
          AND AssignedProfile IS NOT NULL
        ORDER BY SizeMB ASC
        LIMIT %s
        """,
        (MinSizeMB, MaxSizeMB, Limit),
    )
    Candidates = [(int(R['id']), R['filepath']) for R in Rows]
    Picked = _PickReachable(Candidates)
    if Picked is None:
        raise NoCandidatesError(
            f"No reachable QuickFix candidate with SizeMB <= {MaxSizeMB} "
            f"(checked {len(Candidates)} rows)"
        )
    LoggingService.LogInfo(
        f"QuickFixCandidate selected: Id={Picked}",
        "Fixtures", "QuickFixCandidate",
    )
    return Picked


def TranscodeCandidate(MinSizeMB: int = 80, MaxSizeMB: int = 500, Limit: int = 25) -> int:
    """Return a MediaFileId that needs both Transcode AND audio fix.

    Eligible row criteria mirror QuickFixCandidate but with RecommendedMode='Transcode'.
    """
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        """
        SELECT Id, FilePath FROM MediaFiles
        WHERE RecommendedMode = 'Transcode'
          AND (AudioComplete IS NULL OR AudioComplete = FALSE)
          AND (AudioCorruptSuspect IS NULL OR AudioCorruptSuspect = FALSE)
          AND SizeMB BETWEEN %s AND %s
          AND HasExplicitEnglishAudio = TRUE
          AND SourceIntegratedLufs IS NOT NULL
          AND SourceLoudnessRangeLU IS NOT NULL
          AND SourceTruePeakDbtp IS NOT NULL
          AND SourceIntegratedThresholdLufs IS NOT NULL
          AND AssignedProfile IS NOT NULL
        ORDER BY SizeMB ASC
        LIMIT %s
        """,
        (MinSizeMB, MaxSizeMB, Limit),
    )
    Candidates = [(int(R['id']), R['filepath']) for R in Rows]
    Picked = _PickReachable(Candidates)
    if Picked is None:
        raise NoCandidatesError(
            f"No reachable Transcode candidate with SizeMB <= {MaxSizeMB} "
            f"(checked {len(Candidates)} rows)"
        )
    LoggingService.LogInfo(
        f"TranscodeCandidate selected: Id={Picked}",
        "Fixtures", "TranscodeCandidate",
    )
    return Picked


def AlreadyCompliant(Limit: int = 25) -> int:
    """Return a MediaFileId that is already compliant -- for negative tests.

    Eligible row criteria:
      - IsCompliant = TRUE
      - AudioComplete = TRUE
      - RecommendedMode IS NULL
    """
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        """
        SELECT Id, FilePath FROM MediaFiles
        WHERE IsCompliant = TRUE
          AND AudioComplete = TRUE
          AND RecommendedMode IS NULL
          AND HasExplicitEnglishAudio = TRUE
        ORDER BY SizeMB ASC
        LIMIT %s
        """,
        (Limit,),
    )
    Candidates = [(int(R['id']), R['filepath']) for R in Rows]
    Picked = _PickReachable(Candidates)
    if Picked is None:
        raise NoCandidatesError(
            f"No reachable already-compliant candidate (checked {len(Candidates)} rows)"
        )
    return Picked
