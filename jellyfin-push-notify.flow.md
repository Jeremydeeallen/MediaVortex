# Flow: Jellyfin Push-Notify on File Mutations

**Slug:** jellyfin-push-notify

Fire-and-forget POST to Jellyfin's `/Library/Media/Updated` endpoint whenever MediaVortex moves, renames, replaces, or deletes a file Jellyfin indexes. Replaces 2h polling with near-real-time refresh per `jellyfin-push-notify.feature.md`.

## Entry Point

`NotifyJellyfin(Updates: list[dict])` -- single dispatch surface. Called from every mutation choke point.

## Stages

| ID | Stage | Code | What It Does |
|---|---|---|---|
| ST1 | Mutation event | Producer call sites (see Seam S1) | Compose `{Path, UpdateType}` per affected file. `UpdateType IN ('Created','Modified','Deleted')`. |
| ST2 | Batch + dispatch | `NotifyJellyfin(Updates)` | Build JSON body `{"Updates": [...]}`. One POST per call (no client-side coalescing). |
| ST3 | POST | HTTP client (timeout 5s) | `POST <JellyfinHost>/Library/Media/Updated` with `X-Emby-Token`. Expect HTTP 204. |
| ST4 | Coalesce window (server-side) | Jellyfin 10.11.x behavior | ~60s coalescing window per directory; same-folder updates batched server-side. Side benefit: stale entries swept. |
| ST5 | Log + return | `LoggingService.LogInfo` / `LogWarning` | Success: one INFO with path count. Failure: one WARN with status + path count. MediaVortex correctness does not depend on the response. |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1` mutation choke points | `FileReplacementBusinessService._ProcessCompleteFileReplacement` (transcode.flow.md::ST9), `FileScanningBusinessService.ReconcileWithDisk` (filescanning.flow.md::ST5), manual operator delete endpoints | One call per mutation batch; `Updates` list shape: `[{"Path": "<absolute path in Jellyfin's index>", "UpdateType": "Created|Modified|Deleted"}]` | `NotifyJellyfin` dispatches once per call | `grep -rn "NotifyJellyfin(" Features/ WebService/ Scripts/` -- every mutation site referenced in `jellyfin-push-notify.feature.md` criterion 1 appears |
| S2 | `ST3` HTTP POST | `NotifyJellyfin` | JSON over HTTPS with auth header; body matches Jellyfin 10.11.x `/Library/Media/Updated` schema | Jellyfin enqueues per-path refresh | Live: `curl -X POST -H "X-Emby-Token: ..." <host>/Library/Media/Updated -d '{"Updates":[{"Path":"...","UpdateType":"Modified"}]}'` -- 204 No Content |
| S3 | `ST4` coalesce -> library refresh | Jellyfin server (external) | ~60s window per directory; `MediaSegmentsScanned` event in Jellyfin logs | Operator observes affected items refresh in UI ~60s after MediaVortex notify | Jellyfin logs: `grep "Library/Media/Updated" /var/log/jellyfin/jellyfin.log` after a MediaVortex mutation |
| S4 | fire-and-forget invariant | this flow | Non-blocking dispatch: caller does NOT await response; failure surfaces as WARN log only | Caller continues its work regardless of Jellyfin reachability | Manual: stop Jellyfin, run a MediaVortex file replacement; replacement completes successfully, single WARN line in `Logs` |

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| Jellyfin unreachable | One WARN per mutation: `Jellyfin notify failed: <error>` | Jellyfin's own 2h scan-media-library safety net catches up |
| HTTP 401/403 (token rotated) | WARN: `Jellyfin notify auth failed` | Operator updates `SystemSettings.JellyfinApiKey`; reads fresh per call (R3) |
| Path Jellyfin doesn't recognize | Jellyfin returns 204 (always); item just doesn't refresh | No-op; next library scan catches it |

## Out of Scope

- Disabling Jellyfin's 2h library scan -- that requires arr-stack notifications too; tracked separately.
- Per-item refresh status feedback -- Jellyfin's API doesn't expose it.
