# Flow: Windows Worker Deploy

Deploys a MediaVortex `WorkerService` instance natively on a Windows host (not Docker). Counterpart to `worker-deploy.flow.md` (Linux/Docker on the worker-pool LXC). Both deployment models coexist; this flow covers the Windows-native path used by I9-2024 and (as of 2026-05-09) REMINGTON.

## Entry Point

`scp` the repo from the dev workstation to the target Windows host, recreate the venv, set env vars, mount required SMB shares, run `WorkerService\Main.py`.

## When To Use This Flow

- Adding a new physical Windows workstation as a CPU-only transcode worker
- Re-deploying after a host rebuild
- Recovering from corrupted venv or stale env vars

For Linux containerized workers (which scale via `docker compose`), use `worker-deploy.flow.md` instead.

## Deploy Sequence (Quick Reference)

Run `deploy/deploy-windows-worker.py <target-ip>` from the dev workstation for the automated path. The script wraps every step below in order, idempotent. Manual sections in this doc remain canonical for one-off recovery and for understanding what the automation does.

| # | Step | Where | Owner |
|---|---|---|---|
| 1 | Pre-flight checks (Python, sshd, NetworkCategory, port reachability) | Worker host (queried over SSH) | `deploy-windows-worker.py --check` |
| 2 | scp the repo to `C:\Code\MediaVortex` | Dev workstation -> Worker | `scp -r ...` |
| 3 | Recreate venv (the source venv's `pyvenv.cfg` paths don't translate) | Worker host | `py -m venv venv && pip install -r requirements.txt` |
| 4 | Set `MEDIAVORTEX_DB_*` and `MEDIAVORTEX_*_PASSWORD` env vars at User scope | Worker host (creds piped via SSH stdin from dev-workstation vault) | `[Environment]::SetEnvironmentVariable(..., 'User')` |
| 5 | (Optional) Initialize a dedicated scratch volume as `S:`; set `Workers.StagingDirectory` post-registration | Worker host | Disk Management UI + DB UPDATE |
| 6 | Register the `MediaVortex Worker` Task Scheduler entry | Worker host | `deploy\Register-WorkerTask.ps1` |
| 7 | Trigger the task once to validate; future runs fire on user logon | Worker host | `Start-ScheduledTask -TaskName 'MediaVortex Worker'` |
| 8 | Verify the `Workers` row is Online with a recent heartbeat | Dev workstation (DB query) | `QueryDatabase.py sql ...` |

Expected timing on a host with a built venv and reachable network: full sequence completes in **~2-4 minutes**. Worker registration appears in the DB within **~10s** of triggering the task; first job claim within **~60s** of registration if the queue is non-empty.

## Pre-Flight Checks

| Check | Command | Required outcome |
|---|---|---|
| Python 3.12+ installed | `py --version` | Version 3.12.x |
| Git available (optional, for updates) | `git --version` | any |
| OpenSSH Server running | `Get-Service sshd` | Running, StartType Automatic |
| Network profile is Private (not Public) | `Get-NetConnectionProfile` | NetworkCategory = Private |
| Can reach DB | `Test-NetConnection 10.0.0.15 -Port 5432` | TcpTestSucceeded = True |
| Can reach Brain CIFS | `Test-NetConnection 10.0.0.40 -Port 445` | TcpTestSucceeded = True |
| Can reach Synology CIFS | `Test-NetConnection 10.0.0.61 -Port 445` | TcpTestSucceeded = True |

If `NetworkCategory = Public`, fix it before mounting drives or all SMB ops fail with system error 67:

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

## Optional: Dedicated Scratch Volume

If the host has an unmounted disk, dedicate it as `S:` for transcode staging so I/O does not contend with the OS drive. Initialize via Disk Management UI (or `diskpart`) when PowerShell `Get-Disk` cannot see the disk (a common quirk for raw SSDs reported by `Get-PhysicalDisk` but not surfaced in `Get-Disk`):

```powershell
# After Disk Management has initialized the disk to GPT and PowerShell can see it:
New-Partition -DiskNumber 0 -UseMaximumSize -DriveLetter S
Format-Volume -DriveLetter S -FileSystem NTFS -NewFileSystemLabel 'Scratch' -Confirm:$false
New-Item -ItemType Directory -Path 'S:\MediaVortex\Staging' -Force
```

Set `Workers.StagingDirectory = 'S:\MediaVortex\Staging'` in the DB row for this worker. The default falls back to `C:\MediaVortex\` which mixes transcode I/O with the OS drive.

## Build and Deploy Pipeline

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
- Resolves SMB and DB credentials from Vaultwarden via `infrastructure/terraform/secrets.py` (no plaintext on the command line, in the script, or in the operator's transcript)
- Pipes credential values through SSH stdin into a remote PowerShell `-EncodedCommand` block on the worker host (the only safe quoting strategy across Bash/PS/SSH layers; see Failure Modes for what happens if you try plain `-Command "..."`)
- Verifies the `Workers` row reaches `Status='Online'` with a heartbeat <60s old within 90s of triggering the task; exits non-zero if not
- Idempotent: each step has a "skip if already done" check, so re-running on a partially-deployed host completes only the missing steps

Manual deploy is still supported -- every section below documents the by-hand command equivalents the script wraps.

## Drive Mappings

The worker's Step 0 `_VerifyRequiredPaths()` reads `DISTINCT LEFT(FilePath,2)` from `MediaFiles` and verifies each prefix is accessible via `os.path.exists()`. If any required drive is missing the worker hard-fails before any DB writes. As of 2026-05-09 the prefixes in use are `T:`, `M:`, `Z:` (no `F:` despite being in `StartMediaVortex.py`).

| Letter | UNC | Server | User | Vault key for password |
|---|---|---|---|---|
| T: | `\\10.0.0.40\Media_tv` | Brain | `media` | `homelab/brain/cifs-media` |
| M: | `\\10.0.0.61\_video\Adults\Movies` | Synology | `jallen11` | `homelab/synology/jallen11` |
| Z: | `\\10.0.0.61\xxx` | Synology | `jallen11` | `homelab/synology/jallen11` |
| F: | `\\10.0.0.40\Media` | Brain | `media` | `homelab/brain/cifs-media` (only required for dev workstation, not transcode workers) |

Credentials live in the homelab Vaultwarden (`https://vault.jarremy.xyz`). Retrieve via the infrastructure repo's `terraform/secrets.py` helper or the `infra-vault` skill. Never paste the literal password into this repo, the worker host, or a chat transcript.

```powershell
# From the dev workstation (where bw is unlocked and BW_SESSION is set), pull the values:
cd C:\Code\infrastructure
$brainPwd = py terraform\secrets.py get homelab/brain/cifs-media
$synoPwd  = py terraform\secrets.py get homelab/synology/jallen11

# Then pipe to the target host. Mount within the SAME session that will launch WorkerService.
# Persistent mappings reconnect at interactive logon, but SSH sessions and Task Scheduler runs do NOT inherit them.
ssh owner@<target-ip> "powershell -Command @'
New-SmbMapping -LocalPath T: -RemotePath \\10.0.0.40\Media_tv -UserName media -Password $brainPwd -Persistent `$true
New-SmbMapping -LocalPath M: -RemotePath \\10.0.0.61\_video\Adults\Movies -UserName jallen11 -Password $synoPwd -Persistent `$true
New-SmbMapping -LocalPath Z: -RemotePath \\10.0.0.61\xxx -UserName jallen11 -Password $synoPwd -Persistent `$true
'@"
```

Use `New-SmbMapping`, not `net use` -- passing the password as a positional argument to `net use` over SSH frequently produces `system error 67` even when the share name is valid.

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

`StartWorker.py` resolves SMB credentials in this priority:
1. Env vars `MEDIAVORTEX_BRAIN_PASSWORD` / `MEDIAVORTEX_SYNOLOGY_PASSWORD` (set at User scope for non-interactive Task Scheduler use, or per-shell for ad-hoc testing).
2. Vault helper at `MEDIAVORTEX_VAULT_HELPER` (default `C:\Code\infrastructure\terraform\secrets.py`). Calls `<python> <helper> get <key>` and uses stdout. Requires the worker host to have the infrastructure repo, the `bw` CLI, and a DPAPI session cache (`tools\bw-cache-session.ps1`). Recommended -- no plaintext passwords on the host.
3. If neither yields a password for a required drive, the launcher exits with code 2.

Expected first-run sequence (visible in stdout / `Logs` table):

1. `_VerifyRequiredPaths()` confirms each `MediaFiles` drive prefix is accessible
2. `_RegisterAndLoadWorkerConfig()` resolves `FFmpegPath` from `FFmpegMaster\bin\ffmpeg.exe` (project-bundled) and UPSERTs the `Workers` row with `WorkerName = <hostname>`, `Status='Online'`, `LastHeartbeat=NOW()`
3. Health, status, and capability polling threads start
4. `MainLoop` blocks on `ShutdownEvent`
5. Within ~60 s the capability poller picks up `TranscodeEnabled=true` (default for new rows) and the transcode loop begins claiming jobs

## Smoke Test

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
| Task Scheduler "On user logon" | Simple, runs as the logged-in user (sees user-mounted drives, inherits DPAPI). | Requires user to log in interactively after reboot. |
| NSSM (`nssm install MediaVortexWorker ...`) | Runs as service account, survives reboot without logon. | Service account doesn't inherit user SMB mappings; needs system-wide mappings or in-startup mount; credentials must live in the SYSTEM-scoped Credential Manager or the service config. |

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

### Credential placement on the worker host

Pick one (DPAPI cache is the recommended steady state):

**Option A: DPAPI cache (recommended)** -- One-time setup, no plaintext passwords on disk:
1. Clone the infrastructure repo to `C:\Code\infrastructure`.
2. `npm install -g @bitwarden/cli`.
3. `bw login` (interactive, master password).
4. `cd C:\Code\infrastructure; .\tools\bw-cache-session.ps1` (interactive, master password again).
5. `StartWorker.py` will auto-resolve credentials via `secrets.py` on every launch.

**Option B: User env vars** -- Faster bootstrap, but passwords live in `HKCU\Environment` (plaintext registry, scoped to user):
```powershell
# On the worker host, paste from `py terraform\secrets.py get ...` on the dev workstation:
[Environment]::SetEnvironmentVariable('MEDIAVORTEX_BRAIN_PASSWORD','<value>','User')
[Environment]::SetEnvironmentVariable('MEDIAVORTEX_SYNOLOGY_PASSWORD','<value>','User')
```

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| `system error 67` mounting any SMB share | `net use` reports "network name cannot be found" despite TCP 445 open | NetworkCategory is Public on the active NIC. `Set-NetConnectionProfile -InterfaceAlias <alias> -NetworkCategory Private`. Public profile blocks SMB client behavior even when port is reachable. |
| Worker exits with `Required network drives not accessible: M:, T:, Z:` | Persistent mappings show in `Get-SmbMapping` but `Test-Path "T:\\"` returns False from a fresh session | SMB session isolation: persistent mappings reconnect at interactive logon only, not for SSH or Task Scheduler. Re-establish via `New-SmbMapping` (without `-Persistent`) in the same session that launches the worker, or use a launcher script. |
| `Get-Disk -Number 0` reports "no MSFT_Disk objects found" but `Get-PhysicalDisk` shows the disk | Cannot initialize via PowerShell | Initialize via Disk Management UI (or `diskpart`) once; PowerShell sees the disk after that. Cause is a quirk in MSFT_Disk surfacing for raw SSDs. |
| `Workers.FFmpegPath = NULL` after registration | All transcode jobs fail with bland "Failed to build transcoding command" | Pre-`_ResolveBundledOrPathBinary` regression. Verify `FFmpegMaster\bin\ffmpeg.exe` exists in the repo (size ~190 MB). Reinstall by re-running the scp step. |
| FFmpeg pegs all logical cores despite `MEDIAVORTEX_MAX_CPU_THREADS=12` | `Get-Counter '\Processor(*)\% Processor Time'` shows every core at 100% | The env var sets FFmpeg `-threads` but SVT-AV1's internal worker pool ignores it. Use `-svtav1-params lp=12` if real thread limiting is required (would need a profile-level change). For the kids-PC use case, prefer reducing `MaxConcurrentJobs` or scheduling to off-hours instead. |
| `net use` over SSH fails despite correct credentials | system error 67 even on shares known to be valid | Use `New-SmbMapping` instead. The `net use \\host\share /user:USER PASSWORD` positional-password syntax frequently breaks through SSH. |
| psql fails because `psql` not installed on dev workstation | `psql: command not found` | Use the project's QueryDatabase.py: `cd C:\Code\MediaVortex && .\venv\Scripts\python.exe Scripts\SQLScripts\QueryDatabase.py sql "..."` |
| `cmdkey /add:<host> ...` over SSH returns `Credentials cannot be saved from this logon session` | Trying to stash SMB creds in Credential Manager from an SSH session for the DPAPI-cache path | Windows blocks credential-store writes from Network-logon sessions (which is what SSH establishes). The fix is to run `deploy\Bootstrap-WorkerCreds.ps1` from RDP or the physical console, OR fall back to User-scope env vars (which CAN be set over SSH). The deploy automation defaults to the env-var path for this reason. |
| `Register-ScheduledTask` exits with `HRESULT 0x80070534` ("No mapping between account names and security IDs was done") | Workgroup-only Windows host: `$env:USERDOMAIN` returns the literal string `WORKGROUP`, which is not a real SID-resolvable principal | Register-WorkerTask.ps1 uses `$env:COMPUTERNAME\$env:USERNAME` as the task UserId; if that ever changes, restore that pattern. Do NOT use `$env:USERDOMAIN` -- on domain-joined hosts it works, on workgroup hosts it does not, and worker hosts are typically workgroup. |
| Inline PowerShell `-Command "..."` over SSH drops or merges quotes (`length : The term 'length' is not recognized as a cmdlet`) | The Bash/cmd/PS quote layers each strip a level of quoting; what the local shell sees is not what PS receives | Use `-EncodedCommand <base64>` with UTF-16-LE-encoded script bytes -- this carries the script through all three layers untouched. The deploy automation always uses this form for any inline PowerShell over SSH. Reserve `-File` for scripts that are already on the remote host. |
