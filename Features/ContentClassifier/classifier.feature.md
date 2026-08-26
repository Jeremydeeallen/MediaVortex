# Content Classifier

**Slug:** classifier

## What It Does

Assigns `MediaFiles.AssignedProfile` by walking an operator-tunable rules table and picking the first-match profile. Runs as a hook after probe writes metadata. Sticky: only writes when `AssignedProfile IS NULL`. Cascades compliance recompute after write.

Pipeline stage `ST5` in `ingest.flow.md`.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | View / edit rules | `/settings` "Content classification rules" section | GET/POST/PUT/DELETE `/api/ContentClassification/Rules[/<id>]` | `Features/ContentClassifier/ContentClassificationRulesController.py` |
| W2 | Trigger classification for one file | curl (or /Failures Retry after ResetFailures) | `POST /api/MediaProbe/Probe/<id>` (triggers full probe hook chain incl. classifier) | `MediaProbeController.ProbeFile` |
| W3 | Backfill classification for NULL-profile rows | operator script | `Scripts/SQLScripts/BackfillProfileAssignments.py` | existing |
| W4 | View classification-source breakdown | `/SQLQueries` | `SELECT AssignedProfileSource, COUNT(*) FROM MediaFiles GROUP BY 1` | operator |

## Success Criteria

C1. **Runs on every probe write via `_ExecuteProbe` post-flight.** Sticky-guarded: skips when `AssignedProfile IS NOT NULL`. Contract test.

C2. **First-match rules walk.** Loads `ContentClassificationRules WHERE IsActive=TRUE ORDER BY Priority ASC` fresh per call (no cache). Evaluates all non-NULL matchers; first rule where all match wins. Contract test.

C3. **Sticky-guard preserves operator intent.** Classifier calls `ProfileAssignmentService.Assign(Ids, ProfileName, 'classifier', IfUnsetOnly=True)`. Repo layer emits `UPDATE MediaFiles SET AssignedProfile=%s, AssignedProfileSource='classifier', LastModifiedDate=NOW() WHERE Id = ANY(%s) AND AssignedProfile IS NULL RETURNING Id`. Concurrent operator write via `/Scanning` or SQL wins the race. Contract test.

C4. **AssignedProfileSource tracks origin.** `'classifier'` for auto-assigned; `'operator'` for Scanning-page assignments; `'manual_sql'` for direct SQL; `'classifier_skip_av1'` when rule matched a codec-skip sentinel (leaves AssignedProfile NULL). Contract test.

C5. **Cascade before return (writer-owns-cascade).** Classifier delegates write to `Features/MediaFiles/ProfileAssignmentService.Assign` which UPDATEs AssignedProfile via `MediaFilesRepository.WriteAssignedProfile` then calls `QueueManagementBusinessService().RecomputeForFiles(WrittenIds)`. Single writer path across the codebase; test-grep + type-boundary enforcement. See `.claude/rules-details/writer-owns-cascade.md`. Contract: `TestClassifierCascade.py`, `TestProfileAssignmentServiceCascade.py`.

C6. **No-match logs WARNING + leaves AssignedProfile NULL.** `WorkBucket` will derive to `Unclassified` via trigger. Operator sees; adds a rule; next classify run via NULL-profile backfill covers.

C7. **Two rules at same Priority refused at INSERT.** UNIQUE constraint on `Priority` (`idx_contentclassrules_priority_unique`). REST layer returns HTTP 409 on conflict (`TestContentClassificationRulesAPI.test_create_duplicate_priority_returns_409`).

C8. **Rule references a non-existent ProfileName.** Classifier writes the name; downstream queue admission fails with `MissingProfile` in reason; visible in marginal-savings-gate rollup log. Operator fixes rule or sets `IsActive=FALSE`.

C9. **TV storage root pinned to Tier 1.** `ContentClassificationRules` seed row `TvPinTier1Efficient` at `Priority=20` with `FolderPathPattern='T:\%'` -> `AssignProfileName='AV1 Tier 1 Efficient'`. Wins before any resolution-based default rule. Contract: `TestTvPinTier1Classification.py`. Verifiable via SELECT + `/settings` "Content classification rules" section.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | Probe hook -> Classifier | `_ExecuteProbe` post-flight | invokes `ClassifyAndAssign(Id)` in-process | classifier reads populated probe columns | contract test |
| S2 | Classifier -> Repository (rules load) | `ClassifyAndAssign` | `GetActiveRules()` -> `List[Rule]` | rules ordered by Priority ASC | contract test |
| S3 | Classifier -> ProfileAssignmentService.Assign | matched rule | `Assign(Ids, ProfileName, 'classifier', IfUnsetOnly=True)` -- writes via `MediaFilesRepository.WriteAssignedProfile` (RETURNING Id) | `MediaFiles.(AssignedProfile, AssignedProfileSource)` populated for actually-written Ids | `TestClassifierCascade.py` |
| S4 | ProfileAssignmentService -> cascade | after WriteAssignedProfile returns written Ids | `QueueManagementBusinessService.RecomputeForFiles(WrittenIds)` | compliance verticals recompute; WorkBucket derives | `TestProfileAssignmentServiceCascade.py` |
| S5 | Operator write path | Scanning page / SQL / `/Work/<bucket>` series-profile dropdown | routes through `ProfileAssignmentService.Assign` with `Source='operator'/'series'/'root_folder'/'manual_sql'` | classifier's `IfUnsetOnly=True` preserves this on next probe | contract test |
| S6 | Rules CRUD | `/settings` "Content classification rules" section | GET/POST/PUT/DELETE `/api/ContentClassification/Rules[/<id>]` -> `ContentClassificationRulesController` -> `ContentClassificationRules` table | Priority collision returns 409 | `TestContentClassificationRulesAPI.py` |

## AssignedProfileSource semantics

| Value | Interpretation |
|---|---|
| NULL | Pre-classifier row; no rule matched; awaits operator or rule change |
| `'classifier'` | Auto-assigned by rule match |
| `'classifier_skip_av1'` | Rule matched codec-skip sentinel; file is already optimal codec |
| `'operator'` | Manual Scanning-page assignment |
| `'manual_sql'` | Ad-hoc SQL override |
| `'bulk_tier_by_root_2026_07_23'` / `'series'` / `'bulk-tier2-already-transcoded-2026-07-21'` | Historical bulk-script assignments; dominate assignment volume |

## Design Decisions

**DD1. Rule matchers are metadata-only.** Rules match against ffprobe-derived columns (`Codec`, `ResolutionCategory`, `VideoBitrateKbps`, `AudioCodec`) plus operator taxonomy (`FolderPathPattern`). No content-analysis inputs (motion, scene-change rate, luma variance) are supported. Adding one would require a new vertical + operator-visible cost/benefit case (see DD2).

**DD2. Content-based classification was removed.** Prior implementation ran `ffmpeg signalstats` + PySceneDetect inside the probe path per file (60-600s cost per file), writing `MediaFiles.MotionFraction / SceneChangeRatePerMin / LumaVariance`. Sole consumer was one rule (`AnimeBySignal`, priority 40) that produced the same output profile as `AnimeByFolder` (priority 30, folder pattern `%Anime%`). Sonarr's default anime placement covered the folder rule. Deletion removed ~200 lines of Python + 9 DB columns + one dep (`scenedetect`) with zero classification-outcome change on the current library.

**DD3. Classifier assigns ~0.6% of profiles.** DB snapshot: bulk scripts (`bulk_tier_by_root_2026_07_23` = 40,283, `series` = 7,638, `bulk-tier2-already-transcoded-2026-07-21` = 758) + operator manual (3,602) dominate. Classifier is a small fallback surface for the long tail; it is not the primary assignment path.

**DD4. Anime classification stays folder-pattern-based.** `AnimeByFolder %Anime%` is the sole anime rule. Any future content-based classification proposal must revisit DD2 evidence.

## What this feature does NOT own

- Probe metadata: `Features/MediaProbe/probe.feature.md`
- Compliance rules + evaluation: per-vertical (`video-encoding.feature.md`, `audio-normalization.feature.md`, `container-format.feature.md`)
- WorkBucket derivation: `Features/WorkBucket/work-bucket.flow.md`
- Profile catalog: `Features/Profiles/Profiles.feature.md`

## Status

DRAFTED under directive `ingest-pipeline-kiss`. Cascade-on-write is the material new behavior; existing rule-walk + sticky-guard preserved.
