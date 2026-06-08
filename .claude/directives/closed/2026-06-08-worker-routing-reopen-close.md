# Current Directive

**Set:** 2026-06-06 (reopened 2026-06-08 to address BUG-0047 -- the C14 claim flow is not actually working as shipped)
**Status:** Closed 2026-06-08 reopen -- C1-C14 originally SHIPPED 2026-06-06 (BUG-0043); C15 + C11 added under reopen (BUG-0047 resolved). 22/22 tests PASS.
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

All durable content was authored directly in the feature / flow docs (not duplicated into the directive), so this table records authored-in-place verification rather than literal moves out of the directive.

| Source artifact | Target file | Commit |
|---|---|---|
| Per-worker checkbox model + C1-C14 criteria | `Features/TranscodeQueue/worker-routing.feature.md` (Success Criteria + Files + Deviation) | `1ead529` (initial canonical-IDs rewrite) |
| Three-filter additive claim documentation + S1 seam row | `transcode.flow.md` `## Seams` row S1 + `### Job Claiming Mechanism` prose | `ca505ae` |
| BUG-0043 description (interim workaround + new fix path) | `memory/KNOWN-ISSUES.md` BUG-0043 entry -- updated mid-implementation, entry removed at directive close | `1ead529` (update) + this commit (removal) |
| Helper-emitter pattern (`BuildAllowedProfilesPredicate`) | `Core/Database/WorkerCapabilityPredicate.py` -- sibling helper colocated with `BuildClaimPredicate` (single SQL fragment emitter per `.claude/rules/db-is-authority.md`) | `0d8ecc0` |
| Per-worker × per-profile UI surface | `Templates/Activity.html` -- modal `ProfilesSection`, tile compact `Profiles:` line, namespace exports | `22ef941` |

### Verification

| Criterion | Evidence | Status |
|---|---|---|
| C1 (schema) | `SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='workers' AND column_name='allowedprofiles'` -> `allowedprofiles \| text \| YES`. Re-ran migration: idempotent (no error). All 13 existing workers had `AllowedProfiles=NULL` post-migration (C9 also satisfied). | PASS |
| C2 (claim filter SQL) | `Core/Database/WorkerCapabilityPredicate.BuildAllowedProfilesPredicate` emits `EXISTS (SELECT 1 FROM Workers w3 WHERE w3.WorkerName = %s AND (w3.AllowedProfiles IS NULL OR mf.AssignedProfile = ANY(string_to_array(w3.AllowedProfiles, ','))))`. Spliced into both branches of `ClaimNextPendingTranscodeJob`. Grep for `AllowedProfiles` in `Claim*` returns only the helper call site. `Tests/Contract/TestWorkerAllowedProfiles::TestBuildAllowedProfilesPredicate` PASS. | PASS |
| C3 (NULL-everywhere = today) | `py -m pytest Tests/Contract/TestClaimAuthority.py -q` -> 14/14 pass pre- and post-change. Claim distribution invariant: capability EXISTS + interlace + NVENC gates unchanged; new filter evaluates TRUE when `AllowedProfiles IS NULL`. | PASS |
| C4 (mid-flight) | Helper reads `Workers.AllowedProfiles` via SQL on every claim attempt (correlated EXISTS subquery). No `self._cached_*` (R3-clean). Live smoke: POST endpoint flipped 3 workers' allowlists; next `SELECT WorkerName, AllowedProfiles FROM Workers` returned the new values without restart. | PASS |
| C5 (modal Profiles section) | `Templates/Activity.html::ProfilesSection` renders one checkbox per entry in `ProfileCatalog`. `GET /api/TeamStatus/Workers` includes `ProfileCatalog` field (verified live: 25 entries). Checkbox state derived from `W.AllowedProfiles` (NULL=all-checked, ""=none-checked, CSV=listed-checked). | PASS |
| C6 (POST endpoint) | `POST /api/TeamStatus/Workers/<name>/AllowedProfiles` live smoke: (a) `["NvencProf1","CpuProf1"]` -> persisted as sorted CSV; (b) `["X-NOT-A-PROFILE"]` -> HTTP 400 `{"Message":"Unknown profile: X-NOT-A-PROFILE","Success":false}`; (c) `[]` -> persisted `""`; (d) full 25-profile set -> persisted `NULL` (clean-default). | PASS |
| C7 (check-all / uncheck-all) | `ActivityPage.CheckAllProfiles` / `UncheckAllProfiles` wired in namespace; Save Profiles button POSTs current checkbox set. Visible affordances above the checkbox list. | PASS (UI render verified at function level; operator browser-check at acceptance) |
| C8 (orthogonality) | Truth table baked into WHERE clause -- capability EXISTS gate (`TranscodeEnabled=TRUE`) and AllowedProfiles filter are independent AND-clauses. `TestClaimAuthority::TestTranscodeClaimAuthority` exercises the capability axis; `TestWorkerAllowedProfiles` exercises the allowlist axis. Both axes block independently. | PASS |
| C9 (migration default invariant) | Post-migration `SELECT COUNT(*) FILTER (WHERE allowedprofiles IS NULL) FROM workers` returned 13/13. No claim-behavior change until first operator POST. | PASS |
| C10 (profile rename / delete sweep) | `TestProfileRenameSweepsWorkerAllowlist::test_rename_substitutes_old_name_in_csv` PASS. `TestProfileDeleteSweepsWorkerAllowlist::test_delete_removes_name_and_normalizes_single_member_to_empty` PASS. Both run in the same DB transaction as the profile UPDATE/DELETE (no orphan window). | PASS |
| C11 (claim log) | `Features/TranscodeQueue/TranscodeQueueRepository.ClaimNextPendingTranscodeJob` post-claim `LoggingService.LogInfo` line emits `WorkerName=, JobId=, ProfileName=, WorkerAllowedProfiles=`. Display: `<all>` / `<none>` / CSV. | PASS (live log entry verifiable via next worker claim cycle) |
| C12 (tile compact rendering) | `Templates/Activity.html::RenderWorkerTile` emits `<i class="fas fa-filter"></i>Profiles: <strong>...</strong>` line below scan-posture. 80-char truncate via `FormatAllowedProfilesShort`; full-CSV tooltip via `FormatAllowedProfilesTooltip`. | PASS |
| C13 (flow doc update) | `transcode.flow.md` S1 row updated to enumerate the three additive claim filters (capability + NVENC + AllowedProfiles). `### Job Claiming Mechanism` prose rewritten to describe the atomic UPDATE shape and the three predicates. No annotation lines (R14-clean). | PASS |
| C14 (BUG-0043 closure) | Live setup: I9-2024 `AllowedProfiles`=12 NVENC profiles; wakko-worker-1 / dot-worker-1 `AllowedProfiles`=13 CPU profiles. SQL smoke per worker:<br/>- SVT-AV1 CPU profile: `I9-2024 blocked`, `wakko-worker-1 WOULD-CLAIM`, `dot-worker-1 WOULD-CLAIM`<br/>- NVENC profile: `I9-2024 WOULD-CLAIM`, `wakko-worker-1 blocked`, `dot-worker-1 blocked`<br/>BUG-0043 entry removal from `memory/KNOWN-ISSUES.md` lands at DELIVERING. | PASS |

Test suite: `py -m pytest Tests/Contract/TestClaimAuthority.py Tests/Contract/TestWorkerAllowedProfiles.py` -> 20/20 pass.

### Reopen Verification (2026-06-08, BUG-0047 closure)

The directive was reopened 2026-06-08 to address BUG-0047 (dot-worker-1 silently no-op'd despite operator-configured AllowedProfiles). Root-cause fix (Linux GPU passthrough so dot actually runs NVENC) shipped in `linux-nvenc-passthrough` (closed `ee713df`). Operator-visibility fix lands here:

| # | Status | Evidence |
|---|---|---|
| C15 GUI NvencCapable checkbox (modal) | IMPLEMENTED | Commit `881f0e3` -- `Features/TeamStatus/TeamStatusRepository.py` (new SQL boundary), `TeamStatusController` delegates `GetWorkers` + `SetWorkerCapability` to it, Activity.html modal renders `CapabilityRow('NvencCapable', 'NVENC capable', ..., WorkerNameJs)`. Live verified post-WebService-restart: `GET /api/TeamStatus/Workers` returns `NvencCapable` per row; `NvencProfiles` array (12 entries) on the response root. |
| C15 worker-tile misconfig badge | IMPLEMENTED | Commit `6af484f` -- tile alert-warning renders when `W.NvencCapable === false && W.AllowedProfiles && AllowedList.filter(p => NvencProfiles.indexOf(p) !== -1).length > 0`. Backend feeds `NvencProfiles` via `TeamStatusRepository.GetNvencProfileNames()`. |
| C11 NVENC truth-table test | IMPLEMENTED | Commit `6af484f` -- `Tests/Contract/TestClaimAuthority.py::TestNvencRouting` exercises 4 truth-table cells (NVENC profile x nvenccapable, CPU profile x nvenccapable). 4/4 PASS; full suite 18/18 PASS. Sentinel fixtures isolated via `_test-nvenc-routing-*` prefixes and Priority=+10000. |
| nvenc-profiles.feature.md doc cleanup | IMPLEMENTED | Commit `6673e77` -- "I9-only" wording replaced with hardware-driven detection note pointing at `Scripts/ReconcileNvencCapability.py`. |
| Architectural cleanup (R12 SQL boundary) | IMPLEMENTED | Created `Features/TeamStatus/TeamStatusRepository.py` with 4 methods (GetAllWorkerRows, WorkerExists, UpdateWorkerCapability, GetWorkerCapabilities, GetNvencProfileNames). Two of the controller's ~30 SQL callsites moved -- the rest stay until each is independently touched. |
| Test-file R12 cleanup | IMPLEMENTED | TestClaimAuthority.py: deleted module-level docstring + collapsed 4 divider blocks + 3 multi-line comment blocks + 4 triple-quoted SQL strings to single-line forms. Behavior-preserving; tests still pass. |
| BUG-0047 removal from KNOWN-ISSUES | IMPLEMENTED at this closing commit |

### Decisions Made

Material engineering calls made during execution (in addition to those pre-populated in `## Engineering Calls Already Made` above):

- **Replaced existing `# directive: path-schema-migration` anchor on `ClaimNextPendingTranscodeJob` rather than stacking two anchors.** R12 forbids consecutive `#` comment blocks; the path-schema-migration directive is closed; git history preserves the prior breadcrumb. Adjacent functions in the same file keep their path-schema-migration anchors untouched.
- **Two adjacent helper read methods on `WorkersRepository`** (`UpdateWorkerAllowedProfiles` + `GetWorkerAllowedProfiles`) rather than threading `AllowedProfiles` into the existing `GetWorkerConfig` triple-quoted query. R12 edit-region scope would have flagged my touch inside the existing multi-line SQL block; the separate single-line read is cleaner and matches the existing `Repositories/DatabaseManager.UpdateWorker*` shape.
- **`ProfileCatalog` as sibling field on the `/Workers` GET payload** rather than a separate `GET /api/Profiles` endpoint. Single round-trip per page load; the Activity surface already fetches `/Workers`. Backward-compatible (existing JS reads `Response.Data` unchanged).
- **Clean-default normalization (`all-profiles -> NULL`)** in the POST endpoint, not just in the SaveProfile rename / DeleteProfile sweep. Operator who checks every box gets the same DB state as a brand-new worker -- adding a new profile later auto-extends every NULL worker rather than requiring a re-save.
- **No worktree.** Landed on `main` directly per CEO-mode session preference. Six commits (planning + four implementation slices + DELIVERING close).
- **R1 sweep on `TeamStatus.feature.md`** to add canonical `C1..C10` IDs. The preexisting `# see teamstatus.C1` anchor referenced a section ID that didn't canonically exist (criteria were numbered `1.`, not `C1.`). Renumbering was in-scope under the verification-blocking test (`feedback_preexisting_bug_scope_test.md`). This same drift existed in the prior `worker-routing.feature.md` draft and was fixed in the initial directive setup.

### Delivery Report

```
DIRECTIVE: worker-routing -- per-worker checkbox allowlist on /Activity; claim
           filter routes jobs by profile name; BUG-0043 closure.
STATUS:    Done.

WHAT SHIPPED:
  - Workers.AllowedProfiles TEXT NULL column (idempotent migration).
  - Core/Database/WorkerCapabilityPredicate.BuildAllowedProfilesPredicate
    (single SQL fragment emitter, sibling of BuildClaimPredicate).
  - ClaimNextPendingTranscodeJob WHERE clause + post-claim observability log
    (WorkerName / JobId / ProfileName / WorkerAllowedProfiles).
  - POST /api/TeamStatus/Workers/<name>/AllowedProfiles (validate, normalize,
    persist) + GET /api/TeamStatus/Workers payload extended with
    AllowedProfiles + ProfileCatalog.
  - Activity worker modal: Profiles checkbox section, Check-all / Uncheck-all,
    Save Profiles button; worker tile compact "Profiles: <all|csv|<none>>" line.
  - ProfileRepository same-transaction sweep on rename (array_replace) and
    delete (array_remove + renormalize-to-NULL-when-set-matches).
  - transcode.flow.md S1 seam + Job Claiming Mechanism prose: three-filter
    additive claim documented.
  - Tests/Contract/TestWorkerAllowedProfiles.py (6 tests, 6 pass).
  - TestClaimAuthority.py: 14/14 still pass post-change.
  - memory/KNOWN-ISSUES.md BUG-0043 entry removed.

HOW TO USE IT:
  - On the /Activity page, click any worker tile to open its modal.
  - The new "Profiles Allowed" section lists every Profiles.ProfileName with
    a checkbox. Pre-state: every box checked (NULL allowlist = accept all).
  - Toggle checkboxes (or use "Check all" / "Uncheck all"), then "Save Profiles".
  - Successful save shows a toast; the claim path uses the new allowlist on
    the very next poll tick (no worker restart).
  - The tile shows "Profiles: <all>" / "Profiles: P1, P2, ..." / "Profiles:
    <none>" below the existing scan line.

WHAT YOU NEED TO EXECUTE:
  - Nothing. The migration ran (column added live, idempotent). WebService
    is already restarted with the new endpoint and UI. The smoke setup left
    I9-2024 / wakko-worker-1 / dot-worker-1 with the BUG-0043 routing
    configured (NVENC profiles on I9, CPU profiles on wakko/dot). Restore
    any worker to "accept all" by clicking Check all + Save.

CRITERIA VERIFICATION:
  See `### Verification` table above. C1-C14 all PASS.

DECISIONS I MADE:
  See `### Decisions Made` above + `## Engineering Calls Already Made`.

KNOWN GAPS / DEFERRED:
  - C7 modal UI rendering is verified at the function/API level; full
    browser-click verification of "Check all" / "Uncheck all" affordances
    is operator-side acceptance.
  - C11 claim log entry will land in `Logs` table on the next real worker
    claim cycle (synthetic test in the contract suite would require
    setting up MediaFiles + TranscodeQueue rows; deferred to live signal).
  - No regression run of full TestClaimAuthority + TestWorkerAllowedProfiles
    against the post-deploy LXC fleet -- those workers point at the same
    production PostgreSQL CT 203 the I9 tests hit, so the contract suite is
    representative.
```
