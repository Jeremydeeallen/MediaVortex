# Compliance Symmetry -- design spec

**Date:** 2026-06-22
**Status:** Design locked, awaiting directive open
**Replaces / consolidates:** `transcode-vs-remux-routing.feature.md` Section L (C29-C31), the compliance + bucket halves of `transcode-vs-remux-routing.feature.md`, the encoder-vs-compliance split implicit in `Profiles.feature.md`, the codec-side audio knobs that today drift between `audio-normalization.feature.md` and `ContainerComplianceRules`.

This spec is the canonical contract for the compliance + bucket + profile-lifecycle model from this date forward. Existing feature docs that duplicate these contracts are pruned and pointed at this spec (see Doc Consolidation Plan).

## Decisions Made During Tightening (2026-06-22)

Recorded for review. Override any of these in the spec-review pass and I'll reflow:

1. **Codec namespace split.** `Profile.Codec` (existing) stays = encoder library name (`libsvtav1`). New `Profile.StreamCodecName` (e.g. `av1`, `hevc`) is the compliance comparator. `VideoVertical.Evaluate` compares `Mf.Codec` to `Profile.StreamCodecName`. Operator-facing label clarifies the distinction.
2. **Drafts replace eager locking.** Profiles enter the DB with `Draft=TRUE`. Drafts cannot be set as Default, cannot be assigned to shows, cannot be referenced by any cascade. Compliance fields stay editable. Operator clicks "Finalize" -> `Draft=FALSE`; fields lock atomically. Existing profiles migrate AS draft, requiring a one-time finalize pass.
3. **`MaxAudioChannels` moves to `AudioNormalizationConfig`** (per-scope). Channel count is a playback-environment concern, not a content-tier concern.
4. **Explicit NULL handling in `WorkBucket`.** Any NULL boolean -> `WorkBucket=NULL` (undecidable hold). Queue-population requires `WorkBucket IS NOT NULL`.
5. **Resolution tiers defer to `Core.Resolution.ResolutionTierRegistry`.** This spec does not enumerate tier strings.
6. **Cascade split kept** (profile-2-tier for quality, audio-4-tier for loudness). Operator gets a per-file `/MediaFile/<id>/ComplianceSummary` view that joins both cascades into one display.
7. **Lock UX.** Locked compliance fields render gray + read-only. Each locked profile row carries a "Copy as new draft" button -> POST `/api/profiles/<id>/copy-draft` -> opens an editable Draft pre-populated from the locked source.
8. **Container universe.** `mp4`, `mkv`, `m4v`, `mov`. `webm` deliberately excluded.
9. **Margin knobs dropped.** `VideoBitrateMarginPct` and `AudioBitrateMarginPct` are NOT exposed. Compliance check is `source <= target` with a hardcoded 5% rounding tolerance in the comparator (absorbs ffprobe noise; never an operator-facing knob).
10. **`TargetVideoKbps` and `TargetAudioKbps` are NULLABLE.** NULL = "trust the encoder's rate control" (typical for VBR/CQ profiles like NVENC AV1 P7 CANARY VBR -720p). When NULL, the bitrate check is skipped for that dimension; codec + resolution checks still run.
11. **`ProfileThresholds` retained.** Stays as the encoder-side per-source-resolution tuning table (CRF/CQ, downscale targets, per-tier bitrates, ContainerType for ffmpeg argv). `CommandBuilder` reads ProfileThresholds keyed by SOURCE resolution to build the encode command. `Profile.*` carries the compliance BAR; `ProfileThresholds.*` carries the encoder TARGETS. They answer different questions and don't conflict.
12. **Pre-migration default seeded from `NVENC AV1 P7 CANARY VBR -720p`.** Concrete values for the seeded fallback profile: `Codec=av1_nvenc`, `StreamCodecName=av1`, `TargetResolutionCategory=720p`, `TargetVideoKbps=NULL` (VBR), `AllowUpscale=FALSE`, `AudioCodec=aac`, `TargetAudioKbps=128`, `Container=mp4`.
13. **Dual-track behavior unchanged from existing shipped contract** (`audio-normalization.feature.md` C1-C3): Original = LRA preserved, Dialog Boost = LRA compressed to <=11.0 LU, both loudnorm'd to `TargetIntegratedLufs`, Dialog Boost gets `disposition.default=1`. See Open Questions for the bit-copy-vs-LRA-compressed interpretation question.

## Goal

Stop the "target keeps moving" cycle that has produced repeated transcode / remux / loudnorm passes on the same files. Achieve four outcomes simultaneously:

1. **Stable compliance verdict** -- once a file becomes Compliant, no profile tweak silently re-enters it into a queue.
2. **Bucket-scoped operations** -- a file in any bucket gets the minimum-scope work; running a bucket cannot push a file into a higher-cost bucket post-replacement.
3. **One source of truth per knob** -- every threshold lives in exactly one column, queried fresh, with no parallel cached or hardcoded copy.
4. **Operator can see and tune** -- every compliance-shaping knob is visible in the GUI; every change is a deliberate named act with predictable effect.

## Architectural Model

Three orthogonal compliance dimensions, each evaluated by its own vertical, each producing a single boolean on `MediaFiles`:

```
VideoVertical.Evaluate(Mf)     -> MediaFiles.VideoCompliant      BOOLEAN
ContainerVertical.Evaluate(Mf) -> MediaFiles.ContainerCompliant  BOOLEAN
AudioVertical.Evaluate(Mf)     -> MediaFiles.AudioCompliant      BOOLEAN
```

Two parallel cascade systems resolve the bars these verticals evaluate against:

| Cascade | What it resolves | Granularity |
|---|---|---|
| **Profile cascade** (existing) | Video, container, audio-codec bar | `ShowSettings.AssignedProfile > SystemSettings.DefaultProfileName` |
| **Audio policy cascade** (existing in `AudioNormalization`) | Loudness bar, dual-track contract, language keep policy | `item > folder > library > global` (4-tier) |

One generated column derives the bucket. NULL booleans short-circuit to NULL (undecidable hold; not queueable):

```
MediaFiles.WorkBucket  (GENERATED, redefined to handle NULL explicitly)
  = NULL            when ANY OF (VideoCompliant, ContainerCompliant, AudioCompliant) IS NULL
                                   -- undecidable: hold out of queue
  = 'Transcode'     when VideoCompliant      = FALSE
  = 'Remux'         when VideoCompliant      = TRUE  AND ContainerCompliant = FALSE
  = 'AudioFixOnly'  when VideoCompliant      = TRUE  AND ContainerCompliant = TRUE  AND AudioCompliant = FALSE
  = NULL            when all three are TRUE     -- already compliant; no work needed
```

Bucket precedence (`!Video -> Transcode`, `!Container -> Remux`, `!Audio -> AudioFixOnly`) names which bucket OWNS the file. Within that bucket, only the dimensions that are actually False produce work.

**Queue-population invariant:** every queue-entry path's WHERE clause includes `WorkBucket IS NOT NULL`. A NULL WorkBucket means "system cannot decide this file's fate" -- the cure is admin-recompute after resolving the missing input (probe, profile, audio policy), not enqueueing on a guess.

## Per-Profile Compliance Bar (immutable once written)

The `Profiles` table carries the entire video/container/audio-codec bar. Compliance-defining columns are **immutable** after first save; the API refuses updates with HTTP 400 when at least one MediaFile references the profile.

### Video (5 knobs)

| Column | Type | Purpose |
|---|---|---|
| `Codec` | VARCHAR(32) | Encoder library name -- the encoder MediaVortex invokes. E.g. `libsvtav1`, `libx265`, `av1_nvenc`. NOT used for compliance comparison. |
| `StreamCodecName` | VARCHAR(16) | Source-stream codec name as ffprobe reports it -- the compliance comparator. E.g. `av1`, `hevc`, `h264`. Typically derived from `Codec` (`libsvtav1` -> `av1`) but stored explicitly because the namespaces are distinct and either may need to vary independently (e.g. NVENC encoder, software-decoded source -- both produce stream codec `av1`). |
| `TargetResolutionCategory` | VARCHAR(8) | Max resolution. Allowed values from `Core.Resolution.ResolutionTierRegistry` (canonical: `480p`, `540p`, `720p`, `1080p`, `1440p`, `2160p`). |
| `TargetVideoKbps` | INT NULLABLE | Video stream bitrate ceiling. NULL = "trust encoder rate control" (skip the bitrate check). Typical for VBR/CQ profiles. |
| `AllowUpscale` | BOOLEAN | When TRUE, source < target resolution still gets re-encoded to target (Premium 4K case). When FALSE, source < target is compliant by default. |

### Audio (2 knobs, codec-side)

| Column | Type | Purpose |
|---|---|---|
| `AudioCodec` | VARCHAR(16) | The only acceptable audio codec (default `aac` -- industry standard for MP4 / streaming / broadcast) |
| `TargetAudioKbps` | INT NULLABLE | Audio bitrate ceiling. NULL = "trust audio encoder rate control" (skip the bitrate check). |

`MaxAudioChannels` lives on `AudioNormalizationConfig` per the 4-tier scope cascade (it's a playback-environment concern, not content-tier), alongside loudness knobs (`TargetIntegratedLufs`, `TargetLra`, `EmitTracks`, `LanguageKeepPolicy`, etc.). The compliance check defers to `AudioComplete` for "normalized + dual-track emitted + channels match policy" rather than re-checking each component.

### Container (1 knob)

| Column | Type | Purpose |
|---|---|---|
| `Container` | VARCHAR(8) | The only acceptable container extension. Allowed values: `mp4`, `mkv`, `m4v`, `mov`. Also the encode target. `webm` deliberately excluded (not in current library). |

### Total

**8 per-profile compliance knobs** (5 video + 2 audio-codec + 1 container). Library-wide compliance knobs: **zero.** Per-scope audio knobs (loudness + channels): owned by `AudioNormalizationConfig`.

### Rounding tolerance (not a knob)

Bitrate comparisons absorb a hardcoded **5% rounding tolerance** in the comparator (`source <= target * 1.05`). This is a code-internal constant in the vertical, not an operator-facing knob -- its purpose is to swallow ffprobe rounding noise, not to expose a tunable margin.

## Per-Profile Encoder Section (mutable)

Editing these does NOT change the compliance verdict. Operator can tune them freely; only future encodes are affected.

| Column | Purpose |
|---|---|
| `Preset` | Encoder preset (0-13 for SVT-AV1) |
| `FilmGrain` | Film grain synthesis level |
| `YadifMode`, `YadifParity`, `YadifDeint` | Deinterlacing |
| `UseNvidiaHardware` | NVENC vs software |
| `ProfileName` | Display name |
| `Description` | Operator-facing description |
| `SortOrder` | Display order |
| `Active` | FALSE = retired (hidden from pickers, queryable for compliance of existing files) |

### `ProfileThresholds` (retained sibling table -- encoder tuning per source resolution)

`ProfileThresholds` is NOT touched by this spec. It remains the per-source-resolution encoder tuning table that `CommandBuilder` reads to construct the ffmpeg argv. Columns include `Resolution` (source tier), `VideoBitrateKbps` / `AudioBitrateKbps` (per-tier encoder targets, `0` = VBR/CQ), `Quality` (CRF/CQ), `TranscodeDownTo` (per-source downscale target), `ContainerType`.

**Role split (compliance bar vs encoder tuning):**

| Question | Answers from |
|---|---|
| Is this file good enough? (yes/no) | `Profiles.*` -- single output target, immutable bar |
| If re-encoding, what's my CRF / bitrate / downscale target for a 1080p source? | `ProfileThresholds.*` keyed by source resolution -- mutable encoder tuning |

The two tables don't conflict. `Profile.TargetResolutionCategory` says "the compliance bar is 720p output." `ProfileThresholds.Resolution='1080p'` says "when I encode from a 1080p source, target 720p, use CRF X, container mp4." Both are needed; both have different lifecycles.

## Per-Scope Audio Loudness + Channels (existing 4-tier cascade)

The shipped `AudioNormalizationConfig` 4-tier cascade owns loudness policy. This spec adds ONE column (`MaxAudioChannels`) and otherwise leaves the system unchanged. The full set of per-scope knobs after this spec:

- `TargetIntegratedLufs` (default `-23 LUFS`) -- existing
- `TargetLra` (null = preserve source on Original; `11.0` on Dialog Boost) -- existing
- `EmitTracks` (Original + Dialog Boost per kept language) -- existing
- `LanguageKeepPolicy`, `PreVerticalReNormalizePolicy`, etc. -- existing
- `MaxAudioChannels` (default `2`) -- **NEW** in this spec. Drives downmix in `CommandBuilder`; consumed by `AudioPolicyAdmissionGate` for the channel-count compliance check.

Dual-track output is the existing contract (`audio-normalization.feature.md` C1-C3). Every encoded output ships >= 2 tracks per kept English language: Original (LRA preserved, `disposition.default=0`) and Dialog Boost (LRA <= 11.0, `disposition.default=1`). `PostEncodeMeasurementService` writes `TranscodeAttempts.AudioTracksEmittedJson` per-track post-encode, which feeds `AudioComplete`.

## Profile Lifecycle: Draft -> Finalized -> Retired

Three lifecycle states. Compliance immutability is enforced via the Draft/Finalized boundary, not via reference-count eagerness.

- **Draft** (`Draft=TRUE`): the only state where compliance fields are editable.
  - Cannot be set as `SystemSettings.DefaultProfileName`.
  - Cannot be assigned to any `ShowSettings.AssignedProfile` row.
  - Cannot be referenced by any `MediaFiles.AssignedProfile` (the cache column).
  - All 10 compliance fields + the 8 encoder/cosmetic fields are writable.
  - GUI: orange "DRAFT" pill next to the profile name; "Finalize" button.
- **Finalize** (operator action): `Draft=FALSE`, atomic with the lock.
  - Compliance fields become read-only; API rejects updates with HTTP 400; UI grays out fields.
  - Encoder/cosmetic fields remain editable forever.
  - Profile is now eligible to be set as Default, assigned to shows, or referenced via cascade.
- **Retire** (`Active=FALSE`): set via `/Setup -> Profiles`. Retired profiles hide from operator-facing pickers but stay in the table; MediaFiles already referencing them continue to evaluate compliance against the (immutable) bar.
- **Delete**: only allowed when zero MediaFiles reference the profile AND it is not the Default. UI surfaces a count: `"12 files reference this profile -- reassign before deleting"`.

The active `SystemSettings.DefaultProfileName` cannot be retired without first picking a replacement Default.

**Migration of existing profiles**: every pre-migration profile enters the new schema with `Draft=TRUE` and NULL for the new columns. A one-time finalize pass (operator-driven via `/Setup -> Profiles`) fills the new fields per profile, then flips `Draft=FALSE`. Pre-finalize, the cascade falls back to a "pre-migration default" profile so the queue does not stall; this default ships as a seeded `Active=TRUE, Draft=FALSE` row.

**Copy-as-new-draft (the tweak path)**: every locked profile row in the GUI carries a "Copy as new draft" button. `POST /api/profiles/<id>/copy-draft` clones the source row into a new `Draft=TRUE` profile with all fields editable. Operator tweaks + finalizes + reassigns shows. This is the supported path for "I want to bump the bitrate" -- not in-place edit.

## Compliance Evaluation

### `VideoVertical.Evaluate(Mf) -> (Compliant: bool, Reason: str)`

```
profile = EffectiveProfileResolver.Resolve(Mf)
if profile is None:
    return (None, 'no_effective_profile')

if (Mf.Codec or '').lower() != (profile.StreamCodecName or '').lower():
    return (False, f'codec:{Mf.Codec}')

srcRank = ResolutionTier(Mf.ResolutionCategory).Rank
tgtRank = profile.TargetResolutionCategory.Rank

if srcRank > tgtRank:
    return (False, f'resolution:{Mf.ResolutionCategory}')

if srcRank < tgtRank and not profile.AllowUpscale:
    return (True, 'upscale_prevented')

if profile.TargetVideoKbps is not None:
    ceiling = profile.TargetVideoKbps * 1.05   # hardcoded 5% rounding tolerance
    if Mf.VideoBitrateKbps > ceiling:
        return (False, f'bitrate:{Mf.VideoBitrateKbps}>{ceiling:.0f}')

return (True, None)
```

**No `EstimatedSavingsMB`, no `MinSourceBpp` override, no `TranscodedByMediaVortex` exemption, no operator-facing margin knob.** The immutability of the profile bar + nullable bitrate ceiling + hardcoded 5% rounding tolerance handle every legitimate case. Files that were Compliant cannot become non-Compliant unless the cascade reassigns them to a different profile (a deliberate operator act).

### `AudioVertical.Evaluate(Mf) -> (Compliant: bool, Reason: str)`

```
profile = EffectiveProfileResolver.Resolve(Mf)
if profile is None:
    return (None, 'no_effective_profile')

# Upstream undecidables (preserved from existing AudioVertical)
if Mf.AudioCorruptSuspect is True:
    return (None, 'audio_corrupt_suspect')
if Mf.HasExplicitEnglishAudio is False:
    return (None, 'no_english_audio')
if not Mf.AudioCodec and Mf.Resolution:
    return (None, 'no_audio_stream')
if Mf.LoudnessMeasurementFailureReason:
    return (None, 'loudness_measurement_failed')

# Codec-side bar (per-profile)
if (Mf.AudioCodec or '').lower() != (profile.AudioCodec or '').lower():
    return (False, f'codec:{Mf.AudioCodec}')

if profile.TargetAudioKbps is not None:
    ceiling = profile.TargetAudioKbps * 1.05   # hardcoded 5% rounding tolerance
    if Mf.AudioBitrateKbps > ceiling:
        return (False, f'bitrate:{Mf.AudioBitrateKbps}>{ceiling:.0f}')

# Loudness + channels bar (per-scope, via existing admission gate + AudioComplete)
# Channel count check moved to AudioPolicyAdmissionGate -- it reads
# AudioNormalizationConfig.MaxAudioChannels at the effective scope.
decision = AudioPolicyAdmissionGate.AdmitOrDefer(Mf)
if decision.Outcome != 'admitted':
    return (None, decision.DeferReason)
if Mf.AudioComplete is not True:
    return (False, 'needs_normalization')

return (True, None)
```

`AudioComplete=True` requires dual-track emit + post-encode probe per `audio-normalization.feature.md`. The dual-track contract is enforced upstream; this evaluator trusts the flag.

### `ContainerVertical.Evaluate(Mf) -> (Compliant: bool, Reason: str)`

```
profile = EffectiveProfileResolver.Resolve(Mf)
if profile is None:
    return (None, 'no_effective_profile')

if Mf.ContainerFormat.lower() != profile.Container.lower():
    return (False, f'container:{Mf.ContainerFormat}')

return (True, None)
```

The cross-vertical leak (`AcceptableAudioCodecsCsv` in `ContainerComplianceRules`) is removed -- audio codec belongs in `AudioVertical`.

## Bucket-Scoped Operations Contract

Each bucket's worker emits the **minimum-scope** ffmpeg command per the table below. The three compliance booleans are read fresh at command-build time; each False adds the corresponding op, each True suppresses it.

| Bucket | Always (the bucket-defining op) | Conditionally |
|---|---|---|
| `Transcode` | video re-encode via `profile.Codec` (encoder) targeting `profile.StreamCodecName` (stream) + encoder section | container rewrite if `!ContainerCompliant`; audio re-encode + loudnorm + downmix-if-policy-requires if `!AudioCompliant` |
| `Remux` | container rewrite to `profile.Container` | audio re-encode + loudnorm + downmix-if-policy-requires if `!AudioCompliant` |
| `AudioFixOnly` | audio re-encode + loudnorm + downmix-if-policy-requires per `AudioNormalizationConfig` (incl. `MaxAudioChannels`) | -- |

Symmetric reads in `CommandBuilder`:

- `!AudioCompliant` -> emit dual-track loudnorm filter chain per `linear-loudnorm.feature.md` + `audio-normalization.feature.md`; emit `-ac N` + `pan` filter if effective `AudioNormalizationConfig.MaxAudioChannels` < source channels
- `AudioCompliant=True` -> `-c:a copy` (do not touch audio stream)
- `!ContainerCompliant` -> output container = `profile.Container`, source basename + `-mv` suffix
- `ContainerCompliant=True` -> output container matches source container; no rewrite

## Idempotency Invariant

Running any bucket's worker on a file flips ONLY the booleans the bucket touched, and only from False to True. No worker may cause any compliance boolean to flip from True to False post-replacement.

**Surface query (steady-state regression check):**

```sql
SELECT COUNT(*) FROM MediaFilesArchive a
JOIN MediaFiles m ON m.Id = a.MediaFileId
WHERE a.WorkBucket = 'AudioFixOnly'
  AND m.WorkBucket  = 'Transcode';
-- Must be 0. Any non-zero row indicates an AudioFix poisoned a video verdict.
```

Symmetric queries cover Remux -> Transcode and AudioFixOnly -> Remux.

## Re-evaluation Triggers

`RecomputeForFiles(MediaFileIds)` runs the three vertical evaluators per file and writes the three booleans + their reason columns. The generated `WorkBucket` column updates automatically.

Recompute fires when:

1. **Probe complete** (new file or replacement re-probed) -- single file.
2. **Profile cascade change** -- show reassigned to a different profile (`ShowSettings.AssignedProfile` change) or default changed (`SystemSettings.DefaultProfileName` change). All files whose cascade now resolves to a different profile.
3. **File replacement post-flight** -- single file, after successful replace + re-probe.
4. **Admin endpoint** `POST /api/PriorityMaterialization/Recompute` -- scoped or library-wide.
5. **Audio policy scope change** -- the existing `AudioNormalizationConfig` mid-flight reload is observed by the next evaluation; if the operator wants existing files re-evaluated against the new loudness policy, they invoke the admin recompute.

Recompute does NOT fire on profile *encoder-field* edits (Preset, FilmGrain, etc.) because those do not change the compliance bar.

## GUI Surfaces

### `/Setup -> Profiles` (the profile editor)

Each profile row renders one of two states depending on `Draft`:

**Draft state (editable):**

```
[ SVT-AV1 P6 FG10 720p ]  [DRAFT]                     [Finalize]  [Delete]
[ Quality Bar (editable while Draft) ]
  Codec (encoder)              [libsvtav1            v]
  StreamCodecName (compliance) [av1                  v]
  TargetResolutionCategory     [720p                 v]
  TargetVideoKbps              [(blank = VBR)         ]   <-- blank for VBR/CQ profiles
  AllowUpscale                 [ ] off
  AudioCodec                   [aac                  v]
  TargetAudioKbps              [128                   ]   <-- blank for VBR audio
  Container                    [mp4                  v]

[ Encoder Settings (editable always) ]
  Preset                       [6                     ]
  FilmGrain                    [10                    ]
  YadifMode / Parity / Deint   [1 / 1 / 1             ]
  UseNvidiaHardware            [ ] off

[ Profile Metadata ]
  ProfileName                  [SVT-AV1 P6 FG10 720p ]
  Description                  [Standard bulk profile]
  SortOrder                    [10                    ]
```

**Finalized state (compliance fields gray, encoder fields live):**

```
[ SVT-AV1 P6 FG10 720p ]                              [Copy as new draft]  [Retire]
[ Quality Bar (locked) ]                              -- read-only --
  Codec (encoder)              libsvtav1
  StreamCodecName (compliance) av1
  ... (all 10 compliance fields render as static text)

[ Encoder Settings (editable) ]
  Preset                       [6                     ]
  ... (mutable section unchanged)

[ Reference count ]
  4,217 MediaFiles use this profile.
  [Retire]   [Delete (disabled until 0 refs)]
```

### `/settings` (global Default + library-wide knobs)

- `SystemSettings.DefaultProfileName` (already exists). Only `Draft=FALSE, Active=TRUE` profiles appear in the dropdown.
- Banner when a retired profile is still referenced: `"Profile X is retired but 12 files reference it. Reassign?"`

### `/ShowSettings` Card 3 (per-show override)

- Per-row Profile dropdown -- already exists. Only `Draft=FALSE, Active=TRUE` profiles appear.

### `/AudioNormalization` (loudness policy + channels, per-scope)

- 4-tier scope settings, dual-track config -- existing.
- **Adds `MaxAudioChannels`** as a per-scope knob (was previously a per-profile knob in earlier drafts of this spec).

### `/Work/<bucket>` (per-bucket landing pages)

- Already exists from `work-bucket.feature.md`. No changes.

### `/MediaFile/<id>/ComplianceSummary` (NEW per-file view)

- Displays the joined cascade: effective Profile + effective AudioNormalizationConfig for this file.
- Shows the three compliance booleans + reason strings.
- Shows `WorkBucket` and (if non-NULL) the bucket's planned operations.
- Eliminates "where's my compliance bar coming from for this file" confusion when two cascades disagree.
- Backed by a single read endpoint `GET /api/MediaFile/<id>/ComplianceSummary`.

## Decision Diagram

```
                              FILE PROBED
                                  |
                                  v
              +-------------------+-------------------+
              |    Effective profile via cascade      |
              | ShowSettings -> SystemSettings.Default|
              +-------------------+-------------------+
                                  |
        +-------------------------+-------------------------+
        |                         |                         |
        v                         v                         v
+-------+--------+      +---------+---------+      +--------+--------+
| VideoVertical  |      | ContainerVertical |      |  AudioVertical  |
|                |      |                   |      |                 |
| Codec match?   |      | Container match?  |      | Codec match?    |
| Res <= Target? |      |                   |      | Channels <= Max?|
| Bitrate <= cap?|      |                   |      | Bitrate <= cap? |
+-------+--------+      +---------+---------+      | AdmitOrDefer    |
        |                         |                | AudioComplete?  |
        v                         v                +--------+--------+
  VideoCompliant            ContainerCompliant              |
        |                         |                         v
        |                         |                  AudioCompliant
        +-------------+-----------+-------------------------+
                      |
                      v
        +-------------+--------------+
        |   MediaFiles.WorkBucket    |  (GENERATED column)
        |                            |
        |  !V          -> Transcode  |
        |  V, !C       -> Remux      |
        |  V,  C, !A   -> AudioFixOnly|
        |  V,  C,  A   -> NULL       |
        +-------------+--------------+
                      |
                      v
        +-------------+--------------+
        |   CommandBuilder           |
        |   (per-bucket worker)      |
        |                            |
        |  Always-op for the bucket  |
        |  + every conditional op    |
        |    whose !flag is set      |
        +-------------+--------------+
                      |
                      v
                  TRANSCODE
                      |
                      v
        +-------------+--------------+
        |   FileReplacement +        |
        |   re-probe +               |
        |   RecomputeForFiles        |
        +-------------+--------------+
                      |
                      v
              All three TRUE
              WorkBucket = NULL
              (no re-queue)
```

## Schema Changes

All migrations are idempotent (`ADD COLUMN IF NOT EXISTS`, `INSERT ... ON CONFLICT DO NOTHING`). No destructive changes pre-cutover.

### Profiles table

```sql
ALTER TABLE Profiles
  ADD COLUMN IF NOT EXISTS Draft BOOLEAN DEFAULT TRUE,                 -- new: lifecycle
  ADD COLUMN IF NOT EXISTS Active BOOLEAN DEFAULT TRUE,                -- new: retirement
  ADD COLUMN IF NOT EXISTS StreamCodecName VARCHAR(16),                -- new: compliance comparator (av1, hevc, h264)
  ADD COLUMN IF NOT EXISTS TargetResolutionCategory VARCHAR(8),        -- if not already
  ADD COLUMN IF NOT EXISTS TargetVideoKbps INT,                        -- NULLABLE; NULL = trust encoder rate control
  ADD COLUMN IF NOT EXISTS AllowUpscale BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS AudioCodec VARCHAR(16),
  ADD COLUMN IF NOT EXISTS TargetAudioKbps INT,                        -- NULLABLE; NULL = trust audio encoder rate control
  ADD COLUMN IF NOT EXISTS Container VARCHAR(8);
-- Note: MaxAudioChannels moves to AudioNormalizationConfig, not Profiles.
-- Note: NO margin columns. Comparison is `source <= target * 1.05` with the 5% being a hardcoded constant in the vertical.
```

### AudioNormalizationConfig table

```sql
ALTER TABLE AudioNormalizationConfig
  ADD COLUMN IF NOT EXISTS MaxAudioChannels INT DEFAULT 2;   -- 2 = stereo, 6 = surround
```

### MediaFiles table

No new columns required. The three booleans (`VideoCompliant`, `ContainerCompliant`, `AudioCompliant`) and `WorkBucket` (generated) already exist from the compliance-rip directive.

**`WorkBucket` generated column redefined** to handle NULLs explicitly:

```sql
ALTER TABLE MediaFiles DROP COLUMN WorkBucket;  -- existing GENERATED expression
ALTER TABLE MediaFiles ADD COLUMN WorkBucket TEXT GENERATED ALWAYS AS (
  CASE
    WHEN VideoCompliant IS NULL OR ContainerCompliant IS NULL OR AudioCompliant IS NULL
      THEN NULL
    WHEN VideoCompliant = FALSE THEN 'Transcode'
    WHEN ContainerCompliant = FALSE THEN 'Remux'
    WHEN AudioCompliant = FALSE THEN 'AudioFixOnly'
    ELSE NULL
  END
) STORED;
```

### Dying tables (RENAME, not DROP, per 30-day recoverability)

- `VideoComplianceRules -> VideoComplianceRules_OLD_2026_06_22`
- `ContainerComplianceRules -> ContainerComplianceRules_OLD_2026_06_22`

The remaining `*Rules_OLD_*` tables from compliance-rip can be DROPPED once this directive lands (their 30-day window expires 2026-07-21).

## Doc Consolidation Plan

Doc consolidation lands WITH this spec (not deferred to the implementation directive) per the no-duplication mandate. The following docs are pruned to point at this spec (no duplicated content):

| Doc | Action |
|---|---|
| `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` | Sections D, E, F, G, J, L pruned. Replaced with one-line pointer: `See docs/superpowers/specs/2026-06-22-compliance-symmetry-design.md for the canonical compliance + bucket contract.` Sections A (cascade), B (GUI surfaces), C (cache), H (admin), I (visibility), K (Remux audio integrity) retained as routing-specific contracts not duplicated here. |
| `Features/Profiles/Profiles.feature.md` | Profile lifecycle section pruned. Replaced with pointer to spec's `Profile Lifecycle` section. |
| `Features/AudioNormalization/audio-normalization.feature.md` | Untouched. This spec defers to it for loudness policy. Cross-reference added: `Audio codec / channel / bitrate bar lives in <spec>; loudness bar lives here.` |
| `Features/WorkBucket/work-bucket.feature.md` | Untouched. Pure consumer of the generated `WorkBucket` column. |
| `transcode.flow.md` | Stage 4 (queue admission) and Stage 7 (post-flight recompute) prose pruned. Replaced with pointer. Cross-stage seams S* retained. |

## Migration / Rollout

1. **Schema migrations** (idempotent ALTER TABLE on `Profiles` + `AudioNormalizationConfig`; redefine generated `MediaFiles.WorkBucket`).
2. **Seed a pre-migration default profile** named `_PreMigrationDefault` (`Draft=FALSE, Active=TRUE`). Concrete values per Decision #12 (`Codec=av1_nvenc`, `StreamCodecName=av1`, `TargetResolutionCategory=720p`, `TargetVideoKbps=NULL`, `AllowUpscale=FALSE`, `AudioCodec=aac`, `TargetAudioKbps=128`, `Container=mp4`). Cloned from the existing `NVENC AV1 P7 CANARY VBR -720p` profile's encoder section so encode behavior matches the operator's current production profile. Idempotent via `INSERT ... ON CONFLICT DO NOTHING`.
3. **Migrate existing profiles to Draft=TRUE** -- single UPDATE statement; existing references continue to resolve via the seeded pre-migration default until each profile is finalized.
4. **Vertical refactor** -- `VideoVertical`, `AudioVertical`, `ContainerVertical` read per-profile columns; no library-wide rules tables consulted. Drop `_EstimatedSavingsMB`, `_IsAlreadyEfficient`, `_LoadAudioNormalizedSet` legacy code paths.
5. **API immutability + lifecycle enforcement** -- `PATCH /api/Profiles/<id>/knobs` rejects compliance-field updates when `Draft=FALSE`. New `POST /api/Profiles/<id>/copy-draft` and `POST /api/Profiles/<id>/finalize` endpoints.
6. **GUI changes** -- profile editor renders Draft vs Finalized states; "Copy as new draft" button on finalized rows; new `/MediaFile/<id>/ComplianceSummary` view; `MaxAudioChannels` knob moves to `/AudioNormalization`.
7. **Operator finalize pass** -- operator-driven, one-time. Walk each Draft profile, populate the new fields, click Finalize. Until done, files in shows assigned to drafted profiles resolve to the pre-migration default.
8. **Recompute pass** -- full library `RecomputeForFiles` to populate the three booleans against the new bar.
9. **Cutover verification** -- run the three idempotency surface queries; expect all zero. Run all NEW + REUSED contract tests; assert green.
10. **Cleanup** -- RENAME `VideoComplianceRules -> VideoComplianceRules_OLD_2026_06_22`; `ContainerComplianceRules -> ContainerComplianceRules_OLD_2026_06_22`. DROP `*_OLD_2026_06_21` tables from prior compliance-rip whose 30-day window expires 2026-07-21.
11. **Doc consolidation** -- prune and point existing docs per the table above; already landed with this spec.

## Open Questions

None blocking. One deferred for operator clarification:

- **Dialog Boost track interpretation.** The operator's 2026-06-22 statement -- "keep the original loud norm setting and then do a copy of the audio for dialog" -- has two readings:
  - **(a) Keep existing shipped contract** (`audio-normalization.feature.md` C2-C3): Original = LRA preserved (matches source dynamics, `disposition.default=0`); Dialog Boost = LRA compressed to <=11.0 LU (dialog-clarity-optimized, `disposition.default=1`). Both loudnorm'd to `TargetIntegratedLufs`. **Current default** -- this spec defers to the shipped vertical.
  - **(b) Simplify** to: Original = loudnorm'd; Dialog Boost = bit-identical copy of Original with `disposition.default=1`. No dialog-specific LRA compression. Smaller code, less per-track post-encode probe complexity, but loses the dialog-clarity benefit of LRA compression.
  Operator picks (a) or (b) before `compliance-symmetry` enters IMPLEMENTING.
- **Concurrent-finalize race**: if two operators click Finalize on the same profile concurrently, last-write-wins (acceptable; finalize is rare and idempotent if the values match). No optimistic locking added unless a real incident surfaces.

## Non-goals

- Subtitle compliance (separate vertical, owned by `SubtitleFix*` work)
- Per-track loudness compliance beyond the dual-track contract already in `audio-normalization.feature.md`
- HDR / Dolby Vision passthrough (out of scope; treat as `AllowUpscale`-like extension if needed later)
- Multi-language emit beyond the existing AudioNormalization 4-tier cascade
- Renaming the `WorkBucket` column or its values
- Touching `/Work/<bucket>` landing pages or the `WorkBucketRepository`

## Verification Plan

Each criterion in the eventual directive will cite a concrete probe. Named test files (new + reused):

| Test file | What it asserts |
|---|---|
| `Tests/Contract/TestVideoComplianceBar.py` (NEW) | One test per video knob (Codec/StreamCodecName, Resolution, Bitrate ceiling + NULL semantics, AllowUpscale): create a MediaFile at the bar, +/-1 unit, +/-large; assert `VideoVertical.Evaluate` verdict + Reason string. Includes one test confirming `TargetVideoKbps IS NULL` skips the bitrate check. Includes one test confirming a 5% over-ceiling source passes (rounding tolerance) and 6% over fails. |
| `Tests/Contract/TestAudioComplianceBar.py` (NEW) | One test per audio-codec knob (AudioCodec match/mismatch, TargetAudioKbps ceiling + NULL semantics). One test for AudioComplete=False/True. One test confirming MaxAudioChannels lives on AudioNormalizationConfig (assert no `MaxAudioChannels` column on `Profiles`). |
| `Tests/Contract/TestContainerComplianceBar.py` (NEW) | One test per container in {mp4, mkv, m4v, mov}. One negative test confirming webm is non-compliant. |
| `Tests/Contract/TestProfileCascadeResolution.py` (NEW) | Cascade tests: show override resolves to assigned profile; null override falls through to SystemSettings default; Draft profiles never resolve (assert HTTP 400 or empty). |
| `Tests/Contract/TestProfileLifecycle.py` (NEW) | Draft -> Finalize -> Locked transitions. Attempt PUT on `Profiles.TargetVideoKbps` of a Draft=FALSE row -> HTTP 400. Attempt to set a Draft profile as Default -> HTTP 400. `Copy as new draft` produces a Draft=TRUE clone with editable fields. |
| `Tests/Contract/TestWorkBucketDerivation.py` (NEW) | One test per cell of the generated-column truth table, including all-NULL, partial-NULL, and steady-state-NULL (all true). |
| `Tests/Contract/TestComplianceIdempotency.py` (NEW) | The three surface queries (AudioFixOnly -> Transcode regression, Remux -> Transcode regression, AudioFixOnly -> Remux regression) must each return 0. Run against live DB post-cutover. |
| `Tests/Contract/TestE2EPerBucket.py` (REUSED from harness-drift-fixes) | All 4 slow E2E tests pass green against live worker fleet. This is the bucket-correctness gate. |
| `Tests/Contract/TestCrossVerticalLeak.py` (NEW) | Greps `Features/ContainerFormat/ContainerVertical.py` for `AudioCodec` -- assert no reference. Greps `Features/VideoEncoding/VideoVertical.py` for `EstimatedSavings`, `MinSourceBpp`, `TranscodedByMediaVortex` -- assert no references. Greps `Features/AudioNormalization/AudioVertical.py` for `MaxAudioChannels` -- assert no reference (it's on the config gate, not the vertical). |
| `Tests/Contract/TestComplianceSummaryEndpoint.py` (NEW) | `GET /api/MediaFile/<id>/ComplianceSummary` returns the joined profile + audio-policy cascade for one file; shape includes the three booleans, the bucket, and the bucket's planned operations. |

## Reference

- `Features/TranscodeQueue/transcode-vs-remux-routing.feature.md` -- the existing doc this spec consolidates.
- `Features/AudioNormalization/audio-normalization.feature.md` -- the loudness + dual-track contract this spec defers to.
- `Features/WorkBucket/work-bucket.feature.md` -- pure consumer of the generated column.
- `.claude/directives/closed/2026-06-21-compliance-rip.md` -- the prior rip that established the three-vertical structure.
- `.claude/directives/closed/2026-06-21-vertical-column-ownership-test.md` -- enforces per-vertical column ownership; this spec respects it.
- `Features/VideoEncoding/VideoVertical.py` -- the file that gets simplified the most (drops `_EstimatedSavingsMB`, `_IsAlreadyEfficient`, `MvTrusted`).
- `Features/AudioNormalization/AudioVertical.py` -- adds the per-profile codec/channels/bitrate check; keeps the upstream undecidable cascade.
- `Features/ContainerFormat/ContainerVertical.py` -- drops `AcceptableAudioCodecsCsv`; check collapses to a single column comparison.
