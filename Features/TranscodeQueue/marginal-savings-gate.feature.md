# Feature: Marginal-Savings Gate (Queue Admission)

## What It Does

Replaces the "source resolution must be strictly greater than target resolution" gate at queue-population time with a savings-based gate. A file is admitted to the transcode queue when its **estimated bytes saved** exceed an operator-configurable threshold, regardless of whether the source and target resolutions match.

This unblocks **compression-only re-encodes** (720p source -> 720p output with a slower preset / lower CRF) which were previously blocked by the strict-greater-than rule, while preventing **marginal-savings transcodes** (already-efficient files) from burning worker CPU for negligible gain.

The threshold and the CRF-to-bitrate estimates are stored as normalized rows in the database so an operator can tune them from a GUI without code changes.

## Concern

Operator dogfood (2026-05-10). Operator wanted to use `AV1 P4 FG6 >720p` to compression-only re-encode 720p sources, but `ShouldSkipDueToResolution` blocks every same-resolution file as `comparison <= 0`. The flow doc (`transcode.flow.md` Stage 4) claims a "Pre-flight benefit gate" exists, but the implementation only feeds the `IsCompliant` cascade -- the queue-admission path has no savings check. CRF-only profiles (`VideoBitrateKbps=0`) silently bypass the existing bitrate-based estimate entirely.

## Success Criteria

### A. Gate behavior

1. A queue-admission attempt where the source resolution **equals** the target resolution and the estimated savings is greater than or equal to `SystemSettings('MinTranscodeSavingsMB')` is **admitted**. Verifiable: assign a CRF profile whose target resolution matches the source resolution to a high-bitrate file, run populate, observe a `TranscodeQueue` row created with the file's `MediaFileId` and `Mode='Transcode'`.

2. A queue-admission attempt where the source resolution is **less than** the target resolution (upscale) is **blocked** regardless of estimated savings. Verifiable: assign a profile that targets `1080p` to a `480p` file, run populate, observe no `TranscodeQueue` row created and a log entry naming the source/target resolutions.

3. A queue-admission attempt where the estimated savings is **less than** `SystemSettings('MinTranscodeSavingsMB')` is **blocked** with reason `MarginalSavings`. Verifiable: pick a file whose source size is small enough that bitrate-based estimation projects savings below the configured threshold, run populate, observe no queue row and a log entry that names the source MB, target MB, savings MB, and threshold MB.

4. A queue-admission attempt where the source resolution is **greater than** the target resolution and savings are sufficient is **admitted as `Mode='Transcode'`**. Verifiable: 1080p source + `>480p` profile, populate, observe queue row with `Mode='Transcode'`.

### B. Estimation strategy

5. When the matching `ProfileThresholds.VideoBitrateKbps` is **non-zero**, the savings estimate uses the bitrate formula `target_size_mb = ((video_kbps + audio_kbps) * duration_min * 60) / (8 * 1024)` (already documented in `queue-priority.feature.md`). Verifiable: a file with known size and duration assigned to a fixed-bitrate profile gets a queue row when its `SizeMB - target_size_mb >= MinTranscodeSavingsMB`.

6. When the matching `ProfileThresholds.VideoBitrateKbps` is **zero** (CRF-only profile), the savings estimate looks up the expected average bitrate from the new `CrfBitrateEstimates` table keyed on `(Codec, TargetResolution, CRF)`. Verifiable: a CRF-25 `libsvtav1 >720p` profile applied to a 720p source produces a queue row only when `SizeMB - (estimated_kbps_from_table * duration_min * 60 / (8 * 1024)) >= MinTranscodeSavingsMB`.

7. When **no `CrfBitrateEstimates` row** matches `(Codec, Resolution, CRF)` and the profile is CRF-only, the gate **fails open** (admits the file) and logs a `WARNING` naming the missing key. The operator-tunable estimate table must not silently turn into a hard block when a row is missing. Verifiable: insert a queue-population request that targets a CRF/codec combination not present in `CrfBitrateEstimates`, observe the file admitted with a single `MissingCrfBitrateEstimate` warning per missing key per populate run.

### C. Database schema (data-driven configuration -- no SystemSettings KV)

8. A new table `CrfBitrateEstimates` exists with columns `Id BIGSERIAL PRIMARY KEY, Codec TEXT NOT NULL, Resolution TEXT NOT NULL, Crf INTEGER NOT NULL, EstimatedKbps INTEGER NOT NULL, LastUpdated TIMESTAMP DEFAULT NOW(), Source TEXT` and a `UNIQUE(Codec, Resolution, Crf)` constraint. The `Source` column records whether the row was seeded by migration, recomputed from observed transcodes, or set by an operator. Verifiable: `\d CrfBitrateEstimates` shows the columns and constraint.

9. A new table `QueueAdmissionConfig` exists as a single-row scalar-config table with properly-typed columns: `Id INT PRIMARY KEY DEFAULT 1, MinTranscodeSavingsMB INT NOT NULL DEFAULT 150, MissingEstimatePolicy TEXT NOT NULL DEFAULT 'admit', LastUpdated TIMESTAMP DEFAULT NOW(), CHECK (Id = 1)`. The `Id=1` check enforces single-row semantics; future scalar gate knobs are added as new columns rather than new rows. **The threshold is NOT stored in the legacy `SystemSettings` key-value table** -- this feature uses dedicated normalized tables. Verifiable: `\d QueueAdmissionConfig` shows the typed columns; `INSERT INTO QueueAdmissionConfig (Id, MinTranscodeSavingsMB) VALUES (2, 100)` fails the CHECK constraint.

10. Initial `CrfBitrateEstimates` seed rows are populated from observed `TranscodeAttempts` history: for each `(Codec, TargetResolution, CRF)` triple with at least 10 successful transcodes in `TranscodeAttempts`, the seed row's `EstimatedKbps` equals `AVG((NewSizeBytes * 8 / 1024) / (DurationMinutes * 60))` rounded to integer. Verifiable: query `SELECT Codec, Resolution, Crf, EstimatedKbps, Source FROM CrfBitrateEstimates WHERE Source='HistoricalSeed' ORDER BY Resolution, Crf` after migration; row count matches the distinct triples in the source query.

11. A new table `CodecCompatibility` exists with columns `Id BIGSERIAL PRIMARY KEY, Kind TEXT NOT NULL, Name TEXT NOT NULL, IsAcceptable BOOLEAN NOT NULL DEFAULT true, Description TEXT, LastUpdated TIMESTAMP DEFAULT NOW(), Source TEXT` and a `UNIQUE(Kind, Name)` constraint. `Kind` is one of `('VideoCodec', 'AudioCodecMp4', 'Container')`. This replaces the hardcoded `COMPATIBLE_CONTAINERS`, `ACCEPTABLE_VIDEO_CODECS`, `MP4_COMPATIBLE_AUDIO_CODECS` class constants. Verifiable: `\d CodecCompatibility` shows the schema; the table has at least the seeded rows for the three Kinds.

12. The migration seeds `CodecCompatibility` with the values currently hardcoded in the class constants: `Container` rows `{mp4, mov, m4v}` (all `IsAcceptable=true`); `VideoCodec` rows `{h264, hevc, av1}` (all `IsAcceptable=true`); `AudioCodecMp4` rows `{aac, ac3, eac3, mp3}` (all `IsAcceptable=true`). Each row has `Source='InitialSeed'`. Verifiable: `SELECT Kind, COUNT(*) FROM CodecCompatibility GROUP BY Kind` returns the expected counts (3 / 3 / 4).

### D. GUI display (single "Queue Tuning" card on /settings)

13. The `/settings` page contains a "Queue Tuning" card. Inside the card, the `CrfBitrateEstimates` rows are listed in an inline editable table with columns `Codec`, `Resolution`, `CRF`, `Estimated kbps`, `Source`, `Last updated`. Each row is editable; saving an edit updates the DB and stamps `Source='OperatorOverride'`. Verifiable: change a value via the UI, refresh the page, observe the new value persisted with `Source='OperatorOverride'`.

14. The same "Queue Tuning" card exposes `MinTranscodeSavingsMB` and `MissingEstimatePolicy` as editable controls bound to the single `QueueAdmissionConfig` row. Saving an edit updates the table and is read fresh by the next queue-population call. Verifiable: change the threshold via the UI, observe the next populate call use the new value.

15. The same "Queue Tuning" card displays the three `CodecCompatibility` lists (Containers, Video codecs, Audio codecs for MP4) as editable toggles per row plus an "Add new" affordance. Saving an edit updates the table and stamps `Source='OperatorOverride'`. Verifiable: toggle `mp4` to `IsAcceptable=false`, refresh, run populate, observe MP4-source files routed to `Mode='Transcode'` (because container compatibility now fails) instead of `Mode='Remux'`.

### E. Observability

16. Every queue-population run logs a single rolled-up `INFO` summary: `"Marginal-savings gate: <admitted> admitted, <blocked> blocked (Marginal: <n>, Upscale: <n>, MissingEstimate: <n>)"`. Verifiable: run populate with mixed inputs, find the summary line in `Logs.Message` filtered to that run.

## Status

**NOT IMPLEMENTED** -- doc-first feature, awaiting operator approval.

### Progress

- [x] 1. Read existing flow + feature docs (`transcode.flow.md` Stage 4, `TranscodeQueue.feature.md`)
- [x] 2. Identify the gap: `ShouldSkipDueToResolution` is too strict; `_EvaluateCompliance` savings logic is not wired into queue admission; `MIN_SAVINGS_MB` is hardcoded; CRF-only profiles bypass the savings estimate
- [x] 3. Draft this feature doc
- [x] 4. Update `transcode.flow.md` Stage 4 to describe the new gate (this commit)
- [ ] 5. Operator approval of criteria 1-13
- [ ] 6. SQL migration `Scripts/SQLScripts/AddQueueAdmissionTables.py` (criteria 8, 9, 10, 11, 12) -- creates THREE tables (`CrfBitrateEstimates`, `QueueAdmissionConfig`, `CodecCompatibility`); inserts `QueueAdmissionConfig.Id=1` default row; seeds `CodecCompatibility` from the existing class constants; computes `CrfBitrateEstimates` seed rows from `TranscodeAttempts` averages
- [ ] 7. Repository helpers: `CrfBitrateEstimateRepository.GetEstimatedKbps(Codec, Resolution, Crf) -> Optional[int]`; `QueueAdmissionConfigRepository.Get() -> QueueAdmissionConfigModel`; `CodecCompatibilityRepository.GetAcceptableSet(Kind) -> set` (Kind in {'VideoCodec','AudioCodecMp4','Container'}). All read-fresh, no cache.
- [ ] 8. Helper `EstimateTargetSizeMB(MediaFile, ProfileSettings)` -- branches on `VideoBitrateKbps > 0` (criterion 5) vs CRF lookup (criterion 6) vs `MissingEstimatePolicy` (criterion 7)
- [ ] 9. Replace `ShouldSkipDueToResolution` with `EvaluateQueueAdmission(MediaFile, ProfileSettings) -> Tuple[bool, str]` returning `(True, reason)` for blocks. Block reasons: `Upscale`, `MarginalSavings`, `MissingProfile`. Same-resolution + sufficient-savings is **admitted**.
- [ ] 10. Replace the class constants `COMPATIBLE_CONTAINERS`, `ACCEPTABLE_VIDEO_CODECS`, `MP4_COMPATIBLE_AUDIO_CODECS` with calls into `CodecCompatibilityRepository.GetAcceptableSet(...)`. Delete the constants. `_EvaluateCompliance` and any other callers updated.
- [ ] 11. Replace any `self.DatabaseManager.<...>` calls inside the new gate code (`EvaluateQueueAdmission`, `EstimateTargetSizeMB`, replaced compliance branches) with `self.Repository.<...>` calls -- vertical-slice cleanup limited to the touched code path.
- [ ] 12. Wire the new gate into the four queue-admission paths in `transcode.flow.md` Stage 4 (PopulateQueue, AddJob, QueueByFolder, AddSuggestionsToQueue)
- [ ] 13. Rolled-up `INFO` summary log line at end of each populate run (criterion 16)
- [ ] 14. New "Queue Tuning" card on `/settings` page: scalar controls for `MinTranscodeSavingsMB` + `MissingEstimatePolicy` bound to `QueueAdmissionConfig`; inline table editor for `CrfBitrateEstimates`; toggleable lists for `CodecCompatibility` (criteria 13, 14, 15). API endpoints under existing `/api/SystemSettings/...` namespace.
- [ ] 15. Smoke test: assign `AV1 P4 FG6 >720p` to a known 720p file > 400 MB, populate, observe queue row created with `Mode='Transcode'`. Then UPDATE `QueueAdmissionConfig.MinTranscodeSavingsMB=500` and re-populate the same file at a smaller size, observe block with `Reason='MarginalSavings'`.

NEXT: operator approval. Then implement step 6 (schema + seed) first since downstream depends on the tables existing.

## Scope

```
Features/TranscodeQueue/QueueManagementBusinessService.py        -- new EvaluateQueueAdmission, retire ShouldSkipDueToResolution, replace class constants with repo lookups
Features/TranscodeQueue/CrfBitrateEstimateRepository.py          -- NEW, repository for CrfBitrateEstimates
Features/TranscodeQueue/Models/CrfBitrateEstimateModel.py        -- NEW
Features/TranscodeQueue/QueueAdmissionConfigRepository.py        -- NEW, repository for the single-row scalar-config table
Features/TranscodeQueue/Models/QueueAdmissionConfigModel.py      -- NEW
Features/TranscodeQueue/CodecCompatibilityRepository.py          -- NEW, repository for the Kind/Name/IsAcceptable lookup
Features/TranscodeQueue/Models/CodecCompatibilityModel.py        -- NEW
Features/SystemSettings/SystemSettingsController.py              -- new endpoints for the editor (lives under existing /settings page surface)
Features/SystemSettings/SystemSettingsViewModel.py               -- editor view-model methods
Templates/Settings.html                                          -- new "Queue Tuning" card
Scripts/SQLScripts/AddQueueAdmissionTables.py                    -- NEW, idempotent migration + seed (creates THREE tables)
transcode.flow.md                                                -- Stage 4 rewrite
Features/TranscodeQueue/marginal-savings-gate.feature.md         -- this file
```

## Files

| File | Role |
|------|------|
| `Scripts/SQLScripts/AddQueueAdmissionTables.py` | Idempotent migration: create `CrfBitrateEstimates`, `QueueAdmissionConfig`, `CodecCompatibility` tables; insert `QueueAdmissionConfig.Id=1` default row; seed `CodecCompatibility` from current class constants; compute `CrfBitrateEstimates` seed rows from observed `TranscodeAttempts` averages. |
| `Features/TranscodeQueue/Models/CrfBitrateEstimateModel.py` | Plain dataclass. Fields: Id, Codec, Resolution, Crf, EstimatedKbps, LastUpdated, Source. |
| `Features/TranscodeQueue/Models/QueueAdmissionConfigModel.py` | Plain dataclass. Fields: Id, MinTranscodeSavingsMB, MissingEstimatePolicy, LastUpdated. |
| `Features/TranscodeQueue/Models/CodecCompatibilityModel.py` | Plain dataclass. Fields: Id, Kind, Name, IsAcceptable, Description, LastUpdated, Source. |
| `Features/TranscodeQueue/CrfBitrateEstimateRepository.py` | `GetEstimatedKbps(Codec, Resolution, Crf) -> Optional[int]`, `GetAll() -> List`, `Upsert(model)`. No caching. |
| `Features/TranscodeQueue/QueueAdmissionConfigRepository.py` | `Get() -> QueueAdmissionConfigModel`, `Update(MinTranscodeSavingsMB, MissingEstimatePolicy)`. No caching. |
| `Features/TranscodeQueue/CodecCompatibilityRepository.py` | `GetAcceptableSet(Kind) -> set[str]`, `GetAll() -> List`, `Upsert(model)`. No caching. |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | New `EstimateTargetSizeMB`, `EvaluateQueueAdmission`. Class constants `COMPATIBLE_CONTAINERS` / `ACCEPTABLE_VIDEO_CODECS` / `MP4_COMPATIBLE_AUDIO_CODECS` deleted. `_EvaluateCompliance` reads from `CodecCompatibilityRepository`. `self.DatabaseManager.<...>` calls inside the touched paths replaced with `self.Repository.<...>`. The four queue-admission entry paths consult the new evaluator. |
| `Features/SystemSettings/SystemSettingsController.py` | New endpoints: `GET/PUT /api/QueueAdmissionConfig`, `GET /api/CrfBitrateEstimates`, `PUT /api/CrfBitrateEstimates/<id>`, `GET /api/CodecCompatibility`, `PUT /api/CodecCompatibility/<id>`. |
| `Features/SystemSettings/SystemSettingsViewModel.py` | Editor view-model methods, stamps `Source='OperatorOverride'` on edits. |
| `Templates/Settings.html` | New "Queue Tuning" card: scalar controls for `MinTranscodeSavingsMB` + `MissingEstimatePolicy`; inline table editor for `CrfBitrateEstimates`; toggleable lists for `CodecCompatibility`. |
| `transcode.flow.md` | Stage 4 rewrite reflecting the new gate. |

## Deviation from conventions

None. All criteria are externally verifiable (SQL queries, log-line presence, UI inspection, queue-row presence/absence). No criterion references implementation details that would break under a rewrite. The data-driven design (table for estimates, SystemSetting for threshold) makes every behavior tunable from outside the code.
