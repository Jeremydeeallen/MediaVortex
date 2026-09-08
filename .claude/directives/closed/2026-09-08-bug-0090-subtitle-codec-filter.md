# bug-0090-subtitle-codec-filter

**Status:** Closed 2026-09-08

## Interrupts

Parent: `preencode-loudness-cache-hit` (paused below on stack).

## Ask

Stop the bleeding: 100% of I9-2024 transcode attempts failing since 00:38 UTC 2026-09-08 because `SubtitleSlot` emits permissive `-map 0:s? -c:s mov_text` when source has subtitle streams tagged `codec_name=unknown`/`none`/`null` (Tom & Jerry Show WEBDL example; 108 failures / 7d, all on I9). KISS: whitelist `mov_text`-compatible source codecs at the SubtitleSlot boundary, drop everything else with a per-stream log line. One file + probe seam + contract test.

## Context

`Features/TranscodeJob/Emit/Slots/SubtitleSlot.py` today handles image-based subs (`IMAGE_SUB_CODECS` = PGS / DVDSUB / DVBSUB / xsub) correctly for MP4 targets -- drops them or maps only decodable text indices via `SubtitleStreams=[(idx, codec), ...]` when mixed. Line 55 fallback (`HasImage=False`) unconditionally emits `-map 0:s? -c:s mov_text`. That path fires when source has ONLY non-image codecs, which today includes `unknown` / `none` because `HasText = any(F and F not in IMAGE_SUB_CODECS for F in Formats)` treats any non-image codec as text.

ffmpeg's `-map 0:s?` `?` guard means "no matching stream ok"; it does NOT mean "matching-but-undecodable ok". A subtitle stream with `codec_name=unknown` matches the selector, ffmpeg tries to bind it to `mov_text` output, fails with `[sist#0:N/none @ ...] Decoding requested, but no decoder found for: none` -> `[sost#0:M/mov_text @ ...] Error binding an input stream` -> `Invalid argument` -> rc=-22 / rc=4294967274.

`SubtitleFormats` argument is a comma-joined ffprobe codec_name string; `SubtitleStreams` is `[(index, codec), ...]`. Both are populated by CommandComposer L213 from probe output. The producer already has the data; only classifier is wrong.

Real-world subtitle codec distribution for our sources:
- **Text (decodable to `mov_text`)**: `subrip` / `srt`, `ass`, `ssa`, `mov_text`, `webvtt` / `vtt`, `tx3g`, `microdvd`, `text`.
- **Image (needs OCR, drop)**: `hdmv_pgs_subtitle`, `pgssub`, `pgs`, `dvd_subtitle`, `dvdsub`, `dvb_subtitle`, `dvbsub`, `dvb_teletext`, `xsub`.
- **Undecodable (drop)**: `unknown`, `none`, `null`, `''`.

## Acceptance Criteria

**AC1.** `SubtitleSlot.py` adds explicit `TEXT_SUB_CODECS` whitelist frozenset containing every codec name that ffmpeg reliably decodes into `mov_text` output. Bug class today: `HasText = any(F not in IMAGE_SUB_CODECS ...)` counts `unknown` as text. Fix: `HasText = any(F in TEXT_SUB_CODECS ...)`. Introduces third `UNDECODABLE_SUB_CODECS = {'unknown', 'none', 'null', ''}` explicitly for log clarity (a stream in this set is a "dropped undecodable" rather than a "dropped image").

**AC2.** MP4-target emission path: when `SubtitleStreams` present, filter by `codec IN TEXT_SUB_CODECS` -> emit explicit `-map 0:<idx>?` per surviving stream + single `-c:s mov_text` at end. When `SubtitleStreams` absent AND all Formats are TEXT_SUB_CODECS, keep the legacy `-map 0:s? -c:s mov_text` shortcut (backward compat for callers not yet passing per-stream tuples). Otherwise drop-all with warning.

**AC3.** Every dropped stream logs its `(index, codec, reason)` once per Emit call. Aggregate log line at INFO level names how many kept + how many dropped by reason (image / undecodable / other). Verifiable: caller can reconstruct which streams were dropped from Logs.

**AC4.** Non-MP4 target (MKV) behavior unchanged -- `-map 0:s? -c:s copy` remains. Container accepts arbitrary subtitle codecs; no drop needed.

**AC5.** Contract test `Tests/Contract/TestSubtitleSlotCodecFilter.py` covers: (a) source with 1 `subrip` + 1 `unknown` -> argv contains `-map 0:<subrip_idx>?` only + log names 1 dropped; (b) source with 3x `unknown` -> argv contains no `-map 0:s`; (c) source with mixed `subrip` + `hdmv_pgs_subtitle` -> only subrip mapped; (d) source with only `subrip` streams -> permissive shortcut preserved; (e) MKV target with `unknown` -> `-map 0:s?` unchanged (MKV accepts anything).

**AC6.** Existing test `Tests/Contract/TestCommandComposer.py::test_subtitle_slot_always_fires` continues to pass (regression guard).

**AC7.** Live smoke on I9-2024: requeue MediaFileId 701985 (Tom & Jerry S02E18, 3x unknown subs) via `/api/TranscodeQueue/ForceAdd` -> attempt succeeds -> log shows `SubtitleSlot: dropped 3 subtitle streams (codec=unknown x3) MediaFileId=701985` -> resulting `-mv.mp4` has zero subtitle streams (`ffprobe -select_streams s -show_streams` returns empty). No fleet redeploy needed -- I9 runs from source tree, restart picks up the change.

## Out of Scope

- **(b) acknowledged debt**: OCR-based image-subtitle -> text conversion (`BUG-0083` slot referenced in current SubtitleSlot). Would enable preserving PGS subs. Separate directive if operator wants it.
- **(b) acknowledged debt**: BUG-0089 (Windows command-line 32KB cap on multi-stream files, sibling issue in same area). Distinct root cause (argv length, not decoder mismatch).
- **(b) acknowledged debt**: automated failure-class taxonomy so BUG-0090 failures show operator-actionable remediation. Deferred to `BUG-0095`.
- **(a) collapsed in-flight**: SQL mitigation to mark the 38 currently-stuck files as `Failed` (preventing further re-queue loops). Do this only if fix doesn't land within a couple hours -- otherwise the fix itself clears them on next requeue.

## Files

- `Features/TranscodeJob/Emit/Slots/SubtitleSlot.py` -- add whitelist + refactor classifier + per-stream drop logging.
- `Features/TranscodeJob/Emit/CommandComposer.py` -- verify probe pass supplies `SubtitleStreams=[(idx, codec), ...]` in every call path that emits SubtitleSlot; no change if already threaded.
- `Features/TranscodeJob/Emit/command-composer.feature.md` -- extend C4 to name the whitelist + undecodable-drop semantics (at DELIVERING).
- `Tests/Contract/TestSubtitleSlotCodecFilter.py` -- new.

## Call-Graph Audit

Five signals per `.claude/rules/call-graph-audit.md`:

1. **Multiple flow docs for one conceptual operation?** No. `transcode.flow.md` is sole pipeline; SubtitleSlot is intra-ST5.
2. **Mode-branching at orchestration level?** No. Classifier lives in SubtitleSlot (a strategy). Container-target branch (MP4 vs MKV) is existing legitimate variance in the same slot.
3. **Shared output columns sparsely populated?** N/A. Directive changes command argv construction, not DB columns.
4. **OOS ambiguity?** Four items marked (b) explicitly; one (a) collapsed-in-flight decision (optional SQL mitigation contingent on fix timing).
5. **Config-driven call-graph shape?** No. TEXT_SUB_CODECS whitelist is a data constant read by the same code path; toggling entries changes which streams flow, not which functions are called.

Clean on all five. Advance to NEEDS_PLAN.

## Plan

1. `SubtitleSlot.py`: add `TEXT_SUB_CODECS` + `UNDECODABLE_SUB_CODECS`. Rewrite `Emit()` MP4 branch:
   - Prefer per-stream mapping when `SubtitleStreams` present: filter by `codec IN TEXT_SUB_CODECS`, emit `-map 0:<idx>?` per survivor, single `-c:s mov_text` at end.
   - Fallback (no `SubtitleStreams`): if all Formats are in TEXT_SUB_CODECS use legacy shortcut `-map 0:s?`; else drop-all with WARNING.
   - Log per-stream drops with `(index, codec, reason)`; aggregate INFO line at end.
2. Verify every SubtitleSlot.Emit caller in CommandComposer threads `SubtitleStreams` from probe. If missing, thread it.
3. New contract test `Tests/Contract/TestSubtitleSlotCodecFilter.py` — 5 scenarios.
4. Run new + existing subtitle tests + TestCommandComposer.
5. VERIFYING: restart I9 WorkerService, ForceAdd MediaFileId 701985, watch attempt, ffprobe output.
6. DELIVERING: extend `command-composer.feature.md` C4; close directive; update KNOWN-ISSUES BUG-0090 to Resolved.

Risk / rollback: additive constants + one function rewrite + one test. Revert = git revert.

## Verification

- **AC1** -- `SubtitleSlot.py` now defines `TEXT_SUB_CODECS` (subrip/srt/ass/ssa/mov_text/tx3g/webvtt/vtt/microdvd/text), `IMAGE_SUB_CODECS` (unchanged), and `UNDECODABLE_SUB_CODECS` ({'unknown','none','null',''}). Classifier bucketizes streams into kept / image / undecodable / other.
- **AC2** -- MP4 target: when `SubtitleStreams` present, filter by `codec IN TEXT_SUB_CODECS` -> emit `-map 0:<idx>?` per survivor + `-c:s mov_text`. Fallback (no SubtitleStreams + all Formats in TEXT set): legacy `-map 0:s? -c:s mov_text`. Otherwise drop-all with WARN.
- **AC3** -- Every drop-containing Emit call logs one INFO line: `kept=<N> dropped_image=<N> dropped_undecodable=<N> dropped_other=<N>; drop_detail=[(idx,codec),...]`. Verified in Logs post-smoke.
- **AC4** -- MKV target unchanged: `['-map', '0:s?', '-c:s', 'copy']`. Test `test_e_mkv_target_unchanged_with_unknown` covers.
- **AC5** -- `Tests/Contract/TestSubtitleSlotCodecFilter.py` 8 tests PASS (5 spec'd + 3 bonus: null-codec, unrecognized-codec-dropped, all-text-all-mapped).
- **AC6** -- Existing `Tests/Contract/TestCommandComposer.py` (29 tests) all PASS. Full run: 37/37 green.
- **AC7** -- Live smoke on I9-2024 (restart at 2026-09-08 01:49:10): requeued MediaFileId 701985 via `POST /api/TranscodeQueue/AddJob {ForceAdd:true}` -> ItemId 221124. Attempt 89361 completed `Success=TRUE`, `transcodedurationseconds=20.51`. FFmpeg command contains ZERO `-map 0:s?` / `-c:s mov_text` args (verified in DB). Log: `SubtitleSlot: kept=0 dropped_image=0 dropped_undecodable=3 dropped_other=0; drop_detail=[(4, ''), (5, ''), (6, '')]`. ffprobe output MP4: 1 video (av1) + 4 audio (opus) + ZERO subtitle streams.

## Promotions

| Source (directive) | Target (durable doc) | Rows |
|---|---|---|
| SubtitleSlot codec whitelist + undecodable-drop semantics | `Features/TranscodeJob/Emit/command-composer.feature.md` C4 (extend) | at close |
| BUG-0090 resolution + smoke evidence | `memory/KNOWN-ISSUES.md` -> Resolved + `memory/BUG-INDEX.md` update | at close |
