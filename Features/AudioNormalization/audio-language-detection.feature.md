# Audio Language Detection

**Slug:** audio-language-detection

## What It Does

Standalone per-worker background service. Detects audio-language of MediaFiles whose `AudioLanguages` is NULL or `und`. When Whisper reports English at or above the operator threshold, stamps the container's language tag via `ffmpeg -c copy` and refreshes `MediaFiles.AudioLanguages` via re-probe. Isolated from AudioVertical / compliance / transcode queue / audio-fix pipeline. Fleet-wide, opt-in per worker.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|----|-------------|-----------------|---------|----------------------|
| W1 | Turn Language detection on for a worker | `/Admin/Workers` tile capability toggle "Language" | POST `/api/TeamStatus/Workers/<name>/Capability` | `TeamStatusController.SetWorkerCapability` |
| W2 | Watch active detections | `/Activity` "Active Language Detections" card | GET `/api/Activity/Snapshot` | `DashboardSnapshotService._BuildActiveLanguageJobs` |
| W3 | Retry a file (operator-triggered) | SQL only for now | `DELETE FROM MediaFileLanguageDetections WHERE MediaFileId = <id>` | `MediaFileLanguageDetectionsRepository.ClearForMediaFile` |

## Success Criteria

C1. Backend selection is thread-safe. `LanguageEnrichmentService` constructed on any thread returns a non-stub Backend whenever faster-whisper is installed + ffmpeg is resolvable. Verifiable: `Tests/Contract/TestBackendSelectionThreadSafe.py` -- 2 tests (bound + unbound thread).

C2. Single backend across fleet. Only `FasterWhisperBackend` is registered. `WhisperFfmpegBackend` does not exist in the tree. Verifiable: `Tests/Contract/TestNoWhisperFfmpegBackend.py` -- 3 tests (file absent, no production references, import raises).

C3. One shot per file. Worker query is `WHERE NOT EXISTS (SELECT 1 FROM MediaFileLanguageDetections d WHERE d.MediaFileId = mf.Id) AND <capability gate>`. Files with any detection row are never re-processed automatically. Verifiable: `Tests/Contract/TestLanguageWorkerOneShot.py`.

C4. Stamp-on-English. Detected language in {en, eng} AND confidence >= `SystemSettings.MinDetectionConfidence` (default 0.85) triggers `ffmpeg -c copy -metadata:s:a:N language=eng`, atomic `os.replace`, `MediaProbeBusinessService.ProbeFile(Force=True)`. Below threshold OR non-English: detection row still written, file untouched. Verifiable: `Tests/Contract/TestLanguageWorkerStamp.py` -- 3 branches.

C5. Isolation. Language-detection production python imports zero of AudioVertical / AudioPolicyAdmissionGate / _SpawnAudioBackfill / QueueManagementBusinessService / WorkBucket / AudioComplianceRules*. Verifiable: `Tests/Contract/TestLanguageDetectionIsolation.py`.

C6. ActiveJobs lifecycle. Every `_ProcessOne` inserts (`ServiceName='LanguageService'`, `JobType='Language'`, `QueueId=MediaFileId`, `Phase='Setup'`) and deletes in `finally` (success + failure paths). Verifiable: `Tests/Contract/TestLanguageWorkerActiveJobs.py`.

C7. Activity UI. `/Activity` renders "Active Language Detections" (File / Worker / Elapsed) when `Data.ActiveLanguageJobs` non-empty; hides the whole table otherwise. `/api/Activity/Snapshot` returns the list.

C8. `Workers.LanguageEnabled` defaults FALSE. Migration is idempotent. `Tests/Contract/TestLanguageEnabledDefault.py`.

C10. Activity page 10-min success rate. `_BuildLanguageSummary` returns `Successful10m`, `NoAudioDeleted10m`, `OtherErrors10m`, `Attempts10m`, `SuccessPct10m` (Successful / Attempts * 100, 0 when Attempts=0). `/Activity` "Active Language Detections" card renders `<successful>/<attempts> successful (<pct>%)` with a per-outcome breakdown line. Live-verified 2026-07-30 -- API `/api/Activity/Snapshot` returned `SuccessPct10m=87.5` (7/8) post WebService restart.

C9. Progress invariant on `no_audio_streams`. When `EnrichAndStamp` raises `LanguageEnrichmentError('no_audio_streams')`, `LanguageWorker._ProcessOne` routes the MediaFileId to `NoAudioResolver.Resolve` which (a) issues Sonarr `EpisodeSearch` (`media_tv` root) or Radarr `MoviesSearch` (`movies` root) via `SystemSettings.SonarrUrl/SonarrApiKey/RadarrUrl/RadarrApiKey`, deleting the matching episodefile/moviefile first; (b) `os.remove` on the local file; (c) `MediaFilesRepository.DeleteMediaFile(MediaFileId)` -- schema `TranscodeAttempts.MediaFileId` + `TranscodeFiles.MediaFileId` are NULLABLE with `ON DELETE SET NULL`, so attempt history survives with NULL parent; the `MediaFiles` row is removed. Files that raised `no_audio_streams` never re-appear in `_FetchBatch`. Verifiable: `Tests/Contract/TestNoAudioResolver.py` (routing + ordering + env fail-loud) + `Tests/Contract/TestLanguageWorkerProgressInvariant.py` (routing at worker layer).

## Domain Decisions

Recorded in `.claude/directives/closed/2026-07-27-audio-language-detection.md` and DOMAIN.md 2026-07-27 architectural-principles entry.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | LanguageWorker -> LanguageEnrichmentService | `LanguageWorker._ProcessOne` | `(MediaFileId, LocalFilePath)` | `EnrichAndStamp` runs detect+stamp | contract tests C3 C4 |
| S2 | LanguageEnrichmentService -> repository | `Enrich` per stream | `(MediaFileId, StreamIndex, Language, Confidence, BackendName)` | `MediaFileLanguageDetectionsRepository.Insert` | manual invoke verified live |
| S3 | LanguageWorker -> ActiveJobs | `_CreateActiveJob` | `INSERT ... Phase='Setup'` | Row visible in `_BuildActiveLanguageJobs` | contract test C6 + activejobs_phase_enum |
| S4 | Snapshot -> template | `_BuildActiveLanguageJobs` list | `[{MediaFileId, FileName, WorkerName, ElapsedSec, StartedAt}, ...]` | `Templates/Activity.html RenderActiveLanguageJobs` | live-verified on `/Activity` |
| S5 | Fleet capability toggle | `Workers.LanguageEnabled` column | boolean | `BuildClaimPredicate('LanguageEnabled')` gates every LanguageWorker claim; capability-poll starts/stops loop | contract test C1; live-verified capability-poll fix at 40d15d37 |
| S6 | LanguageWorker -> NoAudioResolver | `_ProcessOne` catches Reason='no_audio_streams' | `Resolve(MediaFileId: int, LocalFilePath: str)` | Sonarr/Radarr regrab + disk remove + `DeleteMediaFile` (FK SET NULL preserves attempts); MediaFile no longer re-selected | contract test C9 (TestNoAudioResolver + TestLanguageWorkerProgressInvariant) |
| S7 | NoAudioResolver -> Sonarr/Radarr HTTP | `_Regrab` per StorageRoots.name | `DELETE /api/v3/episodefile\|moviefile/<id>` + `POST /api/v3/command` | HTTP 200/201/202 = success | contract test C9 (mocked); live-verified 2026-07-30 via Logs `NoAudioResolver: ... regrab=sonarr-ok:epFileId=...` |

## Cross-Vertical Contract

- Reads: `MediaFiles.AudioLanguages`, `MediaFiles.StorageRootId`, `MediaFiles.RelativePath`, `Workers.LanguageEnabled`, `SystemSettings.MinDetectionConfidence`.
- Writes: `MediaFileLanguageDetections.*` (owning), `ActiveJobs` rows (`ServiceName='LanguageService'`), `MediaFiles.AudioLanguages` via `MediaProbeBusinessService.ProbeFile` (indirect, re-probe path), container file bytes (single ffmpeg `-c copy` pass).
- Does NOT touch: `AudioVertical`, `AudioComplianceRules`, `AudioPolicyAdmissionGate`, `_SpawnAudioBackfill`, `QueueManagementBusinessService`, `WorkBucket`, `TranscodeQueue`, `TranscodeAttempts`.

## Status

COMPLETE 2026-07-27. Live-verified fleet-wide.

### Progress

- [x] Contract tests written (all failing at start)
- [x] Migration: `MediaFileLanguageDetections` + `Workers.LanguageEnabled` + `SystemSettings.MinDetectionConfidence`
- [x] `FasterWhisperBackend` + `MediaFileLanguageDetectionsRepository` + `LanguageEnrichmentError`
- [x] `LanguageEnrichmentService.EnrichAndStamp` with lazy backend init
- [x] `WorkerService/LanguageWorker.py` + `WorkerService/Main.py` wire-in
- [x] `DashboardSnapshotService` + `ActivityController` + `Templates/Activity.html`
- [x] `WorkerCapabilityPredicate` + `TeamStatusRepository` + `TeamStatusController` + `AdminWorkersRepository` + `Templates/AdminWorkers.html`
- [x] `requirements.txt` faster-whisper
- [x] Contract tests 18/18 green
- [x] I9 smoke (3 branches C4 live-verified)
- [x] Larry-worker-1 canary
- [x] Fleet-wide activation (10 workers)

## Scope

```
Features/AudioNormalization/Services/FasterWhisperBackend.py
Features/AudioNormalization/Services/LanguageEnrichmentService.py
Features/AudioNormalization/Services/LanguageEnrichmentError.py
Features/AudioNormalization/Repositories/MediaFileLanguageDetectionsRepository.py
Features/AudioNormalization/audio-language-detection.feature.md
WorkerService/LanguageWorker.py
WorkerService/Main.py (edit: capability wire)
Features/Activity/Models/DashboardSnapshot.py (edit)
Features/Activity/Services/DashboardSnapshotService.py (edit)
Features/Activity/ActivityController.py (edit)
Templates/Activity.html (edit)
Core/Database/WorkerCapabilityPredicate.py (edit)
Core/WorkerContext.py (edit: TryCurrentOrTemplate)
Features/TeamStatus/TeamStatusRepository.py (edit)
Features/TeamStatus/TeamStatusController.py (edit)
Features/Admin/Workers/AdminWorkersRepository.py (edit)
Templates/AdminWorkers.html (edit)
Features/AudioNormalization/AudioFilterEmitter.py (edit: migrate JSONB -> repo)
Features/AudioNormalization/Services/AudioOperatorReviewService.py (edit: migrate)
requirements.txt (edit)
Scripts/SQLScripts/AddLanguageDetectionSchema_2026_07_27.py
Tests/Contract/TestBackendSelectionThreadSafe.py
Tests/Contract/TestFasterWhisperBackend.py
Tests/Contract/TestLanguageWorkerOneShot.py
Tests/Contract/TestLanguageWorkerStamp.py
Tests/Contract/TestLanguageDetectionIsolation.py
Tests/Contract/TestLanguageWorkerActiveJobs.py
Tests/Contract/TestLanguageEnabledDefault.py
Tests/Contract/TestNoWhisperFfmpegBackend.py
```

## Files

Same as ## Scope above.

## Follow-ups (out of scope for this directive)

- `MediaProbeRepository.SELECT RootFolder FROM RootFolders` -- column renamed to `relativepath` at commit `0f8eb3eb`, caller not updated. Pre-existing bug; fires under active scan capability. File via `/b` when triaged.
- Operator "retry a single file" UI. Today: SQL only. Deferred until throughput indicates it is needed.
- Per-file operator "assert language = eng" override for shows known to be English. Deferred until fleet backfill throughput proves inadequate.
