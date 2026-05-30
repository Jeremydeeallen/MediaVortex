# Content Classifier -- Auto-Assign Profile by Rules

## What It Does

Automatically assigns a `MediaFiles.AssignedProfile` value when a row's `AssignedProfile IS NULL`, by walking an operator-tunable rules table and picking the first matching rule's profile.

Rules are scored on probe-derived metadata (`VideoBitrateKbps`, `ResolutionCategory`, `Codec`) and `Features/ContentSignals/`-derived signals (`MotionFraction`, `SceneChangeRatePerMin`, `LumaVariance`) plus folder-path pattern matching. The match is data-driven from the `ContentClassificationRules` table -- no rule logic is hardcoded in Python.

Operator overrides always win. The classifier ONLY writes when `AssignedProfile IS NULL`. Folder-level profile assignment via the existing Scanning page UI remains the canonical override path.

Triggered on probe completion (via `Features/MediaProbe/` hook, after `ContentSignals` writes its signals) AND via a backfill script for historical NULL-profile rows.

## Concern

Manual per-folder profile assignment is fine for ~50 folders but breaks at library scale. With ~67k MediaFiles rows and ~13.5k that just became transcodable (post-retroflip of mis-marked TranscodedByMediaVortex), most files either have no profile or have the wrong one for their content type. Result: SmartPopulate surfaces files in the wrong queue; the operator either has to assign profiles to thousands of folders manually OR accept the default profile is wrong for ~half the library.

The rules table is the contract -- it makes the classifier's behavior fully visible and tunable from a SQL prompt or future GUI. The Python service is a thin rule-walker, not a policy engine.

## Surface

- **Auto-assignment** runs in the probe hook (invisible to operator unless they look at `MediaFiles.AssignedProfile` post-probe).
- **Rules table** is operator-editable via `/SQLQueries` today (or a future `/settings` "Classifier Rules" card). Adding / removing / reordering rules takes effect on the next classify call (no caching).
- **Folder pin override**: existing `Features/Profiles/AssignProfileToRootFolder` (manual assignment) writes `AssignedProfile` directly; classifier sees the non-NULL value and skips. Operator intent is sticky.
- **Backfill script**: `Scripts/SQLScripts/BackfillProfileAssignments.py` -- walks NULL-profile rows in batches, applies the classifier, reports per-rule hit counts.
- **Audit**: `MediaFiles.AssignedProfile` write also writes `MediaFiles.AssignedProfileSource` (`'operator'` / `'classifier'` / `'manual_sql'`) so the operator can tell which writes came from the classifier vs which were operator-assigned.

## Success Criteria

### Schema

1. `ContentClassificationRules` table exists with columns:
   ```
   Id BIGSERIAL PRIMARY KEY,
   RuleName TEXT NOT NULL,
   Priority INTEGER NOT NULL,
   IsActive BOOLEAN NOT NULL DEFAULT TRUE,
   BitrateKbpsMin INTEGER,
   BitrateKbpsMax INTEGER,
   ResolutionCategory TEXT,
   CodecIn TEXT,                       -- comma-separated list, e.g. 'h264,hevc'
   MotionFractionMin DOUBLE PRECISION,
   MotionFractionMax DOUBLE PRECISION,
   SceneChangeRateMin DOUBLE PRECISION,
   SceneChangeRateMax DOUBLE PRECISION,
   LumaVarianceMin DOUBLE PRECISION,
   LumaVarianceMax DOUBLE PRECISION,
   FolderPathPattern TEXT,             -- SQL LIKE pattern, e.g. '%Anime%' or 'M:\\%'
   AssignProfileName TEXT NOT NULL,
   Description TEXT,
   LastUpdated TIMESTAMP DEFAULT NOW(),
   Source TEXT                         -- 'InitialSeed' | 'OperatorEdit'
   ```
   NULL on any matcher column = wildcard (matches any value). UNIQUE constraint on Priority. Verifiable: `\d ContentClassificationRules` shows the columns and unique constraint.

2. `MediaFiles.AssignedProfileSource TEXT` column exists, nullable. Values used: `'operator'` (set by Scanning-page folder assignment), `'classifier'` (set by this feature), `'manual_sql'` (set by ad-hoc SQL). NULL = legacy or unknown. Verifiable: `\d MediaFiles` shows the column.

3. Migration script is idempotent. Verifiable: running twice produces no errors and no schema diff.

### Rule semantics

4. The classifier walks rules in ORDER BY Priority ASC (lowest priority number = checked first). First match wins. Verifiable: insert two rules that both match a given file with different priorities; the lower-priority-number rule's profile is assigned.

5. A matcher column is "matched" when:
   - NULL: always matches (wildcard)
   - non-NULL numeric Min: file's value >= Min
   - non-NULL numeric Max: file's value <= Max
   - non-NULL `CodecIn`: file's Codec appears in the comma-separated list
   - non-NULL `ResolutionCategory`: file's ResolutionCategory exact-equals the rule's value
   - non-NULL `FolderPathPattern`: `MediaFiles.FilePath LIKE FolderPathPattern ESCAPE '!'`

   For a rule to match, ALL of its non-NULL matchers must match. Verifiable: a rule with `BitrateKbpsMax=1500 AND FolderPathPattern='T:%'` matches T:\ files at <=1500 kbps; not M:\ files; not 1600 kbps files.

6. `IsActive=FALSE` rules are skipped during walk -- the operator disables a rule without deleting it. Verifiable: toggle a rule's IsActive=FALSE and observe the classifier no longer hits it.

7. Classifier signals derived from `ContentSignals` (MotionFraction, SceneChangeRatePerMin, LumaVariance) match against the file's columns. When the file's signal is NULL, ANY rule with a non-NULL signal matcher on that column fails the match for that rule. Verifiable: a rule with `MotionFractionMax=0.3` does NOT match a file with `MotionFraction IS NULL` -- the file skips down to the next rule.

8. If no rule matches, classifier emits a single WARNING `"ContentClassifier: no rule matched MediaFileId N (codec=X bitrate=Y res=Z); leaving AssignedProfile NULL"` and leaves the row unchanged. Verifiable: insert a file with no matching rules, observe NULL stays NULL and the WARNING appears.

### Service contract

9. `Features/ContentClassifier/ContentClassifierService.ClassifyAndAssign(MediaFileId)` reads the MediaFile + rules fresh per call (no caching of either), walks rules, calls repository to update `AssignedProfile` + `AssignedProfileSource='classifier'`. Returns the matched RuleName or None. NEVER raises -- failure logged, returns None. Verifiable: call with a known-good ID -> non-None rule name + row updated.

10. The service skips files where `AssignedProfile IS NOT NULL` -- operator overrides are sticky. Verifiable: pre-set a row's AssignedProfile manually, call classifier, observe no write and the service returns the existing value as "preserved."

11. Bulk variant `ClassifyAndAssignBatch(MediaFileIds: List[int])` processes many files with the rule table loaded ONCE for the call duration. Verifiable: classifying 1000 rows produces 1000 row UPDATEs but only one rules-table SELECT.

### Probe hook

12. `Features/MediaProbe/MediaProbeBusinessService._ExecuteProbe` invokes `ClassifyAndAssign(MediaFileId)` AFTER `ContentSignals` has written, AFTER `ComputePriorityScore` has written. Failure does not block probe completion. Verifiable: induce a classifier failure (e.g. drop the rules table), observe probe still completes and the row keeps its probe metadata.

13. The hook fires once per probe; the in-service `AssignedProfile IS NOT NULL` short-circuit ensures re-probing does not overwrite an existing assignment. Verifiable: probe a file twice; second probe leaves the assignment untouched.

### Seeded rule set

14. Migration seeds the following baseline rules in Priority order. All `Source='InitialSeed'`, `IsActive=TRUE`. Each rule's `AssignProfileName` must reference a profile that already exists in `Profiles` table at migration time. Verifiable: `SELECT Priority, RuleName, AssignProfileName FROM ContentClassificationRules ORDER BY Priority`:

    | Priority | RuleName | Matchers | AssignProfileName |
    |---|---|---|---|
    | 10 | `AlreadyAv1Skip` | `CodecIn='av1'` | -- (no rule emits this; skip handled separately) |
    | 20 | `Anime4KSpecial` | `ResolutionCategory='2160p' AND FolderPathPattern='%Anime%'` | (highest-quality NVENC anime profile, when added) |
    | 30 | `AnimeByFolder` | `FolderPathPattern='%Anime%'` | Anime-tuned profile (added in Phase 1) |
    | 40 | `AnimeBySignal` | `MotionFractionMax=0.30 AND SceneChangeRateMax=2.0 AND LumaVarianceMax=400.0` | Anime-tuned profile |
    | 50 | `LowBitrateLiveAction` | `BitrateKbpsMax=1500 AND CodecIn='h264,hevc'` | Rate-anchored profile (added in Phase 1) |
    | 60 | `HighBitrate4K` | `ResolutionCategory='2160p' AND BitrateKbpsMin=15000` | 4K-downscale profile |
    | 70 | `Default1080pLiveAction` | `ResolutionCategory='1080p'` | Current `nv_cq32_sink` |
    | 80 | `Default720pLiveAction` | `ResolutionCategory='720p'` | Current 720p profile |
    | 90 | `Default480pPassthrough` | `ResolutionCategory='480p'` | -- (no rule; 480p stays unassigned, low storage win) |

    Note: rules referencing profiles that do not yet exist at migration time are inserted with `IsActive=FALSE` and a Description note. They activate once the corresponding profile lands (operator flips IsActive=TRUE).

15. The `AlreadyAv1Skip` rule entry exists with a sentinel `AssignProfileName='__skip__'` -- when the classifier matches this rule, it writes `AssignedProfile=NULL, AssignedProfileSource='classifier_skip_av1'` to mark that the file was deliberately not classified (its codec is already optimal). Verifiable: an av1-codec file post-classifier has `AssignedProfileSource='classifier_skip_av1'`, not a profile name.

### Backfill

16. `Scripts/SQLScripts/BackfillProfileAssignments.py` walks `MediaFiles WHERE AssignedProfile IS NULL` in batches (default 500), applies the classifier per row, writes the assignment + source. Supports `--dry-run` (no writes; reports what would be assigned), `--limit`, `--batch-size`. Reports per-rule hit count at the end. Verifiable: run with `--dry-run --limit 100`; observe the report breakdown without DB writes.

17. The backfill is idempotent (NULL-profile rows only). Re-running on the same state processes zero rows. Verifiable: run, snapshot AssignedProfile values, run again, second run reports 0 processed.

## Stability and operability

- **Rules walked fresh per call**: classifier MUST NOT cache the rules table at process start. Operator's rule edits take effect on the next classify call -- no worker restart needed. Per `feedback_no_cached_db_settings.md`.
- **Operator overrides are sticky**: `AssignedProfile IS NOT NULL` short-circuits the classifier permanently for that row. The only way to re-classify is to nullify `AssignedProfile` explicitly (operator-intentional act).
- **Fail-open default**: if no rule matches AND signals are NULL AND codec/bitrate fall outside all configured ranges, the row keeps `AssignedProfile=NULL`. SmartPopulate already handles NULL-profile rows (filters them out of "Next Batch" until assigned). Better to under-classify than mis-classify.
- **Audit trail**: `AssignedProfileSource` records who wrote the assignment. Operator can query `SELECT AssignedProfileSource, COUNT(*) FROM MediaFiles GROUP BY AssignedProfileSource` to see classifier vs operator vs legacy split.
- **Rule-driven**: every classification decision is one of N rules in the table. Walking the rules in priority order is the entire policy. If a content type misbehaves, the operator inserts a higher-priority rule above the default -- no code change.

## Status

NOT STARTED -- 2026-05-30.

### Progress

- [ ] 1. Migration script `AddContentClassificationRules.py` (criteria 1-3) + seeded baseline rules (criterion 14).
- [ ] 2. `Features/ContentClassifier/` directory: `ContentClassifierService.py`, `Models/`, `ContentClassifierRepository.py`.
- [ ] 3. Probe hook in `MediaProbeBusinessService._ExecuteProbe` after ContentSignals + PriorityScore.
- [ ] 4. Backfill script `BackfillProfileAssignments.py` (criteria 16-17).
- [ ] 5. Update flow doc `content-classifier.flow.md`, `MediaProbe.feature.md`, `transcode.flow.md` Stage 3.5.
- [ ] 6. Deploy to fleet so probe-time auto-assignment fires.
- [ ] 7. Run backfill for already-probed library; report hit-count breakdown.
- [ ] 8. Live verify: assign a folder manually -> classifier respects it. Probe a new file -> classifier picks the right profile.

## Scope

```
Scripts/SQLScripts/AddContentClassificationRules.py         -- NEW: idempotent table + seed
Scripts/SQLScripts/BackfillProfileAssignments.py            -- NEW: one-shot backfill
Features/ContentClassifier/ContentClassifierService.py      -- NEW: rule walker
Features/ContentClassifier/ContentClassifierRepository.py   -- NEW: rule + assignment IO
Features/ContentClassifier/Models/ContentClassificationRuleModel.py -- NEW: dataclass
Features/ContentClassifier/__init__.py                      -- NEW
Features/ContentClassifier/content-classifier.feature.md    -- this file
Features/ContentClassifier/content-classifier.flow.md       -- NEW
Features/MediaProbe/MediaProbeBusinessService.py            -- hook insertion after ContentSignals + PriorityScore
transcode.flow.md                                           -- Stage 3.5 expanded
```

## Files

| File | Role |
|------|------|
| `Scripts/SQLScripts/AddContentClassificationRules.py` | Migration: ContentClassificationRules table + AssignedProfileSource column + seeded rules per criterion 14. |
| `Scripts/SQLScripts/BackfillProfileAssignments.py` | One-shot batched backfill for NULL-profile rows. --dry-run / --limit / --batch-size. Reports per-rule hit count. |
| `Features/ContentClassifier/ContentClassifierService.py` | `ClassifyAndAssign(MediaFileId) -> Optional[str]`. `ClassifyAndAssignBatch(MediaFileIds)`. Reads rules fresh per call. Walks priority-asc. First match wins. |
| `Features/ContentClassifier/ContentClassifierRepository.py` | `GetActiveRules() -> List[Rule]`, `WriteAssignment(MediaFileId, ProfileName, Source)`. No caching. |
| `Features/ContentClassifier/Models/ContentClassificationRuleModel.py` | Dataclass mirroring the table. |
| `Features/MediaProbe/MediaProbeBusinessService.py` | After ContentSignals + ComputePriorityScore, call ClassifyAndAssign. Try/except; never blocks probe. |

## Deviation from conventions

None. Vertical-slice feature directory. Data-driven via the rules table (no hardcoded policy). Read-fresh per call. Audit-source tracking on writes.

## Related features

- `Features/ContentSignals/` -- provides MotionFraction/SceneChangeRatePerMin/LumaVariance inputs.
- `Features/Profiles/nvenc-profiles.feature.md` and `nvenc-rate-anchored.feature.md` -- provide the profiles that rules assign.
- `Features/TranscodeQueue/marginal-savings-gate.feature.md` -- the downstream gate that further filters classifier-assigned files at queue-population time.
- `Features/Profiles/` folder-pin path -- the operator override that wins over the classifier.
