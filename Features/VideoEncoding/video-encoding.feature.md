# Video Encoding -- video compliance (bitrate-driven multiplier)

**Slug:** video-encoding

## What It Does

Answers one question per MediaFile: is the video stream compliant? Writes `(VideoCompliant, VideoCompliantReason)`. One of three per-domain compliance verticals (Audio / Video / Container). The rule itself lives in `transcode.flow.md` D4. Compact-source classification IS the gate; there is no separate admission-time exclusion.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | Operator edits per-resolution multiplier | `/settings` Transcoding card, Video compliance section | `PUT /api/SystemSettings/Transcoding` (VideoCompliance section) | `SystemSettingsController.UpdateTranscodingSettings` -> `VideoComplianceThresholdsRepository.UpsertAll` |
| W2 | Probe completion triggers Video recompute | scanner post-probe | per-file `RecomputeFor` | `VideoVertical.RecomputeFor([Id])` |
| W3 | Bulk recompute after multiplier retune | CLI: `py Scripts/RecomputeWorkBuckets.py` | -- | `VideoVertical.RecomputeFor(all_ids)` |

## Success Criteria

C1. The video rule is stated once, in `transcode.flow.md` D4 (Video rows). A library with a default tier judges source kbps against the kbps that tier encodes the file's resolution at, times the resolution multiplier; the stored reason names source kbps, ceiling, tier, tier kbps and multiplier (`source_above_ceiling:2086>2000(tier=1:1000*2.0)`). A library with no default tier judges against the file's assigned profile, with a same-codec pass first; its reason names the profile. Verifiable: `Tests/Contract/TestTvVideoRuleTier1.py`, `TestVideoVerticalCodecMatch.py`, `TestVideoComplianceMultiplier.py`.

C2. In a library with a default tier, neither the file's codec nor its assigned profile influences `VideoCompliant`. Verifiable: `SELECT COUNT(*) FROM MediaFiles mf JOIN StorageRoots sr ON sr.Id = mf.StorageRootId WHERE sr.DefaultQualityTier IS NOT NULL AND position('(profile=' in mf.VideoCompliantReason) > 0` returns 0.

C3. `VideoComplianceThresholds(ResolutionCategory UNIQUE, Multiplier NUMERIC(4,2) CHECK>0, LastUpdated)` seeded with `(480p, 1.5), (720p, 2.0), (1080p, 2.0), (2160p, 3.0)`. Every read fresh per `Evaluate` call (`db-is-authority` -- no `__init__` cache).

C4. Operator tunes multipliers via `/settings` GUI. GET `/api/SystemSettings/Transcoding` returns `VideoCompliance: [{ResolutionCategory, Multiplier}, ...]`. PUT persists via `VideoComplianceThresholdsRepository.UpsertAll`. No SQL required. Each library's default tier (`StorageRoots.DefaultQualityTier`, 1-5 or unset) is viewed and saved on the same card via GET/PUT `/api/SystemSettings/LibraryTiers`; a save re-evaluates every file in that library and the new value is read by the next evaluation without restart.

C5. Fail-loud on ALL missing decision inputs. Missing multiplier row for a MediaFile's ResolutionCategory -> `RuntimeError`; missing MediaFileId -> `ValueError`; no try/except. Missing ResolutionCategory / VideoBitrateKbps / AssignedProfile / Family / Tier1TargetKbps -> `(None, 'missing_input:<field>')`. The aggregator routes any file with `None` from any vertical to `WorkBucket=NULL` (Unclassified). This surfaces probe-not-yet-run / probe-column-null files as Unclassified rather than hiding them in Compliant. Reason: silent `(True, None)` on missing inputs caused Heroes S2 files at 12-14 Mbps to land in Remux because AssignedProfile-derived Family lookup returned None -> compliant-by-default.

C6. **MediaVortex-output terminal state enforced at aggregate layer, not per-vertical.** The `TranscodedByMediaVortex=TRUE` short-circuit lives in the WorkBucket GENERATED column CASE (see `work-bucket.feature.md` C7 + `transcode.flow.md` D7). `VideoVertical.Evaluate` NO LONGER short-circuits on this flag; it evaluates the multiplier check for every row. Aggregate layer routes MV outputs to Compliant regardless of any vertical's compliance opinion. Prior text (pre-2026-08-07) said `VideoVertical returns (True, 'mediavortex_output_accepted') before any other rule fires` -- deleted per `mediavortex-output-terminal` directive because the per-vertical patch was redundant + inconsistent (AudioVertical + ContainerVertical did not have the same short-circuit, leaving 2439 MV outputs in AudioFix).

C7. Audio-only container files are out of video-compliance scope. `VideoVertical.Evaluate` returns `(None, 'non_video_scope')` when `IsAudioOnlyContainer(Mf)` is true (`ContainerFormat` in `mp3, flac, ogg, wav, aac, opus, dsf, dff, ape, wma`) -- no video stream exists to be compliant or non-compliant about. Same guard is applied uniformly by `ContainerVertical.Evaluate` and `AudioVertical.Evaluate` (all three verticals return `None` for these files, not just Video). Feeds the WorkBucket NULL branch (`transcode.flow.md` D4) -> permanently `Unclassified`: `ContainerFormat` does not change post-scan, so the classification is stable, never transient. Defense-in-depth: `QueueManagementBusinessService` and `CommandComposer` independently refuse admission/command-build for audio-only containers regardless of compliance state. Verifiable: `Tests/Contract/TestNonVideoContainersExcluded.py`.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `RecomputeFor` -> `MediaFiles.VideoCompliant` | `VideoVertical._WriteResult` | `(VideoCompliant: bool/NULL, VideoCompliantReason: text/NULL)` | Generated column `WorkBucket` reflects the flag on next SELECT | Post-RecomputeFor SELECT |
| S2 | `VideoComplianceThresholds` -> vertical | operator via `/settings` PUT | 4 rows `(ResolutionCategory TEXT, Multiplier NUMERIC(4,2))`; multiplier > 0 (CHECK) | `GetMultiplier` reads fresh per call; fail-loud on missing row | `TestVideoComplianceMultiplier` |
| S3 | `Profiles` + `ProfileThresholds` -> `TierLadderRepository.GetProfileTarget` | Backfill + operator ladder edits | JOIN on `ProfileName + ContentClass + Resolution` -> INT kbps or None | vertical multiplies by multiplier; missing target returns `(None, 'missing_input:ProfileTargetKbps')` | `TestVideoComplianceMultiplier` |

## Cross-Vertical Contract

### Columns the VideoEncoding vertical WRITES

| Column | Written by |
|---|---|
| `MediaFiles.VideoCompliant` | `VideoVertical._WriteResult` |
| `MediaFiles.VideoCompliantReason` | `VideoVertical._WriteResult` |
| `VideoComplianceThresholds.*` | operator via `/settings` Transcoding card |

### Columns the VideoEncoding vertical READS from external tables

| Column | Read by | Owner |
|---|---|---|
| `MediaFiles.VideoBitrateKbps`, `TranscodedByMediaVortex`, `ResolutionCategory`, `AssignedProfile`, `ContentClass` | `Evaluate` | MediaProbe vertical + ContentClassifier |
| `Profiles.ProfileName`, `ProfileThresholds.TargetKbps` (per assigned profile) | `TierLadderRepository.GetProfileTarget` | Profiles vertical (operator via `/settings` bitrate ladder) |

### Stable function entry points (cross-vertical callers)

| Class.method | External caller(s) |
|---|---|
| `VideoVertical.RecomputeFor(MediaFileIds: List[int]) -> None` | `QueueManagementBusinessService.RecomputeForFiles` (post-probe orchestrator) |
| `VideoVertical.Evaluate(Mf) -> (bool/None, str/None)` | `ComplianceSummaryController.get_compliance_summary`; `RecomputeFor` internally |

### What is EXPLICITLY NOT a contract

- `_PIXEL_COUNTS` map + `_ASSUMED_FPS=24` (future: probe real fps when available)
- The format of `VideoCompliantReason` strings (today: `source_at_or_below_ceiling:...`, `source_above_ceiling:...`, `source_codec_matches_target:...`, `missing_input:<field>`, `non_video_scope`)

## Status

ACTIVE.

## Files

| File | Role |
|---|---|
| `VideoVertical.py` | Baseline compliance evaluator + `RecomputeFor` |
| `__init__.py` | Package marker |
| `VideoEncodingController.py` | HTTP surface for `/api/VideoEncoding/Rules` |
