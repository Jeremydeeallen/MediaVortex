# Directive: dialog-boost-emission-integrity

**Status:** Closed 2026-09-16

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
- [x] C1 -- restructure loop + test (AudioFilterEmitter.EmitTracks lines 140-152 hoist boost above loop; 5/5 TestAudioFilterEmitterOneBoostPerFile pass)
- [x] C2 -- SourceAudioTrackSelector + wire + test (Features/AudioNormalization/SourceAudioTrackSelector.py; wired in PreEncodeAudioPipeline._SelectPreferredAudioIndex + AudioSlot._EmitReencode; 8/8 TestSourceAudioTrackSelector pass)
- [x] C3 -- column + backfill migration + test (column present, 21,172 files flagged post drain-wait, 2/2 TestDoubleBoostSuspectColumn pass)
- [x] Docs updated in-flight: `audio-normalization.feature.md` S1 SOLID, L1 target shape, Cross-vertical Contract public function row for `SelectTrueSourceStreams`, Files row, Seams row S12; `audio-normalization.flow.md` ST2 (a0) input classification, ST3 selector callsite, Seams row S8
- [x] Verification -- I9 smoke transcodes: (a) Attack on Titan S03E18 1-eng, ffmpeg cmd shows 1 boost + 1 orig correct shape; encode failed at subtitle mov_text -- preexisting unrelated bug. (b) Tom and Jerry S01E06 3-audio-stream FULL E2E success (attempt 94415); live ffprobe on `-mv.mp4` output confirms exactly 4 audio streams = 1 Dialog Boost (eng, default=1) + 3 Originals (spa/por/eng, default=0). Bug A closed at runtime. (c) Selector live-verified against real `-mv.mp4` ffprobe: correctly filters prior Dialog Boost handler tag while keeping Original; fail-loud path unit-tested via TestSourceAudioTrackSelector::test_raises_when_all_streams_are_prior_boost (no all-boost source exists in library for full E2E fail-loud demo)
- [x] DELIVERING: promotions to `audio-normalization.feature.md` + `audio-normalization.flow.md` (populated below; content landed in-flight, recorded retroactively)

### Promotions

| Source artifact in directive | Target durable doc |
|---|---|
| C1 hoist-boost-above-per-stream-loop shape | `audio-normalization.feature.md` S1 (SOLID) rewritten: per-file boost arity vs per-stream Original arity |
| C1 target-state multi-language example | `audio-normalization.feature.md` L1 (Live Verification) rewritten: `N + 1` outputs when boost, `N` when not; example jpn+eng+boost -> 3 tracks; 3 eng streams + boost -> 4 tracks; no output ever carries more than one boost |
| C2 SelectTrueSourceStreams public function | `audio-normalization.feature.md` Cross-Vertical Contract table row added under public class.method surface (filters prior MV boost by handler_name/title, raises PriorBoostSourceError on all-boost input) |
| C2 SourceAudioTrackSelector file | `audio-normalization.feature.md` Files table row added |
| C2 selector -> pre-encode + emit seam | `audio-normalization.feature.md` Seams row S12 (two consumer sites -- deterministic filter, identical results at both callsites; PriorBoostSourceError fail-loud propagates to attempt failure) |
| C2 input-classification stage in pipeline | `audio-normalization.flow.md` ST2 substep (a0) added -- `SourceAudioTrackSelector.SelectTrueSourceStreams` runs before Demucs input-index pick; fail-loud vs fresh-passthrough behavior documented |
| C1 hoist + selector callsite in ST3 | `audio-normalization.flow.md` ST3 rewritten: selector runs at both consumer sites; emitter hoists boost above per-stream loop |
| C2 cross-stage seam | `audio-normalization.flow.md` Seams row S8 (ST2 (a0) input classification -> ST2 (a-e) + ST3 emit; two consumer sites, fail-loud propagation) |
| C3 HasDoubleBoostSuspect column | Contract test `Tests/Contract/TestDoubleBoostSuspectColumn.py` (2/2 pass) is the durable enforcement of column existence + backfill invariant; no `*.feature.md` promotion needed -- column is directly ownable by `MediaFiles` schema |

### Plan

1. **Doc preread.** Read `Features/AudioNormalization/audio-normalization.feature.md` + `Features/AudioNormalization/audio-normalization.flow.md` (partial per R18). Read `Features/AudioNormalization/AudioFilterEmitter.py`, `PreEncodeAudioPipeline.py`, `AudioPreEncodeFacade.py`, `Features/TranscodeJob/Emit/Slots/AudioSlot.py` in full. Grep callers of `_SelectPreferredAudioIndex` and `EmitTracks` to confirm no other consumers.
2. **C3 first (independent).** Land migration script + contract test. Runs before code changes so DB is ready.
3. **C2 next (foundation).** Add `SourceAudioTrackSelector`. Wire into `PreEncodeAudioPipeline._SelectPreferredAudioIndex` (filter before pick) + into the pre-encode context assembly so `AudioSlot.Emit` receives filtered streams. Contract test.
4. **C1 last (depends on selector).** Restructure `AudioFilterEmitter.EmitTracks`: hoist boost emit above loop; loop emits Original only. Contract test.
5. **Verification.** All contract tests pass locally. Operator unpauses transcode. Smoke: 3 real files across the 3 scenarios; assert output track shape (2, 4, fail-loud).
6. **DELIVERING.** Promote C1/C2 shape into `audio-normalization.feature.md` (add `## Seams` rows for selector); promote pipeline stage detail into `audio-normalization.flow.md`. Populate `### Promotions` table. Commit.
