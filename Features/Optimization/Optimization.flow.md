# Jellyfin Optimization Flow

**Slug:** optimization

Pipeline that pulls FFmpeg operation logs from a running Jellyfin server over SSH, parses them, persists them to the local DB, and surfaces aggregated stats on `/Optimization`.

## Entry Points

- `POST /api/Optimization/TestConnection` -- one-shot SSH check.
- `POST /api/Optimization/RefreshJellyfin` -- the "sync" form; fetches and persists new log entries.
- `GET /api/Optimization/JellyfinAnalysis`, `OperationDetails`, `DeviceAnalysis`, `LocalAnalysis*` -- read-only views over already-synced data.
- `GET/POST /api/Optimization/ConnectionSettings` -- persist SSH host/port/user/key path + API key/port.

All entry points are registered in `Features/Optimization/OptimizationController.py`.

## Stages

```
ST1. UI form  ->  Controller endpoint
ST2. Controller  ->  OptimizationViewModel
ST3. ViewModel  ->  JellyfinService (paramiko SSH)
ST4. SSH client  ->  list/read /var/log/jellyfin FFmpeg.*-*.log files
ST5. Parse log filenames + bodies into operation records
ST6. Insert/upsert into JellyfinOperations table
ST7. Return Success envelope -> UI
```

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1 -> ST2` (UI -> controller) | `Templates/Optimization.html` POST | JSON body: `{Host, SSHPort, SSHUser, SSHKeyPath, ApiKey, ApiPort}` (or empty for read endpoints) | `OptimizationController` routes to ViewModel | Browser DevTools: Network panel shows POST + 200 envelope |
| S2 | `ST3 -> ST4` (ViewModel -> SSH) | `JellyfinService._GetSSHClient()` | paramiko client connected with key auth | `exec_command('ls /var/log/jellyfin')` returns file list | `POST /api/Optimization/TestConnection` returns `{Success: true}` |
| S3 | `ST5 -> ST6` (parse -> persist) | `JellyfinService.ParseLogs` -> list of `JellyfinOperation` records | Per-record: `(OperationType, Device, TranscodeReason, VideoCodec, AudioCodec, SubtitleBurnIn, Timestamp)` | `OptimizationRepository` UPSERT into `JellyfinOperations` | `SELECT COUNT(*) FROM JellyfinOperations` increments after a `RefreshJellyfin` call |
| S4 | runtime dependency | `requirements.txt` declares `paramiko>=3.0.0`; WebService runs from `WebService/venv/` (memory: `feedback_webservice_venv_drift.md`) | Active venv has paramiko importable | `ImportError` is caught at JellyfinService construction; surfaced via the standard envelope as `Success=false, Message='paramiko is not installed'` rather than HTTP 500 -- per `Optimization.feature.md` C8 | `WebService/venv/Scripts/python.exe -c "import paramiko"` rc 0; smoke: stop WebService, `pip uninstall paramiko` in its venv, restart, observe sync form surfaces the envelope rather than the raw exception |
| S5 | `ST6 -> read views` (persist -> aggregation endpoints) | `JellyfinOperations` table accreted by `RefreshJellyfin` | `JellyfinOperations.(Id, OperationType TEXT, Device TEXT, TranscodeReason TEXT, VideoCodec, AudioCodec, SubtitleBurnIn BOOLEAN, Timestamp TIMESTAMP)` -- append-only; no UPDATE path | `OptimizationRepository.GetJellyfinAnalysis`, `GetOperationDetails`, `GetDeviceAnalysis` run SQL aggregations grouping by Device / TranscodeReason / day. **Non-obvious:** Templates/Optimization.html doesn't call the persistence endpoint; it polls these read views on render -- so an empty `JellyfinOperations` table renders zero counts silently with no error envelope | `SELECT Device, COUNT(*) FROM JellyfinOperations GROUP BY Device ORDER BY 2 DESC LIMIT 5` matches the page's "top devices" chart |
| S6 | connection-settings persistence | `POST /api/Optimization/ConnectionSettings` -> `OptimizationRepository.SaveConnectionSettings` | `SystemSettings.(Key IN ('JellyfinHost', 'JellyfinSSHPort', 'JellyfinSSHUser', 'JellyfinSSHKeyPath', 'JellyfinApiPort', 'JellyfinApiKey'), Value)` -- per-key rows, NOT a single JSON blob | `JellyfinService.__init__` reads each key fresh per call via `SystemSettingsRepository.GetSystemSetting` -- no `self._cached_*` (R3). Operator changes to Host/Port apply on the next `RefreshJellyfin` without restart | `UPDATE SystemSettings SET Value='other-host' WHERE Key='JellyfinHost'`; next `TestConnection` POST targets the new host without WebService restart |
| S7 | `ST2` host-not-configured guard | `JellyfinService.__init__` | When `SystemSettings.JellyfinHost` is empty/missing, raises `"Jellyfin host is not configured"` before SSH attempt | Caller catches, returns envelope -- does NOT log at ERROR (not actionable). **Non-obvious:** fresh installs see this on every render of `/Optimization` until the operator fills the form. Don't alarm on empty-host log noise | `DELETE FROM SystemSettings WHERE Key='JellyfinHost'`; refresh `/Optimization`, see the configured-host empty state, not a 500 |

## Stage detail

### ST1. UI form -> Controller
Templates/Optimization.html submits to the JSON endpoints above. All endpoints return the project's standard envelope: `{"Success": bool, "ErrorMessage": str, ...}` on failure or `{"Success": true, ...}` on success.

### ST2. Controller -> ViewModel
Thin pass-through. Errors are caught and serialized to the standard envelope with HTTP 500.

### ST3. ViewModel -> JellyfinService
`JellyfinService.__init__` takes Host, SSHPort, SSHUser, SSHKeyPath, ApiKey, ApiPort from saved connection settings.

### ST4. SSH client lifecycle
`_GetSSHClient()` builds a `paramiko.SSHClient` with `AutoAddPolicy` and connects with the configured key. Each operation opens and closes its own client. There is no connection pooling.

### ST5. Log discovery + parsing
Filenames in `/var/log/jellyfin` are categorized by prefix:
- `FFmpeg.DirectStream-*` -> DirectStream
- `FFmpeg.Transcode-*` -> Transcode
- `FFmpeg.Remux-*` -> Remux

Log bodies are streamed via `exec_command` and parsed for transcode reason, device, codec mismatch, subtitle burn-in, etc.

### ST6. Persist (ST7: response envelope returned by controller)
Parsed records are upserted into the JellyfinOperations table. The local `/Optimization` page reads from that table for all aggregated views.

## Failure modes

| Stage | Failure | User-visible |
|-------|---------|--------------|
| Module import | `paramiko` not installed in the runtime venv | Every Jellyfin-touching endpoint returns `{"Success": false, "ErrorMessage": "paramiko is not installed"}` |
| 3 | Host not configured | `"Jellyfin host is not configured"` |
| 4 | SSH auth fails / network unreachable | Exception text from paramiko surfaced in `ErrorMessage` |
| 4 | Key file missing / wrong permissions | Exception text surfaced |
| 5 | Log dir empty or unreadable | Stage returns zero counts (Success=true with all zeros) |
| 6 | DB insert fails | Logged via `LoggingService.LogException`, returned as `Success=false` |

## Runtime environment

The WebService process must be launched from a Python environment that has every entry in `requirements.txt` installed. Two venvs are present in this repo:

- `venv/` -- root venv, documented in CLAUDE.md.
- `WebService/venv/` -- service-local venv. If WebService is launched as `WebService/venv/Scripts/python.exe Main.py`, this is the runtime, and `pip install -r requirements.txt` must be run against it.

`paramiko>=3.0.0` is declared in `requirements.txt` line 21. If the running WebService reports "paramiko is not installed", the active venv is missing it -- install into the venv that owns the running process and restart WebService.
