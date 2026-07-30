# Language Worker No-Audio Resolver

**Slug:** language-worker-progress-invariant
**Set:** 2026-07-30
**Status:** Active -- phase: DELIVERING

## Interrupts: deploy-worker-identity-invariants

## Outcome

Files that raise `no_audio_streams` in `LanguageEnrichmentService.EnrichAndStamp` are deleted from disk + DB + the *arr backing (Sonarr for TV, Radarr for Movies), with a search command triggered on the matching episode/movie so a fresh copy is grabbed. LanguageWorker stops looping on audioless files; detection rate resumes across the fleet.

## Background

`EnrichAndStamp` raises `LanguageEnrichmentError('no_audio_streams')` BEFORE `Enrich` writes any row. `_FetchBatch`'s `NOT EXISTS` clause re-selects the audioless MediaFile every 60s. Detection rate flatlined 2026-07-29 22:18 UTC. Other error paths write rows via `Enrich` before raising -- correctly excluded.

## Domain Decisions (locked; operator-owned)

- **D1.** `no_audio_streams` files get deleted (file + DB) and re-requested from the *arr backing that fed them.
- **D2.** No sentinel row + no retry policy. Deletion is terminal for this file version; the regrab pulls a fresh replacement with a new MediaFileId on next scan.
- **D3.** Delete cascade is hard: file on disk, `MediaFiles` row, all child-table rows keyed on MediaFileId.
- **D4.** Both Sonarr (TV) and Radarr (Movies) supported. `StorageRoots.name` discriminates: `media_tv` -> Sonarr, `movies` -> Radarr. Other StorageRoots (e.g. `xxx`) log-warn + delete-without-regrab.

## Non-Goals

- Sentinel-row approach (rejected: files stay logically alive but poisoned; regrab-and-delete is cleaner).
- Automatic retry / blocklist tracking. Fresh MediaFileId on next scan means fresh attempt naturally.
- Migrating `Scripts/ArrRedownloadBadDialogBoost.py` off hardcoded credentials. Preexisting scope.
- Extracting a shared `Core/Arr/` client. YAGNI at two total call sites; extract when third caller appears.

## Acceptance Criteria

C1. Progress invariant: MediaFile deleted after `no_audio_streams`; never re-selected. Test: `TestLanguageWorkerProgressInvariant`.

C2. Triple-delete order: Sonarr/Radarr HTTP -> `os.remove` -> `DeleteMediaFileCascade`. Test: `TestNoAudioResolver` (ordering + child clearance + HTTP shape).

C3. Routing: `StorageRoots.name` = 'media_tv' -> Sonarr, 'movies' -> Radarr, other -> log-warn + delete-no-regrab. Test: `TestNoAudioResolver::TestNoAudioResolverRouting`.

C4. Sole-writer preserved: `DeleteMediaFileCascade` in `MediaFilesRepository`. `TestMediaFilesSoleWriter` untouched.

C5. Fail-loud: `NoAudioResolver.__init__` raises `RuntimeError` on any empty setting. Test: `TestNoAudioResolverEnvFailLoud` (4 branches).

C6. Live smoke on larry: (a) detections/10min > 0; (b) known audioless MediaFileIds absent; (c) `Logs.FunctionName='NoAudioResolver'` INFO entries with `regrab=sonarr-ok:epFileId=X`; (d) Sonarr EpisodeSearch commands issued.

C7. `py -m pytest Tests/Contract/TestNoAudioResolver.py Tests/Contract/TestLanguageWorkerProgressInvariant.py` exits 0.

## Call-Graph Audit

- No parallel flow docs. Mode-branch on StorageRoot.name = data-driven (legit). No new shared columns. Preexisting hardcoded creds in `Scripts/ArrRedownloadBadDialogBoost.py` = OOS category (b). No config toggle changes graph shape.

## Files

| File | Change |
|---|---|
See Promotions + Delivery Report.

## Seams Enumerated

Promoted -- see `Features/AudioNormalization/audio-language-detection.feature.md` Seams table S6+S7.

## Promotions

| Source (directive) | Target |
|---|---|
| C9 no-audio resolution invariant | `Features/AudioNormalization/audio-language-detection.feature.md` Success Criteria |
| Seam row: LanguageWorker -> NoAudioResolver | `Features/AudioNormalization/audio-language-detection.feature.md` Seams table |

## Progress

- [x] NEEDS_STANDARDS_REVIEW: rules loaded via CLAUDE.md; standards/index.md read; call-graph audit shows no downstream assumes MediaFileId persistence
- [x] NEEDS_PLAN: criteria + Files approved
- [x] NEEDS_DOC_PREREAD: `audio-language-detection.feature.md`, `mediafiles-uniqueness-owner.feature.md`, `WorkerService.feature.md`, `LanguageWorker.py`, `LanguageEnrichmentService.py`, `MediaFilesRepository.py` read
- [x] IMPLEMENTING: `NoAudioResolver` + `DeleteMediaFileCascade` + LanguageWorker `_ResolveNoAudio` wire; migration `AddNoAudioResolverSettings_2026_07_30.py` + creds seeded
- [x] IMPLEMENTING: `TestNoAudioResolver.py` (10) + `TestLanguageWorkerProgressInvariant.py` (3) = 13/13 green
- [x] VERIFYING: contract tests 13/13; deploy larry-worker-2/3/4 (worker-1 blocked by unrelated ffmpeg tag drift, unpaused on old code); live smoke -- 86 detections + 50 NoAudioResolver INFO events in 10 min post-deploy; 10/10 audioless MediaFileIds gone
- [x] DELIVERING: C9 + seams S6+S7 promoted into `audio-language-detection.feature.md`

## Delivery Report

DIRECTIVE: LanguageWorker infinite loop on `no_audio_streams` files -- delete + regrab via Sonarr/Radarr, cascade DB + disk.

STATUS: Done.

WHAT SHIPPED:
- `Features/AudioNormalization/Services/NoAudioResolver.py` -- StorageRoots-routed Sonarr/Radarr regrab, disk remove, DB cascade. Reads creds from `SystemSettings.{Sonarr,Radarr}{Url,ApiKey}` fail-loud at init.
- `Features/MediaFiles/MediaFilesRepository.DeleteMediaFileCascade` -- single-tx delete of TranscodeAttempts children (QualityTestResults / QualityTestingQueue / MediaFilesArchive) + TranscodeAttempts + TranscodeFiles + FailureBudgetResets + ActiveJobs + MediaFiles. Sole-writer invariant preserved.
- `WorkerService/LanguageWorker._ResolveNoAudio` -- routes `Reason='no_audio_streams'` to lazy-instantiated resolver; other reasons keep existing LogWarning path.
- `Scripts/SQLScripts/AddNoAudioResolverSettings_2026_07_30.py` -- idempotent migration adding SonarrUrl/SonarrApiKey/RadarrUrl/RadarrApiKey to SystemSettings.
- `Tests/Contract/TestNoAudioResolver.py` (10) + `Tests/Contract/TestLanguageWorkerProgressInvariant.py` (3) = 13 tests.

HOW TO USE: nothing operator-facing. Whisper picks up any audioless file, resolver drops + re-requests it from the correct *arr; next scan re-ingests the fresh download.

WHAT YOU NEED TO EXECUTE:
- Optional: retry larry-worker-1 redeploy after ffmpeg tag drift fixed (separate scope). Currently Online on 5031f2f6; other three larry workers on 438857a7 with new code.

CRITERIA VERIFICATION:
- C1: contract test `test_no_audio_streams_routes_to_resolver` PASS. Live: 10/10 known audioless MediaFileIds absent post-run.
- C2: `test_regrab_then_disk_delete_then_db_cascade` + `test_sonarr_flow_calls_delete_and_search` + `test_radarr_flow_calls_delete_and_search` PASS.
- C3: `test_media_tv_routes_to_sonarr` + `test_movies_routes_to_radarr` + `test_other_root_skips_arr_but_still_deletes` PASS.
- C4: sole-writer preserved -- new cascade lives in `MediaFilesRepository`, `TestMediaFilesSoleWriter` untouched.
- C5: 4x `test_missing_*_raises` PASS.
- C6: live on larry post-deploy 2026-07-30 -- 86 detections + 50 resolver INFO events / 10 min, Logs show `regrab=sonarr-ok:epFileId=X,episodeId=Y`.
- C7: `py -m pytest Tests/Contract/TestNoAudioResolver.py Tests/Contract/TestLanguageWorkerProgressInvariant.py` -> 13 passed.

DECISIONS I MADE:
- Placement: `NoAudioResolver` colocated with audio-language-detection vertical, not `Core/Arr/` (YAGNI: 2 callers).
- Credential storage: `SystemSettings` (per R4); GUI-editable via existing /settings.
- Movie/TV route: `StorageRoots.name` ('media_tv' / 'movies'); other names skip *arr + still delete.
- Cascade shape: explicit DELETE per child table in a single tx; MediaFileLanguageDetections / ProblemFiles / TranscodeQueue auto-cascade via existing FKs; TranscodeAttempts + TranscodeFiles (SET NULL) get explicit DELETE + polymorphic ActiveJobs scoped to LanguageService/TranscodeService/QualityTestService.

KNOWN GAPS / DEFERRED:
- larry-worker-1 unpaused on old code because ffmpeg release tag 404's from GitHub; blocking rebuild there. Separate directive scope (ffmpeg-tag drift). Fleet unblocked because 3/4 larry workers on new code + I9/dot/wakko unaffected.
- Preexisting `TestClaimAuthority::test_nvenc_profile_not_capable_worker_refused` failure, unrelated to this directive (touches claim routing not language-detect).
