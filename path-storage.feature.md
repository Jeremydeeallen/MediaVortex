# Feature: OS-Independent Path Storage (canonical `(RootId, RelativePath)`)

## What It Does

Stores file paths in the database as `(RootId, RelativePath)` instead of OS-shaped absolute paths (`T:\…`). Each worker resolves its own absolute path per registered root at I/O time. The canonical schema is OS-independent; drive letters and mount prefixes never appear in any data row.

Today's schema stores Windows-shaped paths (`T:\Show\file.mkv`) as the canonical form, forcing every non-Windows worker through `PathTranslationService`. The translation layer works but it is a workaround for a schema decision, not a feature. This doc captures the target architecture and the migration plan that retires the workaround.

## Concern

See `KNOWN-ISSUES.md` — single source of truth for the diagnosis, the current workaround, and the symptoms (271+ "Path does not exist, cannot normalize" log hits, 80+ FFprobe-failed hits, 3 "/bin/sh: 1: C:CodeAutomation..." Linux failures, 439 "FFmpeg path from settings not found" hits, plus the tonight-of-2026-05-11 discoveries: Z:\Videos prefix mismatch, LocalSourcePath/LocalOutputPath misnamed columns storing canonical values, malformed `\staging\<worker>\T:\…` paths in legacy attempts). Do not re-describe the problem here.

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

13. **The KNOWN-ISSUES entry is marked RESOLVED at end of Phase 5**. The entry moves from `## Open` to `## Resolved` with a date and a one-line summary of the resolution. Verifiable: read `KNOWN-ISSUES.md` after Phase 5 merges.

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
| `Features/QualityTesting/QualityTestingBusinessService.py:BuildVMAFCommand` | reads `JobDetails["LocalSourcePath"]` directly | reads `(RootId, RelativePath)` + Resolve |
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

**NOT STARTED** — design pass complete. Awaiting operator approval of criteria before any code lands.

### Progress

- [x] 1. Diagnose OS coupling in canonical path storage (KNOWN-ISSUES single source of truth)
- [x] 2. Record critical bug + workaround in KNOWN-ISSUES.md
- [x] 3. Create stub with [BUG] criterion (criterion 1)
- [x] 4. Point existing related docs at the source of truth
- [x] 5. `/n` design pass: RootFolderResolutions schema, 5-phase migration, code touch list, backfill strategy, validation criteria — THIS DOC
- [ ] 6. **Operator approval of criteria** (REQUIRED before code)
- [ ] 7. **Phase 1 — Schema additive**:
  - `Scripts/SQLScripts/AddPathStorageColumns.py` — adds `RootId`+`RelativePath` (nullable, no CHECK yet) to MediaFiles, TranscodeQueue, TranscodeAttempts, TemporaryFilePaths, ShowSettings, MediaFilesArchive
  - Creates `RootFolderResolutions` table
  - Idempotent migration, runs cleanly on fresh + existing DB
- [ ] 8. **Phase 1 — RootFolderResolutions seed**:
  - `Scripts/SQLScripts/SeedRootFolderResolutions.py` — translates current `WorkerShareMappings` rows into `RootFolderResolutions`; also reads `Workers.ShareCanonicalPrefix` for default Windows mappings
- [ ] 9. **Phase 2 — Backfill**:
  - `Scripts/SQLScripts/BackfillPathStorage.py` — per the strategy above
  - Validation report: matched/orphan counts per table; operator reviews orphans
- [ ] 10. **Phase 3 — Dual-write**: enumerated writer touch list above. One PR per feature vertical (FileScanning, TranscodeQueue admission, ProcessTranscodeQueueService, etc.). Each writes both old `FilePath` and new `(RootId, RelativePath)`; logs WARNING on drift.
- [ ] 11. **Phase 3 burn-in**: run for a fleet-week. Validate that no drift WARNINGs accumulate. Validate that all new rows have `(RootId, RelativePath)` populated. If passing, advance.
- [ ] 12. **Phase 4 — Read switch**: enumerated reader touch list above. One PR per consumer. Each reads `(RootId, RelativePath)` via Resolve; activates CHECK constraints; legacy `FilePath` stops being read.
- [ ] 13. **Phase 4 burn-in**: run for a fleet-week. Validate paths resolve correctly for all I/O. Tail logs for any "file not found" regressions.
- [ ] 14. **Phase 5 — Cleanup**:
  - `Scripts/SQLScripts/DropLegacyPathColumns.py` — drops `FilePath` from each table, drops `WorkerShareMappings`, drops `Workers.ShareCanonicalPrefix`/`ShareMountPrefix`
  - Delete `Services/PathTranslationService.py` (or shrink to <50 LOC wrapper)
  - Delete `MEDIAVORTEX_SHARE_MAPPINGS` env var handling
  - Mark `KNOWN-ISSUES` entry RESOLVED with date
- [ ] 15. Update `Core/WorkerContext.feature.md`, `deploy/worker-deploy.feature.md`, `deploy/worker-deploy.flow.md`, `CLAUDE.md` to reflect the new model

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
Services/PathTranslationService.py                  (shrunk or deleted in Phase 5)
Core/WorkerContext.py                               (PathTranslation singleton -> Resolve wrapper)
WorkerService/Main.py                               (boot path -- load RootFolderResolutions)

Tests/Contract/                                     (fixture + assertion updates)

path-storage.feature.md                             (this doc)
KNOWN-ISSUES.md                                     (entry moves to Resolved post-Phase 5)
Core/WorkerContext.feature.md                       (doc update)
deploy/worker-deploy.feature.md                     (doc update -- no env var)
deploy/worker-deploy.flow.md                        (step 11b retired)
CLAUDE.md                                           (canonical-format paragraph)
```

## Files

| File | Role |
|---|---|
| `path-storage.feature.md` | This doc — design + criteria + phase plan |
| `KNOWN-ISSUES.md` | Source of truth for the bug being fixed; moves to Resolved post-Phase 5 |
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
| `deploy/worker-deploy.flow.md` | Doc update — step 11b retired |
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
