---
description: "Check conformance of the repo's documentation structure against established conventions. Reports violations in feature docs, flow docs, and cross-references."
agent: "agent"
---
# Conformance Check

Verify this repo's documentation structure against the established conventions.

## Checks to run:

### Feature doc structure
Find every *.feature.md. Verify each has:
- `## Success Criteria` with numbered items
- `## Status` with a valid value (NOT STARTED / IN PROGRESS / COMPLETE / PARKED)
- `## Files` or `## Scope` section

### Flow doc structure
Find every *.flow.md. Verify each has:
- `## Entry Point` section
- A step table or stage overview
- Failure modes section

### Cross-references
- Feature docs that reference flow docs: verify the flow docs exist
- Flow docs that reference code files: verify the files exist

### Style checks (advisory)
- Temporal qualifiers ("currently", "soon") in docs
- Feature docs with criteria that fail the five litmus tests

## Report format:
```
Feature Docs:   X found, Y passing, Z with issues
Flow Docs:      X found, Y passing, Z with issues
Cross-refs:     X checked, Y broken
Style:          X advisories

Issues:
  [file:line] description of violation
```
