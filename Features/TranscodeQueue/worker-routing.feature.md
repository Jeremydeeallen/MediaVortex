# Worker Routing -- per-worker profile allowlist

**Slug:** worker-routing

## Interrupts: path-schema-migration

## What It Does

Adds a per-worker profile allowlist to the queue-claim path. Each worker in the `/Activity` page modal exposes a checkbox list of every profile in the system. The operator checks the profiles a given worker is allowed to claim; the worker's claim query filters TranscodeQueue rows to those profiles. A worker with no allowlist set (NULL -- the migration default) accepts every profile, preserving today's behavior.

This is not a load balancer or a least-loaded scheduler. It is a routing layer: "this worker may claim jobs only for these profiles." Combined with the existing capability flags (`TranscodeEnabled`, `nvenccapable`), the operator can pin NVENC profiles to NVENC-capable hardware and CPU profiles to CPU workers in two clicks per machine -- and re-pin in two clicks when a new card lands on a different machine.

## Concern

Operator dogfood -- 2026-05-09 through 2026-06-06. Today's claim model treats every transcode-enabled worker as interchangeable: whoever wins the `SELECT FOR UPDATE SKIP LOCKED` race claims the next-priority job, regardless of whether the job belongs on that hardware. Concrete case (BUG-0043): NVENC-capable i9 grabs the first CPU-only SVT-AV1 row that reaches the top of the queue, burning 20+ minutes of GPU-worker compute on work the CPU-only fleet (wakko / dot) could have done instead. A second NVENC card is landing on a new machine within the week, so the routing surface must be reconfigurable per-machine without code changes.

The earlier draft of this feature proposed a tag-based indirection (workers carry tags, profiles declare required / preferred tags). The operator has chosen the more direct model: a per-worker × per-profile boolean matrix exposed as checkboxes. Indirection is removed; the operator's mental model and the data model match.

## Success Criteria

### A. Schema

C1. `Workers` table gains a nullable `AllowedProfiles TEXT` column via idempotent migration `Scripts/SQLScripts/AddWorkerAllowedProfiles.py`. NULL is the migration default and means "this worker accepts every profile" (backward-compatibility invariant). A non-NULL value is a comma-separated list of `Profiles.Name` strings; only listed profiles are claimable by this worker. Empty string `""` is a legal state and means "this worker accepts no profile" (operator can park a worker without disabling its capability flags). Verifiable: `\d Workers` shows the column; re-running the migration is a no-op.

### B. Claim algorithm

C2. `ClaimNextPendingTranscodeJob` (in `Features/TranscodeQueue/TranscodeQueueRepository.py`) adds the filter
   ```sql
   (w.AllowedProfiles IS NULL
    OR mf.AssignedProfile = ANY(string_to_array(w.AllowedProfiles, ',')))
   ```
   to the WHERE clause of the inner SELECT. The new filter composes additively with all existing filters: the worker-capability EXISTS gate (`Core/Database/WorkerCapabilityPredicate.py`), the `AcceptsInterlaced` filter, `Status='Pending'`, `Priority DESC, DateAdded ASC` ordering. A single place in the code emits this fragment -- the sibling helper `BuildAllowedProfilesPredicate` in `Core/Database/WorkerCapabilityPredicate.py`. Verifiable: grep for `AllowedProfiles` in any `Claim*` function returns only the helper call site; with worker A allowed `[P1,P2]` and worker B allowed `[P3]`, a Pending row with `AssignedProfile=P3` is claimed only by B; rows with profile P1 are claimed only by A; rows with profile P4 (in neither allowlist) sit unclaimed indefinitely.

C3. **NULL-everywhere = today's behavior.** When every worker has `AllowedProfiles IS NULL`, the new clause evaluates `TRUE` for every row and the query plan / claim distribution match today's. Verifiable: `EXPLAIN (ANALYZE, BUFFERS)` on the new query with no allowlists set produces a plan with the same join shape as the pre-change query; a 30-minute parallel-claim soak with three workers and no allowlists shows per-worker claim counts within 5% of a pre-change baseline.

C4. **Mid-flight changes honored within one poll tick.** Per `.claude/rules/db-is-authority.md`, the column is read fresh on every claim attempt -- no boot cache, no per-worker instance variable. Operator unchecks profile P on worker W via the modal at T; W's next claim cycle (<= poll-tick seconds after T) skips rows with `AssignedProfile=P`. Verifiable: queue 5 P-profile jobs; flip W's allowlist mid-claim; confirm via `TranscodeAttempts.workername` query that W stopped claiming P within one tick.

### C. Operator surface

C5. The `/Activity` page worker modal gains a "Profiles" section rendering one checkbox per row in `SELECT Name FROM Profiles ORDER BY Name`. Checkbox state reflects the worker's current `AllowedProfiles`: every box checked when NULL; only listed profiles checked when CSV is set; no boxes checked when empty string. Verifiable: open the modal for any worker; count checkboxes equals `SELECT COUNT(*) FROM Profiles`; add a new profile via the profile editor and reload the modal -- the new profile appears (checked for NULL allowlists, unchecked for explicit CSV allowlists).

C6. Saving the checkbox state issues `POST /api/TeamStatus/Workers/<name>/AllowedProfiles` with body `{"AllowedProfiles": ["P1","P2"]}`. The endpoint:
   - rejects names not present in `Profiles.Name` with HTTP 400 `{"Success": false, "Message": "Unknown profile: <name>"}`. Persisted value unchanged on rejection.
   - sorts and dedupes the input (case-sensitive -- profile names are PascalCase per CLAUDE.md).
   - persists the empty list as the empty string `""`.
   - persists a list containing every existing profile as `NULL` (clean-default invariant: "all checked" normalizes to "no restriction").
   - returns `{"Success": true, "Data": {"AllowedProfiles": "<csv|null>"}}`.

   Verifiable: POST `["P1","X-DOES-NOT-EXIST"]`; response is 400 with the unknown name in the message; `Workers.AllowedProfiles` is unchanged. POST the full set of existing profile names; `Workers.AllowedProfiles IS NULL` after.

C7. The modal Profiles section includes "Check all" and "Uncheck all" affordances above the checkbox list. "Check all" sets every checkbox and submits (endpoint normalizes to NULL). "Uncheck all" clears every checkbox and submits as `""`. Operator flips a worker's policy wholesale in one click without scrolling.

C8. The capability switches (TranscodeEnabled / QualityTestEnabled / RemuxEnabled / ScanEnabled) and the AllowedProfiles checkboxes are independent and orthogonal. Truth table:

   | TranscodeEnabled | AllowedProfiles | Claims transcode rows? |
   |---|---|---|
   | FALSE | any | NO |
   | TRUE | NULL | YES, any profile |
   | TRUE | CSV `[P1,P2]` | YES, only P1/P2 rows |
   | TRUE | `""` | NO |

   Verifiable: contract test exercises all four rows against a synthetic queue.

### D. Backward compatibility and referential integrity

C9. Migration leaves every existing `Workers` row with `AllowedProfiles=NULL`. No worker's claim behavior changes until the operator explicitly saves a non-default list. Verifiable: per-worker claim rate over a 1-hour window pre-migration vs. post-migration is within noise.

C10. **Profile rename / delete sweeps the allowlist in the same transaction.** When a `Profiles` row is renamed or deleted via `ProfileRepository`, every `Workers.AllowedProfiles` CSV is rewritten in the same DB transaction: rename substitutes the new name in place; delete removes the name from the CSV (and renormalizes empty -> `""`, all -> `NULL`). No orphaned references survive. Verifiable: rename profile `P1` -> `P1Renamed`; query `SELECT WorkerName, AllowedProfiles FROM Workers WHERE AllowedProfiles LIKE '%P1%' ESCAPE '!'`; the old name does not appear; the new name does where the old one used to.

### E. Observability

C11. `ClaimNextPendingTranscodeJob` log entry on a successful claim includes `WorkerName`, `JobId`, `ProfileName`, `WorkerAllowedProfiles` (the literal string `<all>` when NULL, `<none>` when empty, the CSV otherwise). One log row per claim. Verifiable: query `SELECT Message FROM Logs WHERE FunctionName='ClaimNextPendingTranscodeJob' ORDER BY TimeStamp DESC LIMIT 1`; all four fields appear.

C12. The `/Activity` worker tile shows a compact one-line rendering of the current allowlist below the capability row: `Profiles: <all>` when NULL, `Profiles: P1, P2, P3` when CSV, `Profiles: <none>` when empty. Truncates to 80 characters with a tooltip showing the full list. Verifiable: visual check across the three states; tooltip shows untruncated value.

### F. Flow doc update

C13. `transcode.flow.md` updates land in two places: (a) the `## Seams` table S1 row (transition `ST5 -> ST6`) is extended to mention the AllowedProfiles filter alongside the existing `nvenccapable` gate, OR a new row S6 is added for `Workers.AllowedProfiles -> claim filter` -- engineering call at edit time, single-row preferred; (b) the `### Job Claiming Mechanism` prose subsection under `## Service Architecture` notes the new WHERE-clause filter alongside the existing `SELECT FOR UPDATE SKIP LOCKED` note. Verifiable: `git diff transcode.flow.md` shows both edits.

### G. Bug closure

C14. **[BUG-0043] resolution.** With i9 configured `AllowedProfiles = <every NVENC profile name>` and wakko / dot configured `AllowedProfiles = <every CPU profile name>`, a queued SVT-AV1 row is claimed by wakko or dot within one poll tick; i9 sits idle if no NVENC work is pending. The Priority-based interim workaround is removed from `memory/KNOWN-ISSUES.md`; the BUG-0043 entry itself is removed at directive close. Verifiable: synthetic test queue with one SVT-AV1 row; observe `TranscodeAttempts.workername` after one tick.

C15. **[BUG-0047] dot-worker-1 not claiming NVENC despite operator config.** When operator configures `dot-worker-1` with `TranscodeEnabled=TRUE` + `AllowedProfiles` containing NVENC profile name(s), ONE of two outcomes MUST hold per the C8 truth table: (a) `dot-worker-1` claims and processes the next matching NVENC `TranscodeQueue.Pending` row within one poll tick, OR (b) the `/Activity` worker modal surfaces a structured gating-reason badge (e.g. `nvenccapable=FALSE -- this worker cannot claim NVENC profiles`, `worker offline`, `WorkerService process not running`) so the operator understands why claims aren't happening. Silent non-claim violates the C8 truth-table promise. Verifiable: configure dot-worker-1 per operator's stated config; queue one NVENC profile row; within one tick either `TranscodeAttempts.WorkerName='dot-worker-1'` exists, OR the `/Activity` modal for dot-worker-1 shows a non-default gating-reason badge naming the actual blocker.

## Status

SHIPPED 2026-06-06 -- BUG-0043 closed.

### Progress

- [x] Read prior issues (`memory/KNOWN-ISSUES.md` -- BUG-0043 confirmed)
- [x] Surveyed existing claim path (`Features/TranscodeQueue/TranscodeQueueRepository.py`, `Core/Database/WorkerCapabilityPredicate.py`, `transcode.flow.md` S1 seam)
- [x] Drafted feature doc against per-worker checkbox model (this file)
- [x] Update BUG-0043 description in `memory/KNOWN-ISSUES.md` to reference the checkbox model
- [x] Operator approval (CEO mode opened the directive)
- [x] Implement C1 (Workers.AllowedProfiles column + migration script)
- [x] Implement C2-C4 (claim filter helper, claim query rewrite, parameter plumbing in WorkerService -> claim call)
- [x] Implement C5-C8 (Activity tile Profiles section, POST endpoint, Check/Uncheck-all affordances, orthogonality contract test)
- [x] Implement C9-C10 (migration default invariant, profile rename/delete sweep in ProfileRepository)
- [x] Implement C11-C12 (extended claim log, worker tile compact rendering)
- [x] Implement C13 (transcode.flow.md S1 + Job Claiming Mechanism update)
- [x] Implement C14 (BUG-0043 smoke -- I9 NVENC-only / wakko-dot CPU-only; KNOWN-ISSUES entry removed)

## Scope

```
Scripts/SQLScripts/AddWorkerAllowedProfiles.py               -- NEW: idempotent ADD COLUMN IF NOT EXISTS Workers.AllowedProfiles TEXT NULL
Core/Database/WorkerCapabilityPredicate.py                   -- ADD: BuildAllowedProfilesPredicate sibling helper
Features/TranscodeQueue/TranscodeQueueRepository.py          -- ClaimNextPendingTranscodeJob WHERE clause + helper call (R19 home for Claim* methods)
Features/Workers/WorkersRepository.py                        -- ADD UpdateWorkerAllowedProfiles; extend GetWorkerConfig / worker payload with AllowedProfiles
Features/TranscodeJob/ProcessTranscodeQueueService.py        -- pass worker name into claim call (helper reads AllowedProfiles fresh)
Features/TeamStatus/TeamStatusController.py                  -- NEW: POST /api/TeamStatus/Workers/<name>/AllowedProfiles; extend /Workers payload
Features/Profiles/ProfileRepository.py                       -- sweep Workers.AllowedProfiles on profile rename / delete (same-tx)
Templates/Activity.html                                      -- worker modal Profiles section (checkbox list + Check/Uncheck-all); tile compact rendering
Tests/Contract/TestWorkerAllowedProfiles.py                  -- NEW: claim filter, orthogonality, mid-flight change, rename sweep
transcode.flow.md                                            -- S1 seam row + Job Claiming Mechanism prose
memory/KNOWN-ISSUES.md                                       -- update BUG-0043 mid-implementation; remove entry at directive close
```

## Files

| File | Role |
|---|---|
| `Scripts/SQLScripts/AddWorkerAllowedProfiles.py` | NEW. Idempotent `ALTER TABLE Workers ADD COLUMN IF NOT EXISTS AllowedProfiles TEXT NULL`. |
| `Core/Database/WorkerCapabilityPredicate.py` | ADD `BuildAllowedProfilesPredicate(WorkerName) -> (sql_fragment, params)`. Single emitter for the `(w.AllowedProfiles IS NULL OR mf.AssignedProfile = ANY(...))` fragment. |
| `Features/TranscodeQueue/TranscodeQueueRepository.py` | `ClaimNextPendingTranscodeJob` adds a LEFT JOIN to `MediaFiles` (if not already present for the call shape) and calls the new helper to extend WHERE. Existing capability EXISTS gate untouched. R19 home for `Claim*` methods. |
| `Features/Workers/WorkersRepository.py` | ADD `UpdateWorkerAllowedProfiles(WorkerName, AllowedProfilesCsv\|None)`. Extend `GetWorkerConfig` / worker payload to expose `AllowedProfiles`. |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py` | At `GetNextJob`, pass worker name into the claim call. Helper reads `Workers.AllowedProfiles` fresh -- no instance cache. |
| `Features/TeamStatus/TeamStatusController.py` | NEW endpoint `POST /api/TeamStatus/Workers/<name>/AllowedProfiles`. Validates against `Profiles.Name`, normalizes (sort/dedupe/empty-vs-null/all-vs-null), UPDATEs `Workers.AllowedProfiles`. Extends `GET /api/TeamStatus/Workers` payload with `AllowedProfiles`. |
| `Features/Profiles/ProfileRepository.py` | On profile rename / delete, sweep `Workers.AllowedProfiles` in the same transaction. |
| `Templates/Activity.html` | Worker modal: Profiles section with checkbox per profile, "Check all" / "Uncheck all" affordances. Worker tile: compact `Profiles: <all\|csv\|<none>>` line below capability row. |
| `Tests/Contract/TestWorkerAllowedProfiles.py` | NEW. Asserts claim filter, orthogonality truth table (C8), mid-flight change honored within one tick, profile rename / delete sweep, clean-default normalization. |
| `transcode.flow.md` | S1 seam row extended (or S6 added) for `Workers.AllowedProfiles -> claim filter`; `### Job Claiming Mechanism` prose updated. |
| `memory/KNOWN-ISSUES.md` | BUG-0043 description updated mid-implementation; entry removed at directive close once C14 verified. |

## Deviation from conventions

Criterion C2 quotes the SQL fragment shape directly. Normally criteria avoid implementation detail, but the routing rule **is** the SQL clause -- the precise composition (`IS NULL OR ANY(string_to_array(...))`) is what changes claim semantics, and prose paraphrase loses the verifiability the operator depends on. Each behavioural assertion (filter applies, NULL-everywhere = today, mid-flight change honored, orthogonality with capability flags) is also stated independently and is each independently testable without reading the SQL.
