"""Create performance indexes and verify improvement."""
import psycopg2
import time

conn = psycopg2.connect(host='10.0.0.15', port=5432, dbname='mediavortex', user='mediavortex', password='mediavortex')
conn.autocommit = True
cur = conn.cursor()

# BEFORE: measure the baseline query
print("=== BEFORE: EXPLAIN ANALYZE (no functional index) ===")
cur.execute(r"""
    EXPLAIN ANALYZE 
    SELECT Id FROM MediaFiles 
    WHERE LOWER(FilePath) = LOWER('T:\Power Rangers\Season 18\file.mkv')
""")
for row in cur.fetchall():
    print(row[0])

# Create functional index on LOWER(FilePath) — the big win
print("\nCreating idx_mediafiles_filepath_lower...")
start = time.time()
cur.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mediafiles_filepath_lower ON MediaFiles (LOWER(FilePath))")
print(f"Done in {time.time()-start:.1f}s")

# AFTER: recheck
print("\n=== AFTER: EXPLAIN ANALYZE (with functional index) ===")
cur.execute(r"""
    EXPLAIN ANALYZE 
    SELECT Id FROM MediaFiles 
    WHERE LOWER(FilePath) = LOWER('T:\Power Rangers\Season 18\file.mkv')
""")
for row in cur.fetchall():
    print(row[0])

# List all indexes now
print("\n=== All MediaFiles indexes ===")
cur.execute("SELECT indexdef FROM pg_indexes WHERE tablename = 'mediafiles'")
for row in cur.fetchall():
    print(f"  {row[0]}")

cur.close()
conn.close()
