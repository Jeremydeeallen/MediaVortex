# FailureTracking -- service-failure history surface

**Slug:** failure-tracking

## What It Does

Exposes a read-only API for recent service failures across Transcode and Quality services. Pure consumer of `Logs` + `TranscodeAttempts` tables; no writes. Surfaced via small widgets on /Status / /Activity for operator at-a-glance visibility. Distinct from FailureAccounting which enforces per-MediaFile failure budgets at /FailedJobs.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | View recent failures | /Status or /Activity widget | GET /api/FailureTracking/RecentFailures | FailureTrackingController.GetRecentFailures |

## Success Criteria

C1. /api/FailureTracking/RecentFailures returns the last 50 (configurable) failure rows across all services.
C2. Query parameter `serviceType` filters to Transcode or Quality (or all when omitted).
C3. Response is read-only -- the endpoint does NOT mutate any table.

## Cross-Vertical Contract

### Columns the FailureTracking vertical WRITES

| Column | Written by |
|---|---|
| (none) | Read-only consumer |

### Columns READS

| Column | Read by | Owner |
|---|---|---|
| Logs.* (recent ERROR rows) | GetRecentFailures | LoggingService |
| TranscodeAttempts.{Id, MediaFileId, ErrorMessage, AttemptDate, Success} | GetRecentFailures | TranscodeJob |
| MediaFiles.{Id, FilePath} | Display | FileScanning |

### Stable function entry points

None for external callers. Self-contained read-only API.

### HTTP API surface

| Method + URL | Purpose |
|---|---|
| GET /api/FailureTracking/RecentFailures?limit=N&serviceType=X | Recent failure list (read-only) |

### What is EXPLICITLY NOT a contract

- Default limit (50) -- tunable
- Per-service categorization (Transcode/Quality) -- expandable
- The shape of returned dict beyond the documented core fields (MediaFileId, FilePath, ErrorMessage, AttemptDate)
