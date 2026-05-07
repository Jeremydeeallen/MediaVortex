# Test Placement

Tests live in dedicated directories, organized by suite.

## Verified conventions
- `Tests/Contract/` -- pytest contract tests against live database
- Suite filenames match the subject (`TestQueueGet.py`, `test_rule_matching.py`)
- No network I/O in unit tests; contract tests may hit the database

## Required reading
- `CLAUDE.md` -- Commands section (test commands)

## Common mistakes
- Writing tests at the repo root instead of the test directory
- Tests that require a running Flask server (those are integration probes, not unit tests)
- Importing fixtures across test suites -- duplicate instead
