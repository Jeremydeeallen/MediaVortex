# Closed Directive: Version on Deploy

**Set:** 2026-05-27
**Closed:** 2026-05-27
**Status:** Closed -- Success (operator marked PASS; full PASS pending one I9 worker restart, operator authority)
**Replaces:** `directives/closed/2026-05-27-transcode-pipeline-happy-path.md` (closed Success, all 7 criteria verified)

## Outcome

The /Activity page is the single source of truth for "what code is running on every worker right now." After a deploy lands, the operator sees the new SHA on /Activity within one poll without taking any extra action. There is no way for the displayed version to drift from the running code -- no live resolution, no half-stamped artifact, no special case for the dev-workstation-hosted worker.

## Acceptance Criteria

1. **/Activity displays each worker's running version.** Per-worker tile shows the short SHA; tooltip shows the full SHA plus `commit / built_at / built_by`. Workers with no resolvable version display "unknown" in a warning color.

2. **Displayed version equals the code the worker process loaded at startup.** No code path resolves the version from a live source that can change while the worker is running. Specifically, `_ResolveWorkerVersion` does not fall through to `git rev-parse HEAD` against a checkout an operator can commit to. The version is read from a deploy-stamped artifact (`VERSION` + `BUILD_INFO`) or it is "unknown."

3. **Every successful deploy stamps VERSION and BUILD_INFO on the target.** `deploy-linux-worker.py` (already does via Docker `--build-arg COMMIT_SHA`) and `deploy-windows-worker.py` (currently does not) both write the dev workstation's `git rev-parse HEAD` into `<repo>/VERSION` and a `BUILD_INFO` file containing `commit`, `built_at`, and `built_by` on the target before the worker restarts.

4. **Deploy verifies the version round-trip.** Both deploy scripts assert, as part of their post-restart verification, that `Workers.Version` for every worker on the target equals the SHA they just stamped. Mismatch causes the deploy to exit non-zero with the expected and actual SHAs in the error message.

5. **Fleet-wide mismatch is surfaced on /Activity.** When workers report different versions, the existing banner lists each version with its worker count. Workers reporting "unknown" are called out separately. (Existing capability -- no regression.)

6. **Displayed version updates without page reload after a deploy.** Operator's open /Activity page picks up the new SHA on the next periodic refresh, without any cache busting or manual reload. (Existing poll -- no regression.)

## Out of Scope

- Worker restart automation for Windows hot-swap (operator still runs the kill+restart sequence per `worker-deploy-windows.flow.md`)
- Build metadata beyond SHA / built_at / built_by (no semver, no release notes, no changelog)
- Automatic action on version mismatch beyond the existing banner (no auto-rollback, no auto-redeploy)
- I9-specific deploy automation that solves dirty-working-tree at deploy time (uncommitted local changes still ship, as today; deploy stamps the committed SHA only)

## Constraints

- No destructive schema changes (Workers.Version already exists)
- Preserve the existing /Activity per-worker tile + fleet-mismatch banner shape (no UI rework)
- Worker restarts are the operator's call on Windows (per existing memory -- Claude never starts services on I9)
- Scope-discipline.md applies per-task

## Escalation Defaults

- Tradeoff between code complexity and operator visibility -> operator visibility (verbose tooltip + full SHA in DB over short-only display)
- Tradeoff between deploy strictness and operator friction -> strictness (mismatch on verify fails the deploy)
- Risk tolerance: medium. Version drift is operator-visible but not safety-critical; favor correctness over conservatism.

## Engineering Calls Already Made

- VERSION + BUILD_INFO file shape stays consistent with the existing Docker build-arg artifact (`/opt/mediavortex/VERSION` and `/opt/mediavortex/BUILD_INFO`), so a single reader in `_ResolveWorkerVersion` covers both deploy paths.
- The fallback to "unknown" is preferred over `git rev-parse HEAD`; an honest "unknown" is more useful than a misleading SHA.
- Windows deploy will write the VERSION + BUILD_INFO file on the target via the existing SSH/PowerShell channel; no new auth or transport.

## Status

CLOSED 2026-05-27. Implementation in commit `c401ae6` plus follow-up doc + UI commits.

### Criteria verification

1. **/Activity displays each worker's running version.** PASS. `/api/TeamStatus/Workers` returns Version + multi-line BuildInfo per worker; render code at `Templates/Activity.html:540-550` produces `v: <sha7>` tile + tooltip. Unknown path renders in warning color.
2. **Version equals code worker process loaded at startup.** PASS on Linux fleet (verified live). PASS-conditional on Windows: I9 needs one operator restart for the new resolver and stamping to take effect. `grep "rev-parse" WorkerService/Main.py` returns zero hits inside the resolver.
3. **Every successful deploy stamps VERSION + BUILD_INFO.** PASS Linux (live: all 12 Linux workers have non-null BuildInfo with today's built_at). UNVERIFIED Windows (code shipped + AST-parsed, not yet executed against I9).
4. **Deploy verifies the round-trip.** PASS Linux happy path (three deploys reported `version=c401ae6`). UNVERIFIED Windows (code shipped, not exercised).
5. **Fleet-wide mismatch surfaced on /Activity.** PASS. Banner endpoint returns `AllAgree=false, MismatchCount=1` for current mixed-version fleet.
6. **Displayed version updates without page reload.** PASS by code inspection (existing `LoadWorkers` poll unchanged).

### Doc supersession sweep (closure gate)

| Doc | Action | Reason |
|---|---|---|
| `WorkerService/WorkerService.flow.md` | Updated | Version section rewritten: 2-state resolver + who writes the files on each platform |
| `Features/TeamStatus/worker-versioning.feature.md` | Marked superseded in part | Top-of-doc block points at `deploy/version-on-deploy.feature.md`; original criteria preserved as historical record |
| `deploy/worker-deploy-linux.flow.md` | Updated | Post-deploy verify SELECT gained Version column + expected-value text |
| `deploy/worker-deploy-windows.flow.md` | Updated | Hot-swap stamp step removed (StartWorker.py now self-stamps); Step 5 verify gained Version column |
| `deploy/version-on-deploy.feature.md` | Owned by this directive | Progress + Files updated |
| `Features/TranscodeQueue/media-tabs-and-loudness.feature.md` | No action | Only a parent-reference mention; doesn't describe changed behavior |

### Engineering follow-ups (not part of this directive; filed for awareness)

- I9 restart pending operator (per memory rule: never touch a running service)
- `deploy/deploy-windows-worker.py` preflight still checks NFS port 2049 + `ClientForNFS-Infrastructure` -- stale from pre-SMB-cutover era, unrelated to this directive
- `StartWorker.py` still mounts NFS drives via `mount.exe` -- same stale era
