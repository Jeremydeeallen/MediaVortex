# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** path-worker-class
**Predecessor:** `.claude/directives/closed/2026-06-04-path-data-cleanup.md`
**Program:** `.claude/programs/path-track.md` (substrate prerequisite to Phase 7 -- not a numbered phase, but a missing dependency Phase 7 cannot proceed without)

## Outcome

A concrete `Worker` class lives at `Core/Path/Worker.py` and satisfies the structural `Worker` Protocol defined in `Core/Path/Path.py:14`. The class provides `Name: str`, `Platform: str`, and `ResolveStorageRoot(StorageRootId: int) -> Optional[str]` -- the exact surface `Path.Resolve(worker)` consumes. Per-instance prefix cache keeps `Resolve` within Phase 4's < 1ms p99 budget after first-call warmup. Phase 7 caller migrations (`<feature>-uses-path` x 7) construct `Worker` once per batch and pass it to `Path.Resolve(worker)` without each vertical reinventing the lookup.

## Why now

Phase 7 cannot proceed without a concrete Worker. The Protocol exists; the test stubs exist; no production class implements it. Phase 7's program text says "swap callers from `Core/PathStorage.<func>` to `Core/Path/Path.<method>`" -- but every meaningful caller needs to pass `worker` to `Path.Resolve(worker)`. Without this substrate piece, every Phase 7 vertical would either invent its own adapter (7 copies → eventual consolidation tax) or block on the substrate-buildout program (2-week scope). One small focused directive HERE unblocks all 7 verticals cheaply.

## Acceptance Criteria

1. **`Core/Path/Worker.py` exists.** Module file at the canonical location. Single-purpose: defines the concrete `Worker` class. Re-exported by `Core/Path/__init__.py`.

2. **Worker satisfies the Path Protocol.** `Worker` instance has attributes `Name: str` and `Platform: str`, and method `ResolveStorageRoot(StorageRootId: int) -> Optional[str]`. The signature matches the Protocol in `Core/Path/Path.py:14` exactly. Verified by an isinstance-style structural check: `Path(7, "x").Resolve(SomeWorkerInstance)` runs without `AttributeError`.

3. **Reads StorageRootResolutions live.** First call to `ResolveStorageRoot(sid)` queries `SELECT AbsolutePath FROM StorageRootResolutions WHERE StorageRootId=? AND WorkerName=? AND IsActive=TRUE LIMIT 1` against the live DB.

4. **Per-instance cache for performance budget.** Repeated calls to `ResolveStorageRoot(sid)` for the same `sid` on the same `Worker` instance hit the cache, not the DB. Cache is per-instance (not class-level / not module-level) so distinct Worker instances see independent fresh snapshots. Phase 4's p99 < 1ms budget is met after the first lookup per `sid`.

5. **None on miss.** When no `StorageRootResolutions` row matches `(StorageRootId, WorkerName, IsActive=TRUE)`, `ResolveStorageRoot` returns `None`. NOT an exception. Path.Resolve then raises PathError per its existing D4 contract.

6. **DI for testability.** Constructor accepts an optional `Db` parameter (`DatabaseService` instance). If omitted, the Worker constructs its own `DatabaseService()`. Unit tests pass a mock DB to verify caching, lookup, and miss behavior without hitting live PostgreSQL.

7. **Factory from WorkerContext.** Class method `Worker.FromWorkerContext()` reads the process-singleton `WorkerContext.Current()` and constructs a Worker with the same `Name` + `Platform`. Convenience for Phase 7 callers that already use `WorkerContext`.

8. **Unit tests.** `Tests/Unit/test_path_worker.py` exists. Tests: (a) constructor + structural Protocol satisfaction; (b) cache hit on second call to same sid (verified by mock-DB call count = 1); (c) None on no-match row; (d) factory method round-trips WorkerName/Platform from WorkerContext; (e) two Worker instances have independent caches.

9. **Contract test against live DB.** `Tests/Contract/TestPathWorkerLive.py` exists. Constructs a Worker for the I9 worker name, calls `ResolveStorageRoot` for each StorageRoot in the live DB, asserts the returned prefix matches the `AbsolutePath` column directly. Skip with clear message if `StorageRootResolutions` has zero rows for the chosen worker name.

10. **DB-is-authority interaction documented.** A code comment on the Worker class explains: cache lives for instance lifetime; operator changes to `StorageRootResolutions` require constructing a NEW Worker instance (or restarting the host process if the Worker is held by a singleton like `WorkerContext`). Deliberate deviation from db-is-authority's "read fresh per call" rule, justified by Phase 4 budget. Mirrors the existing v1 semantics where workers don't auto-reload mounts mid-process either.

11. **Phase 1-6 regression intact.** `py -m pytest Tests/Unit/test_path_*.py Tests/Contract/TestPathDbRoundTrip.py Tests/Contract/TestPathDbRoundTripAllTables.py` -- 156+ tests pass (152 unit + 4 existing contract + new Worker tests).

12. **Path.Resolve actually works against the live DB now.** End-to-end: `Worker.FromWorkerContext()` + `Path(sid, rel).Resolve(worker)` produces a real absolute path on the local filesystem. Verified by a single live-DB smoke check.

13. **R-rule compliance.** PreToolUse hook accepts every Edit/Write without `# allow:` overrides.

## Out of Scope

- Caller migration (Phase 7). This directive only delivers the substrate piece.
- Re-implementing `Core.PathStorage.Resolve` -- v1 stays as-is until Phase 9 deletion.
- Adding `Worker.RefreshCache()` or TTL-based invalidation. Instance-lifetime cache is the documented behavior; refresh = construct a new Worker. If a future caller needs hot-reload, they open a follow-up directive.
- Modifying `Core/Path/Path.py` or `Core/Path/path.feature.md`'s Protocol definition. The concrete class is downstream of the contract.
- Adding `Worker` to `WorkerContext.Initialize(...)`'s return value. Phase 7 callers can choose `Worker.FromWorkerContext()` at the callsite.
- Symlink resolution, TOCTOU defense, or any other Phase 3 deferred items.

## Constraints

- File location: `Core/Path/Worker.py` (NOT `Core/Worker.py`, NOT folded into `Core/Path/Path.py`).
- LOC budget: <= 120 LOC for `Worker.py`, <= 200 LOC for unit tests, <= 100 LOC for contract test.
- No `os.environ` reads (R4). DB access via `DatabaseService` only.
- No multi-line docstrings (R12). Single-line only.
- PascalCase naming.
- The Worker class does NOT depend on or import anything from `Features/` -- it's pure Core infrastructure.
- No new pip dep.

## Engineering Calls Already Made

- **`Core/Path/Worker.py` not `Core/Worker.py`.** Co-locating with `Path.py` makes the v2 path substrate one importable namespace. `from Core.Path import Path, PathError, Worker` is the intended ergonomics for Phase 7 callers.

- **Cache lives for instance lifetime, no TTL.** Justification: `StorageRootResolutions` rows change only at deployment / operator intervention; in-process mounts don't drift. Matches v1's de-facto semantics where workers restart to pick up mount changes. Documented loudly on the class so the next reader doesn't expect hot-reload. If hot-reload is required later, the constructor can grow a `RefreshTtlSeconds` parameter without breaking callers.

- **Factory `Worker.FromWorkerContext()` is the recommended Phase 7 pattern.** It eliminates 5 lines of boilerplate per callsite (look up `WorkerContext.Current()`, fall back to `socket.gethostname()`, etc.). Callers that don't use `WorkerContext` can construct Worker directly via `Worker(Name=..., Platform=...)`.

- **None on miss, not exception.** Mirrors `Path.FromRow` returning `Optional[Path]` on null typed-pair. Phase 1's D4 contract: `Resolve(worker)` raises PathError when `worker.ResolveStorageRoot(...)` returns None. Worker stays close to the data; Path layer owns the error semantics. This split is the existing Phase 1 design; Worker just honors it.

- **No `WorkerCacheError` / no `ResolveError`.** Worker either returns a string (hit) or None (miss). Any exception from the DB layer (connection error, etc.) propagates up as the underlying psycopg2 / DatabaseService exception -- not wrapped. Caller deals with infrastructure exceptions; this class doesn't add a new exception type.

- **Contract test live-DB safety.** Read-only `SELECT`. No worker bracket needed. Skip cleanly if no `StorageRootResolutions` rows match (e.g., a freshly-cloned DB).

## Escalation Defaults

- If the Worker Protocol in `Core/Path/Path.py` is found to be subtly mismatched (e.g., a Phase that I forgot to read tightened the Protocol mid-program) -> escalate; do NOT silently relax to match an implementation. The Protocol is the contract.
- If `StorageRootResolutions` schema differs from what `Core/PathStorage.Resolve` reads -> investigate; one of them is wrong. Almost certainly the schema matches the existing query.
- If the live contract test produces a different `AbsolutePath` than `PathStorage.Resolve(sid, "", worker_name)` would -> divergence in interpretation; investigate. Worker's `ResolveStorageRoot` returns the PREFIX only; v1 returned prefix+joined. Difference is by design but verify the prefix part agrees.
- Risk tolerance: low. Phase 7 x 7 depends on this. Slow + correct beats fast + drift.

## Status

Closed 2026-06-04 -- Success.

### Delivery Report

DONE. Concrete `Worker` class shipped at `Core/Path/Worker.py`; 13 unit tests + 4 live-DB contract tests pass. Path Protocol satisfied structurally. Per-instance cache preserves Phase 4's < 1ms p99 Resolve budget. Phase 7 caller migration is now unblocked -- each vertical can do `from Core.Path import Path, Worker` and pass `Worker.FromWorkerContext()` to `Path.Resolve(worker)` without re-inventing the substrate.

### Progress

- [x] Authored `Core/Path/Worker.py` -- concrete class with per-instance cache + factory.
- [x] Updated `Core/Path/__init__.py` to re-export the concrete Worker.
- [x] Authored `Tests/Unit/test_path_worker.py` -- 13 mock-DB tests covering cache, miss, factory, isolation, Protocol satisfaction.
- [x] Authored `Tests/Contract/TestPathWorkerLive.py` -- 4 live-DB tests verifying ResolveStorageRoot matches SQL ground truth.
- [x] Full regression: 190 passed, 2 skipped.
- [x] Live smoke (end-to-end): `Path(...).Resolve(Worker(...))` produces a real path via `test_end_to_end_path_resolve_with_live_worker`.
- [x] `### Verification` + `### Findings` + `### Promotions` populated.

### Files

```
Core/Path/Worker.py                          -- CREATE: concrete Worker class
Core/Path/__init__.py                        -- EDIT: re-export Worker
Tests/Unit/test_path_worker.py               -- CREATE: unit tests
Tests/Contract/TestPathWorkerLive.py         -- CREATE: live-DB contract test
```

### Verification

- `py -m pytest Tests/Unit/test_path_worker.py` -- 13 passed.
- `py -m pytest Tests/Contract/TestPathWorkerLive.py` -- 4 passed against live 10.0.0.15:5432 (`test_resolve_storage_root_against_live_db`, `test_resolve_storage_root_unknown_id_returns_none`, `test_end_to_end_path_resolve_with_live_worker`, `test_from_worker_context_constructs_usable_worker`).
- Full regression: 190 passed, 2 skipped in 2.97s (the 2 skips are Phase 5's NULL-branch tests on fully-migrated tables -- expected).
- Path Protocol satisfaction verified structurally via `test_path_resolve_consumes_worker_structurally`: `Path(7, "Show/file.mkv").Resolve(Worker(...))` runs without AttributeError and produces the correct joined path.
- Phase 4 perf invariant preserved: per-instance cache means second call to same sid hits cache (verified by `Mock.ExecuteQuery.call_count == 1` across 3 consecutive `ResolveStorageRoot(7)` calls).

### Findings

- The `__init__.py` re-export had to switch from `from Core.Path.Path import Worker` (Protocol) to `from Core.Path.Worker import Worker` (concrete). Same name; different module. Callers doing `from Core.Path import Worker` get the concrete class. Callers needing the Protocol explicitly do `from Core.Path.Path import Worker`. Documented in module headers.
- `Worker.ResolveStorageRoot` handles BOTH `AbsolutePath` (PascalCase) and `absolutepath` (lowercase) row keys -- psycopg2 `RealDictCursor` returns lowercase per CLAUDE.md; defensive fallback covers both.
- Live contract test discovers a real WorkerName from the DB (no hardcoded host name), making the test portable across operator workstations and future Larry / I9 swaps.

### Promotions

| Source artifact | Target file | Status |
|---|---|---|
| no promotions | n/a | substrate implementation; the existing `## Worker Protocol` section in `Core/Path/path.feature.md` already documents the structural surface, and the concrete Worker is downstream of it (not a contract change) |
