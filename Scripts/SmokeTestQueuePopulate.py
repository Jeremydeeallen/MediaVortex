"""Smoke test for the optimized queue population queries."""
import sys
sys.path.insert(0, '.')
import time
from Core.Database.DatabaseService import DatabaseService, EscapeLikePattern

DB = DatabaseService()

# Test 1: GetMkvFilesForRemux equivalent
t0 = time.time()
Rows = DB.ExecuteQuery(
    "SELECT Id, StorageRootId, RelativePath, FilePath, FileName, SizeMB, "
    "DurationMinutes, Resolution, Codec, ContainerFormat "
    "FROM MediaFiles WHERE LOWER(FileName) LIKE %s "
    "ORDER BY SizeMB DESC NULLS LAST",
    ('%.mkv',)
)
t1 = time.time()
print(f"MKV files: {len(Rows)} rows in {t1-t0:.3f}s")
if Rows:
    print(f"  First: {Rows[0]['FileName']} ({Rows[0]['SizeMB']:.0f}MB)")

# Test 2: GetMediaFilesWithProfilesOrderedBySize equivalent
t0 = time.time()
Rows2 = DB.ExecuteQuery(
    "SELECT Id, FilePath, FileName, SizeMB, AssignedProfile, "
    "HasExplicitEnglishAudio, AudioLanguages "
    "FROM MediaFiles "
    "WHERE AssignedProfile IS NOT NULL AND TRIM(AssignedProfile) != '' "
    "ORDER BY SizeMB DESC NULLS LAST LIMIT 5"
)
t1 = time.time()
print(f"Files with profiles: query in {t1-t0:.3f}s")
for R in Rows2:
    print(f"  {R['FileName']} profile={R['AssignedProfile']} audio={R['HasExplicitEnglishAudio']}")

# Test 3: GetExistingQueueFilePaths equivalent
t0 = time.time()
Rows3 = DB.ExecuteQuery("SELECT FilePath FROM TranscodeQueue")
Paths3 = {R.get('FilePath', '') for R in Rows3}
t1 = time.time()
print(f"Queue paths: {len(Paths3)} rows in {t1-t0:.3f}s")

# Test 4: Successfully transcoded paths
t0 = time.time()
Rows4 = DB.ExecuteQuery(
    "SELECT FilePath FROM TranscodeFiles WHERE SuccessfullyTranscoded = true"
)
Paths4 = {R.get('FilePath', '') for R in Rows4}
t1 = time.time()
print(f"Transcoded paths: {len(Paths4)} rows in {t1-t0:.3f}s")

# Test 5: Bulk MediaFileId lookup (simulating BulkInsertQueueItems)
if len(Rows) >= 3:
    TestPaths = [R['FilePath'] for R in Rows[:3]]
    t0 = time.time()
    Rows5 = DB.ExecuteQuery(
        "SELECT Id, FilePath FROM MediaFiles WHERE FilePath IN %s",
        (tuple(TestPaths),)
    )
    t1 = time.time()
    print(f"Bulk MediaFileId lookup ({len(TestPaths)} paths): {len(Rows5)} found in {t1-t0:.3f}s")

# Test 6: Full end-to-end PopulateQueueForRemux
print("\n--- Full PopulateQueueForRemux test (dry) ---")
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
Svc = QueueManagementBusinessService()

t0 = time.time()
MkvFiles = Svc.GetMkvFilesForRemux()
t1 = time.time()
print(f"GetMkvFilesForRemux: {len(MkvFiles)} files in {t1-t0:.3f}s")

from Features.TranscodeQueue.TranscodeQueueRepository import TranscodeQueueRepository
Repo = TranscodeQueueRepository()
t0 = time.time()
ExistingPaths = Repo.GetExistingQueueFilePaths()
t1 = time.time()
print(f"GetExistingQueueFilePaths: {len(ExistingPaths)} paths in {t1-t0:.3f}s")

NewCount = sum(1 for mf in MkvFiles if mf.FilePath not in ExistingPaths)
print(f"Would add: {NewCount} new items (skipping {len(MkvFiles) - NewCount} already in queue)")

print("\nAll smoke tests passed.")
