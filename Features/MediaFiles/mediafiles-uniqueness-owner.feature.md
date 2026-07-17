# MediaFiles Persistence Layer

**Slug:** mediafiles-uniqueness-owner

## Interrupts: transcode-flow-canonical

## What It Does

Strips the MediaFiles persistence layer to a bulletproof minimum. Subtraction-only directive: no new abstractions, no merge machinery, no reconciliation logic. The DB owns concurrency via `INSERT ... ON CONFLICT DO UPDATE`; the code owns nothing more than mapping a `MediaFileModel` to columns.

Locks four invariants that make duplicate rows physically impossible and every writer path idempotent:

1. **One writer.** `MediaFilesRepository` is the sole writer of MediaFiles rows. Every producer (scanner, transcode replacement, admin scripts, backfills) calls `Upsert(model)`. No raw `INSERT`/`UPDATE`/`DELETE` on `MediaFiles` anywhere else.
2. **One statement.** `Upsert` is a single `INSERT ... ON CONFLICT (StorageRootId, LOWER(RelativePath)) DO UPDATE SET ...`. No SELECT-then-INSERT. No mirror between INSERT and UPDATE column lists. Postgres owns the race.
3. **One key.** Path identity = `(StorageRootId, LOWER(RelativePath))`. Case-insensitive. Stored `RelativePath` immutable except when the file is actually renamed on disk.
4. **Sole-writer boundary for `-mv` outputs.** Scanner never INSERTs rows for files whose basename ends `-mv.<ext>` — those are MediaVortex's own outputs, owned by `TranscodedOutputPlacement`. Scanner logs orphans, doesn't create them.

## Success Criteria

C1. `MediaFilesRepository.SaveMediaFile(model)` is the sole write method. Body rewritten as a single SQL statement: `INSERT ... ON CONFLICT (StorageRootId, LOWER(RelativePath)) DO UPDATE SET ...`. Column list appears exactly once. No SELECT-then-INSERT branch. Method body ≤ 40 lines. **Name preserved to avoid gratuitous 8-file caller sweep**; only body changes.

C2. `MediaFilesRepository._UpdateMediaFile` (43-line UPDATE mirror of INSERT) is deleted. Grep in `Features/MediaFiles/MediaFilesRepository.py` returns 0.

C3. `MediaFilesRepository.CleanupDuplicateMediaFiles` is deleted. Grep in `Features/` returns 0.

C4. Characterization test lands BEFORE `_UpdateMediaFilesAfterReplacement` is rewritten. `Tests/Contract/TestUpdateMediaFilesAfterReplacementSideEffects.py` pins every current side effect: (a) probe order, (b) resolution-tier classification, (c) `PostFlightRegistry.Get(Mode).Execute` call, (d) `AudioStateService.DetectNormalizationMode` derivation, (e) FileModificationTime + LastModifiedDate + FileSize re-stamp, (f) `MarkAudioComplete` post-normalize (outer Execute), (g) `NeedsReprobe = FALSE` clear. Test passes against current code + must pass against rewritten code.

C5. `TranscodedOutputPlacement._UpdateMediaFilesAfterReplacement` collapses to: probe → build `MediaFileModel` from probe dict → `SaveMediaFile(model)`. Method body ≤ 40 lines. No inline `DELETE FROM MediaFiles`. Resolution-tier ladder moves to `MediaFileModel` classification helper or pure function next to it. C4 characterization test still passes.

C6. Sole-writer grep invariant: `INSERT INTO MediaFiles`, `UPDATE MediaFiles`, `DELETE FROM MediaFiles` outside `Features/MediaFiles/MediaFilesRepository.py` return 0 across `Features/`, `Workers/`, `WorkerService/`, `WebService/`, `Repositories/`, `Core/`, `Scripts/`. Enforced by `Tests/Contract/TestMediaFilesSoleWriter.py`.

C7. Case-insensitive identity. Repeated `SaveMediaFile(model)` on same path with different casing hits the same row every time. Stored `RelativePath` reflects first-scanned casing; subsequent saves do not rewrite it. `Tests/Contract/TestMediaFilesUniqueness.py::test_case_insensitive_save` asserts.

C8. Case-fold sweep across all path-keyed lookups in `MediaFilesRepository`. `GetMediaFileByPath` and `DeleteMediaFileByPath` (currently case-sensitive `WHERE RelativePath = %s`) rewritten to `WHERE StorageRootId = %s AND LOWER(RelativePath) = LOWER(%s)`. Any additional path-keyed WHERE-clauses found at NEEDS_DOC_PREREAD get the same treatment. Symmetric with C1's ON CONFLICT case-fold. `Tests/Contract/TestMediaFilesUniqueness.py::test_case_insensitive_lookup_symmetry` asserts every lookup method hits the same row regardless of caller casing.

C9. `FileScanning` skips insertion for any file whose basename (post-extension-strip) ends `-mv`. Contract test seeds a `-mv.mp4` discovery event, asserts zero new rows inserted.

C10. `FileScanning` emits one `LoggingService.LogWarning` per `-mv` file with no matching row and returns without INSERT. Signals rollback failure elsewhere; does not silently accept orphans.

C11. `-mv` suffix literal is defined once in `Features/MediaFiles/MvSuffix.py` as `MV_OUTPUT_SUFFIX = '-mv'` plus one `IsMvOutput(basename) -> bool` helper. `OutputFilenameBuilder`, `FileScanning`, and `CollapseMvSuffix` import from this module. String literal `'-mv'` outside `MvSuffix.py` returns 0 in the production tree.

C12. Redundant `idx_mediafiles_typedpair_unique` (case-sensitive) is dropped. `SELECT COUNT(*) FROM pg_indexes WHERE tablename='mediafiles' AND indexname='idx_mediafiles_typedpair_unique'` = 0. Only `idx_mediafiles_storageroot_relpath_unique` (case-insensitive) remains.

C13. `CrashRecoveryService` bounded retry with fully-specified terminal-state rules:
- **Retry target key** = `(RecoveryOp, CanonicalOriginalPath)` — one file, one recovery operation.
- **Counter storage** = new column `CrashRecoveryAttempts.AttemptCount INT NOT NULL DEFAULT 0` in the existing recovery-tracking row; DB-persisted, survives service restart.
- **Reset condition** = `AttemptCount` resets to 0 on any successful completion of the same `(RecoveryOp, CanonicalOriginalPath)`.
- **Terminal threshold** = `AttemptCount >= 3` marks the row `TerminalFailure=TRUE`, logs one ERROR with full context, and is never re-selected by the recovery poll.
- **Manual signal** = a nightly `LoggingService.LogError` sweep enumerates `TerminalFailure=TRUE` rows so operators see backlog. No auto-clear.
`Tests/Contract/TestCrashRecoveryBoundedRetry.py` seeds a persistent-failure row, drives four recovery ticks, asserts row 4 is `TerminalFailure=TRUE` + no fifth attempt fires.

C14. Legacy dedupe / cleanup scripts named in ## Files are deleted. Grep across the tree for the deleted script names returns 0.

C15. Live smoke: force the Pokémon S18E60 race (source `.mkv` row + orphan `-mv.mp4` on disk). Trigger rescan. Assert zero `UniqueViolation` in worker log, zero new rows inserted for `-mv.mp4`, one WARN logged for the orphan.

C16. Live smoke: run transcode-replacement on any non-Pokémon file. Assert `SaveMediaFile` runs one SQL statement, source row updated, no INSERT, no orphan warning. FfmpegCommand + Disposition landed cleanly.

C17. Line-count subtraction target: `SaveMediaFile` (97 lines) + `_UpdateMediaFile` (43 lines) + `CleanupDuplicateMediaFiles` (73 lines) + `_UpdateMediaFilesAfterReplacement` (155 lines) = 368 lines removed. Replacement: rewritten `SaveMediaFile` + rewritten `_UpdateMediaFilesAfterReplacement` = ≤ 80 lines. Net delta ≤ -280 lines in production code. Characterization test (C4) + contract tests (C6, C7, C8) count separately, not against production line-budget.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|----|------|----------|-----------|------------------|--------------|
| S1 | `SaveMediaFile` single-statement write | `MediaFilesRepository.SaveMediaFile` | `INSERT ... ON CONFLICT (StorageRootId, LOWER(RelativePath)) DO UPDATE SET ...` | Every writer path (scanner, replacement, admin) | `TestMediaFilesUniqueness::test_save_single_statement` |
| S2 | `-mv` skip rule | `FileScanning` insert boundary | `IsMvOutput(basename)` guard from `MvSuffix.py` | `TranscodedOutputPlacement` sole writer of these rows | `TestMediaFilesUniqueness::test_scanner_skips_mv_files` |
| S3 | Orphan-mv WARN | `FileScanning` when `-mv` file has no row | `LoggingService.LogWarning("orphan-mv-suspect", canonical_path)` | Fail-loud signal for rollback breakage elsewhere | `TestMediaFilesUniqueness::test_orphan_mv_warns` |
| S4 | Sole-writer grep invariant | Any production-tree file | Zero raw `INSERT`/`UPDATE`/`DELETE` on `MediaFiles` outside `MediaFilesRepository.py` | `SaveMediaFile` is the only path | `TestMediaFilesSoleWriter` |
| S5 | Case-fold identity (writer + lookup) | `SaveMediaFile`, `GetMediaFileByPath`, `DeleteMediaFileByPath` | Postgres `LOWER(RelativePath)` in ON CONFLICT target + WHERE clauses + unique index | Identity is case-insensitive; stored casing frozen at first write | `TestMediaFilesUniqueness::test_case_insensitive_lookup_symmetry` |
| S6 | Characterization of `_UpdateMediaFilesAfterReplacement` | Existing 155-line implementation | 7 side effects (probe order, resolution ladder, PostFlightRegistry, AudioStateService, mtime re-stamp, MarkAudioComplete, NeedsReprobe clear) | Rewritten ≤40-line probe→SaveMediaFile delegator preserves every side effect | `TestUpdateMediaFilesAfterReplacementSideEffects` |
| S7 | CrashRecoveryService bounded retry | `CrashRecoveryService` sees Nth failure on `(RecoveryOp, CanonicalOriginalPath)` | `CrashRecoveryAttempts.AttemptCount>=3` → `TerminalFailure=TRUE` + ERROR log + never re-selected | `_UpdateMediaFilesAfterReplacement` no longer loop-storms `worker.out` | `TestCrashRecoveryBoundedRetry` |

## Scope

**In:**
- `Features/MediaFiles/MediaFilesRepository.py` — rewrite `SaveMediaFile` body to `INSERT ... ON CONFLICT DO UPDATE`; delete `_UpdateMediaFile` + `CleanupDuplicateMediaFiles`; case-fold sweep on `GetMediaFileByPath` + `DeleteMediaFileByPath`
- `Features/MediaFiles/MvSuffix.py` — CREATE; `MV_OUTPUT_SUFFIX` constant + `IsMvOutput` helper
- `Features/FileScanning/*` — `-mv` skip rule + orphan WARN at insert boundary
- `Features/FileReplacement/TranscodedOutputPlacement.py` — rewrite `_UpdateMediaFilesAfterReplacement` as thin probe→SaveMediaFile delegator; delete inline DELETE
- `Features/ServiceControl/CrashRecoveryService.py` — bounded retry with DB-persisted attempt counter
- Schema: `CrashRecoveryAttempts.AttemptCount INT NOT NULL DEFAULT 0` + `TerminalFailure BOOL NOT NULL DEFAULT FALSE` (migration idempotent)
- Drop `idx_mediafiles_typedpair_unique`
- Delete legacy scripts (listed below)
- Docs: this file; touch `Features/FileScanning/FileScanning.feature.md` with `-mv` invariant; touch `Features/FileReplacement/transcoded-output-placement.feature.md` for probe→SaveMediaFile shape
- Contract tests: `Tests/Contract/TestMediaFilesUniqueness.py`, `TestMediaFilesSoleWriter.py`, `TestUpdateMediaFilesAfterReplacementSideEffects.py`, `TestCrashRecoveryBoundedRetry.py`

**Out (with reason):**
- **Rename `SaveMediaFile` → `Upsert`** — 8-file caller sweep for cosmetic clarity. Zero simplification benefit. Body rewrite alone captures the invariant.
- **Rename `MediaFilesArchive.Id` → `MediaFileId`** — 12+ production/test/script callers. Schema migration + code sweep disproportionate to fix. Separate directive if worth doing.
- **`_MapRowToMediaFile` PascalCase/lowercase dual-read boilerplate** (~50 lines) — real DRY smell, but separate concern from uniqueness. File as follow-up directive.
- **`_FULL_SELECT_COLS` DRY violation** (column list synced across 4 places) — same follow-up.
- **`GetMediaFileByFileName` fuzzy match + `_ExtractEpisodePrefix`** (~100 lines of episode-prefix regex) — domain classification in wrong layer. Separate directive.
- **`SetAssignedProfileForFile` + `PropagateSeriesProfile`** — profile mutation in MediaFiles repo (mixed aggregate). Separate directive.
- **Aggregate-boundary sweep for Workers/ActiveJobs/TranscodeQueue** — speculative; only if evidence emerges.

## Status

**Phase:** NEEDS_STANDARDS_REVIEW
**Owner:** claude-opus-4-7
**Opened:** 2026-07-17

### Progress

- [ ] Standards + rules review complete
- [ ] Call-graph audit complete (five signals)
- [ ] Feature doc criteria approved by operator
- [ ] `MvSuffix.py` constant + helper (C11)
- [ ] Characterization test for `_UpdateMediaFilesAfterReplacement` (C4)
- [ ] `SaveMediaFile` body rewrite to ON CONFLICT (C1)
- [ ] Delete `_UpdateMediaFile`, `CleanupDuplicateMediaFiles` (C2, C3)
- [ ] Rewrite `_UpdateMediaFilesAfterReplacement` as probe→SaveMediaFile (C5)
- [ ] Case-fold sweep across `GetMediaFileByPath` / `DeleteMediaFileByPath` (C8)
- [ ] `FileScanning` `-mv` skip + orphan WARN (C9, C10)
- [ ] Sole-writer contract test (C6, S4)
- [ ] Case-insensitive contract tests (C7, C8, S5)
- [ ] Drop `idx_mediafiles_typedpair_unique` (C12)
- [ ] `CrashRecoveryService` bounded retry + schema column (C13, S7)
- [ ] Delete legacy dedupe scripts (C14)
- [ ] Line-count delta ≤ -280 verified (C17)
- [ ] Live smoke Pokémon S18E60 (C15)
- [ ] Live smoke transcode-replacement happy path (C16)
- [ ] KNOWN-ISSUES sweep
- [ ] Commit + push
- [ ] Directive close report

## Files

**Edit:**
- `Features/MediaFiles/MediaFilesRepository.py`
- `Features/FileScanning/FileScanningRepository.py` OR `Features/FileScanning/FileScanningBusinessService.py` (exact file locked at NEEDS_DOC_PREREAD)
- `Features/FileReplacement/TranscodedOutputPlacement.py`
- `Features/ServiceControl/CrashRecoveryService.py`
- `Features/FileScanning/FileScanning.feature.md`
- `Features/FileReplacement/transcoded-output-placement.feature.md`
- `memory/KNOWN-ISSUES.md`

**Create:**
- `Features/MediaFiles/mediafiles-uniqueness-owner.feature.md` (this doc)
- `Features/MediaFiles/MvSuffix.py`
- `Tests/Contract/TestMediaFilesUniqueness.py`
- `Tests/Contract/TestMediaFilesSoleWriter.py`
- `Tests/Contract/TestUpdateMediaFilesAfterReplacementSideEffects.py` — characterization test, lands BEFORE the rewrite
- `Tests/Contract/TestCrashRecoveryBoundedRetry.py`
- `Scripts/SQLScripts/_ONETIME_DropDuplicateTypedpairIndex_2026_07_17.py` (deleted post-run)
- `Scripts/SQLScripts/AddCrashRecoveryBoundedRetryColumns_2026_07_17.py` (idempotent migration, kept)

**Delete (legacy dedupe / cleanup — obsoleted by invariants):**
- `Scripts/SQLScripts/DedupeMediaFilesByRelativePath.py`
- `Scripts/SQLScripts/CleanupOrphanMvPairs.py`
- `Scripts/SQLScripts/CleanupOrphanFailedAttempts.py`
- `Scripts/SQLScripts/CleanupDuplicateSourcesFromBug0067.py`
- `Scripts/SQLScripts/CleanupDoubleMvSuffix_2026_06_26.py`
- `Scripts/SQLScripts/CleanupGenerationalGhostRows.py`
- `Scripts/SQLScripts/AlterTranscodeAttemptsMediaFileIdNullable_2026_06_23.py`
- `Scripts/SQLScripts/SetTranscodeAttemptsMediaFileIdNotNull.py`
- `Scripts/MergeZDriveDuplicateMediaFiles.py`
- `Scripts/DeleteDuplicateMediaFiles.py`
- `Scripts/delete_missing_mv_rows.py`

**Audit before delete (may be truly-obsolete or subsumed):**
- `Scripts/SQLScripts/CleanupSourceFileOrphans.py`
- `mediafile-persistence-no-drift.feature.md` at repo root

## Pre-flight (before landing on prod)

### Drain sequence

1. **Verify zero in-flight attempts.** `SELECT COUNT(*) FROM TranscodeAttempts WHERE Success IS NULL` = 0. Wait or force-abandon stale.
2. **Verify zero active jobs.** `SELECT COUNT(*) FROM ActiveJobs WHERE Status IN ('Running','Claimed')` = 0.
3. **Pause fleet at DB level.** `UPDATE Workers SET Status='Paused' WHERE WorkerName LIKE '%worker%'`. Existing poll loop reads flag; no new claims.
4. **Wait for running attempts to complete** or hit safe checkpoint. Poll `ActiveJobs` until empty.
5. **Stop I9 services.** WebService + WorkerService. Verify zero MediaVortex python procs (memory rule: verify count==2 not >2 for a single worker, count==0 when stopped).
6. **Stop remote containers.** dot/wakko/larry — `docker stop mediavortex-worker-N-1` per host.
7. **DB snapshot.** `pg_dump` on 10.0.0.15 as rollback insurance.

### Schema migrations (idempotent, run offline for safety)

- `Scripts/SQLScripts/AddCrashRecoveryBoundedRetryColumns_2026_07_17.py` — ADD COLUMN `AttemptCount` + `TerminalFailure` `IF NOT EXISTS`. Fast.
- `Scripts/SQLScripts/_ONETIME_DropDuplicateTypedpairIndex_2026_07_17.py` — `DROP INDEX IF EXISTS idx_mediafiles_typedpair_unique`. Fast. Brief lock.

### Code deploy

- I9 reads source tree directly — restart picks up `.py` edits + deleted legacy scripts + new `MvSuffix.py`.
- Remote workers = `deploy/deploy-linux-worker.py` picks up new tree per host.

### Restart

- Start WorkerService on I9 first. Tail boot log 30s. ImportError on deleted-method reference surfaces here.
- Start WebService on I9. Tail boot log for same class of error.
- UN-pause I9 worker: `UPDATE Workers SET Status='Online' WHERE WorkerName='I9-2024'`.
- Start remote containers if operator un-pauses them (per memory rule: only wakko-worker-1 goes Online without operator explicit; others stay Paused).

## Smoke tests (post-restart, before close)

### Upstream — writer paths

**U1. Scanner idempotency + case-fold + `-mv` skip.** Point scanner at synthetic dir with `foo.mkv`, `Foo.MKV`, `foo-mv.mp4`. Assert one row for `foo`, `RelativePath` preserves first-seen casing, zero row for `foo-mv.mp4`, one WARN.

**U2. Concurrent SaveMediaFile.** Two threads call `SaveMediaFile(model)` with different casing on same path. Assert one row. `ON CONFLICT` owns the race.

**U3. Pokémon S18E60 replay.** Re-run the exact scenario from `Logs/worker.out`. Assert zero `UniqueViolation`, zero new row for `-mv.mp4`, one WARN.

**U4. Case-fold lookup symmetry.** `GetMediaFileByPath('T:\\pokémon\\...')` and `GetMediaFileByPath('T:\\Pokémon\\...')` return same row Id.

### Downstream — reader paths (verify nothing else broke)

**D1. Transcode-replacement happy path.** Enqueue one non-Pokémon file end-to-end. Assert: single UPDATE via `SaveMediaFile`, zero new row, `Disposition=Replace`, FfmpegCommand populated, VMAF completes, Jellyfin notify fires.

**D2. WorkBucket recompute.** Post-D1, hit `/api/WorkBucket`. Assert bucket recomputed correctly using `GetMediaFileById` reader path.

**D3. Queue admission.** `POST /api/Work/Transcode/Queue/<mfid>`. Assert row lands in `TranscodeQueue` (BUG-0079 pattern preserved).

**D4. Activity dashboard.** `GET /api/Activity/NavBadges` + `/Overview`. Counts sane (C27 parent-directive pattern).

**D5. VMAF requeue.** Force a Disposition=Requeue. Assert new `TranscodeQueue` row inserted (BUG-0079 regression check).

### CrashRecoveryService

**R1. Bounded retry.** Seed `CrashRecoveryAttempts` row on a target whose `SaveMediaFile` always fails (mock probe). Drive 4 recovery ticks. Assert:
- Ticks 1-3: attempt fires, `AttemptCount` increments.
- Tick 4: not fired. Row `TerminalFailure=TRUE`. One ERROR log.

**R2. Success resets counter.** Seed row with `AttemptCount=2`. Drive one successful recovery. Assert post-success `AttemptCount=0`.

### Fleet-wide sanity

**F1. Grep-invariant.** `Tests/Contract/TestMediaFilesSoleWriter.py` PASS on live tree.

**F2. Log tail 15 min.** Watch `worker.out` + `web.out`. Zero `UniqueViolation`. Zero orphan-mv WARN storm (one per real orphan, not a loop).

**F3. Live disposition audit.** After 10 completed attempts: `SELECT COUNT(*) FROM TranscodeAttempts WHERE CompletedDate > <cutover> AND Success IS TRUE` matches worker log count.

## Rollback plan

Trivial when landing commits are clean:

1. `git revert <landing-commit>` on main, push.
2. Restart services (I9 picks up reverted source tree).

Schema migrations are additive + idempotent — reverse only if the revert commit needs it:
- `DROP INDEX IF EXISTS idx_mediafiles_typedpair_unique` reverses via `CREATE UNIQUE INDEX IF NOT EXISTS ...` (zero data loss).
- `CrashRecoveryAttempts.AttemptCount` + `TerminalFailure` columns are additive; leave them (harmless) OR `ALTER TABLE ... DROP COLUMN IF EXISTS` (zero data loss).

`pg_dump` from Pre-flight step 7 exists as insurance for the "if I broke something I don't understand" case. Normal-case rollback needs no snapshot.

Rollback discipline enforced by keeping the landing commit atomic — one commit lands the whole directive so one revert undoes it. If we ship in multiple commits, revert the range.

## Cross-references

- `.claude/rules/db-is-authority.md` — DB owns concurrency via ON CONFLICT
- `.claude/rules/fail-loud.md` — orphan WARN + bounded-retry terminal state
- `.claude/rules/feature-docs.md`
- `.claude/rules/call-graph-audit.md`
- `Features/FileScanning/FileScanning.flow.md` — S5 uniqueness invariant reference
- `Features/FileReplacement/transcoded-output-placement.feature.md`
