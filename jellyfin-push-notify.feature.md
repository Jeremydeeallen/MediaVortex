# Feature: Jellyfin Push Notifications on File Mutations

**Slug:** jellyfin-push-notify

## What It Does

When MediaVortex moves, renames, replaces, or deletes a media file under any
storage root that Jellyfin indexes (currently `T:\` → BrainTv, `M:\` →
SynologyMovies, `Z:\` → SynologyXXX as seen by their respective workers),
MediaVortex POSTs a notification to Jellyfin's
`POST /Library/Media/Updated` endpoint with the affected path(s) and the
mutation type (`Created` | `Modified` | `Deleted`). Jellyfin re-indexes those
specific items within seconds instead of waiting for its next library-wide
scan.

The notification is fire-and-forget: failure to reach Jellyfin logs a WARNING
and continues. MediaVortex's correctness does NOT depend on Jellyfin
acknowledging the notify.

## Why This Exists

The infrastructure-side `jellyfin-efficiency` feature found that Jellyfin
10.11.x has an upstream scanner regression (issue #15070, fix deferred to
10.12.x) where a full library scan re-validates ~170k items and re-INSERTs
~75k image rows even when nothing changed. Wall-clock floor is ~18 min per
scan with our library on this hardware. A 2h polling cadence is the current
mitigation but the root fix is **stop polling**: have the systems that
actually mutate files tell Jellyfin what changed. MediaVortex is one of two
such systems (the other is the arr-stack; arr already supports Jellyfin
Connect natively).

## Out of scope

The Jellyfin "Scan Media Library" 2h interval trigger stays ON. It is
the safety net for everything this feature does NOT cover -- arr-stack
mutations (Sonarr/Radarr imports, deletes, renames) and any other
source that touches the libraries. Disabling polling requires the arr
stack to also push to Jellyfin, which is a separate configuration
task in the infrastructure repo and is NOT this feature's concern.

This feature's completion criterion is "MediaVortex mutations push to
Jellyfin." It does not depend on, and does not block, the polling-off
decision.

## Success Criteria

1. **Notify on every file-mutation choke point.** MediaVortex calls
   `NotifyJellyfin(Updates)` at every site that creates, moves, renames, or
   deletes a media file Jellyfin would index. Specifically:
   - `Features/FileReplacement/FileReplacementBusinessService.py` —
     after a successful replace (original → archive, transcoded → original
     location): one notify with `UpdateType=Modified` for the canonical
     path, plus `UpdateType=Deleted` for any path Jellyfin previously
     indexed that no longer exists.
   - `Features/FileScanning/*` — when reconcile detects a new or deleted
     file that wasn't introduced by MediaVortex itself (i.e. external
     additions reach Jellyfin without waiting for a poll). Optional
     if FileScanning runs frequently enough that the lag is acceptable.
   - Any future site that calls `shutil.move`, `os.replace`, `os.rename`,
     or `os.remove` on a path under a Jellyfin-watched root.
   - Verifiable: grep the codebase for `shutil.move|os.replace|os.rename|os.unlink|os.remove`
     under `Features/` and `Services/`; every hit either calls
     `NotifyJellyfin` immediately after success or has a one-line code
     comment explaining why the path is not Jellyfin-visible.

2. **Path translation respects worker shape.** The notification payload
   carries the path AS JELLYFIN SEES IT (Linux mount path on the Jellyfin
   host, e.g. `/mnt/SynologyMovies/...`), not the worker's local path
   (`M:\...` on Windows, `/mnt/movies/...` on a Linux worker). The
   translation goes through the same path-storage layer
   (`Core/Path.Resolve`) but resolves against a synthetic
   `__jellyfin__` worker entry in `StorageRootResolutions`. Verifiable:
   `StorageRootResolutions` contains rows for `WorkerName='__jellyfin__'`
   covering every StorageRoot Jellyfin indexes; the notify payload for a
   replaced file matches the absolute path `ls` shows on the Jellyfin
   host.

3. **Batching.** When a single business operation mutates N files (bulk
   replace, bulk delete), N updates are sent in ONE HTTP request, not N
   requests. `NotifyJellyfin` accepts a list; callers that mutate one
   file at a time pass a single-element list. Verifiable: instrument a
   bulk replace of 10 files; tcpdump on the Jellyfin host shows one POST
   carrying 10 `Updates` entries.

4. **Failure is non-fatal.** Network errors, 5xx responses, timeouts, or
   missing config (`SystemSettings.JellyfinHost` or `.JellyfinApiKey`
   unset) log a WARNING via `LoggingService.LogWarning(...)` and return
   without raising. MediaVortex business logic continues regardless of
   Jellyfin's state. Verifiable: stop Jellyfin, run a replace, observe
   the WARNING in the Logs table, confirm MediaVortex did not error
   out, confirm the replace itself committed normally. Restart Jellyfin
   and confirm the next mutation notifies successfully.

5. **Timeout cap.** The HTTP call uses a hard `timeout=5` seconds (connect
   + read). Verifiable: simulate a hung Jellyfin (firewall-drop the
   response port; or point `SystemSettings.JellyfinHost` at a sink that
   accepts connections but never responds); confirm the notify returns
   within ~5s with a WARNING, not after default-socket-timeout minutes.

6. **Config in `SystemSettings`, read fresh.** Reuses the
   `JellyfinHost`/`JellyfinApiPort`/`JellyfinApiKey` rows already managed
   by `Features/Optimization/JellyfinService` (operator sets creds in one
   place, both consumers see them). All three are read fresh on every
   `NotifyJellyfin` call (no module-scope caching, per the
   "don't cache DB-backed settings" rule). The API key never appears in
   env vars, compose files, or any committed file. Verifiable: grep the
   repo for the key value returns zero hits;
   `JellyfinNotifyService._ReadSetting` calls
   `SystemSettingsRepository().GetSystemSetting(...)` (no cache layer).

7. **Idempotent under retry.** If a mutation results in two NotifyJellyfin
   calls for the same path (e.g. caller retries), Jellyfin's behaviour is
   identical — it re-validates the same item twice harmlessly. No
   client-side dedup required. Verifiable: send the same notify twice in
   a row; both return 204, the second is observably a no-op in the
   Jellyfin scan log (item not re-imported, just re-checked).

8. **No suppression toggle.** `NotifyJellyfin` is unconditional once the
   caller invokes it: if FileReplacement (or any other caller) moved a
   file, Jellyfin learns about it. There is no `JellyfinNotifyDryRun`
   gate -- a downstream-of-state-change signal must not be silenceable,
   or real changes drift out of sync with Jellyfin. (Operator preview of
   would-be notifies is provided by the off-pipeline
   `Scripts/DryRunJellyfinNotify.py`, not by a runtime toggle.)
   Verifiable: grep the service file for `DryRun` returns zero hits;
   any successful FileReplacement produces a `JellyfinNotify: sent N
   update(s), status=...` log line.

9. **Observability.** Every notify records to the Logs table at INFO
   level with the count of updates and the HTTP status code. Failures
   are WARNING. A `/metrics`-compatible counter is NOT required for v1,
   but the log shape MUST be greppable for later metric extraction
   (e.g. consistent prefix `JellyfinNotify:`).

10. **Failure WARNINGs include enough context to diagnose
    server-side 5xx responses.** Today the non-2xx WARNING at
    `Services/JellyfinNotifyService.py:169-173` logs only the status code,
    update count, and a 200-char body slice -- not the translated paths
    that were sent. Jellyfin's `Error processing request.` 500 body is
    opaque and the actual cause (path not mapped to any library, separator
    mismatch, plugin error, etc.) is unrecoverable from MediaVortex logs
    alone. Add the `Translated` payload (or at minimum the first path and
    UpdateType) to the WARNING so the next 500 is debuggable without
    needing to attach to a live process or trawl Jellyfin's own log.
    Verifiable: induce a 500 (e.g. send an UpdateType for a path Jellyfin
    has no library root for), grep the log line, confirm the path appears.

## Decision: `/Library/Media/Updated` (parent-folder refresh)

Jellyfin exposes three endpoints that can trigger a re-scan; we picked
the middle one. Verified live 2026-05-22.

| Endpoint | Scope | Inputs needed | Notes |
|---|---|---|---|
| `POST /Library/Refresh` | Full library scan | API key | What Sonarr/Radarr's "Jellyfin Connect" notifications historically use. Broad; relies on Jellyfin's internal coalescing to not blow up under burst. |
| `POST /Library/Media/Updated` (**chosen**) | Parent folder of the path | API key + path | We tell Jellyfin "this folder changed"; it re-stats every file in that folder and re-probes only the ones whose mtime moved. Coalesces ~60s; multiple updates to the same parent dedupe into one refresh task. |
| `POST /Items/{itemId}/Refresh` | Single item | API key + Jellyfin item GUID | Tightest scope, but the GUID doesn't exist yet for a just-created file. Requires a `Items?Path=...` lookup first → two roundtrips per notify, plus failure modes if Jellyfin hasn't imported the item yet. |

**Why the middle endpoint:**
- Strictly more targeted than what arr-stack does -- arr says "refresh
  everything," we say "refresh this season." Side benefit observed in
  testing: Jellyfin refreshing a season folder cleans up stale entries
  for *other* episodes in that folder that we never explicitly notified
  about (S01E06 got auto-cleaned when we notified for S01E07).
- Per-item refresh would require us to either (a) track the Jellyfin
  GUID in MediaVortex (cross-system state, brittle) or (b) make an
  extra lookup roundtrip per notify (more network failure surface).
  Neither is worth it for a marginal refresh-scope win.
- Jellyfin's ~60s coalescing window applies to ALL three endpoints; we
  wouldn't get faster updates by choosing a different scope.

**Observed timing in production (2026-05-22):**
- POST → 204 ACK: <200ms
- 204 ACK → library actually refreshed: ~60s (Jellyfin's
  coalescing window for `/Library/Media/Updated`)
- Library refreshed → new file fully indexed (intro/credits analysis,
  thumbnails, metadata): another ~30-90s depending on file size

The 60s delay is the only meaningful UX cost. If an operator clicks
play within that window they get a "Could not find file" error
referencing the old `.mkv`. Documented as expected behavior; not a bug.

## Implementation Sketch (non-binding)

- New module: `Services/JellyfinNotifyService.py`
- Public surface: one function
  ```python
  def NotifyJellyfin(Updates: List[Dict[str, str]]) -> None:
      # Updates: [{"Path": "/mnt/movies/x.mkv", "UpdateType": "Modified"}, ...]
  ```
- Path translation: resolve `(StorageRootId, RelativePath)` against the
  synthetic `__jellyfin__` worker via `Core.Path.LocalPath / Core.Path.Path.Resolve`. If no
  resolution exists for a given root, log WARNING and skip that entry
  (don't fail the whole batch).
- HTTP: `requests.post(f"http://{JellyfinHost}:{JellyfinApiPort}/Library/Media/Updated",
  headers={"X-Emby-Token": JellyfinApiKey},
  json={"Updates": Updates}, timeout=5)`.
  Host / port / key / dry-run come from `SystemSettings` via
  `SystemSettingsRepository.GetSystemSetting(...)`, read fresh on every
  `NotifyJellyfin` call (no module-scope caching).
- Wire into `FileReplacementBusinessService` first (highest-value site),
  then audit other mutation points per criterion 1.

## Test Plan (criterion-driven)

- Unit: mock `requests.post`, assert payload shape, timeout, header.
- Unit: dry-run mode logs but does not call.
- Unit: missing env var → WARNING + no raise.
- Unit: 500 response → WARNING + no raise.
- Unit: connection timeout → WARNING + no raise within ~5s.
- Integration (manual): replace one file, observe Jellyfin scan log shows
  re-import of that exact item within 30s; full library scan was NOT
  triggered.
- Integration (manual): bulk replace 10 files, observe one POST in
  tcpdump on the Jellyfin host carrying 10 entries.

## Status

**COMPLETE.**
Service implemented, wired into FileReplacement + DuplicateDetection,
unit tests green. Config in `SystemSettings`; reuses existing
`JellyfinHost`/`JellyfinApiPort`/`JellyfinApiKey` rows shared with
`Features/Optimization`. No runtime suppression toggle -- `NotifyJellyfin`
fires unconditionally once invoked. Confirmed end-to-end against
Jellyfin on `10.0.0.179`: notifies POST with status=204, Jellyfin
refreshes the parent folder ~60s later, new files become playable with
correct series/episode metadata.

**Notify shape change 2026-05-27 (root-cause fix for an orphan-import bug):**
`FileReplacementBusinessService._NotifyJellyfinOfReplacement` previously
sent `Deleted(old) + Created(new)` in a single POST whenever the source
path differed from the new path. That shape caused Jellyfin to orphan
the new item (`Series=null`, `IndexNumber=null`) when source and target
shared the same extension (typical re-transcode of a `-mv.mp4`):
S02E10 and S03E16 of 30 Rock both orphaned this session. The canary
that worked (Steven Universe S01E37) had `.mkv -> .mp4` -- different
extensions -- which Jellyfin processed cleanly. Fix: always send a
single `Modified(new)`. Jellyfin's directory-coalescing scan
(`/Library/Media/Updated` is folder-scoped, ~60s window) naturally
sweeps stale entries for the old filename, observed in the 2026-05-22
live verify ("swept stale entries for other episodes in the same
folder"). One notify per replacement, no orphans.

The Jellyfin 2h interval scan stays on -- see Out of scope.

### Progress

- [x] 1. Document the upstream Jellyfin scanner regression on the
      infrastructure side (`infrastructure/docs/features/jellyfin-efficiency.md`)
- [x] 2. Draft this feature doc with criteria + implementation sketch
- [x] 3. Operator review + approval of criteria (approved 2026-05-22)
- [x] 4. Seed `__jellyfin__` rows into `StorageRootResolutions`
      (`Scripts/SQLScripts/SeedJellyfinResolutions.py`, idempotent).
      Reuses existing `JellyfinHost`/`JellyfinApiPort`/`JellyfinApiKey`
      rows -- not seeded here, managed by `Features/Optimization`.
- [x] 5. Implement `Services/JellyfinNotifyService.py`; config read
      fresh from `SystemSettings` on every call (criterion 6).
- [x] 6. Unit tests per criterion 3, 4, 5, 6, 8, 9
      (`Tests/Contract/TestJellyfinNotify.py`, 13 tests including
      fresh-read-per-call and default-port guards)
- [x] 7. Wire into `FileReplacementBusinessService` (`ProcessFileReplacement`
      and `FinalizePartialReplacement` choke points)
- [x] 10. Audit remaining mutation points (see Audit below). Wired
      DuplicateDetectionService; other hits are non-Jellyfin-visible
      (`.inprogress` artifacts, TempDir clips).
- [x] 8. Dry-run validation complete (2026-05-22). Found and fixed XXX
      path mismatch (`/mnt/SynologyXXX/` -> `/mnt/XXX/`); BrainTv and
      SynologyMovies seeds verified correct against Jellyfin's actual
      mounts.
- [x] 9. Live integration verified (2026-05-22). Tested with real
      remuxes ("I Got a Cheat Skill" S01E02, Wednesday S01E07) --
      Jellyfin processed notifies correctly, refreshed parent season
      folder ~60s after 204 ACK, swept stale entries for other episodes
      in the same folder (free bonus cleanup). Re-verified 2026-05-27
      after dry-run removal on Steven Universe S01E37 (status=204).

### Verification (qa-tester, 2026-05-22)

- **Criteria 1-6, 8, 9**: IMPLEMENTED with concrete code/test/DB evidence
  (full report from qa-tester agent attached to commit message of the
  closing commit).
- **Criterion 7 (idempotent under retry)**: asserts Jellyfin server-side
  behavior, not MediaVortex behavior. Our side is stateless: we don't
  dedup, we don't track Jellyfin item IDs. Jellyfin's ~60s coalescing
  window naturally absorbs duplicate notifies for the same path -- and
  this was observed in the live 2026-05-22 burst test (7 notifies for
  the same Season 1 folder coalesced into a single season refresh).
  Live evidence is in this session's Jellyfin scan log, not in the
  repo.

### Audit: file-mutation choke points

Per criterion 1, grep of `shutil.move|os.replace|os.rename|os.unlink|os.remove`
under `Features/` and `Services/` (2026-05-22):

| Site | Disposition |
|---|---|
| `Features/FileReplacement/FileReplacementBusinessService.py` (rename + delete) | NOTIFY -- via `_NotifyJellyfinOfReplacement` after `ProcessFileReplacement` / `FinalizePartialReplacement` success |
| `Features/FileScanning/DuplicateDetectionService.py:96` (duplicate delete) | NOTIFY -- batched `Deleted` updates after each group; only effective on Windows worker where disk paths are canonical (`T:\...`); Linux disk paths fail translation and skip with WARNING |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py:757,1666` | SKIP -- `.inprogress` artifact and partial output cleanup; Jellyfin does not index these filenames |
| `Features/QualityTesting/QualityTestingBusinessService.py:1534` | SKIP -- staged `.inprogress` requeue cleanup |
| `Features/ServiceControl/CrashRecoveryService.py:440` | SKIP -- orphaned `.inprogress` cleanup |
| `Features/ClipBuilder/ClipBuilderBusinessService.py:100,111,116` | SKIP -- VMAF analysis clips in `TempDir` |
| `Services/FileManagerService.py:789` (`ReplaceFile`) | DEAD CODE -- no callers; left alone, out of scope to delete |

## Scope

- `Services/JellyfinNotifyService.py` (new)
- `Features/FileReplacement/FileReplacementBusinessService.py`
- `Features/FileScanning/*` (optional, criterion 1)
- Any future `shutil.move|os.replace|os.rename|os.remove` site under
  `Features/` or `Services/`
- `Core/Path/LocalPath.py + Core/Path/Path.py` — read-only consumer; no changes expected
- `StorageRootResolutions` table — one new logical "worker" added (data,
  not schema)
- `SystemSettings` table — reuses the existing `JellyfinHost`,
  `JellyfinApiPort`, `JellyfinApiKey` rows managed by
  `Features/Optimization`. No push-notify-specific rows.

## Files

- `Services/JellyfinNotifyService.py` (new) -- the notifier
- `Features/FileReplacement/FileReplacementBusinessService.py` --
  primary choke point (`_NotifyJellyfinOfReplacement` helper)
- `Features/FileScanning/DuplicateDetectionService.py` -- secondary
  choke point for duplicate deletions
- `Scripts/SQLScripts/SeedJellyfinResolutions.py` (new) -- idempotent
  seeder for `__jellyfin__` resolutions
- `Scripts/DryRunJellyfinNotify.py` (new) -- operator-run one-shot
  validator; renders translated paths without POSTing
- `Tests/Contract/TestJellyfinNotify.py` (new) -- 13 unit tests
- `jellyfin-push-notify.feature.md` (this doc)
- `CLAUDE.md` -- one-line pointer to the SystemSettings keys

### Commits

- `151c3e5` feat(jellyfin-notify): push library updates on file mutations
- `3530360` docs(jellyfin-notify): scope out the polling-off decision

## Cross-Repo References

- `infrastructure/docs/features/jellyfin-efficiency.md` — the upstream
  bug analysis, push-vs-poll decision, and the arr-stack half of this
  effort. Read its 2026-05-17 PM Decisions entry for the four
  scan-profile data points (20.52 / 8.02 / 18.02 / 18.02 min) that
  motivated this feature.
- Jellyfin issue #15070 — upstream scanner regression (OPEN as of
  2026-05-17, fix deferred to 10.12.x).
- Jellyfin API: `POST /Library/Media/Updated` with header
  `X-Emby-Token: <api-token>` and body
  `{"Updates":[{"Path":"...", "UpdateType":"Modified|Created|Deleted"}]}`.

## Deviation from conventions

None expected. The feature follows:
- Persistence behind a Store seam: N/A — this is an outbound integration,
  no new persistent state in MediaVortex.
- Web-facing observability: N/A — this is an outbound notifier, not an
  HTTP-serving feature.
- Secrets storage: data-driven via `SystemSettings`, not env vars. The
  repo is uniformly data-driven (CLAUDE.md "Key Patterns"); env vars are
  reserved for bootstrap-only values like DB host. Criterion 6 enforces.
- Graceful named exceptions: criterion 4 is the failure contract.
