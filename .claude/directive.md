# Current Directive

**Set:** 2026-06-05
**Status:** Active -- phase: IMPLEMENTING
**Plan:** `C:\Users\jerem\.claude\plans\flickering-yawning-aurora.md` (approved 2026-06-05; batched as A live-safe / B restart-only / C drain)
**Slug:** path-class-perfection
**Predecessor:** `.claude/directives/closed/2026-06-05-path-schema-migration.md` (closed; 10 legacy columns dropped, but the inlined `path-perfect-implementation` plan's "perfect" contract was not honored — see Findings of that directive vs the 8 design weaknesses listed below)

## Outcome

The `Core/Path/` value-object system is honestly "perfect" -- no caller can reach a wrong outcome from a typo, no module-level cache hides DB state, no f-string footgun displays the wrong thing, no DBA/tester can read a `# allow:` annotation baked inside a SQL string. The 8 design weaknesses surfaced in the post-close audit (2026-06-05 retrospective) are closed in code AND in the relevant `path.feature.md` Success Criteria. After this directive: the perfect-implementation plan's title is actually true.

## Why this is its own directive, not a "follow-up"

The closing of `2026-06-05-path-schema-migration.md` was premature — the predecessor inlined the `path-perfect-implementation` plan and declared it complete based on the END-STATE-ARCHITECTURE checklist (typed pair, CanonicalDisplay synthesis, worker-local resolution, zero shape-agnostic wrappers). The 8 weaknesses below are NOT in that checklist but are in the spirit of the plan's title. Reopening the predecessor would muddle the schema-drop record; opening a fresh directive scoped to "honest perfect" is the right surgery. This is the failure mode `feedback_act_on_what_you_already_know.md` catches: my honest retrospective named 8 weaknesses, and refusing to act on them after naming them is the bug.

## Acceptance Criteria

1. **`Path.FromLegacyString` fails loudly on unknown prefix.** Today: silently returns a `Path` with unresolvable typed pair or `None`. Required: raise a typed exception `UnknownStorageRootPrefix(input_str, available_prefixes)` that callers MUST handle. Controllers (HTTP boundary) catch and return structured 400 with `AvailableRoots`. Workers crash-fast — silent corruption is worse than a worker crash.

2. **`Core/Path/PathStorageRoots.GetStorageRoots()` reads DB fresh per call.** Today: caches the StorageRoots table at first access (module-level singleton). Required: every call hits DB. This is `db-is-authority.md` applied to read-mostly tables — the rule exists, I violated it, the violation gets removed. Performance: if a hot path proves this matters, add a TTL'd cache LATER with explicit invalidation; default is fresh.

3. **`Path` value object implements `__str__` and `__repr__` with defined contracts.** `__str__(Path) -> CanonicalDisplay(module-level prefix map)`. `__repr__(Path) -> "Path(StorageRootId=N, RelativePath='...')"`. After this, f-strings (`f"{path}"`) and logger calls produce the canonical display by default — eliminating the "I'll just put `{path}` in an f-string" footgun.

4. **`CanonicalDisplay(prefix_map)` parameter is removed in favor of module-level state.** No caller ever passes anything other than `GetPrefixMap()`. The signature becomes `CanonicalDisplay() -> str` reading the module-level prefix map. Test-only injection via a context manager or test fixture, not a runtime parameter.

5. **Tree-wide sweep for SQL-string-baked `# allow:` annotations.** Grep `--include='*.py' "# allow:.*--"` and `"# allow:"` inside SQL string literals (multi-line and single-line). Every hit is fixed (move the annotation outside the SQL string, or remove if the underlying rule violation is now legitimate). No surviving `# allow:` inside a SQL string. This is the BUG-class `vmaf-restoration` had to clean up reactively; the proactive sweep closes the latent set.

6. **`WorkerContext` indirection flattened.** Today: `WorkerContext.Current().PathTranslation` removed, but criterion 4 still routes through `Worker.FromWorkerContext()` which wraps the WorkerContext singleton. Required: callers either take a `Worker` parameter directly OR `Worker.Current()` is the singleton entry (drop the WorkerContext intermediate for path-resolution purposes). `WorkerContext` may keep its non-path responsibilities (FFmpeg path, capability flags) but path-resolution doesn't go through it anymore. Update `Core/WorkerContext.feature.md` criterion 4 accordingly.

7. **Property-based fuzz test for the `FromLegacyString -> CanonicalDisplay` boundary.** New test under `Tests/Unit/test_path_fuzz.py` using `hypothesis` (already in `requirements.txt`? — verify, add if missing). Property: for every valid `(StorageRootId, RelativePath)` pair drawn from the live `StorageRoots` table, `FromLegacyString(CanonicalDisplay(P)) == P`. 1000+ iterations. Failure on any single case blocks merge.

8. **`RootFolderModel.RootFolder` `@property` synthesis decoupled from template binding.** Today: templates bind to `.RootFolder` and we synthesize via Path.CanonicalDisplay. Required: either (a) templates bind to a typed-pair-aware Jinja filter `{{ root_folder_model | canonical_display }}` (preferred), OR (b) the model's `__str__` does it and templates use `{{ root_folder_model }}`. The `@property` named `RootFolder` is removed (callers grep + update; same commit per `feedback_one_logical_change_per_commit.md`). Template references to `.RootFolder` get swept.

## Out of Scope

- Performance benchmarking. Acceptance is correctness + clarity; perf comes after if measurement says it matters.
- Renaming any existing public API of `Path` (the value object's shape stays the same; only `__str__`/`__repr__` are added).
- Backporting any of this to closed directives. Closed directives stay closed.
- VMAF flow doc separation (filed at `.claude/directives/backlog/vmaf-flow-doc.md`; separate directive).

## Constraints

- PascalCase, R12 (single-line comments, no triple-quoted SQL — and the AC #5 sweep is the corollary), R14 (no annotation lines in feature docs), R15 (`# directive: path-class-perfection` anchors on every touched def), R16 (stable IDs).
- Per `feedback_grep_callers_before_deletion.md`: every helper / @property / parameter removal is preceded by a tree-wide grep of callers. Every caller's update lands in the SAME commit as the removal.
- Per `feedback_smoke_test_per_step_not_at_end.md`: each step's exit gate is a deploy + restart + smoke endpoint on the relevant worker.
- Per `feedback_promotions_grow_incrementally.md`: every step's commit that lands durable content into `path.feature.md` or `Core/WorkerContext.feature.md` adds its Promotions row in the SAME commit.

## Engineering Calls Already Made

- **Fail-fast over fail-quiet on AC #1.** Silently substituting `None` for an unknown prefix corrupts downstream typed-pair queries. A loud exception forces every caller to confront the boundary.
- **AC #2 = fresh-per-call, not TTL'd cache.** Cache is a premature optimization; correctness first. If profiling shows StorageRoots-table reads are a hot-path bottleneck, we add a TTL'd cache then.
- **AC #5 sweep is tree-wide, not just QualityTesting / TranscodeJob.** The two files we hit reactively in `vmaf-restoration` were not exhaustive. Tree sweep closes the latent set in one pass.
- **AC #8 prefers Jinja-filter over `__str__`.** Reason: `__str__` collides with AC #3's `Path.__str__`; if `RootFolderModel.__str__` returns canonical display, that's an extra concept. A `canonical_display` Jinja filter is one filter callers can apply anywhere.

## Status

Active 2026-06-05 -- phase: NEEDS_PLAN.

### Progress

- [ ] Plan the 8 ACs by dependency (e.g. AC #3 `__str__` may need to land before AC #4 to keep test surface stable).
- [ ] AC #2: Drop `GetStorageRoots()` cache. (Smallest; lowest risk; serves as proof of the rest.)
- [ ] AC #1: Make `FromLegacyString` fail loud. + controller adaptation.
- [ ] AC #3: Add `Path.__str__` + `__repr__` with defined contracts.
- [ ] AC #4: Drop `prefix_map` parameter from `CanonicalDisplay`. + caller sweep.
- [ ] AC #6: Flatten `WorkerContext` path-resolution indirection.
- [ ] AC #8: Decouple `RootFolderModel.RootFolder` `@property`. + template sweep.
- [ ] AC #5: Tree-wide `# allow:` in SQL string sweep.
- [ ] AC #7: Property-based fuzz test.
- [ ] Populate `### Verification` + `### Findings` + `### Promotions` per step.
- [ ] Update `path.feature.md` Success Criteria with new IDs (C22 fail-loud-on-unknown-prefix, C23 fresh-DB-read, C24 `__str__`/`__repr__` contract, C25 no `prefix_map` param, C26 no SQL-string `# allow:`, etc.).

### Files

Planned (the plan refines this):

```
Core/Path/Path.py                                    -- EDIT (AC #3, AC #4)
Core/Path/PathStorageRoots.py                        -- EDIT (AC #2, AC #4)
Core/Path/path.feature.md                            -- EDIT (C22-C27 added; R16-stable IDs)
Core/WorkerContext.py                                -- EDIT (AC #6)
Core/WorkerContext.feature.md                        -- EDIT (criterion 4 rewritten)
Features/FileScanning/Models/RootFolderModel.py      -- EDIT (AC #8)
Features/FileScanning/FileScanningController.py      -- EDIT (AC #1 controller adaptation)
Templates/*.html                                     -- EDIT (AC #8 template sweep)
Tests/Unit/test_path_fuzz.py                         -- CREATE (AC #7)
<every-py-with-allow-r12-in-sql>                     -- EDIT (AC #5 sweep)
requirements.txt                                     -- EDIT (verify hypothesis)
```

### Verification

| AC | Evidence |
|---|---|
| #5 | `pytest Tests/Unit/test_no_sql_string_annotations.py` -> 4 passed (4 tests cover prod-tree scan, deliberate-violation self-check, out-of-string-annotation false-positive prevention, non-SQL-string false-positive prevention). Zero violations in production tree. |
| #7 | `pytest Tests/Unit/test_path_fuzz.py` -> 4 passed (3 hypothesis round-trip properties at 1000 examples each, plus 1 PathError unknown-prefix check). |

### Findings

- **Numbering correction.** Plan promised `C22-C26`; actual lowest unused criterion in `path.feature.md` is `C16` (the prior `path-perfect-implementation` plan named `C20` + `C21` in its doc-contract table but those never landed in the feature.md). Starting at `C16` (per R16 stable IDs, no skip-renumbering). Mapping: AC #5 -> C16, AC #7 -> C17. Subsequent ACs claim C18 onward as they land.

### Promotions

| Source artifact (directive scope) | Target file + section |
|---|---|
| AC #5 SQL-string annotation gate + `Tests/Unit/test_no_sql_string_annotations.py` | `Core/Path/path.feature.md` Success Criterion C16 + Verification (Test Plan) rows |
| AC #7 property-based round-trip fuzz + `Tests/Unit/test_path_fuzz.py` | `Core/Path/path.feature.md` Success Criterion C17 + Verification (Test Plan) rows |
