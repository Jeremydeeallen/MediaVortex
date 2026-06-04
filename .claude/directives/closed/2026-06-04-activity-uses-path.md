# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** activity-uses-path
**Predecessor:** `.claude/directives/closed/2026-06-04-mediaprobe-uses-path.md`
**Program:** `.claude/programs/path-track.md` (Phase 7, vertical 2 of 7)

## Outcome

Activity is verified clean: it has zero `Core.PathStorage` imports, zero `os.path.*` calls on path variables, and zero direct `MediaFiles.FilePath` reads in its own code. A single attestation unit test guards this state so future Activity edits cannot reintroduce v1 path patterns without surfacing in CI. After this directive, the path-track program's counter advances (vertical 2 of 7 done) with negligible code change.

## Why this directive is short

The Explore survey found Activity is pure DB-aggregate read + JSON render. It delegates display to controllers and view models that read aggregate columns (compliance counts, audio bands, loudness distribution) -- never path columns. The TranscodingViewModel reads `ta.FilePath` for history rendering but does not resolve it; the string is rendered as-is for operator display. No worker needed. No path resolution needed. The vertical is already in the desired v2 shape.

## Acceptance Criteria

1. **Attestation test exists.** `Tests/Unit/test_activity_uses_path.py` exists. Reads every `.py` file under `Features/Activity/` and asserts that none import from `Core.PathStorage` (substring grep) and none invoke `os.path.<op>` on a path-named local.

2. **Activity remains path-clean after the test passes.** All existing Phase 1-6 regression tests pass. New attestation test passes.

3. **No production code change required.** `Features/Activity/` files unchanged.

4. **No `path.feature.md` Promotion.** Migration Pattern section already documents the Phase 7 recipe; Activity is an existence proof that "no migration needed when vertical is already clean" is a legitimate Phase 7 outcome.

5. **R-rule compliance.** PreToolUse hook accepts the test file without `# allow:` overrides.

## Out of Scope

- `Features/TranscodeJob/VideoTranscodingService.py` and `Features/TranscodeJob/ProcessTranscodeQueueService.py` -- these are Activity's downstream dependencies and DO use `Core.PathStorage`. They are owned by `transcodejob-uses-path` (a later Phase 7 directive), not this one.
- `Features/TranscodeJob/TranscodingViewModel.py:116` -- reads `ta.FilePath` from TranscodeAttempts for display rendering. Display string read, not path resolution. Belongs to `transcodejob-uses-path` if anywhere.
- Refactoring Activity's aggregate queries.
- Adding test coverage for Activity's aggregate response shape -- separate concern.

## Constraints

- Test file: `Tests/Unit/test_activity_uses_path.py`. R8-compliant placement.
- LOC budget: <= 80 LOC for the test file.
- PascalCase. R12 single-line docstrings.
- The grep test reads source files; no DB access, no I/O beyond reading the .py files.

## Engineering Calls Already Made

- **Attestation test, not a migration commit.** The vertical is already clean. A test that locks the state is more valuable than a no-op edit -- it prevents future drift.
- **Substring + AST hybrid attestation.** The test grep-asserts `Core.PathStorage` not in source. For `os.path.*` patterns, an AST walk would be more rigorous than substring matching but adds complexity for a one-off check. Substring grep over `os.path.exists(|isfile(|isdir(|getsize(|getmtime(|dirname(|basename(|join(|split(|splitext(` patterns paired with path-named-variable heuristic is sufficient for an attestation.
- **No deviation from convention.** This is the first Phase 7 vertical where the answer is "already clean." Treating it as a normal directive close (with promotion = none) is the right shape; "no-op" is not a special case.

## Status

Closed 2026-06-04 -- Success.

### Delivery Report

DONE. Vertical 2 of 7 — Activity was already path-clean. Two attestation tests added to lock the state. No production code change.

### Progress

- [x] Authored `Tests/Unit/test_activity_uses_path.py` -- 2 attestation tests.
- [x] All tests pass.
- [x] Close + commit + push.

### Files

```
Tests/Unit/test_activity_uses_path.py    -- CREATE: attestation tests
```

### Verification

- 2 attestation tests pass: `test_no_pathstorage_import_in_activity`, `test_no_os_path_on_path_variable_in_activity`.
- Activity source files: 4 .py files scanned, 0 Core.PathStorage references, 0 os.path violations.

### Findings

- Activity is the smallest Phase 7 vertical: zero production code change. The attestation pattern (substring + regex grep over the vertical's source) is a candidate for the remaining 4 verticals as a defensive add even when migration is required.

### Promotions

| Source artifact | Target file | Status |
|---|---|---|
| no promotions | n/a | vertical was already path-clean; attestation test added; no contract amendments |
