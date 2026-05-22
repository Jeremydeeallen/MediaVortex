# Flow: Windows Worker Deploy

Deploys a MediaVortex `WorkerService` instance natively on a Windows host (not Docker). Counterpart to `worker-deploy-linux.flow.md` (Docker on Linux -- covers LXC and bare-metal). Both deployment models coexist; this flow covers the Windows-native path used by I9-2024 and (as of 2026-05-09) REMINGTON.

## Entry Point

`scp` the repo from the dev workstation to the target Windows host, recreate the venv, set env vars, mount required NFS shares, run `WorkerService\Main.py`.

## Host Inventory (active Windows workers)

| Hostname | IP | SSH user | Repo path | Notes |
|---|---|---|---|---|
| `I9-2024` | (dev workstation, varies) | (operator) | `C:\Code\MediaVortex` | Hosts both WebService + a co-located WorkerService process. Currently the only Online Windows worker. |
| `Remington` | -- | -- | -- | **Retired.** Host hardware rebuilt to Linux Mint and now runs as Wakko (`client-b450m-01`, 10.0.0.230). The `Remington` Workers row lingers in DB with a stale heartbeat (6+ days) and can be deleted on the next cleanup pass per `worker-deploy.feature.md` criterion 12. |

**SSH from dev workstation to a worker:**

```bash
# Verify reachable + identify which host
ssh owner@10.0.0.230 'hostname'
# -> Remington

# Default SSH user across Windows workers in this homelab is `owner`.
# It is NOT root/Administrator/jeremy; the deploy-windows-worker.py
# script's --user flag defaults to `owner` for the same reason.
```

If `Permission denied (publickey,password)` -- the host is up but the dev workstation's key isn't authorised, or password auth is disabled. The OpenSSH Server install path on the deploy doc handles this; an existing host already has the right keys in the operator's `~/.ssh/authorized_keys` on the worker.

## Code-Only Update (Hot-Swap, the most common case)

When you've shipped a code change to `main` and want to roll it out to a Windows worker without re-running the full deploy (no venv rebuild, no env-var push, no NFS mount changes -- just code + restart), use this exact sequence.

**Step 1 -- stop the scheduled task AND explicitly kill the Python child processes.** This is critical and easy to get wrong. `Stop-ScheduledTask` only marks the scheduler entry as stopped; **it does NOT kill the python.exe processes the task spawned**. Those processes keep running, holding file locks, and -- worse -- continue to claim and process queue jobs with stale in-memory code. A subsequent `Start-ScheduledTask` then spawns a SECOND set of processes alongside the first, accumulating zombie workers.

This was discovered the hard way on 2026-05-09 when a remux job built an FFmpeg command with pre-fix shape (unconditional `-tag:v hvc1`, `-c:a copy`, no `loudnorm`) hours after the fix was deployed. Six zombie Python processes had accumulated on Remington across multiple "stop -> deploy -> start" cycles, and a stale one claimed the job. The fix below kills them explicitly.

```bash
ssh owner@10.0.0.230 'powershell -Command "
  Stop-ScheduledTask -TaskName \"MediaVortex Worker\" -ErrorAction SilentlyContinue;
  Get-Process python* -ErrorAction SilentlyContinue | Where-Object {
    (Get-CimInstance Win32_Process -Filter \"ProcessId=\$(\$_.Id)\").CommandLine -like \"*MediaVortex*\"
  } | ForEach-Object {
    Write-Host \"Killing PID \$(\$_.Id) (started \$(\$_.StartTime))\";
    Stop-Process -Id \$_.Id -Force -ErrorAction SilentlyContinue
  };
  Start-Sleep -Seconds 3;
  $count = (Get-Process python* -ErrorAction SilentlyContinue | Where-Object {
    (Get-CimInstance Win32_Process -Filter \"ProcessId=\$(\$_.Id)\").CommandLine -like \"*MediaVortex*\"
  } | Measure-Object).Count;
  Write-Host \"Remaining MediaVortex python procs: \$count\"
"'
# Expected: list of killed PIDs (often 1-6 depending on accumulated zombies),
# then "Remaining MediaVortex python procs: 0".
```

The CommandLine filter (`*MediaVortex*`) catches every Python process whose command line includes the repo path, regardless of whether they were spawned by the scheduled task, by `StartWorker.py`, or directly. **Do not skip the explicit-kill step on Windows hosts** -- the doc's old version did and it caused a real production incident.

**Step 2 -- scp the changed files from dev workstation.**

```bash
# CRITICAL: scp paths MUST use Windows-style `C:/Code/...`, NOT `/c/Code/...`.
# The /c/ form errors with "No such file or directory" even though Test-Path
# on the worker returns True for the same path. This is an OpenSSH/scp Windows
# server quirk. Sample of a correct invocation:

scp Models/CommandBuilder.py 'owner@10.0.0.230:C:/Code/MediaVortex/Models/CommandBuilder.py'
scp Features/FileReplacement/FileReplacementBusinessService.py 'owner@10.0.0.230:C:/Code/MediaVortex/Features/FileReplacement/FileReplacementBusinessService.py'
# ...etc, one file at a time, or scp -r a directory.
```

**Step 3 -- clear .pyc caches on the worker.** Python normally invalidates a `.pyc` whose source mtime is newer than the cached compile, but scp can produce mtimes that confuse the cache check (clock skew, filesystem timestamp granularity). Belt-and-suspenders:

```bash
ssh owner@10.0.0.230 'powershell -Command "Remove-Item -Force -ErrorAction SilentlyContinue C:\Code\MediaVortex\Models\__pycache__\CommandBuilder*.pyc, C:\Code\MediaVortex\Features\FileReplacement\__pycache__\FileReplacementBusinessService*.pyc; Write-Host pyc-cleared"'
```

**Step 4 -- start the scheduled task.**

```bash
ssh owner@10.0.0.230 'powershell -Command "Start-ScheduledTask -TaskName \"MediaVortex Worker\"; Start-Sleep -Seconds 4; (Get-ScheduledTask -TaskName \"MediaVortex Worker\").State"'
# Expected output: Running
```

**Step 5 -- verify Workers row is Online with a fresh heartbeat.** Run from the dev workstation against the production DB:

```bash
sleep 8 && py Scripts/SQLScripts/QueryDatabase.py sql "SELECT WorkerName, Status, AGE(NOW(), LastHeartbeat) AS HeartbeatAge FROM Workers WHERE WorkerName = 'Remington'"
# Expected: Status=Online, HeartbeatAge under ~30 seconds.
```

**Step 6 (optional but recommended) -- verify the new code is actually loaded.** Queue a single test job and inspect the resulting `TranscodeAttempts.FFpmpegCommand` for a known signature of the new code. For the 2026-05-09 remux safety fix the signature is `_remuxed.mp4` in the output path:

```bash
py Scripts/SQLScripts/QueueRemux.py --pick-one
# Wait ~10s, then:
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT FFpmpegCommand FROM TranscodeAttempts ORDER BY Id DESC LIMIT 1"
# Confirm the OUTPUT path (last quoted string in the command) ends with _remuxed.mp4.
# If it does not, the worker did not pick up the new code -- restart again.
```

This whole sequence takes about 30 seconds end-to-end and is idempotent. Use this for routine code shipping; reserve the full `deploy-windows-worker.py` only for fresh hosts or when env vars / NFS mounts changed.

### Gotchas

- **`git` is not on Remington's PATH.** scp from the dev workstation is the only update channel. Don't waste time trying `git pull` on the remote.
- **Unix tools (`head`, `tail`, `grep`) don't exist on Remington's default shell.** Wrap remote commands in PowerShell and use `Select-Object -First N` for truncation.
- **scp path syntax must be `C:/Code/...` (forward slashes, drive-prefix form), not `/c/Code/...`.** Same path in a remote PowerShell command works either way; the asymmetry is specific to scp's path parser when the target is a Windows OpenSSH server.
- **Stopping the scheduled task does NOT kill the Python child processes.** It only marks the scheduler entry as stopped. The Python processes keep running and claiming jobs with their stale in-memory code -- and a subsequent `Start-ScheduledTask` spawns ANOTHER set of processes on top, accumulating zombies. **You must explicitly `Stop-Process` every Python process whose command line includes "MediaVortex"** before scp + restart. The Step 1 snippet above does this. (Discovered 2026-05-09 after a remux job ran with stale code despite three rounds of "successful" hot-swap; six zombie pythons had accumulated.)
- **`__pycache__` directories sometimes survive an scp + restart cycle and serve stale bytecode.** The Step 3 explicit removal eliminates the variable.
- **The deploy-windows-worker.py automation does NOT stop the running worker before scp.** It assumes a fresh host. For an in-place code update on a running worker, prefer the manual sequence above.

## When To Use This Flow

- Adding a new physical Windows workstation as a CPU-only transcode worker
- Re-deploying after a host rebuild
- Recovering from corrupted venv or stale env vars

For Linux containerized workers (which scale via `docker compose`), use `worker-deploy-linux.flow.md` instead.

## Deploy Sequence (Quick Reference)

Run `deploy/deploy-windows-worker.py <target-ip>` from the dev workstation for the automated path. The script wraps every step below in order, idempotent. Manual sections in this doc remain canonical for one-off recovery and for understanding what the automation does.

| # | Step | Where | Owner |
|---|---|---|---|
| 1 | Pre-flight checks (Python, sshd, NetworkCategory, port reachability) | Worker host (queried over SSH) | `deploy-windows-worker.py --check` |
| 2 | scp the repo to `C:\Code\MediaVortex` | Dev workstation -> Worker | `scp -r ...` |
| 3 | Recreate venv (the source venv's `pyvenv.cfg` paths don't translate) | Worker host | `py -m venv venv && pip install -r requirements.txt` |
| 4 | Set `MEDIAVORTEX_DB_*` and `MEDIAVORTEX_*_PASSWORD` env vars at User scope | Worker host (creds piped via SSH stdin from dev-workstation vault) | `[Environment]::SetEnvironmentVariable(..., 'User')` |
| 5 | Register the `MediaVortex Worker` Task Scheduler entry | Worker host | `deploy\Register-WorkerTask.ps1` |
| 6 | Trigger the task once to validate; future runs fire on user logon | Worker host | `Start-ScheduledTask -TaskName 'MediaVortex Worker'` |
| 7 | Verify the `Workers` row is Online with a recent heartbeat | Dev workstation (DB query) | `QueryDatabase.py sql ...` |

Expected timing on a host with a built venv and reachable network: full sequence completes in **~2-4 minutes**. Worker registration appears in the DB within **~10s** of triggering the task; first job claim within **~60s** of registration if the queue is non-empty.

## Pre-Flight Checks

| Check | Command | Required outcome |
|---|---|---|
| Python 3.12+ installed | `py --version` | Version 3.12.x |
| Git available (optional, for updates) | `git --version` | any |
| OpenSSH Server running | `Get-Service sshd` | Running, StartType Automatic |
| Network profile is Private (not Public) | `Get-NetConnectionProfile` | NetworkCategory = Private |
| Can reach DB | `Test-NetConnection 10.0.0.15 -Port 5432` | TcpTestSucceeded = True |
| Can reach Porky NFS | `Test-NetConnection 10.0.0.43 -Port 2049` | TcpTestSucceeded = True |
| Can reach Synology NFS | `Test-NetConnection 10.0.0.61 -Port 2049` | TcpTestSucceeded = True |
| NFS client installed | `(Get-WindowsOptionalFeature -Online -FeatureName ClientForNFS-Infrastructure).State` | Enabled |

If `NetworkCategory = Public`, fix it before mounting drives:

```powershell
Set-NetConnectionProfile -InterfaceAlias Ethernet -NetworkCategory Private
```

If `sshd` is installed but stopped:

```powershell
Start-Service sshd; Set-Service sshd -StartupType Automatic
```

If not installed:

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd; Set-Service sshd -StartupType Automatic
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -Profile Any
```

## Build and Deploy

Run from the dev workstation (PowerShell or Git Bash). Targets the Windows worker host directly via SSH/SCP — no LXC intermediary.

```powershell
# 1. Pre-create destination
ssh owner@<target-ip> "powershell -Command \"if (-not (Test-Path C:\Code)) { New-Item -ItemType Directory -Path C:\Code -Force }\""

# 2. Copy entire repo (including FFmpeg binary, ~200 MB FFmpegMaster\bin\ffmpeg.exe)
scp -r C:/Code/MediaVortex owner@<target-ip>:C:/Code/

# 3. Recreate venv (the source venv is bound to the dev workstation's Python paths)
ssh owner@<target-ip> "powershell -Command \"
  Remove-Item -Recurse -Force C:\Code\MediaVortex\venv -ErrorAction SilentlyContinue;
  Remove-Item -Recurse -Force C:\Code\MediaVortex\WebService\venv -ErrorAction SilentlyContinue;
  Remove-Item -Recurse -Force C:\Code\MediaVortex\WorkerService\venv -ErrorAction SilentlyContinue
\""
ssh owner@<target-ip> "cd C:\Code\MediaVortex && py -m venv venv && venv\Scripts\python.exe -m pip install --upgrade pip && venv\Scripts\python.exe -m pip install -r requirements.txt"
```

The repo's `venv/`, `WebService/venv/`, and any archived `*/venv/` directories scp over but are unusable on the target — Python venvs bake absolute paths into `pyvenv.cfg`. Always recreate.

## Deploy Automation (`deploy/deploy-windows-worker.py`)

A single-command wrapper around steps 1-8 above. Lives at `deploy/deploy-windows-worker.py` in the MediaVortex repo. Designed to be run from the dev workstation against a fresh Windows host that has only Python 3.12 and OpenSSH Server installed.

```powershell
# Full deploy from scratch:
cd C:\Code\MediaVortex
.\venv\Scripts\python.exe deploy\deploy-windows-worker.py 10.0.0.230

# Pre-flight only (no changes made):
.\venv\Scripts\python.exe deploy\deploy-windows-worker.py 10.0.0.230 --check

# Skip steps that are already done (idempotent re-run):
.\venv\Scripts\python.exe deploy\deploy-windows-worker.py 10.0.0.230 --skip-scp --skip-venv
```

The script:
- Pushes DB env vars (and optional CPU-thread cap) through SSH stdin into a remote PowerShell `-EncodedCommand` block on the worker host (the only safe quoting strategy across Bash/PS/SSH layers; see Failure Modes for what happens if you try plain `-Command "..."`). NFS mounts use AUTH_SYS, so no share credentials are pushed.
- Verifies the `Workers` row reaches `Status='Online'` with a heartbeat <60s old within 90s of triggering the task; exits non-zero if not
- Idempotent: each step has a "skip if already done" check, so re-running on a partially-deployed host completes only the missing steps

Manual deploy is still supported -- every section below documents the by-hand command equivalents the script wraps.

## Drive Mappings

The worker's Step 0 `_VerifyRequiredPaths()` reads `DISTINCT LEFT(FilePath,2)` from `MediaFiles` and verifies each prefix is accessible via `os.path.exists()`. If any required drive is missing the worker hard-fails before any DB writes. The required prefixes are `T:`, `M:`, `Z:`.

| Letter | UNC | Server | Protocol |
|---|---|---|---|
| T: | `\\10.0.0.43\srv\nfs-media-_tv` | Porky | NFS (AUTH_SYS) |
| M: | `\\10.0.0.61\volume1\_video\Adults\Movies` | Synology | NFS (AUTH_SYS) |
| Z: | `\\10.0.0.61\volume2\XXX` | Synology | NFS (AUTH_SYS) |

All mounts are NFS via the Windows NFS client. No credentials are required. Install the client once per host:

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName ServicesForNFS-ClientOnly,ClientForNFS-Infrastructure -All
```

Establish drive mappings via `mount.exe` (run interactively on the worker host so the operator's SID owns the mappings). **Always use `mtype=hard`** -- plain `net use` defaults to `mtype=soft, timeout=0.8s, retry=1`, which produces intermittent FFmpeg `Error opening output file: Invalid argument` (EINVAL) failures when the NFS server is briefly slow:

```powershell
mount.exe -o mtype=hard -o timeout=30 -o rsize=1024 -o wsize=1024 -o anon \\10.0.0.43\srv\nfs-media-_tv T:
mount.exe -o mtype=hard -o timeout=30 -o rsize=1024 -o wsize=1024 -o anon \\10.0.0.61\volume1\_video\Adults\Movies M:
mount.exe -o mtype=hard -o timeout=30 -o rsize=1024 -o wsize=1024 -o anon \\10.0.0.61\volume2\XXX Z:
```

Verify: `mount.exe` output must show `mount=hard` on each row. `mount=soft` is the failure mode.

`StartWorker.py` re-runs these `mount.exe` commands in its own process at every launch -- mappings reconnect at interactive logon, but SSH sessions and Task Scheduler runs do NOT inherit them. `mount.exe` does not accept `retry=` together with `mtype=hard` (hard mounts retry forever by definition).

## Environment Variables

Set at User scope so they survive across sessions. Worker startup reads them once.

```powershell
[Environment]::SetEnvironmentVariable('MEDIAVORTEX_DB_HOST','10.0.0.15','User')
[Environment]::SetEnvironmentVariable('MEDIAVORTEX_DB_PORT','5432','User')
[Environment]::SetEnvironmentVariable('MEDIAVORTEX_DB_NAME','mediavortex','User')
[Environment]::SetEnvironmentVariable('MEDIAVORTEX_DB_USER','mediavortex','User')
[Environment]::SetEnvironmentVariable('MEDIAVORTEX_DB_PASSWORD','mediavortex','User')
# Optional: cap FFmpeg `-threads` (note: SVT-AV1 internal worker pool ignores this -- see Failure Modes)
[Environment]::SetEnvironmentVariable('MEDIAVORTEX_MAX_CPU_THREADS','12','User')
```

## First Run

The path-verification step rejects the launch if any required drive is missing in the worker's session. Always mount drives in the **same session** that launches the worker. Use `StartWorker.py` (added 2026-05-09) -- it mounts T:/M:/Z: in its own process, then launches `WorkerService\Main.py` inline.

```powershell
# Single command, ad-hoc test from a logged-in shell:
cd C:\Code\MediaVortex
.\venv\Scripts\python.exe StartWorker.py            # mount + verify + launch
.\venv\Scripts\python.exe StartWorker.py --dry-run  # mount + verify; do not launch
.\venv\Scripts\python.exe StartWorker.py --no-mount # drives already mounted
```

`StartWorker.py` mounts T:/M:/Z: via `net use ... /persistent:yes`. NFS uses AUTH_SYS, so no credentials are passed. If a required drive cannot be mounted (NFS client not installed, server unreachable, etc.), the launcher exits with code 2.

Expected first-run sequence (visible in stdout / `Logs` table):

1. `_VerifyRequiredPaths()` confirms each `MediaFiles` drive prefix is accessible
2. `_RegisterAndLoadWorkerConfig()` resolves `FFmpegPath` from `FFmpegMaster\bin\ffmpeg.exe` (project-bundled) and UPSERTs the `Workers` row with `WorkerName = <hostname>`, `Status='Online'`, `LastHeartbeat=NOW()`
3. Health, status, and capability polling threads start
4. `MainLoop` blocks on `ShutdownEvent`
5. Within ~60 s the capability poller picks up `TranscodeEnabled=true` (default for new rows) and the transcode loop begins claiming jobs

## Post-Deploy Verification

```sql
-- Verify registration from the dev workstation
SELECT WorkerName, Status, FFmpegPath, FFprobePath, Platform, LastHeartbeat
FROM Workers WHERE WorkerName = '<hostname>';
```

Expected: row exists, `FFmpegPath` populated (NOT `NULL`), `Platform='windows'`, `LastHeartbeat` updating every 30 s.

Expected timing after `Start-ScheduledTask`:
- **0-10 s**: process visible in `Get-Process python` filtered to the venv path
- **0-10 s**: `Workers` row UPSERT-ed (Status=Online, FFmpegPath populated, LastHeartbeat = now)
- **0-30 s**: capability poller updates `TranscodeEnabled=true`
- **0-60 s**: first job claim if the queue has eligible work

If the row does not appear within 30 s, check `Get-ScheduledTaskInfo -TaskName 'MediaVortex Worker'` for `LastTaskResult` (267009 = currently running, 0 = exited cleanly, anything else = failure) and read `Logs` table entries with `Source='WorkerService'` for the worker host.

```sql
-- Watch a job get claimed
SELECT QueueId, ClaimedBy, Status, DateStarted FROM TranscodeQueue
WHERE ClaimedBy = '<hostname>' ORDER BY DateStarted DESC LIMIT 5;
```

To stop accepting new work without killing the in-flight job:

```sql
UPDATE Workers SET Status = 'Draining' WHERE WorkerName = '<hostname>';
```

## Persistence (Production Run)

For production, run the worker outside an SSH session so disconnects do not kill it. Two options:

| Option | Pros | Cons |
|---|---|---|
| Task Scheduler "On user logon" | Simple, runs as the logged-in user (sees user-scoped NFS drive mappings). | Requires user to log in interactively after reboot. |
| NSSM (`nssm install MediaVortexWorker ...`) | Runs as service account, survives reboot without logon. | NFS drive mappings are per-user; the service account needs its own persistent mappings established once via `mount`/`net use` while logged in as that account. |

`StartWorker.py` (in the repo root) handles drive mounting in either option. **Recommended: Task Scheduler** for hosts that double as a workstation (REMINGTON), so the worker yields whenever the user logs off; **NSSM** for dedicated worker hosts.

### Register the Task Scheduler entry

Run `deploy\Register-WorkerTask.ps1` ON the worker host (not the dev workstation):

```powershell
cd C:\Code\MediaVortex
.\deploy\Register-WorkerTask.ps1
```

The script registers a task named `MediaVortex Worker` that:
- Triggers when the current user logs on
- Runs `<MediaVortex>\venv\Scripts\python.exe StartWorker.py` with `MediaVortex` as cwd
- Runs in the user's interactive context (so it inherits DPAPI / Credential Manager)
- Restarts up to 3 times on failure, 1 minute apart
- Stops automatically when the user logs off (interactive task scope)

Idempotent -- re-run after edits to overwrite the existing definition.

Verify, trigger manually, or unregister:

```powershell
Get-ScheduledTask -TaskName "MediaVortex Worker"
Get-ScheduledTaskInfo -TaskName "MediaVortex Worker"
Start-ScheduledTask -TaskName "MediaVortex Worker"
Unregister-ScheduledTask -TaskName "MediaVortex Worker" -Confirm:$false
```

## Troubleshooting

| Failure | Symptom | Resolution |
|---|---|---|
| Worker exits with `Required network drives not accessible: M:, T:, Z:` | Persistent mappings exist in `net use` but `Test-Path "T:\\"` returns False from a fresh session | NFS session isolation: persistent mappings reconnect at interactive logon only, not for SSH or Task Scheduler. Re-run `net use ... /persistent:yes` in the same session that launches the worker -- `StartWorker.py` does this automatically. |
| `mount` / `net use` to porky returns `System error 53` or `network path was not found` | NFS port 2049 unreachable from this host | Verify reachability: `Test-NetConnection 10.0.0.43 -Port 2049`. If the port is closed, check porky's NFS server status. If the port is open but the mount still fails, confirm the Windows NFS client feature is installed (`Get-WindowsOptionalFeature -Online -FeatureName ClientForNFS-Infrastructure`). |
| `Get-Disk -Number 0` reports "no MSFT_Disk objects found" but `Get-PhysicalDisk` shows the disk | Cannot initialize via PowerShell | Initialize via Disk Management UI (or `diskpart`) once; PowerShell sees the disk after that. Cause is a quirk in MSFT_Disk surfacing for raw SSDs. |
| `Workers.FFmpegPath = NULL` after registration | All transcode jobs fail with bland "Failed to build transcoding command" | Pre-`_ResolveBundledOrPathBinary` regression. Verify `FFmpegMaster\bin\ffmpeg.exe` exists in the repo (size ~190 MB). Reinstall by re-running the scp step. |
| FFmpeg pegs all logical cores despite `MEDIAVORTEX_MAX_CPU_THREADS=12` | `Get-Counter '\Processor(*)\% Processor Time'` shows every core at 100% | The env var sets FFmpeg `-threads` but SVT-AV1's internal worker pool ignores it. Use `-svtav1-params lp=12` if real thread limiting is required (would need a profile-level change). For the kids-PC use case, prefer reducing `MaxConcurrentJobs` or scheduling to off-hours instead. |
| psql fails because `psql` not installed on dev workstation | `psql: command not found` | Use the project's QueryDatabase.py: `cd C:\Code\MediaVortex && .\venv\Scripts\python.exe Scripts\SQLScripts\QueryDatabase.py sql "..."` |
| `Register-ScheduledTask` exits with `HRESULT 0x80070534` ("No mapping between account names and security IDs was done") | Workgroup-only Windows host: `$env:USERDOMAIN` returns the literal string `WORKGROUP`, which is not a real SID-resolvable principal | Register-WorkerTask.ps1 uses `$env:COMPUTERNAME\$env:USERNAME` as the task UserId; if that ever changes, restore that pattern. Do NOT use `$env:USERDOMAIN` -- on domain-joined hosts it works, on workgroup hosts it does not, and worker hosts are typically workgroup. |
| FFmpeg output `open()` returns EINVAL intermittently (`Error opening output ... .mp4.inprogress: Invalid argument`, return code 4294967274 / `TranscodeDurationSeconds=0`) | Two failure modes look identical from the FFmpeg log; check both in order. **(1)** Multiple WorkerService processes running concurrently against the same host -- `Stop-ScheduledTask` does not kill the spawned `python.exe`, so each restart cycle can leave a zombie. With two processes each honoring `Workers.MaxConcurrentRemuxJobs=N`, you get 2N concurrent CREATE() calls on the NFS export. The Microsoft NFS client returns EINVAL on a percentage of concurrent CREATEs (Linux clients against the same porky export show 0 failures). **(2)** `mtype=soft` mount with sub-second timeout returning EINVAL on transient slowness. | Verify only one `WorkerService\\venv\\Scripts\\python.exe Main.py` process exists (`Get-Process python*` + `Win32_Process.CommandLine -like "*MediaVortex*"`). If duplicates: `Stop-Process` all, then re-launch. Verify mount with `mount.exe` shows `mount=hard, rsize>=131072, wsize>=131072`. Drop `Workers.MaxConcurrentRemuxJobs` to 1-2 on Windows hosts -- the Microsoft NFS client cannot sustain the parallel-CREATE rate the Linux client manages. `MaxConcurrentJobs` controls transcode only; remux concurrency is the separate `MaxConcurrentRemuxJobs` column. |
| Inline PowerShell `-Command "..."` over SSH drops or merges quotes (`length : The term 'length' is not recognized as a cmdlet`) | The Bash/cmd/PS quote layers each strip a level of quoting; what the local shell sees is not what PS receives | Use `-EncodedCommand <base64>` with UTF-16-LE-encoded script bytes -- this carries the script through all three layers untouched. The deploy automation always uses this form for any inline PowerShell over SSH. Reserve `-File` for scripts that are already on the remote host. |
