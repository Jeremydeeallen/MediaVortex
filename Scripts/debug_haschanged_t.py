"""Debug: test HasFileChanged for the T:\30 Rock S01E01 row."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Features.FileScanning.FileScanningRepository import FileScanningRepository
from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService

Repo = FileScanningRepository()
Svc = FileScanningBusinessService(Repo)

# Find the 30 Rock S01E01 row by FilePath
DbResult = Repo.DatabaseService.ExecuteQuery(
    "SELECT Id, FilePath FROM MediaFiles WHERE FilePath ILIKE %s AND FilePath LIKE %s LIMIT 1",
    ('%30 Rock%S01E01%', 'T:%')
)
TARGET_ID = DbResult[0]['Id']
target_filepath = DbResult[0]['FilePath']

rows = Repo.GetMediaFilesByRootFolder('T:' + chr(92))
target = [r for r in rows if r.Id == TARGET_ID][0]

print(f'Row Id {TARGET_ID}: {target_filepath!r}')
print()
print('=== DB row ===')
print(f'  FileName:             {target.FileName!r}')
print(f'  SizeMB:               {target.SizeMB!r}')
print(f'  FileModificationTime: {target.FileModificationTime!r} tz={getattr(target.FileModificationTime,"tzinfo",None)}')

LocalPath = target_filepath

print()
print('=== Computed via NEW code ===')
try:
    CurFileSizeMB = Svc.FileManager.GetFileSizeMB(LocalPath)
    CurFileName = Svc.FileManager.GetFileNameFromPath(LocalPath)
    CurFileMtime = Svc.GetFileModificationTime(LocalPath)
    print(f'  SizeMB:               {CurFileSizeMB!r}')
    print(f'  FileName:             {CurFileName!r}')
    print(f'  FileModificationTime: {CurFileMtime!r} tz={getattr(CurFileMtime,"tzinfo",None)}')
except Exception as e:
    print(f'  ERROR: {type(e).__name__}: {e}')
    sys.exit(2)

print()
print('=== Comparison ===')
print(f'  SizeMB delta:   {abs(CurFileSizeMB - target.SizeMB)} -> SizeChanged={abs(CurFileSizeMB - target.SizeMB) > 0.1}')
print(f'  FileName equal: {CurFileName == target.FileName}')
try:
    delta = abs((CurFileMtime - target.FileModificationTime).total_seconds())
    print(f'  Mtime delta:    {delta}s -> Changed={delta > 1.0}')
except Exception as e:
    print(f'  Mtime subtract failed: {type(e).__name__}: {e}')

print()
print('=== HasFileChanged ===')
print(f'  Verdict: {Svc.HasFileChanged(target, CurFileSizeMB, CurFileName, CurFileMtime)}')
