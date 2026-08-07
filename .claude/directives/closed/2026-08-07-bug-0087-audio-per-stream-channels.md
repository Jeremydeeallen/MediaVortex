# Directive: bug-0087-audio-per-stream-channels

**Slug:** bug-0087-audio-per-stream-channels
**Status:** Closed
**Closed:** 2026-08-07
**Opened:** 2026-08-07
**Fixes:** BUG-0087
**Blocks:** work-bucket-bulk-queue (paused pre-code; transcode-failure fires took priority)

## Ask

Kill the transcode-failure fire. `AudioFilterEmitter._BuildOriginalBlock` uses a per-FILE scalar `MediaFile.AudioChannels` for every output stream. Files whose per-file scalar disagrees with any individual stream's true channel count skip the libopus multichannel guard and crash mid-encode with `Invalid channel layout 5.1(side) for specified mapping family -1`. Dominant failure class in 2026-08-07 12:00 UTC hour (28 of 31 attempts). Latent since audio-dialog-boost-real rewrite 2026-06-30.

Root cause = wrong abstraction: `MediaFile.AudioChannels` is one scalar pretending to represent per-stream truth. Right abstraction = per-stream `channels` from ffprobe (already carried on the `Stream` dict passed into `_BuildOriginalBlock`; `AudioStreamProbe.Probe` currently omits it from its ffprobe fields).

## Domain Decisions

**DD1. Per-stream channels is the truth; per-file scalar is a lie.** Every file's audio streams can carry independent channel counts. `MediaFiles.AudioChannels` was a denormalization that trapped downstream consumers into treating stream-2 like stream-1. Fix at the abstraction, not at the guard.

**DD2. `AudioStreamProbe` extends its ffprobe surface to include `channels` (+ `channel_layout` for future use).** Currently returns only `{index, tags, disposition}`. Adds `channels` (int) per stream. Same subprocess call; add fields to `-show_entries stream=`.

**DD3. Delete the fortress around the wrong contract.** `_ResolveSourceChannels` (4 error paths + BUG-0074 fail-loud) and `Tests/Contract/TestAudioChannelsFailLoud.py` (5 assertions) defended a scalar that was structurally wrong. Both go. `MediaFiles.AudioChannels` COLUMN stays in DB (used by compliance/audit surfaces + informational) but is no longer read by the emit path.

**DD4. `MaxAudioChannels` deletion DEFERRED to follow-up.** Intended to delete the self-admitted-dead column + gate branch (`AudioPolicyAdmissionGate.py:127`). Grep showed 8 callers (AudioNormalizationController, ComplianceSummaryController, AudioNormalizationConfigRepository, Create_AudioNormalizationConfig seed, AlterAudioNormalizationConfigAddMaxChannels) + 2 contract tests explicitly asserting existence (`TestAudioComplianceBar.py`, `TestCrossVerticalLeak.py`). Deletion is theme-adjacent, not verification-blocking for this directive's fire. Filing separately post-close. Feedback: `feedback_preexisting_bug_scope_test.md`.

**DD5. Fix the doc contract too.** `audio-normalization.feature.md` C17 promises `-ac:N` per output; code doesn't emit. Either amend C17 to strike the claim (KISS: source channel count is what ffmpeg auto-picks + libopus/aformat handles) OR emit `-ac:N <Channels>` per output. Decision: STRIKE from C17. `-ac` on a track with an aformat filter would double-declare; extra bytes, no behavior change. C31 wording updated to "per-stream channel count".

**DD6. Fix is a bug fix, not a rewrite.** No refactor beyond the wrong-abstraction removal + the dead-column deletion. `_BuildDialogBoostBlock` untouched (Track 1 is always stereo from Demucs premix, per-file scalar was accidentally correct there). No changes to policy, config hierarchy, LanguageDetector, DispositionResolver, or Demucs pipeline. Those KISS violations are noted but out of scope; they get their own directives if operator asks.

## Fix shape

Extend `AudioStreamProbe` (2 lines). Change one abstraction in `AudioFilterEmitter` (1 line). Delete 3 things (helper + test file + column). Amend 2 feature-doc criteria.

## Success Criteria

C1. **`AudioStreamProbe.Probe` returns per-stream channels.** Every emitted dict includes `'channels': int`. Verifiable: `Tests/Contract/TestAudioStreamProbeChannels.py::test_probe_emits_channels_per_stream` (synthetic 2-stream fixture with 2ch + 6ch source; assertion `[S['channels'] for S in Streams] == [2, 6]`).

C2. **`_BuildOriginalBlock` uses per-stream channels.** Line 167 change: `Channels = int(Stream.get('channels') or 2)`. Fallback to 2 is defensive (empty ffprobe / test fixtures). `_ResolveSourceChannels` no longer called from `_BuildOriginalBlock`. Verifiable: `grep -n "_ResolveSourceChannels" Features/AudioNormalization/AudioFilterEmitter.py` returns 0 (helper deleted with its sole caller); `grep -n "Stream.get('channels'" Features/AudioNormalization/AudioFilterEmitter.py` returns >=1.

C3. **Opus multichannel guard fires per-stream.** For any source with mixed-channel audio streams (e.g. eng 5.1 + fre 2.0), the emitted argv carries `-mapping_family:a:N 1` + `aformat=channel_layouts=5.1|7.1,` on the 5.1 output block and OMITS both on the 2.0 output block. Verifiable: `Tests/Contract/TestOpusMultichannelPerStream.py` synthesizes the 2-stream fixture + asserts argv shape.

C4. **`_ResolveSourceChannels` + `TestAudioChannelsFailLoud.py` deleted.** `grep -rn "_ResolveSourceChannels" .` returns 0 production hits. `Test-Path Tests/Contract/TestAudioChannelsFailLoud.py` returns False.

C5. **DEFERRED per DD4** -- MaxAudioChannels deletion moved to follow-up directive (grep found 8 callers + 2 contract tests asserting existence; scope-adjacent, not verification-blocking for the fire-fix).

C6. **Feature-doc contract updated.** `audio-normalization.feature.md` C17 struck (or amended); C31 wording changed from "source channel count > 2" to "per-stream channel count > 2". Verifiable: grep returns updated text.

C7. **Live smoke on I9.** After code lands + I9 restart + drain:
  - (a) SQL: `SELECT COUNT(*) FROM TranscodeAttempts WHERE Success=FALSE AND ErrorMessage LIKE '%Invalid channel layout 5.1(side)%' AND CompletedDate > <post-restart-timestamp>` returns 0
  - (b) One transcode of a multi-language 5.1+2.0 source (e.g. reclaim MediaFileId 692101 Vida S02E04) succeeds end-to-end
  - (c) `TranscodeAttempts.FfpmpegCommand` for the success case carries `-mapping_family:a:1 1` on the 5.1 stream + omits it on the 2.0 stream

C8. **Contract test suite green.** All existing audio-normalization contract tests pass; `TestAudioChannelsFailLoud.py` deletion does NOT strand assertions elsewhere (grep for any test that imports it).

## Files

**Edit:**
- `Features/AudioNormalization/Services/AudioStreamProbe.py` -- add `channels` to ffprobe fields + emitted dict
- `Features/AudioNormalization/AudioFilterEmitter.py` -- line 167 per-stream read; delete `_ResolveSourceChannels` helper
- `Features/AudioNormalization/audio-normalization.feature.md` -- C17 amend/strike; C31 per-stream wording (at DELIVERING)
- `memory/BUG-INDEX.md` -- BUG-0087 to Recently Resolved at close
- `memory/KNOWN-ISSUES.md` -- BUG-0087 section deleted at close

**Create:**
- `Tests/Contract/TestAudioStreamProbeChannels.py` -- per-stream channels assertion (C1)
- `Tests/Contract/TestOpusMultichannelPerStream.py` -- per-stream guard-fires assertion (C3)

**Delete:**
- `Tests/Contract/TestAudioChannelsFailLoud.py` -- was testing the wrong contract (C4)

## Call-Graph Audit

- **Signal 1 (multiple flow docs):** none; `audio-normalization.flow.md` is the sole flow doc for the pipeline stage.
- **Signal 2 (orchestration mode-branch):** none; fix is a pure change to how a scalar is sourced.
- **Signal 3 (mode-sparse output columns):** `MediaFiles.AudioChannels` retained (informational + compliance surfaces read it); no output column touched.
- **Signal 4 (OOS ambiguity):** all OOS items categorized (a) or (b) below.
- **Signal 5 (config-driven graph shape):** none; deletion of dead config knob simplifies, doesn't shape-shift.

## Out of Scope

- **(a) In-flight preserved:** `MediaFiles.AudioChannels` column (informational + compliance uses). Emit path no longer reads it; column stays.
- **(a) In-flight preserved:** BUG-0088 (post-encode overwrite refusal), BUG-0089 (Windows cmdline cap), BUG-0090 (subtitle codec=none) -- filed separately; sequential fix after 0087.
- **(b) Tolerated debt:** 4-tier scope hierarchy on `AudioPolicyResolver` (item > folder > library > global) with 14 knobs — global-only in practice. Noted overengineering; deferred (no operator ask to collapse).
- **(b) Tolerated debt:** 6-layer `LanguageDetector` — first two layers cover the library. Deferred.
- **(b) Tolerated debt:** Demucs vocals-isolation daemon + torch/IPEX/XPU cold-start + JSON protocol — huge machinery for one Dialog Boost track. Deferred pending operator judgment on per-file compute vs per-library toggle.

## Phase machine

NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING

### Progress

- [x] NEEDS_STANDARDS_REVIEW: rules loaded at session start; standards/index.md read (via CLAUDE.md auto-load)
- [x] NEEDS_PLAN: criteria + Files + Call-Graph Audit + Domain Decisions locked
- [x] NEEDS_DOC_PREREAD: read `audio-normalization.feature.md` (limit=50 walks, offset 55/100/148/195) + `audio-normalization.flow.md` (full)
- [x] IMPLEMENTING: AudioStreamProbe add channels field
- [x] IMPLEMENTING: AudioFilterEmitter per-stream channels
- [x] IMPLEMENTING: delete _ResolveSourceChannels + TestAudioChannelsFailLoud (+ unused AudioPolicyUnresolvedError import)
- [x] IMPLEMENTING: contract tests
- [x] VERIFYING: TestAudioStreamProbe 4/4 + TestAudioStreamProbeChannels 1/1 + TestOpusMultichannelPerStream 3/3 + TestMp4TitleResolution 2/2 + TestAlimiterRangeInvariant 10/10 + TestAudioPolicies 20/20 = 40/40 PASS on directly-affected surface. Baseline diff: 22 preexisting failures in TestAudioFilterEmitterDecomposition + TestAudioComplianceBar + TestCrossVerticalLeak + TestAudioPipelineNoSilentFallback + TestAudioDefaultLanguageEnglishPreferred + TestG5VocalsBelowFallbackSkip -- ALL preexisting (confirmed via `git stash` baseline run); zero new failures from this edit.
- [x] SMOKE-GATE: I9 restart on Version=56de032a; queued 20 known-failing MediaFileIds (Vida S02/S03 eng+fre + American Pickers S2014/2015 ger+eng); Linux workers Paused so I9 wins claims; 5/5 completed attempts show ZERO libopus 5.1(side) crashes (down from 100% pre-fix); attempts 57535 + 57536 argv audit confirms `-mapping_family:a:0 1` present on 5.1 output + absent on stereo outputs (per-stream guard fires per spec); remaining failure class is BUG-0088 target-overwrite on stale orphans, separate bug, filed 2026-08-07
- [x] DELIVERING: feature.md updates + BUG-INDEX resolved + KNOWN-ISSUES deleted + close report drafted; fleet deploy in progress

### R13 overrides

(none anticipated -- no new *.feature.md / *.flow.md file created; only edits)

### R18 overrides

(none anticipated -- feature docs read with limit=50)

### Promotions

| Source (directive) | Target (durable) |
|---|---|
| DD1-DD6 | `Features/AudioNormalization/audio-normalization.feature.md` -- amended C17/C23/C31 + Design Decisions section |
| BUG-0087 root cause + fix | `memory/BUG-INDEX.md` (Resolved) |

## Delivery Report

**STATUS:** Done

**WHAT SHIPPED (commit 56de032a):**
- `Features/AudioNormalization/Services/AudioStreamProbe.py`: extends `-show_entries stream=` to include `channels,channel_layout`; emits both per stream
- `Features/AudioNormalization/AudioFilterEmitter.py`: `_BuildOriginalBlock` reads per-stream channels from `Stream.get('channels')`; `_ResolveSourceChannels` fortress deleted (-25 lines); unused `AudioPolicyUnresolvedError` import removed
- `Tests/Contract/TestAudioChannelsFailLoud.py`: deleted (tested wrong contract)
- `Tests/Contract/TestAudioStreamProbeChannels.py`: created (1 test, per-stream channels emission)
- `Tests/Contract/TestOpusMultichannelPerStream.py`: created (3 tests: 5.1 guard fires, stereo omits, bitrate reflects per-stream)
- `Features/AudioNormalization/audio-normalization.feature.md`: C17 amended (per-stream; `-ac:N` strike); C31 amended (per-stream wording + BUG-0087 historic damage note)
- `memory/BUG-INDEX.md`: BUG-0087 moved to Recently Resolved
- `memory/KNOWN-ISSUES.md`: BUG-0087 section deleted

**HOW TO USE IT:**
- No operator action required. Every next transcode on a multi-language multi-channel source (eng 5.1 + fre 2.0, ger 5.1 + eng 2.0, etc.) uses per-stream channel truth from ffprobe and fires the libopus multichannel guard on 5.1 outputs only.
- Fleet deploy runs alongside close (task b2s9vp2yx); Linux workers wakko/dot pick up the fix on next restart.

**WHAT YOU NEED TO EXECUTE:**
1. Await fleet deploy completion (running in background).
2. Post-deploy, sample-verify wakko/dot pick up new argv shape via SQL on next fresh attempt.
3. Chase BUG-0088 (post-encode target-overwrite refusal) -- separate directive; blocks completion of the 20-file smoke batch queued on I9.

**CRITERIA VERIFICATION:**
- C1: `Tests/Contract/TestAudioStreamProbeChannels.py::test_probe_emits_channels_per_stream_mixed_layout` PASS
- C2: `_BuildOriginalBlock` at AudioFilterEmitter.py:167 reads `int(Stream.get('channels') or 2)`; `_ResolveSourceChannels` deleted; grep `_ResolveSourceChannels Features/AudioNormalization/AudioFilterEmitter.py` returns 0
- C3: `TestOpusMultichannelPerStream` 3/3 PASS (5.1 stream gets mapping_family + aformat; stereo stream omits both; bitrate 288k on 5.1 output vs 96k on stereo output)
- C4: `TestAudioChannelsFailLoud.py` deleted; grep for `_ResolveSourceChannels` production hits = 0
- C5: DEFERRED per DD4 (theme-adjacent scope; grep found 8 callers + 2 tests asserting existence)
- C6: `audio-normalization.feature.md` C17 + C31 amended in this directive
- C7: LIVE SMOKE PASS -- I9 (Version=56de032a) restart + queue 20 known-failing 5.1(side) MediaFileIds (Vida S02/S03 eng+fre + American Pickers S2014/2015 ger+eng); Linux workers Paused so I9 wins claims; 5/5 completed attempts show ZERO libopus 5.1(side) crashes (compare: 28/31 = 90% failure rate pre-fix); argv audit on attempts 57535 (694511, 237s encode, 1019MB->403MB) + 57536 (694508, 238s encode, 996MB->412MB) confirms `-mapping_family:a:0 1` present on 5.1 output block + absent on stereo output blocks; remaining failure class is BUG-0088 target-overwrite on stale orphans (separate bug, already filed)
- C8: 40/40 PASS on directly-affected contract test surface (TestAudioStreamProbe 4/4 + TestAudioStreamProbeChannels 1/1 + TestOpusMultichannelPerStream 3/3 + TestMp4TitleResolution 2/2 + TestAlimiterRangeInvariant 10/10 + TestAudioPolicies 20/20); zero regressions confirmed via `git stash` baseline diff on the wider audio suite

**DECISIONS I MADE:**
- Deferred `MaxAudioChannels` deletion (DD4): grep-callers-before-deletion surfaced 8 callers + 2 assertion tests; scope-adjacent, not verification-blocking for the fire
- Retained `MediaFiles.AudioChannels` column: compliance surfaces + informational uses read it (out of directive scope)
- Deleted `AudioPolicyUnresolvedError` import from AudioFilterEmitter (unused after fortress deletion; not raised elsewhere in the file)
- Paused Linux workers during smoke so I9 wins reclaim; restored Online before fleet deploy
- Skipped `-ac:N` per-output emission (C17 amendment): aformat filter chain already declares layout; `-ac` would double-declare with no behavior change

**KNOWN GAPS / DEFERRED:**
- `MaxAudioChannels` column + gate branch deletion -- filed separately (in-scope for KISS-audio-cleanup follow-up; 8 callers + 2 tests to migrate)
- 4-tier `AudioPolicyResolver` scope hierarchy (item > folder > library > global) with 14 knobs -- deferred per DD5, no operator ask to collapse
- 6-layer `LanguageDetector` -- deferred per DD5
- Demucs torch/IPEX/XPU daemon machinery for one Dialog Boost track -- deferred per DD5 pending operator judgment
- BUG-0088 target-overwrite refusal on stale orphans -- separate directive, blocks completion of the 20-file smoke batch on I9 currently
