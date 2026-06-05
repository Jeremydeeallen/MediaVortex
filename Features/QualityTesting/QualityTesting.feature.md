# Quality Testing

**Slug:** qualitytesting

## What It Does

Runs VMAF quality analysis comparing transcoded files against originals. Scores determine whether a transcode is acceptable (>= 80) or needs re-encoding with adjusted CRF.

## Success Criteria

1. After a transcode completes, the output file is automatically queued for VMAF quality testing (when QualityTestEnabled is on).
2. VMAF scoring compares the transcoded file against the original and produces a numeric score (0-100).

2b. **[BUG - PARTIAL FIX 2026-05-16]** VMAF distribution is bimodal on **held-frame content** -- any source where consecutive frames are byte-identical for an extended fraction of the runtime. Production pipelines that produce held frames: anime and 2D animation animated-on-2s/3s with no compositing noise, older CGI without per-frame jitter, reality-TV photo montages and "previously on" cards, sitcoms shot multicam with static stage framing, dramas with title-card / chapter-card interludes, stop-motion, slideshow documentaries, lecture / conference recordings, telecined content. **Counter-intuitively, modern CGI does NOT trigger** when its render pipeline applies per-frame motion blur or sub-pixel dither -- byte-identity breaks even when a drawing is conceptually held. Live action with continuous camera motion is unaffected. The cause is NOT the container (verified: same encoded bytes against a remuxed MP4 source give identical bimodal numbers). The cause is libvmaf's `integer_motion` elementary feature collapsing on duplicate consecutive source frames -- VMAF model 0.6.1 was trained on continuous-motion live action and produces near-zero VMAF on motion=0 frames even when the encoded picture is visually identical to the source (verified: PNG stills at the VMAF=0 frames are indistinguishable). Cross-tab on Minnie's: 41.3% of source frames are motion=0; 71% of bad-VMAF frames are in that population. Production-DB evidence (2026-05-16) across past attempts:

    | Show | Type | Mean | P5 | StdDev | Pattern |
    |---|---|---|---|---|---|
    | Pokémon S20E10 | Hand-drawn anime | 71.5 | 0.0 | 35.1 | Severe bimodal |
    | Real Housewives S03E22 | Live-action reality | 76.6 | 9.2 | 29.8 | Bimodal |
    | Steven Universe S05E14 | 2D Western animation | 76.8 | 18.9 | 22.7 | Bimodal |
    | Bunk'd S02E11 | Live-action sitcom | 78.3 | 22.7 | 24.7 | Bimodal-ish |
    | The Bear S03E10 | Live-action drama | 79.4 | 10.8 | 27.8 | Bimodal |
    | **The Garfield Show S01E19** | **Modern CGI** | **97.7** | **95.7** | **1.5** | **Clean** |
    | Outlander | Live action | 96.7 | -- | 2.0 | Clean |

    Investigation summary + full mitigation matrix in `memory/KNOWN-ISSUES.md`. Fix shipped 2026-05-16: `ParseVMAFMetrics` and the smoke harness `ParseMetricsFromXml` now detect held-frame content (MotionZeroFraction > 0.15) and pool Mean/StdDev/HarmonicMean/percentiles over only the motion>=0.5 frames; continuous-motion content is unaffected (the filter is a no-op for it). Verifiable: run `py Scripts/Smoke/EncodeAndVmaf.py --vmaf-only Scripts/Smoke/MinnieBowToons-S04E07-Animation8Mbps.results.json`; observe Mean lifts from raw 74.60 to filtered 84.43, P5 from 0.00 to 12.08, StdDev from 32.58 to 26.75, with `MotionFilterApplied=True` and `MotionZeroFraction=0.413` in the metrics dict. Residual limitation: filtered Mean=84 is still below `VmafAutoReplaceMinThreshold=88`, so the auto-replace gate will still Requeue this attempt today even though the encode is visually clean and filtered P25=94. Threshold tuning for held-frame content (gating on filtered P25, or a content-aware threshold) is a separate operator-policy decision tracked outside this criterion.
3. Files with VMAF >= 80 pass quality testing and are eligible for file replacement.
4. Files with VMAF < 80 trigger CRF adjustment for the next transcode attempt.
5. Quality test results are recorded in TranscodeAttempts with the VMAF score.
6. Quality testing runs as a capability within WorkerService (QualityTestEnabled flag). Workers with this capability enabled poll for queued quality tests.
7. Quality test progress (current file, percentage) is reported in real time.

7b. **[BUG 2026-05-10]** `MonitorVMAFProgress` stops emitting progress updates roughly 25% before FFmpeg actually completes the run. On attempt 4396 (Steven Universe S05E14, 16,080 frames), the last progress log line was at frame 12,000 (74.6%) -- the remaining 4,080 frames (about 25 seconds of wall time at 6.88x realtime) produced zero progress events while FFmpeg silently churned through the tail and exited with code 0. `QualityTestProgress.Status` never advances to `Completed`, `ProgressPercentage` never reaches 99-100. Same monitor failure explains why `QualityTestProgress` rows stay at `Status='Processing'` (or `'Started'` with the pre-`RETURNING Id` worker code) indefinitely after the FFmpeg process actually finishes. Verifiable: for any completed run, `QualityTestProgress.ProgressPercentage` should be >= 99 and `Status` should be `Completed`. Today neither is true on the row backed by `MonitorVMAFProgress`. Look first: `Features/QualityTesting/QualityTestingBusinessService.py:722` (`MonitorVMAFProgress`) and `ParseFFmpegProgressLine` around line 803 -- likely an early-EOF interpretation of the FFmpeg stderr read loop, or a timeout on the pipe poll that fires before FFmpeg's final buffer flush. Cosmetic only (XML/score data integrity confirmed by directly inspecting `vmaf_output.xml` after the run -- 1,609 frame elements covering frames 0-16080, parsed mean matches stored VMAFScore exactly). Fix with `/t`.
8. Quality testing can be paused, resumed, or gracefully stopped (finish current test then stop).
9. SystemSettings.QualityTestEnabled controls whether quality testing runs globally (default OFF). Workers.QualityTestEnabled provides per-worker override (NULL = use global).
10. Test result history is viewable with pagination.
11. ShouldQualityTestService.ProcessTranscodedFile() respects QualityTestRequired. When QualityTestRequired=False on the TranscodeAttempt, the bridge skips the quality test queue and goes directly to file replacement.

11c. **[BUG-0022 RESOLVED 2026-05-29]** Both arms shipped.
- **NVENC adoption arm** resolved 2026-05-28. See `Features/Profiles/nvenc-profiles.feature.md`.
- **VMAF measurement arm** resolved 2026-05-29. Three fixes:
  1. **Input order corrected.** Production had `-i original -i transcoded` with `[0:v]->[dist]` and `[1:v]->[ref]` -- libvmaf reads positionally, so it was treating the ORIGINAL as the distorted input and the TRANSCODED as the reference. VMAF is asymmetric; running it backwards produced content-dependent inverted scores. This pre-dated the chain rewrite and is the most likely root cause of historically inconsistent VMAF readings. Fixed by swapping input order: `-i transcoded -i original`. Canary verification: VMAF on a fresh NVENC encode jumped from 67.40 (wrong direction) to a sane score (correct direction).
  2. **Chain aligned to the operator-validated canary** (`Scripts/CodecAnalysis/NvidiaOptimization1.ps1`, source of truth): PTS reset on both inputs, `fps=fps={SourceFps}` on both inputs (kills frame-rate drift between transcoded and reference), scale on the reference branch only (transcoded is already at target resolution), 10-bit precision (`format=yuv420p10le`), libvmaf with `log_fmt=xml` + `n_threads=4`. Updated 2026-05-31 by the nvenc-rate-anchored-remediation directive to match the canary chain that produced VMAF 92.924652 on the operator's reference source.
  3. **`n_subsample=10` removed.** Prior chain scored only every 10th frame, which made the held-frame motion-filter unreliable (integer_motion between non-consecutive frames is meaningless) and lost tail-of-distribution detail the percentile metrics depend on.
- Motion-filter threshold recalibration (the loose `integer_motion < 0.5` cutoff fires on plain low-motion content like talking-head sitcoms, not just held-frame animation) deferred to a separate small task -- needs per-frame XML data captured under the new chain to drive calibration. Not gating production behavior because the input-order and chain fixes already address the user-reported "wildly inconsistent" symptom independently.

**Historical VMAF scores stored in `TranscodeAttempts.VMAF` from before 2026-05-29 are inverted-direction measurements** and should not be trusted as absolute quality scores. They remain valid for relative comparisons within the same content/profile pair (the inversion is systematic, not random) but the absolute number is not what libvmaf normally reports. New scores after 2026-05-29 are correct-direction.

11b. **[BUG 2026-05-12]** Terminology inconsistency: "quality test" (what -- the policy/concept of validating an encode) and "VMAF" (how -- one specific metric implementation) are used interchangeably across the codebase, DB columns, settings keys, log messages, UI labels, and class names (e.g. `QualityTestEnabled` vs `VMAFAutoReplaceMinThreshold`, `QualityTestProgress` vs `MonitorVMAFProgress`, `QualityTestingBusinessService.BuildVMAFCommand`). The concepts are not synonymous: VMAF is one possible quality-test implementation; a future SSIMU2/PSNR/visual-comparison path would be a quality test that is not VMAF. The mixing makes search, refactoring, and operator messaging harder, and bakes the current metric choice into surfaces that should be metric-agnostic. Verifiable when fixed: a documented glossary in `Features/QualityTesting/QualityTesting.feature.md` defining "quality test" (the policy/decision -- accept/requeue/discard) vs "VMAF" (one specific scoring metric), and every identifier in code / DB / UI uses the term that matches the layer it lives at (policy-layer surfaces never name a specific metric; metric-layer surfaces never claim to be "the quality test"). Look first: `Features/QualityTesting/QualityTestingBusinessService.py`, `Repositories/DatabaseManager.py` (column names), `Templates/*.html` (button labels), `Core/Logging` (log strings). Fix with `/t`.

## Status

COMPLETE

## Scope

```
Features/QualityTesting/**
WorkerService/**
```

## Files

| File | Role |
|------|------|
| Features/QualityTesting/QualityTestController.py | Flask Blueprint -- quality test endpoints |
| Features/QualityTesting/QualityTestingBusinessService.py | VMAF execution, scoring logic; `BuildVMAFCommand` reads typed pair from TemporaryFilePaths via `Path.FromRow(R, Prefix='Source'/'Output')` and resolves to worker-native via `Path.Resolve(Worker)` per `path.S5`; existence checks via `PathFs.Exists(P, Worker)` per `path.S10`. |
| Features/QualityTesting/QualityTestRepository.py | Quality test queue + results queries; `_SafeCanonical(Sid, Rel)` synthesizes display via `Path.CanonicalDisplay(GetPrefixMap())` per `path.S8`. |
| Features/QualityTesting/PostTranscodeDispositionService.py | Single decision function; called both immediately after transcode (returns `Pending`/`AwaitingVmaf` to dispatch VMAF) and after VMAF score lands (returns `Replace`/`NoReplace`/`Requeue`). See `post-transcode-disposition.feature.md`. |
| Features/QualityTesting/ProcessQualityTestQueueService.py | Worker-side claim loop; calls `DatabaseManager.ClaimQualityTestJob` (typed-pair-aware, capability-gated) and dispatches to `QualityTestingBusinessService.ProcessClaimedJob`. |
| WorkerService/Main.py | Unified worker entry point (runs quality testing when QualityTestEnabled=TRUE). |

## VMAF claim-to-completion chain (path-class anchors)

Restored 2026-06-05 by `vmaf-restoration` directive after the path-perfect-implementation cutover removed `Path.Exists` / `Path.IsFile` / `Path.IsDir` / `Path.GetSize` / `Path.GetMTime` instance methods (Step 7) -- callers now use `Core.Path.PathFs.<Op>(P, Worker)`. Two failure modes blocked the chain pre-restoration: (1) `# allow: R12 -- preexisting` Python comment annotations baked inside triple-quoted SQL strings caused `psycopg2.errors.SyntaxError: syntax error at or near "#"` at `CreateProgressRecord`, `UpdateProgressRecord`, and 19 other SQL sites across `QualityTestingBusinessService` + `ProcessTranscodeQueueService` (the `#` is not a SQL comment; only `--` and `/* */` are); (2) the Step-7 removal of `Path.Exists` instance methods left `SourcePath.Exists(Wk)` / `OutputPath.Exists(Wk)` calls in `BuildVMAFCommand` raising `AttributeError`. Both fixed in commit `86a0c0b`.

| Step | Code site | Path-class operation |
|---|---|---|
| Claim | `Repositories/DatabaseManager.ClaimQualityTestJob` | Atomic UPDATE on `QualityTestingQueue` gated by `Workers.QualityTestEnabled=TRUE AND Status='Online'` via `WorkerCapabilityPredicate.BuildClaimPredicate`. |
| Worker resolution | `QualityTestingBusinessService._GetWorker` -> `Core.Path.Worker.FromWorkerContext` | Per-instance `Worker` reads `StorageRootResolutions` via `Worker.ResolveStorageRoot` (`path.S11`). |
| TFP read | `BuildVMAFCommand:224-228` | SELECTs `SourceStorageRootId, SourceRelativePath, OutputStorageRootId, OutputRelativePath` typed-pair only. |
| Path construction | `Path.FromRow(R, Prefix='Source')` + `Path.FromRow(R, Prefix='Output')` | `path.S1`. |
| Worker-native string | `SourcePath.Resolve(Wk)` -> `original_file` / `OutputPath.Resolve(Wk)` -> `transcoded_file` | `path.S5` -- POSIX on Linux, Windows on i9. |
| Existence check | `PathFs.Exists(SourcePath, Wk)` + `PathFs.Exists(OutputPath, Wk)` | `path.S10` -- delegates to `LocalExists(P.Resolve(W))`. |
| ffmpeg invocation | `command = [ffmpeg_binary, '-i', transcoded_file, '-i', original_file, '-lavfi', vmaf_filter, '-f', 'null', '-']` | Worker-native strings, no separator normalization. |
| Score parse + DB write | `ParseVMAFMetrics` + `UpdateQualityTestResultsWithScore` -> `UPDATE TranscodeAttempts SET VMAF=%s, QualityTestCompleted=TRUE` + `INSERT INTO QualityTestResults` | Typed pair untouched. |
| Re-decide | `PostTranscodeDispositionService.Decide` re-called after score lands | Closed-vocabulary reason; persists to `TranscodeAttempts.Disposition/DispositionReason/DispositionDecidedAt`. |
| Lifecycle close | `QualityTestingQueue` row removed via `DeleteQualityTestQueueItem` in `StartQualityTest`'s `finally` (revolving-door pattern; see `Features/QualityTesting/qt-queue-visibility-and-override.feature.md` for the surface that makes queue history visible). | Worker-side. |

Verified end-to-end 2026-06-05: i9 NVENC transcode 29484 -> dot-worker-1 claim 1405 -> VMAF=96.25 -> `Disposition=NoReplace/VmafAboveMax`. Parallel: larry-worker-2 claim 1408 + dot-worker-1 claim 1409 processed concurrently. All paths POSIX on Linux workers; identity typed pair throughout.
