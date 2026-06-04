# Current Directive

**Set:** 2026-06-04
**Closed:** 2026-06-04
**Status:** Closed -- Success
**Slug:** path-class-design
**Replaces:** `.claude/directives/closed/2026-06-04-v1-vs-v2-cost-pricing.md` (closed Success -- Option C / Hybrid extraction → v2 selected)

## Outcome

A ratified `path.feature.md` capturing the full `Path` class design for v2: surface, semantics, equality, hashing, serialization, resolution to worker-local string, repr, and edge-case behavior (NULL StorageRoot, deleted storage root, round-trip through Jellyfin's API). Operator stress-tests the design as prose before any code touches it. After this directive, every subsequent v2 extraction directive can depend on `Path` as the canonical path representation.

## Acceptance Criteria

1. **`path.feature.md` exists** at a colocated v2 location (proposed: `Core/Path/path.feature.md` -- the v2 home for this aggregate). Has stable IDs (W1..Wn for workflows, C1..Cn for criteria, S1..Sn for seams) per `.claude/rules/feature-docs.md`. Passes the five litmus tests in `.claude/rules/feature-criteria.md` (rename / outsider / rewrite / negation / stability).

2. **Class surface is fully enumerated.** The doc lists every public method/property the `Path` class will expose, with input types, return types, and one-line semantics each. No "TBD" entries. Methods include at minimum: construction (`FromPair`, `FromCanonicalString` validated, optional `FromLocalString` for migration), resolution (`Resolve(Worker) -> str`), structural ops (`ParentDir() -> Path`, `LastSegment() -> str`, `SplitExt() -> tuple[Path, str]`, `Join(child: str) -> Path`), filesystem ops (`Exists(Worker) -> bool`, `IsFile(Worker) -> bool`, `IsDir(Worker) -> bool`, `GetSize(Worker) -> int`, `GetMTime(Worker) -> float`), equality (`__eq__`), hashing (`__hash__`), repr (`__repr__`), serialization (`ToJsonDict()`, `FromJsonDict()`, `__str__`).

3. **Semantic decisions are explicit.** The doc names the answer for every non-obvious case: equality across shape variants (UNC vs drive-letter representing the same canonical pair → equal? Decision required.), case sensitivity policy (canonical paths case-insensitive across all shapes? Or shape-dependent?), null `StorageRoot` handling, behavior when a referenced `StorageRoot` row is deleted from the DB, behavior under SQLAlchemy/psycopg2 round-trip, JSON serialization shape for API responses, repr shape for logs.

4. **Seams enumerated.** The `## Seams` table lists every cross-component boundary the class crosses: producer (the `Path` constructor / repository read), wire shape (canonical string or typed pair), consumer expectations (every site that reads a `MediaFiles.FilePath` or similar). At minimum: DB-row → `Path` (via repository), `Path` → JSON (API response), `Path` → worker (via `Resolve`), `Path` → log line (via `__repr__`), `Path` → ffmpeg argv (via `Resolve` then string).

5. **Test plan named.** The doc's `## Verification` section names the unit tests that will exist when the class ships: shape parsing (UNC, Windows-drive, POSIX), equality across shapes, round-trip via JSON, resolution against a mock Worker, behavior under deleted StorageRoot, behavior under null StorageRoot. Names tests, doesn't write them -- that's the next directive.

6. **No production code touched.** This directive produces a feature doc and nothing else. v2 lives in a future commit; this is the design contract.

7. **One session.** Wall clock: this directive opens and closes in the same operator session. If it can't, the design isn't tractable as written and the directive's scope is wrong.

## Out of Scope

- Writing `Core/PathStorage/Path.py` or any production code. That's the next directive (`path-class-implementation`).
- Migrating any v1 caller to use `Path`. Migration is N directives away; v2 callers use it from day 1.
- DB column migration (`MediaFiles.FilePath: str` → `(StorageRootId, RelativePath)`). The `Path` class is designed to work both with the legacy single-column read AND the typed-pair read; the migration is later.
- Changes to v1 -- v1 keeps its current `Core.PathStorage` surface unchanged. This directive does not touch v1 production code, v1 hooks, v1 baselines, or v1 R-rules.
- Designing `Capability`, `EncodePlan`, `Disposition`, `QualityPolicy`, or any other v2 substrate type. Those are separate directives in the phased plan (`.claude/programs/v2-decision.md`).
- Picking the v2 deployment shape, packaging, dependency injection strategy, or test framework. Those are part of `v2-substrate-buildout` later.

## Constraints

- `path.feature.md` is the only writable artifact this directive produces.
- The class design must be compatible with the v2 substrate decisions in `.claude/programs/v2-decision.md` (typed pair `(StorageRootId, RelativePath)` as the backing store; resolution is the only `str`-returning boundary; equality is shape-aware by design).
- The design must handle the three v1 path shapes (UNC, Windows-drive, POSIX) without requiring callers to know which one is in hand. Shape is an internal implementation detail.
- The design must be implementable in one session of code-writing once approved (i.e., not so ambitious that the next directive can't finish it). Target: ~200 LOC for the production class.

## Escalation Defaults

- Equality / case-sensitivity / NULL-StorageRoot decisions where multiple defensible answers exist → state the recommendation in the doc and surface as a Decision Point in the directive's Status block. Operator approves or redirects.
- Backward-compatibility tension (v2-clean design vs. v1 migration ergonomics) → choose v2-clean. v1 migration is fixed by adapter functions later, not by polluting the v2 class design.
- Risk tolerance: low. This is the foundation every other v2 directive sits on. Take time to get it right rather than ship a design that has to be revisited.

## Engineering Calls Already Made

- **Class is named `Path`.** Not `CanonicalPath`, not `PathResolver`, not `MediaPath`. Per operator decision earlier this session: the path IS canonical; "canonical" is not a label, it's the definition.
- **Backed by typed pair `(StorageRootId: int, RelativePath: str)`.** Resolution to a worker-local string is via `.Resolve(Worker)`. No string-flavored canonical paths in the public surface.
- **Lives in `Core/Path/`** (v2 location). v1 `Core/PathStorage/` stays untouched. v2 picks the cleaner name.
- **Frozen / immutable.** `Path` instances are value objects; structural ops return new instances rather than mutating.
- **Equality is by typed pair, not by string representation.** Two `Path` instances representing the same `(StorageRootId, RelativePath)` are equal regardless of how they were constructed.

## Status

Closed 2026-06-04 -- Success. Design promoted to `Core/Path/path.feature.md`; operator approved at DELIVERING.

### Files

```
Core/Path/path.feature.md    -- CREATED (this directive)
```

Zero production `.py` / `.sql` / `.html` / `.js` / `.css` touched. Only artifact: the design contract.

### Promotions

| Source artifact | Target file | Status |
|---|---|---|
| `## What It Does` + `## Workflows` + `## Class Surface` + `## Semantic Decisions` + `## Success Criteria` + `## Seams` + `## Verification (Test Plan)` | `Core/Path/path.feature.md` (created) | Promoted 2026-06-04 |

No update needed to `.claude/programs/v2-decision.md` -- the v2-shape decisions captured in this directive (typed-pair backing, `.Resolve` as the only str-yielding boundary, equality by pair, immutability) are already in the program doc's "v2 shape" punch list; this directive ratifies them by enumerating the class surface, not by changing the program.

### Verification

One entry per acceptance criterion.

- **Criterion 1 (doc exists + stable IDs + litmus tests):**
  - `Core/Path/path.feature.md` exists. Slug `**Slug:** path` on line 3 (R16 hook check satisfied).
  - Stable IDs present: W1-W7 (Workflows), C1-C15 (Success Criteria), S1-S8 (Seams), D1-D12 (Decisions).
  - Five litmus tests (per `.claude/rules/feature-criteria.md`):
    - **Rename test PASSES.** Criteria reference public method names which ARE the contract surface. Renaming internal helpers leaves observable behavior intact.
    - **Outsider test PASSES.** Each criterion is a runnable Python expression or observable behavior. C2 / C11 / C12 / C14 are assertions executable on the implementation.
    - **Rewrite test PASSES.** Frozen / immutable / hashable / typed-pair semantics are language-agnostic. D12's `@dataclass(frozen=True)` is the Python idiom; the requirement carries.
    - **Negation test PASSES.** NOT(C2) = case differences merge into one Path -> different DB rows collapse silently -> data corruption. Real failure.
    - **Stability test PASSES.** Criteria describe interface contracts, not implementation. A refactor that splits `Resolve` into private helpers leaves C8/C9 intact.

- **Criterion 2 (class surface fully enumerated):** 21 public methods/properties enumerated in `Core/Path/path.feature.md` `## Class Surface`, grouped Construction / Identity / Structural / Resolution-I/O / Serialization, each with input/return types and one-line semantics. No "TBD" entries. Meets every minimum named in the directive criterion (constructor, FromPair, FromRow, FromLegacyString, FromJsonDict, Resolve, ParentDir, LastSegment, SplitExt, Join, Exists, IsFile, IsDir, GetSize, GetMTime, __eq__, __hash__, __repr__, __str__, ToJsonDict). Two additions over the directive's minimum: `__str__` mirrors `__repr__` (so f-strings don't trigger DB calls); `CanonicalDisplay(prefixes)` is the explicit-prefix-map adapter so UI layers render display without the class touching the DB.

- **Criterion 3 (semantic decisions explicit):** 12 D-decisions in `Core/Path/path.feature.md` `## Semantic Decisions` with answer + reasoning per row. Covers the directive-named cases: equality across shape variants (D1), case sensitivity (D2), NULL StorageRoot (D3), deleted StorageRoot (D4), SQLAlchemy / psycopg2 round-trip (D5), JSON shape (D6), `__repr__` shape (D7). Adds five non-obvious cases the design surfaced: `__str__` shape (D8), construction-time `RelativePath` normalization (D9), `FromLegacyString` validation rules (D10), `Exists` vs `GetSize` failure-mode asymmetry (D11), immutability mechanism (D12).

- **Criterion 4 (seams enumerated):** 8 seams in `Core/Path/path.feature.md` `## Seams`. Directive-named: DB-row -> Path (S1), Path -> JSON (S2), Path -> worker (S3), Path -> log (S4), Path -> ffmpeg argv (S5). Three additions surfaced by the design: legacy canonical str -> Path (S6, migration surface), Path -> DB row write (S7, inverse of S1), Path -> canonical display (S8, UI-layer adapter). Each row carries Producer, Wire shape, Consumer expectation, runnable Verification.

- **Criterion 5 (test plan named):** 28 unit tests + 1 contract test enumerated in `Core/Path/path.feature.md` `## Verification (Test Plan)`. Covers every named area: shape parsing (UNC, Windows-drive, POSIX), equality across shapes, JSON round-trip, resolution against mock Worker, deleted StorageRoot, NULL StorageRoot. Tests named, not written -- the next directive (`path-class-implementation`) writes them.

- **Criterion 6 (no production code touched):** `git diff --stat HEAD -- ':!.claude/directive.md' ':!.claude/.refusal-state.json' ':!.claude/.task-delegation-on' ':!.claude/.session-state.json' ':!Core/Path/path.feature.md'` returns empty. Only modifications: `.claude/directive.md` (writable artifact for this directive), `Core/Path/path.feature.md` (the promotion target), session-state files. Zero `.py`, `.sql`, `.html`, `.js`, `.css` changes.

- **Criterion 7 (one session):** Directive opened 2026-06-04 (header `**Set:** 2026-06-04`), VERIFYING and DELIVERING entered same session 2026-06-04. Close lands same session.

### Decisions Made

Twelve design decisions, full table in `Core/Path/path.feature.md` `## Semantic Decisions`. One-line summary by ID:

- **D1** Equality is `(StorageRootId, RelativePath)` tuple equality.
- **D2** Case-SENSITIVE on `RelativePath`. DB stores exact bytes.
- **D3** Constructor rejects NULL `StorageRootId`. `FromRow` returns `Optional[Path]`.
- **D4** Deleted StorageRoot: Path construction succeeds, `Resolve` raises, `Exists` returns False.
- **D5** No psycopg2 / SQLAlchemy import inside `Core/Path/Path.py`.
- **D6** JSON shape `{"StorageRootId": int, "RelativePath": str}`. No `Display` field.
- **D7** `__repr__` is `<Path #<id>:<relpath>>`. No DB lookup.
- **D8** `__str__` == `__repr__`.
- **D9** Construction normalizes `RelativePath`: backslash -> forward slash, leading separators stripped, `..` rejected.
- **D10** `FromLegacyString` case-insensitive prefix match, longest-prefix-wins, raises on no-match.
- **D11** `Exists/IsFile/IsDir` catch resolution failure as `False`; `GetSize/GetMTime` raise.
- **D12** Immutable. Structural ops return new instances.

Two decisions flagged for operator awareness (defensible alternatives exist):

- **D2 (case sensitivity):** alternative is case-INSENSITIVE equality (matches SMB-share reality). Recommend keep D2 as-is. If MediaVortex ever scans data where the same logical file appears under multiple cases in the DB, D2 flips and scanner gets normalization responsibility.
- **D6 (JSON shape):** alternative is hybrid `{StorageRootId, RelativePath, Display}`. Recommend keep D6 as-is. If a non-MediaVortex API consumer is added, Display can be embedded at the API-response layer without changing `Path.ToJsonDict()`.

### Delivery Report

```
DIRECTIVE: path-class-design -- ratify the v2 Path class design as a feature.md contract.

STATUS: Done

WHAT SHIPPED:
- Core/Path/path.feature.md (new): full Path class design contract.
  - Slug, Workflows (W1-W7), Class Surface (21 methods/properties across 5 categories), Semantic Decisions (D1-D12), Success Criteria (C1-C15), Seams (S1-S8), Verification / Test Plan (28 unit + 1 contract test named).

HOW TO USE IT:
- Read Core/Path/path.feature.md before opening the next directive (path-class-implementation).
- The feature doc is the implementation contract: every method named there with its semantics IS what gets written. Tests named in the Verification section are the acceptance gate for the next directive.
- Reference: Worker Protocol section names the structural type Path.Resolve consumes; concrete Worker class lands in directive v2-substrate-buildout per .claude/programs/v2-decision.md.

WHAT YOU NEED TO EXECUTE:
- Nothing. Design directives are doc-only; no service restart, no deploy, no canary.
- When ready, open the next directive with `/n path-class-implementation`. The Files block in path.feature.md's `## Status` lists the targets.

CRITERIA VERIFICATION:
- C1 PASS -- doc exists at Core/Path/path.feature.md with Slug + W*/C*/S*/D* stable IDs; passes all 5 litmus tests.
- C2 PASS -- 21 methods/properties enumerated with types + semantics; no TBD.
- C3 PASS -- 12 D-decisions with answer + reasoning each.
- C4 PASS -- 8 seams in the Seams table.
- C5 PASS -- 28 unit tests + 1 contract test named.
- C6 PASS -- zero production code touched (verified via git diff).
- C7 PASS -- single session, opened and closed 2026-06-04.

DECISIONS I MADE:
- Class surface chose 21 methods, including two beyond the directive's minimum: __str__ (mirror of __repr__, no DB call on f-string coercion) and CanonicalDisplay(prefixes) (UI-display adapter that doesn't reach into the DB).
- D2 case-sensitive equality chosen over case-insensitive. Trade-off documented in `### Decisions Made`.
- D6 typed-pair JSON shape chosen over hybrid-with-Display. Trade-off documented.
- D11 asymmetric failure modes: Exists/IsFile/IsDir return False on resolution failure; GetSize/GetMTime raise. The asymmetry is intentional -- existence checks ask "is this useful right now?", read ops need to distinguish "no file" from "no path resolution".
- D9 construction-time normalization (backslash -> forward slash, leading separators stripped, `..` rejected) added so D2 case-sensitive equality can't be defeated by callers passing un-normalized input.
- Worker is specified as a Protocol (structural type) rather than a concrete class, deferring the concrete Worker to v2-substrate-buildout. Path doesn't need to wait for Worker to be implementable.

KNOWN GAPS / DEFERRED:
- No production code. By design (Criterion 6). Implementation is the next directive.
- Worker concrete type is forward-dependent. `path-class-implementation` may proceed with a structural Protocol shim; the concrete Worker lands in `v2-substrate-buildout`.
- `MediaFiles.FilePath` -> `(StorageRootId, RelativePath)` schema migration is multiple directives away. Path's `FromRow` is designed to work against either schema (NULL StorageRootId returns None from FromRow), so the migration can be staged.
```

## Closure

Promotions complete. Design contract durable in `Core/Path/path.feature.md`. All seven acceptance criteria pass (evidence in `### Verification`). Zero production code touched. Single-session wall clock. Next directive in the v2 phased plan (per `.claude/programs/v2-decision.md`) is `path-class-implementation` -- writes `Core/Path/Path.py` (~200 LOC) plus the 28 unit tests + 1 contract test named in the feature doc. Operator opens it via `/n path-class-implementation` when ready.
