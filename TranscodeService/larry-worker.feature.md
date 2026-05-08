# Larry Transcode Worker

## What It Does

Adds a second transcoding worker running on Larry (Dell R640 Proxmox host, 10.0.0.6) inside an LXC container. Software-only SVT-AV1 encoding using Larry's 2x Xeon Gold 6130 (32C/64T). This is the first remote (non-Windows) worker -- it exposes a gap in the current PathTranslationService which only supports a single share prefix mapping, but the DB has files across three drive letters (T:\, M:\, Z:\) pointing to two different SMB servers.

## Concern

Both (infrastructure deployment + code change)

## Success Criteria

### Code (multi-prefix path translation)
1. WorkerShareMappings table stores (DriveLetter CHAR(1), LocalMountPrefix TEXT) per worker. No backslashes in the DB -- the service layer owns the `:\` separator.
2. PathTranslationService uses a dict lookup by drive letter (path[0]) instead of string prefix matching. Eliminates backslash escaping across Python/bash/SQL/SSH layers.
3. ProcessTranscodeQueueService loads mappings from the DB as a {DriveLetter: MountPath} dict and passes to PathTranslationService.
4. Existing Windows worker (I9-2024) continues to function with no path translation (backwards compatible -- empty mappings = no translation).
5. DB migration script is idempotent (safe to run on a DB that already has the Workers table).
6. Schema is forward-compatible with full path normalization: DriveLetter maps to a future ShareId FK.

### Infrastructure (LXC container on Larry)
6. LXC container created on Larry with: Debian 12 or Ubuntu 24.04, Python 3.11+, FFmpeg with libsvtav1, psycopg2. System-wide install (no venv -- single-purpose container).
7. Three CIFS mounts configured and persistent across reboot:
   - T:\ (Brain 10.0.0.40 Media_tv) -> /mnt/media_tv/
   - M:\ (Synology "allen" _video/Adults/Movies) -> /mnt/movies/
   - Z:\ (Synology "allen" xxx) -> /mnt/xxx/
8. Worker registered in Workers table with correct multi-prefix mappings, MaxConcurrentJobs=1. Workers.FFmpegPath AND Workers.FFprobePath both set to the worker's local paths (e.g. /usr/local/bin/ffmpeg, /usr/local/bin/ffprobe).
9. FFprobe runs on the worker using the worker's FFprobePath to analyze audio streams before transcoding. Audio language selection (English preferred) works identically on all workers regardless of platform.
10. Worker claims a queued job, transcodes it, and the output file is written in-place next to the source file.
11. Systemd service starts the worker on boot and restarts on failure.

### Documentation
12. WorkerSetup.md updated with multi-share configuration instructions (generic, not Larry-specific).

### End-to-End Worker Lifecycle (pass/fail)
13. setup.sh runs unattended and completes: worker row exists in Workers table, 3 rows in WorkerShareMappings, systemd service enabled.
14. Service starts, registers heartbeat, and enters Running state within 60 seconds of `systemctl start`.
15. Worker claims a Pending queue item: TranscodeQueue.Status = 'Running', ClaimedBy = worker hostname, ClaimedAt set. No other worker can claim the same item.
16. FFmpeg runs to completion on the worker. TranscodeAttempts.Success = TRUE, ErrorMessage IS NULL, NewSizeBytes > 0.
17. After success: queue item deleted from TranscodeQueue, ActiveJob marked Completed.
18. Worker immediately claims the next Pending item and repeats the cycle.
19. Stopping the worker (systemctl stop or SIGTERM) resets only THIS worker's running jobs to Pending, marks worker Offline, does not touch other workers' jobs.
20. Worker isolation: StuckJobDetector, CrashRecoveryService, and SignalHandler never interfere with another worker's jobs.

## Status

IN PROGRESS

### Progress

- [x] Read and understand current PathTranslationService, ProcessTranscodeQueueService worker config loading, and Workers table schema
- [x] Design multi-prefix schema change -- new WorkerShareMappings table (normalized, easy to query ad-hoc)
- [x] Write idempotent DB migration for multi-prefix support (WorkerShareMappings table)
- [x] Redesign: DriveLetter CHAR(1) instead of CanonicalPrefix -- no backslashes in DB, service owns separator
- [x] Update PathTranslationService to accept list of prefix pairs
- [x] Update ProcessTranscodeQueueService to load and pass multi-prefix config
- [x] Verify existing Windows worker still works (no regression -- empty mappings = no translation)
- [x] Create LXC container on Larry (Terraform module at Infrastructure/terraform/mediavortex-transcode/)
- [x] Install Python 3.11+, FFmpeg (with libsvtav1), psycopg2-binary inside container (in setup.sh)
- [x] Configure three media shares via Proxmox bind mounts (same host mounts as mediamanager CT 206)
- [x] Clone repo, install WorkerService requirements system-wide (no venv -- in setup.sh)
- [x] Register worker in DB with multi-prefix share mappings (in setup.sh)
- [x] Set up systemd service for auto-start (in setup.sh)
- [x] Update WorkerSetup.md with multi-share setup instructions
- [x] Fix worker isolation: SignalHandler, CrashRecovery, StuckJobDetector, QueueManagement scoped by WorkerName
- [x] Fix QueryDatabase.py --commit flag so setup.sh writes persist
- [x] Per-worker MaxCpuThreads: Workers table column, -threads N in FFmpeg command, affinity uses per-worker value
- [x] Fix yadif applied to progressive files: nulled YadifMode on profiles (CommandBuilder skips when NULL)
- [x] Upgrade FFmpeg: replace Ubuntu repo FFmpeg 6.1.1/SVT-AV1 1.7.0 with static build (SVT-AV1 2.x, 30-50% faster)
- [x] Interlaced routing: AcceptsInterlaced=FALSE on Larry, claim query skips interlaced files
- [x] Conditional yadif: CommandBuilder checks MediaFile.IsInterlaced, applies yadif only when true
- [x] VERIFY: worker claims job (75609), transcodes (Success=TRUE, 151MB, 784s), claims next (75610)
- [x] True in-place output: output file next to source, not in staging directory
- [x] VMAF toggle: global OFF so worker does not wait for quality test
- [ ] FFprobe per-worker: set Workers.FFprobePath, wire through to FFmpegAnalysisService for audio stream selection
- [ ] VERIFY: worker selects correct English audio stream (not defaulting to stream 0)

## Scope

```
Core/Services/PathTranslationService.py
Features/TranscodeJob/ProcessTranscodeQueueService.py
Scripts/SQLScripts/AddDistributedColumns.py
WorkerService/Main.py
WorkerService/WorkerSetup.md
```

## Files

| File | Change |
|------|--------|
| Core/Services/PathTranslationService.py | Accept list of prefix pairs instead of single pair |
| Features/TranscodeJob/ProcessTranscodeQueueService.py | Load multi-prefix config from DB, pass to PathTranslationService |
| Scripts/SQLScripts/AddDistributedColumns.py | Add migration for WorkerShareMappings table |
| Repositories/DatabaseManager.py | Add GetWorkerShareMappings(), update GetWorkerConfig() to include mappings |
| WorkerService/WorkerSetup.md | Document multi-share setup for Linux and Windows workers |

### Infrastructure repo (C:\Code\Infrastructure)

| File | Change |
|------|--------|
| terraform/mediavortex-transcode/main.tf | LXC container definition (CT 216, 8 cores, 8GB RAM, bind mounts) |
| terraform/mediavortex-transcode/setup.sh | Bootstrap: Python, FFmpeg, psycopg2, worker registration, systemd |
| terraform/mediavortex-transcode/provider.tf | Standard bpg/proxmox provider |
| terraform/mediavortex-transcode/variables.tf | Standard variables |
| terraform/mediavortex-transcode/terraform.tfvars | Larry endpoint + credentials |
| terraform/inventory.toml | Added mediavortex-transcode service entry (VMID 216, 10.0.0.32) |

## Context

### Drive letter to share mapping (from live system)

| Drive | UNC Path | Server | DB File Count |
|-------|----------|--------|---------------|
| T:\ | \\10.0.0.40\Media_tv | Brain | 48,012 |
| M:\ | \\allen\_video\Adults\Movies | Synology (10.0.0.61) | 3,285 |
| Z:\ | \\allen\xxx | Synology (10.0.0.61) | 7,869 |

### Larry hardware available

- CPU: 2x Xeon Gold 6130 (32C/64T total, 2.10 GHz)
- RAM: 384 GB (currently ~98 GB allocated to VMs/CTs)
- Storage: ZFS `data` pool 18.2 TB (~3% used)
- Network: Intel 2P X520 SFP+ / 2P I350 rNDC

### LXC resource allocation (suggested)

- 8 CPU cores (SVT-AV1 scales well but diminishing returns past 8-12 cores for single job)
- 8 GB RAM
- 20 GB root disk (on ZFS `data`)
- Unprivileged container

### Existing worker

The Windows PC (I9-2024) is registered with ShareMountPrefix=NULL, ShareCanonicalPrefix=T:\. It runs on the same machine where T:\, M:\, Z:\ are already mapped as Windows drive letters, so no path translation happens.
