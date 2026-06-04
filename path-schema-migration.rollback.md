# path-schema-migration -- Rollback

The migration RENAMES legacy path columns to `_legacy_<col>` instead of dropping them. Rollback is one ALTER TABLE per column; no data movement, no pg_dump restore needed.

## What the migration renames

| Table | Legacy column | Renamed to |
|---|---|---|
| MediaFiles | FilePath | _legacy_filepath |
| MediaFilesArchive | FilePath | _legacy_filepath |
| TranscodeQueue | FilePath | _legacy_filepath |
| TranscodeAttempts | FilePath | _legacy_filepath |
| TemporaryFilePaths | OriginalPath | _legacy_originalpath |
| TemporaryFilePaths | LocalSourcePath | _legacy_localsourcepath |
| TemporaryFilePaths | LocalOutputPath | _legacy_localoutputpath |
| ShowSettings | ShowFolder | _legacy_showfolder |

V2 code does not reference any of the renamed columns; the rename effectively hides them from the application.

## Rollback procedure (fast path)

If the V2 cutover surfaces an unexpected regression, restore each legacy column's original name:

```sql
ALTER TABLE MediaFiles         RENAME COLUMN _legacy_filepath        TO FilePath;
ALTER TABLE MediaFilesArchive  RENAME COLUMN _legacy_filepath        TO FilePath;
ALTER TABLE TranscodeQueue     RENAME COLUMN _legacy_filepath        TO FilePath;
ALTER TABLE TranscodeAttempts  RENAME COLUMN _legacy_filepath        TO FilePath;
ALTER TABLE TemporaryFilePaths RENAME COLUMN _legacy_originalpath    TO OriginalPath;
ALTER TABLE TemporaryFilePaths RENAME COLUMN _legacy_localsourcepath TO LocalSourcePath;
ALTER TABLE TemporaryFilePaths RENAME COLUMN _legacy_localoutputpath TO LocalOutputPath;
ALTER TABLE ShowSettings       RENAME COLUMN _legacy_showfolder      TO ShowFolder;
```

Each statement is independent and can run individually if only one table needs reverting. Then `git revert <commit>` restores the code that reads/writes those columns.

## Belt-and-suspenders snapshot

`C:\Code\MediaVortex\.backups\path_schema_pre_<timestamp>.sql.gz` — gzip-compressed plain-SQL COPY dump (100,841 rows). Restorable via:

```bash
zcat path_schema_pre_<timestamp>.sql.gz | psql -h 10.0.0.15 -U mediavortex -d mediavortex
```

The snapshot is only needed if a `_legacy_<col>` column itself is dropped, accidentally modified, or otherwise lost.

## When to actually drop the columns

Phase 9 (or later) drops the `_legacy_<col>` columns once V2 is proven stable in production over a defined window. Until then they remain as the fast-rollback safety net.

```sql
ALTER TABLE MediaFiles         DROP COLUMN IF EXISTS _legacy_filepath;
ALTER TABLE MediaFilesArchive  DROP COLUMN IF EXISTS _legacy_filepath;
ALTER TABLE TranscodeQueue     DROP COLUMN IF EXISTS _legacy_filepath;
ALTER TABLE TranscodeAttempts  DROP COLUMN IF EXISTS _legacy_filepath;
ALTER TABLE TemporaryFilePaths DROP COLUMN IF EXISTS _legacy_originalpath;
ALTER TABLE TemporaryFilePaths DROP COLUMN IF EXISTS _legacy_localsourcepath;
ALTER TABLE TemporaryFilePaths DROP COLUMN IF EXISTS _legacy_localoutputpath;
ALTER TABLE ShowSettings       DROP COLUMN IF EXISTS _legacy_showfolder;
```

## Verification commands

After applying the migration:

```bash
venv\Scripts\python.exe -c "
from Core.Database.DatabaseService import DatabaseService
d = DatabaseService()
rows = d.ExecuteQuery(\"SELECT table_name, column_name FROM information_schema.columns WHERE column_name LIKE '_legacy_%' ORDER BY table_name, column_name\")
for r in rows:
    print(f'{r[\"table_name\"]}.{r[\"column_name\"]}')"
```

Expected: 8 rows naming the 8 renamed columns.
