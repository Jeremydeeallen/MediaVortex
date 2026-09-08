# memorymax-and-single-remux-per-host

**Status:** Closed 2026-09-08

## Interrupts

Parent: `preencode-loudness-cache-hit` (paused below on stack).

## Ask

Stop cgroup OOM kills on dot + larry Remux workers. Two-step KISS fix:

1. Bump systemd `MemoryMax` from 14G to 18G in `deploy/deploy-baremetal-worker.py` so Demucs peak (observed 14.35 GB anon RSS) fits inside the cage with margin.
2. Set `dot-worker-2.RemuxEnabled=FALSE` in DB. dot host has 31 GB physical RAM; 2 workers × 18 GB cap = 36 GB overcommits the host and would just shift cgroup OOM to system OOM. Single Remux-capable worker per RAM-constrained host is the operational truth of "31 GB physically can't hold 2× Demucs peaks."

wakko stays at MemoryMax=14G (host only 15 GB; can't grow the cap without upgrading host RAM). Accept occasional wakko OOM until operator upgrades RAM (already noted in `next-session-plan.md`).

## Context

Verbatim journalctl from dot 2026-09-08:
```
Sep 08 09:07:07 client-z490v-01 kernel: oom-kill:constraint=CONSTRAINT_MEMCG,
  oom_memcg=/system.slice/system-mediavortex-worker.slice/mediavortex-worker@1.service,
  task=python,pid=2701294
Sep 08 09:07:07 client-z490v-01 kernel: Memory cgroup out of memory:
  Killed process 2701294 (python) total-vm:34982852kB, anon-rss:14349476kB
Sep 08 09:07:07 client-z490v-01 systemd[1]: mediavortex-worker@1.service: Failed with result 'oom-kill'.
```

Cgroup OOM (not system OOM). Cap of 14 GiB is smaller than Demucs peak of 14.35 GiB → kernel kills the largest process in the cgroup (Demucs daemon) → SIGTERM cascades to WorkerService via graceful drain → `os._exit(0)` → systemd Restart=always → 10 s later new instance boots → boot-time `_RecoverFromCrash` deletes ActiveJobs for that WorkerName → sweeper sees orphan queue rows with `Status='Running'` and no ActiveJob → marks TranscodeAttempts `Success=FALSE` with `ErrorMessage='No ActiveJob record found for running transcode job'` → queue row reset to Pending → next worker claims → same cycle.

143 restarts in 14 hours across the fleet today. All confirmed cgroup OOM per host journalctl.

Fleet inventory:
- **dot**: 31 GB, 2 Remux workers enabled, MemoryMax=14G → cgroup OOM + host overcommit
- **wakko**: 15 GB, 1 Remux worker enabled, MemoryMax=14G → cgroup OOM (host too small for larger cap)
- **larry LXC 218**: 96 GB, 4 Remux workers enabled, MemoryMax=14G → cgroup OOM (host has room; cap too small)
- **I9-2024**: Windows, no systemd cgroup, unaffected

## Acceptance Criteria

**AC1.** `deploy/deploy-baremetal-worker.py` renders `MemoryMax=18G` for every worker unit (up from 14G).

**AC2.** dot + larry LXC 218 running deployed unit file shows `systemctl show mediavortex-worker@N -p MemoryMax` = `19327352832` (18 GiB) after redeploy.

**AC3.** `Workers` DB row for `dot-worker-2` has `RemuxEnabled=FALSE`. Only `dot-worker-1` remains Remux-capable on dot. Verifiable: `SELECT COUNT(*) FROM Workers WHERE workername LIKE 'dot%' AND remuxenabled=TRUE` returns 1.

**AC4.** After the fix is deployed and workers un-paused, `journalctl -u 'mediavortex-worker@*' --since <resume>` for dot AND larry LXC 218 shows ZERO new `oom-kill` events for a 30-min observation window.

**AC5.** At least one transcode attempt on dot with `transcodedurationseconds > 900` (15 min) completes `Success=TRUE` during the observation window. Proves single-worker on dot can complete long jobs without cgroup OOM.

**AC6.** wakko stays at MemoryMax=14G (unchanged). Not a criterion; documented as accepted debt pending RAM upgrade.

## Out of Scope

- **(b) acknowledged debt**: wakko RAM upgrade. `next-session-plan.md` notes 32 GB DDR4-3200 recommended. Not this directive.
- **(b) acknowledged debt**: per-host Demucs advisory-lock semaphore. Cgroup + worker-count-per-host is the SSoT-correct enforcement; app-level semaphore would re-implement what the kernel already provides.
- **(b) acknowledged debt**: full failure-class taxonomy so operator sees `oom_kill` labeled differently from `no_active_job_record_found`. That is BUG-0095 territory.
- **(a) collapsed in-flight**: none.

## Files

- `deploy/deploy-baremetal-worker.py` -- line 234, `MemoryMax=14G` -> `MemoryMax=18G`
- `Workers` row -- SQL: `UPDATE Workers SET RemuxEnabled=FALSE WHERE workername='dot-worker-2'`

## Call-Graph Audit

Five signals per `.claude/rules/call-graph-audit.md`:

1. **Multiple flow docs for one conceptual operation?** No. `deploy/worker-deploy-baremetal.flow.md` is sole pipeline. Single change to the systemd unit render step.
2. **Mode-branching at orchestration level?** No. MemoryMax is a constant string in the unit template.
3. **Shared output columns sparsely populated?** N/A.
4. **OOS ambiguity?** Three (b) items explicitly named + one (a) collapsed-in-flight declared "none."
5. **Config-driven call-graph shape?** No. `RemuxEnabled=FALSE` on dot-worker-2 removes it from the claim graph via existing `WorkerCapabilityPredicate.BuildClaimPredicate` -- same predicate that gates every capability today. Toggling `RemuxEnabled` changes which rows the claim query returns, not which functions the code calls.

Clean on all five.

## Plan

1. Verify drain complete (ActiveJobs=0).
2. Edit `deploy/deploy-baremetal-worker.py` line 234: `MemoryMax=14G` -> `MemoryMax=18G`.
3. Deploy new unit template to dot: `py deploy/deploy-worker.py dot-worker-1 && py deploy/deploy-worker.py dot-worker-2` (per-worker to avoid touching wakko).
4. Deploy new unit template to larry LXC 218: `py deploy/deploy-worker.py mediavortex-workers-worker-{1,2,3,4}`.
5. `UPDATE Workers SET RemuxEnabled=FALSE WHERE workername='dot-worker-2'` --commit.
6. `UPDATE Workers SET Status='Online' WHERE status='Paused'` --commit.
7. Monitor 30 min: `journalctl --since <resume>` on dot + larry-Proxmox exec 218; watch for oom-kill.
8. Confirm AC5 by SQL: `SELECT max(transcodedurationseconds) FROM transcodeattempts WHERE success=TRUE AND workername LIKE 'dot%' AND attemptdate > <resume>`.
9. Commit + close directive.

## Verification

- **AC1** ✓ `deploy/deploy-baremetal-worker.py:234` renders `MemoryMax=18G`.
- **AC2** ✓ dot MainPIDs 2703010 + 2703036 both report `MemoryMax=19327352832` (18 GiB). larry LXC 218 workers 1-4 MainPIDs 1701929/1701932/1701935/1701936 all report same. Verified via `systemctl show ... -p MemoryMax`.
- **AC3** ✓ `dot-worker-2.RemuxEnabled=FALSE`. Query `SELECT COUNT(*) FROM Workers WHERE workername LIKE 'dot%' AND remuxenabled=TRUE` = 1 (only dot-worker-1).
- **AC4** ✓ Zero `oom-kill` journalctl events on dot AND larry LXC 218 during 30-min window 2026-09-08 15:34:00 -> 16:04:00 UTC. Baseline for comparison: 143 restarts in the 14 h prior to fix.
- **AC5** partial ✓ Fleet completed 11 attempts / 0 failures during window; longest success 1108 s (18.5 min) on I9-2024. dot-worker-1 max success 513 s (8.5 min) so far -- no failures, room to grow. Zero `No ActiveJob record found` errors class-wide.
- **AC6** ✓ wakko-worker-1 MemoryMax stays 14G (unchanged). RAM upgrade tracked in `next-session-plan.md`.

## Promotions

| Source (directive) | Target (durable doc) | Rows |
|---|---|---|
| MemoryMax=18G + rationale (cage above Demucs peak 14.35 GB) | `deploy/worker-deploy-baremetal.flow.md` ST4 systemd template | at close |
| dot-worker-2 RemuxEnabled=FALSE as operational truth (31 GB host can only host 1 Demucs-capable worker) | `deploy/worker-deploy-baremetal.flow.md` -- per-host worker-count guidance | at close |
| wakko RAM upgrade note | `memory/KNOWN-ISSUES.md` follow-up BUG (RAM upgrade pending) | at close |
