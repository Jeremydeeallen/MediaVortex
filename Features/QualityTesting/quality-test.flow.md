# Quality Test Flow

**Slug:** quality-test

Entry point: `Features/QualityTesting/ProcessQualityTestQueueService.py` (worker loop started by `WorkerService/Main.py._StartQualityTestCapability` when `Workers.QualityTestEnabled=TRUE`).

Quality Test is a sub-flow of `transcode.flow.md`. Admission is `transcode.ST7` (DISPOSITION) when `PostTranscodeDispositionDecider.Decide` returns `'Pending'` (`VMAF IS NULL` AND `QualityTestRequired=TRUE`). Completion re-enters `DispositionDispatcher.Dispatch` inside the same worker process; the second dispatch resolves to `Replace` / `Reject` / `Requeue` per the VMAF score against `PostTranscodeGateConfig` thresholds.

## Stage Overview

```
ADMIT -> CLAIM -> PROBE -> RUN_VMAF -> WRITE_VMAF -> REDISPATCH
 ST1     ST2      ST3       ST4        ST5           ST6
```

`ST1` is the boundary crossing FROM `transcode.ST7`. `ST6` is the boundary crossing BACK INTO `transcode.ST7` for terminal disposition. Everything between runs on a single WorkerService thread claimed by `ClaimQualityTestJob`.

---

## Seams

Stage-transition data contracts. Intra-feature seams live in `Features/QualityTesting/QualityTesting.feature.md`. The admission seam (S1) and the return seam (S6) are the two boundaries with `transcode.flow.md`.

| ID | Transition | Producer (writer) | Wire shape | Consumer (reader) expects | Verification |
|---|---|---|---|---|---|
| S1 | `transcode.ST7 -> quality-test.ST1` (ADMIT) | `DispositionDispatcher.Dispatch` -> `ProcessTranscodeQueueService.DispatchDisposition` -> `QualityTestQueueService.AddToQualityTestQueue` | `QualityTestingQueue.(Id BIGINT, TranscodeAttemptId BIGINT NOT NULL, OriginalFilePath TEXT, LocalSourcePath TEXT, TranscodedFilePath TEXT, Status='Pending', ForceDisposition IS NULL, DateAdded=NOW(), DateStarted IS NULL, ClaimedBy IS NULL)`; requires `TemporaryFilePaths` row with typed-pair `(SourceStorageRootId, SourceRelativePath, OutputStorageRootId, OutputRelativePath)` already written by ST6 | `QualityTestRepository.ClaimQualityTestJob` polls this row via the shared `BuildClaimPredicate` gate | `SELECT COUNT(*) FROM QualityTestingQueue WHERE Status='Pending'` increments by 1 per admission; `Tests/Contract/TestClaimAuthority.py::TestQualityTestClaimAuthority` |
| S2 | `ST1 -> ST2` (ADMIT -> CLAIM) | `ProcessQualityTestQueueService.ProcessQueueLoop` (polls every 2s) | `WorkerContext.Current().WorkerName` passed to `ClaimQualityTestJob` | `QualityTestRepository.ClaimQualityTestJob` atomically SELECT-then-UPDATE gated by `Workers.Status='Online' AND Workers.QualityTestEnabled=TRUE AND QualityTestingQueue.ForceDisposition IS NULL AND DateStarted IS NULL`; also checked against `FailureBudgetPredicate.BuildCapPredicate` on `ta.MediaFileId` | UPDATE sets `Status='Running', DateStarted=NOW(), ClaimedBy=<WorkerName>`; `Tests/Contract/TestClaimAuthority.py::test_paused_worker_refused / test_capability_false_refused / test_midflight_flip_honored_on_next_claim / test_force_disposition_row_invisible` |
| S3 | `ST2 -> ST3` (CLAIM -> PROBE) | `QualityTestingBusinessService.StartQualityTest` opens tracking rows: `QualityTestResults.(Status='Running', VMAFScore=0.0)`, `ActiveJobs.(ServiceName='QualityTestService', JobType='QualityTest', QueueId, ProcessId, ThreadId, WorkerName)`, `QualityTestProgress.(Status='Processing')` | `TemporaryFilePaths` typed pair `(SourceStorageRootId, SourceRelativePath, OutputStorageRootId, OutputRelativePath)` for the same `TranscodeAttemptId` | `QualityTestingBusinessService.BuildVMAFCommand` reads TFP row, projects to `Path.FromRow` with `Prefix="Source"` / `"Output"`, `Path.Resolve(Worker)` to worker-local absolute paths, `PathFs.Exists` gates both sides | `Tests/Contract/TestQualityTestPath.py` (path projection round-trip); `SELECT COUNT(*) FROM ActiveJobs WHERE ServiceName='QualityTestService' AND Status='Running'` matches worker's in-flight count |
| S4 | `ST3 -> ST4` (PROBE -> RUN_VMAF) | `QualityTestingBusinessService.BuildVMAFCommand` after `GetVideoResolution` on both files + `DetermineVMAFTargetResolution` + `_BuildVmafFilterChain` | ffmpeg argv string: `-i "<transcoded>" -i "<original>" -lavfi "<vmaf_filter with fps lock, PTS reset, lanczos scale, TV color range, 10-bit precision, libvmaf n_threads>" -f null -`; XML log path pinned to `vmaf_output.xml` | `QualityTestingBusinessService.ExecuteFFmpegWithProgress` spawns ffmpeg; `MonitorVMAFProgress` thread updates `QualityTestProgress.(CurrentFps, AverageFps, EtaSeconds, ProgressPercentage)` from stderr frame lines | `QualityTestResults.FFmpegCommand` populated pre-run for audit; process return code drives the branch |
| S5 | `ST4 -> ST5` (RUN_VMAF -> WRITE_VMAF) | ffmpeg process on rc==0 writes `vmaf_output.xml` | libvmaf XML with per-frame `metrics.vmaf` + `metrics.motion` values | `QualityTestingBusinessService.ParseVMAFMetrics` reads `Summary:` block, applies animation-aware motion=0 filter (see `memory/KNOWN-ISSUES.md` VMAF distribution), returns dict `{Mean, Min, Max, HarmonicMean, StdDev, P1, P5, P10, P25}` | `QualityTestingBusinessService.UpdateQualityTestResultsWithScore` writes `QualityTestResults.(VMAFScore, VMAFMin, VMAFMax, VMAFHarmonicMean, VMAFStdDev, VMAFP1..P25, PassesThreshold, Status='Success')`; `DatabaseManager.UpdateTranscodeAttempt` writes `TranscodeAttempts.(VMAF=<mean>, QualityTestCompleted=TRUE)`; `ActiveJobRepository.CompleteActiveJob(True)`; `QualityTestRepository.DeleteQualityTestQueueItem` removes the queue row |
| S6 | `ST5 -> transcode.ST7` (WRITE_VMAF -> REDISPATCH) | `QualityTestingBusinessService.BuildVMAFCommand` calls `self._BuildDispositionDispatcher().Dispatch(TranscodeAttemptId)` after VMAF write | `TranscodeAttempts.(VMAF DOUBLE PRECISION NOT NULL, QualityTestCompleted=TRUE, Disposition='Pending')` -- same row shape `transcode.S4` expects | `DispositionDispatcher.Dispatch` re-reads the row; `PostTranscodeDispositionDecider.Decide` now sees `VmafScore IS NOT NULL` and returns `Replace` when `VMAF >= VmafAutoReplaceMinThreshold`, `Requeue` when below, `Reject` on out-of-band cases. On `Replace` the same code path invokes `FileReplacementBusinessService(...).ProcessFileReplacement`; on `Requeue` it invokes `QualityTestingBusinessService._HandleRequeueDisposition` (delete staged `.inprogress`, `AddProblemFile('VmafBelowMin')`, delete TFP row) | Idempotent -- `DispositionDispatcher._CheckCachedDisposition` short-circuits if `Disposition` was already committed non-Pending; `Tests/Contract/TestDispositionDispatcher.py`; `SELECT COUNT(*) FROM TranscodeAttempts WHERE QualityTestCompleted=TRUE AND VMAF IS NULL` -> 0 |

---

## Stage 1: ADMIT -- Enqueue Pending Attempt (`ST1`)

**Trigger:** `transcode.ST7` (`DispositionDispatcher.Dispatch`) commits `Disposition='Pending'` for an attempt where `VMAF IS NULL AND QualityTestRequired=TRUE`.

**Code path:**
- `Features/TranscodeJob/ProcessTranscodeQueueService.DispatchDisposition` inspects the DispositionResult; on `Pending` it constructs `QualityTestQueueService(self.DatabaseManager)` and calls `AddToQualityTestQueue(TranscodeAttemptId)`.
- `Services/QualityTestQueueService.AddToQualityTestQueue`:
  1. `DatabaseManager.GetTranscodeAttemptById` -- refuses if attempt not `Success=TRUE`.
  2. `DatabaseManager.GetQualityTestQueue` in-memory filter for duplicate `TranscodeAttemptId` -- returns existing JobId if present.
  3. `DatabaseManager.GetTemporaryFilePath(TranscodeAttemptId)` -- refuses if no TFP row exists.
  4. `Path.FromRow(Prefix='Source' | 'Output')` -> `SourcePath.CanonicalDisplay(PrefixMap)` for `OriginalFilePath`, `SourcePath.Resolve(Worker)` for `LocalSourcePath`, `OutputPath.Resolve(Worker)` for `TranscodedFilePath`.
  5. `QualityTestRepository.CreateQualityTestQueueEntry` inserts the row with `Status='Pending', DateAdded=NOW(), DateStarted=NULL, DateCompleted=NULL`.

**Tables written:** `QualityTestingQueue` (one row per admitted attempt).

**Failure modes:** attempt not Success, TFP row missing, path resolution error -- all short-circuit with logged error; no queue row created. `DispositionDispatcher` had already committed `Disposition='Pending'` -- the attempt is invisible to Stage 7 downstream until an operator override lands on the (missing) queue row or `Scripts/AddLastTranscodeAttemptToQualityQueue.py` re-injects it.

---

## Stage 2: CLAIM -- Poll And Reserve (`ST2`)

**Trigger:** `ProcessQualityTestQueueService.ProcessQueueLoop` polls every 2s while `IsProcessing AND NOT StopRequested`.

**Code path:**
- `ClaimNextJob` reads `WorkerContext.Current().WorkerName` (refuses claim if unregistered).
- `QualityTestRepository.ClaimQualityTestJob(WorkerName)` builds two SQL fragments:
  - `WorkerCapabilityPredicate.BuildClaimPredicate(WorkerName, 'QualityTestEnabled')` -- gates on `Workers.Status='Online' AND Workers.QualityTestEnabled=TRUE`.
  - `FailureBudgetPredicate.BuildCapPredicate('ta.MediaFileId')` -- gates on the MediaFile's failure budget.
- SELECT joins `QualityTestingQueue` to `TranscodeAttempts`, filters `Status='Pending' AND ForceDisposition IS NULL AND DateStarted IS NULL` plus both predicates, `ORDER BY DateAdded ASC LIMIT 1`.
- Atomic UPDATE re-applies the capability predicate inside the WHERE so a mid-flight `QualityTestEnabled=FALSE` flip refuses the claim: `SET DateStarted=NOW(), Status='Running', ClaimedBy=<WorkerName>`.

**DB is authority:** the SQL fragment is the single control plane -- no cached capability state in `ProcessQualityTestQueueService`. See `.claude/rules/db-is-authority.md`.

**Tables written:** `QualityTestingQueue.(DateStarted, Status='Running', ClaimedBy)`.

---

## Stage 3: PROBE -- Open Tracking + Resolve Paths (`ST3`)

**Trigger:** `ClaimNextJob` returned a job dict; `ProcessQueueLoop` spawns `ProcessJob(job)` in a daemon thread, which calls `QualityTestingBusinessService.ProcessClaimedJob` -> `StartQualityTest(JobId)`.

**Code path:**
- `StartQualityTest`:
  1. `DatabaseManager.CreateQualityTestResult(TranscodeAttemptId, Status='Running')` -> row in `QualityTestResults` with `VMAFScore=0.0` placeholder.
  2. `ActiveJobRepository.CreateActiveJob(ServiceName='QualityTestService', JobType='QualityTest', QueueId=JobId, ProcessId, ThreadId, WorkerName)` -> row in `ActiveJobs` for operator visibility.
  3. `CreateProgressRecord(JobId, job_details)` -> row in `QualityTestProgress`.
- `BuildVMAFCommand`:
  - Reads `TemporaryFilePaths` typed-pair columns for the `TranscodeAttemptId`.
  - `Path.FromRow` + `Path.Resolve(Worker)` translate canonical to worker-local absolute paths; `PathFs.Exists` refuses if either side is missing.
  - `WorkerContext.Current().FFmpegPath` supplies the ffmpeg binary; refused if unset.
  - `GetVideoResolution(original)` and `GetVideoResolution(transcoded)` via ffprobe.

**Tables written:** `QualityTestResults` (Running placeholder), `ActiveJobs`, `QualityTestProgress`.

---

## Stage 4: RUN_VMAF -- Execute libvmaf (`ST4`)

**Trigger:** `BuildVMAFCommand` finished command assembly.

**Code path:**
- `DetermineVMAFTargetResolution(original, transcoded)` -- compares max-edge, picks the smaller side; both feeds are scaled to that target via lanczos.
- ffprobe reads `stream=avg_frame_rate` on the source; falls back to 24 fps on parse failure.
- `_BuildVmafFilterChain(SourceFps, TargetWidth, TargetHeight, 'vmaf_output.xml', NThreads=4)` -- single source of truth for the libvmaf filter chain, shared with `RunLocalVmafForAttempt` (Mode A). Layout: fps lock, PTS reset, lanczos scale, TV color range pin, 10-bit precision, libvmaf `n_threads=4`.
- Input order pinned: `-i "<transcoded>" -i "<original>"` -- transcoded becomes `[0:v]->[dist]`, original becomes `[1:v]->[ref]`. See `QualityTesting.feature.md` C11c.
- Optional `-ss <StartTime>` from `TranscodeAttempts.StartTime`.
- `QualityTestResults.FFmpegCommand` populated pre-run for audit.
- `ExecuteFFmpegWithProgress(command, ProgressId, JobDetails)` spawns ffmpeg; `MonitorVMAFProgress` thread parses stderr `frame=` lines and updates `QualityTestProgress.(CurrentFps, AverageFps, EtaSeconds, ProgressPercentage, CurrentStep)`.

**Tables written:** `QualityTestResults.FFmpegCommand`, continuous `QualityTestProgress` updates.

---

## Stage 5: WRITE_VMAF -- Parse XML And Persist Score (`ST5`)

**Trigger:** ffmpeg exits with `returncode == 0`.

**Code path:**
- `ParseVMAFMetrics('vmaf_output.xml')`:
  - `rfind('Summary:')` anchors parsing to the Summary block (avoids catching the silence-floor progress lines).
  - Reads per-frame `metrics.vmaf` + `metrics.motion`; drops frames where `motion == 0` (animation duplicate-frame masking). See `memory/KNOWN-ISSUES.md` "VMAF distribution".
  - Returns dict `{Mean, Min, Max, HarmonicMean, StdDev, P1, P5, P10, P25}`; Mean falls back to 0.0 on parse failure.
- `UpdateQualityTestResultsWithScore(result_id, vmaf_score, ffmpeg_result, metrics)`:
  - `PassesThreshold = (VmafAutoReplaceMinThreshold <= VMAFScore <= VmafAutoReplaceMaxThreshold)`.
  - UPDATE `QualityTestResults.(VMAFScore, VMAFMin, VMAFMax, VMAFHarmonicMean, VMAFStdDev, VMAFP1..P25, PassesThreshold, Status='Success', TestDuration)`.
- `DatabaseManager.UpdateTranscodeAttempt(ta_id, {VMAF: vmaf_score, QualityTestCompleted: True})`.
- `_AutoCaptureStillsIfPolicyFires(ta_id)` -- opportunistic still capture on policy match (non-fatal on failure).
- `ActiveJobRepository.CompleteActiveJob(active_job_id, True)`.
- `finally:` `DatabaseManager.DeleteQualityTestQueueItem(JobId)` -- the QT queue row is a revolving door; success or failure, the row is deleted here.

On ffmpeg `returncode != 0` or exception: `UpdateQualityTestResultFailure(result_id, error)`, `UpdateProgressRecord(Failed)`, `ActiveJobRepository.CompleteActiveJob(False, error)`, `_CleanupTemporaryFilePathsForVmafFailure(ta_id)`, `DeleteQualityTestQueueItem` in `finally`. No redispatch fires on failure -- `TranscodeAttempts.Disposition` stays `'Pending'` and the attempt is orphaned until an operator or `GetMissedQualityTests` re-injects it.

**Tables written:** `QualityTestResults` (final row), `TranscodeAttempts.(VMAF, QualityTestCompleted)`, `ActiveJobs.Status='Completed'`, `QualityTestingQueue` (row deleted).

---

## Stage 6: REDISPATCH -- Return To Transcode Disposition (`ST6`)

**Trigger:** `BuildVMAFCommand` on ffmpeg success, after `UpdateTranscodeAttempt` writes the score.

**Code path:**
- `self._BuildDispositionDispatcher().Dispatch(ta_id)` -- constructs a fresh `DispositionDispatcher` with default deps and re-enters `transcode.ST7`.
- `DispositionDispatcher._CheckCachedDisposition` sees `Disposition='Pending'` (not committed as a terminal), proceeds to `_BuildDeciderInput` + `_BuildGateInput`.
- `PostTranscodeDispositionDecider.Decide` now has `VmafScore IS NOT NULL`:
  - `VMAF >= VmafAutoReplaceMinThreshold AND VMAF <= VmafAutoReplaceMaxThreshold` -> `Replace`.
  - `VMAF < VmafAutoReplaceMinThreshold` -> `Requeue`.
  - Out-of-band cases (e.g. compliance fail, size regression) -> `Reject` per the gate table.
- `_CommitDisposition` writes `TranscodeAttempts.(Disposition, DispositionReason, DispositionDecidedAt)`.
- `BuildVMAFCommand` branches on the returned `DispositionResult.Disposition`:
  - `Replace` -> `FileReplacementBusinessService(...).ProcessFileReplacement(ta_id)` synchronously (`AutoReplaceTriggered=True`).
  - `Requeue` -> `_HandleRequeueDisposition(ta_id, AuditPayload)`: delete the staged `.inprogress` via `Path.FromLegacyString.Resolve(Worker)`, `AddProblemFile('VmafBelowMin', ...)`, DELETE the `TemporaryFilePaths` row.
  - `Reject` -> no filesystem action; `.inprogress` sits until `RetainInprogressPolicy` cleanup runs.

**Idempotency:** re-entering `Dispatch` on a row that already has a non-Pending Disposition returns the cached result and does nothing else. See `DispositionDispatcher._CheckCachedDisposition`.

**Tables written:** `TranscodeAttempts.(Disposition, DispositionReason, DispositionDecidedAt)`; downstream side effects belong to `transcode.ST9`.

---

## Operator override sub-path

Operator can bypass this flow entirely via `POST /api/QualityTest/Override` (see `Features/QualityTesting/qt-queue-visibility-and-override.feature.md` C4 + `transcode.flow.md ST8`). The WebService sets `QualityTestingQueue.ForceDisposition IN ('Replace', 'Reject')` and drives disposition + FileReplacement synchronously. `ClaimQualityTestJob` filters `ForceDisposition IS NULL`, so a worker cannot race an override row.

## Related contracts

- `.claude/rules/db-is-authority.md` -- `ClaimQualityTestJob` invariant.
- `.claude/rules/flow-docs.md` -- this doc's shape.
- `transcode.flow.md` -- ST7 (admission), ST9 (post-redispatch action), S3/S4 seams.
- `Features/QualityTesting/QualityTesting.feature.md` -- intra-feature seams (filter chain, resolution policy, still capture).
- `Features/QualityTesting/post-transcode-disposition.feature.md` -- Decider + Dispatcher contract.
- `Features/QualityTesting/qt-queue-visibility-and-override.feature.md` -- operator override + queue visibility.
