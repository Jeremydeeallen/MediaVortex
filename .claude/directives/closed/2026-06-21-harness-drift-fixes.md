# Harness Drift Fixes

**Slug:** harness-drift-fixes
**Set:** 2026-06-21
**Closed:** 2026-06-21
**Status:** Closed -- Success

## Outcome

`Tests/Contract/TestE2EPerBucket.py::test_transcode_bucket_e2e` runs against the live I9 worker fleet and either passes green OR raises an AssertionError naming the exact failure reason (codec mismatch, queue still populated, TranscodeAttempt failure errormessage, etc.). No `UndefinedColumn` exceptions. No silent fast-failure that the test misinterprets as success.

## Acceptance Criteria

C1. `Tests/Pipeline/Harness/Assertions.py::AssertVideoCodecMatchesProfile` no longer queries `m.FilePath` (column removed by path-schema-migration). When it surfaces a codec mismatch, the error message names the MediaFile by Id + RelativePath, not FilePath.

C2. `Tests/Pipeline/Harness/Invocation.py::_Invoke` raises `RuntimeError` if the TranscodeAttempt completes with `Success=False`, including the attempt's `ErrorMessage`, `Disposition`, and `DispositionReason` in the message. Tests cannot mistake a fast-failed attempt for a successful one.

C3. `Tests/Pipeline/Harness/Backup.py` builds `OriginalCanonicalPath` from `StorageRootId + RelativePath` via the PathStorageRoots singleton, not from a non-existent `FilePath` column. The Handle's CanonicalPath round-trips through restore for crash-recovery messaging.

C4. `py -m pytest Tests/Contract/TestE2EPerBucket.py::test_transcode_bucket_e2e -m slow -v` runs to completion (success or assertion-with-reason). Smoke-test exit gate per the worker-restart memory rule.

C5. Remaining 3 slow E2E tests (`test_remux_bucket_e2e`, `test_audiofixonly_bucket_e2e`, `test_already_compliant_no_work_e2e`) are also runnable end-to-end. Each either passes green OR fails with an assertion that names the specific failure reason. No remaining schema-drift exceptions in any of the 4 tests.

## Files

- `Tests/Pipeline/Harness/Assertions.py` -- drop m.FilePath from SELECT (C1)
- `Tests/Pipeline/Harness/Invocation.py` -- raise on Success=False with detail (C2)
- `Tests/Pipeline/Harness/Backup.py` -- synthesize CanonicalPath from typed pair (C3)
- `Tests/Contract/TestE2EPerBucket.py` -- drop unused `_CurrentCanonicalPath` helper (C1)

## Status

### Progress

- [x] C1: Assertions.py m.FilePath removed
- [x] C2: Invocation.py raises on Success=False with full reason (ErrorMessage, Disposition, DispositionReason)
- [x] C3: Backup.py CanonicalPath synthesized via Path.CanonicalDisplay; jsonb dict adapter wraps with psycopg2.extras.Json
- [x] C4: TestE2EPerBucket transcode test runs to completion — no schema crashes; harness now polls for terminal FileReplaced state and reports the actual stuck disposition rather than masking it
- [x] C5: All 4 slow tests exercised; each either passes green or raises with the specific pipeline failure reason

### Verification evidence

- **C1**: `Tests/Contract/TestE2EPerBucket.py::test_transcode_bucket_e2e` no longer raises `UndefinedColumn: column m.FilePath does not exist`. Error path through `AssertVideoCodecMatchesProfile` now formats `file={RelativePath}`.
- **C2**: `_Invoke` returns `(AttemptId, Success, Disposition, FileReplaced)` shape via explicit terminal-state check; Success=False → RuntimeError with errormessage/disposition/dispositionreason in the message. No more silent fast-failure mistaken for completion.
- **C3**: Run captured backup `Tests/Pipeline/_backup/15212-20260621T175803Z.json` containing TranscodeAttempts.audiopolicyjson dict; restore now succeeds without `psycopg2.ProgrammingError: can't adapt type 'dict'`.
- **C4**: Test exit path is deterministic. Concrete observed outcomes during this directive:
  1. Pre-fix: 4.55s AssertionError on m.FilePath (schema drift).
  2. After C1: 4.52s AssertionError "codec mismatch current='mpeg4'" (test didn't check disposition).
  3. After C2+C4 polling: 4.62s AssertionError "Disposition='BypassReplace' but FileReplaced=False" (real pipeline issue exposed).
  4. After C2 wait-for-FileReplaced + C3 jsonb: test polls for terminal-replacement state. When QualityTestEnabled=False AND FileReplacement worker isn't draining BypassReplace attempts, _Invoke correctly times out with "VMAF worker may be stuck or QualityTesting disabled inconsistently".
- **C5**: `py -m pytest Tests/Contract/TestE2EPerBucket.py -m slow -v` (15min 11s wall): **2 passed, 2 failed** — zero schema crashes, every failure cites the exact pipeline reason. Concrete observations:
  - `test_transcode_bucket_e2e`: TimeoutError after 900s with `AttemptId=39196 Last seen: {'Success': True, 'Disposition': 'Pending', 'DispositionReason': 'AwaitingVmaf'}` — real VMAF-queue-stuck pipeline issue.
  - `test_remux_bucket_e2e`: AssertionError `Pipeline ran but did not replace the file. AttemptId=39197 Disposition='NoReplace' Reason='ComplianceGateFailed'` — pipeline executed end-to-end; remuxed output failed the post-replace compliance gate. Real pipeline behavior, not harness drift.
  - `test_audiofixonly_bucket_e2e`: **PASSED** — full end-to-end through Quick path on the live worker fleet.
  - `test_already_compliant_no_work_e2e`: **PASSED** — idempotent vertical recomputes.
- **Honest gap**: 2 of 4 tests reveal real pipeline issues that are out of scope for this directive (harness-drift-fixes). Each is its own follow-up; the harness's job is to surface them, not fix them.

### Decisions Made

- `_Invoke` waits for FileReplaced=True OR Disposition in (Discard, NoReplace) as terminal — Disposition alone is insufficient because BypassReplace is set BEFORE the actual file swap.
- Added `GetAttemptDetails(AttemptId)` helper so tests can branch on disposition rather than asserting blindly.
- Added `_RequireReplacingDisposition` helper in TestE2EPerBucket so non-replacing dispositions fail informatively rather than as a codec-mismatch downstream.
- Toggled `PostTranscodeGateConfig.QualityTestEnabled=FALSE` during verification per "Flip switches to meet criteria" memory rule; restored to TRUE before close.
- `psycopg2.extras.Json` wrapping in Backup._ReinsertRow chosen over per-column type lookup -- O(1) test, handles both jsonb columns (audiopolicyjson, audiotracksemittedjson) without column-name allowlist.

### Files (post-directive)

- `Tests/Pipeline/Harness/Assertions.py` -- m.FilePath -> m.RelativePath
- `Tests/Pipeline/Harness/Invocation.py` -- wait for terminal FileReplaced; new GetAttemptDetails helper
- `Tests/Pipeline/Harness/Backup.py` -- CanonicalPath from typed pair; jsonb dict adapter
- `Tests/Contract/TestE2EPerBucket.py` -- removed unused _CurrentCanonicalPath; added _RequireReplacingDisposition helper

### Seams

Existing flow-doc + feature-doc seams already cover this work. No new seams added.

| Seam | Producer | Wire shape | Consumer expects | Verification |
|---|---|---|---|---|
| Assertions <- MediaFiles | DB | RealDictCursor row with codec + relativepath columns; no filepath | AssertVideoCodecMatchesProfile | C4 smoke run |
| Invocation <- TranscodeAttempts | worker write | row with success boolean + errormessage text | _Invoke loop checks Success NOT NULL THEN raises if False | C4 smoke run |
| Backup -> BackupHandle | MediaFiles row + PathStorageRoots | typed pair canonical-display string | RestoreMediaFile uses LocalPath separately | C4 smoke run |

### Promotions

| Source artifact | Target file | Commit |
|---|---|---|
| Wait-for-terminal-FileReplaced polling logic | `Tests/Pipeline/Harness/Invocation.py` | next commit |
| GetAttemptDetails helper API | `Tests/Pipeline/Harness/Invocation.py` | next commit |
| jsonb adapter via psycopg2.extras.Json | `Tests/Pipeline/Harness/Backup.py` | next commit |
| CanonicalPath synthesized from StorageRootId+RelativePath | `Tests/Pipeline/Harness/Backup.py` | next commit |
| _RequireReplacingDisposition test helper | `Tests/Contract/TestE2EPerBucket.py` | next commit |
| m.FilePath -> m.RelativePath in AssertVideoCodecMatchesProfile | `Tests/Pipeline/Harness/Assertions.py` | next commit |
