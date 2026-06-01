# Flow: Path Resolution at I/O Time

**Slug:** path-storage

How any worker turns a stored `(StorageRootId, RelativePath)` pair into a worker-local absolute path immediately before file-system I/O. This is the single canonical resolution path used by every transcode, VMAF, file-replacement, and probe operation in the system after the Phase 4 read-switch.

## Entry Points

| Caller | Operation | Why it needs Resolve |
|---|---|---|
| `Features/TranscodeJob/ProcessTranscodeQueueService.py:ProcessJob` | About to read source file for FFmpeg encode | Source's `(StorageRootId, RelativePath)` come from `MediaFiles` joined via `MediaFileId` |
| `Features/QualityTesting/QualityTestingBusinessService.py:BuildVMAFCommand` | About to read source + transcoded files for VMAF | Source's `(StorageRootId, RelativePath)` come from `TemporaryFilePaths` joined via `TranscodeAttemptId` |
| `Features/FileReplacement/FileReplacementBusinessService.py:ProcessFileReplacement` | About to archive original + move transcoded into place | Operates on `MediaFiles.(StorageRootId, RelativePath)` |
| `Features/MediaProbe/MediaProbeBusinessService.py:_ExecuteProbe` | About to call FFprobe on a file | Reads `MediaFiles.(StorageRootId, RelativePath)` |
| `Features/QualityTesting/QualityTestController.py:CompareStills` (and `CompareStillsBatch`) | About to extract still frames | Operates on canonical paths from `TranscodeAttempts` / `TemporaryFilePaths` |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py:_VariantizeOutputPath` | About to compute output filename for a test-mode variant | Operates on `RelativePath` directly (no Resolve needed for the path-shape computation) |

## Steps

| ID | Step | Code | What it does |
|---|---|---|---|
| ST1 | Caller has a DB row carrying `(StorageRootId, RelativePath)` | varies (MediaFiles, TemporaryFilePaths, etc.) | The row is the canonical source of truth; OS-independent |
| ST2 | Caller identifies the local worker | `Core.WorkerContext.WorkerContext.Current()` (`.WorkerName`) | Each worker process has one identity registered at boot |
| ST3 | Caller calls `Resolve` | `Core.PathStorage.Resolve(StorageRootId, RelativePath, WorkerName)` | The ONLY translation surface in the system |
| ST3a | Resolve queries `StorageRootResolutions` | SQL: `SELECT AbsolutePath FROM StorageRootResolutions WHERE StorageRootId=%s AND WorkerName=%s AND IsActive=TRUE LIMIT 1` | Per-worker absolute prefix |
| ST3b | Resolve joins prefix + RelativePath | `os.path.join(AbsolutePath, RelativePath)` | Single string operation, no regex |
| ST4 | Caller uses returned path for I/O | `os.path.exists(local)`, `subprocess.run([ffmpeg, '-i', local])`, `shutil.copy(local, ...)` | OS-native path; works on every platform that has a `StorageRootResolutions` row for the worker |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST3a` resolution lookup | `WorkerService.flow.md::S2` (env-var -> `StorageRootResolutions`) + `Scripts/SQLScripts/SetWindowsWorkerUncPaths.py` (Windows native) | `StorageRootResolutions.(Id, StorageRootId BIGINT, WorkerName TEXT, Platform TEXT IN ('linux','windows','mac'), AbsolutePath TEXT NOT NULL, IsActive BOOLEAN) UNIQUE(StorageRootId, WorkerName)` | `Core.PathStorage.Resolve` reads exactly one active row per `(StorageRootId, WorkerName)` | `SELECT COUNT(*) FROM StorageRootResolutions WHERE WorkerName=<host> AND IsActive=TRUE` >= 1 per intended root |
| S2 | `ST3 -> ST4` (resolved path -> I/O) | `Resolve()` returns absolute local path | OS-native string (POSIX `/mnt/...` on Linux, UNC `\\<server>\<share>\...` on Windows, drive letter `T:\...` on legacy hosts) | `os.path.exists`, FFmpeg argv, `shutil.copy` -- all OS path APIs | A working file open of the resolved path for a known-present source row |
| S3 | `ST1` invariant | Every canonical-table writer (`FileScanning`, `FileReplacement`, queue admission) | `MediaFiles.(StorageRootId BIGINT NOT NULL, RelativePath TEXT NOT NULL)` -- forward-slash form, no `..`, no drive letter prefix (CHECK constraint after Phase 4) | All readers rely on this shape | `\d MediaFiles` shows CHECK; `SELECT COUNT(*) FROM MediaFiles WHERE RelativePath ~ '^[A-Za-z]:' OR RelativePath LIKE '%..%'` -> 0 |
| S4 | Windows UNC variant | `SetWindowsWorkerUncPaths.py` (sole writer) idempotent per `StartWorker.py` launch | `AbsolutePath` ends in trailing slash, uses UNC `\\<server>\<share>\` shape | `Resolve` joins prefix + RelativePath via `os.path.join` -- Windows-native; bypasses the per-logon drive-letter session mapping (BUG-0008 mitigation) | `SELECT AbsolutePath FROM StorageRootResolutions WHERE WorkerName=<windows-host> AND Platform='windows'` shows `\\` prefix |

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| No `StorageRootResolutions` row for `(StorageRootId, WorkerName)` | `PathStorageError: No active StorageRootResolutions row for (StorageRootId=X, WorkerName='Y')` | Operator inserts the missing row via SQL. Worker resumes on next claim. |
| `StorageRootResolutions.IsActive=FALSE` for all matching rows | Same `PathStorageError` | Operator reactivates the right row, or inserts a new active row. |
| `RelativePath` contains a `..` segment or absolute prefix | Resolve produces a path outside the intended root | Phase 4 CHECK constraint blocks insert; verifiable via SQL. |
| Local mount missing or unmounted (race with fstab) | Returned local path doesn't exist when caller checks | I/O fails with FileNotFound; caller logs + bails. PathStorage is not at fault. |
| `StorageRootId` references a deleted root | FK violation when the caller wrote the row, OR Resolve returns no rows | FK cascade should not happen (operator action); investigate the write site. |

## Verification

Per `path-storage.feature.md` criterion 4: surviving translation code is < 50 LOC and contains no `[A-Za-z]:` parsing. The current `Core/PathStorage.py` is 47 LOC. No drive-letter regex. No backslash assumptions.

Per criterion 16: each I/O entry point above names the actual `Resolve` call site. Walk:

- `ProcessTranscodeQueueService.ProcessJob` source resolution: `Features/TranscodeJob/ProcessTranscodeQueueService.py:GetMediaFileData` (after Phase 4 update — Resolve replaces direct `MediaFile.FilePath` access).
- `BuildVMAFCommand` source resolution: `Features/QualityTesting/QualityTestingBusinessService.py:BuildVMAFCommand` — `Resolve(StorageRootId, RelativePath, WorkerName)` call, falling back to legacy `JobDetails['LocalSourcePath']` during Phase 4 transitional period.
- `FileReplacementBusinessService.ProcessFileReplacement`: after Phase 4 update, source/destination paths derived via Resolve from `MediaFiles.(StorageRootId, RelativePath)`.

## Out of Scope

- Path NORMALIZATION (collapsing `//`, removing trailing slash, etc.) -- handled by the underlying OS during I/O; Resolve does not normalize.
- Cross-share moves (e.g. moving a file from `media_tv` to `movies`) -- requires explicit `UPDATE` of `(StorageRootId, RelativePath)` and a physical file move.
- Symlink resolution -- callers that need to follow symlinks use `os.path.realpath` on the Resolved path, not inside Resolve itself.
- Per-worker mount-point overrides via env var -- replaced by `StorageRootResolutions` rows.
