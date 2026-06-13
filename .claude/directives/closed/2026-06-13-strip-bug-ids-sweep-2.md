# Strip BUG-NNNN refs from pre-existing code (sweep pass 2)

**Set:** 2026-06-13
**Status:** Active -- phase: IMPLEMENTING
**Slug:** strip-bug-ids-sweep-2

## Outcome

`grep -rEn 'BUG-[0-9]+' --include='*.py' --include='*.html' --include='*.js' --exclude-dir=__pycache__ --exclude-dir=venv` returns zero hits across the production tree. Pass 1 (commit `83c1b90`) cleaned my Cluster A/B/C surface; this pass cleans the 19 remaining files.

## Acceptance Criteria

1. Zero `BUG-[0-9]+` hits across `.py` + `.html` + `.js` outside `venv/` / `__pycache__/`.
2. No behavior change; comments/docstrings keep semantic meaning where the WHY is durable (replaced with slug anchors when available, paraphrased otherwise).
3. Assertion messages that mention bug IDs replaced with their operator-actionable description.
4. R12 honored -- no new multi-line `#` comment blocks introduced; collapse to one line.
