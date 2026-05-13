---
description: "Feature success -- full completion pipeline. Runs finalize, QA, UX review (if surface declared), dead code cleanup, doc updates, and commit."
agent: "agent"
---
Feature success -- run the full completion pipeline in order. Do not skip steps.

1. Run the finalize checklist: turn off debug, update ### Progress with commit hashes, mark feature COMPLETE.

2. QA: check the feature's success criteria against the actual code and system state. Record any failures as [BUG] criteria before closing.

3. UX review (conditional): if the feature doc has a ## Surface section declaring user-facing touchpoints (CLI, UI, API humans call, error messages, docs), review the feature from the end user's perspective. Skip if no ## Surface section or it reads "none" or "internal".

4. Dead code cleanup: remove any code left over from failed approaches explored during this feature.

5. Update flow docs: ensure all *.flow.md files that cover the affected pipeline match the implemented architecture. If a flow step changed, update the table row.

6. Update feature doc: ensure ## Files section is current, verify ### Progress has an entry for every decision point.

7. Run a simplification pass on all changed files -- look for unnecessary complexity, dead code, or redundant logic.

8. Commit with a descriptive message that explains the "why", not just the "what".
