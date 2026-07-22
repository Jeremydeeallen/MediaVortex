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
C2. `VideoVertical.Evaluate` reads exactly two knobs from `VideoComplianceRules`: `AcceptableVideoCodecsCsv` + `BppTranscodeThreshold`. Codec check rejects when source codec is NOT in the allowed CSV. No profile lookup.
C3. Single-threshold BPP rule with `BPP = (VideoBitrateKbps * 1000) / (Width * Height * FrameRate)`, using each MediaFile's actual `Resolution` (parsed as `<Width>x<Height>`) and `FrameRate` (clamped to `[1, 120]`). When `BPP > BppTranscodeThreshold`, return `(False, 'high_bpp_excessive:<bpp>><threshold>')`. Default `BppTranscodeThreshold=0.05`.
C4. `VideoComplianceRules` read fresh per `Evaluate` call (`db-is-authority` -- no `__init__` cache).
C5. Fail-loud: missing rules row -> `RuntimeError`; missing MediaFileId -> `ValueError`; no try/except.
C6. **MediaVortex outputs are compliance-exempt on the video side.** When `MediaFiles.TranscodedByMediaVortex = TRUE`, `Evaluate` returns `(True, 'mediavortex_output_accepted')` before any other rule fires. Domain rule: an MV-produced file's original source has been deleted; re-transcoding compressed AV1 through any profile produces generation-loss. `AudioVertical` and `ContainerVertical` still run so audio-only or container-only issues on MV outputs route through `AudioFix` / `Remux` normally.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `RecomputeFor` -> `MediaFiles.VideoCompliant` | `VideoVertical._WriteResult` | `(VideoCompliant: bool/NULL, VideoCompliantReason: text/NULL)` | Generated column `WorkBucket` reflects the flag on next SELECT | Post-RecomputeFor SELECT |
| S2 | `VideoComplianceRules` -> vertical | DB UPDATE via UI / direct SQL | `AcceptableVideoCodecsCsv`, `BppTranscodeThreshold` | `_LoadRules` parses per call | UPDATE then observe change |

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
| `MediaFiles.Codec`, `VideoBitrateKbps`, `Resolution`, `FrameRate`, `TranscodedByMediaVortex` | `Evaluate` | MediaProbe vertical |

### Stable function entry points (cross-vertical callers)

| Class.method | External caller(s) |
|---|---|
| `VideoVertical.RecomputeFor(MediaFileIds: List[int]) -> None` | `QueueManagementBusinessService.RecomputeForFiles` (post-probe orchestrator) |
| `VideoVertical.Evaluate(Mf) -> (bool/None, str/None)` | `ComplianceSummaryController.get_compliance_summary`; `RecomputeFor` internally |

### What is EXPLICITLY NOT a contract

- `_PIXEL_COUNTS` map + `_ASSUMED_FPS=24` (future: probe real fps when available)
- The format of `VideoCompliantReason` strings (today: `codec:<name>`, `high_bpp_excessive:<bpp>><threshold>`, `mediavortex_output_accepted`)

## Status

ACTIVE.

## Files

| File | Role |
|---|---|
| `VideoVertical.py` | Baseline compliance evaluator + `RecomputeFor` |
| `__init__.py` | Package marker |
| `VideoEncodingController.py` | HTTP surface for `/api/VideoEncoding/Rules` |
