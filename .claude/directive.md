# Current Directive

**Set:** 2026-06-28
**Status:** Active -- phase: NEEDS_DOC_PREREAD
**Slug:** work-transcode-unified
**Replaces:** `directives/closed/2026-06-27-worker-runtime-state.md` (closed Success 2026-06-27)
**Spec:** `Docs/superpowers/specs/2026-06-28-work-transcode-unified-design.md`
**Plan:** `Docs/superpowers/plans/2026-06-28-work-transcode-unified.md`

## Outcome

The three bucket landing pages -- `/Work/Transcode`, `/Work/Remux`, `/Work/Audio` -- become the single operator surface for browsing files that need work, choosing a profile per series, and admitting work to the queue. They render an always-grouped view by series (first path segment under each StorageRoot), with size-sorted series rows that expand inline to size-sorted file rows. The Media tab (`/ShowSettings`) and every artifact behind it is deleted; the per-series profile data it owned survives as a renamed internal storage table (`SeriesProfiles`) consumed exclusively by the WorkBucket vertical. SQL objects that become unused are renamed with a `_DEPRECATED_2026_06_28` marker first; the drop migration is authored in this directive but only run after operator-approved soak.

## Acceptance Criteria

Each criterion passes the five litmus tests in `.claude/rules/feature-criteria.md` (rename / outsider / rewrite / negation / stability). Verbatim from `Docs/superpowers/specs/2026-06-28-work-transcode-unified-design.md`.

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
11. C11. The audit test `Tests/Contract/TestNoShowSettingsReferences.py` passes -- no surviving Python or template references to the deleted vertical (rename migration and archived directive docs are the only exemptions).

**Data-integrity (deletion does not lose operator config):**

12. C12. Every row in the historical `ShowSettings` table (post-rename: `ShowSettings_DEPRECATED_2026_06_28`) has a corresponding row in `SeriesProfiles` after the migration runs. Re-running the migration is a no-op.
13. C13. `Scripts/SQLScripts/BackfillProfileAssignments.py` continues to function -- it reads `SeriesProfiles` and writes `MediaFiles.AssignedProfile`.
14. C14. `EffectiveProfileResolver` is unchanged in behavior -- it reads `MediaFiles.AssignedProfile` (already populated by the cascade) and falls back through SystemSettings.DefaultProfileName -> `_PreMigrationDefault`.

**Rename-then-drop hygiene (operator policy):**

15. C15. After the index-deprecation step, `pg_tables` contains `ShowSettings_DEPRECATED_2026_06_28` (not `ShowSettings`) and `pg_indexes` contains `idx_mediafiles_smartpopulate_DEPRECATED_2026_06_28` (not the original name). The drop migration script `DropDeprecatedShowSettingsArtifacts.py` is committed to `Scripts/SQLScripts/` but not executed by the directive.
16. C16. The audit test additionally scans for surviving production references to the deprecated names -- code MUST NOT read `ShowSettings_DEPRECATED_*` either. The marker exists for ad-hoc operator visibility only.

## Out of Scope

- Dropping the deprecated table/index (separate post-soak operator step via `DropDeprecatedShowSettingsArtifacts.py`).
- `EffectiveProfileResolver` rewrite (it stays — reads `MediaFiles.AssignedProfile`, unchanged behavior).
- `WorkerCapabilityPredicate` / claim invariants (unchanged).
- `TranscodeQueue` table shape (same columns, same status machine).
- `MediaFiles.WorkBucket` generated-column logic (unchanged).
- Bug, FailureAccounting, ContentClassifier, Profiles verticals as functional units (only their pointers to deleted ShowSettings docs change).
- SubtitleFix bucket page (not in the user's "all three" scope today).
- New sort modes beyond Total GB desc / FileCount desc / Series name asc.

## Constraints

- DDD layering: Domain VOs, SRP-focused repositories, thin services, thin Flask controller. Each file owns one reason to change.
- Rename-then-drop pattern for every unused SQL object. No same-commit DROP.
- All migrations idempotent.
- Contract tests against live dev DB (no DB mocks per `feedback_no_production_value_changes_for_testing.md`).
- One logical change per commit (helper deletion + every caller in the SAME commit even when cross-file -- per `feedback_one_logical_change_per_commit.md`).
- Push to origin/main after every commit on main (`feedback_push_after_commit.md`).
- Live smoke per step (`feedback_smoke_test_per_step_not_at_end.md`): each step's exit gate is a live deploy + browser/curl confirmation, not just unit-test green.
- R12: no multi-line docstrings/comments in new code.
- R14: when sweeping cross-vertical doc references, delete sections rather than annotate.

## Escalation Defaults

- Tradeoff between code complexity and operator visibility -> operator visibility.
- Tradeoff between scope discipline and "while I'm here" cleanup -> scope discipline.
- Risk tolerance: low. Destructive operations (DROP) require explicit operator authority post-soak.
- When a criterion is ambiguous against real-world data, pick one interpretation, proceed, surface the choice in the Verification report.

## Engineering Calls Already Made

- The directive serves the broader operator goal: unify the "browse what needs work + sort by size + change profile + group by series" workflows currently split between `/Work/<bucket>` and `/ShowSettings`. The /ShowSettings page is deleted entirely; its functional value moves to `/Work/<bucket>`.
- Per-series profile assignment uses a sticky storage row (renamed `SeriesProfiles` table) so new files scanned into an existing series inherit via the existing `BackfillProfileAssignments` cascade.
- Always-grouped view (no flat-list toggle). Series rows expand inline. One mental model.
- Default sort: series total GB desc. Secondary: files-within-expanded-series by size desc.
- All three /Work/<bucket> pages get the same redesign in one pass (the user explicitly said "all three").
- DDD layering choice: Domain VOs in `Features/WorkBucket/Domain/`, SRP repositories in `Repositories/`, application services in `Services/`, thin controller. Each file ~one class, one reason to change.
- Rename-then-drop for every unused SQL object. Operator policy stated 2026-06-28.

## Status

Phase advances by editing the `**Status:**` header above. PreToolUse hook reads ONLY that header line. Standards in `.claude/standards/index.md`.

Phase machine: `NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING`.

This directive starts at `NEEDS_DOC_PREREAD` because the standards review (spec) and plan are both complete and committed. The first IMPLEMENTING task triggers the hook's colocated-doc-preread requirement for `Features/WorkBucket/work-bucket.feature.md` -- the implementer will Read it before its first Edit.

### Files

```
Features/WorkBucket/Domain/__init__.py                         -- CREATE: domain package
Features/WorkBucket/Domain/SeriesIdentity.py                   -- CREATE: (StorageRootId, RelativePath) VO
Features/WorkBucket/Domain/BucketKey.py                        -- CREATE: bucket name + URL + ProcessingMode + labels VO
Features/WorkBucket/Domain/ProfileName.py                      -- CREATE: validated profile VO
Features/WorkBucket/Domain/SortSpec.py                         -- CREATE: ORDER BY enum
Features/WorkBucket/Domain/FilterSpec.py                       -- CREATE: drive + search filter VO
Features/WorkBucket/Domain/AdmissionResult.py                  -- CREATE: queue admission result VO
Features/WorkBucket/Domain/Series.py                           -- CREATE: aggregate
Features/WorkBucket/Domain/MediaFileRow.py                     -- CREATE: file-row entity
Features/WorkBucket/Repositories/__init__.py                   -- CREATE
Features/WorkBucket/Repositories/SeriesQueryRepository.py      -- CREATE: grouped paged query
Features/WorkBucket/Repositories/FilesInSeriesRepository.py    -- CREATE: expand-series query
Features/WorkBucket/Repositories/SeriesProfileRepository.py    -- CREATE: SeriesProfiles CRUD
Features/WorkBucket/Repositories/QueueAdmissionRepository.py   -- CREATE: TranscodeQueue inserts
Features/WorkBucket/Services/__init__.py                       -- CREATE
Features/WorkBucket/Services/SeriesProfileService.py           -- CREATE: validate + persist + propagate
Features/WorkBucket/Services/QueueAdmissionAppService.py       -- CREATE: queue orchestration
Features/WorkBucket/WorkBucketController.py                    -- REWRITE: thin HTTP only
Features/WorkBucket/WorkBucketRepository.py                    -- DELETE: methods split into new repos
Features/WorkBucket/work-bucket.feature.md                     -- REWRITE: new contract
Features/WorkBucket/work-bucket.flow.md                        -- CREATE: ST1-ST6 + seams
Templates/WorkBucket.html                                      -- REWRITE: grouped UI
Templates/ShowSettings.html                                    -- DELETE
Templates/Base.html                                            -- EDIT: remove Media nav link
WebService/Main.py                                             -- EDIT: remove /ShowSettings route + ShowSettings blueprint
Features/ShowSettings/                                         -- DELETE: entire directory
Scripts/SQLScripts/CreateSeriesProfilesAndDeprecateShowSettings.py  -- CREATE: atomic migration
Scripts/SQLScripts/DeprecateSmartPopulateIndex.py              -- CREATE: index rename migration
Scripts/SQLScripts/DropDeprecatedShowSettingsArtifacts.py      -- CREATE: drop migration (NOT RUN)
Scripts/SQLScripts/BackfillProfileAssignments.py               -- EDIT: ShowSettings -> SeriesProfiles
Tests/Contract/TestSeriesIdentityVO.py                         -- CREATE
Tests/Contract/TestBucketKeyVO.py                              -- CREATE
Tests/Contract/TestProfileNameVO.py                            -- CREATE
Tests/Contract/TestSeriesQueryRepository.py                    -- CREATE
Tests/Contract/TestFilesInSeriesRepository.py                  -- CREATE
Tests/Contract/TestSeriesProfileRepository.py                  -- CREATE
Tests/Contract/TestQueueAdmissionRepository.py                 -- CREATE
Tests/Contract/TestSeriesProfileService.py                     -- CREATE
Tests/Contract/TestQueueAdmissionAppService.py                 -- CREATE
Tests/Contract/TestWorkBucketController.py                     -- CREATE (replaces TestWorkBucketRepository.py)
Tests/Contract/TestNoShowSettingsReferences.py                 -- CREATE: audit grep
Tests/Contract/TestWorkBucketRepository.py                     -- DELETE: superseded by new tests
transcode.flow.md                                              -- EDIT: sweep ShowSettings references
Features/TranscodeQueue/transcode-vs-remux-routing.feature.md  -- EDIT: sweep ShowSettings references
Features/TranscodeQueue/TranscodeQueue.feature.md              -- EDIT: sweep ShowSettings references
Features/TranscodeQueue/next-batch-per-drive.feature.md        -- EDIT: sweep ShowSettings references
Features/TranscodeQueue/media-tabs.flow.md                     -- EDIT: sweep ShowSettings references
Features/TranscodeQueue/media-tabs-and-loudness.feature.md     -- EDIT: sweep ShowSettings references
Features/TranscodeQueue/priority-materialization.feature.md    -- EDIT: sweep ShowSettings references
Features/TranscodeQueue/queue-priority.feature.md              -- EDIT: sweep ShowSettings references
Features/TranscodeQueue/QueueManagementBusinessService.py      -- EDIT: sweep ShowSettings references
Features/FailureAccounting/failure-accounting.feature.md       -- EDIT: sweep ShowSettings references
Features/FailureAccounting/failure-accounting.flow.md          -- EDIT: sweep ShowSettings references
Features/ContentClassifier/content-classifier.feature.md       -- EDIT: sweep ShowSettings references
Features/ContentClassifier/content-classifier.flow.md          -- EDIT: sweep ShowSettings references
Features/FileReplacement/remuxed-flag.feature.md               -- EDIT: sweep ShowSettings references
Features/SharedTable/shared-table-renderer.feature.md          -- EDIT: sweep ShowSettings references
Core/Querying/paged-query.feature.md                           -- EDIT: sweep ShowSettings references
```

### Progress

24 tasks per `Docs/superpowers/plans/2026-06-28-work-transcode-unified.md`. Status mirrors the TaskList.

- [ ] T1 SeriesIdentity VO
- [ ] T2 BucketKey VO
- [ ] T3 ProfileName VO
- [ ] T4 SortSpec / FilterSpec / AdmissionResult VOs
- [ ] T5 Series + MediaFileRow aggregates
- [ ] T6 SeriesQueryRepository
- [ ] T7 FilesInSeriesRepository
- [ ] T8 SeriesProfileRepository
- [ ] T9 QueueAdmissionRepository
- [ ] T10 SeriesProfileService
- [ ] T11 QueueAdmissionAppService
- [ ] T12 Migration: create SeriesProfiles + deprecate ShowSettings
- [ ] T13 Update BackfillProfileAssignments.py
- [ ] T14 Rewrite WorkBucketController + delete old repo
- [ ] T15 Rewrite Templates/WorkBucket.html
- [ ] T16 Sweep cross-vertical ShowSettings references
- [ ] T17 Delete Features/ShowSettings/ directory
- [ ] T18 Delete template + route + blueprint + nav link
- [ ] T19 Deprecate idx_mediafiles_smartpopulate
- [ ] T20 Audit test: no ShowSettings references
- [ ] T21 Author DropDeprecatedShowSettingsArtifacts.py (NOT RUN)
- [ ] T22 Rewrite work-bucket.feature.md
- [ ] T23 New work-bucket.flow.md
- [ ] T24 Verify criteria + advance directive to DELIVERING

### Promotions

Required when phase advances to DELIVERING. Populated incrementally per `feedback_promotions_grow_incrementally.md`: every step's commit that lands durable content into a feature/flow doc adds its row in the SAME commit.

| Source artifact | Target file | Commit |
|---|---|---|

### Verification

Required when phase advances to VERIFYING. One entry per acceptance criterion. Concrete evidence (command output, SQL result, file path), per `Docs/superpowers/plans/2026-06-28-work-transcode-unified.md` Task 24.

- **C1:** TBD
- **C2:** TBD
- **C3:** TBD
- **C4:** TBD
- **C5:** TBD
- **C6:** TBD
- **C7:** TBD
- **C8:** TBD
- **C9:** TBD
- **C10:** TBD
- **C11:** TBD
- **C12:** TBD
- **C13:** TBD
- **C14:** TBD
- **C15:** TBD
- **C16:** TBD

### Decisions Made

Engineering calls made under ambiguity during execution. Empty at start; populated as tasks execute.
