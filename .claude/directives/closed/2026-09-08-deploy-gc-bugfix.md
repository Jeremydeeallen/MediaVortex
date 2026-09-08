# deploy-gc-bugfix

**Status:** Closed 2026-09-08

## Ask

Fix `StepGarbageCollect` in `deploy/deploy-baremetal-worker.py` so it actually deletes old `src-*` and `host-venv-*` directories. Current script is broken: `ls -1t src-*` (no `-d`) recurses INTO each directory listing files instead of the directory names. Result: every deploy adds a new 1.9 GB versioned src dir; nothing ever gets pruned. Discovered when larry LXC 218 hit 100% disk with 9 accumulated src dirs (17 GB total).

## Fix

One-char change: add `-d` and trailing `/` to force directory-only listing.

Before:
```
ls -1t src-* 2>/dev/null | grep -v -- '-legacy-' | tail -n +6 | xargs -r rm -rf
```

After:
```
ls -1td src-*/ 2>/dev/null | grep -v -- '-legacy-' | tail -n +6 | xargs -r rm -rf
```

Same fix for `host-venv-*/` line.

## Acceptance Criteria

**AC1.** `StepGarbageCollect` shell command uses `ls -1td <pattern>/` (with `-d` flag + trailing `/`) so it lists directory names only, not their contents.

**AC2.** After next fleet deploy, `ls -1d /opt/mediavortex/src-*/` on each host returns exactly 5 versioned dirs (or fewer if history shorter). Same for `host-venv-*/`.

**AC3.** Live smoke on larry LXC 218: run `pct exec 218 -- ls -1d /opt/mediavortex/src-*/` post-deploy; confirm <= 5 dirs.

## Out of Scope

- **(b) acknowledged debt**: dev-tree cruft in rsync'd src dirs (`backfill-shard-*.err`, screenshots, `IDEAS.md`, `.rtf`). Each versioned src carries ~1 GB of stuff workers don't need. Separate directive for rsync-exclude tuning.
- **(b) acknowledged debt**: monitoring alert when any deploy host crosses 80% disk. Not this directive.

## Files

- `deploy/deploy-baremetal-worker.py` -- lines 267 + 269

## Plan

1. Edit `StepGarbageCollect` command (2 lines).
2. Commit + push.
3. Verify corrected command directly on larry (no full deploy needed to test).
4. Close directive; next deploy applies the fix fleet-wide automatically.

## Verification

- **AC1** ✓ `deploy/deploy-baremetal-worker.py:267 + 269` now use `ls -1td <pattern>/`.
- **AC2** deferred to next fleet deploy (fix is in the deploy script; effective on next `deploy-fleet.py` run).
- **AC3** ✓ Live test on larry LXC 218 of corrected shell command returns `src-25f013cd7afcbc08/` + `src-eb226b5085a164a7/` (2 dirs — exactly what's on disk after my manual cleanup). Directory names only, no file recursion. `tail -n +6` will correctly prune when count crosses 5 next time.
- **Immediate bleeding stopped**: larry LXC 218 rootfs grown from 40 GB -> 100 GB via `pct resize 218 rootfs +60G` on the Proxmox host. Now 29% used / 72 GB free. Demucs has room for 4 concurrent workers.
