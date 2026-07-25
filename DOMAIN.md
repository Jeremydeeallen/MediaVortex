# MediaVortex Domain Decisions

Source of truth for domain-level "what does the system do and why" decisions.
Every entry answers ONE domain question with ONE committed decision.

Rules:
- Append-only. Old decisions get a `Superseded by <date>` line, never edit.
- No implementation details. Metric choices belong here; SQL columns and Python classes do not.
- Any code, rule, or table that answers the same question differently = refactor. This doc is the ratchet.
- Cross-check every new directive against this doc BEFORE opening.

## 2026-07-25 -- Who owns what (meta-rule)

Question: Who decides domain questions, and who implements them?

Answer: **Operator owns the WHAT and the WHY. Claude owns the HOW.**

- Domain decisions (what the system does, why it does it, which trade-offs are acceptable) come from the operator. Claude MUST NOT invent domain rationale (e.g. "GPU contention" as the reason for a rule when no test data exists). If a decision lacks stated rationale, record "operator instruction; no tested rationale" -- do not fabricate one.
- When Claude perceives a domain question that has not been answered, Claude MUST surface it to the operator and record their answer here BEFORE writing implementation. Claude does not choose between domain options; Claude implements the operator's chosen option.
- Every rule, contract test, code path, skill, and directive that touches a domain concern MUST be traceable to a `DOMAIN.md` entry. If it isn't, either the rule is wrong or the domain entry is missing.
- Correction pattern: when Claude puts speculation into memory or a rule and the operator flags it, Claude corrects the artifact + records the correction so the speculation doesn't propagate.

---

## 2026-07-23 -- Pipeline operators

Question: What operations does MediaVortex perform on a media file?

Answer: Four operators. Nothing else.

- **Skip** -- leave the file alone.
- **Remux** -- copy video stream, re-encode audio, change container.
- **AudioFix** -- copy video stream, re-encode audio, preserve container.
- **Transcode** -- re-encode video + audio + container.

Every file passes through a classifier that returns exactly one operator. The classifier is a decision function with five branches:

```
IF audio-only container            -> out of scope
IF source is efficiently transcoded -> Skip / Remux / AudioFix depending on other compliance
IF video codec not in allowlist    -> Transcode
IF container not in allowlist      -> Remux
IF audio needs normalization       -> AudioFix
ELSE                                -> Skip
```

Consequence: any proposed feature that doesn't map to one of the four operators or the five-branch decision = refuse. Non-destructive archive of source (`MediaFilesArchive`) always. Jellyfin notify on any change to a served file.

## 2026-07-23 -- Definition of "efficiently transcoded"

Question: When is a file "efficiently transcoded" so we should not re-encode?

Answer: **SourceKbps <= profile target kbps at the file's resolution.**

The comparison uses the assigned profile's `TargetKbps` for the file's resolution (from `ProfileThresholds`). If the source is already at or below that target, re-encoding cannot meaningfully reduce size at the operator's chosen quality tier.

Consequences:
- Efficient files are STILL eligible for Remux (if container is not compliant) and AudioFix (if audio needs normalization). Only the Transcode operator is suppressed.
- Files without an assigned profile cannot be evaluated for efficiency and land in the `Unclassified` bucket by default.
- Files with an assigned profile whose SourceKbps exceeds the target enter the Transcode operator via the standard compliance path.
- This decision RETIRES the codec-blind `bpp` gate and the total-bitrate `SizeMB/DurationMinutes` proxy. Both were removed in favor of the direct SourceKbps-vs-TargetKbps comparison.

## 2026-07-23 -- Transcode job boundary

Question: When does a Transcode job END?

Answer: **A Transcode job ends when ffmpeg returns exit code 0.** Nothing else.

`TranscodeAttempts.Success = TRUE` is written at that moment. Everything after -- disposition decision, quality testing, file replacement, Jellyfin notify -- runs in downstream contexts that CONSUME finalized transcode attempts. They do not extend the transcode job.

Downstream contexts, in order, each triggered by the prior stage writing its own terminal state:

1. **Disposition** -- reads a finished attempt + optional VMAF result, decides `Replace` / `Reject` / `Requeue` / `Pending` (VMAF needed).
2. **Quality Test** -- when Disposition = `Pending`, `QualityTestingQueue` gets a row; a QT worker claims, runs VMAF, writes result. Its own queue, own workers, own success semantic.
3. **File Replacement** -- executes the `Replace` decision. Renames output, archives source.
4. **Notify** -- Jellyfin refresh.

Each stage is a separate consumer that polls or is triggered by DB state written by its predecessor. Loose coupling. No single function orchestrating all five.

Consequences:
- The transcode claim (`ta_one_inflight_per_mfid`) releases when ffmpeg exits, not after downstream stages complete. Downstream stages don't need the claim -- they operate on a finalized attempt row.
- A downstream failure (dispatch error, PFR error, replacement error) is tracked in its OWN context. It does not overwrite `TranscodeAttempts.Success`. The transcode succeeded; the downstream step failed.
- The QT admission gate (`AddToQualityTestQueue`) must accept attempts with `Success = TRUE` (ffmpeg done, ready for downstream). It refuses only `Success = FALSE` (freeze marker: encode failed, do not test).
- Documented seams: see `transcode.flow.md` S2 (ST6 -> ST7) and S3 (ST7 -> ST8).

Historical note: commit `40cce5db` (2026-07-21, "Success semantic tightened to end-to-end pipeline") introduced a design that held `Success = NULL` through the entire pipeline including downstream stages. That commit ALSO added a `Success IS NULL` refusal in `AddToQualityTestQueue`, blocking the very seam the flow doc defines. Domain answered here supersedes that commit's design choice. Transcode ends at ffmpeg. Period.

## 2026-07-24 -- Worker identity and multi-instance-per-host

Question: How are worker identities assigned when a single host runs multiple worker instances?

Answer:

- Each worker process has exactly ONE stable identity: `{host}-worker-{N}` where N is a positive integer unique within the host.
- Multiple systemd instances on the same host produce DISTINCT worker identities. Two processes MUST NOT share a WorkerName.
- Slot assignment (which N a fresh process gets) is atomic: the process reserves the slot in the DB inside the same advisory-lock scope that computed it. No process ever returns a WorkerName without having written the row that claims it.
- Slot reclamation is heartbeat-driven: a slot whose last heartbeat is older than 2 minutes is stale and can be reclaimed by a fresh process. A slot with a fresh heartbeat is owned and MUST NOT be reassigned.

Consequences:

- If four systemd units start simultaneously on a host with no existing worker rows, they claim `{host}-worker-1`, `{host}-worker-2`, `{host}-worker-3`, `{host}-worker-4` -- one each. Collision-into-same-slot is a bug.
- WorkerName ties directly to the `MaxConcurrentJobs` semaphore, the claim queries, and every ownership check. Two processes with the same name = ownership invariant broken = concurrent claims on the same work.

## 2026-07-24 -- Worker responsibilities (DDD context)

Question: What does a Worker OWN and DO?

Answer:

- A Worker is a claim-driven executor. It polls queues its DB row says it is capable of (Transcode / Remux / QualityTest / Scan) and CLAIMS one unit of work at a time up to `MaxConcurrentJobs`.
- A Worker OWNS every attempt row it claims through that attempt's terminal state (Success = TRUE / FALSE). No other worker touches an in-flight attempt owned by another worker; the exception is `AttemptAbandonmentSweeper` which releases attempts whose owner has been Offline + heartbeat-stale for the configured window (`.claude/rules/claim-authority.md`).
- Worker capability + policy state (Status, TranscodeEnabled, RemuxEnabled, QualityTestEnabled, ScanEnabled, MaxConcurrentJobs, MaxCpuThreads, MaxConcurrentQualityTestJobs, AcceptsInterlaced) is OPERATOR-OWNED. Code MUST NOT overwrite these columns except via an explicit operator-facing action (GUI, CLI). Boot-time registration MAY set defaults on first INSERT but MUST NOT touch these columns on UPDATE.
- Deploy-derived columns (Platform, FFmpegPath, FFprobePath, Version, BuildInfo, nvenccapable, qsvcapable) are DEPLOY-OWNED. Deploy scripts write them; operator does not.

Consequences:

- Any code path that flips Status from Paused to Online without the operator explicitly asking (GUI action, CLI flag, WorkerService fresh-slot INSERT) is a bug.
- Any code path that resets MaxConcurrentJobs, QualityTestEnabled, TranscodeEnabled, etc. via a mass UPDATE is a bug.

## 2026-07-24 -- Deploy is idempotent, never destructive

Question: What can a deploy script do to the Workers table?

Answer:

- Deploy is IDEMPOTENT. Running it N times produces the same DB state as running it once. Operator-owned columns are unchanged across deploys.
- Deploy MAY: sync source code, restart systemd units, write deploy-owned columns (Version, FFmpegPath, FFprobePath, Platform, BuildInfo, capability probes), age heartbeats to force reclaim of dead slots.
- Deploy MUST NOT: `DELETE FROM Workers`, `UPDATE Workers SET Status=...` (bulk), touch operator-owned columns, or nuke any table that carries operator state.
- Deploy MUST NOT overwrite operator settings even indirectly (e.g., by deleting then re-inserting with defaults).

Consequences:

- The pattern `DELETE FROM Workers WHERE ... -worker-%` in deploy-baremetal-worker.py is FORBIDDEN.
- Any `COALESCE(Status, 'Online')` in deploy-fleet.py that treats a missing/NULL Status as Online during pre-drain capture is FORBIDDEN. Missing Status is a bug to fail loud on, not a value to default around.
- Deploy scripts MUST use ON CONFLICT DO NOTHING (for inserts of operator-owned defaults) or ON CONFLICT DO UPDATE with an explicit column list that excludes operator-owned columns.

Historical damage (2026-07-24): running `deploy-baremetal-worker.py` on dot + wakko flipped `dot-worker-{2,3,4}` and `wakko-worker-{2,3,4}` from Paused to Online because the DELETE nuked operator state and RestoreWorkerStatus captured post-COALESCE 'Online' as the Original. Same run caused four systemd processes on each host to all claim WorkerName='{host}-worker-1' because `_ClaimPrefixedWorkerName` returned a slot name without atomically writing the row, so all four processes read empty state and picked slot 1.

## 2026-07-25 -- Workers MUST be drained before deploy

Question: What must be true before a worker's WorkerService process restarts as part of a deploy?

Answer: **A worker MUST have `ActiveJobs=0` before its process restarts.** Killing an encoder mid-flight loses the work, produces `.inprogress` file orphans, corrupts audio-normalization scratch dirs, and forces a full re-encode next admission. Drain is not optional.

Drain contract:
- Deploy sets `Workers.Status='Paused'` for every worker it intends to restart. The worker's own claim loop MUST honor Paused and stop claiming new work at the next poll.
- Deploy waits until `ActiveJobs` count for the paused worker reaches 0 before touching the process.
- Drain wait has an upper bound (currently `DRAIN_TIMEOUT_SEC = 1800` = 30 minutes). Deploy MUST NOT exceed this without operator interruption; on exceed, deploy either aborts OR forces a supervised kill with explicit `--force-drain` flag from the operator. It does NOT silently `SIGTERM` mid-encode.
- Drain applies to EVERY deploy path: `deploy-fleet.py` (canonical), `deploy-baremetal-worker.py`, `deploy-linux-worker.py`, `deploy-windows-worker.py`. Each script's entry point verifies drain BEFORE code sync + restart. No shortcut path exists.

Consequences:
- The `--no-drain` flag on `deploy-fleet.py` is EMERGENCY-only and must log to `DeployHistory.ErrorMessage` with the operator-supplied reason.
- Any script or skill that restarts a worker without checking `ActiveJobs=0` is a bug.
- Every deploy path is contract-test-locked against this invariant (`Tests/Contract/TestDeployMustDrain.py`).

## 2026-07-25 -- Workers MUST be up-to-date before coming back Online

Question: When can a worker's `Workers.Status` return to `'Online'` after a deploy?

Answer: **Only when the worker's registered `Workers.Version` matches the deploy target SHA AND `LastHeartbeat` is fresh (< 60s).** A worker that has restarted but is still on the old SHA MUST remain `Paused` until it registers on the new SHA.

Version-freshness contract:
- Deploy captures target SHA at entry, stores in `DeployHistory.NewSha`.
- After restart, deploy polls `Workers.Version` per host with a bounded timeout (`POLL_TIMEOUT_SEC = 300` = 5 minutes).
- `RestoreWorkerStatus` only sets `Status` back to the operator's pre-drain intent for workers that have reached `Version = TargetSha[:8]` AND `LastHeartbeat < 60s`.
- Workers that fail the version-match check within the poll window stay `Paused`. Deploy exits with `Outcome='TIMEOUT'` and names the stragglers.
- Operator's original `Status` intent (Online vs Paused) is preserved through the drain-deploy-restore cycle. If pre-drain was Online AND post-restart version-matches, worker returns to Online. If pre-drain was Paused, worker stays Paused.

Consequences:
- No worker is ever Online while running old code. Split-SHA fleet is a bug the deploy catches.
- If deploy times out, workers stay Paused (safe default). Operator investigates the straggler.
- The version bump + status flip happen as a single logical step per worker, not fleet-wide -- one worker on new SHA, one on old, is transient but never Online-old + Online-new simultaneously.
- Every deploy path is contract-test-locked against this invariant (`Tests/Contract/TestDeployVersionGate.py`).

## 2026-07-25 -- Worker identity is deploy-assigned, not runtime-derived

Question: How does a WorkerService process learn its `WorkerName`?

Answer: **`MEDIAVORTEX_WORKER_NAME` is the sole source. Deploy writes it. WorkerService reads it. Fail-loud if unset.**

- Bare-metal: systemd `EnvironmentFile=/etc/mediavortex/instance-%i.env` loads one file per instance. Deploy writes one file per slot with `MEDIAVORTEX_WORKER_NAME=<friendly>-worker-<N>`.
- Docker: compose sets `MEDIAVORTEX_WORKER_NAME` per service.
- Windows (I9): environment variable set by the launcher script.
- `WorkerService.Main._ResolveWorkerName` raises when the env var is missing. No `MEDIAVORTEX_WORKER_PREFIX`, no advisory-lock slot race, no `socket.gethostname()` fallback, no heartbeat-staleness reclaim.

Consequences:
- Runtime identity races (multiple processes computing the same slot at boot) are impossible by construction.
- Second process accidentally spawned for the same `MEDIAVORTEX_WORKER_NAME` still exists but cannot exceed the per-worker concurrency cap (see next entry).
- Any code path that derives `WorkerName` from anything other than the env var is a bug.

Historical damage (2026-07-25): 4 wakko processes + 2 dot processes all claimed the same WorkerName post-Deco-DHCP reboot. `_ClaimPrefixedWorkerName` (retired) read stale heartbeats under a race window and all returned slot 1. `Workers.MaxConcurrentJobs=1` was violated N-way per host. Root cause: identity was computed, not assigned.

## 2026-07-25 -- Per-worker concurrency lives in the DB, not in code

Question: What prevents a worker from exceeding `Workers.MaxConcurrentJobs`?

Answer: **The claim SQL. `Core.Database.WorkerCapabilityPredicate.BuildInflightCapPredicate(WorkerName, JobType)` emits a WHERE-clause fragment that refuses claim when `<in-flight count for this worker> >= <cap column>`.**

- Transcode: `TranscodeAttempts` where `Success IS NULL AND WorkerName=?` compared to `Workers.MaxConcurrentJobs`.
- QualityTest: `QualityTestingQueue` where `Status='Running' AND ClaimedBy=?` compared to `Workers.MaxConcurrentQualityTestJobs`.
- The DB is the authority. Client-side `WorkerLoopService.SlotSemaphore` remains as a rate-limit only (prevents local thread explosion in the happy path); it is not the invariant enforcer.

Consequences:
- A misdeployed second process for the same `WorkerName` (which shouldn't happen post the identity fix, but belt-and-suspenders) cannot claim beyond the cap. The SECOND concurrent claim's SQL sees count == cap and returns 0 rows.
- Adjusting concurrency is a DB update, not a code change (per `feedback_no_hardcoded_values`).
- Any `Claim*` function that omits `BuildInflightCapPredicate` for its JobType is a bug.
- Contract test: `Tests/Contract/TestClaimAuthority.py::TestTranscodeConcurrencyCapLive` proves refusal at cap boundary.

## 2026-07-25 -- All workers must be on the most recent build

Question: What version of the code may a worker be running?

Answer: **Every worker in the fleet MUST be on the current HEAD build. No version drift.**

- `Workers.Version` for every row with `Status IN ('Online','Paused')` AND fresh `LastHeartbeat` MUST equal the repo HEAD SHA.
- Drift between hosts (some on old SHA, some on new) is a bug the deploy is responsible for closing. Not "eventually consistent" -- deploy exits non-zero if it can't converge every named host.
- Deploy is the only sanctioned path to close the gap. No hand-editing `Workers.Version`. No skipping a host because it's "fine as-is."
- If a host can't be updated (offline, unreachable, hardware fault), the deploy names the straggler and the operator either fixes it or removes it from the fleet.

## 2026-07-25 -- Deploy requires a committed + pushed + up-to-date branch

Question: What state must the source tree be in before running a deploy?

Answer: **`git status --porcelain` MUST be empty AND local `HEAD` MUST equal `origin/main`.**

- No dirty deploys. Uncommitted changes MUST be committed before deploy runs.
- No unpushed deploys. Local commits MUST be pushed to `origin/main` before deploy runs.
- No behind-main deploys. Local MUST NOT lag `origin/main`.
- Fleet + per-host deploy entry-points fail-loud when either check fails. The message names the offending files or the SHA delta.
- No override flag. The bar is absolute -- if a deploy needs to happen mid-work, commit the work first.
