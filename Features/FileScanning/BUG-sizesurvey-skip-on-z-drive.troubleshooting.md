# BUG: SizeSurvey silently skipped on Z:\ scans

## Symptom

On scan 73188 (larry-worker-3, Z:\, code be67de1):
- Phase advanced to `Walking` without `SizeSurvey` being observable
- `ScanJobs.TopFiles IS NULL` (no JSON written -- not even an empty array)
- `FilesNeedingProbe IS NULL`, `ProbedFiles IS NULL` (probe counters not initialized)

Same code path on the same tick worked for M:\ (worker-1, drained 100->0) and T:\ (worker-2, draining 100->98).

## Confirmed Facts (DB-observable)

1. ScanJobs row 73188 exists with `RootFolderPath='Z:\'`, `WorkerName='larry-worker-3'`, `Status='Running'`, heartbeat alive (StaleS<5).
2. Workers row `larry-worker-3` shows `Version=be67de1` (matches deployed image).
3. WorkerShareMappings has the row `larry-worker-3 | Z | /mnt/xxx/`.
4. M:\ and T:\ scans on the SAME tick (73186, 73187) successfully wrote `TopFiles` JSON with 100 entries each.

## Ruled Out

- Worker not running new code -- Version matches.
- Path translation broken -- LocalMountPrefix for Z is present.
- M:\ scan started later -- both M:\ and Z:\ started within 1 second of each other; M:\ ran SizeSurvey successfully.

## Active Hypotheses (to test cheaply)

| # | Hypothesis | Test | Why it would explain NULL TopFiles |
|---|---|---|---|
| H1 | `_RunSizeSurvey` exception caught by PerformScan try/except, JSON never written | Look for Z:\ MediaFiles rows with LastScannedDate < scan start = SizeSurvey didn't touch any row | Outer try/except logs but doesn't persist failure to the row |
| H2 | StorageRoots lookup for Z:\ path returns NULL StorageRootId, all UPSERTs hit the existing-row check with NULL/NULL = no match, all become inserts of model with NULL StorageRootId -- SaveMediaFile raises on unique index | Check StorageRoots row for Z:\; sample MediaFiles for current Z:\ schema | If parse returns NULL, the loop accumulates 0 Records and writes empty array NOT null -- doesn't fit symptom |
| H3 | os.scandir on /mnt/xxx hits a permission error early, exception bubbles out of `_WalkSurvey`, caught by outer try/except, no TopFiles write at all | Check filesystem behavior on /mnt/xxx via worker-3 | Fits NULL TopFiles symptom exactly |
| H4 | Heap is empty (no media files match extensions in /mnt/xxx subtree), `TopList=[]`, loop never runs, but the `_WriteTopFiles([])` call should still write `[]` not NULL | Inspect /mnt/xxx contents for media extensions | If no media files, would write empty array; doesn't fit NULL symptom |

H3 is the leading candidate. H1 is the fallback explanation.

## Narrow Test Queries

```sql
-- Q1: Did the scan touch any Z:\ MediaFiles row during its window?
SELECT COUNT(*) FROM MediaFiles
WHERE FilePath LIKE 'Z:\%'
  AND LastScannedDate > (SELECT StartTime FROM ScanJobs WHERE Id = 73188);

-- Q2: StorageRoots config for Z
SELECT Id, Name, CanonicalPrefix FROM StorageRoots WHERE CanonicalPrefix ILIKE 'Z:%';

-- Q3: Was the row touched at all post-Walking-transition?
SELECT TopFiles IS NULL AS TopFilesNull, FilesNeedingProbe IS NULL AS FNPNull,
       Progress, ProcessedFiles, TotalFiles
FROM ScanJobs WHERE Id = 73188;
```

## Next Action

Run Q1-Q3, then directly check /mnt/xxx contents on worker-3 for media files. If H3 holds, the fix is to write empty `[]` to TopFiles BEFORE the walk starts so the row state is at least observable as "SizeSurvey attempted with no result," and to surface the exception text to ScanJobs.ErrorMessage instead of swallowing it.

## Status

Open -- diagnosis in progress.
