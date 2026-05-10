# Feature: Post-Transcode Disposition (unified, data-driven, auditable)

## What It Does

Replaces the five split decision sites in the post-transcode pipeline with a single function `DecidePostTranscodeDisposition(TranscodeAttemptId)` that returns `(Disposition, Reason, AuditPayload)`. Every gate input lives in a typed DB column (no `SystemSettings` KV rows for thresholds, no Python constants). Every disposition records the reason on `TranscodeAttempts` so an operator can answer "why didn't this replace?" with a single SQL query instead of grepping logs.

Retires the legacy chain (`ShouldQualityTestService`, `_ReplaceFileDirectly`, `BypassVMAFCheck` parameter, `ProcessFileReplacementWithVMAF`, three `SystemSettings` rows) entirely. No backwards-compat shims.

## Concern

Operator dogfood, 2026-05-10. Sister Wives S04E05 transcode succeeded but VMAF never ran -- `ServiceStatus.QualityTestService='Paused'` silently routed to bypass-replace, which then silently failed. The 720p output was deleted by failure cleanup, no detail logs, no audit trail. Three layered failures all hid behind the same vague "Quality test processing failed" log. The decisions are spread across `ShouldQualityTestService` (paused?), `QualityTestingBusinessService.UpdateQualityTestResults` (PassesThreshold), `CheckAndTriggerAutoReplace` (auto-fire replace), `FileReplacementBusinessService.ProcessFileReplacement` (BypassVMAFCheck branch), `ProcessFileReplacementWithVMAF` (the duplicate). No place says "given X state, the disposition is Y because Z". This feature creates that place.

## Success Criteria

### A. Single decision function

1. There is exactly one function `DecidePostTranscodeDisposition(TranscodeAttemptId) -> (Disposition: str, Reason: str, AuditPayload: dict)` in the codebase. Verifiable: `grep -rn "def DecidePostTranscodeDisposition" --include="*.py"` returns exactly one definition; no callers invoke any of the legacy decision functions.

2. The function is **idempotent** for non-`Pending` dispositions: calling it twice on a TranscodeAttempt that already has a final disposition returns the same `(Disposition, Reason)` and does NOT trigger any side effect (no second replace, no log spam beyond a single DEBUG line). Verifiable: integration test invokes the function twice, asserts the second call returns the cached decision and produces no new `MediaFilesArchive` row.

3. The function is the **only** code path that decides whether a transcoded file gets replaced, requeued, or discarded. `FileReplacementBusinessService.ProcessFileReplacement` never makes a VMAF-related decision itself; it executes the disposition the function already committed. Verifiable: `ProcessFileReplacement` has no `BypassVMAFCheck` parameter, no read of any VMAF threshold, and refuses to run unless `TranscodeAttempts.Disposition` is one of `Replace` or `BypassReplace`.

### B. Decision-table conformance

4. For every row in the canonical decision table in `transcode.flow.md` Stage 6, an integration test asserts the corresponding `(Disposition, Reason)` is returned. Adding/removing/changing a row in the code MUST be accompanied by the matching flow-doc edit (PR review check). Verifiable: the test suite has at least one assertion per documented row; CI fails if a row's expected outcome and actual outcome diverge.

5. The decision is **deterministic**: the same inputs always produce the same `(Disposition, Reason)`. There is no time-of-day-dependent or worker-identity-dependent branch. Verifiable: a unit test runs each table row twice with a fixed clock and asserts identical output.

### C. Database schema (typed, no KV)

6. New table `PostTranscodeGateConfig` exists as a single-row scalar-config table with typed columns:
   ```
   Id INT PRIMARY KEY DEFAULT 1
   VmafAutoReplaceMinThreshold NUMERIC NOT NULL DEFAULT 88
   VmafAutoReplaceMaxThreshold NUMERIC NOT NULL DEFAULT 98
   WhenVmafUnavailable TEXT NOT NULL DEFAULT 'block' CHECK (WhenVmafUnavailable IN ('block','bypass'))
   LastUpdated TIMESTAMP DEFAULT NOW()
   CHECK (Id = 1)
   CHECK (VmafAutoReplaceMinThreshold <= VmafAutoReplaceMaxThreshold)
   ```
   Verifiable: `\d PostTranscodeGateConfig` shows the columns and constraints; `INSERT INTO PostTranscodeGateConfig (Id) VALUES (2)` fails the single-row CHECK.

7. `TranscodeAttempts` gains three columns:
   ```
   Disposition TEXT NULL
       CHECK (Disposition IS NULL OR Disposition IN
              ('Pending','Replace','BypassReplace','NoReplace','Requeue','Discard'))
   DispositionReason TEXT NULL
   DispositionDecidedAt TIMESTAMP NULL
   ```
   Index on `(Disposition, DispositionDecidedAt)` for the operator audit query. Verifiable: `\d TranscodeAttempts` shows the columns and CHECK; the index exists.

8. The legacy `SystemSettings` rows are deleted by the migration:
   - `VMAFAutoReplaceMinThreshold`
   - `VMAFAutoReplaceMaxThreshold`
   - `QualityTestEnabled` (global; per-worker `Workers.QualityTestEnabled` covers the use case)
   Verifiable: `SELECT * FROM SystemSettings WHERE SettingKey IN ('VMAFAutoReplaceMinThreshold','VMAFAutoReplaceMaxThreshold','QualityTestEnabled')` returns zero rows post-migration.

### D. Audit trail (queryable)

9. Every disposition decision (other than `Pending`) writes the three new columns on `TranscodeAttempts` in a single UPDATE. Verifiable: query a few hours after a populate run -- every successful transcode attempt has `Disposition NOT NULL` and `DispositionReason NOT NULL`; failed attempts have `Disposition='Discard'` with `Reason='TranscodeFailed'`.

10. The reason vocabulary is closed. Allowed values: `TranscodeFailed`, `NoSavings`, `QualityTestNotRequired`, `AwaitingVmaf`, `VmafBelowMin`, `VmafPassed`, `VmafAboveMax`, `VmafServicePaused`, `VmafServicePausedBypassed`, `VmafCapabilityNotConfigured`. No free-text reasons. Verifiable: `SELECT DISTINCT DispositionReason FROM TranscodeAttempts WHERE DispositionReason IS NOT NULL` returns only values from this list.

11. The "why didn't this replace?" query works: `SELECT FilePath, Disposition, DispositionReason FROM TranscodeAttempts WHERE Success=true AND FileReplaced=false AND Disposition <> 'Pending'` returns one row per stuck attempt with an enumerable reason. Verifiable: induce three stuck cases (NoSavings, VmafBelowMin, VmafServicePaused), run the query, observe three rows with the expected reasons.

### E. Logs (one per decision)

12. Every disposition decision logs exactly one INFO line:
    `Disposition for TranscodeAttempt <id>: <Disposition> (Reason=<Reason>) inputs=<json>`
    where `<json>` enumerates QualityTestRequired, ServiceStatus, VMAF score, MinThreshold, MaxThreshold, WhenVmafUnavailable. No additional log noise per decision (the `LogFunctionEntry` boilerplate is gone). Verifiable: a test transcode produces a single matching log line on `Logs.Message`; the JSON payload is parseable.

13. The opaque "Quality test processing failed for TranscodeAttempt <id>: File replaced automatically because Quality testing service is paused" message pattern is gone. Verifiable: post-deploy, `SELECT COUNT(*) FROM Logs WHERE Message LIKE '%Quality test processing failed%'` does not grow.

### F. Legacy code removal (no backward-compat)

14. The following symbols are deleted from the codebase:
    - `Features/QualityTesting/ShouldQualityTestService.py` (entire file)
    - `_ReplaceFileDirectly` helper
    - `BypassVMAFCheck` parameter on `FileReplacementBusinessService.ProcessFileReplacement`
    - `FileReplacementBusinessService.ProcessFileReplacementWithVMAF` (collapse into single `ProcessFileReplacement`)
    - `QualityTestingBusinessService.CheckAndTriggerAutoReplace`
    - The hardcoded `>= 80.0` (and the new DB-fallback variant) in `QualityTestingBusinessService.UpdateQualityTestResults`'s `PassesThreshold` calculation -- the disposition function owns the comparison
    - `IsQualityTestEnabled` on `ProcessTranscodeQueueService` (replaced by per-worker capability + disposition logic)
    - `Workers.WorkerQualityTestEnabled` cached attribute on the long-lived service instance
   Verifiable: `grep -rn "ShouldQualityTestService\|_ReplaceFileDirectly\|BypassVMAFCheck\|ProcessFileReplacementWithVMAF\|CheckAndTriggerAutoReplace" --include="*.py"` returns zero hits in `Features/`, `Services/`, `Repositories/`, `WorkerService/` (the feature doc and KNOWN-ISSUES are exempt).

15. The legacy `Features/FileReplacement/post-transcode-pipeline.feature.md` is updated: criteria 1-3 (the `ShouldQualityTestService` bridge decisions) are marked **superseded by `post-transcode-disposition.feature.md`**. The mechanical criteria (path translation, atomic rename, archive-before-delete) remain in force and are referenced by Stage 8 of the flow doc.

### G. GUI (single source of truth)

16. The `/settings` page contains a "Post-Transcode" card (sibling to "Queue Tuning") with editable controls for the three `PostTranscodeGateConfig` columns: `VmafAutoReplaceMinThreshold`, `VmafAutoReplaceMaxThreshold`, `WhenVmafUnavailable`. Saving an edit updates the table and the next disposition call reads the new value (no caching, per the standing rule). Verifiable: change the threshold to 90, run a transcode that produces VMAF=89, observe `Disposition='NoReplace', Reason='VmafBelowMin'`; change back to 88, re-decide via test endpoint, observe `Replace`.

17. Endpoints under existing `/api/SystemSettings/` namespace: `GET /api/SystemSettings/PostTranscodeGateConfig`, `PUT /api/SystemSettings/PostTranscodeGateConfig`. No separate controller -- consistent with the QueueTuning pattern.

## Status

**NOT IMPLEMENTED** -- doc-first feature, awaiting operator approval.

### Progress

- [x] 1. Read existing related docs (`post-transcode-pipeline.feature.md`, `transcode.flow.md` Stages 6+7, `QualityTesting.feature.md`)
- [x] 2. Identify the five split decision sites and the five+ scattered config sources
- [x] 3. Draft this feature doc with the canonical decision table
- [x] 4. Update `transcode.flow.md` Stages 6+7 with the unified disposition flow + decision table (committed in this `/n`)
- [ ] 5. Operator approval of criteria 1-17
- [ ] 6. SQL migration `Scripts/SQLScripts/AddPostTranscodeDisposition.py` (criteria 6, 7, 8) -- creates `PostTranscodeGateConfig` (single row, typed columns); adds `Disposition`, `DispositionReason`, `DispositionDecidedAt` to `TranscodeAttempts` with CHECK + index; deletes the three legacy `SystemSettings` rows.
- [ ] 7. New repository: `PostTranscodeGateConfigRepository.Get() / Update()`. Read-fresh per call. (Criterion 6.)
- [ ] 8. Implement `DecidePostTranscodeDisposition(TranscodeAttemptId)` in a new module `Features/QualityTesting/PostTranscodeDispositionService.py`. Returns `(Disposition, Reason, AuditPayload)`. Idempotent. (Criteria 1, 2, 5.)
- [ ] 9. Wire the function as the **only** post-transcode call from `ProcessTranscodeQueueService.ProcessJob` and `QualityTestingBusinessService.ProcessQualityTestQueue` (re-decide after VMAF lands). (Criterion 3.)
- [ ] 10. Update `FileReplacementBusinessService.ProcessFileReplacement` to require `Disposition IN ('Replace','BypassReplace')` on the attempt, refuse otherwise. Drop `BypassVMAFCheck` parameter. Delete `ProcessFileReplacementWithVMAF` (collapse). (Criterion 14.)
- [ ] 11. Implement the audit-trail UPDATE in the disposition function (Disposition, DispositionReason, DispositionDecidedAt). (Criteria 9, 11.)
- [ ] 12. Add the rolled-up INFO log line. Remove the opaque "Quality test processing failed" pattern. (Criteria 12, 13.)
- [ ] 13. Delete the legacy symbols listed in criterion 14. Update `post-transcode-pipeline.feature.md` per criterion 15.
- [ ] 14. Add `/settings` "Post-Transcode" card and the two new endpoints. (Criteria 16, 17.)
- [ ] 15. Integration tests: one per decision-table row (criterion 4); idempotency test (criterion 2); audit-query test (criterion 11).
- [ ] 16. Smoke test: re-run the Sister Wives S04E05 scenario that motivated this feature. With `ServiceStatus.QualityTestService='Paused'` and `WhenVmafUnavailable='block'`, expect `Disposition='NoReplace', Reason='VmafServicePaused'`. With `WhenVmafUnavailable='bypass'`, expect `Disposition='BypassReplace', Reason='VmafServicePausedBypassed'`. With `ServiceStatus='Running'` and a real VMAF score in [88, 98], expect `Disposition='Replace', Reason='VmafPassed'`.

NEXT: operator approval of the 17 criteria. Then implement step 6 (schema + migration) first since downstream depends on the new columns / table existing.

## Scope

```
Scripts/SQLScripts/AddPostTranscodeDisposition.py                  -- NEW: migration + seed + delete legacy SystemSettings rows
Features/QualityTesting/PostTranscodeDispositionService.py         -- NEW: DecidePostTranscodeDisposition
Features/QualityTesting/Models/DispositionResult.py                -- NEW: dataclass for return value (Disposition, Reason, AuditPayload)
Features/QualityTesting/PostTranscodeGateConfigRepository.py       -- NEW
Features/QualityTesting/Models/PostTranscodeGateConfigModel.py     -- NEW
Features/QualityTesting/post-transcode-disposition.feature.md      -- this file
Features/QualityTesting/ShouldQualityTestService.py                -- DELETE (entire file)
Features/QualityTesting/QualityTestingBusinessService.py           -- delete CheckAndTriggerAutoReplace, simplify UpdateQualityTestResults
Features/FileReplacement/FileReplacementBusinessService.py         -- drop BypassVMAFCheck, collapse ProcessFileReplacementWithVMAF, gate on Disposition
Features/FileReplacement/post-transcode-pipeline.feature.md        -- supersede criteria 1-3, keep mechanical criteria
Features/TranscodeJob/ProcessTranscodeQueueService.py              -- replace ShouldQualityTestService call with DecidePostTranscodeDisposition; delete IsQualityTestEnabled / WorkerQualityTestEnabled
Features/SystemSettings/SystemSettingsController.py                -- new endpoints for PostTranscodeGateConfig (criteria 16, 17)
Features/SystemSettings/SystemSettingsViewModel.py                 -- editor view-model methods
Templates/Settings.html                                            -- new "Post-Transcode" card
transcode.flow.md                                                  -- Stages 6+7 rewrite (already done in this /n)
KNOWN-ISSUES.md                                                    -- record the messy state being fixed (this /n)
```

## Files

| File | Role |
|------|------|
| `Scripts/SQLScripts/AddPostTranscodeDisposition.py` | Idempotent migration: create `PostTranscodeGateConfig` (single-row CHECK), add `Disposition`/`DispositionReason`/`DispositionDecidedAt` to `TranscodeAttempts` with CHECK constraints + index, delete legacy `SystemSettings` rows for VMAFAutoReplaceMinThreshold/MaxThreshold/QualityTestEnabled. |
| `Features/QualityTesting/PostTranscodeDispositionService.py` | The single decision function. No I/O beyond the three repository calls + the `TranscodeAttempts` UPDATE. Idempotent. |
| `Features/QualityTesting/PostTranscodeGateConfigRepository.py` | `Get() -> PostTranscodeGateConfigModel`, `Update(Min, Max, WhenVmafUnavailable)`. No caching. |
| `Features/QualityTesting/Models/DispositionResult.py` | Dataclass: `Disposition`, `Reason`, `AuditPayload` (dict). |
| `Features/QualityTesting/Models/PostTranscodeGateConfigModel.py` | Dataclass: `Id`, `VmafAutoReplaceMinThreshold`, `VmafAutoReplaceMaxThreshold`, `WhenVmafUnavailable`, `LastUpdated`. |
| `Features/FileReplacement/FileReplacementBusinessService.py` | `ProcessFileReplacement(TranscodeAttemptId)` -- single entry point. Reads `Disposition` from `TranscodeAttempts`, refuses unless `IN ('Replace','BypassReplace')`. No threshold reads. |
| `Features/QualityTesting/QualityTestingBusinessService.py` | After writing a VMAF score, calls `DecidePostTranscodeDisposition` to re-decide and act on the result. `UpdateQualityTestResults` no longer computes `PassesThreshold` -- it just stores the score. |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py` | After successful transcode, calls `DecidePostTranscodeDisposition`. No more `ShouldQualityTestService`, no more `IsQualityTestEnabled`. |
| `Templates/Settings.html` | "Post-Transcode" card with three editable controls (Min, Max, WhenVmafUnavailable). |
| `Features/SystemSettings/SystemSettingsController.py` | `GET/PUT /api/SystemSettings/PostTranscodeGateConfig`. |
| `transcode.flow.md` | Stages 6, 7, 8 rewritten (Stage 6=Disposition, 7=VMAF, 8=Action). Decision table is canonical. |

## Deviation from conventions

**Criteria 1, 2, 3, and 14 reference specific function/parameter/file names** (`DecidePostTranscodeDisposition`, `ShouldQualityTestService`, `_ReplaceFileDirectly`, `BypassVMAFCheck`, `ProcessFileReplacementWithVMAF`, `CheckAndTriggerAutoReplace`, `IsQualityTestEnabled`). This violates the rename test in `.claude/rules/feature-criteria.md`. The deviation is intentional: the operator requirement is explicit legacy-code removal ("remove all legacy code it's worthless"). Without naming the symbols, the "is the legacy gone?" check has no anchor. The behavior criteria (4, 5, 9-13, 16, 17) are name-agnostic and survive renames; the structural cleanup criteria are tied to the symbols by design.

If a future rename happens, criteria 1, 2, 3, 14 must be edited along with the rename in the same PR. The grep pattern in criterion 14 makes this discoverable.

Every other criterion is externally verifiable: SQL queries, log-line presence, integration-test assertions. The "single source of truth" rule (one decision function, one config table, one log line per decision, one column triplet for audit) directly addresses the Cursor-era pattern recorded in `KNOWN-ISSUES.md` of split decisions across multiple files.
