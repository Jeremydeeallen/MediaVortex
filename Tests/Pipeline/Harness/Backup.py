from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path as _SpoolPath
from typing import Any, Dict, List

from Core.Database.DatabaseService import DatabaseService
from Core.Logging.LoggingService import LoggingService
from Core.Path.LocalPath import LocalBasename, LocalDirname, LocalExists, LocalIsDir, LocalJoin, LocalSplitExt
from Tests.Pipeline.Harness.HarnessPathResolver import ResolveLocalPathForMediaFile


BACKUP_ROOT = _SpoolPath(__file__).resolve().parent.parent / '_backup'


_RELATED_TABLES = (
    ('TranscodeAttempts', 'MediaFileId'),
    ('TranscodeQueue', 'MediaFileId'),
)


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
@dataclass
class BackupHandle:
    """One MediaFile's recovery anchor -- file copy + DB row snapshot; see pipeline-test-harness.feature.md S4."""
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


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def _Sha256OfFile(LocalPath: str) -> str:
    """SHA-256 hex digest of file content."""
    H = hashlib.sha256()
    with open(LocalPath, 'rb') as F:
        for Chunk in iter(lambda: F.read(1024 * 1024), b''):
            H.update(Chunk)
    return H.hexdigest()


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def _Stringify(Row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert non-JSON-native row values (datetime, Decimal) to strings."""
    Result: Dict[str, Any] = {}
    for Key, Val in Row.items():
        if isinstance(Val, datetime):
            Result[Key] = Val.isoformat()
        elif hasattr(Val, '__class__') and Val.__class__.__name__ == 'Decimal':
            Result[Key] = float(Val)
        else:
            Result[Key] = Val
    return Result


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def BackupMediaFile(MediaFileId: int) -> BackupHandle:
    """Capture file content + all related DB rows for MediaFileId; spools under Tests/Pipeline/_backup/."""
    Db = DatabaseService()
    Rows = Db.ExecuteQuery("SELECT * FROM MediaFiles WHERE Id = %s", (MediaFileId,))
    if not Rows:
        raise ValueError(f"MediaFile {MediaFileId} not found")
    MediaFileRow = _Stringify(dict(Rows[0]))
    CanonicalPath = MediaFileRow.get('FilePath') or MediaFileRow.get('filepath') or ''
    LocalPath = ResolveLocalPathForMediaFile(MediaFileId, Db)
    if not LocalPath or not LocalExists(LocalPath):
        raise FileNotFoundError(f"MediaFile {MediaFileId} local path {LocalPath!r} does not exist; cannot back up. (Canonical: {CanonicalPath!r})")

    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    Stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    BackupFile = BACKUP_ROOT / f"{MediaFileId}-{Stamp}.bin"
    MetadataJson = BACKUP_ROOT / f"{MediaFileId}-{Stamp}.json"

    LoggingService.LogInfo(f"Backing up MediaFile {MediaFileId}: {LocalPath} -> {BackupFile}", "Backup", "BackupMediaFile")
    Swept = _SweepPostTestArtifacts(LocalPath)
    if Swept > 0:
        LoggingService.LogInfo(f"Pre-backup sweep removed {Swept} stale artifact(s) for {LocalPath}", "Backup", "BackupMediaFile")
    shutil.copy2(LocalPath, BackupFile)
    Sha = _Sha256OfFile(str(BackupFile))
    Size = os.path.getsize(BackupFile)

    Related: Dict[str, List[Dict[str, Any]]] = {}
    for TableName, KeyCol in _RELATED_TABLES:
        QRows = Db.ExecuteQuery(f"SELECT * FROM {TableName} WHERE {KeyCol} = %s", (MediaFileId,))
        Related[TableName] = [_Stringify(dict(R)) for R in QRows]

    AttemptIds = [int(R['id']) for R in Related.get('TranscodeAttempts', [])]
    if AttemptIds:
        PH = ','.join(['%s'] * len(AttemptIds))
        Related['TemporaryFilePaths'] = [
            _Stringify(dict(R))
            for R in Db.ExecuteQuery(f"SELECT * FROM TemporaryFilePaths WHERE TranscodeAttemptId IN ({PH})", tuple(AttemptIds))
        ]
        Related['MediaFilesArchive'] = [
            _Stringify(dict(R))
            for R in Db.ExecuteQuery(f"SELECT * FROM MediaFilesArchive WHERE TranscodeAttemptId IN ({PH})", tuple(AttemptIds))
        ]
    else:
        Related['TemporaryFilePaths'] = []
        Related['MediaFilesArchive'] = []

    QueueIds = [int(R['id']) for R in Related.get('TranscodeQueue', [])]
    if QueueIds:
        PH = ','.join(['%s'] * len(QueueIds))
        Related['ActiveJobs'] = [
            _Stringify(dict(R))
            for R in Db.ExecuteQuery(f"SELECT * FROM ActiveJobs WHERE QueueId IN ({PH})", tuple(QueueIds))
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

    LoggingService.LogInfo(f"Backup complete: file_sha={Sha[:12]} size={Size:,} related_rows={sum(len(v) for v in Related.values())}", "Backup", "BackupMediaFile")
    return Handle


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def LoadBackupHandle(MetadataJsonPath: str) -> BackupHandle:
    """Recover a BackupHandle from its on-disk JSON (for crash recovery)."""
    with open(MetadataJsonPath, 'r', encoding='utf-8') as F:
        Data = json.load(F)
    return BackupHandle(**Data)


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def _ReinsertRow(Db: DatabaseService, TableName: str, Row: Dict[str, Any]) -> None:
    """Insert a single captured row back into its table; column names case-fold via psycopg2."""
    if not Row:
        return
    Cols = list(Row.keys())
    Placeholders = ','.join(['%s'] * len(Cols))
    ColList = ','.join(Cols)
    Values = tuple(Row[C] for C in Cols)
    Db.ExecuteNonQuery(f"INSERT INTO {TableName} ({ColList}) VALUES ({Placeholders})", Values)


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def _DeleteCurrentRowsFor(Db: DatabaseService, MediaFileId: int) -> None:
    """Wipe rows the test added/mutated before reinserting the backup (FK-safe child-then-parent order)."""
    Db.ExecuteNonQuery("DELETE FROM ActiveJobs WHERE QueueId IN (SELECT Id FROM TranscodeQueue WHERE MediaFileId = %s)", (MediaFileId,))
    Db.ExecuteNonQuery("DELETE FROM TemporaryFilePaths WHERE TranscodeAttemptId IN (SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s)", (MediaFileId,))
    Db.ExecuteNonQuery("DELETE FROM MediaFilesArchive WHERE TranscodeAttemptId IN (SELECT Id FROM TranscodeAttempts WHERE MediaFileId = %s)", (MediaFileId,))
    Db.ExecuteNonQuery("DELETE FROM TranscodeQueue WHERE MediaFileId = %s", (MediaFileId,))
    Db.ExecuteNonQuery("DELETE FROM TranscodeAttempts WHERE MediaFileId = %s", (MediaFileId,))


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def _ParseTimestamps(Row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert ISO-string timestamps back to datetime for insert; pg accepts ISO strings but parsed is more robust."""
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


_RES_TAG_RE = re.compile(r'-\d+p$', re.IGNORECASE)


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def _SweepPostTestArtifacts(OriginalLocalPath: str) -> int:
    """Delete same-dir files matching post-pipeline naming (-mv*.mp4, .inprogress, -mv-thumb.jpg); preserves original + non-mv sidecars."""
    Dir = LocalDirname(OriginalLocalPath)
    OriginalBase = LocalBasename(OriginalLocalPath)
    Stem, _OriginalExt = LocalSplitExt(OriginalBase)
    ResolutionFreeStem = _RES_TAG_RE.sub('', Stem)
    if not LocalIsDir(Dir):
        return 0
    Removed = 0
    for Entry in os.listdir(Dir):
        if Entry == OriginalBase:
            continue
        EntryStem, _EntryExt = LocalSplitExt(Entry)
        if not EntryStem.startswith(ResolutionFreeStem):
            continue
        Tail = Entry[len(ResolutionFreeStem):]
        if '-mv' in Tail or Tail.endswith('.inprogress'):
            Full = LocalJoin(Dir, Entry)
            try:
                os.remove(Full)
                Removed += 1
                LoggingService.LogInfo(f"Swept post-test artifact: {Full}", "Backup", "_SweepPostTestArtifacts")
            except OSError as Ex:
                LoggingService.LogWarning(f"Could not sweep {Full}: {Ex}", "Backup", "_SweepPostTestArtifacts")
    return Removed


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def RestoreMediaFile(Handle: BackupHandle) -> None:
    """Replay the backup: sweep -mv* siblings, restore the file, wipe test-added rows, UPDATE MediaFiles to captured state, re-INSERT related rows."""
    if not LocalExists(Handle.LocalBackupFilePath):
        raise FileNotFoundError(f"Backup file missing: {Handle.LocalBackupFilePath}. Cannot restore MediaFile {Handle.MediaFileId} without it.")

    LoggingService.LogInfo(f"Restoring MediaFile {Handle.MediaFileId} from {Handle.LocalBackupFilePath}", "Backup", "RestoreMediaFile")

    _SweepPostTestArtifacts(Handle.OriginalLocalPath)

    os.makedirs(LocalDirname(Handle.OriginalLocalPath), exist_ok=True)
    shutil.copy2(Handle.LocalBackupFilePath, Handle.OriginalLocalPath)
    PostSha = _Sha256OfFile(Handle.OriginalLocalPath)
    if PostSha != Handle.OriginalSha256:
        raise RuntimeError(f"Restore checksum mismatch: expected {Handle.OriginalSha256[:12]}, got {PostSha[:12]}. File at {Handle.OriginalLocalPath} is corrupt.")

    Db = DatabaseService()
    _DeleteCurrentRowsFor(Db, Handle.MediaFileId)

    MfRow = _ParseTimestamps(Handle.MediaFileRow)
    _GENERATED_COLUMNS = {'workbucket', 'iscompliant'}
    SetCols = [C for C in MfRow.keys() if C.lower() != 'id' and C.lower() not in _GENERATED_COLUMNS]
    SetClause = ', '.join(f"{C} = %s" for C in SetCols)
    Values = tuple(MfRow[C] for C in SetCols) + (Handle.MediaFileId,)
    Db.ExecuteNonQuery(f"UPDATE MediaFiles SET {SetClause} WHERE Id = %s", Values)

    for TableName in ('TranscodeAttempts', 'TranscodeQueue', 'MediaFilesArchive'):
        for Row in Handle.RelatedRows.get(TableName, []):
            _ReinsertRow(Db, TableName, _ParseTimestamps(Row))
    for Row in Handle.RelatedRows.get('TemporaryFilePaths', []):
        _ReinsertRow(Db, 'TemporaryFilePaths', _ParseTimestamps(Row))
    for Row in Handle.RelatedRows.get('ActiveJobs', []):
        _ReinsertRow(Db, 'ActiveJobs', _ParseTimestamps(Row))

    LoggingService.LogInfo(f"Restore complete for MediaFile {Handle.MediaFileId}", "Backup", "RestoreMediaFile")


# directive: compliance-solid-refactor | # see compliance-solid-refactor.C15
def DiscardBackup(Handle: BackupHandle) -> None:
    """Optional cleanup: remove the on-disk backup spool for a successfully-restored handle."""
    for P in (Handle.LocalBackupFilePath, Handle.MetadataJsonPath):
        try:
            if LocalExists(P):
                os.remove(P)
        except OSError as Ex:
            LoggingService.LogWarning(f"Could not remove backup artifact {P}: {Ex}", "Backup", "DiscardBackup")
