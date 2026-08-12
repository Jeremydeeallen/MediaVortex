# Directive: worker-memorymax-cgroup

**Status:** Active -- phase: IMPLEMENTING

**Slug:** worker-memorymax-cgroup

**Interrupts:** probe-loudness-remove (top of `.claude/current-feature` stack)

### Promotions

- (populated at DELIVERING)

## What / Why

Wakko-worker-1 kernel-OOM-killed 30-50x in past 5 days. `systemctl show mediavortex-worker@1.service` reports `MemoryPeak=16068640768` (16 GiB) on a host with 15 GiB physical RAM. No `MemoryMax` cgroup limit → process grows unbounded until kernel OOM-killer takes down the whole cgroup + host swap-thrashes.

Fix: set `MemoryMax=12G` in systemd unit template. When the process exceeds 12 GiB, cgroup kills the process cleanly; host stays healthy; systemd auto-restarts per existing `Restart=always`. Restart cycle unchanged, but faster (no host-level swap-hell before death).

Diagnostic value: once cgroup kills consistently, we can observe whether the peak stabilizes over time (fixed leak per boot cycle) or grows (real leak). Also enables leak-hunt: if 12 GiB peak is hit every N minutes with a specific job load, we can profile the culprit.

## Scope

1. Add one line `MemoryMax=12G` to systemd unit template in `deploy/deploy-baremetal-worker.py` (immediately before `LimitNOFILE=65536`).
2. Deploy to wakko host (`py deploy/deploy-baremetal-worker.py wakko`) + restart wakko-worker-1 to render new unit.
3. Observe over 24h: OOM-kill cadence, `MemoryPeak` values, whether kills concentrate on specific job shapes.

## Out of Scope

(a) Actual leak investigation -- category (b) deferred: this directive gives us clean kills to observe from. Leak-hunt is a separate directive once we have data.
(b) MemoryMax on other hosts -- category (a) tolerated: same template writes 12 GiB cap to larry LXC + dot + wakko workers. Larry LXC has plenty; dot has plenty; wakko is the only near-limit host. Uniformity is fine.
(c) `MemoryHigh` throttle -- category (b) deferred: MemoryHigh throttles process before kill. Skip until we see if MemoryMax alone changes behavior.

## Acceptance Criteria

C1. `deploy/deploy-baremetal-worker.py` systemd unit template contains `MemoryMax=12G` between `KillSignal=SIGTERM` and `LimitNOFILE=65536`. Verifiable: grep.
C2. After deploy to wakko + wakko-worker-1 restart, `systemctl show mediavortex-worker@1.service | grep MemoryMax` returns `MemoryMax=12884901888` (12 GiB in bytes).
C3. Live smoke: over 4h post-deploy, count new "worker crashed/restarted" attempts on wakko-worker-1. If kill-by-cgroup is working, `journalctl -u mediavortex-worker@1.service` shows `A process of this unit has been killed by the cgroup memory limit` (or similar) instead of "OOM killer" from kernel.
C4. `MemoryPeak` from `systemctl show` reads <= 12884901888 for the current WorkerService process.

## Principle Analysis

**KISS.** One line of systemd config. No code change. No new dependency.
**DDD.** Deploy concern; lives in `deploy/`. No cross-context change.
**DRY.** One systemd template line, applied uniformly.
**SOLID.** N/A -- config change.
**SSoT.** Systemd unit template remains the SoT for worker process resource limits.

## Files

- `deploy/deploy-baremetal-worker.py` (one line add to `UnitBody` string)

## Progress

- [x] NEEDS_STANDARDS_REVIEW (rules loaded).
- [x] NEEDS_PLAN (settled: single-line config change).
- [x] NEEDS_DOC_PREREAD (no colocated *.feature.md; systemd template inline in deploy script).
- [ ] IMPLEMENTING: add MemoryMax line + deploy to wakko + verify systemctl show.
- [ ] VERIFYING: 4h post-deploy crash-cadence + MemoryPeak observation.
- [ ] DELIVERING: Promotions, delivery report with observation results.
