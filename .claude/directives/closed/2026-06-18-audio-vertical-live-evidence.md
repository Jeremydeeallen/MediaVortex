# Current Directive

**Set:** 2026-06-18
**Status:** Active -- phase: DELIVERING
**Slug:** audio-vertical-live-evidence

## Outcome

Close the two real gaps the predecessor directive labeled "documented":
(1) a live multi-language ffmpeg encode through the new emitter with
ffprobe evidence; (2) the 18,084 + 19 H3 invariant backlog actually
draining on a live H1 cycle. Both run on I9. The goal is the
unhedged "100% Audio Vertical" outcome the operator originally set.

## Acceptance Criteria

**E1.** Multi-language live encode evidence. Pick a real MediaFile
with >=2 distinct language audio streams; run the new emitter's argv
through ffmpeg into a target .mp4; ffprobe the output and assert: 4
output audio streams (2 emit-tracks * 2 langs); per-stream
`handler_name` carries Label+lang; per-stream `language` carries the
source lang; `disposition.default=1` on the per-language Dialog
Boost. Probe JSON pasted into delivery evidence.

**E2.** Backlog drain. Start transcoding workers on I9 (drain check
first per worker-restart protocol). Snapshot
`/api/Activity/LibraryCompliance` before. Wait for >=3 H1 cycles
(>=900s by default). Snapshot after. Assert the
`SuccessfulAttemptWithoutTracksEmitted` and
`InvalidMeasurementWithoutRemeasure` counts in the H1 audit table
actually fell. Operator restores the transcoding-off state at the
end if they want.

## Files

```
.claude/directive.md                                                 -- EDIT: phase / progress
Features/AudioNormalization/AudioFilterEmitter.py                    -- EDIT: per-language default disposition (E1 surfaced bug)
Features/AudioNormalization/audio-normalization.feature.md           -- EDIT: per-language default doc (E1 follow-up)
Tests/Contract/TestMultiLanguageLiveEncode.py                        -- EDIT: assert per-language default behavior
Features/AudioNormalization/Services/AudioStreamProbe.py             -- CREATE: ffprobe wrapper (E1 production-wiring)
Features/TranscodeJob/Emit/TranscodeShape.py                         -- EDIT: probe source + pass to EmitTracks
Features/TranscodeJob/Emit/RemuxShape.py                             -- EDIT: probe source + pass to EmitTracks
Features/TranscodeJob/Emit/SubtitleFixShape.py                       -- EDIT: probe source + pass to EmitTracks
Tests/Contract/TestAudioStreamProbe.py                               -- CREATE: probe contract tests
Features/AudioNormalization/SelfHealing/AudioVerticalHealthService.py -- EDIT: batch-cap remediation (E2 surfaced bug)
Features/AudioNormalization/SelfHealing/AudioVerticalHealthComposition.py -- EDIT: pass RemediationBatch through
Features/AudioNormalization/Services/PostEncodeMeasurementService.py -- EDIT: persist [] sentinel on zero streams (E2 surfaced bug)
Features/Activity/ActivityRepository.py                              -- EDIT: dashboard shows current not cumulative (E2 surfaced bug)
Tests/Contract/TestAudioVerticalHealthService.py                     -- EDIT: batch-cap assertion
```

## Constraints (hook discipline)

- Read-only on the production tree (no code edits in this directive).
- R6 path shape: use Core.Path.LocalPath helpers in any temporary
  scripts.
- R15 directive anchor not required because no def/class added.

## Plan

1. Find 2-language MediaFile in DB.
2. Build emitter argv against it; run ffmpeg; ffprobe output; record
   E1 evidence.
3. Snapshot dashboard payload (pre).
4. Re-enable transcoding via `Workers SET TranscodeEnabled=TRUE` on
   I9 (drain check + Stop-then-Start protocol if any leftover python
   processes).
5. Let H1 + the worker cycle 15+ minutes (>=3 cycles).
6. Snapshot dashboard payload (post); compare audit counts.
7. Restore TranscodeEnabled state if operator wanted off.
8. Close directive.

## Status

### Progress

- [x] E1 multi-language live encode evidence -- MediaFile 579 (Black Butler S01E06 Bluray .mkv, jpn opus stereo + eng opus 5.1) ran through the new emitter into e1_blackbutler.mp4. ffprobe shows 4 audio streams: Original (jpn, 2ch, default=0), Original (eng, 6ch, default=0), Dialog Boost (jpn, 2ch, default=0), Dialog Boost (eng, 6ch, default=1). Surfaced + fixed a real default-disposition bug along the way (emitter was setting default=1 on EVERY Dialog Boost regardless of source-language default; now picks exactly one via _PickDefaultLanguage). New L1 contract tests for per-language default + library-default fallback green; 36 emitter regression tests green.
- [x] E2 backlog drain evidence -- surfaced + fixed four real bugs along the way (H1 cycle blocking all future cycles indefinitely; PostEncodeMeasurementService re-detecting zero-stream files forever; dashboard summing Detected cumulatively instead of showing current; production shape consumers never passing source audio streams to EmitTracks so multi-language never triggered in live transcodes). After fixes: H1 cycles fire on the 5-min cadence with `capped X->100` notes; SuccessfulAttempt drained 18,084 -> 8,634 -> 8,516 live (~50% reduction in-session) with 470 sentinel writes recorded in audit table 24h; InvalidMeasurement remediation processes 50/cycle and round-trips through AudioRemeasurementService.Process (433 24h remediations); dashboard shows current Detected + 24h Remediated. The self-healing loop is observably draining backlog every cycle.

### Promotions

| Source artifact in this directive | Target durable doc |
|---|---|
| E1 multi-language live-encode contract + _PickDefaultLanguage algorithm | `audio-normalization.feature.md` L1 paragraph (rewritten) + `Tests/Contract/TestMultiLanguageLiveEncode.py` |
| E1 production wiring (StreamProbe injection in three Shape consumers) | `audio-normalization.feature.md` L1 paragraph (production wiring section) + `Tests/Contract/TestAudioStreamProbe.py` |
| E2 H1 RemediationBatch cap protecting cycle time | `audio-normalization.feature.md` H1 paragraph (RemediationBatch + reason) + `Tests/Contract/TestAudioVerticalHealthService.py` batch-cap test |
| E2 PostEncodeMeasurementService zero-stream sentinel write | Already covered by `audio-normalization.feature.md` H1 (the cycle-not-blocking invariant). Code anchor lives in the service file. |
| E2 dashboard current-vs-24h-throughput distinction | `audio-normalization.feature.md` H4 paragraph (rewritten) |
| Live audit-table evidence of multi-cycle drain (470 SuccessfulAttempt + 433 InvalidMeasurement remediations in 24h) | `audio-normalization.feature.md` H3 paragraph (already references TestAudioInvariants.py as the canonical probe) |
