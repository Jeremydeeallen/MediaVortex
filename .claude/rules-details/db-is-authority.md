# DB Is Authority -- Details

> Invariant: `.claude/rules/db-is-authority.md`.

## Operator visibility into dynamic re-evaluation (the boot-spawn question)

A reasonable question: "if the claim is the gate, do polling threads need to know the capability flag at all?"

In practice the polling threads DO honor mid-flight flag changes -- not via the claim alone, but via `WorkerService.Main._CapabilityPollingLoop` (default interval 15s, configurable via `SystemSettings.CapabilityPollingIntervalSec`). The loop re-reads `Workers` and calls `_ApplyCapabilities()` to start/stop capability threads as flags change. This keeps `self.QualityTestEnabled` etc. fresh on a long-lived worker.

The loop has one design constraint: it only re-applies capabilities while `Workers.Status='Online'`. When a worker is `Paused`, the reload step is skipped (worker shouldn't be claiming work anyway). This is intentional and harmless post-claim-authority: even if `self.QualityTestEnabled` is stale during a Paused window, the claim refuses on Status, so no claim is attempted. When the worker transitions back to Online, the next loop tick reloads + reconciles within `CapabilityPollingIntervalSec`.

Net operator behavior:
- Flip `Status` Online -> Paused: claim refusal immediate (DB gate); running poller becomes no-op within ~1 cycle.
- Flip `Status` Paused -> Online: capability reconciliation within `CapabilityPollingIntervalSec`. Threads start.
- Flip `QualityTestEnabled` while Online: thread start/stop within `CapabilityPollingIntervalSec`.
- Flip `QualityTestEnabled` while Paused: cached locally; no effect until Status returns to Online (loop reads fresh).

An operator does NOT need to restart a worker to apply a flag change in any normal scenario. If polling interval is too long, lower `SystemSettings.CapabilityPollingIntervalSec`.

## Common mistakes

- **Boot-caching capability flags**: `self.QualityTestEnabled = bool(Row.get('QualityTestEnabled', False))` in `__init__` and then conditioning runtime behavior on `self.QualityTestEnabled`. The cached value diverges from the DB the moment an operator changes it. The claim query is the gate -- the polling thread can run unconditionally.
- **Hand-rolled EXISTS clauses in new claim queries**: copy/paste from a sibling query instead of calling `BuildClaimPredicate`. Drift starts immediately. Always call the helper.
- **`ExecuteQuery` for INSERT/UPDATE with RETURNING**: `DatabaseService.ExecuteQuery` does not commit. Use `ExecuteNonQuery` (auto-commits) for the write, then `ExecuteQuery` to read back. The atomicity guarantee is the `WHERE` predicate inside the UPDATE plus `rows_affected`, not the `RETURNING` clause from a non-committing call.
- **Decision functions that cache thresholds**: a decision function with `self._gate_config_snapshot` taken in `__init__` ignores mid-flight threshold edits. Fetch fresh via the repository on every call.
- **Two-place sources of truth**: the same claim implemented in DatabaseManager AND in a feature repository. One of them drifts. Delete the duplicate; route to the canonical.

## Related documentation

- `.claude/programs/db-authority-program.md` -- the multi-PR program retiring patterns this rule replaces.
- `transcode.flow.md` -- Stage 6 decision table and Stage 7 dual-path trigger illustrate the invariant in production code.
- `Features/QualityTesting/post-transcode-disposition.feature.md` -- C2 already states function-level idempotency; this rule generalizes the claim-level gate.
