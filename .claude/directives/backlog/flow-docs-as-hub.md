# Backlog Directive: Flow Docs as Navigation Hub

**Filed:** 2026-06-01 (by `drop-api-prefix` mid-session post-mortem on doc-preread cost)
**Status:** Backlog -- not yet started
**Slug:** flow-docs-as-hub
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

Backlog -- not yet started. Promote to active by:

1. Copying this file's body into `.claude/directive.md`
2. Updating Status line to `Active YYYY-MM-DD -- phase: NEEDS_STANDARDS_REVIEW`
3. Setting **Filed:** to **Set:**
4. `git rm .claude/directives/backlog/flow-docs-as-hub.md`
