# Compliance-Gated Rename

**Slug:** compliance-gated-rename

## Interrupts: pipeline-test-harness

## What It Does

Stops new `-mv-mv.mp4` (and `-mv-mv-mv.mp4`, etc.) artifacts from being created by gating the `.inprogress` -> `-mv.<ext>` rename on the same compliance predicate the queue cascade uses to decide whether a file needs work.

Today the rename fires when (a) FFmpeg returned 0 and (b) the output FFprobes as a valid container (`worker-lifecycle.feature.md` criterion 7). Neither check answers "would this output still be picked up by the cascade?" -- so a `-mv.mp4` can land for a file whose audio is still wrong, savings are still marginal, container is still non-acceptable. The next scan re-discovers the `-mv.mp4`, the cascade re-queues it, and the next encode produces `-mv-mv.mp4`. Repeat until something breaks.

After this slice, the rename consults `Features/TranscodeQueue/QueueManagementBusinessService._EvaluateCompliance` -- the same function the cascade calls -- against a candidate `MediaFile`-shaped row synthesized from an FFprobe pass on the `.inprogress` plus source-row carry-forward for fields the probe cannot derive. If the gate refuses, the disposition becomes `NoReplace` with `DispositionReason='ComplianceGateFailed'` and the `.inprogress` is deleted by the same `_ProcessCompleteFileReplacement` path that handles the other refuse-and-return branches. No `-mv.mp4` lands, so no `-mv-mv.mp4` can ever follow.

This is the standalone "stop the bleeding" slice. End-to-end worker process ownership of `.inprogress` / TFP / post-replacement state (BUG-0020 criteria 1-3), and the BUG-0018 sweep re-enable, are deferred to follow-up work tracked under their original bug IDs and under `worker-lifecycle.feature.md` criteria 22-23, 26.

## Scope

```
Features/FileReplacement/FileReplacementBusinessService.py
Features/QualityTesting/PostTranscodeDispositionService.py
Features/TranscodeQueue/QueueManagementBusinessService.py    (EvaluateCandidateCompliance wrapper + _RefusalReason)
Models/CommandBuilder.py                                     (criterion 7: -mv suffix collapse)
Features/FileReplacement/FileReplacement.feature.md          (criterion 13 -- canonical home)
WorkerService/worker-lifecycle.feature.md                    (criteria 24, 25 -- canonical home)
transcode.flow.md                                            (Stage 6 disposition table update)
```

Explicitly OUT OF SCOPE for this feature: worker ownership of `.inprogress` lifecycle (worker-lifecycle 22), worker ownership of post-replacement state (worker-lifecycle 23), `OrphanCleanupService._SweepTemporaryFilePaths` re-enable (worker-lifecycle 26 / BUG-0018), existing-orphan disk cleanup (BUG-0015 mop-up scripts stay as-is).

## Success Criteria

1. `FileReplacementBusinessService._ProcessCompleteFileReplacement` consults `QueueManagementBusinessService._EvaluateCompliance` before the `.inprogress` -> final-name rename. The candidate row passed to the evaluator is synthesized from: (a) an FFprobe pass on the `.inprogress` populating `Resolution`, `ResolutionCategory`, `Codec`, `Container`/`ContainerFormat`, `AudioCodec`, `VideoBitrateKbps`, `AudioBitrateKbps`, `DurationMinutes`, `FrameRate`, `SizeMB`; (b) source-row carry-forward via DB lookup on `MediaFiles.Id` for fields the probe cannot derive: `HasExplicitEnglishAudio`, `AudioLanguages`, `SourceIntegratedLufs`, `SourceLoudnessRangeLU`, `SourceTruePeakDbtp`, `SourceIntegratedThresholdLufs`, `LoudnessMeasurementFailureReason`, `AudioComplete`, `AssignedProfile`. The rename only fires when `(IsCompliant, RecommendedMode) == (True, None)`. Verifiable: queue a file whose source has unnormalized audio AND a profile whose emitted FFmpeg command omits the loudnorm chain -- the encode completes, the rename refuses, no `-mv.mp4` lands on disk.

2. When the compliance gate refuses, the disposition committed via `PostTranscodeDispositionService._CommitDisposition` is `Disposition='NoReplace'` with `DispositionReason='ComplianceGateFailed'`. The free-text audit payload (`TranscodeAttempts.ErrorMessage` or the equivalent column already used for disposition context -- pick whatever the existing audit pattern uses, do not add a new column) names the specific cascade reason from the `_EvaluateCompliance` output (e.g. `audio_not_normalized`, `container_not_acceptable`, `video_codec_not_acceptable`, `marginal_savings`, `loudness_measurement_failed`, `awaiting_loudness_measurement`). Verifiable by SQL: `SELECT DISTINCT DispositionReason FROM TranscodeAttempts WHERE Disposition='NoReplace' AND DispositionReason='ComplianceGateFailed'` returns rows after a canary that produces a non-compliant output; the audit-payload column for those rows contains a cascade-vocabulary reason, not free text.

3. The `.inprogress` is deleted by `_ProcessCompleteFileReplacement` when the gate refuses, using the same idempotent delete path the other refuse-and-return branches use. The original source file is untouched. The `TemporaryFilePaths` row for the attempt is cleaned via the same disposition-driven path that already handles `Discard`/`NoReplace`/`Requeue` (per `PostTranscodeDispositionService._CommitDisposition`, transcode.flow.md Stage 6) -- this slice does not introduce a new TFP cleanup path. Verifiable: after a gate-refused encode, `os.path.exists(<.inprogress>)` is False, the source file's MD5 is unchanged, and `SELECT COUNT(*) FROM TemporaryFilePaths WHERE TranscodeAttemptId=<id>` is 0.

4. The source-row carry-forward read is keyed on `TemporaryFilePaths.SourceStorageRootId + SourceRelativePath` (matching the BUG-0014 path-storage fix in commit e0244d3), not on legacy text-path lookup. If the source row cannot be located (deleted between encode start and rename time, edge case), the rename refuses with `Disposition='NoReplace'`, `DispositionReason='ComplianceGateFailed'`, audit payload `source_row_missing`. The encode is not promoted on missing-source evidence. Verifiable: delete a MediaFiles row mid-encode (test harness), confirm the rename refuses with the named audit payload.

5. **`-mv-mv` regression gate.** After this slice ships, a 24-hour live-load probe across the fleet produces zero new `-mv-mv.<ext>` artifacts. Verifiable: `SELECT FilePath, LastScannedDate FROM MediaFiles WHERE FilePath LIKE '%-mv-mv%' AND LastScannedDate > '<feature-deploy-timestamp>'` returns zero rows. Existing `-mv-mv` artifacts on disk (pre-deploy) are out of scope -- BUG-0016 / `CleanupOrphanMvPairs.py` already park / retire those.

6. `transcode.flow.md` Stage 6 disposition table gains the `ComplianceGateFailed` reason; Stage 8 Phase 7 description names the rename as compliance-gated (not FFprobe-gated). `worker-lifecycle.feature.md` criterion 24 (compliance-gated rename) and criterion 25 (NoReplace disposition on gate refusal) are marked IMPLEMENTED with the date this feature ships. `FileReplacement.feature.md` criterion 13 is marked IMPLEMENTED with the same date.

7. **`-mv` suffix collapse.** Re-transcoding a `<name>-mv.<ext>` source produces `<name>-mv.<output-ext>` (replacing the source in-place), never `<name>-mv-mv.<output-ext>`. The output-filename construction in `Models/CommandBuilder` strips a trailing `-mv` from the source basename before appending the `-mv.<output-ext>.inprogress` suffix; `FileReplacementBusinessService._ProcessCompleteFileReplacement` detects the resulting same-slot collision (TargetPath == LocalOriginalPath) and performs a backup-rename-publish dance (rename source -> `<source>.replacing.bak`, rename `.inprogress` -> target, delete backup) so the file is recoverable from any single-step crash. Verifiable end-to-end: queue any `<name>-mv.mp4` file for Quick Fix or Transcode; after the cycle, `<name>-mv.mp4` exists with new content, no `<name>-mv-mv.<ext>` is on disk, and no `.replacing.bak` artifact remains.

## Status

IMPLEMENTED 2026-05-27 -- pending canary + 24h live-load verification.

### Progress

- [x] Tracker criteria added to sibling feature docs (worker-lifecycle 24-25, FileReplacement 13) -- 2026-05-26
- [x] Feature doc drafted at original umbrella scope -- 2026-05-26
- [x] Rescoped to Slice 1 only ("stop the bleeding" / no new `-mv-mv`) -- 2026-05-27
- [x] Criteria approved -- 2026-05-27
- [x] Candidate-row synthesizer: `FileReplacementBusinessService._RunComplianceGate` probes the `.inprogress` via `FileManager.ExtractMediaMetadata`, looks up the source MediaFile by `(StorageRootId, RelativePath)`, synthesizes the candidate row (probe fields + source carry-forward), and calls `QueueManagementBusinessService.EvaluateCandidateCompliance`. Includes the `AudioComplete=True` override when the FFmpeg command contains loudnorm (`AudioCompletionService.DetectNormalizationInCommand`) to avoid the false-negative on first-pass-normalize encodes.
- [x] Compliance-gate wired into `_ProcessCompleteFileReplacement` between the target-exists check and the `os.rename`. Refuse path: deletes `.inprogress`, returns `Success=False, ErrorMessage='ComplianceGateFailed: <cascade_reason>', ComplianceGateRefused=True, CascadeReason=<reason>`. Source untouched. Gate fails closed on any internal error.
- [x] `EvaluateCandidateCompliance` public wrapper added to `QueueManagementBusinessService`; internal `_EvaluateCompliance` records `_RefusalReason` on every refuse branch so the wrapper can surface stable cascade-reason strings (`video_codec_not_acceptable`, `container_not_acceptable`, `audio_codec_not_acceptable`, `audio_not_normalized`, `awaiting_loudness_measurement`, `loudness_measurement_failed`, `no_english_audio`, `audio_corrupt_suspect`, `no_audio_stream`, `savings_exceeds_threshold`, `high_bpp_excessive`).
- [x] `ComplianceFailureRecorder.Record` flips a previously-committed `Replace` disposition to `Reject`/`ComplianceGateFailed` and writes the cascade reason to `TranscodeAttempts.ErrorMessage`. TFP cleanup runs automatically via `AttemptCleanupService.Cleanup` (RetainInprogressPolicy: ComplianceGateFailed does not retain, so `.inprogress` is deleted).
- [x] `ProcessFileReplacement` looks up source `MediaFileId` via TFP `(SourceStorageRootId, SourceRelativePath)` -> MediaFiles row, passes it down, and on gate-refused result calls `RecordComplianceGateFailure`.
- [x] `'ComplianceGateFailed'` added to `REASONS` vocabulary.
- [x] **Criterion 7 (`-mv` suffix collapse):** `OutputFilenameBuilder.CollapseMvSuffix` helper added; applied at all output-filename construction sites (`GenerateOutputFileName` for Reencode plans; StreamCopy plans emit `.inprogress` output via `CommandComposer._ResolveOutputPath`). `_ProcessCompleteFileReplacement` detects `TargetPath == LocalOriginalPath` and performs `<source>.replacing.bak` rename dance with rollback on intermediate failure. Verified end-to-end via isolated filesystem test: `foo-mv.mp4` re-transcode produces `foo-mv.mp4` with new content; no `foo-mv-mv.mp4` or `.replacing.bak` left behind.
- [x] Smoke tested: all cascade reasons surface correctly via wrapper; loudnorm-override path verified; suffix-collapse helper and same-slot rename dance verified; pre-existing contract tests pass (1 unrelated drift on NoSavings vs QualityTestNotRequired order is pre-existing per 2026-05-13 comment in code).
- [x] DB-evidence verification 2026-06-01 (criteria 1, 2, 3): 3 post-deploy gate refusals (TranscodeAttempts Id 26674, 26685, 26697) -- `Disposition='NoReplace'`, `DispositionReason='ComplianceGateFailed'`, `ErrorMessage='ComplianceGateFailed: downscale_needed'`, all sources `1080p-mv.mp4` against the 720p NVENC profile. TFP orphan count for these 3 attempts: 0. Criterion 7 single-`-mv` arm: 10/10 most-recent `-mv.mp4` transcodes post-deploy (30 Rock, Malcolm in the Middle, Impractical Jokers, etc.) produced `-mv.mp4` outputs, zero stacking.
- [x] Multi-depth `-mv` collapse (2026-06-01): `_CollapseMvSuffix` upgraded from strip-one to greedy strip-all after DB audit showed 3 post-deploy `-mv-mv.mp4` artifacts produced by re-transcoding pre-existing `-mv-mv.mp4` sources (Evil S02E04, Love Death Robots S01E07, Westworld S02E01). Direct-call suite: 10/10 PASS including triple-depth `-mv-mv-mv` and case-insensitive. Live-load arm pending next deploy. Directive: `mv-suffix-greedy-collapse`.
- [ ] Doc updates: transcode.flow.md Stage 6 table + Phase 7 description. Mark sibling-doc criteria IMPLEMENTED.
- [ ] 24-hour live-load probe to satisfy criterion 5 -- recheck `SELECT COUNT(*) FROM MediaFiles WHERE FilePath LIKE '%-mv-mv%' AND LastModifiedDate > '<post-greedy-collapse-deploy-ts>'` returns 0 (file-creation timestamp, not LastScannedDate which catches rescans of pre-existing artifacts).
- [ ] Canary on a known-compliant source to confirm no false-negative regression (compliant encodes still rename successfully).
- [ ] Canary on a `<name>-mv.mp4` source to confirm criterion 7 in live conditions (output stays at `<name>-mv.mp4`, no stacking).
- [ ] Doc updates: transcode.flow.md Stage 6 table + Phase 7 description. Mark sibling-doc criteria IMPLEMENTED.
- [ ] 24-hour live-load probe to satisfy criterion 5.

## Files

| File | Role |
|------|------|
| Features/FileReplacement/FileReplacementBusinessService.py | Hosts `_ProcessCompleteFileReplacement`; the compliance-gate call lands here before the existing rename branch (criterion 1). Hosts the candidate-row synthesizer (criterion 1, helper or method). |
| Features/QualityTesting/PostTranscodeDispositionService.py | `_CommitDisposition` maps the gate-refused return to `Disposition='NoReplace'`, `DispositionReason='ComplianceGateFailed'` (criterion 2). |
| Features/TranscodeQueue/QueueManagementBusinessService.py | Hosts `_EvaluateCompliance`; called as predicate -- not modified by this feature. |
| Features/FileReplacement/FileReplacement.feature.md | Canonical home for criterion 13 (compliance-gated rename invariant). Marked IMPLEMENTED on ship (criterion 6). |
| WorkerService/worker-lifecycle.feature.md | Canonical home for criteria 24, 25 (compliance gate + NoReplace disposition). Marked IMPLEMENTED on ship (criterion 6). |
| transcode.flow.md | Stage 6 disposition table + Phase 7 description updated (criterion 6). |
