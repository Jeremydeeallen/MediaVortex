---
description: Verify repo-local monotone-decrease invariants declared in .claude/.conformance-baselines.json. Asserts that named files have not grown beyond their baseline (line count, import count). Complements /check-conformance for in-flight migrations.
argument-hint: <none>
---

You are running the MediaVortex monotone-decrease baselines check. This is
the per-repo invariant gate for in-flight migrations: named files must NOT
grow above their declared baseline. Tracks migration progress in a way
`/check-conformance` (framework-generic) cannot.

## Steps

### Step 1 -- read the baselines file

```
.claude/.conformance-baselines.json
```

If the file does not exist, SKIP with a one-line note. The file is opt-in.

The shape is `{ "baselines": [ { ...entry-specific keys... } ] }`. There are two entry shapes:

**File-scoped entry** -- has `file` and `metric` in (`line_count`, `import_count`). `import_module` is required when `metric = "import_count"` (the dotted path that must appear after `from ` in import statements).

**Scope-scoped entry** -- has `scope` (informational tag, e.g. `"production_code"`), `metric` (free-form identifier), `regex` (the pattern to count), `paths` (array of path prefixes / files to scan), optional `exclude_files` (array of repo-relative paths to skip even if matched by `paths`). Used for project-wide anti-pattern counters such as `os_path_on_pathvar_count`, `pathvar_replace_split_count`, `allow_r6_annotation_count`, `pathstorage_private_import_count`.

`feature_doc` is optional on either shape and points at the `*.feature.md` driving the migration.

### Step 2 -- compute current values

For each entry:

- `metric = "line_count"` -- count newlines in `file`. On Windows use `(Get-Content -Path $f).Count`; on POSIX use `wc -l`. If `file` does not exist, treat `current = 0` (migration complete).
- `metric = "import_count"` -- across all `*.py` in the repo, count lines matching `from {import_module} import\b` (any line; indented imports count). Exclude paths under `.claude/`, `venv/`, `WebService/venv/`, and `__pycache__/`.
- **scope-scoped entry with `regex`** -- for each path in `paths`, run `Grep(pattern=<regex>, path=<path>, type='py', output_mode='count', head_limit=0)`. If the path ends with `.py` it is a single file (Grep handles it). Sum the per-file counts. Drop any file listed in `exclude_files` (compare repo-relative path). The total across all paths is `current`.

Use the Grep tool (NOT `grep`/`rg`) for any metric. Example for the regex case: `Grep(pattern='os\\.path\\.(basename|dirname|join)\\s*\\(\\s*\\w*(?:path|filepath)\\w*', path='Features/', type='py', output_mode='count', head_limit=0)`.

For regex-based entries, when `current > 0` AND the count is small (<= 25), also run `output_mode='content'` with `-n` against the same paths and include the offending `file:line:match` rows in the failure report. This makes the regression actionable without spending tokens on the happy path.

### Step 3 -- compare and report

For each entry:

- `current > baseline` -- FAIL. Report `{file}` `{metric}` `baseline={baseline}` `current={current}` `delta=+{current - baseline}`. If `feature_doc` is set, append "monolith being migrated per `{feature_doc}`" -- the operator should read that doc for the path to lower the baseline.
- `current <= baseline` -- PASS. If `current < baseline`, append the suggestion "consider tightening baseline to {current} in .claude/.conformance-baselines.json" so the floor ratchets down with progress.

Overall result is FAIL iff any entry fails. The baselines file is operator-owned -- this command does NOT write to it. Operators tighten the baseline by editing the integer manually.

### Step 4 -- exit

Print a summary table:

```
MediaVortex baselines check
===========================
  target                                   metric                              baseline   current   status
  Repositories/DatabaseManager.py          line_count                          <N>        <M>       PASS/FAIL
  Repositories.DatabaseManager (imports)   import_count                        <N>        <M>       PASS/FAIL
  production_code                          os_path_on_pathvar_count            0          <M>       PASS/FAIL
  production_code                          pathvar_replace_split_count         0          <M>       PASS/FAIL
  production_code                          allow_r6_annotation_count           0          <M>       PASS/FAIL
  production_code                          pathstorage_private_import_count    0          <M>       PASS/FAIL

Overall: PASS | FAIL
```

For scope-scoped entries the `target` column shows the `scope` field (e.g. `production_code`).

Exit non-zero if FAIL.

## Why this command exists

`/check-conformance` is framework-generic and lives in `claude-rails`. Adding a MediaVortex-specific check there would couple the framework to one repo's migration state. Instead, this command sits in `.claude/commands/`, owned by MediaVortex, and references the data-driven baselines file. Other repos on claude-rails can adopt the pattern by creating their own `*-check-baselines` command and their own baselines file -- nothing in the framework needs to change.

See `Core/Database/repository-split.feature.md#perfect-end-state` for the migration this currently tracks.
