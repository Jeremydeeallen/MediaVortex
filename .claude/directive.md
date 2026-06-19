# Current Directive

**Set:** 2026-06-19
**Status:** Active -- phase: IMPLEMENTING
**Slug:** audio-vertical-phase-1-completion

## Outcome

Close the audio vertical to honest 100% per the operator's bar:
mechanism + GUI-controllable + safe + library convergence path proven.
Compliance routing bug stays on the backlog (captured in IDEAS.md) --
this directive does NOT touch compliance routing. Sequence:
AudioFix JobProcessor -> H1 safety net -> H1 consolidated control
surface -> re-enable H1 -> VMAF data on 30 Rock for future tuning.

Durable design content lives in this directive doc until DELIVERING;
at close it promotes into:
- `Features/AudioNormalization/audio-normalization.feature.md` (AudioFix
  JobProcessor + H1 safety + control surface)
- `Features/FileScanning/file-scanning.feature.md` (Scanners
  orchestrator that H1 now lives under)
- new `Features/FileScanning/scanners.flow.md` (the multi-scanner
  daemon-cadence flow, cross-stage seams between scanners and their
  remediation outputs)

## Acceptance Criteria

**P1.** `AudioFix` JobProcessor exists at
`Features/TranscodeJob/Worker/AudioFixJobProcessor.py`. ffmpeg command
shape: `-c:v copy -c:a:N <emitter codec> <emitter filters> <emitter
metadata> <emitter dispositions>` -- video stream-copied, container
preserved, audio re-encoded through `AudioFilterEmitter`. Dispatched
by `ProcessTranscodeQueueService` when `ProcessingMode='AudioFix'`.
Live verified on at least one legacy `-mv.mp4` file: source preserved
to `.e2e_preservation/`, transcode runs, ffprobe of output confirms
video bit-identical to source (matching size or codec/dimensions), audio
streams now carry per-language `handler_name`, AchievedIntegratedLufs
within tolerance of -23, MediaFile audio fields updated.

**P2.** H1 safety net:
- `AudioVerticalHealthConfig.DryRun BOOLEAN` (new column on the
  SystemSettings-keyed flag pair we already have; concretely: new
  SystemSetting `AudioVerticalHealthDryRun` default 'false'). When
  `true`, `RunCycle` runs every Detect() but no Remediation.Apply(); it
  writes audit rows with `Notes='DRY_RUN: would have remediated N'`.
- `Tests/Contract/TestH1FixtureDryRun.py` exercises the orchestrator
  against a stub invariant + stub remediation, asserts:
  (a) DryRun=true never calls `Remediation.Apply`
  (b) audit row carries `DRY_RUN` Notes prefix
  (c) DryRun=false runs normally

**P3.** H1 consolidated under FileScanning's scan-loop orchestrator:
- New `Scanners` config table OR extended existing one (agent will
  report whether FileScanning already has a `Scanners`-shaped config).
  Columns: `ScannerName TEXT PRIMARY KEY, Enabled BOOL DEFAULT FALSE,
  IntervalSec INT, BatchSize INT, DryRun BOOL DEFAULT FALSE, LastRunAt
  TIMESTAMP, LastUpdated TIMESTAMP`. Seeded with two rows minimum:
  `'ContinuousScan'` and `'AudioVerticalHealth'`.
- `AudioVerticalHealthService` reads its row by name (db-is-authority
  fresh per cycle).
- `ContinuousScanService` follows suit if it isn't already.
- New `Templates/Scanners.html` rendered at `/Admin/Scanners` with a
  table: Name, Enabled toggle, Interval input, Batch input, DryRun
  toggle, LastRunAt, Save button per row. Big master "Pause all"
  button.

**P4.** Re-enable H1 with controls verified:
- Operator flips H1 row Enabled=true + DryRun=true via the new GUI.
- One cycle runs, audit table records `DRY_RUN` rows for the 6
  invariants without writes.
- Operator flips DryRun=false. Next cycle does real work.
- Verified live: invariant counts drop, audit table shows real
  Remediated values.

**P5.** VMAF on 30 Rock S01E01 (task #47 already in_progress):
- Source preserved to `.e2e_preservation/`.
- Queue + canary 720p with QualityTestRequired=true so VMAF runs.
- Result recorded in this directive's evidence block: VMAF score,
  source BPP, output BPP, file sizes.
- Numbers used to inform the Phase 2 compliance refactor's default
  thresholds (out of scope for this directive; just data capture).

**P6.** Promotions at DELIVERING:
- Durable content extracted into the three target docs above.
- Directive doc shrinks back to a thin status record per R14.

## Files

```
.claude/directive.md                                                                   -- EDIT: phase / progress / promotions
Features/TranscodeJob/Worker/AudioFixJobProcessor.py                                   -- CREATE (P1)
Features/TranscodeJob/ProcessTranscodeQueueService.py                                  -- EDIT: dispatch AudioFix mode (P1)
Features/AudioNormalization/SelfHealing/AudioVerticalHealthService.py                  -- EDIT: DryRun gating + Scanners config read (P2/P3)
Features/AudioNormalization/SelfHealing/AudioVerticalHealthComposition.py              -- EDIT: pass DryRun (P2)
Features/FileScanning/ScannersRepository.py                                            -- CREATE: shared scanners table reader/writer (P3)
Features/FileScanning/ScannersController.py                                            -- CREATE: GET / POST endpoints (P3)
Scripts/SQLScripts/CreateScannersConfig.py                                             -- CREATE: idempotent migration (P3)
Templates/Scanners.html                                                                -- CREATE: /Admin/Scanners page (P3)
Templates/_admin_subnav.html                                                           -- EDIT: add Scanners link
WebService/Main.py                                                                     -- EDIT: register ScannersController; route /Admin/Scanners
Tests/Contract/TestAudioFixJobProcessor.py                                             -- CREATE (P1)
Tests/Contract/TestH1FixtureDryRun.py                                                  -- CREATE (P2)
Tests/Contract/TestScannersRepository.py                                               -- CREATE (P3)
```

## Plan (checklist visible at every commit)

### Stage A -- context (parallel agents; no code yet)

- [ ] A1 Explore agent reports FileScanning orchestrator shape + ContinuousScanService control surface
- [ ] A2 Explore agent reports ProcessTranscodeQueueService dispatch pattern (RemuxJobProcessor as template)
- [ ] A3 Explore agent reports VMAF flow + how QualityTestRequired triggers measurement

### Stage B -- AudioFix JobProcessor (P1)

- [ ] B1 Create `AudioFixJobProcessor.py` (template = RemuxJobProcessor minus container swap + minus video re-encode)
- [ ] B2 Wire dispatch in `ProcessTranscodeQueueService` for `ProcessingMode='AudioFix'`
- [ ] B3 Contract test `TestAudioFixJobProcessor.py`
- [ ] B4 Live verify on one legacy `-mv.mp4` file: queue, claim, transcode, ffprobe matches expectations, MediaFile state correct
- [ ] B5 Commit + push

### Stage C -- H1 safety net (P2)

- [ ] C1 Add `AudioVerticalHealthDryRun` SystemSetting key, default `'false'`
- [ ] C2 `AudioVerticalHealthService.RunCycle` reads DryRun fresh; when true, calls Detect but never Remediation.Apply; audit row gets `DRY_RUN: would have remediated N` Notes
- [ ] C3 `TestH1FixtureDryRun.py`: stub invariant + stub remediation, three asserts
- [ ] C4 Commit + push

### Stage D -- Scanners config + controller (P3)

- [ ] D1 Migration `CreateScannersConfig.py`; seed `ContinuousScan` + `AudioVerticalHealth` rows
- [ ] D2 `ScannersRepository.py` with `Get(Name)` / `List()` / `Update(Name, ...)`
- [ ] D3 `ScannersController.py` with GET `/api/Scanners`, POST `/api/Scanners/<name>`, POST `/api/Scanners/PauseAll`
- [ ] D4 `Templates/Scanners.html` rendered at `/Admin/Scanners`
- [ ] D5 `_admin_subnav.html` gains the Scanners link
- [ ] D6 Register blueprint + route in `WebService/Main.py`
- [ ] D7 `TestScannersRepository.py`
- [ ] D8 Migration applied; live verify GET returns rows + POST round-trips
- [ ] D9 Commit + push

### Stage E -- H1 reads Scanners + ContinuousScan reads Scanners (P3 + P4)

- [ ] E1 `AudioVerticalHealthService` reads its Scanners row each cycle (Enabled / Interval / Batch / DryRun)
- [ ] E2 Delete the `AudioVerticalHealthEnabled` SystemSetting (Scanners table is now source of truth)
- [ ] E3 `ContinuousScanService` reads its Scanners row each cycle (preserve current default behavior on first run)
- [ ] E4 Commit + push

### Stage F -- live re-enable H1 (P4)

- [ ] F1 Operator instruction: flip `AudioVerticalHealth.Enabled=true` + `DryRun=true` via UI
- [ ] F2 One H1 cycle runs; audit table shows DRY_RUN rows for all 6 invariants, zero writes
- [ ] F3 Flip `DryRun=false`; next cycle does real remediation; invariant counts move
- [ ] F4 Snapshot post-state in evidence block

### Stage G -- VMAF on 30 Rock (P5)

- [ ] G1 Preserve `T:\Sources\30 Rock - S01E01 - Pilot Bluray-720p.mkv` source to `.e2e_preservation/`
- [ ] G2 Queue 30 Rock (MediaFile 2) with canary 720p; `QualityTestRequired=true`
- [ ] G3 Monitor + wait for completion
- [ ] G4 Record evidence: source BPP, output BPP, VMAF score, output size, attempt id
- [ ] G5 Commit evidence row only (no code change here)

### Stage H -- VERIFYING + DELIVERING

- [ ] H1 All P1-P5 evidence collected; transition Status to VERIFYING
- [ ] H2 Promotions populated; durable content migrated into target docs
- [ ] H3 Status to DELIVERING; hook validates `### Promotions` non-empty + directive doc size <= 110% of IMPLEMENTING snapshot
- [ ] H4 Close + push

## Status

### Evidence

(Populated as stages complete.)

### Promotions

[Populated at DELIVERING phase]
