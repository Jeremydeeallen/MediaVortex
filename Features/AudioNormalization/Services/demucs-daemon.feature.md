# Demucs Daemon

**Slug:** demucs-daemon

## What It Does

Owns one long-lived Python subprocess per WorkerService process that loads torch + intel_extension_for_pytorch + Demucs model once, then processes vocal-isolation requests via stdin/stdout JSON IPC. Every `DemucsVocalIsolationService.IsolateVocals` call routes through this daemon.

Prior to this feature every isolate call `subprocess.run(python -c "...")` a fresh Python: full torch import + model load + XPU kernel compile every time. On Arc XPU this ran ~10 min cold. The daemon pays that cost once at daemon boot; every subsequent isolate is ~2-3 min.

## Success Criteria

C1. **One daemon per WorkerService process.** `DemucsDaemonClient.GetOrStartDaemon()` returns the process-singleton instance. Concurrent callers within one worker share the same daemon (thread-safe via `_SINGLETON_LOCK`). Verifiable: two `IsolateVocals` calls on the same worker use the same `_Proc.pid`.

C2. **Daemon respawn on crash.** If `_Proc.poll()` returns non-None (subprocess exited), the next `GetOrStartDaemon()` call spawns a fresh subprocess. Original crash is logged; caller retries transparently through the singleton refresh. Verifiable: kill the subprocess PID externally; next isolate call succeeds after ~10s (fresh cold-start).

C3. **READY handshake before requests.** Daemon writes `DEMUCS_DAEMON_READY` on stdout after torch + IPEX + model init completes. `DemucsDaemonClient._WaitForReady` blocks up to `SystemSettings.DemucsDaemonStartTimeoutSec` (default 180). No request is written before READY. Verifiable: stderr shows torch import lines; stdout starts with READY.

C4. **Request/response protocol.** `DemucsDaemonProtocol.IsolateRequest` = `{RequestId, InputWavPath, OutputDir, ModelName}`. `IsolateResponse` = `{RequestId, Success, VocalsWavPath, InstrumentalWavPath, ErrorMessage}`. One request per newline; one response per newline. Client verifies `Resp.RequestId == Req.RequestId` before returning. Verifiable: `Tests/Contract/TestDemucsDaemonProtocol.py`.

C5. **The device is required, never detected.** Separation runs on the device the worker's hardware calls for: `cuda` when `Workers.NvencCapable`, else `xpu` when `Workers.QsvCapable`, else `cpu`. The requirement is read from `Workers` when the daemon is started and passed to it as `--device`. Before READY the daemon confirms torch can use that device; if it cannot, the daemon exits with a `DEMUCS_DEVICE_ERROR` line naming the required device, and the client raises `DemucsDaemonUnavailableError` carrying that line. Separation never runs on a slower device than the hardware calls for; `cpu` is used only on a worker with neither GPU flag. Verifiable: `Tests/Contract/TestDemucsNoFallback.py`; on a GPU worker whose GPU is hidden from torch, an Audio job fails with the device error.

C13. **Measurements fail, they do not default.** The vocals-level, source-loudness and premix-loudness measurements raise when ffmpeg returns no parsable value, with the tail of ffmpeg's output in the error. A measurement is never replaced by a silence floor, by "unknown", or by a different loudness method. A measured level of `-inf` (true digital silence) is a value, not a failure. Verifiable: `Tests/Contract/TestDemucsNoFallback.py`.

C6. **Sole subprocess spawn path.** `DemucsDaemonClient` is the ONLY place in `Features/AudioNormalization/` that calls `subprocess.Popen` for `demucs.separate`. `DemucsVocalIsolationService` MUST NOT contain any `subprocess.run` / `Popen` for Demucs. Verifiable: grep `subprocess` in `DemucsVocalIsolationService.py` returns zero matches for the demucs invocation.

C7. **Graceful stop.** `DemucsDaemonClient.Stop()` closes stdin (daemon exits its read loop cleanly) then SIGTERM + wait(5s) + SIGKILL if still alive. Called on WorkerService shutdown (best-effort). Verifiable: after `SIGINT` to WorkerService, daemon subprocess exits within 6s.

C8. **A hang is detected by lack of work, not elapsed time.** A separation request has no total-duration cap: a run that keeps working is never failed for how long it takes. The client fails a request only when the daemon shows no sign of work for the stall window (default 300s) OR the daemon exits. A sign of work is any line on the daemon's stderr (progress ticks included) or an increase in the daemon process's consumed CPU time. On stall or exit the daemon is killed and `DemucsDaemonUnavailableError` is raised, so the WorkerService thread never blocks forever. Verifiable: freeze daemon with SIGSTOP; caller returns a "stalled" error within stall window + a few seconds; next `GetOrStartDaemon` respawns. A separation running longer than 30 minutes with advancing progress completes. `Tests/Contract/TestDemucsDaemonLiveness.py`.

C9. **SystemExit does not crash daemon.** `DemucsDaemonEntry.Main` per-request except clause catches `(Exception, SystemExit)`. `demucs.separate.main` calls `sys.exit()` on model-load / parser errors; a bare `except Exception` misses `SystemExit`, kills the daemon, and every subsequent caller reads EOF -> JSONDecodeError. Verifiable: send a request with a bogus model name; daemon returns `Success=False` with `SystemExit: ...` errmsg and remains alive to serve next request.

C10. **Protocol stdout stays JSON-only.** `_IsolateOnce` swaps `sys.stdout` to `sys.stderr` for the duration of `demucs.separate.main`. Demucs and torch emit `print()` statements ("Separating track ...", "Selected model is a bag of ..."), progress bars, and warnings; without this swap they land on the daemon's stdout, get pumped into the client's `_StdoutQueue`, and the client parses them as responses -> JSONDecodeError `Expecting value: line 1 column 1 (char 0)` or `Response request-id mismatch` (a valid JSON print from an earlier request leaked past). Verifiable: grep `Expecting value: line 1 column 1` in `Logs` after a batch of Demucs runs == 0.

C11. **Stderr never pipe-blocks the daemon + emits per-tqdm-tick progress.** `DemucsDaemonClient._StderrDrainLoop` runs a daemon-thread `readline()` loop over the stderr pipe (universal-newline mode splits demucs' `\r`-terminated tqdm ticks into lines). Every line is consumed: pipe-buffer safety preserved by draining, not by tail retention. Lines matching `_TQDM_LINE_RE` (`^\s*(\d+)%\|.*?\|\s*([\d.]+)/([\d.]+)`) invoke the caller-supplied `ProgressCallback(percent, done_sec, total_sec)` so `/Activity` renders live percent during Demucs; non-tqdm lines are kept as `_LastStderrLine` (500-char tail) for post-crash diagnostic. Verifiable: no `DemucsDaemonUnavailableError` timeout-string hits during a 100-job batch; `Tests/Contract/TestDemucsProgressParser.py` asserts the regex round-trip.

C12. **Separation memory does not grow with input length.** An input longer than one piece (20 minutes, plus a tail allowance of 60 seconds) is cut into 20-minute pieces that overlap by 10 seconds; all pieces go to the separator in one call; each overlap is linearly crossfaded and the pieces are written as one vocals file and one background file at the paths the caller already reads. An input that fits in one piece is separated whole, exactly as without this criterion. The joined result has no gap, repeat or discontinuity at piece boundaries. Before a multi-piece run the daemon writes `MV_DEMUCS_CHUNKS <n> <total_seconds>` on stderr and the client reports progress across the whole input rather than restarting at each piece. Verifiable: `Tests/Contract/TestDemucsChunking.py` (piece plan; split then join of a known signal returns that signal); a ~2-hour input completes on a worker whose memory cap a whole-file run exceeds.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `DemucsVocalIsolationService -> DemucsDaemonClient.IsolateVocals` (function-call) | Service | `(StereoInputWavPath, OutputDir, ModelName)` | `IsolateResponse` (Success + paths OR ErrorMessage) | `TestDemucsDaemonProtocol` + live smoke |
| S2 | `DemucsDaemonClient -> subprocess stdin` (wire) | Client | `EncodeRequest(IsolateRequest) + '\n'` | Daemon reads one line, matches `RequestId` on response | Protocol test |
| S3 | `DemucsDaemonEntry -> demucs.separate.main` (function-call) | Daemon | `sys.argv = ['demucs.separate', '-n', model, '-d', device, '--two-stems', 'vocals', '-o', outdir, '--filename', '{stem}.{ext}', input]` | Vocals + instrumental WAVs land in `OutputDir/<ModelName>/`. Multi-piece input (C12): the separator gets N piece files and writes under `OutputDir/demucs_chunks/`; the daemon joins them into the same two `OutputDir/<ModelName>/` files (16-bit PCM at the separator's sample rate) and deletes the piece directory | Live smoke; response validates paths exist; `TestDemucsChunking` |
| S4 | `DemucsDaemonEntry -> DemucsDaemonClient` progress (wire, stderr) | Daemon | line `MV_DEMUCS_CHUNKS <n> <total_seconds>` before a multi-piece run; separator then prints `Separating track ...` once per piece and tqdm ticks per piece | Client counts pieces and scales each tick to whole-input percent + seconds | `TestDemucsChunking` |

## Status

ACTIVE -- shipped 2026-07-15 commit 5c47322. Wired via `DemucsVocalIsolationService._GetDaemon` lazy init. Fleet deployed and running.

## Files

| File | Role |
|---|---|
| `Features/AudioNormalization/Services/DemucsDaemonProtocol.py` | Wire-format dataclasses + encode/decode + READY sentinel |
| `Features/AudioNormalization/Services/DemucsDaemonEntry.py` | Long-lived subprocess entrypoint; loads torch + IPEX + demucs; reads requests loop |
| `Features/AudioNormalization/Services/DemucsChunking.py` | C12 piece plan, split, crossfade join, progress scaling |
| `Features/AudioNormalization/Services/DemucsDaemonClient.py` | Owns `Popen`; process-singleton via `GetOrStartDaemon`; IsolateVocals returns `IsolateResponse` |
| `Features/AudioNormalization/Services/DemucsVocalIsolationService.py` | Client of daemon; retains `_MeasureWavRmsDbfs` + `MixBoostedPremix` + `MeasureSourceLoudnorm` (non-daemon-owned methods) |
| `Tests/Contract/TestDemucsDaemonProtocol.py` | Protocol encode/decode + READY constant |
