# Call-Graph Audit (DDD+SOLID system-wide)

DDD/SOLID is a system property, not a file property. A vertical that is locally clean while sitting atop a divergent pipeline is NOT clean. Every directive at NEEDS_STANDARDS_REVIEW must audit the WHOLE call graph the feature participates in, not just the layer being edited. Findings either (a) get absorbed into the directive's scope, or (b) get explicitly named as KNOWN ARCHITECTURAL DEBT in the directive's `## Out of Scope` section. Silent inheritance of pipeline-level divergence is refused.

## The five signals (run all five before leaving NEEDS_STANDARDS_REVIEW)

1. **Multiple flow docs for one conceptual operation.** Two `*.flow.md` files describing what should be one pipeline is an architectural smell. Either unify or document the carve-out. Historical example: `transcode.flow.md` + `remux.flow.md` -- the latter was absorbed into `transcode.flow.md ST6 Strategy variants` by the `transcode-worker-unification` directive.

2. **Mode-branching at the orchestration level.** Any `if mode == X` / `if Job.IsRemux` / `if ProcessingMode in (...)` at the orchestration layer is a Template-Method/Strategy violation. Only the strategy hooks (BuildCommand, HandleResult) may differ by mode; the orchestration shape must be identical.

3. **Shared output columns sparsely populated.** Pick the shared output table (e.g. `TranscodeAttempts`). For every column that any mode writes, verify it is populated by EVERY mode that runs through the same pipeline shape. `SELECT count(*) WHERE <col> IS NOT NULL GROUP BY <mode-discriminator>` returning zeroes for some modes = a missing step in that mode's path.

4. **"Out of Scope" clause ambiguity.** The spec's OOS list must explicitly state for each item whether (a) behavior is preserved AND duplication is collapsed in-flight, or (b) duplication is acknowledged debt that survives the directive. Default to (a). "(b) without explicit acknowledgment" = silent debt accretion.

5. **Config-driven call-graph shape.** Feature flags, runtime config, and toggles must drive DATA, never ORCHESTRATION. If turning a flag off REMOVES a node from the call graph (vs short-circuits a path through it), that's a violation. The call graph is a static property of the code; the same functions are called regardless of config -- config only changes which values flow through them and which branches the data takes. Detection: read code with the assumption "this flag is the opposite of its current value" and ask "do different functions get called now?" If yes, the design lets config change the graph shape, which is a SOLID violation (the graph is no longer Open/Closed against runtime state) and a latent-landmine pattern (turning the flag back on activates code that hasn't been exercised in the current config).

## Where to record the audit

`.claude/directive.md` adds a section `## Call-Graph Audit` between `## Acceptance Criteria` and `## Out of Scope`. The section enumerates:

- Every `*.flow.md` the directive's feature touches (and whether any pair describes one conceptual operation).
- Every orchestration-level mode branch found in the call graph.
- Every shared output column with mode-sparse population.
- Every OOS item categorized (a) or (b).

The directive cannot advance NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN until this section is non-empty. Empty section is the operator's signal to ask "did you actually look?"

## Why this rule exists

Recurring failure pattern (work-transcode-unified, 2026-06-28): operator stated "100% clean DDD+SOLID" four times across the directive. The WorkBucket vertical landed locally clean. The pipeline layer below — three divergent JobProcessor classes + `remux.flow.md` as a parallel flow doc + `AudioPolicyResolved` empty across all attempts — survived untouched because the directive's spec scoped to UI only. Operator caught it via 9-media GUI smoke and a question about the 9th file's compliance. The audit above would have surfaced the divergence at spec time, before any code landed.

**Details, full checklist with grep commands, examples from work-transcode-unified:** see `.claude/rules-details/call-graph-audit.md`.
