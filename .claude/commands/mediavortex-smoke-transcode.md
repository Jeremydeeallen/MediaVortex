---
description: Enqueue smoke-test transcodes pinned to a specific fleet worker (NVENC on dot, QSV on wakko). Uses the production AddJob + worker-capability APIs; never direct SQL.
argument-hint: <MediaFileId1:ProfileId1:WorkerName1> [MediaFileId2:ProfileId2:WorkerName2 ...]
---

Enqueue one or more smoke-test transcodes so each lands on the exact worker the operator wants. Smoke tests run on fleet machines (`dot-worker-1` = NVIDIA NVENC, `wakko-worker-1` = Intel QSV), never on I9. A profile that passes on both GPUs is accepted; I9 is added back to the queue by the operator afterwards.

Farm WebService: `http://10.0.0.49:5000` (`mediavortex-server`, also `http://mediavortex-server/` through nginx). Every call below goes to that host.

## When to use this skill

- Testing a profile or ladder row end-to-end (new tier target, codec change, CQ profile).
- Comparing timing / VMAF / size across hardware (dot NVENC vs wakko QSV).
- Any experiment where "which worker ran it" is part of the answer.

## Do NOT use this skill

- For real production transcodes (the queue's normal claim path handles those).
- To bypass admission: run without `ForceAdd` first. A refusal is a finding, not an obstacle.

## A smoke never replaces a library file

A smoke proves the command, the encoder, the size and the VMAF. It does not decide that the output is good; the operator does, after looking. The pipeline has no hold state: a VMAF between the gate's min and max is `Replace`, and `TranscodedOutputPlacement` deletes the source unconditionally (`MediaFiles.KeepSource` has no reader -- BUG-0125). 2026-11-26: smoke attempt 104045 replaced MediaFile 55384's 25 Mbps h264 4K60 source with an 8 Mbps AV1 at VMAF 90.4 before anyone had judged what success looks like. Do not repeat.

Therefore every smoke runs on a COPY:

1. Copy the source into a scanned folder of the same library with a `smoke-` prefix (`cp "<src>" "<dir>/smoke-<name>"`), run one scan tick (or wait for the continuous scan) so the copy has its own `MediaFiles` row, and smoke THAT row. Replacement, if it happens, destroys only the copy. Delete the copy row's files when the operator has finished looking.
2. Until BUG-0125 is fixed there is no in-pipeline way to keep the original. `KeepSource`, pausing QT, and the Override API (Pending rows only; QT claims within seconds) do not protect it.
3. Say in the report which rows are copies so nobody mistakes a smoke output for library state.

## Pre-flight (always run these first, read-only)

1. Target row is the COPY: `SELECT Id, FileName, AssignedProfile, AssignedProfileSource, VideoBitrateKbps, FrameRate, ResolutionCategory, round(FileSize/1e6) FROM MediaFiles WHERE Id=<MediaFileId>` and `SELECT count(*) FROM TranscodeAttempts WHERE MediaFileId=<MediaFileId>` (0 prior attempts). Record `FrameRate`: `TargetKbps` is frame-rate-blind, and 8000k scored 90.4 at 59.94 fps vs 98.9 at 29.97 fps on the same ladder row.
2. Ladder row: `SELECT Resolution, TargetKbps, TranscodeDownTo FROM ProfileThresholds pt JOIN Profiles p ON p.Id=pt.ProfileId WHERE p.Id=<ProfileId> AND pt.ContentClass=<class> AND pt.Resolution=<source resolution>`. Missing row -> "Failed to build Transcode command".
3. Workers: `SELECT WorkerName, Status, TranscodeEnabled, QualityTestEnabled, MaxConcurrentJobs, nvenccapable, qsvcapable FROM Workers WHERE Status='Online'`. The target must be Online, `TranscodeEnabled`, and carry the hardware flag the profile needs.
4. Queue: `SELECT count(*) FROM TranscodeQueue WHERE Status='Pending'` and `SELECT * FROM ActiveJobs`. Know what else can claim.

## AddJob contract (learned 2026-11-26)

- The controller forwards ONLY `MediaFileId`, `Priority`, `ProfileId`, `StartTime`, `ForceAdd`. `QualityTier` / `QualityLabel` are accepted by the service but silently dropped by the controller (BUG filed); passing them encodes at the file's CURRENT profile. Always pass `ProfileId`.
- `ProfileId` writes `MediaFiles.AssignedProfile` (source column untouched) before the queue row is created, so the worker's attempt carries the smoke profile.
- Verify immediately after enqueue: `SELECT AssignedProfile FROM MediaFiles WHERE Id=<MediaFileId>` and `SELECT WorkerName, ProfileName FROM TranscodeAttempts WHERE MediaFileId=<MediaFileId> ORDER BY Id DESC LIMIT 1`. Wrong profile -> stop the job before QT (below), do not let it run.

## Pinning (per triple `<MediaFileId>:<ProfileId>:<WorkerName>`)

Per-worker concurrency is DB-enforced at claim (`Workers.MaxConcurrentJobs`, `claim-authority.md`), so a busy worker cannot take a second job. Pin by leaving exactly one eligible idle claimer:

1. Make the target the only idle worker with `TranscodeEnabled` for that hardware. Flip flags through the API, never SQL:
   ```
   curl -s -X POST http://10.0.0.49:5000/api/TeamStatus/Workers/<OtherWorker>/Capability -H "Content-Type: application/json" -d '{"TranscodeEnabled": false}'
   ```
   The worker reads the flag within 60s. A worker already Running at its cap also cannot claim, so a second triple can be enqueued as soon as the first is Running.
2. Enqueue via the production API (NEVER direct SQL insert):
   ```
   curl -s -X POST http://10.0.0.49:5000/api/TranscodeQueue/AddJob -H "Content-Type: application/json" -d '{"MediaFileId": <MediaFileId>, "ProfileId": <ProfileId>, "Priority": 200}'
   ```
   Add `"ForceAdd": true` only after a refusal has been read and understood.
3. Poll `SELECT Status, ClaimedBy FROM TranscodeQueue WHERE Id=<ItemId>` every 5s for up to 30s. Wrong `ClaimedBy` -> report; do not re-enqueue.
4. Restore flags you flipped once every triple is claimed.

Windows session note: the auto-mode classifier refuses `Stop-Process`, DB writes and SSH writes from the assistant. When a step is refused, hand the operator the exact command; the `!` prefix runs bash, so use `taskkill //F //IM ffmpeg.exe`, not PowerShell.

## Stopping a wrong job

- Pending QT row: `POST /api/QualityTest/Override {"QueueId": <Id>, "ForceDisposition": "Reject"}`.
- Running QT row: kill the VMAF ffmpeg on the QT worker; `PostTranscodeGateConfig.WhenVmafUnavailable='block'` leaves the source untouched.
- Running encode: kill the encode ffmpeg on the owning worker (operator; cross-host kill is not supported). Never `systemctl restart` a worker mid-encode.
- A `Reject` disposition leaves the staged `<name>-mv.<ext>.ip` on the share; delete it by hand and note it.

## Never do this

- Never enqueue to the same host without pinning; two heavy jobs on one 8 GB GPU -> VRAM OOM.
- Never disable every transcode worker and forget to re-enable.
- Never pass `QualityTier` to AddJob and assume it applied.

## Post-completion

For each attempt report: `WorkerName` (pin held), `Success` + `ErrorMessage`, the `EXECUTING COMMAND` log line (encoder, `-b:v`, scale filter present or not), `TranscodeDurationSeconds`, `OldSizeBytes` -> `NewSizeBytes` + `SizeReductionPercent`, `Vmaf` + `Disposition` + `DispositionReason`, `FileReplacedDate`. For an AudioFix job: Track 0 / Track 1 loudness via `ffmpeg -i <output> -map 0:a:N -af ebur128=peak=true -f null -` and stream shape via `ffprobe -show_streams -select_streams a`.

Present as a side-by-side table: one column per worker, one row per metric.

## Related

- `Features/QualityTesting/QualityTesting.feature.md` (VMAF chain, Override)
- `Features/TranscodeQueue/TranscodeQueueRepository.py:ClaimNextPendingJob` + `.claude/rules/claim-authority.md` (DB-enforced cap)
- `Features/TeamStatus/TeamStatusController.py:SetWorkerCapability`
