# Feature: Version on Deploy

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

4. **`deploy-windows-worker.py` stamps VERSION on the target.** Before the Task Scheduler trigger, the script writes the dev workstation's `git rev-parse HEAD` into `<remote-repo>\VERSION` and a `BUILD_INFO` file containing `commit=<sha>\nbuilt_at=<UTC ISO>\nbuilt_by=<dev-workstation hostname>\n`. Idempotent: re-deploying with the same HEAD produces identical files.

5. **Deploy verifies the round-trip.** Both deploy scripts, after restart, assert that `Workers.Version` for every target worker (or the single target worker on Windows) equals the stamped SHA. Mismatch causes exit code 3 with a message naming the expected SHA, the actual SHAs found, and the worker(s) that diverged.

6. **VERSION + BUILD_INFO never accidentally commit.** `.gitignore` excludes both files at the repo root. A local `py Scripts/StampVersion.py` for diagnostic use does not show up in `git status`.

7. **Hot-swap is not silently broken.** The hot-swap procedure in `worker-deploy-windows.flow.md` either (a) calls the stamp step, or (b) explicitly documents that hot-swap does not refresh VERSION so the operator can choose to run `py Scripts/StampVersion.py` or accept stale display. Either is acceptable; silent staleness is not.

## Status

In progress -- 2026-05-27. Plan approved, executing.

### Progress

- [x] Discovery: located worker resolver, deploy scripts, /Activity render path, existing fleet-mismatch banner
- [x] Feature doc + criteria pinned to directive
- [ ] Slice A: `_ResolveWorkerVersion` drops git fallback (criterion 2)
- [ ] Slice B: `Scripts/StampVersion.py` (new shared helper)
- [ ] Slice B: `deploy-windows-worker.py` stamps VERSION + BUILD_INFO on target (criterion 4)
- [ ] Slice C: linux + windows deploy verify `Workers.Version == stamped SHA` post-restart (criterion 5)
- [ ] `.gitignore` entries for VERSION + BUILD_INFO (criterion 6)
- [ ] Hot-swap doc updated to reference stamp step (criterion 7)
- [ ] Linux fleet redeployed -- larry, dot, wakko all show current HEAD SHA on /Activity
- [ ] Operator runs Windows redeploy on I9; I9 row shows the same SHA; /Activity banner clears
- [ ] Live verify: take a screenshot or `SELECT WorkerName, Version FROM Workers ORDER BY WorkerName` showing all 13 workers on one SHA

## Files

| File | Role |
|---|---|
| `WorkerService/Main.py` | Worker entry point; `_ResolveWorkerVersion` reads VERSION at startup |
| `deploy/deploy-linux-worker.py` | Stamps via Docker `--build-arg COMMIT_SHA`; gains version-match verify |
| `deploy/deploy-windows-worker.py` | Gains stamp step; gains version-match verify |
| `Scripts/StampVersion.py` | New -- shared "write VERSION + BUILD_INFO from current git HEAD" helper |
| `Templates/Activity.html` | Renders per-worker version + fleet-mismatch banner (no edits this feature) |
| `deploy/worker-deploy-windows.flow.md` | Hot-swap section updated to reference stamp step |
| `.gitignore` | Excludes VERSION and BUILD_INFO at repo root |
