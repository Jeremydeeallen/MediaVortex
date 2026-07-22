# End-to-End Bug and Failure Fixes

**Slug:** e2e-bug-fixes

## Interrupts: audio-vertical-dialog-boost-enforcement

## What It Does

Triage and fix every bug or failure mode that prevents MediaVortex from delivering a media file end-to-end through the pipeline: bucket admission -> claim -> probe -> transcode -> verify -> replace -> notify -> recompute. Improvement / refactor / DDD-polish work is paused; scope is delivery reliability, not architecture cleanup.

Every discovered issue is either fixed in this directive or filed with `/b BUG-NNNN` and a written reason it cannot land here. No silent "will address later."

## Success Criteria

Baseline captured 2026-07-17: `SELECT LogLevel, FunctionName, LEFT(Message, 200), COUNT(*) FROM Logs WHERE Timestamp > NOW() - INTERVAL '48 hours' AND LogLevel IN ('WARNING','ERROR','CRITICAL')` returned 100+ distinct patterns. Criteria below name every non-trivial repeating failure. Each criterion is: **root cause fixed AND the exact log signature returns zero hits over the 60-minute post-fix soak window**.

### Group A -- path plumbing (repository / scanning collapse)

C1. `ExtractShowInfo` (`ScheduleService`) no longer raises `Path.__init__() missing 1 required positional argument: 'RelativePath'`. Baseline: 251 hits/48h. Fix pattern: `Path()` constructed at that call site with the missing arg (probably a `MediaFiles.RelativePath` lookup that returns `None`). See `.claude/rules/fail-loud.md` -- upstream write is the bug, not the caller's guard.

C2. `FileScanningBusinessService.<method>` no longer raises `'FileScanningRepository' object has no attribute 'GetMediaFilesByRootFolderId'`. Baseline: 58 hits/48h. Fix: add the missing repository method OR retarget caller to the renamed method.

C3. `ReconcileWithDisk` no longer raises `'FileScanningRepository' object has no attribute 'GetMediaFilesByRootFolder'`. Baseline: 58 hits/48h. Companion of C2.

C4. `MediaProbeRepository` no longer raises `column "rootfolder" does not exist` on `SELECT RootFolder FROM RootFolders WHERE Id = %s`. Baseline: 58 hits/48h (29 get + 29 count). Column was renamed (likely to `Path` / `RootPath`); update the SQL. `SchemaChecker` snapshot drift check should have caught this pre-deploy.

C5. `FileScanningRepository` no longer raises `LocalPath op refused canonical drive-letter path on non-Windows worker: 'M:\\' / 'T:\\'`. Baseline: 58 hits/48h. Route through `Path.FromLegacyString(...).Resolve(worker)` per the hook's stated path forward. See `.claude/rules/mediavortex-paths` skill + `.claude/rules/feedback_hook_path_forward_is_the_answer.md`.

### Group B -- replacement / uniqueness collision (OUT OF SCOPE)

C6, C7, C8, C9 are **OWNED BY `mediafiles-uniqueness-owner`** (paused, one level down in the stack). Domain call 2026-07-18: pop this directive back to that one, finish it, then C6-C9 auto-resolve. Do not land tactical fixes for them in e2e-bug-fixes.

C10. `TranscodeQueueRepository: Refusing to admit queue row -- source already MediaVortex-transcoded (Pokémon/...)` cluster drops to zero. Baseline: 300+ hits/48h across ~40 distinct Pokémon files. Fix: purge the stale pre-2026-07-16 `TranscodeQueue` rows whose `FilePath LIKE '%-mv.mp4%'` -- they pre-date commit 7e562a9's admission gate and are stuck re-emitting the refusal. Scanner + admission code is already correct.

### Group C -- crash-recovery no-op storm

C11. `CrashRecoveryService: Crash recovery: completed partial replacement for X -> X` (identical source == destination path) is either eliminated (recovery loop is scanning already-replaced files) OR downgraded to INFO with rationale. Baseline: 500+ hits/48h across ~50 distinct files. A "recovery" that recovers nothing is either a bug in the scanner's terminated-attempt detection OR successful recovery that shouldn't be a WARNING.

### Group D -- worker config discovery

C12. `ProcessTranscodeQueueService: FFprobePath was NULL on worker init; discovered ... Persist this in Workers.FFprobePath for I9-2024` and companion FFmpegPath warning both drop to zero. Baseline: 67 + 67 hits/48h. The warning text names the fix: self-persist the discovered path. Feedback memory `feedback_all_installs_via_requirements_txt.md` context applies -- if this is a deploy-provisioning gap, the deploy artifact is the fix.

### Group E -- video-transcoding logger misuse

C13. `VideoTranscodingService: FFmpeg stdout: ffmpeg version ...` no longer logs the FFmpeg version banner at ERROR level. Baseline: 15 hits/48h. FFmpeg's normal stdout is not an error. Fix: gate on process return code / stderr regex, not on "FFmpeg emitted output".

### Group F -- thread context

C14. `WebService: Jellyfin auto-sync error: WorkerContext.Current called on unbound thread. Call WorkerContext.Bind() at thread entry` drops to zero. Baseline: 12 hits/48h. Fix: call `WorkerContext.Bind()` in the auto-sync thread's entry function.

### Group G -- audio classification noise

C15. `SelectPreferredAudioStream: No English audio stream found among 1 stream(s) (languages: [X]), using first stream` (where X is `und`/`fre`/`dan`/`hin`/etc) is either eliminated for `und` (single-`und` stream is the normal case for a lot of media -- it should not warn) OR downgraded to INFO. Baseline: 316+ hits/48h across languages. Non-English single-stream media landing here isn't a failure; it's the expected fallback.

### Group H -- deploy-artifact hygiene

C16. `ContentSignalsService: PySceneDetect not installed; SceneChangeRatePerMin will be NULL` drops to zero. Baseline: 5 hits/48h. Add `scenedetect>=0.6.0` to `requirements.txt` per `feedback_all_installs_via_requirements_txt.md`; redeploy Linux workers.

C17. `SchemaChecker: no snapshot at /opt/mediavortex/.claude/schema/snapshot.json` drops to zero. Baseline: 4 hits/48h. Either the snapshot is missing from the Linux worker container image OR `GenerateSchemaSnapshot.py` needs to run at deploy time. Snapshot presence would have caught C4 pre-deploy.

### Group I -- meta

C18. Every bug discovered during triage lands one of two outcomes: fixed in this directive with a `## Bugs Fixed` row + commit ref, or filed as `/b BUG-NNNN` with a written reason it cannot be part of this directive (irreversible migration, hardware requirement, design work). Zero silently deferred bugs.

C19. `memory/KNOWN-ISSUES.md` is swept: every entry marked RESOLVED in this directive is moved to the Resolved section; every entry still Active is re-verified against current code (root cause still applies, repro still reproduces, or entry is closed/rewritten).

C20. Post-fix soak: `SELECT LogLevel, FunctionName, LEFT(Message, 200), COUNT(*) FROM Logs WHERE Timestamp > <post-deploy-ts> AND LogLevel IN ('WARNING','ERROR','CRITICAL') GROUP BY 1,2,3 ORDER BY 4 DESC LIMIT 20` shows no C1-C17 pattern in the top 20. New patterns discovered during soak flow through C18.

### Group L -- QSV Tier ladder recalibration (added 2026-07-20 after live VMAF sample + shootout)

C23. `AV1 Tier 1 Efficient` produces VMAF 78.52 on wakko QSV (measured live and confirmed via `Scripts/Smoke/matrices/CriminalMinds-QSV-PresetSweep.matrix.json` shootout 2026-07-20). Auto-replace threshold is 88; every wakko encode fails QT gate. Root cause: QSV `ICQ q=34` was too aggressive for the intended "Efficient" tier baseline. Shootout data (Criminal Minds S01E01 480p, av1_qsv, preset 1): q=34 -> VMAF 78.52 / 68 MB; q=32 -> 83.62 / 81 MB; q=30 -> 87.60 / 96 MB. `-preset` on Arc B580 AV1 QSV moves VMAF <=1.5 points across the full 1-7 range and does NOT change encode time (CPU decode pipeline is the bottleneck at ~500 fps upstream). `q` is the only meaningful quality lever. Fix: lower `ProfileThresholds.IcqQ` by 4 across Tiers 1-4 (Tier 5 unchanged at q=22). New ladder: T1=30 (VMAF ~88), T2=28 (~91), T3=26 (~93), T4=24 (~95), T5=22 (~97). NVENC path (I9 + dot) untouched -- uses `TargetKbps` for VBR, not IcqQ. Verifiable: post-change wakko VMAF sample on Tier 1 should land 87-89.

C24. QSV preset scale is INVERTED from NVENC and is not intuitive. Document once so it does not re-trip: NVENC `-preset p1` = fastest / worst quality, `p7` = slowest / best quality. QSV `-preset 1` = veryslow / best quality (oneVPL `TargetUsage=1`), `-preset 7` = veryfast / worst quality (`TargetUsage=7`). Verified via `ffmpeg -h encoder=av1_qsv`. Production QSV uses `-preset 1` -- already the best QSV preset. Do NOT propose raising the preset number thinking it slows down -- it speeds up + drops quality. On Arc B580 AV1 the effect is small (<=1.5 VMAF) either way. Only meaningful quality lever on QSV is `-global_quality` (ICQ q).

### Group M -- Output-file provenance metadata (added 2026-07-20)

C25. Every MediaVortex-emitted `-mv.mp4` carries provenance metadata in its `moov/udta` box so `ffprobe -show_format` of the output tells the operator exactly which worker, profile, encoder, source commit, and timestamp produced it. Root motivation 2026-07-20: after the Tier 1 QSV recalibration + C22 profile-label fix, operator asked "which worker transcoded this file?" -- current `TranscodeAttempts` row is authoritative but requires DB lookup. File-embedded metadata survives DB restore + moves with the file across hosts/backups. Fix: extend `CommandComposer.Build` (line 66) from single `-metadata "comment=Transcoded by MediaVortex"` to a full provenance block:
  - `comment` = "Transcoded by MediaVortex" (unchanged for player UIs that show comment)
  - `mediavortex_worker` = `WorkerContext.Current().WorkerName`
  - `mediavortex_profile` = `MediaFile.AssignedProfile` (trustworthy per C22)
  - `mediavortex_encoder` = `av1_nvenc` / `av1_qsv` / `libsvtav1` / `copy` (derived from ProfileSettings + Plan_.VideoOp)
  - `mediavortex_commit` = short SHA read from `MediaVortex/VERSION` (cached at CommandComposer init; process-lifetime stable)
  - `mediavortex_ts` = UTC ISO 8601 timestamp at command-build time
No Attempt.Id because command builds BEFORE the attempt row is created (chicken/egg). Operator can join by (worker, ts) if needed. Verifiable: post-fix, `ffprobe -show_format -v error <any-new-mv.mp4> | grep mediavortex_` returns all 5 keys.

### Group T -- AttemptDate immutability (added 2026-07-21)

C32. `TranscodeAttempts.AttemptDate` is set once at `CreateTranscodeAttempt` and never overwritten. Root cause 2026-07-21 (surfaced by larry CPU-Demucs canary): `JobProcessor.Process` line 116-124 UPDATEd `AttemptDate = datetime.now(timezone.utc)` AFTER Demucs pre-pass and BEFORE encode. Wall-time reports (CompletedDate - AttemptDate) then measured only the encode portion, hiding all pre-encode time. Real observed CPU-Demucs took ~12.5 min but DB `wall_sec` showed 59-150s -- a 6-15x under-count that would mask real performance regressions and make throughput planning impossible.

The offending UPDATE re-wrote 7 fields (FilePath, AttemptDate, OldSizeBytes, NewSizeBytes, Success, FfpmpegCommand, VMAF). Only `FfpmpegCommand` was actually new information (command not known until after `BuildCommand`); the other 6 were redundant re-writes of values already correct from `CreateTranscodeAttempt`. Fix: reduce the UPDATE to write ONLY `FfpmpegCommand`. Delete the redundant fields.

Verification: (a) requeue an AudioFix on larry -> `SELECT AttemptDate FROM TranscodeAttempts WHERE Id = <n>` matches the pre-Demucs timestamp; `wall_sec = CompletedDate - AttemptDate` reports the true full-pipeline wall (source.measure + Demucs + encode + post-encode); (b) contract test asserts that on a two-phase pipeline (any Demucs-required mode), the `AttemptDate` seen 30s into the pipeline equals the `AttemptDate` seen at completion.

### Group S -- MediaVortex-output compliance exemption (added 2026-07-21)

C31. `VideoVertical.Evaluate` returns `(True, 'mediavortex_output_accepted')` as its first check when `Mf.TranscodedByMediaVortex` is True. Every subsequent video-side rule (codec allowlist, bpp threshold, resolution-exceeds, bitrate-ceiling) is skipped for MV outputs. `AudioVertical` and `ContainerVertical` still run so audio-only or container-only issues route through `AudioFix` / `Remux` as normal.

Domain decision (operator 2026-07-21): a MediaVortex-produced `-mv.mp4` file's original source is gone (deleted at first successful replacement). The current file IS the output MediaVortex intended. Re-transcoding an already-compressed AV1 file at any different profile produces generation-loss without quality recovery -- we cannot recover pixel information already quantized away. If operator wants better quality on already-transcoded shows, the correct path is Sonarr re-download (fresh original) + first-time transcode from that source. Compliance-driven bpp / bitrate-ceiling re-queue on MV outputs is domain-wrong.

Files touched:

- `Features/VideoEncoding/VideoVertical.py` -- `Evaluate` short-circuits on `TranscodedByMediaVortex=TRUE` before any other check.
- `Features/VideoEncoding/video-encoding.feature.md` -- adds C6 documenting the domain rule.
- `Scripts/SQLScripts/RecomputeVideoComplianceForMvOutputs_2026_07_21.py` -- one-off migration that calls `VideoVertical.RecomputeFor` for every existing `TranscodedByMediaVortex=TRUE` MediaFile so their `VideoCompliant`/`WorkBucket` flip from the stale non-compliant state to the new exempt state.
- `Tests/Contract/TestVideoVerticalMvOutputExempt.py` -- asserts `Evaluate` returns `(True, 'mediavortex_output_accepted')` for any TranscodedByMediaVortex=TRUE MediaFile regardless of codec/bpp/bitrate/resolution values.

Verification: (a) `SELECT COUNT(*) FROM MediaFiles WHERE TranscodedByMediaVortex=TRUE AND VideoCompliant=FALSE AND VideoCompliantReason NOT LIKE 'mediavortex_output_accepted%'` returns 0 after migration. (b) `SELECT COUNT(*) FROM MediaFiles WHERE TranscodedByMediaVortex=TRUE AND WorkBucket='Transcode'` returns 0 after compliance recomputer runs. (c) An MV output with a legitimate audio-only issue still routes to `WorkBucket='AudioFix'` (video short-circuit does not block Audio evaluation).

### Group R -- Success semantic tightened + no self-heal + no retry (added 2026-07-21)

C30. `TranscodeAttempts.Success` carries a single strict end-to-end pipeline semantic:

- `NULL` = pipeline in flight (encode + post-encode + replacement all pending)
- `TRUE` = pipeline complete AND succeeded end-to-end (Replace + FileReplaced=TRUE, OR Reject decided cleanly, OR Requeue scheduled)
- `FALSE` = pipeline failed at ANY step (encode returncode!=0, PFR raised, gate refused unexpectedly, disk error during rename, etc.) AND `ErrorMessage` carries the reason for the failure GUI

Domain decisions (operator 2026-07-21):

1. Dashboards read pipeline-succeeded semantic. "Successful transcode" counters, savings totals, throughput graphs all filter on `Success=TRUE`. Failed rows surface in the failure GUI with the `ErrorMessage` reason.
2. No retry logic. Failed pipelines do NOT auto-retry. Operator sees the reason in failure GUI, fixes the root cause, manually re-queues the MediaFileId. Fail-loud is the interface.
3. No self-heal loop. `FileReplacementSelfHealService` was deleted in C29 as a cross-tenant DDD violation; it stays deleted. WebService threads MUST NOT invoke Worker-owned services that need `WorkerContext.Current()`.
4. Claim lock is `ta_one_inflight_per_mfid ON MediaFileId WHERE Success IS NULL`. Under the tighter semantic, Success stays NULL through the entire pipeline (encode + PFR + replacement), so the partial UNIQUE index blocks duplicate claims end-to-end.

Files touched:

- `Features/TranscodeJob/ProcessTranscodeQueueService.py` -- `HandleTranscodingResult` writes Success=True only AFTER `DispatchDisposition` returns clean; outer catch writes Success=False + ErrorMessage on any exception. `DispatchDisposition` propagates exceptions (no internal swallow); accepts `EncodeSucceeded: bool` param and passes to dispatcher.
- `Features/QualityTesting/Disposition/DispositionDispatcher.py` -- `Dispatch(TranscodeAttemptId, EncodeSucceeded=None)`; `_BuildDeciderInput` uses the param instead of reading `Row.get('Success')` (encode-success is a caller fact, not a DB read).
- `Tests/Contract/TestFileReplacementDrain.py` -- adds invariant `Success=TRUE AND FileReplaced=FALSE` = 0.

Verification: (a) requeue MediaFileId=8167 canary -> attempt row stays Success=NULL through source.measure / demucs / Transcoding / post-encode probe / rename / MediaFiles update; only flips Success=TRUE when TranscodedOutputPlacement completes end-to-end and `Renamer.Commit()` fires. (b) simulate a PFR failure (e.g. inject invalid TFP row) -> attempt row lands Success=FALSE + ErrorMessage carrying the exception text; no ghost row (no Disposition=Replace + FileReplaced=FALSE + Success=TRUE state possible). (c) contract test `TestFileReplacementDrain.test_success_true_requires_filereplaced_true` returns 0 stuck rows in steady state.

### Group Q -- TranscodeAttempts.ProcessingMode SSOT + fail-loud on PFR failure (added 2026-07-21)

C29. `TranscodeAttempts` gets a `ProcessingMode TEXT` column populated by `CreateTranscodeAttempt` from `Job.ProcessingMode`. `FileReplacementBusinessService.ProcessFileReplacement` reads that column directly; the fragile `AttemptMode = transcode_attempt.ProfileName or 'Transcode'` inference at line 206 is deleted. `DispatchDisposition` inspects `PFR`'s return value and RAISES on `Success=False` so the outer catch writes the actual error to `TranscodeAttempts.ErrorMessage` (fail-loud). `FileReplacementSelfHealService` + its WebService background loop deleted (cross-tenant WebService-doing-Worker-work DDD violation; the "Recovery refused (self-heal)" ErrorMessage overwrites blocked diagnosis by hiding the real PFR error). Root cause 2026-07-21: e2e-bug-fixes.C22 (this session) forced `TranscodeAttempts.ProfileName = MediaFile.AssignedProfile` (real profile name like `'AV1 Tier 1 Efficient'`). Line 206 relied on ProfileName being one of the ProcessingMode strings (`'Transcode' / 'Remux' / ...`) via the pre-C22 fallback bug. After C22, `PostFlightRegistry.Get('AV1 Tier 1 Efficient')` raised KeyError -> MediaFiles update failed -> rename rolled back -> `.inprogress` orphaned. `DispatchDisposition` silently ignored the failure return; `FileReplacementSelfHealService` stamped "Recovery refused" over the real error text. Both hid the underlying design flaw: ProcessingMode was not a stored fact per attempt; it was inferred from ProfileName. **Every "successful" Replace attempt in this session (46618, 46621, 46623, 46625) has Disposition=Replace AND FileReplaced=FALSE AND source file untouched on disk.** Data-integrity impact: DB says replaced, disk says untouched, Jellyfin still serves originals, `.inprogress` cruft accumulates. Migration `AddTranscodeAttemptsProcessingMode_2026_07_21.py` adds the column and back-fills existing rows from `TranscodeQueue.ProcessingMode` where the join is still resolvable (queue rows for completed attempts get deleted in `HandleTranscodingResult`, so historical rows may land with NULL and are diagnosed via a `SELECT COUNT(*) WHERE ProcessingMode IS NULL`). Verification: post-fix, requeue MediaFileId=8167 canary -> `SELECT Disposition, FileReplaced FROM TranscodeAttempts WHERE Id = <new>` returns `('Replace', TRUE)`; `ls` on the shared mount shows source `.mkv` replaced by `-mv.mp4` (no `.inprogress` orphan). Ripple audit: `grep -rn 'FileReplacementSelfHealService' --include='*.py'` returns 0 hits in production; WebService no longer spawns its self-heal background thread. Follow-up (not in this criterion): Success flag on TranscodeAttempts conflates "encode succeeded" with "post-encode pipeline succeeded"; split into distinct facts so failed replacement doesn't leave the attempt marked Success=True.

### Group P -- Delete legacy LoudnessMeasurementFailureReason gate (added 2026-07-21)

C28. `MediaFiles.LoudnessMeasurementFailureReason` column + every read/write of it is deleted. Root cause 2026-07-21 (surfaced by e2e-bug-fixes.C27 canary): the column pre-dates the modern `AudioPolicyAdmissionGate` + `LoudnessMeasurementValidator` pattern documented in `audio-normalization.feature.md` C13 + Cross-Vertical Contract. The doc's authoritative writes table (line 282-297) does not list `LoudnessMeasurementFailureReason` -- the column is off-contract legacy cruft. Domain-correct loudness gating is: `LoudnessMeasurementValidator.IsValid(Mf)` returns False when any of the four ebur128 columns is NULL or `SourceIntegratedLufs <= -60` silence-floor; `AudioPolicyAdmissionGate.AdmitOrDefer` calls the validator and sets `MediaFiles.AdmissionDeferReason = 'invalid_loudness_measurement'` via `AudioRemeasurementService.MarkForRemeasurement`. `AudioVertical.Evaluate` carried a REDUNDANT `if LoudnessMeasurementFailureReason: defer` pre-gate that duplicated the admission gate two lines below. `EbuR128MeasurementService.PersistLoudness` wrote the column with a diagnostic failure code on ffmpeg-crash paths -- but a race between `AudioRemeasurementRunner` and a worker's encode (both ffmpeg reading the same source over SMB) caused the runner's ffmpeg to exit -1 and stamp the column even when `SourceIntegratedLufs` was still valid. `AudioVertical.Evaluate` then rejected the (just-encoded, cleanly-measured) file with `ComplianceGateFailed: loudness_measurement_failed`. Root fix (SSOT + fail-loud + KISS): delete the column, delete the writes, delete the pre-gate check, delete every read + object-construction reference across `MediaFilesRepository`, `QueueManagementBusinessService`, `ComplianceGate`, `MediaFileModel`, `TestAudioComplianceBar`. `EbuR128MeasurementService.MeasureAndPersist` still returns `(Success, FailureReason)` so callers (`MediaProbeBusinessService`) can log the reason -- but nothing persists it, so no stale-state class of bug is possible. Migration `DropLoudnessMeasurementFailureReasonColumn_2026_07_21.py` drops the column idempotently. Verification: post-fix, `grep -rn 'LoudnessMeasurementFailureReason' --include='*.py' Features Scripts` returns 0 hits outside the migration script itself; requeue The Resident S01E11 (MediaFileId=8167) on wakko-worker-1 -> `Disposition=Replace` not `Reject`; `SELECT LoudnessMeasurementFailureReason FROM MediaFiles LIMIT 1` errors with "column does not exist" (proof of drop). (Follow-up idea, not in this criterion: teach `AudioRemeasurementRunner` to skip files with an in-flight `TranscodeAttempts` row so the SMB read race stops occurring at all -- prevention beyond cleanup.)

### Group O -- Hardware-accelerated decode (added 2026-07-21)

C27. `CommandComposer.Build` emits `-hwaccel` + `-hwaccel_output_format` pre-input args (and swaps the scale filter to the hwaccel-native variant) whenever the claiming worker's `Workers.HwAccelDecodeEnabled = TRUE` AND the source codec is in the backend's allow-list AND the encoder can accept hardware surfaces end-to-end. Root cause 2026-07-21: `VideoSlot._EmitQsvArgs` + `_EmitNvencArgs` only add OUTPUT-side encoder args (`-c:v av1_qsv` / `av1_nvenc`); no `-hwaccel qsv` / `-hwaccel cuda` before `-i`. Every frame CPU-decodes -> RAM -> PCIe upload -> GPU encode -> PCIe download -> file. Two roundtrips per frame; CPU decode is the throughput bottleneck. Live measurement 2026-07-21 (The Resident S01E11 hevc 1080p, 60s sample):

| Config | Encoder | fps | speed | Gain |
|---|---|---|---|---|
| Baseline (no hwaccel, no scale) | av1_qsv wakko | 251 | 10.4x | -- |
| +hwaccel qsv (decode-only) | av1_qsv wakko | 317 | 13.2x | +27% |
| Baseline + CPU scale 1080p->720p | av1_qsv wakko | 367 | 15.3x | -- |
| +hwaccel qsv + scale_qsv (zero-copy) | av1_qsv wakko | **657** | **27.4x** | **+79%** |
| Baseline (no hwaccel, no scale) | av1_nvenc dot | 386 | 16.1x | -- |
| +hwaccel cuda +output_format cuda | av1_nvenc dot | **503** | **21.0x** | **+30%** |
| Baseline + CPU scale 1080p->720p | av1_nvenc dot | 671 | 28.0x | -- |
| +hwaccel cuda + scale_cuda | av1_nvenc dot | 264 | 11.0x | **-61% regression** |

**v1 rules (KISS -- no orchestration branching; decisions live in one resolver):**
- QSV + codec supported: always emit `-hwaccel qsv -hwaccel_output_format qsv`; when scale filter present, swap `scale=` for `scale_qsv=`. Full zero-copy always.
- NVENC + codec supported + NO scale filter needed: emit `-hwaccel cuda -hwaccel_output_format cuda`. Same-res encode benefits.
- NVENC + codec supported + scale needed: NO hwaccel emitted (baseline CPU-decode + CPU-scale already 671 fps; `scale_cuda` on this ffmpeg build regresses to 264 fps).
- Codec not in backend allow-list (`h264, hevc, av1, vp9, mpeg2video, vc1`): NO hwaccel emitted (CPU fallback).
- `Workers.HwAccelDecodeEnabled = FALSE`: NO hwaccel emitted (operator kill switch, per-host, GUI-toggleable via Admin/Workers page).

**Files touched:**
- `Scripts/SQLScripts/AddWorkersHwAccelDecodeEnabled_2026_07_21.py` -- migration (default FALSE; operator opts each host in via GUI)
- `Features/TranscodeJob/Emit/HwAccelResolver.py` -- new; `HwAccelConfig` dataclass + `HwAccelResolver.Resolve(WorkerRow, ProfileSettings, MediaFile, RequiresScale) -> Optional[HwAccelConfig]`
- `Features/TranscodeJob/Emit/CommandComposer.py` -- reads worker row fresh from `WorkerContext.Current().WorkerName`; passes `HwAccelConfig` to slot emission; swaps scale filter suffix when backend requires it
- `Features/TranscodeJob/Emit/Slots/VideoSlot.py` -- new `EmitInputArgs(HwAccel)` seam returns pre-input args (`[]` when None); `Emit(...)` (output-side) unchanged
- `Features/Activity/Services/DashboardSnapshotService.py` -- SELECT includes `hwacceldecodeenabled` for the Admin/Workers page
- `Templates/AdminWorkers.html` -- checkbox column mirroring `TranscodeEnabled` pattern
- `Features/Workers/WorkersController.py` -- PATCH endpoint accepts `HwAccelDecodeEnabled`
- `Tests/Contract/TestHwAccelResolver.py` -- allow-list + toggle + scale-filter swap invariants

Verification: (a) After migration + deploy + `UPDATE Workers SET HwAccelDecodeEnabled=TRUE WHERE WorkerName='wakko-worker-1'`, next wakko transcode's `TranscodeAttempts.FfPmpegCommand` includes `-hwaccel qsv -hwaccel_output_format qsv` and `-vf scale_qsv=...` (when scaling). (b) Live encode fps observed on `/Activity` is >=2x prior sample on same file class. (c) `SELECT count(*) FROM TranscodeAttempts WHERE FfPmpegCommand LIKE '%hwaccel qsv%' AND AttemptDate > <post-deploy-ts>` returns non-zero. (d) VMAF gate unaffected (same encoder settings, different feed path).

### Group N -- Dialog Boost as Track 0 (added 2026-07-21)

C26. Every 2-track MediaVortex-emitted `-mv.mp4` places Dialog Boost at output audio Track 0 and Original at output audio Track 1. `default=1` disposition stays on the Boost track; Original carries `default=0`. Root motivation 2026-07-21: MP4/MKV `default` flag is advisory. Many TV apps (older Samsung / LG, PS5, several Chromecast profiles, some Jellyfin TV clients) pick output-index-0 blindly regardless of `default` disposition. Result today: ~half of playback surfaces get Original instead of Boost even though the DB says Boost was default. Fix: swap emit order in `AudioFilterEmitter.EmitTracks:132-141` -- when `EmitDialogBoost and IsDefaultLanguage` is true for a stream, emit `_BuildDialogBoostBlock` first (OutputIndex 0) then `_BuildOriginalBlock` (OutputIndex 1, IsDefault=False). Non-boost path unchanged (Original at Track 0 with `default=IsDefaultLanguage`). Both signals (track index + default flag) then align. Historical `-mv.mp4` files keep old order; not backfilled (advisory-flag-aware clients still play Boost via default). Verification: post-fix, `ffprobe -show_streams -select_streams a <any-new-2-track-mv.mp4>` shows stream 0 with title=`Dialog Boost`, stream 1 with title=`Original`, and stream 0 `DISPOSITION:default=1`.

### Group K -- ProfileName label integrity (added 2026-07-20)

C22. `TranscodeAttempts.ProfileName` reflects the real profile used (e.g. `AV1 Tier 2 Good`), NEVER the ProcessingMode fallback (`Transcode` / `Remux` / `AudioFix` / `SubtitleFix` / `Quick`). Root cause 2026-07-20: `ProcessTranscodeQueueService.CreateTranscodeAttempt` (line 973-995) synthesizes a `MockMediaFile` with `AssignedProfile=None` when the fetched MediaFile is None, then falls back to `ProfileName = JobMode`. `HandleJobFailure` (line 1204-1206) uses the same fallback via `Job.AssignedProfile` which is ALWAYS empty (the field exists on `TranscodeQueueModel` line 20 but the claim query never populates it). Result: 100% of the 4,477 successful attempts in the last 14 days were written as `ProfileName='Transcode'`, hiding real quality attribution. Fix (fail-loud, SSOT-clean): (a) delete the mock-MediaFile fallback in `CreateTranscodeAttempt`; (b) delete the JobMode fallback in both call sites; (c) add helper `_ResolveMediaFileOrRaise(Job)` that fetches by `MediaFileId` (primary-key lookup, not fragile `GetMediaFileByPath`) and raises when unresolvable; (d) add `_ResolveProfileNameOrRaise(MediaFile)` that raises if AssignedProfile is empty; (e) delete stale `TranscodeQueueModel.AssignedProfile` field (never populated by any claim query -- misleading, was the seed of the wrong-fallback pattern); (f) contract test asserts `TranscodeAttempts.ProfileName = MediaFiles.AssignedProfile` for every new row. Historical rows NOT backfilled (AssignedProfile may have changed since attempt; label snapshot is the correct semantic). Verification: after fix + fleet redeploy, `SELECT DISTINCT ProfileName FROM TranscodeAttempts WHERE AttemptDate > <post-deploy-ts>` returns only real profile names, never mode strings.

### Group J -- diagnostic capture (added 2026-07-18 after rc=222 blind investigation)

C21. On any non-zero FFmpeg returncode, the tail of FFmpeg stderr (last 4 KB) writes to `TranscodeAttempts.ErrorMessage` AND to a `LoggingService.LogError` with `ClassName='VideoTranscodingService'` / `'QualityTestingBusinessService'` and the full attempt Id. Baseline: 38 non-zero returncodes/48h with zero stderr captured in `Logs` -- every failure a black box (root cause of rc=222 cluster unknown without pulling live ffmpeg re-runs). Fix: `Features/TranscodeJob/VideoTranscodingService.py:~164-172` and `Features/QualityTesting/QualityTestingBusinessService.py:~966-974` -- restructure the `Process.communicate()` block so `ErrorOutput` tail is captured into a variable that is (a) returned to the caller for persistence on the attempt row and (b) logged at ERROR when `returncode != 0`. Complements C13 (which stops logging FFmpeg output on returncode==0). Verification: force one rc=222 attempt post-fix; `SELECT ErrorMessage FROM TranscodeAttempts WHERE Id = <n>` returns the encoder's actual error text.

## Fix Plan

One entry per criterion. KISS: smallest surgical fix that does not break upstream producers or downstream consumers. Investigated 2026-07-17/18.

### C1 -- `ExtractShowInfo` Path constructor missing 'RelativePath'

**File:** `Features/FileScanning/FileScanningBusinessService.py:1038`
**Root cause:** `Path(FileName).stem` -- `Path` at module scope binds to `Core.Path.Path` (line 19 import), which requires `(StorageRoot, RelativePath)`. `pathlib.Path` is aliased as `PyPath` (line 8). Bug is one identifier.
**Fix:** `NameWithoutExt = PyPath(FileName).stem` -- filename-only manipulation, no filesystem access, no shape issues. `PyPath` already imported.
**Ripple:** None. `ExtractShowInfo` returns dict; callers unchanged.

### C2, C3 -- `FileScanningRepository` missing `GetMediaFilesByRootFolder[Id]`

**File:** `Features/FileScanning/FileScanningBusinessService.py:1128, 1162, 1416, 1863, 1971, 2092, 2264` (7 call sites)
**Root cause:** Callers use `self.Repository.GetMediaFilesByRootFolder[Id](...)` but those methods live on `MediaFilesRepository`. `FileScanningBusinessService.__init__` already binds `self.MediaFilesRepository` at line 92.
**Fix:** Replace all 7 `self.Repository.GetMediaFilesByRootFolder` -> `self.MediaFilesRepository.GetMediaFilesByRootFolder` (both suffixes). One-line rename per site.
**Ripple:** None -- method signatures + return shapes identical. `FileScanning.feature.md:230` already documents the two-repository split; no doc change.

### C4 -- `MediaProbeRepository` reads non-existent `RootFolder` column

**Files:** `Features/MediaProbe/MediaProbeRepository.py:66, 105` (get + count) AND `Features/MediaFiles/MediaFilesRepository.py:340` (cascades into C2/C3 fix)
**Root cause:** Schema migration renamed `RootFolders.RootFolder` -> `RootFolders.StorageRootId + RelativePath` typed pair. Three SQLs still read the old column.
**Fix:** Replace `SELECT RootFolder FROM RootFolders WHERE Id = %s` with `SELECT StorageRootId, RelativePath FROM RootFolders WHERE Id = %s`. Downstream `Path.FromLegacyString(RootPath, GetStorageRoots())` becomes direct `Path(StorageRootId=row['StorageRootId'], RelativePath=row['RelativePath'])` -- no legacy string parse required, one hop shorter.
**Ripple:** `MediaFilesRepository.GetMediaFilesByRootFolderId` (line 337-344) also affected -- rewrite to read the typed pair and hand it to `GetMediaFilesByRootFolder`, or reshape `GetMediaFilesByRootFolder` to accept typed args directly. KISS choice: leave `GetMediaFilesByRootFolder(RootFolderPath)` signature intact; construct the canonical string via `Path(...).ToCanonicalString()` inside `GetMediaFilesByRootFolderId`. Zero callers of the outer func change.

### C5 -- `LocalPath op refused canonical drive-letter path on non-Windows`

**File:** `Features/FileScanning/FileScanningRepository.py:NormalizePathToFilesystemCase` (~line 700-754)
**Root cause:** Function is a Windows-only NTFS case-normalization helper (`ntpath.join`, drive-letter parse, `os.listdir` walk to fix case). On Linux workers, called with 'M:\\' / 'T:\\' input; `LocalIsDir` at line 733 triggers `_AssertLocalShape` guard. Line 754 has separate bug: `return Path` returns the imported class instead of the parameter.
**Fix:** Two lines. Guard at top of function: `from Core.Path.LocalPath import _IS_WINDOWS` (or copy the `platform.system() == 'Windows'` check locally); `if not _IS_WINDOWS: return Path` -- Linux filesystems are case-sensitive; input is already canonical; nothing to normalize. Fix line 754 `return Path` -> `return current_path` (or whatever the input parameter is actually named -- read first).
**Ripple:** None. Windows workers keep exact current behavior; Linux workers return identity instead of crashing.

**Domain question resolved 2026-07-18:** Linux workers should never receive drive-letter paths for FS ops -- upstream should have canonicalized. This guard is defense-in-depth; if it fires, log INFO once per worker-startup naming the caller for follow-up, then return identity.

### C6, C7, C8, C9 -- deferred to `mediafiles-uniqueness-owner`

Not fixed in this directive. See scope note above.

### C10 -- Pokémon `-mv` re-admission spam

**Table:** `TranscodeQueue`
**Root cause:** Rows pre-date commit 7e562a9 (2026-07-15) which added the `-mv` exclusion to the admission gate. Existing rows re-hit the refusal every claim cycle.
**Fix:** SQL migration `Scripts/SQLScripts/PurgeStaleMvQueueRows_2026_07_18.py` (idempotent, `DELETE FROM TranscodeQueue WHERE FilePath LIKE '%-mv.mp4%'` with pre-count + post-count log). Pre-flight query first to confirm no in-progress claim (`ProcessingStatus IS NULL OR ProcessingStatus NOT IN ('Claimed', 'InProgress')`).
**Ripple:** Zero -- workers already refuse these rows; deletion just stops the WARN.

### C11 -- `CrashRecoveryService` X -> X spam (skip + downgrade)

**File:** `Features/ServiceControl/CrashRecoveryService.py:_RecoverInProgressArtifacts (~line 400-460)`
**Root cause:** Loop processes `.inprogress` artifacts; for each, calls `FinalizePartialReplacement`. When the artifact has already been replaced on a prior tick, `LocalSource == FinalPath` and the call is a no-op that still logs a WARN.
**Fix (two changes):**
1. Skip: before calling `FinalizePartialReplacement`, check `if LocalSource == FinalPath and LocalExists(FinalPath) and not LocalExists(LocalSource + '.inprogress'): continue`. Nothing to recover -- artifact is already finalized.
2. Downgrade: change `LoggingService.LogWarning` at line 455-458 -> `LoggingService.LogInfo`. Successful recovery is not a warning.

**Ripple:** None. Callers ignore return; log-level change doesn't affect flow.

### C12 -- `FFprobePath was NULL on worker init` (stale-pyc cite)

**Root cause:** Exact warning string does not exist in the current source tree. Container is running stale bytecode per BUG-0085 (`Docker build-cache leaks pre-Reset-9 .pyc into worker containers`). The self-heal path in `ProcessTranscodeQueueService.__init__:73-99` already discovers + persists paths + LogInfo on success; no live code path emits the exact WARN.
**Fix:** Not a code change in e2e-bug-fixes. Verify affected workers: `docker exec <worker> find /opt/mediavortex -name __pycache__ -exec rm -rf {} +; docker compose restart worker-N`. Cite BUG-0085 for durable fix.
**Ripple:** BUG-0085 durable Dockerfile fix is a separate directive.

### C13 -- FFmpeg version banner logged at ERROR

**Files:** `Features/TranscodeJob/VideoTranscodingService.py:168` and `Features/QualityTesting/QualityTestingBusinessService.py:970`
**Root cause:** After `Process.communicate()`, both files call `LoggingService.LogError(f"FFmpeg stdout: {Output}", ...)` if `Output` truthy. FFmpeg's stdout carries the version banner + progress on normal runs; only meaningful when muxing to stdout (which we do not).
**Fix:** Gate on `Process.returncode`. Rewrite the block:
```python
if Process.returncode != 0:
    if Output:
        LoggingService.LogError(f"FFmpeg stdout: {Output}", ...)
    if ErrorOutput:
        LoggingService.LogError(f"FFmpeg stderr: {ErrorOutput}", ...)
```
Two files, same pattern. If return code is 0 and non-empty Output, the caller already succeeded; nothing to log.

**Ripple:** None -- downstream code already checks return code separately. Log volume drops without losing signal.

### C14 -- Jellyfin auto-sync WorkerContext unbound

**File:** `WebService/Main.py:sync_worker` inside `_start_jellyfin_sync` (~line 205-222)
**Root cause:** Thread spawned at 220 doesn't call `WorkerContext.Bind()`. Downstream `RefreshJellyfinData()` -> ... -> `WorkerContext.Current()` at some deep call site raises.
**Fix:** At top of `sync_worker` body, before any other call: `WorkerContext.Bind(WorkerContextForWebService())` or the equivalent WebService pseudo-worker binding pattern. Look at other WebService background threads (`AudioRemeasurementRunner`, `ServiceStatusTracker`) for the canonical bind call.
**Ripple:** None -- adds one line at thread entry.

**Domain question resolved:** WebService already has a pseudo-worker binding pattern for background threads; reuse it here.

### C15 -- SelectPreferredAudioStream noise (silence single-stream, warn multi-no-english)

**File:** grep for `SelectPreferredAudioStream` producer (likely `AudioStateService` or `MediaProbeBusinessService`)
**Root cause:** Every non-English audio stream, single or multi, emits the same WARN. Single-`und` is the common case and shouldn't warn.
**Fix:** Wrap the warning: `if len(streams) > 1: LogWarning(...) else: LogInfo(...)`. One stream = no choice was available; multi-stream + no English = operator may want to investigate.
**Ripple:** None.

### C16 -- PySceneDetect not installed

**File:** `requirements.txt` + Linux worker deploy
**Root cause:** `Features/ContentSignals/ContentSignalsService.py` uses PySceneDetect for scene-change-rate; dep missing on the Linux worker venv.
**Fix:** Add `scenedetect>=0.6.0` to `requirements.txt`. Redeploy Linux workers per `feedback_all_installs_via_requirements_txt.md`.
**Ripple:** None -- new optional dep; behavior on Windows workers (where it's already installed) unchanged.

### C21 -- FFmpeg stderr tail capture on non-zero exit

**Files:** `Features/TranscodeJob/VideoTranscodingService.py:~164-172` and `Features/QualityTesting/QualityTestingBusinessService.py:~966-974`
**Root cause:** `Process.communicate()` returns `(Output, ErrorOutput)`; current code only conditionally LogErrors them (see C13). Neither branch persists `ErrorOutput` to `TranscodeAttempts.ErrorMessage` -- the row gets a synthetic `f"Transcode failed: Transcoding failed with return code {rc}"` string with zero encoder detail. 38 failures/48h, all unlabeled.
**Fix:** In both files, on returncode != 0:
```python
if Process.returncode != 0:
    StderrTail = (ErrorOutput or b'').decode('utf-8', errors='replace')[-4096:]
    LoggingService.LogError(f"FFmpeg stderr (tail): {StderrTail}", ClassName, MethodName)
    # return / raise with StderrTail attached so caller writes it to TranscodeAttempts.ErrorMessage
```
Caller update: `ProcessTranscodeQueueService.HandleTranscodingResult` (or wherever the "Transcode failed: ..." string is composed) appends the tail: `ErrorMessage = f"rc={rc}: {StderrTail}"`.
**Ripple:** `TranscodeAttempts.ErrorMessage` is `TEXT` — no schema change. Downstream consumers (dispatcher, Activity dashboard) already TREAT ErrorMessage as free-form text. Slight column-size growth is bounded (4 KB max).

### C17 -- SchemaChecker snapshot missing

**Files:** `Scripts/Migration/GenerateSchemaSnapshot.py` (source) + `.claude/schema/snapshot.json` (artifact) + `deploy/Dockerfile` (Linux worker container image)
**Root cause:** Snapshot artifact not present at `/opt/mediavortex/.claude/schema/snapshot.json` in the Linux worker container. Either not copied by `deploy/Dockerfile`, or the file is git-ignored and never generated on the build host.
**Fix (investigate first, then choose):**
- If snapshot IS in git: check `deploy/Dockerfile` `COPY` step covers `.claude/schema/` prefix. Likely one glob change.
- If snapshot is NOT in git: run `py Scripts/Migration/GenerateSchemaSnapshot.py` at deploy time as a prebuild step in `deploy/deploy-linux-worker.py`; add snapshot regeneration to the deploy pipeline. Prefer this: snapshot then reflects the actual schema at deploy, not a stale checked-in copy.
**Note:** Presence of this snapshot would have caught C4 pre-deploy. Fix C17 has compounding value.
**Ripple:** None on the Windows path.

## Seams

_Enumerated at NEEDS_STANDARDS_REVIEW per `.claude/rules/seam-verification.md`. Cross-stage seams already covered by `transcode.flow.md ## Seams` are referenced by ID; only new or changed seams get restated here._

## Scope

**IN:** bugs and failure modes discovered while triaging the end-to-end pipeline. Production-code fixes, contract tests for regressions, schema migrations required to unblock a specific stuck path, sweeper / stuck-detect regressions, previously-silent data-integrity self-heal.

**OUT:** architectural refactor, feature additions, DDD/SOLID polish beyond what a specific bug fix requires, doc-hub restructuring, new verticals, performance work absent an outright failure.

If a bug fix reshapes a small piece of nearby code, that is in scope. "While I'm here" adjacent cleanup is not.

## Files

_Populated as bugs are triaged and fixes land._

## Bugs Fixed

| # | Discovered | Symptom | Root cause | Fix commit |
|---|-----------|---------|-----------|-----------|

## Bugs Deferred

| BUG-NNNN | Symptom | Reason deferred |
|---------|--------|----------------|

## Status

**Phase:** IMPLEMENTING
**Owner:** claude-opus-4-7
**Opened:** 2026-07-17
**Stack position:** top (interrupts audio-vertical-dialog-boost-enforcement)

### Progress

- [ ] NEEDS_STANDARDS_REVIEW: read `.claude/rules/*.md` + `.claude/standards/index.md`; run call-graph-audit five signals against affected paths (path plumbing / replacement / crash recovery / logger paths)
- [ ] NEEDS_PLAN: `## Files` populated per criterion; `## Seams` populated per `seam-verification.md`
- [ ] NEEDS_PLAN: priority order committed (Group A path plumbing first -- other groups mask on top of it)
- [ ] NEEDS_DOC_PREREAD: read every colocated `*.feature.md` / `*.flow.md` ancestor of files in `## Files`
- [ ] IMPLEMENTING C1..C5 (Group A path plumbing)
- [ ] IMPLEMENTING C6..C10 (Group B replacement / uniqueness)
- [ ] IMPLEMENTING C11 (Group C crash-recovery no-op storm)
- [ ] IMPLEMENTING C12 (Group D worker config discovery self-persist)
- [ ] IMPLEMENTING C13 (Group E logger level fix)
- [ ] IMPLEMENTING C14 (Group F WorkerContext bind on jellyfin auto-sync thread)
- [ ] IMPLEMENTING C15 (Group G audio classification noise)
- [ ] IMPLEMENTING C16..C17 (Group H deploy artifacts)
- [ ] VERIFYING: 60-min post-fix soak on I9 + one Linux worker; C20 top-20 query clean
- [ ] VERIFYING: sweep `memory/KNOWN-ISSUES.md` per C19
- [ ] DELIVERING: `### Promotions` populated (durable lessons -> per-vertical feature/flow docs or KNOWN-ISSUES rewrites); close report; stack pop
