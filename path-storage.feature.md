# Feature: OS-Independent Path Storage (canonical `(RootId, RelativePath)`)

**Slug:** path-storage

## What It Does

Stores file paths in the database as `(RootId, RelativePath)` instead of OS-shaped absolute paths (`T:\…`). Each worker resolves its own absolute path per registered root at I/O time. The canonical schema is OS-independent; drive letters and mount prefixes never appear in any data row.

Today's schema stores Windows-shaped paths (`T:\Show\file.mkv`) as the canonical form, forcing every non-Windows worker through `PathTranslationService`. The translation layer works but it is a workaround for a schema decision, not a feature. This doc captures the target architecture and the migration plan that retires the workaround.

## Concern

See `memory/KNOWN-ISSUES.md` — single source of truth for the diagnosis, the current workaround, and the symptoms (271+ "Path does not exist, cannot normalize" log hits, 80+ FFprobe-failed hits, 3 "/bin/sh: 1: C:CodeAutomation..." Linux failures, 439 "FFmpeg path from settings not found" hits, plus the tonight-of-2026-05-11 discoveries: Z:\Videos prefix mismatch, LocalSourcePath/LocalOutputPath misnamed columns storing canonical values, malformed `\staging\<worker>\T:\…` paths in legacy attempts). Do not re-describe the problem here.

## Target Schema

```sql
-- IMPORTANT: existing RootFolders table is the PER-SHOW SCAN REGISTRY (110+
-- rows like 'T:\The IT Crowd', 'T:\The Mandalorian'). It is NOT the share-
-- root table. The path-storage rewrite introduces a NEW StorageRoots table
-- for share roots; RootFolders stays as-is for scan targeting.

-- NEW table: share-root registry (one row per logical share)
StorageRoots
  Id              BIGSERIAL PRIMARY KEY
  Name            TEXT NOT NULL UNIQUE        -- 'media_tv', 'movies', 'xxx'
  Description     TEXT
  CanonicalPrefix TEXT NOT NULL UNIQUE        -- 'T:\' or '\\10.0.0.61\xxx\' -- informational, used by backfill

-- NEW table: per-(storage-root x worker) resolution
StorageRootResolutions
  Id              BIGSERIAL PRIMARY KEY
  StorageRootId   BIGINT NOT NULL REFERENCES StorageRoots(Id) ON DELETE CASCADE
  WorkerName      TEXT NOT NULL                -- or '__default__' fallback
  Platform        TEXT NOT NULL                -- 'windows' | 'linux' | 'mac'
  AbsolutePath    TEXT NOT NULL                -- 'T:\' or '/mnt/media_tv/' or '/Volumes/media_tv/'
  IsActive        BOOLEAN NOT NULL DEFAULT TRUE
  UNIQUE (StorageRootId, WorkerName)

-- Every path-bearing table gains two columns:
MediaFiles, TranscodeQueue, TranscodeAttempts, TemporaryFilePaths,
ShowSettings, MediaFilesArchive
  ADD COLUMN StorageRootId  BIGINT REFERENCES StorageRoots(Id)
  ADD COLUMN RelativePath   TEXT
  -- with a CHECK constraint (activated in Phase 4) enforcing format:
  --   no leading slash/backslash, forward slashes only, no '..',
  --   no drive letter (no `[A-Za-z]:` prefix)
```

After migration:

- `Resolve(StorageRootId, RelativePath, WorkerName) -> AbsolutePath` is the only path-resolution path. Single function. < 30 LOC.
- `WorkerShareMappings` table is dropped.
- `Workers.ShareCanonicalPrefix`, `Workers.ShareMountPrefix` are dropped.
- `PathTranslationService` shrinks to a thin Resolve wrapper or is deleted entirely.
- `MEDIAVORTEX_SHARE_MAPPINGS` env var is retired (worker reads its `StorageRootResolutions` rows on boot).
- Legacy `FilePath` columns are dropped from every table.

## Migration Phases (reversible until Phase 5)

| Phase | What changes | Reversible? | Production impact |
|---|---|---|---|
| **1. Schema additive** | Create `RootFolderResolutions`. Add `RootId`+`RelativePath` (nullable) to every path-bearing table. CHECK constraints not yet active. | Yes — drop new columns/table | None — old code still operates on `FilePath` |
| **2. Backfill** | Seed `RootFolderResolutions` from current `WorkerShareMappings` + `Workers.ShareCanonicalPrefix`. Backfill `RootId`+`RelativePath` on every existing row by parsing `FilePath` against `RootFolders` and stripping the root prefix. Flag orphan rows (no matching root) with `RootId IS NULL`. | Yes — UPDATE all rows back to NULL on new columns | None — read path unchanged |
| **3. Dual-write** | Every path-writing site writes BOTH `FilePath` and `(RootId, RelativePath)`. Code asserts they agree (logs WARNING on drift). | Yes — revert to single-write | None — readers still use `FilePath` |
| **4. Read switch** | Every path-reading site uses `Resolve(RootId, RelativePath, WorkerName)`. `FilePath` becomes a dead column, written but never read. Activate CHECK constraints on `(RootId, RelativePath)`. | Yes — flip readers back to FilePath; CHECK constraints still pass | None visible — paths resolve identically |
| **5. Cleanup** | Drop `FilePath` columns. Drop `WorkerShareMappings`. Drop `Workers.ShareCanonicalPrefix`, `Workers.ShareMountPrefix`. Strip `PathTranslationService`. Mark `KNOWN-ISSUES` entry RESOLVED. | **No — destructive** | None if Phases 1-4 verified |

Each phase merges separately. Each phase has its own validation criterion. Phase 5 only runs when Phases 1-4 have been observed in production for a defined burn-in period.

## Success Criteria

1. **[BUG]** No row in any DB table contains a drive letter or backslash in a path field. Verifiable: `SELECT COUNT(*) FROM MediaFiles WHERE FilePath ~ '^[A-Za-z]:' OR FilePath LIKE '%\\\\%'` returns 0; same query against `TranscodeQueue.FilePath`, `TranscodeAttempts` path columns, `RootFolders.RootFolder`, `ShowSettings.ShowFolder`, and any future schema addition with a path-shaped column. CI lint refuses any new column that stores an OS-shaped path. (Stub criterion 1.)

2. **Storage shape**. Path storage is `(RootId BIGINT REFERENCES StorageRoots(Id), RelativePath TEXT)`. `RelativePath` uses forward slashes, no leading slash, no drive letter, no trailing slash, no `..` segments. Verifiable: schema dump shows the column shape; CHECK constraint enforces format on every path-bearing table. (Stub criterion 2.)

3. **New OS adds by data row**. A new worker on a new OS (mac, BSD, second Linux distro with different mount layout) is added by inserting one `RootFolderResolutions` row per registered root. No code change. Verifiable: deploy a third-OS worker against a clean migration; it picks up jobs and reads/writes correct files end-to-end. (Stub criterion 3.)

4. **Translation surviving code is small and OS-blind**. The path-translation layer reduces to `Resolve(RootId, RelativePath, WorkerName) -> AbsolutePath`. No drive-letter parsing. No regex. Verifiable: surviving translation code is < 50 LOC and contains zero references to `"drive"`, `"letter"`, or `[A-Za-z]:`. `WorkerShareMappings` table is dropped (replaced by `RootFolderResolutions`). (Stub criterion 4, expanded.)

5. **Operator-facing display unchanged**. Activity, Queue, SQLQueries, VmafCompare pages display absolute paths exactly as today, but the source columns are `(RootId, RelativePath)`. Verifiable: snapshot Activity / Queue / VmafCompare page HTML for the same rows before and after Phase 5; the visible path strings are character-equal (or differ only in path separator if intentional). (Stub criterion 5.)

6. **Backfill correctness**. For every existing row in `MediaFiles`, `TranscodeQueue`, `TranscodeAttempts`, `TemporaryFilePaths`, `ShowSettings`, and `MediaFilesArchive` that had a valid `FilePath` matching a known root, the backfill produces `(RootId, RelativePath)` such that `Resolve(RootId, RelativePath, ProducingWorker)` returns the original `FilePath` (string-equal after normalization). Verifiable: backfill validation script enumerates every row, calls Resolve against the originating worker, and asserts equality. Reports any drift.

7. **Orphan rows are flagged, not silently dropped**. Rows whose `FilePath` doesn't match any `RootFolders` entry are left with `RootId IS NULL` and counted. The operator reviews and either creates a new `RootFolders` entry + re-runs backfill, or marks them archival, BEFORE Phase 5 drops `FilePath`. Verifiable: pre-Phase-5 report shows the count of `RootId IS NULL` rows per table; operator approval of the orphan list is required to advance.

8. **Phases are reversible through Phase 4**. At any point in Phases 1-4, the migration can be rolled back without data loss by reverting code + dropping the new columns/table. Verifiable: a tagged "phase-N-checkpoint" branch exists; reverting to it on a test environment restores prior behavior. Phase 5 is explicitly destructive and requires green Phase 1-4 burn-in.

9. **Dual-write detects drift**. During Phase 3, every writer that sets `FilePath` also sets `(RootId, RelativePath)`. If they don't resolve to the same path on the producing worker, a WARNING is logged and the write is allowed to proceed (don't block production work, but surface the drift for diagnosis). Verifiable: insert a TranscodeAttempt with mismatched columns; observe the WARNING in the `Logs` table.

10. **RootFolderResolutions cardinality is enforced**. At most one active row per `(RootFolderId, WorkerName)`. A unique index enforces this. Verifiable: attempting to insert a duplicate `(RootFolderId, WorkerName)` pair fails with a constraint violation; deactivating an old row before adding a new one is the operator's path.

11. **`MEDIAVORTEX_SHARE_MAPPINGS` env var is retired**. Workers read their resolutions from `RootFolderResolutions` on boot. The env var is no longer consulted. Verifiable: grep of the surviving codebase for `MEDIAVORTEX_SHARE_MAPPINGS` returns zero hits outside docs and a single migration-helper that parses the legacy env var during initial RootFolderResolutions seeding.

12. **No backslashes anywhere in `RelativePath`**. Even on Windows. Even in display. The canonical form uses forward slashes; OS-specific separators only appear in resolved absolute paths at I/O time. Verifiable: `SELECT COUNT(*) FROM MediaFiles WHERE RelativePath LIKE '%\\\\%'` returns 0; same for every other path-bearing table.

13. **The KNOWN-ISSUES entry is marked RESOLVED at end of Phase 5**. The entry moves from `## Open` to `## Resolved` with a date and a one-line summary of the resolution. Verifiable: read `memory/KNOWN-ISSUES.md` after Phase 5 merges.

14. **No legacy path-translation references survive in code or docs.** Searching the entire repo for `Workers.ShareCanonicalPrefix`, `Workers.ShareMountPrefix`, `WorkerShareMappings`, `MEDIAVORTEX_SHARE_MAPPINGS`, `PathTranslationService`, `LocalMountPrefix`, `Drive Letter`, and `ShareCanonicalPrefix` returns hits only in: (a) this feature doc, (b) `memory/KNOWN-ISSUES.md`'s resolved entry, (c) git history. No commented-out code blocks referencing the legacy system. No historical strings in feature/flow docs that aren't explicitly tagged as historical. Verifiable: `grep -rn` the patterns above against `Features/`, `Services/`, `Repositories/`, `Core/`, `WorkerService/`, `Templates/`, `Scripts/`, `deploy/`, and root-level docs; expected match count is 0 outside the allowlist.

15. **DB is backed up before any destructive migration step (Phase 5).** `pg_dump` snapshot stored at a durable location (Larry filesystem outside the LXC, or another machine), timestamped, kept for at least 30 days. Phase 5 migration script refuses to run without verifying the backup file exists and is newer than 24 hours old. Verifiable: backup file exists at `/mnt/pve/Media/MediaVortex/backups/pre-phase5-<timestamp>.sql.gz` (or equivalent) with a manifest listing schema + row counts; restoring it on a sandbox produces a working pre-Phase-5 DB.

16. **Flow documents reference real code locations.** `path-storage.flow.md` and any updated `transcode.flow.md` / `worker-deploy-linux.flow.md` steps that touch path resolution name the actual function + file path being called at each step (e.g., "Step 4: source resolution via `PathStorage.Resolve(StorageRootId, RelativePath, WorkerName)` -- `Core/PathStorage.py:Resolve`"). Verifiable: pick any 5 path-resolution steps from any flow doc; each names a function that exists at the referenced location and is on the actual execution path for that step.

17. **End-of-rewrite code walk done before fleet deploy.** Operator walks each flow doc top-to-bottom against the live code; signs off in writing (a comment in this feature doc's Progress checklist, or a dated note in `## Status`). Workers are not redeployed to the new image until the walk is complete and signed off. Verifiable: this feature doc's Progress checklist has a checked item naming the walk date + signer.

## Code Touch List

Writers (set paths into DB rows):

| Site | What writes today | Phase 3+ change |
|---|---|---|
| `Features/FileScanning/FileScanningBusinessService.py` | `INSERT INTO MediaFiles ... FilePath` | dual-write `(RootId, RelativePath)`, then read-switch |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | bulk INSERT into `TranscodeQueue` from `MediaFiles` rows | propagate `(RootId, RelativePath)` from source |
| `Features/QualityTesting/QualityTestController.py:QueueTestRun` | INSERT new `TranscodeQueue` row from operator submission | look up `(RootId, RelativePath)` from MediaFiles row |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py` | INSERT `TranscodeAttempts`, `TemporaryFilePaths` | write `(RootId, RelativePath)` for source AND output |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py:_VariantizeOutputPath` | computes `-test-<name>-mv` output filename | unchanged (operates on the RelativePath portion) |
| `Features/QualityTesting/QualityTestingBusinessService.py` | INSERT `QualityTestingQueue` via `AddToQualityTestQueue` | write `(RootId, RelativePath)` for source + transcoded |
| `Features/FileReplacement/FileReplacementBusinessService.py` | UPDATE `MediaFiles.FilePath` post-replacement | UPDATE `RelativePath` (RootId is stable) |
| `Features/MediaProbe/MediaProbeBusinessService.py` | UPDATE `MediaFiles` post-probe | path columns untouched (probe doesn't move the file) |
| `Models/CommandBuilder.py:GenerateOutputFileName` | generates output filename string | unchanged (operates on basename) |
| `Repositories/DatabaseManager.py` | various INSERT helpers (`CreateQualityTestQueueEntry`, etc.) | accept `(RootId, RelativePath)` instead of `FilePath` strings |

Readers (consume paths from DB rows):

| Site | What reads today | Phase 4 change |
|---|---|---|
| `Features/TranscodeJob/ProcessTranscodeQueueService.py:GetMediaFileData` | reads `MediaFile.FilePath` | reads `(RootId, RelativePath)` + calls `Resolve` |
| `Features/QualityTesting/QualityTestingBusinessService.py:BuildVMAFCommand` | reads `(SourceStorageRootId, SourceRelativePath)` + `(OutputStorageRootId, OutputRelativePath)` from `TemporaryFilePaths`, constructs `Path` instances, calls `Path.Resolve(Worker)` for the local strings handed to ffmpeg | unchanged -- the typed-pair -> Resolve chain is the steady state |
| `Features/FileReplacement/FileReplacementBusinessService.py` | path lookups for source/encoded/archive | Resolve at each I/O |
| `Features/MediaProbe/MediaProbeBusinessService.py:_ExecuteProbe` | reads `MediaFile.FilePath` for FFprobe | Resolve before FFprobe call |
| `Features/QualityTesting/QualityTestController.py:CompareStills` (+ batch + test bench) | path lookups for slider stills | Resolve before FFmpeg extract |
| `Templates/Activity.html`, `Templates/Queue.html`, `Templates/VmafCompare.html`, etc. | display `FilePath` in tables | display `Resolve(RootId, RelativePath, DisplayWorker)` via the controllers that feed those pages |
| `Features/Activity/ActivityController.py`, `Features/TeamStatus/TeamStatusController.py`, `Features/SQLQueries/SQLQueriesController.py` | SELECT and surface paths to UI | join + Resolve in the controller layer |
| `Services/PathTranslationService.py` | the existing translation logic | shrunk to thin Resolve wrapper or deleted |
| `Core/WorkerContext.py:PathTranslation` | singleton holding the legacy mapping | replaced by RootFolderResolutions lookup |
| Tests `Tests/Contract/*.py` | reference paths in fixtures + assertions | update fixtures to `(RootId, RelativePath)`; assertions go through Resolve |

Surface estimate: **~15-20 files with real changes, ~5-10 cosmetic**. The DatabaseManager helper layer is the bulk of the change (writers + readers both go through it).

## Backfill Strategy

`Scripts/SQLScripts/BackfillPathStorage.py` runs after Phase 1 schema migration. It:

1. Reads every `RootFolders` row + its current `RootFolder` (the prefix, e.g. `T:\`).
2. For each row in `MediaFiles` (and other path-bearing tables), parses `FilePath`:
   - Tries each root prefix in order of length (longest first, to avoid `T:\` matching when `T:\Subdir\` is more specific).
   - On match, computes `RelativePath = FilePath - prefix`, normalizes to forward slashes, sets `RootId`.
   - On no match: leaves `RootId = NULL` and `RelativePath = NULL` (orphan flag).
3. Reports: total rows, matched count per `RootId`, orphan count, sample of orphans for operator review.
4. Idempotent: re-running doesn't change rows that already have `(RootId, RelativePath)` populated, unless `--force` is passed.

The orphan list is the operator's signal: add a new RootFolders entry covering that prefix (then re-run backfill) or accept those rows are archival.

## Status

**PHASE 8 COMPLETE (column rename cutover).** The `path-schema-migration` directive
is the source of truth for the cutover that landed 2026-06-04. Legacy columns
(`FilePath`, `OriginalPath`, `LocalSourcePath`, `LocalOutputPath`, `ShowFolder`)
were renamed in PostgreSQL to `_legacy_<col>`; production code reads/writes only
`(StorageRootId, RelativePath)`. Display uses `Path.CanonicalDisplay(GetPrefixMap())`;
worker-local I/O uses `Path.Resolve(Worker)`. `Services/PathTranslationService.py`
remains in use by a few legacy verticals; full deprecation runs in
`path-perfect-implementation` Step 3.

**PATH-PERFECT-IMPLEMENTATION STEP 1 COMPLETE (2026-06-05).** Schema extended:
`RootFolders` + `ScanJobs` both gained `StorageRootId BIGINT REFERENCES StorageRoots(Id)`
+ `RelativePath TEXT` columns. Backfill via `Path.FromLegacyString`: 538/538
RootFolders + 73,180/73,180 ScanJobs carry the typed pair. Two malformed historical
ScanJobs rows (terminal status, wrong-separator legacy strings) were deleted as
operator-data cleanup. Legacy columns (`RootFolders.RootFolder`,
`ScanJobs.RootFolderPath`) stay populated; dual-write lands in Step 2; legacy
column drop lands in Step 6.

### Progress

- [x] 1. Diagnose OS coupling in canonical path storage (KNOWN-ISSUES single source of truth)
- [x] 2. Record critical bug + workaround in memory/KNOWN-ISSUES.md
- [x] 3. Create stub with [BUG] criterion (criterion 1)
- [x] 4. Point existing related docs at the source of truth
- [x] 5. `/n` design pass: StorageRootResolutions schema, 5-phase migration, code touch list, backfill strategy, validation criteria — THIS DOC
- [x] 6. **Operator approval of criteria** (implicit — Phases 1-3 ran in production; doc was never updated to reflect approval timing)
- [x] 7. **Phase 1 — Schema additive** (verified 2026-05-15):
  - MediaFiles has `StorageRootId BIGINT` + `RelativePath TEXT` columns present
  - `StorageRoots` table exists (3 rows: media_tv→T:\, movies→M:\, xxx→Z:\)
  - Other path-bearing tables (TranscodeQueue, TranscodeAttempts, TemporaryFilePaths, ShowSettings, MediaFilesArchive) — column presence not re-verified in this audit; check before any Phase 4 work
- [x] 8. **Phase 1 — StorageRootResolutions seed** (verified 2026-05-15):
  - `StorageRootResolutions` table exists, 54 rows (per-worker per-root mappings)
  - `WorkerShareMappings` (48 rows) coexists for backward compatibility
- [x] 9. **Phase 2 — Backfill** (verified 2026-05-15):
  - 59,128 of 59,130 MediaFiles rows have `StorageRootId` (~99.997%); 2 orphans remain — review and either add a covering StorageRoot or accept as archival before Phase 5
  - All 59,130 rows have `RelativePath`
  - Backfill on other path-bearing tables not re-verified; run a fresh report before Phase 4 advances
- [ ] 10. **Phase 3 — Dual-write** (PARTIAL, 2026-05-15):
  - **VERIFIED** FileScanning vertical: `FileScanningRepository.SaveMediaFile` (lines 410 INSERT + 418 UPDATE) writes both `FilePath` AND `StorageRootId, RelativePath`. `FileScanningBusinessService` line 788 computes the new columns via `PathParse(FilePath, LoadStorageRoots())`.
  - **UNVERIFIED** writer verticals: TranscodeQueue admission, ProcessTranscodeQueueService, FileReplacement post-flight writers, MediaProbe, MediaFilesArchive, TemporaryFilePaths producers. Each needs a grep + code-walk to confirm dual-write before Phase 3 burn-in can be declared green.
  - **DRIFT WARNING NOT CONFIRMED** — the criterion-9 contract requires a logged WARNING when `FilePath` and `(StorageRootId, RelativePath)` resolve to different paths. Need to verify the WARNING is wired in and observe the Logs table for accumulation patterns.
- [ ] 11. **Phase 3 burn-in**: run for a fleet-week. Validate that no drift WARNINGs accumulate. Validate that all new rows have `(RootId, RelativePath)` populated. If passing, advance.
- [ ] 12. **Phase 4 — Read switch**: enumerated reader touch list above. One PR per consumer. Each reads `(RootId, RelativePath)` via Resolve; activates CHECK constraints; legacy `FilePath` stops being read.
  - [x] **2026-05-15:** First consumer migrated -- `Features/FileScanning/FileScanningBusinessService.py::ReconcileWithDisk` set membership now keyed on `(StorageRootId, RelativePath.lower())` tuples (via `Core.PathStorage.Parse`), not on OS-coupled `FilePath` strings. NULL-StorageRootId rows preserved. Safety guard: aborts if >90% of rows would be deleted. Remaining consumers (queue admission, transcode-job source resolution, file replacement, archive writers, etc.) still on legacy `FilePath` reads -- one PR per vertical.
- [ ] 13. **Phase 4 burn-in**: run for a fleet-week. Validate paths resolve correctly for all I/O. Tail logs for any "file not found" regressions.
- [ ] 13b. **DB backup (REQUIRED before Phase 5)**: `pg_dump` the entire `mediavortex` DB to a durable location (e.g., `/mnt/pve/Media/MediaVortex/backups/pre-phase5-<timestamp>.sql.gz`). Verify size + sample restore. `Scripts/SQLScripts/DropLegacyPathColumns.py` refuses to run without a fresh backup.
- [ ] 13c. **Code walk against flow docs**: walk `path-storage.flow.md`, `transcode.flow.md`, `worker-deploy-linux.flow.md` top-to-bottom; verify every path-resolution step matches the running code; record a dated sign-off in this checklist.
- [ ] 14. **Phase 5 — Cleanup** (gated on 13b + 13c sign-off):
  - `Scripts/SQLScripts/DropLegacyPathColumns.py` — drops `FilePath` from each table, drops `WorkerShareMappings`, drops `Workers.ShareCanonicalPrefix`/`ShareMountPrefix`. First operation: verify backup file exists + is recent + checksum matches manifest; exit if not.
  - Delete `Services/PathTranslationService.py` (or shrink to <50 LOC wrapper)
  - Delete `MEDIAVORTEX_SHARE_MAPPINGS` env var handling
  - Grep + delete all remaining references to retired symbols (`ShareCanonicalPrefix`, `WorkerShareMappings`, etc.) from code and docs per criterion 14
  - Mark `KNOWN-ISSUES` entry RESOLVED with date
- [ ] 15. Update `Core/WorkerContext.feature.md`, `deploy/worker-deploy.feature.md`, `deploy/worker-deploy-linux.flow.md`, `CLAUDE.md` to reflect the new model

## Scope

Cross-cutting. Every code surface that reads or writes a path column. Concrete file globs:

```
Scripts/SQLScripts/AddPathStorageColumns.py        (NEW)
Scripts/SQLScripts/SeedRootFolderResolutions.py    (NEW)
Scripts/SQLScripts/BackfillPathStorage.py          (NEW)
Scripts/SQLScripts/DropLegacyPathColumns.py        (NEW, Phase 5)

Features/FileScanning/                              (writer)
Features/TranscodeQueue/                            (writer)
Features/TranscodeJob/                              (writer + reader)
Features/QualityTesting/                            (writer + reader)
Features/FileReplacement/                           (writer + reader)
Features/MediaProbe/                                (reader)
Features/Activity/                                  (reader + UI)
Features/TeamStatus/                                (reader + UI)
Features/SQLQueries/                                (reader + UI)
Templates/                                          (display layer)

Repositories/DatabaseManager.py                     (helpers)
Models/CommandBuilder.py                            (output filename)
Services/PathTranslationService.py                  (still in use; full deprecation deferred to Phase 9)
Core/WorkerContext.py                               (PathTranslation singleton -> Resolve wrapper)
WorkerService/Main.py                               (boot path -- load RootFolderResolutions)

Tests/Contract/                                     (fixture + assertion updates)

path-storage.feature.md                             (this doc)
memory/KNOWN-ISSUES.md                                     (entry moves to Resolved post-Phase 5)
Core/WorkerContext.feature.md                       (doc update)
deploy/worker-deploy.feature.md                     (doc update -- no env var)
deploy/worker-deploy-linux.flow.md                        (step 11b retired)
CLAUDE.md                                           (canonical-format paragraph)
```

## Files

| File | Role |
|---|---|
| `path-storage.feature.md` | This doc — design + criteria + phase plan |
| `memory/KNOWN-ISSUES.md` | Source of truth for the bug being fixed; moves to Resolved post-Phase 5 |
| `Scripts/SQLScripts/AddPathStorageColumns.py` | Phase 1 schema migration |
| `Scripts/SQLScripts/SeedRootFolderResolutions.py` | Phase 1 seed from existing `WorkerShareMappings` |
| `Scripts/SQLScripts/BackfillPathStorage.py` | Phase 2 row-by-row backfill + orphan report |
| `Scripts/SQLScripts/DropLegacyPathColumns.py` | Phase 5 destructive cleanup |
| All Features/ paths above | Phase 3 / Phase 4 writers + readers |
| `Templates/*.html` | Display layer for paths (reads from controller-resolved values) |
| `Repositories/DatabaseManager.py` | Helper layer that accepts `(RootId, RelativePath)` instead of literal `FilePath` |
| `Services/PathTranslationService.py` | Shrunk to Resolve wrapper or deleted |
| `Core/WorkerContext.py` | Simplified — PathTranslation becomes a thin `Resolve(RootId, RelativePath)` |
| `WorkerService/Main.py` | Boot path reads `RootFolderResolutions` rows for this worker |
| `Core/WorkerContext.feature.md` | Doc update — workaround section retired |
| `deploy/worker-deploy.feature.md` | Doc update — env-var registration retired |
| `deploy/worker-deploy-linux.flow.md` | Doc update — step 11b retired |
| `Tests/Contract/*.py` | Fixture + assertion updates |

## Estimated Effort

| Phase | Duration | Risk |
|---|---|---|
| 1 (Schema additive + seed) | ~1 day | Low — additive only |
| 2 (Backfill + validation) | ~1 day | Medium — orphans need operator review |
| 3 (Dual-write, ~10 sites) | ~2 days | Medium — every writer needs touch |
| 3 burn-in | 3-5 days (calendar) | Low — read path unchanged |
| 4 (Read switch, ~10 sites) | ~2 days | Medium-high — readers swap underneath running workers |
| 4 burn-in | 3-5 days (calendar) | Low — equivalence already validated |
| 5 (Cleanup) | ~0.5 day | Low — by now everything works without legacy columns |

**Total focused work: ~6.5 days**. Total calendar including burn-ins: **~2-3 weeks** if running with normal observation cycles.

## Deviation from Conventions

None. Each criterion is observable from outside the codebase (SQL queries, grep, file-existence checks, page-render snapshots). No criterion references internal symbols by name except the to-be-deleted `PathTranslationService` and `WorkerShareMappings`, which are part of the deletion contract.
