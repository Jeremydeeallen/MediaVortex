# BUG-0008 -- I9 NFS EINVAL on FFmpeg output-open (Troubleshooting log)

**Read this BEFORE investigating BUG-0008.** Every prior `/t` pass has lost context and re-litigated hypotheses the operator already ruled out. Anchor on this file. Do NOT propose theories that contradict the Confirmed Facts section without first re-reading it.

## Confirmed Facts (operator-asserted, do not re-question)

1. **Failures occur ONLY on I9-2024.** Linux workers (larry-worker-2/3/4) writing to the same porky NFS export at `\\10.0.0.43\srv\nfs-media-_tv` show ZERO `return code 4294967274` (EINVAL) failures over the last 24 hours. Same export, same files, same FFmpeg version family. The defect is host-local to I9.

2. **It is NOT concurrency.** Operator ran I9 with a single worker (concurrency = 1, one in-flight FFmpeg at a time) and the EINVAL failures still occur intermittently. Any hypothesis that requires N>1 simultaneous CREATE() is wrong. Stop reaching for it.

3. **It is NOT multi-NIC routing.** Operator unplugged one NIC on 2026-05-22; I9 is now reachable only on the .7 IP (single NIC active). EINVAL failures continue. H1 ruled out by physical test. Stop reaching for routing/source-IP/asymmetric-path theories.

4. **Worker log lines accompanying every failure** (logged 2026-05-22, post-NIC-unplug):
   ```
   WARNING: Shell process PID NNNN not found
   WARNING: Failed to set CPU affinity: Shell process PID NNNN not found
   ERROR: FFmpeg stdout: ffmpeg version ...
   ...
   [out#0/mp4 @ 0x...] Error opening output T:\...mp4.inprogress: Invalid argument
   ```
   The "Shell process PID not found" warning indicates the worker spawned ffmpeg via `subprocess` with a shell wrapper (cmd.exe), captured the shell PID, then attempted to set CPU affinity on it via psutil; psutil could not find that PID because cmd.exe had already exited. This is consistent with FFmpeg failing within milliseconds (0.0s `TranscodeDurationSeconds`). The warning is a SYMPTOM of fast ffmpeg failure, not necessarily the cause -- but the **shell-wrapper invocation pattern itself** is now a hypothesis (H5).

5. **Windows Defender real-time protection is OFF on I9.** Operator captured 2026-05-22: `Get-MpPreference` returns `DisableRealtimeMonitoring: True`. Existing exclusion paths include `\\allen\games`, `C:\Code`, `C:\Code\ZenScan\zenscan`, `C:\Games` but NOT `T:\`, `M:\`, `Z:\`. With RTP disabled, Defender's `WdFilter` does not intercept CreateFile on the NFS drives at all. Defender-specific form of H2 is ruled out. (Other filter drivers may still be loaded; `fltmc filters` output pending.)

8. **T: drive disappears from sessions intermittently on I9 (BREAKTHROUGH 2026-05-22).** Operator demonstrated by direct test: in a PowerShell window, typing `t:` sometimes works and sometimes fails with "Cannot find drive." When T: is missing, any process in that session that tries to CreateFile on T: gets EINVAL (Win32 87 -- the NFS redirector's way of saying "drive letter not bound right now"). When T: is present, CreateFile succeeds normally. This explains every confirmed fact:
   - **Only I9:** Linux has no per-session drive-letter concept; mounts there are global to the kernel.
   - **Not concurrency:** when T: is gone, every job fails regardless of how many are in flight; when T: is up, every job succeeds. The "intermittent 50%" is actually "T: is up... T: is down..."
   - **NIC unplug didn't help:** the network is fine; the drive-letter binding is what's flapping.
   - **brain -> porky migration is the cause:** SMB mappings on Windows are very durable and auto-reconnect transparently. NFS via the Microsoft NFS client is session-bound and far more fragile. Pre-migration, I9 was on SMB; post-migration, I9 is on NFS. The protocol change exposed the session-binding fragility.

   **EINVAL is not a bug in ffmpeg or in the worker.** It is the correct Windows error code for "you asked CreateFile to open a path on a drive letter that is no longer bound to your session." All the prior hypotheses about ffmpeg flags, shell=True, AV scanners, etc. were chasing symptoms.

   The fix is to keep T: bound durably for the worker process, or to bypass the drive letter entirely.

9. **UNC paths fail with EINVAL too (BIG REVISION 2026-05-22, post-fix).** After the worker code was switched to use UNC paths via `StorageRootResolutions`, `TranscodeAttempts.FfpmpegCommand` rows confirmed UNC strings are reaching ffmpeg. Yet the same EINVAL `4294967274` keeps appearing intermittently:
   - 20183 17:07:21 SUCCESS UNC
   - 20219 17:16:40 **FAIL UNC** -- `Error opening output \\10.0.0.43\srv\nfs-media-_tv\...\My Life as a Teenage Robot - S03E08 - Enclosure of Doom DVD-mv.mp4.inprogress: Invalid argument`
   - 20226 17:16:59 **FAIL UNC** -- Riverdale S07E03, same shape
   - 20267 17:22:09 SUCCESS UNC
   - 20283/20284/20285 17:27:03-05 **FAIL UNC**

   Mixed success/failure on the SAME ffmpeg command shape, SAME export, SAME machine, in successive seconds. This kills the simple "drive letters were the only fragile layer" theory. **The Microsoft NFS client / NFS redirector itself is the unstable component.** Drive-letter session binding was real but it was a downstream symptom of the underlying instability, not the root cause. Bypassing drive letters is still a correctness win (no Pause-style "T: doesn't exist" hard fails) but it does NOT fix the intermittent CreateFile EINVAL.

   Linux workers against the same porky export show ZERO failures. The defect is Windows-client-side and survives any in-app path-shape change.

7. **Windows NFS drive letters are per-logon-session on I9.** Operator ran the layer-isolation repro from elevated PowerShell (`C:\WINDOWS\system32`, "Run as administrator"); `New-Item -Path T:\...` returned `Cannot find drive. A drive with the name 'T' does not exist.` The worker process, running in the operator's interactive (non-elevated) session, sees T: normally and writes successfully most of the time. **The T: drive mapping is bound to a specific logon session ID (LUID).** Implications:
   - Repro tests MUST run either from the operator's interactive session (non-elevated PowerShell) or via UNC path `\\10.0.0.43\srv\nfs-media-_tv\...` to bypass the drive letter.
   - The worker holding a session-bound mapping for hours/days could see its mapping invalidate on any session token change (lock screen, fast-user-switching, scheduled token refresh, group-policy refresh that touches the user's token). Each subsequent CreateFile via T: would hit a stale handle and return EINVAL. This is an H0 sub-hypothesis (H0b) to investigate after the UNC-path repro.

6. **Recent infrastructure change: brain -> porky migration retired SMB on I9, but the planned SMB-on-porky replacement never landed.** Commit `79a02f3 chore(deploy): retire SMB, complete brain -> porky migration` flipped I9's media share access from SMB-to-brain to **NFS-to-porky**. The infrastructure repo's `docs/features/brain-porky-media-migration.md` (lines 126, 181-182, 369, 610, 632) shows the actual plan was SMB-to-brain -> **SMB-to-porky** (`New-SmbMapping` against Porky, persistent). Porky's `smbd` is currently `inactive` -- SMB on porky was never stood up. The Windows worker was put on a stack (Microsoft NFS client -> Linux kernel nfsd via porky's vmbr0 / 10.0.0.43) that the migration doc did NOT plan for and that was never validated. Remote Linux workers (larry LXC, wakko + dot bare-metal Linux) stayed on NFS to porky where they had been before -- which is why they did not regress. **This is not a regression from a previously-working NFS stack; it is an untested combination introduced as an undocumented departure from the migration plan.** That elevates the "switch back to SMB" option from "rollback" to "complete the migration as originally designed."

## What the symptom looks like

- FFmpeg exits with return code 4294967274 (= signed -22 = `EINVAL`)
- `TranscodeDurationSeconds = 0.0`
- FFmpeg stdout shows full input-stream metadata, then dies on output `open()`:
  ```
  [out#0/mp4 @ 0x...] Error opening output T:\...-mv.mp4.inprogress: Invalid argument
  Error opening output file ...
  Error opening output files: Invalid argument
  ```
- Same FFmpeg command, run manually from an interactive shell on I9, works.
- Affects both Remux (stream-copy) and Transcode (libsvtav1) jobs equally -- so it is not a codec or muxer issue.
- Not blocked on input read: FFmpeg reads the source from the same NFS mount cleanly before failing at output create.

## Ruled out (do not re-investigate)

- ~~Soft-mount with sub-second timeout~~ -- mount is `mtype=hard, timeout=10, rsize=1048576, wsize=1048576` on T:; `rsize=131072` on M:/Z:. Verified via `mount.exe`. Hard mount did not cure it.
- ~~Two WorkerService python processes (zombie pair)~~ -- the parent/child python.exe pair on Windows is the standard venv launcher pattern, not a zombie. Verified by `Get-CimInstance Win32_Process`: the parent (`ParentProcessId=<shell>`, low CPU, 1 thread, ~4 MB) is a stub; the child (`ParentProcessId=<parent>`, real CPU, many threads, tens of MB) is the running interpreter. WebService shows the identical pattern. Killing the "parent" kills the worker.
- ~~Stale `.inprogress` file from a prior crashed attempt~~ -- verified absent at the failure path (`Test-Path` returns False before the next retry).
- ~~`-f mp4` muxer auto-detect~~ -- BUG-0005 fix is in place; command builds correctly.
- ~~Concurrent CREATE() race in the Microsoft NFS client~~ -- failures occur at concurrency=1.

## What is actually failing

The whole failure is a single Windows syscall: `CreateFile(T:\<dir>\<basename>.mp4.inprogress, GENERIC_WRITE, ...)` returning `ERROR_INVALID_PARAMETER` (Win32 87). libavformat catches that as `AVERROR(EINVAL)` (-22). The worker prints the unsigned form `4294967274`. Everything else (FFmpeg stderr, CPU-affinity warning, queue removal) is downstream of that one syscall returning an error.

This means **the bug is reproducible without ffmpeg.** Any tool that performs an equivalent `CreateFile` on T:/M:/Z: should hit it.

## Layer-isolation repro (RUN BEFORE INVESTIGATING H0 FURTHER)

A 30-second PowerShell test splits the search space cleanly between "the NFS client mishandles CreateFile" (H0) and "something about ffmpeg's specific CreateFile call" (H5/H6):

```powershell
$root = "T:\__bug0008-repro"
New-Item -ItemType Directory -Path $root -Force | Out-Null
$fail = 0; $ok = 0
1..200 | ForEach-Object {
  $p = "$root\test-$_.mp4.inprogress"
  try {
    $fs = [System.IO.File]::Create($p)
    $fs.Close()
    Remove-Item $p -ErrorAction SilentlyContinue
    $ok++
  } catch {
    $fail++
    Write-Host "FAIL $_ : $($_.Exception.Message)"
  }
}
"OK=$ok FAIL=$fail"
```

Outcomes:

- **FAIL > 0** -> H0 confirmed at the protocol level. ffmpeg is innocent. Investigation pivots to porky exports vs brain's old config, Windows NFS client registry params, and mount options.
- **FAIL = 0 in 200 iterations** -> the simple CreateFile path works. Promote H5 (shell wrapper) + H6 (ffmpeg-specific access mask / share mode / multi-extension). Capture ffmpeg's actual CreateFile parameters with Process Monitor filter `Path contains .mp4.inprogress AND Operation = CreateFile`.
- **FAIL = 0 BUT the worker is idle during the test** -> inconclusive. Re-run while remuxes are actively executing to test under the same load conditions.

Variants worth running once the baseline establishes a positive:
- `T:\TEMP\test-N.mp4` (single extension, fresh path) vs `T:\<existing show folder>\test-N.mp4.inprogress` (multi-dot, in a deep path the NFS client has cached attrs for). If only the second form fails, the multi-dot extension or the cached-dir attr interaction is the trigger.
- Same loop on `M:` and `Z:` -- isolates whether porky-specifically or any NFS export triggers it.
- Same loop but with `[System.IO.File]::Open($p, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)` -- approximates ffmpeg's share-mode.

### H7 -- The brain -> porky migration changed the NFS server, and porky's export shape interacts badly with the Microsoft NFS client (LEADING HYPOTHESIS post-2026-05-22 UNC verdict)

Linux workers against porky's exports: ZERO failures across hours of load. I9 against the SAME exports: intermittent EINVAL on CreateFile, persists through every client-side workaround attempted. The asymmetry isolates the defect to the Microsoft NFS client's handling of something porky does (or doesn't do) that brain did differently.

Things to audit that the brain -> porky migration may have flipped:

| Variable | Brain (pre-migration) | Porky (current) | Why it matters to the Microsoft NFS client |
|---|---|---|---|
| **NFS server software** | Unknown (Synology builtin? Custom?) | Linux kernel `nfs-kernel-server` | Different default OPEN/CREATE response shapes; Microsoft client tolerates one and rejects the other as EINVAL. |
| **NFS protocol versions advertised** | Unknown | Likely v3 + v4 + v4.1 + v4.2 (kernel defaults) | Microsoft NFS client speaks v2/v3 only. Failed v4 negotiation can leave the client in a confused state; certain v4-specific server behaviors break v3 fallback for ops like CREATE_EXCLUSIVE. |
| **`/etc/exports` options** | Unknown | TBD -- need to read | `subtree_check`/`no_subtree_check`, `sync`/`async`, `wdelay`/`no_wdelay`, `crossmnt`, `fsid` all change wire behavior. Microsoft client is finicky about `subtree_check` because it relies on file handles being stable across renames. |
| **Squash policy** | Unknown | TBD | If `root_squash` is on (default) and the Windows client mounts with `anon`, the server maps to `nobody` which may lack write permission on certain subtrees. Linux client's UID mapping differs. |
| **Filesystem under export** | NTFS via Synology / btrfs / ZFS | TBD (likely ZFS or ext4 on porky) | Some filesystems return ENOENT->EINVAL chains the Windows client mistranslates. ZFS in particular has subtle behavior with file CREATE inside directories that have pending writes. |
| **NFS lock daemon (`lockd`/`nlm`)** | Unknown | Kernel `lockd` enabled by default | Microsoft client requests NLM locks on every CREATE. If porky's lockd is slow / mis-bound / blocked by firewall, CreateFile times out and translates to EINVAL on retry. |
| **Network MTU / jumbo frames** | Unknown | TBD | MTU mismatch between client (1500) and server (9000) on a switch port can fragment large NFS WRITE/READ ops; Windows handles fragmentation poorly. |
| **`anonuid`/`anongid`** | Unknown | TBD | Different "nobody" UID on porky vs brain changes who owns the .inprogress file post-create, which can cascade to permission failures on subsequent writes. |

Diagnostic commands to run on porky (no service impact):

```bash
ssh root@porky 'cat /etc/exports'
ssh root@porky 'cat /proc/fs/nfsd/versions'
ssh root@porky 'exportfs -v'
ssh root@porky 'cat /etc/nfs.conf 2>/dev/null; cat /etc/default/nfs-kernel-server 2>/dev/null'
ssh root@porky 'rpcinfo -p localhost | grep -E "nfs|mountd|nlockmgr"'
ssh root@porky 'systemctl status nfs-server nfs-kernel-server lockd 2>&1 | head -40'
```

Diagnostic on I9 (Microsoft NFS client state):

```powershell
# Client mount options actually negotiated (already partially captured -- mount=hard, rsize=1048576, etc.)
mount.exe

# NFS client version + last update
Get-WindowsOptionalFeature -Online -FeatureName ServicesForNFS-ClientOnly, ClientForNFS-Infrastructure
Get-WindowsOptionalFeature -Online | Where-Object FeatureName -like '*NFS*'
Get-HotFix | Where-Object { $_.HotFixID -like 'KB*' } | Sort-Object InstalledOn -Descending | Select-Object -First 5

# Client-side cached settings registry
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\ClientForNFS\CurrentVersion\Default' -ErrorAction SilentlyContinue

# Active Windows version (NFS client behavior changed across Win11 minor updates)
[System.Environment]::OSVersion
(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').DisplayVersion
(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').UBR
```

**Porky network audit (2026-05-22, captured during investigation):**

- Active uplink: single NIC `nic4` -> `vmbr0` -> `10.0.0.43/24`, MTU 1500, 513 dropped RX out of 2.1B packets (noise floor). Default route via 10.0.0.1.
- `vmbr1` (10.0.2.2/24) configured but DOWN -- intended backplane never connected; not relevant to this bug.
- Other physical NICs (ens2f0/f1, nic0-3, nic5) all DOWN.
- NFS listeners: TCP/UDP 111 (portmap), TCP 2049 (nfsd v3 + v4), mountd + nlockmgr + status on dynamic high ports.
- **`/proc/fs/nfsd/versions` = `+3 +4 +4.1 +4.2`** -- ALL versions enabled. Microsoft NFS client only speaks v2/v3. Negotiation against a v4-preferring server is a known fragility for the MS client.
- `/etc/exports` for `/srv/nfs-media-_tv`, `/srv/nfs-media-_xxx`, `/srv/nfs-media-_movies` all use identical options: `sync, wdelay, hide, no_subtree_check, sec=sys, rw, no_root_squash, no_all_squash`. Conservative, matches what Linux workers consume without issue.
- No iptables / ufw rules (INPUT ACCEPT default).
- **`smbd` is `inactive`.** SMB on porky is OFF. The planned SMB replacement for brain's SMB never happened.

### Recommended fixes (in order of preference)

**A. Restore SMB on porky for Windows workers (matches the original migration plan).**
Stand up Samba on porky exporting `/srv/nfs-media-_tv`, `/srv/nfs-media-_movies`, `/srv/nfs-media-_xxx`. Have I9 use SMB UNCs (`\\10.0.0.43\TV\...`) instead of NFS. Linux containers stay on NFS unchanged. SMB is the most-tested network filesystem on Windows; the Microsoft NFS client's CreateFile fragility goes away entirely. Owned by the `infrastructure` repo (brain-porky-media-migration feature) since the SMB-on-porky setup is what the migration doc already specified.

**B. Disable NFSv4 on porky and force pure v3 server-side (cheap test).**
Edit `/etc/nfs.conf` or `/etc/default/nfs-kernel-server` on porky:
```
[nfsd]
vers3=y
vers4=n
vers4.0=n
vers4.1=n
vers4.2=n
```
Then `systemctl restart nfs-server`. Verify with `cat /proc/fs/nfsd/versions` showing `+3 -4 -4.1 -4.2`. Reboot I9 (or remount T:/M:/Z:) to force fresh NFS connections. If EINVAL stops, version-negotiation drift in the MS client was the trigger. Reversible by un-commenting the v4 lines and restarting. Linux clients will continue working on v3.

**C. Worker-side retry-on-EINVAL (symptom treatment).**
Add a retry layer in `Features/TranscodeJob/VideoTranscodingService.py` that catches return code 4294967274 and retries the same ffmpeg command once after a 1-second jitter. Treats the symptom; does not fix the underlying Microsoft NFS client instability. Acceptable as a band-aid while A is being implemented.

Cross-check from a known-good Linux worker (e.g. larry-worker-1) for comparison:

```bash
ssh root@larry "pct exec 218 -- docker exec mediavortex-worker-1-1 sh -c 'mount | grep media_tv; nfsstat -m'"
```

The diff between Linux's mount options + negotiated NFS version and Windows' equivalent is the most likely source of the answer.

### H6 -- ffmpeg's CreateFile uses access flags or share mode the Microsoft NFS client mishandles

ffmpeg's `avio_open` ultimately calls Windows `_wfopen` -> `CreateFileW` with `GENERIC_WRITE | GENERIC_READ`, `FILE_SHARE_READ`, `CREATE_ALWAYS`, `FILE_ATTRIBUTE_NORMAL`. Any of these may interact poorly with the Microsoft NFS client when the file does not yet exist on the server. Promoted to active hypothesis only if the layer-isolation repro returns `FAIL = 0`.

## Pre-commit verification: UNC stability (CURRENT STEP)

Root cause confirmed: drive-letter T: intermittently unbinds from the worker's session; ffmpeg CreateFile on T: returns EINVAL when T: is gone. Fix direction: convert the worker's path handling to UNC (`\\10.0.0.43\srv\nfs-media-_tv\...` for porky, `\\10.0.0.61\...` for Synology), bypassing drive letters entirely. UNC routes through MUP -> NFS redirector and is not session-bound. Confirmed 2026-05-22: porky's SMB is OFF (`smbd inactive`, no listener on 445/139), so the previous 200/200 UNC test went through NFS, not SMB -- direct proof UNC-over-NFS is stable on this exact box.

Before committing the code change, run three tests to verify the fix direction holds across all three shares, end-to-end with ffmpeg, and under live worker load. Order is fastest-first.

### Test A -- UNC parity across all three shares (5 min)

We proved porky behaves; we have not proved Synology does. Different NFS server, different stack.

```powershell
$shares = @(
  @{ Label="porky-tv";     Unc="\\10.0.0.43\srv\nfs-media-_tv" },
  @{ Label="synology-mov"; Unc="\\10.0.0.61\volume1\_video\Adults\Movies" },
  @{ Label="synology-xxx"; Unc="\\10.0.0.61\volume2\XXX" }
)
foreach ($s in $shares) {
  $root = Join-Path $s.Unc "__bug0008-repro"
  New-Item -ItemType Directory -Path $root -Force | Out-Null
  $ok = 0; $fail = 0
  1..200 | ForEach-Object {
    $p = Join-Path $root "test-$_.mp4.inprogress"
    try { $fs = [System.IO.File]::Create($p); $fs.Close(); Remove-Item $p -Force; $ok++ }
    catch { $fail++; if ($fail -le 3) { Write-Host "$($s.Label) FAIL $_ : $($_.Exception.Message)" } }
  }
  "$($s.Label): OK=$ok FAIL=$fail"
}
```

Pass: all three lines say `OK=200 FAIL=0`. If Synology fails, UNC isn't a universal fix and each share needs separate treatment.

### Test B -- actual ffmpeg over UNC, 10 iterations (5 min)

Replicates the worker's exact failure with only the path scheme changed.

```powershell
$ffmpeg = "C:\Code\MediaVortex\FFmpegMaster\bin\ffmpeg.exe"
$inUnc  = "\\10.0.0.43\srv\nfs-media-_tv\South Park\Season 5\South Park - S05E14 - Butters' Very Own Episode WEBDL-480p.mkv"
$outDir = "\\10.0.0.43\srv\nfs-media-_tv\South Park\Season 5"
$ok = 0; $fail = 0; $rcs = @()
1..10 | ForEach-Object {
  $out = Join-Path $outDir "bug0008-test-$_.mp4.inprogress"
  & $ffmpeg -loglevel error -y -i $inUnc -map 0:v:0 -map 0:a:0 -c:v copy -c:a copy -f mp4 -movflags +faststart $out 2>$null
  $rcs += $LASTEXITCODE
  if ($LASTEXITCODE -eq 0) { $ok++; Remove-Item $out -Force -ErrorAction SilentlyContinue }
  else { $fail++; Write-Host "iter $_ rc=$LASTEXITCODE" }
}
"OK=$ok FAIL=$fail  rcs=$($rcs -join ',')"
```

Pass: `OK=10 FAIL=0`. Any `4294967274` exit code means UNC has the same problem and the hypothesis is wrong.

### Test C -- UNC vs drive-letter side-by-side under live worker load (15 min wall clock)

Strongest test. While the worker is actively running and intermittently failing on T:, a parallel UNC loop should NEVER fail.

Two PowerShell windows, both non-elevated in the operator's interactive session.

Window 1 (drive-letter presence monitor):

```powershell
1..600 | ForEach-Object {
  $t = if (Test-Path "T:\") { "UP" } else { "DOWN" }
  "$(Get-Date -Format 'HH:mm:ss.fff') T:=$t" | Add-Content C:\Code\MediaVortex\bug0008-driveletter.log
  Start-Sleep -Seconds 1
}
```

Window 2 (UNC create-loop):

```powershell
$root = "\\10.0.0.43\srv\nfs-media-_tv\__bug0008-repro"
New-Item -ItemType Directory -Path $root -Force | Out-Null
$ok = 0; $fail = 0
1..600 | ForEach-Object {
  $p = "$root\test-$_.mp4.inprogress"
  try { $fs = [System.IO.File]::Create($p); $fs.Close(); Remove-Item $p -Force; $ok++ }
  catch { $fail++ }
  "$(Get-Date -Format 'HH:mm:ss.fff') UNC=$(if($?){"OK"}else{"FAIL"}) running:ok=$ok fail=$fail" | Add-Content C:\Code\MediaVortex\bug0008-unc.log
  Start-Sleep -Seconds 1
}
"UNC final: OK=$ok FAIL=$fail"
```

Pass:
- UNC log final line `OK=600 FAIL=0`
- Drive-letter log has at least one `T:=DOWN` entry
- `TranscodeAttempts` has at least one `4294967274` failure in that 10-minute window
- Drive-letter `DOWN` timestamps correlate with worker failure timestamps (within ~2s)
- UNC log shows OK during every `DOWN` window

That correlation is the proof: same machine, same NFS server, same moment, UNC stays up while drive letter drops.

### Decision

- A + B pass -> safe to commit the worker code change to UNC.
- A passes, B fails -> the issue may be ffmpeg-specific to UNC paths on Windows (rare but possible); investigate before committing.
- A fails on Synology -> need a per-share strategy; do not commit a uniform UNC rewrite.
- C is the rigorous proof for the closing argument and the BUG-0008 verification criterion.

### Fix is owned by a separate feature doc

The code change is documented as a data-driven feature in `WorkerService/windows-unc-path-translation.feature.md`. That doc owns the success criteria, scope, and progress checklist for the work. Do not duplicate criteria here -- this troubleshooting doc closes once BUG-0008 criterion 4 holds; the feature doc closes when all of its criteria hold.

## Earlier next-test (superseded but retained for context): shell=True vs shell=False isolation

Three steps to determine whether the `shell=True` cmd.exe wrapper is the cause (H5) or ffmpeg's own CreateFile is the cause (H6). About 5 minutes end-to-end.

**Step 1 -- capture one failing ffmpeg command.** From any PowerShell window:

```powershell
cd C:\Code\MediaVortex
.\venv\Scripts\python.exe Scripts\SQLScripts\QueryDatabase.py sql "SELECT FfpmpegCommand FROM TranscodeAttempts WHERE WorkerName='I9-2024' AND Success=false AND ErrorMessage LIKE '%4294967274%' ORDER BY Id DESC LIMIT 1"
```

Paste the `ffpmpegcommand` value to the troubleshooting session (or save it inline in this doc under "## Investigation log" as the captured command for this iteration).

**Step 2 -- create `Scripts\Bug0008Repro.py`** that runs the captured command 20 times via `subprocess.run(cmd_string, shell=True)` and 20 times via `subprocess.run(cmd_list, shell=False)`, printing OK/FAIL counts per mode. The output filename in the captured command must be made unique per iteration (append the iteration index before `.inprogress`) so successful runs don't accumulate on the share. After each iteration, delete the produced output file. Treat any non-zero exit code as FAIL; capture stderr's last 200 chars on FAIL.

**Step 3 -- run it from a non-elevated PowerShell in the operator's interactive session** (so T: is visible):

```powershell
cd C:\Code\MediaVortex
.\venv\Scripts\python.exe Scripts\Bug0008Repro.py
```

Expected output shape: `shell=True: OK=X FAIL=Y / shell=False: OK=X FAIL=Y`. Paste the result to the troubleshooting session and append it as an Investigation log entry. The worker can be running or stopped during this test -- load is not a factor (per Investigation log 2026-05-22 entry on load).

**Outcome decoder:**
- shell=True fails intermittently, shell=False passes 20/20 -> **H5 confirmed**. Fix: modify the worker's subprocess invocation to pass a tokenized command list and `shell=False`. Done.
- Both fail -> **H6 confirmed**. ffmpeg's own CreateFile is at fault regardless of launcher. Investigation pivots to ffmpeg build flags, the avformat CreateFile call site, and possibly a Process Monitor trace of the CreateFile parameters.
- Both pass 20/20 -> ffmpeg-from-Python works in both modes from interactive Python, but ffmpeg-from-the-worker fails. There is a third factor specific to the worker process itself (env vars, working directory, inherited handles, the wrapper's `cmd /c` quoting). Capture the worker's env vars vs the test script's, and run the test from inside the worker process (add a `--diagnostic-loop` flag to `StartWorker.py`).

## Active hypotheses (in evidence-strength order)

### H0 -- I9's protocol switch from SMB to NFS (brain -> porky migration) introduced an untested CreateFile path (LEADING HYPOTHESIS, pending layer-isolation repro)

The brain -> porky infrastructure migration retired SMB on I9 and replaced it with the Microsoft NFS client. Before the migration, I9 had years of operator-validated SMB writes against the TV share. After the migration, every `CreateFile()` from I9 to T:/M:/Z: goes through the Microsoft NFS client (`nfsnp` redirector + `mount.exe` user-mode mappings + AUTH_SYS over TCP 2049). The Microsoft NFS client is known to be far less robust than the Linux NFS client for CreateFile-heavy workloads with multi-dot extensions (e.g. `<basename>.mp4.inprogress`).

Why this fits all confirmed facts better than anything else tried:
- **Only on I9:** Linux workers were always on NFS; their client implementation is unchanged. Only I9 changed protocols.
- **Not concurrency:** protocol-level CreateFile semantics fail per-call, not per-N.
- **Not multi-NIC:** the NIC unplug ruled out a network-path issue. This is a layer-above-network issue.
- **Intermittent at concurrency=1:** consistent with the Microsoft NFS client's known fragility on specific path shapes / option combinations / handle-cache states.
- **Not Defender:** RTP is off; the filter-driver intercept does not exist.

**Diagnose -- the deltas to nail down (commit `79a02f3` and predecessors):**
1. What did the **old** brain SMB mount on I9 look like? Drive letter, UNC, credentials, persistence. Compare to current `mount.exe -o mtype=hard ...` form.
2. What does **porky's `/etc/exports`** look like for `srv/nfs-media-_tv`? Squash policy, sync/async, sec mode, fsid, hide/nohide. Compare to brain's exports for the same share (if recoverable from infra repo git history).
3. What does the **infrastructure repo** say about the migration? Look at `infrastructure/terraform/` and any migration scripts authored alongside `79a02f3`. The intent there is the canonical spec; deltas in either direction are suspect.
4. Was the porky export ever tested from Windows with this workload before I9 was cut over? If not, this is the first time the combo was exercised; the bug is the symptom of insufficient burn-in, not of a regression in either component alone.

**Fix candidates if H0 confirmed:**
- (A) Re-export the share with options that the Microsoft NFS client tolerates better -- e.g. add `no_subtree_check`, set explicit `anonuid`/`anongid` matching the file owner, switch to `sync` if currently `async` (or vice versa), test each in isolation.
- (B) Restore SMB on I9 as a parallel mount and route Windows worker writes through it (Linux workers stay on NFS). Documented as retired in `79a02f3`; the question is whether the retirement was premature.
- (C) Bypass the Microsoft NFS client entirely: install `WSL2` on I9 and run the WorkerService inside a Linux container that mounts NFS via the Linux client. Heavier intervention; worth it only if (A) and (B) are blocked.

### H2 -- Antivirus / file-system filter driver intercept on CREATE() (RTP-disabled subset only)

Windows Defender (or any AV) hooks every `CreateFile()` and can return EINVAL on a small percentage when its scanner can't classify the file fast enough. Linux workers do not have this layer. Single-threaded I9 still hits it because it is per-CREATE, not per-concurrent. Survives the NIC unplug because Defender runs locally on I9 regardless of network topology.

**Verify what's loaded:**
```powershell
Get-MpPreference | Select-Object DisableRealtimeMonitoring, ExclusionPath, ExclusionProcess
Get-MpComputerStatus | Select-Object AntivirusEnabled, RealTimeProtectionEnabled, AntispywareEnabled
Get-Service WdFilter, WdNisSvc, MsSecCore, vsservppl, BdfsCore -ErrorAction SilentlyContinue | Select-Object Name, Status, DisplayName
fltmc filters    # list ALL filter drivers, look for Defender (WdFilter), Bitdefender (Trufos / BdfsCore / Avc3 / Gzflt), Norton (SymEFA / BHDrvx64), McAfee (mfehidk / mfewfpk), AVG/Avast (aswSP / aswMonFlt), Sophos (SophosED), MalwareBytes (mbam / mbamswissarmy)
```

**Diagnose conclusively (reversible):**
```powershell
# Add NFS drives + repo path to Defender exclusions:
Add-MpPreference -ExclusionPath 'T:\', 'M:\', 'Z:\', 'C:\Code\MediaVortex'
Add-MpPreference -ExclusionProcess 'ffmpeg.exe', 'ffprobe.exe'
# Re-run a failing batch (concurrency=1). If EINVAL stops, H2 is confirmed.
```

If H2 confirmed and there is also a third-party AV in `fltmc filters`, add identical exclusions in that vendor's console.

### H5 -- `shell=True` subprocess wrapper corrupts ffmpeg's output handle (operator log 2026-05-22)

Worker invokes ffmpeg via `subprocess.Popen(..., shell=True)` (BUG-0008 original "Look first #5" flagged this; the new operator log confirms a shell process is in fact spawned, since the worker prints "Shell process PID NNNN not found" warnings). On Windows, `shell=True` runs `cmd.exe /c "<full command string>"`. cmd.exe parses the command line and re-quotes it before passing to `ffmpeg.exe`. If any character in the output path is special to cmd (`^`, `&`, `|`, `<`, `>`, `(`, `)`, `'`, `"`, `%`), cmd may strip/mangle it depending on quote context. Some failing paths in this run included `'` (X-Men '97) and `(...)` (The Flash (2014)) which cmd handles inconsistently across versions.

That said, this is NOT a clean fit because many failing paths have no special characters (e.g. The Umbrella Academy S01E09 -- no special chars and still failed). And the manual-shell test succeeds, which would be strong negative evidence IF the operator typed/pasted the exact same shell=True-wrapped command. Treat H5 as plausible but not the leading suspect; defer until H2 is ruled out.

**Diagnose:**
1. Capture the EXACT command string the worker passes to Popen (already in `TranscodeAttempts.FfpmpegCommand`).
2. From an interactive PowerShell, run `cmd /c "<the exact string>"` -- NOT bash, NOT direct ffmpeg.exe invocation. If THIS fails the way the worker fails, H5 is confirmed.
3. If H5 confirmed, fix at the worker by switching to `shell=False` with a tokenized command list (`Popen([ffmpeg_exe, "-i", input, ..., output])`).

### H1 -- Two-NIC asymmetric routing on Windows NFS client (operator-raised 2026-05-22; **RULED OUT 2026-05-22** by physical NIC unplug)

The Windows NFS client opens a long-lived TCP connection to porky port 2049 from one source IP. If I9 has two NICs and the routing table can pick either as the source for the connection, then:

- On reconnect after a transient hiccup, the source IP may change. porky sees a "new" client; the kernel-side NFS state for handles, locks, and the open file is lost. Subsequent CREATE() with the stale handle returns EINVAL.
- If Windows uses per-packet load balancing (weak host model + similar interface metrics for the same subnet), individual RPC packets can egress from one NIC and replies come back on the other. porky responds correctly but the Windows NFS client demuxes the reply against the wrong connection and surfaces EINVAL.
- Hyper-V / WSL2 virtual NICs (`vEthernet (Default Switch)`, `vEthernet (WSL)`) on a dev workstation count as additional NICs and routinely cause this.

**Verify:**
```powershell
ipconfig /all                          # list all NICs + IPs + metrics
route print -4 | findstr "10.0.0"      # which NIC owns the 10.0.0.0/24 route
Get-NetIPInterface -AddressFamily IPv4 | Sort-Object InterfaceMetric | Select-Object InterfaceAlias, InterfaceMetric, ConnectionState
Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object Name, InterfaceDescription, LinkSpeed, MacAddress
```

**Diagnose conclusively:**
- Disable one NIC: `Disable-NetAdapter -Name '<name>' -Confirm:$false`. Re-run the failing batch. If failures stop, H1 is confirmed.
- Or set explicit metrics so only one NIC routes to 10.0.0.0/24: `Set-NetIPInterface -InterfaceAlias '<keep>' -InterfaceMetric 5; Set-NetIPInterface -InterfaceAlias '<other>' -InterfaceMetric 9000`.

**If confirmed, fix options:**
- Disable the unused NIC permanently (operator preference).
- Bind the NFS client to a specific interface (no first-class setting in the Microsoft NFS client; effectively only achievable via routing metrics).
- Add a static route forcing 10.0.0.43/32 out the chosen NIC: `route add 10.0.0.43 mask 255.255.255.255 10.0.0.1 metric 1 -p` (substitute the chosen NIC's gateway).

### H2 -- Antivirus / file-system filter driver intercept on CREATE()

Windows Defender (or any AV) hooks every `CreateFile()` and can return EINVAL on a small percentage when its scanner can't classify the file fast enough. Linux workers do not have this layer. Single-threaded I9 still hits it because it is per-CREATE, not per-concurrent.

**Verify:**
```powershell
Get-MpPreference | Select-Object ExclusionPath, DisableRealtimeMonitoring
Get-Service WdFilter, MsSecCore, vsservppl -ErrorAction SilentlyContinue | Select-Object Name, Status
Get-CimInstance Win32_LoadOrderGroup -Filter "Name='FSFilter Anti-Virus'"
```

**Diagnose:**
- Add `T:\`, `M:\`, `Z:\` and `C:\Code\MediaVortex` to Defender exclusions: `Add-MpPreference -ExclusionPath 'T:\', 'M:\', 'Z:\', 'C:\Code\MediaVortex'`. Re-run a failing batch. If failures stop, H2 is confirmed.

### H3 -- Microsoft NFS client UID/GID mapping race on `anon` mount

Current mount is `UID=0, GID=0, anon, sec=sys`. porky's export options may be `root_squash` (the default), which maps UID 0 to `nobody` (UID 65534). On a fresh handle the squashing applies cleanly; on a re-used or cached handle the kernel-side identity may transiently flip, returning EACCES which the Windows NFS client translates as EINVAL to user space.

**Verify on porky:**
```bash
ssh root@porky 'cat /etc/exports | grep nfs-media-_tv'
ssh root@porky 'exportfs -v | grep nfs-media-_tv'
```

**Diagnose:** if porky's export uses `root_squash` (default) or `all_squash`, set `no_root_squash` or `anonuid=<owner UID>` and re-export: `exportfs -ra`. Re-run a failing batch.

### H4 -- Windows NFS client per-process handle cache exhaustion

The Microsoft NFS client maintains a per-process handle cache. FFmpeg opens many files (the moov box rewrite for `+faststart`, the audio decode pipeline, sidecar reads). If the cache overflows mid-job, the next CREATE() returns EINVAL until cache pressure relaxes.

**Verify:** `reg query "HKLM\SYSTEM\CurrentControlSet\Services\NfsClnt\Parameters"` -- look at `MaxNfsUser`, `MaxIcbNfsUser`, `HandleSignatureKeyLength`. Compare to MS defaults.

**Diagnose:** there is no surgical test for this; treat as the last resort after H1-H3 are ruled out.

## Investigation log

Append findings here in order. Each entry: date, operator hypothesis checked, evidence captured, ruled in/out.

- **2026-05-22** -- Initial hypothesis was soft-mount (`mtype=soft, timeout=0.8s, retry=1`). Remounted hard via `mount.exe -o mtype=hard -o timeout=30`. Failures persisted. **Ruled out.**
- **2026-05-22** -- Hypothesis: two `python.exe` processes were concurrent workers. Found `ParentProcessId` shows the pair is a venv launcher stub + interpreter (WebService shows identical pattern, no failures). **Ruled out (misdiagnosis).**
- **2026-05-22** -- Hypothesis: `MaxConcurrentRemuxJobs=4` was producing parallel CREATE() races. Reduced to 1. Failures persisted on operator's single-worker run. **Ruled out by operator.**
- **2026-05-22** -- Operator raised H1 (two NICs on I9). Operator physically unplugged one NIC; I9 reachable only via .7 IP. EINVAL failures continued across multiple ffmpeg invocations (Flash S01E21, Umbrella Academy S01E09, X-Men '97 S01E07). **H1 ruled out.**
- **2026-05-22** -- Operator log captured "WARNING: Shell process PID NNNN not found" + "Failed to set CPU affinity" preceding every FFmpeg failure. Confirms worker uses `shell=True` (cmd.exe wrapper) for ffmpeg invocation. Added H5 (shell wrapper) as new hypothesis.
- **2026-05-22** -- Operator captured `Get-MpPreference`: `DisableRealtimeMonitoring=True`. Defender RTP is off; existing exclusions cover `\\allen\games`, `C:\Code`, `C:\Code\ZenScan\zenscan`, `C:\Games` but not T:/M:/Z:. Defender-specific form of H2 ruled out. `fltmc filters` output not yet captured; other kernel filter drivers (EDR, backup agents, encryption) could still intercept.
- **2026-05-22** -- Operator raised H0: the brain -> porky infrastructure migration retired SMB on I9 and switched I9's media-share access to the Microsoft NFS client. This is the only change to I9's CreateFile path between "worked" and "doesn't work." Linux workers were always on NFS and did not regress. Promoted H0 to LEADING HYPOTHESIS. Next investigation step: diff the pre-migration SMB mount + brain's exports against the current NFS mount + porky's exports; commit `79a02f3` and the infrastructure repo are the sources.
- **2026-05-22** -- Layer-isolation repro attempted from elevated PowerShell, failed at `New-Item T:\...` with "drive 'T' does not exist." Discovered Windows NFS drive letters are per-logon-session (Confirmed Fact #7). Worker's mapping is bound to the operator's interactive session LUID; elevated shells don't inherit it. Added H0b sub-hypothesis: worker's session-bound mapping could be invalidating intermittently and producing stale-handle EINVAL on subsequent CreateFile. Operator re-ran layer-isolation repro via UNC path `\\10.0.0.43\srv\nfs-media-_tv\...`.
- **2026-05-22** -- **UNC-path layer-isolation repro: OK=200 FAIL=0.** All 200 CreateFile attempts via UNC succeeded. The NFS protocol layer between I9 and porky is healthy. The bug is NOT at the wire level; it is in the layer above. This rules out H0 in its broad "NFS protocol broken" form.
- **2026-05-22** -- **Test A passed:** UNC create-loop OK=200 FAIL=0 on all three shares (porky-tv, synology-mov, synology-xxx). **Test B passed:** ffmpeg-over-UNC OK=10 FAIL=0 with the actual failing job command shape. UNC stack is stable across both NFS servers and through ffmpeg's own CreateFile path. Decision matrix triggered: safe to commit the worker code change to UNC. Test C (15-min side-by-side under live worker load) deferred -- will run as the verification step after the code change lands, doubling as the BUG-0008 criterion 13 verification window.
- **2026-05-22** -- Confirmed porky's SMB is OFF (`systemctl is-active smbd nmbd` -> inactive, no listener on 445/139). The earlier 200/200 UNC test routed through NFS via MUP -> NFS redirector. UNC-over-NFS is the target stack.
- **2026-05-22** -- Audited porky network + NFS config and the infrastructure migration doc. Findings: (1) porky has a single active uplink (`nic4` -> `vmbr0` -> 10.0.0.43, MTU 1500), no asymmetric routing risk; (2) `/proc/fs/nfsd/versions` shows `+3 +4 +4.1 +4.2` enabled -- Microsoft NFS client only speaks v3, version-negotiation drift is a candidate trigger; (3) porky's exports look clean and match what Linux workers use; (4) **CRITICAL:** infrastructure repo `brain-porky-media-migration.md` (lines 126, 181-182, 369, 610, 632) shows the migration plan was SMB-to-brain -> SMB-to-porky, but porky's `smbd` is `inactive`. The Windows worker was put on NFS-to-porky as an undocumented departure from the plan; this stack (MS NFS client -> Linux nfsd) was never validated. Reframes the bug: not a regression, an untested combination. Added recommended fixes A (restore SMB per the original plan), B (disable NFSv4 server-side, cheap test), C (worker-side retry, symptom-only band-aid).
- **2026-05-22** -- Code-side fix landed: worker is read-only on SRR/WSM, `SetWindowsWorkerUncPaths.py` is sole writer, gates on `Workers.Status` + `<Cap>Enabled` moved into the claim queries themselves (no more polling-cache lag). Worker now hands UNC paths to ffmpeg. Confirmed via `TranscodeAttempts.FfpmpegCommand`. **EINVAL `4294967274` still appears intermittently** on UNC commands (e.g. attempts 20219, 20226, 20283-20285). Mixed success/failure on UNC kills the simple "drive-letter session unbinding is the only fragility" theory. Confirmed Fact #9 added. Promoted **H7 (brain -> porky migration introduced NFS-server-side behavior the Microsoft client mishandles)** to leading hypothesis with concrete diagnostic commands for the porky side (exports, nfsd version, lockd, anon UID) and the I9 side (Windows + ClientForNFS version, registry settings, recent hotfixes). Linux workers against the SAME export are 100% clean, isolating the defect to the Microsoft NFS client's protocol-level interaction with porky.
- **2026-05-22** -- Operator pushback: load is NOT a factor (ffmpeg fails intermittently at concurrency=1 with no other workers running). Dropping the "run repro while worker is loading" timing requirement. The PowerShell loop succeeded 200/200 with no concurrent worker; that is sufficient evidence that **simple CreateFile on this NFS mount works fine.** The bug is something specific to **how ffmpeg is launched from the worker**, not to NFS itself. Promoted **H5 (`shell=True` cmd.exe wrapper)** to the leading hypothesis. The worker's "Shell process PID NNNN not found" warnings (Confirmed Fact #4) are evidence that the wrapper is in use on every invocation. H0b (drive-letter mapping instability) demoted -- the mapping clearly works from inside the worker's process, just not via simple PowerShell from another session. H6 (ffmpeg's own CreateFile flags) is the alternative candidate if H5 doesn't pan out. Next test: run one failing FfpmpegCommand two ways from a Python script -- `subprocess.run(cmd_str, shell=True)` vs `subprocess.run(cmd_list, shell=False)`, 20 iterations each, compare failure rates.

## Verification criterion

This bug is fixed when:

> Across 100 consecutive `TranscodeAttempts` rows where `WorkerName='I9-2024'`, zero rows have `Success=false` with `ErrorMessage LIKE '%return code 4294967274%'` AND `TranscodeDurationSeconds=0`. Concurrency level used during the verification window is recorded in the investigation log.

This is the same bar as `deploy/worker-deploy.feature.md` criterion 13.
