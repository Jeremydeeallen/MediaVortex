# Directive: scan-broken-restore

**Status:** Active -- phase: IMPLEMENTING
**Opened:** 2026-07-31
**Parent (paused):** docker-purge
**Slug:** scan-broken-restore

## Outcome

Restore the file-scanner path that died 2026-07-31 08:51 UTC when a partial migration of `RootFolders.RootFolder` to `StorageRootId + RelativePath` left 3 SQL queries + 7 call sites broken. Downstream effect: `LanguageWorker` starved of fresh MediaFiles rows → whisper hasn't run in 16+ hours. Also patch a UnicodeEncodeError on paths with `é` (Pokémon) that crashes the log-writer.

KISS scope: fix the specific breaks + one boundary encoding line. No refactor, no cleanup of the 73 pre-existing orphan MediaFiles rows (they self-clear once fresh scans dominate the fetch pool).

## Acceptance Criteria

C1. **`MediaFilesRepository.GetMediaFilesByRootFolderId` reads from `StorageRootId + RelativePath`.** No longer executes `SELECT RootFolder FROM RootFolders WHERE Id = %s`. Verifiable: `grep -rn "SELECT RootFolder FROM RootFolders" Features/` returns zero.

C2. **`MediaProbeRepository` two queries at lines 66 + 105 use new schema.** Same fix as C1. Verifiable: grep zero hits across `Features/`, `Core/`, `Services/`, `WorkerService/`, `WebService/`, `Scripts/`.

C3. **`FileScanningBusinessService` routes `GetMediaFilesByRootFolder*` to the correct repo.** 7 call sites (lines 1194, 1228, 1482, 1929, 2037, 2158, 2330) route through a repository that owns the methods. Verifiable: `SELECT COUNT(*) FROM Logs WHERE Timestamp > NOW() - INTERVAL '1 hour' AND ExceptionMessage ILIKE '%GetMediaFilesByRootFolder%'` = 0 post-deploy.

C4. **LogWriter tolerates surrogate-encoded paths.** UnicodeEncodeError on `\udce9` (Pokémon) no longer crashes the INSERT into `Logs`. Uses `errors='replace'` at the encode boundary (same pattern already at `Features/AudioNormalization/Measurement/EbuR128MeasurementService.py:143`, `AudioStreamProbe.py:44`, `LanguageEnrichmentService.py:142`). Verifiable: `SELECT COUNT(*) FROM Logs WHERE Timestamp > NOW() - INTERVAL '1 hour' AND ExceptionType='UnicodeEncodeError'` = 0 post-deploy.

C5. **Whisper resumes.** Within 15 min of code deploy to a LanguageEnabled worker with a valid mount, `MAX(DetectedAt) FROM MediaFileLanguageDetections` advances past current ceiling `2026-07-31 08:51:41 UTC`. Verifiable: SQL.

C6. **Contract test grep-fences the retired SQL.** `Tests/Contract/TestNoDeletedRootFolderColumn.py` fails on any occurrence of `SELECT RootFolder FROM RootFolders` in Python source under production directories. Prevents regression.

## Call-Graph Audit

Populated pre NEEDS_PLAN. Four signals:

1. **Multiple flow docs for one conceptual operation:** No. FileScanning has one entry pipeline. Not a signal here.
2. **Mode-branching at orchestration:** No new branching. C3 fix just routes call to correct instance.
3. **Shared output columns sparsely populated:** `RootFolders` old column `RootFolder` was retired but 3 queries still reference it. `StorageRootId` + `RelativePath` are the new pair. Consumers should always read the new pair; the old column no longer exists — enforced by contract test C6.
4. **OOS ambiguity:** All OOS items below classified explicitly.

## Out of Scope

- **73 pre-existing orphan MediaFiles rows.** (a) not addressed. Once scanning resumes and fresh MediaFiles get top of fetch pool via ORDER BY LastScannedDate DESC, orphans push down out of BatchSize=25. Not blocking whisper functionally, only log noise.
- **TranscodedOutputPlacement FK constraint failure** (2026-07-31 14:14 + 14:56 UTC ERRORs). (a) not addressed. Root cause of orphan-creation. Separate bug/directive.
- **Linux worker scanning `T:\`.** (a) not addressed. A RootFolder assigned to a canonical Windows path but claimed by a Linux worker. Root-folder assignment audit — separate.
- **LanguageWorker path-missing infinite-retry loop.** (a) not addressed. Doesn't block whisper — orphans self-clear from fetch pool. Improvement, not fix.

## Files (planned)

To edit:
- `Features/MediaFiles/MediaFilesRepository.py` (C1)
- `Features/MediaProbe/MediaProbeRepository.py` (C2)
- `Features/FileScanning/FileScanningBusinessService.py` (C3)
- `Core/Logging/LoggingService.py` — actual log-writer path TBD at read time (C4)

To create:
- `Tests/Contract/TestNoDeletedRootFolderColumn.py` (C6)

At DELIVERING, promote content into:
- `Features/FileScanning/FileScanning.feature.md` — updated column references + repo-attribute correctness invariant
- `Features/MediaFiles/mediafiles.feature.md` (if it exists) — `GetMediaFilesByRootFolderId` uses new schema
- `memory/KNOWN-ISSUES.md` — resolved entry for the 08:51 UTC break

## Progress

- [ ] NEEDS_STANDARDS_REVIEW: call-graph audit populated (above)
- [ ] NEEDS_PLAN: fix order approved
- [ ] NEEDS_DOC_PREREAD: read colocated feature docs for touched files
- [ ] IMPLEMENTING: C1..C4 + C6
- [ ] VERIFYING: contract test green; deploy to one worker; C5 stamp advance observed
- [ ] DELIVERING: promotions to feature docs + KNOWN-ISSUES resolved entry

## Notes

- Docker-purge directive content preserved in git commit `2836ce76`; will be restored on pop-back after this directive closes.
- Pause commit for docker-purge: `2530d4b6 chore(pause): docker-purge blocked by scan-broken-restore`.
- Existing surrogate-safe pattern precedent: `errors='replace'` used at 5+ decode boundaries in `Features/AudioNormalization/` — apply same one-liner at LogWriter INSERT.
