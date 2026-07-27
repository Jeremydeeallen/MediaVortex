# Audio Language Detection

**Slug:** audio-language-detection
**Set:** 2026-07-27 (post-rollback replan; parent stack: deploy-worker-identity-invariants)
**Status:** Active -- phase: IMPLEMENTING

## Outcome

Standalone per-worker background service detects the audio-language of MediaFiles whose `AudioLanguages` is NULL or `und`, records the Whisper result in `MediaFiles.AudioStreamLanguageDetectionsJson`, and -- when the detection is English with sufficient confidence -- stamps the container language tag via `ffmpeg -c copy`, atomic-replaces the file, and refreshes `MediaFiles.AudioLanguages` via re-probe. Runs fleet-wide, opt-in per worker. Isolated from AudioVertical / compliance / transcode queue / audio-fix pipeline.

## Domain Decisions (locked; operator-owned)

Ordered scope-first, behavior next, rollout last.

### Scope + principles
- **D1.** Whisper works on ALL workers (fleet-wide). Idempotent. Follows KISS, DDD, DRY, SOLID.
- **D2.** All state in the DB. No in-memory or file-based caches. `.claude/rules/db-is-authority.md` applies.

### Behavior
- **D3.** Per-file flow: whisper detect -> write result to DB -> if English + confident, stamp container language tag + refresh `MediaFiles.AudioLanguages` via re-probe -> next file.
- **D4.** One shot per file. `MediaFiles.AudioStreamLanguageDetectionsJson IS NOT NULL` is the "tried" marker. Never auto-retried. Operator clears the row to retry.
- **D5.** English + sufficient confidence -> stamp container so the audio system picks it up.
- **D6.** Language detection touches ONLY its own DB columns and the container file. NO interaction with AudioVertical / compliance recompute / transcode queue / WorkBucket / audio-fix.

### Operator surface
- **D7.** `/Activity` shows a minimal presence indicator (File / Worker / Elapsed) when language work is running. Just proof it works.

### Rollout
- **D8.** `Workers.LanguageEnabled` defaults FALSE on every worker. Operator flips per host explicitly.
- **D9.** Larry is the first deploy target. Canary before fleet-wide.

## Non-Goals (explicit)

- No allowlist of acceptable languages for compliance. (Prior attempt's misfeature.)
- No auto re-bucket of Compliant files based on detected language.
- No integration with `AudioComplianceRules` PUT or `_SpawnAudioBackfill`.
- No new UI on `/Compliance` or `/AudioNormalization`.
- No `LanguageFailureReason` column. Detection row presence alone signals "tried".
- No `MetadataOnly` `ProcessingMode`. Standalone worker, not a queue mode.

## Acceptance Criteria

C1. **Thread-safe backend selection.** Backend construction resolves to the working backend regardless of which thread constructs it. Contract test constructs on unbound thread + on bound thread; both return non-stub backend for fleet-shape ffmpeg env.

C2. **One backend across fleet.** `faster-whisper` runs on every host including I9. `WhisperFfmpegBackend` retired. Verifiable: `grep -rn WhisperFfmpegBackend Features/ WorkerService/ Tests/` returns 0 post-implementation; import raises ImportError.

C3. **One shot per file.** Worker query: `WHERE AudioStreamLanguageDetectionsJson IS NULL AND <capability gate>`. Files with existing detection row are never re-processed. Contract test asserts.

C4. **Stamp-on-English.** When detected language in {`en`, `eng`} AND confidence >= `SystemSettings.MinDetectionConfidence` (default 0.85, read fresh per attempt), worker runs `ffmpeg -c copy -metadata:s:a:N language=eng`, atomic-replaces file via `os.replace`, calls `MediaProbeBusinessService.ProbeFile(Force=True)` which refreshes `MediaFiles.AudioLanguages`. Below threshold OR non-English: detection row written, file untouched. Contract test covers all three branches.

C5. **Isolation.** `WorkerService/LanguageWorker.py` and any new `Features/AudioNormalization/` code introduced for this directive import ZERO of: `AudioVertical`, `AudioPolicyAdmissionGate`, `_SpawnAudioBackfill`, `QueueManagementBusinessService`, `WorkBucket`, `AudioComplianceRules*`. Verifiable via `Tests/Contract/TestLanguageDetectionIsolation.py` grep.

C6. **Activity ActiveJobs lifecycle.** Worker inserts an `ActiveJobs` row (`ServiceName='LanguageService'`, `JobType='Language'`, `QueueId=MediaFileId`) on `_ProcessOne` entry and deletes it in the `finally` block (success + failure paths). Uses direct `INSERT ... RETURNING Id` (not `ActiveJobRepository.CreateActiveJob` -- that helper's `LastInsertId` returned 0 in prior work).

C7. **Activity UI.** `Templates/Activity.html` renders `#ActiveLangBody` table (columns: File / Worker / Elapsed) when `Data.ActiveLanguageJobs` non-empty; empty-state message otherwise. `/api/Activity/Snapshot` returns the list. Live-verified via ui-verify.

C8. **LanguageEnabled default FALSE.** Migration adds `Workers.LanguageEnabled BOOLEAN NOT NULL DEFAULT FALSE`. New Workers rows auto-registered pick up FALSE. `SELECT LanguageEnabled FROM Workers WHERE Enabled=TRUE` returns FALSE for every row post-migration.

C9. **Canary shape enforced.** No fleet-wide `LanguageEnabled=TRUE` before:
- (a) I9 processes 3 real English files successfully: detection row + `AudioLanguages='eng'` + container tag changed.
- (b) larry-worker-1 alone processes 20 files over 10 minutes with zero stub-shape detections (all rows carry real confidence > 0 with a language code that isn't the sentinel).

Canary log recorded in this doc's Verification section before promotion.

C10. **Rollback documented before phase A.** This directive contains a `## Rollback` section listing exact SQL + git SHA before any code lands. Verified below.

C11. **DOMAIN.md carries the architectural-principles decision.** New Meta entry dated 2026-07-27 records the KISS/DDD/DRY/SOLID mandate + four-question test. Serves as the framework this directive uses to justify JSONB-vs-normalize choice for `AudioStreamLanguageDetectionsJson` (or its normalized successor). Verifiable: `grep "Architectural principles" DOMAIN.md` returns one hit.

## Contract tests (written FIRST, all failing before implementation)

| File | Criterion |
|---|---|
| `Tests/Contract/TestBackendSelectionThreadSafe.py` | C1 |
| `Tests/Contract/TestFasterWhisperBackend.py` | C2 functional |
| `Tests/Contract/TestLanguageWorkerOneShot.py` | C3 |
| `Tests/Contract/TestLanguageWorkerStamp.py` | C4 (3 branches) |
| `Tests/Contract/TestLanguageDetectionIsolation.py` | C5 (grep-based) |
| `Tests/Contract/TestLanguageWorkerActiveJobs.py` | C6 lifecycle |
| `Tests/Contract/TestLanguageEnabledDefault.py` | C8 |
| `Tests/Contract/TestNoWhisperFfmpegBackend.py` | C2 removal |

## Files (planned)

| File | Role |
|---|---|
| `Scripts/SQLScripts/AddLanguageDetectionColumns_2026_07_27.py` | NEW: migration -- Workers.LanguageEnabled + SystemSettings.MinDetectionConfidence; idempotent (IF NOT EXISTS, ON CONFLICT DO NOTHING). |
| `Features/AudioNormalization/Services/FasterWhisperBackend.py` | NEW: pip-native detection backend (CTranslate2). Single Detect(LocalFilePath, StreamIndex, DurationSeconds) contract. |
| `Features/AudioNormalization/Services/LanguageEnrichmentService.py` | EDIT: retire WhisperFfmpegBackend, use only FasterWhisperBackend. Add EnrichAndStamp(MediaFileId, LocalFilePath). Backend construction remains here but is invoked LAZILY from LanguageWorker. |
| `Features/AudioNormalization/Services/WhisperFfmpegBackend.py` | DELETE per C2 |
| `Features/AudioNormalization/Services/LanguageEnrichmentError.py` | NEW: single typed exception (Reason string) |
| `WorkerService/LanguageWorker.py` | NEW: poll loop + _ProcessOne + ActiveJobs lifecycle. Service constructed inside _MainLoop AFTER WorkerContext.Bind. |
| `WorkerService/Main.py` | EDIT: register capability, LoadCapabilitiesFromDB includes LanguageEnabled, _ApplyCapabilities starts/stops LanguageWorker. |
| `Core/Database/WorkerCapabilityPredicate.py` | EDIT: whitelist 'LanguageEnabled' |
| `Features/TeamStatus/TeamStatusRepository.py` | EDIT: CAPABILITY_COLUMNS + Overview SELECT |
| `Features/TeamStatus/TeamStatusController.py` | EDIT: emit LanguageEnabled in Overview + Capability responses |
| `Features/Admin/Workers/AdminWorkersRepository.py` | EDIT: GetTiles SELECT includes LanguageEnabled |
| `Templates/AdminWorkers.html` | EDIT: CapToggle('LanguageEnabled', 'Language', W.LanguageEnabled) row |
| `Features/Activity/Models/DashboardSnapshot.py` | EDIT: ActiveLanguageJobs field |
| `Features/Activity/Services/DashboardSnapshotService.py` | EDIT: _BuildActiveLanguageJobs() |
| `Features/Activity/ActivityController.py` | EDIT: Snapshot + Stream emit ActiveLanguageJobs |
| `Templates/Activity.html` | EDIT: Active Language Detections table (File / Worker / Elapsed) |
| `requirements.txt` | EDIT: `faster-whisper>=1.0.0` |
| `DOMAIN.md` | EDIT: append 2026-07-27 architectural-principles entry (C11). |
| `Features/AudioNormalization/audio-language-detection.feature.md` | NEW at DELIVERING (colocated feature doc; Promotions from directive) |
| `Tests/Contract/Test*` | 8 files per contract-tests table above |

## Phases

Each phase ends with a stop-and-verify gate. No phase starts without operator ack of prior gate.

| Phase | Work | Exit gate |
|---|---|---|
| A | Rollback plan verified locally; contract tests written (all failing). | 8/8 tests exist + fail as expected. Rollback tested via `git reset --hard 8d672612` on scratch worktree. |
| B | Migration applied on live DB; idempotent second run is a no-op. | `SELECT LanguageEnabled FROM Workers` returns FALSE for every row; `MinDetectionConfidence` row present with value '0.85'. |
| C | `FasterWhisperBackend` + `LanguageEnrichmentError` + edits to `LanguageEnrichmentService` (lazy backend init). WhisperFfmpegBackend deleted. Contract tests C1, C2 (both), C4 pass. | Manual invoke on 1 English file on I9: detection row + container stamp + `AudioLanguages='eng'`. |
| D | `LanguageWorker` + `WorkerService/Main.py` wire-in + `WorkerCapabilityPredicate` whitelist + `TeamStatusRepository` + `TeamStatusController` + `AdminWorkersRepository` + `Templates/AdminWorkers.html`. Contract tests C3, C5, C6, C8 pass. | I9 WorkerService restarted; `LanguageEnabled=TRUE` on I9 alone; 3 real English files processed successfully; ActiveJobs row created + deleted per file. |
| E | `DashboardSnapshot` + `DashboardSnapshotService` + `ActivityController` + `Templates/Activity.html`. Contract test C7 passes. | `/api/Activity/Snapshot` returns `ActiveLanguageJobs` list; `/Activity` renders the table; ui-verify green. |
| F | Fleet deploy via `deploy/deploy-fleet.py` (picks up requirements.txt + code). No capability flips. | All 13 workers on new HEAD SHA; heartbeats fresh; `Workers.LanguageEnabled=FALSE` on every row. |
| G | Larry-worker-1 canary: `Status=Online`, `LanguageEnabled=TRUE`. 10-min soak. Rest of larry stay Paused. | 20 files processed; every detection row carries real confidence > 0 with a language code; no stub-shape entries; ActiveJobs rows clean up. |
| H | Rest of larry + dot + wakko-worker-1 promoted. | Same soak criteria per host. |
| I | Feature doc promoted from directive `## Promotions` -> `Features/AudioNormalization/audio-language-detection.feature.md`. Directive close. | Feature doc committed; directive moves to `.claude/directives/closed/`. |

## Rollback (verified 2026-07-27 pre-phase-A)

If anything breaks:

```sql
UPDATE Workers SET Status='Paused', LanguageEnabled=FALSE WHERE Enabled=TRUE;
ALTER TABLE Workers DROP COLUMN IF EXISTS LanguageEnabled;
DELETE FROM SystemSettings WHERE SettingKey='MinDetectionConfidence';
```

```bash
git reset --hard 8d672612    # pre-directive HEAD
git push --force origin main
py deploy/deploy-fleet.py --skip-local
```

Then Online workers to prior states.

## Call-Graph Audit

_(populated during NEEDS_STANDARDS_REVIEW -- 5 signals per `.claude/rules/call-graph-audit.md`)_

## Verification

_(populated at each phase gate)_

## Promotions

_(populated at DELIVERING -- move durable content from this directive to `audio-language-detection.feature.md`)_
