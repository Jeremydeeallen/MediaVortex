# MediaProbe -- FFprobe metadata extraction + failure tracking

**Slug:** media-probe

## What It Does

Runs FFprobe against media files to extract metadata (resolution, codec, container, audio streams, subtitles, duration), tracks per-file probe failures to skip irrecoverable files, and re-probes after FileReplacement swaps in a transcoded output. The column set this vertical writes is the most-read in the system -- every other vertical (Compliance, AudioNormalization, TranscodeQueue, TranscodeJob, QualityTesting, ContentClassifier) reads it.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | Queue files for reprobe | curl + future /Scanning UI button | `POST /api/MediaProbe/Reprobe` | `MediaProbeController.QueueReprobe` (sets `MediaFiles.NeedsReprobe=TRUE` for matching rows) |
| W2 | Cancel queued reprobe | curl | `DELETE /api/MediaProbe/Reprobe` | `MediaProbeController.CancelReprobe` |
| W3 | View reprobe queue status | admin / /Scanning | `GET /api/MediaProbe/ReprobeQueueStatus` | `MediaProbeController.ReprobeQueueStatus` |
| W4 | Probe a single file by Id | curl / FileReplacement post-rename | `POST /api/MediaProbe/Probe/<MediaFileId>` | `MediaProbeController.ProbeFile` -> `MediaProbeBusinessService.ProbeFile` |
| W5 | Probe all files needing metadata | scanner probe phase / admin | `POST /api/MediaProbe/ProbeAll` | `MediaProbeController.ProbeAll` -> `MediaProbeBusinessService.ProbeFilesNeedingMetadata` |
| W6 | View probe statistics | /Status / /Scanning widgets | `GET /api/MediaProbe/Statistics` | `MediaProbeController.GetStatistics` -> `MediaProbeBusinessService.GetProbeStatistics` |
| W7 | View failed-probe files | /Scanning page Corrupt Files modal | `GET /api/MediaProbe/Failed` | `MediaProbeController.GetFailedFiles` -> `MediaProbeBusinessService.GetFailedFiles` |
| W8 | Reset failures for one file | /Scanning action | `POST /api/MediaProbe/ResetFailures/<MediaFileId>` | `MediaProbeController.ResetFailures` -> `MediaProbeBusinessService.ResetFailures` |
| W9 | Reset all failures | admin action | `POST /api/MediaProbe/ResetAllFailures` | `MediaProbeController.ResetAllFailures` -> `MediaProbeBusinessService.ResetAllFailures` |

## Success Criteria

C1. A successful `ProbeFile(Id)` writes `Resolution`, `Codec`, `AudioCodec`, `VideoBitrateKbps`, `ResolutionCategory`, `IsInterlaced`, `ContainerFormat`, `AudioLanguages`, `HasExplicitEnglishAudio`, `HasForcedSubtitles`, `SubtitleFormats`, `DurationMinutes` on the `MediaFiles` row for that Id. Verifiable: `SELECT Resolution, Codec, ... FROM MediaFiles WHERE Id=<id>` returns non-NULL values matching `ffprobe -show_streams` output for the source file.

C2. A failed `ProbeFile(Id)` increments `FFprobeFailureCount` and sets `LastFFprobeError` + `LastFFprobeAttemptDate`. The C1 columns are NOT overwritten with NULL on failure. Verifiable: probe a deliberately-missing file; pre-existing column values survive, failure count increments by 1.

C3. Files with `FFprobeFailureCount >= 3` are skipped by `ProbeFile` unless `Force=True` is passed. Verifiable: file with count=3 returns `{Success: False, Message: "exceeded max probe failures"}` on a non-Force call.

C4. After FileReplacement renames the new transcoded file in place, MediaProbe is invoked and re-probes the file; metadata reflects the new file. Verifiable: HEVC -> AV1 re-encode shows `Codec='av1'` after re-probe completes.

C5. `ProbeFilesNeedingMetadata` processes files in batches and reports progress via a `ProgressCallback` parameter when supplied. Verifiable: invoke from `FileScanningBusinessService` probe phase; observe `ScanJobs.ProgressedFiles` increment during the run.

C6. `ResetFailures(Id)` sets `FFprobeFailureCount = 0` and clears `LastFFprobeError`; the file is eligible for the next probe. Verifiable: pre-state with count > 0; call ResetFailures; post-state has count=0 + NULL LastFFprobeError.

C7. Probe completion triggers compliance recompute via `QueueManagementBusinessService.RecomputeForFiles([Id])` for the just-probed MediaFileId. Verifiable: post-probe `SELECT ComplianceEvaluatedAt FROM MediaFiles WHERE Id=<id>` advances (today; will become trigger-derived after the compliance refactor).

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `_ExecuteProbe` -> `MediaFiles` columns | `MediaProbeBusinessService._ExecuteProbe` | UPDATE on the 12+ columns listed in Cross-Vertical Contract WRITES | Every downstream vertical (Compliance, AudioNormalization, TranscodeQueue, ContentClassifier) reads these columns | Post-probe `SELECT` returns fresh values; `Tests/Contract/TestMediaProbeBusinessService.py` |
| S2 | FileReplacement -> MediaProbe (re-probe) | `Features/FileReplacement/FileReplacementBusinessService._UpdateMediaFilesAfterReplacement` | `MediaFileId: int` (and resolved new path) | `ProbeFile(Id)` re-extracts metadata for the swapped-in file | `Tests/Contract/TestFileReplacement` re-probe coverage |
| S3 | FileScanning -> MediaProbe (batch probe) | `FileScanningBusinessService` probe phase | (no args; iterates `MediaFiles` with NULL/stale probe data) | `ProbeFilesNeedingMetadata` iterates + probes; updates ScanJobs progress | `ScanJobs.Phase='Probing'` heartbeat |
| S4 | Probe completion -> Compliance recompute | `_ExecuteProbe` post-flight (today: try/except wrapper at lines ~193-200) | `QueueManagementBusinessService.RecomputeForFiles([Id])` | Compliance writes `WorkBucket` / `OperationsNeededCsv` / `ComplianceEvaluatedAt` (post-refactor: trigger derives WorkBucket from three booleans) | Post-probe `SELECT WorkBucket FROM MediaFiles WHERE Id=<id>` advances |
| S5 | Worker capability -> probe binary | `MediaProbeBusinessService._GetWorker` | `Worker.FFprobePath` per-worker resolution | `_ExecuteProbe` invokes the worker's local FFprobe binary, not a global path | Worker with custom FFprobePath produces logs naming that path |

## Cross-Vertical Contract

This section locks the MediaProbe vertical's public surface. Any other vertical interacts with MediaProbe ONLY through what is listed below. Other verticals MUST NOT open MediaProbe internal helpers (any function prefixed with `_`) or import private classes. MediaProbe reserves the right to change anything not in this contract without notice.

### Columns the MediaProbe vertical WRITES

Consumers (every other vertical) may SELECT these. They MUST NOT write them.

| Column | Written by |
|---|---|
| `MediaFiles.Resolution` | `_ExecuteProbe` (success) |
| `MediaFiles.Codec` | `_ExecuteProbe` (success) |
| `MediaFiles.AudioCodec` | `_ExecuteProbe` (success) |
| `MediaFiles.VideoBitrateKbps` | `_ExecuteProbe` (success) |
| `MediaFiles.ResolutionCategory` | `_ExecuteProbe` (success) |
| `MediaFiles.IsInterlaced` | `_ExecuteProbe` (success) |
| `MediaFiles.ContainerFormat` | `_ExecuteProbe` (success) |
| `MediaFiles.AudioLanguages` | `_ExecuteProbe` (initial value at probe time; the AudioNormalization vertical may overwrite per its own contract) |
| `MediaFiles.HasExplicitEnglishAudio` | `_ExecuteProbe` (success) |
| `MediaFiles.HasForcedSubtitles` | `_ExecuteProbe` (success) |
| `MediaFiles.SubtitleFormats` | `_ExecuteProbe` (success) |
| `MediaFiles.DurationMinutes` | `_ExecuteProbe` (success) |
| `MediaFiles.AudioCorruptReason` | `_ExecuteProbe` (when FFmpeg signals corrupt audio, e.g. "ac3 not a single unique syncword found") |
| `MediaFiles.FFprobeFailureCount` | `_RecordProbeFailure` (incremented) / `ResetFailures` (cleared to 0) |
| `MediaFiles.LastFFprobeError` | `_RecordProbeFailure` (set) / `ResetFailures` (cleared) |
| `MediaFiles.LastFFprobeAttemptDate` | `_RecordProbeFailure` + `_ExecuteProbe` (on success) |
| `MediaFiles.NeedsReprobe` | `QueueReprobe` (set TRUE) / `_ExecuteProbe` (cleared on success) |

### Columns the MediaProbe vertical READS from external tables

These are context the MediaProbe vertical consumes. MediaProbe NEVER writes these. Other verticals own them.

| Column | Read by | Owner |
|---|---|---|
| `MediaFiles.{Id, FilePath, StorageRootId, RelativePath, FileName}` | `_ResolveWorkerLocal`, `ProbeFile`, every public method that takes a MediaFileId | FileScanning vertical |
| `Workers.FFmpegPath` / `FFprobePath` | `_GetWorker` -> Path resolution | Workers data accessor (`Features/Workers/`) |
| `StorageRoots.CanonicalPrefix` / `Id` | `_GetStorageRoots`, `Path.FromLegacyString` | Path infrastructure (`Core/Path/`) |

### Stable function entry points (cross-vertical callers)

Classes + signatures with external callers TODAY. Their signatures are contract; constructor injection allowed (any class listed accepts collaborator injection for tests). Adding a new keyword argument with a default is non-breaking; removing or renaming a parameter is a contract change that requires a directive.

| Class.method | External caller(s) |
|---|---|
| `MediaProbeBusinessService.ProbeFile(MediaFileId: int, Force: bool=False) -> dict` | `Features/FileReplacement/` post-rename re-probe |
| `MediaProbeBusinessService.ProbeFilesNeedingMetadata(RootFolderId: Optional[int]=None, ProgressCallback=None) -> dict` | `Features/FileScanning/FileScanningBusinessService` probe phase |
| `MediaProbeBusinessService.GetFailedFiles() -> dict` | `Features/FileScanning/` /Scanning page Corrupt Files modal |
| `MediaProbeBusinessService.ResetFailures(MediaFileId: int) -> dict` | `Features/FileScanning/` UI action |
| `MediaProbeBusinessService.ResetAllFailures() -> dict` | admin action |
| `MediaProbeBusinessService.GetProbeStatistics() -> dict` | /Status / /Scanning widgets |

### HTTP API surface

The blueprint registered at `Features/MediaProbe/MediaProbeController.py` exposes the routes below. These are the operator-facing contract; UI templates + external scripts may call them.

| Method + URL | Purpose |
|---|---|
| `POST /api/MediaProbe/Reprobe` | Queue matching files for reprobe (body: `MediaFileIds[]` / `ShowFolder` / `Drive`) |
| `DELETE /api/MediaProbe/Reprobe` | Cancel queued reprobe |
| `GET /api/MediaProbe/ReprobeQueueStatus` | Reprobe queue counts |
| `POST /api/MediaProbe/Probe/<MediaFileId>` | Probe a single file by Id |
| `POST /api/MediaProbe/ProbeAll` | Probe all files needing metadata |
| `GET /api/MediaProbe/Statistics` | Probe-coverage statistics |
| `GET /api/MediaProbe/Failed` | List of files exceeding FFprobe failure cap |
| `POST /api/MediaProbe/ResetFailures/<MediaFileId>` | Clear failure counter for one file |
| `POST /api/MediaProbe/ResetAllFailures` | Clear failure counter for all files |

### What is EXPLICITLY NOT a contract

Other verticals MUST NOT depend on any of the following. MediaProbe changes these freely:

- Internal helper names (`_ResolveWorkerLocal`, `_ExecuteProbe`, `_RecordProbeFailure`, etc.)
- The specific FFprobe binary version or invocation flags (operator-tunable via `Workers.FFprobePath`)
- The shape of returned dict's debug fields beyond `Success`, `Message`, and the documented primary column values
- The `MaxFFprobeFailures` constant (currently 3); future operator-tunable via SystemSettings
- Internal directory structure under `Features/MediaProbe/`
- The `try/except` wrapper around `RecomputeForFiles` call at probe completion (this will be removed when the compliance refactor lands per its no-failsafes contract)

## Status

ACTIVE. Created 2026-06-20 to fill the ARCHITECTURE.md gap row "Create top-level MediaProbe.feature.md + Cross-Vertical Contract."

## Files

| File | Role |
|---|---|
| `MediaProbeController.py` | Flask blueprint at `/api/MediaProbe/*` -- 9 routes (W1-W9) |
| `MediaProbeBusinessService.py` | Probe orchestration: per-file + batch + failure tracking |
| `MediaProbeRepository.py` | Data access: reads MediaFiles row, writes probe column UPDATEs |
| `MediaProbeViewModel.py` | View-model layer; formats responses for controller |
