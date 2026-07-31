# MediaVortex Domain Decisions

Source of truth for domain-level "what does the system do and why" decisions.
Every entry answers ONE domain question with ONE committed decision.

Rules:
- Append-only. Old decisions get a `Superseded by <date>` line, never edit.
- No implementation details. Metric choices belong here; SQL columns and Python classes do not.
- Any code, rule, or table that answers the same question differently = refactor. This doc is the ratchet.
- Cross-check every new directive against this doc BEFORE opening.

## Table of Contents

- [Meta](#meta) -- how domain decisions are made
- [Pipeline](#pipeline) -- what operations MediaVortex performs
- [Workers](#workers) -- how workers are identified and how much they run
- [Deploy](#deploy) -- how deploys converge the fleet without losing state
- [Compliance](#compliance) -- what qualifies a file for which operator

---

## Meta

### 2026-07-25 -- Who owns what (meta-rule)

Question: Who decides domain questions, and who implements them?

Answer: **Operator owns the WHAT and the WHY. Claude owns the HOW.**

- Domain decisions (what the system does, why it does it, which trade-offs are acceptable) come from the operator. Claude MUST NOT invent domain rationale (e.g. "GPU contention" as the reason for a rule when no test data exists). If a decision lacks stated rationale, record "operator instruction; no tested rationale" -- do not fabricate one.
- When Claude perceives a domain question that has not been answered, Claude MUST surface it to the operator and record their answer here BEFORE writing implementation. Claude does not choose between domain options; Claude implements the operator's chosen option.
- Every rule, contract test, code path, skill, and directive that touches a domain concern MUST be traceable to a `DOMAIN.md` entry. If it isn't, either the rule is wrong or the domain entry is missing.
- Correction pattern: when Claude puts speculation into memory or a rule and the operator flags it, Claude corrects the artifact + records the correction so the speculation doesn't propagate.

---

### 2026-07-27 -- Architectural principles: KISS, DDD, DRY, SOLID

Question: Which principles govern every architectural decision?

Answer: **KISS, DDD, DRY, SOLID apply to every directive. Not aspirational -- enforced.**

Reason: repeated drift into overcomplication (allowlist scope creep, three-defense stacking, DDD scaffolding without payoff) forced the operator to invoke these principles orally in individual directives. Codifying here so every future directive inherits them without re-invocation.

**KISS != minimal code.** KISS = minimal ESSENTIAL complexity. Deferring correct structure to save time now, then paying 3x later for bolt-on features = false economy, not KISS. The KISS-correct answer is the shape that costs the least across the whole lifecycle, not the shape that lands in the fewest lines today.

**Four-question test** applied to every data-shape / abstraction decision:

| Question | Blob / minimal wins | Normalize / explicit wins |
|---|---|---|
| Can I express what I need to READ in one line of SQL? | Yes (read whole blob) | No (SELECT WHERE on fields) |
| Does this data have its own lifecycle (created / updated / queried independently of parent)? | No | Yes |
| Will there be >1 row of this per parent, ever? | No | Yes |
| Do I need to know WHEN or BY WHAT it was produced? | No | Yes |

- 4/4 "normalize wins" -> normalize IS the KISS-correct answer.
- 4/4 "blob wins" -> blob IS the KISS-correct answer.
- Mixed answers -> revisit the concept boundary; may be two aggregates masquerading as one.

**Over-normalization signals (avoid):**

- 3+ JOINs for a common read
- FK CASCADE chains
- Junction tables for what should be enum columns
- Repository interfaces for things with one implementation
- Value objects wrapping single primitives with no invariants
- Application-service layers over one-line CRUD calls

**Under-normalization signals (avoid):**

- WHERE clause with `->>` or `LIKE '%...%'` on JSONB fields for common queries
- Same field embedded in N tables (DRY violation)
- Mode-branching in orchestration (SOLID Open/Closed violation -- see `.claude/rules/call-graph-audit.md` signal 2)
- Feature flag that removes call-graph nodes when off (`call-graph-audit.md` signal 5)
- One class doing detection + persistence + orchestration (SRP violation)

**Directive-time enforcement:**

Every directive doc must include one of:
- (a) explicit statement "no architectural principle traded" in the outcome section, OR
- (b) named principle traded + why + what mitigates it (KNOWN DEBT in `## Out of Scope`)

Silent trade-offs are refused. `.claude/rules/call-graph-audit.md` five-signal check at NEEDS_STANDARDS_REVIEW is the mechanical enforcement for DDD+SOLID; KISS+DRY are judgment gates the reviewer applies at plan review.

---

## Pipeline

### 2026-07-23 -- Pipeline operators

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

*Note: the "video codec not in allowlist" branch is superseded by the 2026-07-26 compliance entry (Compliance section). See [Video compliance is bitrate-driven](#2026-07-26----video-compliance-is-bitrate-driven-codec-allowlist-retired).*

### 2026-07-23 -- Definition of "efficiently transcoded"

Question: When is a file "efficiently transcoded" so we should not re-encode?

Answer: **SourceKbps <= profile target kbps at the file's resolution.**

The comparison uses the assigned profile's `TargetKbps` for the file's resolution (from `ProfileThresholds`). If the source is already at or below that target, re-encoding cannot meaningfully reduce size at the operator's chosen quality tier.

Consequences:
- Efficient files are STILL eligible for Remux (if container is not compliant) and AudioFix (if audio needs normalization). Only the Transcode operator is suppressed.
- Files without an assigned profile cannot be evaluated for efficiency and land in the `Unclassified` bucket by default.
- Files with an assigned profile whose SourceKbps exceeds the target enter the Transcode operator via the standard compliance path.
- This decision RETIRES the codec-blind `bpp` gate and the total-bitrate `SizeMB/DurationMinutes` proxy. Both were removed in favor of the direct SourceKbps-vs-TargetKbps comparison.

*Refined by 2026-07-26 (Compliance section): the compliance threshold applies a per-resolution multiplier over Tier 1 target, not the bare Tier 1 target. This entry defines the base concept; the multiplier tunes strictness. See [Video compliance is bitrate-driven](#2026-07-26----video-compliance-is-bitrate-driven-codec-allowlist-retired).*

### 2026-07-23 -- Transcode job boundary

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

---

### 2026-07-26 -- Vmaf column is truthful; outcome lives in Success + Disposition

Question: What does `TranscodeAttempts.Vmaf` hold, and where does the "did this attempt pass?" signal live?

Answer: **`Vmaf` holds a real VMAF score or NULL. Nothing else. No sentinels. Outcome signal lives in `(Success, Disposition)` -- never in an overloaded quality-score column.**

- Stream-copy modes (`Remux`, `AudioFix`, `SubtitleFix`, `Quick`) are verified by MD5 checksum, not VMAF. Their attempts land with `Vmaf IS NULL`.
- Only real VMAF measurements populate `Vmaf`. A checksum-passed stream-copy is NOT a VMAF measurement.
- Downstream code that wants to know "did this attempt pass?" reads `Success` (ffmpeg exit) and `Disposition` (`Replace` / `Reject` / `Requeue` / `Pending`). It does NOT read `Vmaf` as a proxy for outcome.
- Analytics queries (`AVG(Vmaf)`, `WHERE Vmaf >= 80`) get real signal because `Vmaf` is dense-with-truth for the modes that measure it and NULL for the modes that don't.

Consequences:
- `_VerifyStreamCopyChecksum` returns `Vmaf=None` on match (not `100.0` sentinel).
- Any code path that gates on `Vmaf` and needs to work for stream-copy modes is wrong-column: it must read `Success + Disposition` instead.
- Retry-budget accounting counts prior `Disposition='Requeue'` outcomes, not prior `Vmaf < threshold` measurements.
- The historical `Vmaf=100.0` sentinel rows for stream-copy modes are legacy against this rule. Backfilling them to NULL is a data-honesty fix.

Historical note: sentinel introduced because `RetranscodeDecider.Decide` was reading `Vmaf >= 80` as the pass signal, and stream-copy paths needed to route around it. Both the sentinel and the RetranscodeDecider VMAF gate are legacy against this domain rule; RetranscodeDecider is bypassed by `ForceAdd=True` on every prod admission path (`QueueAdmissionAppService`, `DispositionDispatcher._MaybeScheduleRequeue`) as of BUG-0078 fix and is retired by directive `verify-signal-cleanup` (2026-07-26).

---

## Workers

### 2026-07-24 -- Worker identity and multi-instance-per-host

*Superseded by 2026-07-25 "Worker identity is deploy-assigned, not runtime-derived." The invariant (distinct WorkerName per process, ties to MaxConcurrentJobs + claim gates) still stands; the runtime slot-claim mechanism it described (advisory-lock + heartbeat-driven reclamation) is retired.*

Question: How are worker identities assigned when a single host runs multiple worker instances?

Answer:

- Each worker process has exactly ONE stable identity: `{host}-worker-{N}` where N is a positive integer unique within the host.
- Multiple systemd instances on the same host produce DISTINCT worker identities. Two processes MUST NOT share a WorkerName.
- Slot assignment (which N a fresh process gets) is atomic: the process reserves the slot in the DB inside the same advisory-lock scope that computed it. No process ever returns a WorkerName without having written the row that claims it.
- Slot reclamation is heartbeat-driven: a slot whose last heartbeat is older than 2 minutes is stale and can be reclaimed by a fresh process. A slot with a fresh heartbeat is owned and MUST NOT be reassigned.

Consequences:

- If four systemd units start simultaneously on a host with no existing worker rows, they claim `{host}-worker-1`, `{host}-worker-2`, `{host}-worker-3`, `{host}-worker-4` -- one each. Collision-into-same-slot is a bug.
- WorkerName ties directly to the `MaxConcurrentJobs` semaphore, the claim queries, and every ownership check. Two processes with the same name = ownership invariant broken = concurrent claims on the same work.

### 2026-07-24 -- Worker responsibilities (DDD context)

Question: What does a Worker OWN and DO?

Answer:

- A Worker is a claim-driven executor. It polls queues its DB row says it is capable of (Transcode / Remux / QualityTest / Scan) and CLAIMS one unit of work at a time up to `MaxConcurrentJobs`.
- A Worker OWNS every attempt row it claims through that attempt's terminal state (Success = TRUE / FALSE). No other worker touches an in-flight attempt owned by another worker; the exception is `AttemptAbandonmentSweeper` which releases attempts whose owner has been Offline + heartbeat-stale for the configured window (`.claude/rules/claim-authority.md`).
- Worker capability + policy state (Status, TranscodeEnabled, RemuxEnabled, QualityTestEnabled, ScanEnabled, MaxConcurrentJobs, MaxCpuThreads, MaxConcurrentQualityTestJobs, AcceptsInterlaced) is OPERATOR-OWNED. Code MUST NOT overwrite these columns except via an explicit operator-facing action (GUI, CLI). Boot-time registration MAY set defaults on first INSERT but MUST NOT touch these columns on UPDATE.
- Deploy-derived columns (Platform, FFmpegPath, FFprobePath, Version, BuildInfo, nvenccapable, qsvcapable) are DEPLOY-OWNED. Deploy scripts write them; operator does not.

Consequences:

- Any code path that flips Status from Paused to Online without the operator explicitly asking (GUI action, CLI flag, WorkerService fresh-slot INSERT) is a bug.
- Any code path that resets MaxConcurrentJobs, QualityTestEnabled, TranscodeEnabled, etc. via a mass UPDATE is a bug.

### 2026-07-25 -- Worker identity is deploy-assigned, not runtime-derived

Question: How does a WorkerService process learn its `WorkerName`?

Answer: **`MEDIAVORTEX_WORKER_NAME` is the sole source. Deploy writes it. WorkerService reads it. Fail-loud if unset.**

- Bare-metal Linux: systemd `EnvironmentFile=/etc/mediavortex/instance-%i.env` loads one file per instance. Deploy writes one file per slot with `MEDIAVORTEX_WORKER_NAME=<friendly>-worker-<N>`.
- Windows (I9): environment variable set by the launcher script.
- `WorkerService.Main._ResolveWorkerName` raises when the env var is missing. No `MEDIAVORTEX_WORKER_PREFIX`, no advisory-lock slot race, no `socket.gethostname()` fallback, no heartbeat-staleness reclaim.

Consequences:
- Runtime identity races (multiple processes computing the same slot at boot) are impossible by construction.
- Second process accidentally spawned for the same `MEDIAVORTEX_WORKER_NAME` still exists but cannot exceed the per-worker concurrency cap (see next entry).
- Any code path that derives `WorkerName` from anything other than the env var is a bug.

Historical damage (2026-07-25): 4 wakko processes + 2 dot processes all claimed the same WorkerName post-Deco-DHCP reboot. `_ClaimPrefixedWorkerName` (retired) read stale heartbeats under a race window and all returned slot 1. `Workers.MaxConcurrentJobs=1` was violated N-way per host. Root cause: identity was computed, not assigned.

### 2026-07-25 -- Per-worker concurrency lives in the DB, not in code

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

---

## Deploy

### 2026-07-24 -- Deploy is idempotent, never destructive

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

### 2026-07-25 -- All workers must be on the most recent build (close-the-gap workflow)

Question: What version of the code may a worker be running, and how does deploy safely converge the fleet without losing operator state or in-flight work?

Answer: **Every worker MUST be on the current HEAD build. Closing the fleet-drift gap is deploy's job, MUST NOT kill in-flight encodes, and MUST restore each worker's pre-deploy state end-to-end.**

Invariant:
- `Workers.Version` for every row with `Status IN ('Online','Paused')` AND fresh `LastHeartbeat` MUST equal the repo HEAD SHA. Drift = bug. Deploy is the only sanctioned path to close the gap.
- No hand-editing `Workers.Version`. No skipping a host because it's "fine as-is." No `eventually consistent`; deploy exits non-zero if a named host can't converge.

Close-the-gap workflow (mandatory, single logical operation):

1. **Capture per-worker pre-state.** For every worker with `Status IN ('Online','Paused')` AND fresh `LastHeartbeat`, record `(Status, TranscodeEnabled, QualityTestEnabled, RemuxEnabled, ScanEnabled, in-flight ActiveJobs count)`. This snapshot is the target end-state for step 4.
2. **Drain workers with in-flight work FIRST.** For every worker with `in-flight ActiveJobs > 0`, set `Status='Paused'` (its claim loop stops on next poll) and wait until `ActiveJobs = 0`. Bounded by `DRAIN_TIMEOUT_SEC = 1800` (30 min). Deploy MUST NOT silently `SIGKILL` a running encode; killing mid-flight loses the work, produces `.inprogress` orphans, corrupts audio-normalization scratch dirs, and forces a full re-encode. If drain exceeds the timeout, deploy either aborts OR requires explicit operator `--force-drain` with the reason logged to `DeployHistory.ErrorMessage`.
3. **Deploy source + restart every host.** Per-host script under fleet orchestrator. Each host converges to HEAD SHA or exits non-zero naming the straggler.
4. **Restore per-worker pre-state.** After each restarted worker registers with `Version = HEAD` AND `LastHeartbeat < 60s`, write back its captured `(Status, capability flags)`. A worker that was Online + Encoding pre-deploy returns to Online with capabilities enabled and starts claiming again. A worker that was Paused stays Paused. `RestoreWorkerStatus` MUST NOT default any operator-owned column; missing state is fail-loud, not silently defaulted (see 2026-07-24 idempotence entry).
5. **Bounded post-restart version-gate.** Deploy polls `Workers.Version` per host with `POLL_TIMEOUT_SEC = 300` (5 min). Workers that fail version-match within the poll window stay `Paused`; deploy exits `Outcome='TIMEOUT'` naming the stragglers. No worker is ever `Online` while running old code -- split-SHA fleet is the bug this workflow catches.

Rule violation shapes (all bugs, all contract-test-locked):
- Deploy that leaves a subset of workers on old SHA = bug. Split-SHA fleet is never a valid end-state.
- Deploy that kills in-flight encodes without draining = bug. `--no-drain` on `deploy-fleet.py` is EMERGENCY-only and must log to `DeployHistory.ErrorMessage` with the operator-supplied reason.
- Deploy that "restores" all workers to Online regardless of pre-state = bug. Operator's Paused intent is preserved.
- Any hand-editing of `Workers.Version` = bug. Deploy is the only path.
- Any deploy script or skill that restarts a worker without checking `ActiveJobs = 0` = bug.

Contract tests: `Tests/Contract/TestDeployMustDrain.py` (step 2) + `Tests/Contract/TestDeployVersionGate.py` (step 5). Every deploy path (`deploy-fleet.py`, `deploy-baremetal-worker.py`, `deploy-linux-worker.py`, `deploy-windows-worker.py`) is locked against the same invariants -- no shortcut path exists.

*Refined by 2026-07-26 "Fleet-on-HEAD applies only to worker-affecting commits" (below): docs / web-only / test / tooling commits do not require worker redeploy.*

### 2026-07-25 -- Deploy requires a committed + pushed + up-to-date branch

Question: What state must the source tree be in before running a deploy?

Answer: **`git status --porcelain` MUST be empty AND local `HEAD` MUST equal `origin/main`.**

- No dirty deploys. Uncommitted changes MUST be committed before deploy runs.
- No unpushed deploys. Local commits MUST be pushed to `origin/main` before deploy runs.
- No behind-main deploys. Local MUST NOT lag `origin/main`.
- Fleet + per-host deploy entry-points fail-loud when either check fails. The message names the offending files or the SHA delta.
- No override flag. The bar is absolute -- if a deploy needs to happen mid-work, commit the work first.

### 2026-07-26 -- Fleet-on-HEAD applies only to worker-affecting commits

Question: Does every new commit require a fleet redeploy, or only commits that change worker runtime?

Answer: **Only commits that touch worker-runtime code require a fleet redeploy. Docs, web-only, tests, and deploy-tooling commits do not create drift under the fleet-on-HEAD rule.**

- Worker-runtime paths (worker imports at runtime OR ships in the container/venv):
  - `WorkerService/`
  - `Features/`
  - `Core/`
  - `Services/`
  - `Repositories/`
  - `Composition/`
  - `WorkerService/requirements.txt` (venv content)
  - `StartWorker.py`, `StartMediaVortex.py`, `StartParallelWorkers.py` (launchers)
  - `deploy/baremetal/mediavortex-worker@.service` (systemd invocation)
  - `deploy/baremetal/worker.env.template` (systemd env-file template per instance)
- Non-worker paths (no redeploy needed):
  - `*.md` (all docs, `DOMAIN.md`, `CLAUDE.md`, `ARCHITECTURE.md`, `GLOSSARY.md`)
  - `.claude/` (rules, directives, standards, hooks)
  - `WebService/`, `Templates/`, `Static/`
  - `Tests/`
  - `Scripts/`
  - `deploy/deploy-*.py` (dev-host tooling)
  - `deploy/SyncSource.py`
  - `.gitignore`, `.deployignore`

Consequences:
- The fleet-on-HEAD invariant becomes: `Workers.Version` must equal the SHA of the most recent commit that touched a worker-runtime path.
- Deploy-fleet's version-gate polls that SHA, not raw HEAD.
- A commit that only touches non-worker paths advances HEAD without triggering fleet drift.
- The list above is authoritative. Adding a new top-level directory means updating this entry BEFORE the first commit that touches it.

---

## Compliance

### 2026-07-26 -- Video compliance is bitrate-driven (codec allowlist retired)

Question: What makes a file's video stream "compliant" (i.e. not needing Transcode)?

Answer: **Bitrate compared against the profile's Tier 1 target for the file's resolution, multiplied by a per-resolution tunable multiplier. Codec is not a compliance signal.**

- `SourceKbps <= Tier1TargetKbps(Resolution) * ComplianceMultiplier(Resolution)` -> video-compliant.
- Above that threshold -> video-non-compliant -> Transcode operator.
- Container non-compliance still routes to Remux. Audio non-compliance still routes to AudioFix. Video-compliant files fall through to those operators when their other columns are non-compliant, exactly as the pipeline-operators entry describes.

Codec allowlist retired:
- The prior "video codec not in allowlist -> Transcode" branch (from 2026-07-23 Pipeline Operators, and the historical `VideoComplianceRules.acceptablevideocodecscsv` singleton) is superseded. Codec is orthogonal to whether re-encoding is worthwhile.
- Rationale: a modern codec (h264/hevc/av1) at a wasteful bitrate should still be re-encoded. A legacy codec (mpeg4/wmv3/msmpeg4v3) at an already-compact bitrate should be left alone.
- Truly-unplayable codec edge cases are handled downstream: the container-remux path forces stream-copy into mp4; incompatible codecs fail the copy and land in the operator queue for manual handling. The `acceptablevideocodecscsv` compliance signal is dead code and will be removed in the compliance-multiplier implementation directive.

Per-resolution multiplier defaults (operator-tunable via `/settings` GUI):

| Resolution | Multiplier | Effective floor at Tier 1 default |
|---|---|---|
| 480p | 1.5x | 600 kbps (Tier 1 = 400) |
| 720p | 2.0x | 1800 kbps (Tier 1 = 900) |
| 1080p | 2.0x | 3600 kbps (Tier 1 = 1800) |
| 2160p | 3.0x | 12000 kbps (Tier 1 = 4000) |

Rationale for per-resolution differences:
- 480p: SD content is well-served at low bitrates; 1.5x already covers typical 500-1500 kbps streaming SD.
- 720p / 1080p: 2.0x covers 1500-3000 / 3000-8000 kbps typical HD streaming without over-flagging.
- 2160p: 4K industry norm is 15000-25000 kbps streaming, 50000+ for UHD Blu-ray. 2.0x (8000 kbps floor) would treat below-industry-norm 4K as compliant. 3.0x (12000 kbps floor) matches operator's quality bar for 4K content.

Consequences:
- Values live in a dedicated per-resolution DB table. Operator adjusts via `/settings` GUI. No code change to retune.
- The Compliance evaluator reads the multiplier fresh per call (db-authority; no cache).
- Any code path that reads `VideoComplianceRules.acceptablevideocodecscsv` for compliance decisions is a bug pending the implementation directive that removes the column.
- Reclassification of existing MediaFiles rows against the new threshold is a data-only operation, not a code change.

Operator-visible effect (what changes in the UI):

- `/Work/Transcode` = candidates that need FULL re-encode (video + audio + container). List shrinks -- files whose video is already at/below the multiplier floor stop appearing here.
- `/Work/Remux` = candidates that need container change (typically mkv/avi -> mp4), stream-copy video, re-encode audio. List grows -- compact-video files with wrong container land here.
- `/Work/Audio` = candidates that need only audio work (normalization, downmix, codec change). List grows -- compact-video, correct-container files with audio issues land here.
- `/Work/Compliant` = files already meeting the bar. Browse/audit only, no admit action. List grows.
- `/Queue` = admitted work (rows in `TranscodeQueue` awaiting workers). Count only shifts when operator admits differently because the candidate lists are cleaner.

Concrete example (from the 2026-07-25 live sample):

- 80 MB Ed Edd n Eddy episode (msmpeg4v3, avi, 480p ~800 kbps source):
  - Before: `/Work/Transcode` -- flagged on codec-allowlist miss even though video is compact.
  - After: `/Work/Remux` -- video is under the 1.5x floor (600 kbps @ 480p); container needs avi -> mp4; audio (mp3) needs re-encode.
- 80 MB Pup Named Scooby-Doo (hevc, mkv, 480p at 481 kbps):
  - Before: `/Work/Transcode` -- flagged because 481 > Tier 1 target of 400.
  - After: `/Work/Remux` -- 481 is well under the 1.5x floor (600); container needs mkv -> mp4.
- 1080p movie at 4200 kbps (h264, mkv):
  - Before: `/Work/Transcode` -- 4200 > Tier 1 of 1800.
  - After: `/Work/Transcode` -- 4200 > 2.0x floor of 3600. Still worth re-encoding. Unchanged.

Bottom line: fewer expensive full re-encodes, more cheap Remux + AudioFix operations. Files already at compact bitrates stop being flagged for work that wouldn't save meaningful space.

---

## Resolved Domain Questions (2026-07-26)

Answered during `video-compliance-multiplier` directive planning.

### Q1: Codec compliance tail policy -- (a) Kill the allowlist entirely

Bitrate rule alone drives compliance. Truly-unplayable codec edge cases fail the container-remux stream-copy downstream and land in the operator queue for manual handling. No blocklist table. If false-positive-compliant unplayable files show up in `/Work/Remux` post-cutover, a small `UnsupportedVideoCodecs` blocklist is a follow-up directive, not a blocker for this one.

### Q2: All operator knobs editable via GUI -- (a) Domain rule

Every operator-facing DB knob (per-vertical thresholds, multipliers, gate configs, ladder cells) MUST be tunable via `/settings` or `/Admin/*` GUI without SQL or code. Enforcement is judgment-gate per `.claude/rules/gui-editable-knobs.md`. Reviewer flags any new operator-facing table/column shipped without a matching handler.

### Q3: Reclassify authorization after multiplier lands -- one-shot recompute script

`Scripts/RecomputeWorkBuckets.py` invokes `VideoVertical.RecomputeFor(all_ids)` -- same Python classifier the scanner uses, no duplicated SQL. Operator drain-first sequence (Workers.Status='Paused' + wait ActiveJobs=0 per `feedback_coordinate_live_worker_writes.md`), then run script, then verify WorkBucket delta counts, then unpause. Deploy-time auto-recompute rejected -- operator wants visibility on the shift before workers act.

### Q4: Worker-affecting paths list -- stands as declared

The 2026-07-26 "Fleet-on-HEAD applies only to worker-affecting commits" entry above is authoritative. Adding a new top-level directory means updating that list BEFORE the first commit that touches it.
