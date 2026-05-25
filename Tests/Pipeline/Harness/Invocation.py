"""Synchronous pipeline invocation for tests.

Drives a real MediaFile through the actual Quick Fix (Remux) or
Transcode pipeline by inserting a TranscodeQueue row and calling
`ProcessTranscodeQueueService.ProcessJob` directly. Blocks until the
pipeline completes; returns the resulting TranscodeAttemptId so the
caller can assert against it.

Refuses to run if a real worker has the file claimed -- the harness
must never race with the fleet.

See Tests/Pipeline/pipeline-test-harness.feature.md criteria 4-7.
"""

from __future__ import annotations

import os
import socket
import time
from datetime import datetime, timezone
from typing import Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


class PipelineBusyError(RuntimeError):
    """The fleet has an in-flight job for this MediaFile."""


def _EnsureWorkerContext(WorkerName: str = "I9-2024") -> None:
    """Initialize WorkerContext for the harness if not already set.

    Reads FFmpegPath, FFprobePath, and WorkerShareMappings from the DB,
    then calls WorkerContext.Initialize. No-op if already initialized.
    """
    from Core.WorkerContext import WorkerContext
    if WorkerContext.Current() is not None:
        return
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT FFmpegPath, FFprobePath, Platform FROM Workers WHERE WorkerName = %s",
        (WorkerName,),
    )
    if not Rows:
        raise RuntimeError(
            f"Worker {WorkerName!r} not registered in Workers table; "
            f"cannot initialize WorkerContext for the harness"
        )
    R = Rows[0]
    MountRows = Db.ExecuteQuery(
        "SELECT DriveLetter, LocalMountPrefix FROM WorkerShareMappings WHERE WorkerName = %s",
        (WorkerName,),
    )
    MountMap = {M['DriveLetter']: M['LocalMountPrefix'] for M in MountRows}
    WorkerContext.Initialize(
        WorkerName=WorkerName,
        Platform=R.get('Platform') or 'windows',
        FFmpegPath=R.get('FFmpegPath'),
        FFprobePath=R.get('FFprobePath'),
        ShareMappings=MountMap,
    )
    LoggingService.LogInfo(
        f"Harness initialized WorkerContext for {WorkerName}: "
        f"FFmpegPath={R.get('FFmpegPath')!r}, "
        f"ShareMappings={len(MountMap)} drives",
        "Invocation", "_EnsureWorkerContext",
    )


def _AssertNoActiveWork(MediaFileId: int) -> None:
    """Refuse to run if another worker already has the file claimed."""
    Db = DatabaseService()
    Conflicts = Db.ExecuteQuery(
        "SELECT q.Id AS QueueId, a.Id AS ActiveJobId, a.WorkerName "
        "FROM TranscodeQueue q LEFT JOIN ActiveJobs a ON a.QueueId = q.Id "
        "WHERE q.MediaFileId = %s",
        (MediaFileId,),
    )
    if Conflicts:
        Detail = ", ".join(
            f"QueueId={C.get('QueueId')} ActiveJobId={C.get('ActiveJobId')} "
            f"Worker={C.get('WorkerName')!r}"
            for C in Conflicts
        )
        raise PipelineBusyError(
            f"MediaFile {MediaFileId} has existing queue/active rows: {Detail}. "
            f"Refusing to invoke pipeline -- harness must not race with the fleet."
        )


def _InsertQueueRow(MediaFileId: int, ProcessingMode: str) -> int:
    """Insert a TranscodeQueue row for the test invocation; return its Id.

    Uses the real queue insert path so the row is shape-correct (Priority,
    Status, AssignedProfile populated from MediaFiles).
    """
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT StorageRootId, RelativePath, FilePath, FileName, FileSize AS SizeBytes, "
        "SizeMB, AssignedProfile, PriorityScore "
        "FROM MediaFiles WHERE Id = %s",
        (MediaFileId,),
    )
    if not Rows:
        raise ValueError(f"MediaFile {MediaFileId} not found")
    M = Rows[0]  # CaseInsensitiveDict -- access via M['Anything'] is case-insensitive

    # MediaFiles.FileSize is often NULL on rows the probe never populated.
    # ProcessJob propagates Job.SizeBytes to TranscodeAttempts.OldSizeBytes,
    # which then drives the post-transcode defense-in-depth size check. A 0
    # there causes "refusing to replace because new >= 0". Stat the local
    # file to get a real value.
    SizeBytes = int(M.get('SizeBytes') or 0)
    if SizeBytes <= 0:
        try:
            from Core.PathStorage import LoadStorageRoots, Parse as PathParse, Resolve as PathResolve
            from Core.WorkerContext import WorkerContext
            SrId, Rel = PathParse(M.get('FilePath') or '', LoadStorageRoots(Db))
            Ctx = WorkerContext.Current()
            LocalP = PathResolve(SrId, Rel, Ctx.WorkerName, Db) if Ctx else None
            if LocalP and os.path.exists(LocalP):
                SizeBytes = os.path.getsize(LocalP)
        except Exception:
            pass
    SizeMB = float(M.get('SizeMB') or 0.0) or (SizeBytes / 1024.0 / 1024.0)

    Now = datetime.now(timezone.utc)
    # Use ExecuteNonQuery so the INSERT commits; ExecuteQuery does not commit
    # and the RETURNING row would be rolled back on connection close.
    Db.ExecuteNonQuery(
        """
        INSERT INTO TranscodeQueue
          (StorageRootId, RelativePath, FilePath, FileName, Directory,
           SizeBytes, SizeMB, Priority, Status, DateAdded,
           ProcessingMode, MediaFileId)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING Id
        """,
        (
            M.get('StorageRootId'),
            M.get('RelativePath') or '',
            M.get('FilePath'),
            M.get('FileName'),
            os.path.dirname(M.get('FilePath') or ''),
            SizeBytes,
            SizeMB,
            int(M.get('PriorityScore') or 0),
            'Pending',
            Now,
            ProcessingMode,
            MediaFileId,
        ),
    )
    QueueId = int(Db.LastInsertId)
    LoggingService.LogInfo(
        f"Harness enqueued MediaFile {MediaFileId} as {ProcessingMode} "
        f"(QueueId={QueueId})",
        "Invocation", "_InsertQueueRow",
    )
    return QueueId


def _LoadQueueModel(QueueId: int):
    """Load the TranscodeQueueModel for a freshly-inserted row."""
    from Features.TranscodeQueue.Models.TranscodeQueueModel import TranscodeQueueModel
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT q.Id, q.StorageRootId, q.RelativePath, q.FilePath, q.FileName, q.Directory, "
        "q.SizeBytes, q.SizeMB, q.Priority, q.Status, m.AssignedProfile, q.ProcessingMode, "
        "q.MediaFileId, q.DateAdded, q.DateStarted "
        "FROM TranscodeQueue q LEFT JOIN MediaFiles m ON m.Id = q.MediaFileId "
        "WHERE q.Id = %s",
        (QueueId,),
    )
    if not Rows:
        raise RuntimeError(f"Queue row {QueueId} disappeared after insert")
    R = Rows[0]  # CaseInsensitiveDict
    return TranscodeQueueModel(
        Id=R.get('Id'),
        StorageRootId=R.get('StorageRootId'),
        RelativePath=R.get('RelativePath') or '',
        FilePath=R.get('FilePath') or '',
        FileName=R.get('FileName') or '',
        Directory=R.get('Directory') or '',
        SizeBytes=R.get('SizeBytes') or 0,
        SizeMB=R.get('SizeMB') or 0.0,
        Priority=R.get('Priority') or 0,
        Status=R.get('Status') or 'Pending',
        AssignedProfile=R.get('AssignedProfile') or '',
        ProcessingMode=R.get('ProcessingMode') or 'Transcode',
        MediaFileId=R.get('MediaFileId'),
        DateAdded=R.get('DateAdded'),
        DateStarted=R.get('DateStarted'),
    )


def _FindLatestAttemptId(MediaFileId: int, SinceTs: float) -> Optional[int]:
    """Find the TranscodeAttempt this MediaFile produced after SinceTs."""
    Db = DatabaseService()
    Cutoff = datetime.fromtimestamp(SinceTs, tz=timezone.utc)
    Rows = Db.ExecuteQuery(
        "SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s AND AttemptDate >= %s "
        "ORDER BY AttemptDate DESC LIMIT 1",
        (MediaFileId, Cutoff),
    )
    if not Rows:
        return None
    return int(Rows[0]['Id'])


def _Invoke(MediaFileId: int, ProcessingMode: str) -> int:
    """Internal: enqueue, drive ProcessJob, return TranscodeAttemptId."""
    _EnsureWorkerContext()
    _AssertNoActiveWork(MediaFileId)

    SinceTs = time.time()
    QueueId = _InsertQueueRow(MediaFileId, ProcessingMode)

    # Build the QueueModel and invoke the real pipeline. ProcessJob handles
    # ActiveJobs creation, queue status updates, FFmpeg execution, file
    # replacement, and queue cleanup. Synchronous; we just call it.
    from Features.TranscodeJob.ProcessTranscodeQueueService import ProcessTranscodeQueueService
    Svc = ProcessTranscodeQueueService(WorkerName="I9-2024")
    Job = _LoadQueueModel(QueueId)
    LoggingService.LogInfo(
        f"Harness invoking ProcessJob(QueueId={QueueId}, Mode={ProcessingMode}, "
        f"MediaFileId={MediaFileId})",
        "Invocation", "_Invoke",
    )
    Svc.ProcessJob(Job)
    LoggingService.LogInfo(
        f"Harness ProcessJob returned for QueueId={QueueId}",
        "Invocation", "_Invoke",
    )

    AttemptId = _FindLatestAttemptId(MediaFileId, SinceTs)
    if AttemptId is None:
        raise RuntimeError(
            f"ProcessJob ran for MediaFile {MediaFileId} but no TranscodeAttempts "
            f"row was created with AttemptDate >= {SinceTs}. The pipeline failed "
            f"before reaching the attempt-record step; check worker logs."
        )
    return AttemptId


def InvokeQuickFix(MediaFileId: int) -> int:
    """Run Quick Fix (Remux + audio normalize) synchronously. Returns attempt Id."""
    return _Invoke(MediaFileId, 'Quick')


def InvokeTranscode(MediaFileId: int) -> int:
    """Run Transcode (full video re-encode) synchronously. Returns attempt Id."""
    return _Invoke(MediaFileId, 'Transcode')
