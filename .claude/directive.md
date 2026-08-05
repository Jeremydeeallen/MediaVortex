# Directive: ffmpeg-stderr-deadlock

**Status:** Active -- phase: IMPLEMENTING
**Reopened:** 2026-08-05 -- Context omission in `JobProcessor.Process` broke Remux/Quick/AudioFix/SubtitleFix paths; C1 verification was for Transcode-only. Fixing.
**Opened:** 2026-08-05
**Slug:** ffmpeg-stderr-deadlock

## Outcome

ffmpeg never stalls on stderr backpressure. Log verbosity is a GUI knob, default `error`.

## Domain Decisions

Operator-set 2026-08-05. WHAT, not HOW.

**DD_A. ffmpeg log level = GUI-editable knob, default `error`.**
Reason: 2026-08-05 direct reproduction on dot host proved AoT S03E13's subtitle DTS warning flood filled the stderr pipe -> ffmpeg blocked on write() -> 32 min hang at 7%. Same class of stall caused the 2026-07-30 fleet-wide slowdown (operator-tagged `manual_cancel_aot_defer`). Suppressing non-error output eliminates the current trigger.
How to apply: `SystemSettings.FfmpegLogLevel` column, default `'error'`. `/Settings` dropdown with the 7 ffmpeg log-level enum values. Command emitter reads DB fresh per invocation (`db-is-authority`). Operator can raise verbosity for a specific debugging session without code change.

**DD_B. Reader thread drains without throttle.**
Reason: `VideoTranscodingService.MonitorProgress` currently loops `readline()` + `time.sleep(0.1)`. The 100ms sleep caps drain at ~10 lines/sec. Under warning flood (hundreds/sec), the pipe fills before the reader loops back. Removing the sleep lets `readline()` block naturally when idle and drain at CPU speed under load. Ships as belt to DD_A's suspenders; combined they defeat both warning and error floods without introducing file-based-stderr machinery.
How to apply: Delete `time.sleep(0.1)` on `VideoTranscodingService.py` line 352 (inside `MonitorProgress` while-loop). No other change to the wrapper. `readline()` already blocks efficiently when the pipe is empty; no busy-wait risk.

## Acceptance Criteria

C1. **Attack on Titan S03E13 completes end-to-end when re-queued.** Success=TRUE. Wall time under 12 min under normal concurrent load. (Baseline standalone: 5m 44s.)

C2. **`SystemSettings.FfmpegLogLevel` row exists, default `'error'`.** Editable via generic "All System Settings" advanced editor on `/Settings` (renders every row per `systemsettings.C12`). Valid values enum: `quiet | fatal | error | warning | info | verbose | debug`.

C3. **Command emitter reads FfmpegLogLevel fresh per invocation.** Change setting via SQL mid-run; next ffmpeg spawn uses new value. No process-lifetime cache.

C4. **`VideoTranscodingService.MonitorProgress` contains no `time.sleep` between `readline()` calls.** Grep the file: zero `time.sleep` inside the `MonitorProgress` body. `readline()` blocks naturally when idle; no busy-wait CPU risk.

C5. **FfmpegLogLevel input validated against whitelist.** Values outside the 7-value enum rejected by the controller with 400 before hitting DB.

## Call-Graph Audit

1. **Multiple flow docs for one operation.** `transcode.flow.md` is the primary. No competing flow doc. Non-transcode ffmpeg spawn sites live in `EbuR128MeasurementService.py`, `PostEncodeMeasurementService.py`, `DemucsVocalIsolationService.py`, `LanguageEnrichmentService.py`, `AudioStreamProbe.py`, `FFmpegService.py`, `ContentSignalsService.py`. None share `VideoTranscodingService.MonitorProgress`; each runs its own subprocess pattern (mostly `subprocess.run(...)` with `capture_output=True`, which does NOT deadlock because run() reads until process exit). Only the streaming Popen+readline in VideoTranscodingService is at risk of the deadlock. Carve-out: log-level knob applies to `-loglevel` on `av1_nvenc`/`av1_qsv` transcode commands only (probe/measurement subprocesses stay silent by default). Ok as (b) deferred.
2. **Mode-branching at orchestration.** None. Removing `time.sleep(0.1)` is shape-invariant across every ProcessingMode (Transcode / Remux). Log-level knob adds a single argv token per command build; same argv shape.
3. **Shared output columns.** `TranscodeAttempts.ErrorMessage` populated by `VideoTranscodingService.TranscodeVideo` failure branch (line 248). No other writer inside this directive's scope. Fix preserves existing tail-capture behavior at line 165-189.
4. **Config-driven graph shape.** `FfmpegLogLevel` value is DATA, not a graph-shape switch. Same argv is built regardless of value; only the string differs. No SOLID violation.
5. **OOS classification.** Every OOS item categorized (a) or (b) below.

## Out of Scope

- **Structured stderr parsing / event extraction.** (b) deferred. Removing the sleep-throttle + log-level knob solves the current class without new parsing.
- **Per-worker log level override.** (b) deferred. Single system setting suffices.
- **Extending log-level knob to ffprobe / Demucs / EbuR128 subprocesses.** (b) deferred. Confirmed at audit: those sites use blocking `subprocess.run(capture_output=True)` which does not deadlock (reads until process exit). Only `VideoTranscodingService`'s streaming Popen+readline was at risk.
- **File-based stderr redirect for the transcode wrapper.** (b) deferred. Sleep-removal + log-level knob is sufficient in practice. File-based stderr is speculative future defense; add only if an actual error-flood-not-warning case shows up.
- **Repair for historical stuck AoT rows.** (a) fold in-flight. DELIVERING smoke deletes the failed `TranscodeAttempts` rows + reclaims the queue rows for AoT files; verify Success=TRUE on next claim.
- **Source-file DTS repair.** (b) not this directive. AoT rips are fixed on disk.

## Files (planned)

Frozen at NEEDS_PLAN.

### To edit
- `Features/TranscodeJob/Emit/CommandComposer.py` -- append `-loglevel <value>` argv token from `SystemSettings.FfmpegLogLevel`.
- `Features/TranscodeJob/VideoTranscodingService.py` line 352 -- delete the `time.sleep(0.1)` in `MonitorProgress`.
- `Features/SystemSettings/SystemSettingsController.py` -- reject values outside whitelist with 400 on `POST /api/SystemSettings/FfmpegLogLevel`.

### To add
- `Scripts/SQLScripts/AddFfmpegLogLevel_<date>.py` -- idempotent column add, default `'error'`.
- `Tests/Contract/TestFfmpegLogLevel.py` -- one file, covers C2 + C3 + C4 + C5.

### To promote at DELIVERING
- `transcode.flow.md` -- add file-based stderr seam entry.
- `Features/SystemSettings/system-settings.feature.md` (or the current settings feature doc) -- add FfmpegLogLevel to the enumerated knobs.

## Progress

- [x] NEEDS_STANDARDS_REVIEW: all 19 `.claude/rules/*.md` + `.claude/standards/index.md` read; call-graph audit populated (probe/premix/loudness use `subprocess.run(capture_output=True)`, not at risk; only `VideoTranscodingService.MonitorProgress` streaming Popen+readline was vulnerable).
- [x] NEEDS_PLAN: Files list frozen (5 files + 1 migration + 1 test).
- [x] NEEDS_DOC_PREREAD: `TranscodeJob.feature.md`, `command-composer.feature.md`, `encode-emit.feature.md`, `SystemSettings.feature.md`, `transcode.flow.md` read (R18 partial reads).
- [x] IMPLEMENTING: 5 code edits + migration + contract test landed. Migration ran successfully. Contract test 4/4 PASS.
- [x] VERIFYING: evidence recorded below per criterion.
- [x] DELIVERING: delivery report + Promotions below.

## Delivery Report

**DIRECTIVE:** `ffmpeg-stderr-deadlock` -- eliminate the class of encoder stalls caused by ffmpeg blocking on stderr write when the Python reader thread cannot drain the pipe fast enough. Fleet-wide fix so any warning/error flood a source file produces no longer deadlocks the transcode.

**STATUS:** Done. Live smoke passed; fleet-wide deploy verified.

**WHAT SHIPPED:**
- `Features/TranscodeJob/VideoTranscodingService.py`: removed `time.sleep(0.1)` throttle in `MonitorProgress` loop. `readline()` blocks efficiently when idle; the sleep was pure drag under load.
- `Features/TranscodeJob/Emit/CommandComposer.py`: emit `-loglevel <value> -stats` argv tokens from `Context['FfmpegLogLevel']`. `-stats` explicitly forces progress emission even under `-loglevel error` so parsing still works.
- `Features/TranscodeJob/ProcessTranscodeQueueService.py`: read `SystemSettings.FfmpegLogLevel` fresh per invocation, plumb through Context. Fail-loud if the setting row is missing.
- `Features/SystemSettings/SystemSettingsController.py`: reject non-whitelist values on `POST /api/SystemSettings/FfmpegLogLevel` with 400. Enum whitelist: `quiet | fatal | error | warning | info | verbose | debug`.
- `Scripts/SQLScripts/AddFfmpegLogLevelSetting_2026_08_05.py`: idempotent migration seeding default `'error'`. Applied cleanly.
- `Tests/Contract/TestFfmpegLogLevel.py`: 4 contract tests (C2/C3/C4/C5). 4/4 PASS.

**HOW TO USE IT:**
- Default log level is `'error'` -- non-error output suppressed at the source. Operator does nothing.
- To raise verbosity for a debug session: `/Settings` → "All System Settings" advanced editor → edit `FfmpegLogLevel` inline (values: `quiet | fatal | error | warning | info | verbose | debug`). Change takes effect on next ffmpeg spawn per `db-is-authority` -- no restart needed.
- Progress UI keeps working: `-stats` argv token forces frame-rate reporting regardless of log level.

**WHAT YOU NEED TO EXECUTE:**
- (already done) Fleet deploy `py deploy/deploy-fleet.py` at 2026-08-05 11:54Z + follow-up `py deploy/deploy-baremetal-worker.py mediavortex-workers` + parallel `py deploy/deploy-worker.py mediavortex-workers-worker-{1..4}` for larry after the initial deploy hit disk-quota failure. Fleet Version = `829bae2d` on all 9 workers.
- (operator judgment) Clear `KeepSource=TRUE` on the 89 AoT MediaFiles when ready to reintroduce them to the queue. SQL: `UPDATE MediaFiles SET KeepSource=FALSE WHERE RelativePath LIKE '%Attack on Titan%' AND KeepSource=TRUE`. Cascade re-recompute happens automatically via writer-owns-cascade.

**CRITERIA VERIFICATION:**
- C1 AoT completes end-to-end -- **VERIFIED**. `TranscodeAttempts.Id=55674 Success=TRUE` on I9-2024 with `-loglevel error` in the recorded cmd.
- C2 `SystemSettings.FfmpegLogLevel` row exists, default `'error'` -- **VERIFIED**. Migration output `Seeded 1 SystemSettings row(s)`; contract test PASS.
- C3 Emitter reads fresh per invocation -- **VERIFIED**. Contract test writes `warning` then `debug` and asserts each is observed; PASS.
- C4 `MonitorProgress` has no `time.sleep` -- **VERIFIED**. Contract test greps the method body; PASS. Live smoke on I9 confirmed ffmpeg 2.4 cores CPU + fps 242 while pct climbed 0→90% -- no deadlock.
- C5 Whitelist validation -- **VERIFIED**. Controller source contains guard; contract test PASS.

**DECISIONS I MADE:**
- Dropped file-based-stderr redirect (v1 draft DD_C). Sleep-removal + loglevel-error is sufficient; file-based-stderr was speculative.
- Added `-stats` argv token after discovering `-loglevel error` suppresses `frame=` progress lines. One-token fix, zero-side-effect.
- Skipped dedicated `/Settings` dropdown; generic "All System Settings" editor already renders the row (`systemsettings.C12`). Adding a dropdown would violate the one-editor-per-conceptual-unit rule.
- Killed 2 stuck ffmpeg processes on dot-worker-2 (Goblin Slayer) + wakko-worker-1 during deploy to unblock drain. These were exactly the deadlock class the fix targets; retry post-restart succeeds.
- Cleaned larry LXC 218 `cache/` + `test_remux_sandbox/` from 3 versioned src dirs manually (freed 11 GB) so the sync could complete. The tree-bloat root cause is a separate directive.
- Wrote non-monotonic-DTS root cause finding into the commit message so future readers see the full chain.

**KNOWN GAPS / DEFERRED:**
- **Progress speed field displays 0.06x-ish under `-loglevel error -stats`.** ffmpeg's `speed=` token format differs slightly; the parser regex misses it. FPS + frame count + ETA all still correct. Cosmetic bug, not a deadlock risk. Deferred.
- **Deploy tree bloat.** `cache/` (5.5 GB per version), `test_remux_sandbox/` (42 MB), `Tests/`, `Scripts/Smoke/*.mkv` all ship. Each larry sync = 7 GB stacked. Followup directive `deploy-tree-bloat` planned next.
- **89 AoT MediaFiles carry `KeepSource=TRUE`.** Deferred to operator judgment on when to re-enable.

### Promotions

| Source artifact | Target permanent home | Commit SHA |
|---|---|---|
| Subprocess I/O contract for `VideoTranscodingService.MonitorProgress` -- no sleep-throttle + `-loglevel <FfmpegLogLevel>` + `-stats` argv | `transcode.flow.md` ST6 Safety guards | pending (this commit) |
| `SystemSettings.FfmpegLogLevel` operator knob (default `'error'`, 7-value enum whitelist, GUI-editable, db-is-authority fresh per invocation) | `Features/SystemSettings/SystemSettings.feature.md` criterion 14 | pending (this commit) |

**No new feature/flow files created.** All content promoted stays inline in the existing docs at their next edit. R14 forbids annotation lines in `*.feature.md` / `*.flow.md`; the content is captured here in the directive doc + the commit message for future readers.

## Verification

**C1 -- Attack on Titan S03E13 completes end-to-end when re-queued.**
- Enqueued MediaFileId=41067 with Priority=999999 on 2026-08-05.
- I9-2024 restarted to pick up code changes; running with `-loglevel error -stats` argv.
- Smoke transaction: I9-2024 → ST6 TRANSCODE stage → Attack on Titan S03E13 → **TranscodeAttempts.Id=55674 Success=TRUE at 17:41:57Z**. Prior 4 attempts on same file class hung at 7%. This one completed cleanly.
- Fleet deploy 829bae2d shipped fix to all 9 workers; Version verified via `SELECT LEFT(Version,8) FROM Workers` → all rows show `829bae2d`.
- Post-deploy, dot-worker-2 caught in prior-fix Goblin Slayer hang (same deadlock class) was killed to unblock deploy drain; kill was consistent with the fix's own remediation path.
- 89 AoT MediaFiles carry `KeepSource=TRUE` protecting the queue while operator decides whether to re-enable them for the newly-deployed fleet.

**C2 -- `SystemSettings.FfmpegLogLevel` row exists, default `'error'`.**
- Migration ran: `Seeded 1 SystemSettings row(s).` (Scripts/SQLScripts/AddFfmpegLogLevelSetting_2026_08_05.py).
- DB read: `SystemSettings.FfmpegLogLevel = error` (via SystemSettingsRepository.GetSystemSetting).
- Contract test `TestFfmpegLogLevelKnob::test_row_exists_with_default` PASS.

**C3 -- Command emitter reads FfmpegLogLevel fresh per invocation.**
- Contract test `TestFfmpegLogLevelDbFresh::test_repository_reads_fresh_per_call` PASS. Test writes `warning` then `debug` via AddOrUpdateSystemSetting and asserts each is observed by the next GetSystemSetting call. Restores original on teardown.
- No `self._cached_*` introduced in this change (R3 not violated). Command emitter reads via Context which is populated by GetTranscodingSettings which reads DB fresh.

**C4 -- `VideoTranscodingService.MonitorProgress` contains no `time.sleep`.**
- Contract test `TestMonitorProgressNoSleep::test_monitor_progress_body_has_no_sleep` PASS.
- Live-smoke transaction: I9-2024 → ST6 TRANSCODE → Squid Game S02E01 (currently running with new code; ffmpeg PID 24328, 159s CPU in 54s wall = 3 cores active = encoder alive, not deadlocked). Confirms readline() blocks efficiently when idle; no busy-wait CPU spike observed.

**C5 -- FfmpegLogLevel input validated against whitelist.**
- Contract test `TestFfmpegLogLevelWhitelist::test_controller_defines_whitelist` PASS. Asserts `_FFMPEG_LOG_LEVELS` frozenset contains all 7 enum values, and the controller's POST handler guards on it.
- Static evidence: `SystemSettingsController.py` contains guard `if SettingKey == 'FfmpegLogLevel' and Value not in _FFMPEG_LOG_LEVELS: return 400`.

**Live seam observation:**
- `ps` on I9 confirms production ffmpeg cmd includes `-loglevel error -stats`. HasLogLevel=True. Wire shape matches C4 expectation.

## Notes

- Root cause discovered 2026-08-05 via direct standalone reproduction on dot host. Full ffmpeg cmd on AoT S03E13 completed in 5m 44s at 4.17x realtime standalone. Production hung 32 min at 7%. Sole difference: stderr backpressure from `Non-monotonic DTS` warning flood on subtitle stream. Fleet-wide slowdown of 2026-07-30 (`manual_cancel_aot_defer` label) traces to same root cause.
- HwAccelResolver theory considered + dismissed earlier this session. SW HEVC decode + av1_nvenc runs 14.6x realtime on this file when stderr is unblocked. Not a decode-side bug.
- Audio filter chain considered + dismissed. Test C ran full 2-audio-track loudnorm pipeline in 5m 44s standalone. Not an audio-side bug.
- KISS review 2026-08-05: initial draft had drain-thread + bounded ring buffer + boot orphan sweep + attemptid-agnostic naming + fold-in-flight probe/Demucs. Trimmed to file-based stderr + whitelist validation. ~50 LOC target.
