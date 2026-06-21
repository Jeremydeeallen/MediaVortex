# Video Encoding -- video compliance + BPP-aware admission

**Slug:** video-encoding

## What It Does

Answers one question about each MediaFile: is its video stream compliant under the assigned profile (codec acceptable, resolution not exceeding target, savings meaningful, not an upscale) AND is the source bitrate-density above the MinSourceBpp threshold (already-efficient sources skip transcode). Writes `(VideoCompliant, VideoCompliantReason)`. One of three per-domain compliance verticals (Audio / Video / Container).

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | Operator edits acceptable codecs / thresholds / MinSourceBpp | future `/Compliance` Video tab | (UI in operator-surfaces directive) | direct UPDATE to `VideoComplianceRules` |
| W2 | Probe completion triggers Video recompute | scanner post-probe (after compliance refactor) | per-file `RecomputeFor` | `VideoVertical.RecomputeFor([Id])` |
| W3 | Admin recompute across all files | CLI / future button | -- | `VideoVertical.RecomputeFor(all_ids)` |

## Success Criteria

C1. `VideoVertical.RecomputeFor(MediaFileIds)` writes `(VideoCompliant, VideoCompliantReason)` for each id.
C2. Wraps existing `TranscodeOperation.Apply` for equivalence with current Compliance routing; adds `MinSourceBpp` override on top.
C3. MinSourceBpp override: when wrapped predicate says "needs transcode" but `BPP = (VideoBitrateKbps * 1000) / (Pixels * 24)` is below `MinSourceBpp`, override to `VideoCompliant=TRUE`, reason=`'efficient_bpp_override'`. Pixel counts: 480p:345600, 720p:921600, 1080p:2073600, 2160p:8294400.
C4. `VideoComplianceRules` read fresh per `RecomputeFor` call (`db-is-authority`).
C5. Failure-loudly: missing rules row -> `RuntimeError`; missing MediaFileId -> `ValueError`; no try/except.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `RecomputeFor` -> `MediaFiles.VideoCompliant` | `VideoVertical._WriteResult` | `(VideoCompliant: bool/NULL, VideoCompliantReason: text/NULL)` | future SQL trigger derives `WorkBucket` | Post-RecomputeFor SELECT |
| S2 | `VideoComplianceRules` -> vertical | DB UPDATE via UI / direct SQL | row shape (codecs, threshold, flags, MinSourceBpp) | `_LoadRules` parses per call | UPDATE then observe change |
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
| `MediaFiles.Codec`, `VideoBitrateKbps`, `ResolutionCategory`, `SizeMB`, `DurationMinutes`, `TranscodedByMediaVortex` | `_EvaluateOne` + `_IsAlreadyEfficient` | MediaProbe vertical |
| `MediaFiles.AssignedProfile` | `EffectiveProfileResolver.Resolve` | Profiles vertical |
| `Profiles`, `ProfileThresholds`, `CrfBitrateEstimates` | `EffectiveProfileResolver` | Profiles vertical |

### Stable function entry points (cross-vertical callers)

| Class.method | External caller(s) |
|---|---|
| `VideoVertical.RecomputeFor(MediaFileIds: List[int]) -> None` | future scanner post-probe orchestrator; future admin recompute |

### What is EXPLICITLY NOT a contract

- The wrap of `TranscodeOperation` (dies at directive 7; will be inlined)
- The wrap of `EffectiveProfileResolver` (moves to Profiles vertical in a follow-up directive)
- `_PIXEL_COUNTS` map + `_ASSUMED_FPS=24` (future: probe real fps when available)
- The format of `VideoCompliantReason` strings (today: `<RuleName>:<Actual>`, `efficient_bpp_override`, `no_effective_profile`; future tunable)

## Known Gap to Target

- BPP override uses 24fps assumption. Real probe of fps would improve accuracy. Filed for future enhancement.

## Status

ACTIVE. Created 2026-06-20 in directive `video-vertical-and-bpp` (Phase 4 of paused `vertical-owned-compliance`).

## Files

| File | Role |
|---|---|
| `VideoVertical.py` | Compliance computation: wrap + MinSourceBpp override |
| `__init__.py` | Package marker |
