# Current Directive

**Set:** 2026-06-06
**Status:** Active -- phase: IMPLEMENTING
**Slug:** worker-routing
**Replaces:** `.claude/directives/paused/2026-06-06-db-maintenance-no-partition.md` (paused mid-IMPLEMENTING; one artifact remaining = `Tests/Contract/TestMaintenanceBaseline.py`; resume by un-pausing after worker-routing closes)

## Outcome

The operator can pin each worker to a specific subset of `Profiles` via per-worker checkboxes on the `/Activity` modal. The TranscodeQueue claim path filters Pending rows to the calling worker's allowlist. Today's "every transcode-enabled worker is interchangeable" race becomes a per-machine routing decision that takes two clicks to set up and two clicks to change -- including when a new NVENC card lands on a different host later this week. BUG-0043 (NVENC-capable i9 grabbing CPU-only SVT-AV1 jobs) closes as the operator unchecks SVT profiles on i9.

The full criteria contract lives in `Features/TranscodeQueue/worker-routing.feature.md` (C1-G14, last edited this directive). This directive doc accretes design rationale, in-flight state, and verification evidence; promotions at DELIVERING move durable content back to the feature doc and `transcode.flow.md`.

## Acceptance Criteria

Authoritative: `Features/TranscodeQueue/worker-routing.feature.md` sections A-G (14 criteria). Restated here in compact form for the hook + reviewer:

1. **A1.** `Workers.AllowedProfiles TEXT NULL` via idempotent migration `Scripts/SQLScripts/AddWorkerAllowedProfiles.py`. NULL = accept all. CSV = explicit allowlist. `""` = accept none.
2. **B2.** `ClaimNextPendingTranscodeJob` WHERE clause gains `(w.AllowedProfiles IS NULL OR mf.AssignedProfile = ANY(string_to_array(w.AllowedProfiles, ',')))`. Single emitter in `Core/Database/WorkerCapabilityPredicate.BuildAllowedProfilesPredicate`.
3. **B3.** NULL-everywhere = today's behavior. EXPLAIN plan parity + 30-min parallel-claim soak within 5% of baseline.
4. **B4.** Mid-flight changes honored within one poll tick (db-is-authority -- no boot cache).
5. **C5.** `/Activity` worker modal renders one checkbox per `Profiles.Name`, state reflects current `AllowedProfiles` (all-checked when NULL, listed when CSV, none when `""`).
6. **C6.** `POST /api/TeamStatus/Workers/<name>/AllowedProfiles` validates against `Profiles.Name` (400 on unknown), normalizes (sort/dedupe; empty list -> `""`; all profiles -> NULL).
7. **C7.** Check-all / Uncheck-all affordances above checkbox list.
8. **C8.** Orthogonality truth table: capability switch AND allowlist must both permit to claim.
9. **D9.** Migration leaves every existing Worker at `AllowedProfiles=NULL` (no behavior change until operator saves).
10. **D10.** Profile rename / delete sweeps every `Workers.AllowedProfiles` CSV in the same transaction.
11. **E11.** Claim log row includes `WorkerName`, `JobId`, `ProfileName`, `WorkerAllowedProfiles` (`<all>` / `<none>` / CSV).
12. **E12.** Worker tile compact one-line rendering of allowlist below capability row (80-char truncate + tooltip).
13. **F13.** `transcode.flow.md` updates land in two places: (a) the `## Seams` table S1 row (transition `ST5 -> ST6`) is extended to mention the AllowedProfiles filter as a second gating condition on the claim, OR a new S6 row is added for `Workers.AllowedProfiles -> claim filter` -- engineering call at edit time, single-row preferred; (b) the `### Job Claiming Mechanism` prose subsection under `## Service Architecture` notes the new WHERE-clause filter alongside the existing FOR UPDATE SKIP LOCKED note. The earlier draft's "Stage 2 (ST2)" reference was wrong -- ST2 is PROBE; the claim path is the S1 seam at `ST5 -> ST6`.
14. **G14.** BUG-0043 smoke (i9 unchecks SVT profiles -> wakko/dot claim the row within one tick); `memory/KNOWN-ISSUES.md` BUG-0043 entry removed at directive close.

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

```
Scripts/SQLScripts/AddWorkerAllowedProfiles.py               -- NEW: idempotent ADD COLUMN IF NOT EXISTS Workers.AllowedProfiles TEXT NULL
Core/Database/WorkerCapabilityPredicate.py                   -- ADD BuildAllowedProfilesPredicate sibling helper
Features/TranscodeQueue/TranscodeQueueRepository.py          -- ClaimNextPendingTranscodeJob WHERE clause + helper call (R19 home for Claim* methods)
Features/Workers/WorkersRepository.py                        -- ADD UpdateWorkerAllowedProfiles; extend worker payload with AllowedProfiles
Features/TranscodeJob/ProcessTranscodeQueueService.py        -- pass worker name into claim call (helper reads AllowedProfiles fresh)
Features/TeamStatus/TeamStatusController.py                  -- NEW: POST /api/TeamStatus/Workers/<name>/AllowedProfiles; extend /Workers GET payload
Features/Profiles/ProfileRepository.py                       -- sweep Workers.AllowedProfiles on profile rename / delete (same-tx)
Templates/Activity.html                                      -- worker modal Profiles section (checkbox list + Check/Uncheck-all); tile compact rendering
Tests/Contract/TestWorkerAllowedProfiles.py                  -- NEW: claim filter, orthogonality, mid-flight change, profile rename/delete sweep, clean-default normalization
transcode.flow.md                                            -- Stage 2 (ST2) WHERE clause + Seams row
memory/KNOWN-ISSUES.md                                       -- update BUG-0043 mid-implementation; remove entry at directive close
Features/TranscodeQueue/worker-routing.feature.md             -- the contract; Progress checklist marked off as criteria land; Status -> SHIPPED at DELIVERING
```

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
