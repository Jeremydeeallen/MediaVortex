# Feature: Transcoded Output Placement (side-by-side + `-mv` suffix)

## What It Does

Standardizes where MediaVortex writes transcoded output and what it names the final file after replacement. Two changes, one feature doc, one PR -- both touch the same FileReplacement output-path logic.

1. **Placement.** Every worker writes the staged transcoded file to the same directory as its source ("InPlace" / side-by-side). The `Workers.StagingDirectory` column is no longer read; the column is dropped in this feature's migration. No per-worker scratch.
2. **Final naming.** After successful FileReplacement the output file is named `<basename>-mv.<ext>` (e.g. `Show.mkv` source -> `Show-mv.mp4` final). The `-mv` suffix is permanent and survives.

Together these fix three problems with one change:
- **Cross-worker hand-off.** Today `larry-worker-1.StagingDirectory='/staging/larry-worker-1'` is container-local; any other worker that claims the VMAF row gets "file not found". Workers 2/3/4 use the shared NFS path. Side-by-side eliminates the inconsistency.
- **Same-name collision.** The 2026-05-09 `BuildRemuxCommand` bug (KNOWN-ISSUES.md:104) destroyed source files when input ext == output ext and OutputPath == InputPath. A permanent `-mv` suffix on the final filename means source and output are structurally distinct on disk regardless of any future code regression.
- **On-disk audit gap.** Today only `MediaFiles.TranscodedByMediaVortex` knows which files MediaVortex produced. With `-mv` the filesystem itself is self-describing -- an operator browsing the share in Explorer / `ls` can tell at a glance.

## Concern

Operator dogfood, 2026-05-10. Two adjacent topics surfaced in the same conversation: VMAF cross-system reachability (sparked by larry-worker-1 vs 2/3/4 staging-path drift) and a request for an on-disk visibility marker that also serves as defense-in-depth against extension-collision regressions of the 2026-05-09 bug. Both concerns touch the FileReplacement output-path computation; bundling them avoids two near-simultaneous PRs that fight over the same lines.

## Surface

- **Operator-visible.** Final filenames on the NAS shift from `<basename>.<ext>` to `<basename>-mv.<ext>` for new transcodes going forward. Pre-existing transcoded files are NOT renamed.
- **Configuration.** `Workers.StagingDirectory` becomes obsolete; the column is dropped.
- **No new HTTP endpoints, no new UI.** The Activity / SQLQueries pages display whatever's in `MediaFiles.FilePath`, which now ends in `-mv.<ext>` for new transcodes.
- **External library impact (Plex / Jellyfin / Kodi).** Filename changes by design -- libraries that match by probed metadata (GUID / episode signature) re-link cleanly; libraries that match by exact filename refresh their mapping. No data loss; some watch-progress reset is possible per library.

## Success Criteria

### A. Side-by-side placement

1. Every worker writes the staged transcoded file to a path whose directory equals the source directory. Verifiable: on i9 and any larry worker, after a transcode `os.path.dirname(LocalOutputPath) == os.path.dirname(LocalSourcePath)` for the matching `TemporaryFilePaths` row.

2. No live code reads `Workers.StagingDirectory`. Verifiable: `grep -rn "StagingDirectory\|stagingdirectory" --include="*.py"` outside `archive_*/` and the migration script returns no matches.

3. The worker that produces a transcoded file is not required for VMAF: any worker with `QualityTestEnabled=TRUE` can claim the VMAF row and read the transcoded file. Verifiable: cross-worker integration test -- worker A produces, worker B (different hostname, different OS) consumes the VMAF row and completes successfully against the same source/transcoded pair, with the canonical paths translated to each worker's local mount.

### B. `-mv` final naming

4. After a successful FileReplacement the final on-disk filename is `<basename>-mv.<ext>` where `<ext>` is the transcode output container (`mp4` today). The original is removed (`KeepSource=False`) or renamed to `<basename>.old.<orig-ext>` (`KeepSource=True`). Verifiable: post-replacement of `T:\Show\Show.mkv`, the source no longer exists, `T:\Show\Show-mv.mp4` exists; if `KeepSource=True`, `T:\Show\Show.old.mkv` exists.

5. The `-mv` suffix applies to all MediaVortex output flows -- transcode, remux, subtitle-fix. Verifiable: a remux of `Show.avi` produces `Show-mv.mp4`; a transcode of `Show.mkv` produces `Show-mv.mp4`; a subfix of `Show.mp4` produces `Show-mv.mp4`. Three asserts in the integration suite.

6. A double-suffix `<basename>-mv-mv.<ext>` never appears on disk. The transcode pipeline refuses to admit a queue row whose source filename already ends in `-mv.<ext>`. Verifiable: insert a `TranscodeQueue` row with `FilePath` ending in `-mv.mp4`, run populate; the row is rejected with `Reason='AlreadyMediaVortexTranscoded'`. Audit query against MediaFiles also returns 0 rows matching `FilePath LIKE '%-mv-mv.%'` on a healthy library.

7. `MediaFiles.FilePath` for newly-transcoded rows ends in `-mv.<ext>`. Verifiable: for any cutover-date threshold T, `SELECT COUNT(*) FROM MediaFiles WHERE TranscodedByMediaVortex=TRUE AND ReplacementDate > T AND FilePath NOT LIKE '%-mv.%'` returns 0.

### C. No backfill, no breakage

8. Pre-existing transcoded files keep their current names. No bulk rename. Verifiable: `SELECT COUNT(*) FROM MediaFiles WHERE TranscodedByMediaVortex=TRUE AND ReplacementDate < '<cutover>' AND FilePath LIKE '%-mv.%'` returns 0. The `-mv` convention applies only to new replacements.

9. `FileScanning` recognizes the `.old.<ext>` form as a MediaVortex artifact and does not insert it into `MediaFiles` or `TranscodeQueue`. Verifiable: scan a directory containing `Show-mv.mp4` and `Show.old.mkv`; only the `.mp4` row is created in `MediaFiles`. The `.old.<ext>` is also excluded from queue admission.

10. The atomic-rename collision check at FileReplacement time still refuses to overwrite an existing target. Verifiable: pre-place a `Show-mv.mp4` in the source directory, then trigger replacement for a transcode that would produce the same path; replacement fails with `target already exists` and rolls the original back from `.orig` -- source is bit-identical to its pre-replacement state.

### D. Migration

11. SQL migration drops `Workers.StagingDirectory`. Verifiable: `\d Workers` no longer shows the column.

12. The migration is idempotent. Verifiable: run twice; the second run is a no-op (no error, no row count change).

## Status

**NOT IMPLEMENTED** -- doc-first feature, awaiting operator approval.

### Progress

- [x] 1. Surfaced two related concerns (cross-worker scratch reachability, on-disk audit gap) on 2026-05-10
- [x] 2. Confirmed via DB query that i9 already InPlace (`StagingDirectory=NULL`) and three of four larry workers use the shared NFS staging path; `larry-worker-1` is the outlier
- [x] 3. Drafted this feature doc with 12 success criteria
- [ ] 4. Operator approval of criteria 1-12
- [ ] 5. SQL migration `Scripts/SQLScripts/DropWorkersStagingDirectory.py` (criteria 11, 12)
- [ ] 6. Update `ProcessTranscodeQueueService` to compute side-by-side staging path unconditionally; remove `StagingDirectory` reads (criteria 1, 2)
- [ ] 7. Update `_ProcessCompleteFileReplacement` to compute final `TargetPath` as `<basename>-mv.<ext>` (criteria 4, 5)
- [ ] 8. Add the `-mv` admission guard to queue populate paths (criterion 6)
- [ ] 9. Update `FileScanning` exclusion list to recognize `.old.<ext>` (criterion 9)
- [ ] 10. Update `transcode.flow.md` Stage 8 with the new naming and the dropped `StagingDirectory` input
- [ ] 11. Cross-worker smoke test: worker A produces, worker B consumes the VMAF (criterion 3)
- [ ] 12. End-to-end smoke on both i9 and larry: a `Show-mv.mp4` lands in `MediaFiles`, no double-suffix anywhere on disk

## Scope

```
Features/TranscodeJob/ProcessTranscodeQueueService.py
Features/FileReplacement/FileReplacementBusinessService.py
Features/FileScanning/FileScanningBusinessService.py
Features/TranscodeQueue/QueueManagementBusinessService.py
Models/CommandBuilder.py
Scripts/SQLScripts/DropWorkersStagingDirectory.py
transcode.flow.md
```

## Files

| File | Role |
|---|---|
| `Features/TranscodeJob/ProcessTranscodeQueueService.py` | Compute staging path side-by-side; stop reading `Workers.StagingDirectory` |
| `Features/FileReplacement/FileReplacementBusinessService.py` | `_ProcessCompleteFileReplacement` final `TargetPath` becomes `<basename>-mv.<ext>` |
| `Features/FileScanning/FileScanningBusinessService.py` | Skip `.old.<ext>` artifacts; do not insert them into `MediaFiles` |
| `Features/TranscodeQueue/QueueManagementBusinessService.py` | Refuse to admit queue rows whose source ends in `-mv.<ext>` |
| `Models/CommandBuilder.py` | `BuildTranscodeCommand` / `BuildRemuxCommand` / `BuildSubtitleFixCommand` -- output paths land side-by-side; staging suffix unchanged (`_transcoded.mp4` / `_remuxed.mp4` / `_subfix.mp4` during the encode) |
| `Scripts/SQLScripts/DropWorkersStagingDirectory.py` | One-shot, idempotent column drop |
| `transcode.flow.md` | Stage 6 inputs table loses `StagingDirectory`; Stage 8 Action describes `-mv` rename and `KeepSource` settle |
| `KNOWN-ISSUES.md` | Cross-worker hand-off (Risk 5 in 2026-05-10 sight pass) closed by criterion 3 |

## Deviation from conventions

None.
