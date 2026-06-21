# Vertical Column Ownership Test

**Slug:** vertical-column-ownership-test
**Set:** 2026-06-21
**Closed:** 2026-06-21
**Status:** Closed -- Success

## Outcome

`Tests/Contract/TestVerticalColumnOwnership.py` enforces the column-ownership invariant: each per-vertical `*Compliant` / `*CompliantReason` column is written ONLY by its owning vertical, and `WorkBucket` / `IsCompliant` are never written by Python (they are GENERATED). Test fails loudly with offending file paths if any code outside the owning vertical writes the column.

The architecture's Gap to Target section is now EMPTY. MediaVortex matches the architecture.

## Acceptance Criteria

C1. `Tests/Contract/TestVerticalColumnOwnership.py` exists. Test passes against the current tree.
C2. The test scans production Python files (not tests, not scripts, not closed directives) for `SET <Column>` patterns and per-column allowlists.
C3. Allowlists encoded in the test:
   - `AudioCompliant`, `AudioCompliantReason` → only `Features/AudioNormalization/`
   - `VideoCompliant`, `VideoCompliantReason` → only `Features/VideoEncoding/`
   - `ContainerCompliant`, `ContainerCompliantReason` → only `Features/ContainerFormat/`
   - `WorkBucket`, `IsCompliant` → NO Python writes (GENERATED columns)
C4. Violations produce a clear failure message naming file + line + offending pattern.
C5. ARCHITECTURE.md Gap "Closing work that doesn't fit elsewhere" row for the test REMOVED.
C6. Gap section reduced to remaining future-IDEAS items only (per-share-root audio policy, audio dual-track speech-enrichment).

## Status

### Verification

- **C1**: `Tests/Contract/TestVerticalColumnOwnership.py` exists; `py -m pytest Tests/Contract/TestVerticalColumnOwnership.py` returns `2 passed in 0.76s`.
- **C2**: Test scans `Features/`, `Repositories/`, `Services/`, `WebService/`, `WorkerService/`, `Core/`; excludes `venv/`, `__pycache__`, `.claude/`, `Tests/`, `Scripts/`, `Templates/`.
- **C3**: Allowlists in `_OWNERSHIP` dict + `_GENERATED_NEVER_WRITTEN` tuple match the spec.
- **C4**: Test assertion message format: `"<file>:<line>  writes <Column>  (owner: <OwnerDir>)  >>  <snippet>"`. Empty list = pass; populated list = fail with full violation report.
- **C5,C6**: ARCHITECTURE.md Gap section rewritten -- "Closing work" subsection replaced with "The gap section is EMPTY as of 2026-06-21" + a note that future IDEAS expansions are scope additions, not gaps.

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| TestVerticalColumnOwnership.py | Tests/Contract/ | next commit |
| Gap section emptied + invariant message added | ARCHITECTURE.md | next commit |

### Decisions Made

- Test scans for two patterns: `SET <Col> =` and `<Col> = v.` (FROM VALUES style). Catches both shapes in the codebase.
- Scripts/ excluded -- one-shot migration scripts may temporarily write a column being converted (e.g. ConvertWorkBucketToGenerated.py). Admission-controlled by the human running them.
- Tests/ excluded -- contract tests may construct synthetic rows.
- Templates/ excluded -- HTML/JS, not Python.
- Future-IDEAS items moved out of Gap section -- they are scope-EXPANSIONS to the architecture, not gaps against it.
