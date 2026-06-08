# Linear Loudnorm -- measure once, apply as fixed gain, never silently degrade

**Slug:** linear-loudnorm

## Interrupts: scan-drives

## What It Does

Replaces the current single-pass dynamic `loudnorm` + `acompressor`
chain with **linear-mode loudnorm**: a one-pass FFmpeg invocation that
takes the four ebur128 measurements already stored on `MediaFiles` and
applies a fixed gain to land the output at the configured integrated
loudness target. Show-to-show volume is locked; within-show dynamics
pass through untouched.

Three policies fall out of one design:

1. **Linear is the only mode.** No single-pass dynamic fallback. No
   `acompressor`. If the measurements needed for linear mode are
   absent or the math says fixed gain would clip, the file is held out
   of the queue with a named deferral reason. Encodes never start with
   a guarantee MediaVortex cannot keep.
2. **LRA target is dynamic, not fixed.** The target loudness range is
   computed per file as `max(SourceLoudnessRangeLU,
   MinimumLoudnessRangeLU)`. This guarantees `measured_LRA <=
   target_LRA`, which is the condition FFmpeg uses to stay in linear
   mode. Films keep their dynamics; broadcast keeps its 7 LU envelope.
3. **One source of truth for loudnorm parameters.** This feature owns
   the parameter math and chain shape. All other docs reference here.
   Duplicate parameter tables in `Docs/AudioStrategy.md`,
   `audio-completion.feature.md`, `media-tabs-and-loudness.feature.md`,
   `remux.flow.md`, and `transcode.flow.md` are deleted in this
   change.

This feature is the response to two operational problems:

- The user's daily show-to-show loudness jumps (this is what
  integrated-loudness normalization is supposed to solve, but the
  current dynamic mode drifts off target on short or unusual sources).
- The cinematic-content over-compression introduced by chaining
  `acompressor` before a dynamic-mode `loudnorm` targeting `LRA=7`.

It is also the long-form fix for the trust gap exposed by BUG-0013:
silent fallback to a permissive mode is exactly how the audio pipeline
got into trouble. The new contract is "linear or refused -- never
quietly different."

## Concern

Five concerns this feature resolves:

1. **Show-to-show loudness inconsistency.** Single-pass dynamic mode
   drifts several LU from the integrated target on short or unusual
   sources. Linear mode applies a measured fixed gain -- the integrated
   target is hit to within measurement noise (sub-LUFS).
2. **Cinematic content gets squashed.** Today's chain hits films
   (LRA 12-20) with `LRA=7` plus `acompressor`. The combined dynamic
   range compression is audible and irreversible. Dynamic LRA target
   eliminates the squash.
3. **Silent degradation is the failure mode.** Today, when measurements
   aren't available or the math wouldn't land, FFmpeg silently uses
   dynamic mode. Operators cannot tell which files got which treatment.
   The new admission gate makes this an explicit, surfaced state.
4. **Parameter values live in five docs.** `Docs/AudioStrategy.md`
   names them. So does `audio-completion.feature.md`,
   `media-tabs-and-loudness.feature.md`, `remux.flow.md`, and
   `transcode.flow.md`. Five places, four of them stale relative to
   what the code does. Consolidating to one source of truth is part
   of this feature's contract, per the operator's explicit ask.
5. **`acompressor` is dead weight.** It was added in series with
   dynamic loudnorm as belt-and-suspenders. Linear mode is transparent
   by design; running a compressor after it defeats the point and
   pre-compresses the signal in a way that invalidates the stored
   measurements. The compressor is removed.

## Surface

Operator-visible:

- Queue admission deferral counts on the Activity / Library Compliance
  panel: `awaiting_loudness_measurement`, `ungainable_peak_loudness`.
- A SQL one-liner (or panel filter once the parent panel ships) listing
  the files in each deferral bucket so the operator can decide what to
  do.
- Worker logs name the linear gain applied per file
  (`linear loudnorm: gain=+4.3 dB, target_LRA=12 (source 11.4)`).
- Removal of the `AudioCompressionEnabled` and acompressor parameter
  rows from SystemSettings. The `/settings` page no longer shows them.

API-visible:

- No new endpoints. Existing `POST /api/AudioCompletion/Reset` and
  `POST /api/AudioCompletion/MarkComplete` remain unchanged; they
  continue to be the only way to force a re-normalize.

See `linear-loudnorm.flow.md` for the measure->gate->build->encode
pipeline.

## Success Criteria

### A. Schema

1. `MediaFiles.SourceIntegratedThresholdLufs DOUBLE PRECISION` column
   exists, nullable. Migration
   `Scripts/SQLScripts/AddLoudnessThresholdColumn.py` is idempotent
   (`ADD COLUMN IF NOT EXISTS`). Verifiable: `\d MediaFiles` lists the
   column.

1b. `MediaFiles.AudioNormalizationMode VARCHAR(16)` column exists,
    nullable. Populated by the post-flight hook with the mode used
    on the just-completed encode: `'linear'` or `'dynamic'`. NULL for
    rows that have not yet been re-encoded under this feature.
    Verifiable: `\d MediaFiles` lists the column;
    `SELECT DISTINCT AudioNormalizationMode FROM MediaFiles` returns
    a subset of `{NULL, 'linear', 'dynamic'}`.

2. `MediaFiles.AdmissionDeferReason VARCHAR(64)` column exists,
   nullable. Stores `'awaiting_loudness_measurement'`,
   `'loudness_measurement_failed'`, or NULL. The first means "probe
   co-trigger has not run yet for this file"; the second means
   "ebur128 ran and failed, manual operator action needed." Files
   that would have been blocked for ungainable peak (earlier draft)
   are now encoded in dynamic mode instead -- see criterion 10.
   Verifiable: `SELECT DISTINCT AdmissionDeferReason` returns a
   subset of `{NULL, 'awaiting_loudness_measurement',
   'loudness_measurement_failed'}`.

2b. `MediaFiles.LoudnessMeasurementFailureReason VARCHAR(64)` column
    exists, nullable. Populated by `LoudnessAnalysisService.
    PersistLoudness` with the short failure code when ebur128 cannot
    produce measurements (`'ffmpeg_not_found'`, `'timeout'`,
    `'ffmpeg_exit_<N>'`, `'parse_failed'`, `'silent_stream'`). NULL
    on success. Verifiable: invoke PersistLoudness with a failure
    reason argument, observe the column populated.

3. SystemSettings row `MinimumLoudnessRangeLU` exists (default 11).
   This is the LRA floor used as `target_LRA = max(SourceLoudnessRangeLU,
   MinimumLoudnessRangeLU)`. The 11 default puts MediaVortex in the
   same range as Netflix / Apple TV+ playback normalization -- broadcast
   TV stays in linear mode (transparent), cinematic content gets
   measured dynamic-mode compression (dialog up, peaks down,
   integrated still hits -23 LUFS). Verifiable: `SELECT Value FROM
   SystemSettings WHERE SettingName='MinimumLoudnessRangeLU'` returns
   `'11'`.

4. Cleanup migration `Scripts/SQLScripts/DropAudioCompressionSettings.py`
   removes the SystemSettings rows for `AudioCompressionEnabled`,
   `CompressorThreshold`, `CompressorRatio`, `CompressorAttack`,
   `CompressorRelease`, `CompressorMakeup`. Idempotent. Verifiable:
   re-run reports 0 rows deleted.

### B. Measurement capture

5. `LoudnessAnalysisService.ParseSummary` extracts the relative gating
   threshold from the ebur128 stderr Summary block (`Threshold:` line
   in LUFS). Returns it on the `LoudnessResult` dataclass alongside the
   existing three fields. Verifiable: unit test against captured
   stderr from a real ebur128 run produces a non-NULL threshold value
   for a non-silent source.

6. `LoudnessAnalysisService.PersistLoudness` writes all four loudness
   columns atomically on success. On failure (Loudness=None), writes
   `LoudnessMeasuredAt=NOW()` and
   `LoudnessMeasurementFailureReason=<reason>` so the row is
   distinguishable from "not yet attempted." If the parser succeeded
   for some fields but not all, the function treats it as failure
   (writes none of the four loudness columns, records
   `LoudnessMeasurementFailureReason='parse_incomplete'`). Verifiable:
   pass `Loudness=None, FailureReason='timeout'` to PersistLoudness,
   observe `LoudnessMeasuredAt` and
   `LoudnessMeasurementFailureReason='timeout'`, all four loudness
   columns NULL.

7. `Scripts/SQLScripts/BackfillLoudnessThreshold.py` re-runs ebur128 for
   every row where the existing three columns are populated but
   `SourceIntegratedThresholdLufs IS NULL`. Idempotent. Verifiable:
   second run reports 0 rows changed.

8. Probe co-trigger: when `MediaProbeBusinessService` finishes probing
   a file, it enqueues (or directly invokes) a loudness measurement
   for the same MediaFileId. The trigger is unconditional -- every
   probed file gets measured. Verifiable: insert a fresh MediaFile,
   run the probe pipeline, observe all four loudness columns populated
   without separate operator action.

### C. Queue admission gate

9. `_EvaluateCompliance` in `QueueManagementBusinessService` refuses
   to admit any file with `AudioComplete=false` AND any of
   {`SourceIntegratedLufs`, `SourceLoudnessRangeLU`,
   `SourceTruePeakDbtp`, `SourceIntegratedThresholdLufs`} IS NULL.
   The deferral reason depends on `LoudnessMeasuredAt`:
   - `LoudnessMeasuredAt IS NULL` -> measurement has not been
     attempted yet -> `AdmissionDeferReason=
     'awaiting_loudness_measurement'`. The probe co-trigger will
     catch this up; no operator action required.
   - `LoudnessMeasuredAt IS NOT NULL` (measurement attempted but
     produced no numbers) -> `AdmissionDeferReason=
     'loudness_measurement_failed'`. Operator must intervene
     (re-probe, accept the source as-is via MarkAudioComplete, or
     remove the file).
   In both cases the function returns
   `(IsCompliant=NULL, RecommendedMode=NULL)`. Verifiable: insert two
   rows, one with all NULLs (awaiting), one with
   `LoudnessMeasuredAt=NOW()` and measurement columns NULL (failed).
   Recompute, observe the two distinct deferral reasons.

10. `BuildAudioFilters` computes
    `predicted_peak = SourceTruePeakDbtp + (TargetLoudness - SourceIntegratedLufs)`
    (target loudness read fresh from SystemSettings per the no-cache
    rule). If `predicted_peak <= TargetTruePeak`, emits linear-mode
    loudnorm (see criterion 12). Otherwise emits dynamic-mode loudnorm
    with the same `measured_*` params, same target loudness, same
    target TP, no `linear=true` flag. The mode actually used is
    written to `MediaFiles.AudioNormalizationMode` by FileReplacement
    after the post-replacement FFprobe, by parsing the just-run
    FFmpeg command via `AudioCompletionService.DetectNormalizationMode`
    (`linear=true` token => `'linear'`, `loudnorm` without the flag =>
    `'dynamic'`, no `loudnorm` => leave unchanged). Mode choice is
    logged per encode (`linear loudnorm: gain=+X dB` or
    `dynamic loudnorm: ungainable peak (would clip at +Y dBTP)`).
    Verifiable: build commands for two synthetic rows -- one with
    measured_I=-25, measured_TP=-5 (gainable) and one with
    measured_I=-32, measured_TP=-2 (ungainable). Assert the first
    contains `linear=true` and the second does not. Post-encode,
    `MediaFiles.AudioNormalizationMode` reads `'linear'` and
    `'dynamic'` respectively.

10b. The admission gate (`_EvaluateCompliance`) admits ungainable
     files normally -- it does NOT block on the predicted-peak math.
     Linear-vs-dynamic mode selection is a build-time decision, not
     an admission decision. Verifiable: insert a row with
     SourceIntegratedLufs=-35, SourceTruePeakDbtp=-1 (ungainable),
     recompute, observe IsCompliant and RecommendedMode are set
     normally and AdmissionDeferReason is NULL.

11. When an admitted file's measurements later become eligible
    (e.g., a re-probe widens its measured LRA in a way that no longer
    blocks), the next `RecomputeForFiles` call clears
    `AdmissionDeferReason` and admits the file. Verifiable: NULL out a
    measurement, recompute (file deferred), restore the measurement,
    recompute, observe AdmissionDeferReason=NULL and the file admitted.

### D. Command-build

12. `Models.CommandBuilder.BuildAudioFilters` (the single callsite for
    loudnorm across transcode/remux/subtitle-fix) emits exactly one
    audio filter for an `AudioComplete=false` file: a `loudnorm`
    invocation with all four `measured_*` params, `linear=true`, and a
    target LRA computed as `max(SourceLoudnessRangeLU,
    MinimumLoudnessRangeLU)`. No `acompressor`. No second filter.
    Verifiable: build the command for a file with known measurements,
    parse the `-af` value, assert exactly one `loudnorm=...` filter
    with `linear=true` and the expected `measured_*` values.

13. `BuildAudioFilters` raises `RuntimeError` naming the MediaFileId
    and missing fields when called for an `AudioComplete=false` file
    with any measurement column NULL. Defense-in-depth -- this
    condition should already be blocked at admission. Verifiable: call
    `BuildAudioFilters` directly with a synthetic file missing a
    measurement, observe the exception text contains the MediaFileId
    and the missing field names.

14. `BuildAudioFilters` returns `None` (no `-af`) for an
    `AudioComplete=true` or `AudioCorruptSuspect=true` file -- the
    stream-copy branch is unchanged. Verifiable: same as criterion 9
    in `audio-completion.feature.md`.

15. The dynamic LRA computation reads `MinimumLoudnessRangeLU` from
    SystemSettings each call (no module-level cache per the repo-wide
    rule against cached DB settings). Verifiable: change the setting
    via SQL, rebuild a command for the same file, observe the new
    floor applied.

### E. Source-of-truth consolidation

16. `Docs/AudioStrategy.md` Rule 2 (Normalization) is replaced with a
    one-paragraph summary + a pointer to this feature doc. The
    parameter table (TargetLoudness/LoudnessRange/TruePeak rows and the
    acompressor row) is deleted. Verifiable: `grep -E
    'I=-23|LRA=7|TP=-2|acompressor' Docs/AudioStrategy.md` returns no
    matches.

17. `Features/AudioCompletion/audio-completion.feature.md` and
    `audio-completion.flow.md` references to specific loudnorm
    parameters and to `acompressor` are removed. AudioCompletion
    describes only the per-file state machine; loudnorm parameter
    contracts live in this doc. Verifiable: `grep -E
    'I=-23|LRA=7|TP=-2|acompressor'
    Features/AudioCompletion/audio-completion.*` returns no matches.

18. `Features/TranscodeQueue/remux.flow.md` Audio Filter Chain section
    is reduced to one short paragraph + a pointer to this doc. The
    parameter table and acompressor description are deleted.
    Verifiable: same grep returns no matches in `remux.flow.md`.

19. `transcode.flow.md` Stage 5 audio-args note is reduced to one
    sentence + pointer. Verifiable: same grep returns no matches in
    `transcode.flow.md`.

20. `Features/TranscodeQueue/media-tabs-and-loudness.feature.md`
    measurement-capture criteria are amended to declare this doc as
    the consumer. The "4 columns required" contract belongs to this
    doc; that doc still owns the capture mechanism but defers the
    consumer contract here. Verifiable: a `### Defers to` (or similar)
    pointer to `linear-loudnorm.feature.md` appears in the doc.

21. `Features/CommandBuilder/command-builder.feature.md` (if it
    contains audio-chain criteria) is amended to "implements the
    contract defined in linear-loudnorm.feature.md" for the loudnorm
    section. Verifiable: same grep returns no matches in that doc.

22. Grep audit: `rg -F 'I=-23|LRA=7|TP=-2|acompressor' --type md`
    returns matches only in: this feature doc, this flow doc,
    `memory/KNOWN-ISSUES.md` (historical bug entries), the
    `KNOWN-ISSUES-ARCHIVE.md` memory file, and the
    `mediavortex-analyze-transcode` skill if it references them for
    diagnostic reasons. No other live doc names the parameters.

### F. Operator visibility

23. The Activity page "Library Compliance" panel surfaces four
    counts driven by columns this feature owns:
    - "Waiting on loudness measurement"
      (`AdmissionDeferReason='awaiting_loudness_measurement'`)
    - "Loudness measurement failed (operator review)"
      (`AdmissionDeferReason='loudness_measurement_failed'`)
    - "Normalized in linear mode"
      (`AudioNormalizationMode='linear'`)
    - "Normalized in dynamic mode (ungainable peak)"
      (`AudioNormalizationMode='dynamic'`)
    If the parent panel is not yet live, the criterion is satisfied
    by a documented SQL one-liner in this feature's Runbook that
    produces all four counts. Verifiable: run the one-liner, get a
    non-negative integer for each.

24. Worker log line on every loudnorm encode names the mode, applied
    gain, and target LRA:
    - linear mode: `linear loudnorm: gain=+4.3 dB, target_LRA=12 (source 11.4)`
    - dynamic mode: `dynamic loudnorm: ungainable peak (would clip at +5.2 dBTP), target_LRA=12 (source 11.4)`
    Verifiable: pick one of each mode from the past 24 hours, grep
    the worker log for the leading token (`linear loudnorm:` /
    `dynamic loudnorm:`), observe matching lines.

### G. Live verify

25. After deployment, on a file with all four measurements populated
    and an integrated source loudness of about -27 LUFS (typical
    cinematic), force-Reset AudioComplete and re-queue as Remux. The
    output integrated loudness measured by an independent ebur128 pass
    must read within +/- 1 LUFS of `TargetLoudness`. Verifiable:
    `ffmpeg -i <output> -af ebur128 -f null -` reports
    `I:` within `-22.0 .. -24.0 LUFS`.

26. On the same file, the output true peak must be at or below
    `TargetTruePeak`. Verifiable: same ebur128 run reports `Peak:` at
    or below `-2.0 dBTP`.

27. On the same file, the output loudness range must be greater than
    or equal to the source LRA. Verifiable: source LRA from
    `MediaFiles.SourceLoudnessRangeLU`; output LRA from the same
    ebur128 run on the output -- output >= source within +/- 0.5 LU
    measurement tolerance.

### H. Newly-measured at-target short-circuit

28. When the probe co-trigger persists a measurement and
    `SourceIntegratedLufs` falls within +/- `TARGET_LUFS_TOLERANCE`
    of `TargetLoudness` AND the audio codec is MP4-compat, the same
    transaction marks `AudioComplete=true,
    AudioCorruptReason='already_at_target_loudness',
    AudioCompletedAt=NOW()`. The file never enters the encode path
    -- subsequent encodes stream-copy audio per
    `audio-completion.flow.md`. This closes the gap where a
    newly-measured at-target file would otherwise sit eligible for
    a zero-gain encode. Verifiable: insert a probed MP4 file with no
    measurements yet, trigger the probe co-trigger with a synthetic
    ebur128 result of `SourceIntegratedLufs=-23.0`. After the
    measurement persists, the row should read `AudioComplete=true,
    AudioCorruptReason='already_at_target_loudness'` in the same
    transaction. The existing `EvaluateInitialAudioState` clause (d)
    in `AudioCompletionService` already encodes this logic; this
    criterion ensures it is invoked from the probe co-trigger path,
    not only from the initial backfill.

## Status

DRAFT -- criteria pending operator approval. No code until approved.

**Forward-guarantee tests:** `Tests/Contract/TestLinearLoudnormEnforcement.py` enforces the "Linear or refused -- never quietly different" contract mechanically. See `memory/KNOWN-ISSUES.md` BUG-0046 for the legacy-chain damage accounting.

### Progress

- [x] Stack pivot from `scan-drives`; pause snapshot committed (2560fe9)
- [x] Flow doc `linear-loudnorm.flow.md` drafted
- [x] Feature doc (this file) drafted
- [ ] Operator review + criteria approval (BLOCKING)
- [x] Step 1: Schema migrations -- 4 new MediaFiles cols (Threshold, AdmissionDeferReason, LoudnessMeasurementFailureReason, AudioNormalizationMode), MinimumLoudnessRangeLU=11 SystemSettings row, dropped 7 obsolete compressor + LoudnessRange settings. 5,041 rows need threshold backfill. Idempotent re-run verified.
- [x] Step 2: Parser captures Integrated-Threshold; LoudnessResult adds field; PersistLoudness writes 4 cols + LoudnessMeasurementFailureReason atomically; MeasureAndPersist threads failure reason through. Smoke test: parser passes against realistic ebur128 stderr; clause-(d) at-target detection passes against synthetic rows.
- [x] Step 3: BackfillLoudnessThreshold script written. Eligibility SQL verified -- 5,088 rows have I/LRA/TP populated but Threshold NULL and no prior failure. Script reuses LoudnessAnalysisService so updates to the parser flow through automatically. Operator-runnable on a worker host (paused workers per BUG-0013 means dot-worker-1 is the cleanest target). Idempotent.
- [x] Step 4: Probe co-trigger already existed (MediaProbeBusinessService:119); extended with criterion 28 auto-mark hook (`_MaybeAutoMarkAudioCompleteAtTarget`) that flips AudioComplete=true with reason 'already_at_target_loudness' for newly-measured at-target MP4-compat files.
- [x] Step 5: Admission gate added in `_EvaluateCompliance`. Three-state logic (awaiting / failed / legacy-pre-threshold-data). `RecomputeForFiles` SELECT extended for 5 new columns; bulk UPDATE writes `AdmissionDeferReason`. Live-verified: Id=10006 (legacy I/LRA/TP measured, Threshold NULL) defers 'awaiting_loudness_measurement'; AudioComplete=true row sees no measurement deferral.
- [x] Step 6: BuildAudioFilters rewritten -- signature now takes MediaFile (not ProfileSettings). Linear-or-dynamic mode picked from predicted_peak math; emits single filter with all four measured_* params and dynamic LRA = max(source, MinimumLoudnessRangeLU). Raises RuntimeError on missing measurements. AudioNormalizationEnabled kept as kill switch. All three call sites (BuildCommand, BuildRemuxCommand, BuildSubtitleFixCommand) updated to pass MediaFile. Smoke-tested: loud broadcast -> linear, quiet film -> dynamic, missing measurement -> raise.
- [x] Step 7: acompressor code removed in Step 6 rewrite (no longer reads CompressionThreshold/Ratio/Attack/Release/Makeup/AudioCompressionEnabled/LoudnessRange). SystemSettings rows already dropped in Step 1.
- [x] Step 8: Doc consolidation done. Parameter tables removed from Docs/AudioStrategy.md, audio-completion.feature.md, audio-completion.flow.md, remux.flow.md, transcode.flow.md, media-tabs-and-loudness.feature.md, command-builder.feature.md, transcode-vs-remux-routing.feature.md. Grep audit clean -- only allowed files (this feature's docs, KNOWN-ISSUES, mediavortex-analyze-transcode) contain the forbidden tokens.
- [x] Step 9: Operator visibility -- SQL one-liner in Runbook produces all four counts (awaiting / failed / linear / dynamic). Activity panel sub-section will be added when the parent Library Compliance panel ships (per audio-completion.feature.md criterion 18 DEFERRED note). Criterion 23 satisfied via documented SQL fallback.
- [ ] Step 10: Live verify on a real cinematic file per criteria 25-27. Partial verification via pipeline-test-harness 2026-05-24: Quick Fix on MediaFile 683333 (HIMYM S06E08-mv.mp4, 81 MB) ran end-to-end -- integrated loudness landed within ±1 LUFS of target (criterion 25 PASS) BUT true peak measured +1.70 dBTP, exceeding the -2 dBTP target by 3.7 dB (criterion 26 FAIL). Filed as BUG-0014. Dynamic-mode TP enforcement appears broken on hot-peak sources. Full criterion 27 (output LRA >= source LRA) not yet measured. Step requires BUG-0014 fix before re-running. Also surfaced production gaps captured as BUG-0015 (orphan -mv.mp4 disk files), BUG-0016 (orphan MediaFiles rows for -mv.mp4 paths), BUG-0017 (MediaFiles.FileSize NULL drops downstream defense-in-depth check).
- [x] BUG-0019 fix (2026-05-27): `MediaFiles.AudioNormalizationMode` was staying NULL after encodes that ran loudnorm. Two-gap fix: (a) added the column to `DatabaseManager.SaveMediaFile`'s UPDATE/INSERT with COALESCE protection; (b) `FileReplacementBusinessService._UpdateMediaFilesAfterReplacement` now accepts an `FFmpegCommand` parameter and derives the mode via the new `AudioCompletionService.DetectNormalizationMode` helper. Live-verified on canary 3 (MediaFile 6490, Steven Universe S01E37) -- column reads `'linear'`. Round-trip protected by `Tests/Contract/TestMediaFilePersistence.py`. Commit d93c485.

## Runbook

### Day-one bring-up sequence

Execute in order. Each step has an exit condition; do not proceed
until met.

1. **Schema migrations.** Run `AddLoudnessThresholdColumn.py`,
   `AddAdmissionDeferReason.py`, `AddLoudnessMeasurementFailureReason.py`,
   `AddAudioNormalizationMode.py`, `AddMinimumLoudnessRangeSetting.py`,
   `DropAudioCompressionSettings.py`. Exit: `\d MediaFiles` shows the
   four new columns; `SELECT Value FROM SystemSettings WHERE
   SettingName='MinimumLoudnessRangeLU'` returns `'11'`.

2. **Stop workers** (per `memory/feedback_coordinate_live_worker_writes.md`).
   Confirm with the operator before any settings-row deletes that
   workers are paused or otherwise not reading queue rows.

3. **Extend parser + persister.** Capture `Threshold:` from ebur128
   Summary block; write all four loudness cols + failure reason
   atomically. Exit: unit test passes on captured stderr.

4. **Backfill threshold.** Run `BackfillLoudnessThreshold.py` on rows
   that have three loudness cols but NULL Threshold. Exit: second run
   reports 0 rows changed.

5. **Wire probe co-trigger.** `MediaProbeBusinessService` enqueues a
   loudness measurement after every probe completion. Exit: insert a
   fresh MediaFile, run probe, observe all four loudness cols
   populated.

6. **Admission gate.** Add measurement-present check to
   `_EvaluateCompliance` with the two-reason split. Exit: synthetic
   rows reproduce both deferral reasons.

7. **CommandBuilder rewrite.** Linear-or-dynamic per criterion 10.
   Drop `acompressor`. Raise on missing data. Exit: build commands
   for synthetic rows, observe the correct mode per the
   predicted-peak math.

8. **Doc consolidation** (criteria 16-22). Delete duplicate parameter
   tables; add pointers. Exit: grep audit (criterion 22) passes.

9. **Re-enable workers** with `remuxenabled=true`. Watch the four
   Activity counts for the first hour.

### Tuning the dynamic-range floor (operator)

`MinimumLoudnessRangeLU` is the single knob that controls how much
range compression files get. Settings take effect on the next encode
(no restart -- repo-wide rule against cached DB settings applies).

| Setting | Use case |
|---|---|
| 18 | Movie-night / audiophile. Almost everything stays in linear mode. Full cinematic dynamics preserved. |
| 14 | Daytime balanced. Theatrical mixes get mild compression; TV is untouched. |
| 11 | **Default.** Streaming-platform parity (matches Netflix / Apple TV+ playback normalization). |
| 9 | Light night mode. Film + prestige TV get noticeable compression. |
| 7 | Aggressive night mode. Anything wider than typical broadcast TV gets compressed. |
| 5 | "Kids asleep, volume on 2" mode. Almost everything compressed flat. |

To change: `UPDATE SystemSettings SET Value = '<N>' WHERE SettingName
= 'MinimumLoudnessRangeLU'`. Next encode picks it up. To preview the
effect without re-encoding files already at AudioComplete=true,
`POST /api/AudioCompletion/Reset` for the relevant rows first.

### Triage SQL one-liner

The four-count Activity criterion (23) can be satisfied today via:

```sql
SELECT
    COUNT(*) FILTER (WHERE AdmissionDeferReason='awaiting_loudness_measurement') AS waiting,
    COUNT(*) FILTER (WHERE AdmissionDeferReason='loudness_measurement_failed')   AS failed,
    COUNT(*) FILTER (WHERE AudioNormalizationMode='linear')                       AS linear_mode,
    COUNT(*) FILTER (WHERE AudioNormalizationMode='dynamic')                      AS dynamic_mode
FROM MediaFiles;
```

A spike in `failed` means the ebur128 pipeline is broken for some
inputs -- check the worker log for the failure reason distribution:

```sql
SELECT LoudnessMeasurementFailureReason, COUNT(*)
FROM MediaFiles
WHERE LoudnessMeasurementFailureReason IS NOT NULL
GROUP BY 1 ORDER BY 2 DESC;
```

## Scope

```
Features/LoudnessAnalysis/linear-loudnorm.feature.md            -- (THIS FILE)
Features/LoudnessAnalysis/linear-loudnorm.flow.md               -- (NEW) loudnorm-application flow
Features/LoudnessAnalysis/LoudnessAnalysisService.py            -- ParseSummary + PersistLoudness extension
Models/CommandBuilder.py                                        -- BuildAudioFilters rewrite; acompressor removal
Features/TranscodeQueue/QueueManagementBusinessService.py       -- admission gate checks + AdmissionDeferReason write
Features/MediaProbe/MediaProbeBusinessService.py                -- probe co-trigger for loudness measurement
Features/Activity/*                                              -- two new deferral counts on Library Compliance
Scripts/SQLScripts/AddLoudnessThresholdColumn.py                -- (NEW) idempotent ADD COLUMN
Scripts/SQLScripts/AddAdmissionDeferReason.py                   -- (NEW) idempotent ADD COLUMN
Scripts/SQLScripts/AddMinimumLoudnessRangeSetting.py            -- (NEW) idempotent SystemSettings insert
Scripts/SQLScripts/DropAudioCompressionSettings.py              -- (NEW) idempotent settings cleanup
Scripts/SQLScripts/BackfillLoudnessThreshold.py                 -- (NEW) re-measure rows missing Threshold
Docs/AudioStrategy.md                                           -- Rule 2 reduced to pointer
Features/AudioCompletion/audio-completion.feature.md            -- loudnorm parameter references removed; pointer added
Features/AudioCompletion/audio-completion.flow.md               -- same
Features/TranscodeQueue/remux.flow.md                           -- Audio Filter Chain section reduced to pointer
Features/TranscodeQueue/media-tabs-and-loudness.feature.md      -- consumer-contract pointer added
Features/CommandBuilder/command-builder.feature.md              -- loudnorm criteria reduced to pointer
transcode.flow.md                                                -- Stage 5 note reduced to pointer
```

## Files

| File | Role |
|------|------|
| Feature doc (this file) | Contract |
| `linear-loudnorm.flow.md` | Pipeline shape |
| `Scripts/SQLScripts/AddLoudnessThresholdColumn.py` | Idempotent ADD COLUMN SourceIntegratedThresholdLufs |
| `Scripts/SQLScripts/AddAdmissionDeferReason.py` | Idempotent ADD COLUMN AdmissionDeferReason |
| `Scripts/SQLScripts/AddMinimumLoudnessRangeSetting.py` | Idempotent SystemSettings insert |
| `Scripts/SQLScripts/DropAudioCompressionSettings.py` | Idempotent cleanup of compressor SystemSettings rows |
| `Scripts/SQLScripts/BackfillLoudnessThreshold.py` | Re-measure rows where Threshold is NULL |
| `Features/LoudnessAnalysis/LoudnessAnalysisService.py` | ParseSummary extracts Threshold; PersistLoudness writes 4 cols |
| `Features/MediaProbe/MediaProbeBusinessService.py` | Trigger LoudnessAnalysis on probe completion |
| `Models/CommandBuilder.py` | BuildAudioFilters linear-only; raise on missing data; acompressor removed |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | Admission gate checks (measurements + predicted peak) |
| `Features/Activity/...` | Two new deferral counts on Library Compliance panel |

## Deviation from conventions

- **Removes existing SystemSettings rows.** Cleanup migration drops
  `AudioCompressionEnabled` and five `Compressor*` rows. This is a
  one-time destructive schema change, justified because retaining
  unused rows in a doc-driven settings UI would be misleading. Listed
  here for visibility; idempotent migration makes re-runs safe.
- **Removes `acompressor` entirely with no comeback path.** Linear
  mode is transparent by design; for files where range compression is
  the right answer (ungainable peak per criterion 10, or a future
  per-content "mild compression" use case), the mechanism is
  dynamic-mode loudnorm with a narrower target LRA -- the same
  single filter, driven by EBU R128 measurements rather than a static
  threshold. The compressor was duplicating loudnorm's own internal
  DSP with the wrong knobs. Listed here so a future reader does not
  re-introduce it as "the obvious way to add compression"; the
  obvious way is to lower `MinimumLoudnessRangeLU` (system-wide or
  via a per-profile / per-folder override added later) and let
  loudnorm's dynamic mode handle the compression in the same pass.
- **Source-of-truth consolidation deletes content from five docs.**
  This is at the user's explicit instruction ("we need to delete the
  old references. We can only have one source of truth.") and is
  itself a verifiable criterion (22). Listed so a future reviewer can
  trace the intent.
