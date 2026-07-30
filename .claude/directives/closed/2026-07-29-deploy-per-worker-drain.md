# Deploy Per-Worker Drain

**Slug:** deploy-per-worker-drain
**Set:** 2026-07-29 (pivot; parent: deploy-worker-identity-invariants)
**Status:** Active -- phase: DELIVERING

## Interrupts: deploy-worker-identity-invariants

## Outcome

Every worker service deploy follows the same shape: pause -> drain -> deploy -> back Online. Per-service, not per-host. No opt-out. Codified as a project-wide rule; existing scripts + docs that conflict are retrofit or deleted.

## Domain Decisions (locked; operator-owned)

- **D1.** After worker code complete: commit + push.
- **D2.** Deploy per-service independently. Services do not wait on each other.
- **D3.** Every service treated identically.
- **D4.** Per-service sequence: pause -> drain (no more active jobs) -> deploy -> back Online.
- **D5.** Only DB touch is `Workers.Status` (pause via existing pause feature; set Online after deploy). No other DB writes for the worker.
- **D6.** Each step in the per-service sequence is timed. Elapsed for that step is printed to stdout live as the step completes. Final line prints the total elapsed from pause-start to back-Online.

## Definitions

- **Service** = one `Workers` row. `larry-worker-1` and `larry-worker-2` are two services on one docker host; each drained + deployed independently.
- **Drained** = `Workers.Status='Paused'` AND `SELECT COUNT(*) FROM ActiveJobs WHERE WorkerName=<name>` = 0 AND `SELECT COUNT(*) FROM ScanJobs WHERE WorkerName=<name> AND Status IN ('Pending','Running','Stopping')` = 0.

## Non-Goals

- Fleet-batch atomic deploy semantics. Removed.
- Any `--no-drain`, `--skip-drain`, `--force` flag on any deploy path. Removed.
- DB writes to Workers columns other than `Status` during deploy.

## Acceptance Criteria

C1. **Golden-standard rule exists.** `.claude/rules/worker-deploy-drain.md` names D1-D5, the definition of "drained", and the forbidden list (no opt-out flags, no batch-pause, no non-Status DB writes). Auto-loaded per `CLAUDE.md` framework-rules glob.

C2. **`--no-drain` opt-out deleted.** No `--no-drain`, `--skip-drain`, or equivalent flag exists in any file under `deploy/`. Grep across the tree returns zero matches. Any doc that mentioned the flag is updated.

C3. **`worker-deploy.feature.md` reflects the golden standard.** Doc's Surface + Success Criteria sections describe per-service drain-deploy-online, not host-batch. Every drain-optional or fleet-atomic phrasing is deleted.

C4. **New tool: `deploy/deploy-worker.py <worker-name>`.** Single-service driver. Given a WorkerName (e.g. `larry-worker-3`), it:
- pauses that worker via `Workers.Status='Paused'`
- polls until ActiveJobs=0 + no Running/Pending/Stopping ScanJobs for that worker (timeout configurable, default 30 min)
- dispatches to the correct backend (docker-compose per-service restart, baremetal systemd unit restart, or windows task action) based on `Workers.Platform` + host inventory
- verifies the target service is running new code (Workers.Version matches HEAD)
- sets `Workers.Status='Online'`
- exits 0 on success, non-zero + named failure otherwise
No other DB writes. No touching of sibling workers on the same host.

C5. **Fleet driver becomes a thin loop over C4.** `deploy/deploy-fleet.py` (or its replacement) iterates target WorkerNames and invokes the per-service driver. Parallelism across services allowed (D2 -- services do not wait on each other). No aggregate-pause of a host.

C6. **Contract test.** `Tests/Contract/TestDeployPerWorkerDrain.py` asserts:
- `deploy/deploy-worker.py --help` exits 0 and mentions no bypass flags
- grep of `deploy/**/*.py` returns zero hits for `no-drain|skip-drain|no_drain|skip_drain`
- `deploy/worker-deploy.feature.md` contains the string "pause -> drain -> deploy -> back Online" (or equivalent phrasing anchored on D4)
- `.claude/rules/worker-deploy-drain.md` exists and is non-empty

C7. **Smoke on larry.** Run `py deploy/deploy-worker.py larry-worker-3`. Confirm: worker flips Paused -> Online, ActiveJobs stayed 0 throughout, no writes to Workers columns other than Status (verify via before/after column diff), sibling workers (1/2/4) untouched.

C20. **Timings per step, live.** `deploy-worker.py` prints each step's elapsed on the same line the step completes (e.g. `[1/6] pause: larry-worker-3 (0.1s)`). Final line: `=== OK <name> back Online in <total>s (pause=X, drain=Y, deploy=Z, verify=W) ===`. Timings visible to operator running the tool live AND captured in stdout for fleet loop consumption. Contract test asserts the total-timing pattern in `--help`-safe form.

## Call-Graph Audit

- Flow docs touching deploy: `deploy/worker-deploy-linux.flow.md`, `deploy/worker-deploy-baremetal.flow.md`, `deploy/worker-deploy-windows.flow.md`. Three shape-specific flow docs are legitimate (D3 applies uniformly across shapes; the shapes themselves differ enough to warrant separate docs). No merge.
- Orchestration mode-branch: deploy backend dispatch by `Platform` = data-driven strategy (Linux-docker vs baremetal vs windows). Legitimate; not a Template-Method violation.
- Shared output columns: none added.
- OOS: fleet-batch atomic semantics = category (a) collapsed in-flight (`--no-drain` deleted, fleet driver rewritten as loop).
- Config-driven graph shape: no flag toggles a code path; drain is unconditional.

## Files

| File | Change |
|---|---|
| `.claude/rules/worker-deploy-drain.md` | NEW; codifies D1-D5 + drain definition + forbidden list |
| `deploy/deploy-worker.py` | NEW; per-service pause -> drain -> deploy -> Online driver |
| `deploy/deploy-fleet.py` | Rewrite as thin loop over per-service driver; delete `--no-drain` |
| `deploy/worker-deploy.feature.md` | Retrofit Surface + Success Criteria to per-service golden standard; delete fleet-atomic + drain-optional language |
| `deploy/worker-deploy-linux.flow.md` | Retrofit any drain-optional / batch language |
| `deploy/worker-deploy-baremetal.flow.md` | Same as above if conflicts found |
| `deploy/worker-deploy-windows.flow.md` | Same as above if conflicts found |
| `Tests/Contract/TestDeployPerWorkerDrain.py` | NEW; C6 assertions |

## Seams Enumerated

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| pause -> drain | `deploy-worker.py` writes `Workers.Status='Paused'` | `Workers` row | Worker's next heartbeat observes; new claims refused | `SELECT Status, LastHeartbeat FROM Workers WHERE WorkerName=?` |
| drain complete | Poll `ActiveJobs + ScanJobs` for worker | zero rows in either | deploy backend safe to proceed | C7 smoke |
| deploy backend | `deploy-worker.py` invokes docker/systemd/task per Platform | exit code + Workers.Version match | Post-deploy verification | Existing shape-specific verification |
| restore Online | `deploy-worker.py` writes `Workers.Status='Online'` | `Workers` row | Next claim tick resumes work | C7 smoke |

## Promotions

| Source (directive) | Target |
|---|---|
| D1-D6 + drained defn + forbidden list | `.claude/rules/worker-deploy-drain.md` (auto-loaded) |
| Per-service Surface + retrofit | `deploy/worker-deploy.feature.md` (updated Surface + C1-C19 IDs) |
| Contract test | `Tests/Contract/TestDeployPerWorkerDrain.py` (5/5 green) |
| Per-step timing instrumentation | `deploy/deploy-worker.py` (D6 -- live stdout + total line) |

## Progress

- [x] NEEDS_STANDARDS_REVIEW: operator approved
- [x] IMPLEMENTING: `.claude/rules/worker-deploy-drain.md` written
- [x] IMPLEMENTING: `--no-drain` deleted from `deploy-fleet.py` (via rewrite)
- [x] IMPLEMENTING: flow docs audited (grep found no drain-optional / batch language in linux/baremetal/windows flow docs)
- [x] IMPLEMENTING: `deploy/deploy-worker.py` per-service driver written
- [x] IMPLEMENTING: `deploy/deploy-fleet.py` rewritten as ThreadPoolExecutor loop
- [x] IMPLEMENTING: `Tests/Contract/TestDeployPerWorkerDrain.py` written
- [x] VERIFYING: contract test 4/4 green
- [x] VERIFYING: smoke on larry-worker-3 -- worker deployed to 9183303f while siblings 1/2/4 stayed Online on 09ccfa65 (per-service isolation proven)
- [x] DELIVERING: promoted content into worker-deploy.feature.md + rule file
- [x] REOPENED 2026-07-29: D6 added -- per-step timings printed live + total on completion (deploy-worker.py instrumented, contract test 5/5 green)
- [x] REOPENED 2026-07-30: larry fleet drift -- workers 2/3/4 stranded on 09ccfa65/9183303f after abandoned deploy-fleet.py run (DeployHistory Id=14 Outcome=RUNNING orphan). Redeployed larry-worker-2/3/4 via `py deploy/deploy-worker.py <name>`; all four now on HEAD 5031f2f6 Online. Marked 3 stale DeployHistory RUNNING rows (Ids 3/5/14) ABANDONED. Per-service driver proved out on drift-recovery use case.
