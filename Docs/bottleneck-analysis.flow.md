# Bottleneck Analysis Flow -- per-worker diagnostic process

**Slug:** bottleneck-analysis

## Entry Point

Operator observes lower-than-expected throughput (FPS, jobs/hour, or wall-clock time) on a specific worker or fleet-wide. This flow identifies which resource is the constraint.

## Stage Overview

```
ST1: MEASURE   -- Collect baseline: current FPS, job duration, file size, worker concurrency
ST2: CLASSIFY  -- Determine bottleneck category: CPU, Network I/O, Disk I/O, or Memory
ST3: VALIDATE  -- Confirm with targeted test (single-variable change)
ST4: REMEDIATE -- Apply fix and re-measure
```

## Bottleneck Categories

| Category | Symptom | Key Indicator |
|----------|---------|---------------|
| **CPU-bound** | FPS scales linearly with preset number; adding concurrency does not increase total FPS | CPU usage near 100% on all assigned cores |
| **Network I/O** | FPS drops when reading/writing over network vs local; multiple concurrent jobs don't increase aggregate throughput | NIC utilization near link speed; high SMB read/write latency |
| **Disk I/O** | Same as network I/O but on local storage; queue depth high | Disk queue length > 2; high iowait (Linux) or disk latency > 10ms |
| **Memory** | OOM kills or swap usage during quality testing (VMAF reads entire file into memory) | Available memory near zero during peak concurrency |

## ST1 -- MEASURE -- Baseline Collection

### Data sources already available

- **TranscodeAttempts**: `TranscodeDurationSeconds`, `OldSizeBytes`, `NewSizeBytes`, `WorkerName` -- historical per-job throughput
- **TranscodeProgress**: `CurrentFPS`, `AverageFPS` -- real-time encoding speed
- **SystemMonitoringService** (`/api/SystemResources`): CPU%, memory, temperature -- webservice host only (not remote workers)
- **Workers table**: `MaxConcurrentJobs`, `MaxConcurrentQualityTestJobs`

### Queries for baseline

```sql
-- Per-worker average throughput (last 7 days)
SELECT WorkerName,
       COUNT(*) AS Jobs,
       ROUND(AVG(TranscodeDurationSeconds)::numeric, 1) AS AvgDurationSec,
       ROUND(AVG(OldSizeBytes / 1048576.0)::numeric, 0) AS AvgInputMB,
       ROUND(AVG(NewSizeBytes / 1048576.0)::numeric, 0) AS AvgOutputMB,
       ROUND(AVG(OldSizeBytes / NULLIF(TranscodeDurationSeconds, 0) / 1048576.0)::numeric, 1) AS AvgMBPerSec
FROM TranscodeAttempts
WHERE CompletedDate > NOW() - INTERVAL '7 days'
  AND Success = TRUE
GROUP BY WorkerName
ORDER BY AvgMBPerSec DESC;

-- Compare same file across workers (if available)
SELECT ta.WorkerName, ta.TranscodeDurationSeconds, ta.OldSizeBytes, ta.NewSizeBytes
FROM TranscodeAttempts ta
JOIN MediaFiles mf ON ta.MediaFileId = mf.Id
WHERE mf.FilePath = '<path>'
ORDER BY ta.WorkerName;
```

### External measurements (not in DB -- operator must collect)

- **NIC link speed and utilization**: `Get-NetAdapter` (Windows), `ethtool` / `ip link` (Linux)
- **SMB latency**: `Get-SmbConnection` / `Get-SmbMultichannelConnection` (Windows)
- **Disk latency**: `Get-PhysicalDisk | Get-StorageReliabilityCounter` (Windows), `iostat -x` (Linux)

## ST2 -- CLASSIFY -- Decision Tree

```
Is the source file on a network share (SMB/NFS)?
  |
  +-- YES --> Run the same job on a local copy of the file.
  |           Did FPS improve significantly (>20%)?
  |             +-- YES --> NETWORK I/O bottleneck. Go to Stage 2A.
  |             +-- NO  --> CPU bottleneck. Go to Stage 2B.
  |
  +-- NO (local disk) --> Is CPU at 100% during transcode?
                            +-- YES --> CPU bottleneck. Go to Stage 2B.
                            +-- NO  --> Is disk queue depth > 2 or latency > 10ms?
                                          +-- YES --> DISK I/O bottleneck. Go to Stage 2C.
                                          +-- NO  --> Check memory (Stage 2D) or encoder config.
```

### Stage 2A: Network I/O

**Indicators:**
- NIC link speed vs actual throughput (e.g., 1Gbps link = ~110 MB/s theoretical, ~90 MB/s practical for SMB)
- Multiple concurrent jobs share the same NIC bandwidth -- total throughput plateaus
- Remux jobs (I/O-heavy, minimal CPU) are disproportionately slow compared to CPU-heavy transcodes

**Common findings in this environment:**
- Single 1Gbps link to NAS: ~90 MB/s shared across all read+write operations
- SMB Multichannel with 2x 1Gbps links: ~180 MB/s aggregate, traffic splits automatically
- 10GbE link: ~1000 MB/s, removes network as a constraint for most workloads
- Docker workers accessing NAS via host's NIC share the host's total bandwidth

**What to check:**
```powershell
# Windows -- NIC link speed and multichannel status
Get-NetAdapter | Select-Object Name, LinkSpeed, Status
Get-SmbMultichannelConnection | Select-Object ServerName, ClientLinkSpeed, ServerLinkSpeed

# Linux (Docker host) -- NIC speed
ethtool eth0 | grep Speed
cat /proc/net/dev  # TX/RX bytes for throughput over time
```

### Stage 2B: CPU-bound

**Indicators:**
- FPS scales with SVT-AV1 preset number (preset 8 is faster than preset 6)
- Increasing concurrency splits CPU across jobs -- per-job FPS drops proportionally
- Temperature rises to thermal throttle threshold

**What to check:**
- `CurrentFPS` in TranscodeProgress during active job -- compare to expected range for that preset/resolution
- CPU temperature via SystemMonitoringService or `sensors` (Linux) / LibreHardwareMonitor (Windows)
- Thread count vs core count -- SVT-AV1 uses `--lp` (logical processors) parameter

### Stage 2C: Disk I/O

**Indicators:**
- Local-disk jobs are slow despite low CPU usage
- HDD-backed storage with concurrent random reads/writes (seek-bound)
- NVMe/SSD should not be a bottleneck for typical media files

**What to check:**
```powershell
# Windows
Get-Counter '\PhysicalDisk(*)\Avg. Disk Queue Length'
Get-Counter '\PhysicalDisk(*)\Avg. Disk sec/Read'

# Linux
iostat -x 1 5  # watch %util and await columns
```

### Stage 2D: Memory

**Indicators:**
- VMAF quality testing reads source + transcode into memory for frame-by-frame comparison
- 4K files can require 8-16 GB during VMAF analysis
- Workers running multiple concurrent quality tests may exhaust RAM

**What to check:**
- Available memory during peak VMAF concurrency
- OOM-killer logs: `dmesg | grep -i oom` (Linux containers)
- `MaxConcurrentQualityTestJobs` vs available RAM per worker

## ST3 -- VALIDATE -- Confirm with Single-Variable Test

Change only one variable and re-measure:

| Bottleneck | Validation test |
|------------|----------------|
| Network I/O | Copy file to local scratch disk, transcode from local, compare FPS |
| CPU | Lower concurrency to 1, confirm FPS matches expectation for that preset |
| Disk I/O | Move scratch to SSD/NVMe, re-run same job |
| Memory | Lower quality test concurrency to 1, confirm no OOM |

## ST4 -- REMEDIATE

## Seams

This is a read-only diagnostic flow -- no writes to durable state. The "seam" rows enumerate the data sources read at each stage so a change to producer schemas is visible here.

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1` reads `TranscodeAttempts` | `ProcessTranscodeQueueService` (in `transcode.ST6`) | `TranscodeAttempts.(WorkerName TEXT NOT NULL, TranscodeDurationSeconds INT, OldSizeBytes BIGINT, NewSizeBytes BIGINT, CompletedDate TIMESTAMP, Success BOOLEAN)` | Per-worker throughput SQL (Stage 1 baseline query) | Stage-1 SQL returns a non-empty result set for any 7-day window with completed transcodes |
| S2 | `ST1` reads `TranscodeProgress` | `ProcessTranscodeQueueService` heartbeat | `TranscodeProgress.(TranscodeAttemptId, CurrentFPS, AverageFPS, LastUpdate TIMESTAMP)` | Operator sees real-time FPS via /Activity | Manual probe: pick an active job, confirm CurrentFPS is non-NULL |
| S3 | `ST2` reads `Workers` | `WorkerService` registration + capability poller | `Workers.(WorkerName, MaxConcurrentJobs, MaxConcurrentQualityTestJobs)` | Concurrency reasoning at Stage 2 | `\d Workers` shows both columns; `MaxConcurrentJobs` sizes the boot-fixed transcode-family semaphore, `MaxConcurrentQualityTestJobs` sizes the QT pool |
| S4 | `ST4 -> done` (remediation closes the loop) | Operator action (no MediaVortex write) | External (NIC config, disk swap, concurrency UPDATE) | Re-run of S1 query confirms improvement | Compare Stage 1 baseline query result before and after remediation |
| S5 | `ST1` reads `SystemMonitoringService` | `SystemMonitoringService` (psutil daemon on WebService host only) | `/api/SystemResources` returns `{cpu_percent, memory_percent, disk_io, cpu_temperature_per_core}` -- WebService process scope, not per-worker | Operator interprets as CPU-bound vs memory-bound. **Non-obvious limitation:** these numbers are the WebService host (I9-2024 by default), NOT the remote Linux workers. Bottleneck classification for larry/wakko/dot workers requires SSH-collected metrics per Stage 2 (`Get-NetAdapter` / `ethtool`). Confusing this scope -> mis-classifying a remote worker's bottleneck against I9's psutil numbers | `curl /api/SystemResources` from any worker host returns the WebService host's psutil values, not the target worker's |
| S6 | `ST3` validation requires capability-flag mutation | `Features/ServiceControl/capability-control-plane.flow.md::ST3` consumer pattern | Operator UPDATEs `Workers.MaxConcurrentJobs`; boot-fixed semaphore requires worker restart to apply. `MaxConcurrentQualityTestJobs` picks up mid-flight | Confirming a CPU-bound hypothesis (Stage 2B) requires worker restart when changing transcode concurrency | After test: restore prior concurrency + restart. Per `feedback_coordinate_live_worker_writes.md`, coordinate with the operator before mutation |
| S7 | `ST3` baseline-vs-validation comparison | `TranscodeAttempts` (S1 producer) | Same wire shape as S1; relies on a "post-change" window of completed attempts | A validation test needs at least one full transcode after the change to populate `TranscodeDurationSeconds`. For long files (4K SVT-AV1) the window is hours, not minutes | Time the test against typical job duration before declaring validated; `SELECT CompletedDate FROM TranscodeAttempts WHERE WorkerName=<x> ORDER BY 1 DESC LIMIT 1` must be AFTER the change timestamp |


| Bottleneck | Remediation options |
|------------|-------------------|
| Network I/O | Add NIC ports (SMB Multichannel), upgrade to 10GbE, use local scratch disk for write then move, reduce concurrent I/O-heavy jobs |
| CPU | Use higher preset number (faster, lower quality), reduce concurrency, add workers on other machines |
| Disk I/O | Move to SSD/NVMe, reduce concurrent jobs hitting same spindle |
| Memory | Reduce `MaxConcurrentQualityTestJobs`, add RAM, process 4K quality tests sequentially |

After remediation, re-run the Stage 1 baseline query and compare to pre-change numbers.

## Current Fleet Reference (2026-05-21)

| Worker | Hardware | NIC | Storage Path | Known Constraints |
|--------|----------|-----|-------------|-------------------|
| I9-2024 | i9, 32 threads | Intel X540-T2 2x1Gbps | \\10.0.0.43\srv\nfs-media-_tv (porky NFS) | Network I/O -- 2Gbps aggregate, shared read+write |
| larry-worker-1..4 | Docker on 10.0.0.42 (LXC 218) | Host NIC (1Gbps presumed) | NFS mount via Docker volume | Network I/O -- 4 containers share 1 NIC |
| wakko-worker-1..4 | Bare-metal Linux on 10.0.0.230 (Ryzen 7 3700X + Intel Arc B580) | Host NIC | NFS mount native | Intel Arc XPU demucs |
| dot-worker-1..4 | Docker on 10.0.0.193 (bare-metal) | Host NIC | NFS mount via Docker volume | TBD -- not yet profiled |
