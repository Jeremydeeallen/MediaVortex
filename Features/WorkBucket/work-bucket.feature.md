# WorkBucket -- grouped-by-series operator surface for /Work/<bucket>

**Slug:** work-bucket

## What It Does

Renders `/Work/Transcode`, `/Work/Remux`, `/Work/Audio`, `/Work/Compliant`, and `/Work/Unclassified` as always-grouped-by-series views. Work-needed buckets (Transcode/Remux/Audio) expose file count, total GB, common resolution/codec, InQueue badge, per-series profile dropdown, and a Queue-all button. `Compliant` is browse/audit-only -- no Queue-all button; the operator can still force-enqueue a compliant file via the single-file admit route + quality-tier query param. `Unclassified` surfaces in-flight rows (probe hook not yet complete) plus permanently-deferred rows (`audio_corrupt_suspect`, `no_audio_stream`); action is force-decide (re-run compliance) or defer forever. Every scanned MediaFile lands in exactly one of the five buckets by construction -- `WorkBucket IS NULL` is impossible for probe-complete rows.

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

C1. `/Work/Transcode`, `/Work/Remux`, `/Work/Audio`, `/Work/Compliant`, `/Work/Unclassified` each render only `MediaFiles.WorkBucket = <X>` rows. Spot-checkable: `SELECT WorkBucket FROM MediaFiles WHERE Id IN (...the ids surfaced by /api/Work/Transcode...)` returns only `Transcode`.

C2. Series rows default-sorted by total GB descending; secondary file-row sort by size desc. `Sort: File count desc` and `Sort: Series name asc` are alternative sort modes via the toolbar.

C3. Setting a profile on a series row writes `SeriesProfiles.AssignedProfile` AND updates `MediaFiles.AssignedProfile` for every untranscoded file in the series. Re-scanned files inherit via the existing `BackfillProfileAssignments` cascade.

C4. Queue-all is idempotent. A second click never produces duplicate Pending rows; reports `AlreadyQueued = N` instead of `Inserted = N` on retry.

C5. Per-row Queue is idempotent. Returns `'queued'` first time, `'already_queued'` subsequently.

C6. Filters: multi-select drive + free-text series search. Pagination: 25 rows per page server-side via `Core.Querying.PagedQueryBuilder`.

C7. `WorkBucket` is a GENERATED column derived exclusively from the three compliance flags: `WHEN videocompliant IS NULL OR containercompliant IS NULL OR audiocompliant IS NULL THEN 'Unclassified' / WHEN videocompliant AND containercompliant AND audiocompliant THEN 'Compliant' / WHEN NOT videocompliant THEN 'Transcode' / WHEN NOT containercompliant THEN 'Remux' / ELSE 'AudioFix'`. Every MediaFile row has a non-NULL bucket. `TranscodedByMediaVortex` is METADATA (which files we produced) and MUST NOT influence WorkBucket. Verifiable: `SELECT generation_expression FROM information_schema.columns WHERE table_name='mediafiles' AND column_name='workbucket'` returns the five-branch CASE.

C8. Every compliance evaluator is profile-independent. `AudioVertical.Evaluate`, `VideoVertical.Evaluate`, and `ContainerVertical.Evaluate` read baseline rules from `AudioComplianceRules`/`VideoComplianceRules`/`ContainerComplianceRules` respectively and return `(True|False|None, str|None)` without invoking `EffectiveProfileResolver`. `AssignedProfile` is a HINT for auto-enqueue paths only; it is never a compliance input. Verifiable: `grep -n "EffectiveProfileResolver" Features/VideoEncoding/VideoVertical.py Features/ContainerFormat/ContainerVertical.py Features/AudioNormalization/AudioVertical.py` returns 0 lines. Contract test `Tests/Contract/TestVerticalsAreProfileIndependent.py` asserts each vertical accepts a MediaFile with `AssignedProfile=NULL` and returns a decision without raising.

C9. `AdmitSeries` returns a per-outcome tally: `Inserted`, `AlreadyQueued`, `Skipped`, `AdmissionDeferred`, `Errored`. Sum of the five equals `Total`. No outcome is collapsed into another (prior bug: skipped / deferred / errored all fell into `AlreadyQueued`, hiding the reason files never queued). Verifiable: `Tests/Contract/TestQueueAdmissionAppService.py::test_admit_series_returns_admission_result`.

C10. Every admission (single-file + bulk) routes through `Features/TranscodeQueue/QueueManagementBusinessService.AddJobToQueue`. Repository-layer refusal policies are forbidden -- policy lives at the app-service, data access lives at the repository (SRP). Verifiable: `grep -n "return 0" Features/TranscodeQueue/TranscodeQueueRepository.py` returns zero lines inside `SaveTranscodeQueueItem`.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | Controller -> SeriesQueryRepository | `WorkBucketController.list_series` | `(BucketKey, PagedQuery, SortSpec, FilterSpec)` | Returns `PagedQueryResult[Series]` | `Tests/Contract/TestSeriesQueryRepository.py` |
| S2 | Controller -> FilesInSeriesRepository | `WorkBucketController.list_files_in_series` | `(SeriesIdentity, BucketKey)` | Returns `list[MediaFileRow]` | `Tests/Contract/TestFilesInSeriesRepository.py` |
| S3 | Controller -> SeriesProfileService | `WorkBucketController.set_series_profile` | `(SeriesIdentity, RawProfileName: str)` | Raises `InvalidProfileError` on bad input; otherwise returns `FilesAffected: int` | `Tests/Contract/TestSeriesProfileService.py` |
| S4 | SeriesProfileService -> SeriesProfileRepository | `SeriesProfileService.SetProfile` | UPSERT (StorageRootId, RelativePath, AssignedProfile) | Row present on subsequent `GetProfile` | `Tests/Contract/TestSeriesProfileRepository.py` |
| S5 | SeriesProfileService -> MediaFiles | `SeriesProfileService.SetProfile` | `UPDATE MediaFiles SET AssignedProfile = ? WHERE ... AND TranscodedByMediaVortex IS NOT TRUE` | `MediaFiles.AssignedProfile` reflects choice for untranscoded files only | `Tests/Contract/TestSeriesProfileService.py::test_set_profile_updates_only_untranscoded_files` |
| S6 | QueueAdmissionAppService -> QueueManagementBusinessService -> TranscodeQueue | `QueueAdmissionAppService.AdmitSeries` delegates per-file to `QueueManagementBusinessService.AddJobToQueue` | INSERT via `SaveTranscodeQueueItem` with `ON CONFLICT (MediaFileId) WHERE Status='Pending' AND TestVariantSetId IS NULL DO NOTHING RETURNING Id` against partial unique index `idx_transcodequeue_pending_per_mediafile` | Atomic dedup at DB level (concurrent admissions serialized by PG without exceptions); AudioPolicyJson populated at insert time | `Tests/Contract/TestQueueAdmissionAppService.py::test_admit_series_returns_admission_result` |
| S7 | BackfillProfileAssignments -> SeriesProfiles | `Scripts/SQLScripts/BackfillProfileAssignments.py` | reads sp.AssignedProfile, writes MediaFiles.AssignedProfile | New files in an existing series get the sticky profile | manual smoke: insert a MediaFiles row with the right show folder, run backfill, observe AssignedProfile populated |

## Status

**Phase:** Active feature. The old narrow WorkBucket surface (single-file admit only) and the Media-tab vertical have both been retired; this expanded contract is the sole operator entry point for bucket-level work.

**Files:**

- `Features/WorkBucket/WorkBucketController.py` -- HTTP routes only
- `Features/WorkBucket/Domain/` -- value objects + aggregates (SeriesIdentity, BucketKey, ProfileName, Series, MediaFileRow, SortSpec, FilterSpec, AdmissionResult)
- `Features/WorkBucket/Repositories/SeriesQueryRepository.py` -- grouped paged query
- `Features/WorkBucket/Repositories/FilesInSeriesRepository.py` -- expanded file list
- `Features/WorkBucket/Repositories/SeriesProfileRepository.py` -- SeriesProfiles CRUD
- `Features/TranscodeQueue/QueueManagementBusinessService.py` -- canonical queue admission entry point (AddJobToQueue)
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
| `TranscodeQueue` row INSERT (`ProcessingMode`, `Status='Pending'`, ...) | `QueueAdmissionAppService.AdmitOne` / `AdmitSeries` → `QueueManagementBusinessService.AddJobToQueue` (canonical admission path; ON CONFLICT DO NOTHING against `idx_transcodequeue_pending_per_mediafile`) |

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
