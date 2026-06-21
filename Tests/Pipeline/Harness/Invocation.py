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
    WorkerContext.Initialize(
        WorkerName=WorkerName,
        Platform=R.get('Platform') or 'windows',
        FFmpegPath=R.get('FFmpegPath'),
        FFprobePath=R.get('FFprobePath'),
    )
    LoggingService.LogInfo(
        f"Harness initialized WorkerContext for {WorkerName}: FFmpegPath={R.get('FFmpegPath')!r}",
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
        "SELECT StorageRootId, RelativePath, FileName, FileSize AS SizeBytes, "
        "SizeMB, AssignedProfile, PriorityScore "
        "FROM MediaFiles WHERE Id = %s",
        (MediaFileId,),
    )
    if not Rows:
        raise ValueError(f"MediaFile {MediaFileId} not found")
    M = Rows[0]
    _PrefixMap = {int(R['Id']): R['CanonicalPrefix'] for R in Db.ExecuteQuery("SELECT Id, CanonicalPrefix FROM StorageRoots")}
    _Sid = M.get('StorageRootId')
    _Rel = (M.get('RelativePath') or '').replace('/', '\\')
    _SynthesizedFilePath = (_PrefixMap.get(int(_Sid), '') + _Rel) if _Sid is not None else ''
    M = dict(M)
    M['FilePath'] = _SynthesizedFilePath

    from Core.Path.LocalPath import LocalExists, LocalGetSize
    SizeBytes = int(M.get('SizeBytes') or 0)
    SizeMB = float(M.get('SizeMB') or 0.0)
    if SizeBytes <= 0:
        if LocalExists(_SynthesizedFilePath):
            SizeBytes = LocalGetSize(_SynthesizedFilePath)
        elif SizeMB > 0:
            SizeBytes = int(SizeMB * 1024 * 1024)
    if SizeMB <= 0 and SizeBytes > 0:
        SizeMB = SizeBytes / 1024.0 / 1024.0

    Now = datetime.now(timezone.utc)
    # Use ExecuteNonQuery so the INSERT commits; ExecuteQuery does not commit
    # and the RETURNING row would be rolled back on connection close.
    Db.ExecuteNonQuery(
        "INSERT INTO TranscodeQueue "
        "(StorageRootId, RelativePath, FileName, Directory, "
        "SizeBytes, SizeMB, Priority, Status, DateAdded, ProcessingMode, MediaFileId) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING Id",
        (
            M.get('StorageRootId'),
            M.get('RelativePath') or '',
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


# directive: path-schema-migration | # see path.S8
def _LoadQueueModel(QueueId: int):
    """Load the TranscodeQueueModel for a freshly-inserted row."""
    from Features.TranscodeQueue.Models.TranscodeQueueModel import TranscodeQueueModel
    Db = DatabaseService()
    Rows = Db.ExecuteQuery(
        "SELECT q.Id, q.StorageRootId, q.RelativePath, q.FileName, q.Directory, "
        "q.SizeBytes, q.SizeMB, q.Priority, q.Status, m.AssignedProfile, q.ProcessingMode, "
        "q.MediaFileId, q.DateAdded, q.DateStarted "
        "FROM TranscodeQueue q LEFT JOIN MediaFiles m ON m.Id = q.MediaFileId "
        "WHERE q.Id = %s",
        (QueueId,),
    )
    if not Rows:
        raise RuntimeError(f"Queue row {QueueId} disappeared after insert")
    R = Rows[0]
    return TranscodeQueueModel(
        Id=R.get('Id'),
        StorageRootId=R.get('StorageRootId'),
        RelativePath=R.get('RelativePath') or '',
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


def _Invoke(MediaFileId: int, ProcessingMode: str, TimeoutSec: int = 900) -> int:
    """Enqueue + wait for a real worker to claim + complete. Returns the TranscodeAttempt Id."""
    _EnsureWorkerContext()
    _AssertNoActiveWork(MediaFileId)

    SinceTs = time.time()
    QueueId = _InsertQueueRow(MediaFileId, ProcessingMode)
    LoggingService.LogInfo(f"Harness enqueued QueueId={QueueId}; polling for worker pickup", "Invocation", "_Invoke")

    Db = DatabaseService()
    Deadline = time.time() + TimeoutSec
    AttemptId = None
    NoReplaceDispositions = {'Discard', 'NoReplace'}
    while time.time() < Deadline:
        AttemptId = _FindLatestAttemptId(MediaFileId, SinceTs)
        if AttemptId is not None:
            Rows = Db.ExecuteQuery("SELECT Success, ErrorMessage, Disposition, DispositionReason, FileReplaced, TranscodeDurationSeconds, WorkerName FROM TranscodeAttempts WHERE Id = %s", (AttemptId,))
            if Rows:
                R = Rows[0]
                if R.get('Success') is False:
                    raise RuntimeError(f"TranscodeAttempt {AttemptId} for MediaFile {MediaFileId} completed with Success=False. ErrorMessage={R.get('ErrorMessage')!r} Disposition={R.get('Disposition')!r} DispositionReason={R.get('DispositionReason')!r}")
                Disp = R.get('Disposition')
                Replaced = R.get('FileReplaced')
                if R.get('Success') is True and (Replaced is True or Disp in NoReplaceDispositions):
                    Msg = f"Harness saw terminal AttemptId={AttemptId} Success={R['Success']} Disposition={Disp!r} DispositionReason={R.get('DispositionReason')!r} FileReplaced={Replaced!r} Worker={R.get('WorkerName')!r} Dur={R.get('TranscodeDurationSeconds')!r}s"
                    LoggingService.LogInfo(Msg, "Invocation", "_Invoke")
                    print(f"\n[HARNESS] {Msg}", flush=True)
                    return AttemptId
        time.sleep(3)
    Last = None
    if AttemptId is not None:
        Rows = Db.ExecuteQuery("SELECT Success, Disposition, DispositionReason FROM TranscodeAttempts WHERE Id = %s", (AttemptId,))
        Last = Rows[0] if Rows else None
    raise TimeoutError(f"No terminal-disposition TranscodeAttempt for MediaFile {MediaFileId} after {TimeoutSec}s. AttemptId observed: {AttemptId}. Last seen: {Last!r}. VMAF worker may be stuck or QualityTesting disabled inconsistently.")


def GetAttemptDetails(AttemptId: int) -> dict:
    """Return Disposition/Reason/FileReplaced/etc for a completed attempt; tests branch on this rather than assuming a codec change."""
    Db = DatabaseService()
    Rows = Db.ExecuteQuery("SELECT Success, Disposition, DispositionReason, FileReplaced, ErrorMessage, WorkerName, TranscodeDurationSeconds FROM TranscodeAttempts WHERE Id = %s", (AttemptId,))
    if not Rows:
        raise ValueError(f"TranscodeAttempt {AttemptId} not found")
    return dict(Rows[0])


def WaitForLocalFile(LocalPath: str, TimeoutSec: int = 30) -> None:
    """Poll until the local file exists on disk; cross-host writes via NFS may take a moment to land on the harness host's SMB mount."""
    from Core.Path.LocalPath import LocalExists
    Deadline = time.time() + TimeoutSec
    while time.time() < Deadline:
        if LocalExists(LocalPath):
            return
        time.sleep(1)
    raise AssertionError(f"File did not become visible to harness host within {TimeoutSec}s: {LocalPath}")


def InvokeQuickFix(MediaFileId: int) -> int:
    """Run Quick Fix (Remux + audio normalize) synchronously. Returns attempt Id."""
    return _Invoke(MediaFileId, 'Quick')


def InvokeTranscode(MediaFileId: int) -> int:
    """Run Transcode (full video re-encode) synchronously. Returns attempt Id."""
    return _Invoke(MediaFileId, 'Transcode')
