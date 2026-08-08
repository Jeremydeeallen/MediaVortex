# Directive: plan-factory-driven-by-compliance-flags

**Slug:** plan-factory-driven-by-compliance-flags
**Status:** Paused -- draft awaiting operator resume
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

Before starting, run these five checks per `.claude/rules/call-graph-audit.md`:

- **Signal 1 (multiple flow docs):** audio-normalization.flow.md mode-coverage matrix + transcode.flow.md ST3 both describe slot selection. Confirm both align post-change; consider consolidation.
- **Signal 2 (orchestration mode-branch):** `PlanFactory.FromProcessingMode` IS the orchestration mode-branch. This directive removes it.
- **Signal 3 (mode-sparse output columns):** none anticipated.
- **Signal 4 (OOS ambiguity):** categorize per (a) or (b).
- **Signal 5 (config-driven graph shape):** none anticipated.

## Out of Scope

- **(a) In-flight preserved:** ProcessingMode column in TranscodeQueue + TranscodeAttempts stays. Reporting/priority tag; unchanged.
- **(a) In-flight preserved:** WorkBucket generated column (Phase 3 landed).
- **(a) In-flight preserved:** SubtitleFix mode-specific behavior -- may need explicit intent tag for "operator wants subtitle rewrite even when subtitles are compliant".
- **(b) Tolerated debt:** TestVariant mode may keep FromProcessingMode path (no per-file compliance flags for synthetic variants).

## Phase machine

NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING

### Progress

- [x] NEEDS_STANDARDS_REVIEW (auto-load at session start)
- [ ] NEEDS_PLAN (this doc)
- [ ] NEEDS_DOC_PREREAD: transcode.flow.md D1-D12 (SSoT), audio-normalization.flow.md mode-coverage matrix, PlanFactory source, VideoSlot / AudioSlot / ContainerSlot source
- [ ] IMPLEMENTING: PlanFactory rewrite (FromComplianceState)
- [ ] IMPLEMENTING: migrate call sites
- [ ] IMPLEMENTING: verify AudioSlot.Copy + VideoSlot.Copy strategies exist (add if missing)
- [ ] IMPLEMENTING: contract test (8 flag combinations)
- [ ] VERIFYING: contract test PASS; full audio + phase suites still green
- [ ] SMOKE-GATE: I9 restart; queue video-only-transcode file; ffmpeg cmd shows -c:a copy; no Demucs progress rows
- [ ] DELIVERING: audio-normalization.flow.md mode-coverage matrix rewritten; close report

### R13 overrides

(none anticipated)

### R18 overrides

(none anticipated -- feature docs read with limit=50)

### Promotions

| Source (directive) | Target (durable) |
|---|---|
| DD1-DD5 | `transcode.flow.md` D2 + D3 already cover; audio-normalization.flow.md matrix update lands here |

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
