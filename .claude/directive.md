# Directive: bug-0087-audio-per-stream-channels

**Slug:** bug-0087-audio-per-stream-channels
**Status:** Active -- phase: NEEDS_STANDARDS_REVIEW
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

**DD4. Delete self-admitted dead code in the same beat.** `AudioPolicyAdmissionGate.py:127` comment: `MaxAudioChannels cap dead under 2-track contract; kept as column for future per-track use.` Speculative persistence violates KISS. Column + gate branch removed. If per-track cap is needed later, add then.

**DD5. Fix the doc contract too.** `audio-normalization.feature.md` C17 promises `-ac:N` per output; code doesn't emit. Either amend C17 to strike the claim (KISS: source channel count is what ffmpeg auto-picks + libopus/aformat handles) OR emit `-ac:N <Channels>` per output. Decision: STRIKE from C17. `-ac` on a track with an aformat filter would double-declare; extra bytes, no behavior change. C31 wording updated to "per-stream channel count".

**DD6. Fix is a bug fix, not a rewrite.** No refactor beyond the wrong-abstraction removal + the dead-column deletion. `_BuildDialogBoostBlock` untouched (Track 1 is always stereo from Demucs premix, per-file scalar was accidentally correct there). No changes to policy, config hierarchy, LanguageDetector, DispositionResolver, or Demucs pipeline. Those KISS violations are noted but out of scope; they get their own directives if operator asks.

## Fix shape

Extend `AudioStreamProbe` (2 lines). Change one abstraction in `AudioFilterEmitter` (1 line). Delete 3 things (helper + test file + column). Amend 2 feature-doc criteria.

## Success Criteria

C1. **`AudioStreamProbe.Probe` returns per-stream channels.** Every emitted dict includes `'channels': int`. Verifiable: `Tests/Contract/TestAudioStreamProbeChannels.py::test_probe_emits_channels_per_stream` (synthetic 2-stream fixture with 2ch + 6ch source; assertion `[S['channels'] for S in Streams] == [2, 6]`).

C2. **`_BuildOriginalBlock` uses per-stream channels.** Line 167 change: `Channels = int(Stream.get('channels') or 2)`. Fallback to 2 is defensive (empty ffprobe / test fixtures). `_ResolveSourceChannels` no longer called from `_BuildOriginalBlock`. Verifiable: `grep -n "_ResolveSourceChannels" Features/AudioNormalization/AudioFilterEmitter.py` returns 0 (helper deleted with its sole caller); `grep -n "Stream.get('channels'" Features/AudioNormalization/AudioFilterEmitter.py` returns >=1.

C3. **Opus multichannel guard fires per-stream.** For any source with mixed-channel audio streams (e.g. eng 5.1 + fre 2.0), the emitted argv carries `-mapping_family:a:N 1` + `aformat=channel_layouts=5.1|7.1,` on the 5.1 output block and OMITS both on the 2.0 output block. Verifiable: `Tests/Contract/TestOpusMultichannelPerStream.py` synthesizes the 2-stream fixture + asserts argv shape.

C4. **`_ResolveSourceChannels` + `TestAudioChannelsFailLoud.py` deleted.** `grep -rn "_ResolveSourceChannels" .` returns 0 production hits. `Test-Path Tests/Contract/TestAudioChannelsFailLoud.py` returns False.

C5. **`MaxAudioChannels` column + gate branch deleted.**
  - `Scripts/SQLScripts/DropMaxAudioChannels_2026_08_07.py` idempotent DDL: `ALTER TABLE AudioNormalizationConfig DROP COLUMN IF EXISTS MaxAudioChannels`
  - `AudioPolicyAdmissionGate.py:127` block + `MaxAudioChannels` field on the policy DTO removed
  - `AudioNormalizationController.py:66, 77, 157` MaxAudioChannels references removed (or table stays; controller stops writing it)
  - `audio-normalization.feature.md` C23 mention of `MaxAudioChannels` removed
  - Migration applied on homelab-postgres.

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
- `Features/AudioNormalization/AudioPolicyAdmissionGate.py` -- remove MaxAudioChannels branch + field (self-admitted dead line 127)
- `Features/AudioNormalization/AudioNormalizationController.py` -- remove MaxAudioChannels write path (lines 66, 77, 157 area)
- `Features/AudioNormalization/audio-normalization.feature.md` -- C17 amend/strike; C31 per-stream wording; C23 MaxAudioChannels reference removed (at DELIVERING)
- `memory/BUG-INDEX.md` -- BUG-0087 to Recently Resolved at close
- `memory/KNOWN-ISSUES.md` -- BUG-0087 section deleted at close

**Create:**
- `Scripts/SQLScripts/DropMaxAudioChannels_2026_08_07.py` -- idempotent column drop
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
- [ ] NEEDS_PLAN: criteria + Files + Call-Graph Audit + Domain Decisions locked (this doc)
- [ ] NEEDS_DOC_PREREAD: read `audio-normalization.feature.md` + `audio-normalization.flow.md`
- [ ] IMPLEMENTING: AudioStreamProbe add channels field
- [ ] IMPLEMENTING: AudioFilterEmitter per-stream channels
- [ ] IMPLEMENTING: delete _ResolveSourceChannels + TestAudioChannelsFailLoud
- [ ] IMPLEMENTING: DropMaxAudioChannels migration + code paths
- [ ] IMPLEMENTING: contract tests
- [ ] VERIFYING: contract test PASS; apply migration; existing audio tests green
- [ ] SMOKE-GATE: I9 drain + restart; reclaim MediaFileId 692101; verify argv shape + no 5.1(side) failures
- [ ] DELIVERING: feature.md updates (C17/C23/C31); BUG-INDEX + KNOWN-ISSUES; close report

### R13 overrides

(none anticipated -- no new *.feature.md / *.flow.md file created; only edits)

### R18 overrides

(none anticipated -- feature docs read with limit=50)

### Promotions

| Source (directive) | Target (durable) |
|---|---|
| DD1-DD6 | `Features/AudioNormalization/audio-normalization.feature.md` -- amended C17/C23/C31 + Design Decisions section |
| BUG-0087 root cause + fix | `memory/BUG-INDEX.md` (Resolved) |
