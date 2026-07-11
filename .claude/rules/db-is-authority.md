# DB Is Authority

The PostgreSQL database is the single source of truth for runtime configuration, capability flags, and queue state. Code MUST NOT cache DB values at boot and then act on the cached snapshot. Mid-flight operator changes (GUI flag flips, threshold edits, status transitions) MUST be observed by the next claim, decision, or read.

## The invariant

For every capability-gated claim query, the SQL embeds the worker-capability gate via `Core.Database.WorkerCapabilityPredicate.BuildClaimPredicate`. One place emits this clause; no claim query hand-rolls its own.

For every decision/disposition read of config (thresholds, gate state, system settings), the code calls a repository method that reads DB fresh per call. No `self._cached_*` on long-lived instances. No `_LoadConfig()` invoked once in `__init__`.

In-flight execution state is a DB invariant, not a code check: `TranscodeAttempts` carries a partial UNIQUE index `ta_one_inflight_per_mfid ON (MediaFileId) WHERE Success IS NULL`. Two workers cannot both hold Success-NULL attempts for the same MediaFileId; the DB refuses at INSERT. See `.claude/rules/claim-authority.md`.

## Verified conventions

- `Core/Database/WorkerCapabilityPredicate.py` -- single source for the capability-gate SQL fragment. Whitelists allowed capability column names (SQL-injection safe).
- `Repositories/DatabaseManager.ClaimNextPendingTranscodeJob` -- routes through helper. Honors `TranscodeEnabled` + `Status='Online'` + (for NVENC) `nvenccapable`.
- `Repositories/DatabaseManager.ClaimNextPendingRemuxJob` -- honors `RemuxEnabled` + `Status='Online'`.
- `Repositories/DatabaseManager.ClaimQualityTestJob` -- honors `QualityTestEnabled` + `Status='Online'` + `ForceDisposition IS NULL`.
- `Tests/Contract/TestClaimAuthority.py` -- asserts the invariant per claim path. Run before merging any change touching a claim.

## When this rule applies (PR triggers)

- Adds or edits a function whose name begins with `Claim` against a queue table
- Adds or edits a decision function whose return drives a state transition
- Modifies a column on `Workers`, `SystemSettings`, `PostTranscodeGateConfig`, `ProfileThresholds`, or any other table read at decision time
- Adds a poller / worker thread consuming a queue

If your PR touches any of the above, run `py -m pytest Tests/Contract/TestClaimAuthority.py` and reference this rule in the PR description.

**Mid-flight reload mechanics, common mistakes, related docs:** see `.claude/rules-details/db-is-authority.md`.
