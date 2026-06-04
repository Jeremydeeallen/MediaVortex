# v2 Decision Program

**Decided:** 2026-06-04
**Driving directive:** `.claude/directives/closed/2026-06-04-v1-vs-v2-cost-pricing.md`

## Decision

**Option C: Hybrid extraction → v2.**

Extract substrate-independent domain libraries from MediaVortex v1, then build a v2 application around them with a clean substrate. v1 sunsets stage-by-stage as v2 reaches parity per vertical.

## Why

Parallel pricing of 10 representative future verticals by 10 independent subagents produced a 2.0× average v1-vs-v2 cost ratio (range 1.5×–3.5×). The dominating v1 entanglements named by ≥3 agents:

1. `DatabaseManager` monolith — every claim/query change ripples through 3+ near-duplicate methods. The Job-queue-with-discriminator that should exist doesn't.
2. MVVM + template + controller triple for every UI knob — adding one profile field is 3 plumbing files even when the domain change is one column.
3. Scattered capability flags as boolean columns rather than a first-class `Set[Capability]` — every new gating dimension adds new columns to two tables and N predicate fragments.
4. `CommandBuilder` returns a string blob, not a structured `EncodePlan` — multi-pass / two-pass / policy-driven streams require return-type refactors.
5. `Disposition` is a string tuple, not a sum type — every new outcome ripples through every consumer because the type doesn't enforce exhaustive handling.

These are substrate decisions. None get fixed by feature work; they only get fixed by substrate work. Continuing v1 means paying 2× the tax on every future vertical indefinitely. Greenfield v2 from scratch throws away 12 months of tested domain logic. Hybrid extraction preserves the wins and fixes the substrate.

## Pricing data

| # | Vertical | V1 days | V2 days | Ratio |
|---|---|---:|---:|---:|
| F1 | Worker→profile capability routing | 5.5 | 2.25 | 2.4× |
| F2 | Per-profile audio loudnorm override | 3.5 | 1.5 | 2.3× |
| F3 | Multi-pass encoding option | 5.0 | 2.5 | 2.0× |
| F4 | Worker health-aware claim | 4.0 | 2.5 | 1.6× |
| F5 | Per-show profile override | 1.5 | 1.0 | 1.5× |
| F6 | Conditional VMAF by resolution | 4.5 | 2.5 | 1.8× |
| F7 | Subtitle-stream selection rule | 3.5 | 1.5 | 2.3× |
| F8 | Worker priority weights | 3.5 | 1.0 | 3.5× |
| F9 | Hold-for-review disposition | 5.5 | 3.25 | 1.7× |
| F10 | Per-profile retention policy | 9.5 | 5.5 | 1.7× |
| **TOTAL** | | **46d** | **23d** | **2.0× avg** |

## Phased plan

Each row = one directive. Estimated weeks elapsed.

| # | Directive slug | Weeks | Output |
|---|---|---:|---|
| 1 | `path-class-design` | 0.5 | `path.feature.md` ratified -- full Path class surface, semantics, equality, hashing, serialization, resolution, repr. No code. |
| 2 | `commandbuilder-extraction` | 1 | `mediavortex-core.commandbuilder` library, substrate-independent, uses `Path`. CommandBuilder consumable as a pure library. |
| 3 | `vmaf-and-disposition-extraction` | 1 | VMAF parsing + post-transcode disposition decision tree extracted as pure libraries. |
| 4 | `profile-rules-and-capability-extraction` | 1 | Profile-rule interpreter + worker capability predicate logic extracted. All domain logic now in `mediavortex-core`. |
| 5 | `v2-substrate-buildout` | 2 | v2 schema (typed paths, capability sets, per-aggregate tables), DI shell, one claim policy chain, JobsRepository, ProfilesRepository, WorkersRepository. v2 boots; can claim jobs. |
| 6 | `v2-transcode-happy-path` | 2 | scan → claim → transcode → VMAF → replace → notify works end-to-end in v2 dev for one file. Uses extracted libraries. |
| 7–11 | One vertical per directive on v2; v1 deprecated stage-by-stage | 5 | Parity with v1 verticals. |
| 12+ | v2 in production; sunset v1 services | -- | Done. |

**Total to v2 in production with parity:** ~12 weeks elapsed.

## v2 shape (punch list)

- **`Path`**: single typed class, canonical-by-definition. `.Resolve(worker) -> str` only at I/O boundary. Backed by `(StorageRootId, RelativePath)`.
- **`Capability`**: enum / frozenset. `Profile.RequiredCapabilities: Set[Capability]`. `Worker.Capabilities: Set[Capability]`. Claim is set-subset.
- **Queue**: one `Jobs` table with `JobKind` discriminator. One claim method, one predicate, one `ORDER BY`. No 3-way duplication.
- **Repositories**: per-aggregate. Each <300 LOC. No monolith.
- **`ClaimPolicy`**: composable chain. Capability + Health + Priority + Enabled compose independently. Adding a new gate = one class.
- **`EncodePlan`**: CommandBuilder returns a structured list of ffmpeg invocations, not a string. Multi-pass / pre-pass / post-pass are plan properties, not worker branches.
- **`Disposition`**: sum type with exhaustive matching. New outcomes are compile errors at every consumer until handled.
- **`QualityPolicy`**: callable on Profile returning Disposition. Resolution-banded thresholds are one impl; no schema change to add variants.
- **Profile knobs UI**: one data-driven editor (Profile schema → form). Not 1 controller + 1 viewmodel + 1 template per knob.
- **Workers**: single binary. Capabilities from env at boot. No two-service split, no per-service venv.
- **Tech**: keep Flask, PostgreSQL, jQuery (or HTMX). Don't bikeshed.

## What v2 deletes

- MVVM in server-rendered UI (no ViewModels paying tax for non-existent data binding).
- Most of the R-rule defensive layer (R1, R6, R12, R15 exist because of substrate problems v2 doesn't have).
- Paths-as-`str`.
- Boolean-column-per-capability pattern.
- The `ffpmpegcommand` schema typo (clean schema in v2).
- Two-service split and per-service venv friction.

## What v2 keeps (extracted from v1)

- ffmpeg command construction logic — 12 months of tested flag combinations.
- VMAF score parsing and band interpretation.
- Profile rule matching and codec policy.
- Post-transcode disposition decision tree.
- Worker capability predicate logic.
- The schema design (mostly — modulo the FilePath restructure and the typo fix).
- All flow docs and feature docs as specifications for v2 behavior.
- The KNOWN-ISSUES context (Jellyfin 60s coalescing, Microsoft NFS bugs, etc.).

## Stop conditions / re-evaluate triggers

This program assumes future MediaVortex evolution continues at roughly the current pace (~20–30 verticals in the next 12 months). If that assumption breaks, re-evaluate:

- If MediaVortex pivots fundamentally (e.g., to streaming transcode) → the v2 shape needs redesign before continuing.
- If the operator decides feature ship velocity is no longer needed → A (finish v1 minimal cleanup, freeze it) becomes the rational answer.
- If a v2 directive's actual cost exceeds the estimate by >50% → pause, re-price, decide whether to continue.

Otherwise, drive directives 1 → N in order.
