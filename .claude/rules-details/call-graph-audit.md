# Call-Graph Audit — Details, Checklist, Examples

Companion to `.claude/rules/call-graph-audit.md`. The short rule is the invariant; this file is how-to.

## The audit, step by step

Run during NEEDS_STANDARDS_REVIEW, before writing the spec. The output is the `## Call-Graph Audit` section of `.claude/directive.md`.

### Step 1 — Enumerate the feature's call graph

For the directive's stated feature (e.g. "operator queues a compliance correction from /Work/<bucket>"), trace the FULL request lifecycle from UI click to final DB write. Use Grep to find:

- The HTTP route handler.
- The service / repository it calls.
- The DB writes those produce.
- The worker / background process that consumes those writes.
- The cleanup / notification / archival steps downstream.

Write each step as a line. The list is the WHOLE call graph, not just the layer the directive plans to edit.

### Step 2 — Find every relevant `*.flow.md`

```
Glob: **/*.flow.md
```

For each one in the result, ask: does this describe a stage the feature's call graph touches? If yes, list it.

**Signal 1 fires** if TWO `*.flow.md` files describe what should be one conceptual operation (e.g. `transcode.flow.md` ST6 = "TRANSCODE stage" AND a separate `remux.flow.md` defines its own ST1-ST13 for Remux jobs — that's two flow docs for one conceptual stage).

When Signal 1 fires, the right options are:
- (preferred) Absorb the unification into this directive's scope.
- Open a sibling directive that unifies the flow docs + the underlying code, run it FIRST, then this one.
- Explicitly write under `## Out of Scope`: "We ship on top of the current divergent pipeline. The pipeline unification is its sibling directive `<slug>`. We accept that, e.g., new GUI features touch code paths that branch on mode."

### Step 3 — Find every mode-branch in the orchestration layer

```
Grep -nE "if .+\.IsRemux|if .+ == ['\"]Remux['\"]|if .+ == ['\"]Transcode['\"]|if ProcessingMode|if Mode" -t py Features/ Worker* Repositories/ Services/
```

For each hit, classify:
- **Strategy hook** (acceptable): the branch picks a per-mode command builder, codec config, etc. — i.e. ONE step in an otherwise-identical orchestration differs.
- **Orchestration branch** (Signal 2 — FIRES): the branch routes to an entirely different orchestration function / class. `if Job.IsRemux: ProcessRemuxJob` is the textbook violation.

### Step 4 — Audit shared output columns

Identify the shared output table for the pipeline (commonly `TranscodeAttempts`, `MediaFiles`, or an audit-log table). For each column added to that table by ANY mode's code path, run:

```
py Scripts/SQLScripts/QueryDatabase.py sql "SELECT count(*) FILTER (WHERE <col> IS NOT NULL) AS populated, count(*) AS total, count(DISTINCT <mode-column>) FILTER (WHERE <col> IS NOT NULL) AS modes_populating FROM <table>"
```

**Signal 3 fires** when `populated > 0` but `modes_populating < total_modes`. That means some modes write the column and some don't — the modes that don't are missing a step.

Historical example from work-transcode-unified close: `SELECT count(*) FROM TranscodeAttempts WHERE AudioPolicyResolved IS NOT NULL` returned 0 across ALL attempts. Every mode was missing the attestation step. The ComplianceGate was then failing-closed on remux because there was no attestation to validate. Caught only via 9-media smoke; should have been caught at audit time.

### Signal 5 — Config-driven call-graph shape

Feature flags, runtime config, and toggles must drive DATA, never ORCHESTRATION. If turning a flag off REMOVES a node from the call graph (vs short-circuits a path through it), that's a violation. The call graph is a static property of the code; the same functions are called regardless of config -- config only changes which values flow through them and which branches the data takes.

#### Detection commands

For each feature flag identified in `SystemSettings`, `PostTranscodeGateConfig`, `Workers.*Enabled`, etc., grep for branches that depend on the flag:

```
grep -rnE "if .*Enabled.*:|if not .*Enabled.*:" Features/ Core/ Services/ Repositories/ --include="*.py"
```

For each hit, classify:
- **Data-driven (acceptable):** the flag sets a value that downstream functions consume (e.g. `QualityTestRequired=True` written to a TranscodeAttempts row; the disposition decider reads it and branches on the column value). The flag flowed through; the orchestration shape is identical.
- **Code-driven (violation):** the flag selects which function to call (e.g. `if QualityTestEnabled: RunQualityTest() else: pass`). Turning off the flag erases the QualityTest node from the call graph.

The fix for violations is to make the flag a runtime parameter consumed at a fixed node, not a branch that wraps the node itself.

#### Example from this directive

`QualityTestController:631-667` (pre-fix) had its own inline cascade for "what profile applies" that ONLY ran when QT was enabled. With QT disabled, the cascade was dormant code that grep would never find via runtime tracing. After T11 fix, the controller injects `EffectiveProfileResolver` and calls `.Resolve(mediafile)` unconditionally; the QT enabled/disabled flag only controls whether the SCORING step downstream consumes the result.

This catches latent-landmine code that activates the moment a flag flips back.

#### When this signal fires hardest

Look for "feature parity" claims in docs -- they're usually code-driven branches dressed up as data-driven. If the spec says "when X is enabled, the system does A; when X is disabled, the system does B" -- that's two different orchestrations. The right design is "the system always does C, where C is parameterized by X."

### Step 5 — Categorize every Out of Scope item

For each item the spec puts in `## Out of Scope`, decide which category applies:

- **(a) Behavior preserved, duplication collapsed in-flight.** Default. The OOS clause means "we won't change WHAT the other vertical does." It does NOT mean "we tolerate code duplication." Extract shared helpers as part of THIS directive even when the consuming vertical is OOS.

- **(b) Acknowledged debt that survives the directive.** Requires explicit operator buy-in at spec time, written into `## Out of Scope` verbatim. Reserve for cases where the cleanup is genuinely a separate directive's worth of work (cross-vertical refactor, schema change, etc.).

**Signal 4 fires** when an OOS item is ambiguous (which category?). Resolve to (a) by default.

Historical example: work-transcode-unified spec wrote "EffectiveProfileResolver rewrite (it stays — reads MediaFiles.AssignedProfile, unchanged behavior)" — ambiguous. Was the SQL duplication with `ProfileName.__init__` in scope? Spec didn't say. I parked it as a "decision" rather than collapsing. Operator had to push back to get G6 fully closed. (a) was the correct default.

## How to write the `## Call-Graph Audit` section

```markdown
## Call-Graph Audit

### Call graph traced

1. Operator clicks Queue All on `/Work/<bucket>` →
2. `WorkBucketController.queue_series` →
3. `QueueAdmissionAppService.AdmitSeries` →
4. `QueueAdmissionRepository.AdmitSeries` → bulk INSERT TranscodeQueue Pending
5. Worker polls `DatabaseManager.ClaimNextPendingTranscodeJob` →
6. `ProcessTranscodeQueueService.ProcessJob` →
7. **Mode branch:** `if Job.IsRemux: RemuxJobProcessor else: TranscodeJobProcessor` ← **Signal 2 FIRES**
8. Per-mode FFmpeg execution →
9. Per-mode result handling →
10. `FileReplacementBusinessService.ProcessFileReplacement` →
11. Compliance recompute.

### Flow docs the feature touches

- `transcode.flow.md` (ST1-ST9)
- `Features/TranscodeQueue/remux.flow.md` (ST1-ST13) ← **Signal 1 FIRES** (parallel flow for one conceptual operation)
- `Features/WorkBucket/work-bucket.flow.md` (new, this directive)

### Mode branches found

- `ProcessTranscodeQueueService.ProcessJob:351` — `if Job.IsRemux: ProcessRemuxJob` (orchestration branch — Signal 2)
- `RemuxJobProcessor.HandleRemuxResult` vs `TranscodeJobProcessor.HandleTranscodeResult` — separate result-handling functions (orchestration branch — Signal 2)

### Shared output columns sparsely populated

- `TranscodeAttempts.AudioPolicyResolved`: populated 0/36000 across all modes (Signal 3 — universal miss; column added 2026-06-25, never wired)
- `TranscodeAttempts.AudioTracksEmittedJson`: populated 0/36000 across all modes (Signal 3 — same root cause)

### Out of Scope items

- `EffectiveProfileResolver` behavior preserved AND internal duplication collapsed in this directive (category (a)).
- Worker-processor unification (TranscodeJobProcessor + RemuxJobProcessor + SubtitleFixJobProcessor) — category (b), explicit. Tracked in sibling directive `transcode-worker-unification`, sequenced AFTER this one. **This directive's UI ships on top of the current divergent pipeline; the audio-policy attestation gap (Signal 3) is therefore expected.**
```

The audit takes 15-30 minutes if no signals fire, 1-2 hours if multiple do (because you have to scope or carve-out each one). Cheaper than discovering the divergence via operator probe after declaring DELIVERING.

## What this rule is NOT

- **Not a hook-enforceable check.** The audit is a judgment-call deliverable. The phase gate enforces that you READ the rule file at NEEDS_STANDARDS_REVIEW; the rule's content tells you what to look for. The hook cannot verify you actually traced the call graph honestly.

- **Not a substitute for VERIFYING.** The audit is forward-looking (what could go wrong); verification is backward-looking (did the criteria pass). Both are required.

- **Not a license to expand every directive.** If Signal 1 fires and the right call is "open a sibling directive," do that. The rule forces NAMING the debt, not absorbing it.

## Why this lives in `rules/` not `rules-details/`

The audit must be discoverable at NEEDS_STANDARDS_REVIEW (the phase gate reads every `rules/*.md`). The short invariant in `rules/call-graph-audit.md` is what gets loaded; this file is the how-to for when the operator (or assistant) wants the full checklist.
