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
1. UI form  ->  Controller endpoint
2. Controller  ->  OptimizationViewModel
3. ViewModel  ->  JellyfinService (paramiko SSH)
4. SSH client  ->  list/read /var/log/jellyfin FFmpeg.*-*.log files
5. Parse log filenames + bodies into operation records
6. Insert/upsert into JellyfinOperations table
7. Return Success envelope -> UI
```

## Stage detail

### 1. UI form -> Controller
Templates/Optimization.html submits to the JSON endpoints above. All endpoints return the project's standard envelope: `{"Success": bool, "ErrorMessage": str, ...}` on failure or `{"Success": true, ...}` on success.

### 2. Controller -> ViewModel
Thin pass-through. Errors are caught and serialized to the standard envelope with HTTP 500.

### 3. ViewModel -> JellyfinService
`JellyfinService.__init__` takes Host, SSHPort, SSHUser, SSHKeyPath, ApiKey, ApiPort from saved connection settings.

### 4. SSH client lifecycle
`_GetSSHClient()` builds a `paramiko.SSHClient` with `AutoAddPolicy` and connects with the configured key. Each operation opens and closes its own client. There is no connection pooling.

### 5. Log discovery + parsing
Filenames in `/var/log/jellyfin` are categorized by prefix:
- `FFmpeg.DirectStream-*` -> DirectStream
- `FFmpeg.Transcode-*` -> Transcode
- `FFmpeg.Remux-*` -> Remux

Log bodies are streamed via `exec_command` and parsed for transcode reason, device, codec mismatch, subtitle burn-in, etc.

### 6. Persist
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
