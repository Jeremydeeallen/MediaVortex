# WorkBucket -- grouped-by-series operator surface for /Work/<bucket>

**Slug:** work-bucket

## What It Does

Renders `/Work/Transcode`, `/Work/Remux`, and `/Work/Audio` as an always-grouped-by-series view of files that need work in that bucket. Each series row exposes file count, total GB, common resolution/codec, an InQueue badge, a per-series profile dropdown, and a Queue-all button. Series rows expand inline to show their files, sorted by size. The page replaces the old Media tab (the retired per-show-settings UI); per-series sticky profile assignment is preserved in the internal `SeriesProfiles` table.

## Workflows

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | Browse series needing work in a bucket | `/Work/<bucket>` page | GET `/Work/<bucket>` | `WorkBucketController.render_page` (`Features/WorkBucket/WorkBucketController.py`) |
| W2 | Paginate / sort / filter the series list | toolbar + pager | GET `/api/Work/<bucket>` | `SeriesQueryRepository.ListSeriesByBucket` (`Features/WorkBucket/Repositories/SeriesQueryRepository.py`) |
| W3 | Expand a series to see its files | row chevron | GET `/api/Work/<bucket>/Series/<sid>` | `FilesInSeriesRepository.ListFilesInSeries` (`Features/WorkBucket/Repositories/FilesInSeriesRepository.py`) |
| W4 | Set the profile on a series | series-row dropdown | POST `/api/Work/<bucket>/Series/<sid>/Profile` | `SeriesProfileService.SetProfile` (`Features/WorkBucket/Services/SeriesProfileService.py`) |
| W5 | Clear the profile on a series | dropdown -> blank | DELETE `/api/Work/<bucket>/Series/<sid>/Profile` | `SeriesProfileService.ClearProfile` (`Features/WorkBucket/Services/SeriesProfileService.py`) |
| W6 | Queue every file in a series | Queue-all button | POST `/api/Work/<bucket>/Series/<sid>/Queue` | `QueueAdmissionAppService.AdmitSeries` (`Features/WorkBucket/Services/QueueAdmissionAppService.py`) |
| W7 | Queue a single file | per-row Queue button | POST `/api/Work/<bucket>/Queue/<id>` | `QueueAdmissionAppService.AdmitOne` (`Features/WorkBucket/Services/QueueAdmissionAppService.py`) |

## Success Criteria

C1. `/Work/Transcode`, `/Work/Remux`, and `/Work/Audio` each render only `MediaFiles.WorkBucket = <X>` rows. Spot-checkable: `SELECT WorkBucket FROM MediaFiles WHERE Id IN (...the ids surfaced by /api/Work/Transcode...)` returns only `Transcode`.

C2. Series rows default-sorted by total GB descending; secondary file-row sort by size desc. `Sort: File count desc` and `Sort: Series name asc` are alternative sort modes via the toolbar.

C3. Setting a profile on a series row writes `SeriesProfiles.AssignedProfile` AND updates `MediaFiles.AssignedProfile` for every untranscoded file in the series. Re-scanned files inherit via the existing `BackfillProfileAssignments` cascade.

C4. Queue-all is idempotent. A second click never produces duplicate Pending rows; reports `AlreadyQueued = N` instead of `Inserted = N` on retry.

C5. Per-row Queue is idempotent. Returns `'queued'` first time, `'already_queued'` subsequently.

C6. Filters: multi-select drive + free-text series search. Pagination: 25 rows per page server-side via `Core.Querying.PagedQueryBuilder`.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | Controller -> SeriesQueryRepository | `WorkBucketController.list_series` | `(BucketKey, PagedQuery, SortSpec, FilterSpec)` | Returns `PagedQueryResult[Series]` | `Tests/Contract/TestSeriesQueryRepository.py` |
| S2 | Controller -> FilesInSeriesRepository | `WorkBucketController.list_files_in_series` | `(SeriesIdentity, BucketKey)` | Returns `list[MediaFileRow]` | `Tests/Contract/TestFilesInSeriesRepository.py` |
| S3 | Controller -> SeriesProfileService | `WorkBucketController.set_series_profile` | `(SeriesIdentity, RawProfileName: str)` | Raises `InvalidProfileError` on bad input; otherwise returns `FilesAffected: int` | `Tests/Contract/TestSeriesProfileService.py` |
| S4 | SeriesProfileService -> SeriesProfileRepository | `SeriesProfileService.SetProfile` | UPSERT (StorageRootId, RelativePath, AssignedProfile) | Row present on subsequent `GetProfile` | `Tests/Contract/TestSeriesProfileRepository.py` |
| S5 | SeriesProfileService -> MediaFiles | `SeriesProfileService.SetProfile` | `UPDATE MediaFiles SET AssignedProfile = ? WHERE ... AND TranscodedByMediaVortex IS NOT TRUE` | `MediaFiles.AssignedProfile` reflects choice for untranscoded files only | `Tests/Contract/TestSeriesProfileService.py::test_set_profile_updates_only_untranscoded_files` |
| S6 | QueueAdmissionRepository -> TranscodeQueue | `QueueAdmissionRepository.AdmitSeries` | bulk INSERT with `NOT EXISTS` Pending guard | No duplicate Pending row per MediaFileId | `Tests/Contract/TestQueueAdmissionRepository.py::test_admit_series_idempotent` |
| S7 | BackfillProfileAssignments -> SeriesProfiles | `Scripts/SQLScripts/BackfillProfileAssignments.py` | reads sp.AssignedProfile, writes MediaFiles.AssignedProfile | New files in an existing series get the sticky profile | manual smoke: insert a MediaFiles row with the right show folder, run backfill, observe AssignedProfile populated |

## Known Gaps

Architectural debts identified during the work-transcode-unified directive's code review pass. Each is mechanical, behavior-preserving, and intended to be closed before any new feature ships on top of this vertical. Sequence them in order; each is independent.

- [ ] **G1** -- Extract `MediaFilesRepository.PropagateSeriesProfile(SeriesIdentity, ProfileName) -> int` so `SeriesProfileService.SetProfile` stops carrying raw `UPDATE MediaFiles` SQL. SRP: services orchestrate, repositories own SQL.
- [ ] **G2** -- Add `SeriesIdentity.FromMediaFilePath(StorageRootId: int, RelativePath: str) -> SeriesIdentity` classmethod that implements the "first path segment is the series key" rule once. Route `BackfillProfileAssignments.py._SeriesKey` to it. (SQL `split_part(RelativePath, '/', 1)` stays SQL but the Python contract has one owner.)
- [ ] **G3** -- Add `Domain/AdmitOneResult.py` frozen dataclass `(Status: str, QueueId: int)`. `QueueAdmissionRepository.AdmitOne` and `QueueAdmissionAppService.AdmitOne` both return it instead of `Tuple[str, int]`. Symmetric with `AdmissionResult`.
- [ ] **G4** -- `BackfillProfileAssignments.py` cascade-write path stops issuing raw `UPDATE MediaFiles` SQL. Route through a new `MediaFilesRepository.SetAssignedProfileForFile(MediaFileId: int, ProfileName: str, Source: str = 'series')` method instead.
- [ ] **G5** -- Extract `WorkBucket/Domain/ListSeriesRequest.py` VO with `FromQueryArgs(args) -> (PagedQuery, SortSpec, FilterSpec)` factory. `WorkBucketController.list_series` stops parsing query-strings inline; the VO owns the parsing contract.
- [ ] **G6** -- Add `ProfileRepository.IsFinalizedActive(ProfileName: str) -> bool`. `ProfileName` VO ctor and `EffectiveProfileResolver._IsFinalizedActive` both delegate to it. Single SQL site for the Draft=FALSE + Active=TRUE check.
- [ ] **G7** -- Delete the no-op `HAVING COUNT(*) > 0` clause in `SeriesQueryRepository.ListSeriesByBucket` (cargo-culted from the old GetShowsWithStats; a `GROUP BY` row by definition has >= 1 contributing row).

When all 7 are closed, delete this section. The Decisions Made section in the closing directive records the resolution.

## Status

**Phase:** Active feature. The old narrow WorkBucket surface (single-file admit only) and the Media-tab vertical have both been retired; this expanded contract is the sole operator entry point for bucket-level work.

**Files:**

- `Features/WorkBucket/WorkBucketController.py` -- HTTP routes only
- `Features/WorkBucket/Domain/` -- value objects + aggregates (SeriesIdentity, BucketKey, ProfileName, Series, MediaFileRow, SortSpec, FilterSpec, AdmissionResult)
- `Features/WorkBucket/Repositories/SeriesQueryRepository.py` -- grouped paged query
- `Features/WorkBucket/Repositories/FilesInSeriesRepository.py` -- expanded file list
- `Features/WorkBucket/Repositories/SeriesProfileRepository.py` -- SeriesProfiles CRUD
- `Features/WorkBucket/Repositories/QueueAdmissionRepository.py` -- TranscodeQueue inserts
- `Features/WorkBucket/Services/SeriesProfileService.py` -- validate + persist + propagate
- `Features/WorkBucket/Services/QueueAdmissionAppService.py` -- queue orchestration
- `Templates/WorkBucket.html` -- grouped UI
- `Tests/Contract/` -- contract tests per repository, service, VO, and controller

## Cross-Vertical Contract

### Columns the WorkBucket vertical WRITES

| Column | Written by |
|---|---|
| `SeriesProfiles.AssignedProfile` | `SeriesProfileService.SetProfile` |
| `MediaFiles.AssignedProfile`, `MediaFiles.AssignedProfileSource`, `MediaFiles.LastModifiedDate` | `SeriesProfileService.SetProfile` (untranscoded only) |
| `TranscodeQueue` row INSERT (`ProcessingMode`, `Status='Pending'`, ...) | `QueueAdmissionRepository.AdmitOne` / `AdmitSeries` |

### Columns READ

| Column | Read by | Owner |
|---|---|---|
| `MediaFiles.{Id, FileName, FileSize, SizeMB, StorageRootId, RelativePath, Resolution, ResolutionCategory, Codec, AudioCodec, AudioLanguages, VideoCompliantReason, ContainerCompliantReason, AudioCompliantReason, WorkBucket, AssignedProfile, TranscodedByMediaVortex}` | repositories | per-vertical (WorkBucket is GENERATED) |
| `SeriesProfiles.{StorageRootId, RelativePath, AssignedProfile}` | `SeriesProfileRepository`, `SeriesQueryRepository` | WorkBucket vertical |
| `TranscodeQueue.{Id, MediaFileId, Status}` | "AnyInQueue" + idempotency guard | TranscodeQueue |
| `Profiles.{ProfileName, Draft, Active}` | `ProfileName` VO ctor | Profiles |

### HTTP API surface

| Method + URL | Purpose |
|---|---|
| GET `/Work/<bucket>` | Render landing |
| GET `/api/Work/<bucket>` | Paged series list |
| GET `/api/Work/<bucket>/Series/<sid>` | Files in one series |
| POST `/api/Work/<bucket>/Series/<sid>/Profile` | Set series profile |
| DELETE `/api/Work/<bucket>/Series/<sid>/Profile` | Clear series profile |
| POST `/api/Work/<bucket>/Series/<sid>/Queue` | Queue all files in series |
| POST `/api/Work/<bucket>/Queue/<MediaFileId>` | Queue one file |

### What is EXPLICITLY NOT a contract

- The exact HTML structure inside `WorkBucket.html` -- internal layout choice.
- The list of sort options (extensible via `SortSpec`).
- The exact JSON keys inside the `Data` envelope -- expand freely; consumers (only the template) update in lockstep.
