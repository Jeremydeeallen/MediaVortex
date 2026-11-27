# Transcode decision-layer branching audit (2026-11-26, repo @ 6d06ee9d)

Classification: GS = GRAPH-SHAPE, DP = DATA-PATH, SD = SILENT-DEFAULT, DUP = DUPLICATE-LOOKUP.
Overall: 252 GS / 81 DP / 112 SD / 63 DUP.

## Per-file counts (GS/DP/SD/DUP)
VideoVertical 11/4/2/3 · AudioVertical 7/2/2/2 · ContainerVertical 5/2/3/1 · FileTierResolver 5/2/1/2 · ContentClassResolver 5/1/2/2 · TierLadderRepository 4/6/5/2
ContentClassifierService 17/5/4/3 · ProfileAssignmentService 2/0/0/0 · QueueManagementBusinessService (admission) 44/9/22/9 · EffectiveProfileResolver 5/0/3/3
CommandComposer 15/2/7/3 · Plan+ProcessingModeMetadata 2/0/1/1 · VideoSlot 8/8/5/1 · AudioSlot 5/2/3/2 · ContainerSlot 1/0/0/1 · SubtitleSlot 5/1/2/0 · ResolutionCalculator 2/1/4/1 · HwAccelResolver 5/1/2/1
OutputFilenameBuilder 0/3/1/1 · SvtAv1Args 0/4/0/1 · VideoFilterBuilder 0/1/1/0 · EncoderKnobRepository 1/2/1/1 · WorkerEncoderResolver 4/1/1/1
AudioFilterEmitter 7/4/9/1 · PreEncodeAudioPipeline 4/2/6/2 · AudioStrategyClassifier 5/1/4/1 · AdmissionGate 4/1/1/1 · PolicyResolver 3/1/0/1 · PreEncodeFacade 3/1/0/1
Decider 7/4/3/0 · DispositionDispatcher 16/3/6/3 · RetainPolicy 1/0/0/0 · RetryBudget 0/2/0/1 · TranscodedOutputPlacement 20/3/4/3 · Strategies (5 files) 7/0/2/2 · JobProcessor 14/0/2/2 · ProcessTranscodeQueueService (supporting) 8/2/3/4

## Answers

### Q1. Who answers "profile / target kbps / target resolution"
Profile (8): raw MediaFiles.AssignedProfile reads (VideoVertical:36, PTQS:839/733, QMBS:156/945/1847); EffectiveProfileResolver._ResolveAssignedProfileName:54 (DefaultProfileName / _PreMigrationDefault fallback, persisted by QMBS:1629); FileTierResolver.Resolve:28 + TierLadderRepository.GetTierProfileName:119; ContentClassifierService._TierProfile:90 + _Walk:128; SeriesProfileService:32; NextTierAdjuster (Adjustments/NextTierAdjustmentCalculator.py:25); ProfileRepository.GetProfileIdByQualityLabel/Tier (QMBS:1757/1763); CommandComposer:54 label.
Target kbps (9): GetEncodeRow().TargetKbps (TierLadderRepository:104); GetProfileTarget:142; GetTierEncodeKbps:111; EffectiveProfileResolver.Resolve:44; QMBS._EncodeTargets:1377; QMBS.EvaluateQueueAdmissionForProfile:1525 + EstimateTargetSizeMB:1405 (CrfBitrateEstimates fallback); EncoderKnobRepository:137 (TargetKbps) and :114 (VideoBitrateKbps -> SVT -maxrate); WorkerEncoderResolver MaxBitrateMultiplier 2.0; VideoSlot:118/172.
Target resolution (9): GetProfileRow().TargetResolution (TierLadderRepository:94); EncoderKnobRepository:90; ResolutionCalculator.CalculateTargetResolution:20; EffectiveProfileResolver:46; QMBS:887 + ResolutionService.CompareResolutions; QMBS:1524 + upscale check :1468; QMBS.FindMatchingProfileThreshold:1197; WidthAnchoredScalePolicy via ResolutionCalculator:35; NextTierAdjuster (Profiles.TargetResolutionCategory).
ResolutionCategory derived 4 ways: ResolutionTierRegistry.FromDims (TierLadderRepository:64), CategoryStringFromResolution (MediaProbe:88, QMBS:1425/1638), TranscodedOutputPlacement:414-435 (hardcoded widths), ResolutionCalculator.GetSourceDimensions:84-91.
Lookup keys differ: compliance/priority key on ResolutionCategory; admission/encoder key on raw Resolution. Compliance (tier path) and encode (AssignedProfile) can read different profiles.

### Q2. Who decides audio tracks (7)
1. AudioSlot Copy:33/_CopyCodecArgs:37 maps all `0:a?`; reads AudioComplianceRules (AcceptableAudioCodecsCsv, Track0BitratePerChannelKbps) + MediaFiles.AudioCodec/AudioChannels; Transcode + Remux. Hardcoded 'aac'.
2. AudioFilterEmitter.EmitTracks:116; live ffprobe + AudioComplianceRules + AudioNormalizationConfig (LanguageDefault, EnableSpeechLanguageDetection) + MediaFileLanguageDetections; AudioFix only.
3. SourceAudioTrackSelector.SelectTrueSourceStreams:23.
4. PreEncodeAudioPipeline._SelectPreferredAudioIndex:163 (stream sent to Demucs; 'eng' hardcoded).
5. FFmpegAnalysisService.SelectPreferredAudioStream:210 (scan-time MediaFiles.AudioChannels/AudioLanguages/HasExplicitEnglishAudio). CommandComposer._EnrichAudioStreamIndex:194 writes Context['AudioStreamIndex'] that nothing reads.
6. AudioNormalizationConfig.EmitTracks read only by AudioPolicyAdmissionGate:127 / AudioStrategyClassifier:146 (admission, not emission).
7. AudioDispositionResolver.PickDefaultLanguage:45; ResolveForTrack:50 dead.
AudioStrategyClassifier uses -23 / -2 dBTP / tolerance 3 hardcoded (policy has no target columns); emitter uses AudioComplianceRules: admission and emission use different loudness targets. PreEncodeAudioPipeline:94 SourceMeasureTargetLra always 7.0 (column not in RULES_SELECT).

### Q3. FrameRate
No reads in the three verticals, admission, priority, EncoderKnobRepository, CommandComposer, slots, VideoFilterBuilder. Consumed only at DispositionDispatcher:164-182 and :195-207 (BitratePerPixel bucket) -> Decider._MaybeSmartConfidenceSkip:51-71 can Replace without VMAF; QualityTestingBusinessService:68-74 stats.

### Q4. VMAF thresholds
Read via PostTranscodeGateConfigRepository.Get:15-49 (model defaults 88/98 on missing row or exception). Compared at Decider:28-34, :61; QualityTestingBusinessService:72-74 and :1231-1233; SystemSettingsController:435. Hardcoded: Decider 80.0/97.0 defaults; model 88/98; FileReplacementBusinessService:343 (90.0); ActivityRepository:287 (>=90); TranscodeAttemptModel:97-101 (90/80/70 labels); QMBS:199/210 ("VMAF >= 80" text). Decider never reads New/Old size; FileReplacementBusinessService:232 refuses larger output after a committed Replace and fails the job. HandleTranscodingResult:1136 forces QualityTestRequired=True, overriding Profiles.QualityTestRequired.

### Q5. Writes to MediaFiles.AssignedProfile
Through Assign (MediaFilesRepository.WriteAssignedProfile:555): ContentClassifierService.ReassignTierProfiles:124, ClassifyAndAssign:157/176/183, ClassifyAndAssignBatch:234/236/238; QMBS:859; ProfileService.AssignProfileToRootFolder:175; SeriesProfileService:32.
Bypassing Assign: QMBS.RecomputeForFiles:1709-1715 bulk UPDATE (Assign's own cascade overwrites skip/NULL with EffectiveProfileResolver's default profile); QMBS.AddSuggestionsToQueue:568-572 raw UPDATE; QMBS.AddJobToQueue:1818-1819 via SaveMediaFile (also from DispositionDispatcher._DefaultRequeueScheduler:370); MediaFilesRepository.SaveMediaFile rewrites AssignedProfile from the in-memory model on every save (callers QMBS:2135, PTQS:1031, TranscodedOutputPlacement:494). Scripts: RemapXxxToTier1.py:25, CollapseProfilesToTierLadder_2026_07_09.py:162, ConsolidateCanaryProfileNames_2026_07_04.py:40, BackfillDataFixes.py:36/47, FixDefaultProfileIssue.py:38.

### Q6. Source delete/rename
TranscodedOutputPlacement.Execute:250 os.remove(original), ignores KeepSource; :131 removes original.bak; FilesystemRenameWithBackup.Apply:23 (original -> .bak same-slot), Commit:32 deletes it, Rollback:40/46; FinalizePartialReplacement:321 (CrashRecoveryService:139). Entry points: PTQS.DispatchDisposition:752, QualityTestingBusinessService:434/:1788, QualityTestController:1107, FileReplacementController:46, Scripts/Smoke/RunPostDispositionPipelineTest.py:110. NoAudioResolver.py:136 also deletes sources outside the disposition path.

## Notable findings
- RecomputeForFiles persists EffectiveProfileResolver's fallback (SystemSettings.DefaultProfileName then _PreMigrationDefault), undoing classifier skip and overwriting inactive/draft profiles.
- Transcode mode audio is Copy; WorkerEncoderResolver audio overrides (libopus/192/6ch) never apply; ContainerType only names the extension, muxer is always -f mp4. Container target defined 4x (ContainerComplianceRules, Profiles.Container/ContainerType, WorkerEncoderResolver, ContainerSlot).
- WorkerEncoderResolver hard-overrides DB knobs (preset, tune, multipass, rc, aq, pix fmt, MaxBitrateMultiplier 2.0) when Profiles.Codec == 'av1'. VideoSlot:39 ignores UseIntelHardware; QSV only when Codec == 'av1_qsv'. YadifMode/Parity/Deint knobs loaded but unused (yadif=1:1:1 hardcoded).
- ProcessingModeMetadata is a code mirror of the ProcessingModes table. Remux and AudioFix strategies are identical classes.
- VideoVertical profile path has a codec-skip (:58) that the tier path lacks: AV1 sources in tier libraries can be re-encoded.
- ContainerVertical verdict never reaches the emitter (ContainerSlot always mp4).
- FileTierResolver takes max genre tier; ContentClassResolver takes first genre with a class (inconsistent aggregation over the same Genres). Third content-class source: Profiles.ContentClass (DispositionDispatcher:164, NextTierAdjuster:29).
- Two retry budgets: RetryBudgetService + FailureBudgetService. Two "already transcoded" facts: TranscodeFiles.SuccessfullyTranscoded vs MediaFiles.TranscodedByMediaVortex.
- AudioVertical.Evaluate runs AudioPolicyAdmissionGate (side effects: MarkForRemeasurement / AddToReviewQueue) from a compliance evaluate; AddJobToQueue:1892 runs it again.
- AudioPolicyAdmissionGate backfill SQL omits 'folder' scope that the resolver includes.
- AudioPreEncodeFacade:85 and JobProcessor:83 call RecomputeForFiles mid-job (can rewrite AssignedProfile during an encode).
- DispositionDispatcher:75 exception -> 'Pending' (enqueues a QT on error). Decider ignores VmafCapableWorkerOnline, WhenVmafUnavailable, Old/NewSize inputs.
- TranscodedOutputPlacement:414-435 hardcoded ResolutionCategory widths (differs from ResolutionTierRegistry); :439 PostFlightRegistry result ignored; RemuxedByMediaVortex set but SaveMediaFile does not persist it; DetectNormalizationInCommand string-sniffs the ffmpeg command (duplicates DialogBoostEmitted).
- AddJobToQueue priority: None -> 0+15 always 15, ignores PriorityScore; AddSuggestions uses COALESCE(PriorityScore). QMBS:326 hardcoded LUFS window -24/-22.
- JobProcessor:79 hardcodes TargetLocalPath '-mv.mp4.ip' while Transcode-mode output name includes resolution + ContainerType extension.
- CRFOverride_<path> SystemSettings rows (PTQS:881-905) set Quality; irrelevant for NVENC VBR.
