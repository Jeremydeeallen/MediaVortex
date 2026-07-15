# Feature: Failure Accounting -- per-MediaFile encode-failure budget + operator surface

**Slug:** failure-accounting

## What It Does

Caps the number of consecutive `TranscodeAttempts.Success=FALSE` rows a single MediaFile may accumulate; once the cap is reached the file is excluded from every claim, recompute, and Next-Batch surface until the operator explicitly resets it. Mirrors the existing VMAF `RetryBudgetService` for VMAF retries (`Features/QualityTesting/Disposition/`); this vertical handles the encode side.

Three reinforcing parts:
1. A **budget service** (`FailureBudgetService`) is the single source of truth for "may this MediaFile fail again."
2. A **single SQL fragment** (`Core/Database/FailureBudgetPredicate.BuildCapPredicate`) wires the cap into every claim / recompute / Next-Batch query so one helper emits the WHERE clause used by every surface.
3. A `/FailedJobs` **operator surface** (page + API + repository) so the operator can see what is stuck, view each file's full attempt history, and Reset a file's budget. Reset writes an audit row to `FailureBudgetResets` and bumps `MediaFiles.LastFailureResetAt`; the counter on subsequent claims ignores anything older than that timestamp.

`TranscodeAttempts.MediaFileId` becomes structurally non-nullable from this commit forward: every INSERT path sets it; the historical 5510-row orphan population was archived to CSV + deleted; `\d TranscodeAttempts` shows `MediaFileId BIGINT NOT NULL`.

## Workflows

| #  | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | Open `/FailedJobs` | Nav link "Failed Jobs" with red badge | `GET /FailedJobs` | `Features/FailureAccounting/FailedJobsController.RenderPage` -> `Templates/FailedJobs.html` |
| W2 | Click a filename | Modal "Attempt history" | `GET /api/FailedJobs/<MediaFileId>/Attempts` | `FailedJobsController.GetAttemptHistory` -> `FailedJobsRepository.GetAttemptHistory` |
| W3 | Click Reset on a row | Confirm modal then row disappears | `POST /api/FailedJobs/<MediaFileId>/Reset` | `FailedJobsController.ResetFailureBudget` -> `FailedJobsRepository.ResetFailureBudget` |
| W4 | Worker boots, polls queue | (internal) | Claim path consults cap | `ClaimNextPendingTranscodeJob`, `ClaimNextPendingRemuxJob`, `ClaimQualityTestJob` |
| W5 | Operator triggers Recompute / Smart-Populate / Next-Batch | The buttons on `/Work/<bucket>` / `/TranscodeQueue` | All Next-Batch SQL excludes capped files | `QueueManagementBusinessService.NextTranscodeBatch` / `SmartPopulateQueue` / `AddSuggestionsToQueue` / `QueueAllMatching` |
| W6 | Click "Reset All Visible" on `/FailedJobs` | Toolbar button; confirm modal; all currently-rendered rows reset in one call | `POST /api/FailedJobs/ResetBulk` `{MediaFileIds, OperatorName}` | `FailedJobsController.ResetFailureBudgetBulk` -> `FailedJobsRepository.ResetFailureBudgetBulk` |
| W7 | Switch to "By Series" tab + click "Reset Group" | Group row per top-level folder (series/movie); button resets every capped MediaFile in that folder | `POST /api/FailedJobs/ResetBulk` with the group's MediaFileIds | Same handler as W6 |
| W8 | `/api/Work/Transcode/Queue/<mfid>` add-single-file endpoint | HTTP-side | Single-file admission consults `FailureBudgetService.HasBudgetRemaining` before INSERT (respects ForceAdd) | `QueueManagementBusinessService.AddJobToQueue` |

## Success Criteria

C1. **`FailureBudgetService.HasBudgetRemaining(MediaFileId) -> bool` is the SOT.** Counts `TranscodeAttempts.Success=FALSE` for the given MediaFile since the most recent `Success=TRUE` OR `MediaFiles.LastFailureResetAt` (whichever is more recent). Reads fresh per call (no cache; `db-is-authority`). Verifiable: `Tests/Contract/TestFailureAccounting::TestFailureBudgetService`.

C2. **`FailureBudgetConfig` is single-row scalar config.** `Id INT PK DEFAULT 1 CHECK Id=1`, `MaxEncodeFailures INTEGER NOT NULL DEFAULT 3`, `ResetWindowDays INTEGER NULL`, `LastUpdated TIMESTAMP DEFAULT NOW()`. Idempotent migration `Scripts/SQLScripts/AddFailureBudgetConfig.py` -- second-run no-op. Verifiable: `\d FailureBudgetConfig`.

C3. **`TranscodeAttempts.MediaFileId` is `NOT NULL`.** Migration `Scripts/SQLScripts/SetTranscodeAttemptsMediaFileIdNotNull.py` runs AFTER orphan cleanup; asserts `NULL count = 0` precondition. Verifiable: `SELECT COUNT(*) FROM TranscodeAttempts WHERE MediaFileId IS NULL` returns 0; `information_schema.columns.is_nullable` = `NO`.

C4. **`Scripts/SQLScripts/CleanupOrphanFailedAttempts.py` archives orphans idempotently.** Best-effort backfill via `(StorageRootId, RelativePath)` -> `MediaFileId`; CSV archive to `Reports/OrphanFailedAttempts-<stamp>.csv`; delete archived rows. Second run on clean DB = no-op. Verifiable: `pre/post` counts logged; CSV file present.

C5. **INSERT discipline -- every `TranscodeAttempts` INSERT path sets both `MediaFileId` and `ProfileName`.** Verified for success AND failure AND every `ProcessingMode` (Transcode, Remux, Quick, AudioFix, SubtitleFix, TestVariant). `Worker/AttemptRecordService.Create`, `ProcessTranscodeQueueService.CreateTranscodeAttempt`, `ProcessTranscodeQueueService.HandleJobFailure` all resolve ProfileName as `MediaFile.AssignedProfile OR Job.AssignedProfile OR JobMode` -- JobMode is the mandatory last-resort fallback (always populated from `Job.ProcessingMode`). `SaveTranscodeAttempt` raises `ValueError` when ProfileName is missing at INSERT (fail-loud; no sentinel). MediaFileId falls back to `0` with WARN log for orphan-attempt audit. Verifiable: `Tests/Contract/TestFailureAccounting::TestProfileNameOnFailureRows`.

C6. **Single SQL helper for the cap predicate.** `Core/Database/FailureBudgetPredicate.BuildCapPredicate(MediaFileIdColumn)` is the one place that emits the cap WHERE clause. Consumers: `ClaimNextPendingTranscodeJob` + `ClaimNextPendingRemuxJob` + `ClaimQualityTestJob` (defense-in-depth at the claim layer) + `NextTranscodeBatch` + `SmartPopulateQueue` + `AddSuggestionsToQueue` + `QueueAllMatching` (primary gate at the admission layer). Reads `FailureBudgetConfig.MaxEncodeFailures` inline so operator changes apply on next query. Verifiable: `grep -rn 'BuildCapPredicate' Features/ Core/` shows ONE helper file + N call sites; `Tests/Contract/TestFailureAccounting::TestPendingQueueRespectsCap` asserts no Pending queue row exceeds the cap.

C7. **`FailedJobsRepository` is the read+reset SOT.** `GetCappedJobs(Limit, Offset, Search, SortBy, SortDir) -> List[FailedJobRow]` -- one row per capped MediaFile with FileName + FilePath + FailureCount + LastErrorMessage + LastAttemptDate + AssignedProfile + LastWorkerName + LastFailureResetAt. `ResetFailureBudget(MediaFileId, OperatorName)` writes `FailureBudgetResets` audit row (PriorFailureCount preserved) + bumps `MediaFiles.LastFailureResetAt = NOW()` + logs INFO. `ResetFailureBudgetBulk(MediaFileIds, OperatorName) -> int` is the single-TX bulk shape: one INSERT-SELECT for audit rows (one per input id) + one UPDATE `WHERE Id IN (...)`; returns rows-updated count. `GetCappedJobsGrouped() -> list` returns one row per top-level folder segment (`SPLIT_PART(RelativePath, '/', 1)`) with `SeriesGroup + FailedCount + MediaFileIds`. `CountCapped() -> int` for the nav badge. `GetAttemptHistory(MediaFileId) -> list` for the modal. Verifiable: `Tests/Contract/TestFailureAccounting::TestFailedJobsRepository` + `test_bulk_reset_updates_all_supplied_ids` + `test_bulk_reset_empty_list_returns_zero`.

C8. **`/FailedJobs` page renders the operator surface.** `Templates/FailedJobs.html` shows two tabs: (a) List -- sortable table (Newest first / Most failures first / Filename A-Z), search box, per-row Reset button with confirm dialog, modal "Attempt history"; (b) By Series -- one row per top-level folder with "Reset Group" button. Toolbar "Reset All Visible" button resets every row currently in the List view via `POST /api/FailedJobs/ResetBulk`. Nav-link in `Templates/Base.html` with `NavFailedJobsCount` badge polled every 30s. Blueprint registered in `WebService/Main.py`. Verifiable: `curl /api/FailedJobs/Count`, `curl /api/FailedJobs?limit=3`, `curl /api/FailedJobs/Groups`, `curl -X POST /api/FailedJobs/ResetBulk`.

C9. **Single-file admission consults the failure-budget cap.** `QueueManagementBusinessService.AddJobToQueue` calls `FailureBudgetService.HasBudgetRemaining(mediaFile.Id)` before INSERT, in the `IsTranscodeMode AND not ForceAdd` branch. Returns `{Success: False, CanOverride: True, FailureCapReached: True}` on cap-hit so the UI can offer a reset+requeue flow. Aligns single-file path with the bulk-admission BuildCapPredicate gate. Verifiable: grep `HasBudgetRemaining` shows call site inside `AddJobToQueue`.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `FailureBudgetService.HasBudgetRemaining` (function-call) | Service | `MediaFileId: int -> bool` (DB-fresh per call) | Future helper code that wants to check budget in Python before insert | `TestFailureBudgetService` |
| S2 | `BuildCapPredicate -> Claim/Recompute SQL` (function-call) | `Core/Database/FailureBudgetPredicate` | SQL fragment string + empty params tuple | Each claim/Next-Batch query inlines the fragment in its WHERE | `TestBuildCapPredicate` + `grep` |
| S3 | `FailedJobsRepository.GetCappedJobs -> /api/FailedJobs` (wire) | Repository -> Controller JSON envelope | `{Items: [...], TotalCount, Limit, Offset}` | Page JS reads via `fetch('/api/FailedJobs?...')` | Browser-load smoke + `curl` |
| S4 | `FailureBudgetResets` audit (state-store) | `ResetFailureBudget` | `FailureBudgetResets.(Id BIGSERIAL, MediaFileId BIGINT NOT NULL, OperatorName TEXT NOT NULL, ResetAt TIMESTAMP DEFAULT NOW(), PriorFailureCount INTEGER)` | Future "who reset what" report | `TestFailedJobsRepository::test_reset_writes_audit_and_bumps_lastreset` |
| S5 | `MediaFiles.LastFailureResetAt` (state-store) | `ResetFailureBudget` | `TIMESTAMP NULL` | `FailureBudgetService.CountConsecutiveFailures` uses GREATEST() to ignore failures older than the reset | Same test |
| S6 | `TranscodeAttempts.MediaFileId NOT NULL` (state-store) | Every INSERT path | `BIGINT NOT NULL`, FK -> `MediaFiles.Id` | All downstream readers can JOIN without coalesce | `TestTranscodeAttemptsMediaFileIdNotNull` |
| S7 | `TranscodeAttempts.ProfileName non-null on failure` (state-store) | Every INSERT path | `TEXT non-null on failure rows`, literal `Remux`/`AudioFix`/`Quick`/`SubtitleFix` for non-Transcode | `/FailedJobs` LastWorkerName + AssignedProfile columns; aggregates by profile | `TestProfileNameOnFailureRows` |
| S8 | `POST /api/FailedJobs/ResetBulk` (wire) | Client -> Controller JSON envelope | body `{MediaFileIds: [int...], OperatorName: str}` -> `{ResetCount: int}` | Client: single call resets N files; server: single-TX INSERT audit + UPDATE | `TestFailureAccounting::test_bulk_reset_updates_all_supplied_ids` |
| S9 | `GET /api/FailedJobs/Groups` (wire) | Repository grouping SQL -> Controller | `{Groups: [{SeriesGroup, FailedCount, MediaFileIds: [...]}]}` | Client: renders one row per group with Reset Group button | Manual smoke via `curl /api/FailedJobs/Groups` |
| S10 | `AddJobToQueue.HasBudgetRemaining` (function-call) | Single-file admission | `MediaFileId -> bool (fresh per call)` | Refuse INSERT when False AND not ForceAdd | grep + code review |

## Status

ACTIVE -- shipped 2026-06-13 (commit pending). Cluster A of 3.

## Files

| File | Role |
|------|------|
| `Models/FailedJobRow.py` | Immutable dataclass for one row on the surface |
| `Models/FailureBudgetConfigModel.py` | Immutable dataclass for the single-row config |
| `Repositories/FailureBudgetConfigRepository.py` | DB-fresh Get + Update for the single-row config |
| `Repositories/FailedJobsRepository.py` | GetCappedJobs + ResetFailureBudget + CountCapped + GetAttemptHistory |
| `Services/FailureBudgetService.py` | HasBudgetRemaining + CountConsecutiveFailures (constructor-injected) |
| `FailedJobsController.py` | `/FailedJobs` page + `/api/FailedJobs/*` endpoints |
| `Core/Database/FailureBudgetPredicate.py` | The ONE SQL-fragment helper emitting the cap WHERE clause |
| `Templates/FailedJobs.html` | Operator surface |
| `Scripts/SQLScripts/AddFailureBudgetConfig.py` | Idempotent migration: FailureBudgetConfig + FailureBudgetResets + MediaFiles.LastFailureResetAt |
| `Scripts/SQLScripts/CleanupOrphanFailedAttempts.py` | One-shot orphan archive (CSV) + delete; idempotent |
| `Scripts/SQLScripts/SetTranscodeAttemptsMediaFileIdNotNull.py` | NOT NULL migration with precondition assert |
| `Tests/Contract/TestFailureAccounting.py` | 10 contract tests covering AC1-AC9 |

## See also

- `Features/QualityTesting/Disposition/RetryBudgetService.py` -- the VMAF-retry sibling this vertical mirrors.
- `Features/TranscodeQueue/TranscodeQueue.feature.md` C10 -- the claim-time cap requirement (this vertical implements it).
- `Features/TranscodeQueue/next-batch-per-drive.feature.md` C12 -- the Next-Batch exclusion requirement (this vertical implements it).
- `Features/TranscodeJob/TranscodeJob.feature.md` BUG-0061 line -- the INSERT-discipline + cleanup + NOT NULL requirement (this vertical implements it).
- `failure-accounting.flow.md` -- pipeline detail: stages + cross-stage seams.

## Cross-Vertical Contract

### Columns the FailureAccounting vertical WRITES

| Column | Written by |
|---|---|
| FailureBudgetResets row INSERT | FailedJobsRepository.ResetFailureBudget |
| MediaFiles.LastFailureResetAt | Same |

### Columns the FailureAccounting vertical READS from external tables

| Column | Read by | Owner |
|---|---|---|
| TranscodeAttempts.{Id, MediaFileId, Success, AttemptDate, ErrorMessage, AssignedProfile, WorkerName} | /FailedJobs page + cap predicate | TranscodeJob |
| MediaFiles.{Id, FilePath, LastFailureResetAt} | Cap query exclusion | FileScanning + this vertical |
| PostTranscodeGateConfig.MaxRequeueAttempts | Cap threshold | QualityTesting |

### Stable function entry points

| Class.method | External caller(s) |
|---|---|
| Core.Database.FailureBudgetPredicate.BuildCapPredicate(...) -> str (SQL fragment) | Every claim + recompute + Next-Batch query |
| FailedJobsRepository.ResetFailureBudget(MediaFileId) | UI button + admin script |
| FailureBudgetService.HasExceededCap(MediaFileId) -> bool | Pre-claim check |

### HTTP API surface

| Method + URL | Purpose |
|---|---|
| GET /FailedJobs | Render the failed-jobs page |
| GET /api/FailedJobs/<MediaFileId>/Attempts | Per-file attempt history |
| POST /api/FailedJobs/<MediaFileId>/Reset | Reset failure budget |

### What is EXPLICITLY NOT a contract

- The SQL inside BuildCapPredicate -- single source; consumers append it via the helper
- The consecutive-failures-since-last-reset counting semantics may extend to include time-window filters
- Whether ResetFailureBudget writes a synthetic Success row -- today no, may change
- Internal class names (FailedJobsRepository, FailureBudgetService) -- may be split
