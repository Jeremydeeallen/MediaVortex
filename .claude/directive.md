# Directive: pre-encode-pipeline-parallel

**Status:** Active -- phase: IMPLEMENTING

**Slug:** pre-encode-pipeline-parallel

**Interrupts:** probe-loudness-remove (top of `.claude/current-feature` stack)

### Promotions

- (populated at DELIVERING; hook requires non-empty section for close transition)

## What / Why

`Features/AudioNormalization/Services/PreEncodeAudioPipeline.Run` runs five sequential subprocess passes per Dialog Boost job: `SourceMeasure` → `Downmix` → `Demucs` → `Premix` → `LoudnormMeasure`. Total ~5-6 minutes before the main ffmpeg encode even starts (measured on I9, MediaFileId 691056, attempt 59758: 5:57 pre-encode wall on 10:48 total).

`SourceMeasure` and `Downmix` both read the source file only. They are independent of each other AND of the `Demucs` → `Premix` → `LoudnormMeasure` chain that follows them. Currently sequential; can be parallelized.

Expected wall reduction: `SourceMeasure(3:37) + Downmix(20s) + Demucs(~1-2min) + Premix(20s) + LoudnormMeasure(30s)` = 5:47-6:47 sequential → `max(SourceMeasure, Downmix+Demucs+Premix+LoudnormMeasure)` = ~3:37 parallel. **Save ~2-3 minutes per Dialog Boost job.**

Every media file needs Dialog Boost per operator domain decision. The audio pre-pipeline is the dominant fixed cost per file. Reducing it wins wall time on every job.

## Domain Decisions (operator, 2026-08-11)

D1. Ship SourceMeasure-parallelization only. Defer the other two theoretical optimizations (filter-graph fold, streamed loudnorm→encode) to a separate directive if measured wins warrant.

D2. Correctness invariant: loudnorm parameters produced by the parallel path MUST equal the sequential-path outputs bit-for-bit (SourceI, SourceLra, SourceTp, SourceThresh). No numeric drift allowed.

## Scope

1. Refactor `PreEncodeAudioPipeline.Run` to spawn `SourceMeasure` in one thread while the current `Downmix` → `Demucs` → `Premix` → `LoudnormMeasure` chain runs in the caller thread. Join both before returning.
2. Return dict shape unchanged: `SourceMeasuredI/Lra/Tp/Thresh` + `PremixMeasuredI/Lra/Tp/Thresh` + `DemucsPremixPath`.
3. Progress reporting stays functional: both threads emit their own `_Report(...)` calls to `ProgressReporter`. `TranscodeProgress` receives interleaved rows; `LastProgressUpdate` still advances per D10 (stuck-detect signal).
4. Failure propagation: any thread failure raises to the caller with the original exception; the other thread's subprocess is signaled to terminate (best-effort SIGTERM) to avoid orphaned ffmpeg.
5. Contract test asserts parallel path produces identical loudnorm params to sequential path on a fixture.
6. Live smoke on I9: run one Remux job with Dialog Boost enabled. Wall time measurement + audit that final `TranscodeAttempts.AudioPolicyResolved='resolved'` + `AudioTracksEmittedJson` shape unchanged.

## Out of Scope

(a) Filter-graph fold (combine `Downmix` + `Premix` + `LoudnormMeasure` into a single ffmpeg filter graph) -- category (b) deferred: separate optimization, warrants its own directive if worth it after this ships.

(b) Streamed loudnorm-measure → encode (avoid the two-pass split on the final Dialog Boost track) -- category (b) deferred: same reason.

(c) Skip SourceMeasure via reuse of a prior `MediaFiles.SourceIntegratedLufs` value -- category (a) tolerated debt: caching stale measurements adds an invalidation risk; safer to just parallelize.

(d) GPU-Demucs adoption on larry (CPU-only host) -- category (c) unrelated: hardware limitation, not a pipeline shape concern.

(e) CpuAffinityService pinning removal -- category (c) unrelated: pinning ffmpeg to explicit core masks is questionable-value engineering separate from this pipeline shape change. Deferred to a follow-up review. Concurrent ffmpeg from this directive's parallel path may share the same pinned mask; OS scheduler handles this cleanly on I9 (24 cores) + larry (many cores) so not a blocker here.

## Call-Graph Audit

- **Multiple flow docs for one operation.** `transcode.flow.md` remains SoT. Audio pipeline shape doesn't change; parallelism is an internal reordering.
- **Orchestration-level mode-branching.** No new mode branch. Parallel is unconditional (fires for every Dialog Boost job).
- **Mode-sparse output columns.** No new column writes. Existing dict shape preserved.
- **OOS ambiguity.** All four OOS items explicitly typed. No silent debt.
- **Config-driven call-graph shape.** No new flag. Same subprocesses, same order, same outputs -- just concurrent instead of serial.

## Acceptance Criteria

C1. `PreEncodeAudioPipeline.Run` returns a dict whose numeric loudnorm fields (`SourceMeasuredI/Lra/Tp/Thresh`, `PremixMeasuredI/Lra/Tp/Thresh`) are byte-identical to the pre-refactor sequential path for the same fixture input. Contract test asserts equality against a golden output derived from the sequential baseline.

C2. Wall time for the pre-encode audio pipeline (measured `end_of_LoudnormMeasure - start_of_first_subprocess`) on I9 with Dialog Boost enabled reduces by >=90 seconds vs the pre-refactor baseline for the same fixture (or same-shape fresh source). Fixture: a 30-60 min episode with audio needing loudnorm.

C3. `TranscodeProgress` rows continue to advance during the pipeline. `LastProgressUpdate` timestamp advances at least every 30s across both threads' reporters. Stuck-detect per D12 in `transcode.flow.md` continues to see fresh progress.

C4. On any subprocess failure in either thread, the caller raises with the original exception. Peer thread is joined normally (allowed to finish its subprocess); no attempt to signal peer. Extra wasted work in the rare failure case is accepted in exchange for zero subprocess-handle plumbing. Long-lived orphan risk mitigated by existing stuck-detect + process death.

C5. Feature doc `Features/AudioNormalization/audio-normalization.feature.md` amended (at DELIVERING) with a criterion documenting the parallel shape + the concurrency invariant.

C6. Live smoke on I9 (mandatory per `ceo-mode.md#smoke-gate-verifying---delivering`):
- Drain I9, deploy the change, set Online, wait for one Remux-with-Dialog-Boost job to complete.
- Capture wall time from `AttemptDate` to `CompletedDate`.
- Capture `TranscodeDurationSeconds` (encoder-only).
- Compare wall - `TranscodeDurationSeconds` (audio pre-pipeline + overhead) to baseline (~5:57 on 59758).
- Ship-gate: parallel wall for audio pre-pipeline is <= baseline - 90s.

## Principle Analysis

**KISS.** One thread wrapper around existing `MeasureSourceLoudnorm` call. Rest of Run unchanged. Existing subprocess management preserved.

**DDD.** Audio pre-encode pipeline stays in `Features/AudioNormalization/Services/`. Threading concern lives inside `PreEncodeAudioPipeline`. No cross-context leakage.

**DRY.** Reuses existing `_Report`, `MeasureSourceLoudnorm`, `_ExtractStereoDownmix`, `IsolateVocals`, `MixBoostedPremix`, `MeasurePremixLoudnorm` methods. No parallel implementation.

**SOLID.**
- SRP: `Run` orchestrates; helper methods unchanged.
- OCP: new thread wrapper doesn't touch subprocess implementations.
- LSP: return dict shape identical; caller sees no difference.
- ISP: no new interfaces.
- DIP: threading uses stdlib; no new dependency.

**SSoT.** Loudnorm measurement outputs remain SoT for downstream encode parameters; parallel path computes the same values with the same subprocess.

## Files

- `Features/AudioNormalization/Services/PreEncodeAudioPipeline.py` (refactor `Run` -- SourceMeasure thread + join)
- `Tests/Contract/TestPreEncodePipelineParallel.py` (NEW: assert byte-identical loudnorm params vs sequential baseline)
- `Features/AudioNormalization/audio-normalization.feature.md` (amend at DELIVERING with parallel-shape criterion)

## Progress

- [ ] NEEDS_STANDARDS_REVIEW: rules + standards index (already loaded).
- [ ] NEEDS_PLAN: decide thread-vs-multiprocess (thread wins: subprocesses are the CPU work; Python code just orchestrates), decide failure propagation shape (settled: propagate, don't kill peer), capture C1 golden baseline (run current sequential path on the fixture, record loudnorm outputs, commit as `Tests/Contract/fixtures/preencode_loudnorm_baseline.json` before refactor lands).
- [ ] NEEDS_DOC_PREREAD: Read `Features/AudioNormalization/audio-normalization.feature.md` + `.flow.md` sections covering the audio pre-pipeline.
- [ ] IMPLEMENTING: refactor Run + contract test.
- [ ] VERIFYING: contract test + live smoke on I9 per C6.
- [ ] DELIVERING: Promotions, feature-doc amendment, delivery report.

## Deviation from conventions

No new `pre-encode-pipeline-parallel.feature.md` file. This is a pure internal optimization to an existing feature (`audio-normalization.feature.md` owns the pipeline); a new feature doc would be spec-duplication. Change lands as a new criterion in the existing feature doc at DELIVERING (per doc-layering rule -- promotions move durable content out of the transient directive).
