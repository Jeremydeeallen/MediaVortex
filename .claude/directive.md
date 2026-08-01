# Directive: probe-worker-decoupled

**Status:** Active -- phase: IMPLEMENTING
**Opened:** 2026-08-01
**Parent (paused):** orphan-generators-stop
**Slug:** probe-worker-decoupled

## Outcome

Split ffprobe out of `FileScanningBusinessService.PerformScan` into a standalone `ProbeWorker` capability (mirrors `LanguageWorker` pattern). Decouple probe cadence from scan-cycle-per-RootFolder scoping so Cape Fear TV series (currently waiting up to 60 min for T:\ top-level RootFolder scan to reach probe phase) gets metadata within one poll tick of an idle probe-capable worker.

Add operator-triggered on-demand path scan + on-demand path probe. Operator enters canonical path (`T:\Cape Fear\Season 1`), submits, first idle worker with capability claims + processes. On-demand scan auto-chains: after scan discovers new MediaFiles, an on-demand probe request is enqueued for the same path.

Ships two new sub-tabs under `/Settings` (next to existing Scanners tab).

## Domain Decisions (operator asks)

These are the WHAT. HOW is Claude's responsibility below.

- **Split scan and probe into separate services.** Current coupling means new files wait for the next full-RootFolder scan cycle before probing. That's too slow.
- **Operator wants a GUI Scan interface.** Enter a location, trigger scan of that path immediately.
- **Operator wants a GUI Probe interface.** Enter a location, trigger probe of that path immediately.
- **Motivation:** get specific shows watchable fast, without waiting for the continuous cycle to reach them.
- **Path input format:** canonical (`T:\Cape Fear\Season 1`), matches DB shape.
- **Auto-chain:** on-demand scan should feed on-demand probe automatically. One operator action per path, not two.
- **Worker routing:** operator's constraint = "not busy so it doesn't queue behind a probing or walking scan." Idle workers should take on-demand work; busy workers should not force the request to wait.
- **UI location:** sub-tabs under existing `/Settings` page (there's already a `Scanners` sub-tab there). Don't bloat the GUI with new top-level tabs.
- **Design principle:** KISS. Simplest solution meeting the above.
- **Probe owns "gather all details and classify correctly".** Probe stage writes MediaFiles metadata columns (Resolution, Codec, VideoBitrateKbps, AudioCodec, ContainerFormat, ...). Any downstream state derived from those columns -- WorkBucket, IsCompliant, {Video,Audio,Container}Compliant -- becomes stale the moment the probe writes new values. Probe stage is responsible for making that derived state consistent with the columns it just wrote. Operator does not manually recompute compliance; probe does it for every file it touches. Related fix: compliance evaluators fail-loud on missing inputs (return `(None, 'missing_input:<field>')`, not silent `(True, None)`) so `Unclassified` catches gaps instead of `Compliant` hiding them.

## Implementation (Claude's how)

- **ProbeWorker capability** — new WorkerService loop mirroring `LanguageWorker.py` shape; polls MediaFiles where `Resolution IS NULL AND FFprobeFailureCount < N` regardless of RootFolder ownership.
- **`Workers.ProbeEnabled` column** — added via idempotent migration; wired through `BuildClaimPredicate` allowlist.
- **`FileScanningBusinessService.PerformScan` loses probe-phase call** — SRP: scan only inserts/updates MediaFiles rows.
- **Two on-demand queue tables** — `OnDemandScanRequests` + `OnDemandProbeRequests`. Claim via `UPDATE ... WHERE Id = (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING ...`. Idle workers race; busy workers can't grab — satisfies the operator's "not busy" constraint without a worker-picker dropdown.
- **Auto-chain via ProbeRequests row insert** — when a scan-request completes and inserted new MediaFiles under its path, the scan worker inserts a matching `OnDemandProbeRequests` row for the same `(StorageRootId, RelativePath)`.
- **REST endpoints** — `POST /api/OnDemandScan` + `POST /api/OnDemandProbe` (body: `{CanonicalPath}`); `GET /api/OnDemandScan/Recent` + `GET /api/OnDemandProbe/Recent` for the recent-20 table.
- **GUI** — new collapsible section in `/Settings` between Scanning + Workers sections. Two-panel Scan / Probe with canonical input + submit + recent-20 table.
- **Capability-thread ActiveJobs recording** — ProbeWorker + OnDemandScanWorker insert an ActiveJobs row at work-start + delete at finally. Makes DrainWorker's existing `WHERE WorkerName=?` count truthful. Same shape LanguageWorker already uses.
- **OnDemandScanWorker → StartScanning (not PerformScan)** — reuse the higher-level entry that owns job creation, canonical→local translation, ScanJobs progress heartbeat, terminal status write. Discovered mid-implementation; three bugs in the direct-PerformScan path (missing Recursive arg, wrong path type, missing CurrentJobId setup) were fixed by routing through StartScanning.

## Principles Applied

Decision → principle justification:

| Decision | Principle | Justification |
|---|---|---|
| ProbeWorker mirrors LanguageWorker shape | **DRY** | Same loop/claim/backend pattern already established; no new mechanism |
| Split scan and probe into separate capability workers | **SRP** (SOLID) | Scan = disk walk + MediaFiles inserts; Probe = ffprobe metadata population. Different failure modes, different scaling, different SoT |
| `Workers.ProbeEnabled` column + `BuildClaimPredicate` allowlist | **OCP** (SOLID) | Adding a capability = one column + one allowlist entry. Zero changes to the predicate builder itself. Closed against modification |
| ActiveJobs shared table (not per-capability busy tables) | **DDD + DRY** | ActiveJobs already means "in-flight work"; every capability doing work IS an active job. Reusing the existing bounded-context term prevents parallel schemas |
| Reuse ActiveJobs so DrainWorker is truthful (not extend DrainWorker) | **KISS + DRY** | Existing query `WHERE WorkerName=?` already sees the whole worker's load. Adding N-arm capability-aware queries would multiply drain-query surface area |
| Kill-timeout removed after drain became truthful | **Root-cause fix over bandaid** | Timeout was compensating for drain blindness. Once drain is truthful, kill can be immediate. Bandaid deleted |
| On-demand queue via `FOR UPDATE SKIP LOCKED` (not worker-picker UI) | **KISS + Open/Closed** | Idle workers race for rows via existing claim discipline. New capability worker = same claim shape. Zero operator surface for routing |
| GUI = collapsible section, not new sub-tabs framework | **KISS** | Settings.html already uses `settings-section` pattern. Reusing it fits the operator's "don't bloat the GUI" rule; adding a sub-tabs framework would introduce a UI paradigm the app doesn't otherwise use |
| Canonical path input only (not canonical + local) | **KISS + SoT** | DB shape is canonical everywhere. Accepting local paths would require worker-mount awareness + shape auto-detect in the input parser. One shape in, one shape stored, one shape rendered |
| Auto-chain scan → probe via queue-row insert (not in-process call) | **SRP + DDD** | Scan worker's job ends at "MediaFiles written." Probe worker's job begins at "MediaFiles need metadata." Queue row is the DDD event that crosses the boundary. Preserves single-responsibility per worker |
| OnDemandScanWorker routes via StartScanning (not PerformScan direct) | **DRY** | StartScanning already handles job lifecycle + heartbeat + path translation. Re-implementing = fork risk |
| Two new on-demand tables (not one polymorphic table) | **SRP** | Different fields (`FilesDiscovered` vs `FilesProbed`), different downstream consumers. Polymorphism would demand nullable-everything + type discrimination. Two focused tables are clearer |

## Deliverables at DELIVERING (per R13)

Feature.md + flow.md creation is blocked until directive advances to DELIVERING. At that point Promotions row-map:

| Source (directive) | Target (durable) |
|---|---|
| Domain Decisions + Principles Applied + Acceptance Criteria | new `WorkerService/ProbeWorker.feature.md` (What/Criteria/Workflows/Seams/Status) |
| ProbeWorker fetch cycle + on-demand poll integration | new `WorkerService/probe-worker.flow.md` (single-page ST1..ST5 for poll → fetch → probe → stamp) |
| OnDemandIngest business logic + endpoints + GUI | new `Features/OnDemandIngest/on-demand-ingest.feature.md` |
| FileScanning loses probe-phase | update `Features/FileScanning/FileScanning.feature.md` |
| MediaProbe consumed by ProbeWorker + on-demand invocation shape | update `Features/MediaProbe/MediaProbe.feature.md` |
| Capability-thread ActiveJobs invariant | update `.claude/rules/claim-authority.md` or new rule `capability-drain-truthfulness.md` (every capability thread records its ActiveJobs row so DrainWorker sees it) |
| GUI-editable knobs (`ProbeEnabled` column) | update `.claude/rules/gui-editable-knobs.md` if needed (already covered by Settings /Admin pattern) |

## Acceptance Criteria

### A. Split ffprobe out of scan cycle

C1. **`ProbeWorker` exists as a standalone WorkerService capability.** Shape mirrors `WorkerService/LanguageWorker.py`: loop with configurable poll interval, batch fetch via `BuildClaimPredicate(WorkerName, 'ProbeEnabled')`, per-file process + stamp, LogInfo/LogWarning on outcome. Verifiable: `Tests/Contract/TestProbeWorkerContract.py` asserts fetch query gates on `Workers.ProbeEnabled=TRUE`.

C2. **`Workers.ProbeEnabled` column added.** New nullable BOOLEAN column via `Scripts/SQLScripts/AddProbeEnabledColumn_2026_08_01.py`. Existing workers get NULL default (treated as FALSE by BuildClaimPredicate). Idempotent `ADD COLUMN IF NOT EXISTS`.

C3. **Continuous scan drops the probe phase.** `FileScanningBusinessService.PerformScan` no longer calls `MediaProbeService.ProbeFilesNeedingMetadata(...)` inline. Scan cycle only inserts/updates MediaFiles rows + walks disk. `Tests/Contract/TestScanDoesNotProbe.py` grep-fences the deletion.

C4. **`ProbeWorker` picks up any file where `Resolution IS NULL AND FFprobeFailureCount < MediaProbeBusinessService.MaxFFprobeFailures` regardless of RootFolder ownership.** Fetch query uses `WHERE Resolution IS NULL AND FFprobeFailureCount < ? AND StorageRootId IS NOT NULL AND RelativePath IS NOT NULL AND <ProbeEnabled predicate>` -- no RootFolder scoping. Verifiable: bulk-insert 100 fresh MediaFiles rows with no RootFolder row + observe ProbeWorker stamps all 100 within N poll ticks.

### B. On-demand scan/probe queues

C5. **`OnDemandScanRequests` table exists.** Columns: `Id BIGSERIAL, StorageRootId BIGINT NOT NULL, RelativePath TEXT NOT NULL, RequestedAt TIMESTAMPTZ NOT NULL DEFAULT NOW(), ClaimedBy TEXT, ClaimedAt TIMESTAMPTZ, CompletedAt TIMESTAMPTZ, Status TEXT NOT NULL DEFAULT 'Pending' CHECK (Status IN ('Pending','Claimed','Complete','Failed')), FilesDiscovered INT, ErrorMessage TEXT`. Migration idempotent.

C6. **`OnDemandProbeRequests` table exists.** Same shape as C5 with `FilesProbed INT` instead of `FilesDiscovered`. Idempotent.

C7. **Claim discipline.** Both tables claimed via single `UPDATE ... WHERE Id = (SELECT Id ... FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING ...` pattern. Two workers cannot claim the same row (DB proves it). Idle workers (no ActiveJobs, no in-flight scan) poll their respective queue before scheduled work.

C8. **Auto-chain: on-demand scan enqueues probe.** When an `OnDemandScanRequests` completes and inserted at least one new MediaFile under the path, the scan worker inserts a matching `OnDemandProbeRequests` row for the same (StorageRootId, RelativePath). Verifiable: single-worker test — submit scan request for a path with 5 fresh files, observe 5 MediaFiles rows + 1 OnDemandProbeRequests row + all 5 probed within ~1 min.

### C. GUI

C9. **`/Settings` gains two sub-tabs: `Scan` + `Probe`.** Preserves existing `Scanners` sub-tab. Each new sub-tab: single text input (canonical path), one submit button, table of recent 20 requests with columns (Path, Requested, Claimed By, Status, Files, Elapsed). Verifiable: GET `/settings` renders both sub-tabs; each POSTs to its endpoint.

C10. **POST `/api/OnDemandScan` + POST `/api/OnDemandProbe`.** Body: `{"CanonicalPath": "T:\\Cape Fear\\Season 1"}`. Server parses via `Path.FromLegacyString(canonical, StorageRoots).StorageRootId + .RelativePath`, INSERTs a queue row, returns `{Success, RequestId, Message}`. Verifiable: contract test posts a valid path, receives `Success=True + RequestId`.

C11. **GET `/api/OnDemandScan/Recent` + GET `/api/OnDemandProbe/Recent`.** Returns last 20 rows for the respective queue. Powers the recent-runs table on each sub-tab. Verifiable: contract test asserts response shape.

C12. **Path validation at boundary.** If the canonical prefix doesn't match any StorageRoot, endpoint returns `{Success: False, Message: 'Unknown storage root: T:\\ ...'}` with 400. No queue row inserted.

### D. Backward compat

C13. **`MediaProbeBusinessService.ProbeFile / .ProbeFilesNeedingMetadata` still callable.** ProbeWorker uses `ProbeFile(MediaFileId, Force=False)` internally. `LanguageEnrichmentService.ProbeFile(Force=True)` path unchanged. No caller breakage.

## Call-Graph Audit

1. **Multiple flow docs for one conceptual operation:** No new. Continuous scanning stays in `FileScanning.flow.md`; probing spins off (needs new `ProbeWorker.flow.md` at DELIVERING).
2. **Mode-branching at orchestration:** No new. WorkerService capability start/stop for `ProbeEnabled` mirrors existing `LanguageEnabled` branch in `WorkerService/Main.py`; not a new branch, just a new instance of the same pattern.
3. **Shared output columns sparsely populated:** `MediaFiles.Codec + .Resolution + .VideoBitrateKbps + .AudioCodec + .AudioLanguages + ...` currently populated by scan-cycle probe pass. Post-fix populated by ProbeWorker. Same columns, different populator. No sparsity change.
4. **OOS ambiguity:** All items classified below.

## Out of Scope

- **Kill old scheduled probe queue.** (a) not addressed. `MediaProbeBusinessService.ProbeFilesNeedingMetadata` stays callable so nothing else breaks; ContinuousScanService just stops calling it.
- **Worker selection UI on on-demand tabs.** (b) known-preserved simplicity. System auto-routes to first idle worker; no dropdown per the KISS decision.
- **`OnDemandTranscodeRequests` / `OnDemandLanguageRequests`.** (a) not addressed. Same pattern extendable later if needed; not needed today.
- **Progress bar / live status on sub-tab during in-flight scan/probe.** (a) not addressed. Refresh-to-see table row Status is sufficient; live streaming = separate scope.
- **Cape Fear existing MediaFiles.** (a) not addressed here. Once ProbeWorker ships + a capable worker has `ProbeEnabled=True`, existing 1490 fresh-scanned-unprobed rows get processed automatically. No manual backfill needed.

## Files (planned)

To create:
- `WorkerService/ProbeWorker.py` (C1)
- `Scripts/SQLScripts/AddProbeEnabledColumn_2026_08_01.py` (C2)
- `Scripts/SQLScripts/AddOnDemandScanProbeQueues_2026_08_01.py` (C5 + C6)
- `Features/OnDemandIngest/OnDemandIngestController.py` (C10 + C11 + C12) — new vertical for the two endpoints; feature.md colocated at DELIVERING
- `Features/OnDemandIngest/OnDemandIngestBusinessService.py` (path validation + queue insert + recent-query)
- `Features/OnDemandIngest/OnDemandScanRequestsRepository.py` + `OnDemandProbeRequestsRepository.py` (queue claim + list)
- `Tests/Contract/TestProbeWorkerContract.py` (C1)
- `Tests/Contract/TestScanDoesNotProbe.py` (C3)
- `Tests/Contract/TestOnDemandIngestQueues.py` (C5 + C6 + C7 + C8)

To edit:
- `WorkerService/Main.py` (start/stop ProbeWorker capability lifecycle, mirror LanguageWorker wiring)
- `Features/FileScanning/FileScanningBusinessService.py` (delete probe-phase call at ~line 895-907)
- `Core/Database/WorkerCapabilityPredicate.py` (allowlist `ProbeEnabled` column name)
- `Templates/Settings.html` (add two sub-tabs; wire to new endpoints)
- `Templates/Settings.js` or equivalent (client-side submit + recent-list polling)

At DELIVERING, promote content into:
- `WorkerService/ProbeWorker.feature.md` (new)
- `WorkerService/probe-worker.flow.md` (new; single-page flow for the poll → fetch → probe → stamp cycle)
- `Features/OnDemandIngest/on-demand-ingest.feature.md` (new)
- `Features/FileScanning/FileScanning.feature.md` (updated to remove probe responsibility)
- `Features/MediaProbe/MediaProbe.feature.md` (updated with ProbeWorker consumer + on-demand invocation shape)

## Progress

- [ ] NEEDS_STANDARDS_REVIEW: call-graph audit populated (above)
- [ ] NEEDS_PLAN: implementation order approved
- [ ] NEEDS_DOC_PREREAD: read colocated docs (WorkerService.feature.md, FileScanning.feature.md, MediaProbe if exists)
- [ ] IMPLEMENTING: DB migrations (C2, C5, C6), ProbeWorker (C1, C4), scan-cycle unhook (C3), on-demand endpoints (C7-C12), GUI (C9), tests
- [ ] VERIFYING: contract tests green; deploy to at least one worker; flip its ProbeEnabled=True; observe Cape Fear TV series (1490 unprobed rows) get metadata within minutes; submit on-demand scan for a fresh path + observe auto-chain probe
- [ ] DELIVERING: promotions into feature/flow docs

## Notes

- Parent stack: orphan-generators-stop (paused at IMPLEMENTING, contract tests green, HEAD 8f7872e5 fleet-deployed). scan-broken-restore below that (also paused IMPLEMENTING). docker-purge below that (DELIVERING).
- Contract test for C3 must survive a scan cycle running cleanly without the probe pass (metadata population depends entirely on ProbeWorker post-change).
- LanguageWorker path-missing infinite-retry improvement stays out of scope; if user wants it, separate directive later.
- Existing `MediaProbeBusinessService.ProbeFile` remains the leaf primitive; ProbeWorker orchestrates + throttles, doesn't reimplement probe logic.
