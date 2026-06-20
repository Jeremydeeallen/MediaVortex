# Container Format -- container + audio-codec compliance

**Slug:** container-format

## What It Does

Answers one question about each MediaFile: is its container (mp4, mkv, etc.) acceptable, AND is its audio codec compatible with the container choice. Writes `(ContainerCompliant, ContainerCompliantReason)` to `MediaFiles`. One of three per-domain compliance verticals (Audio / Video / Container) that together feed the WorkBucket trigger.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | Operator edits acceptable containers / audio codecs | future `/Compliance` Container tab | (UI lands in operator-surfaces directive) | direct UPDATE to `ContainerComplianceRules` |
| W2 | Probe completion triggers Container recompute | scanner post-probe (after compliance refactor) | per-file `RecomputeFor` | `ContainerVertical.RecomputeFor([Id])` |
| W3 | Admin recompute across all files | CLI / future button | -- | `ContainerVertical.RecomputeFor(all_ids)` |

## Success Criteria

C1. `ContainerVertical.RecomputeFor(MediaFileIds)` writes `(ContainerCompliant, ContainerCompliantReason)` for each id. Verifiable: post-call `SELECT ContainerCompliant FROM MediaFiles WHERE Id=<id>` is non-NULL.
C2. Predicate: TRUE iff `ContainerFormat` is in `AcceptableContainersCsv` AND `AudioCodec` is in `AcceptableAudioCodecsCsv`. Otherwise FALSE with reason naming the failing rule. Verifiable: file with `Container='mkv'` + rules excluding mkv -> Compliant=FALSE, Reason='container_not_acceptable:mkv'.
C3. Rules read fresh per `RecomputeFor` call (`db-is-authority`). Verifiable: UPDATE ContainerComplianceRules; next RecomputeFor call observes the new values without restart.
C4. Vertical has zero dependency on `Features/Compliance/`. Verifiable: `grep -r 'Features.Compliance' Features/ContainerFormat/` returns 0.
C5. Failure-loudly: if `ContainerComplianceRules` table has no rows, `_LoadRules` raises `RuntimeError`. Verifiable: empty the table; RecomputeFor raises immediately.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | `RecomputeFor` -> `MediaFiles.ContainerCompliant` | `ContainerVertical._WriteResult` | `(ContainerCompliant: bool/NULL, ContainerCompliantReason: text/NULL)` | future SQL trigger reads to derive `WorkBucket` | Post-RecomputeFor SELECT returns fresh values |
| S2 | `ContainerComplianceRules` -> vertical | DB UPDATE via UI or direct SQL | row shape: `(AcceptableContainersCsv, AcceptableAudioCodecsCsv)` | `_LoadRules` parses CSV per call | UPDATE then RecomputeFor observes change |
| S3 | Probe completion -> ContainerVertical | (today: direct call; post-refactor: scanner orchestrator) | `MediaFileId: int` | `RecomputeFor([Id])` writes the column | Live smoke: probe a file, observe ContainerCompliant populates |

## Cross-Vertical Contract

This section locks the ContainerFormat vertical's public surface. Other verticals interact ONLY through what is listed below.

### Columns the ContainerFormat vertical WRITES

| Column | Written by |
|---|---|
| `MediaFiles.ContainerCompliant` | `ContainerVertical._WriteResult` (called from `RecomputeFor`) |
| `MediaFiles.ContainerCompliantReason` | `ContainerVertical._WriteResult` |
| `ContainerComplianceRules.*` | operator via future `/Compliance` Container tab |

### Columns the ContainerFormat vertical READS from external tables

| Column | Read by | Owner |
|---|---|---|
| `MediaFiles.ContainerFormat` | `_EvaluateOne` | MediaProbe vertical |
| `MediaFiles.AudioCodec` | `_EvaluateOne` -- "which audio codecs my container can wrap" is part of the container's domain | MediaProbe vertical |
| `MediaFiles.Id` | every public method | FileScanning vertical |

### Stable function entry points (cross-vertical callers)

| Class.method | External caller(s) |
|---|---|
| `ContainerVertical.RecomputeFor(MediaFileIds: List[int]) -> None` | future scanner post-probe orchestrator; future admin recompute |

Constructor injection: `__init__(Db: Optional[DatabaseService]=None)`. Adding a kwarg with default is non-breaking; removing/renaming is a contract change.

### HTTP API surface

None today. Future `/Compliance` Container tab + per-vertical settings endpoint will land in directive 7.

### What is EXPLICITLY NOT a contract

- Internal helper names (`_LoadRules`, `_EvaluateOne`, `_WriteResult`, `_ParseCsv`)
- The `(set, set)` tuple return shape of `_LoadRules`
- The format of `ContainerCompliantReason` strings (today: `container_not_acceptable:<value>` / `audio_codec_not_acceptable:<value>`; future tunable)
- Whether `_LoadRules` caches inter-call (today: no cache; future: short-TTL cache if perf demands)

## Status

ACTIVE. Created 2026-06-20 in directive `container-vertical` (Phase 3 of paused `vertical-owned-compliance`).

## Files

| File | Role |
|---|---|
| `ContainerVertical.py` | Compliance computation + write |
| `__init__.py` | Package marker |
