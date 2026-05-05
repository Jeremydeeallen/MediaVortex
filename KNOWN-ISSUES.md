# Known Issues

## Open

### [BUG] Second concurrent job shows first job's progress
**Date:** 2025-05-05
**Affects:** TranscodeJob feature -- concurrent job progress tracking
**Criterion violated:** TranscodeJob.feature.md -- each running job must report independent progress

When MaxConcurrentJobs > 1 and a second job starts while the first is still running, the second job displays the same progress percentage and ETA as the first (e.g., both show 20.5% / ETA 01:41:41). Only one FFmpeg process is actually running.

**Look first:** `Features/TranscodeJob/ProcessTranscodeQueueService.py:169` (`GetStatus` returns single `currentProgress`), `GetCurrentTranscodeProgress()` in DatabaseManager (likely returns one row, not per-job), and `VideoTranscodingService.TranscodeVideo` (process spawning).

**Fix with:** `/t`

### [BUG] FilePath used as denormalized natural key across 6+ tables
**Date:** 2026-05-05
**Affects:** Schema-wide -- MediaFiles, TranscodeAttempts, TranscodeFiles, TranscodeQueue, CompliantFiles, ProblemFiles
**Criterion violated:** Data normalization -- same filepath (with platform-specific drive letter prefix) stored redundantly across tables instead of referencing MediaFiles.Id as a foreign key.

Full Windows paths (e.g., `T:\Shows\file.mkv`) are stored as natural keys in at least 6 tables. This causes:
1. Case inconsistencies already present in production data (`T:\` vs `t:\`, `Z:\` vs `z:\`)
2. Platform coupling -- every table embeds Windows drive letters, making cross-platform workers depend on prefix translation at query boundaries
3. No referential integrity -- deleting/renaming a file in MediaFiles does not cascade to dependent tables
4. Path changes (drive letter remapping, share migration) require updating every table

**Scale:** ~67k rows in MediaFiles, ~3.8k in TranscodeFiles, ~2.9k in TranscodeAttempts, ~1.4k in CompliantFiles.

**Look first:** `/data-expert` for schema analysis, then `Scripts/SQLScripts/AddDistributedColumns.py` for migration patterns.

**Fix with:** `/n` (this is a schema redesign, not a quick fix)

### [BUG] QueryDatabase.py sql command silently rolls back writes
**Date:** 2026-05-05
**Affects:** Scripts/SQLScripts/QueryDatabase.py -- `run_raw_sql()` function, line 192
**Criterion violated:** setup.sh uses QueryDatabase.py for INSERT/UPDATE during worker registration, but writes are silently rolled back.

`run_raw_sql()` explicitly calls `conn.rollback()` for non-SELECT statements (comment: "Don't commit modifications from troubleshooting script"). This is intentional for a read-only troubleshooting tool, but setup.sh depends on it for writes. The function reports "Rows affected: N" before rolling back, making it appear successful.

**Impact:** Worker registration and share mapping inserts via setup.sh silently fail on every deploy. Must use direct psycopg2 with autocommit instead.

**Look first:** `Scripts/SQLScripts/QueryDatabase.py:184-192` (`run_raw_sql`), `terraform/mediavortex-transcode/setup.sh` (worker registration section)

**Fix with:** `/t` -- add a `--commit` flag to QueryDatabase.py so `sql` writes commit when explicitly opted in, or have setup.sh use inline Python instead.
