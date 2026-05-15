"""Time SmartPopulate queries to find the real bottleneck."""
import sys
sys.path.insert(0, '.')
import time
from Core.Database.DatabaseService import DatabaseService

DB = DatabaseService()

WhereSql = """
    WHERE m.TranscodedByMediaVortex IS NOT TRUE
      AND m.Id NOT IN (SELECT MediaFileId FROM TranscodeQueue WHERE MediaFileId IS NOT NULL)
      AND m.SizeMB > 0
      AND (m.HasExplicitEnglishAudio IS NULL OR m.HasExplicitEnglishAudio = true)
      AND m.RecommendedMode = %s
      AND m.FilePath LIKE %s ESCAPE %s
"""
Params = ('Remux', 'T:%', '!')

# Query 1: COUNT
t0 = time.time()
R = DB.ExecuteQuery('SELECT COUNT(*) as TotalCount FROM MediaFiles m ' + WhereSql, Params)
t1 = time.time()
print(f"COUNT: {R[0]['TotalCount']} rows in {t1-t0:.3f}s")

# Query 2: SELECT with ORDER + LIMIT
SelectSql = """
    SELECT m.Id, m.FilePath, m.FileName, m.SizeMB, m.VideoBitrateKbps,
           m.Codec, m.Resolution, m.ResolutionCategory, m.ContainerFormat,
           m.PriorityScore
    FROM MediaFiles m
""" + WhereSql + " ORDER BY m.PriorityScore DESC NULLS LAST, m.SizeMB DESC LIMIT 250 OFFSET 0"

t0 = time.time()
R2 = DB.ExecuteQuery(SelectSql, Params)
t1 = time.time()
print(f"SELECT: {len(R2)} rows in {t1-t0:.3f}s")

# EXPLAIN ANALYZE
print("\n--- EXPLAIN ANALYZE COUNT ---")
ExpRows = DB.ExecuteQuery('EXPLAIN ANALYZE SELECT COUNT(*) FROM MediaFiles m ' + WhereSql, Params)
for R in ExpRows:
    for V in R.values():
        print(V)

print("\n--- EXPLAIN ANALYZE SELECT ---")
ExpRows2 = DB.ExecuteQuery('EXPLAIN ANALYZE ' + SelectSql, Params)
for R in ExpRows2:
    for V in R.values():
        print(V)
