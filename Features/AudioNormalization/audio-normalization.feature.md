# Audio Normalization

**Slug:** audio-normalization

## What It Does

Owns every audio-policy decision and emits the ffmpeg argv that ships dual-track output on every encoded file. Two-knob normalization: TargetIntegratedLufs (inter-program consistency, default -23 LUFS) and TargetLra (intra-program dynamics, null = preserve source on Original / 11.0 on Dialog Boost). Every output ships two tracks per kept language: Original (LRA-preserved) + Dialog Boost (LRA-compressed, default-flagged in container). Settings hierarchy `item > folder > library > global`; per-scope override of every knob; mid-flight GUI changes observed by the next admission via fresh DB read.

The vertical absorbed the loudnorm measurement vertical (`Features/LoudnessAnalysis/` -> `Features/AudioNormalization/Measurement/EbuR128MeasurementService`) and the stream-copy-on-MP4-compat decision from `Features/AudioCompletion/`. The legacy `AudioFilterBuilder` + `UngainablePeakError` have been deleted; ungainable files are routed to operator review by the admission gate before they reach any shape.

## Workflows

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W0 | Edit system-wide audio compliance rules (target LUFS, true peak ceiling, overshoot thresholds, codec allowlist, dialog-boost toggle, English-preferred toggle, language rank, speech-detection toggle) | `/Admin/Compliance` Audio Rules tab + `/Compliance` Audio tab | `PUT /api/AudioNormalization/Rules` | `AudioNormalizationController.update_audio_rules` (writes the AudioComplianceRules singleton row + spawns daemon-thread backfill via `AudioVertical().RecomputeFor`) |
| W1 | Edit policy at any scope (per-library, per-folder, per-item overrides) | Settings tab at `/AudioNormalization` | `POST /api/AudioNormalization/Settings` | `AudioNormalizationController.upsert_settings` |
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

C4. Source language streams preserved; per-scope `LanguageDefault` picks the default disposition.

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

C21. `Features/LoudnessAnalysis/LoudnessAnalysisService.py` -> `Features/AudioNormalization/Measurement/EbuR128MeasurementService.py`; all importers updated in same commit; `grep -rn 'from Features.LoudnessAnalysis' --include='*.py' .` returns 0.

C22. Stream-copy decision (MP4_COMPAT_AUDIO_CODECS + ShouldStreamCopy) absorbed into `AudioFilterEmitter`. AudioCompletion's audio-state-machine (AudioComplete / AudioCorruptSuspect column writes) preserved for compliance + FileReplacement pipelines; not in this vertical.

C23. `EmitTracks` carries Label, TargetLufs, TargetLra, Channels, Codec, Bitrate, SampleRateHz, BitDepth, LanguageFilter, IsDefaultTrack. `AudioNormalizationConfig` additionally carries EnableSpeechLanguageDetection, LanguageDefault, PreVerticalReNormalizePolicy, MaxAudioChannels.

C24. [BUG-0065] When a media file carries multiple language audio streams and no per-scope `AudioNormalizationConfig.LanguageDefault` is set, the English track receives `disposition.default=1` on the output. The implicit fallback chain in `_PickDefaultLanguage` becomes: (1) per-scope `LanguageDefault` if set, (2) English if any present stream resolves to English via `LanguageDetector.Detect`, (3) source's per-stream `disposition.default==1`, (4) first present language. Verifiable: encode a source with `eng` + `jpn` audio streams, no per-scope override -- the `eng` Dialog Boost track is the only output stream with `disposition.default=1`; flip the source so `jpn` carries `disposition.default==1` -- the `eng` track still wins. Operator-set `LanguageDefault='jpn'` overrides the rule and the `jpn` track wins. Conforms to C25 -- the rule that won must be recorded; silent cascades are forbidden.

C25. [BUG-0066] No silent fallback chains in the audio pipeline. Every decision that today reads "rule A, falling back to rule B, falling back to rule C" must either (a) collapse to a single explicit rule that fails loud when it doesn't apply, OR (b) return a tagged result naming WHICH rule fired and persist that name to a queryable column (e.g. `TranscodeAttempts.AudioTracksEmittedJson`). Applies at minimum to `LanguageDetector.Detect` (C11) and `_PickDefaultLanguage` (L1). Verifiable: for any encoded output, an operator can SELECT from `TranscodeAttempts` and see, per audio track, which language-pick rule and which default-pick rule produced the result; a contract test asserts that across 50 sample encodes the rule-name field is never null and never `"fallback"`. The operator must be able to answer "is rule 1 still working?" by querying the rule-firing distribution, not by reasoning about which fallback didn't trigger.

C26. PROFILE_CEILING holds unconditionally. `AudioFilterEmitter` has no `STRATEGY_REVIEW: continue` branch; REVIEW classifier output routes through `AudioDispositionResolver.ResolveForTrack` (via `_BuildReviewFallbackBlock`), which clamps emitted bitrate to `Profile.TargetAudioKbps` or raises `AudioPolicyUnresolvedError` when neither ceiling nor config bitrate is available. `TranscodeShape` has no literal `['-c:a', 'copy']` extend; codec args for the empty-Blocks branch come from `EAC3OrPassthroughCodecPolicy.Decide`. Verifiable: `Tests/Contract/TestAudioBitratePolicyHonorsCeiling.py` (REVIEW + truehd source emits eac3 at ceiling; REVIEW + aac emits stream-copy via policy; REVIEW + no inputs raises).

C28. NO_SILENT_PATH structural enforcement. `Tests/Contract/TestAudioPipelineNoSilentFallback.py` AST-walks `AudioFilterEmitter` + `TranscodeShape` and asserts: no `STRATEGY_REVIEW: continue` survives; `_BuildReviewFallbackBlock` + `DispositionResolver.ResolveForTrack` present; `_PickDefaultLanguage` delegates to `DispositionResolver.PickDefaultLanguage`; no literal `['-c:a', 'copy']` extend in `TranscodeShape`; `self.CodecPolicy.Decide` consumed; `EmitTracks` returns only the typed `Blocks` list or `None`.

C29. OPERATOR_VISIBLE_FAILURE. `FailedJobsRepository.GetFailedJobsPaged` surfaces `AudioPolicyResolved` + the latest verdict's `PolicyName` + `PolicyReason` for each capped row. `/Admin/Workers` snapshot already surfaces `Faulted:<PolicyName>` via the existing RuntimeState text. Verifiable: `Tests/Contract/TestAudioOperatorVisibleFailure.py` 2/2 (response shape + synthetic verdict surface).

C30. CODEC_SELECTION. `AudioComplianceRules.Track0Codec` + `AudioComplianceRules.Track1Codec` select the ffmpeg audio codec per track. Accepted values: `'aac'` (AAC-LC, universal support) and `'opus'` (libopus, ~40% smaller than AAC at same perceptual quality; universal decode in browsers, Android, iOS 11+, WebOS 5+, native Roku 4K/Xbox; Jellyfin server-transcodes to AAC for ~8% legacy clients). Emitter resolves codec via `_ResolveFfmpegCodec(name)` which maps `'opus'` -> `'libopus'`. Default: both tracks Opus. Verifiable: change `Track0Codec` in DB -> next encode emits `-c:a:0 libopus` (or `-c:a:0 aac`).

C31. OPUS_MULTICHANNEL. When Track 0 codec is Opus AND source channel count > 2, emitter prepends `aformat=channel_layouts=5.1|7.1` to the Track 0 filter chain (normalizes side-layout DTS/AC3 into Opus-compatible rear-layout 5.1) AND appends `-mapping_family:a:{OutputIndex} 1` to the codec args (Opus surround channel-family selector). Without either, libopus rejects 6+ channel input with ffmpeg exit -22. Verifiable: 6ch source + `Track0Codec='opus'` -> output stream is opus 5.1 with `channel_layout=5.1` in ffprobe; without the aformat filter the same command fails with `Invalid argument`.

C32. BITRATE_DEFAULTS_REFLECT_CODEC. When operator switches codec via GUI, the bitrate defaults follow codec efficiency: Opus needs ~half the bits of AAC-LC for equivalent perceptual quality. Current defaults calibrated for Opus: `Track0BitratePerChannelKbps=48` (Track0MinPerChannelKbps=32), `Track1StereoBitrateKbps=64`. AAC operators should manually bump to `64/48/128` for equivalent transparency. Verifiable: `SELECT Track0BitratePerChannelKbps, Track1StereoBitrateKbps FROM AudioComplianceRules WHERE Id=1;` returns Opus-tuned defaults post-migration `AddAudioCodecKnobs_2026_07_02.py`.

C33. NO_FORCED_DOWNMIX_AT_GLOBAL_SCOPE. `AudioNormalizationConfig.MaxAudioChannels` at scope='global' MUST NOT be lower than the source's channel count for any file expected to preserve surround. Historic damage: `MaxAudioChannels=2` at global scope forced every 5.1 movie to stereo downmix; combined with a prior `-b:a 96k` bitrate cap this ruined Doctor Strange in the Multiverse of Madness, both Dune films, and any other 5.1 title transcoded in that window (see BUG-0072). Verifiable: `SELECT MaxAudioChannels FROM AudioNormalizationConfig WHERE Scope='global'` returns 6 or 8; NEVER 2 unless the operator explicitly wants global stereo downmix.

C34. DEMUCS_STATUS_VISIBLE_IN_ACTIVE_JOB. While `DemucsVocalIsolationService.IsolateVocals` is running for a given TranscodeAttempt, the `/Activity` Active Jobs card MUST show a Demucs-stage indicator distinct from the ffmpeg-stage indicator. The indicator advances through: `demucs.downmix -> demucs.isolate -> demucs.premix -> ffmpeg.encode`. `Workers.RuntimeState` (or the equivalent per-job progress row) carries a `Stage` field the API surfaces to the UI. Verifiable: submit a job, poll `/api/Activity/ActiveJobs` at 2 s cadence, capture the Stage transitions; the sequence includes at least one `demucs.*` value before any `ffmpeg.*` value. Negation: a job whose Active Jobs row goes straight from "queued" to "ffmpeg encoding" fails the criterion. Motivation: today an operator sees a job "running" for 25-360 s of silent Demucs pre-pass with no signal that anything is happening or that Demucs itself is the current bottleneck.

C35. DEMUCS_USES_WORKER_VENV_PYTHON. `DemucsVocalIsolationService.IsolateVocals` MUST invoke `demucs.separate` via the same interpreter that is currently executing the WorkerService (`sys.executable`), never a hard-coded `py` / `python` / `C:\Python313\python.exe` shell resolution. `demucs` MUST be listed in `WorkerService/requirements.txt` and installed into `WorkerService/venv/` at deploy time. Verifiable: `WorkerService/venv/Scripts/python.exe -c "import demucs; print(demucs.__version__)"` succeeds on every heartbeating worker; grep `DemucsVocalIsolationService.py` for the subprocess spawn shows `sys.executable` (or an injected `PythonExecutable` seam), never a literal `"py"` / `"python"` / `"python3"` string. Negation: a worker whose venv lacks `demucs` OR whose service spawns via `py -m demucs.separate` fails the criterion (this is exactly the failure mode that hit Love Island USA S08E17: `py` resolved to `C:\Python313\python.exe`, a bare interpreter with no `demucs` module, and the Dialog Boost track was silently dropped).

C36. TRACK1_TWO_PASS_LINEAR_LOUDNORM. Track 1's loudnorm MUST be two-pass linear-mode when the premix WAV is measurable: `PreEncodeAudioPipeline.Run` runs a `loudnorm=print_format=json` analysis pass on the freshly-mixed `dialog_boost_premix.wav` and returns `(PremixMeasuredI, PremixMeasuredLra, PremixMeasuredTp, PremixMeasuredThresh)`. These flow through `TranscodeJobStrategy` -> `TranscodeShape.Build` -> `AudioFilterEmitter.EmitTracks` -> `_BuildDialogBoostBlock`, and the emitted Track 1 loudnorm carries `measured_I / measured_LRA / measured_TP / measured_thresh / linear=true`. Verifiable: SQL on `TranscodeAttempts.FfpmpegCommand` post-directive returns `-filter:a:1 "...loudnorm=...:measured_I=<x>:measured_LRA=<y>:measured_TP=<z>:measured_thresh=<t>:linear=true..."` for every Dialog-Boost-emitted attempt. Fail-safe: when measurement returns None (JSON parse failure), the emitted filter falls back to the single-pass dynamic form; the fallback is logged as a WARNING at `DemucsVocalIsolationService.MeasurePremixLoudnorm`. Motivation: today's Love Island USA S08E17 encode landed Track 1 at -19.6 LUFS (target -20, G2 violation of 0.4 LU) because single-pass dynamic loudnorm cannot correct for content-dependent premix loudness variation; linear-mode with pre-measured input targets ±0.1 LU regardless of content.

## SOLID Compliance

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

## Self-Healing

The vertical detects and heals its own DB-state discrepancies via an
in-system recurring service. Operator does not run scripts to fix
vertical state.

H1. `AudioVerticalHealthService`
(`Features/AudioNormalization/SelfHealing/AudioVerticalHealthService.py`)
is one row in the shared `Scanners` orchestrator table
(see `Features/FileScanning/scanners.feature.md`). The row carries
`ScannerName='AudioVerticalHealth'`, `Enabled BOOL`, `IntervalSec INT`,
`BatchSize INT`, `DryRun BOOL`, `LastRunAt TIMESTAMP`. The WebService
background-thread loop reads the row fresh per cycle (`db-is-authority`)
and stamps `LastRunAt` via `ScannersRepository.RecordRun` on every
successful cycle. Operator controls everything via `/Admin/Scanners`;
no SQL needed; no WebService restart needed to flip switches.

Constructor injects `List[IAudioVerticalInvariant]`, a per-invariant
`Dict[invariant_name -> IAudioVerticalRemediation]`, a
`RemediationBatch` cap (default 100), and a `DryRun BOOL` (default
False). Each cycle: for each invariant -> `Detect()` returns
offending row ids -> matched `Remediation.Apply()` runs against the
FIRST `RemediationBatch` ids (UNLESS `DryRun=True`, in which case
`Apply` is skipped and the audit row carries
`DRY_RUN: would have remediated N`) -> result + `capped X->N` note
written to `AudioVerticalHealthRuns` table. The batch cap protects
cycle time: without it, a single invariant with 18k+ detected rows
blocks every subsequent cycle for many hours. DryRun is the safety
net: when an invariant or remediation regresses (it has, twice), the
operator can re-enable H1 in DryRun first and watch the audit table
to confirm what it WOULD do before flipping DryRun off.

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

H4. `/api/Activity/LibraryCompliance` payload carries
`AudioVerticalHealth: {LastRunAt, PreVerticalPolicy, Last24h: [{Invariant,
Detected, Remediated}]}`. `Detected` is the count from the most-recent
cycle per invariant (current backlog); `Remediated` is the sum across
all cycles in the last 24h (throughput). The template's
`Self-healing (last 24h)` sub-section renders the table plus the
`PreVerticalPolicy` badge.

## Operational

O1. Stale-code Linux containers are paused at the DB level. Status
'Paused' + `PauseReason` set on every Worker row whose deployed `Version`
diverges from `HEAD` of the source tree at WebService startup. The pause
holds until a redeploy aligns the version.

O2. `AudioNormalizationConfig.PreVerticalReNormalizePolicy TEXT NOT NULL
DEFAULT 'lazy'` IN ('aggressive', 'lazy', 'none'). Default 'lazy' --
H1's `PreVerticalTranscodedFile` invariant skips them; operator manual
queue still works; aggressive flips to auto re-normalize on the next
H1 cycle.

## Live Verification

L1. Multi-language live encode -- a source MediaFile with 2 distinct
language audio streams encodes through the emitter and produces 4 output
streams (2 emit-tracks x 2 source languages). Each Original output tagged
with its source language; each Dialog Boost output tagged with its source
language. Exactly ONE output track carries `disposition.default=1`: the
Dialog Boost in the source's per-stream default-language, falling back to
library default, falling back to first present language. `EmitTracks`
calls `_PickDefaultLanguage(AudioStreams, StreamLanguageMap,
LibraryDefault)` once per emission and passes the per-track
`IsDefaultLanguage` flag into `_BuildDispositionArgs`. Verified live on
MediaFile 579 (Black Butler S01E06 Bluray-1080p.mkv, source: jpn opus
stereo + eng opus 5.1; eng marked default): output had Original (jpn,
default=0) / Original (eng, default=0) / Dialog Boost (jpn, default=0) /
Dialog Boost (eng, default=1).

Production wiring (so live transcode flow actually triggers the
multi-language path): `TranscodeShape`, `RemuxShape`, and
`SubtitleFixShape` each constructor-inject an
`AudioStreamProbe` (`Features/AudioNormalization/Services/
AudioStreamProbe.py`) and call `Probe(CommandData.InputPath)` before
`EmitTracks`. The probe returns an audio-only-indexed list (sequential
0, 1, 2 to match ffmpeg's `-map 0:a:N` convention) with per-stream
language and disposition. When the probe returns `[]` (path missing,
ffprobe unavailable) `EmitTracks` falls back to its single-stream
placeholder behavior.

L2. MP4 audio-track naming -- the MP4 muxer in ffmpeg silently drops
`-metadata:s:a:N title=X` for audio streams (confirmed empirically:
`title` does not appear in `ffprobe -show_entries stream_tags` output
on an MP4 with that flag set; only `language` and `handler_name`
survive). The MP4 spec's per-track name lives in the `hdlr` atom,
which ffmpeg writes from the `handler_name` metadata key. The emitter
emits `-metadata:s:a:N handler_name="<Label> (<lang>)"` per output
stream (resolution outcome (a) in the L2 directive). Contract test
`TestMp4TitleResolution.py` proves the round-trip: title is dropped,
handler_name persists, and ffprobe shows e.g. `handler_name=Dialog
Boost (eng)`. Operator-facing identification of the Dialog Boost
track is the per-stream `handler_name` value AND
`disposition.default=1`.

L3. Whisper backend live verified -- `ggml-tiny.bin` (multilingual
~77MB) deployed under `AIModels/` and `SystemSettings.WhisperModelPath`
points to it. `WhisperFfmpegBackend` runs ffmpeg's `whisper` filter on
the first 60 s of the audio stream, captures the JSON-line transcript,
assembles the text, and runs `langdetect` (deterministic seed) over
it; the top-ranked ISO 639-1 code lands in
`MediaFiles.AudioStreamLanguageDetectionsJson`. Verified live against
MediaFile 24139 (`Bob Hearts Abishola - S01E15`, audiolanguages=`und`)
-> `{Language: en, Confidence: 0.9999955}`. ffmpeg filter syntax
forbids drive-letter colons inside the value; the backend resolves
the model + transcript paths relative to repo root (via cwd) so the
filter argument is `whisper=model=AIModels/ggml-tiny.bin:...`. The
two-tool split (Whisper transcribes; langdetect identifies) is the
documented design; the regex-on-stderr approach the original backend
attempted does not work because ffmpeg's whisper filter does not
emit a detected-language stderr line.

## Cross-Vertical Contract

This section locks the audio vertical's public surface. Any other vertical
(Compliance, Self-Healing, Scanning, TranscodeJob, FileReplacement, etc.)
interacts with the audio vertical ONLY through what is listed below. Other
verticals MUST NOT open any audio-vertical source file or import from any
class not enumerated here. The audio vertical reserves the right to change
anything not in this contract -- without notice -- because nothing outside
should depend on it.

### Columns the audio vertical WRITES

Consumers (other verticals + downstream services) may SELECT these. They
MUST NOT write them.

| Column | Written by |
|---|---|
| `MediaFiles.SourceIntegratedLufs` | `EbuR128MeasurementService.MeasureAndPersist` |
| `MediaFiles.SourceLoudnessRangeLU` | `EbuR128MeasurementService.MeasureAndPersist` |
| `MediaFiles.SourceTruePeakDbtp` | `EbuR128MeasurementService.MeasureAndPersist` |
| `MediaFiles.SourceIntegratedThresholdLufs` | `EbuR128MeasurementService.MeasureAndPersist` |
| `MediaFiles.LoudnessMeasuredAt` | `EbuR128MeasurementService.MeasureAndPersist`, `AudioRemeasurementService.MarkForRemeasurement` (back-dates) |
| `MediaFiles.AudioComplete` | `AudioStateService.MarkAudioComplete` / `ResetAudioComplete` |
| `MediaFiles.AudioCompletedAt` | `AudioStateService.MarkAudioComplete` |
| `MediaFiles.AudioCorruptSuspect` | `AudioStateService.MarkAudioCorruptSuspect` |
| `MediaFiles.AudioCorruptReason` | `AudioStateService.MarkAudioCorruptSuspect` |
| `MediaFiles.AudioLanguages` | `ComplianceGate.Evaluate` -- written by Compliance vertical based on emitted-language seam (S13); the AUDIO vertical only EMITS the metadata tags |
| `MediaFiles.AdmissionDeferReason` | `AudioPolicyAdmissionGate.AdmitOrDefer` (set), `AudioOperatorReviewService.{AddToReviewQueue,BulkClearByReason,BulkRemeasureByReason,BulkClearSpeechEnrichmentCache,ResolveReview}` (set/clear) |
| `MediaFiles.AudioStreamLanguageDetectionsJson` | `LanguageEnrichmentService.Enrich` |
| `MediaFiles.AudioCompliant` | `AudioVertical.RecomputeFor` |
| `MediaFiles.AudioCompliantReason` | `AudioVertical.RecomputeFor` |
| `TranscodeQueue.AudioPolicyJson` | `AudioPolicyAdmissionGate.BackfillRecentInserts` / `BackfillAllPending` |
| `TranscodeAttempts.AudioTracksEmittedJson` | `PostEncodeMeasurementService.Probe` |
| `TranscodeAttempts.AudioPolicyJson` | written by TranscodeJob vertical at attempt creation, copied FROM `TranscodeQueue.AudioPolicyJson` -- consumed by audio vertical's post-encode probe |
| `AudioNormalizationConfig.*` (all columns) | `AudioNormalizationController.upsert_settings` (via the Settings UI) |

### Columns the audio vertical READS from external tables

These are config or context the audio vertical consumes. The audio vertical
NEVER writes these. Other verticals own them.

| Column | Read by | Owner |
|---|---|---|
| `AudioNormalizationConfig.*` (all columns) | `AudioPolicyResolver.GetEffectivePolicy` | Operator-edited via Settings UI; the audio vertical reads fresh per evaluation (`db-is-authority`) |
| `SystemSettings.WhisperModelPath` | `LanguageEnrichmentService._ResolveWhisperModelPath` | Operator/deploy-time setting |
| `Workers.FFmpegPath` / `FFprobePath` | `WhisperFfmpegBackend._ResolveFFmpegPath`, `PostEncodeMeasurementService._ResolveBinaries` | Workers vertical |
| `MediaFiles.StorageRootId` / `RelativePath` / `FileName` / `Resolution` / `AudioCodec` / etc. | every audio-vertical service that needs MediaFile context | FileScanning + Probe verticals |

### Stable function entry points (cross-vertical callers)

The classes + signatures below have actual callers OUTSIDE
`Features/AudioNormalization/` today. Their signatures are contract;
constructor injection is allowed (any class listed accepts collaborator
injection for tests). Adding a new keyword argument with a default is
non-breaking; removing or renaming a parameter is a contract change that
requires a directive.

| Class.method | External caller(s) |
|---|---|
| `AudioFilterEmitter.EmitTracks(MediaFile, Policy, AudioStreams=None, LibraryDefault=None) -> List[TrackBlock]` | `Features/TranscodeJob/Emit/{Transcode,Remux,SubtitleFix}Shape.py` |
| `AudioPolicyResolver.GetEffectivePolicy(MediaFile) -> dict` | same three shapes |
| `AudioStreamProbe.Probe(LocalSourcePath: str) -> list[dict]` (audio-only-indexed) | same three shapes |
| `AudioPolicyAdmissionGate.AdmitOrDefer(MediaFile, IntendedProcessingMode=None) -> AdmissionDecision` | `Features/TranscodeQueue/QueueManagementBusinessService` |
| `AudioPolicyAdmissionGate.BackfillAllPending() -> int` | same |
| `AudioStateService.MarkAudioComplete(MediaFileId) -> None` | `Features/FileReplacement/TranscodedOutputPlacement` |
| `PostEncodeMeasurementService.Probe(TranscodeAttemptId, OutputFilePath) -> bool` | `Features/AudioNormalization/Workers/PostEncodeAudioHandler` (which is itself called by TranscodeJob's worker dispatch) |

Everything else under `Features/AudioNormalization/` is INTERNAL. That
includes (non-exhaustive): `AudioStrategyClassifier`,
`LanguageDetector`, `_BuildBlockForTrack`, the `TrackBlock` dataclass
internals, every helper prefixed with `_`, every Repository, every test
fixture. Other verticals MUST NOT import these.

### HTTP API surface

The blueprint registered at `Features/AudioNormalization/
AudioNormalizationController.py` exposes the routes below. These are the
operator-facing contract; UI templates + external scripts may call them.

| Method + URL | Purpose |
|---|---|
| `GET  /AudioNormalization` | Render the Settings + Dashboard + Review tabbed page |
| `GET  /api/AudioNormalization/Settings` | List every `AudioNormalizationConfig` row |
| `POST /api/AudioNormalization/Settings` | Upsert one row at any scope |
| `GET  /api/AudioNormalization/Dashboard` | `v_audio_consistency_summary` band breakdown per library |
| `GET  /api/AudioNormalization/Review` | Grouped review queue: per-reason counts + 5-sample preview + ActionLabel/ActionVerb |
| `POST /api/AudioNormalization/Review/<int:media_file_id>/Resolve` | Single-file clear + recompute |
| `POST /api/AudioNormalization/Review/Resolve` | Bulk per-reason dispatch: clear / re-measure / re-enrich |
| `GET  /api/AudioNormalization/EnrichmentQueue/Status` | Count of MediaFiles waiting on speech enrichment |
| `POST /api/AudioNormalization/SnapshotPolicies` | Trigger `BackfillAllPending` manually |

### What is EXPLICITLY NOT a contract

Other verticals MUST NOT depend on any of the following. The audio
vertical changes these freely:

- Internal class names of helpers, dataclasses (`TrackBlock`), and the
  shape of `_BuildBlockForTrack`'s six per-concern slots
- SQL clauses inside repositories
- Regex patterns inside the language detector / Whisper parser
- Internal directory structure under `Features/AudioNormalization/`
- The `Strategy` enum strings (`'linear'` / `'adaptive'` / `'limiter'` /
  `'skip'` / `'review'`) emitted by `AudioStrategyClassifier` -- they
  are recorded inside `AudioPolicyJson` but consumers MUST NOT switch
  on these strings; treat `AudioPolicyJson` as opaque
- Anything prefixed with `_` (private by Python convention)

### Cross-vertical relationships (where audio fits in the larger system)

| Other vertical | Direction | Through |
|---|---|---|
| Compliance | Compliance READS audio-vertical columns to evaluate `IsCompliant` | Columns listed above |
| Self-Healing | Self-Healing invariants READ audio-vertical columns + call SELECT-only repository methods | Columns + future `IAudioVerticalInvariant` registry (currently lives inside audio dir; will MOVE to self-healing vertical when that vertical is properly factored) |
| Scanning | Scanning writes new `MediaFiles` rows; audio vertical's admission gate then sees them on next admit | New MediaFiles flow through normal admission |
| TranscodeJob | TranscodeJob's shape classes CALL audio vertical's three public functions to build argv | `EmitTracks` + `GetEffectivePolicy` + `Probe` |
| FileReplacement | FileReplacement CALLS `MarkAudioComplete` after a successful audio-touching transcode replaces the file | `AudioStateService.MarkAudioComplete` |
| Workers | Workers' DB row supplies the FFmpeg paths the audio vertical resolves at runtime | `WorkerContext.Current()` |

## Seams (intra-feature; producer + consumer both inside audio vertical)

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | Resolver -> Classifier | `AudioPolicyResolver.GetEffectivePolicy` | Policy dict (Scope, EmitTracks JSONB, Target* / UngainablePolicy / LoudnessTolerance) | `AudioStrategyClassifier.ClassifyTrack` reads TargetIntegratedLufs / TargetTruePeakDbtp / LoudnessTolerance / UngainablePolicy | `TestAudioPolicyResolver` 6 tests + `TestAudioStrategyClassifier` 11 tests |
| S2 | Classifier -> Emitter | `AudioStrategyClassifier.ClassifyTrack` | `TrackStrategy(Strategy, EffectiveTargetLufs, EffectiveTruePeakDbtp, EffectiveLra, Reason)` | `AudioFilterEmitter._BuildBlockForTrack` translates strategy into argv | `TestAudioFilterEmitter` 12 fixture tests |
| S3 | Emitter -> Shape | `AudioFilterEmitter.EmitTracks` | `List[TrackBlock]` each with `MapArgs / CodecArgs / FilterArgs / MetadataArgs / DispositionArgs` | `RemuxShape.Build` / `TranscodeShape.Build` / `SubtitleFixShape.Build` concatenate the slots into the ffmpeg command | `TestRemuxShape` / `TestTranscodeShape` / `TestSubtitleFixShape` |
| S4 | Admission Gate -> Queue | `AudioPolicyAdmissionGate.AdmitOrDefer` | `AdmissionDecision(Outcome, DeferReason, PolicyJson)` -- side effect: `MediaFiles.AdmissionDeferReason` set on deferred | `TranscodeQueue.AudioPolicyJson` snapshot populated via `BackfillRecentInserts` UPDATE | `TestAudioPolicyAdmissionGate` 6 tests + live SQL `SELECT COUNT(AudioPolicyJson) FROM TranscodeQueue` |
| S6 | Measurement Service -> Validator | `EbuR128MeasurementService.MeasureAndPersist` -> `MediaFiles.SourceIntegratedLufs` / LRA / TP / Threshold | `LoudnessMeasurementValidator.IsValid` reads the four columns + silence floor predicate | `TestEbuR128MeasurementService` 6 tests + `TestLoudnessMeasurementValidator` 8 tests |
| S7 | Enrichment Service -> Detector Cache | `LanguageEnrichmentService.Enrich` writes `MediaFiles.AudioStreamLanguageDetectionsJson` | `LanguageDetector.Detect` 6th layer reads cache when `EnableSpeechLayer=True` | `TestLanguageEnrichmentService` 5 tests + `TestLanguageDetector.test_layer_speech_cache_when_enabled` |
| S8 | Post-Encode Probe -> Dashboard | `PostEncodeMeasurementService.Probe` writes `TranscodeAttempts.AudioTracksEmittedJson` | `v_audio_consistency_summary` view aggregates per-StorageRootId bands; dashboard renders | `TestPostEncodeMeasurementService` 4 tests + live `SELECT * FROM v_audio_consistency_summary` |
| S9 | PostEncodeAudioHandler -> Probe | `PostEncodeAudioHandler.HandlePostEncode(AttemptId, MediaFileId)` resolves canonical path -> invokes `PostEncodeMeasurementService.Probe` | `TranscodeAttempts.AudioTracksEmittedJson` row updated | `TestPostEncodeAudioHandler` with mocked probe |

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
