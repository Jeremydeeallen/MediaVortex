# FileReplacement Drain Bug

**Slug:** filereplacement-drain-bug
**Set:** 2026-06-22
**Status:** Active -- phase: NEEDS_PLAN
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

## Plan -- to be finalized at NEEDS_PLAN exit

NEEDS_PLAN tasks before advancing:

1. Read `Features/FileReplacement/FileReplacement.feature.md` + `transcoded-output-placement.feature.md` for the contract.
2. Read `Features/FileReplacement/FileReplacementBusinessService.ProcessFileReplacement` to see what it actually does at the failure surface.
3. Read `Features/TranscodeJob/ProcessTranscodeQueueService.DispatchDisposition` -- this is the synchronous caller (lines 642-664). The except-Exception swallow on line 660 is the first suspect: any failure inside `ProcessFileReplacement` gets logged but the `Disposition='Replace'` row was already committed (line 58 of `DispositionDispatcher.Dispatch`), so the operator sees the Replace decision but no replacement.
4. Pull the WorkerService logs for the 8 stuck attempts (TranscodeAttemptIds 39267, 39268, 39270, 39271, 39272, 39274, 39281, 39283) to see what `ProcessFileReplacement` actually raised.
5. Finalize Files list + numbered Criteria + Verification.

## Carry-forward (to be merged into Acceptance Criteria at NEEDS_PLAN exit)

From `harness-drift-fixes` C6.1: "BypassReplace -> FileReplaced=True within 60s". This invariant has never actually been verified post-fix; compliance-symmetry inherited it and didn't address the actual code path. This directive owns it.

## Files (placeholder -- finalized at NEEDS_PLAN exit)

Likely surface, pending investigation:

- `Features/FileReplacement/FileReplacementBusinessService.py` -- the `ProcessFileReplacement` entry point; whatever it raises silently is the bug
- `Features/TranscodeJob/ProcessTranscodeQueueService.py` -- `DispatchDisposition` line 660 except-Exception swallow
- New retry / self-heal mechanism for stuck-Replace rows (poller? CLI? admin endpoint?)
- New contract test `Tests/Contract/TestFileReplacementDrain.py` (NEW) -- asserts repro-fingerprint count is 0 + drives a forced-failure path to verify the loud-failure mode

## R18 overrides

(none yet)

## Status

NEEDS_PLAN. Investigate the silent-failure surface (DispatchDisposition line 660 except-Exception + ProcessFileReplacement internals) and decide between (a) loud-fail at the call site, (b) retry-with-budget self-heal, (c) both. Then enumerate Criteria + Files.
