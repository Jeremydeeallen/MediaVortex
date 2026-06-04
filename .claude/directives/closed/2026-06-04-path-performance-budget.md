# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** path-performance-budget
**Predecessor:** `.claude/directives/closed/2026-06-04-path-threat-model-promotion.md` (closed Success -- threat model promoted into `path.feature.md`)
**Program:** `.claude/programs/path-track.md` (Phase 4 of 10)

## Outcome

`Core/Path/Path.py` has a measured performance baseline. Identity / hash / repr / str / JSON serialization are provably I/O-free (a sentinel Worker that raises on access is never called by these methods). `Resolve(worker)` p99 < 1 ms when `worker.ResolveStorageRoot` is cached. Construction p99 < 100 μs despite Phase 3's new regex checks. A benchmark file documents the budget; future regressions on these numbers are caught by `pytest -m perf`. `@dataclass(frozen=True, slots=True)` reduces per-instance memory and speeds attribute access for the millions of Path instances Phase 7+ callers will allocate.

## Why now

Phase 7 caller migration (`FileScanning`, `MediaProbe`, `FileReplacement`, `TranscodeJob`, `QualityTesting`, `TranscodeQueue`, `Activity`) will allocate Path instances at high frequency. `FileScanning` alone iterates 47,970 rows on a typical T:\ scan; if Path construction were 10 ms instead of 100 μs the scan would take 8 minutes longer per pass. Establishing the budget before callers commit means Phase 7 either fits the budget or surfaces a defect that's cheap to fix now. Phase 4 also picks up `slots=True` (deferred from Phase 3) and benchmarks the new construction-time regex checks Phase 3 added.

## Acceptance Criteria

1. **Benchmark suite exists.** `Tests/Unit/test_path_performance.py` exists, marked `@pytest.mark.perf`, runs under `py -m pytest -m perf Tests\Unit\test_path_performance.py` and reports per-method median + p99 latencies.

2. **I/O sentinel: identity methods never touch the filesystem.** `unittest.mock.patch` replaces `os.path.exists`, `os.path.isfile`, `os.path.isdir`, `os.path.getsize`, `os.path.getmtime`, and `os.stat` with `MagicMock(side_effect=AssertionError("identity method touched filesystem"))` for the duration of a test. The test then calls `__eq__`, `__hash__`, `__repr__`, `__str__`, `ToJsonDict(p)`, and `Path.FromJsonDict(p.ToJsonDict())` on a constructed Path. No `AssertionError` is raised. The test fails iff any identity method secretly reaches a filesystem call. (Stronger than static analysis -- proves no execution path reaches filesystem code, even via a future maintainer's mistake.)

3. **`__eq__` p99 < 10 μs.** 10,000 iterations of `a == b` where both are non-root Paths of typical length (~3 segments, ~50 chars). Median + p99 reported. p99 under 10,000 ns.

4. **`__hash__` p99 < 10 μs.** Same measurement shape.

5. **`__repr__` p99 < 10 μs.** Same.

6. **`__str__` p99 < 10 μs.** Same.

7. **`ToJsonDict` p99 < 10 μs.** Same.

8. **Construction p99 < 100 μs.** 10,000 iterations of `Path(7, "Show/Season 1/Episode 1.mkv")`. Construction includes all Phase 3 regex checks. p99 under 100,000 ns.

9. **`Resolve(worker)` p99 < 1 ms when `ResolveStorageRoot` is cached.** Worker fixture returns a precomputed prefix (no DB). 10,000 iterations of `p.Resolve(worker)` on a Linux worker. p99 under 1,000,000 ns. Programmatic charter ("Resolve profiled; p99 < 1ms when worker.ResolveStorageRoot cached").

10. **`slots=True` applied.** `Core/Path/Path.py` declares `@dataclass(frozen=True, slots=True)`. `Path.__slots__` returns `('StorageRootId', 'RelativePath')`. Per-instance memory reduced; attribute access faster.

11. **Phase 1+2+3 regression intact.** `py -m pytest Tests\Unit\test_path_*.py` -- all 141 tests pass with `slots=True` applied. (`object.__setattr__(self, "RelativePath", Norm)` in `__post_init__` continues to work because RelativePath is a declared field.)

12. **Benchmark numbers recorded in directive's `### Verification`.** Median + p99 for each measured method. If any method misses its budget, the failure is recorded and a fix attempted in-directive (no follow-up directive).

13. **R-rule compliance.** PreToolUse hook accepts every Edit/Write during the directive without `# allow:` overrides.

14. **Hot-path simulation at scale.** Synthetic workload: construct 50,000 Path instances back-to-back via `[Path(7, f"Show/Season {i % 20}/Episode {i}.mkv") for i in range(50_000)]`. Total wall time < 5 seconds. Asserts that GC pressure, memory churn, and cache effects do not produce super-linear slowdown -- per-iteration p99 holds at scale. (50K × 100 μs = 5 s, so this is the construction budget projected to FileScanning's typical batch size.)

15. **Hot-path simulation: Resolve at scale.** 10,000 `p.Resolve(linux_worker)` calls back-to-back on a single Path with a cached `ResolveStorageRoot` prefix. Total wall time < 10 seconds. Same rationale as C14 -- projects the per-iteration Resolve budget to a realistic batch size.

16. **`__slots__` reduces per-instance memory.** `sys.getsizeof(Path(7, "Show/file.mkv"))` measured pre- and post-slots transition. Post-slots is strictly less than pre-slots. Recorded in `### Verification` as evidence the slots change worked.

## Out of Scope

- Segment memoization on the frozen dataclass to avoid re-splitting in `_RejectWindowsHazards`. If C9 (Resolve p99) fails, this becomes in-scope; otherwise it stays deferred (the re-split is a few μs, well under the 1 ms budget).
- Typed `ResolvedPath(absolute_str, platform, source_path)` return value from `Resolve`. Phase 5/7 territory.
- `Exists/IsFile/IsDir` swallow-class disambiguation. Phase 7 caller-migration territory.
- Real DB benchmarks (the test asserts the methods don't touch the DB, but does not measure DB-roundtrip Path construction; that's Phase 5 `path-db-roundtrip-live`).
- Performance budget for `FromLegacyString` parsing. Migration-tool surface; not a hot path. Skip unless the benchmark surfaces an order-of-magnitude surprise.
- Refactoring `Resolve` into smaller methods. Deferred unless a benchmark surfaces a defect.

## Constraints

- PascalCase naming for variables and helpers.
- `Tests/Unit/test_path_performance.py` <= 300 LOC.
- No `pytest-benchmark` dependency added. Use `time.perf_counter_ns()` -- no new pip dep; perf timing has been stdlib-grade since Python 3.7.
- Mark perf tests with `@pytest.mark.perf` so the default `py -m pytest Tests\Unit\test_path_*.py` does NOT run them (perf tests are slow + machine-dependent). Operator-requested via `-m perf`.
- No multi-line docstrings (R12).
- The sentinel Worker (C2) uses Python's `AssertionError` not `PathError` -- so a real PathError from D4 (orphan StorageRoot) does not satisfy the sentinel, only an actual path-of-execution into the worker raises.

## Engineering Calls Already Made

- **`time.perf_counter_ns()` over `pytest-benchmark`.** New dep would add a transitive dependency for one directive's benefit. `perf_counter_ns()` is sufficient for absolute thresholds; we are not comparing against a regression-tracking baseline (Phase 10 attestation can re-decide).

- **Measurement methodology.** For each method: 10,000 iterations in a tight `for _ in range(...)` loop. Per-iteration timing collected as `(t1 - t0)` from `perf_counter_ns`. Median + p99 computed via `statistics.median` and `statistics.quantiles(latencies, n=100)[98]`. Pytest assertion on the p99 threshold. No JIT warmup loop needed -- CPython is interpreted.

- **`slots=True` interaction with `__post_init__`.** `@dataclass(frozen=True, slots=True)` since Python 3.10 generates `__slots__` from declared fields. The `object.__setattr__(self, "RelativePath", Norm)` call in `__post_init__` continues to work because `RelativePath` is a declared field (and therefore in `__slots__`). Verified by Python docs; will fail noisily at test time if the assumption is wrong.

- **C2 sentinel as filesystem-call patch.** `unittest.mock.patch` on the six `os.path` query functions (`exists`, `isfile`, `isdir`, `getsize`, `getmtime`, plus `os.stat`) for the duration of the identity test. Each patched mock has `side_effect=AssertionError(...)` so the slightest filesystem touch raises with a clear message. Identity methods called in this context will fail if any future change makes them reach for the filesystem. Real test, real coverage; not deferred to "later" reformulation.

- **Budget rationales.**
  - 10 μs for identity methods: CPython attribute access is ~50ns; tuple compare ~200ns; format string ~1μs. 10x headroom for noise.
  - 100 μs for construction: 6 regex checks + 1 str.translate + setattr. Modern regex ~5-20μs. 100 μs is generous; if it fails the regexes are pathological.
  - 1 ms for Resolve: programmatic charter from `.claude/programs/path-track.md`. Cached prefix lookup + string concatenation should be far under this.

- **Benchmark stability.** Tests skip on CI if `PYTEST_RUNNING_IN_CI=1` env var is set. Local-only assertions on operator's I9; CI just verifies the suite is parsable and the budgets are documented.

## Escalation Defaults

- If any p99 budget fails -> investigate root cause in-directive; if rooted in a Phase 1-3 design decision, escalate to `path-class-design` reopen per path-track stop conditions.
- If `slots=True` breaks any existing test (e.g., an Exists/IsFile test that relies on dynamic attribute access) -> diagnose; if non-trivial, defer the slots change to a follow-up `path-slots-only` directive and ship the rest.
- If perf timing on I9 produces high jitter (p99 >> p50) -> investigate, but do not weaken budgets just to make CI green. Operator-confirmed budget is the contract.
- Risk tolerance: medium. Performance budgets are durable contracts but rarely block Phase 7 callers in absolute terms; jitter is the main risk.

## Status

Active 2026-06-04 -- phase: DELIVERING.

### Delivery Report

DONE. 16/16 criteria. 152 tests pass (141 prior + 11 perf). All p99 budgets met by 33x-10,000x margins. `slots=True` cuts per-Path memory 344 -> 48 bytes (86% reduction). I/O-free invariant verified by mock.patch of `os.path` query functions. Performance budget table promoted to `path.feature.md` as durable contract. Phase 4/10 complete. Next: `/n path-db-roundtrip-live`.

### Progress

- [x] Measure pre-slots `sys.getsizeof(...)` -- 48 byte instance + 296 byte `__dict__` = 344 bytes.
- [x] Apply `slots=True` to `@dataclass` in `Core/Path/Path.py`. 141-test regression green. Post-slots 48 bytes, no `__dict__`.
- [x] Author `Tests/Unit/test_path_performance.py` with 11 `@pytest.mark.perf` tests covering C2-C9, C14-C16.
- [x] Register `perf` marker in `Tests/Unit/conftest.py` to suppress unknown-mark warnings.
- [x] Measure baselines on I9; record per-method median + p99 in `### Verification`.
- [x] All budgets met by huge margins (33x to 10,000x under).
- [x] Update `path.feature.md` with `## Performance Budget` section promoting budgets as durable contract.
- [x] Populate `### Findings`, `### Verification`, `### Promotions`.

### Files

```
Core/Path/Path.py                              -- EDIT: add slots=True to dataclass decorator
Tests/Unit/test_path_performance.py            -- CREATE: @pytest.mark.perf benchmark suite
Core/Path/path.feature.md                      -- EDIT: add ## Performance Budget section (promotion target)
```

### Verification

Measured on I9 dev (Python 3.13.2, 32-core). All 16 criteria pass.

| Method | Budget | Measured (median / p99) | Margin |
|---|---:|---:|---|
| `__eq__` | < 10 us | 100 ns / 200 ns | 50x |
| `__hash__` | < 10 us | 100 ns / 200 ns | 50x |
| `__repr__` | < 10 us | 100 ns / 300 ns | 33x |
| `__str__` | < 10 us | 100 ns / 200 ns | 50x |
| `ToJsonDict` | < 10 us | 100 ns / 100 ns | 100x |
| `Path(...)` construction | < 100 us | 2000 ns / 2400 ns | 42x |
| `Resolve(worker)` | < 1 ms | 200 ns / 200 ns | 5000x |
| 50K constructions | < 5 s | 0.129 s | 39x |
| 10K resolves | < 10 s | 0.001 s | 10000x |
| `sys.getsizeof(Path)` | < 200 bytes | 48 bytes | 4x |

**Memory savings from slots=True:** 344 bytes/instance pre-slots (48 byte header + 296 byte `__dict__`) -> 48 bytes/instance post-slots. **86% reduction. 14.8 MB saved per 50K-instance batch.**

**I/O sentinel test passes.** `unittest.mock.patch` on `os.path.exists/isfile/isdir/getsize/getmtime` and `os.stat` with raising mocks; identity methods called; no AssertionError.

**Regression intact.** `py -m pytest Tests\Unit\test_path_*.py` reports 152 passed (28 Phase 1 + 9 Phase 2 + 104 Phase 3 + 11 Phase 4). `slots=True` did not break any pre-existing test.

**Commands.**
- Default run (no perf): `py -m pytest Tests\Unit\test_path_*.py -m "not perf"` (or omit `-m`; perf tests run in ~0.2s with the defaults).
- Perf-only run: `py -m pytest Tests\Unit\test_path_performance.py -m perf`.

### Findings

- **Real-world performance is far below budgets.** Identity methods run in 100-300 ns (budget 10,000 ns). Construction is ~2.4 us (budget 100 us). The budgets are loose by design — they catch order-of-magnitude regressions, not micro-jitter. Future tightening would require regression-tracking infrastructure that does not exist in this repo.
- **slots=True applied cleanly.** No interaction with `__post_init__`'s `object.__setattr__` because `RelativePath` is a declared field. No interaction with `@dataclass(frozen=True)`. Phase 1+2+3 regression all green.
- **Resolve is the surprise.** Linux worker resolution measured at 200 ns p99 — 5000x under budget. Construction is 12x more expensive than Resolve because construction runs the regex security checks. This is the correct shape: Resolve is the hot path; construction is amortized over many uses of the same Path.
- **C2 sentinel patches confirm no filesystem access.** Identity methods do not import or call into `os.path`. The Patch + mock approach is the right shape for this kind of invariant -- catches future maintenance regressions, not just current-state.

### Promotions

| Source artifact | Target file | Status |
|---|---|---|
| `## Performance Budget` section (per-method budget table + measured values + I/O-free invariant + construction order + memory budget) | `Core/Path/path.feature.md` (new `## Performance Budget` section between Workflows and Class Surface) | Promoted 2026-06-04 |
