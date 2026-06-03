# Current Directive

**Set:** 2026-06-03
**Paused:** 2026-06-03
**Status:** Paused -- pending db-monolith-steering-hook
**Slug:** bug-0042-vmaf-list-parity
**Replaces:** `.claude/directives/closed/2026-06-02-bug-0020-fr-tfp-cleanup.md` (closed Success)

## Why Paused

Implementation blocked by hook friction on the DatabaseManager.py monolith. Three R6 refusals in this session traced to 12 preexisting `os.path.<X>` calls on path-bearing variables. The extraction-on-friction pivot (move `GetRunningQualityTestProgress` to the colocated `QualityTestRepository.py` instead of editing the monolith) is the correct design call, but the current hook is built for the pre-extraction world: it scans the whole file on every edit and refuses additions even when they would have moved code OUT of the monolith. R15 anchor enforcement compounded the cascade on the smaller repo file.

Resuming this directive requires the steering-hook directive (`db-monolith-steering-hook`) to land first. After that lands, the extraction move planned here (rows in the Files block) will route cleanly: new/edited DB methods will be steered to the colocated repo instead of refused on whole-file preexisting violations.

All design decisions in this directive remain valid -- it becomes the canonical test case for the new hook.

## Outcome

The `/Activity` page nav-bar badge count and the in-page Active Jobs list cardinality both reflect the same canonical truth: `TranscodeQueue.Status='Running'` + `QualityTestingQueue.Status='Running'`. VMAF rows appear in the list as soon as a worker claims them (queue row -> Running), not only after the worker emits a first `QualityTestProgress.Status='Processing'` row. The "badge shows N, list shows fewer than N" UI lie that causes operators to kill workers and orphan claimed VMAF rows is gone.

## Acceptance Criteria

1. With zero transcodes Running and exactly N>=1 `QualityTestingQueue` rows in `Status='Running'`, the nav-bar badge displays `N` AND the in-page Active Jobs list renders exactly `N` VMAF rows. Verifiable: SQL pause all transcode work + start one VMAF job, observe `NavActiveJobsCount` text content = `"1"` and `ActiveJobsBody` row count = 1.

2. Each VMAF row in the list shows: file name, worker name (from `QualityTestingQueue.ClaimedBy`), claim age (now - `QualityTestingQueue.DateStarted`), and a progress indicator (percentage when a `QualityTestProgress.Status='Processing'` row exists; "Starting..." placeholder when it does not). Verifiable: claim a VMAF job, observe row appears immediately with worker and "Starting..." placeholder before progress is emitted; once progress emits, observe percentage replaces the placeholder on next 5s poll.

3. The nav-bar badge value is sourced from `(SELECT COUNT(*) FROM TranscodeQueue WHERE Status='Running') + (SELECT COUNT(*) FROM QualityTestingQueue WHERE Status='Running')` — not from `SELECT COUNT(*) FROM ActiveJobs`. Verifiable: state where `ActiveJobs` has stale rows from a crashed worker AND `QualityTestingQueue` has accurate Running rows -> badge tracks the queue truth, not the stale ActiveJobs orphans.

4. A contract test in `Tests/Contract/TestActivityBadgeListParity.py` asserts the badge endpoint's reported in-flight count equals the cardinality the list endpoint would render, under a synthetic state with M transcodes Running + N VMAF Running. Test runs green: `py -m pytest Tests/Contract/TestActivityBadgeListParity.py`.

## Out of Scope

- Worker-side claim release on graceful shutdown (BUG-0042 KNOWN-ISSUES notes the related seam; file separately if not already covered by BUG-0020).
- Cleanup of orphan `ActiveJobs` rows from previously-crashed workers (one-off SQL, not a code change).
- Changes to the Active Transcode Jobs panel HEADER text `(<N> running)` (C1 of the feature doc — transcode-only by design).
- Changes to `/api/SQLQueries/GetActiveJobs` response row shape (Operations.html and SQLQueries.html still read it).
- Refactor of `ActiveJobs` table semantics.

## Constraints

- Existing `/api/QualityTesting/Progress` callers (Queue.html reads `.Progress` / `.CurrentJob`) keep the legacy single-job aliases.
- `R3` no caching in `__init__`; `R10` claim functions still gated; `R12` no multi-line docstrings in edited regions.

## Escalation Defaults

- "Source rows from `QualityTestingQueue` vs from `ActiveJobs.JobType='QualityTest'`" -> QualityTestingQueue (canonical; ActiveJobs has orphans).
- Risk tolerance: low (touches polling UX read every 10s; bug-for-bug compatibility for other surfaces preserved).

## Engineering Calls Already Made

- Fold the Activity-aggregation contract into `Features/Activity/activity-dashboard-improvements.feature.md` (C19 already exists) rather than create a new `*.flow.md` — KNOWN-ISSUES authorized either; aggregation is UI, not a multi-stage pipeline.

## Status

Active 2026-06-03 -- phase: IMPLEMENTING -- writing the four edits + contract test.

### Files

```
Features/QualityTesting/QualityTestRepository.py         -- EDIT: replace GetRunningQualityTestProgress (queue-sourced list); fix preexisting os.path -> ntpath
Features/QualityTesting/QualityTestController.py         -- EDIT: GetQualityTestProgress calls QualityTestRepository (not DatabaseManager)
Templates/Activity.html                                  -- EDIT: VMAF row handles null progress (Starting... placeholder) + claim age column
Features/SQLQueries/SQLQueriesController.py              -- EDIT: GetActiveJobs response gains InFlightCount field (canonical)
Templates/Base.html                                      -- EDIT: nav badge reads data.InFlightCount instead of data.Count
Tests/Contract/TestActivityBadgeListParity.py            -- CREATE: invariant test
Features/Activity/activity-dashboard-improvements.feature.md -- EDIT: mark C19 implemented in progress checklist
memory/KNOWN-ISSUES.md                                   -- EDIT: move BUG-0042 to Resolved
memory/BUG-INDEX.md                                      -- EDIT: move BUG-0042 to Recently Resolved
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| C19 implementation evidence (the queue-as-source-of-truth invariant) | `Features/Activity/activity-dashboard-improvements.feature.md` C19 already documents this; no new content to promote | TBD |
| no promotions | n/a | bugfix only — durable contract already in feature doc C19 |

### Verification

- **Criterion 1:** TBD (run with N=1 VMAF + 0 transcodes; record badge value + row count)
- **Criterion 2:** TBD (claim a VMAF job; record DOM at t=claim and t=claim+progress-emit)
- **Criterion 3:** TBD (SQL audit: badge value tracks `TranscodeQueue.Running + QualityTestingQueue.Running`)
- **Criterion 4:** TBD (pytest output)

### Decisions Made

- VMAF list rows are sourced from `QualityTestingQueue` LEFT JOIN `QualityTestProgress`, not the reverse. Rationale: the queue row is created at claim time; the progress row is emitted only after worker setup completes. The bug specifically exposes the "claimed but not yet processing" window.
- Nav badge gets a NEW response field (`InFlightCount`) rather than changing the existing `Count` field. Rationale: Operations.html and SQLQueries.html consume `data.Count` as "row count of ActiveJobs we just dumped"; preserving their semantics avoids cross-surface drift.
- Extraction-on-friction: the method lives in `Features/QualityTesting/QualityTestRepository.py` (which already had an older single-dict stub by the same name), NOT in `Repositories/DatabaseManager.py`. The 3rd R6 refusal on `DatabaseManager.py` (12 preexisting `os.path` calls on path-bearing variables) made it clear the monolith is charging rent on every edit -- per `feedback_extraction_on_friction.md` + `Core/Database/repository-split.feature.md` (BACKLOG), the right home for the new code is the colocated repo. The old DatabaseManager method becomes dead code and is left for BUG-0028 (repository-split) to sweep.

### Seams Touched

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| `GetRunningQualityTestProgress` -> `/api/QualityTesting/Progress` -> Activity.html `VmafJobs` | DatabaseManager method | list[dict] with ProgressPercentage/CurrentFps/EtaSeconds NULLABLE, NEW `DateStarted` field | Activity.html VMAF row renderer must handle null progress fields | Visual inspection + Criterion 1 SQL+DOM check |
| `GetRunningQualityTestProgress` -> `/api/QualityTesting/Progress` -> Queue.html `CurrentJob`/`Progress` legacy aliases | same | `.CurrentJob` and `.Progress` are first list element or None | Queue.html line 810-811 reads `CurrentQTProgress.Progress.ProgressPercentage` | Smoke: load /Queue with a Running VMAF claim before progress emitted; row should render with null-safe placeholders, not error |
| `GetActiveJobs` -> Base.html nav badge | SQLQueriesController | response gains `InFlightCount: int`; existing `Count`/`ActiveJobs` unchanged | Base.html line 184 reads `data.InFlightCount` (new) | Criterion 3 SQL audit |
