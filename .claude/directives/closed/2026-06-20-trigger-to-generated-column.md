# Generated-Column Substitution for Trigger

**Slug:** trigger-to-generated-column
**Set:** 2026-06-20
**Closed:** 2026-06-20
**Status:** Closed -- Success

## Outcome

`ARCHITECTURE.md` + paused directive 7 + closed directive references updated to use `GENERATED ALWAYS AS ... STORED` column instead of trigger for `WorkBucket` derivation. Doc-only change; no production code or DB modified. Future cutover (directive 7) will install the generated column, not a trigger.

## Why

A trigger is the wrong tool for a pure-same-row derivation. A `GENERATED ALWAYS AS (CASE...) STORED` column is structurally simpler: the expression IS the column definition (visible in `\d MediaFiles`), no separate function to maintain, Postgres refuses any INSERT/UPDATE that tries to set the column, fully indexable, no race conditions possible. The trigger choice was reflexive at the time the architecture was drafted; correcting now before cutover lands.

## Acceptance Criteria

C1. `ARCHITECTURE.md` -- every "SQL trigger" / "trigger" reference about `WorkBucket` derivation replaced with "generated column" / "GENERATED ALWAYS AS ... STORED". 12 lines flagged for edit.
C2. `.claude/directives/paused/2026-06-20-compliance-cutover-and-rip.md` -- "Install the SQL trigger" -> "Install the generated column"; C1 reworded; Files block `InstallWorkBucketTrigger.py` -> `ConvertWorkBucketToGenerated.py`.
C3. No production code change. No DB change. No new migration script.

## Status

### Verification

- **C1**: `grep -n 'trigger\|Trigger' ARCHITECTURE.md` post-edit returns no `WorkBucket`-derivation references; only references to existing (non-WorkBucket) triggers if any.
- **C2**: paused directive 7 file updated; `grep -n 'trigger' <file>` post-edit returns only contextual mentions (e.g. "no longer using a trigger").
- **C3**: `git diff --stat` shows only ARCHITECTURE.md + paused directive 7 file + this directive doc modified.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| trigger -> generated column terminology | `ARCHITECTURE.md` | next commit |
| trigger -> generated column terminology | `.claude/directives/paused/2026-06-20-compliance-cutover-and-rip.md` | next commit |

### Decisions Made

- Keep the closed directive files (4, 5, 6) referencing "trigger" as-is. They're historical records; the architectural correction lives in ARCHITECTURE.md (the current target spec). Editing closed history would violate the archive contract.
