# Knob inventory: transcode decision layer (2026-11-26, repo @ 6d06ee9d)

## SUMMARY (25 lines)
1. Counts per table (READ = READ-AT-DECISION, DISP = READ-ONLY-FOR-DISPLAY, WNR = WRITTEN-NEVER-READ, NEVER = NEVER-REFERENCED):
   - Profiles (42): READ 24 / DISP 10 / WNR 8 / NEVER 0.
   - ProfileThresholds (33): READ 23 / DISP 6 / WNR 4.
   - SeriesProfiles (7): READ 0 / DISP 3 / WNR 2 / NEVER 2.
2. - StorageRoots (8): READ 6 / NEVER 2.
   - GenreQualityTiers (4): READ 3 / WNR 1.
   - ContentClassificationRules (13): READ 10 / DISP 1 / NEVER 2.
3. - AudioNormalizationConfig (12): READ 8 / DISP 2 / WNR 2.
   - AudioComplianceRules (21): READ 20 / WNR 1.
   - ContainerComplianceRules (4): READ 2 / DISP 1 / WNR 1.
4. - VideoComplianceThresholds (4): READ 2 / WNR 1 / NEVER 1.
   - PostTranscodeGateConfig (12): READ 9 / DISP 3.
   - ProcessingModes (7): READ 4 / NEVER 3.
   - ResolutionTiers (7): READ 5 / NEVER 2.
   - SystemSettings (80 keys): READ 37 / DISP 4 / NEVER 39. "NEVER" here means no code references the key by name; the generic "All settings" table on Settings.html still lets you edit them.
5. Dead columns:
   - Profiles: YadifMode, YadifParity, YadifDeint, CodecFlagsId, AudioChannels, AudioFilter, FastStart, TargetAudioKbps.
   - ProfileThresholds: SourceBitratePercent, MinBitrateKbps, MaxBitrateKbps, ScaleHeight.
   - SeriesProfiles: TargetResolution, Id (plus the two date columns, which are written but never read).
6. - ContainerComplianceRules.AcceptableAudioCodecsCsv; AudioNormalizationConfig.PreVerticalReNormalizePolicy.
   - ProcessingModes: BucketName, RequiresVmaf, RequiresNvencGate.
   - StorageRoots: Description, CreatedAt. ContentClassificationRules: Source, LastUpdated.
   - MediaFiles.KeepSource: its only reader, TranscodeJobRepository.GetKeepSourceSetting, has no callers.
   - TranscodeQueue.AudioSlotOverride is never referenced. MediaFiles.LastTranscodeOutcome does not exist.
7. Columns that are read but change nothing:
   - PostTranscodeGateConfig.WhenVmafUnavailable and WorkerHeartbeatWindowSec only reach the audit log; the decider never branches on them.
   - AudioNormalizationConfig.EmitTracks fields Codec/Bitrate/BitDepth/Channels/SampleRateHz/IsDefaultTrack/LanguageFilter are ignored by the audio emitter.
8. Hard-coded overrides make these Profiles knobs inert for 57,116 of 57,168 files. WorkerEncoderResolver applies NVENC_OVERRIDES / QSV_OVERRIDES whenever Codec='av1' (all five "AV1 Tier N" profiles). Inert as a result: Codec, Preset, Tune, Multipass, RateControlMode, SpatialAq, TemporalAq, PixelFormat, UseNvidiaHardware, UseIntelHardware, plus ProfileThresholds.MaxBitrateMultiplier. Because rate control is forced to 'vbr', the IcqQ ladder, Quality and SystemSettings CRFOverride_* also have no effect for those profiles.
9. Facts with two or more authorities:
   - (a) Loudness target: AudioComplianceRules.TargetIntegratedLufs -23 and DialogBoostTargetLufs -14 (what is emitted) vs EmitTracks[].TargetLufs -23 for both tracks (what admission assumes) vs SystemSettings.TargetLoudness -23 (dead).
10. - (b) Loudness range: EmitTracks[].TargetLra 11 vs DialogBoostTargetLra 9 vs AudioNormalizationConfig.TargetLra NULL vs SystemSettings.MinimumLoudnessRangeLU 11 (dead).
    - (c) True peak: TargetTruePeakDbtp -2 vs SystemSettings.TruePeak -2 (dead) vs a hard-coded -2 in AudioStrategyClassifier.
11. - (d) Audio codec and bitrate, six sources: AudioComplianceRules Track0/1 codec (opus, emitted) vs EmitTracks (aac/128) vs Profiles AudioCodec/Bitrate/Channels (libopus/128/2) vs code overrides (libopus/192/6) vs ProfileThresholds.AudioBitrateKbps 192 vs SystemSettings.DefaultAudioBitrate 80 (dead).
    - (e) Acceptable audio codecs: AudioComplianceRules (includes opus, read) vs ContainerComplianceRules (no opus, editable in the GUI, never read).
12. - (f) KeepSource: MediaFiles (117 rows TRUE, no live reader) vs ProfileThresholds (all FALSE, display only; the threshold PUT/POST routes reset it to FALSE).
    - (g) Whether to run a quality test: Profiles.QualityTestRequired (all TRUE) vs PostTranscodeGateConfig.QualityTestEnabled vs ProcessingModes.RequiresVmaf (dead) vs Workers.QualityTestEnabled.
13. - (h) VMAF "good enough to replace": VmafAutoReplaceMinThreshold 90 vs FileReplacementCanReplaceThreshold 90.
    - (i) Encoder knobs: the Profiles columns vs the WorkerEncoderResolver code dictionaries (point 8).
14. - (j) Profile choice, six sources: MediaFiles.AssignedProfile (what the encode uses) vs StorageRoots.DefaultQualityTier + GenreQualityTiers (what VideoVertical judges compliance against, ignoring AssignedProfile) vs SeriesProfiles (applied only at set time) vs ContentClassificationRules (only reached on root 3) vs SystemSettings.DefaultProfileName (points at a profile that does not exist) vs AddJobToQueue ProfileId/QualityTier (overwrites without recording a source).
15. - (k) Content class: StorageRoots.DefaultContentClass + GenreQualityTiers.ContentClass (resolved per file, picks the threshold row) vs Profiles.ContentClass (always live_action; used for the VMAF confidence bucket and next-tier lookup) vs ProfileThresholds.ContentClass (row key).
    - (l) Target resolution: TranscodeDownTo vs Profiles.TargetResolutionCategory (NULL on all tier profiles, so next-tier escalation never fires) vs SeriesProfiles.TargetResolution (dead).
16. - (m) Target video bitrate: TargetKbps vs Profiles.TargetVideoKbps vs ProfileThresholds.VideoBitrateKbps vs SystemSettings Default(Fallback)VideoBitrate (dead).
    - (n) Size thresholds: ProfileThresholds Under30/Under65/Over65MinMB (all 0, display) vs SystemSettings keys of the same names (dead).
    - (o) Processing-mode flags: ProcessingModes table vs the ProcessingModeMetadata._METADATA copy in code.
17. - (p) Excluded folders: ExcludedDirectories (read) vs ExclusionDirectories (dead, different value).
    - (q) Deinterlace: Profiles.Yadif* (dead) vs yadif=1:1:1 hard-coded in VideoFilterBuilder.
    - (r) Container output: ContainerComplianceRules vs Profiles.Container/FastStart vs ProfileThresholds.ContainerType vs ContainerSlot, which hard-codes mp4 + faststart.
18. Stats:
    - AssignedProfileSource: bulk_tier_by_root_2026_07_23 35,982; series 9,666; genre_tier 3,321; classifier 3,264; library_default_tier 2,309; operator 2,101; classifier_skip_av1 239; backfill_tv_tier1_2026_08_25 173; NULL 104; test 6; bulk-tier2-already-transcoded-2026-07-21 3.
19. - SeriesProfiles: 218 rows across 3 StorageRootIds (root 1: 211, root 2: 6, root 3: 1). 214 rows have an AssignedProfile; 8 have a TargetResolution, which nothing reads.
    - Frame rate per root: root 1 ≤30fps 47,552 / >30fps 1,929 / null 2; root 2 3,479 / 7 / 1; root 3 3,642 / 552 / 4.
20. - Profiles:
      - 468–471 are STREAMING NVENC/QSV profiles at tiers 1–2, codecs av1_nvenc/av1_qsv, one threshold row each, and no files use them.
      - 475–479 are "AV1 Tier 1–5" (Family ANY, codec av1, 8 threshold rows each).
      - All nine are live_action, Active, finalized (Draft=false), with QualityTestRequired=true.
21. Other dangling or inconsistent data:
    - SystemSettings.DefaultProfileName = 'NVENC AV1 P7 CANARY VBR -720p', which is not in Profiles. The code's last fallback, '_PreMigrationDefault', does not exist either.
    - One SeriesProfiles row references that same missing profile.
    - 237 root-1 files are tagged classifier_skip_av1 but still have AssignedProfile = 'AV1 Tier 1 Efficient'.
22. Settings.html requests SystemSettings keys that are not in the table: TranscodeCoreTier, QualityTestCoreTier, ThermalGateEnabled, ThermalPauseCriticalTemp, ThermalGateMaxTemp.
23. All 19 GenreQualityTiers rows have QualityTier NULL; only Animation has a ContentClass. Roots 1 and 2 have DefaultQualityTier 1, so every TV show and movie is judged against Tier 1. The classifier rules only run on root 3.
24. No setting depends on frame rate. 60fps files get the same TargetKbps as 24fps files; the only use of FrameRate is the bits-per-pixel bucket in DispositionDispatcher._ComputeBitratePerPixelBucket.
25. Caveat: the readers listed are from grep by column name plus reading the key paths. SystemSettings "NEVER" means no reference by key name; a dynamic lookup could exist, but none was found.

---

# FULL REPORT: Knob inventory for the transcode decision layer

## Decision path: who reads what, in order

### When a file is classified, compliance is recomputed, and the file is queued
- **ContentClassifierService.ClassifyAndAssign**
  - Called from MediaProbeBusinessService:154 at probe time.
  - Skips files that already have an AssignedProfile.
  - Then runs FileTierResolver; that only produces a profile when the file's StorageRoot has a DefaultQualityTier.
  - Otherwise walks the ContentClassificationRules.
  - Writes through ProfileAssignmentService.Assign, which calls MediaFilesRepository.WriteAssignedProfile and then QueueManagementBusinessService.RecomputeForFiles.
- **QueueManagementBusinessService.RecomputeForFiles** (line 1568)
  - Runs AudioVertical, VideoVertical and ContainerVertical; each writes its own compliance boolean, and MediaFiles.WorkBucket is generated from those.
  - Then sets AssignedProfile = EffectiveProfileResolver.ResolveProfileName(...). That cascade goes AssignedProfile if finalized and active, else DefaultProfileName, else '_PreMigrationDefault', else NULL.
  - Then sets PriorityScore using _EncodeTargets.
- **VideoVertical.Evaluate**
  - Resolves the content class with ContentClassResolver, then the tier with FileTierResolver.
  - If a tier resolves, it compares source kbps against tier TargetKbps × VideoComplianceThresholds.Multiplier and **ignores AssignedProfile**.
  - Only when no tier resolves does it use AssignedProfile, via GetProfileCodec / GetProfileTarget.
- **AudioVertical.Evaluate** checks AudioComplianceRules.AcceptableAudioCodecsCsv, then AudioPolicyAdmissionGate (AudioNormalizationConfig), then MediaFiles.HasDialogBoostTrack.
- **ContainerVertical.Evaluate** checks ContainerComplianceRules.AcceptableContainersCsv only.
- **TranscodeQueueRepository claim SQL** (around line 305) joins ProcessingModes on ClaimCapabilityFlag, RequiresProfileGates and RequiresInterlacedFilter, and checks Profiles.codec against worker capability.

### When the file is encoded
- **ProcessTranscodeQueueService.GetTranscodingSettings** (line 823):
  - ContentClassResolver gives the content class.
  - EncoderKnobRepository.GetEncoderKnobsForProfile(MediaFile.AssignedProfile, class, MediaFile.Resolution) reads the joined Profiles + ProfileThresholds row. It uses the "encode row", meaning the row at the source row's TranscodeDownTo resolution.
  - If Codec == 'av1', WorkerEncoderResolver.ApplyOverrides replaces the knobs with the NVENC_OVERRIDES or QSV_OVERRIDES dictionary.
  - A SystemSettings CRFOverride_* key, if present, overwrites Quality.
- Emit stage:
  - CommandComposer, VideoSlot (_EmitNvencArgs / _EmitQsvArgs) and the SvtAv1 strategy build the video arguments.
  - VideoFilterBuilder hard-codes yadif=1:1:1.
  - AudioSlot calls AudioFilterEmitter.EmitTracks, which uses **AudioComplianceRules** values, not EmitTracks entries.
  - ContainerSlot hard-codes mp4 +faststart.
- AttemptRecordService writes TranscodeAttempts.QualityTestRequired from Profiles.QualityTestRequired.

### After the encode
- **DispositionDispatcher** feeds PostTranscodeDispositionDecider.Decide with PostTranscodeGateConfig values, a BucketKey built from Profiles.ContentClass, FrameRate and BitratePerPixelBoundaries, then NextTierAdjuster (Profiles.TargetResolutionCategory/Family/QualityTier/ContentClass), then RetryBudgetService (MaxRequeueAttempts).

### GUI pages
- **Settings.html**
  - Profile editor: PATCH /api/profiles/<id>/knobs, PUT/POST /api/profiles, /finalize, /reorder, /copy, threshold POST/PUT.
  - Content Classification Rules: /api/ContentClassification/Rules.
  - Default profile: /api/SystemSettings/DefaultProfile.
  - Transcoding: bitrate ladder, ICQ ladder, video multipliers and confidence settings via /api/SystemSettings/Transcoding.
  - Gate: /api/SystemSettings/PostTranscodeGateConfig.
  - Library tiers: /LibraryTiers. Genre tiers: /GenreTiers.
  - Generic "All System Settings" table.
- **AdminCompliance.html**: /api/ContainerFormat/Rules and /api/AudioNormalization/Rules.
- **AudioNormalization.html**: /api/AudioNormalization/Rules.
- **WorkBucket.html**: series profile via POST/DELETE /api/Work/<bucket>/Series/<sid>/Profile.
- API only, no page calls them: /api/AudioNormalization/Settings (AudioNormalizationConfig), /api/QualityTest/Override (ForceDisposition), /SetCRFOverride.

Throughout the tables below, "inert" means the code path exists but is never hit for current data.

## Profiles (42 columns)
| Column | Type | GUI editor | Decision readers (file:function) | Class |
|---|---|---|---|---|
| Id | bigint | – | TierLadderRepository.GetProfileRow (join); DispositionDispatcher._BuildBucketKey; NextTierAdjuster.Get | READ-AT-DECISION |
| ProfileName | text | Settings (PATCH knobs) | EffectiveProfileResolver._ResolveAssignedProfileName; TierLadderRepository.GetProfileRow/GetTierProfileName; claim SQL join on AssignedProfile | READ-AT-DECISION |
| Description | text | Settings | ProfileRepository.GetAllProfiles (list) | READ-ONLY-FOR-DISPLAY |
| CreatedDate | timestamp | – | ProfileRepository.GetAllProfiles | READ-ONLY-FOR-DISPLAY |
| LastModified | timestamp | – | ProfileRepository.GetAllProfiles | READ-ONLY-FOR-DISPLAY |
| Codec | text | Settings (compliance-locked once finalized) | TierLadderRepository.GetProfileCodec, used by VideoVertical.Evaluate for the codec-match skip; claim SQL `p.codec <> 'av1'`; ProcessTranscodeQueueService.GetTranscodingSettings ('av1' triggers overrides); CommandComposer; VideoSlot._EmitReencode | READ-AT-DECISION (overridden to av1_nvenc/av1_qsv) |
| Preset | bigint | Settings | VideoSlot._EmitNvencArgs/_EmitQsvArgs; SvtAv1EncoderArgsStrategy | READ (overridden to 7 or 1 for av1 profiles) |
| FilmGrain | bigint | Settings | SvtAv1EncoderArgsStrategy.AddFilmGrainParameter (libsvtav1 only) | READ (inert: no libsvtav1 profile) |
| YadifMode | bigint | Settings | EncoderKnobRepository carries it; VideoFilterBuilder hard-codes yadif=1:1:1 | WRITTEN-NEVER-READ |
| YadifParity | bigint | Settings | same | WRITTEN-NEVER-READ |
| YadifDeint | bigint | Settings | same | WRITTEN-NEVER-READ |
| CodecFlagsId | bigint | – | ProfileRepository.CopyProfile copies it only (all NULL) | WRITTEN-NEVER-READ |
| UseNvidiaHardware | bigint | Settings | CommandComposer; HwAccelResolver; VideoSlot; WorkerCapabilityPredicate (claim) | READ (overridden) |
| SortOrder | int | Settings (/profiles/reorder) | ProfileRepository.GetAllProfiles ORDER BY | READ-ONLY-FOR-DISPLAY |
| RateControlMode | text | Settings | VideoSlot._EmitNvencArgs/_EmitQsvArgs | READ (overridden to 'vbr') |
| Tune | text | Settings | VideoSlot._EmitNvencArgs | READ (overridden to 'hq') |
| Multipass | text | Settings | VideoSlot._EmitNvencArgs | READ (overridden to 'fullres') |
| PixelFormat | text | Settings | VideoSlot._EmitReencode | READ (overridden to p010le) |
| AudioCodec | text | Settings (compliance) | EffectiveProfileResolver feeds ComplianceSummaryController (display); finalize gate; AudioSlot does not use it | READ-ONLY-FOR-DISPLAY |
| AudioBitrateKbps | int | not editable (missing from PATCH list) | Becomes EncoderKnobs.AudioBitrateKbps, used only by AttemptRecordService (TranscodeAttempts record); overridden to 192 | READ-ONLY-FOR-DISPLAY |
| AudioChannels | int | not editable (badge display only) | carried in knobs; no emitter reads it | WRITTEN-NEVER-READ |
| AudioFilter | text | not editable (badge display only) | carried in knobs; no emitter reads it | WRITTEN-NEVER-READ |
| Container | text | Settings (compliance) | EffectiveProfile.Container shown in ComplianceSummary; finalize gate; ContainerSlot hard-codes mp4 | READ-ONLY-FOR-DISPLAY |
| FastStart | bool | Settings | carried in knobs; ContainerSlot hard-codes +faststart | WRITTEN-NEVER-READ |
| AqStrength | int | Settings | VideoSlot._EmitNvencArgs | READ-AT-DECISION (all NULL) |
| QualityTestRequired | bool | Settings | AttemptRecordService / ProcessTranscodeQueueService:977 write TranscodeAttempts.QualityTestRequired, read by PostTranscodeDispositionDecider.Decide | READ-AT-DECISION |
| Draft | bool | Settings (/finalize) | ProfileRepository.IsFinalizedActive, used by EffectiveProfileResolver and RecomputeForFiles (a draft profile nulls AssignedProfile) | READ-AT-DECISION |
| Active | bool | Settings | IsFinalizedActive; NextTierAdjuster; WorkBucketController /api/Profiles/Active | READ-AT-DECISION |
| StreamCodecName | varchar | Settings (compliance) | EffectiveProfileResolver feeds ComplianceSummary; finalize gate | READ-ONLY-FOR-DISPLAY |
| TargetResolutionCategory | varchar | Settings (compliance) | NextTierAdjustmentCalculator.NextTierAdjuster.Get (required; NULL on 475–479 so it returns None and the outcome is QualityCeilingReached); DashboardSnapshotService (COALESCE) | READ-AT-DECISION |
| TargetVideoKbps | int | Settings (compliance) | DashboardSnapshotService COALESCE(pt.TargetKbps, p.TargetVideoKbps) | READ-ONLY-FOR-DISPLAY |
| AllowUpscale | bool | Settings (compliance) | EffectiveProfile shown in ComplianceSummary; ScalePolicy never upscales regardless | READ-ONLY-FOR-DISPLAY |
| TargetAudioKbps | int | Settings (compliance) | none: EffectiveProfile.TargetAudioKbps comes from pt.AudioBitrateKbps | WRITTEN-NEVER-READ |
| UseIntelHardware | bigint | Settings | CommandComposer; HwAccelResolver; WorkerCapabilityPredicate | READ (overridden) |
| SpatialAq | int | Settings | VideoSlot._EmitNvencArgs | READ (overridden to 1) |
| TemporalAq | int | Settings | VideoSlot._EmitNvencArgs | READ (overridden to 1) |
| WeightedPred | int | Settings | VideoSlot._EmitNvencArgs | READ-AT-DECISION (all NULL) |
| LowPower | int | Settings | VideoSlot._EmitQsvArgs | READ-AT-DECISION (all NULL) |
| Family | text | not editable | TierLadderRepository.GetTierProfileName (Family='ANY'), GetBitrateLadder/GetIcqLadder; NextTierAdjuster | READ-AT-DECISION |
| QualityTier | int | not editable | GetTierProfileName (used by ContentClassifierService._TierProfile and VideoVertical._EvaluateAgainstTier); ProfileRepository.GetProfileIdByQualityTier (AddJobToQueue); NextTierAdjuster | READ-AT-DECISION |
| ContentClass | text | not editable | DispositionDispatcher._BuildBucketKey (VMAF confidence bucket); NextTierAdjuster | READ-AT-DECISION |
| QualityLabel | text | not editable | GetTierProfileName (must be NOT NULL); GetProfileIdByQualityLabel (AddJobToQueue); GetTierLabelMap | READ-AT-DECISION |

## ProfileThresholds (33 columns)
| Column | Type | GUI editor | Decision readers | Class |
|---|---|---|---|---|
| Id | bigint | key for PATCH | TierLadderRepository.GetProfileRow (ORDER BY pt.Id LIMIT 1) | READ-AT-DECISION |
| ProfileId | bigint | – | GetProfileRow join; UpdateBitrateCell/UpdateIcqCell | READ-AT-DECISION |
| Resolution | text | Settings (PATCH) | GetProfileRow key (source and encode row) | READ-AT-DECISION |
| Under30MinMB / Under65MinMB / Over65MinMB | bigint | Settings (PATCH, POST/PUT) | Profiles CRUD only (all 0) | READ-ONLY-FOR-DISPLAY (3 columns) |
| VideoBitrateKbps | bigint | Settings | SvtAv1EncoderArgsStrategy (libsvtav1 only); AttemptRecordService | READ (inert) |
| AudioBitrateKbps | bigint | Settings | QueueManagementBusinessService._EncodeTargets, which feeds CalculatePriority (PriorityScore); EffectiveProfile.TargetAudioKbps shown in ComplianceSummary | READ-AT-DECISION (priority only) |
| FallbackVideoBitrateKbps / FallbackAudioBitrateKbps | bigint | Settings | CRUD only | READ-ONLY-FOR-DISPLAY (2 columns) |
| TranscodeDownTo | text | Settings | TierLadderRepository.GetProfileRow, which sets TargetResolution and selects the encode row; ResolutionCalculator | READ-AT-DECISION |
| Quality | bigint | Settings | VideoSlot cq branch; SvtAv1 strategy; CRFOverride_ overwrites it; EstimateTargetSizeMB fallback | READ (inert: vbr is forced; values 0 or NULL) |
| KeepSource | bool | **not editable** (the PUT/POST threshold routes build the model without it, so it resets to FALSE) | ProfileRepository.GetThresholds into the model only; no decision use | READ-ONLY-FOR-DISPLAY |
| ContainerType | text | Settings | CommandComposer:174 and ProcessTranscodeQueueService:1341 (output path/extension) | READ-AT-DECISION |
| SourceBitratePercent | int | Settings (PATCH) | carried in EncoderKnobs; no consumer (all NULL) | WRITTEN-NEVER-READ |
| MinBitrateKbps | int | Settings (PATCH) | same | WRITTEN-NEVER-READ |
| MaxBitrateKbps | int | Settings (PATCH) | same | WRITTEN-NEVER-READ |
| Gop | int | Settings | VideoSlot NVENC/QSV `-g` | READ-AT-DECISION (all NULL) |
| RcLookahead | int | Settings | VideoSlot._EmitNvencArgs | READ (all NULL) |
| BFrames | int | Settings | VideoSlot NVENC/QSV | READ (all NULL) |
| BRefMode | text | Settings | VideoSlot._EmitNvencArgs | READ (all NULL) |
| ScaleHeight | int | Settings (PATCH) | carried in knobs; no consumer | WRITTEN-NEVER-READ |
| MaxBitrateMultiplier | numeric | Settings | VideoSlot._EmitNvencVbrRateArgs/_EmitQsvVbrRateArgs (maxrate/bufsize) | READ (overridden to 2.0 for av1) |
| QsvExtBrc, QsvAdaptiveI, QsvAdaptiveB, QsvLookaheadDepth, QsvBStrategy, QsvTileCols, QsvTileRows | int | Settings | VideoSlot._EmitQsvArgs | READ-AT-DECISION (7 columns) |
| TargetKbps | int | Settings → Transcoding "BitrateLadder" (TierLadderRepository.UpdateBitrateCell) | VideoSlot VBR `-b:v`; VideoVertical (ceiling); TierLadderRepository.GetTierEncodeKbps/GetProfileTarget; _EncodeTargets (priority) | READ-AT-DECISION (the main knob) |
| IcqQ | int | Settings → Transcoding "IcqLadder" | VideoSlot._EmitQsvArgs, icq branch only | READ (inert for Family ANY: the QSV override forces 'vbr') |
| ContentClass | text | not editable | GetProfileRow key | READ-AT-DECISION |

## SeriesProfiles (7 columns)
| Column | Type | GUI editor | Readers | Class |
|---|---|---|---|---|
| id | int | – | none | NEVER-REFERENCED |
| storagerootid | int | WorkBucket.html (series profile POST/DELETE) | SeriesQueryRepository list join; SeriesProfileRepository.GetProfile has **no callers** | READ-ONLY-FOR-DISPLAY |
| relativepath | varchar | same | same | READ-ONLY-FOR-DISPLAY |
| targetresolution | varchar | none | none (8 rows non-null) | NEVER-REFERENCED |
| assignedprofile | varchar | WorkBucket.html | SeriesQueryRepository (display). SeriesProfileService.SetProfile copies it once onto untranscoded MediaFiles (source 'series'); it is never reapplied to files added later | READ-ONLY-FOR-DISPLAY |
| createddate / lastmodifieddate | timestamp | – | written by UpsertProfile only | WRITTEN-NEVER-READ (2 columns) |

## StorageRoots (8 columns)
| Column | Type | GUI | Readers | Class |
|---|---|---|---|---|
| id | bigint | – | all path, tier and class resolvers | READ-AT-DECISION |
| name | text | shown in Settings LibraryTiers | NoAudioResolver (Sonarr vs Radarr routing); display lists | READ-AT-DECISION |
| description | text | – | none | NEVER-REFERENCED |
| canonicalprefix | text | – | PathStorageRoots.GetPrefixMap (path resolution); QueueManagement; classifier FolderPathPattern | READ-AT-DECISION |
| createdat | timestamp | – | none | NEVER-REFERENCED |
| defaultqualitytier | int | Settings LibraryTiers (PUT /api/SystemSettings/LibraryTiers) | FileTierResolver.Resolve (used by VideoVertical and ContentClassifierService); ContentClassifierService.ReassignTierProfiles | READ-AT-DECISION (root 1 = 1, root 2 = 1, root 3 = NULL) |
| genresource | text | none | FileTierResolver.Resolve; MovieGenreSyncService; LibraryDefaultTierRepository.ListGenreSourcedLibraryIds | READ-AT-DECISION (radarr on root 2 only) |
| defaultcontentclass | text | Settings LibraryTiers | ContentClassResolver.Resolve, which feeds the encode row, VideoVertical and _EncodeTargets | READ-AT-DECISION |

## GenreQualityTiers (4 columns)
| Column | Type | GUI | Readers | Class |
|---|---|---|---|---|
| genre | text | Settings GenreTiers | GenreQualityTierRepository.GetTiers/GetClasses | READ-AT-DECISION |
| qualitytier | int | Settings GenreTiers | FileTierResolver.Resolve (max over the file's genres; NULL falls back to the library tier) | READ-AT-DECISION (all 19 rows NULL) |
| lastupdated | timestamp | – | written only | WRITTEN-NEVER-READ |
| contentclass | text | Settings GenreTiers | ContentClassResolver.Resolve (first genre with a class wins) | READ-AT-DECISION (only Animation set) |

## ContentClassificationRules (13 columns)
Context: these rules are only reached when StorageRoot.DefaultQualityTier IS NULL (today only root 3) and the file's AssignedProfile is NULL. They run at probe time from MediaProbeBusinessService:154.

| Column | Type | GUI | Readers | Class |
|---|---|---|---|---|
| id | bigint | Settings Rules (PUT/DELETE key) | ContentClassifierRepository.GetActiveRules | READ-AT-DECISION |
| rulename | text | Settings | ContentClassifierService (logging and hit counts) | READ-AT-DECISION |
| priority | int | Settings | GetActiveRules ORDER BY | READ-AT-DECISION |
| isactive | bool | Settings | GetActiveRules WHERE | READ-AT-DECISION |
| bitratekbpsmin / bitratekbpsmax | int | Settings | _MatchesNumericRange | READ-AT-DECISION (2 columns) |
| resolutioncategory | text | Settings | _MatchesResolution | READ-AT-DECISION |
| codecin | text | Settings | _MatchesCodec | READ-AT-DECISION |
| folderpathpattern | text | Settings | _MatchesFolderPattern | READ-AT-DECISION |
| assignprofilename | text | Settings | ClassifyAndAssign ('__skip__' marks the file classifier_skip_av1) | READ-AT-DECISION |
| description | text | Settings | controller list | READ-ONLY-FOR-DISPLAY |
| lastupdated | timestamp | – | none | NEVER-REFERENCED |
| source | text | – | none (set only by seed scripts) | NEVER-REFERENCED |

## AudioNormalizationConfig (12 columns; GUI: none, API POST /api/AudioNormalization/Settings only)
| Column | Type | Readers | Class |
|---|---|---|---|
| id | bigint | AudioPolicyAdmissionGate BACKFILL to_jsonb snapshot into TranscodeQueue.AudioPolicyJson | READ-ONLY-FOR-DISPLAY |
| scope | text | AudioPolicyResolver.GetEffectivePolicy (item, folder, library, global) | READ-AT-DECISION |
| scopekey | text | same | READ-AT-DECISION |
| enabled | bool | AudioStrategyClassifier.ClassifyTrack (line 43) | READ-AT-DECISION |
| targetlra | real | ComplianceSummaryController (display); policy snapshot. The classifier uses the per-track EmitTracks[].TargetLra instead | READ-ONLY-FOR-DISPLAY |
| loudnesstolerance | real | AudioStrategyClassifier | READ-AT-DECISION |
| emittracks | jsonb | AudioPolicyAdmissionGate.AdmitOrDefer (must be non-empty; per-track TargetLufs/TargetLra feed AudioStrategyClassifier). **AudioFilterEmitter ignores the entries**, so Codec/Bitrate/BitDepth/Channels/SampleRateHz/IsDefaultTrack/LanguageFilter/Label are dead sub-fields | READ-AT-DECISION (partially) |
| ungainablepolicy | text | AudioStrategyClassifier | READ-AT-DECISION |
| enablespeechlanguagedetection | bool | AudioFilterEmitter.EmitTracks | READ-AT-DECISION |
| lastupdated | timestamp | written | WRITTEN-NEVER-READ |
| languagedefault | text | AudioFilterEmitter.EmitTracks (default language) | READ-AT-DECISION |
| preverticalrenormalizepolicy | text | only the validator and the controller upsert | WRITTEN-NEVER-READ |

Classifier gap: AudioStrategyClassifier reads Policy.TargetIntegratedLufs and Policy.TargetTruePeakDbtp, but those columns do not exist on this table, so the hard-coded defaults -23 and -2 always apply.

## AudioComplianceRules (21 columns; GUI: AdminCompliance.html and AudioNormalization.html via /api/AudioNormalization/Rules)
| Column | Type | Readers | Class |
|---|---|---|---|
| id | bigint | GetRules WHERE Id=1 | READ-AT-DECISION |
| targetintegratedlufs | numeric | AudioVertical._LoadRules; AudioFilterEmitter._BuildOriginalBlock; PreEncodeAudioPipeline | READ-AT-DECISION |
| targettruepeakdbtp | numeric | AudioVertical; AudioFilterEmitter (both tracks) | READ-AT-DECISION |
| acceptableaudiocodecscsv | text | AudioVertical.Evaluate (codec check); AudioSlot._CopyCodecArgs | READ-AT-DECISION |
| lastupdated | timestamptz | selected in GetRules but not returned | WRITTEN-NEVER-READ |
| dialogboosttargetlufs, dialogboosttargetlra | numeric | AudioFilterEmitter._BuildDialogBoostBlock; PreEncodeAudioPipeline | READ-AT-DECISION |
| samplelimitheadroomdb | numeric | AudioFilterEmitter | READ-AT-DECISION |
| track0bitrateperchannelkbps, track0minperchannelkbps, track1stereobitratekbps | int | AudioFilterEmitter; AudioSlot copy fallback | READ-AT-DECISION |
| track1vocalsrmsfallbackdbfs | numeric | AudioFilterEmitter._ShouldEmitDialogBoost; AudioPreEncodeFacade | READ-AT-DECISION |
| vocalsboostdb, instrumentalattendb | numeric | Demucs / OpenVino VocalIsolationService; PreEncodeAudioPipeline | READ-AT-DECISION |
| premix* (5 columns) | numeric/int | PreEncodeAudioPipeline | READ-AT-DECISION |
| track0codec, track1codec | text | AudioFilterEmitter (opus → libopus) | READ-AT-DECISION |

## ContainerComplianceRules (4 columns; GUI: AdminCompliance.html via /api/ContainerFormat/Rules)
| Column | Type | Readers | Class |
|---|---|---|---|
| id | int | ContainerVertical._LoadRules (ORDER BY Id LIMIT 1) | READ-AT-DECISION |
| acceptablecontainerscsv | text | ContainerVertical.Evaluate | READ-AT-DECISION |
| acceptableaudiocodecscsv | text | only the controller GET/PUT; not read by ContainerVertical or anything else | WRITTEN-NEVER-READ |
| lastupdated | timestamp | controller GET | READ-ONLY-FOR-DISPLAY |

## VideoComplianceThresholds (4 columns; GUI: Settings Transcoding section)
| Column | Type | Readers | Class |
|---|---|---|---|
| id | int | none | NEVER-REFERENCED |
| resolutioncategory | text | VideoComplianceThresholdsRepository.GetMultiplier, used by VideoVertical.Evaluate/_EvaluateAgainstTier | READ-AT-DECISION |
| multiplier | numeric | same (ceiling = target × multiplier: 480p 4.0, 720p 2.0, 1080p 2.0, 2160p 3.0) | READ-AT-DECISION |
| lastupdated | timestamp | written | WRITTEN-NEVER-READ |

## PostTranscodeGateConfig (12 columns; GUI: Settings gate and Transcoding sections)
| Column | Type | GUI | Readers | Class |
|---|---|---|---|---|
| id | int | – | Repository.Get WHERE Id=1 | READ-AT-DECISION |
| vmafautoreplaceminthreshold | numeric | Settings | PostTranscodeDispositionDecider.Decide (below it: Requeue) and _MaybeSmartConfidenceSkip | READ-AT-DECISION (90) |
| vmafautoreplacemaxthreshold | numeric | Settings | Decide (above it: Reject 'VmafAboveMax') | READ-AT-DECISION (96) |
| whenvmafunavailable | text | Settings | passed into the gate dictionary and audit log only; Decide never branches on it | READ-ONLY-FOR-DISPLAY (no behavioral effect) |
| lastupdated | timestamp | Settings GET | display | READ-ONLY-FOR-DISPLAY |
| qualitytestenabled | bool | Settings | Decide._QualityTestGloballyEnabled | READ-AT-DECISION |
| maxrequeueattempts | int | not editable | RetryBudgetService | READ-AT-DECISION |
| workerheartbeatwindowsec | int | not editable | DispositionDispatcher._QueryVmafCapableWorkerOnline, whose result reaches only the decider input and audit log; Decide ignores it | READ-ONLY-FOR-DISPLAY (no behavioral effect) |
| filereplacementcanreplacethreshold | int | not editable | FileReplacementBusinessService.GetFileReplacementStatus (CanReplace flag) | READ-AT-DECISION (90) |
| minconfidencesamplecount, minconfidencepassrate, sigmamargin | int/numeric | Settings Transcoding | Decide._MaybeSmartConfidenceSkip | READ-AT-DECISION (3 columns) |

## ProcessingModes (7 columns; GUI: none)
| Column | Type | Readers | Class |
|---|---|---|---|
| name | text | claim SQL join; JobProcessorRegistry.Get/IsModeKnown | READ-AT-DECISION |
| bucketname | text | none (the BucketName in code is the WorkBucket.Domain.BucketKey class, not this column) | NEVER-REFERENCED |
| requiresvmaf | bool | none | NEVER-REFERENCED |
| requiresinterlacedfilter | bool | TranscodeQueueRepository claim; also copied in ProcessingModeMetadata | READ-AT-DECISION |
| requiresnvencgate | bool | none | NEVER-REFERENCED |
| claimcapabilityflag | text | claim SQL | READ-AT-DECISION |
| requiresprofilegates | bool | claim SQL; the code copy ProcessingModeMetadata (AddJobToQueue, FileReplacement) | READ-AT-DECISION |

## ResolutionTiers (7 columns; GUI: none)
| Column | Type | Readers | Class |
|---|---|---|---|
| id | bigint | none | NEVER-REFERENCED |
| name, minlongedge, canonicalwidth, canonicalheight, rank | – | ResolutionTiersRepository feeds ResolutionTierRegistry (FromDims / FromCategory / ByRank) and ScalePolicy (CanonicalWidth) | READ-AT-DECISION (5 columns) |
| lastupdated | timestamp | none | NEVER-REFERENCED |

## SystemSettings (80 keys)
Every key can be edited through the generic "All System Settings" table on Settings.html. The table names any dedicated editor beyond that. Values for secrets (API keys, SSH settings) are deliberately not reproduced here.

| Key | Reader (file) | Class | Domain |
|---|---|---|---|
| BitratePerPixelBoundaries | DispositionDispatcher._LoadBitratePerPixelBoundaries | READ-AT-DECISION | VMAF confidence bucket |
| CRFOverride_z:… (1 stale key) | ProcessTranscodeQueueService.GetTranscodingSettings; written by TranscodeJobController /SetCRFOverride | READ (inert under forced vbr) | encode |
| DefaultProfileName | EffectiveProfileResolver._ResolveAssignedProfileName; Settings DefaultProfile editor | READ-AT-DECISION, but **dangling**: value 'NVENC AV1 P7 CANARY VBR -720p' is not in Profiles | profile cascade |
| FfmpegLogLevel | CommandComposer; ProcessTranscodeQueueService; JobProcessor | READ | encode |
| FFmpegPath, FFprobePath | CommandComposer, JobProcessor, VmafCommandComposer, audio services, WorkerService/Main | READ | encode / QT |
| MaxCpuThreads | CommandComposer (-threads); VideoTranscodingService; FFmpegService | READ | encode |
| MaxConcurrentJobs | WorkerLoopService; WorkerCapabilityPredicate; QT services | READ | scheduling |
| PreferredDefaultLanguageRank | IAudioDefaultLanguagePolicy | READ | audio default track |
| MinDetectionConfidence | LanguageEnrichmentService | READ | audio language |
| QualityTestMaxCores | QualityTestingBusinessService.GetQualityTestMaxCores | READ | QT |
| VmafStillCaptureMinSamples, VmafStillCapturePolicy, VmafStillCaptureTimestamps | QualityTestingBusinessService; QualityTestController | READ | QT |
| ExcludedDirectories | FileScanningViewModel; FileManagerService; dedicated Settings editor | READ | scan scope |
| ScanDir1, ScanDir2, ScanDir3 | SystemSettingsRepository.GetScanDirectories (LIKE 'ScanDir%') | READ | scan |
| ContinuousScanEnabled, ContinuousScanIntervalMinutes | FileScanningController; WorkerService/Main | READ | scan |
| CapabilityPollingIntervalSec, StuckJobDetectionIntervalSec | WorkerService/Main | READ | ops |
| FrozenProgressThresholdMin, SetupPhaseTimeoutMin, PostEncodePhaseTimeoutMin, VerifyingPhaseTimeoutMin | ServiceControl PhaseDetectors; StuckJobDetectionService | READ | stuck-job detection |
| CpuAffinityEnabled | Services/CpuAffinityService; Settings | READ | ops |
| JellyfinApiKey, JellyfinApiPort, JellyfinHost, JellyfinSSHKeyPath, JellyfinSSHPort, JellyfinSSHUser | OptimizationViewModel; JellyfinNotifyService | READ | integration |
| RadarrApiKey, RadarrUrl | MovieGenreSyncService (populates Genres); NoAudioResolver | READ | genre-tier input |
| SonarrApiKey, SonarrUrl | NoAudioResolver | READ | audio |
| DisplayTimezone | WebService/Main; TeamStatusController; Settings | READ-ONLY-FOR-DISPLAY | UI |
| HeartbeatStaleThresholdSec, HungEncodeThresholdSec | AdminWorkersRepository; DashboardSnapshotService | READ-ONLY-FOR-DISPLAY | dashboards |
| StaleProgressThresholdSec | ActivityController; DashboardSnapshotService | READ-ONLY-FOR-DISPLAY | dashboards |
| AllowedExtensions, AudioNormalizationEnabled, AudioVerticalHealthEnabled, CpuAffinityCoolingWaitEnabled, CpuAffinityCoolingWaitMaxSeconds, CpuAffinityCoolingWaitTargetTemp, CpuAffinityMonitoringInterval, CpuAffinityTemperatureThreshold, DefaultAudioBitrate, DefaultFallbackAudioBitrate, DefaultFallbackVideoBitrate, DefaultTestFFmpegPath, DefaultTestWorkerName, DefaultVideoBitrate, ExclusionDirectories, HandBrakeCliPath, LimitThreads, MinimumLoudnessRangeLU, MoveDetectionMaxFiles, NextSessionSize, NumberOfThreads, Over65MinMB, RefreshFileList, ScreenshotComparisonEnabled, ScreenshotTimestampSeconds, SessionSize, SizeSurveyTopN, TargetLoudness, TempDirectory, TemporaryOutputDirectory, TemporarySourceDirectory, TerminateOnFailure, TestModeRetentionDays, TranscodeOutputMode, TruePeak, Under30MinMB, Under65MinMB, UseHardwareAcceleration, WhisperModelPath (39 keys) | no code reference by key name. Grep hits for Over65MinMB/Under30MinMB/Under65MinMB are ProfileThresholds columns, and the TruePeak hit is a local variable | NEVER-REFERENCED | – |

Settings.html also requests five keys that are not in the table: TranscodeCoreTier, QualityTestCoreTier, ThermalGateEnabled, ThermalPauseCriticalTemp, ThermalGateMaxTemp.

## MediaFiles (and related) policy columns
| Column | Writers | Readers | Class |
|---|---|---|---|
| AssignedProfile | (1) ProfileAssignmentService.Assign → MediaFilesRepository.WriteAssignedProfile (classifier, genre_tier, library_default_tier, series, root_folder). (2) QueueManagementBusinessService.AddJobToQueue → DatabaseManager.SaveMediaFile, which **does not set AssignedProfileSource and skips the recompute cascade**. (3) Bulk add (QueueManagementBusinessService ~line 569) raw UPDATE, same bypass. (4) RecomputeForFiles rewrites it with ResolveProfileName and **can set it to NULL** when the profile is a draft or inactive, because DefaultProfileName is dangling. (5) Bulk scripts (bulk_tier_*, backfill_*) | ProcessTranscodeQueueService.GetTranscodingSettings (encode knobs; uses AssignedProfile directly, no cascade); TranscodeQueueRepository claim join; VideoVertical (**only when no library tier applies**); EffectiveProfileResolver; ContentClassifierService (sticky skip); _EncodeTargets (priority); ComplianceRecomputeController filter | READ-AT-DECISION |
| AssignedProfileSource | WriteAssignedProfile; scripts | ContentClassifierService.ReassignTierProfiles excludes ['operator','series','root_folder','manual_sql'] unless IncludeOverrides. Script-written sources such as bulk_tier_by_root are not protected | READ-AT-DECISION (single reader) |
| KeepSource | no code writer (117 TRUE rows were set outside the app); FileScanningRepository.SaveMediaFileArchive copies it to the archive | TranscodeJobRepository.GetKeepSourceSetting, which has **no callers** | WRITTEN-NEVER-READ |
| LastTranscodeOutcome | – | column does not exist on MediaFiles | n/a |
| Genres | MovieGenreSyncService (Radarr; roots with a GenreSource, i.e. root 2 only) | FileTierResolver.Resolve; ContentClassResolver.Resolve; GenreQualityTierRepository.ListGenreTiers | READ-AT-DECISION |
| Audio/Video/ContainerCompliant (+ Reason) | AudioVertical / VideoVertical / ContainerVertical._WriteResult | WorkBucket is generated from them; ComplianceSummary | READ-AT-DECISION |
| WorkBucket (generated), IsCompliant | DB-generated | AddJobToQueue mode default; queue candidate SQL (ProcessingModeMetadata.WorkBucketFilterSql); TranscodedOutputPlacement; dashboards | READ-AT-DECISION |
| PriorityScore | RecomputeForFiles; ComputePriorityScore | queue candidate ORDER BY m.PriorityScore (QueueManagementBusinessService:350) | READ-AT-DECISION |
| AdmissionDeferReason | audio admission and review services | review queue; ActivityRepository | READ-AT-DECISION |
| TranscodedByMediaVortex | AddJobToQueue '-mv' self-heal; post-replace | SelectUntranscodedInSeries. A comment claims VideoVertical short-circuits on it, but VideoVertical.Evaluate never reads it | READ-AT-DECISION |
| QualityTestingQueue.ForceDisposition | POST /api/QualityTest/Override (API only, no page) | QualityTestRepository claim (`ForceDisposition IS NULL`); QualityTestController | READ-AT-DECISION |
| TranscodeQueue.AudioSlotOverride | none | none | NEVER-REFERENCED |

## Stats
1. **MediaFiles.AssignedProfileSource**: bulk_tier_by_root_2026_07_23 35,982 · series 9,666 · genre_tier 3,321 · classifier 3,264 · library_default_tier 2,309 · operator 2,101 · classifier_skip_av1 239 · backfill_tv_tier1_2026_08_25 173 · NULL 104 · test 6 · bulk-tier2-already-transcoded-2026-07-21 3.
   - AssignedProfile: Tier 1 Efficient 56,251 · Tier 2 Good 602 · Tier 3 Better 263 · NULL 52.
   - Per root, non-Tier-1 assignments are 17 on root 1 (series → Tier 2) and the rest on root 3 (classifier and series).
   - 237 root-1 files have source classifier_skip_av1 but AssignedProfile = Tier 1 Efficient.
2. **SeriesProfiles**: 218 rows, 3 distinct StorageRootIds (root 1: 211, root 2: 6, root 3: 1).
   - 214 rows have an AssignedProfile: Tier 1 Efficient 206, Tier 2 Good 6, STREAMING QSV HQ 1, and 'NVENC AV1 P7 CANARY VBR -720p' 1 (that profile does not exist). 4 rows are NULL.
   - TargetResolution is non-null on 8 rows (root 1: 7, root 2: 1) and nothing reads it.
3. **FrameRate buckets**:

   | Root | ≤30 fps | >30 fps | NULL |
   |---|---|---|---|
   | 1 (media_tv) | 47,552 | 1,929 | 2 |
   | 2 (movies) | 3,479 | 7 | 1 |
   | 3 (xxx) | 3,642 | 552 | 4 |

   No setting is keyed on frame rate. FrameRate is used only in DispositionDispatcher._ComputeBitratePerPixelBucket (normalized by fps/24).
4. **Profiles**:

   | Id | ProfileName | QualityTier | ContentClass | Codec | Active | Threshold rows |
   |---|---|---|---|---|---|---|
   | 468 | STREAMING NVENC AV1 P6 Default -2160p | 1 | live_action | av1_nvenc | true | 1 |
   | 469 | STREAMING NVENC AV1 P6 HQ -2160p | 2 | live_action | av1_nvenc | true | 1 |
   | 470 | STREAMING QSV AV1 P1 Default -2160p | 1 | live_action | av1_qsv | true | 1 |
   | 471 | STREAMING QSV AV1 P1 HQ -2160p | 2 | live_action | av1_qsv | true | 1 |
   | 475 | AV1 Tier 1 Efficient | 1 | live_action | av1 | true | 8 |
   | 476 | AV1 Tier 2 Good | 2 | live_action | av1 | true | 8 |
   | 477 | AV1 Tier 3 Better | 3 | live_action | av1 | true | 8 |
   | 478 | AV1 Tier 4 Best | 4 | live_action | av1 | true | 8 |
   | 479 | AV1 Tier 5 Reference | 5 | live_action | av1 | true | 8 |

   - All nine are finalized (Draft=false) with QualityTestRequired=true. 475–479 have Family ANY.
   - The 8 rows per tier profile are 4 resolutions × {live_action, animation}.
   - TargetResolutionCategory is NULL on 475–479, so NextTierAdjuster always returns None.

## Columns with NEVER-REFERENCED or WRITTEN-NEVER-READ
- **Profiles**: YadifMode, YadifParity, YadifDeint, CodecFlagsId, AudioChannels, AudioFilter, FastStart, TargetAudioKbps.
- **ProfileThresholds**: SourceBitratePercent, MinBitrateKbps, MaxBitrateKbps, ScaleHeight.
- **SeriesProfiles**: id, targetresolution (never referenced); createddate, lastmodifieddate (written, never read).
- **StorageRoots**: description, createdat.
- **GenreQualityTiers**: lastupdated.
- **ContentClassificationRules**: lastupdated, source.
- **AudioNormalizationConfig**: preverticalrenormalizepolicy, lastupdated; also the dead EmitTracks sub-fields Codec/Bitrate/BitDepth/Channels/SampleRateHz/IsDefaultTrack/LanguageFilter.
- **AudioComplianceRules**: lastupdated.
- **ContainerComplianceRules**: acceptableaudiocodecscsv (editable in the GUI).
- **VideoComplianceThresholds**: id, lastupdated.
- **ProcessingModes**: bucketname, requiresvmaf, requiresnvencgate.
- **ResolutionTiers**: id, lastupdated.
- **MediaFiles**: KeepSource (reader has no callers). **TranscodeQueue**: AudioSlotOverride.
- **SystemSettings**: the 39 keys listed in the SystemSettings table.
- **Read but no behavioral effect**: PostTranscodeGateConfig.WhenVmafUnavailable and WorkerHeartbeatWindowSec (audit log only); SeriesProfiles.assignedprofile (display only; never reapplied).
- **Overridden in code for 99.9% of files**: Profiles Codec, Preset, Tune, Multipass, RateControlMode, SpatialAq, TemporalAq, PixelFormat, UseNvidiaHardware, UseIntelHardware; ProfileThresholds.MaxBitrateMultiplier.
- **Inert under the forced vbr rate control**: ProfileThresholds.IcqQ, Quality, VideoBitrateKbps; Profiles.FilmGrain; SystemSettings CRFOverride_*.

## Facts with two or more authorities
1. **Integrated loudness target**: AudioComplianceRules.TargetIntegratedLufs -23 (what is emitted for Track0, and the vertical) and DialogBoostTargetLufs -14 (what is emitted for Track1) vs AudioNormalizationConfig.EmitTracks[0/1].TargetLufs -23/-23 (what the admission classifier assumes) vs SystemSettings.TargetLoudness -23 (dead). Admission predicts the dialog-boost track at -23 while the emitter targets -14.
2. **Loudness range**: EmitTracks[1].TargetLra 11 (admission) vs AudioComplianceRules.DialogBoostTargetLra 9 (emitted) vs AudioNormalizationConfig.TargetLra NULL (display) vs SystemSettings.MinimumLoudnessRangeLU 11 (dead).
3. **True peak**: AudioComplianceRules.TargetTruePeakDbtp -2 vs SystemSettings.TruePeak -2 (dead) vs AudioStrategyClassifier's hard-coded -2 default (the policy table has no such column).
4. **Audio codec, bitrate and channels**: AudioComplianceRules Track0/1Codec opus and 48 per channel / 64 stereo (emitted) vs EmitTracks aac/128 (ignored) vs Profiles.AudioCodec/AudioBitrateKbps/AudioChannels libopus/128/2 (display or record only) vs WorkerEncoderResolver libopus/192/6 (attempt record) vs ProfileThresholds.AudioBitrateKbps 192 (PriorityScore estimate) vs SystemSettings DefaultAudioBitrate/DefaultFallbackAudioBitrate 80 (dead).
5. **Acceptable audio codecs**: AudioComplianceRules.AcceptableAudioCodecsCsv 'aac,ac3,eac3,mp3,opus' (read) vs ContainerComplianceRules.AcceptableAudioCodecsCsv 'aac,ac3,eac3,mp3' (editable in the GUI, never read).
6. **Container and faststart**: ContainerComplianceRules.AcceptableContainersCsv (vertical) vs Profiles.Container (display) vs ProfileThresholds.ContainerType (output extension) vs Profiles.FastStart (dead) vs ContainerSlot hard-coded mp4 +faststart vs WorkerEncoderResolver Container/FastStart.
7. **KeepSource**: MediaFiles.KeepSource (117 TRUE; no live reader) vs ProfileThresholds.KeepSource (all FALSE; display; silently reset by the threshold PUT/POST routes).
8. **Whether a quality test is required or enabled**: Profiles.QualityTestRequired (per profile; copied to TranscodeAttempts) vs PostTranscodeGateConfig.QualityTestEnabled (global short-circuit) vs ProcessingModes.RequiresVmaf (dead) vs Workers.QualityTestEnabled (capability) vs the QualityTestRepository skip path that sets TranscodeAttempts.QualityTestRequired = FALSE.
9. **VMAF threshold for replacing the file**: PostTranscodeGateConfig.VmafAutoReplaceMinThreshold 90 (auto disposition) vs FileReplacementCanReplaceThreshold 90 (manual CanReplace).
10. **Encoder knobs**: the Profiles and ProfileThresholds columns vs the WorkerEncoderResolver NVENC_OVERRIDES / QSV_OVERRIDES dictionaries, which win for Codec='av1' (all five tier profiles). The ICQ ladder editor in Settings has no effect for those profiles.
11. **Which profile a file gets**:
    - MediaFiles.AssignedProfile is what the encode uses.
    - StorageRoots.DefaultQualityTier + GenreQualityTiers.QualityTier is what VideoVertical judges compliance against, ignoring AssignedProfile for roots 1 and 2. Example: 17 root-1 files with a Tier 2 series pin are judged against the Tier 1 target.
    - SeriesProfiles.AssignedProfile is applied once and never reapplied.
    - ContentClassificationRules only take effect on root 3.
    - SystemSettings.DefaultProfileName is dangling.
    - AddJobToQueue ProfileId/QualityLabel/QualityTier overwrite AssignedProfile without a source or recompute.
    - The cached cascade in RecomputeForFiles can null the field out.
12. **Content class**: StorageRoots.DefaultContentClass + GenreQualityTiers.ContentClass (resolved; selects the threshold row for the encode, VideoVertical and priority) vs Profiles.ContentClass (always live_action; used for the VMAF confidence BucketKey and NextTier) vs ProfileThresholds.ContentClass (row key).
13. **Target resolution**: ProfileThresholds.TranscodeDownTo (encode) vs Profiles.TargetResolutionCategory (NextTier and dashboard; NULL on tier profiles) vs SeriesProfiles.TargetResolution (dead).
14. **Target video bitrate**: ProfileThresholds.TargetKbps (encode, compliance ceiling, priority) vs Profiles.TargetVideoKbps (dashboard fallback; NULL) vs ProfileThresholds.VideoBitrateKbps (SVT path and attempt record) vs SystemSettings DefaultVideoBitrate/DefaultFallbackVideoBitrate (dead).
15. **Size thresholds**: ProfileThresholds Under30MinMB/Under65MinMB/Over65MinMB (display; all 0) vs SystemSettings keys of the same names (300/600/800; dead).
16. **Processing-mode policy**: ProcessingModes table (claim SQL) vs ProcessingModeMetadata._METADATA in code (admission, replacement). The code docstring says the DB row is the source of truth.
17. **Directory exclusions**: SystemSettings.ExcludedDirectories (read; X:\Videos\_uncategorized) vs ExclusionDirectories (dead; ["T:\\Firefly"]).
18. **Encoder threads**: MaxCpuThreads (read) vs NumberOfThreads and LimitThreads (dead).
19. **Deinterlace**: Profiles.YadifMode/Parity/Deint (dead) vs yadif=1:1:1 hard-coded in VideoFilterBuilder vs ProcessingModes.RequiresInterlacedFilter (claim gate).

## Key file paths
- C:\Code\MediaVortex\Features\Profiles\TierLadderRepository.py
- C:\Code\MediaVortex\Features\Profiles\EncoderKnobRepository.py
- C:\Code\MediaVortex\Features\Profiles\EffectiveProfileResolver.py
- C:\Code\MediaVortex\Features\Profiles\FileTierResolver.py
- C:\Code\MediaVortex\Features\Profiles\ContentClassResolver.py
- C:\Code\MediaVortex\Features\Profiles\ProfileController.py
- C:\Code\MediaVortex\Features\TranscodeJob\Worker\WorkerEncoderResolver.py
- C:\Code\MediaVortex\Features\TranscodeJob\Emit\Slots\VideoSlot.py
- C:\Code\MediaVortex\Features\TranscodeJob\Emit\Slots\AudioSlot.py
- C:\Code\MediaVortex\Features\TranscodeJob\Emit\Slots\ContainerSlot.py
- C:\Code\MediaVortex\Features\TranscodeJob\Emit\VideoFilterBuilder.py
- C:\Code\MediaVortex\Features\TranscodeJob\ProcessTranscodeQueueService.py (GetTranscodingSettings, line 823)
- C:\Code\MediaVortex\Features\VideoEncoding\VideoVertical.py
- C:\Code\MediaVortex\Features\AudioNormalization\AudioVertical.py
- C:\Code\MediaVortex\Features\AudioNormalization\AudioFilterEmitter.py
- C:\Code\MediaVortex\Features\AudioNormalization\AudioStrategyClassifier.py
- C:\Code\MediaVortex\Features\AudioNormalization\AudioPolicyAdmissionGate.py
- C:\Code\MediaVortex\Features\ContainerFormat\ContainerVertical.py
- C:\Code\MediaVortex\Features\ContentClassifier\ContentClassifierService.py
- C:\Code\MediaVortex\Features\TranscodeQueue\QueueManagementBusinessService.py (RecomputeForFiles line 1568, AddJobToQueue line 1735)
- C:\Code\MediaVortex\Features\TranscodeQueue\TranscodeQueueRepository.py (claim SQL around line 305)
- C:\Code\MediaVortex\Features\QualityTesting\Disposition\DispositionDispatcher.py
- C:\Code\MediaVortex\Features\QualityTesting\Disposition\PostTranscodeDispositionDecider.py
- C:\Code\MediaVortex\Features\TranscodeJob\Adjustments\NextTierAdjustmentCalculator.py
- C:\Code\MediaVortex\Features\WorkBucket\Repositories\SeriesProfileRepository.py
- C:\Code\MediaVortex\Features\WorkBucket\Services\SeriesProfileService.py
- C:\Code\MediaVortex\Features\TranscodeJob\TranscodeJobRepository.py (GetKeepSourceSetting, line 978, no callers)
- C:\Code\MediaVortex\Features\SystemSettings\SystemSettingsController.py
- C:\Code\MediaVortex\Templates\Settings.html
- C:\Code\MediaVortex\Templates\AdminCompliance.html
- C:\Code\MediaVortex\Templates\WorkBucket.html

## Addendum 2026-11-27 (target-policy-1a-tables): CodecFlags + CodecParameters, frame-rate classes, ladder seed

Missing from the 2026-11-26 pass; measured live 2026-11-27 before the Phase 1a migration.

**CodecFlags** (15 columns: Id, CodecName, DisplayName, PresetType, PresetMin, PresetMax, PresetDefault, PresetOptions, FilmGrainType, FilmGrainMin, FilmGrainMax, FilmGrainDefault, TuneOptions, CreatedDate, LastModified). 3 rows: `libsvtav1` (Id 5, PresetDefault 6, FilmGrainDefault 10), `av1_nvenc` (Id 6, PresetDefault 7), `av1_qsv` (Id 7, PresetDefault 1).

**CodecParameters** (10 columns: Id, CodecFlagsId, ParameterName, ParameterType, MinValue, MaxValue, DefaultValue, Description, FfmpegFlag, CreatedDate). 12 rows: libsvtav1 `preset` (default 6), `crf` (default 30), `qp`, `film-grain` (default 10), `tune`, `la-depth`, `movflags`, `10bit-encoding`; av1_nvenc `cq`, `preset`; av1_qsv `preset`, `global_quality`.

**Readers.** `Core/Database/CodecFlagsRepository` (`GetCodecFlagsByCodecName`, `GetCodecParametersByCodecFlagsId`) called once, from `ProcessTranscodeQueueService.GetTranscodingSettings` (lines 852-858): a codec with no `CodecFlags` row or no `CodecParameters` row fails the job with "Failed to get transcoding settings" (existence gate). `Context['CodecFlags']` is passed to `CreateTranscodeAttempt` and never read; `Context['CodecParameters']` reaches `VideoSlot` -> `SvtAv1EncoderArgsStrategy`, where only three parameter NAMES act as emit switches on the libsvtav1 path: `crf` (emit `-crf <Profiles... Quality>`), `preset` (emit `-preset <Preset>`), `film-grain` (emit `-svtav1-params film-grain=<Profiles.FilmGrain>`). The NVENC and QSV paths ignore the list. Every Min/Max/Default/Description/Options column and the other nine parameter rows are read by nothing at decision time (the `/settings` profile editor shows preset ranges from `CodecFlags`). Writers: `Scripts/SQLScripts/AddNvencProfiles.py` seeds; `Features/Profiles/Models/CodecFlagsModel.py`, `CodecParametersModel.py` are shims.

| Column family | Class |
|---|---|
| `CodecFlags.CodecName` row existence (all 3) | READ-AS-GATE (job fails without it) |
| `CodecParameters.ParameterName` in (`crf`, `preset`, `film-grain`) for libsvtav1 | READ-AS-SWITCH (presence toggles emission) |
| all other `CodecFlags` / `CodecParameters` columns and rows | DISP (profile editor ranges) or NEVER |

**Fold rule (spec 4.5, decided here).** `EncoderSettings` gains `Crf INT NULL` and `FilmGrain INT NULL`; "parameter row present" becomes "column non-NULL". The five `libsvtav1` rows seed `Preset 6`, `Crf 30`, `FilmGrain 10`, `RateControl 'crf'`, everything else NULL (today's tier profiles have `Tune`, `PixelFormat` NULL, so nothing else is emitted). The `av1_nvenc` and `av1_qsv` rows carry the `WorkerEncoderResolver` dictionaries (`Features/TranscodeJob/Worker/WorkerEncoderResolver.py`) plus the QSV threshold knobs (`QsvExtBrc 1`, `QsvLookAheadDepth 8`). The gate and the switch move to the `EncoderSettings` row lookup in `target-policy-1c-pipeline`; both tables, `CodecFlagsRepository` and the two shims are deleted in `target-policy-delete-stored`.

**Frame-rate classes (seed).** Live `MediaFiles.FrameRate` distribution 2026-11-27: 55,829 files at or below 30 fps, 2,309 in (30, 120], 276 above 120 (251 of them at 90000 fps and 2 at 16000 fps: probe fact defects, filed as a bug), 7 NULL. `FrameRateClasses` seeds `standard` MaxFps `30.0` and `high` MaxFps `120.0`; files above 120 or NULL resolve `Undecided('FrameRateClass')`. `high` cells seed at the `standard` cell's `TargetKbps` x `1.5` (evidence: tier 3 8,000 kbps scored VMAF 90.4 at 59.94 fps and 98.9 at 29.97 fps in the xxx-video-tier fleet smoke, 2026-11-26); the operator tunes them on `/settings` in `target-policy-1d-gui`.

**Ladder seed.** A `LadderCells` row's `TargetKbps` is the kbps at its `TargetResolution`: today every consumer (`EncoderKnobRepository`, `VideoVertical` via `GetTierEncodeKbps`, admission) reads the ENCODE row (`TierLadderRepository.GetEncodeRow`, the row at `TranscodeDownTo`), so the `TargetKbps 900` stored on the tier 1 live_action 1080p and 2160p SOURCE rows is dead and is not migrated. Source rows: 44 `ProfileThresholds` rows, 40 on the five tier profiles (Ids 475-479), 4 on the STREAMING profiles (not migrated; they go with the profiles in Phase 2).

**Acceptance seed.** `PostTranscodeGateConfig` holds `VmafAutoReplaceMinThreshold 90.0` / `VmafAutoReplaceMaxThreshold 96.0`; those seed `Profiles.VmafMin` / `VmafMax` on the five tier rows. `HeldFrameDetectionThreshold`, `HeldFrameP25Min`, `HeldFrameMeanMin`, `LiveActionP10Min` have no live source (`post-transcode-disposition.feature.md` describes columns that were never migrated; no Python reads them) and stay NULL until `target-policy-verification` seeds them with the decider.
