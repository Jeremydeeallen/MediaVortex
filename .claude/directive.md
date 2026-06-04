# Current Directive

**Set:** 2026-06-04
**Status:** Active -- phase: NEEDS_STANDARDS_REVIEW
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

Active 2026-06-04 -- phase: NEEDS_STANDARDS_REVIEW -- ready for next session.

**First action next session:** invoke `superpowers:brainstorming` before writing any of the feature doc. The skill's description: "You MUST use this before any creative work -- creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation." This directive IS creative work (designing a new aggregate's full surface), so the brainstorm loop is mandatory by the skill's own contract. Use it to surface edge cases (null StorageRoot, deleted StorageRoot, JSON round-trip, repr shape, equality across shape variants) BEFORE attempting prose. Operator stress-tests the design during the brainstorm; doc-writing comes after.

### Files

```
Core/Path/path.feature.md    -- CREATE: v2 feature doc; the design contract
```

(Zero production code touched. R13 relaxes for new feature docs at DELIVERING; the design directive lives entirely in the doc.)

### Promotions

Populated at DELIVERING. Anticipated:

| Source artifact | Target file | Commit |
|---|---|---|
| `Path` class surface + semantics + seams + test plan | `Core/Path/path.feature.md` (new) | TBD |
| (any v2-shape decisions that affect future directives) | `.claude/programs/v2-decision.md` (update) | TBD |

### Verification

Populated at VERIFYING. One entry per acceptance criterion.

- **Criterion 1:** Path to `Core/Path/path.feature.md` + grep for stable IDs (W*, C*, S*).
- **Criterion 2:** Enumeration of methods + their type signatures (point to doc section).
- **Criterion 3:** Enumeration of named semantic decisions (point to doc section).
- **Criterion 4:** Seams table content (point to doc section).
- **Criterion 5:** Test plan section content (point to doc section).
- **Criterion 6:** `git diff` on production code = empty.
- **Criterion 7:** Session timestamp from open to close.

### Decisions Made

Populated as design decisions land during writing. Anticipated decision points:
- Equality semantics across shape representations.
- Case sensitivity policy.
- NULL / deleted StorageRoot behavior.
- JSON serialization shape for API.
- `__repr__` shape for logs.
- Migration adapter surface (`FromCanonicalString` validation rules).
