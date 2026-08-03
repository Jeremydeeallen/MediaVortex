# Content Classifier

**Slug:** classifier

## What It Does

Assigns `MediaFiles.AssignedProfile` by walking an operator-tunable rules table and picking the first-match profile. Runs as a hook after probe writes metadata. Sticky: only writes when `AssignedProfile IS NULL`. Cascades compliance recompute after write.

Pipeline stage `ST5` in `ingest.flow.md`.

## Workflows

| # | User action | Surface element | Handler | Backing class.method |
|---|---|---|---|---|
| W1 | View / edit rules | `/SQLQueries` (initial) | direct SQL on `ContentClassificationRules` | operator; future `/settings` card deferred |
| W2 | Trigger classification for one file | curl (or /Failures Retry after ResetFailures) | `POST /api/MediaProbe/Probe/<id>` (triggers full probe hook chain incl. classifier) | `MediaProbeController.ProbeFile` |
| W3 | Backfill classification for NULL-profile rows | operator script | `Scripts/SQLScripts/BackfillProfileAssignments.py` | existing |
| W4 | View classification-source breakdown | `/SQLQueries` | `SELECT AssignedProfileSource, COUNT(*) FROM MediaFiles GROUP BY 1` | operator |

## Success Criteria

C1. **Runs on every probe write via `_ExecuteProbe` post-flight.** Sticky-guarded: skips when `AssignedProfile IS NOT NULL`. Contract test.

C2. **First-match rules walk.** Loads `ContentClassificationRules WHERE IsActive=TRUE ORDER BY Priority ASC` fresh per call (no cache). Evaluates all non-NULL matchers; first rule where all match wins. Contract test.

C3. **Sticky-guard preserves operator intent.** `WriteAssignment` SQL: `UPDATE MediaFiles SET AssignedProfile=%s, AssignedProfileSource='classifier' WHERE Id=%s AND AssignedProfile IS NULL`. Concurrent operator write via `/Scanning` or SQL wins the race. Contract test.

C4. **AssignedProfileSource tracks origin.** `'classifier'` for auto-assigned; `'operator'` for Scanning-page assignments; `'manual_sql'` for direct SQL; `'classifier_skip_av1'` when rule matched a codec-skip sentinel (leaves AssignedProfile NULL). Contract test.

C5. **Cascade before return (writer-owns-cascade).** After `WriteAssignment` succeeds, service calls `QueueManagementBusinessService().RecomputeForFiles([Id])`. This is the root-cause fix for Full Circle S1 stuck rows -- see `.claude/rules-details/writer-owns-cascade.md`. Contract: `TestClassifierCascade.py`.

C6. **No-match logs WARNING + leaves AssignedProfile NULL.** `WorkBucket` will derive to `Unclassified` via trigger. Operator sees; adds a rule; next classify run via NULL-profile backfill covers.

C7. **Two rules at same Priority refused at INSERT.** UNIQUE constraint on `Priority`. Operator error surfaced by DB, not silently ordered.

C8. **Rule references a non-existent ProfileName.** Classifier writes the name; downstream queue admission fails with `MissingProfile` in reason; visible in marginal-savings-gate rollup log. Operator fixes rule or sets `IsActive=FALSE`.

## Seams

| ID | Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|---|
| S1 | Probe hook -> Classifier | `_ExecuteProbe` post-flight | invokes `ClassifyAndAssign(Id)` in-process | classifier reads populated probe columns | contract test |
| S2 | Classifier -> Repository (rules load) | `ClassifyAndAssign` | `GetActiveRules()` -> `List[Rule]` | rules ordered by Priority ASC | contract test |
| S3 | Classifier -> Repository (write) | matched rule | `WriteAssignment(Id, ProfileName, 'classifier')` -- single UPDATE with sticky-guard WHERE clause | `MediaFiles.(AssignedProfile, AssignedProfileSource)` populated | contract test |
| S4 | Classifier -> cascade | after WriteAssignment succeeds | `QueueManagementBusinessService.RecomputeForFiles([Id])` | compliance verticals recompute; WorkBucket derives | `TestClassifierCascade.py` |
| S5 | Operator write path | Scanning page / SQL | `UPDATE MediaFiles SET AssignedProfile=?, AssignedProfileSource='operator'` (or `'manual_sql'`) | classifier's sticky-guard preserves this on next probe | contract test |

## AssignedProfileSource semantics

| Value | Interpretation |
|---|---|
| NULL | Pre-classifier row; no rule matched; awaits operator or rule change |
| `'classifier'` | Auto-assigned by rule match |
| `'classifier_skip_av1'` | Rule matched codec-skip sentinel; file is already optimal codec |
| `'operator'` | Manual Scanning-page assignment |
| `'manual_sql'` | Ad-hoc SQL override |

## What this feature does NOT own

- Probe metadata: `Features/MediaProbe/probe.feature.md`
- Compliance rules + evaluation: per-vertical (`video-encoding.feature.md`, `audio-normalization.feature.md`, `container-format.feature.md`)
- WorkBucket derivation: `Features/WorkBucket/work-bucket.flow.md`
- Profile catalog: `Features/Profiles/Profiles.feature.md`

## Status

DRAFTED under directive `ingest-pipeline-kiss`. Cascade-on-write is the material new behavior; existing rule-walk + sticky-guard preserved.
