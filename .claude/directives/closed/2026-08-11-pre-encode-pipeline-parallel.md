# Directive: pre-encode-pipeline-parallel

**Status:** Closed

**Slug:** pre-encode-pipeline-parallel

**Interrupts:** probe-loudness-remove (top of `.claude/current-feature` stack)

### Promotions

- Directive scope (parallel-shape pipeline) → `Features/AudioNormalization/audio-normalization.feature.md` new C42 documenting the concurrent orchestration + invariants (post-close amendment; see delivery report).
- Contract test `Tests/Contract/TestPreEncodePipelineParallel.py` (NEW, 5/5 pass) is durable evidence for the concurrent orchestration invariant.

### Delivery Report

- DIRECTIVE: parallelize `SourceMeasure` with `Downmix → Demucs → Premix → LoudnormMeasure` in `PreEncodeAudioPipeline.Run` to reduce per-Dialog-Boost-job wall time.
- STATUS: Done. Correctness preserved. Perf improvement smaller than initial estimate (~53s/job actual vs 90s C6 threshold; shipping anyway per operator decision -- real 50s/job accumulates across the fleet).
- WHAT SHIPPED:
  - `Features/AudioNormalization/Services/PreEncodeAudioPipeline.py` refactored. `Run` spawns a named daemon thread `PreEncodeSourceMeasure-<JobId>` for `_RunSourceMeasureTask`; the caller thread runs `_RunDemucsChain` (Downmix → Demucs → Premix → LoudnormMeasure). Both threads join before Run returns; exceptions in either propagate through the outer try/except and surface as `DemucsFailed` dict per audio-normalization.C39.
  - `_ThreadResult` box class holds (value, exception) for cross-thread result handoff. No shared mutable state beyond the box.
  - `Tests/Contract/TestPreEncodePipelineParallel.py` (NEW, 5/5 pass): success-path field propagation, thread-naming assertion, wall-time proof (0.3s + 0.3s serial → <0.55s parallel), and exception propagation for both failure modes.
- HOW TO USE IT: no operator action. Runs by default on every Dialog Boost job. Progress rows continue to advance in `TranscodeProgress` per C34 (per-thread `_Report` writes different `PassType` values so no PK collision).
- WHAT YOU NEED TO EXECUTE: fleet-wide deploy (`py deploy/deploy-fleet.py`) to propagate the change to non-I9 workers. Not urgent -- I9 has it, remote workers get the same speedup on next deploy.
- CRITERIA VERIFICATION:
  - C1 byte-identical loudnorm params: covered by the fact that both threads call the same `DemucsService.MeasureSourceLoudnorm` / `MeasurePremixLoudnorm` methods with identical arguments as the sequential predecessor; orchestration is a threading wrapper only, not a math change. Contract test asserts field propagation from mocked subprocess results.
  - C2 wall reduction >=90s: **failed** on the observed sample. Measured 53s reduction on 66-min episodes (66-min baseline median 302s → parallel median 249s). Retained the change per operator decision; the win is real but half of the initial estimate. Root cause: Demucs daemon was already warm on the fast-group comparison sample, so the chain was ~155s not ~90s -- SourceMeasure (~90s) parallelized with a chain that dominates, leaving ~90s savings on the table which was further eaten by CPU contention (~40s) when two ffmpeg subprocesses run concurrent.
  - C3 progress rows advance: verified in live-smoke log for attempt 59900 (18:09:09 SourceMeasure(0%) + Downmix(0%) interleaved through 18:11:47 LoudnormMeasure(100%); no gap > 3s).
  - C4 failure propagation: covered by two contract tests (`test_source_measure_exception_propagates_after_chain_join`, `test_chain_exception_waits_for_source_measure_before_raising`); peer-kill dropped per revised design (KISS).
  - C5 feature doc amendment: done as Promotions row 1 (see below post-close).
  - C6 live smoke on I9: run pair (59900, 59905) completed on Version 156dccaf. Wall 250s / 248s. Baseline 302s. Reduction 53s. **Below the 90s ship-gate but shipping per operator call.**
- DECISIONS I MADE:
  - Contract-test approach: mocked `DemucsService` methods to prove orchestration handoff without depending on real loudnorm subprocess. No golden-fixture baseline needed for C1 because the code path invokes identical service methods with identical arguments -- correctness is preserved by construction.
  - Peer-kill on failure: dropped from C4 (KISS). Rare failure case wastes ~30s of peer work vs the plumbing cost of subprocess handle propagation.
  - Deviation from convention: no new `pre-encode-pipeline-parallel.feature.md`. Rationale in directive body.
- KNOWN GAPS / DEFERRED:
  - No post-restart slow-group Dialog Boost sample yet (baseline attempt 59758 was 648s wall / 253s ffmpeg dual-track full loudnorm). Slow-group parallel savings may be larger than fast-group's 53s. Not blocking close; monitor over next 24h.
  - Filter-graph fold + streamed loudnorm-measure → encode remain deferred (OOS a/b of this directive). Ship this directive first, revisit if operator wants more.

### NOTE on measured perf vs estimated perf

Original directive scoped `~2-3min saved per job`. Real save on the 2-sample post-restart smoke was 53s. Delta reasons:
- The sequential predecessor was NOT as slow on fast-group as the extreme-baseline 59758 suggested. That attempt was an outlier (dual-track full loudnorm on a specific source). Median fast-group pre-restart baseline was ~302s wall (not 648s).
- Demucs daemon warmth (`C40`) already amortized the biggest cost. Parallelization saves LESS when the chain is already fast.
- CPU contention when two ffmpeg subprocesses run concurrent ate ~40s of theoretical savings.

The scope-vs-actual gap is a lesson worth recording: use median baseline, not extreme, for wall-time estimates on parallelization work.
