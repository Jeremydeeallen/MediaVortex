# Backlog Directive: PathStorage Size Budget -- C4 invariant violation

**Filed:** 2026-06-04 (by `paths-canonical-completion` close-out)
**Status:** Backlog -- not yet started
**Slug:** pathstorage-size-budget
**Triggered by:** `paths-canonical-completion` (closed 2026-06-03) grew `Core/Path/LocalPath.py + Core/Path/Path.py` from 47 LOC to ~230 LOC. `Core/Path/path.feature.md` criterion 4 explicitly says "surviving translation code is small and OS-blind, < 50 LOC". That invariant is now violated. The new code IS OS-blind (the canonical surface is shape-preserving), but it's no longer small. Until the feature doc and the code agree, anyone reading `Core/Path/path.feature.md` will think the codebase is out of compliance.

## Outcome

`Core/Path/path.feature.md` C4 and `Core/Path/LocalPath.py + Core/Path/Path.py` agree on the size budget. Either C4 is updated to reflect the new canonical-surface scope, OR the file is split into a package so the original 50-LOC contract holds for the translation core. The operator picks which.

## Acceptance Criteria

This directive requires an OPERATOR DECISION before implementation. The two paths:

### Path A: Accept the new size (edit C4)

A1. `Core/Path/path.feature.md` C4 is updated to reflect that `Core.Path.LocalPath / Core.Path.Path` now owns string ops + FS-op wrappers in addition to canonical-to-local translation. The "< 50 LOC" cap is replaced with an explicit budget naming what's inside the file (e.g. "translation surface + shape-preserving string ops + FS-op wrappers < 300 LOC; no drive-letter regex; no os.path.X usage except internally").

A2. The feature doc's Verification block adds a per-region size note: `Resolve/Parse/CanonicalFor/LoadStorageRoots` < 60 LOC; string ops < 60 LOC; FS-op wrappers < 80 LOC.

A3. `grep` for the OS-blind invariant ("no `[A-Za-z]:` parsing in the surviving code") still passes against the larger file.

### Path B: Split into a package (preserve C4 literally)

B1. `Core/Path/LocalPath.py + Core/Path/Path.py` becomes `Core/Path/__init__.py` re-exporting from sub-modules: `Core/Path/Translate.py` (Resolve, Parse, CanonicalFor, LoadStorageRoots -- the original < 50 LOC contract), `Core/Path/StringOps.py` (LastSegment, ParentDir, Join, SplitExt), `Core/Path/FsOps.py` (Exists, IsFile, IsDir, GetSize, GetMTime, ToLocal, LocalExists, LocalIsFile, LocalIsDir, LocalGetSize, LocalGetMTime).

B2. Every existing `from Core.Path.LocalPath / Core.Path.Path import ...` import line in the codebase continues to work without change (re-exports preserve the public API).

B3. `Core/Path/path.feature.md` C4 explicitly notes that "Translation core in `Core/Path/Translate.py` is < 50 LOC; surrounding modules in the package add canonical-surface ops without bloating the translation core."

### Path C: Hybrid (split shape-preserving ops out, accept FS-op size)

C1. Move only the FS-op wrappers to `Core/Path/FsOps.py`. String ops stay inline with Translate in `__init__.py` (small enough to live together). Sizing: `__init__.py` < 120 LOC, `FsOps.py` < 80 LOC.

## Out of Scope

- Adding more canonical functions (those are tracked by `paths-normalize-completion`).
- Splitting `WorkerContext` or any other Core module -- this directive is about `PathStorage` only.
- Renaming any function in the public API -- migration debt should be zero.

## Reference

Parent directive (closed): `.claude/directives/closed/2026-06-03-paths-canonical-completion.md`
Source contract: `Core/Path/path.feature.md` criterion 4
Current file: `Core/Path/LocalPath.py + Core/Path/Path.py` (~230 LOC as of 2026-06-04)

## Operator Decision Needed

Pick A, B, or C. Each is a ~half-day directive (Path A is the cheapest, Path B is the cleanest, Path C is the middle road). Until this decision lands, the path-storage feature doc and the code disagree.
