---
description: "Start a new feature. Creates flow doc (if user-facing), feature doc with criteria, and progress checklist. No code until criteria are approved."
agent: "agent"
argument-hint: "<feature-name>"
---
New feature: {{input}}

Follow these steps in order. Do not skip steps or begin implementation before step 12.

1. Read the project's issues tracker (KNOWN-ISSUES.md) for related bugs or prior work on this topic.

2. Decide: does this feature have a user-visible surface (CLI, UI, API humans call, error message, docs page)? If NO, skip to step 5.

3. User-facing path: check for an existing *.flow.md near the relevant entry point. The flow captures what the user expects to see -- it is the contract that feature criteria must be traceable to.

4. User-facing path: if no flow doc exists, or the existing one does not cover this feature, draft or update the flow doc FIRST. Name the entry point, write the step table, and define failure modes before any feature doc work.

5. Check for an existing *.feature.md near the code.

6. Create the feature doc next to the primary code file if none exists. Include: ## What It Does, ## Success Criteria, ## Status, ### Progress, ## Scope, ## Files.

7. Include a ### Progress checklist under ## Status with the planned implementation steps.

8. Write success criteria that make each flow step verifiable (user-facing features) or each rule/invariant testable (internal features). Each criterion must be testable pass/fail from the outside.

9. Validate drafted criteria against the feature-criteria instructions (five litmus tests: Rename, Outsider, Rewrite, Negation, Stability). Flag any criterion that violates a test.

10. Fill doc gaps in the same pass: additional flow docs if the feature spans multiple pipelines.

11. If new issues surface during this process: record them in KNOWN-ISSUES.md. Do NOT expand the scope of this feature.

12. Report the feature doc as ready for review. NO code until criteria are explicitly approved.
