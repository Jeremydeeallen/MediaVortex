# Flow: Failure Accounting

**Slug:** failure-accounting

## Entry Points

Three orthogonal entry points consume the cap predicate:

1. **Claim-time gate** -- `TranscodeQueueRepository.ClaimNextPendingTranscodeJob` / `ClaimNextPendingRemuxJob` / `QualityTestRepository.ClaimQualityTestJob`. Defense-in-depth at the worker boundary -- even if a Pending row slipped past the admission gate, the worker cannot claim it for an over-cap MediaFile.

2. **Admission-time gate** -- `QueueManagementBusinessService.AddSuggestionsToQueue` + `QueueAllMatching` + `NextTranscodeBatch` + `SmartPopulateQueue`. Primary gate: capped files never enter `TranscodeQueue` to begin with.

3. **Surface-time read** -- `FailedJobsRepository.GetCappedJobs` powers the `/FailedJobs` page; same predicate inverted (`>=` cap rather than `<` cap).

All three resolve `MaxEncodeFailures` through `FailureBudgetConfig` -- one row, operator-tunable via `/settings` (future enhancement); current default `3`.

## Stages

| ID | Stage | Code | What it does |
|---|---|---|---|
| ST1 | Encode finalize | `ProcessTranscodeQueueService.HandleJobFailure` + `Worker/AttemptRecordService.Create` + `ProcessTranscodeQueueService.CreateTranscodeAttempt` | Write `TranscodeAttempts(MediaFileId NOT NULL, ProfileName non-null, Success=FALSE, ErrorMessage, WorkerName)`. Sentinel `0` / `'__UNRESOLVED__'` plus WARN log if the call site cannot resolve either -- audit row is preserved even on resolver failure (S6 + S7 from feature doc). |
| ST2 | Budget eval | `FailureBudgetService.HasBudgetRemaining(MediaFileId)` | Count consecutive `Success=FALSE` rows since `GREATEST(last Success=TRUE, MediaFiles.LastFailureResetAt)`. Compare against `FailureBudgetConfig.MaxEncodeFailures`. Returns bool. |
| ST3 | Cap-gated SQL | `Core/Database/FailureBudgetPredicate.BuildCapPredicate(MediaFileIdColumn)` | Returns a `(sql_fragment, params_tuple)` pair (params always empty). The fragment is a correlated subquery on `TranscodeAttempts` against the supplied column, with the cutoff GREATEST() and the `FailureBudgetConfig` lookup inlined. Consumers compose it into their existing WHERE clauses. |
| ST4 | Surface render | `FailedJobsController.ListCappedJobs` -> `FailedJobsRepository.GetCappedJobs` | Same logic as the cap predicate but inverted (>= cap) -- returns the file row with FileName, FilePath, FailureCount, LastErrorMessage, LastAttemptDate, AssignedProfile, LastWorkerName, LastFailureResetAt. |
| ST5 | Operator reset | `FailedJobsController.ResetFailureBudget` -> `FailedJobsRepository.ResetFailureBudget` | Two writes: (a) `INSERT FailureBudgetResets(MediaFileId, OperatorName, PriorFailureCount)`; (b) `UPDATE MediaFiles SET LastFailureResetAt = NOW() WHERE Id = MediaFileId`. Counter on next eval ignores anything before this timestamp. |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1 -> ST2` (failure written, eval-able) | TranscodeAttempts row | `(MediaFileId BIGINT NOT NULL, Success=FALSE, AttemptDate TIMESTAMP, ProfileName TEXT NOT NULL, WorkerName TEXT)` | `HasBudgetRemaining` counts the row | `TestFailureBudgetService::test_caps_at_max` |
| S2 | `ST2 -> ST3` (Python eval -> SQL fragment) | Python service call OR SQL helper | Both share the same semantic: "consecutive failures since cutoff < cap". The SQL helper inlines the cutoff via `GREATEST()`; the Python service uses two queries. | Every claim/admission/surface uses the SQL helper consistently | `TestBuildCapPredicate` + `TestPendingQueueRespectsCap` |
| S3 | `ST3 -> claim/admission` (cap-gated SQL) | `BuildCapPredicate` | `(sql_fragment: str, params: tuple = ())` | 7 surfaces inline the fragment in their WHERE: claim x3 + Next-Batch x1 + SmartPopulate x1 + AddSuggestions x1 + QueueAllMatching x1 | Live AC6 end-to-end (synthetic over-cap MediaFileId excluded from each surface) |
| S4 | `ST4 surface` (read) | `FailedJobsRepository.GetCappedJobs` | JSON envelope `{Items: [{MediaFileId, FileName, FilePath, FailureCount, LastErrorMessage, LastAttemptDate, AssignedProfile, LastWorkerName, LastFailureResetAt}], TotalCount, Limit, Offset}` | Page JS renders; nav badge polls `/api/FailedJobs/Count` | `curl /api/FailedJobs` |
| S5 | `ST5 reset` (state-store) | `ResetFailureBudget` | Two atomic writes: `FailureBudgetResets` audit + `MediaFiles.LastFailureResetAt` bump | Next eval (ST2/ST3) treats failures older than `LastFailureResetAt` as not counting | `TestFailedJobsRepository::test_reset_writes_audit_and_bumps_lastreset` |

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| Operator forgets to reset, fleet drains the queue | Capped files do not re-enter the queue; FailedJobs badge stays high | Operator hits `/FailedJobs` Reset OR adjusts `FailureBudgetConfig.MaxEncodeFailures` via `/settings` |
| Producer cannot resolve `MediaFileId` on a TranscodeAttempts INSERT | `MediaFileId=0` sentinel + WARN log `TranscodeAttempts INSERT could not resolve MediaFileId; using sentinel 0 ... see failure-accounting.C5` | Grep logs for `using sentinel 0`; fix the producer's `Job.MediaFileId` -- the audit row was preserved |
| Operator wants to bulk-reset | No bulk endpoint (by design) | Per-file friction -- operator must look at the failure before re-allowing it |
| `FailureBudgetConfig` table missing | `BuildCapPredicate` SQL falls back to default `3` via `COALESCE` | Run `Scripts/SQLScripts/AddFailureBudgetConfig.py` |

## Out of Scope

- **VMAF retries** -- owned by `Features/QualityTesting/Disposition/RetryBudgetService`. Sibling service; this vertical is the encode-failure counterpart.
- **Cap-tuning UI** -- operator can adjust `MaxEncodeFailures` via SQL or a future `/settings` card; not in this directive.
- **Time-based reset window (`ResetWindowDays`)** -- column reserved (NULL default), behavior unwired; not in this directive's gate logic. Future enhancement.

## Code anchors

| Code | Anchor |
|---|---|
| `Features/FailureAccounting/Services/FailureBudgetService.py:HasBudgetRemaining` | `# see failure-accounting.ST2` |
| `Features/FailureAccounting/Services/FailureBudgetService.py:CountConsecutiveFailures` | `# see failure-accounting.ST2` |
| `Core/Database/FailureBudgetPredicate.py:BuildCapPredicate` | `# see failure-accounting.ST3` |
| `Features/FailureAccounting/Repositories/FailedJobsRepository.py:GetCappedJobs` | `# see failure-accounting.ST4` |
| `Features/FailureAccounting/Repositories/FailedJobsRepository.py:ResetFailureBudget` | `# see failure-accounting.ST5` |
