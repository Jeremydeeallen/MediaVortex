# Current Directive

**Set:** 2026-06-06
**Status:** Active -- phase: IMPLEMENTING
**Slug:** worker-routing
**Replaces:** `.claude/directives/paused/2026-06-06-db-maintenance-no-partition.md` (paused mid-IMPLEMENTING; one artifact remaining = `Tests/Contract/TestMaintenanceBaseline.py`; resume by un-pausing after worker-routing closes)

## Outcome

The operator can pin each worker to a specific subset of `Profiles` via per-worker checkboxes on the `/Activity` modal. The TranscodeQueue claim path filters Pending rows to the calling worker's allowlist. Today's "every transcode-enabled worker is interchangeable" race becomes a per-machine routing decision that takes two clicks to set up and two clicks to change -- including when a new NVENC card lands on a different host later this week. BUG-0043 (NVENC-capable i9 grabbing CPU-only SVT-AV1 jobs) closes as the operator unchecks SVT profiles on i9.

The full criteria contract lives in `Features/TranscodeQueue/worker-routing.feature.md` (C1-G14, last edited this directive). This directive doc accretes design rationale, in-flight state, and verification evidence; promotions at DELIVERING move durable content back to the feature doc and `transcode.flow.md`.

## Acceptance Criteria

Authoritative: `Features/TranscodeQueue/worker-routing.feature.md` criteria `C1`-`C14` (canonical IDs grouped under section letters A-G for readability; the IDs themselves are `C<N>` per `.claude/rules/feature-docs.md`). Restated here in compact form for the hook + reviewer:

- **C1** (A. Schema). `Workers.AllowedProfiles TEXT NULL` via idempotent migration `Scripts/SQLScripts/AddWorkerAllowedProfiles.py`. NULL = accept all. CSV = explicit allowlist. `""` = accept none.
- **C2** (B. Claim). `ClaimNextPendingTranscodeJob` WHERE clause gains `(w.AllowedProfiles IS NULL OR mf.AssignedProfile = ANY(string_to_array(w.AllowedProfiles, ',')))`. Single emitter in `Core/Database/WorkerCapabilityPredicate.BuildAllowedProfilesPredicate`.
- **C3** (B. Claim). NULL-everywhere = today's behavior. EXPLAIN plan parity + 30-min parallel-claim soak within 5% of baseline.
- **C4** (B. Claim). Mid-flight changes honored within one poll tick (db-is-authority -- no boot cache).
- **C5** (C. Surface). `/Activity` worker modal renders one checkbox per `Profiles.Name`, state reflects current `AllowedProfiles` (all-checked when NULL, listed when CSV, none when `""`).
- **C6** (C. Surface). `POST /api/TeamStatus/Workers/<name>/AllowedProfiles` validates against `Profiles.Name` (400 on unknown), normalizes (sort/dedupe; empty list -> `""`; all profiles -> NULL).
- **C7** (C. Surface). Check-all / Uncheck-all affordances above checkbox list.
- **C8** (C. Surface). Orthogonality truth table: capability switch AND allowlist must both permit to claim.
- **C9** (D. Compat). Migration leaves every existing Worker at `AllowedProfiles=NULL` (no behavior change until operator saves).
- **C10** (D. Compat). Profile rename / delete sweeps every `Workers.AllowedProfiles` CSV in the same transaction.
- **C11** (E. Observability). Claim log row includes `WorkerName`, `JobId`, `ProfileName`, `WorkerAllowedProfiles` (`<all>` / `<none>` / CSV).
- **C12** (E. Observability). Worker tile compact one-line rendering of allowlist below capability row (80-char truncate + tooltip).
- **C13** (F. Flow doc). `transcode.flow.md` updates: (a) the `## Seams` table S1 row (`ST5 -> ST6`) is extended to mention the AllowedProfiles filter alongside the existing `nvenccapable` gate, OR a new S6 row is added for `Workers.AllowedProfiles -> claim filter` -- single-row preferred; (b) the `### Job Claiming Mechanism` prose subsection under `## Service Architecture` notes the new WHERE-clause filter.
- **C14** (G. Bug closure). BUG-0043 smoke (i9 unchecks SVT profiles -> wakko/dot claim the row within one tick); `memory/KNOWN-ISSUES.md` BUG-0043 entry removed at directive close.

## Out of Scope

- Per-job (TranscodeQueue row-level) overrides. Routing is per-worker × per-profile; if a per-job exception ever justifies itself, that is a separate directive.
- Tag-based indirection (the prior `worker-routing` draft's model). Replaced by the direct checkbox matrix; feature doc rewritten to match.
- Other claim paths (`ClaimNextPendingRemuxJob`, `ClaimQualityTestJob`). Same model could extend later; out of scope here.
- Profile-side preference UI ("which workers prefer this profile"). The matrix is per-worker; the other direction would be a derived view, not a separate config surface.
- Load balancing / least-loaded scheduling. This is routing, not scheduling.
- Resuming `db-maintenance-no-partition` -- separate concern; operator un-pauses after this closes.

## Constraints

- **db-is-authority** (`.claude/rules/db-is-authority.md`): `Workers.AllowedProfiles` reads fresh on every claim. No `self._cached_allowed_profiles` in `ProcessTranscodeQueueService`.
- **R10** (`.claude/standards/index.md`): `ClaimNextPendingTranscodeJob` continues to call `BuildClaimPredicate`. New `BuildAllowedProfilesPredicate` is additive.
- **R11**: migration uses `ADD COLUMN IF NOT EXISTS`; runnable repeatedly.
- **R19**: claim query rewrite lands in `Features/TranscodeQueue/TranscodeQueueRepository.py`, not `Repositories/DatabaseManager.py`.
- **R15**: every edited function/class in the `## Files` list gets `# directive: worker-routing` directly above the `def` / `class`.
- **Data integrity** (`.claude/rules/data-integrity.md`): new column is nullable with NULL default (backward compatible). Profile rename/delete sweep runs in the same transaction as the profile mutation (no orphan window).
- **Seam verification** (`.claude/rules/seam-verification.md`): the cross-stage seam `Workers.AllowedProfiles -> claim filter` is enumerated below in `### Seams Crossed` and round-tripped at VERIFYING.

## Escalation Defaults

- **Schema column add** -> Claude executes (`ADD COLUMN IF NOT EXISTS` is reversible; rollback is `ALTER TABLE Workers DROP COLUMN IF EXISTS AllowedProfiles`).
- **Claim-query rewrite** -> Claude executes; runs `TestClaimAuthority.py` + new `TestWorkerAllowedProfiles.py` before declaring done. Live worker restart is operator-executed (memory: I9 services owned by Claude on dev workstation, container workers operator-executed; both via the worker-restart protocol).
- **BUG-0043 smoke** -> Claude executes the synthetic-queue test; reports `TranscodeAttempts.workername` observation per criterion.
- **Risk tolerance:** low for the live worker restart (one cycle, well-defined); medium for the claim-query change (covered by contract test + EXPLAIN-plan parity check).

## Engineering Calls Already Made

- **CSV column, not junction table.** `Workers.AllowedProfiles TEXT NULL`. Cleaner for 10×20 = 200 cells, single ALTER, matches the existing `Workers.Tags` precedent the earlier draft considered. Junction-table refactor is a one-paragraph migration if profile count ever grows past ~100.
- **Single SQL fragment emitter.** `BuildAllowedProfilesPredicate` sibling of `BuildClaimPredicate`. R10 plus operator memory ("db-is-authority single emitter") plus seam discipline -- one place to edit, one place to test, one place to grep.
- **NULL = accept all** (not `""` = accept all). NULL preserves the migration default and is distinguishable from "operator unchecked everything." `""` is a meaningful operator state (parked worker).
- **Clean-default normalization.** When the operator checks every existing profile, the endpoint stores NULL, not the exhaustive CSV. This keeps backward-compat (NULL semantics) and survives adding a new profile later (a NULL worker auto-accepts new profiles; a CSV worker would need re-saving).
- **Profile rename/delete sweep in same transaction.** Avoids orphan window. Implemented in `ProfileRepository.SaveProfile` (rename path) and `ProfileRepository.DeleteProfile`.
- **Worker tile compact rendering on the tile, full checkbox UI in the modal.** Tile is a glance surface; modal is the editor. Putting checkboxes on the tile would scale poorly and clutter the dashboard.
- **No worktree.** Landing on `main` directly. The change is well-scoped (10 files), high-priority (BUG-0043), and worktree session-handoff cost outweighs the isolation benefit at this scale.

## Status

Active 2026-06-06 -- phase: NEEDS_PLAN. Directive doc just opened; criteria + files list written. Next phase: NEEDS_DOC_PREREAD (read every `*.feature.md` / `*.flow.md` ancestor of files in `### Files` below).

### Files

| # | File | Action | Criterion anchor (`# directive: worker-routing \| # see worker-routing.<ID>`) | R-rule notes |
|---|---|---|---|---|
| 1 | `Scripts/SQLScripts/AddWorkerAllowedProfiles.py` | NEW | `C1` on `Run()` | R11: `ADD COLUMN IF NOT EXISTS`. R12: no module docstring, no triple-quoted SQL -- single-line ALTER string. |
| 2 | `Core/Database/WorkerCapabilityPredicate.py` | EDIT (ADD function) | `C2` on `BuildAllowedProfilesPredicate()` | R12: edit region is the new function only; one-line docstring max. SQL fragment is single-line string. Whitelist not needed -- helper takes no column-name argument. |
| 3 | `Features/TranscodeQueue/TranscodeQueueRepository.py` | EDIT | `C2`+`C11` on `ClaimNextPendingTranscodeJob()` | R10: keep `BuildClaimPredicate` call. R12: existing triple-quoted SQL is preexisting; edit must NOT extend the multi-line block -- splice the new fragment as f-string interpolation on the same line where `BuildClaimPredicate`'s fragment is interpolated, OR introduce a single-line concatenation. R6: not path-bearing. |
| 4 | `Features/Workers/WorkersRepository.py` | EDIT (ADD methods) | `C6` on `UpdateWorkerAllowedProfiles()`; `C5`/`C6` on the read-path method that exposes `AllowedProfiles` in `GetWorkerConfig` (or sibling getter) | R12: one-line docstrings max. R3: no `self._cached_*` (db-is-authority -- repo is a stateless query wrapper). |
| 5 | `Features/TranscodeJob/ProcessTranscodeQueueService.py` | EDIT | `C4` on the `GetNextJob` method that calls the claim | R3: no `self._cached_allowed_profiles` -- repo reads fresh. R12: existing docstrings are preexisting; edit-region scope. |
| 6 | `Features/TeamStatus/TeamStatusController.py` | EDIT (ADD endpoint + payload field) | `C6` on `POST /AllowedProfiles` handler; `C5` on the `/Workers` GET handler edit | R9: any `LIKE` queries (none expected) would need `EscapeLikePattern`. R12: one-line docstrings. |
| 7 | `Features/Profiles/ProfileRepository.py` | EDIT | `C10` on `SaveProfile()` (rename path) + `DeleteProfile()` | R12: existing triple-quoted SQL is preexisting; the sweep UPDATE is a single-line string. R9: rewrite UPDATE uses simple `string_to_array` + `array_to_string`, no LIKE. R7: not polymorphic. |
| 8 | `Templates/Activity.html` | EDIT | N/A (HTML; R15 does not apply to non-Python) | R1: colocated `*.feature.md` preread satisfied via `Features/Activity/` ancestor docs (already in scope this session). |
| 9 | `Tests/Contract/TestWorkerAllowedProfiles.py` | NEW | `C2`/`C3`/`C4`/`C8`/`C9`/`C10` distributed across `test_*` functions | R8: under `Tests/Contract/`. R12: one-line docstrings on each test. |
| 10 | `transcode.flow.md` | EDIT | N/A (flow doc; R15 does not apply) | R16: `**Slug:** transcode` already present. R14: no annotation lines (replace S1 row in place; do not annotate "extended for routing"). |
| 11 | `memory/KNOWN-ISSUES.md` | EDIT (mid-flight) + DELETE entry (at close) | N/A (memory; no anchors) | Entry removed at C14 verify; commit message captures the close. |
| 12 | `Features/TranscodeQueue/worker-routing.feature.md` | EDIT (Progress checkmarks as criteria land; Status -> SHIPPED at DELIVERING) | N/A (feature doc; R15 does not apply) | R14: no annotation lines. R16: `**Slug:** worker-routing` already present. R18: any further edits use `limit<=50` Reads. |

### Hook Conformance Pre-Flight (so we don't bounce off the hook mid-implementation)

The accepted code-anchor syntax is **`# directive: worker-routing | # see worker-routing.C<N>`** -- the second `#` after the pipe is required (per `Test-R15-DirectiveAnchor` regex `#\s*see\s+[a-z0-9-]+\.(S|W|C|ST)\d+`). Working examples in tree: `Core/WorkerContext.py:4`, `Features/MediaFiles/MediaFilesRepository.py:8`. Place this comment on the line **immediately above** each `def` / `class` the directive edits.

Phase: edits land in `IMPLEMENTING`. `VERIFYING` allows directive-doc-only edits + read-only Bash. `DELIVERING` re-opens all tools (R13 relaxed) so any `.feature.md` / `.flow.md` create-needs can happen at close.

R-rules that are easy to forget on this directive:
- **R3** -- no `self._cached_allowed_profiles` anywhere. `Workers.AllowedProfiles` is read in the SQL fragment per-claim. No Python-side cache. This is the load-bearing invariant the operator chose this design for.
- **R10** -- `ClaimNextPendingTranscodeJob` must still call `BuildClaimPredicate`. Adding `BuildAllowedProfilesPredicate` is additive, not a replacement.
- **R11** -- migration `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Re-runnable.
- **R12 edit-region trap** -- when editing existing triple-quoted SQL in `TranscodeQueueRepository.py` / `ProfileRepository.py`, the surrounding lines may already contain triple-quoted strings. R12 fires when violations fall in the edit region. Splice strategy: introduce the new fragment as a Python `+`-concatenation or f-string interpolation on a single new line; do NOT add lines INSIDE the existing `"""..."""` block.
- **R14** -- when updating `transcode.flow.md` S1 seam, REPLACE the row in place. Do not add an annotation like `(extended for routing 2026-06-06)`. The seam table is the durable contract.
- **R15** -- every edited `def` / `class` in the table above gets the two-line anchor exactly as specified.
- **R19** -- claim-query edit lands in `TranscodeQueueRepository.py`, not `DatabaseManager.py` (already correct per aggregate-map row 10).

### Seams Crossed (per `.claude/rules/seam-verification.md`)

The directive adds one new cross-stage seam and touches one existing seam. Persistent home is `transcode.flow.md`'s `## Seams` table (F13 puts the new row there).

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| `Workers.AllowedProfiles -> ClaimNextPendingTranscodeJob filter` | `POST /api/TeamStatus/Workers/<name>/AllowedProfiles` (operator UI) writes `Workers.AllowedProfiles TEXT NULL` (NULL / CSV / `""`) | TEXT column; NULL OR CSV-of-profile-names | `BuildAllowedProfilesPredicate` emits `(w.AllowedProfiles IS NULL OR mf.AssignedProfile = ANY(string_to_array(w.AllowedProfiles, ',')))` | `Tests/Contract/TestWorkerAllowedProfiles.py` |
| `Profiles.Name rename/delete -> Workers.AllowedProfiles sweep` | `ProfileRepository.SaveProfile` (rename) / `DeleteProfile` | Same-transaction UPDATE sweeps every CSV containing the affected name | `BuildAllowedProfilesPredicate` continues to match on the post-sweep CSV | `Tests/Contract/TestWorkerAllowedProfiles.py::test_profile_rename_sweep` + `::test_profile_delete_sweep` |
| `Activity modal -> POST /Workers/<name>/AllowedProfiles` (existing UI surface, new field) | `Templates/Activity.html` (existing modal) | JSON `{"AllowedProfiles": ["P1","P2"] | []}` | `TeamStatusController` validates against `Profiles.Name`, normalizes, persists | Manual modal CRUD round-trip + `TestWorkerAllowedProfiles.py::test_post_endpoint_*` |

### R18 overrides

(None yet. R18 caps `*.feature.md` Reads at limit<=50; partial reads via the `## Files` index. Override entries land here when full reads are genuinely required.)

### Promotions

(Populated at DELIVERING. Source-in-directive -> target feature/flow doc + commit.)

| Source artifact | Target file | Commit |
|---|---|---|
| TBD | TBD | TBD |

### Verification

(Populated at VERIFYING; one entry per acceptance criterion C1-G14.)

### Decisions Made

(Populated during execution as ambiguities surface. Pre-populated decisions live in `## Engineering Calls Already Made` above.)
