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
| W8 | View self-healing actions taken in last 24h | Activity page Library Compliance card "Self-healing" sub-section | `GET /api/Activity/LibraryCompliance` (AudioVerticalHealth key) | `ActivityRepository.GetAudioVerticalHealth` |
| W9 | Run the live-DB invariant probe | CLI | `py -m pytest Tests/Contract/TestAudioInvariants.py` | `TestAudioInvariants` reuses H1 invariant detectors against live DB |
| W10 | Pick pre-vertical re-normalize policy | Settings tab field `PreVerticalReNormalizePolicy` | `POST /api/AudioNormalization/Settings` | `AudioNormalizationConfigRepository` writes the column |

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

C23. `EmitTracks` carries Label, TargetLufs, TargetLra, Channels, Codec, Bitrate, SampleRateHz, BitDepth, LanguageFilter, IsDefaultTrack. `AudioNormalizationConfig` additionally carries KeepCommentaryTracks, EnableSpeechLanguageDetection, AudioDelayMs, LanguageDefault, PreVerticalReNormalizePolicy.

## SOLID Compliance (added 2026-06-17)

S1. `AudioFilterEmitter._BuildBlockForTrack` is a thin orchestrator. The
codec / filter / metadata / dialnorm / disposition / stream-copy decisions
each live in their own per-concern helper method (`_DecideStreamCopyOrReencode`,
`_BuildCodecArgs`, `_BuildFilterArgs`, `_BuildMetadataArgs`,
`_BuildDialNormArgs`, `_BuildDispositionArgs`). Each helper has a per-helper
contract test. SRP at the method level.

S2. The audio-state machine (`MarkAudioComplete`, `ResetAudioComplete`,
`MarkAudioCorruptSuspect`, `EvaluateInitialAudioState`,
`ShouldStreamCopyAudio`, `DetectNormalizationInCommand`,
`DetectNormalizationMode`) lives in `Features/AudioNormalization/Services/
AudioStateService.py`. The legacy name `AudioCompletionService` does not
exist post-2026-06-17 -- naming reflects its role as the audio-state
machine on `MediaFile`.

S3. Audio integration on the worker side -- post-encode probe + canonical
path resolution -- lives in `Features/AudioNormalization/Workers/
PostEncodeAudioHandler.py`. `ProcessTranscodeQueueService` constructor-
injects this collaborator (DIP) and does not own the implementation.

S4. Every integration boundary the vertical adds (QMBS post-INSERT hook,
ComplianceGate language-tag override, `_PostReplacementCanonicalPath` SQL
resolver, PostEncodeAudioHandler invocation) has its own contract test
under `Tests/Contract/`. Boundaries protected against regression at the
test layer, not by live-encode discovery.

## Self-Healing (added 2026-06-17)

The vertical detects and heals its own DB-state discrepancies via an
in-system recurring service. Operator does not run scripts to fix
vertical state.

H1. `AudioVerticalHealthService` (`Features/AudioNormalization/SelfHealing/
AudioVerticalHealthService.py`) runs every
`SystemSettings.AudioVerticalHealthIntervalSec` seconds (default 300) on
the WebService background-thread cadence. Constructor injects
`List[IAudioVerticalInvariant]` and a per-invariant
`Dict[invariant_name -> IAudioVerticalRemediation]`. Each cycle: for each
invariant -> `Detect()` returns offending row ids -> matched
`Remediation.Apply()` runs per id -> result written to
`AudioVerticalHealthRuns` table (one row per cycle x invariant).

Six invariants ship in the initial composition:
- `PendingQueueWithoutPolicyJson` -> `BackfillPolicyJson` remediation
- `SuccessfulAttemptWithoutTracksEmitted` -> `EnqueueReProbe` remediation
- `StaleOperatorReview` (>30 days) -> `AlertOperatorReview` remediation
- `InvalidMeasurementWithoutRemeasure` (>24h, 0 attempts) ->
  `EnqueueRemeasurement` remediation
- `PreVerticalTranscodedFile` (gated by `PreVerticalReNormalizePolicy`
  policy field) -> `EnqueueRetranscode` remediation
- `ConsistencyBandDeviantWithComplete` -> `EnqueueRemeasurement`
  remediation

H2. `Scripts/SweepAudioPolicyForExistingFiles.py` does not exist post
2026-06-17. The H1 service's
`PendingQueueWithoutPolicyJson` + `BackfillPolicyJson` pair owns the
same use case continuously.

H3. `Tests/Contract/TestAudioInvariants.py` runs against the live DB.
Each test instantiates the matching `IAudioVerticalInvariant` and asserts
`Detect()` returns zero violations. Failing tests name offending row ids.
This is the canonical "is the vertical healthy" probe -- same code path
as H1 detection (DRY).

H4. `/api/Activity/LibraryCompliance` payload carries `AudioVerticalHealth:
{LastRunAt, ActionsLast24h: {<invariant>: count}}`. `Templates/Activity.html`
Library Compliance card has a `Self-healing (last 24h)` sub-section
rendering the counts.

## Operational (added 2026-06-17)

O1. Stale-code Linux containers are paused at the DB level. Status
'Paused' + `PauseReason` set on every Worker row whose deployed `Version`
diverges from `HEAD` of the source tree at WebService startup. The pause
holds until a redeploy aligns the version.

O2. `AudioNormalizationConfig.PreVerticalReNormalizePolicy TEXT NOT NULL
DEFAULT 'lazy'` IN ('aggressive', 'lazy', 'none'). Default 'lazy' --
H1's `PreVerticalTranscodedFile` invariant skips them; operator manual
queue still works; aggressive flips to auto re-normalize on the next
H1 cycle.

## Live Verification (added 2026-06-17)

L1. Multi-language live encode -- a source MediaFile with 2 distinct
language audio streams encodes through the emitter and produces 4 output
streams (2 emit-tracks x 2 source languages). Each Original output tagged
with its source language; each Dialog Boost output tagged with its source
language. Contract test `TestMultiLanguageLiveEncode.py` asserts ffprobe
output shape; live run on a real 2-language source recorded in directive
verification.

L2. MP4 title-tag fidelity -- ffprobe of an emitter-produced output
either shows `tags.title=Original` / `tags.title=Dialog Boost` on the
two audio streams, OR criterion C1 is amended in writing here to identify
Dialog Boost by `disposition.default=1` + stream-index convention (with
the spec reference for why MP4 cannot carry per-audio-stream title).
No silent deferral.

L3. Whisper backend live verified -- a synthetic file with no language
tag, scope-configured with `EnableSpeechLanguageDetection=true` and
`SystemSettings.WhisperModelPath` set to a deployed Whisper-compatible
model, produces a real detected language in
`MediaFiles.AudioStreamLanguageDetectionsJson` cache after the
enrichment job runs. OR operator explicitly states stub is acceptable
and this criterion is amended in writing.

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
| S9 | Invariant Detector -> Remediation | `IAudioVerticalInvariant.Detect()` returns `List[<offending_row_id>]` per invariant kind | `IAudioVerticalRemediation.Apply(row_id)` -> structured outcome (Acted / NoOp / Error) | `TestAudioInvariants` against live DB + per-invariant unit tests with fixture seeds |
| S10 | HealthService -> Audit | `AudioVerticalHealthService` writes per-cycle results | `AudioVerticalHealthRuns` row (`Timestamp`, `InvariantName`, `DetectedCount`, `RemediatedCount`, `DurationMs`) | `SELECT * FROM AudioVerticalHealthRuns ORDER BY Timestamp DESC LIMIT N` per `/api/Activity/LibraryCompliance` consumer |
| S11 | Worker version -> Pause | WebService startup compares `Workers.Version` vs `HEAD` SHA at code root | Mismatched workers -> `UPDATE Workers SET Status='Paused', PauseReason='version drift: <sha> vs <HEAD>'` | Boot-time check + Activity dashboard worker tile shows the pause reason |
| S12 | PostEncodeAudioHandler -> Probe | `PostEncodeAudioHandler.HandlePostEncode(AttemptId, MediaFileId)` resolves canonical path -> invokes `PostEncodeMeasurementService.Probe` | `TranscodeAttempts.AudioTracksEmittedJson` row updated | `TestPostEncodeAudioHandler` with mocked probe |
| S13 | ComplianceGate -> Emitted Language Tags | `FFmpegCommand` carries `-metadata:s:a:N "language=eng"` | `ComplianceGate.Evaluate` overrides candidate row's `AudioLanguages` + `HasExplicitEnglishAudio` from parsed emitted tags before evaluating | `TestComplianceGateLanguageOverride` |
| S14 | QMBS Post-INSERT -> Gate | Bulk-INSERT commits land Pending rows | `_SnapshotAudioPoliciesOnRecentInserts` -> `AudioPolicyAdmissionGate.BackfillAllPending` updates the new rows' `AudioPolicyJson` | `TestQueueManagementBusinessServiceHook` |

## Status

C1-C23 shipped 2026-06-16 + live-verified on MediaFile 690392 2026-06-17.
S1-S4 SOLID compliance + H1-H4 self-healing + L1-L3 live verification +
O1-O2 operational are tracked under directive
`audio-vertical-perfection-and-self-healing` (open 2026-06-17). 116+
contract tests green at prior close; new test suites land per S4 / H3 /
L1 substages.

## Files

| File | Role |
|------|------|
| Features/AudioNormalization/AudioPolicyResolver.py | 4-scope walk |
| Features/AudioNormalization/AudioStrategyClassifier.py | 5-route classifier |
| Features/AudioNormalization/AudioFilterEmitter.py | The seam: EmitTracks -> List[TrackBlock]; orchestrator over 6 per-concern helpers (S1) |
| Features/AudioNormalization/AudioPolicyAdmissionGate.py | Pre-queue gate + PolicyJson snapshot + BackfillAllPending (no time window) |
| Features/AudioNormalization/Services/AudioStateService.py | Audio-state machine on MediaFile (S2; renamed from AudioCompletionService) |
| Features/AudioNormalization/Workers/PostEncodeAudioHandler.py | Post-encode probe + canonical-path resolve (S3; extracted from ProcessTranscodeQueueService) |
| Features/AudioNormalization/SelfHealing/AudioVerticalHealthService.py | Recurring scan + remediation (H1) |
| Features/AudioNormalization/SelfHealing/IAudioVerticalInvariant.py | ABC for invariant detectors (OCP) |
| Features/AudioNormalization/SelfHealing/IAudioVerticalRemediation.py | ABC for remediations (OCP) |
| Features/AudioNormalization/SelfHealing/Invariants/*.py | Per-kind invariant impls (6 ship) |
| Features/AudioNormalization/SelfHealing/Remediations/*.py | Per-action remediation impls (5 ship) |
| Tests/Contract/TestAudioInvariants.py | Live-DB invariant probe (H3) |
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
