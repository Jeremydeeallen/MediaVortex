# MediaVortex Architecture

**Purpose:** This document defines DONE for MediaVortex. When the codebase matches every item in this document AND the `## Gap to Target` section at the bottom is empty, MediaVortex is done. Every directive is work that closes one or more gaps. Every architectural decision lands here, in the same commit as the work that surfaced it -- no exceptions.

**Target audience:** an engineer (human or AI) opening a directive who needs to know what verticals exist, what each owns, and where a given problem belongs.

**Not in this document:** target DB schema (row shapes, indexes, FK topology -- separate schema document), per-vertical Cross-Vertical Contracts (those live in each `*.feature.md`), code-level call graphs (read the relevant `*.flow.md`), KNOWN-ISSUES (bug tracker, not architecture), test strategy (`.claude/rules/test-placement.md`), deployment topology (operator runbook), frontend JS decomposition (owned by `.claude/directives/backlog/_perfect-codebase-roadmap.md`).

## The System in One Paragraph

MediaVortex is a self-hosted media library transcoder. A discovery layer (FileScanning + MediaProbe + ContentSignals) builds an inventory of `MediaFiles` rows with extracted metadata and content characterization. Three per-domain verticals each answer ONE question about a file -- is its audio compliant, its video compliant, its container compliant -- and each writes one boolean column on `MediaFiles`. A `GENERATED ALWAYS AS ... STORED` column composes those three booleans into a single `WorkBucket`. A queue vertical (TranscodeQueue) populates a per-worker job queue from `WorkBucket`. An execution vertical (TranscodeJob) runs FFmpeg; a verification vertical (QualityTesting) confirms the result via VMAF; a swap vertical (FileReplacement) installs it. Operator-facing surfaces render the data and accept policy edits. Two services run: WebService (Flask UI on port 5000) and WorkerService (transcoding / VMAF / scanning, capability-flagged per row in the `Workers` table). PostgreSQL is the only data store.

## Topology

| Component | Role |
|---|---|
| WebService | Flask app on port 5000. Renders pages, serves REST APIs, owns no transcoding work. Started by `StartMediaVortex.py`. |
| WorkerService | Unified worker. Three capabilities flagged per row in `Workers` (`TranscodeEnabled`, `QualityTestEnabled`, `ScanEnabled`). One worker process can do any subset; deploy chooses the mix. Started by `StartMediaVortex.py` (dev) or `StartWorker.py` (worker-only hosts). |
| PostgreSQL 16 | Single source of truth. LXC CT 203 (`10.0.0.15:5432`). All tables UTF-8. Per `.claude/rules/db-is-authority.md`: no boot-time caching of mid-flight-tunable values. |
| FFmpeg / FFprobe | Per-worker binaries (`Workers.FFmpegPath` / `FFprobePath`). Capability gating means the worker's local binary is used, not a global path. |
| Larry LXC 218 | Docker host running 8 worker containers (`mediavortex-worker-N-1`). Picks up code changes via image rebuild + redeploy. |
| I9 dev workstation | Reads source tree at `C:\Code\MediaVortex` directly on restart -- no deploy step needed. |

## Vertical Roster

Verticals are organized by what they own. Six categories. Internal vertical names describe their DOMAIN; cross-vertical column names use uniform `*Compliant` suffix at the seam.

### Discovery

| Vertical | Owns | Primary `MediaFiles` writes |
|---|---|---|
| FileScanning | Discovers files in registered root folders; manages `MediaFiles` row lifecycle (create / rename-detect / in-place-update / delete); claims scan work by per-worker affinity. | row create+delete; `FilePath`, `FileName`, `SizeMB`, `LastModifiedDate`, `RootFolderId`, `FFprobeFailureCount` |
| MediaProbe | Runs FFprobe; extracts media metadata; re-probes after FileReplacement. The Probe pipeline is one of the hubs every other vertical reads from. | `Resolution`, `Codec`, `AudioCodec`, `VideoBitrateKbps`, `ResolutionCategory`, `IsInterlaced`, `ContainerFormat`, `AudioLanguages`, `HasExplicitEnglishAudio`, `HasForcedSubtitles`, `SubtitleFormats`, `DurationMinutes` |
| ContentSignals | One-time per-file content characterization (signalstats + PySceneDetect) at probe time; feeds ContentClassifier. | `MotionFraction`, `SceneChangeRatePerMin`, `LumaVariance` |

### Compliance (per-domain, no orchestrator)

Each domain vertical answers ONE compliance question about a file and writes ONE boolean column + ONE reason column. A `GENERATED ALWAYS AS ... STORED` column on `MediaFiles` derives `WorkBucket` from the three booleans. **There is no Compliance vertical.** Compliance is a question each domain answers about itself; bucket derivation is a deterministic SQL expression living in the column definition.

| Vertical | Question answered | Primary writes |
|---|---|---|
| AudioNormalization | Is this file's audio compliant under the resolved scope-cascade policy? | `AudioCompliant`, `AudioCompliantReason`; measurement columns (`SourceIntegratedLufs`, `SourceLoudnessRangeLU`, `SourceTruePeakDbtp`, `SourceIntegratedThresholdLufs`, `LoudnessMeasuredAt`, `AudioComplete`, `AudioCorruptSuspect`, `AdmissionDeferReason`, `AudioStreamLanguageDetectionsJson`); `TranscodeQueue.AudioPolicyJson`; `TranscodeAttempts.AudioTracksEmittedJson`; `AudioNormalizationConfig.*` |
| VideoEncoding | Is this file's video compliant under the assigned profile? Codec acceptable, resolution not exceeding profile target, savings meaningful (BPP-aware), no upscale. | `VideoCompliant`, `VideoCompliantReason`; `VideoComplianceRules` table |
| ContainerFormat | Is this file's container compliant given its audio codec and the assigned profile? | `ContainerCompliant`, `ContainerCompliantReason`; `ContainerComplianceRules` table |

### Profile + Classification

| Vertical | Owns | Primary writes |
|---|---|---|
| Profiles | Encoding profile definitions; per-resolution thresholds; per-folder profile assignment (operator-pinned); `EffectiveProfileResolver` (3-strategy bitrate dispatch: fixed / VBR / CRF). | `Profiles`, `ProfileThresholds` tables; `MediaFiles.AssignedProfile` (manual pin) |
| ContentClassifier | Auto-assigns `AssignedProfile` when `NULL` using `ContentClassificationRules` (data-driven rule walker; no hardcoded policy). Operator pin always wins. | `MediaFiles.AssignedProfile` (only when previously `NULL`) |

### Execution

| Vertical | Owns | Primary writes |
|---|---|---|
| TranscodeQueue | Populates the queue from `WorkBucket`; routes by worker capability + per-rootfolder affinity; enforces failure-budget cap; prioritizes "next batch" surfaces. | `TranscodeQueue` table |
| CommandBuilder | Translates `(MediaFile, Job)` to one FFmpeg command line via one decision tree. Per-vertical emitter slots (`AudioFilterEmitter`, `VideoCommandEmitter`, `ContainerCommandEmitter`) concatenated by shape (Transcode / Remux). | (no DB writes -- emits argv) |
| TranscodeJob | Claims jobs atomically (`SELECT FOR UPDATE SKIP LOCKED`); runs FFmpeg; tracks progress; records attempt outcomes; in-place output (`*.inprogress` rename pattern). | `TranscodeAttempts`, `ActiveJobs`, `TranscodeProgress` tables; output file on disk |
| QualityTesting | Runs VMAF on output vs source; held-frame detection (motion-filtered pooling); auto-replace gate via `PostTranscodeGateConfig`. | `TranscodeAttempts.{VmafScore, QualityTestResult, ...}`; `PostTranscodeGateConfig`; `QualityTestResults` |
| FileReplacement | Swaps source with output (archive original metadata to `MediaFilesArchive`, rename `.inprogress` to final name, call MediaProbe for re-probe); cross-OS canonical-path math via `ntpath`. | `MediaFilesArchive` row; file rename on disk; delegates re-probe to MediaProbe |
| FailureAccounting | Per-`MediaFile` consecutive-encode-failure budget; operator reset surface at `/FailedJobs`; cap is enforced via one SQL fragment (`Core/Database/FailureBudgetPredicate`) wired into every claim + recompute + Next-Batch query. | `FailureBudgetResets`; `MediaFiles.LastFailureResetAt`; `TranscodeAttempts.MediaFileId` is structurally `NOT NULL` |

### Operator Surfaces (UI verticals)

| Vertical | Page | Owns |
|---|---|---|
| Activity | `/Activity` | Live worker / job / scan dashboard; 5s poll; uses SharedTable for every table. |
| ShowSettings | `/ShowSettings` (Media page) | Media library browse + title search + "Next Batch" auto-populate. |
| TeamStatus | `/Stats` | Per-worker job attribution; stuck-job reset; per-volume savings; CPU temperature breakdown. |
| SystemSettings | `/Settings` | Global key-value config UI; per-known-key controls plus generic advanced table for unknowns. |
| SQLQueries | `/SQLQueries` | Ad-hoc DB query interface; quick-query buttons; custom SQL execution. |
| ClipBuilder | `/ClipBuilder` | Independent tool: clip extraction + compilation export. Not part of the transcoding pipeline. |
| Compliance (tabbed shell) | `/Compliance` | Layout-only page with three tabs (Audio / Video / Container) -- each tab is rendered by its vertical's controller. No logic; pure UI shell. |
| WorkBucket | `/Work/<bucket>` (`/Work/Transcode`, `/Work/Remux`, `/Work/Audio`) | Per-bucket landing pages: paginated MediaFiles list filtered by `MediaFiles.WorkBucket`; single-row queue endpoint for one-off admission. Pure UI consumer of the generated column. |
| FailureTracking | `/api/FailureTracking/RecentFailures` | Recent service-failure history surface across `Transcode` / `Quality` services. Distinct from `FailureAccounting` (which enforces the per-MediaFile budget at `/FailedJobs`). |

### Infrastructure

| Vertical | Owns |
|---|---|
| ServiceControl | Service lifecycle (start / stop / pause / resume); health heartbeats via `ServiceStatus`; stuck-job detection; crash recovery; graceful drain. |
| Optimization | Jellyfin SSH log import + transcode-reason analysis at `/Optimization`; per-device breakdown; pre-transcode recommendations. |
| SharedTable | `Static/js/TableRenderer/` -- the single shared JS table renderer. Config-only adoption per page; no domain knowledge; rows / columns / capabilities / EventBus. |

### Sub-components (final non-verticals)

These directories contain only a repository (or pure data-access wrapper) and act as data accessors used by other verticals. They are NOT verticals; they have no domain.

| Path | Role |
|---|---|
| `Features/MediaFiles/MediaFilesRepository.py` | Data access for `MediaFiles` table; used by every vertical that touches the table. |
| `Features/Workers/WorkersRepository.py` | Data access for `Workers` table. |
| `Features/JellyfinIntegration/JellyfinRepository.py` | Pure data access wrapping Jellyfin SSH calls; consumed by Optimization. |

## Cross-Cutting Concerns

Each lives in code or in SQL. They are organizing forces that touch every vertical; they have no domain of their own.

| Concern | Home | Notes |
|---|---|---|
| `WorkBucket` derivation | `MediaFiles.WorkBucket` declared `GENERATED ALWAYS AS (CASE ...) STORED` | Reads `AudioCompliant` + `VideoCompliant` + `ContainerCompliant`; writes `WorkBucket`. Precedence: `!VideoCompliant` -> `Transcode`, else `!ContainerCompliant` -> `Remux`, else `!AudioCompliant` -> `AudioFix`, else `NULL`. Deterministic CASE in the column definition; Postgres refuses any INSERT/UPDATE that tries to set the column directly; no Python orchestrator; no defense layers. |
| FFmpeg command composition | `Features/CommandBuilder/` + per-vertical emitters (`AudioFilterEmitter`, `VideoCommandEmitter`, `ContainerCommandEmitter`) | One entry point; one decision tree. Per-vertical emitter slots concatenated by shape. |
| DB session | `Core/Database/DatabaseService` | `RealDictCursor` + `CaseInsensitiveDict` adapter. `ExecuteQuery` (reads) vs `ExecuteNonQuery` (auto-commits). |
| Logging | `Core/Logging/LoggingService` | Writes `Logs` table with component + method context. Per `.claude/rules/error-ux.md`. |
| Path translation (Windows <-> POSIX) | `Core/PathStorage`, `Core/Path/LocalPath` | Canonical DB paths are Windows-flavored. `os.path` on canonical paths is forbidden (R6 / `mediavortex-paths`). |
| Worker capability gating | `Core/Database/WorkerCapabilityPredicate` | Single SQL fragment emitted by every `Claim*` query. SQL-injection-safe column whitelist. |
| Failure budget gating | `Core/Database/FailureBudgetPredicate` | Single SQL fragment emitted by every claim + recompute + Next-Batch query. |
| LIKE-pattern escaping for paths | `Core.Database.DatabaseService.EscapeLikePattern` with `ESCAPE '!'` | Paths contain `%`, `_`, `!` -- never raw LIKE. |

## Data Flow Graph

```
RootFolder (operator-configured)
     |
     v
FileScanning ---- insert -----> MediaFiles row
                                   |
MediaProbe ------ update --------> (probe columns: Resolution, Codec, AudioCodec, ...)
                                   |
ContentSignals -- update --------> (signal columns: MotionFraction, ...)
                                   |
                                   +-- AudioNormalization ---- update --> AudioCompliant
                                   +-- VideoEncoding --------- update --> VideoCompliant
                                   +-- ContainerFormat ------- update --> ContainerCompliant
                                                   |
                                              [GENERATED column]
                                                   |
                                                   v
                                          MediaFiles.WorkBucket
                                                   |
                  ContentClassifier ---- update --> MediaFiles.AssignedProfile (when NULL)
                                                   |
                                                   v
                                      TranscodeQueue.PopulateFromBucket
                                                   |
                                                   v
                                  TranscodeJob (claim + CommandBuilder + FFmpeg)
                                                   |
                                                   v
                                  QualityTesting (VMAF) ---> TranscodeAttempts.VmafScore
                                                   |
                                                   v
                              FileReplacement (archive + rename + delegate to MediaProbe)
                                                   |
                                                   v
                                      MediaProbe (re-probe) -> MediaFiles columns refreshed
                                                   |
                                                   v
                              AudioNormalization / VideoEncoding / ContainerFormat
                              re-evaluate their respective *Compliant columns
                              (column auto-recomputes -> new WorkBucket)
```

### Cross-vertical reads (asymmetric -- only the legitimate ones)

| Reader | Reads | Why |
|---|---|---|
| ContainerFormat | `MediaFile.AudioCodec` | "Which audio codecs my container can wrap" is part of the container's domain. The only legitimate cross-domain read. |
| TranscodeQueue | `MediaFiles.{WorkBucket, AssignedProfile}` + failure-budget predicate | Routing. |
| TranscodeJob | `Profiles.*`, `TranscodeQueue.AudioPolicyJson` | Command construction. |
| FileReplacement | `TranscodeAttempts.OutputFilePath` + invokes `MediaProbe.ProbeFile` | Swap + re-probe. |
| ContentClassifier | probe columns + signal columns + `ContentClassificationRules` | Rule matching. |
| QualityTesting | source file path + transcoded output path | VMAF comparison. |

### Disallowed reads / writes

| Vertical | Must NOT |
|---|---|
| Any vertical | Write a column owned by another vertical (enforced by repo-wide grep test). |
| Any vertical | Cache DB-tunable config at boot (`db-is-authority`). |
| Any vertical | Open another vertical's internal helpers (`_` prefix, internal dataclasses). Public contract = entries listed in the vertical's Cross-Vertical Contract section. |
| Any Python code | Write `MediaFiles.WorkBucket` (column is `GENERATED ALWAYS`; Postgres refuses the write). |

## Database Invariants

| Invariant | Enforced by |
|---|---|
| `MediaFiles.Id` is PK | Schema |
| `TranscodeAttempts.MediaFileId NOT NULL` | Schema |
| Polymorphic FK columns never use `CASCADE` | Code review + R7 + memory rule (`feedback_polymorphic_fk_no_cascade`) |
| `AudioCompliant` is written only by the Audio vertical | Repo-wide grep test |
| `VideoCompliant` is written only by VideoEncoding | Repo-wide grep test |
| `ContainerCompliant` is written only by ContainerFormat | Repo-wide grep test |
| `WorkBucket` is computed by the `GENERATED ALWAYS AS ... STORED` definition | Column declaration; no Python write path possible (Postgres refuses) |
| Bucket derivation is deterministic | CASE in the column definition; no validators, no defense layers, no fallbacks |
| All paths in `MediaFiles.FilePath` stored as canonical (Windows-flavored) regardless of writing host | `Core/PathStorage` discipline + R6 hook |
| Mid-flight config edits observed by next claim/decision/recompute | `db-is-authority`; per-call repo `Get()`; no instance caching |
| Postgres `ENCODING 'UTF8' LC_COLLATE='en_US.UTF-8' LC_CTYPE='en_US.UTF-8' TEMPLATE=template0` | Migration scripts |
| The `transcodeattempts.ffpmpegcommand` typo is the canonical column name | Documented in `CLAUDE.md`; code must match |
| Every vertical has a `*.feature.md` with a Cross-Vertical Contract section | Convention; repo-wide audit at directive close |

## Failure Modes (no failsafes)

| Failure | Behavior |
|---|---|
| Vertical's `RecomputeFor` raises (missing probe data, invalid policy, DB error) | Exception propagates to scanner post-probe handler; handler fails loudly; no `try/except` swallows. |
| `*Compliant` column is `NULL` for a file | File does not appear in `WorkBucket`; remains unrouted until the owning vertical writes a non-`NULL` value. No defensive defaults. |
| Generated column with all three booleans `NULL` | Evaluates `WorkBucket = NULL` (file isn't ready); no exception, no warning. |
| Operator edits a rule mid-flight | Next claim / next recompute reads fresh per `db-is-authority`. No restart needed. |
| Operator deletes a column owned by another vertical | DB raises; the change is refused at schema-edit time. |

## How to Use This Document

| If you are... | Do this |
|---|---|
| Opening a new directive | Read Vertical Roster. Identify which vertical(s) the directive touches. Scope against named verticals, not "the codebase." |
| Wondering "should I add a Compliance check?" | Add the check to the appropriate domain vertical (Audio / Video / Container) and its boolean column. There is no Compliance vertical to extend. |
| Wondering "should X be a vertical?" | If it owns a domain of policy or an operator-facing capability, yes. If it's a data accessor (one table -> one repo) or a cross-cutting concern (logging, paths), no -- it's a sub-component or lives in `Core/`. |
| Adding a new field to `MediaFiles` | Identify the owning vertical. Add it to that vertical's WRITES list in its feature doc's Cross-Vertical Contract section. |
| Surprised by something not in this doc | File a one-line PR against this document in the same commit as your work. Do not let the doc drift behind the code. |
| Trying to understand a pipeline | Read the relevant `*.flow.md`. This doc is the MAP; flow docs are the PIPELINES. |
| Trying to understand a vertical's contract | Read the relevant `*.feature.md`. This doc names the vertical and what it owns; the feature doc holds the criteria, workflows, and seams. |

## Maintenance Rule

This document is updated as a `Promotions` row at the end of any directive that lands architectural change. The directive's `Files` block must include `ARCHITECTURE.md` and the `Promotions` table must contain a row pointing here. Reviewers and the close-checker refuse a directive marked as architectural that did not touch this file.

Stable headings (do not rename without coordinated update):
- `Vertical Roster`
- `Cross-Cutting Concerns`
- `Data Flow Graph`
- `Database Invariants`
- `Failure Modes`
- `Gap to Target`

## Cross-References

- `CLAUDE.md` -- entry point; "Where everything lives"
- `.claude/rules/*.md` -- auto-loaded invariants
- `.claude/rules-details/*.md` -- the details on each rule
- `.claude/standards/index.md` -- phase gates + R-rules
- `.claude/directive.md` -- the current ask
- `memory/KNOWN-ISSUES.md` -- known bugs (not architecture)
- `IDEAS.md` -- captured ideas not yet promoted to directives
- Per-vertical `*.feature.md` and `*.flow.md` -- the contracts

---

# Gap to Target

The architecture above defines DONE. The list below names every place the current codebase does NOT match the architecture. Each row is closeable work. **When this section is empty, MediaVortex is done.**

Each row owns one of: a directive (existing or new), a feature-doc creation, or a delete. No row is "deferred" or "considered" -- if it's here, it's required to reach the target. If something genuinely isn't required, it doesn't go in the architecture; it goes nowhere.

## Closing work that doesn't fit elsewhere

| Item | Current state | Closing work |
|---|---|---|
| Per-share-root audio policy (`StorageRootAudioPolicy` table) | Does not exist. Audio policy is library-wide. | Add table + scope-cascade integration; replaces the `xxx`-share hardcoded `AudioDamageNotMaterial=TRUE` rows. Filed in `IDEAS.md` 2026-06-12. |
| Audio dual-track speech-enrichment policy | Does not exist. | Audio vertical follow-up. |
| Repo-wide grep test enforcing per-vertical column-write ownership | Does not exist. | Add `Tests/Contract/TestVerticalColumnOwnership.py` once Cross-Vertical Contracts are populated for every vertical. |
