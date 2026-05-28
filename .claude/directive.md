# Current Directive

**Set:** 2026-05-27
**Status:** Active
**Replaces:** `directives/closed/2026-05-27-active-scan-visibility.md` (closed Partial -- producer-side phase/probe writes kept; UI scrapped here)

## Outcome

Within ~30 seconds of a scan starting on any Larry worker, the operator sees the top-N largest files on the share surfaced on /Activity -- file path, size, worker -- before the full walk completes. Those largest files land in `MediaFiles` immediately so the rest of the pipeline (probe + transcode eligibility) acts on the biggest savings opportunities while the long-tail walk continues in background. /Activity scan rows are their own self-contained section -- not shoehorned into transcode-shaped columns -- so the operator can read what's happening at a glance.

The phrase "70% of our problem" in the CEO statement = storage-savings opportunity: largest files yield the largest transcode wins. Front-loading them means visible value within seconds instead of waiting for a 40k-file scan to complete.

## Acceptance Criteria

### A. SizeSurvey phase

1. **Every scan starts with a `SizeSurvey` phase** before `Walking`. The worker enumerates every media file under the rootfolder with size and mtime, sorts descending by size, and isolates the top N (default 100). Default media extensions: `.mkv .mp4 .avi .m4v .mov .ts .wmv .mpg .mpeg`. Verifiable: trigger a scan; `SELECT Phase FROM ScanJobs WHERE Id=<new>` reads `SizeSurvey` within 1s of start.

2. **SizeSurvey returns within 30 seconds on Larry against any registered share root** (T:\ ~40k files, M:\ ~3k, Z:\ ~8k). No FFprobe, no metadata reads -- stat-only enumeration. Verifiable: kick a scan from any larry-worker; `SELECT EXTRACT(EPOCH FROM (LastUpdated - StartTime)) FROM ScanJobs WHERE JobId=<new> AND Phase != 'SizeSurvey' ORDER BY LastUpdated LIMIT 1` is < 30.

3. **Top-N largest files land in `MediaFiles` during SizeSurvey.** For each file in the top-N: UPSERT a `MediaFiles` row keyed on `(StorageRootId, LOWER(RelativePath))` -- populate `FilePath`, `FileName`, `SizeMB`, `FileModificationTime`, `StorageRootId`, `RelativePath`, `RootFolderId`. Probe-dependent columns (`Resolution`, `Codec`, etc.) stay NULL; they fill in during the later Probing phase. Existing rows have their `SizeMB` / `FileModificationTime` refreshed but identity (`Id`) preserved. Verifiable: pick a known large file before scan, note its `Id` and `SizeMB`; trigger a scan; within ~30s the same `Id` is present with refreshed `SizeMB`.

4. **The top-N count is configurable via SystemSettings.** Key `SizeSurveyTopN`, integer, default `100`. Read fresh per scan -- no worker restart needed to change. Verifiable: `UPDATE SystemSettings SET SettingValue='50' WHERE SettingKey='SizeSurveyTopN'`; next scan writes 50 entries to the JSON column (criterion 5).

5. **SizeSurvey results are persisted on the `ScanJobs` row** so /Activity can render them. New column `ScanJobs.TopFiles JSONB NULL`, written once at SizeSurvey completion. Shape: `[{"path": "T:\\Show\\file.mkv", "sizeMB": 4823.1, "modifiedAt": "2026-05-12T14:32:01Z"}, ...]`. Length matches `SizeSurveyTopN`. Verifiable: `SELECT jsonb_array_length(TopFiles) FROM ScanJobs WHERE Id=<scan>` returns N after SizeSurvey completes.

### B. Worker dispatch fix (blocker for criterion 2 across M:\ + Z:\)

6. **`ContinuousScanService._GetTopLevelFolders` collapses subfolders under their share root regardless of host OS.** Today the function uses POSIX `os.sep` on Windows-style canonical paths, so on Linux workers every individual subfolder appears as its own top-level target -- three Linux workers all alphabetically pick `T:\<show>` entries and M:\ + Z:\ never get scanned. Fix: dedup on canonical Windows-style separators directly (split on `\`, prefix-match case-insensitively), not on `os.sep`. Verifiable: with RootFolders containing `T:\`, `T:\30 Rock`, `M:\`, `Z:\`: function returns exactly `T:\`, `M:\`, `Z:\` on Linux AND Windows.

7. **Workers spread across share roots, not pile on one.** With criterion 6 fixed and three ScanEnabled larry workers, the next scan tick produces three concurrent scans -- one each on T:\, M:\, Z:\ (per-rootfolder claim guard already prevents collision). Verifiable: post-fix, kick a scan tick; SQL shows three Running ScanJobs rows, one per drive letter, distinct workers.

### C. /Activity scan rows (clean, self-contained)

8. **Scan rows render as a separate `<tbody>` section under the Active Jobs card** with scan-appropriate columns -- not the 9-column transcode row layout. Columns:
   `Drive | Worker | Phase | Progress | Files (+N ~U -D) | Rate | ETA | Stop`
   Section header row (within the table): `Scans` with the running count, e.g. `Scans (3)`. Transcode + VMAF rows keep their existing layout in a sibling section. Verifiable: visual inspection -- distinct column headers, no Size/FPS/Speed columns above scan rows.

9. **Each running scan row also shows the top-5 largest files from its SizeSurvey** inline below the row (collapsible if >5). Shape: `<filename> -- <size>` per line. Pulled from `ScanJobs.TopFiles` JSON. Empty until SizeSurvey completes for new scans; immediately populated on refresh for scans whose SizeSurvey has finished. Verifiable: row for active scan whose SizeSurvey is done shows 5 file lines with sizes (e.g. `Big.Show.S01E03.mkv -- 4.7 GB`); row for scan still in SizeSurvey shows `enumerating files...`.

10. **/Activity refresh cadence unchanged** -- the existing `LoadOverview()` tick (~5s) picks up scan rows + top-files via the existing `/api/TeamStatus/Overview` payload. No new poller. Verifiable: code inspection.

### D. Producer-side preservation

11. **The prior directive's producer-side work stays as-is.** Phase transitions (Walking / Reconciling / Probing / Completing), probe counters (`FilesNeedingProbe` / `ProbedFiles`), soft-stop via `Status='Stopping'`, and the `_StartProgressHeartbeat` loop are all preserved -- SizeSurvey is inserted ahead of Walking as a new initial phase. No regressions. Verifiable: existing post-SizeSurvey behavior unchanged in a smoke scan.

## Out of Scope

- RootFolder data cleanup (the 534 individual show-folder rows). Criterion 6 + 7 make their presence harmless (parent-dedupe ignores them), but the rows themselves are not deleted here. Separate operator decision.
- "Dynamic-name" display on /Activity rows (using show metadata vs raw path). The drive label `T:\` is enough -- there is only one row per share. If show-name display is wanted later, that is a follow-up.
- FFprobing the top-N inline as part of SizeSurvey. Probe still happens in the existing Probing phase after Walking completes; SizeSurvey only stats + UPSERTs.
- Replacing `RootFolders` with a share-root-only model (path-storage.feature.md scope).
- Worker-tile "Scan:" line (carryover from prior directive) -- leave as-is; not regressed, not improved.

## Constraints

- One new schema column: `ScanJobs.TopFiles JSONB NULL`. Idempotent ADD COLUMN IF NOT EXISTS.
- SizeSurvey must NOT FFprobe -- one stat per file only. The whole point is "fast first signal."
- SizeSurvey must respect existing safety guards: `(StorageRootId, LOWER(RelativePath))` unique index, EscapeLikePattern when used, FFprobe failure limit (does not apply since no probe).
- Default `SizeSurveyTopN = 100`. If operator raises this very high, the JSON column grows -- soft cap at 500 (above that, log a WARNING and truncate to 500 in code).
- Larry's NFS is fast (operator-confirmed); 30s budget is comfortable for 40k files. On a slower host (I9 over SMB), budget may overflow -- the directive doesn't promise speed off Larry. Criterion 2 explicitly scoped to Larry.

## Escalation Defaults

- Tradeoff between "show partial results immediately" vs "write once at SizeSurvey end" -> write once. Simpler, atomic, no torn-read on /Activity polls.
- If SizeSurvey budget breached (>30s), do not abort -- log WARNING + continue. The 30s is a target, not a hard kill.
- Risk tolerance: medium. One new column, one new phase, dispatch fix. Rollback = revert + drop column.

## Engineering Calls Already Made

- SizeSurvey enumeration uses `os.scandir` recursive Python (cross-platform; same speed as `find` on Linux; works on Windows). Not subprocess `find`.
- Top-N persisted as JSONB on ScanJobs (not a side table). Read-once consumer (/Activity), bounded size, no FK semantics needed.
- The "70% of our problem" interpretation = storage-savings opportunity, NOT fault detection or corruption surfacing. CEO can redirect.
- Dispatch fix lands here, not in a separate directive -- criterion 2's "30s on any share" can't be met without it.

## Status

Active 2026-05-27 -- next step: implement.

Plan:
1. Migration: `Scripts/SQLScripts/AddScanJobsTopFiles.py` -- idempotent `ALTER TABLE ScanJobs ADD COLUMN IF NOT EXISTS TopFiles JSONB`. Seed `SystemSettings('SizeSurveyTopN', '100', 'integer')`.
2. Fix `ContinuousScanService._GetTopLevelFolders` to dedupe on Windows-style separators (criterion 6).
3. Add `SizeSurvey` phase to `FileScanningBusinessService.PerformScan` -- new helper `_RunSizeSurvey(LocalRootPath, RootFolder, TopN)` runs first, writes `TopFiles` JSON + UPSERTs the top-N MediaFiles rows.
4. Extend `_BuildActiveScans` in `TeamStatusController` to include `TopFiles` (parsed) on each ActiveScan entry.
5. Rewrite scan-row rendering in `Templates/Activity.html`: new `<tbody>` section with scan-appropriate columns, top-5 largest files inline below each row.
6. Deploy to larry + restart WebService; smoke-test against a real scan on each of T:\, M:\, Z:\; observe top-N populated within 30s.
7. Doc sweep: update `FileScanning.flow.md` for the new phase + dispatch fix; update `FileScanning.feature.md` criterion text where the phase chain is named.
