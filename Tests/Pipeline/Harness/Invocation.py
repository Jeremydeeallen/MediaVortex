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
    R = dict(Rows[0])
    MountRows = Db.ExecuteQuery(
        "SELECT DriveLetter, LocalMountPrefix FROM WorkerShareMappings WHERE WorkerName = %s",
        (WorkerName,),
    )
    MountMap = {M['DriveLetter']: M['LocalMountPrefix'] for M in MountRows}
    WorkerContext.Initialize(
        WorkerName=WorkerName,
        Platform=R.get('platform') or 'windows',
        FFmpegPath=R.get('ffmpegpath'),
        FFprobePath=R.get('ffprobepath'),
        ShareMappings=MountMap,
    )
    LoggingService.LogInfo(
        f"Harness initialized WorkerContext for {WorkerName}: "
        f"FFmpegPath={R.get('ffmpegpath')!r}, "
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
            f"QueueId={C.get('queueid')} ActiveJobId={C.get('activejobid')} "
            f"Worker={C.get('workername')!r}"
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
        "SELECT StorageRootId, RelativePath, FilePath, FileName, SizeBytes, "
        "SizeMB, AssignedProfile, PriorityScore "
        "FROM MediaFiles WHERE Id = %s",
        (MediaFileId,),
    )
    if not Rows:
        raise ValueError(f"MediaFile {MediaFileId} not found")
    M = dict(Rows[0])
    Now = datetime.now(timezone.utc)
    InsertResult = Db.ExecuteQuery(
        """
        INSERT INTO TranscodeQueue
          (StorageRootId, RelativePath, FilePath, FileName, Directory,
           SizeBytes, SizeMB, Priority, Status, DateAdded,
           ProcessingMode, MediaFileId, AssignedProfile)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING Id
        """,
        (
            M.get('storagerootid'),
            M.get('relativepath') or '',
            M.get('filepath'),
            M.get('filename'),
            os.path.dirname(M.get('filepath') or ''),
            M.get('sizebytes') or 0,
            M.get('sizemb') or 0.0,
            int(M.get('priorityscore') or 0),
            'Pending',
            Now,
            ProcessingMode,
            MediaFileId,
            M.get('assignedprofile') or '',
        ),
    )
    QueueId = int(dict(InsertResult[0])['id'])
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
        "SELECT Id, StorageRootId, RelativePath, FilePath, FileName, Directory, "
        "SizeBytes, SizeMB, Priority, Status, AssignedProfile, ProcessingMode, "
        "MediaFileId, DateAdded, DateStarted "
        "FROM TranscodeQueue WHERE Id = %s",
        (QueueId,),
    )
    if not Rows:
        raise RuntimeError(f"Queue row {QueueId} disappeared after insert")
    R = dict(Rows[0])
    return TranscodeQueueModel(
        Id=R.get('id'),
        StorageRootId=R.get('storagerootid'),
        RelativePath=R.get('relativepath') or '',
        FilePath=R.get('filepath') or '',
        FileName=R.get('filename') or '',
        Directory=R.get('directory') or '',
        SizeBytes=R.get('sizebytes') or 0,
        SizeMB=R.get('sizemb') or 0.0,
        Priority=R.get('priority') or 0,
        Status=R.get('status') or 'Pending',
        AssignedProfile=R.get('assignedprofile') or '',
        ProcessingMode=R.get('processingmode') or 'Transcode',
        MediaFileId=R.get('mediafileid'),
        DateAdded=R.get('dateadded'),
        DateStarted=R.get('datestarted'),
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
    return int(dict(Rows[0])['id'])


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
