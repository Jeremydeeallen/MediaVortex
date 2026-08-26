# Writer-Owns-Cascade -- Details

Extends `.claude/rules/writer-owns-cascade.md`. Read the rule first.

## Why this exists

Discovered 2026-08-02 during Full Circle (2023) Season 1 investigation:

- Operator ran on-demand scan for `T:\Full Circle (2023)\Season 1`.
- 6 episodes present in MediaFiles.
- 5 of 6 stuck at `WorkBucket = 'Unclassified'`, `VideoCompliant = None`, `videocompliantreason = 'missing_input:AssignedProfile'`.
- Only 1 file (E04, HEVC) reached `WorkBucket = 'Transcode'`.

Root cause was a pipeline-ordering + missing-cascade combination:

1. Probe hook chain order (per `content-classifier.flow.md`): probe -> ContentSignals -> ComputePriorityScore -> **compliance recompute** -> **classifier**.
2. `video-compliance-multiplier` directive (2026-07-26) added `AssignedProfile` as a required input to `VideoVertical.Evaluate`.
3. At step "compliance recompute", `AssignedProfile IS NULL` -> `VideoVertical.Evaluate` returned `(None, 'missing_input:AssignedProfile')` -> stored.
4. At step "classifier", `WriteAssignment` set `AssignedProfile = 'AV1 Tier 3 Better'`.
5. **No cascade fired at step 4.** Compliance stayed stuck at the step-3 value forever.

E04 slipped through because its source bitrate breached the multiplier gate before `AssignedProfile` was checked (branch ordering coincidence).

## The rule in words

If you are the code path that writes `X`, and any other code path reads `X` to compute `Y`, you are responsible for triggering the recomputation of `Y` before you return. Not the sweeper. Not the next tick. Not the operator running a script. You.

This holds for probe (writes Resolution + Codec + ... -> cascade), classifier (writes AssignedProfile -> cascade), operator SQL updates (writes anything -> cascade), and future writers.

## Pipeline ordering enforcement (paired discipline)

The rule prevents stuck rows in the presence of correctly-ordered writes. But if writes happen in the wrong order, the rule alone cannot repair the derivation. `ingest.flow.md` codifies the ordering:

```
scan -> probe -> ContentSignals -> ComputePriorityScore -> classifier -> compliance recompute
```

Classifier runs BEFORE compliance so compliance sees `AssignedProfile` populated on first pass. Then any subsequent writer to a compliance input cascades per this rule.

## Contract test enforcement

`Tests/Contract/TestWriterOwnsCascadeEnforcement.py`:

1. Enumerates compliance-input columns from the rule's table.
2. Greps the production tree for `UPDATE MediaFiles SET <col>` or equivalent psycopg2 patterns.
3. For each hit, verifies the enclosing function body also calls `RecomputeForFiles`.
4. Whitelist entries carry inline `# cascade-ok: <reason>` marker within 3 lines (e.g. one-shot repair scripts).
5. **Single exemption:** `Features/MediaFiles/MediaFilesRepository.py` (the sanctioned raw writer per `mediafiles-uniqueness-owner.C6`). Every other Repository file is checked. Reason: SSoT writer pattern below eliminates the need for repo-layer cascade -- repos hand back Ids, the service layer owns the cascade.

## SSoT writer pattern (AssignedProfile case study)

Post `tv-tier1-classifier-pin` (2026-08-25), `MediaFiles.AssignedProfile` has exactly one production writer: `Features/MediaFiles/ProfileAssignmentService.Assign(Ids, ProfileName, Source, IfUnsetOnly=False)`.

```
Caller               -> ProfileAssignmentService.Assign
                         |-> MediaFilesRepository.WriteAssignedProfile (raw UPDATE ... RETURNING Id)
                         |-> QueueManagementBusinessService.RecomputeForFiles(WrittenIds)
```

Callers routed through it:
- `ContentClassifierService.ClassifyAndAssign` + `ClassifyAndAssignBatch` (`Source='classifier'`, `IfUnsetOnly=True`)
- `SeriesProfileService.SetProfile` (`Source='series'`)
- `ProfileService.AssignProfileToRootFolder` (`Source='root_folder'`)
- `QueueManagementBusinessService.GetMediaFilesByFolderAndResolutionFilter` (`Source='root_folder'`)
- `Scripts/SQLScripts/BackfillProfileAssignments.py` (`Source='series'`, `IfUnsetOnly=True`)
- `Scripts/SQLScripts/BackfillTvTier1AndCascade_2026_08_25.py` (`Source='backfill_tv_tier1_2026_08_25'`)

Why this works: cascade cannot be forgotten because the service method IS the write. Repositories return Ids; they do not cascade. The enforcement test's Repository.py exemption is safe because no service-layer bypass path exists.

## Repository-layer non-exemption

`Repository.py` files are NOT blanket-exempt from cascade enforcement (unless they are the sanctioned raw writer per `mediafiles-uniqueness-owner`). A repo that writes an AssignedProfile column outside the SSoT service is a violation the test refuses.

Prior blanket-skip (`*Repository.py`) caught a real bug on removal: `ProfileRepository.UpdateMediaFilesProfileByRootFolder` (~40 days undetected) wrote AssignedProfile with priority-only recompute, no compliance cascade. Refactored to `SelectMediaFileIdsByRootFolder` (repo) + `ProfileAssignmentService.Assign` (service) during `tv-tier1-classifier-pin`.

Anti-pattern the test refuses:

```python
def SomeService.WriteBitrate(self, MediaFileId, Kbps):
    self.Db.ExecuteNonQuery(
        "UPDATE MediaFiles SET VideoBitrateKbps = %s WHERE Id = %s",
        (Kbps, MediaFileId),
    )
    # <- test refuses: no RecomputeForFiles call
```

Correct pattern:

```python
def SomeService.WriteBitrate(self, MediaFileId, Kbps):
    self.Db.ExecuteNonQuery(
        "UPDATE MediaFiles SET VideoBitrateKbps = %s WHERE Id = %s",
        (Kbps, MediaFileId),
    )
    QueueManagementBusinessService(self.Db).RecomputeForFiles([MediaFileId])
```

## Repair script

`Scripts/RecomputeStaleCompliance.py` -- one-shot repair for rows where the rule was not yet enforced. Query:

```sql
SELECT Id
FROM MediaFiles
WHERE VideoCompliantReason LIKE 'missing_input:%'
  AND (
       (VideoCompliantReason = 'missing_input:AssignedProfile' AND AssignedProfile IS NOT NULL)
    OR (VideoCompliantReason = 'missing_input:ResolutionCategory' AND ResolutionCategory IS NOT NULL)
    OR (VideoCompliantReason = 'missing_input:VideoBitrateKbps' AND VideoBitrateKbps IS NOT NULL)
  )
```

Batches results through `RecomputeForFiles`. Idempotent. Run once post-deploy of the ingest-pipeline-kiss directive to heal existing rows.

## Common failure modes

| Failure | Symptom | Fix |
|---|---|---|
| Writer forgets cascade | Stuck rows with `missing_input:*` on a populated input | Add `RecomputeForFiles([Id])` to writer; contract test catches it before merge |
| Cascade wrapped in try/except | Silent stuck rows; log noise | Delete the try/except; let failure surface (fail-loud) |
| Writer batches N rows, cascades once with wrong ids | Some rows stuck | Cascade with ALL written ids, not a subset |
| Trigger conflict (WorkBucket derivation clashes with explicit UPDATE) | Contradictory column values | RecomputeForFiles is authoritative; do not write derived columns directly |

## Non-goals

- Enforcing cascade for tier-3 aggregate state (WorkBucket) -- that's DB-trigger-derived.
- Enforcing cascade at read time -- cascade always happens at write time.
- Enforcing cascade for non-compliance-input writes (`LastScannedDate`, `PriorityScore`, `AssignedProfileSource`) -- these don't feed compliance.
