# Flow: Audio Fix Priority Hints

**Slug:** audio-fix-priority-hints

Folder-pinning -> reprioritize -> claim-order pipeline introduced by `media-tabs-and-loudness.feature.md`. Operator pins a folder on the Audio Fix tab; existing matching rows rise to the top of the claim queue, and future cascade-routed rows for that folder also land at the top.

## Entry Point

Audio Fix tab on `/TranscodeQueue` -- folder input + "Prioritize folder" button. Backend: `POST /api/TranscodeQueue/AudioFix/PinFolder` (controller routes to `QueueManagementBusinessService.PinAudioFixFolder`).

## Stages

| ID | Stage | Code | What It Does |
|---|---|---|---|
| ST1 | UI pin | `Templates/Queue.html` Audio Fix tab | Operator enters folder path / picks from suggestion list; clicks Prioritize. |
| ST2 | API receive | `TranscodeQueueController.PinAudioFixFolder` | Body: `{FolderPath: str, BoostBy: int = 1000}`. Validates non-empty, no path-shape mangling (R6 -- treat as opaque string match against `MediaFiles.FilePath LIKE EscapeLikePattern(FolderPath) || '%'`). |
| ST3 | Persist hint | `AudioFixPriorityHintsRepository.Upsert(FolderPath, BoostBy)` | `INSERT INTO AudioFixPriorityHints (FolderPath, BoostBy, CreatedAt) VALUES (...) ON CONFLICT (FolderPath) DO UPDATE SET BoostBy=EXCLUDED.BoostBy, UpdatedAt=NOW()`. Idempotent. |
| ST4 | Bump existing rows | `_ApplyHintToExistingQueueRows(FolderPath, BoostBy)` | `UPDATE TranscodeQueue SET Priority = Priority + %s WHERE ProcessingMode='AudioFix' AND FilePath LIKE %s ESCAPE '!' AND Status='Pending'`. Bounded write, single SQL statement. |
| ST5 | Future cascade entries | `QueueManagementBusinessService._ComputeInitialPriority(MediaFile)` | Reads `AudioFixPriorityHints` fresh per call. If any hint folder is a prefix of the file's `FilePath`, add BoostBy to the computed priority before insert. |
| ST6 | Worker claims | `ClaimNextPendingTranscodeJob` (`transcode.flow.md::S1`) | The hint's `BoostedPriority` is in the 195-200 override window, so boosted rows surface ahead of size-ordered rows per the claim contract owned by `queue-priority.feature.md`. |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST3` persistent hint | `AudioFixPriorityHintsRepository.Upsert` | `AudioFixPriorityHints.(Id BIGSERIAL PK, FolderPath TEXT UNIQUE NOT NULL, BoostBy INT NOT NULL DEFAULT 1000, CreatedAt TIMESTAMP DEFAULT NOW(), UpdatedAt TIMESTAMP)` -- idempotent UPSERT | `_ComputeInitialPriority` reads on every queue admission; `_ApplyHintToExistingQueueRows` reads on each pin event | `\d AudioFixPriorityHints` shows schema after migration; `SELECT FolderPath, BoostBy FROM AudioFixPriorityHints` returns operator's pins |
| S2 | `ST4` existing-row bump | Single UPDATE statement | `TranscodeQueue.Priority` increments by `BoostBy` for matching `(ProcessingMode='AudioFix', FilePath LIKE prefix, Status='Pending')` rows | Workers re-read Priority on next claim (no in-flight job impact) | After pin: `SELECT Priority FROM TranscodeQueue WHERE FilePath LIKE 'T:\\Westworld%' AND ProcessingMode='AudioFix'` -- all boosted |
| S3 | `ST5` cascade integration | `QueueManagementBusinessService._EvaluateCompliance` + insert paths | New AudioFix queue rows for a pinned folder land with `Priority = BoostedPriority` in `[195, 200]` (`AudioFixPriorityHintsController` enforces the range) | Workers claim override-window rows first per `queue-priority.feature.md` claim contract | Add a new file in a pinned folder, populate queue, observe inserted row's Priority in `[195, 200]` |
| S4 | `ST2` path-shape guard | `PinAudioFixFolder` validates FolderPath | No `.replace().split()` on the FolderPath; LIKE escape via `EscapeLikePattern` (R9) | Folders with special chars (`!`, `%`, `_`) match literally | `EscapeLikePattern("T:\Show!Special\")` produces escaped literal; SELECT confirms only the intended rows match |
| S5 | UI feedback loop | Pin endpoint returns count | `{Success, MatchedRowCount, FolderPath}` -- operator sees how many queue rows were boosted | UI toast shows count | Network panel: response shape matches contract |

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| Operator pins a folder that has no matching rows | UPSERT writes hint; ST4 UPDATE matches 0 rows; response `MatchedRowCount=0` | Hint still applies to future cascade entries (ST5). Operator sees the count and decides. |
| Two operators pin overlapping folders | Both hints persist; cascade adds BoostBy for every matching hint | By design -- nested boost is operator-intended |
| `FolderPath` contains a `!` escape char already | `EscapeLikePattern` re-escapes correctly | Confirmed in `Core.Database.DatabaseService.EscapeLikePattern` test |
| Hint outlives the files it covers | Stale rows in `AudioFixPriorityHints` | One-shot cleanup script can `DELETE FROM AudioFixPriorityHints WHERE NOT EXISTS (SELECT 1 FROM MediaFiles WHERE FilePath LIKE FolderPath || '%')`. Not auto-purged (operator policy). |

## Out of Scope

- Per-file priority overrides -- this flow is folder-scoped only.
- UI for editing existing hints -- operator deletes via SQL (`DELETE FROM AudioFixPriorityHints WHERE FolderPath=...`) until a /settings card is added.
- Cross-mode priority effects -- hints only affect `ProcessingMode='AudioFix'` rows.
