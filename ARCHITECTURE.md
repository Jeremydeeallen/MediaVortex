# MediaVortex Architecture

**Purpose:** Defines DONE. When code matches this document AND `## Gap to Target` is empty, MediaVortex is done. Every architectural decision lands here in the same commit as the work that surfaced it.

**Not here (lives elsewhere):** DB schema, per-vertical Cross-Vertical Contracts (`*.feature.md`), pipeline detail (`*.flow.md`), KNOWN-ISSUES, test strategy, deployment, terminology (`GLOSSARY.md`).

## The System in One Paragraph

Self-hosted media library transcoder. Discovery builds `MediaFiles` rows. Three domain verticals each answer ONE compliance question; a GENERATED column derives `WorkBucket`. Queue populates per-worker jobs. Execution runs FFmpeg; verification confirms via VMAF or checksum; swap installs. Two services: WebService (Flask :5000) and WorkerService (capability-flagged). PostgreSQL is the only data store.

## Topology

| Component | Role |
|---|---|
| WebService | Flask on :5000. No transcoding work. |
| WorkerService | Unified worker. Capabilities per row in `Workers` (`TranscodeEnabled` / `QualityTestEnabled` / `ScanEnabled`). |
| PostgreSQL 16 | Single source of truth. LXC CT 203. No boot-cached config (`db-is-authority`). |
| FFmpeg / FFprobe | Per-worker binaries. |
| Larry LXC 218 | Bare-metal Linux host, 4 systemd worker instances. |
| I9 | Dev workstation; reads source tree directly on restart. |

## Job Types

Three FFmpeg-driven job types map to three worker capability flags. One flow doc per pipeline shape.

| Job type | Work | Capability | Flow doc |
|---|---|---|---|
| Transcode | Run FFmpeg to produce new file (re-encode or stream-copy). Verify. Replace source. Three job labels (`Transcode` / `Remux` / `AudioFix`); the label decides the command (`transcode.flow.md` D2). | `TranscodeEnabled` | `transcode.flow.md` |
| QualityTest | Re-run VMAF or checksum against existing attempt. No new encode. | `QualityTestEnabled` | `Features/QualityTesting/quality-test.flow.md` |
| Scan | Walk storage roots. `ffprobe` only. | `ScanEnabled` | `Features/FileScanning/FileScanning.flow.md` |

**Rule:** new job type requires distinct capability flag. Otherwise plan variant. See `.claude/rules/flow-docs.md`.

## Vertical Roster

Column-level ownership per vertical lives in each vertical's `*.feature.md`.

**Discovery:** FileScanning, MediaProbe, ContentSignals.

**Compliance (per-domain, no orchestrator):** AudioNormalization, VideoEncoding, ContainerFormat -- each answers one compliance question and writes one boolean. `WorkBucket` = `GENERATED ALWAYS AS (CASE ...) STORED` over the three.

**Policy:** `Features/Policy/` owns every table that says what a file should become -- `StorageRoots` tier/class/review flag, `GenreQualityTiers`, `TargetOverrides` (file > series), `Profiles` (one row per tier: label, quality-test switch, VMAF and held-frame acceptance), `LadderCells` (tier x class x source resolution x frame-rate class -> target resolution + kbps), `FrameRateClasses`, `EncoderSettings` (encoder x tier knobs), `AudioPolicyTracks` -- plus the SQL VIEW `MediaFileTargets`, `TargetResolver` (view row -> frozen `Target` or `Undecided`), `EncoderSelector` (worker capability flags -> encoder) and `MovieGenreSyncService` (Movies genres from Radarr at the end of each scan). No other vertical reads a policy table; consumers take `Target` as an argument. A new library, codec, frame-rate class, encoder or tier is a row.

**Execution:** TranscodeQueue (populate + route + failure-budget cap), CommandBuilder (`(MediaFile,Job) -> FFmpeg argv` via emitter slots), TranscodeJob (claim + run + record), QualityTesting (VMAF + auto-replace gate), FileReplacement (archive + swap + delegate re-probe), FailureAccounting (per-file failure budget).

**Operator UI:** Activity `/Activity`, TeamStatus `/Stats`, SystemSettings `/Settings`, SQLQueries `/SQLQueries`, ClipBuilder `/ClipBuilder`, Compliance `/Compliance`, WorkBucket `/Work/<bucket>`, FailureTracking.

**Infrastructure:** ServiceControl (lifecycle + stuck detection + drain), Optimization (Jellyfin log analysis), SharedTable (shared JS renderer).

**Sub-components** (repositories only, no domain): `MediaFilesRepository`, `WorkersRepository`, `JellyfinRepository`.

## Cross-Cutting Concerns

| Concern | Home |
|---|---|
| `WorkBucket` derivation | `MediaFiles.WorkBucket` GENERATED column |
| FFmpeg composition | `Features/CommandBuilder/` + emitter slots |
| DB session | `Core/Database/DatabaseService` |
| Logging | `Core/Logging/LoggingService` |
| Path translation | `Core/Path`, `Core/Path/LocalPath` (R6) |
| Worker capability gate | `Core/Database/WorkerCapabilityPredicate` |
| Failure budget gate | `Core/Database/FailureBudgetPredicate` |
| LIKE escaping | `DatabaseService.EscapeLikePattern` with `ESCAPE '!'` |
| A file's target | SQL VIEW `MediaFileTargets` read by `Features/Policy/TargetResolver`; every consumer (three verticals, admission, command composer, disposition decider, placement hand-off) takes the resulting `Target` as an argument and holds no policy repository |
| Radarr reads | `Core/Arr/RadarrClient` |

## Data Flow

```
RootFolder -> FileScanning -> MediaFiles
   end of scan: Movies genres from Radarr -> MediaFiles.Genres (Policy.MovieGenreSyncService)
   MediaProbe + ContentSignals fill metadata + signal columns
   Policy.TargetResolver reads MediaFileTargets -> Target (or Undecided)
   AudioNormalization / VideoEncoding / ContainerFormat: Evaluate(Facts, Target) -> compliance booleans
   -> GENERATED WorkBucket (names the job label)
   -> TranscodeQueue admits (Target: upscale, savings, budget, audio policy)
   -> TranscodeJob (claim + FFmpeg from Target + EncoderSettings)
   -> QualityTesting (VMAF or checksum) -> Disposition (Target acceptance) -> Replace | Hold | Requeue | Reject
   -> FileReplacement (archive + rename + delegate reprobe)
   -> MediaProbe reprobes -> compliance columns refresh -> WorkBucket recomputes
```

Cross-vertical reads asymmetric; per-vertical Cross-Vertical Contract lists legitimate reads. Any vertical writing another vertical's column = repo-wide-grep test failure.

## Database Invariants

- Polymorphic FK columns never `CASCADE` (R7).
- Each `*Compliant` column written only by its owning vertical.
- `WorkBucket` GENERATED; Postgres refuses direct writes.
- Canonical paths in `MediaFiles.FilePath` regardless of writing host (`Core/Path` + R6).
- No boot-cached config (`db-is-authority`).
- Postgres `ENCODING 'UTF8' LC_COLLATE='en_US.UTF-8'`.
- Every vertical has a `*.feature.md` with a Cross-Vertical Contract.
- Policy tables (`StorageRoots` tier/class, `GenreQualityTiers`, `TargetOverrides`, `Profiles`, `LadderCells`, `FrameRateClasses`, `EncoderSettings`, `AudioPolicyTracks`) are read for decisions only by `Features/Policy/` (`TestTargetAuthority`); every column has a `/settings` control and a decision reader (`TestKnobInventory`).
- No stored derived target: `MediaFiles` carries facts (probe/scan writers) and the three compliance booleans; what a file should become is the view `MediaFileTargets`, computed at read. A requeue escalation is a `TargetOverrides` row, not a stored field.
- `WorkBucket` expression is the one home of D7 (`transcode.flow.md`): `CASE WHEN TranscodedByMediaVortex THEN 'Compliant' WHEN any <Dim>Compliant IS NULL THEN 'Unclassified' WHEN all three THEN 'Compliant' WHEN NOT VideoCompliant THEN 'Transcode' WHEN NOT ContainerCompliant THEN 'Remux' ELSE 'AudioFix' END`; `TestWorkBucketGeneratedColumn` asserts it whole. An `Undecided` target is stored as a NULL compliance boolean with the reason, so the row is `Unclassified`.

## Failure Modes (no failsafes)

- Vertical's compute raises -> exception propagates; no swallow.
- `*Compliant` NULL -> file absent from `WorkBucket` until vertical writes.
- Config edit mid-flight -> next claim/recompute reads fresh.

## How to Use

- Opening directive: read Vertical Roster + Job Types. Scope against named verticals.
- Adding compliance check: add to appropriate domain vertical. No Compliance vertical.
- Understanding pipeline: read the relevant `*.flow.md`. This doc is the MAP.
- Understanding a vertical's contract: read the relevant `*.feature.md`.
- Surprised: file a one-line PR against this doc in the same commit as your work.

## Maintenance Rule

Updated as a `Promotions` row at the end of any directive landing architectural change. Reviewers refuse an architectural directive that did not touch this file. Stable headings (do not rename): `Vertical Roster`, `Job Types`, `Cross-Cutting Concerns`, `Data Flow`, `Database Invariants`, `Failure Modes`, `Gap to Target`.

## Cross-References

`CLAUDE.md` -- entry; `GLOSSARY.md` -- terminology; `.claude/rules/*.md` -- auto-loaded invariants; `.claude/standards/index.md` -- phase gates; `.claude/directive.md` -- current ask; `memory/KNOWN-ISSUES.md` -- bugs; `IDEAS.md` -- ideas; per-vertical `*.feature.md` and `*.flow.md`.

## Gap to Target

Re-audited 2026-11-27 (`target-policy-architecture`). Schedule and exit checklist: `Docs/superpowers/plans/2026-11-27-target-policy-program.md`; evidence: `Docs/superpowers/audits/2026-11-26-*.md`.

| Gap | Evidence | Directive |
|---|---|---|
| Policy tables, `MediaFileTargets` view, `TargetResolver`, `EncoderSelector` do not exist; `Features/Profiles` not yet `Features/Policy`; capability flags have no deploy-time writer | 18 facts with two or more authorities; 8/9/9/7 functions answer the four target questions | `target-policy-1a-tables` |
| Verticals hold repositories and side effects; `RecomputeForFiles` resolves profile per file; `WorkBucket` expression carries `HasDialogBoostTrack` | `VideoVertical` tier-vs-profile branch; `AudioVertical` admission-gate writes | `target-policy-1b-verticals` |
| Admission, command composer, claim SQL and disposition read `AssignedProfile` / `Profiles` / `ProfileThresholds` / code dictionaries | claim joins `Profiles` on `AssignedProfile`; `WorkerEncoderResolver` overrides 10 GUI columns | `target-policy-1c-pipeline` |
| Ladder has no frame-rate tab; no encoder-settings, tier-acceptance, override or review-before-replace controls | 8,000 kbps = VMAF 90.4 at 59.94 fps, 98.9 at 29.97 fps | `target-policy-1d-gui` |
| `MediaFiles.AssignedProfile/AssignedProfileSource/KeepSource`, `ContentClassifier`, `SeriesProfiles`, `ContentClassificationRules`, `ProfileThresholds`, `CodecFlags`, dead `Profiles` columns, 39 dead `SystemSettings` keys still exist | knob inventory dead-column list | `target-policy-delete-stored` |
| Audio tracks defined in six places; `no_dialog_boost` compliance rule; Demucs unconditional | loudness target x3, codec/bitrate x6 | `target-policy-audio` |
| Disposition has no `Hold`; smart-confidence replaces without VMAF; two retry budgets; larger output rejected after commit | `VmafConfidenceStats`, `RetryBudgetService` + `FailureBudgetService` | `target-policy-verification` |
| Container defined in four places; `ResolutionCategory` derived four ways; duplicate Remux/AudioFix strategy classes | `ContainerSlot` hard-codes mp4 | `target-policy-command` |
| xxx library policy is operator data not yet set (2160p ceiling, `high` ladder cells, review flag) | 545 xxx 4K files above the 24,000 kbps ceiling | `xxx-target-data` |
| Program criteria 1-9 not re-run end to end | -- | `target-policy-closeout` |
