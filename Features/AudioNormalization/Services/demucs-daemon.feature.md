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

C5. **Device detection lives in the daemon.** `DemucsDaemonEntry._DetectDevice` picks `cuda` / `xpu` / `cpu` based on runtime probes. `DemucsVocalIsolationService._DetectDemucsDevice` (client-side legacy probe) is dead code and MUST be removed. Verifiable: grep `_DetectDemucsDevice` returns zero production hits.

C6. **Sole subprocess spawn path.** `DemucsDaemonClient` is the ONLY place in `Features/AudioNormalization/` that calls `subprocess.Popen` for `demucs.separate`. `DemucsVocalIsolationService` MUST NOT contain any `subprocess.run` / `Popen` for Demucs. Verifiable: grep `subprocess` in `DemucsVocalIsolationService.py` returns zero matches for the demucs invocation.

C7. **Graceful stop.** `DemucsDaemonClient.Stop()` closes stdin (daemon exits its read loop cleanly) then SIGTERM + wait(5s) + SIGKILL if still alive. Called on WorkerService shutdown (best-effort). Verifiable: after `SIGINT` to WorkerService, daemon subprocess exits within 6s.

C8. **Read deadline defeats hang.** `DemucsDaemonClient.IsolateVocals` reads response via `_ReadLineWithDeadline(IsolateReadTimeoutSec)` (default 1800s). Deadline elapsed OR daemon EOF -> daemon killed + `DemucsDaemonUnavailableError` raised. Prevents WorkerService thread from blocking forever when daemon hangs. Verifiable: freeze daemon with SIGSTOP; caller returns error within IsolateReadTimeoutSec + 1s; next `GetOrStartDaemon` respawns.

C9. **SystemExit does not crash daemon.** `DemucsDaemonEntry.Main` per-request except clause catches `(Exception, SystemExit)`. `demucs.separate.main` calls `sys.exit()` on model-load / parser errors; a bare `except Exception` misses `SystemExit`, kills the daemon, and every subsequent caller reads EOF -> JSONDecodeError. Verifiable: send a request with a bogus model name; daemon returns `Success=False` with `SystemExit: ...` errmsg and remains alive to serve next request.

C10. **Protocol stdout stays JSON-only.** `_IsolateOnce` swaps `sys.stdout` to `sys.stderr` for the duration of `demucs.separate.main`. Demucs and torch emit `print()` statements ("Separating track ...", "Selected model is a bag of ..."), progress bars, and warnings; without this swap they land on the daemon's stdout, get pumped into the client's `_StdoutQueue`, and the client parses them as responses -> JSONDecodeError `Expecting value: line 1 column 1 (char 0)` or `Response request-id mismatch` (a valid JSON print from an earlier request leaked past). Verifiable: grep `Expecting value: line 1 column 1` in `Logs` after a batch of Demucs runs == 0.

C11. **Stderr never pipe-blocks the daemon.** `DemucsDaemonClient._StderrDrainLoop` runs a daemon-thread `stderr.read(4096)` loop that drains torch + demucs stderr into a rolling 4KB tail buffer. Without it, long-running Demucs invocations fill the 64KB stderr pipe buffer and block on the next write -- the daemon appears hung and hits `_ReadLineWithDeadline` timeout. Verifiable: no `DemucsDaemonUnavailableError` timeout-string hits during a 100-job batch.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `DemucsVocalIsolationService -> DemucsDaemonClient.IsolateVocals` (function-call) | Service | `(StereoInputWavPath, OutputDir, ModelName)` | `IsolateResponse` (Success + paths OR ErrorMessage) | `TestDemucsDaemonProtocol` + live smoke |
| S2 | `DemucsDaemonClient -> subprocess stdin` (wire) | Client | `EncodeRequest(IsolateRequest) + '\n'` | Daemon reads one line, matches `RequestId` on response | Protocol test |
| S3 | `DemucsDaemonEntry -> demucs.separate.main` (function-call) | Daemon | `sys.argv = ['demucs.separate', '-n', model, '-d', device, '--two-stems', 'vocals', '-o', outdir, '--filename', '{stem}.{ext}', input]` | Vocals + instrumental WAVs land in `OutputDir/<ModelName>/` | Live smoke; response validates paths exist |

## Status

ACTIVE -- shipped 2026-07-15 commit 5c47322. Wired via `DemucsVocalIsolationService._GetDaemon` lazy init. Fleet deployed and running.

## Files

| File | Role |
|---|---|
| `Features/AudioNormalization/Services/DemucsDaemonProtocol.py` | Wire-format dataclasses + encode/decode + READY sentinel |
| `Features/AudioNormalization/Services/DemucsDaemonEntry.py` | Long-lived subprocess entrypoint; loads torch + IPEX + demucs; reads requests loop |
| `Features/AudioNormalization/Services/DemucsDaemonClient.py` | Owns `Popen`; process-singleton via `GetOrStartDaemon`; IsolateVocals returns `IsolateResponse` |
| `Features/AudioNormalization/Services/DemucsVocalIsolationService.py` | Client of daemon; retains `_MeasureWavRmsDbfs` + `MixBoostedPremix` + `MeasureSourceLoudnorm` (non-daemon-owned methods) |
| `Tests/Contract/TestDemucsDaemonProtocol.py` | Protocol encode/decode + READY constant |
