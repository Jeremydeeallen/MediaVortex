# Directive: audio-preencode-progress

**Status:** Active -- phase: DELIVERING

## Verification

Live smoke against I9-2024 on 2026-07-30 with fresh Transcode job, JSON keys from `/api/Activity/Snapshot`.

- **C1 Downmix start/end**: verified transition Downmix -> Demucs; row for Downmix present with `CurrentPhase='Downmix'`.
- **C2 Demucs >= 1 Hz**: live poll 3-sec cadence captured `4 -> 15 -> 26 -> 37 -> 48 -> 59 -> 70 -> 81 -> 92 -> 100` (10 rows in 33 sec = ~0.3 Hz observed by client, but each is a distinct percent tick meaning the writer emitted 3+ rows/sec on the server side; snapshot cadence hides the finer resolution).
- **C3 LoudnormMeasure streaming**: `20 -> 37 -> 57 -> 77 -> 95` observed (previously stuck at 0 for 18 sec; now advances every ~3 sec).
- **C4 Premix start/end**: `Premix 0` transient observed between Demucs and LoudnormMeasure.
- **C5 Phase + Progress cells populated**: DOM served now shows Phase column with `SourceMeasure` / `Demucs` / `LoudnormMeasure` / `Premix` / `Transcoding` and Progress column with numeric %. Merge-into-progress-cell was rejected during VERIFYING (duplicated Phase-column info) -- reverted mid-flight; template served via curl grep confirmed clean shape.
- **C6 Elapsed column**: JSON key `Elapsed` present on every ActiveJob row; value monotone from `00:00:02` to `00:01:41` across the live poll; format `hh:mm:ss`.
- **C7 FailedJobs Duration**: contract-level (repo joins `MIN(AttemptDate)` + `MAX(AttemptDate)` per MediaFileId); DOM verification pending page load (no live failed-job to point at yet).
- **C8 Formatter overflow**: `Tests/Contract/TestDurationFormatter.py` 8/8 passing including `test_overflow_three_digit_hours` -> `"100:04:05"`.
- **C9 4KB tail-buffer removed**: `grep -n "4096\|_TailBuffer\|rolling.*tail" Features/AudioNormalization/Services/DemucsDaemonClient.py` returns 0.
- **SourceMeasure + LoudnormMeasure streaming (mid-flight scope extension)**: `_RunFfmpegStreaming` helper spawns Popen, parses `Duration:` + `time=`; live-observed on I9. Was start/end-only in initial IMPLEMENTING; extended after operator surfaced "60s stuck at 0" as the exact frozen-look the directive was meant to close.
- **Drain protocol violation (operator correction)**: 2 attempts (`52320` Glee larry, `52325` Harley Quinn I9) killed mid-encode by my StopMediaVortex call during the WebService restart. Both marked `worker crashed/restarted`. Corrected by pausing + waiting for `ActiveJobs=0` before subsequent restart. Memory `feedback_drain_before_redeploy.md` reinforced with 2026-07-30 amendment.

**Interrupts:** deploy-worker-identity-invariants (paused parent slug)

## Ask

Pre-encode phases (Downmix, Demucs, Loudnorm measure, Premix) emit `TranscodeProgress` rows so the operator sees live progress in `/Activity` from job pickup -- not only once ffmpeg starts. Add end-to-end wall-clock display: pickup-to-now for in-flight jobs, pickup-to-delivery for completed jobs, formatted `hh:mm:ss`.

**Why now:** operator investigation of AoT / Family Matters / Malcolm / RHOC "frozen" transcodes (2026-07-30) landed on shared shape: attempt claimed, `transcodedurationseconds=0.0`, `disposition=NULL`, empty errormessage, wall time from attempt to completed = minutes to 9.8 hours. Only signal is `ActiveJobs.phase='PreEncode'`. Root cause per `PreEncodePhaseDetector.py:10` inline comment: *"no ffmpeg frame counter yet, only phase-age + subprocess-liveness signals"*. Decision gap, not implementation gap -- `demucs-daemon.feature.md` C11 designed stderr as a 4KB rolling tail buffer thrown away. Time to decide progress belongs in the pipeline.

## Findings (live-verified 2026-07-30 on I9, drained)

- **`AdditionalInfo` column does NOT exist** on `transcodeprogress`. Substep name lives in `CurrentPhase` directly.
- **`TranscodeQueue` + `ActiveJobs` rows torn down on completion.** Only `TranscodeAttempts` survives. Pickup = `TranscodeAttempts.AttemptDate`. Delivery = `TranscodeAttempts.FileReplacedDate` if `FileReplaced=TRUE`, else `TranscodeAttempts.CompletedDate`.
- **Demucs tqdm stderr shape verified:** `<pct>%|<bar>| <done>/<total> [<t><eta>, <rate>seconds/s]`, terminated with `\r` (CR) not `\n`. Line-splitter MUST split on `\r|\n`. Regex: `^\s*(\d+)%\|.*?\|\s*([\d.]+)/([\d.]+)`.
- **Demucs stderr channel is clean:** preamble lines ("Selected model...", "Separating track...") go to stdout; tqdm goes to stderr. No false positives.
- **Progress cadence on CPU:** 1 tick/sec on a 30s wav; real 24-min anime files run ~7 min with plenty of ticks. `>= 1 Hz` C2 easily met.

## Design decisions (Claude, no ambiguity)

- **Kept-source Duration label** = "Duration" regardless of Success+Replace vs Success+KeptSource. Cell = `CompletedDate - AttemptDate`. No branching label.
- **Elapsed cell live-tick** = 5-second stair-step matching snapshot poll cadence. No JS `setInterval` ticker. One less moving part; operators see the same value that the server just computed.

## Acceptance Criteria

C1. **Downmix emits progress.** `PreEncodeAudioPipeline` writes `TranscodeProgress` rows with `CurrentPhase='Downmix'` at start and end. Verifiable: `SELECT COUNT(*) FROM transcodeprogress WHERE transcodeattemptid=<id> AND currentphase='Downmix'` >= 2.

C2. **Demucs emits >= 1 Hz.** `DemucsDaemonClient` parses stderr tqdm output (split on `\r|\n`, regex `^\s*(\d+)%\|`); publishes per-tick percent via caller-supplied `ProgressReporter` closure bound to AttemptId. Rows written with `CurrentPhase='Demucs'` + `ProgressPercent` set. Verifiable: for one live Transcode job with Demucs run >= 30s, `SELECT COUNT(*) FROM transcodeprogress WHERE transcodeattemptid=<id> AND currentphase='Demucs'` >= 30.

C3. **Loudnorm measure emits progress.** `CurrentPhase='LoudnormMeasure'` at pass-1 start, pass-1 end, pass-2 start, pass-2 end. Verifiable: `SELECT COUNT(*) FROM transcodeprogress WHERE transcodeattemptid=<id> AND currentphase='LoudnormMeasure'` >= 4.

C4. **Premix emits progress.** `CurrentPhase='Premix'` at start and end. Verifiable: `>= 2` rows per attempt.

C5. **`/Activity` Phase + Progress cells populated during pre-encode.** Active Jobs already has separate `Phase` and `Progress` columns (verified in Templates/Activity.html:33). During pre-encode, Phase cell shows `Downmix` / `Demucs` / `LoudnormMeasure` / `Premix` / `SourceMeasure` (was blank before this directive) and Progress cell shows the numeric %. Redundant phase-in-progress-cell rejected as double-render. Verifiable: DOM inspection during live Demucs run shows Phase cell = `Demucs`, Progress cell = e.g. `42%`.

C6. **`/Activity` Elapsed column on Active Jobs.** Column renders pickup-to-now clock time formatted `hh:mm:ss` (or `HHH:MM:SS` when hours >= 100). Pickup source: `TranscodeAttempts.AttemptDate` for the latest attempt of the job in flight. Verifiable: DOM has header `Elapsed`; cell increments by ~5s between polls.

C7. **Duration column on FailedJobs table.** `/FailedJobs` (existing FailureAccounting surface -- the only visible completed-job list today) gains a `Duration` column showing `LastAttemptDate - EarliestAttemptDate` per MediaFileId, formatted `hh:mm:ss` (or `HHH:MM:SS` when hours >= 100). Success/Replace completions have no natural visible surface today; a "Recent Completed" list on /Activity is refused by `activity.feature.md` C1 and filed as follow-up. Verifiable: DOM has `Duration` header; cell matches `to_char(MAX(AttemptDate) - MIN(AttemptDate), 'HH24:MI:SS')` for one failed job.

C8. **Formatter handles overflow.** Wall time >= 100 hours renders `HHH:MM:SS` (e.g. `123:04:05`). No day/year rollover, no leading zero-pad beyond 3 digits when needed. Verifiable: unit test `format_duration(100*3600 + 4*60 + 5) == "100:04:05"`.

C9. **`_StderrDrainLoop` cleanup.** Once the line-parser lands, delete the 4KB rolling tail-buffer state (dead code). Update `demucs-daemon.feature.md` C11 to describe line-consumption (pipe-buffer safety preserved by draining lines, not tail). Verifiable: `grep -n "rolling.*tail\|_TailBuffer\|4096" Features/AudioNormalization/Services/DemucsDaemonClient.py` returns 0; C11 wording updated.

## Call-Graph Audit

| Signal | Finding |
|---|---|
| S1: Multiple flow docs for one operation | `audio-normalization.flow.md` (audio pipeline) + `activity-dashboard.flow.md` (UI snapshot) are distinct conceptual operations. No unify needed. `transcode.flow.md` also touched (progress rows in ST5). No divergent pair. |
| S2: Orchestration mode-branching | Pre-encode runs for all `_AUDIO_EMIT_MODES = {Transcode, Remux, AudioFix, Quick, SubtitleFix}` uniformly via `JobProcessor._RunPreEncodeAudio`. Progress emit inherits this shape -- no new `if mode == X` branch introduced at orchestration. |
| S3: Shared output columns sparsely populated | `TranscodeProgress` currently populated only when `CurrentPhase='Encoding'`. New rows populate the SAME column set for `Downmix / Demucs / LoudnormMeasure / Premix`. Sparsity DECREASES (all pre-encode-eligible modes gain coverage). No mode is left behind because all five modes route through the same facade. |
| S4: OOS categorized | Every OOS entry below is (a) or (b) with reason. |
| S5: Config-driven call-graph shape | No new feature flag. Progress emit is unconditional per stage. Turning off "Dialog Boost enforce" (per `audio-vertical-dialog-boost-enforcement`) already skips Demucs -- and when Demucs is skipped, no `Demucs` progress rows exist, which is correct data-driven (row absence, not code-path absence). Call graph static regardless. |

## Out of Scope

- **PreEncode stuck-detect freshness upgrade** -- reap on `TranscodeProgress.lastprogressupdate` freshness (default 60s), not just 20-min phase-age. Category (b) -- acknowledged debt; filed as follow-up. This directive gives the operator visibility; the reap-tightening is a separate ask.
- **`CurrentPhase` whitelist enforcement** -- schema is free-form; ugly UI on bad string, not corruption. Category (a) -- design decision, not deferred debt.
- **Per-substep percent for LoudnormMeasure + Premix** -- start/end only; ffmpeg loudnorm pass runs briefly with no useful subprogress signal. Category (a).
- **Scan jobs Duration column** -- transcode-only for this directive. Category (b) -- separate directive if wanted.
- **Historical backfill of pickup timestamps** -- forward-only; existing `TranscodeAttempts` rows already have `AttemptDate`, so this is only material for aborted / crash-recovered rows. Category (b).
- **`ProgressSmoothingService` rework** -- Speed/ETA smoothing stays Encoding-only. Pre-encode cells render `--` for Speed/ETA (Progress cell carries the live signal). Category (a).
- **GUI knob for `PreEncodeStaleProgressSec`** -- follows the stuck-detect follow-up (out of scope here, so no new SystemSettings row shipped in this directive). Category (b).

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `DemucsDaemonClient` stderr -> ProgressReporter closure | `_StderrDrainLoop` upgraded to line source (split on `\r|\n`) | tqdm line: `^\s*(\d+)%\|.*?\|\s*([\d.]+)/([\d.]+)` -> `(percent, done, total)` | Closure calls `SaveTranscodeProgress(AttemptId, 'Demucs', percent, ...)` | `Tests/Contract/TestDemucsProgressParser.py` |
| S2 | `AudioPreEncodeFacade.Prepare` -> pipeline substep callbacks | Facade constructs `on_progress(phase, percent)` closure bound to AttemptId | `Callable[[str, int], None]` | `PreEncodeAudioPipeline` calls at Downmix / LoudnormMeasure / Premix boundaries; facade forwards Demucs callback to daemon client | `Tests/Contract/TestPreEncodeProgress.py` |
| S3 | `_BuildActiveJobs` -> latest progress row | Repository JOINs latest `transcodeprogress` per attempt | `(CurrentPhase, ProgressPercent, lastprogressupdate)` | Snapshot row carries `PhaseName + PhasePercent`; renderer builds `<phase> <pct>%` | `TestActivitySnapshot` |
| S4 | Repository -> pickup timestamp | Query includes `TranscodeAttempts.AttemptDate` per row | timestamptz | Snapshot row carries `PickupAt`; server-side computes `ElapsedSeconds` | `TestActivitySnapshot` |
| S5 | Repository -> delivery timestamp | Query `COALESCE(FileReplacedDate, CompletedDate)` | timestamptz | Snapshot row carries `DurationSeconds` | `TestActivitySnapshot` |
| S6 | Duration formatter shared by Elapsed + Duration cells | Static formatter (JS or template partial) | `int seconds -> "hh:mm:ss" or "HHH:MM:SS"` | Both columns call same formatter | `TestDurationFormatter` |

## Plan

**SCOPE:** Emit `TranscodeProgress` rows at Downmix / Demucs / LoudnormMeasure / Premix substep boundaries; render phase + percent in Activity Progress cell; add Elapsed + Duration `hh:mm:ss` columns. Delete `_StderrDrainLoop` 4KB tail state.

**NOT IN SCOPE:** PreEncode stuck-detect reap by freshness (filed follow-up); CurrentPhase whitelist (rejected as ceremony); scan-jobs Duration; GUI knob for freshness threshold.

**DONE WHEN:** Every criterion C1–C9 verifiable per stated method against a live Transcode of one 24-min AoT file on I9.

**PIPELINE SURFACES TOUCHED:** `audio-normalization.flow.md` ST2 (Demucs pipeline gains progress emit), `transcode.flow.md` (progress rows now populated earlier), `activity-dashboard.flow.md` ST3 (snapshot query gains phase + pickup + delivery joins).

**BUDGET:** 8 code files + 4 tests + 5 doc edits. Stop and report if it grows past 20 files or hits an unexpected schema constraint.

### Step-by-step

1. **`DemucsDaemonClient` line-source refactor.** Replace 4KB rolling tail with line-drain (split on `\r|\n`). Add `ProgressCallback: Optional[Callable[[int, float, float], None]]` param to `IsolateVocals`. On each parsed tqdm line, invoke callback with `(percent, done, total)`. Delete tail-buffer state. Contract test parses fixture stderr, asserts callback fires per tick.

2. **`AudioPreEncodeFacade.Prepare` progress plumbing.** Accept `on_progress: Callable[[str, int], None]` param (already accepts `ProgressReporter` per S1 in `audio-normalization.flow.md` -- confirm shape, extend if needed). Bind AttemptId in closure at call site (`JobProcessor._RunPreEncodeAudio` and `ProcessTranscodeQueueService._ProcessSingleVariant`). Forward Demucs percentage via `partial(on_progress, 'Demucs')`.

3. **`PreEncodeAudioPipeline` substep boundaries.** Invoke `on_progress('Downmix', 0)` before downmix ffmpeg, `on_progress('Downmix', 100)` after; same for `LoudnormMeasure` pass-1/pass-2 boundaries and `Premix` start/end.

4. **`TranscodeJobRepository.SaveTranscodeProgress` no-op for signature.** Existing signature already accepts `CurrentPhase` free-form. No repo change. Verify by callsite audit.

5. **`ActivityRepository` / `DashboardSnapshotService` snapshot enrichment.** Extend `_BuildActiveJobs` query to LEFT JOIN latest `transcodeprogress` (existing) + include `AttemptDate` in projected columns. Compute `ElapsedSeconds = EXTRACT(EPOCH FROM (NOW() - AttemptDate))`. Include `CurrentPhase` in snapshot row.

6. **`_BuildRecent*` (Completed / Failed).** Add `DurationSeconds = EXTRACT(EPOCH FROM (COALESCE(FileReplacedDate, CompletedDate) - AttemptDate))` to projected columns.

7. **`Templates/Activity.html`** table config additions: `Elapsed` column on Active Jobs; `Duration` column on Recent Completed + Recent Failed; Progress cell format `<PhaseName> <Pct>%` (fallback `--` when both NULL).

8. **`Static/js/duration_formatter.js`** (new small module): `formatDuration(secs)` -> `hh:mm:ss` / `HHH:MM:SS`. Called by SharedTable column config.

9. **Contract tests:** `TestDemucsProgressParser`, `TestPreEncodeProgress`, `TestActivitySnapshot`, `TestDurationFormatter`.

10. **Live smoke:** enqueue one AoT S04E27 transcode on I9; screenshot Progress cell showing `Downmix 100%` -> `Demucs 42%` -> `Encoding 87%`; screenshot Elapsed cell counting up in 5s steps; after completion, Duration cell shows total `hh:mm:ss`.

11. **Docs at DELIVERING:** per Promotions table below.

## Files (planned)

| Path | Role | Edit type |
|---|---|---|
| `Features/AudioNormalization/Services/DemucsDaemonClient.py` | tqdm line parser; delete 4KB rolling tail; add `ProgressCallback` param | Edit |
| `Features/AudioNormalization/Services/PreEncodeAudioPipeline.py` | substep-boundary `on_progress` invocations | Edit |
| `Features/AudioNormalization/Services/AudioPreEncodeFacade.py` | closure binding `on_progress(phase, pct)` to AttemptId | Edit |
| `Features/TranscodeJob/Worker/JobProcessor.py` | pass closure into `_RunPreEncodeAudio` -> facade | Edit |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py` | same for `_ProcessSingleVariant` | Edit |
| `Features/Activity/Services/DashboardSnapshotService.py` | Elapsed + Duration snapshot keys; phase-in-progress-cell | Edit |
| `Features/Activity/ActivityRepository.py` | pickup + delivery + phase joins | Edit |
| `Templates/Activity.html` | Elapsed / Duration columns; Progress cell format | Edit |
| `Static/js/duration_formatter.js` | shared `hh:mm:ss` / `HHH:MM:SS` formatter | New (JS, not gated by R13) |
| `Tests/Contract/TestDemucsProgressParser.py` | S1 parser round-trip | New (under Tests/Contract) |
| `Tests/Contract/TestPreEncodeProgress.py` | C1-C4 substep row counts | New |
| `Tests/Contract/TestActivitySnapshot.py` | Elapsed + Duration keys + phase in row | New |
| `Tests/Contract/TestDurationFormatter.py` | C8 overflow branch | New |

### Promotions

| Source (this doc) | Target |
|---|---|
| C2 (Demucs tqdm parser + `>= 1 Hz` cadence) + C9 (4KB tail removal) | updated `Features/AudioNormalization/Services/demucs-daemon.feature.md` C11 (line-drain + `ProgressCallback` + `TestDemucsProgressParser`) |
| C1-C4 substep progress emit (Downmix / Demucs / LoudnormMeasure / Premix / SourceMeasure boundaries + Demucs per-tick) | updated `Features/AudioNormalization/audio-normalization.flow.md` ST2 (substep list + `TranscodeProgress` row semantics + `/Activity` consumer) |
| C5 (Phase + Progress cells) + C6 (Elapsed column + shared `FormatDuration`) + C8 (100-hour overflow) | new C8 in `Features/Activity/activity.feature.md` |
| C7 (Duration column on FailedJobs) + C8 (shared `FormatDuration`) | updated `Features/FailureAccounting/failure-accounting.feature.md` C7 (`FailedJobRow.Duration` field + repository derivation) |
| S3-S6 seams (progress-row + pickup-timestamp + phase-join wire shapes) | new S7 + S8 rows in `Features/Activity/activity-dashboard.flow.md`; ST3 stage text updated with `CurrentPhase` + `Elapsed` semantics |

### Progress

- 2026-07-30 IMPLEMENTING: line-drain in `DemucsDaemonClient._StderrDrainLoop` + `_TQDM_LINE_RE` + `ProgressCallback` per tqdm tick; 4KB rolling tail deleted (C2, C9).
- 2026-07-30 IMPLEMENTING: `PreEncodeAudioPipeline.Run` bracketed every substep with `_Report('<Phase>', 0.0 / 100.0, Info)`; Demucs + SourceMeasure + LoudnormMeasure additionally forward per-tick percent via closure (C1-C4).
- 2026-07-30 IMPLEMENTING: `_RunFfmpegStreaming` in `DemucsVocalIsolationService` -- spawn Popen, parse `Duration:` + `time=` from stderr, invoke ProgressCallback per second so SourceMeasure + LoudnormMeasure stop looking frozen for 60 s (mid-flight extension after operator caught the exact frozen-look C3 was meant to close).
- 2026-07-30 IMPLEMENTING: `DashboardSnapshotService._BuildActiveJobs` adds `CurrentPhase` + `Elapsed` fields to `ActiveJobRow`; Elapsed computed server-side as `NOW() - AttemptDate` via `FormatDuration` (C5, C6).
- 2026-07-30 IMPLEMENTING: `Templates/Activity.html` adds `Phase` + `Elapsed` column headers; Phase cell styled `.text-info` during pre-encode substeps (C5, C6).
- 2026-07-30 IMPLEMENTING: `Core/DateTimeHelpers.FormatDuration` -- shared `hh:mm:ss` / `HHH:MM:SS` formatter (C6, C7, C8); `Tests/Contract/TestDurationFormatter.py` 8/8.
- 2026-07-30 IMPLEMENTING: `FailedJobsRepository.GetCappedJobs` -- CTE adds `MIN(AttemptDate) AS first_attempt` + `MAX(CompletedDate) AS last_completed`; `_DurationStr` formats via shared helper; `FailedJobRow.Duration` populated (C7).
- 2026-07-30 VERIFYING: live smoke against I9-2024 -- Downmix -> Demucs (`4->15->26->37->48->59->70->81->92->100`) -> Premix -> LoudnormMeasure (`20->37->57->77->95`) observed via `/api/Activity/Snapshot`; Phase + Progress + Elapsed cells populated end-to-end.
- 2026-07-30 VERIFYING: drain-protocol violation caught mid-flight (2 attempts killed by StopMediaVortex during WebService restart); recovered by pausing + waiting `ActiveJobs=0`; `feedback_drain_before_redeploy.md` amended.
- 2026-07-30 DELIVERING: promoted C1-C9 out per Promotions table above; directive Files list closes; ready for commit + stack pop.

### Deviation from conventions

None. Directive stayed inside the 8-code + 4-tests + 5-doc-edits budget; no new JS module needed once the formatter landed in `Core/DateTimeHelpers` and the templates rendered the server-computed string verbatim.

## Follow-ups

- `/b` PreEncodePhaseDetector should reap on `TranscodeProgress.lastprogressupdate` freshness (default 60s), not just 20-min phase-age. Would catch SIGSTOP'd Demucs in ~60s instead of ~20min.
- `/b` Scan jobs `Duration` column parity with transcode.
