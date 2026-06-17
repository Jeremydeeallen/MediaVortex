# Current Directive

**Set:** 2026-06-17
**Status:** Active -- phase: IMPLEMENTING

## Verification

Offline verification recorded 2026-06-17. Live encode evidence pending the
next emitter-driven Transcode through the I9 / larry / dot fleet on 8add6a6.

- **L1 [D]** `AudioPolicyAdmissionGate.BackfillAllPending` exists; replaces
  `BackfillRecentInserts` in `QueueManagementBusinessService._SnapshotAudioPolicies
  OnRecentInserts`. Smoke against live DB: `BackfillAllPending` ran without
  exception (queue was 0 Pending at smoke time, so no rows updated). The
  next Pending row inserted post-deploy will have its `AudioPolicyJson`
  snapshotted by the same admission cycle.
- **L2 [D]** `ProcessTranscodeQueueService.HandleTranscodingResult` (the
  Transcode-result success branch around line 1085) now invokes the same
  `_RunPostEncodeAudioProbe(TranscodeAttemptId, OutputFilePath)` that
  `HandleRemuxResult` uses. Both success paths populate
  `TranscodeAttempts.AudioTracksEmittedJson`.
- **L3 [D]** `AudioFilterEmitter._BuildBlockForTrack`: when codec is ac3
  or eac3 and the strategy is not stream-copy, `Block.CodecArgs` now
  appends `-dialnorm:N <int>`. The dropped `-metadata:s:a:N dialnorm=X`
  emission is removed. `TestAudioFilterEmitter.test_h2_dialnorm_emitted_
  as_codec_option_on_reencode` asserts the codec-option path; `test_h_
  source_dialnorm_preserved_on_original_stream_copy` updated to assert
  the stream-copy path emits `-c:a copy` with no explicit `-dialnorm`
  (bitstream preserves it).
- **L4 [D]** `AudioNormalizationConfig.LanguageDefault TEXT NOT NULL
  DEFAULT 'eng'` column added via
  `Scripts/SQLScripts/AddAudioNormalizationLanguageDefault.py`; global
  row has `LanguageDefault='eng'`. Repository SELECT extended.
  `AudioFilterEmitter` falls back to `Policy.LanguageDefault` when caller
  doesn't pass `LibraryDefault`. `LanguageDetector._GetTagsLanguage`
  treats `'und'` / `'undef'` / `'undetermined'` as not-detected so layers
  (b)-(e) fire. New `test_und_falls_through_to_policy_language_default`
  + parent `test_layer_iso_tag` updates verify both paths.

43 contract tests green across the changed suites (TestAudioFilterEmitter,
TestDialNormHandler, TestLanguageDetector, TestAudioPolicyResolver,
TestAudioPolicyAdmissionGate).

Live smoke pending: queue any future episode of 'Love Island USA - S08E*'
(or any 1080p WEBDL h264 source whose audio is `und`-tagged) through the
TranscodeQueue. Expected outcome on completion:
- ffprobe of the output shows `tags.language=eng` on both audio streams
  (the `und` fallback fired and used the global `LanguageDefault`)
- ffprobe shows the dialnorm value embedded in the eac3 bitstream
  (via `-dialnorm:N` codec option)
- `SELECT AudioTracksEmittedJson FROM TranscodeAttempts WHERE Id=<latest>`
  returns a non-NULL JSON array with per-track achieved measurements
- `SELECT AudioPolicyJson FROM TranscodeQueue WHERE Status='Pending'` is
  non-NULL on every row
- `POST /api/Compliance/Recompute` for the file returns no `EnglishAudio`
  gate block (post-replacement re-probe sees `language=eng` on both
  streams -> `HasExplicitEnglishAudio=True`)

## Status (updated)

### Progress

- [x] L1: BackfillAllPending replaces BackfillRecentInserts in QMBS
- [x] L2: post-encode probe hook on Transcode success
- [x] L3: -dialnorm:N codec option (not metadata)
- [x] L4: LanguageDefault column + fallback when source `und`
- [ ] Live smoke (next queued encode through I9 / larry / dot fleet
      on 8add6a6 -- operator queue action required)
**Slug:** audio-vertical-live-encode-gaps

## Outcome

Close the four gaps the first live emitter encode (MediaFile 690794, attempt 38642)
revealed. The vertical's offline tests are green; the live encode produced a
playable dual-track output; but downstream consumers (compliance, audit JSONs,
DialNorm correctness) are not satisfied. These four are part of "perfect audio
vertical" -- they do NOT move to a sibling directive.

Live evidence informing this directive:
- attempt 38642 finished 2026-06-17 15:00:49 UTC, FileReplaced=True
- Source: 'Love Island USA - S08E13 - Episode 13 WEBDL-1080p.mkv' (h264 / 1080p / 3449 MB)
- Output: -mv.mp4 (av1 / 720p / 768 MB, dual eac3 audio streams)
- ffprobe confirms: 2 audio streams, stream #2 has disposition.default=1
- BUT: tags.title and dialnorm metadata dropped by MP4 muxer; both streams
  tagged language=und; TranscodeAttempts.AudioPolicyJson + AudioTracksEmittedJson
  are NULL; compliance recompute returns GateBlocked='EnglishAudio'.

## Acceptance Criteria

L1. **C12 backfill catches old NULL rows.** `AudioPolicyAdmissionGate.BackfillRecentInserts`
no longer time-windows -- it scoops every TranscodeQueue row with NULL
AudioPolicyJson regardless of DateAdded. New helper
`AudioPolicyAdmissionGate.BackfillAllPending` is the one QMBS calls. Verifiable:
SELECT COUNT(*) FROM TranscodeQueue WHERE Status='Pending' AND AudioPolicyJson IS NULL
returns 0 after the next admission cycle.

L2. **C15 transcode-path hook.** `ProcessTranscodeQueueService` calls
`_RunPostEncodeAudioProbe(TranscodeAttemptId, OutputFilePath)` after every
successful TranscodeAttempt UPDATE -- including the Transcode-result path
that today only fires post-remux. Verifiable: after a successful Transcode
job, `SELECT AudioTracksEmittedJson FROM TranscodeAttempts WHERE Id=<latest>`
is non-NULL and contains achieved measurements per output stream.

L3. **C20 DialNorm via codec option.** AudioFilterEmitter emits
`-dialnorm:N <value>` as a codec option on e-ac-3 / ac-3 outputs (not as
`-metadata`). Source dialnorm survives stream-copy; recomputed dialnorm
survives re-encode. Verifiable: ffprobe of a re-encoded eac3 output shows
the dialnorm value (via `-show_streams -show_data` or the bitstream-level
dialnorm field, depending on ffprobe version), not just missing.

L4. **Language fallback when source is `und`.**
`AudioNormalizationConfig.LanguageDefault` (new TEXT column, default 'eng')
fills in `language=` metadata when source tags.language is empty or 'und'.
`AudioFilterEmitter` reads it via `AudioPolicyResolver`. Compliance
recompute on a previously `und,und`-tagged file now sees the language
default applied AND HasExplicitEnglishAudio resolves correctly via the
existing probe path that consumes the language tag. Verifiable: re-run
attempt 38642's source pattern on a fresh queue row; output ffprobe shows
`language=eng` on both audio streams; compliance recompute returns
GateBlocked!=EnglishAudio.

## Files

```
Features/AudioNormalization/AudioPolicyAdmissionGate.py          -- EDIT: BackfillAllPending (L1)
Features/AudioNormalization/AudioFilterEmitter.py                -- EDIT: -dialnorm codec opt + LanguageDefault use (L3, L4)
Features/AudioNormalization/AudioPolicyResolver.py               -- EDIT: surface LanguageDefault (L4)
Features/AudioNormalization/Repositories/AudioNormalizationConfigRepository.py -- EDIT: SELECT LanguageDefault (L4)
Features/TranscodeJob/ProcessTranscodeQueueService.py            -- EDIT: hook post-encode probe on Transcode success path (L2)
Features/TranscodeQueue/QueueManagementBusinessService.py        -- EDIT: call BackfillAllPending instead of BackfillRecentInserts (L1)
Scripts/SQLScripts/AddAudioNormalizationLanguageDefault.py       -- CREATE: AudioNormalizationConfig.LanguageDefault column (L4)
Tests/Contract/TestAudioPolicyAdmissionGate.py                   -- EDIT: add BackfillAllPending test (L1)
Tests/Contract/TestAudioFilterEmitter.py                         -- EDIT: dialnorm-as-codec-opt + LanguageDefault tests (L3, L4)
```

## Out of Scope

- Real Whisper model deployment (item 6 from the prior close; the seam is
  wired, deployment is operator-config).
- MP4 muxer's title-tag dropping behavior for audio streams. The
  workaround is operator-known: identify Original vs Dialog Boost via
  disposition + stream index. We can revisit if the operator needs in-
  player labels.
- Renaming the existing 22 invalid_loudness_measurement + 1918
  ungainable rows (already applied via Stage 10 sweep).

## Constraints (hook discipline)

Same as the parent audio directive. R1 colocated doc prereads, R6 path
storage, R12 one-line docstrings, R13 no new feature.md outside DELIVERING,
R14 no annotation lines, R15 directive anchors on every def/class in
## Files. db-is-authority: every Get reads fresh.

## Plan

Four serial substages, each commits + smokes before the next:

L1: change Backfill SQL to drop time-window; add new method
BackfillAllPending; replace one call site in QMBS.
L2: locate the Transcode-job success path in ProcessTranscodeQueueService
and add the same `_RunPostEncodeAudioProbe` call.
L3: AudioFilterEmitter: emit `-dialnorm:N` as a codec option for eac3/ac3
codecs; remove the dropped `-metadata "dialnorm=X"` path.
L4: schema migration + repository SELECT + resolver pass-through + emitter
consumes LanguageDefault when source language is `und` / empty.

Live smoke after L1-L4 land: queue 'Love Island USA - S08E13' (same
season-mate file as 690794) through the pipeline; assert ffprobe shows
`language=eng`, AudioTracksEmittedJson is populated, compliance recompute
clears the EnglishAudio gate.

## Status

### Progress

- [ ] L1: BackfillAllPending replaces BackfillRecentInserts in QMBS
- [ ] L2: post-encode probe hook on Transcode success
- [ ] L3: -dialnorm:N codec option (not metadata)
- [ ] L4: LanguageDefault column + fallback when source `und`
- [ ] Live smoke (attempt against a fresh source matching 690794's shape)

### Promotions

[Populated at DELIVERING phase]
