# MediaVortex Domain Decisions

Source of truth for domain-level "what does the system do and why" decisions.
Every entry answers ONE domain question with ONE committed decision.

Rules:
- Append-only. Old decisions get a `Superseded by <date>` line, never edit.
- No implementation details. Metric choices belong here; SQL columns and Python classes do not.
- Any code, rule, or table that answers the same question differently = refactor. This doc is the ratchet.
- Cross-check every new directive against this doc BEFORE opening.

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
