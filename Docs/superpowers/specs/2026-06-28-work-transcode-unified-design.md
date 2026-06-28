# Unified /Work/<bucket> Pages + Retirement of the Media Tab

**Date:** 2026-06-28
**Slug:** work-transcode-unified
**Status:** Design (pending operator review)

## Outcome

The three bucket landing pages — `/Work/Transcode`, `/Work/Remux`, `/Work/Audio` — become the single operator surface for browsing files that need work, choosing a profile per series, and admitting work to the queue. They render an always-grouped view by series (first path segment under each StorageRoot), with size-sorted series rows that expand to size-sorted file rows. The Media tab (`/ShowSettings`) and every artifact behind it is deleted; the per-series profile data it owned survives as a renamed internal storage table consumed by the WorkBucket vertical.

## Success Criteria

**Operator-observable (the bar the user set):**

1. C1. `/Work/Transcode`, `/Work/Remux`, and `/Work/Audio` each render only files where `MediaFiles.WorkBucket` matches the URL. No file from another bucket appears anywhere on the page.
2. C2. Rows are grouped by series (`StorageRootId` + first segment of `RelativePath`). The default sort is series total GB descending. Series rows expand inline to show the files belonging to that series, sorted by size descending.
3. C3. Each series row has a profile control. Changing it applies the selected profile to every untranscoded file in the series (`MediaFiles.AssignedProfile`) AND persists the choice in `SeriesProfiles` so files scanned later inherit it via the existing `BackfillProfileAssignments` cascade.
4. C4. A "Queue all" action on a series row inserts a `TranscodeQueue` Pending row for every file in the series with no existing Pending row. Re-clicking it is idempotent.
5. C5. A per-row Queue button on an expanded file row inserts a single Pending row, idempotently.
6. C6. The page exposes drive filter, free-text series-name search, sort selection, and 25-per-page server-side pagination.

**Cleanup (deletion is observable):**

7. C7. `GET /ShowSettings` returns 404. The top-nav "Media" entry is gone from `Templates/Base.html`.
8. C8. `Features/ShowSettings/` does not exist (no controller, repository, models, feature docs, flow docs, `__init__.py`, or template).
9. C9. `Templates/ShowSettings.html` does not exist.
10. C10. Every `/api/ShowSettings/*` endpoint returns 404 (Flask routes deleted).
11. C11. The audit test `Tests/Contract/TestNoShowSettingsReferences.py` passes — no surviving Python or template references to the deleted vertical (rename migration and archived directive docs are the only exemptions).

**Data-integrity (deletion does not lose operator config):**

12. C12. Every row in the historical `ShowSettings` table (post-rename: `ShowSettings_DEPRECATED_2026_06_28`) has a corresponding row in `SeriesProfiles` after the migration runs. Re-running the migration is a no-op.
13. C13. `Scripts/SQLScripts/BackfillProfileAssignments.py` continues to function — it reads `SeriesProfiles` and writes `MediaFiles.AssignedProfile`.
14. C14. `EffectiveProfileResolver` is unchanged in behavior — it reads `MediaFiles.AssignedProfile` (already populated by the cascade) and falls back through SystemSettings.DefaultProfileName → `_PreMigrationDefault`.

**Rename-then-drop hygiene (operator policy):**

15. C15. After step 11, `pg_tables` contains `ShowSettings_DEPRECATED_2026_06_28` (not `ShowSettings`) and `pg_indexes` contains `idx_mediafiles_smartpopulate_DEPRECATED_2026_06_28` (not the original name). The drop migration script `DropDeprecatedShowSettingsArtifacts.py` is committed to `Scripts/SQLScripts/` but not executed by the directive.
16. C16. The audit test additionally scans for surviving production references to the deprecated names — code MUST NOT read `ShowSettings_DEPRECATED_*` either. The marker exists for ad-hoc operator visibility only.

These criteria pass the five litmus tests in `.claude/rules/feature-criteria.md` (rename / outsider / rewrite / negation / stability).

## Architecture (DDD layering + SOLID)

One vertical dies, one vertical expands. The expansion is layered cleanly so each file has one reason to change.

### Layering

```
HTTP layer ─── Features/WorkBucket/WorkBucketController.py
                  │ routes only, no SQL, no business logic
                  ▼
App services ─ Features/WorkBucket/Services/
                  SeriesProfileService.py
                  QueueAdmissionAppService.py
                  │ orchestrate use cases; no SQL
                  ▼
Domain ─────── Features/WorkBucket/Domain/
                  SeriesIdentity.py        (value object)
                  BucketKey.py             (value object)
                  ProfileName.py           (value object — refuses draft/inactive)
                  Series.py                (aggregate root)
                  MediaFileRow.py          (entity)
                  │ pure Python, no IO
                  ▼
Repositories ─ Features/WorkBucket/Repositories/
                  SeriesQueryRepository.py        (read-only, paged)
                  FilesInSeriesRepository.py      (read-only)
                  SeriesProfileRepository.py      (read/write SeriesProfiles)
                  QueueAdmissionRepository.py     (write TranscodeQueue)
                  │ each file owns one table family
                  ▼
DB ──────────  MediaFiles, SeriesProfiles, TranscodeQueue, Profiles, SystemSettings
```

### SOLID alignment

- **SRP:** the existing `WorkBucketRepository.py` (queries + writes + admission, all in one) is split into four focused repositories. Controller carries HTTP only.
- **OCP:** `SortSpec` and `FilterSpec` are extension points — adding a new sort option means a new enum value + one new switch arm in `SeriesQueryRepository`, no changes to the controller or services.
- **LSP:** repositories are concrete classes (project convention per `CLAUDE.md`); they substitute through identical method signatures, but tests do not mock — they exercise the real database (per `feedback_no_production_value_changes_for_testing.md`: integration tests hit real DB, contract tests live in `Tests/Contract/`).
- **ISP:** `SeriesProfileService` depends on `SeriesProfileRepository` + a write helper for `MediaFiles.AssignedProfile`. It does not see queue or query interfaces.
- **DIP:** services receive repositories via constructor injection (existing project pattern — see `EffectiveProfileResolver` ctor).

### Deleted

- `Features/ShowSettings/` (entire directory — controller, repository, models, `ShowSettings.feature.md`, `smart-populate.feature.md`, `smart-populate.flow.md`, `remux-populate-card.feature.md`, `__init__.py`, `__pycache__/`)
- `Templates/ShowSettings.html`
- The Flask blueprint registration for `show_settings` in `WebService/Main.py`
- The `/ShowSettings` link in `Templates/Base.html`
- All `/api/ShowSettings/*` endpoints — no surviving consumer outside the deleted template
- Cross-vertical pointer lines in surviving feature/flow docs that reference the deleted vertical (`transcode.flow.md`, `Features/TranscodeQueue/*.feature.md`, `Features/TranscodeQueue/media-tabs.flow.md`, `Features/FailureAccounting/*`, etc.) — rewritten to point at the new home or struck cleanly per `R14` (no annotation lines)

### Rename-then-drop pattern for unused SQL objects (operator policy)

Per operator policy, every SQL object that becomes unused in this directive is **renamed to a deprecated marker first**, smoke-tested, and only dropped in a follow-up migration after soak. The deprecated marker is the literal suffix `_DEPRECATED_2026_06_28`. The reason: anyone running ad-hoc SQL against an old name gets an obvious "this is gone" signal instead of a "table doesn't exist" mystery; the audit grep can scan for the marker to confirm no surviving production references.

Objects this rule applies to in this directive:

| Object | Kind | New name (live) | Deprecated name (post-rename, pre-drop) |
|---|---|---|---|
| `ShowSettings` | TABLE | `SeriesProfiles` (new table created alongside, populated, then old renamed away) | `ShowSettings_DEPRECATED_2026_06_28` |
| `idx_mediafiles_smartpopulate` | INDEX | (none — query path deleted) | `idx_mediafiles_smartpopulate_DEPRECATED_2026_06_28` |

Migration scripts (all idempotent; safe to re-run):

- `Scripts/SQLScripts/CreateSeriesProfilesAndDeprecateShowSettings.py` — one atomic transaction: `CREATE TABLE SeriesProfiles (...)`; `INSERT INTO SeriesProfiles SELECT ... FROM ShowSettings`; `ALTER TABLE ShowSettings RENAME TO ShowSettings_DEPRECATED_2026_06_28`. Recreates the unique index on the new table; the deprecated table's index gets implicitly renamed by Postgres.
- `Scripts/SQLScripts/DeprecateSmartPopulateIndex.py` — `ALTER INDEX idx_mediafiles_smartpopulate RENAME TO idx_mediafiles_smartpopulate_DEPRECATED_2026_06_28` (only after `/api/ShowSettings/SmartPopulate` route is gone, so no live query relies on it).
- `Scripts/SQLScripts/BackfillProfileAssignments.py` updated to read `SeriesProfiles` in the same commit as the table rename.
- `Scripts/SQLScripts/DropDeprecatedShowSettingsArtifacts.py` — separate follow-up migration. Drops `ShowSettings_DEPRECATED_2026_06_28` and `idx_mediafiles_smartpopulate_DEPRECATED_2026_06_28`. Runs after the soak window per `ceo-mode.md` operator authority on destructive operations.

### Expanded — `Features/WorkBucket/`

New file layout (replacing the current two-file shape):

```
Features/WorkBucket/
  WorkBucketController.py            (slimmed: HTTP routes only)
  Domain/
    SeriesIdentity.py                (StorageRootId, RelativePath VO)
    BucketKey.py                     (Transcode | Remux | AudioFixOnly VO)
    ProfileName.py                   (validated VO)
    Series.py                        (aggregate)
    MediaFileRow.py                  (entity)
    SortSpec.py                      (enum: TotalGBDesc | FileCountDesc | NameAsc)
    FilterSpec.py                    (StorageRootIds[], SearchTerm)
    AdmissionResult.py               (Inserted, AlreadyQueued, Total)
  Repositories/
    SeriesQueryRepository.py
    FilesInSeriesRepository.py
    SeriesProfileRepository.py
    QueueAdmissionRepository.py
  Services/
    SeriesProfileService.py
    QueueAdmissionAppService.py
  work-bucket.feature.md             (rewritten to reflect new contract)
```

## Components — Detail

### Value objects (`Features/WorkBucket/Domain/`)

- `SeriesIdentity(StorageRootId: int, RelativePath: str)` — `@dataclass(frozen=True)`. Method `ToCompositeKey() -> str` returns `f"{StorageRootId}:{RelativePath}"` for URL paths.
- `BucketKey` — frozen dataclass wrapping the canonical string. Class method `FromUrlKey(url_key: str) -> BucketKey | None` does the URL → bucket name lookup. The current `BUCKET_TO_URL_KEY` / `URL_LABELS` tables collapse into this VO.
- `ProfileName(Value: str)` — constructor calls `Profiles WHERE ProfileName=? AND Draft=FALSE AND Active=TRUE LIMIT 1`; raises `InvalidProfileError` if absent. Validation lives in one place.
- `Series` — `@dataclass(frozen=True)`: `Identity`, `Bucket`, `FileCount`, `TotalGB`, `CommonResolution`, `CommonCodec`, `AssignedProfile: Optional[str]`, `AnyInQueue`.
- `MediaFileRow` — `@dataclass(frozen=True)`: `Id, FileName, SizeGB, Resolution, AudioCodec, AudioLanguages, ComplianceReasons, InQueue`.
- `SortSpec` enum with `ToSql()` method.
- `FilterSpec` — `StorageRootIds: tuple[int, ...]`, `SearchTerm: str`. `ToSqlFragments() -> (where: str, params: tuple)` for parameterized injection-safe building.
- `AdmissionResult` — `Inserted, AlreadyQueued, Total` ints.

### Repositories

`SeriesQueryRepository.ListSeriesByBucket(Bucket, Paged, Sort, Filter) → PagedQueryResult[Series]` — single aggregate SQL via `Core.Querying.PagedQueryBuilder` (window-count for total). Filter and sort plug in via the VOs' `ToSql*` methods.

`FilesInSeriesRepository.ListFilesInSeries(Identity, Bucket, Sort) → list[MediaFileRow]` — simple ORDER BY mf.SizeMB DESC by default.

`SeriesProfileRepository.GetProfile(Identity) → Optional[str]`, `UpsertProfile(Identity, ProfileName) → None` (ON CONFLICT DO UPDATE), `DeleteProfile(Identity) → None`.

`QueueAdmissionRepository.AdmitOne(MediaFileId, ProcessingMode) → ('queued', QueueId) | ('already_queued', QueueId)` — preserves the existing semantics of `WorkBucketRepository.QueueOne`. `AdmitSeries(Identity, Bucket, ProcessingMode) → AdmissionResult` — bulk INSERT with `NOT EXISTS` guard, scoped by bucket + identity. Idempotent.

### Services

`SeriesProfileService.SetProfile(Identity, RawProfileName) → FilesAffected`:
1. `ProfileName(RawProfileName)` — VO validation (refuses draft/inactive)
2. `SeriesProfileRepository.UpsertProfile(Identity, name.Value)`
3. Bulk update via `DatabaseService.ExecuteNonQuery`:
   ```sql
   UPDATE MediaFiles
      SET AssignedProfile = %s,
          AssignedProfileSource = 'series',
          LastModifiedDate = NOW()
    WHERE StorageRootId = %s
      AND split_part(RelativePath, '/', 1) = %s
      AND TranscodedByMediaVortex = FALSE
   ```
4. Return rowcount via `RETURNING Id` count
5. LoggingService.LogInfo with affected count

`SeriesProfileService.ClearProfile(Identity)` — deletes the SeriesProfiles row. Does NOT clear `MediaFiles.AssignedProfile` (preserves history per the user's series-stickiness intent).

`QueueAdmissionAppService.AdmitSeries(Identity, Bucket)`: maps `BucketKey` → `ProcessingMode` via existing `BUCKET_TO_PROCESSING_MODE` constant (moves into `BucketKey` class method); delegates to repository.

### Controller

`WorkBucketController.py` — Flask blueprint. Every route is at most ~10 lines: parse args → invoke service/repository → jsonify envelope. Bucket key parsing via `BucketKey.FromUrlKey`; unknown → 404. Exception handler around each route logs via `LoggingService.LogException` and returns 500 with the standard envelope.

Routes (all return `{Success, Message, Data}`):

| Method | URL | Purpose |
|---|---|---|
| GET | `/Work/<url_key>` | Render `WorkBucket.html` |
| GET | `/api/Work/<url_key>` | Paged series list |
| GET | `/api/Work/<url_key>/Series/<sid>` | Files in one series |
| POST | `/api/Work/<url_key>/Series/<sid>/Profile` | Set series profile |
| DELETE | `/api/Work/<url_key>/Series/<sid>/Profile` | Clear series profile |
| POST | `/api/Work/<url_key>/Series/<sid>/Queue` | Queue all files in series |
| POST | `/api/Work/<url_key>/Queue/<MediaFileId>` | Queue one file |

The composite `<sid>` parses as `<StorageRootId>:<UrlEncodedShowName>`.

### Template

`Templates/WorkBucket.html` — replaces existing minimal template. Uses the shared table renderer (`Features/SharedTable/shared-table-renderer.feature.md`) for both series rows and the expanded file sub-table. Client-side state limited to the expand/collapse map; everything else is server-rendered on each request.

## Data flow

### Page load → grouped series list

1. `GET /Work/Transcode` → controller renders `WorkBucket.html` with `BucketKey='Transcode'`.
2. JS calls `GET /api/Work/Transcode?page=1&pageSize=25&sort=TotalGB.desc`.
3. `SeriesQueryRepository.ListSeriesByBucket(...)` builds:
   ```sql
   SELECT mf.StorageRootId,
          split_part(mf.RelativePath, '/', 1) AS ShowName,
          COUNT(*)::int AS FileCount,
          ROUND(SUM(mf.SizeMB)::numeric / 1024, 1) AS TotalGB,
          MODE() WITHIN GROUP (ORDER BY mf.ResolutionCategory) AS CommonResolution,
          MODE() WITHIN GROUP (ORDER BY mf.Codec) AS CommonCodec,
          sp.AssignedProfile,
          EXISTS (
            SELECT 1
              FROM TranscodeQueue tq
              JOIN MediaFiles m2 ON m2.Id = tq.MediaFileId
             WHERE tq.Status = 'Pending'
               AND m2.StorageRootId = mf.StorageRootId
               AND split_part(m2.RelativePath, '/', 1) = split_part(mf.RelativePath, '/', 1)
               AND m2.WorkBucket = mf.WorkBucket
          ) AS AnyInQueue,
          COUNT(*) OVER () AS __TotalCount
     FROM MediaFiles mf
     LEFT JOIN SeriesProfiles sp
            ON sp.StorageRootId = mf.StorageRootId
           AND sp.RelativePath  = split_part(mf.RelativePath, '/', 1)
    WHERE mf.WorkBucket = %s
      [AND mf.StorageRootId IN (%s, ...)]            -- FilterSpec
      [AND split_part(mf.RelativePath,'/',1) ILIKE %s]  -- SearchTerm (EscapeLikePattern + ESCAPE '!')
    GROUP BY mf.StorageRootId, split_part(mf.RelativePath, '/', 1), sp.AssignedProfile
   HAVING COUNT(*) > 0
   ORDER BY TotalGB DESC                              -- SortSpec
   LIMIT %s OFFSET %s
   ```
4. Response: `{Success, Data: {Series: [...], Total, Page, PageSize}}`. JS renders rows.

### Expand series → files

`GET /api/Work/Transcode/Series/3:House` →
`SELECT mf.Id, mf.FileName, ROUND(mf.SizeMB::numeric/1024,2) AS SizeGB, mf.Resolution, mf.AudioCodec, mf.AudioLanguages, mf.VideoCompliantReason, mf.ContainerCompliantReason, mf.AudioCompliantReason, EXISTS(...) AS InQueue FROM MediaFiles mf WHERE mf.WorkBucket=%s AND mf.StorageRootId=%s AND split_part(mf.RelativePath,'/',1)=%s ORDER BY mf.SizeMB DESC`

### Change series profile

1. `POST /api/Work/Transcode/Series/3:House/Profile {ProfileName: "h264-1080p-target"}`
2. `WorkBucketController.set_series_profile` → `SeriesProfileService.SetProfile(Identity, RawProfileName)`
3. Service validates via VO ctor → upserts SeriesProfiles row → bulk-updates MediaFiles.AssignedProfile for untranscoded rows in the series.
4. Response: `{Data: {FilesAffected: N}}`. JS updates the series row's profile badge and shows a toast.

### Queue all in series

`POST /api/Work/Transcode/Series/3:House/Queue` →
```sql
INSERT INTO TranscodeQueue (
  FileName, Directory, SizeBytes, SizeMB, MediaFileId, StorageRootId, RelativePath,
  ProcessingMode, Status, Priority, DateAdded
)
SELECT mf.FileName, '', COALESCE(mf.FileSize, 0), COALESCE(mf.SizeMB, 0), mf.Id,
       mf.StorageRootId, mf.RelativePath, %s, 'Pending', 100, NOW()
  FROM MediaFiles mf
 WHERE mf.WorkBucket = %s
   AND mf.StorageRootId = %s
   AND split_part(mf.RelativePath, '/', 1) = %s
   AND NOT EXISTS (
     SELECT 1 FROM TranscodeQueue tq
      WHERE tq.MediaFileId = mf.Id AND tq.Status = 'Pending'
   )
```

### Background coherence — new files inherit series profile

1. FileScanner inserts new MediaFiles row.
2. Generated column `WorkBucket` fires.
3. `BackfillProfileAssignments.py` (scheduled) walks NULL-AssignedProfile rows; reads `SeriesProfiles` for the (StorageRootId, first-segment) pair; if a row exists, writes `MediaFiles.AssignedProfile = sp.AssignedProfile`, `AssignedProfileSource='series'`.
4. New file appears under its series row with the sticky profile applied.

## Error handling

| Failure | Behavior |
|---|---|
| Unknown bucket in URL | `BucketKey.FromUrlKey` returns None → 404 `Error.html` |
| Draft/inactive profile in SetProfile | `ProfileName` VO ctor raises `InvalidProfileError` → 400 `{Success: false, Message: "Profile 'X' is not finalized or active"}` |
| Unknown SeriesIdentity (no matching MediaFiles) | `SetProfile` returns FilesAffected=0; controller returns 404 with `"No files match series 'X:Y' in bucket 'Z'"` |
| DB exception | `LoggingService.LogException` + 500 + standard envelope; JS toasts the message |
| Concurrent profile edits | UPSERT last-write-wins. No optimistic-lock layer — single-operator dev system |
| Empty series | Filtered out by `HAVING COUNT(*) > 0` in the aggregate query — never appears in the list |

Per `error-ux.md`:
- 10-second client-side timeout on every AJAX call.
- Loading spinner overlays the affected row, not the whole page.
- Success AND failure both surface a toast.

## Testing strategy

### Contract tests (`Tests/Contract/`)

- `TestSeriesQueryRepository.py` — HAVING clause excludes empty series; bucket filter respected; AssignedProfile pulled from SeriesProfiles when present, NULL when absent; AnyInQueue logic correct; TotalGB rounding correct; pagination via PagedQueryBuilder window-count.
- `TestSeriesProfileService.py` — VO refuses draft/inactive; UPSERT writes SeriesProfiles; bulk update touches only `TranscodedByMediaVortex=FALSE`; ClearProfile removes row but leaves MediaFiles intact.
- `TestQueueAdmissionRepository.py` — `AdmitOne` idempotent; `AdmitSeries` idempotent across reruns; scoped by bucket + identity; returns accurate counts.
- `TestWorkBucketController.py` — unknown-bucket 404, envelope shape, every route reachable.
- `TestProfileNameVO.py` — refuses draft, refuses inactive, refuses non-existent, accepts finalized-active.
- `TestSeriesIdentityVO.py` — equality by value, immutability, composite-key round-trip.

### Audit test (one-shot enforcement)

- `Tests/Contract/TestNoShowSettingsReferences.py` — grep production python + template tree for `ShowSettings`, `/api/ShowSettings/`, `Features/ShowSettings/`, AND the deprecated markers `ShowSettings_DEPRECATED_` / `idx_mediafiles_smartpopulate_DEPRECATED_`. Fails on any match outside the three migration scripts (`CreateSeriesProfilesAndDeprecateShowSettings.py`, `DeprecateSmartPopulateIndex.py`, `DropDeprecatedShowSettingsArtifacts.py`) and `.claude/directives/closed/`. The deprecated-name scan exists because the marker is for operator visibility in ad-hoc SQL only — production code MUST NOT depend on it.

### Pipeline smoke (`Tests/Pipeline/`)

End-to-end: scan a new file → series row appears in `/api/Work/Transcode` with FileCount=1 → set series profile → MediaFiles.AssignedProfile updated → queue series → TranscodeQueue Pending rows exist → claim path passes existing `TestClaimAuthority` invariants.

### Live verification per step (per `feedback_smoke_test_per_step_not_at_end.md`)

Each step's exit gate is a live deploy + browser/curl confirmation, not just unit-test green.

- After migration (step 3): `SELECT * FROM SeriesProfiles` returns rows copied from the original `ShowSettings`; `SELECT count(*) FROM ShowSettings_DEPRECATED_2026_06_28` matches `SELECT count(*) FROM SeriesProfiles`; `SELECT * FROM ShowSettings` errors (relation does not exist); `BackfillProfileAssignments.py` smoke runs and writes MediaFiles.AssignedProfile.
- After services scaffolded (step 2): contract tests green.
- After controller wired (step 5): curl `/api/Work/Transcode` round-trips grouped JSON.
- After template + deletion sweep (step 10): load `/Work/Transcode`, `/Work/Remux`, `/Work/Audio` in browser; expand a series; change a profile; queue the series; observe TranscodeQueue rows; visit `/ShowSettings` and confirm 404; confirm top-nav lacks the Media entry.
- After index deprecation (step 11): `SELECT indexname FROM pg_indexes WHERE indexname = 'idx_mediafiles_smartpopulate_DEPRECATED_2026_06_28'` returns one row; the original index name returns zero rows.
- After audit test landed (step 12): `py -m pytest Tests/Contract/TestNoShowSettingsReferences.py` green.
- **Post-soak (operator-driven, not in this directive's auto-flow):** `DropDeprecatedShowSettingsArtifacts.py` runs; `SELECT count(*) FROM pg_tables WHERE tablename ILIKE 'showsettings%'` returns 0; `SELECT count(*) FROM pg_indexes WHERE indexname ILIKE 'idx_mediafiles_smartpopulate%'` returns 0.

## Doc-layering deliverables

Per `.claude/rules/doc-layering.md`, the directive that implements this design must promote durable content into permanent homes at DELIVERING:

- `Features/WorkBucket/work-bucket.feature.md` — rewritten to describe the new contract (Workflows W1–W6, Seams S1–S6, Criteria C1–C14).
- `Features/WorkBucket/work-bucket.flow.md` — new file. Stages ST1 (URL→render) ST2 (paged series query) ST3 (expand→files) ST4 (set profile) ST5 (admit to queue) ST6 (background backfill). Seams table covers each transition.
- Cross-references in `transcode.flow.md`, `Features/TranscodeQueue/*.feature.md`, and other surviving docs are updated; pointers to deleted docs are either rewritten or struck cleanly (no annotation lines per `R14`).

## Migration ordering (rename-then-drop, irreversible-last)

Implementation order minimizes blast radius. Destructive DROP operations live in a separate follow-up migration that runs after the soak window, per the rename-then-drop policy. This directive lands everything through step 12; the DROP migration script is **authored** here but only **run** after soak with operator authority (per `ceo-mode.md`).

1. Domain VOs + repositories + services scaffolded (zero behavior change).
2. Contract tests for new code, all green.
3. `CreateSeriesProfilesAndDeprecateShowSettings.py` migration created and run on dev in one atomic transaction: new `SeriesProfiles` table created, data copied from `ShowSettings`, `ShowSettings` renamed to `ShowSettings_DEPRECATED_2026_06_28`. Verify row counts match.
4. `BackfillProfileAssignments.py` updated to read `SeriesProfiles`. Smoke runs against the new table.
5. `WorkBucketController` swaps to new routes. Old `WorkBucketRepository` methods (`CountByBucket`, `ListByBucket`, `QueueNext`, `QueueOne`) moved into the new SRP-focused repositories and deleted from the old file.
6. `WorkBucket.html` rewritten to the grouped-by-series shape. Existing minimal template replaced.
7. Surviving feature/flow docs swept for cross-references to `Features/ShowSettings/`. Pointers rewritten to the new home or struck cleanly (no annotation lines per R14).
8. `Features/ShowSettings/` directory deleted in one commit.
9. `Templates/ShowSettings.html` deleted.
10. Blueprint registration removed from `WebService/Main.py`. Top-nav link removed from `Templates/Base.html`. Live deploy. Verify `/ShowSettings` returns 404 and all three bucket pages render in the browser.
11. `DeprecateSmartPopulateIndex.py` migration runs — renames `idx_mediafiles_smartpopulate` to its deprecated marker (safe now: no production query references it).
12. Audit test `TestNoShowSettingsReferences.py` lands and goes green. `DropDeprecatedShowSettingsArtifacts.py` migration script is authored and committed (but **not run** in this directive).

**Soak + follow-up (separate operator-driven step, not in this directive's auto-flow):**

13. Operator runs `DropDeprecatedShowSettingsArtifacts.py` after at least 24h soak with no issues — drops `ShowSettings_DEPRECATED_2026_06_28` table and `idx_mediafiles_smartpopulate_DEPRECATED_2026_06_28` index. Operator authority per `ceo-mode.md` (destructive op).

## What this design explicitly does NOT change

- `EffectiveProfileResolver` — same cascade (MediaFile → SystemSettings.DefaultProfileName → `_PreMigrationDefault`).
- `WorkerCapabilityPredicate` — claim queries unchanged.
- `TranscodeQueue` table shape — same columns, same status machine.
- `MediaFiles.WorkBucket` generated-column logic — unchanged.
- The Bug, FailureAccounting, ContentClassifier, Profiles verticals — unchanged. Pointers in their docs to deleted ShowSettings docs get rewritten/struck only.

## Open questions for the operator to confirm

**Resolved by operator (2026-06-28):**

- ~~Whether destructive DROP runs in this directive or a follow-up.~~ **Resolved:** rename-then-drop pattern. Unused SQL objects get a `_DEPRECATED_2026_06_28` marker now; the DROP migration is authored in this directive but run only after smoke soak.

**Still parked:**

- Whether the audit test should treat archived directives (`.claude/directives/closed/`) as exempt (proposed: yes, since they're historical artifacts) or scrub them too.
