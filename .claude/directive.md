# Directive: dialog-boost-emission-integrity

**Status:** Active -- phase: IMPLEMENTING

## Interrupts: preencode-loudness-cache-hit

## Outcome

Close two production bugs at their architectural root and add visibility for the population already damaged. Operator paused all transcode/remux/audio jobs 2026-09-09 pending this fix.

**Bug A -- N-boost emit (1,173 files).** `AudioFilterEmitter.EmitTracks` couples Dialog Boost emission INTO the per-stream loop. Boost is a per-FILE artifact (one premix WAV, one output track); Original preservation is a per-STREAM artifact. Coupling produces N boost blocks when N source streams share default language. Root cause: SRP violation -- one loop doing two-arity work.

**Bug B -- Demucs on prior boost (18,804 files).** Pipeline does not recognize its OWN prior output. `_SelectPreferredAudioIndex` picks track 0 blindly and `AudioFilterEmitter` iterates raw ffprobe streams -- neither filters out prior MV-emitted Dialog Boost tracks. When source is `-mv.mp4`, track 0 IS a prior Boost; Demucs runs on it (echo artifact) and the "Original" emit copies it as if it were the true original. Root cause: missing input-classification step -- we lack a boundary that distinguishes true source audio from prior MV output.

**Population flag.** 18,804 damaged files invisible in the DB. Add `MediaFiles.HasDoubleBoostSuspect BOOL` + backfill for tracking. Re-source policy is a future directive.

## Acceptance Criteria

C1. **Boost emission moved OUT of per-stream loop.** `AudioFilterEmitter.EmitTracks` structure: (a) compute `EmitDialogBoost` once; (b) if true, append ONE `_BuildDialogBoostBlock` block with `Language=DefaultLanguage` before the loop; (c) loop over `AudioStreams` and append `_BuildOriginalBlock` per stream; (d) `IsDefault` on Original blocks is FALSE whenever a Boost block was emitted (boost carries the default). No `if EmitDialogBoost and IsDefaultLanguage:` inside the loop. Verifiable: `Tests/Contract/TestAudioFilterEmitterOneBoostPerFile.py` -- synthetic AudioStreams=[3 eng streams] + non-empty DemucsPremixPath produces Blocks with `sum(1 for B in Blocks if B.Label=='Dialog Boost') == 1` AND `sum(1 for B in Blocks if B.Label=='Original') == 3` AND boost's OutputIndex==0.

C2. **`SourceAudioTrackSelector` classifies input.** New `Features/AudioNormalization/SourceAudioTrackSelector.py` with `SelectTrueSourceStreams(FfprobeStreams: list) -> list` filters out any stream whose ffprobe `tags.handler_name` starts with `Dialog Boost` OR `tags.title == 'Dialog Boost'`. Consumed by `PreEncodeAudioPipeline._SelectPreferredAudioIndex` (picks from filtered list only) AND by the caller that populates `AudioSlot.Emit(Context={..., 'AudioStreams': ...})` (passes filtered list into `AudioFilterEmitter.EmitTracks`). If filter removes ALL audio streams (source is prior-boost-only, unrecoverable), raise `PriorBoostSourceError` fail-loud from the selector -- pre-encode aborts, transcode fails, operator handles. Verifiable: `Tests/Contract/TestSourceAudioTrackSelector.py` -- (a) mixed input [prior boost + real original + jpn dub] returns [real original + jpn dub]; (b) all-boost input raises `PriorBoostSourceError`; (c) fresh source with no boost tags returns input unchanged.

C3. **Damaged population flagged.** `MediaFiles.HasDoubleBoostSuspect BOOL NOT NULL DEFAULT FALSE` exists. `Scripts/SQLScripts/AddDoubleBoostSuspectColumn_2026_09_09.py` idempotent migration adds the column + backfills via `UPDATE MediaFiles SET HasDoubleBoostSuspect=TRUE WHERE Id IN (SELECT DISTINCT MediaFileId FROM TranscodeAttempts WHERE Success=TRUE AND DialogBoostEmitted=TRUE AND ffpmpegcommand ILIKE '%-mv.mp4"%')`. Migration prints pre-backfill snapshot count and post-backfill flagged count. Verifiable: `Tests/Contract/TestDoubleBoostSuspectColumn.py` -- column exists with correct type/nullability/default; `SELECT COUNT(*) FROM MediaFiles WHERE HasDoubleBoostSuspect=TRUE` matches the pre-migration snapshot (18,804 at directive open 2026-09-09).

## Call-Graph Audit

- **Flow docs touched:** `Features/AudioNormalization/audio-normalization.flow.md` (Demucs stage + emit stage). `transcode.flow.md ST5` (audio slot) shape unchanged. No parallel flow doc -- single ownership.
- **Orchestration mode-branch:** none introduced. `AudioSlot.Emit` shape unchanged. `SourceAudioTrackSelector` is a boundary sanitization step, not a mode branch.
- **Shared output columns:** `DialogBoostEmitted` write path unchanged -- boost still emitted for compliant fresh sources. `AudioTracksEmittedJson` shape unchanged -- boost + originals still recorded per attempt. Fail-loud on prior-boost-only sources means attempt row records failure honestly rather than fabricating a copy-through.
- **OOS clarity:** every out-of-scope item categorized (b) -- acknowledged debt.
- **Config-driven graph shape:** none. Selector is unconditional; no flags branch the call graph.

## Out of Scope

- **(b) Re-transcoding the 18,804 affected files.** Originals gone; requires re-sourcing pipeline that does not exist. Flag visibility is the only output. Acknowledged debt; separate directive when operator decides re-source policy.
- **(b) Per-volume Dialog Boost policy** (original ask that surfaced this bug). Deferred to its own directive once integrity fixes land.
- **(b) Blocking re-transcode of `-mv.mp4` at admission gate.** Fail-loud at pre-encode covers the audio damage; video re-encode for compliance is still a valid reason to re-transcode a `-mv.mp4` file. Admission-gate hardening is a separate concern.

## Files

- `Features/AudioNormalization/AudioFilterEmitter.py`
- `Features/AudioNormalization/SourceAudioTrackSelector.py` (new)
- `Features/AudioNormalization/Services/PreEncodeAudioPipeline.py`
- `Features/AudioNormalization/Services/AudioPreEncodeFacade.py` (wire selector output through Context)
- `Features/TranscodeJob/Emit/Slots/AudioSlot.py` (consume selector output from Context)
- `Scripts/SQLScripts/AddDoubleBoostSuspectColumn_2026_09_09.py` (new)
- `Tests/Contract/TestAudioFilterEmitterOneBoostPerFile.py` (new)
- `Tests/Contract/TestSourceAudioTrackSelector.py` (new)
- `Tests/Contract/TestDoubleBoostSuspectColumn.py` (new)

## Progress

- [x] Standards review (NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN)
- [x] Plan phase (NEEDS_PLAN -> NEEDS_DOC_PREREAD)
- [x] Doc preread (NEEDS_DOC_PREREAD -> IMPLEMENTING)
- [ ] C1 -- restructure loop + test
- [ ] C2 -- SourceAudioTrackSelector + wire + test
- [ ] C3 -- column + backfill migration + test
- [ ] Verification -- smoke transcode 3 real files after unpause: (a) fresh source 1 eng track, (b) fresh source 3 eng tracks, (c) already-boosted `-mv.mp4` (expect fail-loud)
- [ ] DELIVERING: promotions to `audio-normalization.feature.md` + `audio-normalization.flow.md`

### Promotions

(Populated at DELIVERING.)

### Plan

1. **Doc preread.** Read `Features/AudioNormalization/audio-normalization.feature.md` + `Features/AudioNormalization/audio-normalization.flow.md` (partial per R18). Read `Features/AudioNormalization/AudioFilterEmitter.py`, `PreEncodeAudioPipeline.py`, `AudioPreEncodeFacade.py`, `Features/TranscodeJob/Emit/Slots/AudioSlot.py` in full. Grep callers of `_SelectPreferredAudioIndex` and `EmitTracks` to confirm no other consumers.
2. **C3 first (independent).** Land migration script + contract test. Runs before code changes so DB is ready.
3. **C2 next (foundation).** Add `SourceAudioTrackSelector`. Wire into `PreEncodeAudioPipeline._SelectPreferredAudioIndex` (filter before pick) + into the pre-encode context assembly so `AudioSlot.Emit` receives filtered streams. Contract test.
4. **C1 last (depends on selector).** Restructure `AudioFilterEmitter.EmitTracks`: hoist boost emit above loop; loop emits Original only. Contract test.
5. **Verification.** All contract tests pass locally. Operator unpauses transcode. Smoke: 3 real files across the 3 scenarios; assert output track shape (2, 4, fail-loud).
6. **DELIVERING.** Promote C1/C2 shape into `audio-normalization.feature.md` (add `## Seams` rows for selector); promote pipeline stage detail into `audio-normalization.flow.md`. Populate `### Promotions` table. Commit.
