# Bottleneck Analysis -- per-worker throughput diagnostics

**Slug:** bottleneck-analysis

## What It Does

Gives the operator a structured way to identify why a worker (or the fleet) is underperforming. Today the operator must manually correlate FPS, job duration, NIC speed, and CPU usage across multiple tools. This feature surfaces bottleneck indicators from data already in the database and provides a diagnostic flow for the rest.

## Concern

During the 2026-05-14 performance audit, diagnosing I9-2024's throughput required: checking NIC link speed via PowerShell, testing SMB Multichannel status, comparing remux times across workers, and reasoning about whether the constraint was CPU or network. None of this was available in the MediaVortex UI -- it all required SSH and ad-hoc queries. The diagnostic process should be documented (flow doc) and the data that CAN be derived from existing tables should be surfaced automatically.

## Surface

- Activity page (per-worker throughput indicators)
- Diagnostic flow doc for operator-driven investigation: `Docs/bottleneck-analysis.flow.md`

## Success Criteria

### A. Documented diagnostic process

1. A flow doc (`Docs/bottleneck-analysis.flow.md`) describes the four-stage bottleneck identification process: Measure, Classify, Validate, Remediate. Each stage lists concrete data sources, queries, and decision criteria. The flow covers CPU, Network I/O, Disk I/O, and Memory bottleneck categories.

2. The flow doc includes a current fleet reference table listing each worker's hardware, NIC configuration, storage path, and known constraints. Updated whenever fleet topology changes.

### B. Database-derived throughput indicators (future)

3. Per-worker average throughput (MB/s processed) is derivable from `TranscodeAttempts` via `OldSizeBytes / TranscodeDurationSeconds`. An API endpoint or query exposes the last-7-day average per worker so the operator can compare workers without writing SQL.

4. Per-worker job completion rate (jobs/hour over last 24h) is derivable from `TranscodeAttempts.CompletedDate` grouped by worker. Exposed alongside throughput in the same endpoint.

5. When two workers process files of similar size and resolution, a throughput delta greater than 2x between them is flagged as an anomaly worth investigating. The flag is informational (tooltip or indicator), not blocking.

### C. External data the system cannot collect

6. NIC link speed, disk queue depth, and SMB latency are outside the application's monitoring scope. The flow doc lists the exact commands to collect these per OS. The system does not attempt to SSH into workers to gather this data.

## Scope

```
Docs/bottleneck-analysis.flow.md
Docs/bottleneck-analysis.feature.md
```

## Status

IN PROGRESS

### Progress
- [x] Flow doc created with four-stage diagnostic process (2026-05-14)
- [x] Feature doc drafted with success criteria (2026-05-14)
- [x] Criteria A1-A2 implemented (flow doc exists with fleet reference)
- [ ] Criteria B3-B5 -- per-worker throughput API (not yet implemented)
- [ ] Criteria C6 -- verify flow doc command coverage is complete
