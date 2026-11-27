# Current Directive

**Set:** 2026-11-27
**Status:** Active -- phase: IMPLEMENTING
**Slug:** target-policy-1a-tables
**Replaces:** `directives/closed/2026-11-27-target-policy-architecture.md` (closed Success)

## Outcome

Phase 1a of the target-policy program (`Docs/superpowers/plans/2026-11-27-target-policy-program.md` "1a"). After this directive the safety net exists (one TV fixture's Transcode and AudioFix argv frozen as golden files and asserted through `CommandComposer.Build`; TV + Movies per-file compliance frozen and asserted), the policy tables and the `MediaFileTargets` view exist live and are seeded from today's values, `Features/Policy/` holds the `Target` dataclass, `TargetResolver`, `EncoderSelector`, one repository per policy table and the genre sync, `Features/Profiles/` no longer exists, the fleet deploy writes `Workers.nvenccapable` / `qsvcapable` from a probe on every host, and the server + fleet run the new code. Nothing consumes `Target` yet: every encode, verdict and claim is byte-for-byte what it was (golden tests prove it).

## Acceptance Criteria

1. **Golden argv.** `Tests/Contract/Golden/` holds the frozen TV fixture (MediaFile 751897 "Pokémon S20E154": the pre-transcode row for Transcode, the post-replace row for AudioFix, frozen ffprobe audio/subtitle streams, frozen context) and `tv-transcode.argv` / `tv-audiofix.argv`; `py -m pytest Tests/Contract/TestGoldenTvCommands.py` passes against the current code with the DB stubbed at the repository seam; each `.argv` equals the live `TranscodeAttempts.FfpmpegCommand` of attempts 104042 / 104043 after masking only `mediavortex_worker`, `mediavortex_commit`, `mediavortex_ts`.
2. **Compliance snapshot.** `Tests/Contract/Golden/compliance-counts.json` holds, for StorageRootIds 1 and 2, per-library counts per dimension and a per-file list `(Id, FileModificationTime, VideoCompliant, AudioCompliant, ContainerCompliant)`; `py -m pytest Tests/Contract/TestComplianceCountsUnchanged.py` asserts every file whose `FileModificationTime` is unchanged has unchanged verdicts, and reports (does not fail on) files the pipeline replaced or re-scanned. Green before the migration and green after it, same session.
3. **CodecFlags / CodecParameters inventoried.** `Docs/superpowers/audits/2026-11-26-knob-inventory.md` has a dated addendum listing both tables' columns, live rows, readers, and the fold rule into `EncoderSettings`; the migration implements that rule.
4. **Additive migration live and idempotent.** `Scripts/SQLScripts/AddTargetPolicyTables_2026_11_27.py` run twice: second run changes nothing. Live `\d` shows `TargetOverrides` (UNIQUE StorageRootId, Scope, Key; Scope CHECK series|file; QualityTier 1..5), `FrameRateClasses` (2 rows: standard 30, high 120), `EncoderSettings` (15 rows = 3 encoders x 5 tiers; UNIQUE Encoder, QualityTier), `LadderCells` (80 rows = 5 tiers x 2 classes x 4 source resolutions x 2 frame-rate classes; UNIQUE on the four), `Profiles` acceptance columns (`VmafMin`, `VmafMax`, `HeldFrameDetectionThreshold`, `HeldFrameP25Min`, `HeldFrameMeanMin`, `LiveActionP10Min`) populated on the five tier rows from today's gate values, `StorageRoots.ReviewBeforeReplace BOOL NOT NULL DEFAULT FALSE`, `ContainerComplianceRules.OutputContainer TEXT NOT NULL DEFAULT 'mp4'`, VIEW `MediaFileTargets` with exactly the `policy.feature.md` S1 column list. `SeriesProfiles` rows with a live tier profile became series overrides; `MediaFiles.AssignedProfile` rows with source `operator` / `manual_sql` became file overrides unless a series override already yields the same tier; counts recorded. `.claude/schema/snapshot.json` regenerated; `TestSchemaSnapshot` green.
5. **View resolves today's targets.** `SELECT ... FROM MediaFileTargets WHERE MediaFileId = 751897` returns Tier 1, `TierOrigin='library'`, `ContentClass='live_action'`, `FrameRateClass='standard'`, `SourceResolution='720p'`, `TargetResolution='720p'`, `TargetKbps=1000`, `VmafMin=90`, `VmafMax=96`, `Undecided IS NULL`; a Movies file with the `Animation` genre has `ClassOrigin='genre=Animation'`; every xxx file has `Undecided='Tier'`; every file with `FrameRate > 120` or NULL has `Undecided='FrameRateClass'`; a file under a migrated series override has `TierOrigin='series_override'`; `SELECT Undecided, COUNT(*) FROM MediaFileTargets GROUP BY 1` recorded in Verification and every TV/Movies reason is a data gap, not a view bug.
6. **Policy vertical exists, nothing else reads the new tables.** `Features/Policy/` holds `Target.py`, `TargetResolver.py`, `EncoderSelector.py`, `LadderCellRepository.py`, `EncoderSettingsRepository.py`, `TierAcceptanceRepository.py`, `TargetOverrideRepository.py`, `LibraryPolicyRepository.py`, `GenreQualityTierRepository.py`, `FrameRateClassRepository.py`, `MovieGenreSyncService.py` plus everything that was `Features/Profiles/`; `Features/Profiles/` does not exist; `grep -rn "Features.Profiles\|Features/Profiles" --include=*.py --include=*.md . ` (outside `.claude/directives/closed/` and `Docs/superpowers/`) = 0; `py -m pytest Tests/Contract/TestTargetAuthority.py Tests/Contract/TestTargetResolver.py` green: no `FROM`/`JOIN` on `TargetOverrides`, `FrameRateClasses`, `EncoderSettings`, `LadderCells`, `MediaFileTargets` outside `Features/Policy/`, `Scripts/SQLScripts/`, `Tests/`; the resolver returns a `Target` for 751897 equal to criterion 5 and `Undecided('Tier')` for an xxx file; `grep -rn "TargetResolver\|EncoderSelector" --include=*.py Features/ WorkerService/ WebService/ Repositories/ Core/` matches only `Features/Policy/`.
7. **Deploy probes capability.** `deploy/deploy-baremetal-worker.py` runs `Scripts/ReconcileNvencCapability.py` and `Scripts/ReconcileQsvCapability.py` against the host after the ffmpeg step; `py deploy/deploy-server.py` and `py deploy/deploy-fleet.py` complete on this commit; the deploy log shows both probes per host; `SELECT WorkerName, nvenccapable, qsvcapable FROM Workers WHERE Enabled` shows dot true/false, wakko false/true, mediavortex-workers false/false, I9 unchanged; `Workers.Version` = this sha on every Enabled Linux worker and `GET /api/Version` on the server.
8. **Nothing moved.** Criteria 1 and 2 green after the deploy; `py -m pytest Tests/Contract/` has no new failures against the pre-directive run; `TestFailLoud` baseline for `Features/Policy/` does not exceed the `Features/Profiles/` baseline it inherits; `ARCHITECTURE.md` `## Gap to Target` row for `target-policy-1a-tables` deleted; `policy.feature.md` Status names W1 as implemented and the Files block matches the tree; plan 1a steps ticked; handoff memory "Phase 1a done".

## Call-Graph Audit

- **Signal 1 (flow docs):** `transcode.flow.md` + `ingest.flow.md` (meet at ST4); `deploy/worker-deploy-baremetal.flow.md` for the probe step. No pair describes one operation.
- **Signal 2 (orchestration mode branch):** unchanged by this phase and inherited, named: `GetTranscodingSettings` `Codec == 'av1'` override branch; `VideoVertical` tier-vs-profile branch on `DefaultQualityTier IS NULL`; claim SQL `p.codec` gates. Deleted in 1b/1c/2. The view introduces no branch: a NULL input becomes `Undecided(<name>)` data.
- **Signal 3 (sparse columns):** `ProfileThresholds.TargetKbps` on downscaling source rows (tier 1 live_action 1080p/2160p = 900) is dead: every consumer reads the encode row (the 720p row, 1000). `LadderCells.TargetKbps` is seeded from the encode row, so the dead value does not migrate. `AssignedProfileSource` 11 values; only `operator` / `manual_sql` are intent, the rest derived (dropped at Phase 2).
- **Signal 5 (config drives graph shape):** `StorageRoots.DefaultQualityTier IS NULL` removes the tier path today (xxx). In the view it is `Undecided('Tier')` data. The NOT NULL tightening is destructive-order and waits for Phase 2+ (Constraints).
- **OOS items:** all categorized below.

## Out of Scope

- (b) Consumers of `Target`: verticals (1b), admission / composer / claim / disposition (1c), GUI (1d). Named debt until then: two homes for tier/kbps (old readers + the view) with the view unread.
- (b) Deletion of `Features/ContentClassifier/`, `EffectiveProfileResolver`, `EncoderKnobRepository`, `WorkerEncoderResolver`, `TierLadderRepository`, `SeriesProfiles`, `CodecFlags` readers, `AssignedProfile` columns: Phase 2, after a fleet deploy on consumer code.
- (b) Setting xxx `DefaultQualityTier = 3` and the NOT NULL on `StorageRoots.DefaultQualityTier` / `DefaultContentClass`: deferred to the phase that ships `Hold` (Phase 4) or later; see Decisions Made. The plan is amended in this directive.
- (b) `Profiles` acceptance columns stay nullable; NOT NULL + `PostTranscodeGateConfig` drop in Phase 4.
- (b) 276 files with `FrameRate > 120` (251 at 90000 fps) and 7 with NULL: a probe fact defect, filed as a bug; they resolve `Undecided('FrameRateClass')`, which is the correct visible state.
- (b) The `folder` audio scope (0 rows) and `AudioPolicyTracks`: Phase 3.

## Constraints

- Additive only: no DROP, rename, NOT NULL tightening or CHECK on an existing column. Every statement idempotent (R11: `IF NOT EXISTS`, `ON CONFLICT`). `DROP VIEW IF EXISTS` + `CREATE VIEW` is the one sanctioned drop.
- Golden tests are written and green BEFORE the migration file exists; the compliance snapshot is taken BEFORE the migration runs and checked after, same session, with workers draining nothing in between that the check cannot attribute.
- Seed literals cite their source (R2): `WorkerEncoderResolver.py` for the NVENC/QSV dicts, `profile-tier-ladder.feature.md` C6 for `QsvExtBrc=1` / `QsvLookaheadDepth=8`, the knob-inventory addendum for the frame-rate boundaries, the x1.5 `high` seed and the libsvtav1 fold. Ladder and acceptance values are copied by `INSERT ... SELECT`, never retyped.
- The rename `Features/Profiles` -> `Features/Policy` is one commit: `git mv` + every import + every doc path. `# see profiles.*` / `# see profile-tier-ladder.*` anchors keep their slugs (slug = filename).
- Only `Features/Policy/` may hold SQL against the new tables or the view. Tests read the view through `TargetResolver` or through a test-owned connection that is rolled back.
- No production value changes for testing; `TestTargetResolver` fixture rows live in a rolled-back transaction or are read-only against rows that already exist.
- Smoke/deploy: drain is in the deploy scripts; the fleet script is zero-parameter; server release first, fleet second.

## Escalation Defaults

- Spec vs. live data disagreement: live data wins for seeds (the goal is byte-identical behaviour); the disagreement is recorded in Decisions Made.
- A golden test that fails after a change: the change is wrong, never the fixture.
- Risk tolerance: low. Nothing consumes the view; the only live behaviour change is the deploy itself.

## Engineering Calls Already Made

- Golden argv "byte-identical" = identical after masking the three provenance values that encode the run (worker, commit, timestamp); the mask is applied to both sides by the test.
- Compliance snapshot is per-file keyed on `FileModificationTime`: a migration changes verdicts without touching the file; the pipeline changes verdicts by replacing or rescanning it (mtime moves). Aggregate counts are stored for reading, per-file rows for asserting.
- `LadderCells.TargetKbps` for a downscaling cell is the kbps at `TargetResolution` (today's encode row), so the one cell carries what the encoder and the ceiling both use.
- `EncoderSettings` gains `Crf INT NULL` and `FilmGrain INT NULL` (libsvtav1 knobs the SVT strategy emits) per the fold rule; `Preset` is TEXT so `p7`/`1`/`6` all fit.
- `Target.IcqQ` and `Target.VmafMax` are `Optional` because NULL is a value there (no ICQ, no ceiling), not a default; every other field is required and the resolver returns `Undecided` instead of a partial `Target`.
- Capability probe runs in `deploy-baremetal-worker.py` after the ffmpeg step (a host property, once per host) with `--worker-prefix <friendly>-worker`; the restart lives in `deploy-worker.py` and is not where host facts belong.
- `LibraryDefaultTierRepository` is renamed `LibraryPolicyRepository` in the move (policy.feature.md Files); `MovieGenreSyncService` moves into `Features/Policy/` keeping its `ContentClassifierService` call until Phase 2 deletes it.

## Status

### Plan

1. Pre-directive baseline: `py -m pytest Tests/Contract/ -q` result saved to the scratchpad; stack push; bug filed for the 90000-fps probe values.
2. Golden fixture + `TestGoldenTvCommands.py` (criterion 1) green.
3. `Scripts/Golden/SnapshotCompliance.py --write` + `TestComplianceCountsUnchanged.py` (criterion 2) green.
4. Knob-inventory addendum (criterion 3).
5. Migration script; run; run again; snapshot regenerate; `TestSchemaSnapshot`; view checks (criteria 4, 5); criterion 2 re-run.
6. `Features/Policy/` modules + rename + import sweep + `TestTargetAuthority` + `TestTargetResolver` (criterion 6); golden + snapshot re-run; full contract suite.
7. Deploy probe step; commit + push; `deploy-server.py`; `deploy-fleet.py`; Workers check (criterion 7).
8. Docs: plan ticks + amendment, ARCHITECTURE gap row, policy.feature.md Status, classifier.feature.md path, Promotions; VERIFYING evidence; DELIVERING; close; handoff memory; clear line.

### Files

```
Tests/Contract/Golden/tv-mediafile-transcode.json          -- CREATE: frozen pre-transcode MediaFile row (archive)
Tests/Contract/Golden/tv-mediafile-audiofix.json           -- CREATE: frozen post-replace MediaFile row
Tests/Contract/Golden/tv-streams.json                      -- CREATE: frozen ffprobe audio + subtitle streams
Tests/Contract/Golden/tv-context.json                      -- CREATE: frozen ProfileSettings / rules / policy / premix values
Tests/Contract/Golden/tv-transcode.argv                    -- CREATE: expected Transcode command (masked)
Tests/Contract/Golden/tv-audiofix.argv                     -- CREATE: expected AudioFix command (masked)
Tests/Contract/Golden/compliance-counts.json               -- CREATE: per-library counts + per-file verdicts (roots 1, 2)
Tests/Contract/TestGoldenTvCommands.py                     -- CREATE: criterion 1
Tests/Contract/TestComplianceCountsUnchanged.py            -- CREATE: criterion 2
Tests/Contract/TestTargetAuthority.py                      -- CREATE: criterion 6 tree walk
Tests/Contract/TestTargetResolver.py                       -- CREATE: criterion 6 resolver
Scripts/Golden/SnapshotCompliance.py                       -- CREATE: writes compliance-counts.json
Scripts/SQLScripts/AddTargetPolicyTables_2026_11_27.py     -- CREATE: criterion 4
Docs/superpowers/audits/2026-11-26-knob-inventory.md       -- EDIT: criterion 3 addendum
Features/Policy/Target.py                                  -- CREATE
Features/Policy/TargetResolver.py                          -- CREATE
Features/Policy/EncoderSelector.py                         -- CREATE
Features/Policy/LadderCellRepository.py                    -- CREATE
Features/Policy/EncoderSettingsRepository.py               -- CREATE
Features/Policy/TierAcceptanceRepository.py                -- CREATE
Features/Policy/TargetOverrideRepository.py                -- CREATE
Features/Policy/FrameRateClassRepository.py                -- CREATE
Features/Policy/LibraryPolicyRepository.py                 -- MOVE+RENAME: from Features/Profiles/LibraryDefaultTierRepository.py
Features/Policy/MovieGenreSyncService.py                   -- MOVE: from Features/ContentClassifier/
Features/Policy/**                                         -- MOVE: every Features/Profiles/* file and doc (git mv)
<every importer of Features.Profiles / LibraryDefaultTierRepository / MovieGenreSyncService>  -- EDIT: import path
deploy/deploy-baremetal-worker.py                          -- EDIT: StepReconcileCapabilities
Docs/superpowers/plans/2026-11-27-target-policy-program.md -- EDIT: 1a ticks; xxx tier set moves to Phase 4/6
ARCHITECTURE.md                                            -- EDIT: Gap to Target row removed
Features/Policy/policy.feature.md                          -- EDIT: Status (W1 implemented), Files
Features/ContentClassifier/classifier.feature.md           -- EDIT: genre sync path
```

### R13 overrides

- (none: no new feature/flow doc; `policy.feature.md` moves with `git mv`)

### R18 overrides

- (none)

### Seams added or changed

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| policy.S1 view -> resolver | `MediaFileTargets` | S1 column list | `TargetResolver` builds `Target` only when `Undecided IS NULL` | `TestTargetResolver` (criterion 6) + SQL (criterion 5) |
| Golden fixture -> composer | `Tests/Contract/Golden/*.json` | `MediaFile` attrs, `Context` dict, stubbed `AudioSlot` deps | `CommandComposer.Build(MediaFile, Job, Context)` | `TestGoldenTvCommands` |
| Snapshot -> check | `compliance-counts.json` | `{Counts, Files:[Id, Mtime, V, A, C]}` | `TestComplianceCountsUnchanged` | run before + after migration |
| Deploy -> Workers flags | `deploy-baremetal-worker.py` probe step | `UPDATE Workers SET nvenccapable/qsvcapable` via the two scripts | `EncoderSelector` (1c) | criterion 7 SQL |
| Migration -> policy tables | `AddTargetPolicyTables_2026_11_27.py` | tables + seeds + view | repositories in `Features/Policy/` | criterion 4 counts; second run no-op |

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| W1 implemented; Files block = tree; `TargetResolver` / `Target` semantics (Optional only where NULL is a value) | `Features/Policy/policy.feature.md` | TBD |
| Capability probe as a deploy step | `deploy/worker-deploy-baremetal.flow.md` ST3 row | TBD |
| Genre sync lives in Policy | `Features/ContentClassifier/classifier.feature.md`, `ingest.flow.md` (already names it) | TBD |
| Gap row removed | `ARCHITECTURE.md` `## Gap to Target` | TBD |

### Verification

(filled at VERIFYING)

### Decisions Made

- xxx `DefaultQualityTier` stays NULL in this phase. Setting it to 3 today would make `VideoVertical` judge 4,900 xxx files against the tier-3 ceiling on the next recompute, queue them, and the two Online transcode workers would REPLACE them (BUG-0125: `KeepSource` is dead, `Hold` does not exist until Phase 4). The view's `Undecided('Tier')` is the correct state until `Hold` ships; the plan's Phase 1a item and Phase 6 "set by Phase 1 migration" are amended to "set at the start of Phase 6, after Phase 4".
- Phase 1a does the mechanical module rename with `git mv` + a scripted import rewrite (one commit); behaviour edits go through the editor tools with their doc prereads.
