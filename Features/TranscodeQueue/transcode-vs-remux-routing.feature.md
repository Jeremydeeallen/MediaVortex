# Transcode vs Remux Routing -- compliance-driven pipeline selection

## What It Does

Replaces the "transcode everything that has an assigned profile" pattern
with a compliance-driven model. Every probed MediaFile is evaluated
against an effective profile (resolved via cascade), and the system
records two materialized columns:

| Column | Meaning |
|---|---|
| `MediaFiles.IsCompliant` | True if the file already meets all criteria for the effective profile -- no further work needed. |
| `MediaFiles.RecommendedMode` | When not compliant: which pipeline closes the gap. `'Transcode'` for video re-encode (fixes everything downstream); `'Remux'` for audio normalize + container fix (no video re-encode). |

The cascade for the effective profile is:

```
  ShowSettings.AssignedProfile (per-series override -- NULL = inherit)
  -> SystemSettings.DefaultProfileName (operator-set library default)
```

`MediaFiles.AssignedProfile` is repurposed as a denormalized cache of
the cascade result, populated by recompute hooks. It is no longer a
source of truth -- the cascade is.

The operator interacts with two GUI surfaces:

1. `/settings` page -- pick the global default profile.
2. `/ShowSettings` Media Library card -- pick per-series profile overrides for shows the operator wants kept higher-quality.

Once compliance is materialized, every queue-population path filters on
`IsCompliant IS NOT TRUE`, so compliant files cannot enter the queue.

## Concern

Three operator concerns this feature resolves:

1. **No-benefit transcodes wasted hours.** A 290 MB / 720p / h264 / 935 kbps MKV would be transcoded for ~27 MB of estimated savings, often producing an equal-or-larger output. Workers spent hours for nothing.

2. **`MediaFiles.AssignedProfile` is full of stale legacy values.** The earlier priority-materialization backfill showed all ~58k files used the size*0.5 fallback because `AssignedProfile` strings (e.g. `"LiveActionSmall"`, `"Live action 22 - 25 Grain..."`) don't match any current profile name. Reading from the cascade instead, with a global default the operator sets, gives every file a sensible target without manual cleanup.

3. **Library hygiene drift.** Some MediaVortex outputs were transcoded before audio normalization was wired in, so the library has an inconsistent loudness. Some natively-imported files are MKV, breaking Jellyfin compatibility. Today there is no single signal that says "this file is done." The `IsCompliant` column becomes that signal.

The audio-on-remux fix shipped 2026-05-09 made the Remux pipeline a fully-acceptable alternative to Transcode for files that don't need video re-encoding -- this feature is what routes traffic to it.

## Surface

User-facing -- two GUI surfaces, two columns visible in any operator query, one new SystemSetting. See `transcode.flow.md` Stage 4 (queue-population filter) and Stage 7 (post-flight compliance recompute) for pipeline integration.

## Success Criteria

### A. Effective profile cascade

1. `SystemSettings('DefaultProfileName')` row exists, type string, default `'SVT-AV1 P6 FG8 >480p'` (operator's chosen global default). Seed script `Scripts/SQLScripts/SeedDefaultProfileSetting.py` is idempotent (`INSERT ... ON CONFLICT DO NOTHING`). Verifiable: run the seed, query `SELECT SettingValue FROM SystemSettings WHERE SettingKey = 'DefaultProfileName'`.

2. `ShowSettings.AssignedProfile VARCHAR(100)` column exists, nullable. NULL means "inherit from SystemSettings default." Migration `Scripts/SQLScripts/AddShowSettingsAssignedProfile.py` is idempotent (`ADD COLUMN IF NOT EXISTS`). Verifiable: `\d ShowSettings` shows the column.

3. `_GetEffectiveProfile(MediaFile) -> Optional[str]` helper exists in `QueueManagementBusinessService`. It extracts the show folder from `MediaFile.FilePath` (segment immediately under the drive root, same `Parts[1]` rule the existing client-side ShowName extraction uses), looks up `ShowSettings.AssignedProfile` for that folder; if NULL or no row, returns `SystemSettings('DefaultProfileName')`. Returns NULL only if the SystemSetting itself is unset. Verifiable: insert ShowSettings row with `AssignedProfile='X'` for show `Y`, query a MediaFile in `Y` -- helper returns `'X'`. Delete the ShowSettings row, helper returns the SystemSettings default.

### B. GUI surfaces

4. `/settings` page exposes a "Default Profile" `<select>` populated from the Profiles table. Selected value reflects current `SystemSettings('DefaultProfileName')`. Changing the selection POSTs to a new `/api/SystemSettings/DefaultProfile` endpoint, which validates the chosen name exists in `Profiles.ProfileName` and updates the SystemSetting. Verifiable: change the dropdown, query `SystemSettings`, observe new value. Invalid value (manual API call with non-existent profile name) is rejected with HTTP 400.

5. `/ShowSettings` Media Library card (Card 3) gains a "Profile" column with a per-row `<select>` populated from the Profiles table, plus a NULL/blank option labeled "(use default)". Changing a row's selection POSTs to a new `/api/ShowSettings/SetSeriesProfile` endpoint with `{ShowFolder, ProfileName}` -- ProfileName empty string means clear the override (back to default). Verifiable: pick a show, change its profile to "SVT-AV1 P6 FG2 >720p", reload, dropdown reflects the choice; query `ShowSettings WHERE ShowFolder=...` confirms the column.

6. Both GUI controls validate that the chosen value exists in `Profiles.ProfileName`. Stale or invalid names cannot be saved. Verifiable: server-side validation tested with a curl against the API endpoint.

### C. MediaFiles.AssignedProfile as cache

7. `MediaFiles.AssignedProfile` is no longer a source of truth. It is populated from `_GetEffectiveProfile(MediaFile)` by recompute hooks. Existing readers continue to work without changes (read the column directly), but the column reflects the cascade, not operator-direct input. Verifiable: change `SystemSettings('DefaultProfileName')` from `'A'` to `'B'`; the affected MediaFiles rows update from `'A'` to `'B'` within one recompute cycle (or one bulk admin call).

8. Recompute triggers extend the existing priority-materialization hooks. The same `ComputePriorityScoresForFiles` bulk function is rewritten as `RecomputeForFiles(MediaFileIds)` and computes `AssignedProfile` (from cascade), `PriorityScore`, `IsCompliant`, and `RecommendedMode` in a single pass per row. Triggers:
   - Probe completion (single file)
   - `ShowSettings.AssignedProfile` change (all files in that show)
   - `SystemSettings('DefaultProfileName')` change (all files where ShowSettings.AssignedProfile IS NULL)
   - FileReplacement post-flight (single file -- re-probed file may flip IsCompliant)
   - Admin endpoint (full library or scoped sweep)

9. Migration sets `MediaFiles.AssignedProfile = NULL` for all rows once the SystemSetting and ShowSettings.AssignedProfile column exist. Subsequent recompute hooks repopulate via cascade. Verifiable: post-migration `SELECT COUNT(*) FROM MediaFiles WHERE AssignedProfile IS NULL` = total row count; then run admin recompute, count drops to ~0 (only files with broken inputs stay NULL).

### D. IsCompliant materialization

10. `MediaFiles.IsCompliant BOOLEAN` column exists, nullable. Migration `Scripts/SQLScripts/AddIsCompliantColumn.py` is idempotent. NULL means "compliance not yet evaluated" (e.g. probe missing, effective profile cannot be resolved).

11. `_EvaluateCompliance(MediaFile, EffectiveProfile)` helper returns `(IsCompliant: bool, RecommendedMode: Optional[str])`. The cascade:

    ```
    a. HasExplicitEnglishAudio = false
       -> IsCompliant = NULL, RecommendedMode = NULL
       -> file is hard-blocked from queueing (existing audio-language safety guard)

    b. EffectiveProfile cannot be resolved (SystemSetting missing)
       -> IsCompliant = NULL, RecommendedMode = NULL

    c. Resolution > effective_profile.TranscodeDownTo
       OR video codec NOT IN (h264, hevc, av1)
       OR estimated_savings_mb >= MIN_SAVINGS
       -> IsCompliant = false, RecommendedMode = 'Transcode'
       -- transcode inherently fixes container + audio + video, so the
       -- lighter checks below are not consulted

    d. Container NOT IN CompatibleContainers
       OR audio codec NOT IN (aac, ac3, eac3, mp3)
       OR audio not normalized (see criterion 13)
       -> IsCompliant = false, RecommendedMode = 'Remux'

    e. None of the above
       -> IsCompliant = true, RecommendedMode = NULL
    ```

12. Verifiable per-clause:
    - File with HasExplicitEnglishAudio=false: IsCompliant=NULL.
    - 1080p MKV h264 8000 kbps with effective profile targeting 480p: IsCompliant=false, RecommendedMode='Transcode'.
    - 720p MP4 h264 935 kbps already at-or-below profile target with normalized audio: IsCompliant=true.
    - 720p MKV h264 935 kbps with normalized audio: IsCompliant=false, RecommendedMode='Remux' (container-only fix).
    - 720p MP4 h264 935 kbps with un-normalized audio: IsCompliant=false, RecommendedMode='Remux' (audio-only fix).

13. Audio normalization detection (criterion 11d):
    - For files MediaVortex transcoded (`TranscodeAttempts.FileReplaced=true` for that MediaFileId): a file is considered normalized if and only if the most-recent successful attempt's `FFpmpegCommand` (note: column name has a known double-`p` typo, see `CLAUDE.md`) contains `loudnorm` substring (case-insensitive). Approach validated 2026-05-09 against live data: 2,385 normalized attempts vs 230 un-normalized cleanly partitioned, the 230 clustered on a single day (2026-02-17) when normalization was off.
    - For files NOT in TranscodeAttempts (natively imported): default to NOT normalized. Operator can re-evaluate via the admin endpoint after the file is processed once.
    - No `ebur128` measurement in this feature -- deferred. Cheap-and-correct-enough for MediaVortex outputs is the priority here.
    - Verifiable: insert a test TranscodeAttempts row with `FFpmpegCommand='ffmpeg ... -af loudnorm=I=-23 ...'`, recompute -- file marks as normalized. Replace command without loudnorm, recompute -- marks as un-normalized.

### E. Pre-flight gate at queue creation

14. The four queue-entry sites read `MediaFiles.RecommendedMode` (no recomputation at queue time):
    - `CreateQueueItemFromMediaFileWithProfile` (PopulateQueueFromMediaFiles)
    - `AddSuggestionsToQueue` (SmartPopulate / Card 1)
    - `AddJobToQueue` (Add Job dialog / Card 2 per-row +)
    - `QueueByFolder` (Card 2 bulk)

15. Pre-flight behavior per RecommendedMode:
    - `'Transcode'` -> insert TranscodeQueue row with `ProcessingMode='Transcode'`
    - `'Remux'` -> insert TranscodeQueue row with `ProcessingMode='Remux'`
    - NULL with `IsCompliant=true` -> skip; log "AlreadyCompliant" with MediaFileId
    - NULL with `IsCompliant=NULL` -> skip; log a warning citing the missing input (no English audio, no effective profile, etc.) per the loud-failure rule
    - `IsCompliant=false` with `RecommendedMode=NULL` is a logic error -- log critical, do not queue

### F. Post-flight gate at FileReplacement

16. `FileReplacementBusinessService.ProcessFileReplacementWithVMAF` retains the post-flight gate from the prior no-benefit-handling design but only for `ProcessingMode='Transcode'` rows. For Remux rows, the gate is skipped because remux is by definition not aimed at disk savings -- audio re-encode may produce a marginally larger output, and that's acceptable. Verifiable: a Remux job whose new audio adds 200 KB still replaces; a Transcode job whose new file is equal-or-larger does NOT replace.

17. After successful replacement, the new file is re-probed and `RecomputeForFiles([MediaFileId])` runs. The expected outcome is `IsCompliant=true` -- if the recompute shows `IsCompliant=false`, log a warning naming the criterion that still failed (operator visibility into "transcode/remux didn't fully fix this file"). Verifiable: induce a re-encode that intentionally fails one criterion (e.g. mock a reply where audio still isn't normalized due to a settings flip mid-job), confirm warning logged.

### G. Queue-population filter

18. Every queue-entry path's WHERE clause includes `IsCompliant IS NOT TRUE` via the existing shared helper. Compliant files cannot enter any queue. Verifiable: mark a file `IsCompliant=true` manually, attempt to queue it via every entry path -- all return skipped, no TranscodeQueue row appears.

19. The partial index `idx_mediafiles_smartpopulate` is recreated to include `IsCompliant IS NOT TRUE` in its WHERE so SmartPopulate stays sub-millisecond. Verifiable: `EXPLAIN ANALYZE` shows Index Scan after recreation.

### H. Admin endpoint

20. `POST /api/PriorityMaterialization/Recompute` (existing endpoint from priority-materialization) is extended to also recompute IsCompliant + RecommendedMode + AssignedProfile via the unified `RecomputeForFiles`. Optional body filters: `ProfileName` (only files whose cascade resolves to that profile), `Drive`, `ShowFolder`. With no body, recomputes the whole library. Verifiable: POST with no body on a fresh DB; row count returned matches MediaFiles total; library compliance state stabilises.

### I. Operator visibility

21. The Activity page renders a "Library Compliance" panel at the **bottom of the page** (below the existing panels) showing a one-glance summary:
    - Total MediaFiles count
    - Compliant count + percent
    - Non-compliant by RecommendedMode (Transcode N, Remux N)
    - Undecided count (IsCompliant IS NULL) split by reason (no profile / no English audio / not yet probed)
    Source: cheap GROUP BY query on MediaFiles; no per-poll recompute. Verifiable: visual inspection plus a manual `SELECT IsCompliant, RecommendedMode, COUNT(*) FROM MediaFiles GROUP BY 1, 2` reconciles with the displayed numbers.

22. SmartPopulate response per-row includes `IsCompliant` and `RecommendedMode` fields. Card 1 row template renders a small badge showing the recommended mode (Transcode / Remux), so the operator can see at a glance which pipeline a queued item will hit.

### J. Cleanup and deprecation

23. The legacy `CompliantFiles` table is dropped (migration `Scripts/SQLScripts/DropCompliantFilesTable.py`, idempotent `DROP TABLE IF EXISTS`). 1,451 stale rows last written 2025-09-08, no live readers. The new `MediaFiles.IsCompliant` column supersedes it. Verifiable: `\d CompliantFiles` returns "Did not find any relation" after migration.

24. The `TranscodeQueue.ProcessingMode='Remux'` worker path remains the existing `ProcessRemuxJob` -- no behavior change in the worker, only how items get routed to it.

25. The original `no-benefit-handling.feature.md` filename is renamed via `git mv` to this filename. Doc cross-references in other feature docs / flow docs are updated. Verifiable: `grep -r 'no-benefit-handling'` returns only historical commit messages.

## Status

IN PROGRESS -- operator approved 2026-05-09 (cheap-loudnorm-detection validated; visibility panel placed at bottom of Activity page).

### Progress

- [x] Original `no-benefit-handling.feature.md` drafted and operator-approved 2026-05-09
- [x] Audio-on-remux normalization fix shipped 2026-05-09 (covers feature criterion 24's worker-side prerequisite)
- [x] Pivot to compliance-driven model (this rewrite, 2026-05-09)
- [x] Renamed file: `no-benefit-handling.feature.md` -> `transcode-vs-remux-routing.feature.md` (criterion 25)
- [ ] Operator approves criteria 1-25
- [ ] Migrations: `AddIsCompliantColumn.py`, `AddRecommendedModeColumn.py`, `AddShowSettingsAssignedProfile.py`, `SeedDefaultProfileSetting.py`, `DropCompliantFilesTable.py`
- [ ] `_GetEffectiveProfile` helper (criterion 3)
- [ ] `_EvaluateCompliance` helper (criterion 11)
- [ ] `RecomputeForFiles` -- replaces `ComputePriorityScoresForFiles`, single-pass updater (criterion 8)
- [ ] Recompute hooks: extend probe / ShowSettings.AssignedProfile change / SystemSettings DefaultProfileName change / FileReplacement post-flight
- [x] /settings GUI: Default Profile dropdown + API endpoint (criterion 4) -- live-verified 2026-05-09. Card visible at top of /settings page after Setup -> Settings tab rename + lift out of collapsed Profile Management section.
- [x] /ShowSettings Card 3 GUI: per-row Profile dropdown + API endpoint (criterion 5) -- live-verified 2026-05-09 (per-show overrides save and persist via /api/ShowSettings/SetSeriesProfile).
- [ ] Wipe `MediaFiles.AssignedProfile` to NULL, run admin recompute to repopulate from cascade (criterion 9)
- [ ] Pre-flight gate update at all four queue-entry sites (criteria 14, 15)
- [ ] Post-flight gate Mode-aware split (criterion 16)
- [ ] Queue-population filter `IsCompliant IS NOT TRUE` (criterion 18) + index recreate (criterion 19)
- [ ] Operator visibility widget (criterion 21) + SmartPopulate response shape (criterion 22)
- [ ] Drop legacy `CompliantFiles` table (criterion 23)
- [ ] Live verifies: walk criteria 4, 5, 12 (a-e), 18, 19 on the live DB

NEXT: operator approval to start implementation. Recommended order:

1. Schema + seed migrations (criteria 1, 2, 10, 23 prerequisite)
2. GUI surfaces (criteria 4, 5) -- so the operator can actually pick a default profile and per-show overrides before any compliance evaluation runs against meaningful inputs
3. `_GetEffectiveProfile` + `_EvaluateCompliance` helpers
4. `RecomputeForFiles` unified updater + hook wiring
5. `MediaFiles.AssignedProfile` wipe + admin recompute on the live library to populate IsCompliant + RecommendedMode for all rows
6. Queue-population filter rollout + pre/post-flight gate updates
7. Visibility widget + drop of `CompliantFiles`
8. Live verifies

## Scope

```
Features/TranscodeQueue/transcode-vs-remux-routing.feature.md  -- (THIS FILE, renamed)
Features/TranscodeQueue/QueueManagementBusinessService.py      -- _GetEffectiveProfile, _EvaluateCompliance, RecomputeForFiles
Features/TranscodeQueue/TranscodeQueueController.py            -- AddJob route consumes RecommendedMode
Features/ShowSettings/ShowSettingsController.py                -- new /SetSeriesProfile endpoint, AddToQueue/QueueByFolder consume RecommendedMode
Features/ShowSettings/ShowSettingsRepository.py                -- read/write ShowSettings.AssignedProfile
Features/ShowSettings/Models/ShowSettingModel.py               -- add AssignedProfile field
Features/SystemSettings/SystemSettingsController.py            -- new /DefaultProfile endpoint
Features/MediaProbe/MediaProbeBusinessService.py               -- probe-completion hook calls RecomputeForFiles
Features/Profiles/ProfileRepository.py                         -- bulk-update hook calls RecomputeForFiles
Features/FileReplacement/FileReplacementBusinessService.py     -- post-flight gate Mode-aware + RecomputeForFiles call
Features/PriorityMaterialization/PriorityMaterializationController.py  -- admin endpoint extended
Templates/Settings.html                                         -- Default Profile dropdown
Templates/ShowSettings.html                                     -- Card 3 per-show Profile column
Repositories/DatabaseManager.py                                 -- queue-population WHERE-clause helper updated, partial-index recreate
Scripts/SQLScripts/AddIsCompliantColumn.py                      -- (NEW)
Scripts/SQLScripts/AddRecommendedModeColumn.py                  -- (NEW)
Scripts/SQLScripts/AddShowSettingsAssignedProfile.py            -- (NEW)
Scripts/SQLScripts/SeedDefaultProfileSetting.py                 -- (NEW)
Scripts/SQLScripts/DropCompliantFilesTable.py                   -- (NEW)
Scripts/SQLScripts/AddSmartPopulateIndex.py                     -- (UPDATED, recreate with IsCompliant predicate)
transcode.flow.md                                                -- Stage 4 + Stage 7 sections updated
```

## Files

| File | Role |
|------|------|
| Feature doc (this file) | Contract |
| `Scripts/SQLScripts/AddIsCompliantColumn.py` | Idempotent ADD COLUMN MediaFiles.IsCompliant BOOLEAN |
| `Scripts/SQLScripts/AddRecommendedModeColumn.py` | Idempotent ADD COLUMN MediaFiles.RecommendedMode VARCHAR(16) |
| `Scripts/SQLScripts/AddShowSettingsAssignedProfile.py` | Idempotent ADD COLUMN ShowSettings.AssignedProfile VARCHAR(100) |
| `Scripts/SQLScripts/SeedDefaultProfileSetting.py` | Idempotent INSERT SystemSetting `'DefaultProfileName' = 'SVT-AV1 P6 FG8 >480p'` ON CONFLICT DO NOTHING |
| `Scripts/SQLScripts/DropCompliantFilesTable.py` | Idempotent DROP TABLE IF EXISTS CompliantFiles (criterion 23) |
| `Scripts/SQLScripts/AddSmartPopulateIndex.py` | Updated: drop and recreate `idx_mediafiles_smartpopulate` with `IsCompliant IS NOT TRUE` in WHERE |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | New helpers: `_GetEffectiveProfile`, `_EvaluateCompliance`, `RecomputeForFiles` (replaces `ComputePriorityScoresForFiles`); SmartPopulate / queue-population paths consult RecommendedMode |
| `Features/ShowSettings/ShowSettingsController.py` | New `POST /api/ShowSettings/SetSeriesProfile` endpoint with profile-name validation; AddToQueue/QueueByFolder updated to read RecommendedMode |
| `Features/ShowSettings/ShowSettingsRepository.py` | Read/write `ShowSettings.AssignedProfile` |
| `Features/ShowSettings/Models/ShowSettingModel.py` | Add `AssignedProfile: Optional[str] = None` field |
| `Features/SystemSettings/SystemSettingsController.py` | New `POST /api/SystemSettings/DefaultProfile` endpoint with profile-name validation |
| `Features/MediaProbe/MediaProbeBusinessService.py` | Probe-completion hook now calls `RecomputeForFiles([Id])` (was `ComputePriorityScore`) -- updates all four cached fields in one pass |
| `Features/Profiles/ProfileRepository.py` | Bulk-assign-profile flow updated -- writes ShowSettings.AssignedProfile when scoped to a folder, instead of MediaFiles.AssignedProfile directly. Calls RecomputeForFiles for affected rows. |
| `Features/FileReplacement/FileReplacementBusinessService.py` | Post-flight gate Mode-aware (criterion 16); after successful replacement, calls RecomputeForFiles for the MediaFileId |
| `Features/PriorityMaterialization/PriorityMaterializationController.py` | Admin recompute endpoint accepts new optional `Drive` and `ShowFolder` filters; calls unified RecomputeForFiles |
| `Templates/Settings.html` | "Default Profile" `<select>` populated from Profiles, bound to `/api/SystemSettings/DefaultProfile` |
| `Templates/ShowSettings.html` | Card 3 (Media Library) gains a "Profile" column with `<select>` per row, bound to `/api/ShowSettings/SetSeriesProfile`. Card 1 SmartPopulate row template renders RecommendedMode badge alongside the Priority badge. |
| `Repositories/DatabaseManager.py` | Queue-population WHERE clause helper updated to include `IsCompliant IS NOT TRUE`; partial-index recreate matches |
| `transcode.flow.md` | Stage 4 safety guards updated: `IsCompliant IS NOT TRUE` filter; Stage 7 post-flight gate Mode-aware; Stage 3.5 PRIORITY note adjusted to mention IsCompliant + RecommendedMode now share the same materialization pass |

## Deviation from conventions

`Features/PriorityMaterialization/` admin endpoint dir already exists per the priority-materialization feature; this feature extends it rather than creating a new home for the recompute endpoint. The admin endpoint name retains "PriorityMaterialization" for backward compatibility with any operator scripts -- the feature is broader now (priority + compliance + recommended mode + cached profile) but renaming the URL is not worth the breakage.
