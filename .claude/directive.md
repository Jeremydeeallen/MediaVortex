# Current Directive

**Set:** YYYY-MM-DD
**Status:** (no active directive -- task-delegation mode)
**Slug:** <previous-slug>
**Replaces:** `directives/closed/<previous-slug>.md` (closed Success | Partial | Abandoned)

## Outcome

One paragraph describing the operator-observable end state. What is true after this directive is done that wasn't true before.

## Acceptance Criteria

1. ...
2. ...

(Each criterion: observable behavior, verifiable in SQL or by a single command. Rename-test, outsider-test, rewrite-test, negation-test, stability-test per `.claude/rules/feature-criteria.md`.)

## Out of Scope

- ...

## Constraints

- ...

## Escalation Defaults

- Tradeoff between A and B -> B
- Risk tolerance: low | medium | high

## Engineering Calls Already Made

- ...

## Status

Phases advance by editing the `**Status:**` header line at the top of this file: `**Status:** Active -- phase: <NEXT>`. The PreToolUse hook reads ONLY that header line (NOT this section). See `.claude/standards/index.md` for the phase machine.

### Files

```
path/to/file1.py    -- EDIT: one-line reason
path/to/file2.py    -- CREATE: one-line reason
```

### Promotions

Required when phase advances to DELIVERING. The hook refuses Status `Active -- phase: DELIVERING` -> `Closed` if this section is empty.

Each row promotes durable content out of this directive into its permanent home (feature/flow doc). On close, the archive keeps only the pointer table -- the design content lives in the target file.

| Source artifact | Target file | Commit |
|---|---|---|
| `<what content / decision>` | `<path/to/target.feature.md or .flow.md>` | `<sha or "TBD until close">` |

If a row's content is "new vertical entirely" or "new pipeline entirely," the Target is a NEW `*.feature.md` / `*.flow.md` -- R13 allows creation during DELIVERING for exactly this case (`.claude/rules/doc-layering.md`).

If a directive has no durable content to promote (e.g. pure bugfix, no contract change), list one row: `no promotions | n/a | <reason>`. The hook only checks the section is non-empty.

### Verification

Required when phase advances to VERIFYING. One entry per acceptance criterion. Concrete evidence (command output, SQL result, file path) -- not "tested it works."

- **Criterion 1:** `<evidence>`
- **Criterion 2:** `<evidence>`

### Decisions Made

Engineering calls made under ambiguity during execution. These live with the directive (not with features/flows) because they describe THIS directive's reasoning, not the vertical's contract.

- `<decision + one-line rationale>`

---

## Closure (thin-pointer archive shape)

When this directive is ready to close:

1. **Confirm Promotions table is complete.** Every piece of durable content from this directive has a row pointing at its permanent home. The hook will refuse the close otherwise.
2. **Confirm directive did not grow during DELIVERING.** The hook recorded a size snapshot at IMPLEMENTING -> DELIVERING transition; the close is refused if the directive grew by more than the configured tolerance (default 10%). Growth during DELIVERING means content was DUPLICATED into the directive rather than PROMOTED out -- fix by moving the content to its target file and shrinking the directive.
3. **Update Promotions table with commit SHAs** (the commits where each promotion landed).
4. **Change `Status: Active -- phase: DELIVERING` -> `Status: Closed -- Success | Partial | Abandoned`.** Add a `**Closed:** YYYY-MM-DD` line under Set.
5. **Archive:**

   ```powershell
   git mv .claude/directive.md .claude/directives/closed/YYYY-MM-DD-<slug>.md
   Copy-Item .claude/directives/_template.md .claude/directive.md
   ```

   The renamed file becomes the archived record; `git log --follow` traces it.

The archived directive holds these sections only:

| Section | Content |
|---|---|
| Outcome | (restated; what was true at the start of the ask) |
| Acceptance Criteria | (restated; the contract that gated success) |
| Promotions | (the pointer table -- source artifacts and where they live now) |
| Verification | (per-criterion evidence) |
| Decisions Made | (engineering calls made under ambiguity) |

The archive does NOT hold:

- Design content that lives in a feature/flow doc (read the target file instead -- this is the whole point of promotion)
- In-flight planning notes or transient operational state (these served their purpose during execution; they don't belong in the historical record)
- Re-derivations of standards or rules (those live in `.claude/rules/`)

If a future reader wants to know what a vertical does, they read its feature doc. If they want to know why a directive made the choices it made, they read the archived directive's Decisions Made and Verification sections. If they want to know what was promoted, they follow the pointers in the Promotions table.

This shape is governed by `.claude/rules/doc-layering.md` (the three-tier model) and `.claude/rules/ceo-mode.md` (the directive lifecycle).
