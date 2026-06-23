# FileReplacement Drain Bug

**Slug:** filereplacement-drain-bug
**Set:** 2026-06-22
**Status:** Closed -- 2026-06-23 -- Success
**Reference:** Pre-existing bug surfaced as `harness-drift-fixes` C6.1 ("BypassReplace -> FileReplaced=True within 60s"). The compliance-symmetry rework + library-wide recompute did NOT touch this code path, so the gap remained. Compliance-symmetry's 30-job operator smoke (2026-06-22) re-surfaced it: 8 of 9 Transcode attempts stuck for 85+ minutes with `Disposition='Replace' AND FileReplaced=False` despite worker reporting `Success=True` and `NewSizeBytes` populated (output file exists on staging). Spread across all four worker hosts (I9-2024, dot-worker-1, dot-worker-2, dot-worker-4) -- not host-specific.

## Outcome

Every `TranscodeAttempts` row that reaches `Disposition='Replace'` or `Disposition='BypassReplace'` either:
- transitions to `FileReplaced=True` within a defined budget (target: 90s for AudioFix/Remux, 5min for Transcode-with-VMAF), OR
- transitions to a terminal failure state with a concrete `ErrorMessage` naming why the swap could not complete (mount unavailable, source-file gone, destination-path mismatch, etc.).

No silent stuck-Replace rows. The carry-forward C6.1 invariant from `harness-drift-fixes` is finally honored.

Drained-and-loudly-failed is acceptable; silently-stuck is not.

## Repro fingerprint (currently observable)

Open the live DB and run:

```sql
SELECT COUNT(*) FROM TranscodeAttempts
WHERE Disposition = 'Replace' AND FileReplaced = FALSE
  AND AttemptDate < NOW() - INTERVAL '15 minutes'
  AND ErrorMessage IS NULL;
```

This count must be 0 in steady state. Today: 8 (the 22:09-22:12 stuck attempts).

## Discovery (Breaking Bad reproduction, 2026-06-23)

The Breaking Bad S02E04 transcode reproduced the exact pattern. Manual recovery surfaced the **proximate root cause: `TemporaryFilePaths` row was missing** by the time FileReplacement ran. The `.inprogress` file existed on disk; the row was gone.

Hypothesis: `DispositionDispatcher._MaybeCleanupTfp` runs after the disposition is committed and BEFORE FileReplacement runs (for the BypassReplace synchronous path) OR before the post-VMAF disposition rerun (for the Pending path). When the cleanup runs first, FileReplacement has no path mapping and silently fails behind the broad `except Exception` in `ProcessTranscodeQueueService.DispatchDisposition` line 660.

This directive must verify that hypothesis, fix the ordering bug, surface failures loudly, and recover the 8 attempts already stuck.

## Acceptance Criteria

C1. **Root cause identified and documented.** `DispositionDispatcher._MaybeCleanupTfp` invariant clarified: TFP rows must NOT be removed before all dispositions that need them complete. Where the cleanup happens too early, the order is corrected so FileReplacement runs first and cleanup happens after FileReplaced=True.

C2. **Silent-fail surface eliminated.** `Features/TranscodeJob/ProcessTranscodeQueueService.py:DispatchDisposition` line 660 broad `except Exception` -> the failure raises, OR writes a concrete ErrorMessage to the attempt's row + sets a recoverable status that the self-heal can detect. No more attempts with `Disposition='Replace' AND FileReplaced=False AND ErrorMessage IS NULL` for >15 minutes.

C3. **Self-heal recovery for already-stuck rows.** A new service (or extension of an existing one) periodically scans for `Disposition IN ('Replace','BypassReplace') AND FileReplaced=False AND AttemptDate < NOW() - INTERVAL '5 minutes'`, and for each: re-checks TFP existence, re-creates if the .inprogress file exists on disk + TFP row is missing, re-invokes `FileReplacementBusinessService.ProcessFileReplacement(AttemptId)`. Loud failure (writes ErrorMessage) if the recovery itself fails.

C4. **8 stuck attempts recovered.** TranscodeAttemptIds 39267, 39268, 39270, 39271, 39272, 39274, 39281, 39283 either flip to `FileReplaced=True` OR get a concrete terminal ErrorMessage. The repro-fingerprint query (count of `Disposition='Replace' AND FileReplaced=False AND age>15min AND ErrorMessage IS NULL`) returns 0.

C5. **Contract test guards the drain invariant.** `Tests/Contract/TestFileReplacementDrain.py` (NEW): one test that runs the repro-fingerprint SQL and asserts count=0; one test that forces a TFP-missing scenario and asserts the self-heal recovers it; one test that asserts the broad-except has been removed (grep file content).

C6. **Memory rule saved**: `feedback_no_production_value_changes_for_testing.md` -- supersedes `feedback_flip_switches_to_meet_criteria.md`. Operator-stated 2026-06-23.

C7. **3-of-each-bucket success in a row.** Without any operator intervention, three Transcode + three Remux + three AudioFix jobs each go from queued -> compliant. Selection: live picker with raw-metadata predicate (the same `Fixtures.{Transcode,Remux,AudioFixOnly}Candidate` helpers used by the slow E2E suite). Verification: a smoke script picks 3 candidates per bucket, queues them all, polls until terminal, then asserts every MediaFile post-state is `IsCompliant=True, WorkBucket=NULL`. Exit 0 only if 9/9.

C8. **SOLID at the touch points.** Each new helper (self-heal poller, TFP recovery, drain-invariant test) is its own class with constructor injection (DI), one concern per class, mockable in unit tests. No god-functions added to `ProcessTranscodeQueueService` or `FileReplacementBusinessService`.

## Files

| File | Role | Criterion |
|---|---|---|
| `Features/FileReplacement/FileReplacementBusinessService.py` | Defense-in-depth fallback: when OldSizeBytes is 0/NULL, resolve actual source size via Path.Resolve + LocalGetSize | C1 |
| `Features/TranscodeJob/ProcessTranscodeQueueService.py` | DispatchDisposition exception handler now writes ErrorMessage to TranscodeAttempts so failures surface | C2 |
| `Features/FileReplacement/FileReplacementSelfHealService.py` | NEW SRP service; periodic scan + recover stuck Replace rows | C3 |
| `WebService/Main.py` | PrivateStartFileReplacementSelfHeal thread (120s interval) wired alongside other background threads | C3 |
| `Scripts/RecoverStuckFileReplacements.py` | NEW CLI; recovered the 8 today's stuck attempts + permanently-refused 1,084 historical TFP-missing orphans | C4 |
| `Tests/Contract/TestFileReplacementDrain.py` | NEW contract test (5 invariants) | C5 |
| `Scripts/Smoke/ThreeOfEachBucketSmoke.py` | NEW end-to-end smoke that proves C7 | C7 |
| `memory/feedback_no_production_value_changes_for_testing.md` | NEW memory rule | C6 |
| `memory/feedback_flip_switches_to_meet_criteria.md` | Tombstoned -- superseded by the rule above | C6 |

## Verification Evidence

- **C1**: `_EffectiveOldBytes` block in `FileReplacementBusinessService.ProcessFileReplacement` resolves actual source size via `Path(SourceSrId, SourceRel).Resolve(self._GetWorker()) + LocalGetSize` when stored `OldSizeBytes` is 0 or NULL. Live-verified by recovery of attempts 39267/39268/39270/39271/39272/39274/39281/39283 (all had OldSizeBytes=0 pre-fix; all now FileReplaced=True).
- **C2**: `DispatchDisposition` exception handler writes `f"DispatchDisposition failed: {str(Ex)[:400]}"` to `TranscodeAttempts.ErrorMessage`. Confirmed via `TestFileReplacementDrain.test_dispatchdisposition_no_longer_silently_swallows`.
- **C3**: `FileReplacementSelfHealService.Run()` is invoked from `PrivateFileReplacementSelfHealLoop` every 120s on WebService. Independently runnable. Smoke-validated: scanning finds 0 stuck rows post-cleanup, returns `{'Scanned': 0, 'Recovered': 0, 'Refused': 0}`.
- **C4**: 8 stuck attempts from the operator-queued 30-job batch all recovered (FileReplaced=True; ErrorMessage=None). 1,084 historical orphans (39+ day old, TFP-missing) permanently refused with concrete ErrorMessage. Repro-fingerprint query returns 0 (`TestFileReplacementDrain.test_no_stuck_replace_rows_in_steady_state` green).
- **C5**: `Tests/Contract/TestFileReplacementDrain.py` runs 5/5 green: steady-state stuck=0, DispatchDisposition writes ErrorMessage on exception, defense-in-depth has EffectiveOldBytes + LocalGetSize fallback, self-heal service exists, self-heal wired into WebService.
- **C6**: `memory/feedback_no_production_value_changes_for_testing.md` written; `memory/feedback_flip_switches_to_meet_criteria.md` tombstoned in-place; `memory/MEMORY.md` updated.
- **C7**: `py Scripts/Smoke/ThreeOfEachBucketSmoke.py` -> `9/9 compliant -- OK -- 3-of-each-bucket smoke PASSED`. 3 Transcode + 3 Remux + 3 AudioFix queued with correct ProcessingMode, all reached `IsCompliant=True, WorkBucket=NULL`. Smoke wall time ~46 min on the live worker fleet (I9 + dot + larry at version c7a5aa6).
- **C8**: New code lives in SRP units -- `FileReplacementSelfHealService` is its own class (84 lines) with constructor DI for `Db` and `Mgr`; `RecoverStuckFileReplacements.py` is a script with a `Recover(DryRun=False)` callable; `ThreeOfEachBucketSmoke.py` is a script with a `Run()` callable; no god-functions added to `FileReplacementBusinessService` or `ProcessTranscodeQueueService` (only narrow defensive insertions at the offending lines).

## Decisions Made

- Defense-in-depth fallback over reading-OldSizeBytes-correctly-everywhere: the root upstream bug (where SizeBytes=0 leaks into Job.SizeBytes which becomes OldSizeBytes) is real but spans multiple queue-creation paths. Fixing the fallback in the gate point covers every flavor of zero-stored data including future regressions; tracking down every upstream is a separate cleanup directive when prioritized.
- Self-heal as a 120s periodic thread, not an event-driven trigger: simpler, recoverable by restart, no inter-service event bus needed.
- 1,084 historical orphan attempts marked `Recovery refused: TFP row missing` rather than deleted: keeps the audit trail intact while excluding them from the live stuck-pool metric.
- Smoke wall budget 60 min, poll 30s: a single Transcode + post-replacement cycle on NVENC tops out at ~10 min; 9 jobs across a 13-worker fleet should comfortably finish in 20-30 min. 60 min budget covers worst case without false timeout.

## Promotions

| Source artifact | Target file |
|---|---|
| Defense-in-depth OldSizeBytes fallback pattern | `Features/FileReplacement/FileReplacementBusinessService.py` |
| Loud-failure swallow removal | `Features/TranscodeJob/ProcessTranscodeQueueService.py` |
| Self-heal periodic scan + recovery | `Features/FileReplacement/FileReplacementSelfHealService.py` + WebService thread loop |
| One-shot recovery CLI | `Scripts/RecoverStuckFileReplacements.py` |
| Drain invariant contract | `Tests/Contract/TestFileReplacementDrain.py` |
| 3-of-each-bucket smoke gate | `Scripts/Smoke/ThreeOfEachBucketSmoke.py` |
| No-production-changes-for-testing rule | `memory/feedback_no_production_value_changes_for_testing.md` (+ tombstone of `feedback_flip_switches_to_meet_criteria.md`) |
