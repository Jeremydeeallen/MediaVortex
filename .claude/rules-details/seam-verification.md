# Seam Verification -- Details

> Invariant: `.claude/rules/seam-verification.md`.

## Why this rule exists (UseNvidiaHardware case study)

The `UseNvidiaHardware` bug (BUG-0023, 2026-05-31) is the canonical example. A JS-side ternary `? 1 : 0` had been silently coercing a JS boolean to a SQL integer for years, masking a schema mismatch (the `Profiles.UseNvidiaHardware` column is `bigint`, not `BOOLEAN`). When the `unify-profile-editor` directive deleted the legacy modal, the ternary went with it; the new modal sent raw booleans; PostgreSQL rejected. The bug existed because no one had enumerated the JS<->SQL wire-format seam and noticed the ternary was load-bearing -- not orphan code.

A seam-verification pass would have caught it before delivery: the UI seam's CRUD round-trip on a `bool`-typed field would have hit the type mismatch immediately. Instead it shipped, the operator hit the 500 error, and the bug was filed retroactively.

## Expanded seam type reference

- **Function-call seam**: caller <-> callee. Wire shape = function signature + return type.
- **Wire-format seam**: serialization boundary (JSON, SQL params, query strings, file format). Wire shape = both ends' type expectations. The `UseNvidiaHardware` bug lived here -- a JS bool became a PostgreSQL bigint via an undocumented JS ternary.
- **State-store seam**: row / file written by one component, read by another. Wire shape = column types + nullability + semantic meaning.
- **UI seam**: operator action -> form -> API -> DB. Wire shape = form field types <-> JSON <-> API allowlist <-> DB column type.
- **Process seam**: producer writes / consumer claims (queue rows, notify endpoints, IPC). Wire shape = row schema + state machine.

## Honest caveats

- Seam enumeration adds time before IMPLEMENTING. That's the trade. The alternative is re-discovering silent bugs after a directive closes.
- The hook cannot mechanize "did you enumerate every seam?" -- this is judgment-call discipline. Operator review at directive close surfaces gaps.
- The discipline applies to both CEO mode and task-delegation mode. It is about how you make any change, not about how directives are structured.
