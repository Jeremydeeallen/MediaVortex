# Next Session Plan: audio-vertical-dialog-boost-enforcement

## Context (why this directive)

`AudioVertical.Evaluate` currently returns `AudioCompliant=True` when `MediaFile.AudioComplete=True`, without verifying the file actually carries a Dialog Boost track. Per operator's mandatory Dialog Boost policy (audio-normalization.C1), every playback file must ship with a Dialog Boost track. The evaluator's missing check has let **32,957 `-mv.mp4` files** slip through as `AudioCompliant=True` without the track. Bug discovered 2026-08-13 while debugging why the Remux queue wasn't draining (root cause of that specific symptom was the VideoSlotStrategy bug, now fixed; this Dialog Boost enforcement gap is the DEEPER architectural issue predating it).

**Spec already exists.** `Features/AudioNormalization/audio-vertical-dialog-boost-enforcement.feature.md` was drafted 2026-07-17 with C1-C6 spelling out the exact fix. Directive was queued on `.claude/current-feature` stack at slot #2 but never implemented -- got interrupted by other stack work and drowned. This session picks it up and ships it.

## Domain policy (locked 2026-07-17, do not re-litigate)

- Every playback file MUST have a Dialog Boost track. No exceptions for at-target-loudness sources.
- Untranscoded sources (`TranscodedByMediaVortex=FALSE`) are NOT compliant on the audio axis regardless of measured LUFS.
- Ground truth = latest successful `TranscodeAttempts.AudioTracksEmittedJson` for the MediaFileId contains a Dialog Boost track. No cutover-date constant; data self-verifies.

## Fix shape

`AudioVertical.Evaluate(Mf)` collapses to:

```
if IsAudioOnlyContainer(Mf): return (None, 'non_video_scope')
if Mf.AudioCorruptSuspect: return (None, 'audio_corrupt_suspect')
if not Mf.AudioCodec and Mf.Resolution: return (None, 'no_audio_stream')
if not Mf.TranscodedByMediaVortex: return (False, 'no_dialog_boost')  # untranscoded fail
if _HasDialogBoostTrack(Mf.Id): return (True, None)
return (False, 'no_dialog_boost')
```

`_HasDialogBoostTrack(MediaFileId)` reads latest successful `TranscodeAttempts.AudioTracksEmittedJson` for that MediaFileId + returns TRUE iff any track has `Label='Dialog Boost'` (matches AudioFilterEmitter's write shape).

`AudioComplete` column preserved for metadata (LUFS-at-target signal) but no longer read by `AudioVertical.Evaluate`. Grep of `AudioVertical.py` for `AudioComplete` returns 0 after change.

## Success criteria (from existing feature doc, do not re-draft)

- **C1** `AudioVertical.Evaluate` returns Compliant=True iff latest successful TranscodeAttempts row has AudioTracksEmittedJson with Dialog Boost track.
- **C2** Untranscoded sources (TranscodedByMediaVortex IS NOT TRUE) return Compliant=False Reason='no_dialog_boost'.
- **C3** AudioComplete column preserved but no longer read by Evaluate. Grep verifies.
- **C4** Retire 4 MarkAudioComplete call sites per spec (3 delete/rework, 1 keep). Grep of MarkAudioComplete returns exactly one live call (TranscodedOutputPlacement post-loudnorm).
- **C5** Evaluate body ≤ 25 lines total.
- **C6** Contract test `Tests/Contract/TestAudioVerticalDialogBoostStrict.py` covers 4 cases (with-boost / prior-attempts-no-boost / untranscoded-at-target / untranscoded-not-at-target).

## Files (per existing feature doc)

- `Features/AudioNormalization/AudioVertical.py` (collapse Evaluate + add _HasDialogBoostTrack helper)
- `Features/AudioNormalization/audio-vertical-dialog-boost-enforcement.feature.md` (already drafted; ship as-is; amend Status at DELIVERING)
- `Features/AudioCompletion/AudioStateService.py` (retain LUFS-at-target metadata detection but stop flipping AudioComplete=TRUE on scan-time inference per C4)
- `Features/AudioCompletion/AudioCompletionController.py` (rework operator-override endpoint; add AudioComplete_OperatorOverride BOOL column via migration)
- `Features/MediaProbe/MediaProbeBusinessService.py` (delete _MaybeAutoMarkAudioCompleteAtTarget per C4)
- `Features/FileReplacement/TranscodedOutputPlacement.py` (keep the post-loudnorm MarkAudioComplete per C4 exception)
- `Scripts/SQLScripts/AddAudioCompleteOperatorOverride_2026_08_13.py` (NEW; per C4)
- `Tests/Contract/TestAudioVerticalDialogBoostStrict.py` (NEW; per C6)
- `Features/AudioNormalization/audio-normalization.feature.md` (tighten C1 wording from "encoder output ships >=2 streams" to "compliance verifies Dialog Boost track present")

## Expected library churn (locked estimate updated 2026-08-13)

- Pre-fix `IsCompliant=TRUE` count: ~32,957 (MediaFiles WHERE AudioCompliant=TRUE AND -mv.mp4)
- Post-fix estimate: dropped by ~30k → most flip to WorkBucket='AudioFix' (some to Transcode if video also fails)
- Massive workload storm on wakko-worker-1 (Demucs), I9-2024, mv-worker-1 (CPU Demucs = slower per larry hardware inventory)
- Days to drain full backlog

## Prior-session context to inherit

Current stack top (after close of videoslotstrategy-persisted):
```
mediafiles-uniqueness-owner
audio-vertical-dialog-boost-enforcement   ← TOP; take up next
e2e-bug-fixes
concurrency-cap-live-reload
probe-loudness-remove
worker-memorymax-cgroup                    ← MemoryMax=14G active on wakko
preencode-loudness-cache-hit               ← shipped + deployed
```

Recent shipped work relevant to this directive:
- `pre-encode-savings-gate` (2026-08-11) -- AssignedProfile-anchored ceiling + InsufficientSavings gate at 20%
- `pre-encode-pipeline-parallel` (2026-08-11) -- SourceMeasure parallelized with Demucs chain
- `preencode-loudness-cache-hit` (2026-08-12) -- MediaFiles source-loudness cache skips SourceMeasure ffmpeg
- `worker-memorymax-cgroup` (2026-08-12; paused) -- MemoryMax=14G on wakko unit; OOM cadence ~10min still
- `videoslotstrategy-persisted` (2026-08-13; JUST CLOSED) -- fixes Remux/AudioFix false-rejects from InsufficientSavings gate

Fleet state (Version 58bbac74 in flight to wakko + mv-w; I9-2024 already on it):
- I9-2024 Online, 58bbac74
- dot-worker-1 Online, older (out of scope this deploy)
- wakko-worker-1 Online (was on 38970c12; deploy in flight; MemoryMax=14G on unit)
- mediavortex-workers-worker-1 Online (was on 38970c12; deploy in flight)

Known open concerns (not blocking, tracked):
- Wakko OOM cadence ~10 min at MemoryMax=14G; 15 GiB physical RAM is thin for the workload. RAM upgrade to 32GB DDR4-3200 recommended eventually.
- larry LXC (mediavortex-workers-*) is CPU-only, Demucs takes 6+ min per job (vs I9 GPU ~1-2 min). Expect slow drain there.

## Recommended session shape

1. Read the existing feature doc: `Features/AudioNormalization/audio-vertical-dialog-boost-enforcement.feature.md` (limit 50).
2. Read the existing audio-normalization.feature.md sections C1, C34-C42 for context.
3. Confirm the 4 MarkAudioComplete call sites still match the spec's C4 list (grep + read each).
4. Plan implementation order:
    a. Migration for `AudioComplete_OperatorOverride` column
    b. Rewrite `AudioVertical.Evaluate` per fix shape above
    c. Add `_HasDialogBoostTrack` helper (SELECT AudioTracksEmittedJson from latest Success=TRUE TranscodeAttempts row for MediaFileId; jsonb `@>` or ILIKE 'Dialog Boost')
    d. Retire the 4 MarkAudioComplete sites per C4
    e. Contract test per C6
    f. Amend audio-normalization.feature.md C1 wording
5. Advance phase gates normally.
6. IMPLEMENTING: land code + tests.
7. VERIFYING: contract test + live smoke on I9 -- pick a MediaFile with `AudioComplete=TRUE` but no Dialog Boost attempt; call `AudioVertical().Evaluate(Mf)` in a REPL/script; confirm Compliant=False + Reason='no_dialog_boost'. Also pick one WITH Dialog Boost; confirm Compliant=True.
8. Library recompute: run `AudioVertical.RecomputeFor(all_ids_where_audiocompliant_true)` in chunks. Report before/after counts.
9. DELIVERING: Promotions, feature-doc amendment (audio-normalization.C1 wording), delivery report. Close.

## Do NOT do in this session

- Do not re-litigate the domain policy (locked 2026-07-17).
- Do not attempt to also fix `AudioComplete` flag semantics globally -- feature doc explicitly preserves the column for metadata.
- Do not attempt to backfill / retroactively "un-mark" the 32k files' `AudioComplete=True` values. Column stays; only `AudioCompliant` derivation changes.
- Do not chase per-mode workload-shaping (e.g. "should we throttle Remux to avoid the storm") -- correct behavior is to route them to AudioFix and let workers drain naturally.
- Do not open a new feature doc; extend the existing `audio-vertical-dialog-boost-enforcement.feature.md`.

## First operator prompt suggestion (paste after clearing context)

> Take up the top of the stack: `audio-vertical-dialog-boost-enforcement`. The spec is already drafted in `Features/AudioNormalization/audio-vertical-dialog-boost-enforcement.feature.md` (C1-C6, dated 2026-07-17). Full session plan lives at `.claude/next-session-plan.md`. Read that plan first, then execute.
