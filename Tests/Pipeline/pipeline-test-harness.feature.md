# Pipeline Test Harness -- end-to-end verification of the pipeline stages

**Slug:** pipeline-test-harness

## Interrupts: audio-dialog-boost-real (successor to linear-loudnorm)

## What It Does

Provides a `pytest`-runnable harness that drives real MediaFile rows
through the actual pipeline on the I9 worker, asserting state at every
stage. What each job label does to a file and how stages chain is
defined by `transcode.flow.md` D2 (buckets: D4); the harness asserts
against that and does not restate it.

The harness backs up the source file and DB state before each test,
runs the pipeline, asserts every observable, then restores everything
on success or failure. Tests are idempotent and self-cleaning.

This is a **regression-grade** harness, not a one-shot script: the
primitives are reusable for any future end-to-end test (corrupt-file negative test, multi-language audio file, etc.)
without harness rewrites.

## Concern

Five concerns this feature resolves:

1. **No end-to-end verification of the pipeline today.** `Tests/Contract`
   exercises individual repositories against the live DB.
   `Scripts/Smoke` exists for one-off checks. Nothing drives a real
   MediaFile through the actual pipeline and asserts the full
   contract from `audio-completion.feature.md` criterion 25,
   and `Features/AudioNormalization/audio-normalization.feature.md`
   C36 + C37 (linear-mode two-pass + single audio emit path). We have been shipping these
   features without a regression-grade test.
2. **Manual verification doesn't scale.** Each release re-derives the
   same probe sequence (run a file, check the DB, check ffprobe output,
   check Jellyfin) by hand. That's a runbook tax we pay every release.
3. **Cleanup is the hard part.** A pipeline test mutates a real file
   AND multiple DB tables (MediaFiles, TranscodeAttempts,
   TranscodeQueue, MediaFilesArchive, TemporaryFilePaths). Without
   automated backup/restore, a failed test leaves the library in an
   inconsistent state -- which is why ad-hoc manual tests stopped
   getting run.
4. **Jellyfin notify verification needs first-class support.** The
   JELLYFIN_NOTIFY_DRY_RUN mode exists but is invoked ad-hoc; the
   harness wraps it as a primitive so every test asserts the notify
   payload without ever hitting Jellyfin.
5. **Feature criteria reference observable behavior, not internal
   code paths.** Those observables are exactly what a test harness
   should assert. Restating each criterion as a pytest assertion
   keeps the spec and the verification mechanically aligned.

## Surface

Developer-facing only. The "surface" is:

- `pytest Tests/Pipeline/` runs all pipeline tests
- `pytest Tests/Pipeline/test_quickfix_then_transcode.py -v` runs the first scenario verbosely
- `pytest Tests/Pipeline/test_transcode_dual_pipeline.py -v` runs the second
- `pytest --collect-only Tests/Pipeline/` enumerates without running
- Test output is standard pytest -- `.` per test, `F` on failure with a
  diff between expected and observed state
- Tests must be runnable from the I9 with WebService stopped (the
  harness manages WorkerContext and FFmpeg paths internally; it does
  not require the daemon to be up)

No production surface. Not exposed via WebService or any UI.

## Success Criteria

### A. Harness primitives -- file + DB backup/restore

1. `Harness/Backup.py` exposes `BackupMediaFile(MediaFileId) -> BackupHandle`
   that captures: the file at `MediaFiles.FilePath` (translated to local
   path), the `MediaFiles` row, every `TranscodeAttempts` row for the
   file, every `TranscodeQueue` row, every `MediaFilesArchive` row, and
   every `TemporaryFilePaths` row. Returns a `BackupHandle` containing
   the on-disk backup file path and serialized DB row state. Verifiable:
   call `BackupMediaFile` on a known row; the returned handle's
   recorded column values match a fresh `SELECT *` of the same row.

2. `Harness/Backup.RestoreMediaFile(BackupHandle) -> None` rewinds:
   restores the file content byte-for-byte at the original path,
   `DELETE` + `INSERT`s each captured DB row back to its pre-test
   values, and removes any rows the test created that weren't in the
   backup. Verifiable: backup -> mutate columns AND swap the file ->
   restore -> assert columns match backup AND `sha256(file)` matches
   backup.

3. Backup files live under `Tests/Pipeline/_backup/` and are named
   `<MediaFileId>-<timestamp>.bin`. Pre-existing backups for the same
   MediaFileId are preserved (suffix collision resolved by timestamp)
   so concurrent or repeated test runs don't overwrite each other.
   Verifiable: run the harness twice; both backup files persist on
   disk under distinct names.

### B. Harness primitives -- pipeline invocation

5. `Harness/Invocation.InvokeTranscode(MediaFileId) -> TranscodeAttemptId`
   runs a `Transcode` job synchronously. Returns the resulting
   `TranscodeAttempts.Id`. Blocks until completion or raises with the
   failure reason. Verifiable: call against a file whose
   `WorkBucket='Transcode'`; observe a TranscodeAttemptId returned and
   the file's video codec matches the assigned profile post-call.

6. Invocation helpers initialize `WorkerContext` for `I9-2024`
   from `Workers` + `WorkerShareMappings` if not already initialized.
   They do not assume WebService or WorkerService daemons are up.
   Verifiable: with WebService stopped (`Get-NetTCPConnection -LocalPort 5000`
   returns empty), `InvokeTranscode` still completes a real job.

7. Invocation helpers refuse to run when the file has an existing
   `TranscodeQueue` row or `ActiveJobs` row referencing it -- they
   raise `PipelineBusyError` with the conflicting row id. Verifiable:
   insert a TranscodeQueue row for the test file; call
   `InvokeTranscode`; observe the named exception.

### C. Harness primitives -- assertions

8. `Harness/Assertions.AssertIntegratedLoudnessNear(FilePath,
   TargetLufs, ToleranceLU=1.0, AudioStreamIndex=0) -> None` runs
   ebur128 against the file, parses Integrated, raises `AssertionError`
   with measured/expected values if out of tolerance. Verifiable:
   call on a known -23 LUFS file with TargetLufs=-23 -- passes; call
   with TargetLufs=-15 -- fails with named delta.

9. `Harness/Assertions.AssertAudioBytesIdentical(PathA, PathB,
   AudioStreamIndex=0) -> None` extracts each file's audio stream via
   `ffmpeg -map 0:a:N -c copy -f data -` and SHA-256 hashes the
   bytes; raises if hashes differ. Verifiable: call on (A, A); passes.
   Call on (A, B-where-B-was-re-encoded); fails with the two hashes
   in the message.

10. `Harness/Assertions.AssertDbState(MediaFileId, **expected) -> None`
    queries `MediaFiles WHERE Id = MediaFileId`, iterates the keyword
    arguments, raises if any column does not match. Verifiable: pass
    `AudioComplete=True` for a known-true row; passes. Pass
    `AudioComplete=False` for the same row; fails with `expected=False,
    actual=True`.

11. `Harness/Assertions.AssertNoQueueRows(MediaFileId) -> None` asserts
    `TranscodeQueue` has zero rows for the MediaFileId AND the file is
    no longer in a work bucket (`MediaFiles.WorkBucket`; rules in
    `transcode.flow.md` D4). Verifiable: insert one
    TranscodeQueue row; call; observe failure naming the table.
    Remove it; call; passes.

12. `Harness/Assertions.AssertVideoCodecMatchesProfile(MediaFileId)
    -> None` reads the file's current video codec via ffprobe and
    compares against the codec from `Profiles WHERE ProfileName =
    MediaFiles.AssignedProfile`. Verifiable: call on a file with
    AssignedProfile pointing at `libsvtav1` and actual codec av1 --
    passes; mutate to a profile expecting `libx265` -- fails.

### D. Harness primitives -- Jellyfin notify verification

13. `Harness/JellyfinVerify.py` exposes `CaptureNotifyEvents() -> NotifyCapture`
    that enables `JELLYFIN_NOTIFY_DRY_RUN=1` SystemSettings (saves the
    prior value), and `NotifyCapture.Stop()` restores it. While
    active, all `NotifyJellyfin` invocations write their payload to
    a capture buffer (an in-memory ring or to a file under
    `Tests/Pipeline/_jellyfin_capture/`). Verifiable: start a
    capture; trigger a file replacement; stop capture; assert the
    buffer has exactly one notify entry naming the replaced path.

14. `Harness/JellyfinVerify.AssertNotifyFired(Capture,
    CanonicalPath, UpdateType, since_ts=None) -> None` asserts at
    least one entry in the capture matches the canonical path and
    update type. `since_ts` allows scoping to events after a given
    moment. Verifiable: capture a known notify; call with the
    matching path and `UpdateType='Modified'`; passes. Call with
    `UpdateType='Deleted'`; fails.

### E. Test fixtures and registry

15. `Harness/Fixtures.py` exposes a registry of stable test file
    candidates by intent:
    - `TranscodeCandidate(MaxSizeMB=500)` -- returns a MediaFile.Id
      whose `WorkBucket='Transcode'` and is under the size limit
    - `RemuxCandidate(MaxSizeMB=500)` -- returns a MediaFile.Id whose
      `WorkBucket='Remux'` and is under the size limit
    - `AlreadyCompliant()` -- returns a MediaFile.Id with
      `IsCompliant=true, AudioComplete=true` for negative-test purposes
    Selection is data-driven (queries the live DB); the registry
    refuses to return suspect or sub-floor files. Verifiable: each
    function returns an integer that resolves to a real MediaFiles
    row matching the stated intent.

16. Fixture functions cache their selection within a pytest session
    via `pytest fixtures` so the same file is used across asserts
    within one test run, but a fresh session picks a fresh file
    (in case the prior file's state was mutated by a non-rolled-back
    failure). Verifiable: run the same test twice in one session;
    the same MediaFileId is used. Run again in a new session; a
    different (or same, if still eligible) MediaFileId is selected.

### H. Pytest integration and discipline

19. `Tests/Pipeline/conftest.py` provides shared fixtures: a
    session-scoped DB connection, a session-scoped `WorkerContext`
    initialization, and a function-scoped Jellyfin capture wrapper.
    Verifiable: `pytest --collect-only Tests/Pipeline/` lists both
    test cases with their full IDs and no collection errors.

20. Each test uses a `try/finally` (or pytest finalizer fixture)
    that runs `RestoreMediaFile` and `capture.Stop()` regardless of
    pass or fail. Verifiable: deliberately fail an assertion mid-test;
    confirm the file on disk and the DB row are still restored when
    pytest exits.

21. Tests are idempotent. Running `pytest Tests/Pipeline/` three
    times back to back produces the same pass/fail result. Verifiable:
    run three times; observe identical exit codes and test output
    summaries.

22. The harness gates itself on a precondition check at session
    setup -- if the live DB has fewer than N rows matching each
    fixture's candidate criteria (default N=1), the session aborts
    with a clear "no test candidates" message rather than running
    against an empty fixture pool. Verifiable: temporarily filter
    the registry to require an impossible candidate; observe a
    clean abort with an actionable error.

## Status

Harness primitives IMPLEMENTED 2026-05-25. The two test modules under `Tests/Pipeline/` and the `InvokeQuickFix` / `QuickFixCandidate` / `AudioFixOnlyCandidate` helpers were written before `transcode.flow.md` D2 and have not yet been re-pointed at the three job labels; they carry no criteria here until they are.

### Progress

- [x] Stack pivot from historic `linear-loudnorm` directive (content absorbed into `audio-normalization.feature.md` C36); tree was clean, no pause commit
- [x] Feature doc (this file) drafted with PIVOT marker
- [x] Operator approved (2026-05-24)
- [x] Step 1: Tests/Pipeline/ directory + __init__.py + .gitignore exclusions for _backup/_jellyfin_capture
- [x] Step 2: Harness/Backup.py (BackupHandle dataclass + BackupMediaFile + RestoreMediaFile + DiscardBackup + LoadBackupHandle). Live round-trip verified non-destructive (MediaFile 26621, SHA matches pre/post).
- [x] Step 3: Harness/Invocation.py (InvokeQuickFix, InvokeTranscode, _EnsureWorkerContext, _AssertNoActiveWork, PipelineBusyError). Wiring uses real TranscodeQueue insert + ProcessTranscodeQueueService.ProcessJob.
- [x] Step 4: Harness/Assertions.py (AssertIntegratedLoudnessNear, AssertTruePeakAtOrBelow, AssertAudioBytesIdentical, AudioStreamHash, AssertDbState, AssertNoQueueRows, AssertVideoCodecMatchesProfile)
- [x] Step 5: Harness/JellyfinVerify.py (CaptureNotifyEvents intercepts NotifyJellyfin; AssertNotifyFired). Context-manager compatible, restores SystemSettings on Stop.
- [x] Step 6: Harness/Fixtures.py (QuickFixCandidate -> Id=26621, TranscodeCandidate -> Id=108159 live-verified, AlreadyCompliant, NoCandidatesError)
- [x] Step 7: conftest.py (worker_context session fixture, precondition_gate session fixture, notify_capture per-test fixture)
- [x] Step 8: test_quickfix_then_transcode.py
- [x] Step 9: test_transcode_dual_pipeline.py
- [x] Step 10: Live run on real candidates. Iteration 1 surfaced 6 harness bugs + 4 production bugs (filed as BUG-0014..BUG-0017, plus BUG-0013 resolved). Iteration 2 GREEN: test_quickfix_then_transcode_preserves_audio passes in 294s; test_transcode_dual_pipeline passes in 160s. Step 2 of test 1 restructured to assert against the emitted FFmpeg command (TranscodeAttempts.FfpmpegCommand) rather than post-encode file state -- the contract is "Transcode emits -c:a copy when AudioComplete=true" which is verifiable without requiring a successful replacement (defense-in-depth refuses replacement when AV1 output > source size, which is correct production behavior).
- [x] Step 11: Idempotency confirmed via back-to-back `pytest Tests/Pipeline/` run -- 2 passed in 401s. Initial back-to-back attempt revealed a sweep bug (Transcode outputs at a DIFFERENT resolution from the source weren't caught by the orphan sweep); fixed by stripping the trailing `-<digits>p` resolution tag from the stem before prefix-matching. Re-run after fix: both tests pass consecutively against the same candidates without manual cleanup.

## Scope

```
Tests/Pipeline/pipeline-test-harness.feature.md         -- (THIS FILE)
Tests/Pipeline/__init__.py                              -- (NEW)
Tests/Pipeline/conftest.py                              -- (NEW) shared fixtures
Tests/Pipeline/Harness/__init__.py                      -- (NEW)
Tests/Pipeline/Harness/Backup.py                        -- (NEW) BackupMediaFile / RestoreMediaFile / BackupHandle
Tests/Pipeline/Harness/Invocation.py                    -- (NEW) InvokeQuickFix / InvokeTranscode / PipelineBusyError
Tests/Pipeline/Harness/Assertions.py                    -- (NEW) DB + file + loudness asserts
Tests/Pipeline/Harness/JellyfinVerify.py                -- (NEW) Notify-capture wrapper
Tests/Pipeline/Harness/Fixtures.py                      -- (NEW) Test file registry
Tests/Pipeline/test_quickfix_then_transcode.py          -- (NEW) Test case 1
Tests/Pipeline/test_transcode_dual_pipeline.py          -- (NEW) Test case 2
Tests/Pipeline/_backup/.gitkeep                         -- (NEW) Backup-file directory marker
Tests/Pipeline/_jellyfin_capture/.gitkeep               -- (NEW) Capture-file directory marker
.gitignore                                              -- Exclude Tests/Pipeline/_backup/* and _jellyfin_capture/*
```

## Files

| File | Role |
|------|------|
| Feature doc (this file) | Contract |
| `Tests/Pipeline/conftest.py` | Pytest fixtures: DB connection, WorkerContext, capture wrapper, precondition gate |
| `Tests/Pipeline/Harness/Backup.py` | File + DB row backup/restore; `BackupHandle` dataclass |
| `Tests/Pipeline/Harness/Invocation.py` | Synchronous pipeline invocations |
| `Tests/Pipeline/Harness/Assertions.py` | Reusable assertion helpers for DB, file, and audio state |
| `Tests/Pipeline/Harness/JellyfinVerify.py` | Notify-capture: monkey-patches `JellyfinNotifyService.NotifyJellyfin` so tests record payloads without POSTing |
| `Tests/Pipeline/Harness/Fixtures.py` | Test file registry |
| `Tests/Pipeline/test_quickfix_then_transcode.py` | Test module 1 |
| `Tests/Pipeline/test_transcode_dual_pipeline.py` | Test module 2 |

## Deviation from conventions

- **New test directory layout (`Tests/Pipeline/`).** The existing
  convention has `Tests/Contract/` for repository-level DB tests and
  `Tests/Integration/` for in-process service tests. Neither fits an
  end-to-end harness that drives real files through the actual
  pipeline. Creating `Tests/Pipeline/` makes the intent explicit; a
  reviewer looking for "what regression coverage do we have for the
  full pipeline" finds it in one place rather than buried in the
  Integration subtree.
- **Backup files live in `Tests/Pipeline/_backup/`, gitignored.**
  These are temporary on-disk artifacts (real media files copied
  before mutation). Storing them in-repo makes recovery from a
  crashed test trivial (no temp-path guessing) but they must NOT
  be committed -- enforced via `.gitignore`.
- **Harness mutates production data temporarily.** Test cases operate
  on real `MediaFiles` rows from the live library (selected by the
  fixture registry). Every test backs up before mutation and restores
  after -- but a hard crash mid-test (power loss, kernel OOM) leaves
  the row mutated. Mitigation: backup-file naming includes a timestamp
  so manual recovery is straightforward, and the file `_backup/`
  directory is treated as a recoverable spool. A future hardening
  iteration could move tests to a dedicated test-library subtree.
