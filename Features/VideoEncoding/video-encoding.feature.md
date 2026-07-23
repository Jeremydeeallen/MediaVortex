# Video Encoding -- video compliance (profile-independent baseline)

**Slug:** video-encoding

## What It Does

Answers one question per MediaFile: is the video stream at library baseline (codec in the allowed list; bpp under the transcode threshold)? Writes `(VideoCompliant, VideoCompliantReason)`. One of three per-domain compliance verticals (Audio / Video / Container). Profile-independent: consumer never reads `AssignedProfile` or any Profile row.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | Operator edits acceptable codecs / BppTranscodeThreshold | `/Admin/Compliance` Video Rules tab | `PUT /api/VideoEncoding/Rules` | `VideoEncodingController.UpdateRules` (updates row + backfills every MediaFileId via `VideoVertical().RecomputeFor`) |
| W2 | Probe completion triggers Video recompute | scanner post-probe | per-file `RecomputeFor` | `VideoVertical.RecomputeFor([Id])` |
| W3 | Admin bulk recompute | CLI | -- | `VideoVertical.RecomputeFor(all_ids)` |

## Success Criteria

C1. `VideoVertical.RecomputeFor(MediaFileIds)` writes `(VideoCompliant, VideoCompliantReason)` for each id.
C2. `VideoVertical.Evaluate` reads exactly one knob from `VideoComplianceRules`: `AcceptableVideoCodecsCsv`. Codec check rejects when source codec is NOT in the allowed CSV. The `BppTranscodeThreshold` and `MinSizeMbPerMinuteToTranscode` columns are retired -- still present in the schema pending cleanup, no longer read.
C3. **Efficient-source rule (DOMAIN.md 2026-07-23):** when the source's `VideoBitrateKbps` is at or below the file's assigned profile's `TargetKbps` for the file's `ResolutionCategory` (looked up in `ProfileThresholds`, joined by `Profiles.ProfileName`), `Evaluate` returns `(True, 'source_at_or_below_target:<src><=<target>')`. When the source is above the target, returns `(False, 'source_above_target:<src>><target>')`. When any of AssignedProfile / ResolutionCategory / VideoBitrateKbps is missing, the check is skipped and evaluation falls through to `(True, None)`. `ContentClass` defaults to `'live_action'` when the MediaFile does not carry the attribute. This rule REPLACES the retired bpp gate and the retired efficient-size-override total-bitrate proxy; both are gone from the code.
C4. `VideoComplianceRules` read fresh per `Evaluate` call (`db-is-authority` -- no `__init__` cache).
C5. Fail-loud: missing rules row -> `RuntimeError`; missing MediaFileId -> `ValueError`; no try/except.
C6. **MediaVortex outputs are compliance-exempt on the video side.** When `MediaFiles.TranscodedByMediaVortex = TRUE`, `Evaluate` returns `(True, 'mediavortex_output_accepted')` before any other rule fires. Domain rule: an MV-produced file's original source has been deleted; re-transcoding compressed AV1 through any profile produces generation-loss. `AudioVertical` and `ContainerVertical` still run so audio-only or container-only issues on MV outputs route through `AudioFix` / `Remux` normally.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `RecomputeFor` -> `MediaFiles.VideoCompliant` | `VideoVertical._WriteResult` | `(VideoCompliant: bool/NULL, VideoCompliantReason: text/NULL)` | Generated column `WorkBucket` reflects the flag on next SELECT | Post-RecomputeFor SELECT |
| S2 | `VideoComplianceRules` -> vertical | DB UPDATE via UI / direct SQL | `AcceptableVideoCodecsCsv` (only read column post-2026-07-23) | `_LoadRules` parses per call | UPDATE then observe change |
| S3 | `Profiles` + `ProfileThresholds` -> vertical | ContentClassifier populates `MediaFiles.AssignedProfile`; operator edits `ProfileThresholds.TargetKbps` via `/Admin/Profiles` | `_TargetKbpsFor(ProfileName, ResolutionCategory, ContentClass)` returns `TargetKbps` | `Evaluate` compares `VideoBitrateKbps` against target for efficient-source verdict | `TestVideoComplianceBar` cases covering source-at-or-below-target and source-above-target |

## Cross-Vertical Contract

### Columns the VideoEncoding vertical WRITES

| Column | Written by |
|---|---|
| `MediaFiles.VideoCompliant` | `VideoVertical._WriteResult` |
| `MediaFiles.VideoCompliantReason` | `VideoVertical._WriteResult` |
| `VideoComplianceRules.*` | operator via `/Admin/Compliance` Video Rules tab |

### Columns the VideoEncoding vertical READS from external tables

| Column | Read by | Owner |
|---|---|---|
| `MediaFiles.Codec`, `VideoBitrateKbps`, `TranscodedByMediaVortex`, `ResolutionCategory`, `AssignedProfile` | `Evaluate` | MediaProbe vertical + ContentClassifier |
| `Profiles.ProfileName`, `ProfileThresholds.TargetKbps` / `Resolution` / `ContentClass` | `_TargetKbpsFor` | Profiles vertical (operator via `/Admin/Profiles`) |

### Stable function entry points (cross-vertical callers)

| Class.method | External caller(s) |
|---|---|
| `VideoVertical.RecomputeFor(MediaFileIds: List[int]) -> None` | `QueueManagementBusinessService.RecomputeForFiles` (post-probe orchestrator) |
| `VideoVertical.Evaluate(Mf) -> (bool/None, str/None)` | `ComplianceSummaryController.get_compliance_summary`; `RecomputeFor` internally |

### What is EXPLICITLY NOT a contract

- `_PIXEL_COUNTS` map + `_ASSUMED_FPS=24` (future: probe real fps when available)
- The format of `VideoCompliantReason` strings (today: `codec:<name>`, `source_at_or_below_target:<src><=<target>`, `source_above_target:<src>><target>`, `mediavortex_output_accepted`)

## Status

ACTIVE.

## Files

| File | Role |
|---|---|
| `VideoVertical.py` | Baseline compliance evaluator + `RecomputeFor` |
| `__init__.py` | Package marker |
| `VideoEncodingController.py` | HTTP surface for `/api/VideoEncoding/Rules` |
