# Cleanup .inprogress orphans + matching DB state

**Set:** 2026-06-15
**Status:** Active -- phase: IMPLEMENTING
**Slug:** inprogress-orphan-cleanup

## Outcome

The 27 stale `.inprogress` files on `/mnt/media_tv` are deleted; the matching DB orphans (in-flight Alvin attempt, 4 attemptless TFP rows, 1 ActiveJobs row) are reconciled. No live encodes are touched.

## Steps

1. Mark `TranscodeAttempts.Id=37624` (Alvin from dot-worker-1) as `Success=FALSE` -- ffmpeg was killed in the prior directive, attempt should not stay in flight forever.
2. Delete the matching `ActiveJobs` row.
3. Delete 4 TFP rows pointing at `.inprogress` paths with no matching attempt.
4. Run `Scripts/SQLScripts/CleanupStaleInProgressFiles.py --commit` against `/mnt/media_tv` to delete the 27 disk orphans (drives M:, Z: not in scope this pass).
5. Re-verify counts after.

No code changes; data-only cleanup.
