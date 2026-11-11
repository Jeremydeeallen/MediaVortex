# Current Directive

**Set:** 2026-11-11
**Status:** Active -- phase: NEEDS_STANDARDS_REVIEW
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

Initial findings from discovery; to be completed during NEEDS_STANDARDS_REVIEW.

- **Signal 1 (two flow docs for one operation):** a new server-deploy flow would duplicate `deploy/worker-deploy-baremetal.flow.md`, because both deploy versioned code to a Linux host as a systemd service. Resolution: generalize that flow to a host deploy with a role per service (worker, server). Do not add a parallel flow doc. This also closes BUG-0064 (single deploy script, one strategy per host shape).
- **Signal 2 (mode branch at orchestration):** `deploy/deploy-worker.py` `RestartWindowsLocal` (L93-104) restarts WebService inside the I9 worker path. This directive removes that WebService restart. The remaining I9 branch is handled by `push-to-deploy`, which leaves I9 out of automatic deploys by data, not by a flag.
- **Signal 3 (output columns filled sparsely):** a server deploy must fill every DeployHistory column a fleet deploy fills (PriorSha, NewSha, ElapsedSeconds, HostsAttempted, HostsSucceeded, Outcome, ErrorMessage).
- **Signal 5 (config changes which code runs):** none found. Every host runs the same `WebService/Main.py` startup path; only the deploy-assigned env values differ.
- **Seam, WebService identity:** `WebService/Main.py` L132 takes its identity from `socket.gethostname()`. That identity selects ffmpeg paths and path resolution for audio remeasurement. It already violates `claim-authority.md` (identity must be deploy-assigned), and on the server it becomes load-bearing, so it is absorbed here. Identity will come from a deploy-assigned env var. The server identity gets share mappings, but no capability that makes its rows a claim target.
- **Seam, single instance across hosts:** `WebService/Main.py` `_SupersedeExistingInstance` (L224-295) and `ServiceStatusService.RegisterServiceStartup` (L135) compare the recorded PID only against the local host. A WebService on another host sees the server's PID as stale and starts anyway. Absorbed here (criterion 9).
- **Seam, Windows-only dependency:** `WebService/requirements.txt` L28 `WinTmp` cannot install on Linux. It gets a platform marker.

## Out of Scope

- (b) Pull-based CD agent, GitHub Actions CI, automatic fleet deploys, and taking I9 out of fleet deploys. These belong to the next directive, `push-to-deploy`.
- (b) Faster host code staging (artifact build, rsync link-dest). Belongs to the conditional directive `fast-code-staging`.
- (b) Plaintext *arr credentials in `docker-compose.yml` and the hard-coded Flask secret key. Pre-existing; filed as bugs, not fixed here.
- (a) The worker deploy pipeline keeps its behavior. Only shared host-deploy steps are factored out, so the server reuses them instead of duplicating them.
- Worker drain is untouched. It stays mandatory per `worker-deploy.md`.

## Constraints

- Provisioning goes through the infra repo pipeline (`server-deploy.py`, then `app-deploy.py`). The operator approves the terraform apply.
- Versioned dirs follow the same rules as the workers: `src-<sha>` and `host-venv-<fp>` are never mutated after creation, the unit renders resolved paths, and GC keeps 5.
- The deploy refuses a dirty tree or a sha that is not on `origin/main`.
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

### Files

```
C:\Code\infrastructure\terraform\inventory.toml   -- EDIT (infra repo): mediavortex-server LXC entry on larry
deploy/deploy-baremetal-worker.py                 -- EDIT: shared host-deploy steps take a role (worker | server)
deploy/deploy-server.py                           -- CREATE: one-command server deploy + rollback
deploy/mediavortex-server.service                 -- CREATE: systemd unit template, resolved versioned paths
deploy/deploy-worker.py                           -- EDIT: I9 path stops restarting WebService
deploy/worker-deploy-baremetal.flow.md            -- EDIT: host deploy with roles
deploy/bringup.md                                 -- EDIT: server bring-up + cutover runbook
StartMediaVortex.py                               -- EDIT: no longer launches WebService
WebService/Main.py                                -- EDIT: deploy-assigned identity; host-aware single instance
WebService/requirements.txt                       -- EDIT: WinTmp platform marker
WebService/startup.flow.md                        -- EDIT: server host, identity, systemd lifecycle
WebService/single-instance-startup.feature.md     -- EDIT: single instance across hosts
Features/ServiceControl/ServiceStatusService.py   -- EDIT: host-aware RegisterServiceStartup
Features/ServiceControl/ServiceStatusController.py -- EDIT: running-sha endpoint
.claude/rules/worker-deploy.md                    -- EDIT (operator approval): server role
memory/KNOWN-ISSUES.md                            -- EDIT: BUG-0064 resolved; file *arr creds + secret key bugs
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

- **Criterion 1:** `<evidence>`
- **Criterion 2:** `<evidence>`

### Decisions Made

Engineering calls made under ambiguity during execution. These live with the directive (not with features/flows) because they describe THIS directive's reasoning, not the vertical's contract.

- `<decision + one-line rationale>`

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
