# WorkBucket flow -- request lifecycle for /Work/<bucket>

**Slug:** work-bucket-flow

## Entry point and stages

Every operator request that touches the WorkBucket surface enters at the Flask controller and fans out to a stage depending on the route:

```
HTTP request
    |
    v
ST1  WorkBucketController (route dispatch)
    |           |           |           |           |
    v           v           v           v           v
ST2  Page    ST3  Series  ST4  Files  ST5  Profile ST6  Queue
     render       list        expand      write        admit
     (HTML)       (JSON)      (JSON)      (JSON)       (JSON)
```

Each stage is stateless per request. No in-process caching between requests.

## Per-stage detail

### ST1 -- Controller dispatch (`Features/WorkBucket/WorkBucketController.py`)

Receives all `/Work/<bucket>` and `/api/Work/<bucket>/*` HTTP requests. Parses `url_key` into a `BucketKey` VO (validates bucket name against `{Transcode, Remux, Audio, Compliant, Unclassified}`; rejects unknown keys with 400). Routes to ST2-ST6 by method + path pattern. All error responses use `{'Success': False, 'Message': '...'}` envelope. `Compliant` bucket disables Queue-all + Queue-one write routes at the controller layer (browse-only). `Unclassified` bucket disables Set-profile route (files here have no profile-eligible state); Force-decide route recomputes compliance.

### ST2 -- Page render (`WorkBucketController.render_page`)

Produces the WorkBucket HTML landing page. Reads `BucketKey.Labels` to populate page-title and tab context. Returns `render_template('WorkBucket.html', ...)`. No DB reads at render time -- all data is loaded client-side via ST3.

### ST3 -- Paged series list (`SeriesQueryRepository.ListSeriesByBucket`)

Entry: `GET /api/Work/<bucket>?page=<n>&pageSize=<n>&sort=<s>&drive=<d>&search=<q>`

Builds a grouped SQL query against `MediaFiles` joined to `SeriesProfiles` (LEFT JOIN) and `StorageRoots`. Groups by `(StorageRootId, first path segment of RelativePath)`. Applies `WorkBucket = <bucket>` filter, optional drive filter, optional ILIKE series-name search. Orders by `SortSpec` (default: total GB desc). Returns paged `PagedQueryResult[Series]` where each `Series` aggregate carries: `StorageRootId`, `RelativePath`, `ShowName`, `TotalGB`, `FileCount`, `CommonResolution`, `CommonCodec`, `AssignedProfile`, `AnyInQueue`, `CompositeKey`.

### ST4 -- Expand-series file list (`FilesInSeriesRepository.ListFilesInSeries`)

Entry: `GET /api/Work/<bucket>/Series/<sid>`

Parses `sid` into `SeriesIdentity` VO (StorageRootId + RelativePath). Queries `MediaFiles` for all rows matching the series identity and bucket. Returns `list[MediaFileRow]` sorted by `FileSize` desc. Each row carries: `Id`, `FileName`, `FileSize`, `SizeMB`, `Resolution`, `Codec`, `AudioCodec`, `AudioLanguages`, `AssignedProfile`, `WorkBucket`, `TranscodedByMediaVortex`.

### ST5 -- Profile write (`SeriesProfileService.SetProfile` / `ClearProfile`)

Entry: `POST /api/Work/<bucket>/Series/<sid>/Profile` or `DELETE .../Profile`

**Set path:** Validates `ProfileName` VO (queries `Profiles` table; rejects Draft/Inactive/unknown). Calls `SeriesProfileRepository.Upsert` to persist sticky row in `SeriesProfiles`. Calls bulk UPDATE on `MediaFiles.AssignedProfile` for all untranscoded files in the series. Returns `FilesAffected` count.

**Clear path:** Calls `SeriesProfileRepository.Delete`. Returns 200 with no body fields beyond `{'Success': True}`.

### ST6 -- Queue admit (`QueueAdmissionAppService.AdmitSeries` / `AdmitOne`)

Entry: `POST /api/Work/<bucket>/Series/<sid>/Queue` or `POST /api/Work/<bucket>/Queue/<id>`

**Series path:** Loads all file IDs in the series via `FilesInSeriesRepository`. For each file, calls `QueueAdmissionAppService.AdmitOne` (the wrapper delegates to `QueueManagementBusinessService.AddJobToQueue`). Returns `AdmissionResult(Inserted, AlreadyQueued, Total)`.

**Single-file path:** Calls `QueueAdmissionAppService.AdmitOne` directly. Returns `{'queued'|'already_queued'}`.

The underlying `QueueManagementBusinessService.AddJobToQueue` uses `INSERT ... ON CONFLICT (MediaFileId) WHERE Status='Pending' AND TestVariantSetId IS NULL DO NOTHING RETURNING Id`. The partial unique index `idx_transcodequeue_pending_per_mediafile` enforces "at most one non-variant Pending row per MediaFileId" atomically at the DB level; PostgreSQL serializes concurrent INSERTs and silently no-ops the losers. Caller distinguishes via `fetchone()`: row returned → inserted; `None` → already-queued. Race-safe by construction (see `TranscodeQueue.feature.md` Concurrency Notes).

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | ST1 -> ST3 | `WorkBucketController.list_series` | `(BucketKey, page: int, pageSize: int, SortSpec, FilterSpec)` | `SeriesQueryRepository.ListSeriesByBucket` returns `PagedQueryResult[Series]` | `Tests/Contract/TestSeriesQueryRepository.py` |
| S2 | ST1 -> ST4 | `WorkBucketController.list_files_in_series` | `(SeriesIdentity, BucketKey)` from parsed `sid` + `url_key` | `FilesInSeriesRepository.ListFilesInSeries` returns `list[MediaFileRow]` sorted size desc | `Tests/Contract/TestFilesInSeriesRepository.py` |
| S3 | ST1 -> ST5 | `WorkBucketController.set_series_profile` | `(SeriesIdentity, RawProfileName: str)` from request body | `SeriesProfileService.SetProfile` raises `InvalidProfileError` on bad name; returns `FilesAffected: int` on success | `Tests/Contract/TestSeriesProfileService.py` |
| S4 | ST5 -> DB SeriesProfiles | `SeriesProfileService.SetProfile` | UPSERT `(StorageRootId, RelativePath, AssignedProfile)` ON CONFLICT DO UPDATE | `SeriesProfileRepository.GetProfile` returns the upserted row on subsequent call | `Tests/Contract/TestSeriesProfileRepository.py` |
| S5 | ST5 -> DB MediaFiles | `SeriesProfileService.SetProfile` | `UPDATE MediaFiles SET AssignedProfile=? WHERE StorageRootId=? AND first-segment(RelativePath)=? AND TranscodedByMediaVortex IS NOT TRUE` | All untranscoded files in the series reflect new profile; transcoded files unchanged | `Tests/Contract/TestSeriesProfileService.py::test_set_profile_updates_only_untranscoded_files` |
| S6 | ST6 -> DB TranscodeQueue | `QueueAdmissionAppService.AdmitOne` → `QueueManagementBusinessService.AddJobToQueue` | `INSERT INTO TranscodeQueue (...) VALUES (...) ON CONFLICT (MediaFileId) WHERE Status='Pending' AND TestVariantSetId IS NULL DO NOTHING RETURNING Id` against partial unique index `idx_transcodequeue_pending_per_mediafile` | `fetchone()` returns row → inserted; returns `None` → already-queued. Atomic at DB level; concurrent admissions serialized by PostgreSQL's unique-index conflict handling without raising an exception | `Tests/Contract/TestQueueAdmissionAppService.py::test_admit_one_is_idempotent` and `::test_admit_series_idempotent` + 10-thread concurrent admission stress test (1 winner, 9 silent no-ops, exactly 1 final Pending row) |
