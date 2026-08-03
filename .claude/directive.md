# Directive: ingest-pipeline-kiss

**Status:** Active -- phase: IMPLEMENTING
**Opened:** 2026-08-02
**Parent (paused):** orphan-generators-stop
**Slug:** ingest-pipeline-kiss

**Supersedes:** probe-worker-decoupled (opened 2026-08-01, IMPLEMENTING). Rescope driven by operator 2026-08-02: on-demand path-scan/probe UI turned out to be a symptom, not a need. Root need is "20-min discovery + cheap idempotent scan + operator manual trigger + failures visible + never touch a compliant unchanged file again". ProbeWorker + `Workers.ProbeEnabled` + scan-loses-probe are keepers; on-demand queues + workers + UI purged.

## Outcome

Ingest pipeline (scan -> probe -> classify -> compliance -> workbucket) that is:
- **Cheap when idle.** Unchanged file = zero DB write, zero ffprobe, zero cascade.
- **Fast when changed.** Sonarr/Radarr webhook triggers immediate scan of the affected path. Full-library discovery cycle <= 20 min.
- **Never touches a compliant unchanged file again.**
- **Self-consistent.** Every write to a compliance-input column recomputes downstream state before returning; no periodic sweep, no stuck rows.
- **Two operator surfaces.** "Sync Path" button (immediate scan of a canonical path). `/Failures` page (list of stuck files + reason + retry).

## Domain Decisions

Set by operator 2026-08-02. WHAT, not HOW.

**DD_A. Chain is derivation, idempotent, cascade-on-change.**
Six stages (scan -> probe -> classify -> compliance -> workbucket -> transcode-readiness). Each writes only when its input changed. Each cascades to the next in the same call. Unchanged input = no work.

**DD_B. One SQL per RootFolder per scan tick.**
Batch fetch MediaFiles rows for the RootFolder, diff in memory against disk walk output, batch write only the diffs. No per-file SQL. No app-side cache.

**DD_C. Two workers + one webhook.**
ScanWorker walks filesystem on continuous cadence. ProbeWorker polls `Resolution IS NULL OR NeedsReprobe = TRUE` fleet-wide. Sonarr/Radarr webhook (`POST /api/Ingest/Webhook`) interrupts to schedule immediate scan of the affected RootFolder.

**DD_D. No queues except retry state.**
Auto-chain is emergent from shared column state: probe polls the flag scan sets. `NeedsReprobe`, `FFprobeFailureCount` are column-based retry state. No `OnDemand*Requests` tables.

**DD_E. Two operator surfaces.**
(1) "Sync Path" button on `/Settings` -- operator types canonical path, backend triggers immediate scan of that path.
(2) `/Failures` page -- table of stuck files (scan failed, probe failed, cap hit) with reason + per-row retry button.

**DD_F. Writer-owns-cascade rule.**
Every write to a compliance-input column recomputes derived downstream state in the same call. Codified as `.claude/rules/writer-owns-cascade.md` + enforced by contract test grepping for the anti-pattern.

## Implementation (Claude's how)

### Scan
- `FileScanningBusinessService.PerformScan` simplified to: walk + batch-diff + batch-write. Kill `CleanupDuplicateMediaFiles` per-scan, kill `CalculateDirectorySize` pre-scan walk, kill `_RunSizeSurvey` in its entirety.
- Batch fetch: `SELECT StorageRootId, RelativePath, filesize, filemodificationtime FROM MediaFiles WHERE StorageRootId = ?` per RootFolder.
- In-memory diff: `new / changed / deleted` sets.
- Batch write via `execute_values`: INSERT new + UPDATE changed (sets `NeedsReprobe = TRUE`) + soft-delete missing.
- `MediaFiles UNIQUE (StorageRootId, RelativePath)` migration; idempotent; gated on pre-audit for existing dupes.
- `RootFolders.TotalSizeGB` = aggregate from `MediaFiles.filesize` post-scan (single UPDATE), not pre-scan walk.

### Probe
- `ProbeWorker` (already shipped) keeps fleet-wide poll on `Resolution IS NULL OR NeedsReprobe = TRUE`. No RootFolder scoping.
- After every probe write, ProbeWorker calls `QueueManagementBusinessService.RecomputeForFiles([id])`. Verify existing; add if missing.
- On probe failure: increment `FFprobeFailureCount`, write `LastFFprobeError`; when count >= `MaxFFprobeFailures`, row stops being claimed. Visible in `/Failures`.

### Classifier
- `ContentClassifierService` after `WriteAssignment` calls cascade: `QueueManagementBusinessService.RecomputeForFiles([id])`. Fixes Full Circle S1 root cause.

### Discovery triggers (three layers)
- Layer 1: `POST /api/Ingest/Webhook` -- Sonarr/Radarr payload, parses target path, enqueues immediate ScanJobs row.
- Layer 2: `POST /api/Sync/Path` (backing "Sync Path" button) -- canonical path, enqueues ScanJobs row.
- Layer 3: `ContinuousScanService` -- keeps existing per-RootFolder alphabetical tick. Cheap when idle (DD_B).

### Failures surface
- New `/Failures` page. Row per stuck file: filename, path, type (Scan/Probe), reason, count, last attempt, [Retry] button.
- Retry sets `NeedsReprobe = TRUE` AND `FFprobeFailureCount = 0`.
- Endpoints: `GET /api/Failures`, `POST /api/Failures/<mediafileid>/Retry`.

### Purge
- `WorkerService/OnDemandScanWorker.py`
- `Features/OnDemandIngest/*` (whole vertical)
- `Scripts/SQLScripts/DropOnDemandScanProbeQueues_<date>.py` drops `OnDemandScanRequests` + `OnDemandProbeRequests` tables.
- `/Settings` Scan + Probe sub-tabs (HTML + JS).
- `WorkerService/Main.py` OnDemandScanWorker wiring.
- Stale docs enumerated under `## Files`.

### Repair (one-shot)
- `Scripts/RecomputeStaleCompliance.py` -- reads `WHERE videocompliantreason LIKE 'missing_input:%' AND <input col> IS NOT NULL`, runs `RecomputeForFiles`, fixes 6 stuck rows.

## Principles Applied

| Decision | Principle | Justification |
|---|---|---|
| One SQL per RootFolder (DD_B) | KISS + DB-is-authority | Avoids per-file gate ceremony; PG batch is what PG is good at |
| Auto-chain via shared column state (DD_D) | KISS + DRY | No new queue mechanism; probe already polls Resolution IS NULL |
| Writer-owns-cascade (DD_F) | DDD + fail-loud | Derived state is a domain invariant; recompute stays with its writer, not deferred to sweeper |
| Sonarr/Radarr webhook (DD_C) | KISS + right-boundary | Sonarr knows first; polling to detect what Sonarr already knows is redundant work |
| Kill on-demand queues (DD_D) | KISS + YAGNI | On-demand was symptom of slow scan; fix scan, symptom disappears |
| /Failures surface (DD_E) | gui-editable-knobs | Retry state is an operator knob; needs GUI |
| Purge stale docs first, write clean docs after | doc-layering + single-SOT | Rewriting on top of accreted docs preserves the accretion; delete-then-write is honest |

## Docs-first (Path 2, R13 override)

Feature + flow docs are the SPEC for this directive. Code implements approved docs, not the other way around. R13 override authorized 2026-08-02: durable `*.feature.md` / `*.flow.md` files created during NEEDS_DOC_AUTHORING phase (before code lands). No `## Promotions` at DELIVERING -- docs born in their permanent home.

### R13 overrides

- ingest.flow.md
- Features/FileScanning/scan.feature.md
- Features/MediaProbe/probe.feature.md
- Features/ContentClassifier/classifier.feature.md
- Features/Failures/failures.feature.md
- Features/Ingest/ingest-webhook.feature.md

## Acceptance Criteria

### A. Idempotence + cheap-when-idle

C1. **Unchanged file produces zero MediaFiles write.** ScanJob run against subtree where every file's (size, mtime) matches DB completes with 0 rows written (INSERT+UPDATE+DELETE counts all zero). Contract test: seed known state, run scan, assert row counts.

C2. **Unchanged RootFolder produces one SELECT + zero writes per tick.** Instrumented scan reports `sql_selects = 1, sql_writes = 0` on unchanged input. Contract test asserts via query log capture.

C3. **Continuous scan cycle over unchanged full library completes in < 5 minutes on target hardware.** Deploy + measure.

### B. Fast-when-changed

C4. **File appearance triggers discovery within one continuous tick OR one webhook round-trip.** Test: drop test file, observe MediaFiles row within one tick of the RootFolder scanner OR within seconds of webhook.

C5. **File modification triggers re-probe.** Change file mtime/size on disk, next scan sets `NeedsReprobe = TRUE`, next ProbeWorker tick re-probes, cascade recomputes compliance.

C6. **Sonarr/Radarr webhook endpoint exists.** `POST /api/Ingest/Webhook` accepts standard Sonarr/Radarr payload, extracts target path, enqueues immediate ScanJobs row for affected RootFolder, returns 200. Contract test posts canned payload; asserts ScanJobs row appears.

C7. **Sync Path GUI button exists.** `/Settings` page has "Sync Path" input + button; POST body `{CanonicalPath}` to `POST /api/Sync/Path`; returns `{Success, ScanJobId}`. Backend validates prefix against StorageRoots. Contract test.

### C. Writer-owns-cascade

C8. **ContentClassifierService.WriteAssignment triggers cascade.** After WriteAssignment, `QueueManagementBusinessService.RecomputeForFiles([id])` called. Contract test: mock WriteAssignment, assert cascade call.

C9. **ProbeWorker post-write triggers cascade.** After probe writes metadata columns, cascade recomputes compliance for the file. Contract test.

C10. **Every compliance-input writer is enumerated + verified to cascade.** Rule `.claude/rules/writer-owns-cascade.md` lists every writer. Contract test greps for writes to enumerated columns; every hit must be within a function whose body also calls RecomputeForFiles.

C11. **Zero rows with `videocompliantreason = 'missing_input:*' AND <that input> IS NOT NULL`.** SQL-level assertion after repair script runs. Fleet-wide.

### D. Failures surface

C12. **`/Failures` page renders every stuck file.** Filters: `FFprobeFailureCount >= cap OR scan failed`. Shows filename, path, type, reason, count, last attempt. Contract test asserts rendering.

C13. **`POST /api/Failures/<id>/Retry` resets state.** Sets `NeedsReprobe = TRUE, FFprobeFailureCount = 0`. Row picked up by ProbeWorker next tick. Contract test.

### E. Purge

C14. **On-demand infra deleted.** Directory `Features/OnDemandIngest/` does not exist. `WorkerService/OnDemandScanWorker.py` does not exist. `OnDemandScanRequests` + `OnDemandProbeRequests` tables dropped. `/Settings` Scan + Probe sub-tabs removed from HTML.

C15. **SizeSurvey + CleanupDuplicateMediaFiles-per-scan + CalculateDirectorySize-per-scan removed.** Grep `FileScanningBusinessService.py` for `_RunSizeSurvey`, `CleanupDuplicateMediaFiles`, `CalculateDirectorySize` in scan-loop code paths: zero hits.

C16. **`MediaFiles UNIQUE (StorageRootId, LOWER(RelativePath))` constraint verified.** Already exists as `idx_mediafiles_storageroot_relpath_unique` per prior directive. No new migration; verify + reference in scan.feature.md S3. Fleet audit script confirms zero duplicates before IMPLEMENTING lands.

### F. Seam preservation (nothing breaks)

C17. **Downstream consumers of MediaFiles metadata columns unaffected.** No column semantics change. Only writer identity changes (SizeSurvey/probe-pass -> ProbeWorker). Wire shape preserved. Contract test asserts existing column consumers still resolve.

C18. **Existing `/api/RootFolders/<id>/ScanNow` endpoint keeps working.** Reuses the same simplified scan path. Contract test.

C19. **ScanJobs.Phase values remain compatible with `activity-dashboard.flow.md`, `stuck-job-detection.flow.md` consumers.** Any Phase value added via migration to CHECK constraint; removed values not silently dropped. Cross-doc audit at VERIFYING.

C20. **`ContinuousScanService` per-RootFolder alphabetical tick shape preserved.** Only inner scan primitive simplifies; outer scheduler contract unchanged. Contract test.

C21. **`LanguageEnrichmentService.ProbeFile(Force=True)` path unchanged.** Cascade only fires on ProbeWorker's own write path; other probe callers keep existing semantics. Contract test.

## Call-Graph Audit

1. **Multiple flow docs for one conceptual operation.** BEFORE: `FileScanning.flow.md` + `content-classifier.flow.md` describe stages of the same pipeline (walk -> upsert -> classify) with divergent seam vocabulary. AFTER: single `ingest.flow.md` owns the whole chain (scan+probe+classify+compliance+workbucket). Sub-flow only if a stage grows genuine variance (none today).

2. **Mode-branching at orchestration.** BEFORE: `PerformScan` branches on SizeSurvey/Walking/Reconciling/Probing/Completing phases; some phases open files, others don't. AFTER: single-shape orchestration -- walk + diff + batch write. Phase = data (progress heartbeat only), not orchestration.

3. **Shared output columns sparsely populated.** BEFORE: `MediaFiles.videocompliantreason` has `missing_input:AssignedProfile` on rows whose `AssignedProfile IS NOT NULL` (5 of 6 Full Circle S1 rows). Classifier writes AssignedProfile but does not cascade. AFTER: DD_F rule + repair script make column populated consistently.

4. **OOS ambiguity.** All items below categorized (a) fixed in-flight or (b) explicitly deferred.

## Out of Scope

- **Filesystem watchers (inotify / ReadDirectoryChangesW).** (b) explicitly deferred. Polling + webhook sufficient for 20-min budget; watchers add OS-specific + mount-specific reliability risk.
- **Continuous ProbeWorker priority queue.** (b) explicitly deferred. Fleet-wide poll picks up backlog; no priority needed today.
- **On-demand transcode / language enqueue.** (b) explicitly deferred. Same pattern extendable later; not requested.
- **Refactoring existing WorkBucket derivation trigger.** (b) intentionally preserved. Trigger works correctly; DD_A cascade stops before overwriting trigger scope.
- **Scanners config table** (`Features/FileScanning/scanners.feature.md`). Read at NEEDS_DOC_PREREAD; if config-only, folds into new `scan.feature.md` (a); if it owns other behavior, remains as-is with pointer (b).
- **SizeSurvey "biggest files" panel on /Activity.** (a) removed. Separate follow-up if operator wants it back; `SELECT ... FROM MediaFiles ORDER BY filesize DESC LIMIT N` is cheap replacement.

## Files (planned)

### Deleted (NEEDS_DOC_AUTHORING complete 2026-08-02)
- ~~`Features/FileScanning/FileScanning.feature.md`~~ (removed)
- ~~`Features/FileScanning/FileScanning.flow.md`~~ (removed)
- ~~`Features/MediaProbe/media-probe.feature.md`~~ (removed)
- ~~`Features/ContentClassifier/content-classifier.feature.md`~~ (removed)
- ~~`Features/ContentClassifier/content-classifier.flow.md`~~ (removed)

### To delete at IMPLEMENTING
- `WorkerService/OnDemandScanWorker.py`
- `Features/OnDemandIngest/` (entire directory)
- `/Settings` Scan + Probe sub-tab HTML + JS blocks
- `FileScanningBusinessService.py`: `_RunSizeSurvey` + per-scan CleanupDuplicateMediaFiles call + pre-scan CalculateDirectorySize call
- Stale `# directive: <slug>` inline anchors in scan/probe code paths (except path.S* refs which stay)

### Kept (revised scope)
- `Features/FileScanning/ad-hoc-drive-scans.feature.md` -- Registered Drives + per-RootFolder ScanEnabled toggle + Scan Now button; unaffected shape
- `Features/FileScanning/scanners.feature.md` -- shared periodic-service config (Scanners table); ScanWorker + ProbeWorker + StuckJobDetection all read from here

### To edit
- `Features/FileScanning/FileScanningBusinessService.py` -- simplify PerformScan; add batch-diff + batch-write
- `Features/FileScanning/FileScanningRepository.py` -- add BatchFetchForRootFolder + BatchUpsert + BatchSoftDelete
- `Features/ContentClassifier/ContentClassifierService.py` -- add cascade after WriteAssignment
- `WorkerService/ProbeWorker.py` -- verify cascade after probe write
- `WorkerService/Main.py` -- remove OnDemandScanWorker wiring
- `Templates/Settings.html` -- remove Scan/Probe sub-tabs; add Sync Path input; add /Failures link
- `Templates/Settings.js` -- corresponding JS

### To add
- `Scripts/SQLScripts/AddMediaFilesUniquenessConstraint_<date>.py` (idempotent + pre-audit gated)
- `Scripts/SQLScripts/DropOnDemandScanProbeQueues_<date>.py`
- `Features/Ingest/IngestWebhookController.py` -- POST /api/Ingest/Webhook
- `Features/Ingest/IngestWebhookBusinessService.py`
- `Features/Sync/SyncPathController.py` -- POST /api/Sync/Path
- `Features/Failures/FailuresController.py` -- GET + POST /api/Failures/<id>/Retry
- `Features/Failures/FailuresBusinessService.py` + `FailuresRepository.py`
- `Templates/Failures.html` + `Failures.js` -- new page
- `Scripts/RecomputeStaleCompliance.py` -- one-shot repair
- `Tests/Contract/TestScanIdempotence.py` (C1, C2)
- `Tests/Contract/TestScanBatchDiff.py` (DD_B mechanics)
- `Tests/Contract/TestIngestWebhook.py` (C6)
- `Tests/Contract/TestSyncPath.py` (C7)
- `Tests/Contract/TestClassifierCascade.py` (C8)
- `Tests/Contract/TestProbeCascade.py` (C9)
- `Tests/Contract/TestWriterOwnsCascadeEnforcement.py` (C10)
- `Tests/Contract/TestNoStuckCompliance.py` (C11)
- `Tests/Contract/TestFailuresPage.py` (C12, C13)
- `Tests/Contract/TestSeamPreservation.py` (C17, C18, C20, C21)

### To promote at DELIVERING (per R13)
- `ingest.flow.md` (repo root)
- `Features/FileScanning/scan.feature.md`
- `Features/MediaProbe/probe.feature.md`
- `Features/ContentClassifier/classifier.feature.md`
- `Features/Failures/failures.feature.md`
- `Features/Ingest/ingest-webhook.feature.md`
- `.claude/rules/writer-owns-cascade.md` + `.claude/rules-details/writer-owns-cascade.md`

## Progress

- [x] NEEDS_STANDARDS_REVIEW: call-graph audit populated; standards/index.md + rules read; hook R13 override mechanism added (`Get-R13Overrides` + `Test-R13-NoNewFeatureDocs` check)
- [x] NEEDS_PLAN: this doc IS the plan; Files list frozen; R13 overrides block populated
- [x] NEEDS_DOC_PREREAD: read FileScanning.flow.md + content-classifier.flow.md + ad-hoc-drive-scans.feature.md + scanners.feature.md + FileScanning.feature.md + media-probe.feature.md + content-classifier.feature.md
- [x] NEEDS_DOC_AUTHORING: wrote writer-owns-cascade rule + ingest.flow.md + scan/probe/classifier/failures/ingest-webhook feature docs; deleted 5 stale docs; kept ad-hoc-drive-scans + scanners docs. **OPERATOR APPROVAL PENDING BEFORE CODE.**
- [ ] IMPLEMENTING: code lands to match approved docs -- purge on-demand infra -> verify UNIQUE constraint (existing) -> simplify PerformScan -> add batch-diff repository methods -> classifier cascade -> probe cascade -> ingest webhook -> sync path -> /Failures -> repair script -> contract tests
- [ ] VERIFYING: contract tests green; deploy I9 + one Linux worker; measure continuous cycle time; drop test file + observe discovery; verify Full Circle S1 rows classified correctly; smoke Sync Path + webhook + /Failures retry; SEAM CHECK per C17-C21
- [ ] DELIVERING: delivery report; docs already durable (no promotion step)

## Notes

- Parent stack: orphan-generators-stop (paused IMPLEMENTING, HEAD 8f7872e5). scan-broken-restore (paused IMPLEMENTING). docker-purge (DELIVERING).
- **Seam preservation is a hard constraint.** No MediaFiles column semantics change. Only writer identity + cascade discipline changes. C17-C21 gate VERIFYING advance.
- Sonarr/Radarr webhook payload shape: reference Sonarr wiki + validate with real payload before ship; endpoint fails loud on unrecognized shape.
- Discovery cycle time budget: 20 min operator-set; target < 5 min at DD_B batch cost.
- SizeSurvey removal: /Activity "biggest files" panel loses input; separate follow-up if operator wants it back.
- Prior directive `probe-worker-decoupled`: ProbeWorker + Workers.ProbeEnabled + scan-loses-probe stay. On-demand infrastructure deleted (was symptom, not need).
