# Path Track Program

**Set:** 2026-06-04
**Driving directive:** `.claude/directives/closed/2026-06-04-path-class-design.md` (closed Success)

## Decision

Drive `Core/Path/Path.py` from "design ratified" to "v1 deprecated, v2 path layer in production" across 10 phases. Operator delegated path choice 2026-06-04: "I want it to be perfect and done. You chose the path."

## What "flawless" means (the bar)

| Dimension | Standard |
|---|---|
| Correctness | All C1-C15 (from `Core/Path/path.feature.md`) pass + property-based testing finds zero counterexamples in >=1M Hypothesis examples |
| Performance | `Resolve` profiled; `__eq__`/`__hash__`/`__repr__`/`__str__`/`ToJsonDict` provably zero I/O |
| Security | `FromLegacyString` rejects path-traversal vectors; `Resolve` output safe to argv |
| Maintainability | R-rule compliant; code anchors per seam; no dead code |
| Migration safety | Legacy v1 rows round-trip without loss; rollback path documented |
| Observability | Orphan StorageRoot greppable; resolution counters exist |
| Doc reality | `Core/Path/path.feature.md` describes what code actually does, not what we hoped |

## Phased plan

Each row = one directive. Estimated days of operator wall-clock.

| Phase | Directive slug | Days | Ships |
|---|---|---:|---|
| 1 | `path-class-implementation` | 1 | `Core/Path/Path.py` + `PathError` + 28 unit tests + 1 contract test. All 29 green. |
| 2 | `path-property-and-fuzz` | 0.5 | Hypothesis suite: equality reflexivity/symmetry/transitivity, FromLegacyString round-trip on synthetic zoo, normalization idempotency. 1M-example runs zero failures. |
| 3 | `path-security-audit` | 0.5 | Threat model + `/security-review` report + hardening commits. NUL bytes, mixed slashes, Win32 namespace, percent-encoded `..`, UNICODE normalization tricks exhaustively tested. |
| 4 | `path-performance-budget` | 0.5 | Microbenchmark suite + mock-DB sentinel that raises if `__eq__`/`__hash__`/`__repr__`/`__str__`/`ToJsonDict` hit the DB. `Resolve` p99 < 1ms when worker.ResolveStorageRoot cached. |
| 5 | `path-db-roundtrip-live` | 0.5 | Contract test exercised against live 10.0.0.15:5432 PostgreSQL + per-table audit on every path-bearing table (MediaFiles, MediaFilesArchive, TranscodeQueue, TranscodeAttempts, TemporaryFilePaths, ShowSettings). Zero round-trip loss. |
| 6 | `path-migration-rehearsal` | 1 | Read-only audit script walking every `MediaFiles.FilePath` row, attempting `Path.FromLegacyString`. Report parse-failure rate. < 0.1% target; every failure has logged root cause. |
| 7 | `<feature>-uses-path` x N | 4 | Per v1 feature: swap callers from `Core/PathStorage.<func>` to `Core/Path/Path.<method>`. One directive per feature vertical (FileScanning, MediaProbe, FileReplacement, TranscodeJob, QualityTesting, TranscodeQueue, Activity). |
| 8 | `path-schema-migration` | 1 | Drop legacy `FilePath` columns. Idempotent migration. Rollback documented. |
| 9 | `path-v1-deprecation` | 0.5 | Delete `Core/PathStorage.py`. Remove `/mediavortex-paths` command. Re-evaluate R6 hook necessity. |
| 10 | `path-flawless-attestation` | 0.5 | Coverage >= 95%, mutmut < 5% survivors, 1M Hypothesis examples green, live-DB audit clean, 7-day production logs zero unexplained PathError. |

**Total:** ~10 operator-days elapsed (across multiple sessions).

## Tools/skills/agents per phase

Reference list. Specific picks happen at each directive's NEEDS_PLAN.

### Skills (process / discipline)

- `superpowers:brainstorming` -- before creative work (used at Phase 0 / `path-class-design`).
- `superpowers:writing-plans` -- spec to implementation plan.
- `superpowers:test-driven-development` -- tests before implementation (Phase 1, 2, 4).
- `superpowers:executing-plans` -- drive an implementation plan with checkpoints.
- `superpowers:subagent-driven-development` -- in-session parallelism on independent tasks (Phase 1 test files, Phase 7 caller migrations).
- `superpowers:dispatching-parallel-agents` -- 2+ independent tasks without shared state.
- `superpowers:verification-before-completion` -- evidence before assertions; required before any "done" claim.
- `superpowers:systematic-debugging` -- when tests fail or Hypothesis surfaces a counterexample.
- `superpowers:receiving-code-review` / `superpowers:requesting-code-review` -- review loop pre-merge (Phases 1, 7, 8).
- `superpowers:finishing-a-development-branch` -- completion ceremony.
- `/fs` -- per-feature success ceremony (finalize, QA, UX review, dead code, simplify, commit).
- `/r` -- review changed code for reuse/quality/efficiency (every phase).
- `/simplify` -- fix issues found by review.
- `/security-review` -- Phase 3.
- `/check-conformance` -- after every phase.
- `mediavortex-check-baselines` -- after every phase.

### Expert consultations (read-only advice)

- `software-architect` -- Phase 1: frozen dataclass vs `__slots__` vs Pydantic; immutability mechanism.
- `testing-expert` -- Phases 1, 2, 4: test pyramid, Hypothesis design, benchmark methodology.
- `data-expert` -- Phases 5, 8: schema audit, migration safety, column drop ordering.
- `security-expert` -- Phase 3: threat model, OWASP mapping, hardening.
- `observability-expert` -- Phase 9 prep + Phase 10: counters, structured-log schema for orphan StorageRoot.
- `release-management-expert` -- Phase 8: rollback strategy for column drop.
- `documentation-expert` -- Phase 9: docs audit when v1 deletes.

### Agents

- `Explore` -- finding callers (Phase 7), confirming zero `Core.PathStorage` imports (Phase 9).
- `Plan` -- per-phase implementation plan.
- `qa-tester` -- per-directive: walk numbered criteria against actual code, report per-criterion status.
- `general-purpose` -- multi-step audits (Phase 6 migration rehearsal script, Phase 10 evidence gathering).

## Stop conditions / re-evaluate triggers

- Phase 1 reveals the design has a defect that can't be fixed in `path-class-implementation`'s scope -> reopen `path-class-design`.
- Phase 5 finds existing rows that can't round-trip without data transformation -> split work into a `path-data-migration-bridge` directive.
- Phase 6 parse-failure rate > 5% -> reopen `FromLegacyString` design.
- Phase 7 caller migration costs exceed estimate by > 50% -> pause, re-price.
- Any phase introduces a regression to a non-path feature -> halt, fix root cause, write a regression test before resuming.

## Cross-references

- `Core/Path/path.feature.md` -- the design contract this program implements.
- `.claude/programs/v2-decision.md` -- parent program; this is the path-class sub-track.
- `.claude/directives/closed/2026-06-04-path-class-design.md` -- the closed predecessor.
