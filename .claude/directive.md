# Current Directive

**Set:** 2026-06-29
**Status:** Active -- phase: IMPLEMENTING
**Slug:** audio-dialog-boost-real
**Replaces:** in-flight pivot on top of `transcode-worker-unification` (at IMPLEMENTING; paused at `.claude/directives/paused/2026-06-29-transcode-worker-unification.md`)
**Interrupts:** transcode-worker-unification

## Source of Truth (operator-confirmed two-track design)

| Track | Channels | Processing | Audience |
|---|---|---|---|
| 0 Original | source passthrough (5.1 stays 5.1, stereo stays stereo) | linear loudnorm only | AVRs / Atmos receivers / surround setups (have their own dialog enhancement) |
| 1 Dialog Boost (default) | forced stereo downmix | Demucs vocal isolation -> boost vocals stem -> mix -> tight loudnorm | TV speakers / soundbars / phones / mono setups |

Track 1 carries `disposition.default=1`. Track 0 carries `disposition.default=0`. Every encoded output ships exactly these two tracks per kept language. No third track, no variant, no legacy chain.

## Outcome

Two clearly named, clearly distinct audio tracks ship on every encoded output, per the Source of Truth table above. Operator can switch between Original (full dynamics, surround preserved) and Dialog Boost (stereo, vocals lifted via Demucs, compressed for one-comfortable-volume listening) on the TV remote. Inter-program loudness is consistent across episodes. Dialog Boost actually boosts dialog (surgical vocal-stem lift, not EQ guesswork). The `/AudioNormalization` page surfaces exactly this design with the literal ffmpeg/Demucs pipeline shown per track, and no orphan knobs. Legacy filter chains, legacy dynamic-loudnorm fallbacks, and every knob that does not feed the two-track emit are deleted.

## Acceptance Criteria

G1. **Inter-program loudness consistency.** For every encoded output emitted after this directive lands, Track 0 (Original) measured integrated LUFS sits within +/-1 LU of the configured `TargetIntegratedLufs` (default -23 LUFS). Verifiable via `SELECT count(*) FROM transcodeattempts ta JOIN mediafiles mf ON mf.id = ta.mediafileid WHERE ta.attemptdate > <directive-close-date> AND abs(<achieved_track0_lufs_field> - <target_lufs_field>) > 1`. Result MUST be zero. Negation: a track landing 4 LU off target fails the criterion. Stability: references only the achieved measurement, not the filter shape.

G2. **Track 1 emit chain matches the Source of Truth.** For every encoded output, Track 1's emit pipeline is: (a) downmix source to stereo (`-ac 2` or equivalent), (b) Demucs vocal isolation on the downmixed stereo (vocals stem + instrumental stem), (c) mix with vocals boosted +3..+6 dB and instrumental attenuated -2..-4 dB, (d) loudnorm targeting `I <= -20 LUFS` and `LRA <= 5 LU`. Verifiable: SQL on `TranscodeAttempts.FfpmpegCommand` plus the Demucs invocation log row -- both must be present and reference the same pre-processed intermediate. Negation: any of the four pipeline elements missing = criterion fails. Stability: names the perceptual purpose, not specific dB/LUFS numbers.

G3. **Track 0 multichannel bitrate floor >= 48 kbps/ch.** Track 0 (Original) emits AAC-LC at the source channel count with a per-channel bitrate >= 48 kbps/ch (the AAC-LC transparency floor). Default scaling: 64 kbps/ch (mono 64k, stereo 128k, 5.1 384k, 7.1 512k). Verifiable: SQL on `TranscodeAttempts.FfpmpegCommand` extract `-b:a:0` value and divide by `MediaFilesArchive.audiochannels`. Result MUST be >= 48. Negation: any output emitting Track 0 at 21 kbps/ch (the prior starvation pattern) fails.

G4. **Track 1 is the default playback track.** `disposition.default=1` is set on Track 1, `disposition.default=0` on Track 0. Verifiable: `ffprobe -show_streams -select_streams a` on any encoded output reports `DISPOSITION:default=1` on Track 1 and `=0` on Track 0. Negation: any output where Track 0 is default fails.

G5. **Demucs vocals-stem RMS gates Track 1 boost intensity.** If the vocals stem RMS during the source duration is below -50 dBFS (no significant vocal content), Track 1 emits the Original chain unmodified (no boost, no compression) instead of the Source of Truth Track 1 pipeline. The decision + measured vocals-stem RMS is recorded in `TranscodeAttempts.AudioTracksEmittedJson`. Verifiable: SQL on `AudioTracksEmittedJson` finds the field; for files where the field shows `vocals_rms_dbfs <= -50`, the FfpmpegCommand for Track 1 matches the Track 0 chain. Negation: vocals stem RMS <= -50 dBFS but Dialog Boost pipeline emitted = fails.

G6. **GUI surfaces the two-track design literally.** `/AudioNormalization` page shows exactly two panels side-by-side: Track 0 (Original) and Track 1 (Dialog Boost - default). Each panel shows: the row from the Source of Truth table, the literal ffmpeg + Demucs pipeline that will be emitted for the current effective policy, and the goal each track serves. Knob count audit: count input/select/checkbox elements on the page; the number MUST be <= the number of distinct parameters across the two pipelines plus the `TargetIntegratedLufs` global. Existing knobs that do not feed one of the two emit pipelines are removed from the GUI AND from the underlying config tables.

## Out of Scope

- (a) Backfill of pre-directive files. Forward-looking only. Existing damaged files handled under the separate 96kbps re-request investigation (BUG-0070).
- (a) Atmos / object-based audio. Track 0 passthrough handles channel-based 5.1/7.1 only.
- (a) Per-language Dialog Boost OFF switch. If a file has multiple kept languages, each language gets the two-track design.
- (a) Demucs model selection knob. The vertical picks one default Demucs model (`htdemucs` or successor); operator does not pick per-file.
- (a) Demucs GPU vs CPU runtime knob. Implementation picks based on worker capability; no operator knob.

## Call-Graph Audit

Per `.claude/rules/call-graph-audit.md`.

1. **Multiple flow docs for one conceptual operation.** `Features/TranscodeQueue/audio-fix-priority-hints.flow.md` exists for the AudioFix WorkBucket priority pipeline (queue ordering concern). No `audio-normalization.flow.md` exists for the per-encode track-emission pipeline. Resolution: CREATE `Features/AudioNormalization/audio-normalization.flow.md` to document the per-encode pipeline (Demucs pre-pass -> Track 0 emit -> Track 1 emit -> mux). The two flow docs cover distinct pipelines and coexist.

2. **Mode-branching at orchestration level.** `AudioStrategyClassifier` classifies into five strategies (LINEAR/ADAPTIVE/LIMITER/SKIP/REVIEW); `AudioFilterEmitter` branches on the strategy enum to produce different filter chains. Under the Source of Truth, ONE orchestration always emits two tracks: Track 0 = linear loudnorm, Track 1 = Demucs+boost+tight loudnorm. Resolution: collapse `AudioStrategyClassifier` (delete the strategy enum or reduce it to a single classification); `AudioFilterEmitter` emits the two-track shape unconditionally; per-file variance lives in DATA (the measured LUFS values flowing through fixed filter slots, the vocals-stem RMS gate in G5), not orchestration branches.

3. **Shared output columns sparsely populated.** `TranscodeAttempts.AudioPolicyResolved` currently holds multiple enum values reflecting the legacy strategy variants; `TranscodeAttempts.AudioTracksEmittedJson` records per-track strategy + achieved loudness. Audit pending — to be executed at IMPLEMENTING with: `SELECT AudioPolicyResolved, count(*) FROM TranscodeAttempts WHERE AttemptDate > '2026-06-01' GROUP BY AudioPolicyResolved`. Resolution: under Source of Truth, only `two_track_original_and_boost` is valid; the deletion-in-scope section already names this. Migration script drops conflicting enum values.

4. **OOS items categorized.** All OOS items above are category (a): behavior preserved, duplication not introduced. Pre-directive damaged files (BUG-0070), Atmos object audio, per-language OFF switch, Demucs model picker, Demucs runtime picker -- none of these introduce silent debt.

5. **Config-driven call-graph shape.** `AudioComplianceRules.EnableDialogBoostTrack` is a Signal 5 violation: when FALSE the second-track emit code path is skipped = different nodes called = graph shape changes with config. Resolution: deletion-in-scope already names this column for removal. `TargetIntegratedLufs` is data-driven (flows through fixed loudnorm filter slot, no graph change) and stays. `EnableSpeechLanguageDetection` is data-driven (toggles a measurement read, not which functions are called).

## Deletions in scope

- `AudioComplianceRules.EnableDialogBoostTrack` column + every code path branching on it. Dialog Boost is always emitted. No toggle.
- `AudioFilterEmitter` legacy dynamic-loudnorm fallback paths (already deprecated per `linear-loudnorm.feature.md`).
- Every GUI knob on `/AudioNormalization` that does not directly feed a parameter in the Source of Truth table.
- Every `Profiles` column related to per-profile audio overrides that does not feed Track 0 channel count, Track 0 per-channel kbps, or Track 1 stereo kbps. Audio is no longer a per-profile concern.
- `AudioPolicyResolved` enum values that do not correspond to one of the two-track design outcomes (`two_track_original_and_boost` is the only outcome).

## Constraints

- `linear-loudnorm.feature.md` contract: Track 0 stays linear-mode loudnorm. Track 1 is the explicit place where compression is acceptable because Track 0 preserves the full-dynamics copy.
- R12 single-line comments.
- No code edits until phase advances to IMPLEMENTING.
- Demucs invocation runs in the worker before ffmpeg encode; its output WAVs are intermediate artifacts written to worker-local scratch and deleted after encode.
- Existing `audio-normalization.feature.md` C-criteria that conflict with the Source of Truth get deleted in the Promotions step at DELIVERING. C-criteria that remain consistent stay.

## Escalation Defaults

- Tradeoff between knob flexibility and GUI simplicity -> simplicity (operator: "do not overcomplicate the knobs").
- Tradeoff between preserving every legacy knob and removing unused ones -> remove unused (operator: "remove all other knobs").
- Tradeoff between Demucs CPU vs GPU -> implementation decides per worker capability.
- Risk tolerance: low (audio damage is unrecoverable).

## Engineering Calls Already Made

- Slug `audio-dialog-boost-real` (not the literal /n command-args paragraph).
- Track 1 is the default playback track (G4) per operator instruction "the only difference is the default should be dialog boost."
- Demucs picked as the Dialog Boost engine despite earlier hesitation; the design now downmixes to stereo FIRST so Demucs operates in its training domain. Stereo-only limitation no longer disqualifying.
- Track 0 multichannel bitrate floor 48 kbps/ch, default 64 kbps/ch scaling. Above AAC-LC transparency floor; below the legacy 96 kbps total starvation pattern.
- `EnableDialogBoostTrack` toggle deleted. Dialog Boost is always emitted -- it is one half of the contract, not optional.
- Per-profile audio override knobs deleted. Audio policy is global; only `TargetIntegratedLufs` survives as an operator knob.

## Status

### Files

```
CREATE:
Features/AudioNormalization/audio-normalization.flow.md             -- CREATE: new flow doc; per-encode pipeline stages incl. Demucs pre-pass
Features/AudioNormalization/Services/DemucsVocalIsolationService.py -- CREATE: wraps Demucs subprocess; returns vocals.wav + instrumental.wav paths + vocals RMS dBFS
Tests/Contract/TestTwoTrackContract.py                              -- CREATE: per-criterion G1..G6 contract test
# Scripts/SQLScripts/SimplifyAudioPolicyTables_2026_06_30.py -- DROPPED: schema migration deferred; orphan columns left dead, follow-up cleanup directive will drop them. AudioPolicyResolved already all-NULL.

EDIT:
Features/AudioNormalization/AudioFilterEmitter.py                   -- EDIT: rewrite to emit two-track Source of Truth shape unconditionally; delete legacy strategy branches
Features/AudioNormalization/AudioStrategyClassifier.py              -- EDIT or DELETE: collapse to single classification (or remove entirely; consumers updated)
Features/AudioNormalization/AudioVertical.py                        -- EDIT: remove EnableDialogBoostTrack reads; always emit two tracks
Features/AudioNormalization/AudioNormalizationController.py         -- EDIT: remove orphan knob endpoints + EnableDialogBoostTrack from PUT body; add /api/AudioNormalization/PreviewChains endpoint for G6
Features/AudioNormalization/AudioPolicyResolver.py                  -- EDIT: simplify resolver; only TargetIntegratedLufs remains as a knob
Features/AudioNormalization/AudioDispositionResolver.py             -- EDIT: Track 1 disposition.default=1, Track 0 =0 per G4
Features/AudioNormalization/AudioPipelineFailHandler.py             -- EDIT: collapse AudioPolicyResolved to single enum value
Features/AudioNormalization/TranscodeAudioPolicyVerdictRepository.py -- EDIT: same
Features/AudioNormalization/audio-normalization.feature.md          -- EDIT: replace conflicting C-criteria with G1..G6 contract; embed Source of Truth table (DELIVERING-time promotion)
Templates/AudioNormalization.html                                   -- EDIT: rewrite as two-panel side-by-side per G6; show literal pipelines; remove orphan knobs
Templates/AdminCompliance.html                                      -- EDIT: remove EnableDialogBoostTrack toggle + orphan audio knobs
Templates/Compliance.html                                           -- EDIT: same as AdminCompliance.html
Tests/Contract/TestAudioFilterEmitter.py                            -- EDIT: update for Source of Truth chain shape
Tests/Contract/TestAudioStrategyClassifier.py                       -- EDIT or DELETE: matches classifier collapse decision
Tests/Contract/TestMultiLanguageLiveEncode.py                       -- EDIT: per-language two-track still emitted
Tests/Contract/TestLinearLoudnormEnforcement.py                     -- EDIT: Track 0 keeps linear contract; Track 1 chain is post-Demucs and has its own loudnorm shape; whitelist Track 1 path
requirements.txt                                                    -- EDIT: add demucs Python dependency
WorkerService/requirements.txt                                      -- EDIT: same (worker venv runs Demucs)

DELETE (effected via SimplifyAudioPolicyTables_2026_06_30.py migration):
AudioComplianceRules.EnableDialogBoostTrack column
Any Profiles audio-override columns not feeding Track 0 ch/kbps (audit at IMPLEMENTING)
AudioPolicyResolved enum values that do not map to two_track_original_and_boost
```

### Promotions

To be populated at DELIVERING. Anticipated targets:
- `Features/AudioNormalization/audio-normalization.feature.md` -- replace conflicting C-criteria with G1..G6 contract; embed Source of Truth table.
- `Features/AudioNormalization/audio-normalization.flow.md` (create if missing) -- pipeline stages including Demucs pre-pass.

### Verification

To be populated at VERIFYING.

### Decisions Made

To be populated during IMPLEMENTING.
