---
description: Enqueue smoke-test transcodes with deterministic worker pinning. Uses Workers.Status='Paused' to steer claims across hosts so 1080p + 4K jobs land on different workers instead of piling on one.
argument-hint: <MediaFileId1:ProfileId1:WorkerName1> [MediaFileId2:ProfileId2:WorkerName2 ...]
---

Enqueue one or more smoke-test transcodes so each lands on the exact worker the operator wants. Do NOT skip the pause dance -- the TranscodeQueue claim query ignores `MaxConcurrentTranscodeJobs`, so an unpinned enqueue pile-ups on whichever worker polls first.

## When to use this skill

- Testing a new profile end-to-end (Opus codec change, near-lossless CQ profile, etc.)
- Comparing timing / VMAF / audio across hosts (i9 NVENC vs dot NVENC vs wakko QSV)
- Deliberately targeting one hardware type (NVENC vs QSV) without waiting for a random claim
- Any experiment where "which worker ran it" is part of the answer

## Do NOT use this skill

- For real production transcodes (the queue's normal claim path handles those)
- If MaxConcurrentTranscodeJobs is honored correctly in the future -- retire this skill

## Pre-flight (always run these first)

1. Verify each target MediaFileId exists + has `KeepSource=true`. Set it if not:
   ```
   UPDATE MediaFiles SET KeepSource=true WHERE Id IN (...);
   ```
2. Verify each target's `AssignedProfile` matches the intended profile name:
   ```
   UPDATE MediaFiles SET AssignedProfile=(SELECT ProfileName FROM Profiles WHERE Id=<ProfileId>) WHERE Id=<MediaFileId>;
   ```
3. Verify a `ProfileThresholds` row exists for the profile at the source's resolution. If missing, transcode fails with "Failed to build Transcode command". Insert with quality field set to the CQ/ICQ/CRF value.
4. Verify each target worker is Online + has the required hardware flag (`nvenccapable`, `qsvcapable`).

## The pinning dance (per triple `<MediaFileId>:<ProfileId>:<WorkerName>`)

For each triple, in the order listed:

1. **Pause every other worker of the same capability** so the target is the only eligible claimer:
   ```sql
   UPDATE Workers SET Status='Paused'
   WHERE (NvencCapable = <ProfileNvenc> OR QsvCapable = <ProfileQsv>)
     AND WorkerName != '<WorkerName>'
     AND Status = 'Online';
   ```
2. Enqueue the job via the production API (NEVER direct SQL insert -- the API handles ProcessingMode + AudioPolicyJson snapshot + priority logic):
   ```
   curl -s -X POST http://10.0.0.7:5000/api/TranscodeQueue/AddJob \
     -H "Content-Type: application/json" \
     -d '{"MediaFileId": <MediaFileId>, "Priority": 200, "ForceAdd": true}'
   ```
3. Poll `TranscodeQueue.ClaimedBy` every 5s for up to 30s. If ClaimedBy != `<WorkerName>` after 30s, abort and report -- claim went to a stale/wrong worker.
4. Once ClaimedBy is correct, **unpause the other workers of that capability** so they can claim any subsequent triples in the batch:
   ```sql
   UPDATE Workers SET Status='Online'
   WHERE Status='Paused' AND WorkerName != '<WorkerName>';
   ```

Repeat for the next triple. Each triple's target worker stays free while the others are paused, then everyone unpauses so the next triple can pin its own.

## Never do this

- **NEVER `systemctl restart` a worker while its ffmpeg child is encoding.** The restart sends SIGTERM to the child, wasting all encode work done so far (exit code -15 or 234). Restart workers only when they are idle.
- **NEVER enqueue multiple heavy transcodes at the same priority to the same host without pinning.** The claim query ignores MaxConcurrentTranscodeJobs and you will get two Demucs jobs on the same 8GB GPU -> VRAM OOM -> SIGKILL -> Track 1 silently dropped.
- **NEVER pause every worker at once and forget to unpause.** Leaves the queue frozen until manual recovery.

## Post-completion

After the batch finishes, for each attempt report:
- `WorkerName` (verify pin held)
- `Success` + `ErrorMessage`
- `TranscodeDurationSeconds` (report both minutes and seconds)
- `OldSizeBytes` -> `NewSizeBytes` + `SizeReductionPercent`
- `VMAF` (if QualityTestRequired on the profile)
- Post-encode audio loudness on Track 0 + Track 1 via `ffmpeg -i <output> -map 0:a:N -af ebur128=peak=true -f null -`
- Post-encode audio stream shape (codec, channels, bitrate) via `ffprobe -show_streams -select_streams a`

Present as a side-by-side table -- each column a worker/host, each row a metric.

## Related feature docs

- Audio pipeline: `Features/AudioNormalization/audio-normalization.feature.md`
- VMAF chain: `Features/QualityTesting/QualityTesting.feature.md`
- Queue claim (contains the MaxConcurrentTranscodeJobs bug): `Features/TranscodeQueue/TranscodeQueueRepository.py:ClaimNextPendingJob`
