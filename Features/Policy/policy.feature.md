# Policy

**Slug:** policy

## What It Does

Owns what a file should become. Policy is operator data with one home per fact: `StorageRoots` (default tier, default content class, genre source, review-before-replace), `GenreQualityTiers` (tier and class per genre), `TargetOverrides` (file or series tier), `Profiles` (one row per tier: label, quality-test switch, VMAF and held-frame acceptance), `LadderCells` (tier x class x source resolution x frame-rate class -> target resolution, kbps, ICQ), `FrameRateClasses`, `EncoderSettings` (encoder x tier knobs), `AudioPolicyTracks` (per audio policy). The SQL VIEW `MediaFileTargets` joins them with the file's facts into one row per `MediaFiles` row; `TargetResolver` reads that row and returns a frozen `Target` or `Undecided(reason)`. Compliance verticals, queue admission, the command composer, the disposition decider and the placement hand-off take `Target` as an argument and read no policy table. `EncoderSelector` maps a worker's capability flags to its encoder. `MovieGenreSyncService` fills `MediaFiles.Genres` from Radarr at the end of each scan. Pipeline position: `transcode.flow.md` D13, ST4-ST9.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | Resolve a file's target (internal; every recompute, admission, encode, disposition) | none | in-process | `Features/Policy/TargetResolver.Resolve(MediaFileId)` / `.ResolveMany(Ids)` -> `SELECT ... FROM MediaFileTargets` |
| W2 | Override a series' or a file's tier, see the resolved tier next to the control | `/Work/<bucket>` series dropdown; per-file control on `/Work` and `/Optimization` | `PUT /api/Policy/Override {StorageRootId, Scope, Key, QualityTier}`; `DELETE` same | `Features/Policy/TargetOverrideRepository.Upsert / Delete` -> `RecomputeForFiles` of the affected files |
| W3 | Edit a ladder cell | `/settings` Transcoding card, ladder grid per content class with a frame-rate-class tab | `PUT /api/Policy/LadderCells` | `Features/Policy/LadderCellRepository.Update` -> recompute of files in that cell |
| W4 | Edit an encoder's knobs for a tier | `/settings` Transcoding card, encoder settings grid per encoder | `PUT /api/Policy/EncoderSettings` | `Features/Policy/EncoderSettingsRepository.Update` (next encode reads it; no recompute needed) |
| W5 | Edit a tier's acceptance (label, quality test required, VMAF min/max, held-frame thresholds) | `/settings` Transcoding card, tier table | `PUT /api/Policy/Tiers` | `Features/Policy/TierAcceptanceRepository.Update` (next disposition reads it) |
| W6 | Edit a library's tier, class, genre source, review-before-replace; a genre's tier and class; frame-rate class boundaries | `/settings` Transcoding card, library table, genre table, frame-rate classes | `PUT /api/SystemSettings/LibraryTiers`, `PUT /api/SystemSettings/GenreTiers`, `PUT /api/Policy/FrameRateClasses` | `Features/Policy/LibraryPolicyRepository`, `GenreQualityTierRepository`, `FrameRateClassRepository` -> recompute of the affected library |

Rows W2-W6 are implemented by `target-policy-1d-gui`; W1 and the repositories by `target-policy-1a-tables` and `target-policy-1c-pipeline` (`ARCHITECTURE.md` `## Gap to Target`).

## Success Criteria

C1. **No stored target.** `MediaFiles` has no `AssignedProfile`, `AssignedProfileSource` or `KeepSource` column, nor does `MediaFilesArchive`; the production tree has no reference to them. Verify: `\d MediaFiles`; the grep in `transcode.flow.md` D13's program criteria returns 0.

C2. **One reader of policy.** Exactly one Python module per policy table reads it for a decision, and that module lives under `Features/Policy/`. Verify: `Tests/Contract/TestTargetAuthority.py` walks the tree for `FROM`/`JOIN` on each policy table outside `Features/Policy/` and finds none.

C3. **Judge and encode agree.** For any file, the tier the video ceiling is judged against equals the tier the encode command uses equals `MediaFileTargets.Tier`. An override changes both in one cascade. Verify: change a series override on `/Work`; `VideoCompliantReason` names the new tier and the next attempt's command carries that tier's `LadderCell` kbps, with no intermediate step.

C4. **Undecided is visible, not defaulted.** A file whose view row has a NULL input lands in `WorkBucket='Unclassified'` with the input named in a `<Dim>CompliantReason`; `AddJob` refuses it with that reason; no `Target` field is ever NULL. Verify: set a genre to two conflicting classes on a test file; the file appears on `/Work/Unclassified` with `ContentClassConflict`.

C5. **Every knob has one editor and one reader.** Every column of every policy table has a `/settings` (or `/Work`) control and a decision reader; the inventory's dead-column list is empty. Verify: `Tests/Contract/TestKnobInventory.py`.

C6. **Encoder knobs are rows.** The encode command for a worker is a pure function of `Target`, the `EncoderSettings(Encoder, Tier)` row and the label; no code dictionary overrides a knob. Verify: `grep -rn "NVENC_OVERRIDES\|QSV_OVERRIDES\|WorkerEncoderResolver\|CodecFlags" --include=*.py Features/ Core/` returns 0; golden argv test (`Tests/Contract/TestGoldenTvCommands.py`) byte-identical across phases.

C7. **Frame rate is part of the key.** Two files identical except for frame rate class resolve different `LadderCells` rows and different `TargetKbps`. Verify: `SELECT Tier, FrameRateClass, TargetKbps FROM MediaFileTargets WHERE MediaFileId IN (<30fps id>, <60fps id>)` shows two cells; the `high` cell is editable on `/settings`.

C8. **Policy edits take effect without restart.** A `/settings` ladder edit changes `VideoCompliantReason` on an affected file within one cascade; an encoder-settings edit shows in the next attempt's command. Verify: live on the farm server, one edit each, observed in SQL.

C9. **Compliance unchanged for TV and Movies.** The counts of `VideoCompliant` / `AudioCompliant` / `ContainerCompliant` per library equal the Phase 1a snapshot after every phase. Verify: `Tests/Contract/TestComplianceCountsUnchanged.py`.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | View -> resolver | `MediaFileTargets` (one row per `MediaFiles.Id`) | columns: `MediaFileId, StorageRootId, Tier INT, TierOrigin TEXT, ContentClass TEXT, ClassOrigin TEXT, FrameRateClass TEXT, SourceResolution TEXT, TargetResolution TEXT, TargetKbps INT, IcqQ INT NULL, QualityLabel TEXT, QualityTestRequired BOOL, VmafMin NUMERIC, VmafMax NUMERIC NULL, HeldFrameDetectionThreshold, HeldFrameP25Min, HeldFrameMeanMin, LiveActionP10Min NUMERIC, AudioPolicyId INT, OutputContainer TEXT, AcceptableContainersCsv TEXT, AcceptableAudioCodecsCsv TEXT, CeilingMultiplier NUMERIC, ReviewBeforeReplace BOOL, Undecided TEXT NULL` | `TargetResolver` builds `Target` only when `Undecided IS NULL`; every field non-optional | `TestTargetResolver` (fixture rows per origin and per missing input); `TestPipelineShape` asserts the view's CASE against `transcode.flow.md` D4 |
| S2 | Resolver -> verticals | `TargetResolver.ResolveMany(Ids)` inside `RecomputeForFiles` | `dict[MediaFileId -> Target | Undecided]` | `VideoVertical / AudioVertical / ContainerVertical .Evaluate(Facts, Target)` pure; `Undecided` -> NULL + reason | `TestComplianceCountsUnchanged`; per-vertical contract tests |
| S3 | Resolver -> composer | `TargetResolver.Resolve(Id)` + `EncoderSelector(Worker)` + `EncoderSettingsRepository.Get(Encoder, Tier)` | `Target`, `EncoderSettings` row, `Label` | `CommandComposer.Build(Facts, Target, EncoderSettings, Label)`; `VideoSlot` reads the row, `AudioSlot` the policy tracks, `ContainerSlot` `Target.OutputContainer` | `TestGoldenTvCommands` byte-identical argv |
| S4 | Resolver -> decider | `DispositionDispatcher` | `AttemptFacts` + `Target` | `PostTranscodeDispositionDecider.Decide` pure; table in `transcode.flow.md` ST7 | `TestPostTranscodeDisposition` table-driven |
| S5 | GUI -> policy tables | `/settings` and `/Work` controls (W2-W6) | JSON per route; one column family per control | repository UPSERT then `RecomputeForFiles` of affected files | round trip per type-distinct field (int, bool, numeric, text, NULL) on the farm server |
| S6 | Requeue -> override | `DispositionDispatcher` on `Requeue` | `TargetOverrides(file, Key=MediaFileId, QualityTier=Tier+1, SetBy='requeue:<AttemptId>')` | next `Resolve` returns the higher tier; `TierOrigin='file_override'` | `TestPostTranscodeDisposition` requeue case + one fleet smoke |

## Status

Target state (2026-11-27). Implementation lands by phase; the schedule and the gap per phase live in `ARCHITECTURE.md` `## Gap to Target`. Until `target-policy-1a-tables` ships, this vertical is `Features/Profiles/` (`Profiles.feature.md`, `profile-tier-ladder.feature.md`), which describes the running code.

### Files

```
Features/Policy/TargetResolver.py             -- view row -> Target | Undecided (W1)
Features/Policy/Target.py                     -- frozen dataclass, all fields non-optional
Features/Policy/EncoderSelector.py            -- Workers.nvenccapable / qsvcapable -> encoder
Features/Policy/LadderCellRepository.py       -- LadderCells (W3)
Features/Policy/EncoderSettingsRepository.py  -- EncoderSettings (W4)
Features/Policy/TierAcceptanceRepository.py   -- Profiles acceptance columns (W5)
Features/Policy/TargetOverrideRepository.py   -- TargetOverrides (W2, S6)
Features/Policy/LibraryPolicyRepository.py    -- StorageRoots tier/class/genre source/review flag (W6)
Features/Policy/GenreQualityTierRepository.py -- GenreQualityTiers (W6)
Features/Policy/FrameRateClassRepository.py   -- FrameRateClasses (W6)
Features/Policy/MovieGenreSyncService.py      -- Radarr genres -> MediaFiles.Genres (ingest.flow.md ST3)
Scripts/SQLScripts/AddTargetPolicyTables_2026_11_27.py -- tables + VIEW MediaFileTargets + data migration
```
