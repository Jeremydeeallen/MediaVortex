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
| Larry LXC 218 | Docker host, 8 worker containers. |
| I9 | Dev workstation; reads source tree directly on restart. |

## Job Types

Three FFmpeg-driven job types map to three worker capability flags. One flow doc per pipeline shape.

| Job type | Work | Capability | Flow doc |
|---|---|---|---|
| Transcode | Run FFmpeg to produce new file (re-encode or stream-copy). Verify. Replace source. "Remux" is `Plan.VideoOp=StreamCopy`. | `TranscodeEnabled` | `transcode.flow.md` |
| QualityTest | Re-run VMAF or checksum against existing attempt. No new encode. | `QualityTestEnabled` | `Features/QualityTesting/quality-test.flow.md` |
| Scan | Walk storage roots. `ffprobe` only. | `ScanEnabled` | `Features/FileScanning/FileScanning.flow.md` |

**Rule:** new job type requires distinct capability flag. Otherwise plan variant. See `.claude/rules/flow-docs.md`.

## Vertical Roster

Column-level ownership per vertical lives in each vertical's `*.feature.md`.

**Discovery:** FileScanning, MediaProbe, ContentSignals.

**Compliance (per-domain, no orchestrator):** AudioNormalization, VideoEncoding, ContainerFormat -- each answers one compliance question and writes one boolean. `WorkBucket` = `GENERATED ALWAYS AS (CASE ...) STORED` over the three.

**Profile:** Profiles (definitions + thresholds + assignment), ContentClassifier (auto-assign when `AssignedProfile` NULL).

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
| Path translation | `Core/PathStorage`, `Core/Path/LocalPath` (R6) |
| Worker capability gate | `Core/Database/WorkerCapabilityPredicate` |
| Failure budget gate | `Core/Database/FailureBudgetPredicate` |
| LIKE escaping | `DatabaseService.EscapeLikePattern` with `ESCAPE '!'` |

## Data Flow

```
RootFolder -> FileScanning -> MediaFiles
   MediaProbe + ContentSignals fill metadata + signal columns
   AudioNormalization / VideoEncoding / ContainerFormat write compliance booleans
   -> GENERATED WorkBucket
   -> ContentClassifier assigns Profile if NULL
   -> TranscodeQueue populates
   -> TranscodeJob (claim + FFmpeg)
   -> QualityTesting (VMAF or checksum) -> Disposition
   -> FileReplacement (archive + rename + delegate reprobe)
   -> MediaProbe reprobes -> compliance columns refresh -> WorkBucket recomputes
```

Cross-vertical reads asymmetric; per-vertical Cross-Vertical Contract lists legitimate reads. Any vertical writing another vertical's column = repo-wide-grep test failure.

## Database Invariants

- Polymorphic FK columns never `CASCADE` (R7).
- Each `*Compliant` column written only by its owning vertical.
- `WorkBucket` GENERATED; Postgres refuses direct writes.
- Canonical paths in `MediaFiles.FilePath` regardless of writing host (`Core/PathStorage` + R6).
- No boot-cached config (`db-is-authority`).
- Postgres `ENCODING 'UTF8' LC_COLLATE='en_US.UTF-8'`.
- Every vertical has a `*.feature.md` with a Cross-Vertical Contract.

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

Re-audited 2026-07-03 during `transcode-flow-canonical` NEEDS_STANDARDS_REVIEW.

| Gap | Evidence | Directive |
|---|---|---|
| Compliance gate bypassed 88% of attempts | BypassReplace=981/1121 over 7d | `transcode-flow-canonical` C6 |
| `AudioPolicyResolved` 0% populated | 0/1121 rows | C5 |
| `AudioPolicyJson` 0% populated | 0/1121 rows | C5 |
| VMAF measured on 3.6% of attempts | 40/1121 rows | C6 |
| 9+ orchestration `Mode == 'X'` branches | `QueueManagementBusinessService.py:321-1969`, `TranscodedOutputPlacement.py:83`, `JobProcessor.py:110`, `DashboardSnapshotService.py:14` | C4 |
| `GLOSSARY.md` does not exist | -- | C0b |
| `quality-test.flow.md` does not exist | -- | C1 |
| `.claude/rules/fail-loud.md` does not exist | -- | C7 pre-step |

Prior "EMPTY as of 2026-06-21" claim was not audited. On close, this section returns to describing future scope expansions from `IDEAS.md`.
