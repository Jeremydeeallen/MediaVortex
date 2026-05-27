# Current Directive

**Set:** 2026-05-27
**Status:** Active
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

In progress -- 2026-05-27. Discovery complete; feature doc + plan next.
