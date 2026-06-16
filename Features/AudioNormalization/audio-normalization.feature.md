# Audio Normalization

**Slug:** audio-normalization

## What It Does

Owns every audio-policy decision and emits the ffmpeg argv that ships dual-track output on every encoded file. Two-knob normalization: TargetIntegratedLufs (inter-program consistency, default -23 LUFS) and TargetLra (intra-program dynamics, null = preserve source on Original / 11.0 on Dialog Boost). Every output ships two tracks per kept language: Original (LRA-preserved) + Dialog Boost (LRA-compressed, default-flagged in container). Settings hierarchy `item > folder > library > global`; per-scope override of every knob; mid-flight GUI changes observed by the next admission via fresh DB read.

The vertical absorbed the loudnorm measurement vertical (`Features/LoudnessAnalysis/` -> `Features/AudioNormalization/Measurement/EbuR128MeasurementService`) and the stream-copy-on-MP4-compat decision from `Features/AudioCompletion/`. The legacy `AudioFilterBuilder` + `UngainablePeakError` have been deleted; ungainable files are routed to operator review by the admission gate before they reach any shape.

## Workflows

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | Edit policy at any scope | Settings tab at `/AudioNormalization` | `POST /api/AudioNormalization/Settings` | `AudioNormalizationController.upsert_settings` |
| W2 | View consistency-band dashboard | Dashboard tab at `/AudioNormalization` | `GET /api/AudioNormalization/Dashboard` | `AudioNormalizationController.dashboard` |
| W3 | Review operator-held file + resolve | Review tab at `/AudioNormalization` | `POST /api/AudioNormalization/Review/<id>/Resolve` | `AudioOperatorReviewService.ResolveReview` |
| W4 | Trigger one-off policy snapshot on recent queue inserts | Dashboard tab "Run policy snapshot" button | `POST /api/AudioNormalization/SnapshotPolicies` | `AudioPolicyAdmissionGate.BackfillRecentInserts` |
| W5 | Run library-wide policy sweep | CLI script | `py Scripts/SweepAudioPolicyForExistingFiles.py [--apply]` | `Scripts/SweepAudioPolicyForExistingFiles.Main` |
| W6 | Mark a file for re-measurement | (internal -- admission gate) | -- | `AudioRemeasurementService.MarkForRemeasurement` |
| W7 | View speech-enrichment pending count | -- | `GET /api/AudioNormalization/EnrichmentQueue/Status` | `AudioNormalizationController.enrichment_status` |

## Success Criteria

C1. Every encoded output ships >=2 audio streams per kept language with one carrying the `Dialog Boost` title tag.

C2. Dialog Boost stream carries `disposition.default=1`; Original carries `=0`.

C3. Original measures LRA within +/-0.5 LU of `SourceLoudnessRangeLU`; Dialog Boost measures `LRA <= 11.0`.

C4. Source language streams preserved unless excluded by a per-scope `LanguageKeepPolicy`.

C5. Every shipped output has `AchievedIntegratedLufs` within +/-4 LU of effective `TargetIntegratedLufs`; classifier routes the rest to operator review.

C6. Files unable to satisfy +/-4 LU under any policy land on `MediaFiles.AdmissionDeferReason = 'operator_review_pending'` and surface in `/AudioNormalization` Review tab.

C7. Source file + `MediaFilesArchive` row are bit-exact-unchanged at every pipeline stage. Non-destructive by construction.

C8. Audio re-encode / channel mixdown / LRA compression run only on tracks explicitly enabled in resolved policy. Empty `EmitTracks` produces `-c:a copy` only.

C9. `AudioPolicyResolver.GetEffectivePolicy(MediaFile)` walks `item > folder > library > global` and returns the most-specific row.

C10. Every policy field editable at every scope via `/AudioNormalization` Settings tab; saved value applies to the next admission without WebService or WorkerService restart.

C11. `LanguageDetector.Detect` applies in order: ISO 639-2 tag, title regex `english|eng\b|en-us|en-gb`, single-audio-stream short-circuit, `disposition.default==1`, per-library default. Sixth layer reads `MediaFiles.AudioStreamLanguageDetectionsJson` cache when `EnableSpeechLanguageDetection=true`.

C12. Every `TranscodeQueue` row carries an `AudioPolicyJson` snapshot of the policy row that admitted it. Backfill via SQL post-INSERT.

C13. Files with `SourceIntegratedLufs <= -60` OR any of the four ebur128 columns NULL route to `AudioRemeasurementService`; `MediaFiles.AdmissionDeferReason = 'invalid_loudness_measurement'` until cleared.

C14. No encode shape (`TranscodeShape`, `RemuxShape`, `SubtitleFixShape`) contains `loudnorm`, `TargetLufs`, `TargetLra`, `acompressor`, or any audio-filter construction. All audio resolves through `AudioFilterEmitter.EmitTracks`.

C15. `TranscodeAttempts.AudioTracksEmittedJson` populated per-track post-encode by `PostEncodeMeasurementService`; dashboard at `/AudioNormalization` reads `v_audio_consistency_summary`.

C16. `Features/TranscodeJob/Emit/AudioFilterBuilder.py` + `UngainablePeakError.py` deleted; `grep -rn 'AudioFilterBuilder|UngainablePeakError' --include='*.py' .` returns 0 production hits.

C17. Each `EmitTracks` entry carries `Channels`; emitter emits `-ac:N <count>` per output stream.

C18. With no operator changes, every TranscodeQueue admission produces output processed through `AudioFilterEmitter`. Disabling normalization requires explicit `AudioNormalizationConfig.Enabled=false` at a scope.

C19. `LanguageEnrichmentService` scaffolds the 6th `LanguageDetector` layer with pluggable backend; default stub returns `und`. Cache-skip semantics ensure backend runs at most once per stream per file.

C20. `DialNormHandler` preserves source DialNorm on Original stream-copy; emits freshly computed `DialNorm = round(-1 * AchievedIntegratedLufs)` clamped to [1, 31] on re-encode.

C21. `Features/LoudnessAnalysis/LoudnessAnalysisService.py` -> `Features/AudioNormalization/Measurement/EbuR128MeasurementService.py`; all importers updated in same commit; `grep -rn 'from Features.LoudnessAnalysis' --include='*.py' .` returns 0.

C22. Stream-copy decision (MP4_COMPAT_AUDIO_CODECS + ShouldStreamCopy) absorbed into `AudioFilterEmitter`. AudioCompletion's audio-state-machine (AudioComplete / AudioCorruptSuspect column writes) preserved for compliance + FileReplacement pipelines; not in this vertical.

C23. `EmitTracks` carries Label, TargetLufs, TargetLra, Channels, Codec, Bitrate, SampleRateHz, BitDepth, LanguageFilter, IsDefaultTrack. `AudioNormalizationConfig` additionally carries KeepCommentaryTracks, EnableSpeechLanguageDetection, AudioDelayMs.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | Resolver -> Classifier | `AudioPolicyResolver.GetEffectivePolicy` | Policy dict (Scope, EmitTracks JSONB, Target* / UngainablePolicy / LoudnessTolerance) | `AudioStrategyClassifier.ClassifyTrack` reads TargetIntegratedLufs / TargetTruePeakDbtp / LoudnessTolerance / UngainablePolicy | `TestAudioPolicyResolver` 6 tests + `TestAudioStrategyClassifier` 11 tests |
| S2 | Classifier -> Emitter | `AudioStrategyClassifier.ClassifyTrack` | `TrackStrategy(Strategy, EffectiveTargetLufs, EffectiveTruePeakDbtp, EffectiveLra, Reason)` | `AudioFilterEmitter._BuildBlockForTrack` translates strategy into argv | `TestAudioFilterEmitter` 12 fixture tests |
| S3 | Emitter -> Shape | `AudioFilterEmitter.EmitTracks` | `List[TrackBlock]` each with `MapArgs / CodecArgs / FilterArgs / MetadataArgs / DispositionArgs` | `RemuxShape.Build` / `TranscodeShape.Build` / `SubtitleFixShape.Build` concatenate the slots into the ffmpeg command | `TestRemuxShape` / `TestTranscodeShape` / `TestSubtitleFixShape` |
| S4 | Admission Gate -> Queue | `AudioPolicyAdmissionGate.AdmitOrDefer` | `AdmissionDecision(Outcome, DeferReason, PolicyJson)` -- side effect: `MediaFiles.AdmissionDeferReason` set on deferred | `TranscodeQueue.AudioPolicyJson` snapshot populated via `BackfillRecentInserts` UPDATE | `TestAudioPolicyAdmissionGate` 6 tests + live SQL `SELECT COUNT(AudioPolicyJson) FROM TranscodeQueue` |
| S5 | DialNorm Handler -> Emitter | `DialNormHandler.ResolveForTrack` | int 1..31 or None | Emitter emits `-metadata:s:a:N dialnorm=<int>` | `TestDialNormHandler` 8 tests + `TestAudioFilterEmitter.test_h_*` |
| S6 | Measurement Service -> Validator | `EbuR128MeasurementService.MeasureAndPersist` -> `MediaFiles.SourceIntegratedLufs` / LRA / TP / Threshold | `LoudnessMeasurementValidator.IsValid` reads the four columns + silence floor predicate | `TestEbuR128MeasurementService` 6 tests + `TestLoudnessMeasurementValidator` 8 tests |
| S7 | Enrichment Service -> Detector Cache | `LanguageEnrichmentService.Enrich` writes `MediaFiles.AudioStreamLanguageDetectionsJson` | `LanguageDetector.Detect` 6th layer reads cache when `EnableSpeechLayer=True` | `TestLanguageEnrichmentService` 5 tests + `TestLanguageDetector.test_layer_speech_cache_when_enabled` |
| S8 | Post-Encode Probe -> Dashboard | `PostEncodeMeasurementService.Probe` writes `TranscodeAttempts.AudioTracksEmittedJson` | `v_audio_consistency_summary` view aggregates per-StorageRootId bands; dashboard renders | `TestPostEncodeMeasurementService` 4 tests + live `SELECT * FROM v_audio_consistency_summary` |

## Status

COMPLETE 2026-06-16. 116 contract tests green; production code paths verified.

Live-encode ffprobe smokes (Stage 7b DialNorm + Stage 8 AchievedLufs on real
encoded output) pending next WorkerService restart -- drain not safe with
active transcodes in-flight at delivery time.

## Files

| File | Role |
|------|------|
| Features/AudioNormalization/AudioPolicyResolver.py | 4-scope walk |
| Features/AudioNormalization/AudioStrategyClassifier.py | 5-route classifier |
| Features/AudioNormalization/AudioFilterEmitter.py | The seam: EmitTracks -> List[TrackBlock] |
| Features/AudioNormalization/AudioPolicyAdmissionGate.py | Pre-queue gate + PolicyJson snapshot |
| Features/AudioNormalization/AudioNormalizationController.py | Flask blueprint |
| Features/AudioNormalization/DialNormHandler.py | Dolby DialNorm preserve / compute |
| Features/AudioNormalization/LanguageDetector.py | 5+1 layered detection |
| Features/AudioNormalization/LoudnessMeasurementValidator.py | Validity + silence-floor predicate |
| Features/AudioNormalization/Measurement/EbuR128MeasurementService.py | ebur128 measurement + persistence |
| Features/AudioNormalization/Repositories/AudioNormalizationConfigRepository.py | Fresh DB read per call |
| Features/AudioNormalization/Services/AudioOperatorReviewService.py | Review queue ops |
| Features/AudioNormalization/Services/AudioRemeasurementService.py | Re-run ebur128 on invalid |
| Features/AudioNormalization/Services/LanguageEnrichmentService.py | Whisper-class scaffold |
| Features/AudioNormalization/Services/PostEncodeMeasurementService.py | Post-encode ffprobe |
| Templates/AudioNormalization.html | Settings/Dashboard/Review tabbed page |
| Scripts/SweepAudioPolicyForExistingFiles.py | Library-wide sweep |
