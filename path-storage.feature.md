# Feature: OS-Independent Path Storage (canonical (RootId, RelativePath))

## What It Does

Stores file paths in the database as `(RootId, RelativePath)` instead of OS-shaped absolute paths (`T:\…`). Each worker resolves its own absolute path per registered root at I/O time. The canonical schema is OS-independent; drive letters and mount prefixes never appear in any data row.

Today's schema stores Windows-shaped paths (`T:\Show\file.mkv`) as the canonical form, forcing every non-Windows worker through `PathTranslationService`. The translation layer works but it is a workaround for a schema decision, not a feature. This doc captures the target architecture and the [BUG] criterion that defines "fixed".

## Concern

See `KNOWN-ISSUES.md` -- single source of truth for the diagnosis, the current workaround, and the symptoms (271+ "Path does not exist, cannot normalize" log hits, 80+ FFprobe-failed hits, 3 "/bin/sh: 1: C:CodeAutomation..." Linux failures, 439 "FFmpeg path from settings not found" hits). Do not re-describe the problem here or in any other doc -- link to KNOWN-ISSUES.md.

## Success Criteria

1. **[BUG]** No row in any DB table contains a drive letter or backslash in a path field. Verifiable: `SELECT COUNT(*) FROM MediaFiles WHERE FilePath ~ '^[A-Za-z]:' OR FilePath LIKE '%\\\\%'` returns 0; same query against `TranscodeQueue.FilePath`, `TranscodeAttempts` path columns, `RootFolders.RootFolder`, `ShowSettings.ShowFolder`, and any future schema addition with a path-shaped column. CI lint refuses any new column that stores an OS-shaped path.

2. Path storage shape is `(RootId BIGINT REFERENCES RootFolders(Id), RelativePath TEXT)`. RelativePath uses forward slashes, no leading slash, no drive letter, no trailing slash, no `..` segments. Verifiable: schema dump shows the column shape; CHECK constraint enforces format on every path-bearing table.

3. A new worker on a new OS (mac, BSD, second Linux distro with different mount layout) is added by inserting one `RootFolderResolutions` row per registered root. No code change. Verifiable: deploy a third-OS worker against a clean migration; it picks up jobs and reads/writes correct files end-to-end.

4. The path-translation layer reduces to a join: `Resolve(RootId, RelativePath, WorkerName) -> AbsolutePath`. No drive-letter parsing. No regex. Verifiable: surviving translation code is < 50 LOC and contains zero references to "drive", "letter", or `[A-Za-z]:`. `WorkerShareMappings` table is dropped (replaced by `RootFolderResolutions`).

5. Operator-facing display still shows a human-readable path. The UI computes `Resolve(RootId, RelativePath, DisplayWorkerName)` for rendering. Verifiable: the Activity / Queue / SQLQueries pages display absolute paths exactly as today, but the source columns are `(RootId, RelativePath)`.

(Additional criteria appended when `/n` is invoked. This stub exists to anchor the [BUG] criterion and act as the destination for cross-doc links.)

## Status

**NOT STARTED** -- diagnosis recorded in `KNOWN-ISSUES.md` (single source of truth for this issue). Workaround is in production and working. Use `/n` to begin the design pass.

### Progress

- [x] 1. Diagnose OS coupling in canonical path storage
- [x] 2. Record critical bug + workaround in `KNOWN-ISSUES.md` as the single source of truth
- [x] 3. Create this stub with the [BUG] criterion that defines "fixed"
- [x] 4. Point existing related docs (`Core/WorkerContext.feature.md`, `deploy/worker-deploy.feature.md`, `deploy/worker-deploy.flow.md`) at the source of truth
- [ ] 5. `/n` to design the migration: `RootFolderResolutions` table, schema changes to every path-bearing table, backfill script, code touch list
- [ ] 6. Operator approval of full criteria set
- [ ] 7. Implement (real project -- expect 8-12 substeps once /n produces the plan)

## Scope

Cross-cutting. Every feature that reads or writes a path column is in scope. Concrete file globs will be enumerated when `/n` is invoked.

## Files

- `KNOWN-ISSUES.md` -- single source of truth for the diagnosis, workaround, and symptom inventory.
- `Core/WorkerContext.feature.md` -- documents the runtime workaround (PathTranslation singleton).
- `deploy/worker-deploy.feature.md` -- documents the boot-side workaround (WorkerShareMappings registration from env var).
- `deploy/worker-deploy.flow.md` -- documents the `MEDIAVORTEX_SHARE_MAPPINGS` env-var convention (step 11b).
- `Services/PathTranslationService.py` -- the workaround code.
- `Core/WorkerContext.py` -- the singleton holding the translation table.
- Database schema: `RootFolders`, `WorkerShareMappings`, and every path column on `MediaFiles`, `TranscodeQueue`, `TranscodeAttempts`, `ShowSettings`, `MediaFilesArchive`.
