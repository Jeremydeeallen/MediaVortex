# Audio Tag Enrichment + Metadata-Only Fix Pipeline

**Slug:** audio-tag-enrichment-and-metadata-fix
**Set:** 2026-06-26
**Status:** Drafted (backlog) -- awaits activation

## Outcome

Files with missing or wrong audio-language tags (currently 5,132 of 51,521 in the library) are auto-detected via background Whisper-class enrichment, then corrected with a stream-copy metadata pass — no video re-encode. The scanner stays fast: probe finishes in seconds, files queued for async enrichment if needed, tags applied minutes-to-hours later in the background. Every knob exposed in the `/Compliance` Audio Rules tab plus a per-worker capability flag on `/Admin/Workers`.

## Why

Today's only way to fix an audio language tag is a full transcode (minutes per file, GPU work). For 5,132 files that's roughly 7 weeks of NVENC time on the current fleet. A `-c copy` metadata-only pass takes 5-10 seconds per file disk-I/O-bound, so the same 5,132 files finish in ~1.5 hours of wall clock. The `LanguageEnrichmentService` already exists with full test coverage but has zero production callers; the queue marker (`AdmissionDeferReason='awaiting_speech_enrichment'`) already exists in the schema. This directive wires the dormant pieces together and adds the missing two: the enrichment worker loop and the `MetadataUpdateShape`.

## Bounded Contexts (DDD)

Three contexts, each with explicit boundary + anti-corruption interface to the others:

### Context A: Audio Tag Enrichment

**Responsibility:** detect actual spoken language of audio streams, cache the result.

| Element | Type | Owns |
|---|---|---|
| `DetectedLanguage(StreamIndex, LanguageCode, Confidence, DetectorName)` | Value Object | One stream's detection result |
| `AudioStreamLanguageDetection` | Aggregate | All detections for a MediaFile (per-stream rows) |
| `ILanguageDetectionService` | Domain Service interface | Pure `Detect(audio_sample) -> DetectedLanguage` |
| `WhisperBaseLanguageDetectionService` | Concrete implementation | Whisper-base model + 30-sec audio sampling per stream |
| `IAudioStreamLanguageDetectionRepository` | Repository interface | Persistence-agnostic CRUD on detection cache |
| `MediaFilesAudioStreamLanguageDetectionRepository` | Concrete | Reads/writes `MediaFiles.AudioStreamLanguageDetectionsJson` |
| `AudioEnrichmentApplicationService` | Application Service | Use case: "enrich one media file"; orchestrates Detection + Repository |
| `AudioEnrichmentWorker` | Long-running worker | Polls `AdmissionDeferReason='awaiting_speech_enrichment'`, invokes ApplicationService one file at a time |

### Context B: Metadata-Only Fix

**Responsibility:** produce ffmpeg commands and execute them to update file metadata without re-encoding streams.

| Element | Type | Owns |
|---|---|---|
| `MetadataDelta(StreamIndex, Attribute, OldValue, NewValue, ReasonCode)` | Value Object | One concrete metadata change |
| `MetadataUpdatePlan` | Aggregate | All deltas for a MediaFile + their derivation chain |
| `IMetadataUpdatePolicy` | Domain Service interface | `GetDelta(MediaFile, AudioComplianceRules) -> List[MetadataDelta]` |
| `LanguageTagFromDetectionPolicy` | Concrete | Reads detection cache, emits `language=eng` deltas |
| `TrackTitleFromRulesPolicy` | Concrete (optional Phase 2) | Stamps "Original" / "Dialog Boost" titles |
| `DefaultDispositionFromRankPolicy` | Concrete (optional Phase 2) | Flips disposition.default per language rank |
| `MetadataUpdateShape` | EncodeShape | Builds `ffmpeg -c copy -metadata:s:a:N "language=eng" ...` command |
| `MetadataUpdateApplicationService` | Application Service | Use case: "fix metadata for one media file"; composes Plan + Shape |

### Context C: Compliance Routing

**Responsibility:** identify which bucket each MediaFile belongs to. NOT new in this directive but extended.

| Change | Where | Why |
|---|---|---|
| New `WorkBucket = 'MetadataOnly'` value | `MediaFiles.WorkBucket` enum + repository routing | Bucket-priority sit between `AudioFixOnly` and `None` |
| `AudioVertical.Evaluate` returns `(False, 'audio_tags_outdated_vs_cache')` when detection cache exists AND source tags disagree with it AND no other vertical-level issue exists | `Features/AudioNormalization/AudioVertical.py` | Existing data-driven pattern; one new branch |
| `QueueManagementBusinessService.EvaluateCandidateCompliance` priority: `Transcode > Remux > AudioFixOnly > MetadataOnly > None` | Same file | MetadataOnly slot between AudioFix and None per cheaper-fixes-later ordering |

### Anti-Corruption Layers (DDD)

| Boundary | Direction | Shape |
|---|---|---|
| Context A → Context B | Cache shared | `IAudioStreamLanguageDetectionRepository` is the single read interface |
| Context B → Context C | Bucket assignment | `IMetadataUpdatePolicy.GetDelta(...)` is the pure-function input for the routing decision |
| Context A → Scanner (`MediaProbeBusinessService`) | Probe-time marking | `AudioEnrichmentApplicationService.MarkForEnrichment(MediaFileId)` -- scanner never touches the deferred-reason column directly |

## SOLID Compliance

| Principle | How |
|---|---|
| **SRP** | One concrete class per responsibility. `WhisperTinyLanguageDetectionService` does NOT manage queues. `AudioEnrichmentWorker` does NOT decode audio. `MetadataUpdateShape` does NOT decide WHAT to update. |
| **OCP** | Adding `WhisperBaseLanguageDetectionService` = new `ILanguageDetectionService` impl + composition root row, zero changes to ApplicationService, Worker, or callers. Adding a new metadata-fixable attribute (track title, default flag) = new `IMetadataUpdatePolicy` impl. |
| **LSP** | All `ILanguageDetectionService` implementations return `DetectedLanguage`. All `IMetadataUpdatePolicy` implementations return `List[MetadataDelta]`. All EncodeShape implementations return `CommandSpec`. No surprise return types. |
| **ISP** | `ILanguageDetectionService` is just `Detect`. `IMetadataUpdatePolicy` is just `GetDelta`. No god interfaces. |
| **DIP** | `AudioEnrichmentApplicationService` depends on `ILanguageDetectionService` + `IAudioStreamLanguageDetectionRepository` interfaces; concretes constructor-injected at the composition root. Same for `MetadataUpdateApplicationService`. |

## Acceptance Criteria

C1. **Scanner stays fast.** `MediaProbeBusinessService._ExecuteProbe` extends `RecomputeForFiles` to call `AudioEnrichmentApplicationService.MarkForEnrichment(MediaFileId)` for files with untagged audio + `EnableSpeechLanguageDetection=true`. Wall-clock for one probe rises by ≤ 50ms (just a column update). Verifiable: contract test asserts probe time delta under 50ms; existing `Tests/Pipeline/test_transcode_dual_pipeline.py` covers the timing.

C2. **EnrichmentWorker is a real worker loop.** New `Workers.EnrichmentEnabled` boolean column (operator-tunable per worker via `/Admin/Workers`). Workers with the flag set poll `MediaFiles WHERE AdmissionDeferReason='awaiting_speech_enrichment'` in batches of `AudioComplianceRules.EnrichmentBatchSize` (default 50) every `AudioComplianceRules.EnrichmentPollIntervalSec` seconds (default 60), call `AudioEnrichmentApplicationService.Enrich(MediaFileId)`, clear the deferred reason on success. One contract test: synthetic `MediaFile` with marker → worker → cache populated → marker cleared.

C3. **MetadataUpdateShape exists and is a peer of TranscodeShape/RemuxShape.** Implements the `EncodeShape` interface; built command is `ffmpeg -i <in> -c copy <metadata args> -movflags +faststart -y <out>`. Registered in `EncodeShapeRegistry` against `ProcessingMode='MetadataOnly'`. Contract test: build for a synthetic MediaFile with two `MetadataDelta` rows; assert no `-c:v` / `-c:a` codec args, asserts `-metadata:s:a:0 "language=eng"` present, asserts `-movflags +faststart` present, asserts output path ends `-mv.mp4.inprogress`.

C4. **MetadataUpdateApplicationService composes Plan + Shape.** Single `Process(MediaFileId)` method: loads cache, runs every active `IMetadataUpdatePolicy` to assemble a `MetadataUpdatePlan`, hands the Plan to `MetadataUpdateShape.Build`, returns `CommandSpec`. Worker invokes it from the existing claim path; file replacement is unchanged. Contract test asserts: identical-tags input → empty plan → no command emitted (no-op); different tags input → plan with N deltas → command contains N metadata args.

C5. **`AudioVertical.Evaluate` identifies metadata-fixable state.** New branch: when `AudioComplianceRules.EnableSpeechLanguageDetection=true` AND cache exists for the MediaFile AND any cached language differs from source tag AND no codec/bitrate/resolution issue exists, returns `(False, 'audio_tags_outdated_vs_cache')`. Routing in `QueueManagementBusinessService.EvaluateCandidateCompliance` maps that reason to `WorkBucket='MetadataOnly'`. Contract test: file with `und` tag + cache says `eng` + clean video/container → bucket `MetadataOnly`.

C6. **All operator levers in the UI.** `/Compliance` Audio Rules tab + `/Admin/Compliance` Audio Rules tab gain six new rows in the existing form (above the current Save button):

- `EnrichmentBatchSize` (number, default 50) -- per poll
- `EnrichmentPollIntervalSec` (number, default 60)
- `MaxConcurrentEnrichmentJobs` (number, default 2) -- per worker
- `EnableMetadataLanguageFix` (boolean, default true) -- enable LanguageTagFromDetectionPolicy
- `MetadataReDetectOnSourceChange` (boolean, default true) -- when MediaFile.LastModified changes, clear cache + re-mark. Default true closes the silent-stale-cache footgun.

Plus an existing-row update:

- `EnableSpeechLanguageDetection` toggle gains a single-click "Recompute language detection for all non-English-tagged files (N)" button -- triggers `MarkForEnrichment` against every non-English-tagged MediaFile. Confirmation modal shows the live count. Worker pool batches via `EnrichmentBatchSize`; no UI-side batching exposed.

**Decision: WhisperModel is NOT a UI field.** WhisperBase is the chosen production detector (locked in; see Decisions Made). Adding a model selector would expose a worker-side implementation detail to the operator without a real use case for switching. If a different detector is ever needed, it's a new `ILanguageDetectionService` concrete + composition root switch (OCP), not a per-deploy operator decision.

C7. **Per-worker enrichment capability flag.** `/Admin/Workers` tile gains an "Enrichment" sub-badge (parallel to existing Transcode / Remux / QT / Scan badges). Operator-editable via existing `Workers` row UPDATE path. ClaimEnrichmentJob is gated by `Workers.EnrichmentEnabled=TRUE` (parallel to `TranscodeEnabled`).

C8. **No silent failures.** One typed exception per context: `AudioEnrichmentError(MediaFileId, DetectorName, Reason)` covers all detection failures, `MetadataUpdateError(MediaFileId, Reason)` covers all metadata-update failures. Resist granular exception hierarchies -- operators want to know "did this fail," not "what subclass of failure was it." Worker catches, writes `TranscodeAttempts` row with `Success=FALSE`, `AdmissionDeferReason` cleared but `EnrichmentFailureReason` populated. Operator reviews failed enrichments in the existing operator-review surface. Contract test verifies the loud-failure path.

C9. **End-to-end smoke.** Live smoke against three real files from your library:
- file with `und` tag + English audio → marker set → enrichment runs → cache populated → MetadataOnly bucket → `-c copy + metadata language=eng` → file replaced → tag now `eng`, encoded duration unchanged, file size delta < 1% (just metadata bytes)
- file with `eng` tag already correct → marker never set (early-out in scanner); no work performed
- file with mixed language audio (`eng` + `jpn`) → enrichment detects both → MetadataOnly fix stamps both → file replaced

## Files (planned)

| File | Role |
|---|---|
| `Scripts/SQLScripts/AddAudioEnrichmentLeversToComplianceRules_2026_07_XX.py` | Adds six new columns + Workers.EnrichmentEnabled (idempotent, R11) |
| `Features/AudioNormalization/Enrichment/ILanguageDetectionService.py` | Interface only (one class per file, SRP) |
| `Features/AudioNormalization/Enrichment/WhisperBaseLanguageDetectionService.py` | The single production detector (CPU, Whisper Base, 30-sec audio sample). Other model sizes or a GPU variant are added later via OCP without changing callers if scale ever requires it. |
| `Features/AudioNormalization/Enrichment/AudioStreamLanguageDetection.py` | Value object + Aggregate |
| `Features/AudioNormalization/Enrichment/IAudioStreamLanguageDetectionRepository.py` | Repository interface |
| `Features/AudioNormalization/Enrichment/MediaFilesAudioStreamLanguageDetectionRepository.py` | Concrete repository |
| `Features/AudioNormalization/Enrichment/AudioEnrichmentApplicationService.py` | Use cases: `MarkForEnrichment`, `Enrich` |
| `Features/AudioNormalization/Enrichment/AudioEnrichmentError.py` | Single typed exception covering all detection failures |
| `WorkerService/EnrichmentWorker.py` | Long-running poll loop, gated by `Workers.EnrichmentEnabled` |
| `Features/TranscodeJob/Emit/MetadataUpdateShape.py` | New EncodeShape parallel to RemuxShape |
| `Features/AudioNormalization/MetadataFix/MetadataDelta.py` | Value object |
| `Features/AudioNormalization/MetadataFix/MetadataUpdatePlan.py` | Aggregate |
| `Features/AudioNormalization/MetadataFix/IMetadataUpdatePolicy.py` | Interface + LanguageTagFromDetectionPolicy concrete |
| `Features/AudioNormalization/MetadataFix/MetadataUpdateApplicationService.py` | Composes Plan + Shape, invoked from worker claim path |
| `Features/AudioNormalization/MetadataFix/MetadataUpdateError.py` | Single typed exception covering all metadata-update failures |
| `Features/TranscodeJob/Emit/EncodeShapeRegistry.py` | EDIT -- register MetadataOnly mode |
| `Features/AudioNormalization/AudioVertical.py` | EDIT -- new `audio_tags_outdated_vs_cache` branch in Evaluate |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | EDIT -- routing reason → MetadataOnly bucket |
| `Features/MediaProbe/MediaProbeBusinessService.py` | EDIT -- post-probe call to `MarkForEnrichment` |
| `Features/AudioNormalization/AudioNormalizationController.py` | EDIT -- six new lever validations in PUT `/api/AudioNormalization/Rules`; new "Recompute now" endpoint |
| `Features/Admin/Workers/AdminWorkersRepository.py` | EDIT -- surface `EnrichmentEnabled` column in GetTiles |
| `Templates/AdminCompliance.html` + `Templates/Compliance.html` | EDIT -- six new form rows + Recompute-now button + JS |
| `Templates/AdminWorkers.html` | EDIT -- Enrichment sub-badge per tile |
| `Tests/Contract/TestAudioEnrichmentApplicationService.py` | NEW -- C2 |
| `Tests/Contract/TestMetadataUpdateShape.py` | NEW -- C3 |
| `Tests/Contract/TestMetadataUpdateApplicationService.py` | NEW -- C4 |
| `Tests/Contract/TestAudioVerticalRoutesToMetadataOnly.py` | NEW -- C5 |
| `Tests/Contract/TestEnrichmentFailLoud.py` | NEW -- C8 |
| `Features/AudioNormalization/audio-normalization.feature.md` | EDIT (at DELIVERING) -- promote new criteria C18-C23 covering enrichment + metadata-fix bucket |

## Phases (each phase ends with live restart + targeted smoke per `feedback_smoke_test_per_step_not_at_end`)

| Phase | Work | Exit gate |
|---|---|---|
| A | Migration: 6 new AudioComplianceRules columns + `Workers.EnrichmentEnabled` + `MediaFiles.EnrichmentFailureReason`. No code change. Idempotent. | Migration applies clean; re-run reports no-op; WebService + WorkerService restart clean. |
| B | Detection layer (Context A internals): `ILanguageDetectionService` + `WhisperBaseLanguageDetectionService` concrete + `DetectedLanguage` VO + repository interface + concrete repository. Standalone unit tests; not yet wired to a worker. | Unit tests green. Synthetic invoke of `WhisperBaseLanguageDetectionService.Detect(known_audio_sample)` returns expected language code with confidence >= 0.85 across 5 known-language samples (eng / jpn / fra / deu / spa). |
| C | `AudioEnrichmentApplicationService` + `EnrichmentFailedError`. Composes detection + repository. Marks/clears `AdmissionDeferReason`. | Contract test green: synthetic MediaFile + audio sample → service marks → enriches → cache populated → marker cleared. |
| D | `EnrichmentWorker` loop wired into `WorkerService/Main.py`. Gated by `Workers.EnrichmentEnabled`. Polls + processes batch. | Live: one Worker's EnrichmentEnabled flipped TRUE → flagged MediaFile gets enriched within `EnrichmentPollIntervalSec`. Cache row appears. Operator can see count drop via `/api/AudioNormalization/EnrichmentQueue/Status`. |
| E | `MetadataUpdateShape` + `MetadataDelta` + `MetadataUpdatePlan` + `IMetadataUpdatePolicy` interface + `LanguageTagFromDetectionPolicy` concrete + `MetadataUpdateApplicationService` + `MetadataUpdateFailedError`. Not yet wired to bucket routing. | Contract test green: synthetic MediaFile + cache row → plan has 1 delta → shape builds `ffmpeg -c copy -metadata:s:a:0 "language=eng" ...` command. |
| F | `AudioVertical` new branch + `QueueManagementBusinessService` routing + `EncodeShapeRegistry` registration of MetadataOnly. | Contract test green: routing correctly maps reason → bucket → shape. Live smoke: one cache-populated file inserts to TranscodeQueue with ProcessingMode=MetadataOnly; worker claims; file replaced; tag now correct in re-probe. |
| G | UI: six new form rows on both compliance pages + Recompute-now button. Enrichment sub-badge on `/Admin/Workers` tiles. Live ui-verify against both pages: all new elements present, Save round-trips, badge renders. | ui-verify green on both compliance pages + admin-workers page. |
| H | End-to-end smoke: three real files per C9. | All three files end up correctly tagged with no re-encode. SizeMB delta < 1% on each. |

## Out of Scope

- Video metadata fixes (chapter markers, embedded artwork) -- could be added later as additional `IMetadataUpdatePolicy` implementations without architectural change.
- Subtitle stream additions / language fixes -- separate vertical.
- Container-level metadata (title, description) -- can be added trivially as another `IMetadataUpdatePolicy`.
- Whisper model download / GPU acceleration -- assume CPU Whisper-tiny initially; GPU variant lands as new `ILanguageDetectionService` implementation later.

## Decisions Made (locked in 2026-06-26)

These are not options. Each has a specific reason for being this answer and not another.

1. **Detector: Whisper Base, single concrete.** Not tiny (95% accuracy means ~250 misdetected files out of 5,132 -- a silent-error class). Not small or medium (6x slower for an imperceptible accuracy bump). Base sits at the inflection where accuracy stops improving meaningfully -- ~98-99% language ID across noisy / clean / accented / dialog-over-music. Sample size: 30 sec of audio per stream. Wall-clock: ~1.5 sec/file, ~16 min total for the initial 5,132-file backfill on 8-way fleet. Not surfaced in the UI; if a different detector is ever needed it's a new `ILanguageDetectionService` concrete + composition root switch (OCP) without changing callers.

2. **CPU only. No GPU detection.** Building both means maintaining both forever. GPU on dot would contend with the NVENC encode workload we just stabilized; Larry has no GPU and would diverge silently. 16-min initial backfill vs 2-min on GPU is a 14-min one-time saving against permanent architectural complexity. If scale ever requires it (e.g., 200K-files-of-inflow ongoing), a `WhisperBaseGpuLanguageDetectionService` lands as a new concrete -- zero changes to `AudioEnrichmentApplicationService`, `EnrichmentWorker`, or persistence.

3. **Recompute-now: single-click "Mark all N" with confirmation modal.** No per-click batching exposed in the UI. The worker pool batches naturally via `EnrichmentBatchSize`. UI batching would be exposing a worker-pool implementation detail to the operator.

4. **`MetadataReDetectOnSourceChange` default: TRUE.** When `MediaFile.LastModified` advances (re-scan picks up replaced file), the cached detection becomes stale. Defaulting false means stale cache survives silently -- silent-error class. Default true closes the footgun.

5. **Detection cache stays on `MediaFiles.AudioStreamLanguageDetectionsJson`.** Resist the DDD temptation to extract a separate `AudioStreamLanguageDetections` table. The cache is per-MediaFile, lifecycle is tied to MediaFile, JSON column already exists in the schema. A separate table would add a JOIN cost on every compliance recompute, two-phase commit semantics for cache invalidation, and zero functional benefit.

6. **`ProcessingMode='MetadataOnly'` lives in the same enum as Transcode/Remux/AudioFix.** Not a separate column. Not a separate routing path. Same bucket-priority cascade in `EvaluateCandidateCompliance`. Same worker claim path. The only new thing is `MetadataUpdateShape` registered in `EncodeShapeRegistry` -- same Strategy pattern that already works for the three existing shapes.

7. **One typed exception per bounded context, not three.** `AudioEnrichmentError(MediaFileId, DetectorName, Reason)` covers all detection failures. `MetadataUpdateError(MediaFileId, Reason)` covers all metadata-update failures. Resist granular exception hierarchies.

8. **No `WhisperModel` field in the operator UI.** That's a worker-side implementation detail; surfacing it would invite operator-side per-deployment customization with no real use case. See decision 1.

## Activation Protocol

```powershell
git mv .claude/directives/backlog/audio-tag-enrichment-and-metadata-fix.md .claude/directive.md
# Edit Status: Active -- phase: NEEDS_STANDARDS_REVIEW
```
