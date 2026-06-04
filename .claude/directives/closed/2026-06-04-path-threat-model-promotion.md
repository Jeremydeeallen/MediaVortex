# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** path-threat-model-promotion
**Predecessor:** `.claude/directives/closed/2026-06-04-path-security-audit.md` (closed Success)
**Program:** none -- one-off hygiene directive promoting durable content out of a closed directive's archive into its proper feature.md home

## Outcome

The threat model section authored in Phase 3 lives in `Core/Path/path.feature.md` as a durable contract section, not buried in an archived directive. Future sessions reading the contract see the threats Path defends against without grep-spelunking closed directives.

## Why

`.claude/rules/doc-layering.md` says durable content belongs in feature docs. The threat model captures attacker goals, capabilities, and trust boundaries that will remain true for years -- it is durable knowledge by definition. Phase 3 surfaced this gap at directive-close-out (called out in the close-out review). Fix now while the source is fresh; cost is ~5 min.

## Acceptance Criteria

1. **`Core/Path/path.feature.md` contains a `## Threat Model` section** with attacker goals (G1-G6), capabilities (A1-A3 in-scope, named out-of-scope items), trust boundaries, and the goal-to-mitigation mapping table. Placed between `## Principle` and `## Workflows` so narrative context precedes the technical surface.
2. **Section content matches the archived Phase 3 directive** (`.claude/directives/closed/2026-06-04-path-security-audit.md`) verbatim or near-verbatim. No rewording that changes meaning.
3. **R-rule compliance.** PreToolUse hook accepts the edit without `# allow:` overrides.
4. **No regression.** `py -m pytest Tests\Unit\test_path_*.py` -- 141 tests pass.
5. **Directive growth cap respected.** This directive is small by design; closes within 10% of IMPLEMENTING-snapshot size.

## Out of Scope

- Editing `Core/Path/Path.py` (no code change).
- Editing `Tests/Unit/test_path_*.py` (no test change).
- Restructuring other sections of `path.feature.md`.
- Promoting any other Phase 3 content (already done at Phase 3 close).

## Files

```
Core/Path/path.feature.md   -- EDIT: add ## Threat Model section between ## Principle and ## Workflows
```

## Status

Closed 2026-06-04 -- Success.

### Delivery Report

DONE. `## Threat Model` section now lives in `Core/Path/path.feature.md` between `## Principle` and `## Workflows`. Asset, G1-G6 attacker goals, A1-A3 in-scope capabilities + out-of-scope list, trust boundaries, goal-to-mitigation mapping table, residual-risks list all preserved. Mapping table rewritten to reference durable D-decisions (D9, D14) instead of Phase 3 directive-local C-numbers. 141 unit tests still pass. Phase 4 (`path-performance-budget`) ready.

### Progress

- [x] Copy threat-model section from closed Phase 3 directive.
- [x] Insert as new `## Threat Model` section in `path.feature.md` between `## Principle` and `## Workflows`.
- [x] Default-config test regression -- 141 passed.
- [x] Populate `### Verification` + `### Promotions`.

### Files

```
Core/Path/path.feature.md   -- EDIT
```

### Verification

- `py -m pytest Tests\Unit\test_path_*.py` -- 141 passed in 1.13s. No regression.
- `grep -c "^## Threat Model" Core/Path/path.feature.md` -- 1 (section present).
- Section content matches archived Phase 3 directive substantively (mapping table updated to use D-decisions, not directive-local C-numbers; durable-doc-appropriate).

### Promotions

| Source artifact | Target file | Status |
|---|---|---|
| `## Threat Model` section (asset, G1-G6, A1-A3, out-of-scope, trust boundaries, goal-mitigation map, residual risks) | `Core/Path/path.feature.md` (new `## Threat Model` section between Principle and Workflows) | Promoted 2026-06-04 |
