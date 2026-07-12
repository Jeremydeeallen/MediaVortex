---
description: Use when touching a file or directory path in MediaVortex Python code -- about to call `os.path.*`, compare two paths with `==`, or do filesystem I/O on a path variable. Surfaces the `Core.Path.LocalPath / Core.Path.Path` public API and the canonical-vs-local decision before the R6 hook refuses.
argument-hint: <none>
---

# MediaVortex Paths

## Overview

MediaVortex paths mix UNC (`\\server\share\...`), Windows-drive (`T:\...`), and POSIX (`/mnt/...`) shapes. `os.path.*` is platform-dependent and silently wrong on the wrong worker. `Core.Path.LocalPath / Core.Path.Path` is the only correct surface. The R6 hook (`.claude/hooks/pre-edit-standards.ps1:768`) catches violations after they're typed; this skill is the proactive companion.

## Quick Reference

| Need | Public API |
|---|---|
| `os.path.dirname` | `ParentDir(path)` |
| `os.path.basename` | `LastSegment(path)` |
| `os.path.join` | `Join(base, child)` |
| `os.path.splitext` | `SplitExt(path)` |
| `os.path.normpath` | `Normalize(path)` (shape-preserving; does NOT lowercase) |
| `os.path.normcase(a) == os.path.normcase(b)` | `PathsEqual(a, b)` (auto-detects case sensitivity from shape; override via `case_insensitive=`) |
| `os.path.exists` (canonical DB path) | `Exists(canonical, worker)` |
| `os.path.exists` (worker-resolved path) | `LocalExists(local_path)` |
| `isfile / isdir / getsize / getmtime` | canonical: `IsFile/IsDir/GetSize/GetMTime(canonical, worker)`; local: `LocalIsFile/LocalIsDir/LocalGetSize/LocalGetMTime(local_path)` |
| canonical -> worker-local absolute | `Resolve(StorageRootId, RelativePath, WorkerName)` or `ToLocal(canonical, worker)` |

## Canonical vs Local

The most common wrong call. Always know which kind of path is in hand.

**Canonical** -- came from a DB column (`MediaFiles.FilePath`, `TranscodeQueue.FilePath`, `MediaFilesArchive.FilePath`, etc.). Shape is Windows-flavored regardless of host OS. Cannot do I/O directly; needs `Resolve` or one of the canonical-aware wrappers.
- Use: `Exists(canonical, worker)`, `IsFile(canonical, worker)`, `GetSize(canonical, worker)`, `Resolve(...)`, `ToLocal(...)`.

**Local** -- already worker-resolved, or born local: ffmpeg binary path, `.inprogress` staging artifact, return value of `Resolve()`, the `LocalPath` field on `TemporaryFilePaths`.
- Use: `LocalExists(p)`, `LocalIsFile(p)`, `LocalGetSize(p)`.

**Pure string comparison** -- neither side is about to hit the filesystem (excluded-dirs membership, self-overwrite guard, dedup keys). Use `Normalize(p)` to canonicalize and `PathsEqual(a, b)` to compare.

## Public Surface Boundary

**STOP. Names with a leading underscore in `Core.Path.LocalPath / Core.Path.Path` are MODULE-PRIVATE. Importing `_PickPathFlavor`, `_WIN_DRIVE_RX`, `_STORAGE_ROOTS_CACHE`, or `_PREFIX_BY_ID_CACHE` from outside `Core/Path/LocalPath.py + Core/Path/Path.py` is a refusal -- not a tradeoff to flag. Do not import them. Do not "note the tradeoff" and import them anyway. Do not write a wrapper around them.**

The leading underscore is the contract: the maintainer reserves the right to rename, remove, or change the signature of these symbols without warning. External callers who depended on them break silently. That is exactly the kind of cross-shape latent bug the canonical layer exists to prevent.

If the public API doesn't fit, **the answer is to extend the public API, not to bypass it**. Open a follow-up directive that adds the public function you need. Don't ship the private import "for now."

### Rationalization counter: "I need an O(n) hash key for dedup / set membership"

This is the exact thought that causes the wrong answer. Read it before you write it.

**The thought:** "`PathsEqual` is O(n) pairwise -- wrong for dedup of N paths. I'll lift the case-folding rule from `_PickPathFlavor` into a hash key."

**Why it's wrong:** the path layer's case rule lives in one place precisely so this kind of "I'll just lift it" reuse doesn't fork. Two callers lifting the same logic = two copies that drift the first time the rule changes (a new shape, a new TLA on top of `ntpath`). The R6 hook + the `paths-must-be-shape-agnostic` memory entry exist because exactly this pattern produced production bugs before.

**The right answer:**

| Situation | Do this |
|---|---|
| Small list (< ~50 paths: excluded-dirs, output-collision candidates, per-job sets) | Pairwise `PathsEqual(a, b)` in an O(n^2) loop. Concrete cost: 2,500 string compares for n=50. Fine. |
| Larger list with a real O(n) requirement | Open a directive (`/n compare-key-on-pathstorage` or similar) to add a public `CompareKey(path)` to `Core/Path/LocalPath.py + Core/Path/Path.py`. Land it in one commit. Then dedup with `seen.add(CompareKey(p))`. |
| In a hurry, just ship | Use the O(n^2) loop. n=50 is fine; n=500 still completes in microseconds. The instinct that "O(n^2) is wrong" is theoretical for the path sizes this code base sees. |

The forbidden answer is "import `_PickPathFlavor` to build my own key." That ships the same case-rule logic in two files. The whole point of `Core.Path.LocalPath / Core.Path.Path` is that the rule lives in exactly one place.

### Concrete dedup pattern (use this verbatim)

```python
from Core.Path.LocalPath / Core.Path.Path import PathsEqual

def DeduplicatePaths(Paths):
    """Return Paths with duplicates removed, preserving order of first occurrence."""
    Result = []
    for P in Paths:
        if P is None:
            continue
        if any(PathsEqual(P, Existing) for Existing in Result):
            continue
        Result.append(P)
    return Result
```

O(n^2). Public-API only. Correct on every shape. Ship it.

## Common Mistakes

| Wrong | Right | Why |
|---|---|---|
| `os.path.normcase(a) == os.path.normcase(b)` | `PathsEqual(a, b)` | `normcase` is a no-op on POSIX; equality silently wrong cross-worker. |
| `os.path.normpath(p)` | `Normalize(p)` | `normpath` uses host flavor; on Linux it mangles `T:\Show` into a single literal. |
| `os.path.dirname(canonical)` | `ParentDir(canonical)` | `dirname` uses host separator; canonical paths are Windows-flavored. |
| `os.path.join(canonical, child)` | `Join(canonical, child)` | Host-separator on a Windows-shaped string. |
| `LocalExists(canonical_from_db)` | `Exists(canonical, worker)` | Canonical needs `Resolve` first. |
| `Exists(local_path, worker)` | `LocalExists(local_path)` | Local paths are already worker-side; `Exists` would re-translate. |
| `from Core.Path.LocalPath / Core.Path.Path import _PickPathFlavor` | `from Core.Path.LocalPath / Core.Path.Path import Normalize, PathsEqual` | Module-private. Use the public API; surface a gap if it doesn't fit. |
| Building a set key with `Normalize(p).lower()` | pairwise `PathsEqual` (or open directive for `CompareKey`) | Unconditional `.lower()` is wrong for POSIX paths. |

## Resources

- `Core/Path/path.feature.md` -- the contract (criteria, public surface, migration phases).
- `Core/Path/path.feature.md` -- `Resolve` stages (ST1-ST4) + cross-stage seams.
- `Core/Path/LocalPath.py + Core/Path/Path.py` -- the implementation.
- R6 hook at `.claude/hooks/pre-edit-standards.ps1:768` -- reactive enforcement; refuses `os.path.{dirname|basename|join|split|splitext|exists|isfile|isdir|getsize|getmtime|abspath|realpath|normpath|normcase}(pathvar)` with the per-op canonical answer.
- `memory/feedback_paths_must_be_shape_agnostic.md` -- why this rule exists.
- `memory/feedback_hook_path_forward_is_the_answer.md` -- when R6 fires, do exactly what the refusal says; do not invent a clever variant.
