# Probe

**Slug:** probe

## What It Does

Runs ffprobe against MediaFiles rows whose metadata is missing or stale. Writes probe metadata columns (Resolution, Codec, VideoBitrateKbps, AudioCodec, ContainerFormat, ...) + loudness columns. Triggers cascade recompute of compliance derived state.

Runs as a dedicated capability worker (`WorkerService/ProbeWorker.py`) with fleet-wide poll -- not RootFolder-scoped. Pipeline stage `ST4` + `ST5` (classifier hook) in `ingest.flow.md`.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | Reprobe a single file | curl / /Failures Retry button | `POST /api/MediaProbe/Probe/<MediaFileId>` | `Features/MediaProbe/MediaProbeController.ProbeFile` |
| W2 | Queue reprobe for many files (schema-change backfill) | operator script | `Scripts/MarkNeedsReprobe.py <criteria>` | writes `MediaFiles.NeedsReprobe = TRUE` for matching rows |
| W3 | View probe statistics | admin | `GET /api/MediaProbe/Statistics` | existing |
| W4 | View failed-probe files | `/Failures` page | `GET /api/Failures` | `Features/Failures/failures.feature.md` |
| W5 | Reset failure count for one file | `/Failures` Retry button | `POST /api/Failures/<id>/Retry` | `Features/Failures/failures.feature.md` |

## Success Criteria

C1. **`ProbeWorker` runs as a capability worker on any worker where `Workers.ProbeEnabled = TRUE`.** Shape mirrors `LanguageWorker`. Loop with configurable poll interval. Contract: `TestProbeWorkerContract.py` asserts capability-gated claim.

C2. **Probe claim: `Resolution IS NULL OR NeedsReprobe = TRUE`, fleet-wide.** No RootFolder scoping. `AND FFprobeFailureCount < MaxFFprobeFailures` gates retries. `AND StorageRootId IS NOT NULL AND RelativePath IS NOT NULL` skips broken rows. Contract test.

C3. **Successful probe writes 12+ metadata columns.** `Resolution, Codec, AudioCodec, VideoBitrateKbps, ResolutionCategory, IsInterlaced, ContainerFormat, AudioLanguages, HasExplicitEnglishAudio, HasForcedSubtitles, SubtitleFormats, DurationMinutes` + chained loudness (`SourceIntegratedLufs, SourceLoudnessRangeLU, SourceTruePeakDbtp, LoudnessMeasuredAt`) via `LoudnessAnalysisService.MeasureAndPersist`. Also clears `NeedsReprobe` and updates `LastProbedFileSize, LastProbedFileMtime`. Contract test.

C4. **Failed probe increments `FFprobeFailureCount`, writes `LastFFprobeError` + `LastFFprobeAttemptDate`.** The 12+ metadata columns are NOT overwritten with NULL on failure (preserve last-known-good). Contract test.

C5. **Cascade before return (writer-owns-cascade).** After probe writes metadata, `ProbeWorker` calls `QueueManagementBusinessService().RecomputeForFiles([Id])` before releasing the claim. Cascade covers Video/Audio/Container compliance + WorkBucket derivation. Contract: `TestProbeCascade.py`.

C6. **Classifier runs after probe write.** `_ExecuteProbe` post-flight invokes `ContentClassifierService.ClassifyAndAssign(Id)` (sticky-guarded). This satisfies pipeline ordering (classifier BEFORE compliance final state) so first-pass compliance sees populated `AssignedProfile`. Contract test.

C7. **`FFprobeFailureCount >= MaxFFprobeFailures` skips claim.** Row is not re-claimed until `NeedsReprobe = TRUE` OR `ResetFailures` runs. Visible on `/Failures`. `MaxFFprobeFailures` in SystemSettings (default 3).

C8. **`ResetFailures(Id)` sets `FFprobeFailureCount = 0` + clears `LastFFprobeError` + sets `NeedsReprobe = TRUE`.** Row picked up next ProbeWorker tick. Contract test.

C9. **FileReplacement re-probe path preserved.** After transcoded output is renamed in place, `Features/FileReplacement/FileReplacementBusinessService._UpdateMediaFilesAfterReplacement` invokes `ProbeFile(Id, Force=True)`. Cascade fires. Contract test.

C10. **`LanguageEnrichmentService.ProbeFile(Force=True)` path unchanged.** Cascade only fires on ProbeWorker's own write path; other probe callers preserve existing semantics (they call their own downstream). Contract test.

C11. **Probe never walks directories.** Grep production probe code paths for `scandir(` / `os.walk(`: zero hits. Contract test.

C12. **`MediaProbeBusinessService.ProbeFile / .ProbeFilesNeedingMetadata` still callable.** No caller breakage. `ProbeWorker` uses `ProbeFile(MediaFileId, Force=False)` internally.

## Seams

Intra-feature. Cross-stage in `ingest.flow.md`.

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | ProbeWorker -> BusinessService | poll loop | `ProbeFile(Id)` returns `{Success, Message}` | worker handles success (release claim) vs failure (increment count) | contract test |
| S2 | BusinessService -> `_ExecuteProbe` | after claim | ffprobe subprocess invocation via `Worker.FFprobePath` | parses JSON output, writes columns | existing |
| S3 | `_ExecuteProbe` -> LoudnessAnalysis | chained per `media-tabs-and-loudness.feature.md` | invokes `LoudnessAnalysisService.MeasureAndPersist(MediaFileId)` | writes 4 loudness columns | existing |
| S4 | `_ExecuteProbe` -> Classifier | post-flight | invokes `ContentClassifierService.ClassifyAndAssign(Id)` | writes AssignedProfile if NULL | existing (preserved from content-classifier.flow.md ST1-ST7) |
| S5 | ProbeWorker -> cascade | after write | `QueueManagementBusinessService.RecomputeForFiles([Id])` | recomputes Video/Audio/Container compliance | contract test |
| S6 | ProbeWorker -> ActiveJobs | claim + release | INSERT `ActiveJobs(JobType='Probe', WorkerName, ...)`; DELETE on release | DrainWorker sees load | existing pattern (per capability-drain-truthfulness) |

## What this feature does NOT own

- Scan / disk walk: `Features/FileScanning/scan.feature.md`
- Classifier rule table + rule matching: `Features/ContentClassifier/classifier.feature.md`
- Compliance rules + evaluation: `Features/VideoEncoding/video-encoding.feature.md`, `Features/AudioNormalization/audio-normalization.feature.md`, `Features/ContainerFormat/container-format.feature.md`
- WorkBucket derivation: `Features/WorkBucket/work-bucket.flow.md`
- /Failures page: `Features/Failures/failures.feature.md`

## Status

DRAFTED under directive `ingest-pipeline-kiss`. `ProbeWorker` code already exists from prior `probe-worker-decoupled` scope; cascade verification + failure surface hookup land in IMPLEMENTING.
