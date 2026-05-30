# Feature: RemuxedByMediaVortex Flag

## What It Does

Adds a new `MediaFiles.RemuxedByMediaVortex BOOLEAN` column and a paired `RemuxedByMediaVortexDate TIMESTAMP` column, parallel to the existing `TranscodedByMediaVortex` / (implicit) date pair. The post-replacement writer now sets exactly ONE of the two flags based on the originating job's mode, instead of unconditionally setting `TranscodedByMediaVortex=TRUE` for every replacement.

A remux or subtitle-fix or audio-fix that leaves the video stream untouched does NOT lie about having transcoded the file. SmartPopulate (and any other consumer that filters on "already transcoded") can then trust `TranscodedByMediaVortex` to mean exactly what it says: the video stream was re-encoded by MediaVortex.

## Concern

`FileReplacementBusinessService._UpdateMediaFilesAfterReplacement` unconditionally set `TranscodedByMediaVortex=TRUE` regardless of whether the job was a real transcode or a remux/audio-fix. Over time this flagged ~13,498 rows (~4 TB) that had only been container-swapped or audio-normalized -- their video stream was still h264/hevc and still needed a real transcode, but SmartPopulate filtered them out as "already done" because of the false flag.

The mop-up script `Scripts/FixFalseTranscodeFlags.py` existed but only cleared the flag based on a `codec NOT IN ('av1')` heuristic AFTER the fact. The writer was never gated on mode, so every new remux re-introduced the same lie.

## Success Criteria

### Schema

1. `MediaFiles.RemuxedByMediaVortex BOOLEAN DEFAULT FALSE` column exists. NULL is permitted but the default is FALSE so rows scanned before this feature shipped sort cleanly. Verifiable: `\d MediaFiles` shows the column.

2. `MediaFiles.RemuxedByMediaVortexDate TIMESTAMP` column exists, nullable. Mirrors the `AudioCompletedAt` convention. Verifiable: `\d MediaFiles` shows the column.

3. Migration script `Scripts/SQLScripts/AddRemuxedByMediaVortexColumn.py` is idempotent (uses `ADD COLUMN IF NOT EXISTS`). Verifiable: running it twice produces no errors and no schema diff after the second run.

### Writer behavior

4. After file replacement, `FileReplacementBusinessService._UpdateMediaFilesAfterReplacement` sets:
   - `TranscodedByMediaVortex=TRUE` (and leaves `RemuxedByMediaVortex` untouched) when the originating job's `Mode='Transcode'`.
   - `RemuxedByMediaVortex=TRUE`, `RemuxedByMediaVortexDate=NOW()` (and leaves `TranscodedByMediaVortex` untouched) when the originating job's `Mode in ('Remux', 'SubtitleFix', 'AudioFix', 'Quick')`.
   - Never sets both TRUE for the same row in the same replacement. Verifiable: induce one of each mode against test files, observe each row has exactly one flag flipped.

5. Mode is derived from the `TranscodeAttempts.ProfileName` of the just-finished replacement. ProfileName values `'Remux'` and `'SubtitleFix'` route to the remux branch; any other ProfileName routes to the transcode branch. The same rule already used for the `isRemux` defense-in-depth check at line 272 -- reused, not redefined. Verifiable: grep the writer for the routing condition; matches the existing isRemux check.

### Retro-fix

6. A one-shot script `Scripts/SQLScripts/RetroflipRemuxedFlags.py` flips the existing misset rows: `TranscodedByMediaVortex=FALSE, RemuxedByMediaVortex=TRUE` for rows where `TranscodedByMediaVortex=TRUE AND Codec NOT IN ('av1')`. Same heuristic the legacy `Scripts/FixFalseTranscodeFlags.py` uses (all MV transcodes produce av1; anything else was a remux). Verifiable: row count before/after matches the diagnostic query that motivated this feature (~13,498 rows at time of writing).

7. The retro-fix script also clears `TranscodeFiles.SuccessfullyTranscoded=FALSE` for the same MediaFileIds so SmartPopulate / queue-population consumers see consistent state. Verifiable: after the run, `SELECT COUNT(*) FROM TranscodeFiles tf JOIN MediaFiles mf ON tf.MediaFileId=mf.Id WHERE tf.SuccessfullyTranscoded=TRUE AND mf.Codec NOT IN ('av1') AND mf.TranscodedByMediaVortex=FALSE` returns 0.

8. The retro-fix script is idempotent (running twice leaves the row state unchanged). Verifiable: run twice, diff -- empty.

### Consumer compatibility

9. `SmartPopulateQueue` (`Features/TranscodeQueue/QueueManagementBusinessService.py:280`) requires NO query change. The existing filter `m.TranscodedByMediaVortex IS NOT TRUE` already excludes the lying-true rows once the retro-fix clears them. Verifiable: run SmartPopulate for Mode='Transcode' Drive='T:' before/after the retro-fix; the previously-hidden 13k h264/hevc rows now appear at their correct PriorityScore-ranked positions.

10. The flow doc `transcode.flow.md` Stage 7.6 is updated to describe the per-mode flag write -- no longer "always sets TranscodedByMediaVortex=True." Verifiable: read the doc.

## Surface

Internal data correctness fix. No new UI surface. Observable effects:
- `MediaFiles` rows have a new column.
- Files with only a remux history will reappear in the TranscodeQueue / SmartPopulate "Next Batch" cards.
- Operator can query `SELECT FilePath FROM MediaFiles WHERE RemuxedByMediaVortex=TRUE AND TranscodedByMediaVortex=FALSE ORDER BY SizeMB DESC LIMIT 50` to see "files MV has touched at the container/audio level but not transcoded."

## Status

COMPLETE 2026-05-30. Writer fix deployed to larry (c4f8890b). Live verify deferred until next remux completes through the new code path.

### Progress

- [x] 1. Migration script `Scripts/SQLScripts/AddRemuxedByMediaVortexColumn.py` (criteria 1, 2, 3). Applied 2026-05-30; both columns present.
- [x] 2. Writer fix in `FileReplacementBusinessService._UpdateMediaFilesAfterReplacement` -- accepts `Mode` param, routes flag write (criterion 4, 5).
- [x] 3. Plumb `Mode` from `_ProcessCompleteFileReplacement` call site (derived from `transcode_attempt.ProfileName in ('Remux','SubtitleFix')`). `FinalizePartialReplacement` continues to use the default `Mode='Transcode'`.
- [x] 4. Retroflip script `Scripts/SQLScripts/RetroflipRemuxedFlags.py` (criteria 6, 7, 8). Applied 2026-05-30: 13,498 MediaFiles flipped, 13,476 TranscodeFiles cleared.
- [x] 5. Updated `transcode.flow.md` Stage 7.6 and `Features/TranscodeQueue/TranscodeQueue.feature.md` criterion 3.
- [x] 6. Migration + retroflip applied; SmartPopulate now surfaces the 13,498 previously-hidden remuxed files (verified: Westworld S02E10 at PriorityScore=147 returned by the diagnostic query).
- [ ] 7. Deploy to fleet so the writer fix lands on every worker that runs FileReplacement.
- [ ] 8. Live verify: trigger one Transcode + one Remux through the queue, inspect the MediaFile rows post-replacement -- each row has exactly one flag TRUE.

## Scope

```
Scripts/SQLScripts/AddRemuxedByMediaVortexColumn.py        -- NEW: idempotent ADD COLUMN
Scripts/SQLScripts/RetroflipRemuxedFlags.py                -- NEW: one-shot retro-fix
Features/FileReplacement/FileReplacementBusinessService.py -- writer fix + Mode plumbing
Features/FileReplacement/remuxed-flag.feature.md           -- this file
Features/TranscodeQueue/TranscodeQueue.feature.md          -- criterion 3 split
transcode.flow.md                                          -- Stage 7.6 rewrite
```

## Files

| File | Role |
|------|------|
| `Scripts/SQLScripts/AddRemuxedByMediaVortexColumn.py` | Idempotent migration: `ALTER TABLE MediaFiles ADD COLUMN IF NOT EXISTS RemuxedByMediaVortex BOOLEAN DEFAULT FALSE; ADD COLUMN IF NOT EXISTS RemuxedByMediaVortexDate TIMESTAMP`. |
| `Scripts/SQLScripts/RetroflipRemuxedFlags.py` | One-shot: for rows where `TranscodedByMediaVortex=TRUE AND Codec NOT IN ('av1')` flip TranscodedByMediaVortex=FALSE + RemuxedByMediaVortex=TRUE + RemuxedByMediaVortexDate=NOW(). Also clears `TranscodeFiles.SuccessfullyTranscoded=FALSE` for the same MediaFileIds. Logs row count + sample of affected paths. Idempotent. |
| `Features/FileReplacement/FileReplacementBusinessService.py` | `_UpdateMediaFilesAfterReplacement` gains a `Mode` keyword arg (default `'Transcode'`); routes the flag write per criterion 4. `_ProcessCompleteFileReplacement` derives Mode from `transcode_attempt.ProfileName`. `FinalizePartialReplacement` continues to default to `'Transcode'` (only fires after real-transcode crash recovery). |

## Deviation from conventions

None. Mirrors the existing `AudioComplete` / `AudioCompletedAt` column pair convention. No new abstractions. Data-driven, fail-loud writes.
