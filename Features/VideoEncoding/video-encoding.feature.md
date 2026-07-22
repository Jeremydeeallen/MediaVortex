# Video Encoding -- video compliance + BPP-aware admission

**Slug:** video-encoding

## What It Does

Answers one question about each MediaFile: is its video stream compliant under the assigned profile (codec acceptable, resolution not exceeding target, savings meaningful, not an upscale) AND is the source bitrate-density at or below `BppTranscodeThreshold` (wasteful sources flagged for transcode). Writes `(VideoCompliant, VideoCompliantReason)`. One of three per-domain compliance verticals (Audio / Video / Container).

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | Operator edits acceptable codecs / thresholds / BppTranscodeThreshold | `/Admin/Compliance` Video Rules tab + `/Compliance` Video tab | `PUT /api/VideoEncoding/Rules` | `VideoEncodingController.UpdateRules` (updates row + spawns daemon-thread backfill of every MediaFileId via `VideoVertical().RecomputeFor`) |
| W2 | Probe completion triggers Video recompute | scanner post-probe (after compliance refactor) | per-file `RecomputeFor` | `VideoVertical.RecomputeFor([Id])` |
| W3 | Admin recompute across all files (no rule edit) | CLI fallback | -- | `VideoVertical.RecomputeFor(all_ids)` |

## Success Criteria

C1. `VideoVertical.RecomputeFor(MediaFileIds)` writes `(VideoCompliant, VideoCompliantReason)` for each id.
C2. `VideoVertical.Evaluate` is fully data-driven from `VideoComplianceRules` for the codec + BPP checks. Profile is consulted only for the resolution-tier check (when `ResolutionExceedsProfileTarget=TRUE`) and the absolute bitrate ceiling (`Profile.TargetVideoKbps`, often None). Codec check rejects when source codec is NOT in `AcceptableVideoCodecsCsv`; never compares against the profile's target codec.
C3. Single-threshold BPP rule with `BPP = (VideoBitrateKbps * 1000) / (Width * Height * FrameRate)`, using each MediaFile's actual `Resolution` (parsed as `<Width>x<Height>`) and `FrameRate` (clamped to `[1, 120]` to skip ffprobe-corrupted values). When `BPP > BppTranscodeThreshold`, return `(False, 'high_bpp_excessive:<bpp>><threshold>')` -- wastefully encoded, transcode to AV1 saves real space. There is no second threshold and no "efficient source" early-exit: the downstream `EstimatedSavingsMBThreshold` already skips transcodes whose predicted savings are below operator-defined minimum. Default `BppTranscodeThreshold=0.05` (controller validates > 0).
C4. `VideoComplianceRules` read fresh per `Evaluate` call (`db-is-authority` -- no `__init__` cache).
C5. Failure-loudly: missing rules row -> `RuntimeError`; missing MediaFileId -> `ValueError`; no try/except.
C6. **MediaVortex outputs are compliance-exempt on the video side.** When `MediaFiles.TranscodedByMediaVortex = TRUE`, `VideoVertical.Evaluate` returns `(True, 'mediavortex_output_accepted')` before any other rule fires (codec allowlist, bpp threshold, resolution ceiling, bitrate ceiling all skipped). Domain rule: an MV-produced `-mv.mp4` file's original source has been deleted; the current file IS the intended output. Re-transcoding compressed AV1 through any profile produces generation-loss without quality recovery -- cannot recover pixel information already quantized away. If operator wants better quality on already-transcoded shows, the correct path is Sonarr re-download + first-time transcode from that fresh source. `AudioVertical` and `ContainerVertical` still run so audio-only or container-only issues on MV outputs route through `AudioFix` / `Remux` normally.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `RecomputeFor` -> `MediaFiles.VideoCompliant` | `VideoVertical._WriteResult` | `(VideoCompliant: bool/NULL, VideoCompliantReason: text/NULL)` | future SQL trigger derives `WorkBucket` | Post-RecomputeFor SELECT |
| S2 | `VideoComplianceRules` -> vertical | DB UPDATE via UI / direct SQL | row shape (codecs, EstimatedSavingsMBThreshold, flags, BppTranscodeThreshold) | `_LoadRules` parses per call | UPDATE then observe change |
| S3 | Compliance wrap (temporary; dies at directive 7) | `Features/Compliance/Operations/TranscodeOperation.Apply` | `OperationResult(Applies: bool, Reasons: list)` | `_EvaluateOne` consumes Applies + extracts first apply reason | `TestComplianceEngine.TestOperations` |
| S4 | EffectiveProfileResolver wrap (temporary; dies when Profiles vertical absorbs it) | `Features/Compliance/Services/EffectiveProfileResolver.Resolve(Mf)` | `EffectiveProfile` instance | `_EvaluateOne` passes to `TranscodeOperation.Apply` | Same |

## Cross-Vertical Contract

### Columns the VideoEncoding vertical WRITES

| Column | Written by |
|---|---|
| `MediaFiles.VideoCompliant` | `VideoVertical._WriteResult` |
| `MediaFiles.VideoCompliantReason` | `VideoVertical._WriteResult` |
| `VideoComplianceRules.*` | operator via future `/Compliance` Video tab |

### Columns the VideoEncoding vertical READS from external tables

| Column | Read by | Owner |
|---|---|---|
| `MediaFiles.Codec`, `VideoBitrateKbps`, `Resolution`, `ResolutionCategory`, `FrameRate`, `SizeMB`, `DurationMinutes`, `TranscodedByMediaVortex` | `_EvaluateOne` + `_IsAlreadyEfficient` | MediaProbe vertical |
| `MediaFiles.AssignedProfile` | `EffectiveProfileResolver.Resolve` | Profiles vertical |
| `Profiles`, `ProfileThresholds`, `CrfBitrateEstimates` | `EffectiveProfileResolver` | Profiles vertical |

### Stable function entry points (cross-vertical callers)

| Class.method | External caller(s) |
|---|---|
| `VideoVertical.RecomputeFor(MediaFileIds: List[int]) -> None` | future scanner post-probe orchestrator; future admin recompute |

### What is EXPLICITLY NOT a contract

- The wrap of `TranscodeOperation` (dies at directive 7; will be inlined)
- `_PIXEL_COUNTS` map + `_ASSUMED_FPS=24` (future: probe real fps when available)
- The format of `VideoCompliantReason` strings (today: `<RuleName>:<Actual>`, `efficient_bpp_override`; future tunable)

## Known Gap to Target

- BPP override uses 24fps assumption. Real probe of fps would improve accuracy. Filed for future enhancement.

## Status

ACTIVE. Created 2026-06-20 in directive `video-vertical-and-bpp` (Phase 4 of paused `vertical-owned-compliance`).

## Files

| File | Role |
|---|---|
| `VideoVertical.py` | Compliance computation: wrap + MinSourceBpp override |
| `__init__.py` | Package marker |
