# Ingest Webhook

**Slug:** ingest-webhook

## What It Does

Receives file-operation events from Sonarr / Radarr and enqueues an immediate ScanJobs row for the RootFolder containing the affected path. Primary discovery trigger per `ingest.flow.md` DD_C. Discovery latency = seconds, not minutes.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | Sonarr fires OnDownload / OnUpgrade / OnRename event | Sonarr Connect > Webhook config | `POST /api/Ingest/Webhook` | `Features/Ingest/IngestWebhookController.Receive` |
| W2 | Radarr fires OnDownload / OnUpgrade / OnRename event | Radarr Connect > Webhook config | same | same |
| W3 | Operator tests webhook | Sonarr / Radarr "Test" button | same | endpoint accepts test payload without side effect |

## Success Criteria

C1. **`POST /api/Ingest/Webhook` accepts Sonarr and Radarr payload shapes.** Payload types handled: `OnDownload`, `OnRename`, `OnFileUpgrade`, `OnFileDelete`. Test payload (`eventType='Test'`) returns 200 with `{Success: True, Message: 'Test received'}` and does NOT enqueue. Contract: `TestIngestWebhook.py`.

C2. **Payload -> canonical path extraction.** For each supported event type, extract the target file / folder path from the payload's known fields (`series.path` / `movie.folderPath` / `episodeFile.path` / `movieFile.path`). Fail loud on unrecognized shape: 400 response, no queue write.

C3. **Canonical path -> RootFolder resolution.** Match extracted path prefix against `StorageRoots`. Enqueue ScanJobs row scoped to the containing RootFolder (or the specific subtree if payload includes it). Contract test.

C4. **Unknown storage root prefix.** Endpoint returns `{Success: False, Message: 'Unknown storage root: <prefix>'}` with 400. No ScanJobs row written. Logs WARNING (visible for operator debug).

C5. **Discovery latency observable.** Contract test: post canned Sonarr `OnDownload` payload, assert ScanJobs row appears within 1 second. Downstream: scan runs; MediaFiles row appears; probe picks up next tick; classify + compliance cascade.

C6. **Fail-loud on malformed payload.** Missing required field, unparseable JSON, unknown eventType: 400 with structured error. No silent Success=True. Per `.claude/rules/fail-loud.md`.

C7. **Endpoint is idempotent.** Duplicate webhook for same path within short window: second call finds an in-flight ScanJobs for the RootFolder + returns 200 with `{Success: True, Message: 'ScanAlreadyRunning', ExistingJobId: ...}`. Sonarr/Radarr retry logic handled gracefully.

C8. **No authentication required.** Sonarr/Radarr do not sign payloads. Deployed on trusted internal network. If exposed externally, operator must proxy behind auth (out of scope for this feature).

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | Sonarr/Radarr -> Endpoint | external HTTP POST | JSON payload matching `OnDownload` / `OnRename` / `OnFileUpgrade` / `OnFileDelete` / `Test` shape | Flask parses; controller dispatches per eventType | contract test with canned payloads |
| S2 | Controller -> BusinessService | after eventType dispatch | `EnqueueScanForPath(canonical)` -> `{Success, ScanJobId, Message}` | writes ScanJobs row via existing StartScanning primitive | contract test |
| S3 | BusinessService -> StorageRoots lookup | canonical prefix | `PathParser.FromCanonical(path)` returns `(StorageRootId, RelativePath)` OR raises `UnknownStorageRoot` | 400 on raise | contract test |
| S4 | BusinessService -> ScanJobs write | validated inputs | `INSERT INTO ScanJobs (Status='Pending', RootFolderPath, StorageRootId, RelativePath, WorkerName=NULL) ON CONFLICT (per per-rootfolder claim guard) DO NOTHING RETURNING Id` | single INSERT | contract test |
| S5 | ScanJobs -> ScanWorker (implicit) | Pending row appears | ScanWorker claims via existing per-RootFolder claim mechanism | scan runs | contract test |

## Payload examples

### Sonarr OnDownload
```json
{
  "eventType": "Download",
  "series": {"path": "T:\\Full Circle (2023)"},
  "episodeFile": {"relativePath": "Season 1/Full Circle (2023) - S01E01.mkv", "path": "T:\\Full Circle (2023)\\Season 1\\Full Circle (2023) - S01E01.mkv"}
}
```

### Radarr OnDownload
```json
{
  "eventType": "Download",
  "movie": {"folderPath": "M:\\The Matrix (1999)"},
  "movieFile": {"path": "M:\\The Matrix (1999)\\The Matrix (1999).mkv"}
}
```

### Test payload
```json
{"eventType": "Test"}
```

## What this feature does NOT own

- Scan execution: `Features/FileScanning/scan.feature.md`
- Probe execution: `Features/MediaProbe/probe.feature.md`
- Sonarr / Radarr internal config (that's their tooling; this feature just receives)
- Auth (deployed on trusted network; external exposure requires operator proxy)

## Status

DRAFTED under directive `ingest-pipeline-kiss`.
