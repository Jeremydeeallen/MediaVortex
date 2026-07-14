# Feature: Version on Deploy

**Slug:** version-on-deploy

## What It Does

Makes the version displayed for every worker on /Activity equal to the commit that was deployed to that worker at its last process restart. Honest by construction:

- Deploy scripts stamp a `VERSION` + `BUILD_INFO` file on the target with the dev workstation's `git rev-parse HEAD` before the worker restarts.
- Worker reads only from the deploy-stamped file at startup. No fallback to live `git rev-parse HEAD` against a checkout an operator can commit to.
- Both deploy scripts verify, after restart, that `Workers.Version` for every target worker matches the stamped SHA. Mismatch fails the deploy.
- /Activity per-worker tile + fleet-mismatch banner already render the value (no UI rework).

I9-2024 stops looking like "always on HEAD." Remote workers stop looking ahead of or behind the deploy event.

## Scope

- `WorkerService/Main.py`
- `deploy/deploy-linux-worker.py`
- `deploy/deploy-windows-worker.py`
- `deploy/version-on-deploy.feature.md`
- `Scripts/StampVersion.py` (new -- shared stamp helper; used by Windows deploy and reusable by operator scripts)
- `.gitignore` (add `VERSION`, `BUILD_INFO`)

Not in scope: `Templates/Activity.html` (regression-check only -- no edits expected). `WorkerService/Main.py` ancillary methods. Hot-swap automation.

## Surface

Operator-visible:

- `/Activity` per-worker tile shows short SHA + tooltip with full SHA + BUILD_INFO content (existing behavior; verified not regressed)
- `/Activity` fleet-mismatch banner names each version + worker count (existing; verified not regressed)
- `deploy-linux-worker.py` / `deploy-windows-worker.py` post-restart verification line prints "version=<sha>" alongside FFmpeg path and heartbeat age
- Deploy exits non-zero if `Workers.Version` doesn't equal the stamped SHA within the verification window

## Success Criteria

1. **Per-worker version on /Activity matches reality.** For every row in `Workers`, the value of `Version` equals the commit deployed to that worker at its last restart. Verifiable on /Activity (per-worker tile + tooltip) and via `SELECT WorkerName, Version FROM Workers`.

2. **Worker version is read only from a deploy-stamped artifact.** `_ResolveWorkerVersion` returns either the contents of `<repo>/VERSION` (with optional BUILD_INFO) or the literal string `"unknown"`. There is no code path that resolves to `git rev-parse HEAD` at runtime. Verifiable: `grep -n "git" WorkerService/Main.py` returns no `rev-parse` call inside `_ResolveWorkerVersion`.

3. **`deploy-linux-worker.py` stamps VERSION.** (Already true.) The Dockerfile receives `--build-arg COMMIT_SHA=<dev HEAD>`, bakes it into `/opt/mediavortex/VERSION` and `/opt/mediavortex/BUILD_INFO`. No change required.

4. **`deploy-windows-worker.py` stamps VERSION on the target.** Before the Task Scheduler trigger, the script writes the dev workstation's `git rev-parse HEAD` into `<remote-repo>\VERSION` and a `BUILD_INFO` file. The VERSION shape is `<sha>` when the local checkout's HEAD matches `origin/main`, OR `<sha> (<state>)` when divergent, where `<state>` is one of `ahead N`, `behind N`, or `ahead N, behind M` -- e.g. `1073b8d (ahead 2)`, `2b69d30 (behind 5)`, or `d7f993b (ahead 1, behind 3)`. The BUILD_INFO file contains three required lines (`commit=<sha>`, `built_at=<UTC ISO>`, `built_by=<dev-workstation hostname>`) plus an optional fourth line `relative_to_main=<state>` emitted only when divergent (same `<state>` vocabulary as the VERSION suffix). Idempotent on identical inputs: re-stamping with the same HEAD AND the same `origin/main` state produces identical files. The divergence suffix is computed by `Scripts/StampVersion.py` (see commit `2b69d30`) via `git fetch origin main --quiet` (15s timeout; fails silently on network unavailability, in which case the suffix is omitted).

5. **Deploy verifies the round-trip.** Both deploy scripts, after restart, assert that `Workers.Version` for every target worker (or the single target worker on Windows) equals the stamped SHA. Mismatch causes exit code 3 with a message naming the expected SHA, the actual SHAs found, and the worker(s) that diverged.

   **Known gap (introduced by commit `2b69d30`, deferred fix):** The strict-equality check `Workers.Version == ExpectedSha` in both `deploy-windows-worker.py:422` and `deploy-linux-worker.py:358` fails when (a) the dev workstation is ahead of or behind `origin/main` at deploy time AND (b) the target is a remote Windows worker that runs `Scripts/StampVersion.py` (which appends the divergence suffix). Linux containers are unaffected because they bake VERSION at `docker build` time via `--build-arg COMMIT_SHA` and never re-stamp -- the suffix-emitting StampVersion path does not run inside the container. There are zero remote Windows workers in the fleet today (I9-2024 is the dev workstation, not a deploy target), so the gap is latent. Fix path: `deploy-windows-worker.py` (and `deploy-linux-worker.py` defensively) should compare on the bare-SHA prefix of `Workers.Version` -- e.g. `Workers.Version.split()[0] == ExpectedSha` -- not on full string equality. Assigned to a follow-up directive when REMINGTON or another remote Windows worker is brought online.

6. **VERSION + BUILD_INFO never accidentally commit.** `.gitignore` excludes both files at the repo root. A local `py Scripts/StampVersion.py` for diagnostic use does not show up in `git status`.

7. **Hot-swap is not silently broken.** The hot-swap procedure in `worker-deploy-windows.flow.md` either (a) calls the stamp step, or (b) explicitly documents that hot-swap does not refresh VERSION so the operator can choose to run `py Scripts/StampVersion.py` or accept stale display. Either is acceptable; silent staleness is not.

## Status

COMPLETE 2026-05-27. CEO directive closed. All criteria PASS or PASS-conditional-on-I9-restart (operator authority); fleet is on the new resolver + stamping pipeline.

### Progress

- [x] Discovery: located worker resolver, deploy scripts, /Activity render path, existing fleet-mismatch banner
- [x] Feature doc + criteria pinned to directive
- [x] Slice A: `_ResolveWorkerVersion` drops git fallback (criterion 2) -- commit `c401ae6`
- [x] Slice B: `Scripts/StampVersion.py` (new shared helper) -- commit `c401ae6`
- [x] Slice B: `deploy-windows-worker.py` stamps VERSION + BUILD_INFO on target via SSH/PowerShell (criterion 4) -- commit `c401ae6`
- [x] Slice C: linux + windows deploy verify `Workers.Version == stamped SHA` post-restart (criterion 5) -- commit `c401ae6`
- [x] `.gitignore` entries for VERSION + BUILD_INFO (criterion 6) -- commit `c401ae6`
- [x] Hot-swap doc updated -- StartWorker.py self-stamps via Scripts/StampVersion.py at every launch.
- [x] Linux fleet redeployed (dot, larry, wakko) -- all 12 workers show `c401ae6` on /Activity with BuildInfo populated
- [x] `Templates/Activity.html`: version separator `v: ` with leading space for readability
- [x] `StartWorker.py`: pre-launch self-stamp step; Windows hosts pick up local HEAD automatically
- [x] Doc sweep: `WorkerService/WorkerService.flow.md` Version section rewritten; `deploy/worker-deploy-linux.flow.md` post-deploy verify SELECT gained Version
- [ ] OPERATOR: restart I9 worker so the new code path takes effect and VERSION is read at startup. /Activity should then show I9 on the same SHA as the Linux fleet; mismatch banner clears.

## Files

| File | Role |
|---|---|
| `WorkerService/Main.py` | `_ResolveWorkerVersion` reads VERSION + BUILD_INFO only; returns "unknown" if missing (no git fallback) |
| `deploy/deploy-linux-worker.py` | Stamps via Docker `--build-arg COMMIT_SHA`; `StepVerifyWorkers` asserts `Workers.Version == stamped SHA` per container |
| `deploy/deploy-windows-worker.py` | New `StepStampVersion` writes VERSION + BUILD_INFO on target via SSH/PowerShell; `StepVerifyWorkerOnline` asserts version match |
| `Scripts/StampVersion.py` | New -- shared stdlib-only "write VERSION + BUILD_INFO from current git HEAD" helper |
| `StartWorker.py` | `_StampVersion` pre-launch step runs `Scripts/StampVersion.py`; Windows native workers self-stamp at every launch |
| `Templates/Activity.html` | Per-worker tile renders `v: <short-sha>` (separator + leading space); fleet-mismatch banner unchanged from prior feature |
| `deploy/worker-deploy-windows.flow.md` | Hot-swap section + Step 5 verify reference self-stamp behavior |
| `deploy/worker-deploy-linux.flow.md` | Post-deploy verify SELECT gained Version column |
| `WorkerService/WorkerService.flow.md` | Version section rewritten: 2-state resolver, who writes the files on each platform |
| `.gitignore` | Excludes `/VERSION` and `/BUILD_INFO` at repo root |
