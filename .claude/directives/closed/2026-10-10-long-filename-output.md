# Current Directive

**Set:** 2026-10-10
**Status:** Closed 2026-10-10
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

| Source artifact | Target file |
|---|---|
| In-flight suffix is `.ip`; same-slot backup suffix is `.bak` | `transcode.flow.md` (ST6, ST9 steps 5-7), `WorkerService/worker-lifecycle.feature.md`, `Features/FileReplacement/transcoded-output-placement.feature.md`, `Features/TranscodeJob/local-staging.feature.md`, `.claude/rules/worker-deploy.md`, and the 16 other living docs that named the old suffix (same commit as the code) |

### Verification

- **Commits:** `3fef5d2f` (`.inprogress` -> `.ip`), `dd3bb783` (`.replacing.bak` -> `.bak`). Pushed. Fleet on `dd3bb783`, 9 workers OK.
- **Tests:** naming, placement, staging, disposition, hand-off suites 103/103; placement + hand-off 24/24 after the backup change. Claim tests not run (they take live queue rows).
- **2:** production grep for the old suffix returns 0.
- **1 + 3, live on wakko-worker-1 2026-10-10 (UTC):**
  - 701679 Bullwinkle S01E126-E130 (source name 239 bytes, 17 prior `File name too long` failures): attempt 99811 Transcode placed 19:30:53; hand-off queued Audio; attempt 99816 AudioFix placed 20:17:36. Compliant on all three dimensions. Final name 246 bytes, ends `DVD480p-mv.mp4`.
  - 699449 Interspecies Reviewers S01E10 (243 bytes): attempt 99812 Remux placed 19:31:07; hand-off queued Audio; attempt 99815 AudioFix placed 20:07:04. Compliant. Final name 246 bytes, ends `Bluray-1080p-mv.mp4`.
  - 698773 Greatest American Hero S01E01-E08 (246 bytes): attempt 99810 encoded to `...-mv.mp4.ip` without a filename error; rejected `InsufficientSavings_13pct_below_20pct`, so not placed. The filename failure is gone; what remains is the savings rule (backlog row 22).
- **Found on the way:** the first Audio attempts on the two placed files (99813, 99814) failed renaming the in-place backup: `<name>-mv.mp4.replacing.bak` is 260 bytes. Fixed by `dd3bb783`; the re-runs above passed.
- **Not caused by this change:** dot's GPU became unusable after an OS auto-update of the NVIDIA libraries at 06:03 local 2026-10-10 (library 595.99.02 vs loaded kernel module 595.84); the deploy restart exposed it. dot-worker-1 is Paused until the host is rebooted (backlog row 24).
- **Left on disk:** 27 old `.inprogress` files on `T:\` (about 14 GB, July-October), listed to the operator, not deleted.

### Decisions Made

- Plain literal replace, no shared constant, as the operator asked.
- The same-slot backup suffix was shortened too: without it a long-named file passes its first stage and fails every later one.
- Source filenames were not renamed; all three fit once the suffixes shrank.
- `Scripts/SQLScripts/CleanupStaleInProgressFiles.py` still targets the old suffix: it is the tool for the leftovers.
- Three multi-line docstrings on edited lines were collapsed to one line (R12).
