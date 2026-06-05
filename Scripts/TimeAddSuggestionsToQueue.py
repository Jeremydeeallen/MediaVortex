# Time AddSuggestionsToQueue end-to-end with real data, NO INSERTS (rolled back).
import sys
sys.path.insert(0, '.')
import time
from Core.Database.DatabaseService import DatabaseService
from Core.Path.Path import Path, PathError
from Core.Path.PathStorageRoots import GetPrefixMap, GetStorageRoots

DB = DatabaseService()
_StorageRoots = GetStorageRoots()
_PrefixMap = GetPrefixMap()

# Step 1: Get 250 candidate items the way SmartPopulate does
t0 = time.time()
# directive: path-schema-migration | # see path.S8
WhereSql = " WHERE m.TranscodedByMediaVortex IS NOT TRUE AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL) AND m.SizeMB > 0 AND (m.HasExplicitEnglishAudio IS NULL OR m.HasExplicitEnglishAudio = true) AND m.RecommendedMode = %s AND m.RelativePath LIKE %s ESCAPE %s "
# T:\ rows have StorageRootId for the T:\ root; the LIKE filter narrows by RelativePath prefix
Sql = "SELECT m.Id, m.StorageRootId, m.RelativePath, m.FileName, m.SizeMB FROM MediaFiles m " + WhereSql + " ORDER BY m.PriorityScore DESC NULLS LAST, m.SizeMB DESC LIMIT 250"
Candidates = DB.ExecuteQuery(Sql, ('Remux', '%', '!'))
t1 = time.time()
print(f"[1] Get 250 candidates: {t1-t0:.3f}s")

# Items mirror JS payload; FilePath synthesized from typed pair via Path.CanonicalDisplay
Items = [{'FilePath': Path(c['StorageRootId'], c['RelativePath'] or '').CanonicalDisplay(_PrefixMap) if c.get('StorageRootId') is not None else '', 'MediaFileId': c['Id'], 'SizeMB': c['SizeMB'], 'StorageRootId': c.get('StorageRootId'), 'RelativePath': c.get('RelativePath') or '', 'Mode': 'Remux'} for c in Candidates]

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
# directive: path-schema-migration | # see path.S8
Rows = DB.ExecuteQuery(
    "SELECT Id, StorageRootId, RelativePath, FileName, SizeMB, DurationMinutes, AssignedProfile, Resolution "
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
# directive: path-schema-migration | # see path.S8
for Item in Items:
    FilePath = Item['FilePath']
    if FilePath in ExistingPaths:
        continue
    Mf = MediaFileMap.get(Item['MediaFileId'])
    SizeMB = float(Item.get('SizeMB', 0))
    _MfSid = Mf.get('StorageRootId') if Mf else None
    _MfRel = (Mf.get('RelativePath') or '') if Mf else ''
    FileName = (Mf.get('FileName') if Mf else None) or ''
    if _MfSid is not None:
        try:
            _Parent = Path(_MfSid, _MfRel).ParentDir()
            Directory = _Parent.CanonicalDisplay(_PrefixMap)
        except PathError:
            Directory = ""
    else:
        Directory = ""
    from Core.Models.MediaFileModel import MediaFileModel
    MfModel = MediaFileModel(Id=Mf['Id'], StorageRootId=_MfSid, RelativePath=_MfRel, FileName=Mf['FileName'], SizeMB=Mf['SizeMB'] or 0.0, DurationMinutes=Mf.get('DurationMinutes'), Resolution=Mf.get('Resolution'), AssignedProfile=Mf.get('AssignedProfile'))
    Priority = Svc.CalculatePriority(MfModel, None, None)
    QI = TranscodeQueueModel(
        StorageRootId=_MfSid, RelativePath=_MfRel,
        FileName=FileName, Directory=Directory,
        SizeBytes=int(SizeMB * 1024 * 1024), SizeMB=SizeMB,
        Priority=Priority, Status="Pending",
        ProcessingMode='Remux', DateAdded=datetime.now(timezone.utc)
    )
    PendingInserts.append(QI)
t1 = time.time()
print(f"[4] Build {len(PendingInserts)} TranscodeQueueModels + priority: {t1-t0:.3f}s")

# Step 5: Time BulkInsertQueueItems WITHOUT actually committing -- use a savepoint
from psycopg2.extras import execute_values

t0 = time.time()
StorageRoots = _StorageRoots
t1 = time.time()
print(f"[5a] GetStorageRoots: {t1-t0:.3f}s")

t0 = time.time()
for Item in PendingInserts:
    if Item.StorageRootId is None or not Item.RelativePath:
        try:
            P = Path.FromLegacyString(Item.FilePath, StorageRoots)
            Item.StorageRootId = P.StorageRootId
            Item.RelativePath = P.RelativePath
        except PathError:
            pass
t1 = time.time()
print(f"[5b] Pre-resolve StorageRootId/RelativePath in Python ({len(PendingInserts)}): {t1-t0:.3f}s")

# directive: path-schema-migration | # see path.S8
Conn = DB.GetConnection()
try:
    Cur = Conn.cursor()
    AllPairs = [(Item.StorageRootId, Item.RelativePath) for Item in PendingInserts if Item.StorageRootId is not None]

    t0 = time.time()
    Cur.execute("SELECT Id, StorageRootId, RelativePath FROM MediaFiles WHERE (StorageRootId, RelativePath) IN %s", (tuple(AllPairs),))
    PairToMfId = {(Row[1], Row[2]): Row[0] for Row in Cur.fetchall()}
    t1 = time.time()
    print(f"[6] Bulk MediaFileId lookup by typed pair ({len(AllPairs)}): {t1-t0:.3f}s")

    t0 = time.time()
    Values = []
    for Item in PendingInserts:
        Mid = PairToMfId.get((Item.StorageRootId, Item.RelativePath))
        Values.append((
            Item.StorageRootId, Item.RelativePath, Item.FileName, Item.Directory,
            Item.SizeBytes, Item.SizeMB, Item.Priority, Item.Status, Item.DateAdded,
            Item.DateStarted, Item.ProcessingMode, Mid
        ))
    t1 = time.time()
    print(f"[7] Build values tuples: {t1-t0:.3f}s")

    t0 = time.time()
    execute_values(
        Cur,
        "INSERT INTO TranscodeQueue (StorageRootId, RelativePath, FileName, Directory, SizeBytes, SizeMB, Priority, Status, DateAdded, DateStarted, ProcessingMode, MediaFileId) VALUES %s",
        Values,
        page_size=500
    )
    t1 = time.time()
    print(f"[8] execute_values INSERT (250 rows, NOT COMMITTED): {t1-t0:.3f}s")

    Conn.rollback()
    print(f"[9] ROLLED BACK -- no data changes")
finally:
    DB.CloseConnection(Conn)
