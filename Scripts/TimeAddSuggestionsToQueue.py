"""Time AddSuggestionsToQueue end-to-end with real data, NO INSERTS (rolled back)."""
import sys
sys.path.insert(0, '.')
import time
from Core.Database.DatabaseService import DatabaseService

DB = DatabaseService()

# Step 1: Get 250 candidate items the way SmartPopulate does
t0 = time.time()
WhereSql = """
    WHERE m.TranscodedByMediaVortex IS NOT TRUE
      AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL)
      AND m.SizeMB > 0
      AND (m.HasExplicitEnglishAudio IS NULL OR m.HasExplicitEnglishAudio = true)
      AND m.RecommendedMode = %s
      AND m.FilePath LIKE %s ESCAPE %s
"""
Sql = "SELECT m.Id, m.FilePath, m.FileName, m.SizeMB FROM MediaFiles m " + WhereSql + " ORDER BY m.PriorityScore DESC NULLS LAST, m.SizeMB DESC LIMIT 250"
Candidates = DB.ExecuteQuery(Sql, ('Remux', 'T:%', '!'))
t1 = time.time()
print(f"[1] Get 250 candidates: {t1-t0:.3f}s")

# Build the Items list as the JS would send
Items = [{'FilePath': c['FilePath'], 'MediaFileId': c['Id'], 'SizeMB': c['SizeMB'], 'Mode': 'Remux'} for c in Candidates]

# Step 2: GetExistingQueueFilePaths
from Features.TranscodeQueue.TranscodeQueueRepository import TranscodeQueueRepository
Repo = TranscodeQueueRepository()
t0 = time.time()
ExistingPaths = Repo.GetExistingQueueFilePaths()
t1 = time.time()
print(f"[2] GetExistingQueueFilePaths ({len(ExistingPaths)} paths): {t1-t0:.3f}s")

# Step 3: Bulk MediaFile lookup
AllMediaFileIds = [Item.get('MediaFileId') for Item in Items if Item.get('MediaFileId')]
t0 = time.time()
Rows = DB.ExecuteQuery(
    "SELECT Id, FilePath, FileName, SizeMB, DurationMinutes, AssignedProfile, Resolution "
    "FROM MediaFiles WHERE Id IN %s",
    (tuple(AllMediaFileIds),)
)
t1 = time.time()
print(f"[3] Bulk MediaFile lookup ({len(AllMediaFileIds)} ids): {t1-t0:.3f}s")

# Step 4: Build TranscodeQueueModels (in-memory only)
from datetime import datetime, timezone
from Features.TranscodeQueue.Models.TranscodeQueueModel import TranscodeQueueModel
from Features.TranscodeQueue.QueueManagementBusinessService import QueueManagementBusinessService
Svc = QueueManagementBusinessService()
MediaFileMap = {r['Id']: r for r in Rows}

t0 = time.time()
PendingInserts = []
for Item in Items:
    FilePath = Item['FilePath']
    if FilePath in ExistingPaths:
        continue
    Mf = MediaFileMap.get(Item['MediaFileId'])
    SizeMB = float(Item.get('SizeMB', 0))
    PathParts = FilePath.replace("\\", "/").split("/")
    Directory = "/".join(PathParts[:-1]) if len(PathParts) > 1 else ""
    FileName = PathParts[-1]
    # Build a minimal MediaFileModel-shaped object for CalculatePriority
    from Core.Models.MediaFileModel import MediaFileModel
    MfModel = MediaFileModel(Id=Mf['Id'], FilePath=Mf['FilePath'], FileName=Mf['FileName'], SizeMB=Mf['SizeMB'] or 0.0, DurationMinutes=Mf.get('DurationMinutes'), Resolution=Mf.get('Resolution'), AssignedProfile=Mf.get('AssignedProfile'))
    Priority = Svc.CalculatePriority(MfModel, None, None)
    QI = TranscodeQueueModel(
        FilePath=FilePath, FileName=FileName, Directory=Directory,
        SizeBytes=int(SizeMB * 1024 * 1024), SizeMB=SizeMB,
        Priority=Priority, Status="Pending",
        ProcessingMode='Remux', DateAdded=datetime.now(timezone.utc)
    )
    PendingInserts.append(QI)
t1 = time.time()
print(f"[4] Build {len(PendingInserts)} TranscodeQueueModels + priority: {t1-t0:.3f}s")

# Step 5: Time BulkInsertQueueItems WITHOUT actually committing -- use a savepoint
from Core.PathStorage import LoadStorageRoots, Parse as PathParse
from psycopg2.extras import execute_values

t0 = time.time()
StorageRoots = LoadStorageRoots(DB)
t1 = time.time()
print(f"[5a] LoadStorageRoots: {t1-t0:.3f}s")

t0 = time.time()
for Item in PendingInserts:
    if Item.StorageRootId is None or not Item.RelativePath:
        try:
            SrId, Rel = PathParse(Item.FilePath, StorageRoots)
            if SrId is not None:
                Item.StorageRootId = SrId
                Item.RelativePath = Rel or ''
        except Exception:
            pass
t1 = time.time()
print(f"[5b] Pre-resolve StorageRootId/RelativePath in Python ({len(PendingInserts)}): {t1-t0:.3f}s")

# Step 6: simulate the bulk-resolve MediaFileId + execute_values WITHOUT commit
Conn = DB.GetConnection()
try:
    Cur = Conn.cursor()
    AllPaths = [Item.FilePath for Item in PendingInserts]
    
    t0 = time.time()
    Cur.execute("SELECT Id, FilePath FROM MediaFiles WHERE FilePath IN %s", (tuple(AllPaths),))
    PathToMfId = {Row[1]: Row[0] for Row in Cur.fetchall()}
    t1 = time.time()
    print(f"[6] Bulk MediaFileId lookup by FilePath ({len(AllPaths)}): {t1-t0:.3f}s")
    
    t0 = time.time()
    Values = []
    for Item in PendingInserts:
        Mid = PathToMfId.get(Item.FilePath)
        Values.append((
            Item.StorageRootId, Item.RelativePath, Item.FilePath, Item.FileName, Item.Directory,
            Item.SizeBytes, Item.SizeMB, Item.Priority, Item.Status, Item.DateAdded,
            Item.DateStarted, Item.ProcessingMode, Mid
        ))
    t1 = time.time()
    print(f"[7] Build values tuples: {t1-t0:.3f}s")
    
    t0 = time.time()
    execute_values(
        Cur,
        """INSERT INTO TranscodeQueue
           (StorageRootId, RelativePath, FilePath, FileName, Directory,
            SizeBytes, SizeMB, Priority, Status, DateAdded, DateStarted,
            ProcessingMode, MediaFileId)
           VALUES %s""",
        Values,
        page_size=500
    )
    t1 = time.time()
    print(f"[8] execute_values INSERT (250 rows, NOT COMMITTED): {t1-t0:.3f}s")
    
    Conn.rollback()
    print(f"[9] ROLLED BACK -- no data changes")
finally:
    DB.CloseConnection(Conn)
