# Directive: orphan-generators-stop

**Status:** Active -- phase: IMPLEMENTING
**Opened:** 2026-08-01
**Parent (paused):** scan-broken-restore
**Slug:** orphan-generators-stop

## Outcome

Stop the two active sources that keep creating orphan MediaFiles rows (rows pointing at files that don't exist on disk). Orphans clog the LanguageWorker fetch pool + waste ReconcileWithDisk cycles that only run per-RootFolder-walk. Fixing generation at the source is cheaper than continually chasing them.

## The two orphan generators

**G1 — Replace-flow FK failure.** `TranscodedOutputPlacement._UpdateMediaFilesAfterReplacement:432-435` runs `DELETE FROM MediaFiles WHERE (StorageRootId, LOWER(RelativePath))=<new target> AND Id <> <current>` to drop any scan-artifact row the scanner inserted for the new file. If that stale row has TranscodeAttempts children, FK rule `ON DELETE SET NULL` fires against `TranscodeAttempts.MediaFileId NOT NULL` -> constraint violation -> DELETE fails -> exception at line 460 -> `Success=False` returned -> caller keeps the ORIGINAL row pointing at the deleted source file = orphan.

**G2 — Scanner ingests staging dirs.** FileScanningBusinessService walks every subdir of a RootFolder including `_downloads/`, `_AudioTests/`, `_Testing/` (SABnzbd/QBT staging + operator scratch). Rows get created for transient files. ReconcileWithDisk deletes them next pass, next scan re-ingests. Infinite churn.

## Why KISS -- reasoning per fix

**G1 KISS: reparent children, then delete.** Three options considered:

| Option | Change | Trade-off | Verdict |
|---|---|---|---|
| Drop `NOT NULL` on `TranscodeAttempts.MediaFileId` | Schema migration | Loses parent link for orphan history | Operator explicitly said "we don't want to delete the transcode attempts the successful ones tell us what happened" -- preserving history AND its parent link is the goal, not just preservation |
| Change FK to `ON DELETE CASCADE` | Schema migration | Loses attempts entirely on parent delete | Same operator constraint. Deletes history. NO |
| **UPDATE children to reparent, then DELETE parent** | Code-only in `_UpdateMediaFilesAfterReplacement` | 2 extra UPDATEs before the DELETE. Zero schema change. Attempts stay linked to the SURVIVING MediaFile row (which represents the same logical asset -- both rows describe "Heroes S01E23 720p transcode of the 480p original"). | **YES** |

Reasoning: both MediaFiles rows in this collision (X = the transcode originator with the -480p path; Y = the scan-artifact for the -720p-mv output) describe the same logical asset. The transcode LINEAGE lives on X's TranscodeAttempts. When we collapse the pair, X survives (it holds the history) + Y's attempts get repointed at X. Post-collapse, X's RelativePath is the new -720p-mv file, X's TranscodeAttempts include both the "original" transcode + any attempts that were made against Y while it briefly existed. Correct + minimal.

**G2 KISS: exclude prefix list, one config point.** FileScanning already has skip logic for dot-prefix dirs (`.git`, `.thumbnails`, etc). Add an underscore-prefix exclusion list next to the same guard: `_downloads`, `_AudioTests`, `_Testing`. One place, one line, matches existing pattern. No config table, no per-RootFolder override, no operator UI. Add new staging dirs to the constant when they surface.

Reasoning: this is a scanner-invariant, not tunable behavior. Underscore-prefix dirs in this repo are ALWAYS staging/scratch by convention (docs elsewhere confirm). Making it DB-configurable = premature abstraction + a new operator surface for zero benefit.

## Acceptance Criteria

C1. **`_UpdateMediaFilesAfterReplacement` reparents children before DELETE.** Before the `DELETE FROM MediaFiles WHERE StorageRootId=? AND LOWER(RelativePath)=? AND Id <> ?` runs, execute `UPDATE TranscodeAttempts SET MediaFileId = <surviving Id> WHERE MediaFileId IN (SELECT Id FROM MediaFiles WHERE StorageRootId=? AND LOWER(RelativePath)=? AND Id <> <surviving Id>)` + same for `TranscodeFiles`. DELETE succeeds. Verifiable: unit test with a synthetic collision pair + attempts on the stale row -> DELETE completes, attempts point at surviving row.

C2. **Zero MediaFiles update failures with `null value in column "mediafileid" of relation "transcodeattempts"` in Logs post-deploy.** Verifiable: `SELECT COUNT(*) FROM Logs WHERE Timestamp > <deploy-time> AND ExceptionMessage ILIKE '%mediafileid%not-null%'` returns 0 after 24h of transcode activity.

C3. **Scanner excludes `_downloads`, `_AudioTests`, `_Testing` at every RootFolder walk level.** Any subdir whose basename starts with one of these tokens is skipped, no MediaFiles row inserted, no descent into it. Verifiable: after next scan cycle, `SELECT COUNT(*) FROM MediaFiles WHERE RelativePath LIKE '\_downloads/%' OR RelativePath LIKE '\_AudioTests/%' OR RelativePath LIKE '\_Testing/%' ESCAPE '\'` returns 0 (and stays 0 across N scan cycles).

C4. **Contract test grep-fences the retired FK-explosion pattern + confirms staging-dir exclusion.** `Tests/Contract/TestOrphanGeneratorsStopped.py`:
- Grep asserts `DELETE FROM MediaFiles` inside `_UpdateMediaFilesAfterReplacement` is preceded by a matching reparent UPDATE (AST check or line-window regex).
- Grep asserts the scanner's exclusion constant contains `_downloads`, `_AudioTests`, `_Testing`.

## Call-Graph Audit

1. **Multiple flow docs for one conceptual operation:** No new. Transcode-flow.md owns the replace step; no split.
2. **Mode-branching at orchestration:** No new. Reparent logic sits inside existing `_UpdateMediaFilesAfterReplacement` method; not a new orchestration branch.
3. **Shared output columns sparsely populated:** Fix INCREASES consistency -- TranscodeAttempts.MediaFileId always points at a live MediaFile after collapse (previously either the wrong row or NULL after failed DELETE).
4. **OOS ambiguity:** All OOS items classified below.

## Out of Scope

- **Existing orphan MediaFiles cleanup.** (a) not addressed here. ReconcileWithDisk handles as it walks each RootFolder. Prior 52-row SQL DELETE unblocked whisper. This directive stops the FLOW that creates new ones; cleanup of survivors is orthogonal.
- **LanguageWorker path-missing infinite-retry.** (a) not addressed here. Once G1+G2 stop generation and reconcile clears the residue, the retry loop has nothing left to spin on. Separate improvement.
- **DB schema change on TranscodeAttempts.MediaFileId NOT NULL.** (b) known-preserved by operator instruction ("we don't want to delete the transcode attempts").
- **Operator UI to manage scanner exclusion list.** (a) not addressed here. Constant in code is sufficient; underscore-prefix is repo convention.

## Files (planned)

To edit:
- `Features/FileReplacement/TranscodedOutputPlacement.py` (C1 -- add reparent block before line 432 DELETE)
- `Features/FileScanning/FileScanningBusinessService.py` (C3 -- add underscore-prefix exclusion to existing skip guard; location TBD at read time)

To create:
- `Tests/Contract/TestOrphanGeneratorsStopped.py` (C4)

At DELIVERING, promote content into:
- `Features/FileReplacement/FileReplacement.feature.md` (or the transcoded-output-placement colocated doc) -- reparent-before-delete invariant
- `Features/FileScanning/FileScanning.feature.md` -- staging-dir exclusion invariant
- `memory/KNOWN-ISSUES.md` -- resolved entry naming both generators

## Progress

- [ ] NEEDS_STANDARDS_REVIEW: call-graph audit populated (above)
- [ ] NEEDS_PLAN: fix order approved
- [ ] NEEDS_DOC_PREREAD: read colocated feature docs for TranscodedOutputPlacement + FileScanning
- [ ] IMPLEMENTING: C1 + C3 + C4
- [ ] VERIFYING: contract test green; live transcode replace + subsequent scan shows zero new orphans + zero FK-explosion errors
- [ ] DELIVERING: promotions

## Notes

- Parent `scan-broken-restore` paused at IMPLEMENTING with contract test green + whisper resumed. Awaiting closure after orphan-generators-stop lands (the orphan cleanup work here is what makes scan-broken-restore's outcome durable).
- Prior orphan-related archive entry: `BUG-0085` (container build-cache stale-pyc, retired 2026-07-31 via `docker-purge`). Different root cause but same downstream shape.
