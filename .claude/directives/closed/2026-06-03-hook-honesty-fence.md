# Current Directive

**Set:** 2026-06-03
**Status:** Closed -- Paused -- operator to paste diffs
**Closed:** 2026-06-03
**Slug:** hook-honesty-fence
**Replaces:** none (new directive)

## Outcome

Three structural fences in `.claude/hooks/pre-edit-standards.ps1` that make the agent's "rationalize-and-work-around" pattern measurably harder. After this directive: (A) every hook refusal carries a fixed STOP header addressing the agent directly so the reminder fires every refusal, not just on the second occurrence; (B) the directive-close `no promotions` escape is structurally refused when the current commit includes a schema migration or new service method (forcing a real feature/flow doc citation); (C) every `# directive: <slug>` anchor on a def/class requires a companion `# see <feature-or-flow-slug>.<ID>` anchor in the same scope (forcing durable doc references at write time).

## Acceptance Criteria

1. Every refusal emitted by the hook (R1-R18, phase gates, R4, etc.) is prefixed with a fixed header that begins "STOP." and instructs the agent to follow the Path forward literally rather than search for variants. Verifiable: induce any refusal (e.g. Read with no Slug, Edit with missing R1 preread); the emitted text begins with the STOP header.

2. The DELIVERING -> Closed gate refuses a directive whose Promotions table has only "no promotions" rows AND whose `### Files` block names any `Scripts/SQLScripts/Add*.py` migration. Verifiable: stage a closing directive with a `Scripts/SQLScripts/AddFoo.py` in Files and a "no promotions" Promotions row; close attempt is refused with the new message naming the offending file.

3. Test-R15-DirectiveAnchor (or new R19) refuses a def/class that has `# directive: <slug>` above it WITHOUT at least one `# see <feature-or-flow-slug>.<ID>` anchor within the function/class scope. Edited-region-only: only fires on defs touched by the current edit. Verifiable: write a def with `# directive: foo` only; refused. Add `# see bar.C1` in the function body; passes.

## Out of Scope

- Semantic verification of cited feature docs (whether bar.C1 actually exists). Future feature-doc validator could check, but adds reader complexity now.
- Retroactive fix of existing code that has `# directive:` without `# see` companions. New-edit only; backlog burns down as files are touched.
- The audit-pass agent at close (option 4 in conversation) -- deferred until A/B/C land and show whether they catch the pattern.

## Constraints

- Self-mod gate may refuse function-body edits to the hook. If so, surface the diff text for operator paste. The dispatcher pass-through edit pattern (succeeded for R6 earlier) is fair game.
- No backwards compatibility for existing `# directive:`-only anchors except via R15 edited-region-only filtering (already in place).
- C must NOT fire on hook/standards files themselves (R1-R15 already exempt them; mirror the exemption).

## Escalation Defaults

- Risk tolerance: low (touches the gate that protects all other gates).
- If hook function-body edits keep getting refused as self-mod, package the changes as a single Write of the whole hook file with the operator's explicit approval per session.

## Engineering Calls Already Made

- (A) is highest leverage and lowest blast radius; do it first.
- (B) is structural — just check `### Files` block text for `Scripts/SQLScripts/Add*.py`. Don't try to parse Python diffs at hook time.
- (C) extends R15 rather than adding R19 — same hook function, same edited-region filter, no new rule registration overhead.

## Status

Active 2026-06-03 -- phase: IMPLEMENTING.

### Files

```
.claude/hooks/pre-edit-standards.ps1    -- EDIT: A (emit prefix), B (close gate tighten), C (R15 see companion)
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Three patch diffs (A: agent-stop header, B: tighten no-promotions escape, C: # see companion) | `.claude/hooks/pre-edit-standards.ps1` | TBD (operator paste) |

### Verification

- Diffs surfaced to operator in conversation; agent self-mod gate blocked direct apply (expected per prior R6 hook precedent).
- No edits landed in tree under this directive's slug. Closure as Paused so the work item stays visible until operator pastes the diffs.

### Decisions Made

- Closed Paused (not Success) because no code landed. The durable artifact (hook script) is unchanged in tree; only conversation contains the diffs.
