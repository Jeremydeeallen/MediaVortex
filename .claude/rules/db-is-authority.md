# DB Is Authority

The PostgreSQL database is the single source of truth for runtime configuration, capability flags, and queue state. Code MUST NOT cache DB values at boot and then act on the cached snapshot. Mid-flight operator changes (GUI flag flips, threshold edits, status transitions) MUST be observed by the next claim, decision, or read.

## The invariant

For every capability-gated claim query, the SQL embeds the worker-capability gate via the `EXISTS (SELECT 1 FROM Workers ...)` clause produced by `Core.Database.WorkerCapabilityPredicate.BuildClaimPredicate`. There is exactly one place that emits this clause; no claim query hand-rolls its own.

For every decision/disposition read of config (thresholds, gate state, system settings), the code calls a repository method that reads the DB fresh per call. No `self._cached_*` on long-lived service instances. No `_LoadConfig()` invoked once in `__init__`.

## Operator visibility into dynamic re-evaluation (the boot-spawn question)

A reasonable question when reading this rule: "if the claim is the gate, do polling threads need to know the capability flag at all?"

In practice the polling threads DO honor mid-flight flag changes -- not via the claim alone, but via `WorkerService.Main._CapabilityPollingLoop` (default interval 15s, configurable via `SystemSettings.CapabilityPollingIntervalSec`). The loop re-reads `Workers` and calls `_ApplyCapabilities()` to start/stop capability threads as flags change. This is the dynamic mechanism that keeps `self.QualityTestEnabled` etc. fresh on a long-lived worker.

The loop has one design constraint worth noting: it only re-applies capabilities while `Workers.Status='Online'`. When a worker is `Paused`, the reload step is skipped (the worker shouldn't be claiming work anyway). This is intentional and harmless post-claim-authority: even if `self.QualityTestEnabled` is stale during a Paused window, the claim refuses on Status, so no claim is attempted. When the worker transitions back to Online, the next loop tick reloads + reconciles within `CapabilityPollingIntervalSec`.

Net behavior the operator sees:
- Flip `Status` Online -> Paused: claim refusal is immediate (DB gate); the running poller becomes a no-op within ~1 cycle.
- Flip `Status` Paused -> Online: capability reconciliation within `CapabilityPollingIntervalSec`. Threads start.
- Flip `QualityTestEnabled` while Online: thread start/stop within `CapabilityPollingIntervalSec`.
- Flip `QualityTestEnabled` while Paused: cached locally; no effect until Status returns to Online (at which point the loop reads it fresh).

This is symmetric enough that an operator does NOT need to restart a worker to apply a flag change in any normal scenario. If the polling interval is too long for an operator's taste, lower `SystemSettings.CapabilityPollingIntervalSec`.

## Verified conventions

- `Core/Database/WorkerCapabilityPredicate.py` is the single source for the capability-gate SQL fragment. The function whitelists the allowed capability column names to prevent SQL injection via column-name interpolation.
- `Repositories/DatabaseManager.ClaimNextPendingTranscodeJob` routes through the helper. Honors `TranscodeEnabled` + `Status='Online'` + (for NVENC profiles) `nvenccapable`.
- `Repositories/DatabaseManager.ClaimNextPendingRemuxJob` routes through the helper. Honors `RemuxEnabled` + `Status='Online'`.
- `Repositories/DatabaseManager.ClaimQualityTestJob(WorkerName)` routes through the helper. Honors `QualityTestEnabled` + `Status='Online'`. Also gates on `ForceDisposition IS NULL` so operator overrides are not raced.
- `Tests/Contract/TestClaimAuthority.py` asserts the invariant per claim path. Run before merging any change that touches a claim.

## Common mistakes

- **Boot-caching capability flags**: `self.QualityTestEnabled = bool(Row.get('QualityTestEnabled', False))` in `__init__` and then conditioning runtime behavior on `self.QualityTestEnabled`. The cached value diverges from the DB the moment an operator changes it. The claim query is the gate -- the polling thread can run unconditionally.
- **Hand-rolled EXISTS clauses in new claim queries**: copy/paste from a sibling query instead of calling `BuildClaimPredicate`. Drift starts immediately. Always call the helper.
- **`ExecuteQuery` for INSERT/UPDATE with RETURNING**: `DatabaseService.ExecuteQuery` does not commit. Use `ExecuteNonQuery` (auto-commits) for the write, then `ExecuteQuery` to read back. The atomicity guarantee is the `WHERE` predicate inside the UPDATE plus `rows_affected`, not the `RETURNING` clause from a non-committing call.
- **Decision functions that cache thresholds**: a decision function with `self._gate_config_snapshot` taken in `__init__` ignores mid-flight threshold edits. Fetch fresh via the repository on every call.
- **Two-place sources of truth**: the same claim implemented in DatabaseManager AND in a feature repository. One of them drifts. Delete the duplicate; route to the canonical.

## Required reading

- `.claude/programs/db-authority-program.md` -- the multi-PR program retiring the patterns this rule replaces.
- `transcode.flow.md` -- Stage 6 decision table and Stage 7 dual-path trigger illustrate the invariant in production code.
- `Features/QualityTesting/post-transcode-disposition.feature.md` -- C2 already states function-level idempotency; this rule generalizes the claim-level gate.

## When this rule applies

Any PR that:
- adds or edits a function whose name begins with `Claim` against a queue table;
- adds or edits a decision function whose return drives a state transition;
- modifies a column on `Workers`, `SystemSettings`, `PostTranscodeGateConfig`, `ProfileThresholds`, or any other table read at decision time;
- adds a poller / worker thread that consumes a queue.

If your PR touches any of the above, run `py -m pytest Tests/Contract/TestClaimAuthority.py` and reference this rule in the PR description.
