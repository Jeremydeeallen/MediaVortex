# Encoder Shootout Harness

**Slug:** encodershootout

## What It Does

Runs a deterministic, repeatable encoder-vs-encoder comparison: one or more SVT-AV1 reference variants against one or more NVENC variants, on a fixed source set, with VMAF measured under the production-grade chain (motion-filter pooling, 10-bit precision, PTS-aligned, color-range-pinned). Emits per-source and rollup tables plus a JSON sidecar.

The harness exists to answer BUG-0022's operational question:
> Can NVENC av1_nvenc produce closish quality at sameish size as the production SVT-AV1 path, fast enough that the speed wins justify the quality/size losses?

It does NOT probe sources at run time. Every parameter that affects encode output (resolution, FPS, CQ/CRF, preset, film grain, tune, multipass) is declared in the matrix JSON. The same matrix file replayed produces the same numbers.

## Scope

```
Scripts/Smoke/EncoderShootout.py
Scripts/Smoke/NvencKnobSweep.matrix.json
Scripts/Smoke/EncoderShootout.feature.md
```

Outputs land in `Scripts/Smoke/shootout_output/` (encoded mp4s, transient) and `Scripts/Smoke/<test_name>.shootout.json` (results sidecar, durable).

## Success Criteria

1. The harness reads a matrix JSON declaring `sources[]` (each with path, label, content_type, fps, source_height, source_codec) and `variants[]` (each with encoder, encoder-specific params, output_scale), and runs every (source, variant) pair without probing any source file at run time.
2. SVT-AV1 variants are encoded with `libsvtav1`, preset/crf/film_grain from the variant declaration, `-pix_fmt yuv420p10le`.
3. NVENC variants are encoded with `av1_nvenc`, preset/tune/multipass/cq from the variant declaration, `-rc vbr -cq N -b:v 0` for quality-anchored VBR, `-pix_fmt p010le`, with `-spatial-aq 1 -temporal-aq 1 -rc-lookahead 20 -bf 4 -b_ref_mode middle`.
4. Audio for all variants is `-c:a aac -b:a 96k -ac 2` (deterministic, MP4-safe, irrelevant to VMAF — no per-source loudnorm measurements that would make results non-comparable).
5. VMAF runs through the production-equivalent chain: both inputs `setpts=PTS-STARTPTS`, scaled to the output resolution with lanczos and explicit `in_range=auto:out_range=tv` color-range pinning, `format=yuv420p10le` precision match, libvmaf with `log_fmt=xml`, `n_threads=4`.
6. VMAF metrics are pooled via the motion-filter rule ported from `Features/QualityTesting/QualityTestingBusinessService.ParseVMAFMetrics`: when more than 15% of source frames have integer_motion < 0.5, Mean / StdDev / percentiles are computed over only the motion>=0.5 frames. `MotionFilterApplied` and `MotionZeroFraction` are reported per result.
7. Per-source table shows: variant label, encode wall time, output size MB, output bitrate kbps, VMAF Mean, HarmonicMean, StdDev, P5, P10, P25, MotionFilterApplied.
8. Cross-source rollup shows per-variant medians of size, encode time, VMAF Mean / P5 so the operator can read the headline gap at a glance.
9. Sidecar JSON contains the full matrix, every (source, variant) result, the parsed VMAF metrics dict, and run timestamps. Sufficient to reproduce the analysis without re-running.
10. Encoded mp4 outputs are deleted after VMAF unless `--keep-encoded` is passed. Source files are never modified.

## Status

COMPLETE 2026-05-28. Used for the NVENC vs SVT-AV1 production rollout decision (BUG-0022 NVENC arm). Winning variant `nv_cq32_sink` shipped as production Profiles in `Features/Profiles/nvenc-profiles.feature.md`.

Harness remains in the tree for future encoder evaluations -- matrix JSON is the only thing that changes per test.

### Result sidecars
- `Scripts/Smoke/NvencKnobSweep-1080pTo480p-2026-05-28.shootout.json` -- the production-decision-grade rollup (4 sources x 8 variants, no failures).
- Partial sidecars from killed/restarted runs were cleaned up after the decision landed.

### Original READY-TO-RUN block (preserved for reference)

### Run command
```
py Scripts/Smoke/EncoderShootout.py --matrix Scripts/Smoke/NvencKnobSweep.matrix.json
```

### Expected runtime
~3-4 hours wall clock for the shipped 6-source × 4-variant matrix (24 encodes total). Dominated by SVT-AV1 preset 6 encode time; NVENC encodes complete in 3-5 min each.

### What the operator does after the run
1. Read the Cross-Source Rollup table in stdout (also persisted in the sidecar).
2. For each NVENC CQ rung, compare median size and median VMAF Mean against the SVT-AV1 reference row.
3. Decision rule: NVENC "wins" if any CQ rung achieves median VMAF Mean within 2.0 points of SVT AND median size within 15% of SVT, OR if NVENC is clearly worse but speed savings outweigh the gap (operator judgment).
4. If NVENC competitive: proceed to production rollout via the existing `usenvidiahardware` profile flag (already wired on Profiles table; CommandBuilder integration is a separate piece of work, not this test).
5. If NVENC not competitive: close BUG-0022 with the recorded evidence.

## Surface

CLI script. No web UI, no DB writes. Operator-driven, results visible in stdout + JSON sidecar.

## Files

| File | Role |
|------|------|
| Scripts/Smoke/EncoderShootout.py | Harness entry point |
| Scripts/Smoke/NvencKnobSweep.matrix.json | Test matrix (4 sources x 8 variants -- the production-decision matrix) |
| Scripts/Smoke/EncoderShootout.feature.md | This file |
| Scripts/Smoke/shootout_output/ | Transient encode outputs (auto-deleted) |
| Scripts/Smoke/*.shootout.json | Persisted results sidecar |

## Why this is separate from EncodeAndVmaf.py

`EncodeAndVmaf.py` is SVT-AV1-only by design and emits a sidecar consumed by `/VmafCompare`. Adding encoder dispatch to it would change its contract and could break the Test bench card. The shootout is a different question with a different output schema, so it gets its own script and sidecar suffix (`.shootout.json` vs `.results.json`).
