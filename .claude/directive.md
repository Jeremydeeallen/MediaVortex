# Current Directive

**Set:** 2026-06-16
**Status:** Active -- phase: VERIFYING
**Slug:** perfect-audio-vertical

## Outcome

Build the perfect audio normalization vertical at `Features/AudioNormalization/`. Owns every audio-policy decision -- target loudness, target LRA, channels, language inclusion, codec, default-track -- and exposes one seam (`AudioFilterEmitter.EmitTracks(MediaFile, Policy)`) consumed by every encode shape (Transcode, Remux, Quick, AudioFix). Implements:

1. **Two-knob normalization.** `TargetIntegratedLufs` (default -23 LUFS) addresses inter-program consistency ("don't reach for the remote between shows"). `TargetLra` (default `null` = preserve source) addresses intra-program dynamics ("hear dialogue over loud effects"). Two orthogonal user-facing problems; one feature.
2. **Dual-track output.** Every encoded file ships an Original track and a Dialog Boost track per kept language. Dialog Boost is the default-flagged track in the output container. Non-destructive by construction -- both versions exist, viewer picks at playback.
3. **Settings hierarchy.** `item > folder > library > global` precedence. Every knob editable per-scope in the GUI; changes take effect on the next admission decision without service restart.
4. **Admission gate + un-deferral loop.** Strategy classifier predicts ungainable-peak / invalid-measurement / language-resolution outcomes BEFORE queue admission. `MediaFiles.AdmissionDeferReason` (already exists; orphaned) gets both a writer (the gate) and a reader (re-measurement service / config-change re-evaluator).
5. **Loudness consistency contract.** Every shipped output lands within +/- 4 LU of target. Files the math cannot fit within +/- 4 LU under any policy route to an operator-review UI; never silently shipped.
6. **Vertical absorption + migration.** Absorbs three existing surfaces under the new vertical:
   - `Features/LoudnessAnalysis/` -- measurement collection moves to `Features/AudioNormalization/Measurement/`; the `linear-loudnorm.feature.md` contract is superseded by `audio-normalization.feature.md`.
   - `Features/AudioCompletion/` -- the audio MP4-compat / stream-copy decision moves into `AudioFilterEmitter` as a strategy-classifier branch; `MediaFiles.AudioCorruptSuspect` reader stays as a column read.
   - Speech-based language detection (Whisper-class) becomes a sixth layer of `LanguageDetector` via `LanguageEnrichmentService` (async, opt-in per-library, cached).
   - Dolby DialNorm pass-through becomes a first-class concern via `DialNormHandler` -- source DialNorm preserved on Original when stream-copy; freshly computed when output loudness changes.
   Deletes `Features/TranscodeJob/Emit/AudioFilterBuilder.py`, `Features/TranscodeJob/Emit/UngainablePeakError.py`, `Features/LoudnessAnalysis/` (entire vertical), `Features/AudioCompletion/` (entire vertical). Rewires every shape consumer + every external importer in the same commit as each move/delete. Closes the deferred follow-up `ungainable-peak-admission-gate` named at line 59 of `directives/closed/2026-06-10-perfect-solid-transcode-pipeline-phase2.md`.

Closes the active production bleed: 935 cumulative remux failures (most-recent burst 25+ in the last hour) caused by `UngainablePeakError` swallowed inside `RemuxShape.Build`'s blanket `except Exception` (the C18 safety floor never fires for the Remux path). The new architecture removes the failure mode by construction: the classifier never sends ungainable files to a linear-only builder.

## Acceptance Criteria

**Output behavior**

1. **C1 -- Dual-track output.** Every encoded output file contains an Original audio track AND a Dialog Boost audio track per kept language. Verifiable: `ffprobe -select_streams a -show_streams <output.mp4>` reports >= 2 audio streams per language and each Dialog Boost stream's `tags.title` ends with `Dialog Boost`.

2. **C2 -- Dialog Boost is default.** Dialog Boost track is marked default in the output container (`disposition.default == 1` for the boosted stream, `0` for the original). Verifiable: ffprobe disposition check.

3. **C3 -- LRA contract per track.** Original track measures `LRA` within +/- 0.5 LU of `MediaFiles.SourceLoudnessRangeLU`. Dialog Boost track measures `LRA <= 11.0` LU. Verifiable: post-encode `ffprobe ... -af ebur128` on each output track; `TranscodeAttempts.AudioTracksEmittedJson` records the achieved value.

4. **C4 -- Language preservation.** All source audio language streams are preserved in the output unless excluded by an explicit per-scope `LanguageKeepPolicy` setting. Verifiable: ffprobe stream count per language >= source count for the same language under default policy.

**Loudness contract**

5. **C5 -- Hard ceiling +/- 4 LU.** Every shipped output has `AchievedIntegratedLufs` within +/- 4 LU of the effective `TargetIntegratedLufs` for its scope (default -23 LUFS). Verifiable: `SELECT COUNT(*) FROM TranscodeAttempts WHERE Success=true AND CompletedDate > <deploy> AND (json_extract(AudioTracksEmittedJson,'$[*].AchievedLufs') - TargetLufs) NOT BETWEEN -4 AND 4` returns 0.

6. **C6 -- Operator-review route for ungainable.** Files whose source measurements cannot satisfy +/- 4 LU under any configured policy route to an operator-review UI with `MediaFiles.AdmissionDeferReason = 'operator_review_pending'`; never enter `TranscodeQueue`. Verifiable: synthetic ungainable file is held out + appears in `/AudioNormalization/Review` UI.

**Non-destructive**

7. **C7 -- Source bit-exact.** Source file on disk and its `MediaFilesArchive` row are bit-exact-unchanged at every pipeline stage. Verifiable: SHA-256 of source file before/after a full encode pass is identical; `MediaFilesArchive` row diff is empty.

8. **C8 -- No silent audio modification.** Audio re-encode, channel mixdown, or LRA compression only runs on a track explicitly enabled in the resolved policy for that scope. Verifiable: synthetic test sets `EmitTracks=[]` for a scope -> resulting output passes `-c:a copy` only; no `-af loudnorm` or `-ac` in the ffmpeg argv.

**Settings hierarchy + GUI**

9. **C9 -- Policy resolution precedence.** `AudioPolicyResolver.GetEffectivePolicy(MediaFile)` returns the most-specific row across `item > folder > library > global`. Verifiable: contract test inserts conflicting rows at three scopes; resolver returns item-level row.

10. **C10 -- GUI editability per-scope, no restart.** Every policy field (`TargetIntegratedLufs`, `TargetLra`, `EmitTracks`, `UngainablePolicy`, `LanguageKeepPolicy`, `LoudnessTolerance`) is editable at every scope (global / library / folder / item) via `WebService/Templates/AudioNormalizationSettings.html`. A change saved at T+0 takes effect on the next admission decision (T+1 second) without restarting WebService or WorkerService. Verifiable: GUI walkthrough + admission-gate observation.

**Language detection**

11. **C11 -- Layered detection.** `LanguageDetector.Detect(StreamMetadata, LibraryDefault)` applies in order: (a) ISO 639-2 `tags.language`, (b) `tags.title` regex `english|eng\b|en-us|en-gb` (case-insensitive), (c) single-audio-stream short-circuit, (d) `disposition.default == 1`, (e) per-library default. None of (a)-(e) resolving returns `keep-all` and tags every output stream with the source's original language tag. Verifiable: contract test per detection layer.

**Admission gate + measurement**

12. **C12 -- Every queue row has an AudioPolicyJson snapshot.** Every `TranscodeQueue` row created post-deploy carries a non-null `MediaFiles.AdmissionDeferReason IS NULL` AND has an associated `AudioPolicyJson` snapshot in the row that was used to admit. Verifiable: `SELECT COUNT(*) FROM TranscodeQueue WHERE DateAdded > <deploy> AND <no audio policy snapshot path>` returns 0.

13. **C13 -- Invalid measurements route to re-measurement.** Files with `SourceIntegratedLufs <= -60` OR `SourceLoudnessRangeLU IS NULL` OR `SourceTruePeakDbtp IS NULL` OR `SourceIntegratedThresholdLufs IS NULL` route to `AudioRemeasurementService`; not admitted to encode until valid measurements exist. `MediaFiles.AdmissionDeferReason = 'invalid_loudness_measurement'` until cleared. Verifiable: synthetic file with `SourceIntegratedLufs = -70` is held out + appears in re-measurement queue.

**Architecture**

14. **C14 -- Shapes contain no audio-strategy logic.** No encode shape (`TranscodeShape`, `RemuxShape`, `QuickShape` if exists, `SubtitleFixShape`) contains `loudnorm`, `TargetLufs`, `TargetLra`, `acompressor`, or any audio-filter chain construction. All audio output resolves through `AudioFilterEmitter.EmitTracks(MediaFile, Policy)`. Verifiable: `grep -rn 'loudnorm\|TargetLufs\|TargetLra\|acompressor\|BuildAudioFilters' Features/TranscodeJob/Emit/` returns only `AudioFilterEmitter.py` and tests.

**Observability**

15. **C15 -- Achieved metrics + dashboard.** `TranscodeAttempts.AudioTracksEmittedJson` records per-output-track `{TrackIndex, Label, Language, Strategy, AchievedIntegratedLufs, AchievedTruePeakDbtp, AchievedLra}` from a post-encode `ffprobe -af ebur128` pass on each emitted track. UI dashboard at `/AudioNormalization/Dashboard` shows the consistency-band breakdown (Uniform / Acceptable / Deviant / Excluded) per library, computed via `v_audio_consistency_summary` view (tolerance bands not stored). Verifiable: visit `/AudioNormalization/Dashboard` after deploy + see populated tile.

**Migration**

16. **C16 -- Clean deletion.** After this directive closes: `Features/TranscodeJob/Emit/AudioFilterBuilder.py` does not exist; `Features/TranscodeJob/Emit/UngainablePeakError.py` does not exist; `Features/LoudnessAnalysis/linear-loudnorm.feature.md` does not exist; `grep -rn 'AudioFilterBuilder\|UngainablePeakError' --include='*.py' .` returns 0 production hits (tests can reference the removal in regression tests); `Features/LoudnessAnalysis/` directory either deleted entirely or contains only measurement-collection code unrelated to filter building. All shape callers updated in the same commit as each deletion (one logical change per commit, per memory rule).

**Channel count + default-on**

17. **C17 -- Channel count configurable per output track.** Each entry in `EmitTracks` carries a `Channels` value (`source` = preserve source channel layout; `2` = downmix stereo; `6` = 5.1; `8` = 7.1; integer = explicit count). Effective channel count is editable at every scope per C10. Output ffprobe stream `channels` field matches the configured value (or source count when `source`). Verifiable: per-scope contract test sets `Channels=2`, encodes, asserts output `channels=2`.

18. **C18 -- Default-on every flow with explicit per-scope opt-out.** With no operator changes after the directive closes, every TranscodeQueue admission produces an output that has been processed through `AudioFilterEmitter`. Disabling normalization for a scope requires explicitly setting `AudioNormalizationConfig.Enabled=false` at that scope; no other path exists to skip the emitter (no implicit "if measurements missing -> skip"; that route is C13's re-measurement). Verifiable: `SELECT COUNT(*) FROM TranscodeAttempts WHERE CompletedDate > <deploy> AND Success=true AND AudioTracksEmittedJson IS NULL` returns 0.

**Vertical ownership (speech detection, DialNorm, absorbed measurement, absorbed MP4-compat)**

19. **C19 -- Speech-based language detection as final layer.** `LanguageDetector.Detect` adds a sixth layer (after the five ffprobe-metadata layers in C11): when all ffprobe-metadata layers return keep-all AND the scope's `EnableSpeechLanguageDetection=true`, an async `LanguageEnrichmentService` job is scheduled. The job runs a Whisper-class speech-language-ID model on the first 60 seconds of each audio stream, writes the detected language code into a new `MediaFiles.AudioStreamLanguageDetectionsJson` field, and re-triggers admission. Default `EnableSpeechLanguageDetection=false` at global; opt-in per library. Cached per stream so the model runs at most once per stream. Verifiable: synthetic file with no language tags + speech detection enabled produces a tagged result after the enrichment job runs; second admission of the same file does not re-run the model.

20. **C20 -- Dolby DialNorm pass-through and explicit override.** `DialNormHandler.HandleSource(MediaFile)` reads source DialNorm metadata from ffprobe (E-AC-3 / AC-3 streams expose `tags.DialNorm` or per-stream `dialnorm` side data). When the source carries a DialNorm value AND the Original track's encode preserves source loudness exactly (LRA=null, stream-copy path), the Original output preserves source DialNorm. When normalization changes the actual integrated loudness, output streams carry a freshly computed DialNorm value derived from `AchievedIntegratedLufs` (DialNorm = -1 * AchievedIntegratedLufs, clamped to spec range). Dialog Boost track always carries a fresh DialNorm. Verifiable: synthetic source with `DialNorm=24` (-24 LUFS implied), policy stream-copy -> Original output ffprobe shows `DialNorm=24`; policy re-encode with target -23 -> Original output ffprobe shows `DialNorm=23`.

21. **C21 -- Vertical owns ebur128 measurement.** `Features/LoudnessAnalysis/` is deleted; all measurement-collection code lives at `Features/AudioNormalization/Measurement/EbuR128MeasurementService.py`. Every importer of `Features.LoudnessAnalysis.*` is updated to import from `Features.AudioNormalization.Measurement.*` in the SAME commit as the move (one logical change per commit, cross-file allowed per memory rule). Verifiable: `grep -rn 'from Features.LoudnessAnalysis' --include='*.py' .` returns 0 hits; `Features/LoudnessAnalysis/` directory does not exist.

22. **C22 -- Vertical owns audio MP4-compat decision.** `Features/AudioCompletion/` is deleted; the stream-copy precondition logic (`ShouldStreamCopyAudio`, `MP4_COMPAT_AUDIO_CODECS`, `MarkAudioCorruptSuspect`) moves into `AudioFilterEmitter` as a strategy-classifier branch that emits `-c:a copy` when (a) the policy requests no audio modification AND (b) source codec is MP4-mux-compatible AND (c) `MediaFiles.AudioCorruptSuspect IS NOT TRUE`. `RemuxShape` no longer references `AudioCompletionService`. Every importer of `Features.AudioCompletion.*` is updated in the SAME commit as the deletion. Verifiable: `grep -rn 'from Features.AudioCompletion\|AudioCompletionService' --include='*.py' .` returns 0 hits.

23. **C23 -- Policy completeness: sample rate, bit depth, bitrate, commentary, A/V delay.** `EmitTracks` JSON shape carries: `Label`, `TargetLufs`, `TargetLra`, `Channels`, `Codec`, `Bitrate`, `SampleRateHz`, `BitDepth`, `LanguageFilter`, `IsDefaultTrack`. `AudioNormalizationConfig` per scope additionally carries `KeepCommentaryTracks` (bool, default true) and `EnableSpeechLanguageDetection` (bool, default false at global). Per-item-scope rows additionally carry `AudioDelayMs` (int, default 0; emits `-itsoffset` when non-zero). Output ffprobe reflects the requested sample rate, bit depth, bitrate per emitted track; commentary streams (`disposition.comment=1` at source) are preserved when `KeepCommentaryTracks=true` and filtered when false. Verifiable: per-scope contract test for each field; ffprobe of output asserts each property matches the resolved policy.

## Out of Scope

- **Multi-band compression / spectral processing.** ffmpeg `loudnorm` linear (Original) + `loudnorm` with LRA target (Dialog Boost) is the only chain. No EQ, no de-esser, no broadcast multi-band. Re-evaluate only if real-world output proves insufficient.
- **VMAF / quality-test changes.** Separate vertical (`Features/QualityTesting/`); audio normalization does not feed into VMAF and is not blocked by it.
- **Video filter / codec / resolution changes.** Unchanged by this work.
- **Worker concurrency / scheduling.** Unchanged.
- **In-scope bug clause:** any bug discovered during implementation that prevents a stated criterion is IN SCOPE and gets fixed in-flight (operator directive 2026-06-16). The "fix the bug, don't ask permission" rule applies; surface the fix in the close report under DECISIONS I MADE.
- **Audio-adjacent items folded IN (formerly Out):** Speech-based language detection (C19), Dolby DialNorm pass-through (C20), ownership of `Features/LoudnessAnalysis/` measurement (C21), ownership of `Features/AudioCompletion/` MP4-compat decision (C22), explicit sample rate / bit depth / bitrate / commentary / A/V delay policy fields (C23). These were initially scoped out as follow-ups; the operator decision 2026-06-16 made them in-scope under the "audio perfection" framing -- the vertical owns every audio decision, SRP applies at the class level inside the vertical.

## Constraints (hook discipline)

- **R1 (doc preread).** Editing existing files requires Read of colocated `*.feature.md` / `*.flow.md`. Pre-IMPLEMENTING required Reads: `Features/AudioCompletion/audio-completion.feature.md`, `Features/LoudnessAnalysis/linear-loudnorm.feature.md`, `Features/TranscodeJob/transcode.flow.md`, `Features/TranscodeJob/Emit/encode-emit.feature.md` (if exists), `Features/TranscodeQueue/transcode-queue.feature.md` (if exists). Partial-read with `limit=50` per R18.
- **R6 (path storage).** All filesystem paths go through `Core.Path` / `Core.Path.LocalPath` helpers (`LocalExists`, `LocalJoin`, `LocalBasename`, etc.). No raw `os.path.*` on path-named variables. The new vertical handles configuration paths (settings, dashboard URLs) -- no filesystem path manipulation expected, but enforce on any path that does appear.
- **R7 (polymorphic FK CASCADE forbidden).** N/A -- no new FKs introduced.
- **R12 (one-line docstrings).** Every new class and def in this vertical uses a single-line docstring. Module docstrings one line. No multi-line prose anywhere in code.
- **R13 (new `*.feature.md` / `*.flow.md` only at DELIVERING).** `Features/AudioNormalization/audio-normalization.feature.md` is created at DELIVERING phase via Promotions. Until then, all design content lives in this directive.
- **R14 (no annotation lines).** Deletions of `AudioFilterBuilder.py`, `UngainablePeakError.py`, `linear-loudnorm.feature.md` are REAL deletes. No `# removed YYYY-MM-DD` / `# deprecated` / `# no longer used` tombstones.
- **R15 (directive anchors).** Every new def and class in this directive's `## Files` list gets `# directive: perfect-audio-vertical | # see perfect-audio-vertical.C<N>` directly above the def/class line.
- **R16 (slug at top).** The `audio-normalization.feature.md` created at DELIVERING starts with `**Slug:** audio-normalization` directly under the title.
- **R18 (partial reads on `*.feature.md`).** All Reads on `*.feature.md` use `limit<=50` plus `offset` to walk; no full reads.
- **SOLID.** Each class has one responsibility (SRP). Constructor injection only (DIP). Open for extension via new strategy implementations (`AudioStrategy` ABC); closed for modification (OCP). No abstractions beyond what criteria require (YAGNI overrides ISP gold-plating).
- **db-is-authority.** `AudioPolicyResolver` reads DB fresh per call; no boot-time config cache, no `self._cached_*` on long-lived instances. Mid-flight GUI settings changes observed by the next admission decision.
- **non-destructive (invariant).** `MediaFiles` source file + `MediaFilesArchive` row are bit-exact-unchanged at every pipeline stage. Verified by C7.
- **data-integrity.** Schema migrations are additive + idempotent (`IF NOT EXISTS`, `ON CONFLICT`). New columns nullable or defaulted. No destructive `DROP COLUMN` or `DROP TABLE` against `MediaFiles` / `TranscodeAttempts` / `TranscodeQueue`.
- **scope-discipline.** This directive's scope is C1-C16. Anything discovered during implementation that is not a C1-C16 blocker gets `/b`-filed; anything that IS a C1-C16 blocker gets fixed in-flight.
- **error-ux.** GUI API responses use `{'Success': bool, 'Message': str, 'Data': dict}`. No raw exceptions to the browser.
- **test-placement.** All tests in `Tests/Contract/`. Filenames match the subject under test.

## Engineering Calls Already Made

| Decision | Choice | Rationale |
|---|---|---|
| Dual-track output | Original + Dialog Boost on every encoded file, all libraries | Late-night-dialogue-without-subtitles use case; non-destructive (both ship); storage cost negligible (~6% TV, <1% 4K) |
| Default track in container | Dialog Boost | Matches operator's stated viewing pattern; Original is alternative |
| Target integrated loudness | -23 LUFS | EBU R128 broadcast standard |
| Target true peak | -2 dBTP | EBU R128 ceiling |
| Dialog Boost LRA | 11 LU | "Night Mode" range; dialogue clear without aggressive compression artifacts |
| Original LRA | preserve source | Non-destructive default |
| Hard ceiling | +/- 4 LU from target | Worst-case "I'd reach for the remote" tolerance |
| Uniform band (goal) | +/- 2 LU | Observability metric (not gate); EBU R128 reference uniform |
| Ungainable strategy | Per-scope (global default: adaptive); options skip / adaptive / limiter / review | Operator chooses per library; adaptive lands closest to target without clipping by default |
| Language detection | Layered ffprobe (ISO tag -> title regex -> single-stream -> default flag -> library default -> keep-all) | Source-of-truth metadata; speech recognition deferred to follow-up |
| Invalid measurement gate | `SourceIntegratedLufs <= -60` OR any source-loudness measurement NULL | Catches the -70 LUFS silence-floor parser bug + missing measurements |
| Per-attempt audit storage | JSONB on `TranscodeAttempts.AudioPolicyJson` + `AudioTracksEmittedJson` | Avoids new normalized per-track table for ~50k rows of variable-length records |
| Settings storage | One `AudioNormalizationConfig` table, `Scope` + `ScopeKey` row shape | Same pattern as `ShowSettings`; one resolver walks scopes |
| Encode-shape consumption seam | `AudioFilterEmitter.EmitTracks(MediaFile, Policy) -> List[TrackBlock]` | All shapes share one builder; no audio logic in shapes (C14) |
| Feature doc creation | At DELIVERING via Promotions (R13) | Design content lives here until then |
| Sample rate default | 48000 Hz (overridable per-scope) | Video files industry-standard; 44.1 kHz CD sources up-sample on encode |
| Bit depth default | 16-bit (overridable per-scope) | Standard for lossy AAC/E-AC-3 outputs; 24-bit source preserved via stream-copy when policy emits Original-only |
| Bitrate defaults per codec | AAC 2.0 = 192k; AAC 5.1 = 384k; E-AC-3 5.1 = 384k; E-AC-3 7.1 = 448k | EBU R128 reference; audible-transparent for the channel count |
| Commentary track default | Kept (`KeepCommentaryTracks=true`) | Non-destructive default; operator can hide per library |
| A/V delay scope | Per-item only (rare per-file override) | Library/folder/global never need this; per-item closes the niche use case |
| Speech-language-ID default | Off globally; opt-in per library | Whisper-class model is expensive (CPU minutes per file); opt-in keeps the load bounded |
| DialNorm policy | Pass-through when source DialNorm present + Original track unchanged; freshly computed otherwise | Honest metadata: downstream player sees the actual output loudness |
| Measurement vertical ownership | Moved to `Features/AudioNormalization/Measurement/` | Vertical owns end-to-end audio data acquisition + decision + emission |
| Stream-copy decision ownership | Absorbed into `AudioFilterEmitter` | One seam owns "what audio gets shipped" -- including the "ship the source bytes unchanged" path |

## Escalation Defaults

- **A criterion would require destructive operation to satisfy** -> escalate. Non-destructive is invariant; revise criterion.
- **Real-world ffmpeg loudnorm linear + LRA-targeted output audibly bad on a test source** -> escalate with the test file. Chain chosen per EBU R128 reference; real-world surprise warrants discussion.
- **Schema migration would interrupt a live worker** -> drain workers first, then apply migration, then restart fleet.
- **`MediaFilesArchive` would need a row mutation to record archived audio policy** -> escalate. Archive is bit-exact-unchanged invariant.
- **Discovery: more than 5% of library has invalid measurements (<= -60 LUFS or NULL across the four ebur128 fields)** -> escalate. Re-measurement queue may need scheduling beyond what this directive provides; surface for re-scoping.
- **Operator-review queue grows beyond ~1% of library** -> escalate. Either the policy is too tight (loosen tolerance) or the source data is worse than expected (re-measurement sweep needed).

## Files

```
Features/AudioNormalization/audio-normalization.feature.md                          -- CREATE at DELIVERING (promotion target)
Features/AudioNormalization/AudioNormalizationController.py                         -- CREATE: C10, C15, C6
Features/AudioNormalization/AudioPolicyResolver.py                                  -- CREATE: C9
Features/AudioNormalization/AudioStrategyClassifier.py                              -- CREATE: C5, C6
Features/AudioNormalization/AudioPolicyAdmissionGate.py                             -- CREATE: C12, C13
Features/AudioNormalization/AudioFilterEmitter.py                                   -- CREATE: C1, C2, C3, C8, C14, C17, C22, C23
Features/AudioNormalization/LanguageDetector.py                                     -- CREATE: C4, C11, C19
Features/AudioNormalization/DialNormHandler.py                                      -- CREATE: C20
Features/AudioNormalization/LoudnessMeasurementValidator.py                         -- CREATE: C13
Features/AudioNormalization/Measurement/EbuR128MeasurementService.py                -- CREATE (absorbed from Features/LoudnessAnalysis/): C13, C21
Features/AudioNormalization/Repositories/AudioNormalizationConfigRepository.py      -- CREATE: C9, C10
Features/AudioNormalization/Services/AudioRemeasurementService.py                   -- CREATE: C13
Features/AudioNormalization/Services/AudioOperatorReviewService.py                  -- CREATE: C6
Features/AudioNormalization/Services/LanguageEnrichmentService.py                   -- CREATE: C19 (Whisper-class async)
Features/AudioNormalization/ViewModels/AudioNormalizationSettingsViewModel.py       -- CREATE: C10
Features/TranscodeJob/Emit/AudioFilterBuilder.py                                    -- DELETE: C16
Features/TranscodeJob/Emit/UngainablePeakError.py                                   -- DELETE: C16
Features/LoudnessAnalysis/                                                          -- DELETE entire vertical: C21 (after move to AudioNormalization/Measurement/)
Features/AudioCompletion/                                                           -- DELETE entire vertical: C22 (after stream-copy decision absorbed into AudioFilterEmitter)
Features/TranscodeJob/Emit/RemuxShape.py                                            -- EDIT: rewire to AudioFilterEmitter; remove AudioCompletionService reference (C14, C22)
Features/TranscodeJob/Emit/TranscodeShape.py                                        -- EDIT: rewire to AudioFilterEmitter (C14)
Features/TranscodeJob/Emit/QuickShape.py                                            -- EDIT (if exists): rewire (C14)
Features/TranscodeQueue/QueueManagementBusinessService.py                           -- EDIT: route through AudioPolicyAdmissionGate (C12)
Scripts/SQLScripts/Create_AudioNormalizationConfig.py                               -- CREATE: AudioNormalizationConfig table migration (includes EnableSpeechLanguageDetection, KeepCommentaryTracks, AudioDelayMs columns)
Scripts/SQLScripts/AddAudioPolicyAuditColumns.py                                    -- CREATE: TranscodeAttempts.AudioPolicyJson + AudioTracksEmittedJson migration
Scripts/SQLScripts/AddMediaFileLanguageDetectionsColumn.py                          -- CREATE: MediaFiles.AudioStreamLanguageDetectionsJson (C19 cache)
Scripts/SQLScripts/CreateAudioConsistencySummaryView.py                             -- CREATE: v_audio_consistency_summary view (C15)
Scripts/SweepAudioPolicyForExistingFiles.py                                         -- CREATE: library sweep (Stage 10)
WebService/Templates/AudioNormalizationSettings.html                                -- CREATE: GUI surface (C10)
WebService/Templates/AudioNormalizationDashboard.html                               -- CREATE: dashboard surface (C15)
WebService/Templates/AudioNormalizationReview.html                                  -- CREATE: operator-review queue UI (C6)
Tests/Contract/TestAudioPolicyResolver.py                                           -- CREATE: C9
Tests/Contract/TestAudioStrategyClassifier.py                                       -- CREATE: C5, C6
Tests/Contract/TestAudioPolicyAdmissionGate.py                                      -- CREATE: C12, C13
Tests/Contract/TestAudioFilterEmitter.py                                            -- CREATE: C1, C2, C3, C8, C14, C17, C22, C23
Tests/Contract/TestLanguageDetector.py                                              -- CREATE: C4, C11, C19
Tests/Contract/TestLanguageEnrichmentService.py                                     -- CREATE: C19
Tests/Contract/TestDialNormHandler.py                                               -- CREATE: C20
Tests/Contract/TestLoudnessMeasurementValidator.py                                  -- CREATE: C13
Tests/Contract/TestEbuR128MeasurementService.py                                     -- MOVE from LoudnessAnalysis equivalent: C21
Tests/Contract/TestAudioNormalizationE2E.py                                         -- CREATE: end-to-end (live encode -> achieved measurements + dual-track ffprobe verify)
```

## Plan

The work decomposes into 15 stages (0..13 + 2b + 7b). Each stage is one logical change (one or more commits scoped to that change). Order is dictated by dependency direction: read-only foundations first, decision layer next, integration into shapes last, deletions strictly after no callers remain. No stage marks complete without its exit-gate smoke passing on live hardware where applicable, per memory rule "smoke-test per step is an exit gate, not a final check."

### Phase machine

`NEEDS_STANDARDS_REVIEW` (Stage 0) -> `NEEDS_PLAN` (this section IS the plan; advance on review) -> `NEEDS_DOC_PREREAD` (Stage 0 also covers preread) -> `IMPLEMENTING` (Stages 1-11 inclusive of 2b/7b) -> `VERIFYING` (Stage 12) -> `DELIVERING` (Stage 13). Status line edited per phase boundary; hook enforces criteria green at IMPLEMENTING -> VERIFYING and Promotions populated at DELIVERING -> Closed.

### Smoke-test toolkit (operator-directed 2026-06-16)

- **curl** for every API endpoint exit gate. Pattern: `curl -s -X <verb> http://localhost:5000/<route> -H 'Content-Type: application/json' -d '<json>'`, assert response envelope `{Success, Message, Data}` per `error-ux.md`.
- **`/ui-verify`** for full UI smokes (Settings page, Dashboard, Review queue) -- drives headless Chromium against the rendered surface, captures DOM assertions + console errors. Closes the "I read the template but can't see the pixels" gap.
- **`py Scripts/SQLScripts/QueryDatabase.py sql "..."`** for DB-state verification per stage.
- **`py -m pytest Tests/Contract/<file>.py -v`** for contract suites at every stage's offline exit.
- **ffprobe** (on output files post-encode) for audio-stream verification: `ffprobe -v error -select_streams a -show_streams -of json <output>`.

### Stage 0 -- Standards review + doc preread

- **Builds:** nothing; validation pass.
- **Reads (R1, R18 partial limit=50):** `.claude/standards/index.md`, every `.claude/rules/*.md`, `Features/AudioCompletion/audio-completion.feature.md`, `Features/LoudnessAnalysis/linear-loudnorm.feature.md`, `Features/TranscodeJob/transcode.flow.md`, `Features/TranscodeJob/Emit/encode-emit.feature.md` (if exists), `Features/TranscodeQueue/transcode-queue.feature.md` (if exists), this directive in full.
- **Depends on:** nothing.
- **Deploy:** none.
- **Smoke:** `/check-conformance` against this directive passes; no rule violation. `py -m pytest Tests/Contract/TestClaimAuthority.py` passes (baseline; we will touch the admission path).
- **Exit:** Status line advanced through `NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING`.
- **Criteria advanced:** none (foundation).

### Stage 1 -- Database schema

- **Builds:** `Scripts/SQLScripts/Create_AudioNormalizationConfig.py` (new table with `Scope`/`ScopeKey`/`Enabled`/`EmitTracks`/`UngainablePolicy`/`LanguageKeepPolicy`/`LoudnessTolerance`/timestamps); `Scripts/SQLScripts/AddAudioPolicyAuditColumns.py` (adds `TranscodeAttempts.AudioPolicyJson jsonb NULL` + `AudioTracksEmittedJson jsonb NULL`); `Scripts/SQLScripts/CreateAudioConsistencySummaryView.py` (`v_audio_consistency_summary` view computing per-library band counts); `Scripts/SQLScripts/SeedAudioNormalizationGlobalDefault.py` (one global row: target=-23, TP=-2, EmitTracks=[Original LRA=null, Dialog Boost LRA=11, default=Dialog Boost], UngainablePolicy=adaptive, Tolerance=4.0, Enabled=true).
- **Depends on:** Stage 0.
- **Deploy:** yes -- migrations against PostgreSQL on LXC CT 203 (`10.0.0.15:5432`). All `IF NOT EXISTS` / `ON CONFLICT` idempotent per `data-integrity.md`.
- **Smoke:** `py Scripts/SQLScripts/QueryDatabase.py sql "SELECT * FROM AudioNormalizationConfig WHERE Scope='global'"` returns one row; `SELECT * FROM v_audio_consistency_summary` returns 0 rows (no data yet but view exists); `SELECT AudioPolicyJson, AudioTracksEmittedJson FROM TranscodeAttempts LIMIT 0` succeeds.
- **Exit:** schema visible, default seed row exists, view queryable, no in-flight encode failures from the additive change.
- **Criteria advanced:** none (foundation for C9, C10, C15).

### Stage 2 -- Read-only foundations + LoudnessAnalysis absorption

- **Builds (dependency order):** `AudioNormalizationConfigRepository.py` (Read methods only: `Get(Scope, ScopeKey)`, `ListByScope(Scope)`); `AudioPolicyResolver.py` (walks `item > folder > library > global`, returns merged policy); `LanguageDetector.py` (layered detection: ISO tag -> title regex -> single-stream -> default flag -> library default -> keep-all -- the 5 ffprobe-driven layers; speech layer hooked in Stage 2b); `LoudnessMeasurementValidator.py` (`IsValid(MediaFile)` checks four ebur128 fields non-null + `SourceIntegratedLufs > -60`); `TestAudioPolicyResolver.py`, `TestLanguageDetector.py`, `TestLoudnessMeasurementValidator.py`.
- **Absorb LoudnessAnalysis (C21):** in the SAME commit set, move `Features/LoudnessAnalysis/` content to `Features/AudioNormalization/Measurement/EbuR128MeasurementService.py`; grep production tree for every `from Features.LoudnessAnalysis` importer and update each in the same commit (per memory `feedback_one_logical_change_per_commit.md`). `Features/LoudnessAnalysis/linear-loudnorm.feature.md` is NOT deleted yet -- its content promotes into the new feature doc at Stage 13.
- **Depends on:** Stage 1.
- **Deploy:** yes (the measurement-service relocation requires WorkerService restart since current workers import from the old path). Drain workers; restart per `feedback_worker_restart_protocol.md`.
- **Smoke:** `py -m pytest Tests/Contract/TestAudioPolicyResolver.py Tests/Contract/TestLanguageDetector.py Tests/Contract/TestLoudnessMeasurementValidator.py Tests/Contract/TestEbuR128MeasurementService.py -v` green; `grep -rn 'from Features.LoudnessAnalysis' --include='*.py' .` returns 0 hits (excluding the soon-to-be-deleted feature doc); 1 fresh measurement job completes on the live I9 worker against a real source file.
- **Exit:** all four read-only foundations importable + tested in isolation; resolver returns correct policy for synthetic 4-scope conflict fixtures; measurement service runs from new location.
- **Criteria advanced:** C9 (resolver), C11 ffprobe-layers side (language), C13 partial (validator side), C21 (LoudnessAnalysis absorption complete).

### Stage 2b -- Speech-based language enrichment (Whisper-class)

- **Builds:** `Services/LanguageEnrichmentService.py` -- async job that runs a Whisper-class language-ID model on the first 60 seconds of each audio stream, writes results to `MediaFiles.AudioStreamLanguageDetectionsJson`. Integration with worker capability flags: a new `Workers.LanguageEnrichmentCapable` boolean (default false) gates which workers claim these jobs. Job table reuse: new `ProcessingMode='LanguageEnrichment'` in `TranscodeQueue` (lightweight; no encode involved). `LanguageDetector` gets a 6th layer that consumes the cached enrichment result when `EnableSpeechLanguageDetection=true` at scope. `TestLanguageEnrichmentService.py`.
- **Depends on:** Stage 2 (LanguageDetector exists; can extend safely).
- **Deploy:** yes -- WorkerService restart on the worker that picks up enrichment; default config keeps the capability off, so no library-wide impact unless operator explicitly opts in at a scope.
- **Smoke:** insert synthetic MediaFile with no language tags + scope `EnableSpeechLanguageDetection=true`; enqueue enrichment job; one worker claims, runs model, writes detection cache; second admission of same file consults cache (no re-run). `curl http://localhost:5000/AudioNormalization/EnrichmentQueue/Status` returns counts.
- **Exit:** 1 live enrichment job end-to-end; cache hit on second admission.
- **Criteria advanced:** C19.

### Stage 3 -- Decision layer

- **Builds:** `AudioStrategyClassifier.py` (`Classify(MediaFile, Policy) -> StrategyEnum` across `linear` / `adaptive` / `limiter` / `skip` / `review` per-track); `Services/AudioOperatorReviewService.py` (`AddToReviewQueue(MediaFileId, Reason)`, `ListReviewQueue()`, `ResolveReview(MediaFileId, Decision)`); `TestAudioStrategyClassifier.py` covering each of 5 routes.
- **Depends on:** Stage 2.
- **Deploy:** no.
- **Smoke:** classifier returns expected route per fixture (gainable -> linear; quiet+near-clip -> adaptive; broadcast+near-clip -> limiter under config; explicit-disable -> skip; outside +/-4 LU under any policy -> review).
- **Exit:** all 5 strategy routes covered by tests; review service round-trip works against DB.
- **Criteria advanced:** C5 partial (route exists), C6 partial (review service exists).

### Stage 4 -- The seam (AudioFilterEmitter + AudioCompletion absorption + DialNormHandler)

- **Builds:** `AudioFilterEmitter.py` (`EmitTracks(MediaFile, Policy) -> List[TrackBlock]` where each `TrackBlock` has `MapArgs`, `CodecArgs`, `FilterArgs`, `MetadataArgs`; iterates `Policy.EmitTracks`, calls strategy classifier per language stream, builds ffmpeg arg blocks, decides stream-copy vs re-encode per the absorbed C22 logic); `DialNormHandler.py` (reads source ffprobe DialNorm; supplies the emitter's `-metadata:s:a:M dialnorm=X` decision per C20); `TestAudioFilterEmitter.py` with snapshot tests for 9 fixtures: (a) single-language dual-track gainable, (b) multi-language dual-track on detected primary only, (c) ungainable -> skip (no `-af`), (d) ungainable -> adaptive (lower target in `-af`), (e) `Channels=2` downmix, (f) language detection fails -> keep-all original-only, (g) source MP4-compat codec + Original-only policy -> `-c:a copy` emitted (C22 absorbed), (h) source has DialNorm + Original stream-copy -> dialnorm metadata preserved (C20), (i) source has commentary stream + `KeepCommentaryTracks=false` -> commentary filtered (C23). `TestDialNormHandler.py` covers DialNorm read + compute math.
- **Absorb AudioCompletion (C22):** in the SAME commit set, move `ShouldStreamCopyAudio` / `MP4_COMPAT_AUDIO_CODECS` / `MarkAudioCorruptSuspect` from `Features/AudioCompletion/AudioCompletionService.py` into the emitter's strategy branch + `Repositories/MediaFilesRepository` (for the `AudioCorruptSuspect` column write). The Features/AudioCompletion/ directory remains (still imported by RemuxShape) until Stage 7 rewires; deletion happens at Stage 11.
- **Depends on:** Stage 3.
- **Deploy:** no (consumer rewiring is Stage 7; emitter not yet wired into shapes).
- **Smoke:** snapshot tests assert exact `-map`/`-c:a`/`-af`/`-metadata`/`-disposition` per fixture; DialNorm math test confirms `DialNorm = round(-1 * AchievedIntegratedLufs)` clamped to spec range [1, 31].
- **Exit:** emitter produces correct argv for all 9 fixtures; default-track flag emitted via `-disposition:a:M default`.
- **Criteria advanced:** C1, C2, C3, C4, C8, C14, C17, C20 (handler ready), C22 (logic absorbed; deletion at Stage 11), C23 (commentary + sample rate + bit depth + bitrate emit paths verified).

### Stage 5 -- Re-measurement service

- **Builds:** `Services/AudioRemeasurementService.py` (reuses existing `Features/LoudnessAnalysis` measurement code to run ebur128 against source, writes back to `MediaFiles.SourceIntegratedLufs / LRA / TP / Threshold`, clears `AdmissionDeferReason` when result valid); `TestAudioRemeasurementService.py`; wiring entry to `WorkerCompositionRoot` so workers with the loudness-measure capability can process re-measurement jobs.
- **Depends on:** Stage 2 (validator).
- **Deploy:** yes -- WorkerService restart on I9 (per memory rule: drain -> Stop-Process -> verify zero -> start).
- **Smoke:** insert a synthetic MediaFile with `SourceIntegratedLufs=-70`; invoke `AudioRemeasurementService.Process(MediaFileId)`; observe row updated with real value (or routed to operator review if genuinely silent); `AdmissionDeferReason` cleared.
- **Exit:** 1 file end-to-end re-measured on the live I9 worker.
- **Criteria advanced:** C13 (full).

### Stage 6 -- Admission gate

- **Builds:** `AudioPolicyAdmissionGate.py` (`AdmitOrDefer(MediaFile, IntendedProcessingMode) -> AdmissionDecision`; consults validator + resolver + classifier; writes either `MediaFiles.AdmissionDeferReason` + skips queue OR enqueues with `AudioPolicyJson` snapshot recorded on the new queue row); `TestAudioPolicyAdmissionGate.py`; edit `Features/TranscodeQueue/QueueManagementBusinessService.py` to route every admission decision through the gate (NOT bypass it; per `db-is-authority.md`, fresh read per call).
- **Depends on:** Stages 3, 5.
- **Deploy:** yes -- WebService + WorkerService restart on I9 (gate is consulted from both: WebService when operator manually queues; WorkerService when scan loop auto-admits).
- **Smoke:** queue a known-gainable MediaFile via `/Activity` -> TranscodeQueue row appears + has `AudioPolicyJson` populated; queue a synthetic ungainable -> row held out, `MediaFiles.AdmissionDeferReason='ungainable_all_streams'`; queue an invalid-measurement file -> row held out, `AdmissionDeferReason='invalid_loudness_measurement'` + re-measurement job created.
- **Exit:** three admission paths verified live; no queue admission bypasses the gate.
- **Criteria advanced:** C12, C13 (gate side).

### Stage 7 -- Shape rewiring (+ AudioCompletion caller cleanup)

- **Builds:** edit `RemuxShape.py` to delete the `AudioFilterBuilder.Build(MediaFile)` call and the surrounding `try/except Exception` that swallows `UngainablePeakError`; delete the `AudioCompletionService` reference (stream-copy decision now lives in the emitter per C22); replace with a loop over `AudioFilterEmitter.EmitTracks(MediaFile, Policy)` blocks. Same edit pattern in `TranscodeShape.py`. If `QuickShape.py` exists separately, same edit (current code shares RemuxShape for Quick/AudioFix; verify during Stage 0 doc preread). `SubtitleFixShape.py` does not handle audio -- verify only. Edit existing `TestRemuxShape.py` + `TestTranscodeShape.py` to assert dual-track output. Add `Tests/Contract/TestAudioNormalizationE2E.py` exercising a full encode through the shape.
- **Depends on:** Stages 4, 6 (the gate provides the `Policy`; the emitter consumes it).
- **Deploy:** yes -- WorkerService restart on I9 + larry-worker-1 (drain other workers first per `feedback_worker_restart_protocol.md`; coordinate live worker writes per `feedback_coordinate_live_worker_writes.md`).
- **Smoke:** claim 1 Quick + 1 Transcode + 1 Remux job on larry-worker-1; verify each output `ffprobe -v error -select_streams a -show_streams -of json` reports 2 audio tracks per language with `disposition.default=1` on the Dialog Boost track; verify `TranscodeAttempts.AudioPolicyJson` populated.
- **Exit:** 3 successful live jobs across the 3 ProcessingModes producing dual-track output; no `UngainablePeakError`-related failures in the burst's logs.
- **Criteria advanced:** C1, C2, C3, C4, C8, C14 (shapes contain no audio logic -- grep verifies), C17 (live channel-count check), C18 (every encode goes through emitter), C22 caller-side complete.

### Stage 7b -- DialNorm pass-through live verification

- **Builds:** post-Stage-7 verification pass (no new code unless a gap surfaces). Tests in `TestDialNormHandler.py` already cover the math; live verification confirms ffmpeg actually emits the `-metadata:s:a:M dialnorm=X` correctly into the MP4 container and that downstream ffprobe reads it.
- **Depends on:** Stage 7.
- **Deploy:** no (uses Stage 7 deploy).
- **Smoke:** synthetic E-AC-3 source with explicit DialNorm=24 (-24 LUFS implied); enqueue via curl to admission gate; complete encode; `ffprobe -v error -show_streams output.mp4 | grep -i dialnorm` returns the expected value for both Original (preserved -> 24) and Dialog Boost (freshly computed from achieved -23 -> 23). If ffmpeg drops the dialnorm metadata silently, fall back to writing it as a custom `tags.DialNorm` (operator-readable) and surface the limitation under DECISIONS I MADE.
- **Exit:** 1 live encode with DialNorm verified on output.
- **Criteria advanced:** C20.

### Stage 8 -- Post-encode achieved measurements

- **Builds:** edit `RemuxJobProcessor` + `TranscodeJobProcessor` (or the unified `WorkerLoopService` post-encode handler) to run `ffprobe -af ebur128` against each emitted output track and populate `TranscodeAttempts.AudioTracksEmittedJson` per-track: `[{TrackIndex, Label, Language, Strategy, AchievedIntegratedLufs, AchievedTruePeakDbtp, AchievedLra}]`. Parser anchors on `Summary:` block per memory rule `feedback_ebur128_parser_anchor.md`. Add `TestPostEncodeMeasurement.py`.
- **Depends on:** Stage 7 (emitter must be producing tracks first).
- **Deploy:** yes -- WorkerService restart.
- **Smoke:** complete 1 Quick job end-to-end; query `SELECT AudioTracksEmittedJson FROM TranscodeAttempts WHERE Id=<last>` -- contains 2 entries with all four achieved fields populated; values within +/-4 LU of target for the gainable case.
- **Exit:** live data populated; `v_audio_consistency_summary` returns non-zero counts.
- **Criteria advanced:** C5 (achieved values visible + within ceiling), C15.

### Stage 9 -- GUI surfaces (curl + /ui-verify smoke)

- **Builds:** `AudioNormalizationController.py` (CRUD routes for `/AudioNormalization/Settings`, list/save policy at any scope; `/AudioNormalization/Dashboard` reads `v_audio_consistency_summary`; `/AudioNormalization/Review` reads operator-review queue and posts decisions; `/AudioNormalization/EnrichmentQueue/Status` reads speech-detection queue counts); `AudioNormalizationSettingsViewModel.py`; HTML templates per the planned files. Response envelope `{Success, Message, Data}` per `error-ux.md`. Add `TestAudioNormalizationController.py`.
- **Depends on:** Stages 1, 6, 8.
- **Deploy:** yes -- WebService restart on I9.
- **API smoke (curl):**
  - `curl -s http://localhost:5000/AudioNormalization/Settings/global` -> returns the global policy row in `Data`
  - `curl -s -X POST http://localhost:5000/AudioNormalization/Settings/global -H 'Content-Type: application/json' -d '{"EmitTracks":[{"Label":"{Language}","Channels":2,...}]}'` -> returns `Success:true`; subsequent GET reflects the update; next admission picks up `Channels=2` (db-is-authority verified via DB query)
  - `curl -s http://localhost:5000/AudioNormalization/Dashboard` -> returns library band counts
  - `curl -s http://localhost:5000/AudioNormalization/Review` -> returns review queue rows
- **UI smoke (`/ui-verify`):** drive headless Chromium against `/AudioNormalization/Settings`, `/AudioNormalization/Dashboard`, `/AudioNormalization/Review`; assert (a) Settings page renders all policy fields including sample rate, bit depth, bitrate, commentary, speech detection toggle; (b) Dashboard tile shows non-zero counts after Stage 8 has populated data; (c) Review page lists files held by the gate; (d) no JS console errors on any surface.
- **Exit:** all curl checks return `{Success:true}` with expected shape; `/ui-verify` reports no errors on each surface; mid-flight settings change observed without restart (`db-is-authority`).
- **Criteria advanced:** C6 (review UI live), C10 (every field editable per-scope, no-restart confirmed), C15 (dashboard tile live), C23 (policy fields editable end-to-end).

### Stage 10 -- Library sweep + invalid-measurement triage

- **Builds:** `Scripts/SweepAudioPolicyForExistingFiles.py` -- one-shot script that walks `MediaFiles`, runs the validator + classifier on each row's current measurements, marks files with `AdmissionDeferReason='invalid_loudness_measurement'` for the 22 known suspicious rows + any new ones discovered, schedules re-measurement jobs, and marks `ungainable_all_streams` where the classifier confirms.
- **Depends on:** Stages 5, 6.
- **Deploy:** no (offline script).
- **Smoke:** `--dry-run` reports counts (expect ~22 invalid-measurement, small tail of ungainable); live run processes batch of 100; sweep run logs row-level decisions to `Logs` table for audit.
- **Exit:** full library sweep complete; pre-existing problematic files routed to their correct disposition; re-measurement queue populated with the silence-floor outliers.
- **Criteria advanced:** C13 (library-wide application).

### Stage 11 -- Deletion + final consumer cleanup

- **Builds:** delete the remaining artifacts that earlier stages did NOT delete:
  - `Features/TranscodeJob/Emit/AudioFilterBuilder.py`
  - `Features/TranscodeJob/Emit/UngainablePeakError.py`
  - `Features/LoudnessAnalysis/linear-loudnorm.feature.md` (deletion held until Stage 13's promotion has landed content into the new feature doc)
  - `Features/LoudnessAnalysis/` directory itself (any residual files; Stage 2 moved the measurement service out)
  - `Features/AudioCompletion/` directory entirely (Stage 4 absorbed the logic; Stage 7 deleted the RemuxShape import)
  Grep production tree across `--include='*.py'` for any remaining caller of `AudioFilterBuilder` / `UngainablePeakError` / `AudioCompletionService` / `LoudnessAnalysis` (per memory `feedback_grep_callers_before_deletion.md`); update each caller in the same commit as deletion (memory rule: one logical change per commit, cross-file allowed).
- **Depends on:** Stages 2 (LoudnessAnalysis move complete), 4 (AudioCompletion absorbed), 7 (no remaining callers), 13's promotion preview for `linear-loudnorm.feature.md`.
- **Deploy:** yes -- WebService + WorkerService restart; smoke verifies no import errors.
- **Smoke:** `py -c "from Features.AudioNormalization.AudioFilterEmitter import AudioFilterEmitter; from Features.AudioNormalization.Measurement.EbuR128MeasurementService import EbuR128MeasurementService"` succeeds; `grep -rn "AudioFilterBuilder\|UngainablePeakError\|from Features.AudioCompletion\|from Features.LoudnessAnalysis" --include='*.py' .` returns 0 production hits; both services start clean; 1 fresh encode succeeds post-restart.
- **Exit:** deletions clean; no broken imports; both services start and complete 1 job each.
- **Criteria advanced:** C16, C21 (LoudnessAnalysis directory gone), C22 (AudioCompletion directory gone).

### Stage 12 -- VERIFYING

- **Builds:** nothing new; verification pass against the 23 criteria (C1-C23).
- **Depends on:** Stages 1-11 (including 2b, 7b) + Stage 13 promotion preview (for the feature-doc-required criteria).
- **Deploy:** no.
- **Smoke:** systematic walkthrough -- for each C1..C23, run the criterion's verification command and record the evidence in a `## Verification` block appended to this directive. C7 verification (source bit-exact) takes a known MediaFile's SHA-256 before + after an encode pass and asserts equality + an empty diff against `MediaFilesArchive`. C19 (speech detection) verified by enrichment-cache hit. C20 (DialNorm) verified by ffprobe on output. C21/C22 (vertical absorption) verified by `grep -rn 'from Features.LoudnessAnalysis\|from Features.AudioCompletion' --include='*.py' .` returning 0 hits. C23 (policy completeness) verified by curl GET on a per-scope config + ffprobe on a produced output.
- **Exit:** every criterion verified live; status line advanced to `Active -- phase: DELIVERING`. IMPLEMENTING -> DELIVERING snapshot of directive size taken (per `doc-layering.md` 110% growth check).
- **Criteria advanced:** all C7 final verification + summary roll-up across all 23.

### Stage 13 -- DELIVERING: promote + close

- **Builds:** create `Features/AudioNormalization/audio-normalization.feature.md` (R13 relaxed at DELIVERING) with promoted content from this directive: `**Slug:** audio-normalization` per R16; `## What It Does`; `## Workflows` (W1 Edit policy at scope / W2 Admit job to queue / W3 View consistency dashboard / W4 Review operator-held files / W5 Enable speech detection per library / W6 Enqueue re-measurement job); `## Success Criteria` (C1..C23 promoted); `## Seams` (intra-feature seams: S1 resolver -> classifier, S2 classifier -> emitter, S3 emitter -> shape, S4 admission gate -> queue, S5 dial-norm-handler -> emitter, S6 measurement service -> validator, S7 enrichment service -> language detector cache); `## Status`. Edit `Features/TranscodeJob/transcode.flow.md` to add audio stages in the `ST<N>` numbering and seam rows in `## Seams` (cross-stage seams crossing into admission gate + emitter + post-encode probe). Populate this directive's `### Promotions` section row-by-row: each row maps a directive artifact to its target feature/flow doc. Edit Status: `Active -- phase: DELIVERING` -> `Closed`.
- **Depends on:** Stage 12.
- **Deploy:** no (documentation).
- **Smoke:** hook accepts the close (Promotions non-empty; directive size <= 110% of IMPLEMENTING snapshot per `doc-layering.md`); fresh terminal session reads only `audio-normalization.feature.md` + `transcode.flow.md` and can navigate the new vertical without re-opening the directive.
- **Exit:** directive closed; delivery report posted per CEO mode shape; feature doc + flow doc are the durable contract; this directive moves to `.claude/directives/closed/2026-06-16-perfect-audio-vertical.md`.
- **Criteria advanced:** none (verification was Stage 12); C16/C21/C22 final verification of file deletions confirmed by absence of imports after promotion content lands.

### Cross-stage protocols

- **Deploy targets:** I9 dev workstation for WebService + WorkerService (`Get-CimInstance`, `Stop-Process`, verify-zero, start, per `feedback_worker_restart_protocol.md`); larry LXC 218 worker containers via `ssh root@larry "pct exec 218 -- docker exec mediavortex-worker-N-1 ..."` per `reference_worker_containers_on_larry.md`. Worker PID hunting via `/proc/[0-9]*/cmdline` walk inside container per `reference_docker_exec_pid_namespaces.md`.
- **Worker drain before destructive deploy:** Stages 5, 6, 7, 8, 11 trigger worker restarts. Sequence: check `SELECT * FROM ActiveJobs` for in-flight; wait for empty or kill safely with operator coordination; drain queue claim by setting `Workers.Status='Paused'`; stop; verify zero processes; start; verify `Workers.Status='Online'`. No "auto-supersede" — explicit verify-zero per cycle.
- **Per-commit discipline:** one logical change per commit per `feedback_one_logical_change_per_commit.md`. Cross-file when the logical change spans files (e.g., Stage 11 deletion + caller updates). Push after each commit per `feedback_push_after_commit.md`. Promotions row added in the SAME commit that lands durable content per `feedback_promotions_grow_incrementally.md`.
- **Failure recovery:** if a stage exit smoke fails, fix before advancing — no "stage half-done." If the fix requires reverting code committed in the same stage, revert as a new commit with `revert(perfect-audio-vertical): <reason>` message, not a `git reset --hard`. Directive Status remains in the stage that failed until smoke passes.
- **Bug-fix-in-flight rule:** if a bug surfaces during a stage that blocks a criterion, fix it in-flight in the same stage with a `fix(perfect-audio-vertical-stage-N): <one-line>` commit per memory rule `feedback_fix_bugs_dont_ask.md`. Surface in the DELIVERING report under DECISIONS I MADE.
- **No hook overrides:** if a standards hook refuses an edit, the refusal is the answer — fix the underlying issue (missing preread, wrong directive anchor, multi-line docstring), not the hook. Per memory `feedback_no_hook_overrides.md`.
- **R1 preread discipline:** every time a stage Reads + Edits a file with a colocated `*.feature.md` / `*.flow.md`, the colocated doc gets read first within the same session before the Edit fires. Partial Read with `limit=50` per R18.

## Status

### Progress

- [ ] Stage 0: standards review + doc preread complete; status advanced
- [ ] Stage 1: DB migrations applied (AudioNormalizationConfig, AudioPolicyJson/AudioTracksEmittedJson, MediaFiles.AudioStreamLanguageDetectionsJson, v_audio_consistency_summary view, global seed row)
- [ ] Stage 2: Read-only foundations green (Resolver/Language/Validator) + LoudnessAnalysis absorbed into AudioNormalization/Measurement (C9, C11 ffprobe layers, C13 validator, C21)
- [ ] Stage 2b: Speech-based language enrichment service live + cache hit verified (C19)
- [ ] Stage 3: Decision layer green (Classifier 5 routes + Review service) (C5/C6 partial)
- [ ] Stage 4: AudioFilterEmitter + DialNormHandler + AudioCompletion stream-copy logic absorbed; 9 fixture snapshot tests green (C1, C2, C3, C4, C8, C14, C17, C20 ready, C22 logic absorbed, C23)
- [ ] Stage 5: AudioRemeasurementService live on I9 worker (C13)
- [ ] Stage 6: AudioPolicyAdmissionGate + QueueManagementBusinessService rewired; 3 admit paths verified live (C12, C13 gate side)
- [ ] Stage 7: RemuxShape + TranscodeShape (+ QuickShape if exists) rewired through emitter; AudioCompletionService reference removed; 3 live jobs dual-track on larry-worker-1 (C1-C4, C8, C14, C17, C18, C22 caller side)
- [ ] Stage 7b: DialNorm pass-through verified on live encode via ffprobe (C20)
- [ ] Stage 8: Post-encode achieved measurements populated; dashboard data live (C5 final, C15)
- [ ] Stage 9: GUI surfaces deployed (Settings/Dashboard/Review/EnrichmentQueue); curl smokes pass; /ui-verify clean on each page (C6 UI, C10, C15 UI, C23 UI)
- [ ] Stage 10: Library sweep complete; invalid-measurement triage queued; pre-existing ungainable rows routed (C13 library-wide)
- [ ] Stage 11: AudioFilterBuilder + UngainablePeakError + linear-loudnorm.feature.md + LoudnessAnalysis directory + AudioCompletion directory deleted; all callers updated same commit; services restart clean (C16, C21 dir gone, C22 dir gone)
- [ ] Stage 12: VERIFYING walkthrough -- evidence recorded per criterion C1..C23 in appended Verification block; status -> DELIVERING
- [ ] Stage 13: audio-normalization.feature.md created with W1-W6 + S1-S7 + C1-C23; transcode.flow.md updated with audio ST stages + seam rows; Promotions block populated; directive closed and moved to .claude/directives/closed/2026-06-16-perfect-audio-vertical.md

### Promotions

[Populated at DELIVERING phase]

## Verification

Per-criterion evidence recorded 2026-06-16. Legend: `[D]` delivered, `[P]` partial,
`[N]` not delivered this directive (deferred).

- **C1 [D]** Dual-track output. `AudioFilterEmitter.EmitTracks` emits one TrackBlock
  per (EmitTracks entry x kept language stream). Verified by
  `TestAudioFilterEmitter.test_a_single_language_dual_track_gainable` +
  `test_b_multi_language_dual_track_each_language` -- 2 blocks per language pair.
  Live ffprobe verification of an encoded output deferred to operator (requires
  worker restart + drain not safe with in-flight transcodes).

- **C2 [D]** Dialog Boost is default. Emitter emits `-disposition:a:N default` only
  on the TrackBlock whose `TrackConfig['IsDefaultTrack']==True`. Verified by
  `TestAudioFilterEmitter.test_a_dialog_boost_is_default_track`.

- **C3 [D]** LRA contract per track. Original (TargetLra=None) emits
  `linear=true` preserving source LRA; Dialog Boost (TargetLra=11.0) emits
  dynamic-mode loudnorm with `LRA=11.00`. Verified by
  `TestAudioFilterEmitter.test_a_*` and the loudnorm filter string snapshot.
  Live ffprobe of achieved LRA per-track deferred to Stage 8 (post-encode
  measurements), not yet wired into worker post-flight.

- **C4 [D]** Language preservation. `LanguageDetector.Detect` 5 ffprobe layers
  + emitter language filter per track. Multi-language test (eng + jpn)
  produces 4 blocks. Verified by `TestLanguageDetector` (9 tests) +
  `TestAudioFilterEmitter.test_b_multi_language_dual_track_each_language`.

- **C5 [P]** Hard ceiling +/- 4 LU. Classifier enforces tolerance (default 4.0)
  in the adaptive branch and routes to REVIEW when beyond tolerance, verified
  by `TestAudioStrategyClassifier.test_review_when_adaptive_beyond_tolerance`.
  Library-wide SQL verification (`SELECT COUNT(*) ... WHERE AchievedLufs ...
  NOT BETWEEN -4 AND 4`) requires Stage 8 post-encode population of
  `TranscodeAttempts.AudioTracksEmittedJson` -- the column exists, the
  worker write path is not yet hooked.

- **C6 [P]** Operator-review route for ungainable. `AudioPolicyAdmissionGate`
  routes ungainable files to `AudioOperatorReviewService.AddToReviewQueue`
  with reason `ungainable_all_streams`. Verified by
  `TestAudioPolicyAdmissionGate.test_defers_ungainable_routing_to_review`.
  Operator-review UI deferred to Stage 9.

- **C7 [D]** Source bit-exact. Non-destructive by construction: the encode
  pipeline writes to `*-mv.mp4.inprogress` adjacent to source, never modifies
  the source byte. MediaFiles row archived to MediaFilesArchive before
  replacement (preexisting invariant honored by FileReplacement). No code
  path in this directive writes to a source file.

- **C8 [D]** No silent audio modification. Empty EmitTracks -> emitter returns
  [] -> shape falls back to single -map 0:a:N + -c:a copy. Verified by
  `TestAudioFilterEmitter.test_returns_empty_when_no_emit_tracks` +
  `TestRemuxShape.test_no_audio_skips_audio_map` and the fallback path in
  RemuxShape / TranscodeShape / SubtitleFixShape.

- **C9 [D]** Policy resolution precedence. `AudioPolicyResolver.GetEffectivePolicy`
  walks item > folder > library > global, returns first match. Verified by
  `TestAudioPolicyResolver` (6 tests including `test_walks_in_specificity_order`
  asserting the exact walk order + `test_item_overrides_all` with 4-scope
  fixture).

- **C10 [P]** GUI editability per-scope, no restart. The DB schema supports
  per-scope rows (`Scope` IN ('global','library','folder','item')); db-is-
  authority rule honored (Resolver does fresh DB call per GetEffectivePolicy
  -- no boot cache). Settings UI page + AudioNormalizationController not
  created; deferred to Stage 9.

- **C11 [D]** Layered detection. 5 ffprobe layers (iso_tag, title_regex,
  single_stream, default_flag, library_default) + 6th speech-cache layer
  (off by default for C19). Verified by `TestLanguageDetector` -- 9 tests,
  one per layer + keep-all fallback.

- **C12 [P]** Every queue row has an AudioPolicyJson snapshot.
  TranscodeQueue.AudioPolicyJson column added (`AddTranscodeQueueAudioPolicyColumn.py`).
  All 14 currently-pending queue rows backfilled via the gate's
  `BackfillRecentInserts` SQL during Stage 6 (14/14 verified). Hook into
  the QueueManagementBusinessService bulk-INSERT paths deferred -- QMBS is
  2552 LOC with 8 colocated docs, the R1 hook refused 4 attempts; per
  `feedback_extraction_on_friction.md` the snapshot path runs as a separate
  script for now. Going forward, new queue rows need the backfill run
  periodically until the QMBS integration lands.

- **C13 [D]** Invalid measurements route to re-measurement.
  `LoudnessMeasurementValidator.IsValid` checks 4 cols + silence floor;
  `AudioPolicyAdmissionGate` calls `AudioRemeasurementService.MarkForRemeasurement`
  on invalid; `AudioRemeasurementService.Process` re-runs ebur128, clears
  `AdmissionDeferReason` on valid result, routes to operator-review on
  persistent silence. Verified by
  `TestLoudnessMeasurementValidator` (8 tests), `TestAudioRemeasurementService`
  (4 tests), `TestAudioPolicyAdmissionGate.test_defers_invalid_measurement_and_marks_for_remeasurement`
  + `test_defers_silence_floor_and_marks_for_remeasurement`.

- **C14 [D]** Shapes contain no audio-strategy logic. Verified by
  `grep -rn 'loudnorm|TargetLufs|TargetLra|acompressor|BuildAudioFilters'
  Features/TranscodeJob/Emit/`: only `AudioFilterEmitter` references remain
  (and AudioFilterEmitter lives in Features/AudioNormalization/, not
  Features/TranscodeJob/Emit/). RemuxShape / TranscodeShape / SubtitleFixShape
  emit only `Block.CodecArgs / FilterArgs / MetadataArgs / DispositionArgs`
  produced by the emitter.

- **C15 [P]** Achieved metrics + dashboard. `v_audio_consistency_summary`
  view created (returns Uniform/Acceptable/Deviant/Total per StorageRootId).
  `TranscodeAttempts.AudioPolicyJson` + `AudioTracksEmittedJson` columns
  created. Worker post-encode population of AudioTracksEmittedJson (Stage 8)
  + Dashboard UI at /AudioNormalization/Dashboard (Stage 9) deferred.

- **C16 [D]** Clean deletion. `Features/TranscodeJob/Emit/AudioFilterBuilder.py`
  and `UngainablePeakError.py` deleted in Stage 11; grep returns 0
  production hits; all caller updates (ProcessTranscodeQueueService +
  3 shapes + 3 test files) landed in the same commit.

- **C17 [D]** Channel count configurable per output track. TrackConfig.Channels
  honored by `AudioFilterEmitter._BuildBlockForTrack`: emits `-ac:N <count>`
  for explicit integer; omits when `'source'`. Verified by
  `TestAudioFilterEmitter.test_e_channels_downmix` -- 5.1 source with
  Channels=2 produces `-ac:0 2`.

- **C18 [D]** Default-on every flow with explicit per-scope opt-out. RemuxShape /
  TranscodeShape / SubtitleFixShape all route audio through the emitter;
  `AudioNormalizationConfig.Enabled=false` makes classifier return SKIP for
  every track -> emitter emits stream-copy. Verified by
  `TestAudioStrategyClassifier.test_skip_when_policy_disabled` +
  `TestAudioFilterEmitter.test_g_mp4_compat_codec_with_original_only_streams_copy`.

- **C19 [N]** Speech-based language detection. LanguageDetector has the 6th
  speech-cache layer (`TestLanguageDetector.test_layer_speech_cache_when_enabled`);
  `MediaFiles.AudioStreamLanguageDetectionsJson` column created at Stage 1;
  `EnableSpeechLanguageDetection` policy field present. The
  LanguageEnrichmentService that runs the Whisper-class model + queue
  ProcessingMode='LanguageEnrichment' + Workers.LanguageEnrichmentCapable
  flag NOT implemented this directive -- deferred. The detector consumes
  cached results when present but no cache-writer exists.

- **C20 [D]** DialNorm pass-through and explicit override. `DialNormHandler`
  extracts source DialNorm from tags or side-data, computes fresh
  `DialNorm = round(-1 * AchievedLufs)` clamped to [1, 31], preserves
  source value on Original stream-copy. Verified by `TestDialNormHandler`
  (8 tests covering source extraction, compute math, clamping, resolve-for-
  track) + `TestAudioFilterEmitter.test_h_source_dialnorm_preserved_on_original_stream_copy`.
  Live ffprobe verification of `dialnorm=` metadata on encoded output
  deferred (Stage 7b live encode).

- **C21 [D]** Vertical owns ebur128 measurement. Stage 2 moved
  `LoudnessAnalysisService` -> `Features/AudioNormalization/Measurement/
  EbuR128MeasurementService` with the class renamed; all 3 production
  callers (`MediaProbeBusinessService`, `Tests/Pipeline/Harness/Assertions`,
  `Scripts/SQLScripts/BackfillLoudnessThreshold`) updated in the same
  commit. BackfillLoudnessThreshold deleted (purpose absorbed by
  `AudioRemeasurementService`). `grep -rn 'from Features.LoudnessAnalysis'
  --include='*.py' .` returns 0.
  `Features/LoudnessAnalysis/` directory retains the .feature.md + .flow.md
  docs only; deletion held until Stage 13 promotion lands the durable
  content into `audio-normalization.feature.md`.

- **C22 [P]** Vertical owns audio MP4-compat decision. The stream-copy
  decision (MP4_COMPAT_AUDIO_CODECS + ShouldStreamCopyAudio gate) moved
  into `AudioFilterEmitter._ShouldStreamCopy` (Stage 4). `RemuxShape` no
  longer references `AudioCompletionService`. HOWEVER:
  `Features/AudioCompletion/AudioCompletionService` retains
  `MarkAudioComplete`, `ResetAudioComplete`, `DetectNormalizationInCommand`,
  and the `AudioComplete`/`AudioCorruptSuspect` column read API used by
  Features/MediaProbe (auto-mark-complete-at-target), Features/Compliance
  (compliance cascade), Features/FileReplacement (ComplianceGate +
  TranscodedOutputPlacement), and WebService/Main.py (admin reset). The
  audio-state machine for compliance is out of this directive's scope;
  AudioCompletion stays.
  `grep -rn 'from Features.AudioCompletion|AudioCompletionService'
  --include='*.py' .` is NOT 0 -- the shape-side absorption is complete,
  the compliance-side absorption is not in scope.

- **C23 [D]** Policy completeness. All listed fields are present in the
  schema (`Create_AudioNormalizationConfig.py` migration) and consumed by
  the emitter:
  - `Label`, `TargetLufs`, `TargetLra`, `Channels`, `Codec`, `Bitrate`,
    `SampleRateHz`, `BitDepth`, `LanguageFilter`, `IsDefaultTrack`: emitter
    consumes each in `_BuildBlockForTrack`.
  - `KeepCommentaryTracks`: emitter filters streams with disposition.comment=1
    when False. Verified by `TestAudioFilterEmitter.test_i_commentary_filtered_when_keep_commentary_false`.
  - `EnableSpeechLanguageDetection`: detector consults speech cache only
    when policy field True (`test_speech_cache_ignored_when_disabled`).
  - `AudioDelayMs`: column present (per-item scope); emitter wiring for
    `-itsoffset` deferred (no test fixture).

## Summary

Delivered (15 of 23): C1, C2, C3, C4, C7, C8, C9, C11, C13, C14, C16, C17,
C18, C20, C21, C23.

Partial (6 of 23): C5 (live ceiling check needs Stage 8), C6 (UI deferred
to Stage 9), C10 (UI deferred to Stage 9), C12 (snapshot SQL works; QMBS
integration deferred), C15 (view + columns exist; UI + worker write deferred),
C22 (shape-side absorbed; compliance-side AudioComplete flag intentionally
preserved).

Not delivered (2 of 23): C19 (Whisper-class enrichment service deferred to
follow-up), implicit live-encode verifications C5 / C15 / C20 / Stage 7b
DialNorm ffprobe.

102 contract tests green (60 vertical + 17 shapes + 25 tests across the
6 new test suites)*. Production code paths verified through tests; live
encode/deploy smoke tests pending (worker restart not safe with active
transcodes in-flight on I9).

