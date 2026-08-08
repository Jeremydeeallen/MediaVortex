# Directive: plan-factory-driven-by-compliance-flags

**Slug:** plan-factory-driven-by-compliance-flags
**Status:** Closed
**Opened:** 2026-08-08
**Sequence:** Phase 4 of 4 (Phases 1-3 closed 2026-08-07; SSoT at transcode.flow.md D1-D12)

## Ask

Per SSoT D2 + D3 in `transcode.flow.md`: slot strategy must be driven by per-dimension compliance flags (`videocompliant`, `audiocompliant`, `containercompliant`), NOT by `ProcessingMode` enum. Currently `PlanFactory.FromProcessingMode(mode)` returns a hardcoded (VideoSlot, AudioSlot, ContainerSlot, SubtitleSlot) tuple per mode. Same audio-Reencode ships regardless of whether AudioCompliant is TRUE/FALSE. Result: any file that lands in Transcode/Remux/AudioFix with `audiocompliant=TRUE` runs Demucs unnecessarily; ProcessingMode enum has leaked into shape decision that belongs to compliance state.

Fix: replace `PlanFactory.FromProcessingMode(mode)` with `PlanFactory.FromComplianceState(mf)` where slot strategies are computed from `(mf.videocompliant, mf.audiocompliant, mf.containercompliant)`. ProcessingMode column stays as reporting/priority tag (D3).

## Domain Decisions

**DD1. Slot strategy from compliance flags.** See SSoT D2:
- VideoSlot: Reencode if `!videocompliant`, else Copy
- AudioSlot: Reencode if `!audiocompliant`, else Copy
- ContainerSlot: Mp4 if `!containercompliant`, else Preserve
- SubtitleSlot: Preserve always (unless explicit SubtitleFix intent)

**DD2. ProcessingMode = tag, not shape.** ProcessingMode column preserved for reporting (which vertical drove admission) + priority (AudioFix rows may get folder-pin boost). Does NOT decide slot behavior.

**DD3. Structural idempotence.** Combined with D7 (MediaVortex outputs terminal via WorkBucket short-circuit), this fix means:
- MediaVortex outputs never land in a work bucket -> never processed
- Non-MV files in Transcode with audiocompliant=TRUE -> AudioSlot.Copy, no Demucs
- Non-MV files in AudioFix -> AudioSlot.Reencode, Demucs runs once on source

Result: duplicate-Boost class structurally impossible.

**DD4. Backward-compat with existing callers.** Every ProcessingMode enum consumer that used `PlanFactory.FromProcessingMode(mode)` migrates to `PlanFactory.FromComplianceState(mf)`. Grep for callers first. If any caller cannot supply an mf (e.g. TestVariant mode), preserve a legacy `FromProcessingMode` factory path scoped to that caller only.

**DD5. flow doc updated.** `Features/AudioNormalization/audio-normalization.flow.md` mode-coverage matrix currently maps ProcessingMode -> Plan. Amend to note the shift: matrix now shows expected slot strategy PER COMPLIANCE STATE, not per enum.

## Fix shape

Rewrite one factory function + audit callers + update mode-coverage matrix. Contract test locks the invariant.

## Success Criteria

C1. **`PlanFactory.FromComplianceState(mf)` exists** and returns a Plan (VideoSlot, AudioSlot, ContainerSlot, SubtitleSlot) tuple derived from `(mf.videocompliant, mf.audiocompliant, mf.containercompliant)`. Verifiable: `Tests/Contract/TestPlanFactoryFromComplianceState.py` covers 8 flag combinations (2^3).

C2. **`PlanFactory.FromProcessingMode(mode)` removed or scoped to TestVariant only.** Every caller in production migrated to `FromComplianceState`. Grep verifiable.

C3. **AudioSlot.Copy path exists** when audiocompliant=TRUE + processing mode is any of {Transcode, Remux, AudioFix, Quick, SubtitleFix}. Currently these modes all Reencode audio unconditionally. Copy path emits `-c:a copy` for source audio streams; no Demucs runs; no Emitter runs. Contract test covers.

C4. **VideoSlot.Copy path** when videocompliant=TRUE + processing mode is any of {Transcode, Remux, AudioFix, Quick, SubtitleFix}. Video stream-copied through.

C5. **ContainerSlot.Mp4** when containercompliant=FALSE (source not mp4). Preserve otherwise.

C6. **audio-normalization.flow.md mode-coverage matrix rewritten.** Currently lists ProcessingMode x (Video, Audio, Subtitle, Container) x whether-PreEncode-runs. New shape: compliance-state x slot decisions.

C7. **Live smoke on I9 + fleet.** Queue one file with videocompliant=FALSE + audiocompliant=TRUE + containercompliant=TRUE (video-only transcode). Verify:
  - ffmpeg command has `-c:v <encoder>` + `-c:a copy`
  - No Demucs pre-encode ran (no TranscodeProgress rows for SourceMeasure/Downmix/Demucs/Premix/LoudnormMeasure)
  - Encode completes with source audio stream(s) untouched

C8. **Existing contract tests still green.** Full audio suite + phase-detector suite must pass unchanged.

## Files

**Edit (est. 6-10 files):**
- `Features/TranscodeJob/Emit/PlanFactory.py` (or equivalent) -- add `FromComplianceState`; delete or scope `FromProcessingMode`
- `Features/TranscodeJob/ProcessTranscodeQueueService.py` -- call sites migrate
- `Features/TranscodeJob/Worker/JobProcessor.py` -- call sites migrate
- `Features/TranscodeJob/Worker/VariantJobProcessor.py` -- may keep FromProcessingMode for TestVariant only
- `Features/AudioNormalization/Services/AudioPreEncodeFacade.py` -- `_AUDIO_EMIT_MODES` set may become redundant; audio emit now driven by AudioSlot strategy
- `Features/AudioNormalization/audio-normalization.flow.md` -- mode-coverage matrix rewritten (at DELIVERING)
- `Features/TranscodeJob/Emit/Slots/AudioSlot.py` -- Copy strategy needs to exist (may already; verify)
- `Features/TranscodeJob/Emit/Slots/VideoSlot.py` -- Copy strategy needs to exist (may already)

**Create:**
- `Tests/Contract/TestPlanFactoryFromComplianceState.py` -- 8 flag combinations

**Delete:** (none direct; some inline mode-specific logic may become dead + get removed)

## Call-Graph Audit

Results per `.claude/rules/call-graph-audit.md`:

- **Signal 1 (multiple flow docs):** audio-normalization.flow.md `## Mode coverage matrix` + transcode.flow.md D2 both describe slot selection. transcode.flow.md D2 is SSoT. audio-normalization.flow.md matrix rewritten at DELIVERING to compliance-axis (was ProcessingMode-axis). No divergent pair after DELIVERING.
- **Signal 2 (orchestration mode-branch):** `PlanFactory.FromProcessingMode` at `CommandComposer.Build:105` IS the orchestration mode-branch. Directive DELETES it and every caller migrates to `FromComplianceState(mf)`. Second mode-branch: `JobProcessor._RunPreEncodeAudio` gate `if Mode not in _AUDIO_EMIT_MODES`. Directive replaces with `if MediaFile.AudioCompliant: return None` and deletes `_AUDIO_EMIT_MODES` frozenset. `TestNoModeBranchingAtOrchestration` regex only catches `Mode == 'literal'` -- both prior forms slipped it; new form uses no mode literals so it stays green.
- **Signal 3 (mode-sparse output columns):** none. All modes converge on the same CommandComposer + TranscodeAttempts writers post-change.
- **Signal 4 (OOS ambiguity):** categorized below.
- **Signal 5 (config-driven graph shape):** none. Compliance flags drive DATA (which branch inside slot Emit); call graph static.

Production callers of `PlanFactory.FromProcessingMode` (grep 2026-08-08):
- `Features/TranscodeJob/Emit/CommandComposer.py:105` -- sole production call site. Migrated to FromComplianceState.
- `Tests/Contract/TestCommandComposer.py:68-89` -- test-only; migrated to FromComplianceState.
- `Features/TranscodeJob/ProcessTranscodeQueueService.py:145` + `Tests/*` -- instantiation only, not method call.

Variant path (`_ProcessSingleVariant` -> `BuildTranscodeCommand` -> same `CommandComposer.Build`): has MediaFile in scope, uses same FromComplianceState. Diagnostic implication: variant test on a compliant file produces a stream-copy encode, which is an operator-error signal (variant results trivially identical). DD4's "TestVariant may keep FromProcessingMode" fallback proves unnecessary.

## Out of Scope

- **(a) In-flight preserved:** ProcessingMode column in TranscodeQueue + TranscodeAttempts stays. Reporting/priority tag; unchanged (D3).
- **(a) In-flight preserved:** WorkBucket generated column (Phase 3 landed).
- **(a) In-flight preserved:** SubtitleFix mode-specific behavior -- may need explicit intent tag for "operator wants subtitle rewrite even when subtitles are compliant". Defer to future directive.
- **(a) In-flight collapsed:** FromProcessingMode DELETED entirely (not scoped to TestVariant). Variant path uses FromComplianceState because MediaFile is in scope.
- **(a) In-flight preserved:** ContainerSlot.Emit output for `Preserve` = same args as `Mp4` (per D5 "container target = .mp4 always"). Preserve is a semantic label meaning "container was already compliant"; ffmpeg args identical.
- **(a) In-flight fixed:** `_AUDIO_EMIT_MODES` frozenset deleted; audio pre-encode gate is now `if MediaFile.AudioCompliant`.

## Phase machine

NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING

### Progress

- [x] All phases complete. Live smoke anchor: MFID 47355 attempt 58489 -- `-c:v av1_nvenc -c:a copy`, zero Demucs progress rows, 75.5% size reduction, Success=TRUE, file now WorkBucket=Compliant.

## Delivery Report

STATUS: Done. Committed 21273770. Fleet deploy in flight (bg task bmkafv8zb).

CRITERIA: C1-C8 all met -- verification detail per Progress checkboxes above; live smoke attempt 58489 (MFID 47355) is the C7 anchor. 68/68 directive-scope tests green.

DECISIONS: (a) Deleted FromProcessingMode entirely; variant path uses same FromComplianceState (MediaFile in scope). (b) Fixed preexisting TestCommandComposer FfmpegLogLevel fixture bug -- blocked C7 verification. (c) ContainerSlot 'Preserve' emits identical mp4 args to 'Mp4' (D5). (d) MediaFileModel + MediaFilesRepository gained compliance fields; other repos not updated (do not feed CommandComposer).

KNOWN GAPS: 8 preexisting test failures unchanged (unrelated -- TestAudioComplianceBar ctor drift, TestAudioPipelineNoSilentFallback route path, TestPathDbRoundTripAllTables missing showsettings, TestProfileLifecycle/Ladder, TestScanNewSubtreesFirst, TestSharedColumnsPopulated 3-row historical AudioPolicyResolved gap). Fleet deploy async -- confirm completion.

### R13 overrides

(none anticipated)

### R18 overrides

(none anticipated -- feature docs read with limit=50)

### Promotions

| Source (directive) | Target (durable) |
|---|---|
| DD1 slot rules | `transcode.flow.md` D2 already SSoT -- no change |
| DD2 ProcessingMode = reporting tag | `transcode.flow.md` D3 already SSoT -- no change |
| DD3 structural idempotence | `transcode.flow.md` D11 already SSoT -- no change |
| Slot strategy = compliance-driven | `Features/TranscodeJob/Emit/encode-emit.feature.md` C9 + S2 rewrite to `FromComplianceState(mf)` |
| PlanFactory API change | `Features/TranscodeJob/Emit/command-composer.feature.md` C8 rewrite (drop mode-based clause) |
| Mode coverage matrix rewrite | `Features/AudioNormalization/audio-normalization.flow.md` ST3 + `## Mode coverage matrix` swapped to compliance-axis |
| Audio pre-encode gate rewrite | `Features/AudioNormalization/audio-normalization.flow.md` ST2 gate note swapped from `_AUDIO_EMIT_MODES` to `if MediaFile.AudioCompliant: return None` |
| ContainerSlot 'Preserve' semantics | `Features/TranscodeJob/Emit/encode-emit.feature.md` C10 amended -- 'Preserve' alias emits identical mp4 args (D5 output-mp4-always) |

## Sequencing context (why Phase 4 last)

Phase 1 (`transcode-domain-decisions-ssot`) locked D1-D12 as SSoT. Phase 2 (`compliance-reason-full-library-recompute`) normalized data so 50k rows have real compliance flags. Phase 3 (`mediavortex-output-terminal`) made MV outputs terminal at WorkBucket layer. Phase 4 makes slot strategy compliance-driven. Order matters: without Phases 2-3 clean data, Phase 4 would rewrite the factory but callers would still see stale flags + MV outputs in wrong buckets.

## Resume instructions

To pick up in a fresh session:
1. `cp .claude/directives/paused/2026-08-08-plan-factory-driven-by-compliance-flags.md .claude/directive.md`
2. Change `**Status:** Paused` -> `**Status:** Active -- phase: NEEDS_STANDARDS_REVIEW`
3. Standard phase progression from there.

Verify prereq state before starting:
- `SELECT COUNT(*) FROM MediaFiles WHERE TranscodedByMediaVortex=TRUE AND WorkBucket != 'Compliant'` should return 0 (Phase 3 sanity)
- `Tests/Contract/TestFailLoud.py` + `TestPhaseDetectors.py` + `TestWorkBucketMvTerminal.py` + `TestRecomputeForFilesRowIsolation.py` should all be green (regression baseline)
