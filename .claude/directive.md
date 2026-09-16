# Directive: bug-0095-failure-classification

**Status:** Active -- phase: IMPLEMENTING

## Outcome

Implement `failure-accounting.feature.md` C10 (base classifier + column + table + `/FailedJobs` grouping + `/settings` CRUD) + C11 (Terminal-vs-Transient discrimination + no-retry policy + expanded seed rules for BUG-0100..0104). Delivers Phase 1 of the transcode-failure roadmap (`memory/TRANSCODE-FAILURE-PLAN.md`).

Ships the three-bucket failure model:
1. **Transient** -- ephemeral / worker crash / GPU OOM (auto-retry ok)
2. **PipelineDefect** -- code gap; classifier tracks; separate directives fix root (BUG-0102 / BUG-0104)
3. **SourceTerminal** -- Terminal=TRUE on FailureClasses; auto-requeue REFUSES; operator remediation labeled (regrab / manual)

C10 was doc'd 2026-08-27 (directive `2026-08-27-file-bug-0095-failure-class-taxonomy.md`) but never implemented. C11 adds Terminal + no-retry after operator's 2026-09-15 scope-lock on visible transcode failures.

## Acceptance Criteria

Contract is `failure-accounting.feature.md` C10 + C11. All Verifiable clauses in both must pass.

Directive-close bar (see `ceo-mode.md` VERIFYING->DELIVERING smoke gate): every seed rule matches its intended sample stderr against real recent TranscodeAttempts rows on live DB; Terminal=TRUE class row + auto-requeue call inserts no new TranscodeQueue row on I9; operator flip of Terminal in `/settings` observed by next claim tick without restart.

## Call-Graph Audit

- **Flow docs touched:** `Features/FailureAccounting/failure-accounting.flow.md` (extend: add classifier stage after attempt INSERT + terminal-gate seam on claim/admission queries). No parallel flow doc created.
- **Orchestration mode-branch:** none introduced. Classifier is called from every failure-INSERT site (uniform); terminal gate is a WHERE-clause fragment (data-driven, not orchestration).
- **Shared output columns:** `TranscodeAttempts.FailureClass` written by classifier at INSERT; single writer. `FailureClasses.Terminal` written only via `/settings` CRUD; single writer.
- **OOS clarity:** every out-of-scope item categorized (b) -- acknowledged debt.
- **Config-driven graph shape:** none. Terminal is DATA (WHERE-clause value); flipping it changes admission behavior but does not add/remove nodes in the call graph.

## Out of Scope

- **(b) BUG-0102 mov_text drop implementation.** Classifier tags `subtitle_sample_too_large`; BUG-0102 directive fixes pipeline root. Two directives.
- **(b) BUG-0104 pix_fmt normalization implementation.** Same pattern: classifier tags `pix_fmt_unsupported`; BUG-0104 fixes root.
- **(b) BUG-0103 source-readability preflight.** Classifier tags `source_unreadable` + `stereo_downmix_source_unreadable`; BUG-0103 adds pre-encode preflight so classifier stops seeing this class on new attempts.
- **(b) BUG-0100 loudness validator diagnosis.** Classifier tags `loudness_invalid_unrecoverable` Terminal=FALSE pending; BUG-0100 diagnoses + potentially flips Terminal.
- **(b) BUG-0105 FileReplacement pre-swap validation.** Prevents new `source_unreadable` class writes; separate directive.
- **(b) Backfilling historical FailureClass on 122+ existing failed rows.** One-shot script deferred until BUG-0101 decomposition; ships strictly after this directive lands.
- **(b) Bulk regrab operations for existing Terminal-classifiable rows.** Phase 5 operator-driven; not automated.

## Files

- `Scripts/SQLScripts/AddFailureClassesTable_2026_09_16.py` (new; FailureClasses table + Terminal column + 12 seed rules)
- `Scripts/SQLScripts/AddFailureClassColumn_2026_09_16.py` (new; `TranscodeAttempts.FailureClass TEXT NULL`)
- `Scripts/SQLScripts/AddPriorFailureClassAudit_2026_09_16.py` (new; `FailureBudgetResets.PriorFailureClass TEXT NULL`)
- `Features/FailureAccounting/Services/FailureClassifier.py` (new)
- `Features/FailureAccounting/Repositories/FailureClassesRepository.py` (new; fresh DB read per call per `db-is-authority`)
- `Core/Database/TerminalFailurePredicate.py` (new; `BuildTerminalGate(MediaFileIdColumn)` SQL fragment helper)
- `Features/TranscodeJob/Worker/AttemptRecordService.py` (extend; call classifier on failure INSERT)
- `Features/TranscodeJob/ProcessTranscodeQueueService.py` (extend; classifier on `HandleJobFailure` path)
- `Repositories/DatabaseManager.py` (extend; every `ClaimNextPending*` query adds TerminalFailurePredicate)
- `Features/TranscodeQueue/QueueManagementBusinessService.py` (extend; `NextTranscodeBatch` / `SmartPopulateQueue` / `AddSuggestionsToQueue` / `QueueAllMatching` / `AddJobToQueue` add TerminalFailurePredicate; return Terminal envelope on single-file admission)
- `Features/FailureAccounting/Repositories/FailedJobsRepository.py` (extend; GetCappedJobs adds FailureClass JOIN + Terminal grouping)
- `Features/FailureAccounting/FailedJobsController.py` (extend; groups response by Terminal)
- `Templates/FailedJobs.html` (extend; Terminal card section + `card--terminal` CSS class)
- `Features/Settings/SettingsController.py` (extend; add FailureClasses CRUD endpoints)
- `Templates/settings.html` (extend; FailureClasses tab -- POSIX-regex validation on ErrorPattern input)
- `Features/FailureAccounting/failure-accounting.feature.md` (already amended with C11; Progress checklist below)
- `Features/FailureAccounting/failure-accounting.flow.md` (extend; new stage + seams)
- `Tests/Contract/TestFailureClassifier.py` (new)
- `Tests/Contract/TestFailureClassTerminal.py` (new; 5 test cases per C11 Verifiable list)
- `Tests/Contract/TestTerminalFailurePredicate.py` (new; SQL fragment shape + JOIN semantics)

## Progress

- [x] Standards review (NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN) -- feature doc C10+C11 pre-existing + operator-approved 2026-09-16
- [x] Plan phase (NEEDS_PLAN -> NEEDS_DOC_PREREAD) -- feature doc is the plan
- [x] Doc preread (NEEDS_DOC_PREREAD -> IMPLEMENTING) -- read failure-accounting.feature.md + failure-accounting.flow.md, TranscodeAttempts + FailureBudgetResets schema, existing FailedJobsRepository + FailedJobsController + Templates/FailedJobs.html
- [ ] Migrations land + seed rules idempotent
- [ ] Classifier service + wired into every failure-INSERT path
- [ ] Terminal predicate helper + wired into every claim/admission query
- [ ] Reset audit path writes PriorFailureClass
- [ ] `/FailedJobs` Terminal section renders
- [ ] `/settings` FailureClasses CRUD ships (POSIX-regex validation)
- [ ] Contract tests green (Classifier + Terminal + Predicate)
- [ ] Flow doc extension + Seams row for classifier stage
- [ ] I9 smoke gate: seed-rule live-match audit + Terminal blocks re-queue live + operator flip observed next tick without restart
- [ ] DELIVERING: `### Promotions` populated + directive advanced

### Promotions

(Populated at DELIVERING.)

### Plan

1. **Migrations first (independent, idempotent).**
   - `AddFailureClassesTable_2026_09_16.py`: `CREATE TABLE IF NOT EXISTS FailureClasses (ClassName TEXT PRIMARY KEY, Priority INT NOT NULL, ErrorPattern TEXT NOT NULL, Terminal BOOL NOT NULL DEFAULT FALSE, Remediation TEXT NOT NULL, CreatedAt TIMESTAMP DEFAULT NOW(), UpdatedAt TIMESTAMP DEFAULT NOW())`. Seed 12 rules on empty-table (idempotent via `ON CONFLICT (ClassName) DO NOTHING`).
   - `AddFailureClassColumn_2026_09_16.py`: `ALTER TABLE TranscodeAttempts ADD COLUMN IF NOT EXISTS FailureClass TEXT NULL`.
   - `AddPriorFailureClassAudit_2026_09_16.py`: `ALTER TABLE FailureBudgetResets ADD COLUMN IF NOT EXISTS PriorFailureClass TEXT NULL`.

2. **Classifier service.**
   - `Services/FailureClassifier.Classify(ErrorMessage: str) -> str` runs `SELECT ClassName FROM FailureClasses WHERE %s ~* ErrorPattern ORDER BY Priority LIMIT 1`. Returns `'unclassified'` on no match. Fresh DB read per call (no cache) via `Repositories/FailureClassesRepository`.
   - Log INFO at each classification: `classified attempt <id> as <class> (Terminal=<bool>)`.

3. **Wire classifier into failure-INSERT paths.**
   - `AttemptRecordService.Create` (canonical failure INSERT) sets `FailureClass = FailureClassifier().Classify(ErrorMessage)` when `Success=FALSE`.
   - `ProcessTranscodeQueueService.HandleJobFailure` and any other insert path -- grep `SaveTranscodeAttempt` callers with `Success=False`.

4. **Terminal gate helper.**
   - `Core/Database/TerminalFailurePredicate.BuildTerminalGate(MediaFileIdColumn: str) -> str` returns the JOIN + WHERE fragment. Whitelists column name (SQL-injection safe) matching FailureBudgetPredicate.

5. **Wire terminal gate into gate-consumers.**
   - Each of the C6 consumers (`ClaimNextPendingTranscodeJob`, `ClaimNextPendingRemuxJob`, `ClaimQualityTestJob`, `NextTranscodeBatch`, `SmartPopulateQueue`, `AddSuggestionsToQueue`, `QueueAllMatching`, `AddJobToQueue`) adds `BuildTerminalGate` fragment alongside `BuildCapPredicate`.
   - `AddJobToQueue` on Terminal-gate-hit returns `{Success: False, FailureClassTerminal: True, CanOverride: False, Remediation: <text>}` (Terminal supersedes CapReached CanOverride semantics).

6. **Reset audit extension.**
   - `FailedJobsRepository.ResetFailureBudget` reads latest failing attempt's `FailureClass` and writes to new `FailureBudgetResets.PriorFailureClass` column. Same in Bulk variant.

7. **`/FailedJobs` extension.**
   - `FailedJobsRepository.GetCappedJobs` LEFT JOIN `FailureClasses` on `latest_fail.FailureClass`; return `FailureClass`, `FailureClassTerminal`, `FailureClassRemediation` per row.
   - Controller groups response into `TerminalRows` + `TransientRows`.
   - Template renders two sections; Terminal rows use `card--terminal` CSS.

8. **`/settings` FailureClasses CRUD.**
   - SettingsController adds `GET /api/Settings/FailureClasses`, `POST /api/Settings/FailureClasses`, `DELETE /api/Settings/FailureClasses/<name>`.
   - POST validates ErrorPattern as compilable POSIX regex (server-side) before UPSERT.
   - Template extends with sortable table + inline edit + Terminal checkbox.

9. **Contract tests.**
   - `TestFailureClassifier`: every seed rule's regex matches its intended sample stderr fixture (12 test cases + first-match-wins ordering).
   - `TestFailureClassTerminal`: 5 cases per C11 Verifiable list.
   - `TestTerminalFailurePredicate`: fragment shape + column whitelist + JOIN produces expected rows on synthetic data.

10. **Flow doc extension.**
    - `failure-accounting.flow.md` add classifier stage between "attempt INSERT" and "operator surface"; add terminal-gate cross-stage seam.

11. **I9 smoke gate (per `ceo-mode.md` VERIFYING->DELIVERING).**
    - After migrations + classifier land: `UPDATE TranscodeAttempts SET FailureClass = FailureClassifier.Classify(ErrorMessage) WHERE Success = FALSE AND FailureClass IS NULL` backfills recent failures; verify class distribution matches expectations (Doctor Who S08E10 -> `loudness_invalid_unrecoverable`, Weeds S02E12 -> `stereo_downmix_source_unreadable`, etc).
    - Verify Terminal blocks re-queue: insert synthetic Terminal-class attempt on a test MediaFile + call `AddJobToQueue`; assert refuses.
    - Verify live operator flip: change `FailureClasses.Terminal` for one class via SQL (simulating `/settings` toggle); observe next `ClaimNextPendingTranscodeJob` respects new value without WorkerService restart.

12. **DELIVERING.**
    - Populate `### Promotions` mapping directive artifacts to durable homes (feature doc's C10 + C11 are already promoted; flow doc extension is the primary promotion).
