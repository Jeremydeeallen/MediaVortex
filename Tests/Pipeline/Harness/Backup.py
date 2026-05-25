"""File + DB row backup and restore for the pipeline test harness.

Captures a MediaFile and every related DB row before a test mutates them;
restores all of it on success or failure. The on-disk backup file is the
recovery anchor -- if a hard crash leaves the test halfway through, the
backup file is still on disk and `RestoreMediaFile` can be replayed.

See Tests/Pipeline/pipeline-test-harness.feature.md criteria 1-3.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService


BACKUP_ROOT = Path(__file__).resolve().parent.parent / '_backup'


# Tables touched by a Quick Fix / Transcode pipeline run. For each table the
# backup captures every row keyed to the MediaFileId; restore wipes any rows
# the test added and re-inserts the captured rows.
_RELATED_TABLES = (
    # (table_name, predicate_column, optional extra row-key for ordering)
    ('TranscodeAttempts', 'MediaFileId'),
    ('TranscodeQueue', 'MediaFileId'),
    # MediaFilesArchive joins via TranscodeAttemptId -- handled specially after TA is captured.
    # TemporaryFilePaths also joins via TranscodeAttemptId -- handled specially.
    # ActiveJobs joins via TranscodeQueue.Id -- handled specially.
)


@dataclass
class BackupHandle:
    """The unit of recovery for one MediaFile under test.

    On-disk artifacts:
      - LocalBackupFilePath: byte-for-byte copy of the original file
      - MetadataJsonPath:    captured DB rows as JSON

    DB snapshots (in-memory mirror of the JSON):
      - MediaFileRow: the single MediaFiles row
      - RelatedRows: {table_name: [row dicts]} for each related table
    """
    MediaFileId: int
    CapturedAt: str
    OriginalCanonicalPath: str
    OriginalLocalPath: str
    LocalBackupFilePath: str
    MetadataJsonPath: str
    OriginalSha256: str
    OriginalSizeBytes: int
    MediaFileRow: Dict[str, Any] = field(default_factory=dict)
    RelatedRows: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)


def _Sha256OfFile(LocalPath: str) -> str:
    H = hashlib.sha256()
    with open(LocalPath, 'rb') as F:
        for Chunk in iter(lambda: F.read(1024 * 1024), b''):
            H.update(Chunk)
    return H.hexdigest()


def _Stringify(Row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert non-JSON-native types (datetime, Decimal) to strings."""
    Result: Dict[str, Any] = {}
    for Key, Val in Row.items():
        if isinstance(Val, datetime):
            Result[Key] = Val.isoformat()
        elif hasattr(Val, '__class__') and Val.__class__.__name__ == 'Decimal':
            Result[Key] = float(Val)
        else:
            Result[Key] = Val
    return Result


def _ResolveLocalPath(CanonicalPath: str) -> str:
    """Translate a canonical DB path to the I9's local view via WorkerContext."""
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
        pass
    return CanonicalPath


def BackupMediaFile(MediaFileId: int) -> BackupHandle:
    """Capture file content + all related DB rows for `MediaFileId`.

    The on-disk backup lives under `Tests/Pipeline/_backup/<id>-<timestamp>.bin`
    with a sibling `.json` holding the DB snapshot.
    """
    Db = DatabaseService()
    Rows = Db.ExecuteQuery("SELECT * FROM MediaFiles WHERE Id = %s", (MediaFileId,))
    if not Rows:
        raise ValueError(f"MediaFile {MediaFileId} not found")
    MediaFileRow = _Stringify(dict(Rows[0]))
    CanonicalPath = MediaFileRow.get('FilePath') or MediaFileRow.get('filepath')
    if not CanonicalPath:
        raise ValueError(f"MediaFile {MediaFileId} has no FilePath")
    LocalPath = _ResolveLocalPath(CanonicalPath)
    if not os.path.exists(LocalPath):
        raise FileNotFoundError(
            f"MediaFile {MediaFileId} local path {LocalPath!r} does not exist; "
            f"cannot back up. (Canonical: {CanonicalPath!r})"
        )

    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    Stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    BackupFile = BACKUP_ROOT / f"{MediaFileId}-{Stamp}.bin"
    MetadataJson = BACKUP_ROOT / f"{MediaFileId}-{Stamp}.json"

    LoggingService.LogInfo(
        f"Backing up MediaFile {MediaFileId}: {LocalPath} -> {BackupFile}",
        "Backup", "BackupMediaFile",
    )
    shutil.copy2(LocalPath, BackupFile)
    Sha = _Sha256OfFile(str(BackupFile))
    Size = os.path.getsize(BackupFile)

    Related: Dict[str, List[Dict[str, Any]]] = {}
    # Tables that key directly on MediaFileId
    for TableName, KeyCol in _RELATED_TABLES:
        QRows = Db.ExecuteQuery(
            f"SELECT * FROM {TableName} WHERE {KeyCol} = %s",
            (MediaFileId,),
        )
        Related[TableName] = [_Stringify(dict(R)) for R in QRows]

    # TemporaryFilePaths + MediaFilesArchive -- both join via TranscodeAttempts.Id
    AttemptIds = [int(R['id']) for R in Related.get('TranscodeAttempts', [])]
    if AttemptIds:
        PH = ','.join(['%s'] * len(AttemptIds))
        Related['TemporaryFilePaths'] = [
            _Stringify(dict(R))
            for R in Db.ExecuteQuery(
                f"SELECT * FROM TemporaryFilePaths WHERE TranscodeAttemptId IN ({PH})",
                tuple(AttemptIds),
            )
        ]
        Related['MediaFilesArchive'] = [
            _Stringify(dict(R))
            for R in Db.ExecuteQuery(
                f"SELECT * FROM MediaFilesArchive WHERE TranscodeAttemptId IN ({PH})",
                tuple(AttemptIds),
            )
        ]
    else:
        Related['TemporaryFilePaths'] = []
        Related['MediaFilesArchive'] = []

    # ActiveJobs -- key on any TranscodeQueue.Id we captured
    QueueIds = [int(R['id']) for R in Related.get('TranscodeQueue', [])]
    if QueueIds:
        PH = ','.join(['%s'] * len(QueueIds))
        Related['ActiveJobs'] = [
            _Stringify(dict(R))
            for R in Db.ExecuteQuery(
                f"SELECT * FROM ActiveJobs WHERE QueueId IN ({PH})",
                tuple(QueueIds),
            )
        ]
    else:
        Related['ActiveJobs'] = []

    Handle = BackupHandle(
        MediaFileId=MediaFileId,
        CapturedAt=Stamp,
        OriginalCanonicalPath=CanonicalPath,
        OriginalLocalPath=LocalPath,
        LocalBackupFilePath=str(BackupFile),
        MetadataJsonPath=str(MetadataJson),
        OriginalSha256=Sha,
        OriginalSizeBytes=Size,
        MediaFileRow=MediaFileRow,
        RelatedRows=Related,
    )

    with open(MetadataJson, 'w', encoding='utf-8') as F:
        json.dump(asdict(Handle), F, indent=2)

    LoggingService.LogInfo(
        f"Backup complete: file_sha={Sha[:12]} size={Size:,} "
        f"related_rows={sum(len(v) for v in Related.values())}",
        "Backup", "BackupMediaFile",
    )
    return Handle


def LoadBackupHandle(MetadataJsonPath: str) -> BackupHandle:
    """Recover a BackupHandle from its on-disk JSON (for crash recovery)."""
    with open(MetadataJsonPath, 'r', encoding='utf-8') as F:
        Data = json.load(F)
    return BackupHandle(**Data)


def _ReinsertRow(Db: DatabaseService, TableName: str, Row: Dict[str, Any]) -> None:
    """Insert a single captured row back into its table.

    Columns and values come from the captured dict; column names are
    quoted by PostgreSQL convention (case-folding to lowercase, which is
    how psycopg2 returns them from `SELECT *`).
    """
    if not Row:
        return
    Cols = list(Row.keys())
    Placeholders = ','.join(['%s'] * len(Cols))
    ColList = ','.join(Cols)
    Values = tuple(Row[C] for C in Cols)
    Db.ExecuteNonQuery(
        f"INSERT INTO {TableName} ({ColList}) VALUES ({Placeholders})",
        Values,
    )


def _DeleteCurrentRowsFor(Db: DatabaseService, MediaFileId: int) -> None:
    """Wipe rows the test added/mutated before reinserting the backup."""
    # Order matters: child tables before parents to avoid FK issues.
    # ActiveJobs -> TranscodeQueue (FK on QueueId)
    Db.ExecuteNonQuery(
        "DELETE FROM ActiveJobs WHERE QueueId IN "
        "(SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s)",
        (MediaFileId,),
    )
    # MediaFilesArchive + TemporaryFilePaths both key on TranscodeAttempts.Id
    Db.ExecuteNonQuery(
        "DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId IN "
        "(SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s)",
        (MediaFileId,),
    )
    Db.ExecuteNonQuery(
        "DELETE FROM MediaFilesArchive WHERE TranscodeAttemptId IN "
        "(SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s)",
        (MediaFileId,),
    )
    Db.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE MediaFileId = %s", (MediaFileId,))
    Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE MediaFileId = %s", (MediaFileId,))


def _ParseTimestamps(Row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert ISO-string timestamps back to datetime for insert.

    JSON serialization replaced datetimes with strings; psycopg2 will
    accept ISO strings for TIMESTAMP columns, but parsing them to
    datetime is more robust against PG version quirks.
    """
    Out: Dict[str, Any] = {}
    for Key, Val in Row.items():
        if isinstance(Val, str) and len(Val) >= 10 and Val[4] == '-' and Val[7] == '-':
            try:
                Out[Key] = datetime.fromisoformat(Val.replace('Z', '+00:00'))
                continue
            except (ValueError, TypeError):
                pass
        Out[Key] = Val
    return Out


def _SweepPostTestArtifacts(OriginalLocalPath: str) -> int:
    """Delete files in the same dir that match post-pipeline naming.

    After a Quick Fix the source `foo.mkv` becomes `foo-mv.mp4` (+ a
    `.inprogress` while encoding). Repeated runs can compound to
    `foo-mv-mv.mp4` etc. Leftover `.inprogress` files block the next
    encode with "Refusing to overwrite existing file at target".

    This sweep deletes any sibling that starts with the original
    basename (stem-only) and has `-mv` somewhere in its trailing
    segment, OR ends in `.inprogress`. Does NOT touch the original
    file or its sidecars (.nfo, -thumb.jpg).
    """
    Dir = os.path.dirname(OriginalLocalPath)
    OriginalBase = os.path.basename(OriginalLocalPath)
    Stem, OriginalExt = os.path.splitext(OriginalBase)
    if not os.path.isdir(Dir):
        return 0
    Removed = 0
    for Entry in os.listdir(Dir):
        if Entry == OriginalBase:
            continue  # never touch the original itself
        if not Entry.startswith(Stem):
            continue
        Tail = Entry[len(Stem):]
        # `-mv*.mp4`, `-mv*.mp4.inprogress`, etc.
        if '-mv' in Tail or Tail.endswith('.inprogress'):
            Full = os.path.join(Dir, Entry)
            try:
                os.remove(Full)
                Removed += 1
                LoggingService.LogInfo(
                    f"Swept post-test artifact: {Full}",
                    "Backup", "_SweepPostTestArtifacts",
                )
            except OSError as Ex:
                LoggingService.LogWarning(
                    f"Could not sweep {Full}: {Ex}",
                    "Backup", "_SweepPostTestArtifacts",
                )
    return Removed


def RestoreMediaFile(Handle: BackupHandle) -> None:
    """Replay the backup: file content + DB rows back to captured state.

    Steps:
      1. Sweep post-test artifacts (the test may have produced -mv.mp4
         outputs that no longer correspond to any row).
      2. Restore the file on disk (overwrite if it was renamed/replaced).
      3. Wipe any rows the test created for this MediaFile.
      4. UPDATE the MediaFiles row column-by-column to its captured values.
      5. Re-INSERT every captured related row.

    Safe to call after a partial test run -- everything is idempotent.
    Raises only if the backup files are missing or DB writes fail.
    """
    if not os.path.exists(Handle.LocalBackupFilePath):
        raise FileNotFoundError(
            f"Backup file missing: {Handle.LocalBackupFilePath}. "
            f"Cannot restore MediaFile {Handle.MediaFileId} without it."
        )

    LoggingService.LogInfo(
        f"Restoring MediaFile {Handle.MediaFileId} from {Handle.LocalBackupFilePath}",
        "Backup", "RestoreMediaFile",
    )

    # 1. Sweep any -mv* / .inprogress siblings the test produced.
    _SweepPostTestArtifacts(Handle.OriginalLocalPath)

    # 2. Restore the file at the canonical original path.
    os.makedirs(os.path.dirname(Handle.OriginalLocalPath), exist_ok=True)
    shutil.copy2(Handle.LocalBackupFilePath, Handle.OriginalLocalPath)
    PostSha = _Sha256OfFile(Handle.OriginalLocalPath)
    if PostSha != Handle.OriginalSha256:
        raise RuntimeError(
            f"Restore checksum mismatch: expected {Handle.OriginalSha256[:12]}, "
            f"got {PostSha[:12]}. File at {Handle.OriginalLocalPath} is corrupt."
        )

    Db = DatabaseService()

    # 2. Wipe rows the test added/mutated
    _DeleteCurrentRowsFor(Db, Handle.MediaFileId)

    # 3. UPDATE MediaFiles row to captured values (DELETE+INSERT would break FKs)
    MfRow = _ParseTimestamps(Handle.MediaFileRow)
    SetCols = [C for C in MfRow.keys() if C.lower() != 'id']
    SetClause = ', '.join(f"{C} = %s" for C in SetCols)
    Values = tuple(MfRow[C] for C in SetCols) + (Handle.MediaFileId,)
    Db.ExecuteNonQuery(
        f"UPDATE MediaFiles SET {SetClause} WHERE Id = %s",
        Values,
    )

    # 4. Re-insert related rows. Order matters: parents before children.
    for TableName in ('TranscodeAttempts', 'TranscodeQueue', 'MediaFilesArchive'):
        for Row in Handle.RelatedRows.get(TableName, []):
            _ReinsertRow(Db, TableName, _ParseTimestamps(Row))
    for Row in Handle.RelatedRows.get('TemporaryFilePaths', []):
        _ReinsertRow(Db, 'TemporaryFilePaths', _ParseTimestamps(Row))
    for Row in Handle.RelatedRows.get('ActiveJobs', []):
        _ReinsertRow(Db, 'ActiveJobs', _ParseTimestamps(Row))

    LoggingService.LogInfo(
        f"Restore complete for MediaFile {Handle.MediaFileId}",
        "Backup", "RestoreMediaFile",
    )


def DiscardBackup(Handle: BackupHandle) -> None:
    """Remove the on-disk backup spool for a successfully-restored handle.

    Optional cleanup. Leaves the JSON + .bin in place by default so
    failed tests retain a recovery anchor.
    """
    for P in (Handle.LocalBackupFilePath, Handle.MetadataJsonPath):
        try:
            if os.path.exists(P):
                os.remove(P)
        except OSError as Ex:
            LoggingService.LogWarning(
                f"Could not remove backup artifact {P}: {Ex}",
                "Backup", "DiscardBackup",
            )
