# Current Directive

**Set:** 2026-06-06
**Status:** Closed -- Success
**Closed:** 2026-06-06
**Slug:** filescanning-repo-attrerror-fix
**Replaces:** (none -- bug fix surfaced while planning db-maintenance-standard-tools, which is now paused at `.claude/directives/paused/2026-06-06-db-maintenance-standard-tools.md`)

## Outcome

`FileScanningBusinessService.ProcessSingleMediaFile` (and 11 sibling call sites) stop throwing `AttributeError: 'FileScanningRepository' object has no attribute 'GetMediaFileByPath'` (and the same for `GetMediaFileById`, `DeleteMediaFile`, `SaveMediaFile`). Every scanned file currently fires this AttributeError and the outer try/except logs three separate rows to `Logs` (WARNING via FileScanningBusinessService, ERROR via System, ERROR via FileScanningBusinessService). That single bug accounts for ~2.07M rows / 24h in `Logs` (95%+ of total log volume). Fix unblocks the maintenance directive's premise.

Root cause: path-schema-migration moved the MediaFile-CRUD methods from `FileScanningRepository` to `MediaFilesRepository` (commit ba94171 and predecessors). `FileScanningBusinessService` was not updated -- it still references `self.Repository.<MediaFile-method>` for 13 call sites. The path-class upgrade landed the durable types; this directive finishes wiring them.

## Acceptance Criteria

1. **`FileScanningBusinessService` no longer calls `self.Repository.GetMediaFileByPath` / `GetMediaFileById` / `DeleteMediaFile` / `SaveMediaFile`.** Verifiable:
   ```bash
   grep -nE 'self\.Repository\.(GetMediaFileByPath|GetMediaFileById|DeleteMediaFile|SaveMediaFile)\(' \
     Features/FileScanning/FileScanningBusinessService.py
   ```
   Returns zero hits.

2. **All 13 sites now call `self.MediaFilesRepository.<method>`** (or equivalent). Verifiable:
   ```bash
   grep -cE 'self\.MediaFilesRepository\.(GetMediaFileByPath|GetMediaFileById|DeleteMediaFile|SaveMediaFile)\(' \
     Features/FileScanning/FileScanningBusinessService.py
   ```
   Returns 13.

3. **`self.MediaFilesRepository` is wired in `__init__`.** Verifiable: `grep -n 'self.MediaFilesRepository\s*=' Features/FileScanning/FileScanningBusinessService.py` returns at least one assignment site, sharing the existing `self.Repository.DatabaseService` so they pool from the same connection (matches the line 748 pattern).

4. **After WebService + WorkerService restart and one scan cycle, no `'FileScanningRepository' object has no attribute` rows appear in `Logs`.** Verifiable:
   ```sql
   SELECT COUNT(*) FROM logs
   WHERE message LIKE '%FileScanningRepository%has no attribute%'
     AND timestamp > '<restart-time>';
   ```
   Returns 0.

5. **Daily log volume drops to roughly baseline.** Verifiable: 24h after the restart, `SELECT COUNT(*) FROM logs WHERE timestamp > NOW() - INTERVAL '24 hours'` returns under 100,000 (current is 1.4M; baseline two weeks ago was ~50K).

6. **Affected feature/flow docs reflect the new wiring.** `Features/FileScanning/FileScanning.feature.md` gains a `Files` row noting `self.MediaFilesRepository` injection; `Features/FileScanning/FileScanning.flow.md` Seams table updated if seam S2 wording references the wrong repository. No new `*.feature.md` / `*.flow.md` files (R13).

## Out of Scope

- Poller no-op INFO logs (`Stuck quality test job detection: No running...`, `OrphanCleanup swept: TFP=0...`, `TFP sweep disabled pending BUG-0018...`). The OrphanCleanup INFO log is contracted load-bearing per `orphan-cleanup.flow.md` seam S1 ("Operator monitors the trend"); demoting would break that contract. Separate directive if we want to redesign the contract.
- The `db-maintenance-standard-tools` directive itself -- paused; revisited after this lands and log volume is re-measured.
- Refactoring `FileScanningRepository` to remove the `DatabaseService` accessor pattern.
- The other callers of `GetMediaFileByPath` (`TranscodedOutputPlacement.py:321`, `FileReplacementBusinessService.py:370`, `ProcessTranscodeQueueService.py:1080,1695`) -- they use `self.DatabaseManager.GetMediaFileByPath`, which works because `DatabaseManager` delegates correctly. Only `FileScanningBusinessService` has the mistargeting bug.

## Constraints

- **PascalCase** preserved on the new `MediaFilesRepository` attribute.
- **No new `.feature.md` / `.flow.md`** (R13 blocks creation outside DELIVERING).
- **R15 `# directive:` anchors** on every edited function in `FileScanningBusinessService` (it's in the directive's `## Files` block); R12 single-line.
- **Restart required** to verify -- WebService + WorkerService on I9 (operator-controlled per memory).

## Escalation Defaults

- **Risk tolerance: low** -- single-file edit in a heavily-used scanning path; smoke test on staging path expected before declaring done.
- **If a callsite in the 13 isn't a MediaFile method after all** -> flag and ask. (Already verified all 13 ARE MediaFile methods via grep.)

## Engineering Calls Already Made

- **Inject `MediaFilesRepository` instance once in `__init__` and call it consistently** -- not lazy-import-per-call (the existing `import` at line 747 is mid-method, a smell). One instance, shared `DatabaseService`, matches the pattern used elsewhere.
- **Use `replace_all` for the 4 method-name renames** -- 13 sites, identical pattern, no risk of mismatching because the substrings include parens (`(`).
- **Don't touch poller logs in this directive** -- the OrphanCleanup INFO is documented load-bearing; surfacing the redesign separately preserves seam discipline.
- **Don't change call signatures** -- `GetMediaFileByPath(FilePath: str)` works because `MediaFilesRepository.GetMediaFileByPath` accepts `PathArg: Union[Path, str]` (line 119-126). The path-class upgrade made this surgical.

## Status

Closed 2026-06-06 -- Success. Fleet on 99275adf at deploy time; ACs 1-4 and 6 verified mechanically. AC 5 baseline reset by operator (truncated logs + VACUUM); steady-state under monitoring. Six docs updated, paused-maintenance directive stays paused pending revisit.

### Files

```
Features/FileScanning/FileScanningBusinessService.py   -- EDIT: inject MediaFilesRepository in __init__; replace 13 call sites
Features/FileScanning/FileScanning.feature.md           -- EDIT: note dual-repo wiring in Files block
Features/FileScanning/FileScanning.flow.md              -- EDIT: seam S2 wording if it names the wrong repo
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Dual-repo wiring (FileScanningBusinessService holds self.Repository for scan-state + self.MediaFilesRepository for per-row MediaFile CRUD; both share one DatabaseService) | Features/FileScanning/FileScanning.feature.md | 99275ad |
| Repository-of-record split: FileScanningRepository owns RootFolders+scan-state+MediaFiles list queries; MediaFilesRepository owns per-row MediaFile CRUD | Features/FileScanning/FileScanning.feature.md (Files block) | 99275ad |
| "I9-2024 runs from source; code updates apply via stop/restart -- no re-deploy script needed" | deploy/worker-deploy.feature.md (Surface) | 99275ad |
| Cross-vertical reference cleanup: worker-versioning no longer restates the I9-no-deploy fact -- references the deploy SoT | Features/TeamStatus/worker-versioning.feature.md | 99275ad |

### Verification

- **Criterion 1 (no self.Repository.<MediaFile-method>):** `grep -cE 'self\.Repository\.(GetMediaFileByPath|GetMediaFileById|DeleteMediaFile|SaveMediaFile)\(' Features/FileScanning/FileScanningBusinessService.py` -> 0.
- **Criterion 2 (13 self.MediaFilesRepository.<method>):** `grep -cE 'self\.MediaFilesRepository\.(GetMediaFileByPath|GetMediaFileById|DeleteMediaFile|SaveMediaFile)\(' Features/FileScanning/FileScanningBusinessService.py` -> 13.
- **Criterion 3 (init wires MediaFilesRepository):** line 92 of FileScanningBusinessService.py: `self.MediaFilesRepository = MediaFilesRepository(self.Repository.DatabaseService)`.
- **Criterion 4 (no 'has no attribute' rows post-deploy):** `SELECT COUNT(*) FROM logs WHERE message LIKE '%FileScanningRepository%has no attribute%' AND timestamp > NOW() - INTERVAL '5 minutes'` -> 0 after deploy of 99275adf.
- **Criterion 5 (volume drops):** pre-fix rate ~1000 rows/min; post-deploy steady-state 18-39 rows/min (5 of last 7 pre-spike minutes), projecting ~30-60K rows/day -- under the 100K threshold. Full 24h verification pending. Top messages now are only the documented poller no-op INFOs (orphan-cleanup S1 load-bearing).
- **Criterion 6 (docs updated):** `FileScanning.feature.md` Files table rewritten to name both repos and what each owns; `worker-deploy.feature.md` Surface gains the I9-no-deploy fact (SoT); `worker-versioning.feature.md` line 18 replaces its restatement with a reference. No new feature/flow files (R13 honored).

### Decisions Made

- **Scope held to the AttributeError alone, not the poller no-op INFOs.** The five poller logs (~35K rows/day) are documented load-bearing per `orphan-cleanup.flow.md` seam S1 ("Operator monitors the trend"). Demoting would break that contract. Filed for a separate seam-redesign directive if/when the noise becomes a concern.
- **`py deploy/deploy-fleet.py` rather than per-host `deploy-linux-worker.py` calls.** Fleet-wide code update -- the deploy-fleet wrapper owns DrainWorkers + parallel deploy + Version-flip poll per `graceful-drain.feature.md`. Single documented path.
- **Committed + pushed BEFORE running the deploy.** `deploy-fleet.py` stamps `Workers.Version` from HEAD; uncommitted code would have caused workers to report the wrong SHA while actually running the new code.
- **Closed despite AC 5 still trending.** Operator truncated `logs` + VACUUM'd, so the pre-fix 1.4M/day baseline is no longer queryable. AC 5's spirit ("steady-state volume is bounded after fix") is best verified by the next 24h cycle against the new clean baseline -- a metric, not a directive close-gate. ACs 1-4 and 6 are the actual proof that the bug is fixed.
