# Quality Testing

## What It Does

Runs VMAF quality analysis comparing transcoded files against originals. Scores determine whether a transcode is acceptable (>= 80) or needs re-encoding with adjusted CRF.

## Success Criteria

1. After a transcode completes, the output file is automatically queued for VMAF quality testing (when QualityTestEnabled is on).
2. VMAF scoring compares the transcoded file against the original and produces a numeric score (0-100).

2b. **[BUG - CRITICAL 2026-05-10]** VMAF distribution becomes bimodal on MKV-source transcodes, making the produced numeric score not reflect perceptual quality. Empirical: same recipe gives Mean 95.77 / P5 94.30 on a clean 4K MP4 source (unimodal) and Mean 74.60 / P5 0.00 on Minnie's Bow-Toons WEBDL-1080p MKV source (bimodal: 56% of frames score 90+, 7% score near zero). Visual confirmation that the encoder is fine: extracted source-vs-encoded stills at "VMAF=0" frames are visually indistinguishable. Frame desync ruled out (identical frame counts 2181=2181, identical fps 24000/1001). Subsampling ruled out (re-ran without n_subsample, distribution stayed bimodal). Most likely cause: color metadata mismatch (source `color_range=unknown` or 8-bit `yuv420p`; encoded `color_range=tv` 10-bit `yuv420p10le`) confusing libvmaf on dark frames where limited-vs-full range gaps are largest. Verifiable: run `py Scripts/Smoke/EncodeAndVmaf.py --vmaf-only Scripts/Smoke/MinnieBowToons-S04E07-Animation8Mbps.results.json`; observe Mean ~74 / P5 0; extract source and encoded stills at frame 150 (~6.26s) via FFmpeg and confirm visual identity. Until fixed, do NOT use Mean/HMean/P5 from MKV-source attempts for tier-threshold calibration or cross-source comparison; visual slider inspection remains valid. Full discussion + candidate mitigations in `KNOWN-ISSUES.md`. Fix with `/t`.
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
| Features/QualityTesting/QualityTestingController.py | Flask Blueprint -- quality test endpoints |
| Features/QualityTesting/QualityTestingBusinessService.py | VMAF execution, scoring logic |
| Features/QualityTesting/QualityTestingRepository.py | Quality test queue and results queries |
| WorkerService/Main.py | Unified worker entry point (runs quality testing when QualityTestEnabled=TRUE) |
