# directive: path-schema-migration | # see path.S8
import time
import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='mediavortex', user='mediavortex', password='mediavortex')
cur = conn.cursor()

# T: drive resolves to StorageRoots row whose CanonicalPrefix starts with 'T:'.
cur.execute("SELECT Id FROM StorageRoots WHERE CanonicalPrefix LIKE 'T:%' LIMIT 1")
_root = cur.fetchone()
if _root is None:
    raise SystemExit("StorageRoots has no row matching CanonicalPrefix LIKE 'T:%'")
T_ROOT_ID = _root[0]

# Query 1: GetShowsWithStats (with T: filter)
t1 = time.perf_counter()
cur.execute(
    "SELECT "
    "    split_part(mf.RelativePath, '/', 1) as ShowName, "
    "    MIN(split_part(mf.RelativePath, '/', 1)) as ShowFolder, "
    "    COUNT(*) as FileCount, "
    "    ROUND(SUM(mf.SizeMB)::numeric / 1024, 1) as TotalGB, "
    "    MODE() WITHIN GROUP (ORDER BY mf.ResolutionCategory) as CommonResolution, "
    "    MODE() WITHIN GROUP (ORDER BY mf.Codec) as CommonCodec, "
    "    ss.TargetResolution as TargetResolution, "
    "    SUM(CASE WHEN mf.TranscodedByMediaVortex = true THEN 1 ELSE 0 END) as TranscodedCount "
    "FROM MediaFiles mf "
    "LEFT JOIN ShowSettings ss "
    "  ON ss.StorageRootId = mf.StorageRootId "
    " AND ss.RelativePath = split_part(mf.RelativePath, '/', 1) "
    "WHERE mf.StorageRootId = %s "
    "GROUP BY ShowName, ss.TargetResolution "
    "HAVING COUNT(*) > 0 "
    "ORDER BY SUM(mf.SizeMB) DESC",
    (T_ROOT_ID,)
)
rows1 = cur.fetchall()
t2 = time.perf_counter()
print(f"GetShowsWithStats (T:): {t2-t1:.3f}s, {len(rows1)} rows")

# Query 2: SmartPopulate (no limit, T: drive)
t3 = time.perf_counter()
cur.execute(
    "SELECT m.Id, m.RelativePath, m.FileName, m.SizeMB, m.VideoBitrateKbps, "
    "       m.Codec, m.Resolution, m.ResolutionCategory, m.ContainerFormat "
    "FROM MediaFiles m "
    "WHERE (m.TranscodedByMediaVortex IS NULL OR m.TranscodedByMediaVortex = false) "
    "  AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL) "
    "  AND m.SizeMB > 0 "
    "  AND m.StorageRootId = %s "
    "ORDER BY m.SizeMB DESC, m.VideoBitrateKbps DESC",
    (T_ROOT_ID,)
)
rows2 = cur.fetchall()
t4 = time.perf_counter()
print(f"SmartPopulate (T:, no limit): {t4-t3:.3f}s, {len(rows2)} rows")

# Query 3: SmartPopulate with LIMIT 100
t5 = time.perf_counter()
cur.execute(
    "SELECT m.Id, m.RelativePath, m.FileName, m.SizeMB, m.VideoBitrateKbps, "
    "       m.Codec, m.Resolution, m.ResolutionCategory, m.ContainerFormat "
    "FROM MediaFiles m "
    "WHERE (m.TranscodedByMediaVortex IS NULL OR m.TranscodedByMediaVortex = false) "
    "  AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL) "
    "  AND m.SizeMB > 0 "
    "  AND m.StorageRootId = %s "
    "ORDER BY m.SizeMB DESC, m.VideoBitrateKbps DESC "
    "LIMIT 100",
    (T_ROOT_ID,)
)
rows3 = cur.fetchall()
t6 = time.perf_counter()
print(f"SmartPopulate (T:, LIMIT 100): {t6-t5:.3f}s, {len(rows3)} rows")

# Query 4: SmartPopulate with NOT EXISTS instead of NOT IN
t7 = time.perf_counter()
cur.execute(
    "SELECT m.Id, m.RelativePath, m.FileName, m.SizeMB, m.VideoBitrateKbps, "
    "       m.Codec, m.Resolution, m.ResolutionCategory, m.ContainerFormat "
    "FROM MediaFiles m "
    "WHERE (m.TranscodedByMediaVortex IS NULL OR m.TranscodedByMediaVortex = false) "
    "  AND NOT EXISTS (SELECT 1 FROM TranscodeQueue tq WHERE tq.MediaFileId = m.Id) "
    "  AND m.SizeMB > 0 "
    "  AND m.StorageRootId = %s "
    "ORDER BY m.SizeMB DESC, m.VideoBitrateKbps DESC",
    (T_ROOT_ID,)
)
rows4 = cur.fetchall()
t8 = time.perf_counter()
print(f"SmartPopulate (T:, NOT EXISTS no limit): {t8-t7:.3f}s, {len(rows4)} rows")

# Query 5: NOT EXISTS with LIMIT 100
t9 = time.perf_counter()
cur.execute(
    "SELECT m.Id, m.RelativePath, m.FileName, m.SizeMB, m.VideoBitrateKbps, "
    "       m.Codec, m.Resolution, m.ResolutionCategory, m.ContainerFormat "
    "FROM MediaFiles m "
    "WHERE (m.TranscodedByMediaVortex IS NULL OR m.TranscodedByMediaVortex = false) "
    "  AND NOT EXISTS (SELECT 1 FROM TranscodeQueue tq WHERE tq.MediaFileId = m.Id) "
    "  AND m.SizeMB > 0 "
    "  AND m.StorageRootId = %s "
    "ORDER BY m.SizeMB DESC, m.VideoBitrateKbps DESC "
    "LIMIT 100",
    (T_ROOT_ID,)
)
rows5 = cur.fetchall()
t10 = time.perf_counter()
print(f"SmartPopulate (T:, NOT EXISTS LIMIT 100): {t10-t9:.3f}s, {len(rows5)} rows")

# Query 6: CTE version of GetShowsWithStats
t11 = time.perf_counter()
cur.execute(
    "WITH ShowData AS ( "
    "    SELECT "
    "        mf.SizeMB, mf.ResolutionCategory, mf.Codec, mf.TranscodedByMediaVortex, "
    "        mf.StorageRootId, "
    "        split_part(mf.RelativePath, '/', 1) as ComputedShowName "
    "    FROM MediaFiles mf "
    "    WHERE mf.StorageRootId = %s "
    ") "
    "SELECT "
    "    ComputedShowName as ShowName, "
    "    MIN(ComputedShowName) as ShowFolder, "
    "    COUNT(*) as FileCount, "
    "    ROUND(SUM(SizeMB)::numeric / 1024, 1) as TotalGB, "
    "    MODE() WITHIN GROUP (ORDER BY ResolutionCategory) as CommonResolution, "
    "    MODE() WITHIN GROUP (ORDER BY Codec) as CommonCodec, "
    "    ss.TargetResolution as TargetResolution, "
    "    SUM(CASE WHEN TranscodedByMediaVortex = true THEN 1 ELSE 0 END) as TranscodedCount "
    "FROM ShowData "
    "LEFT JOIN ShowSettings ss "
    "  ON ss.StorageRootId = ShowData.StorageRootId "
    " AND ss.RelativePath = ComputedShowName "
    "GROUP BY ComputedShowName, ss.TargetResolution "
    "HAVING COUNT(*) > 0 "
    "ORDER BY SUM(SizeMB) DESC",
    (T_ROOT_ID,)
)
rows6 = cur.fetchall()
t12 = time.perf_counter()
print(f"GetShowsWithStats CTE (T:): {t12-t11:.3f}s, {len(rows6)} rows")

# Check indexes
print("\n--- Indexes on mediafiles ---")
cur.execute("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'mediafiles' ORDER BY indexname")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1][:150]}")

print("\n--- Indexes on transcodequeue ---")
cur.execute("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'transcodequeue' ORDER BY indexname")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1][:150]}")

print("\n--- Indexes on showsettings ---")
cur.execute("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'showsettings' ORDER BY indexname")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1][:150]}")

# Count rows in key tables
cur.execute("SELECT COUNT(*) FROM mediafiles")
print(f"\nMediaFiles rows: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM transcodequeue")
print(f"TranscodeQueue rows: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM mediafiles WHERE storagerootid = %s", (T_ROOT_ID,))
print(f"MediaFiles on T: drive: {cur.fetchone()[0]}")
cur.execute(
    "SELECT COUNT(*) FROM mediafiles "
    "WHERE (transcodedbymediavortex IS NULL OR transcodedbymediavortex = false) "
    "  AND sizemb > 0 "
    "  AND storagerootid = %s",
    (T_ROOT_ID,)
)
print(f"Untranscoded on T: (candidates): {cur.fetchone()[0]}")

conn.rollback()
conn.close()
