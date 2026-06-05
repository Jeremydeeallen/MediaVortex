# Path

**Slug:** path

## What It Does

`Path` is the canonical typed representation of a media file's location in MediaVortex v2. Every reference to a file -- in code, in the DB, in API responses, in queue rows -- is a `Path` instance backed by `(StorageRootId: int, RelativePath: str)`. The class is the single boundary at which canonical identity becomes worker-local string: `path.Resolve(worker) -> str` is the only public method that yields a string suitable for `os.open()`, `ffmpeg`, or any other I/O. Everything else is identity, structural transformation, or serialization that preserves the typed pair.

## Principle

`Path` is a value object. It accepts what a legitimate media-file filesystem produces, and rejects what such a filesystem cannot or could not honestly contain. Platform-specific dangers that travel cross-filesystem (a Linux-stored filename consumed by a Windows worker) are enforced at the I/O boundary, not at identity.

Two corollaries follow:

- **Construction-time rejections** target inputs that have no legitimate filesystem origin: NUL bytes, control characters (`\x00-\x1f`, `\x7f`), Win32 device namespace (`\\?\`, `\\.\`), UNC prefixes (`\\host\share`), leading `/` or `\` (already in D9), leading drive-letter (`^[A-Za-z]:`), and `..` segments.
- **Resolve-time platform-aware rejections** target inputs that a Linux/macOS scanner can legitimately produce but a Windows worker cannot safely consume: DOS device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9` as a segment basename), trailing dot or space per segment, mid-segment colons (NTFS Alternate Data Stream marker). On `worker.Platform == 'windows'`, `Resolve(worker)` raises `PathError`. On non-Windows workers, the same `RelativePath` resolves cleanly.

What gets accepted byte-wise at construction (no normalization, no scrubbing): Unicode in any encoding (D2 commits Path to byte equality; D13 confirms no normalization), mid-segment colons on non-Windows workers, anything else not in the rejection lists above. Normalization and adversarial scrubbing are scanner / ingest-layer concerns. The type mirrors what is in the DB.

## Threat Model

**Asset.** A `Path` instance is the canonical identity of a media file. It is consumed at three boundaries: (a) DB row read/write, (b) JSON API payloads, (c) worker-local I/O (`subprocess`, `os.open`, `ffmpeg` argv).

**Attacker goals.**

- **G1 Path traversal:** read or write a file outside any `StorageRoot`.
- **G2 Device open / DoS:** cause a Windows worker to open a kernel-object path (`\\.\COM1`, `CON`) instead of a file, hanging the worker or returning garbage.
- **G3 Alternate Data Stream exfiltration:** address an NTFS ADS (`file:secret`) via a path field on a Windows worker.
- **G4 Phantom-equality bug:** insert two `RelativePath` values that visually compare equal but byte-compare unequal (NFC/NFD twins, trailing dot/space on Windows), confusing dedup logic.
- **G5 C-string injection:** smuggle a NUL byte into a Resolved path so that `subprocess` argv receives only the prefix, opening a different file than the path claims.
- **G6 Log / terminal injection:** pass control characters that escape ANSI sequences in operator-facing logs.

**Attacker capabilities (in-scope).**

- **A1:** Controls full request body of an HTTP API endpoint that accepts a path (`StorageRootId`, `RelativePath`, or a canonical string). Highest-trust threat -- attacker writes arbitrary bytes into Path-bound fields.
- **A2:** Controls a canonical string fed to `Path.FromLegacyString` (e.g., a migration tool reads a file the attacker can write).
- **A3:** Controls filenames on a Linux/NFS share that a scanner ingests (attacker has filesystem write on a non-Windows source disk).

**Attacker capabilities (out of scope -- defense lives upstream).**

- Direct DB writes (requires PostgreSQL credentials; perimeter compromise).
- Modification of the `StorageRoots` table (same; the `FromLegacyString` prefix list is loaded from this table -- trust posture: prefix-list integrity == DB integrity).
- `MEDIAVORTEX_DB_HOST` / other env-var manipulation (process-spawn compromise).
- TOCTOU file-swap between `Exists(worker)` check and downstream `open()` -- racey by design; caller responsibility.
- Symlinks that point out of a StorageRoot -- filesystem-level concern; caller responsibility.

**Trust boundaries.**

- HTTP API surface -> `Path(...)` constructor: Path enforces what construction promises. Authentication / authorization happens upstream (Flask middleware).
- DB column -> `Path.FromRow(row)`: trusted (operator-only write authority).
- `Path.Resolve(worker)` output -> `subprocess` / `os.open`: this is the highest-risk boundary. Resolve-time platform-aware checks live here.

**Mapping goals to mitigations.**

| Goal | Mitigation |
|---|---|
| G1 path traversal | `..`-segment rejection + leading-separator rejection at construction (D9) |
| G2 device open | DOS device name rejection at `Resolve(worker)` when `worker.Platform == 'windows'` (D14) |
| G3 ADS exfiltration | Mid-segment colon rejection at `Resolve(worker)` when `worker.Platform == 'windows'` (D14) |
| G4 phantom equality | Trailing dot/space rejection at Resolve on Windows (D14); D2 + D13 commit Path to byte equality so NFC/NFD twins compare unequal at identity level |
| G5 NUL injection | NUL byte rejection at construction (D9 / D14) |
| G6 log injection | Control char (`\x00-\x1f`, `\x7f`) rejection at construction (D9 / D14) |

**Residual risks accepted.**

- An attacker with DB write authority can insert arbitrary `RelativePath` bytes that the Path constructor accepts. Mitigation: DB write authority is already a high trust grant; defense lives at the perimeter, not the type.
- An attacker controlling the on-disk filesystem of a source share can plant filenames that Resolve will reject on Windows workers. Defense in depth: the file simply will not transcode; this is a denial-of-service against that one file, not a path-traversal vulnerability.

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

## Performance Budget

`Path` is allocated at high frequency (FileScanning ingests 47K+ rows per pass) and called even more frequently (identity, hash, repr at log lines, JSON round-trips at API responses). Per-method budgets below are durable contract -- regressions catch via `py -m pytest Tests\Unit\test_path_performance.py -m perf`.

| Method | Budget (p99) | Measured (p99, I9 dev) | Notes |
|---|---:|---:|---|
| `__eq__` | < 10 us | 200 ns | tuple compare |
| `__hash__` | < 10 us | 200 ns | tuple hash |
| `__repr__` | < 10 us | 300 ns | f-string format |
| `__str__` | < 10 us | 200 ns | delegates to __repr__ |
| `ToJsonDict` | < 10 us | 100 ns | dict literal |
| `Path(...)` construction | < 100 us | 2.4 us | includes all D9/D14 regex checks |
| `Resolve(worker)` | < 1 ms | 200 ns | cached `worker.ResolveStorageRoot` |
| 50K consecutive constructions | < 5 s | 0.129 s | FileScanning batch projection |
| 10K consecutive Resolve calls | < 10 s | 0.001 s | transcode worker projection |
| `sys.getsizeof(Path)` | < 200 bytes | 48 bytes | `slots=True`, no `__dict__` |

**I/O-free invariant.** `__eq__`, `__hash__`, `__repr__`, `__str__`, `ToJsonDict`, and `FromJsonDict` do not touch the filesystem. Verified by `test_identity_methods_do_not_touch_filesystem` which patches `os.path.exists/isfile/isdir/getsize/getmtime` and `os.stat` with raising mocks during execution.

**Construction order matters.** `__post_init__` runs the security checks in a defined order: NUL/control chars first, then leading-marker / drive-letter / Win32-namespace / UNC, then backslash normalization, then `..`-segment check on the normalized form. Adding a new check at the wrong position can produce a false-accept; new D-decisions must specify their ordering relative to existing checks.

**Memory budget.** `@dataclass(frozen=True, slots=True)` keeps each Path at 48 bytes (vs. 344 bytes with `__dict__`). At 50K instances this saves ~14.8 MB. Required: any new instance attribute must be declared as a field; ad-hoc `setattr` will fail at runtime against the slots constraint.

## Migration Pattern (Phase 7 caller verticals)

Each v1 vertical migrates by removing `Core.PathStorage` imports and routing path consumption through `Path` + `Worker`. The pattern established by the pathfinder (`mediaprobe-uses-path`, closed 2026-06-04) is the canonical recipe for the remaining six verticals: FileScanning, FileReplacement, TranscodeJob, QualityTesting, TranscodeQueue, Activity.

**Imports:** swap `from Core.PathStorage import Resolve as PathResolve, LocalExists` (or any subset) for `from Core.Path import Path, Worker, PathError`.

**Worker as lazy instance state:**

```python
class FeatureBusinessService:
    def __init__(self, ...):
        ...
        self._Worker: Optional[Worker] = None
        self._StorageRoots: Optional[List[dict]] = None

    def _GetWorker(self) -> Worker:
        if self._Worker is None:
            self._Worker = Worker.FromWorkerContext()
        return self._Worker
```

The `Worker` instance carries the per-instance StorageRootResolutions cache (Phase 4 budget). One service instance == one Worker == one cache. Long-running batches benefit; per-request services pay the cache cost per request.

**Path resolution with FromLegacyString fallback:**

```python
def _ResolveWorkerLocal(self, MediaFile, FallbackFilePath):
    """Returns (local_path_str, Path_obj_or_None)."""
    if MediaFile.StorageRootId is not None and MediaFile.RelativePath:
        try:
            P = Path(MediaFile.StorageRootId, MediaFile.RelativePath)
            return (P.Resolve(self._GetWorker()), P)
        except PathError:
            pass
    if FallbackFilePath:
        try:
            P = Path.FromLegacyString(FallbackFilePath, self._GetStorageRoots())
            return (P.Resolve(self._GetWorker()), P)
        except PathError:
            pass
    return (FallbackFilePath, None)
```

Three-stage fallback: typed pair (canonical), `FromLegacyString` parse of the legacy `FilePath` column (handles unmigrated rows + orphan StorageRoot), raw string (logging-only sentinel). Each vertical adopts this verbatim; the only adaptation is which DB columns the row model exposes.

**Existence checks via `Path.Exists(worker)`:** when you have a `Path` object, use `P.Exists(worker)` rather than `os.path.exists(local_str)`. R6 path-shape hook fires on the latter for path-named variables. The `Path.Exists` method internally does the os.path.exists call but at a documented boundary (S5 seam).

**StorageRoots loader:** cache the StorageRoots prefix list per-instance for the `FromLegacyString` fallback path:

```python
def _GetStorageRoots(self) -> List[dict]:
    if self._StorageRoots is None:
        from Core.Database.DatabaseService import DatabaseService
        Rows = DatabaseService().ExecuteQuery(
            "SELECT Id, CanonicalPrefix FROM StorageRoots ORDER BY length(CanonicalPrefix) DESC"
        )
        self._StorageRoots = [{"Id": R.get("id", R.get("Id")),
                               "CanonicalPrefix": R.get("canonicalprefix", R.get("CanonicalPrefix"))}
                              for R in Rows]
    return self._StorageRoots
```

Per-instance cache; constructed on first miss; operator restart required to refresh (matches Worker semantics per D14).

**Test shape:** mock-DB unit tests cover the four `_ResolveWorkerLocal` branches (typed-pair / legacy-fallback / orphan-fallback / final-None). One live-DB smoke contract test confirms an actual MediaFile resolves to an on-disk-existing path on the operator's I9 / Larry workers.

**What stays the same:** operator-facing log messages (the existing `f"File does not exist on disk: {FilePath} (local: {LocalPath})"` shape is preserved verbatim), failure-tracking semantics (probe failures recorded the same way), downstream service signatures (`FileManager.ExtractMediaMetadata` still takes a `str` path -- it's at an I/O boundary). Migration is surgical, not architectural.

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
| D9 | `RelativePath` normalization at construction | Backslashes -> forward slashes; leading `/` or `\` rejected with `PathError`; leading drive-letter prefix (`^[A-Za-z]:`) rejected with `PathError`; `..` segments rejected with `PathError`; case preserved. Additional construction-time rejections (per D14): NUL byte and control chars (`\x00-\x1f`, `\x7f`), Win32 device namespace (`\\?\`, `\\.\`, `\\?\UNC\`), UNC prefix (`\\host\share`). | Single canonical storage form; eliminates "double-form" equality bugs that would otherwise compromise D2. Drive-letter prefixes (including bare `C:` and drive-relative `C:foo`) are Windows-specific absolute or drive-relative markers, not pure-relative paths -- callers parsing drive-letter inputs use `FromLegacyString`, not the constructor. |
| D13 | Unicode normalization | Accept any Unicode in `RelativePath` byte-wise; no NFC/NFD normalization at construction. Two Paths constructed from NFC and NFD encodings of the same visual string compare UNEQUAL. | Path is a value object that mirrors DB content (see Principle). Normalization is a scanner / ingest concern, not a Path concern. Silent normalization would break D2 byte-equal identity and `Path.FromJsonDict(p.ToJsonDict()) == p` round-trips. Cross-encoding duplicates are an ingest-layer bug; fix at scan time, not at type. |
| D14 | Platform-hazard placement | Inputs that no legitimate scanner produces (NUL, control chars, Win32 namespace, UNC prefix) are rejected at construction. Inputs that a Linux scanner can legitimately produce but a Windows worker cannot safely consume (DOS device names, trailing dot/space, mid-segment colons) are rejected at `Resolve(worker)` when `worker.Platform == 'windows'`. On non-Windows workers, the same RelativePath resolves cleanly. | Single architectural principle (see Principle) -- value-object identity is platform-agnostic; platform-specific dangers live at the I/O boundary where platform is known. |
| D10 | `FromLegacyString` validation rules | Case-insensitive prefix match against `CanonicalPrefix`; longest-prefix wins (caller responsible for sort); empty / no-match raises `PathError`. Relative tail normalized per D9. | Mirrors v1 `Core.PathStorage.Parse()` behavior but raises instead of returning `(None, None)` -- migrations fail loudly. |
| D11 | `Exists/IsFile/IsDir` failure modes | Resolution failure (orphan StorageRoot) returns `False`, NOT raises. `GetSize/GetMTime` raises `PathError` / `FileNotFoundError`. | Existence checks are "is the path useful right now?" queries; raising would force every caller into try/except. Read ops must distinguish "no file" from "no path resolution" -- the failure mode carries operational signal. |
| D12 | Immutability enforcement | `@dataclass(frozen=True)` or equivalent (`__setattr__` raises after init). Structural ops return new instances. | Hashability + value-object semantics + safe to use as dict key / set member. |

## Success Criteria

| # | Criterion |
|---|---|
| C1 | `Path(7, "Show/file.mkv") == Path(7, "Show/file.mkv")` is True; both placed in a `set` collapse to one member. |
| C2 | `Path(7, "Show/file.mkv") != Path(7, "show/FILE.MKV")`. Case-sensitive identity (D2). |
| C3 | `Path(7, "Show/file.mkv") != Path(8, "Show/file.mkv")`. StorageRoot is part of identity. |
| C4 | `Path(None, "x")`, `Path(7, None)`, `Path(7, "/abs/path")`, `Path(7, "../escape")` each raise `PathError` at construction. (Empty `RelativePath` is the root per C13, not rejected.) |
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
| S9 | `Path.Resolve` output -> `Core/Path/LocalPath.py` helpers | worker-resolved local paths (output of `Path.Resolve(Worker)`) | local OS-native string (Windows backslash or POSIX forward slash, per worker platform) | code needing `basename` / `dirname` / `exists` / `join` on those local strings; `LocalPath` wraps `os.path` so the worker OS owns the separator (ntpath on Windows, posixpath on Linux) | import + invoke `Core.Path.LocalPath` helpers on Windows or Linux container; ntpath/posixpath semantics derive from local OS automatically (no platform branching in caller code) |
| S11 | `Worker.ResolveStorageRoot` <- `StorageRootResolutions` | `StorageRootResolutions.(StorageRootId, WorkerName, AbsolutePath, IsActive=TRUE)` -- exactly one active row per `(StorageRootId, WorkerName)` | per-worker per-StorageRoot absolute prefix string | `Worker.FromWorkerContext()` -> `worker.ResolveStorageRoot(Sid)` returns AbsolutePath; `worker.LocalToPath(local_str)` is the inverse (longest-prefix match, returns `Optional[Path]`). Replaces `Core/Services/PathTranslationService.py` (deleted 2026-06-05, `path-perfect-implementation` Step 3). | live transcode + scan + VMAF round-trip on any worker shows correct local resolution without `PathTranslationService`; `grep -rn PathTranslation` returns zero production-code hits |

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
