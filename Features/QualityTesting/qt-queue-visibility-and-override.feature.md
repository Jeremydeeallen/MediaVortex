# QualityTestingQueue Visibility + Operator Override

**Slug:** qt-queue-visibility-and-override

## What It Does

Closes a gap in the post-transcode pipeline: when a transcode completes and VMAF is required, the `QualityTestingQueue` row is **always created**, regardless of whether a VMAF-capable worker is currently online. Operators see in-progress work in one place. They can either bring a capable worker online (normal VMAF path resolves the row) or operator-override the row to force an immediate `Replace` or `Discard` via the WebService -- no worker required.

Retires the legacy "no capable worker -> terminal NoReplace/VmafServicePaused" decision branch. That branch produced silently-stuck files with no operator surface.

## Concern

Discovered 2026-05-29 during the NVENC canary. I9 finished a successful transcode while every worker had `QualityTestEnabled=FALSE`. The disposition function (per the prior decision table) returned `NoReplace/VmafServicePaused`, no queue row was created, and the `.inprogress` output sat on disk with zero operator visibility. The only way to recover was manual SQL surgery (insert QualityTestingQueue row + restart worker with capability flipped). Operator's correct read: "if VMAF is on, the item should be on the queue so I can see it -- and I should be able to override Replace right there." This feature is that.

## Success Criteria

C1. **Always enqueue when VMAF required.** `DecidePostTranscodeDisposition` returns `Pending/AwaitingVmaf` whenever `QualityTestRequired=TRUE` and the VMAF score is NULL, regardless of `VmafCapableWorkerOnline`. The post-decision dispatcher in `ProcessTranscodeQueueService.DispatchDisposition` calls `AddToQualityTestQueue(TranscodeAttemptId)` on Pending, which INSERTs the queue row. Verifiable: queue a transcode with every worker's `QualityTestEnabled=FALSE`; after the transcode completes, exactly one `QualityTestingQueue` row exists for that attempt with `Status='Pending'` and `ForceDisposition IS NULL`.

C2. **Decision table simplified to 8 rows.** The `transcode.flow.md` Stage 6 decision table no longer includes `VmafCapableWorkerOnline` or `WhenVmafUnavailable` as inputs. Rows for `VmafServicePaused` / `VmafServicePausedBypassed` are removed from the active decision set; the reason values remain in the closed enum (`REASONS` in `PostTranscodeDispositionService.py`) for audit-history compatibility on legacy attempts. Verifiable: `grep VmafServicePaused Features/QualityTesting/PostTranscodeDispositionService.py` shows the values only in the REASONS list, not in any `return` statement of `_DecideFromInputs`.

C3. **Queue gains override columns.** `QualityTestingQueue` adds three columns via idempotent migration:
   ```
   Status            TEXT NOT NULL DEFAULT 'Pending'
                     CHECK (Status IN ('Pending','Running','Completed','Cancelled','Failed'))
   ForceDisposition  TEXT NULL
                     CHECK (ForceDisposition IS NULL OR ForceDisposition IN ('Replace','Discard'))
   OverrideSetAt     TIMESTAMP NULL
   ```
   Existing rows backfill to `Status='Pending'` for rows without `DateStarted`/`DateCompleted`, `Status='Running'` when only `DateStarted` set, `Status='Completed'` when `DateCompleted` set. Verifiable: `\d QualityTestingQueue` shows the columns and CHECK; backfill produces sensible Status values for legacy rows.

C4. **Worker poll query honors the override.** `QualityTestingBusinessService.ProcessQualityTestQueue` (and the underlying claim query in `DatabaseManager`) selects only `WHERE Status='Pending' AND ForceDisposition IS NULL`. A row with `ForceDisposition` set is invisible to workers, so a worker can't race the WebService override. Verifiable: set ForceDisposition='Replace' on a pending row, restart a capable worker, observe the worker does not claim that row.

C5. **WebService override endpoint.** `POST /api/QualityTest/Override` accepts `{queueId, forceDisposition, reason?}`. The handler runs atomically:
   - UPDATE `QualityTestingQueue` SET `ForceDisposition=$forceDisposition`, `OverrideSetAt=NOW()`, `Status='Cancelled'` WHERE `Id=$queueId AND Status='Pending'`
   - UPDATE `TranscodeAttempts` SET `Disposition=$d`, `DispositionReason=$r`, `DispositionDecidedAt=NOW()` where `$d`='Replace' for Replace, 'Discard' for Discard; `$r`='OperatorForcedReplace' or 'OperatorDiscarded'
   - For Replace: call `FileReplacementBusinessService.ProcessFileReplacement(attemptId)` synchronously, return the result
   - For Discard: delete the `.inprogress` output file via `TemporaryFilePaths.LocalOutputPath`, delete the TFP row, return success
   - Response: `{Success, AttemptId, Disposition, Reason, FileReplaced?}`
   Verifiable: POST with `forceDisposition='Replace'` on a real pending row; observe the file replaces on disk, MediaFiles re-probed, audit columns set; second POST on the same queueId returns 409 Conflict (Status no longer Pending).

C6. **Closed reason vocabulary extended.** Add `OperatorForcedReplace`, `OperatorDiscarded` to the `REASONS` enum in `PostTranscodeDispositionService.py`. The closed-list audit query (post-transcode-disposition.feature.md criterion 10) still passes. Verifiable: `SELECT DISTINCT DispositionReason FROM TranscodeAttempts` returns only values in the enum.

C7. **Backward compat: no terminal NoReplace from "no worker".** After this ships, the queries
   ```sql
   SELECT COUNT(*) FROM TranscodeAttempts
   WHERE DispositionDecidedAt > '<deploy date>'
     AND DispositionReason IN ('VmafServicePaused', 'VmafServicePausedBypassed');
   ```
   return zero. Pre-deploy rows with these reasons remain for history. Verifiable post-deploy: query returns zero for any date >= deploy.

## Status

COMPLETE 2026-05-29.

### Progress

- [x] Flow doc updated (`transcode.flow.md` Stage 6 decision table + Stage 7 dual-path trigger section)
- [x] Migration `Scripts/SQLScripts/AddQualityTestQueueOverride.py` (Status + ForceDisposition + OverrideSetAt columns + backfill)
- [x] `_DecideFromInputs` Row 4 simplified (drop VmafCapableWorkerOnline + WhenVmafUnavailable branches); REASONS enum extended
- [x] `ProcessQualityTestQueue` claim query gains `AND ForceDisposition IS NULL`
- [x] WebService endpoint `POST /api/QualityTest/Override` wired in `QualityTestController`
- [x] Reason audit verified: zero new VmafServicePaused-class decisions post-deploy
- [x] UI surface partial: the QT queue is rendered as the "VMAF Queue" card on `/Queue` (collapsible by default; summary shows `(pending • running • failed)` from `/api/QualityTest/AggregateStats`; table body shows pending QT rows with Retry button on failed rows). Per-row Force-Replace / Force-Discard buttons still DEFERRED to a follow-up; the endpoint remains callable via the SQL Queries page or curl until those buttons land.

## Scope

```
transcode.flow.md                                                       -- Stage 6 + Stage 7 rewrites
Features/QualityTesting/qt-queue-visibility-and-override.feature.md     -- this file
Features/QualityTesting/PostTranscodeDispositionService.py              -- _DecideFromInputs Row 4 simplification + REASONS extension
Features/QualityTesting/QualityTestController.py                        -- POST /api/QualityTest/Override endpoint
Repositories/DatabaseManager.py                                         -- claim query gains ForceDisposition IS NULL filter
Scripts/SQLScripts/AddQualityTestQueueOverride.py                       -- idempotent migration + backfill
```

## Files

| File | Role |
|------|------|
| `Scripts/SQLScripts/AddQualityTestQueueOverride.py` | Idempotent migration: 3 ADD COLUMN IF NOT EXISTS + backfill Status from existing DateStarted/DateCompleted. |
| `Features/QualityTesting/PostTranscodeDispositionService.py` | Row 4 unconditional Pending; Rows 8-9 deleted from `_DecideFromInputs`; REASONS extended with `OperatorForcedReplace`, `OperatorDiscarded`. |
| `Features/QualityTesting/QualityTestController.py` | `POST /api/QualityTest/Override` -- atomic update + immediate FileReplacement / Discard action. |
| `Repositories/DatabaseManager.py` | Queue claim query filters `ForceDisposition IS NULL` to keep WebService overrides race-free against worker polling. |

## Deferred / Out of Scope

- UI: a dedicated Queue-page card with per-row Force-Replace / Force-Discard buttons. Endpoint is callable from `/SQLQueries` or curl until the UI lands. Filed as a follow-up.
- Retiring the `WhenVmafUnavailable` config column on `PostTranscodeGateConfig`. The decision logic no longer reads it. Cleanup follow-up.
- Auto-alert when QualityTestingQueue accumulates rows older than N hours (operator sees pending work hasn't been processed). Telemetry follow-up.
