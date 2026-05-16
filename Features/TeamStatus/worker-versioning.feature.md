# Worker Versioning -- know what code each worker is running

## What It Does

Stamps each worker's Docker image and Python process with the git commit SHA that built it, then surfaces that version on every Workers row and on the Activity page. After a deploy the operator can confirm at a glance that all workers are running the new code -- not a mix of old and new because one container failed to recreate or the Windows host wasn't restarted. Exposes mismatch as a visible row decoration so a forgotten worker can't quietly stay on yesterday's code.

This is a small addition: a build-time stamp, a startup read, a new nullable column, and a UI badge. No new pipeline, no schema migration beyond the column.

## Concern

Just deployed (2026-05-09): rebuilt the worker image, recreated 4 LXC containers. The Windows worker (I9-2024) is on the same code repo but is a Python process not a Docker container and does not get redeployed by `docker compose up`. Today the operator has no way to confirm "is I9-2024 running the same commit as the LXC workers?" without SSHing each host and `git log`ing. Two specific gaps this closes:

1. After today's two-commit pair (`a9e1c19` + `c18ced3`, fixing the queue priority bypass paths and the worker claim ORDER BY), only the LXC workers got the new code. The Windows worker is still on the old binary until manually restarted. There is currently no signal in the DB or UI that says so.
2. A future container that fails to restart cleanly (image not pulled, hostname collision, etc.) could quietly stay on the prior version while heartbeating normally. Pure heartbeat freshness gives no version signal.

## Success Criteria

### A. Build-time version stamp

1. The `deploy/Dockerfile` writes the git commit SHA into `/opt/mediavortex/VERSION` during the image build. The SHA is sourced from `git rev-parse HEAD` at build time, captured by `deploy/worker-deploy-linux.flow.md` step 2 (so the build context already has the commit available). The file contents are exactly the 40-char SHA followed by a newline. Verifiable: `docker run --rm --entrypoint cat mediavortex-worker:latest /opt/mediavortex/VERSION` returns the expected SHA.

2. The Dockerfile additionally writes a short build manifest to `/opt/mediavortex/BUILD_INFO` containing: `commit=<SHA>`, `built_at=<ISO-8601 UTC>`, `built_by=<hostname of build host>`. Three lines, each `key=value`. Verifiable: `cat /opt/mediavortex/BUILD_INFO` inside any worker container returns all three keys with non-empty values.

### B. Worker self-reports version at registration

3. `Repositories/DatabaseManager.RegisterWorker()` accepts a new `Version` argument (string, nullable). Writes it to `Workers.Version`. The `Workers` table gains a nullable `Version VARCHAR(64)` column via `Scripts/SQLScripts/AddWorkerVersionColumn.py` (idempotent `ADD COLUMN IF NOT EXISTS`). Verifiable: `\d Workers` shows the column.

4. `WorkerService/Main.py` resolves its version at startup using a 3-tier resolver in this order, falls through on FileNotFoundError / non-empty value:
   1. Read `/opt/mediavortex/VERSION` (Docker workers)
   2. Run `git rev-parse HEAD` in the project root with a 2-second timeout (Windows / dev-host workers running from a git checkout)
   3. Return the literal string `"unknown"`
    The resolved value is passed into `RegisterWorker`. Verifiable for each tier: a Docker worker has the SHA from the file; the local Windows worker has the live `git rev-parse HEAD` output; a worker run from a non-git tarball reports `"unknown"`.

5. The version is also written into `BUILD_INFO`-style fields on the Workers row: a new `BuildInfo TEXT` column (nullable) holds the entire `BUILD_INFO` file contents, or NULL if the file is absent. Lets the operator see the build host and timestamp without reading the image. Verifiable: `SELECT BuildInfo FROM Workers WHERE WorkerName='larry-worker-1'` returns the three-line contents.

### C. Activity page surfaces it

6. The Activity page worker tile shows the short version (first 7 chars of the SHA) next to the worker name. For workers reporting `"unknown"`, shows `unknown` in italics. Tooltip on hover shows the full SHA + the BuildInfo contents. Verifiable: open Activity page, hover the version on each tile, observe full SHA + build_at + built_by.

7. **Version mismatch warning.** When two or more workers report different versions (excluding `"unknown"`), the Activity page renders a fleet-wide banner at the top: `Workers running mixed versions: 4 on a9e1c19, 1 on c18ced3`. Mismatches against `"unknown"` workers do not trigger the banner (an `unknown` worker is its own problem, not a mismatch indicator). Verifiable: queue a deliberate mismatch by stopping one worker and restarting the others on a new build; banner appears. Restart the held-back worker; banner clears.

### D. Mismatch detection backend

8. `/api/TeamStatus/Workers` payload gains optional `Version` and `BuildInfo` fields per worker, sourced from the new columns. Verifiable: GET the endpoint, see fields populated for Docker workers, populated-or-null for the Windows worker depending on git availability.

9. New endpoint `GET /api/TeamStatus/Workers/VersionStatus` returns `{"AllAgree": bool, "Versions": {"<sha>": ["<workerName>", ...], "unknown": [...]}, "MismatchCount": int}`. Drives the Activity page banner via a single round-trip rather than client-side aggregation. Verifiable: with mixed versions, response has `AllAgree=false` and a non-empty `Versions` dict with multiple keys.

### E. Documentation

10. `deploy/worker-deploy-linux.flow.md` "Build and Deploy Pipeline" section gains a one-line note that step 2's `docker build` runs from the source tree on the LXC, and the Dockerfile ARG / ENV mechanism captures `git rev-parse HEAD` from the build context. If the source tree on the LXC is not a git checkout (it isn't -- it's an scp'd snapshot), the deploy script must pass the commit SHA in via `--build-arg COMMIT_SHA=$(git -C /c/Code/MediaVortex rev-parse HEAD)` and the Dockerfile reads that ARG. Update the flow doc step 2 accordingly. Verifiable: doc shows the new `--build-arg` flag in the build command; the resulting image has the correct SHA in `/opt/mediavortex/VERSION`.

11. `WorkerService.flow.md` "Per-Worker Status Control" section gains a brief "Version" subsection describing the resolver order and where the value is written.

## Status

COMPLETE 2026-05-16 -- full design (not MVP). All 11 criteria verified
against live fleet state. Implementation in commit `89c8ab2`.

### Progress

- [x] Read prior issues (no related entry in `KNOWN-ISSUES.md`)
- [x] Read existing deploy flow (`deploy/worker-deploy-linux.flow.md`)
- [x] Drafted feature doc (this file)
- [x] Operator approval (2026-05-16 "Let's add b right above our current work")
- [x] A1-A2: Dockerfile `ARG COMMIT_SHA=unknown` + writes `/opt/mediavortex/VERSION` and three-line `/opt/mediavortex/BUILD_INFO` (commit / built_at / built_by). Commit `89c8ab2`.
- [x] B3-B5: `Scripts/SQLScripts/AddWorkerVersionColumn.py` migration (Version VARCHAR(64), BuildInfo TEXT) applied. `DatabaseManager.RegisterWorker` accepts and UPSERTs both. `WorkerService/Main.py::_ResolveWorkerVersion` 3-tier resolver (VERSION file -> git rev-parse -> "unknown") wired into `_RegisterAndLoadWorkerConfig`. Commit `89c8ab2`.
- [x] C6-C7: Activity tile shows `v<short-sha>` next to worker name with full SHA + BuildInfo tooltip; "unknown" workers render in italics/warning color. Fleet-wide mismatch banner appears above the worker grid when 2+ workers report different non-unknown versions. Commit `89c8ab2`.
- [x] D8-D9: `/api/TeamStatus/Workers` payload includes `Version` + `BuildInfo`. New `GET /api/TeamStatus/Workers/VersionStatus` endpoint returns `{AllAgree, Versions, MismatchCount}`. Commit `89c8ab2`.
- [x] `deploy/worker-deploy-linux.flow.md` step 2 already updated with `--build-arg COMMIT_SHA=$(git rev-parse HEAD)` by the operator's deploy refactor (verified pre-existing).
- [x] `WorkerService/WorkerService.flow.md` new Version subsection describing the resolver order, the columns written, and the Activity page surface. Commit `89c8ab2`.
- [x] Larry + Wakko + Dot redeployed with `--build-arg COMMIT_SHA=<sha>`; all 16 docker workers report VERSION + BuildInfo. Verified `SELECT version, buildinfo FROM workers` -- all rows populated with `19fc6328...` + three-line BuildInfo.
- [x] I9 WorkerService restarted by operator; tier-2 resolver (`git rev-parse HEAD`) fired -- I9-2024 row shows Version=`19fc6328...` and BuildInfo=NULL (expected; tier-2 produces no BuildInfo).
- [x] Smoke test passed: all 17 workers report SHA `19fc63286596eedd9ab3f84679cdd361d1866c20`. AllAgree=true across fleet.

## Scope

```
deploy/Dockerfile                                            -- ARG COMMIT_SHA, write VERSION + BUILD_INFO files
deploy/worker-deploy-linux.flow.md                                  -- step 2 build command updated with --build-arg
Repositories/DatabaseManager.py                               -- RegisterWorker accepts Version + BuildInfo
WorkerService/Main.py                                         -- 3-tier version resolver at startup, passes to RegisterWorker
Features/TeamStatus/TeamStatusController.py                   -- /Workers payload includes Version + BuildInfo; new /Workers/VersionStatus endpoint
Templates/Activity.html                                       -- short SHA on tile, tooltip, fleet-wide mismatch banner
Scripts/SQLScripts/AddWorkerVersionColumn.py                  -- NEW. Idempotent ALTER TABLE Workers ADD COLUMN IF NOT EXISTS Version VARCHAR(64), BuildInfo TEXT
WorkerService/WorkerService.flow.md                           -- Version subsection added
```

## Files

| File | Role |
|------|------|
| `deploy/Dockerfile` | `ARG COMMIT_SHA` declared near the top of stage 2; `RUN echo "$COMMIT_SHA" > /opt/mediavortex/VERSION` and write three-line BUILD_INFO with built_at/built_by from build-time `date -u` and `hostname` |
| `deploy/worker-deploy-linux.flow.md` | Step 2 updated to `docker build --build-arg COMMIT_SHA=$(git -C /c/Code/MediaVortex rev-parse HEAD) ...`. The git command runs on the dev workstation before the SSH so the SHA is baked even though the LXC source tree is a snapshot |
| `Repositories/DatabaseManager.py` | `RegisterWorker(WorkerName, Platform, FFmpegPath, FFprobePath, ..., Version=None, BuildInfo=None)` adds the two columns to the UPSERT |
| `WorkerService/Main.py` | New `_ResolveWorkerVersion()` returns `(version, build_info_or_none)`. Tier 1 reads `/opt/mediavortex/VERSION` and `/opt/mediavortex/BUILD_INFO`; tier 2 runs `git rev-parse HEAD` with 2s timeout; tier 3 returns `("unknown", None)`. Called once during `_RegisterAndLoadWorkerConfig` |
| `Features/TeamStatus/TeamStatusController.py` | `/Workers` SELECT includes Version + BuildInfo; new `/Workers/VersionStatus` endpoint groups workers by version and returns the AllAgree flag |
| `Templates/Activity.html` | Worker tile shows `<small class="text-muted">v<short-sha></small>` next to name; on page load fetches `/Workers/VersionStatus` and renders the mismatch banner above the worker grid |
| `Scripts/SQLScripts/AddWorkerVersionColumn.py` | NEW. `ALTER TABLE Workers ADD COLUMN IF NOT EXISTS Version VARCHAR(64); ALTER TABLE Workers ADD COLUMN IF NOT EXISTS BuildInfo TEXT;` |
| `WorkerService/WorkerService.flow.md` | New "Version" subsection under "Registration", describes the 3-tier resolver and which columns get written |

## Deviation from conventions

None. Each criterion is observable: file content, DB column read, HTTP response, DOM inspection. The Workers schema additions are nullable so older workers (pre-deploy) keep registering without error -- they just write NULL for both fields, which the UI shows as `unknown` italics.
