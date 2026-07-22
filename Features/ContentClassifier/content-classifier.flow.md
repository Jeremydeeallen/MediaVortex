# Flow: Content Classifier

**Slug:** content-classifier

## Entry Point

`MediaProbeBusinessService._ExecuteProbe(MediaFile)` -- the classifier runs as the LAST step of the probe hook chain, AFTER:
1. Probe metadata written
2. `ContentSignals` written (if compute succeeded)
3. `ComputePriorityScore` written
4. Compliance recompute fired (`QueueManagementBusinessService.RecomputeForFiles`)

Also invoked manually from `Scripts/SQLScripts/BackfillProfileAssignments.py` for historical NULL-profile rows.

The classifier is the only writer of `AssignedProfile` with `AssignedProfileSource='classifier'`. Operator assignments via the Scanning page write `'operator'`; ad-hoc SQL writes `'manual_sql'`.

**Classifier role: HINT for auto-enqueue paths.** `AssignedProfile` is not a compliance input. Compliance evaluators (`AudioVertical.Evaluate` + `VideoVertical.Evaluate` + `ContainerVertical.Evaluate`) read baseline rules from their respective `*ComplianceRules` tables and never consume `AssignedProfile`. The classifier's output steers the scanner auto-enqueue path + backfill scripts + `/Work/Compliant` operator-visible recommendation, not the compliance decision itself. Ordering of classifier vs compliance recompute inside the probe hook chain is therefore behavior-irrelevant to bucket assignment.

## Pipeline

| ID | Stage | File | What It Does |
|---|---|---|---|
| ST1 | Probe + signal chain completes | `MediaProbeBusinessService._ExecuteProbe` | MediaFile row has populated probe metadata + (optionally) ContentSignals columns + PriorityScore. |
| ST2 | Sticky-override gate | `ContentClassifierService.ClassifyAndAssign(Id)` | If `MediaFile.AssignedProfile IS NOT NULL`, classifier returns the existing value and does NOT write. Operator intent wins permanently. |
| ST3 | Load rules fresh | `ContentClassifierRepository.GetActiveRules()` | `SELECT * FROM ContentClassificationRules WHERE IsActive=TRUE ORDER BY Priority ASC`. Fresh per call -- no caching. |
| ST4 | Walk rules, first match wins | service-internal | For each rule in priority-ascending order: evaluate all non-NULL matchers; if ALL match the MediaFile row, this rule wins. If no rule matches, emit WARNING and leave AssignedProfile NULL. |
| ST5 | Apply special sentinels | service-internal | `AssignProfileName='__skip__'` triggers the codec-skip path: write `AssignedProfile=NULL, AssignedProfileSource='classifier_skip_av1'`. Other sentinels reserved for future use. |
| ST6 | Persist | `ContentClassifierRepository.WriteAssignment(Id, ProfileName, 'classifier')` | `UPDATE MediaFiles SET AssignedProfile=%s, AssignedProfileSource='classifier' WHERE Id=%s AND AssignedProfile IS NULL`. The `AND AssignedProfile IS NULL` guard prevents racing with a concurrent operator write. |
| ST7 | Log | `LoggingService.LogInfo` | `"ContentClassifier: matched rule '<RuleName>' -> profile '<ProfileName>' for MediaFileId N"`. One line per assignment. |

## Seams

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `ST1 -> ST2` (probe completes -> classifier inputs ready) | `MediaProbeBusinessService._ExecuteProbe` (transcode.flow.md::ST2) + `ContentSignals` flow | `MediaFiles.(Codec, Resolution, VideoBitrateKbps, MotionFraction, SceneChangeRatePerMin, LumaVariance)` populated, plus `MediaFiles.AssignedProfile IS NULL` (sticky guard) | `ContentClassifierService.ClassifyAndAssign(Id)` reads the row | `SELECT COUNT(*) FROM MediaFiles WHERE AssignedProfile IS NULL AND Codec IS NOT NULL` -- non-zero before classifier runs, decremented after |
| S2 | `ST3 -> ST4` (rules loaded -> matched) | Operator INSERT/UPDATE on `ContentClassificationRules` (no MediaVortex writer) | `ContentClassificationRules.(Priority INT UNIQUE, IsActive BOOLEAN, BitrateKbpsMin/Max, ResolutionCategory, CodecIn, MotionFractionMin/Max, SceneChangeRateMin/Max, LumaVarianceMin/Max, FolderPathPattern, AssignProfileName TEXT NOT NULL)` | Classifier iterates rule rows in priority order | `\d ContentClassificationRules` shows the schema; `SELECT COUNT(*) WHERE IsActive=TRUE` > 0 |
| S3 | `ST6 -> downstream` (classifier write -> queue admission) | `ContentClassifierRepository.WriteAssignment` | `MediaFiles.(AssignedProfile TEXT, AssignedProfileSource TEXT)` -- single UPDATE statement | `QueueManagementBusinessService._EvaluateCompliance` reads `AssignedProfile`; emits cascade decision | `SELECT AssignedProfileSource, COUNT(*) FROM MediaFiles GROUP BY AssignedProfileSource` -- 'classifier' bucket non-zero after first probe pass |

## Failure Modes

| Failure | Symptom | Resolution |
|---|---|---|
| Rules table empty | Every classify call emits WARNING "no rule matched"; all rows stay NULL-profile | Operator runs the seed migration OR inserts at least one default rule. SmartPopulate filters NULL-profile rows out of "Next Batch" so nothing breaks downstream. |
| Rule references a non-existent ProfileName | Classifier writes the bogus name; downstream queue admission fails with "MissingProfile" reason | Visible immediately in the marginal-savings-gate rollup log. Operator updates the rule to reference a real profile OR sets the rule IsActive=FALSE. |
| ContentSignals NULL on the row | Rules with non-NULL signal matchers automatically FAIL the match; rules without signal matchers proceed normally | Graceful degradation: file gets classified by bitrate + folder + resolution, just not as precisely as it would with signals. Eventually backfill populates signals and a subsequent re-classify (after operator nullifies AssignedProfile) refines the assignment. |
| Two rules at the same Priority | UNIQUE constraint blocks the second insert | By design. Priority is the conflict-resolution mechanism; collisions are an operator error and the DB tells them. |
| Classifier raises (DB hiccup) | Service catches at top level, logs Exception, returns None; probe continues with NULL AssignedProfile | Acceptable. Next probe retries via the same path. |

## State Surface

`MediaFiles.AssignedProfile TEXT, AssignedProfileSource TEXT` columns:

| AssignedProfile | AssignedProfileSource | Interpretation |
|---|---|---|
| NULL | NULL | Pre-classifier row, no operator assignment |
| NULL | `'classifier_skip_av1'` | Classifier matched the `AlreadyAv1Skip` rule -- file is already optimal codec |
| `<profile name>` | `'classifier'` | Auto-assigned by this feature |
| `<profile name>` | `'operator'` | Set by Scanning-page folder assignment |
| `<profile name>` | `'manual_sql'` | Operator wrote via SQL Queries page or ad-hoc connection |

The `AssignedProfileSource` column makes per-source counts queryable -- the operator can verify "yes, X% of my library is now classifier-assigned, Y% operator-pinned" without inferring from indirect signals.

## Continuous Mode Specifics

Classifier runs inside the probe hook -- inherits the probe scheduler's cadence. Same as `ContentSignals`. Every newly-discovered file gets classified on its first probe.

For the one-shot backfill of pre-feature rows, `BackfillProfileAssignments.py` is operator-invoked. After the backfill completes, the classifier handles all new files automatically.

## Rule Operator Mental Model

Think of the rules as a priority-ordered list of "if-then" claims:

```
IF rule's matchers all apply to this file THEN assign this profile.
The FIRST rule whose matchers all apply wins.
```

Tuning the system means editing the rules table:
- Insert a new rule with low Priority to override an existing default
- Set `IsActive=FALSE` to disable a rule without deleting it
- Adjust thresholds (`BitrateKbpsMax`, `MotionFractionMax`) to widen / narrow a rule's reach
- Add new rules as new profiles ship (e.g. when an HDR-aware profile lands)

The operator never needs to read Python code to understand WHY a file got the profile it got -- the rule that matched is in `AssignedProfileSource` adjacent to the rule table's `RuleName`.

## Surface

No direct UI in the initial cut. Operator interaction lives at `/SQLQueries`:

```sql
-- See current rules in priority order
SELECT Priority, RuleName, AssignProfileName, IsActive
FROM ContentClassificationRules ORDER BY Priority;

-- See classification source breakdown
SELECT AssignedProfileSource, COUNT(*)
FROM MediaFiles GROUP BY AssignedProfileSource;

-- See which rule assigned what
SELECT mf.FilePath, mf.AssignedProfile, mf.AssignedProfileSource
FROM MediaFiles mf
WHERE mf.AssignedProfileSource = 'classifier'
ORDER BY mf.LastScannedDate DESC LIMIT 50;
```

A future `/settings` "Classification Rules" card is a deferred follow-up -- the SQL is already enough for operator use.
