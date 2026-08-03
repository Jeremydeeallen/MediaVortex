# Flow: Ingest

**Slug:** ingest

## What this flow is

The end-to-end derivation chain from **filesystem** to **transcode-ready MediaFiles row**. Owns the pipeline shape; per-vertical contracts live in the colocated `*.feature.md` docs referenced per stage.

Design invariants (`.claude/directive.md` ingest-pipeline-kiss, DDs):

- **DD_A** -- chain is derivation, idempotent, cascade-on-change.
- **DD_B** -- one SQL per RootFolder per scan tick (batch fetch + in-memory diff + batch write).
- **DD_C** -- two workers + one webhook (scan + probe + Sonarr/Radarr).
- **DD_D** -- no queues except retry state (`NeedsReprobe`, `FFprobeFailureCount`).
- **DD_E** -- two operator surfaces (Sync Path button + /Failures page).
- **DD_F** -- writer-owns-cascade (see `.claude/rules/writer-owns-cascade.md`).

## Entry Points

Three discovery layers converge on the same scan primitive.

| Layer | Trigger | Frequency | Path |
|---|---|---|---|
| Sonarr / Radarr webhook | External POST | On file operation | `POST /api/Ingest/Webhook` -> enqueue ScanJobs row for the RootFolder containing the payload's target path |
| Sync Path GUI | Operator button on `/Settings` | On demand | `POST /api/Sync/Path` `{CanonicalPath}` -> enqueue ScanJobs row scoped to that path |
| Continuous scanner | `ContinuousScanService` per worker | `ScanIntervalMinutes` (default 60; safety net) | Iterate top-level RootFolders alphabetically; enqueue ScanJobs row per (subject to `ScanEnabled` + affinity) |

Plus the existing `POST /api/RootFolders/<id>/ScanNow` from `ad-hoc-drive-scans.feature.md` (per-RootFolder immediate scan button on `/Scanning` page).

All entry points land in `FileScanningBusinessService.StartScanning(canonicalpath, WorkerName=...)` which writes a `ScanJobs` row with `Status='Pending'`. The per-RootFolder claim guard (partial UNIQUE index on ScanJobs) ensures only one active scan per rootfolder at a time.

## Pipeline

| ID | Stage | File | What It Does |
|---|---|---|---|
| ST1 | Trigger | `IngestWebhookController` / `SyncPathController` / `ContinuousScanService` / `FileScanningController.ScanNow` | Enqueue `ScanJobs` row (`Status='Pending'`, `RootFolderPath`, `StorageRootId`, `RelativePath`, `WorkerName`) |
| ST2 | Claim + walk | `FileScanningBusinessService.PerformScan` -> `FileManager.ScanDirectory` | Claim `ScanJobs` row; `os.scandir` recursively over the requested subtree; produce `disk_files = List[(RelativePath, filesize, filemodificationtime)]`. Skips excluded dirs per `SystemSettings('ExcludedDirectories')`. Never opens files. |
| ST3 | Diff + batch write | `FileScanningRepository.BatchFetchForRootFolder` + `.BatchUpsert` + `.BatchSoftDelete` | ONE SELECT: `db_files = dict[RelativePath] -> (filesize, filemodificationtime)`. In-memory 3-way set diff -> `new / changed / deleted / renamed`. Rename detection: `deleted` and `new` rows with matching `(filesize, filename)` collapse into single UPDATE that reassigns RelativePath (preserves Id + AssignedProfile + probe metadata + archive rows). Batch INSERT `new`; batch UPDATE `changed` (sets `NeedsReprobe = TRUE`); batch soft-delete `deleted`. Zero writes if all three sets empty. |
| ST4 | Probe (async, fleet-wide) | `WorkerService/ProbeWorker.py` | Independent poll loop on capable workers (`Workers.ProbeEnabled=TRUE`). Claims one MediaFiles row where `Resolution IS NULL OR NeedsReprobe = TRUE` AND `FFprobeFailureCount < MaxFFprobeFailures`. Runs `MediaProbeBusinessService.ProbeFile(Id)` which extracts metadata + loudness. On success: writes 12+ metadata columns + clears `NeedsReprobe`. On failure: increments `FFprobeFailureCount`, writes `LastFFprobeError` + `LastFFprobeAttemptDate`. **Cascade before return** per writer-owns-cascade. |
| ST5 | Classify (probe hook) | `ContentClassifierService.ClassifyAndAssign(Id)` | Runs immediately after probe write (in-process, same call chain). Sticky-guard: if `AssignedProfile IS NOT NULL`, skip. Otherwise walk `ContentClassificationRules` priority-ascending; first match wins; `WriteAssignment(Id, ProfileName, 'classifier')`. **Cascade before return** per writer-owns-cascade. |
| ST6 | Compliance recompute | `QueueManagementBusinessService.RecomputeForFiles([Id])` | Called by the cascade in ST4 + ST5. Phase 1: `AudioVertical + VideoVertical + ContainerVertical`.RecomputeFor each write `AudioCompliant / VideoCompliant / ContainerCompliant` booleans. DB trigger derives `IsCompliant` + `WorkBucket`. Phase 2: re-fetch + compute `PriorityScore` + AudioFix folder pin + bulk UPDATE. Idempotent + cheap on unchanged inputs. |
| ST7 | WorkBucket (trigger-derived) | DB trigger on `MediaFiles` | Derives `WorkBucket IN ('Compliant', 'Unclassified', 'Transcode', 'Remux', 'AudioFix')` from the three compliance booleans + AssignedProfile presence. Owned by `work-bucket.flow.md`; ingest treats as sink. |

## Ordering rationale

Classifier runs BEFORE compliance so `VideoVertical.Evaluate` (which requires `AssignedProfile` since `video-compliance-multiplier` 2026-07-26) sees populated input on first pass. Writer-owns-cascade (`.claude/rules/writer-owns-cascade.md`) ensures any later write to a compliance input (including operator SQL, manual reassignment) recomputes correctly.

Prior ordering (compliance BEFORE classifier) caused Full Circle S1 stuck rows -- see rule-details case study.

## Seams

Cross-stage contracts. Downstream consumers rely on these; every change enumerates the affected seams per `.claude/rules/seam-verification.md`.

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | trigger -> ST2 | any entry-point controller writes `ScanJobs(Id, Status='Pending', RootFolderPath, StorageRootId, RelativePath, WorkerName)` | `ScanJobs` row visible | `PerformScan` claims via partial UNIQUE index `sj_one_active_per_root` (existing) | `SELECT Status, Phase, WorkerName FROM ScanJobs WHERE Id=<id>` -- transitions Pending -> Running |
| S2 | ST2 -> ST3 (walk -> diff) | `FileManager.ScanDirectory` returns `List[str]` of local paths | in-memory list, worker-local | `PerformScan` converts local -> canonical via `_ToCanonicalPath` | contract test: seed known disk state, assert list contents |
| S3 | ST3 write (per-file identity) | `BatchUpsert` INSERT/UPDATE on `MediaFiles(StorageRootId, RelativePath, filesize, filemodificationtime, LastScannedDate)`; `NeedsReprobe=TRUE` on any UPDATE that changed size or mtime | Row identity: `(StorageRootId, LOWER(RelativePath))` per existing `idx_mediafiles_storageroot_relpath_unique` | every downstream vertical reads MediaFiles by Id | `SELECT COUNT(*) FROM MediaFiles WHERE LastScannedDate >= <scan-start>` matches sum of new+changed |
| S4 | ST3 rename detection | `BatchUpsert` collapses `(deleted, new)` pair with matching `(filesize, filename)` into one UPDATE that reassigns `RelativePath` | preserves `Id`, `AssignedProfile`, `TranscodedByMediaVortex`, `IsCompliant`, probe metadata, `TranscodeAttempts` FK, `MediaFilesArchive` FK | `Tests/Contract/TestScanRenameDetection.py` asserts row Id unchanged post-rename | contract test |
| S5 | ST3 -> ST4 (auto-chain via column state) | UPDATE branch sets `NeedsReprobe = TRUE`; INSERT branch leaves `Resolution` NULL | `MediaFiles.(Resolution IS NULL OR NeedsReprobe = TRUE)` | `ProbeWorker` polls that predicate fleet-wide; picks up new/changed rows | contract test asserts row appears in probe claim within N ticks after scan write |
| S6 | ST4 probe write | `ProbeWorker` -> `MediaProbeBusinessService._ExecuteProbe` writes `Resolution, Codec, VideoBitrateKbps, AudioCodec, ContainerFormat, AudioLanguages, HasExplicitEnglishAudio, HasForcedSubtitles, SubtitleFormats, DurationMinutes, ResolutionCategory, IsInterlaced` + loudness columns via chained `LoudnessAnalysisService.MeasureAndPersist`; clears `NeedsReprobe`; cascade fires | 12+ metadata columns + 4 loudness columns non-NULL | every vertical reads these; wire shape unchanged from pre-directive | `SELECT Resolution, Codec, LoudnessMeasuredAt FROM MediaFiles WHERE Id=<id>` non-NULL after probe |
| S7 | ST4 -> ST5 (probe hook) | `_ExecuteProbe` post-flight invokes `ContentClassifierService.ClassifyAndAssign(Id)` | in-process function call | classifier reads populated probe columns | contract test |
| S8 | ST5 write | `ContentClassifierRepository.WriteAssignment(Id, ProfileName, 'classifier')` -- `UPDATE MediaFiles SET AssignedProfile=%s, AssignedProfileSource='classifier' WHERE Id=%s AND AssignedProfile IS NULL` (sticky guard); cascade fires | `MediaFiles.(AssignedProfile TEXT, AssignedProfileSource TEXT)` populated | queue admission + `/Work/Compliant` operator surface | contract test |
| S9 | cascade -> ST6 | `RecomputeForFiles([Id])` writes `AudioCompliant / VideoCompliant / ContainerCompliant` booleans + reasons | 3 booleans + 3 reason strings per row | DB trigger reads to derive IsCompliant + WorkBucket | `SELECT VideoCompliant, VideoCompliantReason, WorkBucket FROM MediaFiles WHERE Id=<id>` populated |
| S10 | probe failure | `_ExecuteProbe` catch writes `FFprobeFailureCount += 1, LastFFprobeError, LastFFprobeAttemptDate` | integer + text + timestamp | `/Failures` page reads for retry surface; ProbeWorker's claim gate skips at cap | contract test |
| S11 | scan failure (permission / mount) | `ScanJobs.Status='Failed', ErrorMessage='<reason>'` | terminal ScanJobs row | `/Failures` page reads scan failures; per-RootFolder claim guard releases; next tick retries | contract test |
| S12 | webhook -> trigger | `IngestWebhookController` accepts Sonarr/Radarr payload; parses `Path` field; resolves to owning RootFolder via prefix match; enqueues ScanJobs row | JSON payload matches Sonarr `OnDownload` / `OnRename` / `OnUpgrade` / Radarr equivalent | `Features/Ingest/ingest-webhook.feature.md` documents payload shape + failure modes | contract test posts canned payload |
| S13 | Sync Path -> trigger | `SyncPathController` accepts `{CanonicalPath}`, validates prefix against `StorageRoots`, enqueues ScanJobs | JSON `{CanonicalPath: string}`; returns `{Success, ScanJobId}` | `/Settings` Sync Path button consumes | contract test |
| S14 | ContinuousScan -> trigger | `ContinuousScanService._ExecuteScan` iterates RootFolders + calls `StartScanning` | no wire; in-process | per-RootFolder claim guard blocks concurrent scans of same rootfolder | existing behavior preserved |
| S15 | RootFolder stats | post-scan aggregate: `UPDATE RootFolders SET LastScannedDate=NOW(), TotalSizeGB=(SELECT SUM(filesize)/1073741824 FROM MediaFiles WHERE StorageRootId=? AND RelativePath LIKE ?)` | `RootFolders.(LastScannedDate, TotalSizeGB)` | `/Scanning` page reads for last-scanned display | contract test |

## Idempotence contract (cheap-when-idle)

Unchanged tree = zero DB writes. Contract test `TestScanIdempotence.py` asserts:

- Seed known MediaFiles state matching disk.
- Run scan.
- Row count in `MediaFiles` unchanged.
- `NeedsReprobe = FALSE` count unchanged.
- `LastScannedDate` on unchanged rows NOT bumped (idempotence extends to timestamp columns).
- `sql_writes == 0` per instrumented query log.
- `sql_selects == 1` per RootFolder (the batch fetch).

Full-library cycle over unchanged fleet: target < 5 min, budget 20 min per operator (`ContinuousScanIntervalMinutes` default 60 remains but tick cost is bounded).

## Fast-when-changed contract

- New file: Sonarr webhook -> ScanJobs -> BatchUpsert INSERT -> `NeedsReprobe` implicit via NULL Resolution -> ProbeWorker claim next tick (<= 5s) -> probe + cascade + classify + compliance. Total: seconds to first WorkBucket.
- Existing file, mtime changed: continuous scan or webhook -> BatchUpsert UPDATE with `NeedsReprobe=TRUE` -> ProbeWorker re-probes -> cascade.
- Existing file, unchanged: zero work (idempotence).

## Failure Modes

| Failure | Symptom | Recovery |
|---|---|---|
| RootFolder mount unreachable | `ScanJobs.Status='Failed', ErrorMessage='[Errno ...] No such file or directory'` | Fix mount; next continuous tick retries; visible in `/Failures` |
| Worker crash mid-scan | `ScanJobs` row left `Running` past heartbeat cap | `StuckJobDetectionService.DetectAndCleanStuckScanJobs` (existing) flips to `Failed`; per-RootFolder claim releases |
| Concurrent scan attempt on same rootfolder | `StartScanning` rejects with `ScanAlreadyRunning` | Partial UNIQUE index `sj_one_active_per_root` enforces at DB (existing) |
| ffprobe fails N times | `FFprobeFailureCount >= MaxFFprobeFailures`; row not re-claimed | Visible on `/Failures`; operator hits Retry -> resets count + `NeedsReprobe=TRUE` |
| Escape-variant insert (buggy writer) | `psycopg2.UniqueViolation` on `idx_mediafiles_storageroot_relpath_unique` | Loud fail by design; caller catches + picks next batch |
| Classifier no-rule-matched | WARNING logged; `AssignedProfile` stays NULL; `WorkBucket='Unclassified'` | Operator adds a rule via SQL; next re-classify via NULL AssignedProfile + probe hook covers |
| Cascade error mid-write | Exception propagates per fail-loud | Writer transaction rolls back; next scan or manual retry recovers |
| Sonarr webhook malformed | 400 response; no ScanJobs row | Endpoint fails loud on unrecognized shape (per Fail Loud rule); operator inspects payload |
| Rename detection false-positive | Wrong row's RelativePath reassigned | Rare: requires same `(filesize, filename)` collision AND single-tick disk state. Detection: run scan twice; consistent output means no collision. |

## State Surface

**MediaFiles** (per-row derived state):
- Tier 1 (source-of-truth, populated by scan or probe): `filesize, filemodificationtime, LastScannedDate, Resolution, Codec, VideoBitrateKbps, AudioCodec, ContainerFormat, AudioLanguages, ...`
- Tier 1 retry state: `NeedsReprobe (bool), FFprobeFailureCount (int), LastFFprobeError, LastFFprobeAttemptDate`
- Tier 1 classifier: `AssignedProfile, AssignedProfileSource`
- Tier 2 derived (populated by cascade): `AudioCompliant, VideoCompliant, ContainerCompliant, IsCompliant, {Video/Audio/Container}CompliantReason`
- Tier 3 trigger-derived: `WorkBucket`

**ScanJobs** (per-scan runtime state): `Id, Status, Phase, WorkerName, RootFolderPath, StorageRootId, RelativePath, StartTime, EndTime, LastUpdated, Progress, TotalFiles, ProcessedFiles, NewFiles, UpdatedFiles, DeletedFiles, SkippedFiles, ErrorMessage`. `Phase` values reduced to `Walking, Diffing, Completing` (was 5-value per prior directive; SizeSurvey + Reconciling + Probing removed).

**Workers** (per-worker capability state): `ScanEnabled (bool), ProbeEnabled (bool)`. Both DB-authoritative; claim predicates read fresh per tick (`.claude/rules/db-is-authority.md`).

**RootFolders**: `LastScannedDate, TotalSizeGB, ScanEnabled, PreferredWorkerName`. `TotalSizeGB` = post-scan aggregate from `SUM(MediaFiles.filesize)`, not disk-walk.

## Discovery cadence

| Layer | Latency | Cost |
|---|---|---|
| Webhook | seconds | ~1 SELECT + 1 INSERT (ScanJobs enqueue) per Sonarr event |
| Sync Path | seconds | same + ScanJobs claim + one-shot scan of subtree |
| Continuous | up to 60 min | 1 SELECT per RootFolder (unchanged tree); wall-time bounded by DD_B batch cost |
| Per-RootFolder ScanNow | seconds | same as continuous per one rootfolder |

## Operator Surfaces

- `/Settings` -- "Sync Path" input + button (S13). "Registered Drives" section from `ad-hoc-drive-scans.feature.md` (per-RootFolder ScanEnabled toggle + Scan Now button).
- `/Scanning` -- scan history + active scans (existing; unchanged shape).
- `/Failures` -- stuck files (scan or probe failure); per-row Retry button (`Features/Failures/failures.feature.md`).
- `/Activity` -- in-flight scans block (existing).
- `/Operations` -- recent scan history (existing).
- `/api/Ingest/Webhook` -- Sonarr/Radarr external POST (`Features/Ingest/ingest-webhook.feature.md`).

## What this flow does NOT own

- Transcode pipeline: `transcode.flow.md`.
- WorkBucket derivation trigger: `work-bucket.flow.md`.
- QT / VMAF: `Features/QualityTesting/quality-test.flow.md`.
- FileReplacement post-transcode: `Features/FileReplacement/post-transcode-pipeline.feature.md`.

Per-stage details live in the colocated feature docs:

- `Features/FileScanning/scan.feature.md` -- ST1/ST2/ST3 details, entry points, RootFolder registration, ScanEnabled, ContinuousScanService cadence.
- `Features/MediaProbe/probe.feature.md` -- ST4 details, ProbeWorker, cascade behavior, failure semantics.
- `Features/ContentClassifier/classifier.feature.md` -- ST5 details, rules table, sticky-override semantics, cascade behavior.
- `Features/Failures/failures.feature.md` -- /Failures page + retry endpoint.
- `Features/Ingest/ingest-webhook.feature.md` -- Sonarr/Radarr webhook contract + payload parsing.
- `Features/FileScanning/scanners.feature.md` -- shared `Scanners` config table (ScanWorker + ProbeWorker + StuckJobDetection read their config from here).
- `Features/FileScanning/ad-hoc-drive-scans.feature.md` -- per-RootFolder ScanEnabled toggle + Scan Now button.
