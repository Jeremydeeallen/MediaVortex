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

The shape is `{ "baselines": [ { "file": ..., "metric": ..., "baseline": ..., "import_module": ..., "feature_doc": ... } ] }`. `metric` is one of `line_count` or `import_count`. `import_module` is required when `metric = "import_count"` (the dotted path that must appear after `from ` in import statements). `feature_doc` is optional and points at the `*.feature.md` driving the migration.

### Step 2 -- compute current values

For each entry:

- `metric = "line_count"` -- count newlines in `file`. On Windows use `(Get-Content -Path $f).Count`; on POSIX use `wc -l`. If `file` does not exist, treat `current = 0` (migration complete).
- `metric = "import_count"` -- across all `*.py` in the repo, count lines matching `from {import_module} import\b` (any line; indented imports count). Exclude paths under `.claude/`, `venv/`, `WebService/venv/`, and `__pycache__/`.

Use the Grep tool (NOT `grep`/`rg`) for the import_count metric. Example: `Grep(pattern='from Repositories.DatabaseManager import', type='py', output_mode='count', head_limit=0)` then sum the per-file counts after excluding the directory list above.

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
  file                                     metric            baseline   current   status
  Repositories/DatabaseManager.py          line_count        <N>        <M>       PASS/FAIL
  Repositories.DatabaseManager (imports)   import_count      <N>        <M>       PASS/FAIL

Overall: PASS | FAIL
```

Exit non-zero if FAIL.

## Why this command exists

`/check-conformance` is framework-generic and lives in `claude-rails`. Adding a MediaVortex-specific check there would couple the framework to one repo's migration state. Instead, this command sits in `.claude/commands/`, owned by MediaVortex, and references the data-driven baselines file. Other repos on claude-rails can adopt the pattern by creating their own `*-check-baselines` command and their own baselines file -- nothing in the framework needs to change.

See `Core/Database/repository-split.feature.md#perfect-end-state` for the migration this currently tracks.
