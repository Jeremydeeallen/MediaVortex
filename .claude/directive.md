# Directive: docker-purge

**Status:** Active -- phase: IMPLEMENTING

**Opened:** 2026-07-31
**Parent (paused):** deploy-worker-identity-invariants
**Slug:** docker-purge

## Outcome

Delete every docker reference from active MediaVortex code, docs, comments, memory, tests, and configuration. MediaVortex is baremetal-Linux + Windows-native only. No docker path remains. Nobody discovering the repo six months from now finds a stale docker instruction.

**Not touched (per operator):** closed directives under `.claude/directives/closed/*`, `memory/KNOWN-ISSUES-ARCHIVE.md`, historical CSV reports under `Reports/`, vendored `Static/vendor/fontawesome.min.css`.

## Acceptance Criteria

C1. **`grep -rn "docker\|Docker\|DOCKER"` returns zero hits** across the tree, excluding the four archive locations above. Case-insensitive. Verified by a contract test that fails loud on any new hit outside the whitelist.

C2. **`deploy/Dockerfile` and `.deployignore` are deleted.** No dockerfile artifacts survive.

C3. **`deploy/deploy-linux-worker.py` is deleted.** Its role (docker-image build + push) no longer exists. `deploy/deploy-baremetal-worker.py` covers Linux; `deploy/deploy-windows-worker.py` covers Windows.

C4. **`deploy/worker-deploy-linux.flow.md` is deleted.** Baremetal flow replaces it. `deploy/bringup.md`, `deploy/worker-deploy.feature.md`, and every referrer update their shape table + cross-refs to name only baremetal + Windows.

C5. **`deploy/deploy-worker.py` and `deploy/deploy-fleet.py`** dispatch on shape from `inventory.toml` with two options only: baremetal (Linux) + Windows. Any code path branching on "docker" is removed.

C6. **BUG-0085 (docker build-cache stale-`.pyc`)** is moved from `memory/KNOWN-ISSUES.md` Active to `memory/KNOWN-ISSUES-ARCHIVE.md` marked "resolved by docker-purge (2026-07-31): platform no longer supports the failure mode."

C7. **Memory index cleanup.** `MEMORY.md` entries `reference_worker_containers_on_larry.md`, `reference_docker_exec_pid_namespaces.md`, `feedback_ms_nfs_client_unreliable.md` rewritten or deleted to reflect baremetal reality. `reference_worker_host_hardware.md` no longer points at `deploy/compose-templates/<host>.yml` (empty dir); points at `infrastructure/terraform/inventory.toml` or baremetal equivalent.

C8. **Feature/flow doc updates.** Every `*.feature.md` / `*.flow.md` outside archives strips docker language. Cross-refs to Docker-only paths get replaced or deleted. Doc-layering rule respected (feature vs. flow scope).

C9. **DB shape.** `Workers.Platform='linux'` values remain (baremetal linux still is linux). No docker-specific columns exist; no schema change required. Confirm by inspection.

C10. **Contract test lands.** `Tests/Contract/TestNoDockerReferences.py` greps the tree per C1 and fails on any new reference outside the whitelist. Whitelist enumerated explicitly (no wildcard directory globs).

C11. **`Scripts/SQLScripts/_*_shards.sh`** helpers refer to docker exec patterns. Since larry LXC 218 now runs systemd not docker, rewrite these to hit the systemd workers OR delete if unused. Grep for callers first.

C12. **`.claude/settings.local.json`** entries for docker-related Bash permissions are removed (21 hits — likely `Bash(docker:*)` patterns). Cannot claim useful.

C13. **`.claude/rules/worker-deploy-drain.md` + `.claude/rules/claim-authority.md`** cross-refs to docker are removed. Both rules are platform-agnostic; the docker mentions are illustrative + can be updated to baremetal or deleted.

## Call-Graph Audit

Populated before advancing NEEDS_STANDARDS_REVIEW -> NEEDS_PLAN. Four signals:

1. **Multiple flow docs for one conceptual operation:** `worker-deploy-linux.flow.md` + `worker-deploy-baremetal.flow.md` describe the same conceptual op (Linux worker bring-up). Docker path is dead. Delete the linux (docker) flow; baremetal absorbs the Linux slot. Windows keeps its own doc (genuinely different shape).

2. **Mode-branching at orchestration:** `deploy/deploy-worker.py` currently branches on shape ("docker" vs. "baremetal" vs. "windows"). After purge: two shapes only. Strategy pattern intact — no `if platform == 'docker'` in orchestration.

3. **Shared output columns sparsely populated:** `Workers.BuildInfo` currently carries docker BuildKit strings (`built_by=buildkitsandbox`) for larry rows and I9-hostname strings elsewhere. Not a mode-branch — same column, same producer (deploy script stamps it), different content. No change needed but format consolidation is an option.

4. **OOS ambiguity:** Out-of-scope items enumerated below with (a) / (b) classification.

## Out of Scope

- **`Static/vendor/fontawesome.min.css`** — (b) known-preserved. Vendored asset; docker icon shipped by fontawesome library; will be re-added on next update. Leave.
- **`Reports/OrphanFailedAttempts-2026-07-13-102950.csv`** — (b) known-preserved. Historical data snapshot; contains embedded docker paths from that day's report.
- **`memory/KNOWN-ISSUES-ARCHIVE.md`** — (b) known-preserved. Archive of resolved issues; docker mentions are historical.
- **`.claude/directives/closed/*.md`** — (b) known-preserved. Closed directive history; docker mentions capture the rationale for past decisions.
- **Stale DB rows** (`larry-worker-1..4`, `wakko-3/4`, `dot-3/4` with heartbeats hours old) — (a) not addressed here; DB cleanup is a separate directive if operator wants it.
- **Docker binary presence on hosts** (dot still has `/usr/bin/docker` installed) — (a) not addressed here; host hygiene is infrastructure repo's job, not MediaVortex's.

## Files (planned)

To delete:
- `deploy/Dockerfile`
- `deploy/deploy-linux-worker.py`
- `deploy/worker-deploy-linux.flow.md`
- `.deployignore`

To edit (strip docker refs):
- `deploy/deploy-worker.py`, `deploy/deploy-fleet.py`, `deploy/deploy-baremetal-worker.py`, `deploy/deploy-windows-worker.py`, `deploy/bringup.md`, `deploy/worker-deploy.feature.md`, `deploy/worker-deploy-baremetal.flow.md`, `deploy/worker-deploy-windows.flow.md`, `deploy/version-on-deploy.feature.md`
- `ARCHITECTURE.md`, `DOMAIN.md`, `GLOSSARY.md`, `e2e-bug-fixes.feature.md`, `mac_monitoring_setup.md`
- `WorkerService/WorkerService.feature.md`, `WorkerService/WorkerService.flow.md`, `WorkerService/Main.py`
- `Docs/bottleneck-analysis.flow.md`
- `Features/MediaFiles/mediafiles-uniqueness-owner.feature.md`, `Features/ServiceControl/graceful-drain.feature.md`, `Features/ServiceControl/CrashRecoveryService.py`
- `Features/TeamStatus/worker-versioning.feature.md`, `Features/TranscodeJob/local-staging.feature.md`, `Features/TranscodeJob/Emit/CommandComposer.py`, `Features/TranscodeJob/VideoTranscodingService.py`
- `Services/FFmpegService.py`
- `Scripts/StampVersion.py`, `Scripts/ReconcileNvencCapability.py`, `Scripts/ReconcileQsvCapability.py`, `Scripts/MigrateSQLiteToPostgres.py`, `Scripts/SQLScripts/AddWorkerVersionColumn.py`
- `Scripts/SQLScripts/_launch_persistent.sh`, `Scripts/SQLScripts/_kill_shards.sh`, `Scripts/SQLScripts/_status_shards.sh`, `Scripts/SQLScripts/_launch_shards.sh` (rewrite to systemd OR delete)
- `Tests/Contract/TestDeployPipInstallsRequirementsTxt.py`
- `.claude/commands/mediavortex-deploy-worker.md`, `.claude/programs/db-authority-program.md`, `.claude/plans/goofy-squishing-cake.md`, `.claude/rules/claim-authority.md`, `.claude/rules/worker-deploy-drain.md`, `.claude/settings.local.json`
- `memory/KNOWN-ISSUES.md` (archive BUG-0085 to KNOWN-ISSUES-ARCHIVE.md)

To create:
- `Tests/Contract/TestNoDockerReferences.py`

Memory files to update:
- `MEMORY.md` + linked entries (`reference_worker_containers_on_larry.md`, `reference_docker_exec_pid_namespaces.md`, `feedback_ms_nfs_client_unreliable.md`, `reference_worker_host_hardware.md`)

## Progress

- [x] NEEDS_STANDARDS_REVIEW: call-graph audit populated (above)
- [x] NEEDS_PLAN: sequenced deletion + edit plan approved
- [x] NEEDS_DOC_PREREAD: read colocated docs during implementation
- [x] IMPLEMENTING: deletions + edits + test creation
- [x] VERIFYING: contract test green; grep returns zero hits outside whitelist
- [x] DELIVERING: promotions populated

### Promotions

| From (directive) | To (durable) |
|---|---|
| C1..C13 acceptance criteria (baremetal-only invariant) | `deploy/worker-deploy.feature.md` (Surface + criteria already reflect two shapes: baremetal + windows) |
| BUG-0085 stale-pyc archival | `memory/KNOWN-ISSUES-ARCHIVE.md` (appended with `resolved: 2026-07-31 by docker-purge`) |
| `Tests/Contract/TestNoDockerReferences.py` | new colocated contract test; guards C1 (no docker refs outside whitelist) |
| R4 hook allowlist extension (deploy scripts + Scripts/{Migrate,Stamp,Reconcile}*.py) | `.claude/hooks/pre-edit-standards.ps1` (Test-R4-NoEnvVars) |
| Baremetal cutover reality (Larry, wakko, dot all systemd) | `ARCHITECTURE.md`, `DOMAIN.md`, `GLOSSARY.md`, `Docs/bottleneck-analysis.flow.md` |
| Memory: baremetal is the only Linux shape | `reference_worker_containers_on_larry.md`, `reference_worker_host_hardware.md`, MEMORY.md index |

## Notes

- No new feature doc created. Purge is a cross-tree sweep; existing `deploy/worker-deploy.feature.md` is the durable contract that gets the "baremetal + Windows only" invariant promoted at DELIVERING.
- Untracked files at directive open (`Scripts/QueueNeededTranscodes300.py`, `restartI9Worker.py`) are out of scope; unrelated to parent slug + this directive.
- VERIFYING gate does not include a live worker deploy against every host — that's the operator's call whether to smoke-verify each shape post-purge. Contract test + grep + manual sanity read of key files satisfies "code is clean."
