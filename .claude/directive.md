# Current Directive

**Set:** 2026-11-25
**Status:** Active -- phase: IMPLEMENTING
**Slug:** xxx-video-tier
**Replaces:** `directives/closed/2026-11-25-profile-row-lookup.md` (closed Success)

## Outcome

The xxx library is a tiered library like TV and Movies: every xxx file carries the Tier 3 Better profile, so a 4K source is judged against and encoded at the Tier 3 live-action 2160p row (2160p @ 8000 kbps AV1). Saving a library's default tier on `/settings` re-assigns that library's files whether or not the library has a genre source (today TV and xxx never move, although the page says they do), and the save offers a "replace per-file and per-series overrides" checkbox so the 2,757 xxx files pinned to Tier 1 Efficient by the old plan can be moved in one action. TV and Movies profile assignments are unchanged.

Unit 2 of the xxx program (`Docs/superpowers/specs/2026-10-28-xxx-stash-cull-audio-design.md`); plan Phase 4 in `Docs/superpowers/plans/2026-10-29-xxx-program.md`.

## Acceptance Criteria

1. Saving a library's default tier re-assigns files in any library that has a default tier, with or without a genre source. Verify: contract test runs `ReassignTierProfiles` for a genre-less library fixture and asserts the tier profile is written; the reassign query no longer filters on the library's genre source (`grep -n "GenreSource IS NOT NULL" Features/ContentClassifier/ContentClassifierService.py` returns 0).
2. Override handling is a parameter with a safe default. `ReassignTierProfiles(Ids)` leaves `operator`, `series`, `root_folder` and `manual_sql` sourced files untouched; `ReassignTierProfiles(Ids, IncludeOverrides=True)` moves them to the tier profile with source `library_default_tier` / `genre_tier`. Verify: contract test asserts both predicates from the SQL and the written source.
3. The library-tier save on `/settings` carries the choice. `PUT /api/SystemSettings/LibraryTiers` accepts `ReplaceOverrides` (boolean, default false) and passes it through to the background recompute; the library row has a checkbox "replace per-file and per-series overrides", unchecked on load. Verify: PUT with `ReplaceOverrides: true` returns `Success=true`; `grep -n ReplaceOverrides Templates/Settings.html Features/SystemSettings/SystemSettingsController.py` names the checkbox, the request body and the pass-through; the GET response and page load show the box unchecked.
4. After the operator saves xxx = Tier 3 with the box ticked and deletes rule `XxxPinTier2Good`: `SELECT COUNT(*) FROM MediaFiles WHERE StorageRootId=3 AND AssignedProfile IS DISTINCT FROM 'AV1 Tier 3 Better'` returns 0 (today 3,885 + 52 unprofiled), and `SELECT COUNT(*) FROM ContentClassificationRules WHERE FolderPathPattern LIKE 'X:%'` returns 0.
5. Live: one xxx 4K file above the Tier 3 2160p ceiling is admitted on the farm server without `ForceAdd`, transcodes on a worker to 2160p AV1 at about 8 Mbps (`-b:v 8000k` in the attempt command), attempt `Success=TRUE`, VMAF at or above the gate, and the file is replaced. Source and output sizes recorded.
6. An xxx 4K file at or below the Tier 3 2160p ceiling is not queued: `VideoCompliant=TRUE` with a reason naming `tier=3`; one such file run through `AddJob` without `ForceAdd` is refused.
7. TV and Movies assignments are unchanged. Baseline 2026-11-25: TV (StorageRootId 1) `AV1 Tier 1 Efficient` 49,423 / `AV1 Tier 2 Good` 17; Movies (StorageRootId 2) `AV1 Tier 1 Efficient` 3,486. Same counts after the xxx save and rule delete.
8. Docs say what the code does: `classifier.feature.md` C9 covers any tiered library plus the override-replace choice, with an evidence line; `video-encoding.feature.md` no longer carries the "library with no default tier (XXX)" debt note; no doc says a library without a genre source skips reassign. Verify: `grep -rn "GenreSource" --include=*.md Features/ | grep -i reassign` returns 0; `grep -n "no default tier (XXX)" Features/VideoEncoding/video-encoding.feature.md` returns 0.

## Call-Graph Audit

- **Signal 1 (flow docs):** no flow doc added or split. Touched stages: `ingest.flow.md` ST5/ST6 (classifier assigns profile), `transcode.flow.md` ST4 (admission reads the Tier 3 row via `GetProfileRow`, unchanged by this directive). One conceptual operation, one flow each.
- **Signal 2 (orchestration mode branch):** `ContentClassifierService.ReassignTierProfiles` predicate `sr.GenreSource IS NOT NULL` is a library-kind branch inside the reassign path: genre-sourced libraries reassign, others silently do nothing. Absorbed: predicate deleted; the only gate is "library has a default tier", which `FileTierResolver.Resolve` already answers (returns None when `DefaultQualityTier IS NULL`). `UpdateGenreTier` -> `ListGenreSourcedLibraryIds` stays: a genre's tier can only change files that have genres, so recomputing genre-sourced libraries only is correct scoping, not a branch.
- **Signal 3 (sparse columns):** `MediaFiles.AssignedProfileSource` on xxx today: `operator` 2,101, `series` 656, `classifier` 1,346, NULL 40 (profile set, source missing), `classifier_skip_av1` 2, `bulk-tier2-already-transcoded-2026-07-21` 3, unprofiled 50. After the save every xxx row is `library_default_tier`. No new column.
- **Signal 5 (config drives graph shape):** today `StorageRoots.GenreSource` NULL removes the reassign node for a whole library; after this directive the same functions run for every tiered library and `GenreSource` only changes which tier comes back (already the stated design in `video-encoding.feature.md` "Genre is data, not a code path"). Pre-existing, named as debt (b) below: `DefaultQualityTier IS NULL` still selects the profile-and-codec compliance path; after this directive no library has a NULL tier, so that path is dead by data, not by code.
- **Domain gap found at audit (escalated, see Escalation Defaults):** `VideoComplianceThresholds` 2160p multiplier is 3.00, so the Tier 3 2160p ceiling is 24,000 kbps. xxx 4K by source bitrate: >24,000: 545 files (4.7 TB); 16,001-24,000: 517 (3.1 TB); 12,001-16,000: 451 (1.8 TB); 8,001-12,000: 171 (0.4 TB); <=8,000: 88. Under 3.00 only the 545 ever queue; the spec assumed everything above ~10 Mbps queues (1,619 files). Movies has 0 2160p files and TV has 1 (9,735 kbps, non-compliant under any multiplier from 1.0 to 3.0), so the 2160p multiplier is effectively an xxx-only knob today.
- **Seams the directive adds or changes:**

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| Settings.html row -> PUT `/api/SystemSettings/LibraryTiers` | `SaveLibraryTier` | JSON `{StorageRootId:int, DefaultQualityTier:int|null, DefaultContentClass:str|null, ReplaceOverrides:bool}` | `UpdateLibraryTier` reads `ReplaceOverrides` as bool, default false when absent | PUT round trip (criterion 3) |
| `UpdateLibraryTier` -> `_SpawnLibraryRecompute(StorageRootId, IncludeOverrides)` | controller | positional int + bool | thread passes bool to `ReassignTierProfiles` | contract test on call args |
| `ReassignTierProfiles(Ids, IncludeOverrides)` -> SQL | service | `WHERE mf.Id = ANY(%s)` + optional `AND COALESCE(mf.AssignedProfileSource,'') <> ALL(%s)` | rows of every tiered library; override rows only when `IncludeOverrides` | contract test (criteria 1, 2) |
| `ReassignTierProfiles` -> `ProfileAssignmentService.Assign(Group, ProfileName, Source)` | service | existing; source `library_default_tier` for genre-less libraries | `MediaFiles.AssignedProfile/Source` written, cascade to `RecomputeForFiles` | existing `TestProfileAssignmentServiceCascade`; criterion 4 count |

## Out of Scope

- (b) KNOWN ARCHITECTURAL DEBT: `VideoVertical` still has the profile-and-codec path for a library with `DefaultQualityTier IS NULL` (call-graph Signal 5). After this directive every library is tiered and the path is unreachable by data. Deleting it is a separate directive (spec Out of scope keeps ladder/tier code unchanged beyond Unit 2).
- (a) Tier ladder values, TV and Movies tiers, genre tiers, content classes: unchanged and verified unchanged (criterion 7).
- (a) `UpdateGenreTier` recompute scope (genre-sourced libraries) unchanged; behaviour preserved, no duplication.
- (b) Audio policy (Unit 3), cull (Unit 4).
- (b) A source-bitrate knob on profile rows (spec Out of scope).
- (b) `Scripts/ActivateMoviesGenreTiers_2026_10_13.py` keeps calling `ReassignTierProfiles(Ids)` with the default; one-time script, not re-run.

## Constraints

- Default off: a tier save without the checkbox never moves an `operator` / `series` / `root_folder` / `manual_sql` file (TV depends on series overrides).
- No new table or column; the choice is a request parameter, not stored state.
- Operator GUI actions (tier 3 + checkbox, rule delete, multiplier) are the operator's; Claude prepares and verifies, never runs them against production.
- Fail loud: `ReplaceOverrides` that is present but not a boolean is a 400.

## Escalation Defaults

- **2160p multiplier (missing domain data).** Recommendation: operator sets the 2160p multiplier on `/settings` Video compliance to 1.25 (ceiling 10,000 kbps). Then 8,001-10,000 kbps files stay compliant, 10,001-12,000 queue when savings pass the existing 20% / 150 MB gate, everything above 12 Mbps queues; this matches the spec's stated expectation and the program goal. TV and Movies are unaffected (0 Movies 4K files; the single TV 4K file is non-compliant either way). Code in this directive does not depend on the answer; criteria 5 and 6 are phrased against "the ceiling" so they verify under either value. If the operator keeps 3.00, 1,139 xxx 4K files (5.4 TB) never re-encode and the spec's size projections are void; that is a program-level decision, recorded here either way.
- Breadth vs. safety on overrides -> safety: default off, explicit checkbox.
- Risk tolerance: medium. Reassigning 4,198 xxx files recomputes compliance for all of them in the background thread; the TV library recompute of 49k files runs the same way today.

## Engineering Calls Already Made

- `IncludeOverrides` is a plain keyword argument on `ReassignTierProfiles`; the SQL adds the source predicate only when it is false. No second method.
- Source for a moved override is the tier source (`library_default_tier` or `genre_tier`), so a later tier save keeps moving it; the override is replaced, not re-labelled.
- Smoke file comes from the 545 files above 24,000 kbps so criterion 5 holds under either multiplier.

## Status

### Plan

1. `ReassignTierProfiles`: drop `sr.GenreSource IS NOT NULL`; add `IncludeOverrides: bool = False`; predicate applied only when false. Tests in `TestMoviesVideoRule.py` updated (query asserts no genre filter; new tests for both override modes).
2. `SystemSettingsController`: `_SpawnLibraryRecompute(StorageRootId, IncludeOverrides=False)`; `UpdateLibraryTier` reads `ReplaceOverrides` (bool or absent, else 400) and passes it. `UpdateGenreTier` unchanged (default).
3. `Settings.html`: checkbox in the library row, unchecked on load; `SaveLibraryTier` sends `ReplaceOverrides`.
4. Contract tests green; restart farm server (`py deploy/deploy-server.py`).
5. Operator: `/settings` xxx -> Tier 3, box ticked, Save; delete rule `XxxPinTier2Good`; decide the 2160p multiplier. Claude verifies criteria 4, 6, 7 by SQL.
6. Smoke: one xxx 4K file > 24,000 kbps through AddJob -> worker -> replaced (criterion 5); sizes recorded.
7. Docs: `classifier.feature.md` C9 + evidence; `video-encoding.feature.md` debt line deleted; plan Phase 4 status; Promotions rows.
8. Deliver, close, commit, push, handoff memory, `/clear`.

### Files

```
Features/ContentClassifier/ContentClassifierService.py       -- EDIT: ReassignTierProfiles acts for any tiered library; IncludeOverrides
Features/SystemSettings/SystemSettingsController.py          -- EDIT: ReplaceOverrides on PUT LibraryTiers; _SpawnLibraryRecompute passes it
Templates/Settings.html                                      -- EDIT: "replace per-file and per-series overrides" checkbox
Tests/Contract/TestMoviesVideoRule.py                        -- EDIT: reassign tests for genre-less library + override modes
Features/ContentClassifier/classifier.feature.md             -- EDIT: C9 wording + evidence
Features/VideoEncoding/video-encoding.feature.md             -- EDIT: delete XXX no-tier debt note
Docs/superpowers/plans/2026-10-29-xxx-program.md             -- EDIT: Phase 4 status
```

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|

### Verification

- **Criterion 1:** `py -m pytest Tests/Contract/TestMoviesVideoRule.py Tests/Contract/TestClassifierCascade.py Tests/Contract/TestTvPinTier1Classification.py -q` -> 35 passed (2026-11-25, 7ca3c0be). `test_reassign_moves_genre_less_library_to_its_library_tier` asserts `Assign([7], 'Profile3', 'library_default_tier')` for a `GenreSource`-less root; `grep -n "GenreSource IS NOT NULL" Features/ContentClassifier/ContentClassifierService.py` -> 0. Live: pending farm server at 7ca3c0be.
- **Criterion 2:** `test_reassign_query_excludes_operator_set_profiles` asserts the `AssignedProfileSource <> ALL(%s)` predicate with `['operator','series','root_folder','manual_sql']` when the flag is off; `test_reassign_with_overrides_drops_the_source_predicate` asserts params `([1],)` and no source predicate when on.
- **Criterion 3:** Flask test client (scratchpad `CheckReplaceOverrides.py`, venv interpreter): `ReplaceOverrides:'yes'` -> 400 `ReplaceOverrides must be a boolean`; `true` -> 200 and `_SpawnLibraryRecompute(3, IncludeOverrides=True)`; absent -> `IncludeOverrides=False`. Page-load check (box unchecked) pending farm server.
- **Criterion 4:** pending operator GUI step.
- **Criterion 5:** fleet smokes 2026-11-26, both via `POST /api/TranscodeQueue/AddJob {MediaFileId, ProfileId: 477, Priority: 200}` on the farm server (no `ForceAdd`), admitted first try. NVENC: MediaFile 55384 (h264 2160p, 25,438 kbps, 1,183 MB, 6.1 min) -> attempt 104045 on `dot-worker-1`, command `-hwaccel cuda ... -c:v av1_nvenc -preset p7 -tune hq -multipass fullres -rc vbr -b:v 8000k -maxrate:v 16000k`, no scale filter (native 2160p), `Success=TRUE`, 332 s, 1,183 -> 424 MB (64%). QSV: MediaFile 55372 (h264 2160p, 24,994 kbps, 1,557 MB, 8.2 min) -> attempt 104046 on `wakko-worker-1`, command `-hwaccel qsv ... -c:v av1_qsv -preset 1 -b:v 8000k -maxrate:v 16000k -extbrc 1 -look_ahead 1`, native 2160p, `Success=TRUE`, 179 s, 1,557 -> 506 MB (68%). VMAF: QSV output (104046) scored 98.92 (min 93.25, P10 97.49, P25 98.32, model `vmaf_4k_v0.6.1`), 25 min on wakko CPU with two QTs sharing the box (`Workers.MaxConcurrentQualityTestJobs=2`); disposition `Reject / VmafAboveMax` because `PostTranscodeGateConfig.VmafAutoReplaceMaxThreshold=96`. Source untouched, 506 MB staged `.ip` left beside it. NVENC output (104045, 59.94 fps source) VMAF 90.40 (min 58.34, P10 80.84, P25 89.44) -> `Replace / VmafPassed`, `FileReplacedDate` 2026-11-26 12:36:52 UTC; MediaFiles 55384 now av1 3840x2160, 8,938 kbps, 418 MB, `TranscodedByMediaVortex=TRUE`, source deleted by `TranscodedOutputPlacement`, Jellyfin notify in the same path. Criterion met on NVENC end-to-end; on QSV the encode is correct and the replacement is blocked only by the operator's max-VMAF gate. Finding for the operator (not this directive's scope): `ProfileThresholds.TargetKbps` is frame-rate-blind; 8,000 kbps at 59.94 fps scored 90.4 while 8,000 kbps at 29.97 fps scored 98.9. Earlier attempt 104044 on 55384 ran at Tier 1 by mistake (BUG-0124: AddJob dropped `QualityTier`), VMAF 81.68 -> Reject, source untouched; staged 720p `.ip` left on the share.
- **Criterion 6:** pending (pick after reassign from the 1,139 files between 8,001 and 24,000 kbps, or below the operator's new ceiling).
- **Criterion 7:** baseline recorded in the criterion; re-count pending.
- **Criterion 8:** `grep -rn "GenreSource" --include=*.md Features/ | grep -i reassign` -> 0; `grep -n "no default tier (XXX)" Features/VideoEncoding/video-encoding.feature.md` -> 0 (7ca3c0be). C9 evidence line pending live counts.

### Decisions Made

- `Tests/Contract/TestFailLoud.py::test_no_growth_against_baseline` fails on clean HEAD (c97eb25f) for `JobProcessor.py` (6 > 5) and `DemucsChunking.py` (1 > 0), neither touched here; tracked in `memory/KNOWN-ISSUES.md` (insert-returning-id note). Not this directive's bug; not blocking verification.
- Code and directive landed in one commit (7ca3c0be) because the code commit's `-m` here-string was split on an inner quoted phrase and the staged files rolled into the directive commit. Message is incomplete for the code change; not amended (already pushed; force-push is operator authority).
- `py deploy/deploy-server.py` is refused by the session classifier; the operator runs it (`! py deploy/deploy-server.py`).
- Criterion 6 is phrased against the live ceiling, not the spec's "7 Mbps": under multiplier 3.00 a 7 Mbps 4K file is compliant and never reaches the marginal-savings gate, so `MarginalSavings` cannot be the observed reason. The observable contract is "at or below the ceiling -> compliant -> not queued".
