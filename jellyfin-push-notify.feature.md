# Feature: Jellyfin Push Notifications on File Mutations

> **Status flag for pickup:** READY FOR DESIGN/IMPLEMENTATION. Created by the
> infrastructure repo's jellyfin-efficiency work (see
> `infrastructure/docs/features/jellyfin-efficiency.md`, 2026-05-17 PM Decisions
> entry). MediaVortex side has NOT been touched yet — `/n` step 14 explicitly
> blocks code until criteria are reviewed and approved by the operator.

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

## Concern

After this feature ships AND the arr-stack Connect notify is also enabled,
the infrastructure side will disable the Jellyfin "Scan Media Library"
interval trigger (or reduce it to a once-daily safety net for libraries
neither system mutates — XXX, Workout, custom downloads). Until BOTH push
paths are live, do NOT disable polling.

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
   (`Core/PathStorage.Resolve`) but resolves against a synthetic
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
   missing config (`JELLYFIN_URL` or `JELLYFIN_API_TOKEN` unset) log a
   WARNING via `LoggingService.LogWarning(...)` and return without
   raising. MediaVortex business logic continues regardless of Jellyfin's
   state. Verifiable: stop Jellyfin, run a replace, observe the WARNING
   in the Logs table, confirm MediaVortex did not error out, confirm the
   replace itself committed normally. Restart Jellyfin and confirm the
   next mutation notifies successfully.

5. **Timeout cap.** The HTTP call uses a hard `timeout=5` seconds (connect
   + read). Verifiable: simulate a hung Jellyfin (firewall-drop the
   response port; or point `JELLYFIN_URL` at a sink that accepts
   connections but never responds); confirm the notify returns within
   ~5s with a WARNING, not after default-socket-timeout minutes.

6. **Secrets via env vars only.** `JELLYFIN_URL` and `JELLYFIN_API_TOKEN`
   are read from environment (or whatever config mechanism MediaVortex
   uses today for similar external creds) and never committed to git.
   Verifiable: grep the repo for the token value `8958caee...` returns
   zero hits; `.env.example` (or equivalent) documents both variables.

7. **Idempotent under retry.** If a mutation results in two NotifyJellyfin
   calls for the same path (e.g. caller retries), Jellyfin's behaviour is
   identical — it re-validates the same item twice harmlessly. No
   client-side dedup required. Verifiable: send the same notify twice in
   a row; both return 204, the second is observably a no-op in the
   Jellyfin scan log (item not re-imported, just re-checked).

8. **Optional dry-run mode.** Setting `JELLYFIN_NOTIFY_DRY_RUN=1` logs
   the would-be payload at INFO level instead of POSTing. Lets the
   operator validate the choke-point coverage before going live.
   Verifiable: set the env var, run a replace, confirm a log line of
   shape `[DRY-RUN] Would notify Jellyfin: {Updates:[...]}` and zero
   outbound HTTP.

9. **Observability.** Every notify (real or dry-run) records to the Logs
   table at INFO level with the count of updates and the HTTP status
   code. Failures are WARNING. A `/metrics`-compatible counter is NOT
   required for v1, but the log shape MUST be greppable for later
   metric extraction (e.g. consistent prefix `JellyfinNotify:`).

## Implementation Sketch (non-binding)

- New module: `Services/JellyfinNotifyService.py`
- Public surface: one function
  ```python
  def NotifyJellyfin(Updates: List[Dict[str, str]]) -> None:
      # Updates: [{"Path": "/mnt/movies/x.mkv", "UpdateType": "Modified"}, ...]
  ```
- Path translation: resolve `(StorageRootId, RelativePath)` against the
  synthetic `__jellyfin__` worker via `Core.PathStorage.Resolve`. If no
  resolution exists for a given root, log WARNING and skip that entry
  (don't fail the whole batch).
- HTTP: `requests.post(JELLYFIN_URL + "/Library/Media/Updated",
  headers={"X-Emby-Token": JELLYFIN_API_TOKEN},
  json={"Updates": Updates}, timeout=5)`.
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

**NOT STARTED.** Doc drafted by the infrastructure repo's
jellyfin-efficiency session on 2026-05-17. MediaVortex code has NOT been
touched. Criteria pending operator review per `/n` step 14.

### Progress

- [x] 1. Document the upstream Jellyfin scanner regression on the
      infrastructure side (`infrastructure/docs/features/jellyfin-efficiency.md`)
- [x] 2. Draft this feature doc with criteria + implementation sketch
- [ ] 3. **Operator review + approval of criteria** (gate — no code before this)
- [ ] 4. Seed `__jellyfin__` rows into `StorageRootResolutions` (one per
      Jellyfin-indexed StorageRoot)
- [ ] 5. Implement `Services/JellyfinNotifyService.py` with dry-run support
- [ ] 6. Unit tests per criterion 4, 5, 6, 8
- [ ] 7. Wire into `FileReplacementBusinessService` (highest-value site)
- [ ] 8. Run dry-run for a fleet-day, audit logs for choke-point coverage
- [ ] 9. Flip dry-run off; manual integration tests per Test Plan
- [ ] 10. Audit remaining mutation points (FileScanning reconcile, future
      sites), wire notify in or document why skipped (criterion 1 grep)
- [ ] 11. Coordinate with infrastructure side: once arr-stack Connect is
      also live and notifying, disable the Jellyfin Scan Media Library
      interval trigger (or reduce to once-daily safety net). That flip
      happens in the infrastructure repo, not here, but this feature is
      a prerequisite.

## Scope

- `Services/JellyfinNotifyService.py` (new)
- `Features/FileReplacement/FileReplacementBusinessService.py`
- `Features/FileScanning/*` (optional, criterion 1)
- Any future `shutil.move|os.replace|os.rename|os.remove` site under
  `Features/` or `Services/`
- `Core/PathStorage.py` — read-only consumer; no changes expected
- `StorageRootResolutions` table — one new logical "worker" added (data,
  not schema)
- `.env.example` (or current equivalent) — document `JELLYFIN_URL`,
  `JELLYFIN_API_TOKEN`, `JELLYFIN_NOTIFY_DRY_RUN`

## Files

- `Services/JellyfinNotifyService.py` (new)
- `Features/FileReplacement/FileReplacementBusinessService.py`
- `jellyfin-push-notify.feature.md` (this doc)

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
- Secrets via env vars: criterion 6 honors this explicitly.
- Graceful named exceptions: criterion 4 is the failure contract.
