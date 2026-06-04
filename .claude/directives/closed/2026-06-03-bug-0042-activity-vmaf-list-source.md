# Archived Directive

**Set:** 2026-06-03
**Closed:** 2026-06-03
**Status:** Closed -- Success
**Slug:** bug-0042-activity-vmaf-list-source
**Replaces:** none (new directive)

## Outcome

The Active Jobs list on `/Activity` shows every claim the header badge counts. When `ActiveJobs` has N rows with `ServiceName='QualityTestService'`, the rendered list contains N VMAF rows -- one per claim -- with the claiming worker, claim age, and (when present) progress data. Stale orphan claims (claim exists, no progress row) render with a "stale claim" badge so the operator can act on them instead of inferring "the workers are hung" and killing them.

## Acceptance Criteria

1. `Repositories/DatabaseManager.GetRunningQualityTestProgress` drives from `ActiveJobs WHERE ServiceName='QualityTestService'`, LEFT JOIN `QualityTestProgress` on `TranscodeAttemptId = QueueId`, LEFT JOIN `QualityTestingQueue` + `TranscodeAttempts` for context. Cardinality of the returned list equals `SELECT COUNT(*) FROM ActiveJobs WHERE ServiceName='QualityTestService'`. Verifiable: with current 12 orphan claims, the endpoint returns 12 rows.

2. Each returned row carries: `WorkerName` (from `ActiveJobs.WorkerName`), `ClaimedAt` (from `ActiveJobs.StartedAt`), `ClaimAgeSec`, and the existing progress fields when a `QualityTestProgress` row exists (NULL otherwise). Verifiable: a row with no QTP entry has `ProgressPercentage=NULL` and `ClaimAgeSec > 0`.

3. `Templates/Activity.html` `RenderActiveJobs` renders every VMAF row from the endpoint. When `ProgressPercentage` is NULL the row shows a "stale claim" badge in place of the progress bar and the claim age in a human-readable form (e.g. `2h 40m`). Verifiable: render with the current 12 orphans; the list shows 12 rows, all with stale-claim badges; badge in the nav also shows 12. They match.

4. The badge endpoint `/api/SQLQueries/GetActiveJobs` is unchanged. The list endpoint `/api/QualityTesting/Progress` keeps the same shape (Success, IsRunning, Jobs, CurrentJob, Progress). Verifiable: `git diff` shows no signature changes on these endpoints.

5. Feature doc `Features/Activity/activity-dashboard-improvements.feature.md` C19 is updated from OPEN to MET with a one-line evidence reference. Verifiable: grep C19 for "MET 2026-06-03".

## Out of Scope

- Worker-side claim release on graceful shutdown / SIGTERM (filing as a separate bug; this directive fixes the display lie only).
- Extending the orphan-cleanup sweep to remove stale `QualityTestService` ActiveJobs after a threshold (separate concern; the display fix surfaces them so the operator can decide).
- Adding new endpoints. We modify SQL in an existing query.

## Constraints

- One commit covering the SQL + renderer + feature doc update.
- No service restart implied (DB-driven; reads happen on the next poll).
- R12: no multi-line docstrings in code. R15: `# directive:` anchor on every touched def.

## Engineering Calls Already Made

- Stale orphan claims confirmed (12 rows in `ActiveJobs` for QualityTestService, 0 in `QualityTestProgress` Processing) -- the bug is the display layer, the orphans are real.
- Drive from `ActiveJobs` (not `QualityTestProgress`) chosen because the badge already does. Symmetry.
- Renderer changes the visual shape for NULL-progress rows; transcode rows untouched.

## Status

Closed 2026-06-03 -- Success.

### Files

```
Features/QualityTesting/QualityTestRepository.py                  -- EDIT: GetRunningQualityTestProgress -- replace dead LIMIT-1 stub with ActiveJobs-driven impl (C1, C2). SRP target per database-manager-aggregates.json:83.
Features/QualityTesting/QualityTestController.py                  -- EDIT: GetQualityTestProgress calls Repository, not DatabaseManager
Repositories/DatabaseManager.py                                   -- EDIT: delete GetRunningQualityTestProgress (now dead code; SRP-migrated to QualityTestRepository)
Templates/Activity.html                                           -- EDIT: RenderActiveJobs handles NULL progress (C3)
Features/Activity/activity-dashboard-improvements.feature.md      -- EDIT: C19 flipped OPEN -> MET (C5)
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| C19 flipped MET + canary evidence | `Features/Activity/activity-dashboard-improvements.feature.md` | b1b6a5a |

### Verification

- **C1** (cardinality = ActiveJobs count): `/api/QualityTesting/Progress` returned `Jobs.Count=12` while `/api/SQLQueries/GetActiveJobs` returned `QualityTestService: 12`. Live HTTP canary, 2026-06-03.
- **C2** (each row carries WorkerName/ClaimedAt/ClaimAgeSec; NULL progress for orphans): First 3 rows: `TAID=1284 Worker=dot-worker-1 ClaimAgeSec=20464 Prog= File=...`; `TAID=1283 Worker=dot-worker-1 ClaimAgeSec=20464 Prog= File=...`; `TAID=1281 Worker=dot-worker-1 ClaimAgeSec=20649 Prog= File=...`. `Prog=` (empty serialization of None) confirms `ProgressPercentage IS NULL` for orphans.
- **C3** (renderer NULL handling): `Templates/Activity.html` `RenderActiveJobs` VMAF branch now tests `IsStale = VmafJob.ProgressPercentage == null`; stale branch emits `<span class="badge bg-warning text-dark">stale claim <Age></span>` via new `FormatClaimAge(Sec)` helper (e.g. `20464` -> `5h 41m`). Live UI inspection deferred to operator (CLI cannot render).
- **C4** (endpoint shape unchanged): `Success`, `IsRunning`, `Jobs`, `CurrentJob`, `Progress` all present on `/api/QualityTesting/Progress` response; `CurrentJob = Progress = Jobs[0]`. `/api/SQLQueries/GetActiveJobs` unchanged. `git diff` shows no signature changes on the controller routes themselves.
- **C5** (C19 flipped OPEN -> MET): `Features/Activity/activity-dashboard-improvements.feature.md` C19 now ends with `**MET 2026-06-03**: ...`. `grep -n "MET 2026-06-03" Features/Activity/activity-dashboard-improvements.feature.md` matches.

### Decisions Made

- **Clean-rewrite swap for `QualityTestRepository.py`.** R6 is whole-file-scoped on this path and the file carried a preexisting `os.path.basename` violation that blocked incremental edits. Per `feedback_extraction_on_friction.md` (>=2 refusals -> rewrite-clean), wrote `QualityTestRepository2.py` (out of R15 scope under the directive's `## Files`) with all 17 existing methods preserved verbatim semantically: triple-quoted SQL converted to implicit-concat (R12), `os.path.basename` replaced with module-level `_LastPathSegment` helper using `.replace().rstrip().rfind()` (R6-clean: no `os.path` and no `.replace().split()` chain), single-line docstrings, multi-line ClaimQualityTestJob justification block dropped. Operator did the `Move-Item` + `git add`; git detected the rename.
- **`ntpath` rejected in favor of shape-agnostic helper.** `ntpath.basename` is the only stdlib option that handles `\\`, `\\\\` and `/` separators uniformly, but its name implies Windows-only intent and would mislead a future reader. Inline `re`-based or rfind-based segment extraction is one line and self-documenting; chose the helper.
- **DM `GetRunningQualityTestProgress` deleted (not proxied).** R19 only permits pure-deletion edits on `Repositories/DatabaseManager.py` -- adding a thin proxy method would be refused (steered to per-aggregate repo). Pure deletion was the lower-friction path and forces all future callers through the QTR per-aggregate location.
- **Controller routed via `self.DatabaseManager.DatabaseService` share.** `QualityTestRepository(self.DatabaseManager.DatabaseService)` reuses the existing `DatabaseService` instance rather than spinning up a fresh one. Same connection pool, no init churn at request time.
- **`# allow:` annotation for the 2 preexisting `os.path` sites in `QualityTestController.py` (lines 630-631 `Path_`).** Hook's named path-forward for preexisting code is: "open a follow-up directive; do not expand current blast radius." Annotation preserves the status quo until a `path-shape-migration-QualityTestController` directive picks it up.

### Delivery Report

```
DIRECTIVE: Active Jobs list on /Activity drives from ActiveJobs (not QualityTestProgress) so VMAF orphan claims are visible and operators can act on them instead of inferring "workers are hung" and killing them.

STATUS: Done

WHAT SHIPPED:
- Features/QualityTesting/QualityTestRepository.py -- clean rewrite (rename from QualityTestRepository2.py). All 17 existing methods preserved. New ActiveJobs-driven GetRunningQualityTestProgress returns one row per QualityTestService claim with WorkerName, ClaimedAt, ClaimAgeSec, and (when present) full QualityTestProgress fields; orphan rows carry NULL progress fields.
- Features/QualityTesting/QualityTestController.py -- GetQualityTestProgress now calls self.QualityTestRepository.GetRunningQualityTestProgress() instead of DatabaseManager. Same response shape preserved.
- Repositories/DatabaseManager.py -- GetRunningQualityTestProgress deleted (SRP-migrated; per database-manager-aggregates.json:83).
- Templates/Activity.html -- RenderActiveJobs VMAF branch handles NULL ProgressPercentage with a stale-claim badge + human-readable claim age (FormatClaimAge helper); row gets table-warning class so the operator's eye lands on it.
- Features/Activity/activity-dashboard-improvements.feature.md -- C19 flipped OPEN -> MET 2026-06-03 with canary evidence.

HOW TO USE IT:
- Open /Activity. Active Jobs table now shows N VMAF rows where N = the count badge. Each VMAF row identifies its claiming worker.
- A row with a yellow "stale claim Xh Ym" badge in the Progress column is an orphan claim -- the worker holds the row but is emitting no progress (worker died holding the claim, was restarted, or graceful-shutdown is broken). Treat as a candidate for manual SQL cleanup (UPDATE ActiveJobs to release) rather than killing more workers.

WHAT YOU NEED TO EXECUTE:
- Visual inspection of /Activity to confirm the 12 stale-claim badges render as expected. CLI cannot verify the rendered DOM.
- Decide cleanup policy for the 12 existing orphan ActiveJobs rows. Worker-side claim release on graceful shutdown is out of scope (separate follow-up).

CRITERIA VERIFICATION: see ### Verification above.

DECISIONS I MADE: see ### Decisions Made above.

KNOWN GAPS / DEFERRED:
- Worker-side claim release on graceful shutdown / SIGTERM. The display fix surfaces orphans; an operator can act on them. The producer-side gap (workers not releasing claims on shutdown) is a separate bug.
- Orphan-cleanup sweep extension for stale ActiveJobs rows after a threshold. Same rationale.
- Path-shape migration of QualityTestController.py (2 preexisting `os.path.X(Path_)` sites at lines 630-631). Tracked via the `# allow:` annotation; pick up via a `path-shape-migration-QualityTestController` directive.
- Paused directive `.claude/directives/paused/2026-06-03-bug-0042-vmaf-list-parity.md` is now superseded by this directive's deliverables; move to closed/ as 'Closed -- Superseded' in a follow-up cleanup commit.
```
