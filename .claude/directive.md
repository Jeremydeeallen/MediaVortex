# Current Directive

**Set:** 2026-10-10
**Status:** Active -- phase: IMPLEMENTING
**Slug:** long-filename-output
**Replaces:** `directives/closed/2026-10-10-auto-handoff.md` (closed Success)

## Outcome

The temporary name a job writes to while encoding ends in `.ip` instead of `.inprogress`. That is 8 characters shorter, so long multi-episode filenames no longer exceed the filesystem's 255-byte filename limit during an encode. Final filenames are unchanged. Backlog row 17. Operator 2026-10-10: "search and replace .inprogress with .ip".

## Acceptance Criteria

1. A source whose temporary output name was over 255 bytes with the old suffix and fits with the new one completes its stage. Verify: live run of MediaFiles 698773, 701679 (Transcode) and 699449 (Remux), which failed or would fail with `File name too long`.
2. No production code writes or expects the old suffix. Verify: `grep -rn "\.inprogress" --include=*.py Features Core Services Repositories WorkerService WebService Composition Models deploy` returns 0.
3. Final placed filenames are unchanged: `<name>-mv.mp4`. Verify: the live files above.

## Call-Graph Audit

- **Flow docs:** `transcode.flow.md` (ST6 encode, ST9 placement), `Features/QualityTesting/quality-test.flow.md`, `deploy/worker-deploy-baremetal.flow.md`. They name the suffix; no pair describes one operation.
- **Orchestration mode branches:** none added or touched.
- **Signal 5:** no flag.
- **Shared output columns:** none. `TemporaryFilePaths` stores the final path; the suffix is appended in code.
- **OOS categories:** below.

## Out of Scope

- (b) Old `.inprogress` files already on disk (leftovers from failed or duplicate runs). Code no longer recognises them; they are listed for the operator, not deleted.
- (b) The suffix literal stays repeated at each site (no shared constant); operator asked for a plain replace.
- (b) Closed directives, `memory/KNOWN-ISSUES*.md`, `memory/BUG-INDEX.md` keep the old word: they are history.

## Constraints

- Cut over only with an empty queue and no active jobs (nothing staged under the old suffix).

## Escalation Defaults

- Risk tolerance: medium.

## Engineering Calls Already Made

- Operator 2026-10-10: suffix is `.ip`; plain search and replace.

## Status

### Files

```
Features/TranscodeJob/Emit/OutputFilenameBuilder.py, Emit/CommandComposer.py
Features/TranscodeJob/ProcessTranscodeQueueService.py, LocalStagingService.py
Features/TranscodeJob/Worker/JobProcessor.py, Worker/LocalStagingAdapter.py, Worker/TemporaryFilePathsService.py
Features/FileReplacement/TranscodedOutputPlacement.py, FileReplacementBusinessService.py
Features/ServiceControl/CrashRecoveryService.py
Features/QualityTesting/QualityTestController.py, Disposition/DispositionDispatcher.py, Disposition/RetainInprogressPolicy.py
Features/AudioNormalization/Services/LanguageEnrichmentService.py
Services/FileManagerService.py
Tests/Contract/* and Tests/Pipeline/Harness/Backup.py that name the suffix
Scripts/SQLScripts/CleanupStaleInProgressFiles.py
Living *.feature.md / *.flow.md / DOMAIN.md / .claude/rules/worker-deploy.md that name the suffix
```

### Plan

One commit: replace the literal `.inprogress` with `.ip` in every file above. Deploy with the queue empty. Re-queue the three long-name files.

Seam changed:

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| Encode -> placement | `OutputFilenameBuilder` / `CommandComposer` | file on disk `<name>-mv.mp4.ip` | `TranscodedOutputPlacement.Execute`, `CrashRecoveryService`, scan exclusion all strip / match `.ip` | contract tests, live |

### Promotions

### Verification

### Decisions Made
