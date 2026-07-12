# Content Signals -- Probe-Time Content Characterization

**Slug:** content-signals

## What It Does

Adds a small read-only extension to the existing probe pipeline that runs `ffmpeg signalstats` and `PySceneDetect` on each newly-probed file once, then writes three numeric columns to `MediaFiles`:

- `MotionFraction` (DOUBLE 0..1) -- fraction of source frames whose integer_motion score is above a threshold. Approximates "how dynamic is this content." Low = held-frame / talking-head / static-locked-camera; high = action / sports / handheld.
- `SceneChangeRatePerMin` (DOUBLE) -- number of detected scene changes per minute of source duration. Low = anime / documentary / long takes; high = action / music video / trailer-style cuts.
- `LumaVariance` (DOUBLE) -- per-frame Y-channel variance averaged across the file. Low = flat colors (animation), high = textured / grainy / detailed.

These signals feed `Features/ContentClassifier/` (the auto-profile-assignment vertical) and any future system that needs content-type awareness without re-probing.

The probe extension runs ONCE per file at the same point `ComputePriorityScore` runs. Cached in DB forever; recomputed only on operator request via the backfill script.

## Concern

`Features/ContentClassifier/` cannot make good per-content-type profile decisions without numeric signals. Today the only signals are `Codec`, `Resolution`, `VideoBitrateKbps`, `ContainerFormat` -- enough to detect "already compressed" but not "anime" vs "live action with held frames" vs "action." Folder-pattern guessing (`%Anime%`) works for a fraction of the library but breaks on everything that doesn't follow a naming convention.

`signalstats` + `PySceneDetect` are battle-tested OSS tools that give us the three numeric signals above for ~5-10 seconds of probe-time CPU per file. Cheap data; high downstream leverage.

## Surface

Internal probe-pipeline extension. No new UI; the columns surface on `/SQLQueries` and any future tile that wants to display them.

Observable effects:
- `MediaFiles` gains three columns. NULL = not yet signaled (probed before this feature shipped or recompute pending).
- `Logs` shows a single INFO line per probe: `"ContentSignals computed for MediaFileId N: motion=X scene_rate=Y luma_var=Z (took N.Ns)"`.
- Backfill script `Scripts/SQLScripts/BackfillContentSignals.py` walks NULL rows in batches, applies the signal compute, reports progress.

## Success Criteria

### Schema

1. `MediaFiles.MotionFraction DOUBLE PRECISION` column exists, nullable. NULL = not yet computed. Verifiable: `\d MediaFiles` shows the column.

2. `MediaFiles.SceneChangeRatePerMin DOUBLE PRECISION` column exists, nullable. NULL = not yet computed.

3. `MediaFiles.LumaVariance DOUBLE PRECISION` column exists, nullable. NULL = not yet computed.

4. Migration script `Scripts/SQLScripts/AddContentSignalsColumns.py` is idempotent (uses `ADD COLUMN IF NOT EXISTS`). Verifiable: running it twice produces no errors and no schema diff after the second run.

### Service contract

5. `Features/ContentSignals/ContentSignalsService.ComputeSignals(LocalFilePath: str) -> Optional[ContentSignalsModel]` returns a populated `ContentSignalsModel` (MotionFraction, SceneChangeRatePerMin, LumaVariance) on success, or `None` on any failure (file not found, tool crash, parse error). NEVER raises -- failure is logged, returns None, caller continues. Verifiable: call with a known-good file -> non-None; call with a bogus path -> None.

6. The service does NOT write to the database. Persistence is the caller's responsibility (separation: compute service is reusable for canaries / tests, the persistence policy lives at the call site).

7. The service is data-source-agnostic: it accepts a local filesystem path (already-translated by the caller). It does NOT do path translation itself. Verifiable: the same call works from a Linux worker with `/mnt/media_tv/...` and from a Windows worker with `T:\...` or `\\10.0.0.43\srv\...`. Translation responsibility stays at the probe-pipeline seam.

8. Tool dependencies are confined to the service module: `ffmpeg` (already on PATH per WorkerContext) and `PySceneDetect` (new pip requirement). No other module imports either of these tools directly. Verifiable: grep the repo for `scenedetect` imports -- only `ContentSignalsService.py`.

### Probe hook

9. `Features/MediaProbe/MediaProbeBusinessService._ExecuteProbe` invokes ContentSignals AFTER probe success but BEFORE `ComputePriorityScore` (so the classifier hook downstream can see fresh signals). Failure of ContentSignals does NOT roll back probe -- the row keeps its probe metadata and gets NULL signals. Verifiable: induce a ContentSignals failure (e.g. delete PySceneDetect), confirm probe still completes Success=True and the row's probe metadata is populated.

10. The hook computes signals exactly once per file. If signals are already non-NULL on the row, the hook skips. Verifiable: probe a file twice; second probe leaves the existing signal values untouched (no recompute, no UPDATE).

### Backfill

11. `Scripts/SQLScripts/BackfillContentSignals.py` walks `MediaFiles WHERE MotionFraction IS NULL ORDER BY Id` in batches (default 100), computes signals, writes the three columns. Supports `--dry-run`, `--limit`, `--batch-size`. Verifiable: run on a small `--limit 10` sample; observe 10 rows transitioned from NULL to non-NULL.

12. The backfill is idempotent (already-signaled rows are skipped by the WHERE clause; re-running produces zero work). Verifiable: run twice on the same state, second run reports 0 processed.

13. The backfill is shape-agnostic per `feedback_paths_must_be_shape_agnostic.md`: routes through `Core.Path.LocalPath / Core.Path.Path.Resolve(StorageRootId, RelativePath, WorkerName)` when the row has canonical pair; falls back to `FilePath` only if the canonical pair is NULL.

## Data sources (what each tool gives us)

| Tool | Output | Signal computed |
|---|---|---|
| `ffmpeg -i SRC -vf signalstats -an -f null -` | per-frame YDIF (luma frame diff), YLOW/YHIGH (luma min/max), HUEMED | `MotionFraction` (from YDIF aggregation), `LumaVariance` (from YLOW/YHIGH spread) |
| `PySceneDetect ContentDetector` | scene boundaries (list of (start_time, end_time)) | `SceneChangeRatePerMin = len(scenes) / duration_min` |

Implementation notes:
- signalstats writes per-frame stats to stderr; we sample (not every-frame) -- one pass with frame-skip for large files to bound CPU.
- PySceneDetect runs via its Python API directly, NOT via shell-out, so no separate subprocess.
- The two tools share a single pass where possible; if PySceneDetect can't reuse the signalstats output, we accept the second pass.

## Stability and operability

- **Read-fresh per call**: ContentClassifier consumers must read these columns fresh per classification (no caching). Per `feedback_no_cached_db_settings.md`.
- **Tool-version stability**: PySceneDetect pinned in `requirements.txt` to a specific version. Upgrades require a re-canary + intentional doc update.
- **Forward-compat**: the model has room for additional signals (e.g. `GrainScore`, `ChromaVariance`) without rewriting the service. New columns added via migration; service extended in one place.
- **Backwards-compat**: rows with NULL signals are valid; ContentClassifier degrades gracefully (falls back to bitrate + folder heuristics, same as today's manual flow).

## Status

COMPLETE 2026-05-30. Deployed to larry workers (commit c4f8890b). Backfill on the ~50K NULL-signal library is operator-opt-in (~3-4 min per file -- only valuable when signal-based classification rules are needed for the existing backlog).

### Progress

- [x] 1. Migration script `AddContentSignalsColumns.py` applied. Three columns present.
- [x] 2. `Features/ContentSignals/` directory complete: service + repository + model + `__init__`.
- [x] 3. `scenedetect>=0.6.0` pinned in requirements.txt; installed in WebService + WorkerService + root venvs.
- [x] 4. Probe hook inserted in `MediaProbeBusinessService._ExecuteProbe` between probe-success and PriorityScore.
- [x] 5. `BackfillContentSignals.py` written + canary-verified on 30 Rock S01E01 (motion=0.94, scene_rate=22.0, luma_var=1475 -- live-action sitcom signature).
- [x] 6. Feature doc + flow doc + transcode.flow.md updated.
- [x] 7. Deployed to larry (c4f8890b). Future probes auto-populate signals on a single-shot basis.
- [ ] 8. (Operator opt-in) Bulk backfill of the existing 50K-row library. Defer until a classifier rule needs signal-derived discrimination for files already in the backlog.

## Scope

```
Scripts/SQLScripts/AddContentSignalsColumns.py          -- NEW: idempotent ADD COLUMN
Scripts/SQLScripts/BackfillContentSignals.py            -- NEW: one-shot backfill
Features/ContentSignals/ContentSignalsService.py        -- NEW: tool wrapper, returns model
Features/ContentSignals/ContentSignalsRepository.py     -- NEW: write/read columns
Features/ContentSignals/Models/ContentSignalsModel.py   -- NEW: dataclass
Features/ContentSignals/__init__.py                     -- NEW
Features/ContentSignals/content-signals.feature.md      -- this file
Features/ContentSignals/content-signals.flow.md         -- NEW
Features/MediaProbe/MediaProbeBusinessService.py        -- hook insertion after probe-success
requirements.txt                                        -- pin PySceneDetect
transcode.flow.md                                       -- Stage 2 note about the signal write
```

## Files

| File | Role |
|------|------|
| `Scripts/SQLScripts/AddContentSignalsColumns.py` | Idempotent migration: ADD COLUMN IF NOT EXISTS MotionFraction / SceneChangeRatePerMin / LumaVariance. |
| `Scripts/SQLScripts/BackfillContentSignals.py` | One-shot batched backfill for NULL-signal rows; --dry-run / --limit / --batch-size. |
| `Features/ContentSignals/ContentSignalsService.py` | `ComputeSignals(LocalFilePath) -> Optional[ContentSignalsModel]`. Runs signalstats + PySceneDetect. Never raises. |
| `Features/ContentSignals/ContentSignalsRepository.py` | `WriteSignals(MediaFileId, Model)`, `GetSignals(MediaFileId) -> Optional[Model]`. Thin SQL wrapper. |
| `Features/ContentSignals/Models/ContentSignalsModel.py` | Plain dataclass: MotionFraction, SceneChangeRatePerMin, LumaVariance, ComputedAt. |
| `Features/MediaProbe/MediaProbeBusinessService.py` | After probe success: if `MotionFraction IS NULL`, call ContentSignalsService + persist via repository. Failure logged, never blocks. |
| `requirements.txt` | `scenedetect>=0.6.0` pinned. |

## Deviation from conventions

None. Mirrors existing single-responsibility verticals: dedicated `Features/X/` directory with its own service + repository + model + docs. Compute service is reusable in test harnesses (the encoder shootout could call it to characterize sources without going through the probe pipeline).

## Cross-Vertical Contract

This section locks the ContentSignals vertical's public surface. Other verticals interact ONLY through what is listed below.

### Columns the ContentSignals vertical WRITES

| Column | Written by |
|---|---|
| `MediaFiles.MotionFraction` | `ContentSignalsService.ComputeSignals` + persistence at the probe-pipeline call site |
| `MediaFiles.SceneChangeRatePerMin` | Same |
| `MediaFiles.LumaVariance` | Same |

### Columns the ContentSignals vertical READS from external tables

| Column | Read by | Owner |
|---|---|---|
| Source file at probe-time local path | `ContentSignalsService.ComputeSignals` | (filesystem; path translated by probe-pipeline caller per content-signals.C7) |
| `Workers.FFmpegPath` | `ContentSignalsService` shell-out to ffmpeg signalstats | Workers data accessor |

### Stable function entry points (cross-vertical callers)

| Class.method | External caller(s) |
|---|---|
| `ContentSignalsService.ComputeSignals(LocalFilePath: str) -> Optional[ContentSignalsModel]` | Probe-pipeline hook in MediaProbe vertical; ContentClassifier backfill scripts |

### HTTP API surface

None today. Operator views signals via `/SQLQueries` or future tile.

### What is EXPLICITLY NOT a contract

- The specific `ffmpeg signalstats` flags / PySceneDetect threshold values -- tunable internally
- The `ContentSignalsModel` field set (today: 3 fields; may grow)
- The exact threshold used to compute `MotionFraction` (integer_motion score cutoff) -- implementation detail
- Whether ContentSignals runs synchronously in the probe hook or asynchronously in a background job (today: synchronous; may change)
