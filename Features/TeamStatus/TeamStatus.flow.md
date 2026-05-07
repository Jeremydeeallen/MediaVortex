# Stats Page Flow

Entry point: `GET /Stats` (renders `Templates/Status.html`)

## Data Sources

| Section | API Endpoint | Data Source |
|---------|-------------|-------------|
| Library Statistics | GET /api/Statistics | MediaFiles aggregate |
| Savings by Day (chart) | GET /api/TeamStatus/SavingsByDay | TranscodeAttempts aggregate |
| System Resources | GET /api/SystemResources | SystemMonitoringService (local psutil) |
| Active Transcode Jobs | GET /api/TeamStatus/Overview | TranscodeProgress + TranscodeQueue + TranscodeAttempts |
| Transcode Savings Summary | GET /api/TeamStatus/Overview | TranscodeAttempts aggregate |
| Savings by Volume | GET /api/TeamStatus/SavingsByVolume | TranscodeAttempts aggregate |
| Continuous Scanning | GET /api/Scan/ContinuousStatus | In-memory scan state |
| Services | GET /api/Status | ServiceStatus table |

## User Flow

| Step | User sees | System does |
|------|-----------|-------------|
| 1 | Page loads, all sections show "Loading..." | JS calls all 7 API endpoints in parallel |
| 2 | Library stats populate (file count, size, encoded, saved) | /api/Statistics returns MediaFiles aggregate |
| 3 | Savings chart renders | /api/TeamStatus/SavingsByDay returns last 30 days |
| 4 | System resources populate (CPU, temp, memory, disk) | /api/SystemResources returns psutil data from WebService host |
| 5 | Active Transcode Jobs: table of running jobs with progress bars, FPS, ETA | /api/TeamStatus/Overview joins TranscodeProgress to TranscodeQueue |
| 6 | Savings summary cards populate | Same /api/TeamStatus/Overview response |
| 7 | Volume table populates | /api/TeamStatus/SavingsByVolume groups by drive letter |
| 8 | Continuous scan status populates | /api/Scan/ContinuousStatus |
| 9 | Services section: cards for each service with status badge | /api/Status reads ServiceStatus table |
| 10 | Auto-refresh polls every 10s | All APIs re-fetched on timer |

## Failure Modes

| Failure | Current behavior | Expected behavior |
|---------|-----------------|-------------------|
| Worker offline but has Running queue items | Active Jobs shows stale Running jobs indefinitely | Stuck jobs should be detectable and cleanable from the UI |
| Multiple workers transcoding simultaneously | All jobs shown in one flat list, no worker attribution | Each job should show which worker is processing it |
| Remote worker not in ServiceStatus table | Services section shows only local services | Workers section should list all registered workers from Workers table |
| WebService not on same host as worker | System Resources shows WebService host only | Per-worker resources would need a separate monitoring path (out of scope) |
