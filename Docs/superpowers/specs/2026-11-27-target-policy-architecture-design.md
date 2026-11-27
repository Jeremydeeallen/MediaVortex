# Target Policy Architecture (transcode decision layer)

**Status:** approved design, 2026-11-27. Supersedes the decision-layer parts of `2026-10-28-xxx-stash-cull-audio-design.md` Units 0, 2 and 3. Unit 4 (cull) is unchanged and follows this program.
**Evidence:** `knob-inventory.md` and `branching-audit.md` (session scratchpad 2026-11-26, copied into `Docs/superpowers/audits/2026-11-26-*.md` by Phase 0).

## 1. Goal

A file's target (what it should become) is never stored and never has two definitions. Facts are probed and stored; policy is operator data with one home per fact and a GUI control; everything derived is computed at read by one function. The pipeline shape is fixed: bucket -> label -> stage -> verify -> re-bucket. A new library, codec, frame-rate class, encoder, or tier is an INSERT. After this program, a change to encode policy is a `/settings` edit, and a bug in the decision layer is a data error visible on `/Work/Unclassified`, not a code path.

## 2. Why the current design keeps forcing refactors

Measured 2026-11-26 on `6d06ee9d`:

- 18 facts have two or more authorities (loudness target x3, audio codec/bitrate x6, profile choice x6, content class x3, target resolution x3, target kbps x4, container x4, quality-test switch x4, VMAF threshold x2, retry budget x2, processing-mode flags x2, ...).
- 8 functions answer "which profile", 9 "target kbps", 9 "target resolution", 7 "which audio tracks". Compliance judges by tier; the encoder encodes by `AssignedProfile`; they can disagree.
- `MediaFiles.AssignedProfile` is policy and derived at once. It has 4 write paths, 3 of which bypass the cascade, one of which is the cascade itself (`RecomputeForFiles` persists a fallback profile that does not exist).
- 252 branches in the decision layer pick a code path from data (library tier null, profile name, codec, mode). 112 silent defaults. 63 duplicate lookups.
- Encoder knobs on `Profiles` are inert for 57,116 of 57,168 files; `WorkerEncoderResolver` overrides them from code dictionaries.
- The ladder key ignores frame rate: 8,000 kbps scored VMAF 90.4 at 59.94 fps and 98.9 at 29.97 fps.
- 12 dead columns across policy tables; 39 dead `SystemSettings` keys; `KeepSource` has no reader; a smoke test replaced a library file.
- Found by the 2026-11-27 completeness review: the transcode claim SQL (`TranscodeQueueRepository.ClaimNextPendingJob`) joins `Profiles` on `AssignedProfile` and gates on `p.codec` / `p.usenvidiahardware` / `p.useintelhardware`, so a file with a NULL or stale profile can never be claimed; the `WorkBucket` generated column carries the D7 terminal rule (`TranscodedByMediaVortex AND HasDialogBoostTrack -> 'Compliant'`) while `VideoVertical` is documented as its home; `CodecFlags` and `CodecParameters` are a third encoder-knob home (read by `ProcessTranscodeQueueService` and `SvtAv1EncoderArgsStrategy`) absent from the knob inventory; `VmafConfidenceStats.ProfileId` cascades on `Profiles` delete.

Each past directive fixed one symptom inside this shape and added a reader or a stored value. The shape, not the fixes, is the cause.

## 3. Structural principles (how the design prevents recurrence)

These are structures, not rules. Each makes a wrong state unrepresentable.

| Principle | Structure |
|---|---|
| Three kinds of data, never mixed | Facts live on `MediaFiles` (probe/scan writers only). Policy lives in the tables of section 4, each column edited by one `/settings` control. Derived values are not stored; the only stored derived columns are `VideoCompliant`, `AudioCompliant`, `ContainerCompliant` (+ generated `WorkBucket`, `IsCompliant`), maintained by writer-owns-cascade. `WorkBucket` is exactly `CASE WHEN TranscodedByMediaVortex THEN 'Compliant' WHEN any <Dim>Compliant IS NULL THEN 'Unclassified' WHEN all three THEN 'Compliant' WHEN NOT VideoCompliant THEN 'Transcode' WHEN NOT ContainerCompliant THEN 'Remux' ELSE 'AudioFix' END`; the D7 terminal rule lives in that expression and nowhere else (asserted whole by `TestWorkBucketGeneratedColumn`) |
| One definition of "target" | SQL VIEW `MediaFileTargets` (section 5). Python, tests, GUI and audits read the view. There is one definition because there is one object |
| Consumers cannot fetch policy | `TargetResolver` returns a frozen `Target`. Compliance verticals, admission, command composer, disposition decider and placement hand-off take `Target` as an argument and hold no repository. Only `Features/Policy/` depends on the policy tables |
| No code-side knobs | Encoder knobs are rows in `EncoderSettings`; the override dictionaries are deleted. The mode registry reads `ProcessingModes`; the code mirror is deleted |
| Judge and encode agree | Both read `Target.Tier`. An override is a tier. A profile-level override has no representation |
| No silent defaults | `Target` fields are non-optional. An unresolvable file is `Undecided(reason)` at the view. Consumers never see a partial target |
| Review is a state | `Hold` is a disposition. The staged output is retained; the operator resolves it. Smoke tests run on copies and end in `Hold` |
| Backstop tests, few | `TestTargetAuthority` (only `Features/Policy/` touches policy tables), `TestKnobInventory` (every policy column has a reader and a `/settings` control), `TestFailLoud` decision-layer baseline = 0, `TestPipelineShape` (D2 labels, D4 CASE, hand-off byte-identical to the flow doc). They catch what structure cannot: a new table added outside Policy, a column without a GUI |

## 4. Policy model (one home per fact)

### 4.1 Library and genre

- `StorageRoots`: `DefaultQualityTier INT NOT NULL`, `DefaultContentClass TEXT NOT NULL CHECK (live_action|animation)`, `GenreSource TEXT NULL`, `ReviewBeforeReplace BOOL NOT NULL DEFAULT FALSE` (new). Drop `Description`, `CreatedAt` (never referenced). Every library is tiered; the untiered code path ceases to exist.
- `GenreQualityTiers`: `Genre`, `QualityTier INT NULL`, `ContentClass TEXT NULL`. Aggregation (one place, the view): tier = MAX over the file's genres with a tier, else library tier; class = the single distinct explicit class among the file's genres, else library class; two different explicit classes -> `Undecided('ContentClassConflict')` and the pair is listed on `/settings`. Drop `LastUpdated` (written, never read).

### 4.2 Overrides

- New `TargetOverrides(Id, StorageRootId, Scope CHECK (series|file), Key TEXT, QualityTier INT NOT NULL, SetBy TEXT, SetAt TIMESTAMP)`, UNIQUE (StorageRootId, Scope, Key). `Key` = first `RelativePath` segment for series, `MediaFiles.Id` text for file. Precedence in the view: file > series > genre > library.
- Replaces `SeriesProfiles` (218 rows: migrate `AssignedProfile` name -> that profile's `QualityTier`; drop `TargetResolution`, never read) and every hand-set `AssignedProfile` whose source is `operator` or `manual_sql` (migrate to file-scope rows). Bulk/backfill-sourced assignments are derived values and are dropped, not migrated.
- Editing: `/Work/<bucket>` series dropdown writes a series override (tier labels, not profile names); the per-file control on `/Work` and `/Optimization` writes a file override. Both show the resolved tier next to the control.
- Requeue escalation is a file override: ST7 `Requeue` upserts `TargetOverrides(file, Key=MediaFileId, QualityTier=Tier+1, SetBy='requeue:<AttemptId>')`. Judge and encode then agree the file needs the higher tier, which is also its correct compliance verdict. No per-queue-row or per-attempt tier exists.

### 4.3 Tier recipe and acceptance

- `Profiles` becomes one row per tier (`QualityTier UNIQUE`, 5 rows; the 4 unused STREAMING profiles are deleted): `QualityLabel`, `QualityTestRequired BOOL`, `VmafMin NUMERIC NOT NULL`, `VmafMax NUMERIC NULL` (null = no ceiling), `HeldFrameDetectionThreshold`, `HeldFrameP25Min`, `HeldFrameMeanMin`, `LiveActionP10Min`. Seeded from today's `PostTranscodeGateConfig` row. The five tier rows keep their `Id` and `ProfileName`; `TranscodeAttempts.ProfileName` keeps receiving the tier row's name so dashboards and failure views that join attempt history to `Profiles` stay valid.
- Dropped from `Profiles`: `Codec, Preset, Tune, Multipass, RateControlMode, PixelFormat, SpatialAq, TemporalAq, WeightedPred, LowPower, UseNvidiaHardware, UseIntelHardware, AqStrength, FilmGrain, CodecFlagsId, YadifMode, YadifParity, YadifDeint, AudioCodec, AudioBitrateKbps, AudioChannels, AudioFilter, Container, FastStart, TargetAudioKbps, TargetVideoKbps, TargetResolutionCategory, AllowUpscale, StreamCodecName, Family, ContentClass, Draft, Active, SortOrder, Description`. Every one is either dead, inert under the code overrides, or a second home for a fact owned elsewhere.

### 4.4 Ladder

- `ProfileThresholds` is renamed `LadderCells`, keyed `(QualityTier, ContentClass, SourceResolution, FrameRateClass)` UNIQUE. Columns: `TargetResolution` (text category, equals source when no downscale), `TargetKbps INT NOT NULL`, `IcqQ INT NULL`. Nothing else.
- New `FrameRateClasses(Name TEXT PK, MaxFps NUMERIC)`: `standard` 30.0, `high` 120.0. A file's class = first row with `FrameRate <= MaxFps` ordered by MaxFps. Seed `high` cells = `standard` cells with `TargetKbps` x 1.5 (operator tunes on `/settings`; the seed cites this spec section as evidence).
- Dropped: `Under30MinMB, Under65MinMB, Over65MinMB, VideoBitrateKbps, AudioBitrateKbps, FallbackVideoBitrateKbps, FallbackAudioBitrateKbps, Quality, KeepSource, ContainerType, SourceBitratePercent, MinBitrateKbps, MaxBitrateKbps, Gop, RcLookahead, BFrames, BRefMode, ScaleHeight, MaxBitrateMultiplier, Qsv*` (encoder knobs move to 4.5; the rest are dead or duplicates).

### 4.5 Encoder settings

- New `EncoderSettings(Encoder CHECK (av1_nvenc|av1_qsv|libsvtav1), QualityTier, Preset TEXT, Tune TEXT, Multipass TEXT, RateControl TEXT, MaxRateMultiplier NUMERIC, BufSizeMultiplier NUMERIC, SpatialAq INT, TemporalAq INT, PixelFormat TEXT, Gop INT, RcLookahead INT, BFrames INT, BRefMode TEXT, QsvExtBrc INT, QsvAdaptiveI INT, QsvAdaptiveB INT, QsvLookAheadDepth INT, QsvBStrategy INT, QsvTileCols INT, QsvTileRows INT)`, UNIQUE (Encoder, QualityTier). Seeded from today's `WorkerEncoderResolver` dictionaries and `ProfileThresholds` QSV columns, so the first encode after the change is byte-identical to the last before it (golden test, section 9).
- The worker's encoder = `Workers.nvenccapable` -> `av1_nvenc`, else `qsvcapable` -> `av1_qsv`, else `libsvtav1`. One function in `Features/Policy/EncoderSelector.py`; `WorkerEncoderResolver`, `HwAccelResolver` worker reads and the `Profiles.Codec == 'av1'` guard are deleted. The two capability flags are written by the deploy-time probe (`deploy-baremetal-worker.py` runs `Scripts/ReconcileNvencCapability.py` / `ReconcileQsvCapability.py` after restart); nothing else writes them.
- The transcode claim reads no policy: `ClaimNextPendingJob` drops the `Profiles` join and the `p.codec` / `p.usenvidiahardware` / `p.useintelhardware` gates; worker eligibility is `BuildClaimPredicate` (capability flag, `Status`, in-flight cap) plus `ProcessingModes.RequiresInterlacedFilter` vs `Workers.AcceptsInterlaced`. `ProcessingModes.RequiresProfileGates` is dropped with the gates (`claim-authority.md`, `db-is-authority.md`).
- `CodecFlags` and `CodecParameters` are folded into `EncoderSettings`: rows that libsvtav1 reads become the `libsvtav1` encoder rows' columns; both tables and their readers are deleted. Variant runs (`multi-variant-testing`) pass an explicit per-attempt `EncoderSettings` delta; they never edit a policy row.
- Deinterlace: `yadif=1:1:1` stays the one constant in `VideoFilterBuilder`; the dead `Yadif*` columns are dropped.

### 4.6 Audio

- `AudioNormalizationConfig` keeps scope rows (`global`, `library`, `folder`, `item`) with `Enabled`, `LoudnessTolerance`, `UngainablePolicy`, `EnableSpeechLanguageDetection`, `LanguageDefault`. Drop `EmitTracks` JSON, `TargetLra`, `PreVerticalReNormalizePolicy`.
- New `AudioPolicyTracks(PolicyId FK, Ordinal, Label, Codec, BitrateKbps, BitrateIsPerChannel BOOL, Channels INT NULL (null = source), TargetLufs, TargetLra NULL, TargetTruePeakDbtp, IsDefault, LanguageFilter)`. Seeded from the live `AudioComplianceRules` values (Original: opus 48/ch -23 TP -2; Dialog Boost: opus 64 -14 LRA 9) so TV output is unchanged.
- `AudioComplianceRules` keeps engine constants only: `AcceptableAudioCodecsCsv`, `SampleLimitHeadroomDb`, `Track1VocalsRmsFallbackDbfs`, `VocalsBoostDb`, `InstrumentalAttenDb`, premix compressor and dynaudnorm knobs, `SourceMeasureTargetLra`. Drop `TargetIntegratedLufs, TargetTruePeakDbtp, DialogBoostTargetLufs, DialogBoostTargetLra, Track0Codec, Track1Codec, Track0BitratePerChannelKbps, Track0MinPerChannelKbps, Track1StereoBitrateKbps`.
- Track emission (AudioFix stage): the emitter iterates `AudioPolicyTracks` for the resolved policy; `Original` = one loudnorm block per kept source stream at the track's targets; `Dialog Boost` = the Demucs block; the Demucs pre-pass runs only when the policy has a `Dialog Boost` track. The Copy path (Transcode and Remux labels) stream-copies when the source codec is in `AcceptableAudioCodecsCsv`, else converts to the policy's default track codec and bitrate.
- Audio compliance: labels of the latest successful attempt's emitted tracks equal the policy's labels per kept language, and each track's achieved integrated loudness is within `LoudnessTolerance` of its target. `HasDialogBoostTrack` remains a fact column; `no_dialog_boost` ceases to exist. `AudioVertical` has no side effects (the admission gate's re-measure and review-queue writes move to the admission stage where they belong).
- Delete `AudioDispositionResolver.ResolveForTrack`, `Context['AudioStreamIndex']`, the dead `SystemSettings` audio keys, `TranscodeQueue.AudioSlotOverride`.

### 4.7 Container

- `ContainerComplianceRules`: `AcceptableContainersCsv`, `OutputContainer TEXT NOT NULL DEFAULT 'mp4'`, `FastStart BOOL`. Drop `AcceptableAudioCodecsCsv` (never read; audio owns codecs). `ContainerSlot` and `OutputFilenameBuilder` read `OutputContainer`; the hardcoded `mp4` and the four other container homes are deleted.

### 4.8 Ceiling

- `VideoComplianceThresholds(ResolutionCategory, Multiplier)` unchanged. Video compliant when `source kbps <= LadderCell.TargetKbps x Multiplier(source resolution)`. Codec plays no part (operator decision 2026-10-06, now the only path). D7 (our outputs are final; re-acquire to change them) is the first branch of the `WorkBucket` generated column (section 3); no vertical reads `TranscodedByMediaVortex`. The audio half of today's expression (`AND HasDialogBoostTrack`) is removed in Phase 3 once `AudioCompliant` expresses tracks-match-policy, so the column reads `TranscodedByMediaVortex -> 'Compliant'` alone.

### 4.9 Verification

- `PostTranscodeGateConfig` is renamed `VerificationConfig` and keeps `MaxRequeueAttempts`, `MinOutputSavingsPercent` (new, seeded 0: a larger output is rejected in the decider, not after commit). Drop `VmafAutoReplaceMinThreshold, VmafAutoReplaceMaxThreshold, FileReplacementCanReplaceThreshold, WhenVmafUnavailable, WorkerHeartbeatWindowSec, QualityTestEnabled, MinConfidenceSampleCount, MinConfidencePassRate, SigmaMargin`. The smart-confidence skip (Replace without VMAF from bucket statistics) is deleted: an unverified replace contradicts section 6. `ProcessingModes.RequiresVmaf/RequiresNvencGate/BucketName` dropped.
- One retry budget: `FailureBudgetService` stays; `RetryBudgetService` is deleted; `MaxRequeueAttempts` is its cap.
- `VmafConfidenceStats` (the smart-confidence store, FK cascade on `Profiles`) and `SystemSettings.BitratePerPixelBoundaries` are dropped with the skip.
- `Hold` is non-terminal for disk: `RetainInprogressPolicy.ShouldRetain('Hold')` is TRUE; `DispositionDispatcher._MaybeCleanupArtifacts`, `CrashRecoveryService` and `OrphanCleanupService` leave `TemporaryFilePaths` rows and `.ip` files of attempts with `Disposition='Hold'` alone. The Override API's Replace/Reject resolution is the only path that releases them.

### 4.10 SystemSettings and MediaFiles

- Delete the 39 never-referenced keys, `DefaultProfileName`, `CRFOverride_*` rows, `ExclusionDirectories`, and the audio/bitrate keys listed in the inventory as dead.
- `MediaFiles`: drop `AssignedProfile`, `AssignedProfileSource`, `KeepSource`. `TranscodeFiles.SuccessfullyTranscoded` is dropped in favour of `MediaFiles.TranscodedByMediaVortex` (one fact).

## 5. The resolver

SQL VIEW `MediaFileTargets` (one row per `MediaFiles` row):

```
MediaFileId, StorageRootId,
Tier            -- COALESCE(file override, series override, MAX(genre tier), library tier)
TierOrigin      -- 'file_override' | 'series_override' | 'genre=<name>' | 'library'
ContentClass    -- single explicit genre class, else library class; NULL on conflict
ClassOrigin, FrameRateClass, SourceResolution,
TargetResolution, TargetKbps, IcqQ,            -- from LadderCells
QualityLabel, QualityTestRequired, VmafMin, VmafMax, HeldFrame*, LiveActionP10Min,   -- from Profiles
AudioPolicyId,                                  -- item > folder > library > global
OutputContainer, AcceptableContainersCsv, AcceptableAudioCodecsCsv,
CeilingMultiplier, ReviewBeforeReplace,
Undecided TEXT  -- NULL when every field above is non-null; else the first missing input name
```

`Features/Policy/TargetResolver.py` reads one row from the view and returns `Target` (frozen dataclass, all fields non-optional) or `Undecided(Reason)`. It is the only Python that reads the view for decisions. The view is the executable SSoT and is asserted against `transcode.flow.md` D4 by `TestPipelineShape`.

View mechanics: `MediaFiles.Genres` is CSV text, aggregated with `unnest(string_to_array(Genres, ','))`; `FrameRateClass` is NULL (so `Undecided('FrameRate')`) when `FrameRate` is NULL; `AudioPolicyId` precedence is `item` (MediaFileId) > `library` (StorageRootId) > `global`, the unused `folder` scope being dropped in Phase 3 unless rows exist then. `TargetResolver.ResolveMany(Ids)` reads the view once per batch for `RecomputeForFiles`.

`Undecided` is stored as NULL: a vertical handed `Undecided(reason)` writes `<Dim>Compliant = NULL, <Dim>CompliantReason = reason`; the generated column makes that row `Unclassified`, which is how a data error reaches `/Work/Unclassified`. Admission refuses an `Undecided` file with that reason; the composer never sees one.

## 6. Pipeline after the change

```
SCAN -> PROBE -> RECOMPUTE -> QUEUE -> TRANSCODE -> DISPOSITION -> VERIFY -> ACTION
 ST1     ST2       ST4         ST5       ST6          ST7          ST8       ST9
```

ST3 ASSIGN is deleted (stable IDs are not renumbered). `ingest.flow.md` ST5 Classify is deleted; genre sync stays at the end of scan and moves to `Features/Policy/`.

| Stage | Reads `Target` for | Change |
|---|---|---|
| ST4 RECOMPUTE | the three verticals: `Evaluate(Facts, Target) -> Verdict`, pure; `PriorityScore` estimate = `Target.TargetKbps` + default audio track `BitrateKbps` (x channels when per-channel) | verticals lose their repositories and side effects; `_EncodeTargets` reads `Target`, not `ProfileThresholds` |
| ST5 QUEUE | `AddJob(MediaFileId, Label=None)`; gates: upscale (TargetResolution vs source), marginal savings (`MinTranscodeSavingsMB`, 20% / 150 MB), failure budget, terminal, audio-policy admission (re-measure / review-queue writes happen here) | `ProfileId`, `QualityTier`, `QualityLabel` parameters and the three profile write paths are deleted (BUG-0124 becomes unrepresentable) |
| ST6 TRANSCODE | `CommandComposer.Build(Facts, Target, EncoderSettings(worker encoder, Target.Tier), Label)` | slot shape unchanged; VideoSlot reads a row, not a dict; AudioSlot reads policy tracks; ContainerSlot reads `OutputContainer` |
| ST7 DISPOSITION | `Decide(AttemptFacts, Target) -> Replace | Hold | Requeue | Reject`, pure, no repository | adds `Hold`; size check moves here; exception propagates (no `-> Pending`) |
| ST8 VERIFY | unchanged (VMAF / checksum) | thresholds come from `Target` |
| ST9 ACTION | Replace unchanged; `Hold` retains `.ip` and writes `Disposition='Hold'`; Requeue upserts the file override `Tier+1` (section 4.2) and re-adds the job; Reject per `RetainInprogressPolicy` | `KeepSource` deleted; Override API resolves `Hold` to Replace/Reject |

Decision table for ST7:

| Condition (in order) | Disposition |
|---|---|
| attempt failed | Reject / TranscodeFailed |
| output size >= source x (1 - MinOutputSavingsPercent) | Reject / NoSavings |
| `QualityTestRequired = FALSE` | Hold if `ReviewBeforeReplace` else Replace / QualityTestNotRequired |
| VMAF missing | Pending / AwaitingVmaf (QT row created) |
| held-frame content: P25 < HeldFrameP25Min or mean < HeldFrameMeanMin; live action: P10 < LiveActionP10Min; or mean < VmafMin | Requeue / VmafBelowMin (budget permitting, else Reject / RetryBudgetExhausted; no `LadderCells` row at Tier+1, i.e. Tier 5, -> Reject / QualityCeilingReached) |
| `VmafMax` set and mean > VmafMax | Hold / VmafAboveMax |
| otherwise | Hold if `ReviewBeforeReplace` else Replace / VmafPassed |

## 7. GUI (one editor per fact)

`/settings` Transcoding card: library table (tier, class, genre source, review-before-replace), genre table (tier, class, conflict list), tier table (`Profiles`: label, QT required, VMAF min/max, held-frame thresholds), ladder grid per class with a frame-rate-class tab, encoder settings grid per encoder, ceiling multipliers, verification config. `/AudioNormalization`: scope rows with a tracks sub-table (`AudioPolicyTracks`). `/Admin/Compliance`: container rule + audio engine constants. `/Work/<bucket>`: tier override controls (series, file) showing the resolved tier. `/QualityTesting`: `Hold` rows with stills, VMAF percentiles, Replace / Reject buttons (the existing Override API).

## 8. Migration (data, idempotent, one script per phase)

| From | To | Rule |
|---|---|---|
| `SeriesProfiles.AssignedProfile` | `TargetOverrides(series)` | profile name -> `Profiles.QualityTier` |
| `MediaFiles.AssignedProfile` with source `operator`/`manual_sql` | `TargetOverrides(file)` | same mapping; other sources dropped (derived) |
| `WorkerEncoderResolver` dicts + `ProfileThresholds.Qsv*`, `MaxBitrateMultiplier` | `EncoderSettings` | one row per (encoder, tier) |
| `ProfileThresholds` rows | `LadderCells(standard)` + `LadderCells(high)` | high = standard x 1.5 kbps |
| `PostTranscodeGateConfig` thresholds | `Profiles` acceptance columns | same value on every tier row |
| `AudioComplianceRules` track columns | `AudioPolicyTracks` for the global policy | Original + Dialog Boost as today |
| `StorageRoots.DefaultQualityTier NULL` (xxx) | `3`, class `live_action`, `ReviewBeforeReplace TRUE` | operator-confirmed in Phase 6 |

Every migration is followed by the same-day invariant check: TV and Movies `VideoCompliant` / `AudioCompliant` / `ContainerCompliant` counts identical before and after; the golden TV ffmpeg command (video and audio) byte-identical.

## 9. Acceptance criteria (program level)

1. `grep -rn "AssignedProfile" --include=*.py --include=*.html Features/ Core/ Repositories/ WorkerService/ WebService/ Services/ Templates/ Scripts/*.py Scripts/Smoke/` returns 0 (one-off dated migrations under `Scripts/SQLScripts/` excepted); `\d MediaFiles` and `\d MediaFilesArchive` have no `AssignedProfile`, `AssignedProfileSource`, `KeepSource`.
2. Exactly one Python module reads `StorageRoots`, `GenreQualityTiers`, `TargetOverrides`, `Profiles`, `LadderCells`, `EncoderSettings`, `FrameRateClasses` for decisions (`TestTargetAuthority`).
3. `TestFailLoud` baseline for `Features/Policy`, the three verticals, `Features/TranscodeJob/Emit`, `Features/QualityTesting/Disposition`, `Features/FileReplacement` is 0.
4. Every column of every policy table has a `/settings` control and a decision reader (`TestKnobInventory`); the inventory's dead-column list is empty.
5. Golden tests: one TV fixture's Transcode and AudioFix commands are byte-identical before and after each phase; TV and Movies compliance counts identical after each migration.
6. Live: a file whose series override is changed on `/Work` recomputes within one cascade with no reassign step; a `/settings` ladder edit changes `VideoCompliantReason` on an affected file with no code restart.
7. Live, fleet: one xxx 4K >30 fps file and one <=30 fps file encode on dot (NVENC) and wakko (QSV) from COPIES, land in `Hold`, show VMAF and stills on `/QualityTesting`, and are resolved by the operator.
8. `ARCHITECTURE.md` Vertical Roster names `Policy` and no `ContentClassifier`; `## Gap to Target` is empty; `transcode.flow.md` D2/D4/D6/D7 match the view and the labels.
9. A `grep` for `WorkerEncoderResolver`, `ProcessingModeMetadata`, `RetryBudgetService`, `SmartConfidence`, `VmafConfidenceStats`, `GetKeepSourceSetting`, `ReassignTierProfiles`, `ContentClassificationRules`, `SeriesProfiles`, `CodecFlags`, `CodecParameters`, `EmitTracks`, `no_dialog_boost` across the production tree returns 0; `ClaimNextPendingJob` SQL contains no `Profiles`.

## 10. Decisions made (reversals flagged)

- REVERSAL of 2026-10-06 "hand-set profile changes encode, never bucket": an override is a tier; judge and encode agree. Reason: the split is the one place the system could hold two targets for one file.
- REVERSAL: encoder knobs are data (`EncoderSettings`), not code overrides. Reason: 10 inert GUI columns and an invisible override.
- Above-max VMAF is `Hold`, not `Reject`. Reason: the output is usable; the operator decides.
- Smart-confidence skip deleted. Reason: replaces without verification; contradicts the review model.
- Frame-rate classes: two (`standard` <= 30, `high` > 30), boundary as data. Reason: measured 8-point VMAF gap; two classes cover 57,151 of 57,168 files.
- Genre class conflict is undecided, not resolved by order. Reason: fail-loud; the operator fixes the data once.
- D7 terminal state retained. Reason: product decision to never re-encode our own output.
- D8 source deletion on Replace retained; `Hold` is the review mechanism. `KeepSource` deleted rather than revived.
- xxx library: tier 3, live_action, `ReviewBeforeReplace TRUE` until the operator has judged the first fleet outputs, then FALSE.
- Requeue escalation is a stored file override, not a queue-row or attempt field (2026-11-27 review). Reason: the only other representation would be a second stored target.
- `Hold` artefacts are exempt from every cleanup sweeper (2026-11-27 review). Reason: a Hold whose `.ip` was swept is a Reject the operator never saw.

## 11. Out of scope

Cull vertical (Unit 4), Stash, worker lifecycle and deploy, scan/probe internals, Jellyfin notify, ClipBuilder, intro detection. Changing TV or Movies encode results: they are verified unchanged by the golden tests.
