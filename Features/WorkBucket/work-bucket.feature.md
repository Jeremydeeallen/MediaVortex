# WorkBucket -- per-bucket landing pages

**Slug:** work-bucket

## What It Does

Renders operator-facing landing pages at `/Work/<bucket>` for each WorkBucket value (Transcode, Remux, AudioFixOnly). Each page is a paginated MediaFiles list filtered by `MediaFiles.WorkBucket = '<value>'`, with a single-row queue-admission endpoint for one-off operator actions. Pure consumer of the trigger-derived WorkBucket column.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | Browse files needing transcode | /Work/Transcode page | GET /Work/<bucket> | WorkBucketController.RenderPage |
| W2 | Paginate within a bucket | page controls | GET /api/WorkBucket/<bucket>?page=N | WorkBucketRepository.ListByBucket |
| W3 | Admit one file to the queue | per-row Queue button | POST /api/WorkBucket/<bucket>/Queue/<MediaFileId> | WorkBucketRepository.AdmitToQueue |

## Success Criteria

C1. Each of {/Work/Transcode, /Work/Remux, /Work/Audio} renders within 1s on first load.
C2. List query reads MediaFiles.WorkBucket (GENERATED column) -- no Python derivation.
C3. Single-row admission writes a TranscodeQueue row only if MediaFile's WorkBucket matches the page's bucket (no cross-bucket leak).

## Cross-Vertical Contract

### Columns the WorkBucket vertical WRITES

| Column | Written by |
|---|---|
| TranscodeQueue row INSERT | AdmitToQueue (single-row admission only; bulk admission goes through TranscodeQueue vertical) |

### Columns READS

| Column | Read by | Owner |
|---|---|---|
| MediaFiles.{Id, FilePath, FileName, WorkBucket, AssignedProfile, Resolution, AudioCodec, AudioLanguages, OperationsNeededCsv} | List queries | per-vertical (WorkBucket is GENERATED) |
| TranscodeQueue.{Id, MediaFileId, Status} | "Already queued" filter | TranscodeQueue |

### Stable function entry points

None for external callers. Self-contained UI vertical.

### HTTP API surface

| Method + URL | Purpose |
|---|---|
| GET /Work/<bucket> | Render the per-bucket landing page |
| GET /api/WorkBucket/<bucket> | Paginated list JSON |
| POST /api/WorkBucket/<bucket>/Queue/<MediaFileId> | One-row admission |

### What is EXPLICITLY NOT a contract

- The per-row column set rendered -- adjustable
- Whether single-row admission validates per the full compliance predicate or trusts WorkBucket -- today trusts the GENERATED column
- The URL parameter format (`url_key` vs `bucket_name`) -- internal mapping
