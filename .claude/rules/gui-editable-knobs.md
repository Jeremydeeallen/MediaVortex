# GUI-Editable Knobs

Every operator-facing DB knob is tunable via `/settings` or `/Admin/*` GUI. No SQL edits. No code changes. Adding a new operator-facing table or column ships with a matching GUI handler in the same directive.

## The rule

If a value can be tuned by the operator to change system behavior, it lives in a DB column AND has a GUI handler that reads + writes it. Persistent operator control lives in one place: the GUI. Discovery burden lives in one place: `/settings` + `/Admin/*`.

Applies to:
- Per-vertical thresholds (`VideoComplianceThresholds`, `AudioComplianceRules`, `ContainerComplianceRules`, ...)
- Gate configs (`PostTranscodeGateConfig`, `SystemSettings.*Enabled` toggles, ...)
- Ladder cells (`ProfileThresholds.TargetKbps` / `IcqQ`, ...)
- Policy multipliers, retry caps, timeouts, thresholds -- anything an operator would want to tune post-deploy

Does NOT apply to:
- Deploy-time constants (paths, ports, credentials -- these live in env vars / config files)
- Framework internals (index names, generated columns, migration filenames)
- Runtime state (queue rows, attempt rows, ActiveJobs -- data, not knobs)

## Enforcement

Judgment gate per `.claude/standards/index.md` "What is NOT gated". Reviewer flags at NEEDS_STANDARDS_REVIEW / VERIFYING:

- Any new column added to `SystemSettings` without a corresponding `/settings` handler.
- Any new operator-facing table without a `/settings` or `/Admin/*` handler.
- Any directive that ships a knob "editable via SQL for now" -- not acceptable; the directive owns the GUI too.

No contract test enforces this -- whitelist enumeration rots faster than code. Reviewer catches it at plan review.

## When this rule applies (PR triggers)

- Adds a new table under `Features/*/Repositories/` or `Scripts/SQLScripts/Add*.py` whose rows the operator will edit.
- Adds a new column to `SystemSettings`, `PostTranscodeGateConfig`, `ProfileThresholds`, `AudioComplianceRules`, `ContainerComplianceRules`, or any per-vertical singleton.
- Adds a new `/api/*/Rules` or `/api/*/Config` endpoint whose values the operator tunes.

Ship the GUI in the same directive. Don't defer.

## Related

- `.claude/rules/db-is-authority.md` -- DB is SoT for runtime state; GUI is the tuning surface for that state.
- `.claude/rules/ceo-mode.md` -- one editor per conceptual unit (no parallel UIs).
- Operationalized by `video-compliance-multiplier` directive (2026-07-26) after Q2 domain answer.
