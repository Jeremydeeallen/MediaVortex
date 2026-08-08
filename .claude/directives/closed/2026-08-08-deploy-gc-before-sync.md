# Directive: deploy-gc-before-sync

**Slug:** deploy-gc-before-sync
**Status:** Closed
**Opened:** 2026-08-08

## Ask

`deploy-baremetal-worker.py` runs `StepGarbageCollect` LAST. If earlier steps (like `StepSyncSource`) fail because the disk is full, GC never runs -> next deploy also fails on the same full disk -> death spiral.

Concrete incident (2026-08-08): mediavortex-workers LXC accumulated 12 stale `src-*` dirs (~1.7 GB each), disk hit 40G/40G, sync failed with `tar: <file>: Cannot open: No such file or directory`. Fleet deploy has been silently failing on this host for ~24 hours.

Fix: run GC BEFORE `StepSyncSource` (in addition to keeping the current post-sync GC call). Pre-sync GC frees the incoming deploy's headroom; post-sync GC prunes the just-created cohort.

## Success Criteria

C1. `deploy-baremetal-worker.py::main` calls `StepGarbageCollect(Target)` before `StepSyncSource(Target, Sha)`. Post-sync `StepGarbageCollect` call preserved.

C2. Pre-sync GC failure is NON-FATAL (it's opportunistic disk-freeing, not a correctness step). Post-sync GC failure remains non-fatal (already returns True on skip).

C3. `deploy/worker-deploy-baremetal.flow.md` ST3 note updated to reflect pre-sync GC pass.

C4. Deploy on mediavortex-workers succeeds end-to-end. (Already verified manually 2026-08-08 12:59 after manual `rm -rf`.)

## Files

- `deploy/deploy-baremetal-worker.py` -- move/duplicate GC call
- `deploy/worker-deploy-baremetal.flow.md` -- ST3 note

## Call-Graph Audit

- Signal 1 (multiple flow docs): only `worker-deploy-baremetal.flow.md`. No divergence.
- Signal 2 (orchestration mode-branch): none.
- Signal 3 (mode-sparse output columns): none.
- Signal 4 (OOS ambiguity): out-of-scope items categorized below.
- Signal 5 (config-driven graph shape): none.

## Out of Scope

- **(a) In-flight preserved:** Post-sync GC call retained (defense-in-depth).
- **(b) Tolerated debt:** `deploy-fleet.py` deploy-history rows stuck RUNNING (never UPDATEd to OK) -- separate script-lifecycle bug, not addressed here.
- **(b) Tolerated debt:** Fleet deploy Windows-local vs remote path handling has edge cases (MSYS conversion) -- separate concern.

### Promotions

| Source (directive) | Target (durable) |
|---|---|
| Pre-sync GC step | `deploy/worker-deploy-baremetal.flow.md` ST3 |
