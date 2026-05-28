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

Active 2026-05-28 -- shipped and verified live; operator UX confirmation pending.

Shipped 2026-05-28 (commit 7e0919c):
- [x] 1. `Scripts/SQLScripts/AddScanJobsTopFiles.py` run against live DB. ScanJobs.TopFiles JSONB column added (nullable). `SystemSettings('SizeSurveyTopN', '100')` seeded.
- [x] 2. `ContinuousScanService._GetTopLevelFolders` rewritten to dedupe on Windows-style backslash separators directly (no `os.sep` / `os.path.normpath`). Smoke-tested locally: 9 mixed inputs (T:\, T:\30 Rock, T:\FBI, T:\\, M:\, M:\Saving Private Ryan, Z:\, Z:\Some Folder, dupes) collapse to exactly 3 share roots.
- [x] 3. `FileScanningBusinessService._RunSizeSurvey` -- heap-based top-N (`heapq.heappushpop`, O(N log K)); media-extension filter; excluded-directory honored; `os.scandir` recursive (no `subprocess`, cross-platform). UPSERTs by `(StorageRootId, LOWER(RelativePath))`; preserves Id on existing rows; refreshes SizeMB + FileSize + FileModificationTime + FilePath + FileName. Writes JSON array to `ScanJobs.TopFiles` at completion. `_SetPhase('SizeSurvey')` then `_SetPhase('Walking')` bracket the call; any exception is caught and logged so the full scan still proceeds.
- [x] 4. `_BuildActiveScans` selects `TopFiles` and emits the top-5 entries per ActiveScan in the /api/TeamStatus/Overview payload.
- [x] 5. `Templates/Activity.html` rewrite: dedicated `<div id="ActiveScansBlock">` under the Active Jobs card with scan-appropriate columns (Drive | Worker | Phase | Progress | Files | Rate | ETA | Stop). Inline top-5 largest files render under each row with size labels. Phase badge color-coded per phase. Old "cram into transcode columns" `RenderScanRow` removed.
- [x] 6. Deployed to larry (image tag `cf9ea19` -- file sync via tar-over-ssh, latest code in container). WebService restarted. Worker containers restarted post-deploy to clear deploy-time zombie ScanJobs rows (old-container final heartbeat overwriting Stopped -- known race from the prior directive). Fresh scans 73180/73181/73182 verified end-to-end: three workers each picked a distinct share root (M:\, T:\, Z:\); each SizeSurvey completed and persisted `TopFiles` (length 100) within ~30s; Phase advanced to Walking with correct ProcessedFiles vs TotalFiles counters.
- [x] 7. Doc sweep: `FileScanning.flow.md` updated -- new "1.5. SizeSurvey" pipeline row; State Surface lists SizeSurvey in the Phase enum and adds the TopFiles column. `FileScanning.feature.md` did not name the prior phase chain explicitly, so no edit needed there. Prior directive at `.claude/directives/closed/2026-05-27-active-scan-visibility.md` already marked Closed -- Partial with the supersession pointer.

Verified live data (from the three fresh post-deploy scans):
- M:\ top file: *Saving Private Ryan (1998) Bluray-2160p.mkv* @ 10.6 GB
- T:\ top file: *Westworld - S01E10 - The Bicameral Mind Bluray-1080p.mkv* @ 7.8 GB
- Z:\ top file: 22.0 GB
- TopFiles length: 100 on all three (matches SizeSurveyTopN setting)
- Phase transition observable: SizeSurvey -> Walking happened within 30s of scan start
- Dispatch fix: three workers picked three distinct share roots on the same restart tick

Operator-pending verification:
- Refresh /Activity in a browser. Expected: Active Scans block with three rows (T:\, M:\, Z:\); each row shows phase badge, progress bar, files counters; under each row a "Largest files found" inline list of 5 entries with sizes. If the rendering doesn't match -- or if the layout is still wrong -- report and I'll iterate.

Close (Success) when operator confirms the UI render is what they want.
