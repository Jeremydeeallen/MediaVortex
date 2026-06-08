# Local Staging -- per-worker opt-in scratch-disk staging

**Slug:** local-staging

## What It Does

Adds an opt-in, per-worker pre-flight stage that bulk-copies the source from the shared mount to local scratch before encoding, then ships the encoded `.inprogress` back to the canonical side-by-side location after encode + verify. Solves the Microsoft-SMB-on-Windows intermittent-handle-drop pattern that causes long GPU-paced reads to fail with `EINVAL` mid-encode (e.g. `Mune Guardian of the Moon`, 14 failed attempts on I9-2024 over 7 days). Workers without the opt-in (e.g. Linux containers on NFS, which is stable on long reads) keep today's in-place behavior unchanged.

Composed with the prior `transcoded-output-placement.feature.md` durable contract: that doc remains the **default** ("every worker writes side-by-side on the shared mount, no scratch"); this feature is the **opt-in override** that re-introduces staging WITH the cross-worker VMAF reachability fix the original staging design lacked (per-worker scratch dirs were container-local; any other worker claiming the VMAF row got "file not found"). Mode B (copy-back after encode) preserves that reachability for free.

## Concern

Operator observation 2026-06-08: I9-2024 NVENC worker had failed `Mune Guardian of the Moon (2015) Bluray-1080p.mkv` 14 times since 2026-05-31 with FFmpeg exit code 4294967274 (signed -22 = `EINVAL`). Worker log captured `GetFileModificationTime: No such file or directory` 2 minutes into the encode on the same path that had been readable seconds earlier. Same exact ffmpeg command succeeds on a 10-second `-t 10` probe. Pattern matches the documented Microsoft NFS/SMB client intermittent-handle behavior (`memory/feedback_ms_nfs_client_unreliable.md`). Bulk-sequential copy uses a different IO pattern that SMB handles reliably; encoding from local NVMe also typically speeds the encode ~5-15% by removing IO-bound waits.

## Surface

- **`/settings` "Local staging" card** -- single number input for the cluster-wide size floor (`LocalStagingConfig.MinSizeMB`, default 500). Lazy-load on collapse; `PUT /api/SystemSettings/LocalStagingConfig`.
- **`/Activity` worker modal "Local staging" section** -- per-worker scratch dir + enable toggle + local-VMAF-first toggle. `POST /api/TeamStatus/Workers/<name>/LocalStaging`.
- **`/Activity` worker tile** -- compact `Staging: <ScratchDir>` line below the Profiles line when LocalStagingEnabled; omitted otherwise.

## Success Criteria

### A. Schema

C1. Migration `Scripts/SQLScripts/AddLocalStagingColumns.py` is idempotent: `Workers` gains nullable `LocalScratchDir TEXT`, NOT NULL `LocalStagingEnabled BOOLEAN DEFAULT FALSE`, NOT NULL `LocalVmafFirst BOOLEAN DEFAULT FALSE`; `TemporaryFilePaths` gains nullable `LocalSourcePath TEXT` + `LocalOutputPath TEXT`; `LocalStagingConfig` single-row table created (`Id INTEGER PRIMARY KEY DEFAULT 1, MinSizeMB INTEGER NOT NULL DEFAULT 500, LastUpdated TIMESTAMP DEFAULT NOW(), CHECK (Id = 1) AND CHECK (MinSizeMB > 0)`) with a seed `INSERT ... ON CONFLICT DO NOTHING`. Re-runnable.

C2. Post-migration default: every existing Workers row has `LocalStagingEnabled=FALSE`. No worker behavior changes until operator opts in.

C17. `Features/TranscodeJob/LocalStagingConfigRepository.py` is the only emitter of SQL reads/writes against `LocalStagingConfig`. Shape mirrors `Features/TranscodeQueue/QueueAdmissionConfigRepository.py`. Composes `DatabaseService`; no inheritance; no caching.

### B. Staging is its own service (SRP)

C3. `Features/TranscodeJob/LocalStagingService.py` -- single-responsibility module owning the staging decision (`ShouldStage`), source copy (`StageSource`), local-output-path resolution (`ResolveLocalOutputPath`), and cleanup (`Cleanup`, `CleanupJobScratchDir`). Composes `DatabaseService` + `LocalStagingConfigRepository`; reads `Workers` columns fresh per call (db-is-authority -- no `self._cached_*`).

C4. `ProcessTranscodeQueueService.SetupFilePreparation` consults `LocalStagingService.ShouldStage(WorkerName, SourceSizeMB)`; on TRUE, calls `StageSource` and returns the staged local path as `EffectiveInputPath`. Falls back to canonical mount on copy failure.

### C. Staging gate

C5. `LocalStagingService.ShouldStage` returns TRUE iff **all three**: (i) `Workers.LocalStagingEnabled=TRUE`, (ii) `Workers.LocalScratchDir` is non-empty, (iii) source `SizeMB >= LocalStagingConfig.MinSizeMB` (default 500). All three reads are fresh per call.

C6. Workers without the opt-in keep today's in-place behavior byte-identical -- the staging code path is skipped entirely when ShouldStage returns FALSE.

### D. Local-path routing through ffmpeg

C7. `QualityTestRepository.CreateTemporaryFilePath` accepts optional `LocalSourcePath` + `LocalOutputPath` and persists them on the row alongside the canonical typed pair. `GetTemporaryFilePath` reads + prefers the local columns over canonical-synthesized paths; returns `IsStaged` boolean for the consumer.

C8. **One-knob-per-attempt invariant.** Staging changes ONLY the ffmpeg `-i <source>` argument and the output `.inprogress` location -- every other arg (codec, bitrate, scale, audio, loudnorm, pix_fmt) is byte-identical to the non-staged version of the same profile.

### E. Two-mode VMAF disposition

C9. **Mode A (local-only VMAF) -- `Workers.LocalVmafFirst=TRUE AND Workers.QualityTestEnabled=TRUE`:** after encode, the same worker runs VMAF against `LocalSourcePath` vs `LocalOutputPath` BEFORE shipping `.inprogress` back to canonical. Pass -> copy-back + FileReplacement. Fail -> record attempt + cleanup local; no canonical write. **STATUS: flag plumbed end-to-end (DB + repo + endpoint + UI); QualityTestingBusinessService dispatch deferred to follow-up `/n local-staging-mode-a`.**

C10. **Mode B (cross-worker hand-off) -- default:** after encode, worker copies local `.inprogress` to canonical side-by-side path BEFORE downstream dispatch (FileReplacement or VMAF queue claim). Any worker can then claim the VMAF row and read the canonical input/output paths -- the prior cross-worker reachability failure that killed the original staging design does NOT recur. `_CopyBackStagedOutput` size-verifies; on mismatch, deletes the partial canonical write and fails the job loudly.

### F. Cleanup discipline

C11. Local scratch removed on every attempt-finalize: success (after copy-back), failure (`_CleanupFailedAttemptFiles` extended to call `LocalStagingService.Cleanup` on local paths when TFP `IsStaged=True`). Idempotent.

C12. `CrashRecoveryService` orphan sweep extension for `<LocalScratchDir>` files whose TFP is finalized: **DEFERRED to follow-up `/n local-staging-crash-recovery`**. Crash-mid-encode today leaves stale files; operator manually cleans. Foreground cleanup paths (success / fail) work correctly.

### G. Operator surface

C13. `/Activity` worker modal gains a "Local staging" section (scratch-dir input + Enable + LocalVmafFirst toggles + Save). Backed by `POST /api/TeamStatus/Workers/<name>/LocalStaging` (validates non-empty scratch when Enabled=TRUE; 400 otherwise). `GET /api/TeamStatus/Workers` payload extended with the three fields.

C14. Worker tile compact `Staging: <ScratchDir>` line below Profiles line when LocalStagingEnabled; 80-char truncate; tooltip with full path + mode label. Omitted when off.

C16. `/settings` "Local staging" collapsible card with a number input bound to `LocalStagingConfig.MinSizeMB`. `GET/PUT /api/SystemSettings/LocalStagingConfig`. Lazy-load on expand; alert confirmation on save matches existing convention.

### H. Flow doc

C15. `transcode.flow.md` Stage 5 (ST6) "File staging" subsection documents the conditional opt-in local-staging branch alongside the default in-place path. S2 seam row extended with LocalSourcePath/LocalOutputPath + IsStaged transparency to downstream consumers.

## Status

SHIPPED 2026-06-08 -- closed directive at `.claude/directives/closed/2026-06-08-local-staging.md`. C1-C8, C10-C11, C13-C17 fully implemented. C9 (Mode A dispatch) + C12 (crash-recovery sweep) plumbed but deferred to follow-up directives (see `### Decisions Made` in the closed directive doc).

### Files

```
Scripts/SQLScripts/AddLocalStagingColumns.py                  -- migration (Workers + TFP + LocalStagingConfig)
Core/Database/<no changes>                                    -- existing helpers consumed
Features/TranscodeJob/LocalStagingConfigRepository.py         -- single emitter for LocalStagingConfig
Features/TranscodeJob/LocalStagingService.py                  -- SRP: ShouldStage / StageSource / Cleanup
Features/TranscodeJob/ProcessTranscodeQueueService.py         -- SetupFilePreparation + ProcessJob copy-back + helpers
Features/QualityTesting/QualityTestRepository.py              -- TFP CRUD extended with local-path columns
Features/Workers/WorkersRepository.py                         -- UpdateWorkerLocalStaging + GetWorkerLocalStagingConfig
Features/TeamStatus/TeamStatusController.py                   -- POST LocalStaging endpoint + GET /Workers extension
Features/SystemSettings/SystemSettingsController.py           -- GET/PUT /api/SystemSettings/LocalStagingConfig
Templates/Settings.html                                       -- /settings Local staging card
Templates/Activity.html                                       -- per-worker modal section + tile line
transcode.flow.md                                             -- Stage 5 staging subsection + S2 seam update
Tests/Contract/TestLocalStaging.py                            -- 16 tests, all pass
```

## Operator runbook (post-deploy)

1. **Confirm migration applied.** `py Scripts/SQLScripts/QueryDatabase.py sql "SELECT * FROM LocalStagingConfig"` returns 1 row.
2. **Adjust the global floor** (optional). `/settings` -> "Local staging" -> set MinSizeMB (default 500) -> Save.
3. **Enable per-worker** (the operator-facing knob). `/Activity` -> click I9-2024 tile -> "Local staging" section -> set Scratch dir (e.g. `D:\MediaVortexScratch`) -> check Enable staging -> leave Local VMAF first OFF (Mode A deferred) -> Save Staging.
4. **Verify on next claim.** Worker logs `LocalStaging active for MediaFileId=<id>; copying to scratch before encode`. After encode + verify, logs `Copy-back complete for MediaFileId=<id>`. Local scratch subdir empty post-attempt.
5. **Re-queue Mune** (the smoke). Set Mune's profile to NVENC, queue, observe successful completion.

## See also

- `Features/FileReplacement/transcoded-output-placement.feature.md` -- the default in-place contract that this feature overrides per-worker.
- `memory/feedback_ms_nfs_client_unreliable.md` -- the SMB-on-Windows pattern motivating the work.
- `memory/KNOWN-ISSUES.md#BUG-0045` -- comma-separated directive-anchor convention + 3 hook validator improvements (filed during this directive's implementation).
- Follow-ups: `/n local-staging-mode-a` (C9 dispatch), `/n local-staging-crash-recovery` (C12 sweep), `/n anchor-convention-comma-separated` (BUG-0045).
