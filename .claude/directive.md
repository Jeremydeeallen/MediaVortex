# Current Directive

**Set:** 2026-06-28
**Status:** Active -- phase: NEEDS_STANDARDS_REVIEW
**Slug:** transcode-worker-unification
**Replaces:** in-flight pivot on top of `work-transcode-unified` (at DELIVERING; awaiting operator close)
**Interrupts:** work-transcode-unified

## Outcome

The compliance-correction pipeline runs ONE orchestration path regardless of `ProcessingMode`. The three current divergent processors (`TranscodeJobProcessor`, `RemuxJobProcessor`, `SubtitleFixJobProcessor`) collapse into a single `JobProcessor` Template Method with mode-specific Strategy hooks (`BuildCommand`, `HandleResult`). The post-encode audio-policy attestation step runs for every mode that produces ffmpeg output, populating `TranscodeAttempts.AudioPolicyResolved` and `AudioTracksEmittedJson` so the `ComplianceGate` has data to validate against. The parallel `Features/TranscodeQueue/remux.flow.md` collapses into `transcode.flow.md` — one durable flow doc for compliance correction with mode-specific stage variants documented as strategy hooks, not as a separate pipeline.

## Call-Graph Audit

Per `.claude/rules/call-graph-audit.md`. All four signals were FIRING at work-transcode-unified's DELIVERING claim; this directive's outcome closes them.

### Call graph traced (compliance correction lifecycle)

1. Operator clicks Queue All on `/Work/<bucket>` (UI: WorkBucket vertical, delivered by sibling directive `work-transcode-unified`).
2. `WorkBucketController.queue_series` → `QueueAdmissionAppService.AdmitSeries` → `QueueAdmissionRepository.AdmitSeries` → bulk INSERT TranscodeQueue Pending.
3. Worker polls `DatabaseManager.ClaimNextPendingTranscodeJob` → returns one TranscodeQueue row.
4. `WorkerLoopService` dispatches → `ProcessTranscodeQueueService.ProcessJob` (line 348-358).
5. **CURRENT — orchestration mode-branch (Signal 2 fires):** `if Job.IsRemux: RemuxJobProcessor` else if SubtitleFix: `SubtitleFixJobProcessor` else: `TranscodeJobProcessor`.
6. Per-mode FFmpeg execution via mode-specific orchestration body.
7. Per-mode result handling (`HandleRemuxResult` vs `HandleTranscodeResult` vs `HandleSubtitleFixResult`).
8. **CURRENT — attestation universally missing (Signal 3 fires):** `PostEncodeMeasurementService.Measure` is NEVER called from any processor. `AudioPolicyResolved IS NULL` for all 36000+ TranscodeAttempts.
9. `FileReplacementBusinessService.ProcessFileReplacement` (mode-aware but at least called from a single library, not duplicated).
10. `ComplianceGate.Decide` (in `Features/QualityTesting/Disposition/`) → blocks replacement when attestation is empty → falls back to `Disposition='NoReplace', DispositionReason='ComplianceGateFailed'`.
11. Compliance recompute.

### Signal findings

**Signal 1 — Multiple flow docs for one conceptual operation: FIRES.**
- `transcode.flow.md` (ST1-ST9) — describes the full compliance-correction pipeline.
- `Features/TranscodeQueue/remux.flow.md` (ST1-ST13) — a parallel flow doc for the same conceptual operation, with its OWN stage IDs and seam table.
- Resolution: collapse `remux.flow.md` content into `transcode.flow.md` as a "Strategy variants" section under ST6 (TRANSCODE stage). `remux.flow.md` file gets deleted; cross-references rewritten.

**Signal 2 — Mode-branching at orchestration level: FIRES.**
- `ProcessTranscodeQueueService.ProcessJob` line ~351: `if Job.IsRemux: ProcessRemuxJob` and similar branches to `ProcessSubtitleFix`, `ProcessTranscodeJob`.
- Three processor classes carry duplicated orchestration: ActiveJob create → mark Running → load MediaFile → setup file preparation → BuildCommand (mode-specific, Strategy) → ExecuteFFmpeg → verify output → HandleResult (mode-specific, Strategy) → cleanup.
- Resolution: one `JobProcessor` base class owns steps 1-3, 5, 7, 9 (Template Method shape — identical across modes). Mode-specific `BuildCommand` and `HandleResult` become Strategy methods on per-mode subclasses. Existing `JobProcessor.py` at `Features/TranscodeJob/Worker/` is already the abstract base — needs to be extended with the Template Method logic.

**Signal 3 — Shared output columns sparsely populated: FIRES.**
- `TranscodeAttempts.AudioPolicyResolved IS NOT NULL` count: **0** across the entire DB.
- `TranscodeAttempts.AudioTracksEmittedJson != '[]'::jsonb` count: **0** across the entire DB.
- `PostEncodeMeasurementService.Measure` exists at `Features/AudioNormalization/Services/PostEncodeMeasurementService.py` but is not called from any processor. ComplianceGate then fails-closed on Remux output (no attestation = "cannot validate, refuse replace") and fails-open on Transcode output (other compliance signals carry it).
- Resolution: the unified `JobProcessor.Process` calls `PostEncodeMeasurementService.Measure` AFTER a successful ffmpeg run, BEFORE `HandleResult`. Populates both columns for every mode.

**Signal 4 — "Out of Scope" ambiguity: managed.**
- This directive's OOS list (below) categorizes every item explicitly. Default category: (a) preserve behavior + collapse duplication.

## Acceptance Criteria

Each criterion passes the five litmus tests in `.claude/rules/feature-criteria.md` (rename / outsider / rewrite / negation / stability).

**Orchestration unification:**

1. **C1.** `Features/TranscodeJob/Worker/` contains exactly ONE concrete processor class hierarchy: an abstract `JobProcessor` base implementing `Process(Job) -> JobResult` as a Template Method, plus per-mode Strategy subclasses (`TranscodeJobStrategy`, `RemuxJobStrategy`, `AudioFixJobStrategy`, `SubtitleFixJobStrategy`) that ONLY implement `BuildCommand(Job, MediaFile, Context) -> CommandSpec` and `HandleResult(Job, Result, AttemptId, ActiveJobId, OutputPath) -> None`. The classes `TranscodeJobProcessor`, `RemuxJobProcessor`, `SubtitleFixJobProcessor` no longer exist. Spot-checkable: `grep -rn "class.*JobProcessor.*JobProcessor" Features/TranscodeJob/Worker/` returns one base + N strategy subclasses, never N processor classes.

2. **C2.** `ProcessTranscodeQueueService.ProcessJob` contains ZERO mode-branching at the orchestration layer. The function body picks the Strategy via a lookup (e.g. `STRATEGIES[Job.ProcessingMode]`) and calls `JobProcessor(strategy).Process(Job)`. Spot-checkable: `grep -nE "if .+\.IsRemux|if .+\.ProcessingMode\b" Features/TranscodeJob/ProcessTranscodeQueueService.py` returns zero hits.

3. **C3.** Identical orchestration steps run for every mode: ActiveJob create → mark Running → load MediaFile → file preparation → BuildCommand (strategy) → ExecuteFFmpeg → verify output → PostEncodeMeasurement → HandleResult (strategy) → cleanup. Verifiable by running a Transcode job, a Remux job, and an AudioFix job through the same processor and confirming each writes the same set of columns to `TranscodeAttempts` (mode-discriminator excepted).

**Post-encode attestation wired:**

4. **C4.** `JobProcessor.Process` invokes `PostEncodeMeasurementService.Measure(OutputPath, TranscodeAttemptId)` after every successful ffmpeg run, BEFORE `HandleResult`. Verifiable: after this directive lands, run one job of each mode and assert `SELECT AudioPolicyResolved, AudioTracksEmittedJson FROM TranscodeAttempts WHERE Id IN (<three new ids>)` returns non-NULL / non-`'[]'` for all three.

5. **C5.** `MediaFileId=621412` (Trolls World Tour Remux that failed under work-transcode-unified) re-runs successfully end-to-end through the unified processor: claim → ffmpeg → measurement → ComplianceGate evaluates against populated attestation → `Disposition='Replace'` → `FileReplaced=True` → `MediaFiles.IsCompliant=True` → `WorkBucket IS NULL`. The 1-of-9 smoke failure becomes 9-of-9.

**Flow doc unification:**

6. **C6.** `Features/TranscodeQueue/remux.flow.md` does not exist. Its content has been absorbed into `transcode.flow.md` as a "Strategy variants" sub-section under ST6 (TRANSCODE), with per-mode notes on what `BuildCommand` and `HandleResult` differ on. All cross-references to `remux.flow.md` in feature docs / code anchors are rewritten to point at `transcode.flow.md` with the relevant ST anchor.

7. **C7.** `transcode.flow.md` `## Seams` table documents the single ST6 transition for compliance correction regardless of mode; mode-specific differences are documented as Strategy-method seams within the same ST6 section, not as parallel pipeline transitions.

**Backward compatibility + safety:**

8. **C8.** No regression in successful Transcode-mode behavior. `SELECT count(*) FROM TranscodeAttempts WHERE Success=TRUE AND Disposition='Replace' AND ProfileName != 'Remux' AND ProfileName != 'AudioFix' AND AttemptDate > '<directive-start>'` keeps growing post-deploy.

9. **C9.** No regression in idempotent claim semantics. Claim invariants (`db-is-authority.md`) preserved; `TestClaimAuthority` test suite stays green.

10. **C10.** Audit test `TestNoShowSettingsReferences` stays green (no resurrection of deleted vertical references during this refactor).

## Out of Scope

Categorized per call-graph-audit Signal 4. Default category: (a) behavior preserved AND duplication collapsed in-flight. Items below are explicitly category (b).

- **`FileReplacementBusinessService` rewrite** — category (b). Already a single library (not duplicated per mode); used by all paths. Not touched here. Internal duplication WITHIN that file is OOS.
- **`ComplianceGate` logic changes** — category (b). The gate's evaluation rules stay unchanged; this directive only ensures the gate has populated attestation columns to evaluate against. C5 verifies the gate flips its verdict (from `NoReplace` to `Replace`) on 621412 strictly because the attestation now exists, not because the gate's rules changed.
- **TranscodeQueue schema** — category (b). Unchanged.
- **WorkerCapabilityPredicate / claim queries** — category (b). Unchanged; verified via C9.
- **`/Work/<bucket>` UI** — category (b). Already delivered by sibling directive `work-transcode-unified` (at DELIVERING). This directive ships under it; UI does not change.

## Constraints

- Template Method pattern: ONE base class owns the orchestration; Strategies override per-mode hooks. Liskov substitutable.
- Behavior-preserving refactor: NO new criteria observable in the operator UI. The system does the same thing; just with shared code.
- Push every commit on main.
- Live smoke per phase exit: each major step (collapse processors / wire measurement / consolidate flow doc) ships with a worker-restart + one job of each mode verified end-to-end.
- R12: no multi-line docstrings.
- R14: cross-vertical doc sweep deletes obsolete references, no annotation lines.

## Escalation Defaults

- Tradeoff between behavior-preserving rigor and architectural cleanliness → cleanliness, provided behavior is preserved (verified by C5 + C8).
- Risk tolerance: low. The compliance correction pipeline is operator-critical; regressions here block production work. Stage changes through one bucket at a time during smoke.
- Worker restart authority: operator owns it (memory: `feedback_user_starts_webservice.md`); but on I9 dev workstation I have full restart authority (memory: same file, "I control WebService and WorkerService on I9").

## Engineering Calls Already Made

- Template Method (not Strategy-via-composition-only): `JobProcessor` is already an abstract base class. The cleanest pattern is to fill in its `Process` with the orchestration body and have subclasses override hooks. Strategy-via-composition would mean a separate Strategy interface + a single Processor concrete that holds a Strategy — more indirection for no clearer separation.
- `PostEncodeMeasurementService.Measure` is called BEFORE `HandleResult` (not inside it). HandleResult is mode-specific; Measure is universal. Order matters because HandleResult's disposition decision needs the attestation populated.
- Flow doc consolidation direction: `remux.flow.md` → `transcode.flow.md` (collapse the smaller into the larger). Reverse direction (rename transcode → compliance-correction.flow.md) is a bigger doc churn for no semantic gain.

## Status

Phase advances by editing the `**Status:**` header above. PreToolUse hook reads ONLY that header line. Standards in `.claude/standards/index.md`.

Phase machine: `NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN -> NEEDS_DOC_PREREAD -> IMPLEMENTING -> VERIFYING -> DELIVERING`.

### Progress

- [ ] T1 — Define `JobProcessor` Template Method (`Process` body owns the orchestration)
- [ ] T2 — Extract `TranscodeJobStrategy` from `TranscodeJobProcessor` (BuildCommand + HandleResult only)
- [ ] T3 — Extract `RemuxJobStrategy` from `RemuxJobProcessor`
- [ ] T4 — Extract `AudioFixJobStrategy` (currently embedded in RemuxJobProcessor; pull apart)
- [ ] T5 — Extract `SubtitleFixJobStrategy` from `SubtitleFixJobProcessor`
- [ ] T6 — Wire `PostEncodeMeasurementService.Measure` into `JobProcessor.Process` after successful ffmpeg, before HandleResult
- [ ] T7 — Replace `ProcessJob`'s `if Job.IsRemux: ...` dispatch with `STRATEGIES[Job.ProcessingMode]` lookup → `JobProcessor(strategy).Process(Job)`
- [ ] T8 — Delete `TranscodeJobProcessor.py`, `RemuxJobProcessor.py`, `SubtitleFixJobProcessor.py` (now redundant)
- [ ] T9 — Collapse `remux.flow.md` into `transcode.flow.md` (Strategy variants sub-section under ST6); delete `remux.flow.md`; sweep cross-references
- [ ] T10 — Re-queue MediaFileId=621412 through the unified path; verify C5 end-to-end
- [ ] T11 — Run each mode (Transcode, Remux, AudioFix, SubtitleFix) once through the unified processor; verify `AudioPolicyResolved` + `AudioTracksEmittedJson` populated for each; verify Disposition matches pre-refactor expectations
- [ ] T12 — Verify full Tests/Contract/ suite green (no new failures vs. work-transcode-unified close baseline)
- [ ] T13 — Advance to DELIVERING; populate Promotions + Verification; operator close

### Files

```
Features/TranscodeJob/Worker/JobProcessor.py                 -- EDIT: fill in Process Template Method
Features/TranscodeJob/Worker/Strategies/__init__.py          -- CREATE: strategy package
Features/TranscodeJob/Worker/Strategies/TranscodeJobStrategy.py    -- CREATE: BuildCommand + HandleResult
Features/TranscodeJob/Worker/Strategies/RemuxJobStrategy.py        -- CREATE
Features/TranscodeJob/Worker/Strategies/AudioFixJobStrategy.py     -- CREATE
Features/TranscodeJob/Worker/Strategies/SubtitleFixJobStrategy.py  -- CREATE
Features/TranscodeJob/Worker/TranscodeJobProcessor.py        -- DELETE
Features/TranscodeJob/Worker/RemuxJobProcessor.py            -- DELETE
Features/TranscodeJob/Worker/SubtitleFixJobProcessor.py      -- DELETE
Features/TranscodeJob/ProcessTranscodeQueueService.py        -- EDIT: ProcessJob dispatch uses strategy lookup
Features/AudioNormalization/Services/PostEncodeMeasurementService.py -- EDIT (small): expose Measure as the unified entry point
transcode.flow.md                                            -- EDIT: absorb remux.flow.md ST1-ST13 as ST6 Strategy variants
Features/TranscodeQueue/remux.flow.md                        -- DELETE
Features/TranscodeJob/TranscodeJob.feature.md                -- EDIT: document the Template Method + Strategy structure
Features/TranscodeJob/Worker/worker-loop.feature.md          -- EDIT: rewrite ProcessJob dispatch description
Tests/Contract/TestUnifiedJobProcessor.py                    -- CREATE: integration test exercising all four modes through the unified processor
Tests/Contract/TestPostEncodeMeasurementWiring.py            -- CREATE: contract test that every mode populates AudioPolicyResolved
```

### Promotions

Required when phase advances to DELIVERING. Populated incrementally per `feedback_promotions_grow_incrementally.md`.

| Source artifact | Target file | Commit |
|---|---|---|

### Verification

Required when phase advances to VERIFYING. One entry per acceptance criterion.

- **C1:** TBD
- **C2:** TBD
- **C3:** TBD
- **C4:** TBD
- **C5:** TBD (621412 re-run)
- **C6:** TBD
- **C7:** TBD
- **C8:** TBD
- **C9:** TBD
- **C10:** TBD

### Decisions Made

Engineering calls made under ambiguity. Empty at start; populated as tasks execute.
