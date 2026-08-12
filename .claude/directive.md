# Directive: preencode-loudness-cache-hit

**Status:** Active -- phase: IMPLEMENTING

**Slug:** preencode-loudness-cache-hit

**Interrupts:** worker-memorymax-cgroup (top of `.claude/current-feature` stack) -- MemoryMax=14G is deployed to wakko; observation ongoing. Pausing to fix upstream root cause.

### Promotions

- (populated at DELIVERING)

## What / Why

`PreEncodeAudioPipeline.Run._RunSourceMeasureTask` unconditionally invokes `DemucsService.MeasureSourceLoudnorm(SourceFilePath)` on every Dialog Boost job. This runs a full ffmpeg loudnorm-analysis pass on the source (~30-90s of ffmpeg wall + subprocess RAM footprint).

The measurement it produces (`SourceIntegratedLufs`, `SourceLoudnessRangeLU`, `SourceTruePeakDbtp`, `SourceIntegratedThresholdLufs`) is already persisted on `MediaFiles` from prior runs. Once a source has been measured, the values are stable (source file is bit-exact-unchanged per audio-normalization.C7). Re-measuring wastes ffmpeg time + RAM.

**Historical context:** commit `6856ac70 2026-08-06 perf(probe): remove EBU R128 loudness measurement from probe path` correctly removed the probe-time measurement (SRP win) but the corresponding cache-hit in `PreEncodeAudioPipeline.Run` was never added. Every Dialog Boost job now re-measures at transcode-time. This is the root cause of the wakko-worker-1 OOM cadence that started 2026-08-06 (30-50 crashes since; documented in the paused `worker-memorymax-cgroup` directive).

Fix: check `MediaFiles` row for populated source-loudness columns before invoking `MeasureSourceLoudnorm`. Cache-hit path skips the ffmpeg subprocess entirely; cache-miss path (fresh probe or missing columns) runs the measurement + persists it.

## Domain Decisions (operator, 2026-08-12)

D1. Cache-hit predicate: all four columns non-NULL on the `MediaFiles` row → skip ffmpeg pass, use cached values. Any column NULL → run ffmpeg pass, persist to MediaFiles.

D2. No new measurement invalidation gate (e.g. LoudnessMeasuredAt age check) -- the source file is bit-exact-unchanged invariant (audio-normalization.C7 + MediaFilesArchive semantics), so cached measurements never go stale unless the file itself is replaced. Replace-path MUST reset the 4 source-loudness columns to NULL (existing behavior per prior probe-loudness design; NEEDS_PLAN grep task verifies this + adds reset if missing -- in-scope guardrail).

D3. Persistence sink: cache-miss path must write measurements back to `MediaFiles` (SourceIntegratedLufs, SourceLoudnessRangeLU, SourceTruePeakDbtp, SourceIntegratedThresholdLufs, LoudnessMeasuredAt) so the next job hits the cache. Existing writer at `Features/AudioNormalization/Services/AudioPreEncodeFacade.py:80` (per probe.feature.md C5 reference) already does this -- confirm still wired; add if not.

## Scope

1. `PreEncodeAudioPipeline._RunSourceMeasureTask` accepts `MediaFileId` (new arg). Reads `MediaFiles` row; if all four source-loudness columns are non-NULL, returns the cached tuple without running ffmpeg.
2. `PreEncodeAudioPipeline.Run` passes `MediaFileId` through from its caller (`AudioPreEncodeFacade.Prepare`).
3. `AudioPreEncodeFacade.Prepare` signature already carries `SourceFilePath` + `JobId`; add `MediaFileId` param or lookup via JobId.
4. Cache-miss path unchanged from today (ffmpeg pass + persist).
5. Contract test: mocked repo returns fully-populated row → `MeasureSourceLoudnorm` NOT invoked, tuple returned matches DB values. Mocked repo returns partial row → `MeasureSourceLoudnorm` IS invoked, DB write occurs.
6. Live smoke on I9 (or wakko): run one Dialog Boost job whose MediaFile already has loudness columns → confirm `SourceMeasure` phase completes in <1s (cache hit) instead of ~30-90s (ffmpeg pass). Log line differentiates hit vs miss.
7. `audio-normalization.feature.md` amended at DELIVERING with the cache-hit criterion + reference to attempt 60358 baseline (or whatever the smoke job is).
8. Observation on wakko-worker-1: OOM cadence should lengthen dramatically after this ships (SourceMeasure ffmpeg subprocess memory removed from peak; my parallelization no longer stacks that footprint with Demucs).

## Out of Scope

(a) Reverting commit `6856ac70` (probe loudness removal) -- category (c) unrelated: probe should stay metadata-only per SRP. This directive adds the missing cache-hit at the transcode-time consumer.
(b) `worker-memorymax-cgroup` refinement -- category (b) deferred: complete observation on paused directive after this ships; may become unnecessary if cache-hit alone drops wakko OOM to zero.
(c) LoudnessMeasuredAt staleness check -- category (a) tolerated per D2: source-file-immutable invariant makes staleness impossible in normal flow.

## Call-Graph Audit

- **Multiple flow docs.** `transcode.flow.md` remains SoT. No new flow.
- **Orchestration mode-branching.** Cache-hit vs cache-miss is a DATA branch inside `_RunSourceMeasureTask`; same function returns same tuple shape either way. Not an orchestration mode branch.
- **Mode-sparse columns.** Source-loudness columns already written by every mode's audio path via `AudioPreEncodeFacade` (per audio-normalization.C37). No new sparsity.
- **OOS clarity.** (a)/(b)/(c) each explicitly typed.
- **Config-driven graph shape.** No new flag. Data-driven cache-check; same functions called either way.

## Acceptance Criteria

C1. `_RunSourceMeasureTask` accepts `MediaFileId: int` param. Before invoking `MeasureSourceLoudnorm`, reads `MediaFiles` row via existing repository; if `SourceIntegratedLufs`, `SourceLoudnessRangeLU`, `SourceTruePeakDbtp`, `SourceIntegratedThresholdLufs` are all non-NULL, returns `(SourceIntegratedLufs, SourceLoudnessRangeLU, SourceTruePeakDbtp, SourceIntegratedThresholdLufs)` and emits a DEBUG log line: `SourceMeasure cache-hit MediaFileId=<id>` (DEBUG because hits will be the majority path -- avoid log flood).

C2. Cache-miss path (any column NULL) runs the existing `MeasureSourceLoudnorm` ffmpeg pass, returns the fresh tuple, and persists to `MediaFiles` via the existing writer path (`AudioPreEncodeFacade` or equivalent). INFO log line: `SourceMeasure cache-miss MediaFileId=<id>; ran ffmpeg loudnorm scan (took <n>s)` (INFO because miss should be rare once cache warms).

C3. Contract test `Tests/Contract/TestSourceMeasureCacheHit.py` (NEW) covers: (a) fully-populated row → mock `DemucsService.MeasureSourceLoudnorm` NOT called (assert 0 invocations), returned tuple equals DB values. (b) partial row (any column NULL) → mock IS called (assert 1 invocation), returned tuple equals mock return. (c) all-NULL row → cache miss (same as partial).

C4. `PreEncodeAudioPipeline.Run` signature updated to accept `MediaFileId` param (already has `SourceFilePath, JobId`); caller `AudioPreEncodeFacade.Prepare` passes it through.

C5. Live smoke on I9: pick one MediaFile with all four source-loudness columns populated + queue a Dialog Boost job (Transcode or Remux mode) → observe log line `SourceMeasure cache-hit for MediaFileId=<id>` fires; `TranscodeProgress.SourceMeasure` completes within 2 seconds instead of 30-90s. Compare `TranscodeAttempts.CompletedDate - AttemptDate` vs a baseline cache-miss job on similar-length source.

C6. Live observation on wakko-worker-1 post-deploy: over 2h, count OOM events via `journalctl -u mediavortex-worker@1.service --since='2h ago' | grep 'killed by'`. Ship-gate: OOM cadence extends to >=30 min between kills (vs current ~10 min with 14G cap).

## Principle Analysis

**KISS.** One function signature change + one if-branch inside `_RunSourceMeasureTask`. No new subsystems. No new dependencies.

**DDD.** Change stays in `Features/AudioNormalization/Services/`. Repository read uses existing `MediaFileRepository` interface. No cross-context bleed.

**DRY.** Cache-hit path reuses existing DB row shape. Cache-miss path reuses existing `MeasureSourceLoudnorm` + `AudioPreEncodeFacade` persistence. No duplicate code.

**SOLID.**
- SRP: `_RunSourceMeasureTask` still has one responsibility (produce source-loudness tuple); its input surface widens to include a cache lookup, but the output contract is unchanged.
- OCP: cache-hit predicate is a new branch inside the task, not a new subclass or hook. Not a violation.
- LSP: n/a.
- ISP: no new interface.
- DIP: repository injected via existing DI path.

**SSoT.** `MediaFiles` source-loudness columns remain the SoT for per-file loudness. Cache-hit READS from SoT; cache-miss WRITES to SoT then reads. No parallel data path.

## Files

- `Features/AudioNormalization/Services/PreEncodeAudioPipeline.py` (add MediaFileId param + cache-hit branch in `_RunSourceMeasureTask`; `Run` plumbs MediaFileId through)
- `Features/AudioNormalization/Services/AudioPreEncodeFacade.py` (pass MediaFileId from caller into `PreEncodeAudioPipeline.Run`)
- `Features/MediaFile/Repositories/MediaFileRepository.py` (if a targeted 4-column read helper doesn't exist, add `GetSourceLoudness(MediaFileId) -> Optional[Tuple[float, float, float, float]]`)
- `Tests/Contract/TestSourceMeasureCacheHit.py` (NEW, per C3)
- `Features/AudioNormalization/audio-normalization.feature.md` (amend at DELIVERING with new criterion C43 covering cache-hit shape)

## Progress

- [ ] NEEDS_STANDARDS_REVIEW: rules + standards index (already loaded).
- [ ] NEEDS_PLAN:
    - Confirm caller chain has MediaFileId available (search `PreEncodeAudioPipeline.Run` call sites).
    - Confirm existing MediaFileRepository shape for 4-column source-loudness read; add `GetSourceLoudness(MediaFileId)` method if missing.
    - **Verify existing writer at `AudioPreEncodeFacade.py:80` (per probe.feature.md C5 reference) still persists all 4 source-loudness columns.** If drifted or removed, add writer (SSoT preserved but scope +1 file).
    - **Verify `FileReplacementBusinessService` (or wherever source-replacement lands) RESETS the 4 loudness columns to NULL when a source file is replaced.** If not, stale cache could return old-source loudness for a new source → wrong Track 1 loudnorm → wrong output. If gap exists, add reset (in-scope guardrail; not a new directive).
    - Query DB for a real MediaFile with all 4 columns populated to use as the C5 live-smoke fixture (`SELECT Id, Filename FROM MediaFiles WHERE SourceIntegratedLufs IS NOT NULL AND SourceLoudnessRangeLU IS NOT NULL AND SourceTruePeakDbtp IS NOT NULL AND SourceIntegratedThresholdLufs IS NOT NULL AND ... LIMIT 5`).
- [ ] NEEDS_DOC_PREREAD: Read colocated docs for touched files (audio-normalization.feature.md sections covering C7/C37/C42).
- [ ] IMPLEMENTING: refactor + contract test.
- [ ] VERIFYING: contract test + live smoke per C5 + wakko observation per C6.
- [ ] DELIVERING: Promotions, feature-doc amendment, delivery report.

## Deviation from conventions

No new `preencode-loudness-cache-hit.feature.md` file. This is an incremental optimization to the audio pre-encode pipeline (owned by `audio-normalization.feature.md`); a new feature doc would fragment the contract. Change lands as a new criterion (C43 or next available) in the existing feature doc at DELIVERING per doc-layering promotions rule.
