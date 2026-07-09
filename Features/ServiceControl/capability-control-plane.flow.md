# Flow: Capability Control Plane

**Slug:** capability-control-plane

How a `Workers` row's capability flags become "loop running / loop stopped" on every worker, once per polling interval. Sole operational gate per `Features/ServiceControl/capability-control-plane.feature.md` -- `ServiceStatus.<X>Service.Status` is informational only and never read as a gate.

## Entry Point

`WorkerService._StartCapabilityPolling` (`workerservice.flow.md::ST11`) -- daemon thread on every worker that wakes every `SystemSettings.CapabilityPollingIntervalSec` (default 15s).

## Stages

| ID | Stage | Code | What It Does |
|---|---|---|---|
| ST1 | Wake | `_CapabilityPollingLoop` | Sleep on `ShutdownEvent`; wake on tick or shutdown. |
| ST2 | Read flags fresh | `_LoadCapabilitiesFromDB()` | `SELECT TranscodeEnabled, QualityTestEnabled, RemuxEnabled, ScanEnabled, Status, MaxConcurrentJobs, MaxConcurrentQualityTestJobs FROM Workers WHERE WorkerName=%s`. No `self._cached_*` (R3). |
| ST3 | Compute gate | service-internal | Per capability: `running := <Cap>Enabled = TRUE AND Status = 'Online' AND (NOW() - LastHeartbeat) < 90s`. `Status='Paused'` forces every capability off regardless of flag. `Status='Draining'` blocks NEW claims but lets in-flight finish. |
| ST4 | Apply | `_ApplyCapabilities()` + `_ApplyConcurrencyChanges()` | Start/Stop services on change. Semaphore capacity on `WorkerLoopService` is boot-fixed; changing `MaxConcurrentJobs` mid-flight logs a restart-required notice. QT concurrency updates mid-flight via `ProcessQualityTestQueueService.MaxConcurrentJobs`. |
| ST5 | Log transitions | `LoggingService.LogInfo` | One line per state change: `<Cap> capability started/stopped`. No log on no-op cycles. |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST2` row read | Operator + `WorkerService.flow.md::S6` writer | `Workers.(<Cap>Enabled BOOLEAN, Status TEXT, LastHeartbeat TIMESTAMP, MaxConcurrent*Jobs INTEGER)` | Fresh read per cycle | Mid-cycle UPDATE `Workers.TranscodeEnabled=FALSE`; observe stop within one interval |
| S2 | `ST3` invariant | this flow + `capability-control-plane.feature.md C1` | Single-gate predicate: no processing loop body reads `ServiceStatus` | `grep -rn "GetServiceStatus" Features/QualityTesting/ProcessQualityTestQueueService.py Features/TranscodeJob/ProcessTranscodeQueueService.py` returns no matches in any `*Loop`/`Run`/`ProcessJob` body | `Tests/Contract/TestClaimAuthority.py` per `db-is-authority.md` |
| S3 | `ST4` start/stop | this flow | Service Start/Stop methods on `WorkerLoopService`, `ProcessQualityTestQueueService`, `ContinuousScanService` | Each service runs a claim loop only when started; Stop joins on in-flight | `transcode.flow.md::S1` claim query (all modes via unified `ClaimNextPendingJob`) only executes when the worker's row has the matching capability on |
| S4 | `ST4` concurrency rebind | this flow | Boot-fixed `WorkerLoopService.SlotSemaphore` capacity + live `ProcessQualityTestQueueService.MaxConcurrentJobs` attribute | GUI edit + poll cycle logs restart-required for slot resize | UPDATE `Workers.MaxConcurrentJobs`; observe restart-required log line within one interval |

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| `Workers` row missing for this hostname | First cycle skips (no row); next `_RegisterAndLoadWorkerConfig` cycle creates it | Auto-heals on next worker restart |
| DB unreachable mid-cycle | Exception caught, no state change, next cycle retries | Self-healing |
| Operator writes `Workers.Status='Paused'` mid-claim | In-flight job completes; no new claims on next cycle | By design |
