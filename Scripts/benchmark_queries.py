"""Benchmark the Media page SQL queries to find bottlenecks."""
import time
import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='mediavortex', user='mediavortex', password='mediavortex')
cur = conn.cursor()

# Query 1: GetShowsWithStats (with T: filter)
t1 = time.perf_counter()
cur.execute(r"""
    SELECT 
        split_part(replace(mf.FilePath, '\', '/'), '/', 2) as ShowName,
        MIN(split_part(mf.FilePath, '\', 1) || '\' || split_part(replace(mf.FilePath, '\', '/'), '/', 2)) as ShowFolder,
        COUNT(*) as FileCount,
        ROUND(SUM(mf.SizeMB)::numeric / 1024, 1) as TotalGB,
        MODE() WITHIN GROUP (ORDER BY mf.ResolutionCategory) as CommonResolution,
        MODE() WITHIN GROUP (ORDER BY mf.Codec) as CommonCodec,
        ss.TargetResolution as TargetResolution,
        SUM(CASE WHEN mf.TranscodedByMediaVortex = true THEN 1 ELSE 0 END) as TranscodedCount
    FROM MediaFiles mf
    LEFT JOIN ShowSettings ss ON ss.ShowFolder = split_part(mf.FilePath, '\', 1) || '\' || split_part(replace(mf.FilePath, '\', '/'), '/', 2)
    WHERE mf.FilePath LIKE 'T:%%'
    GROUP BY ShowName, ss.TargetResolution
    HAVING COUNT(*) > 0
    ORDER BY SUM(mf.SizeMB) DESC
""")
rows1 = cur.fetchall()
t2 = time.perf_counter()
print(f"GetShowsWithStats (T:): {t2-t1:.3f}s, {len(rows1)} rows")

# Query 2: SmartPopulate (no limit, T: drive)
t3 = time.perf_counter()
cur.execute("""
    SELECT m.Id, m.FilePath, m.FileName, m.SizeMB, m.VideoBitrateKbps,
           m.Codec, m.Resolution, m.ResolutionCategory, m.ContainerFormat
    FROM MediaFiles m
    WHERE (m.TranscodedByMediaVortex IS NULL OR m.TranscodedByMediaVortex = false)
      AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL)
      AND m.SizeMB > 0
      AND m.FilePath LIKE 'T:%%'
    ORDER BY m.SizeMB DESC, m.VideoBitrateKbps DESC
""")
rows2 = cur.fetchall()
t4 = time.perf_counter()
print(f"SmartPopulate (T:, no limit): {t4-t3:.3f}s, {len(rows2)} rows")

# Query 3: SmartPopulate with LIMIT 100
t5 = time.perf_counter()
cur.execute("""
    SELECT m.Id, m.FilePath, m.FileName, m.SizeMB, m.VideoBitrateKbps,
           m.Codec, m.Resolution, m.ResolutionCategory, m.ContainerFormat
    FROM MediaFiles m
    WHERE (m.TranscodedByMediaVortex IS NULL OR m.TranscodedByMediaVortex = false)
      AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL)
      AND m.SizeMB > 0
      AND m.FilePath LIKE 'T:%%'
    ORDER BY m.SizeMB DESC, m.VideoBitrateKbps DESC
    LIMIT 100
""")
rows3 = cur.fetchall()
t6 = time.perf_counter()
print(f"SmartPopulate (T:, LIMIT 100): {t6-t5:.3f}s, {len(rows3)} rows")

# Query 4: SmartPopulate with NOT EXISTS instead of NOT IN
t7 = time.perf_counter()
cur.execute("""
    SELECT m.Id, m.FilePath, m.FileName, m.SizeMB, m.VideoBitrateKbps,
           m.Codec, m.Resolution, m.ResolutionCategory, m.ContainerFormat
    FROM MediaFiles m
    WHERE (m.TranscodedByMediaVortex IS NULL OR m.TranscodedByMediaVortex = false)
      AND NOT EXISTS (SELECT 1 FROM TranscodeQueue tq WHERE tq.MediaFileId = m.Id)
      AND m.SizeMB > 0
      AND m.FilePath LIKE 'T:%%'
    ORDER BY m.SizeMB DESC, m.VideoBitrateKbps DESC
""")
rows4 = cur.fetchall()
t8 = time.perf_counter()
print(f"SmartPopulate (T:, NOT EXISTS no limit): {t8-t7:.3f}s, {len(rows4)} rows")

# Query 5: NOT EXISTS with LIMIT 100
t9 = time.perf_counter()
cur.execute("""
    SELECT m.Id, m.FilePath, m.FileName, m.SizeMB, m.VideoBitrateKbps,
           m.Codec, m.Resolution, m.ResolutionCategory, m.ContainerFormat
    FROM MediaFiles m
    WHERE (m.TranscodedByMediaVortex IS NULL OR m.TranscodedByMediaVortex = false)
      AND NOT EXISTS (SELECT 1 FROM TranscodeQueue tq WHERE tq.MediaFileId = m.Id)
      AND m.SizeMB > 0
      AND m.FilePath LIKE 'T:%%'
    ORDER BY m.SizeMB DESC, m.VideoBitrateKbps DESC
    LIMIT 100
""")
rows5 = cur.fetchall()
t10 = time.perf_counter()
print(f"SmartPopulate (T:, NOT EXISTS LIMIT 100): {t10-t9:.3f}s, {len(rows5)} rows")

# Query 6: CTE version of GetShowsWithStats
t11 = time.perf_counter()
cur.execute(r"""
    WITH ShowData AS (
        SELECT 
            mf.SizeMB, mf.ResolutionCategory, mf.Codec, mf.TranscodedByMediaVortex,
            split_part(mf.FilePath, '\', 1) || '\' || split_part(replace(mf.FilePath, '\', '/'), '/', 2) as ComputedShowFolder,
            split_part(replace(mf.FilePath, '\', '/'), '/', 2) as ComputedShowName
        FROM MediaFiles mf
        WHERE mf.FilePath LIKE 'T:%%'
    )
    SELECT 
        ComputedShowName as ShowName,
        MIN(ComputedShowFolder) as ShowFolder,
        COUNT(*) as FileCount,
        ROUND(SUM(SizeMB)::numeric / 1024, 1) as TotalGB,
        MODE() WITHIN GROUP (ORDER BY ResolutionCategory) as CommonResolution,
        MODE() WITHIN GROUP (ORDER BY Codec) as CommonCodec,
        ss.TargetResolution as TargetResolution,
        SUM(CASE WHEN TranscodedByMediaVortex = true THEN 1 ELSE 0 END) as TranscodedCount
    FROM ShowData
    LEFT JOIN ShowSettings ss ON ss.ShowFolder = ComputedShowFolder
    GROUP BY ComputedShowName, ss.TargetResolution
    HAVING COUNT(*) > 0
    ORDER BY SUM(SizeMB) DESC
""")
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
cur.execute("SELECT COUNT(*) FROM mediafiles WHERE filepath LIKE 'T:%%'")
print(f"MediaFiles on T: drive: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM mediafiles WHERE (transcodedbymedianvortex IS NULL OR transcodedbymedianvortex = false) AND sizemb > 0 AND filepath LIKE 'T:%%'")
print(f"Untranscoded on T: (candidates): {cur.fetchone()[0]}")

conn.rollback()
conn.close()
