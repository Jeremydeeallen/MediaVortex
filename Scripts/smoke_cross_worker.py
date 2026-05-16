"""Cross-worker smoke test for criterion 26: verify two workers compute IDENTICAL
values for the same file given a canonical FilePath. Run on each worker; emit
JSON for character-by-character comparison.
"""
import sys
import os
import socket
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Core.PathStorage import LoadStorageRoots, Parse as PathParse
from Features.FileScanning.FileScanningRepository import FileScanningRepository
from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService

CANONICAL_FILEPATH = 'T:' + chr(92) + '8 Minute Ab workout.mkv'

Repo = FileScanningRepository()
Svc = FileScanningBusinessService(Repo)

# Resolve canonical -> local for this worker
StorageRoots = LoadStorageRoots()
Sid, Rel = PathParse(CANONICAL_FILEPATH, StorageRoots)
WorkerName = socket.gethostname()

Resolutions = Repo.DatabaseService.ExecuteQuery(
    "SELECT AbsolutePath FROM StorageRootResolutions WHERE StorageRootId=%s AND WorkerName=%s AND IsActive=TRUE LIMIT 1",
    (Sid, WorkerName),
)
LocalRoot = Resolutions[0]['AbsolutePath']
LocalPath = os.path.join(LocalRoot, Rel.replace('/', os.sep))

# Compute the three fields HasFileChanged compares
SizeMB = Svc.FileManager.GetFileSizeMB(LocalPath)
FileName = Svc.FileManager.GetFileNameFromPath(CANONICAL_FILEPATH)
FileModTime = Svc.GetFileModificationTime(LocalPath)

# Also compute POSIX timestamp so we can compare byte-level
PosixMtime = os.path.getmtime(LocalPath)
FileSize = os.path.getsize(LocalPath)

out = {
    'worker_name': WorkerName,
    'system': sys.platform,
    'tzname': __import__('time').tzname,
    'canonical_filepath': CANONICAL_FILEPATH,
    'local_root': LocalRoot,
    'local_path': LocalPath,
    'size_bytes': FileSize,
    'size_mb_str': repr(SizeMB),
    'filename_repr': repr(FileName),
    'mtime_posix': PosixMtime,
    'mtime_naive_utc_repr': repr(FileModTime),
    'mtime_naive_utc_iso': FileModTime.isoformat() if FileModTime else None,
}
print(json.dumps(out, indent=2))
