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

C1. The video rule is stated once, in `transcode.flow.md` D4 (Video rows). A library with a default tier judges source kbps against the kbps that tier encodes the file's resolution at, times the resolution multiplier; the stored reason names source kbps, ceiling, tier, tier kbps and multiplier (`source_above_ceiling:2086>2000(tier=1:1000*2.0)`). In a library that tiers by genre the tier is the file's genre tier and the reason also names the deciding genre (`...(tier=3:3000*2.0,genre=Action)`, or `genre=none` when the movie has no genre); a movie whose genres are not fetched yet is undecided with reason `missing_input:Genres`. Verifiable: `Tests/Contract/TestMoviesVideoRule.py`. A library with no default tier judges against the file's assigned profile, with a same-codec pass first; its reason names the profile. Verifiable: `Tests/Contract/TestTvVideoRuleTier1.py`, `TestVideoVerticalCodecMatch.py`, `TestVideoComplianceMultiplier.py`.

C2. In a library with a default tier, neither the file's codec nor its assigned profile influences `VideoCompliant`. Verifiable: `SELECT COUNT(*) FROM MediaFiles mf JOIN StorageRoots sr ON sr.Id = mf.StorageRootId WHERE sr.DefaultQualityTier IS NOT NULL AND position('(profile=' in mf.VideoCompliantReason) > 0` returns 0.

C3. `VideoComplianceThresholds(ResolutionCategory UNIQUE, Multiplier NUMERIC(4,2) CHECK>0, LastUpdated)` seeded with `(480p, 1.5), (720p, 2.0), (1080p, 2.0), (2160p, 3.0)`. Every read fresh per `Evaluate` call (`db-is-authority` -- no `__init__` cache).

C4. Operator tunes multipliers via `/settings` GUI. GET `/api/SystemSettings/Transcoding` returns `VideoCompliance: [{ResolutionCategory, Multiplier}, ...]`. PUT persists via `VideoComplianceThresholdsRepository.UpsertAll`. No SQL required. Each library's default tier (`StorageRoots.DefaultQualityTier`, 1-5 or unset) is viewed and saved on the same card via GET/PUT `/api/SystemSettings/LibraryTiers`; a save re-evaluates every file in that library and the new value is read by the next evaluation without restart. Each genre's tier (`GenreQualityTiers.QualityTier`, 1-5 or "Library default") is viewed and saved on the same card via GET/PUT `/api/SystemSettings/GenreTiers`; a save moves every movie whose profile the operator did not set by hand to its genre tier's profile and re-evaluates the library.

C5. Fail-loud on ALL missing decision inputs. Missing multiplier row for a MediaFile's ResolutionCategory -> `RuntimeError`; missing MediaFileId -> `ValueError`; no try/except. Missing ResolutionCategory / VideoBitrateKbps / TierEncodeKbps / Genres (genre-sourced library, not fetched yet) / AssignedProfile and ProfileTargetKbps (library with no default tier) -> `(None, 'missing_input:<field>')`. The aggregator routes any file with `None` from any vertical to `WorkBucket=NULL` (Unclassified). This surfaces probe-not-yet-run / probe-column-null files as Unclassified rather than hiding them in Compliant. Reason: silent `(True, None)` on missing inputs caused Heroes S2 files at 12-14 Mbps to land in Remux because AssignedProfile-derived Family lookup returned None -> compliant-by-default.

C6. **MediaVortex-output terminal state enforced at aggregate layer, not per-vertical.** The `TranscodedByMediaVortex=TRUE` short-circuit lives in the WorkBucket GENERATED column CASE (see `work-bucket.feature.md` C7 + `transcode.flow.md` D7). `VideoVertical.Evaluate` NO LONGER short-circuits on this flag; it evaluates the multiplier check for every row. Aggregate layer routes MV outputs to Compliant regardless of any vertical's compliance opinion.

C7. Audio-only container files are out of video-compliance scope. `VideoVertical.Evaluate` returns `(None, 'non_video_scope')` when `IsAudioOnlyContainer(Mf)` is true (`ContainerFormat` in `mp3, flac, ogg, wav, aac, opus, dsf, dff, ape, wma`) -- no video stream exists to be compliant or non-compliant about. Same guard is applied uniformly by `ContainerVertical.Evaluate` and `AudioVertical.Evaluate` (all three verticals return `None` for these files, not just Video). Feeds the WorkBucket NULL branch (`transcode.flow.md` D4) -> permanently `Unclassified`: `ContainerFormat` does not change post-scan, so the classification is stable, never transient. Defense-in-depth: `QueueManagementBusinessService` and `CommandComposer` independently refuse admission/command-build for audio-only containers regardless of compliance state. Verifiable: `Tests/Contract/TestNonVideoContainersExcluded.py`.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `RecomputeFor` -> `MediaFiles.VideoCompliant` | `VideoVertical._WriteResult` | `(VideoCompliant: bool/NULL, VideoCompliantReason: text/NULL)` | Generated column `WorkBucket` reflects the flag on next SELECT | Post-RecomputeFor SELECT |
| S2 | `VideoComplianceThresholds` -> vertical | operator via `/settings` PUT | 4 rows `(ResolutionCategory TEXT, Multiplier NUMERIC(4,2))`; multiplier > 0 (CHECK) | `GetMultiplier` reads fresh per call; fail-loud on missing row | `TestVideoComplianceMultiplier` |
| S3 | `Profiles` + `ProfileThresholds` -> `TierLadderRepository.GetProfileTarget` | Backfill + operator ladder edits | JOIN on `ProfileName + ContentClass + Resolution` -> INT kbps or None | vertical multiplies by multiplier; missing target returns `(None, 'missing_input:ProfileTargetKbps')`. Libraries with no default tier only | `TestVideoComplianceMultiplier` |
| S4 | `FileTierResolver.Resolve(StorageRootId, MediaFileId)` -> vertical | `StorageRoots.(DefaultQualityTier, GenreSource)` + `MediaFiles.Genres` + `GenreQualityTiers` | `None` (library has no default tier) or `FileTier(Tier: int or None, Origin: '' / 'genre=<name>' / 'genre=none' / 'missing_input:Genres')` | vertical: None -> profile path; Tier None -> undecided with Origin as reason; else tier rule, Origin appended to the reason. The classifier reads the same result for the profile | `TestMoviesVideoRule` |
| S5 | `TierLadderRepository.GetTierEncodeKbps(Tier, ContentClass, Resolution)` -> vertical | operator ladder edits on `/settings` | INT kbps of the cell the tier encodes that source resolution at (follows `TranscodeDownTo`), or None | vertical multiplies by multiplier; None -> `missing_input:TierEncodeKbps` | `TestTvVideoRuleTier1Live` |

## Design Decisions

- **One rule, stated once.** The bucket rule lives in `transcode.flow.md` D4; this doc, the classifier doc and `DOMAIN.md` point at it.
- **One answer to "what tier is this file".** `FileTierResolver` is the only place a file's tier is worked out (library default, or genre tier in a genre-sourced library). The video verdict and the classifier's profile both call it, so the tier a file is judged at and the tier it is encoded at cannot disagree.
- **Genre is data, not a code path.** A library with a genre source and one without go through the same lookup; genre only changes which tier comes back. TV has no genre source and keeps byte-identical reasons.
- **Bucket by default tier, encode by profile.** A profile the operator sets by hand changes what a file is encoded at, never its bucket (operator decision for TV 2026-10-06, extended to Movies 2026-10-13).
- **External reads happen at ingest, never at evaluation.** Radarr is read once per scan by `MovieGenreSyncService` and stored in `MediaFiles.Genres`; every evaluation reads the database only (`db-is-authority`). `Core/Arr/RadarrClient` is the one Radarr reader; `NoAudioResolver` uses its folder match.
- **Writers cascade.** `Genres` is a compliance input; its writer reassigns tier profiles and re-evaluates before returning (`writer-owns-cascade`).
- **Known debt:** a library with no default tier (XXX) still takes the profile-and-codec path, so the vertical has two paths chosen by data (call-graph audit signal 5). It is deleted by backlog row 1 `xxx-video-rule`.

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
