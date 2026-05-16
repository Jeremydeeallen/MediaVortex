# Feature: Local Staging for Transcode Jobs

## What It Does

Copies source files from the NFS share to the worker LXC's local RAID 10 storage before transcoding, runs FFmpeg against local disk, copies the transcoded output back to NFS, and deletes both local staging files. Eliminates the I/O bottleneck from Brain's RAID 5 (4 concurrent workers saturated disk at 17% CPU) by keeping all FFmpeg read/write on Larry's local disks (tested at 99% CPU, 0% iowait).

## Concern

Dogfood

## Success Criteria

1. When a worker picks up a transcode job, it copies the source file from the NFS bind mount to a local staging directory on Larry's RAID 10 storage before running FFmpeg. The copy uses the backplane path (10.0.1.x network, 20 Gbps). Verified via worker logs showing `LocalStaging mode: copied <nfs_path> to <local_path>`.

2. FFmpeg reads the source from local staging and writes the transcoded output to local staging (not NFS). Both `-i` input and output path in the FFmpeg command point to the local staging directory. Verified via the `FfmpegCommand` column in `TranscodeAttempts`.

3. After FFmpeg completes successfully, the worker copies the transcoded output file from local staging back to the NFS-based `StagingDirectory` (so VMAF and FileReplacement can find it via `TemporaryFilePaths`). Verified via worker logs showing the copy-back and the output file existing at the NFS staging path.

4. After copy-back, both local staging files (source copy and transcoded output) are deleted. The local staging directory does not accumulate files between jobs. Verified via worker logs showing deletion and `ls` of the local staging directory between jobs.

5. If FFmpeg fails or the job is cancelled, local staging files are cleaned up (source copy and any partial output). No orphaned files remain on local disk after a failed job. Verified via crash recovery logs.

10. If a worker crashes and restarts, crash recovery skips the source copy for any job whose local staging file already exists on disk. The existing local file is reused. Verified via worker logs showing `LocalStaging mode: source already staged, skipping copy` when the file is present.

6. The local staging directory is a Docker volume mount from Larry's local filesystem (not an NFS bind mount). Workers access it inside the container at a well-known path (e.g., `/staging/`). Verified via `docker inspect` showing the volume source is a local path on the LXC.

7. `TemporaryFilePaths` records store canonical NFS paths (not local staging paths) so VMAF and FileReplacement on any machine can find the output file. The local staging is transparent to all downstream stages (QUALITY, REPLACE). Verified via `SELECT * FROM TemporaryFilePaths` showing canonical `T:\` paths for a completed local-staging job.

8. With 4 concurrent workers using local staging, CPU utilization on the worker LXC exceeds 90% during active transcodes (vs ~17% with NFS-direct I/O). Verified via `top` or Prometheus `node_cpu_seconds_total`.

9. The `TranscodeFileMode` SystemSetting gains a third value `LocalStaging` (alongside `InPlace` and `CopyLocal`). Workers read this setting per-job. Changing the setting does not require container restarts. Verified via `POST /api/SystemSettings/TranscodeFileMode` with `{"Value": "LocalStaging"}` and the next job using the local staging path.

11. [BUG] Workers without `StagingDirectory` configured in the Workers table gracefully fall back to InPlace mode when `TranscodeFileMode` is `LocalStaging`. No crash, no data loss. Verified via log message: "LocalStaging mode requires StagingDirectory in Workers table. Falling back to InPlace."

## Status

IN PROGRESS

### Progress

- [x] 1. Add local staging volume to docker-compose.yml and LXC provisioning (local disk mount point on Larry)
- [x] 2. Extend `SetupFilePreparation()` with `LocalStaging` mode: copy source to local, return local path as effective input
- [x] 3. Change output directory to local staging when `LocalStaging` mode is active (FFmpeg writes locally)
- [x] 4. Add copy-back step after successful transcode: local output -> NFS StagingDirectory
- [x] 5. Add local cleanup step: delete source copy + output copy from local staging
- [x] 6. Update `TemporaryFilePaths` to store canonical NFS paths (not local paths) for downstream compatibility
- [x] 7. Add failure cleanup: delete local staging files on job failure or cancellation
- [x] 8. Add `LocalStaging` option to `TranscodeFileMode` SystemSetting
- [ ] 9. Test: 4 concurrent workers, verify CPU >90%, local staging files cleaned up, VMAF + FileReplacement work end-to-end
- [x] 10. Update transcode.flow.md with LocalStaging file staging path

## Scope

```
Features/TranscodeJob/ProcessTranscodeQueueService.py
Features/TranscodeJob/TranscodingFileManagerService.py
deploy/compose-templates/*.yml
terraform/mediavortex-workers/docker-compose.yml
terraform/mediavortex-workers/main.tf
transcode.flow.md
Features/TranscodeJob/local-staging.feature.md
```

## Files

- `Features/TranscodeJob/ProcessTranscodeQueueService.py` -- `SetupFilePreparation()` and `ProcessJob()`: add LocalStaging mode, copy-back, and cleanup
- `Features/TranscodeJob/TranscodingFileManagerService.py` -- `CopyFile()`, new `CleanupLocalStaging()` method
- `deploy/compose-templates/*.yml` -- Add local staging volume mount to each per-host template
- `terraform/mediavortex-workers/docker-compose.yml` -- Add local staging volume mount (production)
- `terraform/mediavortex-workers/main.tf` -- Ensure LXC has local disk mount point for staging
- `transcode.flow.md` -- Update file staging section with LocalStaging mode
- `Core/Services/PathTranslationService.py` -- May need updates if local staging paths need translation
