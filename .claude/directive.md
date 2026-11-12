# Current Directive

**Set:** 2026-11-11
**Status:** Active -- phase: VERIFYING
**Slug:** farm-server
**Replaces:** `directives/closed/2026-11-11-movies-video-rule.md` (closed Success)

## Outcome

The MediaVortex UI and control plane (WebService with its background runners) run around the clock on a dedicated container on the server farm. It is reachable by name, comes back on its own after a reboot, and no longer depends on I9-2024 being on. One command moves it to `origin/main` in seconds, and one command returns it to the previous release in seconds. A release that fails to start leaves the prior release serving. Every server deploy and rollback is recorded.

First of three, in order. `push-to-deploy` comes next: CI on GitHub-hosted runners, plus a pull-based CD agent on this server that deploys green `main` commits to the server and the worker fleet. `fast-code-staging` is opened only if staging any host from the server still takes more than 60s. Operator decisions (2026-11-11):
- New LXC on larry with the same media bind mounts as CT 218.
- The server runs WebService and, in the next directive, the CD agent.
- A few seconds of restart downtime is acceptable.
- I9-2024 stays a dev workstation; its worker is started by hand and left out of automatic deploys.
- Speed targets: green commit -> server on the new sha within 2 min; code staged on every worker host within 60s; rollback within 30s.

## Acceptance Criteria

1. With no WebService running on I9-2024, the MediaVortex UI answers HTTP 200 at its nginx name and at the server's address on port 5000.
2. After the server container reboots, the UI answers HTTP 200 within 60s with no operator action.
3. A single HTTP call to the server returns the git sha it is running.
4. One command deploys `origin/main` to the server. When dependencies are unchanged, the server answers on the new sha within 30s of the command starting.
5. One command rolls the server back to the previously deployed sha within 30s; the call in criterion 3 shows the prior sha.
6. A deploy whose new release fails to start exits non-zero and leaves the server answering on the prior sha.
7. Every server deploy and rollback writes one DeployHistory row with prior sha, new sha, elapsed seconds, and outcome (`OK` or `FAILED` with a reason).
8. The background runners run on the server. Verify: the service status and worker status pages refresh, and one audio remeasurement completes by reading media through the server's mounts.
9. At most one WebService serves at any time. Verify:
   - Starting MediaVortex on I9-2024 does not start a WebService there.
   - A fleet deploy does not start or restart a WebService on I9-2024.
   - A second WebService started on any other host refuses to start while the server's is alive.

## Call-Graph Audit

Completed at NEEDS_PLAN.

- **Signal 1 (two flow docs for one operation):** a new server-deploy flow would duplicate `deploy/worker-deploy-baremetal.flow.md`, because both deploy versioned code to a Linux host as a systemd service. Resolution: generalize that flow to a host deploy with a role per service (worker, server). Do not add a parallel flow doc. This also closes BUG-0064 (single deploy script, one strategy per host shape).
- **Signal 2 (mode branch at orchestration):** `deploy/deploy-worker.py` `RestartWindowsLocal` (L93-104) restarts WebService inside the I9 worker path. This directive removes that WebService restart. The remaining I9 branch is handled by `push-to-deploy`, which leaves I9 out of automatic deploys by data, not by a flag.
- **Signal 3 (output columns filled sparsely):** a server deploy must fill every DeployHistory column a fleet deploy fills (PriorSha, NewSha, ElapsedSeconds, HostsAttempted, HostsSucceeded, Outcome, ErrorMessage).
- **Signal 5 (config changes which code runs):** none found. Every host runs the same `WebService/Main.py` startup path; only the deploy-assigned env values differ.
- **Seam, WebService identity:** `WebService/Main.py` L132 takes its identity from `socket.gethostname()`. That identity selects ffmpeg paths and path resolution for audio remeasurement. It already violates `claim-authority.md` (identity must be deploy-assigned), and on the server it becomes load-bearing, so it is absorbed here. Identity will come from a deploy-assigned env var. The server identity gets share mappings, but no capability that makes its rows a claim target.
- **Seam, single instance across hosts:** `WebService/Main.py` `_SupersedeExistingInstance` (L224-295) and `ServiceStatusService.RegisterServiceStartup` (L135) compare the recorded PID only against the local host. A WebService on another host sees the server's PID as stale and starts anyway. Absorbed here (criterion 9).
- **Seam, Windows-only dependency:** `WebService/requirements.txt` L28 `WinTmp` cannot install on Linux. It gets a platform marker.
- **Cross-owner terminal write:** WebService startup (`Main.py` ~L157) sets every host's Running/Pending `ScanJobs` to Stopped. With deploys every few minutes, this would kill worker scans on each deploy. Absorbed: narrowed to the WebService's own WorkerName.
- **Host source sync:**
  - `SyncSource.py` ships the working tree, including uncommitted files and untracked junk (372 extra files on CT 218).
  - It also rsyncs into an existing `src-<sha>`, which violates "never mutated after creation".
  - The fingerprint hashes working-tree bytes (CRLF on Windows), not the deployed sha, so `--sha` and rollback would select the wrong venv.
  - `StepShipSchemaSnapshot` re-ships a file that git already tracks.
  - All four are absorbed: `git archive <sha>`, a fingerprint taken from git blobs, and the snapshot step deleted.
- **Shared DeployHistory:** the fleet's PriorSha is the latest OK row of any kind, so server rows would corrupt it. Absorbed: queries are scoped by `HostsAttempted`.
- **App factory side effects:** two contract tests construct `WebServiceApp()`, which runs supersede (it can kill a live local WebService) and the single-instance gate. Absorbed: the gate moves to `Main()`, the serving-process entry.
- **Signal 5 re-check:** the host role (worker or server) is data: unit body, identity env file, and requirements list. Both roles run the same host-sync call graph.

## Out of Scope

- (b) Pull-based CD agent, GitHub Actions CI, automatic fleet deploys, and taking I9 out of fleet deploys. These belong to the next directive, `push-to-deploy`.
- (b) Faster host code staging (artifact build, rsync link-dest). Belongs to the conditional directive `fast-code-staging`.
- (b) Plaintext *arr credentials in `docker-compose.yml` and the hard-coded Flask secret key. Pre-existing; filed as bugs, not fixed here.
- (a) The worker deploy pipeline keeps its shape. Its host-sync steps become role-driven, so the server reuses them instead of duplicating them. Two visible effects for workers:
  - They now receive committed content only (`git archive`).
  - Each worker host does a one-time venv rebuild, because the fingerprint now comes from git blobs.
- Worker drain is untouched. It stays mandatory per `worker-deploy.md`.
- (b) The UI's ServiceControl start/stop buttons act on processes local to the WebService host. After cutover they act on the server, not I9. This is pre-existing design; filed.
- (b) WebService init swallows SchemaChecker and WorkerContext failures as warnings. Contract tests that build the app also start its background runners. Both pre-existing; filed.

## Constraints

- Provisioning goes through the infra repo pipeline (`server-deploy.py`, then `app-deploy.py`). The operator approves the terraform apply.
- Versioned dirs follow the same rules as the workers: `src-<sha>` and `host-venv-<fp>` are never mutated after creation, the unit renders resolved paths, and GC keeps 5.
- The deploy ships only the committed tree of a sha reachable from `origin/main` (`git archive`). Any other sha is refused, and local working-tree state is irrelevant.
- No new operator-tunable knob without a GUI handler (`gui-editable-knobs.md`).
- Fail loud: a start failure is a non-zero exit, never a silent fallback.

## Escalation Defaults

- Speed vs. safety of the start check -> safety. Never report OK before the new release answers HTTP.
- Risk tolerance: low. This host becomes the single control plane.

## Engineering Calls Already Made

- The container is a new LXC on larry with media bind mounts matching CT 218 and the nginx proxy enabled. Starting size: 4 vCPU, 8 GB RAM, 32 GB disk.
- Rollback re-points the unit at the prior `src-<sha>` / `host-venv-<fp>` and restarts. Nothing is rebuilt.
- One command for deploy and rollback, a thin entry over the shared host-deploy pipeline.

## Status

Phases advance by editing the `**Status:**` header line at the top of this file: `**Status:** Active -- phase: <NEXT>`. The PreToolUse hook reads ONLY that header line (NOT this section). See `.claude/standards/index.md` for the phase machine.

### Plan

1. **Infra row (infra repo).**
   - Insert `mediavortex-server` into infra-db `services` as `inventory_rw`, under `SET LOCAL app.actor`. Values:
     - vmid 237, ip 10.0.0.49, port 5000
     - internal, proxy=true, `proxmox_lxc` on larry, ct
     - 4 cores, 8192 MB, 32 GB, privileged, nesting
     - CT 218's three bind mounts
     - ssh root, monitor ct, backup true, `app_type none`, tags mediavortex+server
   - Run `regenerate-inventory-toml.sh` and commit in the infra repo.
2. **Host sync takes a role and a sha** (`deploy/deploy-baremetal-worker.py`).
   - New args: `--role worker|server` (default worker) and `--sha` (default HEAD).
   - A role table supplies the unit file name and body, the identity env file(s), and one requirements list. That list feeds both the fingerprint and `pip install -r ...`.
   - Source: `git archive <sha>` is piped over ssh into `src-<sha16>.tmp`, VERSION is stamped, and the dir is renamed to `src-<sha16>`. An existing dir whose VERSION matches is reused and touched.
   - The fingerprint hashes the git blobs of the role's requirements at `<sha>`. A reused venv is touched so mtime GC never removes it.
   - Delete `SyncSource.py`, `.deployignore`, StepStampVersion, and StepShipSchemaSnapshot. Deleted-code buckets:
     - **Pure redundancy:**
       - SyncSource and `.deployignore` are replaced by the archive. The archive ships no untracked files, and the excluded tracked files (`.claude/*`, about 20 MB total) are harmless.
       - StepStampVersion is folded into the archive step.
       - StepShipSchemaSnapshot re-shipped a file git already tracks.
     - **Replaced:** WebService's `GetWorkerConfig` ffmpeg lookup becomes discovery, which returns the same `FFmpegMaster` path on I9.
   - Server role:
     - Unit `mediavortex-server.service` with `Restart=always`.
     - Identity file `/etc/mediavortex/server.env` (`MEDIAVORTEX_WORKER_NAME=mediavortex-server`).
     - Requirements: root + `WebService`.
3. **`deploy/deploy-server.py [--sha S | --rollback]`.**
   - Target: `origin/main` after `git fetch`. `--sha` must be an ancestor of `origin/main`. `--rollback` uses the PriorSha of the latest OK server row.
   - PriorSha = VERSION in the running unit's WorkingDirectory.
   - Insert a DeployHistory row (`HostsAttempted='mediavortex-server'`, RUNNING).
   - Run the host sync with `--role server --sha`, `systemctl restart`, then poll `/api/Version` until its Sha equals the target (60s deadline).
   - On failure: re-run the same steps for PriorSha, mark the row FAILED with the reason, and exit 1.
   - On success: mark the row OK.
   - Print per-step timings.
   - The fleet's PriorSha query excludes server rows.
4. **WebService identity and version.**
   - `Main()` resolves `MEDIAVORTEX_WORKER_NAME` (exit 1 if unset), runs supersede and the single-instance gate, then builds `WebServiceApp(InstanceName)`.
   - WorkerContext gets InstanceName plus FFmpeg/FFprobe paths from `FFmpegService.FindFFmpegPath/FindFFprobePath`, made static. The server gets no Workers row.
   - `Core/CodeVersion.py` holds the sha resolver, extracted from WorkerService `_ResolveWorkerVersion`; WorkerService delegates to it. WebService resolves the sha once at startup.
   - `GET /api/Version` returns `Data: {Sha, Instance}`.
   - The startup ScanJobs cleanup is narrowed to `WorkerName = InstanceName`.
   - The two contract tests that build the app pass an instance name.
5. **Single instance across hosts.**
   - Migration `AddServiceStatusInstanceName`: nullable `InstanceName TEXT`. Regenerate the schema snapshot.
   - `RegisterServiceStartup` refuses when the row's InstanceName is set, differs from this instance's, and `UpdatedAt` is within 90s (three 30s heartbeats). Otherwise the existing local-PID logic applies, and registration writes InstanceName.
   - Supersede acts only when the recorded InstanceName equals this instance's.
6. **I9 dev.**
   - `StartMediaVortex.py` launches WorkerService only.
   - `deploy-worker.py` `RestartWindowsLocal` stops restarting WebService.
   - WinTmp gets `; sys_platform == "win32"`, in its own commit (that commit is the C6 drill target).
7. **SRR seed.** `SeedServerStorageRootResolutions.py` is an idempotent upsert of 3 linux rows for `mediavortex-server` (T `/mnt/media_tv/`, M `/mnt/movies/`, X `/mnt/xxx/`), via `RegisterStorageRootResolutions`.
8. **Linux import probe.** On CT 218, run `import WebService.Main` from an extracted archive using the host venv plus a `--target` dir for waitress and flask-compress. The worker venv is not modified.
9. **Tests.**
   - Blob fingerprint: stable per sha and role.
   - CodeVersion: VERSION vs `.git/HEAD`.
   - `/api/Version` route.
   - `RegisterServiceStartup` cross-host refusal, using a test-only ServiceName row.
   - Run TestFailLoud plus the deploy contract tests.
10. **Operator runbook** (`deploy/bringup.md`), the "ready, please execute" steps:
    1. `server-deploy.py --name mediavortex-server` (approve the terraform apply).
    2. Stop the WebService on I9.
    3. `py deploy/deploy-server.py`.
    4. Smoke C1-C9: reboot, rollback, a C6 drill with `--sha <WinTmp commit>` (no `/api/Version`), and a second WebService on I9 being refused.
    5. Fleet deploy: verifies the worker path and the one-time venv rebuild.

### Seams

Changed or added by this directive. Existing worker seams are in `worker-deploy-baremetal.flow.md`.

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| N1 | identity -> WebService | host sync writes `/etc/mediavortex/server.env` | `MEDIAVORTEX_WORKER_NAME=mediavortex-server` | `WebService/Main.Main` exits 1 if unset | `/api/Version` Data.Instance |
| N2 | identity -> path resolution | SRR seed | 3 rows (StorageRootId 1-3, linux, `/mnt/...`) | `Core/Path/Worker.py` resolves media paths | C8 remeasurement completes |
| N3 | ServiceStatus across hosts | `RegisterServiceStartup` + 30s heartbeat | `InstanceName TEXT NULL`, `UpdatedAt` set by DB `NOW()` | another host refuses when fresh (<90s) and different | contract test + C9 drill |
| N4 | running sha | host sync stamps `src-<sha16>/VERSION` | 40-char sha | `/api/Version` Data.Sha == target | C3, C4 |
| N5 | DeployHistory | `deploy-server.py` | one row, `HostsAttempted='mediavortex-server'` | fleet PriorSha excludes server rows; rollback reads latest OK server row | SQL after deploy and rollback |
| N6 | sha -> src tree | `git archive <sha>` | committed tree + VERSION, renamed into place | unit WorkingDirectory; never mutated | same-sha redeploy reuses dir |
| N7 | requirements -> venv | blob fingerprint per role | sha256(variant, torch pin, role file blobs) | `host-venv-<fp16>` + `.deps-fingerprint` | unit test; SKIPPED when unchanged |
| N8 | ffmpeg discovery | `FFmpegService.FindFFmpegPath` | absolute path or None | `WorkerContext.FFmpegPath` for EBU R128 | C8 |

### Files

```
C:\Code\infrastructure (infra-db row + regenerated terraform\inventory.toml) -- mediavortex-server LXC on larry
deploy/deploy-baremetal-worker.py                 -- EDIT: role table, --sha, git archive, blob fingerprint, touch on reuse
deploy/SyncSource.py, .deployignore               -- DELETE: replaced by git archive
deploy/deploy-server.py                           -- CREATE: one-command server deploy + rollback
deploy/deploy-fleet.py                            -- EDIT: PriorSha excludes server rows
deploy/common.py                                  -- EDIT: shared server target name
deploy/deploy-worker.py                           -- EDIT: I9 path stops restarting WebService
deploy/worker-deploy-baremetal.flow.md            -- EDIT: host deploy with roles, git archive
deploy/bringup.md                                 -- EDIT: server bring-up + cutover runbook
StartMediaVortex.py                               -- EDIT: no longer launches WebService
WebService/Main.py                                -- EDIT: identity + gate in Main(); ScanJobs cleanup scoped; app version
WebService/requirements.txt                       -- EDIT: WinTmp platform marker
WebService/startup.flow.md                        -- EDIT: server host, identity, systemd lifecycle
WebService/single-instance-startup.feature.md     -- EDIT: single instance across hosts
WorkerService/Main.py                             -- EDIT: version resolver delegates to Core/CodeVersion.py
Core/CodeVersion.py                               -- CREATE: running-sha resolver
Services/FFmpegService.py                         -- EDIT: FindFFmpegPath/FindFFprobePath static
Features/ServiceControl/ServiceStatusService.py   -- EDIT: host-aware RegisterServiceStartup
Features/ServiceControl/ServiceControlRepository.py -- EDIT: fresh-other-instance query
Features/ServiceControl/ServiceStatusController.py -- EDIT: GET /api/Version
Scripts/SQLScripts/AddServiceStatusInstanceName_2026_11_11.py -- CREATE: idempotent migration
Scripts/SQLScripts/SeedServerStorageRootResolutions.py -- CREATE: idempotent SRR seed
.claude/schema/snapshot.json                      -- REGENERATE: ServiceStatus.InstanceName
Tests/Contract/TestFarmServer.py                  -- CREATE: fingerprint, CodeVersion, /api/Version, cross-host gate
Tests/Contract/TestWorkBucketController.py, TestTranscodingSettingsRoundTrip.py -- EDIT: pass instance name
DOMAIN.md, .claude/rules/worker-deploy.md         -- EDIT: git archive, server role
WorkerService/WorkerService.flow.md, WorkerService.feature.md -- EDIT: version stamp via archive; C8 I9 launches WorkerService only
Features/ServiceControl/ServiceControl.feature.md  -- EDIT: C9 launcher scope; RegisterServiceStartup signature
transcode.flow.md                                  -- EDIT: ServiceLifecycleManager section (server hosts WebService)
memory/KNOWN-ISSUES.md                            -- EDIT: BUG-0064 resolved; file OOS (b) items
```

### Promotions

Required when phase advances to DELIVERING. The hook refuses Status `Active -- phase: DELIVERING` -> `Closed` if this section is empty.

Each row promotes durable content out of this directive into its permanent home (feature/flow doc). On close, the archive keeps only the pointer table -- the design content lives in the target file.

| Source artifact | Target file | Commit |
|---|---|---|
| `<what content / decision>` | `<path/to/target.feature.md or .flow.md>` | `<sha or "TBD until close">` |

If a row's content is "new vertical entirely" or "new pipeline entirely," the Target is a NEW `*.feature.md` / `*.flow.md` -- R13 allows creation during DELIVERING for exactly this case (`.claude/rules/doc-layering.md`).

If a directive has no durable content to promote (e.g. pure bugfix, no contract change), list one row: `no promotions | n/a | <reason>`. The hook only checks the section is non-empty.

### Verification

Required when phase advances to VERIFYING. One entry per acceptance criterion. Concrete evidence (command output, SQL result, file path) -- not "tested it works."

Pre-smoke (47589757):
- `TestFarmServer` 10 passed. `TestClaimAuthority`, `TestDeployPipInstallsRequirementsTxt`, and `TestDeployIdempotenceInvariants` pass (44 passed), except the pre-existing BUG-0116 failure.
- Linux import probe on CT 218 (python 3.12.3, host venv plus a `--target` dir with waitress 3.0.2 and flask_compress 1.26): `import WebService.Main, Core.CodeVersion, ServiceStatusController` -> `IMPORT_OK True`.
- Migration `AddServiceStatusInstanceName` and the SRR seed applied live.

Smoke (2026-11-12, CT 237 at 10.0.0.49, server on 1a6bb82c):
- **C1:** `GET http://10.0.0.49:5000/` 200 and `GET http://mediavortex-server/` 200 (nginx, name resolved via Pi-hole); the I9 WebService had not been running.
- **C2:** `pct reboot 237`; the container's `uptime -p` read "up 0 minutes", the unit started 2s after boot, and `/api/Version` answered 200 after 8s with no operator action.
- **C3:** `GET /api/Version` -> `{"Sha":"1a6bb82c6e4ef6abb9dbadb070c111fb93773a94","Instance":"mediavortex-server"}`.
- **C4:** `deploy-server.py --sha 47589757` (deps unchanged) -> `== SERVER ON 47589757 ==`, total 9.8s (DeployHistory Id=77, ElapsedSeconds 9). The first deploy built the venv: 183s (Id=76).
- **C5:** `deploy-server.py --rollback` -> `== SERVER ON 1a6bb82c ==`, total 7.6s (Id=78); `/api/Version` showed 1a6bb82c.
- **C6:** `deploy-server.py --sha ea0b57a5` -> `/api/Version` 404 for 60s, reverted to 1a6bb82c, exit 1, row Id=79 `FAILED` ("revert to 1a6bb82c OK"); `/api/Version` showed 1a6bb82c afterwards.
- **C7:** `SELECT ... FROM DeployHistory WHERE HostsAttempted='mediavortex-server'` -> Ids 76 OK, 77 OK, 78 OK, 79 FAILED, each with PriorSha, NewSha, ElapsedSeconds.
- **C8:** `/mnt/media_tv` (777 entries), `/mnt/movies` (3473) and `/mnt/xxx` (9) are visible on the server; ffmpeg at `/usr/local/bin`. `AudioRemeasurementService.MarkForRemeasurement(16802)`; within 30s the server's runner (the only one running) cleared `AdmissionDeferReason` and rewrote the loudness values through `/mnt/media_tv`. Before: LUFS -20.0, LRA 8.3, TP -2.2, threshold -30.8. After: -15.4, 4.4, -3.0, -25.9.
- **C9:** `MEDIAVORTEX_WORKER_NAME=I9-dev; py WebService/Main.py` on I9 printed "WebService is already running. Preventing duplicate instance." and exited 1. `StartMediaVortex.py` launching only WorkerService is asserted by `TestDeployAssignedIdentity`. UNVERIFIED live: a fleet deploy leaving I9 without a WebService (no fleet deploy run yet).

### Decisions Made

Engineering calls made under ambiguity during execution. These live with the directive (not with features/flows) because they describe THIS directive's reasoning, not the vertical's contract.

- **VMID 237 / IP 10.0.0.49.** 237 is the next free VMID on larry. 10.0.0.48 answers ping but is missing from inventory, so it is skipped.
- **nginx internal-only.** MediaVortex has no auth and includes an ad-hoc SQL page.
- **`app_type none`.** `deploy-server.py` owns the app install, not the infra app-deploy step.
- **No Workers row for the server.** It is not a claim target. It gets SRR rows only (deploy-time path plumbing). There is no SRR GUI for any identity today.
- **The role is a `--role` argument, not an inventory field.** infra-db `services` has a fixed column list.
- **The server unit body lives inline in the role table,** matching the worker unit. No separate template file.
- **`git archive` replaces `SyncSource.py`.** It ships committed content only (about 20 MB, under 1s to build) and never writes into an existing `src-<sha>`.
- **The fingerprint comes from git blobs at the deployed sha.** Cost: a one-time venv rebuild (torch reinstall) on each worker host at the next fleet deploy.
- **Rollback = PriorSha of the latest OK server row.** A second rollback toggles back.
- **Cross-host liveness = heartbeat freshness under 90s, not the Status column.** WebService never writes Running, and it exits on SIGTERM without updating the row.
- **The single-instance gate lives in `Main()`.** Building the app (tests) has no effect on other instances.
- **C6 drill: deploy the WinTmp-marker commit.** Its deps install, but it has no `/api/Version`, so verification fails and the deploy reverts to the prior sha.
- **Infra row needed `disk_storage = zfs-containers`.** larry has no `local-lvm`; without it `pct create` failed while Terraform recorded success. The CT was created on the second apply after tainting the false-success resources.
- **Short name, not FQDN.** nginx serves `http://mediavortex-server` (internal bare-name convention); `generate-dns.py --dns-only` was run to publish the record instead of waiting for the 15-minute reconcile.
- **Prometheus target needs root on 10.0.0.239.** The live Prometheus runs from `/root/code/infrastructure/monitoring/docker-compose.monitoring.yml` (a root-owned checkout of the infra repo), not `~/monitoring`; `adroit` cannot read it and has no passwordless sudo, so the target is not live. The infra skill's `scp ~/monitoring/prometheus.yml` step writes a stale unused copy and is out of date. Infra commits are pushed (`d846b98`); the remaining step is a `git pull` plus recreate of the prometheus container as root.
- **Jellyfin sync fixed (BUG-0117).** Dedicated key on the server, authorized for `adroit@10.0.0.179`, `JellyfinSSHKeyPath` set to `/root/.ssh/mediavortex_jellyfin`.
- **One real row remeasured for C8.** MediaFiles Id 16802 was flagged and remeasured by the server's runner; its original loudness values are recorded under Verification.
- **BUG-0064 closed, not carried.** Its three asks are now either met (independent remote deploys, worker-deploy.md rule 2) or no longer apply (I9 local-start policy; a single strategy script, replaced by roles of one sync script).
- **BUG-0113 is filed, not fixed.** Making WebService init fail loudly breaks two contract tests that build the app twice in one process (the second `WorkerContext.Initialize` raises). Fixing it needs a test-fixture change outside this scope.
- **The host sync runs `apt-get update` before installs, and the ffmpeg install is verified (fail-loud).** A fresh CT that never ran the bare-metal bootstrap has an empty apt cache.

---

## Closure (thin-pointer archive shape)

When this directive is ready to close:

1. **Confirm Promotions table is complete.** Every piece of durable content from this directive has a row pointing at its permanent home. The hook will refuse the close otherwise.
2. **Confirm directive did not grow during DELIVERING.** The hook recorded a size snapshot at IMPLEMENTING -> DELIVERING transition; the close is refused if the directive grew by more than the configured tolerance (default 10%). Growth during DELIVERING means content was DUPLICATED into the directive rather than PROMOTED out -- fix by moving the content to its target file and shrinking the directive.
3. **Update Promotions table with commit SHAs** (the commits where each promotion landed).
4. **Change `Status: Active -- phase: DELIVERING` -> `Status: Closed -- Success | Partial | Abandoned`.** Add a `**Closed:** YYYY-MM-DD` line under Set.
5. **Archive:**

   ```powershell
   git mv .claude/directive.md .claude/directives/closed/YYYY-MM-DD-<slug>.md
   Copy-Item .claude/directives/_template.md .claude/directive.md
   ```

   The renamed file becomes the archived record; `git log --follow` traces it.

The archived directive holds these sections only:

| Section | Content |
|---|---|
| Outcome | (restated; what was true at the start of the ask) |
| Acceptance Criteria | (restated; the contract that gated success) |
| Promotions | (the pointer table -- source artifacts and where they live now) |
| Verification | (per-criterion evidence) |
| Decisions Made | (engineering calls made under ambiguity) |

The archive does NOT hold:

- Design content that lives in a feature/flow doc (read the target file instead -- this is the whole point of promotion)
- In-flight planning notes or transient operational state (these served their purpose during execution; they don't belong in the historical record)
- Re-derivations of standards or rules (those live in `.claude/rules/`)

If a future reader wants to know what a vertical does, they read its feature doc. If they want to know why a directive made the choices it made, they read the archived directive's Decisions Made and Verification sections. If they want to know what was promoted, they follow the pointers in the Promotions table.

This shape is governed by `.claude/rules/doc-layering.md` (the three-tier model) and `.claude/rules/ceo-mode.md` (the directive lifecycle).
