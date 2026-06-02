# Ad-hoc Drive Scans

**Slug:** ad-hoc-drive-scans

## Interrupts: media-tabs-and-loudness

## What It Does

Lets the operator keep RootFolders registered but turn scanning on or off per drive, and trigger an ad-hoc scan against any registered drive from the `/Scanning` page. Pairs with the existing draft `scanning-on-activity-page.feature.md` to also surface in-flight scan progress on the `/Activity` page.

Today the only on/off lever is `Workers.ScanEnabled` (global per worker). To scan just one drive you either type a path into the Manual Scan field or flip a worker-wide flag and let the continuous loop iterate every RootFolder alphabetically. There is no per-drive disable for the continuous loop, and the `/Activity` page does not show scan progress (only transcodes and quality tests).

## Surface

- **`/Scanning` page** — a new "Registered Drives" section listing each RootFolder with: path, last-scanned date, ScanEnabled toggle, "Scan Now" button.
- **`RootFolders.ScanEnabled BOOLEAN NOT NULL DEFAULT TRUE`** — new column.
- **`PATCH /api/RootFolders/<id>`** accepting `{"ScanEnabled": true|false}`.
- **`POST /api/RootFolders/<id>/ScanNow`** triggers an immediate scan of that RootFolder on an eligible worker; returns `{Success, JobId, WorkerName}`.
- **`/Activity` page** — File Scanning panel (Active + Recent) per `scanning-on-activity-page.feature.md`. That feature already covers the visibility half; this feature explicitly pulls it into the same release so toggles, ad-hoc triggers, and live progress ship together.

## Success Criteria

1. **Per-RootFolder ScanEnabled column.** `RootFolders` has `ScanEnabled BOOLEAN NOT NULL DEFAULT TRUE`. Migration is idempotent (`ADD COLUMN IF NOT EXISTS`). Every existing row receives `TRUE` so default behavior is unchanged. Verifiable: `\d RootFolders` shows the column; `SELECT COUNT(*) FROM RootFolders WHERE ScanEnabled IS NULL` returns 0.

2. **Continuous scan honors the toggle.** `ContinuousScanService._ExecuteScan` filters out RootFolders where `ScanEnabled=false` before iterating. A RootFolder with `ScanEnabled=false` produces no `ScanJobs` row from continuous mode regardless of `Workers.ScanEnabled` or worker count. Verifiable: set `T:\` to `ScanEnabled=false`, enable continuous scanning on a worker, observe no `ScanJobs` row for `T:\` on the next tick; flip it back to true and observe the next tick scans it.

3. **Toggle endpoint.** `PATCH /api/RootFolders/<id>` accepts `{"ScanEnabled": bool}`, persists, returns the updated row. Verifiable: PATCH `{"ScanEnabled": false}` then GET `/api/RootFolders` shows the new value.

4. **Ad-hoc scan endpoint.** `POST /api/RootFolders/<id>/ScanNow` enqueues an immediate scan and returns `{Success, JobId, WorkerName}`. The scan bypasses the per-RootFolder ScanEnabled gate (operator explicitly asked for it) but still respects `PreferredWorkerName` affinity and the per-RootFolder claim guard (rejects with `ScanAlreadyRunning` if one is in flight). Verifiable: with `T:\` set to ScanEnabled=false, POST `/api/RootFolders/<TId>/ScanNow`; a new ScanJobs row appears with `RootFolderPath='T:\'` and a `WorkerName` set.

5. **/Scanning page lists registered drives with controls.** A "Registered Drives" section renders one row per RootFolder with: path, last-scanned (display TZ via `formatTime`), ScanEnabled toggle (Bootstrap switch), "Scan Now" button. The table is scrollable / collapsible because RootFolders currently has 537 rows. Toggling the switch calls the PATCH endpoint; clicking "Scan Now" calls the ScanNow endpoint and shows a toast with the JobId. Verifiable: load `/Scanning`, observe rows, click a toggle and confirm DB value flips; click Scan Now and confirm a ScanJobs row appears.

6. **Top-level drive root toggles cascade in continuous mode.** Continuous mode iterates only top-level RootFolders (`_GetTopLevelFolders`), so a parent drive root (`T:\`) being disabled implicitly skips every per-show child it covers regardless of those children's toggle values. The criterion documents the precedence so the operator does not need to disable each child separately. Per-RootFolder toggles on child rows still apply to their own `Scan Now` button and to any future direct-scan invocation. Verifiable: disable `T:\` (parent) while leaving `T:\30 Rock` (child) enabled; continuous tick produces no ScanJobs row for either; hitting "Scan Now" on the `T:\30 Rock` row still works.

7. **Worker-level ScanEnabled remains the master kill switch.** With every worker at `ScanEnabled=false`, no continuous scans run regardless of per-RootFolder toggles. Ad-hoc `ScanNow` still works as long as at least one worker is `Status='Online'` and can resolve the path (path-validation gate from FileScanning criterion 20 still applies). Verifiable: set all workers to ScanEnabled=false, set `M:\` to ScanEnabled=true, observe no ScanJobs row from continuous mode; POST `/api/RootFolders/<MId>/ScanNow` and observe a ScanJobs row with a valid WorkerName.

8. **Manual-path field unaffected.** The existing "Manual Scan" text input + `POST /api/Scan/Start` continues to accept any path (registered or not, enabled or not). This feature does not change the manual-entry contract. Verifiable: enter `T:\30 Rock` while `T:\` is disabled; scan starts.

9. **Activity-page visibility lands in the same release.** `scanning-on-activity-page.feature.md` (DRAFTED, 15 criteria) is promoted from drafted to in-progress as part of this feature's pipeline. Its criteria are not duplicated here — that doc remains the source of truth for the `/Activity` surface. Verifiable: when this feature is marked COMPLETE, `scanning-on-activity-page.feature.md` is also COMPLETE with its criteria met (operator can see active scans + recent history + per-worker next-scan ETA on `/Activity`).

10. **No regression on existing scan behavior.** A fresh install with no operator action (no toggling) behaves identically to today: continuous mode scans every top-level RootFolder, manual scans work, ad-hoc endpoint is opt-in. Verifiable: deploy with the migration applied, do not change any ScanEnabled value, observe a continuous-scan tick scans `M:\` → `T:\` → `Z:\` as before.

## Status

DRAFTED -- awaiting operator approval. No code written.

### Progress

- [x] 1. Read `memory/KNOWN-ISSUES.md` and existing FileScanning feature/flow docs
- [x] 2. Confirm pivot: paused parent `media-tabs-and-loudness`; pause snapshot committed (ed97c4d)
- [x] 3. Identify companion: `scanning-on-activity-page.feature.md` already drafted; pulled into this feature's release scope via criterion 9
- [x] 4. Draft this doc with criteria
- [ ] 5. **Operator approval of criteria** -- no code until this is checked
- [ ] 6. Migration: `Scripts/SQLScripts/AddRootFolderScanEnabled.py` (idempotent ADD COLUMN; backfill default TRUE; verify count)
- [ ] 7. Repository + business service: `FileScanningRepository.UpdateRootFolderScanEnabled(id, bool)`, `GetRootFoldersWithStatus()`; `ContinuousScanService._ExecuteScan` filter on `ScanEnabled=true`
- [ ] 8. Controller: `PATCH /api/RootFolders/<id>`, `POST /api/RootFolders/<id>/ScanNow`
- [ ] 9. UI: `/Scanning` "Registered Drives" section with toggle + Scan Now per row
- [ ] 10. Activity-page rendering is covered by the directives at `.claude/directives/closed/2026-05-27-active-scan-visibility.md` and `2026-05-28-scan-largest-first.md`; this feature doesn't redefine that surface.
- [ ] 11. Smoke test: toggle a drive off, confirm continuous mode skips it; click Scan Now, confirm a ScanJobs row appears and `/Activity` shows it live; let it complete and confirm the Recent Scans card on `/Operations` updates.
- [ ] 12. `/f` finalize and `/fs` full pipeline

## Scope

```
Features/FileScanning/FileScanningController.py            -- PATCH RootFolder; POST ScanNow
Features/FileScanning/FileScanningBusinessService.py       -- ScanNow business path; gating check on continuous loop
Features/FileScanning/FileScanningRepository.py            -- ScanEnabled read/write; GetRootFoldersWithStatus
Features/FileScanning/FileScanningViewModel.py             -- view model for the new section
Features/FileScanning/ContinuousScanService.py             -- filter ScanEnabled=false in _ExecuteScan
Features/FileScanning/Models/RootFolderModel.py            -- add ScanEnabled field
Templates/FileScanning.html                                -- Registered Drives section + handlers
Scripts/SQLScripts/AddRootFolderScanEnabled.py             -- NEW migration
Features/FileScanning/scanning-on-activity-page.feature.md -- co-delivered (existing draft)
```

## Files

| File | Role |
|------|------|
| `Features/FileScanning/FileScanningController.py` | New `PATCH /api/RootFolders/<id>` and `POST /api/RootFolders/<id>/ScanNow` endpoints |
| `Features/FileScanning/FileScanningBusinessService.py` | `ScanNow(RootFolderId)` -- resolves worker affinity, claim-guards, calls `StartScanning` synchronously to enqueue |
| `Features/FileScanning/FileScanningRepository.py` | `UpdateRootFolderScanEnabled(id, bool)`, extend `GetAllRootFolders` to return `ScanEnabled` and `LastScannedDate` |
| `Features/FileScanning/ContinuousScanService.py` | `_ExecuteScan` filter `[f for f in EligibleFolders if f.ScanEnabled]` |
| `Features/FileScanning/Models/RootFolderModel.py` | Add `ScanEnabled: bool` field |
| `Templates/FileScanning.html` | New "Registered Drives" section; renders the existing `/api/RootFolders` payload with toggle switches + Scan Now buttons; existing dropdown for Manual Scan unchanged |
| `Scripts/SQLScripts/AddRootFolderScanEnabled.py` | `ALTER TABLE RootFolders ADD COLUMN IF NOT EXISTS ScanEnabled BOOLEAN NOT NULL DEFAULT TRUE;` |
| `Features/FileScanning/scanning-on-activity-page.feature.md` | Co-delivered companion (15 criteria for the `/Activity` surface) |

## Deviation from conventions

None. Each criterion is observable externally (SQL read, HTTP response, page render). The schema addition is `NOT NULL DEFAULT TRUE` so existing rows back-fill safely and downstream readers don't need NULL handling. Criterion 9 references a sibling feature doc rather than duplicating its 15 criteria; the link is explicit and the burn-in test (criterion 11) exercises both surfaces.
