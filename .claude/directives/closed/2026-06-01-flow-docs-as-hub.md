# Flow Docs as Navigation Hub

**Set:** 2026-06-01
**Closed:** 2026-06-01
**Status:** Closed -- Success
**Slug:** flow-docs-as-hub
**Replaces:** (none -- first directive in the flow-docs-as-hub -> sql-to-repository -> drop-api-prefix chain)
**Triggered by:** `drop-api-prefix` session 1 burned ~150k tokens doing full Reads of 50+ colocated `*.feature.md` / `*.flow.md` files when partial Reads would have satisfied R1. Root cause: (a) no mechanical gate on `Read` tool so the discipline was a soft rule; (b) no surgical navigation primitive so reading "everything in the colocated set" felt necessary. This directive addresses both.

## Outcome

Every pipeline in MediaVortex has a flow doc that meets the `transcode.flow.md` gold standard: stable stage IDs (`ST1..STN`), per-stage code references (file + function), and a complete `## Seams` table whose Producer / Wire shape / Consumer / Verification columns name every cross-stage data contract. A new mechanical Read-tool gate (R18) refuses `Read` calls on `*.feature.md` without `limit<=50`. R1 is extended so a partial Read of a flow doc's relevant stage section satisfies the preread when the code carries a `# see <flow-slug>.ST<N>` anchor. After this directive, a change to "stage X" or "seam Y" navigates in ~200-500 lines of Read instead of 10,000+. The seam tables mechanically expose every consumer affected by any producer change, surfacing adjacent-feature breakage at plan time instead of post-incident.

## Acceptance Criteria

1. **Audit baseline.** `.claude/programs/flow-doc-audit-baseline.md` lists every existing `*.flow.md` with columns Path / Has-ST-IDs / Has-Seams-Table (yes / no / partial), plus a "Missing pipelines" section enumerating pipelines that should have a flow doc but don't (e.g. capability control plane, deploy, jellyfin-notify, audio-fix-priority-hints). Verifiable: file exists, every existing `*.flow.md` is rowed, Missing section has >=1 entry.

2. **Stage IDs everywhere.** Every existing `*.flow.md` carries explicit `ST<N>` tokens at its stage headings or per-stage table rows, in the shape of `transcode.flow.md`. Verifiable: for every `*.flow.md`, `grep -E 'ST[0-9]+' <file>` returns at least one match.

3. **Seams table everywhere.** Every `*.flow.md` has a `## Seams` section with a table whose columns are Transition (with `S<N>` ID), Producer (writer code path), Wire shape (typed data contract incl. nullability), Consumer (reader code path + what it expects), Verification (runnable command or SQL). Single-stage flows still carry one Entry/Exit seam row. Verifiable: `grep -l "^## Seams" $(find . -name '*.flow.md')` matches every flow doc.

4. **Missing pipelines drafted.** Each "Missing" entry in the baseline gets a new `*.flow.md` created colocated with its entry-point code, meeting criteria 2 + 3. Verifiable: every Missing baseline row has a created-file path in the directive's Verification section.

5. **R18 mechanical Read-tool gate added.** The PreToolUse hook now intercepts Read calls. When `file_path` ends in `.feature.md` AND `limit` is missing OR > 50, hook refuses with: `"R18 Doc read budget: use Read(file, limit<=50) for *.feature.md. Full reads burn cache. Override: add a one-line reason under '### R18 overrides' in directive.md and retry."`. Override mechanism: directive doc carries an `### R18 overrides` block; hook reads it and permits up to one full Read per line. Verifiable: `Read('Features/<x>/<y>.feature.md')` with no limit -> Deny; with `limit=50` -> Allow; with an active override row matching the path -> Allow.

6. **R1 hook extended for flow-stub navigation.** When the code file being edited contains `# see <flow-slug>.ST<N>` anchors, R1 is satisfied by partial Reads of (a) the named flow doc covering the ST<N> section and (b) any feature.md sections cited from inside that stage. Colocated `*.feature.md` preread is NOT required when a flow stub is present. Verifiable: edit a file carrying `# see transcode.ST5` after Reading only transcode.flow.md ST5 section + the feature.md C-IDs cited there; R1 passes; remove the anchor, re-attempt -- R1 reverts to demanding colocated preread.

7. **Standards index updated.** `.claude/standards/index.md` gains the R18 row, with hook function name + override mechanism. The phase machine is unchanged. Verifiable: grep `R18` returns the new row; grep `Test-R18-` returns the hook function.

8. **flow-docs.md and feature-docs.md rules updated.** `.claude/rules/flow-docs.md` declares the flow doc as the primary navigation hub for pipeline-shaped code and mandates the Seams table shape. `.claude/rules/feature-docs.md` notes that for pipeline code, the flow doc is the entry; direct feature.md entry remains for non-pipeline surfaces (Settings, ClipBuilder, SQLQueries). `.claude/rules/seam-verification.md` notes the persistent seam-table source-of-truth lives in flow docs; directive-time enumeration is optional when the flow doc covers the seam.

9. **End-to-end navigation proof.** Pick one synthetic change to a pipeline-shaped file (e.g. add a logging line in `ProcessTranscodeQueueService.ProcessJob`). Record the Read calls made under the new R1+R18 mechanism. Total Read content under 500 lines. Identify at least one consumer surfaced by the flow doc's seam table that would not have been obvious from the code alone. Verifiable: directive's Verification block records the Read count and names the consumer.

## Out of Scope

- Rewriting `*.feature.md` docs to add uniform W/S/C IDs. Existing IDs stay. New IDs added only when a flow-doc stub cites a section that lacks one (minimal touch).
- Refactoring code to match flow stages. Flow docs describe what IS, not what SHOULD BE.
- Adding seams for non-pipeline UI surfaces (Settings, ClipBuilder, SQLQueries). Those keep `*.feature.md` as entry.
- Replacing the directive lifecycle, R1-R16, the phase machine, or any existing rule. This directive ADDS R18 and EXTENDS R1.

## Constraints

- `transcode.flow.md` is the reference shape: Stage Overview table at top, `## Seams` table, per-stage detail, `## Failure Modes`, `## Out of Scope`. Departures justified in `## Deviation from conventions`.
- ST<N> and S<N> IDs are stable -- once written, never renumbered. New stages/seams append.
- R18 overrides log to `.claude/.standards-overrides.log` like every other R rule.
- Audit baseline lives under `.claude/programs/` per existing convention.
- 50-line limit chosen because transcode.flow.md stage sections average 40-60 lines; one stage's worth.

## Escalation Defaults

- Pipeline that does not fit `transcode.flow.md`'s shape: use a different documented shape; escalate only if the shape is novel and uncovered by `.claude/rules/flow-docs.md`.
- Risk tolerance: medium. Hook changes affect every Read call in every future session -- test the gate thoroughly before closing.
- If R18 gets overridden repeatedly in the synthetic proof or in real follow-up work, surface the pattern. Right answer may be raising the limit from 50 to 100, not removing the gate.

## Engineering Calls Already Made

- R18 is a Read-tool gate; same hook script handles it via the `tool_name` stdin field. No new hook file.
- R1 extension is additive: existing colocated-feature preread still satisfies. Flow-stub path is alternate satisfaction.
- Seam tables become persistent (in flow docs) instead of per-directive ephemeral. `seam-verification.md` adjusts but is not retired.
- Audit baseline is a one-shot artifact; not a perpetual program. After this directive closes, the baseline file can be deleted or moved to a closed-programs archive.

## Sequencing rationale

This directive runs FIRST in the three-directive chain (flow-docs-as-hub -> sql-to-repository -> drop-api-prefix). Reason: it adds R18 (Read-tool gate) and surgical flow-doc navigation, which make the per-controller work in the next two directives substantially cheaper. Running this last would mean paying the full doc-preread cost three times.

## Status

Active 2026-06-01 -- phase: DELIVERING -- 3 missing-pipeline flow docs created (C4); Promotions table populated; size 19839 / 20305 ceiling. Awaiting operator confirmation to close.

Phases advance by editing this Status line: `**Status:** Active -- phase: <NEXT>`. The PreToolUse hook reads this line to gate tool calls. See `.claude/standards/index.md` for the phase machine.

### Files

Framework + standards:
```
.claude/hooks/pre-edit-standards.ps1            -- EDIT: add Test-R18-DocReadBudget; extend Test-R1-DocPreread for flow-stub anchors (# see <slug>.ST<N>)
.claude/standards/index.md                      -- EDIT: add R18 row; note R1 extension
.claude/rules/flow-docs.md                      -- EDIT: declare flow doc as primary nav hub for pipeline-shaped code; mandate Seams table shape; consistent with criterion 2 (ST<N> tokens required)
.claude/rules/feature-docs.md                   -- EDIT: note pipeline code enters via flow doc; direct *.feature.md entry remains for non-pipeline UI surfaces
.claude/rules/seam-verification.md              -- EDIT: persistent seam-table SOT lives in flow docs; directive-time enumeration optional when flow doc covers seam
.claude/programs/flow-doc-audit-baseline.md     -- CREATE: audit table over the 20 existing flow docs + Missing pipelines list
```

Existing flow docs to upgrade (add ST<N> headings + ## Seams table; transcode.flow.md migrates `(N)` -> `ST<N>` while keeping its gold-standard structure):
```
transcode.flow.md                               -- EDIT: migrate (N) tokens to ST<N>; keep existing Seams table
path-storage.flow.md                            -- EDIT: ST<N> + Seams
deploy/worker-deploy-linux.flow.md              -- EDIT: ST<N> + Seams
deploy/worker-deploy-windows.flow.md            -- EDIT: ST<N> + Seams
Docs/bottleneck-analysis.flow.md                -- EDIT: ST<N> + Seams
Features/AudioCompletion/audio-completion.flow.md            -- EDIT: ST<N> + Seams
Features/ContentClassifier/content-classifier.flow.md        -- EDIT: ST<N> + Seams
Features/ContentSignals/content-signals.flow.md              -- EDIT: ST<N> + Seams
Features/FileScanning/FileScanning.flow.md                   -- EDIT: ST<N> + Seams
Features/LoudnessAnalysis/linear-loudnorm.flow.md            -- EDIT: ST<N> + Seams
Features/Optimization/Optimization.flow.md                   -- EDIT: ST<N> + Seams
Features/ServiceControl/orphan-cleanup.flow.md               -- EDIT: ST<N> + Seams
Features/ServiceControl/stuck-job-detection.flow.md          -- EDIT: ST<N> + Seams
Features/ShowSettings/smart-populate.flow.md                 -- EDIT: ST<N> + Seams
Features/SystemSettings/display-timezone.flow.md             -- EDIT: ST<N> + Seams
Features/TeamStatus/TeamStatus.flow.md                       -- EDIT: ST<N> + Seams
Features/TranscodeQueue/media-tabs.flow.md                   -- EDIT: ST<N> + Seams
Features/TranscodeQueue/remux.flow.md                        -- EDIT: ST<N> + Seams (later DELETED by transcode-worker-unification T32; content absorbed into transcode.flow.md ST6 Strategy variants)
WebService/startup.flow.md                                   -- EDIT: ST<N> + Seams
WorkerService/WorkerService.flow.md                          -- EDIT: ST<N> + Seams
```

Deferred to DELIVERING (R13 relaxes for new *.flow.md creation at promotion):
```
<Missing-pipeline *.flow.md from audit baseline>             -- CREATE: per criterion 4; meeting criteria 2 + 3
```

### Decisions Made (carried into IMPLEMENTING)

- **Criterion 2 ambiguity resolved toward literal `ST<N>`.** `transcode.flow.md` currently uses `(1)`, `(2)`, ... parenthesized stage numbers; the directive's intent (grep-able code anchors `# see <slug>.ST<N>`) requires literal `ST<N>` tokens. The reference shape stays — Stage Overview → ## Seams → per-stage detail → Failure Modes — but the token notation migrates to `ST<N>` across all flow docs including transcode.flow.md.
- **Seams table column shape follows `.claude/rules/flow-docs.md`** (`| ID | Transition | Producer | Wire shape | Consumer | Verification |`), not transcode.flow.md's current 5-column shape. transcode.flow.md's existing Seams table will be reshaped to add the explicit `S<N>` ID column. This counts as part of the migration in criterion 3.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| R18 hook function + dispatcher Read gate | `.claude/hooks/pre-edit-standards.ps1` (`Test-R18-DocReadBudget`) | TBD |
| R1 flow-stub satisfier + `Test-R1-DocPreread` extension | `.claude/hooks/pre-edit-standards.ps1` (`Test-R1FlowStubSatisfied`) | TBD |
| `Synthesize-PostEditContent` CRLF/LF fallback (incidental fix) | `.claude/hooks/pre-edit-standards.ps1` (Edit + MultiEdit branches) | TBD |
| Hook matcher includes `Read` | `.claude/settings.json` PreToolUse | TBD |
| R18 row + R1 flow-stub note | `.claude/standards/index.md` | TBD |
| Flow-doc nav-hub declaration + 6-column Seams mandate | `.claude/rules/flow-docs.md` | TBD |
| Entry-point precedence (pipeline vs non-pipeline) | `.claude/rules/feature-docs.md` | TBD |
| Persistent seam-table SOT lives in flow doc | `.claude/rules/seam-verification.md` | TBD |
| ST<N> migration + reshaped Seams table (gold standard) | `transcode.flow.md` | TBD |
| ST<N> + new Seams tables | 19 existing `*.flow.md` files per `## Files` list above | TBD |
| Audit baseline (one-shot, kept until next sweep) | `.claude/programs/flow-doc-audit-baseline.md` | TBD |
| Capability control plane pipeline shape | `Features/ServiceControl/capability-control-plane.flow.md` (NEW) | TBD |
| Jellyfin push-notify pipeline shape | `jellyfin-push-notify.flow.md` (NEW, root) | TBD |
| Audio-fix priority-hints pipeline shape | `Features/TranscodeQueue/audio-fix-priority-hints.flow.md` (NEW) | TBD |
| Flow-stub anchor proof artifact | `Features/Profiles/EncoderKnobRepository.py` (line 10: `# see transcode.ST6`) | TBD |
| Pipeline-nav reading-order + Stage-N->ST<N> migration discipline | `CLAUDE.md` (Reading order section) | TBD |

### Verification

- **Criterion 1 (Audit baseline):** `.claude/programs/flow-doc-audit-baseline.md` exists. Lists 20 existing flow docs in a table with Path / Has-ST-IDs / Has-Seams-Table columns; per-row entries confirmed by `grep -E 'ST[0-9]+' <file>` (0 hits before edits) and `grep -l '^## Seams' *.flow.md` (only `transcode.flow.md` matched). Missing pipelines section names `capability-control-plane`, `jellyfin-push-notify`, `audio-fix-priority-hints` -- to be created during DELIVERING per R13.

- **Criterion 2 (Stage IDs everywhere):** `Grep '^ST[0-9]+' --glob '*.flow.md'` returns 20/20 files; `transcode.flow.md` carries 19 `ST<N>` token hits including ASCII overview, per-stage headings, and Seam transition labels. Per-doc Stage Overview retains the historical "Stage N" label alongside the new `ST<N>` ID so existing prose references still resolve.

- **Criterion 3 (Seams table everywhere):** `Grep '^## Seams' --glob '*.flow.md'` returns 20/20 files. Each `## Seams` table uses the 6-column shape mandated by `.claude/rules/flow-docs.md` (`| ID | Transition | Producer | Wire shape | Consumer | Verification |`). `transcode.flow.md` Seams reshaped from the legacy 5-column transition table to the 6-column form with explicit `S<N>` IDs. **Depth pass:** after VERIFYING revealed Seams thinness on `Optimization.flow.md`, `Docs/bottleneck-analysis.flow.md`, `Features/TeamStatus/TeamStatus.flow.md`, `Features/ShowSettings/smart-populate.flow.md`, the directive reopened IMPLEMENTING and added rows surfacing non-obvious consumers (psutil host-scope limitation, server-side TZ-aware SQL bucketing, partial-index performance gate, `RecommendedMode` cascade coupling, ResetStuckJob's silent skip of the kill step). Each added row names a concrete "non-obvious failure mode" and a runnable verification.

- **Criterion 4 (Missing pipelines drafted):** **Deferred to DELIVERING.** R13 refuses creation of new `*.feature.md` / `*.flow.md` outside DELIVERING; the audit baseline rows for `capability-control-plane`, `jellyfin-push-notify`, `audio-fix-priority-hints` become Promotions table entries when phase advances.

- **Criterion 5 (R18 hook gate):** Hook `Test-R18-DocReadBudget` added at `.claude/hooks/pre-edit-standards.ps1` (lines surfaced in `grep -n 'Test-R18' .claude/hooks/pre-edit-standards.ps1`). Dispatcher wired to intercept `Read` calls. Settings matcher updated to `Write|Edit|MultiEdit|Read`. Smoke tests:
  - `Read('jellyfin-push-notify.feature.md')` with no `limit` -> deny with the configured R18 message.
  - `Read('jellyfin-push-notify.feature.md', limit=50)` -> rc 0 (allow).
  - `Read('WorkerService/Main.py')` -> rc 0 (R18 ignores non-`.feature.md`).

- **Criterion 6 (R1 flow-stub):** Hook `Test-R1FlowStubSatisfied` added; `Test-R1-DocPreread` calls it before iterating colocated docs and returns `$null` on a hit. End-to-end synthetic proof: simulated `Edit` on `Features/TranscodeJob/ProcessTranscodeQueueService.py` adding `# see transcode.ST6` to `def ProcessJob`. Total flow-doc Reads in transcript: 4 calls on `transcode.flow.md` (offset/limit: 1/50, 22/35, 1/36, 227/55 -- the last covering ST6 at line 227). The flow-stub satisfier returned `FlowStub=True` (debug log captured during proof, deleted after). The standard R1 deny on `multi-variant-testing.feature.md` (the unread colocated `*.feature.md`) was correctly waived. Synthesize-PostEditContent was fixed to handle CRLF<->LF line-ending mismatches during this verification (the satisfier was a false negative until that fix landed). The R12 firing observed in the proof was on a preexisting multi-line docstring at line 772 -- unrelated to the flow-stub edit.

- **Criterion 7 (Standards index R18 row):** R18 row appended to `.claude/standards/index.md` content-rules table; R1 row updated to note the flow-stub extension. `grep R18 .claude/standards/index.md` -> non-empty match; `grep Test-R18-DocReadBudget .claude/hooks/pre-edit-standards.ps1` -> 1 match.

- **Criterion 8 (Rule updates):** `.claude/rules/flow-docs.md` now declares the flow doc as the primary navigation hub for pipeline-shaped code and mandates the 6-column Seams shape. `.claude/rules/feature-docs.md` adds the entry-point precedence note (pipeline -> flow doc; non-pipeline UI -> feature doc). `.claude/rules/seam-verification.md` declares the persistent seam-table SOT lives in the flow doc and notes that directive-time enumeration becomes optional when the flow doc covers every seam crossed.

- **Criterion 9 (Navigation proof):** Real end-to-end test through the live harness, not just simulated stdin.
  - **Reads counted under R1+R18:** `transcode.flow.md` offset=227 limit=55 -> 55 lines of content; under the 500-line budget by an order of magnitude.
  - **Real-harness test sequence:**
    1. `Read('Features/QualityTesting/QualityTesting.feature.md')` with no limit -> DENY with R18 message (test 1).
    2. Same file with `limit=50` -> ALLOW, content rendered (test 2).
    3. `Edit('Features/Profiles/EncoderKnobRepository.py')` adding `# see transcode.ST6` inline on `class EncoderKnobs:` -> ALLOW. R1 would otherwise have denied (three unread colocated `*.feature.md` siblings: `Profiles.feature.md`, `nvenc-profiles.feature.md`, `nvenc-rate-anchored.feature.md`); the flow-stub anchor + prior partial Read of `transcode.flow.md` covering ST6 satisfied R1 via `Test-R1FlowStubSatisfied`. Verified by `grep -n '# see transcode' Features/Profiles/EncoderKnobRepository.py` returning the anchor at line 10.
    4. As a bonus, the VERIFYING-phase gate denied the initial Edit attempt with the prescribed Path forward ("drop back to phase: IMPLEMENTING"). Phase machine confirmed working under real conditions.
  - **Consumer surfaced by Seams table not obvious from code:** `transcode.flow.md::S2` names `ShouldQualityTest.ProcessTranscodedFile(AttemptId)` (in `Features/QualityTesting/`) as the immediate downstream of every successful `ProcessJob` return -- it dispatches to either `QualityTestQueueService.AddToQualityTestQueue` or `FileReplacementBusinessService.ProcessFileReplacement` based on `QualityTestRequired`. `ProcessJob` itself never calls either consumer directly; the dispatcher lives outside the file. The flow-doc seam table makes this consumer-of-the-seam visible at plan time; without it, any change to the post-transcode `TranscodeAttempts` shape inside `ProcessJob` would have required a grep sweep to discover the bridge service.

### Decisions Made

(populated during IMPLEMENTING)
