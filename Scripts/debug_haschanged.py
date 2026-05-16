"""One-off debug: empirically test what HasFileChanged returns for a known-unchanged row."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Features.FileScanning.FileScanningRepository import FileScanningRepository
from Features.FileScanning.FileScanningBusinessService import FileScanningBusinessService

ROOT = 'M:' + chr(92)
TARGET_ID = 618463

Repo = FileScanningRepository()
Svc = FileScanningBusinessService(Repo)

rows = Repo.GetMediaFilesByRootFolder(ROOT)
target = [r for r in rows if r.Id == TARGET_ID][0]

print('=== DB row (Python objects) ===')
print(f'  Id:                   {target.Id}')
print(f'  FileName:             {target.FileName!r}')
print(f'  SizeMB:               {target.SizeMB!r} (type={type(target.SizeMB).__name__})')
print(f'  FileModificationTime: {target.FileModificationTime!r} (type={type(target.FileModificationTime).__name__})')
if hasattr(target.FileModificationTime, 'tzinfo'):
    print(f'  ^^ tzinfo:            {target.FileModificationTime.tzinfo!r}')

LocalPath = (r'M:' + chr(92) + r'Captain America The Winter Soldier (2014)' +
             chr(92) + r'Captain America The Winter Soldier (2014) Bluray-720p.mp4')

print()
print('=== Computed via NEW code (what I9 should now see) ===')
CurFileSizeMB = Svc.FileManager.GetFileSizeMB(LocalPath)
CurFileName = Svc.FileManager.GetFileNameFromPath(LocalPath)
CurFileMtime = Svc.GetFileModificationTime(LocalPath)
print(f'  SizeMB:               {CurFileSizeMB!r} (type={type(CurFileSizeMB).__name__})')
print(f'  FileName:             {CurFileName!r}')
print(f'  FileModificationTime: {CurFileMtime!r} (type={type(CurFileMtime).__name__})')
if hasattr(CurFileMtime, 'tzinfo'):
    print(f'  ^^ tzinfo:            {CurFileMtime.tzinfo!r}')

print()
print('=== Per-field comparison ===')
print(f'  SizeMB: stored={target.SizeMB} current={CurFileSizeMB} delta={abs(CurFileSizeMB - target.SizeMB)} -> SizeChanged={abs(CurFileSizeMB - target.SizeMB) > 0.1}')
print(f'  FileName equal? {CurFileName == target.FileName}')
if target.FileModificationTime and CurFileMtime:
    try:
        delta = abs((CurFileMtime - target.FileModificationTime).total_seconds())
        print(f'  Mtime delta:    {delta}s -> Changed={delta > 1.0}')
    except Exception as e:
        print(f'  Mtime subtract failed: {type(e).__name__}: {e}')

print()
print('=== HasFileChanged verdict ===')
verdict = Svc.HasFileChanged(target, CurFileSizeMB, CurFileName, CurFileMtime)
print(f'  HasFileChanged: {verdict}')
