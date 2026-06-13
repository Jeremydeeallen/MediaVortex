# Strip BUG-NNNN references from code

**Set:** 2026-06-13
**Status:** Active -- phase: IMPLEMENTING
**Slug:** strip-bug-ids-from-code

## Outcome

`grep -rn 'BUG-[0-9]\+' --include='*.py' --include='*.html' --include='*.js'` against the production tree returns zero hits. Slug-based anchors (`# see <slug>.<C|S|ST|W><N>`) replace them where the context-link adds value; pure-redundancy mentions delete outright. Documentation (`*.feature.md`, `*.flow.md`, `memory/*.md`, `deploy/*.md`, troubleshooting docs) keep BUG-NNNN references -- that's where the tracker lives.

## Why

Operator-facing log strings like `WARNING: BUG-0061: TranscodeAttempts INSERT could not resolve ProfileName` force the reader to context-switch to a bug tracker to understand the message. Logs should describe the problem in operator-actionable terms. Code anchors should point at the durable artifact (the feature/flow doc + criterion) that still exists after the bug is closed -- not the bug tracker ID that loses meaning after rotation.

## Acceptance Criteria

1. **Runtime code carries no BUG-NNNN references.** Verifiable: `grep -rEn 'BUG-[0-9]+' Features/ Core/ Scripts/ Templates/ WebService/ WorkerService/ Models/ Repositories/ Services/ Tests/ StartWorker.py StartMediaVortex.py StopMediaVortex.py 2>/dev/null` returns zero lines.

2. **Operator-facing log strings describe the problem, not the tracker ID.** No `WARNING: BUG-NNNN:` prefixes; the message itself names the failure.

3. **Documentation keeps tracker IDs.** `*.feature.md`, `*.flow.md`, `memory/*.md`, `deploy/*.md`, `*.troubleshooting.md` -- untouched.

4. **No behavior change.** Code paths and tests still execute identically; sweep is text-only.

## Out of Scope

- Pre-existing BUG-NNNN references in comments / docstrings of files I did not edit today *may* be left if they paraphrase historical context that the slug anchor doesn't cover -- judgment call per file.
- Migration script descriptions (e.g. `CleanupOrphanMvPairs.py` header explaining what BUG-0013 era files look like) -- these describe historical state the operator may need to recognize.

Practical approach: scrub the runtime log strings + my newly-introduced docstrings first (immediate operator value), then sweep the rest with edits that preserve meaning.

## Files

```
Features/Compliance/Models/ComplianceDecision.py
Features/Compliance/Repositories/ComplianceWriteRepository.py
Features/Compliance/Services/ComplianceRecomputeService.py   -- (if any)
Features/TranscodeJob/TranscodeJobRepository.py
Features/TranscodeQueue/QueueManagementBusinessService.py
Features/Activity/Models/ActiveJobRow.py
Features/Activity/Services/DashboardSnapshotService.py
Scripts/SQLScripts/AddActivityDashboardSettings.py
Scripts/SQLScripts/RemediateComplianceWritebackInvariant.py
Tests/Contract/TestComplianceWriteConsistency.py
+ Any pre-existing .py / .html / .js with BUG-NNNN (judgment-call per file)
```
