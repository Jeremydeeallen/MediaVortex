# Directive: tv-tier1-classifier-pin

**Status:** Closed

**Slug:** tv-tier1-classifier-pin

**Interrupts:** preencode-loudness-cache-hit (paused).

## Outcome

TV files (StorageRootId=1, canonical prefix `T:\`) always classify to `AV1 Tier 1 Efficient`. Every writer of `MediaFiles.AssignedProfile` cascades compliance recompute in the same call, enforced by construction via a single-writer domain service. Operator tunes classification rules from `/settings`, not from `/SQLQueries`. Outer Banks S05E09 (1080p, 5967 kbps) lands in Transcode (target 900 kbps @ 720p), not Remux.

## Motivation

Outer Banks S05E09 discovered in Remux queue (2026-08-25). Root causes:
- Classifier assigned Tier 3 Better via `Default1080pLiveAction` rule (Priority 70). Tier 3 ceiling 6400 > source 5967 -> Remux. Operator policy: TV = Tier 1 always. No standing rule enforces this.
- 44 TV files currently on Tier 2/3 with `AssignedProfileSource='classifier'`. `RetierTvToTier1_2026_08_07.py` was one-shot; TV rows scanned since ran without the pin.
- `SeriesProfileService.SetProfile` -> `MediaFilesRepository.PropagateSeriesProfile` bulk-UPDATE `AssignedProfile` without cascade. Same day, 101 Dog Whisperer rows kept stale `VideoCompliantReason` -> wrong WorkBucket.
- `MediaFilesRepository.SetAssignedProfileForFile` same class of skip.
- `TestWriterOwnsCascadeEnforcement.py` skips `*Repository.py` -> both writers evade enforcement.
- `ContentClassificationRules` operator-tunable but only editable via `/SQLQueries`. Violates `.claude/rules/gui-editable-knobs.md`; `classifier.feature.md` W1 already carries the deferral debt ("future /settings card deferred").

## Design

**Cascade discipline expressed in code, not test-grep.**

New domain service `Features/MediaFiles/ProfileAssignmentService.py` owns the invariant "AssignedProfile change requires compliance recompute". Single method:

```python
def Assign(MediaFileIds: List[int], ProfileName: Optional[str], Source: str) -> List[int]:
    # UPDATE MediaFiles SET AssignedProfile=%s, AssignedProfileSource=%s WHERE Id = ANY(%s)
    # returns actually-updated Ids; cascades via QueueManagementBusinessService.RecomputeForFiles(Ids)
```

All three writer paths route through it:
- `ContentClassifierService.ClassifyAndAssign` / `ClassifyAndAssignBatch`
- `SeriesProfileService.SetProfile`
- Direct-single-file writers (Scanning page, `SetAssignedProfileForFile` callers)

`MediaFilesRepository.PropagateSeriesProfile` + `SetAssignedProfileForFile` reduce to pure repo methods (return affected Ids); cascade lives in the service layer above.

`TestWriterOwnsCascadeEnforcement.py` unskip `*Repository.py` becomes belt-and-suspenders (main enforcement is now type-level).

## Acceptance Criteria

C1. `ContentClassificationRules` gets row `TvPinTier1Efficient` at Priority=20 (between AV1 skip=10 and Anime=30): `FolderPathPattern='T:\%'`, `AssignProfileName='AV1 Tier 1 Efficient'`, `IsActive=TRUE`. Verifiable via SELECT.

C2. Classifier evaluation on any StorageRootId=1 MediaFile matches TvPinTier1Efficient before any resolution rule. Contract test: `TestTvPinTier1Classification.py` asserts `_Walk` picks TvPinTier1Efficient for a synthetic TV row + does NOT pick it for `M:\` or `Z:\` rows.

C3. `ProfileAssignmentService.Assign(Ids, ProfileName, Source)` is the single writer of `MediaFiles.AssignedProfile` in production code. Contract test: grep `Features/`, `WorkerService/`, `WebService/` for `UPDATE MediaFiles ... SET AssignedProfile` -- outside `MediaFilesRepository` (raw repo) and `ProfileAssignmentService` (service) count = 0.

C4. `ProfileAssignmentService.Assign` cascades via `QueueManagementBusinessService.RecomputeForFiles(WrittenIds)` before returning. Contract test: `TestProfileAssignmentServiceCascade.py` asserts a synthetic Assign call rewrites `VideoCompliantReason` to embed the new profile name.

C5. Three call sites route through `ProfileAssignmentService.Assign`:
- `ContentClassifierService.ClassifyAndAssign` + `ClassifyAndAssignBatch` (replaces direct `Repository.WriteAssignment` + `QueueManagementBusinessService.RecomputeForFiles` pair).
- `SeriesProfileService.SetProfile` (replaces direct `Repository.PropagateSeriesProfile` -- repo method reduced to raw UPDATE + returns Ids).
- Any current caller of `MediaFilesRepository.SetAssignedProfileForFile` (repo method reduced to raw UPDATE + returns Optional[Id]).

C6. `TestWriterOwnsCascadeEnforcement.py` no longer skips `*Repository.py`. All previous violations landed in the refactor of C5.

C7. Backfill (`BackfillTvTier1AndCascade_2026_08_25.py`) uses `ProfileAssignmentService.Assign` to (a) retier every `StorageRootId=1` row where `AssignedProfile <> 'AV1 Tier 1 Efficient'`, (b) recompute every row whose `VideoCompliantReason` embeds a profile name mismatched from `AssignedProfile`. Post-run: `SELECT COUNT(*) FROM MediaFiles WHERE StorageRootId=1 AND AssignedProfile <> 'AV1 Tier 1 Efficient'` = 0; `SELECT COUNT(*) FROM MediaFiles WHERE VideoCompliantReason LIKE 'source_%_ceiling%' AND SUBSTRING(videocompliantreason FROM 'profile=([^:]+):') <> AssignedProfile` = 0.

C8. Smoke: MediaFileId 700065 (Outer Banks S05E09) post-backfill has `AssignedProfile='AV1 Tier 1 Efficient'`, `VideoCompliant=False`, `VideoCompliantReason` embeds `profile=AV1 Tier 1 Efficient`, `WorkBucket='Transcode'`. Queue materialization enqueues it under `processingmode='Transcode'`.

C9. `/settings` gains a new section "Content Classification Rules" positioned immediately after "Transcoding profiles" (rules pick profiles -> adjacency = discoverability). Section shape:

| Column | Editor |
|---|---|
| Priority | int input |
| Rule Name | text input |
| Folder Pattern | text input (nullable) |
| Resolution | select {any, 480p, 720p, 1080p, 2160p} |
| Codec(s) | multi-select {any, h264, hevc, av1, mpeg2, vp9, mpeg4} |
| Bitrate Min/Max (kbps) | int inputs (nullable) |
| Assign Profile | select of active `Profiles.ProfileName` + `__skip__` |
| Active | bool toggle |
| Actions | Edit / Save / Delete / Add row |

REST: `/api/ContentClassification/Rules` (GET list, POST create, PUT id, DELETE id). Contract test: `TestContentClassificationRulesAPI.py` covers list/create/update/delete round-trip.

C10. `Scripts/SQLScripts/RetierTvToTier1_2026_08_07.py` deleted. Its policy now lives in the classification rule + `BackfillTvTier1AndCascade` for the one-shot data reconcile.

C11. Promotions at DELIVERING:
- `classifier.feature.md` W1 handler moves from "operator; future /settings card deferred" to `ContentClassificationRulesController.py` + `/settings` section. New criterion: "TV storage root pins to Tier 1 via `TvPinTier1Efficient` rule at Priority=20."
- `.claude/rules-details/writer-owns-cascade.md`: add "Repository-layer writers of compliance-input columns are NOT exempt from enforcement; single-writer service pattern (`ProfileAssignmentService`) is the SSoT for MediaFiles.AssignedProfile."
- New seam entry S6 in classifier feature doc: Classifier -> `ProfileAssignmentService.Assign` -> Repository UPDATE + cascade.

## Call-Graph Audit

**Flow docs touched:** `ingest.flow.md` ST5 (classifier stage) -- rule table row added, no shape change. No `*.flow.md` duplication.

**Orchestration-level mode-branch check:** none introduced. Classifier walks rules in priority order regardless of storage root; TV pin is DATA, not a branch. `ProfileAssignmentService.Assign` is unbranched (single write + single cascade).

**Shared output columns sparsely populated:** `MediaFiles.AssignedProfile` currently populated by 3 writer paths, cascading state 0/3 uniformly. After directive: 1 writer path, cascade 1/1. `AssignedProfileSource` distribution unchanged.

**OOS clauses:** each item below categorized (a) fixed-in-flight or (b) known debt.

## Out of Scope

- (b) Movies (StorageRootId=2) + XXX (StorageRootId=3) have no default tier pin rule. Classifier defaults for those roots stay as-is. Follow-up directive if operator wants defaults.
- (b) `SeriesProfileService.ClearProfile` does not clear `MediaFiles.AssignedProfile` (documented behavior). Retier on clear unchanged.
- (b) `Templates/Scanning.html` operator-set profile path -- not audited; already writes `AssignedProfileSource='operator'`. If it skips cascade, discovered at DELIVERING and filed as follow-up.
- (a) Rule-name / priority-slot dedup constraint on `ContentClassificationRules` -- existing UNIQUE(Priority) covers priority collisions; RuleName not enforced UNIQUE. Not touched.

## Files

**Create:**
- `Features/MediaFiles/ProfileAssignmentService.py` -- domain service SSoT for AssignedProfile writes + cascade
- `Features/ContentClassifier/ContentClassificationRulesController.py` -- REST CRUD for /api/ContentClassification/Rules
- `Scripts/SQLScripts/AddTvPinTier1EfficientRule_2026_08_25.py` -- idempotent INSERT
- `Scripts/SQLScripts/BackfillTvTier1AndCascade_2026_08_25.py` -- one-shot reconcile via ProfileAssignmentService
- `Tests/Contract/TestTvPinTier1Classification.py` -- C2
- `Tests/Contract/TestProfileAssignmentServiceCascade.py` -- C4
- `Tests/Contract/TestContentClassificationRulesAPI.py` -- C9

**Edit:**
- `Features/ContentClassifier/ContentClassifierService.py` -- route through ProfileAssignmentService
- `Features/MediaFiles/MediaFilesRepository.py` -- `PropagateSeriesProfile` + `SetAssignedProfileForFile` become raw repo methods returning affected Ids; cascade removed
- `Features/WorkBucket/Services/SeriesProfileService.py` -- route through ProfileAssignmentService
- `Features/ContentClassifier/ContentClassifierRepository.py` -- `WriteAssignment` inlined into `ProfileAssignmentService` OR kept as raw repo method (decide at IMPLEMENTING)
- `Tests/Contract/TestWriterOwnsCascadeEnforcement.py` -- unskip `*Repository.py`
- `Templates/Settings.html` -- new section "Content Classification Rules" after Transcoding profiles
- `Features/ContentClassifier/classifier.feature.md` -- promotion at DELIVERING (C11)
- `.claude/rules-details/writer-owns-cascade.md` -- promotion at DELIVERING (C11)

**Delete:**
- `Scripts/SQLScripts/RetierTvToTier1_2026_08_07.py` -- superseded

### Progress

- [x] NEEDS_STANDARDS_REVIEW: rules + standards read (auto-loaded in context)
- [x] NEEDS_PLAN: criteria + Files list approved
- [x] NEEDS_DOC_PREREAD: read `classifier.feature.md`, `work-bucket.feature.md`, `ingest.flow.md`, `mediafiles-uniqueness-owner.feature.md`, `Profiles.feature.md`, `startup.flow.md`
- [x] IMPLEMENTING: ProfileAssignmentService + 5-way route + rule row + settings UI + backfill + tests
- [x] VERIFYING: 14/14 tests pass; backfill ran on I9 (188 TV rows retiered + 6 stale-reason rows recomputed; residuals 0/0); Outer Banks smoke passed (Transcode bucket); WebService restarted + REST + settings page smoke passed
- [x] DELIVERING: promotions to classifier.feature.md + writer-owns-cascade rule-details; deleted Retier script

### Promotions

- Directive Design section + C3/C4 -> `.claude/rules-details/writer-owns-cascade.md` (SSoT writer pattern + Repository-layer non-exemption sections).
- Directive C1 + C9 (TV pin rule + criterion) -> `Features/ContentClassifier/classifier.feature.md` C9 (new).
- Directive C3-C6 (single writer path) -> `classifier.feature.md` C3 + C5 + S3 + S4 (rewritten).
- Directive C9 (settings UI) -> `classifier.feature.md` W1 (graduates from "/SQLQueries + deferred" to `/settings` REST) + S6 (new seam).
- Directive C7 (Priority collision -> 409) -> `classifier.feature.md` C7 (rewritten to name enforcement test).

### Delivery Report

- DIRECTIVE: TV files always classify to Tier 1 Efficient; every AssignedProfile writer cascades compliance recompute via a single-writer domain service; operator edits classification rules via /settings.
- STATUS: Done. Verified end-to-end on I9 sha (post-commit).
- WHAT SHIPPED:
  - `ContentClassificationRules.TvPinTier1Efficient` row at Priority=20 (`FolderPathPattern='T:\%'` -> `AV1 Tier 1 Efficient`).
  - `Features/MediaFiles/ProfileAssignmentService.py` -- SSoT writer for `MediaFiles.AssignedProfile`; writes via `MediaFilesRepository.WriteAssignedProfile` then cascades `RecomputeForFiles(WrittenIds)`.
  - `MediaFilesRepository`: new `WriteAssignedProfile(Ids, Name, Source, IfUnsetOnly)` + `SelectUntranscodedInSeries` + `SelectMediaFileIdsByRootFolder`; deleted `SetAssignedProfileForFile` + `PropagateSeriesProfile` + `UpdateMediaFilesProfileByRootFolder` (last one was the ~40-day undetected priority-only cascade bug).
  - 5 callers routed through ProfileAssignmentService: ContentClassifierService, SeriesProfileService, ProfileService.AssignProfileToRootFolder, QueueManagementBusinessService.GetMediaFilesByFolderAndResolutionFilter, BackfillProfileAssignments.
  - `ContentClassifierRepository.WriteAssignment` deleted (subsumed by ProfileAssignmentService); classifier's sticky-guard preserved via `IfUnsetOnly=True`.
  - `Features/ContentClassifier/ContentClassificationRulesController.py` -- REST CRUD on `/api/ContentClassification/Rules[/<id>]`.
  - `Templates/Settings.html` -- new "Content classification rules" section between Transcoding profiles + FFmpeg paths; table + inline edit + add + delete + priority-collision toast.
  - `TestWriterOwnsCascadeEnforcement.py` unskipped `Repository.py` (kept a single exemption for `MediaFilesRepository.py` as sanctioned raw writer).
  - 3 new contract tests: `TestTvPinTier1Classification.py` (C2), `TestProfileAssignmentServiceCascade.py` (C4), `TestContentClassificationRulesAPI.py` (C9).
  - `Scripts/SQLScripts/BackfillTvTier1AndCascade_2026_08_25.py` -- one-shot; retiered 188 TV rows + reconciled 6 stale-reason rows.
  - `Scripts/SQLScripts/AddTvPinTier1EfficientRule_2026_08_25.py` -- idempotent rule INSERT.
  - Deleted `Scripts/SQLScripts/RetierTvToTier1_2026_08_07.py` (superseded).
- HOW TO USE IT: operator edits classification rules from `/settings` > "Content classification rules". Any new TV scan auto-classifies to Tier 1. Series-profile / root-folder / operator writes cascade automatically.
- WHAT YOU NEED TO EXECUTE: `py deploy/deploy-fleet.py` to roll new code to dot/wakko/larry (I9 restarted for smoke). Fleet redeploy is deferred; workers on old code still write AssignedProfile via `SetAssignedProfileForFile` -- caller import will fail on first call (fail-loud). Recommend redeploy before next series-profile change.
- CRITERIA VERIFICATION:
  - C1: `SELECT * FROM ContentClassificationRules WHERE RuleName='TvPinTier1Efficient'` returns Priority=20, FolderPathPattern='T:\%', Active.
  - C2: `TestTvPinTier1Classification.py` 2/2 pass.
  - C3-C5: `TestClassifierCascade.py` 3/3, `TestWriterOwnsCascadeEnforcement.py` 1/1, `TestProfileAssignmentServiceCascade.py` 3/3 -- single-writer + cascade verified.
  - C6: enforcement test with `Repository.py` unskipped passes (only MediaFilesRepository exempted).
  - C7: backfill ran; post-run `SELECT COUNT(*) FROM MediaFiles WHERE StorageRootId=1 AND AssignedProfile <> 'AV1 Tier 1 Efficient'` = 0; stale-reason count = 0.
  - C8: Outer Banks S05E09 (Id=700065) now `AssignedProfile='AV1 Tier 1 Efficient'`, `VideoCompliant=False`, `VideoCompliantReason='source_above_ceiling:5967>1800(profile=AV1 Tier 1 Efficient:900*2.0)'`, `WorkBucket='Transcode'`.
  - C9: `/settings` page renders new section (curl grep); `/api/ContentClassification/Rules` returns 200 with rule list; `TestContentClassificationRulesAPI.py` 3/3 pass (list, CRUD roundtrip, 409 on duplicate priority).
  - C10: `Scripts/SQLScripts/RetierTvToTier1_2026_08_07.py` deleted; `Test-Path` returns False.
  - C11: promotions above.
- DECISIONS I MADE:
  - Refactored `ProfileRepository.UpdateMediaFilesProfileByRootFolder` + `MediaFilesRepository.UpdateMediaFilesProfileByRootFolder` (two duplicate methods!) into a single `SelectMediaFileIdsByRootFolder` on MediaFilesRepository. Consolidated per `mediafiles-uniqueness-owner` C6 (MediaFiles SQL lives on that repo). Fixed a ~40-day undetected cascade bug as side benefit.
  - Kept `MediaFilesRepository.py` as the sole exemption in `TestWriterOwnsCascadeEnforcement`. Removing the exemption entirely would force cascade into repo layer (violates SRP -- repo returns Ids, service owns cascade).
  - REST layer uses `ExecuteReturning` for INSERT + UPDATE + DELETE to detect actual affected rows (returns 404 vs silent 0).
  - Backfill Source label `'backfill_tv_tier1_2026_08_25'` (not overwriting `'series'` / `'classifier'`) so operator can audit which files were retiered by this backfill.
- KNOWN GAPS / DEFERRED:
  - Fleet redeploy pending (dot/wakko/larry on old code). Old code paths that called `SetAssignedProfileForFile` / `PropagateSeriesProfile` / `UpdateMediaFilesProfileByRootFolder` will `AttributeError` on first call -- fail-loud, not silent-wrong.
  - Movies (StorageRootId=2) + XXX (StorageRootId=3) still classifier-defaulted -- separate directive if operator wants explicit pins.
  - Scanning-page operator profile write path not audited (OOS declared).
