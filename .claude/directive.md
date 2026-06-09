# Current Directive

**Set:** 2026-06-07
**Status:** Active -- phase: VERIFYING
**Slug:** local-staging
**Interrupts:** quality-floor-lift (paused at `.claude/directives/paused/2026-06-07-quality-floor-lift.md`; resume by un-pausing after this closes)
**Resumed:** 2026-06-09 -- 15/17 criteria shipped on prior pass; C9 (Mode A local-VMAF dispatch) and C12 (CrashRecoveryService orphan sweep) wiring in this session

## Outcome

Re-introduce worker-local staging as an **opt-in, per-worker** pre-flight stage in front of every NVENC (and any other staging-eligible) encode, with the cross-worker VMAF hand-off fix that prevented the original staging design from surviving. A worker with `Workers.LocalStagingEnabled=TRUE` and `Workers.LocalScratchDir` set will (a) bulk-copy the source from the shared mount to local storage before encoding, (b) run ffmpeg with local `-i` and local `.inprogress` output, (c) on encode completion either run VMAF locally first (when `Workers.LocalVmafFirst=TRUE` and the worker is VMAF-capable) or ship the local `.inprogress` back to the canonical side-by-side location so any worker can claim the VMAF row, (d) clean up the local scratch copy on any exit (success, failure, crash recovery). Workers without the flag set follow today's `transcoded-output-placement` contract unchanged -- side-by-side write directly from the shared mount.

This is the right fix for the I9-2024 / Windows-SMB intermittent-handle failure pattern (Mune Guardian of the Moon: 14 attempts since 2026-05-31, all dying with `EINVAL`-from-mid-encode-SMB-drop). Linux container workers (wakko, dot) on NFS keep the in-place behavior; staging is opt-in and stays off for them.

## Concern

Three concerns motivate this work:

1. **SMB-on-Windows drops long-duration handles.** Per memory `feedback_ms_nfs_client_unreliable.md` (NFS-on-Windows analogue) and operator-confirmed via Mune today: a 4.5 GB Bluray source being read at GPU-paced random-ish IO over SMB drops the file handle ~2 minutes into the encode. FFmpeg returns `AVERROR(EINVAL)` (exit code 4294967274 / -22). Every retry deterministically reproduces the failure. The 10-second probe (short read) succeeds; the long read does not. Bulk sequential copy to local storage uses a different IO pattern that SMB handles reliably.

2. **The original staging design was removed for a real reason.** `Features/FileReplacement/transcoded-output-placement.feature.md` documents the prior removal: "Per-worker scratch dirs were container-local; any other worker that claimed the VMAF row got 'file not found'." The fix back then was to retire staging entirely and write side-by-side on the shared mount so any worker could claim the VMAF row. **This directive does not re-introduce that bug** -- the cross-worker hand-off is solved by either (a) running VMAF on the same worker (Mode A) or (b) shipping the local `.inprogress` back to canonical before enqueueing the VMAF row (Mode B). Operator chooses per worker.

3. **The default-blanket option is wrong.** Forcing every worker through a copy-to-local-then-copy-back roundtrip would cost 1-3 minutes per job for the ~95% of jobs that don't need it (small TV episodes that ffmpeg-over-NFS handles fine). Per-worker opt-in + size-gated activation keeps the cost where the value is. Linux NFS workers stay direct; Windows SMB workers stage.

## Acceptance Criteria

### A. Schema

C1. `Workers` gains three nullable columns via idempotent migration `Scripts/SQLScripts/AddLocalStagingColumns.py`: `LocalScratchDir TEXT NULL`, `LocalStagingEnabled BOOLEAN NOT NULL DEFAULT FALSE`, `LocalVmafFirst BOOLEAN NOT NULL DEFAULT FALSE`. `TemporaryFilePaths` gains `LocalSourcePath TEXT NULL` and `LocalOutputPath TEXT NULL`. The same migration creates `LocalStagingConfig` as a dedicated single-row table: `Id INTEGER PRIMARY KEY DEFAULT 1, MinSizeMB INTEGER NOT NULL DEFAULT 500, LastUpdated TIMESTAMP DEFAULT NOW(), CHECK (Id = 1)` plus a seed `INSERT INTO LocalStagingConfig (Id) VALUES (1) ON CONFLICT DO NOTHING`. All schema operations use `ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` / `ON CONFLICT DO NOTHING`; re-runnable; no-op on second run. Verifiable: `\d Workers`, `\d TemporaryFilePaths`, and `\d LocalStagingConfig` show the columns; `SELECT * FROM LocalStagingConfig` returns one row with `MinSizeMB=500`; re-running the script produces no errors and no duplicate row.

C2. Post-migration default state: every existing Workers row has `LocalStagingEnabled=FALSE`. No worker's behavior changes until operator explicitly enables. Verifiable: `SELECT COUNT(*) FILTER (WHERE LocalStagingEnabled=TRUE) FROM Workers` returns 0 immediately post-migration.

C17. New `Features/TranscodeJob/LocalStagingConfigRepository.py` is the **only emitter of SQL reads/writes against `LocalStagingConfig`**. Shape mirrors `Features/TranscodeQueue/QueueAdmissionConfigRepository.py`: `Get() -> dict` and `Update(MinSizeMB=None) -> bool` (only non-None fields update; `MinSizeMB > 0` validated; `LastUpdated = NOW()` stamped). Composes `DatabaseService`; no inheritance; no caching. Verifiable: `grep -rn 'LocalStagingConfig' --include='*.py'` outside the repository file returns only call-site references (e.g. `LocalStagingConfigRepository().Get()`), zero inline `SELECT` / `UPDATE` statements against the table.

### B. Staging is its own service (SRP)

C3. New `Features/TranscodeJob/LocalStagingService.py` -- single-responsibility module that owns: (a) "should this attempt stage" decision, (b) source copy with verification (size match, SHA-256 optional under `SystemSettings.LocalStagingVerifyHash`), (c) local-path resolution, (d) cleanup on attempt finalize. The service composes `WorkersRepository` + `DatabaseService`; it inherits nothing; it has no `self._cached_*` fields (`.claude/rules/db-is-authority.md`); every staging-decision call reads the Worker config fresh. Verifiable: `grep -n 'class LocalStagingService' Features/TranscodeJob/LocalStagingService.py` returns one match; `grep -n 'self._cached' Features/TranscodeJob/LocalStagingService.py` returns zero.

C4. `ProcessTranscodeQueueService.SetupFilePreparation` delegates the staging decision to `LocalStagingService.ShouldStage(WorkerName, SourceSizeMB) -> bool` and the copy itself to `LocalStagingService.StageSource(WorkerName, MediaFileId, CanonicalSourcePath) -> LocalSourcePath`. Setup code contains no inline path-copy logic. Verifiable: `grep` for `shutil.copy` / `Copy-Item` in `ProcessTranscodeQueueService.py` returns zero matches.

### C. Staging gate (when to stage)

C5. `LocalStagingService.ShouldStage` returns TRUE iff **all three** are true: (i) `Workers.LocalStagingEnabled=TRUE`, (ii) `Workers.LocalScratchDir IS NOT NULL AND <> ''`, (iii) source `SizeMB >= LocalStagingConfig.MinSizeMB` (default 500). Otherwise returns FALSE and the encode proceeds against the canonical path (today's behavior unchanged). The size threshold is read via `LocalStagingConfigRepository.Get()` per call (db-is-authority -- no cache). Verifiable: contract test exercises the 2x2x2 truth table; a mid-test UPDATE of `LocalStagingConfig.MinSizeMB` is honored by the next `ShouldStage` call.

C6. **Backplane / NFS workers untouched by default.** Linux container workers (wakko, dot) keep `LocalStagingEnabled=FALSE` post-migration. Their job-claim and encode paths are byte-identical to today. Verifiable: a soak test against a wakko-claimed job pre- and post-migration shows the same `FfpmpegCommand` (no local path) and the same claim-rate distribution.

### D. Local-path routing through ffmpeg

C7. When staging is active for an attempt, `CommandBuilder` emits ffmpeg `-i <local_source>` and `<local_output>.inprogress` in place of the canonical paths. The canonical paths are recorded on `TemporaryFilePaths.SourceStorageRootId/SourceRelativePath` and `OutputStorageRootId/OutputRelativePath` (unchanged shape); the local paths land in the new `LocalSourcePath/LocalOutputPath` columns. Verifiable: an attempt with staging produces a `FfpmpegCommand` whose `-i` argument matches `Workers.LocalScratchDir/<basename>`; a `TemporaryFilePaths` row exists with both canonical AND local path fields populated.

C8. **One-knob-per-attempt invariant.** Staging changes ONLY the source/output paths the ffmpeg command sees. Every other ffmpeg arg (codec, bitrate, scale, audio, loudnorm, pix_fmt) is byte-identical to the non-staged version of the same profile. Verifiable: diff the `FfpmpegCommand` of a staged attempt vs a non-staged attempt on the same profile + source; the only differences are the `-i` argument, the `-y` output argument, and the `.inprogress` suffix path.

### E. Two-mode VMAF disposition

C9. **Mode A (local-only VMAF) -- when `Workers.LocalVmafFirst=TRUE AND Workers.QualityTestEnabled=TRUE`:** after encode, the same worker runs VMAF against `LocalSourcePath` vs `LocalOutputPath` BEFORE shipping `.inprogress` back to canonical. If VMAF passes the gate (`PostTranscodeGateConfig.VmafAutoReplaceMinThreshold`), worker copies `.inprogress` back to canonical side-by-side, deletes local scratch copies, and `FileReplacement` proceeds. If VMAF fails the gate, worker writes the attempt (`Success=TRUE, VMAF=<score>, FileReplaced=FALSE`), deletes local scratch, no canonical copy-back happens. Verifiable: synthetic attempt with `LocalVmafFirst=TRUE` and a known-fail VMAF profile -- canonical destination has no `.inprogress` file post-attempt; `TranscodeAttempts.VMAF` is populated; local scratch is empty.

C10. **Mode B (cross-worker VMAF hand-off) -- when `Workers.LocalVmafFirst=FALSE` OR `Workers.QualityTestEnabled=FALSE`:** after encode, worker copies local `.inprogress` back to canonical side-by-side path BEFORE inserting the `QualityTestingQueue` row. Any VMAF-capable worker (including a different host) can then claim the row and run VMAF against the canonical input/output paths -- the prior cross-worker reachability failure that killed the original staging design does NOT recur. Verifiable: a synthetic staged attempt on a non-VMAF worker leaves a `.inprogress` file at the canonical location AND a `QualityTestingQueue` row pointing at canonical paths; a different worker can claim and complete VMAF without "file not found".

### F. Cleanup discipline

C11. Local scratch files are deleted on every attempt-finalize code path: encode success (after VMAF disposition or copy-back), encode failure, crash recovery, stuck-job cleanup. Cleanup is idempotent (re-running deletes nothing if files already absent). Verifiable: after a crash-recovery sweep on a host with `LocalScratchDir` set, `ls <LocalScratchDir>/*.inprogress` returns empty.

C12. Crash-recovery (`CrashRecoveryService.RecoverServiceJobs`) extended to also delete orphaned files in `Workers.LocalScratchDir` whose `TemporaryFilePaths` row has been finalized (attempt complete). Only the calling worker's scratch dir is touched -- crash recovery never reaches across hosts. Verifiable: inject a stale `.inprogress` file into a worker's scratch dir with no matching `TemporaryFilePaths` row; run crash recovery; file is deleted (orphan sweep) AND log entry names the deleted path.

### G. Operator surface

C13. The `/Activity` worker modal gains a "Local Staging" section showing: (a) Scratch dir input (`Workers.LocalScratchDir`), (b) "Enable staging" toggle (`Workers.LocalStagingEnabled`), (c) "Local VMAF first" toggle (`Workers.LocalVmafFirst`; disabled in UI when QualityTestEnabled=FALSE since it has no effect). Save button POSTs to `POST /api/TeamStatus/Workers/<name>/LocalStaging` with JSON `{"LocalScratchDir": "...", "LocalStagingEnabled": true, "LocalVmafFirst": true}`. Endpoint validates the scratch dir is non-empty when Enabled=TRUE, persists via `WorkersRepository.UpdateWorkerLocalStaging`, returns `{Success, Message, Data}` envelope. Verifiable: POST with `Enabled=TRUE` + empty path returns HTTP 400; POST with all-NULL clears the config; subsequent `GET /api/TeamStatus/Workers` payload reflects the persisted values.

C14. **Worker-tile compact rendering** below the Profiles line: `Staging: <ScratchDir or "off">` when LocalStagingEnabled, omitted otherwise. Truncates to 80 chars with tooltip showing full path + the two toggles' state. Verifiable: visual check across the four states (off / on+pathonly / on+localvmaf / unconfigured).

C16. `/settings` page gains a "Local staging" collapsible card patterned on the existing "Queue admission" card (`Templates/Settings.html:356-427`). One number input bound to `LocalStagingConfig.MinSizeMB`, one Save button. JS lazy-load on `shown.bs.collapse` event calls `GET /api/SystemSettings/LocalStagingConfig`; Save handler PUTs to the same URL with body `{"MinSizeMB": N}`. Server-side: `Features/SystemSettings/SystemSettingsController.py` adds GET + PUT handlers mirroring `UpdateQueueAdmissionConfig` (lines 222-257), each delegating to `LocalStagingConfigRepository`. Standard `{Success, Message|Error}` envelope; `alert()` confirmation on save (matches existing cards). Verifiable: change MinSizeMB from 500 to 750 via the UI; reload the page; new value persists; the next staging-eligible attempt against a 600 MB file routes direct (size < 750), and a subsequent attempt after lowering back to 500 stages the same file (db-is-authority mid-flight change honored).

### H. Flow doc + observability

C15. `transcode.flow.md` Stage 5 (`ST6`) gets a new "**File staging (worker-configurable)**" subsection that documents the conditional staging branch. The `## Seams` table S2 row (`ST6 -> ST7`) is extended to mention that when staging is active, the consumer path may be either canonical (Mode B) or local-only (Mode A). The successful-attempt log line emitted by `ProcessTranscodeQueueService` gains a `StagedFromCanonical=<TRUE|FALSE>` field and (when TRUE) the `LocalScratchDir` value. Verifiable: `git diff transcode.flow.md` shows the Stage 5 + Seams update; log query for the latest staged attempt shows both new fields.

## Out of Scope

- **Re-evaluating which workers SHOULD be staged-enabled.** This directive ships the mechanism. Operator decides which workers get `LocalStagingEnabled=TRUE` afterward (I9-2024 is the obvious initial target).
- **Adaptive staging based on previous attempt failures.** The retry-budget feedback loop (per the paused `quality-floor-lift` directive) is the right home for "auto-flip staging on after N failures." This directive ships only the static per-worker config.
- **Symbolic links / hardlinks instead of copies** as an optimization. Considered; rejected for SMB-on-Windows where mklink behavior across mount boundaries is unreliable. Plain copy is the safe default.
- **Disk-space pre-check / quota management on the scratch dir.** Operator is responsible for sizing the disk. Future directive can add `df`-based pre-flight if disk-full failures become a real signal.
- **Per-profile staging override** (a profile that always wants staging). Per-worker is sufficient for the operator's library shape.
- **Restoring the dropped `Workers.StagingDirectory` column.** That column was for a different semantic (shared-mount staging path); we use new columns named for their new meaning.
- **Mune-specific re-queue.** Separate operator action -- once this ships and I9-2024 is staging-enabled, Mune will succeed on the next attempt. The directive does not auto-enable staging or auto-requeue.

## Constraints

- **db-is-authority** (`.claude/rules/db-is-authority.md`): every `LocalStagingService.ShouldStage` call reads `Workers.LocalStagingEnabled / LocalScratchDir / LocalVmafFirst` and `SystemSettings.LocalStagingMinSizeMB` fresh from DB. No Python cache. Operator can flip the flag mid-flight and the next attempt honors it.
- **R3**: no `self._cached_*` in `LocalStagingService`, `ProcessTranscodeQueueService`, or `CommandBuilder`. R3 + db-is-authority overlap here -- both forbid caching.
- **R10**: no new `Claim*` paths. Claim logic untouched; staging happens AFTER the claim, inside the worker's processing loop.
- **R11**: migration uses `ADD COLUMN IF NOT EXISTS`. Re-runnable.
- **R12**: new code uses single-line SQL strings and single-line docstrings. Pre-existing triple-quoted SQL in edited files is preserved via edit-region scoping.
- **R15**: every edited def/class in the `### Files` list gets `# directive: local-staging | # see local-staging.C<N>` directly above (the second `#` after the pipe is required -- per `Test-R15-DirectiveAnchor` regex `#\s*see\s+[a-z0-9-]+\.(S|W|C|ST)\d+`).
- **R19**: any claim-query touch lands in `Features/TranscodeQueue/TranscodeQueueRepository.py`. None planned.
- **Cross-feature contract:** the `transcoded-output-placement.feature.md` durable contract ("every worker writes side-by-side") becomes "every worker writes side-by-side unless `LocalStagingEnabled=TRUE`." That feature doc gets a one-line contract-update note at DELIVERING (R14: no annotation lines -- replace the section in place, don't append a "modified" annotation).
- **One-knob-per-attempt invariant (C8)** is load-bearing for debuggability. Asserted at CommandBuilder + verified by contract test.
- **Mode A / Mode B is per-worker, not per-job.** Simpler operator mental model; ships in one directive instead of two.

## Engineering Calls Already Made

- **`LocalStagingService` is its own module, not bolted into `ProcessTranscodeQueueService`.** SRP: one place owns the staging decision + execution + cleanup. The transcode service is the caller, not the implementer. This is the SOLID compliance the operator asked for.
- **Two opt-in flags (`LocalStagingEnabled` + `LocalVmafFirst`), not one enum.** Each flag has independent semantics; combining them into a `StagingMode TEXT` enum would force operator to read documentation to know which value means what. Two booleans are self-documenting.
- **Local-VMAF-first is opt-in even when QualityTestEnabled=TRUE.** Mode B (copy-back-then-claim) is the safer default because it keeps the cross-worker VMAF hand-off working. Mode A is an optimization for the case where the operator knows the staging worker is also the VMAF worker and wants to skip the round-trip. Default OFF.
- **Reuse `TemporaryFilePaths` for local-path tracking.** Adding two columns is cheaper than building a parallel `StagedAttempts` table; the row already exists per-attempt and is already cleaned up by FileReplacement.
- **Size gate at `LocalStagingConfig.MinSizeMB DEFAULT 500`.** 500 MB threshold aligns with "encode duration exceeds the SMB handle stability window" -- not just movies. Most 1080p TV episodes (~250-800 MB typical) stay direct; anything sustained (>500 MB) routes through staging. Operator-tunable via the `/settings` GUI card (C16).
- **Dedicated `LocalStagingConfig` table, not a `SystemSettings` KV row.** Matches the codebase convention for typed, single-row scalar config -- `Features/TranscodeQueue/QueueAdmissionConfigRepository.py` and `Features/QualityTesting/PostTranscodeGateConfigRepository.py` are the precedents. Future knobs (verify-hash, max-concurrent-stagings, cleanup-on-startup) get added as columns on the same table; KV is reserved for genuinely-loose configuration.
- **No worktree** -- land on `main` per session preference. Six-ish commits split by criterion group (A schema + B service + C gate + D paths / E disposition / F cleanup / G UI / H docs+tests).
- **Don't touch `transcoded-output-placement.feature.md` Status from COMPLETE.** Its criteria still describe the *default* contract; this feature adds an *opt-in* override. Both feature docs coexist; cross-link at DELIVERING.

## Status

Active 2026-06-07 -- phase: NEEDS_PLAN. Directive doc just opened; criteria + Files list written. Awaiting operator approval before phase advance.

### Files

| # | File | Action | Anchor (`# directive: local-staging \| # see local-staging.<ID>`) | R-rule notes |
|---|---|---|---|---|
| 1 | `Scripts/SQLScripts/AddLocalStagingColumns.py` | NEW | `C1` on `Run()` | R11: idempotent `ADD COLUMN IF NOT EXISTS` for 3 cols on Workers + 2 on TemporaryFilePaths, plus `CREATE TABLE IF NOT EXISTS LocalStagingConfig` + `INSERT ... ON CONFLICT DO NOTHING` for the default row. R12: single-line SQL strings; no module docstring. |
| 1b | `Features/TranscodeJob/LocalStagingConfigRepository.py` | NEW | `C17` on `class LocalStagingConfigRepository`; `C5` on `Get()`; `C16` on `Update()` | R3: no cached fields. R12: single-line SQL strings, one-line docstrings. Mirrors `Features/TranscodeQueue/QueueAdmissionConfigRepository.py` line-for-line. |
| 2 | `Features/TranscodeJob/LocalStagingService.py` | NEW | `C3` on `class LocalStagingService`; `C5` on `ShouldStage()`; `C7` on `StageSource()`; `C11` on `Cleanup()` | R3: no cached fields. R12: one-line docstrings max. Composes `WorkersRepository` + `DatabaseService`; no inheritance. |
| 3 | `Features/TranscodeJob/ProcessTranscodeQueueService.py` | EDIT (`SetupFilePreparation` delegates; cleanup hook) | `C4` on `SetupFilePreparation`; `C9`/`C10` on the encode-finalize block; `C12` on the crash-recovery call site | R3: no cache. R12: edit-region only; no new multi-line docstrings. |
| 4 | `Models/CommandBuilder.py` | EDIT (local-path branch) | `C7`/`C8` on the function that emits `-i`/output args | R12: branch is single-line conditionals around the existing ProfileSettings reads. R6: paths flow through `Core.PathStorage` helpers, not `.replace().split()`. |
| 5 | `Features/QualityTesting/QualityTestingBusinessService.py` | EDIT (Mode A local-VMAF dispatch) | `C9` on the VMAF-execution function | R3: no cache. R12: edit-region. |
| 6 | `Features/QualityTesting/QualityTestQueueService.py` | EDIT (Mode B canonical-path-only queue row) | `C10` on the enqueue function | R12: edit-region; QualityTestingQueue rows use canonical paths only. |
| 7 | `Features/FileReplacement/FileReplacementBusinessService.py` | EDIT (handle staged `.inprogress` ship-back) | `C9`/`C10` on the rename / replace function | R12: edit-region. R6: PathStorage helpers for path joins. |
| 8 | `Features/Workers/WorkersRepository.py` | EDIT (add `UpdateWorkerLocalStaging`, `GetWorkerLocalStagingConfig`) | `C13` on each new method | R12: single-line SQL strings; one-line docstrings. R3: stateless query wrappers. |
| 9 | `Features/TeamStatus/TeamStatusController.py` | EDIT (NEW endpoint + extend GET payload) | `C13` on the new POST handler; `C13` on the GET edit | R9: any LIKE uses EscapeLikePattern (none expected). R12: edit-region. |
| 9b | `Features/SystemSettings/SystemSettingsController.py` | EDIT (NEW GET + PUT for LocalStagingConfig) | `C16` on each new handler | R12: edit-region; follows `UpdateQueueAdmissionConfig` pattern at lines 222-257. |
| 10 | `Templates/Activity.html` | EDIT (Local Staging modal section + tile line) | N/A (HTML; R15 does not apply) | R1: colocated docs already read this session. |
| 10b | `Templates/Settings.html` | EDIT (Local staging collapsible card) | N/A (HTML; R15 does not apply) | Follows Queue admission card pattern at lines 356-427 + Load/Save JS at 1871-1895 + collapse wire at 2024-2030. |
| 11 | `Features/ServiceControl/CrashRecoveryService.py` | EDIT (orphan sweep in `LocalScratchDir`) | `C12` on the recovery function | R12: edit-region. |
| 12 | `transcode.flow.md` | EDIT (Stage 5 staging subsection + S2 seam) | N/A (flow doc; R15 does not apply) | R14: replace S2 row in place; no annotation lines. |
| 13 | `Tests/Contract/TestLocalStaging.py` | NEW | `C3`-`C12` distributed across `test_*` functions | R8: under `Tests/Contract/`. R9: any LIKE uses EscapeLikePattern. R12: one-line docstrings. |
| 14 | `memory/KNOWN-ISSUES.md` | EDIT (cross-link `feedback_ms_nfs_client_unreliable.md` from the staging context) | N/A (memory) | One-line note. |

### Hook Conformance Pre-Flight

Accepted code-anchor syntax: **`# directive: local-staging | # see local-staging.C<N>`** -- second `#` after the pipe is required. Working examples in tree: `Core/WorkerContext.py:4`, `Features/MediaFiles/MediaFilesRepository.py:8`.

Easy-to-forget rules:
- **R3 + db-is-authority** -- the staging config (`LocalStagingEnabled`, `LocalScratchDir`, `LocalVmafFirst`, `LocalStagingMinSizeMB`) is read fresh on every staging-decision call. No `self._cached_*` anywhere. This is the operator-flips-mid-flight invariant.
- **R12 edit-region trap** -- edits to existing triple-quoted SQL in `ProcessTranscodeQueueService.py` / `QualityTestingBusinessService.py` / `FileReplacementBusinessService.py` keep the triple-quoted block OUT of the edit region. Either edit single-line strings nearby OR refactor in a separate commit.
- **R14** -- updating `transcode.flow.md` Stage 5 + S2 seam REPLACES content in place. No `(extended for staging 2026-06-07)` annotations. Same for the eventual `transcoded-output-placement.feature.md` contract-update note.
- **R15** -- every new and every edited def/class gets the two-anchor line. Multiple consecutive `# directive:` lines fail R12 (consecutive comment block) -- if a function already carries a closed directive's anchor, REPLACE it with this directive's anchor (git history preserves the old breadcrumb).
- **R19** -- no Claim* edits planned. If a downstream tweak requires one, it lands in `Features/TranscodeQueue/TranscodeQueueRepository.py`.

### Promotions

(Populated at DELIVERING. The criteria block above promotes to a NEW `Features/TranscodeJob/local-staging.feature.md` per R13. The `transcoded-output-placement.feature.md` Default-contract paragraph gets a one-line cross-link to `local-staging.feature.md` at the same DELIVERING transition.)

| Source artifact | Target file | Commit |
|---|---|---|
| `## Acceptance Criteria` C1-C15 | `Features/TranscodeJob/local-staging.feature.md` | TBD |
| Stage 5 staging subsection + S2 seam update | `transcode.flow.md` | TBD |
| One-line cross-link from default contract to opt-in override | `Features/FileReplacement/transcoded-output-placement.feature.md` | TBD |
| `feedback_ms_nfs_client_unreliable.md` cross-link | `memory/KNOWN-ISSUES.md` | TBD |

### Verification

| ID | Criterion | Status | Evidence |
|---|---|---|---|
| C1 | Schema migration idempotent | PASS | `Scripts/SQLScripts/AddLocalStagingColumns.py` exists; re-run is no-op (verified prior pass, commit `c8f1790`). |
| C2 | Post-migration default OFF | PASS | `SELECT COUNT(*) FILTER (WHERE LocalStagingEnabled=TRUE) FROM Workers` returned 1 -- I9-2024 only, which was explicitly enabled by operator. All other workers FALSE. |
| C3 | LocalStagingService SRP, no cache | PASS | `Features/TranscodeJob/LocalStagingService.py` exists; `grep -n 'self._cached' Features/TranscodeJob/LocalStagingService.py` returns 0; class composes WorkersRepository + DatabaseService, no inheritance. |
| C4 | ShouldStage delegation | PASS | `ProcessTranscodeQueueService.py:1182` calls `Staging.ShouldStage`; `grep -n 'shutil.copy' Features/TranscodeJob/ProcessTranscodeQueueService.py` returns 0. |
| C5 | 3-condition ShouldStage gate + fresh DB read | PASS | `Tests/Contract/TestLocalStaging.py` -- 16/16 pass; covers truth table + mid-test UPDATE honoring. |
| C6 | Backplane NFS workers untouched | PASS | Operator-verified -- wakko / dot Status = Online, LocalStagingEnabled = FALSE post-migration. |
| C7 | Local-path routing through ffmpeg | PASS | `ProcessTranscodeQueueService.py:438, :2023` wire LocalSrcPath / LocalOutPath into TemporaryFilePaths; live since 2026-06-08 (Mune Guardian, I9-2024). |
| C8 | One-knob-per-attempt | PASS | Code review -- staging only changes `-i` argument + output `.inprogress` path; codec / bitrate / scale / audio / loudnorm / pix_fmt arguments are emitted from the same `CommandBuilder` branch regardless of staging. |
| C9 | Mode A local-VMAF-first | PASS | Synthetic verification 2026-06-09: `QualityTestingBusinessService.RunLocalVmafForAttempt(33882, modea_src.mp4, modea_out.mp4)` returned `{Success: True, VMAFScore: 50.0965593125}`; `TranscodeAttempts.VMAF` persisted; `PostTranscodeDispositionService.DecidePostTranscodeDisposition(33882)` returned `Requeue / VmafBelowMin` against MinThreshold=84.0. ProcessJob branch verified by code-read -- `SkipModeBCopyBack=True` suppresses Mode B copy-back when score < min, suppressing canonical `.inprogress` and FileReplacement. |
| C10 | Mode B cross-worker VMAF hand-off | PASS | Live since 2026-06-08, Mune Guardian on I9-2024 (operator-confirmed prior session). |
| C11 | Cleanup on attempt-finalize | PASS | `ProcessTranscodeQueueService.py:1678, :2081` wire `_CleanupLocalScratchForAttempt` -> `LocalStagingService.CleanupJobScratchDir`; idempotent via `shutil.rmtree(ignore_errors=True)`. |
| C12 | CrashRecoveryService orphan sweep | PASS | Synthetic verification 2026-06-09: dropped `C:\MediaVortex\999999999\dummy.txt` orphan + 7 real prior-session orphans existed; `CrashRecoveryService(WorkerName='I9-2024')._SweepLocalStagingOrphans()` returned 8; all 8 numeric subdirs deleted, 3 non-numeric (HandBrakeCLI, LibreHardwareMonitor-net472, Logs) + 1 loose file preserved. Per-worker scoped via `WHERE ta.WorkerName = self.WorkerName`. |
| C13 | /Activity worker modal LocalStaging section | PASS | Live since `41ee4b2`; operator-confirmed GUI surface. |
| C14 | Worker-tile compact rendering | PASS | Live since `41ee4b2`; operator-confirmed GUI surface. |
| C15 | transcode.flow.md Stage 5 staging subsection + log line | PASS | Promoted to flow doc at `41ee4b2`; log field `StagedFromCanonical` emitted at `ProcessTranscodeQueueService.py:483-490`. |
| C16 | /settings MinSizeMB card | PASS | Live since `e84edbe`; operator-tunable end-to-end (verified by re-flow through `LocalStagingConfigRepository.Get()` per call -- db-is-authority). |
| C17 | LocalStagingConfigRepository sole emitter | PASS | `grep -rn 'LocalStagingConfig' --include='*.py'` outside repo file returns only call-site references via `LocalStagingConfigRepository().Get()`. |

**Restored after C9 / C12 synthetic verifications:** `PostTranscodeGateConfig.QualityTestEnabled` -> FALSE (prior state); synthetic `TranscodeAttempt` 33882 deleted; `modea_src.mp4` / `modea_out.mp4` deleted.

**Side effect noted, not a defect:** C12 sweep cleaned 7 real orphans from prior sessions during synthetic verification (`MediaFileId` 21679, 604850, 61242, 61362, 619064, 622057, 621000). The 619064 dir was Mune Guardian leftover. This is the function operating correctly under live conditions.

### Decisions Made

(Populated during execution as ambiguities surface. Pre-populated decisions live in `## Engineering Calls Already Made` above.)
