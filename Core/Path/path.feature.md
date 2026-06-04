# Path

**Slug:** path

## What It Does

`Path` is the canonical typed representation of a media file's location in MediaVortex v2. Every reference to a file -- in code, in the DB, in API responses, in queue rows -- is a `Path` instance backed by `(StorageRootId: int, RelativePath: str)`. The class is the single boundary at which canonical identity becomes worker-local string: `path.Resolve(worker) -> str` is the only public method that yields a string suitable for `os.open()`, `ffmpeg`, or any other I/O. Everything else is identity, structural transformation, or serialization that preserves the typed pair.

## Workflows

| # | Consumer pattern | Surface | Backing class.method |
|----|---|---|---|
| W1 | Repository loads a media row -> returns `Path` | `MediaFilesRepository.FindById(id) -> MediaFile` (carries `Path`) | `Path.FromRow(row, prefix="")` |
| W2 | API response serializes path | `GET /api/queue/{id}` -> JSON body | `Path.ToJsonDict() -> dict` |
| W3 | Worker resolves canonical -> local for ffmpeg | `FFmpegService.RunTranscode(path, ...)` | `Path.Resolve(worker) -> str` |
| W4 | Log line includes path identity | `LoggingService.LogInfo("...", path=path)` | `Path.__repr__() -> str` |
| W5 | Worker checks file existence before claim | `WorkerHealthCheck.CanClaim(path)` | `Path.Exists(worker) -> bool` |
| W6 | Migration tool parses legacy canonical -> typed pair | `BackfillStorageColumns.PopulateRow(canonical_str, roots)` | `Path.FromLegacyString(canonical, roots) -> Path` |
| W7 | Operator UI shows canonical display in tables | `/Queue/{id}` view -> renders `T:\Show\file.mkv` | `Path.CanonicalDisplay(prefixes) -> str` |

## Class Surface

### Construction

| Method | Returns | Semantics |
|---|---|---|
| `Path(storage_root_id: int, relative_path: str)` | `Path` | Strict constructor. Raises `PathError` if `storage_root_id` is None / non-int, or `relative_path` is None / empty / starts with `/` or `\` / contains `..` segment. Backslashes in `relative_path` normalized to forward slashes (D9) before storage. |
| `Path.FromPair(storage_root_id, relative_path) -> Path` | `Path` | Alias of constructor for explicit-name call sites. |
| `Path.FromRow(row: dict, prefix: str = "") -> Optional[Path]` | `Optional[Path]` | Reads `<prefix>StorageRootId` and `<prefix>RelativePath` from a `CaseInsensitiveDict` row. Returns `None` if either is NULL (legacy unmigrated row). `prefix` lets one row carry multiple paths (e.g., `"Output"` reads `OutputStorageRootId` / `OutputRelativePath`). |
| `Path.FromLegacyString(canonical: str, storage_roots: list[dict]) -> Path` | `Path` | Parses a v1-shape canonical string (UNC / Windows-drive / POSIX). `storage_roots` is `[{'Id': int, 'CanonicalPrefix': str}, ...]` sorted by `len(CanonicalPrefix)` DESC. Raises `PathError` if no prefix matches or input is empty. Case-insensitive prefix match; case-preserving on relative tail. Migration-tool surface only -- runtime code uses `FromRow`. |
| `Path.FromJsonDict(payload: dict) -> Path` | `Path` | Inverse of `ToJsonDict`. Reads `{"StorageRootId": int, "RelativePath": str}`. Raises `PathError` on shape mismatch. |

### Identity

| Method / Property | Returns | Semantics |
|---|---|---|
| `path.StorageRootId` | `int` | Read-only property. |
| `path.RelativePath` | `str` | Read-only property. Always normalized per D9 (forward slashes, no leading slash). |
| `path == other` | `bool` | True iff `other` is `Path` and `(StorageRootId, RelativePath)` tuples are byte-equal. Case-sensitive on `RelativePath` (D2). |
| `hash(path)` | `int` | Hash of `(StorageRootId, RelativePath)` tuple. Hashable; usable as dict key / set member. |
| `repr(path)` | `str` | Stable shape: `<Path #7:Show/file.mkv>`. No DB lookup (D7). |
| `str(path)` | `str` | Same as `repr(path)` (D8). |

### Structural Operations

All return new `Path` instances (frozen / immutable -- D12; no mutation).

| Method | Returns | Semantics |
|---|---|---|
| `path.ParentDir() -> Path` | `Path` | Parent within the same StorageRoot. Raises `PathError` when `path` is at the StorageRoot itself (`RelativePath == ""`). |
| `path.LastSegment() -> str` | `str` | Trailing segment of `RelativePath` (filename or terminal dir name). Empty only when `RelativePath` is empty. |
| `path.SplitExt() -> tuple[Path, str]` | `tuple[Path, str]` | `(Path with extension stripped, ".ext")`. Extension includes the dot. `("", "")` only on root paths. Extensionless input returns `(self, "")`. |
| `path.Join(child: str) -> Path` | `Path` | Appends `child` with forward slash. Raises `PathError` if `child` contains `..` or absolute markers (`/`, `\`, drive letter). |

### Resolution / I/O

All require a `worker: Worker` argument. Worker protocol below.

| Method | Returns | Semantics |
|---|---|---|
| `path.Resolve(worker: Worker) -> str` | `str` | Worker-local absolute path string. Raises `PathError` when `worker.ResolveStorageRoot(path.StorageRootId)` returns None (orphaned / inactive StorageRoot -- D4). The sole public method yielding a `str` suitable for I/O. |
| `path.Exists(worker) -> bool` | `bool` | True iff the resolved path exists. Resolution failure -> `False` (callers of existence checks don't unwrap PathError -- D11). |
| `path.IsFile(worker) -> bool` | `bool` | True iff resolved path is an existing file. Same catch-as-False semantics. |
| `path.IsDir(worker) -> bool` | `bool` | True iff resolved path is an existing directory. Same catch-as-False semantics. |
| `path.GetSize(worker) -> int` | `int` | File size in bytes. Raises `FileNotFoundError` if missing; raises `PathError` if StorageRoot orphaned (D11 -- read ops distinguish "no file" from "no path resolution"). |
| `path.GetMTime(worker) -> float` | `float` | POSIX mtime. Same raise semantics as `GetSize`. |

### Serialization

| Method | Returns | Semantics |
|---|---|---|
| `path.ToJsonDict() -> dict` | `dict` | `{"StorageRootId": int, "RelativePath": str}`. Stable shape (D6); round-trips through `FromJsonDict`. |
| `path.CanonicalDisplay(prefixes: dict[int, str]) -> str` | `str` | Joins `prefixes[StorageRootId]` + `RelativePath` (backslash-normalized) for human-readable display. Caller passes the pre-loaded prefix map; class does NOT touch the DB. Orphan id renders as `[orphan #<id>] <relative_path>`. |

### Worker Protocol

`Path` consumes a structural `Worker` type:

```python
class Worker(Protocol):
    Name: str
    Platform: str  # 'windows' | 'linux' | 'mac'
    def ResolveStorageRoot(self, storage_root_id: int) -> Optional[str]: ...
```

`ResolveStorageRoot` returns the worker-local absolute prefix for the StorageRoot (e.g., `T:\` or `/mnt/media_tv/`) or `None` when no active resolution exists. `Path.Resolve` joins this prefix to `RelativePath` using the worker-platform separator (`Platform` field picks backslash vs forward slash). The concrete `Worker` class lands in directive `v2-substrate-buildout` per the phased plan; this directive specifies only the protocol surface `Path` requires.

## Semantic Decisions

Explicit answers to every non-obvious case the design surfaced.

| D# | Question | Decision | Reasoning |
|---|---|---|---|
| D1 | Equality across shape variants (UNC vs drive-letter representing the same canonical pair) | By `(StorageRootId, RelativePath)` tuple. Shape is not a concept the class has. | v1 ambiguity eliminated at the type level. Two paths resolving to the same file under the same root on the same worker ARE the same `Path`. |
| D2 | Case sensitivity on `RelativePath` | Case-SENSITIVE equality. | DB stores exact bytes; scanner canonicalizes case at ingest. Identity reflects DB row identity, not filesystem identity. Case-insensitive filesystems are an I/O concern at the worker boundary, not a Path identity concern. |
| D3 | NULL `StorageRootId` handling | Constructor rejects None / non-int with `PathError`. `Path.FromRow(row)` returns `Optional[Path]` -- `None` for legacy unmigrated rows. | Forces the migration-vs-runtime distinction at the type system. Runtime code never holds a half-typed Path. |
| D4 | Deleted `StorageRoot` row | Construction succeeds (Path is a value object; no DB read at construction). `Resolve(worker)` raises `PathError` when `worker.ResolveStorageRoot(id)` returns None. `Exists/IsFile/IsDir` catch and return False. `__eq__`, `__hash__`, `__repr__`, `ToJsonDict` work unchanged. | Validation cost paid only at the I/O boundary. Pure value-object semantics -- Path identity doesn't depend on DB state. |
| D5 | SQLAlchemy / psycopg2 round-trip | `Path` does not know about ORM layer. Repositories call `FromRow` on reads and `(p.StorageRootId, p.RelativePath)` unpack on writes. No psycopg2 / SQLAlchemy import inside `Core/Path/Path.py`. | Substrate-independence (per `.claude/programs/v2-decision.md`). Path is pure domain. |
| D6 | JSON serialization shape | `{"StorageRootId": int, "RelativePath": str}`. No `Display` field -- UI adds Display via `CanonicalDisplay(prefixes)` adapter at the response-build site. | Machine-to-machine API stays minimal and round-trippable. Display is a UI concern, not a Path concern. |
| D7 | `__repr__` shape | `<Path #7:Show/file.mkv>`. No DB lookup, no canonical-display join. | Cheap, deterministic, grep-friendly (`#7:` is a unique anchor). |
| D8 | `__str__` shape | Same as `__repr__`. | Predictable; no implicit DB call on string coercion. Implicit `str()` in f-strings does not trigger a DB query. |
| D9 | `RelativePath` normalization at construction | Backslashes -> forward slashes; leading `/` or `\` stripped; `..` segments rejected with `PathError`; case preserved. | Single canonical storage form; eliminates "double-form" equality bugs that would otherwise compromise D2. |
| D10 | `FromLegacyString` validation rules | Case-insensitive prefix match against `CanonicalPrefix`; longest-prefix wins (caller responsible for sort); empty / no-match raises `PathError`. Relative tail normalized per D9. | Mirrors v1 `Core.PathStorage.Parse()` behavior but raises instead of returning `(None, None)` -- migrations fail loudly. |
| D11 | `Exists/IsFile/IsDir` failure modes | Resolution failure (orphan StorageRoot) returns `False`, NOT raises. `GetSize/GetMTime` raises `PathError` / `FileNotFoundError`. | Existence checks are "is the path useful right now?" queries; raising would force every caller into try/except. Read ops must distinguish "no file" from "no path resolution" -- the failure mode carries operational signal. |
| D12 | Immutability enforcement | `@dataclass(frozen=True)` or equivalent (`__setattr__` raises after init). Structural ops return new instances. | Hashability + value-object semantics + safe to use as dict key / set member. |

## Success Criteria

| # | Criterion |
|---|---|
| C1 | `Path(7, "Show/file.mkv") == Path(7, "Show/file.mkv")` is True; both placed in a `set` collapse to one member. |
| C2 | `Path(7, "Show/file.mkv") != Path(7, "show/FILE.MKV")`. Case-sensitive identity (D2). |
| C3 | `Path(7, "Show/file.mkv") != Path(8, "Show/file.mkv")`. StorageRoot is part of identity. |
| C4 | `Path(None, "x")`, `Path(7, "")`, `Path(7, None)`, `Path(7, "/abs/path")`, `Path(7, "../escape")` each raise `PathError` at construction. |
| C5 | `Path.FromRow({"StorageRootId": None, "RelativePath": "x"})` returns `None`. `Path.FromRow({"StorageRootId": 7, "RelativePath": "Show/file.mkv"})` returns the expected Path. |
| C6 | `Path.FromLegacyString("T:\\Show\\file.mkv", [{"Id": 1, "CanonicalPrefix": "T:\\"}]).RelativePath == "Show/file.mkv"`. UNC, Windows-drive, and POSIX inputs all parse against a matching prefix. |
| C7 | `Path.FromJsonDict(p.ToJsonDict()) == p` for any constructed Path. |
| C8 | `p.Resolve(worker)` returns `worker.ResolveStorageRoot(p.StorageRootId)` joined with `p.RelativePath` using the worker-platform separator. `T:\Show\file.mkv` shape on a Windows worker, `/mnt/media_tv/Show/file.mkv` on a Linux worker. |
| C9 | `p.Resolve(worker)` raises `PathError` when `worker.ResolveStorageRoot(p.StorageRootId)` returns None. |
| C10 | `p.Exists(worker)` returns `False` (not raises) when the StorageRoot is orphaned. |
| C11 | `repr(p)` returns `<Path #7:Show/file.mkv>` exactly. No DB lookup; no variation between runs. |
| C12 | `p.ParentDir().Join(p.LastSegment()) == p` for any non-root Path. |
| C13 | `Path(7, "")` is the root; `p.ParentDir()` raises `PathError` on root. |
| C14 | `Path(7, "Show/file.mkv").SplitExt() == (Path(7, "Show/file"), ".mkv")`. SplitExt on extensionless input returns `(self, "")`. |
| C15 | Attempting `path.RelativePath = "x"` raises (frozen). |

## Seams

Intra-feature seams the class participates in.

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | DB row -> Path | Repository SELECT on a path-bearing table | `{"StorageRootId": int \| None, "RelativePath": str \| None}` (CaseInsensitiveDict) | `Path.FromRow(row, prefix)` returns `Optional[Path]` | `Tests/Unit/test_path_fromrow.py` (round-trips synthetic row dict) |
| S2 | Path -> JSON API response | `Path.ToJsonDict()` | `{"StorageRootId": int, "RelativePath": str}` | API consumer parses the typed pair; UI-side `CanonicalDisplay` joined into response payload at the API layer when needed | `Tests/Unit/test_path_json.py` (round-trips `Path -> ToJsonDict -> FromJsonDict -> Path`) |
| S3 | Path -> worker-local string | `Path.Resolve(worker)` | platform-correct absolute path string | Consumer feeds the string to `os.open` / `subprocess` / `ffmpeg` | `Tests/Unit/test_path_resolve.py` (mock Worker returning known prefix) |
| S4 | Path -> log line | `Path.__repr__()` | `<Path #<id>:<relpath>>` | LoggingService formats as a single field; grep on `#<id>:` works | `Tests/Unit/test_path_repr.py` (asserts exact shape) |
| S5 | Path -> ffmpeg argv | `Path.Resolve(worker)` then `str` | quoted absolute path string | `FFmpegService.RunTranscode` includes the string as a positional argv element | `Tests/Unit/test_path_resolve.py` (asserts D8/C8 worker-platform separator behavior) |
| S6 | Legacy canonical str -> Path | `Path.FromLegacyString(canonical, roots)` | UNC `\\host\share\...`, Windows `T:\...`, POSIX `/mnt/.../...` | Migration script reads canonical column, constructs Path, writes typed columns | `Tests/Unit/test_path_legacy.py` (parameterized over the three shapes) |
| S7 | Path -> DB row | Repository INSERT / UPDATE | `INSERT (..., StorageRootId, RelativePath) VALUES (..., %s, %s)` with `(p.StorageRootId, p.RelativePath)` | DB row written; next `FromRow` round-trips | `Tests/Contract/TestPathDbRoundTrip.py` (insert + select against test schema) |
| S8 | Path -> canonical display | `Path.CanonicalDisplay({1: "T:\\", 2: "\\\\10.0.0.61\\xxx\\"})` | backslash-joined absolute display string | UI tables / log lines render verbatim; orphan id renders as `[orphan #<id>] <relpath>` | `Tests/Unit/test_path_display.py` (asserts resolved vs orphan branches) |

## Verification (Test Plan)

Unit tests that will exist when the class ships. Names only; bodies belong to the next directive (`path-class-implementation`).

| Test | Asserts |
|---|---|
| `test_path_construction.py::test_strict_constructor_rejects_invalid` | C4 -- all invalid inputs raise `PathError`. |
| `test_path_construction.py::test_relative_path_normalized` | D9 -- backslashes -> forward slashes, leading slash stripped, case preserved. |
| `test_path_equality.py::test_equal_when_typed_pair_matches` | C1 -- equality by tuple. |
| `test_path_equality.py::test_case_sensitive_on_relative_path` | C2, D2. |
| `test_path_equality.py::test_storage_root_part_of_identity` | C3. |
| `test_path_hash.py::test_usable_in_set_and_dict` | C1 collapse + hashing contract. |
| `test_path_fromrow.py::test_returns_none_for_legacy_null_row` | C5 -- D3 NULL handling. |
| `test_path_fromrow.py::test_reads_with_prefix` | `prefix="Output"` reads `OutputStorageRootId` / `OutputRelativePath`. |
| `test_path_legacy.py::test_parses_unc` | S6 UNC shape. |
| `test_path_legacy.py::test_parses_windows_drive` | S6 Windows-drive shape. |
| `test_path_legacy.py::test_parses_posix` | S6 POSIX shape. |
| `test_path_legacy.py::test_longest_prefix_wins` | D10 longest-prefix. |
| `test_path_legacy.py::test_no_match_raises` | D10 no-match. |
| `test_path_json.py::test_round_trip` | C7. |
| `test_path_json.py::test_shape_stable` | D6 -- exact key set. |
| `test_path_resolve.py::test_returns_worker_local_string` | C8. |
| `test_path_resolve.py::test_windows_worker_uses_backslash` | C8 Windows branch. |
| `test_path_resolve.py::test_linux_worker_uses_forward_slash` | C8 Linux branch. |
| `test_path_resolve.py::test_orphan_storage_root_raises` | C9, D4. |
| `test_path_existence.py::test_exists_returns_false_on_orphan` | C10, D11. |
| `test_path_existence.py::test_getsize_raises_on_orphan` | D11 distinction. |
| `test_path_repr.py::test_exact_shape` | C11, D7. |
| `test_path_structural.py::test_parentdir_join_lastsegment_identity` | C12. |
| `test_path_structural.py::test_parentdir_at_root_raises` | C13. |
| `test_path_structural.py::test_splitext` | C14. |
| `test_path_immutability.py::test_setattr_raises` | C15, D12. |
| `test_path_display.py::test_resolved_prefix` | S8 happy path. |
| `test_path_display.py::test_orphan_marker` | S8 orphan branch. |

All unit tests live under `Tests/Unit/`. `TestPathDbRoundTrip.py` is a contract test under `Tests/Contract/`.

## Status

DESIGN RATIFIED 2026-06-04 -- contract approved by `path-class-design` directive.

Implementation tracked in the next directive (`path-class-implementation`). When that directive opens, the Files block becomes:

```
Core/Path/Path.py                              -- CREATE: the class implementation (~200 LOC)
Tests/Unit/test_path_construction.py           -- CREATE
Tests/Unit/test_path_equality.py               -- CREATE
Tests/Unit/test_path_hash.py                   -- CREATE
Tests/Unit/test_path_fromrow.py                -- CREATE
Tests/Unit/test_path_legacy.py                 -- CREATE
Tests/Unit/test_path_json.py                   -- CREATE
Tests/Unit/test_path_resolve.py                -- CREATE
Tests/Unit/test_path_existence.py              -- CREATE
Tests/Unit/test_path_repr.py                   -- CREATE
Tests/Unit/test_path_structural.py             -- CREATE
Tests/Unit/test_path_immutability.py           -- CREATE
Tests/Unit/test_path_display.py                -- CREATE
Tests/Contract/TestPathDbRoundTrip.py          -- CREATE
```

Worker protocol is a forward dependency: `Path.Resolve` requires the `Worker` type defined in directive `v2-substrate-buildout`. Implementation may proceed with a structural `Worker` Protocol shim until the substrate lands.
