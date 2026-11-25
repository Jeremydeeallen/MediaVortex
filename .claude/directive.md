# Current Directive

**Set:** 2026-11-25
**Status:** Active -- phase: IMPLEMENTING
**Slug:** insert-returning-id
**Replaces:** `directives/closed/2026-11-25-farm-server.md` (closed Success)

## Outcome

Every row id that code gets back from an INSERT comes from that statement's own `RETURNING Id`, on the connection that ran it. No code reads an id from state shared across calls or threads, and no id lookup can quietly return 0 or None instead of the real id. Today `DatabaseService.LastInsertId` is a per-instance field overwritten by every `RETURNING` write. Readers on another thread can get another row's id, and `GetLastInsertId()` returns 0 instead of raising. That is the defect class behind BUG-0109 (fleet DeployHistory rows never finalized) and the `ActiveJobRepository.CreateActiveJob` "returned 0" note in `2026-07-27-audio-language-detection`.

## Acceptance Criteria

1. No Python file in the repo reads or writes `LastInsertId` or calls `GetLastInsertId`. A contract test scans the tree and fails on any hit.
2. Each insert function that returns a new row id returns the id of the row it inserted. Verify: a contract test calls each function against the live DB, then SELECTs the row by the returned id and finds the values it wrote. Test rows are removed afterwards.
3. Two threads inserting through one shared database object at the same time each get their own row's id. Verify: a contract test with 2 threads x 50 inserts finds that every returned id maps to the row that thread wrote.
4. One real transcode on the I9 worker completes. Its ActiveJobs row is created and then removed, its progress updates land on one TranscodeProgress row, and its TemporaryFilePaths row carries the attempt id.
5. One real VMAF quality test completes, with its queue entry, its result row, and one progress row.
6. One probe on a worker writes its ActiveJobs row and removes it when done.
7. `POST /api/QualityTest/QueueTestRun` on the farm server returns each accepted `QueueId` equal to the TranscodeQueue row it created.

## Call-Graph Audit

- **Signal 1 (two flow docs for one operation):** none added. The touched paths belong to `transcode.flow.md` (progress, temp paths, ActiveJobs), the quality-test pipeline, and the probe worker. No new flow doc.
- **Signal 2 (mode branch at orchestration):** none. The change sits below orchestration, in repository insert helpers.
- **Signal 3 (sparse output columns):** none. The written columns are unchanged.
- **Signal 5 (config changes which code runs):** none.
- **Duplicate inserters:** `ServiceControlRepository.CreateActiveJob` and `CreateServiceCommand` have no callers (tree-wide grep). Deleted (genuinely-dead orphan bucket). `ProbeWorker._CreateActiveJob`, `LanguageWorker._CreateActiveJob` and `ActiveJobRepository.CreateActiveJob` are three ActiveJobs inserters: see Out of Scope.
- **Seam, shared id state:** `DatabaseService.ExecuteNonQuery` stores the first `RETURNING` column in `self.LastInsertId`. `ExecuteReturning` already returns rows from the same cursor. The capture, the field, and both `GetLastInsertId` methods are deleted. Call sites use `self.DatabaseService.ExecuteReturning`; `BaseRepository` gets no new passthrough, because `repository-split.feature.md`'s end state has no `BaseRepository` (repositories compose `DatabaseService`).
- **`ExecuteNonQuery` + `RETURNING` callers that ignore the id** (`MediaFilesRepository`, `ContentClassificationRulesController`, `AudioFixPriorityHintsController`, `TranscodeQueueRepository`): unaffected. They never read the id.

## Out of Scope

- (b) Three ActiveJobs inserters (`ProbeWorker`, `LanguageWorker`, `ActiveJobRepository`) duplicate one INSERT. Collapsing them is a DRY change with its own callers; acknowledged debt, filed.
- (b) The touched insert functions keep their outer `try/except` that logs and returns 0/None/False. Making them raise changes caller control flow in the encode loop, VMAF monitor and queue service. That is the fail-loud sweep (`TestFailLoud` baseline ratchet), filed separately. The inner `if RowsAffected > 0 ... else return 0` id branches are removed (a), because `ExecuteReturning` yields the row or nothing.
- (a) Behaviour is otherwise preserved: same SQL, same columns, same return types.

## Constraints

- Fail loud: an insert that returns no row raises; it never substitutes 0.
- Contract tests that write live rows clean up after themselves and use test-only marker values.
- Live smoke follows the drain and one-I9-instance rules.

## Escalation Defaults

- Speed vs. completeness -> completeness. Every reader of the shared field is migrated or deleted in this directive.
- Risk tolerance: low. Transcode, VMAF and probe hot paths are touched.

## Engineering Calls Already Made

- `ExecuteReturning(...)[0]['Id']` at each call site. No new helper.
- No runtime guard that makes `ExecuteNonQuery` refuse `RETURNING`. Callers that ignore the id are harmless, and deleting the field turns any leftover reader into an immediate `AttributeError`.

## Status

Phases advance by editing the `**Status:**` header line at the top of this file: `**Status:** Active -- phase: <NEXT>`. The PreToolUse hook reads ONLY that header line (NOT this section). See `.claude/standards/index.md` for the phase machine.

### Plan

1. `Core/Database/DatabaseService.py`: delete the `LastInsertId` init and capture, and `GetLastInsertId`.
2. `Core/Database/BaseRepository.py`: delete `GetLastInsertId` (no replacement passthrough; see Call-Graph Audit).
3. Migrate to `ExecuteReturning(...)[0]['Id']`:
   - `WorkerService/ProbeWorker._CreateActiveJob`
   - `Features/ServiceControl/ActiveJobRepository.CreateActiveJob`
   - `Features/QualityTesting/QualityTestRepository.CreateQualityTestQueueEntry`, `.CreateQualityTestResult`, `.CreateTemporaryFilePath`
   - `Features/QualityTesting/QualityTestingBusinessService.CreateProgressRecord` (drop the `or 0`)
   - `Features/QualityTesting/QualityTestController.QueueTestRun`
   - `Features/TranscodeJob/TranscodeJobRepository.SaveTranscodeProgress`
4. Delete `ServiceControlRepository.CreateActiveJob` and `.CreateServiceCommand` (no callers).
5. Tests:
   - `Tests/Pipeline/Harness/Invocation._InsertQueueRow` -> `ExecuteReturning`.
   - `Tests/Contract/TestJobPhaseTransitions` mock -> `ExecuteReturning` returns `[{'Id': 42}]`.
   - New `Tests/Contract/TestInsertReturningId.py` covering C1, C2 and C3.
6. Close BUG-0109 (fixed in 258c0ccf); file the two (b) items.
7. Smoke C4-C7.

### Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| N1 | insert -> id | `DatabaseService.ExecuteReturning` | `list[CaseInsensitiveDict]`, one row with `Id` | Caller indexes `[0]['Id']`; an empty list raises `IndexError` | C2, C3 |
| N2 | ActiveJobs id -> completion | `CreateActiveJob` / `_CreateActiveJob` | int `ActiveJobs.Id` | `DELETE FROM ActiveJobs WHERE Id = %s` at job end | C4, C6 |
| N3 | progress id -> updates | `SaveTranscodeProgress` / `CreateProgressRecord` | int progress row id | Later updates target that id | C4, C5 |
| N4 | queue id -> HTTP | `QueueTestRun` | `Accepted[].QueueId` int | Operator UI shows queue ids | C7 |

### Files

```
Core/Database/database-architecture.feature.md            -- EDIT: C15 insert id comes from its own RETURNING
Core/Database/DatabaseService.py                          -- EDIT: delete LastInsertId + GetLastInsertId
Core/Database/BaseRepository.py                           -- EDIT: delete GetLastInsertId
WorkerService/ProbeWorker.py                              -- EDIT: _CreateActiveJob via ExecuteReturning
Features/ServiceControl/ActiveJobRepository.py            -- EDIT: CreateActiveJob via ExecuteReturning
Features/ServiceControl/ServiceControlRepository.py       -- EDIT: delete dead CreateActiveJob + CreateServiceCommand
Features/QualityTesting/QualityTestRepository.py          -- EDIT: 3 inserts via ExecuteReturning
Features/QualityTesting/QualityTestingBusinessService.py  -- EDIT: CreateProgressRecord via ExecuteReturning
Features/QualityTesting/QualityTestController.py          -- EDIT: QueueTestRun via ExecuteReturning
Features/TranscodeJob/TranscodeJobRepository.py           -- EDIT: SaveTranscodeProgress via ExecuteReturning
Tests/Pipeline/Harness/Invocation.py                      -- EDIT: harness insert via ExecuteReturning
Tests/Contract/TestJobPhaseTransitions.py                 -- EDIT: mock ExecuteReturning
Tests/Contract/TestInsertReturningId.py                   -- CREATE: C1-C3
memory/KNOWN-ISSUES.md, memory/BUG-INDEX.md               -- EDIT: close BUG-0109; file OOS (b) items
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Insert id comes from the statement's own `RETURNING` (no shared last-insert state) | `Core/Database/database-architecture.feature.md` (C15) | TBD until close |

### Verification

### Decisions Made

---

## Closure (thin-pointer archive shape)

When this directive is ready to close: confirm Promotions, set `Status: Closed -- <outcome>` with a `**Closed:**` line, then `git mv .claude/directive.md .claude/directives/closed/YYYY-MM-DD-<slug>.md` and copy `_template.md` back. Governed by `.claude/rules/doc-layering.md` and `.claude/rules/ceo-mode.md`.
