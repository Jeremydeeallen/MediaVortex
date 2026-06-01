# Feature: Windows Worker UNC Path Translation

**Slug:** windows-unc-path-translation

## What It Does

Resolves [BUG-0008]. The Windows WorkerService translates DB-stored drive-letter paths (`T:\...`, `M:\...`, `Z:\...`) to UNC paths pointing at porky's NFSv4 exports (`\\10.0.0.43\srv\nfs-media-_tv\...`, `\\10.0.0.43\srv\nfs-media-_movies\...`, `\\10.0.0.43\srv\nfs-media-_xxx\...`) at every point where the worker hands a path to ffmpeg, ffprobe, or any `CreateFile`-equivalent syscall. UNC paths bypass the per-logon-session drive-letter mapping that intermittently unbinds on Windows NFS (root cause documented in `deploy/BUG-0008-i9-nfs-einval.troubleshooting.md`). All three shares consolidated on porky 2026-05-30; the previous .61 Synology shares are retired.

Linux workers are unaffected -- their translator path is unchanged.

The translation is **data-driven**: the per-share UNC strings come from `Workers.ShareMappings` (or the equivalent `WorkerShareMappings` table) in the DB, populated at worker registration. No code constants. If an operator needs to change a UNC for a worker, they edit the DB row (or the corresponding UI surface) and restart the worker -- no code change required.

## Surface

Operator-facing surfaces:

- **None new.** This is a behavior change inside the WorkerService, invisible to the operator beyond the disappearance of `4294967274` failures in `TranscodeAttempts`.
- **Existing UI:** if the worker-config / share-mapping panel on the Activity page already renders `ShareMappings`, the operator can use it to verify the UNC strings the worker will use. If it does not yet expose ShareMappings, that is a separate UX improvement, not in scope here.
- **Diagnostics:** every `LogInfo` line that previously printed a `T:\...` path now prints the translated UNC path. This is intentional: log lines must match the syscall the worker actually made, not the canonical DB value.

## Data Sources (the "data-driven" part)

**Confirmed 2026-05-22 via `QueryDatabase.py schema ...`:**

There are TWO per-worker path tables, both involved:

1. **`storagerootresolutions`** -- the PRIMARY seam consumed by `PathStorage.Resolve()` (the function that ends up populating `EffectiveInputPath` for the ffmpeg command). Schema:
   | Column | Type | Notes |
   |---|---|---|
   | `id` | bigint | PK |
   | `storagerootid` | bigint | FK to `storageroots.id` (3 rows: media_tv, movies, xxx) |
   | `workername` | text | NOT NULL |
   | `platform` | text | 'linux' or 'windows' |
   | `absolutepath` | text | Per-worker mount/UNC string |
   | `isactive` | boolean | |
   | `createdat` | timestamp | |

   Unique on (storagerootid, workername) drives the `ON CONFLICT ... DO UPDATE` UPSERT.

2. **`workersharemappings`** -- the SECONDARY translator consumed by `PathTranslationService.ToLocalPath()`, used by `FileScanning`, `FileReplacement`, `QualityTesting`, `ContinuousScanService`. Schema:
   | Column | Type | Notes |
   |---|---|---|
   | `id` | bigint | PK, auto-increment |
   | `workername` | text | NOT NULL, joins to `workers.workername` |
   | `driveletter` | character | NOT NULL, single char ('T', 'M', 'Z') |
   | `localmountprefix` | text | NOT NULL, the worker's local view of this drive |

   Unique constraint on (`workername`, `driveletter`) drives its UPSERT.

   The column name `localmountprefix` is a slight semantic mismatch with Windows UNC strings, but the concept fits: "this worker's local view of where this drive letter actually lives." Linux stores POSIX (`/mnt/media_tv/`); Windows stores UNC (`\\10.0.0.43\srv\nfs-media-_tv\`). Trailing slash convention is preserved across both platforms so the translator can do a simple prefix swap.

3. **Single writer.** `Scripts/SQLScripts/SetWindowsWorkerUncPaths.py` is the only writer to either table for Windows workers (operator-invoked at deploy/config time). Linux writes happen through the equivalent deploy step in `infrastructure/`. The worker process is read-only on both tables.

4. **Population API** (in `Repositories/DatabaseManager.py`, kept because the script consumes them):
   - `RegisterStorageRootResolutions(WorkerName, Platform, Mappings)` -- UPSERTs SRR rows. Authoritative writer.
   - `RegisterWorkerShareMappings(WorkerName, Mappings)` -- UPSERTs WSM rows. The script derives input here from SRR read-back; never authored separately.
   - `GetWorkerShareMappings(WorkerName) -> dict` -- read-side, used by `GetWorkerConfig` to populate `WorkerContext.ShareMappings`.

5. **Consumption paths:**
   - Primary: `PathStorage.Resolve(StorageRootId, RelativePath, WorkerName)` reads SRR.AbsolutePath. Feeds `EffectiveInputPath` into `CommandBuilder` and onward to ffmpeg.
   - Secondary: `PathTranslationService.ToLocalPath(canonical_path)` reads `WorkerContext.ShareMappings` (sourced from WSM at startup). Used by FileScanning, FileReplacement, QualityTesting.

6. **Failure mode if data missing:** Windows worker startup hard-fails (`sys.exit(1)`) when no SRR rows exist for its WorkerName, with the message naming `SetWindowsWorkerUncPaths.py` as the remediation. No silent fallback. The worker is a strict reader; missing data is an operator action, not a runtime guess.

## Success Criteria

### Behavior

1. **No drive-letter paths reach the syscall on Windows.** When `platform.system().lower() == 'windows'` and SRR rows exist for the worker, every path the worker passes to `subprocess.run`/`Popen`, `os.path.exists`, `pathlib.Path`, or `open()` for a share-rooted file is a UNC string starting with `\\<host>\<share>\`, not a drive letter. Verifiable: a Process Monitor capture filtered to `Operation = CreateFile AND ProcessName = ffmpeg.exe` while the worker is running shows zero accesses whose `Path` starts with `T:\`, `M:\`, or `Z:\`. The same capture shows UNC paths in the form `\\10.0.0.43\srv\...` or `\\10.0.0.43\srv\nfs-media-_...` instead.

2. **Linux workers are unchanged.** A worker running on Linux (larry-worker-N, wakko-worker-N, dot-worker-N) continues to translate `T:\...` -> `/mnt/mediafiles/tv/...` (or whichever POSIX mount-point it was using) via the existing `ToLocalPath` path. No UNC strings appear in any Linux worker log or ffmpeg command line. Verifiable: `grep -E '\\\\\\\\[0-9]' /var/log/mediavortex-worker.log` on any Linux worker returns nothing.

3. **No code constants for share UNCs.** A grep of the codebase for the literal strings `\\10.0.0.43\` and `\\10.0.0.43\srv\nfs-media-_` returns hits only in: (a) the `WorkerShareMappings` DB seed/migration, (b) `StartWorker.py`'s `NetworkDrives` list (the source-of-truth for I9 boot-time mount + env-var export), (c) test fixtures, (d) documentation (this doc, troubleshooting doc, flow doc). It returns NO hits in `Core/`, `Features/`, `Models/`, or anywhere else that decides what path to use at runtime. The runtime decision flows from `WorkerContext.ShareMappings` only.

4. **[BUG-0008] criterion holds.** Across 100 consecutive `TranscodeAttempts` rows where `WorkerName='I9-2024'`, zero rows have `Success=false` with `ErrorMessage` matching `return code 4294967274` AND `TranscodeDurationSeconds=0`. This is the original BUG-0008 verification bar; this feature owns its closure.

5. **Drive-letter session unbinding no longer affects the worker.** Operator can run `Test-Path T:\` from a separate PowerShell session and see it return `False` (T: unbound) while the worker continues processing remux/transcode jobs successfully without interruption. The two are decoupled. Verifiable: the side-by-side test described in `BUG-0008-i9-nfs-einval.troubleshooting.md` Test C, run for 10 minutes, shows worker success rate >= 99% while `T:=DOWN` appears in the presence log at least once.

### Configuration

6. **Operator can change a UNC without a code change.** Re-running `SetWindowsWorkerUncPaths.py` with updated `UNC_PREFIXES` (or editing the SRR/WSM rows directly) and restarting the worker process causes ffmpeg invocations to use the new UNC. Verifiable: change the rows, restart, watch the next `TranscodeAttempts.FfpmpegCommand` -- the new UNC appears literally in the command string.

7. **Worker is a strict reader.** The worker never writes to `StorageRootResolutions` or `WorkerShareMappings`. On startup, if no SRR rows exist for its WorkerName, it hard-fails with `sys.exit(1)` and a message naming the remediation script. There is no fallback that silently substitutes drive-letter paths. Verifiable: grep `WorkerService/` for `RegisterStorageRoot*` or `RegisterWorkerShareMappings` -- zero hits.

### Startup checks

8. **`_VerifyRequiredPaths` is share-mapping-aware.** When `ShareMappings` is set on a Windows worker, the startup verification iterates the configured UNC paths and calls `os.path.exists()` on each, not on the drive-letter prefixes from `MediaFiles.FilePath`. If a UNC is unreachable, the worker hard-fails with a message naming the unreachable UNC, before any DB writes. Verifiable: SSH into I9, set `MEDIAVORTEX_SHARE_MAPPINGS=T=\\bad-host\share`, launch `StartWorker.py`; it exits non-zero within 30 seconds with the offending UNC in the message.

## Deviation from conventions

None anticipated. This feature respects every existing pattern: data-driven config from DB, PascalCase, fail-loud at startup, Linux/Windows path divergence isolated to `PathTranslationService`.

## Status

NOT STARTED -- 2026-05-22.

### Progress

- [x] 1. Confirmed `workersharemappings` schema (2026-05-22): 4 columns (id, workername, driveletter, localmountprefix), unique on (workername, driveletter). 36 existing rows, all Linux. **I9-2024 has zero rows -- gap is real.** Existing `RegisterWorkerShareMappings` / `GetWorkerShareMappings` APIs accept arbitrary string in the prefix slot, so UNC values fit the existing schema with no DB migration required. Data Sources section above rewritten with the actual schema and current contents.
- [x] 2. **No new method needed (2026-05-22).** The existing `ToLocalPath()` already does the right thing on Windows when the MountMap contains UNC values instead of POSIX paths -- the translation is cross-platform-uniform (strip 3 chars, prepend prefix); only the trailing slash-flip for Linux differs. Verified: `ToLocalPath('T:\\Shows\\foo.mkv')` with `MountMap={'T': '\\\\10.0.0.43\\srv\\nfs-media-_tv\\'}` returns `\\\\10.0.0.43\\srv\\nfs-media-_tv\\Shows\\foo.mkv` correctly. Updated the class and method docstrings to make the Windows-UNC case a first-class documented example alongside the Linux POSIX case. No behavior change in this commit; the data side (item 5) and the call-site wiring (item 3) carry the actual fix.
- [x] 3. **No call-site wiring needed (2026-05-22).** The translation seam is `PathStorage.Resolve(StorageRootId, RelativePath, WorkerName)`, which reads `StorageRootResolutions.AbsolutePath` for `(StorageRootId, WorkerName)`. `SetupFilePreparation` calls it; result becomes `EffectiveInputPath` which flows into `CommandBuilder.InputPath`, then `os.path.dirname/join` propagate it into `OutputPath`, then ffmpeg gets it. Linux already works because larry/wakko/dot have `AbsolutePath = '/mnt/media_tv/'` etc. I9 currently has `AbsolutePath = 'T:\\'` -- that is why ffmpeg gets drive-letter paths. Flip the I9 rows to UNC strings and the existing code paths emit UNC. Verified `os.path.join`, `os.path.dirname`, `os.path.normpath`, `os.path.exists` all handle UNC strings correctly on Windows. The secondary code paths (FileScanning, FileReplacement, QualityTesting) consume `WorkerShareMappings` via `PathTranslationService.ToLocalPath` -- they need the parallel data update (item 5), but no code change.
- [x] 4. **`_VerifyRequiredPaths`** reads `StorageRootResolutions.AbsolutePath` for this worker and calls `os.path.exists()` on each share. Works uniformly for POSIX, drive letters, and UNC strings. Failure message names the missing share and its AbsolutePath. WorkerName resolution: env `MEDIAVORTEX_WORKER_NAME` then `socket.gethostname()`.
- [x] 5. **Data flip script + worker becomes a strict reader (2026-05-22).** Created `Scripts/SQLScripts/SetWindowsWorkerUncPaths.py`:
   - Single `UNC_PREFIXES` dict at the top is the only place UNC strings live in code.
   - Writes `StorageRootResolutions` via `RegisterStorageRootResolutions(WorkerName, 'windows', UNC_PREFIXES)` -- authoritative.
   - Reads back the SRR rows and projects them into `WorkerShareMappings`. WSM cannot drift from SRR for this worker by construction.
   - Idempotent; supports `--dry-run`.

   `WorkerService/Main.py::_RegisterAndLoadWorkerConfig` is now a strict reader: queries SRR for the worker; if zero rows, hard-fails with `sys.exit(1)` and a message naming `SetWindowsWorkerUncPaths.py` as the remediation. The env-var branch and the canonical-prefix bootstrap branch are deleted. `RegisterStorageRootResolutionsFromCanonical` is removed from `DatabaseManager.py`. The worker has no path that can clobber operator data.

   `StartWorker.py` calls `_SetUncResolutions()` after `_VerifyDrives` so a fresh I9 deploy populates SRR/WSM before the worker reads them. Missing script file emits a WARN; the worker's strict-reader check will then hard-fail with a clear message rather than silently using drive letters.
- [ ] 6. Add the criterion-1 grep check (`Path contains \\` in ProcessMon, captured during a short worker run) to the BUG-0008 verification log.
- [ ] 7. Run BUG-0008 troubleshooting doc Test C (15-min side-by-side under live load) and record the final OK/FAIL counts in this doc's Status section.
- [ ] 8. Mark BUG-0008 resolved per `/bs BUG-0008` once criterion 4 is met.

## Scope

```
Core/Services/PathTranslationService.py
WorkerService/Main.py
StartWorker.py
Models/CommandBuilder.py
Features/TranscodeJob/ProcessTranscodeQueueService.py
Features/TranscodeJob/VideoTranscodingService.py
Features/FileScanning/FileScanningBusinessService.py
Features/FileReplacement/FileReplacementBusinessService.py
Features/QualityTesting/QualityTestingBusinessService.py
WorkerService/windows-unc-path-translation.feature.md
```

`deploy/BUG-0008-i9-nfs-einval.troubleshooting.md` and `KNOWN-ISSUES.md` are touched only to update status, not to add new content.

## Follow-ups (known debt, deferred deliberately)

### Consolidate `WorkerShareMappings` and `StorageRootResolutions` into one table

Two tables currently store the same concept ("where does this worker see this share"):

| Table | Read by | Schema | Notes |
|---|---|---|---|
| `StorageRootResolutions` | `PathStorage.Resolve()` -> `SetupFilePreparation` -> CommandBuilder -> ffmpeg | Relational: FK to `StorageRoots` (3 canonical shares); per-(StorageRootId, WorkerName) row with `AbsolutePath`, `Platform`, `IsActive` | The newer, more normalized design. Survivor. |
| `WorkerShareMappings` | `PathTranslationService.ToLocalPath()` via `WorkerContext.PathTranslation` -> FileScanning, FileReplacement, QualityTesting, ContinuousScanService | Flat: per-(WorkerName, DriveLetter) row with `LocalMountPrefix` | The older design. Functionally a denormalization keyed on drive letter rather than StorageRoot. Deprecation candidate. |

Both consume the same logical data; both have separate UPSERT APIs in `DatabaseManager`; both have separate consumers in the runtime. Keeping them in sync is implicit work that the codebase does not enforce.

**Why this BUG-0008 fix did not consolidate them:** scope. The EINVAL bug is data-shape-agnostic -- it would have been triggered identically with one table or two. Adding a schema-consolidation migration to the same change would have:
- doubled the blast radius of the fix
- required Linux workers to be migrated and re-validated as part of a Windows bugfix
- delayed BUG-0008 closure on a fragile production worker (I9-2024)

**What we did instead, to make the future consolidation cheap:**

1. Designated `StorageRootResolutions` as the authoritative source in everything BUG-0008 touched. `_VerifyRequiredPaths` now reads from it (item 4); the data-flip script writes to it first (item 5).
2. Made `WorkerShareMappings` strictly **derived** from `StorageRootResolutions` in the data-flip script. The script never writes UNC values directly to WSM -- it reads them back from the SRR rows it just wrote and projects them into WSM. By code construction, WSM cannot drift from SRR for any worker the script has touched.
3. Did NOT add any new code dependencies on `WorkerShareMappings`. New code routes through `PathStorage.Resolve`. Existing WSM consumers are unchanged but on notice.

**When to do the consolidation:** once every WSM consumer has been migrated to read via `PathStorage.Resolve` or a successor facade. Suggested order:
1. Refactor `PathTranslationService.ToLocalPath` to consult `StorageRootResolutions` (via a thin `WorkerContext.StorageRootResolutions` map populated at startup), keeping its current signature so callers do not change.
2. Run for one release cycle on both Linux and Windows; verify no behavior drift.
3. Drop `WorkerShareMappings` table, the `Register/GetWorkerShareMappings` methods, and the env var `MEDIAVORTEX_SHARE_MAPPINGS` if no consumer remains.

Tracked as a separate feature when prioritized.

### Other deferred items

- `_VerifyRequiredPaths` still falls back to drive-letter prefix scan when no `StorageRootResolutions` rows exist for the worker. The fallback can be removed once the data migration is verified on every host. Until then it is rollback safety.
- The `localmountprefix` column name in `WorkerShareMappings` is slightly misleading for Windows UNC values. Renaming requires the consolidation migration above; not worth a separate rename pass.

## References

- `deploy/BUG-0008-i9-nfs-einval.troubleshooting.md` -- root cause analysis and verification protocol
- `deploy/worker-deploy.feature.md` criterion 13 -- the [BUG-0008] no-EINVAL contract this feature delivers
- `deploy/worker-deploy-windows.flow.md` -- I9 deployment flow; the Drive Mappings section will be reframed once UNC takes over (drive letters become operator-convenience only, not the worker's path)
- `WorkerService/worker-lifecycle.feature.md` -- adjacent runtime invariants; share-mapping config is owned here
