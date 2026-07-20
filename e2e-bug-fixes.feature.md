# End-to-End Bug and Failure Fixes

**Slug:** e2e-bug-fixes

## Interrupts: audio-vertical-dialog-boost-enforcement

## What It Does

Triage and fix every bug or failure mode that prevents MediaVortex from delivering a media file end-to-end through the pipeline: bucket admission -> claim -> probe -> transcode -> verify -> replace -> notify -> recompute. Improvement / refactor / DDD-polish work is paused; scope is delivery reliability, not architecture cleanup.

Every discovered issue is either fixed in this directive or filed with `/b BUG-NNNN` and a written reason it cannot land here. No silent "will address later."

## Success Criteria

Baseline captured 2026-07-17: `SELECT LogLevel, FunctionName, LEFT(Message, 200), COUNT(*) FROM Logs WHERE Timestamp > NOW() - INTERVAL '48 hours' AND LogLevel IN ('WARNING','ERROR','CRITICAL')` returned 100+ distinct patterns. Criteria below name every non-trivial repeating failure. Each criterion is: **root cause fixed AND the exact log signature returns zero hits over the 60-minute post-fix soak window**.

### Group A -- path plumbing (repository / scanning collapse)

C1. `ExtractShowInfo` (`ScheduleService`) no longer raises `Path.__init__() missing 1 required positional argument: 'RelativePath'`. Baseline: 251 hits/48h. Fix pattern: `Path()` constructed at that call site with the missing arg (probably a `MediaFiles.RelativePath` lookup that returns `None`). See `.claude/rules/fail-loud.md` -- upstream write is the bug, not the caller's guard.

C2. `FileScanningBusinessService.<method>` no longer raises `'FileScanningRepository' object has no attribute 'GetMediaFilesByRootFolderId'`. Baseline: 58 hits/48h. Fix: add the missing repository method OR retarget caller to the renamed method.

C3. `ReconcileWithDisk` no longer raises `'FileScanningRepository' object has no attribute 'GetMediaFilesByRootFolder'`. Baseline: 58 hits/48h. Companion of C2.

C4. `MediaProbeRepository` no longer raises `column "rootfolder" does not exist` on `SELECT RootFolder FROM RootFolders WHERE Id = %s`. Baseline: 58 hits/48h (29 get + 29 count). Column was renamed (likely to `Path` / `RootPath`); update the SQL. `SchemaChecker` snapshot drift check should have caught this pre-deploy.

C5. `FileScanningRepository` no longer raises `LocalPath op refused canonical drive-letter path on non-Windows worker: 'M:\\' / 'T:\\'`. Baseline: 58 hits/48h. Route through `Path.FromLegacyString(...).Resolve(worker)` per the hook's stated path forward. See `.claude/rules/mediavortex-paths` skill + `.claude/rules/feedback_hook_path_forward_is_the_answer.md`.

### Group B -- replacement / uniqueness collision (OUT OF SCOPE)

C6, C7, C8, C9 are **OWNED BY `mediafiles-uniqueness-owner`** (paused, one level down in the stack). Domain call 2026-07-18: pop this directive back to that one, finish it, then C6-C9 auto-resolve. Do not land tactical fixes for them in e2e-bug-fixes.

C10. `TranscodeQueueRepository: Refusing to admit queue row -- source already MediaVortex-transcoded (Pokémon/...)` cluster drops to zero. Baseline: 300+ hits/48h across ~40 distinct Pokémon files. Fix: purge the stale pre-2026-07-16 `TranscodeQueue` rows whose `FilePath LIKE '%-mv.mp4%'` -- they pre-date commit 7e562a9's admission gate and are stuck re-emitting the refusal. Scanner + admission code is already correct.

### Group C -- crash-recovery no-op storm

C11. `CrashRecoveryService: Crash recovery: completed partial replacement for X -> X` (identical source == destination path) is either eliminated (recovery loop is scanning already-replaced files) OR downgraded to INFO with rationale. Baseline: 500+ hits/48h across ~50 distinct files. A "recovery" that recovers nothing is either a bug in the scanner's terminated-attempt detection OR successful recovery that shouldn't be a WARNING.

### Group D -- worker config discovery

C12. `ProcessTranscodeQueueService: FFprobePath was NULL on worker init; discovered ... Persist this in Workers.FFprobePath for I9-2024` and companion FFmpegPath warning both drop to zero. Baseline: 67 + 67 hits/48h. The warning text names the fix: self-persist the discovered path. Feedback memory `feedback_all_installs_via_requirements_txt.md` context applies -- if this is a deploy-provisioning gap, the deploy artifact is the fix.

### Group E -- video-transcoding logger misuse

C13. `VideoTranscodingService: FFmpeg stdout: ffmpeg version ...` no longer logs the FFmpeg version banner at ERROR level. Baseline: 15 hits/48h. FFmpeg's normal stdout is not an error. Fix: gate on process return code / stderr regex, not on "FFmpeg emitted output".

### Group F -- thread context

C14. `WebService: Jellyfin auto-sync error: WorkerContext.Current called on unbound thread. Call WorkerContext.Bind() at thread entry` drops to zero. Baseline: 12 hits/48h. Fix: call `WorkerContext.Bind()` in the auto-sync thread's entry function.

### Group G -- audio classification noise

C15. `SelectPreferredAudioStream: No English audio stream found among 1 stream(s) (languages: [X]), using first stream` (where X is `und`/`fre`/`dan`/`hin`/etc) is either eliminated for `und` (single-`und` stream is the normal case for a lot of media -- it should not warn) OR downgraded to INFO. Baseline: 316+ hits/48h across languages. Non-English single-stream media landing here isn't a failure; it's the expected fallback.

### Group H -- deploy-artifact hygiene

C16. `ContentSignalsService: PySceneDetect not installed; SceneChangeRatePerMin will be NULL` drops to zero. Baseline: 5 hits/48h. Add `scenedetect>=0.6.0` to `requirements.txt` per `feedback_all_installs_via_requirements_txt.md`; redeploy Linux workers.

C17. `SchemaChecker: no snapshot at /opt/mediavortex/.claude/schema/snapshot.json` drops to zero. Baseline: 4 hits/48h. Either the snapshot is missing from the Linux worker container image OR `GenerateSchemaSnapshot.py` needs to run at deploy time. Snapshot presence would have caught C4 pre-deploy.

### Group I -- meta

C18. Every bug discovered during triage lands one of two outcomes: fixed in this directive with a `## Bugs Fixed` row + commit ref, or filed as `/b BUG-NNNN` with a written reason it cannot be part of this directive (irreversible migration, hardware requirement, design work). Zero silently deferred bugs.

C19. `memory/KNOWN-ISSUES.md` is swept: every entry marked RESOLVED in this directive is moved to the Resolved section; every entry still Active is re-verified against current code (root cause still applies, repro still reproduces, or entry is closed/rewritten).

C20. Post-fix soak: `SELECT LogLevel, FunctionName, LEFT(Message, 200), COUNT(*) FROM Logs WHERE Timestamp > <post-deploy-ts> AND LogLevel IN ('WARNING','ERROR','CRITICAL') GROUP BY 1,2,3 ORDER BY 4 DESC LIMIT 20` shows no C1-C17 pattern in the top 20. New patterns discovered during soak flow through C18.

### Group J -- diagnostic capture (added 2026-07-18 after rc=222 blind investigation)

C21. On any non-zero FFmpeg returncode, the tail of FFmpeg stderr (last 4 KB) writes to `TranscodeAttempts.ErrorMessage` AND to a `LoggingService.LogError` with `ClassName='VideoTranscodingService'` / `'QualityTestingBusinessService'` and the full attempt Id. Baseline: 38 non-zero returncodes/48h with zero stderr captured in `Logs` -- every failure a black box (root cause of rc=222 cluster unknown without pulling live ffmpeg re-runs). Fix: `Features/TranscodeJob/VideoTranscodingService.py:~164-172` and `Features/QualityTesting/QualityTestingBusinessService.py:~966-974` -- restructure the `Process.communicate()` block so `ErrorOutput` tail is captured into a variable that is (a) returned to the caller for persistence on the attempt row and (b) logged at ERROR when `returncode != 0`. Complements C13 (which stops logging FFmpeg output on returncode==0). Verification: force one rc=222 attempt post-fix; `SELECT ErrorMessage FROM TranscodeAttempts WHERE Id = <n>` returns the encoder's actual error text.

## Fix Plan

One entry per criterion. KISS: smallest surgical fix that does not break upstream producers or downstream consumers. Investigated 2026-07-17/18.

### C1 -- `ExtractShowInfo` Path constructor missing 'RelativePath'

**File:** `Features/FileScanning/FileScanningBusinessService.py:1038`
**Root cause:** `Path(FileName).stem` -- `Path` at module scope binds to `Core.Path.Path` (line 19 import), which requires `(StorageRoot, RelativePath)`. `pathlib.Path` is aliased as `PyPath` (line 8). Bug is one identifier.
**Fix:** `NameWithoutExt = PyPath(FileName).stem` -- filename-only manipulation, no filesystem access, no shape issues. `PyPath` already imported.
**Ripple:** None. `ExtractShowInfo` returns dict; callers unchanged.

### C2, C3 -- `FileScanningRepository` missing `GetMediaFilesByRootFolder[Id]`

**File:** `Features/FileScanning/FileScanningBusinessService.py:1128, 1162, 1416, 1863, 1971, 2092, 2264` (7 call sites)
**Root cause:** Callers use `self.Repository.GetMediaFilesByRootFolder[Id](...)` but those methods live on `MediaFilesRepository`. `FileScanningBusinessService.__init__` already binds `self.MediaFilesRepository` at line 92.
**Fix:** Replace all 7 `self.Repository.GetMediaFilesByRootFolder` -> `self.MediaFilesRepository.GetMediaFilesByRootFolder` (both suffixes). One-line rename per site.
**Ripple:** None -- method signatures + return shapes identical. `FileScanning.feature.md:230` already documents the two-repository split; no doc change.

### C4 -- `MediaProbeRepository` reads non-existent `RootFolder` column

**Files:** `Features/MediaProbe/MediaProbeRepository.py:66, 105` (get + count) AND `Features/MediaFiles/MediaFilesRepository.py:340` (cascades into C2/C3 fix)
**Root cause:** Schema migration renamed `RootFolders.RootFolder` -> `RootFolders.StorageRootId + RelativePath` typed pair. Three SQLs still read the old column.
**Fix:** Replace `SELECT RootFolder FROM RootFolders WHERE Id = %s` with `SELECT StorageRootId, RelativePath FROM RootFolders WHERE Id = %s`. Downstream `Path.FromLegacyString(RootPath, GetStorageRoots())` becomes direct `Path(StorageRootId=row['StorageRootId'], RelativePath=row['RelativePath'])` -- no legacy string parse required, one hop shorter.
**Ripple:** `MediaFilesRepository.GetMediaFilesByRootFolderId` (line 337-344) also affected -- rewrite to read the typed pair and hand it to `GetMediaFilesByRootFolder`, or reshape `GetMediaFilesByRootFolder` to accept typed args directly. KISS choice: leave `GetMediaFilesByRootFolder(RootFolderPath)` signature intact; construct the canonical string via `Path(...).ToCanonicalString()` inside `GetMediaFilesByRootFolderId`. Zero callers of the outer func change.

### C5 -- `LocalPath op refused canonical drive-letter path on non-Windows`

**File:** `Features/FileScanning/FileScanningRepository.py:NormalizePathToFilesystemCase` (~line 700-754)
**Root cause:** Function is a Windows-only NTFS case-normalization helper (`ntpath.join`, drive-letter parse, `os.listdir` walk to fix case). On Linux workers, called with 'M:\\' / 'T:\\' input; `LocalIsDir` at line 733 triggers `_AssertLocalShape` guard. Line 754 has separate bug: `return Path` returns the imported class instead of the parameter.
**Fix:** Two lines. Guard at top of function: `from Core.Path.LocalPath import _IS_WINDOWS` (or copy the `platform.system() == 'Windows'` check locally); `if not _IS_WINDOWS: return Path` -- Linux filesystems are case-sensitive; input is already canonical; nothing to normalize. Fix line 754 `return Path` -> `return current_path` (or whatever the input parameter is actually named -- read first).
**Ripple:** None. Windows workers keep exact current behavior; Linux workers return identity instead of crashing.

**Domain question resolved 2026-07-18:** Linux workers should never receive drive-letter paths for FS ops -- upstream should have canonicalized. This guard is defense-in-depth; if it fires, log INFO once per worker-startup naming the caller for follow-up, then return identity.

### C6, C7, C8, C9 -- deferred to `mediafiles-uniqueness-owner`

Not fixed in this directive. See scope note above.

### C10 -- Pokémon `-mv` re-admission spam

**Table:** `TranscodeQueue`
**Root cause:** Rows pre-date commit 7e562a9 (2026-07-15) which added the `-mv` exclusion to the admission gate. Existing rows re-hit the refusal every claim cycle.
**Fix:** SQL migration `Scripts/SQLScripts/PurgeStaleMvQueueRows_2026_07_18.py` (idempotent, `DELETE FROM TranscodeQueue WHERE FilePath LIKE '%-mv.mp4%'` with pre-count + post-count log). Pre-flight query first to confirm no in-progress claim (`ProcessingStatus IS NULL OR ProcessingStatus NOT IN ('Claimed', 'InProgress')`).
**Ripple:** Zero -- workers already refuse these rows; deletion just stops the WARN.

### C11 -- `CrashRecoveryService` X -> X spam (skip + downgrade)

**File:** `Features/ServiceControl/CrashRecoveryService.py:_RecoverInProgressArtifacts (~line 400-460)`
**Root cause:** Loop processes `.inprogress` artifacts; for each, calls `FinalizePartialReplacement`. When the artifact has already been replaced on a prior tick, `LocalSource == FinalPath` and the call is a no-op that still logs a WARN.
**Fix (two changes):**
1. Skip: before calling `FinalizePartialReplacement`, check `if LocalSource == FinalPath and LocalExists(FinalPath) and not LocalExists(LocalSource + '.inprogress'): continue`. Nothing to recover -- artifact is already finalized.
2. Downgrade: change `LoggingService.LogWarning` at line 455-458 -> `LoggingService.LogInfo`. Successful recovery is not a warning.

**Ripple:** None. Callers ignore return; log-level change doesn't affect flow.

### C12 -- `FFprobePath was NULL on worker init` (stale-pyc cite)

**Root cause:** Exact warning string does not exist in the current source tree. Container is running stale bytecode per BUG-0085 (`Docker build-cache leaks pre-Reset-9 .pyc into worker containers`). The self-heal path in `ProcessTranscodeQueueService.__init__:73-99` already discovers + persists paths + LogInfo on success; no live code path emits the exact WARN.
**Fix:** Not a code change in e2e-bug-fixes. Verify affected workers: `docker exec <worker> find /opt/mediavortex -name __pycache__ -exec rm -rf {} +; docker compose restart worker-N`. Cite BUG-0085 for durable fix.
**Ripple:** BUG-0085 durable Dockerfile fix is a separate directive.

### C13 -- FFmpeg version banner logged at ERROR

**Files:** `Features/TranscodeJob/VideoTranscodingService.py:168` and `Features/QualityTesting/QualityTestingBusinessService.py:970`
**Root cause:** After `Process.communicate()`, both files call `LoggingService.LogError(f"FFmpeg stdout: {Output}", ...)` if `Output` truthy. FFmpeg's stdout carries the version banner + progress on normal runs; only meaningful when muxing to stdout (which we do not).
**Fix:** Gate on `Process.returncode`. Rewrite the block:
```python
if Process.returncode != 0:
    if Output:
        LoggingService.LogError(f"FFmpeg stdout: {Output}", ...)
    if ErrorOutput:
        LoggingService.LogError(f"FFmpeg stderr: {ErrorOutput}", ...)
```
Two files, same pattern. If return code is 0 and non-empty Output, the caller already succeeded; nothing to log.

**Ripple:** None -- downstream code already checks return code separately. Log volume drops without losing signal.

### C14 -- Jellyfin auto-sync WorkerContext unbound

**File:** `WebService/Main.py:sync_worker` inside `_start_jellyfin_sync` (~line 205-222)
**Root cause:** Thread spawned at 220 doesn't call `WorkerContext.Bind()`. Downstream `RefreshJellyfinData()` -> ... -> `WorkerContext.Current()` at some deep call site raises.
**Fix:** At top of `sync_worker` body, before any other call: `WorkerContext.Bind(WorkerContextForWebService())` or the equivalent WebService pseudo-worker binding pattern. Look at other WebService threads (e.g. `AudioVerticalHealthService`, `FileReplacementSelfHealService` per web.out log) for the canonical bind call.
**Ripple:** None -- adds one line at thread entry.

**Domain question resolved:** WebService already has a pseudo-worker binding pattern for background threads; reuse it here.

### C15 -- SelectPreferredAudioStream noise (silence single-stream, warn multi-no-english)

**File:** grep for `SelectPreferredAudioStream` producer (likely `AudioStateService` or `MediaProbeBusinessService`)
**Root cause:** Every non-English audio stream, single or multi, emits the same WARN. Single-`und` is the common case and shouldn't warn.
**Fix:** Wrap the warning: `if len(streams) > 1: LogWarning(...) else: LogInfo(...)`. One stream = no choice was available; multi-stream + no English = operator may want to investigate.
**Ripple:** None.

### C16 -- PySceneDetect not installed

**File:** `requirements.txt` + Linux worker deploy
**Root cause:** `Features/ContentSignals/ContentSignalsService.py` uses PySceneDetect for scene-change-rate; dep missing on the Linux worker venv.
**Fix:** Add `scenedetect>=0.6.0` to `requirements.txt`. Redeploy Linux workers per `feedback_all_installs_via_requirements_txt.md`.
**Ripple:** None -- new optional dep; behavior on Windows workers (where it's already installed) unchanged.

### C21 -- FFmpeg stderr tail capture on non-zero exit

**Files:** `Features/TranscodeJob/VideoTranscodingService.py:~164-172` and `Features/QualityTesting/QualityTestingBusinessService.py:~966-974`
**Root cause:** `Process.communicate()` returns `(Output, ErrorOutput)`; current code only conditionally LogErrors them (see C13). Neither branch persists `ErrorOutput` to `TranscodeAttempts.ErrorMessage` -- the row gets a synthetic `f"Transcode failed: Transcoding failed with return code {rc}"` string with zero encoder detail. 38 failures/48h, all unlabeled.
**Fix:** In both files, on returncode != 0:
```python
if Process.returncode != 0:
    StderrTail = (ErrorOutput or b'').decode('utf-8', errors='replace')[-4096:]
    LoggingService.LogError(f"FFmpeg stderr (tail): {StderrTail}", ClassName, MethodName)
    # return / raise with StderrTail attached so caller writes it to TranscodeAttempts.ErrorMessage
```
Caller update: `ProcessTranscodeQueueService.HandleTranscodingResult` (or wherever the "Transcode failed: ..." string is composed) appends the tail: `ErrorMessage = f"rc={rc}: {StderrTail}"`.
**Ripple:** `TranscodeAttempts.ErrorMessage` is `TEXT` — no schema change. Downstream consumers (dispatcher, Activity dashboard) already TREAT ErrorMessage as free-form text. Slight column-size growth is bounded (4 KB max).

### C17 -- SchemaChecker snapshot missing

**Files:** `Scripts/Migration/GenerateSchemaSnapshot.py` (source) + `.claude/schema/snapshot.json` (artifact) + `deploy/Dockerfile` (Linux worker container image)
**Root cause:** Snapshot artifact not present at `/opt/mediavortex/.claude/schema/snapshot.json` in the Linux worker container. Either not copied by `deploy/Dockerfile`, or the file is git-ignored and never generated on the build host.
**Fix (investigate first, then choose):**
- If snapshot IS in git: check `deploy/Dockerfile` `COPY` step covers `.claude/schema/` prefix. Likely one glob change.
- If snapshot is NOT in git: run `py Scripts/Migration/GenerateSchemaSnapshot.py` at deploy time as a prebuild step in `deploy/deploy-linux-worker.py`; add snapshot regeneration to the deploy pipeline. Prefer this: snapshot then reflects the actual schema at deploy, not a stale checked-in copy.
**Note:** Presence of this snapshot would have caught C4 pre-deploy. Fix C17 has compounding value.
**Ripple:** None on the Windows path.

## Seams

_Enumerated at NEEDS_STANDARDS_REVIEW per `.claude/rules/seam-verification.md`. Cross-stage seams already covered by `transcode.flow.md ## Seams` are referenced by ID; only new or changed seams get restated here._

## Scope

**IN:** bugs and failure modes discovered while triaging the end-to-end pipeline. Production-code fixes, contract tests for regressions, schema migrations required to unblock a specific stuck path, sweeper / stuck-detect regressions, previously-silent data-integrity self-heal.

**OUT:** architectural refactor, feature additions, DDD/SOLID polish beyond what a specific bug fix requires, doc-hub restructuring, new verticals, performance work absent an outright failure.

If a bug fix reshapes a small piece of nearby code, that is in scope. "While I'm here" adjacent cleanup is not.

## Files

_Populated as bugs are triaged and fixes land._

## Bugs Fixed

| # | Discovered | Symptom | Root cause | Fix commit |
|---|-----------|---------|-----------|-----------|

## Bugs Deferred

| BUG-NNNN | Symptom | Reason deferred |
|---------|--------|----------------|

## Status

**Phase:** NEEDS_STANDARDS_REVIEW
**Owner:** claude-opus-4-7
**Opened:** 2026-07-17
**Stack position:** top (interrupts audio-vertical-dialog-boost-enforcement)

### Progress

- [ ] NEEDS_STANDARDS_REVIEW: read `.claude/rules/*.md` + `.claude/standards/index.md`; run call-graph-audit five signals against affected paths (path plumbing / replacement / crash recovery / logger paths)
- [ ] NEEDS_PLAN: `## Files` populated per criterion; `## Seams` populated per `seam-verification.md`
- [ ] NEEDS_PLAN: priority order committed (Group A path plumbing first -- other groups mask on top of it)
- [ ] NEEDS_DOC_PREREAD: read every colocated `*.feature.md` / `*.flow.md` ancestor of files in `## Files`
- [ ] IMPLEMENTING C1..C5 (Group A path plumbing)
- [ ] IMPLEMENTING C6..C10 (Group B replacement / uniqueness)
- [ ] IMPLEMENTING C11 (Group C crash-recovery no-op storm)
- [ ] IMPLEMENTING C12 (Group D worker config discovery self-persist)
- [ ] IMPLEMENTING C13 (Group E logger level fix)
- [ ] IMPLEMENTING C14 (Group F WorkerContext bind on jellyfin auto-sync thread)
- [ ] IMPLEMENTING C15 (Group G audio classification noise)
- [ ] IMPLEMENTING C16..C17 (Group H deploy artifacts)
- [ ] VERIFYING: 60-min post-fix soak on I9 + one Linux worker; C20 top-20 query clean
- [ ] VERIFYING: sweep `memory/KNOWN-ISSUES.md` per C19
- [ ] DELIVERING: `### Promotions` populated (durable lessons -> per-vertical feature/flow docs or KNOWN-ISSUES rewrites); close report; stack pop
