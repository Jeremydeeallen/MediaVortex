# Flow: Content Signals

**Slug:** content-signals

## Entry Point

`MediaProbeBusinessService._ExecuteProbe(MediaFile)` -- after probe success. The probe completes, writes its metadata (Codec, Resolution, AudioLanguages, etc.), then invokes ContentSignals as a non-blocking extension before `ComputePriorityScore`.

Also invoked manually from `Scripts/SQLScripts/BackfillContentSignals.py` for historical rows that pre-date this feature.

## Pipeline

| Stage | File | What It Does |
|---|---|---|
| 1. Probe completes | `MediaProbeBusinessService._ExecuteProbe` | Writes probe metadata, returns the MediaFile model with updated columns. |
| 2. Signal-gate check | same | If `MediaFile.MotionFraction IS NOT NULL`, signals already computed -- skip. Otherwise proceed. |
| 3. Path resolve | same | Translate canonical `(StorageRootId, RelativePath)` to local path via `Core.PathStorage.Resolve(WorkerName)`. Use `MediaFile.FilePath` as fallback if canonical pair is missing. |
| 4. Compute signals | `ContentSignalsService.ComputeSignals(LocalPath)` | Runs `ffmpeg signalstats` (sampled per-frame YDIF + YLOW/YHIGH) and `PySceneDetect ContentDetector`. Aggregates into MotionFraction / SceneChangeRatePerMin / LumaVariance. Returns `ContentSignalsModel` or None on any failure. |
| 5. Persist | `ContentSignalsRepository.WriteSignals(MediaFileId, Model)` | `UPDATE MediaFiles SET MotionFraction=%s, SceneChangeRatePerMin=%s, LumaVariance=%s WHERE Id = %s`. Single statement, ExecuteNonQuery, auto-commits. |
| 6. Log | `LoggingService.LogInfo` | `"ContentSignals computed for MediaFileId N: motion=X scene_rate=Y luma_var=Z (took N.Ns)"`. One line per compute, no spam. |

## State Surface

`MediaFiles` columns added by this flow:
- `MotionFraction` (DOUBLE 0..1, nullable) -- fraction of sampled frames where motion exceeds threshold
- `SceneChangeRatePerMin` (DOUBLE, nullable) -- scene-changes-per-minute over the file
- `LumaVariance` (DOUBLE, nullable) -- mean Y-channel variance

NULL on any of the three = signals not yet computed (either pre-feature row or compute failed last time). ContentClassifier treats NULL as "fall back to bitrate + folder heuristics" (graceful degradation).

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| File unreadable (NFS hiccup, permission) | ContentSignalsService returns None; INFO log "signal compute failed: <reason>"; columns stay NULL | Next probe retries (the NULL-gate check at Stage 2 will hit the recompute branch). If the file becomes readable, signals populate. |
| PySceneDetect not installed | Import error at service load; ContentSignalsService.ComputeSignals returns None on every call; one WARNING line at startup | Add `scenedetect` to the worker venv via the standard deploy. |
| ffmpeg signalstats parse error (unknown stat line) | Service catches at parse boundary, returns None | Investigate the new ffmpeg version's output format; extend the parser. |
| Compute exceeds budget (e.g. 4K source takes minutes) | Subprocess timeout (default 600s); ContentSignalsService returns None | Acceptable. Backfill will retry; runtime probe is non-blocking so the file moves through the pipeline anyway. Operator can manually re-run BackfillContentSignals.py on the failing rows. |

## Continuous Mode Specifics

ContentSignals runs inside the probe hook -- it inherits the probe scheduler's cadence. Workers that are `ScanEnabled=true` pick up newly-discovered files via `ContinuousScanService`, those scans trigger probes, those probes trigger ContentSignals. No separate cron / poller; the existing scan-probe lifecycle covers continuous coverage.

For the backfill of pre-feature rows, the operator runs `BackfillContentSignals.py` once as a one-shot. After that, every newly-probed file (forever) gets signals automatically.

## Surface

No direct UI. Read-side consumers:
- `Features/ContentClassifier/` -- the primary consumer; reads all three signals to pick a profile
- `/SQLQueries` page -- operator-visible via ad-hoc queries
- Future feature docs that need content-type signals
